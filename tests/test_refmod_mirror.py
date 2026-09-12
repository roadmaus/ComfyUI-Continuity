"""The frontend's half of a saved reference agrees with the compiler's.

    python3 tests/test_refmod_mirror.py

Skips itself if node is not installed.

Three things are said twice and have to match. What a mod *is*: `state.isRefMod`
and `compile.Asset.mod` both read the `refmod:` prefix, and a blob the shelf
builds out of one compiles to a `<Picture N>`. What a mod *cannot* do: no size
to choose (`sizeable`), no soundtrack to bring (`trackFor`), which the
compiler refuses by name if a blob asks anyway. And what keeping somebody as a
mod does to the piece (`refmod.keepAsMod`): the mods land where the pictures
were, the member's looks and notes follow, and a picture leaves only when
nobody else needs it — the same bargain removing a member makes.
"""

import json

import layout
from harness import FAILURES, check, passed

layout.skip_without_node()

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "refmod", "compile",
                   package="mmc")
compiler = _pkg.compile

# The stub API answers the two routes a mod needs: the listing and the job.
# The job answers with `result` inline, which is how `queue.run` returns a job
# that finished inside the round trip.
API = layout.STUBS["api.js"].replace(
    "    return { ok: true, status: 200, json: async () => ({}) };",
    """    if (String(url).startsWith("/continuity/assets?root=refmods")) {
      return { ok: true, status: 200, json: async () => ({ assets: [
        { path: "refmod:cast/anna", name: "anna", subfolder: "cast", kind: "image",
          size: 1, mtime: 1, mod: true, mode: "training", tokens: 64, preview: true },
        { path: "refmod:walk", name: "walk", subfolder: "", kind: "video",
          size: 1, mtime: 1, mod: true, mode: "encode", tokens: 768, preview: false },
      ], folders: ["cast"], truncated: false }) };
    }
    if (String(url).startsWith("/continuity/refmod/make")) {
      const body = JSON.parse(options.body);
      globalThis.__made = body;
      if (body.mode === "stack") {
        return { ok: true, status: 200, json: async () => ({ result: { mods: [
          { path: `refmod:cast/${body.name}`, kind: "video", tokens: 64 * (body.sources.length + 5),
            mode: "training", source: "stack" }] } }) };
      }
      return { ok: true, status: 200, json: async () => ({ result: { mods: body.sources.map(
        (source, i) => ({ path: `refmod:cast/${body.name}${i ? `-${i + 1}` : ""}`,
                          kind: "image", tokens: 64, mode: body.mode })) } }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };""").replace(
    "  async fetchApi(url) {", "  async fetchApi(url, options = {}) {")

SCRIPT = layout.DOMSHIM if hasattr(layout, "DOMSHIM") else ""
SCRIPT = __import__("domshim").DOM + """
import * as S from "./web/creator/state.js";
import { cost, costMark, keepable, keepAsMod, ledger, modRows, modeRows } from "./web/creator/refmod.js";
import { CastShelf } from "./web/creator/cast.js";
import { openPicker } from "./web/creator/picker.js";

const out = {};
const mod = { handle: "img-2", kind: "image", role: "reference", filename: "refmod:cast/anna" };
const pic = { handle: "img-1", kind: "image", role: "reference", filename: "anna.png" };
out.isMod = [S.isRefMod(mod), S.isRefMod(pic)];
out.sizeable = [S.sizeable(mod), S.sizeable(pic)];
out.track = [S.trackFor({ path: "refmod:walk", kind: "video" }),
             S.trackFor({ path: "walk.mp4", kind: "video" }),
             S.trackFor({ path: "walk.mp4", kind: "video", track: "sound" })];

// A blob with a mod on a member, as the shelf would leave it.
const piece = S.parseState(JSON.stringify({
  prompt: "@anna smiles at @img-3",
  assets: [pic, mod, { handle: "img-3", kind: "image", role: "reference", filename: "b.png" }],
  subjects: [{ handle: "anna", from: ["img-1", "img-2"], takes: "person",
               notes: { "img-1": "her face" } }],
  duration_s: 6, aspect: "16:9", short_edge: 768,
}));
out.blob = JSON.parse(JSON.stringify({ assets: piece.assets, subjects: piece.subjects, prompt: piece.prompt }));

// Keeping her: the picture goes, the mod takes its place, the words follow.
const list = piece.assets;
const rows = await keepAsMod(piece.subjects[0], list, "compressed", {
  vae: "h3_vae.safetensors",
  list: () => list,
  nextHandle: (kind) => S.nextHandle(piece, kind),
  texts: () => [piece.prompt],
  cast: () => piece.subjects,
  drop: (handles) => { piece.assets = piece.assets.filter((a) => !handles.includes(a.handle)); },
});
out.made = globalThis.__made;
out.rows = rows.map((r) => r.path);
out.after = { assets: piece.assets.map((a) => [a.handle, a.filename]),
              from: piece.subjects[0].from, notes: piece.subjects[0].notes ?? null };
out.keepableAfter = keepable(piece.subjects[0], piece.assets).length;

// A picture somebody else claims, or the prompt writes, stays.
const shared = S.parseState(JSON.stringify({
  prompt: "@anna and @ben, and @img-9 on the wall",
  assets: [{ handle: "img-1", kind: "image", role: "reference", filename: "a.png" },
           { handle: "img-9", kind: "image", role: "reference", filename: "wall.png" }],
  subjects: [{ handle: "anna", from: ["img-1", "img-9"] }, { handle: "ben", from: ["img-1"] }],
  duration_s: 6, aspect: "16:9", short_edge: 768,
}));
await keepAsMod(shared.subjects[0], shared.assets, "full", {
  vae: "v", list: () => shared.assets, nextHandle: (k) => S.nextHandle(shared, k),
  texts: () => [shared.prompt], cast: () => shared.subjects,
  drop: (handles) => { shared.assets = shared.assets.filter((a) => !handles.includes(a.handle)); },
});
out.shared = { assets: shared.assets.map((a) => a.handle), anna: shared.subjects[0].from,
               ben: shared.subjects[1].from };

// A stack: two stills and a clip become one video mod in their looks, the
// words on the files ride in its header, and the clip's own note goes too.
const stacked = S.parseState(JSON.stringify({
  prompt: "@vera",
  assets: [{ handle: "img-1", kind: "image", role: "reference", filename: "a.png" },
           { handle: "img-2", kind: "image", role: "reference", filename: "b.png" },
           { handle: "vid-1", kind: "video", role: "reference", filename: "walk.mp4" }],
  subjects: [{ handle: "vera", from: ["img-1", "img-2", "vid-1"], takes: "person",
               description: "a keeper", notes: { "img-1": "her face", "vid-1": "the walk" } }],
  duration_s: 6, aspect: "16:9", short_edge: 768,
}));
out.stackMenu = modeRows(stacked.assets.map((a) => ({ filename: a.filename, kind: a.kind, ref_size: "max" })), () => {})
  .map((row) => row.label);
out.soloMenu = modeRows([{ filename: "a.png", kind: "image", ref_size: "max" }], () => {}).map((row) => row.label);
out.stackable = keepable(stacked.subjects[0], stacked.assets, "stack").map((a) => a.handle);
out.perPicture = keepable(stacked.subjects[0], stacked.assets).map((a) => a.handle);
const stackRows = await keepAsMod(stacked.subjects[0], stacked.assets, "stack", {
  vae: "v", list: () => stacked.assets, nextHandle: (k) => S.nextHandle(stacked, k),
  texts: () => [stacked.prompt], cast: () => stacked.subjects,
  drop: (handles) => { stacked.assets = stacked.assets.filter((a) => !handles.includes(a.handle)); },
});
out.stacked = {
  made: { sources: globalThis.__made.sources, mode: globalThis.__made.mode, description: globalThis.__made.description },
  rows: stackRows.map((r) => [r.path, r.kind]),
  assets: stacked.assets.map((a) => [a.handle, a.kind, a.filename, a.track ?? null]),
  from: stacked.subjects[0].from, notes: stacked.subjects[0].notes ?? null,
  blob: JSON.parse(JSON.stringify({ assets: stacked.assets, subjects: stacked.subjects, prompt: stacked.prompt,
                                    duration_s: 6, aspect: "16:9", short_edge: 768 })),
};

// Nothing to keep is said, not queued.
try {
  await keepAsMod({ handle: "ghost", from: [] }, [], "full", { list: () => [] });
  out.empty = "kept";
} catch (error) { out.empty = error.message; }

// ---- the ledger ------------------------------------------------------------
// What their looks cost, by the encoder's arithmetic: a token is 32x32 source
// pixels, so `match` is the canvas over that and `max` is a 2048 short edge
// over that; a mod's count is the listing's.
await modRows();
const canvas = { width: 992, height: 576 };
const matchPic = { filename: "a.png", kind: "image", ref_size: "match" };
const maxPic = { filename: "b.png", kind: "image", ref_size: "max" };
const modEntry = { filename: "refmod:cast/anna", kind: "image" };
const c1 = cost([matchPic], canvas);
const c2 = cost([maxPic], canvas);
const c3 = cost([modEntry], canvas);
const c4 = cost([matchPic, modEntry], canvas);
out.cost = {
  match: [c1.pictures, c1.picTokens, c1.exact],
  max: [c2.pictures, c2.picTokens, c2.exact],
  mod: [c3.mods, c3.modTokens, c3.exact],
  mixed: [c4.pictures, c4.mods, c4.picTokens + c4.modTokens, c4.exact],
  marks: [costMark([maxPic], canvas), costMark([modEntry], canvas), costMark([], canvas)],
};
const text = (node) => node.text.replace(/\\s+/g, " ").trim();
const acts = (node) => (node.children ?? []).filter((k) => String(k.className).includes("mmc-cast-ledger-act")).map(text);
const before = ledger({ entries: [maxPic], canvas, onSave: () => {} });
const busy = ledger({ entries: [maxPic], canvas, busy: { count: 1, mode: "compressed", progress: .4 } });
const saved = ledger({ entries: [modEntry], canvas, onLibrary: () => {} });
const mixed = ledger({ entries: [matchPic, modEntry], canvas, onSave: () => {} });
out.ledger = {
  before: [text(before), acts(before), before.className],
  busy: [text(busy), busy.className],
  saved: [text(saved), acts(saved), saved.className,
          saved.children.find((k) => k.tagName === "A")?.getAttribute("href") ?? null],
  mixed: [text(mixed), acts(mixed)],
  none: ledger({ entries: [], canvas }),
  modes: modeRows([maxPic], () => {}).map((row) => row.label),
};

// The card: the ledger under the tiles, the verbs in a footer, no cube.
const shelfPiece = S.parseState(JSON.stringify({
  prompt: "@anna",
  assets: [{ handle: "img-1", kind: "image", role: "reference", filename: "a.png", ref_size: "max" }],
  subjects: [{ handle: "anna", from: ["img-1"], takes: "person" }],
  duration_s: 6, aspect: "16:9", short_edge: 768,
}));
const shelf = new CastShelf({
  getCast: () => shelfPiece.subjects, setCast: (l) => { shelfPiece.subjects = l; },
  getAssets: () => shelfPiece.assets, addAsset: null,
  whereCited: () => ({ text: "in the prompt", cited: true }), cite: () => {},
  touch: () => {}, commit: () => {},
  keep: async () => {}, library: async () => {}, mod: async () => [],
  canvas: () => canvas,
});
shelf.render();
const classes = [];
const walkAll = (node) => { classes.push(...String(node.className ?? "").split(" ")); (node.children ?? []).forEach(walkAll); };
walkAll(shelf.root);
const has = (cls) => classes.includes(cls);
out.shutCard = { cost: has("mmc-cast-line-cost"), ledger: has("mmc-cast-ledger") };
shelf.openMember("anna");
classes.length = 0; walkAll(shelf.root);
out.openCard = {
  ledger: has("mmc-cast-ledger"), foot: has("mmc-cast-foot"), cube: has("mmc-cast-modme"),
  star: has("mmc-cast-keepme"), swap: has("mmc-cast-swapme"),
};

// The picker: a tab, rows off the listing, an import where upload sits, no organize.
document.body.children.length = 0;
openPicker({ kinds: ["image", "refmods"], kind: "refmods",
             capacity: () => ({ used: 0, max: 9, filesLeft: 9 }) });
await new Promise((resolve) => setTimeout(resolve, 20));
const found = (cls) => {
  const hits = [];
  const walk = (node) => {
    if (node.className && String(node.className).split(" ").includes(cls)) hits.push(node);
    for (const kid of node.children ?? []) walk(kid);
  };
  walk(document.body);
  return hits;
};
out.picker = {
  tabs: found("mmc-tab").map((n) => n.textContent),
  cells: found("mmc-cell-mod").map((n) => n.textContent),
  upload: found("mmc-upload").map((n) => [n.style.display, n.textContent]),
  organize: found("mmc-organize").map((n) => n.style.display),
};
console.log(JSON.stringify(out));
"""

with layout.pack(extra_stubs={"api.js": API}, skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target)

check("state.js tells a mod from a picture", got["isMod"], [True, False])
check("a mod has no size to choose", got["sizeable"], [False, True])
check("a saved clip lands silent; a file lands on the default (silent, until the probe says), or as asked",
      got["track"], ["picture", "picture", "sound"])

# The blob the shelf makes compiles, and the mod is a picture in the plan.
blob = {**got["blob"], "duration_s": 6, "aspect": "16:9", "short_edge": 768}
compiled = compiler.compile_request(blob, image_size_lookup=lambda _f: (1500, 1000))
check("compile.py reads the same mod",
      [(step["asset"].handle, step["asset"].mod, step["label"]) for step in compiled.plan],
      [("img-1", False, "<Picture 1>"), ("img-2", True, "<Picture 2>"), ("img-3", False, "<Picture 3>")])
check("...and the member is built out of both",
      "<Subject 1> is the person in <Picture 1> (her face) and <Picture 2>" in compiled.prompt, True)

# Keeping her.
check("the job is asked for her picture, under her name, as her kind of thing",
      (got["made"]["sources"], got["made"]["name"], got["made"]["subfolder"],
       got["made"]["mode"], got["made"]["concept"], got["made"]["vae"]),
      (["anna.png"], "anna", "cast", "compressed", "identity", "h3_vae.safetensors"))
check("one mod comes back per picture", got["rows"], ["refmod:cast/anna"])
check("the picture leaves and the mod takes its place",
      got["after"]["assets"],
      [["img-2", "refmod:cast/anna"], ["img-3", "b.png"], ["img-4", "refmod:cast/anna"]])
check("...her looks point at the mods", got["after"]["from"], ["img-4", "img-2"])
check("...and her words follow", got["after"]["notes"], {"img-4": "her face"})
check("there is nothing left to keep", got["keepableAfter"], 0)

# A stack.
check("the menu leads with the stack where there is something to stack", got["stackMenu"],
      ["One file — everything stacked — ≈512 tokens", "Compressed — ≈1,152 tokens", "Full — ≈2,048 tokens"])
check("...and not for one still", got["soloMenu"], ["Compressed — ≈576 tokens", "Full — ≈1,024 tokens"])
check("a stack takes the clip; the per-picture modes do not",
      (got["stackable"], got["perPicture"]), (["img-1", "img-2", "vid-1"], ["img-1", "img-2"]))
check("the job is asked for all three as one, with the files' words in its header",
      got["stacked"]["made"], {"sources": ["a.png", "b.png", "walk.mp4"], "mode": "stack",
                               "description": "a keeper; her face; the walk"})
check("one video mod comes back", got["stacked"]["rows"], [["refmod:cast/vera", "video"]])
check("...and stands where the three were, silent",
      got["stacked"]["assets"], [["vid-2", "video", "refmod:cast/vera", "picture"]])
check("...listed once in their looks, with no per-file notes left",
      (got["stacked"]["from"], got["stacked"]["notes"]), (["vid-2"], None))
stacked_blob = compiler.compile_request(got["stacked"]["blob"], image_size_lookup=lambda _f: (1500, 1000))
check("and compile.py cites the stack as one video",
      ([step["label"] for step in stacked_blob.plan],
       "<Subject 1> is the person in <Video 1>" in stacked_blob.prompt), (["<Video 1>"], True))

check("a picture another member claims stays, and so does one the prompt writes",
      got["shared"], {"assets": ["img-1", "img-9", "img-2", "img-3"],
                      "anna": ["img-2", "img-3"], "ben": ["img-1"]})
check("nothing to keep is refused before the queue", got["empty"],
      "Nothing to save — hang a picture on them first.")

# The ledger.
check("a match picture costs the canvas over 32x32", got["cost"]["match"], [1, 558, False])
check("a max picture costs a 2048 edge over 32x32 (square, unmeasured)", got["cost"]["max"], [1, 4096, False])
check("a mod costs what its header says, exactly", got["cost"]["mod"], [1, 64, True])
check("...and the two add", got["cost"]["mixed"], [1, 1, 622, False])
check("the shut line's mark is ≈ for a picture, plain and amber for a mod, absent for nobody",
      got["cost"]["marks"], [{"text": "≈4.1k tok", "saved": False}, {"text": "64 tok", "saved": True}, None])
check("before: the line says what it costs and offers to save",
      got["ledger"]["before"],
      ["Encoded on every render · 1 picture at max · ≈4,096 tokens Save as RefMod ▾",
       ["Save as RefMod ▾"], "mmc-cast-ledger"])
check("busy: the same line, with the arithmetic and a bar",
      got["ledger"]["busy"],
      ["Encoding 1 picture… · compressed · ≈4,096 → ≈576 tokens on the queue", "mmc-cast-ledger busy"])
check("saved: the receipt — mode, tokens, where the file is, and the two doors out",
      got["ledger"]["saved"],
      ["Saved as a RefMod · compressed · 64 tokens · refmods/cast/anna Download Show in library",
       ["Download", "Show in library"], "mmc-cast-ledger saved",
       "/continuity/refmod/file?filename=refmod%3Acast%2Fanna"])
check("mixed: both counted, and the picture offered", got["ledger"]["mixed"],
      ["1 RefMod + 1 picture · 64 + ≈558 tokens Save the picture too ▾", ["Save the picture too ▾"]])
check("nobody: no line", got["ledger"]["none"], None)
check("the mode menu names what each would cost", got["ledger"]["modes"],
      ["Compressed — ≈576 tokens", "Full — ≈1,024 tokens"])
check("a shut line wears the cost and no ledger", got["shutCard"], {"cost": True, "ledger": False})
check("an open card has the ledger and the footer, and none of the three icons",
      got["openCard"], {"ledger": True, "foot": True, "cube": False, "star": False, "swap": False})

check("the picker has a RefMod tab", got["picker"]["tabs"], ["Image", "RefMod"])
check("...whose cells say what a mod costs", got["picker"]["cells"],
      ["compressed · 64 tokens", "full · 768 tokens"])
check("...with an import in the upload slot and nothing to organize",
      (got["picker"]["upload"], got["picker"]["organize"]),
      ([[None, "+  Import RefMod"]], ["none"]))

passed("state.js, refmod.js and the picker mirror compile.py about saved references")
