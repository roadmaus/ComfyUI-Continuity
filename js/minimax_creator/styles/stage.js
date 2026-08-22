// The satellite, its stage, and the weights control.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- the satellite and its stage ------------------------------------------ */
/*
 * The picture: the preview while it samples, the finished video after, the error
 * if there was one — and nothing whatsoever before any of that. It floats in a
 * satellite card beside the node (satellite.js), which sets translate+scale from
 * the node's graph position every frame — so inside here one CSS px is one graph
 * unit, and the card's height is the node's. Width comes from the picture: the
 * media keeps its own aspect at full card height, so a portrait render makes a
 * portrait card.
 */
.mmc-satellite {
  position: fixed; left: 0; top: 0; z-index: 100;
  transform-origin: 0 0; display: none;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
  color: var(--mmc-text);
}
.mmc-satellite.showing { display: block; }

.mmc-stage {
  /* The card's own floor matters when there is no media to size it — a failed
     render is a chip of text in an otherwise empty box. */
  position: relative; height: 100%; min-width: 240px;
  flex-direction: column; min-height: 0;
  border-radius: 16px; overflow: hidden;
  background: #000; border: 1px solid var(--mmc-line);
  box-shadow: 0 8px 30px rgba(0,0,0,.45);
}
/* The same running halo Comfy paints around the executing node: litegraph's
   "running" stroke style is a 3px line centered on a path 6px outside the node,
   covering 4.5–7.5px out. outline-offset 4.5px puts our 3px outline over the
   same band, so node and card keep the same silhouette while it runs — without
   it the card read as shorter than the node for the whole render. Black, not
   the node's status green: the card is not reporting progress, only holding
   its edge. */
.mmc-stage[data-state="sampling"] { outline: 3px solid #000; outline-offset: 4.5px; }
.mmc-stage-media { flex: 1; min-height: 0; display: flex; }
.mmc-stage-img, .mmc-stage-video {
  height: 100%; width: auto; min-height: 0; object-fit: contain;
  /* Until the media reports its size the card would be a sliver; until it is
     absurdly wide it may be as wide as it likes. Both bounds in graph units. */
  min-width: 240px; max-width: 1200px;
  display: block; background: #000;
}

/* Progress, as a rule along the bottom edge of the picture rather than a bar of
   its own. The step count is already overlaid; a second reading of the same
   number in a different shape would be decoration. */
.mmc-stage-rule {
  position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
  background: var(--mmc-accent);
  transform-origin: left center; transform: scaleX(0);
  opacity: 0; transition: transform .3s linear, opacity .2s ease;
  pointer-events: none;
}
/*
 * Over the picture, not under it: a caption row would be height the picture
 * could have had.
 *
 * **One kind of object across the whole row.** It used to hold two: the Gallery
 * was a pill and everything beside it was bare text on a gradient scrim, so a
 * finished render carried a dark band across its bottom third to make three
 * words legible. Every chip now brings its own small ground, which is what let
 * the scrim go — the picture ends where the picture ends.
 *
 * Two sides, laid out by the row rather than by what happens to be in it: the
 * left says what this is, the right is the clock. See renderReadout — the point
 * is that the clock does not move when it stops.
 */
.mmc-stage-readout {
  position: absolute; left: 0; right: 0; bottom: 0;
  display: flex; align-items: flex-end; justify-content: space-between; gap: 10px;
  padding: 10px; pointer-events: none;
  font-size: 11px; font-variant-numeric: tabular-nums;
}
.mmc-stage-readout:empty { display: none; }
/* Wrapping, and upwards: a row of hand-off chips on a narrow portrait render is
   three lines, and they belong above the picture's edge rather than off it. */
.mmc-stage-side {
  display: flex; flex-wrap: wrap-reverse; align-items: flex-end; gap: 6px;
  min-width: 0;
}
.mmc-stage-side.end { justify-content: flex-end; }
.mmc-stage-chip {
  color: #ededed; border-radius: 999px; padding: 3px 9px;
  background: rgba(0,0,0,.55); border: 1px solid var(--mmc-line);
  white-space: nowrap;
}
.mmc-stage-chip.warn {
  color: #e0743c; border-color: rgba(224,116,60,.4);
  white-space: normal; text-align: left;
}
/* The step count, while there are steps. Scoped to the left side so the accent
   lands on what is counting and not on the clock beside it. */
.mmc-stage[data-state="sampling"] .mmc-stage-side:not(.end) .mmc-stage-chip:last-child {
  color: var(--mmc-accent); border-color: rgba(240,166,60,.35);
}
/* Which segment the steps belong to — first in the row, before the count it is
   the context for. */
.mmc-stage-segment { font-weight: 500; }
/* The readout swallows the pointer so the finished video's controls stay
   reachable under it; its one real button opts back in. */
.mmc-stage-gallery {
  pointer-events: auto; cursor: pointer; font: inherit;
}
.mmc-stage-gallery:hover { border-color: #7a7a7a; background: rgba(0,0,0,.75); }

/* --- the weights control -------------------------------------------------- */
/* A required file nobody has picked. The same warm orange the resolution slider
   uses past 768 and for the same reason: it is a fact about the render, said
   before you queue instead of after. */
.mmc-weights.missing { border-color: rgba(224,116,60,.45); color: #e0743c; }
.mmc-weights.missing:hover:not(:disabled) { border-color: rgba(224,116,60,.75); }
/* Wider with a device column: "cuda:0" beside a folder-qualified filename needs
   the room, and a popover that ellipsises both tells you neither. */
.mmc-weights-pop { width: 380px; padding: 8px; }
.mmc-weight-row {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 3px 4px; box-sizing: border-box;
}
.mmc-weight-name { flex: none; color: var(--mmc-dim); font-size: 12px; width: 112px; }
.mmc-weight-file, .mmc-weight-device {
  background: none; border: 0; border-radius: 8px; padding: 5px 8px;
  color: var(--mmc-text); font-family: inherit; font-size: 13px;
  text-align: left; cursor: pointer;
}
.mmc-weight-file:hover, .mmc-weight-device:hover { background: var(--mmc-surface-2); }
/* Names run to a folder-qualified minimax/h3_ref2va_fp8.safetensors, and the end
   of one is the part that identifies it — so this ellipsises from the *left*
   and keeps the filename rather than the folder. */
.mmc-weight-file {
  flex: 1; min-width: 0; overflow: hidden; white-space: nowrap;
  text-overflow: ellipsis; direction: rtl;
}
.mmc-weight-file.empty { color: var(--mmc-off); direction: ltr; }
.mmc-weight-row.missing .mmc-weight-file { color: #e0743c; }
/* The device this field's weights load on. Quiet at "auto", which is the answer
   on every single-GPU machine and most multi-GPU ones; lit once it is a decision
   somebody made, because which card a thing is on is worth seeing at a glance. */
.mmc-weight-device {
  flex: none; width: 72px; text-align: center; font-size: 11px;
  color: var(--mmc-off); border: 1px solid transparent;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.mmc-weight-device.pinned {
  color: var(--mmc-blue); border-color: rgba(47,123,246,.35);
}
/* A standing route, which is a decision rather than a default — and the reason
   the checkpoint below it may be greyed out. */
.mmc-weight-file.forced { color: var(--mmc-accent); }
/* A checkpoint the route has taken out of play. Still listed, so the setting is
   not thrown away, but visibly out of the run — the same treatment an idle LoRA
   gets on the asset row. */
.mmc-weight-row.idle { opacity: .45; }
/* A route that will be refused: forcing FL2VA on a generation with references.
   Said on the badge rather than at queue time. */
.mmc-mode.bad { color: #e0743c; border-color: rgba(224,116,60,.45); }
.mmc-mode.bad b, .mmc-mode.bad .mmc-pin { color: inherit; }

`;
