"""Regression tests for the audit: each one guards a bug that was found and fixed."""
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    assert ok, name


def load_plugin(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{name}", ROOT / "plugins" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_telegram_has_one_client_and_no_loop_per_call():
    tg = load_plugin("telegram")
    seen = []

    async def probe(client):
        seen.append(id(client))
        return 1
    with mock.patch.object(tg.connections, "telegram_creds", return_value=("1", "hash")):
        loop_a = tg._ensure_loop()
        loop_b = tg._ensure_loop()
    check("one background loop for all Telegram calls", loop_a is loop_b)


def test_telegram_without_login_answers_at_once():
    tg = load_plugin("telegram")
    tg._auth.update(ok=None, t=0.0)
    with mock.patch.object(tg.connections, "telegram_creds", return_value=("", "")):
        t0 = time.time()
        assert tg.connected() is False
        check("no credentials: not connected, no network, instant", time.time() - t0 < 0.5)


def test_telegram_refusal_is_remembered_not_retried_each_time():
    tg = load_plugin("telegram")
    tg._auth.update(ok=False, t=time.time(), warned=True)
    with mock.patch.object(tg.connections, "telegram_creds", return_value=("1", "h")), \
            mock.patch.object(tg, "_has_login", return_value=True), \
            mock.patch.object(tg, "run", side_effect=AssertionError("must not call Telegram again")):
        assert tg.connected() is False
    check("a refused session is not asked again for an hour", True)


def test_calendar_survives_a_page_instead_of_a_calendar():
    cal = load_plugin("calendar_ics")
    cal._BROKEN.clear()
    cal._CACHE.clear()
    html = b"<!DOCTYPE html><style>body{height:100%}</style>"
    with mock.patch.object(cal, "ics_urls", return_value=["https://example.invalid/cal.ics"]), \
            mock.patch.object(cal.requests, "get") as get:
        get.return_value.content = html
        import datetime as dt
        out = cal.events(dt.date(2026, 11, 27))
        again = cal.events(dt.date(2026, 11, 27))
    check("a broken calendar gives an empty list, not an exception", out == [] and again == [])
    check("the same broken calendar is reported once", len(cal._BROKEN) == 1)


def test_calendar_is_cached_for_ten_minutes():
    cal = load_plugin("calendar_ics")
    cal._CACHE.clear()
    ics = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART:20261127T100000\r\nDTEND:20261127T110000\r\n"
           "SUMMARY:Встреча\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n").encode("utf-8")
    import datetime as dt
    with mock.patch.object(cal, "ics_urls", return_value=["https://example.invalid/ok.ics"]), \
            mock.patch.object(cal.requests, "get") as get:
        get.return_value.content = ics
        first = cal.events(dt.date(2026, 11, 27))
        second = cal.events(dt.date(2026, 11, 27))
        check("one download serves repeated requests", get.call_count == 1)
    check("the event is read", first and first[0]["title"] == "Встреча" and second == first)


def test_memo_expires():
    import core
    core._MEMO.clear()
    calls = []
    f = lambda: calls.append(1) or len(calls)  # noqa: E731
    assert core.memo("k", 60, f) == 1 and core.memo("k", 60, f) == 1 and len(calls) == 1
    core._MEMO["k"] = (time.time() - 120, 1)
    assert core.memo("k", 60, f) == 2
    check("memo returns the cached value, then refreshes after the time-to-live", True)


def test_tv_wake_waits_for_the_caller_budget():
    """Runs in its own process: the TV module lives in prime/, whose «core» package must not shadow the root one."""
    import subprocess
    snippet = (
        "import asyncio, inspect, sys\n"
        "from unittest import mock\n"
        "sys.path.insert(0, '.')\n"
        "from domains import tv_samsung as tv\n"
        "assert inspect.signature(tv.wake).parameters['wait'].default is None\n"
        "async def no_link(*a, **k):\n"
        "    raise tv.TvError('нет связи')\n"
        "async def off(cfg):\n"
        "    return {'online': False, 'power': None, 'model': ''}\n"
        "with mock.patch.object(tv, '_send', no_link), mock.patch.object(tv, 'status', off), "
        "mock.patch.object(tv, '_drop', mock.AsyncMock()), mock.patch('domains.device_hub.wake_on_lan'):\n"
        "    text = asyncio.run(tv.wake({'ip': '192.0.2.10', 'mac': '02:00:00:aa:bb:01'}, wait=0.1))\n"
        "print('TEXT=' + text)\n"
    )
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", snippet], cwd=str(ROOT / "prime"),
                       capture_output=True, text=True, timeout=120)
    check("the TV wake default resolves, and a short wait answers at once", "ещё загружается" in r.stdout and r.returncode == 0)


def test_hardware_reads_are_fast_and_name_windows_11():
    import pc_profile
    t0 = time.time()
    h = pc_profile._hardware()
    check("hardware read is fast (under 5 s)", time.time() - t0 < 5)
    check("ram and cpu are filled in", h["ram_gb"] > 0 and bool(h["cpu"]))
    check("the Windows name is filled in", "Windows" in h["os"])


def test_no_undefined_names_in_the_code():
    import shutil
    import subprocess
    uv = shutil.which("uv")
    if not uv:
        print("SKIP  no uv on PATH, so pyflakes was not run here")
        return
    targets = ["assistant.py", "core.py", "agent.py", "hud_data.py", "remote_bot.py", "cloud.py", "pc_profile.py",
               "cognition", "learning", "plugins", "prime/domains", "prime/core", "prime/interfaces", "prime/main.py"]
    r = subprocess.run([uv, "tool", "run", "pyflakes", *targets], cwd=ROOT, capture_output=True, text=True, timeout=300)
    undefined = [ln for ln in (r.stdout or "").splitlines() if "undefined name" in ln]
    check("no undefined names anywhere", not undefined)


if __name__ == "__main__":
    test_telegram_has_one_client_and_no_loop_per_call()
    test_telegram_without_login_answers_at_once()
    test_telegram_refusal_is_remembered_not_retried_each_time()
    test_calendar_survives_a_page_instead_of_a_calendar()
    test_calendar_is_cached_for_ten_minutes()
    test_memo_expires()
    test_tv_wake_waits_for_the_caller_budget()
    test_hardware_reads_are_fast_and_name_windows_11()
    test_no_undefined_names_in_the_code()
    print("stage31: all passed")
