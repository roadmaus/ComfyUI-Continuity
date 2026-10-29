"""A target's budgets, checked on the finished picture (§6.6).

A Game Boy sprite tile holds three colours and transparent; a GBC scene has
eight background palettes of four; GB Studio keeps 192 unique tiles a scene.
A picture that breaks one of these does not fail loudly in the engine — it
comes out wrong, or the build tool refuses it with a message about bytes. So
the check runs here, on the converted picture, and a violation is a sentence
with the place it happened: "tile (3, 2) needs 5 colours".

Each problem is `{problem, code, at?}` — `at` is `[column, row]` in tiles when
the problem has a place — and `overlay` draws them on the picture, because a
person looks for the red box faster than they read a log. Codes are a contract
with agents (`problems.py`) and are never reworded.

Two roles, because the hardware treats them differently: a **sprite** (OAM
objects: colour 0 is transparent, 8 or 16 lines tall, ten to a line) and a
**background** (tile data plus a map: four colours per tile, the unique-tile
budget). The limits themselves are data in `targets.py`.
"""

import numpy as np

from . import tiles as tiling
from .image import checker, over, upscale_nearest


def _tile_colours(picture, tile):
    """Per tile, the set of visible colours, as packed ints. -> rows × cols list."""
    grid = tiling.cut(picture, (tile, tile))
    out = []
    for row in grid:
        line = []
        for cell in row:
            visible = cell[..., 3] > 0
            rgb = cell[..., :3][visible].astype(np.int64)
            line.append(frozenset((rgb[:, 0] << 16 | rgb[:, 1] << 8 | rgb[:, 2]).tolist()))
        out.append(line)
    return out


def palettes_needed(sets, capacity):
    """How many palettes of `capacity` colours the colour sets fit in, packed
    greedily, largest set first. Greedy is not optimal, but it never reports
    fewer than are needed, and it is what the build tools do too."""
    packed = []
    for colours in sorted(sets, key=len, reverse=True):
        for i, palette in enumerate(packed):
            if len(palette | colours) <= capacity:
                packed[i] = palette | colours
                break
        else:
            packed.append(set(colours))
    return len(packed)


def check(picture, limits, role):
    """The problems `picture` (RGBA, at the target size) has against `limits`."""
    problems = []
    if "tile" not in limits:
        return problems
    tile = limits["tile"]
    height, width = picture.shape[:2]
    if width % tile or height % tile:
        problems.append({"problem": f"{width}×{height} is not a whole number of {tile}-pixel tiles",
                         "code": "budget.grid"})
        return problems
    colours = _tile_colours(picture, tile)
    everything = frozenset().union(*(c for line in colours for c in line))
    capacity = limits["sprite_colours"] if role == "sprite" else limits["shades"]
    what = "sprite tile" if role == "sprite" else "tile"
    for r, line in enumerate(colours):
        for c, used in enumerate(line):
            if len(used) > capacity:
                problems.append({"problem": f"{what} ({c}, {r}) needs {len(used)} colours; "
                                            f"it can have {capacity}", "code": "budget.colours", "at": [c, r]})
    if limits.get("rgb555"):
        key = "sprite_palettes" if role == "sprite" else "bg_palettes"
        sets = [used for line in colours for used in line if used]
        need = palettes_needed(sets, capacity)
        if need > limits[key]:
            problems.append({"problem": f"needs {need} palettes of {capacity}; the hardware has {limits[key]}",
                             "code": "budget.palettes"})
    elif len(everything) > capacity:
        problems.append({"problem": f"uses {len(everything)} colours; a {role} can have {capacity}",
                         "code": "budget.shades"})

    if role == "sprite":
        across = -(-width // 8)
        if across > limits["sprites_per_line"]:
            problems.append({"problem": f"{across} sprites side by side; the hardware draws "
                                        f"{limits['sprites_per_line']} on a line", "code": "budget.sprites_per_line"})
        tall = max(h for _, h in limits["sprite_sizes"])
        objects = sum(1 for top in range(0, height, tall) for left in range(0, width, 8)
                      if picture[top:top + tall, left:left + 8, 3].any())
        if objects > limits["sprites"]:
            problems.append({"problem": f"needs {objects} hardware sprites; there are {limits['sprites']}",
                             "code": "budget.sprites"})
        return problems

    unique, _ = tiling.dedupe(picture, (tile, tile), flips=limits.get("flips", False))
    if len(unique) > limits["bg_tiles"]:
        problems.append({"problem": f"{len(unique)} unique tiles; a scene can have {limits['bg_tiles']}",
                         "code": "budget.tiles"})
    if "max_size" in limits and max(width, height) > limits["max_size"]:
        problems.append({"problem": f"{width}×{height} is larger than {limits['max_size']} on a side",
                         "code": "budget.size"})
    if "max_area" in limits and width * height > limits["max_area"]:
        problems.append({"problem": f"{width}×{height} is {width * height} pixels; at most {limits['max_area']}",
                         "code": "budget.size"})
    return problems


def overlay(picture, problems, tile=8, scale=None):
    """The picture, enlarged, over a checkerboard, with each problem's tile
    outlined in red; a problem with no place outlines the whole picture."""
    height, width = picture.shape[:2]
    scale = scale or max(1, min(16, 512 // max(width, height, 1)))
    big = upscale_nearest(picture, scale)
    rgb = over(checker(*big.shape[:2], cell=max(4, scale * 2)), big)
    red = np.array([230, 30, 30], np.uint8)
    for problem in problems:
        if "at" in problem:
            c, r = problem["at"]
            x0, y0, x1, y1 = c * tile * scale, r * tile * scale, (c + 1) * tile * scale, (r + 1) * tile * scale
        else:
            x0, y0, x1, y1 = 0, 0, width * scale, height * scale
        thick = max(1, scale // 4)
        rgb[y0:y0 + thick, x0:x1] = red
        rgb[y1 - thick:y1, x0:x1] = red
        rgb[y0:y1, x0:x0 + thick] = red
        rgb[y0:y1, x1 - thick:x1] = red
    return rgb
