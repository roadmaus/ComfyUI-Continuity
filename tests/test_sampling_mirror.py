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

sampling_py = layout.load("accel", "sampling").sampling

SCRIPT = """
const S = await import("./web/creator/state.js");
const M = await import("./web/creator/sampling.js");

const out = { fields: Object.keys(S.SAMPLING_FIELDS).sort(), widgetOnly: M.WIDGET_ONLY };

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
# Both ways round. A name only the frontend knows is a pill that changes nothing;
# a name only the backend knows is a setting nothing can reach.
check("the two halves carry the same fields",
      reflected["fields"], sorted(sampling_py.DEFAULTS))

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
