"""Device hub: Wake-on-LAN, TV reachability, Home Assistant, Bluetooth audio. Everything is optional.

A device with empty settings in config/devices.yaml is simply reported as "not configured".
Nothing here guesses an address: no IP or MAC means no network call at all.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("prime.devices")


def load_devices(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("devices", {}) or {}


def magic_packet(mac: str) -> bytes:
    """Wake-on-LAN frame: 6 x 0xFF followed by the MAC repeated 16 times."""
    hexes = mac.replace(":", "").replace("-", "").strip()
    if len(hexes) != 12 or any(c not in "0123456789abcdefABCDEF" for c in hexes):
        raise ValueError(f"bad MAC address: {mac!r}")
    raw = bytes.fromhex(hexes)
    return b"\xff" * 6 + raw * 16


def wake_on_lan(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> str:
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (broadcast, port))
    return f"Пакет включения отправлен на {mac}."


def reachable(ip: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


async def tv_status(cfg: dict[str, Any]) -> str:
    ip = cfg.get("ip", "")
    if not ip:
        return "Телевизор не настроен: укажите IP в config/devices.yaml."
    # Samsung Tizen TVs answer on 8001 (http) and 8002 (https) when they are on
    on = await asyncio.to_thread(reachable, ip, 8001)
    return "Телевизор включён и доступен по сети." if on else "Телевизор выключен или не в сети."


async def tv_power_on(cfg: dict[str, Any]) -> str:
    mac = cfg.get("mac", "")
    if not mac:
        return "Телевизор не настроен: укажите MAC в config/devices.yaml, чтобы включать его по сети."
    return await asyncio.to_thread(wake_on_lan, mac)


async def ha_call(url: str, token: str, service: str, entity_id: str, data: dict[str, Any] | None = None) -> str:
    """Call a Home Assistant service, e.g. light.turn_on. Needs a long-lived token in the environment."""
    if not url or not token:
        return "Умный дом не настроен: нужны адрес Home Assistant и токен."
    import json
    import urllib.request

    domain, action = service.split(".", 1)
    body = json.dumps({"entity_id": entity_id, **(data or {})}).encode()

    def call() -> str:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/services/{domain}/{action}", body,
                                     {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return "Готово." if r.status in (200, 201) else f"Ошибка: {r.status}"
    try:
        return await asyncio.to_thread(call)
    except Exception as e:  # noqa: BLE001 — a missing home must not break the assistant
        log.error("home assistant call failed: %s", e)
        return "Умный дом не отвечает."


async def bluetooth_audio(name_contains: str) -> str:
    """List nearby Bluetooth devices whose name contains the given text. Needs the bleak package."""
    if not name_contains:
        return "Наушники не настроены: укажите часть имени в config/devices.yaml."
    try:
        from bleak import BleakScanner
    except ImportError:
        return "Bluetooth недоступен: не установлен пакет bleak."
    try:
        found = await asyncio.wait_for(BleakScanner.discover(timeout=6), timeout=10)
    except Exception as e:  # noqa: BLE001 — Bluetooth may be off
        log.error("bluetooth scan failed: %s", e)
        return "Не удалось сканировать Bluetooth: проверьте, что он включён."
    names = [d.name for d in found if d.name and name_contains.lower() in d.name.lower()]
    return f"Нашёл: {', '.join(names)}." if names else f"«{name_contains}» рядом не найден."


def ha_settings() -> tuple[str, str]:
    return os.environ.get("PRIME_HA_URL", ""), os.environ.get("PRIME_HA_TOKEN", "")
