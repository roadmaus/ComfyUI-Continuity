"""Game Boy, Game Boy Color and GB Studio: indexed PNGs (§3.7, §9.5).

We do not compile tile data. `rgbgfx`, `png2asset` and GB Studio read PNGs
and do that themselves; the export's job is to hand them a PNG they take as it
is — the right colours, in the right order, on the 8-pixel grid — and the
check's job is to say beforehand when they will refuse it.

- **Game Boy**: an indexed PNG whose palette is the four shades light to dark,
  so an index is a shade number. A sprite's colour 0 is transparent (with a
  `tRNS` entry) and its three shades follow.
- **Game Boy Color**: the same, with every colour the picture uses, already
  rounded to RGB555; rgbgfx packs them into the hardware's palettes, and the
  check has already counted whether they fit.
- **GB Studio**: its own four exact colours, matched by shade, and its
  transparent green on sprites, in the asset folders it reads:
  `assets/sprites/`, `assets/backgrounds/`, `assets/tilesets/`, `assets/ui/`.

Sprites go out as one strip, frames left to right, which is how GB Studio
reads an animated sprite; a background, tile or UI piece as itself.
"""

import numpy as np

from .. import targets
from ..post import image, pixelize

GBSTUDIO_FOLDER = {"sprite": "sprites", "character": "sprites", "icon": "sprites",
                   "background": "backgrounds", "tile": "tilesets", "tileset": "tilesets", "ui": "ui"}


def write(project, built):
    from . import layout

    if built.palette is None:
        raise AssertionError("a Game Boy target always pixelizes")
    packed = layout(built)
    if packed is None:
        return None
    sheet = packed.sheet
    name = built.recipe["name"]
    palette = built.palette.round().astype(int)
    if built.target == "gbstudio":
        studio = [image.hex_colour(c) for c in targets.GBSTUDIO_PALETTE]
        # The built palette is light to dark, so rank is shade; sprites hold
        # shades 0, 1 and 3 (build.palette_for).
        palette = np.array([studio[i] for i in ([0, 1, 3] if built.role == "sprite" else range(4))])
    index = pixelize.nearest(sheet[..., :3], built.palette)  # exact: the sheet holds only palette colours
    colours = [tuple(int(v) for v in c) for c in palette]
    transparent = None
    if built.role == "sprite":
        index = np.where(sheet[..., 3] > 0, index + 1, 0)
        if built.target == "gbstudio":
            colours = [image.hex_colour(targets.GBSTUDIO_TRANSPARENT)] + colours
        else:
            colours = [colours[0]] + colours
            transparent = 0
    elif built.recipe["alpha"]:
        # A background with holes: the hardware has no transparency there, so
        # a hole is shade 0, the colour behind everything.
        index = np.where(sheet[..., 3] > 0, index, 0)
    data = image.indexed_png(index, colours, transparent)
    if built.target == "gbstudio":
        return {f"assets/{GBSTUDIO_FOLDER[built.recipe['kind']]}/{name}.png": data}
    return {f"{name}.png": data}
