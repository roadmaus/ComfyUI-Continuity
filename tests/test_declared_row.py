"""A declared sampler row draws what the render will actually read.

    python3 tests/test_declared_row.py

`samplingBar` renders a non-H3 family from its manifest alone, and for a while
it rendered *all* of it: the advanced flag Settings → Nodes writes is read past
the early return that sends a declared family off to `declaredRow`, so
"Standard" and "Everything" drew the same row. Worse, LTX 2.5's distilled route
is nine fixed sigmas and `render.py` reads none of the curve controls on it —
so five pills sat on the row at full strength describing a curve nothing built,
one of them (the stretch) lit, which made the only pill that looked switched on
the only one that could not be doing anything.

So this drives the real `samplingBar` against the real manifest and asks what
is on the row, in each of the four states that decide it: the two recipes
crossed with the two settings. Plus the two readings that made the row hard to
parse even where every pill was live — a combo that showed a bare value, and a
guidance slider that showed a number when what it meant was "off".

The one thing it deliberately does not assert is a list of ids. Which controls
LTX considers advanced is that family's statement, in its own manifest, and a
suite holding a copy of it would fail the day somebody made a decision rather
than the day something broke. What is held is the *rules* — requires, in force
means visible, the readouts — against whatever the family declares.

Skips itself if node is not installed.
"""

import layout
from domshim import DOM
from harness import FAILURES, check, passed

layout.skip_without_node()
passed("a declared row draws what the render reads, and reads as words")

_pkg = layout.load("canvas", "accel", "sampling", "contextir", "compile",
                   "compile_image", "models", "registry", "manifest",
                   "still", "krea2_still", "ideogram4_still", "grammar",
                   "h3_declare", "h3_models", "h3_grammar", "ltx25_declare",
                   "ltx25_models", "ltx25_sampling")
ltx = _pkg.manifest.describe("ltx25")
WIDGETS = {w["id"]: w for w in ltx["widgets"]}

# What the family says is advanced, and what only the custom curve is read for.
# Read off the manifest rather than written down — see the docstring.
ADVANCED = sorted(w["id"] for w in ltx["widgets"] if w.get("advanced"))
CURVE_ONLY = sorted(
    w["id"] for w in ltx["widgets"]
    if any(c.get("value") == "scheduler" for c in w.get("requires", [])))

CHECK = """
await import("./dom.mjs");
const { samplingBar } = await import("./web/creator/sampling.js");
const { noteSettings } = await import("./web/creator/api.js");

const [, casesJSON] = process.argv;
const cases = JSON.parse(casesJSON);

// Every pill's text, flattened. The row is nested — a divided pill is a div of
// buttons — so what is asked is "does this string appear anywhere on the row",
// which is also the only question a person has of it.
const textOf = (node) => {
  const out = [];
  const walk = (n) => {
    if (!n) return;
    if (n.tagName === "SPAN" && !(n.children ?? []).length && n.textContent)
      out.push(String(n.textContent).trim());
    (n.children ?? []).forEach(walk);
  };
  walk(node);
  return out;
};

// The row over a plain object, which is all `samplingBar` ever asks of the
// pair. No node and no widgets: this family declares one combo that reads its
// options off a widget (`sampler_name`), and a row drawn without one simply
// has no such pill — asserted below rather than worked around.
const row = (blob, widgets = {}) =>
  textOf(samplingBar({
    widgets,
    value: (name, fallback) => (name in blob ? blob[name] : fallback),
    set: () => {},
    family: "ltx25",
  }));

const out = {};
for (const [label, { settings, blob, widgets }] of Object.entries(cases)) {
  noteSettings(settings);
  out[label] = row(blob, widgets ?? {});
}
console.log(JSON.stringify(out));
"""

# A combo whose options the manifest does not carry reads them off the node's
# own widget — `sampler_name` is that case — so the row is given one.
SAMPLER = WIDGETS["sampler_name"]["default"]
SAMPLER_WIDGET = {"sampler_name": {"name": "sampler_name",
                                   "options": {"values": [SAMPLER, "euler"]}}}

CASES = {
    # The four states the row's length turns on.
    "standard_builtin": {"settings": {"advanced": False}, "blob": {}},
    "everything_builtin": {"settings": {"advanced": True}, "blob": {},
                           "widgets": SAMPLER_WIDGET},
    "standard_custom": {"settings": {"advanced": False},
                        "blob": {"schedule": "scheduler"}},
    "everything_custom": {"settings": {"advanced": True},
                          "blob": {"schedule": "scheduler"},
                          "widgets": SAMPLER_WIDGET},
    # In force means visible: an advanced control away from its default keeps
    # its pill on Standard. Both conditions have to hold at once, so the recipe
    # is the custom one — an advanced control whose `requires` fails is not in
    # force, it is a leftover.
    "in_force": {"settings": {"advanced": False},
                 "blob": {"schedule": "scheduler",
                          "base_shift": WIDGETS["base_shift"]["default"] + 0.5}},
    # A guidance slider on its declared `off`, and off it.
    "guidance_off": {"settings": {"advanced": False}, "blob": {}},
    "guidance_on": {"settings": {"advanced": False},
                    "blob": {"stg_scale": 1.0, "modality_scale": 3.0}},
}

with layout.pack(skip=["atlas"]) as target:
    drawn = layout.in_pack(
        CHECK.replace("await import(\"./dom.mjs\");", DOM), target, CASES)


def says(case, needle):
    """Whether a pill on that row reads as that control.

    Whole-label rather than substring: the labels are words and one of them is
    "to", which is inside half the row.
    """
    return any(text == needle or text.startswith(needle + " ") for text in drawn[case])


# ---- the curve controls follow the recipe ------------------------------------
#
# The distilled route emits `ManualSigmas` and no `ModelSamplingLTXV` at all;
# `sampling.py`'s own docstring says the five below "describe nothing on this
# route and are not read". Not read means not drawn, at either setting — this
# is the half that is not a length control.

for id in CURVE_ONLY:
    label = WIDGETS[id]["label"]
    check(f"'{label}' is off the row on the built-in curve, whatever the setting",
          (says("standard_builtin", label), says("everything_builtin", label)),
          (False, False))

check("the built-in curve draws no stretch to look switched on",
      says("everything_builtin", "stop early"), False)

# ---- advanced is a length control -------------------------------------------

for id in ADVANCED:
    label = WIDGETS[id]["label"]
    if id in CURVE_ONLY:
        check(f"'{label}' comes back on the custom curve when everything is asked for",
              (says("standard_custom", label), says("everything_custom", label)),
              (False, True))
    else:
        check(f"'{label}' is behind the setting on either recipe",
              (says("standard_custom", label), says("everything_custom", label)),
              (False, True))

check("a value away from its default keeps its pill on Standard",
      says("in_force", WIDGETS["base_shift"]["label"]), True)

# What is *not* behind the setting: the controls a piece is actually tuned by.
for id in ("schedule", "video_cfg", "audio_cfg"):
    check(f"'{WIDGETS[id]['label']}' is on the row at either setting",
          (says("standard_builtin", WIDGETS[id]["label"]),
           says("everything_builtin", WIDGETS[id]["label"])),
          (True, True))

check("steps follows the recipe, not the setting",
      (says("standard_builtin", "steps"), says("standard_custom", "steps")),
      (False, True))

# ---- what the pills read -----------------------------------------------------
#
# A combo used to draw its bare value: `distilled` and `res_multistep` standing
# alone, saying what they are called and never what they are a choice about.

check("the recipe combo says what it is a choice about, under its display name",
      says("standard_builtin", "recipe built-in"), True)
check("and the wire value is not what is shown",
      says("standard_builtin", "recipe distilled"), False)
check("the sampler combo names itself too",
      says("everything_custom", f"sampler {SAMPLER}"), True)

# A slider that declares an `off` reads out at it the way every switch on this
# row always has — "cache off", "faces off" — instead of showing the number a
# person would have to know was the off one.

check("a guidance slider on its off value says off",
      (says("guidance_off", "detail guidance off"), says("guidance_off", "a/v sync off")),
      (True, True))
check("and shows the number once it is costing a pass",
      (says("guidance_on", "detail guidance 1.0"), says("guidance_on", "a/v sync 3.0")),
      (True, True))
check("the blocks field follows its scale on and off",
      (says("guidance_off", "blocks"), says("guidance_on", "blocks")),
      (False, True))

if FAILURES:
    raise SystemExit(1)
