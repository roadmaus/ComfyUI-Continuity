"""A forge project on disk: storage, versions, the plan merge and status.

    <base>/<project>/
      project.json         style, targets, and the asset list (every recipe)
      MANIFEST.md          written from project.json on every save
      style/               reference pictures, swatches
      assets/<kind>/<name>/
        recipe.json        the recipe the files below were made from
        masters/           the large originals, with alpha
        variants/          directions, frames, expressions, costumes, maps, takes
      build/<target>/      engine-ready output, regenerated from masters
      .versions/           every set a later write replaced

`<base>` is `output/continuity/forge` on a running ComfyUI (`outputs.FORGE`);
every function here takes it as an argument, so the suites run on a temporary
folder and nothing here imports ComfyUI.

**Two recipes per asset, on purpose.** `project.json` holds the recipe as it is
*now* — what the plan says. `assets/<kind>/<name>/recipe.json` holds the recipe
the files were *made from*, written in the same swap as the files. Staleness is
the two disagreeing (spec §5.4), and needs no bookkeeping beyond that.

**Writes are safe** (§2). Names match one pattern and every path is joined
under the project and checked to stay there. A set of files is staged beside
its destination and swapped in with `os.replace`; whatever it replaces moves to
`.versions/` under a number first. Nothing in this module deletes a file the
user made: `remove` is a move.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading

from . import kinds, style as styles, targets
from .problems import ForgeError

NAME = re.compile(r"\A[a-z0-9][a-z0-9_-]{0,63}\Z")
FORMAT = 1

PROJECT_FILE = "project.json"
MANIFEST_FILE = "MANIFEST.md"
RECIPE_FILE = "recipe.json"
VIEWED_FILE = ".viewed.json"
BUILT_FILE = ".built.json"
VERSIONS = ".versions"

# One lock for every write. Handlers run on the executor's threads, and two
# edits to one project.json must not interleave; the forge is not busy enough
# for a lock per project to be worth the bookkeeping.
LOCK = threading.RLock()


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def check_name(name, what="name"):
    if not isinstance(name, str) or not NAME.match(name):
        raise ForgeError(f"{name!r} is not a usable {what}: lowercase letters, digits, - and _, "
                         "starting with a letter or digit, at most 64", f"{what}.invalid", name=name)
    return name


def inside(root, *parts):
    """`root/parts…`, refused if it would land outside `root`."""
    path = os.path.realpath(os.path.join(root, *parts))
    top = os.path.realpath(root)
    if path != top and os.path.commonpath([path, top]) != top:
        raise ForgeError("that path leads outside the project", "path.outside")
    return path


def folder(base, name):
    return inside(base, check_name(name, "project"))


# ---- versioned writes ----------------------------------------------------------


def _next_version(where):
    taken = [int(n.split(".")[0]) for n in os.listdir(where) if n.split(".")[0].isdigit()] \
        if os.path.isdir(where) else []
    return max(taken, default=0) + 1


def _retire(root, path):
    """Move `path` (a file or a folder under `root`) into `.versions/`, numbered.
    -> where it went, or None when there was nothing there."""
    if not os.path.lexists(path):
        return None
    rel = os.path.relpath(path, root)
    shelf = inside(root, VERSIONS, rel)
    os.makedirs(shelf, exist_ok=True)
    ext = os.path.splitext(path)[1] if os.path.isfile(path) else ""
    dest = os.path.join(shelf, f"{_next_version(shelf):04d}{ext}")
    os.replace(path, dest)
    return dest


def write_file(root, rel, data):
    """Write one file under `root`; the file it replaces is kept as a version."""
    path = inside(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".staging-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        if os.path.exists(path):
            _retire(root, path)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def write_derived(root, rel, data):
    """Write a file that is regenerated from others (build/, check overlays,
    contact sheets): swapped in whole, but not kept as a version — the next
    export makes it again, so the old one would be a copy of a copy."""
    path = inside(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".staging-")
    with os.fdopen(fd, "wb") as handle:
        handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.replace(tmp, path)
    return path


def safe_file(name):
    """A frame or layer name as a file name: anything but letters, digits,
    `.`, `-` and `_` becomes `_`, so a name cannot make a path."""
    cleaned = re.sub(r"[^\w.-]", "_", name).lstrip(".")
    return cleaned or "_"


def swap_folder(root, rel, fill):
    """Replace the folder `root/rel` with a new set, as one swap.

    `fill(staging)` writes the new set into an empty folder beside the
    destination; then the old folder is retired to `.versions/` and the staged
    one renamed into place. A `fill` that raises leaves the old set untouched.
    """
    path = inside(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    staging = tempfile.mkdtemp(dir=os.path.dirname(path), prefix=".staging-")
    try:
        fill(staging)
        _retire(root, path)
        os.replace(staging, path)
    finally:
        if os.path.isdir(staging):
            shutil.rmtree(staging)
    return path


def _dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


# ---- the project ----------------------------------------------------------------


def listing(base):
    """Every project under `base`: name, mode, targets, asset count."""
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if not NAME.match(name):
            continue
        data = _read_json(os.path.join(base, name, PROJECT_FILE))
        if not isinstance(data, dict):
            continue
        out.append({"name": name, "mode": data.get("style", {}).get("mode"),
                    "targets": data.get("targets", []), "assets": len(data.get("assets", []))})
    return out


def load(base, name):
    path = os.path.join(folder(base, name), PROJECT_FILE)
    data = _read_json(path)
    if data is None:
        raise ForgeError(f"there is no project called {name!r}", "project.missing", status=404, project=name)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ForgeError(f"{name}/project.json is not a forge project this version can read",
                         "project.format", project=name)
    return data


def save(base, project):
    """Write project.json (keeping the last one as a version) and MANIFEST.md."""
    from . import manifest

    root = folder(base, project["name"])
    project["updated"] = now()
    with LOCK:
        write_file(root, PROJECT_FILE, _dump(project))
        # The manifest is derived, so the one it replaces is not worth keeping:
        # project.json's own version already says what it said.
        path = inside(root, MANIFEST_FILE)
        with open(path + ".tmp", "w", encoding="utf-8") as handle:
            handle.write(manifest.render(base, project))
        os.replace(path + ".tmp", path)
    return project


def create(base, name, mode=None, target_ids=(), style=None):
    root = folder(base, name)
    with LOCK:
        if os.path.exists(os.path.join(root, PROJECT_FILE)):
            raise ForgeError(f"there is already a project called {name!r}", "project.exists",
                             status=409, project=name)
        chosen = list(dict.fromkeys(target_ids or ["generic"]))
        for target in chosen:
            targets.require_target(target)
        settings = dict(style or {})
        if mode:
            settings["mode"] = mode
        settings = styles.normalise(settings)
        # A pixel project for a Game Boy starts on the Game Boy's greens and its
        # 8-pixel tiles drawn eight master pixels wide, rather than on nothing.
        if settings["mode"] == "pixel" and any(targets.TARGETS[t].get("pixel") for t in chosen):
            settings["palette"] = settings["palette"] or list(targets.DMG_PALETTE)
            settings["grid"] = settings["grid"] or 8
        for sub in ("style", "assets", "build"):
            os.makedirs(os.path.join(root, sub), exist_ok=True)
        project = {"format": FORMAT, "name": name, "created": now(), "updated": None,
                   "style": settings, "targets": chosen, "assets": []}
        return save(base, project)


def set_style(base, name, changes):
    with LOCK:
        project = load(base, name)
        project["style"] = styles.normalise(changes, project["style"])
        return save(base, project)


def add_target(base, name, target):
    targets.require_target(target)
    with LOCK:
        project = load(base, name)
        if target not in project["targets"]:
            project["targets"].append(target)
            save(base, project)
        return project


def remove_target(base, name, target):
    """Stops exporting to `target`. Its build folder stays where it is."""
    with LOCK:
        project = load(base, name)
        if target not in project["targets"]:
            raise ForgeError(f"{name} does not export to {target}", "project.target", target=target)
        if len(project["targets"]) == 1:
            raise ForgeError("a project needs at least one target", "project.target", target=target)
        project["targets"].remove(target)
        return save(base, project)


# ---- assets ------------------------------------------------------------------------


def find(project, asset):
    for recipe in project["assets"]:
        if recipe["name"] == asset:
            return recipe
    raise ForgeError(f"{project['name']} has no asset called {asset!r}", "asset.missing",
                     status=404, asset=asset)


def asset_dir(base, project, recipe):
    return inside(folder(base, project["name"]), "assets", recipe["kind"], recipe["name"])


def _recipe(entry):
    check_name(entry.get("name") if isinstance(entry, dict) else None, "asset")
    return kinds.normalise(entry)


def merge_plan(base, name, plan):
    """Merge a plan into the project, by asset name. Idempotent.

    A plan is `{"style"?, "targets"?, "assets": [recipe…]}`. Each recipe in it
    *is* that asset's recipe — fields it leaves out take their defaults — so a
    plan applied twice changes nothing, and editing one entry changes (and
    stales) only that asset. Assets the plan does not name are left alone: a
    plan adds and changes, it never removes. Targets are only ever added.

    The whole plan is checked before anything is written, so a plan with one
    bad entry changes nothing.
    """
    if not isinstance(plan, dict):
        raise ForgeError("a plan is a JSON object with an \"assets\" list", "plan.shape")
    unknown = sorted(set(plan) - {"style", "targets", "assets"})
    if unknown:
        raise ForgeError("a plan has style, targets and assets; not " + ", ".join(unknown),
                         "plan.shape", fields=unknown)
    entries = plan.get("assets", [])
    if not isinstance(entries, list):
        raise ForgeError("a plan's assets must be a list", "plan.shape")
    recipes = [_recipe(entry) for entry in entries]
    seen = set()
    for recipe in recipes:
        if recipe["name"] in seen:
            raise ForgeError(f"the plan names {recipe['name']!r} twice", "plan.duplicate", asset=recipe["name"])
        seen.add(recipe["name"])
    new_targets = plan.get("targets", [])
    if not isinstance(new_targets, list):
        raise ForgeError("a plan's targets must be a list", "plan.shape")
    for target in new_targets:
        targets.require_target(target)

    report = {"added": [], "changed": [], "unchanged": [], "style": False, "targets": []}
    with LOCK:
        project = load(base, name)
        if "style" in plan:
            settings = styles.normalise(plan["style"], project["style"])
            report["style"] = settings != project["style"]
            project["style"] = settings
        for target in new_targets:
            if target not in project["targets"]:
                project["targets"].append(target)
                report["targets"].append(target)
        current = {r["name"]: i for i, r in enumerate(project["assets"])}
        for recipe in recipes:
            at = current.get(recipe["name"])
            if at is None:
                project["assets"].append(recipe)
                report["added"].append(recipe["name"])
                continue
            old = project["assets"][at]
            if old["kind"] != recipe["kind"]:
                raise ForgeError(f"{recipe['name']!r} is a {old['kind']}, not a {recipe['kind']}; "
                                 "remove it first to make it something else",
                                 "asset.kind", asset=recipe["name"])
            if old == recipe:
                report["unchanged"].append(recipe["name"])
            else:
                project["assets"][at] = recipe
                report["changed"].append(recipe["name"])
        if report["added"] or report["changed"] or report["style"] or report["targets"]:
            save(base, project)
    return report


def add_asset(base, name, entry):
    recipe = _recipe(entry)
    with LOCK:
        project = load(base, name)
        if any(r["name"] == recipe["name"] for r in project["assets"]):
            raise ForgeError(f"{name} already has an asset called {recipe['name']!r}; "
                             "edit it, or plan it", "asset.exists", status=409, asset=recipe["name"])
        project["assets"].append(recipe)
        save(base, project)
    return recipe


def edit_asset(base, name, asset, changes):
    """Change some fields of one asset's recipe; the rest stay as they are."""
    if not isinstance(changes, dict):
        raise ForgeError("changes must be a JSON object of fields", "recipe.shape")
    if "name" in changes and changes["name"] != asset:
        raise ForgeError("an asset cannot be renamed; remove it and add it again", "asset.rename",
                         asset=asset)
    with LOCK:
        project = load(base, name)
        old = find(project, asset)
        if "kind" in changes and changes["kind"] != old["kind"]:
            raise ForgeError(f"{asset!r} is a {old['kind']}; remove it first to make it something else",
                             "asset.kind", asset=asset)
        recipe = kinds.normalise({**old, **changes})
        project["assets"][project["assets"].index(old)] = recipe
        save(base, project)
    return recipe


def remove_asset(base, name, asset):
    """Take an asset out of the project. Its files move to `.versions/`."""
    with LOCK:
        project = load(base, name)
        recipe = find(project, asset)
        moved = _retire(folder(base, name), asset_dir(base, project, recipe))
        project["assets"].remove(recipe)
        save(base, project)
    root = folder(base, name)
    return {"removed": asset, "kept": os.path.relpath(moved, root) if moved else None}


# ---- what an asset was made from, and whether it still is --------------------------


def fingerprint(project, recipe, source="made"):
    """A short hash of everything that decides what an asset looks like.

    For a made asset that is its costly fields, its effective seed and family,
    its full prompt and the style it was made under. For an imported one, the
    style had no say in the picture, so only the recipe counts: restyling a
    project does not ask anyone to redraw a file they brought in.
    """
    style = project["style"]
    data = {"recipe": kinds.costly(recipe)}
    if source != "import":
        data["recipe"]["seed"] = styles.seed(recipe, style)
        data["recipe"]["family"] = recipe.get("family") or style["family"]
        data["prompt"] = styles.prompt(recipe, style)
        data["style"] = {k: style[k] for k in ("mode", "references", "loras", "palette", "grid",
                                                "texel_density")}
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _files(path):
    if not os.path.isdir(path):
        return []
    return sorted(n for n in os.listdir(path) if not n.startswith("."))


def state(base, project, recipe):
    """One asset's row of `status`: planned / made / exported / stale."""
    where = asset_dir(base, project, recipe)
    made = _read_json(os.path.join(where, RECIPE_FILE))
    masters = _files(os.path.join(where, "masters"))
    row = {"name": recipe["name"], "kind": recipe["kind"], "masters": masters,
           "seed": styles.seed(recipe, project["style"]),
           "family": recipe.get("family") or project["style"]["family"]}
    if not made or not masters:
        return {**row, "status": "planned", "viewed": False, "made": None, "source": None, "exported": []}
    source = made.get("source", "made")
    current = fingerprint(project, recipe, source)
    viewed = _read_json(os.path.join(where, VIEWED_FILE), {})
    row.update(made=made.get("at"), source=source, viewed=viewed.get("hash") == made.get("hash"))
    if made.get("hash") != current:
        return {**row, "status": "stale", "exported": []}
    root = folder(base, project["name"])
    exported = [t for t in project["targets"]
                if (_read_json(inside(root, "build", t, BUILT_FILE), {}) or {}).get(recipe["name"]) == current]
    status = "exported" if exported and len(exported) == len(project["targets"]) else "made"
    return {**row, "status": status, "exported": exported}


def status(base, name):
    project = load(base, name)
    rows = [state(base, project, recipe) for recipe in project["assets"]]
    counts = {key: 0 for key in ("planned", "made", "exported", "stale")}
    for row in rows:
        counts[row["status"]] += 1
    counts["unviewed"] = sum(1 for row in rows if row["status"] != "planned" and not row["viewed"])
    return {"project": name, "counts": counts, "assets": rows}


def put_masters(base, name, asset, sources, source="import"):
    """Make `sources` (`{filename: absolute path}`) the asset's masters, as one
    versioned swap, with the recipe they now stand for beside them."""
    if not sources:
        raise ForgeError("nothing to put in the masters", "import.empty", asset=asset)
    for filename in sources:
        if not re.match(r"\A[\w.-]{1,128}\Z", filename) or filename.startswith("."):
            raise ForgeError(f"{filename!r} is not a usable file name", "import.name", asset=asset)
    with LOCK:
        project = load(base, name)
        recipe = find(project, asset)
        root = folder(base, name)
        where = asset_dir(base, project, recipe)
        made = {"recipe": recipe, "source": source, "at": now(),
                "hash": fingerprint(project, recipe, source), "files": sorted(sources)}
        if source != "import":
            made["style"] = project["style"]
            made["prompt"] = styles.prompt(recipe, project["style"])

        def fill(staging):
            masters = os.path.join(staging, "masters")
            os.makedirs(masters)
            for filename, path in sources.items():
                shutil.copyfile(path, os.path.join(masters, filename))
            # Variants were made from the masters being replaced; they go with
            # them into the version rather than outliving what they vary.
            with open(os.path.join(staging, RECIPE_FILE), "w", encoding="utf-8") as handle:
                handle.write(_dump(made))

        swap_folder(root, os.path.relpath(where, root), fill)
        save(base, project)
    return state(base, project, recipe)


def mark_viewed(base, name, asset):
    """Record that somebody looked at what an asset is now (spec §13)."""
    with LOCK:
        project = load(base, name)
        recipe = find(project, asset)
        where = asset_dir(base, project, recipe)
        made = _read_json(os.path.join(where, RECIPE_FILE))
        if made:
            with open(os.path.join(where, VIEWED_FILE), "w", encoding="utf-8") as handle:
                handle.write(_dump({"hash": made.get("hash"), "at": now()}))
        return state(base, project, recipe)


def history(base, name, asset):
    """The versions an asset's folder has been through, oldest first."""
    project = load(base, name)
    try:
        recipe = find(project, asset)
        kind = recipe["kind"]
    except ForgeError:
        # A removed asset still has a history; look for it under any kind.
        kind = next((k for k in kinds.names()
                     if os.path.isdir(inside(folder(base, name), VERSIONS, "assets", k, asset))), None)
        if kind is None:
            raise
    root = folder(base, name)
    shelf = inside(root, VERSIONS, "assets", kind, check_name(asset, "asset"))
    out = []
    for number in sorted(os.listdir(shelf)) if os.path.isdir(shelf) else []:
        made = _read_json(os.path.join(shelf, number, RECIPE_FILE)) or {}
        out.append({"version": int(number), "path": os.path.relpath(os.path.join(shelf, number), root),
                    "at": made.get("at"), "source": made.get("source"), "hash": made.get("hash"),
                    "files": _files(os.path.join(shelf, number, "masters"))})
    return {"project": name, "asset": asset, "kind": kind, "versions": out}


def files(base, name, under="", versions=False):
    """Every file in the project (or under one folder of it), relative paths."""
    root = folder(base, name)
    load(base, name)
    start = inside(root, under) if under else root
    out = []
    for here, dirs, names in os.walk(start):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".staging-")
                         and (versions or d != VERSIONS))
        for filename in sorted(names):
            if filename.startswith(".staging-"):
                continue
            path = os.path.join(here, filename)
            out.append({"path": os.path.relpath(path, root).replace(os.sep, "/"),
                        "bytes": os.path.getsize(path)})
    return sorted(out, key=lambda item: item["path"])


def file_path(base, name, rel):
    """The absolute path of one project file, for reading. Refused outside."""
    load(base, name)
    path = inside(folder(base, name), rel)
    if not os.path.isfile(path):
        raise ForgeError(f"{name} has no file {rel}", "file.missing", status=404, path=rel)
    return path
