"""The presentation: voice control of the slides («начни доклад», «следующий слайд», «переключись на японский»).

The slides themselves are built in hud_data.deck() from real statistics. This module keeps the current position
on the PC, so the voice and the screen agree. The home screen reads it from /api/hud and follows it.
"""
from __future__ import annotations

import threading

_LOCK = threading.Lock()
STATE = {"active": False, "lang": "ru", "i": 0, "slides": []}


def _deck(lang: str) -> list[dict]:
    import hud_data
    return hud_data.deck(lang)


def public() -> dict:
    s = STATE
    cur = s["slides"][s["i"]] if s["slides"] and s["i"] < len(s["slides"]) else {}
    return {"active": s["active"], "lang": s["lang"], "i": s["i"], "total": len(s["slides"]), "slide": cur}


def start(lang: str = "ru") -> dict:
    with _LOCK:
        STATE.update(active=True, lang=lang, i=0, slides=_deck(lang))
    return public()


def stop() -> None:
    with _LOCK:
        STATE.update(active=False, i=0)


def step(delta: int) -> dict:
    with _LOCK:
        if STATE["active"]:
            STATE["i"] = max(0, min(len(STATE["slides"]) - 1, STATE["i"] + delta))
    return public()


def switch(lang: str) -> dict:
    with _LOCK:
        keep = STATE["i"]
        STATE.update(lang=lang, slides=_deck(lang), i=min(keep, max(0, len(STATE["slides"]) - 1)))
    return public()


def say_current() -> str:
    """The text of the current slide, as Jarvis says it out loud."""
    cur = public()["slide"]
    return cur.get("say", "")
