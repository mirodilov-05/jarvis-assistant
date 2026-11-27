"""Setup-readiness tests: .env loading, the setup report, supervised restarts, ntfy when not configured."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.env import load_env, present  # noqa: E402
from config.persona import PERSONA, greeting  # noqa: E402
from core.notify import push  # noqa: E402
from core.watchdog import supervise  # noqa: E402


def test_env_file_is_loaded_and_never_overrides_real_variables():
    d = Path(tempfile.mkdtemp())
    f = d / ".env"
    f.write_text("# comment\nPRIME_TEST_A=one\nPRIME_TEST_B = \"two\"\n\nEMPTY=\n", encoding="utf-8")
    os.environ.pop("PRIME_TEST_A", None)
    os.environ["PRIME_TEST_B"] = "real"
    try:
        assert load_env(f) == 1
        assert os.environ["PRIME_TEST_A"] == "one"
        assert os.environ["PRIME_TEST_B"] == "real"            # real environment wins
        assert not present("EMPTY")
    finally:
        os.environ.pop("PRIME_TEST_A", None)
        os.environ.pop("PRIME_TEST_B", None)


def test_missing_env_file_is_fine():
    assert load_env(Path(tempfile.mkdtemp()) / "none.env") == 0


def test_supervisor_restarts_after_a_crash():
    async def run():
        calls = []

        async def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("boom")
            await asyncio.sleep(60)       # healthy from the third start on

        task = asyncio.create_task(supervise(flaky, "flaky"))
        await asyncio.sleep(4.5)          # 1 s + 2 s pauses between the first crashes
        task.cancel()
        return len(calls)
    assert asyncio.run(run()) >= 3


def test_notify_is_silent_without_topic():
    os.environ.pop("PRIME_NTFY_TOPIC", None)
    assert asyncio.run(push("тест")) is False


def test_persona_greetings():
    assert greeting("ru").endswith(PERSONA.honorific_ru + ".")
    assert greeting("en").startswith("Yes")
    assert "はい" in greeting("ja")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
