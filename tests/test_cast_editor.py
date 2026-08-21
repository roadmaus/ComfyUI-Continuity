"""A cast member is made, changed and kept without a node anywhere near it.

The thing this guards is a claim about *reach*, not about pixels. Before the
editor, the only way into the roster was: attach a picture to a node, add a
subject on that node's cast shelf, point the subject at the picture, press the
star. Three of those four steps are about a node, and a member is deliberately
not about a node — their files are stored by filename precisely so they outlive
the graph they were built on (`presets.captureSubject`).

So the check mounts the library with **no target at all** — the read-only shape
the node context menu opens — makes somebody, gives them a face, moves that file
between slots, describes them, renames them, and then reads the *stored* body
back out of userdata. Nothing in here touches a timeline, and that is the point:
if a node ever became necessary again, this is what would notice.

    python3 tests/test_cast_editor.py

Skips itself if node is not installed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)

from domshim import DOM  # noqa: E402  (after the node check above)

# userdata is a Map, because the whole test is "what is actually on disk after
# the sheet has been typed into" — a stub that forgot would pass everything.
STUBS = {
    "app.js": "export const app = { registerExtension() {}, extensionManager: null };",
    "api.js": """
const store = new Map();
globalThis.__userdata = store;
export const api = {
  apiURL: (u) => u,
  addEventListener() {}, removeEventListener() {},
  async fetchApi() { return { ok: true, status: 200, json: async () => ({}) }; },
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
const { openPresetLibrary } = await import("./js/minimax_creator/presetlib.js");
const P = await import("./js/minimax_creator/presets.js");

const out = { errors: [] };
const wait = () => new Promise((r) => setTimeout(r, 0));

/** Everything under `root` carrying `cls`, flattened. */
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
const press = (node) => node?.listeners?.click?.[0]?.({
  currentTarget: node, target: node, stopPropagation() {}, preventDefault() {},
});
function type(field, value) {
  field.value = value;
  field.listeners?.input?.[0]?.({
    target: field, currentTarget: field, stopPropagation() {},
  });
}

// The picker hands back whatever the test queued, without a modal.
const picked = [];
globalThis.__pick = picked;

try {
  // No target: the read-only shape the node context menu opens. If making
  // somebody needed a node, it would fail right here.
  openPresetLibrary({ scope: "cast" });
  await wait(); await wait();

  const modal = one(globalThis.document.body, "mmc-modal");
  if (!modal) throw new Error("the library did not mount");

  // ---- the way in ----------------------------------------------------------
  const newButton = all(modal, "mmc-upload").find((b) => /New cast member/.test(b.text));
  out.hasNewButton = Boolean(newButton);
  press(newButton);
  await wait(); await wait(); await wait();

  const sheet = one(modal, "mmc-cast-sheet");
  const lib = globalThis.__lib;
  out.sheetOpened = Boolean(lib?.editing);
  out.gridHidden = one(modal, "mmc-preset-split")?.style?.display === "none";
  // A row exists from the moment New is pressed — which is why there is no Save.
  out.savedImmediately = (await P.listPresets({ force: true }))
    .filter((row) => row.scope === "cast").length;

  // ---- their name ----------------------------------------------------------
  const nameField = one(sheet, "mmc-cast-sheet-name");
  // A handle is a token in a sentence, so what a sentence cannot separate it
  // from is refused as it is typed rather than at save time.
  type(nameField, "an na!");
  out.handleCleaned = lib.body.cast.handle;
  type(nameField, "ana");
  await lib.flushSave();

  // ---- what they are made of ----------------------------------------------
  picked.push([{ path: "people/ana.png", kind: "image" }]);
  await lib.addFile(lib.body.cast);
  picked.push([{ path: "people/walk.mp4", kind: "video" }]);
  await lib.addFile(lib.body.cast);
  picked.push([{ path: "people/voice.wav", kind: "audio" }]);
  await lib.addFile(lib.body.cast);
  // The slot is guessed from what the file *is* — the shelf's own guess.
  out.guessedSlots = lib.body.cast.files.map((f) => f.slot);

  // The three single-file slots hold one each, so moving a second file into an
  // occupied one must send the sitting tenant back to `from` rather than
  // silently dropping it.
  lib.setSlot(lib.body.cast, 1, "motion");
  await wait(); await wait();
  out.afterMove = lib.body.cast.files.map((f) => `${f.filename.split("/")[1]}:${f.slot}`);

  // ---- their description ---------------------------------------------------
  const desc = one(sheet, "mmc-cast-sheet-desc");
  out.hasDescription = Boolean(desc);
  type(desc, "Nervous around strangers, never takes the cardigan off.");
  await lib.flushSave();

  // ---- what is actually on disk -------------------------------------------
  const rows = (await P.listPresets({ force: true })).filter((r) => r.scope === "cast");
  const row = rows[0];
  const body = await P.loadBody(row);
  out.stored = {
    rows: rows.length,
    // The row's name IS their handle: a card saying one thing and the prompt
    // token being another would make the roster unusable.
    name: row.name,
    handle: body.cast.handle,
    takes: body.cast.takes,
    description: body.cast.description,
    files: body.cast.files.map((f) => ({ slot: f.slot, filename: f.filename })),
  };
  // The card's own reading, off the index alone — no body fetched.
  out.card = { blurb: row.blurb ?? null, facts: row.facts, portrait: row.portrait };
  out.factsLine = P.castFactsLine(row.facts);

  // ---- and back out --------------------------------------------------------
  press(one(sheet, "mmc-cast-sheet-back"));
  await wait(); await wait();
  out.closedBack = !lib.editing && one(modal, "mmc-preset-split")?.style?.display !== "none";
} catch (error) {
  out.errors.push(`cast editor: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-cast-editor-")
try:
    pack = os.path.join(work, "pack")
    shutil.copytree(os.path.join(ROOT, "js"), os.path.join(pack, "js"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, source in STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(source)

    # Two seams the sheet reaches through, stubbed in the copy rather than in the
    # check: the picker is a modal this has no way to drive, and the library
    # instance is otherwise private to `openPresetLibrary`.
    lib_path = os.path.join(pack, "js", "minimax_creator", "presetlib.js")
    with open(lib_path, encoding="utf-8") as handle:
        source = handle.read()
    source = source.replace(
        'import { openPicker } from "./picker.js";',
        "const openPicker = async () => globalThis.__pick.shift() ?? null;")
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
    print("the cast editor did not run:\n"
          + (result.stderr.strip() or result.stdout.strip()))
    sys.exit(1)

report = json.loads(result.stdout.strip().splitlines()[-1])
from harness import FAILURES, check, passed  # noqa: E402

passed("a cast member is made, changed and kept with no node in sight")
FAILURES.extend(report["errors"])

# ---- the way in -------------------------------------------------------------

check("the roster offers a way to make somebody", report.get("hasNewButton"), True)
check("...which opens the editor", report.get("sheetOpened"), True)
check("...over the grid rather than beside it", report.get("gridHidden"), True)
# There is no Save button, so the row has to exist from the first press —
# otherwise a closed window would be a lost member.
check("...on a member that is already in the library", report.get("savedImmediately"), 1)

# ---- their name -------------------------------------------------------------

check("a handle keeps only what a sentence can hold", report.get("handleCleaned"), "an_na_")

# ---- what they are made of --------------------------------------------------

# A recording is a voice; everything you can see lends looks until you say
# otherwise. Deliberately the shelf's own guess — `cast.js` picks the first role
# a file fits and the roles are ordered looks-first — so a clip attached here and
# a clip dropped on a card land in the same slot.
check("a file's slot is guessed from what it is",
      report.get("guessedSlots"), ["from", "from", "voice"])
# Moving the picture onto `motion` evicts the clip that was there, back to the
# slot everything can hold, rather than dropping it.
check("...and a slot that holds one file evicts rather than drops",
      report.get("afterMove"),
      ["ana.png:from", "walk.mp4:motion", "voice.wav:voice"])

# ---- their description ------------------------------------------------------

check("the editor has a description field", report.get("hasDescription"), True)

# ---- what is on disk --------------------------------------------------------

stored = report.get("stored") or {}
check("one member was kept", stored.get("rows"), 1)
check("their handle is stored", stored.get("handle"), "ana")
check("...and is the row's name too", stored.get("name"), "ana")
check("what they are is stored", stored.get("takes"), "person")
check("their description is stored",
      stored.get("description"), "Nervous around strangers, never takes the cardigan off.")
# Filenames, not handles: the whole reason a member survives leaving their node.
check("their files are stored by name, in their slots", stored.get("files"), [
    {"slot": "from", "filename": "people/ana.png"},
    {"slot": "motion", "filename": "people/walk.mp4"},
    {"slot": "voice", "filename": "people/voice.wav"},
])

# ---- what the card reads off the index alone --------------------------------

card = report.get("card") or {}
check("the card carries their prose",
      card.get("blurb"), "Nervous around strangers, never takes the cardigan off.")
# The face is the first *image* lending them their looks — a clip in that slot
# is not one, which is why the facts line counts the two apart.
check("...and their face is the still, not the clip",
      card.get("portrait"), "people/ana.png")
check("the facts line reads as an instrument",
      report.get("factsLine"), "person · 1 picture · moves · voice")

# ---- and back out -----------------------------------------------------------

check("the way out returns the roster", report.get("closedBack"), True)

sys.exit(1 if FAILURES else 0)
