"""Message alerts (switched per mode): tells you when a new personal message or
email arrives — "Новое сообщение в Телеграме от Ахмада: буду через час".
Checks every 2 minutes; only personal chats (not groups/channels), only once per message.
"""

import sys
import time

import core

_seen: dict = {"tg": {}, "wa": {}, "mail": None}


def _mod(name: str):
    return sys.modules.get(f"jarvis_plugin_{name}")


def _check_messengers() -> list[str]:
    out = []
    tg = _mod("telegram")
    if tg and tg.connected():
        try:
            for d in tg.unread_dialogs():
                if not d["is_user"] or d["muted"]:
                    continue
                if d["unread"] > _seen["tg"].get(d["name"], 0):
                    if d["name"] in _seen["tg"] or _seen.get("tg_ready"):
                        out.append(f"Новое сообщение в Телеграме от {d['name']}: {d['last']}")
                _seen["tg"][d["name"]] = d["unread"]
            _seen["tg_ready"] = True
        except Exception:  # noqa: BLE001
            core.log.warning("telegram alerts failed", exc_info=True)
    wa = _mod("whatsapp")
    if wa and wa.connected():
        try:
            for c in wa.unread():
                if c["group"]:
                    continue
                if c["unread"] > _seen["wa"].get(c["jid"], 0) and (c["jid"] in _seen["wa"] or _seen.get("wa_ready")):
                    out.append(f"Новое сообщение в WhatsApp от {c['name']}: {c['last']}")
                _seen["wa"][c["jid"]] = c["unread"]
            _seen["wa_ready"] = True
        except Exception:  # noqa: BLE001
            core.log.warning("whatsapp alerts failed", exc_info=True)
    return out


def _check_mail() -> list[str]:
    em = _mod("email_imap")
    if not em:
        return []
    try:
        boxes = em.check_all(limit=3)
    except Exception:  # noqa: BLE001
        return []
    total = sum(b["unread"] for b in boxes if not b["error"])
    prev = _seen["mail"]
    _seen["mail"] = total
    if prev is None or total <= prev:
        return []
    newest = next((i for b in boxes for i in b["items"]), None)
    n = total - prev
    return [f"Пришло новое письмо" + (f" от {newest['from']}: {newest['subject']}" if newest and n == 1 else f", новых: {n}")]


@core.on_start
def loop() -> None:
    time.sleep(60)
    while True:
        try:
            if core.feature("message_alerts"):
                for msg in (_check_messengers() + _check_mail())[:3]:
                    core.speak(msg, "ru")
        except Exception:  # noqa: BLE001
            core.log.exception("notifier loop")
        time.sleep(120)
