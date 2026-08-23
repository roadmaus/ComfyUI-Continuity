"""Every frontend module still links, and the entry point still pulls them in.

    python3 tests/test_js_links.py

The cheapest possible check, and the one this pack was missing. ES modules
resolve their named imports at *link* time, before a line of either module runs:
importing a name the other side does not export takes down the whole graph, not
just the pair. So renaming an export and missing one of its importers does not
break a feature — it breaks the extension, and every node in it falls back to
raw widgets with nothing in the log but a stack trace from a file nobody edited.

`node --check` does not catch it: that is a parse, and the import list parses
fine. `test_js_bodies.py` does catch it, because it imports the entry point —
but it catches it as a hundred lines of node stack in the middle of a suite that
takes a while and is about something else. This says which module and which
name, in a second, which is what you want when the answer is a typo.

Every module is imported *individually* as well as through the entry point.
A module nothing imports yet — one written ahead of its wiring — is exactly
where a bad import hides, and the entry point would never reach it.

Skips itself if node is not installed.
"""

import os
import sys

import layout
from harness import FAILURES, passed

layout.skip_without_node()

MODULES = []
for base, _, names in os.walk(layout.WEB_ROOT):
    # The vendored style atlas is data — a thousand-entry array with no imports
    # in it — and the pack below leaves its stills out anyway.
    if os.path.basename(base) == "atlas":
        continue
    for name in sorted(names):
        if name.endswith(".js"):
            full = os.path.join(base, name)
            MODULES.append(os.path.relpath(full, layout.ROOT).replace(os.sep, "/"))
MODULES.sort()

passed(f"all {len(MODULES) + 1} frontend modules link")

SCRIPT = """
const modules = JSON.parse(process.argv[1]);
const out = { failed: {} };
for (const path of modules) {
  try {
    await import(`./${path}`);
  } catch (error) {
    // The message, not the stack: a link error names the export and the two
    // files, and that is the whole of what is worth reporting.
    out.failed[path] = String(error.message).split("\\n")[0];
  }
}
console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    reflected = layout.in_pack(SCRIPT, target, [*MODULES, "web/creator.js"])

for path, message in sorted(reflected["failed"].items()):
    FAILURES.append(f"{path}: {message}")
