"""LTX 2.5's segment node — the family's boundary, same as H3's.

`MiniMaxLTX25Segment` is to this family what `MiniMaxH3TimelineSegment` is to
H3: one self-contained payload in, `(model, positive, latent, negative)` out.
A new node id rather than a reuse, because it is a genuinely new node — a
different conditioning, a different latent, and a fourth output that is a real
negative rather than H3's held-back lead model.

**Why the negative is an output at all.** H3's checkpoints are CFG-distilled and
sample at 1.0, where the negative is skipped, so its sampler builds one with
`ConditioningZeroOut` and never has to encode a second prompt. LTX guides the
two modalities of a packed AV latent apart through `LTXVDualCFGGuider`, whose
uncond pass always runs — and every guide node in core's LTX set
(`LTXVAddGuide`, `LTXVConditioning`) takes *both* conditionings and returns
both, because a keyframe has to be described to the negative as well or the
guidance pulls against its own condition latents. So positive and negative are
built together here and travel together, and the sampler hook takes the pair.

**Why the whole conditioning is built in Python rather than emitted as core
nodes.** The number of guides is a property of the payload — a keyframe, a last
frame, one or two seams — so a graph would need a variable-length chain, and the
images come from `media`'s resolver rather than from a `LoadImage`. This is the
same reason H3's segment node exists, and the payload string is the same cache
key: edit one card and only that card's node re-runs.

**The order the latent is built in is load-bearing.** `LTXVAddGuide.append_keyframe`
refuses a combined AV latent outright — it checks the channel count against the
video VAE's 128 — so every guide goes onto the *video* latent, and the audio
stream is concatenated after. Reversing the two is a ValueError from inside
core with nothing in it about guides.
"""

import json
import logging

import torch
from comfy_api.latest import io

from ... import canvas, compile as compiler, lora, media
from . import models as slots

SEGMENT_NODE = "MiniMaxLTX25Segment"

# Lightricks' own negative for this family, as diffusers ships it. Used rather
# than invented: a negative prompt is a piece of the model's release, and a
# template string of our own would be this pack having an opinion about weights
# it did not train. Editable like any other — it is the row's default, not a
# constraint — but there is nowhere in the UI to edit it yet, which is why it is
# spelled here and not hidden behind a setting nobody would find.
DEFAULT_NEGATIVE = "worst quality, inconsistent motion, blurry, jittery, distorted"


def _core(node_id):
    """One of core's LTX nodes, by registry key.

    By key rather than by import, for the reason `families/h3/render.py` writes
    its node ids as strings: these are ComfyUI registry entries, and a pack that
    imported `comfy_extras.nodes_lt` directly would break the day core moved the
    module rather than the day it removed the node.
    """
    import nodes

    try:
        return nodes.NODE_CLASS_MAPPINGS[node_id]
    except KeyError:
        raise ValueError(
            f"This render needs core's '{node_id}' node, which this ComfyUI "
            f"does not have. LTX 2.5 needs a ComfyUI new enough to ship the "
            f"LTX-AV nodes; update it, or switch the piece's model pill back "
            f"to MiniMax H3."
        ) from None


def _encode(clip, text):
    """One prompt through Gemma. Plain prose — see `compile.plain_prompt`."""
    tokens = clip.tokenize(text)
    return clip.encode_from_tokens_scheduled(tokens)


def _empty_video_latent(width, height, length):
    """`EmptyLTXVLatentVideo`'s tensor, built here rather than through the node.

    The node is four widgets around one `torch.zeros`, and calling it would mean
    resolving a registry key for arithmetic that is the VAE's downscale ratio
    written out. The shape is the one thing that must not drift, so it is copied
    with the ratio named: /32 on both spatial axes, 8:1 in time with the first
    latent frame standing for one pixel frame, 128 channels.
    """
    import comfy.model_management

    return {"samples": torch.zeros(
        [1, 128, ((length - 1) // 8) + 1, height // 32, width // 32],
        device=comfy.model_management.intermediate_device()),
        "downscale_ratio_spacial": 32}


def _predicted_frames(model, positive, duration_head, compiled, rules):
    """How long this shot wants to be, asked of the model. -> a frame count.

    **Why this cannot happen before the queue.** `LTXVDurationPredictor` runs
    the transformer's own caption connectors over the encoded prompt, so it
    needs the loaded 22B DiT and the encoded conditioning — the two most
    expensive things a render does. There is no cheap route a pill could call
    to fill a number in while somebody types. So "auto" is resolved *here*, and
    the count `compile_request` worked out from the pill stays what the strip's
    bar counts: an estimate, and labelled one.

    **The clamp is not the head's default.** Its own is 1–20 s, which is what
    Lightricks trained; what is passed is that range with the floor raised to
    fit this segment's seams. A feathered seam re-generates its inherited run at
    the head of the pass and the reel trims it off after decode, so a pass
    shorter than twice its blend delivers less than it re-made — `compile_request`
    refuses that outright for a length the user set, and this is the same rule
    said to the model as a bound instead of to the user as an error.
    """
    if duration_head is None:
        raise ValueError(
            "This shot's length is set to 'auto', which asks LTX's duration "
            "head how long it wants to be — and no duration head has been "
            "picked. Choose one under the node's 'weights' control "
            "(models/model_patches), or set the seconds pill to a length."
        )
    overlap = ((compiled.feather if compiled.feather > 1 else 0)
               + (compiled.ends_feather if compiled.ends_feather > 1 else 0))
    floor = max(rules.trained_min_frames / rules.fps,
                2 * overlap / rules.fps)
    frames, seconds = _core("LTXVDurationPredictor").execute(
        model, positive, duration_head, float(rules.fps),
        floor, rules.trained_max_frames / rules.fps)[:2]
    logging.info(
        "[MiniMax] LTX 2.5: the duration head asked for %.2f s; rendering %d "
        "frames (%.2f s at %d fps). The strip's bar showed %d — it is an "
        "estimate whenever a card is on auto.",
        seconds, frames, frames / rules.fps, rules.fps, compiled.frames)
    return int(frames)


class MiniMaxLTX25Segment(io.ComfyNode):
    """One segment of an LTX 2.5 piece. Written into the graph by the loop."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=SEGMENT_NODE,
            display_name="MiniMax LTX 2.5 Segment",
            category="MiniMax/internal",
            description="One segment of an LTX 2.5 piece. Written into the graph by the Creator node.",
            is_dev_only=True,
            inputs=[
                io.Model.Input("model"),
                io.Clip.Input("clip"),
                # Required, unlike H3's: every guide goes through the video VAE
                # and the empty audio latent is shaped from the audio VAE's own
                # config, so an LTX render reaches for both before it samples
                # whatever the payload says. There is no soundless mode to gate
                # on — the family generates a packed AV latent, always.
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.String.Input("segment_data", multiline=True),
                # The duration head, wired only when this card's length is the
                # model's to pick. A `MODEL_PATCH` like any other, loaded
                # through core's `ModelPatchLoader` — see `render.Links`, which
                # builds it lazily for the same reason it builds the upscaler
                # lazily: it is a pass, not a component.
                io.Custom("MODEL_PATCH").Input("duration_head", optional=True,
                    tooltip="LTX's duration head, when this shot's length is the model's to pick."),
                io.Image.Input("prev_image", optional=True,
                    tooltip="An earlier segment's last frame, when this segment continues from it."),
                io.Audio.Input("prev_audio", optional=True,
                    tooltip="The tail of an earlier segment's soundtrack. Not yet conditioned on — see the node's source."),
                io.Image.Input("next_image", optional=True,
                    tooltip="The opening frames of the supplied clip this segment runs into."),
                io.Audio.Input("next_audio", optional=True,
                    tooltip="The opening of that clip's soundtrack. Not yet conditioned on."),
            ],
            outputs=[
                io.Model.Output(display_name="model"),
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(),
                io.Conditioning.Output(display_name="negative"),
            ],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, segment_data, **kwargs):
        from ... import timeline

        try:
            payload = json.loads(segment_data)
            return (segment_data,
                    timeline.stamps({"segments": [payload.get("request", {})]}))
        except Exception:
            return (segment_data, ())

    @classmethod
    def execute(cls, model, clip, vae, audio_vae, segment_data,
                duration_head=None, prev_image=None, prev_audio=None,
                next_image=None, next_audio=None) -> io.NodeOutput:
        from ... import timeline

        payload = json.loads(segment_data)
        progress = payload.get("progress")
        if progress:
            timeline._announce(cls.hidden.unique_id, progress)

        compiled = compiler.compile_segment(
            payload, image_size_lookup=media.image_size, family="ltx25")

        override = payload.get("prompt_override")
        if override:
            compiled.prompt = override

        model = lora.apply(model, payload["request"].get("loras"),
                           compiled.checkpoint)

        positive = _encode(clip, compiled.prompt)
        negative = _encode(clip, DEFAULT_NEGATIVE)

        rules = canvas.RULES["ltx25"]
        frames = compiled.frames
        if compiled.auto_duration:
            frames = _predicted_frames(model, positive, duration_head, compiled,
                                       rules)

        latent = _empty_video_latent(compiled.width, compiled.height, frames)

        add_guide = _core("LTXVAddGuide")

        def guide(image, frame_idx, strength=1.0):
            nonlocal positive, negative, latent
            positive, negative, latent = add_guide.execute(
                positive, negative, vae, latent, image, frame_idx, strength)

        # The guides, in timeline order, which is also the order their frame
        # indexes ascend. `LTXVAddGuide` appends each one's condition latent past
        # the end of the sequence and records where in time it belongs, so the
        # order is not arithmetic — but it is what a reader of the graph expects,
        # and it keeps the emitted node list stable for the golden suite.
        #
        # A seam wins over a keyframe at the same end: a continuing segment
        # inherits real frames from the pass in front, and a first frame the user
        # also attached would be describing the same instant twice.
        if compiled.continues:
            if prev_image is None:
                raise ValueError(
                    "This segment continues from an earlier one but no frame "
                    "reached it — the render loop should have wired one.")
            # The inherited run, pinned at the head on this segment's own
            # timeline. `feather` frames of it, which the loop has already
            # trimmed to — and which is already on the 8n+1 grid, because
            # `canvas.feather_grid` derives the widths this family offers from
            # the same packing. That matters: `LTXVAddGuide` crops a guide to
            # the nearest 8n+1 *silently*, so H3's 5-frame blend would arrive
            # here, leave as one frame, and still have five trimmed off the
            # head of the decoded pass.
            guide(prev_image[-compiled.feather:], 0)
        elif compiled.first_frame is not None:
            guide(media.load_image(compiled.first_frame.filename), 0)

        if compiled.ends_on:
            if next_image is None:
                raise ValueError(
                    "This segment runs into the clip after it but no frame "
                    "reached it — the render loop should have wired one.")
            # Negative indexes count from the end of the video, which is exactly
            # what "the last N frames are the clip's opening" means and saves
            # this having to know the latent length.
            guide(next_image[:compiled.ends_feather], -compiled.ends_feather)
        elif compiled.last_frame is not None:
            guide(media.load_image(compiled.last_frame.filename), -1)

        # References are carried by the prompt and by nothing else, and that is
        # a real limitation rather than an oversight. A guide is a keyframe: it
        # pins picture at an instant. Attaching a character sheet as a guide at
        # frame 0 would make the character sheet the first frame of the video,
        # which is not what citing a reference means on H3 and is not what
        # anybody attaching one wants. What LTX 2.5 has instead is IC-LoRAs and
        # `GetICLoRAParameters`, and choosing that grammar is the open question
        # the plan records. Until it is chosen the files ride as their `<Picture
        # N>` labels in the prose, the render proceeds, and this says so once so
        # that a reference doing nothing visible is legible in the log rather
        # than mysterious on screen.
        cited = len(compiled.ref_images) + len(compiled.ref_videos) + len(compiled.ref_audios)
        if cited:
            logging.info(
                "[MiniMax] LTX 2.5: %d reference(s) are in the prompt text only "
                "— this family has no reference grammar yet, so nothing is "
                "encoded from them.", cited)
        if prev_audio is not None or next_audio is not None:
            logging.info(
                "[MiniMax] LTX 2.5: a sound seam reached this segment and is "
                "not conditioned on — the soundtrack is generated fresh with "
                "the picture.")

        # The soundtrack's own empty latent, shaped by the audio VAE's config
        # for this many frames at this rate, then packed with the picture. After
        # the guides, always: `append_keyframe` refuses a combined AV latent.
        audio_latent = _core("LTXVEmptyLatentAudio").execute(
            frames, float(rules.fps), 1, audio_vae)[0]
        latent = _core("LTXVConcatAVLatent").execute(latent, audio_latent)[0]

        # The rate, as conditioning. Last, so both conditionings carry it
        # whatever the guides did to them.
        positive, negative = _core("LTXVConditioning").execute(
            positive, negative, float(rules.fps))[:2]

        return io.NodeOutput(model, positive, latent, negative)


NODES = [MiniMaxLTX25Segment]
