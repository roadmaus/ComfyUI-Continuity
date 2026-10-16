"""MOSS-Image's own half of an image render: the constants and the sampler
branch.

The shared flow — prompt, triggers, the init image, the /16 canvas — is
`compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only MOSS-Image knows: it reads no pictures; its unconditional pass runs
with one layer skipped, which is the model card's guidance rather than a
tuning of ours; and its text encoder has to be a file core can recognise,
which not every published cut is (`check_clip`).

Everything it emits is core's (Comfy-Org/ComfyUI#17095). The schedule is not
emitted at all: `supported_models.MOSSImage` already carries the card's shift
of 5 at a timestep multiplier of 1. The `ModelSamplingSD3` node the community
workflows put in front of the sampler is a different statement — it builds the
same shift at a multiplier of 1000, which is what the third-party plugin's DiT
reads and not what core's does, so copied onto core's model it would hand
every block a timestep a thousand times too large.
"""

import sys

ARCH = "moss"

# Which weights fields this architecture has. One DiT and no speed axis: the
# published 8-step distillations (data-space DMD) only work under their own
# sampler loop — every step re-mixes the same starting noise with the previous
# clean estimate through a learned matrix — and their own cards say a stock
# sampler at 8 steps and cfg 1 is not equivalent. No turbo pill until core
# can sample one.
FIELDS = ("model", "clip", "vae")

# Which VAE the `vae` field has to hold, checked off the file's header before
# the render is queued — see `vaekind`. The Flux 2 VAE (the card ships its
# small decoder); Klein's and Ideogram's file is the same one.
VAE_KIND = "flux2"

# What CLIPLoader calls the Qwen3.5-9B encoder these weights read prose
# through. Core only routes a Qwen3.5 *9B* to MOSS's tokenizer under this
# type — the chat template with an open think block, last hidden state.
CLIP_TYPE = "moss_image"

# Text-to-image only — the card's pipeline has no image input, and core's
# model reads no reference conditioning. Refused rather than dropped, as on
# Ideogram.
TAKES_REFS = False
REFS_REFUSAL = (
    "MOSS-Image draws from the prompt alone and reads no pictures — switch "
    "the model pill to an edit family, or clear the references"
)

# The tell core's Qwen3.5 detection reads (`sd.detect_te_model`), with and
# without the `model.` in front of it. Some community repacks of the MOSS
# encoder save the keys without it; core's detection then finds nothing it
# knows, falls through to loading the file as a CLIP-L, and the render dies
# inside the DiT's text projection on a 768-wide conditioning — after the
# 18 GB of weights have been read. The header says so before anything loads.
QWEN35_KEY = "model.language_model.layers.0.linear_attn.A_log"
QWEN35_KEY_BARE = "language_model.layers.0.linear_attn.A_log"

# The guidance the card ships: the unconditional pass runs with layer 22
# (zero-based) skipped, the release pipeline's `uncond_skip_layers=[22]`.
# Core's `SkipLayerGuidanceDiTSimple` is the same statement — it touches the
# uncond pass only, and MOSS's blocks answer to its `("single_block", i)`
# patches. Over the whole schedule, as the card runs it.
UNCOND_SKIP_LAYERS = "22"

# The sampler row the card ships: flow-matching Euler, 50 steps at cfg 3,
# shift 5 (detected, see the module header). `simple` over that shifted flow
# is the release scheduler's linear timesteps; the card's 30 is the floor of
# the range it recommends, 50 is the default it runs.
MOSS_BASE = {"steps": 50, "cfg": 3.0, "sampler_name": "euler", "scheduler": "simple"}


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    Nothing to decide: one checkpoint, and the schedule is core's detection.
    """
    return "model", {}


def require_support():
    """Refuse a core that does not know MOSS-Image yet — see krea2's twin.

    Keyed off what is registered rather than a version number: `CLIPLoader`
    learning the type arrived with the model, and the guidance node is the
    one this branch cannot sample the card's row without.
    """
    import nodes

    declared = nodes.NODE_CLASS_MAPPINGS["CLIPLoader"].INPUT_TYPES()
    types = declared.get("required", {}).get("type", [[]])[0]
    if CLIP_TYPE not in types or "SkipLayerGuidanceDiTSimple" not in nodes.NODE_CLASS_MAPPINGS:
        raise ValueError(
            "This ComfyUI does not know MOSS-Image yet (no 'moss_image' "
            "CLIPLoader type). Update ComfyUI and restart."
        )


def check_clip(path, filename):
    """Refuse an encoder core will not recognise as Qwen3.5 — see `QWEN35_KEY`.

    Only the one positive tell: a file that could not be read, or that is some
    other encoder entirely, is left to the loader, which names its own errors.
    """
    from ... import visionweights

    if not path or not path.lower().endswith((".safetensors", ".sft")):
        return
    try:
        header = visionweights.safetensors_header(path)
    except (OSError, ValueError):
        return
    if header and QWEN35_KEY_BARE in header and QWEN35_KEY not in header:
        raise ValueError(
            f"{filename} saves its weights without the 'model.' key prefix, "
            f"and ComfyUI's text-encoder loader does not recognise it as "
            f"Qwen3.5 that way — it only loads through the MOSS-Image plugin's "
            f"own loader. Pick Comfy-Org's qwen3.5_9b file from "
            f"models/text_encoders instead."
        )


def emit_graph(graph, payload, sampling, weights, clip, vae, model, unique_id,
               filename_prefix):
    """The sampler branch over the shared prologue's loaders."""
    from ... import render_image

    positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)
    if sampling.cfg == 1.0:
        # The sampler never evaluates the unconditional at cfg 1, so neither
        # the empty-prompt encode nor the layer skip below would be read.
        negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)
    else:
        # The card's negative is the empty prompt, encoded — not a zeroed copy.
        negative = graph.node("CLIPTextEncode", clip=clip, text="").out(0)
        model = graph.node("SkipLayerGuidanceDiTSimple", model=model,
                           double_layers="", single_layers=UNCOND_SKIP_LAYERS,
                           start_percent=0.0, end_percent=1.0).out(0)

    latent, denoise = render_image.emit_latent(graph, payload, vae,
                                               "EmptyFlux2LatentImage")
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
