"""Ideogram 4.0's own half of an image render: the preset table and the
dual-model sampler branch.

The shared flow is `compile_image.compile_prestage` and `render_image.emit`,
which take this module as the `family`. What stays here is what only Ideogram
knows: its knobs are the official preset table rather than a steps widget
alone (mu and std shape the resolution-shifted schedule, so they belong to the
preset, not to the user), its unconditional branch is a separate checkpoint
behind `DualModelGuider`, and its schedule is `Ideogram4Scheduler`'s — which is
why this branch samples through `SamplerCustomAdvanced` rather than `KSampler`.
"""

import sys

ARCH = "ideogram4"

# Which weights fields this architecture has. No distilled checkpoint — the
# speed axis is the preset table; the second file is the unconditional branch.
FIELDS = ("model", "uncond_model", "clip", "vae")

# What CLIPLoader calls the Qwen3-VL-8B encoder.
CLIP_TYPE = "ideogram4"

# The model reads no reference conditioning at all; a render that silently
# ignored attached images is the failure this package exists to avoid, so the
# shared compile refuses them with this.
TAKES_REFS = False
REFS_REFUSAL = (
    "Ideogram 4.0 has no local reference conditioning — switch the "
    "model pill to Krea 2, or clear the style references"
)

# Ideogram's official preset table, verbatim from the shipped ComfyUI template
# (V4_QUALITY_48 / V4_DEFAULT_20 / V4_TURBO_12). mu and std shape the
# resolution-shifted schedule, so they belong to the preset, not to the user.
IDEOGRAM_QUALITIES = {
    "quality": {"steps": 48, "mu": 0.0, "std": 1.5},
    "default": {"steps": 20, "mu": 0.0, "std": 1.75},
    "turbo": {"steps": 12, "mu": 0.5, "std": 1.75},
}
DEFAULT_IDEOGRAM_QUALITY = "default"
# The template's guidance: cfg 7 for most of the trajectory, dropped to 3 over
# the last 30% so the fine steps stop over-sharpening. The 7 is the node's cfg
# widget; the late drop is constant wiring.
IDEOGRAM_CFG = 7.0
IDEOGRAM_CFG_LATE = {"cfg": 3.0, "start_percent": 0.7, "end_percent": 1.0}


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, mu, std)."""
    from ...compile import CompileError

    quality = data.get("quality", DEFAULT_IDEOGRAM_QUALITY)
    if quality not in IDEOGRAM_QUALITIES:
        raise CompileError(f"unknown Ideogram quality preset {quality!r}")
    preset = IDEOGRAM_QUALITIES[quality]
    return "model", preset["mu"], preset["std"]


def require_support():
    """Refuse a core that does not know Ideogram 4 yet — see krea2's twin."""
    import nodes

    if "Ideogram4Scheduler" not in nodes.NODE_CLASS_MAPPINGS:
        raise ValueError(
            "This ComfyUI does not know Ideogram 4 yet (no Ideogram4Scheduler "
            "node). Update ComfyUI and restart."
        )


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)
    negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)

    # The late-cfg drop wraps the conditional model, after the LoRAs — it is a
    # sampling wrapper, not a weight patch.
    model = graph.node("CFGOverride", model=model, **IDEOGRAM_CFG_LATE).out(0)

    # Without the unconditional file picked, `DualModelGuider` degrades to
    # ordinary CFG on the one model, which the node itself documents — so that
    # file is optional here too.
    guider_inputs = {"model": model, "positive": positive, "negative": negative,
                     "cfg": sampling.cfg}
    if weights.get("uncond_model"):
        guider_inputs["model_negative"] = render_image.emit_unet(
            graph, weights, "uncond_model")
    guider = graph.node("DualModelGuider", **guider_inputs).out(0)

    sigmas = graph.node("Ideogram4Scheduler", steps=sampling.steps,
                        width=payload.width, height=payload.height,
                        mu=payload.mu, std=payload.std).out(0)
    latent, denoise = render_image.emit_latent(graph, payload, vae,
                                               "EmptyFlux2LatentImage")
    if denoise < 1.0:
        # img2img on a custom schedule: keep the tail of the sigmas and let the
        # noise node start the latent at the truncated schedule's first sigma —
        # the same statement KSampler's denoise makes, said in sigmas.
        sigmas = graph.node("SplitSigmasDenoise", sigmas=sigmas,
                            denoise=denoise).out(1)

    sampled = graph.node(
        "SamplerCustomAdvanced",
        noise=graph.node("RandomNoise", noise_seed=sampling.seed).out(0),
        guider=guider,
        sampler=graph.node("KSamplerSelect", sampler_name=sampling.sampler_name).out(0),
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
