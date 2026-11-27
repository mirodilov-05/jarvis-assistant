"""Detects when the owner tells Jarvis he got something wrong. Pure text rules: no network, no model.

detect(text) -> {"severity": 0.3..1.0, "lang": "ru|uz|en", "pattern": str} or None.
"""
from __future__ import annotations

import re

PATTERNS = {
    "ru": [
        r"нет,?\s*я\s*(имел в виду|хотел|говорил)",
        r"это\s*(не то|неправильно|неверно)",
        r"ты\s*(не понял|не так понял|опять)",
        r"я\s*(уже|раньше)\s*(говорил|сказал)",
        r"зачем\s*ты\s*(это|так)",
        r"почему\s*ты\s*(всегда|снова|опять)",
        r"не\s*надо\s*(так|это)",
        r"надо\s*(было|бы)",
        r"не\s*(та|то)\s*(программа|команда|громкость|вещь)",
        r"я\s*про\s*(музыку|плеер|другое)",
    ],
    "uz": [
        r"yo'q,?\s*men\s*(boshqa|niyat|aytdim)",
        r"bu\s*(noto'g'ri|xato|emas)",
        r"siz\s*(tushunmading|yana)",
        r"nima\s*uchun\s*(shunday|buni)",
        r"men\s*(allaqachon|avval)\s*(aytdim|dedim)",
    ],
    "en": [
        r"\bno,?\s*i\s*(meant|wanted|said)\b",
        r"\bthat'?s\s*(wrong|not right)\b",
        r"\byou\s*(misunderstood|did it again)\b",
    ],
}
ANGER = ("опять", "всегда", "снова", "надоел", "раздража", "yana", "doimo", "again", "always")
QUESTION = ("почему", "зачем", "нега", "nega", "why")


def severity(text: str) -> float:
    """0.3 = a gentle fix, 1.0 = a repeated, annoyed correction."""
    t = text.lower()
    score = 0.3 + 0.2 * sum(1 for m in ANGER if m in t) + 0.15 * sum(1 for m in QUESTION if m in t)
    return round(min(score, 1.0), 2)


def detect(text: str) -> dict | None:
    t = (text or "").lower().strip()
    if len(t) < 3:
        return None
    for lang, pats in PATTERNS.items():
        for pat in pats:
            if re.search(pat, t):
                return {"severity": severity(t), "lang": lang, "pattern": pat}
    return None
