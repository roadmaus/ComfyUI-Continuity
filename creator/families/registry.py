"""One registry for every family, whatever it produces.

A family declares what it renders — H3 produces video *and* still, Krea 2 and
Ideogram 4 are still-only — and this is the one table that says so. Callers
name a family instead of importing its modules: the PreStage resolves its arch
pill here, the video nodes take their `Family` singleton here, and the
manifest route lists what this lists. One registry rather than one per kind,
because "which families exist" is one question and H3 answers it twice.

Everything resolves lazily. The registry itself imports nothing of a family
until it is asked, because the video half of H3 pulls in ComfyUI at import
time and the pure suites load family modules without a server to boot.
"""

import importlib

# Every family, in the order anything listing them shows them — the video
# families first, since that is the order the family pill offers.
FAMILIES = ("h3", "ltx25", "krea2", "ideogram4")

# What each family renders. The manifest serves this; the split between the
# video loop and the still flow dispatches on it.
PRODUCES = {
    "h3": frozenset({"video", "still"}),
    "ltx25": frozenset({"video"}),
    "krea2": frozenset({"still"}),
    "ideogram4": frozenset({"still"}),
}

# How a family's prose reaches its text encoder, and the one thing about a
# family `compile.py` has to know that is not canvas arithmetic.
#
# "context-ir" is H3's own training: section headers, `[Shot 2] At 00:05.000`
# cut lines, a `<Picture 1>` glossary defining every attached file. "plain" is
# the substituted description and nothing else — what an encoder that was
# trained on captions should be sent, and what putting H3's format in front of
# Gemma would spoil. The families' manifests serve the same value under
# `prompt.pipeline`, read off this table so the two cannot disagree.
PROMPT_PIPELINE = {
    "h3": "context-ir",
    "ltx25": "plain",
    "krea2": "plain",
    "ideogram4": "plain",
}

# Which families can be asked to pick a shot's own length, and the weight slot
# that does it. `None` where the family has no answer at all — H3 does not, and
# a control that offered "auto" there would be offering nothing.
#
# Here rather than in the manifests for the same reason `PROMPT_PIPELINE` is:
# `compile.py` has to know whether a card's `auto_duration` means anything
# before any manifest is built, and the family's own capability block reads
# this table, so a UI cannot offer a length nobody will predict.
DURATION_HEAD = {
    "h3": None,
    "ltx25": "duration_head",
    "krea2": None,
    "ideogram4": None,
}

# What the pre-stage blob's `arch` pill calls each still-capable family.
# "minimax" predates the family ids and is frozen in every saved blob, so the
# alias is permanent — the id it maps to is the registry's business.
STILL_ARCHES = {"krea2": "krea2", "ideogram4": "ideogram4", "minimax": "h3"}

# What a blob with no arch means: the pill's first entry.
DEFAULT_STILL_ARCH = "krea2"

# What a piece with no `family` means. Every workflow saved before the field
# existed is one, so like `STILL_ARCHES`' "minimax" alias this default is
# permanent: it is what "the video node" meant when there was only one answer.
DEFAULT_VIDEO = "h3"


def video_families():
    """Every family that renders video, in the registry's order.

    What the piece's family pill may hold, and what `compile.piece_family`
    validates against — asked of the registry rather than written down, so a
    family becomes selectable by being registered.
    """
    return tuple(f for f in FAMILIES if "video" in PRODUCES.get(f, ()))


def still(arch):
    """The still module answering for a pre-stage `arch`, or None.

    What comes back is the family's `still.py` — the uniform surface the
    PreStage drives: `compile_still(data, image_size_lookup)` and
    `emit_still(data, plan, sampling, unique_id)`.
    """
    family = STILL_ARCHES.get(arch)
    if family is None:
        return None
    return importlib.import_module(f".{family}.still", __package__)


def video(family=DEFAULT_VIDEO):
    """The video `Family` singleton (`families/base.py`) for `family`.

    Imported on demand because the video hooks pull in ComfyUI — asking for a
    family is asking for its whole render half.
    """
    if "video" not in PRODUCES.get(family, ()):
        raise KeyError(f"{family!r} renders no video")
    return importlib.import_module(f".{family}.render", __package__).FAMILY
