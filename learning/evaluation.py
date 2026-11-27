"""Is it learning? Numbers the owner can read: corrections, lessons, and the main one, repeat_mistake_rate.

repeat_mistake_rate = corrections where the owner repeats something already corrected before, out of all corrections, in %.
If it does not go down over the weeks, the learning is not working.
"""
from __future__ import annotations

from learning import store


def metrics(path=None) -> dict:
    rows = store.recent_feedback(2000, path)
    rows.reverse()
    corrections = [r for r in rows if r["rating"] == -1 or r["severity"] > 0]
    seen: list[str] = []
    repeats = 0
    for c in corrections:
        if any(store.similarity(c["user_text"], s) > 0.5 for s in seen):
            repeats += 1
        seen.append(c["user_text"])
    up = sum(1 for r in rows if r["rating"] == 1)
    down = sum(1 for r in rows if r["rating"] == -1)
    lessons = store.lessons(500, path)
    return {
        "feedback_total": len(rows), "thumbs_up": up, "thumbs_down": down,
        "corrections_detected": len(corrections),
        "lessons_learned": len(lessons),
        "repeat_mistake_rate": round(100 * repeats / len(corrections), 1) if corrections else 0.0,
        "repeats": repeats,
    }
