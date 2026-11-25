"""`/continuity/stagehand`: one exchange between the blockout's agent and its
model, and the Stop under it."""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import jobs, stagehand
from ..families import refine
from ..guard import same_origin


@PromptServer.instance.routes.post("/continuity/stagehand")
@same_origin
async def take_turn(request):
    """`{session, backend, model, device, eject, messages, tools, seen, client_id}`
    -> `{"answer_id": id}`, and the server's reply on the socket as `mmc_answer`.

    Off the queue and not inside this request, as a chat turn on a server is: a
    model building a set outlasts the frontend's fetch (`jobs.answer_later`).
    """
    try:
        body = await request.json()
        session, model = str(body["session"]), str(body.get("model") or "")
        backend = "remote" if body.get("backend") == "remote" else "local"
        messages, tools, seen = body["messages"], body["tools"], int(body["seen"])
        if not isinstance(messages, list) or not isinstance(tools, list):
            raise TypeError
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    refused = "" if stagehand.SESSION.fullmatch(session) else "bad session id"
    refused = refused or stagehand.refusal(backend, model)
    if refused:
        return web.json_response({"error": refused}, status=400)
    answer_id = jobs.answer_later(
        lambda: stagehand.turn(session, model, messages, tools, seen, backend=backend,
                               eject=body.get("eject") is True),
        body.get("client_id"), (refine.RefineError, ValueError))
    return web.json_response({"answer_id": answer_id})


@PromptServer.instance.routes.post("/continuity/stagehand/stop")
@same_origin
async def stop(request):
    """`{session}` -> `{"stopped": whether an exchange was out}`."""
    try:
        session = str((await request.json())["session"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    # Off the loop: dropping the model is a call to the server.
    stopped = await asyncio.get_running_loop().run_in_executor(None, stagehand.stop, session)
    return web.json_response({"stopped": stopped})
