"""Computer control tools: apps, sites, games, music, search, sound, power."""

from tools import run_skill, tool

S = {"type": "string"}


@tool("open", "Открыть программу, игру, сайт, папку или сервис по названию (телеграм, стим, ютуб, яндекс музыка, "
      "загрузки, cs 2, https://...). Для нескольких — вызвать несколько раз.",
      {"target": {**S, "description": "Что открыть, как сказал пользователь, например «телеграм» или «cs 2»"}}, ["target"])
def open_(target: str) -> str:
    return run_skill("apps.open", f"открой {target}")


@tool("close_app", "Закрыть запущенную программу (программа сама спросит про несохранённое).",
      {"name": {**S, "description": "Название программы, например «телеграм», «discord», «хром»"}}, ["name"])
def close_app(name: str) -> str:
    return run_skill("apps.close", f"закрой {name}")


@tool("web_search", "Найти в интернете (откроется браузер с результатами).", {"query": S}, ["query"])
def web_search(query: str) -> str:
    return run_skill("apps.search", f"найди в интернете {query}")


@tool("youtube_search", "Найти видео на YouTube.", {"query": S}, ["query"])
def youtube_search(query: str) -> str:
    return run_skill("apps.youtube", f"найди на ютубе {query}")


@tool("play_music", "Включить музыку в Яндекс Музыке. Без query — просто открыть музыку; с query — найти песню/исполнителя/жанр.",
      {"query": {**S, "description": "Песня, исполнитель или настроение (необязательно)"}})
def play_music(query: str = "") -> str:
    return run_skill("apps.music", f"включи песню {query}" if query else "включи музыку")


@tool("volume", "Громкость: up — громче, down — тише, mute — выключить/включить звук.",
      {"action": {"type": "string", "enum": ["up", "down", "mute"]}}, ["action"])
def volume(action: str) -> str:
    return run_skill({"up": "system.volume_up", "down": "system.volume_down", "mute": "system.mute"}[action],
                     {"up": "громче", "down": "тише", "mute": "выключи звук"}[action])


@tool("media", "Управление музыкой/видео: pause (пауза/продолжить), next, previous.",
      {"action": {"type": "string", "enum": ["pause", "next", "previous"]}}, ["action"])
def media(action: str) -> str:
    return run_skill("system.media", {"pause": "пауза", "next": "следующий трек", "previous": "предыдущий трек"}[action])


@tool("screenshot", "Сделать скриншот экрана.")
def screenshot() -> str:
    return run_skill("system.screenshot", "сделай скриншот")


@tool("lock_pc", "Заблокировать компьютер.")
def lock_pc() -> str:
    return run_skill("system.lock", "заблокируй компьютер")


@tool("power", "Выключить (shutdown) или перезагрузить (restart) компьютер через минуту, или отменить (cancel).",
      {"action": {"type": "string", "enum": ["shutdown", "restart", "cancel"]}}, ["action"],
      tier="confirm", confirm_text=lambda action: {"shutdown": "выключить компьютер", "restart": "перезагрузить компьютер",
                                                   "cancel": "отменить выключение"}[action])
def power(action: str) -> str:
    if action == "cancel":
        return run_skill("system.shutdown_cancel", "отмени выключение")
    return run_skill("system.shutdown", "перезагрузи компьютер" if action == "restart" else "выключи компьютер")


@tool("look_at_screen", "Посмотреть на экран (активное окно) и ответить про то, что там видно: прочитать текст, "
      "объяснить ошибку, перевести, описать картинку или страницу.",
      {"question": {**S, "description": "Что пользователь хочет узнать про экран"}}, ["question"])
def look_at_screen(question: str) -> str:
    import vision
    return vision.look(question)


@tool("battery", "Узнать заряд батареи ноутбука.")
def battery() -> str:
    return run_skill("system.battery", "сколько заряда")


@tool("game_list", "Список установленных игр.")
def game_list() -> str:
    return run_skill("games.list", "какие у меня игры")


@tool("start_recording", "Начать запись голоса (диктофон) до слова «стоп».")
def start_recording() -> str:
    return run_skill("recorder.start", "запись") or "Начинаю запись."
