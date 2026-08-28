"""Recasting: somebody else takes a cast member's place, in one gesture.

Swapping who is in a shot used to cost four steps, three of which were undoing
damage the first one did — remove the member (which took the clip they stood in
with them), cut the source video again, cast the newcomer, hang the clip back on
them by hand. The clip stays now (`test_cast_detach`), and this is the other
half: the swap itself.

What has to survive the swap is the shot. The clips the outgoing member stood
in, the sentence about what is being changed in them, and the slot in the cast
order — cast order is subject order and ordinal order, so a newcomer appended to
the end renumbers everybody after them. What has to *move* is the prose: compile
reads the citations, so a swap that left every sentence writing the departed name
would be a piece that refuses to queue until each line is edited by hand.

    python3 tests/test_cast_recast.py

Skips itself if node is not installed.
"""

import json
import os
import shutil
import subprocess
import sys

import layout
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)

from domshim import DOM  # noqa: E402  (after the node check above)

STUBS = {
    "app.js": "export const app = { registerExtension() {}, extensionManager: null };",
    "api.js": """
export const api = {
  apiURL: (u) => u, addEventListener() {}, removeEventListener() {},
  async fetchApi(url) {
    if (String(url).startsWith("/continuity/families")) {
      const body = (await import("node:fs")).readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  },
  async getUserData() { return { status: 404, json: async () => null }; },
  async storeUserData() { return { status: 200 }; },
  async deleteUserData() { return { status: 204 }; },
};
""",
    "widgets.js": "export const ComfyWidgets = {};",
}

CHECK = r"""
await import("./dom.mjs");
const { CastShelf } = await import("./web/creator/cast.js");
const S = await import("./web/creator/state.js");

const out = { errors: [] };

const img = (handle) => ({ handle, kind: "image", role: "reference", filename: `${handle}.png` });
const clip = (handle, takes = "full") => ({
  handle, kind: "video", role: "reference", filename: `${handle}.mp4`, takes });

/**
 * A host in the shape both real ones have, with the one hook a swap adds: a
 * library window that casts somebody, and a rename that rewrites the prose.
 *
 * `arrive` is what the window does while it is open — the test's stand-in for
 * the user picking a member out of the roster. Nothing at all is a window
 * closed on nobody, which must leave the piece exactly as it was.
 */
function host({ cast, assets, texts = {}, arrive = null }) {
  const state = { cast, assets, texts };
  state.shelf = new CastShelf({
    getCast: () => state.cast,
    setCast: (list) => { state.cast = list; },
    getAssets: () => state.assets,
    addAsset: async () => null,
    whereCited: () => ({ cited: false, text: "" }),
    cite: () => {},
    touch: () => {},
    commit: () => { state.commits = (state.commits ?? 0) + 1; },
    library: async () => { arrive?.(state); },
    rename: (from, to) => { S.renameSubjectCitations([state.texts], from, to); },
    dropAssets: (handles) => {
      state.dropped = handles;
      state.assets = state.assets.filter((asset) => !handles.includes(asset.handle));
    },
  });
  return state;
}

/** What the library does when it casts somebody: attach their files where a
 *  file attaches, then append them under a handle free of everybody standing —
 *  `presets.addSubjectToPiece` and `freeSubjectHandle`, in miniature. */
const casts = (subject, files = []) => (state) => {
  for (const file of files) state.assets.push(file);
  const taken = new Set(state.cast.map((s) => s.handle));
  let handle = subject.handle;
  for (let n = 2; taken.has(handle); n += 1) handle = `${subject.handle}_${n}`;
  state.cast.push({ ...subject, handle, from: files.map((f) => f.handle) });
};

const names = (state) => state.cast.map((s) => s.handle);

try {
  // ---- the swap ------------------------------------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1"],
                  replaces: ["vid-1"], replaces_what: "the woman at the counter" };
    const extra = { handle: "rui", takes: "person", from: ["img-9"] };
    const state = host({
      cast: [ana, extra],
      assets: [img("img-1"), img("img-9"), clip("vid-1", "edit")],
      texts: { prompt: "@ana steps through the door, @rui waits" },
      arrive: casts({ handle: "bea", takes: "person" }, [img("img-4")]),
    });
    await state.shelf.recast(ana);
    out.swap = {
      cast: names(state),
      left: state.assets.map((a) => a.handle).sort(),
      dropped: state.dropped,
      place: S.replacesOf(state.cast[0]),
      what: state.cast[0].replaces_what,
      prompt: state.texts.prompt,
    };
  }

  // ---- the name the departure frees ---------------------------------------
  {
    // A second Anna. The library can only hand them `ana_2` while the first is
    // standing, and once that name is free, `ana_2` is a name nobody chose — so
    // it is taken back, and the sentences never had to move at all.
    const ana = { handle: "ana", takes: "person", from: ["img-1"], replaces: ["vid-1"] };
    const state = host({
      cast: [ana],
      assets: [img("img-1"), clip("vid-1", "edit")],
      texts: { prompt: "@ana steps through the door" },
      arrive: casts({ handle: "ana", takes: "person" }, [img("img-4")]),
    });
    await state.shelf.recast(ana);
    out.reclaimed = { cast: names(state), prompt: state.texts.prompt };
  }

  // ---- a window closed on nobody ------------------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1"], replaces: ["vid-1"] };
    const state = host({
      cast: [ana],
      assets: [img("img-1"), clip("vid-1", "edit")],
      texts: { prompt: "@ana steps through the door" },
    });
    await state.shelf.recast(ana);
    out.nobody = {
      cast: names(state),
      left: state.assets.map((a) => a.handle).sort(),
      prompt: state.texts.prompt,
    };
  }

  // ---- the clip's own narrowing lands on the newcomer ----------------------
  {
    // Attached raw, never narrowed. Standing in it is what makes it an edit,
    // and that has to happen for whoever is standing in it now.
    const ana = { handle: "ana", takes: "person", from: [], replaces: ["vid-1"] };
    const state = host({
      cast: [ana],
      assets: [clip("vid-1")],
      texts: { prompt: "@ana waits" },
      arrive: casts({ handle: "bea", takes: "person" }),
    });
    await state.shelf.recast(ana);
    out.narrowed = { takes: state.assets[0].takes, prompt: state.texts.prompt };
  }

  // ---- the rename itself, without a shelf around it ------------------------
  {
    const piece = {
      prompt: "@ana and @ana_2 and @anastasia",
      soundscape: "footsteps behind @ana",
      music: null,
      refined: { body: "@ana turns", sections: { look: "@ana in blue" } },
    };
    S.renameSubjectCitations([piece], "ana", "bea");
    out.renamed = {
      prompt: piece.prompt, soundscape: piece.soundscape,
      body: piece.refined.body, look: piece.refined.sections.look,
    };
    out.renamedNothing = S.renameSubjectCitations([piece], "nobody", "bea");
  }
} catch (error) {
  out.errors.push(`recast: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-cast-recast-")
try:
    pack = os.path.join(work, "pack")
    shutil.copytree(os.path.join(ROOT, "web"), os.path.join(pack, "web"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, source in STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(source)
    with open(os.path.join(work, "scripts", "families.json"), "w", encoding="utf-8") as handle:
        handle.write(layout.catalog_json())
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

passed("somebody else takes their place in one gesture")
FAILURES.extend(report["errors"])

# ---- the swap ---------------------------------------------------------------

swap = report.get("swap") or {}
# Their slot, not the end of the list: cast order is ordinal order.
check("the newcomer stands where they stood", swap.get("cast"), ["bea", "rui"])
check("the clip they stood in stays", "vid-1" in (swap.get("left") or []), True)
check("...and the outgoing member's own picture goes", swap.get("dropped"), ["img-1"])
check("...and the place is handed over", swap.get("place"), ["vid-1"])
check("...along with what is being changed in it",
      swap.get("what"), "the woman at the counter")
check("the prompt is rewritten to the new name",
      swap.get("prompt"), "@bea steps through the door, @rui waits")

reclaimed = report.get("reclaimed") or {}
check("a name the departure frees is taken back", reclaimed.get("cast"), ["ana"])
check("...so the sentence never moved",
      reclaimed.get("prompt"), "@ana steps through the door")

# ---- what must not happen ---------------------------------------------------

nobody = report.get("nobody") or {}
check("a library closed on nobody casts nobody", nobody.get("cast"), ["ana"])
check("...and takes nothing off the node",
      nobody.get("left"), ["img-1", "vid-1"])
check("...and leaves the sentence alone",
      nobody.get("prompt"), "@ana steps through the door")

narrowed = report.get("narrowed") or {}
check("the clip is narrowed to edit for whoever stands in it now",
      narrowed.get("takes"), "edit")

# ---- the rename, on its own -------------------------------------------------

renamed = report.get("renamed") or {}
# `\b` after the name, and an underscore is a word character — which is the whole
# reason `@ana` can be renamed at all in a piece that also holds `@ana_2`.
check("only the whole name is rewritten",
      renamed.get("prompt"), "@bea and @ana_2 and @anastasia")
check("every text the piece holds, not just the prompt",
      renamed.get("soundscape"), "footsteps behind @bea")
# The rewrite is the prompt that is actually queued while it is enabled.
check("the rewrite too", renamed.get("body"), "@bea turns")
check("...section by section", renamed.get("look"), "@bea in blue")
check("a name nobody writes moves nothing", report.get("renamedNothing"), False)

sys.exit(1 if FAILURES else 0)
