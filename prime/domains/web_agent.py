"""Web agent: opens a page in a real browser and reads it. Read-only by design: no form submission here.

Needs the `playwright` package and its browser. Without them, every call returns a clear message.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

log = logging.getLogger("prime.web")
ALLOWED_SCHEMES = {"http", "https"}


def safe_url(url: str) -> str:
    """Only plain web addresses. Local files, javascript: and similar are refused."""
    p = urlparse(url.strip())
    if p.scheme not in ALLOWED_SCHEMES or not p.netloc:
        raise ValueError("только адреса http:// или https://")
    return url.strip()


async def read_page(url: str, max_chars: int = 4000, timeout_ms: int = 15000) -> str:
    url = safe_url(url)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Веб-агент недоступен: не установлен playwright."
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:  # noqa: BLE001 — browser binaries missing
            return "Браузер для веб-агента не установлен: выполните playwright install chromium."
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            text = await page.inner_text("body", timeout=timeout_ms)
            return " ".join(text.split())[:max_chars]
        finally:
            await browser.close()
