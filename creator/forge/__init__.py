"""Game Forge: a game's assets, made inside one project.

`specs/continuity-game-forge-spec.md` is the design. This package is its
Python half, and everything in it imports without ComfyUI, torch or numpy at
module scope — the suites load it standalone, and the CLI's parity test runs
the real handlers behind a standard-library server.

- `problems.py`  the refusal every layer raises: a sentence and a code.
- `kinds.py`     what an asset of each kind is: its fields, defaults, schema.
- `targets.py`   the render modes and the engine profiles a project exports to.
- `style.py`     what every asset in a project must agree on.
- `project.py`   storage: names, versioned writes, the plan merge, status.
- `manifest.py`  `MANIFEST.md`, written from the project.
- `api.py`       the `/continuity/forge/*` surface as a table of handlers,
                 which `routes/forge.py` serves and the CLI is held against.
"""
