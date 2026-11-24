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

// A stretch given a pace: its ends go at the pace, its stops stay, it never
// runs backwards, and a bent path has no say in the speed.
const S = await import("./web/creator/state.js");
const bent = [{ ...at(0, 0), out: 0 }, { ...at(2, 2, 3), in: 2 }, at(4, 4, 0)];
const fast = (marks, t) => { const a = cameraAt(marks, t - 5e-3), b = cameraAt(marks, t + 5e-3);
  return Math.hypot(b.x - a.x, b.z - a.z) / 1e-2; };
const flat = [{ ...at(0, 0), out: 1 }, { ...at(2, 2, 3), in: 1 }, at(4, 4, 0)];
const run = Array.from({ length: 9 }, (_, k) => fast(flat, 0.2 + k * 0.2));
out.flat = Math.max(...run) / Math.min(...run) < 1.04;
out.gentle = fast(bent, 0.02) < 0.1;
out.stops = [0, 2, 4].map((t) => [r(cameraAt(bent, t).x), r(cameraAt(bent, t).z)]);
const hard = [{ ...at(0, 0), out: 3 }, { ...at(2, 4), in: 3 }];
let least = 1;
for (let t = 0.01; t < 2; t += 0.01) least = Math.min(least, cameraAt(hard, t + 0.01).z - cameraAt(hard, t).z);
out.forward = least > -1e-6;
const sudden = [{ ...at(0, 0), out: 1 }, { ...at(2, 2), in: 1 }, at(4, 2)];
out.sudden = [1, 1.95, 3].map((t) => Math.round(speed(sudden, t) * 10) / 10);
out.panned = r(cameraAt([{ ...at(0, 0), out: 0 }, { ...at(2, 0), yaw: 1, in: 0 }], 0.5).yaw);
out.person = r(poseAt([{ ...pm(0, 0, 0), out: 0 }, { ...pm(2, 0, 2), in: 0 }], 0.5).z);
const kept = S.serializeStaging({ camera: bent, people: { 1: [{ ...pm(0, 0, 0), out: 0 }, { ...pm(1, 1, 1), in: 9 }] } });
out.kept = [kept.camera.map((m) => [m.in ?? null, m.out ?? null]), kept.people[1].map((m) => [m.in ?? null, m.out ?? null])];
out.reads = Object.keys(cameraAt(bent, 0)).includes("out");

// Bent by hand: stops stay, the pace is even, a corner is straight, and whoever
// faced the way they went faces along the curve.
const B = await import("./web/creator/blockout.js");
const turnedWalk = [{ ...pm(0, 0, 0), bend: { x: 2, y: 0, z: 0 } }, { ...pm(4, 0, 6), bend: { x: -2, y: 0, z: 0 } }];
B.faceArrival(turnedWalk, 1, { kind: "person" });
const gait = Array.from({ length: 9 }, (_, k) => { const t = 0.4 + k * 0.4;
  const a = poseAt(turnedWalk, t - 0.02), b = poseAt(turnedWalk, t + 0.02); return Math.hypot(b.x - a.x, b.z - a.z); });
out.bentStops = [0, 4].map((t) => [r(poseAt(turnedWalk, t).x), r(poseAt(turnedWalk, t).z)]);
out.bentEven = Math.max(...gait) / Math.min(...gait) < 1.05;
const a0 = poseAt(turnedWalk, 1.4), b0 = poseAt(turnedWalk, 1.6);
out.bentFaces = Math.abs(poseAt(turnedWalk, 1.5).ry - Math.atan2(b0.x - a0.x, b0.z - a0.z)) < 0.05;
let jump = 0;
for (let t = 0.02; t < 4; t += 0.02) jump = Math.max(jump, Math.abs(poseAt(turnedWalk, t).ry - poseAt(turnedWalk, t - 0.02).ry));
out.bentJump = jump < 0.15;
const corner = [at(0, 0), { ...at(2, 2), corner: true }, at(4, 2, 2)];
out.corner = [r(cameraAt(corner, 1.5).x), r(cameraAt(corner, 2.5).z)];
const set = { id: "s", objects: [{ ...anna }, { id: 2, kind: "block", x: 0, y: 0, z: 5, w: 4, h: 1.4, d: 1.8, plays: "", word: "car" }] };
const drive = { camera: [at(0, -3)], people: { 2: [pm(0, -4, 5), pm(4, 4, 5)] }, look: 2 };
out.car = [r(B.stagedAt(set, drive, 2)[1].x), r(B.facingOf(set.objects[1], 1, 0, 0))];
out.look = [0, 2, 4].map((t) => r(B.lensAt(set, drive, t).yaw));
out.lookWords = B.stagedSentence(set, drive, 4, { w: 16, h: 9 });
out.lookPlain = moveSentence(B.aimedMarks(set, drive, 4), 4, null, { plain: true, keeping: B.lookName(set, drive) });
const shaped = S.serializeStaging({ camera: corner, people: { 1: turnedWalk }, look: 2 });
out.shaped = [shaped.camera[1].corner, shaped.people[1][0].bend, shaped.look];

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

check("a steady pace is steady round a bend", said["flat"], True)
check("a gentle start is from standing still", said["gentle"], True)
check("the stops stay where and when they were", said["stops"], [[0, 0], [3, 2], [0, 4]])
check("no pace runs backwards", said["forward"], True)
check("a steady stretch before a wait stops suddenly", said["sudden"], [1, 1, 0])
check("a camera that only turns has a pace too", said["panned"], 0.16)
check("so does a person", said["person"], 0.31)
check("the pace is kept on the mark, and clamped", said["kept"],
      [[[None, 0], [2, None], [None, None]], [[None, 0], [3, None]]])
check("a moment read off the path carries no pace", said["reads"], False)

check("a bent path keeps its stops", said["bentStops"], [[0, 0], [0, 6]])
check("...and an even pace", said["bentEven"], True)
check("...and is faced along, without a jump", [said["bentFaces"], said["bentJump"]], [True, True])
check("a corner is straight in and straight out", said["corner"], [0, 2])
check("a thing moves, lengthways", said["car"], [0, 0])
check("the camera keeps on it", said["look"], [-0.46, 0, 0.46])
check("...and says so", said["lookWords"],
      "@anna stands at frame right in the midground; a car starts at centre in the midground and moves to the right. "
      "The camera pans right with large amplitude, keeping the car in frame.")
check("...in everyday words on the bench", said["lookPlain"],
      "The camera turns right, always looking at the car.")
check("the shape is kept", said["shaped"], [True, {"x": 2, "y": 0, "z": 0}, 2])

passed("the blockout says who is where, and the move in the model's own words")
