"""Send a message in Telegram or WhatsApp — always asks for confirmation first.

"Напиши маме что я опоздаю на 10 минут"           -> Telegram (default)
"Напиши Ахмаду в ватсап: буду через час"          -> WhatsApp
"Onamga telegramda yoz: kechikaman"
"""

import re
import sys

from core import Ctx, ask_confirm, skill

_WA = re.compile(r"(ватсап|вотсап|вацап|whatsapp|vatsap|votsap)")


def _backend(name: str):
    return sys.modules.get(f"jarvis_plugin_{name}")


@skill(
    "messaging.send",
    title={"ru": "Написать сообщение (Telegram/WhatsApp, с подтверждением)",
           "uz": "Xabar yozish (Telegram/WhatsApp, tasdiq bilan)"},
    patterns={
        "ru": [r"^(?:джарвис )?(?:напиши|отправь|скинь|передай)(?: сообщение)?(?: в (?:телеграм\w*|ватсап\w*|вотсап\w*|whatsapp))? "
               r"(\w+(?: \w+)?)(?: в (?:телеграм\w*|ватсап\w*|вотсап\w*|whatsapp))?(?: что|:)\s*(.+)$",
               r"^(?:джарвис )?(?:напиши|отправь)(?: сообщение)? (\w+)(?: в (?:телеграм\w*|ватсап\w*|вотсап\w*|whatsapp))? (.+)$"],
        "uz": [r"^(?:jarvis )?(\w+?)(?:ga|ka|qa)? (?:telegramda |telegramdan |whatsappda |vatsapda )?(?:yoz|xabar yubor|ayt)\w*:? (.+)$"],
    },
    examples={"ru": ["Напиши маме что я опоздаю", "Напиши Ахмаду в ватсап: буду через час"],
              "uz": ["Onamga telegramda yoz: kechikaman"]},
    priority=35,
)
def send(ctx: Ctx):
    who, text = ctx.group(1), ctx.group(2)
    if not who or not text:
        return None
    use_wa = bool(_WA.search(ctx.norm))
    tg, wa = _backend("telegram"), _backend("whatsapp")
    backend = wa if use_wa else tg
    if use_wa and (wa is None or not wa.connected()):
        return ctx.t("WhatsApp не подключён. Откройте окно Джарвиса → «Подключения» → WhatsApp.",
                     "WhatsApp ulanmagan. Jarvis oynasi → «Подключения» → WhatsApp.")
    if backend is None or not backend.connected():
        # fall back to whichever messenger is connected
        backend = next((b for b in (tg, wa) if b and b.connected()), None)
        if backend is None:
            return ctx.t("Ни Telegram, ни WhatsApp не подключены. Подключите их в окне Джарвиса → «Подключения».",
                         "Telegram ham, WhatsApp ham ulanmagan.")
    app = "WhatsApp" if backend is wa else "Telegram"
    # keep the user's original wording of the message
    m = re.search(re.escape(text.split()[0]), ctx.text, re.IGNORECASE)
    body = ctx.text[m.start():].strip() if m else text
    try:
        name = backend.resolve_name(who)
    except Exception as e:  # noqa: BLE001
        return ctx.t(f"{app}: ошибка — {e}", f"{app}: xato — {e}")
    if not name:
        return ctx.t(f"Не нашёл «{who}» в {app}.", f"{app}da «{who}» topilmadi.")

    def do_send() -> str:
        sent_to = backend.send(name, body)
        return ctx.t(f"Отправил в {app}: {sent_to}.", f"{app}da yuborildi: {sent_to}.")

    return ask_confirm(ctx, ctx.t(f"Отправить в {app} для {name}: «{body}»? Скажите да или нет.",
                                  f"{app}da {name}ga yuboraymi: «{body}»? Ha yoki yo'q deng."), do_send)
