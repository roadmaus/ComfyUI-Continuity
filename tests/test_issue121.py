"""Saved references survive being saved again, and can be redone or forgotten (#121).

    python3 tests/test_issue121.py

Three failures the reporter met building one five-sheet cast member, each
checked where it lived.

A mod lost to another. A make job named its sources `<member>`, `<member>-2`,
... counting from the first *source it was handed* — and saving a member again
hands it only the pictures not saved yet. Swap one picture, save again, and
its new mod was written as `<member>`: the first picture's file, which that
picture still cited. The face became whatever had been swapped in. A new mod
now takes a name no file on disk answers to (`routes.refmod._targets`).

A mod whose file has gone. The ledger asked the listing about it, the listing
did not have it, and the answer "listing landed" redrew the card — which asked
again. The listing endpoint was hammered and the card redrawn too fast to use.
`modRow` now asks once and redraws only when its answer changes, the ledger
says the file is gone, and `forgetMods` takes the rendition off the picture.

A mod that cannot be redone. The re-encode menu offered only the mode a mod
was not in, so a bad full encode could never be encoded full again.

Skips the server half where its imports cannot be stubbed, and itself if node
is not installed.
"""

import importlib.util
import os
import sys
import tempfile
import types

import layout
from harness import check, passed

layout.skip_without_node()


# ---- the server: a new mod never lands on an old one ---------------------------

def _routes():
    """`creator/routes/refmod.py`, with what it imports that needs ComfyUI,
    torch or aiohttp stubbed. Only the naming is exercised."""
    layout.stub_server()
    web = types.SimpleNamespace(json_response=lambda *a, **k: None, FileResponse=None)
    sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp")).web = web
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.is_within_directory = (
        lambda root, path: os.path.realpath(path).startswith(os.path.realpath(root)))
    sys.modules["folder_paths"] = folder_paths
    pkg = layout.load("refmod", "jobs", package="mmc121")
    stubs = {
        "media": types.SimpleNamespace(MediaError=Exception),
        "vaekind": types.SimpleNamespace(),
        "guard": types.SimpleNamespace(same_origin=lambda handler: handler),
    }
    for name, module in stubs.items():
        sys.modules[f"mmc121.{name}"] = module
        setattr(pkg, name, module)
    families = types.ModuleType("mmc121.families")
    families.__path__ = []
    families.registry = types.SimpleNamespace(DEFAULT_VIDEO="h3", REFMOD={})
    sys.modules["mmc121.families"] = families
    sys.modules["mmc121.families.registry"] = families.registry
    routes = types.ModuleType("mmc121.routes")
    routes.__path__ = [os.path.join(layout.PY_ROOT, "routes")]
    sys.modules["mmc121.routes"] = routes
    spec = importlib.util.spec_from_file_location(
        "mmc121.routes.refmod", os.path.join(layout.PY_ROOT, "routes", "refmod.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["mmc121.routes.refmod"] = module
    spec.loader.exec_module(module)
    return pkg.refmod, module


try:
    refmod, routes = _routes()
except Exception as exc:  # noqa: BLE001 — an import this suite cannot stub
    print(f"server half skipped ({type(exc).__name__}: {exc})")
    routes = None

if routes is not None:
    root = tempfile.mkdtemp(prefix="mmc-121-")
    refmod.roots = lambda: [root]
    os.makedirs(os.path.join(root, "cast"))

    def touch(name):
        open(os.path.join(root, *name.split("/")) + refmod.EXT, "wb").close()

    check("an empty folder: the member's own name, then numbered",
          routes._targets("anna", "cast", "h3_video", 3), ["cast/anna", "cast/anna-2", "cast/anna-3"])
    # Five sheets saved; the third swapped and saved again on its own.
    for name in ("cast/anna", "cast/anna-2", "cast/anna-3", "cast/anna-4", "cast/anna-5"):
        touch(name)
    check("saving again never writes over the first picture's mod",
          routes._targets("anna", "cast", "h3_video", 1), ["cast/anna-6"])
    os.unlink(os.path.join(root, "cast", "anna-2" + refmod.EXT))
    check("...and fills a gap a deleted mod left, never a taken name",
          routes._targets("anna", "cast", "h3_video", 2), ["cast/anna-2", "cast/anna-6"])
    check("another family's renditions are counted under their own names",
          routes._targets("anna", "cast", "flux2", 2), ["cast/anna.flux2", "cast/anna-2.flux2"])
    touch("cast/anna.flux2")
    check("...and kept from each other the same way",
          routes._targets("anna", "cast", "flux2", 1), ["cast/anna-2.flux2"])
    check("no subfolder is a name at the root",
          routes._targets("bob", "", "h3_video", 1), ["bob"])
    source = open(os.path.join(layout.PY_ROOT, "routes", "refmod.py"), encoding="utf-8").read()
    check("every job that writes a new mod takes its name from `_targets`",
          source.count(" = _targets(name, subfolder, space,"), 3)


# ---- the frontend: the listing, the ledger and the menu ------------------------

API = layout.STUBS["api.js"].replace(
    "    return { ok: true, status: 200, json: async () => ({}) };",
    """    if (String(url).startsWith("/continuity/assets?root=refmods")) {
      globalThis.__listings = (globalThis.__listings ?? 0) + 1;
      return { ok: true, status: 200, json: async () => ({ assets: [
        { path: "refmod:cast/anna", name: "anna", subfolder: "cast", kind: "image",
          size: 1, mtime: 1, mod: true, mode: "encode", tokens: 1024, grid: [1, 64, 64],
          source: "image", source_file: "anna/face.png", source_present: true },
        { path: "refmod:cast/anna-2", name: "anna-2", subfolder: "cast", kind: "image",
          size: 1, mtime: 1, mod: true, mode: "training", tokens: 576, grid: [1, 48, 48],
          source: "image", source_file: "anna/coat.png", source_present: false },
      ], folders: ["cast"], truncated: false }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };""").replace(
    "  async fetchApi(url) {", "  async fetchApi(url, options = {}) {")

SCRIPT = __import__("domshim").DOM + """
import { cost, forgetMods, missingMods, modRow, remakeRows } from "./web/creator/refmod.js";

const out = {};
const tick = () => new Promise((resolve) => setTimeout(resolve, 20));

// A card that redraws whenever it is told something changed, and asks about a
// mod whose file is gone on every draw: the loop the reporter's card was in.
let draws = 0;
const draw = () => { draws += 1; if (draws < 50) modRow("refmod:cast/gone", draw); };
out.first = String(modRow("refmod:cast/gone", draw));
for (let i = 0; i < 10; i += 1) await tick();
out.draws = draws;
out.listings = globalThis.__listings;
out.gone = String(modRow("refmod:cast/gone", draw));
out.there = modRow("refmod:cast/anna", draw)?.path ?? null;

// The ledger: five pictures, one rendition's file gone.
const entries = [
  { filename: "face.png", kind: "image", mods: { h3_video: "refmod:cast/anna" } },
  { filename: "coat.png", kind: "image", mods: { h3_video: "refmod:cast/gone", flux2: "refmod:cast/anna.flux2" } },
  { filename: "back.png", kind: "image", mods: { h3_video: "refmod:cast/gone-2" } },
];
out.missing = cost(entries, null, null).missing;
out.missingMods = missingMods(entries);

// Forgetting the missing ones: only those, only in that family.
out.forgotMissing = forgetMods(entries, "h3_video", out.missing);
out.afterMissing = entries.map((entry) => entry.mods ?? null);
// ...and the rest, for a fresh save.
out.forgotAll = forgetMods(entries, "h3_video");
out.afterAll = entries.map((entry) => entry.mods ?? null);

// The re-encode menu: a full mod can be encoded full again from its picture.
const rows = [modRow("refmod:cast/anna"), modRow("refmod:cast/anna-2")];
const picked = [];
const menu = remakeRows(rows, (mode, paths) => picked.push([mode, paths]));
out.menu = menu.map((row) => [row.label, Boolean(row.disabled)]);
menu.forEach((row) => row.onPick());
out.picked = picked;
out.onlyFull = remakeRows([rows[0]], () => {}).map((row) => [row.label, Boolean(row.disabled)]);
out.stuck = remakeRows([rows[1]], () => {}).map((row) => [row.label, Boolean(row.disabled)]);
out.stack = remakeRows([{ ...rows[0], source: "stack" }], () => {}).length;
console.log(JSON.stringify(out));
"""

with layout.pack(extra_stubs={"api.js": API}, skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target)

check("a mod is unknown before the listing lands", got["first"], "undefined")
check("a card asking about a deleted mod on every draw draws once more, not forever",
      got["draws"], 1)
check("...and the listing is asked for once", got["listings"], 1)
check("...after which the deleted mod reads as gone", got["gone"], "null")
check("...and a mod still on disk reads as itself", got["there"], "refmod:cast/anna")
check("the ledger names the renditions whose files are gone",
      got["missing"], ["refmod:cast/gone", "refmod:cast/gone-2"])
check("...as does `missingMods`", got["missingMods"], got["missing"])
check("forgetting the missing takes off only those", got["forgotMissing"], 2)
check("...in that family alone, and drops an emptied map",
      got["afterMissing"], [{"h3_video": "refmod:cast/anna"}, {"flux2": "refmod:cast/anna.flux2"}, None])
check("forgetting every one leaves the pictures plain for that family",
      (got["forgotAll"], got["afterAll"]), (1, [None, {"flux2": "refmod:cast/anna.flux2"}, None]))
check("a full mod whose picture is there can be encoded full again",
      got["onlyFull"], [["Compressed — ≈576 tokens", False], ["Full again — ≈1,024 tokens", False]])
check("a mixed set: each row takes what it can, and none is sunk by the other",
      got["picked"], [["compressed", ["refmod:cast/anna"]], ["full", ["refmod:cast/anna"]]])
check("a compressed mod whose picture is gone can be redone in neither mode",
      [disabled for _, disabled in got["stuck"]], [True, True])
check("a stack is remade by saving the member again, not from this menu", got["stack"], 0)

passed("saved references survive saving again, and can be redone or forgotten")
