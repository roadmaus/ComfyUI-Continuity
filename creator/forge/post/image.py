"""Pictures as arrays: read, write, fit, split.

Everything in the post chain is RGBA `uint8`. A master without alpha is read as
fully opaque rather than refused here — whether an opaque master is acceptable
is the matte step's question, not the reader's.

Resampling goes through premultiplied alpha (PIL's `RGBa`). Scaling straight
RGBA averages the colour of transparent texels into the edge, which is the dark
halo the bleed step exists to prevent; premultiplying keeps it out at the
source.
"""

import io
import math

import numpy as np
from PIL import Image


def read(path):
    with Image.open(path) as picture:
        return np.asarray(picture.convert("RGBA")).copy()


def png(rgba):
    """An RGBA array -> PNG bytes."""
    out = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(out, "PNG", optimize=True)
    return out.getvalue()


def indexed_png(indices, palette, transparent=None):
    """A palette-index array -> an indexed PNG (`P` mode), palette order kept.

    Order is the point: rgbgfx and png2asset read colour 0 as the lightest
    shade (or as transparent on a sprite), so the writer must not let PIL
    reorder or merge entries.
    """
    picture = Image.fromarray(indices.astype(np.uint8), "P")
    flat = [channel for colour in palette for channel in colour]
    picture.putpalette(flat + [0] * (768 - len(flat)))
    out = io.BytesIO()
    if transparent is None:
        picture.save(out, "PNG", optimize=False)
    else:
        picture.save(out, "PNG", optimize=False, transparency=transparent)
    return out.getvalue()


def hex_colour(text):
    return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))


def opaque(rgba, threshold=128):
    return rgba[..., 3] >= threshold


def resize(rgba, size):
    """Lanczos to `size` (width, height), through premultiplied alpha."""
    width, height = size
    if rgba.shape[1] == width and rgba.shape[0] == height:
        return rgba.copy()
    picture = Image.fromarray(rgba, "RGBA").convert("RGBa")
    picture = picture.resize((width, height), Image.LANCZOS)
    return np.asarray(picture.convert("RGBA")).copy()


def pad_to_aspect(rgba, aspect, anchor="bottom"):
    """Pad with transparency until width / height == `aspect`.

    `anchor` is where the picture sits in the new canvas: "bottom" keeps the
    feet on the floor (sprites, characters), "centre" for everything else.
    The picture is never cropped — a frame that loses a hand to make it fit is
    worse than one with more air around it.
    """
    height, width = rgba.shape[:2]
    if abs(width / height - aspect) < 1e-6:
        return rgba
    if width / height < aspect:
        new_w, new_h = int(round(height * aspect)), height
    else:
        new_w, new_h = width, int(round(width / aspect))
    out = np.zeros((new_h, new_w, 4), np.uint8)
    x = (new_w - width) // 2
    y = new_h - height if anchor == "bottom" else (new_h - height) // 2
    out[y:y + height, x:x + width] = rgba
    return out


def crop_to_aspect(rgba, aspect):
    """Trim equally from both ends of the long side until width / height ==
    `aspect`. For scenes, where the edge is the least of the picture and
    padding would put a border of nothing into the game."""
    height, width = rgba.shape[:2]
    if width / height > aspect:
        keep = int(round(height * aspect))
        x = (width - keep) // 2
        return rgba[:, x:x + keep]
    keep = int(round(width / aspect))
    y = (height - keep) // 2
    return rgba[y:y + keep]


def grid_shape(count):
    """Columns and rows for `count` cells laid out as squarely as possible."""
    columns = math.ceil(math.sqrt(count))
    return columns, math.ceil(count / columns)


def split(rgba, columns, rows):
    """Cut a sheet into `columns × rows` cells, row by row. Cell edges are
    rounded, so a sheet that does not divide evenly loses no pixel."""
    height, width = rgba.shape[:2]
    xs = np.linspace(0, width, columns + 1).round().astype(int)
    ys = np.linspace(0, height, rows + 1).round().astype(int)
    return [rgba[ys[r]:ys[r + 1], xs[c]:xs[c + 1]].copy() for r in range(rows) for c in range(columns)]


def upscale_nearest(rgba, factor):
    return rgba.repeat(factor, axis=0).repeat(factor, axis=1)


def checker(height, width, cell=8):
    """A light grey checkerboard, what transparency is drawn over on a sheet."""
    ys, xs = np.mgrid[:height, :width]
    light = ((ys // cell + xs // cell) % 2).astype(bool)
    out = np.empty((height, width, 3), np.uint8)
    out[light] = (204, 204, 204)
    out[~light] = (240, 240, 240)
    return out


def over(rgb, rgba):
    """`rgba` composited over an opaque `rgb` background -> RGB."""
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * alpha + rgb * (1 - alpha)).round().astype(np.uint8)
