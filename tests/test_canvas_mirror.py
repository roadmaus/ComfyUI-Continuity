"""`canvas.js` still agrees with `canvas.py`.

The duplication is deliberate — the pills resolve `1344 x 768` and the frame
count live, before anything is queued, so the rules have to exist in the browser
too — but it is only safe while the two agree, and nothing else checks that.
`canvas.py` is authoritative; this asserts the mirror reflects it.

    python3 tests/test_canvas_mirror.py

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

MIRROR = layout.js("canvas.js")
canvas = layout.load("canvas").canvas

# Everything the mirror is expected to reproduce, dumped in one go rather than
# one subprocess per question — and asked of **every family**, not of the one
# whose numbers used to be module constants on both sides. That is the whole
# claim the parameterisation makes: one body of math, a family's numbers in,
# and a mirror that only ever checked the default family's could not see the
# case it exists for.
SCRIPT = """
const c = await import(process.argv[1]);
const out = { rules: {}, frames: {}, canvases: {}, trained: {}, matches: {},
              feathers: {}, presets: {} };
for (const id of FAMILIES) {
  const r = c.rulesFor(id);
  out.rules[id] = r;
  out.feathers[id] = c.featherGrid(r);
  out.presets[id] = r.aspects.map(([label]) => label);
  out.frames[id] = {};
  for (let s = r.minSeconds; s <= r.maxSeconds; s++) out.frames[id][s] = c.framesForSeconds(s, r);
  out.canvases[id] = {};
  for (const [label, ratio] of r.aspects) {
    for (const edge of EDGES) out.canvases[id][label + "@" + edge] = c.resolveCanvas(ratio, edge, r);
  }
  out.trained[id] = {};
  for (const n of TRAINED_CASES) out.trained[id][n] = c.isTrainedLength(n, r);
  out.matches[id] = {};
  for (const s of MATCH_CASES) out.matches[id][s] = c.matchSeconds(s, r);
}
console.log(JSON.stringify(out));
"""

# Reference lengths a card can be matched to: both ends of the clamp, the two
# whole seconds either side of a legal count, and the 6.6 s case that is the
# whole reason `match_seconds` does not simply round.
MATCH_CASES = [0.2, 1, 2.5, 5.88, 6, 6.6, 7.29, 9.33, 15, 15.04, 59.71, 60, 180]
EDGES = [384, 512, 640, 768, 896, 1024, 1536, 2048]
TRAINED_CASES = [5, 107, 124, 192, 362, 379, 1433]

# Every family with a frame grid — `canvas.RULES` is the table, so a family
# added there is checked here without this list being touched.
FAMILIES = sorted(canvas.RULES)

# `rulesFrom`'s field names against the dataclass's. The mirror is a
# transliteration, and this is the one place the two spellings meet.
FIELDS = {
    "multiple": "multiple", "fps": "fps", "fpsFixed": "fps_fixed",
    "nativeShortEdge": "native_short_edge", "nativeMaxPixels": "native_max_pixels",
    "minShortEdge": "min_short_edge", "maxShortEdge": "max_short_edge",
    "minRatio": "min_ratio", "maxRatio": "max_ratio",
    "frameStep": "frame_step", "frameOffset": "frame_offset",
    "trainedMinFrames": "trained_min_frames", "trainedMaxFrames": "trained_max_frames",
    "minSeconds": "min_seconds", "maxSeconds": "max_seconds",
}

reflected = layout.run(
    f"const MATCH_CASES = {json.dumps(MATCH_CASES)};\n"
    f"const EDGES = {json.dumps(EDGES)};\n"
    f"const TRAINED_CASES = {json.dumps(TRAINED_CASES)};\n"
    f"const FAMILIES = {json.dumps(FAMILIES)};\n" + SCRIPT, MIRROR)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: canvas.js says {got!r}, canvas.py says {want!r}")


for family in FAMILIES:
    rules = canvas.RULES[family]
    served = reflected["rules"][family]

    for mirrored, field in FIELDS.items():
        check(f"{family}.{field}", served[mirrored], getattr(rules, field))
    # Pairs on one side, a dict on the other, and the *order* is load-bearing —
    # it is the order the aspect popover lists them in.
    check(f"{family} aspects", [list(pair) for pair in served["aspects"]],
          [[label, ratio] for label, ratio in rules.aspects.items()])
    check(f"{family} aspect labels", reflected["presets"][family], list(rules.aspects))

    check(f"{family} feather grid", reflected["feathers"][family],
          list(canvas.feather_grid(rules)))

    for seconds, frames in reflected["frames"][family].items():
        check(f"{family} {seconds}s", frames,
              canvas.frames_for_seconds(int(seconds), rules))

    for key, size in reflected["canvases"][family].items():
        label, edge = key.rsplit("@", 1)
        check(f"{family} {key}", size,
              list(canvas.resolve_canvas(rules.aspects[label], int(edge), rules)))

    for seconds, matched in reflected["matches"][family].items():
        check(f"{family} match {seconds}s", matched,
              canvas.match_seconds(float(seconds), rules))

    # What the match is for: the two decimals it writes have to compile back to
    # the frame count they were chosen from, or the card silently lands
    # somewhere else.
    for seconds in MATCH_CASES:
        clamped = min(rules.max_seconds, max(rules.min_seconds, seconds))
        check(f"{family} match {seconds}s round-trips",
              canvas.frames_for_seconds(canvas.match_seconds(seconds, rules), rules),
              canvas.frames_for_seconds(clamped, rules))

    for frames, trained in reflected["trained"][family].items():
        check(f"{family} is_trained_length({frames})", trained,
              canvas.is_trained_length(int(frames), rules))

passed(f"canvas.js mirrors canvas.py on {len(FAMILIES)} families — every field, "
       f"grid, canvas and match of each")
