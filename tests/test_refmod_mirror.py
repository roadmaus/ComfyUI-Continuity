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
      return { ok: true, status: 200, json: async () => ({ result: { mods: body.sources.map(
        (source, i) => ({ path: `refmod:cast/${body.name}${i ? `-${i + 1}` : ""}`,
                          kind: "image", tokens: 64, mode: body.mode })) } }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };""").replace(
    "  async fetchApi(url) {", "  async fetchApi(url, options = {}) {")

SCRIPT = layout.DOMSHIM if hasattr(layout, "DOMSHIM") else ""
SCRIPT = __import__("domshim").DOM + """
import * as S from "./web/creator/state.js";
import { keepable, keepAsMod } from "./web/creator/refmod.js";
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

// Nothing to keep is said, not queued.
try {
  await keepAsMod({ handle: "ghost", from: [] }, [], "full", { list: () => [] });
  out.empty = "kept";
} catch (error) { out.empty = error.message; }

// The picker: a tab, rows off the listing, no upload and no organize.
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
  upload: found("mmc-upload").map((n) => n.style.display),
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

check("a picture another member claims stays, and so does one the prompt writes",
      got["shared"], {"assets": ["img-1", "img-9", "img-2", "img-3"],
                      "anna": ["img-2", "img-3"], "ben": ["img-1"]})
check("nothing to keep is refused before the queue", got["empty"],
      "Nothing to keep — hang a picture on them first.")

check("the picker has a RefMod tab", got["picker"]["tabs"], ["Image", "RefMod"])
check("...whose cells say what a mod costs", got["picker"]["cells"],
      ["compressed · 64 tokens", "full-detail · 768 tokens"])
check("...with nothing to upload or organize", (got["picker"]["upload"], got["picker"]["organize"]),
      (["none"], ["none"]))

passed("state.js, refmod.js and the picker mirror compile.py about saved references")
