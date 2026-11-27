"""Full analysis of this PC and a safe optimization plan for it.

analyze()  — reads facts only (processor, memory, graphics, disks, battery wear, power plan, startup programs, junk files)
             and returns a score, plain-language problems and a list of steps.
apply(ids) — runs only the steps the owner ticked. Nothing runs by itself.
undo()     — puts back every setting that was changed. Deleted temporary files cannot come back, and the plan says so.

What it never does: no administrator rights, no services, no registry «cleaning», no security settings, no drivers,
no overclocking, no files outside the temporary folder.

Run from a terminal:  python optimizer.py      (report only, changes nothing)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import winreg
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil

BASE = Path(__file__).resolve().parent
UNDO = BASE / "data" / "optimize_undo.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEMP_DAYS = 7
BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
SAVER = "a1841308-3541-4fab-bc81-f71556f20b4a"
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"


# ------------------------------------------------------------------------------------------------ reading

def _run(cmd: list[str], timeout: float = 40, enc: str = "utf-8") -> str:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW).stdout.decode(enc, "replace")
    except (OSError, subprocess.SubprocessError):
        return ""


def _facts() -> dict:
    """One PowerShell call for everything Windows only tells through CIM."""
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='SilentlyContinue';"
              "$c=Get-CimInstance Win32_Processor|Select-Object -First 1; $o=Get-CimInstance Win32_OperatingSystem;"
              "$s=Get-CimInstance Win32_ComputerSystem; $m=@(Get-CimInstance Win32_PhysicalMemory);"
              "$g=@(Get-CimInstance Win32_VideoController|ForEach-Object{[pscustomobject]@{name=$_.Name;driver=$_.DriverVersion;"
              "date=$(if($_.DriverDate){$_.DriverDate.ToString('yyyy-MM-dd')})}});"
              "$d=@(Get-PhysicalDisk|ForEach-Object{[pscustomobject]@{name=$_.FriendlyName;type=\"$($_.MediaType)\";"
              "health=\"$($_.HealthStatus)\";gb=[math]::Round($_.Size/1GB)}});"
              "[pscustomobject]@{cpu=$c.Name;cores=$c.NumberOfCores;threads=$c.NumberOfLogicalProcessors;mhz=$c.MaxClockSpeed;"
              "os=$o.Caption;build=$o.BuildNumber;maker=$s.Manufacturer;model=$s.Model;sticks=$m.Count;"
              "ramtype=($m|Select-Object -First 1).SMBIOSMemoryType;ramspeed=($m|Select-Object -First 1).Speed;gpus=$g;disks=$d}"
              "|ConvertTo-Json -Depth 4 -Compress")
    try:
        return json.loads(_run(["powershell", "-NoProfile", "-Command", script], 90) or "{}")
    except ValueError:
        return {}


def _nvidia() -> dict | None:
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"], 8).strip()
    if not out:
        return None
    p = [x.strip() for x in out.splitlines()[0].split(",")]
    return {"name": p[0], "vram_mb": int(p[1]), "driver": p[2]} if len(p) == 3 and p[1].isdigit() else None


def _battery() -> dict | None:
    b = psutil.sensors_battery()
    if b is None:
        return None
    out = {"pct": round(b.percent), "plugged": bool(b.power_plugged), "wear": None, "cycles": None}
    f = Path(tempfile.gettempdir()) / "jarvis_battery.xml"
    _run(["powercfg", "/batteryreport", "/xml", "/output", str(f)], 25)
    try:
        root = ET.parse(f).getroot()
        val: dict[str, str] = {}
        for e in root.iter():                      # the first number is the battery itself, later ones are daily history
            if e.tag.endswith(("DesignCapacity", "FullChargeCapacity", "CycleCount")) and (e.text or "").strip().isdigit():
                val.setdefault(e.tag.split("}")[-1], e.text.strip())
        design, full = int(val.get("DesignCapacity", 0)), int(val.get("FullChargeCapacity", 0))
        if design and full:
            out["wear"] = max(0, round(100 - full / design * 100))
        out["cycles"] = int(val["CycleCount"]) if val.get("CycleCount", "0") != "0" else None
    except (OSError, ET.ParseError, ValueError):
        pass
    f.unlink(missing_ok=True)
    return out


def _reg(path: str, name: str, root=winreg.HKEY_CURRENT_USER):
    try:
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _reg_set(path: str, name: str, value, kind=winreg.REG_DWORD) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, kind, value)


def _reg_del(path: str, name: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def startup() -> list[dict]:
    """Programs that start with Windows for this user: [{id, name, cmd, on}]. Machine-wide entries need admin: left alone."""
    out = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, cmd, _ = winreg.EnumValue(k, i)
                out.append({"id": "startup:Run:" + name, "name": name, "cmd": str(cmd)})
    except OSError:
        pass
    folder = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    if folder.exists():
        out += [{"id": "startup:StartupFolder:" + f.name, "name": f.stem, "cmd": str(f)} for f in folder.iterdir()
                if f.suffix.lower() in (".lnk", ".exe", ".bat", ".cmd", ".vbs")]
    for x in out:
        _, kind, name = x["id"].split(":", 2)
        flag = _reg(APPROVED + "\\" + kind, name)
        x["on"] = not (isinstance(flag, bytes) and flag and flag[0] % 2 == 1)      # odd first byte = turned off, as in Task Manager
    return [x for x in out if "jarvis" not in x["name"].lower()]


def _old_temp() -> tuple[int, int]:
    """(files, bytes) in the user's temp folder that nobody changed for a week."""
    n = size = 0
    edge, stop = time.time() - TEMP_DAYS * 86400, time.time() + 12
    for root, _dirs, files in os.walk(tempfile.gettempdir()):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            if max(st.st_mtime, st.st_ctime) < edge:
                n, size = n + 1, size + st.st_size
        if time.time() > stop:
            break
    return n, size


def _power_plan() -> str:
    m = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27})", _run(["powercfg", "/getactivescheme"], 10, "cp866"))
    return m.group(1) if m else ""


def _reboot_pending() -> bool:
    for p in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
              r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"):
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, p))
            return True
        except OSError:
            continue
    return False


# ------------------------------------------------------------------------------------------------ judging

def tier(ram_gb: float, threads: int, vram_mb: int) -> str:
    """«weak», «medium» or «strong»: which Jarvis settings this PC can carry."""
    if ram_gb < 7.5 or threads <= 4:
        return "weak"
    return "strong" if ram_gb >= 15 and threads >= 8 and vram_mb >= 4000 else "medium"


_SEEN: dict = {"at": 0.0, "plan": {}}
TIER_NAME = {"weak": "слабый", "medium": "средний", "strong": "мощный"}


def jarvis_settings(t: str, vram_mb: int) -> dict[tuple[str, str], object]:
    """Settings of Jarvis for this class of PC. Speech goes through the cloud first; these are for work on the PC itself."""
    gpu = vram_mb >= 4000
    return {("voice", "whisper_device"): "cuda" if gpu else "cpu",
            ("voice", "whisper_model"): "large-v3-turbo" if gpu else "base" if t == "weak" else "small",
            ("voice", "spot_model"): "tiny",
            ("ui", "hud_lite"): t == "weak",
            ("wake", "name_detection"): t != "weak"}


def analyze() -> dict:
    f, nv, vm = _facts(), _nvidia(), psutil.virtual_memory()
    ram, threads, vram = round(vm.total / 2**30, 1), f.get("threads") or psutil.cpu_count() or 1, nv["vram_mb"] if nv else 0
    disks = f.get("disks") or []
    disks = disks if isinstance(disks, list) else [disks]
    gpus = f.get("gpus") or []
    gpus = gpus if isinstance(gpus, list) else [gpus]
    sysd = os.environ.get("SystemDrive", "C:")
    free = shutil.disk_usage(sysd + "\\").free / 2**30
    t = tier(ram, threads, vram)
    bat, st, (tn, tb), plan_id, reboot = _battery(), startup(), _old_temp(), _power_plan(), _reboot_pending()
    on = [x for x in st if x["on"]]
    ssd = any(d.get("type") == "SSD" for d in disks) or not any(d.get("type") == "HDD" for d in disks)

    probs: list[dict] = []
    add = lambda sev, title, how: probs.append({"sev": sev, "title": title, "how": how})      # noqa: E731
    if ram < 7.5:
        add("bad", f"Мало памяти: {ram} ГБ", "Поставьте ещё модуль памяти, лучше до 16 ГБ. Это даст больше всего.")
    elif vm.percent >= 88:
        add("warn", f"Память занята на {vm.percent:.0f}%", "Закройте лишние программы (виджет «Диспетчер задач») и сократите автозапуск ниже.")
    if f.get("sticks") == 1 and ram < 31:
        add("warn", "Один модуль памяти", "Второй такой же модуль включит двухканальный режим: игры и видеоядро станут быстрее.")
    if not ssd:
        add("bad", "Нет SSD", "Замена жёсткого диска на SSD ускорит всё сильнее любых настроек.")
    if free < 15:
        add("bad" if free < 6 else "warn", f"На {sysd} свободно {free:.0f} ГБ", "Windows нужно 15 ГБ и больше. Очистите временные файлы ниже и корзину.")
    for d in disks:
        if d.get("health") not in ("", "Healthy", None):
            add("bad", f"Диск {d.get('name')}: {d['health']}", "Сделайте копию важных файлов сейчас: диск сообщает о неисправности.")
    if bat and bat["wear"] is not None and bat["wear"] >= 30:
        add("warn", f"Батарея износилась на {bat['wear']}%", "Время без зарядки будет короче. При 40% и больше батарею меняют.")
    if not nv:
        add("info", "Нет видеокарты NVIDIA", "Речь распознаётся в облаке или на процессоре. Для этого достаточно бесплатного ключа Groq.")
    if len(on) >= 8:
        add("warn", f"В автозапуске {len(on)} программ", "Из-за них Windows дольше включается. Отключите ненужные ниже.")
    if reboot:
        add("warn", "Windows ждёт перезагрузки", "Перезагрузите компьютер, чтобы закончить обновления.")
    if int(f.get("build") or 0) and int(f["build"]) < 19045:
        add("warn", "Старая сборка Windows", "Обновите Windows: старые сборки не получают исправлений безопасности.")

    plan: list[dict] = []

    def step(sid, title, why, default, undo=True, group="windows"):
        plan.append({"id": sid, "title": title, "why": why, "default": default, "undo": undo, "group": group})

    import core
    if not core.CONFIG:
        core.load_config()
    diff = {k: v for k, v in jarvis_settings(t, vram).items() if core.setting(*k) != v and not (k == ("ui", "hud_lite") and not v and core.setting(*k) is None)
            and not (k == ("voice", "spot_model") and core.setting(*k) is None)}
    if diff:
        names = {"whisper_device": "где распознавать речь", "whisper_model": "модель речи", "hud_lite": "лёгкая графика", "name_detection": "поиск имени в речи", "spot_model": "модель имени"}
        step("jarvis", "Настроить Джарвиса под этот компьютер", "; ".join(f"{names[k[1]]}: {_say(v)}" for k, v in diff.items()), True, group="jarvis")
    if tb > 50 * 2**20:
        step("temp", f"Удалить старые временные файлы: {tb / 2**30:.1f} ГБ", f"{tn} файлов, которые никто не менял {TEMP_DAYS} дней. Вернуть их нельзя.", True, undo=False)
    if plan_id == SAVER:
        step("power", "Включить сбалансированное питание", "Сейчас включена экономия: процессор работает медленнее.", True)
    if _reg(r"Software\Microsoft\GameBar", "AutoGameModeEnabled") == 0:
        step("gamemode", "Включить игровой режим Windows", "Во время игры Windows меньше отвлекается на фон.", True)
    if _reg(r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled") == 1 and _reg(r"System\GameConfigStore", "GameDVR_Enabled") != 0 \
            and _reg(r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "HistoricalCaptureEnabled") == 1:
        step("gamedvr", "Выключить фоновую запись игр", "Она постоянно пишет видео и занимает видеокарту.", False)
    if t == "weak" and _reg(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency") != 0:
        step("transparency", "Выключить прозрачность окон", "На слабой видеокарте окна открываются быстрее.", True)
    for x in on:
        step(x["id"], f"Убрать из автозапуска: {x['name']}", "Программа останется, но не будет запускаться сама.", False, group="startup")

    score = 100
    score -= 25 if ram < 7.5 else 8 if ram < 15 else 0
    score -= 25 if not ssd else 0
    score -= 12 if threads <= 4 else 4 if threads < 8 else 0
    score -= 15 if free < 6 else 8 if free < 15 else 0
    score -= 8 if vm.percent >= 88 else 0
    score -= 6 if len(on) >= 8 else 2 if len(on) >= 5 else 0
    score -= 6 if bat and (bat["wear"] or 0) >= 30 else 0
    score -= 5 if tb > 2 * 2**30 else 0
    score -= 4 if reboot else 0
    score -= 20 if any(d.get("health") not in ("", "Healthy", None) for d in disks) else 0

    gpu_names = [g.get("name", "") for g in gpus if g.get("name") and "Virtual" not in g["name"]]
    passport = [["Модель", " ".join(x for x in (f.get("maker"), f.get("model")) if x) or "—"],
                ["Windows", f"{(f.get('os') or 'Windows').replace('Майкрософт ', '').replace('Microsoft ', '')} · сборка {f.get('build') or '—'}"],
                ["Процессор", re.sub(r"\s+", " ", re.sub(r"\(R\)|\(TM\)", "", f.get("cpu") or "—")).strip() + f" · потоков {threads}"],
                ["Память", f"{ram} ГБ" + (f" · модулей {f['sticks']}" if f.get("sticks") else "") + (f" · {f['ramspeed']} МГц" if f.get("ramspeed") else "")],
                ["Видео", "; ".join(g + (f" · {vram / 1024:.0f} ГБ" if vram and "NVIDIA" in g else "") for g in gpu_names).replace("(R)", "") or "—"],
                *[["Диск", f"{d.get('name')} · {d.get('type') or '?'} · {d.get('gb')} ГБ · {'исправен' if d.get('health') == 'Healthy' else d.get('health')}"] for d in disks],
                ["Свободно на " + sysd.rstrip(":"), f"{free:.0f} ГБ"],
                ["Батарея", "нет" if not bat else f"{bat['pct']}%" + (f" · износ {bat['wear']}%" if bat["wear"] is not None else "") + (f" · циклов {bat['cycles']}" if bat["cycles"] else "")],
                ["Автозапуск", f"{len(on)} программ"]]
    _SEEN.update(at=time.time(), plan={s["id"]: s["title"] for s in plan})
    return {"score": max(5, score), "tier": t, "tier_name": TIER_NAME[t], "passport": passport, "problems": probs, "plan": plan,
            "can_undo": bool(_load_undo())}


def _say(v) -> str:
    return {True: "да", False: "нет", "cuda": "видеокарта", "cpu": "процессор"}.get(v, str(v)) if isinstance(v, (bool, str)) else str(v)


# ------------------------------------------------------------------------------------------------ doing and undoing

def _load_undo() -> dict:
    try:
        return json.loads(UNDO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _remember(sid: str, value) -> None:
    """Keeps the FIRST value from before any change: applying twice must not lose it."""
    d = _load_undo()
    if sid not in d:
        d[sid] = value
        UNDO.parent.mkdir(parents=True, exist_ok=True)
        UNDO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


REG_STEPS = {"gamemode": (r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1),
             "gamedvr": (r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "HistoricalCaptureEnabled", 0),
             "transparency": (r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 0)}


def _clean_temp() -> str:
    freed = n = 0
    edge, tmp = time.time() - TEMP_DAYS * 86400, Path(tempfile.gettempdir()).resolve()
    if tmp == tmp.parent or tmp in (Path.home().resolve(), Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()):
        raise ValueError("папка временных файлов задана странно, не трогаю")
    for root, dirs, files in os.walk(tmp, topdown=True):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d)) and not os.path.isjunction(os.path.join(root, d))]
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.stat(p, follow_symlinks=False)
                if max(st.st_mtime, st.st_ctime) < edge:
                    os.unlink(p)
                    n, freed = n + 1, freed + st.st_size
            except OSError:                     # in use by a program: leave it
                continue
    return f"освобождено {freed / 2**30:.2f} ГБ, файлов {n}"


def _startup_set(sid: str, on: bool) -> None:
    _, kind, name = sid.split(":", 2)
    _reg_set(APPROVED + "\\" + kind, name, bytes([2 if on else 3]) + bytes(11), winreg.REG_BINARY)


def _apply_one(sid: str) -> str:
    import core
    if sid == "jarvis":
        vm, nv = psutil.virtual_memory(), _nvidia()
        vram = nv["vram_mb"] if nv else 0
        want = jarvis_settings(tier(vm.total / 2**30, psutil.cpu_count() or 1, vram), vram)
        _remember(sid, [[s, k, core.setting(s, k)] for (s, k) in want])
        for (s, k), v in want.items():
            core.save_setting(s, k, v)
        return "настройки Джарвиса подобраны"
    if sid == "temp":
        return _clean_temp()
    if sid == "power":
        _remember(sid, _power_plan())
        _run(["powercfg", "/setactive", BALANCED], 10)
        if _power_plan() != BALANCED:
            raise ValueError("Windows не переключила план питания")
        return "сбалансированное питание включено"
    if sid in REG_STEPS:
        path, name, value = REG_STEPS[sid]
        _remember(sid, _reg(path, name))
        _reg_set(path, name, value)
        return "готово"
    if sid.startswith("startup:") and sid in [x["id"] for x in startup()]:
        _remember(sid, True)
        _startup_set(sid, False)
        return "убрано из автозапуска"
    raise ValueError("неизвестный шаг")


def apply(ids: list[str]) -> list[dict]:
    """Runs the ticked steps. One failed step does not stop the rest."""
    if time.time() - _SEEN["at"] > 1800:                # the plan the owner saw; a full analysis takes half a minute
        analyze()
    allowed, out = dict(_SEEN["plan"]), []
    for sid in ids:
        if sid not in allowed:
            out.append({"id": sid, "title": sid, "ok": False, "message": "этого шага нет в плане"})
            continue
        try:
            out.append({"id": sid, "title": allowed[sid], "ok": True, "message": _apply_one(sid)})
        except Exception as e:  # noqa: BLE001 — told to the owner
            out.append({"id": sid, "title": allowed[sid], "ok": False, "message": str(e) or type(e).__name__})
    return out


def undo() -> list[str]:
    """Puts back every setting changed by apply()."""
    import core
    done, keep = [], {}
    for sid, old in _load_undo().items():
        try:
            if sid == "jarvis":
                data = core.load_json(core.SETTINGS_FILE, {})
                for s, k, v in old:
                    if v is None:
                        data.get(s, {}).pop(k, None)
                        core.CONFIG.get(s, {}).pop(k, None)
                    else:
                        data.setdefault(s, {})[k] = v
                        core.CONFIG.setdefault(s, {})[k] = v
                core.save_json(core.SETTINGS_FILE, data)
            elif sid == "power":
                _run(["powercfg", "/setactive", str(old)], 10)
            elif sid in REG_STEPS:
                path, name, _ = REG_STEPS[sid]
                _reg_del(path, name) if old is None else _reg_set(path, name, old)
            elif sid.startswith("startup:"):
                _startup_set(sid, True)
            done.append(sid)
        except Exception:  # noqa: BLE001 — stays in the list, can be tried again
            keep[sid] = old
    if keep:
        UNDO.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        UNDO.unlink(missing_ok=True)
    return done


# ------------------------------------------------------------------------------------------------ TV on the home network

def find_tv() -> dict:
    """Looks for a Samsung TV on the home network (port 8001) and saves its address. Called only from the owner's button."""
    import socket
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        me = s.getsockname()[0]
    if not re.match(r"(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", me):
        return {"found": False, "message": "Компьютер не в домашней сети."}

    def probe(ip: str):
        try:
            with urllib.request.urlopen(f"http://{ip}:8001/api/v2/", timeout=1.5) as r:
                d = json.loads(r.read()).get("device", {})
            return (ip, d) if "samsung" in (d.get("type", "") + d.get("modelName", "") + d.get("OS", "")).lower() or d.get("OS") == "Tizen" else None
        except Exception:  # noqa: BLE001 — nothing there
            return None
    with ThreadPoolExecutor(64) as pool:
        hits = [x for x in pool.map(probe, [me.rsplit(".", 1)[0] + f".{i}" for i in range(1, 255)]) if x]
    if not hits:
        return {"found": False, "message": "Телевизор Samsung не ответил. Включите его и подключите к той же сети Wi-Fi."}
    ip, d = hits[0]
    mac = str(d.get("wifiMac") or "").lower()
    mac = mac if re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", mac) else ""
    path = BASE / "prime" / "config" / "devices.yaml"
    if path.exists() and re.search(r'ip:\s*"\d', path.read_text(encoding="utf-8")):
        return {"found": True, "message": f"Нашёл {d.get('modelName', 'Samsung')}, адрес {ip}. Он уже настроен."}
    path.write_text("# Written by «Найти телевизор». Stays on this PC.\ndevices:\n  tv_samsung:\n    type: smart_tv\n    protocol: samsung_tizen\n"
                    f'    ip: "{ip}"\n    mac: "{mac}"\n    mac_wifi: "{mac}"\n  headphones:\n    type: bluetooth_audio\n    name_contains: ""\n', encoding="utf-8")
    return {"found": True, "message": f"Нашёл {d.get('modelName', 'Samsung')}. При первой команде разрешите доступ на экране телевизора."}


def report() -> str:
    a = analyze()
    out = [f"Оценка компьютера: {a['score']} из 100, класс: {a['tier_name']}", ""]
    out += [f"  {k}: {v}" for k, v in a["passport"]]
    out += ["", "Что мешает:"] + ([f"  - {p['title']}. {p['how']}" for p in a["problems"]] or ["  ничего серьёзного"])
    out += ["", "Что можно оптимизировать (в окне Джарвиса, после вашего согласия):"]
    out += [f"  - {s['title']}" for s in a["plan"] if s["group"] != "startup"] or ["  всё уже настроено"]
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(report())
