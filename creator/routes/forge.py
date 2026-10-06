"""`/continuity/forge/*`: Game Forge, served.

The routes are not written out here one by one: they are `forge/api.py`'s
`ROUTES`, registered in a loop, so the list the CLI is held against is the list
that is served (spec §11.6), with `TAB_ROUTES` beside it: the half of a pose
job a browser tab calls. This module is only the aiohttp half — reading the
request, running the handler off the event loop, and answering with JSON, a
refusal, or a file.

Every handler does disk work, so each runs on the executor. Every POST goes
through `same_origin`, like every other route in the pack that writes.
"""

import asyncio
import json
import os

import folder_paths
from aiohttp import web
from server import PromptServer

from .. import media, outputs
from ..families import registry
from ..forge import api
from ..guard import same_origin


def _resolve(filename):
    return media.resolve(filename)


def _families():
    return [{"id": family, "still": family in registry.STILL_ARCHES.values()}
            for family in registry.FAMILIES]


def _tabs():
    return len(PromptServer.instance.sockets)


def _announce(event, data):
    # No sid: every tab hears it, and the first to claim the job does it.
    PromptServer.instance.send_sync(event, data)


def _host():
    base = os.path.join(folder_paths.get_output_directory(), *outputs.FORGE.split("/"))
    return api.Host(base, _resolve, _families, _tabs, _announce)


async def _answer(method, path, params):
    loop = asyncio.get_running_loop()
    status, answer = await loop.run_in_executor(None, api.call, _host(), method, path, params)
    if isinstance(answer, api.File):
        return web.FileResponse(answer.path)
    return web.json_response(answer, status=status)


def _register(method, path):
    if method == "GET":
        @PromptServer.instance.routes.get(path)
        async def handle_get(request):
            return await _answer("GET", path, dict(request.query))
        return

    @PromptServer.instance.routes.post(path)
    @same_origin
    async def handle_post(request):
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response({"problem": "expected a JSON body", "code": "request.json"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"problem": "the request body must be a JSON object",
                                      "code": "request.json"}, status=400)
        return await _answer("POST", path, body)


for _method, _path, _ in api.ROUTES + api.TAB_ROUTES:
    _register(_method, api.PREFIX + _path)
