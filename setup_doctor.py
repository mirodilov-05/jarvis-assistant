"""First-run check for a new PC: what is ready, what is missing, and what to do about it.

Nothing is installed, downloaded or restarted by a check. Each fix is listed first and runs only when the owner
confirms it (a button in the app, the voice «да», or the terminal prompt). Manual fixes are only described:
Ollama, the microphone, the Gemini key (entered in the app), Smart App Control (a Windows setting only you change).

Run from a terminal:  python setup_doctor.py            (report)
                      python setup_doctor.py --fix      (asks before each automatic fix)
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV_PY = BASE / ".venv" / "Scripts" / "python.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
STATE = BASE / "data" / "setup_state.json"
REQUIRED_MODULES = ["openwakeword", "faster_whisper", "sounddevice", "keyring", "psutil", "edge_tts",
                    "piper", "anthropic", "telethon", "requests", "aiohttp", "yaml", "pycaw", "webview", "tokenizers"]
VOICES = ["denis", "dmitri", "irina", "ruslan"]
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/{v}/medium/ru_RU-{v}-medium.{ext}"
MODEL_FILES = {
    "models/minilm/onnx/model_quantized.onnx": "https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/onnx/model_quantized.onnx",
    "models/minilm/tokenizer.json": "https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/tokenizer.json",
    "models/speaker/voxceleb_resnet34_LM.onnx": "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/voxceleb_resnet34_LM.onnx",
}


@dataclass
class Fix:
    id: str
    label: str
    kind: str                 # "auto" (the app runs it after your yes) or "manual" (you do it, the app explains)
    size: str = ""            # what gets downloaded, roughly
    admin: bool = False       # needs administrator rights (Windows asks)
    reboot: bool = False      # a restart is needed afterwards


@dataclass
class Check:
    id: str
    title: str
    status: str               # "ok", "missing", "optional", "warn"
    detail: str = ""
    fix: Fix | None = None


def _run(cmd: list[str], timeout: int = 60, cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=str(cwd) if cwd else None, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _reg(hive: str, path: str, value: str):
    try:
        import winreg
        root = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}[hive]
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, value)[0]
    except Exception:  # noqa: BLE001
        return None


def _key_exists(path: str) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path):
            return True
    except OSError:
        return False


def _free_gb(path: Path) -> float:
    try:
        return shutil.disk_usage(path).free / 2 ** 30
    except OSError:
        return 0.0


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None


def _secret(name: str) -> bool:
    try:
        import connections
        return bool(connections.get_secret(name))
    except Exception:  # noqa: BLE001
        return False


def _uv_exe() -> str:
    """uv right after its own installation is not on PATH yet."""
    local = Path.home() / ".local" / "bin" / "uv.exe"
    return shutil.which("uv") or (str(local) if local.exists() else "uv")


def _sync() -> list[str]:
    return [_uv_exe(), "sync", "--python", "3.12", *(["--extra", "gpu"] if has_nvidia() else [])]


def check_all() -> list[Check]:
    out: list[Check] = []
    win = platform.system() == "Windows"
    out.append(Check("windows", "Windows 10/11, 64-бит",
                     "ok" if win and platform.machine().endswith("64") else "missing",
                     platform.platform()))

    py_ok = VENV_PY.exists()
    py_ver = ""
    if py_ok:
        _, v = _run([str(VENV_PY), "-c", "import sys;print('%d.%d' % sys.version_info[:2])"])
        py_ver = v.strip()
    py_good = py_ok and py_ver in ("3.11", "3.12")
    out.append(Check("python", "Python 3.11–3.12 для Джарвиса",
                     "ok" if py_good else "missing",
                     f"версия в окружении: {py_ver or 'окружения нет'}",
                     None if py_good else Fix("python312", "Установить Python 3.12 (через winget)", "auto",
                                              size="около 25 МБ")))

    uv_path = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv.exe")
    uv_ok = Path(uv_path).exists() or bool(shutil.which("uv"))
    out.append(Check("uv", "Менеджер пакетов uv", "ok" if uv_ok else "missing",
                     "нужен, чтобы поставить библиотеки",
                     None if uv_ok else Fix("uv", "Установить uv", "auto", size="несколько МБ")))

    vc = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "msvcp140.dll").exists()
    out.append(Check("vcredist", "Библиотеки Microsoft Visual C++", "ok" if vc else "missing",
                     "" if vc else "без них не запустится распознавание речи",
                     None if vc else Fix("vcredist", "Установить Visual C++ (через winget)", "auto", size="около 25 МБ", admin=True)))
    wv = any(_reg(h, p, "pv") for h, p in (
        ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ("HKCU", r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")))
    out.append(Check("webview", "WebView2 (окно Джарвиса)", "ok" if wv else "optional",
                     "" if wv else "без него окно откроется в браузере Edge",
                     None if wv else Fix("webview", "Установить WebView2 (через winget)", "auto", size="около 2 МБ")))

    missing = []
    if py_ok:
        code = "import importlib.util as u,sys;print(' '.join(m for m in sys.argv[1:] if u.find_spec(m) is None))"
        _, out_mods = _run([str(VENV_PY), "-c", code, *REQUIRED_MODULES])
        missing = out_mods.split()
    out.append(Check("deps", "Библиотеки Джарвиса", "ok" if py_ok and not missing else "missing",
                     ("не хватает: " + ", ".join(missing)) if missing else "все на месте",
                     None if py_ok and not missing else Fix("deps", "Установить библиотеки (uv sync)", "auto",
                                                            size="несколько сотен МБ")))

    node = shutil.which("node")
    node_ver = ""
    if node:
        _, v = _run(["node", "--version"])
        node_ver = v.strip()
    node_ok = bool(node) and node_ver[1:].split(".")[0].isdigit() and int(node_ver[1:].split(".")[0]) >= 18
    out.append(Check("node", "Node.js 18+ (для WhatsApp)", "ok" if node_ok else "optional",
                     node_ver or "не установлен; нужен только для WhatsApp",
                     None if node_ok else Fix("node", "Установить Node.js LTS (через winget)", "auto",
                                              size="около 30 МБ", admin=True)))
    wa = (BASE / "whatsapp-bridge" / "node_modules").exists()
    out.append(Check("wa_bridge", "Мост WhatsApp (зависимости)", "ok" if wa else "optional",
                     "" if wa else "не установлен; нужен только для WhatsApp",
                     None if wa or not node_ok else Fix("wa_bridge", "Установить зависимости WhatsApp (npm)", "auto",
                                                        size="несколько МБ")))

    voices_missing = [v for v in VOICES if not (BASE / "voices" / f"ru_RU-{v}-medium.onnx").exists()]
    out.append(Check("voices", "Русские голоса (Piper)", "ok" if not voices_missing else "missing",
                     ("не хватает: " + ", ".join(voices_missing)) if voices_missing else "все четыре на месте",
                     None if not voices_missing else Fix("voices", "Скачать русские голоса", "auto",
                                                         size="около 250 МБ")))

    models_missing = [p for p in MODEL_FILES if not (BASE / p).exists()]
    out.append(Check("models", "Модели памяти и распознавания голоса", "ok" if not models_missing else "missing",
                     "" if not models_missing else f"не хватает {len(models_missing)} файл(а)",
                     None if not models_missing else Fix("models", "Скачать модели", "auto", size="около 150 МБ")))

    gpu, libs = has_nvidia(), (VENV_PY.parents[1] / "Lib" / "site-packages" / "nvidia").exists()
    out.append(Check("gpu", "Видеокарта NVIDIA (для быстрого распознавания)", "ok" if gpu and libs else "optional",
                     "готова" if gpu and libs else "есть, но её библиотеки не установлены" if gpu else "нет: речь распознаётся в облаке или на процессоре",
                     Fix("gpu_libs", "Установить библиотеки для видеокарты NVIDIA", "auto", size="около 1 ГБ") if gpu and not libs else None))

    mic_ok = False
    try:
        import sounddevice as sd
        mic_ok = any(d.get("max_input_channels", 0) > 0 for d in sd.query_devices())
    except Exception:  # noqa: BLE001
        mic_ok = False
    out.append(Check("mic", "Микрофон", "ok" if mic_ok else "missing",
                     "" if mic_ok else "не найден: подключите микрофон или гарнитуру",
                     None if mic_ok else Fix("mic", "Подключить микрофон и проверить в Windows", "manual")))

    groq, gem = _secret("groq:api_key"), _secret("gemini:api_key")
    out.append(Check("groq", "Ключ Groq (речь и мозг)", "ok" if groq else "missing", "сохранён" if groq else "бесплатный, берётся на console.groq.com/keys",
                     None if groq else Fix("groq", "Ввести ключ Groq: Настройки → Ключи", "manual")))
    out.append(Check("gemini", "Ключ Gemini (зрение, запасной мозг)", "ok" if gem else "optional" if groq else "missing",
                     "сохранён" if gem else "бесплатный, берётся на aistudio.google.com/apikey",
                     None if gem else Fix("gemini", "Ввести ключ Gemini: Настройки → Ключи", "manual")))

    ollama = shutil.which("ollama") is not None
    out.append(Check("ollama", "Ollama (локальный мозг, без интернета)", "ok" if ollama else "optional",
                     "есть" if ollama else "не нужен, если есть ключ Gemini",
                     None if ollama else Fix("ollama", "Установить Ollama с ollama.com", "manual")))

    sac = _reg("HKLM", r"SYSTEM\CurrentControlSet\Control\CI\Policy", "VerifiedAndReputablePolicyState")
    if sac == 1:
        out.append(Check("sac", "Smart App Control", "warn",
                         "включён: блокирует неподписанные программы (нужны для сборки). Выключить можно только в "
                         "«Безопасность Windows → Управление приложениями и браузером». Решение за вами.",
                         Fix("sac", "Выключить Smart App Control вручную (Windows)", "manual")))
    else:
        out.append(Check("sac", "Smart App Control", "ok", "выключен или не используется"))

    reboot = (_key_exists(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending")
              or _key_exists(r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"))
    out.append(Check("reboot", "Перезагрузка Windows", "warn" if reboot else "ok",
                     "Windows ждёт перезагрузки: сделайте её до установки" if reboot else "не нужна",
                     Fix("reboot", "Перезагрузить компьютер через минуту", "auto", reboot=True) if reboot else None))

    free = _free_gb(BASE)
    out.append(Check("disk", "Свободное место на диске с Джарвисом", "ok" if free >= 10 else "warn",
                     f"свободно {free:.0f} ГБ (нужно около 10 ГБ)"))
    return out


def missing_auto(checks: list[Check]) -> list[Check]:
    return [c for c in checks if c.fix and c.fix.kind == "auto" and c.status in ("missing", "warn", "optional")]


def summary(checks: list[Check]) -> str:
    lines = []
    for c in checks:
        mark = {"ok": "готово", "missing": "не хватает", "optional": "по желанию", "warn": "внимание"}[c.status]
        lines.append(f"- {c.title}: {mark}" + (f" — {c.detail}" if c.detail and c.status != "ok" else ""))
    return "\n".join(lines)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


AUTO_STEPS: dict[str, object] = {}


def _step(fix_id: str):
    def deco(fn):
        AUTO_STEPS[fix_id] = fn
        return fn
    return deco


@_step("python312")
def _python(): return _run(["winget", "install", "-e", "--id", "Python.Python.3.12", "--silent",
                            "--accept-package-agreements", "--accept-source-agreements"], timeout=900)


@_step("uv")
def _uv(): return _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                        "irm https://astral.sh/uv/install.ps1 | iex"], timeout=300)


@_step("deps")
def _deps(): return _run(_sync(), timeout=3600, cwd=BASE)


@_step("gpu_libs")
def _gpu_libs(): return _run(_sync(), timeout=3600, cwd=BASE)


@_step("vcredist")
def _vcredist(): return _run(["winget", "install", "-e", "--id", "Microsoft.VCRedist.2015+.x64", "--silent",
                              "--accept-package-agreements", "--accept-source-agreements"], timeout=900)


@_step("webview")
def _webview(): return _run(["winget", "install", "-e", "--id", "Microsoft.EdgeWebView2Runtime", "--silent",
                             "--accept-package-agreements", "--accept-source-agreements"], timeout=900)


@_step("node")
def _node(): return _run(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--silent",
                          "--accept-package-agreements", "--accept-source-agreements"], timeout=900)


@_step("wa_bridge")
def _wa(): return _run(["npm", "install", "--no-fund", "--no-audit"], timeout=900, cwd=BASE / "whatsapp-bridge")


@_step("voices")
def _voices():
    try:
        for v in VOICES:
            for ext in ("onnx", "onnx.json"):
                dest = BASE / "voices" / f"ru_RU-{v}-medium.{ext}"
                if not dest.exists():
                    _download(VOICE_URL.format(v=v, ext=ext), dest)
        return 0, "голоса скачаны"
    except OSError as e:
        return 1, f"не удалось скачать голоса: {e}"


@_step("models")
def _models():
    try:
        for rel, url in MODEL_FILES.items():
            if not (BASE / rel).exists():
                _download(url, BASE / rel)
        return 0, "модели скачаны"
    except OSError as e:
        return 1, f"не удалось скачать модели: {e}"


@_step("reboot")
def _reboot(): return _run(["shutdown", "/r", "/t", "60", "/c", "Jarvis: перезагрузка для установки. Сохраните работу."])


def run_fix(fix_id: str) -> tuple[bool, str]:
    """Run one automatic fix. Call only after the owner confirmed it."""
    fn = AUTO_STEPS.get(fix_id)
    if fn is None:
        return False, "Такое исправление не выполняется автоматически. Сделайте шаг вручную."
    code, text = fn()
    ok = code == 0
    if fix_id == "deps" and not ok:
        return False, "Библиотеки не установились: " + text[-300:]
    return ok, ("готово" if ok else (text[-300:] or "не получилось"))


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _mark(key: str) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({**_state(), key: True}), encoding="utf-8")


def mark_checked() -> None:
    _mark("checked")


def mark_hinted() -> None:
    _mark("hinted")


def mark_wizard() -> None:
    _mark("wizard")


def was_hinted() -> bool:
    return bool(_state().get("hinted"))


def was_checked() -> bool:
    return bool(_state().get("checked"))


def wizard_done() -> bool:
    return bool(_state().get("wizard"))


_LAST: dict = {"running": False, "log": [], "now": "", "total": 0}


def run_all_in_background(fix_ids: list[str], on_done=None) -> bool:
    if _LAST["running"]:
        return False
    _LAST.update(running=True, log=[], now="", total=len(fix_ids))

    def work():
        try:
            for fid in fix_ids:
                _LAST["now"] = fid
                ok, msg = run_fix(fid)
                _LAST["log"].append({"id": fid, "ok": ok, "message": msg})
            if on_done:
                on_done()
        finally:
            _LAST["running"] = False

    threading.Thread(target=work, daemon=True, name="setup-fixes").start()
    return True


def last_run() -> dict:
    return dict(_LAST)


def _cli() -> int:
    checks = check_all()
    print(summary(checks))
    todo = missing_auto(checks)
    if not todo or "--fix" not in sys.argv:
        if todo:
            print("\nЧтобы выполнить автоматические шаги с вашим подтверждением: python setup_doctor.py --fix")
        return 0
    for c in todo:
        f = c.fix
        extra = (f" [скачается: {f.size}]" if f.size else "") + (" [нужны права администратора]" if f.admin else "") \
            + (" [потом перезагрузка]" if f.reboot else "")
        if input(f"Выполнить «{f.label}»{extra}? (да/нет): ").strip().lower() not in ("да", "y", "yes"):
            print("  пропущено")
            continue
        ok, msg = run_fix(f.id)
        print(("  OK: " if ok else "  ОШИБКА: ") + msg)
    mark_checked()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
