"""How LTX 2.5 renders: the family's half of the loop in `core/emit.py`.

The generic loop owns the clip branch, the seam wiring, the reel and the save
node. What is here is what Lightricks' training decided and H3 does not share:
one transformer and no routing, a sigma curve that rides the latent's own token
count, two CFG scales for the two modalities of a packed AV latent, and a second
stage that is a *latent upscaler* rather than a re-sample at a bigger canvas.

**The sampler is core's LTX nodes, wired, not reimplemented.** H3 emits one
`KSampler`; this emits the five that make a custom sampling pass —

    LTXVScheduler(steps, max_shift, base_shift, stretch, terminal, latent) -> SIGMAS
    KSamplerSelect(sampler_name)                                           -> SAMPLER
    ModelSamplingLTXV(model, max_shift, base_shift, latent)                -> MODEL
    LTXVDualCFGGuider(model, positive, negative, video_cfg, audio_cfg)     -> GUIDER
    RandomNoise(seed)                                                      -> NOISE
                                                     -> SamplerCustomAdvanced

— with KJNodes' preview override wrapped outside the lot where it is installed,
so a render of this family is watchable at all (`models.graph_preview`).

The scheduler and the model patch are both handed the latent, because the
shift they compute is a function of its token count. They must be given the same
shift pair: they are two readings of one curve, and letting them disagree is a
quality bug with nothing in the log.

**Guides are cropped exactly once.** `LTXVAddGuide` appends each guide's
condition latent past the end of the sequence, so a sampled latent is longer
than the video it describes and the extra frames must come off before anything
decodes it. `LTXVCropGuides` is what takes them off — and it cannot run on the
packed AV latent, because removing frames from a `NestedTensor` would take them
off the soundtrack too. So the pass is unpacked, cropped and packed again, and
the whole of that happens either at the end of `emit_sampler` (one-stage) or at
the *start* of `emit_refine` (two-stage), never twice and never after an upscale
has spent itself on frames nobody will see.

**Taste guidance is two more model patches, and only when asked for.** STG and
modality guidance each hang a post-CFG hook on the model that runs a second
forward pass per step — so they are off by default, they are emitted only when
the row's values would do something, and they wear their cost in the copy of the
pills that write them. See `_guided`.

**`refine` here is Lightricks' own second stage.** Not H3's refine, which
re-encodes the conditioning at a larger canvas and re-samples: LTX ships a
trained x2 latent upscaler, so the pipeline is sample at the native edge, run
the upscaler on the video latent, and sample again over a tail of the schedule.
That is what the model card describes and it is what the pill runs.
"""

from ... import canvas
from ... import models as core
from .. import base
from . import models, sampling as sampling_mod, segment as segment_node
from . import declare


class LTX25(base.Family):
    """LTX 2.5, behind the family contract. See the module docstring."""

    id = "ltx25"
    label = "LTX 2.5"
    produces = frozenset({"video"})
    #: The canvas and duration arithmetic this family renders under. Read by
    #: `core/emit.py` for the rate the finished file is written at, which used
    #: to be H3's `canvas.FPS` because there was one family to have one.
    rules = declare.RULES

    def weights_from_blob(self, data):
        return core.Weights.from_blob(data, models.SLOTS)

    def resolve_sampling(self, data, widgets):
        return sampling_mod.resolve(data, widgets)

    def preflight(self, sampling, acceleration):
        # Nothing to refuse. `sampling.resolve` hands this family an empty
        # accelerator set by construction — every accelerator this pack knows
        # about is an H3 patch — so there is no pack to check for and no plan to
        # make. The hook stays overridden rather than inherited, because the
        # inherited one raises.
        return None

    def compile(self, payload, image_size):
        from ... import compile as compiler

        one = compiler.compile_segment(payload, image_size, family=self.id)
        if one.refine is not None:
            # The second stage is a *trained x2 upscaler*, so its target is
            # exactly twice the canvas the first stage sampled — not whatever
            # the resolution slider happens to say. `compile_request` resolves
            # the slider's own answer because that is what H3's re-sample
            # refines up to; here the model decides the factor and the slider
            # decides only whether there is a second stage at all.
            one.refine = compiler.Refine(one.width * 2, one.height * 2,
                                         one.refine.denoise)
        return one

    def routes(self, compiled, labels):
        # One transformer. Nothing routes, so nothing is routed to, and the
        # weights check below reads its own required list rather than this.
        return {}

    def check(self, weights, where, audio=True, face=False):
        # The slots a render can never go without: every loader that is not
        # optional, less the audio VAE on a soundless render — which this family
        # has no such thing as, but the rule is the table's rather than this
        # family's. The two opt-in slots are deliberately absent: they are
        # passes, not components, and `models.Links` refuses each in its own
        # words at the moment something reaches for it.
        core.check(weights, [name for name, slot in models.SLOTS.items()
                             if slot.loader and not slot.optional
                             and (audio or not slot.audio)])

    def emit_loaders(self, graph, weights, routes):
        return core.Links(graph, weights, routes)

    def emit_segment(self, graph, links, payload, compiled, weights, sampling,
                     seams, run):
        import json

        return graph.node(
            segment_node.SEGMENT_NODE,
            model=links.dit, clip=links.clip,
            vae=links.vae, audio_vae=links.audio_vae,
            # Only where this card's length is the model's to pick. The input is
            # optional so a graph without it is byte-identical to one built
            # before the head existed, and the loader is built on the first ask
            # — a strip with one auto card loads the file once, and a strip with
            # none never loads it at all.
            **({"duration_head": links.duration_head}
               if compiled.auto_duration else {}),
            # sort_keys so an unchanged payload serialises identically every
            # time — this string is the segment node's cache key.
            segment_data=json.dumps(payload, sort_keys=True),
            **seams)

    def _guided(self, graph, model, sampling):
        """The taste guidance, where the row asked for it. -> the model link.

        Two model patches, both of which hang a post-CFG hook on the model and
        both of which **cost one extra forward pass per step** — core's own
        wording, and worth repeating here because it is the whole reason these
        are not switched on by default. On the distilled row the base pass is a
        single forward per step (`video_cfg == audio_cfg == 1.0`, where the dual
        guider falls back to single CFG and the uncond pass is skipped), so
        either one of these roughly doubles the time a stage takes and both of
        them roughly triple it.

        They stack: `set_model_sampler_post_cfg_function` appends, and each hook
        reads `args["denoised"]` — whatever the hook before it returned — so the
        order here is the order they compose in. STG first and modality second,
        which is the order Lightricks' own copy names them in ("stacks with the
        dual-CFG guider and STG").

        Emitted only when the row says they would do something, so a piece that
        never touched these pills builds the graph it always did. That is not
        only a golden's convenience: each node clones the model, and a clone
        carrying a hook that returns its input unchanged is a pass nobody can
        see and nobody asked for.
        """
        if sampling.stg:
            model = graph.node(
                "LTXVSpatioTemporalGuidance", model=model,
                scale=sampling.stg_scale, blocks=sampling.stg_blocks,
                # The sigma window is core's full range. Restricting STG to part
                # of the schedule is a real control and not one this pack has
                # measured on these weights, so it is left where Lightricks put
                # it rather than guessed at behind a pill.
                start_percent=0.0, end_percent=1.0).out(0)
        if sampling.modality:
            model = graph.node(
                "LTXVModalityGuidance", model=model,
                modality_scale=sampling.modality_scale,
                start_percent=0.0, end_percent=1.0).out(0)
        return model

    def _sampled(self, graph, model, positive, negative, latent, sampling, seed,
                 sigmas, weights):
        """One custom-sampling pass over `latent`. -> the sampled latent link.

        The four nodes that differ between the two stages are the caller's
        (`sigmas` above, and the model it hands in); everything here is the same
        both times, which is the whole reason it is written once.

        The taste guidance goes on inside the preview and outside the sampling
        patch: it is a post-CFG hook and belongs with the sampling, where the
        preview override wraps OUTER_SAMPLE and wants to be the outermost thing
        on the model — the same place H3's `render.patched` puts it. This family picks no tiny
        decoder, and does not need to: KJNodes recognises an LTX latent format
        and previews it through its own LTX previewer, guide frames cropped off.
        Without the pack installed this adds nothing and there is no preview,
        which is the one case worth a line in the log rather than an error.
        """
        model = core.graph_preview(graph, self._guided(graph, model, sampling),
                                   weights)
        guider = graph.node(
            "LTXVDualCFGGuider", model=model,
            positive=positive, negative=negative,
            video_cfg=sampling.video_cfg, audio_cfg=sampling.audio_cfg).out(0)
        return graph.node(
            "SamplerCustomAdvanced",
            noise=graph.node("RandomNoise", noise_seed=seed).out(0),
            guider=guider,
            sampler=graph.node("KSamplerSelect",
                               sampler_name=sampling.sampler_name).out(0),
            sigmas=sigmas,
            latent_image=latent).out(0)

    def _schedule(self, graph, latent, sampling):
        """The sigma curve for a latent, and the model patch that matches it.

        -> `(sigmas link, a function taking a model link to the patched one)`.
        Both read the same token count off the same latent and are given the
        same shift pair, which is the invariant this pairing exists to keep.
        """
        sigmas = graph.node(
            "LTXVScheduler", steps=sampling.steps,
            max_shift=sampling.max_shift, base_shift=sampling.base_shift,
            stretch=sampling.stretch, terminal=sampling.terminal,
            latent=latent).out(0)

        def patch(model):
            return graph.node(
                "ModelSamplingLTXV", model=model,
                max_shift=sampling.max_shift, base_shift=sampling.base_shift,
                latent=latent).out(0)

        return sigmas, patch

    def _cropped(self, graph, positive, negative, latent):
        """A sampled pass with its guide frames taken off. -> the latent link.

        Unpacked and packed again around `LTXVCropGuides`, because the crop is a
        slice in time and the soundtrack shares that axis: run on the packed
        latent it would shorten the sound by however many guides the picture
        had. The conditioning links are the segment node's own, which still
        carry the `keyframe_idxs` saying how many there were.
        """
        split = graph.node("LTXVSeparateAVLatent", av_latent=latent)
        crop = graph.node("LTXVCropGuides", positive=positive,
                          negative=negative, latent=split.out(0))
        return graph.node("LTXVConcatAVLatent",
                          video_latent=crop.out(2),
                          audio_latent=split.out(1)).out(0), crop

    def emit_sampler(self, graph, segment, payload, compiled, sampling,
                     acceleration, weights, seed, run):
        latent = segment.out(2)
        sigmas, patch = self._schedule(graph, latent, sampling)
        sampled = self._sampled(graph, patch(segment.out(0)),
                                segment.out(1), segment.out(3), latent,
                                sampling, seed, sigmas, weights)
        if compiled.refine is not None:
            # Left packed and uncropped on purpose: the second stage crops
            # before it upscales, so cropping here would be the same slice done
            # twice — and the loop hands this straight to `emit_refine`.
            return sampled
        return self._cropped(graph, segment.out(1), segment.out(3), sampled)[0]

    def emit_refine(self, graph, links, segment, payload, compiled, weights,
                    seams, latent, sampling, acceleration, seed, run):
        # The guides come off first. They did their work in stage one, they are
        # not part of the picture, and upscaling them would spend the x2 pass on
        # frames that are about to be thrown away.
        stage_one, crop = self._cropped(graph, segment.out(1), segment.out(3),
                                        latent)

        split = graph.node("LTXVSeparateAVLatent", av_latent=stage_one)
        upscaled = graph.node(
            "LTXVLatentUpsampler", samples=split.out(0),
            upscale_model=links.upscaler, vae=links.vae).out(0)
        # The soundtrack rides across unchanged and is packed back onto the
        # bigger picture. `LTXVConcatAVLatent` fits its length to the video's,
        # which after a spatial-only upscale is the length it already was.
        packed = graph.node("LTXVConcatAVLatent",
                            video_latent=upscaled,
                            audio_latent=split.out(1)).out(0)

        # A new canvas is a new token count, so the curve is rebuilt rather
        # than reused — that is the whole reason both nodes take the latent.
        sigmas, patch = self._schedule(graph, packed, sampling)
        # ...and only its tail is run. `SamplerCustomAdvanced` has no `denoise`
        # of its own; the schedule is where a partial pass is expressed, which
        # is what `SplitSigmasDenoise` is for.
        tail = graph.node("SplitSigmasDenoise", sigmas=sigmas,
                          denoise=compiled.refine.denoise).out(1)
        # The cropped conditioning, not the segment node's: stage two samples a
        # latent with no guide frames in it, and conditioning that still claimed
        # some would have the model looking for picture that is not there.
        return self._sampled(graph, patch(segment.out(0)),
                             crop.out(0), crop.out(1), packed,
                             sampling, seed, tail, weights)


FAMILY = LTX25()
