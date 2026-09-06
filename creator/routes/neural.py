"""`/continuity/neural/*`: the DLSS 5 refiner's diagnostic surface.

Four small routes, and they exist because of the support tail `neural.py`
predicts: getting the weights means the user finding their own DLL, and every
question that raises — is it the right file, did the extraction work, where
did it land — should be answerable from the settings page without opening an
issue.

- `status` says where things stand: weights, and the last DLL path.
- `check` hashes a DLL path and says whether it is the supported build.
- `extract` runs upstream's tool over it into `models/dlss/`.
- `estimate` is the memory arithmetic, for a surface that wants to print it.

`extract` is a plain handler on the thread pool rather than a queued job: it
is a few seconds of CPU over a 100 MB file, wants no GPU, and a queue item
waiting behind a render to run a hash would be waiting for nothing it needs.
It holds its own lock so two presses cannot write one file.
"""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import neural, settings


def _number(query, key, fallback):
    try:
        return float(query.get(key, fallback) or fallback)
    except (TypeError, ValueError):
        return fallback


@PromptServer.instance.routes.get("/continuity/neural/status")
async def neural_status(request):
    loop = asyncio.get_running_loop()
    dll = settings.neural_dll()
    state = await loop.run_in_executor(None, neural.status, dll or None)
    state["dll_path"] = dll
    return web.json_response(state)


@PromptServer.instance.routes.post("/continuity/neural/check")
async def neural_check(request):
    """Hash a DLL and remember its path. -> `check_dll`'s answer.

    Remembered whether or not it is the right file: the path is what the page
    shows next time, and a wrong file the user is about to replace is still
    the folder they were looking in.
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    path = str(body.get("path") or "").strip()
    loop = asyncio.get_running_loop()
    checked = await loop.run_in_executor(None, neural.check_dll, path)
    try:
        settings.save({"neural_dll": path})
    except (ValueError, OSError):
        pass
    return web.json_response(checked)


@PromptServer.instance.routes.post("/continuity/neural/extract")
async def neural_extract(request):
    """Run the extraction. -> the status afterwards, or the sentence that stopped it."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    path = str(body.get("path") or settings.neural_dll() or "").strip()
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, neural.extract, path)
    except neural.NeuralError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001 — the tool's own failure, as a sentence
        return web.json_response({"error": str(exc)}, status=500)
    # A pipeline loaded off the previous file would keep answering with it.
    neural.unload()
    state = await loop.run_in_executor(None, neural.status, path)
    state["dll_path"] = path
    return web.json_response(state)


@PromptServer.instance.routes.get("/continuity/neural/estimate")
async def neural_estimate(request):
    width = int(_number(request.query, "width", 0))
    height = int(_number(request.query, "height", 0))
    if width <= 0 or height <= 0:
        return web.json_response({"error": "width and height are needed"}, status=400)
    scale = _number(request.query, "scale", 1.0)
    precision = request.query.get("precision", neural.DEFAULT_PRECISION)
    if precision not in neural.PRECISIONS:
        precision = neural.DEFAULT_PRECISION
    return web.json_response(neural.estimate(width, height, scale, precision))
