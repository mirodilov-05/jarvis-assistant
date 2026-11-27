"""Everyday «open» commands that were missing: more websites, Windows settings pages and system tools.

Each entry is one command: «открой <название>» (also «запусти», «покажи», «зайди на»). Names are matched as
whole phrases, so an unknown name passes to the other skills instead of being guessed.
"""
import os
import re
import subprocess

import core
from core import Ctx, skill

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

WEBSITES = {
    "озон": "https://www.ozon.ru", "ozon": "https://www.ozon.ru",
    "вайлдберриз": "https://www.wildberries.ru", "wildberries": "https://www.wildberries.ru",
    "авито": "https://www.avito.ru", "avito": "https://www.avito.ru",
    "госуслуги": "https://www.gosuslugi.ru",
    "яндекс маркет": "https://market.yandex.ru", "маркет": "https://market.yandex.ru",
    "алиэкспресс": "https://aliexpress.ru", "aliexpress": "https://aliexpress.ru",
    "реддит": "https://www.reddit.com", "reddit": "https://www.reddit.com",
    "пинтерест": "https://www.pinterest.com", "pinterest": "https://www.pinterest.com",
    "zoom": "https://zoom.us", "зум": "https://zoom.us",
    "гугл meet": "https://meet.google.com", "гугл мит": "https://meet.google.com", "google meet": "https://meet.google.com",
    "notion": "https://www.notion.so", "ноушен": "https://www.notion.so",
    "рутуб": "https://rutube.ru", "rutube": "https://rutube.ru",
    "википедия": "https://ru.wikipedia.org", "wikipedia": "https://en.wikipedia.org",
    "лента": "https://lenta.ru", "риа": "https://ria.ru", "би би си": "https://www.bbc.com/news", "bbc": "https://www.bbc.com/news",
    "гисметео": "https://www.gismeteo.ru",
    "курсы валют": "https://www.cbr.ru/currency_base/daily/",
    "гугл переводчик": "https://translate.google.com", "google translate": "https://translate.google.com",
    "словари": "https://slovari.yandex.ru",
    "яндекс такси": "https://taxi.yandex.ru", "такси": "https://taxi.yandex.ru",
    "яндекс диск": "https://disk.yandex.ru", "гугл фото": "https://photos.google.com",
    "гугл карты": "https://www.google.com/maps", "google maps": "https://www.google.com/maps",
    "стим магазин": "https://store.steampowered.com",
    "сбербанк": "https://www.sberbank.ru", "сбер": "https://www.sberbank.ru",
}

# Windows pages and system tools. The value is what Windows opens (a settings link or a program).
SYSTEM = {
    "настройки bluetooth": "ms-settings:bluetooth", "блютуз": "ms-settings:bluetooth", "bluetooth": "ms-settings:bluetooth",
    "настройки wifi": "ms-settings:network-wifi", "настройки вайфай": "ms-settings:network-wifi",
    "настройки сети": "ms-settings:network-status", "сетевые настройки": "ms-settings:network-status",
    "настройки звука": "ms-settings:sound", "звуковые настройки": "ms-settings:sound",
    "настройки экрана": "ms-settings:display", "настройки дисплея": "ms-settings:display",
    "настройки питания": "ms-settings:powersleep", "настройки сна": "ms-settings:powersleep",
    "обновления windows": "ms-settings:windowsupdate", "центр обновления": "ms-settings:windowsupdate",
    "установленные программы": "ms-settings:appsfeatures", "приложения и функции": "ms-settings:appsfeatures",
    "автозагрузку": "ms-settings:startupapps", "автозагрузка": "ms-settings:startupapps",
    "дату и время": "ms-settings:dateandtime", "часовой пояс": "ms-settings:dateandtime",
    "конфиденциальность": "ms-settings:privacy", "о системе": "ms-settings:about",
    "учётные записи": "ms-settings:yourinfo", "учетные записи": "ms-settings:yourinfo",
    "диспетчер устройств": "devmgmt.msc", "управление дисками": "diskmgmt.msc", "службы": "services.msc",
    "редактор реестра": "regedit", "реестр": "regedit", "командную строку": "cmd", "командная строка": "cmd",
    "powershell": "powershell", "панель управления": "control", "монитор ресурсов": "resmon",
}
PROGRAMS = {"cmd", "powershell", "control", "regedit", "explorer", "calc", "notepad", "taskmgr", "resmon",
            "devmgmt.msc", "diskmgmt.msc", "services.msc"}


def _open(target: str) -> None:
    if target in PROGRAMS:
        subprocess.Popen(target, shell=True, creationflags=NO_WINDOW)
    else:
        os.startfile(target)


_NAMES = sorted(set(WEBSITES) | set(SYSTEM), key=len, reverse=True)      # longest name first
_NAME_RE = "|".join(re.escape(n) for n in _NAMES)


@skill("daily.open", title={"ru": "Открыть сайт или раздел Windows (повседневные)"},
       patterns={"ru": [r"^(?:джарвис )?(?:открой|запусти|покажи|зайди на|перейди на|открыть)(?: мне)?"
                        r"(?: раздел| страницу| сайт)? (" + _NAME_RE + r")$"]},
       examples={"ru": ["Открой озон", "Открой настройки Bluetooth", "Открой диспетчер устройств"]},
       priority=6)
def daily_open(ctx: Ctx):
    name = re.sub(r"\s+", " ", ctx.group(1)).strip(" ?.!")
    if name in WEBSITES:
        _open(WEBSITES[name])
        return ctx.t(f"Открываю {name}.", f"{name} ochilmoqda.")
    if name in SYSTEM:
        _open(SYSTEM[name])
        return ctx.t(f"Открываю {name}.", f"{name} ochilmoqda.")
    return None      # not one of ours (e.g. «открой настройки» is Jarvis's own settings): the other skills decide


core._LONG_OK.add("daily.open")
