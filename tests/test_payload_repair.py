"""What payload.py's seam repair does to a real PackedLayout.

Runs against core's own `comfy.ldm.minimax.model` — the position rewrite is a
claim about that class's coordinate system, and a stub layout would only prove
the stub agrees with itself. Needs torch but no server and no model weights:
`PackedLayout` is pure geometry.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_payload_repair.py

Skips itself with a message if core cannot be imported.
"""

import importlib.util
import inspect
import os
import sys

import layout
import types

import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    from comfy.ldm.minimax.model import FRAME_RESCALE, PackedLayout
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI core not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)


def _load_payload():
    package = types.ModuleType("mmc")
    package.__path__ = [layout.PY_ROOT]
    sys.modules["mmc"] = package
    spec = importlib.util.spec_from_file_location("mmc.payload", layout.py("payload"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["mmc.payload"] = module
    spec.loader.exec_module(module)
    return module


repair = _load_payload()

from harness import FAILURES, check, passed


TEXT_LEN = 7
AUDIO_STEPS = 5
AUDIO_END = 22

# Two pinned guides (a feathered seam's first two blocks), one image reference,
# and the seam's audio tail end-aligned at pixel frame 22.
#
# A keyframe's latent is a real tensor and the rest are None: since 2026-08-13
# core sizes a guide's cond rows from `latent.shape[2]` and emits none at all
# for a guide that has no latent, so a placeholder there is a layout with no
# guides in it — which is what this test is about. (Older core ignored the
# tensor and gave every guide one frame's rows, which is what this one is, so
# the same fixture reads correctly on both.) Everything else is read as
# geometry (`latent_h`, `ref_audio_t`) and needs no tensor.
_guide = torch.zeros(1, 24, 1, 4, 4)   # [B, C, latent_t, H, W], one latent step
keyframes = [
    {"resolved_frame_index": 0, repair.FRAME_INDEX_KEY: 0, "latent": _guide},
    {"resolved_frame_index": 0, repair.FRAME_INDEX_KEY: 1, "latent": _guide},
]
refs = [
    {"kind": "image", "latent_h": 4, "latent_w": 4, "latent": None},
    {"kind": "audio", "ref_audio_t": AUDIO_STEPS, "audio_latent": None,
     repair.AUDIO_END_KEY: AUDIO_END},
]

layout = PackedLayout(TEXT_LEN, 8, 4, 4, 12, keyframes=keyframes, refs=refs)
payload = {"keyframes": keyframes, "refs": refs, "layout": layout}

# Where the target clip starts: the cursor after the references — the image
# advances it by 1, the audio by its 5 latent steps.
ORIGIN = float(TEXT_LEN + 1 + AUDIO_STEPS)
check("the target origin is read off the layout", repair._target_origin(layout), ORIGIN)

# Where stock puts the guides before the repair runs — which depends on the
# core installed, so it is asked rather than assumed. Until 2026-08-13 keyframe
# anchors counted from `text_len`, the references' coordinate rather than the
# clip's, and that misplacement is what this module was written for. Core now
# starts the cursor after the references and lands on the clip's origin by
# itself. Either way every entry we build carries `resolved_frame_index: 0` and
# its real index under the key below, so stock stacks them all at one anchor and
# the repair is what spreads them.
STOCK_ANCHORS_AFTER_REFS = "frame_count" not in inspect.signature(
    PackedLayout.__init__).parameters
cond = [(a, b) for a, b, kind in layout.segments if kind == "cond"]
check("stock stacks every guide at one anchor",
      {float(layout.position_ids[a, 0]) for a, _ in cond},
      {ORIGIN if STOCK_ANCHORS_AFTER_REFS else float(TEXT_LEN)})

repair._reposition(layout, payload)

for index, (a, b) in enumerate(cond):
    want = ORIGIN + FRAME_RESCALE * index
    times = {float(t) for t in layout.position_ids[a:b, 0]}
    check(f"guide {index} lands at the clip's pixel frame {index}", times, {want})

# The audio tail: 5 latent steps ending at pixel frame 22 of the clip, so its
# start is that instant minus the steps, each one time unit. Channel-major
# stereo repeats the run once per channel.
audio_seg = [(a, b) for a, b, kind in layout.segments if kind == "ref_audio"][0]
a, b = audio_seg
start = ORIGIN + FRAME_RESCALE * AUDIO_END - AUDIO_STEPS
check("the audio tail is end-aligned on the clip's timeline",
      [float(t) for t in layout.position_ids[a:b, 0]],
      [start + k for k in range(AUDIO_STEPS)] * 2)

# Idempotent: the layout is shared across sampling steps and must be rewritten
# exactly once — a second pass would add the origin again.
before = layout.position_ids.clone()
repair._reposition(layout, payload)
check("a second pass changes nothing", bool((layout.position_ids == before).all()), True)

# An unkeyed keyframe is stock behaviour and is left exactly where stock put
# it: this module is a repair, not a relayout.
plain = [{"resolved_frame_index": 0, "latent": _guide}]
untouched = PackedLayout(TEXT_LEN, 8, 4, 4, 12, keyframes=plain)
repair._reposition(untouched, {"keyframes": plain, "refs": []})
a, b, kind = [s for s in untouched.segments if s[2] == "cond"][0]
check("an unkeyed keyframe keeps stock's coordinate",
      float(untouched.position_ids[a, 0]), float(TEXT_LEN))

# Without references the clip starts at text_len, so a keyed frame-0 guide
# lands exactly where stock's frame-0 anchor is — the classic seam and the
# repaired one agree wherever both are defined.
keyed = [{"resolved_frame_index": 0, repair.FRAME_INDEX_KEY: 0, "latent": _guide}]
bare = PackedLayout(TEXT_LEN, 8, 4, 4, 12, keyframes=keyed)
repair._reposition(bare, {"keyframes": keyed, "refs": []})
a, b, kind = [s for s in bare.segments if s[2] == "cond"][0]
check("without references the repair reproduces stock exactly",
      float(bare.position_ids[a, 0]), float(TEXT_LEN))

# The latent list, rebuilt in layout order: keyframes first, then reference
# images — the order the forward walks its one running offset in.
built = repair._rebuild({
    "keyframes": [{"latent": "kf1"}, {"latent": "kf2"}],
    "refs": [{"kind": "audio", "audio_latent": "aud"}, {"kind": "image", "latent": "ref1"}],
})
check("cond_video_latents is keyframes then reference images",
      built, ["kf1", "kf2", "ref1"])

passed("all payload-repair tests passed")
