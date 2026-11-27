"""Voice control of Jarvis's memory of your activity (see activity.py for exactly what is recorded)."""
import activity
import core
from core import Ctx, skill


@core.on_start
def _resume():
    activity.start()          # resumes only if the owner turned it on before


@skill(
    "activity.on",
    title={"ru": "Запоминать, какими программами я пользуюсь"},
    patterns={"ru": [r"^(?:джарвис )?(?:включи|начни) запоминание (?:активности|того что я делаю|моей активности)$",
                     r"^(?:джарвис )?запоминай (?:что я делаю|мою активность|все мои действия)$"]},
    examples={"ru": ["Включи запоминание активности"]},
    priority=4,
)
def activity_on(ctx: Ctx) -> str:
    activity.set_enabled(True)
    activity.start()
    return ctx.t("Включил. Буду помнить, какими программами вы пользуетесь и сколько времени. "
                 "Клавиши, пароли и содержимое экрана я не запоминаю. Выключить: «выключи запоминание активности».",
                 "Yoqdim. Qaysi dasturlardan foydalanganingizni eslab qolaman.")


@skill(
    "activity.off",
    title={"ru": "Перестать запоминать активность"},
    patterns={"ru": [r"^(?:джарвис )?(?:выключи|останови|отключи) запоминание(?: активности| того что я делаю)?$",
                     r"^(?:джарвис )?не запоминай (?:что я делаю|мою активность)$"]},
    examples={"ru": ["Выключи запоминание активности"]},
    priority=4,
)
def activity_off(ctx: Ctx) -> str:
    activity.set_enabled(False)
    activity.stop()
    return ctx.t("Выключил запоминание активности. Уже записанное осталось; «забудь мою активность» удалит и его.",
                 "Faollikni eslab qolish o'chirildi.")


@skill(
    "activity.summary",
    title={"ru": "Что я делал сегодня (по программам)"},
    patterns={"ru": [r"^(?:джарвис )?что я (?:сегодня )?(?:делал|делала|делаю|использовал)(?: сегодня)?$",
                     r"^(?:джарвис )?(?:сколько|сколько времени) (?:я )?(?:сегодня )?(?:провёл|провел|был|был за|работал за) "
                     r"(?:за )?(?:компьютером|ноутбуком|комп\w*)(?: сегодня)?$",
                     r"^(?:джарвис )?(?:моя )?активность(?: за сегодня)?$"]},
    examples={"ru": ["Что я сегодня делал"]},
    priority=4,
)
def activity_summary(ctx: Ctx) -> str:
    text = activity.today_summary()
    return ctx.t(text, text)


@skill(
    "activity.forget",
    title={"ru": "Удалить всю запомненную активность"},
    patterns={"ru": [r"^(?:джарвис )?забудь (?:мою |всю мою )?активность$",
                     r"^(?:джарвис )?удали (?:мою )?(?:историю )?активности$"]},
    examples={"ru": ["Забудь мою активность"]},
    priority=4,
)
def activity_forget(ctx: Ctx) -> str:
    def do():
        activity.forget()
        return ctx.t("Удалил всю запомненную активность.", "Faollik o'chirildi.")
    return core.ask_confirm(ctx, ctx.t("Удалить всю запомненную активность? Скажите «да».",
                                       "Faollikni o'chiraymi? «ha» deng."), do)
