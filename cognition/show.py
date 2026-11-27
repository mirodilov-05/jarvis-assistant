"""The presentation on the whole screen: Jarvis presents himself («самопрезентация») or the month («начни доклад»).

The server keeps the one true position (which deck, which slide, which language, whether it reads itself), so the
voice, the buttons and the screen always agree. The window asks /api/show and follows it; every change is also
announced with the event {"type": "show"}.

Auto mode reads each slide out loud and turns to the next one when the voice has finished — the slides never
repeat or run ahead of the voice. Any manual step («дальше», a button, an arrow key) cuts the current phrase,
so the old slide is never read on top of the new one.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
DECKS = {"about": "Самопрезентация", "report": "Отчёт за месяц"}
LANGS = ("ru", "en", "ja")
STATE = {"active": False, "deck": "about", "lang": "ru", "i": 0, "slides": [], "auto": False, "gen": 0}
MIN_SLIDE_S = 3.0          # a slide stays at least this long, even if the voice is off
PAUSE_S = 0.9              # a breath between slides


def _deck(deck: str, lang: str) -> list[dict]:
    import hud_data
    return hud_data.about_deck(lang) if deck == "about" else hud_data.deck(lang)


def _emit() -> None:
    try:
        import core
        core.emit({"type": "show", "active": STATE["active"], "i": STATE["i"]})
    except Exception:  # noqa: BLE001 — the screen also polls, a lost event is not fatal
        pass


def public() -> dict:
    s = STATE
    cur = s["slides"][s["i"]] if s["slides"] and s["i"] < len(s["slides"]) else {}
    return {"active": s["active"], "deck": s["deck"], "deck_name": DECKS.get(s["deck"], ""), "lang": s["lang"], "i": s["i"],
            "total": len(s["slides"]), "slide": cur, "slides": s["slides"], "auto": s["auto"]}


def _speak(text: str, lang: str) -> None:
    import core
    core.stop_speaking()
    if text:
        core.emit({"type": "message", "role": "jarvis", "text": text, "lang": lang, "source": "презентация"})
        core._speak_fn(text, lang)


def say_current() -> str:
    """Reads the current slide out loud (cutting whatever was being said) and returns its text."""
    cur = public()["slide"]
    text = cur.get("say", "")
    _speak(text, STATE["lang"])
    return text


def _auto(gen: int) -> None:
    """Reads the slides one after another, from the current one, until the end, a stop or a manual step."""
    import core
    while True:
        with _LOCK:
            if gen != STATE["gen"] or not STATE["active"] or not STATE["auto"]:
                return
            slide = STATE["slides"][STATE["i"]] if STATE["slides"] else {}
            lang = STATE["lang"]
        text = slide.get("say", "")
        _speak(text, lang)
        started = time.time()
        least = max(MIN_SLIDE_S, len(text) * 0.055 * (MIN_SLIDE_S / 3.0))   # readable even if the voice is off
        time.sleep(min(0.3, PAUSE_S))
        while time.time() - started < 180:
            if gen != STATE["gen"]:
                return
            if not core.speaking() and time.time() - started >= least:
                break
            time.sleep(0.15)
        time.sleep(PAUSE_S)
        with _LOCK:
            if gen != STATE["gen"] or not STATE["auto"]:
                return
            if STATE["i"] >= len(STATE["slides"]) - 1:
                STATE["auto"] = False
                _emit()
                return
            STATE["i"] += 1
        _emit()


def _restart_auto() -> None:
    """Call under _LOCK: a new generation cancels the old reader; start a new one if auto is on."""
    STATE["gen"] += 1
    if STATE["auto"] and STATE["active"]:
        threading.Thread(target=_auto, args=(STATE["gen"],), daemon=True, name="show-auto").start()


def start(lang: str = "ru", deck: str = "about", auto: bool = False) -> dict:
    lang = lang if lang in LANGS else "ru"
    deck = deck if deck in DECKS else "about"
    slides = _deck(deck, lang)
    with _LOCK:
        STATE.update(active=True, deck=deck, lang=lang, i=0, slides=slides, auto=auto)
        _restart_auto()
    _emit()
    return public()


def stop() -> None:
    import core
    with _LOCK:
        STATE.update(active=False, i=0, auto=False)
        STATE["gen"] += 1
    core.stop_speaking()
    _emit()


def pause() -> dict:
    """Stops reading out loud; the slide stays on the screen."""
    with _LOCK:
        was = STATE["auto"]
        STATE["auto"] = False
        STATE["gen"] += 1
    if was:
        import core
        core.stop_speaking()
        _emit()
    return public()


def play() -> dict:
    """Reads the presentation out loud from the current slide."""
    with _LOCK:
        if not STATE["active"]:
            return public()
        STATE["auto"] = True
        _restart_auto()
    _emit()
    return public()


def step(delta: int, speak: bool = False) -> dict:
    """A manual step. In auto mode the reading goes on from the new slide; otherwise it is read only if `speak`."""
    with _LOCK:
        if not STATE["active"]:
            return public()
        STATE["i"] = max(0, min(len(STATE["slides"]) - 1, STATE["i"] + delta))
        auto = STATE["auto"]
        _restart_auto()
    if not auto:
        import core
        core.stop_speaking()
        if speak:
            say_current()
    _emit()
    return public()


def go(i: int) -> dict:
    with _LOCK:
        if not STATE["active"]:
            return public()
        delta = int(i) - STATE["i"]
    return step(delta)


def switch(lang: str, deck: str | None = None) -> dict:
    lang = lang if lang in LANGS else "ru"
    with _LOCK:
        deck = deck if deck in DECKS else STATE["deck"]
    slides = _deck(deck, lang)
    with _LOCK:
        keep = STATE["i"] if deck == STATE["deck"] else 0
        STATE.update(lang=lang, deck=deck, slides=slides, i=min(keep, max(0, len(slides) - 1)))
        _restart_auto()
    _emit()
    return public()


EDGE_VOICES = {"ru": "ru-RU-DmitryNeural", "en": "en-US-GuyNeural", "ja": "ja-JP-KeitaNeural"}


def export_audio(lang: str = "ru", deck: str = "about", out_dir: Path | None = None) -> Path:
    """The whole presentation as one MP3 file (Microsoft voices, needs the internet). Returns the file path."""
    import asyncio

    import core
    import edge_tts
    lang = lang if lang in LANGS else "ru"
    deck = deck if deck in DECKS else "about"
    text = "\n\n".join(s.get("say", "") for s in _deck(deck, lang) if s.get("say"))
    voice = core.setting("voice", f"edge_voice_{lang}", "") or EDGE_VOICES[lang]
    out = (out_dir or core.DATA / "media")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"jarvis_{deck}_{lang}.mp3"
    tmp = path.with_suffix(".part")

    async def run():
        await edge_tts.Communicate(text, voice).save(str(tmp))
    asyncio.run(run())
    if not tmp.exists() or tmp.stat().st_size < 1000:
        raise RuntimeError("голос Microsoft не ответил (нужен интернет)")
    tmp.replace(path)
    return path
