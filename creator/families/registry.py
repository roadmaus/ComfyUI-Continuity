"""One registry for every family, whatever it produces.

A family declares what it renders — H3 produces video *and* still, Krea 2 and
Ideogram 4 are still-only — and this is the one place that knows they exist.
Callers name a family instead of importing its modules: the PreStage resolves
its arch pill here, the video nodes take their `Family` singleton here, and the
manifest route lists what this lists. One registry rather than one per kind,
because "which families exist" is one question and H3 answers it twice.

**Discovered, not written down.** This module used to carry six tables keyed by
family id — what each produces, how its prose reaches its encoder, which LoRA
stack it takes, whether it can pick a shot's length, what it routes between —
and `canvas.py` carried a seventh with the frame grids. Every value in them was
a fact its family already knew, and a new family meant seven edits to two files
it does not live in before its own package would run. Each family carries them
in a `declare.py` of its own now, and this walks the package for them: a family
becomes real by being a directory with a declaration in it.

`declare.py` is deliberately the one module of a family that imports nothing
heavy, which is what makes the walk affordable. `compile.py` has to know which
checkpoints a piece routes between before a loader exists, and importing a
family's `render.py` to find out would pull in the sampler.

Everything else resolves lazily, for the same reason: the video half of H3 pulls
in ComfyUI at import time and the pure suites load family modules without a
server to boot.
"""

import importlib
import os
import pkgutil

# The directory this module sits in — `families/`, whose subpackages are the
# families. `__path__` would be the package's, and this is a module inside it.
_HERE = os.path.dirname(os.path.abspath(__file__))


def _declarations():
    """Every family's declaration, in the order anything listing them shows.

    A subpackage of `families/` **is** a family, and one without a `declare.py`
    is a mistake worth naming rather than a directory to skip quietly. Plain
    modules beside them (`base.py`, `row.py`, `manifest.py`, this one) are not
    packages and are not candidates.

    Ordered by each family's own `ORDER`, ties broken by id so the list is
    stable whatever the filesystem hands back.
    """
    found = []
    for entry in pkgutil.iter_modules([_HERE]):
        if not entry.ispkg:
            continue
        try:
            module = importlib.import_module(f".{entry.name}.declare", __package__)
        except ModuleNotFoundError as exc:
            raise ImportError(
                f"families/{entry.name}/ is a family package with no "
                f"declare.py — every family declares what it is before any of "
                f"it is imported. See families/h3/declare.py."
            ) from exc
        found.append(module)
    return tuple(sorted(found, key=lambda m: (m.ORDER, m.ID)))


DECLARED = _declarations()

# Every family, in the order anything listing them shows them — the video
# families first, since that is the order the family pill offers.
FAMILIES = tuple(module.ID for module in DECLARED)

# The declaration of one family, by id.
DECLARATION = {module.ID: module for module in DECLARED}

# What each family renders. The manifest serves this; the split between the
# video loop and the still flow dispatches on it.
PRODUCES = {module.ID: module.PRODUCES for module in DECLARED}

# How a family's prose reaches its text encoder, as one word. Descriptive now
# rather than load-bearing: `compile.py` used to branch on it, and asks the
# family's grammar instead (`families/grammar.py`), so this is what the manifest
# tells the UI about the family rather than what decides the prompt.
PROMPT_PIPELINE = {module.ID: module.PROMPT_PIPELINE for module in DECLARED}

# How a family's LoRAs reach its transformer. A file that has nothing to do with
# the weights it is pointed at is the user's mistake and is reported as one:
# `lora.apply` raises when a stack places nothing at all rather than rendering as
# though it had.
LORA_STACK = {module.ID: module.LORA_STACK for module in DECLARED}

# Which families can be asked to pick a shot's own length, and the weight slot
# that does it. `None` where the family has no answer at all.
DURATION_HEAD = {module.ID: module.DURATION_HEAD for module in DECLARED}

# The checkpoints each family routes a generation between. The manifests'
# `routed` flags are the same answer served to the frontend, and
# `tests/test_families.py` holds the two together.
ROUTED = {module.ID: tuple(module.ROUTED) for module in DECLARED}

# The families that render nothing but stills, in the registry's order.
IMAGE_FAMILIES = tuple(module.ID for module in DECLARED
                       if module.PRODUCES == frozenset({"still"}))

# What the pre-stage blob's `arch` pill calls each still-capable family, in the
# order the pill offers them: the families that are *only* stills first, then
# the still branch of a family that also renders video — which is a video
# generation one latent frame of which is decoded, and belongs after the ones
# that draw a picture outright.
#
# "minimax" predates the family ids and is frozen in every saved blob, so that
# alias is permanent — the id it maps to is the family's own declaration.
STILL_ARCHES = {
    module.STILL_ARCH: module.ID
    for module in sorted(DECLARED, key=lambda m: (len(m.PRODUCES), m.ORDER))
    if module.STILL_ARCH
}

# The canvas and duration arithmetic of every family that has any. A still-only
# family has no entry — there is no duration and no frame grid to have one for.
# `compile.rules_of` is what looks a piece's family up in it.
RULES = {module.ID: module.RULES for module in DECLARED if module.RULES}

# What a blob with no arch means: the pill's first entry.
DEFAULT_STILL_ARCH = "krea2"

# What a piece with no `family` means. Every workflow saved before the field
# existed is one, so like `STILL_ARCHES`' "minimax" alias this default is
# permanent: it is what "the video node" meant when there was only one answer.
DEFAULT_VIDEO = "h3"


def rules(family):
    """The canvas rules of `family`, or None where it renders no video."""
    return RULES.get(family)


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


def segment_nodes():
    """Every video family's segment node, for the pack's ComfyUI extension.

    Asked of the families rather than listed by the extension, which is what
    makes registering one the family's own business: a new package used to need
    a line in `creator_node.py` before its node existed at all — the last edit
    outside a family package that adding a family still required.

    Imported here and not at module scope, for the reason everything else in
    this module is lazy: a segment node pulls in ComfyUI and the pure suites
    load declarations without a server.
    """
    nodes = []
    for family in video_families():
        module = importlib.import_module(f".{family}.segment", __package__)
        nodes.extend(module.NODES)
    return nodes


def video(family=DEFAULT_VIDEO):
    """The video `Family` singleton (`families/base.py`) for `family`.

    Imported on demand because the video hooks pull in ComfyUI — asking for a
    family is asking for its whole render half.
    """
    if "video" not in PRODUCES.get(family, ()):
        raise KeyError(f"{family!r} renders no video")
    return importlib.import_module(f".{family}.render", __package__).FAMILY
