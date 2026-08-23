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

# Every family, in the order anything listing them shows them.
FAMILIES = ("h3", "krea2", "ideogram4")

# What each family renders. The manifest serves this; the split between the
# video loop and the still flow dispatches on it.
PRODUCES = {
    "h3": frozenset({"video", "still"}),
    "krea2": frozenset({"still"}),
    "ideogram4": frozenset({"still"}),
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
