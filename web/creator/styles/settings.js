// The settings page.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- settings page -------------------------------------------------------- */
/* A sibling of the LoRA manager rather than a new species: same overlay, same
   head, same Done. Wider than it was, because a row is now a name and a set of
   buttons side by side rather than a card of options stacked under a heading —
   and the index down the left takes its own column. */
.mmc-settings { width: min(920px, 100%); height: min(700px, 100%); border-radius: calc(12px * var(--mmc-round)); }
.mmc-set-title { font-size: calc(15px * var(--mmc-type)); color: var(--mmc-strong); font-weight: 600; }
/* A shallow head: the title and the way out, and no band under it that the
   first row has to wait beneath. */
.mmc-settings .mmc-modal-head { gap: 16px; padding: 10px 24px; min-height: 48px; box-sizing: border-box; }
/* A bare glyph with a full hit target: a filled disc would be the one circle
   on a page of rounded rectangles. */
.mmc-settings .mmc-close { background: none; width: 36px; height: 36px; margin-right: -10px; color: var(--mmc-dim); }
.mmc-settings .mmc-close:hover { color: var(--mmc-strong); }
.mmc-set-body { display: grid; grid-template-columns: 200px 1fr; flex: 1; min-height: 0; }
/* The index: one press per group, the current one lifted. It follows the
   scroll rather than driving it — the page is one page, and the index only
   says where in it you are. The inventory is pushed a step below the four
   groups of settings, as it sits apart on the page. It starts level with the
   first row, so the two columns share a top edge. */
.mmc-set-index { display: flex; flex-direction: column; gap: 2px; padding: 20px 12px 16px 16px; }
/* The current group is a filled pill: the one lifted surface in the rail, and
   no accent — the amber is the answers', and the rail is not an answer. */
.mmc-set-ix {
  position: relative; text-align: left; padding: 0 12px; border-radius: calc(6px * var(--mmc-round)); border: 0; background: none;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(13px * var(--mmc-type)); font-weight: 500;
  cursor: pointer; line-height: 32px; height: 32px;
}
.mmc-set-ix:hover { color: var(--mmc-text); background: var(--mmc-wash); }
.mmc-set-ix[aria-current="true"] { color: var(--mmc-strong); background: var(--mmc-wash-2); }
.mmc-set-ix[aria-current="true"]::before {
  content: ""; position: absolute; left: 0; top: 8px; bottom: 8px; width: 2px; border-radius: calc(1px * var(--mmc-round));
  background: var(--mmc-accent);
}
.mmc-set-ix:focus-visible { outline: 2px solid var(--mmc-blue); outline-offset: -2px; }
/* The inventory is not a group of settings: a step of air sets it apart. */
.mmc-set-ix:last-child { margin-top: 20px; }
.mmc-set-page { overflow-y: auto; min-height: 0; padding: 0 24px 48px; }
/* A refusal, beside the title: the one place on a page this long that is
   always on screen. */
.mmc-set-problem { color: var(--mmc-warn); font-size: calc(12px * var(--mmc-type)); line-height: 1.45; flex: 1; }
.mmc-set-problem:empty { display: none; }
.mmc-set-wait { color: var(--mmc-dim); font-size: calc(13px * var(--mmc-type)); padding: 28px 0 24px; }

/* A group: its cards, each under a head. No boxes: the modal is the one border
   on the page, and inside it the grouping is done by the heads and the rules
   over them. */
.mmc-set-group { padding: 0; }
.mmc-set-card { padding: 0; }
/* The head over a run of rows: small tracked capitals in the text colour, 36
   of air above and 8 below, the same everywhere. No rule — the air is the
   separator, and a rule under a head would be two marks for one seam. */
.mmc-set-card-name {
  display: flex; align-items: baseline; gap: 10px;
  color: var(--mmc-dim); font-size: calc(10px * var(--mmc-type)); font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase; line-height: 1;
  padding: 32px 0 6px; margin: 0 0 6px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-set-group:first-child > .mmc-set-card:first-child > .mmc-set-card-name { padding-top: 18px; }
.mmc-set-card-under {
  color: var(--mmc-dim); font-weight: 400; letter-spacing: 0; text-transform: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11.5px * var(--mmc-type));
}
.mmc-set-card-desc {
  color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); line-height: 1.45;
  padding: 0 0 6px; max-width: 70ch;
}
.mmc-set-card-foot {
  color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.5;
  padding: 10px 0 0; max-width: 78ch;
}
.mmc-set-card-foot code {
  font-family: ui-monospace, Menlo, monospace; font-size: calc(11px * var(--mmc-type));
}

/* A row: the name on the left, the control on the right, on one shared axis.
   Every row is the same 44px whatever it holds — a field, a track of answers,
   a button — and the reading that belongs to a name (crf 23, 112%) sits on the
   name's own line rather than pushing the row taller. What a row wants to say
   under the control (a store's size, a warning) is the one thing that adds
   height, and it is added under, never between. */
.mmc-set-row {
  display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 0 20px;
  align-items: center; min-height: 40px; padding: 0;
}
.mmc-set-what { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.mmc-set-name { font-size: calc(13px * var(--mmc-type)); font-weight: 500; color: var(--mmc-text); white-space: nowrap; }
/* The reading in force — crf 23, 8 GB, Extracted — at the far right of the
   row, so the readouts stack into one column down the page. */
.mmc-set-hint {
  color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-variant-numeric: tabular-nums;
}
.mmc-set-ctl {
  display: flex; align-items: center; justify-content: flex-end; gap: 12px; min-width: 0;
  justify-self: stretch; min-height: 40px;
}
/* A field is the one control that takes the column: it has nothing to be
   right-aligned against. */
.mmc-set-ctl > .mmc-neural-field { flex: 1; }
.mmc-set-note {
  grid-column: 2; color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.5;
  max-width: 72ch; padding: 0 0 8px;
}
.mmc-set-note .over { color: var(--mmc-warn); }
.mmc-set-more { grid-column: 2; padding-top: 4px; }
.mmc-set-more .mmc-set-hint { max-width: 78ch; }

/* The answers: one track, one segment pressed. A choice, not a tab — the
   pressed one is a solid amber block with dark text, and that block is the
   only amber on the page besides the rail's mark. The track is a wash with no
   border: the pressed block is the chrome. */
.mmc-set-seg { display: flex; align-items: center; gap: 8px; }
.mmc-set-seg-row {
  display: inline-flex; gap: 2px; padding: 2px; border-radius: calc(15px * var(--mmc-round));
  background: var(--mmc-bg); border: 1px solid var(--mmc-line);
}
.mmc-set-seg-opt {
  display: flex; padding: 0; border: 0; background: none; color: var(--mmc-dim); font-family: inherit;
  font-size: calc(12px * var(--mmc-type)); white-space: nowrap; cursor: pointer;
}
.mmc-set-seg-in {
  display: inline-block; height: calc(26px * var(--mmc-type)); line-height: calc(26px * var(--mmc-type));
  padding: 0 14px; border-radius: calc(13px * var(--mmc-round));
}
/* A button carrying a picture of its option in front of the word. */
.mmc-set-seg-marked { display: inline-flex; align-items: center; gap: 7px; padding-left: 10px; }
.mmc-set-seg-opt:hover:not(:disabled) { color: var(--mmc-text); }
.mmc-set-seg-opt[aria-pressed="true"] { color: var(--mmc-text); }
.mmc-set-seg-opt[aria-pressed="true"] .mmc-set-seg-in { background: var(--mmc-surface-3); }
.mmc-set-seg-opt:focus-visible { outline: none; }
.mmc-set-seg-opt:focus-visible .mmc-set-seg-in { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-set-seg-opt:disabled { cursor: default; }
.mmc-set-seg.off .mmc-set-seg-opt { color: var(--mmc-off); }
.mmc-set-seg.off .mmc-set-seg-opt[aria-pressed="true"] { color: var(--mmc-dim); }
/* A number on a scale: a step down, the value in mono, a step up. */
.mmc-set-stepper {
  display: inline-flex; align-items: center; height: calc(30px * var(--mmc-type)); border-radius: calc(15px * var(--mmc-round));
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line); padding: 0 6px;
}
.mmc-set-step {
  width: 26px; height: 100%; border: 0; border-radius: calc(13px * var(--mmc-round)); background: none; color: var(--mmc-text);
  font-family: inherit; font-size: calc(14px * var(--mmc-type)); cursor: pointer;
}
.mmc-set-step:hover:not(:disabled) { color: var(--mmc-strong); }
.mmc-set-step:disabled { color: var(--mmc-off); cursor: default; }
.mmc-set-step-val {
  min-width: 6ch; text-align: center; color: var(--mmc-strong); font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(12px * var(--mmc-type));
}
/* The unit after the track — GB, px — in the reading type. */
.mmc-set-unit { color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.mmc-set-clear { margin-left: 6px; }

/* The one button the page has, wherever a press stands beside a field or a
   count: a hairline box in the text colour, quiet until hovered. */
.mmc-set-reset {
  height: calc(30px * var(--mmc-type)); padding: 0 14px; background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  border-radius: calc(15px * var(--mmc-round)); color: var(--mmc-text); font-family: inherit; font-size: calc(12.5px * var(--mmc-type));
  cursor: pointer; white-space: nowrap;
}
.mmc-set-reset:hover:not(:disabled) { background: var(--mmc-surface-3); color: var(--mmc-strong); }
.mmc-set-reset:disabled { cursor: default; color: var(--mmc-off); }
/* Inline in a note it is a word, not a box. */
.mmc-set-note .mmc-set-reset { height: auto; padding: 0; border: 0; color: var(--mmc-text); }
.mmc-set-note .mmc-set-reset:hover { background: none; text-decoration: underline; }

/* A destination: the family's name, the field beside it, the reading under
   both. The same grid the setting rows use, so the shelves line up with the
   quality row above them — a folder is one more answer per family. */
.mmc-set-dest {
  display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 0 20px;
  align-items: center; min-height: 40px; padding: 0;
}
.mmc-set-dest-head { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.mmc-set-dest-name { font-size: calc(13px * var(--mmc-type)); font-weight: 500; color: var(--mmc-text); }
.mmc-set-dest .mmc-set-reset { margin-left: auto; height: 22px; padding: 0 9px; background: none; border-color: transparent; color: var(--mmc-off); font-size: calc(11.5px * var(--mmc-type)); }
.mmc-set-dest .mmc-set-reset:hover { border-color: var(--mmc-line); color: var(--mmc-text); background: none; }
/* One box to the column's right edge: the output folder ghosted before the
   path, the counter and the extension after it, the path itself editable
   between. The box wears the border; the field inside it wears none. */
.mmc-set-path {
  display: flex; align-items: center; gap: 0; min-width: 0; justify-self: stretch; height: 30px;
  padding: 0 12px; border: 1px solid var(--mmc-line); border-radius: calc(15px * var(--mmc-round)); background: var(--mmc-surface);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(12px * var(--mmc-type));
  cursor: text;
}
.mmc-set-path:focus-within { border-color: var(--mmc-accent); }
.mmc-set-path:has(.bad) { border-color: var(--mmc-warn); }
.mmc-set-path .mmc-out-ghost { color: var(--mmc-off); white-space: nowrap; flex: none; font-size: inherit; }
/* The suffix runs straight on from the stem; the box's remaining width is the
   path's to grow into. */
.mmc-set-path::after { content: ""; flex: 1 1 0; }
.mmc-set-dest .mmc-out-field {
  margin: 0; flex: 0 1 auto; min-width: 4ch; padding: 0; border: 0; border-radius: 0; background: none;
  font-size: inherit; font-weight: 400; line-height: 28px; height: 28px; color: var(--mmc-text);
  /* One line, scrolling under the caret rather than wrapping: a path that
     folds onto a second line reads as two paths. */
  white-space: pre; overflow-x: auto;
}
.mmc-set-dest .mmc-out-field:focus, .mmc-set-dest .mmc-out-field.bad { border: 0; outline: none; }
.mmc-set-dest .mmc-out-problem { grid-column: 2; padding: 2px 2px 8px; }
/* The token chips exist while the destination is being edited and not
   otherwise: at rest the card is a field per family and its reading, not
   sixteen buttons. :focus-within keeps them up while a chip itself is the click. */
.mmc-set-dest .mmc-out-tokens { display: none; grid-column: 2; padding: 2px 0 8px; }
.mmc-set-dest:focus-within .mmc-out-tokens { display: flex; }

/* The DLSS 5 refiner: the path in the same box the folders use, the one press
   after it, the verdict under both. */
.mmc-neural-field { flex: 1; min-width: 0; }
.mmc-neural-row { display: flex; gap: 8px; align-items: center; }
.mmc-neural-path {
  flex: 1; min-width: 0; height: 30px; padding: 0 12px; border-radius: calc(15px * var(--mmc-round)); box-sizing: border-box;
  border: 1px solid var(--mmc-line); background: var(--mmc-surface); color: var(--mmc-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(12px * var(--mmc-type));
  text-overflow: ellipsis;
}
.mmc-neural-path:focus { outline: none; border-color: var(--mmc-accent); }
.mmc-neural-line { display: block; padding: 6px 0 8px; color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; }
.mmc-neural-verdict {
  padding: 6px 0 8px; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-dim);
}
.mmc-neural-verdict.ok { color: var(--mmc-accent); }
.mmc-neural-verdict.bad { color: var(--mmc-warn); }

/* Narrow: the index turns into a row of presses above the page, and a row's
   control drops under its name. */
@media (max-width: 720px) {
  .mmc-set-body { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
  .mmc-set-index { flex-direction: row; flex-wrap: wrap; border-right: 0; border-bottom: 1px solid var(--mmc-line); padding: 10px 12px; }
  .mmc-set-ix:last-child { margin-top: 0; margin-left: auto; }
  .mmc-set-row, .mmc-set-dest { grid-template-columns: 1fr; }
  .mmc-set-ctl { justify-self: start; max-width: 100%; }
  .mmc-set-seg-row { max-width: 100%; flex-wrap: wrap; }
  .mmc-set-note { grid-column: 1; }
  .mmc-set-dest .mmc-out-problem, .mmc-set-dest .mmc-out-tokens { grid-column: 1; }
}


/* --- stored data ---------------------------------------------------------- */
/* The inventory, as a table: the name, what is behind it in the value column,
   and the press. One line per row, so the group reads as "what does this pack
   have of mine" without pressing anything; what a row holds waits on the
   pointer. The count is right-aligned against the button so the numbers stack
   into a column. */
.mmc-zone-row {
  display: grid; grid-template-columns: 1fr auto auto; gap: 0 16px;
  align-items: center; min-height: 40px; padding: 0; border-bottom: 1px solid var(--mmc-line);
}
.mmc-zone-row:last-child { border-bottom: 0; }
.mmc-zone-what { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.mmc-zone-name { font-size: calc(13px * var(--mmc-type)); font-weight: 500; color: var(--mmc-text); }
.mmc-zone-note { color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; max-width: 62ch; }
.mmc-zone-held {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
  font-variant-numeric: tabular-nums; white-space: nowrap; text-align: right; min-width: 4ch;
}
/* A row holding nothing goes quiet all the way across, its press disabled
   and still there: the columns hold whatever the rows hold. */
.mmc-zone-row[data-empty="true"] .mmc-zone-name,
.mmc-zone-row[data-empty="true"] .mmc-zone-held { color: var(--mmc-off); }

.mmc-zone-go {
  height: calc(30px * var(--mmc-type)); padding: 0 14px; border-radius: calc(15px * var(--mmc-round));
  border: 1px solid var(--mmc-line); background: var(--mmc-surface-2);
  color: var(--mmc-text); font-family: inherit; font-size: calc(12px * var(--mmc-type));
  white-space: nowrap; cursor: pointer;
  /* Wide enough for "Really remove?" from the start, so arming a row does not
     shove the count beside it sideways. */
  min-width: calc(112px * var(--mmc-type));
}
.mmc-zone-go:hover:not(:disabled) { color: var(--mmc-warn); border-color: var(--mmc-warn); }
.mmc-zone-go:disabled { color: var(--mmc-off); border-color: var(--mmc-line); cursor: not-allowed; }
/* Armed is the only red on the page. The gravity belongs to the second press —
   a page that is red before you have touched it has spent the warning early. */
.mmc-zone-go.armed,
.mmc-zone-go.armed:hover {
  background: var(--mmc-bad-solid); color: var(--mmc-strong); border-color: transparent;
}
.mmc-zone-all { width: auto; min-width: 0; margin: 6px 0 0; height: 30px; padding: 0 14px; }
@media (max-width: 520px) {
  .mmc-zone-row { grid-template-columns: 1fr auto; }
  .mmc-zone-what { grid-column: 1 / -1; }
}
`;
