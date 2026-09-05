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

from ... import (accel, canvas, compile as compiler, guide as guides, media,
                 models as core, raylight, sampling as sampling_mod, settings)
from .. import base
from . import declare, models as slots, truncate

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
SEAM_RESTORE_NODE = "MiniMaxH3SeamRestore"


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


def truncated(graph, model):
    """`model` behind the drift guard, when the settings page asks for it.

    Off by default, and off means nothing is emitted. On, the pass's latent is
    the average of the model's last few guesses at it rather than its last
    step (`truncate.py`); the page's "every guess" stop is the node's 0. Only
    the pass and its lead-in: the refine, the face crop and the restore resume
    partway down the schedule and redraw texture on purpose, which is the part
    this averages away.
    """
    guard = settings.drift_guard()
    if guard <= 0:
        return model
    return graph.node(truncate.TRUNCATE_NODE, model=model,
                      guesses=0 if guard >= settings.EVERY_GUESS else guard).out(0)


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


def restore_payload(payload, compiled):
    """The payload the seam restore's *conditioning* is built from.

    The source shot's request with the same two things taken out that
    `face_payload` takes out, for the same reasons — its own second passes, so
    the payload compiled here asks for none, and its keyframes, which are
    statements about a whole shot's composition and the run being restored is
    a few frames off its end. References survive: they are what the restore
    is pulling the picture back toward. The canvas is the source's own, since
    the frames are re-drawn at the size they were written.
    """
    request = {key: value for key, value in payload["request"].items() if key != "face"}
    assets = [asset for asset in (request.get("assets") or [])
              if isinstance(asset, dict) and asset.get("role") == "reference"]
    if assets or "assets" in request:
        request["assets"] = assets
    return {"request": request,
            "canvas": {"width": compiled.width, "height": compiled.height,
                       "ratio": compiled.ratio, "label": compiled.ratio_label,
                       "from_image": compiled.ratio_from_image,
                       "clamped": compiled.ratio_clamped}}


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

    def preflight(self, sampling, acceleration, weights):
        if raylight.enabled(weights):
            # A different set of packs entirely: the accelerator nodes are not
            # this render's dependencies, and asking for them here would refuse
            # a Ray render for the absence of a KJNodes patch it was never going
            # to emit. What it does need is the fork, and what it cannot carry
            # is most of the accelerator row — both said now, before a payload
            # is compiled, rather than at the sampler.
            raylight.preflight(acceleration)
            return
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
        if not raylight.enabled(weights):
            return core.Links(graph, weights, routes)
        # The multi-GPU backend. The checkpoint is loaded inside Ray's workers
        # from a filename, so the loader that would have opened it here is
        # skipped — everything else on the table is unchanged, because
        # everything else still runs on this side of the wire: the text encoder
        # encodes the prompt here, and both VAEs decode here.
        #
        # Refused before a single node is built, which is why this is the first
        # thing the hook does: a device pin or a two-checkpoint route is not
        # something Ray can be asked to do differently, it is a render that has
        # to be set up another way.
        raylight.refuse_weights(weights, routes)
        links = core.Links(graph, weights, routes, skip=slots.ROUTED_SLOTS)
        # Carried on the links object because that is the one thing in a render
        # that is made once and handed to every hook — see `raylight.Actors` for
        # why the workers have to be built once and asked for late.
        links.actors = raylight.Actors(graph, weights, raylight.Spread(weights.gpus))
        return links

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
        if raylight.enabled(weights):
            # No MODEL sockets at all on a Ray render: the transformer is in the
            # workers, and this node's two model outputs go unwired. Said in the
            # payload rather than inferred from the absent sockets, because a
            # segment that is *missing* its checkpoint is a graph error worth
            # keeping — see the node's own `sampler_backend` input.
            #
            # Written only in this mode, so a single-GPU render carries the
            # inputs, and therefore the cache key, it had before this existed.
            inputs["sampler_backend"] = raylight.RAYLIGHT
        else:
            # The segment node's MODEL input names are its schema and are frozen
            # — `model_<slot>` happens to spell them, but it is the slot table
            # that decides which loaders exist to wire.
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

    def emit_control(self, graph, links, segment, compiled, weights, guide):
        """The Fun ControlNet-Union branch, put on this segment's conditioning.

        Three nodes and no arithmetic, which is the shape this hook is supposed
        to have: the drawing and its trim came in on `compiled.guide` as an
        ordinary attached asset, the switch's strength came in on `guide`,
        `Links` opened the branch, and what is left for the family to say is
        which core node reads them and what its inputs are called.

        **On the conditioning, not on the model.** Core's `MiniMaxH3ControlNet`
        encodes the hint to a latent and hangs it off each conditioning entry,
        and `MiniMaxH3Model._forward` picks it up as `control` and advances a
        control block at every tenth layer. So the returned segment replaces
        out 1 and leaves the model alone — which matters, because the turbo
        lead-in samples out 3 (the model with the distillation held off it) and
        both sittings have to be aimed at the same drawing.

        **The VAE is wired in whether or not the segment encodes anything.** A
        text-only shot leaves `vae` off the segment node on purpose — see
        `_segment_inputs` — and the apply node needs it regardless, because the
        hint is encoded to a video latent before it ever reaches a block. That
        is not a contradiction: a guided text-only shot is one that encodes a
        picture after all, and the picture is the drawing.
        """
        if raylight.enabled(weights):
            # Before the branch is loaded rather than after: six gigabytes of
            # ControlNet for a render that is about to be refused would be six
            # gigabytes read off disk for nothing.
            raylight.refuse_guide()
        if getattr(compiled.guide, "op", "") == "matte":
            return self._emit_inpaint(graph, links, segment, compiled, guide)
        frames = guides.guide_frames(graph, compiled.guide, compiled,
                                     self.rules.fps)
        applied = graph.node(
            declare.CONTROL_NODE,
            positive=segment.out(1),
            # `links.control` is the lazy-optional path: this is the first ask,
            # so the loader is built here, and a guide thrown with no file
            # picked raises the slot's own sentence rather than emitting a
            # loader with an empty filename.
            control_net=links.control,
            vae=links.vae,
            strength=float(guide.strength),
            start_percent=float(guide.start),
            end_percent=float(guide.end),
            control_video=frames,
        )
        return guides.Controlled(segment, positive=applied.out(0))

    def _emit_inpaint(self, graph, links, segment, compiled, guide):
        """The same apply node's other mode: mask and source instead of drawing.

        The Fun union's inpaint channels — the bench's matte is the mask (white
        regenerates, `set_inpaint` re-hardens it at 0.5), and the clip being
        edited rides behind it as `source_video`, so everything outside the
        white is conditioned to *stay that clip* at latent level rather than
        asked to in prose. `control_video` stays unwired on purpose: the node
        holds an absent input's channels at zero, which is the checkpoint's
        trained fallback for masking without a drawing.

        The source is the shot's own edit clip — the one a subject replaces
        into, or the one chipped `edit`. Read through the same frames node as
        the matte, at the same canvas, rate and length, so the two line up
        frame for frame as long as the matte was traced over the same cut the
        clip is trimmed to.
        """
        replaced = {h for s in compiled.cast for h in s.replaces}
        source = next(
            (a for a in compiled.ref_videos
             if a.handle in replaced or a.takes == "edit"), None)
        if source is None:
            raise guides.GuideError(
                "a matte guide is an inpaint mask over a source clip, and this "
                "shot has none: attach the clip the matte was traced from as a "
                "reference and chip it 'edit' (casting somebody to take a place "
                "in it does the same)."
            )
        matte = guides.guide_frames(graph, compiled.guide, compiled,
                                    self.rules.fps)
        mask = graph.node("ImageToMask", image=matte, channel="red").out(0)
        frames = guides.guide_frames(graph, source, compiled, self.rules.fps)
        applied = graph.node(
            declare.CONTROL_NODE,
            positive=segment.out(1),
            control_net=links.control,
            vae=links.vae,
            strength=float(guide.strength),
            start_percent=float(guide.start),
            end_percent=float(guide.end),
            mask=mask,
            source_video=frames,
        )
        return guides.Controlled(segment, positive=applied.out(0))

    def emit_sampler(self, graph, links, segment, payload, compiled, sampling,
                     acceleration, weights, seed, run):
        splits = run.within(sampling, compiled, payload)

        if raylight.enabled(weights):
            return self._emit_ray_sampler(graph, links, segment, payload,
                                          compiled, sampling, acceleration,
                                          weights, seed, splits)

        # The distilled H3 checkpoints run at cfg 1.0, where the negative is
        # skipped outright, so there is nothing here worth a socket on the node.
        against = graph.node("ConditioningZeroOut", conditioning=segment.out(1)).out(0)

        # Patched after the segment node, which is where the LoRAs go on. Off,
        # every one of these adds nothing and this is the segment's model
        # unchanged.
        model = truncated(graph, patched(graph, segment.out(0), sampling,
                                         acceleration, weights))

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
                model=truncated(graph, patched(graph, segment.out(3), sampling,
                                                 accel.uncached(acceleration), weights)),
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

    def _emit_ray_sampler(self, graph, links, segment, payload, compiled,
                          sampling, acceleration, weights, seed, splits):
        """The same generation, sampled across the cards by Raylight's workers.

        The custom-sampler arrangement rather than `XFuserKSamplerAdvanced`,
        which is otherwise `KSamplerAdvanced` with actors where the model goes:

            RayCFGGuider(actors, positive, zeroed negative, cfg)  -> RAY_GUIDER
            RayBasicScheduler(actors, scheduler, steps)           -> SIGMAS
            KSamplerSelect(sampler_name)                          -> SAMPLER
            XFuserSamplerCustomAdvanced(...)                      -> LATENT

        Three more nodes, and what they buy is the preview: the K3U bridge hands
        the sampler a context only in this form, and a distributed render is the
        one you least want to sit in front of as an empty box.

        `patched()` has no counterpart here and deliberately no equivalent: of
        the three things it does, the sigma shift is an actor patch the fork
        ships, the accelerators are refused above, and the preview comes in
        through the bridge below.
        """
        from .payload import CORE_ANCHORS_ANYWHERE

        # Everything this generation asks for that the workers cannot carry,
        # said before a node is built. The label is the card's number where the
        # loop stamped one — a strip's fourth shot should say so.
        progress = payload.get("progress") or {}
        label = f"Segment {progress['index']}" if progress.get("index") else None
        raylight.refuse_run(compiled, splits, label)
        raylight.refuse_seam(compiled, CORE_ANCHORS_ANYWHERE, label)

        actors = links.actors.of(compiled.checkpoint,
                                 self._ray_loras(payload, compiled),
                                 acceleration)
        if sampling.shifted():
            # Core's own node, run inside the workers — the fork wraps it rather
            # than reimplementing it, so this is the same schedule the
            # single-GPU path emits, said to a different object.
            actors = graph.node(
                raylight.SHIFT_NODE, ray_actors=actors,
                shift_video=sampling.shift_video,
                shift_audio=sampling.shift_audio).out(0)

        # The preview bridge. Export hands out a stand-in MODEL that carries the
        # actors as an attachment, KJNodes' override wraps it exactly as it
        # wraps a real one, and Import reads the wrapper back off it as a
        # context the sampler runs on the driver while the workers step. The
        # adapter refuses a model carrying patches it did not register, which is
        # the second reason `refuse_accel` is not a matter of taste.
        context = None
        if core.preview_available():
            exported = graph.node(raylight.K3U_EXPORT_NODE, ray_actors=actors).out(0)
            previewed = core.graph_preview(graph, exported, weights,
                                           declare.RULES.fps)
            imported = graph.node(raylight.K3U_IMPORT_NODE, model=previewed)
            context, actors = imported.out(0), imported.out(1)

        against = graph.node("ConditioningZeroOut", conditioning=segment.out(1)).out(0)
        guider = graph.node(
            raylight.GUIDER_NODE, ray_actors=actors,
            positive=segment.out(1), negative=against, cfg=sampling.cfg).out(0)
        # `denoise` is 1.0 for the same reason the single-GPU pass runs a whole
        # schedule: this is the first pass, and the refine that would re-noise
        # partway down one is refused above.
        sigmas = graph.node(
            raylight.SCHEDULER_NODE, ray_actors=actors,
            scheduler=sampling.scheduler, steps=sampling.steps, denoise=1.0).out(0)
        sampler = graph.node("KSamplerSelect",
                             sampler_name=sampling.sampler_name).out(0)
        return graph.node(
            raylight.SAMPLER_NODE,
            add_noise=True, noise_seed=seed,
            guider=guider, sampler=sampler, sigmas=sigmas,
            latent_image=segment.out(2),
            **({"k3u_adapter_context": context} if context is not None else {}),
        ).out(0)

    def _ray_loras(self, payload, compiled):
        """This generation's LoRA stack, as the workers take it.

        The stack is read the same way the segment node reads it — `active_loras`
        against the routed checkpoint — but it stops at the filenames: the
        adapters are opened and merged inside the workers by `RayLoraLoader`,
        through core's patcher rather than through `h3lora`. That is the one
        thing this backend silently does differently and it is silent nowhere
        else: the switch says so, and `h3lora`'s own docstring says what is lost.

        The modality dial is the exception, because it is not a strength anybody
        could read off the result: it slices adaLN rows, which is `h3lora`'s and
        has no counterpart in a merge. A file carrying one is refused rather
        than merged at full strength into the soundtrack it was damped off.
        """
        from ... import lora as lora_mod

        entries = compiler.active_loras(payload["request"].get("loras"),
                                        compiled.checkpoint, self.id)
        loras = []
        for entry in entries:
            if lora_mod.modality(entry):
                raise ValueError(
                    f"'{entry['name']}' has its audio dial turned down, which "
                    f"slices the adapter's modulation rows — a thing this pack's "
                    f"own LoRA stack does and a merge inside Raylight's workers "
                    f"cannot. Put the dial back to 1.0 (the file will reach the "
                    f"soundtrack again), or set the backend back to single-GPU."
                )
            loras.append((entry["name"], float(entry.get("strength", 1.0))))
        return loras

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


    restores_seams = True
    hands_latents = True

    def emit_seam_restore(self, graph, links, frames, payload, compiled, denoise,
                          weights, sampling, acceleration, seed):
        # A segment node of its own, compiled from the source shot at its own
        # canvas, so the references are encoded at the size the run is drawn
        # at. No seam links: the run *is* the seam, and it is being re-drawn in
        # place rather than continued from anything.
        source = restore_payload(payload, compiled)
        restore = compiler.compile_segment(source, image_size_lookup=media.image_size)
        inputs = {"clip": links.clip,
                  "segment_data": json.dumps(source, sort_keys=True)}
        if restore.encodes_video():
            inputs["vae"] = links.vae
            inputs["vae_name"] = weights.vae or ""
        if restore.encodes_audio():
            inputs["audio_vae"] = links.audio_vae
            inputs["audio_vae_name"] = weights.audio_vae or ""
        for name in slots.ROUTED_SLOTS:
            if links.get(name) is not None:
                inputs[f"model_{name}"] = links.get(name)
        segment = graph.node(SEGMENT_NODE, **inputs)

        # Patched as the passes are — same LoRAs off the segment node, cfg 1.0
        # behind a zeroed negative, the same accelerators — because it is the
        # same model re-drawing a few frames of its own picture. No lead-in:
        # like the refine, this resumes partway down the schedule.
        model = patched(graph, segment.out(0), sampling, acceleration, weights)
        restored = graph.node(
            SEAM_RESTORE_NODE, model=model, positive=segment.out(1),
            negative=graph.node("ConditioningZeroOut",
                                conditioning=segment.out(1)).out(0),
            vae=links.vae, frames=frames,
            seed=seed, steps=sampling.steps, cfg=sampling.cfg,
            sampler_name=sampling.sampler_name, scheduler=sampling.scheduler,
            denoise=float(denoise))
        return restored.out(0), restored.out(1)


FAMILY = H3()
