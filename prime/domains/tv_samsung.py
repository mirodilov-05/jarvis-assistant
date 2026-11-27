"""Samsung TV (Tizen) over the local network.

  Power on   — Wake-on-LAN to the MAC in config/devices.yaml (the TV must be in standby with network on).
  Status     — HTTP on port 8001: the TV reports its PowerState (standby / on).
  Keys       — websocket on port 8002: volume, power off, and so on, like a remote control.
  Apps       — HTTP on port 8001: start YouTube and other apps by their id.

The first control connection makes the TV show an «Allow» prompt. Press Allow on the TV once; the pairing
token it returns is stored in prime/data/tv_token.txt (kept out of git) and used for every later call.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import ssl
from pathlib import Path
from typing import Any

log = logging.getLogger("prime.tv")
TOKEN_FILE = Path(__file__).resolve().parent.parent / "data" / "tv_token.txt"
APP_YOUTUBE = "111299001912"           # Samsung's id for the YouTube app
CLIENT_NAME = base64.b64encode(b"JarvisPrime").decode()


class TvError(RuntimeError):
    """A readable reason the TV could not do the thing; the message is shown to the owner."""


def _settings(cfg: dict[str, Any]) -> tuple[str, str]:
    ip, mac = (cfg.get("ip") or "").strip(), (cfg.get("mac") or "").strip()
    if not ip:
        raise TvError("телевизор не настроен: нет IP в config\\devices.yaml")
    return ip, mac


def _load_token() -> str:
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _save_token(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")


async def status(cfg: dict[str, Any]) -> dict[str, Any]:
    """{'online': bool, 'power': 'on'|'standby'|None, 'model': str}. Never raises."""
    import aiohttp
    ip, _ = _settings(cfg)
    try:
        timeout = aiohttp.ClientTimeout(total=4)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f"http://{ip}:8001/api/v2/") as r:
                data = await r.json(content_type=None)
    except Exception:  # noqa: BLE001 — off or not on the network
        return {"online": False, "power": None, "model": ""}
    dev = data.get("device", {})
    return {"online": True, "power": dev.get("PowerState", "on"), "model": dev.get("modelName", "")}


async def wake(cfg: dict[str, Any], wait: float | None = None) -> str:
    """Turn the TV on from standby and report how long it took. wait: seconds to watch for it (default WAKE_WAIT_S).

    First choice: the power key over the open remote-control link (about 2 seconds on this TV, measured).
    Fallback: Wake-on-LAN packets to the cable and Wi-Fi addresses, if the link does not answer.
    """
    import time
    from domains.device_hub import wake_on_lan
    wait = WAKE_WAIT_S if wait is None else wait
    ip, mac = _settings(cfg)
    t0 = time.monotonic()
    try:
        await _drop()
        await asyncio.wait_for(_send(cfg, ["KEY_POWER"]), timeout=6)
        via = "по сети"
    except (TvError, asyncio.TimeoutError):
        via = None
        macs = [m for m in (mac, cfg.get("mac_wifi")) if m]
        if not macs:
            raise TvError("нет MAC для включения по сети в config\\devices.yaml")
        for _ in range(3):                                        # a few packets: the first one can be lost
            for m in macs:
                await asyncio.to_thread(wake_on_lan, m)
            await asyncio.sleep(0.3)
    while time.monotonic() - t0 < wait:
        st = await status(cfg)
        if st["online"] and st["power"] == "on":
            return f"Телевизор включился за {time.monotonic() - t0:.0f} с" + (f" ({via})." if via else " (пакетом сети).")
        await asyncio.sleep(0.5)
    if wait < WAKE_WAIT_S:          # the command is sent: he is still starting, do not keep the owner waiting
        return "Включаю телевизор, он ещё загружается. Через несколько секунд будет готов."
    return (f"Телевизор не ответил за {WAKE_WAIT_S:.0f} с. Проверьте в его настройках «Включение по сети» "
            "и что он подключён к той же сети.")


# One open connection is kept between commands: opening it costs about a second, sending a key costs milliseconds.
_LINK: dict[str, Any] = {"session": None, "ws": None, "ip": None, "used": 0.0, "lock": None}
WAKE_WAIT_S = 25.0                  # how long a switch-on is watched before giving up
IDLE_CLOSE_S = 120.0                    # a stale link is dropped sooner; the TV drops quiet links itself                    # the connection is closed after this much idle time (the TV drops it anyway)


async def _connect(ip: str) -> Any:
    import aiohttp
    token = _load_token()
    url = f"wss://{ip}:8002/api/v2/channels/samsung.remote.control?name={CLIENT_NAME}"
    if token:
        url += f"&token={token}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE                       # the TV uses its own self-signed certificate on the LAN
    session = aiohttp.ClientSession()
    try:
        ws = await session.ws_connect(url, ssl=ctx, timeout=6, heartbeat=20)
        # the TV sends its first message right after connecting (and the token once allowed)
        first = await asyncio.wait_for(ws.receive(), timeout=8)
        if first.type == aiohttp.WSMsgType.TEXT:
            tok = (json.loads(first.data).get("data") or {}).get("token")
            if tok:
                _save_token(str(tok))
    except BaseException:
        await session.close()
        raise
    _LINK.update(session=session, ws=ws, ip=ip)
    return ws


async def _drop() -> None:
    for k in ("ws", "session"):
        obj = _LINK.get(k)
        _LINK[k] = None
        if obj is not None:
            try:
                await obj.close()
            except Exception:  # noqa: BLE001 — already closed
                pass


async def _send(cfg: dict[str, Any], keys: list[str]) -> None:
    """Send remote-control keys. Reuses the open connection; reconnects once if it was dropped."""
    import time
    import aiohttp
    ip, _ = _settings(cfg)
    if _LINK["lock"] is None:
        _LINK["lock"] = asyncio.Lock()
    async with _LINK["lock"]:
        if _LINK["ws"] is not None and (_LINK["ip"] != ip or time.monotonic() - _LINK["used"] > IDLE_CLOSE_S
                                        or _LINK["ws"].closed):
            await _drop()
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                ws = _LINK["ws"] or await _connect(ip)
                for key in keys:
                    await ws.send_str(json.dumps({"method": "ms.remote.control", "params": {
                        "Cmd": "Click", "DataOfCmd": key, "Option": "false", "TypeOfRemote": "SendRemoteKey"}}))
                    await asyncio.sleep(0.04)                 # the TV needs a moment between keys
                _LINK["used"] = time.monotonic()
                return
            except asyncio.TimeoutError as e:
                await _drop()
                raise TvError("телевизор не ответил: если он впервые, нажмите «Разрешить» на экране телевизора") from e
            except (aiohttp.ClientError, ConnectionError, OSError) as e:
                last_error = e
                await _drop()
        raise TvError("телевизор недоступен по сети или выключен") from last_error


async def press(cfg: dict[str, Any], keys: list[str]) -> str:
    if "KEY_POWER" in keys:
        await _drop()          # power keys always use a fresh link: a stale one swallows the key silently
    await _send(cfg, keys)
    return "Готово."


async def open_youtube(cfg: dict[str, Any]) -> str:
    import aiohttp
    ip, _ = _settings(cfg)
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f"http://{ip}:8001/api/v2/applications/{APP_YOUTUBE}") as r:
                if r.status not in (200, 201):
                    raise TvError(f"телевизор не открыл YouTube (код {r.status})")
    except aiohttp.ClientError as e:
        raise TvError("телевизор недоступен по сети или выключен") from e
    return "Открываю YouTube на телевизоре."


# Apps installed on the TV. IDs were checked on the owner's TV (GET /api/v2/applications/<id> answers for
# installed apps only). More apps can be added in data/tv_apps.json as {"name": "id"}.
APP_CATALOG = {"youtube": APP_YOUTUBE, "netflix": "3201907018807", "prime video": "3201910019365",
               "spotify": "3201606009684"}
APP_ALIASES = {"youtube": ["youtube", "ютуб", "ютюб", "ютьюб", "музык"],   # «поставь музыку в телевизоре» = YouTube
               "netflix": ["netflix", "нетфликс", "нетфлекс", "нэтфликс", "нетфлэкс"],
               "prime video": ["prime video", "прайм видео", "прайм", "амазон", "amazon prime"],
               "spotify": ["spotify", "спотифай", "спотифи", "спотик"]}
APPS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "tv_apps.json"


def _catalog() -> dict:
    import json
    cat = dict(APP_CATALOG)
    try:
        cat.update({str(k).lower(): str(v) for k, v in json.loads(APPS_FILE.read_text(encoding="utf-8")).items()})
    except (OSError, ValueError):
        pass
    return cat


def resolve_app(name: str) -> tuple[str, str] | None:
    """(canonical name, app id) of the TV app the spoken name means, or None if unknown."""
    low = name.lower().strip()
    if not low:
        return None
    for canonical, app_id in _catalog().items():
        names = [canonical] + APP_ALIASES.get(canonical, [])
        if any(n in low for n in names):
            return canonical, app_id
    return None


async def launch_app(cfg: dict[str, Any], app_id: str, payload: dict | None = None) -> None:
    import aiohttp
    ip, _ = _settings(cfg)
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f"http://{ip}:8001/api/v2/applications/{app_id}", json=payload) as r:
                if r.status not in (200, 201):
                    raise TvError(f"телевизор не открыл приложение (код {r.status})")
    except aiohttp.ClientError as e:
        raise TvError("телевизор недоступен по сети или выключен") from e


async def open_app(cfg: dict[str, Any], name: str) -> str:
    hit = resolve_app(name)
    if hit is None:
        known = ", ".join(sorted(_catalog()))
        return (f"На телевизоре я не знаю приложение «{name}». Пока умею: {known}. "
                f"Добавить новое можно в data/tv_apps.json, указав его id.")
    canonical, app_id = hit
    await launch_app(cfg, app_id)
    return f"Открываю {canonical} на телевизоре."


async def open_youtube_video(cfg: dict[str, Any], video_id: str) -> str:
    await launch_app(cfg, APP_YOUTUBE, {"v": video_id})
    return "Открываю видео на YouTube в телевизоре."


VOLUME_UP, VOLUME_DOWN, POWER_OFF, MUTE = "KEY_VOLUP", "KEY_VOLDOWN", "KEY_POWER", "KEY_MUTE"
