"""Jarvis core: skill registry, plugin loader, language helpers, router.

Adding a new ability = dropping a .py file into plugins/ (see plugins/_template.py).
Each skill declares regex patterns per language ("ru", "uz") and a handler that
receives a Ctx and returns the reply text (or None to let other skills try).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import logging
import re
import sys
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PLUGINS_DIR = BASE / "plugins"
for d in (DATA, DATA / "log", DATA / "dictations"):
    d.mkdir(exist_ok=True)

log = logging.getLogger("jarvis")
file_lock = threading.Lock()
LANGS = ("ru", "uz")


# ---------------------------------------------------------------------------
# Language helpers
# ---------------------------------------------------------------------------

_UZ_CYR = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o", "қ": "q", "ғ": "g",
    "ҳ": "h",
})


def detect_lang(text: str) -> str:
    """Guess ru/uz for typed text (speech gets its language from Whisper)."""
    if CONFIG.get("voice", {}).get("languages", ["ru", "uz"]) == ["ru"]:
        return "ru"
    low = text.lower()
    if re.search(r"[ўқғҳ]", low):
        return "uz"
    if re.search(r"[а-яё]", low):
        return "ru"
    if re.search(r"[a-z]", low):
        return "uz"
    return "ru"


def normalize(text: str, lang: str) -> str:
    """Lowercase, unify apostrophes (o'/g'), strip punctuation.

    Uzbek is converted to Latin without apostrophes: "qo'sh" -> "qosh".
    """
    t = text.lower().replace("ё", "е")
    if lang == "uz":
        t = t.translate(_UZ_CYR)
        t = re.sub(r"[ʻʼ'’‘`´]", "", t)
    t = re.sub(r"[^\w\s:]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


_NUMS = {
    # ru
    "ноль": 0, "один": 1, "одну": 1, "одна": 1, "одно": 1, "первое": 1, "первую": 1, "первый": 1,
    "два": 2, "две": 2, "второе": 2, "вторую": 2, "второй": 2, "три": 3, "третье": 3, "третью": 3,
    "четыре": 4, "четвертое": 4, "четвертую": 4, "пять": 5, "пятое": 5, "пятую": 5, "шесть": 6,
    "шестое": 6, "семь": 7, "седьмое": 7, "восемь": 8, "восьмое": 8, "девять": 9, "девятое": 9,
    "десять": 10, "десятое": 10, "одиннадцать": 11, "двенадцать": 12, "пятнадцать": 15,
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
    "полчаса": 30, "пару": 2, "пара": 2,
    # uz
    "bir": 1, "birinchi": 1, "ikki": 2, "ikkinchi": 2, "uch": 3, "uchinchi": 3, "tort": 4,
    "tortinchi": 4, "besh": 5, "beshinchi": 5, "olti": 6, "oltinchi": 6, "yetti": 7,
    "yettinchi": 7, "sakkiz": 8, "sakkizinchi": 8, "toqqiz": 9, "toqqizinchi": 9, "on": 10,
    "oninchi": 10, "yigirma": 20, "ottiz": 30, "qirq": 40, "ellik": 50, "oltmish": 60,
}


def parse_number(text: str) -> Optional[int]:
    """'25', 'двадцать пять', 'yigirma besh', '3-chi' -> int."""
    text = text.strip()
    m = re.match(r"^(\d+)", text)
    if m:
        return int(m.group(1))
    total, found = 0, False
    for w in text.split():
        w = re.sub(r"(chi|nchi|inchi)$", "", w) if w not in _NUMS else w
        if w in _NUMS:
            total += _NUMS[w]
            found = True
        elif found:
            break
    return total if found else None


NUM_RE = r"(\d+|(?:[a-zа-я]+(?:\s+[a-zа-я]+)?))"


def now() -> dt.datetime:
    return dt.datetime.now()


_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среду": 2, "среда": 2, "четверг": 3, "пятницу": 4, "пятница": 4,
    "субботу": 5, "суббота": 5, "воскресенье": 6,
    "dushanba": 0, "seshanba": 1, "chorshanba": 2, "payshanba": 3, "juma": 4, "shanba": 5, "yakshanba": 6,
}
_PARTS_OF_DAY = {"утром": 9, "днем": 14, "днём": 14, "вечером": 19, "ночью": 23,
                 "ertalab": 9, "tushda": 13, "kechqurun": 19, "kechasi": 23}


def parse_when(text: str) -> tuple[Optional[dt.datetime], str]:
    """Find a date/time in normalized ru/uz text.

    Returns (datetime or None, text with the date words removed).
    "купить хлеб завтра в 10" -> (tomorrow 10:00, "купить хлеб")
    "ertaga soat 9 da non olish" -> (tomorrow 09:00, "non olish")
    """
    t = f" {text} "
    base = now()
    day: Optional[dt.date] = None
    hour = minute = None

    def cut(pattern: str) -> Optional[re.Match]:
        nonlocal t
        m = re.search(pattern, t)
        if m:
            t = t[:m.start()] + " " + t[m.end():]
        return m

    m = cut(r" через (\d+|[а-я]+(?: [а-я]+)?)? ?(минут\w*|час\w*|дн\w*|день|недел\w*) ")
    m = m or cut(r" (\d+|[a-z]+(?: [a-z]+)?) (daqiqa|minut|soat|kun|hafta)\w* ?(?:dan|tan)? (?:keyin|song) ")
    if m:
        n = parse_number(m.group(1) or "1") or 1
        unit = m.group(2)
        delta = (dt.timedelta(minutes=n) if unit.startswith(("минут", "daqiqa", "minut"))
                 else dt.timedelta(hours=n) if unit.startswith(("час", "soat"))
                 else dt.timedelta(weeks=n) if unit.startswith(("недел", "hafta"))
                 else dt.timedelta(days=n))
        when = base + delta
        return when.replace(second=0, microsecond=0), re.sub(r"\s+", " ", t).strip()

    if cut(r" (сегодня|bugun) "):
        day = base.date()
    elif cut(r" (послезавтра|индинга|indinga) "):
        day = base.date() + dt.timedelta(days=2)
    elif cut(r" (завтра|ertaga) "):
        day = base.date() + dt.timedelta(days=1)
    else:
        m = cut(r" (?:в |во )?(" + "|".join(_WEEKDAYS) + r")(?: kuni)? ")
        if m:
            ahead = (_WEEKDAYS[m.group(1)] - base.weekday()) % 7 or 7
            day = base.date() + dt.timedelta(days=ahead)

    m = cut(r" (?:в|к|до) (\d{1,2})(?::(\d{2})| (\d{2}))?(?: час\w*| утра| вечера| дня)? ")
    m = m or cut(r" soat (\d{1,2})(?::(\d{2})| (\d{2}))?(?: ?da| ?ga| gacha)? ")
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or m.group(3) or 0)
        if "вечера" in m.group(0) and hour < 12:
            hour += 12
    else:
        m = cut(r" (" + "|".join(_PARTS_OF_DAY) + r") ")
        if m:
            hour, minute = _PARTS_OF_DAY[m.group(1)], 0

    if day is None and hour is None:
        return None, text
    if hour is None:
        hour, minute = 9, 0
    if not (0 <= hour < 24 and 0 <= (minute or 0) < 60):
        return None, text
    when = dt.datetime.combine(day or base.date(), dt.time(hour, minute or 0))
    if day is None and when <= base:
        when += dt.timedelta(days=1)
    return when, re.sub(r"\s+", " ", t).strip()


MODES = {
    "work": {"ru": "рабочий", "uz": "ish"},
    "friend": {"ru": "дружеский", "uz": "do'stona"},
    "polite": {"ru": "вежливый", "uz": "hurmatli"},
    "tactical": {"ru": "тактический", "uz": "taktik"},
    "coder": {"ru": "программист", "uz": "dasturchi"},
    "business": {"ru": "бизнес", "uz": "biznes"},
    "custom": {"ru": "свой", "uz": "o'zim"},
    "quiet": {"ru": "тихий", "uz": "jim"},
}


def mode() -> str:
    """Character: the V3 persona chosen in the HUD (tactical / coder / business / custom) wins;
    otherwise the active profile's personality (friend / work / polite)."""
    persona = setting("assistant", "persona", "")
    if persona in MODES:
        return persona
    m = active_profile().get("personality") or CONFIG.get("assistant", {}).get("mode", "friend")
    return m if m in MODES else "friend"


# ---------------------------------------------------------------------------
# Profiles ("режимы"): each has a personality and its own set of on/off features
# ---------------------------------------------------------------------------

# Every feature Jarvis can switch per profile: key -> (title, description, default)
FEATURES = {
    "voice_replies":    ("Отвечать голосом", "Иначе ответы только текстом в окне", True),
    "wake_reply":       ("Говорить «Слушаю» после имени", "Иначе короткий сигнал", True),
    "name_listening":   ("Слышать «Джарвис» в обычной речи", "«Hey Jarvis» работает всегда", True),
    "conversation":     ("Продолжать разговор без имени", "Можно отвечать, не говоря «Джарвис» снова", True),
    "chat":             ("Свободный разговор с ИИ", "Вопросы, болтовня, советы", True),
    "smart_understanding": ("Понимать свободные фразы", "ИИ переводит любую формулировку в команду", True),
    "greeting":         ("Приветствие при включении", "", True),
    "briefing":         ("Полный отчёт при включении", "Дела, почта, сообщения, YouTube, советы", True),
    "due_reminders":    ("Напоминать о сроках дел", "За 10 минут и в сам срок", True),
    "task_nudges":      ("Сводки открытых дел", "Каждые несколько часов", True),
    "message_alerts":   ("Сообщать о новых письмах и сообщениях", "Telegram, WhatsApp, почта — только личные", False),
    "break_reminders":  ("Напоминать о перерыве", "Каждые 50 минут работы", False),
    "water_reminders":  ("Напоминать пить воду", "Каждые 90 минут", False),
    "quiet_voice":      ("Говорить тише", "Голос Джарвиса на половину громкости", False),
    "dnd":              ("Не беспокоить", "Никаких сообщений по своей инициативе, кроме будильников", False),
    "voice_lock":       ("Слушаться только моего голоса", "После «Запомни мой голос»: чужие голоса и звук из колонок не будят Джарвиса", True),
    "ducking":          ("Приглушать музыку, когда я говорю", "Музыка и видео тише, пока Джарвис слушает и отвечает", True),
    "barge_in":         ("Перебивать голосом", "Начните говорить, пока Джарвис отвечает, — он замолчит и выслушает", True),
}

_F = {k: v[2] for k, v in FEATURES.items()}

DEFAULT_PROFILES = {
    "normal": {"title": "Обычный", "icon": "🏠", "personality": "friend", "features": dict(_F),
               "actions": [], "say": "Обычный режим. Я рядом."},
    "work": {"title": "Работа", "icon": "💼", "personality": "work",
             "features": {**_F, "chat": True, "conversation": False, "message_alerts": True, "break_reminders": True,
                          "water_reminders": True, "briefing": True},
             "actions": [], "say": "Режим работы. Только по делу."},
    "study": {"title": "Учёба", "icon": "📚", "personality": "polite",
              "features": {**_F, "message_alerts": False, "task_nudges": False, "break_reminders": True,
                           "water_reminders": True, "quiet_voice": True},
              "actions": [], "say": "Режим учёбы. Не отвлекаю, напомню о перерыве."},
    "game": {"title": "Игра", "icon": "🎮", "personality": "friend",
             "features": {**_F, "wake_reply": False, "conversation": False, "briefing": False, "greeting": False,
                          "task_nudges": False, "message_alerts": False, "break_reminders": False,
                          "water_reminders": False, "dnd": True, "ducking": False},
             "actions": [], "say": "Игровой режим. Удачи, не мешаю."},
    "rest": {"title": "Отдых", "icon": "🛋", "personality": "friend",
             "features": {**_F, "message_alerts": True, "task_nudges": False},
             "actions": ["https://music.yandex.ru"], "say": "Режим отдыха. Включаю музыку."},
    "night": {"title": "Ночь", "icon": "🌙", "personality": "polite",
              "features": {**_F, "wake_reply": False, "briefing": False, "task_nudges": False, "message_alerts": False,
                           "break_reminders": False, "water_reminders": False, "quiet_voice": True, "dnd": True},
              "actions": [], "say": "Ночной режим. Спокойной ночи."},
}
PROFILES_FILE = DATA / "profiles.json"
_profile_cache: dict = {}


def profiles() -> dict:
    """All profiles: built-in defaults merged with your saved changes."""
    if _profile_cache.get("data") is not None:
        return _profile_cache["data"]
    saved = load_json(PROFILES_FILE, {}) if PROFILES_FILE.exists() else {}
    out = {}
    for pid, base in {**DEFAULT_PROFILES, **{k: v for k, v in saved.get("profiles", {}).items() if k not in DEFAULT_PROFILES}}.items():
        p = json.loads(json.dumps(base))
        user = saved.get("profiles", {}).get(pid, {})
        p.update({k: v for k, v in user.items() if k != "features"})
        p["features"] = {**_F, **base.get("features", {}), **user.get("features", {})}
        out[pid] = p
    data = {"profiles": out, "active": saved.get("active", "normal"),
            "schedule": saved.get("schedule", [{"profile": "night", "from": 23, "to": 8, "enabled": False}]),
            "auto_game": saved.get("auto_game", True)}
    if data["active"] not in out:
        data["active"] = "normal"
    _profile_cache["data"] = data
    return data


def save_profiles(data: dict) -> None:
    with file_lock:
        PROFILES_FILE.write_text(json.dumps({k: v for k, v in data.items() if not k.startswith("_")},
                                            ensure_ascii=False, indent=2), encoding="utf-8")
    _profile_cache["data"] = data
    emit({"type": "profiles"})


_overrides: dict = {}   # temporary automatic profiles: {"game": "game", "schedule": "night"}


def set_override(source: str, pid: str | None) -> None:
    """Automatic switch (game detected, schedule). Priority: game > schedule > your choice."""
    before = active_profile_id()
    if pid:
        _overrides[source] = pid
    else:
        _overrides.pop(source, None)
    after = active_profile_id()
    if after != before:
        log.info("Profile %s -> %s (%s)", before, after, source)
        emit({"type": "profiles"})


def active_profile_id() -> str:
    data = profiles()
    for src in ("game", "schedule"):
        if _overrides.get(src) in data["profiles"]:
            return _overrides[src]
    return data["active"]


def active_profile() -> dict:
    data = profiles()
    return data["profiles"].get(active_profile_id(), data["profiles"]["normal"])


def feature(name: str) -> bool:
    """Is this feature on in the active profile?"""
    return bool(active_profile()["features"].get(name, _F.get(name, True)))


def set_profile(pid: str, announce: bool = True, lang: str = "ru") -> str:
    data = profiles()
    if pid not in data["profiles"]:
        return ""
    data["active"] = pid
    _overrides.pop("schedule", None)   # your explicit choice wins over the timetable until it changes again
    save_profiles(data)
    p = data["profiles"][pid]
    run_profile_actions(p)
    return p.get("say") or f"Режим {p['title']}."


def run_profile_actions(p: dict) -> None:
    """Open the apps/sites/folders listed for this profile."""
    import os

    for target in p.get("actions", []):
        try:
            if target.startswith(("http://", "https://", "shell:", "ms-settings:")) or Path(target).exists():
                os.startfile(target)
            else:
                apps = sys.modules.get("jarvis_plugin_apps")
                if apps:
                    found = apps.find_app(target)
                    if found:
                        os.startfile(found[1])
        except Exception:  # noqa: BLE001
            log.exception("profile action %s failed", target)


def set_feature(name: str, value: bool, pid: str | None = None) -> None:
    data = profiles()
    pid = pid or active_profile_id()
    data["profiles"][pid]["features"][name] = bool(value)
    save_profiles(data)


def address(lang: str) -> str:
    """How Jarvis addresses you in the current mode ("сэр", your name, or nothing)."""
    a = CONFIG.get("assistant", {})
    name = a.get("user_name", "")
    if mode() in ("work", "coder", "business"):
        return ""
    if mode() == "friend":
        return name or ("" if lang == "ru" else a.get("honorific_uz", "aka"))
    return a.get("honorific_ru", "сэр") if lang == "ru" else a.get("honorific_uz", "janob")


def styled(text: str, lang: str) -> str:
    """Adapt a reply to the current mode: drop or swap the "сэр"/"janob" address."""
    if not text:
        return text
    a = CONFIG.get("assistant", {})
    who = address(lang)
    for h in {a.get("honorific_ru", "сэр"), "сэр", a.get("honorific_uz", "janob"), "janob"}:
        if not h:
            continue
        if who:
            text = re.sub(rf"\b{re.escape(h)}\b", who, text)
        else:
            text = re.sub(rf",\s*{re.escape(h)}\b|\b{re.escape(h)},\s*|\s*{re.escape(h)}\b", "", text)
    if mode() == "friend" and lang == "ru":   # friends say "ты", not "вы"
        for a_, b_ in (("У вас", "У тебя"), ("у вас", "у тебя"), ("Рад вас", "Рад тебя"), ("Рад Вас", "Рад тебя"),
                       ("Скажите", "Скажи"), ("скажите", "скажи"), ("Вам ", "тебе "), (" вам ", " тебе "),
                       ("Откройте", "Открой"), ("Нажмите", "Нажми"), ("Добавьте", "Добавь"), ("Впишите", "Впиши"),
                       ("повторите, пожалуйста", "повтори, пожалуйста"), ("Повторите", "Повтори")):
            text = text.replace(a_, b_)
    text = re.sub(r"\s+([.,!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def human_when(when: dt.datetime, lang: str) -> str:
    today = now().date()
    if when.date() == today:
        d = "сегодня" if lang == "ru" else "bugun"
    elif when.date() == today + dt.timedelta(days=1):
        d = "завтра" if lang == "ru" else "ertaga"
    else:
        d = when.strftime("%d.%m")
    return f"{d} в {when:%H:%M}" if lang == "ru" else f"{d} soat {when:%H:%M} da"


# ---------------------------------------------------------------------------
# Context passed to skills
# ---------------------------------------------------------------------------

@dataclass
class Ctx:
    text: str
    lang: str
    source: str = "текст"
    config: dict = field(default_factory=dict)
    match: Optional[re.Match] = None
    norm: str = ""

    def __post_init__(self) -> None:
        if not self.norm:
            self.norm = normalize(self.text, self.lang)

    def t(self, ru: str, uz: Optional[str] = None) -> str:
        """Pick the reply in the user's language."""
        return uz if (self.lang == "uz" and uz) else ru

    def group(self, i: int | str = 1) -> str:
        return (self.match.group(i) or "").strip() if self.match else ""

    def cfg(self, section: str) -> dict:
        return self.config.get(section, {}) or {}

    def say(self, text: str) -> None:
        """Speak right now (e.g. progress messages) in addition to the reply."""
        speak(text, self.lang)


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------

@dataclass
class Skill:
    name: str
    handler: Callable[[Ctx], Optional[str]]
    patterns: dict[str, list[re.Pattern]]
    title: dict[str, str]
    examples: dict[str, list[str]]
    priority: int
    module: str


SKILLS: list[Skill] = []
STARTUP_HOOKS: list[Callable[[], None]] = []
_current_module = "core"


def skill(name: str, *, patterns: dict[str, list[str]], title: dict[str, str] | str = "",
          examples: dict[str, list[str]] | None = None, priority: int = 50):
    """Register a skill. Lower priority number = tried earlier."""

    def deco(fn: Callable[[Ctx], Optional[str]]):
        compiled = {lang: [re.compile(p) for p in pats] for lang, pats in patterns.items()}
        ttl = title if isinstance(title, dict) else {"ru": title, "uz": title}
        SKILLS.append(Skill(name, fn, compiled, ttl, examples or {}, priority, _current_module))
        return fn

    return deco


def on_start(fn: Callable[[], None]) -> Callable[[], None]:
    """Run fn in a background thread once the assistant starts (e.g. schedulers)."""
    STARTUP_HOOKS.append(fn)
    return fn


def load_plugins() -> list[str]:
    """(Re)load every plugins/*.py that does not start with '_'. Returns errors."""
    global _current_module
    SKILLS.clear()
    STARTUP_HOOKS.clear()
    errors = []
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        mod_name = f"jarvis_plugin_{path.stem}"
        _current_module = path.stem
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception as e:  # noqa: BLE001
            SKILLS[:] = [s for s in SKILLS if s.module != path.stem]
            errors.append(f"{path.name}: {e}")
            log.error("Plugin %s failed:\n%s", path.name, traceback.format_exc())
    _current_module = "core"
    SKILLS.sort(key=lambda s: s.priority)
    try:
        import tools
        log.info("Loaded %d tools for the brain", tools.load_all())
    except Exception as e:  # noqa: BLE001
        errors.append(f"tools: {e}")
        log.exception("tools failed to load")
    write_capabilities()
    log.info("Loaded %d skills from plugins", len(SKILLS))
    return errors


def start_hooks() -> None:
    for hook in STARTUP_HOOKS:
        threading.Thread(target=hook, daemon=True, name=f"hook-{hook.__name__}").start()


# ---------------------------------------------------------------------------
# Speaking hook (set by assistant.py) and logging
# ---------------------------------------------------------------------------

_speak_fn: Callable[[str, str], None] = lambda text, lang: None  # noqa: E731


def set_speaker(fn: Callable[[str, str], None]) -> None:
    global _speak_fn
    _speak_fn = fn


def speak(text: str, lang: str = "ru", urgent: bool = False) -> None:
    """Jarvis talks on his own (reminders, alerts). "Не беспокоить" mutes everything except urgent ones."""
    text = styled(text, lang)
    if (feature("dnd") and not urgent) or not feature("voice_replies"):
        emit({"type": "message", "role": "jarvis", "text": "🔕 " + text, "lang": lang, "source": "auto"})
        return
    emit({"type": "message", "role": "jarvis", "text": text, "lang": lang, "source": "auto"})
    _speak_fn(text, lang)


# ---------------------------------------------------------------------------
# Event bus for the desktop app (status changes, messages, data updates)
# ---------------------------------------------------------------------------

_listeners: list[Callable[[dict], None]] = []


def subscribe(fn: Callable[[dict], None]) -> None:
    _listeners.append(fn)


def emit(event: dict) -> None:
    event.setdefault("time", now().strftime("%H:%M:%S"))
    for fn in list(_listeners):
        try:
            fn(event)
        except Exception:  # noqa: BLE001
            log.exception("event listener failed")


# ---------------------------------------------------------------------------
# Settings: config.toml + overrides saved from the app (data/settings.json)
# ---------------------------------------------------------------------------

SETTINGS_FILE = DATA / "settings.json"
CONFIG: dict = {}


def load_config() -> dict:
    import tomllib

    with open(BASE / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    for section, values in load_json(SETTINGS_FILE, {}).items():
        cfg.setdefault(section, {}).update(values)
    CONFIG.clear()
    CONFIG.update(cfg)
    return CONFIG


def save_setting(section: str, key: str, value) -> None:
    with file_lock:
        data = load_json(SETTINGS_FILE, {})
        data.setdefault(section, {})[key] = value
        save_json(SETTINGS_FILE, data)
    CONFIG.setdefault(section, {})[key] = value
    emit({"type": "settings"})


_MEMO: dict = {}


def memo(key: str, ttl: float, fn):
    """Remembers fn() for ttl seconds: slow network answers (weather, rates) are not fetched again every time."""
    import time as _time
    hit = _MEMO.get(key)
    if hit and _time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _MEMO[key] = (_time.time(), value)
    return value


def setting(section: str, key: str, default=None):
    return CONFIG.get(section, {}).get(key, default)


LAST_ACTION: dict = {"skill": "", "tools": ""}      # what the last request did, filled by route() and agent.py
HISTORY_FILE = DATA / "history.jsonl"

# Results of the last search (YouTube videos, …): «запусти первое видео» refers to them.
RESULTS: dict = {"kind": "", "items": [], "at": 0.0}


def set_results(kind: str, items: list) -> None:
    import time as _time
    RESULTS.update(kind=kind, items=list(items), at=_time.time())


def get_results(kind: str = "", ttl: float = 1800.0) -> list:
    """Results of the last search, if it is recent (30 min) and of the asked kind."""
    import time as _time
    if not RESULTS["items"] or _time.time() - RESULTS["at"] > ttl:
        return []
    if kind and RESULTS["kind"] != kind:
        return []
    return RESULTS["items"]


def add_history(source: str, user: str, reply: str, lang: str, engine: str) -> None:
    """One line per request: time, source, what was said, what was answered, and what was done."""
    import json
    rec = {"time": now().strftime("%Y-%m-%d %H:%M:%S"), "source": source, "lang": lang, "user": user,
           "reply": reply, "skill": LAST_ACTION.get("skill", ""), "tools": LAST_ACTION.get("tools", ""),
           "engine": engine}
    with file_lock:
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_history(limit: int = 200) -> list[dict]:
    import json
    if not HISTORY_FILE.exists():
        return []
    lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def log_exchange(source: str, lang: str, user: str, reply: str) -> None:
    line = f"- {now():%H:%M:%S} [{source}, {lang}] **Вы:** {user}\n  **Джарвис:** {reply}\n"
    with file_lock, open(DATA / "log" / f"{now():%Y-%m-%d}.md", "a", encoding="utf-8") as f:
        f.write(line)


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    emit({"type": "data", "file": path.name})


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

PENDING: dict = {}               # action waiting for "да"/"нет"
FOLLOWUP = threading.Event()     # assistant should listen again right after speaking
RECORD_REQUEST = threading.Event()   # start the voice recorder (set by the recorder skill / app)
ENROLL_REQUEST = threading.Event()   # "запомни мой голос": the listener records ~20 s and saves a voiceprint
RECORD_STOP = threading.Event()      # stop it (app button; voice "стоп" is handled by the listener)
RECORD_LANG: dict = {"lang": "ru"}

_YES = re.compile(r"^(да|ага|конечно|отправляй|отправь|подтверждаю|давай|верно|yes|ha|xa|albatta|yubor|tasdiqlayman|mayli)\b")
_NO = re.compile(r"^(нет|не надо|отмена|отмени|стоп|no|yoq|kerak emas|bekor)\b")


def ask_confirm(ctx: "Ctx", question: str, action: Callable[[], str]) -> str:
    """Ask the user to confirm an action (e.g. sending a message) before doing it."""
    PENDING.clear()
    PENDING.update(action=action, lang=ctx.lang, expires=now() + dt.timedelta(minutes=2))
    FOLLOWUP.set()
    return question


def _handle_pending(text: str, lang: str) -> Optional[str]:
    if not PENDING:
        return None
    if now() > PENDING["expires"]:
        PENDING.clear()
        return None
    norm = normalize(text, "uz" if detect_lang(text) == "uz" else "ru")
    if re.search(r"\b(нет|не надо|не нужно|отмена|отмени|не выключай)\b", norm):
        PENDING.clear()
        return "Хорошо, отменил."
    if _YES.search(norm) or _YES.search(normalize(text, "uz")):
        action = PENDING["action"]
        PENDING.clear()
        try:
            return action()
        except Exception as e:  # noqa: BLE001
            log.exception("Confirmed action failed")
            return ("Не получилось: " if lang == "ru" else "Bajarilmadi: ") + str(e)
    if _NO.search(norm) or _NO.search(normalize(text, "uz")):
        PENDING.clear()
        return "Хорошо, отменил." if lang == "ru" else "Xo'p, bekor qilindi."
    PENDING.clear()  # something else was said: forget the question
    return None


_rerouting: dict = {}
# skills whose last part is free text by design ("добавь дело <что угодно>") keep the instant path for long phrases
_LONG_OK = {"vision.look", "tasks.add", "notes.add", "notes.search", "notes.recall", "reminders.in", "reminders.at", "messaging.send", "apps.search",
            "apps.youtube", "apps.music", "apps.browser", "modes.name", "recorder.start", "briefing.report", "llm.chat", "pc.about", "pc.analyze", "pc.optimize", "pc.optimize_undo", "pc.scan", "pc.index", "desktop.find_file", "activity.on", "activity.off", "activity.summary", "activity.forget",
            "docs.search", "docs.summary", "memory.fact_add", "memory.recall", "shield.block", "show.lang", "docs.index"}
# never run these from an AI guess — they change or delete things / talk to other people
_NO_SMART = {"system.shutdown", "tasks.clear", "tasks.delete", "notes.delete", "notes.clear", "messaging.send",
             "apps.close", "reminders.cancel", "basics.reload", "recorder.start"}


_POLITE = re.compile(r"(?:,\s*)?\b(?:пожалуйста|плиз|please|будь добр|будь другом)\b,?", re.I)


LAST_QUESTION: dict = {"user": "", "question": "", "source": "", "at": None}   # the brain's own open question
_SHORT_YES = re.compile(r"^(да|ага|угу|давай|да давай|ок|окей|хорошо|конечно|перв\w{2,3}|втор\w{2,3}|трет\w{2,3})$")
_SHORT_NO = re.compile(r"^(нет|не|не надо|не нужно|отмена|да нет)$")


_MISHEARD = [
    (re.compile(r"^(?:атпой|аткрой|открой|открою|открыл|отрой|фаткоя|фоткай|от крой)(?=[\s,])", re.I), "открой"),
    (re.compile(r"^(?:включу|ключи|включай)(?=[\s,])", re.I), "включи"),
    (re.compile(r"^(?:выключу|выключай|и ключи|вы ключи)(?=[\s,])", re.I), "выключи"),
    (re.compile(r"^(?:закрою|закрыл|за крой)(?=[\s,])", re.I), "закрой"),
    (re.compile(r"^(?:топ|стоб)[.,]?\s+(?=музык)", re.I), "стоп "),
    (re.compile(r"\bстоп[.,]\s+музык\w*", re.I), "стоп музыка"),
    (re.compile(r"\b(?:модбук|нотбук|ноутбоок|ноудбук)(?=\w{0,2}\b)", re.I), "ноутбук"),
    # «ноту / нота / ноты» is the laptop when you talk about power, brightness or volume
    (re.compile(r"(?<=\s)(?:ноут(?:а|у|е|ок|ка)?|нот[ауые]|ноток)(?=[.,!?\s]|$)", re.I), "ноутбук"),
    (re.compile(r"\b(?:анекс|янекс|яндес|индекс)(?=\s+музык)", re.I), "яндекс"),
]
_ABOUT_PC = re.compile(r"выключ|включ|перезагруз|яркост|громкост|звук|экран|усыпи|спящ|заблокир", re.I)


def fix_hearing(text: str) -> str:
    """Put right the words that speech recognition regularly gets wrong."""
    out = text.strip()
    for rx, good in _MISHEARD:
        if "нот[" in rx.pattern and not _ABOUT_PC.search(out):
            continue
        out = rx.sub(good, out)
    if out != text.strip():
        log.info("Heard %r -> %r", text, out)
    return out


def _ask_brain(text: str, source: str) -> Optional[str]:
    import agent
    reply = agent.run(text, source)
    if reply and reply.rstrip().endswith("?") and not PENDING:
        LAST_QUESTION.update(user=text, question=reply.strip()[-300:], source=source, at=now())
    return reply


def route(text: str, lang: str, source: str, config: dict) -> str:
    text = re.sub(r"\s{2,}", " ", _POLITE.sub("", text)).strip(" ,")   # «открой, пожалуйста, телеграм» = «открой телеграм»
    if not text:
        return ""
    pending_reply = _handle_pending(text, lang)
    if pending_reply:
        return pending_reply
    if source == "голос":
        text = fix_hearing(text)
    import agent
    # «да» / «нет» to a question the BRAIN asked (skills that ask, like music, wait for their own answer).
    # The answer goes straight to the brain: pasted into the request it would trigger a skill even on «нет».
    q = dict(LAST_QUESTION)
    LAST_QUESTION.update(question="", at=None)          # any next phrase closes the question
    if q["question"] and q["source"] == source and now() - q["at"] < dt.timedelta(minutes=3):
        short = normalize(text, lang).strip(" .!?,")
        if _SHORT_NO.match(short):
            return "Хорошо, не делаю." if lang == "ru" else "Xo'p, qilmayman."
        if _SHORT_YES.match(short):
            return _ask_brain(f"{q['user']} (на твой вопрос «{q['question']}» отвечаю: {text})", source) or "Не понял, повторите, пожалуйста."
    # several actions in one phrase: do them one by one, each through the reliable path
    parts = agent.split_chain(text)
    if len(parts) > 1 and not _rerouting.get("chain"):
        _rerouting["chain"] = True
        try:
            replies = []
            tv_ctx = False
            for p in parts[:5]:
                if tv_ctx and not re.search(r"(?<!\w)(?:телев[ие]?з\w*|телеиз\w*|телик\w*|телек\w*|тв)(?!\w)", p) \
                        and re.search(r"музык|песн|трек|клип|видео|ролик|ютуб|youtube", p):
                    p = p + " на телевизоре"          # «…и поставь музыку» after «…в телевизоре» means the TV
                replies.append(route(p, lang, source, config))
                if re.search(r"(?<!\w)(?:телев[ие]?з\w*|телеиз\w*|телик\w*|телек\w*|тв)(?!\w)", p):
                    tv_ctx = True
        finally:
            _rerouting["chain"] = False
        return " ".join(r for r in replies if r)
    other = [lg for lg in LANGS if lg != lang]
    long_phrase = len(normalize(text, lang).split()) > 5 and feature("smart_understanding")
    # 1st pass: patterns of the detected language; 2nd pass: the other language
    for try_lang in [lang, *other]:
        norm = normalize(text, try_lang)
        for sk in SKILLS:
            # instant shortcuts take long free-form phrases only where the tail is meant to be free text
            if long_phrase and sk.name not in _LONG_OK:
                continue
            for pat in sk.patterns.get(try_lang, []):
                m = pat.search(norm)
                if not m:
                    continue
                ctx = Ctx(text=text, lang=lang, source=source, config=config, match=m, norm=norm)
                try:
                    reply = sk.handler(ctx)
                except Exception as e:  # noqa: BLE001
                    log.exception("Skill %s failed", sk.name)
                    return ctx.t(f"Ошибка в навыке {sk.name}: {e}", f"{sk.name} ko'nikmasida xato: {e}")
                if reply is not None:  # "" = handled silently (e.g. the recorder announces itself)
                    LAST_ACTION.update(skill=sk.name, tools="")
                    log.info("Skill %s handled: %s", sk.name, text)
                    return reply
    # Voice: a one-word fragment that no skill understood is almost always mishearing — ask again
    if source == "голос" and len(normalize(text, lang).split()) < 2:
        FOLLOWUP.set()
        return "Не понял, повторите, пожалуйста." if lang == "ru" else "Tushunmadim, qaytaring."
    # Anything else: the brain decides — call tools (any wording, chains) or just talk.
    if feature("smart_understanding"):
        reply = _ask_brain(text, source)
        if reply is not None:
            return reply
    fallback = next((s for s in SKILLS if s.name == "llm.chat"), None)
    if fallback:
        return fallback.handler(Ctx(text=text, lang=lang, source=source, config=config)) or ""
    return "Не понял команду." if lang == "ru" else "Buyruqni tushunmadim."


# ---------------------------------------------------------------------------
# Capabilities list (data/../CAPABILITIES.md, regenerated on every load)
# ---------------------------------------------------------------------------

def capabilities(lang: str) -> list[tuple[str, list[str]]]:
    seen = []
    for sk in sorted(SKILLS, key=lambda s: (s.module, s.priority)):
        title = sk.title.get(lang) or sk.title.get("ru") or sk.name
        if title and sk.name != "llm.chat":
            seen.append((title, sk.examples.get(lang, [])))
    return seen


def write_capabilities() -> None:
    lines = ["# Что умеет Джарвис / Jarvis nima qila oladi",
             "",
             "Файл создаётся автоматически при запуске из папки plugins/. "
             "Fayl plugins/ papkasidan avtomatik yaratiladi.", ""]
    by_module: dict[str, list[Skill]] = {}
    for sk in SKILLS:
        by_module.setdefault(sk.module, []).append(sk)
    for module, items in sorted(by_module.items()):
        lines.append(f"## {module}")
        lines.append("")
        lines.append("| Навык / Ko'nikma | Примеры (ru) | Misollar (uz) |")
        lines.append("|---|---|---|")
        for sk in items:
            ru = "; ".join(f"«{e}»" for e in sk.examples.get("ru", []))
            uz = "; ".join(f"«{e}»" for e in sk.examples.get("uz", []))
            ttl = sk.title.get("ru", sk.name)
            if sk.title.get("uz") and sk.title.get("uz") != ttl:
                ttl += f" / {sk.title['uz']}"
            lines.append(f"| {ttl} | {ru} | {uz} |")
        lines.append("")
    (BASE / "CAPABILITIES.md").write_text("\n".join(lines), encoding="utf-8")
