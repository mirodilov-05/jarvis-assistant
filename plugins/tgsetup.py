"""Remote setup and control through your own Telegram «Избранное» (Saved Messages) — works from the phone, away from home.

Your personal Telegram is already connected to Jarvis. Every ~15 s Jarvis looks at NEW messages in «Избранное»
(messages you send to yourself — nobody else can write there):

  • a bot token from @BotFather (123456789:AA…)  -> saved to Windows Credential Manager, the bot starts and is linked
    to YOUR account at once (no «Это я» needed); the answer appears in «Избранное»
  • «Джарвис, …» (any command)                  -> runs on the laptop, the answer appears in «Избранное»

Old messages are never processed: only those sent after Jarvis started watching.
"""

from __future__ import annotations

import re
import sys
import threading
import time

import core

TOKEN_RE = re.compile(r"\b(\d{6,12}:[A-Za-z0-9_-]{30,})\b")
_lock = threading.Lock()


def _tg():
    return sys.modules.get("jarvis_plugin_telegram")


def _reply(text: str) -> None:
    tg = _tg()
    tg.run(lambda c: c.send_message("me", "🤖 Джарвис: " + text[:3900]), timeout=30)


def _setup_bot(me_id: int, token: str) -> str:
    import connections
    import remote_bot
    connections.set_secret("telegram_bot:token", token)
    core.save_setting("remote", "owner_id", int(me_id))       # it came from your own account: you are the owner
    core.save_setting("remote", "enabled", True)
    remote_bot.restart()
    for _ in range(20):
        time.sleep(0.5)
        st = remote_bot.status()
        if st["running"] or st["error"]:
            break
    st = remote_bot.status()
    core.emit({"type": "v3"})
    if st["running"]:
        return (f"✅ Бот @{st['username']} подключён и слушается только вас. Откройте его и напишите /start "
                "или любую команду — можно голосовым.\nСовет: удалите сообщение с токеном из «Избранного».")
    return f"Токен сохранён, но бот не запустился: {st['error'] or 'нет ответа от Telegram'}. Проверьте токен у @BotFather."


def _fetch() -> tuple[int, list[tuple[int, str]]] | None:
    """Your id and the last messages of «Избранное», read on the one shared Telegram client."""
    async def go(c):
        if not await c.is_user_authorized():
            return None
        me = await c.get_me()
        msgs = await c.get_messages("me", limit=8)
        return int(me.id), [(int(m.id), (m.message or "").strip()) for m in msgs]
    return _tg().run(go, timeout=30)


def check_once() -> None:
    tg = _tg()
    if not tg or not tg.connected():
        return
    with _lock:
        got = _fetch()
        if got:
            _check(*got)


def _check(me_id: int, msgs: list[tuple[int, str]]) -> None:
    """New messages only; the commands run here, outside the Telegram thread, so a command may use Telegram too."""
    seen = int(core.setting("remote", "saved_seen", 0) or 0)
    if not seen:      # first run: start from now, never touch old messages
        core.save_setting("remote", "saved_seen", max((i for i, _ in msgs), default=1))
        return
    for mid, text in sorted((m for m in msgs if m[0] > seen), key=lambda m: m[0]):
        core.save_setting("remote", "saved_seen", mid)
        if not text or text.startswith("🤖"):
            continue
        tok = TOKEN_RE.search(text)
        if tok:
            core.log.info("Bot token received from the owner's Saved Messages")
            _reply(_setup_bot(me_id, tok.group(1)))
        elif re.match(r"^(?:джарвис|jarvis)\b", text, re.I):
            cmd = re.sub(r"^(?:джарвис|jarvis)[,!\s]*", "", text, flags=re.I)
            core.emit({"type": "message", "role": "user", "text": "📱 " + text, "lang": "ru", "source": "телеграм"})
            reply = core.process(cmd, "ru", "телеграм") or "Готово."
            core.emit({"type": "message", "role": "jarvis", "text": reply, "lang": "ru", "source": "телеграм"})
            _reply(reply)


@core.on_start
def _watch() -> None:
    if getattr(_watch, "started", False):
        return
    _watch.started = True

    def loop():
        time.sleep(10)
        while True:
            try:
                check_once()
            except Exception as e:  # noqa: BLE001
                core.log.warning("Saved Messages watcher: %s", e)
                time.sleep(30)
            time.sleep(15)
    threading.Thread(target=loop, daemon=True, name="tg-saved").start()
