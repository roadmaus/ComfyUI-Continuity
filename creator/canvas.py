"""Canvas, duration and aspect math, parameterised by family.

Everything in this module is pure: no torch, no ComfyUI, no I/O — and no
family. The frontend mirrors these same rules to draw its live readouts (the
resolution pill shows the resolved WxH as you drag), so this file is the single
source of truth for what the sampler will actually receive. Keep it side-effect
free and keep the JS in `web/creator/canvas.js` in step with it.

The *math* is family-neutral — snap to a grid, follow a ratio, cap an area,
land on a legal frame count — and every function below takes the `Rules` that
drive it. The *numbers* are a family's and live with the family, in its
`declare.py`: H3's 17n+5 grid at a fixed 24 fps, LTX 2.5's 8n+1 with the rate
carried as conditioning. Both pass through these functions unchanged, which is
the whole claim this parameterisation makes, and `registry.rules(family)` is
where a caller gets the set it needs.

They were declared here, two `Rules` literals and a table mapping ids to them,
which meant a new family edited this file to say something about itself that
this file has no other use for. `Rules` is the contract; the numbers are not
its business.

**Every function here takes its rules and none of them defaults.** They used to
default to `H3`, and there were module constants beside them — `canvas.FPS`,
`canvas.NATIVE_SHORT_EDGE`, `canvas.FEATHER_GRID` — carrying the same numbers
under historic names. Both were how the one family this pack shipped reached its
own arithmetic without saying so, and both are exactly the wrong shape for a
second: a caller that forgot to thread the piece's rules through did not fail,
it silently ran H3's grid over somebody else's weights. A required argument is
the only version of this that fails loudly, and a family's own
`declare.RULES` spelled out at a call site that belongs to it is a leak anyone
can grep for.
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
