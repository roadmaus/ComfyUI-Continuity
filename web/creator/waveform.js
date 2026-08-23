// Peak data for the segment editor's timeline.
//
// Decoded on the server (see preview.py) and fetched as a small JSON array. It
// used to be done here with the Web Audio API, which meant downloading the whole
// file — up to 120 MB — into an ArrayBuffer just to draw a few hundred pixels of
// waveform, alongside the <video> element loading the same file for playback.
// That is what made opening the editor on a large clip feel like a hang.
//
// Best effort by design: an undecodable container or a silent clip resolves to
// null and the timeline simply stays plain. A missing waveform must never stop
// you trimming.

import { fetchPeaks } from "./api.js";

// path -> Promise<Float32Array|null>. Re-opening the editor on the same clip,
// which is the normal way to adjust a segment, must not ask again.
const CACHE = new Map();

export function peaks(path) {
  if (!CACHE.has(path)) CACHE.set(path, fetchPeaks(path).catch(() => null));
  return CACHE.get(path);
}

/** Paint peaks into a canvas at its current CSS size, one column per pixel. */
export function draw(canvas, data, colour) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  if (!data?.length) return;

  context.fillStyle = colour;
  const middle = height / 2;
  for (let x = 0; x < width; x += 1) {
    const from = Math.floor((x / width) * data.length);
    const to = Math.max(from + 1, Math.floor(((x + 1) / width) * data.length));
    let peak = 0;
    for (let at = from; at < to && at < data.length; at += 1) {
      if (data[at] > peak) peak = data[at];
    }
    const bar = Math.max(1, peak * (height - 4));
    context.fillRect(x, middle - bar / 2, 1, bar);
  }
}
