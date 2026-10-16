"""A LoRA on a cast member, on every surface that draws them (discussion #82).

A LoRA is one family's weights, so it is filed under the family it was hung
for (`state.wearOn`) and drawn on that family's tab of the wears panel
(`wears.js`). The row's menu edits its words and its weight in place, the blob
round-trips the wardrobe through the stack's own serializer, the library keeps
it with the member and hands it back, and the library's sheet draws the same
panel. Driven through the real modules
against the DOM shim, the way test_cast_role_notes.py and test_cast_editor.py
are.

    python3 tests/test_cast_lora_ui.py

Skips itself if node is not installed.
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

from domshim import DOM  # noqa: E402  (after the node check above)

STUBS = {
    "app.js": "export const app = { registerExtension() {}, extensionManager: null };",
    "api.js": """
const store = new Map();
export const api = {
  apiURL: (u) => u, addEventListener() {}, removeEventListener() {},
  async fetchApi(url) {
    if (String(url).startsWith("/continuity/families")) {
      const body = (await import("node:fs")).readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
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
const { CastShelf } = await import("./web/creator/cast.js");
const { castFamilies } = await import("./web/creator/refmod.js");
const S = await import("./web/creator/state.js");
const P = await import("./web/creator/presets.js");
const { openPresetLibrary } = await import("./web/creator/presetlib.js");

const out = { errors: [] };
const wait = () => new Promise((r) => setTimeout(r, 0));

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
const text = (node) => (node ? node.text.replace(/\s+/g, " ").replace(/ \./g, ".").trim() : null);
const press = (node) => node?.listeners?.click?.[0]?.({
  currentTarget: node, target: node, stopPropagation() {}, preventDefault() {},
});
function type(field, value) {
  field.value = value;
  field.listeners?.input?.[0]?.({ target: field, currentTarget: field, stopPropagation() {} });
}

const img = (handle) => ({ handle, kind: "image", role: "reference", filename: `${handle}.png` });
const ANNA = { name: "people/anna_v3.safetensors", strength: 0.85, triggers: ["ohwx anna"] };
const KLEIN = { name: "people/anna_klein.safetensors", strength: 0.7, triggers: ["ann4"] };

function host({ cast, assets }) {
  const state = { cast, assets, touched: 0, committed: 0 };
  state.shelf = new CastShelf({
    getCast: () => state.cast,
    setCast: (list) => { state.cast = list; },
    getAssets: () => state.assets,
    addAsset: async () => null,
    whereCited: () => ({ cited: false, text: "" }),
    cite: () => {},
    touch: () => { state.touched += 1; },
    commit: () => { state.committed += 1; },
    families: () => castFamilies("h3", "h3_vae", {}),
    vae: () => "h3_vae",
  });
  return state;
}

try {
  // ---- the shelf: the tab, the row, the menu -----------------------------------
  {
    // A flat list from before the rows existed, read as the piece's family's.
    const ana = S.parseState(JSON.stringify({
      prompt: "@ana", assets: [img("img-1")],
      subjects: [{ handle: "ana", takes: "person", from: ["img-1"], loras: [{ ...ANNA, triggers: [...ANNA.triggers] }] }],
      duration_s: 6, aspect: "16:9", short_edge: 768,
    })).subjects[0];
    out.migrated = JSON.parse(JSON.stringify(ana.wears));
    S.wearOn(ana, "flux2klein").loras.push({ ...KLEIN, triggers: [...KLEIN.triggers] });
    const bare = { handle: "ben", takes: "person", description: "a tall man" };
    const state = host({ cast: [ana, bare], assets: [img("img-1")] });
    state.shelf.render();
    // The shut line marks that Ana wears something and Ben wears nothing.
    out.shutMarks = all(state.shelf.root, "mmc-cast-row").map((row) => Boolean(one(row, "mmc-cast-line-wears")));
    state.shelf.opened = ana;
    state.shelf.render();
    const root = state.shelf.root;
    out.tabs = all(root, "mmc-wears-tab").map((tab) => [text(tab), all(tab, "mmc-wears-dot").map((d) => d.className)]);
    out.sentence = text(one(root, "mmc-wears-sentence"));
    const row = one(root, "mmc-wears-lora");
    out.row = { lead: text(one(row, "mmc-wears-row-lead")), note: text(one(row, "mmc-wears-row-note")),
                weight: text(one(row, "mmc-wears-weight")) };
    out.addOffered = all(root, "mmc-wears-act").map(text).includes("+ LoRA");
    // The Klein tab wears the Klein one, and only that one.
    state.shelf.wears.open = "flux2klein";
    state.shelf.render();
    out.kleinSentence = text(one(root, "mmc-wears-sentence"));
    out.kleinRows = all(root, "mmc-wears-lora").map((r) => text(one(r, "mmc-wears-row-lead")));
    state.shelf.wears.open = "h3";
    state.shelf.render();

    // The row's menu: words and weight at its head, written to the entry as
    // typed and dragged; a row takes it off.
    press(one(root, "mmc-wears-lora"));
    await wait();
    const menu = one(globalThis.document.body, "mmc-cast-menu");
    const wordsField = one(one(menu, "mmc-cast-menu-wear"), "mmc-cast-menu-field");
    type(wordsField, "OHWX anna, film still ");
    const slider = one(menu, "mmc-cast-menu-weight");
    type(slider, "0.6");
    const worn = () => S.subjectLoras(ana, "h3")[0];
    out.edited = { triggers: worn().triggers, strength: worn().strength,
                   touched: state.touched > 0, committed: state.committed };
    const mute = all(menu, "mmc-opt").find((b) => /^Mute\b/.test(b.text.replace(/\s+/g, " ").trim()));
    press(mute);
    await wait();
    out.muted = { enabled: worn().enabled, committed: state.committed };
    // Struck on the redraw, not gone.
    out.mutedRow = String(one(state.shelf.root, "mmc-wears-lora")?.className).includes("off");
    press(one(state.shelf.root, "mmc-wears-lora"));
    await wait();
    const menu2 = all(globalThis.document.body, "mmc-cast-menu").pop();
    const off = all(menu2, "mmc-opt").find((b) => /Take it off/.test(b.text));
    press(off);
    await wait();
    out.takenOff = { h3: ana.wears?.h3 ?? null, klein: S.subjectLoras(ana, "flux2klein").map((e) => e.name),
                     rows: all(state.shelf.root, "mmc-wears-lora").length };
  }

  // ---- the blob: through the stack's own serializer and back -----------------
  {
    const timeline = S.parseTimeline(JSON.stringify({
      version: 2, prompt: "", segments: [{ prompt: "@ana walks in.", duration_s: 6 }],
      subjects: [{ handle: "ana", from: ["ref-1"],
                   loras: [{ ...ANNA, enabled: true, modes: ["fl2va", "ref2va"], triggers: "ohwx anna, Blue" }] }],
    }));
    const stored = JSON.parse(S.serializeTimeline(timeline)).subjects[0];
    out.roundTrip = { loras: stored.loras ?? null, wears: stored.wears };
    // The mirror of `compile.cast_loras`: her LoRA counts on the shot that
    // cites her, under the shot's own entry for the same file.
    S.syncTimeline?.(timeline);
    const shot = timeline.segments[0];
    shot.loras = [{ name: ANNA.name, strength: 0.4, enabled: true, modes: ["fl2va", "ref2va"], triggers: [] }];
    out.active = S.activeLoras(shot).map((e) => [e.name, e.strength]);
    out.activeOff = S.activeLoras({ ...shot, prompt: "an empty room.", loras: [] }).length;
    // A wardrobe with a row for a still family round-trips whole, and a
    // checkpoint claim is not written for a family that routes between none.
    const dressed = S.parseTimeline(JSON.stringify({
      version: 2, prompt: "", segments: [{ prompt: "@ana", duration_s: 6 }],
      subjects: [{ handle: "ana", from: ["ref-1"], wears: {
        h3: { loras: [{ ...ANNA, modes: ["ref2va"] }] },
        flux2klein: { send: "words", loras: [{ ...KLEIN, modes: ["ref2va"] }] } } }],
    }));
    out.wardrobe = JSON.parse(S.serializeTimeline(dressed)).subjects[0].wears;
    out.wornOnKlein = S.subjectLoras(dressed.subjects[0], "flux2klein").map((e) => e.name);
  }

  // ---- a still's blob: the same cast, over its refs --------------------------
  {
    const still = S.parsePreStage(JSON.stringify({
      version: 1, arch: "flux2klein", prompt: "@ana at dusk",
      refs: [{ handle: "img-1", filename: "a.png", mods: { flux2: "refmod:cast/ana.flux2" } }],
      subjects: [{ handle: "ana", from: ["img-1"], loras: [{ ...KLEIN, triggers: [...KLEIN.triggers] }] }],
    }));
    const back = JSON.parse(S.serializePreStage(still));
    out.still = {
      refs: still.refs.map((r) => [r.handle, r.kind, r.role, r.mods ?? null]),
      wears: back.subjects?.[0]?.wears ?? null,
      backRefs: back.refs,
      // Its LoRAs count on the still's own family, as the compiler's do.
      active: S.activeLoras(still, "flux2klein").map((e) => e.name),
      triggers: S.promptTriggers(still, "flux2klein"),
      cited: S.citedCast(still).map((s) => s.handle),
    };
  }

  // ---- the library: kept with them, handed back ------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1"],
                  wears: { h3: { loras: [{ ...ANNA, triggers: [...ANNA.triggers], enabled: false }] },
                           flux2klein: { send: "pictures" } } };
    const captured = P.captureSubject(ana, [img("img-1")]);
    out.kept = captured.data.cast.wears;
    out.facts = P.castFactsLine(P.factsOf(captured.data, "cast"));
    const landed = P.addSubjectToPiece(captured.data.cast, { assets: [], subjects: [], segments: [] });
    out.landed = landed.wears;
    // A member wearing nothing writes no key.
    out.plainKept = "wears" in P.captureSubject({ handle: "ben", from: ["img-1"] }, [img("img-1")]).data.cast;
    // ...and a LoRA with a word is enough to stand behind a name; one without is not.
    out.problem = [
      S.subjectProblem({ subjects: [], assets: [] }, { handle: "ben", wears: { h3: { loras: [{ ...ANNA }] } } }),
      S.subjectProblem({ subjects: [], assets: [] }, { handle: "ben", wears: { h3: { loras: [{ name: "x", triggers: [] }] } } }),
    ];
  }

  // ---- the sheet: a row, its menu ---------------------------------------------
  {
    openPresetLibrary({ scope: "cast" });
    await wait(); await wait();
    const modal = one(globalThis.document.body, "mmc-modal");
    const newButton = all(modal, "mmc-upload").find((b) => /New cast member/.test(b.text));
    press(newButton);
    await wait(); await wait(); await wait();
    const lib = globalThis.__lib;
    lib.body.cast.wears = { h3: { loras: [{ ...ANNA, triggers: [...ANNA.triggers] }] } };
    lib.renderSheet();
    const sheet = one(modal, "mmc-cast-sheet");
    const row = one(sheet, "mmc-wears-lora");
    out.sheetRow = {
      drawn: Boolean(row),
      name: text(one(row, "mmc-wears-row-lead")),
      note: text(one(row, "mmc-wears-row-note")),
      weight: text(one(row, "mmc-wears-weight")),
    };
    out.sheetTabs = all(sheet, "mmc-wears-tab").length;
    out.sheetOffers = all(sheet, "mmc-wears-act").map(text).includes("+ LoRA");
    press(row);
    await wait();
    const menu = all(globalThis.document.body, "mmc-cast-menu").pop();
    type(one(one(menu, "mmc-cast-menu-wear"), "mmc-cast-menu-field"), "ohwx anna, portrait");
    await lib.flushSave();
    const rows = (await P.listPresets({ force: true })).filter((r) => r.scope === "cast");
    const body = await P.loadBody(rows[0]);
    out.sheetStored = body.cast.wears;
    out.sheetFacts = rows[0].facts?.loras;
  }
} catch (error) {
  out.errors.push(`cast lora: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-cast-lora-")
try:
    pack = os.path.join(work, "pack")
    shutil.copytree(os.path.join(ROOT, "web"), os.path.join(pack, "web"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, source in STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(source)
    with open(os.path.join(work, "scripts", "families.json"), "w", encoding="utf-8") as handle:
        handle.write(layout.catalog_json())
    # The library instance is otherwise private to `openPresetLibrary` — the
    # same seam test_cast_editor.py opens.
    lib_path = os.path.join(pack, "web", "creator", "presetlib.js")
    with open(lib_path, encoding="utf-8") as handle:
        source = handle.read()
    source = source.replace(
        "    this.unmount = mountOverlay(this.overlay, () => this.close());",
        "    globalThis.__lib = this;\n"
        "    this.unmount = mountOverlay(this.overlay, () => this.close());")
    with open(lib_path, "w", encoding="utf-8") as handle:
        handle.write(source)
    for name, text in (("dom.mjs", DOM), ("check.mjs", CHECK)):
        with open(os.path.join(pack, name), "w", encoding="utf-8") as handle:
            handle.write(text)
    result = subprocess.run(["node", os.path.join(pack, "check.mjs")],
                            capture_output=True, text=True, cwd=pack)
finally:
    shutil.rmtree(work, ignore_errors=True)

if result.returncode != 0:
    print("the cast shelf did not run:\n"
          + (result.stderr.strip() or result.stdout.strip()))
    sys.exit(1)

report = json.loads(result.stdout.strip().splitlines()[-1])
from harness import FAILURES, check, passed  # noqa: E402

FAILURES.extend(report["errors"])
ANNA_ENTRY = {"name": "people/anna_v3.safetensors", "strength": 0.85, "triggers": ["ohwx anna"]}

# ---- the shelf --------------------------------------------------------------

check("a flat list from before the rows existed is the piece's family's row",
      report.get("migrated"), {"h3": {"loras": [ANNA_ENTRY]}})
check("the open card has a tab per family; hers wear a LoRA dot on H3 and on Klein",
      [tab for tab in (report.get("tabs") or []) if "lora" in " ".join(tab[1])],
      [["MiniMax H3 this piece", ["mmc-wears-dot pic", "mmc-wears-dot lora"]],
       ["Flux 2 Klein", ["mmc-wears-dot pic", "mmc-wears-dot lora"]]])
check("the sentence says what H3 gets and what she wears there",
      report.get("sentence"), "When MiniMax H3 renders @ana it gets their picture wearing anna_v3 “ohwx anna”.")
check("the row says the file, the words and the weight",
      report.get("row"), {"lead": "anna_v3", "note": "trigger words ohwx anna", "weight": "0.85 weight"})
check("...and the way to hang another beside it", report.get("addOffered"), True)
check("the Klein tab wears the Klein one and only that one",
      (report.get("kleinSentence"), report.get("kleinRows")),
      ("When Flux 2 Klein renders @ana it gets their picture wearing anna_klein “ann4”.", ["anna_klein"]))
check("the shut line marks who wears something", report.get("shutMarks"), [True, False])
check("the menu writes the words as typed and the weight as dragged, without committing",
      report.get("edited"),
      {"triggers": ["OHWX anna", "film still"], "strength": 0.6, "touched": True, "committed": 0})
check("muting is a row, and a commit", report.get("muted"), {"enabled": False, "committed": 1})
check("...and the row is struck, not gone", report.get("mutedRow"), True)
check("taking it off drops H3's row and leaves Klein's",
      report.get("takenOff"), {"h3": None, "klein": ["people/anna_klein.safetensors"], "rows": 0})

# ---- the blob ---------------------------------------------------------------

check("the blob writes the entry under the piece's family through the stack's serializer — no modes where both are claimed",
      report.get("roundTrip"),
      {"loras": None, "wears": {"h3": {"loras": [{"name": "people/anna_v3.safetensors", "strength": 0.85,
                                                  "triggers": ["ohwx anna", "Blue"]}]}}})
check("the shot's active stack mirrors compile: hers under the shot's own for the same file",
      report.get("active"), [["people/anna_v3.safetensors", 0.4]])
check("...and nothing where she is not cited", report.get("activeOff"), 0)
check("a wardrobe round-trips whole, a claim kept on H3 and dropped on a family that routes between none",
      report.get("wardrobe"),
      {"h3": {"loras": [{"name": "people/anna_v3.safetensors", "strength": 0.85, "triggers": ["ohwx anna"],
                         "modes": ["ref2va"]}]},
       "flux2klein": {"send": "words", "loras": [{"name": "people/anna_klein.safetensors", "strength": 0.7,
                                                  "triggers": ["ann4"]}]}})
check("...and she wears Klein's row on Klein", report.get("wornOnKlein"), ["people/anna_klein.safetensors"])

# ---- a still's blob ---------------------------------------------------------

check("a still's references are pictures the shelf can read, carrying their renditions",
      (report.get("still") or {}).get("refs"), [["img-1", "image", "reference", {"flux2": "refmod:cast/ana.flux2"}]])
check("...its flat list from before the rows is the still family's row, and the blob keeps neither kind nor role",
      ((report.get("still") or {}).get("wears"), (report.get("still") or {}).get("backRefs")),
      ({"flux2klein": {"loras": [{"name": "people/anna_klein.safetensors", "strength": 0.7, "triggers": ["ann4"]}]}},
       [{"handle": "img-1", "filename": "a.png", "mods": {"flux2": "refmod:cast/ana.flux2"}}]))
check("...and her LoRA counts on the still, with its word in front",
      ((report.get("still") or {}).get("active"), (report.get("still") or {}).get("triggers"),
       (report.get("still") or {}).get("cited")),
      (["people/anna_klein.safetensors"], ["ann4"], ["ana"]))

# ---- the library ------------------------------------------------------------

check("the library keeps the wardrobe, muted or not, send words included",
      report.get("kept"),
      {"h3": {"loras": [{"name": "people/anna_v3.safetensors", "strength": 0.85, "enabled": False,
                         "triggers": ["ohwx anna"]}]},
       "flux2klein": {"send": "pictures"}})
check("...and the card says so", report.get("facts"), "person · 1 picture · 1 LoRA")
check("...and hands it back onto a piece", report.get("landed"), report.get("kept"))
check("a member wearing nothing writes no key", report.get("plainKept"), False)
check("a LoRA with a word stands behind a name; one without does not",
      report.get("problem"),
      ["", "their LoRA has no trigger word — give it one, or describe them in words"])

# ---- the sheet --------------------------------------------------------------

check("the sheet draws them as a row on the family's tab", report.get("sheetRow"),
      {"drawn": True, "name": "anna_v3", "note": "trigger words ohwx anna", "weight": "0.85 weight"})
check("...with a tab per family and a way to hang one",
      (report.get("sheetTabs"), report.get("sheetOffers")), (8, True))
check("the row's menu writes the words to the member on disk",
      report.get("sheetStored"),
      {"h3": {"loras": [{"name": "people/anna_v3.safetensors", "strength": 0.85, "triggers": ["ohwx anna", "portrait"]}]}})
check("...and the index counts it", report.get("sheetFacts"), 1)

passed("a cast member wears a LoRA on the card, in the blob, in the library and on the sheet")
