"""Eight hues, and which of them a handle wears.

The identity hue is the pack's one wordless "this is that": a chip mid-prompt,
the file on the asset row and the card on the cast shelf are the same colour, so
a sentence can be read against the pictures behind it without reading either.
It is derived from the handle rather than stored, which is what makes it survive
a reload and a deletion — img-2 keeps its colour when img-1 is removed.

A file's handle counts (`img-2`, `ref-4`) and a cast member's does not: `anna` is
a name. Every name therefore fell to hue 0, so a cast of five was one colour five
times and a member's chip in the prompt matched their card by accident. This pins
both halves — that the counted handles are exactly where they were, because those
colours are in every saved piece, and that names spread over the same eight.

    python3 tests/test_tag_hues.py

Skips itself if node is not installed.
"""

import json
import os
import shutil
import subprocess
import sys

import layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STATE = layout.js("state.js")

from harness import check, passed, skip  # noqa: E402

if shutil.which("node") is None:
    skip("node is not installed")

SCRIPT = r"""
const s = await import(process.argv[1]);
const of = (list) => Object.fromEntries(list.map((h) => [h, s.tagIndex(h)]));
console.log(JSON.stringify({
  files: of(["img-1", "img-2", "img-9", "vid-1", "aud-1", "ref-1", "ref-4"]),
  names: of(["anna", "test", "subject", "subject_2", "subject_3", "x"]),
  // The same answer twice, from the same string: nothing here may depend on
  // when it was asked or on what was asked before it.
  stable: s.tagIndex("subject_2") === s.tagIndex("subject_2"),
}));
"""

proc = subprocess.run(["node", "--input-type=module", "-e", SCRIPT, "--", STATE],
                      capture_output=True, text=True)
if proc.returncode != 0:
    print(f"node failed:\n{proc.stderr}")
    sys.exit(1)
got = json.loads(proc.stdout)

# The counter, minus one, plus the kind's offset — img-1 opens the row, and
# vid-1 and aud-1 are staggered off it so one of each is three colours.
check("a file's handle is counted, and the count is its hue",
      got["files"],
      {"img-1": 0, "img-2": 1, "img-9": 0, "vid-1": 1, "aud-1": 2,
       "ref-1": 0, "ref-4": 3})

names = got["names"]
check("a cast of five is five colours", len(set(names.values())) >= 5, True)
check("...and @subject_2 is not @subject",
      names["subject"] != names["subject_2"], True)
check("...each of them inside the eight the stylesheet defines",
      all(isinstance(n, int) and 0 <= n <= 7 for n in names.values()), True)
check("a handle keeps its hue", got["stable"], True)

passed("a handle wears one of eight hues, counted where it can be and spread where it cannot")
