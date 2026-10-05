"""Game Forge's project storage: names, versioned writes, the plan merge, status.

Runs standalone — `python3 tests/test_forge_project.py` — with no ComfyUI, no
torch and no numpy: `creator/forge/` keeps all of those out of module scope so
this suite and the CLI's parity suite can load it on a bare Python.

What is pinned is what the spec makes a promise of (§2, §5, §11.2): a plan
applied twice changes nothing and an edit to one entry stales only that asset;
nothing is ever deleted, every replaced set is kept as a numbered version; a
name or a path cannot reach outside its project; and a refusal always carries
a code an agent can branch on.
"""

import importlib.util
import json
import os
import sys
import tempfile
import types

import layout
from harness import FAILURES, check

package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
for name in ("problems", "kinds", "targets", "style", "project", "manifest", "api"):
    spec = importlib.util.spec_from_file_location(f"forgepkg.{name}",
                                                  os.path.join(layout.PY_ROOT, "forge", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"forgepkg.{name}"] = module
    spec.loader.exec_module(module)
problems = sys.modules["forgepkg.problems"]
kinds = sys.modules["forgepkg.kinds"]
style = sys.modules["forgepkg.style"]
project = sys.modules["forgepkg.project"]
ForgeError = problems.ForgeError


def refused(label, fn, code):
    try:
        fn()
    except ForgeError as exc:
        check(f"{label}: code", exc.code, code)
        check(f"{label}: has a sentence", bool(exc.problem), True)
        return exc
    FAILURES.append(f"{label}: was not refused")
    return None


base = tempfile.mkdtemp(prefix="forge-")

# ---- names and paths ----------------------------------------------------------------

for bad in ("", "Hero", "../up", "a/b", "-dash", "x" * 65, None, "dot.name"):
    refused(f"project name {bad!r}", lambda bad=bad: project.create(base, bad), "project.invalid")
refused("a path out of the project", lambda: project.inside(base, "a", "..", "..", "etc"), "path.outside")

# ---- a project --------------------------------------------------------------------

made = project.create(base, "mygame", "pixel", ["gbstudio", "godot4"])
check("targets kept in order", made["targets"], ["gbstudio", "godot4"])
check("a pixel project for a Game Boy starts on its four greens", len(made["style"]["palette"]), 4)
check("and on an 8-pixel grid", made["style"]["grid"], 8)
check("the manifest is written", os.path.isfile(os.path.join(base, "mygame", "MANIFEST.md")), True)
refused("the same name twice", lambda: project.create(base, "mygame"), "project.exists")
refused("an unknown target", lambda: project.create(base, "other", target_ids=["snes"]), "project.target")
refused("an unknown mode", lambda: project.create(base, "other", "watercolour"), "project.mode")
check("a refused project leaves no folder", os.path.exists(os.path.join(base, "other", "project.json")), False)
refused("a missing project", lambda: project.load(base, "nothere"), "project.missing")
check("listing", [p["name"] for p in project.listing(base)], ["mygame"])

# ---- the plan merge ---------------------------------------------------------------

plan = {"assets": [
    {"kind": "character", "name": "hero", "prompt": "a small knight with a red plume", "seed": 7},
    {"kind": "sprite", "name": "hero-walk", "of": "hero", "frame": [16, 16],
     "animations": [{"name": "walk", "frames": 4, "fps": 8, "loop": True}], "directions": 4},
    {"kind": "tile", "name": "grass", "prompt": "short grass", "tile": [8, 8]},
]}
first = project.merge_plan(base, "mygame", plan)
check("a first plan adds every asset", first["added"], ["hero", "hero-walk", "grass"])
again = project.merge_plan(base, "mygame", plan)
check("the same plan again changes nothing", (again["added"], again["changed"]), ([], []))
check("and says so", again["unchanged"], ["hero", "hero-walk", "grass"])

stored = project.load(base, "mygame")
hero = project.find(stored, "hero")
check("defaults are filled in", (hero["size"], hero["directions"], hero["layer"]), ([1024, 1024], 1, 0))

refused("an unknown field", lambda: project.merge_plan(base, "mygame", {"assets": [
    {"kind": "tile", "name": "x", "frame_count": 3}]}), "recipe.unknown")
refused("a field out of range", lambda: project.merge_plan(base, "mygame", {"assets": [
    {"kind": "sprite", "name": "x", "directions": 3}]}), "recipe.field")
refused("an unknown kind", lambda: project.merge_plan(base, "mygame", {"assets": [
    {"kind": "level", "name": "x"}]}), "asset.kind")
refused("a bad asset name", lambda: project.merge_plan(base, "mygame", {"assets": [
    {"kind": "tile", "name": "Grass Tile"}]}), "asset.invalid")
refused("a name twice in one plan", lambda: project.merge_plan(base, "mygame", {"assets": [
    {"kind": "tile", "name": "x"}, {"kind": "tile", "name": "x"}]}), "plan.duplicate")
refused("a kind changed under a name", lambda: project.merge_plan(base, "mygame", {"assets": [
    {"kind": "tile", "name": "hero"}]}), "asset.kind")
refused("a plan with an unknown key", lambda: project.merge_plan(base, "mygame", {"assetz": []}), "plan.shape")
# A plan with one bad entry writes nothing — not even its good entries.
before = json.dumps(project.load(base, "mygame")["assets"])
refused("a half-bad plan", lambda: project.merge_plan(base, "mygame", {"assets": [
    {"kind": "tile", "name": "fine"}, {"kind": "tile", "name": "bad", "tile": [0, 8]}]}), "recipe.field")
check("a half-bad plan changes nothing", json.dumps(project.load(base, "mygame")["assets"]), before)

# ---- import, status, staleness ------------------------------------------------------

source = os.path.join(base, "hero.png")
with open(source, "wb") as handle:
    handle.write(b"\x89PNG not really")

check("planned before anything is made", project.status(base, "mygame")["counts"]["planned"], 3)
row = project.put_masters(base, "mygame", "hero", {"hero.png": source})
check("an import makes it made", row["status"], "made")
check("and not yet looked at", row["viewed"], False)
check("the master is in place",
      os.path.isfile(os.path.join(base, "mygame", "assets", "character", "hero", "masters", "hero.png")), True)
check("viewed once marked", project.mark_viewed(base, "mygame", "hero")["viewed"], True)

# Notes and export overrides never change what is made.
project.edit_asset(base, "mygame", "hero", {"notes": "the plume is the silhouette", "targets": {"godot4": {}}})
check("a note does not stale", project.state(base, stored, project.find(project.load(base, "mygame"), "hero"))
      ["status"], "made")
project.edit_asset(base, "mygame", "hero", {"prompt": "a small knight with a blue plume"})
counts = project.status(base, "mygame")["counts"]
check("an edited prompt stales only that asset", (counts["stale"], counts["planned"]), (1, 2))

# An imported asset is not staled by a restyle; a made one would be.
fresh = project.edit_asset(base, "mygame", "hero", {"prompt": "a small knight with a red plume"})
project.put_masters(base, "mygame", "hero", {"hero.png": source})
project.set_style(base, "mygame", {"clause": "16-colour pixel art, black outlines"})
check("a restyle leaves an import alone", project.status(base, "mygame")["assets"][0]["status"], "made")
project.put_masters(base, "mygame", "grass", {"grass.png": source}, source="made")
project.set_style(base, "mygame", {"clause": "8-colour pixel art"})
grass = [r for r in project.status(base, "mygame")["assets"] if r["name"] == "grass"][0]
check("a restyle stales a made asset", grass["status"], "stale")

# ---- versions: nothing is lost --------------------------------------------------------

versions = project.history(base, "mygame", "hero")["versions"]
check("the replaced masters were kept", len(versions), 1)
check("with their file", versions[0]["files"], ["hero.png"])
kept = project.remove_asset(base, "mygame", "hero")
check("rm keeps the files", os.path.isdir(os.path.join(base, "mygame", kept["kept"])), True)
check("rm takes it out of the plan", [a["name"] for a in project.load(base, "mygame")["assets"]],
      ["hero-walk", "grass"])
check("a removed asset still has a history", len(project.history(base, "mygame", "hero")["versions"]), 2)
check("project.json is versioned too",
      len(os.listdir(os.path.join(base, "mygame", ".versions", "project.json"))) > 3, True)
check("no staging folder is left behind",
      [n for _, d, f in os.walk(os.path.join(base, "mygame")) for n in d + f if n.startswith(".staging-")], [])

# ---- targets ------------------------------------------------------------------------

project.add_target(base, "mygame", "love")
project.add_target(base, "mygame", "love")
check("a target added twice is there once", project.load(base, "mygame")["targets"], ["gbstudio", "godot4", "love"])
project.remove_target(base, "mygame", "love")
project.remove_target(base, "mygame", "godot4")
refused("the last target", lambda: project.remove_target(base, "mygame", "gbstudio"), "project.target")

# ---- the schema is the validator's ----------------------------------------------------

for kind in kinds.names():
    schema = kinds.schema(kind)
    fields = set(schema["properties"]) - {"name", "kind"}
    check(f"{kind}: schema names every field", fields, {f.name for f in kinds.fields(kind)})
    kinds.normalise({"kind": kind, "name": "x"})  # every kind's defaults pass its own checks

# ---- style --------------------------------------------------------------------------

check("the prompt ends with the clause", style.prompt({"prompt": "a knight."}, {"clause": "pixel art"}),
      "a knight. pixel art")
derived = style.seed({"name": "grass", "seed": None}, {"seed": 1})
check("a derived seed is fixed", derived, style.seed({"name": "grass", "seed": None}, {"seed": 1}))
check("and differs by name", derived != style.seed({"name": "sand", "seed": None}, {"seed": 1}), True)
refused("a bad palette", lambda: style.normalise({"palette": ["green"]}), "style.field")
refused("an unknown style field", lambda: style.normalise({"colour": 1}), "style.unknown")

# ---- the manifest -------------------------------------------------------------------

with open(os.path.join(base, "mygame", "MANIFEST.md"), encoding="utf-8") as handle:
    manifest = handle.read()
check("the manifest lists the assets", "**hero-walk**" in manifest and "**grass**" in manifest, True)
check("with their full prompts", "short grass. 8-colour pixel art" in manifest, True)
check("and their status", "| stale |" in manifest, True)
