#!/usr/bin/env python3
"""Mock Slack API server for testing TrackGuard Slack integration."""

import json
from aiohttp import web

SLACK_API_URL = "http://localhost:8888"


async def auth_test(request):
    return web.json_response({
        "ok": True,
        "team_id": "T_MOCK_001",
        "user_id": "U_MOCK_BOT",
        "bot_id": "B_MOCK_001"
    })


async def views_open(request):
    data = await request.post()
    return web.json_response({
        "ok": True,
        "view": {
            "id": "V_MOCK_001",
            "callback_id": "decision_modal"
        }
    })


async def chat_postMessage(request):
    data = await request.post()
    return web.json_response({
        "ok": True,
        "ts": "1745000000.000001",
        "channel": data.get("channel", "U_MOCK_USER")
    })


async def chat_update(request):
    return web.json_response({"ok": True})


app = web.Application()
app.router.add_post("/api/auth.test", auth_test)
app.router.add_post("/api/views.open", views_open)
app.router.add_post("/api/chat.postMessage", chat_postMessage)
app.router.add_post("/api/chat.update", chat_update)

if __name__ == "__main__":
    print("Mock Slack API server starting on http://localhost:8888")
    web.run_app(app, host="0.0.0.0", port=8888)