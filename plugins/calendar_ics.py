"""Calendar events from private iCal links (Google Calendar: Settings → your
calendar → "Secret address in iCal format"; Outlook/Yandex/Apple have the same).
Links are stored in Windows Credential Manager (Connections → Calendar).
"""

import datetime as dt
import time
import json

import requests

import connections
import core
from core import Ctx, plural_ru, skill


def ics_urls() -> list[str]:
    raw = connections.get_secret("calendar:ics_urls")
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []


def set_urls(urls: list[str]) -> None:
    urls = [u.strip() for u in urls if u.strip()]
    connections.set_secret("calendar:ics_urls", json.dumps(urls) if urls else "")
    data = connections.load()
    data["calendar"]["count"] = len(urls)
    connections.save(data)


_CACHE: dict = {}        # (url, day, days) -> (time, events); one download per ten minutes
_BROKEN: set = set()     # calendars that failed to parse: said once, not on every request


def _fetch(url: str, start: dt.datetime, end: dt.datetime) -> list[dict]:
    import icalendar
    import recurring_ical_events

    raw = requests.get(url.replace("webcal://", "https://"), timeout=15).content
    try:
        cal = icalendar.Calendar.from_ical(raw)
    except ValueError:
        # one malformed line makes the whole file fail: drop the lines that cannot be read and try again
        lines = [ln for ln in raw.decode("utf-8", "replace").splitlines() if ":" in ln or ln[:1] in (" ", "\t")]
        cal = icalendar.Calendar.from_ical("\n".join(lines))
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        s = ev.get("DTSTART").dt
        all_day = not isinstance(s, dt.datetime)
        if isinstance(s, dt.datetime) and s.tzinfo:
            s = s.astimezone().replace(tzinfo=None)
        out.append({"title": str(ev.get("SUMMARY", "")), "start": s, "all_day": all_day,
                    "location": str(ev.get("LOCATION", "") or "")})
    return out


def events(day: dt.date, days: int = 1) -> list[dict]:
    start = dt.datetime.combine(day, dt.time.min)
    end = start + dt.timedelta(days=days)
    out = []
    for url in ics_urls():
        key = (url, day, days)
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < 600:
            out.extend(hit[1])
            continue
        try:
            got = _fetch(url, start, end)
            _CACHE[key] = (time.time(), got)
            out.extend(got)
            _BROKEN.discard(url)
        except Exception as e:  # noqa: BLE001 — one calendar must not break the others
            if url not in _BROKEN:
                _BROKEN.add(url)
                core.log.warning("Calendar could not be read (%s): %s", type(e).__name__, str(e)[:120])
    return sorted(out, key=lambda e: (not e["all_day"], str(e["start"])))


def summary(lang: str, day: dt.date | None = None) -> str:
    if not ics_urls():
        return ""
    day = day or dt.date.today()
    evs = events(day)
    if not evs:
        return "В календаре на сегодня событий нет." if lang == "ru" else "Bugun kalendarda tadbir yo'q."
    items = [(e["title"] if e["all_day"] else f"{e['start']:%H:%M} {e['title']}") for e in evs[:6]]
    n = len(evs)
    head = (f"В календаре {n} {plural_ru(n, 'событие', 'события', 'событий')}: " if lang == "ru"
            else f"Kalendarda {n} ta tadbir: ")
    return head + "; ".join(items) + "."


@skill(
    "calendar.day",
    title={"ru": "События в календаре (сегодня/завтра)", "uz": "Kalendar tadbirlari (bugun/ertaga)"},
    patterns={"ru": [r"(календар|событи|встреч)\w*.*(сегодня|завтра|какие|что)?", r"что (у меня )?(запланировано|в календаре)"],
              "uz": [r"(kalendar|tadbir|uchrashuv)\w*"]},
    examples={"ru": ["Какие встречи сегодня?", "Что в календаре завтра?"], "uz": ["Bugun qanday uchrashuvlar bor?"]},
    priority=33,
)
def day(ctx: Ctx) -> str:
    if not ics_urls():
        return ctx.t("Календарь не подключён. Добавьте ссылку iCal в окне Джарвиса → «Подключения».",
                     "Kalendar ulanmagan.")
    tomorrow = "завтра" in ctx.norm or "ertaga" in ctx.norm
    d = dt.date.today() + dt.timedelta(days=1 if tomorrow else 0)
    s = summary(ctx.lang, d)
    return s.replace("на сегодня", "на завтра").replace("Bugun", "Ertaga") if tomorrow else s
