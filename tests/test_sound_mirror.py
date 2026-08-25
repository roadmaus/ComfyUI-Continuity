"""`sound.js` and `sound.py` still agree about where a track sits.

The lane is decided twice. `sound.js` draws it — a block at a percentage of the
strip, a gap where nothing was laid — and `sound.py` cuts it up and hands the
pieces to the passes that sample them. The two run on different machines at
different times and share nothing but the blob, so the duplication is the same
deliberate one the other mirror suites cover.

The failure it hides is quiet and expensive: a lane that draws a cue starting on
the cut and compiles it a third of a second late is a lane nobody distrusts
until they have rendered the piece twice. `sound.py` is authoritative.

Both families, because the arithmetic is in frames and the frame rates differ —
a mirror that only checked the default family could not see a rounding that only
bites on the other one.

    python3 tests/test_sound_mirror.py

Skips itself if node is not installed.
"""

import json

import layout
from harness import FAILURES, check, passed

layout.skip_without_node()

MIRROR = layout.js("sound.js")

_pkg = layout.load("canvas", "h3_declare", "contextir", "compile", "sound")
compiler = _pkg.compile
sound = _pkg.sound
registry = _pkg.compile.registry

# Lanes worth disagreeing about. Every one is a shape somebody reaches by
# dragging: a cue from the top, one that starts late, two butted up against each
# other, one that ends exactly on a cut, and the awkward fractions that whole
# seconds do not cover.
LANES = [
    [],
    [("score.mp3", 0.0, 0.0, 11.0)],
    [("score.mp3", 2.5, 0.0, 6.25)],
    [("a.wav", 0.0, 0.0, 5.0), ("b.wav", 5.0, 1.5, 9.0)],
    [("a.wav", 0.0, 1.0, 4.0), ("b.wav", 9.3, 0.0, 3.7)],
    [("odd.wav", 1.0 / 3, 0.125, 7.875)],
]

# Strips the lane is laid over. The seamed ones are the point: a feathered seam
# moves every pass after it, so a mirror that only checked a plain strip would
# agree about the one case that cannot drift.
#
# The last number is an *index into the family's own feather grid*, not a frame
# count, and that is not tidiness. H3 inherits (1, 5, 22, 39) and LTX 2.5
# inherits (1, 9, 17, 25) — the video VAE's temporal cycle, which is different
# weights and so a different grid. A hardcoded 22 is a legal seam on one family
# and a blob `compile_request` refuses on the other, and a mirror comparing two
# readings of a request that will never render is a mirror reporting a
# disagreement nobody can reach.
STRIPS = [
    [(5, False, False, 0), (5, False, False, 0), (5, False, False, 0)],
    [(5, False, False, 0), (8, False, True, 2), (4, False, True, 2)],
    [(5, False, False, 0), (4, True, False, 0), (6, False, True, 2)],
    [(12, False, False, 0), (3, False, True, 1)],
]

SCRIPT = """
const snd = await import(process.argv[1]);
const state = await import(process.argv[2]);
const canvas = await import(process.argv[3]);
const [strips, lanes, families] = process.argv.slice(4, 7).map((a) => JSON.parse(a));

const out = [];
for (const family of families) {
  const grid = canvas.featherGrid(canvas.rulesFor(family));
  for (const cards of strips) {
    for (const entries of lanes) {
      const piece = {
        family,
        segments: cards.map(([seconds, merge, cont, step]) => ({
          prompt: "x", duration_s: seconds, merge, continue: cont,
          feather: grid[step],
        })),
        sound: entries.map(([filename, at_s, in_s, out_s]) =>
          ({ filename, at_s, in_s, out_s })),
      };
      const blocks = snd.lane(piece);
      const total = state.timelineFrames(piece);
      out.push({
        windows: state.passWindows(piece).map((w) =>
          [w.at, w.frames, w.sampledAt, w.sampled, w.clip]),
        blocks: blocks.map((b) => [b.filename, b.at, b.frames]),
        band: snd.band(blocks, total).map((p) => [p.at, p.frames, p.block !== null]),
        total,
      });
    }
  }
}
console.log(JSON.stringify(out));
"""

FAMILIES = sorted(registry.video_families())

reflected = layout.run(SCRIPT, MIRROR, layout.js("state.js"), layout.js("canvas.js"),
                       json.dumps(STRIPS), json.dumps(LANES),
                       json.dumps(FAMILIES))


def piece(family, cards, entries):
    grid = _pkg.canvas.feather_grid(registry.RULES[family])
    return {
        "family": family,
        "segments": [{"prompt": "x", "duration_s": seconds, "merge": merge,
                      "continue": cont, "feather": grid[step]}
                     for seconds, merge, cont, step in cards],
        "sound": [{"filename": name, "at_s": at, "in_s": start, "out_s": end}
                  for name, at, start, end in entries],
    }


cases = [(family, cards, entries)
         for family in FAMILIES for cards in STRIPS for entries in LANES]

if len(cases) != len(reflected):
    FAILURES.append(f"the mirror answered {len(reflected)} cases, python has {len(cases)}")
else:
    for (family, cards, entries), drawn in zip(cases, reflected):
        blob = piece(family, cards, entries)
        rules = compiler.rules_of(blob)
        where = f"{family} {len(cards)} cards, {len(entries)} tracks"

        total = compiler.timeline_frames(blob)
        check(f"{where}: the piece is the same length", drawn["total"], total)

        windows = compiler.timeline_windows(blob)
        check(f"{where}: every pass lands where it is drawn",
              drawn["windows"],
              [[w.at, w.frames, w.sampled_at, w.sampled, w.clip] for w in windows])

        blocks = sound.parse(blob["sound"], rules, total)
        check(f"{where}: every block lands where it is drawn",
              drawn["blocks"], [[b.filename, b.at, b.frames] for b in blocks])

        check(f"{where}: the band covers the same stretches",
              drawn["band"],
              [[p.at, p.frames, p.supplied] for p in sound.band(blocks, total)])

passed(f"sound.js mirrors sound.py across {len(cases)} lanes, on both video families")
