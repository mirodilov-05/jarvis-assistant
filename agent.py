"""Jarvis V2 brain: the language model decides which tools to call.

One request may call several tools at once ("закрой телеграм и включи музыку",
"подготовь меня к работе"). Safe tools run immediately; risky ones
(delete, power) are confirmed with "да/нет" first. If no tool fits, the model
just answers — that's the conversation.

Providers: the cloud (Groq / Gemini, cloud.py — default in V3), local Ollama (qwen3.5) or Claude via your API key.
"""

from __future__ import annotations

import json
import re
import sys

import requests

import connections
import core
import tools

_history: list[dict] = []

GUIDE = (
    "\n\nТы управляешь ноутбуком пользователя через инструменты (tools). Правила:\n"
    "- Если пользователь просит что-то СДЕЛАТЬ или УЗНАТЬ, что умеет инструмент — вызови инструмент, не описывай словами.\n"
    "- Если в просьбе несколько действий — вызови несколько инструментов сразу, в нужном порядке.\n"
    "- «Подготовь к работе / учёбе / игре / ночи» — переключи режим (switch_mode) и сделай, что попросили.\n"
    "- Никогда не выдумывай результаты инструментов и данные пользователя.\n"
    "- Если это просто разговор или вопрос на знания — ответь сам, коротко, без инструментов.\n"
    "- Отвечай по-русски, без списков, разметки и эмодзи: ответ читается голосом."
)


def _llm():
    return sys.modules.get("jarvis_plugin_llm")


def _system(text: str) -> str:
    llm = _llm()
    base = llm.system_prompt("ru") if llm else "Ты Джарвис, голосовой помощник."
    ctx = ""
    if llm and (llm.provider() in ("claude", "cloud") or llm._NEEDS_CONTEXT.search(text)):
        ctx = "\n\nКонтекст пользователя:\n" + llm.context_text()
    else:
        ctx = f"\n\nСейчас {core.now():%A %d.%m.%Y %H:%M}. Режим: {core.active_profile()['title']}."
    mem = llm.memories_for(text) if llm else []
    if mem:   # semantic memory: what the user told Jarvis before that is about this request
        ctx += "\nПользователь раньше просил запомнить: " + " | ".join(mem)
    return base + GUIDE + ctx


# ---------------------------------------------------------------------------
# Model calls -> (text, [(tool_name, args), ...])
# ---------------------------------------------------------------------------

def _tc(name: str, **args) -> dict:
    return {"function": {"name": name, "arguments": args}}


# Worked examples: a small local model learns the "call a tool, don't just talk" habit from these.
FEW_SHOT = [
    {"role": "user", "content": "закинь в список хлеб и открой телеграм"},
    {"role": "assistant", "content": "", "tool_calls": [_tc("add_task", text="купить хлеб"), _tc("open", target="телеграм")]},
    {"role": "tool", "content": "Записал дело: купить хлеб."},
    {"role": "tool", "content": "Запускаю telegram desktop."},
    {"role": "assistant", "content": "Записал и открываю Телеграм."},
    {"role": "user", "content": "выруби комп"},
    {"role": "assistant", "content": "", "tool_calls": [_tc("power", action="shutdown")]},
    {"role": "tool", "content": "Нужно подтверждение."},
    {"role": "assistant", "content": "Точно выключить компьютер?"},
    {"role": "user", "content": "что у меня там по делам на пятницу"},
    {"role": "assistant", "content": "", "tool_calls": [_tc("list_tasks", period="friday")]},
    {"role": "tool", "content": "Пятница: 1. сдать отчёт в 12:00."},
    {"role": "assistant", "content": "В пятницу: сдать отчёт в 12:00."},
    {"role": "user", "content": "какой код от домофона я тебе говорил"},
    {"role": "assistant", "content": "", "tool_calls": [_tc("search_notes", query="код домофона")]},
    {"role": "tool", "content": "1. код от домофона 4567."},
    {"role": "assistant", "content": "Код от домофона — 4567."},
    {"role": "user", "content": "подготовь меня к учёбе и найди лекции по физике на ютубе"},
    {"role": "assistant", "content": "", "tool_calls": [_tc("switch_mode", mode="study"), _tc("youtube_search", query="лекции по физике")]},
    {"role": "tool", "content": "Режим учёбы."},
    {"role": "tool", "content": "Ищу на YouTube: лекции по физике."},
    {"role": "assistant", "content": "Режим учёбы включён, ищу лекции."},
    {"role": "user", "content": "как думаешь, кофе вредно пить вечером?"},
    {"role": "assistant", "content": "Вечером лучше без кофе: кофеин действует до шести часов и мешает уснуть."},
]

# The model *says* it did something but called no tool — that's a lie we must catch
_CLAIM = re.compile(r"\b(открываю|открою|откроем|закрываю|закрою|включаю|включу|выключаю|выключу|переключ\w*|запуска\w*|"
                    r"запущу|найд[уё]м|найду|ищу|напомню|записал\w*|запишу|добавил\w*|добавлю|удалил\w*|удалю|отправ\w*|"
                    r"ставлю|поставлю|сделаю|делаю|перенес\w*|перенесу|отмечу|отметил|выключен\w*|включен\w*|открыт\w*|"
                    r"закрыт\w*|запущен\w*|записан\w*|добавлен\w*|поставлен\w*|уже стоит|готово)\b", re.I)


# extra words people use for each tool (besides its description)
SYNONYMS = {
    "window": "окно окна сверни разверни закрой переключи рабочий стол влево вправо весь экран",
    "brightness": "яркость ярче темнее экран подсветка",
    "set_volume": "громкость звук процентов максимум минимум",
    "find_file": "файл файлы документ найди где фото видео папка",
    "translate_phrase": "переведи как по английски японски узбекски перевод фразу слово",
    "convert_currency": "сколько долларов сумов рублей евро валюта перевести курс",
    "learn_programs": "изучи программы установил новую программу",
    "type_text": "напечатай набери впиши введи напиши здесь текст в поле",
    "write_prompt": "промпт промт запрос нейросеть chatgpt чатгпт claude midjourney",
    "write_text": "напиши составь пост письмо ответ описание сценарий текст поздравление",
    "press_keys": "нажми клавишу клавиши сочетание контрол альт шифт энтер",
    "repeat_last": "повтори ещё раз снова то же самое",
    "system_check": "проверь систему грузит тормозит компьютер диагностика процессор память",
    "play_music": "музыку песню трек включи поставь послушать исполнителя плейлист",
    "app_volume": "громкость игры дискорда браузера музыки программы приложения отдельно тише громче процентов",
    "quieter_here": "тише громче тут здесь звук игры",
    "focus_shield": "фокус фокусировка сосредоточиться работаю учусь отвлекает прокрастинация щит минут",
    "translate_screen": "переведи перевод перевести английский японский текст экран окно игра",
    "save_this": "сохрани это ссылку фрагмент код",
    "rates": "курс биткоин эфир usdt доллар рубль сум валюта крипта стоит цена",
    "watch_movie": "фильм сериал посмотреть кино включи кинопоиск",
    "media_seek": "перемотай вперёд назад перемотка секунд",
    "code_create_file": "создай файл напиши скрипт программу код python",
    "code_run": "запусти скрипт выполни код программу ошибка терминал",
    "code_fix": "исправь ошибку почини фикс баг",
    "look_at_screen": "экран экране монитор окно вижу видишь посмотри глянь прочитай написано ошибка переведи картинка страница тут здесь",
    "open": "открой запусти включи зайди поиграть игру программу сайт приложение",
    "close_app": "закрой выключи убери вырубай заверши",
    "add_task": "дело задачу список надо нужно забыть сделать купить",
    "list_tasks": "дела планы задачи завтра сегодня неделю пятницу понедельник просрочено",
    "remember": "запомни запиши заметку идея пароль код",
    "search_notes": "какой какая какие помнишь говорил запоминал пароль код номер адрес заметках",
    "set_reminder": "напомни напоминание через минут часов",
    "set_timer": "таймер минут секунд засеки",
    "set_alarm": "будильник разбуди утра",
    "power": "выключи выруби компьютер комп ноутбук перезагрузи вырубай",
    "volume": "громче тише звук громкость погромче потише",
    "media": "пауза трек следующий предыдущий песню дальше",
    "web_search": "найди интернете погугли загугли поищи",
    "youtube_search": "ютубе ютуб видео ролик",
    "switch_mode": "режим подготовь работе учебе игре ночь отдых",
    "weather": "погода погоду градусов холодно тепло дождь",
    "calculate": "сколько будет посчитай процентов умножить разделить плюс минус",
    "briefing": "отчет сводка новости нового",
    "send_message": "напиши отправь сообщение скажи передай",
    "read_chat": "пишет написал переписку чат",
    "messages_unread": "сообщения телеграм ватсап непрочитанные",
    "read_email": "почту письма почта",
    "get_datetime": "время час дата число день",
    "battery": "заряд батарея",
    "screenshot": "скриншот снимок экрана",
    "lock_pc": "заблокируй блокировка",
    "complete_task": "выполнил сделал готово отметь",
    "move_task": "перенеси передвинь отложи",
    "delete_task": "удали дело",
    "start_recording": "запись диктофон запиши голос",
}


def _stems(text: str) -> set:
    return {w[:5] for w in re.findall(r"[а-яёa-z]{3,}", text.lower())}


def pick_tools(text: str, k: int = 7) -> list[dict]:
    """Give the small local model only the tools that fit this phrase — it chooses much better from a short list."""
    words = _stems(text)
    scored = []
    for t in tools.TOOLS.values():
        syn = _stems(SYNONYMS.get(t.name, ""))
        vocab = _stems(t.description + " " + t.name.replace("_", " ")) | syn
        score = len(words & vocab) + 2 * len(words & syn)
        if score:
            scored.append((score, t.name))
    names = [n for _, n in sorted(scored, reverse=True)[:k]]
    return [s for s in tools.ollama_schemas() if s["function"]["name"] in names]


def _call_local(system: str, messages: list[dict]) -> tuple[str, list]:
    cfg = core.CONFIG.get("llm", {})
    r = requests.post(cfg.get("ollama_url", "http://127.0.0.1:11434") + "/api/chat", json={
        "model": cfg.get("model", "qwen3.5:2b-q4_K_M"),
        "messages": [{"role": "system", "content": system}] + FEW_SHOT + messages,
        "tools": pick_tools(next(m["content"] for m in reversed(messages) if m["role"] == "user"
                                 and not m["content"].startswith("Ты не вызвал"))),
        "stream": False, "think": False,
        "keep_alive": "2m" if core.CONFIG.get("_game_mode") else "30m",
        "options": {"num_predict": 300, "temperature": 0},
    }, timeout=60)
    r.raise_for_status()
    msg = r.json().get("message", {})
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function", {})
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        calls.append((fn.get("name", ""), args))
    return msg.get("content", "") or "", calls


def _call_claude(system: str, messages: list[dict]) -> tuple[str, list]:
    import anthropic

    llm = _llm()
    key = connections.get_secret("anthropic:api_key")
    cache = llm._client_cache
    if cache.get("key") != key:
        cache.update(key=key, client=anthropic.Anthropic(api_key=key, timeout=60.0))
    model = connections.load()["ai"].get("model") or "claude-opus-5-5"
    response = cache["client"].beta.messages.create(
        model=model, max_tokens=1024, system=system, messages=messages, tools=tools.anthropic_schemas(),
        output_config={"effort": "low"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if response.stop_reason == "refusal":
        return "Извините, с этим я помочь не могу.", []
    text = "".join(b.text for b in response.content if b.type == "text")
    calls = [(b.name, dict(b.input)) for b in response.content if b.type == "tool_use"]
    return text, calls


def _call_cloud(system: str, messages: list[dict]) -> tuple[str, list]:
    import cloud
    # only the tools that fit this phrase: all 51 would cost ~3000 tokens per request, and the free Groq plan
    # allows ~8000 tokens a minute per model
    text = next((m["content"] for m in reversed(messages) if m.get("role") == "user" and isinstance(m.get("content"), str)
                 and not m["content"].startswith("Ты не вызвал")), "")
    return cloud.chat([{"role": "system", "content": system}] + messages, tools=pick_tools(text, k=12),
                      max_tokens=500, temperature=0.2)


def _think(text: str) -> tuple[str, list]:
    system = _system(text)
    messages = _history[-8:] + [{"role": "user", "content": text}]
    llm = _llm()
    if llm and llm.provider() == "cloud":
        import cloud
        try:
            return _call_cloud(system, messages)
        except Exception:  # noqa: BLE001
            core.log.exception("Cloud tool call failed")
            if not cloud.local_fallback():
                raise
    if llm and llm.provider() == "claude":
        try:
            return _call_claude(system, messages)
        except Exception:  # noqa: BLE001
            core.log.exception("Claude tool call failed, using local model")
    content, calls = _call_local(system, messages)
    if not calls and _CLAIM.search(content or ""):
        # promised an action in words only: ask again, firmly
        core.log.info("Agent claimed an action without a tool: %r — retrying", content)
        retry = messages + [{"role": "assistant", "content": content},
                            {"role": "user", "content": "Ты не вызвал инструмент, поэтому ничего не произошло. "
                                                        "Вызови нужный инструмент (или несколько) для моей просьбы сейчас."}]
        content2, calls = _call_local(system, retry)
        if calls:
            return content2, calls
        return "Не понял, что именно сделать. Скажи по-другому, пожалуйста.", []
    return content, calls


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(text: str, source: str) -> str | None:
    """Handle a request with tools. Returns the reply, or None if the brain is unavailable."""
    try:
        content, calls = _think(text)
    except Exception:  # noqa: BLE001
        core.log.exception("agent unavailable")
        return None
    llm = _llm()
    content = llm._clean(content) if llm else content.strip()
    calls = [(n, a) for n, a in calls if n in tools.TOOLS][:6]
    core.log.info("Agent: %r -> tools %s", text, [n for n, _ in calls] or "none")

    if not calls:   # plain conversation / knowledge question
        if not core.feature("chat"):
            return f"Свободный разговор выключен в режиме «{core.active_profile()['title']}». Команды работают."
        if not content:
            return None
        if source == "голос" and llm:
            _tokens, sentences = llm.LIMITS.get(core.mode(), (180, 3))
            content = llm._short(content, sentences)
            if core.mode() == "friend" or content.rstrip().endswith("?"):
                core.FOLLOWUP.set()
        _remember(text, content)
        return content

    results, risky = [], []
    for name, args in calls:
        t = tools.TOOLS[name]
        if t.tier == "confirm":
            risky.append((t, args))
            continue
        out = tools.execute(name, args)
        if out:
            results.append(out)
    reply = " ".join(results)
    if risky:
        t, args = risky[0]
        try:
            what = t.confirm_text(**{k: v for k, v in args.items() if k in t.params}) if t.confirm_text else t.name
        except TypeError:
            what = t.name
        question = f"Точно {what}? Скажите да или нет."
        ctx = core.Ctx(text=text, lang="ru", source=source, config=core.CONFIG)
        core.ask_confirm(ctx, question, lambda t=t, args=args: tools.execute(t.name, args) or "Готово.")
        reply = (reply + " " + question).strip()
    if not reply:
        reply = content or "Готово."
    _remember(text, reply)
    return reply


def _remember(user: str, reply: str) -> None:
    _history.extend([{"role": "user", "content": user}, {"role": "assistant", "content": reply}])
    del _history[:-12]


# A phrase with several actions must go to the brain, not to a single V1 skill
_CHAIN = re.compile(
    r"\b(и|потом|затем|а также|после этого|а потом|плюс)\s+(?:ещ[её] )?(открой|закрой|включи|выключи|поставь|добавь|запиши|"
    r"напомни|сделай|найди|покажи|прочитай|напиши|запусти|перенеси|удали|скажи|переключи|убери|заблокируй)", re.I)


_SPLIT = re.compile(r"(?:,\s*|\s+)(?:и|потом|затем|а также|после этого|а потом|плюс)\s+(?:ещ[её]\s+)?(?=(?:открой|закрой|"
                    r"включи|выключи|поставь|добавь|запиши|напомни|сделай|найди|покажи|прочитай|напиши|запусти|перенеси|"
                    r"удали|скажи|переключи|убери|заблокируй)\b)", re.I)


_NO_SPLIT = re.compile(r"(?:запомни|создай|сохрани|добавь) (?:команду|макрос)|упакуй|оформи (?:видео|ролик)|"
                       r"^(?:джарвис )?(?:узнай|выясни|погугли|загугли|найди ответ)|переведи|разбери|"
                       r"^(?:джарвис )?(?:запомни|запиши заметку|заметка)|напиши (?:сообщение|маме|папе|в )|"
                       r"^(?:джарвис )?(?:напечатай|набери|впиши|введи)|(?:напиши|составь|сочини|набросай|придумай|дай)(?: мне)? "
                       r"(?:промпт|промт|запрос|текст|пост|письмо|ответ|описание|резюме|комментарий|статью|сценарий|план|отзыв|"
                       r"поздравление|объявление)|скопируй (?:текст)?\s*:", re.I)


def split_chain(text: str) -> list[str]:
    """«закрой телеграм и включи музыку» -> ["закрой телеграм", "включи музыку"]."""
    if _NO_SPLIT.search(text.strip()):
        return [text]          # «запомни команду X: открой ютуб и включи музыку» is ONE command
    parts = [p.strip(" ,.") for p in _SPLIT.split(text) if p and p.strip(" ,.")]
    return parts if len(parts) > 1 else [text]


def needs_brain(text: str) -> bool:
    norm = core.normalize(text, "ru")
    return bool(_CHAIN.search(norm)) or len(norm.split()) > 14
