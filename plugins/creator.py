"""Content assistant for your YouTube / Reels / TikTok:

  «Найди, какие рилсы про нейросети залетели за ночь»  -> the most-viewed fresh short videos on the topic
  «Пиши сценарий под меня» / «Напиши сценарий про …»    -> a 30–45 s script in YOUR style, hook taken from the top hit
  «Запомни мой стиль: коротко, на ты, без воды»          -> remembered for every script
  «Мой канал про нейросети и игры»                       -> remembered too
  «Скинь мне в телегу» / «Отправь это в телеграм»        -> the last result goes to your Telegram (private bot)

Sources for trends: YouTube Data API (exact views; needs the YouTube key in ⚙ → Подключения),
Gemini with Google Search (sees Reels/TikTok too; needs the Gemini key), plus a direct YouTube search.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys

import core
from core import Ctx, skill

LAST: dict = {"trends": [], "topic": "", "script": "", "text": "", "title": ""}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "ru,en;q=0.8"}


def _pro():
    return sys.modules.get("jarvis_plugin_pro")


def _remember_result(title: str, text: str) -> None:
    LAST.update(title=title, text=text)


def _views(s: str) -> int:
    s = (s or "").replace("\xa0", " ").lower()
    m = re.search(r"([\d][\d\s.,]*)\s*(тыс|млн|млрд|k|m)?", s)
    if not m:
        return 0
    if m.group(2):
        n = float(m.group(1).replace(" ", "").replace(",", "."))
    else:
        n = float(re.sub(r"[^\d]", "", m.group(1)) or 0)
    return int(n * {"тыс": 1e3, "k": 1e3, "млн": 1e6, "m": 1e6, "млрд": 1e9}.get(m.group(2) or "", 1))


def _fmt(n: int) -> str:
    return f"{n / 1e6:.1f} млн".replace(".0 ", " ") if n >= 1e6 else f"{n / 1e3:.0f} тыс" if n >= 1e3 else str(n)


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

def _yt_api(topic: str, hours: int, shorts: bool) -> list[dict]:
    import connections
    import requests
    key = connections.get_secret("youtube:api_key")
    if not key:
        return []
    after = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"part": "snippet", "q": topic, "type": "video", "order": "viewCount", "publishedAfter": after,
              "maxResults": 25, "relevanceLanguage": "ru", "key": key}
    if shorts:
        params["videoDuration"] = "short"
    items = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=10).json().get("items", [])
    ids = ",".join(i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId"))
    if not ids:
        return []
    stats = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "statistics,snippet", "id": ids, "key": key}, timeout=10).json().get("items", [])
    return [{"title": s["snippet"]["title"], "views": int(s["statistics"].get("viewCount", 0)),
             "url": f"https://www.youtube.com/shorts/{s['id']}" if shorts else f"https://youtu.be/{s['id']}",
             "channel": s["snippet"].get("channelTitle", ""), "source": "YouTube"} for s in stats]


def _yt_scrape(topic: str, shorts: bool) -> list[dict]:
    import requests
    out = []
    for sp in ("EgQIAhAB", "EgQIAxAB"):           # today, this week (videos)
        try:
            r = requests.get("https://www.youtube.com/results", headers=UA, timeout=10,
                             params={"search_query": topic + (" shorts" if shorts else ""), "sp": sp, "hl": "ru"})
            data = json.loads(re.search(r"var ytInitialData = (\{.*?\});</script>", r.text, re.S).group(1))
        except Exception:  # noqa: BLE001
            continue

        def walk(o):
            if isinstance(o, dict):
                v = o.get("videoRenderer")
                if v and v.get("videoId"):
                    out.append({"title": v["title"]["runs"][0]["text"], "source": "YouTube",
                                "views": _views((v.get("viewCountText") or {}).get("simpleText", "")),
                                "url": f"https://youtu.be/{v['videoId']}",
                                "channel": ((v.get("ownerText") or {}).get("runs") or [{}])[0].get("text", ""),
                                "age": (v.get("publishedTimeText") or {}).get("simpleText", "")})
                for x in o.values():
                    walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(data)
    return out


def _gemini_trends(topic: str, hours: int) -> str:
    pro = _pro()
    if not pro:
        return ""
    period = "за последние сутки" if hours <= 24 else "за последнюю неделю"
    try:
        g = pro.gemini_search(f"Какие короткие видео (Instagram Reels, YouTube Shorts, TikTok) про «{topic}» {period} набрали "
                              "больше всего просмотров? Назови до 5 штук: о чём ролик, автор, площадка, примерно сколько "
                              "просмотров, и в чём их хук (первые секунды).")
    except Exception as e:  # noqa: BLE001
        core.log.warning("gemini trends: %s", e)
        return ""
    if not g:
        return ""
    text, links = g
    return text + ("\n\n" + "\n".join(f"• {t}: {u}" for t, u in links) if links else "")


def trends(topic: str, hours: int = 24, shorts: bool = True) -> tuple[str, str]:
    """(spoken answer, card text)"""
    vids = []
    try:
        vids = _yt_api(topic, hours, shorts)
    except Exception as e:  # noqa: BLE001
        core.log.warning("youtube api trends: %s", e)
    exact = bool(vids)
    if not vids:
        vids = _yt_scrape(topic, shorts)
    vids = sorted({v["url"]: v for v in vids}.values(), key=lambda v: v["views"], reverse=True)[:20]
    web = _gemini_trends(topic, hours)
    LAST.update(trends=vids, topic=topic)
    lines = [f"{i + 1}. {_fmt(v['views'])} — {v['title'][:90]} ({v.get('channel', '')}) {v['url']}" for i, v in enumerate(vids[:10])]
    card = ""
    if web:
        card += "🌐 Reels / Shorts / TikTok (поиск Google):\n" + web + "\n\n"
    if lines:
        card += ("▶ YouTube — точные данные:\n" if exact else "▶ YouTube — свежие ролики:\n") + "\n".join(lines)
    if not card:
        return f"Не нашёл свежих роликов про «{topic}», сэр.", ""
    _remember_result(f"Тренды · {topic}", card)
    if vids and exact:
        top = vids[0]
        spoken = f"Нашёл {len(vids)} свежих. Лучший набрал {_fmt(top['views'])} просмотров: «{top['title'][:70]}»."
    elif web:
        spoken = re.split(r"(?<=[.!?])\s+", web.strip())[0][:220] + " Подробности в окне."
    else:
        spoken = f"Нашёл {len(vids)} свежих роликов. Больше всего у «{vids[0]['title'][:70]}». Подробности в окне."
    return spoken, card


@skill("creator.trends", title={"ru": "Какие ролики (рилсы / шортсы) залетели за ночь по теме"},
       patterns={"ru": [r"(?:найди|покажи|какие|глянь|проверь|что)(?: мне)?,? (?:какие |что )?(?:рилс\w*|шортс\w*|ролик\w*|видео\w*|тикток\w*|тренд\w*)\s*(?:про|о|об|по теме|на тему|по)?\s*(.+?)\s*(?:залетел\w*|завирусил\w*|выстрелил\w*|в тренде|набрал\w*|популярн\w*)?\s*(?:за ночь|за сутки|сегодня|за неделю|за вчера)?$",
                        r"что (?:залетело|в тренде|завирусилось)(?: на ютубе| в рилсах| в тиктоке)? (?:про|по теме|на тему) (.+)$"]},
       examples={"ru": ["Найди, какие рилсы про нейросети залетели за ночь", "Что в тренде на тему игр за неделю"]},
       priority=4)
def trends_skill(ctx: Ctx):
    topic = re.sub(r"\s*(залетел\w*|завирусил\w*|выстрелил\w*|в тренде|набрал\w*|популярн\w*|за ночь|за сутки|сегодня|за неделю|за вчера)\s*",
                   " ", ctx.group(1) or "").strip(" ,.?")
    if not topic or len(topic) < 2:
        return None
    hours = 24 * 7 if "недел" in ctx.norm else 24
    shorts = not re.search(r"\bвидео\b(?! коротк)", ctx.norm) or bool(re.search(r"рилс|шортс|тикток|коротк", ctx.norm))
    spoken, card = trends(topic, hours, shorts)
    if card:
        core.emit({"type": "card", "title": f"Тренды · {topic}", "text": card, "ttl": 0})
    return spoken


# ---------------------------------------------------------------------------
# Your style and scripts
# ---------------------------------------------------------------------------

def style() -> str:
    return core.setting("creator", "style", "") or "коротко, на «ты», живо, с юмором, без воды"


@skill("creator.style", title={"ru": "Запомнить мой стиль / о чём мой канал"},
       patterns={"ru": [r"(?:запомни )?мой стиль\s*[:—-]?\s*(.+)$", r"(?:запомни,? (?:что )?)?мой канал (?:про|о|об) (.+)$",
                        r"(?:я снимаю|я делаю) (?:видео|ролики|рилсы|шортсы) (?:про|о|об) (.+)$"]},
       examples={"ru": ["Запомни мой стиль: коротко, на ты, без воды", "Мой канал про нейросети и игры"]}, priority=4)
def style_skill(ctx: Ctx) -> str:
    val = ctx.group(1).strip(" .")
    if "стиль" in ctx.norm:
        core.save_setting("creator", "style", val)
        return f"Запомнил ваш стиль: {val}."
    core.save_setting("creator", "about", val)
    return f"Запомнил: ваш канал про {val}."


def write_script(topic: str = "") -> str:
    pro = _pro()
    top = LAST["trends"][0] if LAST["trends"] else None
    topic = topic or LAST["topic"] or core.setting("creator", "about", "")
    about = core.setting("creator", "about", "")
    hook_src = f"Самый залетевший ролик по теме: «{top['title']}» ({_fmt(top['views'])} просмотров). Возьми из него идею хука, " \
               "но не копируй дословно." if top else ""
    prompt = (f"Напиши сценарий короткого вертикального видео (Reels/Shorts, 30–45 секунд) на тему «{topic}». "
              f"{'Канал автора: ' + about + '. ' if about else ''}Стиль автора: {style()}. {hook_src}\n"
              "Формат:\nХУК (0–3 с): одна фраза, которая цепляет.\nТЕКСТ: что говорить в кадре, короткими фразами.\n"
              "КАДРЫ: 3–5 подсказок, что показывать.\nФИНАЛ: призыв (подписка/коммент) в стиле автора.\n"
              "Пиши по-русски, разговорно, без воды и без пояснений вокруг сценария.")
    out = pro._write(prompt, 900) if pro else ""
    if out and not out.startswith("Нет связи"):
        LAST["script"] = out
        _remember_result(f"Сценарий · {topic}", out)
        pro.set_clipboard(out)
    return out


@skill("creator.script", title={"ru": "Сценарий ролика под меня (хук от залетевшего)"},
       patterns={"ru": [r"(?:пиши|напиши|сделай|составь|давай)(?: мне)? сценари\w*(?: только)?(?: под меня| для меня)?\s*(?:про|о|об|на тему|по)?\s*(.*)$"]},
       examples={"ru": ["Давай, пиши сценарий только под меня", "Напиши сценарий про бесплатные нейросети"]}, priority=4)
def script_skill(ctx: Ctx) -> str:
    topic = re.sub(r"^(?:только )?(?:под меня|для меня)\s*", "", ctx.group(1) or "").strip(" .")
    out = write_script(topic)
    if not out:
        return "Не получилось написать сценарий, сэр."
    core.emit({"type": "card", "title": "Сценарий (в буфере)", "text": out, "ttl": 0})
    hook = re.search(r"ХУК[^:\n]*:\s*(.+)", out)
    ref = " Хук взял у самого залетевшего, подачу под вас." if LAST["trends"] else ""
    return (f"Готово.{ref} Хук: {hook.group(1).strip()[:140]}" if hook else f"Готово.{ref}") + " Скинуть в телегу?"


# ---------------------------------------------------------------------------
# Send to Telegram
# ---------------------------------------------------------------------------

def last_text() -> tuple[str, str]:
    if LAST["text"]:
        return LAST["title"], LAST["text"]
    import importlib.util as _iu  # fallback: the last answer Jarvis gave
    _iu.find_spec("pcx")
    main = sys.modules.get("__main__")
    hist = list(getattr(main, "HISTORY", []))
    last = next((m["text"] for m in reversed(hist) if m.get("role") == "jarvis"), "")
    return "Джарвис", last


@skill("creator.send_tg", title={"ru": "Скинуть результат мне в Telegram"},
       patterns={"ru": [r"(?:скинь|отправь|пришли|кинь|перешли)(?: мне)?(?: это| его| её| ее| сценарий| список| результат| ответ)?\s*(?:сюда )?(?:в |на )?(?:телег\w*|телеграм\w*|тг|личку)",
                        r"^(?:да|давай|ага)?,?\s*скинь$"]},
       examples={"ru": ["Скинь мне в телегу", "Отправь сценарий в телеграм"]}, priority=3)
def send_tg(ctx: Ctx) -> str:
    import remote_bot
    title, text = last_text()
    if not text:
        return "Пока нечего отправлять, сэр."
    ok, why = remote_bot.notify(f"📌 {title}\n\n{text}")
    return "Скинул в телегу, сэр." + (" Читайте на светофоре, а не за рулём." if ok and ctx.source == "телеграм" else "") \
        if ok else why


core._LONG_OK.update({"creator.trends", "creator.script", "creator.style", "creator.send_tg"})
