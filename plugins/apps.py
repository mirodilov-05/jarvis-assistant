"""Open/close programs and websites, search the web and YouTube."""

import csv
import difflib
import io
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import core
from core import Ctx, skill

NO_WINDOW = 0x08000000

SITES = {
    "ютуб": "https://www.youtube.com", "youtube": "https://www.youtube.com", "yutub": "https://www.youtube.com",
    "гугл": "https://www.google.com", "google": "https://www.google.com", "gugl": "https://www.google.com",
    "яндекс": "https://ya.ru", "yandex": "https://ya.ru",
    "почту": "https://mail.google.com", "почта": "https://mail.google.com", "pochta": "https://mail.google.com",
    "pochtani": "https://mail.google.com", "gmail": "https://mail.google.com", "джимейл": "https://mail.google.com",
    "вконтакте": "https://vk.com", "вк": "https://vk.com", "инстаграм": "https://www.instagram.com",
    "instagram": "https://www.instagram.com", "instagramni": "https://www.instagram.com",
    "гитхаб": "https://github.com", "github": "https://github.com", "чатгпт": "https://chatgpt.com",
    "chatgpt": "https://chatgpt.com", "переводчик": "https://translate.yandex.ru", "tarjimon": "https://translate.yandex.ru",
    "карты": "https://yandex.ru/maps", "xarita": "https://yandex.ru/maps", "погоду": "https://yandex.ru/pogoda",
    "джарвис": "http://127.0.0.1:50778", "jarvis": "http://127.0.0.1:50778", "openjarvis": "http://127.0.0.1:5173",
    # music & video
    "яндекс музыку": "https://music.yandex.ru", "яндекс музыка": "https://music.yandex.ru", "музыку": "https://music.yandex.ru",
    "yandex music": "https://music.yandex.ru", "yandex musiqa": "https://music.yandex.ru", "musiqa": "https://music.yandex.ru",
    "spotify web": "https://open.spotify.com", "вк музыку": "https://vk.com/audio", "кинопоиск": "https://www.kinopoisk.ru",
    "нетфликс": "https://www.netflix.com", "netflix": "https://www.netflix.com", "твич": "https://www.twitch.tv",
    "twitch": "https://www.twitch.tv", "тикток": "https://www.tiktok.com", "tiktok": "https://www.tiktok.com",
    "ютуб музыку": "https://music.youtube.com", "youtube music": "https://music.youtube.com",
    # social & messengers (web versions)
    "фейсбук": "https://www.facebook.com", "facebook": "https://www.facebook.com", "твиттер": "https://x.com",
    "икс": "https://x.com", "linkedin": "https://www.linkedin.com", "линкедин": "https://www.linkedin.com",
    "телеграм веб": "https://web.telegram.org", "ватсап веб": "https://web.whatsapp.com",
    # work & tools
    "гугл диск": "https://drive.google.com", "google drive": "https://drive.google.com", "документы гугл": "https://docs.google.com",
    "гугл документы": "https://docs.google.com", "таблицы": "https://sheets.google.com", "календарь": "https://calendar.google.com",
    "kalendar": "https://calendar.google.com", "claude": "https://claude.ai", "клод": "https://claude.ai",
    "википедию": "https://ru.wikipedia.org", "википедия": "https://ru.wikipedia.org", "переводчик гугл": "https://translate.google.com",
    "яндекс диск": "https://disk.yandex.ru", "почту яндекс": "https://mail.yandex.ru", "яндекс почту": "https://mail.yandex.ru",
    # shopping & local services (Uzbekistan / CIS)
    "узум": "https://uzum.uz", "uzum": "https://uzum.uz", "олх": "https://www.olx.uz", "olx": "https://www.olx.uz",
    "озон": "https://www.ozon.ru", "ozon": "https://www.ozon.ru", "вайлдберриз": "https://www.wildberries.ru",
    "wildberries": "https://www.wildberries.ru", "алиэкспресс": "https://aliexpress.ru", "hh": "https://hh.uz",
    "хедхантер": "https://hh.uz", "яндекс такси": "https://taxi.yandex.uz", "кун уз": "https://kun.uz", "kun uz": "https://kun.uz",
    "газета уз": "https://www.gazeta.uz", "gazeta": "https://www.gazeta.uz", "новости": "https://kun.uz",
    "yangiliklar": "https://kun.uz",
}

# when the desktop app isn't installed, open its web version instead
WEB_FALLBACK = {
    "telegram": "https://web.telegram.org", "телеграм": "https://web.telegram.org", "телегу": "https://web.telegram.org",
    "whatsapp": "https://web.whatsapp.com", "ватсап": "https://web.whatsapp.com", "вотсап": "https://web.whatsapp.com",
    "vatsap": "https://web.whatsapp.com", "spotify": "https://open.spotify.com", "спотифай": "https://open.spotify.com",
    "discord": "https://discord.com/app", "дискорд": "https://discord.com/app", "instagram": "https://www.instagram.com",
    "zoom": "https://app.zoom.us", "зум": "https://app.zoom.us", "word": "https://www.office.com", "ворд": "https://www.office.com",
    "excel": "https://www.office.com", "эксель": "https://www.office.com", "chatgpt": "https://chatgpt.com",
}

COMMANDS = {
    "блокнот": "notepad.exe", "notepad": "notepad.exe", "bloknot": "notepad.exe",
    "калькулятор": "calc.exe", "kalkulyator": "calc.exe",
    "проводник": "explorer.exe", "провод": "explorer.exe", "papkalar": "explorer.exe", "provodnik": "explorer.exe",
    "диспетчер задач": "taskmgr.exe", "vazifalar dispetcheri": "taskmgr.exe",
    "параметры": "ms-settings:", "настройки": "ms-settings:", "sozlamalar": "ms-settings:",
    "пейнт": "mspaint.exe", "paint": "mspaint.exe", "командную строку": "cmd.exe", "терминал": "wt.exe",
    "загрузки": str(Path.home() / "Downloads"), "yuklamalar": str(Path.home() / "Downloads"),
    "документы": str(Path.home() / "Documents"), "hujjatlar": str(Path.home() / "Documents"),
    "рабочий стол": str(Path.home() / "Desktop"), "ish stoli": str(Path.home() / "Desktop"),
    "корзину": "shell:RecycleBinFolder", "korzina": "shell:RecycleBinFolder", "savat": "shell:RecycleBinFolder",
    "картинки": str(Path.home() / "Pictures"), "rasmlar": str(Path.home() / "Pictures"),
    "заметки джарвиса": str(Path(__file__).resolve().parents[1] / "data"),
}

ALIASES = {  # spoken name -> start-menu name fragment
    "браузер": "yandex", "brauzer": "yandex", "яндекс браузер": "yandex", "хром": "chrome", "гугл хром": "chrome",
    "xrom": "chrome", "телеграм": "telegram", "телегу": "telegram", "телеграмм": "telegram",
    "дискорд": "discord", "diskord": "discord", "стим": "steam", "ворд": "word", "vord": "word",
    "эксель": "excel", "eksel": "excel", "пауэр поинт": "powerpoint", "спотифай": "spotify",
    "вс код": "visual studio code", "вскод": "visual studio code", "обс": "obs", "зум": "zoom",
    "ватсап": "whatsapp", "вотсап": "whatsapp", "vatsap": "whatsapp", "эдж": "edge",
}

PROCESS_ALIASES = {
    "telegram": "telegram.exe", "телеграм": "telegram.exe", "браузер": "browser.exe", "brauzer": "browser.exe",
    "яндекс": "browser.exe", "хром": "chrome.exe", "chrome": "chrome.exe", "блокнот": "notepad.exe",
    "bloknot": "notepad.exe", "калькулятор": "calculatorapp.exe", "kalkulyator": "calculatorapp.exe",
    "дискорд": "discord.exe", "discord": "discord.exe", "стим": "steam.exe", "steam": "steam.exe",
    "ворд": "winword.exe", "word": "winword.exe", "эксель": "excel.exe", "excel": "excel.exe",
    "ватсап": "whatsapp.exe", "whatsapp": "whatsapp.exe", "vatsap": "whatsapp.exe", "spotify": "spotify.exe",
}

_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
})

_index: dict[str, str] = {}


def app_index() -> dict[str, str]:
    if _index:
        return _index
    roots = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
        Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
        Path.home() / "Desktop",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    ]
    for root in roots:
        if root.exists():
            for p in root.rglob("*"):
                if p.suffix.lower() in {".lnk", ".url", ".appref-ms"} and "uninstall" not in p.stem.lower():
                    _index.setdefault(p.stem.lower(), str(p))
    try:  # Microsoft Store apps (Telegram, WhatsApp, ...)
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, timeout=30, creationflags=NO_WINDOW,
        )
        apps = json.loads(out.stdout.decode("utf-8", errors="replace") or "[]")
        for app in apps if isinstance(apps, list) else [apps]:
            name = (app.get("Name") or "").lower()
            if name and "uninstall" not in name:
                _index.setdefault(name, "shell:AppsFolder\\" + app["AppID"])
    except Exception:  # noqa: BLE001
        pass
    return _index


def find_app(name: str):
    idx = app_index()
    name = name.strip().lower()
    for c in filter(None, [name, ALIASES.get(name, ""), name.translate(_TRANSLIT)]):
        if c in idx:  # exact name first ("steam", not "steam support center")
            return c, idx[c]
        for test in (lambda k: k.startswith(c + " "), lambda k: c in k.split(), lambda k: c in k):
            hits = sorted((k for k in idx if test(k)), key=len)  # shortest = most likely the main app
            hits = [k for k in hits if not re.search(r"(support|help|readme|manual|справк|документац|website|сайт)", k)] or hits
            if hits:
                return hits[0], idx[hits[0]]
        close = difflib.get_close_matches(c, list(idx), n=1, cutoff=0.75)
        if close:
            return close[0], idx[close[0]]
    return None


def _strip_uz_suffix(name: str) -> str:
    return re.sub(r"(ni|ga|dan|da)$", "", name) if len(name) > 4 else name


SHORTCUTS_FILE = core.DATA / "shortcuts.json"  # {"name": "https://... or C:\\path\\app.exe"}


def shortcuts() -> dict[str, str]:
    return core.load_json(SHORTCUTS_FILE, {})


def save_shortcut(name: str, target: str) -> None:
    with core.file_lock:
        data = shortcuts()
        data[name.strip().lower()] = target.strip()
        core.save_json(SHORTCUTS_FILE, data)


def delete_shortcut(name: str) -> None:
    with core.file_lock:
        data = shortcuts()
        data.pop(name.strip().lower(), None)
        core.save_json(SHORTCUTS_FILE, data)


def clipboard_text() -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
                         capture_output=True, timeout=10, creationflags=NO_WINDOW)
    return out.stdout.decode("utf-8", errors="replace").strip()


_URL_RE = re.compile(r"(https?://\S+|www\.\S+|[\w-]+\.(?:com|ru|uz|org|net|io|ai|tv|me)(?:/\S*)?)")


def open_target(ctx: Ctx, target: str) -> str:
    target = target.strip()
    candidates = [target, _strip_uz_suffix(target)] if ctx.lang == "uz" else [target]
    custom = shortcuts()
    for t in candidates:
        if t in custom:
            os.startfile(custom[t])
            return ctx.t(f"Открываю {t}.", f"{t} ochilmoqda.")
        close = difflib.get_close_matches(t, list(custom), n=1, cutoff=0.8)
        if close:
            os.startfile(custom[close[0]])
            return ctx.t(f"Открываю {close[0]}.", f"{close[0]} ochilmoqda.")
    for t in candidates:
        if t in SITES:
            os.startfile(SITES[t])
            return ctx.t(f"Открываю {t}.", f"{t} ochilmoqda.")
        if t in COMMANDS:
            os.startfile(COMMANDS[t])
            return ctx.t(f"Открываю {t}.", f"{t} ochilmoqda.")
        if re.match(r"^[\w.-]+\.(ru|com|org|net|io|uz|ai|tv)$", t):
            os.startfile("https://" + t)
            return ctx.t(f"Открываю сайт {t}.", f"{t} sayti ochilmoqda.")
    finder = sys.modules.get("jarvis_plugin_appfinder")
    for t in candidates:   # learned Russian names and sound-alike first: exact and quick
        hit = finder.find(t, use_brain=False) if finder else None
        if hit:
            os.startfile(hit[1])
            return ctx.t(f"Запускаю {hit[0]}.", f"{hit[0]} ishga tushirilmoqda.")
    for t in candidates:
        found = find_app(t)
        if found:
            os.startfile(found[1])
            return ctx.t(f"Запускаю {found[0]}.", f"{found[0]} ishga tushirilmoqda.")
    games = sys.modules.get("jarvis_plugin_games")
    for t in candidates:
        game = games.find_game(t) if games else None
        if game:
            os.startfile(game["launch"])
            return ctx.t(f"Запускаю игру {game['name']}.", f"{game['name']} o'yini ishga tushirilmoqda.")
    finder = sys.modules.get("jarvis_plugin_appfinder")
    for t in candidates:
        hit = finder.find(t) if finder else None
        if hit:
            os.startfile(hit[1])
            return ctx.t(f"Запускаю {hit[0]}.", f"{hit[0]} ishga tushirilmoqda.")
    for t in candidates:
        if t in WEB_FALLBACK:
            os.startfile(WEB_FALLBACK[t])
            return ctx.t(f"Приложение не установлено, открываю {t} в браузере.", f"{t} brauzerda ochilmoqda.")
    return ctx.t(f"Не нашёл программу «{target}». Скажите название, как в меню Пуск.",
                 f"«{target}» dasturini topmadim. Pusk menyusidagi nomini ayting.")


@skill(
    "apps.open_link",
    title={"ru": "Открыть ссылку из буфера обмена", "uz": "Buferdagi havolani ochish"},
    patterns={"ru": [r"(открой|перейди по) (ссылк\w*|линк\w*)(?: из буфера)?$", r"открой (то )?что (я )?скопировал"],
              "uz": [r"(havola|ssilka|link)\w* (och|ochib ber)\w*$", r"nusxalagan\w* (narsani )?och"]},
    examples={"ru": ["Открой ссылку"], "uz": ["Havolani och"]},
    priority=50,
)
def open_link(ctx: Ctx) -> str:
    text = clipboard_text()
    m = _URL_RE.search(text)
    if not m:
        return ctx.t("В буфере обмена нет ссылки. Скопируйте ссылку и повторите.",
                     "Buferda havola yo'q. Havolani nusxalab, qayta ayting.")
    url = m.group(1)
    if not url.startswith("http"):
        url = "https://" + url
    os.startfile(url)
    return ctx.t("Открываю ссылку.", "Havola ochilmoqda.")


@skill(
    "apps.save_link",
    title={"ru": "Сохранить ссылку из буфера под именем", "uz": "Buferdagi havolani nom bilan saqlash"},
    patterns={"ru": [r"(?:сохрани|запомни) (?:ссылку|линк|сайт)(?: из буфера)? (?:как|под именем|под названием) (.+)$"],
              "uz": [r"havola\w* (.+?) (?:deb|nomi bilan) saqla\w*$"]},
    examples={"ru": ["Сохрани ссылку как работа"], "uz": ["Havolani ish deb saqla"]},
    priority=49,
)
def save_link(ctx: Ctx) -> str:
    text = clipboard_text()
    m = _URL_RE.search(text)
    if not m:
        return ctx.t("В буфере обмена нет ссылки.", "Buferda havola yo'q.")
    url = m.group(1) if m.group(1).startswith("http") else "https://" + m.group(1)
    name = ctx.group(1)
    save_shortcut(name, url)
    return ctx.t(f"Сохранил. Теперь скажите «открой {name}».", f"Saqlandi. Endi «{name}ni och» deng.")


@skill(
    "apps.open",
    title={"ru": "Открыть программу, папку или сайт", "uz": "Dastur, papka yoki saytni ochish"},
    patterns={
        "ru": [r"^(?:джарвис )?(?:открой|запусти|открыть|запустить)(?: мне)? (?:программу |приложение |сайт |папку )?(.+)$"],
        "uz": [r"^(?:jarvis )?(.+?) (?:och|ochib ber|ochgin|ochib qoy|ishga tushir)\w*$",
               r"^(?:jarvis )?(?:och|ishga tushir)\w* (.+)$"],
    },
    examples={"ru": ["Открой телеграм", "Открой загрузки", "Открой ютуб"], "uz": ["Telegramni och", "Brauzerni och"]},
    priority=60,
)
def open_app(ctx: Ctx) -> str:
    return open_target(ctx, ctx.group(1))


def _processes() -> list[str]:
    out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, creationflags=NO_WINDOW)
    text = out.stdout.decode("cp866", errors="replace")
    return sorted({row[0].lower() for row in csv.reader(io.StringIO(text)) if row})


@skill(
    "apps.close",
    title={"ru": "Закрыть программу", "uz": "Dasturni yopish"},
    patterns={
        "ru": [r"^(?:джарвис )?(?:закрой|выключи|заверши) (?:программу |приложение )?(.+)$"],
        "uz": [r"^(?:jarvis )?(.+?) (?:yop|yopib qoy|yopgin)\w*$"],
    },
    examples={"ru": ["Закрой блокнот"], "uz": ["Telegramni yop"]},
    priority=65,
)
def close_app(ctx: Ctx):
    name = ctx.group(1).strip()
    if ctx.lang == "uz":
        name = _strip_uz_suffix(name)
    procs = _processes()
    exe = PROCESS_ALIASES.get(name)
    if not exe or exe not in procs:
        key = name.translate(_TRANSLIT).replace(" ", "")
        exe = next((p for p in procs if p.startswith(key)), None)
    if not exe:
        finder = sys.modules.get("jarvis_plugin_appfinder")
        exe = finder.find_running(name) if finder else None
    if not exe:
        return ctx.t(f"Не нашёл запущенную программу «{name}».", f"«{name}» ishlab turgan dastur topilmadi.")
    subprocess.run(["taskkill", "/IM", exe], capture_output=True, creationflags=NO_WINDOW)
    return ctx.t(f"Закрываю {exe}.", f"{exe} yopilmoqda.")


@skill(
    "apps.youtube",
    title={"ru": "Найти видео на YouTube", "uz": "YouTube'dan video qidirish"},
    patterns={
        "ru": [r"(?:найди|включи|поставь|покажи) (?:на|в) ютубе? (.+)$", r"(?:найди|включи) (?:видео|клип) (.+?)(?: на ютубе)?$"],
        "uz": [r"(?:youtubedan|yutubdan|youtubeda|yutubda) (.+?) (?:qidir|top|qoy|och)\w*$", r"(.+?) (?:ni )?(?:youtubedan|yutubdan) (?:qidir|top|qoy)\w*$"],
    },
    examples={"ru": ["Найди на ютубе рецепт плова"], "uz": ["YouTube'dan palov retseptini qidir"]},
    priority=55,
)
def youtube(ctx: Ctx) -> str:
    q = ctx.group(1)
    os.startfile("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
    return ctx.t(f"Ищу на YouTube: {q}.", f"YouTube'dan qidiryapman: {q}.")


@skill(
    "apps.music",
    title={"ru": "Включить музыку (Яндекс Музыка)", "uz": "Musiqa qo'yish (Yandex Musiqa)"},
    patterns={
        "ru": [r"^(?:джарвис )?(?:включи|поставь|запусти|найди)(?: мне)? (?:песню|трек|альбом|плейлист|музыку|группу|исполнителя) (.+?)(?: (?:на|в) яндекс музык\w*)?$",
               r"^(?:джарвис )?(?:включи|поставь|найди) (.+?) (?:на|в) яндекс музык\w*$",
               r"^(?:джарвис )?(?:включи|поставь)(?: мне)? (музыку|что нибудь послушать|мою волну|радио)$"],
        "uz": [r"^(?:jarvis )?(.+?) (?:qoshigini|qoshiqni|musiqasini|trekini) (?:qoy|och|top)\w*$",
               r"^(?:jarvis )?(musiqa|qoshiq) (?:qoy|och)\w*$"],
    },
    examples={"ru": ["Включи музыку", "Включи песню Шахзода", "Поставь Imagine Dragons на Яндекс Музыке"],
              "uz": ["Musiqa qo'y", "Shahzoda qo'shig'ini qo'y"]},
    priority=54,
)
def music(ctx: Ctx) -> str:
    q = ctx.group(1)
    service = core.CONFIG.get("music", {}).get("service", "yandex")
    if q in ("музыку", "что нибудь послушать", "мою волну", "радио", "musiqa", "qoshiq"):
        url = "https://music.yandex.ru" if service == "yandex" else "https://music.youtube.com"
        os.startfile(url)
        return ctx.t("Включаю музыку.", "Musiqa ochilmoqda.")
    url = (f"https://music.yandex.ru/search?text={urllib.parse.quote(q)}" if service == "yandex"
           else f"https://music.youtube.com/search?q={urllib.parse.quote(q)}")
    os.startfile(url)
    return ctx.t(f"Ищу в Яндекс Музыке: {q}.", f"Yandex Musiqada qidiryapman: {q}.")


@skill(
    "apps.browser",
    title={"ru": "Открыть сайт или запрос в браузере", "uz": "Saytni brauzerda ochish"},
    patterns={"ru": [r"^(?:джарвис )?(?:открой|покажи) в браузере (.+)$", r"^(?:джарвис )?(?:зайди|перейди) на (?:сайт )?(.+)$"],
              "uz": [r"^(?:jarvis )?brauzerda (.+?) (?:och|korsat)\w*$", r"^(?:jarvis )?(.+?) saytiga kir\w*$"]},
    examples={"ru": ["Открой в браузере кун уз", "Зайди на сайт olx.uz"], "uz": ["Brauzerda kun.uz ni och"]},
    priority=52,
)
def browser(ctx: Ctx) -> str:
    q = ctx.group(1).strip()
    domain = re.search(r"((?:https?://)?[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}(?:/\S*)?)", ctx.text, re.I)
    if q in SITES:
        url = SITES[q]
    elif domain:
        url = domain.group(1) if domain.group(1).startswith("http") else "https://" + domain.group(1)
        q = domain.group(1)
    else:
        url = "https://yandex.ru/search/?text=" + urllib.parse.quote(q)
    os.startfile(url)
    return ctx.t(f"Открываю в браузере: {q}.", f"Brauzerda ochilmoqda: {q}.")


@skill(
    "apps.search",
    title={"ru": "Найти в интернете", "uz": "Internetdan qidirish"},
    patterns={
        "ru": [r"^(?:джарвис )?(?:найди|поищи|загугли|погугли)(?: в интернете| в гугле| в яндексе)? (.+)$"],
        "uz": [r"^(?:jarvis )?(.+?) (?:ni )?(?:internetdan |googledan |guguldan )?(?:qidir|topib ber)\w*$",
               r"^(?:jarvis )?(?:internetdan |googledan )?qidir\w* (.+)$"],
    },
    examples={"ru": ["Найди в интернете курс доллара"], "uz": ["Dollar kursini internetdan qidir"]},
    priority=70,
)
def search(ctx: Ctx) -> str:
    q = ctx.group(1)
    os.startfile("https://yandex.ru/search/?text=" + urllib.parse.quote(q))
    return ctx.t(f"Ищу в интернете: {q}.", f"Internetdan qidiryapman: {q}.")
