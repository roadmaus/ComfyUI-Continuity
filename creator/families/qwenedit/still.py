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
    same thing as zeroing the conditional: the reference latents ride in the
    conditioning, so a zeroed negative removes the pictures from the
    unconditional as well and the guidance then points away from the edit's own
    subject.

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
