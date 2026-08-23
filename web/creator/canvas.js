// Mirror of canvas.py. The pills show the resolved frame count and WxH live, so
// the same rules have to exist on both sides. canvas.py is the source of truth —
// it is what the sampler actually runs — and any change there belongs here too.
//
// The math is family-neutral and every function takes the rules that drive it;
// the numbers are a family's. H3_RULES is MiniMax H3's set, the mirror of
// canvas.py's `H3`, and the default everywhere — the same numbers the family's
// manifest serves, which is what will let another family hand its own rules in
// without this file changing.

export const H3_RULES = {
  multiple: 32,
  fps: 24,
  fpsFixed: true,
  nativeShortEdge: 768,
  nativeMaxPixels: 768 * 1344,
  minShortEdge: 384,
  // The slider's ceiling rather than a claim about the weights — see canvas.py.
  // Everything above nativeShortEdge is off-distribution and the pill says so.
  maxShortEdge: 2048,
  minRatio: 9 / 16,
  maxRatio: 21 / 9,
  // Order matters: this is the order the ratio popover lists them in.
  aspects: [
    ["16:9", 16 / 9],
    ["4:3", 4 / 3],
    ["1:1", 1],
    ["3:4", 3 / 4],
    ["9:16", 9 / 16],
    ["21:9", 21 / 9],
  ],
  // Legal frame counts are step*n + offset — the temporal packing. What the
  // weights were *trained* on is not a limit; the trained pair exists so the
  // pill can say when you have left the distribution, which is a different
  // statement from "you cannot".
  frameStep: 17,
  frameOffset: 5,
  trainedMinFrames: 124,
  trainedMaxFrames: 362,
  minSeconds: 1,
  maxSeconds: 60,
};

// The H3 rules under their historic names — what every H3-owned reader
// imports today, bound to the one family this pack ships.
export const CANVAS_MULTIPLE = H3_RULES.multiple;
export const FPS = H3_RULES.fps;
export const NATIVE_SHORT_EDGE = H3_RULES.nativeShortEdge;
export const NATIVE_MAX_PIXELS = H3_RULES.nativeMaxPixels;
export const MIN_SHORT_EDGE = H3_RULES.minShortEdge;
export const MAX_SHORT_EDGE = H3_RULES.maxShortEdge;
export const MIN_RATIO = H3_RULES.minRatio;
export const MAX_RATIO = H3_RULES.maxRatio;
export const ASPECT_PRESETS = H3_RULES.aspects;
export const TRAINED_MIN_FRAMES = H3_RULES.trainedMinFrames;
export const TRAINED_MAX_FRAMES = H3_RULES.trainedMaxFrames;
export const MIN_SECONDS = H3_RULES.minSeconds;
export const MAX_SECONDS = H3_RULES.maxSeconds;

export function legalFrameCounts(rules = H3_RULES) {
  const counts = [];
  const top = rules.maxSeconds * rules.fps + rules.frameStep;
  for (let n = rules.frameOffset; n <= top; n += rules.frameStep) counts.push(n);
  return counts;
}

export const isTrainedLength = (frames, rules = H3_RULES) =>
  frames >= rules.trainedMinFrames && frames <= rules.trainedMaxFrames;

// Whole UI seconds -> nearest legal frame count. There is no 6.00 s H3 video;
// the pill lies pleasantly and this is where the truth is recovered.
export function framesForSeconds(seconds, rules = H3_RULES) {
  const target = Math.round(seconds * rules.fps);
  let best = null;
  for (const n of legalFrameCounts(rules)) {
    if (best === null || Math.abs(n - target) < Math.abs(best - target)) best = n;
  }
  return best;
}

export function secondsForFrames(frames, rules = H3_RULES) {
  return frames / rules.fps;
}

// A reference's own length -> the card duration that lands nearest it. Not
// Math.round: legal counts are 0.708 s apart and whole seconds do not cover
// that grid, so a matched card carries a fractional duration_s — see canvas.py
// for the arithmetic and the 6.6 s case that argues for it.
export function matchSeconds(seconds, rules = H3_RULES) {
  const clamped = Math.min(rules.maxSeconds, Math.max(rules.minSeconds, Number(seconds)));
  return Math.round(secondsForFrames(framesForSeconds(clamped, rules), rules) * 100) / 100;
}

export function clampRatio(ratio, rules = H3_RULES) {
  if (ratio < rules.minRatio) return [rules.minRatio, true];
  if (ratio > rules.maxRatio) return [rules.maxRatio, true];
  return [ratio, false];
}

function snap(value, rules) {
  const grid = rules.multiple;
  return Math.max(grid, Math.floor(value / grid + 0.5) * grid);
}

export function resolveCanvas(ratio, shortEdge, rules = H3_RULES) {
  const [clamped] = clampRatio(ratio, rules);
  const edge = Math.max(rules.minShortEdge, Math.min(rules.maxShortEdge, Math.round(shortEdge)));
  const maxPixels = rules.nativeMaxPixels * (edge / rules.nativeShortEdge) ** 2;

  let width, height;
  if (clamped >= 1) { width = edge * clamped; height = edge; }
  else { width = edge; height = edge / clamped; }

  if (width * height > maxPixels) {
    const scale = Math.sqrt(maxPixels / (width * height));
    width *= scale;
    height *= scale;
  }

  width = snap(width, rules);
  height = snap(height, rules);

  // Independent rounding can push the area back over the cap; step the long
  // axis down rather than hand the model a latent it was not trained to hold.
  while (width * height > maxPixels && Math.max(width, height) > rules.multiple) {
    if (width >= height) width -= rules.multiple;
    else height -= rules.multiple;
  }
  return [width, height];
}

export function describeRatio(ratio, rules = H3_RULES) {
  let best = rules.aspects[0];
  for (const preset of rules.aspects) {
    if (Math.abs(preset[1] - ratio) < Math.abs(best[1] - ratio)) best = preset;
  }
  return best[0];
}
