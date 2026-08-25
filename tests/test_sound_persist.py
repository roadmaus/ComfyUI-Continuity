"""A track laid on the lane can be dragged, and is still there next time.

    python3 tests/test_sound_persist.py

Two failures, and both of them are the whole feature not working. Neither is
visible from the layer below: `test_sound_mirror` proves the lane's arithmetic
agrees with `sound.py`, and it went on proving it while nothing on the surface
could reach that arithmetic and nothing that did reach it survived a restart.

**The drag died on its first pixel.** Every pointermove committed, a commit
re-renders the lane, and a re-render replaces the very node the pointer was
captured on — a captured element that leaves the document takes the capture with
it. So the block jumped once and then sat there while the pointer went on moving
across a lane that was no longer listening. Nothing throws; the surface is
simply inert, which is exactly the shape of bug a mirror suite cannot see.

The invariant that fixes it is the one asserted here: **between pointerdown and
pointerup the lane is not rebuilt, and the piece is written exactly once.** Not
"the block ends up in the right place" — it does that in a shim either way,
because a shim has no capture to lose. The node still being the same object
after three moves is the part that only holds in a browser if the code is right.

**And the lane was never serialized.** `serializeTimeline` wrote every other
field the piece owns and quietly dropped `sound`, so a piece cut to a track
opened the next morning with nothing on the lane — the state layer had it, the
compiler could read it, and the one function between them threw it away.

Skips itself if node is not installed.
"""

import layout
from domshim import DOM
from harness import check, passed

layout.skip_without_node()

CHECK = """
await import("./dom.mjs");
const S = await import("./web/creator/state.js");
const { SoundLane } = await import("./web/creator/soundlane.js");

const out = {};

/** A 15 s piece — three 5 s shots — with one track laid across its first third.
 *
 *  `lengths` is seeded rather than probed: a file's whole duration is a fact
 *  from the server, the lane asks for it once, and the trim ceiling is the only
 *  thing here that reads it. */
function laid(entries = [{ filename: "score.wav", at_s: 0, in_s: 0, out_s: 5 }]) {
  const piece = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "x",
    segments: [{ prompt: "a", duration_s: 5 }, { prompt: "b", duration_s: 5 },
               { prompt: "c", duration_s: 5 }],
    sound: entries,
  }));
  let commits = 0;
  const lane = new SoundLane({ read: () => piece, onCommit: () => { commits += 1; },
                               flash: () => {} });
  lane.lengths.set("score.wav", 30);
  lane.render();
  return { piece, lane, commits: () => commits };
}

/** The lane is 100 px wide in the shim and starts at x=0, so a clientX is a
 *  percentage of the piece: 20 px into a 15 s piece is 3 s in. */
const press = (node, x) => node.listeners.pointerdown[0](
  { clientX: x, pointerId: 1, preventDefault() {}, stopPropagation() {} });
const move = (node, x) => node.listeners.pointermove.forEach((fn) => fn({ clientX: x }));
const lift = (node) => node.listeners.pointerup.forEach((fn) => fn({}));

const block = (lane) => lane.host.querySelectorAll(".mmc-snd-block")[0];
const grip = (lane, edge) =>
  lane.host.querySelectorAll(`.mmc-snd-grip.${edge}`)[0];

// ---- a drag that goes somewhere ---------------------------------------------
{
  const { piece, lane, commits } = laid();
  const node = block(lane);

  press(node, 0);
  move(node, 10);
  // The node the pointer is on, after the lane has had every chance to rebuild
  // under it. This is the assertion: in a browser a replaced node is a dropped
  // pointer capture, and every move after this one goes nowhere.
  const alive = block(lane) === node;
  move(node, 30);
  move(node, 60);
  const stillAlive = block(lane) === node;
  // What the surface says mid-drag, while the piece has not been touched.
  const painted = node.style.left;
  const untouched = piece.sound[0].at_s === 0;
  lift(node);

  out.drag = {
    alive, stillAlive, painted, untouched,
    // Where the second cut is, in the units the block is drawn in. The pointer
    // stopped six pixels short of it and the drag pulled it the rest of the
    // way, which is the gesture the snap radius exists for.
    cut: lane.pct(S.passWindows(piece)[2].at),
    at: piece.sound[0].at_s,
    // One gesture is one edit. A commit per move buries the undo stack and
    // writes the widget sixty times to move a cue once.
    commits: commits(),
  };
}

// ---- a press that never moved is still a click ------------------------------
//
// Clicking a block opens it in the trim modal, and a click only lands when the
// same node saw both halves of the press. Writing or re-rendering on an
// untouched pointerup eats it.
{
  const { lane, commits } = laid();
  const node = block(lane);
  press(node, 20);
  lift(node);
  out.click = { same: block(lane) === node, commits: commits() };
}

// ---- trimming an end ---------------------------------------------------------
//
// The head handle moves where the block sits in the piece and where it opens in
// the file together; the tail moves only the file's out point.
{
  const { piece, lane } = laid();
  const tail = grip(lane, "tail");
  press(tail, 33);
  move(tail, 60);
  lift(tail);
  out.tail = { at_s: piece.sound[0].at_s, in_s: piece.sound[0].in_s,
               out_s: piece.sound[0].out_s };

  const fresh = laid();
  const head = grip(fresh.lane, "head");
  press(head, 0);
  move(head, 13);
  lift(head);
  out.head = { at_s: fresh.piece.sound[0].at_s, in_s: fresh.piece.sound[0].in_s,
               out_s: fresh.piece.sound[0].out_s };
}

// ---- putting one track in front of another ----------------------------------
//
// The lane's rule is that two blocks never overlap, and for a while that made a
// neighbour a wall with nothing behind it: the only way to put a cue in front of
// one already down was to delete both and lay them again the other way round.
// Pushed past the halfway mark the two trade places instead.
{
  const two = [{ filename: "score.wav", at_s: 0, in_s: 0, out_s: 5 },
               { filename: "voice.wav", at_s: 5, in_s: 0, out_s: 3 }];
  const order = (piece) => piece.sound.map((entry) => [entry.filename, entry.at_s]);

  // Short of the mark: the wall holds, and the block butts up against it. The
  // second track sits at 5 s and is 3 s long, so its middle is at 6.5 s — the
  // pointer stops just before the first track's own middle at 2.58 s.
  const near = laid(two);
  const held = near.lane.host.querySelectorAll(".mmc-snd-block")[1];
  press(held, 33);
  move(held, 12);
  lift(held);
  out.butted = order(near.piece);

  // Past it: the two swap, closing up at the head of the stretch they had.
  const far = laid(two);
  const past = far.lane.host.querySelectorAll(".mmc-snd-block")[1];
  press(past, 33);
  move(past, 4);
  lift(past);
  out.swapped = order(far.piece);

  // And back again inside one gesture — a reorder is the drag, not a mode.
  // Read off the painted lane, not the piece: the piece is not written until
  // the pointer is up, so mid-drag the swap exists only on screen, which is
  // where the person doing it is looking.
  const back = laid(two);
  const there = back.lane.host.querySelectorAll(".mmc-snd-block")[1];
  const drawn = () => [...back.lane.host.querySelectorAll(".mmc-snd-block")]
    .map((node) => parseFloat(node.style.left));
  press(there, 33);
  move(there, 4);
  const [score, voice] = drawn();
  move(there, 33);
  lift(there);
  out.returned = { swappedOnScreen: voice < score, after: order(back.piece) };

  // The other direction: the first track pushed past the second.
  const right = laid(two);
  const first = right.lane.host.querySelectorAll(".mmc-snd-block")[0];
  press(first, 0);
  move(first, 45);
  lift(first);
  out.forward = order(right.piece);
}

// ---- and it is still there tomorrow -----------------------------------------
{
  const { piece, lane } = laid();
  const node = block(lane);
  press(node, 0);
  move(node, 40);
  lift(node);

  const saved = S.serializeTimeline(piece);
  const reopened = S.parseTimeline(saved);
  out.reload = {
    stored: JSON.parse(saved).sound ?? null,
    lane: reopened.sound ?? null,
    // A piece with nothing on the lane writes no key at all, so every workflow
    // saved before the lane existed round-trips to the bytes it always had.
    empty: "sound" in JSON.parse(S.serializeTimeline(
      S.parseTimeline(JSON.stringify({ version: 2, prompt: "x",
                                       segments: [{ prompt: "a", duration_s: 5 }] })))),
  };
}

// ---- what a hand-written blob is allowed to hold ----------------------------
{
  const piece = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "x", segments: [{ prompt: "a", duration_s: 5 }],
    sound: [
      { filename: "good.wav", at_s: 1, in_s: 0, out_s: 3 },
      { filename: "", at_s: 0, in_s: 0, out_s: 3 },
      { at_s: 0, in_s: 0, out_s: 3 },
      { filename: "tiny.wav", at_s: 0, in_s: 1, out_s: 1.05 },
      { filename: "junk.wav", at_s: "half way in", in_s: 0, out_s: 2 },
      { filename: "back.wav", at_s: -4, in_s: 0, out_s: 2 },
    ],
  }));
  out.hand = piece.sound.map((entry) => entry.filename);
}

console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    reflected = layout.in_pack(CHECK.replace('await import("./dom.mjs");', DOM), target)

drag = reflected["drag"]
check("the lane is not rebuilt under the pointer", drag["alive"], True)
check("...not after the third move either", drag["stillAlive"], True)
check("the block is painted where the drag has got to", drag["painted"], drag["cut"])
check("...and the piece is not touched until the pointer is up", drag["untouched"], True)
# Two shots in. A "5 s" shot is 5.167 s once the family's frame grid has had
# it, which is exactly why a cue is placed against the cut and not by counting.
check("the cue lands on the cut it was dragged to", drag["at"], 10.333)
check("one gesture writes the piece once", drag["commits"], 1)

check("a press that never moved rebuilds nothing", reflected["click"]["same"], True)
check("...and writes nothing", reflected["click"]["commits"], 0)

# Dragging the tail out to 60% of a 15 s piece: the block still starts at 0 and
# opens at the head of the file, and only its out point moved.
check("the tail moves the file's out point", reflected["tail"],
      {"at_s": 0, "in_s": 0, "out_s": 10.333})
# ...and the head moves both windows at once — two seconds in on the piece is
# two seconds into the file, and the block is that much shorter.
check("the head moves the piece and the file together", reflected["head"],
      {"at_s": 2, "in_s": 2, "out_s": 5})

check("the lane reaches the blob", reflected["reload"]["stored"],
      [{"filename": "score.wav", "at_s": 5.167, "in_s": 0.0, "out_s": 5.0}])
check("...and is still on the lane when the piece is reopened",
      reflected["reload"]["lane"],
      [{"filename": "score.wav", "at_s": 5.167, "in_s": 0.0, "out_s": 5.0}])
check("a piece with no lane writes no key", reflected["reload"]["empty"], False)

# Kept what can be read, dropped what cannot: no filename, none at all, shorter
# than the shortest block, and numbers that are not numbers.
check("a hand-written lane keeps only what it can read",
      reflected["hand"], ["good.wav"])

# The reorder. A "5 s" shot is 5.167 s on the frame grid, so the first track
# runs 0–5 s and the second 5–8 s on a 15.5 s piece.
check("a neighbour still stops a cue short of it", reflected["butted"],
      [["score.wav", 0.0], ["voice.wav", 5.0]])
check("...and gives way once it is pushed past the middle", reflected["swapped"],
      [["voice.wav", 0.0], ["score.wav", 3.0]])
check("the swap is on screen while the pointer is still down",
      reflected["returned"]["swappedOnScreen"], True)
check("...and pushing back the other way undoes it",
      reflected["returned"]["after"], [["score.wav", 0.0], ["voice.wav", 5.0]])
check("a cue can be pushed forward past one as well", reflected["forward"],
      [["voice.wav", 0.0], ["score.wav", 3.0]])

passed("a cue can be dragged, and the lane survives a reload")
