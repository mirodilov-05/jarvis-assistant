"""Stage 3 tests: goals cascade, Rule of 3, rebalancing, inbox sorting, SM-2, search, devices (no network)."""
import asyncio
import datetime as dt
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domains import device_hub as dh  # noqa: E402
from domains.life_flow import morning_brief, rebalance, rollup, rule_of_three, sort_inbox  # noqa: E402
from domains.second_brain import search, sm2  # noqa: E402


def test_cascade_rolls_up_to_the_year():
    goals = [
        {"id": 1, "parent_id": None, "progress": 0.0},
        {"id": 2, "parent_id": 1, "progress": 0.5},
        {"id": 3, "parent_id": 1, "progress": 1.0},
        {"id": 4, "parent_id": 2, "progress": 0.0},
    ]
    r = rollup(goals)
    assert r[2] == 0.0 and r[3] == 1.0 and round(r[1], 3) == 0.5


def test_rule_of_three_picks_overdue_first_and_caps_at_three():
    tasks = [{"id": i, "text": f"t{i}", "due": f"2026-11-{20 + i:02d}T10:00", "done": False} for i in range(1, 6)]
    tasks.append({"id": 9, "text": "old", "due": "2026-11-01T09:00", "done": False})
    focus = rule_of_three(tasks, "2026-11-25")
    assert len(focus) == 3 and focus[0]["text"] == "old"


def test_rebalance_moves_overdue_to_today():
    tasks = [{"text": "late", "due": "2026-11-20T10:00", "done": False}, {"text": "done", "due": "2026-11-20T10:00", "done": True}]
    moved = rebalance(tasks, "2026-11-25")
    assert len(moved) == 1 and tasks[0]["due"].startswith("2026-11-25") and tasks[1]["due"].startswith("2026-11-20")


def test_morning_brief_is_short_and_in_order():
    text = morning_brief("Мирод", [{"text": "отчёт"}], [("японский", 0.4)], "Ясно, +12.")
    assert text.startswith("Доброе утро, Мирод.") and "отчёт" in text and "40%" in text


def test_inbox_sorting_never_overwrites():
    base = Path(tempfile.mkdtemp())
    inbox = base / "00_Inbox"
    inbox.mkdir()
    (inbox / "a.pdf").write_text("1")
    (inbox / "b.png").write_text("2")
    dest = base / "out"
    (dest / "Документы").mkdir(parents=True)
    (dest / "Документы" / "a.pdf").write_text("old")          # name clash
    moved = sort_inbox(inbox, dest)
    assert ("a.pdf", "Документы") in moved and ("b.png", "Изображения") in moved
    assert (dest / "Документы" / "a (1).pdf").exists()
    assert (dest / "Документы" / "a.pdf").read_text() == "old"


def test_sm2_intervals_grow_and_failure_resets():
    today = dt.date(2026, 11, 25)
    r1 = sm2(2.5, 0, 5, today)
    r2 = sm2(r1.ease, r1.interval, 5, today)
    assert r1.interval == 1 and r2.interval == 6
    r3 = sm2(r2.ease, r2.interval, 5, today)
    assert r3.interval > 6
    fail = sm2(r3.ease, r3.interval, 1, today)
    assert fail.interval == 1 and fail.ease == r3.ease
    assert sm2(1.3, 6, 3, today).ease >= 1.3


def test_search_finds_by_word_prefix():
    notes = [{"text": "Встреча с Юлей в пятницу"}, {"text": "список покупок молоко"}]
    assert search("юля встреча", notes)[0]["text"].startswith("Встреча")
    assert search("ab", notes) == []


def test_wake_on_lan_packet_format():
    p = dh.magic_packet("AA:BB:CC:DD:EE:FF")
    assert len(p) == 102 and p[:6] == b"\xff" * 6 and p[6:12] == bytes.fromhex("aabbccddeeff")
    try:
        dh.magic_packet("nope")
        raise AssertionError("bad MAC accepted")
    except ValueError:
        pass


def test_unconfigured_devices_say_so_and_send_nothing():
    async def run():
        return (await dh.tv_status({}), await dh.tv_power_on({}), await dh.bluetooth_audio(""),
                await dh.ha_call("", "", "light.turn_on", "light.x"))
    msgs = asyncio.run(run())
    assert all("не настроен" in m or "не настроен" in m.lower() or "не настроен" in m for m in msgs[:2] + msgs[2:3] + msgs[3:4])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
