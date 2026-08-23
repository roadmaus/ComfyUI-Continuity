"""A cast's pictures follow it when one shot becomes a strip.

A piece of one shot keeps its cast's files on that shot's own row, and it has to:
the pool is what tells the node it is no longer a lone shot, so putting a
member's first photograph in one would answer "hang this picture on Anna" by
folding the node's face into the strip summary.

The cast itself is the piece's either way, and that is where the two used to
part company. Growing a second card left every one of Anna's files somewhere
only card 1 could see: the shelf in the Timeline window drew her with no
pictures behind her, and citing her on card 2 was refused at queue time over
files sitting right there on card 1.

So the sync promotes them, and what this suite pins is the whole of that move —
that it takes the right files and leaves the rest, that the prose which named
them still names them afterwards, that it repairs a piece grown before the
repair existed, and that running it twice changes nothing.

    python3 tests/test_cast_promote.py

Skips itself if node is not installed.
"""

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "js", "minimax_creator", "state.js")

from harness import FAILURES, check, passed, skip  # noqa: E402

if shutil.which("node") is None:
    skip("node is not installed")

SCRIPT = r"""
const s = await import(process.argv[1]);

const image = (handle, filename) => ({ handle, kind: "image", role: "reference",
                                       filename, ref_size: "max" });
const clip = (handle, filename) => ({ handle, kind: "video", role: "reference",
                                      filename, ref_size: "max", track: "picture" });

// The piece as the node face builds it: one shot, Anna's files on its own row,
// and a start frame that is nobody's reference.
function lonePiece() {
  const piece = s.emptyTimeline();
  const shot = piece.segments[0];
  shot.prompt = "@anna walks past @img-10, and @img-1 is where her face comes from";
  shot.assets.push(image("img-1", "anna.png"), image("img-10", "wall.png"),
                   clip("vid-1", "walk.mp4"),
                   { ...image("img-2", "opening.png"), role: "first_frame" });
  piece.subjects.push({ handle: "anna", takes: "person", from: ["img-1"],
                        motion: "vid-1" });
  piece.aspect_source = { handle: "img-1", card: 1 };
  s.syncTimeline(piece);
  return piece;
}

// What the shelf in the Timeline window asks about a member, at the scope it
// asks it at — the pool and a lone shot's row together.
const problem = (piece) => s.subjectProblem(
  { subjects: piece.subjects, assets: s.castAssets(piece) }, piece.subjects[0]);

const one = lonePiece();
const beforeGrow = {
  problem: problem(one),
  // Nothing moved while it is still one shot: the pool is what the face reads
  // to decide it is not a lone shot any more.
  pool: one.assets.map((a) => a.handle),
  row: one.segments[0].assets.map((a) => a.handle),
};

const grown = lonePiece();
grown.segments.push(s.continuingSegment());
grown.segments[1].prompt = "@anna sits down";
s.syncTimeline(grown);
const card2 = grown.segments[1];
const afterGrow = {
  problem: problem(grown),
  pool: grown.assets.map((a) => `${a.handle}:${a.filename}`),
  row: grown.segments[0].assets.map((a) => `${a.handle}:${a.filename}`),
  prompt: grown.segments[0].prompt,
  subject: grown.subjects[0],
  aspect: grown.aspect_source,
  // The whole point: card 2 writes her name and the files ride in.
  cited: s.citedPool(card2).map((a) => a.handle),
  references: s.hasReferences(card2),
};

// Twice changes nothing — every commit and every load runs this.
s.syncTimeline(grown);
const twice = {
  pool: grown.assets.map((a) => a.handle),
  subject: grown.subjects[0],
};

// The strip grown the other way: by duplicating the only card there was.
// `Timeline.duplicate` copies a card whole, so the clone arrives holding its own
// deep copy of every file on it — the cast's included, under the handle the
// original wore, and it is the original the promotion moves. The copy is a
// second Anna nobody cast, sitting on card 2 where the shelf cannot see it.
const duplicated = lonePiece();
const copy = s.cloneSegment(duplicated.segments[0]);
duplicated.segments.splice(1, 0, copy);
s.syncTimeline(duplicated);
const afterDuplicate = {
  problem: problem(duplicated),
  pool: duplicated.assets.map((a) => `${a.handle}:${a.filename}`),
  // What the clone kept: the wall it walks past and the frame it opens on are
  // the card's own business, and duplicating a card copies them on purpose.
  clone: duplicated.segments[1].assets.map((a) => `${a.handle}:${a.filename}`),
  prompt: duplicated.segments[1].prompt,
  cited: s.citedPool(duplicated.segments[1]).map((a) => a.handle),
};

// Who each pool entry belongs to, once the strip has grown. This is the
// question the piece's shelf asks to tell a reference somebody attached from a
// member's own picture that was moved here — drawn as the same kind of thing,
// the promoted ones read as duplicates of the cast shelf above them.
const shelved = lonePiece();
shelved.segments.splice(1, 0, s.cloneSegment(shelved.segments[0]));
shelved.assets.push(image("ref-9", "backdrop.png"));
s.syncTimeline(shelved);
const owned = shelved.assets.map((a) => ({
  handle: a.handle,
  owners: s.assetOwners(shelved, a).map((subject) => subject.handle),
}));

// A piece saved in the broken shape, repaired on the way in.
const loaded = s.parseTimeline(JSON.stringify({
  version: 2, render: "chained", prompt: "", aspect: "16:9", short_edge: 720,
  subjects: [{ handle: "anna", takes: "person", from: ["img-1"] }],
  segments: [
    { prompt: "@anna walks in", duration_s: 6, loras: [],
      assets: [image("img-1", "anna.png")] },
    { prompt: "@anna sits", duration_s: 6, loras: [], continue: true },
  ],
}));
const repaired = {
  problem: problem(loaded),
  pool: loaded.assets.map((a) => `${a.handle}:${a.filename}`),
  row: loaded.segments[0].assets.map((a) => a.handle),
  // Narrowed on the same load that moved it, rather than on the one after.
  takes: loaded.assets[0].takes,
};

console.log(JSON.stringify({ beforeGrow, afterGrow, twice, afterDuplicate, owned, repaired }));
"""

proc = subprocess.run(["node", "--input-type=module", "-e", SCRIPT, "--", STATE],
                      capture_output=True, text=True)
if proc.returncode != 0:
    print(f"node failed:\n{proc.stderr}")
    sys.exit(1)
got = json.loads(proc.stdout)

before = got["beforeGrow"]
check("a lone shot's cast is whole where it stands", before["problem"], "")
check("...and nothing has been moved into the pool", before["pool"], [])
check("...the shot keeps every file it was given",
      before["row"], ["img-1", "img-10", "vid-1", "img-2"])

after = got["afterGrow"]
check("a grown piece's cast is whole too", after["problem"], "")
check("her looks and her movement are the piece's now",
      after["pool"], ["ref-1:anna.png", "ref-2:walk.mp4"])
check("...and only they are: a wall she walks past is card 1's, and a start "
      "frame is a moment of card 1's video",
      after["row"], ["img-10:wall.png", "img-2:opening.png"])
check("she is built out of what she is built out of",
      after["subject"], {"handle": "anna", "takes": "person",
                         "from": ["ref-1"], "motion": "ref-2"})
check("the prose that named them names them still — and leaves @img-10 alone",
      after["prompt"],
      "@anna walks past @img-10, and @ref-1 is where her face comes from")
check("the canvas source follows the file it names into the pool",
      after["aspect"], {"handle": "ref-1"})
check("card 2 writing her name is what carries them into it",
      after["cited"], ["ref-1", "ref-2"])
check("...which makes it a reference generation", after["references"], True)

twice = got["twice"]
check("syncing again moves nothing", twice["pool"], ["ref-1", "ref-2"])
check("...and renames nothing", twice["subject"], after["subject"])

dup = got["afterDuplicate"]
check("duplicating the only card leaves the cast whole", dup["problem"], "")
check("...her files are the piece's, once",
      dup["pool"], ["ref-1:anna.png", "ref-2:walk.mp4"])
check("...the copy the clone was handed follows them off it",
      dup["clone"], ["img-10:wall.png", "img-2:opening.png"])
check("...and the clone's prose follows them too",
      dup["prompt"],
      "@anna walks past @img-10, and @ref-1 is where her face comes from")
check("...which is what carries them into the clone", dup["cited"], ["ref-1", "ref-2"])

check("a promoted file is still the member's, and says whose it is",
      got["owned"],
      [{"handle": "ref-9", "owners": []},
       {"handle": "ref-1", "owners": ["anna"]},
       {"handle": "ref-2", "owners": ["anna"]}])

repaired = got["repaired"]
check("a piece grown before this existed is repaired on the way in",
      repaired["problem"], "")
check("...its cast's file is the piece's", repaired["pool"], ["ref-1:anna.png"])
check("...and card 1 no longer holds it alone", repaired["row"], [])
check("...narrowed to what her slot means, on the same load",
      repaired["takes"], "person")

passed("a cast's pictures follow it out of the lone shot and onto the piece")
