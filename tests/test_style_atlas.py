"""The vendored style atlas is complete, and a style applied leads the prompt.

Two halves, and the first is the one that rots. `web/creator/presets/`
holds a generated index and two folders of pictures, written by
`tools/vendor_style_atlas.py` from upstream's page — and the failure mode of a
vendored asset tree is not a crash, it is a card with a hole where a picture
should be, six months after somebody moved a file. So: every clip the index names
has a still, every still on disk is named by the index, and the counts stamped in
the header are the counts in the arrays.

The second half is the one thing a style does that no other section does. Every
other section replaces the field it lands on; a style is a clause at the front of
a sentence somebody wrote, and applying a second one has to *swap* the first
rather than stack on it. That is `leadWithStyle`, and it is checked against the
real vocabulary rather than a fixture, because the whole trick is knowing what a
descriptor looks like and the atlas is the only place that is written down.

    python3 tests/test_style_atlas.py

Skips itself if node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import layout
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESETS = layout.js("presets")
MODULE = os.path.join(PRESETS, "atlas.js")
THUMBS = os.path.join(PRESETS, "atlas")
STILLS = os.path.join(THUMBS, "full")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import FAILURES, check, passed, skip  # noqa: E402

passed("the style atlas is whole, and a style leads the prompt")

if not os.path.isfile(MODULE):
    FAILURES.append("web/creator/presets/atlas.js is missing — run "
                    "tools/vendor_style_atlas.py")
    sys.exit(1)

with open(MODULE, encoding="utf-8") as handle:
    source = handle.read()

# ---- the generated index ----------------------------------------------------
#
# Read with a regex rather than by importing it: the point is that the file on
# disk says what it should, and a reader that ran the file could not tell a
# missing line from a clever one.

rows = [json.loads(line[:-1]) for line in source.splitlines()
        if line.startswith("[") and line.endswith("],")]
block = re.search(r"export const CATEGORIES = \[(.*?)\n\];", source, re.S)
categories = [json.loads(name) for name in re.findall(r'"(?:[^"\\]|\\.)*"', block.group(1))] \
    if block else []
stamped = {key: json.loads(value) for key, value in
           re.findall(r"^  (\w+): (.+),$", source, re.M)}

check("the index holds styles", bool(rows), True)
check("...in eight media categories", len(categories), 8)
check("...and says so in its header", stamped.get("styles"), len(rows))

clips = [clip for _, _, ids in rows for clip in ids]
check("every clip is named once", len(clips), len(set(clips)))
check("the header's clip count is the real one", stamped.get("clips"), len(set(clips)))
check("the vendored revision is stamped", bool(stamped.get("revision")), True)
check("every descriptor is text and every style has a clip",
      all(isinstance(phrase, str) and phrase.strip() and ids
          for _, phrase, ids in rows), True)
check("every category index names a category",
      all(0 <= index < len(categories) for index, _, _ in rows), True)

# ---- the pictures -----------------------------------------------------------
#
# Both directions, and both sizes. A clip with no picture is a hole in a card; a
# picture no clip names is a file that will be here forever because nothing ever
# looks at it.
#
# The full-size stills are checked as hard as the card pictures because they are
# the half that is easy to lose: nothing draws them until somebody asks for a
# style as a reference, so a folder that silently failed to vendor would look
# perfectly healthy until the day it was needed.

wanted = {"%s.webp" % clip for clip in set(clips)}
on_disk = {name for name in os.listdir(THUMBS)
           if name != "full"} if os.path.isdir(THUMBS) else set()
stills = {name for name in os.listdir(STILLS)} if os.path.isdir(STILLS) else set()

check("every clip has a card picture", sorted(wanted - on_disk)[:4], [])
check("...and no card picture is an orphan", sorted(on_disk - wanted)[:4], [])
check("every clip has a full-size still", sorted(wanted - stills)[:4], [])
check("...and no still is an orphan", sorted(stills - wanted)[:4], [])
check("the pictures are webp and not empty",
      all(os.path.getsize(os.path.join(THUMBS, name)) > 256 for name in sorted(on_disk)[:50]),
      True)
# A still that came out thumbnail-sized is a still that was copied from the card
# picture rather than cut from the clip — which is the one way this could go
# wrong and still pass every check above it.
check("the stills are bigger than the card pictures",
      all(os.path.getsize(os.path.join(STILLS, name))
          > os.path.getsize(os.path.join(THUMBS, name)) for name in sorted(stills)[:50]),
      True)

# ---- how a cast look addresses its frame ------------------------------------
#
# Every other picture in this pack is named by a path under ComfyUI/input. A
# look's frame is the one that is already on disk before anybody asks for it, so
# casting one cites it where it sits — `atlas:000123` — rather than copying the
# file into input/ to give it an address of the expected kind. That copy is what
# this replaced: one per look ever cast, kept forever, in the picker and in every
# core LoadImage combo on the canvas.
#
# Two resolvers know the address, one per side of the wire and in different
# languages. Nothing but this check stands between them drifting apart and a cast
# look that draws a broken thumbnail, or resolves to nothing at execute time.

REF = os.path.join(PRESETS, "atlasref.js")
with open(REF, encoding="utf-8") as handle:
    ref_source = handle.read()
with open(layout.py("media"), encoding="utf-8") as handle:
    media_source = handle.read()

js_scheme = re.search(r'export const ATLAS_SCHEME = "([^"]*)"', ref_source)
py_scheme = re.search(r'^ATLAS_SCHEME = "([^"]*)"', media_source, re.M)
check("the frontend names the scheme", bool(js_scheme), True)
check("...and so does media.resolve",
      py_scheme.group(1) if py_scheme else None,
      js_scheme.group(1) if js_scheme else None)

# Where each side then looks for the file. The browser's is a URL relative to
# `presets/`; the node's is a join off the repo root. Both have to land on the
# folder the stills are actually in, which is the one checked above.
js_dir = re.search(r"new URL\(`\./([\w/]+)/\$\{clip\}\.webp`", ref_source)
py_dir = re.search(r"^ATLAS_DIR = os\.path\.join\((.*?)\)$", media_source, re.M | re.S)
check("the frontend serves the frame out of the stills folder",
      os.path.join(PRESETS, *js_dir.group(1).split("/")) if js_dir else None, STILLS)
check("...and the node reads it from the same one",
      os.path.join(ROOT, *re.findall(r'"([^"]+)"', py_dir.group(1))) if py_dir else None,
      STILLS)

if shutil.which("node") is None:
    skip("node is not installed")

# ---- what a style does ------------------------------------------------------

STUBS = {
    "app.js": "export const app = { registerExtension() {}, extensionManager: null };",
    "api.js": """
export const api = {
  apiURL: (u) => u,
  async fetchApi() { return { ok: true, status: 200, json: async () => ({}) }; },
  async getUserData() { return { status: 404, json: async () => null }; },
  async storeUserData() { return { status: 200 }; },
  async deleteUserData() { return { status: 204 }; },
};
""",
    "widgets.js": "export const ComfyWidgets = {};",
}

CHECK = r"""
const S = await import("./web/creator/state.js");
const P = await import("./web/creator/presets.js");
const { styleRows, ATLAS } = await import("./web/creator/presets/stylelib.js");

const out = { errors: [] };
const rows = styleRows();

// ---- the rows ---------------------------------------------------------------

try {
  const first = rows[0];
  out.rows = {
    count: rows.length,
    stamped: ATLAS.styles,
    allStyleScope: rows.every((row) => row.scope === "style"),
    // A style row is an ordinary builtin with one section — which is why the
    // library needed no new card machinery to draw one.
    oneSection: rows.every((row) => row.sections.length === 1 && row.sections[0] === "style"),
    allBuiltin: rows.every((row) => row.builtin === true && row.cover === null),
    idsUnique: new Set(rows.map((row) => row.id)).size === rows.length,
    // One still per clip, and the shelf the card lands on is the atlas's own
    // media group — `folders()` picks it up with no code of its own.
    thumbsPerClip: rows.every((row) => row.thumbs.length === row.data.style.clips.length),
    shelved: rows.every((row) => !!row.folder),
    described: rows.every((row) => row.facts && row.facts.clips > 0),
    // The card sets the opening clauses and the rest apart, and between them
    // they are the descriptor — neither half invented, neither half printed
    // twice.
    splitIsWhole: rows.every((row) =>
      (row.rest ? row.name + ", " + row.rest : row.name) === row.data.style.text),
    // What `loadBody` hands the inspector, without touching userdata.
    bodyInline: (await P.loadBody(first)) === first.data,
  };
} catch (error) {
  out.errors.push(`rows: ${error.stack}`);
}

// ---- the swap ---------------------------------------------------------------

try {
  const a = rows[0].data.style.text;
  const b = rows[1].data.style.text;
  const shortest = rows.map((row) => row.data.style.text)
    .reduce((best, text) => (text.length < best.length ? text : best));
  out.lead = {
    // Nothing written yet: the descriptor is the prompt.
    fromEmpty: P.leadWithStyle("", a) === a,
    // Written: the descriptor leads and the sentence follows, which is the
    // shape H3's own captions have.
    leads: P.leadWithStyle("A dog runs.", a) === `${a}, a dog runs.`,
    // The whole point. A second style replaces the first rather than stacking
    // on it — six looks tried on one shot is six prompts, not six paragraphs.
    swaps: P.leadWithStyle(P.leadWithStyle("A dog runs.", a), b)
        === P.leadWithStyle("A dog runs.", b),
    noStack: !P.leadWithStyle(P.leadWithStyle("A dog runs.", a), b).includes(a),
    // An article is safe to lower-case behind a comma; somebody's character is
    // not, and mangling a name is worse than a capital letter mid-sentence.
    lowersArticle: P.leadWithStyle("The dog runs", a) === `${a}, the dog runs`,
    keepsName: P.leadWithStyle("Marcus waits at the gate", a)
        === `${a}, Marcus waits at the gate`,
    // A descriptor only matches on a clause boundary: "Claymation" must not eat
    // the front of a word that merely starts the same way.
    boundary: P.leadWithStyle(`${shortest}ist puppets`, b).endsWith(`${shortest}ist puppets`),
  };
} catch (error) {
  out.errors.push(`lead: ${error.stack}`);
}

// ---- applying ----------------------------------------------------------------

try {
  const style = rows[0].data;
  const phrase = style.style.text;

  const timeline = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "A dog runs.", aspect: "1:1", short_edge: 720,
    segments: [{ prompt: "the card's own line", assets: [], loras: [], duration_s: 6 }],
  }));
  S.syncTimeline(timeline);
  const before = JSON.parse(S.serializeTimeline(timeline));
  P.applyToPiece(style, ["style"], timeline, { value: (n, f) => f, set: () => {} },
                 { from: "style" });
  const after = JSON.parse(S.serializeTimeline(timeline));

  const segment = { prompt: "A dog runs.", assets: [], loras: [], duration_s: 6 };
  P.applyToShot(style, ["style"], segment, { value: (n, f) => f, set: () => {} },
                { from: "style" });

  const still = S.parsePreStage(JSON.stringify({ version: 1, prompt: "A dog runs." }));
  P.applyToPreStage(style, ["style"], still, { value: (n, f) => f, set: () => {} },
                    { from: "style" });

  out.apply = {
    piece: after.prompt === `${phrase}, a dog runs.`,
    shot: segment.prompt === `${phrase}, a dog runs.`,
    prestage: still.prompt === `${phrase}, a dog runs.`,
    // A style touches the prompt and nothing else — not the canvas, not the
    // strip, not a card that was already written.
    nothingElseMoved: JSON.stringify({ ...after, prompt: before.prompt })
                   === JSON.stringify(before),
  };
} catch (error) {
  out.errors.push(`apply: ${error.stack}`);
}

// ---- where it can land --------------------------------------------------------

try {
  const reach = {};
  for (const scope of ["piece", "shot", "prestage"]) {
    reach[scope] = P.crossable("style", "style", scope, {}).ok;
  }
  out.crossable = reach;
  // And the reverse is not a thing: no node captures a style, so no target
  // scope offers it as a shelf of your own work.
  out.styleIsSourceOnly = JSON.stringify(P.SCOPE_SECTIONS.style) === '["style"]';
  out.styleIsATab = P.SCOPES.includes("style");
} catch (error) {
  out.errors.push(`crossable: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-atlas-")
try:
    pack = os.path.join(work, "pack")
    # The stills are half a thousand files this half of the suite never opens —
    # the Python half above is what checks them, off the real tree.
    shutil.copytree(os.path.join(ROOT, "web"), os.path.join(pack, "web"),
                    ignore=shutil.ignore_patterns("atlas"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, stub in STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(stub)
    with open(os.path.join(pack, "check.mjs"), "w", encoding="utf-8") as handle:
        handle.write(CHECK)
    result = subprocess.run(["node", os.path.join(pack, "check.mjs")],
                            capture_output=True, text=True, cwd=pack)
finally:
    shutil.rmtree(work, ignore_errors=True)

if result.returncode != 0:
    print("the style library did not load:\n"
          + (result.stderr.strip() or result.stdout.strip()))
    sys.exit(1)

report = json.loads(result.stdout.strip().splitlines()[-1])
FAILURES.extend(report["errors"])

built = report.get("rows", {})
check("every style in the index becomes a row", built.get("count"), len(rows))
check("...and the header counted them right", built.get("stamped"), len(rows))
for label, key in [
    ("a style row is scoped to the style tab", "allStyleScope"),
    ("...holds exactly the style section", "oneSection"),
    ("...ships read-only, with no cover", "allBuiltin"),
    ("...has an id of its own", "idsUnique"),
    ("...carries a still per clip", "thumbsPerClip"),
    ("...lands on its media group's shelf", "shelved"),
    ("...and describes itself for the card", "described"),
    ("the card's two halves are the descriptor, whole", "splitIsWhole"),
    ("the body needs no userdata read", "bodyInline"),
]:
    check(label, built.get(key), True)

lead = report.get("lead", {})
for label, key in [
    ("a style on an empty prompt is the prompt", "fromEmpty"),
    ("a style leads what is already written", "leads"),
    ("a second style swaps the first out", "swaps"),
    ("...rather than stacking on it", "noStack"),
    ("an article behind the comma is lower-cased", "lowersArticle"),
    ("...but somebody's character is left alone", "keepsName"),
    ("a descriptor only matches on a clause boundary", "boundary"),
]:
    check(label, lead.get(key), True)

applied = report.get("apply", {})
for label, key in [("a piece takes a style", "piece"), ("a card takes a style", "shot"),
                   ("a pre-stage takes a style", "prestage"),
                   ("and a style moves nothing but the prompt", "nothingElseMoved")]:
    check(label, applied.get(key), True)

check("a style reaches all three nodes", report.get("crossable"),
      {"piece": True, "shot": True, "prestage": True})
check("...and nothing captures one", report.get("styleIsSourceOnly"), True)
check("the catalogue has a tab", report.get("styleIsATab"), True)
