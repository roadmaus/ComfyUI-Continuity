"""An asset's masters, through its post-chain, for one target.

The one place that knows which post-step an asset gets and why. The steps
themselves (`post/`) are arithmetic on arrays; this module reads the masters,
cuts them into frames by the recipe, runs the chain the render mode (or the
recipe) names, converts to the target's size, and hands the exporters a
`Built`: frames at the target size, their names and animation tags, pivots,
the palette, and every budget the target says they break.

**The steps run in one order, whatever order a recipe lists them in**:
matte → colour match → conversion → baseline → bleed. A recipe's `post` list
says *which* steps run, not when, because the order is not a matter of taste:
colours are matched at full precision before the conversion throws precision
away, feet are aligned at the size they will be shown at, and bleed fills the
texels the conversion left transparent. Conversion is not optional — it is
the target's, not the recipe's (§5.3): pixelize when the project or the target
is pixel art, a premultiplied Lanczos resize otherwise. Constraints are always
checked and the atlas is always packed at export; naming them in a recipe
changes nothing.

**How masters become frames**, per kind:

- `sprite`: one file per frame (in name order), or one sheet holding them all,
  one row per animation and direction, as a grid generation makes them.
  Directions are rows within an animation: `walk_s`, `walk_e`, … (§7.1).
- `icon`, `ui`, `tileset`: one file per name in the recipe's set, or one sheet
  split into that many cells, as squarely as they go.
- `character`: every master is a view; `tile`: exactly one; `background`:
  every master is a layer, back to front.

Materials, model textures and sounds have their own chains (§7.3, §7.4, §8)
and are not built here yet; asking is refused with a code.
"""

import os

import numpy as np

from . import project as projects, targets
from .post import baseline, bleed, colormatch, constraints, image, pixelize
from .problems import ForgeError

PICTURES = (".png", ".webp", ".jpg", ".jpeg")
DIRECTIONS = {1: [None], 4: ["s", "e", "n", "w"], 8: ["s", "se", "e", "ne", "n", "nw", "w", "sw"]}
DEFAULT_FPS = 12
BUILDABLE = ("character", "sprite", "tile", "tileset", "icon", "ui", "background")

# What the hardware treats a kind as (constraints.py): objects drawn over the
# scene, or the scene itself.
ROLE = {"character": "sprite", "sprite": "sprite", "icon": "sprite",
        "tile": "background", "tileset": "background", "ui": "background", "background": "background"}


class Built:
    """What one asset is for one target, ready to be written."""

    def __init__(self, recipe, target):
        self.recipe = recipe
        self.target = target
        self.role = ROLE[recipe["kind"]]
        self.frames = []        # RGBA arrays at the target size
        self.names = []         # one per frame
        self.tags = []          # [{name, from, to, fps, loop}] — animations, inclusive
        self.pivots = []        # (x, y) per frame
        self.palette = None     # N × 3 floats when pixelized, light to dark on a Game Boy
        self.problems = []      # [{problem, code, frame?, at?}]
        self.steps = []         # the steps that ran, in order

    def durations(self):
        """Milliseconds per frame, from its animation's fps."""
        out = [round(1000 / DEFAULT_FPS)] * len(self.frames)
        for tag in self.tags:
            for i in range(tag["from"], tag["to"] + 1):
                out[i] = round(1000 / tag["fps"])
        return out


def _refuse(recipe, sentence, code, **extra):
    raise ForgeError(f"{recipe['name']}: {sentence}", code, asset=recipe["name"], **extra)


def read_masters(base, project, recipe):
    """-> [(file name, RGBA array)] in name order. Refused when there are none."""
    where = os.path.join(projects.asset_dir(base, project, recipe), "masters")
    names = [n for n in sorted(os.listdir(where)) if n.lower().endswith(PICTURES)] \
        if os.path.isdir(where) else []
    if not names:
        _refuse(recipe, "has no pictures in its masters yet; make or import them first", "build.no_masters")
    out = []
    for n in names:
        try:
            out.append((n, image.read(os.path.join(where, n))))
        except (OSError, ValueError) as exc:  # PIL's UnidentifiedImageError is an OSError
            _refuse(recipe, f"cannot read its master {n}: {exc}", "build.unreadable", file=n)
    return out


def _named_set(recipe, masters, names, what):
    """One picture per name, or one sheet split into that many cells."""
    count = len(names)
    if not count:
        return [(os.path.splitext(n)[0], picture) for n, picture in masters]
    if len(masters) == count:
        return [(name, picture) for name, (_, picture) in zip(names, masters)]
    if len(masters) == 1:
        columns, rows = image.grid_shape(count)
        return list(zip(names, image.split(masters[0][1], columns, rows)))
    _refuse(recipe, f"names {count} {what} but has {len(masters)} masters; give one per {what[:-1]}, "
                    "or one sheet holding them all", "build.count", want=count, have=len(masters))


def _sprite_frames(recipe, masters):
    """-> [(name, picture)], [tags]: frames in sheet order with their animations."""
    animations = recipe["animations"] or [{"name": "default", "frames": len(masters) if len(masters) > 1 else 1}]
    directions = DIRECTIONS[recipe["directions"]]
    rows = [(a, d) for a in animations for d in directions]
    total = sum(a.get("frames", 1) for a, _ in rows)
    if len(masters) == total:
        pictures = [p for _, p in masters]
    elif len(masters) == 1:
        columns = max(a.get("frames", 1) for a, _ in rows)
        cells = image.split(masters[0][1], columns, len(rows))
        pictures = [cells[r * columns + c] for r, (a, _) in enumerate(rows) for c in range(a.get("frames", 1))]
    else:
        _refuse(recipe, f"has {len(masters)} masters for {total} frames; give one per frame, or one sheet "
                        "with a row per animation and direction", "build.count", want=total, have=len(masters))
    frames, tags = [], []
    for animation, direction in rows:
        tag = animation["name"] + (f"_{direction}" if direction else "")
        start = len(frames)
        for i in range(animation.get("frames", 1)):
            frames.append((f"{tag}_{i}", pictures[len(frames)]))
        tags.append({"name": tag, "from": start, "to": len(frames) - 1,
                     "fps": animation.get("fps") or DEFAULT_FPS, "loop": animation.get("loop", True)})
    return frames, tags


def frames_of(recipe, masters):
    """The recipe's frames from its masters -> ([(name, RGBA)], [tags])."""
    kind = recipe["kind"]
    if kind == "sprite":
        return _sprite_frames(recipe, masters)
    if kind == "tile":
        if len(masters) != 1:
            _refuse(recipe, f"a tile has one master; this has {len(masters)}", "build.count",
                    want=1, have=len(masters))
        return [(recipe["name"], masters[0][1])], []
    if kind == "tileset":
        return _named_set(recipe, masters, recipe["tiles"], "tiles"), []
    if kind in ("icon", "ui"):
        return _named_set(recipe, masters, recipe["set"], "pieces"), []
    return [(os.path.splitext(n)[0], picture) for n, picture in masters], []


def _override_size(recipe, target):
    size = (recipe.get("targets") or {}).get(target, {}).get("size")
    if size is None:
        return None
    if (not isinstance(size, list) or len(size) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in size)):
        _refuse(recipe, f"targets.{target}.size must be [width, height]", "recipe.field", field="targets")
    return size


def out_size(recipe, picture, target, style, pixel):
    """The size one frame is converted to for `target`."""
    size = _override_size(recipe, target)
    if size:
        return size
    kind = recipe["kind"]
    if kind == "sprite":
        return recipe["frame"]
    if kind in ("tile", "tileset"):
        return recipe["tile"]
    if kind == "icon":
        return recipe["icon"]
    height, width = picture.shape[:2]
    if not pixel:
        return [width, height]
    if not style["grid"]:
        _refuse(recipe, f"needs a size to be pixel art for {target}: set the style's grid, or "
                        f"targets.{target}.size on the asset", "build.size", target=target)
    size = [max(1, width // style["grid"]), max(1, height // style["grid"])]
    tile = targets.TARGETS[target]["limits"].get("tile")
    if tile and ROLE[kind] == "background":
        # The scene is tile data; a part tile at the edge is a picture the
        # hardware cannot show, so the conversion stops at the last whole one.
        size = [max(tile, size[0] - size[0] % tile), max(tile, size[1] - size[1] % tile)]
    return size


def palette_for(target, style, role, cells):
    """The palette a pixel conversion quantises to, as N × 3 floats."""
    limits = targets.TARGETS[target]["limits"]
    if "tile" in limits and not limits.get("rgb555"):
        # A monochrome Game Boy has four shades and nothing else. The style's
        # palette is used when it is four colours; otherwise the greens. Kept
        # light to dark, so an index is a shade number.
        shades = style["palette"] if len(style["palette"]) == limits["shades"] else targets.DMG_PALETTE
        colours = pixelize.palette_of(shades)
        colours = colours[np.argsort(-(colours @ np.array([0.30, 0.59, 0.11])), kind="stable")]
        if role == "sprite":
            # Three shades and transparent. GB Studio forbids the second-darkest;
            # a plain Game Boy could map any three through OBP, and the same
            # three keep one project's sprites alike on both.
            colours = colours[[0, 1, 3]]
        return colours
    if style["palette"]:
        colours = pixelize.palette_of(style["palette"])
    else:
        colours = pixelize.cut_palette(cells, 32 if limits.get("rgb555") else 16)
    if limits.get("rgb555"):
        colours = np.unique((colours / 255 * 31).round() * 255 / 31, axis=0)
    return colours


def _fit(recipe, picture, aspect, anchor):
    """A picture brought to its frame's shape: a tile is stretched (it must
    fill), a scene cropped (its size stops at the last whole tile), anything
    else padded, so no figure loses a hand to fit."""
    if recipe["kind"] in ("tile", "tileset"):
        return picture
    if recipe["kind"] == "background":
        return image.crop_to_aspect(picture, aspect)
    return image.pad_to_aspect(picture, aspect, anchor)


def run(base, project, recipe, target, steps=None):
    """Build one asset for one target -> Built.

    `steps` overrides the chain (the `post` route); otherwise the recipe's own
    list, else the render mode's.
    """
    if recipe["kind"] not in BUILDABLE:
        _refuse(recipe, f"{recipe['kind']} assets are not built in this version of the forge", "build.kind",
                kind=recipe["kind"])
    targets.require_target(target)
    style = project["style"]
    chosen = set(steps if steps is not None else targets.chain(style["mode"], recipe))
    pixel = style["mode"] == "pixel" or targets.TARGETS[target].get("pixel", False)
    built = Built(recipe, target)

    named, built.tags = frames_of(recipe, read_masters(base, project, recipe))
    built.names = [n for n, _ in named]
    pictures = [p for _, p in named]

    if "matte" in chosen:
        built.steps.append("matte")
        if not recipe["alpha"]:
            for p in pictures:
                p[..., 3] = 255
        else:
            for name, p in named:
                if p[..., 3].min() == 255:
                    _refuse(recipe, f"frame {name} has no transparency. Matting an opaque picture runs "
                                    "BiRefNet on the GPU, which this version does not do yet: import it "
                                    "with alpha, or set the asset's alpha to false", "matte.opaque", frame=name)

    one_subject = recipe["kind"] in ("sprite", "character")
    if "colormatch" in chosen and one_subject and len(pictures) > 1:
        built.steps.append("colormatch")
        pictures = colormatch.match_set(pictures)

    # Conversion to the target's size.
    anchor = "bottom" if one_subject else "centre"
    sizes = [out_size(recipe, p, target, style, pixel) for p in pictures]
    fitted = [_fit(recipe, p, w / h, anchor) for p, (w, h) in zip(pictures, sizes)]
    if pixel:
        built.steps.append("pixelize")
        for name, p, (w, h) in zip(built.names, fitted, sizes):
            if w > p.shape[1] or h > p.shape[0]:
                _refuse(recipe, f"frame {name} is {p.shape[1]}×{p.shape[0]}, smaller than the {w}×{h} it "
                                "would be pixelized to; pixel art is made from a larger master",
                        "build.size", frame=name)
        cells = [pixelize.cells(p, s) for p, s in zip(fitted, sizes)]
        built.palette = palette_for(target, style, built.role, cells)
        frames = []
        for c in cells:
            indices, visible = pixelize.quantise(c, built.palette)
            frames.append(pixelize.to_rgba(indices, visible, built.palette))
    else:
        built.steps.append("resize")
        frames = [image.resize(p, s) for p, s in zip(fitted, sizes)]
    if not recipe["alpha"]:
        for f in frames:
            f[..., 3] = 255

    if "baseline" in chosen and one_subject and len({f.shape for f in frames}) == 1:
        built.steps.append("baseline")
        if built.tags:
            for tag in built.tags:
                frames[tag["from"]:tag["to"] + 1] = baseline.align(frames[tag["from"]:tag["to"] + 1])
        else:
            frames = baseline.align(frames)
    pivot = recipe.get("pivot")
    if built.tags:
        # One pivot per animation, read off its first frame, so the anchor does
        # not jitter with the figure inside the cycle.
        built.pivots = [None] * len(frames)
        for tag in built.tags:
            point = baseline.pivot(frames[tag["from"]], pivot)
            built.pivots[tag["from"]:tag["to"] + 1] = [point] * (tag["to"] - tag["from"] + 1)
    else:
        built.pivots = [baseline.pivot(f, pivot) for f in frames]

    if "bleed" in chosen and not pixel and recipe["alpha"]:
        built.steps.append("bleed")
        frames = [bleed.bleed(f) for f in frames]
    built.frames = frames

    limits = targets.TARGETS[target]["limits"]
    for name, frame in zip(built.names, frames):
        for problem in constraints.check(frame, limits, built.role):
            built.problems.append({**problem, "asset": recipe["name"], "frame": name})
    if recipe["kind"] == "tileset" and "tile" in limits:
        _tileset_budget(built, limits)
    return built


def _tileset_budget(built, limits):
    """A tileset is one scene's tiles: its unique count across every frame,
    side by side so a tile in one frame and its mirror in another are one."""
    from .post import tiles as tiling

    tile = limits["tile"]
    if len({f.shape for f in built.frames}) != 1 or built.frames[0].shape[0] % tile \
            or built.frames[0].shape[1] % tile:
        return
    unique, _ = tiling.dedupe(np.concatenate(built.frames, axis=1), (tile, tile), limits.get("flips", False))
    if len(unique) > limits["bg_tiles"]:
        built.problems.append({"problem": f"{len(unique)} unique tiles; a scene can have {limits['bg_tiles']}",
                               "code": "budget.tiles", "asset": built.recipe["name"]})
