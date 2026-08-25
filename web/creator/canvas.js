// Mirror of canvas.py's math. The pills show the resolved frame count and WxH
// live, so the same rules have to exist on both sides. canvas.py is the source
// of truth — it is what the sampler actually runs — and any change there
// belongs here too.
//
// The math is family-neutral and every function takes the rules that drive it;
// the numbers are a family's and arrive in its manifest. `rulesFrom` lifts a
// served canvas block into the shape the functions read, `rulesFor` names a
// family instead of a block, and VIDEO_RULES is the default family's set — the
// same `canvas.py` instance the manifest was built from, having travelled the
// route instead of being written down twice.
//
// **No function here defaults its rules, and there are no module constants.**
// Both existed — `rules = VIDEO_RULES`, and `FPS` / `NATIVE_SHORT_EDGE` /
// `ASPECT_PRESETS` beside them — and both are how a caller reached the default
// family's arithmetic without saying so. A piece on another family drew the
// wrong trained-length warning, the wrong aspect labels and the wrong canvas,
// silently, because the call still worked. Passing `rulesFor(piece.family)` is
// the whole fix and a required argument is what makes forgetting it fail.
// Mirrors canvas.py, which lost the same two things for the same reason.

import { DEFAULT_VIDEO_FAMILY, videoFamily } from "./manifest.js";

/** A manifest canvas block, in the shape the functions below read. */
export const rulesFrom = (block) => ({
  multiple: block.multiple,
  fps: block.fps.value,
  fpsFixed: block.fps.fixed,
  nativeShortEdge: block.native_short_edge,
  nativeMaxPixels: block.native_max_pixels,
  minShortEdge: block.min_short_edge,
  // The slider's ceiling rather than a claim about the weights — see canvas.py.
  // Everything above nativeShortEdge is off-distribution and the pill says so.
  maxShortEdge: block.max_short_edge,
  minRatio: block.min_ratio,
  maxRatio: block.max_ratio,
  // As [label, ratio] pairs, in the popover's order — the declaration's own.
  aspects: Object.entries(block.aspects),
  // Legal frame counts are step*n + offset — the temporal packing. What the
  // weights were *trained* on is not a limit; the trained pair exists so the
  // pill can say when you have left the distribution, which is a different
  // statement from "you cannot".
  frameStep: block.frames.step,
  frameOffset: block.frames.offset,
  trainedMinFrames: block.frames.trained_min,
  trainedMaxFrames: block.frames.trained_max,
  minSeconds: block.frames.min_seconds,
  maxSeconds: block.frames.max_seconds,
});

// One `Rules` object per family, built once. Every function below takes rules
// by identity-free value, but the readouts rebuild on every keystroke and
// `rulesFrom` would otherwise hand each of them a fresh object to walk.
const CACHE = new Map();

/** The canvas rules of the family a piece renders with — `piece.family`, or
 *  the default when it names none. The forgiving lookup is `videoFamily`'s;
 *  see there for why a saved blob's id is not trusted. */
export function rulesFor(id) {
  const manifest = videoFamily(id);
  if (!CACHE.has(manifest.id)) CACHE.set(manifest.id, rulesFrom(manifest.canvas));
  return CACHE.get(manifest.id);
}

export const VIDEO_RULES = rulesFor(DEFAULT_VIDEO_FAMILY);


export function legalFrameCounts(rules) {
  const counts = [];
  const top = rules.maxSeconds * rules.fps + rules.frameStep;
  for (let n = rules.frameOffset; n <= top; n += rules.frameStep) counts.push(n);
  return counts;
}

export const isTrainedLength = (frames, rules) =>
  frames >= rules.trainedMinFrames && frames <= rules.trainedMaxFrames;

// Mirrors canvas.feather_grid: the seam widths this family's video VAE can
// encode standalone, which is the frame grid again for the same reason — the
// VAE's temporal cycle. The single frame is always offered; three widths above
// it is what the picker has room for. H3's set is [1, 5, 22, 39] and LTX 2.5's
// is [1, 9, 17, 25], and borrowing one for the other is a seam that quietly
// stops being feathered — see canvas.py for the whole of why.
export function featherGrid(rules) {
  return [1, ...legalFrameCounts(rules).filter((n) => n > 1).slice(0, 3)];
}

// Whole UI seconds -> nearest legal frame count. There is no 6.00 s H3 video;
// the pill lies pleasantly and this is where the truth is recovered.
export function framesForSeconds(seconds, rules) {
  const target = Math.round(seconds * rules.fps);
  let best = null;
  for (const n of legalFrameCounts(rules)) {
    if (best === null || Math.abs(n - target) < Math.abs(best - target)) best = n;
  }
  return best;
}

export function secondsForFrames(frames, rules) {
  return frames / rules.fps;
}

// A reference's own length -> the card duration that lands nearest it. Not
// Math.round: legal counts are 0.708 s apart and whole seconds do not cover
// that grid, so a matched card carries a fractional duration_s — see canvas.py
// for the arithmetic and the 6.6 s case that argues for it.
export function matchSeconds(seconds, rules) {
  const clamped = Math.min(rules.maxSeconds, Math.max(rules.minSeconds, Number(seconds)));
  return Math.round(secondsForFrames(framesForSeconds(clamped, rules), rules) * 100) / 100;
}

export function clampRatio(ratio, rules) {
  if (ratio < rules.minRatio) return [rules.minRatio, true];
  if (ratio > rules.maxRatio) return [rules.maxRatio, true];
  return [ratio, false];
}

function snap(value, rules) {
  const grid = rules.multiple;
  return Math.max(grid, Math.floor(value / grid + 0.5) * grid);
}

export function resolveCanvas(ratio, shortEdge, rules) {
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

export function describeRatio(ratio, rules) {
  let best = rules.aspects[0];
  for (const preset of rules.aspects) {
    if (Math.abs(preset[1] - ratio) < Math.abs(best[1] - ratio)) best = preset;
  }
  return best[0];
}
