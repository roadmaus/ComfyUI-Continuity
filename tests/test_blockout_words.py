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
const { moveSentence, stagingSentence } = await import("./web/creator/blockout.js");
const out = {};

out.static = moveSentence([], 4);

// A gentle push-in: 1.4 m over 4 s. Medium amplitude is omitted the way the
// spec omits it; the rate lands in "slow".
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

console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    said = layout.in_pack(SCRIPT, target)

check("a pathless camera holds", said["static"], "The camera holds a static shot.")
check("a gentle push, in the spec's words", said["push"],
      "The camera pushes in at slow speed.")
check("the push aims itself when told at whom", said["pushAt"],
      "The camera pushes in toward @anna at slow speed.")
check("a plain pan carries no amplitude or speed", said["pan"],
      "The camera pans right.")
check("staging: cast first, article on the prop, move aimed", said["staged"],
      "@anna stands at centre in the midground; a table at frame left in the "
      "foreground. The camera pushes in toward @anna at slow speed.")
check("no marks: staging over a static shot", said["propOnly"],
      "A table at frame left in the foreground. The camera holds a static shot.")
check("out of shot is out of the sentence", said["unseen"],
      "The camera pushes in at slow speed.")

passed("the blockout says who is where, and the move in the model's own words")
