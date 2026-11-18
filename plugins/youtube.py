"""YouTube channels: subscribers, views, growth since yesterday, latest videos,
new comments. Uses the YouTube Data API v3 with your API key (Connections →
YouTube). Without a key only the latest uploads are read (RSS).
"""

import datetime as dt
import re
import xml.etree.ElementTree as ET

import requests

import connections
import core
from core import Ctx, skill

API = "https://www.googleapis.com/youtube/v3"
STATS_FILE = core.DATA / "youtube_stats.json"
SEEN_FILE = core.DATA / "youtube_seen.json"


def _key() -> str:
    return connections.get_secret("youtube:api_key")


def _get(endpoint: str, **params) -> dict:
    params["key"] = _key()
    r = requests.get(f"{API}/{endpoint}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def channels() -> list[str]:
    return [c.strip() for c in connections.load()["youtube"].get("channels", []) if c.strip()]


def channel_info(ref: str) -> dict | None:
    if ref.startswith("UC"):
        items = _get("channels", part="snippet,statistics,contentDetails", id=ref).get("items", [])
    else:
        handle = ref if ref.startswith("@") else "@" + ref.split("/")[-1].lstrip("@")
        items = _get("channels", part="snippet,statistics,contentDetails", forHandle=handle).get("items", [])
    if not items:
        return None
    it = items[0]
    st = it["statistics"]
    return {"id": it["id"], "title": it["snippet"]["title"], "subs": int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)), "videos": int(st.get("videoCount", 0)),
            "uploads": it["contentDetails"]["relatedPlaylists"]["uploads"]}


def latest_videos(info: dict, n: int = 3) -> list[dict]:
    items = _get("playlistItems", part="contentDetails,snippet", playlistId=info["uploads"], maxResults=n).get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return []
    stats = {v["id"]: v["statistics"] for v in _get("videos", part="statistics", id=",".join(ids)).get("items", [])}
    return [{"title": i["snippet"]["title"], "id": i["contentDetails"]["videoId"],
             "published": i["contentDetails"].get("videoPublishedAt", ""),
             "views": int(stats.get(i["contentDetails"]["videoId"], {}).get("viewCount", 0)),
             "likes": int(stats.get(i["contentDetails"]["videoId"], {}).get("likeCount", 0)),
             "comments": int(stats.get(i["contentDetails"]["videoId"], {}).get("commentCount", 0))} for i in items]


def new_comments(info: dict, limit: int = 5) -> list[dict]:
    try:
        data = _get("commentThreads", part="snippet", allThreadsRelatedToChannelId=info["id"], order="time", maxResults=20)
    except requests.HTTPError:
        return []
    seen = core.load_json(SEEN_FILE, {})
    last = seen.get(info["id"], "")
    out = []
    for t in data.get("items", []):
        c = t["snippet"]["topLevelComment"]["snippet"]
        if c["publishedAt"] > last:
            out.append({"author": c["authorDisplayName"], "text": re.sub(r"<[^>]+>", "", c["textDisplay"])[:200],
                        "published": c["publishedAt"]})
    if data.get("items"):
        seen[info["id"]] = data["items"][0]["snippet"]["topLevelComment"]["snippet"]["publishedAt"]
        core.save_json(SEEN_FILE, seen)
    return out[:limit]


def _growth(info: dict) -> tuple[int, int]:
    """Subscribers/views change vs the most recent snapshot from an earlier day."""
    data = core.load_json(STATS_FILE, {})
    hist = data.setdefault(info["id"], {})
    today = dt.date.today().isoformat()
    earlier = sorted(d for d in hist if d < today)
    base = hist[earlier[-1]] if earlier else None
    hist[today] = {"subs": info["subs"], "views": info["views"]}
    for d in sorted(hist)[:-60]:
        hist.pop(d)
    core.save_json(STATS_FILE, data)
    return (info["subs"] - base["subs"], info["views"] - base["views"]) if base else (0, 0)


def _rss_latest(channel_id: str) -> list[str]:
    r = requests.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id}, timeout=10)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return [e.find("a:title", ns).text for e in ET.fromstring(r.content).findall("a:entry", ns)[:3]]


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def report(lang: str, detailed: bool = True) -> str:
    chs = channels()
    if not chs:
        return ""
    if not _key():
        parts = []
        for ref in chs:
            if ref.startswith("UC"):
                try:
                    vids = _rss_latest(ref)
                    parts.append(("Последние видео: " if lang == "ru" else "Oxirgi videolar: ") + "; ".join(vids))
                except Exception:  # noqa: BLE001
                    pass
        hint = ("Для статистики YouTube добавьте API-ключ в «Подключениях»." if lang == "ru"
                else "YouTube statistikasi uchun API kalitini qo'shing.")
        return " ".join(parts + [hint])
    out = []
    for ref in chs:
        try:
            info = channel_info(ref)
        except Exception as e:  # noqa: BLE001
            out.append(f"YouTube {ref}: " + ("ошибка " if lang == "ru" else "xato ") + str(e)[:60])
            continue
        if not info:
            out.append(f"YouTube: {'канал не найден' if lang == 'ru' else 'kanal topilmadi'} {ref}.")
            continue
        dsubs, dviews = _growth(info)
        if lang == "ru":
            s = f"Канал {info['title']}: {_fmt(info['subs'])} подписчиков"
            if dsubs:
                s += f" ({'+' if dsubs > 0 else ''}{dsubs} с прошлой проверки)"
            s += f", {_fmt(info['views'])} просмотров."
        else:
            s = f"{info['title']} kanali: {_fmt(info['subs'])} obunachi"
            if dsubs:
                s += f" ({'+' if dsubs > 0 else ''}{dsubs})"
            s += f", {_fmt(info['views'])} ko'rish."
        if detailed:
            vids = latest_videos(info, 1)
            if vids:
                v = vids[0]
                s += (f" Последнее видео «{v['title']}»: {_fmt(v['views'])} просмотров, {v['likes']} лайков, {v['comments']} комментариев."
                      if lang == "ru" else
                      f" Oxirgi video «{v['title']}»: {_fmt(v['views'])} ko'rish, {v['likes']} layk, {v['comments']} izoh.")
            comments = new_comments(info, 3)
            if comments:
                s += (f" Новых комментариев: {len(comments)}. " if lang == "ru" else f" Yangi izohlar: {len(comments)} ta. ") + \
                     ". ".join(f"{c['author']}: {c['text']}" for c in comments) + "."
        out.append(s)
    return " ".join(out)


@skill(
    "youtube.stats",
    title={"ru": "Статистика моих YouTube-каналов", "uz": "YouTube kanallarim statistikasi"},
    patterns={"ru": [r"(ютуб|youtube|канал)\w*.*(статистик|подписчик|просмотр|как дела|что нового|отчет)",
                     r"(статистик|подписчик|просмотр)\w*.*(ютуб|youtube|канал)", r"сколько (у меня )?подписчиков"],
              "uz": [r"(youtube|yutub|kanal)\w*.*(statistika|obunachi|korish|yangilik)", r"nechta obunachi"]},
    examples={"ru": ["Статистика ютуба", "Сколько у меня подписчиков?"], "uz": ["YouTube statistikasi"]},
    priority=42,
)
def stats(ctx: Ctx) -> str:
    return report(ctx.lang) or ctx.t("YouTube-каналы не подключены. Добавьте их в окне Джарвиса → «Подключения».",
                                     "YouTube kanallar ulanmagan. Jarvis oynasi → «Подключения».")


@skill(
    "youtube.comments",
    title={"ru": "Новые комментарии на YouTube", "uz": "YouTube'dagi yangi izohlar"},
    patterns={"ru": [r"(комментари|коменты)\w*.*(ютуб|youtube|канал|новые)", r"(новые|прочитай) (комментари|коменты)"],
              "uz": [r"(yangi )?izohlar\w*.*(youtube|yutub|oqi)?"]},
    examples={"ru": ["Прочитай новые комментарии"], "uz": ["Yangi izohlarni o'qi"]},
    priority=41,
)
def comments(ctx: Ctx) -> str:
    if not channels() or not _key():
        return ctx.t("Для комментариев нужен API-ключ YouTube и каналы в «Подключениях».",
                     "Izohlar uchun YouTube API kaliti kerak.")
    parts = []
    for ref in channels():
        info = channel_info(ref)
        if info:
            cs = new_comments(info, 5)
            if cs:
                parts.append(f"{info['title']}: " + ". ".join(f"{c['author']}: {c['text']}" for c in cs))
    return " ".join(parts) + "." if parts else ctx.t("Новых комментариев нет.", "Yangi izohlar yo'q.")
