"""Chat and voice bridge tests: punctuation and name removal, history order, TV phrases in prime."""
import asyncio
import dataclasses
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as prime_main  # noqa: E402
from core.memory_core import Memory  # noqa: E402

TMP = Path(tempfile.mkdtemp())
prime_main.SETTINGS = dataclasses.replace(prime_main.SETTINGS, db_path=TMP / "prime.db", backup_dir=TMP / "backups")
os.environ.pop("GEMINI_API_KEY", None)


def test_name_and_punctuation_are_removed():
    n = prime_main.normalize_command
    assert n("Эй, Джарвис, включи телевизор!") == "включи телевизор"
    assert n("Джарвис, громче телевизор.") == "громче телевизор"
    assert n("Статус телевизора?") == "статус телевизора"


def test_tv_phrases_reach_the_tv_tools():
    async def run():
        p = prime_main.Prime()
        seen = []
        for name in ("tv_on", "tv_off", "tv_volume", "tv_status", "tv_youtube"):
            tool = p.registry.tools[name]
            real = tool.run

            async def spy(_real=real, _name=name, **kw):
                seen.append(_name)
                return "ok"
            tool.run = spy
        await p.handle("Эй, Джарвис, включи телевизор!")
        await p.handle("громче телевизор")
        await p.handle("статус телевизора?")
        return seen
    seen = asyncio.run(run())
    assert seen == ["tv_on", "tv_volume", "tv_status"]


def test_history_keeps_order_and_limit():
    async def run():
        m = Memory(TMP / "h.db")
        for i in range(5):
            await m.log_turn("user" if i % 2 == 0 else "jarvis", f"msg {i}")
        turns = await m.recent_turns(3)
        m.close()
        return [t["text"] for t in turns]
    assert asyncio.run(run()) == ["msg 2", "msg 3", "msg 4"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
