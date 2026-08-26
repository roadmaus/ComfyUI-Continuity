"""How H3 renders: the family's half of the loop in `core/emit.py`.

The generic loop owns the clip branch, the seam wiring, the reel and the save
node; everything in this module is what H3's training decided and no other
family shares — two routed checkpoints, `KSampler` at cfg 1.0 behind a zeroed
negative, the sigma-shift patch, the turbo lead-in's split schedule, and the
refine and face passes that re-emit the segment node at another canvas.

The segment node is the boundary: `MiniMaxH3TimelineSegment` takes
`segment_data` plus loader links and returns `(model, positive, latent, lead
model)`, and that tuple is the whole of what the loop knows about a family.

Node ids are written as strings rather than imported, because they are ComfyUI
registry keys and not Python names — `MiniMaxH3TimelineSegment` is still called
that for both callers, since renaming it would only churn the tests for a label
nothing outside an expanded graph ever sees.
"""

import json
from dataclasses import dataclass

import comfy.sample

from ... import (accel, canvas, compile as compiler, models as core,
                 sampling as sampling_mod, settings)
from .. import base
from . import declare, models as slots

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

SEGMENT_NODE = declare.SEGMENT_NODE
REFINE_NODE = "MiniMaxH3RefinePass"
FACE_NODE = "MiniMaxH3FacePass"


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
    return core.graph_preview(graph, model, weights, declare.RULES.fps)


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


class H3(base.Family):
    """MiniMax H3, behind the family contract. See the module docstring."""

    id = "h3"
    label = "MiniMax H3"
    produces = frozenset({"video", "still"})
    output_stem = declare.OUTPUT_STEM
    rules = declare.RULES
    compile_error = compiler.CompileError

    def weights_from_blob(self, data):
        return slots.weights_from_blob(data)

    def resolve_sampling(self, data, widgets):
        return sampling_mod.resolve(data, widgets)

    def run_context(self, data):
        return LeadIn.of(data)

    def preflight(self, sampling, acceleration):
        # An accelerator whose pack is not installed should say so before
        # anything is queued rather than after the first segment has sampled.
        accel.plan(acceleration, sampling.steps)

    def compile(self, payload, image_size):
        return compiler.compile_segment(payload, image_size)

    def routes(self, compiled, labels):
        return routed(compiled, labels)

    def check(self, weights, where, audio=True, face=False):
        core.check(weights, slots.needs(where, audio=audio, face=face), where)

    def emit_loaders(self, graph, weights, routes):
        return core.Links(graph, weights, routes)

    def _segment_inputs(self, links, payload, compiled, weights, seams, splits, run):
        """The segment node's inputs, shared by the pass and its refine.

        Built once per hook rather than once per payload, but deterministically
        and from the same seam links — so the refine's copy is byte-identical to
        the pass's, as it was when it copied the dict.
        """
        inputs = {
            "clip": links.clip,
            # sort_keys so an unchanged payload serialises identically every
            # time — this string is the segment node's cache key.
            "segment_data": json.dumps(payload, sort_keys=True),
        }
        if splits:
            # Only when it is in play: an input the graph does not write is an
            # input the segment node's cache key does not carry, so a render
            # without a lead-in keeps the key it had before this existed.
            inputs["hold_lora"] = run.lora
        # The VAEs are wired into the encoder only when this segment actually
        # encodes with them — a keyframe or a sound seam. A text-only segment
        # touches neither until decode, and a decode node runs after sampling
        # where the DiT no longer needs the room. Wiring them here regardless
        # would load both before the first step and, on tight VRAM, push part of
        # the model into per-step recompute for no encode that uses them.
        if compiled.encodes_video():
            inputs["vae"] = links.vae
            # The checkpoint's name travels beside the socket, for the reference
            # cache to key its latents to — a live VAE object cannot be
            # identified across a restart, and a name can. Written only where
            # the VAE itself is, so a segment that encodes nothing keeps the
            # inputs, and the cache key, it had before this existed.
            inputs["vae_name"] = weights.vae or ""
        if compiled.encodes_audio():
            inputs["audio_vae"] = links.audio_vae
            inputs["audio_vae_name"] = weights.audio_vae or ""
        # The segment node's MODEL input names are its schema and are frozen —
        # `model_<slot>` happens to spell them, but it is the slot table that
        # decides which loaders exist to wire.
        for name in slots.ROUTED_SLOTS:
            if links.get(name) is not None:
                inputs[f"model_{name}"] = links.get(name)
        inputs.update(seams)
        return inputs

    def emit_segment(self, graph, links, payload, compiled, weights, sampling,
                     seams, run):
        # Whether this generation's schedule is split — decided here as well as
        # in the sampler hook, from the same inputs, so the two cannot disagree
        # about whether the segment holds the LoRA off a model nothing samples.
        splits = run.within(sampling, compiled, payload)
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
        return graph.node(SEGMENT_NODE,
                          **self._segment_inputs(links, payload, compiled,
                                                 weights, seams, splits, run))

    def emit_sampler(self, graph, segment, payload, compiled, sampling,
                     acceleration, weights, seed, run):
        splits = run.within(sampling, compiled, payload)

        # The distilled H3 checkpoints run at cfg 1.0, where the negative is
        # skipped outright, so there is nothing here worth a socket on the node.
        against = graph.node("ConditioningZeroOut", conditioning=segment.out(1)).out(0)

        # Patched after the segment node, which is where the LoRAs go on. Off,
        # every one of these adds nothing and this is the segment's model
        # unchanged.
        model = patched(graph, segment.out(0), sampling, acceleration, weights)

        # What every sampler below this line is handed, whether the schedule is
        # run in one sitting or two. The seed is not in here because the two
        # sittings the lead-in makes spell it differently — `noise_seed` — and a
        # dict that had to be unpacked and then corrected would be worse than
        # naming it twice.
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
                add_noise="enable", noise_seed=seed,
                start_at_step=0, end_at_step=run.steps,
                return_with_leftover_noise="enable", **common)
            sampled = graph.node(
                "KSamplerAdvanced",
                model=model, latent_image=opening.out(0),
                # The noise is already in the latent. A second `enable` here
                # would add a whole schedule's worth of it on top and throw the
                # opening steps away.
                add_noise="disable", noise_seed=seed,
                start_at_step=run.steps, end_at_step=sampling.steps,
                return_with_leftover_noise="disable", **common)
        else:
            sampled = graph.node(
                "KSampler", model=model, latent_image=segment.out(2),
                seed=seed, denoise=1.0, **common)
        return sampled.out(0)

    def emit_refine(self, graph, links, segment, payload, compiled, weights,
                    seams, latent, sampling, acceleration, seed, run):
        # `segment` is the first pass's node and is deliberately unused: this
        # family's second pass re-encodes the request at the target canvas, so
        # its conditioning is a segment node of its own — see below.
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
        splits = run.within(sampling, compiled, payload)
        spec = {"width": compiled.refine.width, "height": compiled.refine.height,
                "ratio": compiled.ratio, "label": compiled.ratio_label,
                "from_image": compiled.ratio_from_image,
                "clamped": compiled.ratio_clamped}
        refine_inputs = self._segment_inputs(links, payload, compiled, weights,
                                             seams, splits, run)
        refine_inputs["segment_data"] = json.dumps(
            {**payload, "canvas": spec}, sort_keys=True)
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
        return graph.node(
            REFINE_NODE,
            model=refine_model, positive=second.out(1), negative=refine_against,
            latent=latent,
            width=compiled.refine.width, height=compiled.refine.height,
            seed=seed, steps=sampling.steps, cfg=sampling.cfg,
            sampler_name=sampling.sampler_name, scheduler=sampling.scheduler,
            denoise=compiled.refine.denoise,
        ).out(0)

    def face_payload(self, payload, face):
        return face_payload(payload, face)

    def emit_face(self, graph, links, payload, compiled, face, written, weights,
                  sampling, acceleration, seed):
        # Its conditioning is a second segment node, compiled at the crop
        # canvas so the references are encoded at the size they are seen at.
        # No seam links on it: `prev_image` and the rest anchor the full
        # canvas, and there is no full canvas in a crop.
        face_inputs = {"clip": links.clip,
                       "segment_data": json.dumps(payload, sort_keys=True)}
        if compiled.encodes_video():
            face_inputs["vae"] = links.vae
        if compiled.encodes_audio():
            face_inputs["audio_vae"] = links.audio_vae
        for name in slots.ROUTED_SLOTS:
            if links.get(name) is not None:
                face_inputs[f"model_{name}"] = links.get(name)
        crop = graph.node(SEGMENT_NODE, **face_inputs)

        # Patched exactly as the passes are — the LoRAs come with the
        # segment node, cfg 1.0 skips the negative, the accelerators and the
        # preview decoder sit in the same places — because it is the same
        # model answering a smaller question.
        crop_model = patched(graph, crop.out(0), sampling, acceleration, weights)
        return graph.node(
            FACE_NODE, model=crop_model, positive=crop.out(1),
            negative=graph.node("ConditioningZeroOut",
                                conditioning=crop.out(1)).out(0),
            vae=links.vae, audio_vae=links.audio_vae,
            source=written.out(1), reel=written.out(0),
            detector=weights.sam3 or "",
            width=face.width, height=face.height,
            seed=seed, steps=sampling.steps, cfg=sampling.cfg,
            sampler_name=sampling.sampler_name, scheduler=sampling.scheduler,
            denoise=face.denoise)


FAMILY = H3()
