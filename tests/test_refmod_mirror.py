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
        { path: "refmod:cast/anna.flux2", name: "anna.flux2", subfolder: "cast", kind: "image",
          size: 1, mtime: 1, mod: true, mode: "training", tokens: 1024, preview: true, space: "flux2",
          space_label: "Flux 2" },
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
      const space = body.family === "flux2klein" ? "flux2" : "h3_video";
      const suffix = space === "h3_video" ? "" : `.${space}`;
      return { ok: true, status: 200, json: async () => ({ result: { mods: body.sources.map(
        (source, i) => ({ path: `refmod:cast/${body.name}${i ? `-${i + 1}` : ""}${suffix}`,
                          kind: body.mode === "clip" ? "video" : "image",
                          tokens: space === "flux2" ? 1024 : 64, mode: body.mode, space })) } }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };""").replace(
    "  async fetchApi(url) {", "  async fetchApi(url, options = {}) {")

SCRIPT = layout.DOMSHIM if hasattr(layout, "DOMSHIM") else ""
SCRIPT = __import__("domshim").DOM + """
import * as S from "./web/creator/state.js";
import { castFamilies, cost, costMark, everyFamilyRows, familyModeRows, keepable, keepAsMod, modFamilies, modRows, modeRows } from "./web/creator/refmod.js";
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

// Keeping her: the picture stays, and carries the mod for the family.
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
out.after = { assets: piece.assets.map((a) => [a.handle, a.filename, a.mods ?? null]),
              from: piece.subjects[0].from, notes: piece.subjects[0].notes ?? null };
out.keepableAfter = keepable(piece.subjects[0], piece.assets).length;
out.keepableForKlein = keepable(piece.subjects[0], piece.assets, "compressed", "flux2").map((a) => a.handle);
out.afterBlob = JSON.parse(S.serializeTimeline({ ...piece, segments: [] })).assets
  .map((a) => [a.handle, a.mods ?? null]);

// ...and for Klein too, from the same picture, through Klein's VAE.
const families = modFamilies("h3", "h3_vae.safetensors", { flux2klein: { vae: "flux2-vae.safetensors" } });
out.families = families.map((f) => [f.id, f.space, f.vae, f.clips]);
await keepAsMod(piece.subjects[0], list, "full", {
  family: families.find((f) => f.id === "flux2klein"),
  list: () => list, nextHandle: (kind) => S.nextHandle(piece, kind),
  texts: () => [piece.prompt], cast: () => piece.subjects, drop: () => {},
});
out.madeKlein = { family: globalThis.__made.family, vae: globalThis.__made.vae, mode: globalThis.__made.mode };
out.bothMods = piece.assets[0].mods;
// The rows per family, refused where that family has no VAE picked; and
// the "every family" row where more than one is ready.
const sectionsOf = (entries, families, onPick = () => {}) => [
  ...(everyFamilyRows(entries, families, onPick, () => {}).length
    ? [["Every family", everyFamilyRows(entries, families, onPick, () => {}).map((row) => row.label)]] : []),
  ...families.map((family) => [family.label, familyModeRows(entries, family, onPick, () => {})
    .map((row) => [row.label, Boolean(row.disabled)])]),
];
out.sections = sectionsOf([{ filename: "c.png", kind: "image", ref_size: "max" }],
                          modFamilies("h3", "h3_vae.safetensors", {}));
out.everyRow = sectionsOf(
  [{ filename: "c.png", kind: "image", ref_size: "max" }, { filename: "w.mp4", kind: "video" }],
  modFamilies("h3", "h3_vae.safetensors", { flux2klein: { vae: "flux2-vae.safetensors" } }))
  .map(([head, rows]) => [head, rows.map((row) => (Array.isArray(row) ? row[0] : row))]);
everyFamilyRows([{ filename: "c.png", kind: "image", ref_size: "max" }],
                modFamilies("h3", "h3_vae.safetensors", { flux2klein: { vae: "flux2-vae.safetensors" } }),
                (mode, family) => { out.everyPicked = [mode, family.map((f) => f.id)]; }, () => {})[0].onPick();
// Every family a member can be sent to, not only the ones that keep mods.
out.castFamilies = castFamilies("h3", "h3_vae.safetensors", {}).map((f) => [
  f.id, f.here, f.video, f.reads.pictures, f.reads.clips, f.adapter, f.refmod]);
// A new frame forgets the renditions: they were latents of the old window.
const framed = { handle: "img-5", kind: "image", role: "reference", filename: "d.png",
                 mods: { h3_video: "refmod:cast/d" } };
S.dropMods(framed);
out.dropped = framed.mods ?? null;

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
const bound = { filename: "anna.png", kind: "image", ref_size: "max",
                mods: { h3_video: "refmod:cast/anna", flux2: "refmod:cast/anna.flux2" } };
const c1 = cost([matchPic], canvas);
const c2 = cost([maxPic], canvas);
const c3 = cost([modEntry], canvas);
const c4 = cost([matchPic, modEntry], canvas);
const c5 = cost([bound], canvas);
const c6 = cost([bound], canvas, null, "flux2");
const c7 = cost([{ ...bound, mods: { h3_video: "refmod:cast/anna" } }], canvas, null, "flux2");
out.cost = {
  match: [c1.pictures, c1.picTokens, c1.exact],
  max: [c2.pictures, c2.picTokens, c2.exact],
  mod: [c3.mods, c3.modTokens, c3.exact],
  mixed: [c4.pictures, c4.mods, c4.picTokens + c4.modTokens, c4.exact],
  bound: [[c5.mods, c5.modTokens, c5.exact], [c6.mods, c6.modTokens, c6.exact],
          [c7.pictures, c7.mods, c7.picTokens]],
  marks: [costMark([maxPic], canvas), costMark([modEntry], canvas), costMark([], canvas)],
};
const text = (node) => node.text.replace(/\\s+/g, " ").replace(/ \\./g, ".").trim();
out.modes = modeRows([maxPic], () => {}).map((row) => row.label);

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
  canvas: () => canvas, vae: () => "h3_vae.safetensors",
  families: () => castFamilies("h3", "h3_vae.safetensors", { flux2klein: { vae: "flux2-vae.safetensors" } }),
});
shelf.render();
const classes = [];
const walkAll = (node) => { classes.push(...String(node.className ?? "").split(" ")); (node.children ?? []).forEach(walkAll); };
walkAll(shelf.root);
const has = (cls) => classes.includes(cls);
out.shutCard = { cost: has("mmc-cast-line-cost"), panel: has("mmc-wears") };
shelf.openMember("anna");
classes.length = 0; walkAll(shelf.root);
const found2 = (cls) => { const hits = []; const walk = (node) => {
  if (String(node.className ?? "").split(" ").includes(cls)) hits.push(node); (node.children ?? []).forEach(walk); };
  walk(shelf.root); return hits; };
out.openCard = {
  panel: has("mmc-wears"), foot: has("mmc-cast-foot"), cube: has("mmc-cast-modme"),
  star: has("mmc-cast-keepme"), swap: has("mmc-cast-swapme"),
  tabs: found2("mmc-wears-tab").map((n) => [text(n), n.getAttribute("aria-selected")]),
  sentence: text(found2("mmc-wears-sentence")[0]),
  status: text(found2("mmc-wears-status")[0]),
  acts: found2("mmc-wears-act").map(text),
};
// The Klein tab: the same picture, unsaved there, offered for saving there.
shelf.wears.open = "flux2klein";
shelf.render();
out.kleinTab = {
  sentence: text(found2("mmc-wears-sentence")[0]),
  status: text(found2("mmc-wears-status")[0]),
  acts: found2("mmc-wears-act").map(text),
};
// A family that reads no pictures says so, and the sentence's noun is fixed.
shelf.wears.open = "ideogram4";
shelf.render();
out.ideogramTab = { sentence: text(found2("mmc-wears-sentence")[0]), status: text(found2("mmc-wears-status")[0]),
                    fixed: String(found2("mmc-wears-choice")[0]?.className).includes("fixed") };
// Sent as words to H3: the status says so, and the blob carries the choice.
shelf.wears.open = "h3";
S.wearOn(shelfPiece.subjects[0], "h3").send = "words";
shelf.render();
out.wordsTab = { sentence: text(found2("mmc-wears-sentence")[0]),
                 blob: JSON.parse(S.serializeTimeline({ ...shelfPiece, segments: [] })).subjects[0].wears };

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
check("the picture stays, carrying the mod for the family",
      got["after"]["assets"],
      [["img-1", "anna.png", {"h3_video": "refmod:cast/anna"}], ["img-2", "refmod:cast/anna", None],
       ["img-3", "b.png", None]])
check("...her looks and her words are untouched",
      (got["after"]["from"], got["after"]["notes"]), (["img-1", "img-2"], {"img-1": "her face"}))
check("there is nothing left to keep for H3", got["keepableAfter"], 0)
check("...but the same picture is still unsaved for Klein", got["keepableForKlein"], ["img-1"])
check("the blob carries the renditions", got["afterBlob"],
      [["img-1", {"h3_video": "refmod:cast/anna"}], ["img-2", None], ["img-3", None]])
bound_blob = compiler.compile_request(
    {"prompt": "@anna", "assets": [{"handle": "img-1", "kind": "image", "role": "reference",
                                    "filename": "anna.png", "mods": {"h3_video": "refmod:cast/anna"}}],
     "subjects": [{"handle": "anna", "from": ["img-1"], "takes": "person"}],
     "duration_s": 6, "aspect": "16:9", "short_edge": 768},
    image_size_lookup=lambda _f: (1500, 1000))
check("...and compile.py reads them off the picture",
      (bound_blob.ref_images[0].mod, bound_blob.ref_images[0].mod_for("h3_video"),
       bound_blob.ref_images[0].mod_for("flux2")), (False, "refmod:cast/anna", None))
check("the families a member can be saved for, the piece's first",
      got["families"], [["h3", "h3_video", "h3_vae.safetensors", True],
                        ["flux2klein", "flux2", "flux2-vae.safetensors", False]])
check("saving for Klein asks for that family and its VAE",
      got["madeKlein"], {"family": "flux2klein", "vae": "flux2-vae.safetensors", "mode": "full"})
check("...and the picture carries both renditions",
      got["bothMods"], {"h3_video": "refmod:cast/anna", "flux2": "refmod:cast/anna.flux2"})
check("the rows are per family, and a family with no VAE picked is offered disabled",
      got["sections"],
      [["MiniMax H3", [["Compressed — ≈576 tokens", False], ["Full — ≈1,024 tokens", False]]],
       ["Flux 2 Klein", [["Compressed — ≈1,024 tokens", True], ["Full — ≈4,096 tokens", True]]]])
check("every family a member can be sent to is listed, the piece's first, with what each reads",
      got["castFamilies"],
      [["h3", True, True, True, True, False, True], ["ltx25", False, True, True, False, False, False],
       ["krea2", False, False, True, False, True, False], ["ideogram4", False, False, False, False, False, False],
       ["qwenedit", False, False, True, False, False, False], ["flux2klein", False, False, True, False, False, True],
       ["qwen21", False, False, True, False, False, False],
       ["moss", False, False, False, False, False, False]])
check("a new frame forgets the renditions", got["dropped"], None)
check("with two families ready the menu leads with one row for all of them, per-picture modes only",
      got["everyRow"],
      [["Every family", ["Compressed — ≈576 + 1,024 tokens", "Full — ≈1,024 + 4,096 tokens"]],
       ["MiniMax H3", ["One file — everything stacked — ≈448 tokens", "Compressed — ≈576 tokens",
                       "Full — ≈1,024 tokens", "Each clip — its own file — ≈2,016 tokens"]],
       ["Flux 2 Klein", ["Compressed — ≈1,024 tokens", "Full — ≈4,096 tokens"]]])
check("...and picking it names every ready family, the piece's first",
      got["everyPicked"], ["compressed", ["h3", "flux2klein"]])

# A stack.
check("the menu leads with the stack where there is something to stack, and offers the clip on its own",
      got["stackMenu"],
      ["One file — everything stacked — ≈512 tokens", "Compressed — ≈1,152 tokens", "Full — ≈2,048 tokens",
       "Each clip — its own file — ≈2,016 tokens"])
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

check("a picture two members share is saved once and stays both of theirs",
      got["shared"], {"assets": ["img-1", "img-9"],
                      "anna": ["img-1", "img-9"], "ben": ["img-1"]})
check("nothing to keep is refused before the queue", got["empty"],
      "Nothing to save — hang a picture on them first.")

# The ledger.
check("a match picture costs the canvas over 32x32", got["cost"]["match"], [1, 558, False])
check("a max picture costs a 2048 edge over 32x32 (square, unmeasured)", got["cost"]["max"], [1, 4096, False])
check("a mod costs what its header says, exactly", got["cost"]["mod"], [1, 64, True])
check("...and the two add", got["cost"]["mixed"], [1, 1, 622, False])
check("a picture carrying a rendition costs the rendition, in each family's own space — and is a picture "
      "where it has none for that family",
      got["cost"]["bound"], [[1, 64, True], [1, 1024, True], [1, 0, 4096]])
check("the shut line's mark is ≈ for a picture, plain and amber for a mod, absent for nobody",
      got["cost"]["marks"], [{"text": "≈4.1k tok", "saved": False}, {"text": "64 tok", "saved": True}, None])
check("the mode menu names what each would cost", got["modes"],
      ["Compressed — ≈576 tokens", "Full — ≈1,024 tokens"])
check("a shut line wears the cost and no panel", got["shutCard"], {"cost": True, "panel": False})
opened = got["openCard"]
check("an open card has the panel and the footer, and none of the three icons",
      {k: opened[k] for k in ("panel", "foot", "cube", "star", "swap")},
      {"panel": True, "foot": True, "cube": False, "star": False, "swap": False})
check("a tab per family, the piece's own open", opened["tabs"][:3],
      [["MiniMax H3 this piece", "true"], ["LTX 2.5", "false"], ["Krea 2", "false"]])
check("the sentence says what H3 gets", opened["sentence"], "When MiniMax H3 renders @anna it gets their picture.")
check("...and the status says what it costs, and offers to save for that family",
      (opened["status"], opened["acts"]),
      ("1 picture encoded every render — ≈4.1k tokens. Saving them once reads the file instead. Save for MiniMax H3 ▾",
       ["Save as RefMod ▾", "+ LoRA", "Save for MiniMax H3 ▾"]))
check("the Klein tab offers the same picture for Klein", got["kleinTab"]["acts"][-1], "Save for Flux 2 Klein ▾")
check("a family that reads no pictures gets the words, and says so",
      got["ideogramTab"],
      {"sentence": "When Ideogram 4.0 renders @anna it gets their description only.",
       "status": "Ideogram 4.0 takes no reference pictures. Their description is all it can be told.", "fixed": True})
check("sent as words, the sentence says so and the blob carries the choice",
      got["wordsTab"],
      {"sentence": "When MiniMax H3 renders @anna it gets their description only.", "blob": {"h3": {"send": "words"}}})

check("the picker has a RefMod tab", got["picker"]["tabs"], ["Image", "RefMod"])
check("...whose cells say what a mod costs, and whose it is when not H3's", got["picker"]["cells"],
      ["compressed · 64 tokens", "full · 768 tokens", "Flux 2 · compressed · 1024 tokens"])
check("...with an import in the upload slot and nothing to organize",
      (got["picker"]["upload"], got["picker"]["organize"]),
      ([[None, "+  Import RefMod"]], ["none"]))

passed("state.js, refmod.js and the picker mirror compile.py about saved references")
