"""Krea 2's own half of an image render: the constants and the sampler branch.

The shared flow — prompt, triggers, references, init image, the /16 canvas —
is `compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only Krea 2 knows: RAW is the base checkpoint and samples with real CFG;
Turbo is an 8-step distillation at cfg 1; the two want different timestep shifts
and this is where that is put right (`KREA_RAW_SHIFT`); and style references go
through core's Qwen-edit encoder, which the model only reads with one of the
reference LoRAs patched on.
"""

import sys

ARCH = "krea2"

# Which weights fields this architecture has. There is no second branch — the
# speed axis is the Turbo checkpoint.
FIELDS = ("model", "turbo_model", "clip", "vae")

# What CLIPLoader calls the Qwen3-VL-4B encoder.
CLIP_TYPE = "krea2"

# Style references are read: core's Qwen-edit encoder conditions on up to three
# images, which Krea 2 was post-trained against.
TAKES_REFS = True

# What each checkpoint wants from the sampler row. RAW is undistilled and runs
# real CFG; Turbo is distilled and runs at 1. These are what the turbo pill
# writes into the widgets and what a fresh node defaults to.
KREA_RAW = {"steps": 52, "cfg": 3.5, "sampler_name": "euler", "scheduler": "simple"}
KREA_TURBO = {"cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}
TURBO_STEPS = {"draft": 4, "medium": 6, "good": 8}
DEFAULT_TURBO_QUALITY = "good"

# The timestep shift, which is not the same number for the two checkpoints and
# is the one place this pack corrects what a bare load would do.
#
# `ModelSamplingFlux` spells its `shift` as Krea's `mu`: the sigma it builds is
# `exp(mu) / (exp(mu) + (1/t - 1))`. Krea's own inference derives that mu from
# the canvas — `--y1 0.5` at its smallest resolution rising to `--y2 1.15` at
# its largest — and pins it only for Turbo, where `--mu 1.15` is the schedule
# the distillation was fitted to. Core detects one arch for both files and so
# gives both Turbo's pin, which leaves RAW sampling a 1K canvas on a schedule
# meant for a 2K distilled render.
#
# So RAW gets the ramp back and Turbo keeps the pin. The ramp is stated in
# `ModelSamplingFlux`'s coordinates rather than Krea's: that node interpolates
# between 256 and 4096 *latent tokens* (256x256 and 1024x1024) while Krea's line
# runs to 1280x1280, so RAW_MAX_SHIFT is Krea's line read at 4096 tokens. Same
# line, same value at every canvas — 0.906 lands the 2.5x effective shift at
# 1024x1024 that Krea 2's own schedule has there.
KREA_RAW_SHIFT = {"max_shift": 0.90625, "base_shift": 0.5}
KREA_TURBO_SHIFT = 1.15

# How reference latents are laid into the token sequence, and the reason this is
# a choice rather than a constant.
#
# Krea 2 is detected with no default reference method at all: core reads the
# attached images only when one is named, because the base weights never learned
# to. What did learn to are the reference LoRAs trained against them, and they do
# not agree on the layout — the ai-toolkit edit LoRAs condition their reference
# tokens at timestep zero, the identity-edit ones index them like any other
# frame. Picking the wrong one is not an error anywhere; it is a render that
# quietly ignores half of what it was given.
#
# So the method rides with the adapter, and the default is the one the two
# published Krea 2 edit LoRAs use.
REF_METHODS = ("index_timestep_zero", "index")
DEFAULT_REF_METHOD = REF_METHODS[0]

# ...and references with no adapter at all are refused. Every way of reading a
# reference on Krea 2 is a LoRA, so an empty stack is not a weaker render, it is
# the images going nowhere.
REFS_NEED_LORA = (
    "Krea 2 reads style references only through a reference LoRA — the base "
    "weights were never trained to. Add one to the stack (krea2_style_reference "
    "for style, an ai-toolkit edit LoRA for edits), or clear the references"
)


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    Which file the DiT loads from is the turbo pill's call, and the shift the
    sampler runs on follows it: RAW takes the canvas-derived ramp, Turbo the
    constant it was distilled against. See `KREA_RAW_SHIFT`.
    """
    from ...compile_image import turbo_block

    turbo = turbo_block(data, ARCH)
    if turbo.get("on"):
        # Two ways to be fast, and they load different files. The distillation
        # ships as a checkpoint *and* as an SVD extraction of the same weight
        # difference; with the LoRA picked the DiT stays RAW and the stack does
        # the distilling, which is what lets a content LoRA ride along and keeps
        # one 24 GB file resident when the pill is thrown back and forth. Either
        # way the schedule is the one the distillation was fitted to.
        field = "model" if turbo.get("lora") else "turbo_model"
        return field, {"shift": KREA_TURBO_SHIFT, "ref_method": ref_method(data)}
    return "model", {**KREA_RAW_SHIFT, "ref_method": ref_method(data)}


def ref_method(data):
    """Which reference layout this render asks for. See `REF_METHODS`."""
    from ...compile import CompileError

    method = data.get("ref_method") or DEFAULT_REF_METHOD
    if method not in REF_METHODS:
        raise CompileError(f"unknown Krea 2 reference method {method!r}")
    return method


def require_support():
    """Refuse a core that does not know Krea 2 yet.

    Both image models are native in current ComfyUI; a stale install fails
    inside the loader with a shape mismatch nobody can read, so this says it up
    front. Keyed off what is actually registered rather than a version number.
    """
    import nodes

    declared = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()
    types = declared.get("required", {}).get("type", [[]])[0]
    if "krea2" not in types:
        raise ValueError(
            "This ComfyUI does not know Krea 2 yet (CLIPLoader has no "
            "'krea2' type). Update ComfyUI and restart."
        )


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    # The shift, before anything else touches the model: RAW's ramp is a
    # function of the canvas, and Turbo's pin is already what the checkpoint
    # detected, so the node is emitted for one of them and not the other —
    # the same "at the default value, emit nothing" rule the video row keeps.
    ramp = payload.schedule
    if "max_shift" in ramp:
        model = graph.node("ModelSamplingFlux", model=model,
                           width=payload.width, height=payload.height,
                           max_shift=ramp["max_shift"],
                           base_shift=ramp["base_shift"]).out(0)

    if payload.refs:
        # The Qwen-edit encoder reads up to three references: it feeds them to
        # the text encoder as vision tokens *and* VAE-encodes them into the
        # conditioning's reference latents, which is the pair Krea 2 was
        # post-trained against. The method node picks the variant the official
        # workflow uses.
        images = {f"image{i + 1}": graph.node("LoadImage", image=name).out(0)
                  for i, name in enumerate(payload.refs)}
        positive = graph.node("TextEncodeQwenImageEditPlus", clip=clip,
                              prompt=payload.prompt, vae=vae, **images).out(0)
        positive = graph.node("FluxKontextMultiReferenceLatentMethod",
                              conditioning=positive,
                              reference_latents_method=payload.schedule["ref_method"]).out(0)
    else:
        positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)

    # Zeroed-out conditioning as the negative on both checkpoints: at Turbo's
    # cfg 1.0 it is skipped outright, and RAW's cfg 3.5 wants an unconditional,
    # not a second prompt.
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
