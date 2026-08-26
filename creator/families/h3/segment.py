"""H3's segment node — the family's boundary, same as LTX 2.5's.

`MiniMaxH3TimelineSegment` takes one self-contained payload plus loader links
and returns `(model, positive, latent, lead model)`. That tuple is the whole of
what `core/emit.py` knows about a family, and everything the loop does around it
— the clip branch, the seam wiring, the reel, the save node — never looks inside
a conditioning or a latent.

It lived in `timeline.py` beside the reel, the pass readers, the clip nodes and
the save node, which are family-neutral and shared: every family's render goes
through them. Two kinds of node in one module made "what a family brings" and
"what the pack provides" a matter of reading each class rather than of looking
at the tree. LTX 2.5's equivalent has always been in its own package; this is
H3's, in its.

A self-contained payload rather than the timeline plus an index, so that the
cache key changes when *this* segment changes and not when any other one does.

The node id is a ComfyUI registry key named in saved workflows and is frozen —
`MiniMaxH3TimelineSegment` is still what it is called wherever it lives.
"""

import json

from comfy_api.latest import io

from ... import compile as compiler, lora, media
from . import declare, encode as encoder, payload as payload_repair

SEGMENT_NODE = declare.SEGMENT_NODE


def _parse(data):
    """The payload string this node is handed, as a dict.

    Not the node's blob — that is `creator_node`'s, and it is a piece rather
    than a payload. This is the self-contained string the emitter writes onto
    the graph.
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
            display_name="H3 Segment",
            category="Continuity/internal",
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
                # Which checkpoint is on each VAE socket, for the reference
                # cache to key on. Names and not the loaded objects: a name is
                # the same string across restarts, where a live VAE is a bag of
                # attributes some of which are lambdas whose repr is a memory
                # address — which is exactly how the cache spent a release never
                # hitting after a restart. See `latents.fingerprint`.
                #
                # Optional, and unread by `fingerprint_inputs`: a graph that does
                # not write them keys its references off the weights' shape
                # instead, and no cache key already on disk moves for their being
                # added.
                io.String.Input("vae_name", optional=True,
                    tooltip="The video VAE's filename, so cached references can be keyed to it."),
                io.String.Input("audio_vae_name", optional=True,
                    tooltip="The audio VAE's filename, so cached references can be keyed to it."),
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
                # The turbo lead-in's one question, asked of the node that
                # patches the LoRAs because that is the only place that can
                # answer it. Optional, and written into the graph only when the
                # lead-in is on: a render without one has the inputs — and so
                # the cache key — it had before this existed.
                io.String.Input("hold_lora", optional=True,
                    tooltip="A LoRA to leave off the 'lead model' output — the distillation, for a turbo lead-in."),
            ],
            outputs=[
                io.Model.Output(display_name="model"),
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(),
                # The same model with `hold_lora` left off, for the opening
                # steps of a turbo lead-in. Without a `hold_lora` it *is* the
                # first output — the same object, not a second patch of it —
                # so a graph that never wires this pays nothing for it.
                io.Model.Output(display_name="lead model"),
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
                vae_name=None, audio_vae_name=None,
                model_fl2va=None, model_ref2va=None,
                prev_image=None, prev_audio=None,
                next_image=None, next_audio=None, hold_lora="") -> io.NodeOutput:
        payload = _parse(segment_data)

        # Which segment the queue has reached, told to the stage the moment
        # this segment starts encoding — the sampler that follows reports steps
        # but not whose they are, and on a long strip "23 / 40" says nothing
        # about where in the piece you are. the render loop stamps the index onto
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
        entries = payload["request"].get("loras")
        # The lead-in's model first, off the same unpatched weights: it is the
        # stack minus the distillation, so it carries whatever character or
        # style LoRAs the piece is wearing. Only built when one is named —
        # otherwise the second output is this one, and no LoRA is loaded twice.
        lead = lora.apply(model, entries, compiled.checkpoint,
                          without=hold_lora) if hold_lora else None
        model = lora.apply(model, entries, compiled.checkpoint)

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
            if lead is not None:
                lead = payload_repair.repair(lead)

        cond, latent = encoder.encode(
            clip, vae, audio_vae, compiled, loaded,
            {"vae": vae_name, "audio_vae": audio_vae_name},
            sound=payload.get("sound"))
        return io.NodeOutput(model, cond, latent, model if lead is None else lead)


NODES = [MiniMaxH3TimelineSegment]
