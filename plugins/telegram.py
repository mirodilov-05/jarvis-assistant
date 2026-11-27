"""Telegram (your own account via Telethon): unread chats, read a chat, send messages.

Connect in the app: Connections → Telegram (api_id/api_hash from my.telegram.org,
then phone number and the login code Telegram sends you).
The session is stored in data/telegram.session — keep it private.

One client lives in one background thread with its own event loop. Every call goes through run(),
so there is never a second client on the same session file, and no loop is ever created per request.
"""

import asyncio
import difflib
import re
import threading
import time
from pathlib import Path

import connections
import core
from core import Ctx, plural_ru, skill

SESSION = str(core.DATA / "telegram")
_login: dict = {}
_auth: dict = {"ok": None, "t": 0.0, "warned": False}
_loop_lock = threading.Lock()
_state: dict = {"loop": None, "client": None, "key": None}


# ---- the single client -----------------------------------------------------

def _ensure_loop() -> asyncio.AbstractEventLoop:
    with _loop_lock:
        if _state["loop"] is None or not _state["loop"].is_running():
            ready = threading.Event()

            def runner():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                _state["loop"] = loop
                ready.set()
                loop.run_forever()

            threading.Thread(target=runner, daemon=True, name="telegram-user").start()
            ready.wait(5)
        return _state["loop"]


async def _get_client():
    api_id, api_hash = connections.telegram_creds()
    if not api_id or not api_hash:
        raise RuntimeError("нет api_id и api_hash: введите их в Подключениях")
    key = (str(api_id), api_hash)
    if _state["client"] is None or _state["key"] != key:
        from telethon import TelegramClient
        if _state["client"] is not None:
            await _state["client"].disconnect()
        _state["client"] = TelegramClient(SESSION, int(api_id), api_hash)
        _state["key"] = key
    client = _state["client"]
    if not client.is_connected():
        await client.connect()
    return client


def run(fn, timeout: float = 60):
    """Runs `async def fn(client)` on the Telegram thread and returns its result."""
    loop = _ensure_loop()

    async def wrapper():
        return await fn(await _get_client())
    return asyncio.run_coroutine_threadsafe(wrapper(), loop).result(timeout)


# ---- status ----------------------------------------------------------------

def _has_login() -> bool:
    api_id, api_hash = connections.telegram_creds()
    return bool(api_id and api_hash and Path(SESSION + ".session").exists() and _login.get("ok", True))


def connected() -> bool:
    """Does Telegram still accept this login? Asked at most every ten minutes (an hour after a refusal)."""
    if not _has_login():
        return False
    age = time.time() - _auth["t"]
    if _auth["ok"] is False and age < 3600:
        return False
    if _auth["ok"] is True and age < 600:
        return True
    try:
        ok = bool(run(lambda c: c.is_user_authorized(), timeout=8))   # a slow network must not hold a voice reply
    except Exception:  # noqa: BLE001 — offline: keep the last answer
        return bool(_auth["ok"]) if _auth["ok"] is not None else True
    _auth.update(ok=ok, t=time.time())
    if not ok and not _auth["warned"]:
        _auth["warned"] = True
        core.log.warning("Telegram account session is no longer authorised — log in again in Подключения")
    if ok:
        _auth["warned"] = False
    return ok


# ---- login flow used by the app ------------------------------------------

_RU_ERRORS = {
    "SendCodeUnavailableError": "Telegram уже несколько раз отправлял код на этот номер и пока больше не отправит. "
                                "Код приходит в само приложение Telegram, в чат «Telegram», а не по SMS. "
                                "Найдите последний код там или подождите 1–2 часа и запросите снова.",
    "PhoneNumberInvalidError": "Номер не подходит. Введите его полностью, с кодом страны, например +998901234567.",
    "PhoneNumberBannedError": "Этот номер заблокирован в Telegram.",
    "PhoneCodeInvalidError": "Код неверный. Проверьте цифры в чате «Telegram» и введите снова.",
    "PhoneCodeExpiredError": "Код устарел. Нажмите «Отправить код» ещё раз и сразу введите новый.",
    "PhoneCodeEmptyError": "Введите код из чата «Telegram».",
    "PasswordHashInvalidError": "Пароль двухэтапной проверки неверный.",
    "ApiIdInvalidError": "api_id или api_hash неверные. Возьмите их заново на my.telegram.org.",
    "AuthRestartError": "Telegram попросил начать вход заново. Нажмите «Отправить код» ещё раз.",
}


def explain(e: Exception) -> str:
    """A Telegram error in plain Russian, with what to do."""
    name = type(e).__name__
    secs = getattr(e, "seconds", None)
    if name.startswith("Flood") and secs:
        return f"Слишком много попыток. Telegram разрешит снова через {max(1, round(secs / 60))} мин."
    if name in _RU_ERRORS:
        return _RU_ERRORS[name]
    if isinstance(e, (TimeoutError, ConnectionError, OSError)):
        return "Нет связи с Telegram. Проверьте интернет и попробуйте ещё раз."
    return f"Telegram ответил ошибкой: {e}"


def _login_call(go, timeout: float) -> str:
    try:
        return run(go, timeout=timeout)
    except Exception as e:  # noqa: BLE001 — shown to the owner as a clear sentence
        core.log.warning("Telegram login: %s: %s", type(e).__name__, e)
        raise RuntimeError(explain(e)) from e


def login_send_code(phone: str) -> str:
    async def go(c):
        if await c.is_user_authorized():
            return "already"
        sent = await c.send_code_request(phone)
        _login.update(phone=phone, hash=sent.phone_code_hash)
        return "code_sent"
    return _login_call(go, 60)


def login_sign_in(code: str = "", password: str = "") -> str:
    from telethon.errors import SessionPasswordNeededError

    async def go(c):
        if password:
            await c.sign_in(password=password)
        else:
            try:
                await c.sign_in(phone=_login.get("phone"), code=code, phone_code_hash=_login.get("hash"))
            except SessionPasswordNeededError:
                return "password_needed"
        me = await c.get_me()
        _auth.update(ok=True, t=time.time())
        _login.clear()
        return f"ok:{me.first_name or ''}"
    return _login_call(go, 90)


def logout() -> None:
    async def go(c):
        try:
            await c.log_out()
        finally:
            await c.disconnect()
    try:
        run(go, timeout=30)
    except Exception:  # noqa: BLE001 — the session file is removed below in any case
        pass
    _state["client"] = None
    _state["key"] = None
    _auth.update(ok=None, t=0.0)
    for suffix in (".session", ".session-journal"):
        Path(SESSION + suffix).unlink(missing_ok=True)


# ---- data ----------------------------------------------------------------

def _text(msg, lang: str) -> str:
    if msg is None:
        return ""
    if msg.message:
        return re.sub(r"\s+", " ", msg.message)[:200]
    return ("вложение" if lang == "ru" else "fayl") if msg.media else ""


def unread_dialogs(limit: int = 100) -> list[dict]:
    async def go(c):
        dialogs = [d for d in await c.get_dialogs(limit=limit) if d.unread_count > 0 and not d.archived]
        return [{"name": d.name, "unread": d.unread_count, "last": _text(d.message, "ru"),
                 "is_user": d.is_user, "muted": bool(getattr(d.dialog.notify_settings, "mute_until", None))}
                for d in dialogs]
    return run(go)


def summary(lang: str, detailed: bool = True) -> str:
    if not connected():
        return ""
    try:
        dialogs = unread_dialogs()
    except Exception as e:  # noqa: BLE001
        return ("Телеграм сейчас недоступен." if lang == "ru" else "Telegram hozir ishlamayapti.") + f" ({str(e)[:60]})."
    if not dialogs:
        return "В Телеграме непрочитанных нет." if lang == "ru" else "Telegramda o'qilmagan xabar yo'q."
    personal = [d for d in dialogs if d["is_user"] and not d["muted"]]
    total = sum(d["unread"] for d in dialogs)
    if lang == "ru":
        s = f"В Телеграме {total} {plural_ru(total, 'непрочитанное сообщение', 'непрочитанных сообщения', 'непрочитанных сообщений')}"
        s += f", личных чатов: {len(personal)}." if personal else "."
    else:
        s = f"Telegramda {total} ta o'qilmagan xabar" + (f", shaxsiy chatlar: {len(personal)} ta." if personal else ".")
    if detailed:
        top = (personal or dialogs)[:4]
        s += " " + ". ".join(f"{d['name']}: {d['last']}" for d in top) + "."
    return s


async def find_dialog(client, who: str):
    dialogs = await client.get_dialogs(limit=300)
    names = {d.name.lower(): d for d in dialogs if d.name}
    key = who.lower().strip()
    variants = {key, re.sub(r"(е|у|ю|ой|ей|и|ga|ka|qa|ni)$", "", key), re.sub(r"(е|у|ю)$", "а", key)}
    for v in variants:
        for n, d in names.items():
            if v and (n == v or n.startswith(v) or v in n.split()):
                return d
    for v in variants:
        close = difflib.get_close_matches(v, list(names), n=1, cutoff=0.6)
        if close:
            return names[close[0]]
    return None


def read_chat(who: str, lang: str, limit: int = 5) -> str:
    async def go(c):
        d = await find_dialog(c, who)
        if d is None:
            return None, []
        count = max(1, min(d.unread_count or limit, 10))
        msgs = list(reversed(await c.get_messages(d.entity, limit=count)))
        senders = {}
        for m in msgs:
            if not m.out:
                senders[m.id] = (await m.get_sender())
        if d.unread_count:
            await c.send_read_acknowledge(d.entity)
        return d, [(m, senders.get(m.id)) for m in msgs]
    d, msgs = run(go)
    if d is None:
        return f"Не нашёл чат «{who}»." if lang == "ru" else f"«{who}» chati topilmadi."
    lines = []
    for m, sender in msgs:
        name = ("вы" if lang == "ru" else "siz") if m.out else (getattr(sender, "first_name", None) or d.name)
        lines.append(f"{name}: {_text(m, lang)}")
    return (f"Чат {d.name}. " if lang == "ru" else f"{d.name} chati. ") + ". ".join(lines) + "."


def resolve_name(who: str) -> str | None:
    async def go(c):
        d = await find_dialog(c, who)
        return d.name if d else None
    return run(go)


def send(who: str, text: str) -> str:
    async def go(c):
        d = await find_dialog(c, who)
        if d is None:
            raise RuntimeError(f"чат «{who}» не найден")
        await c.send_message(d.entity, text)
        return d.name
    return run(go)


def _not_ready(ctx: Ctx):
    if connected():
        return None
    return ctx.t("Телеграм не подключён. Откройте окно Джарвиса → «Подключения» → Telegram.",
                 "Telegram ulanmagan. Jarvis oynasi → «Подключения» → Telegram.")


@skill(
    "telegram.unread",
    title={"ru": "Непрочитанные сообщения в Telegram", "uz": "Telegramdagi o'qilmagan xabarlar"},
    patterns={
        "ru": [r"(телеграм|телеге)\w*.*(прочитай|сколько|проверь|есть|новые|новых|покажи|непрочитан|что)",
               r"(прочитай|сколько|проверь|есть|новые|новых|покажи|непрочитан)\w*.*(телеграм|телеге|сообщени|чат)"],
        "uz": [r"(telegram)\w*.*(oqi|nechta|tekshir|bormi|yangi|korsat|qancha)",
               r"(yangi|nechta|oqilmagan) (xabar|sms)"],
    },
    examples={"ru": ["Сколько сообщений в телеграме?"], "uz": ["Telegramda yangi xabarlar bormi?"]},
    priority=47,
)
def unread(ctx: Ctx) -> str:
    return _not_ready(ctx) or summary(ctx.lang)


@skill(
    "telegram.chat",
    title={"ru": "Прочитать переписку с человеком", "uz": "Kishi bilan yozishmani o'qish"},
    patterns={
        "ru": [r"(?:что пишет|что написал|что написала|прочитай (?:сообщения|чат|переписку) (?:от|с|из чата))\s+(.+?)(?: в телеграм\w*)?$"],
        "uz": [r"(.+?) (?:nima yozdi|nima yozgan|dan kelgan xabar\w*)", r"(.+?)(?:ning|dan)? xabarlari\w*\s*(?:ni )?oqi\w*"],
    },
    examples={"ru": ["Что пишет мама?"], "uz": ["Onam nima yozdi?"]},
    priority=46,
)
def chat(ctx: Ctx):
    if re.search(r"(ватсап|whatsapp|vatsap)", ctx.norm):
        return None  # WhatsApp plugin handles it
    return _not_ready(ctx) or read_chat(ctx.group(1), ctx.lang)
