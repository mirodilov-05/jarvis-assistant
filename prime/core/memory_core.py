"""Local memory on SQLite (standard library). Goals, tasks, notes, study cards, history.

Writes run in a worker thread so the event loop never waits on the disk.
Daily backups are kept in backups/ (the newest 14).
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY, title TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'day',
  parent_id INTEGER, progress REAL NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, text TEXT NOT NULL, due TEXT, done INTEGER NOT NULL DEFAULT 0,
  goal_id INTEGER, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, text TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, amount REAL NOT NULL, category TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cards(id INTEGER PRIMARY KEY, front TEXT NOT NULL, back TEXT NOT NULL,
  ease REAL NOT NULL DEFAULT 2.5, interval_days INTEGER NOT NULL DEFAULT 0, due TEXT NOT NULL);
"""


class Memory:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---- low level, always called through asyncio.to_thread
    def _exec(self, sql: str, args: tuple = ()) -> int:
        cur = self._conn.execute(sql, args)
        self._conn.commit()
        return cur.lastrowid or 0

    def _all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    # ---- public async API
    async def add_task(self, text: str, due: str | None = None, goal_id: int | None = None) -> int:
        return await asyncio.to_thread(self._exec, "INSERT INTO tasks(text,due,goal_id,created) VALUES(?,?,?,?)",
                                       (text, due, goal_id, _now()))

    async def finish_task(self, task_id: int) -> None:
        await asyncio.to_thread(self._exec, "UPDATE tasks SET done=1 WHERE id=?", (task_id,))

    async def open_tasks(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._all, "SELECT * FROM tasks WHERE done=0 ORDER BY COALESCE(due,'9999')")

    async def add_goal(self, title: str, level: str = "day", parent_id: int | None = None) -> int:
        return await asyncio.to_thread(self._exec, "INSERT INTO goals(title,level,parent_id,created) VALUES(?,?,?,?)",
                                       (title, level, parent_id, _now()))

    async def set_progress(self, goal_id: int, progress: float) -> None:
        progress = max(0.0, min(1.0, progress))
        await asyncio.to_thread(self._exec, "UPDATE goals SET progress=? WHERE id=?", (progress, goal_id))

    async def goals(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._all, "SELECT * FROM goals ORDER BY level, id")

    async def add_note(self, text: str) -> int:
        return await asyncio.to_thread(self._exec, "INSERT INTO notes(text,created) VALUES(?,?)", (text, _now()))

    async def add_expense(self, amount: float, category: str, note: str = "") -> int:
        return await asyncio.to_thread(self._exec, "INSERT INTO expenses(amount,category,note,created) VALUES(?,?,?,?)",
                                       (amount, category, note, _now()))

    async def expenses_between(self, start: str, end: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._all, "SELECT * FROM expenses WHERE created >= ? AND created < ?", (start, end))

    async def cards_due(self, today: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._all, "SELECT * FROM cards WHERE due <= ? ORDER BY due", (today,))

    async def cards_count(self) -> int:
        return (await asyncio.to_thread(self._all, "SELECT COUNT(*) AS n FROM cards", ()))[0]["n"]

    async def save_card(self, card_id: int | None, front: str, back: str, ease: float, interval: int, due: str) -> int:
        if card_id is None:
            return await asyncio.to_thread(self._exec, "INSERT INTO cards(front,back,ease,interval_days,due) VALUES(?,?,?,?,?)",
                                           (front, back, ease, interval, due))
        await asyncio.to_thread(self._exec, "UPDATE cards SET ease=?, interval_days=?, due=? WHERE id=?",
                                (ease, interval, due, card_id))
        return card_id

    async def recent_turns(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await asyncio.to_thread(self._all, "SELECT role, text, created FROM history ORDER BY id DESC LIMIT ?", (limit,))
        return list(reversed(rows))

    async def log_turn(self, role: str, text: str) -> None:
        await asyncio.to_thread(self._exec, "INSERT INTO history(role,text,created) VALUES(?,?,?)", (role, text, _now()))

    async def integrity_ok(self) -> bool:
        def check() -> bool:
            return self._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return await asyncio.to_thread(check)

    async def backup(self, folder: Path, keep: int = 14) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"memory-{datetime.now():%Y-%m-%d}.db"

        def do() -> None:
            dst = sqlite3.connect(target)
            try:
                self._conn.backup(dst)
            finally:
                dst.close()
            for old in sorted(folder.glob("memory-*.db"))[:-keep]:
                old.unlink(missing_ok=True)

        await asyncio.to_thread(do)
        return target

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
