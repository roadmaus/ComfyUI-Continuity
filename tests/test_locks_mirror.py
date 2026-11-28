"""A locked take stays put, and a part-render shoots what was picked.

Two things the reel promises and `compile.py` has to keep:

- **A lock.** A kept take is released by an edit to its card, by a new take of
  what it continues from, and by cards moving around. A locked one is not: it
  plays until its own button lets it go. This walks a piece through
  `state.js` and asks `compile.py` at each step what it would sample and what
  it would play.
- **Shooting some of it.** Picking shots and shooting only those queues the
  same node with a blob in which every other pass is held
  (`state.partialPiece`). `compile.py` is what decides what that blob makes,
  so the picks are checked against it: what is sampled, what plays as film,
  and what is left out.

    python3 tests/test_locks_mirror.py

Skips itself if node is not installed. `compile.py` is authoritative.
"""

import json

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")

_pkg = layout.load("canvas", "h3_declare", "contextir", "compile")
compiler = _pkg.compile

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


def what_renders(blob):
    """-> (sampled card numbers, played card numbers) for a blob."""
    piece = compiler.rendered_piece(json.loads(blob))
    segments = compiler.timeline_segments(piece)
    runs = compiler.timeline_runs(piece, segments)
    payloads = compiler.timeline_payloads(piece)
    sampled, played = [], []
    for (start, _), payload in zip(runs, payloads):
        number = int(segments[start].get("card_no") or start + 1)
        (played if "clip" in payload else sampled).append(number)
    return sampled, played


# Four shots: 2 continues from 1, 4 continues from 3, a cut between 2 and 3.
WALK = """
const s = await import(process.argv[1]);
const timeline = s.parseTimeline(JSON.stringify({
  version: 2, render: "chained", prompt: "p", aspect: "16:9", short_edge: 768,
  segments: [1, 2, 3, 4].map((n) => ({
    prompt: "shot " + n, duration_s: 5, assets: [], loras: [],
    ...(n === 2 || n === 4 ? { continue: true, continue_audio: true, feather: 22 } : {}),
  })),
}));
const out = [];
let version = 0;
const report = (index) => ({
  segment: index + 1, filename: "s" + (index + 1) + "v" + (++version) + ".mp4", subfolder: "takes",
  duration_s: 5, width: 1280, height: 720, has_audio: true,
});
const land = (...indices) => s.attachTakes(timeline, indices.map(report));
const commit = () => { s.syncTimeline(timeline); s.releaseEdited(timeline); };
const step = (name, extra = {}) => {
  s.syncTimeline(timeline);
  out.push({ name, blob: s.serializeTimeline(timeline),
             jumps: [...s.lockedJumps(timeline)], edited: [...s.editedSince(timeline)], ...extra });
};
land(0, 1);                                              step("1 and 2 land");
s.lockTake(timeline, 0, true);                           step("lock 1");
timeline.segments[0].prompt = "shot 1, a comma,";
commit();                                                step("a tiny edit to locked 1");
s.lockTake(timeline, 0, false); commit();                step("unlock 1");
s.lockTake(timeline, 1, true); commit();                 step("lock 2 while 1 reshoots");
land(0); commit();                                       step("1 lands again");
s.lockTake(timeline, 1, false); commit();                step("unlock 2");
const refused = s.lockTake(timeline, 2, true);           step("lock 3, which has no take", { refused: !refused });
console.log(JSON.stringify(out));
"""

walked = layout.run(WALK, MIRROR)
WANT = [
    # name                         sampled     played   jumps (pass indices)
    ("1 and 2 land",               [3, 4],     [1, 2],  []),
    ("lock 1",                     [3, 4],     [1, 2],  []),
    ("a tiny edit to locked 1",    [3, 4],     [1, 2],  []),   # the bug this is for
    ("unlock 1",                   [1, 2, 3, 4], [],    []),   # the edit is shot, and 2 follows
    ("lock 2 while 1 reshoots",    [1, 3, 4],  [2],     [1]),  # kept, and the cut may jump
    ("1 lands again",              [3, 4],     [1, 2],  [1]),  # still kept, still may jump
    ("unlock 2",                   [2, 3, 4],  [1],     []),   # it read the old 1: shot again
    ("lock 3, which has no take",  [2, 3, 4],  [1],     []),
]
check("every step was walked", len(walked), len(WANT))
for (name, sampled, played, jumps), seen in zip(WANT, walked):
    got_sampled, got_played = what_renders(seen["blob"])
    check(f"{name}: generated", got_sampled, sampled)
    check(f"{name}: played from film", got_played, played)
    check(f"{name}: locked cuts that may jump", seen["jumps"], jumps)
    check(f"{name}: is the step it says", seen["name"], name)
check("a lock with no take behind it is refused", walked[7].get("refused"), True)
check("the edit under the lock is still seen as an edit", walked[2]["edited"], [0])
locked_blob = json.loads(walked[1]["blob"])
check("a lock is written to the blob", locked_blob["segments"][0].get("lock"), True)
check("...and a take says what it continued from",
      locked_blob["segments"][1]["take"].get("from"), ["takes/s1v1.mp4 [output]"])
check("locking is not an edit", walked[1]["edited"], [])

# ---- shooting some of it ------------------------------------------------------
#
# Shot 1 and 2 kept (2 continues from 1), 3 and 4 never shot (4 continues
# from 3), 5 kept after a cut. Every pick asked of `state.js`, then the blob it
# makes asked of `compile.py`.

PICKS = """
const s = await import(process.argv[1]);
const take = (n) => ({ filename: "takes/s" + n + ".mp4 [output]", duration_s: 5,
                       width: 1280, height: 720, has_audio: true });
const timeline = s.parseTimeline(JSON.stringify({
  version: 2, render: "chained", prompt: "p", aspect: "16:9", short_edge: 768,
  segments: [1, 2, 3, 4, 5].map((n) => ({
    prompt: "shot " + n, duration_s: 5, assets: [], loras: [],
    ...(n === 2 || n === 4 ? { continue: true, continue_audio: true, feather: 22 } : {}),
    ...(n === 1 || n === 2 || n === 5 ? { hold: true, take: take(n) } : {}),
    ...(n === 5 ? { lock: true } : {}),
  })),
}));
s.syncTimeline(timeline);
const entries = (picks, busy = []) => s.shootEntries(timeline, picks, new Set(busy));
const blob = (wanted) => s.partialPiece(timeline, wanted);
const full = s.serializeTimeline(timeline);
console.log(JSON.stringify({
  alone4: entries([3]),
  alone2: entries([1]),
  order: entries([4, 1]),
  joined: entries([2, 3]),
  joinedLate: entries([3, 2]),
  busy: entries([3], [2]),
  blob4: blob([2, 3]),
  blob2: blob([1]),
  blob5: blob([4]),
  partial: s.queuedCards(s.parseTimeline(blob([1]))).partial,
  whole: s.queuedCards(s.parseTimeline(full)).partial,
  unchanged: s.serializeTimeline(timeline) === full,
}));
"""

picks = layout.run(PICKS, MIRROR)
check("shot 4 alone brings shot 3, which it starts from",
      picks["alone4"], {"entries": [{"passes": [2, 3], "added": [2]}], "problem": None})
check("shot 2 alone plays shot 1's take",
      picks["alone2"], {"entries": [{"passes": [1], "added": []}], "problem": None})
check("picks shoot in the order they were picked",
      [entry["passes"] for entry in picks["order"]["entries"]], [[4], [1]])
check("a pick that continues from an earlier pick joins its render",
      picks["joined"]["entries"], [{"passes": [2, 3], "added": []}])
check("...in either order of picking",
      picks["joinedLate"]["entries"], [{"passes": [2, 3], "added": []}])
check("a pick waiting on a shot already on the queue is refused, not shot twice",
      picks["busy"], {"entries": [], "problem": {"pass": 3, "source": 2}})

check("shooting 3 and 4: generates them and nothing else",
      what_renders(picks["blob4"]), ([3, 4], []))
check("shooting 2: plays 1 for its seam and generates 2",
      what_renders(picks["blob2"]), ([2], [1]))
check("shooting locked 5 on purpose: generates it",
      what_renders(picks["blob5"]), ([5], []))
check("a part-render says it is one", picks["partial"], True)
check("...and a whole one does not", picks["whole"], False)
check("making a part-render leaves the strip alone", picks["unchanged"], True)

# A lock is the reel's, not the model's: shot on purpose, a locked card's
# request must be the request it would be unlocked, or locking costs a re-encode.
piece = compiler.rendered_piece(json.loads(picks["blob5"]))
payload = [p for p in compiler.timeline_payloads(piece) if "clip" not in p][0]
check("a lock never reaches the request", "lock" in payload["request"], False)

passed("a locked take survives edits and new takes upstream, and a part-render "
       "shoots only what was picked")
