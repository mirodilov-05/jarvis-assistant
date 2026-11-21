"""Brain tools: windows, brightness, exact volume, file search, phrase translation, currency conversion, learn programs."""

from tools import run_skill, tool

S = {"type": "string"}


@tool("window", "Управление окнами: minimize_all (свернуть всё / рабочий стол), maximize, minimize, close (закрыть текущее окно), "
      "switch (alt+tab), left, right (прижать окно к краю).",
      {"action": {**S, "enum": ["minimize_all", "maximize", "minimize", "close", "switch", "left", "right"]}}, ["action"])
def window(action: str) -> str:
    phrase = {"minimize_all": "сверни все окна", "maximize": "разверни окно", "minimize": "сверни окно",
              "close": "закрой окно", "switch": "переключи окно", "left": "окно влево", "right": "окно вправо"}[action]
    return run_skill("desktop.windows", phrase)


@tool("brightness", "Яркость экрана: level 0–100, или change (+20 ярче, -20 темнее).",
      {"level": {"type": "integer"}, "change": {"type": "integer"}})
def brightness(level: int | None = None, change: int | None = None) -> str:
    if level is not None:
        return run_skill("desktop.brightness", f"яркость {int(level)}")
    return run_skill("desktop.brightness", "ярче" if (change or 0) >= 0 else "темнее")


@tool("set_volume", "Поставить общую громкость Windows на точное значение 0–100.", {"level": {"type": "integer"}}, ["level"])
def set_volume(level: int) -> str:
    return run_skill("desktop.volume_level", f"громкость {int(level)}")


@tool("find_file", "Найти файл на компьютере (документы, загрузки, рабочий стол, диск D) по словам из названия; "
      "open=true — сразу открыть самый свежий.",
      {"query": {**S, "description": "Слова из названия файла"}, "open": {"type": "boolean"}}, ["query"])
def find_file(query: str, open: bool = False) -> str:  # noqa: A002
    return run_skill("desktop.find_file", f"{'открой файл' if open else 'найди файл'} {query}")


@tool("translate_phrase", "Перевести фразу на другой язык (английский, японский, узбекский, немецкий…), результат в буфер.",
      {"text": S, "language": {**S, "description": "Язык по-русски, например «английский»"}}, ["text", "language"])
def translate_phrase(text: str, language: str) -> str:
    return run_skill("desktop.translate_phrase", f"переведи на {language} {text}")


@tool("convert_currency", "Перевести сумму из одной валюты в другую по текущему курсу (доллары, евро, рубли, сумы, тенге…).",
      {"amount": {"type": "number"}, "from_currency": {**S, "description": "по-русски: долларов, евро, рублей, сумов"},
       "to_currency": {**S, "description": "по-русски: в сумах, в рублях…"}}, ["amount", "from_currency", "to_currency"])
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    return run_skill("desktop.convert", f"сколько будет {amount:g} {from_currency} в {to_currency}")


@tool("learn_programs", "Изучить установленные программы заново (после установки новых), чтобы открывать их по-русски.")
def learn_programs() -> str:
    return run_skill("apps.learn", "изучи мои программы")
