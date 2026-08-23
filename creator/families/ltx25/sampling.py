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

from dataclasses import dataclass

from ... import accel


@dataclass(frozen=True)
class Sampling:
    """The row, however the piece came by it.

    The same role H3's `sampling.Sampling` plays and deliberately not the same
    fields: `sampler_name` is the only name the two share, because the two
    families' rows describe different nodes. `steps` is here under H3's name for
    the one reason a shared name is ever worth it — the render loop passes this
    object through unread, but `core/emit.py`'s progress and the accelerator
    planner both count steps, and a family that spelled it otherwise would be
    inventing a difference.
    """

    seed: int = 0
    steps: int = 8
    video_cfg: float = 1.0
    audio_cfg: float = 1.0
    sampler_name: str = "euler"
    max_shift: float = 2.05
    base_shift: float = 0.95
    stretch: bool = True
    terminal: float = 0.1


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


# What each field has to be. The same refusal-by-name H3's row makes: a
# hand-edited `"steps": "eight"` should say so before a loader is built.
_WHOLE = ("steps",)
_NUMBER = ("video_cfg", "audio_cfg", "max_shift", "base_shift", "terminal")
_FLAG = ("stretch",)


class SamplingError(ValueError):
    """A `sampling` block this family will not run."""


def _checked(name, value):
    if name in _WHOLE:
        # `True` is an int in Python and would sail through as one step.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
            raise SamplingError(f"sampling.{name} must be a whole number")
        if int(value) < 1:
            raise SamplingError(f"sampling.{name} must be at least 1")
        return int(value)
    if name in _NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SamplingError(f"sampling.{name} must be a number")
        return float(value)
    if name in _FLAG:
        if not isinstance(value, bool):
            raise SamplingError(f"sampling.{name} must be true or false")
        return value
    # `sampler_name`. Not checked against core's list here: that is what
    # `KSamplerSelect` will refuse by name, and a copy of it in this module
    # would go stale the first time core added one.
    if not isinstance(value, str) or not value:
        raise SamplingError(f"sampling.{name} must be a name")
    return value


def resolve(data, widgets):
    """-> `(Sampling, accel.Settings)` for this queue.

    The blob is the whole of the row. There is no widget fallback the way H3 has
    one, and there could not be: the node's thirteen widget slots are H3's row,
    frozen in that order forever, and none of them is `video_cfg`. A field the
    blob does not carry falls back to `DEFAULTS` — the distilled checkpoint's
    numbers — which is what an LTX piece written by any frontend older than the
    field should run at.

    The seed is the exception and still comes off the widget, for the reason it
    does on H3: `control_after_generate` is the frontend's own linked control
    and there is nothing for a JSON field to be.

    The accelerators come back off. Every one of them is H3's — the block
    caches are keyed to its DiT, Spectrum ships a pack named for it, and the two
    attention swaps and the FFN chunker are KJNodes patches written against its
    blocks. None of that has been tried against LTX, and quietly applying a
    model patch nobody has verified is how a render comes out subtly wrong with
    nothing in the log. Off is the honest answer until someone measures.
    """
    raw = data.get("sampling")
    if raw is None:
        stored = {}
    elif not isinstance(raw, dict):
        raise SamplingError("sampling must be an object")
    else:
        stored = {name: _checked(name, value) for name, value in raw.items()
                  if name in DEFAULTS and value is not None}

    def pick(name):
        return stored[name] if name in stored else DEFAULTS[name]

    return (
        Sampling(
            seed=int(widgets.get("seed", 0)),
            steps=pick("steps"),
            video_cfg=pick("video_cfg"), audio_cfg=pick("audio_cfg"),
            sampler_name=pick("sampler_name"),
            max_shift=pick("max_shift"), base_shift=pick("base_shift"),
            stretch=pick("stretch"), terminal=pick("terminal"),
        ),
        accel.Settings(),
    )
