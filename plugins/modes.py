"""Profiles ("режимы") and personality, all by voice.

Profiles: Обычный, Работа, Учёба, Игра, Отдых, Ночь (+ your own from the app).
Each profile has a personality (friend / work / polite) and on/off features
(see core.FEATURES). Switch: "Режим работа", "Включи режим учёбы", "Ночной режим".
Toggle in the current mode: "Выключи напоминания о перерыве", "Включи озвучку сообщений".
"""

import datetime as dt
import re
import time

import core
from core import Ctx, skill

# spoken names -> profile id
PROFILE_WORDS = {
    "normal": r"обычн\w*|стандартн\w*|домашн\w*|по умолчанию",
    "work": r"работ\w*|рабоч\w*|делов\w*|офис\w*",
    "study": r"учеб\w*|учебн\w*|занят\w*|фокус\w*|концентрац\w*",
    "game": r"игр\w*|игров\w*|гейм\w*",
    "rest": r"отдых\w*|расслаб\w*|чил\w*",
    "night": r"ноч\w*|сон|сна|спат\w*",
}

# spoken names -> feature key
FEATURE_WORDS = [
    ("break_reminders", r"перерыв|отдых(а)? от работы|разминк"),
    ("water_reminders", r"вод[уыа]|пить"),
    ("message_alerts", r"сообщени|письм|почт|уведомлени|оповещени"),
    ("task_nudges", r"сводк|напоминани[яй] о делах|сводки дел"),
    ("due_reminders", r"срок|напоминани[яй] о сроках|дедлайн"),
    ("greeting", r"приветстви"),
    ("briefing", r"отчет при включении|утренн\w* отчет|отчет при запуске|утренн\w* сводк"),
    ("voice_replies", r"голосов\w* ответ|отвечать голосом|говорить голосом|озвучк\w* ответ|голос$"),
    ("wake_reply", r"слушаю|ответ на имя"),
    ("conversation", r"продолжени\w* разговор|разговор без имени|диалог"),
    ("chat", r"болтовн|свободн\w* разговор|разговор\w* с ии"),
    ("smart_understanding", r"умн\w* понимани|понимани\w* фраз"),
    ("quiet_voice", r"тих\w* голос|говорить тише"),
    ("dnd", r"не беспокоить"),
    ("name_listening", r"слушать имя|реагировать на имя"),
]


def find_profile(text: str) -> str | None:
    data = core.profiles()
    for pid, rx in PROFILE_WORDS.items():
        if re.search(rf"\b({rx})", text):
            return pid
    for pid, p in data["profiles"].items():   # your own profiles by title
        if p.get("title", "").lower() in text:
            return pid
    return None


def find_feature(text: str) -> str | None:
    for key, rx in FEATURE_WORDS:
        if re.search(rx, text):
            return key
    return None


@skill(
    "modes.switch",
    title={"ru": "Включить режим (работа, учёба, игра, отдых, ночь, обычный)"},
    patterns={"ru": [r"^(?:джарвис )?(?!.*(?:спящ|режим сна|гибернац|какой ))(?:включи |переключи(?:сь)? на |перейди в |активируй |давай )?(?:режим )?(.+?) режим$",
                     r"^(?:джарвис )?(?!.*(?:спящ|режим сна|гибернац|какой ))(?:включи |переключи(?:сь)? на |перейди в |активируй )?режим (.+)$"]},
    examples={"ru": ["Режим работа", "Включи режим учёбы", "Ночной режим", "Режим отдыха"]},
    priority=1,
)
def switch(ctx: Ctx):
    words = ctx.group(1)
    if re.search(r"(друг|вежлив|официальн)", words):
        return None   # personality, handled below
    pid = find_profile(words)
    if not pid:
        return None
    return core.set_profile(pid)


@skill(
    "modes.list",
    title={"ru": "Какие есть режимы и какой включён"},
    patterns={"ru": [r"(какие|какой) (есть |у тебя |сейчас )?режим", r"в каком (ты )?режиме", r"список режимов"]},
    examples={"ru": ["Какой сейчас режим?", "Какие есть режимы?"]},
    priority=2,
)
def list_modes(ctx: Ctx) -> str:
    data = core.profiles()
    cur = core.active_profile()
    names = ", ".join(p["title"] for p in data["profiles"].values())
    auto = ""
    if core.active_profile_id() != data["active"]:
        auto = " (включился автоматически)"
    return f"Сейчас режим «{cur['title']}»{auto}. Есть режимы: {names}."


@skill(
    "modes.features",
    title={"ru": "Что включено в этом режиме"},
    patterns={"ru": [r"что (у тебя |сейчас )?(включено|выключено)", r"какие (функции|настройки) (включены|в этом режиме)"]},
    examples={"ru": ["Что сейчас включено?"]},
    priority=2,
)
def features(ctx: Ctx) -> str:
    p = core.active_profile()
    on = [core.FEATURES[k][0].lower() for k, v in p["features"].items() if v and k in core.FEATURES]
    off = [core.FEATURES[k][0].lower() for k, v in p["features"].items() if not v and k in core.FEATURES]
    if ctx.source == "голос":   # short spoken version: say whichever list is shorter
        if len(off) <= len(on):
            return f"Режим «{p['title']}»: включено {len(on)} из {len(on) + len(off)}. Выключено: {', '.join(off) or 'ничего'}."
        return f"Режим «{p['title']}»: включено только: {', '.join(on) or 'ничего'}."
    return f"Режим «{p['title']}». Включено: {', '.join(on) or 'ничего'}. Выключено: {', '.join(off) or 'ничего'}."


@skill(
    "modes.toggle",
    title={"ru": "Включить или выключить функцию в текущем режиме"},
    patterns={"ru": [r"^(?:джарвис )?(включи|выключи|отключи|не надо|перестань|прекрати|убери|верни|разреши|запрети)\w* (.+)$"]},
    examples={"ru": ["Выключи напоминания о перерыве", "Включи озвучку сообщений", "Включи режим не беспокоить",
                     "Перестань говорить голосом"]},
    priority=9,
)
def toggle(ctx: Ctx):
    verb, what = ctx.group(1), ctx.group(2)
    key = find_feature(what)
    if not key:
        return None   # "включи музыку", "выключи звук" etc. belong to other skills
    on = verb in ("включи", "верни", "разреши")
    if key == "voice_replies" and verb in ("перестань", "прекрати"):
        on = False
    core.set_feature(key, on)
    title = core.FEATURES[key][0]
    return f"{'Включил' if on else 'Выключил'}: {title.lower()} — в режиме «{core.active_profile()['title']}»."


@skill(
    "modes.personality",
    title={"ru": "Характер: друг, деловой, вежливый"},
    patterns={"ru": [r"(режим друг\w*|дружеский режим|давай как друзья|будь (мне )?другом|давай поболтаем)",
                     r"(вежливый режим|режим вежлив\w*|будь вежлив\w*|официальный режим|говори на вы)",
                     r"(говори по делу|будь краток|без лишних слов|коротко отвечай)"]},
    examples={"ru": ["Давай как друзья", "Будь вежливым", "Говори по делу"]},
    priority=1,
)
def personality(ctx: Ctx) -> str:
    n = ctx.norm
    kind = "friend" if re.search(r"друг|друзья|поболтаем", n) else "polite" if re.search(r"вежлив|официальн|на вы", n) else "work"
    data = core.profiles()
    pid = core.active_profile_id()
    data["profiles"][pid]["personality"] = kind
    core.save_profiles(data)
    core.save_setting("assistant", "persona", kind)   # V3: the HUD character switch follows the voice
    core.emit({"type": "v3"})
    return {"friend": "Окей, общаемся по-дружески!", "polite": "Хорошо, буду предельно вежлив, сэр.",
            "work": "Понял. Коротко и по делу."}[kind]


@skill(
    "modes.name",
    title={"ru": "Запомнить, как меня зовут"},
    patterns={"ru": [r"^(?:джарвис )?(?:меня зовут|зови меня|называй меня|моё имя|мое имя) ([а-яa-z]+(?: [а-яa-z]+)?)$"]},
    examples={"ru": ["Меня зовут Алекс", "Называй меня босс"]},
    priority=3,
)
def set_name(ctx: Ctx) -> str:
    raw = ctx.group(1)
    pos = ctx.text.lower().find(raw.split()[0])
    name = ctx.text[pos:pos + len(raw)].strip(" .!") if pos >= 0 else raw
    name = name[:1].upper() + name[1:]
    core.save_setting("assistant", "user_name", name)
    return f"Приятно познакомиться, {name}! Запомнил."


@skill(
    "modes.whoami",
    title={"ru": "Как меня зовут"},
    patterns={"ru": [r"как меня зовут", r"ты знаешь как меня зовут"]},
    examples={"ru": ["Как меня зовут?"]},
    priority=3,
)
def whoami(ctx: Ctx) -> str:
    name = core.CONFIG.get("assistant", {}).get("user_name", "")
    return f"Тебя зовут {name}." if name else "Ты ещё не сказал. Скажи: «Меня зовут …»."


def _in_window(hour: int, frm: int, to: int) -> bool:
    if frm == to:
        return False
    return (frm <= hour or hour < to) if frm > to else (frm <= hour < to)


@core.on_start
def scheduler() -> None:
    """Switch profiles by the timetable you set in the app (e.g. Ночь 23 → 8, Работа 9 → 18 on weekdays)."""
    while True:
        try:
            data = core.profiles()
            now = dt.datetime.now()
            target = None
            for rule in data.get("schedule", []):
                if not rule.get("enabled"):
                    continue
                days = rule.get("days")   # list of weekday numbers 0=Mon, or None for every day
                if days and now.weekday() not in days:
                    continue
                if _in_window(now.hour, int(rule.get("from", 0)), int(rule.get("to", 0))):
                    target = rule.get("profile")
                    break
            prev = core._overrides.get("schedule")
            if target != prev:
                core.set_override("schedule", target)
                if target:
                    p = data["profiles"].get(target, {})
                    core.run_profile_actions(p)
                    core.speak(p.get("say") or f"Режим {p.get('title', '')}.", "ru")
        except Exception:  # noqa: BLE001
            core.log.exception("profile scheduler")
        time.sleep(30)


PERSONA_WORDS = {"tactical": r"тактическ|джарвис", "coder": r"программист|кодер|разработчик", "business": r"бизнес|продуктивн|делов",
                 "quiet": r"тих|молча|без голоса", "custom": r"сво[йе]"}


@skill(
    "modes.persona",
    title={"ru": "Характер V3: тактический, программист, бизнес, тихий, свой"},
    patterns={"ru": [r"(?:характер|персона|роль|режим характера)\s+(тактическ\w*|программист\w*|кодер|разработчик|бизнес\w*|"
                     r"продуктивн\w*|тих\w*|сво\w*)",
                     r"(?:стань|будь|включи)\s+(программист\w*|тактическ\w*|бизнес\w*)"]},
    examples={"ru": ["Характер программист", "Характер тактический", "Характер тихий"]},
    priority=2,
)
def persona(ctx: Ctx) -> str:
    word = ctx.group(1)
    kind = next((k for k, rx in PERSONA_WORDS.items() if re.search(rx, word)), "tactical")
    core.save_setting("assistant", "persona", kind)
    core.emit({"type": "v3"})
    return {"tactical": "Тактический режим, сэр.", "coder": "Режим программиста. Слушаю.",
            "business": "Бизнес-режим. Фокус на задачах.", "quiet": "Тихий режим, сэр. Отвечаю текстом.",
            "custom": "Свой характер включён."}[kind]
