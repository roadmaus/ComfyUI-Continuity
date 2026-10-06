"""Engine files, written from built assets into `build/<target>/` (spec §9).

A target only ever reads masters (§5.3): every export builds each made asset
afresh through `build.run` and writes what the engine reads. The writers are
one module per family of formats:

- `aseprite.py`  PNG sheet + Aseprite JSON (generic), and LÖVE's Lua table;
- `godot.py`     `SpriteFrames` and `TileSet` `.tres`;
- `tiled.py`     `.tsx` tilesets and `.tmj` maps;
- `gameboy.py`   indexed PNGs for rgbgfx, png2asset and GB Studio.

**`build/` is derived, so it is not versioned.** Every file there is
regenerated from masters by the next export; keeping the old ones under
`.versions/` would keep copies of copies. Files are still swapped in whole,
so a reader never sees half a sheet. `.built.json` records, per asset, the
fingerprint it was exported from — what `status` reads to say *exported*.

An asset with a broken budget is still written, and the problems come back
with the answer: the person or agent can see the red box on the overlay and
decide. An asset that cannot be written at all (a sheet over the atlas limit)
is skipped, with its problem.
"""

import json
import os

from .. import build, project as projects, targets
from ..post import atlas, image
from ..problems import ForgeError


def layout(built):
    """The sheet `built` goes on for its target -> Packed, or None (with a
    `budget.atlas` problem added) when it does not fit."""
    limits = targets.TARGETS[built.target]["limits"]
    pack = targets.pack(built.target)
    frames = built.frames
    if "tile" in limits:
        # A Game Boy sheet: frames in one strip, on the tile grid. GB Studio
        # reads a sprite's frames left to right; png2asset takes any order.
        if len(frames) == 1:
            return atlas.Packed(frames[0], [(0, 0, frames[0].shape[1], frames[0].shape[0])])
        if len({f.shape for f in frames}) == 1:
            return atlas.grid(frames, len(frames), limit=1 << 30)
        return atlas.shelves(frames, limit=1 << 30)
    limit = limits.get("atlas", 2048)
    uniform = len({f.shape for f in frames}) == 1
    if not uniform:
        packed = atlas.shelves(frames, pack["extrude"], pack["spacing"], limit)
    elif built.tags and built.recipe.get("sheet", "grid") == "grid":
        rows = [next(t["name"] for t in built.tags if t["from"] <= i <= t["to"]) for i in range(len(frames))]
        packed = atlas.grid_rows(frames, rows, pack["extrude"], pack["spacing"], limit)
    elif built.recipe.get("sheet") == "row":
        packed = atlas.grid(frames, len(frames), pack["extrude"], pack["spacing"], limit)
    else:
        packed = atlas.grid(frames, image.grid_shape(len(frames))[0], pack["extrude"], pack["spacing"], limit)
    if packed is None:
        built.problems.append({"problem": f"its frames do not fit on one {limit}×{limit} sheet",
                               "code": "budget.atlas", "asset": built.recipe["name"]})
    return packed


def tile_sheet(built):
    """Tiles on a plain grid -> (Packed or None, the target's pack settings).

    Tiled and Godot address a tile by column and row, so a tile sheet is a
    grid whatever layout the recipe asks for.
    """
    pack = targets.pack(built.target)
    limit = targets.TARGETS[built.target]["limits"].get("atlas", 2048)
    packed = atlas.grid(built.frames, image.grid_shape(len(built.frames))[0],
                        pack["extrude"], pack["spacing"], limit)
    if packed is None:
        built.problems.append({"problem": f"its tiles do not fit on one {limit}×{limit} sheet",
                               "code": "budget.atlas", "asset": built.recipe["name"]})
    return packed, pack


def writer_for(target):
    from . import aseprite, gameboy, godot, tiled

    return {"generic": aseprite.write_generic, "love": aseprite.write_love, "godot4": godot.write,
            "tiled": tiled.write, "gb": gameboy.write, "gbc": gameboy.write,
            "gbstudio": gameboy.write}.get(target)


def export(base, name, target, assets=None):
    """Write every made asset (or the named ones) for `target`.

    -> {target, written: [paths relative to the project], skipped: [{asset,
    why, code}], problems: [...]}.
    """
    project = projects.load(base, name)
    targets.require_target(target)
    if target not in project["targets"]:
        raise ForgeError(f"{name} does not export to {target}; add it first", "project.target", target=target)
    writer = writer_for(target)
    if writer is None:
        raise ForgeError(f"exporting to {target} is not in this version of the forge", "export.target",
                         target=target)
    chosen = [projects.find(project, a) for a in assets] if assets else project["assets"]
    root = projects.folder(base, name)
    out_root = projects.inside(root, "build", target)
    marker = os.path.join(out_root, projects.BUILT_FILE)
    try:
        with open(marker, encoding="utf-8") as handle:
            built_from = json.load(handle)
    except FileNotFoundError:
        built_from = {}
    answer = {"target": target, "written": [], "skipped": [], "problems": []}
    with projects.LOCK:
        _export_each(base, project, chosen, target, writer, out_root, built_from, answer)
        projects.write_derived(out_root, projects.BUILT_FILE, json.dumps(built_from, indent=2, sort_keys=True) + "\n")
        projects.save(base, project)  # the manifest's status column moves to exported
    return answer


def _export_each(base, project, chosen, target, writer, out_root, built_from, answer):
    for recipe in chosen:
        row = projects.state(base, project, recipe)
        if row["status"] == "planned":
            answer["skipped"].append({"asset": recipe["name"], "why": "not made yet", "code": "export.planned"})
            continue
        try:
            built = build.run(base, project, recipe, target)
        except ForgeError as problem:
            answer["skipped"].append({"asset": recipe["name"], "why": problem.problem, "code": problem.code})
            continue
        files = writer(project, built)
        answer["problems"] += built.problems
        if files is None:
            answer["skipped"].append({"asset": recipe["name"], "code": "budget.atlas",
                                      "why": "its frames do not fit on one sheet"})
            continue
        for rel, data in files.items():
            projects.write_derived(out_root, rel, data)
            answer["written"].append(f"build/{target}/{rel}")
        built_from[recipe["name"]] = projects.fingerprint(project, recipe, row["source"])
