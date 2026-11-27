"""TV music and the «first video» memory, and the gaps found by the 300-phrase check.

Nothing is played: the YouTube search and the TV call are replaced.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import core  # noqa: E402
from core import Ctx, normalize  # noqa: E402

core.load_plugins()
CATCH = {"music.choice", "macros.run"}
ROUTES = {
    "поставь музыку на телевизоре": "tv.media",
    "включи Imagine Dragons в телевизоре": "tv.media",
    "включи ютуб в телевизоре": "prime.tv",
    "запусти первое видео": "apps.result_open",
    "покажи статус системы": "batch2.system",
    "какой план на сегодня": "batch2.plan",
    "сделай паузу на час": "batch2.pause_hour",
    "что я запоминал про ключ": "batch2.remember_recall",
    "сколько у меня свободного места на диске": "batch2.disk",
}


def first_match(text):
    norm = normalize(text, "ru")
    for sk in core.SKILLS:
        if sk.name in CATCH:
            continue
        if any(p.search(norm) for p in sk.patterns.get("ru", [])):
            return sk.name
    return None


def test_routes():
    bad = {t: (first_match(t), want) for t, want in ROUTES.items() if first_match(t) != want}
    assert not bad, bad


def test_first_video_after_a_tv_search_plays_on_the_tv():
    played_tv, played_pc = [], []
    apps = next(s for s in core.SKILLS if s.name == "apps.result_open").handler.__globals__
    saved = (apps["_tv_video"], apps["os"].startfile)
    apps["_tv_video"] = lambda vid: played_tv.append(vid) or "ok"
    apps["os"].startfile = lambda url: played_pc.append(url)
    core.set_results("youtube_tv", [{"id": "AAAAAAAAAAA", "title": "first"}, {"id": "BBBBBBBBBBB", "title": "second"}])
    try:
        sk = next(s for s in core.SKILLS if s.name == "apps.result_open")
        norm = normalize("запусти первое видео", "ru")
        m = next(p.search(norm) for p in sk.patterns["ru"] if p.search(norm))
        reply = sk.handler(Ctx(text="запусти первое видео", lang="ru", source="тест", config={}, match=m, norm=norm))
    finally:
        apps["_tv_video"], apps["os"].startfile = saved
        core.set_results("youtube", [])
    assert played_tv == ["AAAAAAAAAAA"] and not played_pc, (played_tv, played_pc)
    assert "На телевизоре" in reply, reply


if __name__ == "__main__":
    test_routes()
    test_first_video_after_a_tv_search_plays_on_the_tv()
    print("stage25: all passed")
