"""An in-flight tile cannot declare changed settings/frame/region up to date.

    python3 tests/test_loupe_preview.py

Actual Loupe methods and neural slider callbacks run in the shared DOM fixture;
only metadata HTTP and the delayed image response are simulated.
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
    ok: true, json: async () => ({ ours: false, on: false, settings: null }) };
  return baseFetch(route, options);
};
const { Loupe } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const { NEURAL } = await import("./web/creator/manifest.js");
NEURAL.ready = true;
let pendingImage;
globalThis.Image = class {
  constructor() { pendingImage = this; }
  set src(value) { this._src = value; }
  get src() { return this._src; }
};
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
let cases = 0;
for (const change of ["detail", "time", "region", "source", "unchanged", "closed"]) {
  const lp = new Loupe({ source: { path: "photo.png [input]", kind: "image" }, compare: true }, () => {});
  lp.mount(); await flush();
  try {
    const before = lp.overLayer.src;
    const pending = lp.refine();
    const requested = pendingImage;
    if (change === "detail") {
      const slider = lp.rail.querySelector("input");
      slider.value = "3";
      for (const fn of slider.listeners.input ?? []) fn({ target: slider });
      assert.equal(lp.neural.detail, 3);
    }
    if (change === "time") lp.cutter = { at: () => 5, destroy() {} };
    if (change === "region") lp.zoomTo(1, null);
    if (change === "source") lp.source = { path: "other.png [input]", kind: "image" };
    if (change === "closed") lp.close();
    requested.onload(); await pending;
    if (change === "closed") {
      assert.equal(lp.overLayer.src, before, "closed viewer ignores the late image");
      assert.equal(lp.tile, null);
    } else {
      assert.equal(lp.stale, change !== "unchanged", `${change}: completed request freshness`);
      assert.equal("disabled" in lp.rail.querySelector(".mmc-lp-run").attrs, change === "unchanged");
      assert.equal(lp.overLayer.src, requested.src, "completed old tile remains visible, marked stale");
    }
    assert.equal(lp.working, false);
    cases++;
  } finally { if (change !== "closed") lp.close(); }
}
console.log(JSON.stringify({ cases }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)
check("delayed result identity and closed-viewer cases", result["cases"], 6)
