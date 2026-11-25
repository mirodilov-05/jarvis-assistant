"""Computer control: volume, media keys, screenshot, lock, shutdown/restart, battery."""

import ctypes
import subprocess
import time

import keyboard

from core import Ctx, skill

NO_WINDOW = 0x08000000


def _press(key: str, times: int = 1) -> None:
    for _ in range(times):
        keyboard.send(key)
        time.sleep(0.03)


@skill(
    "system.volume_up",
    title={"ru": "Сделать громче", "uz": "Ovozni balandlatish"},
    patterns={"ru": [r"(громче|прибавь звук|увеличь (звук|громкость)|сделай громче)"],
              "uz": [r"ovoz\w* (balandlat|oshir|kotar|kuchaytir)", r"balandroq"]},
    examples={"ru": ["Громче"], "uz": ["Ovozni balandlat"]},
    priority=10,
)
def volume_up(ctx: Ctx) -> str:
    _press("volume up", 5)
    return ctx.t("Сделал громче.", "Ovoz balandlatildi.")


@skill(
    "system.volume_down",
    title={"ru": "Сделать тише", "uz": "Ovozni pasaytirish"},
    patterns={"ru": [r"(тише|убавь звук|уменьши (звук|громкость)|сделай тише)"],
              "uz": [r"ovoz\w* (pasaytir|kamaytir|tushir)", r"pastroq"]},
    examples={"ru": ["Тише"], "uz": ["Ovozni pasaytir"]},
    priority=10,
)
def volume_down(ctx: Ctx) -> str:
    _press("volume down", 5)
    return ctx.t("Сделал тише.", "Ovoz pasaytirildi.")


@skill(
    "system.mute",
    title={"ru": "Выключить или включить звук", "uz": "Ovozni o'chirish/yoqish"},
    patterns={"ru": [r"(выключи|включи|отключи) (звук|громкость)", r"без звука"],
              "uz": [r"ovoz\w* (ochir|yoq)\w*"]},
    examples={"ru": ["Выключи звук"], "uz": ["Ovozni o'chir"]},
    priority=10,
)
def mute(ctx: Ctx) -> str:
    _press("volume mute")
    return ctx.t("Готово.", "Bajarildi.")


@skill(
    "system.media",
    title={"ru": "Музыка/видео: пауза, следующий, предыдущий", "uz": "Musiqa: pauza, keyingi, oldingi"},
    patterns={"ru": [r"^(пауза|продолжи|играй|воспроизведи|следующ\w+( трек| песн\w+)?|предыдущ\w+( трек| песн\w+)?|дальше)$"],
              "uz": [r"^(pauza|davom ettir|keyingi\w*( qoshiq)?|oldingi\w*( qoshiq)?|toxtat)$"]},
    examples={"ru": ["Пауза", "Следующий трек"], "uz": ["Pauza", "Keyingi qo'shiq"]},
    priority=10,
)
def media(ctx: Ctx) -> str:
    w = ctx.norm
    if w.startswith(("следующ", "дальше", "keyingi")):
        _press("next track")
    elif w.startswith(("предыдущ", "oldingi")):
        _press("previous track")
    else:
        _press("play/pause media")
    return ctx.t("Готово.", "Bajarildi.")


@skill(
    "system.screenshot",
    title={"ru": "Сделать скриншот", "uz": "Skrinshot olish"},
    patterns={"ru": [r"(сделай|сними) (скриншот|снимок экрана)", r"^скриншот$"],
              "uz": [r"skrinshot (ol|qil)\w*", r"ekran\w* (rasmga ol|suratga ol)"]},
    examples={"ru": ["Сделай скриншот"], "uz": ["Skrinshot ol"]},
    priority=10,
)
def screenshot(ctx: Ctx) -> str:
    keyboard.send("windows+print screen")
    return ctx.t("Скриншот сохранён в папку Изображения, Снимки экрана.", "Skrinshot Rasmlar papkasiga saqlandi.")


@skill(
    "system.lock",
    title={"ru": "Заблокировать компьютер", "uz": "Kompyuterni qulflash"},
    patterns={"ru": [r"(заблокируй|блокируй) (компьютер|ноутбук|экран)"],
              "uz": [r"(kompyuter|noutbuk|ekran)\w* (qulfla|blokla)\w*"]},
    examples={"ru": ["Заблокируй компьютер"], "uz": ["Kompyuterni qulfla"]},
    priority=10,
)
def lock(ctx: Ctx) -> str:
    ctypes.windll.user32.LockWorkStation()
    return ctx.t("Блокирую.", "Qulflanmoqda.")


@skill(
    "system.shutdown",
    title={"ru": "Выключить или перезагрузить компьютер (через минуту)", "uz": "Kompyuterni o'chirish yoki qayta yoqish"},
    patterns={"ru": [r"^(?:джарвис )?(?:я сказал |это не программа )?(?:выключи|выключить|перезагрузи|перезапусти) (?:мой |этот |сразу |сейчас )*(?:компьютер|ноутбук|ноут|комп|пк)"
                     r"(?: пожалуйста| сразу| сейчас| я говорю| я сказал)*$"],
              "uz": [r"(kompyuter|noutbuk)\w* (ochir|qayta yoq|qayta ishga tushir)\w*"]},
    examples={"ru": ["Выключи компьютер"], "uz": ["Kompyuterni o'chir"]},
    priority=9,
)
def shutdown(ctx: Ctx) -> str:
    restart = any(w in ctx.norm for w in ("перезагру", "перезапус", "qayta"))

    def _do() -> str:
        subprocess.run(["shutdown", "/r" if restart else "/s", "/t", "60"], creationflags=NO_WINDOW)
        if restart:
            return ctx.t("Перезагружу компьютер через минуту. Чтобы отменить, скажите: отмени выключение.",
                         "Bir daqiqadan keyin qayta yoqiladi. Bekor qilish uchun: o'chirishni bekor qil.")
        return ctx.t("Выключу компьютер через минуту. Чтобы отменить, скажите: отмени выключение.",
                     "Bir daqiqadan keyin o'chiriladi. Bekor qilish uchun: o'chirishni bekor qil.")

    # never power off on one phrase: the user must say «да»
    import core
    return core.ask_confirm(ctx, ctx.t(
        "Перезагрузить компьютер через минуту?" if restart else "Выключить компьютер через минуту?",
        "Kompyuterni qayta yoqaymi?" if restart else "Kompyuterni o'chiraymi?"), _do)


@skill(
    "system.sleep",
    title={"ru": "Спящий режим и гибернация (после «да»)"},
    patterns={"ru": [r"^(?:джарвис )?(?:(?:переведи|отправь|поставь|включи|перейди|уйди) )?(?:(?:компьютер|ноутбук|ноут|комп|пк) )?(?:в )?"
                     r"(?:спящ\w+ режим\w*|режим сна|сон|гибернаци\w*)$",
                     r"^(?:джарвис )?(?:усни|усыпи (?:компьютер|ноутбук|ноут|комп|пк))$"]},
    examples={"ru": ["Спящий режим", "Переведи компьютер в спящий режим"]},
    priority=9,
)
def sleep(ctx: Ctx) -> str:
    import core

    hibernate = "гиберн" in ctx.norm

    def _go() -> None:
        if hibernate:
            subprocess.run(["shutdown", "/h"], creationflags=NO_WINDOW)
        else:      # this laptop has S0 standby, no S3: it falls asleep when the display is switched off
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)      # WM_SYSCOMMAND, SC_MONITORPOWER, off

    def _do() -> str:
        import threading
        threading.Timer(4, _go).start()      # say it first, then sleep
        return "Ухожу в гибернацию." if hibernate else "Ухожу в спящий режим."

    return core.ask_confirm(ctx, "Перевести компьютер в гибернацию?" if hibernate else "Перевести компьютер в спящий режим?", _do)


@skill(
    "system.shutdown_cancel",
    title={"ru": "Отменить выключение", "uz": "O'chirishni bekor qilish"},
    patterns={"ru": [r"отмени (выключение|перезагрузку)"], "uz": [r"ochirish\w* bekor", r"qayta yoqish\w* bekor"]},
    examples={"ru": ["Отмени выключение"], "uz": ["O'chirishni bekor qil"]},
    priority=8,
)
def shutdown_cancel(ctx: Ctx) -> str:
    subprocess.run(["shutdown", "/a"], creationflags=NO_WINDOW)
    return ctx.t("Выключение отменено.", "O'chirish bekor qilindi.")


class _Power(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


@skill(
    "system.battery",
    title={"ru": "Сказать заряд батареи", "uz": "Batareya quvvatini aytish"},
    patterns={"ru": [r"(заряд|батаре)"], "uz": [r"(batareya|zaryad|quvvat)"]},
    examples={"ru": ["Сколько заряда?"], "uz": ["Batareya qancha?"]},
    priority=10,
)
def battery(ctx: Ctx) -> str:
    s = _Power()
    ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))
    pct = s.BatteryLifePercent & 0xFF
    plugged = s.ACLineStatus == 1
    if pct == 255:
        return ctx.t("Не удалось узнать заряд.", "Quvvatni aniqlab bo'lmadi.")
    return ctx.t(f"Заряд {pct} процентов" + (", ноутбук на зарядке." if plugged else "."),
                 f"Batareya {pct} foiz" + (", quvvatlanmoqda." if plugged else "."))
