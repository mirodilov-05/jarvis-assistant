"""Stage 1 tests. Run: python -m pytest tests -q  (or python tests/test_stage1.py)."""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.event_bus import EventBus, _match  # noqa: E402
from core.memory_core import Memory  # noqa: E402
from core.watchdog import preflight  # noqa: E402


def test_topic_matching():
    assert _match("*", "anything")
    assert _match("task.*", "task.done")
    assert not _match("task.*", "timer.done")
    assert _match("timer.fired", "timer.fired")


def test_bus_delivers_and_survives_a_broken_handler():
    async def run():
        bus = EventBus()
        got = []

        async def broken(ev):
            raise RuntimeError("boom")

        async def good(ev):
            got.append(ev.payload["n"])

        bus.subscribe("task.*", broken)
        bus.subscribe("task.*", good)
        bus.start()
        await bus.publish("task.done", n=1)
        await bus.publish("task.done", n=2)
        await asyncio.sleep(0.1)
        await bus.stop()
        return got
    assert asyncio.run(run()) == [1, 2]


def test_memory_roundtrip_and_backup():
    async def run():
        d = Path(tempfile.mkdtemp())
        mem = Memory(d / "prime.db")
        tid = await mem.add_task("проверить слух", due="2026-11-30T10:00")
        gid = await mem.add_goal("японский 50 слов в день")
        await mem.set_progress(gid, 1.7)          # clamped to 1.0
        await mem.log_turn("user", "привет")
        tasks = await mem.open_tasks()
        goals = await mem.goals()
        ok = await mem.integrity_ok()
        path = await mem.backup(d / "backups")
        mem.close()
        return tid, tasks, goals, ok, path.exists()
    tid, tasks, goals, ok, backed = asyncio.run(run())
    assert tasks[0]["text"] == "проверить слух" and tid > 0
    assert goals[0]["progress"] == 1.0
    assert ok and backed


def test_preflight_reports_each_folder():
    d = Path(tempfile.mkdtemp())
    checks = preflight(d)
    assert any(c.name == "python" for c in checks)
    assert all(c.ok for c in checks if c.name.startswith("folder"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
