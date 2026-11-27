"""Life flow: goals cascade (year > month > week > day), Rule of 3, anti-overload rebalancing, inbox sorting.

Progress of a parent goal is the average of its children, so finishing a day step moves the whole chain.
"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

LEVELS = ("year", "month", "week", "day")
MAX_FOCUS = 3


def rollup(goals: list[dict[str, Any]]) -> dict[int, float]:
    """Progress for every goal: leaves use their own value, parents use the average of their children."""
    children: dict[int, list[int]] = {}
    by_id = {g["id"]: g for g in goals}
    for g in goals:
        if g.get("parent_id") is not None:
            children.setdefault(g["parent_id"], []).append(g["id"])
    out: dict[int, float] = {}

    def value(gid: int, seen: frozenset[int] = frozenset()) -> float:
        if gid in out:
            return out[gid]
        if gid in seen:                                    # guards against a cycle in bad data
            return float(by_id[gid].get("progress", 0.0))
        kids = children.get(gid)
        v = (sum(value(k, seen | {gid}) for k in kids) / len(kids)) if kids else float(by_id[gid].get("progress", 0.0))
        out[gid] = max(0.0, min(1.0, v))
        return out[gid]

    for gid in by_id:
        value(gid)
    return out


def rule_of_three(tasks: list[dict[str, Any]], today: str) -> list[dict[str, Any]]:
    """The three things that matter today: overdue first, then due today, then the rest by date."""
    open_tasks = [t for t in tasks if not t.get("done")]

    def key(t: dict[str, Any]) -> tuple[int, str]:
        due = t.get("due") or "9999-12-31"
        bucket = 0 if due[:10] < today else 1 if due[:10] == today else 2
        return bucket, due

    return sorted(open_tasks, key=key)[:MAX_FOCUS]


def rebalance(tasks: list[dict[str, Any]], today: str) -> list[dict[str, Any]]:
    """Overdue tasks move to today instead of piling up. Returns the tasks that were moved."""
    moved = []
    for t in tasks:
        due = (t.get("due") or "")[:10]
        if not t.get("done") and due and due < today:
            t["due"] = today + "T09:00"
            moved.append(t)
    return moved


def morning_brief(name: str, focus: list[dict[str, Any]], goals_today: list[tuple[str, float]], weather: str = "") -> str:
    lines = [f"Доброе утро{', ' + name if name else ''}."]
    if weather:
        lines.append(weather)
    if focus:
        lines.append("Главное на сегодня: " + "; ".join(t["text"] for t in focus) + ".")
    else:
        lines.append("Дел на сегодня нет.")
    for title, pct in goals_today[:3]:
        lines.append(f"{title}: {round(pct * 100)}%.")
    return " ".join(lines)


def sort_inbox(inbox: Path, dest_root: Path, dry_run: bool = False) -> list[tuple[str, str]]:
    """Move files from 00_Inbox into folders by type. Returns (file, folder) for every move.
    Never overwrites: a name clash gets a numbered suffix. Subfolders are not touched."""
    kinds = {
        "Документы": {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt"},
        "Таблицы": {".xlsx", ".xls", ".csv"},
        "Презентации": {".pptx", ".ppt"},
        "Изображения": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic"},
        "Видео": {".mp4", ".mov", ".mkv", ".webm"},
        "Аудио": {".mp3", ".wav", ".ogg", ".m4a", ".flac"},
        "Архивы": {".zip", ".rar", ".7z"},
    }
    moved: list[tuple[str, str]] = []
    if not inbox.exists():
        return moved
    for f in sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith(".")):
        folder = next((name for name, exts in kinds.items() if f.suffix.lower() in exts), "Прочее")
        target_dir = dest_root / folder
        target = target_dir / f.name
        n = 1
        while target.exists():
            target = target_dir / f"{f.stem} ({n}){f.suffix}"
            n += 1
        moved.append((f.name, folder))
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(target))
    return moved


def week_bounds(day: dt.date) -> tuple[str, str]:
    start = day - dt.timedelta(days=day.weekday())
    return start.isoformat(), (start + dt.timedelta(days=7)).isoformat()
