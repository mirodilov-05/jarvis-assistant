"""Remote-control phrases: channel, pause, back, mute, arrows, and that a TV phrase never falls back to music."""
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


def test_key_phrases_map_to_remote_keys():
    k = prime_main.tv_key_for
    assert k("канал вверх телевизор") == "KEY_CHUP"
    assert k("следующий канал телевизор") == "KEY_CHUP"
    assert k("канал вниз телевизор") == "KEY_CHDOWN"
    assert k("пауза телевизор") == "KEY_PAUSE"
    assert k("домой телевизор") == "KEY_HOME"
    assert k("назад телевизор") == "KEY_RETURN"
    assert k("без звука телевизор") == "KEY_MUTE"
    assert k("вверх телевизор") == "KEY_UP"


def test_no_key_without_the_tv_word():
    assert prime_main.tv_key_for("канал вверх") is None
    assert prime_main.tv_key_for("открой ютуб") is None


def test_tv_phrases_never_fall_back_to_the_brain():
    async def run():
        p = prime_main.Prime()
        seen = []
        for name in ("tv_on", "tv_off", "tv_volume", "tv_status", "tv_youtube", "tv_key", "ask_brain"):
            tool = p.registry.tools[name]

            async def spy(_name=name, **kw):
                seen.append((_name, kw.get("key", "")))
                return "ok"
            tool.run = spy
        for phrase in ("включи телик", "выключи телевизор", "канал вверх телевизор", "пауза телевизор", "статус телевизора"):
            await p.handle(phrase)
        return seen
    seen = asyncio.run(run())
    assert ("ask_brain", "") not in seen
    assert ("tv_key", "KEY_CHUP") in seen and ("tv_key", "KEY_PAUSE") in seen


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
