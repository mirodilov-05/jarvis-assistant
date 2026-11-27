"""Documents: find things inside your PDF, Word and text files, by words and by meaning.

Only after the owner says yes (the same rule as the file-name index). Reads Documents, Desktop and Downloads.
Skips hidden files, files over 30 MB, and any file whose name suggests a secret (пароль, password, token, key).
Nothing leaves the PC: the search runs on this machine, and the answer names the file and the page.
"""
from __future__ import annotations

import math
import os
import re
import threading
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from cognition import db

ROOTS = [Path.home() / "Documents", Path.home() / "Desktop", Path.home() / "Downloads"]
EXTS = {".pdf", ".docx", ".txt", ".md"}
MAX_BYTES = 30 * 2 ** 20
SECRET = re.compile(r"парол|password|passwd|secret|token|ключ|key|pin|логин|login", re.I)
CHUNK, OVERLAP = 700, 120
WORD = re.compile(r"\w+", re.UNICODE)
STATE = {"running": False, "files": 0, "chunks": 0, "at": "", "error": ""}


def _chunks(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK])
        i += CHUNK - OVERLAP
    return [c for c in out if len(c.strip()) > 40]


def read_file(path: Path) -> list[tuple[int, str]]:
    """[(page, text)]: page 0 when the format has no pages."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paras = ["".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p")]
        return [(0, "\n".join(paras))]
    return [(0, path.read_text(encoding="utf-8", errors="replace"))]


def candidates(roots=None) -> list[Path]:
    out = []
    for root in roots or ROOTS:
        if not root.exists():
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith((".", "$")) and d.lower() not in ("node_modules", ".git", "venv", ".venv")]
            for f in fn:
                p = Path(dp) / f
                if p.suffix.lower() not in EXTS or f.startswith(("~", ".")) or SECRET.search(f):
                    continue
                try:
                    if p.stat().st_size <= MAX_BYTES:
                        out.append(p)
                except OSError:
                    continue
    return out


def index(roots=None, path=None, max_chunks: int = 20000) -> dict:
    """Reads what changed since the last time and stores the chunks with their meaning vectors."""
    files = chunks_n = 0
    with db._LOCK, db.conn(path) as c:
        known = {r["path"]: r["mtime"] for r in c.execute("SELECT path, MAX(mtime) AS mtime FROM docs GROUP BY path")}
    for p in candidates(roots):
        mt = p.stat().st_mtime
        if known.get(str(p)) == mt:
            files += 1
            continue
        try:
            pages = read_file(p)
        except Exception:  # noqa: BLE001 — a broken file is skipped, not fatal
            continue
        rows = []
        for page, text in pages:
            for k, ch in enumerate(_chunks(text)):
                rows.append((str(p), mt, k, page, ch, db.to_blob(db.embed_one(ch))))
                if chunks_n + len(rows) >= max_chunks:
                    break
        with db._LOCK, db.conn(path) as c:
            c.execute("DELETE FROM docs WHERE path = ?", (str(p),))
            c.executemany("INSERT INTO docs(path,mtime,chunk,page,text,vec) VALUES(?,?,?,?,?,?)", rows)
        files += 1
        chunks_n += len(rows)
        if chunks_n >= max_chunks:
            break
    STATE.update(files=files, chunks=count(path), at=db.now())
    return {"files": files, "chunks": STATE["chunks"]}


def count(path=None) -> int:
    with db.conn(path) as c:
        return c.execute("SELECT COUNT(*) FROM docs").fetchone()[0]


def start_background(roots=None, path=None) -> bool:
    if STATE["running"]:
        return False
    STATE.update(running=True, error="")

    def work():
        try:
            index(roots, path)
        except Exception as e:  # noqa: BLE001
            STATE["error"] = str(e)[:160]
        finally:
            STATE["running"] = False
    threading.Thread(target=work, daemon=True, name="docs-index").start()
    return True


def search(query: str, k: int = 4, path=None) -> list[dict]:
    """Chunks that best match the words and the meaning of the query."""
    words = [w for w in WORD.findall(query.lower()) if len(w) > 2]
    with db.conn(path) as c:
        rows = [dict(r) for r in c.execute("SELECT id, path, page, text, vec FROM docs").fetchall()]
    if not rows:
        return []
    n = len(rows)
    df = Counter()
    toks = []
    for r in rows:
        t = set(WORD.findall(r["text"].lower()))
        toks.append(t)
        df.update(t & set(words))
    q = db.embed_one(query)
    sem = db.cosine(q, [db.from_blob(r["vec"]) for r in rows]) if q is not None else [0.0] * n
    scored = []
    for i, r in enumerate(rows):
        lex = sum(math.log(1 + n / (1 + df[w])) for w in words if w in toks[i])
        s = lex + 6.0 * float(sem[i])
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    best, seen = [], set()
    for s, r in scored:                                    # one best chunk per file and page, not five from one place
        key = (r["path"], r["page"])
        if key in seen:
            continue
        seen.add(key)
        best.append({"file": Path(r["path"]).name, "path": r["path"], "page": r["page"], "text": r["text"][:260]})
        if len(best) >= k:
            break
    return best


def summary(query: str, path=None) -> str:
    """No model needed: the three most relevant chunks of the best file, as the text to read."""
    hits = search(query, 1, path)
    if not hits:
        return ""
    with db.conn(path) as c:
        rows = c.execute("SELECT text FROM docs WHERE path = ? ORDER BY page, chunk LIMIT 3", (hits[0]["path"],)).fetchall()
    return " ".join(r["text"][:300] for r in rows)
