"""Proactive messages: Jarvis speaks first, but only on real signals and within limits.

Signals (checked every five minutes):
  * a break: 150 minutes in a row without a 5-minute pause (keyboard and mouse idle time, from activity.py);
  * a check-in: the owner's words in the last two hours sounded tired or stressed.
Limits: never at night (23:00–08:00), never in game mode, never more than three messages a day, each signal once a day.
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
import time

from cognition import db

BREAK_AFTER_MIN = 150
IDLE_RESET_S = 300
MAX_PER_DAY = 3
_STATE = {"streak_min": 0.0, "last_check": 0.0}


def _get(key: str, path=None) -> str:
    with db.conn(path) as c:
        row = c.execute("SELECT value FROM relationship WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def _set(key: str, value: str, path=None) -> None:
    with db.conn(path) as c:
        c.execute("INSERT INTO relationship(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def allowed(now: dt.datetime, path=None) -> bool:
    if now.hour >= 23 or now.hour < 8:
        return False
    a = sys.modules.get("assistant")
    if a is not None and getattr(a, "GAME", {}).get("on"):
        return False
    today = now.date().isoformat()
    sent = _get("proactive_day", path)
    count = int(_get("proactive_count", path) or 0) if sent == today else 0
    return count < MAX_PER_DAY


def _sent(now: dt.datetime, path=None) -> None:
    today = now.date().isoformat()
    count = int(_get("proactive_count", path) or 0) if _get("proactive_day", path) == today else 0
    _set("proactive_day", today, path)
    _set("proactive_count", str(count + 1), path)


def decide(now: dt.datetime, idle_s: float, streak_min: float, path=None) -> list[str]:
    """The messages to say now (a pure function of the inputs: easy to test)."""
    out: list[str] = []
    if idle_s >= IDLE_RESET_S:
        streak_min = 0.0
    today = now.date().isoformat()
    if streak_min >= BREAK_AFTER_MIN and _get("break_day", path) != today and allowed(now, path):
        out.append("Вы работаете уже два с половиной часа. Встаньте, разомнитесь минут пять, сэр.")
        _set("break_day", today, path)
    last = _get("last_mood_at", path)
    recent = last and (now - dt.datetime.fromisoformat(last)).total_seconds() < 2 * 3600
    if recent and _get("last_mood", path) in ("стресс", "усталость") and _get("checkin_day", path) != today and allowed(now, path):
        out.append("Вы, похоже, устали. Могу отложить дела на завтра или просто помолчать. Скажите, что нужно.")
        _set("checkin_day", today, path)
    return out


def tick(now: dt.datetime | None = None, idle_s: float | None = None, speak=None, path=None) -> list[str]:
    """One check. Returns what was said (tests read it)."""
    now = now or dt.datetime.now()
    if idle_s is None:
        from activity import _idle_seconds
        idle_s = _idle_seconds()
    if idle_s < IDLE_RESET_S:
        _STATE["streak_min"] += 5.0
    else:
        _STATE["streak_min"] = 0.0
    msgs = decide(now, idle_s, _STATE["streak_min"], path)
    for m in msgs:
        _sent(now, path)
        if speak is None:
            import core
            core.speak(m, "ru")
    return msgs


def start() -> None:
    def loop():
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001 — a background helper must never crash the assistant
                pass
            time.sleep(300)
    threading.Thread(target=loop, daemon=True, name="proactive").start()
