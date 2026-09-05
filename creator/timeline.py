"""A clip made of several shots, in one of two ways.

**Chained** is what the graph machinery below is for: one generation per segment,
concatenated, with segment N able to start from segment N-1's decoded last frame.
It buys length — there is no bound on the finished clip — at the cost of a real
seam at every join.

**One pass** is the other reading of the same timeline. H3's own prompt format is
already a shot list with cut times (`[Shot 2] At 00:05.000, the camera cuts to
...`), so the segments can be compiled into a single multi-shot description and
generated in one go. Nothing is decoded and re-encoded mid-clip, which is what
removes the seam entirely: continuity, sound and colour carry because they were
never broken. `compile.single_payload` does the whole of it — the timeline
becomes one ordinary request and everything downstream is unchanged. What it
costs is anything one pass can only have one of: one mode, one checkpoint, one
LoRA stack, and no per-segment continuation to switch.

The rest of this module is the chained path's **family-neutral** half: the reel
every pass is written into, the readers a seam takes its frames and its sound
back off, the clip nodes that splice supplied footage, the save node — and the
two helpers `creator_node` names its payloads with. Every family renders through
all of it.

A family's own segment node is not here. H3's was, beside these, which made
"what the pack provides" and "what a family brings" a matter of reading each
class; it lives in `families/h3/segment.py` now, where LTX 2.5's has always
lived in its package.

**The user-facing node is not here.** It was, while the Creator and the Timeline
were two of them; they are one now and it lives in `creator_node.py`, because
one shot and twenty are the same node and the pack has one front door. What is
left in this module is the machinery that node expands into — none of it meant
to be placed by hand, all of it `is_dev_only`.

Why a graph rather than an ordinary node at all: segment 2 starts from segment
1's *decoded* last frame, so the chain has a data dependency that only exists
downstream of sampling. Returning conditioning N times would not express it, and
feeding the result back into the node's own input would be a cycle the executor
refuses to run. So the node builds the graph instead of being a node in it —
one `segment -> KSampler -> decode` chain per pass, each chain's last frame
wired into the next, returned through ComfyUI's `expand` mechanism. The "feed the
result back" is a genuine forward edge in a generated graph, not a loop.

One consequence worth knowing before reading further: **editing a segment only
re-runs that segment and the ones after it.** What buys that is easy to lose:
each segment node is handed its own payload rather than the whole piece, so a
payload changes only when its own segment does. Hand a segment the whole blob and
editing the last shot re-generates all of them. The loaders `models.Links`
writes are ordinary nodes keyed on their filenames, so they cache the same way
and are built once for the whole chain.
"""

import json
import logging

from comfy_api.latest import io

from . import (compile as compiler, guide, lora, media, mux,
               outputs, settings, spill)

# The reel's own socket type: the parts of the finished video in play order,
# each of them a file — a pass `spill.py` wrote, or a clip the user supplied.
# See `MiniMaxH3Reel` for why a pass is on disk rather than in the socket.
REEL_TYPE = "MMC_REEL"

# One spilled pass, as the seams beside it read it. Its own type rather than a
# string, so a graph cannot wire a clip's spec where a pass's belongs.
PASS_TYPE = "MMC_PASS"

def _parse(data):
    """One of the payload strings the nodes below are handed, as a dict.

    Not the node's blob — that is `creator_node`'s, and it is a piece rather than
    a payload. These are the self-contained strings the emitter writes onto the
    graph: a segment's, a clip's.
    """
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"segment data is not valid JSON: {exc}") from exc


def stamps(data):
    """Mtimes of every file any segment names, for `fingerprint_inputs`."""
    import os

    out = []

    def stamp(path_of, item, key):
        try:
            out.append(os.path.getmtime(path_of(item.get(key, ""))))
        except Exception:
            out.append(None)

    # The timeline's own LoRAs are patched onto every segment, so a replaced file
    # has to invalidate the node just as a segment's own would. The reference
    # pool is the same story on the asset side: a cited pool file rides into
    # segments, so replacing it has to re-render them.
    for entry in data.get("loras", []) or []:
        stamp(lora.resolve, entry, "name")
    for asset in data.get("assets", []) or []:
        stamp(media.resolve, asset, "filename")
    for segment in data.get("segments", []):
        if not isinstance(segment, dict):
            continue
        # A supplied clip's own file. Without this, replacing the footage under
        # a card that has not otherwise changed would be a cache hit and the
        # render would keep playing the clip that is no longer there.
        if segment.get("filename"):
            stamp(media.resolve, segment, "filename")
        for asset in segment.get("assets", []) or []:
            stamp(media.resolve, asset, "filename")
        for entry in segment.get("loras", []) or []:
            stamp(lora.resolve, entry, "name")
    return tuple(out)


def labels(runs, segments=None, whole_piece=True):
    """What to call each payload in an error raised about it.

    A pass holding one segment is that segment, and is named the way it always
    was — most pieces are nothing but these. A pass holding several is named by
    the cards it covers, because that is what the user would go and look at.

    A piece that is one pass *over the whole strip* has no card worth singling
    out, and there are two of those. One pass over several cards is the one-pass
    render. One pass over one card is a lone generation — there is no strip on
    the node's face, so "Segment 1" would name something the user cannot see. It
    says what the Creator node always said instead, which is what that piece
    still is.

    Over the whole strip, and not merely alone in this render: a card shot by
    itself out of six is also one run, and calling it "This generation" would
    name it as the piece when it is one shot of one. `whole_piece` is whether
    this render covers the strip; True where nobody says otherwise, which is
    what this assumed before a card could be held back.

    `segments` is the piece the runs were read off, and is only ever the
    rendered one — a render that holds cards back is shorter than the strip, so
    a payload's position in it is not the number on the card. `card_no` is the
    number the user is looking at, written by `compile.rendered_piece`; without
    it the position is the number, which is what it has always been.
    """
    def number(index):
        if segments is None:
            return index + 1
        return int(segments[index].get("card_no") or index + 1)

    if len(runs) == 1 and whole_piece:
        covered = runs[0][1] - runs[0][0]
        return ["This generation" if covered == 1 else "This one-pass render"]
    return [f"Segment {number(start)}" if end - start == 1
            else f"Segments {number(start)}-{number(end - 1)}"
            for start, end in runs]



class MiniMaxH3Reel(io.ComfyNode):
    """One pass: decoded, trimmed, written to disk, added to the reel.

    Five things in one node, and the reason is memory. ComfyUI keeps every
    node's output alive for the whole execution, so any node that *returns* a
    decoded pass holds that pass until the render is over — and the render is
    over when the save node has written every one of them. A minute of 768p
    video is 18 GB of float32 held at once, on top of the weights, which on a
    box streaming a staged model from host RAM is the difference between a
    render and the OOM killer.

    So the tensors never leave. They are decoded here, trimmed here, and
    written straight out by `spill.py`; what this returns is a path and a frame
    count. The pass exists in memory for the length of this call and is dropped
    at the end of it, so the peak is one pass rather than all of them, whatever
    the strip is.

    This is the second half of retiring `MiniMaxH3TimelineJoin`. The join
    concatenated — folding N passes built N-1 running totals, all kept alive,
    about 81 GB of intermediates for ten 768p passes on top of the 15 GB of
    passes themselves. The reel took the intermediates away by carrying
    references instead of a total; this takes the passes away too.

    Chained the same way the join was — each reel node takes the one before it —
    because that keeps the growth an ordinary graph edge with no variadic
    inputs, and it keeps a pass's cache key naming exactly the passes in front
    of it.

    The decoders are core's own, called rather than copied: `VAEDecode`'s nested
    unbind and 5-dim reshape, and `vae_decode_audio`'s attenuation of anything
    hot enough to clip, are H3's decode contract and this node has no business
    having a second opinion about them.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3Reel",
            display_name="Continuity Reel",
            category="Continuity/internal",
            description="Decodes one pass, writes it to disk and adds it to the reel.",
            is_dev_only=True,
            inputs=[
                io.Latent.Input("samples"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                # The rate this pass's frames were snapped to. An input rather
                # than a module constant because this node is family-neutral and
                # the rate is not: it converts a seam's width in frames into a
                # count of audio samples, and it is stamped onto the spill for
                # every later reader of that pass. Read off a constant it was
                # H3's 24 whatever family sampled — which both video families
                # happen to agree on, so the error would have been invisible
                # until a family that does not.
                # The default is a schema placeholder and nothing more —
                # every graph this pack builds writes the family's own rate.
                io.Float.Input("fps", default=24.0, min=1.0, max=120.0),
                # The runs this pass shares with its neighbours, dropped before
                # anything is written: a blend re-generates the moment it
                # inherited, and an untrimmed pass would play it twice. `head`
                # is the run taken from the pass in front, `tail` the opening of
                # a supplied clip this one runs into. Optional so a pass with no
                # blend on it has the node inputs — and the cache key — it had
                # before either could happen.
                io.Int.Input("head", default=0, min=0, max=64, optional=True),
                io.Int.Input("tail", default=0, min=0, max=64, optional=True),
                io.Custom(REEL_TYPE).Input("reel", optional=True,
                    tooltip="The passes in front of this one. Absent on the first."),
            ],
            outputs=[io.Custom(REEL_TYPE).Output(display_name="reel"),
                     io.Custom(PASS_TYPE).Output(display_name="pass")],
        )

    @classmethod
    def execute(cls, samples, vae, audio_vae, fps, head=0, tail=0,
                reel=None) -> io.NodeOutput:
        import nodes
        from comfy_extras.nodes_audio import vae_decode_audio

        images = nodes.VAEDecode().decode(vae, samples)[0]
        audio = vae_decode_audio(audio_vae, samples)

        head, tail = max(0, int(head)), max(0, int(tail))
        if head or tail:
            if images.shape[0] <= head + tail:
                # compile refuses a blend of half the segment or more, so
                # hitting this means the graph was built against different
                # arithmetic.
                raise ValueError(
                    f"cannot trim {head + tail} blended frames off a "
                    f"{images.shape[0]}-frame pass")
            rate = int(audio["sample_rate"])
            # Counted off the end rather than as an absolute index: the decoded
            # soundtrack is the same span as the picture but not the same
            # length, and an index computed from the frame count would drift by
            # the rounding.
            head_samples = int(round(head / float(fps) * rate))
            tail_samples = int(round(tail / float(fps) * rate))
            waveform = audio["waveform"][..., head_samples:]
            if tail_samples:
                waveform = waveform[..., :-tail_samples]
            images = images[head:images.shape[0] - tail] if tail else images[head:]
            audio = {"waveform": waveform, "sample_rate": rate}

        written = spill.write(images, audio, float(fps))
        # Dropped before returning rather than left to the frame's teardown:
        # what this node exists to guarantee is that nothing holds a pass once
        # it is on disk, and the largest thing in this scope is that pass.
        del images, audio

        # A new list rather than an append: the reel this was handed is another
        # node's cached output, and growing it in place would rewrite history
        # every time a later pass re-ran.
        return io.NodeOutput([*(reel or []), {"pass": written}], written)


class MiniMaxH3PassFrames(io.ComfyNode):
    """The frames a seam inherits from the pass in front of it.

    A generation continuing from an earlier one starts on its last frame — or,
    blended, its last run of them. Those come back off the spill rather than
    out of a tensor somebody kept: the pass was written to disk the moment it
    decoded, and this reads the seam's width out of it, one frame or at most
    39, however long the pass is.

    They come back as 8-bit, which is what the spill stores and what the file
    was always going to be written as. That is the fidelity a keyframe attached
    from a PNG has always had, and it is the VAE encoder's ordinary diet.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3PassFrames",
            display_name="Continuity Pass Frames",
            category="Continuity/internal",
            description="The final frames of a decoded pass — what the next one continues from.",
            is_dev_only=True,
            inputs=[
                io.Custom(PASS_TYPE).Input("source"),
                # A feathered seam inherits a run instead of a single frame.
                io.Int.Input("count", default=1, min=1, max=64, optional=True),
            ],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def execute(cls, source, count=1) -> io.NodeOutput:
        return io.NodeOutput(spill.frames(source, int(count), "tail"))


class MiniMaxH3PassAudio(io.ComfyNode):
    """The end of a pass's soundtrack — what the next one's sound continues from.

    The picture's counterpart is one frame; sound's is a stretch of it, because
    a single sample says nothing about a room. How long is
    `compile.DEFAULT_AUDIO_TAIL_S` and why it is short is argued there.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3PassAudio",
            display_name="Continuity Pass Audio",
            category="Continuity/internal",
            description="The last few seconds of a decoded pass's sound, for the next one.",
            is_dev_only=True,
            inputs=[
                io.Custom(PASS_TYPE).Input("source"),
                io.Float.Input("seconds", default=compiler.DEFAULT_AUDIO_TAIL_S,
                               min=0.1, max=compiler.MAX_AUDIO_TAIL_S, step=0.1),
            ],
            outputs=[io.Audio.Output()],
        )

    @classmethod
    def execute(cls, source, seconds) -> io.NodeOutput:
        return io.NodeOutput(spill.sound(source, float(seconds), "tail"))


class MiniMaxH3ClipReel(io.ComfyNode):
    """Supplied footage, added to the reel as a file rather than as frames.

    The one node in the chain that decodes nothing. A clip card is part of the
    finished video, and the finished video is written frame by frame — so the
    file only has to be *named* here and `mux.py` demuxes, conforms and
    re-encodes it straight into the container. Two minutes of 768p footage
    would be 35 GB as a tensor; this way it is a dict.

    The audio VAE is taken as an input for one number: the rate its decoder
    outputs at. That is the rate the generated passes' sound arrives at, so it
    is the rate this clip has to be resampled to, and it is a fact about the
    weights on this disk rather than a constant this package may assume.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3ClipReel",
            display_name="Continuity Clip",
            category="Continuity/internal",
            description="Adds a supplied clip to the reel, without decoding it.",
            is_dev_only=True,
            inputs=[
                io.String.Input("clip_data", multiline=True),
                io.Custom(REEL_TYPE).Input("reel", optional=True),
                io.Vae.Input("audio_vae", optional=True,
                    tooltip="Only for its output sample rate — the clip's sound is "
                            "resampled to whatever the generated passes decode at."),
            ],
            outputs=[io.Custom(REEL_TYPE).Output(display_name="reel")],
        )

    @classmethod
    def fingerprint_inputs(cls, clip_data, **kwargs):
        try:
            return (clip_data, stamps({"segments": [json.loads(clip_data)]}))
        except Exception:
            return (clip_data, ())

    @classmethod
    def execute(cls, clip_data, reel=None, audio_vae=None) -> io.NodeOutput:
        spec = dict(_parse(clip_data))
        # Resolved here rather than in `mux.py`, which knows nothing about
        # ComfyUI's folders and is loadable on its own because of it.
        spec["name"] = spec["filename"]
        spec["path"] = media.resolve(spec.pop("filename"))
        if spec.get("sound"):
            if audio_vae is None:
                # The graph wires it whenever the clip plays with its sound, so
                # reaching here means a hand-built graph — say which input is
                # missing rather than writing the clip at the wrong pitch.
                raise ValueError(
                    "this clip plays with its sound, so it needs the audio VAE "
                    "on 'audio_vae' to know what rate to resample it to."
                )
            spec["rate"] = mux.decode_sample_rate(audio_vae)
            spec["channels"] = mux.decode_channels(audio_vae)
        return io.NodeOutput([*(reel or []), {"clip": spec}])


class MiniMaxH3ClipFrames(io.ComfyNode):
    """The frames a seam beside a supplied clip inherits.

    The counterpart to `MiniMaxH3PassFrames`, for a pass that was never
    generated and so has no spill to read back. `at` says which end: the tail is
    what a generation after the clip continues from, the head is what a
    generation *before* it ends on.

    Its own node rather than an output of the clip's reel node, so that a clip
    nothing continues from is never decoded at all. What is decoded here is the
    seam's width — one frame, or a feathered run of at most 39.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3ClipFrames",
            display_name="Continuity Clip Frames",
            category="Continuity/internal",
            description="The first or last frames of a supplied clip, for a seam beside it.",
            is_dev_only=True,
            inputs=[
                io.String.Input("clip_data", multiline=True),
                io.Int.Input("count", default=1, min=1, max=64),
                io.Combo.Input("at", options=["head", "tail"], default="tail"),
            ],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, clip_data, **kwargs):
        try:
            return (clip_data, stamps({"segments": [json.loads(clip_data)]}))
        except Exception:
            return (clip_data, ())

    @classmethod
    def execute(cls, clip_data, count=1, at="tail") -> io.NodeOutput:
        return io.NodeOutput(media.clip_frames(_parse(clip_data), int(count), at))


class MiniMaxH3ClipAudio(io.ComfyNode):
    """The sound a seam beside a supplied clip inherits. See `MiniMaxH3ClipFrames`."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3ClipAudio",
            display_name="Continuity Clip Audio",
            category="Continuity/internal",
            description="The first or last seconds of a supplied clip's sound, for a seam beside it.",
            is_dev_only=True,
            inputs=[
                io.String.Input("clip_data", multiline=True),
                io.Float.Input("seconds", default=compiler.DEFAULT_AUDIO_TAIL_S,
                               min=0.1, max=compiler.MAX_AUDIO_TAIL_S, step=0.1),
                io.Combo.Input("at", options=["head", "tail"], default="tail"),
            ],
            outputs=[io.Audio.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, clip_data, **kwargs):
        try:
            return (clip_data, stamps({"segments": [json.loads(clip_data)]}))
        except Exception:
            return (clip_data, ())

    @classmethod
    def execute(cls, clip_data, seconds=compiler.DEFAULT_AUDIO_TAIL_S,
                at="tail") -> io.NodeOutput:
        return io.NodeOutput(media.clip_audio(_parse(clip_data), float(seconds), at))


class ContinuityGuideFrames(io.ComfyNode):
    """The stretch of a ControlNet guide one shot is aimed at.

    The counterpart to `MiniMaxH3ClipFrames` on the other side of the render: a
    clip's frames are what a seam *inherits*, and these are what a pass is
    *pointed at*. Same shape of job — a window of a file on disk, decoded to the
    frames one generation needs and no more — which is why it sits here beside
    it rather than in a family package. Nothing about reading a drawing off a
    file is an architecture's decision; which node the drawing is then handed to
    is, and that is `Family.emit_control`'s.

    A node rather than a tensor built in the emitter, for the reason every other
    file in this pack is read through one: the emitter runs at queue time on the
    event loop, and decoding fifteen seconds of video there would stall the
    progress socket for every render in the queue. This runs where the executor
    runs it, and ComfyUI caches its output across queues that did not change it.

    Its id is its own rather than a `MiniMaxH3*` one: those are frozen because
    saved workflows name them, and a node that has never shipped has no saved
    workflow to break.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityGuideFrames",
            display_name="Continuity Guide Frames",
            category="Continuity/internal",
            description="One pass's window of a ControlNet guide, at the render's canvas and rate.",
            is_dev_only=True,
            inputs=[
                io.String.Input("filename"),
                io.Float.Input("start", default=0.0, min=0.0, max=86400.0, step=0.001),
                # 0 means "to the end of the file" -- `media._decode_window`'s own
                # convention for a duration of 0, and what an untrimmed guide carries.
                io.Float.Input("end", default=0.0, min=0.0, max=86400.0, step=0.001),
                io.Int.Input("frames", default=5, min=1, max=100000),
                io.Int.Input("width", default=0, min=0, max=16384),
                io.Int.Input("height", default=0, min=0, max=16384),
                io.Float.Input("fps", default=float(media.TARGET_FPS), min=1.0, max=240.0, step=0.001),
            ],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def fingerprint_inputs(cls, filename, **kwargs):
        # The file's mtime beside its name, for `stamps`' reason: re-tracing a
        # guide over the same filename has to re-render the passes aimed at it,
        # and the name alone would be a cache hit on the drawing that is gone.
        return (filename, stamps({"assets": [{"filename": filename}]}))

    @classmethod
    def execute(cls, filename, start=0.0, end=0.0, frames=5, width=0, height=0,
                fps=float(media.TARGET_FPS)) -> io.NodeOutput:
        trim = (float(start), float(end)) if float(end) > float(start) else None
        return io.NodeOutput(guide.read(
            filename, trim, int(frames), int(width), int(height), float(fps)))


def reported_take(part, card, filename, subfolder, fps, seed):
    """One take, as the strip reads it back: which card, and what the file is.

    The length off the pass's own frame count rather than off the file,
    because the file is not open here and the count is what it was written
    from — the same number, arrived at without a probe.
    """
    spec = part["pass"]
    return {
        "segment": card,
        "filename": filename,
        "subfolder": subfolder,
        "type": "output",
        "duration_s": round(int(spec["frames"]) / float(fps), 6),
        "width": int(spec["width"]),
        "height": int(spec["height"]),
        "has_audio": "audio_path" in spec,
        "seed": seed,
    }


class ContinuityTake(io.ComfyNode):
    """One generated pass, written out as a file of its own — as it lands.

    The takes used to be written by the save node, all together, after the
    whole reel existed. Which meant a strip that failed on its last pass kept
    nothing: fourteen good passes sat as spills in a temp directory core wipes
    on restart, no take was ever muxed from them, and the next queue sampled
    all fourteen again. This node is the fix — it hangs off each reel node's
    pass output and is an output node, so the executor writes each take the
    moment its pass exists, whatever happens to the passes after it.

    It also makes a quality change cheap: CRF rides in as an input, so
    re-queueing with a new quality re-muxes every take from its spill instead
    of hitting the cache — and instead of sampling anything.

    Failures are logged and swallowed, the same trade `MiniMaxH3Save._takes`
    has always made: a take that cannot be written must not take the render
    down with it.

    Not emitted for a single-pass render, whose take is the piece's own file
    (see `MiniMaxH3Save._takes`), nor under ReDetail, which rebuilds the reel
    at another size after the passes exist — there the save node still writes
    the takes from the finished reel.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityTake",
            display_name="Continuity Take",
            category="Continuity/internal",
            description="Writes one pass's own file the moment the pass exists.",
            is_dev_only=True,
            is_output_node=True,
            inputs=[
                io.Custom(PASS_TYPE).Input("source"),
                io.Float.Input("fps", default=24.0, min=1.0, max=120.0),
                io.String.Input("filename_prefix", default="continuity/H3"),
                # An input for `MiniMaxH3Save`'s reason: read from settings
                # here, a re-queue after a quality change would be a cache hit.
                io.Int.Input("crf", default=settings.DEFAULT_CRF,
                             min=settings.MIN_CRF, max=settings.MAX_CRF),
                io.Int.Input("card", default=1, min=1, max=9999),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, source, fps, filename_prefix, crf, card, seed) -> io.NodeOutput:
        import os

        import folder_paths

        directory, name, counter, subfolder, _ = folder_paths.get_save_image_path(
            outputs.takes(filename_prefix), folder_paths.get_output_directory(),
            int(source["width"]), int(source["height"]))
        filename = f"{name}_{counter:05}_s{int(card):02}.mp4"
        try:
            mux.write(os.path.join(directory, filename), [{"pass": source}],
                      fps=float(fps), crf=int(crf))
        except Exception as exc:      # noqa: BLE001 - see the docstring
            logging.warning("MiniMax: could not write the take for segment "
                            "%s: %s", card, exc)
            return io.NodeOutput(ui={})
        return io.NodeOutput(ui={"mmc_takes": [reported_take(
            {"pass": source}, int(card), filename, subfolder, fps, int(seed))]})


class MiniMaxH3Save(io.ComfyNode):
    """The last node of every render: the reel, muxed and written out.

    Ours rather than core's `CreateVideo` + `SaveVideo` for one mechanical
    reason: `SaveVideo`'s `codec` is a `DynamicCombo`, whose value the frontend
    assembles out of a dynamic schema. A graph built in Python has no frontend,
    so there is nothing to assemble it and the input arrives as a bare string the
    node then subscripts.

    It takes a reel rather than one clip's tensors, and `mux.py` writes it part
    by part — which is what stops a long timeline from having to exist as one
    concatenated tensor first. That also retired the CRF version gate this node
    used to carry: `VideoFromComponents.save_to` only learned `crf` in ComfyUI
    0.29, so a quality setting had to be refused on anything older. Writing the
    container ourselves, it is always honoured.

    It is an output node, and `core.emit.emit_tail` stamps the calling node's id on
    it, so what it saves is reported against the Creator or Timeline the user is
    looking at rather than against an expanded node on nobody's canvas.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3Save",
            display_name="Continuity Save",
            category="Continuity/internal",
            description="Writes a render's passes into one file under output/.",
            is_dev_only=True,
            is_output_node=True,
            inputs=[
                io.Custom(REEL_TYPE).Input("reel"),
                io.Float.Input("fps", default=24.0, min=1.0, max=120.0),
                io.String.Input("filename_prefix", default="continuity/H3"),
                # An input rather than a read of `settings.py` here, so that
                # changing the quality and re-queueing actually re-writes the
                # file: an output node whose inputs are all unchanged is a
                # cache hit, and the render would keep the quality it had.
                # `core.emit.emit_tail` is the one place that reads the setting.
                io.Int.Input("crf", default=settings.DEFAULT_CRF,
                             min=settings.MIN_CRF, max=settings.MAX_CRF),
                # Which card each part of the reel is and what seed it ran on,
                # or empty on a render with nothing to keep. See `_takes`.
                io.String.Input("takes", default="", optional=True),
            ],
            outputs=[],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def execute(cls, reel, fps, filename_prefix,
                crf=settings.DEFAULT_CRF, takes="") -> io.NodeOutput:
        import os

        import folder_paths
        from comfy.cli_args import args

        width, height = mux.reel_geometry(reel)
        directory, name, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), width, height)

        # The workflow, so a render dropped back onto the canvas rebuilds the node
        # that made it. Same two hidden fields core's savers write, and skipped
        # under --disable-metadata for the same reason.
        metadata = None
        if not args.disable_metadata:
            collected = dict(cls.hidden.extra_pnginfo or {})
            if cls.hidden.prompt is not None:
                collected["prompt"] = cls.hidden.prompt
            metadata = collected or None

        filename = f"{name}_{counter:05}_.mp4"
        mux.write(os.path.join(directory, filename), reel,
                  fps=float(fps), crf=int(crf), metadata=metadata)

        # Not `ui.PreviewVideo`: that reports under "images", the key the stock
        # frontend preview keys on — and with the caller's id stamped on this
        # node, that stock player lands on the canvas node right under the
        # stage already showing the same clip. A key core does not know keeps
        # the report and loses the widget; stage.js reads it by name.
        report = {"mmc_video": [
            {"filename": filename, "subfolder": subfolder, "type": "output"},
        ]}
        kept = cls._takes(reel, takes, filename_prefix, fps, crf,
                          piece=(filename, subfolder))
        if kept:
            report["mmc_takes"] = kept
        return io.NodeOutput(ui=report)

    @classmethod
    def _takes(cls, reel, takes, filename_prefix, fps, crf, piece=None):
        """Every generated pass, written out again as a file of its own.

        What a take is for: a piece is built a pass at a time, and a card whose
        pass came out right should never have to be sampled again. The strip
        splices the file back in as footage it already has — see
        `compile.rendered_piece` — so this is the one thing standing between a
        render and never paying for that pass twice.

        Only the generated passes. A part that is already a file — supplied
        footage, or a take being spliced back in — has nothing to write: it is
        the file it would be written from.

        `piece` is (filename, subfolder) of the render itself, and is the same
        rule said about the render: a reel of one generated pass *is* that pass,
        so its take is the file just written and reporting it is cheaper and
        truer than encoding the same frames again. That is the shape a piece
        shot a pass at a time starts in — one card, generated whole — and
        without it the first card came back with nothing to keep.

        No metadata: the workflow rides in the piece's own container, and a take
        is a working file rather than something to drop back on a canvas.
        Failures are reported and swallowed for the same reason — the render is
        already on disk, and losing the piece over a take that could not be
        written would be the wrong trade entirely.
        """
        import os

        import folder_paths

        try:
            plan = json.loads(takes) if takes else None
        except json.JSONDecodeError:
            plan = None
        if not plan:
            return []

        cards = plan.get("cards") or []
        seeds = plan.get("seeds") or []
        wanted = [index for index, part in enumerate(reel)
                  if not mux.is_clip(part) and index < len(cards)]
        if not wanted:
            return []

        def seed_of(index):
            return int(seeds[index]) if index < len(seeds) and seeds[index] is not None \
                else None

        # The render as its own take — see the docstring. Nothing is written and
        # nothing can fail, so this is above the shelf the others are written to.
        if piece and len(reel) == 1:
            return [cls._reported(reel[0], int(cards[wanted[0]]), piece[0], piece[1],
                                  fps, seed_of(wanted[0]))]

        # One counter for the whole render, so a piece's takes sort together
        # and read as the set they are.
        width, height = mux.reel_geometry(reel)
        directory, name, counter, subfolder, _ = folder_paths.get_save_image_path(
            outputs.takes(filename_prefix), folder_paths.get_output_directory(),
            width, height)

        written = []
        for index in wanted:
            card = int(cards[index])
            filename = f"{name}_{counter:05}_s{card:02}.mp4"
            try:
                mux.write(os.path.join(directory, filename), [reel[index]],
                          fps=float(fps), crf=int(crf))
            except Exception as exc:      # noqa: BLE001 - see the docstring
                logging.warning("MiniMax: could not write the take for segment "
                                "%s: %s", card, exc)
                continue
            written.append(cls._reported(reel[index], card, filename, subfolder,
                                         fps, seed_of(index)))
        return written

    # One take's report — shared with `ContinuityTake`, which writes the same
    # shape from inside the render.
    _reported = staticmethod(reported_take)


# Registered by `creator_node.MiniMaxCreatorExtension` — one extension for the
# package, so there is one place that says what this node pack contains.
NODES = [MiniMaxH3Reel,
         MiniMaxH3PassFrames, MiniMaxH3PassAudio,
         MiniMaxH3ClipReel, MiniMaxH3ClipFrames, MiniMaxH3ClipAudio,
         ContinuityGuideFrames,
         ContinuityTake, MiniMaxH3Save]
