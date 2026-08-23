// Mirror of canvas.py. The pills show the resolved frame count and WxH live, so
// the same rules have to exist on both sides. canvas.py is the source of truth —
// it is what the sampler actually runs — and any change there belongs here too.

export const CANVAS_MULTIPLE = 32;
export const FPS = 24;

export const NATIVE_SHORT_EDGE = 768;
export const NATIVE_MAX_PIXELS = 768 * 1344;
export const MIN_SHORT_EDGE = 384;
// The slider's ceiling rather than a claim about the weights — see canvas.py.
// Everything above NATIVE_SHORT_EDGE is off-distribution and the pill says so.
export const MAX_SHORT_EDGE = 2048;

export const MIN_RATIO = 9 / 16;
export const MAX_RATIO = 21 / 9;

// Order matters: this is the order the ratio popover lists them in.
export const ASPECT_PRESETS = [
  ["16:9", 16 / 9],
  ["4:3", 4 / 3],
  ["1:1", 1],
  ["3:4", 3 / 4],
  ["9:16", 9 / 16],
  ["21:9", 21 / 9],
];

// What the weights were *trained* on, not a limit — see canvas.py. 17n+5 is the
// only hard rule; this pair exists so the pill can say when you have left the
// distribution, which is a different statement from "you cannot".
export const TRAINED_MIN_FRAMES = 124;
export const TRAINED_MAX_FRAMES = 362;
export const MIN_SECONDS = 1;
export const MAX_SECONDS = 60;

export function legalFrameCounts() {
  const counts = [];
  for (let n = 5; n <= MAX_SECONDS * FPS + 17; n += 17) counts.push(n);
  return counts;
}

export const isTrainedLength = (frames) =>
  frames >= TRAINED_MIN_FRAMES && frames <= TRAINED_MAX_FRAMES;

// Whole UI seconds -> nearest legal frame count. There is no 6.00 s H3 video;
// the pill lies pleasantly and this is where the truth is recovered.
export function framesForSeconds(seconds) {
  const target = Math.round(seconds * FPS);
  let best = null;
  for (const n of legalFrameCounts()) {
    if (best === null || Math.abs(n - target) < Math.abs(best - target)) best = n;
  }
  return best;
}

export function secondsForFrames(frames) {
  return frames / FPS;
}

// A reference's own length -> the card duration that lands nearest it. Not
// Math.round: legal counts are 0.708 s apart and whole seconds do not cover
// that grid, so a matched card carries a fractional duration_s — see canvas.py
// for the arithmetic and the 6.6 s case that argues for it.
export function matchSeconds(seconds) {
  const clamped = Math.min(MAX_SECONDS, Math.max(MIN_SECONDS, Number(seconds)));
  return Math.round(secondsForFrames(framesForSeconds(clamped)) * 100) / 100;
}

export function clampRatio(ratio) {
  if (ratio < MIN_RATIO) return [MIN_RATIO, true];
  if (ratio > MAX_RATIO) return [MAX_RATIO, true];
  return [ratio, false];
}

function snap(value) {
  return Math.max(CANVAS_MULTIPLE, Math.floor(value / CANVAS_MULTIPLE + 0.5) * CANVAS_MULTIPLE);
}

export function resolveCanvas(ratio, shortEdge) {
  const [clamped] = clampRatio(ratio);
  const edge = Math.max(MIN_SHORT_EDGE, Math.min(MAX_SHORT_EDGE, Math.round(shortEdge)));
  const maxPixels = NATIVE_MAX_PIXELS * (edge / NATIVE_SHORT_EDGE) ** 2;

  let width, height;
  if (clamped >= 1) { width = edge * clamped; height = edge; }
  else { width = edge; height = edge / clamped; }

  if (width * height > maxPixels) {
    const scale = Math.sqrt(maxPixels / (width * height));
    width *= scale;
    height *= scale;
  }

  width = snap(width);
  height = snap(height);

  // Independent rounding can push the area back over the cap; step the long
  // axis down rather than hand the model a latent it was not trained to hold.
  while (width * height > maxPixels && Math.max(width, height) > CANVAS_MULTIPLE) {
    if (width >= height) width -= CANVAS_MULTIPLE;
    else height -= CANVAS_MULTIPLE;
  }
  return [width, height];
}

export function describeRatio(ratio) {
  let best = ASPECT_PRESETS[0];
  for (const preset of ASPECT_PRESETS) {
    if (Math.abs(preset[1] - ratio) < Math.abs(best[1] - ratio)) best = preset;
  }
  return best[0];
}
