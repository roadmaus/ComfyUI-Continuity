"""The graphs this pack emits, frozen case by case.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_golden_graph.py

This is the net under the multi-family refactor. The other graph suites say what
the wiring *means* — which node reads which, what a seam carries, why a clip has
no sampler — and they are the ones to read and to extend. This one says only
that it has not moved, and it says it about every node and every input at once,
which is the assertion a pure move needs and the one no property check can make.

The cases below are chosen to reach every branch in `render.emit` that changes
the shape of the graph rather than a number inside it: the two checkpoints, both
seams, the merge, the second pass, the face pass, supplied footage, and the
accelerators. A branch with no case here is a branch a refactor can break in
silence, so a phase that adds one adds a case.

**Machine settings are pinned.** `render.emit`'s turbo lead-in and the save
node's CRF and folder come from `settings.load`, which reads a file in this
ComfyUI's user directory — so without this the goldens would record whatever the
person who ran them last had set on the settings page, and would fail for
everyone else. The defaults are what a fresh install renders with and are the
only honest thing to freeze.

See `goldens.py` for the id normalisation and for how to re-record.
"""

import asyncio
import importlib
import json
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

# The pack imports *outside* the skip guard. A machine without ComfyUI is
# allowed to bow out; a pack that will not import is the exact failure this
# suite exists to catch, and for one afternoon a skip that swallowed it
# reported eight suites green on a branch whose node did not load.
importlib.import_module(PACKAGE)

cn = importlib.import_module(f"{PACKAGE}.creator.creator_node")
media_mod = importlib.import_module(f"{PACKAGE}.creator.media")
settings_mod = importlib.import_module(f"{PACKAGE}.creator.settings")

from goldens import compare
from harness import FAILURES, passed

passed("all golden graph tests passed")

# See the module docstring: the settings file on the machine running this must
# not reach the recorded graph. Patched rather than pointed at a temporary file
# because `load` resolves its own path through `folder_paths`, and a suite that
# had to stand up a user directory to freeze a default would be describing the
# filesystem instead of the render.
settings_mod.load = lambda: dict(settings_mod.DEFAULTS)

# The same argument about the attached files. A keyframe with `aspect_source`
# on auto takes the canvas from its own picture, so the graph a keyframe blob
# expands to depends on the size of a PNG in this ComfyUI's input folder — which
# is not something a golden can be honest about on two machines. Answered from a
# table instead, so the branch is exercised and the answer is the same wherever
# it runs. `creator_node._render` reads this off the module at call time, which
# is what makes patching it here enough.
#
# The keyframes are portrait on purpose: a 16:9 picture behind a blob whose pill
# also says 16:9 derives the canvas the pill would have given anyway, so the
# golden would look identical whether the derivation ran or not. Portrait is what
# makes that branch visible in the file.
SIZES = {"a.png": (1080, 1920), "b.png": (1080, 1920), "face.png": (1024, 1024)}
media_mod.image_size = lambda filename: SIZES.get(filename, (1920, 1080))

MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
}

# The face pass loads its detector itself rather than through an emitted loader,
# so it is named only where a case actually repairs a face — a file in the blob
# that nothing reads would be describing a picker, not a graph.
FACE_MODELS = {**MODELS, "sam3": "sam3.safetensors"}

NODE_ID = "7"


def piece(**fields):
    """A whole-piece blob with the weights and the canvas already filled in."""
    return json.dumps({
        "version": 2,
        "prompt": "",
        "aspect": "16:9",
        "short_edge": 768,
        "models": MODELS,
        **fields,
    })


def graph_of(data, **overrides):
    """The subgraph `MiniMaxH3Creator` expands `data` to.

    The sampler row is passed explicitly rather than left to the schema's
    defaults: these values are half of what the goldens freeze, and reading them
    off the node would make a golden move whenever a default was retuned — which
    is a change worth seeing in `creator_node.py`'s diff, not in twelve JSON
    files.
    """
    from comfy_api.latest import io as comfy_io

    kwargs = dict(
        creator_data=data,
        seed=100, steps=20, cfg=1.0,
        sampler_name="res_multistep", scheduler="simple",
    )
    kwargs.update(overrides)

    node = cn.MiniMaxH3Creator
    previous = node.hidden
    node.hidden = comfy_io.HiddenHolder(
        unique_id=NODE_ID, prompt=None, extra_pnginfo=None, dynprompt=None,
        auth_token_comfy_org=None, api_key_comfy_org=None)
    try:
        return node.execute(**kwargs).expand
    finally:
        node.hidden = previous


def frozen(name, data, **overrides):
    compare(name, graph_of(data, **overrides), FAILURES)


# ---- one generation ---------------------------------------------------------
#
# The shapes a lone render can take, which is also every shape a single segment
# of a timeline can take. Text-only and keyframe route to FL2VA; anything with a
# reference routes to Ref2VA and loads the other checkpoint instead, so these
# three between them build both loaders and both encode paths.

frozen("text_only", piece(segments=[{"prompt": "a red room", "duration_s": 6}]))

frozen("keyframe", piece(segments=[{
    "prompt": "she turns to the window", "duration_s": 6,
    "assets": [
        {"handle": "img-1", "kind": "image", "role": "first_frame", "filename": "a.png"},
        {"handle": "img-2", "kind": "image", "role": "last_frame", "filename": "b.png"},
    ],
}]))

# One of each kind of reference, because the ordinals are assigned across the
# three lists in one walk and a golden of images alone would not hold that order
# down.
frozen("references", piece(segments=[{
    "prompt": "@img-1 walks through the room from @vid-1, scored like @aud-1",
    "duration_s": 6,
    "assets": [
        {"handle": "img-1", "kind": "image", "role": "reference", "filename": "face.png"},
        {"handle": "vid-1", "kind": "video", "role": "reference", "filename": "walk.mp4"},
        {"handle": "aud-1", "kind": "audio", "role": "reference", "filename": "score.wav"},
    ],
}]))

# ---- the timeline -----------------------------------------------------------
#
# Three cards, and the middle seam carries both halves: a feathered picture and
# an audio tail. This is the case that wires `prev_image`, `prev_audio` and the
# trim on the reel, none of which a one-segment render reaches.

frozen("chained_seam", piece(
    prompt="a house at dusk",
    audio_tail_s=1.0,
    segments=[
        {"prompt": "wide", "duration_s": 5},
        {"prompt": "closer", "duration_s": 5, "continue": True, "feather": 5,
         "continue_audio": True},
        {"prompt": "cut away", "duration_s": 5},
    ],
))

# The same strip read the other way: one generation whose description holds all
# three shots. Nothing is decoded mid-clip, so the graph loses the seam nodes and
# the loop runs once — the largest structural difference any blob field makes.
frozen("one_pass", piece(
    prompt="a house at dusk",
    render="single",
    segments=[
        {"prompt": "wide", "duration_s": 5},
        {"prompt": "closer", "duration_s": 5},
        {"prompt": "cut away", "duration_s": 5},
    ],
))

# Supplied footage: a card with no sampler in front of it. It reaches the reel
# as a file, and the pass before it ends on the clip's opening rather than
# cutting to it, which is the seam running forwards.
frozen("supplied_clip", piece(
    prompt="a house at dusk",
    segments=[
        {"prompt": "wide", "duration_s": 5, "ends_on": True},
        {"kind": "clip", "filename": "footage.mp4", "duration_s": 4,
         "width": 1920, "height": 1080},
    ],
))

# ---- the second passes ------------------------------------------------------
#
# Both of them add a *second* segment node compiled at another canvas, which is
# the wiring most easily broken by a move — the refine pass at the target size,
# the face pass at the crop.

frozen("refine_two_pass", piece(
    short_edge=1152,
    segments=[{"prompt": "a red room", "duration_s": 6}],
))

frozen("face_pass", json.dumps({
    "version": 2,
    "prompt": "",
    "aspect": "16:9",
    "short_edge": 768,
    "models": FACE_MODELS,
    "face": {"on": True, "canvas": 512, "denoise": 0.45},
    "segments": [{"prompt": "a woman crossing a market", "duration_s": 5}],
}))

# ---- the model patches ------------------------------------------------------
#
# What `render.patched` puts between the segment node and the sampler. The
# accelerators that need a pack installed are not frozen here — a golden that
# only records on a machine with FirstBlockCache and KJNodes is a golden nobody
# else can check — so what is covered is the two paths that need nothing: the
# flow shift, and one accelerator behind the stand-in the other graph suites
# already use. `test_accel.py` owns the arguments; this owns the edge.

# H3 runs picture and sound on separate schedules, and at the checkpoints' own
# 12/3 no shift node is emitted at all. Moved off those, one appears — so this
# freezes both the node and the fact that the default emits nothing, since the
# cases above all run at the defaults.
frozen("sigma_shift",
       piece(segments=[{"prompt": "a red room", "duration_s": 6}]),
       shift_video=6.0, shift_audio=3.0)


class _FakePack:
    """A stand-in for an accelerator pack that is not installed.

    `accel.py` reads the installed class's own defaults rather than carrying a
    copy, so the on path can only be reached with *something* registered. The
    harness boots with `init_custom_nodes=False`, which means the real pack is
    absent here even on a machine that has it — the same reasoning, and the same
    fake, as `test_timeline_graph.py`.
    """

    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",),
                             "mode": (["H3 Safe — 0.08", "H3 Fast — 0.10"],
                                      {"default": "H3 Fast — 0.10"})}}


import nodes as comfy_nodes  # noqa: E402  (only reachable once ComfyUI has booted)

_accel = importlib.import_module(f"{PACKAGE}.creator.accel")
comfy_nodes.NODE_CLASS_MAPPINGS[_accel.BLOCK_CACHE_NODE] = _FakePack
try:
    frozen("block_cache",
           piece(segments=[{"prompt": "a red room", "duration_s": 6}]),
           block_cache="fast")
finally:
    del comfy_nodes.NODE_CLASS_MAPPINGS[_accel.BLOCK_CACHE_NODE]


# ---- the row in the blob -----------------------------------------------------
#
# `sampling.py` moved the row off the widgets and into `creator_data`, and the
# widgets stayed declared as the fallback. Three things have to be true of that,
# and none of them is a golden — they are claims about two graphs being the same
# rather than about one graph being what it was, so they are checked here
# directly and the goldens above go on covering the shape.

from goldens import canonical  # noqa: E402

SHOT = {"prompt": "a red room", "duration_s": 6}
ROW = {"steps": 7, "cfg": 2.5, "sampler_name": "euler", "scheduler": "beta"}

# 1. The two roads reach the same graph. A blob that names the row and a node
#    whose widgets name it must emit the identical thing, or the migration is
#    not a migration.
by_widget = graph_of(piece(segments=[SHOT]), **ROW)
by_blob = graph_of(piece(segments=[SHOT], sampling=ROW))
if canonical(by_widget) != canonical(by_blob):
    FAILURES.append("a sampling block does not emit what the same widgets emit")

# 2. The blob wins where both speak. Otherwise a workflow whose widgets still
#    hold pre-migration values would quietly render at them forever.
contested = graph_of(piece(segments=[SHOT], sampling=ROW),
                     steps=99, cfg=9.9, sampler_name="ddim", scheduler="karras")
if canonical(contested) != canonical(by_blob):
    FAILURES.append("the widgets outrank the blob's sampling block")


def _segment_data(graph):
    return [node["inputs"]["segment_data"] for node in graph.values()
            if node["class_type"] == "MiniMaxH3TimelineSegment"][0]


# 3. And none of it reaches the segment node's cache key. The row is not
#    conditioning: re-rolling the step count must not re-encode a reference, and
#    the only thing standing between those two facts is that `compile.py` builds
#    payloads out of named keys. This is what says so out loud.
if _segment_data(graph_of(piece(segments=[SHOT]))) != _segment_data(by_blob):
    FAILURES.append("a sampling block changed segment_data — the row is now a cache key")
