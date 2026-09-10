"""A twin accepts only its producer's file, including the correct batch index.

    python3 tests/test_loupe_producer.py
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const url = pathToFileURL(path.join(process.cwd(), "web/creator/loupe.js"));
const source = readFileSync(url, "utf8").replace("class Loupe {", "export class Loupe {")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, url).href}"`);
const { api } = await import("./../scripts/api.js");
const baseFetch = api.fetchApi.bind(api);
api.fetchApi = async (route, options) => {
  if (String(route).startsWith("/continuity/probe")) return {
    ok: true, json: async () => ({ width: 1920, height: 1080 }) };
  if (String(route).startsWith("/continuity/neural/of")) return {
    ok: true, json: async () => ({ ours: true, on: false, settings: null, node: "B", index: 1 }) };
  if (String(route).startsWith("/continuity/neural/twin")) return {
    ok: true, json: async () => ({ prompt_id: "comparison", node: "B", index: 1 }) };
  return baseFetch(route, options);
};
const { Loupe } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const { NEURAL } = await import("./web/creator/manifest.js");
NEURAL.ready = true;
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
const file = (name) => ({ filename: name, subfolder: "renders", type: "output" });
const lp = new Loupe({ source: { path: "B-second.png [output]", kind: "image" }, compare: true }, () => {});
lp.mount(); await flush();
try {
  await lp.renderTwin();
  lp.onWire({ type: "executed", detail: { prompt_id: "comparison", node: "A.0.save", display_node: "A",
    output: { mmc_image: [file("A-first.png"), file("A-second.png")] } } });
  assert.equal(lp.twin, null, "another output from the same prompt is ignored");
  assert.equal(lp.twinBusy, true);
  lp.onWire({ type: "executed", detail: { prompt_id: "comparison",
    output: { mmc_image: [file("anonymous.png"), file("anonymous-2.png")] } } });
  assert.equal(lp.twin, null, "an anonymous result cannot claim this comparison");
  lp.onWire({ type: "executed", detail: { prompt_id: "another-prompt", node: "B",
    output: { mmc_image: [file("wrong-prompt.png"), file("wrong-prompt-2.png")] } } });
  assert.equal(lp.twin, null);
  lp.onWire({ type: "executed", detail: { prompt_id: "comparison", node: "B.0.save", display_node: "B",
    output: { mmc_image: [file("B-first.png"), file("B-second.png")] } } });
  assert.equal(lp.twin.path, "renders/B-second.png [output]");
  assert.equal(lp.twinBusy, false);
  assert.equal(lp.twinId, null);
  lp.onWire({ type: "executed", detail: { prompt_id: "comparison", node: "A",
    output: { mmc_image: [file("late-A.png")] } } });
  assert.equal(lp.twin.path, "renders/B-second.png [output]");
} finally { lp.close(); }
console.log(JSON.stringify({ checked: true }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)
check("producer and image-index routing", result["checked"], True)
