"""Voice for the cognitive layer: memory facts, documents, the network shield, the VPN, the presentation, the character."""
import re
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

def _say_slide() -> str:
    text = show.say_current()
    if text:
        threading.Thread(target=core.speak, args=(text, show.public()["lang"]), daemon=True).start()
    return text


@skill(
    "show.start",
    title={"ru": "Начать презентацию голосом"},
    patterns={"ru": [r"^(?:джарвис )?(?:режим презентации|начни доклад|начни презентацию|начни показ)$"]},
    examples={"ru": ["Начни доклад"]},
    priority=5,
)
def show_start(ctx: Ctx) -> str:
    st = show.start("ru")
    _say_slide()
    return f"Презентация, слайд 1 из {st['total']}."


@skill(
    "show.next",
    title={"ru": "Следующий слайд"},
    patterns={"ru": [r"^(?:джарвис )?следующий слайд$", r"^(?:джарвис )?дальше$"]},
    examples={"ru": ["Следующий слайд"]},
    priority=5,
)
def show_next(ctx: Ctx) -> str:
    st = show.step(1)
    if not st["active"]:
        return "Презентация не запущена. Скажите: начни доклад."
    _say_slide()
    return f"Слайд {st['i'] + 1} из {st['total']}."


@skill(
    "show.prev",
    title={"ru": "Предыдущий слайд"},
    patterns={"ru": [r"^(?:джарвис )?предыдущий слайд$", r"^(?:джарвис )?назад слайд$"]},
    examples={"ru": ["Предыдущий слайд"]},
    priority=5,
)
def show_prev(ctx: Ctx) -> str:
    st = show.step(-1)
    if not st["active"]:
        return "Презентация не запущена."
    _say_slide()
    return f"Слайд {st['i'] + 1} из {st['total']}."


@skill(
    "show.lang",
    title={"ru": "Переключить язык презентации"},
    patterns={"ru": [r"^(?:джарвис )?переключись на (?P<l>японский|английский|русский)(?: язык)?$"]},
    examples={"ru": ["Переключись на японский"]},
    priority=5,
)
def show_lang(ctx: Ctx) -> str:
    code = {"японский": "ja", "английский": "en", "русский": "ru"}[ctx.match.group("l")]
    if not show.public()["active"]:
        show.start(code)
    else:
        show.switch(code)
    _say_slide()
    return "Переключил."


@skill(
    "show.stop",
    title={"ru": "Закончить презентацию"},
    patterns={"ru": [r"^(?:джарвис )?(?:закончи|заверши|выйди из) (?:презентацию|доклад|показ)$"]},
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
