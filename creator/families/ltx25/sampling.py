"""LTX 2.5's sampler row — the defaults, and the nodes each one belongs to.

The row is a different shape from H3's, which is the reason `families/manifest.py`
describes controls instead of shipping a bag of values. H3 emits a `KSampler`
and its row is that node's inputs. LTX emits three nodes:

    LTXVScheduler(steps, max_shift, base_shift, stretch, terminal, latent) -> SIGMAS
    KSamplerSelect(sampler_name)                                           -> SAMPLER
    LTXVDualCFGGuider(model, positive, negative, video_cfg, audio_cfg)     -> GUIDER
                                                    -> SamplerCustomAdvanced

so there is no `scheduler` combo at all (the scheduler *is* a node, and its
shift pair rides the token count of the latent handed to it), and one `cfg`
becomes two — the packed AV latent takes a separate scale per modality.

**The defaults are the distilled checkpoint's**, because the distilled
transformer is what the family ships: Lightricks' card pins it to a fixed
8-step schedule at CFG 1, and their own reference pipeline runs
`guidance_scale=1.0, audio_guidance_scale=1.0`. The full `dev` transformer
wants the node defaults instead — 20 steps at 3.0/7.0 — which is a file the
user picks in the same slot, so it is a row they change rather than a mode the
pack switches. The bounds below are wide enough for both.

`max_shift`, `base_shift`, `stretch` and `terminal` are `LTXVScheduler`'s own
numbers, unchanged: they describe the sigma curve the architecture was trained
against, not a taste.
"""

DEFAULTS = {
    # The distilled schedule. `LTXVScheduler`'s own default is 20, which is the
    # dev transformer's.
    "steps": 8,
    # One scale per modality of the packed AV latent. Both 1.0 is the distilled
    # checkpoint's; the dev transformer's are the guider's own 3.0 / 7.0.
    "video_cfg": 1.0,
    "audio_cfg": 1.0,
    # The sigma curve. `ModelSamplingLTXV` takes the same shift pair and must be
    # given the same numbers — the model patch and the schedule are two readings
    # of one curve, and letting them disagree is a silent quality bug.
    "max_shift": 2.05,
    "base_shift": 0.95,
    "stretch": True,
    "terminal": 0.1,
    # `KSamplerSelect`'s list, which is core's to declare — the manifest's combo
    # carries no options for the same reason H3's does not.
    "sampler_name": "euler",
}
