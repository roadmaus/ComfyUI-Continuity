"""What LTX 2.5 is, before anything of LTX 2.5's is imported.

See `families/h3/declare.py` for why this is its own module.
"""

from ... import canvas

ID = "ltx25"
LABEL = "LTX 2.5"

ORDER = 2

PRODUCES = frozenset({"video"})

# What this family's files are called under `continuity/renders/ltx25/`. See
# `h3/declare.py` for why the stem is declared rather than derived.
OUTPUT_STEM = "LTX25"

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

# The IC-LoRA that makes a reference mean anything on this family, and the slot
# that has to carry a file for it. Lightricks' `Ingredients` adapter: it reads a
# composite reference sheet — characters, props and locations laid out on black —
# and holds what is on it consistent through the generated video. That is this
# family's answer to H3's ordinal citations, and the open question the grammar's
# docstring used to record.
INGREDIENTS = "ic_lora"

# Black, because the sheet the adapter was trained on is black. Not a taste:
# Lightricks' own description of the Ingredients reference sheet is panels "on a
# black background", so any other field is a sheet unlike the ones it learned to
# read. See `creator/cutout.py`.
REF_BACKDROP = 0.0

# Whether a piece on this family cuts its references out unless told otherwise.
# **On.** A reference here becomes a panel of a composite sheet, and a panel that
# still carries the room it was photographed in is a sheet made of photographs
# rather than of ingredients. Nothing saved is changed by the default: this
# family refused every attachment until the sheet existed, so there is no
# LTX 2.5 piece with references on it that predates the choice.
CUTOUT_DEFAULT = True

# **The distilled transformer's own sigma curve, and it is a constant rather
# than a schedule.** Both of Lightricks' 2.5 workflows and ComfyUI's own
# `video_ltx2_5_i2v.json` template feed these numbers through `ManualSigmas`,
# and neither emits `LTXVScheduler` or `ModelSamplingLTXV` at all. That is the
# whole difference between a step-distilled checkpoint and a full one: the
# distillation was done *against this trajectory*, so a curve of the same length
# through the same endpoints is not a substitute for it. `LTXVScheduler(8, 2.05,
# 0.95, stretch, 0.1)` over a 960x544x121 latent gives
#
#     1.0, 0.9779, 0.9486, 0.9083, 0.8489, 0.753, 0.5718, 0.1, 0.0
#
# — an even descent that jumps 0.572 -> 0.1, skipping the 0.42 -> 0 stretch
# where the picture's detail resolves. The trained curve below instead spends
# four of its eight steps almost in place at the top and does the denoise in
# four large drops. It is not a tuning difference; sampling off it is what makes
# an LTX 2.5 render come out a magnitude softer than the same prompt through
# Lightricks' own API.
#
# The dev transformer is the case `LTXVScheduler` was written for, and the row's
# `schedule` field is which of the two a piece is on — see `sampling.py`.
DISTILLED_SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"

# The second stage's, and it is the same curve read differently: 0.85 is where
# the upscaled latent re-enters, and the three values after it are the trained
# tail above, unchanged. So a partial pass is expressed here as its own constant
# rather than as a fraction of the first — there is no `denoise` to take of a
# curve whose every value the distillation fixed.
DISTILLED_REFINE_SIGMAS = "0.85, 0.7250, 0.4219, 0.0"

# What both official workflows select, in both stages. Ancestral rather than
# plain euler: the noise each step adds back is part of what eight steps were
# distilled against.
DISTILLED_SAMPLER = "euler_ancestral"

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
