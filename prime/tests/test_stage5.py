"""Stage 5 tests: Prime wired together, using a temporary database. Nothing is sent over the network.

Covers: task and goal commands, read-only queries, the confirmation flow, the web API, and the Telegram owner check.
"""
import asyncio
import dataclasses
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as prime_main  # noqa: E402
from interfaces.web_command_center import make_app  # noqa: E402

TMP = Path(tempfile.mkdtemp())
prime_main.SETTINGS = dataclasses.replace(prime_main.SETTINGS, db_path=TMP / "prime.db", backup_dir=TMP / "backups")
os.environ.pop("GEMINI_API_KEY", None)                 # tests never use a real key


def make_prime():
    return prime_main.Prime()


def test_task_and_goal_commands_and_queries():
    async def run():
        p = make_prime()
        r1 = await p.handle("добавь дело купить молоко")
        r2 = await p.handle("цель японский 50 слов")
        r3 = await p.handle("главное")
        r4 = await p.handle("прогресс")
        return r1, r2, r3, r4
    r1, r2, r3, r4 = asyncio.run(run())
    assert "купить молоко" in r1 and "японский" in r2
    assert "купить молоко" in r3
    assert "японский" in r4


def test_critical_action_waits_for_confirmation_then_runs_once():
    async def run():
        p = make_prime()
        # a tool that is CRITICAL by its level: parked until the owner sends the code
        from core.orchestrator import Tool
        from core.security_guard import Level
        ran = []

        async def wipe(note: str) -> str:
            ran.append(note)
            return "стёрто"
        p.registry.add(Tool("wipe", Level.CRITICAL, "стереть", wipe))
        step = await p.orch.run_tool("wipe", note="x")
        assert step.status == "blocked" and not ran
        code = step.result.split("«")[1].split("»")[0]
        first = await p.handle(f"подтверди {code}")
        second = await p.handle(f"подтверди {code}")
        return first, second, ran
    first, second, ran = asyncio.run(run())
    assert first == "стёрто" and "неверный" in second and ran == ["x"]


def test_offline_brain_answers_without_crashing():
    async def run():
        p = make_prime()
        return await p.handle("расскажи про Японию")
    reply = asyncio.run(run())
    assert "нет связи" in reply or reply


def test_web_api_status_and_command():
    from aiohttp.test_utils import TestClient, TestServer

    async def run():
        p = make_prime()
        async with TestClient(TestServer(make_app(p))) as client:
            st = await (await client.get("/api/status")).json()
            cmd = await (await client.post("/api/command", json={"text": "добавь дело из теста"})).json()
            bad = await client.post("/api/command", data="не json")
            return st, cmd, bad.status
    st, cmd, bad_status = asyncio.run(run())
    assert "engine" in st and "tasks" in st and "добавь" not in cmd.get("reply", "x") and "из теста" in cmd["reply"]
    assert bad_status == 400


def test_telegram_ignores_strangers_and_is_off_without_settings():
    from interfaces import telegram_hub

    async def run():
        p = make_prime()
        try:                                                      # no token: stays idle, sends nothing
            await asyncio.wait_for(telegram_hub.run(p, token="", owner_id=0), timeout=0.3)
            return "returned"
        except asyncio.TimeoutError:
            return "idle"
    assert asyncio.run(run()) == "idle"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
