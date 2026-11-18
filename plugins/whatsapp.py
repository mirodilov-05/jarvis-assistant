"""WhatsApp via the local Node bridge (whatsapp-bridge/bridge.js, linked device).

Enable in the app: Connections → WhatsApp → scan the QR code with your phone
(WhatsApp → Linked devices). Unofficial client: WhatsApp may restrict accounts
that use unofficial clients; use at your own risk.
"""

import re
import subprocess
import time
from pathlib import Path

import requests

import connections
import core
from core import Ctx, plural_ru, skill

URL = "http://127.0.0.1:50779"
BRIDGE_DIR = Path(__file__).resolve().parents[1] / "whatsapp-bridge"
_proc: dict = {}


def enabled() -> bool:
    return bool(connections.load()["whatsapp"].get("enabled"))


def status() -> dict:
    try:
        return requests.get(URL + "/status", timeout=3).json()
    except Exception:  # noqa: BLE001
        return {"state": "off" if not enabled() else "starting", "qr": None}


def start_bridge() -> None:
    if status().get("state") not in ("off", "starting") or (_proc.get("p") and _proc["p"].poll() is None):
        return
    log = open(core.DATA / "whatsapp-bridge.log", "a", encoding="utf-8")
    _proc["p"] = subprocess.Popen(["node", "bridge.js"], cwd=BRIDGE_DIR, stdout=log, stderr=log,
                                  creationflags=0x08000000)


def stop_bridge() -> None:
    p = _proc.pop("p", None)
    if p and p.poll() is None:
        p.terminate()


def connected() -> bool:
    return enabled() and status().get("state") == "connected"


def unread() -> list[dict]:
    return requests.get(URL + "/unread", timeout=5).json()


def summary(lang: str, detailed: bool = True) -> str:
    if not connected():
        return ""
    try:
        chats = unread()
    except Exception as e:  # noqa: BLE001
        return "WhatsApp: ошибка — " + str(e)[:80]
    if not chats:
        return "В WhatsApp непрочитанных нет." if lang == "ru" else "WhatsAppda o'qilmagan xabar yo'q."
    total = sum(c["unread"] for c in chats)
    personal = [c for c in chats if not c["group"]]
    if lang == "ru":
        s = f"В WhatsApp {total} {plural_ru(total, 'непрочитанное сообщение', 'непрочитанных сообщения', 'непрочитанных сообщений')}"
        s += f", личных чатов: {len(personal)}." if personal else "."
    else:
        s = f"WhatsAppda {total} ta o'qilmagan xabar" + (f", shaxsiy chatlar: {len(personal)} ta." if personal else ".")
    if detailed:
        s += " " + ". ".join(f"{c['name']}: {c['last']}" for c in (personal or chats)[:4]) + "."
    return s


def read_chat(who: str, lang: str) -> str:
    r = requests.get(URL + "/chat", params={"name": who, "limit": 6}, timeout=5)
    if r.status_code == 404:
        return f"Не нашёл чат «{who}» в WhatsApp." if lang == "ru" else f"WhatsAppda «{who}» topilmadi."
    data = r.json()
    lines = [f"{('вы' if lang == 'ru' else 'siz') if m['fromMe'] else (m.get('sender') or data['name'])}: {m['text']}"
             for m in data["messages"]]
    return (f"WhatsApp, {data['name']}. " if lang == "ru" else f"WhatsApp, {data['name']}. ") + ". ".join(lines) + "."


def resolve_name(who: str) -> str | None:
    r = requests.get(URL + "/resolve", params={"name": who}, timeout=5)
    return r.json()["name"] if r.status_code == 200 else None


def send(who: str, text: str) -> str:
    r = requests.post(URL + "/send", json={"to": who, "text": text}, timeout=15)
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", "send failed"))
    return data["name"]


@core.on_start
def autostart() -> None:
    if enabled():
        start_bridge()
    while True:  # keep the bridge alive
        time.sleep(60)
        if enabled() and _proc.get("p") and _proc["p"].poll() is not None:
            start_bridge()


def _not_ready(ctx: Ctx):
    if connected():
        return None
    return ctx.t("WhatsApp не подключён. Откройте окно Джарвиса → «Подключения» → WhatsApp и отсканируйте QR-код.",
                 "WhatsApp ulanmagan. Jarvis oynasi → «Подключения» → WhatsApp, QR-kodni skanerlang.")


@skill(
    "whatsapp.unread",
    title={"ru": "Непрочитанные сообщения в WhatsApp", "uz": "WhatsAppdagi o'qilmagan xabarlar"},
    patterns={"ru": [r"(ватсап|вотсап|whatsapp|вацап)\w*.*(прочитай|сколько|проверь|есть|новые|новых|нового|покажи|непрочитан|что)",
                     r"(прочитай|сколько|проверь|есть|новые|новых|нового|покажи|непрочитан|что)\w*.*(ватсап|вотсап|whatsapp|вацап)"],
              "uz": [r"(whatsapp|vatsap|votsap)\w*.*(oqi|nechta|tekshir|bormi|yangi|korsat|qancha)"]},
    examples={"ru": ["Что нового в ватсапе?"], "uz": ["WhatsAppda yangi xabarlar bormi?"]},
    priority=44,
)
def wa_unread(ctx: Ctx) -> str:
    if re.search(r"(что пишет|что написал)", ctx.norm):
        return None
    return _not_ready(ctx) or summary(ctx.lang)


@skill(
    "whatsapp.chat",
    title={"ru": "Прочитать чат в WhatsApp", "uz": "WhatsAppdagi chatni o'qish"},
    patterns={"ru": [r"(?:что пишет|что написал|что написала|прочитай (?:сообщения|чат|переписку) (?:от|с))\s+(.+?)\s+в (?:ватсап|вотсап|whatsapp|вацап)\w*$"],
              "uz": [r"(?:whatsappda|vatsapda) (.+?) (?:nima yozdi|nima yozgan)"]},
    examples={"ru": ["Что пишет Ахмад в ватсапе?"], "uz": ["WhatsAppda Ahmad nima yozdi?"]},
    priority=43,
)
def wa_chat(ctx: Ctx) -> str:
    return _not_ready(ctx) or read_chat(ctx.group(1), ctx.lang)
