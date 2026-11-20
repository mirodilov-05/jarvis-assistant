"""Information & communication tools: weather, briefing, mail, messengers, YouTube, calendar, modes."""

import core
from tools import run_skill, tool

S = {"type": "string"}
APP = {"type": "string", "enum": ["telegram", "whatsapp"]}


@tool("weather", "Погода сейчас и на завтра (по умолчанию город пользователя).", {"city": S})
def weather(city: str = "") -> str:
    return run_skill("weather.now", f"погода в {city}" if city else "какая погода")


@tool("briefing", "Полный отчёт о дне: дела, календарь, погода, почта, сообщения, YouTube и совет.")
def briefing() -> str:
    return run_skill("briefing.report", "отчет")


@tool("read_email", "Непрочитанные письма во всех ящиках.")
def read_email() -> str:
    return run_skill("email.unread", "прочитай почту")


@tool("messages_unread", "Непрочитанные сообщения в Telegram или WhatsApp.", {"app": APP}, ["app"])
def messages_unread(app: str) -> str:
    return run_skill("whatsapp.unread" if app == "whatsapp" else "telegram.unread",
                     "что нового в ватсапе" if app == "whatsapp" else "сколько сообщений в телеграме")


@tool("read_chat", "Прочитать переписку с человеком.", {"contact": S, "app": APP}, ["contact"])
def read_chat(contact: str, app: str = "telegram") -> str:
    if app == "whatsapp":
        return run_skill("whatsapp.chat", f"что пишет {contact} в ватсапе")
    return run_skill("telegram.chat", f"что пишет {contact}")


@tool("send_message", "Отправить сообщение человеку в Telegram или WhatsApp (Джарвис сам переспросит перед отправкой).",
      {"contact": {**S, "description": "Кому, как в контактах"}, "text": {**S, "description": "Текст сообщения"}, "app": APP},
      ["contact", "text"], tier="self")
def send_message(contact: str, text: str, app: str = "telegram") -> str:
    where = " в ватсап" if app == "whatsapp" else ""
    return run_skill("messaging.send", f"напиши {contact}{where}: {text}")


@tool("youtube_stats", "Статистика YouTube-каналов пользователя и новые комментарии.")
def youtube_stats() -> str:
    return run_skill("youtube.stats", "статистика ютуба")


@tool("calendar", "События в календаре на сегодня или завтра.", {"day": {"type": "string", "enum": ["today", "tomorrow"]}})
def calendar(day: str = "today") -> str:
    return run_skill("calendar.day", "что в календаре завтра" if day == "tomorrow" else "какие встречи сегодня")


@tool("switch_mode", "Переключить режим: normal (обычный), work (работа), study (учёба), game (игра), rest (отдых), night (ночь).",
      {"mode": {"type": "string", "enum": ["normal", "work", "study", "game", "rest", "night"]}}, ["mode"])
def switch_mode(mode: str) -> str:
    return core.set_profile(mode)


@tool("set_feature", "Включить/выключить функцию в текущем режиме.",
      {"feature": {"type": "string", "enum": list(core.FEATURES)}, "on": {"type": "boolean"}}, ["feature", "on"])
def set_feature(feature: str, on: bool) -> str:
    core.set_feature(feature, bool(on))
    return f"{'Включил' if on else 'Выключил'}: {core.FEATURES[feature][0].lower()}."
