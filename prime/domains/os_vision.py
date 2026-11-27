"""Screen and window awareness. Reading the screen is READ_ONLY; controlling the mouse/keyboard is not offered here.

Capture needs the `mss` package. Without it the function says so instead of failing.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

log = logging.getLogger("prime.vision")


def capture_png(max_side: int = 1280) -> bytes:
    """PNG of the whole screen, scaled down. Raises RuntimeError if capture is unavailable."""
    try:
        import mss
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("для снимка экрана нужны пакеты mss и Pillow") from e
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def describe_request(png: bytes, question: str) -> dict[str, Any]:
    """Payload for a vision-capable model: the image and the question. The caller sends it through the router."""
    return {"question": question,
            "image": {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                  "data": base64.b64encode(png).decode("ascii")}}}
