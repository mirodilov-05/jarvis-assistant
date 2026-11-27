"""Self-learning: Jarvis notices his own failures and learns what you meant, without being told.

1. A failed answer («Не понял», an error in a skill, «не нашёл программу») is stored as a mistake at once.
   You do not have to say «нет, я имел в виду»: these mistakes go into the lessons like corrections do.
2. If within two minutes after a failure you say the same thing in other words, and that works, Jarvis keeps the
   link. Next time the first wording runs the second one at once («самопрезентуй себя» → «расскажи о себе»).
3. «Забудь последнее обучение» removes the last link; «что ты выучил сам» lists them.

Only phrases of two words or more are learned: a one-word fragment is almost always a misheard word.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from learning import store

WINDOW_S = 120            # a rephrasing counts only shortly after the failure
FAIL = re.compile(
    r"^(?:не понял|не поняла|повторите|ошибка в навыке|не получилось|не нашёл|не нашел|я не знаю|не знаю, как|"
    r"у меня нет возможности|извините, с этим|не умею|не могу)", re.I)
_STOP = {"джарвис", "пожалуйста", "можешь", "сделай", "давай", "теперь", "просто", "этот", "этого", "тебя", "себя"}
_LAST_FAIL: dict = {"text": "", "reply": "", "at": 0.0}
_LOCK = threading.Lock()
SCHEMA = """CREATE TABLE IF NOT EXISTS aliases(
  id INTEGER PRIMARY KEY, phrase TEXT NOT NULL UNIQUE, means TEXT NOT NULL, created_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0)"""


def _conn(path: Path | None = None):
    con = store._conn(path)
    con.execute(SCHEMA)
    return con


def norm(text: str) -> str:
    t = text.lower().replace("ё", "е")
    t = re.sub(r"^(?:эй,?\s*)?джарвис[,!\s]*", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def failed(reply: str) -> bool:
    return bool(FAIL.match((reply or "").strip()))


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[а-яa-z0-9]{4,}", norm(text)) if w not in _STOP}


def related(a: str, b: str) -> bool:
    """Two wordings of one request share at least one meaningful word stem."""
    return bool(_stems(a) & _stems(b))


def observe(text: str, reply: str, skill: str = "", tools: str = "", source: str = "",
            now: float | None = None, path: Path | None = None) -> str:
    """Called after every exchange. Returns "mistake", "learned" or ""."""
    now = time.time() if now is None else now
    if skill.startswith("learning."):
        return ""
    if failed(reply):
        store.add_feedback(text, reply, rating=-1, skill=skill, comment="сам: не справился", severity=0.4, path=path)
        if len(norm(text).split()) >= 2:
            with _LOCK:
                _LAST_FAIL.update(text=text, reply=reply, at=now)
        return "mistake"
    acted = bool(skill or tools)
    with _LOCK:
        last = dict(_LAST_FAIL)
        if acted:
            _LAST_FAIL.update(text="", reply="", at=0.0)
    if (acted and last["text"] and now - last["at"] <= WINDOW_S and norm(text) != norm(last["text"])
            and related(last["text"], text)):
        learn(last["text"], text, path=path)
        store.add_lesson(last["text"], last["reply"], f"выполнить: {text}", context="переформулировка", severity=0.5, path=path)
        return "learned"
    return ""


def learn(phrase: str, means: str, path: Path | None = None) -> None:
    import datetime as dt
    with _LOCK, _conn(path) as con:
        con.execute("INSERT INTO aliases(phrase, means, created_at) VALUES(?,?,?) "
                    "ON CONFLICT(phrase) DO UPDATE SET means = excluded.means, created_at = excluded.created_at",
                    (norm(phrase), means.strip(), dt.datetime.now().isoformat(timespec="seconds")))


def resolve(text: str, path: Path | None = None) -> str | None:
    """What a learned wording means, or None."""
    key = norm(text)
    if not key:
        return None
    with _LOCK, _conn(path) as con:
        row = con.execute("SELECT id, means FROM aliases WHERE phrase = ?", (key,)).fetchone()
        if not row:
            return None
        con.execute("UPDATE aliases SET used = used + 1 WHERE id = ?", (row["id"],))
        return row["means"]


def aliases(limit: int = 50, path: Path | None = None) -> list[dict]:
    with _conn(path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM aliases ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def forget_last(path: Path | None = None) -> dict | None:
    with _LOCK, _conn(path) as con:
        row = con.execute("SELECT * FROM aliases ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            con.execute("DELETE FROM aliases WHERE id = ?", (row["id"],))
        return dict(row) if row else None


def forget(alias_id: int, path: Path | None = None) -> None:
    with _LOCK, _conn(path) as con:
        con.execute("DELETE FROM aliases WHERE id = ?", (alias_id,))
