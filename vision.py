"""Screen vision: "что у меня на экране?", "прочитай ошибку", "переведи это" — only when you ask.

Capture: the active window (or the whole screen when the Jarvis window itself is in front) via Windows GDI with
ctypes — no Pillow (its unsigned DLLs could be blocked by Smart App Control). Encoded as PNG with zlib.
Nothing is written to disk. The picture goes to Google Gemini (V3 cloud mode), or to the local qwen3.5 / Claude.
"""

from __future__ import annotations

import base64
import ctypes
import logging
import struct
import zlib
from ctypes import wintypes

import numpy as np

import core

log = logging.getLogger("vision")
user32, gdi32, dwmapi = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.dwmapi
MAX_SIDE = 1600


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _window() -> tuple[str, tuple[int, int, int, int]]:
    """Title and screen rectangle of what the user is looking at."""
    hwnd = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 256)
    rect = wintypes.RECT()
    ok = hwnd and not user32.IsIconic(hwnd) and dwmapi.DwmGetWindowAttribute(
        hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0           # 9 = frame bounds without the shadow
    screen = (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    if not ok or "Джарвис" in title.value or rect.right - rect.left < 200 or rect.bottom - rect.top < 150:
        return ("весь экран", screen)
    # clip to the primary screen
    l, t = max(rect.left, 0), max(rect.top, 0)
    r, b = min(rect.right, screen[2]), min(rect.bottom, screen[3])
    return (title.value or "окно", (l, t, r, b)) if r - l > 100 and b - t > 100 else ("весь экран", screen)


def capture() -> tuple[str, np.ndarray]:
    """(window title, RGB uint8 image) of the active window."""
    old = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))   # real pixels on scaled (125%/150%) screens
    try:
        title, (l, t, r, b) = _window()
        w, h = r - l, b - t
        src = user32.GetDC(0)
        mem = gdi32.CreateCompatibleDC(src)
        bmp = gdi32.CreateCompatibleBitmap(src, w, h)
        gdi32.SelectObject(mem, bmp)
        gdi32.BitBlt(mem, 0, 0, w, h, src, l, t, 0x00CC0020 | 0x40000000)   # SRCCOPY | CAPTUREBLT
        bih = _BIH(biSize=ctypes.sizeof(_BIH), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, src)
    finally:
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old) if old else ctypes.c_void_p(-1))
    img = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4)[:, :, 2::-1]   # BGRA -> RGB
    return title, img


def shrink(img: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    h, w = img.shape[:2]
    f = -(-max(h, w) // max_side)          # ceil
    if f <= 1:
        return np.ascontiguousarray(img)
    h2, w2 = h // f, w // f
    return img[:h2 * f, :w2 * f].reshape(h2, f, w2, f, 3).mean((1, 3)).astype(np.uint8)


def png(img: np.ndarray) -> bytes:
    h, w = img.shape[:2]
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _is_blank(img: np.ndarray) -> bool:
    return float(img.std()) < 3.0     # e.g. a fullscreen game that GDI can't see


GUIDE = ("\n\nСейчас тебе показан снимок экрана пользователя (окно «{title}»). Отвечай по-русски, 1–3 коротких "
         "предложения, без списков и разметки: ответ читается голосом. Если просят прочитать — прочитай главное "
         "дословно. Если просят перевести — переведи. Если это ошибка — скажи коротко, что она значит и что сделать. "
         "Не выдумывай того, чего не видно.")


def look(question: str) -> str:
    """Take a screenshot of the active window and answer the question about it."""
    import sys
    llm = sys.modules.get("jarvis_plugin_llm")
    title, img = capture()
    if _is_blank(img):
        return "Экран для меня чёрный: так бывает с играми на весь экран. Сверните игру или переключите её в оконный режим."
    small = shrink(img)
    data = base64.b64encode(png(small)).decode()
    thumb = base64.b64encode(png(shrink(img, 360))).decode()
    core.emit({"type": "vision", "title": title, "thumb": thumb})
    system = (llm.system_prompt("ru") if llm else "Ты Джарвис.") + GUIDE.format(title=title)
    q = question.strip() or "Что на экране?"
    log.info("Vision: %r on «%s» %dx%d -> %dx%d", q, title, img.shape[1], img.shape[0], small.shape[1], small.shape[0])
    try:
        import cloud
        if cloud.setting("enabled", True) and cloud.has("gemini"):
            try:
                return (llm._clean(cloud.look(system, q, data)) if llm else cloud.look(system, q, data)) or "Не разобрал, что на экране."
            except Exception:  # noqa: BLE001
                log.exception("Gemini vision failed")
                if not cloud.local_fallback():
                    return "Не получилось связаться с Gemini. Проверьте интернет или ключ."
        elif cloud.enabled() and not cloud.local_fallback():
            return "Для зрения нужен бесплатный ключ Gemini, сэр. Добавьте его в настройках."
        if llm and llm.provider() == "claude":
            try:
                reply = llm._ask_claude(system, [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                    {"type": "text", "text": q}]}], 400)
                return llm._clean(reply)
            except Exception:  # noqa: BLE001
                log.exception("Claude vision failed, using the local model")
        reply = _ask_local(system, q, data)
    except Exception as e:  # noqa: BLE001
        log.exception("Vision failed")
        return "Не получилось рассмотреть экран: " + str(e)[:100]
    return (llm._clean(reply) if llm else reply) or "Не разобрал, что на экране."


def _ask_local(system: str, question: str, image_b64: str) -> str:
    import requests
    cfg = core.CONFIG.get("llm", {})
    r = requests.post(cfg.get("ollama_url", "http://127.0.0.1:11434") + "/api/chat", json={
        "model": cfg.get("vision_model") or cfg.get("model", "qwen3.5:2b-q4_K_M"),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": question, "images": [image_b64]}],
        "stream": False, "think": False, "keep_alive": "2m" if core.CONFIG.get("_game_mode") else "30m",
        "options": {"num_predict": 250, "temperature": 0.2},
    }, timeout=180)
    r.raise_for_status()
    return r.json()["message"]["content"]
