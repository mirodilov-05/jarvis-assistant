"""Keeps Jarvis running in the background no matter what.

- starts assistant.py (and Ollama if needed) with below-normal priority
- restarts Jarvis if it crashes or its audio loop freezes (heartbeat older than 60 s)
- backs off if it keeps crashing, so a broken setup can't spin the CPU
Started at Windows logon by the Startup shortcut (start-hidden.ps1).
"""

import ctypes
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
LOG = DATA / "supervisor.log"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
BELOW_NORMAL = 0x4000
NO_WINDOW = 0x08000000


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def single_instance() -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 50776))
    except OSError:
        sys.exit(0)
    return s


def ensure_ollama() -> None:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ollama.exe", "/NH"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    if "ollama.exe" in out.lower():
        return
    exe = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Ollama" / "ollama.exe"
    if exe.exists():
        env = dict(os.environ, OLLAMA_KEEP_ALIVE="30m", OLLAMA_MAX_LOADED_MODELS="1")
        subprocess.Popen([str(exe), "serve"], creationflags=NO_WINDOW | BELOW_NORMAL, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("started Ollama")


def heartbeat_age() -> float:
    try:
        return time.time() - int((DATA / "heartbeat").read_text())
    except (OSError, ValueError):
        return 0.0


def main() -> None:
    _lock = single_instance()  # noqa: F841
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
    log("supervisor started")
    first = True
    crashes: list[float] = []
    while True:
        ensure_ollama()
        (DATA / "heartbeat").unlink(missing_ok=True)
        args = [str(PYTHONW), str(BASE / "assistant.py")]
        if first and "--app" in sys.argv:
            args.append("--app")
        if not first:
            args.append("--restarted")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", HF_HUB_DISABLE_SYMLINKS_WARNING="1")
        proc = subprocess.Popen(args, cwd=BASE, creationflags=BELOW_NORMAL, env=env)
        first = False
        started = time.time()
        while proc.poll() is None:
            time.sleep(10)
            if time.time() - started > 120 and heartbeat_age() > 60:
                log("heartbeat stale — restarting Jarvis")
                proc.kill()
                break
        code = proc.poll()
        if code == 0 and time.time() - started < 5:
            log("another Jarvis is already running — supervisor exits")
            return
        log(f"Jarvis exited with code {code}")
        crashes = [t for t in crashes if time.time() - t < 600] + [time.time()]
        time.sleep(min(300, 5 * 2 ** (len(crashes) - 1)))  # 5 s, 10 s, 20 s … up to 5 min


if __name__ == "__main__":
    main()
