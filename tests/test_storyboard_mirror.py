"""`state.js` and `compile.py` still agree about the storyboard (issue #43).

The strip decides twice what a card is shown of the shots before it. The
frontend draws it — the chip on the seam, the diagram in its popover, the
"storyboard" badge on the card, the reference route the card takes — and the
compiler decides it, by stamping the cells onto the payload. Both answer off
the same blob keys and the same three rules: which cards a setting or a list
resolves to, which pass each card is generated in, and how nine cells are
shared out by duration. This holds the two to each other through the blob.
`compile.py` is authoritative.

    python3 tests/test_storyboard_mirror.py

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "compile")
compiler = _pkg.compile

# Per case: the piece setting, and per card (seconds, merge, the card's own
# `storyboard` — absent, false, or a list of card numbers).
CASES = [
    (None, [(5, False, None), (4, False, None), (7, False, None)]),
    ("previous", [(5, False, None), (4, False, None), (7, False, None)]),
    ("all", [(5, False, None), (4, False, None), (7, False, None)]),
    ("all", [(5, False, None), (4, False, False), (7, False, None)]),
    ("all", [(5, False, None), (4, False, None), (7, False, [1])]),
    (None, [(5, False, None), (4, False, None), (7, False, [2, 1])]),
    (None, [(5, False, None), (4, False, [2, 3, 9])]),
    # Merged runs: one source at its combined length; a name inside it lands
    # on the run; the head is the one shown.
    ("all", [(5, False, None), (4, True, None), (7, False, None)]),
    (None, [(5, False, None), (4, True, None), (7, False, [2])]),
    ("previous", [(5, False, None), (4, False, None), (7, True, None)]),
    # A short insert, and more shots than cells.
    ("all", [(10, False, None), (0.5, False, None), (10, False, None), (3, False, None)]),
    ("all", [(1, False, None)] * 12),
    ("all", [(2, False, None), (3, False, None), (5, False, None), (1, False, None),
             (4, False, None), (6, False, None), (2, False, None), (2, False, None),
             (3, False, None), (5, False, None), (2, False, None)]),
]

SCRIPT = """
const s = await import(process.argv[1]);
const out = [];
for (const [policy, cards] of JSON.parse(process.argv[2])) {
  const blob = JSON.stringify({
    version: 2, render: "chained", prompt: "p", aspect: "16:9", short_edge: 768,
    ...(policy ? { storyboard: policy } : {}),
    segments: cards.map(([seconds, merge, own], index) => ({
      prompt: "shot " + (index + 1), duration_s: seconds, assets: [], loras: [],
      ...(merge ? { merge: true } : {}),
      ...(own === null ? {} : { storyboard: own }),
    })),
  });
  const timeline = s.parseTimeline(blob);
  s.syncTimeline(timeline);
  out.push({
    sheets: timeline.segments.map((segment, index) =>
      s.storyboardSheet(timeline, index).map(({ pass, count }) => [pass.start, count])),
    modes: timeline.segments.map((segment) => s.mode(segment, timeline)),
    slots: timeline.segments.map((segment) => s.capacity(segment, "image", timeline).used),
    blob: s.serializeTimeline(timeline),
  });
}
console.log(JSON.stringify(out));
"""

reflected = layout.run(SCRIPT, MIRROR, CASES)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: state.js says {got!r}, compile.py says {want!r}")


for (policy, cards), seen in zip(CASES, reflected):
    name = f"{policy or 'off'}:" + "/".join(
        f"{sec}{'m' if merge else ''}{'' if own is None else ('x' if own is False else str(own))}"
        for sec, merge, own in cards)
    data = json.loads(seen["blob"])
    payloads = compiler.timeline_payloads(data)
    runs = compiler.timeline_runs(data)
    # The compiler stamps cells as (payload position, count); the frontend
    # says (pass start, count). Same thing said in the other's numbering.
    want = []
    for index in range(len(cards)):
        head = next((p for p, (start, end) in enumerate(runs) if start <= index < end), None)
        cells = payloads[head].get("storyboard", {}).get("cells", []) \
            if runs[head][0] == index else []
        want.append([[runs[where][0], count] for where, count in cells])
    check(f"{name}: sheets", seen["sheets"], want)
    # A shown card is a reference generation, and the sheet is one of its
    # pictures — the mode and the slot count both say so.
    compiled = compiler.compile_timeline(data)
    for index, (start, end) in enumerate(runs):
        check(f"{name}: card {start + 1} mode", seen["modes"][start], compiled[index].mode)
        check(f"{name}: card {start + 1} pictures", seen["slots"][start],
              len(compiled[index].ref_images))

# The cells themselves, on the numbers alone.
CELLS = [[5], [5, 5], [6, 3], [7, 2], [10, 0.5, 10], [1] * 9, list(range(1, 11)),
         [0, 0], [2, 2, 2, 2], [3.3, 3.3, 3.4], [0.1, 9.9]]
counted = layout.run("""
const s = await import(process.argv[1]);
console.log(JSON.stringify(JSON.parse(process.argv[2]).map((seconds) => s.storyboardCells(seconds))));
""", MIRROR, CELLS)
for seconds, got in zip(CELLS, counted):
    check(f"cells {seconds}", got, compiler.storyboard_cells(seconds))

passed("state.js and compile.py agree about what each shot is shown")
