"""How the piece is run, read off the blob instead of off the widgets.

The node declares thirteen sampler widgets — steps, cfg, the sampler and
scheduler, the two flow shifts, and the accelerators — and the frontend hides
every one of them and re-draws them as pills. They were widgets because that is
what a ComfyUI node had, not because anybody wanted them there.

**Which is a problem the moment there is a second model family.** A node's
schema is static per class, and LTX-AV does not want the same row: it samples
through a guider with separate video and audio CFG scales, a stretched sigma
schedule with its own terminal, and none of it is a superset of H3's. Three ways
out of that, and two of them are bad — one node class per family multiplies the
frontend and the menu, and a union of every family's widgets makes every node
wear every other family's controls. The third is to put the row where everything
else about the piece already lives, which is the blob the UI owns.

**Nothing is removed to do it.** ComfyUI restores widget values *by position*,
so dropping a widget silently hands the next one somebody else's value — this
pack has already been bitten once, when adding the two flow shifts made a
nine-entry saved row read `steps` into `shift_video`. The `sage` slot is kept
alive today for exactly that reason and says so. So the thirteen stay declared,
in order, forever; they are already invisible, so keeping them costs nothing.

**The fallback is the migration.** `resolve` reads each field from the blob and
falls back to the widget value, key by key rather than block by block. A
workflow saved before this existed has no `sampling` block and every field falls
through to the widget it always used, so it queues exactly as it did. A blob
written by an older frontend that is missing one field falls through for that
one field alone, which is what makes adding a field later free. And a headless
API queue that never opens the node keeps working for the same reason.

What is *not* here is the seed. `control_after_generate` only exists on a real
widget — it is the frontend's own linked control, not something a JSON field can
carry — and the seed is the one number on this row a user reaches for between
runs. It stays a widget and `creator_node` passes it through.

Nothing in this module reaches the segment node's cache key: `compile.py` builds
payloads out of named keys, so a blob field it does not read cannot land in
`segment_data`. That is what keeps re-rolling the step count from re-encoding
every reference, and `tests/test_golden_graph.py` is what holds it to it.
"""

from dataclasses import dataclass

from . import accel
from .families import row

# The H3 checkpoints' own flow shifts — `MiniMaxH3Model.__init__`'s
# `sigma_shift_video` / `sigma_shift_audio` defaults. At exactly these values no
# shift node is emitted, so a graph whose pills were never touched stays
# byte-identical to what this pack always built.
SHIFT_DEFAULTS = (12.0, 3.0)


@dataclass(frozen=True)
class Sampling:
    """The sampler settings, however the node came by them.

    Lived in `render.py` while the row was widgets and nothing but widgets. It
    is here because this is the module with no ComfyUI import in it: the blob
    half of the row has to be readable — and mirrored in the frontend, and one
    day declared by a family manifest — without booting a server. `render.py`
    re-exports the name, which is what everything downstream still spells.
    """

    seed: int = 0
    steps: int = 20
    cfg: float = 1.0
    sampler_name: str = "res_multistep"
    scheduler: str = "simple"
    shift_video: float = SHIFT_DEFAULTS[0]
    shift_audio: float = SHIFT_DEFAULTS[1]

    def shifted(self):
        return (self.shift_video, self.shift_audio) != SHIFT_DEFAULTS


# Every field this row carries, and what it is worth when nobody has said — the
# widgets' own defaults, kept beside the dataclass they fill so a retune happens
# once and this cannot drift from the schema it falls back to.
DEFAULTS = {
    "steps": 20,
    "cfg": 1.0,
    "sampler_name": "res_multistep",
    "scheduler": "simple",
    "shift_video": SHIFT_DEFAULTS[0],
    "shift_audio": SHIFT_DEFAULTS[1],
    "block_cache": "off",
    "spectrum": False,
    "spectrum_blend": 0.5,
    "attention": "default",
    "chunk_ffn": False,
    "fp16_accumulation": False,
}

# What each field has to be. Anything else in the blob is refused by name rather
# than coerced: a hand-edited `"steps": "twenty"` should say so before a loader
# is built, not sample once at whatever `int()` made of it.
_WHOLE = ("steps",)
_NUMBER = ("cfg", "shift_video", "shift_audio", "spectrum_blend")
_FLAG = ("spectrum", "chunk_ffn", "fp16_accumulation")
_CHOICE = {
    "block_cache": accel.BLOCK_CACHE_MODES,
    "attention": accel.ATTENTION_MODES,
}


class SamplingError(ValueError):
    """A `sampling` block this pack will not run."""


# The row itself, as kinds — see `families/row.py`. What is left here is the
# field lists, which are the only part that is H3's.
ROW = row.Row(DEFAULTS, error=SamplingError, whole=_WHOLE, number=_NUMBER,
              flag=_FLAG, choice=_CHOICE)


def block(data):
    """The blob's `sampling` block, validated. `{}` where there is none.

    An absent block is the ordinary state of every workflow saved before this
    existed, so it is not an error — it means every field falls back.
    """
    return ROW.stored(data)


def resolve(data, widgets):
    """-> `(Sampling, accel.Settings)` for this queue.

    `widgets` is what the node was actually called with, and is the fallback for
    every field the blob does not carry. Both halves come out of one function
    because they are one row on screen and one decision by the user; splitting
    them would be describing the two dataclasses rather than the control.
    """
    stored = block(data)

    def pick(name):
        if name in stored:
            return stored[name]
        # `widgets` is missing a key only when a caller left it off entirely,
        # which the schema does not allow; `DEFAULTS` is there so this module
        # is still usable from a test that passes a partial row.
        return widgets.get(name, DEFAULTS[name])

    return (
        Sampling(
            seed=int(widgets.get("seed", 0)),
            steps=pick("steps"), cfg=pick("cfg"),
            sampler_name=pick("sampler_name"), scheduler=pick("scheduler"),
            shift_video=pick("shift_video"), shift_audio=pick("shift_audio"),
        ),
        accel.Settings(
            block_cache=pick("block_cache"),
            spectrum=pick("spectrum"),
            spectrum_blend=pick("spectrum_blend"),
            attention=_attention(pick("attention"),
                                 widgets.get("sage", False),
                                 named="attention" in stored),
            chunk_ffn=pick("chunk_ffn"),
            fp16_accumulation=pick("fp16_accumulation"),
        ),
    )


def _attention(attention, sage, named):
    """Which backend the row is asking for, across the rename.

    `sage` was a switch before `attention` was a list, and a workflow saved with
    it on has to keep running sage. So the switch is read only where the list
    has not been spoken for.

    Which the widgets could not actually express. "Nobody touched the list" and
    "somebody chose `default`" are both the string `"default"`, so on a node
    whose old switch was on, picking `default` did nothing at all — there was no
    way to say it. A blob can: the field is *absent* until a pill writes one, so
    `named` is the difference between the two, and turning the attention off on
    an old node is now a thing a user can do. Nothing already saved changes,
    because nothing already saved has a block.

    The switch itself stays widget-only. It predates all of this and no pill
    will ever write one, so the blob has nothing to say about it.
    """
    if sage and not named and attention == "default":
        return "sage"
    return attention
