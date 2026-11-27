"""Four memory layers, one recall() that asks all of them at once.

working     the last ten exchanges of this session (from data/history.jsonl)
episodic    what happened: each exchange with its mood, its valence (+1 liked, -1 corrected), and whether it was a mistake.
            importance = (0.5 + |valence| * 0.3 + 0.2 if mistake) * 0.95 ** age_days
semantic    stable facts about the owner, added by hand or by the phrase «запомни факт: ...»
procedural  phrases the owner repeats and the skill that answered them (counted, shown as habits)
"""
from __future__ import annotations

import datetime as dt
import re

import numpy as np

from cognition import db
from learning import store as lstore

STRESS = ("устал", "стресс", "тяжело", "раздраж", "злюсь", "бесит", "плохо", "не могу", "выгорел", "грустно", "тревожно")
WORD = re.compile(r"\w+", re.UNICODE)


def mood_of(text: str) -> str:
    t = (text or "").lower()
    return "стресс" if any(w in t for w in STRESS) else ""


def importance(valence: float, mistake: bool, created: str, today: dt.date | None = None) -> float:
    try:
        age = ((today or dt.date.today()) - dt.date.fromisoformat(created[:10])).days
    except ValueError:
        age = 0
    return (0.5 + abs(valence) * 0.3 + (0.2 if mistake else 0.0)) * (0.95 ** max(0, age))


def record_turn(user_text: str, reply: str, source: str, skill: str = "", valence: float = 0.0, mistake: bool = False,
                path=None) -> None:
    """After every exchange: store the episode, and count the procedure (the phrase and the skill that answered it)."""
    if not user_text.strip():
        return
    vec = db.embed_one(user_text + " " + reply[:200])
    with db._LOCK, db.conn(path) as c:
        c.execute("INSERT INTO episodes(created,user_text,reply,source,skill,valence,mood,mistake,vec) VALUES(?,?,?,?,?,?,?,?,?)",
                  (db.now(), user_text[:400], reply[:400], source, skill, valence, mood_of(user_text), int(mistake), db.to_blob(vec)))
        mood = mood_of(user_text)
        if mood:   # the proactive check-in reads these two
            for key, val in (("last_mood", mood), ("last_mood_at", db.now())):
                c.execute("INSERT INTO relationship(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, val))
        if skill:
            key = " ".join(WORD.findall(user_text.lower()))[:80]
            c.execute("INSERT INTO procedures(phrase,skill,hits,last) VALUES(?,?,1,?) ON CONFLICT(phrase) DO UPDATE SET "
                      "hits = hits + 1, skill = excluded.skill, last = excluded.last", (key, skill, db.now()))


def working(limit: int = 10) -> list[dict]:
    import core
    return [{"user": h.get("user", ""), "reply": h.get("reply", "")} for h in core.read_history(limit)]


def facts(path=None) -> list[dict]:
    with db.conn(path) as c:
        return [dict(r) for r in c.execute("SELECT id, created, text FROM facts ORDER BY id").fetchall()]


def add_fact(text: str, path=None) -> int:
    text = text.strip()[:300]
    if not text:
        raise ValueError("пустой факт")
    vec = db.embed_one(text)
    with db._LOCK, db.conn(path) as c:
        cur = c.execute("INSERT OR IGNORE INTO facts(created,text,vec) VALUES(?,?,?)", (db.now(), text, db.to_blob(vec)))
        return cur.lastrowid or 0


def delete_fact(fid: int, path=None) -> None:
    with db._LOCK, db.conn(path) as c:
        c.execute("DELETE FROM facts WHERE id = ?", (fid,))


def habits(limit: int = 8, path=None) -> list[dict]:
    with db.conn(path) as c:
        return [dict(r) for r in c.execute("SELECT phrase, skill, hits FROM procedures ORDER BY hits DESC LIMIT ?", (limit,)).fetchall()]


def recall(query: str, k: int = 3, path=None, lessons_path=None) -> dict:
    """The four layers at once. Meaning (MiniLM) plus the same words, so it still works when the model is off."""
    q = db.embed_one(query)
    qw = {w for w in WORD.findall(query.lower()) if len(w) > 2}   # short words (я, и, в) match everything

    def rank(vecs, texts):
        # with the meaning model, words are a small bonus; without it, words are the whole search
        sem = db.cosine(q, vecs)
        kw = np.array([len(qw & set(WORD.findall(t.lower()))) / max(1, len(qw)) for t in texts], dtype=np.float32)
        return sem + (0.3 if q is not None else 1.0) * kw

    threshold = 0.3 if q is not None else 0.2
    with db.conn(path) as c:
        eps = [dict(r) for r in c.execute("SELECT * FROM episodes ORDER BY id DESC LIMIT 800").fetchall()]
        fs = [dict(r) for r in c.execute("SELECT * FROM facts").fetchall()]
    les = lstore.lessons(200, lessons_path)
    e_s = rank([db.from_blob(e["vec"]) for e in eps], [e["user_text"] + " " + e["reply"] for e in eps])
    # relevance decides whether an episode is shown at all; importance only decides the order among the relevant ones
    e_rank = sorted(((float(s), float(s) * importance(e["valence"], bool(e["mistake"]), e["created"]), e)
                     for s, e in zip(e_s, eps) if float(s) > threshold), key=lambda x: -x[1])
    f_s = rank([db.from_blob(f["vec"]) for f in fs], [f["text"] for f in fs])
    f_rank = sorted(zip(f_s, fs), key=lambda x: -x[0])
    l_s = rank([None] * len(les), [l["trigger_text"] + " " + l["right_action"] for l in les])
    l_rank = sorted(zip(l_s, les), key=lambda x: -x[0])
    return {
        "working": working(10),
        "episodic": [{"user": e["user_text"], "reply": e["reply"], "when": e["created"][:16]} for _, _, e in e_rank[:k]],
        "semantic": [f["text"] for s, f in f_rank[:k] if s > threshold],
        "lessons": [f"{l['trigger_text']} → {l['right_action']}" for s, l in l_rank[:k] if s > threshold],
        "habits": habits(3, path),
    }
