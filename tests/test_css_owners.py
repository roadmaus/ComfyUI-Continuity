"""One class, one stylesheet.

    python3 tests/test_css_owners.py

The frontend's CSS is a dozen modules concatenated into one sheet, in a fixed
order, with no scoping between them. So a rule written as a bare `.mmc-thing` in
one module lands on every `.mmc-thing` on the page, whatever module drew it —
and the last module in the concatenation wins.

That is exactly how a picker's 62-pixel panel thumbnail once became the width of
the node's whole body: `styles/picker.js` introduced `.mmc-panel` without
knowing `styles/editor.js` had defined it years earlier as the editor's main
container. Nothing failed. `node --check` passed, every module still linked,
every body still mounted, and the node face collapsed into a column.

So: a bare class selector belongs to one module, and the ones that are genuinely
shared are named here. Adding a class to the list is a decision — "these two
modules are styling the same element on purpose" — and it is the decision that
was skipped when the collision above was written.

Selectors that qualify themselves are not this suite's business: `.mmc-fs
.mmc-panel` is a statement *about* the editor's panel inside the fullscreen
shell, which is what a cascade is for. Only the unqualified ones are counted,
because only those claim the class outright.
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout
from harness import FAILURES, check, passed

STYLES = os.path.join(layout.ROOT, "web", "creator", "styles")

# Classes two modules style on purpose, each with the module that may do it.
# Both predate this suite and both are deliberate: a refine row is drawn by the
# panel and by the popover that edits it, and the segmented control is drawn by
# the LoRA manager and by the overlays it opens.
SHARED = {
    "mmc-refine-row": {"popovers.js", "refine.js"},
    "mmc-seg": {"loras.js", "overlays.js"},
}

# `{` opens a block; what precedes it on that line is the selector list. Crude,
# and it does not have to be more: an at-rule body or a declaration would not
# match the bare-class pattern below, so anything this misreads is discarded.
_BLOCK = re.compile(r"([^{}]+)\{")
_BARE = re.compile(r"\.(mmc-[a-z0-9-]+)\Z")


def owners():
    """class -> the modules that claim it with an unqualified selector."""
    claimed = collections.defaultdict(set)
    for name in sorted(os.listdir(STYLES)):
        if not name.endswith(".js"):
            continue
        with open(os.path.join(STYLES, name), encoding="utf-8") as handle:
            css = handle.read()
        for block in _BLOCK.finditer(css):
            # The last line before the brace: a multi-line selector list is one
            # per line in this codebase, and a comment above it is not part of it.
            line = block.group(1).strip().split("\n")[-1]
            for selector in line.split(","):
                match = _BARE.fullmatch(selector.strip())
                if match:
                    claimed[match.group(1)].add(name)
    return claimed


claimed = owners()
check("the sheet is not empty", len(claimed) > 200, True)

collisions = {name: sorted(where) for name, where in sorted(claimed.items())
              if len(where) > 1 and where != SHARED.get(name)}
check("every class is one module's, bar the ones named here", collisions, {})

# The other half of the same statement: a name in SHARED that is no longer
# shared is a stale exemption, and a stale exemption is a collision this suite
# would wave through the next time somebody reached for that class.
stale = sorted(name for name, where in SHARED.items()
               if claimed.get(name, set()) != where)
check("...and no exemption outlives the sharing it excuses", stale, [])

passed(f"{len(claimed)} classes, each one module's own")
