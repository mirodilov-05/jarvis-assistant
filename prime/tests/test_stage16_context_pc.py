"""Memory of the last search («запусти первое видео»), the YouTube list, and the PC profile summary.

Nothing is opened and nothing is sent: the browser opener is replaced by a list, and YouTube is not called.
"""
import sys
from pathlib import Path

ASSISTANT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ASSISTANT))

import core  # noqa: E402
from core import Ctx, normalize  # noqa: E402

core.load_plugins()
CATCH_ALL = {"music.choice", "macros.run"}
ROUTES = {
    "запусти первое видео": "apps.result_open",
    "открой второе видео": "apps.result_open",
    "запусти последнее видео": "apps.result_open",
    "запусти видео номер 3": "apps.result_open",
    "найди на ютубе рецепт плова": "apps.youtube",
    "запусти первое видео на телевизоре": "tv.media",
    "поставь песню believer в ютуб": "music.youtube",
    "что ты знаешь о моём компьютере": "pc.about",
    "изучи мой компьютер": "pc.scan",
}


def first_match(text):
    norm = normalize(text, "ru")
    for sk in core.SKILLS:
        if sk.name in CATCH_ALL:
            continue
        if any(p.search(norm) for p in sk.patterns.get("ru", [])):
            return sk.name
    return None


def test_routes():
    for text, expected in ROUTES.items():
        assert first_match(text) == expected, (text, first_match(text), expected)


def _run_result_open(text):
    norm = normalize(text, "ru")
    sk = next(s for s in core.SKILLS if s.name == "apps.result_open")
    for p in sk.patterns["ru"]:
        m = p.search(norm)
        if m:
            return sk.handler(Ctx(text=text, lang="ru", source="test", config={}, match=m, norm=norm))
    return None


def test_first_second_last_pick_the_right_video(monkeypatch=None):
    from plugins import apps
    opened = []
    apps.os.startfile = lambda url: opened.append(url)
    items = [{"id": "AAAAAAAAAAA", "title": "first"}, {"id": "BBBBBBBBBBB", "title": "second"},
             {"id": "CCCCCCCCCCC", "title": "third"}, {"id": "DDDDDDDDDDD", "title": "fourth"}]
    core.set_results("youtube", items)
    _run_result_open("запусти первое видео")
    _run_result_open("открой второе видео")
    _run_result_open("запусти последнее видео")
    _run_result_open("запусти видео номер 3")
    assert opened == [
        "https://www.youtube.com/watch?v=AAAAAAAAAAA&autoplay=1",
        "https://www.youtube.com/watch?v=BBBBBBBBBBB&autoplay=1",
        "https://www.youtube.com/watch?v=DDDDDDDDDDD&autoplay=1",
        "https://www.youtube.com/watch?v=CCCCCCCCCCC&autoplay=1",
    ], opened


def test_no_search_yet_says_so_and_bare_song_passes():
    core.set_results("youtube", [])
    assert "Сначала скажите" in _run_result_open("запусти первое видео")
    assert _run_result_open("включи песню") is None      # let the music skills handle a bare «песню»


def test_youtube_list_parses_the_results_page(monkeypatch=None):
    from plugins import apps
    html = ('{"videoRenderer":{"videoId":"QX-THYs8ZMk","thumbnail":{}, "title":{"runs":[{"text":"ПЛОВ. Как приготовить"}]}},'
            '"videoRenderer":{"videoId":"QX-THYs8ZMk","title":{"runs":[{"text":"дубль"}]}},'
            '"videoRenderer":{"videoId":"m00M_psAKoM","title":{"runs":[{"text":"ПЛОВ. ПОШАГОВЫЙ"}]}}}')

    class Resp:
        text = html

    import requests
    original = requests.get
    requests.get = lambda *a, **k: Resp()
    try:
        items = apps.youtube_list("плов", n=5)
    finally:
        requests.get = original
    assert [i["id"] for i in items] == ["QX-THYs8ZMk", "m00M_psAKoM"], items
    assert items[0]["title"] == "ПЛОВ. Как приготовить"


def test_pc_summary_from_a_profile(tmp_path=None):
    import json
    import pc_profile
    original = pc_profile.PROFILE
    tmp = Path(tempfile_dir()) / "pc_profile_test.json"
    tmp.write_text(json.dumps({"scanned_at": "2026-11-25T20:00:00", "browser": "Microsoft Edge",
                               "hardware": {"os": "Windows 11", "cpu": "i5", "ram_gb": 24, "gpu": "RTX"},
                               "folders": {"Downloads": 6, "_documents_folders": ["x"]},
                               "installed": ["Git", "Discord"], "apps": []}), encoding="utf-8")
    pc_profile.PROFILE = tmp
    try:
        text = pc_profile.summary()
    finally:
        pc_profile.PROFILE = original
    assert "ОЗУ 24" in text and "Microsoft Edge" in text and "Discord" in text and "Downloads (6)" in text
    assert "_documents_folders" not in text


def tempfile_dir():
    import tempfile
    return tempfile.gettempdir()


def test_long_phrases_reach_the_pc_skills():
    # a phrase of more than five words only reaches the skills listed in core._LONG_OK
    for name in ["pc.about", "pc.scan", "pc.index", "desktop.find_file"]:
        assert name in core._LONG_OK, name


if __name__ == "__main__":
    test_routes()
    test_first_second_last_pick_the_right_video()
    test_no_search_yet_says_so_and_bare_song_passes()
    test_youtube_list_parses_the_results_page()
    test_pc_summary_from_a_profile()
    test_long_phrases_reach_the_pc_skills()
    print("stage16: all passed")
