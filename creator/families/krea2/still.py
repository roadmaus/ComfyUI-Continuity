"""Krea 2's own half of an image render: the constants and the sampler branch.

The shared flow — prompt, triggers, references, init image, the /16 canvas —
is `compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only Krea 2 knows: RAW is the base checkpoint and samples with real CFG;
Turbo is an 8-step distillation at cfg 1; the two want different timestep shifts
and this is where that is put right (`KREA_RAW_SHIFT`); and style references go
through core's Qwen-edit encoder, which the model only reads with one of the
reference LoRAs patched on — named rather than counted (`check_refs`), because
a stack that merely holds a LoRA is not the same question as a stack that holds
the one that reads pictures.
"""

import re
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

# ...and *style reference* is the right words for them here, which is not true
# of every family that reads pictures. Krea 2 carries a look across: what these
# images contribute is their appearance, and the LoRA that reads them is the one
# trained to hold identity or style. On an edit family the same slot holds a
# picture the instruction is about, and calling that a style reference describes
# it as the one thing it is not. So the noun is the family's, and every message
# that counts references asks for it.
REFS_NOUN = ("style reference", "style references")

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

# ...and the adapter that reads them is *named*, not merely present. Every way
# of reading a reference on Krea 2 is a LoRA, so the stack has to hold one — but
# "the stack is not empty" is not the same question, and answering the easy one
# passes a render whose only LoRA is a style or a character and whose pictures
# go nowhere. That is the exact failure the check exists to catch, so the blob
# says which entry is the reference adapter and this refuses anything else.
#
# It is also the honest place for the layout: `REF_METHODS` above is a property
# of the adapter, not of the render, so the two are picked together in the UI.
REF_LORA_FIELD = "ref_lora"
REFS_NEED_ADAPTER = (
    "Krea 2 reads style references only through a reference LoRA — the base "
    "weights were never trained to, so an unread picture is the only other "
    "outcome. Add one to the stack (krea2_style_reference for style, an "
    "ai-toolkit edit LoRA for edits) and name it as the reference adapter, or "
    "clear the references"
)
REFS_ADAPTER_GONE = (
    "{name} is named as the reference adapter but is not in this render's LoRA "
    "stack — it was removed, disabled or turned down to zero strength. Pick the "
    "adapter again, or clear the references"
)

# Filename needles the *frontend* fills an empty adapter field from — the
# published Krea 2 reference LoRAs, spelled the ways they are actually
# distributed. Deliberately only the names that identify themselves: a needle as
# loose as "edit" would fill the field from a LoRA that merely had the word in
# its title, which is the silent mis-read this field exists to prevent. A file
# named anything else is picked by hand, and the compile reads the field and
# nothing else either way.
REF_LORA_HINTS = ("krea2_style_reference", "krea2_identity_edit", "krea2_edit",
                  "identity_edit")

# Removal is the one edit the distilled checkpoint cannot do. At cfg 1 there is
# no guidance to push the render away from what the reference latents are
# showing it, so Turbo re-draws the subject it was asked to delete — the doc's
# own words, and a routing rule rather than a tuning preference. RAW at its own
# row is what the task needs.
#
# The instruction is the only place that says a removal is being asked for, so
# it is read for the verbs a removal is written with. English-shaped and so
# necessarily partial: it catches the way these prompts are actually written
# without claiming to be a parser, and it only ever refuses the one combination
# the doc says produces a wrong picture.
REMOVAL_WORDS = (
    "remove", "removes", "removed", "removing", "removal",
    "delete", "deletes", "deleted", "deleting",
    "erase", "erases", "erased", "erasing",
    "take out", "takes out", "taking out", "get rid of", "rid of",
)
REMOVAL_NEEDS_RAW = (
    "Krea 2 Turbo cannot take something out of a picture: distilled at cfg 1 it "
    "has no guidance to push against the reference, so it re-renders the "
    "subject instead of deleting it. Throw the turbo switch back and let RAW's "
    "own row do the removal"
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


def check_refs(data, refs, loras):
    """What has to be true before Krea 2's references are worth sampling.

    Two things, and neither is visible in the graph afterwards: the adapter that
    reads them is actually in this render's stack, and the row this render will
    sample can do what the instruction asks. See `REFS_NEED_ADAPTER` and
    `REMOVAL_NEEDS_RAW` for why each is a refusal rather than a worse picture.
    """
    from ...compile import CompileError
    from ...compile_image import turbo_block

    adapter = data.get(REF_LORA_FIELD)
    adapter = adapter.strip() if isinstance(adapter, str) else ""
    if not adapter:
        raise CompileError(REFS_NEED_ADAPTER)
    # `loras` has already been reduced to the entries that will be patched on,
    # so "not in it" covers removed, unticked and turned down to zero alike.
    if adapter not in {entry["name"] for entry in loras}:
        raise CompileError(REFS_ADAPTER_GONE.format(name=adapter))

    if turbo_block(data, ARCH).get("on") and asks_for_removal(data.get("prompt")):
        raise CompileError(REMOVAL_NEEDS_RAW)


def asks_for_removal(prompt):
    """Is this instruction asking for something to be taken out of the picture?

    Word-boundary matching so `removed` counts and `remote` does not. See
    `REMOVAL_WORDS` on what this is and is not claiming to be.
    """
    text = (prompt or "").lower()
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in REMOVAL_WORDS)


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
        # post-trained against. The method node picks the variant the adapter in
        # the stack was trained with.
        images = {f"image{i + 1}": graph.node("LoadImage", image=name).out(0)
                  for i, name in enumerate(payload.refs)}
        method = payload.schedule["ref_method"]
        positive = _refs_encode(graph, clip, vae, payload.prompt, images, method)
        negative = _refs_negative(graph, sampling, positive, clip, vae, images, method)
    else:
        positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)
        # Nothing grounded to be unconditional *about*: with no pictures in the
        # conditioning, a zeroed copy is the whole unconditional either
        # checkpoint wants, and at Turbo's cfg 1.0 it is skipped outright.
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


def _refs_encode(graph, clip, vae, prompt, images, method):
    """One grounded encode: the pictures as vision tokens and as reference
    latents, laid into the sequence the way the adapter learned them."""
    conditioning = graph.node("TextEncodeQwenImageEditPlus", clip=clip,
                              prompt=prompt, vae=vae, **images).out(0)
    return graph.node("FluxKontextMultiReferenceLatentMethod",
                      conditioning=conditioning,
                      reference_latents_method=method).out(0)


def _refs_negative(graph, sampling, positive, clip, vae, images, method):
    """The unconditional branch of a reference render, in the shape the row it
    is sampled against can use.

    At real CFG that is a second grounded encode — the same pictures, nothing
    asked of them — because that is the unconditional these adapters were
    trained against. A zeroed copy is *not* the same thing: `ConditioningZeroOut`
    copies the conditioning dict, so the reference latents do ride along, but the
    text stream it hands the DiT is a block of zeros rather than the encoder's
    reading of the pictures, and the guidance is then a difference between two
    things only one of which the model has seen before.

    At cfg 1 the sampler never evaluates the negative, so the distilled path
    gets the zeroed copy instead of paying for a second VL encode that nothing
    reads — the same trade Qwen Image Edit's branch makes.
    """
    if sampling.cfg == 1.0:
        return graph.node("ConditioningZeroOut", conditioning=positive).out(0)
    return _refs_encode(graph, clip, vae, "", images, method)


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
