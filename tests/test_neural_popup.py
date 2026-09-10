"""DLSS can always be switched off, including on a machine without its weights.

    python3 tests/test_neural_popup.py

The actual TimelineBody sampler row and shared popover run against the existing
DOM shim. No server, GPU, DLL, or weights are needed: their absence must not
prevent editing a saved workflow. These are interaction/serialization checks,
not browser-layout or neural-rendering tests.
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
import assert from "node:assert/strict";
// Keep text assertions independent of the machine's browser/Node locale.
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const S = await import("./web/creator/state.js");
const { NEURAL } = await import("./web/creator/manifest.js");
const { TimelineBody } = await import("./web/creator/timeline.js");
const { openNeuralPopover } = await import("./web/creator/pills.js");

function click(node) {
  assert.ok(node, "the click target exists");
  for (const listener of node.listeners.click ?? []) {
    listener({ currentTarget: node, target: node,
               stopPropagation() {}, preventDefault() {} });
  }
}
const pop = () => document.body.querySelector(".mmc-neural-pop");
const toggle = () => pop()?.querySelector('[role="switch"]');
const displayedOn = () => toggle()?.getAttribute("aria-checked");

function build(on, ready, saved = null) {
  document.body.replaceChildren();
  NEURAL.ready = ready;
  NEURAL.needs = ready ? null : "DLSS weights are absent";
  const store = { writes: 0, value: saved ?? JSON.stringify({ version: 2,
    aspect: "16:9", short_edge: 480,
    segments: [{ prompt: "one", duration_s: 6 }, { prompt: "two", duration_s: 6 }],
    neural: { ...S.emptyNeural(), on },
  }) };
  const body = new TimelineBody({
    read: () => store.value,
    write: (value) => { store.value = value; store.writes++; },
    widgets: {}, nodeId: () => 1,
  });
  const row = body.renderSampling();
  document.body.appendChild(row);
  const pill = row.querySelectorAll("button").find((n) => n.text.includes("DLSS"));
  return { body, store, pill };
}

let bodyCases = 0;
for (const ready of [false, true]) {
  for (const on of [false, true]) {
    const { body, store, pill } = build(on, ready);
    // The body is not the modal Timeline class; do not add a fake method to
    // make its callback work. This exercises the callback actually shipped.
    assert.equal(typeof body.geometry, "undefined");
    click(pill);
    assert.ok(pop()?.isConnected);
    assert.equal(displayedOn(), String(on));
    assert.equal(store.writes, 0, "opening settings does not save them");
    if (!on) click(toggle());
    assert.equal(displayedOn(), "true");
    assert.equal(body.timeline.neural.on, true);
    assert.ok(pop().text.includes("832 × 480"), "the timeline canvas supplies the estimate");
    click(toggle());
    assert.equal(displayedOn(), "false");
    assert.equal(body.timeline.neural.on, false);
    assert.equal(Object.hasOwn(JSON.parse(store.value), "neural"), false);
    // An unrelated control must not resurrect ON when it saves the timeline.
    body.set("cfg", 3.5);
    assert.equal(Object.hasOwn(JSON.parse(store.value), "neural"), false);
    const reloaded = build(false, ready, store.value);
    assert.equal(reloaded.body.timeline.neural.on, false);
    click(reloaded.pill);
    assert.equal(displayedOn(), "false");
    body.destroy();
    reloaded.body.destroy();
    bodyCases++;
  }
}

let fallbackCases = 0;
const warnings = [];
const warn = console.warn;
console.warn = (...args) => warnings.push(args);
try {
  for (const ready of [false, true]) {
    for (const initialOn of [false, true]) {
      const { body, store, pill } = build(initialOn, ready);
      openNeuralPopover(pill, {
        target: body.timeline, commit: () => body.commit(),
        geometry: () => { throw new Error("estimate unavailable"); },
      });
      assert.ok(pop()?.isConnected, "optional geometry cannot prevent opening");
      if (!initialOn) click(toggle());
      assert.equal(displayedOn(), "true");
      assert.equal(body.timeline.neural.on, true);
      assert.ok(pop().text.includes("About a gigabyte of VRAM per megapixel."));
      if (!initialOn) assert.equal(JSON.parse(store.value).neural.on, true);
      click(toggle());
      assert.equal(displayedOn(), "false");
      assert.equal(body.timeline.neural.on, false);
      assert.equal(Object.hasOwn(JSON.parse(store.value), "neural"), false);
      assert.equal(S.parseTimeline(store.value).neural.on, false);
      body.destroy();
      fallbackCases++;
    }
  }
} finally {
  console.warn = warn;
}
assert.equal(warnings.length, 4, "only the four failed estimates are reported");
assert.ok(warnings.every((entry) => entry[1]?.message === "estimate unavailable"));

// The fallback is confined to the optional estimate, not a catch around all
// settings rendering or saving that would conceal an unrelated regression.
{
  const { body, pill } = build(true, true);
  assert.throws(() => openNeuralPopover(pill, {
    target: body.timeline, commit: () => body.commit(),
    geometry: () => ({ width: 832, height: 480 }),
    picture: () => { throw new Error("unrelated picture failure"); },
  }), /unrelated picture failure/);
  body.destroy();
}
console.log(JSON.stringify({ bodyCases, fallbackCases }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)

check("real timeline ON/OFF and readiness combinations", result["bodyCases"], 4)
check("failing optional geometry ON/OFF and readiness combinations", result["fallbackCases"], 4)
