"""Where the face is, how big to crop it, and how hard to re-generate it.

The geometry half of the face pass. Pure: no torch, no numpy, no ComfyUI, no
I/O — the same discipline `canvas.py` keeps, and for the same reason. Every
decision here is a number the sampler will be held to, and a number that can be
argued about in a test without a model, a GPU, or a decoded frame.

`facepass.py` is the other half: it holds the weights, the pixels and the VAE.

What this module is for, in one paragraph: H3 draws a face badly when the head
is a small fraction of the frame, and that is a fact about head-size-in-frame
rather than about resolution — it persists at 720p and above, so no upscaler
reaches it. The fix is to crop the face so it fills a canvas, let H3 re-generate
it at low denoise (low enough that it stays frame-aligned and keeps the sound's
lipsync), and composite it back. Everything below is what that costs in
arithmetic.

Four rules, each of which is a mistake somebody already made:

- **The crop size varies per frame.** One fixed crop is sized by the widest
  frame, so on a push-in the face is still small inside it — on exactly the
  frames that needed the help. `crop_boxes` holds the face at a constant
  fraction of the canvas instead, whatever size it is in the source.
- **The trajectory is smoothed, and size harder than position.** Size jitter
  changes the resample factor every frame, which reads as shimmer rather than as
  movement. Hence `SIZE_WINDOW` well above `POSITION_WINDOW`.
- **Nothing is padded to fit the model's frame grid.** H3 takes 17n+5 frames and
  a trimmed pass rarely is one, so `windows` tiles the pass with legal-length
  windows that all end on real frames — the last one pulled *backward* over
  ground already covered. Repeating a frame to make the count fit would pin
  motion that never happened, which is the same reason `spill.frames` refuses to
  pad a seam.
- **Denoise is scaled per frame by how big the face is.** A shot where somebody
  walks towards the camera has frames with no detail to protect and frames with
  plenty, and one number cannot serve both.
"""

import math

from . import canvas


class FaceError(ValueError):
    """A face pass that cannot be planned from what the pass actually holds."""


# How much of the crop the face itself takes up: the crop is this many face
# heights tall. 3 leaves the head, the shoulders and enough around them for the
# model to know what it is drawing — the context is the point of the crop being
# wider than the paste (see `facepass`, which composites the face box alone).
CROP_FACTOR = 3.0

# The trajectory filters, in frames. Gaussian rather than a boxcar: a boxcar's
# sinc sidelobes leave residual jitter at exactly the frequency this is trying to
# remove. Size is filtered nearly three times as hard as position — see the
# module docstring.
POSITION_WINDOW = 21
SIZE_WINDOW = 51

# The longest window one crop generation covers. The trained length ceiling, so
# a face pass never asks the weights for a duration the render itself would have
# warned about, and a minute-long merged pass is refined in several bites rather
# than one that would not fit anywhere.
WINDOW_CAP = canvas.H3.trained_max_frames

# How much two neighbouring windows share, when a pass needs more than one. One
# temporal packing group: the smallest overlap that is a whole latent frame on
# both sides, so the cross-fade never falls inside one.
WINDOW_OVERLAP = 17

# The per-frame denoise ramp, as multipliers on the pass's own denoise.
#
# A face 30 source pixels tall has no detail worth keeping and wants to be
# synthesised; one 120 pixels tall was already fine and wants to be left nearly
# alone. Between them the strength interpolates. These are the reference
# workflow's numbers, and they are calibrated as a pair with the base denoise —
# moving one without the other is how a render either does nothing or rewrites
# every large face it touches.
STRENGTH_SMALL = 0.8
STRENGTH_LARGE = 0.35
FACE_PX_SMALL = 30.0
FACE_PX_LARGE = 120.0

# Smoothing on the strength curve itself. An abrupt change in denoise between
# neighbouring frames shows up as a texture pop, which is more visible than the
# thing the ramp was buying, so this wants to be generous.
STRENGTH_SMOOTH = 9

# How often the detector actually runs. Every fourth frame: the trajectory is
# low-passed at 21 frames for position and 51 for size, so a detection every 4
# carries every frequency that survives the filter anyway — and the detector is
# a second model's forward pass per frame it runs on, which is the one part of
# this pass whose cost is not H3's.
DETECT_INTERVAL = 4

# How long the detector may find nothing before the paste fades out. Two sample
# intervals: one missed detection is a blink and the crop rides through it on
# the interpolation, a longer blind run is a face that is not there — occluded,
# turned away, out of frame — and pasting a generated one over it would be
# inventing a face rather than repairing one.
BLIND_HOLD = DETECT_INTERVAL * 2
BLIND_FADE = DETECT_INTERVAL * 2

# The paste mask, in **source** pixels. Feather is converted to canvas pixels per
# frame by that frame's magnification (`feather_in_canvas`), so the blend is the
# same physical width on a close-up as on a distant frame — without that, the
# same number is a tenth as wide where the crop was tightest.
PASTE_DILATION = 24
PASTE_FEATHER = 24


def windows(frames, cap=WINDOW_CAP, overlap=WINDOW_OVERLAP):
    """`frames` -> the legal-length windows a face pass covers them with.

    Half-open `(start, end)` pairs, in order, every one of them a length H3
    accepts and every one of them inside the pass. The last window ends on the
    pass's true last frame, which is what makes this tiling rather than padding:
    where the arithmetic does not come out, the answer is to re-generate frames
    that are already covered, never to invent frames that are not.

    The common case is one window and no overlap at all. A lone shot is
    generated at a legal count and nothing trims it, so `frames` is already
    legal; the tiling only appears once a feathered seam has taken a few frames
    off the ends, or once a merged run is longer than one generation.
    """
    frames = int(frames)
    overlap = int(overlap)
    usable = [n for n in canvas.legal_frame_counts(canvas.H3)
              if n <= min(frames, int(cap))]
    if not usable:
        raise FaceError(
            f"this pass is {frames} frames and the shortest generation H3 "
            f"accepts is {canvas.legal_frame_counts(canvas.H3)[0]} — there is nothing "
            f"here to refine")
    if usable[-1] == frames:
        return [(0, frames)]

    # Which legal length to tile with. Not simply the longest that fits: the
    # windows have to *end* on the last frame, so the longest length usually
    # means a final window that overlaps almost entirely with the one before it
    # — 400 frames tiled at 362 samples 724 to deliver 400. What is minimised
    # here is the frames actually sampled, `count * size`, which lands on the
    # shortest length that still covers the pass in the same number of windows.
    best = None
    for size in usable:
        stride = size - overlap
        if stride <= 0:
            continue
        count = max(1, -(-(frames - overlap) // stride))
        if count * size - (count - 1) * overlap < frames:
            continue
        cost = (count * size, count)
        if best is None or cost < best[0]:
            best = (cost, count, size)
    if best is None:                    # pragma: no cover - overlap < shortest legal
        raise FaceError(f"a {frames}-frame pass cannot be tiled with legal windows")

    _, count, size = best
    if count == 1:
        return [(0, size)]
    # Spread evenly between the two ends rather than striding from the front and
    # clamping the last one: every window then shares about the same run with
    # its neighbour, and the first and last sit exactly on the pass's own ends.
    return [(round(index * (frames - size) / (count - 1)),
             round(index * (frames - size) / (count - 1)) + size)
            for index in range(count)]


def detect_frames(frames, interval=DETECT_INTERVAL):
    """Which frames the detector runs on: every `interval`, and always the last.

    The last one explicitly, so the end of a shot is anchored on a real
    detection rather than on the last sample plus three frames of extrapolation
    — a face walking out of frame does most of its moving there.
    """
    frames = int(frames)
    if frames <= 0:
        raise FaceError("a face pass over no frames")
    interval = max(1, int(interval))
    sampled = list(range(0, frames, interval))
    if sampled[-1] != frames - 1:
        sampled.append(frames - 1)
    return sampled


def _iou(a, b):
    """Intersection over union of two `(x, y, w, h)` boxes."""
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(ax2, bx2), min(ay2, by2)
    if right <= left or bottom <= top:
        return 0.0
    overlap = (right - left) * (bottom - top)
    union = a[2] * a[3] + b[2] * b[3] - overlap
    return overlap / union if union > 0 else 0.0


def pick(candidates, previous):
    """One face out of a frame's detections: the one the last frame was about.

    Two people in shot means two boxes, and taking the largest every frame swaps
    between them the moment one turns towards the camera — which would refine
    two half-faces and hold neither. So after the first detection the choice is
    whichever box overlaps the previous one most; only when nothing overlaps at
    all — the first frame, or a genuine cut inside a pass — does size decide.

    `candidates` are `(x, y, w, h)` boxes. Returns one of them, or None.
    """
    if not candidates:
        return None
    if previous is not None:
        best = max(candidates, key=lambda box: _iou(box, previous))
        if _iou(best, previous) > 0:
            return best
    return max(candidates, key=lambda box: box[2] * box[3])


def paste_weights(found, hold=BLIND_HOLD, fade=BLIND_FADE):
    """Per-frame paste opacity, from which frames actually detected a face.

    1 wherever a detection is close by, falling to 0 across a run where the
    detector kept finding nothing. The crop is still computed on those frames —
    `_fill_gaps` interpolates it — but nothing is composited from them, because
    a face that is not there is not a face this pass is allowed to draw.
    """
    seen = [index for index, ok in enumerate(found) if ok]
    if not seen:
        raise FaceError("no face was found anywhere in this pass")
    out = []
    for index in range(len(found)):
        distance = min(abs(index - i) for i in seen)
        if distance <= hold:
            out.append(1.0)
        elif fade <= 0:
            out.append(0.0)
        else:
            out.append(max(0.0, 1.0 - (distance - hold) / float(fade)))
    return out


def smooth(values, window):
    """A trajectory, low-passed with a gaussian kernel and reflected edges.

    `window <= 1` is a no-op, and so is a sequence too short to filter. The
    kernel's sigma is `window / 6`, so the window holds ~3 sigma either side and
    the tails it cuts off are worth nothing.

    Pure Python over a list rather than numpy: this runs once per pass over at
    most a few thousand frames, and it keeps the module importable — and its
    tests runnable — without anything installed.
    """
    values = [float(v) for v in values]
    window = int(window)
    if window <= 1 or len(values) < 3:
        return values
    window = min(window, len(values))
    if window % 2 == 0:
        window += 1
    if window < 3:
        return values

    half = window // 2
    sigma = max(window / 6.0, 0.5)
    kernel = [math.exp(-((i - half) ** 2) / (2.0 * sigma * sigma))
              for i in range(window)]
    total = sum(kernel)
    kernel = [k / total for k in kernel]

    # Reflected, so the ends are filtered against the shot's own movement rather
    # than against an edge that pulls them towards zero.
    padded = ([values[min(half - i, len(values) - 1)] for i in range(half)]
              + values
              + [values[max(len(values) - 2 - i, 0)] for i in range(half)])
    return [sum(padded[i + k] * kernel[k] for k in range(window))
            for i in range(len(values))]


def _fill_gaps(values, found):
    """Detected values with the undetected frames interpolated between them.

    A tracker loses the face for a few frames — a turn, a hand across it — and
    the crop still has to be somewhere on those frames. Linear between the
    neighbours that did detect, held flat past the last one at either end.

    This is about *where to crop*, not about what to paste: `facepass` gives an
    undetected frame no paste weight, so nothing invented here reaches the
    picture. It exists so the crop window does not jump when the track blinks.
    """
    seen = [i for i, ok in enumerate(found) if ok]
    if not seen:
        raise FaceError("no face was found anywhere in this pass")
    out = []
    for index in range(len(values)):
        if found[index]:
            out.append(float(values[index]))
            continue
        before = [i for i in seen if i <= index]
        after = [i for i in seen if i >= index]
        if not before:
            out.append(float(values[after[0]]))
        elif not after:
            out.append(float(values[before[-1]]))
        else:
            low, high = before[-1], after[0]
            span = high - low
            weight = (index - low) / span if span else 0.0
            out.append(float(values[low]) * (1 - weight) + float(values[high]) * weight)
    return out


def crop_boxes(boxes, found, canvas_width, canvas_height, crop_factor=CROP_FACTOR):
    """Per-frame face boxes -> per-frame crop boxes, smoothed and sized.

    `boxes` are `(x, y, w, h)` face rectangles in source pixels, one per frame,
    with `found[i]` saying whether frame i actually detected one. Returns
    `(crops, faces)`: the crop rectangle to sample, and the face rectangle
    expressed *inside the canvas* so the paste mask can be built from it.

    The crop is `crop_factor` face-heights tall, centred on the face, and its
    aspect is the canvas's — a crop of a different shape would be squeezed by
    the resize into a face the model has never seen. It is clamped to nothing:
    a crop that runs off the edge of the frame samples the border, which is what
    `padding_mode="border"` in the warp is for, and clamping it instead would
    drag the face off-centre exactly when it is nearest the edge.

    Everything is float. Rounding the box to whole pixels is, once the
    trajectory is smoothed, the largest remaining source of frame-to-frame
    jitter — so the crop is taken at sub-pixel coordinates and never rounded.
    """
    if len(boxes) != len(found):
        raise FaceError(f"{len(boxes)} boxes for {len(found)} frames")
    if not boxes:
        raise FaceError("a face pass over no frames")

    centres_x = _fill_gaps([b[0] + b[2] / 2.0 for b in boxes], found)
    centres_y = _fill_gaps([b[1] + b[3] / 2.0 for b in boxes], found)
    heights = _fill_gaps([b[3] for b in boxes], found)
    widths = _fill_gaps([b[2] for b in boxes], found)

    centres_x = smooth(centres_x, POSITION_WINDOW)
    centres_y = smooth(centres_y, POSITION_WINDOW)
    heights = smooth(heights, SIZE_WINDOW)
    widths = smooth(widths, SIZE_WINDOW)

    aspect = float(canvas_width) / float(canvas_height)
    crops, faces = [], []
    for cx, cy, fw, fh in zip(centres_x, centres_y, widths, heights):
        crop_h = max(float(fh) * float(crop_factor), 8.0)
        crop_w = crop_h * aspect
        crop_x = cx - crop_w / 2.0
        crop_y = cy - crop_h / 2.0
        crops.append((crop_x, crop_y, crop_w, crop_h))

        # The same face box, in canvas coordinates: where it lands after the
        # crop is resized to the canvas. This is what gets pasted back — the
        # wider crop is context for the sampler, not content for the composite.
        scale_x = float(canvas_width) / crop_w
        scale_y = float(canvas_height) / crop_h
        faces.append(((cx - fw / 2.0 - crop_x) * scale_x,
                      (cy - fh / 2.0 - crop_y) * scale_y,
                      float(fw) * scale_x, float(fh) * scale_y))
    return crops, faces


def face_heights(crops, crop_factor=CROP_FACTOR):
    """The source-pixel face height each crop was sized for.

    The inverse of the sizing rule above, and what the strength ramp is read
    against — the crop is the only per-frame record of how big the face was that
    survives the smoothing.
    """
    return [float(crop[3]) / float(crop_factor) for crop in crops]


def strengths(heights, small=STRENGTH_SMALL, large=STRENGTH_LARGE,
              px_small=FACE_PX_SMALL, px_large=FACE_PX_LARGE,
              smoothing=STRENGTH_SMOOTH):
    """Per-frame denoise multipliers, from per-frame face height in source pixels.

    `small` at `px_small` and below, `large` at `px_large` and above, linear
    between, then smoothed. Absolute pixel thresholds rather than this pass's
    own smallest-to-largest range: a shot that never has a small face should sit
    at the gentle end throughout, where normalising to its own extremes would
    give its least-bad frame the full treatment and rewrite a face that was fine.
    """
    span = float(px_large) - float(px_small)
    out = []
    for height in heights:
        if span <= 0:
            weight = 0.0
        else:
            weight = min(1.0, max(0.0, (float(height) - float(px_small)) / span))
        out.append(float(small) + (float(large) - float(small)) * weight)
    return [min(1.0, max(0.0, value)) for value in smooth(out, smoothing)]


def feather_in_canvas(crop_height, canvas_height, feather=PASTE_FEATHER):
    """A feather given in source pixels -> the same physical width in canvas ones.

    The mask is built at canvas size but the blend is a fact about the finished
    picture, so it is specified there and converted here. A third of the canvas
    is the ceiling: past that the "blend" is most of the paste.
    """
    magnification = float(canvas_height) / max(float(crop_height), 1.0)
    return max(1, min(int(round(float(feather) * magnification)),
                      int(canvas_height) // 3))


def window_weights(spans):
    """Per-window, per-frame paste weights that cross-fade the overlaps.

    `spans` are `windows()`' output. Where two windows cover the same frame, the
    later one ramps in linearly across the shared run while the earlier one ramps
    out, so the two generations of that frame are mixed rather than one of them
    winning at a hard edge. Frames covered once weigh 1.

    Returns one list per window, each as long as its own span.
    """
    weights = [[1.0] * (end - start) for start, end in spans]
    for index in range(1, len(spans)):
        prev_start, prev_end = spans[index - 1]
        start, end = spans[index]
        shared = prev_end - start
        if shared <= 0:
            continue
        for offset in range(shared):
            ramp = (offset + 1) / (shared + 1)
            weights[index][offset] = ramp
            weights[index - 1][start - prev_start + offset] = 1.0 - ramp
    return weights
