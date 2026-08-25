"""What LTX 2.5 is, before anything of LTX 2.5's is imported.

See `families/h3/declare.py` for why this is its own module.
"""

from ... import canvas

ID = "ltx25"
LABEL = "LTX 2.5"

ORDER = 2

PRODUCES = frozenset({"video"})

# No still branch: LTX 2.5 renders video and the pre-stage never reaches for it.
STILL_ARCH = None

# Plain prose straight through Gemma — the substituted description and nothing
# else, which is what an encoder trained on captions should be sent and what
# putting H3's Context-IR in front of it would spoil.
PROMPT_PIPELINE = "plain"

# ComfyUI's own LoRA loader, which is what every family but H3 wants: it is what
# the official workflows use, its key mapping is core's to keep current, and a
# family whose LoRAs it cannot place is a family core will learn about before
# this pack would. LTX 2.5 takes LTX 2.3 LoRAs — Lightricks' own word — and that
# is the path they arrive on.
LORA_STACK = "core"

# The optional head that predicts a shot's length from its own prompt. What the
# seconds pill's "auto" asks, and the slot `models.SLOTS` has to carry a file
# for before it can.
DURATION_HEAD = "duration_head"

# The graph node that is this family's boundary. See `h3/declare.py`. A new id
# rather than a reuse of H3's, because it is a genuinely new node: a different
# conditioning, a different latent, and a fourth output that is a real negative.
SEGMENT_NODE = "MiniMaxLTX25Segment"

# One transformer, in several precisions — a choice of file rather than a choice
# of weights. Nothing routes, so nothing is routed to, no pin may name one, and
# a LoRA on such a piece claims nothing because there is nothing to claim
# between.
ROUTED = ()

# The canvas and duration arithmetic, from Lightricks' own model card and from
# the nodes core ships for the family:
#
# - `multiple=32` and the 8n+1 frame grid are the card's two hard constraints,
#   and they are what `EmptyLTXVLatentVideo` enforces in its widget steps.
# - fps is **conditioning**, not architecture — `LTXVConditioning` carries it
#   into the prompt embedding, so `fps_fixed=False` and the pill is a control.
#   24 rather than `LTXVConditioning`'s own 25: the card's reference pipeline
#   runs at 24.0 and `LTXVDurationPredictor` defaults its clamp to 24.0, which
#   is two statements from Lightricks against one Comfy widget default. One
#   number, pinned here and passed everywhere the family conditions on a rate.
# - 544x960 is the resolution the card's own two-stage example samples at; the
#   x2 spatial upscaler is what takes it to 1088x1920, and that is a pass this
#   pack does not run yet. So the native edge is stage one's, not the pack
#   shot's, and everything above it is honestly off-distribution. The area cap
#   keeps the same shape H3's does (960/544 = 1.76 against 1344/768 = 1.75), so
#   a 21:9 canvas letterboxes the same way at every slider setting.
# - `max_short_edge` is the slider's ceiling rather than a claim: 2048 is where
#   a stage-one render plus the x2 upscaler lands, and the pill warns above the
#   native edge long before here.
# - The trained frame range is the duration head's own default clamp — 1 s to
#   20 s at 24 fps, snapped to the grid — which is Lightricks saying which
#   durations the weights were taught to hold. The seconds range below it is
#   what the pill offers, H3's, and a different statement entirely.
RULES = canvas.Rules(
    multiple=32,
    fps=24,
    fps_fixed=False,
    native_short_edge=544,
    native_max_pixels=544 * 960,
    min_short_edge=256,
    max_short_edge=2048,
    min_ratio=9 / 16,
    max_ratio=21 / 9,
    aspects={
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "1:1": 1.0,
        "3:4": 3 / 4,
        "9:16": 9 / 16,
        "21:9": 21 / 9,
    },
    frame_step=8,
    frame_offset=1,
    trained_min_frames=25,
    trained_max_frames=481,
    min_seconds=1,
    max_seconds=60,
)
