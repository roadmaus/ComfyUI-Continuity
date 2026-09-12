"""The library's Cast tab is where RefMods live: the Saved references panel.

A RefMod is a file somebody carries between machines, and a folder reachable
only over ssh is not a library. So the Cast tab's right-hand column — the
inspector elsewhere, and empty on the roster since a card opens its own page —
lists every mod on the machine, says who is built out of it, and is where one
becomes a member, hangs on a member, is renamed, or leaves.

    python3 tests/test_refmod_library.py

Skips itself if node is not installed. Mounts the library with no target, like
`test_cast_editor`, over a stub API that answers the mod listing and the file
routes, and reads the roster back out of userdata.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)

from domshim import DOM  # noqa: E402

STUBS = {
    "app.js": "export const app = { registerExtension() {}, extensionManager: null };",
    "api.js": """
const store = new Map();
globalThis.__calls = [];
const mods = [
  { path: "refmod:cast/anna", name: "anna", subfolder: "cast", kind: "image", size: 1, mtime: 1,
    mod: true, mode: "training", tokens: 64, grid: [1, 16, 16], description: "a woman in a green coat",
    foreign: false, preview: true },
  { path: "refmod:vanellope_example", name: "vanellope_example", subfolder: "", kind: "image", size: 1,
    mtime: 1, mod: true, mode: "encode", tokens: 1024, grid: [1, 64, 64], description: "", foreign: true,
    preview: false },
];
globalThis.__mods = mods;
export const api = {
  apiURL: (u) => u,
  addEventListener() {}, removeEventListener() {},
  async fetchApi(url, options = {}) {
    if (String(url).startsWith("/continuity/families")) {
      const body = (await import("node:fs")).readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
    }
    if (String(url).startsWith("/continuity/assets?root=refmods")) {
      return { ok: true, status: 200, json: async () => ({ assets: mods, folders: ["cast"], truncated: false }) };
    }
    if (String(url).startsWith("/continuity/refmod/move")) {
      const body = JSON.parse(options.body);
      globalThis.__calls.push(["move", body]);
      const row = mods.find((m) => m.path === body.filename);
      row.path = "refmod:" + body.name; row.name = body.name.split("/").pop();
      row.subfolder = body.name.includes("/") ? body.name.split("/").slice(0, -1).join("/") : "";
      return { ok: true, status: 200, json: async () => row };
    }
    if (String(url).startsWith("/continuity/refmod/upload")) {
      globalThis.__calls.push(["upload", null]);
      const row = { path: "refmod:hero_visual", name: "hero_visual", subfolder: "", kind: "video", size: 1,
                    mtime: 3, mod: true, mode: "training", source: "stack", tokens: 2816, grid: [44, 16, 16],
                    description: "a girl with candy in her hair", foreign: true, preview: false };
      mods.push(row);
      return { ok: true, status: 200, json: async () => row };
    }
    if (String(url).startsWith("/continuity/refmod/make")) {
      const body = JSON.parse(options.body);
      globalThis.__calls.push(["make", body]);
      const row = { path: `refmod:cast/${body.name}`, name: body.name, subfolder: "cast", kind: "video",
                    size: 1, mtime: 2, mod: true, mode: "training", source: "stack", tokens: 448,
                    grid: [7, 16, 16], description: body.description, foreign: false, preview: true };
      mods.push(row);
      return { ok: true, status: 200, json: async () => ({ result: { mods: [row] } }) };
    }
    if (String(url).startsWith("/continuity/refmod/")) {
      globalThis.__calls.push([String(url), options.body ? JSON.parse(options.body) : null]);
      return { ok: true, status: 200, json: async () => ({ ok: true }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  },
  async getUserData(file) {
    return store.has(file)
      ? { status: 200, json: async () => JSON.parse(store.get(file)) }
      : { status: 404, json: async () => null };
  },
  async storeUserData(file, value) { store.set(file, JSON.stringify(value)); return { status: 200 }; },
  async deleteUserData(file) { store.delete(file); return { status: 204 }; },
};
""",
    "widgets.js": "export const ComfyWidgets = {};",
}

CHECK = r"""
await import("./dom.mjs");
const { openPresetLibrary } = await import("./web/creator/presetlib.js");
const P = await import("./web/creator/presets.js");

const out = { errors: [] };
const wait = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 6; i += 1) await wait(); };
function all(root, cls) {
  const found = [];
  const walk = (node) => {
    if (String(node.className ?? "").split(" ").includes(cls)) found.push(node);
    (node.children ?? []).forEach(walk);
  };
  walk(root);
  return found;
}
const one = (root, cls) => all(root, cls)[0] ?? null;
const text = (node) => node.text.replace(/\s+/g, " ").trim();

try {
  openPresetLibrary({ scope: "cast" });
  await settle();
  const modal = one(globalThis.document.body, "mmc-modal");
  if (!modal) throw new Error("the library did not mount");
  const lib = globalThis.__lib;

  // ---- the panel ---------------------------------------------------------
  const panel = one(modal, "mmc-mod-panel");
  out.panel = {
    there: Boolean(panel),
    title: one(panel, "mmc-preset-insp-title")?.textContent ?? null,
    folders: all(panel, "mmc-mod-folder").map((n) => n.textContent),
    rows: all(panel, "mmc-mod-row").map((row) => [
      one(row, "mmc-mod-name")?.textContent, one(row, "mmc-mod-facts")?.textContent, text(one(row, "mmc-mod-who"))]),
    importText: text(one(panel, "mmc-mod-panel-import")),
  };
  // The bar's Import takes both kinds on this tab.
  out.importAccept = null;
  const origCreate = globalThis.document.createElement;

  // ---- a member out of a foreign mod ----------------------------------------
  await lib.castMod(globalThis.__mods[1]);
  await settle();
  const sheet = one(modal, "mmc-cast-sheet");
  const fileRows = all(sheet, "mmc-cast-sheet-file");
  out.fromMod = {
    handle: lib.body?.cast?.handle ?? null,
    files: lib.body?.cast?.files ?? null,
    row: fileRows.map((row) => [text(one(row, "mmc-cast-sheet-role")), one(row, "mmc-cast-sheet-filename")?.textContent,
                                text(one(row, "mmc-cast-sheet-enc"))]),
    ledger: text(one(sheet, "mmc-cast-ledger")),
    saveOffered: all(sheet, "mmc-cast-ledger-act").map(text),
    legends: all(sheet, "mmc-cast-sheet-legend").map((n) => n.textContent),
  };
  lib.closeSheet();
  await settle();

  // ---- who uses what, on the card and in the panel ---------------------------
  const rows = (await P.listPresets({ force: true })).filter((r) => r.scope === "cast");
  out.card = { facts: rows[0].facts.mods, line: P.castFactsLine(rows[0].facts, { tokens: 1024 }),
               badge: Boolean(one(modal, "mmc-cast-hero-mod")) };
  await lib.loadMods();
  await settle();
  out.usedBy = all(one(modal, "mmc-mod-panel"), "mmc-mod-row").map((row) => text(one(row, "mmc-mod-who")));

  // ---- hang the other mod on them too ---------------------------------------
  await lib.hangOn(rows[0], globalThis.__mods[0]);
  await settle();
  const body = await P.loadBody(rows[0]);
  out.hung = body.cast.files.map((f) => f.filename);

  // ---- a stack from the page ----------------------------------------------------
  const rowsNow = (await P.listPresets({ force: true })).filter((r) => r.scope === "cast");
  const saved = await P.savePreset({ name: "vera", scope: "cast", data: { cast: {
    handle: "vera", takes: "person", description: "a keeper",
    files: [{ slot: "from", filename: "people/a.png", kind: "image", note: "her face" },
            { slot: "from", filename: "people/b.png", kind: "image" },
            { slot: "from", filename: "people/walk.mp4", kind: "video", note: "the walk" },
            { slot: "voice", filename: "people/v.wav", kind: "audio" }] } } });
  lib.rows = [saved, ...lib.rows];
  lib.target = { vae: () => "h3_vae", label: "this piece", apply() {} };
  await lib.edit(saved);
  await settle();
  const page = one(modal, "mmc-cast-sheet");
  out.pageBefore = { ledger: text(one(page, "mmc-cast-ledger")), acts: all(page, "mmc-cast-ledger-act").map(text),
                     stackable: lib.modSources(lib.body.cast).map((f) => f.filename) };
  await lib.keepAsMod(lib.body.cast, "stack");
  await settle();
  const made = globalThis.__calls.find((c) => c[0] === "make")?.[1] ?? null;
  const pageAfter = one(modal, "mmc-cast-sheet");
  out.pageAfter = {
    made: made && { sources: made.sources, mode: made.mode, description: made.description, vae: made.vae },
    files: lib.body.cast.files,
    ledger: text(one(pageAfter, "mmc-cast-ledger")),
    rows: all(pageAfter, "mmc-cast-sheet-file").map((row) => [text(one(row, "mmc-cast-sheet-role")), text(one(row, "mmc-cast-sheet-enc"))]),
  };
  lib.closeSheet();
  lib.target = null;
  await settle();

  // ---- importing a RefMod is casting them ----------------------------------------
  // No piece behind the window: the member is made and their page opens.
  await lib.takeIn([{ name: "hero_visual.safetensors" }]);
  await settle();
  out.imported = {
    page: lib.editing?.name ?? null,
    files: lib.body?.cast?.files ?? null,
    description: lib.body?.cast?.description ?? null,
    rows: (await P.listPresets({ force: true })).filter((r) => r.scope === "cast").map((r) => r.name),
  };
  lib.closeSheet();
  await settle();
  // Twice is still one member.
  await lib.takeIn([{ name: "hero_visual.safetensors" }]);
  await settle();
  out.importedTwice = (await P.listPresets({ force: true })).filter((r) => r.scope === "cast").map((r) => r.name);
  lib.closeSheet();
  await settle();
  // A piece behind the window changes nothing: the page opens, and casting
  // them is the button at its foot.
  const landed = [];
  lib.target = { vae: () => "v", label: "this piece", apply: (body, keys, scope) => landed.push([body.cast.handle, keys, scope]) };
  let closed = false;
  const realClose = lib.close.bind(lib);
  lib.close = () => { closed = true; };
  globalThis.__mods.splice(globalThis.__mods.findIndex((m) => m.path === "refmod:hero_visual"), 1);
  await lib.takeIn([{ name: "hero_visual.safetensors" }]);
  await settle();
  out.importedOnto = { landed, closed, page: lib.editing?.name ?? null,
                       castButton: all(one(modal, "mmc-cast-sheet"), "mmc-cast-sheet-apply").map(text) };
  lib.close = realClose;
  lib.closeSheet();
  lib.target = null;
  await settle();

  // ---- rename: the member follows -------------------------------------------
  await lib.rewritePaths("refmod:cast/anna", "refmod:people/anna");
  const after = await P.loadBody(rows[0]);
  out.renamed = after.cast.files.map((f) => f.filename);
} catch (error) {
  out.errors.push(`refmod library: ${error.stack}`);
}
console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-refmod-library-")
try:
    pack = os.path.join(work, "pack")
    shutil.copytree(os.path.join(ROOT, "web"), os.path.join(pack, "web"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, source in STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(source)
    with open(os.path.join(work, "scripts", "families.json"), "w", encoding="utf-8") as handle:
        handle.write(layout.catalog_json())
    lib_path = os.path.join(pack, "web", "creator", "presetlib.js")
    with open(lib_path, encoding="utf-8") as handle:
        source = handle.read()
    source = source.replace(
        "    this.unmount = mountOverlay(this.overlay, () => this.close());",
        "    globalThis.__lib = this;\n"
        "    this.unmount = mountOverlay(this.overlay, () => this.close());")
    with open(lib_path, "w", encoding="utf-8") as handle:
        handle.write(source)
    for name, body in (("dom.mjs", DOM), ("check.mjs", CHECK)):
        with open(os.path.join(pack, name), "w", encoding="utf-8") as handle:
            handle.write(body)
    result = subprocess.run(["node", os.path.join(pack, "check.mjs")],
                            capture_output=True, text=True, cwd=pack)
finally:
    shutil.rmtree(work, ignore_errors=True)

if result.returncode != 0:
    print("the library did not run:\n" + (result.stderr.strip() or result.stdout.strip()))
    sys.exit(1)

report = json.loads(result.stdout.strip().splitlines()[-1])
from harness import FAILURES, check, passed  # noqa: E402

FAILURES.extend(report["errors"])
panel = report.get("panel") or {}
check("the Cast tab's column is the Saved references panel", panel.get("there"), True)
check("...titled as such", panel.get("title"), "Saved references")
check("...grouped by folder", panel.get("folders"), ["(top level)", "cast/"])
check("...one row a mod: name, what it costs, who uses it", panel.get("rows"), [
    ["vanellope_example", "full · 1,024 tokens · 64×64 · made elsewhere", "not in any member"],
    ["anna", "compressed · 64 tokens · 16×16", "not in any member"],
])
check("...with its own way in", panel.get("importText"), "Import")

made = report.get("fromMod") or {}
check("a foreign mod becomes a member named after its file", made.get("handle"), "vanellope_example")
check("...with the file as their looks",
      made.get("files"), [{"slot": "from", "filename": "refmod:vanellope_example", "kind": "image"}])
check("...whose row says so", made.get("row"),
      [["looks", "refmods/vanellope_example", "RefMod · full 1,024 tokens"]])
check("...and whose ledger is the receipt", made.get("ledger"),
      "Saved as a RefMod · full · 1,024 tokens · refmods/vanellope_example Download Show in library")
check("...with nothing to save and no node to save with", made.get("saveOffered"), ["Download", "Show in library"])
check("the page's legends are sentences", made.get("legends"),
      ["Who they are", "What a picture cannot say", "Made out of"])

card = report.get("card") or {}
check("the card's facts name the file", card.get("facts"), ["refmod:vanellope_example"])
check("...and read as an instrument", card.get("line"), "person · 1 RefMod · 1,024 tok")
check("...under a badge", card.get("badge"), True)
check("the panel says who uses what", report.get("usedBy"), ["in @vanellope_example", "not in any member"])
check("a mod hung on somebody from the panel lands in their looks", report.get("hung"),
      ["refmod:vanellope_example", "refmod:cast/anna"])
check("a renamed mod's members follow it", report.get("renamed"),
      ["refmod:vanellope_example", "refmod:people/anna"])

imported = report.get("imported") or {}
check("importing a RefMod makes the member and opens their page",
      (imported.get("page"), imported.get("files"), imported.get("description")),
      ("hero_visual", [{"slot": "from", "filename": "refmod:hero_visual", "kind": "video"}],
       "a girl with candy in her hair"))
check("...in the roster", imported.get("rows"), ["hero_visual", "vera", "vanellope_example"])
check("...and importing it twice is still one member", report.get("importedTwice"), ["hero_visual", "vera", "vanellope_example"])
check("with a piece behind the window the page still opens, and casting is its button",
      report.get("importedOnto"), {"landed": [], "closed": False, "page": "hero_visual",
                                   "castButton": ["Cast @hero_visual into this piece"]})

before = report.get("pageBefore") or {}
check("a page with a node behind it offers to save, counting the clip",
      (before.get("ledger"), before.get("acts")),
      ("Encoded on every render · 2 pictures + 1 clip at max · ≈8,192+ tokens Save as RefMods ▾",
       ["Save as RefMods ▾"]))
check("...and a stack takes all three", before.get("stackable"), ["people/a.png", "people/b.png", "people/walk.mp4"])
after = report.get("pageAfter") or {}
check("the job is asked for one file, with the files' words in its header",
      after.get("made"), {"sources": ["people/a.png", "people/b.png", "people/walk.mp4"], "mode": "stack",
                          "description": "a keeper; her face; the walk", "vae": "h3_vae"})
check("the stack stands where the three were; the voice stays",
      after.get("files"), [{"slot": "from", "filename": "refmod:cast/vera", "kind": "video"},
                           {"slot": "voice", "filename": "people/v.wav", "kind": "audio"}])
check("...and the page reads it as a stack",
      (after.get("ledger"), after.get("rows")),
      ("Saved as a RefMod · stack · 448 tokens · refmods/cast/vera Download Show in library",
       [["looks", "RefMod · stack 448 tokens"], ["voice", "voice"]]))

passed("the roster's Saved references panel lists, casts, hangs and renames RefMods")
