"""The programs on this PC that Jarvis can open by name, whether each one runs right now, and their icons.

The list comes from the Start Menu and desktop shortcuts. Each shortcut is resolved to its .exe, so «запущена» means
that exact .exe is running (not a program with a similar name). Installers, help and Windows admin tools are left out.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import procs

BASE = Path(__file__).resolve().parent
ICONS = BASE / "data" / "icons"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ROOTS = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
    Path.home() / "Desktop",
    Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
]
SKIP = re.compile(r"uninstall|удал|readme|help|справк|documentation|документац|manual|docs|module|verifier|license|release notes|website|сайт|"
                  r"setup|installer|^install |установ|обновлен|update|about|administrative|control panel|registry|event viewer|component services|"
                  r"computer management|disk cleanup|system configuration|system information|^run$|character map|performance|resource|"
                  r"task scheduler|^services$|defrag|dfrgui|security configuration|debuggable|developer|windows tools|memory diagnostic|"
                  r"odbc|iscsi|recoverydrive|print management|fax|steps recorder|quick assist|remote desktop|wordpad|magnify|narrator|"
                  r"on-screen|voiceaccess|livecaptions|immersive|idle \(|driver & support|git cmd|git gui|(\(x86\)|x64|arm64)$", re.I)
SKIP_EXE = {"cmd.exe", "powershell.exe", "mmc.exe", "explorer.exe", "control.exe", "rundll32.exe", "msiexec.exe", "wscript.exe", "hh.exe"}
_LOCK = threading.Lock()
_LIST: dict = {"at": 0.0, "items": []}


def _scan() -> list[dict]:
    import comtypes
    import comtypes.client
    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
    found: dict[str, dict] = {}
    for root in ROOTS:
        if not root.exists():
            continue
        for lnk in root.rglob("*.lnk"):
            name = lnk.stem.strip()
            if not name or SKIP.search(name):
                continue
            try:
                sc = shell.CreateShortcut(str(lnk))
                target, args = str(sc.TargetPath or ""), str(sc.Arguments or "")
            except Exception:  # noqa: BLE001 — a broken shortcut
                continue
            if not target.lower().endswith(".exe") or not Path(target).exists():
                continue
            exe = Path(target).name.lower()
            real = re.search(r"--processStart\s+\"?([\w .-]+\.exe)", args, re.I)      # Discord starts through Update.exe
            if real:
                exe = real.group(1).lower()
            if exe in SKIP_EXE or (args and exe in ("chrome.exe", "msedge.exe") and "--app" in args):
                continue
            found.setdefault(exe + "|" + ("" if exe not in ("python.exe", "pythonw.exe") else name.lower()),
                             {"name": name, "lnk": str(lnk), "exe": exe, "target": target})
    items = [x for x in found.values() if not x["exe"].startswith("python")]
    return sorted(items, key=lambda x: x["name"].lower())


def shortcuts() -> list[dict]:
    """All known programs; the shortcuts are re-read every 10 minutes."""
    with _LOCK:
        if not _LIST["items"] or time.time() - _LIST["at"] > 600:
            _LIST.update(items=_scan(), at=time.time())
            threading.Thread(target=make_icons, args=(list(_LIST["items"]),), daemon=True, name="icons").start()
        return _LIST["items"]


def icon_id(target: str) -> str:
    return hashlib.sha1(target.lower().encode("utf-8")).hexdigest()[:16]


def make_icons(items: list[dict]) -> None:
    """Saves each program's own icon as a small PNG in data/icons (one PowerShell run for all missing ones)."""
    ICONS.mkdir(parents=True, exist_ok=True)
    todo = [{"src": x["target"], "dst": str(ICONS / (icon_id(x["target"]) + ".png"))} for x in items
            if not (ICONS / (icon_id(x["target"]) + ".png")).exists()]
    # Discord's shortcut points at Update.exe: take the icon of the real program next to it
    if not todo:
        return
    job = ICONS / "job.json"
    job.write_text(json.dumps(todo), encoding="utf-8")
    script = ("Add-Type -AssemblyName System.Drawing; $j = Get-Content -Raw -Encoding UTF8 '" + str(job) + "' | ConvertFrom-Json; "
              "foreach ($x in $j) { try { $i = [System.Drawing.Icon]::ExtractAssociatedIcon($x.src); "
              "$i.ToBitmap().Save($x.dst, [System.Drawing.Imaging.ImageFormat]::Png) } catch {} }")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=90, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        pass
    job.unlink(missing_ok=True)


def list_programs(limit: int = 24) -> list[dict]:
    """[{name, running, memory_mb, processes, icon}] — running programs first, then by name."""
    mem: dict[str, list[float]] = {}
    for p in procs.snapshot():
        mem.setdefault(p["name"].lower(), []).append(p["mem"])
    out = []
    for x in shortcuts():
        m = mem.get(x["exe"], [])
        out.append({"name": x["name"], "running": bool(m), "memory_mb": round(sum(m)), "processes": len(m), "exe": x["exe"],
                    "icon": icon_id(x["target"]) if (ICONS / (icon_id(x["target"]) + ".png")).exists() else ""})
    out.sort(key=lambda x: (not x["running"], x["name"].lower()))
    return out[:limit]


def _by_name(name: str) -> dict:
    for x in shortcuts():
        if x["name"] == name:
            return x
    raise ValueError("такой программы нет в списке")


def open_program(name: str) -> str:
    x = _by_name(name)
    os.startfile(x["lnk"])
    return f"Открываю {x['name']}."


def close_program(name: str) -> str:
    """Asks the program to close (as its own × would), without force: it can still ask about unsaved work."""
    x = _by_name(name)
    r = subprocess.run(["taskkill", "/IM", x["exe"]], capture_output=True, creationflags=NO_WINDOW, timeout=15)
    if r.returncode != 0:
        raise ValueError(f"{x['name']} не закрылась сама: закройте её окно вручную")
    return f"Закрываю {x['name']}."
