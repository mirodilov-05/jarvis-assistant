"""Live data and actions for the 30 home widgets.

Reading: snapshot() collects everything the page shows. Each source has its own refresh time and is refreshed in a
background thread, so a slow source (ping, Bluetooth, weather) never delays the page: the page gets the last value.
Nothing is collected unless the page asks (it stops asking when it is hidden).

Reading the TV state goes straight to the TV over HTTP. It is NOT sent as a voice command: that would fill the command
history and cancel a question that is waiting for «да» or «нет».

Acting: action() accepts a fixed list of actions with checked arguments. Programs are opened and closed only by a name
from the Start Menu list; a process is ended only if its pid and name still match and it is not a system process.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

import psutil

import procs

BASE = Path(__file__).resolve().parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PRIME = "http://127.0.0.1:8765"
_POOL = ThreadPoolExecutor(max_workers=5, thread_name_prefix="hud")
_CACHE: dict[str, dict] = {}
_LOCK = threading.Lock()


# ------------------------------------------------------------------------------------------------ cache

def _refresh(name: str, fn) -> None:
    try:
        value = fn()
        with _LOCK:
            _CACHE[name].update(value=value, at=time.time(), error="")
    except Exception as e:  # noqa: BLE001 — one broken source must not break the page
        with _LOCK:
            _CACHE[name].update(at=time.time(), error=f"{type(e).__name__}: {str(e)[:120]}")
    finally:
        with _LOCK:
            _CACHE[name]["busy"] = False


def cached(name: str, ttl: float, fn):
    """Last known value; starts a background refresh when it is older than `ttl` seconds."""
    with _LOCK:
        c = _CACHE.setdefault(name, {"value": None, "at": 0.0, "busy": False, "error": ""})
        stale = time.time() - c["at"] > ttl and not c["busy"]
        if stale:
            c["busy"] = True
    if stale:
        _POOL.submit(_refresh, name, fn)
    return c["value"]


def invalidate(*names: str) -> None:
    with _LOCK:
        for n in names:
            if n in _CACHE:
                _CACHE[n]["at"] = 0.0


def _run(cmd: list[str], timeout: float = 6, encoding: str = "cp866") -> str:
    return subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW).stdout.decode(encoding, "replace")


def _http_json(url: str, body: dict | None = None, timeout: float = 4):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    head = {"Content-Type": "application/json", **({"X-Jarvis": "1"} if url.startswith(PRIME) else {})}
    req = urllib.request.Request(url, data, head)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ------------------------------------------------------------------------------------------------ sources

def _gpu() -> dict | None:
    out = _run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits"], 4, "utf-8").strip()
    if not out:
        return None
    name, util, used, total, temp = [x.strip() for x in out.splitlines()[0].split(",")]
    return {"name": name.replace("NVIDIA ", ""), "util": int(util), "used": int(used), "total": int(total), "temp": int(temp)}


_CPU = {"at": 0.0, "v": 0.0}


def _cpu() -> float:
    """CPU load over at least one second: two windows asking at once would otherwise read 0%."""
    if time.time() - _CPU["at"] >= 1:
        _CPU.update(v=psutil.cpu_percent(None), at=time.time())
    return _CPU["v"]


def _system() -> dict:
    m = psutil.virtual_memory()
    return {"cpu": _cpu(), "cores": psutil.cpu_count(), "ram_used": round(m.used / 2**30, 1),
            "ram_total": round(m.total / 2**30, 1), "ram_pct": m.percent, "uptime": int(time.time() - psutil.boot_time()),
            "procs": len(procs.snapshot(4))}


_NET = {"at": 0.0, "sent": 0, "recv": 0, "up": 0.0, "down": 0.0}


def _net_rate() -> dict:
    c, now = psutil.net_io_counters(), time.time()
    if _NET["at"] and now - _NET["at"] > 0.5:
        d = now - _NET["at"]
        _NET["up"], _NET["down"] = max(0, c.bytes_sent - _NET["sent"]) / d, max(0, c.bytes_recv - _NET["recv"]) / d
    if not _NET["at"] or now - _NET["at"] > 0.5:
        _NET.update(at=now, sent=c.bytes_sent, recv=c.bytes_recv)
    return {"up": round(_NET["up"]), "down": round(_NET["down"]), "total_up": c.bytes_sent, "total_down": c.bytes_recv}


def _ping() -> int | None:
    m = re.search(r"[=<]\s*(\d+)\s*(?:мс|ms)", _run(["ping", "-n", "1", "-w", "900", "1.1.1.1"], 4))
    return int(m.group(1)) if m else None


def _wifi() -> dict:
    out = _run(["netsh", "wlan", "show", "interfaces"], 6)
    ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
    sig = re.search(r":\s*(\d{1,3})%", out)
    vpn = [n for n, s in psutil.net_if_stats().items() if s.isup and re.search(r"warp|vpn|wireguard|tailscale|\btun", n, re.I)]
    return {"ssid": ssid.group(1).strip() if ssid else "", "signal": int(sig.group(1)) if sig else None, "vpn": vpn[:1]}


def _ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def _disks() -> list[dict]:
    out = []
    for p in psutil.disk_partitions():
        if not p.fstype or "cdrom" in p.opts:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        out.append({"name": p.device[:2], "used": round(u.used / 2**30), "total": round(u.total / 2**30),
                    "free": round(u.free / 2**30), "pct": u.percent})
    return out


def _battery() -> dict | None:
    b = psutil.sensors_battery()
    if b is None:
        return None
    left = b.secsleft if b.secsleft and b.secsleft > 0 and not b.power_plugged else None
    return {"pct": round(b.percent), "plugged": bool(b.power_plugged), "left": left}


class _DevMode(ctypes.Structure):
    _fields_ = [("name", wintypes.WCHAR * 32), ("a", wintypes.WORD * 4), ("fields", wintypes.DWORD), ("x", wintypes.LONG),
                ("y", wintypes.LONG), ("orient", wintypes.DWORD), ("fixed", wintypes.DWORD), ("b", wintypes.SHORT * 5),
                ("form", wintypes.WCHAR * 32), ("logpix", wintypes.WORD), ("bpp", wintypes.DWORD), ("w", wintypes.DWORD),
                ("h", wintypes.DWORD), ("flags", wintypes.DWORD), ("hz", wintypes.DWORD), ("c", wintypes.DWORD * 8)]


class _DisplayDevice(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("name", wintypes.WCHAR * 32), ("text", wintypes.WCHAR * 128),
                ("state", wintypes.DWORD), ("id", wintypes.WCHAR * 128), ("key", wintypes.WCHAR * 128)]


def _screens() -> list[dict]:
    user32, out, i = ctypes.windll.user32, [], 0
    dev = _DisplayDevice()
    dev.cb = ctypes.sizeof(dev)
    while user32.EnumDisplayDevicesW(None, i, ctypes.byref(dev), 0):
        i += 1
        if not dev.state & 1:                                     # attached to the desktop
            continue
        mode = _DevMode()
        mode.a[2] = ctypes.sizeof(mode)                           # dmSize
        if user32.EnumDisplaySettingsW(dev.name, -1, ctypes.byref(mode)):
            out.append({"w": mode.w, "h": mode.h, "hz": mode.hz, "primary": bool(dev.state & 4)})
    return out


def _brightness() -> int | None:
    out = _run(["powershell", "-NoProfile", "-Command",
                "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness).CurrentBrightness"], 40, "utf-8").strip()
    return int(out.splitlines()[0]) if out and out.splitlines()[0].isdigit() else None


def _com():
    import comtypes
    try:
        comtypes.CoInitialize()
    except OSError:
        pass


def _volume_iface(device=None):
    from pycaw.pycaw import AudioUtilities
    dev = device or AudioUtilities.GetSpeakers()
    vol = getattr(dev, "EndpointVolume", None)
    if vol is None:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        vol = cast(dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
    return dev, vol


def _audio() -> dict:
    _com()
    from pycaw.pycaw import AudioUtilities
    dev, vol = _volume_iface()
    out = {"volume": round(vol.GetMasterVolumeLevelScalar() * 100), "mute": bool(vol.GetMute()),
           "speaker": getattr(dev, "FriendlyName", "") or "", "mic": ""}
    try:
        mic = AudioUtilities.GetMicrophone()
        out["mic"] = getattr(AudioUtilities.CreateDevice(mic), "FriendlyName", "") if mic else ""
    except Exception:  # noqa: BLE001 — no microphone
        pass
    return out


# ---- Bluetooth: registry + CfgMgr32 (PowerShell needs 50 s for the same answer)

class _Guid(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]


class _PropKey(ctypes.Structure):
    _fields_ = [("fmtid", _Guid), ("pid", wintypes.ULONG)]


def _key(a, b, c, d: bytes, pid: int) -> _PropKey:
    return _PropKey(_Guid(a, b, c, (ctypes.c_ubyte * 8)(*d)), pid)


_K_BATTERY = _key(0x104EA319, 0x6EE2, 0x4701, bytes([0xBD, 0x47, 0x8D, 0xDB, 0xF4, 0x25, 0xBB, 0xE5]), 2)
_K_CONNECTED = _key(0x83DA6326, 0x97A6, 0x4088, bytes([0x94, 0x53, 0xA1, 0x92, 0x3F, 0x57, 0x3B, 0x29]), 15)


def _devnode_byte(instance_id: str, key: _PropKey) -> int | None:
    cfg = ctypes.windll.cfgmgr32
    node = wintypes.DWORD()
    if cfg.CM_Locate_DevNodeW(ctypes.byref(node), instance_id, 0) != 0:
        return None
    ptype, size, buf = wintypes.ULONG(), wintypes.ULONG(16), (ctypes.c_ubyte * 16)()
    if cfg.CM_Get_DevNode_PropertyW(node, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0) != 0:
        return None
    return buf[0] if size.value else None


def _subkeys(root, path: str) -> list[str]:
    import winreg
    try:
        with winreg.OpenKey(root, path) as k:
            return [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
    except OSError:
        return []


def _bluetooth() -> list[dict]:
    import winreg
    hklm, base = winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
    enum = r"SYSTEM\CurrentControlSet\Enum"
    instances = [f"{bus}\\{dev}\\{inst}" for bus in ("BTHENUM", "BTHLE", "BTHLEDevice")
                 for dev in _subkeys(hklm, f"{enum}\\{bus}") for inst in _subkeys(hklm, f"{enum}\\{bus}\\{dev}")]
    out = []
    for mac in _subkeys(hklm, base):
        try:
            with winreg.OpenKey(hklm, f"{base}\\{mac}") as k:
                name = winreg.QueryValueEx(k, "Name")[0]
        except OSError:
            continue
        if isinstance(name, bytes):
            name = name.split(b"\0")[0].decode("utf-8", "replace")
        battery, connected = None, False
        for inst in (i for i in instances if mac.upper() in i.upper()):
            b = _devnode_byte(inst, _K_BATTERY)
            if b is not None and 0 < b <= 100:
                battery = b
            if _devnode_byte(inst, _K_CONNECTED):
                connected = True
        out.append({"name": str(name).strip(), "connected": connected, "battery": battery if connected else None})
    out.sort(key=lambda d: (not d["connected"], d["name"].lower()))
    return out[:8]


def _tv_ip() -> str:
    f = BASE / "prime" / "config" / "devices.yaml"
    m = re.search(r"tv_samsung:.*?\bip:\s*\"([\d.]+)\"", f.read_text(encoding="utf-8"), re.S) if f.exists() else None
    return m.group(1) if m else ""


def _tv() -> dict:
    ip = _tv_ip()
    if not ip:
        return {"configured": False}
    try:
        d = _http_json(f"http://{ip}:8001/api/v2/", timeout=2.5).get("device", {})
        return {"configured": True, "online": True, "power": d.get("PowerState", "on"), "model": d.get("modelName", ""), "ip": ip}
    except Exception:  # noqa: BLE001 — off, or not on this network
        return {"configured": True, "online": False, "power": "off", "model": "", "ip": ip}


def _lan() -> list[dict]:
    tv, me, out = _tv_ip(), _ip(), []
    net = me.rsplit(".", 1)[0] + "."
    for ip, mac in re.findall(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f]{2}(?:-[0-9a-f]{2}){5})", _run(["arp", "-a"], 6), re.I):
        if not ip.startswith(net) or ip.endswith(".255") or mac.lower().startswith(("ff-ff", "01-00")):
            continue
        name = "Телевизор Samsung" if ip == tv else "Роутер" if ip == net + "1" else "Устройство"
        if ip not in [d["ip"] for d in out]:
            out.append({"ip": ip, "name": name})
    out.insert(0, {"ip": me, "name": "Этот ноутбук"})
    return out[:10]


_WMO = {0: ("ясно", "sun"), 1: ("почти ясно", "sun"), 2: ("облачно", "cloud"), 3: ("пасмурно", "cloud"), 45: ("туман", "fog"), 48: ("туман", "fog"),
        51: ("морось", "rain"), 53: ("морось", "rain"), 55: ("морось", "rain"), 61: ("дождь", "rain"), 63: ("дождь", "rain"), 65: ("ливень", "rain"),
        71: ("снег", "snow"), 73: ("снег", "snow"), 75: ("снегопад", "snow"), 80: ("ливень", "rain"), 81: ("ливень", "rain"), 82: ("ливень", "rain"),
        95: ("гроза", "storm"), 96: ("гроза", "storm"), 99: ("гроза", "storm")}


def _weather() -> dict:
    import core
    city = core.setting("weather", "city", "Tashkent")
    q = urllib.parse.urlencode({"name": city, "count": 1, "language": "ru"})
    res = (_http_json("https://geocoding-api.open-meteo.com/v1/search?" + q, timeout=8).get("results") or [None])[0]
    if not res:
        return {"city": city, "error": "город не найден"}
    q = urllib.parse.urlencode({"latitude": res["latitude"], "longitude": res["longitude"], "timezone": "auto", "forecast_days": 4,
                                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"})
    d = _http_json("https://api.open-meteo.com/v1/forecast?" + q, timeout=8)
    c, day = d["current"], d["daily"]
    text, icon = _WMO.get(c["weather_code"], ("", "cloud"))
    return {"city": res["name"], "temp": round(c["temperature_2m"]), "text": text, "icon": icon, "wind": round(c["wind_speed_10m"]),
            "hum": c["relative_humidity_2m"], "rain": (day.get("precipitation_probability_max") or [None])[0],
            "days": [{"date": day["time"][i], "max": round(day["temperature_2m_max"][i]), "min": round(day["temperature_2m_min"][i]),
                      "icon": _WMO.get(day["weather_code"][i], ("", "cloud"))[1]} for i in range(len(day["time"]))]}


PROTECTED = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
             "dwm.exe", "explorer.exe", "fontdrvhost.exe", "sihost.exe", "memory compression", "memcompression", "msmpeng.exe",
             "system idle process", "audiodg.exe", "lsaiso.exe", "conhost.exe", "taskhostw.exe", "ctfmon.exe", "spoolsv.exe"}


def _own_pids() -> set[int]:
    me, own = psutil.Process(), {os.getpid()}
    for p in [*me.parents(), *me.children(recursive=True)]:
        own.add(p.pid)
    return own


def _top() -> list[dict]:
    """Programs by memory, with CPU since the previous look. One row per program name."""
    rows: dict[str, dict] = {}
    for p in procs.snapshot():
        if p["pid"] in (0, 4) or not p["name"]:
            continue
        r = rows.setdefault(p["name"], {"name": p["name"], "cpu": 0.0, "mem": 0.0, "pid": p["pid"], "count": 0, "big": 0.0})
        r["cpu"] += p["cpu"]
        r["mem"] += p["mem"]
        r["count"] += 1
        if p["mem"] > r["big"]:
            r["big"], r["pid"] = p["mem"], p["pid"]
    out = sorted(rows.values(), key=lambda r: r["cpu"] * 40 + r["mem"], reverse=True)[:8]
    return [{"name": r["name"], "cpu": round(r["cpu"], 1), "mem": round(r["mem"]), "pid": r["pid"], "count": r["count"],
             "safe": r["name"].lower() not in PROTECTED and not r["name"].lower().startswith("python")} for r in out]


SERVICES = [("Audiosrv", "Звук Windows"), ("WlanSvc", "Wi-Fi"), ("bthserv", "Bluetooth"), ("WinDefend", "Защитник"),
            ("wuauserv", "Обновления"), ("Dnscache", "DNS"), ("WSearch", "Поиск Windows"), ("Spooler", "Печать")]


def _port(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def _services() -> list[dict]:
    out = [{"name": "Джарвис", "on": True, "own": True}, {"name": "Prime", "on": _port(8765), "own": True},
           {"name": "Ollama", "on": _port(11434), "own": True}]
    for sid, title in SERVICES:
        try:
            out.append({"name": title, "on": psutil.win_service_get(sid).status() == "running", "own": False})
        except Exception:  # noqa: BLE001 — not on this Windows
            continue
    return out


_SECRET = re.compile(r"(bot)?\d{8,}:[\w-]{30,}|(?:gsk_|AIza|sk-)[\w-]{16,}")


def _logs() -> list[str]:
    f = BASE / "data" / "assistant.log"
    try:
        with f.open("rb") as h:
            h.seek(0, 2)
            h.seek(max(0, h.tell() - 6000))
            lines = h.read().decode("utf-8", "replace").splitlines()[1:]
    except OSError:
        return []
    return [_SECRET.sub("***", re.sub(r"^\S+ (\S+?),\d+ ", r"\1 ", ln))[:150] for ln in lines if ln.strip()][-16:]


def _prime() -> dict:
    try:
        return {"on": True, **_http_json(PRIME + "/api/status", timeout=3)}
    except Exception:  # noqa: BLE001
        return {"on": False}


def _cards() -> dict:
    try:
        return _http_json(PRIME + "/api/cards", timeout=3)
    except Exception:  # noqa: BLE001
        return {"off": True, "total": 0, "due": 0, "card": None}


def _bots() -> dict:
    import connections
    out: dict = {"telegram": {}, "whatsapp": {}, "secrets": {}}
    try:
        import remote_bot
        st = remote_bot.status()
        out["telegram"] = {"has_token": st["has_token"], "running": st["running"], "error": str(st["error"] or "")[:90],
                           "username": st["username"] or "", "owner": bool(st["owner_id"])}
    except Exception:  # noqa: BLE001
        pass
    try:
        import sys
        wa = sys.modules.get("jarvis_plugin_whatsapp")
        if wa:
            on = wa.enabled()
            out["whatsapp"] = {"enabled": on, "state": wa.status().get("state", "") if on else "off"}
    except Exception:  # noqa: BLE001
        pass
    for name, title in (("groq:api_key", "Groq"), ("gemini:api_key", "Gemini"), ("telegram_bot:token", "Telegram")):
        out["secrets"][title] = bool(connections.get_secret(name))
    return out


def _activity() -> dict:
    import activity
    midnight = dt.datetime.combine(dt.date.today(), dt.time.min)
    rows = activity.minutes_by_app(midnight, top=6)
    return {"on": activity.enabled(), "total": round(sum(m for _, m in rows)),
            "apps": [{"name": a.replace(".exe", ""), "min": round(m)} for a, m in rows]}


def _learning() -> dict:
    from learning import evaluation
    return evaluation.metrics()


def _index() -> dict:
    import pc_index
    d = pc_index.info()
    return {"built": d.get("built", False), "files": d.get("files", 0), "at": d.get("built_at", ""), "running": pc_index.running(),
            "projects": [{"name": Path(p).name, "path": p} for p in d.get("projects", [])][:12], "projects_n": len(d.get("projects", []))}


def _programs() -> list[dict]:
    import programs
    return programs.list_programs(60)


def snapshot() -> dict:
    import cloud
    import core
    return {
        "now": dt.datetime.now().isoformat(timespec="seconds"),
        "sys": _system(), "net": _net_rate(), "battery": _battery(),
        "gpu": cached("gpu", 4, _gpu), "ping": cached("ping", 8, _ping), "wifi": cached("wifi", 20, _wifi),
        "disks": cached("disks", 30, _disks), "screens": cached("screens", 30, _screens),
        "brightness": cached("brightness", 600, _brightness), "audio": cached("audio", 4, _audio),
        "bt": cached("bt", 20, _bluetooth), "tv": cached("tv", 6, _tv), "lan": cached("lan", 30, _lan),
        "weather": cached("weather", 900, _weather), "top": cached("top", 4, _top), "services": cached("services", 60, _services),
        "logs": cached("logs", 4, _logs), "programs": cached("programs", 10, _programs), "prime": cached("prime", 15, _prime),
        "cards": cached("cards", 15, _cards), "bots": cached("bots", 20, _bots), "activity": cached("activity", 20, _activity),
        "index": cached("index", 20, _index), "learning": cached("learning", 60, _learning), "cloud": cloud.status(), "skills": len(core.SKILLS),
    }


# ------------------------------------------------------------------------------------------------ actions

def _prime_post(path: str, body: dict, timeout: float = 8) -> dict:
    try:
        return _http_json(PRIME + path, body, timeout)
    except urllib.error.HTTPError as e:
        raise ValueError("Prime не принял запрос") from e
    except OSError as e:
        raise ValueError("Prime не запущен") from e


def _tv_action(what: str) -> str:
    r = _prime_post("/api/tv", {"what": what}, 45)
    invalidate("tv")
    if not r.get("ok"):
        raise ValueError(r.get("reply") or "телевизор не ответил")
    return r.get("reply") or "Готово."


def _goals(change) -> None:
    """Changes goals.json under the same lock the voice skills use."""
    import sys

    import core
    with sys.modules["jarvis_plugin_goals"]._lock:
        goals = core.load_json(core.DATA / "goals.json", [])
        core.save_json(core.DATA / "goals.json", change(goals))


def _goal_add(title: str, per_day: int | None) -> str:
    title = title.strip()[:120]
    if not title:
        raise ValueError("напишите цель")
    _goals(lambda gs: [*gs, {"id": uuid.uuid4().hex[:8], "title": title, "per_day": per_day, "per_week": None,
                             "created": dt.date.today().isoformat(), "log": {}}])
    return "Цель добавлена."


def _goal_mark(gid: str, day: str, value: int | None) -> str:
    """value None = one more step; a number = set that day to it (0 clears the mark)."""
    if dt.date.fromisoformat(day) > dt.date.today():
        raise ValueError("этот день ещё не наступил")

    def change(gs):
        for g in gs:
            if g["id"] == gid:
                log = g.setdefault("log", {})
                log[day] = int(log.get(day, 0)) + 1 if value is None else max(0, min(9999, value))
                if not log[day]:
                    log.pop(day)
        return gs
    _goals(change)
    return "Отмечено."


def _project_open(path: str) -> str:
    import pc_index
    if path not in pc_index.info().get("projects", []):
        raise ValueError("такого проекта нет в списке")
    os.startfile(path)
    return f"Открываю {Path(path).name}."


def _note_find(query: str) -> list[str]:
    import sys
    notes = sys.modules["jarvis_plugin_notes"].all_notes()
    words = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
    texts = [str(n.get("text", n) if isinstance(n, dict) else n) for n in notes]
    return [t[:200] for t in texts if words and all(w[:5] in t.lower() for w in words)][:6]


def _kill(pid: int, name: str) -> str:
    if name.lower() in PROTECTED or name.lower().startswith("python"):
        raise ValueError("это системный процесс, его закрывать нельзя")
    if pid in _own_pids():
        raise ValueError("это сам Джарвис")
    p = psutil.Process(pid)
    if p.name() != name:
        raise ValueError("процесс уже другой, обновите список")
    p.terminate()
    invalidate("top", "programs")
    return f"Завершил {name}."


def _set_volume(level: int) -> str:
    _com()
    _, vol = _volume_iface()
    vol.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
    if level > 0:
        vol.SetMute(0, None)
    invalidate("audio")
    return f"Громкость {max(0, min(100, level))}%."


def _toggle_mute() -> str:
    _com()
    _, vol = _volume_iface()
    muted = not vol.GetMute()
    vol.SetMute(1 if muted else 0, None)
    invalidate("audio")
    return "Звук выключен." if muted else "Звук включён."


def _set_brightness(level: int) -> str:
    level = max(5, min(100, level))
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"],
                   capture_output=True, timeout=20, creationflags=NO_WINDOW)
    with _LOCK:
        _CACHE.setdefault("brightness", {"value": None, "at": 0.0, "busy": False, "error": ""}).update(value=level, at=time.time())
    return f"Яркость {level}%."


SETTINGS_PAGES = {"display": "ms-settings:display", "sound": "ms-settings:sound", "bluetooth": "ms-settings:bluetooth", "power": "ms-settings:powersleep",
                  "wifi": "ms-settings:network-wifi", "storage": "ms-settings:storagesense", "taskmgr": "taskmgr.exe", "phone": "ms-settings:mobile-devices"}


def _find(query: str) -> list[dict]:
    import pc_index
    return [{"name": Path(p).name, "dir": str(Path(p).parent), "path": p} for p in pc_index.search(query, 8) if Path(p).exists()]


def _reveal(path: str) -> str:
    import pc_index
    p = Path(path)
    if not p.exists() or str(p) not in pc_index.search(p.stem, 200):     # only a file the index itself returned
        raise ValueError("файла нет в индексе")
    subprocess.Popen(["explorer", "/select,", str(p)])
    return f"Показываю {p.name}."


def _about_numbers() -> dict:
    """Real numbers for the self-presentation. Each one is optional: a missing part shows 0, never an error."""
    import core
    n = {"skills": len(getattr(core, "SKILLS", []) or []), "tools": 0, "commands": 0, "lessons": 0, "learned": 0, "tests": 0}
    try:
        import tools
        n["tools"] = len(tools.TOOLS)
    except Exception:  # noqa: BLE001
        pass
    try:
        with core.HISTORY_FILE.open(encoding="utf-8") as f:
            n["commands"] = sum(1 for line in f if line.strip())
    except OSError:
        pass
    try:
        from learning import autolearn, store
        n["lessons"] = len(store.lessons(10000))
        n["learned"] = len(autolearn.aliases(10000))
    except Exception:  # noqa: BLE001
        pass
    n["tests"] = len(list((Path(__file__).resolve().parent / "prime" / "tests").glob("test_stage*.py")))
    return n


def _ru(n: int, one: str, few: str, many: str) -> str:
    """Russian number agreement: 1 навык, 2 навыка, 5 навыков, 21 навык."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def about_deck(lang: str = "ru") -> list[dict]:
    """Jarvis presents himself: what he is, why, what he can do, how he understands, learns and keeps data safe."""
    n = _about_numbers()
    s, t, c, le, ln, ts = n["skills"], n["tools"], n["commands"], n["lessons"], n["learned"], n["tests"]
    if lang == "ja":
        return [
            {"title": "ジャービス", "big": "パーソナル音声アシスタント",
             "points": ["Windows 11", "ロシア語・英語・日本語", "音声とテキスト"],
             "say": "皆さん、こんにちは。私はジャービスです。Windows用のパーソナル音声アシスタントです。"
                    "声でパソコンを操作し、毎日の作業をお手伝いします。これから自己紹介をします。"},
            {"title": "なぜ必要か", "big": "面倒な作業を減らす",
             "points": ["クリックの代わりに一言", "予定を忘れない", "作業中も手が空く"],
             "say": "私たちは毎日、小さな作業に多くの時間を使っています。アプリを開く、ファイルを探す、メッセージを確認する、予定を思い出す。"
                    "ジャービスなら、一言話すだけでこれらを代わりに行います。"},
            {"title": "できること", "big": f"スキル {s} 個",
             "points": ["アプリ・音量・明るさ・ファイル", "タスク・目標・リマインダー", "サムスンのテレビ", "Telegram・WhatsApp・メール・カレンダー"],
             "say": "アプリの起動と終了、音量と明るさの調整、ファイルの検索ができます。タスクや目標、リマインダーを管理し、"
                    "サムスンのテレビを操作し、Telegram、WhatsApp、メール、カレンダーを読みます。"},
            {"title": "理解のしくみ", "big": "3つの段階",
             "points": ["音声認識：Whisper と Groq", "高速スキル：すぐに実行", f"AIの頭脳：ツール {t} 個"],
             "say": "まず音声を文字に変換します。次に、高速なスキルの中から一致するものを探し、すぐに実行します。"
                    "複雑な文の場合は、言語モデルが意味を理解し、必要なツールを自分で選びます。複数の操作も一度に行えます。"},
            {"title": "記憶と学習", "big": f"学んだ言い方 {ln} 件",
             "points": ["4つの記憶の層", "文書の中を検索", "自分の間違いから学ぶ"],
             "say": "持ち主について覚えた事実を記憶し、文書の中から答えを探します。間違えたときは自分で記録します。"
                    "言い直してもらえれば、その意味を覚えます。毎晩、間違いを振り返り、教訓にします。"},
            {"title": "安全性", "big": "データはあなたの手元に",
             "points": ["個人データはこのパソコンだけ", "鍵は Windows の安全な保管庫", "危険な操作は確認してから", "持ち主の声を認識"],
             "say": "個人データはこのパソコンにだけ保存されます。鍵は Windows の安全な保管庫にあります。"
                    "電源を切る、削除するなどの危険な操作は、必ず確認してから実行します。"},
            {"title": "しくみ", "big": "Python",
             "points": ["サーバー：aiohttp", "画面：WebView", "音声：Piper と Microsoft Edge", "頭脳：Groq、Gemini、Ollama"],
             "say": "私は Python で作られています。サーバーは aiohttp、画面は WebView です。音声合成には Piper と Microsoft Edge を使い、"
                    "難しい質問はクラウドの Groq や Gemini、またはローカルの Ollama が処理します。"},
            {"title": "数字で見る", "big": f"{c} 回のコマンド",
             "points": [f"スキル {s} 個", f"ツール {t} 個", f"教訓 {le} 件", f"テスト {ts} 組"],
             "say": f"現在、スキルは{s}個、ツールは{t}個あります。これまでに{c}回のコマンドを実行しました。"
                    f"プロジェクトは{ts}組の自動テストで確認されています。"},
            {"title": "試してみてください", "big": "「ジャービス」と呼んでください",
             "points": ["ジャービス、天気は？", "ジャービス、テレビをつけて", "ジャービス、事実を覚えて"],
             "say": "ぜひ試してみてください。ジャービス、天気は？ ジャービス、テレビをつけて。と話しかけるだけです。"},
            {"title": "ありがとうございました", "big": "ご清聴ありがとうございました",
             "say": "ご清聴ありがとうございました。ご質問をお待ちしています。"},
        ]
    if lang == "en":
        return [
            {"title": "Jarvis", "big": "A personal voice assistant",
             "points": ["Windows 11", "Russian, English, Japanese", "Voice and text"],
             "say": "Hello everyone. My name is Jarvis. I am a personal voice assistant for Windows. "
                    "I listen to speech, control the computer and help with everyday tasks. Let me introduce myself."},
            {"title": "Why I exist", "big": "Less routine",
             "points": ["One phrase instead of ten clicks", "Nothing is forgotten", "Your hands stay free"],
             "say": "Every day people lose time on small actions: opening an app, finding a file, checking messages, "
                    "remembering a task. I take this routine over. One phrase is enough."},
            {"title": "What I can do", "big": f"{s} skills",
             "points": ["Apps, volume, brightness, files", "Tasks, goals, reminders", "Samsung TV", "Telegram, WhatsApp, email, calendar"],
             "say": "I open and close programs, change volume and brightness, and find files. I keep tasks, goals and reminders, "
                    "control a Samsung TV, and read Telegram, WhatsApp, email and the calendar."},
            {"title": "How I understand", "big": "Three levels",
             "points": ["Speech recognition: Whisper and Groq", "Fast skills: instant", f"The brain: {t} tools"],
             "say": "First I turn speech into text. Then I look for an exact match among fast skills, so a command runs instantly. "
                    "A complex phrase goes to a language model, which chooses the right tools by itself, even several at once."},
            {"title": "Memory and learning", "big": f"{ln} learned phrases",
             "points": ["Four layers of memory", "Search in your documents", "I learn from my mistakes"],
             "say": "I remember facts about my owner and search for answers in their documents. When I make a mistake, I note it myself. "
                    "If you say the same thing in other words, I remember what you meant. Every night I turn mistakes into lessons."},
            {"title": "Security", "big": "Your data stays with you",
             "points": ["Personal data only on this PC", "Keys in the Windows vault", "Risky actions only after a yes", "I know my owner's voice"],
             "say": "Personal data is stored only on this computer. Keys are kept in the Windows credential vault. "
                    "Risky actions, like shutting down or deleting, happen only after you confirm them."},
            {"title": "How I am built", "big": "Python",
             "points": ["Server: aiohttp", "Window: WebView", "Voice: Piper and Microsoft Edge", "Brain: Groq, Gemini, Ollama"],
             "say": "I am written in Python. The server is aiohttp and the window is a WebView. Piper and Microsoft Edge give me a voice. "
                    "Hard requests go to Groq or Gemini in the cloud, or to a local model through Ollama."},
            {"title": "In numbers", "big": f"{c} commands",
             "points": [f"{s} skills", f"{t} tools", f"{le} lessons", f"{ts} test suites"],
             "say": f"Today I have {s} skills and {t} tools. I have carried out {c} commands. "
                    f"The project is checked by {ts} automatic test suites."},
            {"title": "Try it", "big": "Say «Jarvis»",
             "points": ["Jarvis, what is the weather?", "Jarvis, turn on the TV", "Jarvis, remember a fact"],
             "say": "Try it yourself. Say: Jarvis, what is the weather. Or: Jarvis, turn on the TV."},
            {"title": "Thank you", "big": "Thank you for your attention",
             "say": "Thank you for your attention. I am ready for your questions."},
        ]
    return [
        {"title": "Джарвис", "big": "Личный голосовой ассистент",
         "points": ["Windows 11", "Русский, английский, японский", "Голос и текст"],
         "say": "Всем здравствуйте. Меня зовут Джарвис. Я личный голосовой ассистент для Windows: слушаю речь, "
                "управляю компьютером и помогаю с делами. Сейчас я расскажу о себе."},
        {"title": "Зачем я нужен", "big": "Меньше рутины",
         "points": ["Одна фраза вместо десятка кликов", "Ничего не забывается", "Руки остаются свободными"],
         "say": "Каждый день человек тратит время на мелкие действия: открыть программу, найти файл, проверить сообщения, "
                "вспомнить о деле. Я беру эту рутину на себя. Достаточно сказать одну фразу."},
        {"title": "Что я умею", "big": f"{s} {_ru(s, 'навык', 'навыка', 'навыков')}",
         "points": ["Программы, громкость, яркость, файлы", "Дела, цели, напоминания", "Телевизор Samsung", "Telegram, WhatsApp, почта, календарь"],
         "say": "Я открываю и закрываю программы, меняю громкость и яркость, ищу файлы. Веду дела, цели и напоминания, "
                "управляю телевизором Samsung, читаю Telegram, WhatsApp, почту и календарь."},
        {"title": "Как я понимаю", "big": "Три уровня",
         "points": ["Распознавание речи: Whisper и Groq", "Быстрые навыки: мгновенно", f"Мозг: {t} {_ru(t, 'инструмент', 'инструмента', 'инструментов')}"],
         "say": "Сначала я превращаю речь в текст. Затем ищу точное совпадение среди быстрых навыков, и команда выполняется мгновенно. "
                "Сложную фразу разбирает языковая модель: она сама выбирает нужные инструменты, даже несколько за раз."},
        {"title": "Память и обучение", "big": f"{ln} {_ru(ln, 'выученная фраза', 'выученные фразы', 'выученных фраз')}",
         "points": ["Четыре уровня памяти", "Поиск по вашим документам", "Учусь на своих ошибках"],
         "say": "Я помню факты о владельце и ищу ответы в его документах. Когда я ошибаюсь, я сам записываю ошибку. "
                "Если сказать то же самое другими словами, я запомню, что имелось в виду. Каждую ночь я превращаю ошибки в уроки."},
        {"title": "Безопасность", "big": "Данные остаются у вас",
         "points": ["Личные данные только на этом компьютере", "Ключи в хранилище Windows", "Опасное только после «да»", "Узнаю голос владельца"],
         "say": "Личные данные хранятся только на этом компьютере. Ключи лежат в защищённом хранилище Windows. "
                "Опасные действия, например выключение или удаление, я выполняю только после вашего подтверждения."},
        {"title": "Как я устроен", "big": "Python",
         "points": ["Сервер: aiohttp", "Окно: WebView", "Голос: Piper и Microsoft Edge", "Мозг: Groq, Gemini, Ollama"],
         "say": "Я написан на Python. Сервер работает на aiohttp, окно на WebView. Голос мне дают Piper без интернета и Microsoft Edge. "
                "Сложные запросы разбирает облачная модель через Groq или Gemini, либо локальная через Ollama."},
        {"title": "В цифрах", "big": f"{c} {_ru(c, 'команда', 'команды', 'команд')}",
         "points": [f"{s} {_ru(s, 'навык', 'навыка', 'навыков')}", f"{t} {_ru(t, 'инструмент', 'инструмента', 'инструментов')}",
                    f"{le} {_ru(le, 'урок', 'урока', 'уроков')}", f"{ts} {_ru(ts, 'набор', 'набора', 'наборов')} тестов"],
         "say": f"Сейчас у меня {s} {_ru(s, 'навык', 'навыка', 'навыков')} и {t} {_ru(t, 'инструмент', 'инструмента', 'инструментов')}. "
                f"Я выполнил {c} {_ru(c, 'команду', 'команды', 'команд')}. "
                f"Проект проверяют {ts} {_ru(ts, 'набор', 'набора', 'наборов')} автоматических тестов."},
        {"title": "Попробуйте", "big": "Скажите «Джарвис»",
         "points": ["Джарвис, какая погода?", "Джарвис, включи телевизор", "Джарвис, запомни факт"],
         "say": "Попробуйте сами. Скажите: Джарвис, какая погода. Или: Джарвис, включи телевизор."},
        {"title": "Спасибо", "big": "Спасибо за внимание",
         "say": "Спасибо за внимание. Я готов ответить на ваши вопросы."},
    ]


def deck(lang: str = "ru") -> list[dict]:
    """Slides of the monthly report, built from the real tasks, goals, activity and history of this month."""
    import activity
    import core
    month = dt.date.today().replace(day=1)
    tasks = core.load_json(core.DATA / "tasks.json", [])
    done = [t for t in tasks if t.get("done") and str(t.get("done_at", ""))[:10] >= month.isoformat()]
    opened = [t for t in tasks if not t.get("done")]
    goals = (core.load_json(core.DATA / "goals.json", {}) or {})
    goals = goals.get("goals", goals) if isinstance(goals, dict) else goals
    steps = sum(v for g in goals or [] for d, v in (g.get("log") or {}).items() if d >= month.isoformat())
    hist = [h for h in core.read_history(20000) if h["time"][:10] >= month.isoformat() and h.get("user")
            and h["user"] != "статус телевизора"]
    apps = activity.minutes_by_app(dt.datetime.combine(month, dt.time.min), top=3)
    hours = round(sum(m for _, m in apps) / 60, 1)
    tops = ", ".join(a.replace(".exe", "") for a, _ in apps)
    names = {"ru": ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"],
             "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]}
    m, y = month.month, month.year
    if lang == "ja":
        return [{"title": "月次報告", "big": f"{y}年{m}月", "say": "皆さん、こんにちは。私はジャービスです。月次報告を始めます。"},
                {"title": "タスク", "big": str(len(done)), "say": f"今月、タスクを{len(done)}件完了しました。残りは{len(opened)}件です。"},
                {"title": "目標", "big": str(steps), "say": f"目標は{len(goals or [])}件あり、今月は{steps}回進めました。"},
                {"title": "アシスタント", "big": str(len(hist)), "say": f"音声とテキストの指示は{len(hist)}件でした。"},
                {"title": "終わり", "big": "ありがとうございました", "say": "ご清聴ありがとうございました。質問をお受けします。"}]
    if lang == "en":
        return [{"title": "Monthly report", "big": f"{names['en'][m - 1]} {y}", "say": "Good day. I am Jarvis. Let's begin the report."},
                {"title": "Tasks", "big": str(len(done)), "say": f"Tasks closed this month: {len(done)}. Still open: {len(opened)}."},
                {"title": "Goals", "big": str(steps), "say": f"Goals: {len(goals or [])}. Steps made this month: {steps}."},
                {"title": "Assistant", "big": str(len(hist)), "say": f"Requests to Jarvis this month: {len(hist)}."},
                {"title": "Time", "big": f"{hours} h", "say": f"Recorded time in the top programs: {hours} hours. {tops}".strip()},
                {"title": "The end", "big": "Thank you", "say": "Thank you. I am ready for questions."}]
    return [{"title": "Отчёт за месяц", "big": f"{names['ru'][m - 1]} {y}", "say": "Всем здравствуйте. Я — Джарвис. Начинаем отчёт."},
            {"title": "Дела", "big": str(len(done)), "say": f"За месяц закрыто дел: {len(done)}. Открыто: {len(opened)}."},
            {"title": "Цели", "big": str(steps), "say": f"Целей: {len(goals or [])}. Шагов за месяц: {steps}."},
            {"title": "Команды", "big": str(len(hist)), "say": f"Запросов к Джарвису за месяц: {len(hist)}."},
            {"title": "Время", "big": f"{hours} ч", "say": f"В главных программах записано {hours} ч. {tops}".strip()},
            {"title": "Конец", "big": "Спасибо", "say": "Спасибо. Готов ответить на вопросы."}]


def action(kind: str, body: dict) -> dict:
    """Run one widget action. Raises ValueError with a readable text when it is not allowed."""
    import programs
    if kind == "tv":
        return {"reply": _tv_action(str(body.get("what", "")))}
    if kind == "volume":
        return {"reply": _set_volume(int(body.get("level", 0)))}
    if kind == "mute":
        return {"reply": _toggle_mute()}
    if kind == "brightness":
        return {"reply": _set_brightness(int(body.get("level", 50)))}
    if kind == "open":
        invalidate("programs")
        return {"reply": programs.open_program(str(body.get("name", "")))}
    if kind == "close":
        invalidate("programs", "top")
        return {"reply": programs.close_program(str(body.get("name", "")))}
    if kind == "kill":
        return {"reply": _kill(int(body.get("pid", 0)), str(body.get("name", "")))}
    if kind == "find":
        return {"items": _find(str(body.get("query", ""))[:120])}
    if kind == "reveal":
        return {"reply": _reveal(str(body.get("path", "")))}
    if kind == "goal_add":
        n = int(body.get("per_day") or 0)
        return {"reply": _goal_add(str(body.get("title", "")), n if 0 < n < 10000 else None)}
    if kind == "goal_mark":
        val = body.get("value")
        return {"reply": _goal_mark(str(body.get("id", "")), str(body.get("day") or dt.date.today().isoformat()),
                                    None if val is None else int(val))}
    if kind == "goal_delete":
        _goals(lambda gs: [g for g in gs if g["id"] != body.get("id")])
        return {"reply": "Цель удалена."}
    if kind == "focus":
        import pcx
        minutes = int(body.get("minutes", 0))
        return {"reply": pcx.focus_start(max(5, min(180, minutes))) if minutes else pcx.focus_stop()}
    if kind == "project":
        return {"reply": _project_open(str(body.get("path", "")))}
    if kind == "note_find":
        return {"notes": _note_find(str(body.get("query", ""))[:120])}
    if kind == "settings":
        page = SETTINGS_PAGES.get(str(body.get("page", "")))
        if not page:
            raise ValueError("нет такой страницы настроек")
        os.startfile(page)
        return {"reply": "Открываю настройки Windows."}
    if kind == "activity":
        import activity
        on = bool(body.get("on"))
        activity.set_enabled(on)
        activity.start() if on else activity.stop()
        invalidate("activity")
        return {"reply": "Учёт времени включён." if on else "Учёт времени выключен."}
    if kind == "card_review":
        r = _prime_post("/api/cards/review", {"id": int(body.get("id", 0)), "quality": int(body.get("quality", 0))})
    elif kind == "card_add":
        r = _prime_post("/api/cards", {"front": str(body.get("front", ""))[:200], "back": str(body.get("back", ""))[:300]})
    elif kind == "card_deck":
        r = _prime_post("/api/cards", {"deck": "n2"})
    elif kind == "show":
        from cognition import show as shw
        op = str(body.get("op", ""))
        if op == "start":
            st = shw.start(str(body.get("lang", "ru")), str(body.get("deck", "about")), bool(body.get("auto")))
        elif op == "next":
            st = shw.step(1)
        elif op == "prev":
            st = shw.step(-1)
        elif op == "go":
            st = shw.go(int(body.get("i", 0)))
        elif op == "lang":
            st = shw.switch(str(body.get("lang", "ru")), body.get("deck"))
        elif op == "say":
            shw.say_current(); st = shw.public()
        elif op == "play":
            st = shw.play()
        elif op == "pause":
            st = shw.pause()
        elif op == "stop":
            shw.stop(); st = shw.public()
        elif op == "audio":
            try:
                path = shw.export_audio(str(body.get("lang", "ru")), str(body.get("deck", "about")))
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"Аудиофайл не получился: {e}") from e
            return {"reply": f"Сохранил аудио: {path.name}", "file": path.name, "show": shw.public()}
        else:
            raise ValueError("неизвестное действие презентации")
        return {"reply": "Готово.", "show": st}
    elif kind == "deck":
        lang = str(body.get("lang", "ru"))
        return {"slides": about_deck(lang) if body.get("deck", "report") == "about" else deck(lang)}
    else:
        raise ValueError("неизвестное действие")
    with _LOCK:                                    # the new card state is shown at once
        _CACHE.setdefault("cards", {"value": None, "at": 0.0, "busy": False, "error": ""}).update(value=r, at=time.time())
    return {"cards": r, "reply": r.get("reply", "Готово.")}
