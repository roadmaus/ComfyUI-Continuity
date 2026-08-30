"""`/continuity/upscale/*`: the upscale bench, served.

The same three routes as the tracing bench and the same reasons for their
shapes — the catalogue says what this machine can do, the preview draws one tile
with the current dials, the run writes the whole file and answers with where it
landed. `routes/control.py` is worth reading for the argument behind the GET.

Two things differ, and both come from what an upscale *is*.

The preview is a tile rather than a frame, so it carries a centre as well as a
mark: which part of the picture is being judged is a thing the person judging
moves around. And `plain` asks for the same tile with no model in it, which is
what the surface holds the backend against.

The run answers with a path under the *output* folder. A tracing is an
ingredient and lands in `input/` for a render to reference; this is the finished
file and lands on a shelf beside the renders, so the answer names its root.
"""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import jobs, media, upscale

# The preview is asked for whenever a dial or the centre moves and the answer is
# a picture — long enough that going back to a setting is free, short enough
# that a source replaced under the same name is not still on screen later.
CACHE = "private, max-age=120"


@PromptServer.instance.routes.get("/continuity/upscale/backends")
async def list_backends(request):
    loop = asyncio.get_running_loop()
    return web.json_response(await loop.run_in_executor(None, upscale.catalogue))


def _values(query):
    """The dial values out of a query string.

    Everything arrives as a string and `upscale._params` already clamps and
    defaults against the spec, so this only has to hand over the pairs that are
    not the request's own.
    """
    return {key: value for key, value in query.items()
            if key not in ("filename", "op", "at", "cx", "cy", "plain")}


def _number(query, key, fallback=0.0):
    try:
        return float(query.get(key, fallback) or fallback)
    except (TypeError, ValueError):
        return fallback


@PromptServer.instance.routes.get("/continuity/upscale/preview")
async def preview_tile(request):
    """One tile of the source, upscaled, as a PNG.

    Gated while the queue is busy rather than queued behind it — see the same
    route in `routes/control.py` for why a slider's previews must not become
    queue items.
    """
    refused = jobs.refuse_if_busy()
    if refused is not None:
        return refused
    filename = request.query.get("filename", "")
    op = request.query.get("op", "sharpen")
    at = max(0.0, _number(request.query, "at"))
    centre = (_number(request.query, "cx", 0.5), _number(request.query, "cy", 0.5))
    plain = str(request.query.get("plain", "")).lower() in ("1", "true", "yes", "on")
    try:
        path = media.resolve(filename)
    except media.MediaError as exc:
        return web.json_response({"error": str(exc)}, status=404)
    try:
        loop = asyncio.get_running_loop()
        png, _ = await loop.run_in_executor(
            None, upscale.preview, path, op, _values(request.query), at, centre, plain)
    except upscale.UpscaleError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001 — an unreadable source is the caller's problem
        return web.json_response({"error": str(exc)}, status=500)
    return web.Response(body=png, content_type="image/png", headers={"Cache-Control": CACHE})


def _run_job(body):
    """One upscale, on the queue. See `creator/jobs.py`."""
    return upscale.run(body.get("filename", ""), body.get("op", "sharpen"),
                       body.get("params") or {}, body.get("trim"),
                       bool(body.get("keep_sound", True)), jobs.progress(),
                       body.get("at"))


jobs.register("upscale", _run_job)


@PromptServer.instance.routes.post("/continuity/upscale/run")
async def run_upscale(request):
    """Upscale the whole file and put the result on the shelf.

    Queued, for the reasons `routes/control.py` gives — and more so here, since
    a Restore is a sampler and a VAE and was the heaviest thing in this pack
    that ran beside the prompt queue instead of in it.

    The validation stays: it is knowable now, and a sentence under the button
    beats an error dialog once the queue reaches the job.
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)

    trim = body.get("trim")
    if trim is not None:
        try:
            trim = (max(0.0, float(trim["start"])), float(trim["end"]))
        except (KeyError, TypeError, ValueError):
            return web.json_response({"error": "trim must be {start, end} in seconds"}, status=400)
        if trim[1] <= trim[0]:
            return web.json_response({"error": "a cut has to end after it starts"}, status=400)

    # One frame of a clip as a still, rather than the cut as a clip.
    at = body.get("at")
    if at is not None:
        try:
            at = max(0.0, float(at))
        except (TypeError, ValueError):
            return web.json_response({"error": "at must be a mark in seconds"}, status=400)

    try:
        prompt_id = await jobs.submit("upscale", {
            "filename": body.get("filename", ""),
            "op": body.get("op", "sharpen"),
            "params": body.get("params") or {},
            "trim": list(trim) if trim else None,
            "keep_sound": bool(body.get("keep_sound", True)),
            "at": at,
        }, body.get("client_id"))
    except jobs.JobError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"prompt_id": prompt_id})
