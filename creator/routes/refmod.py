"""The RefMod routes: make one, and handle the file it is.

`/continuity/refmod/make` is a job (`creator/jobs.py`): encoding through the
H3 VAE is GPU work and goes on the queue behind whatever is rendering, with
Cancel and the real progress bar. The result is the picker rows of what was
written, so the caller can attach them without a second listing. Two shapes
of result: one mod per picture (`compressed` / `full`), or — `stack` — every
still and clip handed in as one `video`-kind file, which is what the sibling
pack means by a character (see `refmod.stack`).

The rest are the file itself, and none of them touch a tensor: `file` hands
the .safetensors out, `upload` takes one in, `move` renames it, `delete`
removes it, `describe` rewrites the one header field worth editing. They exist
because a RefMod is a character somebody carries between machines and packs —
the sibling pack's README ships one as a download — and a folder you can only
reach over ssh is not a library.

The listing needs no route of its own: `/continuity/assets?root=refmods` lists
mods and `/continuity/thumb` serves their pictures (`server_routes`).
"""

import asyncio
import json
import logging
import os
import tempfile

from aiohttp import web
from server import PromptServer

from .. import jobs, media, refmod

log = logging.getLogger(__name__)

# What a full mod is encoded at when the caller does not say: the sibling
# pack's own default, a 64x64 latent for a square picture. Core's reference
# path goes to 2048 — `edge` reaches it, at four times the tokens.
DEFAULT_EDGE = 1024
# How far a compressed still is pooled. Measured 2026-09-12 on one portrait
# against the picture itself as a reference, same seed: the sibling pack's
# 16-grid (48 tokens for a 3:4 still) rendered the man with red and blue
# stains on his face, 32 (192 tokens) held the face but kept the fringing,
# 48 (432 tokens) was clean and indistinguishable from the full mod. So a
# still pools no further than about 1.75x — "compressed" is under half the
# tokens, not a sixteenth — and the refinement steps make no difference to
# any of it (150 and 500 wrote the same bytes).
DEFAULT_GRID = 48
# A stack keeps the sibling pack's square 16, the grid their own example is
# built on: their word for a character is concept and motion, not a face.
STACK_GRID = 16
DEFAULT_STEPS = 150
MAX_STEPS = 2000
# A stack: how much of a clip is read, how many of its frames are encoded, and
# the token cap the whole file is fitted under — the sibling pack's default.
# 22 source frames is the largest count under two dozen that core's reference
# path takes whole (n % 17 == 5), and it lands as six latent frames.
STACK_SECONDS = 8
STACK_FRAMES = 22
STACK_MAX_TOKENS = 5120


def _steps(body):
    """Refinement steps, where 0 is a real answer (pool only) and only an
    absent field means the default — `or` would turn 0 into 150."""
    value = body.get("steps")
    return DEFAULT_STEPS if value in (None, "") else int(value)


def _vae(name):
    """Core's own VAE loader, so the encode is the one a render would do."""
    import nodes

    if not name:
        raise jobs.JobError("pick the H3 video VAE in the node's weights control first")
    loader = nodes.NODE_CLASS_MAPPINGS["VAELoader"]()
    return loader.load_vae(name)[0]


def _encode(vae, image, edge):
    """One still -> its full latent, sized the way `encode.encode_image` sizes a
    `max` reference but to `edge` rather than core's 2048."""
    from comfy_extras.nodes_minimax_h3 import _resize
    from ..families.h3.encode import _snap

    height, width = image.shape[1], image.shape[2]
    scale = min(1.0, edge / min(width, height))
    target_w, target_h = _snap(width * scale), _snap(height * scale)
    resized = _resize(image, target_w, target_h, "disabled")
    return vae.encode(resized), resized


def _frames(source, count):
    """`count` frames of a clip, spread evenly over its first seconds, trimmed
    to a run core's reference path encodes whole (n % 17 == 5)."""
    frames, _ = media.load_video(source, max_seconds=STACK_SECONDS)
    if frames.shape[0] > count:
        import torch
        picks = torch.linspace(0, frames.shape[0] - 1, count).round().long()
        frames = frames[picks]
    n = frames.shape[0]
    while n >= 5 and n % 17 != 5:
        n -= 1
    if n < 5:
        raise jobs.JobError(f"{source} is too short to stack — five frames at least")
    return frames[:n]


def _run_stack(body, sources):
    """Every source into one file: a `video`-kind mod whose frames are the
    sources laid end to end, each pooled to one square grid. See `refmod.stack`."""
    name = refmod.name_of(refmod.SCHEME + str(body.get("name") or ""))
    subfolder = str(body.get("subfolder") or "").strip().strip("/")
    edge = max(256, min(4096, int(body.get("edge") or DEFAULT_EDGE)))
    grid = max(4, min(64, int(body.get("grid") or STACK_GRID)))
    steps = max(0, min(MAX_STEPS, _steps(body)))
    max_tokens = max(0, int(body.get("max_tokens", STACK_MAX_TOKENS) or 0))
    frames = max(5, min(200, int(body.get("frames") or STACK_FRAMES)))
    tell = jobs.progress()

    vae = _vae(str(body.get("vae") or ""))
    latents, shapes, first = [], [], None
    stills = clips = 0
    for index, source in enumerate(sources):
        # A still or a clip, by what core makes of the name — the same call the
        # listing classifies files with.
        import folder_paths
        if folder_paths.filter_files_content_types([source.rsplit("/", 1)[-1]], ["video"]):
            image = _frames(source, frames)
            clips += 1
        else:
            image = media.load_image(source)
            stills += 1
        latent, resized = _encode(vae, image, min(edge, 768) if image.shape[0] > 1 else edge)
        latent = latent.detach().float().cpu()
        latents.append(latent)
        shapes.append("x".join(str(v) for v in latent.shape[2:]))
        if first is None:
            first = resized[0]
        tell(0.3 * (index + 1) / len(sources))
    stacked, kept = refmod.stack(latents, grid, steps, max_tokens=max_tokens,
                                 tell=lambda f: tell(0.3 + 0.7 * f))
    target = f"{subfolder}/{name}" if subfolder else name
    path = refmod.save(target, stacked, {
        "kind": "video", "mode": "training", "source": "stack",
        "source_shape": " +".join(shapes),
        "pool": "x".join(str(v) for v in stacked.shape[2:]),
        "optimize_steps": steps,
        "tags": [f"{stills} img, {clips} vid"],
        "description": str(body.get("description") or ""),
        "concept_type": str(body.get("concept") or "generic"),
        "source_file": ", ".join(s.rsplit("/", 1)[-1] for s in sources),
    }, preview=first)
    row = refmod.row_for(path, target)
    row["sources"] = sources
    row["kept"] = kept
    log.info("[Continuity] stacked %d sources as %s (%d frames, %d tokens)",
             len(sources), target, stacked.shape[2], row["tokens"])
    return {"mods": [row]}


def _run_job(body):
    """Every source in `body["sources"]` becomes one mod — or, `stack`, all of
    them become one. See the module note."""
    sources = [str(s) for s in (body.get("sources") or []) if s]
    if not sources:
        raise jobs.JobError("nothing to keep — the member has no pictures attached")
    if body.get("mode") == "stack":
        return _run_stack(body, sources)
    name = refmod.name_of(refmod.SCHEME + str(body.get("name") or ""))
    subfolder = str(body.get("subfolder") or "").strip().strip("/")
    mode = "training" if body.get("mode") == "compressed" else "encode"
    edge = max(256, min(4096, int(body.get("edge") or DEFAULT_EDGE)))
    grid = max(4, min(64, int(body.get("grid") or DEFAULT_GRID)))
    steps = max(0, min(MAX_STEPS, _steps(body)))
    description = str(body.get("description") or "")
    concept = str(body.get("concept") or "generic")
    tell = jobs.progress()

    vae = _vae(str(body.get("vae") or ""))
    rows = []
    for index, source in enumerate(sources):
        image = media.load_image(source)
        latent, resized = _encode(vae, image, edge)
        latent = latent.detach().float().cpu()
        full_shape = "x".join(str(v) for v in latent.shape[2:])
        pool = f"1x{latent.shape[3]}x{latent.shape[4]}"
        if mode == "training":
            base = index / len(sources)
            latent = refmod.compress(
                latent, grid, steps,
                tell=lambda f, base=base: tell(base + f / len(sources)))
            pool = f"1x{latent.shape[3]}x{latent.shape[4]}"
        tell((index + 1) / len(sources))
        stem = name if index == 0 else f"{name}-{index + 1}"
        target = f"{subfolder}/{stem}" if subfolder else stem
        path = refmod.save(target, latent, {
            "kind": "image", "mode": mode, "source": "image",
            "source_shape": full_shape, "pool": pool,
            "optimize_steps": steps if mode == "training" else 0,
            "description": description, "concept_type": concept,
            "source_file": source.rsplit("/", 1)[-1],
        }, preview=resized[0])
        row = refmod.row_for(path, target)
        row["source"] = source
        rows.append(row)
        log.info("[Continuity] kept %s as a %s RefMod (%d tokens)", source, mode, row["tokens"])
    return {"mods": rows}


jobs.register("refmod", _run_job)


@PromptServer.instance.routes.post("/continuity/refmod/make")
async def make_refmod(request):
    """Queue the encode. The shape of the body is checked here, where a 400 with
    a sentence beats an error dialog a minute later."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    try:
        refmod.name_of(refmod.SCHEME + str(body.get("name") or ""))
    except refmod.RefModError:
        return web.json_response({"error": "a mod needs a name"}, status=400)
    sources = body.get("sources")
    if not isinstance(sources, list) or not sources:
        return web.json_response({"error": "nothing to keep — attach a picture first"}, status=400)
    for source in sources:
        if refmod.is_mod(source):
            return web.json_response(
                {"error": f"{source} is already a saved reference"}, status=400)
        try:
            media.resolve(source)
        except media.MediaError as exc:
            return web.json_response({"error": str(exc)}, status=400)
    if body.get("mode") not in (None, "", "full", "compressed", "stack"):
        return web.json_response({"error": "mode is full, compressed or stack"}, status=400)
    try:
        prompt_id = await jobs.submit("refmod", {
            key: body.get(key) for key in
            ("name", "subfolder", "sources", "mode", "edge", "grid", "steps",
             "description", "concept", "vae", "max_tokens", "frames")
        }, body.get("client_id"))
    except jobs.JobError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"prompt_id": prompt_id})


# ---- the file --------------------------------------------------------------------


def _json_body(request):
    async def read():
        try:
            return await request.json()
        except (json.JSONDecodeError, ValueError):
            return None
    return read()


def _refused(exc, status=400):
    return web.json_response({"error": str(exc)}, status=status)


@PromptServer.instance.routes.get("/continuity/refmod/file")
async def refmod_file(request):
    """The .safetensors itself, as a download named after the mod."""
    try:
        path = refmod.resolve(request.query.get("filename", ""))
    except refmod.RefModError as exc:
        return _refused(exc, 404)
    stem = os.path.basename(path)
    return web.FileResponse(path, headers={
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{stem}"',
    })


@PromptServer.instance.routes.post("/continuity/refmod/upload")
async def upload_refmod(request):
    """A .safetensors in, as `refmod:<subfolder>/<stem>`.

    Multipart, the way core's `/upload/image` is: `file`, and an optional
    `subfolder`. Streamed to a temporary file beside its destination and read
    as a mod before it is given a name — a file that is not one is deleted and
    refused by sentence, never left in the folder for the listing to skip.
    -> the picker row.
    """
    reader = await request.multipart()
    subfolder, stem, temporary = "", None, None
    try:
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "subfolder":
                subfolder = (await part.text()).strip().strip("/")
            elif part.name == "file" and temporary is None:
                original = os.path.basename(part.filename or "")
                stem = original[:-len(refmod.EXT)] if original.lower().endswith(refmod.EXT) else original
                fd, temporary = tempfile.mkstemp(prefix=".refmod-", suffix=".tmp", dir=refmod.home())
                with os.fdopen(fd, "wb") as out:
                    while True:
                        chunk = await part.read_chunk(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
        if temporary is None or not stem:
            return _refused("send a .safetensors as `file`")
        name = f"{subfolder}/{stem}" if subfolder else stem
        loop = asyncio.get_running_loop()
        path, meta = await loop.run_in_executor(None, refmod.adopt, temporary, name)
        temporary = None
        return web.json_response(refmod.row_for(path, refmod.name_of(name), meta=meta))
    except refmod.RefModError as exc:
        return _refused(exc)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


@PromptServer.instance.routes.post("/continuity/refmod/move")
async def move_refmod(request):
    """Rename a mod, or move it between folders: `{filename, name}` -> the row."""
    body = await _json_body(request)
    if body is None:
        return _refused("expected a JSON body")
    try:
        loop = asyncio.get_running_loop()
        path = await loop.run_in_executor(None, refmod.move, body.get("filename", ""), body.get("name", ""))
        return web.json_response(refmod.row_for(path, refmod.name_of(body.get("name", ""))))
    except refmod.RefModError as exc:
        return _refused(exc)


@PromptServer.instance.routes.post("/continuity/refmod/delete")
async def delete_refmod(request):
    """Delete a mod and its picture. Members built out of it show a missing
    tile until it is replaced — the same honest answer a deleted input file gets."""
    body = await _json_body(request)
    if body is None:
        return _refused("expected a JSON body")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, refmod.remove, body.get("filename", ""))
        return web.json_response({"ok": True})
    except refmod.RefModError as exc:
        return _refused(exc, 404)


@PromptServer.instance.routes.post("/continuity/refmod/describe")
async def describe_refmod(request):
    """Rewrite the description in the file's header: `{filename, description}`.
    The one field of a mod worth editing, and the one their loaders show."""
    body = await _json_body(request)
    if body is None:
        return _refused("expected a JSON body")
    try:
        path = refmod.resolve(body.get("filename", ""))
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: refmod.rewrite_meta(path, description=str(body.get("description") or "")))
        return web.json_response(refmod.row_for(path, refmod.name_of(body.get("filename", ""))))
    except refmod.RefModError as exc:
        return _refused(exc, 404)
