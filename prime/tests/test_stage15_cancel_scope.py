"""«Отмени таймер» removes only timers; «отмени напоминание» only reminders; «отмени все» both."""
import sys
import tempfile
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import core  # noqa: E402

_state: dict = {}


def _reminders():
    if "mod" not in _state:
        t = Path(tempfile.mkdtemp())
        core.DATA, core.SETTINGS_FILE, core.PROFILES_FILE = t, t / "s.json", t / "p.json"
        core._profile_cache.clear()
        (t / "log").mkdir()
        (t / "dictations").mkdir()
        core.load_config()
        core.load_plugins()
        mod = sys.modules["jarvis_plugin_reminders"]
        mod.FILE = t / "reminders.json"
        _state["mod"] = mod
    return _state["mod"]


def _run(text: str, items: list[dict]) -> list[dict]:
    mod = _reminders()
    core.save_json(mod.FILE, items)
    norm = core.normalize(text, "ru")
    ctx = core.Ctx(text=text, lang="ru", source="тест", config=core.CONFIG, match=None, norm=norm)
    mod.cancel(ctx)
    return core.load_json(mod.FILE, [])


ITEMS = [
    {"at": "2030-01-01T10:00:00", "text": "позвонить маме", "lang": "ru", "kind": "remind"},
    {"at": "2030-01-01T10:05:00", "text": "таймер чая", "lang": "ru", "kind": "timer"},
]


def test_timer_cancel_keeps_reminders():
    left = _run("отмени таймер", list(ITEMS))
    assert [r["kind"] for r in left] == ["remind"]


def test_reminder_cancel_keeps_timers():
    left = _run("отмени напоминание", list(ITEMS))
    assert [r["kind"] for r in left] == ["timer"]


def test_cancel_all_removes_both():
    assert _run("отмени все напоминания и таймеры", list(ITEMS)) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
