"""One generation, as a graph. Shared by both nodes.

Both the Creator and the Timeline own their sampler, and neither can be an
ordinary node because of it: a node that samples has to *be* the sampler, and
ComfyUI has no way to say that except by returning a subgraph. So both compile
their blob to payloads and hand them here, and this emits

    loaders -> segment -> [accelerators] -> [preview] -> KSampler -> Reel -> Save

(with a turbo lead-in on, that one KSampler is two KSamplerAdvanced nodes
sharing a schedule — see `LeadIn`.)

once per payload, adding each to the reel the save node writes. The Creator
passes one payload and the Timeline passes one per segment; a single-payload
render is the same code with the loop running once, which is why there is no
second implementation of it and must not be. Everything the two nodes disagree
about — how the blob becomes payloads, what the widgets are called — stays in
the nodes.

The chaining is the only part a one-payload render does not exercise: segment N
starting from segment N-1's decoded last frame. It is driven off the compiled
payload rather than off a flag, so a Creator render simply never asks for it.

**The passes are collected on disk, not concatenated in memory.** They used to
be folded pairwise by a join node, which meant N-1 running totals all held alive
by the executor's cache — O(N^2) in the length of the piece, and 81 GB of
intermediates on a ten-pass 768p strip. A reel is a list of parts that copies
nothing, and each part is a file: the decode happens inside the reel node and
`spill.py` writes what comes out of it straight to disk, because a node's output
is kept for the whole execution and a decoded pass is the largest thing in the
render. `mux.py` reads the parts back a frame at a time. Peak memory is one
pass, whatever the strip is.

**Both ends of that chain used to be the user's problem.** The loaders were five
sockets on the node and the video was two outputs somebody had to wire a save
node to, which made a node built to need no wiring need six. `models.py` builds
the loaders here now, and the tail below muxes and saves. Neither node has a
socket left.

**`set_override_display_id` is what puts the finished video back in the node.**
An expanded node's UI result is broadcast against its own id, which is our id
plus a `GraphBuilder` prefix and is on nobody's canvas. Stamping the parent's id
on the save node makes `execution.py` file its `executed` message under the node
the user is actually looking at, so the body can play what it just made without
anything being faked or wired.

Node ids are written as strings rather than imported, because they are ComfyUI
registry keys and not Python names — `MiniMaxH3TimelineSegment` is still called
that for both callers, since renaming it would only churn the tests for a label
nothing outside an expanded graph ever sees.
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

import comfy.sample
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder

from . import accel, canvas, compile as compiler, media, models, outputs, settings

# Whether this core can start a sampler with the noise switched off on an H3
# audio+video latent. The lead-in's second sitting does exactly that — the noise
# is already in the latent the first sitting handed over — and core before
# 27bca654 (2026-08-11) built that zero noise from `NestedTensor.size()`, which
# is the *picture's* shape and not the pack's. The sampler then packs a
# video-shaped noise against a video-and-sound latent and the first step dies on
# arithmetic nobody can read: "The size of tensor a (56448) must match the size
# of tensor b (1369792) at non-singleton dimension 2", a hundred seconds into a
# render, with the lead-in nowhere in the sentence. Reported in #27.
#
# Probed off the repair itself rather than a version string, the same way
# `payload.CORE_ANCHORS_ANYWHERE` is: what matters is whether the empty noise
# knows about the pack, and the function that knows is the whole of the fix.
CORE_EMPTY_NOISE_IS_NESTED = hasattr(comfy.sample, "prepare_empty_noise")

SEGMENT_NODE = "MiniMaxH3TimelineSegment"
REFINE_NODE = "MiniMaxH3RefinePass"
FACE_NODE = "MiniMaxH3FacePass"
PASS_FRAMES_NODE = "MiniMaxH3PassFrames"
PASS_AUDIO_NODE = "MiniMaxH3PassAudio"
REEL_NODE = "MiniMaxH3Reel"
CLIP_NODE = "MiniMaxH3ClipReel"
CLIP_FRAMES_NODE = "MiniMaxH3ClipFrames"
CLIP_AUDIO_NODE = "MiniMaxH3ClipAudio"
SAVE_NODE = "MiniMaxH3Save"

# Where a render lands when the blob does not say. Under a folder of its own,
# because the node writes one every queue now and mixing them into the root of
# output/ would bury whatever else is in there. `outputs` owns the value and
# what a typed one is allowed to be.
FILENAME_PREFIX = outputs.VIDEO_PREFIX


# The H3 checkpoints' own flow shifts — `MiniMaxH3Model.__init__`'s
# `sigma_shift_video` / `sigma_shift_audio` defaults. At exactly these values
# no shift node is emitted, so a graph whose pills were never touched stays
# byte-identical to what this pack always built.
SHIFT_DEFAULTS = (12.0, 3.0)


@dataclass(frozen=True)
class Sampling:
    """The sampler settings both nodes expose under the same widget names."""

    seed: int = 0
    steps: int = 20
    cfg: float = 1.0
    sampler_name: str = "res_multistep"
    scheduler: str = "simple"
    shift_video: float = SHIFT_DEFAULTS[0]
    shift_audio: float = SHIFT_DEFAULTS[1]

    def shifted(self):
        return (self.shift_video, self.shift_audio) != SHIFT_DEFAULTS


@dataclass(frozen=True)
class LeadIn:
    """The turbo lead-in: how many opening steps run without the distillation.

    A distillation LoRA is a step-collapsed velocity field. It is very good at
    finishing a shot and it is not what decided the shot — the opening steps of
    a flow schedule are where the composition, the motion and everything the
    prompt actually asked for are settled, and a 4-step distill settles them at
    a quarter of the resolution the base weights would. That is what people
    mean when they say a turbo LoRA makes H3 stupid: not that the frames are
    worse, but that it stopped listening.

    So the schedule is split rather than shortened. `steps` opening steps sample
    on the checkpoint with the distillation held off it, the leftover noise is
    handed on, and the rest of the same schedule runs on the distilled model as
    it always did. The sigmas, the seed and the step count are one run's — this
    only moves where the distillation takes over. Two steps of eight costs about
    a quarter of the time the distill saved and buys back the part it sold.

    **What it is not.** Not extra steps: they come out of the count on the node,
    so a 6-step turbo render with a 2-step lead-in is still six. Not real
    guidance either — the released H3 checkpoints are CFG-distilled and 1.0 is
    the value they were trained at, so both halves sample at the node's cfg and
    nothing here doubles the sampling cost.

    **Where it does not reach.** The refine and face passes re-noise partway
    down the schedule and sample from there; the opening steps this is about
    are not in them, and they carry on as before.

    `lora` is the file the switch engaged. Without one there is nothing to hold
    off — a checkpoint with the distillation merged into the weights has no
    lead-in to give, which is a real answer and not a failure.
    """

    steps: int = 0
    lora: str = ""

    @classmethod
    def of(cls, data):
        """The lead-in this machine asks for, for the piece `data` describes."""
        turbo = data.get("turbo") or {}
        if not turbo.get("on") or not turbo.get("lora"):
            return cls()
        return cls(steps=settings.turbo_lead_in(), lora=str(turbo["lora"]))

    def within(self, sampling, compiled, payload):
        """Whether this payload actually splits — the whole test, in one place.

        Three ways a lead-in that is switched on still does nothing here, and
        all three are ordinary rather than wrong: nobody asked for one, the
        schedule is too short to give steps away from, or this generation is
        not wearing the LoRA (a shot that turned it off, or a checkpoint it does
        not claim). `active_loras` is the same filter the segment node patches
        by, so the two cannot disagree about what is on the model.
        """
        if self.steps <= 0 or not self.lora or self.steps >= sampling.steps:
            return False
        return any(entry["name"] == self.lora for entry in
                   compiler.active_loras(payload["request"].get("loras"),
                                         compiled.checkpoint))


@dataclass(frozen=True)
class Links:
    """The loaders, as links into the graph they were built in.

    Links rather than loaded objects throughout: these go into the subgraph, and
    ComfyUI hashes input *values* for its cache — a model object hashes as
    `Unhashable`, so passing the real thing would make every expanded node miss
    on every queue.

    A checkpoint nothing routes to is `None` and has no loader in the graph at
    all. That is the point of `models.emit_links` taking the set: both MODEL
    sockets used to have to be connected even though one generation samples with
    exactly one of them, so every queue loaded weights it never touched.
    """

    clip: Any
    vae: Any
    audio_vae: Any
    model_fl2va: Optional[Any] = None
    model_ref2va: Optional[Any] = None

    def model_for(self, checkpoint):
        return {"fl2va": self.model_fl2va, "ref2va": self.model_ref2va}[checkpoint]


def compile_all(payloads, labels):
    """Payloads -> `Compiled`, failing with the caller's own name for each one.

    Done before a single node is emitted so that a request which cannot compile,
    or which routes to a checkpoint nothing is connected to, fails now rather
    than after the first sampler pass has already run.

    A supplied clip compiles to `None`: there is no request in it, no mode and
    no checkpoint, and every caller below reads the absence as "this pass is
    played rather than generated" rather than being handed a hollow `Compiled`
    that would have to answer questions it has no answer to.
    """
    out = []
    for index, payload in enumerate(payloads):
        where = labels[index] if index < len(labels) else f"Segment {index + 1}"
        # `None` is a payload that was never built — a pass with no face repair
        # in the face-conditioning list — and reads the same way a clip does:
        # there is nothing here to compile.
        if payload is None or "clip" in payload:
            out.append(None)
            continue
        try:
            out.append(compiler.compile_segment(payload, media.image_size))
        except compiler.CompileError as exc:
            raise ValueError(f"{where}: {exc}") from exc
    return out


def routed(compiled, labels):
    """`{checkpoint: the label of the first generation that reached for it}`.

    Which weights this render needs, and who to blame when one of them was never
    picked. Ordered by first use so the error names the earliest segment rather
    than an arbitrary one.
    """
    where = {}
    for index, one in enumerate(compiled):
        if one is None:
            continue        # a supplied clip reaches for no weights at all
        label = labels[index] if index < len(labels) else f"Segment {index + 1}"
        where.setdefault(one.checkpoint, label)
    return where


def is_clip_source(source):
    """Whether a seam is inheriting from supplied footage rather than a pass.

    `decoded` holds one entry per pass in play order, tagged by kind: a
    generated pass leaves `("pass", link)`, the link its reel node hands out
    naming what it spilled to disk, and a clip leaves `("clip", spec)`, since
    there is nothing in the graph for it to point at.
    """
    return source[0] == "clip"


def inherited_frames(graph, source, feather):
    """The run of frames a seam takes off the pass in front of it.

    Two roads to the same tensor, and both of them go through a file. A
    generated pass was written to disk the moment it decoded, so the run comes
    back off the spill — see `MiniMaxH3Reel`. A supplied clip was never decoded
    at all, so the run is read out of the clip's own window. Either way what is
    read is the seam's width and not the pass, which is what makes a seam cost
    the same behind a five-second shot and a five-minute one.
    """
    if is_clip_source(source):
        return graph.node(CLIP_FRAMES_NODE,
                          clip_data=json.dumps(source[1], sort_keys=True),
                          count=feather, at="tail").out(0)
    return graph.node(PASS_FRAMES_NODE, source=source[1],
                      **({"count": feather} if feather > 1 else {})).out(0)


def inherited_audio(graph, source, seconds):
    """The stretch of sound a seam takes off the pass in front of it."""
    if is_clip_source(source):
        return graph.node(CLIP_AUDIO_NODE,
                          clip_data=json.dumps(source[1], sort_keys=True),
                          seconds=seconds, at="tail").out(0)
    return graph.node(PASS_AUDIO_NODE, source=source[1], seconds=seconds).out(0)


def patched(graph, model, sampling, acceleration, weights):
    """The three patches every sampler in this module runs behind, in order.

    The flow shifts first, only when they leave the checkpoints' own values: a
    turbo LoRA's card names the schedule it was distilled against, and this is
    where the pills reach the run. Core's node on both sides of the 2026-08-13
    split, so there is no version to gate on.

    Then the accelerators, which want to sit between the model patches and the
    sampler — FirstBlockCache refuses to run downstream of another DiT block
    replacement — and last the preview decoder, which wraps OUTER_SAMPLE and so
    wants to be outside them rather than under. Off, each of these adds nothing
    and returns what it was given.

    Written once because the pass, the refine, the face crop and the lead-in all
    need exactly this and a fourth copy is how the four stop agreeing.
    """
    if sampling.shifted():
        model = graph.node(
            "MiniMaxH3SigmaShift", model=model,
            shift_video=sampling.shift_video,
            shift_audio=sampling.shift_audio).out(0)
    model = accel.graph_apply(graph, model, acceleration, sampling.steps)
    return models.graph_preview(graph, model, weights)


def face_payload(payload, face):
    """The payload the face pass's *conditioning* is built from.

    The crop is a square of one face, so two kinds of thing are taken out of the
    segment before it is compiled again at that canvas:

    - **The face settings themselves**, so the pass compiled here does not ask
      for a face pass of its own. This is what ends the recursion, the way a
      pinned target ends the refine pass's.
    - **Start and end frames.** A keyframe is a condition latent for the whole
      picture, injected at every step; inside a face crop it is an instruction to
      match a composition that is not in the crop. References survive — a
      character sheet is exactly what a face crop wants, and it is what the
      reference workflows lean on — so a segment with a keyframe compiles here as
      the text-or-reference pass it becomes without one, and routes accordingly.

    The seam inputs are dropped by the emitter rather than here: they are node
    links, not blob fields, and they are anchors for the full canvas for the same
    reason a keyframe is.
    """
    request = {key: value for key, value in payload["request"].items() if key != "face"}
    assets = [asset for asset in (request.get("assets") or [])
              if isinstance(asset, dict) and asset.get("role") == "reference"]
    if assets or "assets" in request:
        request["assets"] = assets
    return {"request": request,
            "canvas": {"width": face.width, "height": face.height, "ratio": 1.0,
                       "label": "1:1", "from_image": False, "clamped": False}}


def emit(payloads, labels, weights, sampling, acceleration, unique_id,
         filename_prefix=FILENAME_PREFIX, cards=None, seeds=None,
         whole_piece=True, lead_in=None):
    """-> the graph, which the caller finalizes. Nothing comes back out of it.

    `labels[i]` names payload i in any error raised about it — "Segment 2", or
    "This generation" where there is only one of them. `unique_id` is the calling
    node's, and is stamped on the save node so the finished video is reported
    against the node the user is looking at. `filename_prefix` is where the
    result lands under output/; the callers get it from `outputs.video`, which
    has already refused anything unusable.

    `cards[i]` is the number on the strip of the card payload i renders, and
    `seeds[i]` its own seed or None for the piece's. Together they are also what
    the save node writes the takes from — see `MiniMaxH3Save` — so a piece
    rendered a pass at a time gets one file per pass to keep as well as the
    piece.

    `lead_in` is the turbo lead-in this machine asks for — see `LeadIn`. Absent
    means none, which is every render this pack made before the setting existed
    and every render on a machine that leaves it off.

    `whole_piece` is whether this render covers the strip the user is looking
    at. Everything below that used to ask "is there only one payload" is really
    asking "is this render the whole piece, made in one go", and those were the
    same question until a card could be held back. They stopped being it the
    moment they could: a card shot by itself out of six is one payload and is
    emphatically not a lone generation. True where nobody says otherwise, which
    is what this assumed before holding existed.
    """
    # All three of these raise, and all three are cheap: an accelerator whose
    # pack is not installed, a request that cannot compile, or weights that were
    # never picked should say so before anything is queued rather than after the
    # first segment has sampled.
    accel.plan(acceleration, sampling.steps)
    lead_in = lead_in or LeadIn()
    # Before compiling, and before the payloads become segment cache keys: a
    # standing route is the same statement the per-request pin makes, said once
    # for every generation instead of once per generation.
    payloads = [weights.routed(payload) for payload in payloads]
    # Which segment each payload is, for the stage's "now rendering segment N"
    # chip — the segment node announces it when it executes. Not on a piece
    # generated in one go: there is one thing happening and no position within
    # it worth reporting, which is as true of a one-pass render over twelve
    # cards as it is of a lone generation.
    #
    # A card shot by itself is the case this had wrong. It is one payload and it
    # is not the piece, so it does say which card it is — and because the stamp
    # is the card's own number, its payload then serialises identically whether
    # it was shot alone or with the whole strip. Gated on `len(payloads)`, as it
    # was, shooting one card missed the cache the full render had just filled.
    #
    # The index alone, never the total: a payload's index is stable when a
    # segment is appended, so earlier segments keep their cache keys, where a
    # total would invalidate the whole strip for adding one shot at the end.
    if len(payloads) > 1 or not whole_piece:
        # The card's number on the strip, not its position in the render: a
        # piece shot a pass at a time renders fewer passes than it has cards,
        # and "rendering segment 2" has to name the card the user can go and
        # open. Without `cards` the two are the same thing, which is what they
        # have always been.
        numbers = cards or range(1, len(payloads) + 1)
        payloads = [{**payload, "progress": {"index": int(number)}}
                    for payload, number in zip(payloads, numbers)]
    compiled = compile_all(payloads, labels)
    where = routed(compiled, labels)

    # The face pass's conditioning is a second compile of the same segment at
    # the crop canvas, and dropping the keyframes can land it on the other
    # checkpoint — so it is compiled here, before the loaders are built, and its
    # route joins the set they are built from. `None` wherever a pass is not
    # having its face repaired, so the list indexes alongside `compiled`.
    face_payloads = [face_payload(payloads[index], one.face) if one and one.face else None
                     for index, one in enumerate(compiled)]
    face_compiled = compile_all(face_payloads, labels) if any(face_payloads) \
        else [None] * len(payloads)
    where = {**routed(face_compiled, labels), **where}
    models.check(weights, set(where), where, face=any(face_payloads))

    # This card's own seed where it has one, the node's everywhere else. Held as
    # a lookup rather than folded into the payloads: the payload is the segment
    # node's cache key and the seed is not one of its inputs — it goes to the
    # sampler — so putting it there would re-encode every conditioning for a
    # re-roll that changes no conditioning at all.
    def seed_for(index):
        seed = (seeds or [None] * len(payloads))[index]
        return sampling.seed if seed is None else int(seed)

    graph = GraphBuilder()
    links = models.emit_links(graph, weights, set(where))
    reel = None             # the reel link holding every pass emitted so far
    decoded = []            # every payload as (kind, what to read it back from),
                            # in order — a seam defaults to the previous one but
                            # may name any earlier one via `continue_from`

    for index, one in enumerate(compiled):
        if one is None:
            # Supplied footage. It joins the reel as a file and is never
            # decoded into it — see `MiniMaxH3ClipReel`. What a later seam
            # needs out of it is decoded then, from the clip's own window, and
            # is bounded by the seam's width rather than by the clip's length.
            spec = payloads[index]["clip"]
            clip_inputs = {"clip_data": json.dumps(spec, sort_keys=True)}
            if reel is not None:
                clip_inputs["reel"] = reel
            if spec.get("sound"):
                clip_inputs["audio_vae"] = links.audio_vae
            reel = graph.node(CLIP_NODE, **clip_inputs).out(0)
            decoded.append(("clip", spec))
            continue

        # Whether this generation's schedule is split — asked once, because the
        # answer wires the segment node as well as the sampler, and a graph
        # where those two disagreed would hold a model nothing samples on.
        splits = lead_in.within(sampling, one, payloads[index])
        if splits and not CORE_EMPTY_NOISE_IS_NESTED:
            # Said here, before a single model is loaded, because the shape it
            # saves the user from is thrown after the opening steps have already
            # been sampled — and says nothing about what asked for them.
            raise ValueError(
                "the turbo lead-in needs a ComfyUI from 2026-08-11 or later "
                "(27bca654, \"Fix KSamplerAdvanced with add_noise disabled on "
                "nested latents\"): before it, the second half of a split "
                "schedule builds its noise from the picture alone and H3's "
                "soundtrack is not in it, so the first step fails on a tensor "
                "size mismatch. Update ComfyUI, or set the turbo lead-in to 0 "
                "steps under Settings -> Rendering -> Turbo lead-in, which "
                "sends the whole schedule to one sampler."
            )

        inputs = {
            "clip": links.clip,
            # sort_keys so an unchanged payload serialises identically every
            # time — this string is the segment node's cache key.
            "segment_data": json.dumps(payloads[index], sort_keys=True),
        }
        if splits:
            # Only when it is in play: an input the graph does not write is an
            # input the segment node's cache key does not carry, so a render
            # without a lead-in keeps the key it had before this existed.
            inputs["hold_lora"] = lead_in.lora
        # The VAEs are wired into the encoder only when this segment actually
        # encodes with them — a keyframe or a sound seam. A text-only segment
        # touches neither until decode, and a decode node runs after sampling
        # where the DiT no longer needs the room. Wiring them here regardless
        # would load both before the first step and, on tight VRAM, push part of
        # the model into per-step recompute for no encode that uses them.
        if one.encodes_video():
            inputs["vae"] = links.vae
            # The checkpoint's name travels beside the socket, for the reference
            # cache to key its latents to — a live VAE object cannot be
            # identified across a restart, and a name can. Written only where
            # the VAE itself is, so a segment that encodes nothing keeps the
            # inputs, and the cache key, it had before this existed.
            inputs["vae_name"] = weights.vae or ""
        if one.encodes_audio():
            inputs["audio_vae"] = links.audio_vae
            inputs["audio_vae_name"] = weights.audio_vae or ""
        if links.model_fl2va is not None:
            inputs["model_fl2va"] = links.model_fl2va
        if links.model_ref2va is not None:
            inputs["model_ref2va"] = links.model_ref2va
        source = decoded[payloads[index].get("continue_from", index - 1)] \
            if index else (None, None)
        if one.continues:
            # Only the tail, not the whole batch: the source segment's images
            # are a video and what this one inherits is its last moment — or,
            # feathered, its last few. Inserted here rather than after every
            # segment, so a render of hard cuts has no dead nodes in it and a
            # Creator render has none at all. The count rides only on feathered
            # seams, so a classic seam's node inputs stay byte-identical.
            inputs["prev_image"] = inherited_frames(graph, source, one.feather)
        if one.continues_audio:
            # `one.audio_tail_s` rather than the timeline's setting directly:
            # compile clamps it to a feathered seam's overlap, and this is
            # where that decision reaches the graph.
            inputs["prev_audio"] = inherited_audio(graph, source, one.audio_tail_s)
        if one.ends_on or one.ends_on_audio:
            # The seam running the other way: the pass after this one is
            # supplied footage, and this generation ends on its opening rather
            # than cutting to it. Always the pass immediately after — what a
            # generation can end on is decided while it is sampled, so there is
            # no reaching further forward the way a seam reaches back.
            ahead = payloads[index + 1]["clip"]
            if one.ends_on:
                inputs["next_image"] = graph.node(
                    CLIP_FRAMES_NODE, clip_data=json.dumps(ahead, sort_keys=True),
                    count=one.ends_feather, at="head").out(0)
            if one.ends_on_audio:
                inputs["next_audio"] = graph.node(
                    CLIP_AUDIO_NODE, clip_data=json.dumps(ahead, sort_keys=True),
                    seconds=one.ends_tail_s, at="head").out(0)

        segment = graph.node(SEGMENT_NODE, **inputs)

        # The distilled H3 checkpoints run at cfg 1.0, where the negative is
        # skipped outright, so there is nothing here worth a socket on the node.
        against = graph.node("ConditioningZeroOut", conditioning=segment.out(1)).out(0)

        # Patched after the segment node, which is where the LoRAs go on. Off,
        # every one of these adds nothing and this is the segment's model
        # unchanged.
        model = patched(graph, segment.out(0), sampling, acceleration, weights)

        # What every sampler below this line is handed, whether the schedule is
        # run in one sitting or two. The seed is not in here because the two
        # sitting the lead-in makes spell it differently — `noise_seed` — and a
        # dict that had to be unpacked and then corrected would be worse than
        # naming it twice.
        #
        # The seed is the node's, on every pass, unless this card carries one of
        # its own. A piece is one look and the seed is the handle on it:
        # *offsetting* it per segment made segment 3 of a six-segment chain
        # unreproducible from the number on the node, and made the same clip
        # render differently for having been moved. What separates consecutive
        # shots is their prompts and their seams, not their noise.
        #
        # A card that names its own seed is the other thing entirely, and is
        # what shooting a piece a pass at a time needs: retaking segment 2 under
        # one number for the whole piece means rolling the number that the take
        # already kept on segment 1 was made under, so the handle stops
        # describing the piece. A take's seed is a fact about the take. Absent —
        # which is every card until somebody rolls one — this is the node's seed
        # and nothing has changed.
        common = dict(
            steps=sampling.steps, cfg=sampling.cfg,
            sampler_name=sampling.sampler_name, scheduler=sampling.scheduler,
            positive=segment.out(1), negative=against,
        )

        if splits:
            # The split. One schedule, sampled in two sittings: the opening
            # steps on the model the segment node handed back with the
            # distillation held off it, then the leftover noise to the model
            # that has it. `add_noise` is on for the first and off for the
            # second, which is what makes them one run rather than two.
            #
            # The lead-in is not cached. The step accelerators reuse a forward
            # they have already paid for, and there are two forwards here to
            # reuse — they would be caching the exact steps this feature exists
            # to run properly. Sage stays: it makes one attention call cheaper
            # and skips nothing.
            opening = graph.node(
                "KSamplerAdvanced",
                model=patched(graph, segment.out(3), sampling,
                              accel.uncached(acceleration), weights),
                latent_image=segment.out(2),
                add_noise="enable", noise_seed=seed_for(index),
                start_at_step=0, end_at_step=lead_in.steps,
                return_with_leftover_noise="enable", **common)
            sampled = graph.node(
                "KSamplerAdvanced",
                model=model, latent_image=opening.out(0),
                # The noise is already in the latent. A second `enable` here
                # would add a whole schedule's worth of it on top and throw the
                # opening steps away.
                add_noise="disable", noise_seed=seed_for(index),
                start_at_step=lead_in.steps, end_at_step=sampling.steps,
                return_with_leftover_noise="disable", **common)
        else:
            sampled = graph.node(
                "KSampler", model=model, latent_image=segment.out(2),
                seed=seed_for(index), denoise=1.0, **common)

        if one.refine:
            # The two-pass upscale: the first pass sampled at the smaller
            # first-pass canvas, and this regenerates it at the target size
            # from the same context.
            # A second segment node, pinned to the target canvas, re-encodes
            # the keyframes and references at that size so their condition
            # latents match the upscaled video latent — then the refine pass
            # interpolates the picture up, re-noises it partway down the
            # schedule, and samples again with the soundtrack riding through
            # un-noised. Pinning the canvas also ends the recursion: a pinned
            # target compiles with nothing left to refine to.
            spec = {"width": one.refine.width, "height": one.refine.height,
                    "ratio": one.ratio, "label": one.ratio_label,
                    "from_image": one.ratio_from_image, "clamped": one.ratio_clamped}
            refine_inputs = dict(inputs)
            refine_inputs["segment_data"] = json.dumps(
                {**payloads[index], "canvas": spec}, sort_keys=True)
            second = graph.node(SEGMENT_NODE, **refine_inputs)
            # Patched the same way as the first pass, because it is the same
            # run at a different size: cfg 1.0 skips the negative, the LoRAs
            # come with the segment node, the accelerators and the preview
            # decoder sit in the same places. No lead-in: this pass re-noises
            # partway down the schedule and samples from there, so the opening
            # steps a lead-in splits are not in it to split.
            refine_against = graph.node(
                "ConditioningZeroOut", conditioning=second.out(1)).out(0)
            refine_model = patched(graph, second.out(0), sampling, acceleration, weights)
            sampled = graph.node(
                REFINE_NODE,
                model=refine_model, positive=second.out(1), negative=refine_against,
                latent=sampled.out(0),
                width=one.refine.width, height=one.refine.height,
                seed=seed_for(index), steps=sampling.steps, cfg=sampling.cfg,
                sampler_name=sampling.sampler_name, scheduler=sampling.scheduler,
                denoise=one.refine.denoise,
            )

        # Decoded, trimmed, written to disk and added to the reel, all in the
        # one node. The decode is not a node of its own because a node's output
        # is kept for the whole execution, and a decoded pass is the largest
        # thing in the render — see `MiniMaxH3Reel`. What travels the wire from
        # here is a path and a frame count.
        #
        # The trim is the runs this pass shares with its neighbours: the one it
        # inherited at its head, the clip's opening it runs into at its tail.
        # Both are re-generated here and would otherwise play twice. It is also
        # what later seams inherit from — their tail is identical either way,
        # and this is the pass as delivered.
        written = graph.node(
            REEL_NODE, samples=sampled.out(0), vae=links.vae, audio_vae=links.audio_vae,
            **({"head": one.feather} if one.feather > 1 else {}),
            **({"tail": one.ends_feather} if one.ends_feather > 1 else {}),
            **({"reel": reel} if reel is not None else {}))
        source = written

        if one.face:
            # The face pass, on the pass as delivered: it reads the frames back
            # off the spill, re-draws the face at a canvas where it is large,
            # and writes a replacement. It goes *here*, after the pass is
            # written and before the next segment is emitted, because what the
            # next seam inherits is `decoded[]` — put at the end of the render
            # instead, every seam would have continued from a face this pass
            # then went on to repair.
            #
            # Its conditioning is the second segment node, compiled at the crop
            # canvas so the references are encoded at the size they are seen at.
            # No seam links on it: `prev_image` and the rest anchor the full
            # canvas, and there is no full canvas in a crop.
            face = face_compiled[index]
            face_inputs = {"clip": links.clip,
                           "segment_data": json.dumps(face_payloads[index],
                                                      sort_keys=True)}
            if face.encodes_video():
                face_inputs["vae"] = links.vae
            if face.encodes_audio():
                face_inputs["audio_vae"] = links.audio_vae
            if links.model_fl2va is not None:
                face_inputs["model_fl2va"] = links.model_fl2va
            if links.model_ref2va is not None:
                face_inputs["model_ref2va"] = links.model_ref2va
            crop = graph.node(SEGMENT_NODE, **face_inputs)

            # Patched exactly as the passes are — the LoRAs come with the
            # segment node, cfg 1.0 skips the negative, the accelerators and the
            # preview decoder sit in the same places — because it is the same
            # model answering a smaller question.
            crop_model = patched(graph, crop.out(0), sampling, acceleration, weights)
            source = graph.node(
                FACE_NODE, model=crop_model, positive=crop.out(1),
                negative=graph.node("ConditioningZeroOut",
                                    conditioning=crop.out(1)).out(0),
                vae=links.vae, audio_vae=links.audio_vae,
                source=written.out(1), reel=written.out(0),
                detector=weights.sam3 or "",
                width=one.face.width, height=one.face.height,
                seed=seed_for(index), steps=sampling.steps, cfg=sampling.cfg,
                sampler_name=sampling.sampler_name, scheduler=sampling.scheduler,
                denoise=one.face.denoise)

        reel = source.out(0)
        decoded.append(("pass", source.out(1)))

    # What the save node needs to write each pass out as its own file: which
    # card it is and what seed it ran on. Not where the render is the whole
    # piece made in one go: that take is the render, and writing it twice would
    # be one file to keep and one to delete.
    #
    # "The whole piece" and not "one payload", because those differ exactly
    # where takes matter most. A card shot by itself out of six is one payload,
    # and gating on that is what stopped a piece from ever being shot a pass at
    # a time: the take never landed, so the card could not be kept, so the next
    # render was one payload again, and so on for the whole strip.
    takes = json.dumps({"cards": list(cards),
                        "seeds": [seed_for(index) for index in range(len(payloads))]},
                       sort_keys=True) \
        if cards and (len(payloads) > 1 or not whole_piece) else ""
    emit_tail(graph, reel, unique_id, filename_prefix, takes)
    return graph


def emit_tail(graph, reel, unique_id, filename_prefix=FILENAME_PREFIX, takes=""):
    """Write the reel to a file, and report it against `unique_id`.

    H3 generates picture and sound together and they should leave together, which
    used to mean wiring both outputs into somebody else's save node and getting
    the frame rate wrong. `canvas.FPS` is the rate the frame counts were snapped
    to, so it is the only rate this can be.

    `MiniMaxH3Save` rather than core's `CreateVideo` + `SaveVideo`: `SaveVideo`'s
    `codec` is a `DynamicCombo`, whose value is assembled from the frontend's
    dynamic schema rather than being the plain string it looks like, and a
    built graph has no frontend to assemble it. Ours takes the reel and writes
    it part by part.

    The display-id stamp is the whole reason the node can show its own result —
    see the module docstring.

    The quality target is read here, once, and travels into the graph as an
    ordinary input. That is what makes it take effect on a re-queue: an output
    node with unchanged inputs is a cache hit, so a save node that read the
    setting itself would keep writing yesterday's quality until something else
    about the render changed.

    `takes` is what the strip needs back to keep a pass: the card each part
    belongs to and the seed it ran on. Passed as a plain input rather than read
    off the reel, because the reel knows nothing about cards — and passed as an
    input for the same reason the quality target is one, so that keeping a take
    and re-queueing writes the files again instead of hitting the cache.
    """
    save = graph.node(SAVE_NODE, reel=reel,
                      fps=float(canvas.FPS), filename_prefix=filename_prefix,
                      crf=settings.video_crf(), takes=takes)
    save.set_override_display_id(unique_id)
    return save


class _NoExportedLinks(io.NodeOutput):
    """A `NodeOutput` that expands to a graph and exports nothing from it.

    Neither node has an output socket, so an expansion from either one hands
    nothing back to the graph around it. `NodeOutput.result` collapses "no
    values" to `None`, but the empty tuple is what `execution.py` wants: it
    takes `len()` of the result to find which of the subgraph's outputs are
    links the parent exports, and `None` is a `TypeError` rather than "none of
    them". The rest of the expansion — including the save node that makes the
    file — is already in the graph and runs regardless.
    """

    @property
    def result(self):
        return ()


def expanded(graph):
    """-> the node return for a finished graph. See `_NoExportedLinks`."""
    return _NoExportedLinks(expand=graph.finalize())
