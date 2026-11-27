"""Apps everywhere: TV apps by name, and the PC catalog that includes programs without a shortcut.

Nothing is launched: the TV is not called, and no program is started.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "prime"))

from core.tv_intents import tv_intent  # noqa: E402
from domains import tv_samsung as tv  # noqa: E402


def test_tv_app_names_resolve_to_ids():
    assert tv.resolve_app("нетфликс") == ("netflix", "3201907018807")
    assert tv.resolve_app("прайм видео") == ("prime video", "3201910019365")
    assert tv.resolve_app("спотифай") == ("spotify", "3201606009684")
    assert tv.resolve_app("ютуб") == ("youtube", "111299001912")
    assert tv.resolve_app("дота") is None


def test_tv_phrases_pick_the_right_tool():
    assert tv_intent("запусти netflix в телевизоре") == ("tv_app", {"name": "netflix"})
    assert tv_intent("открой спотифай на телике") == ("tv_app", {"name": "спотифай"})
    assert tv_intent("запусти ютуб в телеизоре") == ("tv_youtube", {})          # YouTube keeps its own tool
    assert tv_intent("включи телевизор") == ("tv_on", {})
    assert tv_intent("запусти первое видео") is None                              # not a TV phrase at all


def test_unknown_tv_app_is_said_not_guessed():
    import asyncio
    text = asyncio.run(tv.open_app({}, "дота"))
    assert "не знаю приложение" in text and "netflix" in text, text


if __name__ == "__main__":
    test_tv_app_names_resolve_to_ids()
    test_tv_phrases_pick_the_right_tool()
    test_unknown_tv_app_is_said_not_guessed()
    print("stage19: all passed")
