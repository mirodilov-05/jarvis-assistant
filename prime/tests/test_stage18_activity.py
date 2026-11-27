"""Activity memory: minutes per program are summed from stretches, private programs are never stored,
and the voice phrases reach their own skills. Uses a temporary database; nothing real is recorded here.
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import activity  # noqa: E402
import core  # noqa: E402
from core import normalize  # noqa: E402

core.load_plugins()
CATCH_ALL = {"music.choice", "macros.run"}


def use_temp_db():
    base = Path(tempfile.mkdtemp())
    activity.DB = base / "activity.db"
    activity.SETTINGS = base / "activity_settings.json"


def test_minutes_are_summed_per_program():
    use_temp_db()
    now = dt.datetime.now()
    start = now - dt.timedelta(hours=2)
    activity._write(start.timestamp(), (start + dt.timedelta(minutes=30)).timestamp(), "code.exe")
    activity._write((start + dt.timedelta(minutes=30)).timestamp(), (start + dt.timedelta(minutes=50)).timestamp(), "chrome.exe")
    activity._write((start + dt.timedelta(minutes=50)).timestamp(), (start + dt.timedelta(minutes=50, seconds=0.5)).timestamp(), "x.exe")  # half a second: skipped
    rows = dict(activity.minutes_by_app(start - dt.timedelta(minutes=1)))
    assert round(rows["code.exe"]) == 30, rows
    assert round(rows["chrome.exe"]) == 20, rows
    assert "x.exe" not in rows, rows


def test_forget_removes_everything():
    use_temp_db()
    activity._write(1000.0, 2000.0, "code.exe")
    assert activity.DB.exists()
    activity.forget()
    assert not activity.DB.exists()


def test_enabled_flag_round_trip():
    use_temp_db()
    assert activity.enabled() is False
    activity.set_enabled(True)
    assert activity.enabled() is True
    activity.set_enabled(False)
    assert activity.enabled() is False


def test_private_apps_are_listed_as_never_recorded():
    for name in ["keepass.exe", "1password.exe", "bitwarden.exe"]:
        assert name in activity.PRIVATE_APPS, name


ROUTES = {
    "что я сегодня делал": "activity.summary",
    "сколько времени я сегодня провёл за компьютером": "activity.summary",
    "включи запоминание активности": "activity.on",
    "выключи запоминание активности": "activity.off",
    "забудь мою активность": "activity.forget",
}


def first_match(text):
    norm = normalize(text, "ru")
    for sk in core.SKILLS:
        if sk.name in CATCH_ALL:
            continue
        if any(p.search(norm) for p in sk.patterns.get("ru", [])):
            return sk.name
    return None


def test_voice_routes():
    for text, expected in ROUTES.items():
        assert first_match(text) == expected, (text, first_match(text), expected)


if __name__ == "__main__":
    test_minutes_are_summed_per_program()
    test_forget_removes_everything()
    test_enabled_flag_round_trip()
    test_private_apps_are_listed_as_never_recorded()
    test_voice_routes()
    print("stage18: all passed")
