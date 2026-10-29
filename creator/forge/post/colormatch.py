"""A set's frames brought to its first frame's colours (§6.4).

Frames and views made one render at a time drift: a little warmer here, a
little darker there, and a sprite flickers when it plays. Each frame's visible
pixels are histogram-matched to the first frame's, a channel at a time: every
value is moved to the value at the same quantile in the reference. Transparent
texels are not counted on either side — a frame with more air around it is
not a darker frame.

It corrects drift, not difference: a frame that is really meant to be another
colour (a hit flash) should be outside the set, or the recipe should leave
`colormatch` out of its post list.
"""

import numpy as np

from .image import opaque


def _quantiles(values):
    counts = np.bincount(values, minlength=256).astype(np.float64)
    return np.cumsum(counts) / counts.sum()


def match(frame, reference):
    """`frame` with its visible colours matched to `reference`'s."""
    mine, theirs = opaque(frame), opaque(reference)
    if not mine.any() or not theirs.any():
        return frame.copy()
    out = frame.copy()
    for channel in range(3):
        source = frame[..., channel][mine]
        target = reference[..., channel][theirs]
        cdf_source = _quantiles(source)
        cdf_target = _quantiles(target)
        # For each source level, the lowest target level whose quantile
        # reaches it. A search, not an interpolation: a CDF is flat across
        # every level nobody uses, and interpolating along a flat run picks
        # a level from nowhere.
        lookup = np.searchsorted(cdf_target, cdf_source - 1e-9).clip(0, 255)
        out[..., channel][mine] = lookup[source].astype(np.uint8)
    return out


def match_set(frames):
    if len(frames) < 2:
        return [f.copy() for f in frames]
    return [frames[0].copy()] + [match(f, frames[0]) for f in frames[1:]]
