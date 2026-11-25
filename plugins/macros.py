"""No-code macros (V3): a voice phrase -> a chain of actions, edited in the HUD (⚡ Макросы).

data/macros.json:
  [{"id": "a1b2", "phrase": "боевой режим", "reply": "Боевой режим, сэр.",
    "actions": [{"type": "run", "value": "C:\\\\Games\\\\cs2.lnk"},
                {"type": "app_volume", "value": "discord=40"},
                {"type": "url", "value": "https://open.spotify.com"},
                {"type": "keys", "value": "win+d"},
                {"type": "volume", "value": "60"},
                {"type": "wait", "value": "2"},
                {"type": "say", "value": "Готов к бою."},
                {"type": "command", "value": "включи режим игра"}]}]

Voice packs: voices/packs/<name>/ok/*.wav (played when a command is done), start/*.wav (at start-up),
error/*.wav. Pick the pack in the HUD settings. The packs are your own recordings or clips you have the right to use.
"""

from __future__ import annotations

import difflib
import os
import random
import re
import subprocess
import threading
import time
import uuid
import webbrowser
import winsound
from pathlib import Path

import core
from core import Ctx, skill

FILE = core.DATA / "macros.json"
PACKS = core.BASE / "voices" / "packs"
ACTION_TYPES = {
    "run": "Запустить программу / файл",
    "url": "Открыть сайт",
    "keys": "Нажать клавиши (ctrl+shift+esc)",
    "volume": "Общая громкость 0–100",
    "app_volume": "Громкость программы (discord=40)",
    "say": "Сказать фразу",
    "command": "Любая команда Джарвису",
    "wait": "Пауза, секунд",
    "snap": "Окно текущей программы: left / right / max / min",
}

# window placement for «snap» steps: Windows' own shortcuts on the foreground window
_SNAP_KEYS = {"left": "windows+left", "right": "windows+right", "max": "windows+up", "min": "windows+down"}


def load() -> list[dict]:
    return core.load_json(FILE, [])


def save(items: list[dict]) -> None:
    with core.file_lock:
        core.save_json(FILE, items)
    core.emit({"type": "macros"})


def upsert(item: dict) -> dict:
    items = load()
    item = {"id": item.get("id") or uuid.uuid4().hex[:6], "phrase": item.get("phrase", "").strip(),
            "reply": item.get("reply", "").strip(),
            "actions": [{"type": a["type"], "value": str(a.get("value", ""))} for a in item.get("actions", [])
                        if a.get("type") in ACTION_TYPES]}
    items = [m for m in items if m["id"] != item["id"]] + [item]
    save(items)
    return item


def delete(mid: str) -> None:
    save([m for m in load() if m["id"] != mid])


def find(text: str) -> dict | None:
    norm = core.normalize(text, "ru").strip(" .!?")
    norm = re.sub(r"^(?:эй |хей )?(?:джарвис|jarvis)\s+", "", norm)   # «Джарвис, боевой режим» is the same macro
    best, score = None, 0.0
    for m in load():
        ph = core.normalize(m["phrase"], "ru").strip(" .!?")
        if not ph:
            continue
        s = 1.0 if norm == ph else difflib.SequenceMatcher(None, norm, ph).ratio()
        if s > score:
            best, score = m, s
    return best if score >= 0.86 else None


def _master_volume(level: int) -> None:
    """Set the Windows master volume to level %."""
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    dev = AudioUtilities.GetSpeakers()
    vol = getattr(dev, "EndpointVolume", None)
    if vol is None:                                  # older pycaw
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        vol = cast(dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
    vol.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)


def run_action(a: dict) -> str:
    t, v = a["type"], a.get("value", "").strip()
    if t == "run":
        if os.path.exists(v.strip('"')):
            os.startfile(v.strip('"'))
        else:
            subprocess.Popen(v, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    elif t == "url":
        webbrowser.open(v if "://" in v else "https://" + v)
    elif t == "keys":
        import keyboard
        keyboard.send(v)
    elif t == "volume":
        _master_volume(int(float(v)))
    elif t == "app_volume":
        import pcx
        app, _, level = v.partition("=")
        pcx.app_volume(pcx.match_exes(app), level=float(level or 50) / 100)
    elif t == "say":
        core.speak(v, "ru")
    elif t == "command":
        return core.route(v, "ru", "макрос", core.CONFIG) or ""
    elif t == "wait":
        time.sleep(min(30.0, float(v or 1)))
    elif t == "snap":
        import keyboard
        keyboard.send(_SNAP_KEYS.get(v.lower(), "windows+up"))
    return ""


def run(m: dict) -> str:
    replies = []
    for a in m["actions"]:
        try:
            out = run_action(a)
            if out:
                replies.append(out)
        except Exception:  # noqa: BLE001
            core.log.exception("macro %s action %s failed", m["phrase"], a)
            replies.append(f"Шаг «{ACTION_TYPES.get(a['type'], a['type'])}» не получился.")
    core.log.info("Macro «%s» done: %d actions", m["phrase"], len(m["actions"]))
    return m.get("reply") or " ".join(replies) or "Готово."


core._LONG_OK.add("macros.run")


@skill("macros.run", title={"ru": "Мои макросы (фраза → цепочка действий)", "uz": "Makroslar"},
       patterns={"ru": [r"^(.+)$"], "uz": [r"^(.+)$"]}, examples={"ru": [], "uz": []}, priority=0)
def macro_skill(ctx: Ctx) -> str | None:
    m = find(ctx.text)
    if not m:
        return None   # not a macro: let the other skills / the brain handle it
    return run(m)


# ---------------------------------------------------------------------------
# Voice packs
# ---------------------------------------------------------------------------

def packs() -> list[str]:
    return sorted(p.name for p in PACKS.iterdir() if p.is_dir()) if PACKS.exists() else []


def active_pack() -> str:
    name = core.setting("voice", "pack", "")
    return name if name and (PACKS / name).is_dir() else ""


def clip(kind: str) -> Path | None:
    pack = active_pack()
    if not pack:
        return None
    files = list((PACKS / pack / kind).glob("*.wav"))
    return random.choice(files) if files else None


def play(kind: str, wait: bool = False) -> bool:
    """Play a character clip (0.01 s, no synthesis). False if the pack has none — then the synthesiser speaks."""
    c = clip(kind)
    if not c:
        return False
    if wait:
        winsound.PlaySound(str(c), winsound.SND_FILENAME)
    else:
        threading.Thread(target=winsound.PlaySound, args=(str(c), winsound.SND_FILENAME), daemon=True).start()
    return True
