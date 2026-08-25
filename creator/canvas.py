"""Canvas, duration and aspect math, parameterised by family.

Everything in this module is pure: no torch, no ComfyUI, no I/O. The frontend
mirrors these same rules to draw its live readouts (the resolution pill shows
the resolved WxH as you drag), so this file is the single source of truth for
what the sampler will actually receive. Keep it side-effect free and keep the
JS in `web/creator/canvas.js` in step with it.

The *math* is family-neutral — snap to a grid, follow a ratio, cap an area,
land on a legal frame count — and every function below takes the `Rules` that
drive it. The *numbers* are a family's: `H3` is MiniMax H3's set, declared
here and served to the frontend through the family's manifest. `LTX25` is LTX
2.5's — fps carried as conditioning rather than fixed, an 8n+1 frame packing
instead of 17n+5 — and it passes through the same functions unchanged, which
is the whole claim this parameterisation makes.

Two model constraints drive H3's numbers:

- The video latent is a /16 downsample and the DiT wants /32 pixel canvases,
  so both axes snap to multiples of 32.
- Frame counts must satisfy `n % 17 == 5` at 24 fps. There is no such thing as
  a 6.00-second H3 video; the UI shows whole seconds and we land on the nearest
  legal count behind it.

**Every function here takes its rules and none of them defaults.** They used to
default to `H3`, and there were module constants beside them — `canvas.FPS`,
`canvas.NATIVE_SHORT_EDGE`, `canvas.FEATHER_GRID` — carrying the same numbers
under historic names. Both were how the one family this pack shipped reached its
own arithmetic without saying so, and both are exactly the wrong shape for a
second: a caller that forgot to thread the piece's rules through did not fail,
it silently ran H3's grid over somebody else's weights. A required argument is
the only version of this that fails loudly, and `canvas.H3` spelled out at an
H3-owned call site is a leak anyone can grep for.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    """One family's canvas and duration constraints.

    `frame_step`/`frame_offset` say which frame counts the architecture
    accepts (`step*n + offset`); the trained range is the subset the weights
    actually saw, kept apart because "off-distribution" is a different
    statement from "illegal". `fps_fixed` says whether the rate is a property
    of the weights (H3) or conditioning the family takes (LTX).
    """

    multiple: int              # both canvas axes snap to this
    fps: int
    fps_fixed: bool
    native_short_edge: int     # what the weights were trained at
    native_max_pixels: int     # the trained area cap, at the native edge
    min_short_edge: int
    max_short_edge: int
    min_ratio: float
    max_ratio: float
    aspects: dict              # label -> ratio, in the popover's order
    frame_step: int
    frame_offset: int
    trained_min_frames: int
    trained_max_frames: int
    min_seconds: int
    max_seconds: int


# MiniMax H3's rules. The provenance of every number:
#
# - 768 px short edge and a 768*1344 area cap are what the open weights are
#   trained with; both scale together off the resolution slider so the
#   constraint keeps its shape at every setting (21:9 stays letterboxed the
#   same way at 384 as at 768).
# - `max_short_edge` is the slider's ceiling, not a statement about the
#   weights — everything above the native edge is off-distribution and the
#   pill says so. There is a reason to offer it anyway: the pre-stage's H3
#   branch decodes one latent frame as a still, where the single-image VAE
#   holds up to around 3 MP, and a 2K checkpoint is expected. A ceiling the
#   hardware and the warning already govern is better than one that has to be
#   raised again the day those weights land.
# - The 9:16..21:9 ratio envelope is the official H3 aspect range.
# - The trained frame range is ~5.2 s to ~15.1 s. Not a limit: the
#   architecture takes any 17n+5 count and clips well past the top do come
#   out; the pair exists so the UI can say when you have left the
#   distribution, which is a different statement from "you cannot".
# - The seconds range is what the pill offers: below a second there is barely
#   a shot, and a minute is about as far as anyone has reported getting a
#   coherent single generation — past it the attention cost stops being worth
#   arguing about.
H3 = Rules(
    multiple=32,
    fps=24,
    fps_fixed=True,
    native_short_edge=768,
    native_max_pixels=768 * 1344,
    min_short_edge=384,
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
    frame_step=17,
    frame_offset=5,
    trained_min_frames=124,
    trained_max_frames=362,
    min_seconds=1,
    max_seconds=60,
)


# LTX 2.5's rules. The provenance of every number, from Lightricks' own model
# card and from the nodes core ships for the family:
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
LTX25 = Rules(
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


# Every family's rules, under the id the registry knows it by. The registry
# says which families exist; this says what each one's arithmetic is, and
# `compile.rules_of` is what looks a piece's family up in it. A still-only
# family has no entry — there is no duration and no frame grid to have one for.
RULES = {"h3": H3, "ltx25": LTX25}


def legal_frame_counts(rules):
    """Every frame count the model accepts, ascending, across the offered range.

    `step*n + offset` is an architectural constraint — the temporal packing —
    so this is the real set, not a taste. The trained range is a subset of it
    and is only used to warn.
    """
    return list(range(rules.frame_offset,
                      rules.max_seconds * rules.fps + rules.frame_step,
                      rules.frame_step))


def feather_grid(rules):
    """The seam widths a family can inherit as motion. -> a tuple, ascending.

    A feathered seam hands the pass in front's last run to the next one as a
    multi-frame guide, so the run has to be a length the family's temporal
    packing encodes standalone — which is the same `step*n + offset` grid a
    whole generation's frame count lands on, for the same reason: the video
    VAE's cycle. A run ending short of a boundary pins frames that stop before
    the source's last one, and the join jumps by the difference.

    The single frame is always offered — the classic seam, and on an 8n+1
    family it is the grid's own first member — and three widths above it is
    what the picker has room for. H3's set is (1, 5, 22, 39), which is 0.21 s,
    0.92 s and 1.63 s of inherited motion; LTX 2.5's is (1, 9, 17, 25).

    That difference is not cosmetic. `LTXVAddGuide` crops a guide to the
    nearest 8n+1 itself, so H3's 5-frame blend handed to LTX reaches the model
    as a *single* frame while the strip goes on subtracting five — a seam that
    silently stops being feathered, with nothing in the log.
    """
    return (1, *[n for n in legal_frame_counts(rules) if n > 1][:3])


def is_trained_length(frames, rules):
    """Whether a frame count sits inside what the weights actually saw."""
    return rules.trained_min_frames <= frames <= rules.trained_max_frames


def frames_for_seconds(seconds, rules):
    """Whole UI seconds -> nearest legal frame count.

    Nearest rather than round-up: the worst drift is 0.35 s, where always
    rounding up would cost up to 0.71 s. 8 s is the only whole second under 15
    that lands exactly (192 frames).

    Out-of-range input lands on the nearest offered count rather than raising —
    the set is bounded, so this is where a hand-edited blob gets clamped.
    """
    target = round(float(seconds) * rules.fps)
    return min(legal_frame_counts(rules), key=lambda n: (abs(n - target), n))


def seconds_for_frames(frames, rules):
    """The real duration of a frame count. This is what the prompt refiner needs.

    The refiner writes the shot timeline and the `S.SS` keyframe-alignment line
    to fit the video, so it must see the true duration, never the rounded number
    on the pill.
    """
    return frames / rules.fps


def match_seconds(seconds, rules):
    """A reference's own length -> the card duration that lands nearest it.

    Not `round(seconds)`. Legal frame counts are `frame_step` apart — 0.708 s
    for H3 — and whole seconds do not cover that grid evenly; some legal
    counts are not the nearest to any whole number of seconds at all. A 6.6 s
    cue's best match is 158 frames (6.58 s); rounding to 7 s compiles to 175
    (7.29 s), which is two thirds of a second late and audible in exactly the
    case somebody asked for a match. So this answers in the model's own units
    and hands back the real duration of the count it picked, which
    `frames_for_seconds` then round-trips.

    Out-of-range lengths clamp to the pill's range rather than to the frame
    set: a three-minute music cue matches the longest card there is, not a
    60-second one that the UI cannot then show.
    """
    clamped = min(rules.max_seconds, max(rules.min_seconds, float(seconds)))
    return round(seconds_for_frames(frames_for_seconds(clamped, rules), rules), 2)


def clamp_ratio(ratio, rules):
    """Clamp an aspect ratio into the family's envelope. -> (ratio, was_clamped)."""
    if ratio < rules.min_ratio:
        return rules.min_ratio, True
    if ratio > rules.max_ratio:
        return rules.max_ratio, True
    return ratio, False


def _snap(value, rules):
    grid = rules.multiple
    return max(grid, int(value / grid + 0.5) * grid)


def resolve_canvas(ratio, short_edge, rules):
    """(aspect ratio, slider short edge) -> the (width, height) actually generated.

    The area cap scales as the square of the slider, so `short_edge=768` with
    `ratio=16/9` reproduces H3's native 1344x768 exactly.
    """
    ratio, _ = clamp_ratio(float(ratio), rules)
    short_edge = max(rules.min_short_edge,
                     min(rules.max_short_edge, int(short_edge)))
    max_pixels = rules.native_max_pixels * (short_edge / rules.native_short_edge) ** 2

    if ratio >= 1.0:
        width, height = short_edge * ratio, float(short_edge)
    else:
        width, height = float(short_edge), short_edge / ratio

    if width * height > max_pixels:
        scale = math.sqrt(max_pixels / (width * height))
        width, height = width * scale, height * scale

    width, height = _snap(width, rules), _snap(height, rules)

    # Snapping rounds each axis independently and can push the area back over
    # the cap. Step the long axis down rather than let the latent exceed what
    # the model was trained to hold.
    while width * height > max_pixels and max(width, height) > rules.multiple:
        if width >= height:
            width -= rules.multiple
        else:
            height -= rules.multiple

    return width, height


def canvas_from_image(image_width, image_height, short_edge, rules):
    """Adaptive canvas for the image modes.

    In I2VA / L2VA / FL2VA the aspect comes from the keyframe, not the ratio
    pill, matching the hosted API's "adaptive" behaviour. The slider still owns
    the scale. Returns (width, height, ratio, was_clamped).
    """
    ratio, clamped = clamp_ratio(image_width / image_height, rules)
    width, height = resolve_canvas(ratio, short_edge, rules)
    return width, height, ratio, clamped


def describe_ratio(ratio, rules):
    """Nearest preset label for a free-form ratio, for the disabled ratio pill."""
    return min(rules.aspects.items(), key=lambda kv: abs(kv[1] - ratio))[0]
