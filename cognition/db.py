"""Shared SQLite file for everything the cognitive layer keeps. Standard library only (numpy for vectors)."""
from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path

import numpy as np

DB = Path(__file__).resolve().parent.parent / "data" / "jarvis_cognitive.db"
_LOCK = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes(
  id INTEGER PRIMARY KEY, created TEXT NOT NULL, user_text TEXT NOT NULL, reply TEXT NOT NULL, source TEXT NOT NULL,
  skill TEXT NOT NULL DEFAULT '', valence REAL NOT NULL DEFAULT 0, mood TEXT NOT NULL DEFAULT '',
  mistake INTEGER NOT NULL DEFAULT 0, vec BLOB);
CREATE TABLE IF NOT EXISTS facts(
  id INTEGER PRIMARY KEY, created TEXT NOT NULL, text TEXT NOT NULL UNIQUE, vec BLOB);
CREATE TABLE IF NOT EXISTS procedures(
  phrase TEXT PRIMARY KEY, skill TEXT NOT NULL, hits INTEGER NOT NULL DEFAULT 0, last TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relationship(
  key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY, path TEXT NOT NULL, mtime REAL NOT NULL, chunk INTEGER NOT NULL, page INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL, vec BLOB);
CREATE INDEX IF NOT EXISTS docs_path ON docs(path);
"""


def conn(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def to_blob(vec) -> bytes | None:
    return None if vec is None else np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob) -> np.ndarray | None:
    return None if not blob else np.frombuffer(blob, dtype=np.float32)


def embed_one(text: str):
    """A meaning vector, or None when the model is not there (search then uses words only)."""
    try:
        import memory
        if not memory.available():
            return None
        return memory.embed([text[:500]])[0]
    except Exception:  # noqa: BLE001 — search must still work without the model
        return None


def cosine(q, rows: list) -> np.ndarray:
    out = np.zeros(len(rows), dtype=np.float32)
    if q is None:
        return out
    for i, v in enumerate(rows):
        if v is not None and v.shape == q.shape:
            out[i] = float(np.dot(q, v))
    return out
