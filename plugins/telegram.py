"""Telegram (your own account via Telethon): unread chats, read a chat, send messages.

Connect in the app: Connections → Telegram (api_id/api_hash from my.telegram.org,
then phone number and the login code Telegram sends you).
The session is stored in data/telegram.session — keep it private.
"""

import asyncio
import difflib
import re
from pathlib import Path

import connections
import core
from core import Ctx, plural_ru, skill

SESSION = str(core.DATA / "telegram")
_login: dict = {}


def _client():
    from telethon.sync import TelegramClient

    api_id, api_hash = connections.telegram_creds()
    if not api_id or not api_hash:
        raise RuntimeError("no api credentials")
    asyncio.set_event_loop(asyncio.new_event_loop())
    return TelegramClient(SESSION, int(api_id), api_hash)


_auth: dict = {"ok": None, "t": 0.0}


def connected() -> bool:
    api_id, api_hash = connections.telegram_creds()
    if not (api_id and api_hash and Path(SESSION + ".session").exists() and _login.get("ok", True)):
        return False
    import time
    if _auth["ok"] is None or time.time() - _auth["t"] > 600:      # does Telegram still accept this login?
        try:
            client = _client()
            client.connect()
            try:
                _auth["ok"] = bool(client.is_user_authorized())
            finally:
                client.disconnect()
        except Exception:  # noqa: BLE001 - offline: assume it still works
            _auth["ok"] = True if _auth["ok"] is None else _auth["ok"]
        _auth["t"] = time.time()
        if not _auth["ok"]:
            core.log.warning("Telegram account session is no longer authorised — log in again in ⚙ → Подключения")
    return bool(_auth["ok"])


# ---- login flow used by the app ------------------------------------------

def login_send_code(phone: str) -> str:
    client = _client()
    client.connect()
    try:
        if client.is_user_authorized():
            return "already"
        sent = client.send_code_request(phone)
        _login.update(phone=phone, hash=sent.phone_code_hash)
        return "code_sent"
    finally:
        client.disconnect()


def login_sign_in(code: str = "", password: str = "") -> str:
    from telethon.errors import SessionPasswordNeededError

    client = _client()
    client.connect()
    try:
        if password:
            client.sign_in(password=password)
        else:
            try:
                client.sign_in(phone=_login.get("phone"), code=code, phone_code_hash=_login.get("hash"))
            except SessionPasswordNeededError:
                return "password_needed"
        me = client.get_me()
        _auth.update(ok=True, t=0.0)
        _login.clear()
        return f"ok:{me.first_name or ''}"
    finally:
        client.disconnect()


def logout() -> None:
    try:
        client = _client()
        client.connect()
        client.log_out()
        client.disconnect()
    except Exception:  # noqa: BLE001
        pass
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
    with _client() as client:
        dialogs = [d for d in client.get_dialogs(limit=limit) if d.unread_count > 0 and not d.archived]
        return [{"name": d.name, "unread": d.unread_count, "last": _text(d.message, "ru"),
                 "is_user": d.is_user, "muted": bool(getattr(d.dialog.notify_settings, "mute_until", None))}
                for d in dialogs]


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


def find_dialog(client, who: str):
    dialogs = client.get_dialogs(limit=300)
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
    with _client() as client:
        d = find_dialog(client, who)
        if d is None:
            return f"Не нашёл чат «{who}»." if lang == "ru" else f"«{who}» chati topilmadi."
        count = max(1, min(d.unread_count or limit, 10))
        msgs = list(reversed(client.get_messages(d.entity, limit=count)))
        client.send_read_acknowledge(d.entity) if d.unread_count else None
    lines = []
    for m in msgs:
        sender = ("вы" if lang == "ru" else "siz") if m.out else (getattr(m.sender, "first_name", None) or d.name)
        lines.append(f"{sender}: {_text(m, lang)}")
    return (f"Чат {d.name}. " if lang == "ru" else f"{d.name} chati. ") + ". ".join(lines) + "."


def resolve_name(who: str) -> str | None:
    with _client() as client:
        d = find_dialog(client, who)
        return d.name if d else None


def send(who: str, text: str) -> str:
    with _client() as client:
        d = find_dialog(client, who)
        if d is None:
            raise RuntimeError(f"чат «{who}» не найден")
        client.send_message(d.entity, text)
        return d.name


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
