"""A file's words survive it changing what it lends a subject.

The tile's menu takes a sentence about the file — "how they move when smoking
a cigar, motion sheet" — and the same menu is where the file is switched from
their looks to their action. Switching used to lose the sentence (issue #70):
the move cleared the old slot before filling the new one, and the clear drops a
file's words the moment it is on none of their slots.

Driven through the real `CastShelf` against a plain object host, the way
test_cast_detach.py does.

    python3 tests/test_cast_detach.py

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
    // The family catalog, written beside this stub — manifest.js loads it at
    // import, the same way the real route serves it.
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

const out = { errors: [] };

function host({ cast, assets }) {
  const state = { cast, assets };
  state.shelf = new CastShelf({
    getCast: () => state.cast,
    setCast: (list) => { state.cast = list; },
    getAssets: () => state.assets,
    addAsset: async () => null,
    whereCited: () => ({ cited: false, text: "" }),
    cite: () => {},
    touch: () => {},
    commit: () => {},
  });
  return state;
}

const img = (handle) => ({ handle, kind: "image", role: "reference", filename: `${handle}.png` });
const clip = (handle) => ({ handle, kind: "video", role: "reference", filename: `${handle}.mp4` });

try {
  // ---- looks -> action, the report itself ---------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1"],
                  notes: { "img-1": "how they move when smoking a cigar, motion sheet" } };
    const state = host({ cast: [ana], assets: [img("img-1")] });
    state.shelf.setRole(ana, "img-1", "from", "motion");
    out.toAction = { note: ana.notes?.["img-1"], from: ana.from, motion: ana.motion };
  }

  // ---- and back again -----------------------------------------------------
  {
    const ana = { handle: "ana", takes: "person", motion: "img-1",
                  notes: { "img-1": "the cigar" } };
    const state = host({ cast: [ana], assets: [img("img-1")] });
    state.shelf.setRole(ana, "img-1", "motion", "from");
    out.toLooks = { note: ana.notes?.["img-1"], from: ana.from, motion: ana.motion };
  }

  // ---- a sibling moving out of the list does not take the others' words --
  // (the place they take carries its own words, `replaces_what`, so nothing
  // rides on the clip itself)
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1", "vid-1"],
                  notes: { "img-1": "the face" } };
    const state = host({ cast: [ana], assets: [img("img-1"), clip("vid-1")] });
    state.shelf.setRole(ana, "vid-1", "from", "replaces");
    out.toPlace = { notes: ana.notes, from: ana.from, replaces: ana.replaces };
  }

  // ---- taking it off still drops the words --------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1"],
                  notes: { "img-1": "gone with it" } };
    const state = host({ cast: [ana], assets: [img("img-1")] });
    state.shelf.clearRole(ana, "img-1", "from");
    out.off = { notes: ana.notes ?? null, from: ana.from ?? null };
  }
} catch (error) {
  out.errors.push(`role: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-cast-role-")
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

passed("a file keeps its words across a change of slot")
FAILURES.extend(report["errors"])

toAction = report.get("toAction") or {}
check("looks -> action keeps the note",
      toAction.get("note"), "how they move when smoking a cigar, motion sheet")
check("...and the file moved", (toAction.get("from"), toAction.get("motion")), (None, "img-1"))

toLooks = report.get("toLooks") or {}
check("action -> looks keeps the note", toLooks.get("note"), "the cigar")
check("...and the file moved", (toLooks.get("from"), toLooks.get("motion")), (["img-1"], None))

toPlace = report.get("toPlace") or {}
check("a sibling leaving the list keeps the others' notes",
      toPlace.get("notes"), {"img-1": "the face"})
check("...and only the clip moved",
      (toPlace.get("from"), toPlace.get("replaces")), (["img-1"], ["vid-1"]))

off = report.get("off") or {}
check("taking a file off them still drops its words", off.get("notes"), None)
check("...and the slot", off.get("from"), None)

sys.exit(1 if FAILURES else 0)
