"""A Blockout run is one scene, even while the live bench is edited.

    python3 tests/test_blockout_snapshot.py

Exercises the real run/path/raster code, replacing only DOM, PNG encoding and
HTTP. Frame checksums and the submitted sidecar must match an unedited control.
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
const url = pathToFileURL(path.join(process.cwd(), "web/creator/blockout.js"));
const source = readFileSync(url, "utf8").replace("class Bench {", "export class Bench {")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, url).href}"`);
const { Bench } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const { api } = await import("./../scripts/api.js");
let written, uploaded, active, mutate, captures;
api.fetchApi = async (route, options) => {
  if (route.endsWith("/write")) written = JSON.parse(options.body);
  if (route === "/upload/image") uploaded = options.body.get("image").name;
  return { ok: true, json: async () => route.endsWith("/write")
    ? { path: "continuity/blockout/test.mp4", kind: "video" }
    : route === "/upload/image" ? { name: uploaded, subfolder: "continuity/blockout" } : { held: 24 } };
};
NodeClass.prototype.getContext = function () {
  const canvas = this;
  return { createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }),
    putImageData: (image) => { canvas.rgba = Array.from(image.data); } };
};
NodeClass.prototype.toBlob = function (callback) {
  captures.push(this.rgba.reduce((sum, value) => sum + value, 0));
  if (captures.length === 1 && mutate) {
    assert.equal(active.busy, true);
    active.setPass("lines");
    active.marks.forEach((mark) => { mark.x += 8; });
    active.shot.x += 8;
    active.objects.forEach((piece) => { piece.x += 8; piece.word = "changed object"; });
    active.setDuration(2);
    active.aspect = "1:1";
  }
  queueMicrotask(() => callback(new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" })));
};
async function sample(edit, still = false) {
  written = null; uploaded = null; captures = []; mutate = edit;
  const bench = active = new Bench({}, () => {});
  bench.overlay = { isConnected: false };
  for (const name of ["paintBench", "paintBox", "paint", "paintResult", "paintFoot"]) bench[name] = () => {};
  bench.frameSize = () => ({ w: 32, h: 18 });
  bench.setDuration(1);
  bench.addPiece("box");
  bench.objects[0].word = "original object";
  bench.marks = still ? [] : [{ ...bench.shot, x: 0 }, { ...bench.shot, x: 1 }];
  const originalScene = bench.scene();
  const originalWords = bench.said();
  const originalPass = { ...bench.passOf() };
  await bench.run();
  assert.equal(bench.error, null);
  return { frames: captures, written, uploaded, result: bench.result,
    originalScene, originalWords, originalPass, busy: bench.busy };
}
const control = await sample(false);
const edited = await sample(true);
assert.equal(control.frames.length, 24);
assert.deepEqual(edited.frames, control.frames, "mid-run edits must not change later frame pixels");
assert.deepEqual(edited.written.scene, control.written.scene, "sidecar describes the rendered snapshot");
assert.equal(edited.written.op, "depth");
assert.equal(control.result.words, control.originalWords);
assert.equal(control.result.opId, control.originalPass.opId);
assert.equal(edited.result, null, "old run cannot reopen attachment doors for the edited scene");
assert.equal(edited.busy, false);
const stillControl = await sample(false, true);
const stillEdited = await sample(true, true);
assert.deepEqual(stillEdited.frames, stillControl.frames);
assert.equal(stillEdited.uploaded, "blockout-depth.png", "still filename belongs to the rendered pass");
assert.equal(stillControl.result.words, stillControl.originalWords);
assert.equal(stillEdited.result, null);
console.log(JSON.stringify({ frames: control.frames.length, cases: 4 }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)
check("one-second guide", result["frames"], 24)
check("still and video snapshot controls", result["cases"], 4)
