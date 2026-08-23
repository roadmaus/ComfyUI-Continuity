"""`state.js` and `compile.py` still agree about what a pass is.

A pass — a run of merged segments generated as one clip — is decided twice: in
`state.js`, which draws the casing and counts the generations before anything is
queued, and in `compile.py`, which builds one payload per pass at queue time. The
duplication is the same deliberate one the other mirror tests cover, and the
failure it hides is quiet: a strip that says "2 generations" and queues 3, with
the cut times drawn against passes the compiler never made.

So this asserts the mirror through the blob, which is the only thing the two
halves actually share. `state.js` builds and serializes; `compile.py` reads what
it wrote. `compile.py` is authoritative.

    python3 tests/test_passes_mirror.py

Skips itself if node is not installed.
"""

import json

import mirror

mirror.skip_without_node()

MIRROR = mirror.js("state.js")

_pkg = mirror.load("canvas", "contextir", "compile")
compiler = _pkg.compile
canvas_mod = _pkg.canvas


# Every shape worth asking about, as (render, merge flags). The flags are what a
# saved blob carries; `render` is what one saved before they existed carries,
# and both have to come out the same passes on both sides.
# Third element: per-card feather width, 0 for a hard cut. A feathered seam is
# the one thing that makes the finished length differ from what the passes sum
# to, so the frame mirror is only worth anything with these in it.
CASES = [
    ["chained", [False], [0]],
    ["chained", [False, False, False], [0, 0, 0]],
    ["chained", [False, True, False], [0, 0, 0]],
    ["chained", [False, True, True], [0, 0, 0]],
    ["chained", [False, False, True, False, True], [0, 0, 0, 0, 0]],
    ["chained", [True, False, False], [0, 0, 0]],          # ignored on segment 1
    ["single", [False, False, False], [0, 0, 0]],           # saved before the flags existed
    ["single", [False, True, True], [0, 0, 0]],
    # Seams, feathered and not. The widths are FEATHER_GRID's, and card 1's is
    # ignored on both sides exactly as its merge flag is.
    ["chained", [False, False], [0, 22]],
    ["chained", [False, False, False], [0, 5, 39]],
    ["chained", [False, True, False], [0, 0, 22]],          # after a merged pass
    ["chained", [False, False], [39, 22]],                  # ignored on segment 1
]

SCRIPT = """
const s = await import(process.argv[1]);
const out = [];
for (const [render, flags, feathers] of JSON.parse(process.argv[2])) {
  // Built the way the node builds one: a blob in, `parseTimeline` out. That is
  // where a timeline saved as one pass grows its flags, so the case list can
  // hold both spellings of the same strip.
  const blob = JSON.stringify({
    version: 2, render, prompt: "p", aspect: "16:9", short_edge: 768,
    segments: flags.map((merge, index) => ({
      prompt: "shot " + (index + 1), duration_s: 5, assets: [], loras: [],
      ...(merge ? { merge: true } : {}),
      ...(feathers[index]
        ? { continue: true, continue_audio: true, feather: feathers[index] } : {}),
    })),
  });
  const timeline = s.parseTimeline(blob);
  s.syncTimeline(timeline);
  out.push({
    passes: s.passes(timeline).map((pass) => [pass.start, pass.end]),
    frames: s.timelineFrames(timeline),
    render: timeline.render,
    // What the node writes back, and therefore all compile.py ever sees.
    blob: s.serializeTimeline(timeline),
  });
}
console.log(JSON.stringify(out));
"""

reflected = mirror.run(SCRIPT, MIRROR, CASES)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: state.js says {got!r}, compile.py says {want!r}")


for (render, flags, feathers), seen in zip(CASES, reflected):
    name = (f"{render} {''.join('m' if f else '.' for f in flags)}"
            f" {''.join(str(f) if f else '-' for f in feathers)}")
    data = json.loads(seen["blob"])
    runs = [list(run) for run in compiler.timeline_runs(data)]
    check(f"{name}: passes", seen["passes"], runs)
    # And the number the bar reports as the queue's cost is the number of
    # payloads the queue actually builds.
    payloads = compiler.timeline_payloads(data)
    check(f"{name}: generations", len(seen["passes"]), len(payloads))
    # The finished length: snapped per pass rather than per segment, less what
    # each feathered seam re-generates and the reel node then drops. This is the
    # number `MAX_TIMELINE_FRAMES` is checked against, so the two halves
    # disagreeing here means a strip the bar calls legal is refused at queue
    # time — or worse, the reverse.
    check(f"{name}: frames", seen["frames"], compiler.timeline_frames(data))
    # And `timeline_frames` is still counting the passes the compiler built,
    # not a second opinion about them.
    check(f"{name}: frames vs payloads",
          compiler.timeline_frames(data)
          + sum(p.get("feather", 1) if p.get("continue") and p.get("feather", 1) > 1 else 0
                for p in payloads),
          sum(canvas_mod.frames_for_seconds(p["request"]["duration_s"]) for p in payloads))
    # A strip that turned out to be one pass end to end is still called that, so
    # everything that reads the old key keeps working.
    check(f"{name}: render", seen["render"], compiler.render_mode(data))

passed(f"state.js mirrors compile.py across {len(CASES)} strips")
