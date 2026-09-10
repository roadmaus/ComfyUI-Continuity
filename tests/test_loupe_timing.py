"""Seeking or playing footage updates both sides of the loupe comparison.

    python3 tests/test_loupe_timing.py

Uses the real Loupe and Trim with the shared DOM shim. Decoded-frame events are
delivered by hand; no video decoder or neural network runs.
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
NodeClass.prototype.getContext = function () {
  const canvas = this;
  return { drawImage: (media) => { canvas.lastPaintTime = media.currentTime; },
    clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fillRect() {}, fill() {}, closePath() {} };
};
NodeClass.prototype.pause = function () { this.paused = true; };
NodeClass.prototype.play = function () { this.paused = false; return Promise.resolve(); };
NodeClass.prototype.load = function () {};
const url = pathToFileURL(path.join(process.cwd(), "web/creator/loupe.js"));
const source = readFileSync(url, "utf8").replace("class Loupe {", "export class Loupe {")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, url).href}"`);
const { api } = await import("./../scripts/api.js");
const baseFetch = api.fetchApi.bind(api);
api.fetchApi = async (route, options) => {
  if (String(route).startsWith("/continuity/probe")) return {
    ok: true, json: async () => ({ width: 1920, height: 1080, duration: 12, has_audio: false }) };
  if (String(route).startsWith("/continuity/neural/of")) return {
    ok: true, json: async () => ({ ours: false, on: false, settings: null }) };
  return baseFetch(route, options);
};
const { Loupe } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const { NEURAL } = await import("./web/creator/manifest.js");
NEURAL.ready = true;
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
const fire = (node, event) => { for (const fn of node.listeners[event] ?? []) fn({}); };
let imageRequests = 0;
globalThis.Image = class { set src(value) { imageRequests++; } };
const lp = new Loupe({ source: { path: "clip.mp4 [input]", kind: "video" }, compare: true }, () => {});
lp.mount(); await flush();
try {
  Object.assign(lp.cutter.media, { currentTime: 0, videoWidth: 1920, videoHeight: 1080, duration: 12 });
  fire(lp.cutter.media, "loadedmetadata");
  fire(lp.cutter.media, "seeked");
  lp.twin = { path: "twin.mp4 [output]", kind: "video", on: true };
  lp.showTwin();
  Object.assign(lp.twinMedia, { currentTime: 0, videoWidth: 1920, videoHeight: 1080, duration: 12, seeking: false });
  fire(lp.twinMedia, "loadeddata");
  lp.cutter.media.currentTime = 5;
  fire(lp.cutter.media, "seeked");
  assert.equal(lp.picture.lastPaintTime, 5);
  assert.equal(lp.twinMedia.currentTime, 5, "scrub parks the twin at the same timestamp");
  fire(lp.twinMedia, "seeked");
  assert.equal(lp.twinCanvas.lastPaintTime, 5);
  // Coalesce playback changes while a seek is pending; the completion picks
  // up the latest source time rather than displaying an outdated seek result.
  lp.twinMedia.seeking = true;
  lp.cutter.media.currentTime = 6; lp.onFrame(lp.cutter.media);
  lp.cutter.media.currentTime = 7; lp.onFrame(lp.cutter.media);
  assert.equal(lp.twinMedia.currentTime, 5);
  lp.twinMedia.seeking = false;
  fire(lp.twinMedia, "seeked");
  assert.equal(lp.twinMedia.currentTime, 7);
  fire(lp.twinMedia, "seeked");
  assert.equal(lp.twinCanvas.lastPaintTime, 7);
  // Ordinary same-frame repaints must not invalidate a tile or launch a pass.
  lp.twin = null;
  lp.tile = { centre: [0.5, 0.5], side: 384 };
  lp.stale = false; lp.paintTile(); lp.paintRail();
  lp.onFrame(lp.cutter.media);
  assert.equal(lp.stale, false);
  lp.cutter.media.currentTime = 8;
  fire(lp.cutter.media, "seeked");
  assert.equal(lp.stale, true);
  assert.equal("disabled" in lp.rail.querySelector(".mmc-lp-run").attrs, false);
  assert.equal(imageRequests, 0, "transport never starts neural inference");
} finally { lp.close(); }
console.log(JSON.stringify({ checked: true }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)
check("seek, playback, pending seeks and tile invalidation", result["checked"], True)
