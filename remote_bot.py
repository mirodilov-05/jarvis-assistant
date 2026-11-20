"""Remote control from your phone: a private Telegram bot that obeys only your Telegram ID.

Set up (in the Jarvis window → ⚙ → Telegram-бот):
  1. In Telegram open @BotFather → /newbot → copy the token.
  2. Paste the token, then send any message to your new bot: Jarvis shows your ID — press «Это я».
Messages from anyone else are ignored (and logged).

Commands from the phone:
  /screen — screenshot        /status — CPU, RAM, video memory, battery, active window, game
  /run <программа>            /close_game — close the running game (asks first)
  /shutdown — power off in a minute (asks first)        /cancel — cancel the power-off
  any other text — a normal command to Jarvis («добавь дело …», «какая погода», «громче», «да» / «нет»)

Uses the plain Bot API over HTTPS with requests (long polling) — no extra packages.
The token is stored in Windows Credential Manager ("telegram_bot:token").
"""

from __future__ import annotations

import ctypes
import json
import logging
import subprocess
import threading
import time

import requests

import connections
import core

log = logging.getLogger("remote_bot")
API = "https://api.telegram.org/bot{token}/{method}"
STATE = {"running": False, "error": "", "last_stranger": None, "username": ""}
_stop = threading.Event()
_thread: threading.Thread | None = None
_http = requests.Session()


def token() -> str:
    return connections.get_secret("telegram_bot:token")


def owner_id() -> int:
    try:
        return int(core.setting("remote", "owner_id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def call(method: str, http_timeout: float = 30, files=None, **params):
    r = _http.post(API.format(token=token(), method=method), data=params if files else None,
                   json=None if files else params, files=files, timeout=http_timeout)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", f"HTTP {r.status_code}"))
    return data["result"]


def send(chat: int, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
    params = {"chat_id": chat, "text": (text or "Готово.")[:4000]}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
    call("sendMessage", **params)


# ---------------------------------------------------------------------------
# What the bot can do
# ---------------------------------------------------------------------------

def _screen_png() -> bytes:
    """The whole primary screen as PNG (not saved anywhere)."""
    import vision
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    old = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        src = user32.GetDC(0)
        mem = gdi32.CreateCompatibleDC(src)
        bmp = gdi32.CreateCompatibleBitmap(src, w, h)
        gdi32.SelectObject(mem, bmp)
        gdi32.BitBlt(mem, 0, 0, w, h, src, 0, 0, 0x00CC0020 | 0x40000000)
        bih = vision._BIH(biSize=ctypes.sizeof(vision._BIH), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, src)
    finally:
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old) if old else ctypes.c_void_p(-1))
    import numpy as np
    img = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4)[:, :, 2::-1]
    return vision.png(vision.shrink(img, 1400))


def _local(path: str) -> dict:
    try:
        return requests.get("http://127.0.0.1:50778" + path, timeout=5).json()
    except Exception:  # noqa: BLE001
        return {}


def status_text() -> str:
    t = _local("/api/telemetry")
    s = _local("/api/state")
    lines = [f"🖥 Процессор {t.get('cpu', '?')}%"]
    if t.get("ram"):
        lines.append(f"🧠 ОЗУ {t['ram']['used_gb']} из {t['ram']['total_gb']} ГБ")
    if t.get("gpu"):
        g = t["gpu"]
        lines.append(f"🎮 Видеопамять {g['vram_used'] / 1024:.1f} из {g['vram_total'] / 1024:.1f} ГБ · {g['util']}% · {g['temp']}°C")

    class _PS(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("pct", ctypes.c_byte), ("saver", ctypes.c_byte),
                    ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
    ps = _PS()
    if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(ps)) and ps.pct != -1 and ps.pct <= 100:
        lines.append(f"🔋 Батарея {ps.pct}%" + (" · заряжается" if ps.ac == 1 else ""))
    try:
        import pcx
        _, title, exe = pcx.foreground()
        lines.append(f"🪟 Активное окно: {title or exe or '—'}")
    except Exception:  # noqa: BLE001
        pass
    game = (s.get("game") or {})
    lines.append(f"🕹 Игра: {game.get('name')}" if game.get("on") else "🕹 Игр не запущено")
    lines.append(f"🤖 Джарвис: {s.get('status', 'не отвечает')}")
    return "\n".join(lines)


HELP = ("Я Джарвис на вашем ноутбуке. Команды:\n/screen — скриншот\n/status — состояние ПК\n/run программа — запустить\n"
        "/close_game — закрыть игру\n/shutdown — выключить ПК\n/cancel — отменить выключение\n"
        "Или просто напишите, как Джарвису: «добавь дело …», «громче», «какая погода».")


def handle_text(chat: int, text: str) -> None:
    low = text.strip().lower()
    cmd = low.split()[0] if low else ""
    if cmd in ("/start", "/help", "помощь"):
        send(chat, HELP)
    elif cmd in ("/screen", "скриншот", "/screenshot", "экран"):
        png = _screen_png()
        call("sendPhoto", http_timeout=60, files={"photo": ("screen.png", png, "image/png")}, chat_id=chat)
    elif cmd in ("/status", "статус"):
        send(chat, status_text())
    elif cmd == "/run":
        what = text.strip()[4:].strip()
        send(chat, core.route(f"открой {what}", "ru", "телеграм", core.CONFIG) if what else "Напишите: /run telegram")
    elif cmd in ("/close_game", "закрой игру"):
        game = (_local("/api/state").get("game") or {})
        if not game.get("on"):
            send(chat, "Сейчас игра не запущена.")
        else:
            send(chat, f"Закрыть {game['name']}? Несохранённый прогресс пропадёт.",
                 [[("Да, закрыть", f"kill:{game['name']}"), ("Нет", "no")]])
    elif cmd in ("/shutdown", "выключи компьютер", "выключи пк"):
        send(chat, "Выключить компьютер через минуту?", [[("Да, выключить", "shutdown"), ("Нет", "no")]])
    elif cmd in ("/cancel", "отмена"):
        subprocess.run(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)
        send(chat, "Выключение отменено.")
    else:
        reply = core.route(text, "ru", "телеграм", core.CONFIG)
        reply = core.styled(reply, "ru") if hasattr(core, "styled") else reply
        send(chat, reply or "Готово.")
    core.emit({"type": "message", "role": "user", "text": "📱 " + text, "lang": "ru", "source": "телеграм"})


def handle_button(chat: int, data: str) -> str:
    if data == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "60"], creationflags=subprocess.CREATE_NO_WINDOW)
        return "Компьютер выключится через минуту. /cancel — отменить."
    if data.startswith("kill:"):
        name = data[5:]
        r = subprocess.run(["taskkill", "/IM", name, "/F"], capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return f"Закрыл {name}." if r.returncode == 0 else f"Не получилось закрыть {name}."
    return "Отменено."


# ---------------------------------------------------------------------------
# Long polling
# ---------------------------------------------------------------------------

def _loop() -> None:
    offset = 0
    STATE.update(running=True, error="")
    try:
        STATE["username"] = call("getMe", http_timeout=10).get("username", "")
        log.info("Telegram bot @%s started", STATE["username"])
    except Exception as e:  # noqa: BLE001
        STATE.update(running=False, error=str(e)[:200])
        log.warning("Telegram bot can't start: %s", e)
        return
    while not _stop.is_set():
        try:
            updates = call("getUpdates", http_timeout=40, offset=offset, timeout=30)   # long polling
        except Exception as e:  # noqa: BLE001
            STATE["error"] = str(e)[:200]
            time.sleep(5)
            continue
        STATE["error"] = ""
        for u in updates:
            offset = u["update_id"] + 1
            try:
                _dispatch(u)
            except Exception as e:  # noqa: BLE001
                log.exception("Telegram update failed")
                chat = (u.get("message") or u.get("callback_query", {}).get("message") or {}).get("chat", {}).get("id")
                if chat and chat == owner_id():
                    try:
                        send(chat, "Ошибка: " + str(e)[:200])
                    except Exception:  # noqa: BLE001
                        pass
    STATE["running"] = False


def _dispatch(u: dict) -> None:
    owner = owner_id()
    if "callback_query" in u:
        q = u["callback_query"]
        if q["from"]["id"] != owner:
            return
        answer = handle_button(q["message"]["chat"]["id"], q.get("data", ""))
        call("answerCallbackQuery", callback_query_id=q["id"])
        call("editMessageText", chat_id=q["message"]["chat"]["id"], message_id=q["message"]["message_id"], text=answer)
        return
    msg = u.get("message") or {}
    sender, chat = msg.get("from", {}), msg.get("chat", {})
    if not sender or chat.get("type") != "private":
        return
    if not owner:   # not linked yet: show who wrote, the owner confirms in the Jarvis window
        STATE["last_stranger"] = {"id": sender["id"], "name": " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])),
                                  "username": sender.get("username", "")}
        core.emit({"type": "remote", "pending": STATE["last_stranger"]})
        send(chat["id"], "Бот ещё не привязан. Откройте окно Джарвиса → ⚙ → Telegram-бот и нажмите «Это я».")
        return
    if sender["id"] != owner:
        log.warning("Telegram bot: ignored a message from id %s (@%s)", sender["id"], sender.get("username", ""))
        return
    text = msg.get("text") or ""
    if text:
        handle_text(chat["id"], text)


def start() -> None:
    global _thread
    if not token() or not core.setting("remote", "enabled", True):
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="telegram-bot")
    _thread.start()


def restart() -> None:
    stop()
    if _thread:
        _thread.join(timeout=45)
    start()


def stop() -> None:
    _stop.set()


def status() -> dict:
    return {"has_token": bool(token()), "owner_id": owner_id(), "running": STATE["running"], "error": STATE["error"],
            "username": STATE["username"], "pending": STATE["last_stranger"],
            "enabled": bool(core.setting("remote", "enabled", True))}
