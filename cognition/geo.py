"""Where an outside IP address is: country, city, provider (ASN). Only on the owner's explicit request.

What leaves the PC: the one IP address the owner asked about, over HTTPS, to ipapi.co. Nothing else:
no name, no list of connections, no history. Private and local addresses are refused without a request.
Answers are cached for a day in data/jarvis_cognitive.db so the same address is not asked twice.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import urllib.error
import urllib.request

from cognition import db

API = "https://ipapi.co/{ip}/json/"
TTL = dt.timedelta(days=1)


def _public(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise ValueError("это не IP-адрес")
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified or addr.is_reserved:
        raise ValueError("это домашний или служебный адрес, его место не определить")
    return str(addr)


def _cached(ip: str, path=None) -> dict | None:
    with db.conn(path) as c:
        row = c.execute("SELECT value FROM relationship WHERE key = ?", ("geo:" + ip,)).fetchone()
    if not row:
        return None
    if dt.datetime.now() - dt.datetime.fromisoformat(json.loads(row["value"])["at"]) > TTL:
        return None
    return json.loads(row["value"])["data"]


def _store(ip: str, data: dict, path=None) -> None:
    val = json.dumps({"at": dt.datetime.now().isoformat(timespec="seconds"), "data": data}, ensure_ascii=False)
    with db.conn(path) as c:
        c.execute("INSERT INTO relationship(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                  ("geo:" + ip, val))


def locate(ip: str, path=None, fetch=None) -> dict:
    """{'ip','country','city','org','asn'} for a public address. `fetch(url) -> dict` is injectable for tests."""
    ip = _public(ip)
    hit = _cached(ip, path)
    if hit is not None:
        return hit
    if fetch is None:
        def fetch(url):
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode("utf-8"))
    try:
        raw = fetch(API.format(ip=ip))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ValueError("сервис определения места не ответил, попробуйте позже") from e
    if raw.get("error"):
        raise ValueError("сервис не знает этот адрес")
    data = {"ip": ip, "country": raw.get("country_name", ""), "city": raw.get("city", ""),
            "org": raw.get("org", ""), "asn": raw.get("asn", "")}
    _store(ip, data, path)
    return data
