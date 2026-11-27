"""Television intents: one table that turns a spoken or typed phrase into one TV action.

Rules, in this order:
  1. The phrase must name the TV (телевизор, телик, ТВ). Otherwise it is not a TV phrase at all.
  2. YouTube word -> open YouTube on the TV.
  3. Channel number («канал 5») -> the digits, one by one.
  4. Power, volume, channel, sound, playback, navigation -> the matching action.
  5. A TV phrase with no matching action -> 'unknown' (answered as «не понял», never sent to the brain).
"""
from __future__ import annotations

import re

TV = r"(?:телев[ие]?з\w*|телеиз\w*|телик\w*|телек\w*|тв)"
DIGITS = {str(i): f"KEY_{i}" for i in range(10)}


def _has(low: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(w)}", low) for w in words)


def tv_intent(low: str) -> tuple[str, dict] | None:
    """(tool, args) for a TV phrase; None when the phrase does not name the TV."""
    if not re.search(rf"(?<!\w){TV}(?!\w)", low):
        return None
    # 1. a YouTube video by its id (from a search): «открой видео dQw4w9WgXcQ на телевизоре»
    m = re.search(r"видео\s+([\w-]{11})\b", low)
    if m:
        return ("tv_video", {"video_id": m.group(1)})
    # 2. YouTube on the TV
    if re.search(r"\b(ютуб\w*|ютюб\w*|ютьюб\w*|youtube)\b", low):
        return ("tv_youtube", {})
    # 2b. any other app by name: «запусти netflix в телевизоре», «открой спотифай на телике»
    m = re.match(r"(?:запусти|открой|включи|поставь|покажи)(?: приложение)?\s+(.+)$", low)
    if m:
        name = re.sub(r"\s*(?:в|на|для)\s+(?:телевизор\w*|телеизор\w*|телик\w*|телек\w*|тв)\s*$", "", m.group(1)).strip()
        name = re.sub(r"^(?:в|на)\s+(?:телевизор\w*|телик\w*|телек\w*)\s+", "", name).strip()
        if name and not re.search(r"(?<!\w)" + TV + r"(?!\w)", name):
            return ("tv_app", {"name": name})
    # 3. a channel number
    m = re.search(r"\bканал\w*\s+(\d{1,3})\b", low) or re.search(r"\b(\d{1,3})\s+канал\w*\b", low)
    if m:
        return ("tv_digits", {"digits": m.group(1)})
    # 3b. universal phrasings: volume level, timed power-off, last channel, playback, info, input
    m = re.search(r"громкост\w*(?: телевизора| телика| тв)?\s+(?:на\s+)?(\d{1,3})\b", low)
    if m:
        return ("tv_volume_set", {"level": min(100, int(m.group(1)))})
    if _has(low, ("громкость на максимум", "максимальная громкость", "громкость максимум", "на полную громкость")):
        return ("tv_volume_set", {"level": 100})
    if _has(low, ("громкость на ноль", "громкость ноль", "минимальная громкость", "громкость минимум")):
        return ("tv_volume_set", {"level": 0})
    m = re.search(r"выключи\w*\s+(?:телевизор\w*|телик\w*|телек\w*|тв)?\s*через\s+(\d{1,3})\s*(минут\w*|час\w*)", low)
    if m:
        mins = int(m.group(1)) * (60 if m.group(2).startswith("час") else 1)
        return ("tv_off_later", {"minutes": mins})
    if _has(low, ("последний канал", "прошлый канал", "вернись на канал", "предыдущий прямой канал")):
        return ("tv_key", {"key": "KEY_PRECH"})
    if _has(low, ("перемотай назад", "перемотка назад", "отмотай назад", "назад на несколько")):
        return ("tv_key", {"key": "KEY_REW"})
    if _has(low, ("перемотай вперёд", "перемотай вперед", "перемотка вперёд", "перемотка вперед", "промотай вперёд")):
        return ("tv_key", {"key": "KEY_FF"})
    if _has(low, ("информация", "инфо", "что сейчас показывают", "что идёт", "что идет")):
        return ("tv_key", {"key": "KEY_INFO"})
    if _has(low, ("программа передач", "телегид", "гид", "расписание передач")):
        return ("tv_key", {"key": "KEY_GUIDE"})
    # 4. actions, most specific first
    if _has(low, ("канал вверх", "следующий канал", "канал плюс", "канал больше", "программа вверх",
                  "переключи канал вверх", "переключи на следующий", "следующая программа", "канал выше")):
        return ("tv_key", {"key": "KEY_CHUP"})
    if _has(low, ("канал вниз", "предыдущий канал", "канал минус", "канал меньше", "программа вниз",
                  "переключи канал вниз", "переключи на предыдущий", "предыдущая программа", "канал ниже")):
        return ("tv_key", {"key": "KEY_CHDOWN"})
    if _has(low, ("без звука", "выключи звук", "отключи звук", "звук выключи", "заглуши", "mute", "беззвучный")):
        return ("tv_key", {"key": "KEY_MUTE"})
    if _has(low, ("включи звук", "верни звук", "звук включи", "звук верни", "unmute")):
        return ("tv_key", {"key": "KEY_MUTE"})
    if _has(low, ("громче", "погромче", "прибавь", "увеличь громкость", "громкость больше", "громкость вверх", "добавь громкость", "громкость плюс")):
        return ("tv_volume", {"direction": "up"})
    if _has(low, ("тише", "потише", "убавь", "уменьши громкость", "громкость меньше", "громкость вниз", "убавь громкость", "громкость минус")):
        return ("tv_volume", {"direction": "down"})
    if _has(low, ("пауза", "останови", "приостанови", "поставь на паузу", "стоп")):
        return ("tv_key", {"key": "KEY_PAUSE"})
    if _has(low, ("играй", "продолжи", "воспроизведи", "запусти видео", "возобнови")):
        return ("tv_key", {"key": "KEY_PLAY"})
    if _has(low, ("домой", "главный экран", "главное меню", "на главный")):
        return ("tv_key", {"key": "KEY_HOME"})
    if _has(low, ("назад", "вернись", "обратно")):
        return ("tv_key", {"key": "KEY_RETURN"})
    if _has(low, ("меню", "настройки телевизора", "открой меню")):
        return ("tv_key", {"key": "KEY_MENU"})
    if _has(low, ("источник", "вход", "hdmi", "смени вход", "переключи вход")):
        return ("tv_key", {"key": "KEY_SOURCE"})
    if _has(low, ("вверх",)):
        return ("tv_key", {"key": "KEY_UP"})
    if _has(low, ("вниз",)):
        return ("tv_key", {"key": "KEY_DOWN"})
    if _has(low, ("влево",)):
        return ("tv_key", {"key": "KEY_LEFT"})
    if _has(low, ("вправо",)):
        return ("tv_key", {"key": "KEY_RIGHT"})
    if _has(low, ("ок", "выбери", "выбрать", "подтверди", "нажми ок", "нажми enter")):
        return ("tv_key", {"key": "KEY_ENTER"})
    if _has(low, ("выключи", "выключить", "выруби", "вырубай", "выключай", "отключи", "погаси")):
        return ("tv_off", {})
    if _has(low, ("включи", "включить", "вруби", "включай", "зажги", "запусти", "оживи")):
        return ("tv_on", {})
    if _has(low, ("статус", "как там", "работает ли", "включен", "включён", "горит", "состояние", "что с")):
        return ("tv_status", {})
    if re.fullmatch(rf"{TV}", low.strip()):
        return ("tv_status", {})
    return ("unknown", {})


def digit_keys(digits: str) -> list[str]:
    """Samsung keys for a channel number, e.g. '12' -> ['KEY_1', 'KEY_2']."""
    return [DIGITS[d] for d in digits if d in DIGITS]
