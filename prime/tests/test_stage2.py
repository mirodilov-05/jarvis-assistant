"""Stage 2 tests: guard levels, circuit breaker, timeouts, budget, battery. No network calls."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orchestrator import MAX_STEPS, Orchestrator, Registry, Tool  # noqa: E402
from core.router import Budget, Router, battery_saver  # noqa: E402
from core.security_guard import Guard, Level, check  # noqa: E402


async def _ok(**kw):
    return "ok"


async def _slow(**kw):
    await asyncio.sleep(5)
    return "late"


async def _boom(**kw):
    raise RuntimeError("bad")


def _registry():
    r = Registry()
    r.add(Tool("read", Level.READ_ONLY, "read", _ok))
    r.add(Tool("write", Level.SAFE_WRITE, "write", _ok))
    r.add(Tool("delete", Level.CRITICAL, "delete", _ok))
    r.add(Tool("slow", Level.READ_ONLY, "slow", _slow, timeout_s=0.1))
    r.add(Tool("boom", Level.READ_ONLY, "boom", _boom))
    return r


def _code(step):
    return step.result.split("«")[1].split("»")[0]


def test_levels():
    assert check(Level.SAFE_WRITE, Level.READ_ONLY)
    assert check(Level.SAFE_WRITE, Level.SAFE_WRITE)
    assert not check(Level.SAFE_WRITE, Level.CRITICAL)
    assert not check(Level.READ_ONLY, Level.SAFE_WRITE)


def test_critical_needs_code_and_codes_work_once():
    async def run():
        orch = Orchestrator(_registry(), Guard())
        step = await orch.run_tool("delete", path="x")
        assert step.status == "blocked"
        code = _code(step)
        assert orch.guard.confirm(code) is not None
        assert orch.guard.confirm(code) is None
    asyncio.run(run())


def test_codes_expire():
    async def run():
        orch = Orchestrator(_registry(), Guard(ttl_s=-1))
        step = await orch.run_tool("delete", path="y")
        assert orch.guard.confirm(_code(step)) is None
    asyncio.run(run())


def test_timeout_and_errors_do_not_crash():
    async def run():
        orch = Orchestrator(_registry(), Guard())
        return [(await orch.run_tool("slow")).status, (await orch.run_tool("boom")).status,
                (await orch.run_tool("nope")).status]
    assert asyncio.run(run()) == ["timeout", "error", "unknown"]


def test_circuit_breaker_stops_long_plans():
    async def run():
        orch = Orchestrator(_registry(), Guard())
        return await orch.execute_plan([("read", {})] * 20)
    steps = asyncio.run(run())
    assert len(steps) == MAX_STEPS + 1 and steps[-1].status == "limit"


def test_budget_guard_blocks_paid_calls_after_limit():
    b = Budget(limit_usd=0.01)
    assert b.allows_paid()
    b.record(2.0)
    assert not b.allows_paid()


def test_battery_saver_only_on_battery_below_30():
    assert battery_saver(20, False)
    assert not battery_saver(20, True)
    assert not battery_saver(50, False)
    assert not battery_saver(None, None)


def test_router_offline_without_key_or_ollama():
    async def run():
        r = Router("", Budget(1.0), ollama_url="http://127.0.0.1:9")
        return await r.complete("sys", "hi", need_cloud=True)
    reply, engine = asyncio.run(run())
    assert engine == "offline" and "нет связи" in reply


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
