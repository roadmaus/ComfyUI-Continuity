"""Canvas, duration and aspect math for MiniMax H3.

Everything in this module is pure: no torch, no ComfyUI, no I/O. The frontend
mirrors these same rules to draw its live readouts (the resolution pill shows
the resolved WxH as you drag), so this file is the single source of truth for
what the sampler will actually receive. Keep it side-effect free and keep the
JS in `web/creator/canvas.js` in step with it.

Two model constraints drive all of it:

- The video latent is a /16 downsample and the DiT wants /32 pixel canvases,
  so both axes snap to multiples of 32.
- Frame counts must satisfy `n % 17 == 5` at 24 fps. There is no such thing as
  a 6.00-second H3 video; the UI shows whole seconds and we land on the nearest
  legal count behind it.
"""

import math

CANVAS_MULTIPLE = 32
FPS = 24

# The open weights are trained with a 768 px short edge and a 768*1344 area cap.
# Both scale together off the resolution slider so the constraint keeps its
# shape at every setting (21:9 stays letterboxed the same way at 384 as at 768).
NATIVE_SHORT_EDGE = 768
NATIVE_MAX_PIXELS = 768 * 1344

MIN_SHORT_EDGE = 384
# The slider's ceiling, not a statement about the weights. `NATIVE_SHORT_EDGE`
# is what the released checkpoints were trained at and anything above it is
# off-distribution — the pill says so from 768 up, and that does not change
# here. What changed is that there is now a reason to go there: the pre-stage's
# H3 branch decodes one latent frame as a still, where the single-image VAE
# holds up to around 3 MP, and a 2K checkpoint is expected. A ceiling the
# hardware and the warning already govern is better than one that has to be
# raised again the day those weights land.
MAX_SHORT_EDGE = 2048

# Official H3 aspect envelope: 21:9 through 9:16.
MIN_RATIO = 9 / 16
MAX_RATIO = 21 / 9

ASPECT_PRESETS = {
    "21:9": 21 / 9,
    "16:9": 16 / 9,
    "4:3": 4 / 3,
    "1:1": 1.0,
    "3:4": 3 / 4,
    "9:16": 9 / 16,
}

# What the open weights were *trained* on, ~5.2 s to ~15.1 s. Not a limit: the
# architecture takes any 17n+5 count, and clips well past the top of this range
# do come out. Kept so the UI can say when you have left the distribution, which
# is a different statement from "you cannot".
TRAINED_MIN_FRAMES = 124
TRAINED_MAX_FRAMES = 362

# What the pill will offer. The floor is a second because below that there is
# barely a shot; the ceiling is a minute because that is about as far as anyone
# has reported getting a coherent single generation, and past it the attention
# cost stops being worth arguing about.
MIN_SECONDS = 1
MAX_SECONDS = 60


def legal_frame_counts():
    """Every frame count the model accepts, ascending, across the offered range.

    17n+5 is an architectural constraint — the temporal packing — so this is the
    real set, not a taste. The trained range is a subset of it and is only used
    to warn.
    """
    return list(range(5, MAX_SECONDS * FPS + 17, 17))


def is_trained_length(frames):
    """Whether a frame count sits inside what the weights actually saw."""
    return TRAINED_MIN_FRAMES <= frames <= TRAINED_MAX_FRAMES


def frames_for_seconds(seconds):
    """Whole UI seconds -> nearest legal frame count.

    Nearest rather than round-up: the worst drift is 0.35 s, where always
    rounding up would cost up to 0.71 s. 8 s is the only whole second under 15
    that lands exactly (192 frames).

    Out-of-range input lands on the nearest offered count rather than raising —
    the set is bounded, so this is where a hand-edited blob gets clamped.
    """
    target = round(float(seconds) * FPS)
    return min(legal_frame_counts(), key=lambda n: (abs(n - target), n))


def seconds_for_frames(frames):
    """The real duration of a frame count. This is what the prompt refiner needs.

    The refiner writes the shot timeline and the `S.SS` keyframe-alignment line
    to fit the video, so it must see the true duration, never the rounded number
    on the pill.
    """
    return frames / FPS


def match_seconds(seconds):
    """A reference's own length -> the card duration that lands nearest it.

    Not `round(seconds)`. Legal frame counts are 17 apart, which is 0.708 s, and
    whole seconds do not cover that grid evenly — some legal counts are not the
    nearest to any whole number of seconds at all. A 6.6 s cue's best match is
    158 frames (6.58 s); rounding to 7 s compiles to 175 (7.29 s), which is two
    thirds of a second late and audible in exactly the case somebody asked for a
    match. So this answers in the model's own units and hands back the real
    duration of the count it picked, which `frames_for_seconds` then round-trips.

    Out-of-range lengths clamp to the pill's range rather than to the frame set:
    a three-minute music cue matches the longest card there is, not a 60-second
    one that the UI cannot then show.
    """
    clamped = min(MAX_SECONDS, max(MIN_SECONDS, float(seconds)))
    return round(seconds_for_frames(frames_for_seconds(clamped)), 2)


def clamp_ratio(ratio):
    """Clamp an aspect ratio into H3's envelope. Returns (ratio, was_clamped)."""
    if ratio < MIN_RATIO:
        return MIN_RATIO, True
    if ratio > MAX_RATIO:
        return MAX_RATIO, True
    return ratio, False


def _snap(value):
    return max(CANVAS_MULTIPLE, int(value / CANVAS_MULTIPLE + 0.5) * CANVAS_MULTIPLE)


def resolve_canvas(ratio, short_edge):
    """(aspect ratio, slider short edge) -> the (width, height) actually generated.

    The area cap scales as the square of the slider, so `short_edge=768` with
    `ratio=16/9` reproduces the native 1344x768 exactly.
    """
    ratio, _ = clamp_ratio(float(ratio))
    short_edge = max(MIN_SHORT_EDGE, min(MAX_SHORT_EDGE, int(short_edge)))
    max_pixels = NATIVE_MAX_PIXELS * (short_edge / NATIVE_SHORT_EDGE) ** 2

    if ratio >= 1.0:
        width, height = short_edge * ratio, float(short_edge)
    else:
        width, height = float(short_edge), short_edge / ratio

    if width * height > max_pixels:
        scale = math.sqrt(max_pixels / (width * height))
        width, height = width * scale, height * scale

    width, height = _snap(width), _snap(height)

    # Snapping rounds each axis independently and can push the area back over
    # the cap. Step the long axis down rather than let the latent exceed what
    # the model was trained to hold.
    while width * height > max_pixels and max(width, height) > CANVAS_MULTIPLE:
        if width >= height:
            width -= CANVAS_MULTIPLE
        else:
            height -= CANVAS_MULTIPLE

    return width, height


def canvas_from_image(image_width, image_height, short_edge):
    """Adaptive canvas for the image modes.

    In I2VA / L2VA / FL2VA the aspect comes from the keyframe, not the ratio
    pill, matching the hosted API's "adaptive" behaviour. The slider still owns
    the scale. Returns (width, height, ratio, was_clamped).
    """
    ratio, clamped = clamp_ratio(image_width / image_height)
    width, height = resolve_canvas(ratio, short_edge)
    return width, height, ratio, clamped


def describe_ratio(ratio):
    """Nearest preset label for a free-form ratio, for the disabled ratio pill."""
    return min(ASPECT_PRESETS.items(), key=lambda kv: abs(kv[1] - ratio))[0]
