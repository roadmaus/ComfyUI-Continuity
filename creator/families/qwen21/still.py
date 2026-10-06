"""Qwen Image 2.1's own half of an image render: the constants and the
sampler branch.

The shared flow — prompt, triggers, references, the /16 canvas — is
`compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only this architecture knows: one encoder node that reads the sentence
and every attached picture together and hands back both conditionings, the
`<imageN>` spelling its tokenizer writes in front of each picture, the pixel
budget the references are resized to, and the fact that the first picture is
also the one being edited.

Everything it emits is core's, taken from the official ComfyUI Qwen Image 2.1
templates (`image_qwen_image_2_1_t2i`, `_image_edit`) rather than invented.
Compared with the Qwen Image Edit family this is a shorter graph, not a
variant of the same one: the schedule is detected (`supported_models.
QwenImage21` carries the shift, so no `ModelSamplingAuraFlow`), the templates
sample at cfg 1 with no `CFGNorm`, and drawing from nothing and editing a
picture go through the same encoder node — its template is the text-to-image
one with the references prepended, so there is no system prompt about a
picture that is not there and nothing to switch encoders over.
"""

import math
import sys

ARCH = "qwen21"

# Which weights fields this architecture has. One DiT: the speed axis is a
# Lightning LoRA or nothing, so there is nothing to route between. `control`
# is the Fun ControlNet branch below, optional: loaded only where a guide is
# attached.
FIELDS = ("model", "clip", "vae", "control")

# The guide, through a loaded branch rather than a picture slot. Unlike Qwen
# Image Edit 2509/2511 these weights were never post-trained to follow a
# tracing arriving among the references — fed to the encoder, an edge map is
# read as a picture *of* an edge map. What does follow one is alibaba-pai's
# Qwen-Image-2.1-Fun-Controlnet-Union: a 16-block control branch beside the
# DiT, one block injected at every second base layer, its input the guide's
# VAE latent. Core loads it with `ModelPatchLoader` (from models/model_patches,
# not models/controlnet — it is a model patch, not a ControlNet core's
# conditioning path knows) and applies it with `ZImageFunControlnet`, whose
# description names Qwen Image 2.1 alongside Z-Image: both branches patch the
# *model*, so the guide is a model wrapper and the conditioning is untouched.
#
# The tracings the card lists — canny, depth, gray, HED, line art, MLSD, pose,
# scribble — in the bench's vocabulary: Edges is the canny, Lines covers HED,
# line art and scribble, Luma is the grey. MLSD the bench does not trace.
CONTROL_LOADER = "ModelPatchLoader"
CONTROL_NODE = "ZImageFunControlnet"
CONTROL_TRACINGS = ("edges", "lines", "depth", "pose", "luma")

# Which VAE the `vae` field has to hold, checked off the file's header before
# the render is queued — see `vaekind`. Not the Qwen image VAE: 2.1 ships its
# own, 64 latent channels at /16 with an alpha channel in and out, and the
# 16-channel one Qwen Image Edit and Krea 2 decode with would sample the whole
# render before core's decode found the mismatch.
VAE_KIND = "qwen_image21"

# What CLIPLoader calls the encoder. The same type string Qwen Image Edit
# loads its 2.5-VL through — core tells the two apart by what is in the file,
# and a Qwen3-VL-8B under `qwen_image` is what routes to the 2.1 tokenizer.
CLIP_TYPE = "qwen_image"

# References are native: `TextEncodeQwenImage21` feeds every attached picture
# to the encoder as vision tokens *and* VAE-encodes it into the conditioning's
# reference latents, and the DiT splices each latent into the sequence where
# its `<imageN>` stood. No adapter to add first — the base weights read them.
TAKES_REFS = True

# What to call them — an edit family's noun. `Picture 1` is the thing the
# instruction is about, read for what is in it, and "style reference" would
# name the one property the model is not being asked about.
REFS_NOUN = ("picture", "pictures")

# ...and how the prompt names them. The 2.1 tokenizer writes `<image1>`,
# `<image2>`, ... in front of each picture's vision block, and the official
# edit prompts cite them by that spelling; `Picture N` is what the *2509/2511*
# encoder writes and means nothing to this one. `compile_image._cite_refs`
# reads this where a family declares it.
REFS_CITATION = "<image{n}>"

# How many. The encoder node grows to sixteen slots; the official template says
# ten and stops there, and so does this pack: every picture is another latent
# the DiT attends over at every step, and ten is already a contact sheet.
REFS_LIMIT = 10
REFS_LIMIT_REASON = ("ten is where the official Qwen Image 2.1 workflow stops — "
                     "every picture is another latent the model attends over "
                     "at every step")

# An edit in place is a picture being changed, so `Picture 1` decides the
# canvas when the blob asks (`edit_first`) — the shared compile promotes it to
# the init at denoise 1.0 and the render comes out its shape. Like Flux 2
# Klein and unlike Qwen Image Edit, the official graph starts the latent
# *empty*: the picture reaches the model through the reference conditioning,
# and `emit_graph` honours that by emitting the template's own empty latent
# for a full-denoise init rather than an encode about to be noised away.
# Without the flag the pictures are references on the aspect pill's canvas —
# a character rendered once, then drawn into a sheet — and an explicit init
# wins over either.
EDITS_FIRST_REF = True

# The references' pixel budget and the canvas, which are one decision here.
# `TextEncodeQwenImage21` resizes each picture to about `resolution`² pixels,
# aspect kept, on the vision tower's /32 patch grid, and hands back an empty
# latent at the *first* picture's resized size with the note that "any other
# size shifts the edit": the reference latent is spliced into the sequence at
# that size, and a target one latent row bigger or smaller is an edit that
# drifts. So on an edit the canvas is not snapped to the shared /16 grid and
# the budget derived from it — that is off by a row on a 4:3 phone photo at
# the default edge — but built the other way round: the budget is taken from
# the canvas the shared compile resolved, and the canvas becomes the encoder's
# own resize of the picture at that budget, by the encoder's own arithmetic.
# The budget then rides in the payload (`ref_resolution`), because a /32
# canvas does not round back to the budget that made it on a wide aspect. The
# template's fixed 1024 is not kept: a 2K edit wants a 2K reference. 0 would
# keep every reference at its file size, which on a phone photo is a
# 12-megapixel latent the model was never asked to attend over.
REF_RESOLUTION_STEP = 32

# What the checkpoint wants from the sampler row with nothing distilled on it:
# the shipped template's row. A six-way sweep on the lab (2026-09, a candid
# phone-photo prompt) first picked 40 steps at cfg 3 for its hands and skin,
# and a second sitting at native 2K put that back: a 2048x1152 character sheet
# was four minutes at 40/cfg 3 (3.6 s a step, the uncond doubling every one)
# against one at 20/cfg 1, for a crisper ruff and nothing anyone chose the
# picture by. Qwen's own card asks 40-50 at euler; the row is where to go
# when a render is worth the wait, not where every render starts.
QWEN21_BASE = {"steps": 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}

# The speed axis, and like Qwen Image Edit's it is a LoRA or it is nothing:
# there is no distilled Qwen Image 2.1 checkpoint. The ladder's ends are where
# the Lightning distillations of every Qwen-Image release so far have been
# published, four and eight steps; the middle is for a run that wants a little
# more than the short LoRA's own number.
TURBO_STEPS = {"draft": 4, "medium": 6, "good": 8}
DEFAULT_TURBO_QUALITY = "draft"
TURBO_ROW = {"cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}
TURBO_NEEDS_LORA = (
    "Qwen Image 2.1 has no distilled checkpoint — its turbo pill is a "
    "Lightning LoRA over the ordinary one. Pick the LoRA, or leave the switch "
    "off and sample the full row"
)


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    One checkpoint field either way: the turbo pill here is a LoRA. No schedule
    block — the shift is in core's model detection for these weights, and the
    Lightning LoRAs are fitted against that same schedule.
    """
    from ...compile import CompileError
    from ...compile_image import turbo_block

    turbo = turbo_block(data, ARCH)
    if turbo.get("on") and not turbo.get("lora"):
        raise CompileError(TURBO_NEEDS_LORA)
    return "model", {}


def max_refs(data):
    """`(references this render may carry, why)` — see `REFS_LIMIT`."""
    return REFS_LIMIT, REFS_LIMIT_REASON


def _encoder_size(resolution, ratio):
    """`TextEncodeQwenImage21`'s resize of a picture of `ratio` at `resolution`
    — the node's own lines, so the canvas lands on the same pixels."""
    step = REF_RESOLUTION_STEP
    width = round(math.sqrt(resolution * resolution * ratio) / step) * step
    height = round(math.sqrt(resolution * resolution / ratio) / step) * step
    return max(step, width), max(step, height)


def fit_canvas(width, height, source_ratio=None):
    """The shared compile's canvas -> (width, height, budget) — see
    `REF_RESOLUTION_STEP`.

    `source_ratio` is the picture's ratio when the canvas was taken off a
    picture, and None on a preset aspect. With a picture the canvas becomes
    the encoder's resize of it at the canvas's own budget; the budget steps
    down until that resize fits the per-axis ceiling, since the encoder does
    not know one and a 21:9 sheet at 2048 comes back 2080 wide. Without a
    picture there is nothing to line up with, and the canvas stays.
    """
    from ...compile_image import MAX_SHORT_EDGE

    step = REF_RESOLUTION_STEP
    resolution = round(math.sqrt(width * height) / step) * step
    if source_ratio is None:
        return width, height, resolution
    while True:
        fitted_w, fitted_h = _encoder_size(resolution, source_ratio)
        if max(fitted_w, fitted_h) <= MAX_SHORT_EDGE or resolution <= step:
            return fitted_w, fitted_h, resolution
        resolution -= step


def require_support():
    """Refuse a core that does not know Qwen Image 2.1 yet — see krea2's twin.

    Keyed off what is registered rather than a version number, and off the
    encoder node rather than the CLIPLoader type: the type string is the one
    Qwen Image Edit has loaded through for a year, and what arrived with 2.1 is
    the node that reads the pictures.
    """
    import nodes

    if "TextEncodeQwenImage21" not in nodes.NODE_CLASS_MAPPINGS:
        raise ValueError(
            "This ComfyUI does not know Qwen Image 2.1 yet (no "
            "TextEncodeQwenImage21 node). Update ComfyUI and restart."
        )


def control_supported():
    """Whether this core's `ModelPatchLoader` can load the 2.1 Fun branch.

    Not a node probe: `ZImageFunControlnet` is older than the 2.1 branch and
    sits on cores that would load the file as nothing they know. What arrived
    with it (Comfy-Org/ComfyUI#16519) is the module class the loader builds,
    so that is what is asked. No ComfyUI is a probe that says no, which keeps
    the manifest importable in the pure-Python suites.
    """
    try:
        from comfy.ldm.qwen_image21 import model
    except Exception:      # noqa: BLE001
        return False
    return hasattr(model, "QwenImage21FunControl")


def require_control():
    """Refuse a guide on a core that cannot load the branch — see above."""
    if not control_supported():
        raise ValueError(
            "This ComfyUI cannot load the Qwen Image 2.1 Fun ControlNet yet. "
            "Update ComfyUI and restart, or take the guide off."
        )


def emit_control(graph, payload, weights, model, vae):
    """The Fun ControlNet over `model`, aimed at the payload's guide.

    The guide is cropped to the canvas here, centred, because the patch only
    stretches it: core resizes the hint to the latent's size with no crop, so
    a 4:3 tracing under a 16:9 canvas would come back as a squashed room.
    Lanczos, as the init is scaled.
    """
    from ... import render_image

    control = payload.control
    image = render_image.load_picture(graph, payload, "guide", control["filename"])
    image = graph.node("ImageScale", image=image, upscale_method="lanczos",
                       width=payload.width, height=payload.height,
                       crop="center").out(0)
    patch = graph.node(CONTROL_LOADER, name=weights.get("control")).out(0)
    return graph.node(
        CONTROL_NODE, model=model, model_patch=patch, vae=vae,
        strength=control["strength"], image=image,
        start_percent=control["start"], end_percent=control["end"],
    ).out(0)


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    # One encoder node for both kinds of render. With no pictures the `vae`
    # goes unread and the node encodes the sentence on the text-to-image
    # template; with pictures it resizes each to the canvas's budget, reads
    # it through the vision tower and VAE-encodes it into the reference
    # latents — the pair the weights were trained on.
    images = {f"images.image_{i + 1}": render_image.load_picture(graph, payload, f"ref:{i}", name)
              for i, name in enumerate(payload.refs)}
    encoded = graph.node("TextEncodeQwenImage21", clip=clip, prompt=payload.prompt,
                         negative_prompt="", vae=vae,
                         resolution=payload.ref_resolution, **images)
    # The node encodes the negative whether or not the row will read it —
    # the official graph's own cost, and at cfg 1 the sampler never evaluates
    # it. Wired rather than zeroed so that at a real CFG the unconditional is
    # what the recipe means: the same pictures behind an empty sentence.
    positive, negative = encoded.out(0), encoded.out(1)

    if payload.init is not None and payload.init["denoise"] < 1.0:
        # An explicit init at a partial denoise: the picture encoded, which the
        # 2.1 VAE does as any other, and the leftover noise the row asks for.
        latent, denoise = render_image.emit_latent(graph, payload, vae, "EmptyLatentImage")
    else:
        # Empty at full denoise, *including* the promoted first picture: it
        # already reaches the model as a reference latent, and the official
        # edit template starts from an empty latent for that reason — the
        # encoder's own, at the first picture's resized size, which is what
        # `fit_canvas` made the canvas, so this is the same latent. Core's
        # own `EmptyLatentImage` — it stamps the /8 it was made at, and the
        # sampler rescales an empty latent to the model's /16 and 64 channels,
        # which is how the template itself starts.
        latent = graph.node("EmptyLatentImage", width=payload.width,
                            height=payload.height, batch_size=1).out(0)
        denoise = 1.0

    if payload.control is not None:
        model = emit_control(graph, payload, weights, model, vae)

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
    shared `compile_image.compile_prestage`, handed this module as the family."""
    from ... import compile_image

    return compile_image.compile_prestage(data, sys.modules[__name__],
                                          image_size_lookup)


def emit_still(data, plan, sampling, unique_id):
    """The uniform still surface over the shared `render_image.emit`."""
    from ... import outputs, render_image, settings
    from . import declare

    weights = render_image.ImageWeights.from_blob(data, sys.modules[__name__])
    return render_image.emit(plan, weights, sampling, unique_id,
                             sys.modules[__name__],
                             filename_prefix=outputs.image(
                                 data, settings.image_prefix(declare.ID)))
