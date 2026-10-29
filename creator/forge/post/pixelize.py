"""A large picture made into real pixel art at the target size (§3.5, §6.5).

Image models cannot draw a true 16×16 sprite; they can draw a clean, flat,
pixel-art-styled picture at 1024. The conversion is ours, and it is not a
resize: a resize *blends* each cell, and a blend of a black outline and a skin
tone is a colour that is in neither the art nor the palette. So:

1. **Mode of each cell.** The master is cut into the output's cells, and each
   cell takes the colour most of its pixels have — the mean of the pixels in
   the most common bin (12-bit colour), so noise in a flat area does not split
   the vote. A cell is transparent when fewer than half its pixels are visible.
2. **Palette at the target size.** Each cell's colour goes to the nearest
   palette colour after the downscale, not before: quantising the master first
   lets the vote be won by a colour no cell is mostly made of. With no palette
   given, one is cut from all the frames' cell colours together (median cut),
   so a set shares one.
3. **Orphans removed.** A lone pixel whose four neighbours all agree on
   another colour is noise from the vote, and takes their colour.

Ordered dithering is not done in this build.

Everything runs vectorised over cells: a 160×144 background is 23k cells, and
a Python loop over them would make `check` too slow to run after every make.
"""

import numpy as np
from PIL import Image

from .image import hex_colour

_TRANSPARENT = 4096  # the bin key for a cell's invisible pixels, beside 4096 colour bins


def cells(rgba, size):
    """Mode-of-cell colours at `size` (width, height) -> RGBA, alpha 0 or 255."""
    out_w, out_h = size
    height, width = rgba.shape[:2]
    if out_w > width or out_h > height:
        raise ValueError(f"cannot pixelize {width}×{height} up to {out_w}×{out_h}")
    col = np.searchsorted(np.linspace(0, width, out_w + 1).round()[1:], np.arange(width), side="right")
    row = np.searchsorted(np.linspace(0, height, out_h + 1).round()[1:], np.arange(height), side="right")
    cell = (row[:, None] * out_w + col[None, :]).ravel()
    n = out_w * out_h

    pixels = rgba.reshape(-1, 4).astype(np.int64)
    visible = pixels[:, 3] >= 128
    key = ((pixels[:, 0] >> 4) << 8) | ((pixels[:, 1] >> 4) << 4) | (pixels[:, 2] >> 4)
    key[~visible] = _TRANSPARENT

    coverage = np.bincount(cell, weights=visible, minlength=n) / np.bincount(cell, minlength=n)

    group = cell * (_TRANSPARENT + 1) + key
    groups, inverse, counts = np.unique(group, return_inverse=True, return_counts=True)
    group_cell = groups // (_TRANSPARENT + 1)
    group_key = groups % (_TRANSPARENT + 1)
    # The winning bin of each cell: the most pixels among its visible bins.
    counts = np.where(group_key == _TRANSPARENT, -1, counts)
    order = np.lexsort((-counts, group_cell))
    first = np.ones(order.size, bool)
    first[1:] = group_cell[order][1:] != group_cell[order][:-1]
    winners = order[first]

    sums = np.stack([np.bincount(inverse, weights=pixels[:, c], minlength=groups.size) for c in range(3)], 1)
    sizes = np.bincount(inverse, minlength=groups.size)
    colour = np.zeros((n, 3))
    colour[group_cell[winners]] = sums[winners] / sizes[winners, None]

    out = np.zeros((n, 4), np.uint8)
    out[:, :3] = colour.round().clip(0, 255)
    out[:, 3] = np.where(coverage >= 0.5, 255, 0)
    out[out[:, 3] == 0, :3] = 0
    return out.reshape(out_h, out_w, 4)


def palette_of(hexes):
    return np.array([hex_colour(c) for c in hexes], np.float64)


def cut_palette(pictures, count=16):
    """A shared palette for pictures that have none: median cut over every
    visible cell colour of all of them together."""
    colours = np.concatenate([p[p[..., 3] > 0][:, :3] for p in pictures] or [np.zeros((0, 3), np.uint8)])
    if not colours.size:
        return np.zeros((1, 3))
    strip = Image.fromarray(colours.reshape(1, -1, 3).astype(np.uint8), "RGB")
    quantised = strip.quantize(colors=min(count, len(colours)), method=Image.Quantize.MEDIANCUT)
    used = sorted(set(np.asarray(quantised).ravel().tolist()))
    flat = quantised.getpalette()[:3 * (max(used) + 1)]
    return np.array([flat[3 * i:3 * i + 3] for i in used], np.float64)


def nearest(rgb, palette):
    """Index of the nearest palette colour for each pixel, weighted RGB."""
    weights = np.array([0.30, 0.59, 0.11])
    diff = rgb[..., None, :].astype(np.float64) - palette[None, None, :, :]
    return np.argmin((diff ** 2 * weights).sum(-1), axis=-1)


def remove_orphans(indices, visible):
    """A pixel unlike its four neighbours, who agree with each other, joins them."""
    out = indices.copy()
    if min(indices.shape) < 3:
        return out
    centre = indices[1:-1, 1:-1]
    up, down = indices[:-2, 1:-1], indices[2:, 1:-1]
    left, right = indices[1:-1, :-2], indices[1:-1, 2:]
    seen = (visible[1:-1, 1:-1] & visible[:-2, 1:-1] & visible[2:, 1:-1]
            & visible[1:-1, :-2] & visible[1:-1, 2:])
    lonely = seen & (up == down) & (up == left) & (up == right) & (centre != up)
    out[1:-1, 1:-1][lonely] = up[lonely]
    return out


def quantise(picture, palette):
    """A cell picture -> (palette indices, visible mask), orphans removed."""
    visible = picture[..., 3] > 0
    indices = remove_orphans(nearest(picture[..., :3], palette), visible)
    return indices, visible


def to_rgba(indices, visible, palette):
    out = np.zeros(indices.shape + (4,), np.uint8)
    out[..., :3] = palette[indices].round().astype(np.uint8)
    out[..., 3] = np.where(visible, 255, 0)
    out[~visible, :3] = 0
    return out
