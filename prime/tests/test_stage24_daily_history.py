"""Daily open commands and the fixes from the command history.

Nothing is opened: os.startfile and subprocess are replaced by lists, and the music search is replaced.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import os  # noqa: E402
import subprocess  # noqa: E402

import core  # noqa: E402
from core import Ctx, normalize  # noqa: E402

core.load_plugins()


def _skill(name):
    return next(s for s in core.SKILLS if s.name == name)


def _run(name, text):
    sk = _skill(name)
    norm = normalize(text, "ru")
    for p in sk.patterns["ru"]:
        m = p.search(norm)
        if m:
            return sk.handler(Ctx(text=text, lang="ru", source="тест", config=core.CONFIG, match=m, norm=norm))
    return "NO MATCH"


def test_known_sites_and_settings_open_and_unknown_passes(monkeypatch=None):
    opened, popened = [], []
    saved = (os.startfile, subprocess.Popen)
    os.startfile = lambda t: opened.append(t)
    subprocess.Popen = lambda cmd, **k: popened.append(cmd)
    try:
        assert _run("daily.open", "открой озон") is not None
        assert _run("daily.open", "открой настройки wifi") is not None
        assert _run("daily.open", "открой диспетчер устройств") is not None
        assert _run("daily.open", "открой ютуб") in (None, "NO MATCH")   # not ours: apps.open handles it
        assert _run("daily.open", "открой настройки") in (None, "NO MATCH")   # Jarvis's own settings
    finally:
        os.startfile, subprocess.Popen = saved
    assert "https://www.ozon.ru" in opened and "ms-settings:network-wifi" in opened, opened
    assert "devmgmt.msc" in popened, popened


def test_video_choice_is_not_a_song(monkeypatch=None):
    # «запусти первое видео в YouTube» must not become a music search: the music skill passes it on
    assert _run("music.youtube", "запусти первое видео в YouTube") is None


def test_generic_music_request_plays_something_popular(monkeypatch=None):
    glob = _skill("music.youtube").handler.__globals__      # the module the skill really runs in
    asked = []
    saved = glob["play"]
    glob["play"] = lambda q, service=None: asked.append(q) or "ok"
    try:
        _run("music.youtube", "поставь музыку какой-нибудь в ютубе")
    finally:
        glob["play"] = saved
    assert asked == ["лучшие песни"], asked


def test_tv_music_means_youtube():
    sys.path.insert(0, str(ROOT / "prime"))
    from domains import tv_samsung as tv
    assert tv.resolve_app("музыку") == ("youtube", "111299001912")


if __name__ == "__main__":
    test_known_sites_and_settings_open_and_unknown_passes()
    test_video_choice_is_not_a_song()
    test_generic_music_request_plays_something_popular()
    test_tv_music_means_youtube()
    print("stage24: all passed")
