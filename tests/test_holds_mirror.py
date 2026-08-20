"""`state.js` and `compile.py` still agree about a piece shot a pass at a time.

The strip decides twice what the next queue will do. `state.js` draws it — a
card solid because its take exists, perforated because it has not been shot, and
a bar saying how much of the piece this render will make — and `compile.py`
decides it, by rewriting the piece before a payload is built. The duplication is
the same deliberate one the other mirror tests cover, and the failure it hides
is the expensive kind: a bar that says six seconds and a queue that samples
forty-eight.

So this asserts the mirror through the blob, which is the only thing the two
halves share. `state.js` builds and serializes; `compile.py` reads what it
wrote. `compile.py` is authoritative.

    python3 tests/test_holds_mirror.py

Skips itself if node is not installed.

No clip cards here: what a supplied clip does to the arithmetic is
`test_passes_mirror.py`'s, and a strip that mixes footage with holds only adds
its terms to both sides at once.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "js", "minimax_creator", "state.js")

if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)

package = types.ModuleType("mmcpkg")
package.__path__ = [ROOT]
sys.modules["mmcpkg"] = package
for name in ("canvas", "contextir", "compile"):
    spec = importlib.util.spec_from_file_location(f"mmcpkg.{name}", os.path.join(ROOT, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmcpkg.{name}"] = module
    spec.loader.exec_module(module)
compiler = sys.modules["mmcpkg.compile"]
canvas_mod = sys.modules["mmcpkg.canvas"]

# Per card: (merge, hold, has a take, feather). The shapes a piece passes
# through on the way from "nothing shot" to "all of it kept", plus the ones a
# user reaches by going back — a kept card in the middle, a retake of the first.
CASES = [
    # Nothing held: every strip anyone has rendered so far.
    [(False, False, False, 0), (False, False, False, 22), (False, False, False, 0)],
    # The sequential shoot, one step at a time.
    [(False, False, False, 0), (False, True, False, 22), (False, True, False, 0)],
    [(False, True, True, 0), (False, False, False, 22), (False, True, False, 0)],
    [(False, True, True, 0), (False, True, True, 22), (False, False, False, 0)],
    [(False, True, True, 0), (False, True, True, 22), (False, True, True, 0)],
    # ...and going back: the first card retaken with the later ones kept.
    [(False, False, True, 0), (False, True, True, 22), (False, True, True, 0)],
    # A take that came back and has not been ruled on yet is still in the render.
    [(False, False, True, 0), (False, False, False, 0), (False, False, False, 0)],
    # Holds belong to the pass: a merged run held, and a merged run shot.
    [(False, True, True, 0), (False, False, False, 0), (True, False, False, 0)],
    [(False, False, False, 0), (False, True, True, 0), (True, True, True, 0)],
    # A seam onto a card that is locked with nothing to play, which is what
    # shooting out of order walks into: the queue refuses it and so must the
    # bar. Both orders of it — the card in front never shot, and shot but
    # dropped from behind a kept one.
    [(False, True, False, 0), (False, False, False, 22), (False, True, False, 0)],
    [(False, True, True, 0), (False, True, False, 0), (False, False, False, 22)],
    # ...and the same shape with the seam onto film that *is* there, which is
    # the ordinary sequential shoot and must not be refused.
    [(False, True, True, 0), (False, False, False, 22), (False, True, False, 0)],
]

SCRIPT = """
const s = await import(process.argv[1]);
const out = [];
for (const cards of JSON.parse(process.argv[2])) {
  const blob = JSON.stringify({
    version: 2, render: "chained", prompt: "p", aspect: "16:9", short_edge: 768,
    segments: cards.map(([merge, hold, take, feather], index) => ({
      prompt: "shot " + (index + 1), duration_s: 5, assets: [], loras: [],
      ...(merge ? { merge: true } : {}),
      ...(hold ? { hold: true } : {}),
      ...(take ? { take: { filename: "takes/s" + (index + 1) + ".mp4",
                           duration_s: 5, width: 1280, height: 720,
                           has_audio: true } } : {}),
      ...(feather ? { continue: true, continue_audio: true, feather } : {}),
    })),
  });
  const timeline = s.parseTimeline(blob);
  s.syncTimeline(timeline);
  out.push({
    shot: s.passes(timeline).filter(s.passShot).length,
    sampled: s.sampledFrames(timeline),
    inParts: s.shotInParts(timeline),
    problem: s.stripProblem(timeline) !== null,
    blob: s.serializeTimeline(timeline),
  });
}
console.log(JSON.stringify(out));
"""

result = subprocess.run(
    ["node", "--input-type=module", "--eval", SCRIPT, MIRROR, json.dumps(CASES)],
    capture_output=True, text=True)
if result.returncode != 0:
    print("failed to read state.js:\n" + result.stderr.strip())
    sys.exit(1)
mirror = json.loads(result.stdout)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: state.js says {got!r}, compile.py says {want!r}")


for cards, seen in zip(CASES, mirror):
    name = "".join(("m" if m else ".") + ("h" if h else ".") + ("t" if t else ".")
                   for m, h, t, _ in cards)
    data = json.loads(seen["blob"])
    # Everything the queue would refuse, in one place: a strip with nothing left
    # to render, and a seam onto a card this render will not have. The bar says
    # both while the cards are still in front of you, so both are one flag here.
    try:
        piece = compiler.rendered_piece(data)
        payloads = compiler.timeline_payloads(piece)
        refused = False
    except compiler.CompileError:
        piece, payloads, refused = None, [], True
    check(f"{name}: refused", seen["problem"], refused)
    if refused:
        continue
    sampled = [payload for payload in payloads if "clip" not in payload]

    # How many generations the bar promises, and how many the queue builds.
    check(f"{name}: generations", seen["shot"], len(sampled))
    # ...and how much of the piece they make. The same arithmetic the frame
    # mirror does over the whole strip, restricted to what is sampled: a
    # feathered seam re-generates its inherited run and the reel node drops it.
    check(f"{name}: sampled frames", seen["sampled"],
          sum(canvas_mod.frames_for_seconds(payload["request"]["duration_s"])
              - (payload.get("feather", 1) if payload.get("continue")
                 and payload.get("feather", 1) > 1 else 0)
              for payload in sampled))
    # The bar only draws any of this once the strip is shooting in parts.
    check(f"{name}: shooting in parts", seen["inParts"],
          any(compiler.is_held(segment) or segment.get("take")
              for segment in compiler.timeline_segments(data)))

# The refusal itself, which the cases above never reach because a strip with
# nothing left to render is one the bar is meant to talk you out of.
# A strip where every card is kept is the end of a shoot, not a refusal: it
# samples nothing and writes the piece out of the film it already has.
finished = json.loads(mirror[4]["blob"])
check("a fully kept strip samples nothing", mirror[4]["sampled"], 0)
check("...and is not refused", mirror[4]["problem"], False)
check("...but still writes a piece",
      len(compiler.timeline_payloads(compiler.rendered_piece(finished))), 3)

empty = {"version": 2, "render": "chained", "prompt": "p", "aspect": "16:9",
         "short_edge": 768,
         "segments": [{"prompt": "a", "duration_s": 5, "hold": True},
                      {"prompt": "b", "duration_s": 5, "hold": True}]}
try:
    compiler.rendered_piece(empty)
except compiler.CompileError as exc:
    if "held with nothing to play" not in str(exc):
        FAILURES.append(f"the all-held refusal reads {str(exc)!r}")
else:
    FAILURES.append("a strip with every card held was not refused")

passed(f"state.js mirrors compile.py across {len(CASES)} part-shot strips")
