"""`/continuity/stagehand`: one exchange between the blockout's agent and its
model, and the Stop under it."""

import asyncio
import base64
import io
import json

from aiohttp import web
from server import PromptServer

from .. import jobs, models as core_models, refine_local, stagehand
from ..families import refine
from ..guard import same_origin


def _picture(url):
    """A `data:` URL -> the tensor the model in ComfyUI is shown."""
    from PIL import Image

    return refine_local.to_tensor(Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))))


def _local(body):
    """One exchange on the model in ComfyUI. -> the reply, as a server gives one.

    The device is followed, and refused in the chat's words when it is gone.
    The seed is new every exchange and the temperature the chat's cold one.
    """
    device = str(body.get("device") or "").strip()
    if device and device not in core_models.device_options():
        raise refine.RefineError(f"the selected local LLM device '{device}' is no longer available")

    def write(system, turns):
        return refine_local.converse(
            body["model"], system, [(turn["role"], turn["text"], len(turn["images"])) for turn in turns],
            [_picture(url) for turn in turns for url in turn["images"]],
            temperature=stagehand.FENCED_TEMPERATURE, seed=-1, max_tokens=stagehand.FENCED_TOKENS,
            **({"device": device} if device else {}))

    return stagehand.turn(body["session"], body["model"], body["messages"], body["tools"], int(body["seen"]),
                          backend="local", write=write)


def _job(body):
    """`_local` on the queue: it waits behind a render, a render waits behind
    it, the bar is the real one and Cancel reaches it. See `creator/jobs.py`."""
    try:
        return _local(body)
    except (refine.RefineError, ValueError) as problem:
        raise jobs.JobError(str(problem)) from problem


jobs.register("stagehand", _job)


@PromptServer.instance.routes.post("/continuity/stagehand")
@same_origin
async def take_turn(request):
    """`{session, backend, model, device, eject, messages, tools, seen, client_id}`
    -> an id, and the reply on the socket.

    As a chat turn is answered, and for its reasons (`jobs.py`). A server is off
    the queue: `{"answer_id": id}`, and the reply as `mmc_answer`, since a model
    building a set outlasts the frontend's fetch. A model in ComfyUI is GPU
    work and a job on ComfyUI's own queue: `{"prompt_id": id}`, and the same
    reply on `executed`.
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
    if backend != "remote":
        try:
            prompt_id = await jobs.submit("stagehand", {**body, "session": session, "model": model},
                                          body.get("client_id"))
        except jobs.JobError as problem:
            return web.json_response({"error": str(problem)}, status=500)
        return web.json_response({"prompt_id": prompt_id})
    answer_id = jobs.answer_later(
        lambda: stagehand.turn(session, model, messages, tools, seen, backend=backend,
                               eject=body.get("eject") is True),
        body.get("client_id"), (refine.RefineError, ValueError))
    return web.json_response({"answer_id": answer_id})


@PromptServer.instance.routes.post("/continuity/stagehand/stop")
@same_origin
async def stop(request):
    """`{session}` -> `{"stopped": whether an exchange was out}`.

    For a server: its connection is closed. A job in ComfyUI is cancelled by
    the browser the way ComfyUI's own Cancel cancels it, by its prompt id.
    """
    try:
        session = str((await request.json())["session"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    # Off the loop: dropping the model is a call to the server.
    stopped = await asyncio.get_running_loop().run_in_executor(None, stagehand.stop, session)
    return web.json_response({"stopped": stopped})
