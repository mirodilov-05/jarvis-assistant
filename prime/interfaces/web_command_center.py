"""Web command center: a small local page and JSON API on 127.0.0.1 only (aiohttp, already in the project).

GET  /              — the page
GET  /api/status    — battery, engine, open tasks, goals, pending confirmations
POST /api/command   — {"text": "..."} runs one request through Prime.handle()
"""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from core.watchdog import battery_state
from domains import study_cards

TV_BUTTONS: dict[str, tuple[str, dict]] = {
    "on": ("tv_on", {}), "off": ("tv_off", {}), "youtube": ("tv_youtube", {}),
    "up": ("tv_key", {"key": "KEY_VOLUP"}), "down": ("tv_key", {"key": "KEY_VOLDOWN"}), "mute": ("tv_key", {"key": "KEY_MUTE"}),
    "ch_up": ("tv_key", {"key": "KEY_CHUP"}), "ch_down": ("tv_key", {"key": "KEY_CHDOWN"}),
    "home": ("tv_key", {"key": "KEY_HOME"}), "back": ("tv_key", {"key": "KEY_RETURN"}), "source": ("tv_key", {"key": "KEY_SOURCE"}),
    "ok": ("tv_key", {"key": "KEY_ENTER"}), "pause": ("tv_key", {"key": "KEY_PAUSE"}), "play": ("tv_key", {"key": "KEY_PLAY"}),
    "left": ("tv_key", {"key": "KEY_LEFT"}), "right": ("tv_key", {"key": "KEY_RIGHT"}),
    "arrow_up": ("tv_key", {"key": "KEY_UP"}), "arrow_down": ("tv_key", {"key": "KEY_DOWN"}),
}
PAGE = Path(__file__).resolve().parent / "index.html"


def make_app(prime) -> web.Application:
    app = web.Application(client_max_size=64 * 1024)

    async def index(_r: web.Request) -> web.Response:
        return web.FileResponse(PAGE)

    async def status(_r: web.Request) -> web.Response:
        tasks = await prime.mem.open_tasks()
        goals = await prime.mem.goals()
        bat = battery_state()
        return web.json_response({
            "battery": bat,
            "saver": prime.router.saver,
            "engine": "gemini" if prime.router.key else ("local" if prime.router.local_available() else "offline"),
            "budget_left_usd": round(max(0.0, prime.budget.limit_usd - prime.budget.spent), 2),
            "tasks": tasks[:20],
            "goals": goals[:20],
            "pending_confirmations": sorted(prime.guard.pending),
        })

    async def history(_r: web.Request) -> web.Response:
        return web.json_response({"turns": await prime.mem.recent_turns(60)})

    async def command(r: web.Request) -> web.Response:
        try:
            body = await r.json()
        except (ValueError, UnicodeDecodeError):      # bad JSON or not UTF-8: a clear 400, never a crash
            return web.json_response({"error": "нужен JSON в кодировке UTF-8"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "нужен объект с полем text"}, status=400)
        text = str(body.get("text", "")).strip()
        if not text or len(text) > 2000:
            return web.json_response({"error": "пустой или слишком длинный запрос"}, status=400)
        reply = await prime.handle(text)
        return web.json_response({"reply": reply})

    # ---- used by the Jarvis home screen. The custom header keeps other web pages from calling these.
    async def _json(r: web.Request) -> dict:
        if r.headers.get("X-Jarvis") != "1":
            raise web.HTTPForbidden()
        try:
            body = await r.json()
        except (ValueError, UnicodeDecodeError):
            raise web.HTTPBadRequest() from None
        return body if isinstance(body, dict) else {}

    async def tv(r: web.Request) -> web.Response:
        """One remote-control button. Runs the tool directly: it is not a spoken request, so no history line."""
        body = await _json(r)
        call = TV_BUTTONS.get(str(body.get("what", "")))
        if call is None:
            return web.json_response({"ok": False, "reply": "неизвестная кнопка"}, status=400)
        step = await prime.orch.run_tool(call[0], **call[1])
        return web.json_response({"ok": step.status == "done", "reply": step.result})

    async def cards_get(_r: web.Request) -> web.Response:
        return web.json_response(await study_cards.state(prime.mem))

    async def cards_post(r: web.Request) -> web.Response:
        body = await _json(r)
        try:
            reply = await study_cards.add_deck(prime.mem) if body.get("deck") == "n2" else \
                await study_cards.add(prime.mem, str(body.get("front", "")), str(body.get("back", "")))
        except ValueError as e:
            return web.json_response({**await study_cards.state(prime.mem), "reply": str(e)})
        return web.json_response({**await study_cards.state(prime.mem), "reply": reply})

    async def cards_review(r: web.Request) -> web.Response:
        body = await _json(r)
        try:
            reply = await study_cards.review(prime.mem, int(body.get("id", 0)), int(body.get("quality", 0)))
        except ValueError as e:
            reply = str(e)
        return web.json_response({**await study_cards.state(prime.mem), "reply": reply})

    app.router.add_post("/api/tv", tv)
    app.router.add_get("/api/cards", cards_get)
    app.router.add_post("/api/cards", cards_post)
    app.router.add_post("/api/cards/review", cards_review)
    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/command", command)
    app.router.add_get("/api/history", history)
    return app


async def serve(prime, port: int = 8765) -> web.AppRunner:
    runner = web.AppRunner(make_app(prime))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)      # local only, never 0.0.0.0
    await site.start()
    return runner
