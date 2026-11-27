"""Everyday phrasings that were missing: alarms, timers, notes, weather, rates, memory, recycle bin, routes, small
helpers. Most reuse the skill that already does the work (delegate); a few are new and small.
"""
import ctypes
import datetime as dt
import random
import socket
import urllib.parse

import core
from core import Ctx, skill

_UNIT = r"(минут\w*|секунд\w*|час\w*)"


def _delegate(skill_name: str, text: str, ctx: Ctx):
    """Run another skill's handler on a phrase it understands (the same way its own pattern would)."""
    sk = next((s for s in core.SKILLS if s.name == skill_name), None)
    if sk is None:
        return None
    norm = core.normalize(text, ctx.lang)
    for pat in sk.patterns.get(ctx.lang, []):
        m = pat.search(norm)
        if m:
            return sk.handler(Ctx(text=text, lang=ctx.lang, source=ctx.source, config=ctx.config, match=m, norm=norm))
    return None


# ---- alarms and timers --------------------------------------------------------------------------------------

@skill("more.alarm", title={"ru": "Будильник на время (6 30, в 7, разбуди в 8)"},
       patterns={"ru": [r"^(?:джарвис )?(?:поставь )?(?:будильник|разбуди меня)(?: на| в)? (\d{1,2}(?: \d{2})?(?: утра| вечера)?)$"]},
       examples={"ru": ["Будильник на 6 30", "Разбуди меня в 8"]}, priority=3)
def alarm(ctx: Ctx):
    return _delegate("reminders.at", f"поставь будильник на {ctx.group(1)}", ctx)


@skill("more.timer", title={"ru": "Таймер (на 10 минут, засеки 5 минут, помодоро, пауза)"},
       patterns={"ru": [rf"^(?:джарвис )?(?:поставь |заведи )?(?:таймер|засеки)(?: на)? (\d+) {_UNIT}$",
                        rf"^(?:джарвис )?засеки (\d+) {_UNIT}$",
                        r"^(?:джарвис )?помодоро$",
                        r"^(?:джарвис )?сделай паузу$"]},
       examples={"ru": ["Таймер на 10 минут", "Засеки 5 минут", "Помодоро", "Сделай паузу"]}, priority=3)
def timer(ctx: Ctx):
    if ctx.match.re.pattern.endswith("помодоро$"):
        return _delegate("reminders.timer", "поставь таймер на 25 минут", ctx)
    if "паузу" in ctx.norm:
        return _delegate("reminders.timer", "поставь таймер на 5 минут", ctx)
    return _delegate("reminders.timer", f"поставь таймер на {ctx.group(1)} {ctx.group(2)}", ctx)


@skill("more.until_day_end", title={"ru": "Сколько осталось до конца дня"},
       patterns={"ru": [r"^(?:джарвис )?сколько (?:осталось|до конца|времени до конца) (?:до )?(?:конца )?дня$"]},
       examples={"ru": ["Сколько осталось до конца дня"]}, priority=3)
def until_day_end(ctx: Ctx) -> str:
    now = core.now()
    end = now.replace(hour=23, minute=59, second=0, microsecond=0)
    mins = max(0, int((end - now).total_seconds() // 60))
    return ctx.t(f"До конца дня {mins // 60} ч {mins % 60} мин.", f"Kun oxirigacha {mins // 60} soat {mins % 60} daqiqa.")


@skill("more.days_to_new_year", title={"ru": "Сколько дней до Нового года"},
       patterns={"ru": [r"^(?:джарвис )?сколько (?:дней|осталось дней) до нового года$"]},
       examples={"ru": ["Сколько дней до нового года"]}, priority=3)
def days_to_new_year(ctx: Ctx) -> str:
    today = core.now().date()
    ny = dt.date(today.year + 1, 1, 1)
    return ctx.t(f"До Нового года {(ny - today).days} дн.", f"Yangi yilgacha {(ny - today).days} kun.")


# ---- notes and tasks ----------------------------------------------------------------------------------------

@skill("more.note", title={"ru": "Сделать заметку (сделай заметку …)"},
       patterns={"ru": [r"^(?:джарвис )?сделай заметку (.+)$", r"^(?:джарвис )?заметь (.+)$"]},
       examples={"ru": ["Сделай заметку что завтра встреча"]}, priority=3)
def note(ctx: Ctx):
    return _delegate("notes.add", f"запиши заметку {ctx.group(1)}", ctx)


@skill("more.notes_list", title={"ru": "Что у меня в заметках"},
       patterns={"ru": [r"^(?:джарвис )?что (?:у меня )?(?:в )?заметк\w*$", r"^(?:джарвис )?мои заметки$"]},
       examples={"ru": ["Что у меня в заметках"]}, priority=3)
def notes_list(ctx: Ctx):
    return _delegate("notes.read", "прочитай мои заметки", ctx)


# ---- weather, money, facts ----------------------------------------------------------------------------------

@skill("more.rain", title={"ru": "Будет ли дождь"},
       patterns={"ru": [r"^(?:джарвис )?будет ли (?:сегодня |завтра )?(?:дождь|снег)\w*$", r"^(?:джарвис )?(?:сегодня )?дождь будет\w*$"]},
       examples={"ru": ["Будет ли сегодня дождь"]}, priority=3)
def rain(ctx: Ctx):
    return _delegate("weather.now", "какая погода сегодня", ctx)


@skill("more.euro", title={"ru": "Курс евро и других валют (из интернета)"},
       patterns={"ru": [r"^(?:джарвис )?(?:какой )?курс (евро|юаня|фунта|рубля|тенге|сума|иены)$"]},
       examples={"ru": ["Курс евро"]}, priority=3)
def euro(ctx: Ctx):
    return _delegate("pro.web_answer", f"узнай курс {ctx.group(1)} к доллару сейчас", ctx)


@skill("more.holiday", title={"ru": "Какой завтра праздник"},
       patterns={"ru": [r"^(?:джарвис )?какой (?:завтра|сегодня) праздник$"]},
       examples={"ru": ["Какой завтра праздник"]}, priority=3)
def holiday(ctx: Ctx):
    return _delegate("pro.web_answer", "узнай какой праздник завтра", ctx)


@skill("more.news", title={"ru": "Новости (из интернета)"},
       patterns={"ru": [r"^(?:джарвис )?(?:что )?(?:по )?новост\w*(?: сегодня)?$", r"^(?:джарвис )?расскажи новости$"]},
       examples={"ru": ["Что по новостям", "Расскажи новости"]}, priority=3)
def news(ctx: Ctx):
    return _delegate("pro.web_answer", "узнай главные новости сегодня", ctx)


# ---- computer --------------------------------------------------------------------------------------------------

@skill("more.memory", title={"ru": "Сколько памяти свободно"},
       patterns={"ru": [r"^(?:джарвис )?сколько (?:оперативной )?памяти (?:свободно|осталось)$", r"^(?:джарвис )?свободная память$"]},
       examples={"ru": ["Сколько памяти свободно"]}, priority=3)
def memory(ctx: Ctx) -> str:
    import psutil
    m = psutil.virtual_memory()
    free, total = m.available / 2 ** 30, m.total / 2 ** 30
    return ctx.t(f"Свободно {free:.1f} ГБ из {total:.0f} ГБ памяти.", f"{free:.1f} GB bo'sh.")


@skill("more.recycle", title={"ru": "Очистить корзину (с подтверждением)"},
       patterns={"ru": [r"^(?:джарвис )?очисти (?:корзину|корзину windows)$", r"^(?:джарвис )?(?:опустоши|очисть) корзин\w*$"]},
       examples={"ru": ["Очисти корзину"]}, priority=3)
def recycle(ctx: Ctx) -> str:
    def empty():
        # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
        return ctx.t("Корзина очищена. Удалённое не восстановить.", "Savat tozalandi.")
    return core.ask_confirm(ctx, ctx.t("Очистить корзину? Удалённые файлы потом не вернуть. Скажите «да».",
                                       "Savatni tozalaymi? «ha» deng."), empty)


@skill("more.ip", title={"ru": "Какой IP-адрес у компьютера"},
       patterns={"ru": [r"^(?:джарвис )?какой ip(?: адрес)?(?: у (?:меня|компьютера|ноутбука))?$", r"^(?:джарвис )?какой (?:у (?:меня|компьютера|ноутбука) )?ip(?: адрес)?$",
                        r"^(?:джарвис )?(?:мой )?ip(?: адрес)?$"]},
       examples={"ru": ["Какой IP адрес у компьютера"]}, priority=3)
def ip_address(ctx: Ctx) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            addr = s.getsockname()[0]
    except OSError:
        return ctx.t("Не вижу сети: IP-адрес не определён.", "IP aniqlanmadi.")
    return ctx.t(f"Адрес в сети: {addr}.", f"Tarmoq manzili: {addr}.")


@skill("more.sleep", title={"ru": "Положить компьютер спать"},
       patterns={"ru": [r"^(?:джарвис )?(?:положи|уложи) (?:ноутбук|компьютер|комп|пк) спать$"]},
       examples={"ru": ["Положи ноутбук спать"]}, priority=3)
def sleep_pc(ctx: Ctx):
    return _delegate("system.sleep", "спящий режим", ctx)


@skill("more.louder_max", title={"ru": "Громкость: подними, на максимум"},
       patterns={"ru": [r"^(?:джарвис )?(?:подними|прибавь) громкость$", r"^(?:джарвис )?максимальная громкость$"]},
       examples={"ru": ["Подними громкость", "Максимальная громкость"]}, priority=3)
def louder_max(ctx: Ctx):
    if "максим" in ctx.norm:
        return _delegate("desktop.volume_level", "громкость 100", ctx)
    return _delegate("system.volume_up", "сделай громче", ctx)


@skill("more.route", title={"ru": "Маршрут до адреса на картах"},
       patterns={"ru": [r"^(?:джарвис )?(?:построй |проложи )?маршрут (?:до|к) (.+)$"]},
       examples={"ru": ["Построй маршрут до центра"]}, priority=3)
def route(ctx: Ctx) -> str:
    target = ctx.group(1).strip()
    ctx_url = "https://yandex.ru/maps/?rtext=~" + urllib.parse.quote(target)
    import os
    os.startfile(ctx_url)
    return ctx.t(f"Открываю маршрут до «{target}» на картах.", f"«{target}» yo'nalishi xaritada ochilmoqda.")


@skill("more.wifi_bt", title={"ru": "Wi-Fi и Bluetooth: что можно сделать голосом"},
       patterns={"ru": [r"^(?:джарвис )?(?:включи|выключи|отключи) (?:вайфай|вай фай|wi fi|wifi|блютуз|bluetooth)$"]},
       examples={"ru": ["Выключи блютуз"]}, priority=3)
def wifi_bt(ctx: Ctx) -> str:
    return ctx.t("Wi-Fi и Bluetooth пока не переключаю голосом: это делается в быстрых настройках Windows "
                 "(Win + A). Могу открыть их: скажите «открой настройки звука» или «открой настройки».",
                 "Wi-Fi va Bluetooth ovoz bilan o'zgarmaydi.")


# ---- small helpers -------------------------------------------------------------------------------------------

@skill("more.coin", title={"ru": "Подбросить монетку"},
       patterns={"ru": [r"^(?:джарвис )?подбрось монетку$", r"^(?:джарвис )?орёл или решка$", r"^(?:джарвис )?орел или решка$"]},
       examples={"ru": ["Подбрось монетку"]}, priority=3)
def coin(ctx: Ctx) -> str:
    side = random.choice(["Орёл", "Решка"])
    return ctx.t(side + ".", side + ".")


@skill("more.choose", title={"ru": "Выбрать из вариантов (чай или кофе)"},
       patterns={"ru": [r"^(?:джарвис )?выбери (.+?) или (.+)$"]},
       examples={"ru": ["Выбери чай или кофе"]}, priority=3)
def choose(ctx: Ctx) -> str:
    pick = random.choice([ctx.group(1).strip(), ctx.group(2).strip()])
    return ctx.t(f"Выбираю: {pick}.", f"Tanlayman: {pick}.")


@skill("more.random_number", title={"ru": "Случайное число"},
       patterns={"ru": [r"^(?:джарвис )?случайное число(?: от (\d+) до (\d+))?$"]},
       examples={"ru": ["Случайное число от 1 до 10"]}, priority=3)
def random_number(ctx: Ctx) -> str:
    lo, hi = (int(ctx.match.group(1)), int(ctx.match.group(2))) if ctx.match.group(1) else (1, 100)
    if lo > hi:
        lo, hi = hi, lo
    return ctx.t(f"Выпало {random.randint(lo, hi)}.", f"Chiqdi: {random.randint(lo, hi)}.")


@skill("more.shutdown_later", title={"ru": "Выключить компьютер через N минут (с подтверждением)"},
       patterns={"ru": [r"^(?:джарвис )?(?:выключи|выключить) (?:компьютер|ноутбук|ноут|комп|пк) через (\d+) (минут\w*|час\w*)$"]},
       examples={"ru": ["Выключи компьютер через 30 минут"]}, priority=3)
def shutdown_later(ctx: Ctx) -> str:
    import subprocess
    n = int(ctx.group(1))
    seconds = n * (3600 if ctx.group(2).startswith("час") else 60)
    if seconds > 12 * 3600:
        return ctx.t("Слишком долго. Выбери время до 12 часов.", "Juda uzoq.")

    def do():
        subprocess.run(["shutdown", "/s", "/t", str(seconds), "/c", "Jarvis: выключение по команде"],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return ctx.t(f"Выключу через {n} {ctx.group(2)}. Скажите «отмени выключение», чтобы остановить.",
                     "O'chiraman.")
    return core.ask_confirm(ctx, ctx.t(f"Выключить компьютер через {n} {ctx.group(2)}? Скажите «да».",
                                       f"{n} daqiqadan keyin o'chiraymi? «ha» deng."), do)


@skill("more.clipboard", title={"ru": "Что сейчас в буфере обмена"},
       patterns={"ru": [r"^(?:джарвис )?что (?:сейчас )?(?:в|у меня в) буфер\w* обмен\w*$", r"^(?:джарвис )?что я скопировал$"]},
       examples={"ru": ["Что в буфере обмена"]}, priority=3)
def clipboard(ctx: Ctx) -> str:
    import subprocess
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
                         capture_output=True, encoding="utf-8", errors="replace", timeout=15,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    if not out:
        return ctx.t("В буфере обмена пусто или там не текст.", "Buferda matn yo'q.")
    return ctx.t("В буфере: " + out[:300], out[:300])


@skill("more.my_files", title={"ru": "Открыть мои файлы (документы)"},
       patterns={"ru": [r"^(?:джарвис )?покажи (?:мои )?файлы$"]},
       examples={"ru": ["Покажи мои файлы"]}, priority=3)
def my_files(ctx: Ctx):
    return _delegate("apps.open", "открой документы", ctx)


@skill("more.task_done_by_name", title={"ru": "Отметить дело выполненным по названию (подсказка)"},
       patterns={"ru": [r"^(?:джарвис )?отметь (?:дело |задачу )?(.+?) выполненн\w*$"]},
       examples={"ru": ["Отметь дело купить хлеб выполненным"]}, priority=3)
def task_done_by_name(ctx: Ctx) -> str:
    what = ctx.group(1).strip()
    return ctx.t(f"Отмечу по номеру. Скажите «какие у меня дела», потом «выполнил дело номер N» — "
                 f"«{what}» я не менял, чтобы не отметить не то.",
                 "Raqam bo'yicha belgilayman.")


# A phrase of more than five words only reaches the skills in core._LONG_OK; these are short commands too.
core._LONG_OK.update({"more.alarm", "more.timer", "more.until_day_end", "more.note", "more.notes_list",
                      "more.rain", "more.euro", "more.holiday", "more.news", "more.memory", "more.recycle",
                      "more.ip", "more.sleep", "more.louder_max", "more.route", "more.wifi_bt", "more.coin",
                      "more.choose", "more.random_number", "more.days_to_new_year", "more.shutdown_later",
                      "more.clipboard", "more.my_files", "more.task_done_by_name"})
