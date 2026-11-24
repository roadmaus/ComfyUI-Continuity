"""The blockout's prose: the move, and who stands where.

    python3 tests/test_blockout_words.py

The sentence is the half of the bench's output that binds identity to place —
the search for a pixel channel that could carry "who is where" comes back
empty on every family, and even mask-injection systems bind a reference to its
region through the prompt — so the words are a contract, not decoration. This
pins them: the camera vocabulary is H3's own (§4.3 — motion type, amplitude,
speed, with medium and normal omitted), placement is thirds and depth bands, a
handle is cited as `@anna` exactly as the prompt's substitution reads one, and
the move aims itself at whoever the last mark's frame holds at centre.

Runs the real module under the packed stubs, the way the link suite does.
Skips itself if node is not installed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout
from harness import FAILURES, check, passed

layout.skip_without_node()

SCRIPT = """
const { moveSentence, stagingSentence, cameraAt, poseAt } = await import("./web/creator/blockout.js");
const out = {};

out.static = moveSentence([], 4);

// A gentle push-in: 1.4 m over 4 s. Medium amplitude is omitted the way the
// spec omits it; a third of a metre a second is nothing to call slow.
const push = [
  { x: 0, y: 1.6, z: -0.8, yaw: 0, pitch: 0, mm: 32 },
  { x: 0, y: 1.6, z: 0.6, yaw: 0, pitch: 0, mm: 32 },
];
out.push = moveSentence(push, 4);
out.pushAt = moveSentence(push, 4, "anna");

// A pan: twenty degrees in two seconds — no amplitude or speed worth naming.
const pan = [
  { x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 },
  { x: 0, y: 1.6, z: 0, yaw: 0.35, pitch: 0, mm: 32 },
];
out.pan = moveSentence(pan, 2);

// The staging: a person-block dead ahead, a table near and left. The cast is
// said first, the move aims itself at her, and the table takes an article.
const objects = [
  { id: 1, kind: "block", x: 0, z: 5, w: 0.5, h: 1.8, d: 0.4, rot: 0, plays: "anna", word: "" },
  { id: 2, kind: "block", x: -1.1, z: 1.8, w: 1.2, h: 0.9, d: 0.8, rot: 0, plays: "", word: "table" },
];
out.staged = stagingSentence(objects, push, 4, push[0], { w: 704, h: 396 });

// No marks: the staging still speaks, over a static shot.
out.propOnly = stagingSentence([objects[1]], [], 4, push[0], { w: 704, h: 396 });

// Out of shot is out of the sentence: a piece behind the camera says nothing.
const behind = [{ id: 3, kind: "block", x: 0, z: -6, w: 1, h: 1, d: 1, rot: 0, plays: "ben", word: "" }];
out.unseen = stagingSentence(behind, push, 4, push[0], { w: 704, h: 396 });

// The pace, and what it is called.
const at = (t, z, x = 0) => ({ t, x, y: 1.6, z, yaw: 0, pitch: 0, mm: 32 });
const speed = (marks, t) => Math.round((cameraAt(marks, t + 1e-3).z - cameraAt(marks, t - 1e-3).z) / 2e-3 * 100) / 100;
const uneven = [at(0, 0), at(1, 1), at(5, 5)];
out.steady = [0.01, 0.99, 1.01, 3, 4.99].map((t) => speed(uneven, t));
const hold = [at(0, 0), at(2, 0), at(4, 4)];
out.hold = [0.5, 1, 1.9].map((t) => cameraAt(hold, t).z);
out.back = moveSentence([at(0, 0), at(2.5, 4), at(5, 0)], 5);
out.crawl = moveSentence([at(0, 0), at(5, 0.5)], 5);
out.plain = moveSentence([at(0, 0), at(5, 1, 3)], 5, null, { plain: true });

const pm = (t, x, z, ry = 0) => ({ t, x, y: 0, z, rx: 0, ry, rz: 0 });
const anna = { id: 1, kind: "person", x: -1, y: 0, z: 3, w: 0.5, h: 1.75, d: 0.35, plays: "anna", word: "" };
const say = (marks, cam = at(0, 0)) => stagingSentence([{ ...anna, ...marks[0] }], [cam], 5, cam, { w: 16, h: 9 },
  { withMove: false, ends: [{ ...anna, ...marks[marks.length - 1] }], people: { 1: marks } });
out.walks = say([pm(0, -1, 3), pm(5, 1.5, 5)]);
out.runs = say([pm(0, -1, 3), pm(1, 1.5, 6)]);
out.waits = say([pm(0, -1, 3), pm(4, -1, 3), pm(5, 1.5, 6)]);
out.leaves = say([pm(0, 0, 5), pm(5, 9, 5)]);
out.enters = say([pm(0, 9, 5), pm(5, 0, 5)]);
out.nears = say([pm(0, 0, 8), pm(4, 0, 4)]);
out.stays = say([pm(0, 0, 5), pm(5, 0.1, 5)]);
const r = (v) => Math.round(v * 100) / 100;
const facing = [pm(0, 0, 0, 0), pm(4, 4, 0, Math.PI / 2)];
out.turns = [0, 0.4, 2].map((t) => r(poseAt(facing, t).ry));
out.backwards = r(poseAt([pm(0, 0, 0, 0), pm(4, 0, -4, 0)], 2).ry);

console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    said = layout.in_pack(SCRIPT, target)

check("a pathless camera holds", said["static"], "The camera holds a static shot.")
check("a gentle push, in the spec's words", said["push"],
      "The camera pushes in.")
check("the push aims itself when told at whom", said["pushAt"],
      "The camera pushes in toward @anna.")
check("a plain pan carries no amplitude or speed", said["pan"],
      "The camera pans right.")
check("staging: cast first, article on the prop, move aimed", said["staged"],
      "@anna stands at centre in the midground; a table at frame left in the "
      "foreground. The camera pushes in toward @anna.")
check("no marks: staging over a static shot", said["propOnly"],
      "A table at frame left in the foreground. The camera holds a static shot.")
check("out of shot is out of the sentence", said["unseen"],
      "The camera pushes in.")

check("an evenly paced camera keeps its pace, however its marks are spaced", said["steady"], [1, 1, 1, 1, 1])
check("a hold holds", said["hold"], [0, 0, 0])
check("out and back is two moves", said["back"],
      "The camera pushes in, then pulls out with large amplitude at fast speed.")
check("a crawl is slow", said["crawl"], "The camera pushes in with small amplitude at slow speed.")
check("the bench says it in everyday words", said["plain"], "The camera moves right and moves forward.")
check("somebody walking walks", said["walks"],
      "@anna starts at frame left in the foreground and walks to frame right in the midground.")
check("...or runs", "and runs to frame right" in said["runs"], True)
check("a wait is not part of the pace", "and runs to frame right" in said["waits"], True)
check("out of frame", said["leaves"], "@anna starts at centre in the midground and walks out of frame.")
check("into frame", said["enters"], "@anna walks into frame, to the centre in the midground.")
check("toward the camera", said["nears"], "@anna starts at centre in the midground and walks toward the camera.")
check("a shuffle is standing", said["stays"], "@anna stands at centre in the midground.")
check("a walker turns as they set off", said["turns"], [0, 1.57, 1.57])
check("and can be placed walking backwards", said["backwards"], 0)

passed("the blockout says who is where, and the move in the model's own words")
