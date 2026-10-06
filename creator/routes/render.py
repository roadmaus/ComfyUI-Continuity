"""`/continuity/render`: a render asked for by a script, with no node on a canvas.

The front door for anything that is not a browser — a shell, a CI job, a coding
agent told "make a clip of a cat on the lab". Before it, such a caller had to
write the Creator's `creator_data` blob by hand, guess filenames for every weight
slot, list all thirteen sampler widgets in ComfyUI's API format and throw the
turbo switch itself; each one reinvented that, differently. `skills/continuity-render/render.py`
is the client (shipped, unlike `tools/`, and inside the Claude Code skill so an agent never has to look for it), and `docs/headless.md` says how to use it.

**Nothing here is a second builder.** The chat room already turns "this prompt,
these pictures, this family" into a validated one-node prompt, over this
machine's remembered weight picks, with the compiler's dry run in front of the
queue — `routes/chat._build`. A request here becomes the same action, ledger
and rail the room sends, over a bare piece of the family asked for, and goes
through that function. What it adds is the one thing the room reads off a
canvas node: the turbo switch (`creator/headless.py`).

`GET` answers what this machine can make: every family, whether its files are
all here, what it would render with, and what `fast` would throw on it. `POST`
queues one render and answers its prompt id; the result lands in output/ like
any render and is reported in `/history/<prompt_id>` under the save node's
`mmc_video` or `mmc_image`.

Request (POST, JSON):

    {"family": "h3", "prompt": "a cat stretches on a windowsill",
     "still": false,                 # a picture rather than a clip (image families)
     "pictures": [{"filename": "cat.png", "as": "start"}],   # input/ names
     "seconds": 6, "aspect": "16:9", "short_edge": 768, "seed": 7,
     "fast": true, "turbo_lora": null, "merged": false, "quality": null,
     "models": {"clip": "..."},      # a slot's file, over this machine's picks
     "devices": {"clip": "cuda:1"},  # where a slot loads, over this machine's pins
     "accel": {"attention": "kitchen"},  # how the card runs it, over this machine's row
     "guide_strength": 0.8,          # how hard a guide pulls (a still's, below)
     "loras": [{"name": "style.safetensors", "strength": 0.8}]}  # on the stack, under any turbo LoRA

A picture is cited in the prompt as `@pic-1` (`@clip-1`, `@snd-1` for video and
sound), numbered in the order sent; one that is not cited rides anyway. `as` is
`start`, `end`, `ref` or a reference scope (`style`, `person`, ...); left out,
the first picture opens the shot — the room's rule, `chat.video_piece`.

`loras` are the caller's own, by their name under models/loras, patched as the
node's stack would patch them; the turbo switch adds its distill beside them.
On H3 an entry may say `"modes": ["ref2va"]` to claim one checkpoint, as the
node's LoRA manager does; without it the LoRA rides every pass.

`as: "guide"` is a still's tracing for a family that loads a ControlNet branch
to read one (Qwen Image 2.1): it is not a picture the prompt cites — it takes no
`@pic-N` — and goes onto the blob the way the pre-stage's Guide tool puts it
there, with `guide_strength` as the stop pressed beside it.

A clip samples on the machine's half of the row (`settings.accel`: attention,
low VRAM, fast math), the one the node last set, because the node is where a
browser render reads it and there is no node here. The room does not need
this — it renders with the node's own widgets — which is why it was missed:
until it was read here every headless render ran plain attention.
"""

import asyncio
import os

from aiohttp import web

from server import PromptServer

from .. import chat, headless, jobs, models as core_models, sampling, server_routes, settings
from ..families import manifest, registry
from ..guard import same_origin
from . import chat as room

# The ledger's word for a file, by extension. The room mints the same three.
KINDS = {**dict.fromkeys((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"),
                         ("pic", "still")),
         **dict.fromkeys((".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"), ("clip", "clip")),
         **dict.fromkeys((".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"), ("snd", "sound"))}


def _machine():
    """What every family would render with here, and what `fast` would throw."""
    catalog = manifest.catalog()
    available = core_models.available()
    stored = settings.load().get("weights") or {}
    names = server_routes._lora_names()
    out = []
    for family, report in zip(catalog["families"],
                              chat.setup_report(catalog, available, stored)):
        turbo = headless.turbo_of(family)
        routed = [slot["id"] for slot in family.get("weights") or [] if slot.get("routed")]
        fast = {"switch": bool(turbo)}
        if turbo:
            fast["checkpoint"] = report["picks"].get(chat.TURBO_SLOT) if turbo.get("checkpoint") else None
            fast["loras"] = ({c: headless.candidates(turbo, names, c) for c in routed}
                             if routed else headless.candidates(turbo, names))
            fast["qualities"] = turbo["steps"]
            fast["default_quality"] = turbo.get("default_quality")
        out.append({"id": report["id"], "label": report["label"],
                    "produces": report["produces"], "ready": not report["missing"],
                    "missing": report["missing"], "picks": report["picks"], "fast": fast})
    return {"families": out}


@PromptServer.instance.routes.get("/continuity/render")
async def describe(request):
    loop = asyncio.get_running_loop()
    return web.json_response(await loop.run_in_executor(None, _machine))


def _request(body, accel=None):
    """The body -> `(action, ledger, rail, base, family manifest, still)`.

    `accel` is the machine's remembered rows, by family (`settings.accel`).
    """
    family_id = str(body.get("family") or "").strip()
    if family_id not in registry.FAMILIES:
        raise headless.HeadlessError(
            f"family must be one of {', '.join(registry.FAMILIES)}; yours was {family_id!r}.")
    family = manifest.describe(family_id)
    produces = set(family.get("produces") or [])
    still = bool(body.get("still")) if "still" in body else "video" not in produces
    if still and family_id not in registry.IMAGE_FAMILIES:
        raise headless.HeadlessError(
            f"{family['label']} renders clips here; for a picture use one of "
            f"{', '.join(registry.IMAGE_FAMILIES)}.")
    if not still and "video" not in produces:
        raise headless.HeadlessError(f"{family['label']} draws pictures, not clips — send still: true.")

    ledger, cited, counts, guides = [], [], {}, []
    for item in body.get("pictures") or []:
        item = {"filename": item} if isinstance(item, str) else dict(item or {})
        filename = str(item.get("filename") or "").strip()
        if not filename:
            raise headless.HeadlessError("every picture needs a filename in ComfyUI's input folder.")
        # `name.png [output]` is ComfyUI's own annotation; the extension is before it.
        prefix, kind = KINDS.get(os.path.splitext(filename.split(" [")[0])[1].lower(), (None, None))
        if prefix is None:
            raise headless.HeadlessError(f"{filename!r} is not a picture, a clip or a sound.")
        if str(item.get("as") or "").strip() == "guide":
            guides.append(_guide(family, still, prefix, filename))
            continue
        counts[prefix] = counts.get(prefix, 0) + 1
        handle = f"{prefix}-{counts[prefix]}"
        ledger.append({"handle": handle, "kind": kind, "filename": filename})
        role = str(item.get("as") or "").strip()
        cited.append(f"{handle}:{role}" if role else handle)

    raw = {"act": chat.ACT_RENDER, "kind": chat.KIND_STILL if still else chat.KIND_VIDEO,
           "prompt": body.get("prompt"), "from": cited,
           "seconds": body.get("seconds"), "aspect": body.get("aspect")}
    action = chat.validate(raw, ledger)

    edge = body.get("short_edge")
    rail = room._rail({("still_family" if still else "video_family"): family_id,
                       **({"short_edge": edge} if edge else {})})
    overrides = {k: v for k, v in (body.get("models") or {}).items() if isinstance(v, str)}
    if still:
        if body.get("devices"):
            raise headless.HeadlessError(
                "devices is for a video family; a picture family loads where ComfyUI puts it.")
        if body.get("accel"):
            raise headless.HeadlessError(
                "accel is for a video family; a picture family's row has no attention to pick.")
        piece = {"version": 1, "arch": rail["still_arch"], "loras": [], "turbo": {},
                 "models": {rail["still_arch"]: overrides}}
        if guides:
            # `chat.still_piece` writes the cited pictures over the blob and
            # keeps a guide already on it, as a pre-stage node's would be.
            piece["refs"] = guides
            if body.get("guide_strength") is not None:
                piece["guide"] = {"strength": body.get("guide_strength")}
    else:
        devices = {k: v for k, v in (body.get("devices") or {}).items()
                   if isinstance(k, str) and isinstance(v, str)}
        try:
            row = {**((accel or {}).get(family_id) or {}),
                   **sampling.machine(body.get("accel") or {})}
        except sampling.SamplingError as problem:
            raise headless.HeadlessError(str(problem)) from None
        piece = {"version": 2, "family": family_id, "loras": [], "turbo": {},
                 "models": {**overrides, **({"devices": devices} if devices else {})},
                 **({"sampling": row} if row else {})}
    piece["loras"] = _loras(body.get("loras"))
    seed = body.get("seed")
    widgets = {"seed": int(seed)} if isinstance(seed, int) and not isinstance(seed, bool) else {}
    return action, ledger, rail, (piece, widgets), family, still


def _loras(raw):
    """The request's `loras` -> stack entries, each a file this machine has.

    Refused by name rather than dropped: a LoRA that is not on the disk is a
    render that quietly lacks what it was asked for, and the caller is a script
    that would never notice. The near names are said, because the usual cause
    is a subfolder left off.
    """
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise headless.HeadlessError('loras must be a list of {"name", "strength"}.')
    names = server_routes._lora_names()
    out = []
    for item in raw:
        item = {"name": item} if isinstance(item, str) else item
        name = str((item or {}).get("name") or "").strip() if isinstance(item, dict) else ""
        if not name:
            raise headless.HeadlessError("every LoRA needs a name under models/loras.")
        if name not in names:
            stem = os.path.splitext(os.path.basename(name))[0].lower()
            near = [n for n in names if stem and stem in n.lower()][:5]
            raise headless.HeadlessError(
                f"{name!r} is not in models/loras on this machine"
                + (f" — did you mean {', '.join(near)}?" if near else "."))
        try:
            strength = float(item.get("strength", 1.0))
        except (TypeError, ValueError):
            raise headless.HeadlessError(f"LoRA {name}: strength must be a number.") from None
        entry = {"name": name, "strength": strength}
        if isinstance(item.get("modes"), list):
            entry["modes"] = [str(m) for m in item["modes"]]
        out.append(entry)
    return out


def _guide(family, still, prefix, filename):
    """One `as: "guide"` picture -> the pre-stage's guide entry, or a refusal."""
    if not still:
        raise headless.HeadlessError(
            "a guide here is a still's — a clip is aimed through the Creator's "
            "guide, which this route does not drive yet.")
    if (family.get("capabilities", {}).get("control") or {}).get("method") != "branch":
        raise headless.HeadlessError(
            f"{family['label']} loads no ControlNet here, so it has nothing to read a "
            f"guide with (on Qwen Image 2.1 the branch also needs a core that can load "
            f"it).")
    if prefix != "pic":
        raise headless.HeadlessError(f"{filename!r}: a still's guide is one picture.")
    return {"handle": "guide", "filename": filename, "role": "guide"}


def _render(body):
    """The blocking half: build, throw the switch, build again. -> the answer."""
    machine = settings.load()
    action, ledger, rail, base, family, still = _request(body, machine.get("accel"))
    stored = machine.get("weights") or {}
    built = room._build(action, ledger, rail, stored, base)
    if "problem" in built or not body.get("fast", True):
        return {**built, "speed": "native"}

    piece, widgets = base
    names = server_routes._lora_names()
    lora = str(body.get("turbo_lora") or "").strip() or None
    merged = body.get("merged") is True
    if still:
        if merged:
            raise headless.HeadlessError(
                "merged: true is for a video family's checkpoint; a picture family's "
                "turbo checkpoint is picked in its turbo_model slot.")
        picks = room._picked(family, stored, core_models.available(),
                             own=piece["models"][piece["arch"]])
        thrown = headless.throw_still(piece, family, picks, names, lora, body.get("quality"))
    else:
        # The checkpoints the dry run routed to — which distill each one takes.
        passes = server_routes.compiled_passes(built["piece"])["passes"]
        checkpoints = sorted({p["checkpoint"] for p in passes if not p["clip"]})
        thrown = headless.throw_video(piece, family, checkpoints, names, lora,
                                      body.get("quality"), merged=merged)
    if thrown is None:
        # Nothing to throw: the family has no switch, and its native row is its
        # only row. Said, so nobody reads a long render as a fast one.
        return {**built, "speed": f"native ({family['label']} has no turbo switch)"}
    built = room._build(action, ledger, rail, stored, (piece, widgets))
    return {**built, "speed": {"turbo": thrown}}


@PromptServer.instance.routes.post("/continuity/render")
@same_origin
async def render(request):
    """Queue one render. -> `{prompt_id, speed, piece}`, or `{problem}` (400)."""
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"problem": "the request body was not JSON"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"problem": "the request body must be a JSON object"}, status=400)

    loop = asyncio.get_running_loop()
    try:
        built = await loop.run_in_executor(None, _render, body)
    except (headless.HeadlessError, chat.ActionError) as problem:
        return web.json_response({"problem": str(problem)}, status=400)
    except server_routes.COMPILE_FAILURES as problem:
        return web.json_response({"problem": str(problem)}, status=400)
    if "problem" in built:
        return web.json_response({"problem": built["problem"]}, status=400)

    try:
        prompt_id = await jobs.enqueue(built["prompt"], body.get("client_id"))
    except jobs.JobError as problem:
        return web.json_response({"problem": str(problem)}, status=500)
    return web.json_response({"prompt_id": prompt_id, "node": built["node"],
                              "speed": built["speed"], "piece": built["piece"]})
