"""Games: finds installed Steam and Epic games and game shortcuts, launches them.

"Запусти игру CS 2", "Поиграть в Dota", "Какие у меня игры?", "GTA o'yinini och".
"""

import difflib
import json
import os
import re
import winreg
from pathlib import Path

import core
from core import Ctx, skill

_cache: list[dict] = []


def _steam_games() -> list[dict]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        return []
    libs = {steam}
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        libs |= {Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore"))}
    games = []
    for lib in libs:
        for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
            txt = acf.read_text(encoding="utf-8", errors="ignore")
            appid = re.search(r'"appid"\s+"(\d+)"', txt)
            name = re.search(r'"name"\s+"([^"]+)"', txt)
            if appid and name and not re.search(r"(redistributable|steamworks|proton|runtime)", name.group(1), re.I):
                games.append({"name": name.group(1), "launch": f"steam://rungameid/{appid.group(1)}", "store": "Steam"})
    return games


def _epic_games() -> list[dict]:
    games = []
    for item in Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests").glob("*.item"):
        try:
            d = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
            games.append({"name": d["DisplayName"], "store": "Epic",
                          "launch": f"com.epicgames.launcher://apps/{d['AppName']}?action=launch&silent=true"})
        except Exception:  # noqa: BLE001
            continue
    return games


def _shortcut_games() -> list[dict]:
    games = []
    roots = [Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
             Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
             Path.home() / "Desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.url"):  # Steam/Epic desktop shortcuts are .url files
            try:
                body = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "steam://rungameid" in body or "com.epicgames.launcher" in body:
                games.append({"name": p.stem, "launch": str(p), "store": "ярлык"})
        for p in root.rglob("*.lnk"):
            if any(part.lower() in ("games", "игры", "steam", "epic games") for part in p.parts):
                games.append({"name": p.stem, "launch": str(p), "store": "ярлык"})
    return games


def all_games(refresh: bool = False) -> list[dict]:
    if _cache and not refresh:
        return _cache
    seen, out = set(), []
    for g in _steam_games() + _epic_games() + _shortcut_games():
        key = g["name"].lower()
        if key not in seen:
            seen.add(key)
            out.append(g)
    _cache[:] = sorted(out, key=lambda g: g["name"].lower())
    return _cache


_ALIASES = {"кс": "counter-strike", "контра": "counter-strike", "кс го": "counter-strike", "cs": "counter-strike",
            "дота": "dota", "гта": "grand theft auto", "gta": "grand theft auto", "майнкрафт": "minecraft",
            "фортнайт": "fortnite", "пабг": "pubg", "валорант": "valorant", "варзон": "call of duty",
            "колда": "call of duty", "фифа": "fc", "fifa": "fc", "роблокс": "roblox", "раст": "rust"}


def find_game(name: str):
    games = all_games()
    if not games:
        return None
    q = name.lower().strip()
    q = _ALIASES.get(q, q)
    names = {g["name"].lower(): g for g in games}
    for n, g in names.items():
        if n == q or n.startswith(q) or q in n:
            return g
    compact = {re.sub(r"[^a-z0-9а-я]", "", n): g for n, g in names.items()}
    cq = re.sub(r"[^a-z0-9а-я]", "", q)
    for n, g in compact.items():
        if cq and cq in n:
            return g
    close = difflib.get_close_matches(q, list(names), n=1, cutoff=0.6)
    return names[close[0]] if close else None


@skill(
    "games.launch",
    title={"ru": "Запустить игру (Steam, Epic, ярлыки)", "uz": "O'yinni ishga tushirish"},
    patterns={"ru": [r"^(?:джарвис )?(?:запусти|включи|открой) игру (.+)$", r"^(?:джарвис )?(?:хочу )?поиграть в (.+)$",
                     r"^(?:джарвис )?(?:давай )?играть в (.+)$"],
              "uz": [r"^(?:jarvis )?(.+?) oyin\w* (?:och|boshla|qoy|ishga tushir)\w*$", r"^(?:jarvis )?(.+?) oyna\w*$"]},
    examples={"ru": ["Запусти игру Dota 2", "Поиграть в CS"], "uz": ["Dota o'yinini och"]},
    priority=48,
)
def launch(ctx: Ctx) -> str:
    q = ctx.group(1)
    g = find_game(q)
    if not g:
        all_games(refresh=True)  # maybe installed since the last scan
        g = find_game(q)
    if not g:
        return ctx.t(f"Не нашёл игру «{q}». Скажите «какие у меня игры», чтобы услышать список.",
                     f"«{q}» o'yini topilmadi.")
    os.startfile(g["launch"])
    return ctx.t(f"Запускаю {g['name']}. Удачной игры!", f"{g['name']} ishga tushirilmoqda. Omad!")


@skill(
    "games.list",
    title={"ru": "Список моих игр", "uz": "O'yinlarim ro'yxati"},
    patterns={"ru": [r"(какие|покажи|список|сколько) (у меня )?(игр|игры)"], "uz": [r"(qanday|qaysi) oyinlar\w*", r"oyinlarim"]},
    examples={"ru": ["Какие у меня игры?"], "uz": ["Qanday o'yinlarim bor?"]},
    priority=49,
)
def list_games(ctx: Ctx) -> str:
    games = all_games(refresh=True)
    if not games:
        return ctx.t("Не нашёл установленных игр в Steam, Epic и на рабочем столе.", "O'rnatilgan o'yinlar topilmadi.")
    names = ", ".join(g["name"] for g in games[:15])
    return ctx.t(f"Нашёл игр: {len(games)}. {names}.", f"{len(games)} ta o'yin topildi: {names}.")
