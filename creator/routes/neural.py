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

Two more are about a finished file rather than about this machine, and they
are the comparison the viewer is built on:

- `of` reads what a render's own embedded prompt says about the refiner.
- `twin` puts that prompt back on the queue with the refiner the other way
  round. See `neuraltwin.py` for why that costs the save and not the render.

`extract` is a plain handler on the thread pool rather than a queued job: it
is a few seconds of CPU over a 100 MB file, wants no GPU, and a queue item
waiting behind a render to run a hash would be waiting for nothing it needs.
It holds its own lock so two presses cannot write one file.
"""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import neural, neuraltwin, settings


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


# ---- the other version of a render -------------------------------------------


@PromptServer.instance.routes.get("/continuity/neural/of")
async def neural_of(request):
    """What one finished file says about the refiner. -> `neuraltwin.read`.

    A file with no prompt in it — footage, a photo, a render saved under
    `--disable-metadata` — answers `{"ours": false}` with a 200 rather than an
    error. It is an ordinary file that simply has no other version, and the
    surface that asked has something else to offer it.
    """
    from ..server_routes import _input_path, _read_embedded

    path = _input_path(request)
    if path is None:
        return web.json_response({"error": "not in the input or output folder"}, status=404)
    loop = asyncio.get_running_loop()
    try:
        embedded = await loop.run_in_executor(None, _read_embedded, path,
                                              ("prompt", neuraltwin.PRODUCER_KEY))
    except Exception as exc:  # noqa: BLE001 — an unreadable file has no answer, not an error
        return web.json_response({"ours": False, "on": False, "settings": None,
                                  "node": None, "error": str(exc)})
    return web.json_response(neuraltwin.read(embedded.get("prompt"),
                                            embedded.get(neuraltwin.PRODUCER_KEY)))


@PromptServer.instance.routes.post("/continuity/neural/twin")
async def neural_twin(request):
    """Queue this render again with the refiner the other way round.

    The same four steps `jobs.submit` takes and `server.post_prompt` takes
    before it — mint an id, validate, enqueue, hand the id back — because this
    is the same thing arriving by a third door. It is not a `jobs` item: those
    wrap one `ContinuityJob` node, and what goes on the queue here is the
    user's own prompt, which is the whole point. Cancel, the progress bar and
    the queue count all reach it for the same reason they reach a render.

    The client waits for `executed` carrying this `prompt_id`.
    """
    import execution
    import uuid

    from ..server_routes import _read_embedded

    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)

    filename = str(body.get("filename") or "")
    try:
        from .. import media

        path = media.resolve(filename)
    except Exception as exc:  # noqa: BLE001 — a path that is not ours
        return web.json_response({"error": str(exc)}, status=404)

    loop = asyncio.get_running_loop()
    embedded = await loop.run_in_executor(None, _read_embedded, path,
                                          ("prompt", neuraltwin.PRODUCER_KEY))
    try:
        producer = embedded.get(neuraltwin.PRODUCER_KEY)
        info = neuraltwin.read(embedded.get("prompt"), producer)
        prompt = neuraltwin.twin(embedded.get("prompt"), bool(body.get("on")),
                                 body.get("block") if isinstance(body.get("block"), dict) else None,
                                 producer=producer)
    except neuraltwin.TwinError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    prompt_id = str(uuid.uuid4())
    valid = await execution.validate_prompt(prompt_id, prompt, None)
    if not valid[0]:
        # The prompt in the file no longer validates on this install — a node it
        # names is gone, or a file it loads has been moved. That is a sentence
        # the user can act on, unlike the two above.
        return web.json_response({"error": f"that render will not queue here: {valid[1]}"},
                                 status=400)
    server = PromptServer.instance
    number = server.number
    server.number += 1
    client_id = body.get("client_id")
    extra_data = {"client_id": client_id} if client_id else {}
    server.prompt_queue.put((number, prompt_id, prompt, extra_data, valid[2], {}))
    # Which output is the twin: the producer's, where the file names one. An
    # older file leaves it to the viewer, which takes the first of ours.
    return web.json_response({"prompt_id": prompt_id,
                              "node": info["node"] if producer is not None else None,
                              "index": info.get("index", 0)})
