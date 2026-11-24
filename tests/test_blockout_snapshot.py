"""A guide written from the bench is one scene, even while the bench is edited.

    python3 tests/test_blockout_snapshot.py

Exercises the real `writeGuide`, path and raster code, replacing only DOM, PNG
encoding and HTTP. The set and the staging are copied before the first frame,
so editing them while the frames are drawn and sent changes neither the pixels
nor the scene written beside the clip. One camera mark writes a still.
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
import assert from "node:assert/strict";
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const B = await import("./web/creator/blockout.js");
const S = await import("./web/creator/state.js");
const { api } = await import("./../scripts/api.js");
let written, uploaded, mutate, captures, piece;
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
    const shot = piece.segments[0];
    shot.staging.pass = "lines";
    shot.staging.camera.forEach((mark) => { mark.x += 8; });
    piece.sets[0].objects.forEach((thing) => { thing.x += 8; thing.word = "changed object"; });
  }
  queueMicrotask(() => callback(new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" })));
};
async function sample(edit, still = false) {
  written = null; uploaded = null; captures = []; mutate = edit;
  piece = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", aspect: "16:9", staging_pass: "depth",
    sets: [{ id: "s1", name: "Set", objects: [{ id: 1, kind: "block", x: 0, z: 4, word: "original object" }] }],
    segments: [{ prompt: "", duration_s: 1, assets: [], loras: [], set: "s1",
      staging: { camera: still ? [{ t: 0, x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }]
        : [{ t: 0, x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }, { t: 1, x: 1, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }] } }],
  }));
  const words = B.stagingWords(piece, 0);
  const result = await B.writeGuide(piece, 0);
  return { frames: captures, written, uploaded, result, words };
}
const control = await sample(false);
const edited = await sample(true);
assert.ok(control.frames.length >= 17 && control.frames.length <= 33, `frames ${control.frames.length}`);
assert.deepEqual(edited.frames, control.frames, "mid-run edits must not change later frame pixels");
assert.deepEqual(edited.written.scene, control.written.scene, "the scene beside the clip is the one drawn");
assert.equal(edited.written.op, "depth");
assert.equal(control.result.words, control.words);
assert.equal(edited.result.words, control.words);
assert.equal(control.result.opId, "depth");
assert.equal(control.result.kind, "video");
const back = S.sceneAsStaging(control.written.scene, { id: "again" });
assert.deepEqual(back.staging.camera.map((mark) => mark.t), [0, 1], "the scene reads back in at its own times");
const stillControl = await sample(false, true);
const stillEdited = await sample(true, true);
assert.deepEqual(stillEdited.frames, stillControl.frames);
assert.equal(stillEdited.uploaded, "blockout-depth.png", "still filename belongs to the drawn pass");
assert.equal(stillControl.result.kind, "image");
console.log(JSON.stringify({ frames: control.frames.length >= 17, cases: 4 }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)
check("a one-second guide is drawn frame by frame", result["frames"], True)
check("still and video snapshot controls", result["cases"], 4)
