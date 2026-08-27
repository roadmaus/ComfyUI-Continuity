"""Qwen Image Edit's own half of an image render: the constants and the
sampler branch.

The shared flow — prompt, triggers, references, the /16 canvas — is
`compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is what
only this architecture knows: the schedule shift core does not detect, the
CFG-norm the published workflow samples through, the paired empty-prompt
negative that a real CFG run wants, and the fact that the first reference is
also the picture being edited.

Everything it emits is core's. Qwen-Image-Edit has been native in ComfyUI since
`comfy_extras/nodes_qwen.py`, and Krea 2 already borrows its encoder for style
references — this family is the same encoder pointed at the weights it was
built for.
"""

import sys

ARCH = "qwenedit"

# Which weights fields this architecture has. One DiT: the speed axis is a
# Lightning LoRA, not a second checkpoint, so there is nothing to route between.
FIELDS = ("model", "clip", "vae")

# What CLIPLoader calls the Qwen2.5-VL-7B encoder.
CLIP_TYPE = "qwen_image"

# References are the whole point of this family: `TextEncodeQwenImageEditPlus`
# feeds up to three images to the encoder as vision tokens *and* VAE-encodes
# them into the conditioning's reference latents, which is the pair the edit
# post-training was fitted to. Unlike Krea 2 there is no adapter to add first —
# the base weights read them, which is what "edit" means here.
TAKES_REFS = True

# What to call them, which is not what Krea 2 calls its own — see that family's
# `REFS_NOUN`. Nothing attached here is a style input: `Picture 1` is the thing
# being changed and `Picture 2` and `Picture 3` are pictures the instruction
# names, read for what is in them. "Style reference" would describe the one
# property of these images the model is not being asked about.
REFS_NOUN = ("picture", "pictures")

# ...and one of those pictures may be a ControlNet guide, which is the part of
# these weights that has no node anywhere.
#
# 2509 and 2511 have ControlNet *built in*: they were post-trained to recognise a
# depth pass, an edge map or a pose skeleton arriving in an ordinary image slot
# and to build the render around it. There is nothing to load and nothing to
# apply — no `ControlNetLoader`, no `QwenImageDiffsynthControlnet`, no strength
# to set. Core's shipped 2509 and 2511 blueprints are the evidence: three plain
# image inputs and no control input among them.
#
# So the graph a guide render emits is the graph a reference render already
# emits, and what the pack has to get right is which slot the tracing bench
# hands its file to. As the init image — where every guide went before this — an
# edge map is a picture being restyled at denoise 0.65, and what comes back is a
# tidied edge map. As `Picture 1` it is what the render is aimed at.
#
# The three tracings named on the model card, and no more: `lines` and `blocks`
# are edge-ish and tone-ish and were not trained on, and a guide the weights
# never learned reads as a picture of a drawing.
NATIVE_CONTROL = ("depth", "edges", "pose")
# The first edition has none of it — the built-in ControlNet arrived with 2509.
CONTROL_EDITIONS = ("2509", "2511")
CONTROL_NEEDS_EDITION = (
    "A ControlNet guide is read by the 2509 and 2511 weights, which were "
    "post-trained on depth, edge and pose maps arriving as a picture. The first "
    "edition never learned to, and would edit the guide instead of following "
    "it — move the edition pill, or attach the guide as an ordinary picture"
)

# ...but not the same number of them on every file that loads here. The encoder
# has three slots on all of them; what changed between editions is what the DiT
# was post-trained to *read*, and the first Qwen-Image-Edit weights were fitted
# on a single picture. Three references on those is not a worse render, it is
# two pictures the model has no idea what to do with.
#
# Nothing in the checkpoint says which edition it is — 2509 and base are the
# same architecture and differ only in post-training, and core's own detection
# tells 2511 apart by a marker buffer the other two share nothing like. So the
# edition is a declared field with a filename guess behind it in the UI, and the
# compile reads what the field says. Wrong-by-default in one direction only:
# an unrecognised filename is read as the edition most people are running.
EDITIONS = {"2511": 3, "2509": 3, "base": 1}
DEFAULT_EDITION = "2511"
# Which needle in a filename means which edition, checked in this order. The
# frontend fills the field from these; a name that says nothing leaves the
# default standing.
EDITION_HINTS = (("2511", "2511"), ("2509", "2509"))
EDITION_REASON = {
    3: "the Qwen edit encoder the model reads them through has exactly three "
       "image slots",
    1: "the first Qwen-Image-Edit weights were post-trained on a single "
       "picture — switch the edition to 2509 or 2511 for three",
}

# ...and the first of them is not only a reference. An edit is a picture being
# changed, so `Picture 1` is also what the render starts from: the shared
# compile promotes it to the init image at denoise 1.0, which is the shape the
# official workflow has (`VAEEncode` of the first image straight into the
# sampler) and, on the way, the reason the canvas follows that picture's aspect
# instead of the aspect pill. An explicit init still wins — see
# `compile_image.compile_prestage`, which is where this flag is read.
EDITS_FIRST_REF = True

# What the checkpoint wants from the sampler row with nothing distilled on it.
# The shipped template's own numbers for Qwen-Image-Edit-2509; the 2511 template
# asks 40 steps at the same guidance, and Qwen's own card 40-50, so the steps
# pill is the place to spend more where a render is worth it.
QWEN_BASE = {"steps": 20, "cfg": 4.0, "sampler_name": "euler", "scheduler": "simple"}

# The timestep shift, which core does not detect for these weights: `QwenImage`
# in `supported_models.py` carries `shift: 1.15`, and every published Qwen-Image
# workflow — t2i, edit 2509, edit 2511 — samples through `ModelSamplingAuraFlow`
# at ~3. So the node is emitted on every render rather than only when something
# moved it: at 1.15 the schedule spends its steps in the wrong place, and no
# widget on this node says so.
#
# 3.0 is the 2509 template's; the 2511 template asks 3.1, which moves sigma by
# under a percent at mid-schedule. One number for both files rather than a guess
# read off a filename.
AURAFLOW_SHIFT = 3.0

# `CFGNorm` rescales the guided prediction back to the conditional's norm, and
# the templates sample through it on both the distilled and the undistilled
# path. Emitted unconditionally for the same reason: at cfg 1 it is arithmetic
# on a ratio that is exactly 1 and does nothing, and at real CFG it is part of
# the recipe rather than a control anybody set.
CFGNORM_STRENGTH = 1.0

# The speed axis, and like Ideogram's it is a LoRA or it is nothing: there is no
# distilled Qwen-Image-Edit checkpoint, there are the Lightning distillations of
# the ordinary one. They are published at four and at eight steps, which is what
# the ladder's ends are; the middle is for a run that wants a little more than
# the 4-step LoRA's own number.
TURBO_STEPS = {"draft": 4, "medium": 6, "good": 8}
DEFAULT_TURBO_QUALITY = "draft"
TURBO_ROW = {"cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}
TURBO_NEEDS_LORA = (
    "Qwen Image Edit has no distilled checkpoint — its turbo pill is a "
    "Lightning LoRA over the ordinary one. Pick the LoRA, or leave the switch "
    "off and sample the full row"
)


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    One checkpoint field either way: the turbo pill here is a LoRA, and the
    schedule it runs on is the same one — the Lightning distillations were
    fitted against the shift the ordinary checkpoint samples at, so unlike
    Krea's pair there is nothing for the switch to move.
    """
    from ...compile import CompileError
    from ...compile_image import turbo_block

    turbo = turbo_block(data, ARCH)
    if turbo.get("on") and not turbo.get("lora"):
        raise CompileError(TURBO_NEEDS_LORA)
    return "model", {"shift": AURAFLOW_SHIFT}


def edition(data):
    """Which Qwen-Image-Edit release this blob says it is loading."""
    from ...compile import CompileError

    name = data.get("edition") or DEFAULT_EDITION
    if name not in EDITIONS:
        raise CompileError(f"unknown Qwen Image Edit edition {name!r}")
    return name


def max_refs(data):
    """`(references this edition reads, why)` — see `EDITIONS`."""
    limit = EDITIONS[edition(data)]
    return limit, EDITION_REASON[limit]


def reads_guides(data):
    """Does the edition this blob names read a control map as a picture?"""
    return edition(data) in CONTROL_EDITIONS


def check_refs(data, refs, loras):
    """What has to be true before these pictures are worth sampling.

    One thing, and it is the guide: the built-in ControlNet arrived with 2509,
    so a tracing handed to the first edition is a depth pass about to be edited
    rather than followed. Read off the blob's own `refs` rather than the parsed
    pair list, because the role is this family's business and nothing between
    here and the graph has any use for it — the guide *is* `Picture N`, wired
    exactly as every other picture is, which is the whole reason this needed no
    node.
    """
    from ...compile import CompileError

    if reads_guides(data):
        return
    for item in data.get("refs") or []:
        if isinstance(item, dict) and item.get("role") == "guide":
            raise CompileError(CONTROL_NEEDS_EDITION)


def require_support():
    """Refuse a core that does not know Qwen Image Edit yet — see krea2's twin.

    Keyed off what is registered rather than a version number, and off the
    encoder rather than the sampler nodes: `CLIPLoader` learning the type is
    what makes these weights loadable at all.
    """
    import nodes

    declared = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()
    types = declared.get("required", {}).get("type", [[]])[0]
    if CLIP_TYPE not in types:
        raise ValueError(
            "This ComfyUI does not know Qwen Image yet (CLIPLoader has no "
            "'qwen_image' type). Update ComfyUI and restart."
        )


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    model = graph.node("ModelSamplingAuraFlow", model=model,
                       shift=payload.schedule["shift"]).out(0)
    model = graph.node("CFGNorm", model=model, strength=CFGNORM_STRENGTH).out(0)

    if payload.refs:
        images = {f"image{i + 1}": graph.node("LoadImage", image=name).out(0)
                  for i, name in enumerate(payload.refs)}
        positive = graph.node("TextEncodeQwenImageEditPlus", clip=clip,
                              prompt=payload.prompt, vae=vae, **images).out(0)
        negative = _negative(graph, sampling, positive, clip, vae, images)
    else:
        # An edit model asked to draw from nothing, which is a legitimate thing
        # to ask it: these weights are Qwen-Image post-trained, not replaced.
        # Through `CLIPTextEncode` rather than the edit encoder, because with no
        # images the edit encoder's only contribution is a system prompt about
        # an input image there isn't one of.
        positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)
        negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)

    latent, denoise = render_image.emit_latent(graph, payload, vae,
                                               "EmptySD3LatentImage")
    sampled = graph.node(
        "KSampler", model=model, positive=positive, negative=negative,
        latent_image=latent, seed=sampling.seed, steps=sampling.steps,
        cfg=sampling.cfg, sampler_name=sampling.sampler_name,
        scheduler=sampling.scheduler, denoise=denoise,
    )
    render_image.emit_tail(graph, sampled.out(0), vae, unique_id, filename_prefix)


def _negative(graph, sampling, positive, clip, vae, images):
    """The unconditional branch, in the shape the row it is sampled against
    can use.

    At real CFG that is a second pass of the edit encoder over the *same*
    images with an empty prompt — what the published workflow does, and not the
    same thing as zeroing the conditional. `ConditioningZeroOut` copies the
    conditioning dict, so the reference latents do survive into the negative;
    what does not is the encoder's reading of the pictures, which becomes a
    block of zeros. The guidance is then a difference between a grounded
    prediction and one made against a text stream the model never saw in
    training, which is not the unconditional this edit post-training was fitted
    against.

    At cfg 1 the sampler never evaluates the negative, and a second 7B encoder
    pass to build a tensor nothing reads is a minute of a Lightning render's
    four steps. So the distilled path gets the zeroed copy instead — the same
    trade Krea 2's branch makes, said here for the one row that needs it.
    """
    if sampling.cfg == 1.0:
        return graph.node("ConditioningZeroOut", conditioning=positive).out(0)
    return graph.node("TextEncodeQwenImageEditPlus", clip=clip, prompt="",
                      vae=vae, **images).out(0)


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
