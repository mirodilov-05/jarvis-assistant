"""Cognitive layer: memory layers, relationship stages, proactive limits, presentation control, documents, shield."""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cognition import db, docs, memory, personality, proactive, show, shield  # noqa: E402


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    assert ok, name


def tmp(name):
    return Path(tempfile.mkdtemp()) / name


def test_episodes_and_recall():
    p = tmp("e.db")
    memory.record_turn("включи музыку", "открываю Яндекс Музыку", "голос", skill="music.play", path=p)
    memory.record_turn("я устал сегодня", "отдыхайте, сэр", "текст", path=p)
    memory.add_fact("я работаю программистом", path=p)
    r = memory.recall("когда я просил музыку", path=p)
    assert r["episodic"] and "музыку" in r["episodic"][0]["user"], r
    f = memory.recall("кем я работаю", path=p)
    assert f["semantic"] and "программистом" in f["semantic"][0], f
    assert memory.habits(path=p)[0]["skill"] == "music.play"
    check("episodes, facts and habits are recalled by words", True)


def test_mood_is_remembered_for_the_check_in():
    p = tmp("m.db")
    memory.record_turn("я очень устал", "ок", "текст", path=p)
    with db.conn(p) as c:
        val = c.execute("SELECT value FROM relationship WHERE key='last_mood'").fetchone()[0]
    assert val == "стресс"
    check("tired words set the mood the check-in reads", True)


def test_importance_fades_and_counts_mistakes():
    today = dt.date(2026, 11, 27)
    fresh = memory.importance(0.0, False, "2026-11-27", today)
    old = memory.importance(0.0, False, "2026-10-01", today)
    mistake = memory.importance(-1.0, True, "2026-11-27", today)
    assert fresh > old and mistake > fresh
    check("importance: fades with age, mistakes and strong feelings count more", True)


def test_relationship_stage_from_numbers():
    p = tmp("s.db")
    assert personality.stage(p)["stage"] == "знакомые"
    with db.conn(p) as c:
        for i in range(40):
            c.execute("INSERT INTO episodes(created,user_text,reply,source,valence) VALUES(?,?,?,?,?)",
                      ((dt.date(2026, 11, 1) + dt.timedelta(days=i % 5)).isoformat() + "T10:00", "x", "y", "текст", 1.0))
    st = personality.stage(p, today=dt.date(2026, 11, 27))
    assert st["stage"] == "друг", st
    check("stage: друг after three days and thirty exchanges", True)


def test_proactive_break_and_limits():
    p = tmp("p.db")
    day = dt.datetime(2026, 11, 27, 15, 0)
    said = proactive.decide(day, idle_s=10, streak_min=160, path=p)
    assert said and any("разомнитесь" in x for x in said), said
    assert proactive.decide(day, idle_s=10, streak_min=170, path=p) == [], "once a day"
    night = dt.datetime(2026, 11, 27, 2, 0)
    assert proactive.decide(night, idle_s=10, streak_min=999, path=tmp("n.db")) == [], "never at night"
    check("break after 150 minutes, once a day, never at night", True)


def test_proactive_stress_check_in():
    p = tmp("c.db")
    memory.record_turn("я очень устал", "ок", "текст", path=p)
    said = proactive.decide(dt.datetime(2026, 11, 27, 16, 0), idle_s=0, streak_min=0, path=p)
    assert any("устали" in s for s in said), said
    check("tired speech gives one check-in the same day", True)


def test_presentation_follows_voice():
    show.STATE.update(active=False, i=0, slides=[])
    show.STATE["slides"] = [{"title": "a", "say": "первый"}, {"title": "b", "say": "второй"}]
    show.STATE["active"] = True
    assert show.step(1)["i"] == 1 and show.say_current() == "второй"
    assert show.step(5)["i"] == 1, "stops at the last slide"
    show.stop()
    assert show.step(-1)["active"] is False
    check("next and previous slide, and the end of the show", True)


def test_documents_search_and_summary():
    d = Path(tempfile.mkdtemp())
    (d / "report.txt").write_text("Отчёт по проекту Ромашка: выручка выросла на двадцать процентов в третьем квартале. " * 3, encoding="utf-8")
    (d / "password_notes.txt").write_text("пароль от банка 1234 " * 10, encoding="utf-8")
    p = tmp("d.db")
    docs.index([d], p)
    hits = docs.search("выручка проекта", path=p)
    assert hits and hits[0]["file"] == "report.txt"
    assert not docs.search("пароль банка", path=p), "secret-looking files are never indexed"
    assert "выручка" in docs.summary("выручка", path=p)
    check("documents: found by words, names skipped, summary without a model", True)


def test_shield_reads_without_changing_anything():
    p = shield.ports()
    assert "listening" in p and "remote" in p
    v = shield.vpn()
    assert "on" in v
    try:
        shield.block_ip("192.168.1.10")
        check("private address refused", False)
    except ValueError:
        check("private address refused", True)
    try:
        shield.block_ip("не ip")
        check("bad address refused", False)
    except ValueError:
        check("bad address refused", True)


if __name__ == "__main__":
    test_episodes_and_recall()
    test_mood_is_remembered_for_the_check_in()
    test_importance_fades_and_counts_mistakes()
    test_relationship_stage_from_numbers()
    test_proactive_break_and_limits()
    test_proactive_stress_check_in()
    test_presentation_follows_voice()
    test_documents_search_and_summary()
    test_shield_reads_without_changing_anything()
    print("stage29: all passed")
