"""`/continuity/blockout/*`: the blockout bench, served.

Two routes, and neither is a job. The other benches queue their runs because a
run is a model on the GPU; a blockout's run happened in the browser — the
frames arrive already drawn — and all the server does is hold them and then
encode them, which is CPU work the render queue should never make wait (see
`creator/blockout.py` for the whole argument). The still path has no route
here at all: one frame goes through core's own `/upload/image`.

`frames` takes a multipart batch against a token the client minted; `write`
turns whatever is staged under that token into an mp4 in the input folder.
The validation lives here, the way it does in the other route modules: a bad
token or a frameless write is knowable now and worth a sentence, where the
same thing discovered inside the encoder would be a stack trace.
"""

import asyncio
import json

from aiohttp import web
from server import PromptServer

from .. import blockout

# One request's worth of frames. Generous against the batches the bench
# actually sends (two dozen 720p PNGs), tight against the route being a place
# to park arbitrary bytes.
MOST_BATCH_BYTES = 256 * 1024 * 1024


@PromptServer.instance.routes.post("/continuity/blockout/frames")
async def take_frames(request):
    """A batch of rendered frames into staging. -> `{held}`.

    Multipart rather than JSON, because the frames are PNG bytes and base64
    would grow every batch by a third for nothing. Each part's name is the
    frame's index, so batches commute and a retry overwrites.
    """
    if request.content_length and request.content_length > MOST_BATCH_BYTES:
        return web.json_response({"error": "that batch is too large"}, status=413)
    token = ""
    frames = []
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name == "token":
                token = (await part.text()).strip()
                continue
            try:
                index = int(part.name or "")
            except (TypeError, ValueError):
                continue
            frames.append((index, await part.read(decode=False)))
    except Exception:  # noqa: BLE001 — a malformed body is the caller's problem
        return web.json_response({"error": "expected a multipart body of frames"}, status=400)
    if not frames:
        return web.json_response({"error": "the batch carried no frames"}, status=400)
    try:
        loop = asyncio.get_running_loop()
        held = await loop.run_in_executor(None, blockout.take_frames, token, frames)
    except blockout.BlockoutError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"held": held})


@PromptServer.instance.routes.post("/continuity/blockout/write")
async def write_clip(request):
    """Encode the staged frames into the input folder. -> `{path, kind}`."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    scene = body.get("scene")
    if scene is not None and not isinstance(scene, dict):
        return web.json_response({"error": "the scene has to be an object"}, status=400)
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None, blockout.write,
            body.get("token", ""), body.get("fps", 24), body.get("op", "guide"), scene)
    except blockout.BlockoutError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001 — an encoder failure is worth the sentence
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response(answer)
