"""Jarvis remembers which programs you use and for how long, on this PC only.

What is recorded: the name of the program in front and the time it was in front (one line per stretch).
What is NOT recorded: keystrokes, passwords, screen content, window titles, file contents.
Idle time (no keyboard or mouse for 5 minutes) is not counted. Programs in PRIVATE_APPS are never recorded.
Turn it off with the voice command «выключи запоминание активности»; data/activity.db is deleted with
«забудь мою активность». Stored in data/ on this PC only, never committed.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import sqlite3
import threading
import time
from ctypes import wintypes
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "activity.db"
SETTINGS = BASE / "data" / "activity_settings.json"
SAMPLE_S = 5
IDLE_S = 300
FLUSH_S = 60
PRIVATE_APPS = {"keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe", "lastpass.exe",
                "keeper.exe", "dashlane.exe", "authy.exe", "signal.exe", "telegram.exe", "whatsapp.exe"}
_LOCK = threading.Lock()
_STATE = {"running": False, "thread": None}


def enabled() -> bool:
    try:
        return bool(json.loads(SETTINGS.read_text(encoding="utf-8")).get("enabled"))
    except (OSError, ValueError):
        return False


def set_enabled(value: bool) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"enabled": bool(value), "changed": dt.datetime.now().isoformat(timespec="seconds")}),
                        encoding="utf-8")


def _connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS seg (start REAL, end REAL, app TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS seg_start ON seg(start)")
    return con


def _foreground_app() -> str:
    """Executable name of the window in front (e.g. chrome.exe), or '' if unknown."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        import psutil
        return psutil.Process(pid.value).name().lower()
    except Exception:  # noqa: BLE001
        return ""


def _idle_seconds() -> float:
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO))
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0


def _loop() -> None:
    current, since = "", time.time()
    while _STATE["running"]:
        time.sleep(SAMPLE_S)
        if not enabled():
            _STATE["running"] = False
            break
        now = time.time()
        app = "" if _idle_seconds() > IDLE_S else _foreground_app()
        if app in PRIVATE_APPS:
            app = ""
        if app != current:
            if current:
                _write(since, now, current)
            current, since = app, now
        elif current and now - since >= FLUSH_S:   # save the running stretch too, so the summary is current
            _write(since, now, current)
            since = now
    if current:
        _write(since, time.time(), current)


def _write(start: float, end: float, app: str) -> None:
    if end - start < 1:
        return
    with _LOCK:
        con = _connect()
        with con:
            con.execute("INSERT INTO seg VALUES (?,?,?)", (start, end, app))
        con.close()


def start() -> bool:
    """Start recording in the background if the owner has turned it on."""
    if _STATE["running"] or not enabled():
        return False
    _STATE["running"] = True
    t = threading.Thread(target=_loop, daemon=True, name="activity")
    _STATE["thread"] = t
    t.start()
    return True


def stop() -> None:
    _STATE["running"] = False


def running() -> bool:
    return _STATE["running"]


def forget() -> None:
    stop()
    with _LOCK:
        DB.unlink(missing_ok=True)


def minutes_by_app(since: dt.datetime, until: dt.datetime | None = None, top: int = 8) -> list[tuple[str, float]]:
    if not DB.exists():
        return []
    end = (until or dt.datetime.now()).timestamp()
    start_ts = since.timestamp()
    with _LOCK:
        con = _connect()
        rows = con.execute(
            "SELECT app, SUM(MIN(end, ?) - MAX(start, ?)) FROM seg WHERE end > ? AND start < ? AND app != '' "
            "GROUP BY app ORDER BY 2 DESC LIMIT ?", (end, start_ts, start_ts, end, top)).fetchall()
        con.close()
    return [(app, secs / 60.0) for app, secs in rows if secs and secs > 0]


def today_summary() -> str:
    midnight = dt.datetime.combine(dt.date.today(), dt.time.min)
    rows = minutes_by_app(midnight)
    if not rows:
        return "Сегодня я ещё ничего не записал. Запоминание: " + ("включено." if enabled() else "выключено.")
    total = sum(m for _, m in rows)
    parts = [f"{app.replace('.exe', '')} {int(m)} мин" for app, m in rows[:5]]
    return f"Сегодня за компьютером около {int(total)} мин. Больше всего: " + ", ".join(parts) + "."
