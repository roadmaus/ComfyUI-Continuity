"""One generation, as a graph — the loop every family renders through.

Both the Creator and the Timeline own their sampler, and neither can be an
ordinary node because of it: a node that samples has to *be* the sampler, and
ComfyUI has no way to say that except by returning a subgraph. So both compile
their blob to payloads and hand them here, and this emits

    loaders -> segment -> sampler subgraph -> Reel -> Save

once per payload, adding each to the reel the save node writes. The Creator
passes one payload and the Timeline passes one per segment; a single-payload
render is the same code with the loop running once, which is why there is no
second implementation of it and must not be. Everything the two nodes disagree
about — how the blob becomes payloads, what the widgets are called — stays in
the nodes; everything a *family* decides — what the loaders are, how the
segment is wired, what a sampler subgraph looks like — comes in as the `family`
argument (`families/base.py` is the contract, `families/h3/render.py` the one
implementation today).

What stays in this loop is what holds for any family: the routing and progress
stamping, the clip branch, the seam wiring, the reel, the save node and the
takes. The reel layer is family-neutral by construction — core's joint AV
latent is a `NestedTensor` and `LTXVConcatAVLatent`'s own description says
"any AV model" — which is why the loop can decode and spill without asking the
family anything beyond `.vae` and `.audio_vae` on its links object.

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
node to, which made a node built to need no wiring need six. The family builds
the loaders here now, and the tail below muxes and saves. Neither node has a
socket left.

**`set_override_display_id` is what puts the finished video back in the node.**
An expanded node's UI result is broadcast against its own id, which is our id
plus a `GraphBuilder` prefix and is on nobody's canvas. Stamping the parent's id
on the save node makes `execution.py` file its `executed` message under the node
the user is actually looking at, so the body can play what it just made without
anything being faked or wired.

The reel, clip, pass and save nodes keep their `MiniMaxH3*` ids whatever family
renders through them: they are ComfyUI registry keys named in saved workflows,
and frozen for it.
"""

import json

from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder

from .. import canvas, media, outputs, settings

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


def compile_all(family, payloads, labels):
    """Payloads -> the family's compiled form, failing with the caller's own
    name for each one.

    Done before a single node is emitted so that a request which cannot compile,
    or which routes to a checkpoint nothing is connected to, fails now rather
    than after the first sampler pass has already run.

    A supplied clip compiles to `None`: there is no request in it, no mode and
    no checkpoint, and every caller below reads the absence as "this pass is
    played rather than generated" rather than being handed a hollow compiled
    object that would have to answer questions it has no answer to.
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
            out.append(family.compile(payload, media.image_size))
        except family.compile_error as exc:
            raise ValueError(f"{where}: {exc}") from exc
    return out


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


def emit(family, payloads, labels, weights, sampling, acceleration, unique_id,
         filename_prefix=FILENAME_PREFIX, cards=None, seeds=None,
         whole_piece=True, run=None, upscaler=None):
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

    `weights`, `sampling`, `acceleration` and `run` are the family's own shapes
    and pass through this loop unread — `run` is the family's per-queue context
    (H3's is the turbo lead-in), already normalised by the caller. The two
    things the loop does read are the contract's fine print in
    `families/base.py`: `weights.routed(payload)` and the `.vae`/`.audio_vae`
    links on what `emit_loaders` returns.

    `upscaler` is the blob's upscale-backend weights, read by the caller the
    same way the family's are and passed through unread unless a compiled
    payload asks for the pass. It belongs to no family — ReDetail re-renders an
    H3 pass through LTX 2.5's files — which is exactly why it arrives beside
    `weights` rather than inside it.

    `whole_piece` is whether this render covers the strip the user is looking
    at. Everything below that used to ask "is there only one payload" is really
    asking "is this render the whole piece, made in one go", and those were the
    same question until a card could be held back. They stopped being it the
    moment they could: a card shot by itself out of six is one payload and is
    emphatically not a lone generation. True where nobody says otherwise, which
    is what this assumed before holding existed.
    """
    # All three of these raise, and all three are cheap: a run the family
    # cannot make, a request that cannot compile, or weights that were never
    # picked should say so before anything is queued rather than after the
    # first segment has sampled.
    family.preflight(sampling, acceleration)
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
    compiled = compile_all(family, payloads, labels)
    where = family.routes(compiled, labels)

    # The face pass's conditioning is a second compile of the same segment at
    # the crop canvas, and dropping the keyframes can land it on the other
    # checkpoint — so it is compiled here, before the loaders are built, and its
    # route joins the set they are built from. `None` wherever a pass is not
    # having its face repaired, so the list indexes alongside `compiled`.
    face_payloads = [family.face_payload(payloads[index], one.face)
                     if one and one.face else None
                     for index, one in enumerate(compiled)]
    face_compiled = compile_all(family, face_payloads, labels) if any(face_payloads) \
        else [None] * len(payloads)
    where = {**family.routes(face_compiled, labels), **where}
    family.check(weights, where, face=any(face_payloads))

    # This card's own seed where it has one, the node's everywhere else. Held as
    # a lookup rather than folded into the payloads: the payload is the segment
    # node's cache key and the seed is not one of its inputs — it goes to the
    # sampler — so putting it there would re-encode every conditioning for a
    # re-roll that changes no conditioning at all.
    def seed_for(index):
        seed = (seeds or [None] * len(payloads))[index]
        return sampling.seed if seed is None else int(seed)

    graph = GraphBuilder()
    links = family.emit_loaders(graph, weights, set(where))
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

        # The seams, wired here because they are the loop's own bookkeeping —
        # which pass a segment inherits from is a fact about the strip, not
        # about the family. The links land on the segment node in this order,
        # so a graph without a seam keeps the inputs it always had.
        source = decoded[payloads[index].get("continue_from", index - 1)] \
            if index else (None, None)
        seams = {}
        if one.continues:
            # Only the tail, not the whole batch: the source segment's images
            # are a video and what this one inherits is its last moment — or,
            # feathered, its last few. Inserted here rather than after every
            # segment, so a render of hard cuts has no dead nodes in it and a
            # Creator render has none at all. The count rides only on feathered
            # seams, so a classic seam's node inputs stay byte-identical.
            seams["prev_image"] = inherited_frames(graph, source, one.feather)
        if one.continues_audio:
            # `one.audio_tail_s` rather than the timeline's setting directly:
            # compile clamps it to a feathered seam's overlap, and this is
            # where that decision reaches the graph.
            seams["prev_audio"] = inherited_audio(graph, source, one.audio_tail_s)
        if one.ends_on or one.ends_on_audio:
            # The seam running the other way: the pass after this one is
            # supplied footage, and this generation ends on its opening rather
            # than cutting to it. Always the pass immediately after — what a
            # generation can end on is decided while it is sampled, so there is
            # no reaching further forward the way a seam reaches back.
            ahead = payloads[index + 1]["clip"]
            if one.ends_on:
                seams["next_image"] = graph.node(
                    CLIP_FRAMES_NODE, clip_data=json.dumps(ahead, sort_keys=True),
                    count=one.ends_feather, at="head").out(0)
            if one.ends_on_audio:
                seams["next_audio"] = graph.node(
                    CLIP_AUDIO_NODE, clip_data=json.dumps(ahead, sort_keys=True),
                    seconds=one.ends_tail_s, at="head").out(0)

        segment = family.emit_segment(graph, links, payloads[index], one,
                                      weights, sampling, seams, run)
        latent = family.emit_sampler(graph, segment, payloads[index], one,
                                     sampling, acceleration, weights,
                                     seed_for(index), run)
        if one.refine:
            latent = family.emit_refine(graph, links, segment, payloads[index],
                                        one, weights, seams, latent, sampling,
                                        acceleration, seed_for(index), run)

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
            REEL_NODE, samples=latent, vae=links.vae, audio_vae=links.audio_vae,
            # The family's rate, for the same reason the save node is given it:
            # the frame counts were snapped to it, so the seam trim's sample
            # arithmetic and the spill's stamp are both wrong at any other.
            fps=float(family.rules.fps),
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
            source = family.emit_face(graph, links, face_payloads[index],
                                      face_compiled[index], one.face, written,
                                      weights, sampling, acceleration,
                                      seed_for(index))

        reel = source.out(0)
        decoded.append(("pass", source.out(1)))

    # The re-detail pass, on the finished reel. After the loop and not inside it,
    # which is the opposite of where the face pass goes and for the same reason
    # the face pass goes where it does: what comes back is a *different size*,
    # and a seam that inherited it would hand the next segment a guide at twice
    # the canvas it is about to sample at. Every part is re-rendered or none is —
    # the muxer holds a reel's parts to one geometry, and `timeline_payloads`
    # has already refused a strip carrying footage this cannot re-render.
    if any(one is not None and one.redetail for one in compiled):
        from .. import redetailpass

        reel = redetailpass.emit(graph, family, links, upscaler, compiled, reel,
                                 seed_for(0))

    # What the save node needs to keep each pass as a take: which card it is and
    # what seed it ran on. Asked for on every render that knows its cards,
    # including the lone generation — a piece of one card is where a piece shot
    # a pass at a time *starts*, and a strip whose first card came back with no
    # take could only go on by shooting it again. The old gate read "the whole
    # piece in one go has nothing to keep, because that take is the render",
    # which is true about the file and wrong about the card: the render is the
    # take, so the save node reports the piece's own file as one rather than
    # writing it twice. See `MiniMaxH3Save._takes`.
    takes = json.dumps({"cards": list(cards),
                        "seeds": [seed_for(index) for index in range(len(payloads))]},
                       sort_keys=True) if cards else ""
    emit_tail(graph, reel, unique_id, filename_prefix, takes,
              fps=float(family.rules.fps))
    return graph


def emit_tail(graph, reel, unique_id, filename_prefix, takes, fps):
    """Write the reel to a file, and report it against `unique_id`.

    An AV family generates picture and sound together and they should leave
    together, which used to mean wiring both outputs into somebody else's save
    node and getting the frame rate wrong. The rate is the one the frame counts
    were snapped to and so is the family's, not this module's — required rather
    than defaulted, because there is no rate this module could pick that is not
    some other family's.

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
                      fps=float(fps), filename_prefix=filename_prefix,
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
