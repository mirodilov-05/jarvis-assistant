"""Jarvis knows every program on this PC — and you can name it in Russian.

«Открой хвинфо» -> HWiNFO 64, «запусти каунтер страйк» -> Counter-Strike 2, «открой вижуал студио» -> Visual Studio
Installer, «закрой дискорд» -> Discord.exe … How:
  1. catalog: Start menu (all users + you), Microsoft Store apps, Steam games, desktop shortcuts
  2. learned names: once in a while the cloud brain writes how a Russian speaker says each program
     (data/app_aliases.json) — so «фотошоп», «ворд», «калькулятор» map to the English names
  3. sound-alike matching: Russian and English are turned into the same phonetic key («каунтер» ≈ «counter»)
  4. last resort: the brain picks the program from your catalog and Jarvis remembers the answer
«Изучи мои программы» relearns now; «Какие программы у меня есть?» lists them.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import threading
import time

import core
from core import Ctx, skill

ALIASES_FILE = core.DATA / "app_aliases.json"
_JUNK = re.compile(r"(uninstall|удалить|readme|manual|documentation|справк|support center|help|website|faq|release notes|"
                   r"odbc|component services|isc?si|debuggable|app cert kit|sample (desktop|uwp)|tools for (desktop|uwp)|"
                   r"memory diagnostics|recoverydrive|steps recorder|print management|security configuration|"
                   r"cross tools|native tools|developer command|developer powershell|module docs|dfrgui|services$)", re.I)

# words Russians use for Windows' own English names (and common programs)
BUILTIN = {
    "блокнот": "notepad", "калькулятор": "calculator", "проводник": "file explorer", "диспетчер задач": "task manager",
    "панель управления": "control panel", "командная строка": "command prompt", "командную строку": "command prompt",
    "редактор реестра": "registry editor", "реестр": "registry editor", "экранная клавиатура": "on-screen keyboard",
    "лупа": "magnify", "ножницы": "snipping tool", "фото": "photos", "камера": "camera", "часы": "clock",
    "магазин": "microsoft store", "пауэршелл": "windows powershell", "павершелл": "windows powershell",
    "монитор ресурсов": "resource monitor", "планировщик заданий": "task scheduler", "просмотр событий": "event viewer",
    "очистка диска": "disk cleanup", "субтитры": "livecaptions", "голосовой доступ": "voiceaccess",
    "удалённый рабочий стол": "remote desktop connection", "удаленный рабочий стол": "remote desktop connection",
    "медиаплеер": "windows media player legacy", "плеер": "windows media player legacy", "гит": "git bash",
    "питон": "python 3.12 (64-bit)", "пайтон": "python 3.12 (64-bit)", "нода": "node.js", "олама": "ollama",
    "оллама": "ollama", "ван драйв": "onedrive", "клаудфлер": "cloudflare one client", "ворп": "cloudflare one client",
    "браузер": "yandex", "яндекс": "yandex", "эдж": "microsoft edge", "интернет": "yandex",
    "кс": "counter-strike 2", "кс 2": "counter-strike 2", "кс2": "counter-strike 2", "кска": "counter-strike 2",
    "контра": "counter-strike 2", "контру": "counter-strike 2", "дота": "dota 2", "доту": "dota 2", "дота 2": "dota 2",
    "кс го": "counter-strike 2", "ксго": "counter-strike 2", "вайфай настройки": "settings",
}


# ---------------------------------------------------------------------------
# Phonetic key: Russian and English written down the same way
# ---------------------------------------------------------------------------

_RU = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "o", "ж": "j", "з": "z", "и": "i", "й": "i",
       "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
       "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "u", "я": "a"}


def key(text: str) -> str:
    t = text.lower()
    t = "".join(_RU.get(ch, ch) for ch in t)
    t = re.sub(r"[®™©]", "", t)
    for a, b in (("ph", "f"), ("ck", "k"), ("qu", "kv"), ("x", "ks"), ("w", "v"), ("oo", "u"), ("ee", "i"), ("ea", "i"),
                 ("ou", "au"), ("th", "t"), ("tion", "shn"), ("dj", "j"), ("y", "i")):
        t = t.replace(a, b)
    t = re.sub(r"c(?=[eiy])", "s", t).replace("c", "k").replace("q", "k")
    t = re.sub(r"[^a-z0-9]", "", t)
    return re.sub(r"(.)\1+", r"\1", t)


def skeleton(k: str) -> str:
    return re.sub(r"[aeiou]", "", k)


def similarity(spoken: str, name: str) -> float:
    a, b = key(spoken), key(name)
    if not a or not b:
        return 0.0
    full = difflib.SequenceMatcher(None, a, b).ratio()
    sk = difflib.SequenceMatcher(None, skeleton(a), skeleton(b)).ratio()
    pref = 1.0 if b.startswith(a) and len(a) >= 4 else 0.0           # «каунтер» opens «Counter-Strike 2»
    return max(full, 0.5 * full + 0.5 * sk, 0.9 * pref)


# ---------------------------------------------------------------------------
# Catalog of programs
# ---------------------------------------------------------------------------

_cat: dict = {"items": {}, "t": 0.0}


def _apps_mod():
    return sys.modules.get("jarvis_plugin_apps")


def catalog(refresh: bool = False) -> dict[str, str]:
    """{program name: how to start it}"""
    if _cat["items"] and not refresh and time.time() - _cat["t"] < 3600:
        return _cat["items"]
    items: dict[str, str] = {}
    apps = _apps_mod()
    if apps:
        if refresh:
            apps._index.clear()
        for name, target in apps.app_index().items():
            if not _JUNK.search(name):
                items[name] = target
    games = sys.modules.get("jarvis_plugin_games")
    if games:
        try:
            for g in games.all_games(refresh=refresh):
                items.setdefault(g["name"].lower(), g["launch"])
        except Exception:  # noqa: BLE001
            pass
    _cat.update(items=items, t=time.time())
    return items


def aliases() -> dict[str, str]:
    return core.load_json(ALIASES_FILE, {})


def _save_aliases(data: dict) -> None:
    with core.file_lock:
        core.save_json(ALIASES_FILE, data)


def remember(spoken: str, name: str) -> None:
    data = aliases()
    data[spoken.lower().strip()] = name
    _save_aliases(data)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

_FILLER = re.compile(r"^(?:мне |пожалуйста )?(?:программу|приложение|прогу|игру|утилиту)\s+", re.I)


def find(spoken: str, use_brain: bool = True) -> tuple[str, str] | None:
    """(program name, target) for a spoken name, or None."""
    s = _FILLER.sub("", spoken.lower().strip(" .!?"))
    if not s:
        return None
    cat = catalog()
    if not cat:
        return None
    # 1) learned and built-in Russian names
    learned = {**{k: v for k, v in BUILTIN.items()}, **aliases()}
    target_name = learned.get(s)
    if not target_name:
        close = difflib.get_close_matches(s, list(learned), n=1, cutoff=0.86)
        target_name = learned[close[0]] if close else None
    if target_name:
        hit = _resolve(target_name, cat)
        if hit:
            return hit
    # 2) sounds alike
    best = max(((similarity(s, n), n) for n in cat), default=(0, ""))
    if best[0] >= 0.78:
        return best[1], cat[best[1]]
    # 3) ask the brain once, then remember
    if use_brain:
        name = _brain_pick(s, list(cat))
        if name:
            remember(s, name)
            return name, cat[name]
    return None


def _resolve(name: str, cat: dict) -> tuple[str, str] | None:
    n = name.lower()
    if n in cat:
        return n, cat[n]
    starts = sorted((k for k in cat if k.startswith(n)), key=len)
    if starts:
        return starts[0], cat[starts[0]]
    inside = sorted((k for k in cat if n in k), key=len)
    return (inside[0], cat[inside[0]]) if inside else None


def _brain_pick(spoken: str, names: list[str]) -> str | None:
    try:
        import cloud
        if not cloud.enabled():
            return None
        listing = "\n".join(sorted(names))
        out = cloud.ask("Ты сопоставляешь название программы, сказанное по-русски, с установленными программами. "
                        "Ответь ТОЛЬКО точным названием из списка или словом NONE.",
                        [{"role": "user", "content": f"Пользователь сказал: «{spoken}».\n\nУстановленные программы:\n{listing}"}],
                        max_tokens=40).strip().strip("«»\"'. ").lower()
    except Exception as e:  # noqa: BLE001
        core.log.warning("app brain pick failed: %s", e)
        return None
    if out in names:
        return out
    close = difflib.get_close_matches(out, names, n=1, cutoff=0.9)
    return close[0] if close else None


def learn_all() -> int:
    """Ask the brain how a Russian speaker names each installed program. Returns how many names were learned."""
    import cloud
    if not cloud.enabled():
        return 0
    names = sorted(catalog(refresh=True))
    learned = 0
    data = aliases()
    for i in range(0, len(names), 60):
        chunk = names[i:i + 60]
        try:
            out = cloud.ask(
                "Для каждой программы напиши, как её чаще всего называют вслух по-русски (1–3 варианта, строчными, "
                "русскими буквами: транслитерация и русские названия, например «discord» -> «дискорд», "
                "«counter-strike 2» -> «каунтер страйк», «кс», «кс 2»). Ответь только JSON-объектом "
                "{\"точное имя программы\": [\"вариант\", ...]}.",
                [{"role": "user", "content": "\n".join(chunk)}], max_tokens=1800)
            js = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
        except Exception as e:  # noqa: BLE001
            core.log.warning("learn apps chunk failed: %s", e)
            continue
        for prog, variants in js.items():
            prog = prog.lower().strip()
            if prog not in chunk or not isinstance(variants, list):
                continue
            for v in variants[:4]:
                v = str(v).lower().strip()
                if v and re.search(r"[а-яё]", v) and v not in data:
                    data[v] = prog
                    learned += 1
        time.sleep(1)
    data["_learned_at"] = int(time.time())
    _save_aliases(data)
    core.log.info("Learned %d Russian names for %d programs", learned, len(names))
    return learned


@core.on_start
def _learn_in_background() -> None:
    """Re-learn the programs once a week (and the first time), quietly, never during a game."""
    def go():
        time.sleep(45)
        if core.CONFIG.get("_game_mode"):
            return
        if time.time() - aliases().get("_learned_at", 0) > 7 * 86400:
            try:
                learn_all()
            except Exception:  # noqa: BLE001
                core.log.exception("learning programs failed")
    threading.Thread(target=go, daemon=True, name="learn-apps").start()


# ---------------------------------------------------------------------------
# Running programs (for «закрой …»)
# ---------------------------------------------------------------------------

def running() -> dict[str, str]:
    """{exe name: window title or exe} of programs with a visible window."""
    import ctypes

    import psutil
    u32 = ctypes.windll.user32
    out: dict[str, str] = {}

    def cb(h, _l):
        if u32.IsWindowVisible(h) and u32.GetWindowTextLengthW(h) > 0:
            buf = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(h, buf, 256)
            pid = ctypes.c_ulong()
            u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            try:
                exe = psutil.Process(pid.value).name().lower()
                out.setdefault(exe, buf.value)
            except Exception:  # noqa: BLE001
                pass
        return True
    u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb), 0)
    return out


def find_running(spoken: str) -> str | None:
    """exe of a running program by its Russian/English name («закрой хвинфо» -> hwinfo64.exe)."""
    s = _FILLER.sub("", spoken.lower().strip(" .!?"))
    procs = running()
    for k in ("python.exe", "pythonw.exe", "explorer.exe", "textinputhost.exe", "applicationframehost.exe"):
        procs.pop(k, None)
    learned = {**BUILTIN, **aliases()}
    want = [s] + ([learned[s]] if s in learned else [])
    best = (0.0, None)
    for exe, title in procs.items():
        for w in want:
            score = max(similarity(w, exe.replace(".exe", "")), similarity(w, title.split(" - ")[-1]), similarity(w, title))
            if score > best[0]:
                best = (score, exe)
    return best[1] if best[0] >= 0.75 else None


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------

@skill("apps.learn", title={"ru": "Изучить мои программы (русские названия)"},
       patterns={"ru": [r"(?:изучи|выучи|обнови|просканируй|пересканируй)(?: все| мои)? (?:программ\w*|приложени\w*|список программ)"]},
       examples={"ru": ["Изучи мои программы"]}, priority=5)
def learn_skill(ctx: Ctx) -> str:
    n = len(catalog(refresh=True))
    threading.Thread(target=learn_all, daemon=True).start()
    return f"Нашёл {n} программ, сэр. Запоминаю, как вы их называете — минуту."


@skill("apps.list", title={"ru": "Какие программы у меня есть"},
       patterns={"ru": [r"(?:какие|сколько) (?:у меня )?(?:есть )?(?:программ\w*|приложени\w*)", r"список (?:моих )?программ"]},
       examples={"ru": ["Какие программы у меня есть?"]}, priority=6)
def list_skill(ctx: Ctx) -> str:
    cat = catalog()
    names = sorted(cat)
    core.emit({"type": "card", "title": f"Программы · {len(names)}", "text": "\n".join(names), "ttl": 60000})
    system = re.compile(r"(command prompt|powershell|python 3|node\.js|git |visual studio|windows |tools|verifier|character map|"
                        r"computer management|control panel|administrative|registry|event viewer|performance monitor|"
                        r"resource monitor|task scheduler|system (configuration|information)|disk cleanup|narrator|magnify|"
                        r"on-screen keyboard|remote desktop|^run$|idle|services|file explorer|task manager)", re.I)
    main = [n for n in names if not system.search(n)]
    return f"У вас {len(names)} программ, сэр. Например: " + ", ".join(main[:8]) + ". Полный список в окне."
