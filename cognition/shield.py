"""Home-network shield: what is listening, who is connected, a firewall block with the owner's yes, VPN status.

Honest limits: blocking a rule and starting a VPN tunnel need administrator rights in Windows. Without them
Jarvis says so and gives the command to run by hand. Nothing is sent anywhere: no outside lookups (no GeoIP service).
"""
from __future__ import annotations

import ipaddress
import subprocess
from pathlib import Path

import psutil

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
VPN_NAMES = ("wireguard", "wintun", "openvpn", "tap-windows", "tailscale", "warp", "cloudflare", "nordlynx", "proton")
KNOWN_OPEN = {135, 139, 445, 5040, 7680, 49664, 49665, 49666, 49667, 49668, 49669, 5357, 5353, 1900}


def ports() -> dict:
    """Listening ports (who opened them) and the outside addresses that are connected right now."""
    listening, remote = [], {}
    for c in psutil.net_connections(kind="inet"):
        try:
            name = psutil.Process(c.pid).name() if c.pid else "система"
        except psutil.Error:
            name = "?"
        if c.status == psutil.CONN_LISTEN and c.laddr:
            open_all = c.laddr.ip in ("0.0.0.0", "::")
            listening.append({"port": c.laddr.port, "program": name, "open_to_network": open_all,
                              "usual": c.laddr.port in KNOWN_OPEN})
        elif c.status == psutil.CONN_ESTABLISHED and c.raddr:
            ip = c.raddr.ip
            try:
                if ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback:
                    continue
            except ValueError:
                continue
            remote.setdefault(ip, {"ip": ip, "programs": set()})["programs"].add(name)
    odd = [p for p in listening if p["open_to_network"] and not p["usual"]]
    return {"listening": sorted({(p["port"], p["program"], p["open_to_network"], p["usual"]) for p in listening}, key=lambda x: x[0]),
            "unusual": sorted({(p["port"], p["program"]) for p in odd}),
            "remote": [{"ip": v["ip"], "programs": sorted(v["programs"])} for v in remote.values()][:20]}


def block_command(ip: str) -> str:
    return f'netsh advfirewall firewall add rule name="Jarvis block {ip}" dir=in action=block remoteip={ip}'


def block_ip(ip: str) -> str:
    """Adds a Windows Firewall rule. Only a valid address; the caller has already asked the owner."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError("это не IP-адрес")
    if addr.is_private or addr.is_loopback or addr.is_unspecified:
        raise ValueError("домашние и локальные адреса не блокирую")
    r = subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name=Jarvis block {addr}", "dir=in",
                        "action=block", f"remoteip={addr}"], capture_output=True, timeout=20, creationflags=NO_WINDOW)
    out = _text(r.stdout + r.stderr)
    if r.returncode != 0:
        if _netsh_error(out):
            raise ValueError("Windows не дала: нужны права администратора. Запустите окно Джарвиса от администратора "
                             "или выполните команду вручную: " + block_command(str(addr)))
        raise ValueError("брандмауэр не принял правило: " + out.strip()[:160])
    return f"Заблокировал {addr} во входящих подключениях."


def _text(raw: bytes) -> str:
    """netsh answers in UTF-8 on this Windows, in older versions in the console code page: try both."""
    for enc in ("utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _netsh_error(out: str) -> bool:
    low = out.lower()
    return any(w in low for w in ("администратор", "повышени", "elevat", "access is denied", "требуется", "запрещ"))


def unblock_ip(ip: str) -> str:
    """Removes the rule made by block_ip. Only rules with Jarvis's name are touched."""
    addr = str(ipaddress.ip_address(ip))
    r = subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name=Jarvis block {addr}"],
                       capture_output=True, timeout=20, creationflags=NO_WINDOW)
    out = _text(r.stdout + r.stderr)
    if r.returncode != 0:
        if _netsh_error(out):
            raise ValueError("нужны права администратора, чтобы убрать правило. Выполните вручную: "
                             f'netsh advfirewall firewall delete rule name="Jarvis block {addr}"')
        raise ValueError("правило не найдено или не удалилось: " + out.strip()[:160])
    return f"Разблокировал {addr}."


def vpn() -> dict:
    """Is a VPN adapter up? Only reads the network; nothing is changed here."""
    up = []
    for name, stats in psutil.net_if_stats().items():
        if stats.isup and any(v in name.lower() for v in VPN_NAMES):
            up.append(name)
    return {"on": bool(up), "adapters": up}


def vpn_tunnel(action: str, name: str) -> str:
    """Starts or stops an installed WireGuard tunnel by its name (the tunnel must already be set up)."""
    if not name or not all(ch.isalnum() or ch in "-_" for ch in name):
        raise ValueError("странное имя туннеля")
    exe = Path(r"C:\Program Files\WireGuard\wireguard.exe")
    if not exe.exists():
        raise ValueError("WireGuard не установлен. Установите его и создайте туннель, затем скажите «включи VPN» снова.")
    arg = "/installtunnelservice" if action == "on" else "/uninstalltunnelservice"
    conf = Path(r"C:\Program Files\WireGuard\Data\Configurations") / f"{name}.conf.dpapi"
    if action == "on" and not conf.exists():
        raise ValueError(f"туннель {name} не найден в WireGuard")
    target = str(Path(r"C:\Program Files\WireGuard\Data\Configurations") / f"{name}.conf") if action == "on" else name
    r = subprocess.run([str(exe), arg, target], capture_output=True, timeout=30, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise ValueError("Windows не дала изменить VPN: нужны права администратора. Сделайте это в приложении WireGuard вручную.")
    return "VPN включён." if action == "on" else "VPN выключен."
