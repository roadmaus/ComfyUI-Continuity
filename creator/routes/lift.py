"""`/continuity/lift/*`: the image-to-3D tool, served.

Two routes. `models` says which of the eight files this machine has, so the tool
can name what is missing (and where to get it) before anybody presses Build and
waits for a loader to fail three stages in. `run` validates a request, builds
the graph (`lift.py`) and queues it — answering with the prompt id and the plan
the frontend reads the wire back with, never with the mesh: that arrives stage
by stage on `executed`, which is the whole reason this is a graph on the queue.
"""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import jobs, lift, media
from ..guard import same_origin


@PromptServer.instance.routes.get("/continuity/lift/models")
async def list_models(request):
    loop = asyncio.get_running_loop()
    return web.json_response({"models": await loop.run_in_executor(None, lift.catalogue)})


def _has_alpha(path):
    """Whether a picture carries a cut-out of its own — an alpha channel with
    something actually transparent in it. A PNG saved with an opaque alpha is
    common and would crop to the whole frame."""
    from PIL import Image

    with Image.open(path) as picture:
        if picture.mode not in ("RGBA", "LA", "PA") and "transparency" not in picture.info:
            return False
        return picture.convert("RGBA").getchannel("A").getextrema()[0] < 250


@PromptServer.instance.routes.post("/continuity/lift/run")
@same_origin
async def run_lift(request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    try:
        settings = lift.spec(body)
    except lift.LiftError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    loop = asyncio.get_running_loop()
    for side, filename in settings["views"].items():
        try:
            path = media.resolve(filename)
        except media.MediaError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        if settings["background"] == "keep" and not await loop.run_in_executor(None, _has_alpha, path):
            return web.json_response({
                "error": f"the {side} picture has no transparency to cut out along — "
                         "let the tool remove the background"}, status=400)

    models = await loop.run_in_executor(None, lift.catalogue)
    absent = lift.missing(settings, models)
    if absent:
        names = ", ".join(f"{entry['folder']}/{entry['file']}" for entry in absent)
        return web.json_response({"error": f"missing {names}", "missing": absent}, status=400)

    prompt, plan = lift.build(settings, models)
    try:
        prompt_id = await jobs.enqueue(prompt, body.get("client_id"))
    except jobs.JobError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"prompt_id": prompt_id, "plan": plan, "name": settings["name"]})
