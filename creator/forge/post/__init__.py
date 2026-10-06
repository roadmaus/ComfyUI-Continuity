"""The post-steps (spec §6): masters in, game-ready pictures out.

Each step is a pure function of numpy arrays — RGBA, `uint8`, height × width
× 4 — with no knowledge of projects, recipes or targets, so each has its own
suite and the chain that strings them together (`forge/build.py`) is the only
place that knows which step an asset gets and why.

Unlike the rest of `creator/forge/`, these modules import numpy and PIL at
module scope: they are arithmetic and nothing else. `api.py` imports them only
inside the handlers that need them, so the project storage and the CLI's parity
suite still load on a bare Python.

- `image.py`        reading, writing, fitting and splitting pictures.
- `bleed.py`        alpha bleed by push–pull.
- `baseline.py`     a set's frames on one foot line; pivots.
- `colormatch.py`   a set's frames matched to its first.
- `pixelize.py`     mode-of-cell downscale and palette quantisation.
- `constraints.py`  a target's budgets, broken ones drawn on the picture.
- `atlas.py`        frames packed into one sheet, extruded and spaced.
- `tiles.py`        a picture cut into tiles, de-duplicated, as a map.
"""
