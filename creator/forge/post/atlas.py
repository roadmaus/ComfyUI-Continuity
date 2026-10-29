"""Frames packed into one sheet (§6.7).

Two layouts, because two kinds of set come through here:

- **Uniform** frames (a sprite's, a tileset's, an icon set's) go on a grid,
  one row per animation where there are animations. A grid is what Tiled and
  Godot's tile atlas need — they address a tile by column and row — and what a
  person reading the sheet expects.
- **Mixed** sizes (a character's views, UI pieces, background layers) go on
  shelves: tallest first, left to right, a new shelf when a row is full.

Each frame is **extruded** — its edge pixels repeated outward — and frames
are **spaced** apart, both per target. Without the extrusion a bilinear sample
at a frame's border reads the neighbour; with it, it reads the frame's own
edge. A Game Boy sheet has neither: its tiles must sit on the 8-pixel grid.

The sheet never grows past the target's limit (2048 by default). A set that
does not fit is reported, not shrunk: shrinking it would change the art.
"""

import math

import numpy as np


class Packed:
    def __init__(self, sheet, rects, columns=None):
        self.sheet = sheet
        self.rects = rects          # [(x, y, w, h)] of each frame's own pixels, in order
        self.columns = columns      # grid layouts only


def _extruded(frame, extrude):
    if not extrude:
        return frame
    return np.pad(frame, ((extrude, extrude), (extrude, extrude), (0, 0)), mode="edge")


def _place(size, frames, positions, extrude):
    sheet = np.zeros((size[1], size[0], 4), np.uint8)
    for frame, (x, y) in zip(frames, positions):
        grown = _extruded(frame, extrude)
        sheet[y:y + grown.shape[0], x:x + grown.shape[1]] = grown
    return sheet


def grid(frames, columns, extrude=0, spacing=0, limit=2048):
    """Same-size frames, `columns` to a row. -> Packed, or None if over `limit`.

    The cell pitch is the frame plus extrusion on both sides plus spacing, so
    the sheet is what Tiled calls margin `extrude`, spacing `2·extrude + spacing`.
    """
    fh, fw = frames[0].shape[:2]
    if any(f.shape[:2] != (fh, fw) for f in frames):
        raise ValueError("a grid takes frames of one size")
    pitch_x, pitch_y = fw + 2 * extrude + spacing, fh + 2 * extrude + spacing
    columns = max(1, min(columns, len(frames)))
    rows = math.ceil(len(frames) / columns)
    width = columns * pitch_x - spacing
    height = rows * pitch_y - spacing
    if width > limit or height > limit:
        return None
    positions = [((i % columns) * pitch_x, (i // columns) * pitch_y) for i in range(len(frames))]
    sheet = _place((width, height), frames, positions, extrude)
    return Packed(sheet, [(x + extrude, y + extrude, fw, fh) for x, y in positions], columns)


def grid_rows(frames, rows_of, extrude=0, spacing=0, limit=2048):
    """Same-size frames with a row break wherever `rows_of[i]` changes — one
    row per animation. Over `limit` -> None."""
    fh, fw = frames[0].shape[:2]
    pitch_x, pitch_y = fw + 2 * extrude + spacing, fh + 2 * extrude + spacing
    positions, row, column, last = [], -1, 0, object()
    for key in rows_of:
        if key != last:
            row, column, last = row + 1, 0, key
        positions.append((column * pitch_x, row * pitch_y))
        column += 1
    width = max(x for x, _ in positions) + pitch_x - spacing
    height = (row + 1) * pitch_y - spacing
    if width > limit or height > limit:
        return None
    sheet = _place((width, height), frames, positions, extrude)
    return Packed(sheet, [(x + extrude, y + extrude, fw, fh) for x, y in positions])


def shelves(frames, extrude=0, spacing=0, limit=2048):
    """Frames of any size on shelves, tallest first. Over `limit` -> None.
    Rects come back in the frames' own order, not packing order."""
    sizes = [(f.shape[1] + 2 * extrude, f.shape[0] + 2 * extrude) for f in frames]
    if any(w > limit or h > limit for w, h in sizes):
        return None
    order = sorted(range(len(frames)), key=lambda i: -sizes[i][1])
    # Aim for a square-ish sheet, never wider than the limit.
    area = sum((w + spacing) * (h + spacing) for w, h in sizes)
    width_cap = min(limit, max(max(w for w, _ in sizes), int(math.sqrt(area) * 1.2)))
    positions = [None] * len(frames)
    x = y = shelf = 0
    used_w = 0
    for i in order:
        w, h = sizes[i]
        if x and x + w > width_cap:
            x, y, shelf = 0, y + shelf + spacing, 0
        positions[i] = (x, y)
        x += w + spacing
        shelf = max(shelf, h)
        used_w = max(used_w, x - spacing)
    height = y + shelf
    if height > limit:
        return None
    sheet = _place((used_w, height), frames, positions, extrude)
    return Packed(sheet, [(x + extrude, y + extrude, f.shape[1], f.shape[0])
                          for (x, y), f in zip(positions, frames)])
