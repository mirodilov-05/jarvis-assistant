"""Mood from the sound of the voice, measured against the owner's own usual voice.

Three measures per phrase (16 kHz audio):
  energy   loudness of the voiced frames, in dB
  pitch    the fundamental frequency (F0) by autocorrelation, in Hz, and how much it moves
  rate     syllable-like peaks per second in the loudness envelope

The owner's usual values are kept as a running average (the baseline). A phrase is «tired» when it is quieter
and slower than usual, and «stressed» when it is louder with a jumpier pitch. Nothing is compared with other
people, and nothing is sent anywhere. Without a baseline (the first phrases) no mood is given.
"""
from __future__ import annotations

import numpy as np

from cognition import db

SR = 16000
FRAME = int(0.03 * SR)
HOP = int(0.01 * SR)
MIN_F0, MAX_F0 = 70.0, 320.0
BASELINE_KEYS = ("energy", "f0", "rate", "f0_spread")


def _float(audio: np.ndarray) -> np.ndarray:
    a = np.asarray(audio)
    if a.dtype.kind == "i":
        return a.astype(np.float32) / 32768.0
    return a.astype(np.float32)


def _frames(x: np.ndarray) -> np.ndarray:
    n = 1 + max(0, (len(x) - FRAME) // HOP)
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    return x[idx] if n and len(x) >= FRAME else np.zeros((0, FRAME), dtype=np.float32)


def pitch_of(frame: np.ndarray) -> float | None:
    """F0 of one frame by autocorrelation; None when the frame is not clearly voiced."""
    f = frame - frame.mean()
    if np.sqrt(np.mean(f * f)) < 0.01:
        return None
    ac = np.correlate(f, f, mode="full")[FRAME - 1:]
    lo, hi = int(SR / MAX_F0), min(int(SR / MIN_F0), FRAME - 1)
    if hi <= lo or ac[0] <= 0:
        return None
    k = lo + int(np.argmax(ac[lo:hi]))
    if ac[k] / ac[0] < 0.35:                      # not periodic enough: noise or unvoiced
        return None
    return SR / k


def analyze(audio: np.ndarray) -> dict | None:
    """The three measures of one phrase, or None when there is too little speech to judge."""
    x = _float(audio)
    fr = _frames(x)
    if len(fr) < 10:
        return None
    rms = np.sqrt(np.mean(fr * fr, axis=1) + 1e-12)
    voiced_mask = rms > max(0.01, float(np.percentile(rms, 60)) * 0.8)
    if voiced_mask.sum() < 8:
        return None
    energy = float(20 * np.log10(float(np.mean(rms[voiced_mask])) + 1e-9))
    f0s = [p for p in (pitch_of(f) for f, v in zip(fr, voiced_mask) if v) if p]
    if len(f0s) < 5:
        return None
    f0 = float(np.median(f0s))
    spread = float(np.std(f0s) / f0)
    env = rms.copy()
    k = np.ones(5) / 5.0                           # ~50 ms smoothing
    env = np.convolve(env, k, mode="same")
    thr = float(np.percentile(env, 50)) * 1.15
    peaks = int(np.sum((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] > thr)))
    seconds = len(x) / SR
    return {"energy": round(energy, 2), "f0": round(f0, 1), "f0_spread": round(spread, 3),
            "rate": round(peaks / max(seconds, 0.3), 2)}


def mood_from(now: dict, base: dict) -> str:
    """'усталость', 'стресс' or '' by comparing with the owner's usual values."""
    de = now["energy"] - base["energy"]
    dr = (now["rate"] - base["rate"]) / max(base["rate"], 0.1)
    # about 3.5 dB: the size of the usual change in loudness (Lombard effect) between calm and strained speech
    if de <= -3.5 and dr <= -0.2:
        return "усталость"
    if de >= 3.5 and now["f0_spread"] >= max(0.02, base["f0_spread"] * 1.4):   # jumpy pitch, not a flat voice
        return "стресс"
    return ""


def _load_baseline(path=None) -> dict:
    with db.conn(path) as c:
        row = c.execute("SELECT value FROM relationship WHERE key = 'voice_baseline'").fetchone()
    if not row:
        return {}
    import json
    try:
        return json.loads(row["value"])
    except ValueError:
        return {}


def _save_baseline(base: dict, path=None) -> None:
    import json
    with db.conn(path) as c:
        c.execute("INSERT INTO relationship(key,value) VALUES('voice_baseline',?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                  (json.dumps(base),))


def note(audio: np.ndarray, path=None) -> str:
    """Called for every command. Updates the baseline and, when the voice is clearly off, sets the mood."""
    m = analyze(audio)
    if m is None:
        return ""
    base = _load_baseline(path)
    mood = ""
    if base.get("n", 0) >= 5:
        mood = mood_from(m, base)
        if mood:
            with db.conn(path) as c:
                for key, val in (("last_mood", mood), ("last_mood_at", db.now()), ("last_mood_source", "голос")):
                    c.execute("INSERT INTO relationship(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, val))
    # running average over the usual voice; tired or stressed phrases do not move the baseline
    if not mood:
        n = base.get("n", 0)
        for key in BASELINE_KEYS:
            cur = base.get(key, m[key] if key in m else 0.0)
            base[key] = round(cur + (m[key] - cur) / (n + 1), 4) if n < 50 else round(cur + (m[key] - cur) / 50, 4)
        base["n"] = n + 1
        _save_baseline(base, path)
    return mood
