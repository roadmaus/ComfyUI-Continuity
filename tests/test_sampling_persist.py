"""A sampler pill still says the same thing after the workflow is reloaded.

    python3 tests/test_sampling_persist.py

The row moved off the widgets into the blob, and the state layer round-trips it
— `test_sampling_mirror.py` proves that much. What it does not prove is that the
value a *pill* writes ever reaches the blob, because between the two sits the
wiring: which object the body is holding, whose `onCommit` runs, and which state
that callback serializes.

That wiring is where this broke in practice. The pre-stage mounts a body on a
*nested* creator request for its H3 branch (`state.minimax.request`) while the
sampler widgets belong to the pre-stage node, so the row went into the request
and `serializeStill` — which carries no row — dropped it. In the browser that
reads as a node that forgets its sampler every time ComfyUI restarts, and every
layer below it tests clean.

So this drives the real bodies through the real save/load cycle: build one, move
a pill, serialize what the node would store, hand it back to a fresh body, and
ask the pill what it says now. All four faces, because they keep the row in
three different places.

Skips itself if node is not installed.
"""

import layout
from domshim import DOM
from harness import FAILURES, check, passed

layout.skip_without_node()
passed("a moved pill survives a reload on every face")

CHECK = """
await import("./dom.mjs");
const S = await import("./web/creator/state.js");
const { CreatorEditor } = await import("./web/creator/editor.js");
const { PreStageBody } = await import("./web/creator/prestage.js");
const { TimelineBody } = await import("./web/creator/timeline.js");

const out = {};

/** The node's real sampler widgets, as a body sees them. The pre-stage declares
 *  five and the piece thirteen; both are keyed by name, which is all that
 *  matters here. */
const widgets = (names) =>
  Object.fromEntries(names.map((n) => [n, { name: n, value: null, callback() {} }]));

const PIECE_WIDGETS = ["seed", "steps", "cfg", "sampler_name", "scheduler",
                       "shift_video", "shift_audio", "block_cache", "spectrum",
                       "spectrum_blend", "sage", "attention", "chunk_ffn",
                       "fp16_accumulation"];
const PRESTAGE_WIDGETS = ["seed", "steps", "cfg", "sampler_name", "scheduler"];

/**
 * One face, taken through the whole cycle.
 *
 * `build(raw, store)` returns the body; `io(body)` its sampler pair; `save(body)`
 * whatever the node would put in its widget. Written as three hooks because the
 * four faces genuinely differ in all three.
 */
function cycle(label, { blob, widgetNames, build, io, save }) {
  const store = { value: blob };
  const first = build(store.value, widgetNames);

  io(first).set("cfg", 3.5);
  io(first).set("steps", 9);
  io(first).set("sampler_name", "euler");
  const live = { cfg: io(first).value("cfg", null), steps: io(first).value("steps", null) };

  // What the workflow file would hold, and what a fresh session reads back.
  const saved = save(first);
  const second = build(saved, widgetNames);
  out[label] = {
    live,
    stored: JSON.parse(saved).sampling ?? null,
    reloaded: {
      cfg: io(second).value("cfg", null),
      steps: io(second).value("steps", null),
      sampler_name: io(second).value("sampler_name", null),
    },
  };
}

// ---- the piece, as a strip ---------------------------------------------------
cycle("timeline", {
  blob: JSON.stringify({ version: 2, prompt: "x",
                         segments: [{ prompt: "a", duration_s: 5 },
                                    { prompt: "b", duration_s: 5 }] }),
  widgetNames: PIECE_WIDGETS,
  build: (raw, names) => {
    const store = { value: raw };
    const body = new TimelineBody({
      read: () => store.value,
      write: (next) => { store.value = next; },
      widgets: widgets(names),
      nodeId: () => 1,
    });
    body.store = store;
    return body;
  },
  io: (body) => body.widgetIO(),
  save: (body) => body.store.value,
});

// ---- the piece, as one shot --------------------------------------------------
//
// The Creator's face is a CreatorEditor over the piece itself, and it is the
// case where `piece` and the sampling store are the same object.
cycle("creator", {
  blob: JSON.stringify({ version: 2, prompt: "x",
                         segments: [{ prompt: "a", duration_s: 5 }] }),
  widgetNames: PIECE_WIDGETS,
  build: (raw, names) => {
    const piece = S.parseTimeline(raw);
    const editor = new CreatorEditor({
      state: piece.segments[0],
      piece,
      samplingWidgets: widgets(names),
      nodeId: () => 1,
    });
    editor.pieceRef = piece;
    return editor;
  },
  io: (editor) => editor.widgetIO(),
  save: (editor) => S.serializeTimeline(editor.pieceRef),
});

// ---- the pre-stage, on an image architecture ---------------------------------
cycle("prestage_krea2", {
  blob: JSON.stringify({ version: 1, arch: "krea2", prompt: "x" }),
  widgetNames: PRESTAGE_WIDGETS,
  build: (raw, names) => {
    const state = S.parsePreStage(raw);
    const body = new PreStageBody({
      state,
      onCommit: () => {},
      samplingWidgets: widgets(names),
      nodeId: () => 1,
    });
    return body;
  },
  // The *editor's* pair, not the body's: the sampler row is drawn by whichever
  // editor is mounted, so the body's own is not the path a pill takes.
  io: (body) => body.editor.widgetIO(),
  save: (body) => S.serializePreStage(body.state),
});

// ---- the pre-stage, on the H3 branch -----------------------------------------
//
// The one that was broken: this face is a CreatorEditor over a nested creator
// request, while the sampler widgets belong to the pre-stage node. A row written
// into the request is a row `serializeStill` does not carry.
cycle("prestage_minimax", {
  blob: JSON.stringify({ version: 1, arch: "minimax", prompt: "x" }),
  widgetNames: PRESTAGE_WIDGETS,
  build: (raw, names) => {
    const state = S.parsePreStage(raw);
    const body = new PreStageBody({
      state,
      onCommit: () => {},
      samplingWidgets: widgets(names),
      nodeId: () => 1,
    });
    return body;
  },
  // Through the mounted editor, which on this branch is a `CreatorEditor` over
  // the nested request — the whole point of the case.
  io: (body) => body.editor.widgetIO(),
  save: (body) => S.serializePreStage(body.state),
});

// ---- what the row draws -----------------------------------------------------
//
// A separate question from what it stores, and the half that broke: the sampler
// pill read `widget.value` for its label while `set` wrote the blob, so a pick
// changed the render and left the pill showing the old name — a control that
// reads as doing nothing. Asserted against `samplingBar` directly, because the
// io is the thing under suspicion and asking it would prove nothing.
{
  const { samplingBar } = await import("./web/creator/sampling.js");
  const w = widgets(PRESTAGE_WIDGETS);
  // The widget still holds what it held before the row moved; the blob holds
  // the pick. Every face is in this state after a migration.
  w.sampler_name.value = "res_multistep";
  w.sampler_name.options = { values: ["res_multistep", "euler", "ddim"] };
  w.scheduler.value = "simple";
  w.scheduler.options = { values: ["simple", "beta"] };
  const block = { sampler_name: "euler", scheduler: "beta" };
  const bar = samplingBar({
    widgets: w,
    value: (name, fallback) => (name in block ? block[name] : fallback),
    set: () => {},
  });
  const texts = [];
  const walk = (n) => {
    if (!n) return;
    if (n.textContent) texts.push(String(n.textContent));
    (n.children ?? []).forEach(walk);
  };
  walk(bar);
  out.draws = { pick: texts.includes("euler") && texts.includes("beta"),
                stale: texts.includes("res_multistep") || texts.includes("simple") };
}

console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    reflected = layout.in_pack(
        CHECK.replace("await import(\"./dom.mjs\");", DOM), target)

for face in ("timeline", "creator", "prestage_krea2", "prestage_minimax"):
    got = reflected[face]
    check(f"{face}: the pill reads back what was set", got["live"], {"cfg": 3.5, "steps": 9})
    check(f"{face}: the blob carries the row",
          (got["stored"] or {}).get("cfg"), 3.5)
    check(f"{face}: and it is still there after a reload",
          got["reloaded"], {"cfg": 3.5, "steps": 9, "sampler_name": "euler"})

# The row has to *show* the row it is going to run. Storing the pick and drawing
# the widget's old name is a control that reads as broken however right the
# render is.
check("the schedule pill draws what the blob says", reflected["draws"]["pick"], True)
check("...and not what the widget still holds", reflected["draws"]["stale"], False)
