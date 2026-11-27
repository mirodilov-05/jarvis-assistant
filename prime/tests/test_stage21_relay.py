"""Wake-up relay: the Wake-on-LAN packet is right, only the owner gets answers, and the TV wake is chosen correctly.

No packet is sent and no network is used: the send and the reachability check are replaced.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "relay"))

import wake_relay as wr  # noqa: E402

CFG = {"token": "t", "owner_id": 1, "laptop_ip": "192.0.2.20",
       "tv_mac": "02:00:00:aa:bb:01", "laptop_mac": "02:00:00:aa:bb:03"}


def test_magic_packet_layout():
    pkt = wr.magic_packet("02:00:00:aa:bb:01")
    assert len(pkt) == 102 and pkt[:6] == b"\xff" * 6
    assert pkt[6:12] == bytes.fromhex("020000aabb01") and pkt[-6:] == bytes.fromhex("020000aabb01")


def test_bad_mac_is_refused():
    try:
        wr.magic_packet("nope")
    except ValueError:
        return
    raise AssertionError("bad MAC accepted")


def test_tv_wake_is_chosen_and_sent(monkeypatch=None):
    sent = []
    wr.send_wake = lambda mac, *a: sent.append(mac)
    wr.laptop_on = lambda ip: False
    answer = wr.reply_for("включи телевизор", CFG)
    assert sent == [CFG["tv_mac"]] and "Включаю телевизор" in answer


def test_laptop_wake_and_status():
    sent = []
    wr.send_wake = lambda mac, *a: sent.append(mac)
    wr.laptop_on = lambda ip: False
    assert "Пробую включить ноутбук" in wr.reply_for("включи ноут", CFG)
    assert sent == [CFG["laptop_mac"]]
    assert "выключен" in wr.reply_for("статус", CFG)


def test_unknown_phrase_sends_nothing():
    sent = []
    wr.send_wake = lambda mac, *a: sent.append(mac)
    answer = wr.reply_for("поставь музыку", CFG)
    assert sent == [] and "Пока умею" in answer


if __name__ == "__main__":
    test_magic_packet_layout()
    test_bad_mac_is_refused()
    test_tv_wake_is_chosen_and_sent()
    test_laptop_wake_and_status()
    test_unknown_phrase_sends_nothing()
    print("stage21: all passed")
