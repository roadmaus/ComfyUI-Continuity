"""A picture cut into tiles, de-duplicated, and the map that rebuilds it.

What a tile engine stores is not the picture but its unique tiles plus a map
of which goes where. Counting the unique tiles is the Game Boy's budget
(192 in a GB Studio scene, §3.7); the tiles and the map are what Tiled and
Godot are given. On targets whose hardware can flip a tile (GBC, Tiled,
Godot) a tile and its mirror image are one tile, used flipped.
"""

import numpy as np

FLIP_X = 1
FLIP_Y = 2


def cut(picture, tile):
    """`picture` (H × W × C) -> array rows × columns × th × tw × C.
    The picture must be a whole number of tiles."""
    tw, th = tile
    height, width = picture.shape[:2]
    if width % tw or height % th:
        raise ValueError(f"{width}×{height} is not a whole number of {tw}×{th} tiles")
    rows, columns = height // th, width // tw
    return picture.reshape(rows, th, columns, tw, -1).swapaxes(1, 2)


def dedupe(picture, tile, flips=False):
    """-> (unique tiles in first-seen order, map rows × columns of
    (tile index, flip bits))."""
    grid = cut(picture, tile)
    rows, columns = grid.shape[:2]
    seen = {}
    unique = []
    index = np.zeros((rows, columns), np.int64)
    flip = np.zeros((rows, columns), np.int64)
    for r in range(rows):
        for c in range(columns):
            cell = grid[r, c]
            variants = [(0, cell)]
            if flips:
                variants += [(FLIP_X, cell[:, ::-1]), (FLIP_Y, cell[::-1]), (FLIP_X | FLIP_Y, cell[::-1, ::-1])]
            for bits, variant in variants:
                found = seen.get(variant.tobytes())
                if found is not None:
                    index[r, c], flip[r, c] = found, bits
                    break
            else:
                seen[cell.tobytes()] = len(unique)
                index[r, c] = len(unique)
                unique.append(cell.copy())
    return unique, np.stack([index, flip], -1)
