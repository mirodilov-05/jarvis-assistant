"""Voice biometrics: tell the owner's voice from others (friends on Discord, TV, Jarvis's own voice).

Model: WeSpeaker ResNet34-LM trained on VoxCeleb (ONNX, 26 MB, models/speaker/). Runs on the CPU with 2 threads,
~30-60 ms per phrase. Features are Kaldi-style 80-dim log-mel filterbanks computed here with numpy (no torch).

data/voiceprint.npz keeps:
  user  — embeddings of the owner's enrollment segments (≈20 s of speech, cut into ~3 s pieces)
  tts_<voice> — Jarvis's own Piper voice, so barge-in can tell "you talking" from "Jarvis heard through the mic".
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

import core

log = logging.getLogger("voiceprint")
MODEL = Path(__file__).parent / "models" / "speaker" / "voxceleb_resnet34_LM.onnx"
FILE = core.DATA / "voiceprint.npz"
SR = 16000
_lock = threading.Lock()
_sess = None
_cache: dict = {}

# Cosine thresholds (calibrated, see README): same speaker ≈ 0.55-0.85, other people ≈ -0.1-0.35.
# Real log of 24 Nov: the owner's «Эй, Джарвис» 0.31 (over music) … 0.67; noise and other voices 0.02 … 0.17.
LENIENT = 0.25   # normal use: rather answer you than miss you
STRICT = 0.38    # in games: friends on voice chat must not trigger Jarvis


# ---------------------------------------------------------------------------
# Features: Kaldi fbank (25 ms Hamming frames, 10 ms shift, pre-emphasis 0.97, 80 mel bins, CMN)
# ---------------------------------------------------------------------------

def _mel(f):
    return 1127.0 * np.log(1.0 + np.asarray(f) / 700.0)


def _mel_banks(n_mels: int = 80, n_fft: int = 512, low: float = 20.0, high: float = SR / 2) -> np.ndarray:
    lo, hi = _mel(low), _mel(high)
    delta = (hi - lo) / (n_mels + 1)
    mels = _mel(np.arange(n_fft // 2) * SR / n_fft)
    banks = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(n_mels):
        left, center, right = lo + m * delta, lo + (m + 1) * delta, lo + (m + 2) * delta
        up = (mels - left) / (center - left)
        down = (right - mels) / (right - center)
        banks[m, :n_fft // 2] = np.maximum(0, np.minimum(up, down))
    return banks


_BANKS = _mel_banks()
_WIN = np.hamming(400).astype(np.float32)


def fbank(audio: np.ndarray) -> np.ndarray:
    x = audio.astype(np.float32)          # int16 scale, like Kaldi
    if len(x) < 400:
        x = np.pad(x, (0, 400 - len(x)))
    n = 1 + (len(x) - 400) // 160
    frames = np.lib.stride_tricks.sliding_window_view(x, 400)[::160][:n].astype(np.float32)
    frames = frames - frames.mean(1, keepdims=True)
    pre = frames.copy()
    frames[:, 1:] = pre[:, 1:] - 0.97 * pre[:, :-1]
    frames[:, 0] = pre[:, 0] * (1 - 0.97)
    spec = np.abs(np.fft.rfft(frames * _WIN, 512)) ** 2
    feats = np.log(np.maximum(spec @ _BANKS.T, np.finfo(np.float32).eps))
    return (feats - feats.mean(0)).astype(np.float32)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def _model():
    global _sess
    if _sess is None:
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads, opts.inter_op_num_threads = 2, 1
            _sess = ort.InferenceSession(str(MODEL), opts, providers=["CPUExecutionProvider"])
            log.info("Speaker model loaded")
        except Exception as e:  # noqa: BLE001
            log.warning("Speaker model unavailable: %s", e)
            _sess = False
    return _sess


def embed(audio: np.ndarray) -> np.ndarray | None:
    """256-dim L2-normalised voice embedding of up to the last 8 s of 16 kHz int16 audio."""
    sess = _model()
    if not sess or len(audio) < SR * 0.5:
        return None
    feats = fbank(audio[-SR * 8:])
    with _lock:
        v = sess.run(None, {"feats": feats[None]})[0][0]
    return v / (np.linalg.norm(v) + 1e-9)


def resample(audio: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return audio
    t = np.arange(0, len(audio) / sr, 1 / SR)
    return np.interp(t, np.arange(len(audio)) / sr, audio.astype(np.float32)).astype(np.int16)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _load() -> dict:
    if "data" not in _cache:
        try:
            with np.load(FILE) as z:
                _cache["data"] = {k: z[k] for k in z.files}
        except Exception:  # noqa: BLE001
            _cache["data"] = {}
    return _cache["data"]


def _save(data: dict) -> None:
    _cache["data"] = data
    np.savez(FILE, **data)


def enrolled() -> bool:
    return "user" in _load()


def forget() -> None:
    data = {k: v for k, v in _load().items() if k != "user"}
    _save(data)


def segments(audio: np.ndarray, seconds: float = 3.0) -> list[np.ndarray]:
    step = int(SR * seconds)
    return [audio[i:i + step] for i in range(0, len(audio) - step // 2, step)]


def enroll(audio: np.ndarray) -> int:
    """Remember the owner's voice from a long recording of their speech. Returns how many pieces were used."""
    embs = [e for e in (embed(s) for s in segments(audio)) if e is not None]
    if len(embs) < 3:
        return 0
    embs = np.stack(embs)
    centroid = embs.mean(0)
    keep = embs[embs @ (centroid / np.linalg.norm(centroid)) > 0.5]   # drop pieces with coughs/noise/other people
    if len(keep) < 3:
        keep = embs
    _save({**_load(), "user": keep.astype(np.float32)})
    log.info("Voice enrolled from %d pieces", len(keep))
    return len(keep)


def _score(emb: np.ndarray, ref: np.ndarray) -> float:
    centroid = ref.mean(0)
    centroid /= np.linalg.norm(centroid)
    top = np.sort(ref @ emb)[-3:].mean()     # closest enrollment pieces + the average voice
    return float(0.5 * (emb @ centroid) + 0.5 * top)


def user_score(audio: np.ndarray) -> float | None:
    data = _load()
    if "user" not in data:
        return None
    emb = embed(audio)
    return None if emb is None else _score(emb, data["user"])


def is_owner(audio: np.ndarray, strict: bool = False) -> tuple[bool, float | None]:
    """(accept, score). Accepts everything while no voice is enrolled or the audio is too short to judge."""
    s = user_score(audio)
    if s is None:
        return True, None
    return s >= (STRICT if strict else LENIENT), s


def set_tts_voice(name: str, audio: np.ndarray, sr: int) -> None:
    emb = embed(resample(audio, sr))
    if emb is not None:
        _save({**_load(), f"tts_{name}": emb[None].astype(np.float32)})


def tts_score(audio: np.ndarray, name: str) -> float | None:
    ref = _load().get(f"tts_{name}")
    emb = embed(audio) if ref is not None else None
    return None if emb is None else _score(emb, ref)
