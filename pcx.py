"""Windows helpers for Jarvis V3: active window, per-app volume (pycaw), clipboard, Focus Shield, screen translator."""

from __future__ import annotations

import ctypes
import re
import threading
import time
from ctypes import wintypes

import core

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

BROWSERS = {"chrome.exe", "msedge.exe", "browser.exe", "firefox.exe", "opera.exe", "brave.exe", "vivaldi.exe", "yandex.exe"}
IDES = {"code.exe", "cursor.exe", "pycharm64.exe", "idea64.exe", "devenv.exe", "sublime_text.exe", "notepad++.exe",
        "webstorm64.exe", "clion64.exe", "rider64.exe", "zed.exe", "windowsterminal.exe"}
# words people use for an app -> process names
ALIASES = {
    "браузер": BROWSERS, "хром": {"chrome.exe"}, "яндекс": {"browser.exe"}, "edge": {"msedge.exe"},
    "дискорд": {"discord.exe"}, "discord": {"discord.exe"}, "телеграм": {"telegram.exe"},
    "музык": {"yandexmusic.exe", "yandex music.exe", "spotify.exe", "browser.exe"}, "спотифай": {"spotify.exe"},
    "стим": {"steam.exe", "steamwebhelper.exe"}, "ютуб": BROWSERS, "youtube": BROWSERS,
}


# ---------------------------------------------------------------------------
# Active window
# ---------------------------------------------------------------------------

def foreground() -> tuple[int, str, str]:
    """(hwnd, window title, process .exe name in lower case)."""
    import psutil

    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        exe = psutil.Process(pid.value).name().lower()
    except Exception:  # noqa: BLE001
        exe = ""
    return hwnd, buf.value, exe


def kind(exe: str) -> str:
    if exe in BROWSERS:
        return "browser"
    if exe in IDES:
        return "ide"
    if core.CONFIG.get("_game_mode"):
        return "game"
    return "app"


def close_window(hwnd: int) -> None:
    user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE: the app may still ask to save


# ---------------------------------------------------------------------------
# Clipboard (ctypes, no extra packages)
# ---------------------------------------------------------------------------

def clipboard() -> str:
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    user32.GetClipboardData.restype = ctypes.c_void_p
    for _ in range(5):
        if user32.OpenClipboard(0):
            break
        time.sleep(0.05)
    else:
        return ""
    try:
        h = user32.GetClipboardData(13)   # CF_UNICODETEXT
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p) if p else ""
        finally:
            kernel32.GlobalUnlock(ctypes.c_void_p(h))
    finally:
        user32.CloseClipboard()


def copy_from_app(keys: list[str]) -> str:
    """Press keys in the active app (e.g. ctrl+l, ctrl+c) and read what landed in the clipboard."""
    import keyboard

    before = clipboard()
    for k in keys:
        keyboard.send(k)
        time.sleep(0.12)
    for _ in range(10):
        now = clipboard()
        if now and now != before:
            return now
        time.sleep(0.05)
    return clipboard() if clipboard() != before else ""


# ---------------------------------------------------------------------------
# Per-app volume (pycaw)
# ---------------------------------------------------------------------------

def _sessions():
    import comtypes
    from pycaw.pycaw import AudioUtilities

    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    return [s for s in AudioUtilities.GetAllSessions() if s.Process]


def match_exes(name: str) -> set[str]:
    n = name.lower().strip()
    if n in ("игра", "игру", "игры", "game") and core.CONFIG.get("_game_exe"):
        return {core.CONFIG["_game_exe"].lower()}
    for k, exes in ALIASES.items():
        if k in n:
            return set(exes)
    n = re.sub(r"\.exe$", "", n)
    return {n + ".exe"} if n else set()


def app_volume(exes: set[str], level: float | None = None, delta: float | None = None, mute: bool | None = None) -> list[str]:
    """Change the volume of the apps whose process name is in exes (or contains the given name). Returns names changed."""
    done = []
    for s in _sessions():
        pname = s.Process.name().lower()
        if pname not in exes and not any(e.replace(".exe", "") in pname for e in exes):
            continue
        vol = s.SimpleAudioVolume
        if mute is not None:
            vol.SetMute(int(mute), None)
        if level is not None or delta is not None:
            cur = vol.GetMasterVolume()
            new = level if level is not None else cur + delta
            vol.SetMasterVolume(max(0.0, min(1.0, new)), None)
            if new > 0:
                vol.SetMute(0, None)
        done.append(pname)
    return sorted(set(done))


def playing_apps() -> list[str]:
    """Apps that are making sound right now."""
    from pycaw.pycaw import IAudioMeterInformation

    out = []
    for s in _sessions():
        try:
            meter = s._ctl.QueryInterface(IAudioMeterInformation)
            if meter.GetPeakValue() > 0.001:          # music fades in: the first seconds are very quiet
                out.append(s.Process.name().lower())
        except Exception:  # noqa: BLE001
            continue
    return out


# ---------------------------------------------------------------------------
# Focus Shield: while a focus timer runs, distracting windows get closed
# ---------------------------------------------------------------------------

DISTRACT_TITLES = re.compile(r"(youtube|tiktok|instagram|twitch|reddit|vk\.com|вконтакте|9gag|netflix|кинопоиск|"
                             r"shorts|reels|одноклассники)", re.I)
DISTRACT_EXES = {"steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "battle.net.exe", "riotclientservices.exe"}
FOCUS = {"until": 0.0, "thread": None, "closed": 0}


def focus_active() -> bool:
    return time.time() < FOCUS["until"]


def focus_start(minutes: float) -> str:
    FOCUS.update(until=time.time() + minutes * 60, closed=0)
    core.emit({"type": "focus", "on": True, "until": FOCUS["until"]})
    if not (FOCUS["thread"] and FOCUS["thread"].is_alive()):
        FOCUS["thread"] = threading.Thread(target=_focus_loop, daemon=True, name="focus-shield")
        FOCUS["thread"].start()
    return f"Фокус-щит включён на {int(minutes)} мин, сэр. YouTube, TikTok и Steam буду закрывать."


def focus_stop() -> str:
    if not focus_active():
        return "Фокус-щит и так выключен."
    FOCUS["until"] = 0.0
    core.emit({"type": "focus", "on": False})
    return f"Фокус-щит выключен. Отвлечений закрыто: {FOCUS['closed']}."


def _distracting(title: str, exe: str) -> bool:
    if exe in DISTRACT_EXES:
        return True
    return exe in BROWSERS and bool(DISTRACT_TITLES.search(title))


def _focus_loop() -> None:
    warned: dict[int, float] = {}
    while focus_active():
        time.sleep(2)
        try:
            hwnd, title, exe = foreground()
            if not _distracting(title, exe):
                continue
            if hwnd in warned and time.time() - warned[hwnd] < 30:
                continue
            warned[hwnd] = time.time()
            core.speak("Сэр, сейчас время фокуса. Закрою через пять секунд.", "ru", urgent=True)
            time.sleep(5)
            hwnd2, title2, exe2 = foreground()
            if hwnd2 != hwnd or not _distracting(title2, exe2):
                continue   # the user switched away by themselves
            if exe2 in BROWSERS:
                import keyboard
                keyboard.send("ctrl+w")   # close only that tab
            else:
                close_window(hwnd2)
            FOCUS["closed"] += 1
            core.log.info("Focus shield closed %s «%s»", exe2, title2[:80])
        except Exception:  # noqa: BLE001
            core.log.exception("focus shield")
    if FOCUS["until"]:   # ran out on its own
        FOCUS["until"] = 0.0
        core.emit({"type": "focus", "on": False})
        core.speak(f"Фокус-сессия окончена, сэр. Отвлечений закрыто: {FOCUS['closed']}.", "ru")


# ---------------------------------------------------------------------------
# Live screen translator
# ---------------------------------------------------------------------------

TRANSLATE = ("Ты переводчик. На снимке — окно программы или игры (возможно на английском, японском или другом языке). "
             "Найди на нём весь значимый текст (меню, диалоги, ошибки, абзацы) и переведи на русский. Выведи только "
             "перевод, сохраняя порядок, короткими строками. Если текст уже русский — ответь: «Текст уже на русском».")


def translate_screen() -> str:
    """Screenshot of the active window -> Russian translation shown as a floating card in the HUD."""
    import base64

    import cloud
    import vision

    title, img = vision.capture()
    if vision._is_blank(img):
        return "Окно для меня чёрное: переключите игру в оконный режим, сэр."
    data = base64.b64encode(vision.png(vision.shrink(img))).decode()
    text = cloud.look(TRANSLATE, "Переведи текст на экране.", data, max_tokens=900)
    core.emit({"type": "translation", "title": title, "text": text})
    return "Перевод на экране, сэр."


# ---------------------------------------------------------------------------
# Live translator: re-translates the active window every few seconds while it changes
# ---------------------------------------------------------------------------

LIVE = {"on": False, "thread": None}


def translate_live(on: bool, every: float = 6.0) -> str:
    LIVE["on"] = on
    core.emit({"type": "translate_live", "on": on})
    if on and not (LIVE["thread"] and LIVE["thread"].is_alive()):
        LIVE["thread"] = threading.Thread(target=_live_loop, args=(every,), daemon=True, name="live-translate")
        LIVE["thread"].start()
    return "Живой перевод включён, сэр: перевод будет в капсуле поверх окон." if on else "Живой перевод выключен."


def _live_loop(every: float) -> None:
    import numpy as np

    import vision

    prev = None
    while LIVE["on"]:
        try:
            title, img = vision.capture()
            if "Джарвис" in title or vision._is_blank(img):
                time.sleep(every)
                continue
            small = vision.shrink(img, 160).astype(np.int16)
            changed = prev is None or prev.shape != small.shape or float(np.abs(small - prev).mean()) > 6
            if changed:
                prev = small
                translate_screen()
        except Exception as e:  # noqa: BLE001
            core.log.warning("live translate: %s", e)
            time.sleep(10)
        time.sleep(every)


# ---------------------------------------------------------------------------
# Audio ducking: music and video get quiet while Jarvis listens and answers
# ---------------------------------------------------------------------------

_DUCK = {"saved": {}, "depth": 0, "lock": threading.Lock()}


def _fade(vol, start: float, end: float, ms: int = 250) -> None:
    steps = max(1, ms // 25)
    for i in range(1, steps + 1):
        try:
            vol.SetMasterVolume(max(0.0, min(1.0, start + (end - start) * i / steps)), None)
        except Exception:  # noqa: BLE001
            return
        time.sleep(0.025)


def duck(level: float = 0.15) -> None:
    """Turn down every app that is playing sound (not Jarvis itself, not games) to `level`."""
    import os

    from pycaw.pycaw import IAudioMeterInformation
    with _DUCK["lock"]:
        _DUCK["depth"] += 1
        if _DUCK["depth"] > 1:
            return
        me = os.getpid()
        game = (core.CONFIG.get("_game_exe") or "").lower()
        for s in _sessions():
            try:
                if s.ProcessId == me or s.Process.name().lower() in ("python.exe", "pythonw.exe", game):
                    continue
                if s._ctl.QueryInterface(IAudioMeterInformation).GetPeakValue() < 0.005:
                    continue      # silent apps stay as they are
                vol = s.SimpleAudioVolume
                cur = vol.GetMasterVolume()
                if cur > level:
                    _DUCK["saved"][s.ProcessId] = cur
                    threading.Thread(target=_fade, args=(vol, cur, level, 200), daemon=True).start()
            except Exception:  # noqa: BLE001
                continue


def unduck() -> None:
    with _DUCK["lock"]:
        _DUCK["depth"] = max(0, _DUCK["depth"] - 1)
        if _DUCK["depth"] or not _DUCK["saved"]:
            return
        saved, _DUCK["saved"] = _DUCK["saved"], {}
    for s in _sessions():
        try:
            if s.ProcessId in saved:
                vol = s.SimpleAudioVolume
                threading.Thread(target=_fade, args=(vol, vol.GetMasterVolume(), saved[s.ProcessId], 500), daemon=True).start()
        except Exception:  # noqa: BLE001
            continue
