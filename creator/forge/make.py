"""Making an asset: its recipe as renders on ComfyUI's queue, and the renders
back as its masters.

Nothing here is a second builder. A recipe becomes the same request a script
sends `/continuity/render` (`routes/render.py`): a family, a prompt, pictures,
an aspect, a seed, LoRAs. The host (`routes/forge.py`) runs that request
through the render route's own builder and puts it on the queue, so a forge
render is checked, weighted and sampled exactly like any other still, and
refused in the same words. What this module adds is what the render route
cannot know: what a *kind* of asset asks of the picture, where the files land,
and how they become masters.

**What a kind asks for.** The prompt is the recipe's words, then a sentence the
kind needs (a character is a model sheet: the neutral pose with the arms away
from the body, spec §7.1 step 1), then the style clause, then the style's
pictures cited by number, then — for anything with alpha — the sentence that
asks Qwen Image 2.1 for a transparent background. 2.1 draws alpha itself
through its RGBA VAE, and the save node keeps all four channels, so an asset
made on 2.1 needs no matting (§6.1). A family without alpha draws an opaque
picture, which the build refuses as it refuses an opaque import
(`matte.opaque`); the take says so the moment it lands rather than at export.

**A set is one render per name**, every one on the asset's seed and its style,
so the set shares a look without needing a grid the model has to lay out
exactly. The masters are numbered so they sort in the set's order, which is
the order `build._named_set` reads them in.

**Takes.** Every make is a take: `takes/<asset>/<take>/`, a `take.json` saying
what was asked, and the renders themselves, which the save node writes there
because the request names that folder as its output prefix. A take is
collected when every render it queued is on disk: each is fitted to the
recipe's size (padded with transparency where the asset has alpha, cropped
where it is a scene) and the set becomes the asset's masters in one versioned
swap, with the recipe *as it was when the take was queued* — so a recipe edited
while its render was on the queue comes back stale, as it is. The files on
disk are the record, so a take queued before a restart is still collected after
one; only the queue's own word on a failure is lost to a restart, and the take
then says that.

Collection happens whenever someone asks how the takes are going
(`/jobs`, and `status`): the queue has no hook to call back into, and asking
is what every client does anyway while it waits.
"""

import datetime
import json
import math
import os
import re
import secrets
import time

from . import project as projects, style as styles
from .problems import ForgeError

TAKES = "takes"
TAKE_FILE = "take.json"

# `outputs.FORGE`, spelt here so this module stays importable without the
# pack around it (the parity suite loads `forge/` alone). The test holds the
# two together.
FORGE_SHELF = "continuity/forge"

# What a kind's picture needs that its recipe's words do not say.
SHEET = ("A full-body character model sheet: one figure standing in a neutral pose, arms held "
         "away from the body, mouth closed, eyes open, the whole figure in frame.")
ALPHA = "Transparent background with alpha channel."
STYLE_REFS = "Draw it in the art style of {cites}."

# The kinds a still render makes, and why each of the others waits.
MAKEABLE = ("character", "background", "icon", "ui", "tile", "tileset")
NOT_YET = {
    "sprite": "a sprite's frames are drawn from a pose set through the four-frame grid, which make "
              "does not do yet; render them with the continuity-render skill and import them",
    "material": "materials are a later step (spec §12, step 4)",
    "texture": "texturing a model is a later step (spec §12, step 4)",
    "sound": "sound is a later step (spec §12, step 3)",
}

def _words(name):
    return re.sub(r"[-_]+", " ", name).strip()


def _sentence(text):
    text = (text or "").strip()
    return text if not text or text[-1] in ".!?" else text + "."


def _cite(numbers):
    cites = [f"@pic-{n}" for n in numbers]
    return cites[0] if len(cites) == 1 else ", ".join(cites[:-1]) + " and " + cites[-1]


def nearest_aspect(size, aspects):
    """The family's named aspect closest to `size`, by ratio on a log scale."""
    ratio = size[0] / size[1]
    return min(aspects, key=lambda name: abs(math.log(aspects[name] / ratio)))


def _family(host, name):
    for family in host.families():
        if family["id"] == name:
            if not family.get("still"):
                raise ForgeError(f"{name} draws clips, not pictures; a forge asset is made by a still family",
                                 "make.family", family=name)
            return family
    raise ForgeError(f"this server has no family called {name!r}", "make.family", family=name)


def _picture(base, project, name):
    """A reference by name -> the name the render route reads it by: a project
    file as an annotated output name, anything else as ComfyUI's input."""
    try:
        path = projects.inside(projects.folder(base, project["name"]), name)
    except ForgeError:
        path = None
    if path and os.path.isfile(path):
        return f"{FORGE_SHELF}/{project['name']}/{name.replace(os.sep, '/')} [output]"
    return name


def plan(host, base, project, recipe, fast=False, quality=None):
    """One asset -> the renders that make it: `[{stem, body}]`, nothing queued.

    Refused with a code when the kind cannot be made yet or the recipe asks for
    something no render here gives (a seamless tile, a parallax stack)."""
    kind = recipe["kind"]
    name = recipe["name"]
    if kind not in MAKEABLE:
        raise ForgeError(f"{name}: {NOT_YET[kind]}", "make.kind", asset=name, kind=kind)
    if kind in ("tile", "tileset") and recipe["seamless"] != "none":
        raise ForgeError(f"{name}: seamless tiling is not built yet, so a render would not wrap; set "
                         "seamless to none to make it anyway, or import a tile that wraps",
                         "make.seamless", asset=name)
    if kind == "background" and recipe["layers"] > 1:
        raise ForgeError(f"{name}: slicing a scene into parallax layers is not built yet; make it with "
                         "layers 1, or import the layers", "make.layers", asset=name)

    style = project["style"]
    family = _family(host, recipe.get("family") or style["family"])
    canvas = family.get("canvas") or {}
    aspects = canvas.get("aspects") or {"1:1": 1.0}
    size = recipe["size"] or [1024, 1024]
    aspect = nearest_aspect(size, aspects)
    edge = max(canvas.get("min_short_edge", 512), min(canvas.get("max_short_edge", 2048), min(size)))

    own = [_picture(base, project, r) for r in recipe["references"]]
    looks = [_picture(base, project, r) for r in style["references"]]
    pictures = [{"filename": f, "as": "ref"} for f in own + looks]

    tail = [_sentence(style["clause"])]
    if looks:
        tail.append(STYLE_REFS.format(cites=_cite(range(len(own) + 1, len(own) + len(looks) + 1))))
    if recipe["alpha"]:
        tail.append(ALPHA)
    lead = [SHEET] if kind == "character" else []

    items = recipe.get("set") or recipe.get("tiles") or []
    subjects = [(f"{i + 1:02d}-{item}", f"{_words(item)}.") for i, item in enumerate(items)] \
        or [(name, "")]
    seed = styles.seed(recipe, style)
    out = []
    for stem, subject in subjects:
        words = " ".join(p for p in [subject, _sentence(recipe["prompt"]), *lead, *tail] if p)
        body = {"family": family["id"], "still": True, "prompt": words, "pictures": pictures,
                "aspect": aspect, "short_edge": edge, "seed": seed, "fast": bool(fast),
                "loras": [dict(l) for l in style["loras"]]}
        if quality:
            body["quality"] = quality
        out.append({"stem": stem, "body": body})
    return out


# ---- takes on disk ------------------------------------------------------------------


def _take_dir(base, project_name, asset, take):
    return projects.inside(projects.folder(base, project_name), TAKES, asset, take)


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError):
        return None


def _write(where, take):
    with open(os.path.join(where, TAKE_FILE) + ".tmp", "w", encoding="utf-8") as handle:
        handle.write(json.dumps(take, indent=2, ensure_ascii=False) + "\n")
    os.replace(os.path.join(where, TAKE_FILE) + ".tmp", os.path.join(where, TAKE_FILE))


def takes(base, project_name, asset=None):
    """Every take of a project (or of one asset), oldest first."""
    root = projects.inside(projects.folder(base, project_name), TAKES)
    out = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if asset and name != asset:
            continue
        for take in sorted(os.listdir(os.path.join(root, name))):
            data = _read(os.path.join(root, name, take, TAKE_FILE))
            if data:
                out.append(data)
    return sorted(out, key=lambda t: t["queued"])


def _new_id():
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


def start(host, base, project_name, names=None, missing=False, stale=False, dry_run=False,
          fast=False, quality=None):
    """Queue renders for the named assets, or every planned (`missing`) or stale
    one. -> `{takes, skipped}`; with `dry_run`, what would be queued instead.

    Named assets are all checked before anything is queued, so a request with
    one asset that cannot be made queues nothing. Assets picked by `missing`
    or `stale` that cannot be made are skipped and said, so one sound in a
    plan does not stop the pictures."""
    collect(host, base, project_name)
    project = projects.load(base, project_name)
    rows = {row["name"]: row for row in projects.status(base, project_name)["assets"]}
    busy = {t["asset"] for t in takes(base, project_name) if t["state"] == "queued"}
    if names:
        chosen = [projects.find(project, n) for n in dict.fromkeys(names)]
        explicit = True
    else:
        if not (missing or stale):
            raise ForgeError("say which assets to make, or missing or stale", "request.missing", field="assets")
        wanted = ({"planned"} if missing else set()) | ({"stale"} if stale else set())
        chosen = [r for r in project["assets"] if rows[r["name"]]["status"] in wanted]
        explicit = False

    planned, skipped = [], []
    for recipe in chosen:
        try:
            if recipe["name"] in busy:
                raise ForgeError(f"{recipe['name']} is already being made; wait for its take",
                                 "make.busy", asset=recipe["name"])
            planned.append((recipe, plan(host, base, project, recipe, fast, quality)))
        except ForgeError as problem:
            if explicit:
                raise
            skipped.append({"asset": recipe["name"], "why": problem.problem, "code": problem.code})

    if dry_run:
        return {"dry_run": True, "skipped": skipped,
                "takes": [{"asset": r["name"], "renders": [{"stem": p["stem"], **p["body"]} for p in renders]}
                          for r, renders in planned]}

    out = []
    for recipe, renders in planned:
        take_id = _new_id()
        where = _take_dir(base, project_name, recipe["name"], take_id)
        os.makedirs(where)
        take = {"take": take_id, "project": project_name, "asset": recipe["name"], "kind": recipe["kind"],
                "at": projects.now(), "queued": time.time(), "state": "queued", "recipe": recipe, "style": project["style"],
                "renders": [], "warnings": []}
        # `where` is resolved (`projects.inside`), so the base it is measured
        # from must be too, or an output folder behind a symlink names a
        # prefix full of `..` that the render route refuses.
        rel = os.path.relpath(where, os.path.realpath(base)).replace(os.sep, "/")
        try:
            for render in renders:
                body = {**render["body"], "output_prefix": f"{FORGE_SHELF}/{rel}/{render['stem']}"}
                queued = host.render(body)
                take["renders"].append({"stem": render["stem"], "prompt_id": queued["prompt_id"],
                                        "speed": queued.get("speed"), "seed": body["seed"],
                                        "prompt": body["prompt"], "family": body["family"]})
        except ForgeError as problem:
            # What was queued before the refusal still runs; the take says what
            # it asked for and why the rest is not coming.
            take.update(state="failed", problem=problem.problem, code=problem.code)
            _write(where, take)
            if not take["renders"]:
                raise
            out.append(take)
            break
        _write(where, take)
        out.append(take)
    return {"takes": out, "skipped": skipped}


def _landed(where, stem):
    """The file the save node wrote for `stem` in a take, or None."""
    names = sorted(n for n in os.listdir(where) if n.startswith(f"{stem}_") and n.endswith(".png"))
    return names[-1] if names else None


def _fit(rgba, recipe):
    """A render at the recipe's size: padded with transparency to the shape
    where the asset has alpha (the subject is never cut), cropped where it is
    a scene (padding would put a border of nothing into the game)."""
    from .post import image

    size = recipe["size"]
    if not size:
        return rgba
    aspect = size[0] / size[1]
    shaped = image.pad_to_aspect(rgba, aspect, "centre") if recipe["alpha"] else image.crop_to_aspect(rgba, aspect)
    return image.resize(shaped, size)


def _finish(host, base, project_name, where, take):
    """Every render of `take` is on disk: fit them, make them the masters."""
    from .post import image

    recipe = take["recipe"]
    sources = {}
    fitted = os.path.join(where, "fitted")
    os.makedirs(fitted, exist_ok=True)
    for render in take["renders"]:
        rgba = image.read(os.path.join(where, render["file"]))
        if recipe["alpha"] and int(rgba[..., 3].min()) == 255:
            take["warnings"].append({"stem": render["stem"], "code": "make.opaque",
                                     "problem": f"{render['file']} came back with no transparency; "
                                                f"{render['family']} may not draw alpha, and the build "
                                                "will refuse it until it is matted"})
        filename = f"{render['stem']}.png" if len(take["renders"]) > 1 else f"{recipe['name']}.png"
        path = os.path.join(fitted, filename)
        with open(path, "wb") as handle:
            handle.write(image.png(_fit(rgba, recipe)))
        sources[filename] = path
    try:
        projects.put_masters(base, project_name, recipe["name"], sources, source="made",
                             made_from=(recipe, take["style"]))
    except ForgeError as problem:
        # The asset was removed (or renamed by remove-and-add) while the
        # render was on the queue: the take keeps its files and says why.
        take.update(state="failed", problem=problem.problem, code=problem.code)
        return
    take.update(state="done", finished=projects.now(), masters=sorted(sources))


def collect(host, base, project_name):
    """Bring every queued take that has landed into its asset. -> the takes
    whose state changed."""
    changed = []
    with projects.LOCK:
        for take in takes(base, project_name):
            if take["state"] != "queued":
                continue
            where = _take_dir(base, project_name, take["asset"], take["take"])
            for render in take["renders"]:
                render["file"] = render.get("file") or _landed(where, render["stem"])
            waiting = [r for r in take["renders"] if not r["file"]]
            if not waiting:
                _finish(host, base, project_name, where, take)
            else:
                # The first render still out decides: queued or running means
                # wait; anything else means it is not coming.
                state, message = host.prompt_state(waiting[0]["prompt_id"])
                if state in ("queued", "running"):
                    continue
                if state == "failed":
                    take.update(state="failed", code="make.failed", problem=message)
                elif state == "done":
                    take.update(state="failed", code="make.astray",
                                problem=f"the render finished but {waiting[0]['stem']} never landed in "
                                        f"{TAKES}/{take['asset']}/{take['take']}; it was saved somewhere else")
                else:
                    take.update(state="failed", code="make.lost",
                                problem="ComfyUI no longer knows this render and it never landed: it was "
                                        "cancelled, or the server restarted before it finished")
            _write(where, take)
            changed.append(take)
    return changed
