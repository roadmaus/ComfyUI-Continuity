"""`/continuity/refmod/make`: keep a picture as a saved reference.

One route, and it is a job (`creator/jobs.py`): encoding through the H3 VAE is
GPU work and goes on the queue behind whatever is rendering, with Cancel and
the real progress bar. The result is the picker rows of what was written, so
the caller can attach them without a second listing.

The reading side needs no route of its own: `/continuity/assets?root=refmods`
lists mods and `/continuity/thumb` serves their pictures (`server_routes`).
"""

import json
import logging
import os

from aiohttp import web
from server import PromptServer

from .. import jobs, media, refmod

log = logging.getLogger(__name__)

# What a full mod is encoded at when the caller does not say: the sibling
# pack's own default, a 64x64 latent for a square picture. Core's reference
# path goes to 2048 — `edge` reaches it, at four times the tokens.
DEFAULT_EDGE = 1024
DEFAULT_GRID = 16
DEFAULT_STEPS = 150
MAX_STEPS = 2000


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


def _run_job(body):
    """Every source in `body["sources"]` becomes one mod. See the module note."""
    sources = [str(s) for s in (body.get("sources") or []) if s]
    if not sources:
        raise jobs.JobError("nothing to keep — the member has no pictures attached")
    name = refmod.name_of(refmod.SCHEME + str(body.get("name") or ""))
    subfolder = str(body.get("subfolder") or "").strip().strip("/")
    mode = "training" if body.get("mode") == "compressed" else "encode"
    edge = max(256, min(4096, int(body.get("edge") or DEFAULT_EDGE)))
    grid = max(4, min(64, int(body.get("grid") or DEFAULT_GRID)))
    steps = max(0, min(MAX_STEPS, int(body.get("steps") or DEFAULT_STEPS)))
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
        meta = refmod.header(path)
        stat = os.stat(path)
        rows.append({
            "path": refmod.filename_of(target), "name": stem, "subfolder": subfolder,
            "kind": "image", "size": stat.st_size, "mtime": stat.st_mtime, "mod": True,
            "mode": meta["mode"], "tokens": meta["tokens"],
            "grid": [meta["latent_t"], meta["latent_h"], meta["latent_w"]],
            "description": description, "preview": True, "source": source,
        })
        log.info("[Continuity] kept %s as a %s RefMod (%d tokens)", source, mode, meta["tokens"])
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
    if body.get("mode") not in (None, "", "full", "compressed"):
        return web.json_response({"error": "mode is full or compressed"}, status=400)
    try:
        prompt_id = await jobs.submit("refmod", {
            key: body.get(key) for key in
            ("name", "subfolder", "sources", "mode", "edge", "grid", "steps",
             "description", "concept", "vae")
        }, body.get("client_id"))
    except jobs.JobError as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"prompt_id": prompt_id})
