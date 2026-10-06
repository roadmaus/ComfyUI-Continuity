"""Game Forge: a game's assets, made inside one project.

`specs/continuity-game-forge-spec.md` is the design. This package is its
Python half. Nothing in it imports ComfyUI or torch, and the storage half
imports no numpy either — the suites load it standalone, and the CLI's parity
test runs the real handlers behind a standard-library server. The building half
(`build`, `review`, `post/`, `export/`) is numpy and PIL arithmetic, imported by
the handlers that need it.

- `problems.py`  the refusal every layer raises: a sentence and a code.
- `kinds.py`     what an asset of each kind is: its fields, defaults, schema.
- `targets.py`   the render modes and the engine profiles a project exports to.
- `style.py`     what every asset in a project must agree on.
- `project.py`   storage: names, versioned writes, the plan merge, status.
- `manifest.py`  `MANIFEST.md`, written from the project.
- `build.py`     an asset's masters through its post-chain, for one target.
- `review.py`    the constraint check, the contact sheet, a post preview.
- `post/`        the post-steps, one module each (spec §6).
- `export/`      the engine writers (spec §9).
- `api.py`       the `/continuity/forge/*` surface as a table of handlers,
                 which `routes/forge.py` serves and the CLI is held against.
"""
