"""Learns this computer, with the owner's consent, so Jarvis fits this PC.

What is read (names and facts only, never the contents of files):
  - installed programs: Start Menu shortcuts and the Windows uninstall list (names);
  - user folders: how many items each has, and folder names under Documents (no file names);
  - hardware and system: Windows edition, CPU, RAM, graphics card, default browser.

Nothing is sent anywhere. The result is one local file, data/pc_profile.json, which is never committed
(data/ is in .gitignore). A scan runs only after the owner agrees: the button on the home screen or the
voice command «изучи мой компьютер». Deleting data/pc_profile.json forgets everything.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROFILE = BASE / "data" / "pc_profile.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
USER_FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]


def _start_menu_names() -> list[str]:
    roots = [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
             Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs"]
    names: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for lnk in root.rglob("*.lnk"):
            names.add(lnk.stem)
    return sorted(names, key=str.lower)


def _uninstall_names() -> list[str]:
    try:
        import winreg
    except ImportError:
        return []
    names: set[str] = set()
    keys = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as root:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            name, _ = winreg.QueryValueEx(k, "DisplayName")
                            try:
                                system_component, _ = winreg.QueryValueEx(k, "SystemComponent")
                            except OSError:
                                system_component = 0
                            if name and system_component != 1:   # hidden system entries are not programs
                                names.add(str(name))
                    except OSError:
                        continue
        except OSError:
            continue
    return sorted(names, key=str.lower)


def _default_browser() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as k:
            prog, _ = winreg.QueryValueEx(k, "ProgId")
    except Exception:  # noqa: BLE001
        return ""
    prog = str(prog).lower()
    for key, title in (("edge", "Microsoft Edge"), ("chrome", "Google Chrome"), ("firefox", "Firefox"),
                       ("opera", "Opera"), ("brave", "Brave"), ("yandex", "Яндекс Браузер"), ("safari", "Safari")):
        if key in prog:
            return title
    return str(prog)[:40]


def _reg_value(path: str, name: str) -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            return str(winreg.QueryValueEx(k, name)[0]).strip()
    except OSError:
        return ""


def _hardware() -> dict:
    """Read from the registry, psutil and nvidia-smi: milliseconds instead of the seconds a WMI query takes."""
    import psutil
    cpu = _reg_value(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
    os_name = _reg_value(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductName") or platform.platform()
    build = int(_reg_value(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuildNumber") or 0)
    if build >= 22000 and os_name.startswith("Windows 10"):     # Windows 11 keeps the old product name in the registry
        os_name = "Windows 11" + os_name[len("Windows 10"):]
    gpu = ""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, timeout=5,
                           creationflags=NO_WINDOW)
        gpu = r.stdout.decode("utf-8", "replace").strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        gpu = ""
    return {"cpu": cpu, "ram_gb": round(psutil.virtual_memory().total / 1024 ** 3), "gpu": gpu, "os": os_name}


def _folders() -> dict:
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    out: dict = {}
    for name in USER_FOLDERS:
        p = home / name
        if p.exists():
            try:
                out[name] = sum(1 for _ in p.iterdir())
            except OSError:
                out[name] = 0
    docs = home / "Documents"
    try:
        out["_documents_folders"] = sorted(d.name for d in docs.iterdir() if d.is_dir())[:60]
    except OSError:
        out["_documents_folders"] = []
    return out


def scan() -> dict:
    """Read the computer and save the profile. Call only after the owner agreed. The parts run side by side."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = {"hardware": pool.submit(_hardware), "browser": pool.submit(_default_browser),
                "apps": pool.submit(_start_menu_names), "installed": pool.submit(_uninstall_names),
                "folders": pool.submit(_folders)}
        got = {k: f.result() for k, f in jobs.items()}
    data = {
        "scanned_at": dt.datetime.now().isoformat(timespec="seconds"),
        "hardware": got["hardware"],
        "browser": got["browser"],
        "apps": got["apps"][:400],
        "installed": got["installed"][:400],
        "folders": got["folders"],
    }
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load() -> dict | None:
    try:
        return json.loads(PROFILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summary(max_chars: int = 900) -> str:
    """A short, plain-text description for the assistant's prompt. Empty if the PC was not studied."""
    d = load()
    if not d:
        return ""
    hw = d.get("hardware", {})
    folders = d.get("folders", {})
    apps = d.get("installed") or d.get("apps") or []
    parts = [
        f"{hw.get('os', '')}; процессор {hw.get('cpu', '')}; ОЗУ {hw.get('ram_gb', '?')} ГБ; видео {hw.get('gpu', '')}".strip("; "),
        f"браузер по умолчанию: {d.get('browser') or 'неизвестно'}",
        "папки: " + ", ".join(f"{k} ({v})" for k, v in folders.items() if not k.startswith("_")),
        f"программы ({len(apps)}): " + ", ".join(apps[:60]),
    ]
    return ("; ".join(p for p in parts if p))[:max_chars]
