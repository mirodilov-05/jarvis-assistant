"""Brain tools: type / paste / copy text, write prompts and texts, press keys, repeat the last command, system check."""

from tools import run_skill, tool

S = {"type": "string"}


@tool("type_text", "Напечатать текст в активное окно (где сейчас курсор): сообщение, ответ, команду.",
      {"text": {**S, "description": "Что напечатать, дословно"}}, ["text"])
def type_text(text: str) -> str:
    return run_skill("assist.type", f"напечатай {text}")


@tool("write_prompt", "Написать готовый промпт для нейросети (ChatGPT, Claude, Midjourney…) и положить в буфер; "
      "paste=true — сразу вставить в активное окно.",
      {"task": {**S, "description": "Для чего промпт"}, "paste": {"type": "boolean"}}, ["task"])
def write_prompt(task: str, paste: bool = False) -> str:
    return run_skill("assist.prompt", f"напиши промпт для {task}" + (" и вставь" if paste else ""))


@tool("write_text", "Написать текст за пользователя: пост, письмо, ответ, описание, сценарий, план, поздравление… "
      "Кладёт в буфер обмена; paste=true — сразу вставить в активное окно.",
      {"kind": {**S, "enum": ["текст", "пост", "письмо", "ответ", "описание", "сценарий", "план", "поздравление", "комментарий", "статью"]},
       "about": {**S, "description": "О чём и для кого"}, "paste": {"type": "boolean"}}, ["kind", "about"])
def write_text(kind: str, about: str, paste: bool = False) -> str:
    return run_skill("assist.write", f"напиши {kind} про {about}" + (" и вставь" if paste else ""))


@tool("press_keys", "Нажать сочетание клавиш в активном окне, например ctrl+s, alt+tab, enter, f5.",
      {"keys": {**S, "description": "Сочетание в формате ctrl+shift+esc"}}, ["keys"])
def press_keys(keys: str) -> str:
    return run_skill("assist.keys", f"нажми {keys}")


@tool("repeat_last", "Повторить последнюю команду пользователя («ещё раз», «повтори»).")
def repeat_last() -> str:
    return run_skill("assist.repeat", "повтори")


@tool("system_check", "Проверить компьютер: что грузит процессор и память, диски, батарея, температура видеокарты.")
def system_check() -> str:
    return run_skill("pro.doctor", "проверь систему")
