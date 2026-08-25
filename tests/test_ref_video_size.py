"""What a reference video is encoded at, and what that costs in the sequence.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_ref_video_size.py

A reference video block is `latent_t` copies of its latent grid, and all of it
rides through every sampling step — at full length one clip is about as long as
the target video itself, which is why 'match' exists for video at all.

Two claims are worth holding down. That 'max' is exactly what shipped before the
setting existed, so no blob changes meaning by being reread. And that 'match' can
never be the more expensive of the two, whatever the clip's shape is against the
generation's — a "cheaper" setting that sometimes is not would be worse than no
setting, because the cost is invisible until the render is already slow.

Skips itself with a message if ComfyUI cannot be imported.
"""

import importlib.util
import math
import os
import sys

import layout
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A stock install is one tree and `--base-directory` defaults to it. Point
# COMFYUI_PATH at the ComfyUI that actually runs, and set COMFYUI_BASE as well
# if the base directory is somewhere else (a Desktop install: it usually is).
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    from comfy_extras.nodes_minimax_h3 import CANVAS_MULTIPLE, adapt_canvas
    return adapt_canvas, CANVAS_MULTIPLE


try:
    adapt_canvas, MULTIPLE = _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

# The pack's module loads *outside* the skip guard: the guard proves the
# environment, and a module of ours that will not import is a failure, not a
# machine allowed to bow out.
# Through `layout.load`: `encode` lives in the family package now, and a module
# flat-loaded under a fake name cannot reach above itself for `latents`/`media`.
encode = layout.load("encode", package="mmcencode").encode

from harness import FAILURES, check, passed


# Source clips across the shapes people actually attach, plus a couple of
# extremes to make the area cap and the native-size clamp both fire.
SOURCES = [
    (1920, 1080), (1280, 720), (3840, 2160),    # landscape
    (1080, 1920), (720, 1280),                  # portrait
    (1024, 1024), (640, 640),                   # square
    (2560, 1080), (1080, 2560),                 # very wide / very tall
    (320, 240), (128, 96),                      # smaller than the reference canvas
]

# Generation canvases the short-edge slider can land on, at 16:9 and 9:16.
CANVASES = [(864, 480), (1024, 576), (1184, 672), (1376, 768),
            (480, 864), (576, 1024), (768, 1376)]


def canvas(source, gen, ref_size):
    return encode.video_canvas(source[0], source[1], gen[0], gen[1], ref_size)


# --- 'max' is unchanged -------------------------------------------------------
#
# Reproduced here from core rather than called through, so that a change to
# either side shows up as a failure instead of agreeing with itself.
for source in SOURCES:
    width, height = adapt_canvas(*source)
    if source[0] * source[1] < width * height:
        snap = lambda v: max(MULTIPLE, round(v / MULTIPLE) * MULTIPLE)  # noqa: E731
        width, height = snap(source[0]), snap(source[1])
    for gen in CANVASES:
        # The generation canvas must not enter into it at all: 'max' is the same
        # answer whatever is being generated.
        check(f"max {source} @ {gen}", canvas(source, gen, "max"), (width, height))

# --- 'match' is never the more expensive one ----------------------------------

for source in SOURCES:
    for gen in CANVASES:
        wide, tall = canvas(source, gen, "max")
        narrow_w, narrow_h = canvas(source, gen, "match")
        if narrow_w * narrow_h > wide * tall:
            FAILURES.append(
                f"match {source} @ {gen}: {narrow_w}x{narrow_h} is larger than max's {wide}x{tall}")
        # Aspect is the clip's own either way — a reference is not letterboxed
        # onto the generation's shape, only scaled down towards its area.
        if abs(math.log((narrow_w / narrow_h) / (wide / tall))) > 0.12:
            FAILURES.append(
                f"match {source} @ {gen}: aspect {narrow_w}x{narrow_h} drifted from {wide}x{tall}")
        # Both axes stay legal latent sizes.
        for name, value in (("w", narrow_w), ("h", narrow_h)):
            if value % MULTIPLE or value < MULTIPLE:
                FAILURES.append(f"match {source} @ {gen}: {name}={value} is not a usable canvas")

# --- and it does something ----------------------------------------------------
#
# The point of the setting. A 1080p clip against the smallest canvas the slider
# offers should be a real cut, not a rounding.
big = canvas((1920, 1080), (864, 480), "max")
small = canvas((1920, 1080), (864, 480), "match")
ratio = (big[0] * big[1]) / (small[0] * small[1])
if ratio < 2.0:
    FAILURES.append(f"match saves little at the small end: {small} vs {big} is only {ratio:.1f}x")

# A clip already smaller than the generation is left alone — there is nothing to
# save by scaling it down, and scaling it up was never on offer.
check("a small clip is untouched by match",
      canvas((320, 240), (1376, 768), "match"), canvas((320, 240), (1376, 768), "max"))

# The rows this actually removes, as the reason any of it is here. A 6 s
# generation is latent_t 47, and a full-length 16:9 reference clip is that many
# copies of its grid.
def rows(size):
    return 47 * (size[0] // 16) * (size[1] // 16)


for gen in [(864, 480), (1024, 576), (1376, 768)]:
    at_max = rows(canvas((1920, 1080), gen, "max"))
    at_match = rows(canvas((1920, 1080), gen, "match"))
    print(f"  6 s 1080p reference @ generation {gen[0]}x{gen[1]}: "
          f"max {at_max:,} rows -> match {at_match:,} rows ({at_max / at_match:.1f}x)")

passed("all reference-video size tests passed")
