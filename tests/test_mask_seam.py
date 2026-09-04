"""Contract tests for latent-mask continuation: `compile.py`'s `seam_mode`
validation and `families/h3/maskseam.py`'s node wiring.

Runs standalone — `python tests/test_mask_seam.py` — with no torch and no
ComfyUI. `maskseam.py` imports `nodes` (ComfyUI's registry) only inside its
functions, so a stub module under that name is the whole of the harness for
it, the same shape `test_accel.py` uses for the other externally-wired
accelerators.
"""

import sys
import types

import layout

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "compile",
                   "still", package="mmc")
compiler = _pkg.compile

# `maskseam` imports `nodes` lazily, so the stub only has to exist before a
# function that reaches for it is called — not before the module loads.
NODES = types.ModuleType("nodes")
NODES.NODE_CLASS_MAPPINGS = {}
sys.modules["nodes"] = NODES

# `splice_live` reaches for `media.TARGET_FPS`, and `media.py` imports
# ComfyUI's `folder_paths` at module level whether or not this path ever calls
# it — an empty stand-in is enough, the same shape `test_latents.py` uses.
sys.modules.setdefault("folder_paths", types.SimpleNamespace())

# `splice_live` reaches for `media.TARGET_FPS` via a lazy `from ... import
# media` — and the real `media.py` pulls in ComfyUI's own `comfy_api` at
# module level, several layers deeper than a `folder_paths` stub can reach.
# Seeding `sys.modules` with a lightweight stand-in under its *resolved* name
# (`mmc.media`, since `maskseam` loads as `mmc.families.h3.maskseam`) is what
# every other suite that needs one module out of a heavy sibling does instead
# of dragging the whole chain in.
fake_media = types.ModuleType("mmc.media")
fake_media.TARGET_FPS = 24
sys.modules["mmc.media"] = fake_media

maskseam = layout.load("maskseam", package="mmc").maskseam

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# ---- compile.py: seam_mode validation ---------------------------------------
#
# A chained, two-segment timeline, the way the Timeline node compiles one —
# `compiler.timeline_payloads` writes the seam flags onto segment 2's payload,
# `compiler.compile_segment` is what a masked seam is actually validated in.
# `seam` is a plain dict rather than keyword arguments because its keys are the
# blob's own — "continue" is a reserved word and cannot be a Python kwarg.

def second_segment(seam):
    blob = {
        "version": 2, "render": "chained", "prompt": "", "aspect": "16:9",
        "short_edge": 768,
        "segments": [{"duration_s": 6, "prompt": "one"},
                     {"duration_s": 6, "prompt": "two", **seam}],
    }
    return compiler.timeline_payloads(blob)[1]


check("default seam_mode is blend",
      compiler.compile_segment(
          second_segment({"continue": True, "feather": 39})).seam_mode, "blend")
check("mask at the qualifying width compiles",
      compiler.compile_segment(
          second_segment({"continue": True, "feather": 39,
                          "seam_mode": "mask"})).seam_mode, "mask")
check("MASK_SEAM_FEATHER is the grid's own maximum for H3",
      compiler.MASK_SEAM_FEATHER, 39)
check("SEAM_MODES", compiler.SEAM_MODES, ("blend", "mask"))

expect_error("mask needs the blend at its maximum width",
             lambda: compiler.compile_segment(
                 second_segment({"continue": True, "feather": 22,
                                "seam_mode": "mask"})),
             "39")
expect_error("mask on a family with no masked-continuation story",
             lambda: compiler.compile_segment(
                 # 25, not 39: LTX 2.5's own feather grid tops out there, and
                 # the family refusal has to be reached before a width refusal
                 # that is really just a fact about the wrong family's grid.
                 second_segment({"continue": True, "feather": 25,
                                "seam_mode": "mask"}),
                 family="ltx25"),
             "MiniMax H3")
expect_error("an unknown seam_mode is refused",
             lambda: compiler.compile_segment(
                 second_segment({"continue": True, "feather": 39,
                                "seam_mode": "sideways"})),
             "blend")

# `timeline_payloads` itself never carries `seam_mode` onto a payload whose
# seam is not live — it drops `feather` the same way, "only carried when it
# says something" — so the "needs a live seam" refusal in `_check_seam_mode`
# is only reachable through `compile_segment`'s own direct payload shape, the
# one a hand-written blob or another caller could still hand it.

def direct_payload(seam):
    return {"request": {"prompt": "two", "assets": [], "duration_s": 6,
                        "aspect": "16:9", "short_edge": 768}, **seam}


expect_error("mask needs a live seam",
             lambda: compiler.compile_segment(direct_payload({"seam_mode": "mask"})),
             "live seam")

# ---- compile.py: the latent rides the take, then the clip spec -------------

held_take = {"kind": "shot", "hold": True,
             "take": {"filename": "a.mp4 [output]", "duration_s": 6.0,
                      "has_audio": True, "latent": "takes/latent_00001.safetensors"}}
spec = compiler.take_spec(held_take, 0)
check("a take's latent rides onto the clip spec", spec.get("latent"),
      "takes/latent_00001.safetensors")

held_no_latent = {"kind": "shot", "hold": True,
                  "take": {"filename": "a.mp4 [output]", "duration_s": 6.0,
                           "has_audio": True}}
check("an old take with no saved latent carries none",
      "latent" in compiler.take_spec(held_no_latent, 0), False)

clip_with_latent = {"kind": "clip", "filename": "a.mp4 [output]",
                    "duration_s": 6.0, "latent": "takes/latent_00001.safetensors"}
check("clip_spec propagates a rewritten take's latent",
      compiler.clip_spec(clip_with_latent, 0).get("latent"),
      "takes/latent_00001.safetensors")

plain_clip = {"kind": "clip", "filename": "b.mp4", "duration_s": 6.0}
check("a hand-attached clip has no latent to propagate",
      "latent" in compiler.clip_spec(plain_clip, 0), False)


# ---- maskseam.py: fakes for the four MultiRef nodes -------------------------

class FakeSaveLatent:
    FUNCTION = "save"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT", {}),
            "filename_prefix": ("STRING", {"default": "h3_context/clip"}),
            "clip_index": ("INT", {"default": 0, "min": 0, "max": 9999}),
        }}


class FakeLoadLatent:
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent_path": ("STRING", {"default": "h3_context"}),
            "clip_index": ("INT", {"default": 0, "min": 0, "max": 9999}),
        }}


class FakeMaskedContext:
    FUNCTION = "prepare"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT", {}),
            "source_latent": ("LATENT", {}),
            "context_length": ("INT", {"default": 39, "min": 5, "max": 9999}),
            "audio_feather_ticks": ("INT", {"default": 8, "min": 0, "max": 256}),
        }}


class FakeExistingVideoMaskedContext:
    FUNCTION = "prepare"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT", {}),
            "vae": ("VAE", {}),
            "audio_vae": ("VAE", {}),
            "source_frames": ("IMAGE", {}),
            "source_audio": ("AUDIO", {}),
            "source_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0}),
            "context_length": ("INT", {"default": 39, "min": 5, "max": 9999}),
            "crop": (["disabled", "center"], {"default": "disabled"}),
            "audio_feather_ticks": ("INT", {"default": 8, "min": 0, "max": 256}),
        }}


def install(mask=True, existing=True, save=True, load=True):
    NODES.NODE_CLASS_MAPPINGS.clear()
    if mask:
        NODES.NODE_CLASS_MAPPINGS[maskseam.MASK_NODE] = FakeMaskedContext
    if existing:
        NODES.NODE_CLASS_MAPPINGS[maskseam.EXISTING_VIDEO_MASK_NODE] = FakeExistingVideoMaskedContext
    if save:
        NODES.NODE_CLASS_MAPPINGS[maskseam.SAVE_LATENT_NODE] = FakeSaveLatent
    if load:
        NODES.NODE_CLASS_MAPPINGS[maskseam.LOAD_LATENT_NODE] = FakeLoadLatent


class FakeGraph:
    """Enough of `GraphBuilder` to record what was built, in order."""

    def __init__(self):
        self.built = []

    def node(self, node_id, **kwargs):
        self.built.append((node_id, kwargs))

        class Node:
            def out(self, index):
                return f"{node_id}:{index}"

        return Node()


class FakeSegment:
    """Enough of the segment contract's four outs to test the splice."""

    def out(self, index):
        return f"segment:{index}"


class FakeLinks:
    vae = "VAE_LINK"
    audio_vae = "AUDIO_VAE_LINK"


install()

# ---- a missing pack fails loudly, naming itself and the repo ----------------

install(mask=False)
expect_error("a missing mask node names itself and the repo",
             lambda: maskseam.splice_saved(FakeGraph(), FakeSegment(), "SOURCE_LATENT", 39),
             "MiniMaxH3GeneratedAVMaskedContext")
expect_error("...and the repo it ships from",
             lambda: maskseam.splice_saved(FakeGraph(), FakeSegment(), "SOURCE_LATENT", 39),
             "github.com/seitanism")
install()

# ---- save / load --------------------------------------------------------

graph = FakeGraph()
path = maskseam.save_latent(graph, "SAMPLED_LATENT", "renders/h3/H3/takes/H3/latent", 2)
check("save wires the pack's own node", graph.built[0][0], maskseam.SAVE_LATENT_NODE)
check("save is keyed by the card's own number", graph.built[0][1]["clip_index"], 2)
check("save's prefix is the piece's own takes folder, one level deeper",
      graph.built[0][1]["filename_prefix"], "renders/h3/H3/takes/H3/latent")
check("save returns the node's own path output", path, f"{maskseam.SAVE_LATENT_NODE}:0")

graph = FakeGraph()
loaded = maskseam.load_latent(graph, "renders/h3/H3/takes/H3/latent_00002.safetensors")
check("load wires the pack's own node", graph.built[0][0], maskseam.LOAD_LATENT_NODE)
check("load names a file, not a folder", graph.built[0][1]["latent_path"],
      "renders/h3/H3/takes/H3/latent_00002.safetensors")
check("load's clip_index is inert — it names a file already",
      graph.built[0][1]["clip_index"], 0)

# ---- splicing a loaded/live latent -------------------------------------------

graph = FakeGraph()
segment = FakeSegment()
spliced, trim = maskseam.splice_saved(graph, segment, "LOADED_LATENT", 39)
check("splice_saved wires the mask node", graph.built[0][0], maskseam.MASK_NODE)
check("...over the segment's own fresh latent", graph.built[0][1]["latent"], "segment:2")
check("...and the loaded source", graph.built[0][1]["source_latent"], "LOADED_LATENT")
check("...at the requested context length", graph.built[0][1]["context_length"], 39)
check("trim_frames is the mask node's second out", trim, f"{maskseam.MASK_NODE}:1")
check("the spliced latent replaces out(2)", spliced.out(2), f"{maskseam.MASK_NODE}:0")
check("out(0) still answers for the original segment", spliced.out(0), "segment:0")
check("out(1) still answers for the original segment", spliced.out(1), "segment:1")
check("out(3) still answers for the original segment", spliced.out(3), "segment:3")

# ---- splicing a live-encoded window ------------------------------------------

graph = FakeGraph()
segment = FakeSegment()
spliced, trim = maskseam.splice_live(graph, segment, FakeLinks(),
                                     "SOURCE_FRAMES", "SOURCE_AUDIO", 39)
check("splice_live wires the existing-video mask node",
      graph.built[0][0], maskseam.EXISTING_VIDEO_MASK_NODE)
check("...over the segment's own fresh latent", graph.built[0][1]["latent"], "segment:2")
check("...off the piece's own loaders", graph.built[0][1]["vae"], "VAE_LINK")
check("...both of them", graph.built[0][1]["audio_vae"], "AUDIO_VAE_LINK")
check("...the seam's own window", graph.built[0][1]["source_frames"], "SOURCE_FRAMES")
check("...both streams of it", graph.built[0][1]["source_audio"], "SOURCE_AUDIO")
check("source_fps is always Continuity's own 24 fps clip-window rate",
      graph.built[0][1]["source_fps"], 24.0)
check("trim_frames is this node's second out too",
      trim, f"{maskseam.EXISTING_VIDEO_MASK_NODE}:1")
check("the spliced latent replaces out(2) here too",
      spliced.out(2), f"{maskseam.EXISTING_VIDEO_MASK_NODE}:0")

passed("all mask-seam tests passed")
