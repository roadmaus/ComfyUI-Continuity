"""The Save as RefMod body's blob: a list of files, and the shape before it.

The body now stores several files (a set of stills stacks into one mod) and
offers finished Renders as a source, while a blob saved before either change
still reads. This is the one place that shape is decided on the frontend, and
`creator/refmod_node.py` reads it back, so it is asserted without a browser.

    python3 tests/test_refmod_body.py

Skips itself if node is not installed.
"""

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

SCRIPT = domshim.DOM + """
import { parseRefMod, serializeRefMod } from "./web/creator/refmod.js";
const blob = JSON.parse(process.argv[1]);
const parsed = parseRefMod(JSON.stringify(blob));
const back = JSON.parse(serializeRefMod(parsed));
console.log(JSON.stringify({
  parsed,
  back,
  legacy: parseRefMod(JSON.stringify({ filename: "c.jpg", kind: "image" })).files,
  empty: parseRefMod("{}").files,
  junk: parseRefMod("not json").files,
}));
"""

# A render's path carries ComfyUI's folder annotation; a clip is a video.
BLOB = {"files": [{"path": "a.png", "kind": "image"},
                  {"path": "b.mp4", "kind": "video"},
                  {"path": "clip.mp4 [output]", "kind": "video"}],
        "name": "x", "type": "identity", "capture": "motion", "vae": "v.safetensors"}

with layout.pack(skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target, BLOB)

check("parseRefMod keeps every file and its kind", got["parsed"]["files"], BLOB["files"])
check("serializeRefMod round-trips them", got["back"]["files"], BLOB["files"])
check("...and the answers beside them",
      [got["back"]["name"], got["back"]["type"], got["back"]["capture"], got["back"]["vae"]],
      ["x", "identity", "motion", "v.safetensors"])
check("a blob from before the file list still reads",
      got["legacy"], [{"path": "c.jpg", "kind": "image"}])
check("an empty blob has no files", got["empty"], [])
check("unparseable data has no files", got["junk"], [])

passed("the RefMod body reads and writes its blob")
