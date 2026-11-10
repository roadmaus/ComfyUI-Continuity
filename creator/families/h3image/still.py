"""MiniMax H3 Image's own half of an image render: the constants, the old
blob's migration and the sampler branch.

The shared flow — prompt, triggers, references, the canvas — is
`compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only this model knows, all of it read off core's support
(Comfy-Org/ComfyUI#17655, `comfy_extras/nodes_minimax_h3.py`) and the two
official templates (`image_minimax_h3_image_t2i`, `image_minimax_h3_image_edit`):

- **One conditioning node does the reading.** `MiniMaxH3ImageConditioning`
  takes the prompt and up to a hundred pictures, puts each in front of the
  Qwen3-VL encoder as `Picture N:` and — with the VAE connected — anchors it as
  a reference latent too, and hands back the conditioning *and* the empty
  latent at the canvas asked for. So this branch never builds a latent of its
  own for a text-to-image or an edit; it only replaces it where there is
  something to start from (an init, or the picture an inpaint keeps).
- **The schedule is baked.** The checkpoint is a PDD distillation: six heads,
  one per interval of its own sigma grid, and core's model sampling maps the
  stock schedulers onto that grid exactly when the step count is the head
  count. Six steps, cfg 1, euler/simple is the template's row and this
  family's default; anything else interpolates between heads the model was not
  distilled at, which the sampler row still allows because that is a thing
  worth being able to try.
- **The canvas is big.** The model card's working range is about 4 to 20 MP,
  best near 16; below 4 MP the template's own note says it does not work well.
  So this family declares its own `CANVAS` rather than reading the shared 4 MP
  ceiling every other still family lives under.
- **Inpainting is a noise mask.** The bench's `matte` tracing (white where the
  picture changes) attached as the still's guide is the mask, `Picture 1` is
  the picture it is drawn over, and the sampler keeps every latent outside it
  — ordinary latent-mask inpainting, which core's MiniMax H3 base model hands
  straight to the stock path for the image model's single stream. No branch to
  load, no strength: the mask is the whole control.

**Why this replaced the H3 still.** The pre-stage used to make a MiniMax still
by running the *video* model on the shortest legal clip and decoding its first
latent frame (`MiniMaxH3StillLatent`, now gone). That was the only way to get
a picture out of MiniMax weights, and it cost a video sampler pass at a video
canvas for one frame. These weights draw a picture outright, at four to
twenty times the area, and edit one. The pill kept its "minimax" id, so a
saved pre-stage still opens here — see `migrate`.

**LoRAs** go through core's `LoraLoaderModelOnly` like every other still family.
The DiT has the pruned H3 video transformer's shape (50 blocks, 5376 wide), so
an H3 video LoRA's keys match; whether one *does* anything useful on an image
model distilled to six heads is a lab question, not a key-matching one.
"""

import sys

from . import declare

ARCH = declare.STILL_ARCH

# Saved references in this family's latent space — H3's own, see
# `declare.REFMOD`. Read by `compile_image.compile_prestage` to hand this
# graph the rendition of a picture rather than the picture, where the slot
# has one.
REFMOD = declare.REFMOD

# Which weights fields this architecture has. One DiT, no second checkpoint and
# no distillation LoRA: the six-step schedule is the checkpoint itself.
FIELDS = ("model", "clip", "vae")

# The image VAE, not the video one: the H3 encoder with a 2D single-frame ViT
# decoder. The video VAE loads and then decodes a one-frame latent through a
# temporal decoder, which is exactly the mistake `vaekind` exists to refuse.
VAE_KIND = "h3_image"

# The same Qwen3-VL 32B encoder H3 video reads prose through — one file on disk
# serves both families — under CLIPLoader's "minimax" type.
CLIP_TYPE = "minimax"

# References are native: the conditioning node reads them on the base weights.
TAKES_REFS = True

# Pictures, not style references: `Picture 1` is the thing an edit changes and
# the rest are what the instruction names. See qwenedit's `REFS_NOUN`.
REFS_NOUN = ("picture", "pictures")

# How a cited picture is spelled in the prompt. The encoder writes `Picture N:`
# in front of each image, and both templates' prompts (and the prompt
# enhancer's system prompt) cite them `<Picture N>` — MiniMax's convention,
# angle brackets and all, the same one H3 video was trained on.
REFS_CITATION = "<Picture {n}>"

# Core's node grows to a hundred slots; the pack caps it where the reference bar
# is built to go. Every picture is a reference latent at a 1-2k short edge that
# the DiT attends over beside a 16 MP target, so the cap is about memory before
# it is about the model.
REFS_LIMIT = 4
REFS_LIMIT_REASON = ("every picture is another reference latent the model "
                     "attends over beside a canvas of up to 20 MP")

# What the pictures go through on their way in: the Qwen3-VL vision tower. The
# H3 text-only cut would read the sentence and quietly drop every picture.
REFS_NEED_VISION = True

# `Picture 1` is the picture an edit changes — core's own tooltip says so — and
# with `edit_first` it decides the canvas, the way the edit template sizes its
# latent off the loaded image. The latent itself stays the conditioning node's
# empty one: the instruction reaches the model through the reference, and at
# the schedule's first sigma an encoded init is noise anyway.
EDITS_FIRST_REF = True

# The canvas. The model card's range is ~4-20 MP and best near 16; the template
# starts at 4 MP "because it is cheaper", and so does the slider. The /32 grid
# is core's (`CANVAS_MULTIPLE` in `nodes_minimax_h3.py`), as is the ratio
# envelope: 21:9 is the widest size the card lists. The long-edge ceiling is the
# card's 21:9 entry, 6272, rounded to the grid.
CANVAS = {
    "multiple": 32,
    "min_short_edge": 1536,
    "max_short_edge": 4096,
    "max_long_edge": 6272,
    "default_short_edge": 2048,
    "max_pixels": 20 * 1024 * 1024,
    "min_ratio": 9 / 21,
    "max_ratio": 21 / 9,
}

# The row. `pdd_steps` in the checkpoint's own metadata is 6, and the template
# samples 6 steps at cfg 1 on euler/simple — with the negative zeroed out,
# because a distilled cfg-1 row never evaluates it.
H3IMAGE_ROW = {"steps": 6, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}

# The guide this family reads: a mask. `CONTROL_WEIGHTS = False` tells
# `render_image.check` there is no branch file to ask for — the matte goes to
# the sampler as its noise mask, and that is all a guide does here.
CONTROL_TRACINGS = ("matte",)
CONTROL_WEIGHTS = False
INPAINT_NEEDS_PICTURE = (
    "An inpaint mask is drawn over a picture, and this still has none: attach "
    "the picture the matte was traced from as Picture 1, or take the mask off"
)

# The conditioning node, keyed off what core registers.
CONDITIONING_NODE = "MiniMaxH3ImageConditioning"


def migrate(data):
    """A pre-stage blob from before these weights -> one this family reads.

    The H3 still kept everything in its own `minimax` block: a Creator-shaped
    `request` (prompt, assets, LoRAs, aspect, refined prose, screens) plus the
    clip length and latent frame it decoded. Those last two mean nothing to an
    image model and are dropped; the request's sentence, pictures and LoRAs are
    lifted into the shared fields every still family reads, because that is
    what the person saw in the box when they saved. The mirror is
    `state.js`'s `migratePreStage` (run by `parsePreStage`), so a blob opened
    in the browser and one queued headless read the same.

    A blob with no `minimax.request` is returned as it is — it was written by
    this family, or never had the branch.
    """
    block = data.get(ARCH) if isinstance(data, dict) else None
    request = block.get("request") if isinstance(block, dict) else None
    if not isinstance(request, dict):
        return data
    out = {key: value for key, value in data.items() if key != ARCH}
    if data.get("arch") != ARCH:
        # Another family's blob that still carries the old branch's block from
        # a pill flip: the block goes, and nothing of it is lifted over fields
        # that family is using.
        return out
    out["prompt"] = request.get("prompt") or ""
    if isinstance(request.get("refined"), dict):
        out["refined"] = request["refined"]
    else:
        out.pop("refined", None)
    refs = []
    for asset in request.get("assets") or []:
        if not isinstance(asset, dict) or asset.get("kind", "image") != "image":
            continue
        if asset.get("role") == "guide" or not asset.get("filename"):
            continue
        ref = {"filename": asset["filename"]}
        for key in ("handle", "crop", "mods"):
            if asset.get(key):
                ref[key] = asset[key]
        refs.append(ref)
    out["refs"] = refs
    out["loras"] = list(request.get("loras") or [])
    if request.get("aspect"):
        out["aspect"] = request["aspect"]
    if request.get("screens"):
        out["screens"] = request["screens"]
    return out


def plan(data):
    """-> (checkpoint field, schedule). One file and a schedule the checkpoint
    carries, so there is nothing to decide."""
    return "model", {}


def max_refs(data):
    """`(references this render may carry, why)` — see `REFS_LIMIT`."""
    return REFS_LIMIT, REFS_LIMIT_REASON


def require_support():
    """Refuse a core without the image model — keyed off the node it renders
    through, which arrived with it (ComfyUI 0.45)."""
    import nodes

    if CONDITIONING_NODE not in nodes.NODE_CLASS_MAPPINGS:
        raise ValueError(
            "This ComfyUI does not know MiniMax H3 Image yet (no "
            "MiniMaxH3ImageConditioning node — it arrived in ComfyUI 0.45). "
            "Update ComfyUI and restart."
        )


def require_control():
    """Nothing to load for a mask; the conditioning node is the only
    requirement, and `require_support` has already asked for it."""


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    # A slot read from a saved reference shows the encoder the mod's own
    # decode — what H3 video's encode does (`encode._mod_tensors`): the mod
    # is the member, a compressed one is the blur the DiT will attend to, and
    # a mod standing alone has no other picture. The conditioning node then
    # anchors that picture as usual, and `ContinuityRefModH3ImageAnchor`
    # puts the file's latent back in the slot's place: one throwaway encode
    # per mod, in exchange for core's node reading the prompt and sizing the
    # canvas exactly as the template's does.
    images = {}
    for slot, name in enumerate(payload.refs):
        mod = payload.mods.get(slot)
        if mod is None:
            images[f"images.image_{slot + 1}"] = render_image.load_picture(
                graph, payload, f"ref:{slot}", name)
            continue
        latent = graph.node("ContinuityRefModLatent", name=mod,
                            space=declare.REFMOD["space"]).out(0)
        images[f"images.image_{slot + 1}"] = graph.node(
            "VAEDecode", samples=latent, vae=vae).out(0)
    conditioning = graph.node(CONDITIONING_NODE, clip=clip, vae=vae,
                              prompt=payload.prompt, width=payload.width,
                              height=payload.height, **images)
    positive = conditioning.out(0)
    for slot, mod in sorted(payload.mods.items()):
        positive = graph.node("ContinuityRefModH3ImageAnchor", conditioning=positive,
                              name=mod, slot=slot).out(0)
    # cfg 1 never evaluates the negative; the template zeroes it, and at real
    # cfg a zeroed copy is still the unconditional the model sees in training
    # more nearly than an empty prompt with the pictures stripped would be.
    negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)

    latent, denoise = conditioning.out(1), 1.0
    if payload.control is not None:
        # Inpainting: Picture 1 encoded as the latent the sampler keeps, the
        # matte as the region it may change. Full denoise inside the mask —
        # the stock sampler pins everything outside it at every step.
        source = images["images.image_1"]
        source = graph.node("ImageScale", image=source, upscale_method="lanczos",
                            width=payload.width, height=payload.height,
                            crop="center").out(0)
        encoded = graph.node("VAEEncode", pixels=source, vae=vae).out(0)
        matte = render_image.load_picture(graph, payload, "guide",
                                          payload.control["filename"])
        matte = graph.node("ImageScale", image=matte, upscale_method="bilinear",
                           width=payload.width, height=payload.height,
                           crop="center").out(0)
        mask = graph.node("ImageToMask", image=matte, channel="red").out(0)
        latent = graph.node("SetLatentNoiseMask", samples=encoded, mask=mask).out(0)
    elif payload.init is not None and payload.init["denoise"] < 1.0:
        # img2img: the init encoded and partly noised. A full-denoise init —
        # the promoted Picture 1 of an edit — keeps the node's empty latent.
        latent, denoise = render_image.emit_latent(graph, payload, vae, None)

    sampled = graph.node(
        "KSampler", model=model, positive=positive, negative=negative,
        latent_image=latent, seed=sampling.seed, steps=sampling.steps,
        cfg=sampling.cfg, sampler_name=sampling.sampler_name,
        scheduler=sampling.scheduler, denoise=denoise,
    )
    render_image.emit_tail(graph, sampled.out(0), vae, unique_id, filename_prefix,
                           request=payload.neural, screens=payload.screens)


def compile_still(data, image_size_lookup=None):
    """The uniform still surface — see `families/registry.py`. The flow is the
    shared `compile_image.compile_prestage`, handed this module as the family,
    after the old H3 still's blob is lifted into the shared fields.

    A mask makes Picture 1 the picture edited in place whether or not the
    `edit_first` switch is on: an inpaint *is* that edit, and the canvas has to
    be Picture 1's for the mask to land where it was traced.

    The picture an edit or an inpaint changes is read as itself, never as a
    saved reference hung on it: the render keeps that picture's pixels (all
    of them outside a mask), and a mod pooled to a 48-grid is the wrong thing
    to keep. Its mod stays on it for every other render. A mod standing alone
    in Picture 1 has no pixels to draw a mask over, so an inpaint refuses it.
    """
    import dataclasses

    from ... import compile_image, refmod
    from ...compile import CompileError

    data = migrate(data)
    if isinstance(data, dict) and any(
            isinstance(r, dict) and r.get("role") == "guide" for r in data.get("refs") or []):
        if not any(isinstance(r, dict) and r.get("role") != "guide"
                   for r in data.get("refs") or []):
            raise CompileError(INPAINT_NEEDS_PICTURE)
        data = {**data, compile_image.EDIT_FIRST_FIELD: True}
    payload = compile_image.compile_prestage(data, sys.modules[__name__],
                                             image_size_lookup)
    if payload.control is not None and payload.refs and refmod.is_mod(payload.refs[0]):
        raise CompileError(INPAINT_NEEDS_PICTURE)
    if (0 in payload.mods and payload.init is not None
            and payload.init.get("filename") == payload.refs[0]):
        payload = dataclasses.replace(
            payload, mods={slot: mod for slot, mod in payload.mods.items() if slot})
    return payload


def emit_still(data, plan, sampling, unique_id):
    """The uniform still surface over the shared `render_image.emit`."""
    from ... import outputs, render_image, settings

    weights = render_image.ImageWeights.from_blob(data, sys.modules[__name__])
    return render_image.emit(plan, weights, sampling, unique_id,
                             sys.modules[__name__],
                             filename_prefix=outputs.image(
                                 data, settings.image_prefix(declare.ID)))
