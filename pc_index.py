"""Index of the file NAMES on this computer, built only after the owner's explicit consent.

What is stored: file name, folder, extension, size and date. What is never read: the contents of any file.
Secrets are skipped by name (keys, passwords, tokens, cookies, session files) and never stored.
Windows, program and build folders are skipped. Everything goes to data/pc_index.db on this PC only.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import os
import sqlite3
import string
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "pc_index.db"
_LOCK = threading.Lock()

USER_FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]
SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
             "system volume information", "appdata", "node_modules", ".venv", "venv", "__pycache__", ".git",
             ".cache", "site-packages", "recovery", "perflogs", "$windows.~bt", "temp", ".idea", ".vs", "steamapps"}
SECRET_PATTERNS = [".env", ".env.*", "*.key", "*.pem", "*.p12", "*.pfx", "*.kdbx", "*.ppk", "*.ovpn", "*.session",
                   "id_rsa*", "id_ed25519*", "*password*", "*passwd*", "*secret*", "*token*", "*credential*",
                   "*wallet*", "cookies*", "login data*", "*.gpg", "*.asc", "tv_token.txt"]
PROJECT_MARKERS = [".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", "requirements.txt"]
MAX_FILES = 300_000
MAX_DEPTH = 7
TIME_BUDGET_S = 300


def _is_secret(name: str) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatch(low, pat) for pat in SECRET_PATTERNS)


def _roots() -> list[Path]:
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    roots = [home / f for f in USER_FOLDERS if (home / f).exists()]
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        if letter == "C" or not drive.exists():
            continue                      # the system drive is covered by the user folders; other drives are indexed
        roots.append(drive)
    return roots


def _connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, name TEXT, ext TEXT, folder TEXT, "
                "size INTEGER, mtime REAL)")
    con.execute("CREATE INDEX IF NOT EXISTS files_name ON files(name)")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return con


def build(roots: list[Path] | None = None) -> dict:
    """Walk the chosen folders and rebuild the index. Call only after the owner agreed."""
    started = time.time()
    roots = roots or _roots()
    rows, projects, skipped_secret, truncated = [], [], 0, False
    stack = [(r, 0) for r in roots if r.exists()]
    while stack:
        if time.time() - started > TIME_BUDGET_S or len(rows) >= MAX_FILES:
            truncated = True
            break
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        names = {e.name for e in entries}
        if any(m in names for m in PROJECT_MARKERS) and depth > 0:
            projects.append(str(folder))
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if depth < MAX_DEPTH and e.name.lower() not in SKIP_DIRS and not e.name.startswith("."):
                        stack.append((Path(e.path), depth + 1))
                    continue
                if not e.is_file(follow_symlinks=False):
                    continue
                if _is_secret(e.name):
                    skipped_secret += 1
                    continue
                st = e.stat(follow_symlinks=False)
                rows.append((e.path, e.name, Path(e.name).suffix.lower(), str(folder), st.st_size, st.st_mtime))
            except OSError:
                continue
    with _LOCK:
        con = _connect()
        with con:
            con.execute("DELETE FROM files")
            con.executemany("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)", rows)
            meta = {"built_at": dt.datetime.now().isoformat(timespec="seconds"),
                    "roots": ", ".join(str(r) for r in roots), "files": str(len(rows)),
                    "projects": "\n".join(projects[:200]), "skipped_secret": str(skipped_secret),
                    "truncated": "1" if truncated else "0", "seconds": str(round(time.time() - started))}
            con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", meta.items())
        con.close()
    return info()


def info() -> dict:
    with _LOCK:
        if not DB.exists():
            return {"built": False}
        con = _connect()
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        con.close()
    if not meta:
        return {"built": False}
    return {"built": True, "built_at": meta.get("built_at"), "files": int(meta.get("files", 0)),
            "projects": [p for p in meta.get("projects", "").split("\n") if p],
            "skipped_secret": int(meta.get("skipped_secret", 0)), "truncated": meta.get("truncated") == "1",
            "roots": meta.get("roots", "").split(", ")}


def search(query: str, limit: int = 10) -> list[str]:
    """Paths of files whose names contain every word of the query, newest first."""
    import re
    words = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 1]
    if not words or not DB.exists():
        return []
    where = " AND ".join("lower(name) LIKE ?" for _ in words)
    with _LOCK:
        con = _connect()
        rows = con.execute(f"SELECT path FROM files WHERE {where} ORDER BY mtime DESC LIMIT ?",
                           [f"%{w}%" for w in words] + [limit]).fetchall()
        con.close()
    return [r[0] for r in rows]


def summary(max_chars: int = 500) -> str:
    """A short description for the assistant's prompt (no file names)."""
    d = info()
    if not d.get("built"):
        return ""
    proj = [Path(p).name for p in d["projects"][:12]]
    text = (f"проиндексировано файлов: {d['files']}; проекты: {len(d['projects'])}"
            + (f" ({', '.join(proj)})" if proj else ""))
    return text[:max_chars]


_RUNNING = {"on": False}


def start_background(on_done=None) -> bool:
    """Build the index in a background thread (it can take minutes). False if one is already running."""
    if _RUNNING["on"]:
        return False
    _RUNNING["on"] = True

    def work():
        try:
            build()
            if on_done:
                on_done()
        finally:
            _RUNNING["on"] = False

    threading.Thread(target=work, daemon=True, name="pc-index").start()
    return True


def running() -> bool:
    return _RUNNING["on"]
