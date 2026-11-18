"""FLUX 3 Image Klein's refiner: BFL's prompt upsampler in place of the pack's.

The still families share `stillrefine`, and this family keeps its modes and
its template pin. What it replaces is the instruction and the reply: BFL
publishes the instruction their upsampler was fitted to (`upsample.py`), the
model the card says to run before every request, so the refine button runs
that rather than a second opinion of the pack's. No JSON contract, no prefill,
no `what_i_see` — the reply is the caption, as BFL's pipeline takes it.

Which instruction is the mode's. `EDIT` and `REF` render with the pictures as
reference latents, which is what BFL's `i2i` was written for. `I2I` starts
from a picture at partial denoise that the model never reads as a reference,
and `T2I` has nothing attached: both get `t2i`, which is asked about the words.
"""

from .. import stillrefine
from . import upsample

# The modes whose pictures reach the model as references.
READS_PICTURES = ("EDIT", "REF")


class Flux3KleinPrompting(stillrefine.StillPrompting):
    id = "flux3klein"

    # BFL's caption is plain prose that names no picture by handle — "this
    # image", "the first image" — and Klein reads every attached picture as a
    # reference whether the caption names it or not.
    prefill = ""
    reports_seen = False
    cites_pictures = False

    def reply_shape(self, mode, shots, cuts=0, shown=(), piece=False, ref_shots=(),
                    cast=()):
        return None

    def system_prompt(self, mode, language="English", shape=None, cuts=0, extra="",
                      cast=(), still=True, attached=True):
        system = upsample.system_prompt(mode in READS_PICTURES)
        # A user's own instructions in `add` mode, joined on as one more
        # section — the skill path's promise, kept.
        return f"{system}\n\n{extra.strip()}" if extra.strip() else system

    def user_message(self, shots, seconds=None, shown=(), mode=None, piece=None,
                     pool=None, footage=(), cast=()):
        pictures = tuple(shown) if mode in READS_PICTURES else ()
        return upsample.user_message(shots[0].get("text"), pictures)

    def parse_reply(self, content, mode, shots, cuts=0, piece=False, ref_shots=()):
        text = upsample.caption(content)
        if not text:
            raise stillrefine.RefineError("the upsampler returned no caption — try again, "
                                          "or use a larger model")
        return {"shots": [text], "soundscape": "", "music": "", "seen": ""}


PROMPTING = Flux3KleinPrompting()
