"""Hands on the keyboard: Jarvis types, pastes, copies, writes prompts and texts for you, presses keys and repeats
what you asked before.

  «Напечатай привет, как дела»        — types into the window you're in (via the clipboard, any language)
  «Вставь» / «Скопируй это»           — Ctrl+V / Ctrl+C in the active window
  «Скопируй текст: …»                 — puts the text into the clipboard
  «Напиши промпт для …» (… «и вставь») — a ready prompt for ChatGPT / Claude / Midjourney into the clipboard (and pasted)
  «Напиши текст / пост / письмо / ответ про …» (… «и вставь»)
  «Нажми контрол эс», «Нажми энтер», «Нажми alt+tab»
  «Повтори» / «Ещё раз» / «Сделай то же самое» — repeats your last command
"""

from __future__ import annotations

import re
import sys
import time

import core
from core import Ctx, skill

_last: dict = {"cmd": ""}
_SKIP = re.compile(r"^(?:джарвис )?(?:повтори|ещё раз|еще раз|снова|сделай то же самое|сделай так же|да|нет|стоп)\b", re.I)


def _remember(ev: dict) -> None:
    """The last real command you gave (voice or text) — for «повтори»."""
    if ev.get("type") == "message" and ev.get("role") == "user" and ev.get("source") in ("голос", "текст", "телеграм"):
        text = re.sub(r"^📱\s*", "", ev.get("text", "")).strip()
        if text and not _SKIP.match(core.normalize(text, "ru")):
            _last["cmd"] = text


core.subscribe(_remember)


def _pro():
    return sys.modules.get("jarvis_plugin_pro")


def paste_text(text: str) -> bool:
    """Type text into the active window: put it into the clipboard and press Ctrl+V (works with any language)."""
    import keyboard
    pro = _pro()
    if not pro or not pro.set_clipboard(text):
        return False
    time.sleep(0.08)
    keyboard.send("ctrl+v")
    return True


@skill("assist.type", title={"ru": "Напечатать текст в активное окно"},
       patterns={"ru": [r"^(?:джарвис )?(?:напечатай|набери|впиши|введи|вставь текст|напиши (?:здесь|тут|в окне|в поле))\s*[:,]?\s+(.+)$"]},
       examples={"ru": ["Напечатай: привет, как дела?"]}, priority=7)
def type_text(ctx: Ctx) -> str:
    raw = re.search(r"(?:напечатай|набери|впиши|введи|вставь текст|напиши (?:здесь|тут|в окне|в поле))\s*[:,]?\s+(.+)$", ctx.text, re.I)
    text = (raw.group(1) if raw else ctx.group(1)).strip()
    return "Напечатал." if paste_text(text) else "Не получилось напечатать."


@skill("assist.paste", title={"ru": "Вставить (Ctrl+V)"},
       patterns={"ru": [r"^(?:джарвис )?(?:вставь|вставляй|вставь сюда|вставь из буфера)$"]},
       examples={"ru": ["Вставь"]}, priority=6)
def paste(ctx: Ctx) -> str:
    import keyboard
    keyboard.send("ctrl+v")
    return "Вставил."


@skill("assist.copy", title={"ru": "Скопировать (выделенное или текст)"},
       patterns={"ru": [r"^(?:джарвис )?(?:скопируй|копируй)(?: это| выделенное| всё| все)?$",
                        r"^(?:джарвис )?(?:скопируй|запиши в буфер)(?: текст)?\s*[:,]\s*(.+)$"]},
       examples={"ru": ["Скопируй это", "Скопируй текст: привет"]}, priority=6)
def copy(ctx: Ctx) -> str:
    raw = re.search(r"(?:скопируй|запиши в буфер)(?: текст)?\s*[:,]\s*(.+)$", ctx.text, re.I)
    if raw:
        _pro().set_clipboard(raw.group(1).strip())
        return "Скопировал в буфер."
    import pcx
    if re.search(r"вс[её]$", ctx.norm):
        import keyboard
        keyboard.send("ctrl+a")
        time.sleep(0.05)
    got = pcx.copy_from_app(["ctrl+c"])
    return f"Скопировал: {len(got)} символов." if got else "Ничего не выделено, сэр."


# ---------------------------------------------------------------------------
# Prompts and texts written for you
# ---------------------------------------------------------------------------

PROMPT_GUIDE = ("Ты — эксперт по промптам. Напиши один готовый к вставке промпт для нейросети по задаче пользователя. "
                "Промпт: роль, контекст, чёткая задача, требования к результату и формату, ограничения. "
                "Пиши на языке задачи (если не сказано иное), без пояснений вокруг — только сам промпт.")


def _write(prompt: str, max_tokens: int = 900) -> str:
    pro = _pro()
    return pro._write(prompt, max_tokens) if pro else ""


def _deliver(text: str, ctx: Ctx, title: str) -> str:
    pro = _pro()
    if not text or text.startswith("Нет связи"):
        return text or "Не получилось написать, сэр."
    pro.set_clipboard(text)
    pro.card(title + " (в буфере)", text, 0)
    if re.search(r"(?:и|потом) (?:вставь|напечатай|впиши)|вставь (?:его|её|ее|сюда)", ctx.norm):
        time.sleep(0.1)
        import keyboard
        keyboard.send("ctrl+v")
        return "Готово, вставил, сэр."
    return "Готово, сэр. Текст в буфере обмена — Ctrl+V."


@skill("assist.prompt", title={"ru": "Написать промпт для нейросети (в буфер / вставить)"},
       patterns={"ru": [r"(?:напиши|составь|сделай|придумай|дай)(?: мне)? (?:промпт|промт|запрос)(?: для нейросети| для чатгпт| для chatgpt| для claude| для клода| для миджорни| для midjourney)?\s*(?:для|чтобы|на|про|по)?\s*(.+)$"]},
       examples={"ru": ["Напиши промпт для логотипа моего канала и вставь"]}, priority=5)
def prompt(ctx: Ctx) -> str:
    task = re.sub(r"\s*(?:и|потом) (?:вставь|напечатай|впиши).*$", "", ctx.group(1)).strip()
    return _deliver(_write(PROMPT_GUIDE + "\n\nЗАДАЧА: " + task), ctx, "Промпт")


@skill("assist.write", title={"ru": "Написать текст, пост, письмо, ответ (в буфер / вставить)"},
       patterns={"ru": [r"(?:напиши|составь|сочини|набросай)(?: мне)? (текст|пост|письмо|ответ|описание|сообщение для|резюме|"
                        r"комментарий|статью|сценарий|план|отзыв|поздравление|объявление)\s*(?:про|о|об|для|на тему|к)?\s*(.+)$"]},
       examples={"ru": ["Напиши пост про мой новый ролик и вставь", "Составь письмо преподавателю о переносе экзамена"]},
       priority=6)
def write(ctx: Ctx) -> str:
    kind, about = ctx.group(1), re.sub(r"\s*(?:и|потом) (?:вставь|напечатай|впиши).*$", "", ctx.group(2)).strip()
    text = _write(f"Напиши {kind} {('про ' + about) if about else ''}. Готовый текст для вставки, без пояснений и "
                  "без кавычек вокруг. Язык — русский, если в задаче не сказано иное.")
    return _deliver(text, ctx, kind.capitalize())


# ---------------------------------------------------------------------------
# Keys and repeat
# ---------------------------------------------------------------------------

KEY_WORDS = {"контрол": "ctrl", "контрл": "ctrl", "ктрл": "ctrl", "кантрол": "ctrl", "шифт": "shift", "альт": "alt",
             "энтер": "enter", "ввод": "enter", "пробел": "space", "эскейп": "esc", "эскейт": "esc", "таб": "tab",
             "вин": "windows", "виндовс": "windows", "делит": "delete", "удалить": "delete", "бэкспейс": "backspace",
             "стрелка вверх": "up", "стрелка вниз": "down", "стрелка влево": "left", "стрелка вправо": "right",
             "вверх": "up", "вниз": "down", "влево": "left", "вправо": "right", "плюс": "+", "принтскрин": "print screen"}
LETTERS = {"а": "f", "б": ",", "в": "d", "г": "u", "д": "l", "е": "t", "ж": ";", "з": "p", "и": "b", "й": "q", "к": "r",
           "л": "k", "м": "v", "н": "y", "о": "j", "п": "g", "р": "h", "с": "c", "т": "n", "у": "e", "ф": "a", "х": "[",
           "ц": "w", "ч": "x", "ш": "i", "щ": "o", "ы": "s", "я": "z", "эс": "s", "си": "c", "ви": "v", "икс": "x",
           "зет": "z", "а англ": "a", "эф": "f", "эн": "n", "ти": "t", "дабл ю": "w", "вэ": "v", "эр": "r"}


def keys_from_words(text: str) -> str:
    t = text.lower().strip(" .")
    if re.fullmatch(r"[a-z0-9+ ]+", t):
        return t.replace(" ", "+") if "+" not in t else t.replace(" ", "")
    for ru, en in sorted(KEY_WORDS.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(rf"\b{ru}\b", f" {en} ", t)
    parts = []
    for w in re.split(r"[\s+]+", t):
        if not w:
            continue
        if re.fullmatch(r"f\d{1,2}|[a-z]|\d|ctrl|shift|alt|enter|space|esc|tab|windows|delete|backspace|up|down|left|right|print|screen", w):
            parts.append(w)
        elif w in ("эс", "си", "ви", "икс", "зет", "эф", "эн", "ти", "вэ", "эр"):
            parts.append(LETTERS[w])
    keys = "+".join(parts).replace("print+screen", "print screen")
    return keys


@skill("assist.keys", title={"ru": "Нажать клавиши («нажми контрол эс», «нажми энтер»)"},
       patterns={"ru": [r"^(?:джарвис )?(?:нажми|жми|нажать)(?: на)?(?: клавиш[уи])?\s+(.+)$"]},
       examples={"ru": ["Нажми контрол эс", "Нажми alt tab", "Нажми энтер"]}, priority=6)
def press(ctx: Ctx) -> str:
    keys = keys_from_words(ctx.group(1))
    if not keys:
        return "Не понял, какие клавиши, сэр. Например: «нажми контрол эс»."
    import keyboard
    try:
        keyboard.send(keys)
    except ValueError:
        return f"Не знаю клавишу «{ctx.group(1)}»."
    return f"Нажал {keys}."


@skill("assist.repeat", title={"ru": "Повторить последнюю команду"},
       patterns={"ru": [r"^(?:джарвис )?(?:повтори(?: последнюю команду| команду| это)?|ещё раз|еще раз|снова|сделай то же самое|сделай так же)$"]},
       examples={"ru": ["Повтори", "Ещё раз"]}, priority=4)
def repeat(ctx: Ctx) -> str:
    cmd = _last["cmd"]
    if not cmd:
        return "Пока нечего повторять, сэр."
    return core.route(cmd, ctx.lang, ctx.source, core.CONFIG)


core._LONG_OK.update({"assist.type", "assist.copy", "assist.prompt", "assist.write", "assist.keys"})
