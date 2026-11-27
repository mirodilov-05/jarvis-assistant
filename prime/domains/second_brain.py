"""Second brain: spaced repetition (SM-2) for study cards, and simple local note search.

Search is keyword based on purpose: it runs anywhere, with no native libraries (see the Smart App Control note).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass


@dataclass
class Review:
    ease: float
    interval: int          # days
    due: str               # YYYY-MM-DD


def sm2(ease: float, interval: int, quality: int, today: dt.date) -> Review:
    """SM-2 update. quality: 0..5 (0-2 = forgot, 3-5 = remembered). Ease never drops below 1.3."""
    if not 0 <= quality <= 5:
        raise ValueError("quality must be 0..5")
    if quality < 3:
        new_interval = 1                       # forgot: see it again tomorrow
        new_ease = ease
    else:
        new_ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        if interval == 0:
            new_interval = 1
        elif interval == 1:
            new_interval = 6
        else:
            new_interval = round(interval * new_ease)
    return Review(round(new_ease, 3), new_interval, (today + dt.timedelta(days=new_interval)).isoformat())


_WORD = re.compile(r"[\w']+", re.UNICODE)


def search(query: str, notes: list[dict[str, str]], limit: int = 5) -> list[dict[str, str]]:
    """Notes ranked by how many query words they contain (case-insensitive, word prefixes)."""
    words = {w.lower() for w in _WORD.findall(query) if len(w) >= 3}
    if not words:
        return []
    scored = []
    for n in notes:
        text = n.get("text", "").lower()
        tokens = set(_WORD.findall(text))
        score = sum(1 for w in words if any(t.startswith(w[:4]) for t in tokens) or w in text)
        if score:
            scored.append((score, n))
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:limit]]
