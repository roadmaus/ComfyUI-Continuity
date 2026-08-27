"""The ControlNet guide: what the pill leaves, and where each pass looks in it.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_guide.py

`tests/golden/guide_*.json` freeze the graph this produces; this suite says what
the graph *means*, which is the half a byte comparison cannot express.

The feature is deliberately split in two and every section below is about one
half or the seam between them. **The drawing is an asset** — it rides in
`assets` with `role: "guide"`, so the picker attaches it and the trim overlay
says which seconds of it a shot uses, and none of that is code this pack had to
write. **The switch is a setting** — whether the branch is loaded at all, and
how hard it pulls. Either half alone must do nothing, which is the pair of
assertions at the end of the golden suite.

The part worth testing hardest is `without`: a guide has to stay out of the
segment node's cache key, and getting that wrong is silent. Nothing breaks; the
prompt is simply re-encoded every time a trim handle moves, on a file the text
encoder has never seen.
"""

import asyncio
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))

    sys.path.insert(0, os.path.dirname(ROOT))


try:
    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

importlib.import_module(PACKAGE)

guide = importlib.import_module(f"{PACKAGE}.creator.guide")
compiler = importlib.import_module(f"{PACKAGE}.creator.compile")
h3 = importlib.import_module(f"{PACKAGE}.creator.families.h3.declare")

from harness import FAILURES, check, passed  # noqa: E402

passed("all guide tests passed")

FILE = "continuity/control/walk_edges.mp4"


# ---- the switch --------------------------------------------------------------
#
# Three ways a blob says "do not load a branch", and they all have to give the
# same answer, because every one of them is an ordinary state rather than a
# mistake: a blob from before the feature, a piece nobody has thrown it on, and
# a switch explicitly off.

check("no block at all", guide.Guide.of({}), None)
check("a blob from before guides", guide.Guide.of({"prompt": "x"}), None)
check("the switch off", guide.Guide.of({"guide": {"on": False}}), None)

on = guide.Guide.of({"guide": {"on": True, "strength": 0.8,
                               "start": 0.1, "end": 0.7}})
check("the strength", on.strength, 0.8)
check("the schedule window", (on.start, on.end), (0.1, 0.7))

# Clamped to what the weights were trained at rather than to what the apply node
# will accept. Core's node takes a strength of 10; nothing above 1.0 was
# trained, and a blob that says 4 is a hand edit rather than a request.
wild = guide.Guide.of({"guide": {"on": True, "strength": 4.0,
                                 "start": -1.0, "end": 9.0}})
check("strength clamped to the trained range", wild.strength, guide.MAX_STRENGTH)
check("the window clamped to the schedule", (wild.start, wild.end), (0.0, 1.0))

# Two ends of one control, dragged past each other. Normalised rather than
# refused: it is a thing hands do, and the honest reading is the span between.
crossed = guide.Guide.of({"guide": {"on": True, "start": 0.8, "end": 0.2}})
check("a crossed window is the span between the ends",
      (crossed.start, crossed.end), (0.2, 0.8))

# Garbage where a number belongs falls back rather than raising. The blob is
# hand-editable by design and a typo in one dial should not cost the piece.
junk = guide.Guide.of({"guide": {"on": True, "strength": "hard"}})
check("a non-number falls back to the default",
      junk.strength, guide.DEFAULT_STRENGTH)


# ---- the drawing, as an asset -------------------------------------------------
#
# The half this pack did not have to write. A guide is attached the way every
# other clip is, so what is tested here is only the two things the role adds:
# it must be a clip, and there can be only one.


def compiled(assets, **fields):
    return compiler.compile_request(
        {"prompt": "a red room", "duration_s": 6, "aspect": "16:9",
         "short_edge": 768, "assets": assets, **fields}, None)


GUIDE = {"handle": "gde-1", "kind": "video", "role": "guide", "filename": FILE}

one = compiled([GUIDE])
check("the guide is on the compiled shot", one.guide.filename, FILE)
check("and is not a reference", [a.handle for a in one.ref_videos], [])

# The trim is the asset's own, set in the overlay every reference clip uses.
# This is the whole reason a guide is an asset rather than a block of its own:
# "which seconds of that file" is a question the grammar already answered.
trimmed = compiled([{**GUIDE, "trim": {"start": 4.0, "end": 10.0}}])
check("the window is the asset's trim", trimmed.guide.trim, (4.0, 10.0))

# A still held for the whole shot is a shot told not to move. Refused with that
# sentence rather than silently accepted, because the branch would take it.
try:
    compiled([{**GUIDE, "kind": "image", "filename": "a.png"}])
    FAILURES.append("a still was accepted as a guide")
except compiler.CompileError as exc:
    if "clip" not in str(exc):
        FAILURES.append(f"the refusal does not say a guide is a clip: {exc}")

# One per shot: the branch injects a single control latent, so two drawings is a
# question with no answer.
try:
    compiled([GUIDE, {**GUIDE, "handle": "gde-2"}])
    FAILURES.append("two guides on one shot were accepted")
except compiler.CompileError as exc:
    if "one guide" not in str(exc):
        FAILURES.append(f"the refusal does not name the limit: {exc}")

# And a shot with no guide says so plainly, which is what the loop branches on.
check("no guide is None", compiled([]).guide, None)


# ---- out of the cache key ------------------------------------------------------
#
# `without` is the seam between the two halves, and the one place a mistake here
# is silent. A guide reaches the model through a branch bolted on *after* the
# segment node, so leaving it in `segment_data` re-encodes the prompt every time
# a trim handle moves — on a file the encoder never sees.

payload = {"request": {"prompt": "x", "assets": [GUIDE, {"handle": "img-1",
                                                         "kind": "image",
                                                         "role": "reference"}]}}
stripped = guide.without(payload)
check("the guide comes out", [a["handle"] for a in stripped["request"]["assets"]],
      ["img-1"])
check("the references stay", len(stripped["request"]["assets"]), 1)
check("the original is not mutated", len(payload["request"]["assets"]), 2)

# A shot whose only attachment was the guide has to serialise as what it now is
# — a shot with nothing attached — or it keeps a cache key of its own forever
# and never hits the one every other bare shot shares.
lone = guide.without({"request": {"prompt": "x", "assets": [GUIDE]}})
check("an empty list is no key at all", "assets" in lone["request"], False)

# Nothing to strip is the payload itself, so a render with no guide on it
# serialises byte-identically to what it always did.
bare = {"request": {"prompt": "x"}}
check("a payload with no assets is handed straight back",
      guide.without(bare) is bare, True)
plain = {"request": {"prompt": "x", "assets": [{"handle": "img-1",
                                                "kind": "image",
                                                "role": "reference"}]}}
check("a payload with no guide is handed straight back",
      guide.without(plain) is plain, True)
# A clip payload has no request at all.
clip = {"clip": {"filename": "a.mp4"}}
check("a clip payload is handed straight back", guide.without(clip) is clip, True)


# ---- which tracings these weights know -----------------------------------------
#
# Never an error, anywhere. A guide the checkpoint was not post-trained on is
# still a picture; the render comes out looking like the drawing rather than
# aimed by it, which is worth saying and not worth refusing.


class Traced:
    def __init__(self, op):
        self.op = op


check("a trained tracing is not flagged",
      guide.untrained(Traced("depth"), h3.CONTROL_TRACINGS), False)
check("an untrained tracing is flagged",
      guide.untrained(Traced("blocks"), h3.CONTROL_TRACINGS), True)
# A guide that did not come off the bench carries no tracing id, and nothing can
# be said about it. An empty id is not an untrained one.
check("no tracing id says nothing",
      guide.untrained(Traced(""), h3.CONTROL_TRACINGS), False)
check("no asset at all says nothing",
      guide.untrained(None, h3.CONTROL_TRACINGS), False)


# ---- the wrapper ---------------------------------------------------------------
#
# `Controlled` is what lets the sampler, refine and face hooks stay unaware that
# guides exist: it answers `.out(i)` for the four outs a segment node has, with
# the one a controlnet replaced swapped in and the other three untouched.


class Segment:
    def out(self, index):
        return ("segment", index)


held = guide.Controlled(Segment(), positive=("controlnet", 0))
check("the conditioning is replaced", held.out(1), ("controlnet", 0))
check("the model is the segment's", held.out(0), ("segment", 0))
check("the latent is the segment's", held.out(2), ("segment", 2))
# The turbo lead-in samples out 3 — the model with the distillation held off it
# — and both sittings have to be aimed at the same drawing. Replacing the
# conditioning rather than the model is what makes that true for free.
check("the lead model is the segment's", held.out(3), ("segment", 3))
