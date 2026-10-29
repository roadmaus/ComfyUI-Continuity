"""Game Forge's post-steps, one at a time, on pictures small enough to reason about.

    python3 tests/test_forge_post.py

Each step in `creator/forge/post/` is a pure function of arrays (spec §6), so
each is pinned here on a picture whose right answer can be worked out by hand:
a bleed that must not touch alpha, a mode-of-cell vote that must not blend, a
tile budget that must count a mirrored tile once on hardware that flips.

Needs numpy and PIL (the post-steps are arithmetic); no ComfyUI.
"""

import importlib
import os
import sys
import types

import layout
from harness import check, skip

try:
    import numpy as np
except ImportError:
    skip("numpy is not installed")

package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
image = importlib.import_module("forgepkg.post.image")
bleed = importlib.import_module("forgepkg.post.bleed")
baseline = importlib.import_module("forgepkg.post.baseline")
colormatch = importlib.import_module("forgepkg.post.colormatch")
pixelize = importlib.import_module("forgepkg.post.pixelize")
constraints = importlib.import_module("forgepkg.post.constraints")
atlas = importlib.import_module("forgepkg.post.atlas")
tiles = importlib.import_module("forgepkg.post.tiles")
targets = importlib.import_module("forgepkg.targets")


def blank(h, w):
    return np.zeros((h, w, 4), np.uint8)


# ---- bleed ------------------------------------------------------------------------

pic = blank(16, 16)
pic[4:8, 4:8] = (200, 50, 10, 255)
pic[4:8, 8:12] = (10, 50, 200, 255)
out = bleed.bleed(pic)
check("bleed leaves alpha alone", np.array_equal(out[..., 3], pic[..., 3]), True)
check("and visible texels alone", np.array_equal(out[pic[..., 3] > 0], pic[pic[..., 3] > 0]), True)
check("a texel left of the red takes red", tuple(out[5, 0, :3]), (200, 50, 10))
check("a texel right of the blue takes blue", tuple(out[5, 15, :3]), (10, 50, 200))
check("no transparent texel is left black", int((out[..., :3].sum(-1) == 0).sum()), 0)
solid = np.full((4, 4, 4), 77, np.uint8)
solid[..., 3] = 255
check("an opaque picture is unchanged", np.array_equal(bleed.bleed(solid), solid), True)

# ---- baseline and pivot ---------------------------------------------------------

frames = []
for drop in (0, 3, -2):
    f = blank(32, 16)
    f[10 + drop:24 + drop, 4:12] = 255
    frames.append(f)
aligned = baseline.align(frames)
check("every frame's feet on the first frame's line", [baseline.bottom(f) for f in aligned], [23, 23, 23])
check("moved only vertically", [int(np.flatnonzero(f[..., 3].any(0))[0]) for f in aligned], [4, 4, 4])
check("the pivot is the middle of the feet, under them", baseline.pivot(aligned[0]), (8, 24))
check("a recipe's pivot is kept", baseline.pivot(aligned[0], [0.5, 0.25]), (8, 8))
check("an empty frame pivots at the bottom centre", baseline.pivot(blank(10, 10)), (5, 10))

# ---- colour match ---------------------------------------------------------------

ref = blank(4, 4)
ref[:2] = (100, 100, 100, 255)
ref[2:] = (200, 200, 200, 255)
warm = ref.copy()
warm[:2, :, :3] = (110, 95, 90)
warm[2:, :, :3] = (215, 190, 185)
warm[0, 0, 3] = 0
matched = colormatch.match(warm, ref)
check("drift is matched back to the reference", tuple(matched[3, 3, :3]), (200, 200, 200))
check("on both levels", tuple(matched[1, 1, :3]), (100, 100, 100))
check("a transparent texel is not counted or changed", tuple(matched[0, 0]), tuple(warm[0, 0]))

# ---- pixelize ---------------------------------------------------------------------

big = blank(64, 64)
big[..., :3] = (250, 250, 250)
big[..., 3] = 255
big[:32, :32, :3] = (10, 10, 10)
noise = np.random.default_rng(0).integers(-3, 4, big.shape[:2] + (3,))
big[..., :3] = np.clip(big[..., :3].astype(int) + noise, 0, 255)
big[0:3, 0:3, :3] = (255, 0, 0)  # a minority inside a cell
small = pixelize.cells(big, (4, 4))
check("the mode wins, never a blend", tuple(small[0, 0, :3]) in [(9, 9, 9), (10, 10, 10), (11, 11, 11)], True)
check("a light cell stays light", int(small[3, 3, 0]) >= 245, True)
holey = big.copy()
holey[:, 32:, 3] = 0
holey[:, 32:40, 3] = 255
cells = pixelize.cells(holey, (4, 4))
check("a cell under half covered is transparent", int(cells[0, 3, 3]), 0)
check("a cell half covered is visible", int(cells[0, 2, 3]), 255)
palette = pixelize.palette_of(["#000000", "#ffffff"])
indices, visible = pixelize.quantise(small, palette)
check("colours go to the nearest palette entry", indices.tolist(),
      [[0, 0, 1, 1], [0, 0, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]])
lonely = np.zeros((5, 5), int)
lonely[2, 2] = 1
check("an orphan joins its neighbours", int(pixelize.remove_orphans(lonely, np.ones((5, 5), bool))[2, 2]), 0)
edge = np.zeros((5, 5), int)
edge[2, 2] = 1
edge[2, 3] = 1
check("a pair is not an orphan", int(pixelize.remove_orphans(edge, np.ones((5, 5), bool))[2, 2]), 1)
cut = pixelize.cut_palette([small], 2)
check("a palette cut from the cells has the colours asked for", len(cut), 2)

# ---- tiles and the budgets --------------------------------------------------------

scene = blank(8, 24)
scene[..., 3] = 255
scene[:, :8, :3] = 0
scene[0, 0, :3] = 255                      # tile 0: a dot top-left
scene[:, 8:16] = scene[:, :8][:, ::-1]     # tile 1: tile 0 mirrored
scene[:, 16:24] = scene[:, :8]             # tile 2: tile 0 again
unique, tile_map = tiles.dedupe(scene, (8, 8))
check("a repeated tile is stored once", len(unique), 2)
unique, tile_map = tiles.dedupe(scene, (8, 8), flips=True)
check("with flips, a mirrored tile is the same tile", len(unique), 1)
check("used flipped", tile_map[0, 1].tolist(), [0, tiles.FLIP_X])

gb = targets.TARGETS["gb"]["limits"]
sprite = blank(16, 16)
sprite[:8, :8] = (255, 0, 0, 255)
sprite[0, 0] = (0, 255, 0, 255)
sprite[1, 1] = (0, 0, 255, 255)
sprite[2, 2] = (9, 9, 9, 255)
found = constraints.check(sprite, gb, "sprite")
check("a sprite tile with four colours breaks the budget", [(p["code"], p.get("at")) for p in found],
      [("budget.colours", [0, 0]), ("budget.shades", None)])
check("in a sentence with its place", found[0]["problem"], "sprite tile (0, 0) needs 4 colours; it can have 3")
check("a picture off the tile grid", constraints.check(blank(10, 16), gb, "sprite")[0]["code"], "budget.grid")
wide = blank(8, 96)
wide[..., 3] = 255
check("eleven sprites on a line", [p["code"] for p in constraints.check(wide, gb, "sprite")],
      ["budget.sprites_per_line"])
gbc = targets.TARGETS["gbc"]["limits"]
rainbow = blank(8, 80)
rainbow[..., 3] = 255
for t in range(10):
    for i in range(4):
        rainbow[:, t * 8 + i * 2:t * 8 + i * 2 + 2, :3] = (t * 20, i * 60, 7)
check("ten tiles of four colours each need ten palettes",
      [p["code"] for p in constraints.check(rainbow, gbc, "background")], ["budget.palettes"])
check("palettes are shared where colours allow", constraints.palettes_needed(
    [frozenset({1, 2}), frozenset({3, 4}), frozenset({1, 2, 3, 4})], 4), 1)
drawn = constraints.overlay(sprite, found, 8, scale=4)
check("the overlay is the picture enlarged", drawn.shape, (64, 64, 3))
check("with the broken tile outlined in red", tuple(drawn[0, 10]), (230, 30, 30))
check("and the rest not", tuple(drawn[40, 40]) != (230, 30, 30), True)

# ---- atlas ------------------------------------------------------------------------

four = [np.full((8, 8, 4), (i * 50, 0, 0, 255), np.uint8) for i in range(4)]
packed = atlas.grid(four, 2, extrude=1, spacing=2)
check("a grid sheet's size", packed.sheet.shape[:2], (22, 22))
check("frames sit inside their extrusion", packed.rects[1], (13, 1, 8, 8))
check("the extrusion repeats the edge", tuple(packed.sheet[0, 12]), (50, 0, 0, 255))
check("a sheet over the limit is refused, not shrunk", atlas.grid(four, 4, limit=16), None)
rows = atlas.grid_rows(four, ["walk", "walk", "walk", "idle"])
check("a new animation starts a new row", rows.rects[3], (0, 8, 8, 8))
mixed = [blank(30, 10), blank(10, 40), blank(20, 20)]
shelf = atlas.shelves(mixed, spacing=1)
check("shelves keep the frames' own order", [r[2:] for r in shelf.rects], [(10, 30), (40, 10), (20, 20)])
overlaps = [(a, b) for a in shelf.rects for b in shelf.rects if a < b and a[0] < b[0] + b[2]
            and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]]
check("and none overlap", overlaps, [])

# ---- fitting --------------------------------------------------------------------

tall = blank(20, 10)
tall[..., 3] = 255
padded = image.pad_to_aspect(tall, 1.0, "bottom")
check("padding keeps the feet on the floor", (padded.shape[:2], int(padded[19, 5, 3]), int(padded[0, 0, 3])),
      ((20, 20), 255, 0))
check("a scene is cropped from both ends", image.crop_to_aspect(blank(10, 40), 2.0).shape[:2], (10, 20))
check("a sheet splits into cells, row by row", [c.shape[:2] for c in image.split(blank(10, 30), 3, 2)],
      [(5, 10)] * 6)
