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
   which list a word came from. Two controls in one chip: the word toggles, and
   the ✕ forgets it. It needs both because a word of yours that is switched off
   is still a chip — there is no "click again and it is gone" left to be the way
   out, and without the ✕ a typo would sit under that LoRA forever. */
.mmc-trig.own {
  display: inline-flex; align-items: center; padding: 0;
  border: 1px dashed color-mix(in srgb, var(--mmc-accent) 50%, transparent);
  background: none; color: var(--mmc-off);
}
.mmc-trig.own.on {
  background: color-mix(in srgb, var(--mmc-accent) 14%, transparent); color: var(--mmc-accent);
}
.mmc-trig-word {
  background: none; border: 0; color: inherit; font-family: inherit; font-size: inherit;
  padding: 2px 3px 2px 8px; cursor: pointer; max-width: 140px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Quiet until wanted: forgetting a word is rarer than switching one off, and a
   row of ✕s would read as the chips' main business. */
.mmc-trig-forget {
  background: none; border: 0; color: inherit; font-family: inherit;
  font-size: calc(9px * var(--mmc-type)); line-height: 1; padding: 2px 6px 2px 2px;
  cursor: pointer; opacity: .4;
}
.mmc-trig-forget:hover { opacity: 1; color: var(--mmc-warn); }
.mmc-trig-add {
  height: calc(24px * var(--mmc-type)); border-radius: 8px; background: var(--mmc-float); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); padding: 0 8px; font-size: calc(11px * var(--mmc-type)); font-family: inherit; outline: none;
  width: 100%; box-sizing: border-box;
}
.mmc-trig-add:focus { border-color: var(--mmc-blue); }

/* The star, and the same quiet-until-hover rule the asset picker's has: an
   untouched grid should look untouched, but a set star stays lit. Steps left
   when the selection check needs the corner. */
.mmc-lora-star {
  position: absolute; top: 8px; right: 8px; width: 24px; height: 24px;
  display: none; align-items: center; justify-content: center;
  border: 0; border-radius: 50%; background: var(--mmc-scrim-2);
  color: var(--mmc-text); cursor: pointer; padding: 0;
}
.mmc-lora-art:hover .mmc-lora-star,
.mmc-lora-art:focus-visible .mmc-lora-star,
.mmc-lora-star.on { display: flex; }
.mmc-lora-star.on { color: var(--mmc-accent); }
.mmc-lora-star.on svg { fill: currentColor; }
.mmc-lora-star svg { width: 13px; height: 13px; }
.mmc-lora[aria-selected="true"] .mmc-lora-star { right: 36px; }

/* Where these settings came from, when it was not the file's own sidecar. */
.mmc-lora-memo { font-size: calc(10px * var(--mmc-type)); color: var(--mmc-dim); font-style: italic; }

/* The card the window was opened for. Lit, then let go of — a mark that stayed
   would become part of how the card looks rather than an answer to "which one
   did I click". */
.mmc-lora-found { border-color: var(--mmc-blue); }
.mmc-lora-found .mmc-lora-art { box-shadow: inset 0 0 0 2px var(--mmc-blue); }
@media (prefers-reduced-motion: no-preference) {
  .mmc-lora-found { animation: mmc-lora-found 1.6s ease-out; }
}
@keyframes mmc-lora-found {
  0%, 55% { border-color: var(--mmc-blue); }
  100% { border-color: transparent; }
}

/* --- saved stacks ---------------------------------------------------------- */
/* One column rather than the grid's cards: a stack is a name and a list of
   filenames, and both want the width to read on one line. Same bottom padding
   as the grid, which clears the floating Done bar. */
.mmc-stacks {
  flex: 1; overflow-y: auto; padding: 4px 24px 96px;
  display: flex; flex-direction: column; gap: 8px;
}
.mmc-stack, .mmc-stack-save {
  display: flex; align-items: center; gap: 14px; padding: 12px 16px;
  border-radius: 12px; background: var(--mmc-surface); border: 1px solid transparent;
}
/* Keeping one is the errand you arrive on this tab with, so it leads and is
   marked off from the shelf below it rather than sitting in the same list. */
.mmc-stack-save { border-color: var(--mmc-line); background: none; }
.mmc-stack-what, .mmc-stack-save-what { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.mmc-stack-title { font-size: calc(14px * var(--mmc-type)); color: var(--mmc-text); }
.mmc-stack-sub {
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-stack-name {
  flex: none; width: calc(200px * var(--mmc-type)); height: calc(36px * var(--mmc-type));
  border-radius: 10px; background: var(--mmc-float); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); padding: 0 12px; font-size: calc(13px * var(--mmc-type));
  font-family: inherit; outline: none;
}
.mmc-stack-name:focus { border-color: var(--mmc-blue); }
.mmc-stack .mmc-del { font-size: calc(12px * var(--mmc-type)); }

`;
