"""First-run personalisation: Jarvis studies this computer once, with the owner's consent, and fits its owner.

What is read — names and facts only, nothing is opened and nothing leaves this PC:
  1. Windows, processor, memory, video card, the default browser, installed programs (pc_profile)
  2. installed games: Steam, Epic and game shortcuts (the games plugin)
  3. the names of the files in the owner's folders, so «найди файл …» works (pc_index)
  4. Russian names for the programs («ворд» → Word, «фотошоп» → Photoshop) — needs the brain, skipped without it

From this Jarvis knows what to open on THIS computer, which browser and music service to use, which games exist,
and which program names to listen for in speech. After that he keeps learning: every new wording that worked is
remembered (appfinder.remember, learning.autolearn). Run again with «изучи мой компьютер» after installing programs.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import threading

import core
import pc_profile

LAUNCHERS = re.compile(r"^(?:steam|epic games(?: launcher)?|ea app|ea|origin|ubisoft connect|uplay|battle\.net|gog galaxy|"
                       r"xbox|riot client|rockstar games launcher)$", re.I)     # stores, not games
STATE: dict = {"running": False, "step": "", "done": [], "failed": [], "result": None, "at": ""}
_LOCK = threading.Lock()

MUSIC = (("яндекс музык", "Яндекс Музыка", "yandex"), ("yandex music", "Яндекс Музыка", "yandex"),
         ("spotify", "Spotify", "spotify"), ("apple music", "Apple Music", "apple"), ("vk музык", "VK Музыка", "vk"))
MESSENGERS = (("telegram", "Telegram"), ("whatsapp", "WhatsApp"), ("discord", "Discord"), ("viber", "Viber"),
              ("skype", "Skype"), ("zoom", "Zoom"), ("teams", "Microsoft Teams"), ("slack", "Slack"))
# programs people name out loud most often: they go first into the speech hint when present on this PC
POPULAR = ("telegram", "discord", "steam", "chrome", "яндекс", "yandex", "firefox", "edge", "opera", "word", "excel",
           "powerpoint", "photoshop", "spotify", "obs", "zoom", "whatsapp", "visual studio code", "notion", "figma")


def _plugin(name: str):
    return sys.modules.get(f"jarvis_plugin_{name}")


def _apps(profile: dict | None) -> list[str]:
    p = profile or {}
    seen, out = set(), []
    for name in (p.get("installed") or []) + (p.get("apps") or []):
        k = name.lower()
        if k not in seen:
            seen.add(k)
            out.append(name)
    return out


def detect(profile: dict | None) -> dict:
    """What the scan says about the owner's habits: music service, messengers, games."""
    apps = [a.lower() for a in _apps(profile)]
    music = next(((title, key) for word, title, key in MUSIC if any(word in a for a in apps)), None)
    messengers = [title for word, title in MESSENGERS if any(word in a for a in apps)]
    return {"music": music[0] if music else "", "music_key": music[1] if music else "",
            "messengers": messengers, "games": list((profile or {}).get("games") or [])}


def _step(name: str, fn) -> object:
    with _LOCK:
        STATE["step"] = name
    core.emit({"type": "personalize", "step": name})
    try:
        out = fn()
        STATE["done"].append(name)
        return out
    except Exception as e:  # noqa: BLE001 — one part failing must not stop the others
        core.log.warning("personalise: %s failed: %s", name, e)
        STATE["failed"].append(f"{name}: {e}"[:160])
        return None


def run() -> dict:
    """Studies the computer (call only after the owner agreed). Returns a short result for the screen and voice."""
    with _LOCK:
        STATE.update(running=True, step="", done=[], failed=[], result=None)
    try:
        profile = _step("Программы и железо", pc_profile.scan) or pc_profile.load() or {}
        apps_mod = _plugin("apps")
        if apps_mod:     # the whole Start menu, Microsoft Store apps too (Telegram, WhatsApp, Spotify from the Store)
            start = _step("Приложения из Пуска и Microsoft Store", lambda: list(apps_mod.app_index().keys())) or []
            have = {a.lower() for a in _apps(profile)}
            extra = [n for n in start if n and n.lower() not in have]
            profile["apps"] = (profile.get("apps") or []) + extra[:400]
        games_mod = _plugin("games")
        games = _step("Игры", lambda: games_mod.all_games(refresh=True) if games_mod else []) or []
        names = sorted({g.get("name", "") for g in games if g.get("name") and not LAUNCHERS.match(g["name"].strip())},
                       key=str.lower)
        profile["games"] = names[:120]
        found = detect(profile)
        profile["music"], profile["messengers"] = found["music"], found["messengers"]
        profile["personalized_at"] = dt.datetime.now().isoformat(timespec="seconds")
        pc_profile.PROFILE.parent.mkdir(parents=True, exist_ok=True)
        core.save_json(pc_profile.PROFILE, profile)
        chosen = (core.load_json(core.SETTINGS_FILE, {}) or {}).get("music", {}).get("service")
        if not chosen:          # the owner's own choice is never overwritten; otherwise what this PC has
            core.save_setting("music", "service", "yandex" if found["music_key"] == "yandex" else "youtube")
        import pc_index
        files = _step("Имена файлов", pc_index.build) or {}
        finder = _plugin("appfinder")
        learned = _step("Русские названия программ", lambda: finder.learn_all() if finder else 0)
        result = {
            "programs": len(_apps(profile)), "games": len(names), "browser": profile.get("browser", ""),
            "music": found["music"], "messengers": found["messengers"],
            "files": int((files or {}).get("files", 0) or 0) if isinstance(files, dict) else 0,
            "names": learned if isinstance(learned, int) else 0,
            "failed": list(STATE["failed"]),
        }
        with _LOCK:
            STATE.update(result=result, at=profile["personalized_at"])
        core.emit({"type": "personalize", "done": True})
        return result
    finally:
        with _LOCK:
            STATE.update(running=False, step="")


def start_background() -> bool:
    if STATE["running"]:
        return False
    threading.Thread(target=run, daemon=True, name="personalize").start()
    return True


def status() -> dict:
    with _LOCK:
        out = {k: (list(v) if isinstance(v, list) else v) for k, v in STATE.items()}
    p = pc_profile.load() or {}
    out["studied"] = bool(p.get("personalized_at") or p.get("scanned_at"))
    out["studied_at"] = p.get("personalized_at") or p.get("scanned_at") or ""
    return out


def say_result(r: dict) -> str:
    parts = [f"Изучил компьютер: {r['programs']} программ"]
    if r.get("games"):
        parts.append(f"игр {r['games']}")
    if r.get("files"):
        parts.append(f"файлов {r['files']}")
    text = ", ".join(parts) + "."
    if r.get("browser"):
        text += f" Браузер по умолчанию: {r['browser']}."
    if r.get("music"):
        text += f" Музыка: {r['music']}."
    if r.get("messengers"):
        text += " Мессенджеры: " + ", ".join(r["messengers"]) + "."
    return text + " Теперь открываю то, что есть именно у вас, и запоминаю, как вы это называете."


# ---------------------------------------------------------------- used by the brain and the speech recogniser

_HINT: dict = {"mtime": None, "text": ""}


def preferences() -> list[str]:
    """What the brain should know about this owner's computer (empty before the first study)."""
    p = pc_profile.load()
    if not p:
        return []
    out = []
    if p.get("browser"):
        out.append("браузер — " + p["browser"])
    games = p.get("games") or []
    if games:
        out.append("игры на компьютере — " + ", ".join(games[:12]))
    if p.get("messengers"):
        out.append("мессенджеры — " + ", ".join(p["messengers"]))
    return out


def speech_hint(limit: int = 14) -> str:
    """Names of this PC's programs and games, to help speech recognition hear them right."""
    try:
        mtime = pc_profile.PROFILE.stat().st_mtime
    except OSError:
        return ""
    if _HINT["mtime"] == mtime:
        return _HINT["text"]
    p = pc_profile.load() or {}
    apps = _apps(p)
    low = [a.lower() for a in apps]
    picked: list[str] = []
    for word in POPULAR:
        hit = next((apps[i] for i, a in enumerate(low) if word in a), None)
        if hit and hit not in picked:
            picked.append(hit)
    for g in p.get("games") or []:
        if g not in picked:
            picked.append(g)
    text = ", ".join(n for n in picked[:limit] if len(n) <= 40)
    _HINT.update(mtime=mtime, text=text)
    return text


def studied() -> bool:
    p: dict | None = pc_profile.load()
    return bool(p and (p.get("personalized_at") or p.get("scanned_at")))
