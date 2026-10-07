"""A shot says what it is made of, whether the file is its own or the piece's (#91).

Two separate failures wore one face here, and both of them needed a strip of
more than one card to appear at all.

The first is the row. A piece of one shot keeps the cast's pictures on that
shot; growing a second card moves them into the pool (`promoteCastFiles`),
because card 2 cannot see card 1's row. The editor's reference row read
`state.assets` and nothing else, so from the moment the strip grew it had
nothing left to draw: casting somebody emptied the one place that answers "what
is this shot made of", on every card at once, with no error anywhere near it.
The reference was still bound the whole time — which is what made it look like
a dead div rather than a lost file.

The row has since stopped drawing a member's files at all: they are on the
cast shelf, under the member, and the row is the files you attached. So the
answer to "what is this shot made of" is the row and the shelf together, and
this suite reads both — what #91 lost must not be lost from either.

The second is not cosmetic. `motion` became a *list* of clips, and the two
places that rename a member's handles as their files move carried on reading it
as a single handle — so the clip went into the pool under `ref-N` and the
member went on naming the `vid-N` that nothing holds. Their action rode into no
shot at all. `inheritTakes` read the same slot the same way and stopped
narrowing an action clip for the same reason.

    python3 tests/test_issue91.py

Skips itself if node is not installed.
"""

import layout
from domshim import DOM
from harness import check, passed

layout.skip_without_node()
passed("a card draws the piece's references, and a member's action follows its file")

CHECK = r"""
await import("./dom.mjs");
const S = await import("./web/creator/state.js");
const { CreatorEditor } = await import("./web/creator/editor.js");

const out = {};

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

const image = (handle, filename) => ({ handle, kind: "image", role: "reference",
                                       filename, ref_size: "max" });

/** Anna, her photograph, and whatever else the case needs on card 1. */
const piece = (cards, subject = {}) => S.parseTimeline(JSON.stringify({
  version: 2, prompt: "", aspect: "16:9", short_edge: 720,
  subjects: [{ handle: "anna", takes: "person", from: ["img-1"], ...subject }],
  segments: cards,
}));

const card1 = (extra = []) => ({
  prompt: "@anna walks in", duration_s: 5, loras: [],
  assets: [image("img-1", "anna.png"), ...extra],
});

/** The card editor as the Timeline window mounts one. */
const row = (timeline, index) => {
  const editor = new CreatorEditor({
    state: timeline.segments[index], piece: timeline, castPiece: timeline,
    nodeId: () => 1,
  });
  editor.pieceRef = timeline;
  editor.toggleCast();
  const host = editor.assetsHost;
  return {
    // The chip's title is its filename, which is the one thing that says which
    // picture is being drawn rather than which handle it wears today.
    files: all(host, "mmc-asset").map((chip) => chip.attrs?.title ?? ""),
    // What the card may do to what it drew. A pool entry carries neither: both
    // would reach every other card. The mute wears `mmc-asset-x` too — it is
    // the other glyph in that corner — so the ✕ is the ones that are not it.
    removes: all(host, "mmc-asset-x").filter(
      (b) => !String(b.className).split(" ").includes("mmc-asset-mute")).length,
    mutes: all(host, "mmc-asset-mute").length,
    pooled: all(host, "mmc-asset-pooled").length,
    // The door onto a reference's own card, which a pool entry does not open.
    doors: all(host, "mmc-asset-door").length,
    // Her files, which the shelf holds rather than the row.
    shelf: all(editor.castHost, "mmc-cast-ref").map((tile) => tile.dataset.handle),
  };
};

// ---- the row ----------------------------------------------------------------

// One shot: her picture is on the card, and the card owns it outright.
out.lone = row(piece([card1()]), 0);

// Grown. Her picture is the piece's now, and both cards write her name.
const grown = piece([card1()]);
grown.segments.push(S.continuingSegment(grown));
grown.segments[1].prompt = "@anna sits down";
S.syncTimeline(grown);
out.grown1 = row(grown, 0);
out.grown2 = row(grown, 1);
out.grownPool = grown.assets.map((a) => `${a.handle}:${a.filename}`);

// A card that says nothing about her draws nothing of hers — the row is about
// this shot, not about the piece's shelf.
const quiet = piece([card1()]);
quiet.segments.push(S.continuingSegment(quiet));
quiet.segments[1].prompt = "an empty room";
S.syncTimeline(quiet);
out.quiet = row(quiet, 1);

// The card's own files and the piece's, in one row: the card's lead, and only
// the card's carry the two buttons.
const both = piece([card1()]);
both.segments.push(S.continuingSegment(both));
both.segments[1].prompt = "@anna sits by @img-1";
both.segments[1].assets = [image("img-1", "chair.png")];
S.syncTimeline(both);
out.both = row(both, 1);

// A piece file nobody is built out of, cited by its own handle: the row still
// draws it as the piece's, since no shelf holds it.
const loose = piece([card1()]);
loose.segments.push(S.continuingSegment(loose));
S.syncTimeline(loose);
loose.assets.push(image("ref-5", "lamp.png"));
loose.segments[1].prompt = "@anna by @ref-5";
S.syncTimeline(loose);
out.loose = row(loose, 1);

// The shelf's own readout of her picture, when a card cites the *file* and
// not her. "in shots 1, 2" was read off the shots that write her name alone,
// so a third card saying `@ref-1` was in the compile and off the shelf.
{
  const { openTimeline } = await import("./web/creator/timeline.js");
  const timeline = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", aspect: "16:9", short_edge: 720,
    assets: [image("ref-1", "anna.png")],
    subjects: [{ handle: "anna", takes: "person", from: ["ref-1"] }],
    segments: [{ prompt: "@anna walks in", duration_s: 5 },
               { prompt: "an empty room", duration_s: 5 },
               { prompt: "@ref-1 on the wall", duration_s: 5 }] }));
  openTimeline({ timeline, onCommit: () => {} });
  await new Promise((done) => setTimeout(done, 0));
  const modal = document.body.children.at(-1);
  out.shelf = all(modal, "mmc-tl-pool-where").map((n) => n.text ?? n.textContent ?? "");
}

// ---- the member's action ----------------------------------------------------

const withMotion = () => {
  const p = piece([card1([{ handle: "vid-1", kind: "video", role: "reference",
                            filename: "walk.mp4", ref_size: "max", track: "picture" }])],
                  { motion: ["vid-1"], triggers: { "vid-1": "walk" } });
  p.segments.push(S.continuingSegment(p));
  p.segments[1].prompt = "@anna sits down";
  S.syncTimeline(p);
  return p;
};

const moved = withMotion();
out.motion = {
  // The clip moved with the rest of her files...
  pool: moved.assets.map((a) => `${a.handle}:${a.filename}`),
  // ...and she followed it, which is the whole of the second bug.
  says: S.motionOf(moved.subjects[0]),
  files: S.subjectFiles(moved.subjects[0]),
  // ...and so does the word that wakes it. Triggers are keyed by handle like
  // notes, and were the one key the rename walked past (#92).
  triggers: S.subjectTriggers(moved.subjects[0]),
  // So it rides into the shots that name her, on both cards.
  cited1: S.citedPool(moved.segments[0]).map((a) => a.filename),
  cited2: S.citedPool(moved.segments[1]).map((a) => a.filename),
};

// ...and home again when the strip goes back to one card.
const home = withMotion();
home.segments.pop();
S.syncTimeline(home);
out.collapsed = {
  row: home.segments[0].assets.map((a) => `${a.handle}:${a.filename}`),
  says: S.motionOf(home.subjects[0]),
  triggers: S.subjectTriggers(home.subjects[0]),
  pool: home.assets.map((a) => a.handle),
};

// Twice changes nothing: every commit and every load runs the sync.
S.syncTimeline(moved);
out.twice = { says: S.motionOf(moved.subjects[0]),
              pool: moved.assets.map((a) => a.handle) };

// The third reader of the same slot: a clip dropped in the action slot is
// narrowed to "motion" the way every other slot narrows its file.
{
  const clip = { handle: "vid-1", kind: "video", role: "reference",
                 filename: "walk.mp4", ref_size: "max", track: "picture" };
  const anna = { handle: "anna", takes: "person", from: [], motion: ["vid-1"] };
  S.inheritTakes(anna, [clip]);
  out.inherit = S.takes(clip);
}

console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    got = layout.in_pack(CHECK.replace('await import("./dom.mjs");', DOM), target)

# ---- the row ----------------------------------------------------------------

lone = got["lone"]
check("one shot: her picture is on the shelf, under her", lone["shelf"], ["img-1"])
check("...and not on the row, which is the files you attached", lone["files"], [])

check("the strip keeps her picture on the piece", got["grownPool"], ["ref-1:anna.png"])
for name in ("grown1", "grown2"):
    card = got[name]
    check(f"{name}: the card still shows her picture — on the shelf, under her (#91)",
          card["shelf"], ["ref-1"])
    check(f"{name}: and not on the row", card["files"], [])

loose = got["loose"]
check("a piece file nobody is built out of is drawn on the card that cites it",
      loose["files"], ["lamp.png"])
check("...marked as the piece's", loose["pooled"], 1)
check("...carrying neither button, which would reach every other card",
      {"remove": loose["removes"], "mute": loose["mutes"]}, {"remove": 0, "mute": 0})
check("...and no door onto a card-shaped edit of a piece-wide file", loose["doors"], 0)

check("a card that never names her draws nothing of hers", got["quiet"]["files"], [])
check("the shelf counts a card that cites the file and not her (#91)",
      got["shelf"], ["in shots 1, 3"])

both = got["both"]
check("the card's own file is on the row, hers on the shelf",
      {"row": both["files"], "shelf": both["shelf"]}, {"row": ["chair.png"], "shelf": ["ref-1"]})
check("...and the card's own carries the two buttons",
      {"remove": both["removes"], "mute": both["mutes"], "pooled": both["pooled"]},
      {"remove": 1, "mute": 1, "pooled": 0})

# ---- the member's action ----------------------------------------------------

motion = got["motion"]
check("her action clip moves into the pool with the rest of her files",
      motion["pool"], ["ref-1:anna.png", "ref-2:walk.mp4"])
check("and she follows it to its new handle", motion["says"], ["ref-2"])
check("so nothing of hers dangles", motion["files"], ["ref-1", "ref-2"])
check("and the word that wakes the clip follows it too (#92)",
      motion["triggers"], {"ref-2": "walk"})
check("it rides into card 1, which says its word", motion["cited1"], ["anna.png", "walk.mp4"])
check("...and holds back from card 2, which does not", motion["cited2"], ["anna.png"])

collapsed = got["collapsed"]
check("back at one card the files come home, under a card's own scheme",
      collapsed["row"], ["img-1:anna.png", "vid-1:walk.mp4"])
check("...and she follows them home too", collapsed["says"], ["vid-1"])
check("...with the word still on the clip", collapsed["triggers"], {"vid-1": "walk"})
check("leaving no pool behind", collapsed["pool"], [])

check("running the sync twice changes nothing",
      got["twice"], {"says": ["ref-2"], "pool": ["ref-1", "ref-2"]})

check("a clip in the action slot is narrowed to motion", got["inherit"], "motion")
