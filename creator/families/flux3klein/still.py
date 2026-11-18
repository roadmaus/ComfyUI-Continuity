"""FLUX 3 Image Klein's own half of an image render: the constants and the
sampler branch.

The shared flow — prompt, triggers, references, the /16 canvas — is
`compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only Klein 3 knows: its references arrive as Flux 2 VAE latents chained
onto the conditioning (`ReferenceLatent`), the way Flux 2 Klein's do, and its
text encoder is Qwen3-VL-4B read as text only; and the checkpoint is a flow
map, step-distilled to 16 steps at cfg 1.

Everything it emits is core's (Comfy-Org/ComfyUI#17064). The schedule is not
emitted at all: `supported_models.Flux3` carries the reference shift, and the
flow map takes the time each step jumps to from the sampler's own sigmas, so
`simple` over that shift is the whole statement. No scheduler node and no
shift node.

One checkpoint and no turbo pill: the distilled Klein is the file BFL ships
for editing and generation. Klein Base (50 steps, cfg 3.5) loads in the same
slot, since core tells the two apart by the file, with the row raised by hand.
"""

import sys

ARCH = "flux3klein"

FIELDS = ("model", "clip", "vae")

# Which VAE the `vae` field has to hold, checked off the file's header before
# the render is queued — see `vaekind`. The Flux 2 VAE: BFL's `ae.safetensors`
# for Klein 3 is that autoencoder.
VAE_KIND = "flux2"

# What CLIPLoader calls the Qwen3-VL-4B encoder these weights read prose
# through.
CLIP_TYPE = "flux3"

# References are native: the weights read pictures chained into the
# conditioning as reference latents, with no adapter to add first.
TAKES_REFS = True

# An edit family's noun — see Flux 2 Klein's.
REFS_NOUN = ("picture", "pictures")

# BFL's own limit: "combine up to 10 references".
REFS_LIMIT = 10
REFS_LIMIT_REASON = "ten is as many references as FLUX 3 Image Klein was built to combine"

# References reach the model as VAE latents, not through the vision tower:
# core's `flux3` type reads Qwen3-VL as text only, so a text-only cut of the
# encoder is as good as the full one here.
REFS_NEED_VISION = False

# `Picture 1` decides the canvas when the blob asks — Flux 2 Klein's
# arrangement, empty latent at full denoise included (`emit_graph`).
EDITS_FIRST_REF = True

# The flow map's row, from the core PR and BFL's card: euler, 16 steps, no
# guidance.
KLEIN3 = {"steps": 16, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}

# Each picture's working size before it is encoded — Flux 2 Klein's.
REFS_MEGAPIXELS = 1.0


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    Nothing to decide: one checkpoint, and the schedule is core's detection.
    """
    return "model", {}


def max_refs(data):
    """`(references this render may carry, why)` — see `REFS_LIMIT`."""
    return REFS_LIMIT, REFS_LIMIT_REASON


def require_support():
    """Refuse a core that does not know FLUX 3 Image yet — see krea2's twin.

    Keyed off what is registered rather than a version number: `CLIPLoader`
    learning the type arrived with the model.
    """
    import nodes

    declared = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()
    types = declared.get("required", {}).get("type", [[]])[0]
    if CLIP_TYPE not in types:
        raise ValueError(
            "This ComfyUI does not know FLUX 3 Image yet (no 'flux3' "
            "CLIPLoader type). Update ComfyUI and restart."
        )


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)
    # At cfg 1 the sampler never evaluates the unconditional; Klein Base at
    # real CFG gets the empty-prompt encode, with the pictures chained onto it
    # below the same as onto the positive.
    if sampling.cfg == 1.0:
        negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)
    else:
        negative = graph.node("CLIPTextEncode", clip=clip, text="").out(0)

    for slot, name in enumerate(payload.refs):
        image = render_image.load_picture(graph, payload, f"ref:{slot}", name)
        scaled = graph.node("ImageScaleToTotalPixels", image=image,
                            upscale_method="lanczos",
                            megapixels=REFS_MEGAPIXELS,
                            resolution_steps=16).out(0)
        latent = graph.node("VAEEncode", pixels=scaled, vae=vae).out(0)
        positive = graph.node("ReferenceLatent", conditioning=positive,
                              latent=latent).out(0)
        negative = graph.node("ReferenceLatent", conditioning=negative,
                              latent=latent).out(0)

    if payload.init is not None and payload.init["denoise"] < 1.0:
        latent, denoise = render_image.emit_latent(graph, payload, vae,
                                                   "EmptyFlux2LatentImage")
    else:
        # Empty at full denoise, including the promoted first picture: it
        # already reaches the model as a reference latent.
        latent = graph.node("EmptyFlux2LatentImage", width=payload.width,
                            height=payload.height, batch_size=1).out(0)
        denoise = 1.0

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
