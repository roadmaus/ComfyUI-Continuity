"""Removing a cast member takes their pictures off the node with them.

Casting somebody *attaches* files: the `+` on their card opens the picker and
hangs what comes back on the node, and taking them out of the library does the
same thing with the filenames it stored. Removing them used to undo only half of
that — the member went, the pictures stayed, and the only way back was to find
each one on the asset row and press its own ✕.

The whole difficulty is what must NOT be dropped, and that is what most of this
file is:

* a picture two members are built out of — the other one still needs it;
* a file a prompt writes by hand as `@img-2` — a pool asset can be cited with no
  subject in between, and dropping it breaks the sentence;
* the pool, when the removal happened on one card of a strip — the pool belongs
  to the piece, and one shot is not where a file is taken off every other shot;
* the clip somebody stands in the place of, when a second member stands in it
  too.

Driven through the real `CastShelf` against a plain object host, because the
ordering is the subtle part: `remove` reads the claims *before* the cast is
rewritten, and asks the host *after*.

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
    if (String(url).startsWith("/minimax_creator/families")) {
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

/** A host in the shape both real ones have: a cast, a bag of files, and a rule
 *  about which of them a departing member may take. `texts` is what the node
 *  has written down, which is the half only a host can answer for. */
function host({ cast, assets, texts = [] }) {
  const state = { cast, assets, texts };
  state.shelf = new CastShelf({
    getCast: () => state.cast,
    setCast: (list) => { state.cast = list; },
    getAssets: () => state.assets,
    addAsset: async () => null,
    whereCited: () => ({ cited: false, text: "" }),
    cite: () => {},
    touch: () => {},
    commit: () => {},
    dropAssets: (handles) => {
      state.dropped = handles;
      state.assets = state.assets.filter(
        (asset) => !handles.includes(asset.handle)
                || S.handleWritten(state.texts, asset.handle));
    },
  });
  return state;
}

const img = (handle) => ({ handle, kind: "image", role: "reference", filename: `${handle}.png` });
const clip = (handle) => ({ handle, kind: "video", role: "reference", filename: `${handle}.mp4` });
const left = (state) => state.assets.map((a) => a.handle);

try {
  // ---- the plain case ------------------------------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1", "img-2"], motion: "vid-1" };
    const state = host({ cast: [ana], assets: [img("img-1"), img("img-2"), clip("vid-1")] });
    state.shelf.remove(ana);
    out.plain = { left: left(state), dropped: state.dropped, cast: state.cast.length };
  }

  // ---- a picture two members share ----------------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1", "img-2"] };
    const rui = { handle: "rui", takes: "person", from: ["img-2"] };
    const state = host({ cast: [ana, rui], assets: [img("img-1"), img("img-2")] });
    state.shelf.remove(ana);
    out.shared = { left: left(state), dropped: state.dropped };
  }

  // ---- a file the prompt writes by hand ------------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1", "img-2"] };
    const state = host({
      cast: [ana],
      assets: [img("img-1"), img("img-2")],
      texts: ["a wide shot of the room, @img-2 on the table"],
    });
    state.shelf.remove(ana);
    // Offered by the shelf — it is theirs alone — and kept by the host, which
    // is the only one that can read the sentence.
    out.written = { left: left(state), dropped: state.dropped };
  }

  // ---- the clip somebody stands in the place of ---------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1"], replaces: "vid-1" };
    const rui = { handle: "rui", takes: "person", from: ["img-3"], replaces: "vid-1" };
    const state = host({ cast: [ana, rui],
                         assets: [img("img-1"), img("img-3"), clip("vid-1")] });
    state.shelf.remove(ana);
    out.replaces = { left: left(state), dropped: state.dropped };
  }

  // ---- a member with nothing behind them ----------------------------------
  {
    const keeper = { handle: "keeper", takes: "person", from: [],
                     description: "a retired lighthouse keeper" };
    const state = host({ cast: [keeper], assets: [img("img-1")] });
    state.shelf.remove(keeper);
    // Nothing to drop, so the host is not called at all — a node whose files
    // belong to nobody must not lose them to somebody else's departure.
    out.described = { left: left(state), called: state.dropped !== undefined };
  }

  // ---- a host that cannot detach ------------------------------------------
  {
    const ana = { handle: "ana", takes: "person", from: ["img-1"] };
    const shelf = new CastShelf({
      getCast: () => cast, setCast: (l) => { cast = l; }, getAssets: () => [],
      addAsset: async () => null, whereCited: () => ({ cited: false, text: "" }),
      cite: () => {}, touch: () => {}, commit: () => {},
    });
    let cast = [ana];
    shelf.remove(ana);
    out.noHook = { cast: cast.length };
  }

  // ---- the claim itself, without a shelf around it ------------------------
  {
    const ana = { handle: "ana", from: ["img-1", "img-2"], voice: "snd-1" };
    const rui = { handle: "rui", from: ["img-2"] };
    out.claims = S.soleClaims(ana, [ana, rui]).sort();
    out.claimsAlone = S.soleClaims(ana, [ana]).sort();
  }
} catch (error) {
  out.errors.push(`detach: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-cast-detach-")
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

passed("a member leaving takes their own pictures with them")
FAILURES.extend(report["errors"])

# ---- what should go ---------------------------------------------------------

plain = report.get("plain") or {}
check("their pictures and their clip go with them", plain.get("left"), [])
check("...and the shelf named exactly those",
      sorted(plain.get("dropped") or []), ["img-1", "img-2", "vid-1"])
check("...and they are out of the cast", plain.get("cast"), 0)

# ---- what should stay -------------------------------------------------------

shared = report.get("shared") or {}
# The other member is still built out of it. This is the case that makes the
# whole thing a claim question rather than a file question.
check("a picture another member is built out of stays", shared.get("left"), ["img-2"])
check("...and is never offered for dropping", shared.get("dropped"), ["img-1"])

written = report.get("written") or {}
# The shelf offers it — nobody else claims it — and the host keeps it, because
# the host is the only one holding the sentence.
check("a file the prompt writes by hand stays", written.get("left"), ["img-2"])
check("...though the shelf did offer it",
      sorted(written.get("dropped") or []), ["img-1", "img-2"])

replaces = report.get("replaces") or {}
check("a clip a second member stands in stays",
      sorted(replaces.get("left") or []), ["img-3", "vid-1"])

described = report.get("described") or {}
check("a member with nothing behind them takes nothing", described.get("left"), ["img-1"])
check("...and the host is not troubled at all", described.get("called"), False)

# A shelf whose host offers no way to detach still removes the member — the
# PreStage mounts one, and a missing hook must not throw on a ✕.
check("a host with no way to detach still removes them",
      (report.get("noHook") or {}).get("cast"), 0)

# ---- the claim, on its own --------------------------------------------------

check("a claim is what nobody else claims", report.get("claims"), ["img-1", "snd-1"])
check("...and alone, that is everything they hold",
      report.get("claimsAlone"), ["img-1", "img-2", "snd-1"])

sys.exit(1 if FAILURES else 0)
