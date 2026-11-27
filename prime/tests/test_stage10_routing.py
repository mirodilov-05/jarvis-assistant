"""Routing table: every phrase must reach exactly its own action. Nothing about the TV ever goes to the brain."""
import asyncio
import dataclasses
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as prime_main  # noqa: E402

TMP = Path(tempfile.mkdtemp())
prime_main.SETTINGS = dataclasses.replace(prime_main.SETTINGS, db_path=TMP / "prime.db", backup_dir=TMP / "backups")
os.environ.pop("GEMINI_API_KEY", None)

# phrase -> expected (tool, args) — the args are checked too when given
TV_ROUTES = {
    "включи телевизор": ("tv_on", {}),
    "включи телик": ("tv_on", {}),
    "включи ТВ": ("tv_on", {}),
    "включить телевизор": ("tv_on", {}),
    "выключи телевизор": ("tv_off", {}),
    "выключи телик": ("tv_off", {}),
    "громче телевизор": ("tv_volume", {"direction": "up"}),
    "тише телевизор": ("tv_volume", {"direction": "down"}),
    "статус телевизора": ("tv_status", {}),
    "открой в телике ютуб": ("tv_youtube", {}),
    "открой ютуб на телевизоре": ("tv_youtube", {}),
    "включи ютуб на телевизоре": ("tv_youtube", {}),
    "телевизор ютуб": ("tv_youtube", {}),
    "запусти ютуб на телике": ("tv_youtube", {}),
    "канал вверх телевизор": ("tv_key", {"key": "KEY_CHUP"}),
    "канал вниз телевизор": ("tv_key", {"key": "KEY_CHDOWN"}),
    "пауза телевизор": ("tv_key", {"key": "KEY_PAUSE"}),
    "домой телевизор": ("tv_key", {"key": "KEY_HOME"}),
    "назад телевизор": ("tv_key", {"key": "KEY_RETURN"}),
    "меню телевизор": ("tv_key", {"key": "KEY_MENU"}),
    "источник телевизор": ("tv_key", {"key": "KEY_SOURCE"}),
    "без звука телевизор": ("tv_key", {"key": "KEY_MUTE"}),
    "вверх телевизор": ("tv_key", {"key": "KEY_UP"}),
    "ок телевизор": ("tv_key", {"key": "KEY_ENTER"}),
}


def test_every_tv_phrase_reaches_its_own_action_and_never_the_brain():
    async def run():
        results = {}
        p = prime_main.Prime()
        for name in ("tv_on", "tv_off", "tv_volume", "tv_status", "tv_youtube", "tv_key", "ask_brain"):
            def make(n):
                async def spy(**kw):
                    results.setdefault("calls", []).append((n, kw))
                    return "ok"
                return spy
            p.registry.tools[name].run = make(name)
        for phrase in TV_ROUTES:
            results["calls"] = []
            await p.handle(phrase)
            yield_phrase = phrase
            results.setdefault("by_phrase", {})[yield_phrase] = results["calls"][:]
        return results["by_phrase"]
    by_phrase = asyncio.run(run())
    bad = []
    for phrase, (tool, args) in TV_ROUTES.items():
        calls = by_phrase.get(phrase, [])
        if not calls or calls[0][0] != tool or (args and calls[0][1] != args):
            bad.append((phrase, calls))
        if any(c[0] == "ask_brain" for c in calls):
            bad.append((phrase, "reached the brain"))
    assert not bad, bad


def test_phrases_without_the_tv_are_not_tv_phrases():
    for phrase in ("открой ютуб", "включи музыку", "включи imagine dragons", "открой телеграм", "канал вверх"):
        assert not prime_main.is_tv_phrase(phrase)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
