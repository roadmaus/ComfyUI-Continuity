"""Looking at assets: the constraint check, the contact sheet, a post preview.

The three things an agent that cannot see the bench needs to act on what it
made (spec §11.1): numbers it can branch on and a picture it can read.

- `check` builds every made asset for every target (or the ones asked for),
  answers with each problem's code, sentence and place, and draws the broken
  ones — red boxes on the converted picture — under `build/<target>/check/`.
- `sheet` is one PNG of an asset: its masters, then what each of the
  project's targets makes of them. Writing it counts as somebody having
  looked (`status` stops saying "not looked at"), which is the point: the
  skill makes looking part of the loop.
- `post` runs chosen steps for one target and keeps the frames under the
  asset's `variants/post/<target>/`, versioned like any other set.

All of it is arithmetic on the masters; nothing here runs a model.
"""

import os

import numpy as np
from PIL import Image, ImageDraw

from . import build, export, project as projects, targets
from .post import constraints, image
from .problems import ForgeError

THUMB = 192


def _made(base, project, assets):
    chosen = [projects.find(project, a) for a in assets] if assets else project["assets"]
    for recipe in chosen:
        if projects.state(base, project, recipe)["status"] != "planned":
            yield recipe


def check(base, name, target=None, assets=None):
    project = projects.load(base, name)
    if target is not None and target not in project["targets"]:
        raise ForgeError(f"{name} does not export to {target}", "project.target", target=target)
    root = projects.folder(base, name)
    answer = {"project": name, "targets": [], "count": 0}
    for t in [target] if target else project["targets"]:
        tile = targets.TARGETS[t]["limits"].get("tile", 8)
        report = {"target": t, "assets": [], "skipped": []}
        for recipe in _made(base, project, assets):
            try:
                built = build.run(base, project, recipe, t)
            except ForgeError as problem:
                report["skipped"].append({"asset": recipe["name"], "why": problem.problem, "code": problem.code})
                continue
            if built.recipe["kind"] in ("tile", "tileset") and "tile" not in targets.TARGETS[t]["limits"]:
                export.tile_sheet(built)
            else:
                export.layout(built)
            overlay = None
            if built.problems:
                drawn = []
                for frame_name, frame in zip(built.names, built.frames):
                    mine = [p for p in built.problems if p.get("frame") == frame_name]
                    if mine:
                        drawn.append(constraints.overlay(frame, mine, tile))
                rel = f"build/{t}/check/{recipe['name']}.png"
                if drawn:
                    projects.write_derived(root, rel, image.png(_side_by_side(drawn)))
                    overlay = rel
            report["assets"].append({"asset": recipe["name"], "problems": built.problems, "overlay": overlay})
            answer["count"] += len(built.problems)
        answer["targets"].append(report)
    return answer


def _side_by_side(pictures, gap=8, background=(255, 255, 255)):
    """RGB or RGBA pictures in a row, tops aligned -> RGBA."""
    height = max(p.shape[0] for p in pictures)
    width = sum(p.shape[1] for p in pictures) + gap * (len(pictures) - 1)
    out = np.zeros((height, width, 4), np.uint8)
    out[..., :3] = background
    out[..., 3] = 255
    x = 0
    for p in pictures:
        if p.shape[2] == 3:
            p = np.concatenate([p, np.full(p.shape[:2] + (1,), 255, np.uint8)], 2)
        out[:p.shape[0], x:x + p.shape[1]] = p
        x += p.shape[1] + gap
    return out


def _thumb(rgba, pixel=False):
    height, width = rgba.shape[:2]
    if pixel:
        factor = max(1, THUMB // max(width, height))
        big = image.upscale_nearest(rgba, factor)
    else:
        scale = min(1.0, THUMB / max(width, height))
        big = image.resize(rgba, (max(1, round(width * scale)), max(1, round(height * scale))))
    return image.over(image.checker(*big.shape[:2]), big)


def sheet(base, name, asset):
    """One PNG: the masters, then each target's frames. -> {path, rows}."""
    project = projects.load(base, name)
    recipe = projects.find(project, asset)
    masters = build.read_masters(base, project, recipe)
    rows = [("masters", [_thumb(p) for _, p in masters], [])]
    for t in project["targets"]:
        try:
            built = build.run(base, project, recipe, t)
        except ForgeError as problem:
            rows.append((t, [], [problem.problem]))
            continue
        rows.append((t, [_thumb(f, built.palette is not None) for f in built.frames],
                     [p["problem"] for p in built.problems]))
    label_h, gap = 16, 8
    strips = []
    for label, thumbs, notes in rows:
        text = label + (f" — {len(notes)} problem{'s' if len(notes) != 1 else ''}: {notes[0]}" if notes else "")
        strip = _side_by_side(thumbs) if thumbs else np.full((1, 1, 4), 255, np.uint8)
        canvas = Image.new("RGBA", (max(strip.shape[1], 8 * len(text)), strip.shape[0] + label_h), "white")
        ImageDraw.Draw(canvas).text((0, 2), text, fill=(200, 0, 0) if notes else (40, 40, 40))
        canvas.paste(Image.fromarray(strip, "RGBA"), (0, label_h))
        strips.append(np.asarray(canvas))
    width = max(s.shape[1] for s in strips)
    out = np.full((sum(s.shape[0] for s in strips) + gap * (len(strips) - 1), width, 4), 255, np.uint8)
    y = 0
    for s in strips:
        out[y:y + s.shape[0], :s.shape[1]] = s
        y += s.shape[0] + gap
    rel = f"build/sheets/{asset}.png"
    projects.write_derived(projects.folder(base, name), rel, image.png(out))
    projects.mark_viewed(base, name, asset)
    return {"project": name, "asset": asset, "path": rel, "rows": [label for label, _, _ in rows]}


def post(base, name, asset, steps, target=None):
    """Run `steps` for `target` and keep the frames as the asset's post variants."""
    from .kinds import POST_STEPS

    unknown = [s for s in steps if s not in POST_STEPS]
    if unknown:
        raise ForgeError("no post-step called " + ", ".join(unknown) + "; the steps are " + ", ".join(POST_STEPS),
                         "post.step", steps=unknown)
    project = projects.load(base, name)
    recipe = projects.find(project, asset)
    target = target or project["targets"][0]
    if target not in project["targets"]:
        raise ForgeError(f"{name} does not export to {target}", "project.target", target=target)
    built = build.run(base, project, recipe, target, steps)
    root = projects.folder(base, name)
    where = projects.asset_dir(base, project, recipe)
    rel = os.path.relpath(os.path.join(where, "variants", "post", target), root)

    def fill(staging):
        for frame_name, frame in zip(built.names, built.frames):
            with open(os.path.join(staging, projects.safe_file(frame_name) + ".png"), "wb") as handle:
                handle.write(image.png(frame))

    with projects.LOCK:
        projects.swap_folder(root, rel, fill)
    files = [f"{rel}/{projects.safe_file(n)}.png".replace(os.sep, "/") for n in built.names]
    return {"project": name, "asset": asset, "target": target, "steps": built.steps, "files": files,
            "problems": built.problems}
