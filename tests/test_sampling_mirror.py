"""The sampler row's two halves still agree about where the row is kept.

    python3 tests/test_sampling_mirror.py

`sampling.py` reads the block and `sampling.js` writes it, and between them sits
a JSON object nobody validates twice. The failure that shape invites is the
quiet one: a field the pills write under a name the backend does not read is a
control that appears to work and changes nothing about the render.

So the field list is asserted both ways — neither side may carry a name the
other does not — and the three behaviours the move actually rests on are
exercised in the browser half:

  - the blob wins for everything except the seed, which is still a widget;
  - a pill writes the blob rather than the widget;
  - a workflow saved before the move is carried across exactly once.

`tests/test_sampling.py` is the Python half. Skips itself if node is missing.
"""

import json
import sys

import layout
from harness import FAILURES, check, passed

layout.skip_without_node()
passed("the sampler row agrees across both halves")

_pkg = layout.load("accel", "sampling", "ltx25_sampling")
sampling_py = _pkg.sampling

# Each family's row against its own backend module. The list the browser derives
# is the family's manifest widgets, and `test_families.py` holds those against
# these `DEFAULTS` — this closes the loop from the other end, where the bug
# actually was: the browser carried one written-down list, H3's, and an LTX 2.5
# piece lost `video_cfg` and the sigma pair on the way through it.
BACKENDS = {"h3": sampling_py, "ltx25": _pkg.ltx25_sampling}

SCRIPT = """
const S = await import("./web/creator/state.js");
const M = await import("./web/creator/sampling.js");

const out = { widgetOnly: M.WIDGET_ONLY };

// Every family's row, derived from its own declarations rather than written
// down here — which is the point: a family added to the pack turns up in this
// object without anyone editing the browser half.
out.perFamily = Object.fromEntries(S.VIDEO_FAMILIES.map(
  (id) => [id, S.samplingFields(id)]));

// And a row of a family that is not the default survives the store. The old
// list dropped every LTX field but `steps`, on load and on save both, so the
// pills wrote a block that forgot them.
{
  const raw = JSON.stringify({ version: 2, prompt: "x", family: "ltx25",
                               sampling: { steps: 8, video_cfg: 3, stretch: false,
                                           shift_video: 6 } });
  out.ltxRoundTrip = JSON.parse(S.serializeTimeline(S.parseTimeline(raw))).sampling;
}

/** A stand-in for the node's real widgets: `{value}` is all either io reads. */
const fakeWidgets = (values) =>
  Object.fromEntries(Object.entries(values).map(([k, v]) => [k, { value: v }]));

// ---- blobIO -----------------------------------------------------------------
{
  const widgets = fakeWidgets({ seed: 7, steps: 20, sage: false });
  let block = { steps: 4, cfg: 2.0 };
  const io = M.blobIO(() => widgets, () => block, (next) => { block = next; });

  out.reads = {
    fromBlock: io.value("steps", 99),
    // Not in the block: the caller's fallback, never the stale widget.
    absent: io.value("scheduler", "simple"),
    // The seed is the widget's, whatever the block says.
    seed: io.value("seed", 0),
  };

  io.set("steps", 6);
  io.set("scheduler", "beta");
  io.set("seed", 1234);
  out.writes = { block, seedWidget: widgets.seed.value };
}

// ---- adopted ----------------------------------------------------------------
{
  const widgets = fakeWidgets({
    seed: 7, control_after_generate: "fixed", steps: 33, cfg: 4.5,
    sampler_name: "euler", scheduler: "beta", shift_video: 6, shift_audio: 2,
    block_cache: "fast", spectrum: false, spectrum_blend: 0.5, sage: true,
    attention: "default", chunk_ffn: false, fp16_accumulation: false,
  });
  const blob = (extra) => JSON.stringify({ version: 2, prompt: "x", ...extra });

  // A workflow from before the move: no block, so the widgets come across.
  const carried = M.adopted(blob({}), widgets, S.parseTimeline, S.serializeTimeline);
  out.carried = carried === null ? null : JSON.parse(carried).sampling;

  // One saved since: the block is authority and is left alone, even at `{}`,
  // which is what a piece nobody has tuned stores.
  out.declines = {
    full: M.adopted(blob({ sampling: { steps: 9 } }), widgets,
                    S.parseTimeline, S.serializeTimeline),
    empty: M.adopted(blob({ sampling: {} }), widgets,
                     S.parseTimeline, S.serializeTimeline),
    broken: M.adopted("{not json", widgets, S.parseTimeline, S.serializeTimeline),
  };
}

// ---- the round trip ---------------------------------------------------------
{
  const raw = JSON.stringify({ version: 2, prompt: "x", sampling: { steps: 5, cfg: 1.5 } });
  out.roundTrip = JSON.parse(S.serializeTimeline(S.parseTimeline(raw))).sampling;
  // Nothing stored, nothing written — the rule the turbo block already follows.
  out.emptyIsAbsent =
    "sampling" in JSON.parse(S.serializeTimeline(S.parseTimeline(
      JSON.stringify({ version: 2, prompt: "x" }))));
}

console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    reflected = layout.in_pack(SCRIPT, target)

# ---- the field list ----------------------------------------------------------
#
# Every family, both ways round. A name only the frontend knows is a pill that
# changes nothing; a name only the backend knows is a setting nothing can reach, against the module that resolves its row. The
# kinds too: a field the browser stores as a string and Python reads as a number
# is a pill that writes a block the first queue refuses.
KIND = {"number": "number", "boolean": "boolean", "string": "string"}
for family, module in BACKENDS.items():
    fields = reflected["perFamily"].get(family)
    if fields is None:
        FAILURES.append(f"{family} declares no sampler row in the browser")
        continue
    check(f"{family}: the two halves carry the same fields",
          sorted(fields), sorted(module.DEFAULTS))
    for name, kind in sorted(fields.items()):
        want = ("number" if name in module._WHOLE + module._NUMBER
                else "boolean" if name in module._FLAG else "string")
        check(f"{family}: {name} is a {want} on both sides", kind, want)

# A family the catalog offers and this suite has never heard of is a row nobody
# is holding to anything.
for family in reflected["perFamily"]:
    if family not in BACKENDS:
        FAILURES.append(f"{family} has a sampler row and no backend module here")

check("a non-default family's row survives parse and serialize",
      reflected["ltxRoundTrip"], {"steps": 8, "video_cfg": 3, "stretch": False})

# The seed and its after-generate stay on the widgets, and so does the retired
# `sage` switch — `sampling.py` reads all three off the node for the same reason.
check("what stays on the widgets", sorted(reflected["widgetOnly"]),
      ["control_after_generate", "sage", "seed"])
for name in reflected["widgetOnly"]:
    if name in sampling_py.DEFAULTS:
        FAILURES.append(f"{name} is widget-only in the browser and a blob field in Python")

# ---- blobIO ------------------------------------------------------------------

check("a stored field reads off the block", reflected["reads"]["fromBlock"], 4)
check("an absent one reads the caller's fallback", reflected["reads"]["absent"], "simple")
check("the seed reads off the widget", reflected["reads"]["seed"], 7)
check("a pill writes the block",
      reflected["writes"]["block"], {"steps": 6, "cfg": 2.0, "scheduler": "beta"})
check("...and the seed still writes the widget", reflected["writes"]["seedWidget"], 1234)

# ---- the migration -----------------------------------------------------------

carried = reflected["carried"]
check("a pre-move workflow carries its row across",
      (carried["steps"], carried["cfg"], carried["sampler_name"], carried["block_cache"]),
      (33, 4.5, "euler", "fast"))
check("...and does not carry the seed", "seed" in carried, False)
check("...nor the retired switch", "sage" in carried, False)

check("a blob that already has a block is left alone",
      reflected["declines"]["full"], None)
check("...including an empty one, which is a row somebody cleared",
      reflected["declines"]["empty"], None)
check("...and an unparseable blob is somebody else's problem",
      reflected["declines"]["broken"], None)

# The migration must survive `sampling.py`: whatever the widgets held has to be a
# block the backend will actually run, or the first queue after an upgrade fails
# on a row nobody typed.
try:
    sampling_py.block({"sampling": carried})
except sampling_py.SamplingError as exc:
    FAILURES.append(f"the carried row is one Python refuses: {exc}")

# ---- the round trip ----------------------------------------------------------

check("a block survives parse and serialize", reflected["roundTrip"], {"steps": 5, "cfg": 1.5})
check("an untuned piece writes no block at all", reflected["emptyIsAbsent"], False)
