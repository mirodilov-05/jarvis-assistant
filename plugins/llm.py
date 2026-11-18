"""The assistant's "brain" for free-form questions and advice.

Providers (Connections → AI):
  local  — Ollama on this laptop (qwen3.5:2b): free, offline, fast, but simple.
  claude — Anthropic Claude via your API key: much smarter, needs internet, paid per use.
The model always gets your current context (tasks, latest briefing) so it can
answer "what should I do first?".
"""

import re
import sys

import requests

import connections
import core
from core import Ctx, skill

# Persona per mode: work = short & on topic, friend = warm talk, polite = courteous
PERSONA = {
    "work": {
        "ru": ("Ты Джарвис — деловой ИИ-ассистент. Режим РАБОТА: отвечай строго по теме, ясно и кратко — "
               "одно-два коротких предложения, только суть, без приветствий, шуток и вопросов в ответ. "
               "Если ответ — число, факт или шаг, назови только его."),
        "uz": ("Sen Jarvis — ishchan AI yordamchisan. ISH rejimi: faqat mavzu bo'yicha, aniq va qisqa — "
               "bir-ikki gap, salomlashish va hazilsiz."),
    },
    "friend": {
        "ru": ("Ты Джарвис — ИИ-друг пользователя. Говори на «ты», тепло, живо и по-дружески, как близкий друг: "
               "можно лёгкий юмор, поддержка, искренний интерес к его делам. Отвечай естественно, 1–3 предложения; "
               "если уместно, задай короткий встречный вопрос, чтобы продолжить разговор. Не будь занудой."),
        "uz": ("Sen Jarvis — foydalanuvchining AI do'stisan. «Sen» deb, samimiy va do'stona gapir, biroz hazil "
               "va qo'llab-quvvatlash bilan. 1–3 gap; o'rinli bo'lsa, suhbatni davom ettirish uchun qisqa savol ber."),
    },
    "polite": {
        "ru": ("Ты Джарвис — вежливый и учтивый ИИ-ассистент, как дворецкий Тони Старка. Обращайся на «Вы» и «сэр», "
               "будь доброжелателен и тактичен, отвечай понятно и по делу, 1–3 предложения."),
        "uz": ("Sen Jarvis — xushmuomala va odobli AI yordamchisan. «Siz» va «janob» deb murojaat qil, "
               "aniq va tushunarli javob ber, 1–3 gap."),
    },
}
RULES = {
    "ru": " Отвечай ТОЛЬКО по-русски, без списков, разметки и эмодзи — ответ зачитывается голосом. Не выдумывай факты: если не знаешь, так и скажи.",
    "uz": " FAQAT o'zbek tilida (lotin yozuvida), ro'yxat, belgi va emojisiz — javob ovoz bilan o'qiladi. Bilmasang, ochiq ayt.",
}
LIMITS = {"work": (90, 2), "friend": (180, 3), "polite": (160, 3)}   # (max tokens, max spoken sentences)


def system_prompt(lang: str) -> str:
    m = core.mode()
    p = PERSONA[m].get(lang, PERSONA[m]["ru"]) + RULES.get(lang, RULES["ru"])
    name = core.CONFIG.get("assistant", {}).get("user_name", "")
    if name and m != "work":
        p += f" Пользователя зовут {name}." if lang == "ru" else f" Foydalanuvchining ismi {name}."
    return p

_history: list[dict] = []
_client_cache: dict = {}


def context_text() -> str:
    lines = [f"Сейчас {core.now():%A %d.%m.%Y %H:%M}."]
    tasks_mod = sys.modules.get("jarvis_plugin_tasks")
    if tasks_mod:
        items = tasks_mod.open_tasks()
        if items:
            lines.append("Открытые дела: " + "; ".join(
                t["text"] + (f" (срок {t['due'].replace('T', ' ')})" if t.get("due") else "") for t in items[:15]))
        else:
            lines.append("Открытых дел нет.")
    brief = core.CONFIG.get("_last_brief")
    if brief:
        lines.append(f"Последняя сводка ({brief['time']}): {brief['text']}")
    notes = core.DATA / "notes.md"
    if notes.exists():   # things the user asked to remember
        last = [ln[2:] for ln in notes.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")][-15:]
        if last:
            lines.append("Заметки пользователя: " + " | ".join(last))
    return "\n".join(lines)


def _clean(reply: str) -> str:
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S)
    reply = re.sub(r"[*#`_]+", "", reply)
    reply = re.sub(r"^\s*[-•—]\s*", "", reply, flags=re.M)
    reply = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️‍]", "", reply)  # emoji can't be spoken
    reply = reply.strip(" \"'«»")
    return re.sub(r"\s*\n+\s*", " ", reply).strip()


def _short(reply: str, max_sentences: int = 3) -> str:
    parts = re.split(r"(?<=[.!?])\s+", reply)
    return " ".join(parts[:max_sentences])


def provider() -> str:
    ai = connections.load()["ai"]
    if ai.get("provider") == "claude" and connections.get_secret("anthropic:api_key"):
        return "claude"
    return "local"


def _ask_claude(system: str, messages: list[dict], max_tokens: int) -> str:
    import anthropic

    key = connections.get_secret("anthropic:api_key")
    if _client_cache.get("key") != key:
        _client_cache.update(key=key, client=anthropic.Anthropic(api_key=key, timeout=60.0))
    client = _client_cache["client"]
    model = connections.load()["ai"].get("model") or "claude-opus-5-5"
    response = client.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        output_config={"effort": "low"},          # short spoken answers: keep latency low
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",                      # if a request is declined, retry on a fallback model
    )
    if response.stop_reason == "refusal":
        return "Извините, с этим я помочь не могу."
    return "".join(b.text for b in response.content if b.type == "text")


def _ask_local(system: str, messages: list[dict], max_tokens: int) -> str:
    cfg = core.CONFIG.get("llm", {})
    r = requests.post(cfg.get("ollama_url", "http://127.0.0.1:11434") + "/api/chat", json={
        "model": cfg.get("model", "qwen3.5:2b"), "messages": [{"role": "system", "content": system}] + messages,
        "stream": False, "think": False, "keep_alive": "2m" if core.CONFIG.get("_game_mode") else "30m",
        "options": {"num_predict": max_tokens},
    }, timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]


_NEEDS_CONTEXT = re.compile(r"(дел|задач|план|заметк|запис|сегодня|завтра|неделю|что мне|посоветуй|совет|сводк|"
                           r"vazifa|reja|qayd|bugun|ertaga|maslahat)", re.I)


def ask(text: str, lang: str, max_tokens: int = 300, use_history: bool = True, extra_system: str = "",
        with_context: bool | None = None) -> str:
    # small local models get confused by a big context: give it only when the question is about your stuff
    if with_context is None:
        with_context = provider() == "claude" or bool(_NEEDS_CONTEXT.search(text))
    ctx_part = ("\n\nКонтекст пользователя:\n" + context_text()) if with_context else f"\n\nСейчас {core.now():%d.%m.%Y %H:%M}."
    system = system_prompt(lang) + ctx_part + extra_system
    messages = (_history[-8:] if use_history else []) + [{"role": "user", "content": text}]
    try:
        if provider() == "claude":
            try:
                reply = _ask_claude(system, messages, max_tokens)
            except Exception:  # noqa: BLE001 - offline / quota: fall back to the local model
                core.log.exception("Claude request failed, using local model")
                reply = _ask_local(system, messages, max_tokens)
        else:
            reply = _ask_local(system, messages, max_tokens)
    except Exception as e:  # noqa: BLE001
        return ("Модель недоступна: " if lang == "ru" else "Model ishlamayapti: ") + str(e)[:120]
    reply = _clean(reply or "") or ("Не знаю, что ответить." if lang == "ru" else "Javob topa olmadim.")
    if use_history:
        _history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": reply}])
        del _history[:-16]
    return reply


@core.on_start
def warm_up() -> None:
    cfg = core.CONFIG.get("llm", {})
    if core.CONFIG.get("_game_mode"):
        return
    try:
        requests.post(cfg.get("ollama_url", "http://127.0.0.1:11434") + "/api/generate",
                      json={"model": cfg.get("model", "qwen3.5:2b"), "prompt": "", "keep_alive": "30m"}, timeout=120)
    except Exception:  # noqa: BLE001
        core.log.warning("Local model warm-up failed (is Ollama running?)")


@skill(
    "llm.advice",
    title={"ru": "Посоветовать, что делать дальше", "uz": "Keyin nima qilishni maslahat berish"},
    patterns={"ru": [r"(что|чем) (мне )?(стоит|лучше|нужно|надо) (сделать|заняться)", r"(с чего|что) (мне )?начать",
                     r"(дай|посоветуй) (совет|что делать)", r"что (мне )?делать"],
              "uz": [r"nima qilsam (boladi|yaxshi)", r"(maslahat ber|nimadan boshlay)"]},
    examples={"ru": ["Что мне стоит сделать сейчас?"], "uz": ["Nima qilsam yaxshi?"]},
    priority=36,
)
def advice(ctx: Ctx) -> str:
    return ask(ctx.text + ("\n(Посмотри на мои дела, сроки и непрочитанное и назови 2–3 самых важных шага по порядку.)"
                           if ctx.lang == "ru" else "\n(Vazifalarim va muddatlarga qarab 2–3 muhim qadamni ayt.)"),
               ctx.lang, max_tokens=400)


def understand(text: str, lang: str) -> str | None:
    """Map free wording to one of Jarvis's commands (or None if it's just conversation)."""
    examples = []
    for sk in core.SKILLS:
        if sk.module == "llm" or sk.name in core._NO_SMART:
            continue
        examples += sk.examples.get(lang, [])[:2]
    if not examples:
        return None
    prompt = ("Ты разбираешь фразы для голосового ассистента. Вот команды, которые он понимает:\n- "
              + "\n- ".join(examples)
              + "\n\nФраза пользователя: «" + text + "»\n"
              "Если пользователь просит что-то СДЕЛАТЬ, что подходит под одну из команд, перепиши его фразу в виде такой "
              "команды, сохранив все детали (что, кому, когда, название). Если это просто разговор, вопрос или мнение — "
              "ответь одним словом CHAT. Ответь только командой или CHAT, без пояснений.")
    try:
        cfg = core.CONFIG.get("llm", {})
        r = requests.post(cfg.get("ollama_url", "http://127.0.0.1:11434") + "/api/generate", json={
            "model": cfg.get("model", "qwen3.5:2b"), "prompt": prompt, "stream": False, "think": False,
            "keep_alive": "2m" if core.CONFIG.get("_game_mode") else "30m",
            "options": {"num_predict": 40, "temperature": 0},
        }, timeout=20)
        out = _clean(r.json().get("response", "")).strip(" .«»\"'")
    except Exception:  # noqa: BLE001
        return None
    if not out or "CHAT" in out.upper() or len(out) > 160 or out.lower() == text.lower():
        return None
    # the rewrite must keep the user's meaning: most of their content words must survive
    def stems(s: str) -> set:
        return {w[:5] for w in re.findall(r"[a-zа-яё']{4,}", s.lower())}
    orig, new = stems(text), stems(out)
    if orig and len(orig & new) / len(orig) < 0.5:
        core.log.info("smart router rejected rewrite %r -> %r", text, out)
        return None
    return out


@skill(
    "llm.chat",
    title={"ru": "Поговорить / ответить на любой вопрос (ИИ)", "uz": "Suhbat / har qanday savolga javob (AI)"},
    patterns={"ru": [r"^(?:спроси у ии|вопрос) (.+)$"], "uz": [r"^(?:savol) (.+)$"]},
    examples={"ru": ["Объясни, что такое инфляция", "Как прошёл твой день?"], "uz": ["Inflyatsiya nima?"]},
    priority=999,
)
def chat(ctx: Ctx) -> str:
    max_tokens, sentences = LIMITS[core.mode()]
    if ctx.source != "голос":
        return ask(ctx.text, ctx.lang, max_tokens=max_tokens * 3)
    reply = _short(ask(ctx.text, ctx.lang, max_tokens=max_tokens), sentences)
    # keep the conversation going without "Джарвис" again: in friend mode, or when Jarvis asked something
    if core.mode() == "friend" or reply.rstrip().endswith("?"):
        core.FOLLOWUP.set()
    return reply
