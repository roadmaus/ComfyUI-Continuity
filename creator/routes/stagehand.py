"""`/continuity/stagehand`: one exchange between the blockout's agent and its model."""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import stagehand
from ..families import refine
from ..guard import same_origin


@PromptServer.instance.routes.post("/continuity/stagehand")
@same_origin
async def take_turn(request):
    """`{session, model, messages, tools, seen}` -> the server's reply."""
    try:
        body = await request.json()
        args = (str(body["session"]), str(body["model"]), body["messages"], body["tools"], int(body["seen"]))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, stagehand.turn, *args)
    except (refine.RefineError, ValueError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(answer)
