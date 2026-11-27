"""More everyday commands that are safe to run without asking: open folders, newest file, make a folder,
the latest screenshot, internet check, public IP, days to the weekend, and simple unit conversions.

Nothing here deletes or changes settings. Anything that could lose data is not in this file.
"""
import os
import re
import subprocess
from pathlib import Path

import core
from core import Ctx, skill

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HOME = Path(os.environ.get("USERPROFILE", str(Path.home())))
FOLDERS = {"рабочий стол": HOME / "Desktop", "загрузки": HOME / "Downloads", "документы": HOME / "Documents",
           "фото": HOME / "Pictures", "картинки": HOME / "Pictures", "музыку": HOME / "Music",
           "видео": HOME / "Videos", "скриншоты": HOME / "Pictures" / "Screenshots"}


@skill("batch3.folder", title={"ru": "Открыть папку (рабочий стол, загрузки, документы, фото, музыка, видео)"},
       patterns={"ru": [r"^(?:джарвис )?(?:открой|покажи) (?:мою |мои |мой )?(загрузки|документы|фото|картинки|музыку|видео|скриншоты)$"]},
       examples={"ru": ["Открой загрузки", "Покажи скриншоты"]}, priority=3)
def open_folder(ctx: Ctx) -> str:
    name = ctx.group(1)
    path = FOLDERS[name]
    if not path.exists():
        return ctx.t(f"Папки «{name}» нет.", f"{name} papkasi yo'q.")
    os.startfile(str(path))
    return ctx.t(f"Открываю {name}.", f"{name} ochilmoqda.")


@skill("batch3.newest", title={"ru": "Открыть последний файл в документах или загрузках"},
       patterns={"ru": [r"^(?:джарвис )?(?:открой|покажи) последний (?:файл|документ) (?:в )?(документах|загрузках)$"]},
       examples={"ru": ["Открой последний файл в документах"]}, priority=3)
def newest_file(ctx: Ctx) -> str:
    folder = FOLDERS["документы" if ctx.group(1) == "документах" else "загрузки"]
    try:
        files = [p for p in folder.iterdir() if p.is_file()]
    except OSError:
        files = []
    if not files:
        return ctx.t("Там нет файлов.", "Fayl yo'q.")
    newest = max(files, key=lambda p: p.stat().st_mtime)
    os.startfile(str(newest))
    return ctx.t(f"Открываю {newest.name}.", f"{newest.name} ochilmoqda.")


@skill("batch3.screenshot", title={"ru": "Открыть последний скриншот"},
       patterns={"ru": [r"^(?:джарвис )?(?:открой|покажи) последний (?:скриншот|скрин)$"]},
       examples={"ru": ["Открой последний скриншот"]}, priority=3)
def last_screenshot(ctx: Ctx) -> str:
    folders = [FOLDERS["скриншоты"], HOME / "Pictures"]
    shots = [p for f in folders if f.exists() for p in f.glob("*.png")]
    if not shots:
        return ctx.t("Скриншотов не нашёл.", "Skrinshot topilmadi.")
    newest = max(shots, key=lambda p: p.stat().st_mtime)
    os.startfile(str(newest))
    return ctx.t(f"Открываю {newest.name}.", f"{newest.name} ochilmoqda.")


@skill("batch3.make_folder", title={"ru": "Создать папку на рабочем столе"},
       patterns={"ru": [r"^(?:джарвис )?создай папку (.+?)(?: на рабочем столе)?$"]},
       examples={"ru": ["Создай папку проекты на рабочем столе"]}, priority=3)
def make_folder(ctx: Ctx) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "", ctx.group(1)).strip()
    if not name:
        return ctx.t("Какое имя у папки?", "Papka nomi?")
    target = FOLDERS["рабочий стол"] / name
    if target.exists():
        return ctx.t(f"Папка «{name}» уже есть.", f"{name} papkasi bor.")
    target.mkdir(parents=True)
    return ctx.t(f"Создал папку «{name}» на рабочем столе.", f"{name} papkasi yaratildi.")


@skill("batch3.internet", title={"ru": "Проверить интернет (пинг)"},
       patterns={"ru": [r"^(?:джарвис )?проверь (?:интернет|связь|соединение)$"]},
       examples={"ru": ["Проверь интернет"]}, priority=3)
def check_internet(ctx: Ctx) -> str:
    out = subprocess.run(["ping", "-n", "2", "-w", "1000", "8.8.8.8"], capture_output=True, encoding="cp866",
                         errors="replace", timeout=15, creationflags=NO_WINDOW).stdout
    m = re.search(r"(?:Среднее|Average)\D*(\d+)\s*(?:мс|ms)", out)
    if m:
        return ctx.t(f"Интернет есть, пинг около {m.group(1)} мс.", f"Internet bor, ping {m.group(1)} ms.")
    return ctx.t("Интернета нет или он очень медленный.", "Internet yo'q.")


@skill("batch3.public_ip", title={"ru": "Какой у меня внешний IP"},
       patterns={"ru": [r"^(?:джарвис )?(?:какой )?(?:мой )?внешний ip(?: адрес)?$"]},
       examples={"ru": ["Какой внешний IP"]}, priority=3)
def public_ip(ctx: Ctx) -> str:
    import requests
    try:
        ip = requests.get("https://api.ipify.org", timeout=6).text.strip()
    except requests.RequestException:
        return ctx.t("Не смог узнать внешний адрес: нет связи.", "Tashqi manzil aniqlanmadi.")
    return ctx.t(f"Внешний адрес: {ip}.", f"Tashqi manzil: {ip}.")


@skill("batch3.weekend", title={"ru": "Сколько дней до выходных"},
       patterns={"ru": [r"^(?:джарвис )?сколько (?:дней|осталось) до выходных$"]},
       examples={"ru": ["Сколько дней до выходных"]}, priority=3)
def days_to_weekend(ctx: Ctx) -> str:
    today = core.now().date()
    days = (5 - today.weekday()) % 7
    if days == 0 and today.weekday() >= 5:
        return ctx.t("Сегодня уже выходной.", "Bugun dam olish kuni.")
    if days == 0:
        days = 5
    return ctx.t(f"До выходных {days} дн.", f"Dam olish kunigacha {days} kun.")


_UNITS = {
    ("км", "мили"): lambda x: x * 0.621371, ("мили", "км"): lambda x: x / 0.621371,
    ("кг", "фунты"): lambda x: x * 2.20462, ("фунты", "кг"): lambda x: x / 2.20462,
    ("см", "дюймы"): lambda x: x / 2.54, ("дюймы", "см"): lambda x: x * 2.54,
    ("градусов цельсия", "фаренгейта"): lambda x: x * 9 / 5 + 32,
    ("градусов фаренгейта", "цельсия"): lambda x: (x - 32) * 5 / 9,
}


@skill("batch3.convert", title={"ru": "Перевести единицы (км в мили, кг в фунты, градусы)"},
       patterns={"ru": [r"^(?:джарвис )?(?:переведи|сколько будет) (\d+(?:[.,]\d+)?) (км|мили|кг|фунты|см|дюймы|градусов цельсия|градусов фаренгейта) в (мили|км|фунты|кг|дюймы|см|фаренгейта|цельсия)$"]},
       examples={"ru": ["Переведи 10 км в мили"]}, priority=3)
def convert(ctx: Ctx) -> str:
    x = float(ctx.group(1).replace(",", "."))
    src, dst = ctx.group(2), ctx.group(3)
    fn = _UNITS.get((src, dst))
    if fn is None:
        return ctx.t("Такой перевод пока не знаю.", "Bu o'girish noma'lum.")
    return ctx.t(f"{x:g} {src} — это {fn(x):.2f} {dst}.", f"{x:g} {src} = {fn(x):.2f} {dst}.")


core._LONG_OK.update({"batch3.folder", "batch3.newest", "batch3.screenshot", "batch3.make_folder",
                      "batch3.internet", "batch3.public_ip", "batch3.weekend", "batch3.convert"})
