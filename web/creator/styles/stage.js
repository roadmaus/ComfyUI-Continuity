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
     render is a chip of text in an otherwise empty box.

     A column, and it has to say display: the media row below is flex 1, and
     that is what stretches it to the card's height — the height the picture then
     fills. Without it the row is auto-height, the media's height 100% resolves
     against nothing and falls back to the file's own size, and the preview sits
     in the corner at whatever the decoder happened to produce. taeh3 decodes at
     ~480px and hid that for as long as it was the only preview there was;
     latent2rgb decodes the latent itself, which is 30x17 on an LTX canvas. */
  position: relative; height: 100%; min-width: 240px;
  display: flex; flex-direction: column; min-height: 0;
  border-radius: 16px; overflow: hidden;
  background: var(--mmc-media-bg); border: 1px solid var(--mmc-line);
  box-shadow: 0 8px 30px var(--mmc-shadow-soft);
}
/* The same running halo Comfy paints around the executing node: litegraph's
   "running" stroke style is a 3px line centered on a path 6px outside the node,
   covering 4.5–7.5px out. outline-offset 4.5px puts our 3px outline over the
   same band, so node and card keep the same silhouette while it runs — without
   it the card read as shorter than the node for the whole render. The ground,
   not the node's status green: the card is not reporting progress, only holding
   its edge, so this wants the colour behind the card rather than a colour of its
   own. It was a literal black for as long as that ground was black. */
.mmc-stage[data-state="sampling"] { outline: 3px solid var(--mmc-bg); outline-offset: 4.5px; }
/* The card's *width* is the picture's shape at the node's height. Shrink-to-fit
   cannot work it out — a parent's max-content width comes from the image's
   intrinsic width and ignores any cap on its height — so the one fact CSS cannot
   derive is measured off the media by Stage.setAspect and handed back here.
   Without it the card sat at its 240px floor whatever it held and letterboxed
   the picture inside, which is invisible while the preview decodes at roughly
   the render's own shape and glaring the moment it decodes a 30x17 latent. The
   dock states this for itself, on its own terms — this one is the satellite's. */
.mmc-satellite .mmc-stage { aspect-ratio: var(--mmc-media-ar, auto); }
.mmc-stage-media { flex: 1; min-height: 0; display: flex; }
.mmc-stage-img, .mmc-stage-video {
  height: 100%; width: auto; min-height: 0; object-fit: contain;
  /* Until the media reports its size the card would be a sliver; until it is
     absurdly wide it may be as wide as it likes. Both bounds in graph units. */
  min-width: 240px; max-width: 1200px;
  display: block; background: var(--mmc-media-bg);
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
  font-size: calc(11px * var(--mmc-type)); font-variant-numeric: tabular-nums;
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
  color: var(--mmc-text); border-radius: 999px; padding: 3px 9px;
  background: var(--mmc-scrim-2); border: 1px solid var(--mmc-line);
  white-space: nowrap;
}
.mmc-stage-chip.warn {
  color: var(--mmc-warn); border-color: color-mix(in srgb, var(--mmc-warn) 40%, transparent);
  white-space: normal; text-align: left;
}
/* The step count, while there are steps. Scoped to the left side so the accent
   lands on what is counting and not on the clock beside it. */
.mmc-stage[data-state="sampling"] .mmc-stage-side:not(.end) .mmc-stage-chip:last-child {
  color: var(--mmc-accent); border-color: color-mix(in srgb, var(--mmc-accent) 35%, transparent);
}
/* Which segment the steps belong to — first in the row, before the count it is
   the context for. */
.mmc-stage-segment { font-weight: 500; }
/* The readout swallows the pointer so the finished video's controls stay
   reachable under it; its one real button opts back in. */
.mmc-stage-gallery {
  pointer-events: auto; cursor: pointer; font: inherit;
}
.mmc-stage-gallery:hover { border-color: var(--mmc-edge-2); background: var(--mmc-scrim-3); }

/* --- the weights control -------------------------------------------------- */
/* A required file nobody has picked. The same warm orange the resolution slider
   uses past 768 and for the same reason: it is a fact about the render, said
   before you queue instead of after. */
.mmc-weights.missing { border-color: color-mix(in srgb, var(--mmc-warn) 45%, transparent); color: var(--mmc-warn); }
.mmc-weights.missing:hover:not(:disabled) { border-color: color-mix(in srgb, var(--mmc-warn) 75%, transparent); }
/* Wider with a device column: "cuda:0" beside a folder-qualified filename needs
   the room, and a popover that ellipsises both tells you neither. */
.mmc-weights-pop { width: 380px; padding: 8px; }
.mmc-weight-row {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 3px 4px; box-sizing: border-box;
}
.mmc-weight-name { flex: none; color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); width: 112px; }
.mmc-weight-file, .mmc-weight-device {
  background: none; border: 0; border-radius: 8px; padding: 5px 8px;
  color: var(--mmc-text); font-family: inherit; font-size: calc(13px * var(--mmc-type));
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
.mmc-weight-row.missing .mmc-weight-file { color: var(--mmc-warn); }
/* The device this field's weights load on. Quiet at "auto", which is the answer
   on every single-GPU machine and most multi-GPU ones; lit once it is a decision
   somebody made, because which card a thing is on is worth seeing at a glance. */
.mmc-weight-device {
  flex: none; width: 72px; text-align: center; font-size: calc(11px * var(--mmc-type));
  color: var(--mmc-off); border: 1px solid transparent;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.mmc-weight-device.pinned {
  color: var(--mmc-blue); border-color: color-mix(in srgb, var(--mmc-blue) 35%, transparent);
}
/* A standing route, which is a decision rather than a default — and the reason
   the checkpoint below it may be greyed out. */
.mmc-weight-file.forced { color: var(--mmc-accent); }
/* A checkpoint the route has taken out of play. Still listed, so the setting is
   not thrown away, but visibly out of the run — the same treatment an idle LoRA
   gets on the asset row. */
.mmc-weight-row.idle { opacity: .45; }
/* The heading over an upscale backend's files. A hairline and a name, because
   what follows is a second architecture's weights rather than more of the
   piece's own — the rule is the whole of the device, and the note beside it
   says why the rows are there in one clause. */
.mmc-weight-group {
  display: flex; align-items: baseline; gap: 8px;
  margin: 8px 0 2px; padding: 8px 4px 0;
  border-top: 1px solid var(--mmc-line);
}
.mmc-weight-group-name { color: var(--mmc-text); font-size: calc(12px * var(--mmc-type)); }
.mmc-weight-group-note {
  color: var(--mmc-off); font-size: calc(11px * var(--mmc-type));
  min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
/* A route that will be refused: forcing FL2VA on a generation with references.
   Said on the badge rather than at queue time. */
.mmc-mode.bad { color: var(--mmc-warn); border-color: color-mix(in srgb, var(--mmc-warn) 45%, transparent); }
.mmc-mode.bad b, .mmc-mode.bad .mmc-pin { color: inherit; }

`;
