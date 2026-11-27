"""Voice for the cognitive layer: memory facts, documents, the network shield, the VPN, the presentation, the character."""
import re
import sys
import threading

import core
from cognition import docs, geo, memory, personality, proactive, show, shield
from core import Ctx, on_start, skill


@on_start
def _start_cognition():
    proactive.start()


# ---------------------------------------------------------------- memory

@skill(
    "memory.fact_add",
    title={"ru": "Запомни факт о себе"},
    patterns={"ru": [r"^(?:джарвис )?запомни факт[:,]? (?P<t>.+)$"]},
    examples={"ru": ["Запомни факт: я работаю программистом"]},
    priority=5,
)
def fact_add(ctx: Ctx) -> str:
    memory.add_fact(ctx.match.group("t"))
    return "Запомнил."


@skill(
    "memory.facts",
    title={"ru": "Что ты обо мне знаешь"},
    patterns={"ru": [r"^(?:джарвис )?что ты (?:обо мне )?знаешь(?: обо мне)?$"]},
    examples={"ru": ["Что ты обо мне знаешь"]},
    priority=5,
)
def facts_say(ctx: Ctx) -> str:
    fs = memory.facts()
    if not fs:
        return "Пока ничего. Скажите: запомни факт, и я запомню."
    return "Я знаю: " + "; ".join(f["text"] for f in fs[-8:]) + "."


@skill(
    "memory.recall",
    title={"ru": "Что я говорил про …"},
    patterns={"ru": [r"^(?:джарвис )?что я (?:тебе )?говорил (?:про|о|об) (?P<t>.+)$"]},
    examples={"ru": ["Что я говорил про японский"]},
    priority=5,
)
def recall_say(ctx: Ctx) -> str:
    r = memory.recall(ctx.match.group("t"), k=2)
    if r["episodic"]:
        e = r["episodic"][0]
        return f"В {e['when'][11:]} {e['when'][:10]} вы сказали: {e['user'][:120]}."
    if r["semantic"]:
        return "Помню: " + r["semantic"][0]
    return "Не нашёл такого в памяти."


# ---------------------------------------------------------------- documents

@skill(
    "docs.index",
    title={"ru": "Изучить мои документы (с согласия)"},
    patterns={"ru": [r"^(?:джарвис )?(?:изучи|проиндексируй) мои документы$"]},
    examples={"ru": ["Изучи мои документы"]},
    priority=5,
)
def docs_index(ctx: Ctx) -> str:
    def go() -> str:
        if not docs.start_background():
            return "Уже изучаю документы."
        return "Начал изучать документы в Документах, на рабочем столе и в Загрузках. Скажу, когда закончу."
    return core.ask_confirm(ctx, "Прочитаю PDF, Word и текстовые файлы в Документах, на рабочем столе и в Загрузках. "
                                 "Файлы остаются на этом ноутбуке. Скажите «да».", go)


@skill(
    "docs.search",
    title={"ru": "Найти в моих документах"},
    patterns={"ru": [r"^(?:джарвис )?(?:найди|поищи|ищи) (?:в )?(?:моих )?документах? (?P<t>.+)$"]},
    examples={"ru": ["Найди в моих документах отчёт по выручке"]},
    priority=5,
)
def docs_find(ctx: Ctx) -> str:
    if not docs.count():
        return "Документы ещё не изучены. Скажите «изучи мои документы»."
    hits = docs.search(ctx.match.group("t"), 3)
    if not hits:
        return "В документах такого не нашёл."
    h = hits[0]
    where = f", страница {h['page']}" if h["page"] else ""
    return f"Нашёл в файле {h['file']}{where}: {h['text'][:200]}"


@skill(
    "docs.summary",
    title={"ru": "Краткая выжимка из документа"},
    patterns={"ru": [r"^(?:джарвис )?(?:сделай )?(?:краткую )?выжимку (?:из|по) (?P<t>.+)$"]},
    examples={"ru": ["Сделай выжимку из отчёта"]},
    priority=5,
)
def docs_summary(ctx: Ctx) -> str:
    text = docs.summary(ctx.match.group("t"))
    return text[:500] if text else "Не нашёл такой документ."


# ---------------------------------------------------------------- network shield

@skill(
    "shield.ports",
    title={"ru": "Проверить порты и подключения"},
    patterns={"ru": [r"^(?:джарвис )?(?:проверь|проверить) (?:открытые )?порты$",
                     r"^(?:джарвис )?кто (?:ко мне )?подключ(?:ён|ен|ена|ены) к (?:компьютеру|ноутбуку|ноуту)$"]},
    examples={"ru": ["Проверь порты"]},
    priority=5,
)
def shield_ports(ctx: Ctx) -> str:
    p = shield.ports()
    msg = f"Слушают сеть портов: {len(p['listening'])}. "
    msg += ("Необычные открытые порты: " + ", ".join(f"{port} ({prog})" for port, prog in p["unusual"][:4]) + ". ") if p["unusual"] else "Необычных открытых портов нет. "
    msg += f"Внешних подключений сейчас: {len(p['remote'])}."
    return msg


@skill(
    "shield.block",
    title={"ru": "Заблокировать IP-адрес в брандмауэре (с согласия)"},
    patterns={"ru": [r"^(?:джарвис )?заблокируй (?:ip|айпи|адрес|ай пи) (?P<ip>(?:\d{1,3}[ .]){3}\d{1,3})$"]},
    examples={"ru": ["Заблокируй IP 203.0.113.5"]},
    priority=5,
)
def shield_block(ctx: Ctx) -> str:
    ip = ".".join(re.findall(r"\d{1,3}", ctx.match.group("ip")))   # the normaliser turns dots into spaces
    return core.ask_confirm(ctx, f"Заблокирую входящие с адреса {ip} в брандмауэре Windows. Скажите «да».",
                            lambda: _safe(lambda: shield.block_ip(ip)))


def _safe(fn) -> str:
    try:
        return fn()
    except ValueError as e:
        return str(e)


@skill(
    "shield.unblock",
    title={"ru": "Снять блокировку IP-адреса (с согласия)"},
    patterns={"ru": [r"^(?:джарвис )?разблокируй (?:ip|айпи|адрес|ай пи) (?P<ip>(?:\d{1,3}[ .]){3}\d{1,3})$"]},
    examples={"ru": ["Разблокируй IP 203.0.113.5"]},
    priority=5,
)
def shield_unblock(ctx: Ctx) -> str:
    ip = ".".join(re.findall(r"\d{1,3}", ctx.match.group("ip")))
    return core.ask_confirm(ctx, f"Сниму блокировку с адреса {ip}. Скажите «да».",
                            lambda: _safe(lambda: shield.unblock_ip(ip)))


@skill(
    "shield.locate",
    title={"ru": "Где находится IP-адрес (по запросу)"},
    patterns={"ru": [r"^(?:джарвис )?(?:где находится|где|кто за|чей) (?:ip|айпи|адрес|ай пи) (?P<ip>(?:\d{1,3}[ .]){3}\d{1,3})$"]},
    examples={"ru": ["Где находится IP 8.8.8.8"]},
    priority=5,
)
def shield_locate(ctx: Ctx) -> str:
    ip = ".".join(re.findall(r"\d{1,3}", ctx.match.group("ip")))
    try:
        d = geo.locate(ip)
    except ValueError as e:
        return str(e)
    where = ", ".join(x for x in (d["city"], d["country"]) if x) or "место не указано"
    return f"Адрес {d['ip']}: {where}. Провайдер: {d['org'] or 'неизвестен'}" + (f", {d['asn']}." if d["asn"] else ".")


@skill(
    "shield.vpn_status",
    title={"ru": "Включён ли VPN"},
    patterns={"ru": [r"^(?:джарвис )?(?:статус|включён ли|включен ли|работает ли) vpn$"]},
    examples={"ru": ["Статус VPN"]},
    priority=5,
)
def vpn_status(ctx: Ctx) -> str:
    v = shield.vpn()
    return "VPN включён: " + ", ".join(v["adapters"]) if v["on"] else "VPN сейчас выключен."


@skill(
    "shield.vpn_switch",
    title={"ru": "Включить или выключить VPN (с согласия)"},
    patterns={"ru": [r"^(?:джарвис )?(?P<a>включи|выключи) vpn$"]},
    examples={"ru": ["Включи VPN"]},
    priority=5,
)
def vpn_switch(ctx: Ctx) -> str:
    on = ctx.match.group("a") == "включи"
    tunnel = core.setting("vpn", "tunnel", "")
    if not tunnel:
        return "Туннель не задан. Укажите имя туннеля WireGuard в config.toml, раздел [vpn], tunnel."
    return core.ask_confirm(ctx, f"{'Включу' if on else 'Выключу'} VPN {tunnel}. Скажите «да».",
                            lambda: _safe(lambda: shield.vpn_tunnel("on" if on else "off", tunnel)))


# ---------------------------------------------------------------- presentation

_LANG_WORDS = (("японск", "ja"), ("англий", "en"), ("русск", "ru"))
_AUDIO = re.compile(r"аудио|mp3|мп3|звуков\w* файл|в файл|запиши в|сохрани")


def _lang_of(text: str, default: str = "ru") -> str:
    low = text.lower()
    return next((code for word, code in _LANG_WORDS if word in low), default)


def _bring_window() -> None:
    """The slides are on the screen: show the Jarvis window even if it was hidden in the tray."""
    fn = getattr(sys.modules.get("__main__"), "open_app_window", None)
    if fn:
        threading.Thread(target=fn, daemon=True, name="show-window").start()


def _active() -> bool:
    return bool(show.public()["active"])


def _audio(deck: str, lang: str) -> str:
    names = {"ru": "русском", "en": "английском", "ja": "японском"}
    try:
        path = show.export_audio(lang, deck)
    except Exception as e:  # noqa: BLE001
        return f"Аудиофайл не получился: {e}."
    import subprocess
    subprocess.Popen(["explorer", "/select,", str(path)])
    return f"Готово. Аудиофайл презентации на {names[lang]} сохранён: {path.name}. Открыл папку с ним."


@skill(
    "show.about",
    title={"ru": "Самопрезентация: Джарвис рассказывает о себе на весь экран"},
    patterns={"ru": [r"самопрезент\w*",
                     r"(?:презентуй|представь|покажи|опиши) себя",
                     r"расскажи (?:\w+ )?(?:всё |все |подробно |полностью )?о себе",
                     r"презентаци\w* (?:о себе|себя|про себя|о джарвисе|джарвиса)",
                     r"(?:свою|твою) презентаци\w*",
                     r"^(?:джарвис )?(?:начни|запусти|покажи|включи|сделай)(?: полную| полноценную)? презентацию$",
                     r"^(?:джарвис )?режим презентации$",
                     r"презентаци\w*.*(?:аудио|mp3)", r"(?:аудио|mp3)\w*.*презентаци\w*"]},
    examples={"ru": ["Самопрезентация", "Расскажи о себе на японском", "Сохрани самопрезентацию в аудиофайл"]},
    priority=4,
)
def show_about(ctx: Ctx) -> str:
    lang = _lang_of(ctx.text)
    if _AUDIO.search(ctx.norm) and re.search(r"аудио|mp3|мп3|файл", ctx.norm):
        return _audio("about", lang)
    show.start(lang, "about", auto=True)          # reads itself slide by slide; the screen follows
    _bring_window()
    return ""                                     # the first slide is the answer: it is being read out now


@skill(
    "show.start",
    title={"ru": "Отчёт за месяц на весь экран"},
    patterns={"ru": [r"^(?:джарвис )?(?:начни|запусти|покажи) (?:доклад|отч[её]т)(?: за месяц)?$",
                     r"^(?:джарвис )?(?:доклад|отч[её]т) за месяц$"]},
    examples={"ru": ["Начни доклад"]},
    priority=4,
)
def show_start(ctx: Ctx) -> str:
    if _AUDIO.search(ctx.norm) and re.search(r"аудио|mp3|мп3|файл", ctx.norm):
        return _audio("report", _lang_of(ctx.text))
    show.start(_lang_of(ctx.text), "report", auto=True)
    _bring_window()
    return ""


@skill(
    "show.next",
    title={"ru": "Следующий слайд"},
    patterns={"ru": [r"^(?:джарвис )?(?:следующий слайд|дальше|далее|следующий)$"]},
    examples={"ru": ["Следующий слайд"]},
    priority=5,
)
def show_next(ctx: Ctx) -> str | None:
    if not _active():
        return None if ctx.norm.strip() in ("дальше", "далее", "следующий") else "Презентация не запущена. Скажите: самопрезентация."
    show.step(1, speak=True)
    return ""


@skill(
    "show.prev",
    title={"ru": "Предыдущий слайд"},
    patterns={"ru": [r"^(?:джарвис )?(?:предыдущий слайд|назад слайд|слайд назад|вернись назад)$"]},
    examples={"ru": ["Предыдущий слайд"]},
    priority=5,
)
def show_prev(ctx: Ctx) -> str | None:
    if not _active():
        return None
    show.step(-1, speak=True)
    return ""


@skill(
    "show.say",
    title={"ru": "Повторить текущий слайд"},
    patterns={"ru": [r"^(?:джарвис )?(?:повтори|прочитай|скажи) (?:этот |текущий )?слайд$"]},
    examples={"ru": ["Повтори слайд"]},
    priority=5,
)
def show_say(ctx: Ctx) -> str | None:
    if not _active():
        return None
    show.say_current()
    return ""


@skill(
    "show.play",
    title={"ru": "Презентация читает себя сама или пауза"},
    patterns={"ru": [r"^(?:джарвис )?(?P<a>читай сам|показывай сам|продолжай показ|продолжи|продолжай|автопоказ|пауза|"
                     r"останови показ|подожди)$"]},
    examples={"ru": ["Читай сам", "Пауза"]},
    priority=5,
)
def show_play(ctx: Ctx) -> str | None:
    if not _active():
        return None                                # «пауза» / «продолжи» stay the music commands
    if ctx.match.group("a") in ("пауза", "останови показ", "подожди"):
        show.pause()
        return "Пауза. Скажите «продолжай», и я продолжу."
    show.play()
    return ""


@skill(
    "show.lang",
    title={"ru": "Переключить язык презентации"},
    patterns={"ru": [r"^(?:джарвис )?(?:переключись|переключи презентацию|перейди|давай) на (?P<l>японский|английский|русский)(?: язык)?$"]},
    examples={"ru": ["Переключись на японский"]},
    priority=5,
)
def show_lang(ctx: Ctx) -> str | None:
    code = {"японский": "ja", "английский": "en", "русский": "ru"}[ctx.match.group("l")]
    if not _active():
        show.start(code, "about", auto=True)
        _bring_window()
        return ""
    st = show.switch(code)
    if not st["auto"]:
        show.say_current()
    return ""


@skill(
    "show.stop",
    title={"ru": "Закончить презентацию"},
    patterns={"ru": [r"^(?:джарвис )?(?:закончи|заверши|выйди из|закрой|останови) (?:презентацию|доклад|показ|самопрезентацию)$"]},
    examples={"ru": ["Закончи презентацию"]},
    priority=5,
)
def show_stop(ctx: Ctx) -> str:
    show.stop()
    return "Презентация закончена."


# ---------------------------------------------------------------- personality

@skill(
    "personality.stage",
    title={"ru": "Какие у нас отношения"},
    patterns={"ru": [r"^(?:джарвис )?(?:какие у нас|в каком мы) отношения$", r"^(?:джарвис )?кто ты для меня$"]},
    examples={"ru": ["Какие у нас отношения"]},
    priority=5,
)
def stage_say(ctx: Ctx) -> str:
    st = personality.stage()
    return f"Мы: {st['stage']}. Разговоров было {st['exchanges']}, дней знакомы {st['days']}."
