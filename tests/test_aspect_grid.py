"""The aspect popover offers every ratio the manifest lists, in six tiles.

    python3 tests/test_aspect_grid.py

`aspectGrid` groups the presets into shapes — 16:9 and 9:16 are one rectangle
seen two ways up — and hangs one orientation switch over the grid, so a list
that grew from six labels to ten did not grow from six rows to ten. Everything
that can go wrong with that lives in the grouping: a shape silently dropped
because its twin was found twice, a family that lists a shape one way up only
losing it whenever the switch is on the other way, or the switch writing a
ratio over a choice that was never the grid's to make.

So this drives the real `aspectGrid` against the real manifests and asks what
is on the grid, what a tile writes, and what the switch writes. It does not
assert a list of ratios: which shapes a family offers is that family's
statement, and a suite holding a copy would fail the day somebody added one.

Skips itself if node is not installed.
"""

import layout
from domshim import DOM
from harness import FAILURES, check, passed

layout.skip_without_node()
passed("the aspect grid holds every listed ratio and the switch turns it")

_pkg = layout.load("canvas", "compile", "compile_image", "still", "krea2_still",
                   "ideogram4_still", "qwenedit_still", "flux2klein_still",
                   "h3_declare")
H3 = _pkg.h3_declare.RULES.aspects

CHECK = """
await import("./dom.mjs");
const { aspectGrid } = await import("./web/creator/pills.js");

const [, casesJSON] = process.argv;
const cases = JSON.parse(casesJSON);

// A tile is a glyph over its label; the label is the only text on it.
const tiles = (root) => [...root.querySelectorAll(".mmc-aspect-tile")].map((tile) => ({
  label: tile.querySelector(".mmc-aspect-num").textContent,
  on: tile.getAttribute("aria-checked") === "true",
  dead: tile.getAttribute("disabled") !== undefined,
  why: tile.getAttribute("title") ?? null,
}));
const flips = (root) => [...root.querySelectorAll(".mmc-flip-opt")];
// The shim keeps handlers in `listeners`, which is what `el` registers into.
const click = (node) => (node.listeners.click ?? []).forEach((fn) => fn({}));

const out = {};
for (const [name, spec] of Object.entries(cases)) {
  // Every write the grid makes, in order, so "wrote nothing" is a readable
  // answer rather than the absence of one.
  const wrote = [];
  const root = aspectGrid(spec.presets, spec.checked, spec.facing,
                          (label, close) => wrote.push([label, close]));
  const opened = tiles(root);
  // Click through: a named tile first where the case has one, then the switch.
  if (spec.tile) {
    const hit = tiles(root).findIndex((t) => t.label === spec.tile);
    click(root.querySelectorAll(".mmc-aspect-tile")[hit]);
  }
  if (spec.flip) click(flips(root)[spec.flip === "tall" ? 1 : 0]);
  out[name] = {
    opened,
    pressed: flips(root).map((b) => b.getAttribute("aria-pressed") === "true"),
    after: tiles(root),
    wrote,
  };
}
console.log(JSON.stringify(out));
"""

VIDEO = [[label, ratio] for label, ratio in H3.items()]
# A family that lists a shape one way up only. Not a real manifest — the point
# is that the grouping is read off whatever it is handed, so a list nobody has
# written yet still draws every option it contains.
LOPSIDED = [["16:9", 16 / 9], ["9:16", 9 / 16], ["1:1", 1.0], ["2:3", 2 / 3]]

CASES = {
    # Opened on a landscape choice, and on a portrait one: the switch is set
    # from the ratio in force, not from a default.
    "wide": {"presets": VIDEO, "checked": "16:9", "facing": "16:9"},
    "tall": {"presets": VIDEO, "checked": "9:16", "facing": "9:16"},
    # Nothing of the grid's is chosen — a donor picture is supplying the ratio —
    # but the piece still falls back to a portrait shape, so the grid opens
    # turned that way with no tile lit.
    "donor": {"presets": VIDEO, "checked": None, "facing": "3:4"},
    "lopsided_wide": {"presets": LOPSIDED, "checked": "16:9", "facing": "16:9"},
    "lopsided_tall": {"presets": LOPSIDED, "checked": "16:9", "facing": "16:9",
                      "flip": "tall"},
    # A tile is a whole answer and closes; the switch turns the answer already
    # given and does not.
    "pick": {"presets": VIDEO, "checked": "16:9", "facing": "16:9", "tile": "4:3"},
    "turn": {"presets": VIDEO, "checked": "4:3", "facing": "4:3", "flip": "tall"},
    "turn_back": {"presets": VIDEO, "checked": "3:4", "facing": "3:4", "flip": "wide"},
    # The two cases the switch must stay quiet through: no choice of the grid's
    # to turn, and a square, which is the same label both ways up.
    "turn_donor": {"presets": VIDEO, "checked": None, "facing": "16:9", "flip": "tall"},
    "turn_square": {"presets": VIDEO, "checked": "1:1", "facing": "1:1", "flip": "tall"},
}

with layout.pack(skip=["atlas"]) as target:
    drawn = layout.in_pack(
        CHECK.replace('await import("./dom.mjs");', DOM), target, CASES)

labels = lambda case, key="opened": [tile["label"] for tile in drawn[case][key]]
lit = lambda case, key="opened": [tile["label"] for tile in drawn[case][key] if tile["on"]]

# ---- the grid holds every listed ratio ---------------------------------------
#
# Six tiles rather than ten rows, and between the two orientations they name
# every label the manifest declares — the grouping halves the height without
# costing an option. A shape is one rectangle however many ways up it is
# listed, which is what the long edge over the short one says.
shapes = {round(max(ratio, 1 / ratio), 6) for _, ratio in VIDEO}
check("one tile per shape", len(labels("wide")), len(shapes))
check("both ways up name every listed ratio",
      sorted(set(labels("wide") + labels("tall"))), sorted(label for label, _ in VIDEO))

# Widest first, squarest last, so the grid is aimed at rather than read. Asked
# of the ratios the labels stand for, not of the labels.
ratio = dict(VIDEO)
order = [ratio[label] for label in labels("wide")]
check("widest first", order, sorted(order, reverse=True))

# ---- the switch is set from the ratio in force -------------------------------
check("a landscape ratio opens wide", drawn["wide"]["pressed"], [True, False])
check("a portrait ratio opens tall", drawn["tall"]["pressed"], [False, True])
check("wide draws landscape labels", "16:9" in labels("wide"), True)
check("tall draws portrait labels", "9:16" in labels("tall"), True)
check("and only those", "16:9" in labels("tall"), False)
check("the chosen tile is lit", lit("wide"), ["16:9"])

check("the widest shape is the widest", labels("wide")[0], "21:9")
check("and turns with the rest", labels("tall")[0], "9:21")

# Every shape a shipped family offers, it offers both ways up: the switch never
# meets a tile it cannot turn. This is the assertion the manifests were widened
# to satisfy — 21:9 used to have no 9:21 behind it, and the tile that could not
# answer made the switch look broken.
dead = lambda case, key="opened": [t["label"] for t in drawn[case][key] if t["dead"]]
check("nothing dead wide", dead("wide"), [])
check("nothing dead tall", dead("tall"), [])

# A list that does leave one stranded still keeps the option and says why,
# rather than dropping a column out of the grid whenever the switch is turned.
check("the stranded shape holds its column", dead("lopsided_wide"), ["2:3"])
stranded = next(t for t in drawn["lopsided_wide"]["opened"] if t["label"] == "2:3")
check("and says which form is missing", stranded["why"],
      "3:2 is outside this family's aspect range. 2:3 is the only way up "
      "this shape is offered.")
check("and is live the way up it is listed", dead("lopsided_tall", "after"), [])

# A donor supplies the ratio, so nothing on the grid is lit — but the piece's
# own fallback is portrait and the grid opens turned that way, which is the
# shape a preset click would land on.
check("a donor lights no tile", lit("donor"), [])
check("and still opens the right way up", drawn["donor"]["pressed"], [False, True])

# ---- a shape listed one way up only keeps its tile ---------------------------
#
# 2:3 has no 3:2 to pair with. It is not dropped from the landscape grid — it
# shows the one label it has, which is the option the family actually offers.
check("every shape has a tile either way",
      sorted(labels("lopsided_wide")), sorted(labels("lopsided_tall")))
check("the unpaired shape shows what it has",
      "2:3" in labels("lopsided_wide"), True)

# ---- what a tile writes, and what the switch writes --------------------------
check("a tile writes its label and closes", drawn["pick"]["wrote"], [["4:3", True]])
check("the switch writes the flip and stays open", drawn["turn"]["wrote"], [["3:4", False]])
check("and turns back", drawn["turn_back"]["wrote"], [["4:3", False]])
check("the turned tile is the lit one", lit("turn", "after"), ["3:4"])

# Nothing of the grid's is in force, so the switch turns the grid and writes
# nothing: flipping a ratio the user did not choose would be the switch making
# the choice. A square has the same label both ways up and has nothing to say
# either.
check("no choice to turn writes nothing", drawn["turn_donor"]["wrote"], [])
check("but the grid still turns", drawn["turn_donor"]["pressed"], [False, True])
check("a square writes nothing", drawn["turn_square"]["wrote"], [])
