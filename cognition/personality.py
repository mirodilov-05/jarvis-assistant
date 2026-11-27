"""Character: the stage of the relationship, the owner's mood, and how Jarvis should talk right now.

The stage comes from real numbers, not from a guess: days since the first exchange, the number of exchanges,
and the thumbs-up against thumbs-down.
  знакомые      first days: polite, careful, no jokes
  друг          3+ days and 30+ exchanges: knows the habits, may joke
  близкий друг  14+ days, 200+ exchanges, and not more corrections than praise: may say «ты опять так делаешь»
  партнёр       60+ days and 1000+ exchanges: offers help unasked, short messages
"""
from __future__ import annotations

import datetime as dt

from cognition import db, memory

STAGES = ["знакомые", "друг", "близкий друг", "партнёр"]


def stage(path=None, today: dt.date | None = None) -> dict:
    with db.conn(path) as c:
        first, n = c.execute("SELECT MIN(created), COUNT(*) FROM episodes").fetchone()
        up = c.execute("SELECT COUNT(*) FROM episodes WHERE valence > 0").fetchone()[0]
        down = c.execute("SELECT COUNT(*) FROM episodes WHERE valence < 0").fetchone()[0]
    days = ((today or dt.date.today()) - dt.date.fromisoformat(first[:10])).days if first else 0
    if days >= 60 and n >= 1000:
        name = "партнёр"
    elif days >= 14 and n >= 200 and up >= down:
        name = "близкий друг"
    elif days >= 3 and n >= 30:
        name = "друг"
    else:
        name = "знакомые"
    return {"stage": name, "index": STAGES.index(name), "days": days, "exchanges": n, "up": up, "down": down}


def recent_voice_mood(path=None, hours: float = 2.0) -> str:
    """The mood the voice showed in the last two hours (set by voice_mood), or ''."""
    with db.conn(path) as c:
        rows = dict(c.execute("SELECT key, value FROM relationship WHERE key IN ('last_mood','last_mood_at')").fetchall())
    if not rows.get("last_mood_at"):
        return ""
    age = dt.datetime.now() - dt.datetime.fromisoformat(rows["last_mood_at"])
    return rows.get("last_mood", "") if age.total_seconds() < hours * 3600 else ""


def guidance(text: str = "", path=None) -> str:
    """One paragraph for the brain: how to talk to this person right now."""
    st = stage(path)
    mood = memory.mood_of(text) or recent_voice_mood(path)
    lines = [f"Стадия отношений: {st['stage']} ({st['exchanges']} разговоров)."]
    lines.append({
        "знакомые": "Говори вежливо и осторожно, без шуток и давления.",
        "друг": "Можно лёгкую шутку, опирайся на известные привычки.",
        "близкий друг": "Можно сказать прямо, если владелец повторяет ошибку: честно и тепло.",
        "партнёр": "Предлагай помощь сам, отвечай коротко и по делу.",
    }[st["stage"]])
    if mood in ("стресс", "усталость"):
        lines.append("Владелец устал или раздражён: отвечай коротко, поддержи, без шуток, предложи помощь.")
    return " ".join(lines)
