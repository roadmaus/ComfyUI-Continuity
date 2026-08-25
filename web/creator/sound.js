// Where a track sits on the piece, in frames. The lane's arithmetic and nothing
// else — `soundlane.js` is the surface that draws it.
//
// Split for the same reason `canvas.js` is split from the components that use
// it: this half mirrors `sound.py` and `test_sound_mirror` runs the two against
// each other under bare node, where ComfyUI's modules do not exist. A single
// file that also imported the picker and the waveform could not be loaded
// there, and the mirror is the thing that keeps the two halves honest.
//
// `sound.py` is authoritative. Anything below that reads like a judgement call
// about frames is a judgement call already made over there.

import * as S from "./state.js";
import { rulesFor } from "./canvas.js";

// The shortest block worth having. Mirrors `sound.MIN_SECONDS`, and the same
// number `trim.js` calls MIN_SEGMENT — a handle that can be dragged into
// nothing is a trap, and the two surfaces have to agree or the lane can make a
// block the trim modal refuses to reopen.
export const MIN_SECONDS = 0.25;

/**
 * A time on the piece's clock -> the frame it lands on.
 *
 * Mirrors `sound.at_frame`, and is deliberately **not** `framesForSeconds`:
 * that one snaps to the legal generation counts, because it answers "how long
 * may one pass be". A lane position answers where in the finished file a cue
 * starts, and the finished file has no grid on it. Snapping a downbeat to the
 * generation grid would move it by up to a third of a second for no reason
 * anybody could see.
 */
export const atFrame = (seconds, rules) =>
  Math.max(0, Math.round((Number(seconds) || 0) * rules.fps));

/** The lane's blocks, in play order. Mirrors `sound.parse`, minus the refusals:
 *  this side prevents the states that one raises on rather than reporting them,
 *  so a lane that reaches the compiler has already been kept legal here. */
export function lane(timeline) {
  const rules = rulesFor(S.pieceFamily(timeline));
  return (timeline.sound ?? [])
    .map((entry, index) => ({
      index,
      filename: entry.filename,
      at: atFrame(entry.at_s, rules),
      frames: Math.max(1, atFrame((entry.out_s ?? 0) - (entry.in_s ?? 0), rules)),
      in_s: Number(entry.in_s) || 0,
      out_s: Number(entry.out_s) || 0,
    }))
    .sort((a, b) => a.at - b.at || a.filename.localeCompare(b.filename));
}

/** Every block and every gap, end to end, covering the whole piece. Mirrors
 *  `sound.band` — including that the gaps come back as parts of the same list
 *  rather than being left for each reader to infer from the holes. */
export function band(blocks, totalFrames) {
  const parts = [];
  let at = 0;
  for (const block of blocks) {
    if (block.at > at) parts.push({ at, frames: block.at - at, block: null });
    parts.push({ at: block.at, frames: block.frames, block });
    at = block.at + block.frames;
  }
  if (at < totalFrames) parts.push({ at, frames: totalFrames - at, block: null });
  return parts;
}

/**
 * The imitation references attached to cards, placed under the cards they
 * belong to.
 *
 * Not blocks, and drawn differently for it. What these say to the model is
 * "sound like this", and where they sit in time is decided by which card they
 * are attached to — so they are shown at that card's extent and cannot be
 * dragged. A `copy` is excluded: that one is the signal itself, which is what
 * the lane proper is for, and it appears as a pinned block instead.
 */
export function pinned(timeline, windows) {
  const found = [];
  (timeline.segments ?? []).forEach((segment, index) => {
    const window = windows[S.passIndexOf(timeline, index)];
    if (!window) return;
    for (const asset of segment.assets ?? []) {
      if (asset.role !== "reference" || S.scopeKind(asset) !== "audio") continue;
      found.push({
        segment: index,
        asset,
        take: S.takes(asset),
        at: window.at,
        frames: window.frames,
      });
    }
  });
  return found;
}

