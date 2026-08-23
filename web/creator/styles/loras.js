// The LoRA manager grid.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- lora manager --------------------------------------------------------- */
/* Wider cells than the asset grid: a card carries a name, a base model, trigger
   words and, once active, three controls. */
.mmc-lora-grid { grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
/* Which folder under models/loras is being browsed. A native select: the list
   is as deep as the user's collection and the browser's own scrolling popup
   handles a hundred entries better than anything built here would. */
.mmc-folder {
  flex: none; max-width: calc(260px * var(--mmc-type)); height: calc(40px * var(--mmc-type)); border-radius: 12px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); color: var(--mmc-text);
  padding: 0 10px; font-size: calc(13px * var(--mmc-type)); font-family: inherit; cursor: pointer; outline: none;
}
/* Sits after the last card and spans the grid: how many are still unrendered
   while scrolling, and what the server left out when it stops. */
.mmc-grid-note {
  grid-column: 1/-1; color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type));
  padding: 18px 0 4px; text-align: center; line-height: 1.5;
}
.mmc-lora {
  display: flex; flex-direction: column; border-radius: 12px; overflow: hidden;
  background: var(--mmc-surface); border: 2px solid transparent;
}
.mmc-lora[aria-selected="true"] { border-color: var(--mmc-strong); }
/* 4:3, and aspect-ratio rather than .mmc-cell's height:0 + padding-bottom.
   The cell IS a grid item, so its percentage padding sizes its own row. The art
   is a child of one, and percentage padding contributes nothing to a grid item's
   intrinsic height — the row would be sized for the body alone and the card,
   which clips, would swallow the picture whole. aspect-ratio gives a real height
   that counts. Every child is still positioned out of flow, so a showcase clip
   cannot push the box taller than its ratio. */
.mmc-lora-art {
  position: relative; aspect-ratio: 4 / 3; cursor: pointer; background: var(--mmc-float);
}
.mmc-lora-art img, .mmc-lora-art canvas, .mmc-lora-art video, .mmc-lora-art .mmc-cell-fallback {
  position: absolute; inset: 0; width: 100%; height: 100%; box-sizing: border-box;
}
.mmc-lora-art img, .mmc-lora-art canvas, .mmc-lora-art video { object-fit: cover; display: block; }
.mmc-lora-art:focus-visible { outline: 2px solid var(--mmc-edge-2); outline-offset: -2px; }
.mmc-lora[aria-selected="true"] .mmc-check { display: flex; }
.mmc-lora-body { display: flex; flex-direction: column; gap: 4px; padding: 10px 11px 11px; }
.mmc-lora-name {
  font-size: calc(13px * var(--mmc-type)); color: var(--mmc-text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-lora-sub {
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-lora-words {
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-accent); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-lora-ctl {
  display: flex; flex-direction: column; gap: 7px;
  margin-top: 8px; padding-top: 9px; border-top: 1px solid var(--mmc-line);
}
.mmc-lora-row { display: flex; justify-content: space-between; align-items: center; font-size: calc(11px * var(--mmc-type)); }
.mmc-lora-label { color: var(--mmc-dim); }
.mmc-lora-strength { color: var(--mmc-text); font-variant-numeric: tabular-nums; }
/* The card's mute, in the strength row: label left, this and the readout right.
   Pressed is lit the way a chosen trigger chip is — same "on" in the same
   panel — except that what is lit here is the LoRA being *off*. */
.mmc-lora-mute {
  margin-left: auto; margin-right: 8px; padding: 1px 7px; border-radius: 8px;
  background: none; border: 1px solid var(--mmc-line); color: var(--mmc-off);
  font-family: inherit; font-size: calc(10px * var(--mmc-type)); cursor: pointer;
}
.mmc-lora-mute:hover { color: var(--mmc-text); }
.mmc-lora-mute[aria-pressed="true"] {
  background: color-mix(in srgb, var(--mmc-warn) 16%, transparent); border-color: transparent; color: var(--mmc-warn);
}
.mmc-lora-ctl input[type="range"] { width: 100%; accent-color: var(--mmc-blue); margin: 0; }
.mmc-lora-idle { font-size: calc(10px * var(--mmc-type)); color: var(--mmc-warn); }
.mmc-seg {
  display: flex; border: 1px solid var(--mmc-line); border-radius: 9px; overflow: hidden;
}
.mmc-seg-btn {
  flex: 1; padding: 5px 0; background: none; border: 0; border-right: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(10px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-seg-btn:last-child { border-right: 0; }
.mmc-seg-btn:hover { color: var(--mmc-text); }
.mmc-seg-btn[aria-pressed="true"] { background: color-mix(in srgb, var(--mmc-blue) 22%, transparent); color: var(--mmc-text); }

.mmc-trig-box { display: flex; flex-direction: column; gap: 6px; }
.mmc-trigs { display: flex; flex-wrap: wrap; gap: 4px; }
.mmc-trigs:empty { display: none; }
/* Off is an outline, on is filled: a sidecar word you have not taken should not
   look like one you have. */
.mmc-trig {
  padding: 2px 8px; border-radius: 8px; cursor: pointer; font-family: inherit;
  font-size: calc(10px * var(--mmc-type)); max-width: 100%; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; background: none; border: 1px solid var(--mmc-line);
  color: var(--mmc-off);
}
.mmc-trig:hover { color: var(--mmc-text); }
.mmc-trig[aria-pressed="true"] {
  background: color-mix(in srgb, var(--mmc-accent) 14%, transparent); border-color: transparent; color: var(--mmc-accent);
}
/* Yours rather than the sidecar's — same weight in the prompt, but you can tell
   which list a word came from. */
.mmc-trig.own { border: 1px dashed color-mix(in srgb, var(--mmc-accent) 50%, transparent); background: none; }
.mmc-trig-add {
  height: calc(24px * var(--mmc-type)); border-radius: 8px; background: var(--mmc-float); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); padding: 0 8px; font-size: calc(11px * var(--mmc-type)); font-family: inherit; outline: none;
  width: 100%; box-sizing: border-box;
}
.mmc-trig-add:focus { border-color: var(--mmc-blue); }

`;
