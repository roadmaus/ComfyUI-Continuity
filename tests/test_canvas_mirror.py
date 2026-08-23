"""`canvas.js` still agrees with `canvas.py`.

The duplication is deliberate — the pills resolve `1344 x 768` and the frame
count live, before anything is queued, so the rules have to exist in the browser
too — but it is only safe while the two agree, and nothing else checks that.
`canvas.py` is authoritative; this asserts the mirror reflects it.

    python3 tests/test_canvas_mirror.py

Skips itself if node is not installed.
"""

import json

import mirror

mirror.skip_without_node()

MIRROR = mirror.js("canvas.js")
canvas = mirror.load("canvas").canvas

# Everything the mirror is expected to reproduce, dumped in one go rather than
# one subprocess per question.
SCRIPT = """
const c = await import(process.argv[1]);
const out = { constants: {}, frames: {}, canvases: {}, trained: {} };
for (const name of ["CANVAS_MULTIPLE", "FPS", "NATIVE_SHORT_EDGE", "NATIVE_MAX_PIXELS",
                    "MIN_SHORT_EDGE", "MAX_SHORT_EDGE", "MIN_SECONDS", "MAX_SECONDS",
                    "TRAINED_MIN_FRAMES", "TRAINED_MAX_FRAMES"]) {
  out.constants[name] = c[name];
}
for (let s = c.MIN_SECONDS; s <= c.MAX_SECONDS; s++) out.frames[s] = c.framesForSeconds(s);
for (const [label, ratio] of c.ASPECT_PRESETS) {
  for (const edge of [384, 512, 640, 768, 896, 1024, 1536, 2048]) {
    out.canvases[label + "@" + edge] = c.resolveCanvas(ratio, edge);
  }
}
for (const n of [5, 107, 124, 192, 362, 379, 1433]) out.trained[n] = c.isTrainedLength(n);
out.matches = {};
for (const s of MATCH_CASES) out.matches[s] = c.matchSeconds(s);
out.presets = c.ASPECT_PRESETS.map(([label]) => label).sort();
console.log(JSON.stringify(out));
"""

# Reference lengths a card can be matched to: both ends of the clamp, the two
# whole seconds either side of a legal count, and the 6.6 s case that is the
# whole reason `match_seconds` does not simply round.
MATCH_CASES = [0.2, 1, 2.5, 5.88, 6, 6.6, 7.29, 9.33, 15, 15.04, 59.71, 60, 180]

reflected = mirror.run(
    f"const MATCH_CASES = {json.dumps(MATCH_CASES)};\n" + SCRIPT, MIRROR)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: canvas.js says {got!r}, canvas.py says {want!r}")


for name, value in reflected["constants"].items():
    check(name, value, getattr(canvas, name))

check("aspect presets", reflected["presets"], sorted(canvas.ASPECT_PRESETS))

for seconds, frames in reflected["frames"].items():
    check(f"{seconds}s", frames, canvas.frames_for_seconds(int(seconds)))

for key, size in reflected["canvases"].items():
    label, edge = key.split("@")
    check(key, size, list(canvas.resolve_canvas(canvas.ASPECT_PRESETS[label], int(edge))))

for seconds, matched in reflected["matches"].items():
    check(f"match {seconds}s", matched, canvas.match_seconds(float(seconds)))

# What the match is for: the two decimals it writes have to compile back to the
# frame count they were chosen from, or the card silently lands somewhere else.
for seconds in MATCH_CASES:
    clamped = min(canvas.MAX_SECONDS, max(canvas.MIN_SECONDS, seconds))
    check(f"match {seconds}s round-trips",
          canvas.frames_for_seconds(canvas.match_seconds(seconds)),
          canvas.frames_for_seconds(clamped))

for frames, trained in reflected["trained"].items():
    check(f"is_trained_length({frames})", trained, canvas.is_trained_length(int(frames)))

passed(f"canvas.js mirrors canvas.py across {len(reflected['frames'])} durations "
      f"and {len(reflected['canvases'])} canvases")
