"""`/continuity/control/*`: the tracing bench, served.

Three routes and no state. The catalogue says what can be traced; the preview
draws one frame with the current settings; the run writes the whole file into
the input folder and answers with its name.

**The preview is a GET on purpose.** It is set as an `<img src>` while a slider
is moving, which means the browser gets to coalesce, abort and cache it the way
it does every other picture on the page — none of which a POST would give it.
The parameters ride in the query string for the same reason: the URL *is* the
cache key, so a threshold dragged back to where it was redraws from memory.

Everything that touches media runs in a thread. A tracing is arithmetic over a
frame and a run is arithmetic over every frame of a clip, and the event loop
this is on is the one carrying the prompt queue and the progress socket.
"""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import control, jobs, media

# The preview is asked for on every drag of a slider and the answer is a picture.
# Long enough that dragging back and forth is free, short enough that a source
# file replaced under the same name is not still on screen a session later.
CACHE = "private, max-age=120"


@PromptServer.instance.routes.get("/continuity/control/tracings")
async def list_tracings(request):
    return web.json_response(control.catalogue())


def _values(query):
    """The slider values out of a query string.

    Everything arrives as a string and `control._params` already clamps and
    defaults against the spec, so this only has to hand over the pairs — which
    is why there is no per-key parsing here and should not be.
    """
    return {key: value for key, value in query.items()
            if key not in ("filename", "op", "at")}


@PromptServer.instance.routes.get("/continuity/control/preview")
async def preview_frame(request):
    """One frame of the source, traced, as a PNG.

    Gated rather than queued. A preview is asked for on every drag of a slider
    and the browser's coalescing is what makes that feel like a control, so one
    queue item per drag position would replay the whole drag once the render
    ahead of it finished. The surface holds the `src` while the queue is busy;
    this 409 is what stands under that for the tab that has not heard yet.
    """
    refused = jobs.refuse_if_busy()
    if refused is not None:
        return refused
    filename = request.query.get("filename", "")
    op = request.query.get("op", "as_shot")
    try:
        at = max(0.0, float(request.query.get("at", 0) or 0))
    except ValueError:
        at = 0.0
    try:
        path = media.resolve(filename)
    except media.MediaError as exc:
        return web.json_response({"error": str(exc)}, status=404)
    try:
        loop = asyncio.get_running_loop()
        png, _ = await loop.run_in_executor(
            None, control.preview, path, op, _values(request.query), at)
    except control.ControlError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001 — an unreadable source is the caller's problem
        return web.json_response({"error": str(exc)}, status=500)
    return web.Response(body=png, content_type="image/png", headers={"Cache-Control": CACHE})


def _run_job(body):
    """One tracing, on the queue. See `creator/jobs.py`."""
    return control.run(body.get("filename", ""), body.get("op", "as_shot"),
                       body.get("params") or {}, body.get("trim"),
                       bool(body.get("keep_sound")), jobs.progress(),
                       body.get("at"))


jobs.register("control", _run_job)


@PromptServer.instance.routes.post("/continuity/control/run")
async def run_tracing(request):
    """Trace the whole file and put the result in the input folder.

    Queued rather than run here. Every tracing worth waiting for is a model over
    every frame of a clip, and this used to go onto a thread pool beside the
    prompt queue rather than into it — so a Trace pressed during a render put a
    second model on the same GPU. It is a job now: `jobs.submit` answers with a
    `prompt_id`, ComfyUI's Cancel reaches it, its progress is on the real bar,
    and the client picks the result up off `executed`.

    What did not move is the validation below. A trim that ends before it starts
    is knowable now and is worth a 400 with a sentence in it, where the same
    thing discovered inside a queued job would be an error dialog a minute later.
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

    # One frame of a clip as a still, rather than the cut as a clip. The bench
    # sends this when the door being pressed takes a picture and the source is
    # footage — see `control.run`.
    at = body.get("at")
    if at is not None:
        try:
            at = max(0.0, float(at))
        except (TypeError, ValueError):
            return web.json_response({"error": "at must be a mark in seconds"}, status=400)

    try:
        prompt_id = await jobs.submit("control", {
            "filename": body.get("filename", ""),
            "op": body.get("op", "as_shot"),
            "params": body.get("params") or {},
            "trim": list(trim) if trim else None,
            "keep_sound": bool(body.get("keep_sound")),
            "at": at,
        }, body.get("client_id"))
    except jobs.JobError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"prompt_id": prompt_id})
