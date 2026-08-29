"""Flux 2 Klein's own half of an image render: the constants and the sampler
branch.

The shared flow — prompt, triggers, references, the /16 canvas — is
`compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only Klein knows: its schedule is `Flux2Scheduler`'s, a function of the
step count and the canvas with nothing left for a scheduler widget to say,
which is why this branch samples through `SamplerCustomAdvanced` rather than
`KSampler`; its references arrive as VAE latents chained onto the conditioning
(`ReferenceLatent`), not as vision tokens, so the text encoder is the plain
text-only Qwen3; and its speed axis is the 4-step distilled checkpoint BFL
publishes beside the base one.

Everything it emits is core's, taken from the official ComfyUI Flux.2 Klein
templates rather than invented. One family covers both sizes: 4B and 9B are
the same architecture and the same graph, so which one runs is which files
were picked — the checkpoint and the Qwen3 encoder that matches it.
"""

import sys

ARCH = "flux2klein"

# Which weights fields this architecture has. Like Krea 2, the speed axis is a
# second checkpoint: BFL publishes the distillation as its own file, at both
# sizes, and there is no LoRA extraction of it.
FIELDS = ("model", "turbo_model", "clip", "vae")

# What CLIPLoader calls the Qwen3 encoder these weights read prose through.
CLIP_TYPE = "flux2"

# References are native: the base weights were trained to read pictures chained
# into the conditioning as reference latents, single- or multi-reference, with
# no adapter to add first.
TAKES_REFS = True

# What to call them — an edit family's noun, not Krea 2's. `Picture 1` is the
# thing the instruction is about, read for what is in it rather than for its
# look, and "style reference" would name the one property the model is not
# being asked about. (BFL's own multi-reference example says "Figure 1"; the
# citation label stays the pack's shared `Picture N`, which the model reads the
# same way — plain prose naming a slot — and which every chip in the UI
# already says.)
REFS_NOUN = ("picture", "pictures")

# ...and unlike the encoder-slot families there is no node with three image
# inputs behind this: `ReferenceLatent` chains, and the official template's own
# note is "follow this pattern to add more". Three is where this pack caps it —
# the UI's reference bar is built around three slots, and every picture past
# the first is another full-resolution latent the model attends over.
REFS_LIMIT = 3
REFS_LIMIT_REASON = ("three is where this pack caps the reference chain — "
                     "every picture is another full-resolution latent the "
                     "model attends over")

# References reach the model as VAE latents, not through a vision tower: the
# matched encoders (qwen_3_4b, qwen_3_8b) are the text-only cut, and that is
# correct rather than the silent mis-pick `render_image.check_vision` exists to
# catch on the VL families.
REFS_NEED_VISION = False

# An edit is a picture being changed, so `Picture 1` also decides the canvas —
# the shared compile promotes it to the init at denoise 1.0 and the render
# comes out its shape. Unlike Qwen Image Edit the official graph starts the
# latent *empty* (the instruction reaches the model through the reference
# conditioning alone), and `emit_graph` honours that: a full-denoise init is
# emitted as the template's own empty latent rather than an encode about to be
# noised away. `start_blank` and an explicit init win exactly as they do there.
EDITS_FIRST_REF = True

# What each checkpoint wants from the sampler row — the shipped templates' own
# numbers. Base is undistilled and runs real CFG; the distillation runs at 1.
# No scheduler entry on either: the schedule is `Flux2Scheduler`'s, derived
# from the steps and the canvas, and a scheduler widget would be a control
# nothing reads.
KLEIN_BASE = {"steps": 20, "cfg": 5.0, "sampler_name": "euler"}
KLEIN_TURBO = {"cfg": 1.0, "sampler_name": "euler"}
TURBO_STEPS = {"draft": 2, "medium": 4, "good": 6}
DEFAULT_TURBO_QUALITY = "medium"


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    Which file the DiT loads from is the turbo pill's call, and that is the
    whole decision: the schedule is `Flux2Scheduler`'s own, a function of the
    sampler row and the canvas, so there is no shift to put right and nothing
    for the schedule block to carry.
    """
    from ...compile_image import turbo_block

    if turbo_block(data, ARCH).get("on"):
        return "turbo_model", {}
    return "model", {}


def max_refs(data):
    """`(references this render may carry, why)` — see `REFS_LIMIT`."""
    return REFS_LIMIT, REFS_LIMIT_REASON


def require_support():
    """Refuse a core that does not know Flux 2 yet — see krea2's twin.

    Keyed off what is registered rather than a version number: `CLIPLoader`
    learning the type is what makes the encoder loadable, and the scheduler is
    the one node this branch cannot sample without.
    """
    import nodes

    declared = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()
    types = declared.get("required", {}).get("type", [[]])[0]
    if "flux2" not in types or "Flux2Scheduler" not in nodes.NODE_CLASS_MAPPINGS:
        raise ValueError(
            "This ComfyUI does not know Flux 2 yet (no 'flux2' CLIPLoader "
            "type, or no Flux2Scheduler node). Update ComfyUI and restart."
        )


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)
    # The unconditional the row can use: at real CFG an empty-prompt encode —
    # the base template's own negative — and at cfg 1, where the guider never
    # evaluates it, a zeroed copy instead of an encode nothing reads. The
    # reference latents below are chained onto both branches either way, which
    # is the template's shape: at real CFG the guidance is then a difference
    # between two predictions that both saw the pictures.
    if sampling.cfg == 1.0:
        negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)
    else:
        negative = graph.node("CLIPTextEncode", clip=clip, text="").out(0)

    # Each picture: scaled to the model's ~1MP working size, VAE-encoded once,
    # and chained into both conditionings as a reference latent. No encoder
    # slots and no method to pick — the base weights read the chain natively.
    for name in payload.refs:
        image = graph.node("LoadImage", image=name).out(0)
        # resolution_steps is required on current cores and gets no default
        # injected for a prompt that omits it, so it is always sent; 16 is the
        # family's own snap, the same one the canvas takes.
        scaled = graph.node("ImageScaleToTotalPixels", image=image,
                            upscale_method="lanczos", megapixels=1.0,
                            resolution_steps=16).out(0)
        latent = graph.node("VAEEncode", pixels=scaled, vae=vae).out(0)
        positive = graph.node("ReferenceLatent", conditioning=positive,
                              latent=latent).out(0)
        negative = graph.node("ReferenceLatent", conditioning=negative,
                              latent=latent).out(0)

    guider = graph.node("CFGGuider", model=model, positive=positive,
                        negative=negative, cfg=sampling.cfg).out(0)
    # The schedule is the model's own, shaped by the canvas — the reason the
    # sampler row has no scheduler widget on this family.
    sigmas = graph.node("Flux2Scheduler", steps=sampling.steps,
                        width=payload.width, height=payload.height).out(0)

    if payload.init is not None and payload.init["denoise"] < 1.0:
        # img2img on a custom schedule: keep the tail of the sigmas —
        # Ideogram's arrangement, the same statement KSampler's denoise makes.
        latent, denoise = render_image.emit_latent(graph, payload, vae,
                                                   "EmptyFlux2LatentImage")
        sigmas = graph.node("SplitSigmasDenoise", sigmas=sigmas,
                            denoise=denoise).out(1)
    else:
        # Empty at full denoise, *including* the promoted first picture: it
        # already reaches the model as a reference latent, and at the
        # schedule's first sigma an encoded init is noise with an encoder pass
        # behind it. The official edit template's empty latent, kept.
        latent = graph.node("EmptyFlux2LatentImage", width=payload.width,
                            height=payload.height, batch_size=1).out(0)

    sampled = graph.node(
        "SamplerCustomAdvanced",
        noise=graph.node("RandomNoise", noise_seed=sampling.seed).out(0),
        guider=guider,
        sampler=graph.node("KSamplerSelect",
                           sampler_name=sampling.sampler_name).out(0),
        sigmas=sigmas, latent_image=latent,
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
