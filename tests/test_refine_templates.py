"""The refiner's template pill offers the piece's family's own templates.

    python3 tests/test_refine_templates.py

The pill used to carry one hardcoded list — the default family's five modes —
which is the frontend half of the same bug the backend half of this change
fixed: a piece on any other family was offered templates its refiner does not
have, and pinning one sent a name the server would refuse. So the list travels
in the manifest now, and this holds the three claims that makes:

- the chips a family draws are the ones its own `Prompting` declares;
- a pin is per family, so switching the piece's model pill cannot carry one
  family's template into another's request;
- a pin the family no longer offers reads as `auto` rather than as an error on
  every press — a stale localStorage entry outliving a rename is the ordinary
  case, not a corrupt one.

Skips itself if node is not installed.
"""

import layout

layout.skip_without_node()

from harness import FAILURES, check, passed

_pkg = layout.load("registry", "manifest")
registry, catalog = _pkg.registry, _pkg.manifest.catalog()

VIDEO = list(registry.video_families())

SCRIPT = """
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, String(v)),
};
const [, pinned] = process.argv;
const r = await import('./web/creator/refine.js');
const S = await import('./web/creator/state.js');

const families = %s;
const offered = Object.fromEntries(
  families.map((id) => [id, S.templatesOf(id).map((entry) => entry.name)]));
const helped = families.every((id) =>
  S.templatesOf(id).every((entry) => entry.help && entry.help.length > 10));

// A pin made on one family, read back on every one of them.
r.saveTemplate(families[0], pinned);
const after = Object.fromEntries(families.map((id) => [id, r.chosenTemplate(id)]));

// A name no family declares — the entry a rename leaves behind.
r.saveTemplate(families[0], 'NO-SUCH-TEMPLATE');
const stale = r.chosenTemplate(families[0]);

// The pre-family setting: one template, written flat. It was pinned against
// the only family there was, so that is the one it survives on.
store.clear();
store.set('minimax_creator.refiner', JSON.stringify({ template: pinned }));
const lifted = Object.fromEntries(families.map((id) => [id, r.chosenTemplate(id)]));

console.log(JSON.stringify({ offered, helped, after, stale, lifted }));
""" % layout.json.dumps(VIDEO)

# The pin used throughout: the last template the first family declares, which
# is a real name there and (by construction, since the families' vocabularies
# are their own) not one anywhere else.
PIN = catalog["families"][0]["prompt"]["templates"][-1]["name"]

with layout.pack(skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target, PIN)

for family in VIDEO:
    declared = [entry["name"] for entry in
                next(f for f in catalog["families"] if f["id"] == family)
                ["prompt"]["templates"]]
    check(f"{family} draws the templates it declares", got["offered"][family], declared)
    check(f"...and {family} offers auto first", declared[0], "auto")
check("every chip says what it is for", got["helped"], True)

check("a pin holds on the family it was made for", got["after"][VIDEO[0]], PIN)
for family in VIDEO[1:]:
    check(f"...and {family} is untouched by it", got["after"][family], "auto")
check("a pin no family declares reads as auto", got["stale"], "auto")

check("a pre-family pin is kept for the family it was made against",
      got["lifted"][registry.DEFAULT_VIDEO], PIN)
for family in VIDEO:
    if family != registry.DEFAULT_VIDEO:
        check(f"...and {family} still reads auto", got["lifted"][family], "auto")

passed("the template pill is the piece's family's own, and a pin cannot cross")
