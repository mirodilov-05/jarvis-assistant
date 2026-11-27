"""TV: universal phrasings reach the right action, and switch-on waits for the TV and reports the time.

No packet is sent and the TV is not touched: the network calls are replaced.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.tv_intents import tv_intent  # noqa: E402
from domains import tv_samsung as tv  # noqa: E402

ROUTES = {
    "громкость 30 телевизор": ("tv_volume_set", {"level": 30}),
    "громкость телевизора 20": ("tv_volume_set", {"level": 20}),
    "громкость на максимум телевизор": ("tv_volume_set", {"level": 100}),
    "громкость на ноль телевизор": ("tv_volume_set", {"level": 0}),
    "выключи телевизор через 30 минут": ("tv_off_later", {"minutes": 30}),
    "выключи телик через 2 часа": ("tv_off_later", {"minutes": 120}),
    "последний канал телевизор": ("tv_key", {"key": "KEY_PRECH"}),
    "перемотай вперёд телевизор": ("tv_key", {"key": "KEY_FF"}),
    "перемотай назад телевизор": ("tv_key", {"key": "KEY_REW"}),
    "информация телевизор": ("tv_key", {"key": "KEY_INFO"}),
    "программа передач телевизор": ("tv_key", {"key": "KEY_GUIDE"}),
    "громче телевизор": ("tv_volume", {"direction": "up"}),
    "выключи телевизор": ("tv_off", {}),
    "включи телевизор": ("tv_on", {}),
    "канал 5 телевизор": ("tv_digits", {"digits": "5"}),
    "статус телевизора": ("tv_status", {}),
}


def test_universal_phrases_route_to_their_action():
    bad = {t: (tv_intent(t), want) for t, want in ROUTES.items() if tv_intent(t) != want}
    assert not bad, bad


def test_phrase_without_the_tv_word_is_not_a_tv_command():
    assert tv_intent("громкость 30") is None


def test_wake_waits_for_the_tv_and_reports_seconds(monkeypatch=None):
    states = iter(["standby", "standby", "on"])
    sent = []

    async def fake_status(cfg):
        return {"online": True, "power": next(states), "model": ""}

    async def fake_send(cfg, keys):
        sent.append(keys)

    def fake_wol(mac, *a, **k):
        sent.append(("wol", mac))
        return "ok"

    import domains.device_hub as hub
    saved = (tv.status, tv._send, hub.wake_on_lan, tv.WAKE_WAIT_S)
    tv.status, tv._send, hub.wake_on_lan = fake_status, fake_send, fake_wol
    tv.WAKE_WAIT_S = 10.0
    try:
        cfg = {"ip": "192.0.2.10", "mac": "02:00:00:aa:bb:01", "mac_wifi": "02:00:00:aa:bb:02"}
        text = asyncio.run(tv.wake(cfg))
    finally:
        tv.status, tv._send, hub.wake_on_lan, tv.WAKE_WAIT_S = saved
    assert text.startswith("Телевизор включился за") and "по сети" in text, text
    assert ["KEY_POWER"] in sent, "the power key goes over the open link first"
    assert not [x for x in sent if isinstance(x, tuple)], "no Wake-on-LAN packet when the link answers"


def test_wake_falls_back_to_packets_when_the_link_fails():
    states = iter(["standby", "on"])
    sent = []

    async def fake_status(cfg):
        return {"online": True, "power": next(states), "model": ""}

    async def dead_link(cfg, keys):
        raise tv.TvError("нет связи")

    def fake_wol(mac, *a, **k):
        sent.append(("wol", mac))
        return "ok"

    import domains.device_hub as hub
    saved = (tv.status, tv._send, hub.wake_on_lan, tv.WAKE_WAIT_S)
    tv.status, tv._send, hub.wake_on_lan = fake_status, dead_link, fake_wol
    tv.WAKE_WAIT_S = 10.0
    try:
        cfg = {"ip": "192.0.2.10", "mac": "02:00:00:aa:bb:01", "mac_wifi": "02:00:00:aa:bb:02"}
        text = asyncio.run(tv.wake(cfg))
    finally:
        tv.status, tv._send, hub.wake_on_lan, tv.WAKE_WAIT_S = saved
    wol_macs = {x[1] for x in sent}
    assert wol_macs == {"02:00:00:aa:bb:01", "02:00:00:aa:bb:02"}, wol_macs
    assert "пакетом сети" in text, text


def test_wake_gives_up_with_a_clear_message():
    async def never_on(cfg):
        return {"online": True, "power": "standby", "model": ""}

    import domains.device_hub as hub
    saved = (tv.status, hub.wake_on_lan, tv.WAKE_WAIT_S)
    tv.status, hub.wake_on_lan, tv.WAKE_WAIT_S = never_on, (lambda *a, **k: "ok"), 1.0
    try:
        text = asyncio.run(tv.wake({"ip": "x", "mac": "02:00:00:aa:bb:01"}))
    finally:
        tv.status, hub.wake_on_lan, tv.WAKE_WAIT_S = saved
    assert "не ответил" in text and "Включение по сети" in text, text


if __name__ == "__main__":
    test_universal_phrases_route_to_their_action()
    test_phrase_without_the_tv_word_is_not_a_tv_command()
    test_wake_waits_for_the_tv_and_reports_seconds()
    test_wake_falls_back_to_packets_when_the_link_fails()
    test_wake_gives_up_with_a_clear_message()
    print("stage23: all passed")
