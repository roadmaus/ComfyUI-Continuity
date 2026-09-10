"""Three losses from issue #52: a LoRA's soundtrack slider, the "action" take,
and the cast when its mention or its card goes.

    python3 tests/test_issue52.py

Runs the real state, editor and pills modules over the DOM shim. No server.
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
import assert from "node:assert/strict";
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const S = await import("./web/creator/state.js");
const { pickTakes } = await import("./web/creator/editor.js");
const out = {};

// 1. The soundtrack slider survives a serialize/parse round trip, and is not
//    written at all when it was never turned down.
{
  const loras = [{ name: "a.safetensors", strength: 0.8, audio: 0.5, modes: [] },
                 { name: "b.safetensors", strength: 1, modes: [] }];
  const written = S.serializeLoras(loras, "h3");
  out.audio = [written[0].audio, Object.hasOwn(written[1], "audio")];
  const state = S.parseState(JSON.stringify({ ...S.emptyState(), loras: written }));
  out.audioBack = state.loras[0].audio;
}

// 2. Picking "action" narrows the reference to motion, not to full.
{
  const asset = { handle: "img-1", kind: "image", role: "reference", filename: "a.png" };
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  let committed = 0;
  pickTakes(anchor, asset, () => committed++);
  const option = [...document.body.querySelectorAll(".mmc-opt")]
    .find((node) => node.text.trim() === "action");
  assert.ok(option, "the menu offers action");
  for (const listener of option.listeners.click ?? []) listener({});
  out.action = [asset.takes, committed];
}

// 3. Removing the one card a cast member's pictures sit on sends the pictures
//    to the pool rather than away with the card.
{
  const timeline = S.parseTimeline(JSON.stringify({
    version: 2, aspect: "16:9", short_edge: 480,
    subjects: [{ handle: "ana", takes: "person", from: ["img-1"] }],
    segments: [{ prompt: "@ana walks in", duration_s: 6,
                 assets: [{ handle: "img-1", kind: "image", role: "reference", filename: "ana.png" }] }],
  }));
  S.rescueCastFiles(timeline, timeline.segments[0]);
  timeline.segments.splice(0, 1);
  out.rescued = {
    pool: timeline.assets.map((a) => a.filename),
    from: timeline.subjects[0].from,
    cast: timeline.subjects.length,
  };
}
console.log(JSON.stringify(out));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)

check("a turned-down soundtrack is written, a full one is not", result["audio"], [0.5, False])
check("...and reads back", result["audioBack"], 0.5)
check("action narrows to motion", result["action"], ["motion", 1])
check("a removed card leaves the cast's picture in the pool",
      result["rescued"], {"pool": ["ana.png"], "from": ["ref-1"], "cast": 1})
