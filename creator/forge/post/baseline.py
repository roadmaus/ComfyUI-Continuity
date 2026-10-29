"""A set's frames on one foot line, and where each frame's pivot is (§6.3).

Frames generated one by one land at slightly different heights, and an
animation played from them bobs. Each frame is moved vertically, by whole
pixels, so its lowest visible row sits where the first frame's does. Never
horizontally: a walk cycle's sideways sway is the animation, not an error.

The pivot is stored, not guessed later by whoever imports the sheet: the
middle of the feet — the visible pixels in the lowest band of the figure — on
the foot line. A recipe that names its own pivot (as fractions of the frame)
keeps it.
"""

import numpy as np

from .image import opaque


def bottom(rgba):
    """The lowest row with a visible pixel, or None for an empty frame."""
    rows = np.flatnonzero(opaque(rgba).any(axis=1))
    return int(rows[-1]) if rows.size else None


def shift_down(rgba, dy):
    """Move the picture down `dy` pixels (up when negative), transparent in."""
    if dy == 0:
        return rgba.copy()
    out = np.zeros_like(rgba)
    if dy > 0:
        out[dy:] = rgba[:-dy]
    else:
        out[:dy] = rgba[-dy:]
    return out


def align(frames):
    """Every frame moved so its feet are on the first frame's foot line.

    Frames must share a size; an empty frame is left where it is.
    """
    line = next((b for b in map(bottom, frames) if b is not None), None)
    if line is None:
        return [f.copy() for f in frames]
    out = []
    for frame in frames:
        low = bottom(frame)
        out.append(frame.copy() if low is None else shift_down(frame, line - low))
    return out


def pivot(rgba, fraction=None):
    """The frame's pivot in pixels, (x, y).

    `fraction` is the recipe's own `[x, y]` as fractions of the frame. Without
    it: the centre of the visible pixels in the bottom eighth of the figure,
    on the row just below the feet.
    """
    height, width = rgba.shape[:2]
    if fraction is not None:
        return (round(fraction[0] * width), round(fraction[1] * height))
    mask = opaque(rgba)
    rows = np.flatnonzero(mask.any(axis=1))
    if not rows.size:
        return (width // 2, height)
    top, low = int(rows[0]), int(rows[-1])
    band = max(1, (low - top + 1) // 8)
    xs = np.flatnonzero(mask[low - band + 1:low + 1].any(axis=0))
    return (int(round((xs[0] + xs[-1] + 1) / 2)), low + 1)
