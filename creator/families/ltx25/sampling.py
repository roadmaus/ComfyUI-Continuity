"""LTX 2.5's sampler row — the defaults, and the nodes each one belongs to.

The row is a different shape from H3's, which is the reason `families/manifest.py`
describes controls instead of shipping a bag of values. H3 emits a `KSampler`
and its row is that node's inputs. LTX emits three nodes:

    ManualSigmas(sigmas) | LTXVScheduler(steps, ..., latent)               -> SIGMAS
    KSamplerSelect(sampler_name)                                           -> SAMPLER
    LTXVDualCFGGuider(model, positive, negative, video_cfg, audio_cfg)     -> GUIDER
                                                    -> SamplerCustomAdvanced

so there is no `scheduler` combo at all, and one `cfg` becomes two — the packed
AV latent takes a separate scale per modality.

**`schedule` is which of the two SIGMAS nodes the render emits, and it is the
field the rest of the row hangs off.** The two transformers in the `dit` slot
are sampled differently rather than merely at different settings:

- `distilled` feeds `declare.DISTILLED_SIGMAS` through `ManualSigmas` and emits
  no `ModelSamplingLTXV` at all. Neither number is ours and neither is a
  default — the curve is what the checkpoint was distilled against, so `steps`,
  `max_shift`, `base_shift`, `stretch` and `terminal` describe nothing on this
  route and are not read. This is what both of Lightricks' 2.5 workflows and
  ComfyUI's own LTX 2.5 templates do.
- `scheduler` is `LTXVScheduler` with the shift pair and the terminal, paired
  with the `ModelSamplingLTXV` patch that reads the same curve — the recipe LTX
  2.3 shipped, and what the full `dev` transformer wants, at ~20 steps and
  3.0/7.0 rather than 8 at 1/1.

Distilled is the default because the distilled transformer is what a piece
loads unless someone picks otherwise, and because the trained curve is the one
thing about this family that a wrong guess costs the whole render — see
`declare.DISTILLED_SIGMAS` for the two curves side by side. The bounds below
stay wide enough for both routes.

`max_shift`, `base_shift`, `stretch` and `terminal` are `LTXVScheduler`'s own
numbers, unchanged: they describe the sigma curve the architecture was trained
against, not a taste.

**The three guidance fields are a different kind of control** and are declared
in their own group for it. `stg_scale`, `stg_blocks` and `modality_scale` do not
describe the schedule: each switches on an *extra forward pass per step*, and
the pass they add is the same size as the one the render was already making. So
they are off by default at the values core calls off — 0 for STG, 1.0 for
modality guidance — and the pills that write them say what they cost rather than
leaving a user to find out from the step timer. See `render._guided`.
"""

from dataclasses import dataclass

from ... import accel
from .. import row as base_row
from . import declare

#: Which SIGMAS node the render emits. See the module docstring.
SCHEDULES = ("distilled", "scheduler")


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
    schedule: str = SCHEDULES[0]
    steps: int = 8
    video_cfg: float = 1.0
    audio_cfg: float = 1.0
    sampler_name: str = declare.DISTILLED_SAMPLER
    max_shift: float = 2.05
    base_shift: float = 0.95
    stretch: bool = True
    terminal: float = 0.1
    #: Taste guidance, off at core's own off values. See the module docstring.
    stg_scale: float = 0.0
    stg_blocks: str = "29"
    modality_scale: float = 1.0

    @property
    def manual(self):
        """Whether the render samples on the checkpoint's trained curve.

        The one thing outside this module that has to ask: `render._schedule`
        emits a different SIGMAS node either way, and on this route it emits no
        `ModelSamplingLTXV` either.
        """
        return self.schedule == "distilled"

    @property
    def stg(self):
        """Whether STG would do anything. Both halves have to say yes: a scale
        of 0 short-circuits inside core's post-CFG hook, and so does an empty
        block set, so either one alone means an extra node in the graph that
        costs a model clone and changes no frame."""
        return self.stg_scale != 0.0 and any(c.isdigit() for c in self.stg_blocks)

    @property
    def modality(self):
        """Whether modality guidance would do anything. 1.0 is core's own
        "no extra pass", not a low setting."""
        return self.modality_scale != 1.0


DEFAULTS = {
    # The trained curve, which is what the file in the `dit` slot is unless a
    # user went and picked the dev transformer. See the module docstring.
    "schedule": SCHEDULES[0],
    # `LTXVScheduler`'s step count, and the `scheduler` route's alone — the
    # distilled curve carries its own eight and reads nothing from here. 8
    # rather than the node's own 20 so that switching routes lands on the
    # distilled row's shape rather than the dev transformer's.
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
    # carries no options for the same reason H3's does not. Ancestral, which is
    # what both official workflows pick in both stages: the noise an ancestral
    # step adds back is part of what eight steps were distilled against, and
    # plain euler over the same curve comes out flat.
    "sampler_name": declare.DISTILLED_SAMPLER,
    # Taste guidance, off. `LTXVSpatioTemporalGuidance` returns the unmodified
    # prediction at 0 and `LTXVModalityGuidance` at 1.0 — these are core's own
    # off values rather than a timid setting, which is why the pills read them
    # through the manifest's `off` rather than through a range.
    "stg_scale": 0.0,
    # `LTXVSpatioTemporalGuidance`'s own default block, kept: which blocks to
    # degrade is a property of the trained transformer, and 29 is what
    # Lightricks' node ships pointing at.
    "stg_blocks": "29",
    "modality_scale": 1.0,
}


# What each field has to be. The same refusal-by-name H3's row makes: a
# hand-edited `"steps": "eight"` should say so before a loader is built.
_WHOLE = ("steps",)
_NUMBER = ("video_cfg", "audio_cfg", "max_shift", "base_shift", "terminal",
           "stg_scale", "modality_scale")
_FLAG = ("stretch",)
# The one field with a closed list. A misspelt route would otherwise pass as a
# name and sample on the wrong curve, which is the failure this whole field
# exists to make impossible.
_CHOICE = {"schedule": SCHEDULES}


class SamplingError(ValueError):
    """A `sampling` block this family will not run."""


# The floor a field's own node imposes, where it is not zero. Modality guidance
# is the whole list: `LTXVModalityGuidance` takes 1.0 as "off" and its formula
# scales by `modality_scale - 1`, so a value below it pushes the prediction away
# from the coupled one — the opposite of the control's name.
_FLOOR = {"stg_scale": 0.0, "modality_scale": 1.0}


def _blocks(value):
    """`stg_blocks`, checked. -> the string as written.

    Core parses it with `re.findall(r"\\d+")`, so what is legal is "any text
    with some numbers in it" — and an empty one is legal too, meaning STG is
    off however high its scale is. What is refused is text with no number in it
    at all, which is the typo case: it would sample at full cost with the
    perturbation switched off, and say nothing.

    A `custom` field on the row below rather than a kind of its own, because
    nothing else in this pack has an opinion like it.
    """
    if not isinstance(value, str):
        raise SamplingError("sampling.stg_blocks must be a list of block "
                            "numbers, written as text")
    if value.strip() and not any(c.isdigit() for c in value):
        raise SamplingError(
            f"sampling.stg_blocks is {value!r}, which names no block. Give it "
            f"transformer block numbers separated by commas, or leave it empty "
            f"to switch spatio-temporal guidance off.")
    return value


ROW = base_row.Row(DEFAULTS, error=SamplingError, whole=_WHOLE, number=_NUMBER,
                   flag=_FLAG, choice=_CHOICE, floors=_FLOOR,
                   custom={"stg_blocks": _blocks})


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
    stored = ROW.stored(data)

    def pick(name):
        return stored[name] if name in stored else DEFAULTS[name]

    return (
        Sampling(
            seed=int(widgets.get("seed", 0)),
            schedule=pick("schedule"), steps=pick("steps"),
            video_cfg=pick("video_cfg"), audio_cfg=pick("audio_cfg"),
            sampler_name=pick("sampler_name"),
            max_shift=pick("max_shift"), base_shift=pick("base_shift"),
            stretch=pick("stretch"), terminal=pick("terminal"),
            stg_scale=pick("stg_scale"), stg_blocks=pick("stg_blocks"),
            modality_scale=pick("modality_scale"),
        ),
        accel.Settings(),
    )
