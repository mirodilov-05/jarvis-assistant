"""V3 instant commands (no AI needed, work even when the free cloud limit is busy):
rates, movies, per-app volume, context «тише», «сохрани это», focus shield, character status."""

import re

import core
from core import Ctx, skill


def _v3():
    import tools.v3 as v3
    return v3


@skill("v3.rates", title={"ru": "Курсы: биткоин, эфир, USDT, доллар (рубли, сумы)"},
       patterns={"ru": [r"(?:какой |скажи |какие )?курс\w* (биткоин\w*|битка|btc|эфир\w*|eth|usdt|тезер\w*|доллар\w*|валют\w*|крипт\w*)",
                        r"сколько (?:сейчас )?стоит (биткоин|биток|эфир|usdt|доллар)\w*",
                        r"^(?:курсы|курсы валют|курс)$"]},
       examples={"ru": ["Курс биткоина", "Сколько стоит доллар", "Курсы валют"]}, priority=6)
def rates(ctx: Ctx) -> str:
    w = ctx.norm
    what = "bitcoin" if re.search(r"битк|биток|btc", w) else "ethereum" if re.search(r"эфир|eth", w) else \
        "usdt" if re.search(r"usdt|тезер", w) else "usd" if "доллар" in w else ""
    return _v3().rates(what)


@skill("v3.movie", title={"ru": "Найти фильм или сериал (Кинопоиск)"},
       patterns={"ru": [r"(?:включи|найди|хочу посмотреть|поставь|открой)\s+(?:фильм|сериал|кино|мультфильм)\s+(.+)$"]},
       examples={"ru": ["Включи фильм Интерстеллар"]}, priority=7)
def movie(ctx: Ctx) -> str:
    return _v3().watch_movie(ctx.group(1))


APPS = r"(игр\w*|дискорд\w*|discord|браузер\w*|хром\w*|музык\w*|телеграм\w*|ютуб\w*|youtube|спотиф\w*|стим\w*)"


@skill("v3.app_volume", title={"ru": "Громкость отдельной программы (игра, дискорд, браузер, музыка)"},
       patterns={"ru": [r"(?:сделай |убавь |прибавь |поставь )?(?:звук |громкость )?" + APPS +
                        r"\s+(тише|громче|на \d+|без звука|выключи звук|включи звук)",
                        r"(?:выключи|убери|включи|верни) звук (?:в |у )?" + APPS,
                        r"(?:приглуши|заглуши|убавь|прибавь)\s+" + APPS + r"(?:\s+(?:на|до)\s+(\d+))?",
                        r"(?:громкость|звук) " + APPS + r"(?: на)? (\d+)"]},
       examples={"ru": ["Сделай игру тише", "Дискорд на 40", "Выключи звук в браузере"]}, priority=6)
def app_volume(ctx: Ctx) -> str:
    n = ctx.norm
    app = re.search(APPS, n).group(1)
    app = "игра" if app.startswith("игр") else app
    num = re.search(r"(\d+)", n)
    if "без звука" in n or re.search(r"(выключи|убери) звук|заглуши", n):
        return _v3().app_volume(app, mute=True)
    if re.search(r"(включи|верни) звук", n):
        return _v3().app_volume(app, mute=False)
    if num:
        return _v3().app_volume(app, level=float(num.group(1)))
    if "приглуши" in n:
        return _v3().app_volume(app, level=30)
    return _v3().app_volume(app, change=-30 if re.search(r"тише|убавь", n) else 25)


@skill("v3.quieter", title={"ru": "«Тише» с учётом экрана: в игре — только игра"},
       patterns={"ru": [r"^(?:джарвис )?(?:тише|потише|сделай тише|чуть тише)$"]},
       examples={"ru": ["Тише"]}, priority=4)
def quieter(ctx: Ctx):
    if not core.CONFIG.get("_game_mode"):
        return None     # not in a game: the normal «тише» (master volume) answers
    return _v3().quieter_here()


@skill("v3.save_this", title={"ru": "«Сохрани это»: ссылка в браузере, код в редакторе"},
       patterns={"ru": [r"^(?:джарвис )?(?:сохрани|запомни|запиши) (?:это|эту ссылку|этот код|вот это|что на экране)$"]},
       examples={"ru": ["Сохрани это"]}, priority=5)
def save_this(ctx: Ctx) -> str:
    return _v3().save_this()


@skill("v3.focus", title={"ru": "Фокус-щит: закрываю YouTube, TikTok, Steam на время работы"},
       patterns={"ru": [r"(?:включи|запусти|начни)\s+(?:фокус\w*|фокус-щит|режим фокуса|щит)(?:\s+на)?\s*(\d+)?",
                        r"(?:выключи|останови|отключи|сними)\s+(?:фокус\w*|фокус-щит|щит)",
                        r"^фокус(?: на)? (\d+)(?: минут\w*)?$"]},
       examples={"ru": ["Включи фокус на 25 минут", "Выключи фокус"]}, priority=5)
def focus(ctx: Ctx) -> str:
    import pcx
    if re.search(r"выключи|останови|отключи|сними", ctx.norm):
        return pcx.focus_stop()
    num = re.search(r"(\d+)", ctx.norm)
    minutes = float(num.group(1)) if num else 50.0
    if re.search(r"\d+\s*час", ctx.norm):
        minutes *= 60
    return pcx.focus_start(minutes)


@skill("v3.focus_add", title={"ru": "Фокус-щит: закрывать ещё и это (сайт или программу)"},
       patterns={"ru": [r"(?:добавь|закрывай|закрывать|блокируй) (?P<w>[\w.\- ]{2,40}?) (?:в|для|во время) (?:режим\w* фокуса|фокус\w*|фокус-щит\w*)$",
                        r"(?:в|во время) (?:режим\w* фокуса|фокус\w*) (?:закрывай|закрывать|блокируй)(?: тоже| ещё| еще)? (?P<w>[\w.\- ]{2,40})$",
                        r"фокус\w*.* (?:закрыть|закрывай|закрывать|блокируй|блокировать) (?P<w>[\w.\-]{2,30})(?: тоже| ещё| еще)?$"]},
       examples={"ru": ["Закрывай инстаграм в режиме фокуса", "Добавь discord в фокус"]}, priority=4)
def focus_add(ctx: Ctx) -> str:
    import pcx
    w = re.sub(r"^(?:тоже|ещё|еще)\s+|\s+(?:тоже|ещё|еще)$", "", ctx.match.group("w").strip())
    names = {"инстаграм": "instagram", "инстаграмм": "instagram", "тикток": "tiktok", "дискорд": "discord",
             "телеграм": "telegram", "ютуб": "youtube", "вк": "vk.com", "вконтакте": "vk.com", "твич": "twitch"}
    word = names.get(w, w)
    words = pcx.focus_add(word)
    reply = f"Добавил «{word}» в фокус-щит. Свой список: {', '.join(words)}."
    if re.match(r"^(?:джарвис )?(?:добавь|включи|запусти) режим", ctx.norm) and not pcx.focus_active():
        reply += " " + pcx.focus_start(50)          # «добавь режим фокуса, закрыть инстаграм тоже»: both at once
    return reply


@skill("v3.persona_status", title={"ru": "Какой сейчас характер"},
       patterns={"ru": [r"(?:какой|какая) (?:сейчас |у тебя )?(?:характер|персона|роль)"]},
       examples={"ru": ["Какой сейчас характер?"]}, priority=3)
def persona_status(ctx: Ctx) -> str:
    names = {"tactical": "тактический", "coder": "программист", "business": "бизнес", "quiet": "тихий",
             "custom": "свой", "friend": "друг", "work": "деловой", "polite": "вежливый"}
    return f"Сейчас характер «{names.get(core.mode(), core.mode())}». Меняется словами «характер программист» и т. п."


core._LONG_OK.update({"v3.rates", "v3.movie", "v3.app_volume", "v3.focus", "v3.focus_add", "v3.save_this", "modes.persona"})
