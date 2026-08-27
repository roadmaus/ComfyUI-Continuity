"""Ideogram 4.0's own half of an image render: the preset table and the
dual-model sampler branch.

The shared flow is `compile_image.compile_prestage` and `render_image.emit`,
which take this module as the `family`. What stays here is what only Ideogram
knows: its knobs are the official preset table rather than a steps widget
alone (mu and std shape the resolution-shifted schedule, so they belong to the
preset, not to the user), its unconditional branch is a separate checkpoint
behind `DualModelGuider`, and its schedule is `Ideogram4Scheduler`'s — which is
why this branch samples through `SamplerCustomAdvanced` rather than `KSampler`.

The guidance tail is the other thing only Ideogram knows, and the reason this
module carries a copy of the scheduler's arithmetic: the official presets end on
a fixed *number of steps* at a lower guidance weight, and `CFGOverride` takes a
percent. Converting one to the other means knowing where those steps fall on the
schedule, which moves with the preset and with the canvas — see `polish_percent`.
"""

import math
import sys
from statistics import NormalDist

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
    "model pill to Krea 2 or Qwen Image Edit, or clear the style references"
)

# Ideogram's official preset table, verbatim from the shipped ComfyUI template
# (V4_QUALITY_48 / V4_DEFAULT_20 / V4_TURBO_12). mu and std shape the
# resolution-shifted schedule, so they belong to the preset, not to the user.
# `polish` is the tail each preset ends on at the lower guidance weight, in
# steps: "45 steps @ gw=7, then 3 polish steps @ gw=3" and its two siblings.
IDEOGRAM_QUALITIES = {
    "quality": {"steps": 48, "mu": 0.0, "std": 1.5, "polish": 3},
    "default": {"steps": 20, "mu": 0.0, "std": 1.75, "polish": 2},
    "turbo": {"steps": 12, "mu": 0.5, "std": 1.75, "polish": 1},
}
DEFAULT_IDEOGRAM_QUALITY = "default"
# Guidance is 7 on every preset — the preset moves the step count and the
# schedule, never the weight — and drops to 3 for the polish tail so the fine
# steps stop over-sharpening. The 7 is the node's cfg widget; the 3 is constant.
IDEOGRAM_CFG = 7.0
IDEOGRAM_CFG_POLISH = 3.0

# The other speed axis, and the one the preset table cannot reach: a distillation
# LoRA over the same checkpoint, which takes Ideogram down to a handful of steps
# at cfg 1. There is no distilled Ideogram checkpoint to swap to — the presets
# *are* the official fast path — so unlike Krea's pill this one is a LoRA or it
# is nothing, and the compile says so rather than sampling 4 steps of an
# undistilled model at cfg 1 and calling it turbo.
#
# At cfg 1 two things stop being worth their weight: the unconditional branch is
# never evaluated, so its 9.3B file is not loaded at all, and the polish tail has
# no guidance left to drop. The schedule stays the Turbo preset's, which is the
# one shaped for a short run.
TURBO_STEPS = {"draft": 2, "medium": 4, "good": 8}
DEFAULT_TURBO_QUALITY = "medium"
TURBO_QUALITY = "turbo"
TURBO_ROW = {"cfg": 1.0, "sampler_name": "euler"}
TURBO_NEEDS_LORA = (
    "Ideogram 4.0 has no distilled checkpoint — its turbo pill is a "
    "distillation LoRA over the ordinary one. Pick the LoRA, or switch the "
    "quality pill to the Turbo preset instead"
)

# `Ideogram4Scheduler`'s logSNR clamp, mirrored from core's `nodes_ideogram4`.
# Mirrored rather than imported because everything above `emit_graph` in this
# package is pure: the tests run this arithmetic without a ComfyUI to import.
_LOGSNR_MIN = -15.0
_LOGSNR_MAX = 18.0
_NORMAL = NormalDist()


def sigmas(steps, width, height, mu, std):
    """The descending sigmas `Ideogram4Scheduler` will hand the sampler.

    `core.nodes_ideogram4.ideogram4_sigmas` in plain Python: a logit-normal
    schedule whose mean carries a resolution term, which is why the same preset
    lands its steps somewhere else on a 2K canvas than on a 1K one.
    """
    mean = mu + 0.5 * math.log((width * height) / (512 * 512))
    t_min = 1.0 / (1.0 + math.exp(0.5 * _LOGSNR_MAX))
    t_max = 1.0 / (1.0 + math.exp(0.5 * _LOGSNR_MIN))
    out = []
    for i in range(steps + 1):
        u = (steps - i) / steps
        # The quantile blows up at the ends; the clamp below is where both
        # infinities land anyway, so they are taken there directly.
        if u <= 0.0:
            t = t_max
        elif u >= 1.0:
            t = t_min
        else:
            t = 1.0 / (1.0 + math.exp(mean + std * _NORMAL.inv_cdf(u)))
            t = min(max(t, t_min), t_max)
        out.append(1.0 - t)
    out[-1] = 0.0                       # core forces the last sigma to zero
    return out


def polish_percent(steps, polish, width, height, mu, std):
    """Where `CFGOverride` has to start for the last `polish` steps to be it.

    The preset says "the last 3 of 48 steps run at gw=3" and `CFGOverride` takes
    a percent, which it turns straight back into a sigma — Ideogram 4 samples on
    `ModelSamplingDiscreteFlow` at shift 1, where sigma is the timestep, so the
    percent is `1 - sigma`. The boundary is put halfway between the last full-
    guidance step and the first polish one so no rounding can move it a step
    either way.

    A fixed percent cannot do this job: the same 0.7 that gives Turbo its one
    polish step gives Quality seven instead of three, and gives Turbo none at all
    on a 2K canvas.
    """
    if polish <= 0:
        return None
    if polish >= steps:
        return 0.0
    row = sigmas(steps, width, height, mu, std)
    return 1.0 - (row[steps - polish] + row[steps - polish - 1]) / 2.0


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    The schedule block is the preset's, minus its step count: steps ride the
    sampler row like every other family's, so what is left is the shape the
    scheduler is given, the tail the guidance drops over, and whether the
    unconditional branch is worth loading. There is one checkpoint field either
    way — the turbo pill here is a LoRA, not a second file.
    """
    from ...compile import CompileError

    from ...compile_image import turbo_block

    turbo = turbo_block(data, ARCH)
    if turbo.get("on"):
        if not turbo.get("lora"):
            raise CompileError(TURBO_NEEDS_LORA)
        preset = IDEOGRAM_QUALITIES[TURBO_QUALITY]
        return "model", {"mu": preset["mu"], "std": preset["std"],
                         "polish": 0, "uncond": False}

    quality = data.get("quality", DEFAULT_IDEOGRAM_QUALITY)
    if quality not in IDEOGRAM_QUALITIES:
        raise CompileError(f"unknown Ideogram quality preset {quality!r}")
    preset = IDEOGRAM_QUALITIES[quality]
    return "model", {"mu": preset["mu"], "std": preset["std"],
                     "polish": preset["polish"], "uncond": True}


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

    # The polish tail wraps the conditional model, after the LoRAs — it is a
    # sampling wrapper, not a weight patch. Its start is resolved against the
    # schedule this render will actually run, so the preset's "last N steps"
    # stays N steps at any canvas; see `polish_percent`.
    start = polish_percent(sampling.steps, payload.schedule.get("polish", 0),
                           payload.width, payload.height,
                           payload.schedule["mu"], payload.schedule["std"])
    if start is not None:
        model = graph.node("CFGOverride", model=model, cfg=IDEOGRAM_CFG_POLISH,
                           start_percent=start, end_percent=1.0).out(0)

    # Without the unconditional file picked, `DualModelGuider` degrades to
    # ordinary CFG on the one model, which the node itself documents — so that
    # file is optional here too.
    guider_inputs = {"model": model, "positive": positive, "negative": negative,
                     "cfg": sampling.cfg}
    if payload.schedule.get("uncond") and weights.get("uncond_model"):
        guider_inputs["model_negative"] = render_image.emit_unet(
            graph, weights, "uncond_model")
    guider = graph.node("DualModelGuider", **guider_inputs).out(0)

    schedule = graph.node("Ideogram4Scheduler", steps=sampling.steps,
                          width=payload.width, height=payload.height,
                          mu=payload.schedule["mu"],
                          std=payload.schedule["std"]).out(0)
    latent, denoise = render_image.emit_latent(graph, payload, vae,
                                               "EmptyFlux2LatentImage")
    if denoise < 1.0:
        # img2img on a custom schedule: keep the tail of the sigmas and let the
        # noise node start the latent at the truncated schedule's first sigma —
        # the same statement KSampler's denoise makes, said in sigmas.
        schedule = graph.node("SplitSigmasDenoise", sigmas=schedule,
                              denoise=denoise).out(1)

    sampled = graph.node(
        "SamplerCustomAdvanced",
        noise=graph.node("RandomNoise", noise_seed=sampling.seed).out(0),
        guider=guider,
        sampler=graph.node("KSamplerSelect", sampler_name=sampling.sampler_name).out(0),
        sigmas=schedule, latent_image=latent,
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
