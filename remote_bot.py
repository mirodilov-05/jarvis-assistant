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
import re
import sys
import logging
import subprocess
import threading
import time

import requests
from pathlib import Path

import connections
import core

log = logging.getLogger("remote_bot")
API = "https://api.telegram.org/bot{token}/{method}"
STATE = {"running": False, "error": "", "last_stranger": None, "username": "", "auth_error": False}
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


class AuthError(RuntimeError):
    """Telegram refused the token (401). Retrying cannot help: the owner must paste a new one."""


def call(method: str, http_timeout: float = 30, files=None, **params):
    r = _http.post(API.format(token=token(), method=method), data=params if files else None,
                   json=None if files else params, files=files, timeout=http_timeout)
    if r.status_code == 401:
        raise AuthError("токен не принят Telegram")
    data = r.json()
    if not data.get("ok"):
        if data.get("error_code") == 401:
            raise AuthError("токен не принят Telegram")
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


HELP = ("Я Джарвис на вашем ноутбуке. Пишите или говорите голосовым — отвечу голосом.\n"
        "Например: «найди, какие рилсы про нейросети залетели за ночь», «пиши сценарий под меня», «напомни в 8 вечера снять видео».\n\n"
        "Скиньте мне файл или фото — сохраню на ноутбуке. «Скинь файл договор» — пришлю файл с ноутбука.\n"
        "Каждое утро в 8:00 — сводка: погода, дела, напоминания.\n\n"
        "Команды:\n/screen — скриншот\n/status — состояние ПК\n/run программа — запустить\n"
        "/close_game — закрыть игру\n/shutdown — выключить ПК\n/cancel — отменить выключение\n"
        "Или просто напишите, как Джарвису: «добавь дело …», «громче», «какая погода».")


def answer(chat: int, text: str, voice: bool = False) -> None:
    """Reply in text; to a voice message also with Jarvis's voice (Telegram voice note)."""
    LAST_SENT.update(kind="text", text=text or "")
    send(chat, text or "Готово.")
    if voice and text and core.setting("remote", "voice_replies", True):
        try:
            ogg = voice_note(text)
            if ogg:
                call("sendVoice", http_timeout=60, files={"voice": ("jarvis.ogg", ogg, "audio/ogg")}, chat_id=chat)
        except Exception as e:  # noqa: BLE001
            log.warning("voice reply failed: %s", e)


# in the bot «скрин» means: send the picture HERE (not save it on the laptop)
_SCREEN = re.compile(r"(скрин\w*|скриншот\w*|снимок экрана|сфоткай экран|сфотографируй экран|покажи (?:мне )?экран|"
                     r"что (?:у меня |сейчас )?на (?:экране|ноуте|компе|ноутбуке))", re.I)
_SEND_HERE = re.compile(r"^(?:джарвис,?\s*)?(?:отправь|скинь|пришли|кинь|перешли)(?: мне)?(?: это| его| её| ее| результат| ответ| скрин\w*)?"
                        r"\s*(?:сюда|в этот чат|в чат|мне|в телег\w*|в телеграм\w*|в тг)?\s*$", re.I)
LAST_SENT: dict = {"kind": "", "data": b"", "text": ""}
_FILE_RE = re.compile(r"(?:скинь|отправь|пришли|кинь|дай)(?: мне)?(?: сюда)? (?:файл|документ|фото|видео|презентаци\w*|таблиц\w*)\s+(.+)$", re.I)
INBOX = Path.home() / "Downloads" / "Jarvis"


def send_file(chat: int, query: str) -> None:
    desktop = sys.modules.get("jarvis_plugin_desktop")
    hits = desktop.find_files(query.strip(" .?")) if desktop else []
    hits = [h for h in hits if h.is_file() and h.stat().st_size < 49 * 2**20]       # the Bot API limit is 50 MB
    if not hits:
        send(chat, f"Не нашёл файл «{query}» на ноутбуке (документы, загрузки, рабочий стол, диск D).")
        return
    f = hits[0]
    call("sendDocument", http_timeout=180, files={"document": (f.name, f.read_bytes())}, chat_id=chat,
         caption=f"{f.name}\n{f.parent}"[:1000])
    if len(hits) > 1:
        send(chat, "Ещё нашёл: " + "; ".join(h.name for h in hits[1:5]))


def save_incoming(msg: dict) -> str | None:
    """A file or photo you sent to the bot is saved on the laptop in Загрузки\\Jarvis."""
    if msg.get("document"):
        d = msg["document"]
        name = d.get("file_name") or f"file_{d['file_unique_id']}"
        fid = d["file_id"]
    elif msg.get("photo"):
        ph = msg["photo"][-1]                     # the biggest size
        name, fid = f"photo_{time.strftime('%Y-%m-%d_%H-%M-%S')}.jpg", ph["file_id"]
    elif msg.get("video"):
        v = msg["video"]
        name, fid = v.get("file_name") or f"video_{time.strftime('%Y-%m-%d_%H-%M-%S')}.mp4", v["file_id"]
    else:
        return None
    INBOX.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    target = INBOX / safe
    if target.exists():
        target = INBOX / f"{target.stem}_{int(time.time())}{target.suffix}"
    target.write_bytes(_download(fid))
    core.emit({"type": "message", "role": "jarvis", "text": f"📥 С телефона: {target.name}", "lang": "ru", "source": "телеграм"})
    return str(target)


def send_screen(chat: int, caption: str = "") -> None:
    png = _screen_png()
    LAST_SENT.update(kind="photo", data=png)
    call("sendPhoto", http_timeout=60, files={"photo": ("screen.png", png, "image/png")}, chat_id=chat,
         **({"caption": caption[:1000]} if caption else {}))


_WAKE_PC = re.compile(r"^(?:джарвис,?\s*)?(?:включи|разбуди|запусти)(?: мой| мне)? (?:комп\w*|пк|ноут\w*)$", re.I)


def handle_text(chat: int, text: str, voice: bool = False) -> None:
    low = text.strip().lower()
    cmd = low.split()[0] if low else ""
    if _WAKE_PC.match(low.strip(" .!")):
        _wake_screen()
        answer(chat, "Включил. На связи, что делаем?", voice)
    elif cmd in ("/start", "/help", "помощь"):
        send(chat, HELP)
    elif cmd in ("/screen", "/screenshot") or (_SCREEN.search(low) and not re.search(r"\bчто\b", low)):
        send_screen(chat)
    elif _SCREEN.search(low):           # «что у меня на экране?» — the picture and what Jarvis sees on it
        import vision
        try:
            seen = vision.look("Что на экране? Коротко.")
        except Exception as e:  # noqa: BLE001
            seen = f"Не смог рассмотреть: {str(e)[:80]}"
        send_screen(chat, seen)
        if voice:
            answer(chat, seen, voice)
    elif _FILE_RE.search(low):
        send_file(chat, _FILE_RE.search(low).group(1))
    elif _SEND_HERE.match(low.strip(" .!")):   # «отправь это сюда / в этот чат»
        if LAST_SENT["kind"] == "photo" and LAST_SENT["data"]:
            call("sendPhoto", http_timeout=60, files={"photo": ("screen.png", LAST_SENT["data"], "image/png")}, chat_id=chat)
        else:
            creator = sys.modules.get("jarvis_plugin_creator")
            title, text = creator.last_text() if creator and creator.LAST["text"] else ("", LAST_SENT["text"])
            send(chat, (f"📌 {title}\n\n{text}" if title and text else text) or "Пока нечего отправлять.")
    elif cmd in ("/status", "статус"):
        send(chat, status_text())
    elif cmd == "/run":
        what = text.strip()[4:].strip()
        send(chat, core.process(f"открой {what}", "ru", "телеграм") if what else "Напишите: /run telegram")
    elif cmd == "/close_game" or re.match(r"^закрой (игру|игра)$", low.strip(" .!")):
        game = (_local("/api/state").get("game") or {})
        if not game.get("on"):
            send(chat, "Сейчас игра не запущена.")
        else:
            send(chat, f"Закрыть {game['name']}? Несохранённый прогресс пропадёт.",
                 [[("Да, закрыть", f"kill:{game['name']}"), ("Нет", "no")]])
    elif cmd == "/shutdown" or re.match(r"^(выключи|выключить) (компьютер|комп|пк|ноут|ноутбук)$", low.strip(" .!")):
        send(chat, "Выключить компьютер через минуту?", [[("Да, выключить", "shutdown"), ("Нет", "no")]])
    elif cmd in ("/cancel", "отмена") or low.strip(" .!") in ("отмени выключение", "отмени перезагрузку"):
        subprocess.run(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)
        send(chat, "Выключение отменено.")
    else:
        core.emit({"type": "message", "role": "user", "text": "📱 " + text, "lang": "ru", "source": "телеграм"})
        reply = core.process(text, "ru", "телеграм")     # kept in the history and the memory, like a voice command
        answer(chat, reply or "Готово.", voice)
        core.emit({"type": "message", "role": "jarvis", "text": reply or "Готово.", "lang": "ru", "source": "телеграм"})
        return
    core.emit({"type": "message", "role": "user", "text": "📱 " + text, "lang": "ru", "source": "телеграм"})


def _wake_screen() -> None:
    """The laptop is on (the bot runs on it): wake the display if it went dark."""
    import ctypes
    u32 = ctypes.windll.user32
    u32.mouse_event(0x0001, 1, 0, 0, 0)          # tiny mouse move
    u32.mouse_event(0x0001, -1 & 0xFFFFFFFF, 0, 0, 0)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000002 | 0x00000001)


# ---------------------------------------------------------------------------
# Voice messages: in (Groq / local Whisper) and out (Piper -> OGG Opus voice note)
# ---------------------------------------------------------------------------

def _download(file_id: str) -> bytes:
    info = call("getFile", http_timeout=20, file_id=file_id)
    r = _http.get(f"https://api.telegram.org/file/bot{token()}/{info['file_path']}", timeout=60)
    r.raise_for_status()
    return r.content


def _decode_16k(data: bytes):
    import io

    import av
    import numpy as np
    c = av.open(io.BytesIO(data))
    res = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
    pcm = [r.to_ndarray().reshape(-1) for fr in c.decode(audio=0) for r in res.resample(fr)]
    c.close()
    return np.concatenate(pcm).astype(np.int16) if pcm else np.zeros(0, dtype=np.int16)


def transcribe_voice(data: bytes) -> str:
    pcm = _decode_16k(data)
    if len(pcm) < 16000 * 0.3:
        return ""
    main = sys.modules.get("__main__")
    if main and hasattr(main, "transcribe"):
        text, _lang, _ok = main.transcribe(pcm, accurate=True, lang_hint="ru")
        return text
    import cloud
    return cloud.transcribe(pcm, "ru")["text"]


def voice_note(text: str) -> bytes:
    """Jarvis's Piper voice as an OGG/Opus voice note."""
    import io

    import av
    import numpy as np
    main = sys.modules.get("__main__")
    spk = getattr(main, "speaker", None)
    voice = spk._piper_voice(core.setting("voice", "piper_voice_ru", "dmitri")) if spk else None
    if voice is None:
        return b""
    chunks = list(voice.synthesize(re.sub(r"[*#_`>]", "", text)[:900]))
    if not chunks:
        return b""
    pcm = np.concatenate([c.audio_int16_array for c in chunks])
    rate = chunks[0].sample_rate
    buf = io.BytesIO()
    out = av.open(buf, "w", format="ogg")
    st = out.add_stream("libopus", rate=48000)
    st.layout = "mono"
    res = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=48000)
    frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = rate
    for f in res.resample(frame):
        for pkt in st.encode(f):
            out.mux(pkt)
    for pkt in st.encode(None):
        out.mux(pkt)
    out.close()
    return buf.getvalue()


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
    STATE.update(running=True, error="", auth_error=False)
    try:
        STATE["username"] = call("getMe", http_timeout=10).get("username", "")
        log.info("Telegram bot @%s started", STATE["username"])
    except AuthError as e:                       # one short line, no traceback, no reconnect loop
        STATE.update(running=False, error=str(e), auth_error=True)
        log.warning("Telegram bot stopped: %s. Paste a new token in Settings → Keys.", e)
        return
    except Exception as e:  # noqa: BLE001
        STATE.update(running=False, error=str(e)[:200])
        log.warning("Telegram bot can't start: %s", e)
        return
    while not _stop.is_set():
        try:
            updates = call("getUpdates", http_timeout=40, offset=offset, timeout=30)   # long polling
        except AuthError as e:
            STATE.update(running=False, error=str(e), auth_error=True)
            log.warning("Telegram bot stopped: %s", e)
            return
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
    saved = save_incoming(msg) if (msg.get("document") or msg.get("photo") or msg.get("video")) else None
    if saved:
        caption = (msg.get("caption") or "").strip()
        send(chat["id"], f"📥 Сохранил на ноутбуке: {saved}")
        if caption:
            handle_text(chat["id"], caption)
        return
    text = msg.get("text") or ""
    media = msg.get("voice") or msg.get("audio") or msg.get("video_note")
    if media and not text:
        call("sendChatAction", chat_id=chat["id"], action="typing")
        text = transcribe_voice(_download(media["file_id"]))
        if not text:
            send(chat["id"], "Не расслышал, повторите, пожалуйста.")
            return
        send(chat["id"], f"🎙 {text}")
        handle_text(chat["id"], text, voice=True)
        return
    if text:
        handle_text(chat["id"], text)


def _morning_loop() -> None:
    """Every day at [remote] morning (default 08:00): weather, tasks, reminders — in Telegram."""
    while not _stop.is_set():
        time.sleep(30)
        try:
            when = str(core.setting("remote", "morning", "08:00") or "")
            if not when or not owner_id() or not token():
                continue
            now = core.now()
            today = now.strftime("%Y-%m-%d")
            if now.strftime("%H:%M") >= when and core.setting("remote", "morning_sent", "") != today:
                core.save_setting("remote", "morning_sent", today)
                briefing = sys.modules.get("jarvis_plugin_briefing")
                text = briefing.build("ru", greet=True) if briefing else ""
                if text:
                    notify("☀️ " + text)
        except Exception:  # noqa: BLE001
            log.exception("morning summary")


def start() -> None:
    global _thread
    if not token() or not core.setting("remote", "enabled", True):
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="telegram-bot")
    _thread.start()
    threading.Thread(target=_morning_loop, daemon=True, name="telegram-morning").start()


def restart() -> None:
    stop()
    if _thread:
        _thread.join(timeout=45)
    start()


def stop() -> None:
    _stop.set()


def notify(text: str) -> tuple[bool, str]:
    """Send a message to the owner (reminders, «скинь мне в телегу»). -> (sent, reason if not)."""
    if not token():
        return False, "Telegram-бот не подключён: вставьте токен в ⚙ → Telegram-бот."
    if not owner_id():
        return False, "Бот не привязан: напишите ему в Telegram и нажмите «Это я» в ⚙ → Telegram-бот."
    try:
        for i in range(0, len(text), 3900):
            call("sendMessage", chat_id=owner_id(), text=text[i:i + 3900])
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, f"Telegram не ответил: {str(e)[:120]}"


def status() -> dict:
    return {"has_token": bool(token()), "owner_id": owner_id(), "running": STATE["running"], "error": STATE["error"],
            "auth_error": bool(STATE.get("auth_error")),
            "username": STATE["username"], "pending": STATE["last_stranger"],
            "enabled": bool(core.setting("remote", "enabled", True))}
