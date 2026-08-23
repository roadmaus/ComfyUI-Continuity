"""Krea 2's own half of an image render: the constants and the sampler branch.

The shared flow — prompt, triggers, references, init image, the /16 canvas —
is `compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only Krea 2 knows: RAW is the base checkpoint and samples with real CFG;
Turbo is an 8-step distillation at cfg 1; style references go through core's
Qwen-edit encoder and swap the shift onto `ModelSamplingFlux`, exactly as the
official reference template wires it.
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

# The reference template's shift, applied only on the style-reference branch —
# plain t2i leaves the shift the checkpoint detection already set (1.15).
KREA_REF_SHIFT = {"max_shift": 1.15, "base_shift": 0.5}
KREA_REF_METHOD = "index_timestep_zero"


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, mu, std).

    Which file the DiT loads from is the turbo pill's call; Krea 2 samples on
    the row's own schedule, so it has no mu/std to shape one with.
    """
    turbo = data.get("turbo") or {}
    return ("turbo_model" if turbo.get("on") else "model"), None, None


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
                              reference_latents_method=KREA_REF_METHOD).out(0)
        model = graph.node("ModelSamplingFlux", model=model,
                           width=payload.width, height=payload.height,
                           **KREA_REF_SHIFT).out(0)
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

    weights = render_image.ImageWeights.from_blob(data, sys.modules[__name__])
    return render_image.emit(plan, weights, sampling, unique_id,
                             sys.modules[__name__],
                             filename_prefix=outputs.image(
                                 data, settings.image_prefix()))
