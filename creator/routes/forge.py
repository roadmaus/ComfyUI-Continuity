"""`/continuity/forge/*`: Game Forge, served.

The routes are not written out here one by one: they are `forge/api.py`'s
`ROUTES`, registered in a loop, so the list the CLI is held against is the list
that is served (spec §11.6), with `TAB_ROUTES` beside it: the half of a pose
job a browser tab calls. This module is only the aiohttp half — reading the
request, running the handler off the event loop, and answering with JSON, a
refusal, or a file.

Every handler does disk work, so each runs on the executor. Every POST goes
through `same_origin`, like every other route in the pack that writes.

A make renders through `/continuity/render`'s own builder (`render._render`),
so a forge asset is built, weighted and refused exactly like a scripted still;
the prompt goes on the queue from the executor thread by handing `jobs.enqueue`
back to the server's loop.
"""

import asyncio
import json
import os

import folder_paths
from aiohttp import web
from server import PromptServer

from .. import chat, headless, jobs, media, outputs, server_routes
from ..families import manifest, registry
from ..forge import api
from ..forge.problems import ForgeError
from ..guard import same_origin
from . import render as rendering


def _resolve(filename):
    return media.resolve(filename)


def _families():
    """Every family; a still one with the canvas a make picks its shape from."""
    out = []
    for family in registry.FAMILIES:
        entry = {"id": family, "still": family in registry.STILL_ARCHES.values()}
        if entry["still"]:
            canvas = manifest.describe(family).get("canvas") or {}
            entry["canvas"] = {k: canvas[k] for k in ("aspects", "min_short_edge", "max_short_edge")
                               if k in canvas}
        out.append(entry)
    return out


def _render(body):
    """One render request, built and queued. Runs on the executor."""
    try:
        built = rendering._render(body)
    except (headless.HeadlessError, chat.ActionError, *server_routes.COMPILE_FAILURES) as problem:
        raise ForgeError(str(problem), "make.refused") from None
    if "problem" in built:
        raise ForgeError(built["problem"], "make.refused")
    try:
        prompt_id = asyncio.run_coroutine_threadsafe(jobs.enqueue(built["prompt"]),
                                                     PromptServer.instance.loop).result()
    except jobs.JobError as problem:
        raise ForgeError(str(problem), "make.queue") from None
    return {"prompt_id": prompt_id, "speed": built["speed"]}


def _prompt_state(prompt_id):
    queue = PromptServer.instance.prompt_queue
    running, pending = queue.get_current_queue_volatile()
    if any(item[1] == prompt_id for item in running):
        return "running", None
    if any(item[1] == prompt_id for item in pending):
        return "queued", None
    record = queue.get_history(prompt_id=prompt_id).get(prompt_id)
    if record is None:
        return "unknown", None
    status = record.get("status") or {}
    if status.get("status_str") != "error":
        return "done", None
    for event, data in status.get("messages") or []:
        if event == "execution_error":
            return "failed", f"{data.get('node_type')}: {data.get('exception_message', '').strip()}"
        if event == "execution_interrupted":
            return "failed", "the render was cancelled"
    return "failed", "the render failed"


def _tabs():
    return len(PromptServer.instance.sockets)


def _announce(event, data):
    # No sid: every tab hears it, and the first to claim the job does it.
    PromptServer.instance.send_sync(event, data)


def _host():
    base = os.path.join(folder_paths.get_output_directory(), *outputs.FORGE.split("/"))
    return api.Host(base, _resolve, _families, _tabs, _announce, _render, _prompt_state)


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
