"""Everyday desktop control by voice: windows, brightness, exact volume, files, phrase translation, currency.

  Окна:      «сверни все окна», «сверни окно», «разверни окно», «закрой окно», «переключи окно»,
             «окно влево / вправо», «покажи рабочий стол»
  Экран:     «яркость 40», «ярче», «темнее»
  Звук:      «громкость 30», «громкость на максимум», «громкость на 0»
  Файлы:     «найди файл договор», «открой последний скачанный файл», «открой последнюю загрузку»
  Перевод:   «как по-английски спасибо за помощь», «переведи на японский я люблю кофе»
  Валюта:    «сколько будет 100 долларов в сумах», «переведи 50 евро в рубли»
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import core
from core import Ctx, skill

NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _keys(k: str) -> None:
    import keyboard
    keyboard.send(k)


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

WIN_ACTIONS = [
    (r"сверни все(?: окна)?|покажи рабочий стол|на рабочий стол", "windows+d", "Свернул все окна."),
    (r"разверни(?: это)? окно|окно на весь экран|на весь экран", "windows+up", "Развернул."),
    (r"сверни(?: это)? окно|убери окно", "windows+down", "Свернул."),
    (r"закрой (?:это |текущее )?окно", "alt+f4", "Закрыл окно."),
    (r"восстанови(?:ть)?(?: все)?(?: свернут\w*)? окна?|верни окна|верни (?:все )?окна|покажи окна", "windows+shift+m", "Вернул свёрнутые окна."),
    (r"переключи(?:сь)? окно|следующее окно|предыдущее окно|другое окно", "alt+tab", "Переключил."),
    (r"окно (?:влево|налево)|прижми влево", "windows+left", "Окно слева."),
    (r"окно (?:вправо|направо)|прижми вправо", "windows+right", "Окно справа."),
]


@skill("desktop.windows", title={"ru": "Окна: свернуть, развернуть, закрыть, переключить, влево/вправо"},
       patterns={"ru": [r"^(?:джарвис )?(" + "|".join(rx for rx, _, _ in WIN_ACTIONS) + r")$"]},
       examples={"ru": ["Сверни все окна", "Окно влево", "Закрой окно"]}, priority=7)
def windows(ctx: Ctx) -> str:
    for rx, keys, reply in WIN_ACTIONS:
        if re.search(rx, ctx.norm):
            if keys == "alt+f4":
                import pcx
                _, title, exe = pcx.foreground()
                if "Джарвис" in title:
                    return "Это моё окно, сэр. Скажите «сверни в трей»."
            _keys(keys)
            return reply
    return None


# ---------------------------------------------------------------------------
# Brightness and exact volume
# ---------------------------------------------------------------------------

def brightness(level: int | None = None, delta: int = 0) -> int:
    get = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness).CurrentBrightness"],
                         capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW).stdout.strip()
    cur = int(get.splitlines()[0]) if get and get.splitlines()[0].isdigit() else 50
    new = max(0, min(100, level if level is not None else cur + delta))
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{new})"],
                   capture_output=True, timeout=10, creationflags=NO_WINDOW)
    return new


@skill("desktop.brightness", title={"ru": "Яркость экрана: «яркость 40», «ярче», «темнее»"},
       patterns={"ru": [r"^(?:джарвис )?(?:сделай |поставь |установи )?яркост\w*(?: экрана)?(?: на| в)? (\d{1,3})(?: процент\w*)?$",
                        r"^(?:джарвис )?(?:сделай )?(?:экран )?(ярче|темнее|потемнее|поярче)(?: экран)?$",
                        r"^(?:джарвис )?(?:яркость|яркости) (на максимум|на минимум|максимум|минимум|побольше|поменьше)$"]},
       examples={"ru": ["Яркость 40", "Сделай ярче"]}, priority=6)
def bright(ctx: Ctx) -> str:
    n = ctx.norm
    num = re.search(r"(\d{1,3})", n)
    try:
        if num:
            v = brightness(int(num.group(1)))
        elif re.search(r"максимум", n):
            v = brightness(100)
        elif re.search(r"минимум", n):
            v = brightness(10)
        else:
            v = brightness(delta=20 if re.search(r"ярче|поярче|побольше", n) else -20)
    except Exception as e:  # noqa: BLE001
        return f"Не получилось поменять яркость: {str(e)[:80]}"
    return f"Яркость {v}%."


@skill("desktop.volume_level", title={"ru": "Громкость точно: «громкость 30», «на максимум»"},
       patterns={"ru": [r"^(?:джарвис )?(?:сделай |поставь |установи )?(?:общую )?громкост\w*(?: звука)?(?: на| в)? (\d{1,3})(?: процент\w*)?$",
                        r"^(?:джарвис )?(?:громкость|звук) (?:на )?(максимум|минимум|ноль|полную)$"]},
       examples={"ru": ["Громкость 30", "Громкость на максимум"]}, priority=5)
def volume_level(ctx: Ctx) -> str:
    n = ctx.norm
    num = re.search(r"(\d{1,3})", n)
    level = int(num.group(1)) if num else 100 if re.search(r"максимум|полную", n) else 0 if "ноль" in n else 10
    macros = sys.modules.get("jarvis_plugin_macros")
    try:
        macros._master_volume(level)
    except Exception as e:  # noqa: BLE001
        return f"Не получилось: {str(e)[:80]}"
    return f"Громкость {min(100, level)}%."


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

SEARCH_ROOTS = [Path.home() / "Desktop", Path.home() / "Documents", Path.home() / "Downloads", Path.home() / "Pictures",
                Path.home() / "Videos", Path.home() / "Music", Path("D:/")]
SKIP_DIRS = {"$recycle.bin", "system volume information", "windows", "program files", "program files (x86)",
             "appdata", "node_modules", ".git", ".venv", "venv", "__pycache__", "steam", "steamapps", "programdata"}


def find_files(query: str, limit: int = 8, seconds: float = 4.0) -> list[Path]:
    """Files whose name contains the words (Russian or English), newest first; stops after `seconds`."""
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
    if not words:
        return []
    finder = sys.modules.get("jarvis_plugin_appfinder")
    keys = [finder.key(w) for w in words] if finder else []
    hits, t0 = [], time.time()
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        stack = [(root, 0)]
        while stack and time.time() - t0 < seconds:
            d, depth = stack.pop()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                name = e.name.lower()
                if e.is_dir(follow_symlinks=False):
                    if depth < 5 and name not in SKIP_DIRS and not name.startswith("."):
                        stack.append((Path(e.path), depth + 1))
                    continue
                k = finder.key(name) if finder else name
                if all(w in name for w in words) or (keys and all(kk in k for kk in keys)):
                    hits.append(Path(e.path))
    hits = list(dict.fromkeys(hits))
    hits.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return hits[:limit]


@skill("desktop.find_file", title={"ru": "Найти файл на компьютере и открыть"},
       patterns={"ru": [r"^(?:джарвис )?(?:найди|поищи|где) (?:мой |мою |мои )?(?:файл\w*|документ\w*|фото\w*|картинк\w*|видео\w*|папк\w*) (.+)$",
                        r"^(?:джарвис )?открой (?:файл|документ) (.+)$"]},
       examples={"ru": ["Найди файл договор", "Открой документ резюме"]}, priority=8)
def find_file(ctx: Ctx) -> str:
    q = ctx.group(1).strip(" ?")
    hits = find_files(q)
    if not hits:
        return f"Не нашёл файлов «{q}» в документах, загрузках, на рабочем столе и диске D, сэр."
    core.emit({"type": "card", "title": f"Файлы · {q}", "ttl": 60000,
               "text": "\n".join(f"{i + 1}. {p.name}   —   {p.parent}" for i, p in enumerate(hits))})
    if ctx.norm.startswith(("открой", "джарвис открой")) or len(hits) == 1:
        os.startfile(str(hits[0]))
        return f"Открываю {hits[0].name}."
    return f"Нашёл {len(hits)}, сэр. Самый свежий: {hits[0].name}. Список в окне — скажите «открой файл …» для нужного."


@skill("desktop.last_download", title={"ru": "Открыть последний скачанный файл"},
       patterns={"ru": [r"(?:открой|покажи) (?:последн\w+ )?(?:скачанн\w+ файл|загрузк\w*|скачанное)$",
                        r"(?:открой|покажи) последн\w+ (?:скачанн\w+|загруженн\w+)(?: файл)?$"]},
       examples={"ru": ["Открой последний скачанный файл"]}, priority=9)
def last_download(ctx: Ctx):
    if not re.search(r"последн|скачанн", ctx.norm):
        return None          # plain «открой загрузки» opens the folder (apps plugin)
    d = Path.home() / "Downloads"
    files = [p for p in d.iterdir() if p.is_file() and not p.name.endswith((".crdownload", ".part", ".tmp"))] if d.exists() else []
    if not files:
        return "В загрузках пусто, сэр."
    newest = max(files, key=lambda p: p.stat().st_mtime)
    if newest.suffix.lower() in (".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".scr"):
        subprocess.Popen(["explorer", "/select,", str(newest)])
        return f"Последний файл — программа {newest.name}. Показал её в папке, запускайте сами, сэр."
    os.startfile(str(newest))
    return f"Открываю {newest.name}."


# ---------------------------------------------------------------------------
# Phrase translation and currency
# ---------------------------------------------------------------------------

LANGS = {"английск": "английский", "японск": "японский", "узбекск": "узбекский", "русск": "русский", "немецк": "немецкий",
         "французск": "французский", "испанск": "испанский", "китайск": "китайский", "корейск": "корейский",
         "турецк": "турецкий", "арабск": "арабский", "итальянск": "итальянский", "казахск": "казахский"}


@skill("desktop.translate_phrase", title={"ru": "Перевести фразу: «как по-английски …», «переведи на японский …»"},
       patterns={"ru": [r"^(?:джарвис )?как (?:будет )?(?:по |на )?(английск\w*|японск\w*|узбекск\w*|немецк\w*|французск\w*|испанск\w*|китайск\w*|корейск\w*|турецк\w*|арабск\w*|итальянск\w*|казахск\w*|русск\w*)(?: будет| сказать)? (.+)$",
                        r"^(?:джарвис )?переведи (?:фразу |слово |текст )?на (английск\w*|японск\w*|узбекск\w*|немецк\w*|французск\w*|испанск\w*|китайск\w*|корейск\w*|турецк\w*|арабск\w*|итальянск\w*|казахск\w*|русск\w*)(?: язык)? (.+)$"]},
       examples={"ru": ["Как по-английски «спасибо за помощь»?", "Переведи на японский я люблю кофе"]}, priority=6)
def translate_phrase(ctx: Ctx) -> str:
    lang = next((v for k, v in LANGS.items() if ctx.group(1).startswith(k)), "английский")
    raw = re.search(r"(?:будет|сказать|язык|" + re.escape(ctx.group(1)) + r")\s+(.+)$", ctx.text, re.I)
    phrase = (raw.group(1) if raw else ctx.group(2)).strip(" ?«»\"")
    pro = sys.modules.get("jarvis_plugin_pro")
    extra = " Для японского добавь чтение хираганой в скобках." if lang == "японский" else ""
    out = pro._write(f"Переведи на {lang} язык фразу: «{phrase}». Ответ — только перевод, одна строка.{extra}", 120) if pro else ""
    if not out:
        return "Не получилось перевести, сэр."
    pro.set_clipboard(out.split("(")[0].strip() if lang == "японский" else out)
    return f"{out} — уже в буфере, сэр."


CUR = {"доллар": "USD", "бакс": "USD", "евро": "EUR", "рубл": "RUB", "сум": "UZS", "тенге": "KZT", "юан": "CNY",
       "фунт": "GBP", "лир": "TRY", "вон": "KRW", "иен": "JPY", "йен": "JPY", "дирхам": "AED"}


MANY = {"USD": "долларов", "EUR": "евро", "RUB": "рублей", "UZS": "сумов", "KZT": "тенге", "CNY": "юаней", "GBP": "фунтов",
        "TRY": "лир", "KRW": "вон", "JPY": "иен", "AED": "дирхамов"}


def _code(word: str) -> str | None:
    return next((v for k, v in CUR.items() if word.startswith(k)), None)


@skill("desktop.convert", title={"ru": "Конвертер валют: «100 долларов в сумах»"},
       patterns={"ru": [r"(?:сколько (?:будет )?|переведи |конвертируй )?(\d[\d\s.,]*)\s*(доллар\w*|бакс\w*|евро|рубл\w*|сум\w*|тенге|юан\w*|фунт\w*|лир\w*|вон\w*|иен\w*|йен\w*|дирхам\w*) (?:в|на) (доллар\w*|бакс\w*|евро|рубл\w*|сум\w*|тенге|юан\w*|фунт\w*|лир\w*|вон\w*|иен\w*|йен\w*|дирхам\w*)"]},
       examples={"ru": ["Сколько будет 100 долларов в сумах", "Переведи 50 евро в рубли"]}, priority=5)
def convert(ctx: Ctx) -> str:
    import requests
    amount = float(re.sub(r"\s", "", ctx.group(1)).replace(",", "."))
    a, b = _code(ctx.group(2)), _code(ctx.group(3))
    if not a or not b:
        return None
    try:
        js = requests.get(f"https://open.er-api.com/v6/latest/{a}", timeout=6).json()
        rate = js["rates"][b]
    except Exception as e:  # noqa: BLE001
        return f"Курсы сейчас недоступны: {str(e)[:60]}"
    res = amount * rate
    fmt = (f"{res:,.0f}" if res >= 100 else f"{res:,.2f}").replace(",", " ")
    return f"{ctx.group(1).strip()} {ctx.group(2)} — это {fmt} {MANY.get(b, b)}."


core._LONG_OK.update({"desktop.find_file", "desktop.translate_phrase", "desktop.convert"})
