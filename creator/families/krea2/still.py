"""Krea 2's own half of an image render: the constants and the sampler branch.

The shared flow — prompt, triggers, references, init image, the /16 canvas —
is `compile_image.compile_prestage` and `render_image.emit`, which take this
module as the `family` and read the declarations below. What stays here is
what only Krea 2 knows: RAW is the base checkpoint and samples with real CFG;
Turbo is an 8-step distillation at cfg 1; the two want different timestep shifts
and this is where that is put right (`KREA_RAW_SHIFT`); and references are read
through the Krea 2 Edit V2 LoRAs and the conditioning they were trained on —
the vendored Krea2Edit nodes (`edit.py`, `creator/krea2edit/`) — with the LoRA
named rather than counted (`check_refs`), because a stack that merely holds a
LoRA is not the same question as a stack that holds the one that reads pictures.
"""

import re
import sys

ARCH = "krea2"

# Which weights fields this architecture has. There is no second branch — the
# speed axis is the Turbo checkpoint.
FIELDS = ("model", "turbo_model", "clip", "vae")

# Which VAE the `vae` field has to hold, checked off the file's header before
# the render is queued — see `vaekind`.
VAE_KIND = "qwen_image"

# What CLIPLoader calls the Qwen3-VL-4B encoder.
CLIP_TYPE = "krea2"

# References are read — through an edit LoRA and nothing else; see below.
TAKES_REFS = True

# What they are called. Not *style* references any more: what the Identity Edit
# LoRA reads off a picture is the person in it, and what the General Edit one
# reads is the picture being changed. "Reference" is true of both.
REFS_NOUN = ("reference", "references")

# How a cited picture is spelled in the prompt. The grounded encode writes no
# label in front of an image — the training's template has none — so the words
# are the model card's own: the scene is image 1, the person image 2.
REFS_CITATION = "image {n}"

# The first reference can be the picture changed: General Edit V2 is an editor,
# and an edit in place wants the canvas to be that picture's. Asked for with the
# blob's `edit_first`, read by the shared compile — see
# `compile_image.EDIT_FIRST_FIELD`. Off, the pictures are references and the
# aspect pill is the canvas, which is what restaging a person wants. Only
# General Edit is offered it in the UI (`EDITS_IN_PLACE`): Identity Edit puts a
# person somewhere new, and a Krea 2 node with no edit LoRA keeps "again" as
# the img2img init it has always been.
EDITS_FIRST_REF = True
EDITS_IN_PLACE = ("general",)

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

# How references reach the model, which is one way now.
#
# Krea 2's base weights never learned to read a picture, so every way of doing
# it is a LoRA, and the ones that matter are Lars Bouaraba's Krea 2 Edit V2
# pair: Identity Edit (one photo of a person in, that person anywhere out) and
# General Edit (an instruction applied to a picture). Both were trained on two
# conditionings core does not build — the picture as clean tokens fitted to the
# output's grid, and the instruction encoded with the picture in view — which is
# what the vendored Krea2Edit nodes are. This family used to hand references to
# core's Qwen-edit encoder with a layout pill beside it; that got the layout
# roughly right and the rest of the recipe wrong, and is gone.
#
# Two pictures at most: the nodes have a scene slot and a subject slot.
REFS_LIMIT = 2
REFS_LIMIT_REASON = ("the Krea 2 edit LoRAs read a scene and a subject — put a "
                     "group together one person at a time")

# ...and at most 2 MP of canvas while they do. The card's own limit: above the
# trained range the reference bleeds into the output and subjects duplicate.
REFS_MAX_PIXELS = 2 * 1024 * 1024
REFS_TOO_BIG = (
    "A {width}x{height} canvas is {mp:.1f} MP, and the Krea 2 edit LoRAs were "
    "trained up to 2 MP — past it the reference bleeds into the picture and "
    "people duplicate. Lower the resolution pill, and upscale after"
)

# The adapter that reads them is *named*, not merely present: "the stack is not
# empty" would pass a render whose only LoRA is a style or a character and whose
# pictures go nowhere. So the blob says which entry it is, and a stack entry
# whose filename names itself one of the pair stands in where the blob does not.
REF_LORA_FIELD = "ref_lora"
REFS_NEED_ADAPTER = (
    "Krea 2 reads references only through a Krea 2 Edit LoRA — the base weights "
    "were never trained to, so an unread picture is the only other outcome. Add "
    "krea2_identity_edit_v2 (to put a person somewhere new) or "
    "krea2_general_edit_v2 (to change a picture) to the stack and name it as the "
    "reference adapter, or clear the references"
)
REFS_ADAPTER_GONE = (
    "{name} is named as the reference adapter but is not in this render's LoRA "
    "stack — it was removed, disabled or turned down to zero strength. Pick the "
    "adapter again, or clear the references"
)

# Which of the pair a file is, off its name — the filename needles the frontend
# also fills an empty adapter field from. The published files are
# `krea2_identity_edit_v2*` and `krea2_general_edit_v2*` (with `_r128` and `_r64`
# low-VRAM cuts); a needle is the part a rename is least likely to lose.
# Deliberately not "edit" alone, which a LoRA can have in its title for any
# reason — that is the silent mis-read the field exists to prevent.
EDIT_KINDS = (("identity_edit", "identity"), ("general_edit", "general"))
REF_LORA_HINTS = tuple(needle for needle, _ in EDIT_KINDS)
KIND_LABEL = {"identity": "Identity Edit", "general": "General Edit"}
REFS_NOT_AN_EDIT_LORA = (
    "{name} is named as the reference adapter, but it is not a Krea 2 Edit LoRA "
    "by its name — and those are the only ones this pack reads references "
    "through. Use krea2_identity_edit_v2 or krea2_general_edit_v2; a renamed copy "
    "has to keep 'identity_edit' or 'general_edit' in its name, which is how the "
    "render knows which of the two it is"
)

# v1 and v1.1 were trained on an older reference geometry (a centre-crop to the
# canvas) that this pack does not wire. v1.2 and V2 share the current one.
LEGACY_EDIT_LORA = re.compile(r"_v1(?:_1)?(?![\d_])")
REFS_LEGACY_ADAPTER = (
    "{name} is a v1 / v1.1 Krea 2 edit LoRA, trained on an older reference "
    "geometry than this pack lays out. Use the V2 file — krea2_identity_edit_v2 "
    "or krea2_general_edit_v2"
)

# The pair share a lineage, and at full strength together they make noise. The
# card's way to have both is about 0.6 each; past this the refusal says so.
BOTH_KINDS_MAX = 0.7
REFS_BOTH_KINDS = (
    "{a} and {b} are both on the stack, and the two Krea 2 edit LoRAs share a "
    "lineage — together at this strength they render noise. Keep one per task, "
    "or turn both down to about 0.6"
)

# Where a reference sits in the model's position space, by the id the blob and
# the frontend use -> upstream's option. Pinned onto the output's layout is how
# both LoRAs were trained; beside the canvas keeps who is in it and drops where
# — what restaging a person wants. Upstream's third, `bag of features`, is
# experimental with no recommended use and is not offered.
PLACEMENTS = {"aligned": "aligned (trained)", "beside": "beside (right of target)"}

# How hard the target attends to a reference — upstream's `ref_boost`, which
# the card never recommends leaving at its 1.0 default. The bounds are the
# dial's useful range rather than the node's.
BOOST_MIN, BOOST_MAX, BOOST_STEP = 0.0, 10.0, 0.25

# The longest side the text encoder sees each picture at. 768 in every row of
# the card, so it is not offered.
GROUNDING_PX = 768

# What each LoRA wants by default, by how many pictures there are. The card's
# recommended settings: Identity Edit restages one person at boost 2 and lets
# the photo's framing go; with a scene, the scene is pinned at 1 and the person
# placed beside at 2–3. General Edit runs at 4 and keeps the layout — an edit is
# the same picture with something changed. `place_a` / `boost_a` are the first
# picture's when there are two (the scene); the plain keys are the last's.
EDIT_DEFAULTS = {
    "identity": {1: {"boost": 2.0, "place": "beside"},
                 2: {"boost": 2.5, "place": "beside", "boost_a": 1.0, "place_a": "aligned"}},
    "general": {1: {"boost": 4.0, "place": "aligned"},
                2: {"boost": 4.0, "place": "aligned", "boost_a": 4.0, "place_a": "aligned"}},
}

# The blob fields for the last picture's two dials. Absent is the LoRA's default
# above, which is what a fresh node has; a value is somebody's choice and stays.
# The first picture's are the defaults' alone — the card has no reason to move
# a scene off them.
REF_BOOST_FIELD = "ref_boost"
REF_PLACE_FIELD = "ref_place"

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
    "subject instead of deleting it. Throw the turbo switch back and let RAW "
    "do the removal — the General Edit card's row for it is 20 steps at cfg 3"
)


def plan(data):
    """The blob's arch-specific decisions -> (checkpoint field, schedule).

    Which file the DiT loads from is the turbo pill's call, and the shift the
    sampler runs on follows it: RAW takes the canvas-derived ramp, Turbo the
    constant it was distilled against. See `KREA_RAW_SHIFT`. The reference dials
    ride along, read and checked here; which LoRA they default from is decided
    off the stack at emit (`edit_dials`).
    """
    from ...compile_image import turbo_block

    dials = _dials(data)
    turbo = turbo_block(data, ARCH)
    if turbo.get("on"):
        # Two ways to be fast, and they load different files. The distillation
        # ships as a checkpoint *and* as an SVD extraction of the same weight
        # difference; with the LoRA picked the DiT stays RAW and the stack does
        # the distilling, which is what lets a content LoRA ride along and keeps
        # one 24 GB file resident when the pill is thrown back and forth. Either
        # way the schedule is the one the distillation was fitted to.
        field = "model" if turbo.get("lora") else "turbo_model"
        return field, {"shift": KREA_TURBO_SHIFT, **dials}
    return "model", {**KREA_RAW_SHIFT, **dials}


def _dials(data):
    """The blob's reference adapter and last-picture dials, checked. -> the
    schedule keys `edit_dials` reads; an absent dial is left out."""
    from ...compile import CompileError

    out = {}
    adapter = data.get(REF_LORA_FIELD)
    if isinstance(adapter, str) and adapter.strip():
        out[REF_LORA_FIELD] = adapter.strip()
    boost = data.get(REF_BOOST_FIELD)
    if boost is not None:
        if isinstance(boost, bool) or not isinstance(boost, (int, float)) \
                or not BOOST_MIN <= boost <= BOOST_MAX:
            raise CompileError(f"the reference likeness must be a number from "
                               f"{BOOST_MIN:g} to {BOOST_MAX:g}, not {boost!r}")
        out[REF_BOOST_FIELD] = float(boost)
    place = data.get(REF_PLACE_FIELD)
    if place is not None:
        if place not in PLACEMENTS:
            raise CompileError(f"unknown reference placement {place!r} — "
                               f"{' or '.join(PLACEMENTS)}")
        out[REF_PLACE_FIELD] = place
    return out


def kind_of(name):
    """Which of the pair a LoRA file is by its name, or None."""
    lowered = (name or "").lower()
    for needle, kind in EDIT_KINDS:
        if needle in lowered:
            return kind
    return None


def adapter_of(named, loras):
    """The reference adapter's filename: the one the blob names, else the first
    entry on the stack that names itself an edit LoRA. None where neither is.

    `loras` is the reduced stack — only entries that will be patched on.
    """
    if named:
        return named
    return next((entry["name"] for entry in loras if kind_of(entry["name"])), None)


def check_refs(data, refs, loras):
    """What has to be true before Krea 2's references are worth sampling.

    Each a refusal rather than a worse picture, and none of them visible in the
    graph afterwards: the adapter that reads them is on this render's stack and
    is one of the V2 pair; the pair are not both on at a strength that makes
    noise; and the row this render will sample can do what the instruction
    asks. See the messages above for why each.
    """
    from ...compile import CompileError
    from ...compile_image import turbo_block

    named = data.get(REF_LORA_FIELD)
    named = named.strip() if isinstance(named, str) else ""
    # `loras` has already been reduced to the entries that will be patched on,
    # so "not in it" covers removed, unticked and turned down to zero alike.
    names = {entry["name"] for entry in loras}
    if named and named not in names:
        raise CompileError(REFS_ADAPTER_GONE.format(name=named))
    # Nothing named, and nothing on the stack that is one by its filename: a
    # cast member who wears the adapter puts it on the stack without a field to
    # name it in, and that is a reference read, not a picture going nowhere.
    adapter = adapter_of(named, loras)
    if adapter is None:
        raise CompileError(REFS_NEED_ADAPTER)
    if kind_of(adapter) is None:
        raise CompileError(REFS_NOT_AN_EDIT_LORA.format(name=adapter))
    if LEGACY_EDIT_LORA.search(adapter.lower()):
        raise CompileError(REFS_LEGACY_ADAPTER.format(name=adapter))

    by_kind = {}
    for entry in loras:
        kind = kind_of(entry["name"])
        if kind:
            by_kind.setdefault(kind, []).append(entry)
    if len(by_kind) > 1:
        both = [entry for entries in by_kind.values() for entry in entries]
        if any(entry["strength"] > BOTH_KINDS_MAX for entry in both):
            first, second = (entries[0]["name"] for entries in by_kind.values())
            raise CompileError(REFS_BOTH_KINDS.format(a=first, b=second))

    if turbo_block(data, ARCH).get("on") and asks_for_removal(data.get("prompt")):
        raise CompileError(REMOVAL_NEEDS_RAW)


def max_refs(data):
    """`(cap, why)` — the scene and subject slots, whatever is loaded."""
    return REFS_LIMIT, REFS_LIMIT_REASON


def check_canvas(width, height, refs):
    """Refuse a reference render past the 2 MP the LoRAs were trained up to."""
    from ...compile import CompileError

    if refs and width * height > REFS_MAX_PIXELS:
        raise CompileError(REFS_TOO_BIG.format(width=width, height=height,
                                               mp=width * height / 1e6))


def edit_dials(schedule, loras, count):
    """What the two internal nodes are handed: the LoRA's defaults for this many
    pictures under whatever the blob set. -> `{"kind", "boost", "place",
    "boost_a", "place_a"}`; the `_a` pair is the neutral one for a single
    picture, where the node never reads it."""
    adapter = adapter_of(schedule.get(REF_LORA_FIELD), loras)
    kind = kind_of(adapter) or "general"
    dials = {"boost_a": 1.0, "place_a": "aligned",
             **EDIT_DEFAULTS[kind][min(max(count, 1), REFS_LIMIT)]}
    if REF_BOOST_FIELD in schedule:
        dials["boost"] = schedule[REF_BOOST_FIELD]
    if REF_PLACE_FIELD in schedule:
        dials["place"] = schedule[REF_PLACE_FIELD]
    return {"kind": kind, **dials}


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

    latent, denoise = render_image.emit_latent(graph, payload, vae,
                                               "EmptySD3LatentImage")

    if payload.refs:
        # The two halves of what the edit LoRAs were trained on, both from the
        # vendored nodes: the pictures as clean tokens fitted to the latent the
        # sampler starts from, and the instruction read with them in view. The
        # first picture is the scene and the last the subject — see `edit.py`.
        images = [render_image.load_picture(graph, payload, f"ref:{i}", name)
                  for i, name in enumerate(payload.refs)]
        pair = {"image": images[0], **({"image_b": images[1]} if len(images) > 1 else {})}
        dials = edit_dials(payload.schedule, payload.loras, len(images))
        model = graph.node("ContinuityKrea2EditPatch", model=model, vae=vae, target=latent,
                           boost=dials["boost"], boost_a=dials["boost_a"],
                           place=dials["place"], place_a=dials["place_a"], **pair).out(0)
        positive = _refs_encode(graph, clip, payload.prompt, pair)
        negative = _refs_negative(graph, sampling, positive, clip, pair)
    else:
        positive = graph.node("CLIPTextEncode", clip=clip, text=payload.prompt).out(0)
        # Nothing grounded to be unconditional *about*: with no pictures in the
        # conditioning, a zeroed copy is the whole unconditional either
        # checkpoint wants, and at Turbo's cfg 1.0 it is skipped outright.
        negative = graph.node("ConditioningZeroOut", conditioning=positive).out(0)

    sampled = graph.node(
        "KSampler", model=model, positive=positive, negative=negative,
        latent_image=latent, seed=sampling.seed, steps=sampling.steps,
        cfg=sampling.cfg, sampler_name=sampling.sampler_name,
        scheduler=sampling.scheduler, denoise=denoise,
    )
    render_image.emit_tail(graph, sampled.out(0), vae, unique_id, filename_prefix,
                           request=payload.neural, screens=payload.screens)


def _refs_encode(graph, clip, prompt, pair):
    """One grounded encode: the instruction, read by Qwen3-VL with the pictures
    in view under the training's own template."""
    return graph.node("ContinuityKrea2EditEncode", clip=clip, prompt=prompt,
                      grounding_px=GROUNDING_PX, **pair).out(0)


def _refs_negative(graph, sampling, positive, clip, pair):
    """The unconditional branch of a reference render, in the shape the row it
    is sampled against can use.

    At real CFG that is a second grounded encode — the same pictures, nothing
    asked of them — because that is the unconditional these LoRAs were trained
    against (the card: "ground the negative too"). A zeroed copy is not the
    same thing: the text stream it hands the DiT is a block of zeros rather than
    the encoder's reading of the pictures, and the guidance is then a difference
    between two things only one of which the model has seen before.

    At cfg 1 the sampler never evaluates the negative, so the distilled path
    gets the zeroed copy instead of paying for a second VL encode that nothing
    reads — the same trade Qwen Image Edit's branch makes.
    """
    if sampling.cfg == 1.0:
        return graph.node("ConditioningZeroOut", conditioning=positive).out(0)
    return _refs_encode(graph, clip, "", pair)


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
