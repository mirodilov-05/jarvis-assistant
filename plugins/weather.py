"""Weather via Open-Meteo (free, no key). City is set in config.toml [weather] city."""

import requests

import core
from core import Ctx, skill

_CODES_RU = {0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман", 48: "туман",
             51: "морось", 53: "морось", 55: "сильная морось", 61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
             71: "небольшой снег", 73: "снег", 75: "сильный снег", 80: "ливень", 81: "ливень", 82: "сильный ливень",
             95: "гроза", 96: "гроза с градом", 99: "гроза с градом"}
_CODES_UZ = {0: "ochiq", 1: "asosan ochiq", 2: "qisman bulutli", 3: "bulutli", 45: "tuman", 48: "tuman",
             51: "mayda yomg'ir", 53: "mayda yomg'ir", 55: "mayda yomg'ir", 61: "yengil yomg'ir", 63: "yomg'ir",
             65: "kuchli yomg'ir", 71: "yengil qor", 73: "qor", 75: "kuchli qor", 80: "jala", 81: "jala",
             82: "kuchli jala", 95: "momaqaldiroq", 96: "do'l bilan momaqaldiroq", 99: "do'l bilan momaqaldiroq"}


def _geocode(city: str, lang: str = "ru"):
    """A city does not move: its coordinates are kept for a day."""
    return core.memo(f"geo:{city}:{lang}", 86400, lambda: _geocode_now(city, lang))


def _geocode_now(city: str, lang: str):
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1, "language": "ru" if lang == "ru" else "en"}, timeout=10)
    res = (r.json().get("results") or [None])[0]
    return (res["latitude"], res["longitude"], res["name"]) if res else None


def _forecast(lat: float, lon: float) -> dict:
    """The forecast is refreshed every ten minutes at most."""
    return core.memo(f"fc:{lat:.3f}:{lon:.3f}", 600, lambda: requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code", "timezone": "auto", "forecast_days": 2,
    }, timeout=10).json())


def short_weather(city: str, lang: str) -> str:
    if not city:
        return ""
    place = _geocode(city, lang)
    if not place:
        return ""
    lat, lon, name = place
    data = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code", "timezone": "auto",
    }, timeout=6).json()
    cur = data.get("current")
    if not cur:
        return ""
    t, code = round(cur["temperature_2m"]), cur["weather_code"]
    if lang == "uz":
        return f"{name}da hozir {t} daraja, {_CODES_UZ.get(code, '')}."
    return f"В городе {name} {t} градусов, {_CODES_RU.get(code, '')}."


@skill(
    "weather.now",
    title={"ru": "Погода сейчас и на завтра", "uz": "Ob-havo (hozir va ertaga)"},
    patterns={
        "ru": [r"погод\w*(?: в| во)? ?([а-я]+)?", r"(какая|сколько) (на улице )?(температура|градусов)"],
        "uz": [r"ob ?havo\w*(?: (?:qanday|qanaqa))?", r"(havo|harorat) (qanday|necha|qancha)"],
    },
    examples={"ru": ["Какая погода?", "Погода в Самарканде"], "uz": ["Ob-havo qanday?"]},
    priority=25,
)
def weather(ctx: Ctx) -> str:
    city = ctx.cfg("weather").get("city", "")
    if ctx.lang == "ru" and ctx.match and ctx.match.lastindex and ctx.group(1) not in ("", "сегодня", "завтра", "сейчас", "на"):
        city = ctx.group(1)
    if not city:
        return ctx.t("Для какого города? Скажите «мой город» и название, например «мой город Самарканд». "
                     "Я запомню его.", "Qaysi shahar uchun? Masalan: «mening shahrim Samarqand».")
    place = _geocode(city, ctx.lang)
    if not place:
        return ctx.t(f"Не нашёл город {city}.", f"{city} shahri topilmadi.")
    lat, lon, name = place
    r = _forecast(lat, lon)
    cur, daily = r["current"], r["daily"]
    t, code = round(cur["temperature_2m"]), cur["weather_code"]
    tmax, tmin, tcode = round(daily["temperature_2m_max"][1]), round(daily["temperature_2m_min"][1]), daily["weather_code"][1]
    if ctx.lang == "uz":
        return (f"{name}da hozir {t} daraja, {_CODES_UZ.get(code, '')}. "
                f"Ertaga {tmin} dan {tmax} darajagacha, {_CODES_UZ.get(tcode, '')}.")
    return (f"В городе {name} сейчас {t} градусов, {_CODES_RU.get(code, '')}. "
            f"Завтра от {tmin} до {tmax}, {_CODES_RU.get(tcode, '')}.")


@skill(
    "weather.set_city",
    title={"ru": "Запомнить мой город для погоды", "uz": "Shaharimni eslab qolish"},
    patterns={"ru": [r"^(?:джарвис )?(?:мой город|я живу в(?: городе)?|я из(?: города)?|запомни(?: мой)? город|город по умолчанию)"
                     r" (?P<c>[а-яa-z\- ]{2,30})$"],
              "uz": [r"^(?:jarvis )?mening shahrim (?P<c>[a-z\- ]{2,30})$"]},
    examples={"ru": ["Мой город Самарканд"], "uz": ["Mening shahrim Samarqand"]},
    priority=20,
)
def set_city(ctx: Ctx) -> str:
    city = ctx.match.group("c").strip()
    place = _geocode(city, ctx.lang)
    if not place:
        return ctx.t(f"Не нашёл город «{city}». Скажите название ещё раз.", f"«{city}» topilmadi.")
    name = place[2]
    core.save_setting("weather", "city", name)
    return ctx.t(f"Запомнил: ваш город {name}. Теперь «какая погода» — про него.", f"Eslab qoldim: {name}.")
