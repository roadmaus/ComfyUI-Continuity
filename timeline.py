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

The rest of this module is the chained path: the nodes the emitter writes into
the expanded graph, and the two helpers `creator_node` names its payloads with.

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
editing the last shot re-generates all of them. The loaders `models.emit_links`
writes are ordinary nodes keyed on their filenames, so they cache the same way
and are built once for the whole chain.
"""

import json
import logging

from comfy_api.latest import io

from . import (canvas, compile as compiler, encode as encoder, lora, media, mux,
               outputs, payload as payload_repair, settings, spill)

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


def _announce(unique_id, progress):
    """Broadcast which segment is being built, keyed to the emitting node.

    `mmc_segment` carries the expanded node's own id — the Timeline's plus a
    GraphBuilder prefix — which `stage.js` prefix-matches exactly as it does
    for the sampler's preview frames. Sent through the running PromptServer;
    a graph executed without one (the test harness) has nobody to tell.
    """
    from server import PromptServer

    server = getattr(PromptServer, "instance", None)
    if server is not None:
        server.send_sync("mmc_segment", {"node": unique_id, **progress})


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


def labels(runs, segments=None):
    """What to call each payload in an error raised about it.

    A pass holding one segment is that segment, and is named the way it always
    was — most pieces are nothing but these. A pass holding several is named by
    the cards it covers, because that is what the user would go and look at.

    A piece that is *one* pass has no card worth singling out, and there are two
    of those. One pass over several cards is the one-pass render. One pass over
    one card is a lone generation — there is no strip on the node's face, so
    "Segment 1" would name something the user cannot see. It says what the
    Creator node always said instead, which is what that piece still is.

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

    if len(runs) == 1:
        return ["This generation" if runs[0][1] - runs[0][0] == 1 else "This one-pass render"]
    return [f"Segment {number(start)}" if end - start == 1
            else f"Segments {number(start)}-{number(end - 1)}"
            for start, end in runs]


class MiniMaxH3TimelineSegment(io.ComfyNode):
    """One segment of a timeline — the Creator node's job for one shot.

    Written into the graph by `MiniMaxH3Timeline` and not meant to be placed by
    hand. It takes a self-contained payload rather than the timeline plus an
    index, so that its cache key changes when *this* segment changes and not
    when any other one does.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3TimelineSegment",
            display_name="MiniMax H3 Timeline Segment",
            category="MiniMax/internal",
            description="One segment of a MiniMax H3 timeline. Written into the graph by the Timeline node.",
            is_dev_only=True,
            inputs=[
                io.Clip.Input("clip"),
                # Optional because a text-only segment encodes no picture: the
                # video VAE is reached for only when there is a keyframe or a
                # visual reference to turn into a condition latent, so the graph
                # leaves it unwired otherwise and the loader stays a decode-time
                # cost. Absent when it *is* needed raises below rather than
                # reaching a None inside the encoder.
                io.Vae.Input("vae", optional=True),
                # Optional for the same reason on the sound side: nothing on the
                # encode path touches the audio VAE unless the request carries
                # reference audio or a sound seam. The PreStage's still branch
                # emits this node without one either way. Both raise below if it
                # is missing rather than reaching a None.
                io.Vae.Input("audio_vae", optional=True),
                io.String.Input("segment_data", multiline=True),
                io.Model.Input("model_fl2va", optional=True),
                io.Model.Input("model_ref2va", optional=True),
                io.Image.Input("prev_image", optional=True,
                    tooltip="An earlier segment's last frame, when this segment continues from it."),
                io.Audio.Input("prev_audio", optional=True,
                    tooltip="The tail of an earlier segment's soundtrack, when this segment's sound continues from it."),
                io.Image.Input("next_image", optional=True,
                    tooltip="The opening frames of the supplied clip this segment runs into."),
                io.Audio.Input("next_audio", optional=True,
                    tooltip="The opening of that clip's soundtrack, when this segment's sound runs into it."),
            ],
            outputs=[
                io.Model.Output(display_name="model"),
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(),
            ],
            # For the "now rendering segment N" report — the announce below
            # names this node, whose id is the Timeline's plus a GraphBuilder
            # prefix, and the stage prefix-matches it back to the node body.
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, segment_data, **kwargs):
        try:
            payload = json.loads(segment_data)
            return (segment_data, stamps({"segments": [payload.get("request", {})]}))
        except Exception:
            return (segment_data, ())

    @classmethod
    def execute(cls, clip, segment_data, vae=None, audio_vae=None,
                model_fl2va=None, model_ref2va=None,
                prev_image=None, prev_audio=None,
                next_image=None, next_audio=None) -> io.NodeOutput:
        payload = _parse(segment_data)

        # Which segment the queue has reached, told to the stage the moment
        # this segment starts encoding — the sampler that follows reports steps
        # but not whose they are, and on a long strip "23 / 40" says nothing
        # about where in the piece you are. `render.emit` stamps the index onto
        # multi-segment payloads only, so a Creator render announces nothing.
        # A cached segment never executes and so never announces, which is
        # right: the stage should name the segment actually being made.
        progress = payload.get("progress")
        if progress:
            _announce(cls.hidden.unique_id, progress)

        compiled = compiler.compile_segment(payload, image_size_lookup=media.image_size)

        # Both VAEs are wired only when the encoder will actually reach for them
        # (`render` gates on the same two predicates), so a missing one here is a
        # graph that decided this segment needs no encode with it. Named before
        # any of it runs: a hand-built graph should hear which input is missing
        # rather than meet a None inside the encoder.
        if vae is None and compiled.encodes_video():
            raise ValueError(
                "This generation encodes a keyframe or a visual reference, so it "
                "needs the video VAE on 'vae'."
            )
        if audio_vae is None and compiled.encodes_audio():
            raise ValueError(
                "This generation carries sound — reference audio, or a seam "
                "continuing the previous segment's — so it needs the audio VAE "
                "on 'audio_vae'."
            )

        # `prompt_override` replaces the composed prompt verbatim, after
        # compiling — routing, canvas and references are all still worked out
        # from the request, and only the text the DiT reads is swapped. It has no
        # control of its own any more: the node has no sockets, and the refiner's
        # editable rewrite is the same escape hatch with a UI on it. Still read
        # here because a hand-written blob may carry one, and because it lives
        # inside the string this node caches on, so changing it re-runs the
        # generation exactly as editing the prompt would.
        override = payload.get("prompt_override")
        if override:
            compiled.prompt = override

        model = {"fl2va": model_fl2va, "ref2va": model_ref2va}[compiled.checkpoint]
        if model is None:
            raise ValueError(
                f"This segment is {compiled.mode}, which needs the "
                f"{compiled.checkpoint.upper()} checkpoint — connect it to "
                f"'model_{compiled.checkpoint}'."
            )
        model = lora.apply(model, payload["request"].get("loras"), compiled.checkpoint)

        loaded = media.load_all(compiled)
        if compiled.continues:
            if prev_image is None:
                raise ValueError(
                    "This segment continues from an earlier one but no frame "
                    "reached it — the Timeline node should have wired one."
                )
            if prev_image.shape[0] < compiled.feather:
                raise ValueError(
                    f"this seam inherits {compiled.feather} frames but only "
                    f"{prev_image.shape[0]} reached it — shorten the feather "
                    f"or lengthen the source segment"
                )
            loaded[encoder.PREV_FRAME] = {"image": prev_image[-compiled.feather:]}
        if compiled.continues_audio:
            if prev_audio is None:
                raise ValueError(
                    "This segment's sound continues from an earlier one but no "
                    "audio reached it — the Timeline node should have wired some."
                )
            loaded[encoder.PREV_AUDIO] = {"audio": prev_audio}
        if compiled.ends_on:
            if next_image is None:
                raise ValueError(
                    "This segment runs into the clip after it but no frame "
                    "reached it — the Timeline node should have wired one."
                )
            if next_image.shape[0] < compiled.ends_feather:
                raise ValueError(
                    f"this seam blends {compiled.ends_feather} frames of the "
                    f"clip that follows but only {next_image.shape[0]} reached "
                    f"it — shorten the blend, or use more of the clip"
                )
            loaded[encoder.NEXT_FRAME] = {"image": next_image[:compiled.ends_feather]}
        if compiled.ends_on_audio:
            if next_audio is None:
                raise ValueError(
                    "This segment's sound runs into the clip after it but no "
                    "audio reached it — the Timeline node should have wired some."
                )
            loaded[encoder.NEXT_AUDIO] = {"audio": next_audio}
        if (compiled.continues or compiled.continues_audio
                or compiled.ends_on or compiled.ends_on_audio):
            # What core's payload assembly cannot express — keyframes alongside
            # references, guides at real timeline positions — is repaired just
            # before the forward; `payload.py` says exactly what and why. Inert
            # on a seam that needs neither, so every seam wears it rather than
            # this node re-deriving which ones do.
            model = payload_repair.repair(model)

        cond, latent = encoder.encode(clip, vae, audio_vae, compiled, loaded)
        return io.NodeOutput(model, cond, latent)


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
            display_name="MiniMax H3 Reel",
            category="MiniMax/internal",
            description="Decodes one pass, writes it to disk and adds it to the reel.",
            is_dev_only=True,
            inputs=[
                io.Latent.Input("samples"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
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
    def execute(cls, samples, vae, audio_vae, head=0, tail=0, reel=None) -> io.NodeOutput:
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
            head_samples = int(round(head / canvas.FPS * rate))
            tail_samples = int(round(tail / canvas.FPS * rate))
            waveform = audio["waveform"][..., head_samples:]
            if tail_samples:
                waveform = waveform[..., :-tail_samples]
            images = images[head:images.shape[0] - tail] if tail else images[head:]
            audio = {"waveform": waveform, "sample_rate": rate}

        written = spill.write(images, audio, canvas.FPS)
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
            display_name="MiniMax H3 Pass Frames",
            category="MiniMax/internal",
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
            display_name="MiniMax H3 Pass Audio",
            category="MiniMax/internal",
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
            display_name="MiniMax H3 Clip",
            category="MiniMax/internal",
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
            display_name="MiniMax H3 Clip Frames",
            category="MiniMax/internal",
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
            display_name="MiniMax H3 Clip Audio",
            category="MiniMax/internal",
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

    It is an output node, and `render.emit_tail` stamps the calling node's id on
    it, so what it saves is reported against the Creator or Timeline the user is
    looking at rather than against an expanded node on nobody's canvas.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3Save",
            display_name="MiniMax H3 Save",
            category="MiniMax/internal",
            description="Writes a render's passes into one file under output/.",
            is_dev_only=True,
            is_output_node=True,
            inputs=[
                io.Custom(REEL_TYPE).Input("reel"),
                io.Float.Input("fps", default=float(canvas.FPS), min=1.0, max=120.0),
                io.String.Input("filename_prefix", default="minimax/H3"),
                # An input rather than a read of `settings.py` here, so that
                # changing the quality and re-queueing actually re-writes the
                # file: an output node whose inputs are all unchanged is a
                # cache hit, and the render would keep the quality it had.
                # `render.emit_tail` is the one place that reads the setting.
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
        kept = cls._takes(reel, takes, filename_prefix, fps, crf)
        if kept:
            report["mmc_takes"] = kept
        return io.NodeOutput(ui=report)

    @classmethod
    def _takes(cls, reel, takes, filename_prefix, fps, crf):
        """Every generated pass, written out again as a file of its own.

        What a take is for: a piece is built a pass at a time, and a card whose
        pass came out right should never have to be sampled again. The strip
        splices the file back in as footage it already has — see
        `compile.rendered_piece` — so this is the one thing standing between a
        render and never paying for that pass twice.

        Only the generated passes. A part that is already a file — supplied
        footage, or a take being spliced back in — has nothing to write: it is
        the file it would be written from.

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

        # One counter for the whole render, so a piece's takes sort together
        # and read as the set they are.
        width, height = mux.reel_geometry(reel)
        directory, name, counter, subfolder, _ = folder_paths.get_save_image_path(
            outputs.takes(filename_prefix), folder_paths.get_output_directory(),
            width, height)

        written = []
        for index in wanted:
            spec = reel[index]["pass"]
            card = int(cards[index])
            filename = f"{name}_{counter:05}_s{card:02}.mp4"
            try:
                mux.write(os.path.join(directory, filename), [reel[index]],
                          fps=float(fps), crf=int(crf))
            except Exception as exc:      # noqa: BLE001 - see the docstring
                logging.warning("MiniMax: could not write the take for segment "
                                "%s: %s", card, exc)
                continue
            written.append({
                "segment": card,
                "filename": filename,
                "subfolder": subfolder,
                "type": "output",
                "duration_s": round(int(spec["frames"]) / float(fps), 6),
                "width": int(spec["width"]),
                "height": int(spec["height"]),
                "has_audio": "audio_path" in spec,
                "seed": int(seeds[index]) if index < len(seeds) else None,
            })
        return written


# Registered by `creator_node.MiniMaxCreatorExtension` — one extension for the
# package, so there is one place that says what this node pack contains.
NODES = [MiniMaxH3TimelineSegment, MiniMaxH3Reel,
         MiniMaxH3PassFrames, MiniMaxH3PassAudio,
         MiniMaxH3ClipReel, MiniMaxH3ClipFrames, MiniMaxH3ClipAudio,
         MiniMaxH3Save]
