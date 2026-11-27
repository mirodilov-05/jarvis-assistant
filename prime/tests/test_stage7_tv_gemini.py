"""TV control and Gemini brain tests. No real device or network: the TV is simulated, the key is never used."""
import asyncio
import base64
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.router import Budget, Router, gemini_key  # noqa: E402
from domains import tv_samsung as tv  # noqa: E402

CFG = {"ip": "192.0.2.10", "mac": "02:00:00:aa:bb:01"}


def test_tv_without_ip_is_a_clear_error():
    async def run():
        try:
            await tv.status({"ip": ""})
        except tv.TvError as e:
            return str(e)
    assert "не настроен" in asyncio.run(run())


def test_tv_status_reports_offline_without_raising():
    async def run():
        return await tv.status({"ip": "127.0.0.1"})          # nothing listens on 8001 there
    st = asyncio.run(run())
    assert st["online"] is False


def test_token_is_saved_and_reused_in_a_private_file():
    d = Path(tempfile.mkdtemp())
    with mock.patch.object(tv, "TOKEN_FILE", d / "tv_token.txt"):
        assert tv._load_token() == ""
        tv._save_token("123456")
        assert tv._load_token() == "123456"


def test_remote_name_is_base64_of_client_name():
    assert base64.b64decode(tv.CLIENT_NAME).decode() == "JarvisPrime"


def test_wake_refuses_without_mac():
    async def run():
        async def no_link(*_a):              # never touch the real TV from a test
            raise tv.TvError("нет связи")
        with mock.patch.object(tv, "_send", no_link):
            try:
                await tv.wake({"ip": "127.0.0.1", "mac": ""})
            except tv.TvError as e:
                return str(e)
    assert "MAC" in asyncio.run(run())


def test_gemini_key_comes_from_environment_first():
    with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        assert gemini_key() == "test-key"


def test_router_falls_back_when_no_gemini_key():
    async def run():
        r = Router("", Budget(1.0), ollama_url="http://127.0.0.1:9")
        return await r.complete("sys", "привет", need_cloud=True)
    reply, engine = asyncio.run(run())
    assert engine == "offline"


def test_router_uses_gemini_for_hard_tasks_when_allowed():
    r = Router("k", Budget(1.0), ollama_url="http://127.0.0.1:9")
    assert r.pick(need_cloud=True) == "gemini"
    r.saver = True                                           # battery saver: no cloud calls
    assert r.pick(need_cloud=True) != "gemini"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
