"""SQLite store for the learning core: data/jarvis_cognitive.db (standard library only, no extra packages)."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import threading
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "jarvis_cognitive.db"
_LOCK = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons(
  id INTEGER PRIMARY KEY, trigger_text TEXT NOT NULL, wrong_action TEXT NOT NULL, right_action TEXT NOT NULL,
  context TEXT NOT NULL DEFAULT '', severity REAL NOT NULL DEFAULT 0.5, occurrence_count INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, last_triggered_at TEXT, resolved INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, user_text TEXT NOT NULL, assistant_reply TEXT NOT NULL,
  skill_used TEXT NOT NULL DEFAULT '', rating INTEGER NOT NULL DEFAULT 0, comment TEXT NOT NULL DEFAULT '',
  severity REAL NOT NULL DEFAULT 0);
"""


def _conn(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2}


def similarity(a: str, b: str) -> float:
    """Jaccard overlap of the words: 1.0 = the same wording. Cheap and good enough to merge repeats."""
    x, y = words(a), words(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def add_feedback(user_text: str, reply: str, rating: int = 0, skill: str = "", comment: str = "",
                 severity: float = 0.0, path: Path | None = None) -> int:
    with _LOCK, _conn(path) as con:
        cur = con.execute("INSERT INTO feedback(timestamp,user_text,assistant_reply,skill_used,rating,comment,severity) "
                          "VALUES(?,?,?,?,?,?,?)", (_now(), user_text[:500], reply[:800], skill, rating, comment[:300], severity))
        return cur.lastrowid


def add_lesson(trigger: str, wrong: str, right: str, context: str = "", severity: float = 0.5,
               path: Path | None = None) -> int:
    """Stores a lesson. A lesson with nearly the same trigger (similarity > 0.6) is merged: the count grows instead."""
    with _LOCK, _conn(path) as con:
        for row in con.execute("SELECT id, trigger_text, severity, occurrence_count FROM lessons WHERE resolved = 0"):
            if similarity(row["trigger_text"], trigger) > 0.6:
                con.execute("UPDATE lessons SET occurrence_count = ?, severity = ?, last_triggered_at = ?, right_action = ? WHERE id = ?",
                            (row["occurrence_count"] + 1, max(row["severity"], severity), _now(), right, row["id"]))
                return row["id"]
        cur = con.execute("INSERT INTO lessons(trigger_text,wrong_action,right_action,context,severity,created_at) VALUES(?,?,?,?,?,?)",
                          (trigger[:300], wrong[:300], right[:300], context[:80], severity, _now()))
        return cur.lastrowid


def lessons(limit: int = 50, path: Path | None = None) -> list[dict]:
    with _conn(path) as con:
        rows = con.execute("SELECT * FROM lessons WHERE resolved = 0").fetchall()
    ranked = sorted((dict(r) for r in rows), key=lambda r: r["severity"] + 0.15 * r["occurrence_count"], reverse=True)
    return ranked[:limit]


def recent_feedback(limit: int = 200, path: Path | None = None) -> list[dict]:
    with _conn(path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
