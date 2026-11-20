"""Semantic memory: finds notes by meaning, not by exact words.

notes.md stays the source of truth (the app's «Заметки» tab edits it). This module keeps a vector index of every
note in data/memory.db and refreshes it on each search, so added, edited or deleted notes are always in sync and
the old notes are migrated automatically on the first search.

Embeddings: paraphrase-multilingual-MiniLM-L12-v2 (quantized ONNX, ~118 MB) on the CPU with 2 threads — no GPU,
no torch, ~3 ms per phrase (beat multilingual-e5-small/base on Russian paraphrases: 10/10 vs 7 and 9). If the model is missing, search falls back to keyword matching.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import sys
import threading
from contextlib import closing
from pathlib import Path

import numpy as np

import core

log = logging.getLogger("memory")
MODEL_DIR = Path(__file__).parent / "models" / "minilm"
DB = core.DATA / "memory.db"
_lock = threading.Lock()
_model = None   # (session, tokenizer) | False when unavailable


def _load():
    global _model
    if _model is None:
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2          # stay light: games and Whisper come first
            opts.inter_op_num_threads = 1
            sess = ort.InferenceSession(str(MODEL_DIR / "onnx" / "model_quantized.onnx"), opts,
                                        providers=["CPUExecutionProvider"])
            tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
            tok.enable_truncation(256)
            tok.enable_padding()
            _model = (sess, tok)
            log.info("Memory embeddings loaded")
        except Exception as e:  # noqa: BLE001
            log.warning("Memory embeddings unavailable (%s) — keyword search only", e)
            _model = False
    return _model


def available() -> bool:
    return bool(_load())


def embed(texts: list[str]) -> np.ndarray:
    """L2-normalised sentence vectors (n, 384), mean pooling."""
    sess, tok = _load()
    enc = tok.encode_batch(texts)
    ids = np.array([e.ids for e in enc], dtype=np.int64)
    mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
    feeds = {"input_ids": ids, "attention_mask": mask}
    if any(i.name == "token_type_ids" for i in sess.get_inputs()):
        feeds["token_type_ids"] = np.zeros_like(ids)
    hidden = sess.run(None, feeds)[0]
    m = mask[..., None].astype(np.float32)
    vec = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
    return vec / np.linalg.norm(vec, axis=1, keepdims=True)


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS vec (h TEXT PRIMARY KEY, text TEXT, v BLOB)")
    return con


def _h(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _vectors(texts: list[str]) -> np.ndarray:
    """Vectors for these texts, embedding only new ones; drops vectors of texts that no longer exist."""
    with _lock, closing(_db()) as con, con:   # closing(): sqlite's own "with" only commits, never closes
        have = {h: v for h, v in con.execute("SELECT h, v FROM vec")}
        hashes = [_h(t) for t in texts]
        new = [(h, t) for h, t in dict(zip(hashes, texts)).items() if h not in have]
        for i in range(0, len(new), 16):
            chunk = new[i:i + 16]
            for (h, t), v in zip(chunk, embed([t for _, t in chunk])):
                blob = v.astype(np.float32).tobytes()
                con.execute("INSERT OR REPLACE INTO vec VALUES (?, ?, ?)", (h, t, blob))
                have[h] = blob
        gone = set(have) - set(hashes)
        con.executemany("DELETE FROM vec WHERE h = ?", [(h,) for h in gone])
    return np.stack([np.frombuffer(have[h], dtype=np.float32) for h in hashes]) if texts else np.zeros((0, 384))


_STOP = {"что", "это", "мне", "меня", "мой", "моя", "мое", "мои", "был", "была", "было", "про", "как", "какой",
         "какая", "какие", "какое", "тебе", "говорил", "скажи", "напомни", "помнишь", "у", "от", "для", "мы"}


# words people use for the same thing — the small model doesn't always connect them
SYNONYMS = [
    {"интернет", "вайфай", "вай-фай", "wifi", "wi-fi", "роутер", "сеть"},
    {"подъезд", "домофон", "дверь", "дверь"},
    {"стим", "steam"}, {"ютуб", "youtube", "видео", "ролик", "канал"},
    {"тачка", "машина", "авто", "автомобиль"}, {"почта", "почты", "email", "имейл", "gmail", "мейл"},
    {"телефон", "номер", "мобильный"}, {"праздник", "день рождения", "днюха", "др"},
    {"мама", "мамы", "маме", "мать"}, {"папа", "папы", "отец"},
]


def stem(w: str) -> str:
    return w[:max(4, len(w) - 2)]


def _alts(word: str) -> set[str]:
    out = {stem(word)}
    for group in SYNONYMS:
        if any(stem(word) == stem(g) or word.startswith(stem(g)) for g in group):
            out |= {stem(g) for g in group}
    return out


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[\w-]+", text.lower()) if len(w) > 2 and w not in _STOP]


def mentions(text: str, word: str) -> bool:
    """Does the text talk about this word (or a synonym of it)?"""
    low = text.lower()
    return any(a in low for a in _alts(word.lower()))


def _keyword(query: str, text: str) -> float:
    words = _words(query)
    if not words:
        return 0.0
    return sum(mentions(text, w) for w in words) / len(words)


def search(query: str, texts: list[str], k: int = 3, min_score: float = 0.35) -> list[int]:
    """Indexes of the texts that best match the query by meaning (plus a keyword bonus), best first.

    Cosine: unrelated ≈ 0.0-0.25, paraphrase ≈ 0.3-0.8. 0.35 = "clearly about it" (safe to give the brain as
    context); an explicit "что я говорил про …" may go lower, since the user asked for memory.
    """
    if not texts or not query.strip():
        return []
    kw = np.array([_keyword(query, t) for t in texts])
    if available():
        try:
            sem = _vectors(texts) @ embed([query])[0]
            score = sem + 0.25 * kw
            cut = max(min_score, float(score.max()) - 0.12)   # only the clear winners, not "somewhat related"
            order = [int(i) for i in np.argsort(-score) if score[i] >= cut]
            return order[:k]
        except Exception as e:  # noqa: BLE001
            log.warning("Semantic search failed (%s), using keywords", e)
    order = [int(i) for i in np.argsort(-kw, kind="stable") if kw[i] >= 0.5]
    return order[:k]


def warm_up() -> None:
    """Load the model and index existing notes in the background, so the first question is fast."""
    def go():
        try:
            notes = sys.modules.get("jarvis_plugin_notes")
            if notes and available():
                _vectors([n["text"] for n in notes.all_notes()])
        except Exception as e:  # noqa: BLE001
            log.warning("Memory warm-up failed: %s", e)
    threading.Thread(target=go, daemon=True, name="memory-warmup").start()
