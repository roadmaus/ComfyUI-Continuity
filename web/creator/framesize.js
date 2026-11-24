// The render's frame, measured once for every view of a piece.
//
// The frame is a preset's ratio until the piece takes it from a picture or a
// clip (`state.timelineAspectSize`), and then it is that picture's ratio, which
// only a look at the file can tell. The reel, the timeline bar and the blockout
// all ask here, so the stage is drawn in the shape the render will have and not
// the preset's while a still says otherwise.

import { probe, viewUrl } from "./api.js";
import * as S from "./state.js";

/** filename -> {width, height}, null while a probe is out. Module-level so the
 *  modal bar and the node face — two views of the same strip — measure a file
 *  once between them. Clip cards never land here: they store their own size. */
export const ASPECT_SIZES = new Map();
// The source's own size; the framing is applied by whoever reads it — the
// cache is by file, and two chips can frame one file two ways.
export const aspectSizeOf = (asset) => ASPECT_SIZES.get(asset.filename) || null;

/** Everyone waiting on a file's size, by filename. */
const waiting = new Map();

function landed(filename, size) {
  if (size) ASPECT_SIZES.set(filename, size);
  for (const done of waiting.get(filename) ?? []) done();
  waiting.delete(filename);
}

/** Measure the pictures the timeline's canvas can follow: the resolved source
 *  (or segment 1's anchor under the auto rule), and with `all` every donor the
 *  aspect popover will list. Stills through an <img>, videos through the probe
 *  route; `onReady` re-renders when an answer lands. The backend re-reads the
 *  files at queue time — this is only so the bar can tell the truth early. */
export function probeAspectSizes(timeline, onReady, { all = false } = {}) {
  const want = [];
  if (all) {
    for (const segment of timeline.segments) {
      if (!S.isClip(segment)) want.push(...S.aspectDonors(segment));
    }
    for (const asset of timeline.assets ?? []) {
      if (asset.kind !== "audio" && !S.soundOnly(asset)) want.push(asset);
    }
  } else {
    // Just what the bar needs: ask timelineAspectSize what it would read, by
    // reading through a recording lookup.
    S.timelineAspectSize(timeline, (asset) => {
      want.push(asset);
      return aspectSizeOf(asset);
    });
  }
  const pending = [];
  for (const asset of want) {
    if (ASPECT_SIZES.has(asset.filename)) {
      if (ASPECT_SIZES.get(asset.filename) === null) pending.push(asset.filename);
      continue;
    }
    ASPECT_SIZES.set(asset.filename, null);
    pending.push(asset.filename);
    if (asset.kind === "video") {
      probe(asset.filename).then(({ width, height } = {}) => {
        landed(asset.filename, width && height ? { width, height } : null);
        if (width && height) onReady();
      }, () => landed(asset.filename, null));
      continue;
    }
    const measure = new Image();
    measure.onload = () => {
      landed(asset.filename, { width: measure.naturalWidth, height: measure.naturalHeight });
      onReady();
    };
    measure.onerror = () => landed(asset.filename, null);
    measure.src = viewUrl(asset.filename);
  }
  return pending;
}

/** Measure what the frame is read from, and resolve once it is known — or
 *  after `patience` ms, when the preset's ratio is all there is to go on. For
 *  what must be drawn in the right shape before it is written: a guide. */
export function measureFrame(timeline, patience = 4000) {
  const pending = probeAspectSizes(timeline, () => {});
  if (!pending.length) return Promise.resolve();
  return Promise.race([
    Promise.all(pending.map((filename) => new Promise((done) => {
      if (ASPECT_SIZES.get(filename) !== null) { done(); return; }
      waiting.set(filename, [...(waiting.get(filename) ?? []), done]);
    }))),
    new Promise((done) => setTimeout(done, patience)),
  ]);
}

/** The frame's ratio, width over height: the source's where the piece takes
 *  it from one and its size is known, else the preset's. */
export function frameRatio(timeline, rules) {
  const size = S.timelineAspectSize(timeline, aspectSizeOf);
  return size ? size.width / size.height
    : rules.aspects.find(([label]) => label === timeline.aspect)?.[1] ?? rules.aspects[0]?.[1] ?? 16 / 9;
}
