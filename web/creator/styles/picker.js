// Picker modal, shelves, organize mode.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- picker modal --------------------------------------------------------- */
.mmc-overlay {
  position: fixed; inset: 0; z-index: 1400; background: var(--mmc-scrim-2);
  display: flex; align-items: center; justify-content: center; padding: 40px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
}
.mmc-modal {
  background: var(--mmc-float); border: 1px solid var(--mmc-line); border-radius: 22px;
  width: min(1100px, 100%); height: min(760px, 100%);
  display: flex; flex-direction: column; color: var(--mmc-text); overflow: hidden;
  box-shadow: 0 30px 80px var(--mmc-shadow);
}
.mmc-modal-head {
  display: flex; align-items: center; gap: 22px; padding: 20px 24px 14px;
  border-bottom: 1px solid var(--mmc-line);
}
.mmc-tab {
  background: none; border: 0; padding: 4px 0; color: var(--mmc-dim);
  font-size: calc(17px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-tab[aria-selected="true"] { color: var(--mmc-strong); font-weight: 500; }
.mmc-close {
  margin-left: auto; width: calc(34px * var(--mmc-type)); height: calc(34px * var(--mmc-type)); border-radius: 50%;
  background: var(--mmc-surface-2); border: 0; color: var(--mmc-text); cursor: pointer; font-size: calc(16px * var(--mmc-type));
}
.mmc-modal-bar { display: flex; gap: 12px; padding: 16px 24px; align-items: center; }
.mmc-search {
  flex: 1; height: calc(40px * var(--mmc-type)); border-radius: 12px; background: var(--mmc-surface);
  border: 1px solid var(--mmc-line); color: var(--mmc-text); padding: 0 14px;
  font-size: calc(14px * var(--mmc-type)); font-family: inherit; outline: none;
}
.mmc-upload {
  height: calc(40px * var(--mmc-type)); padding: 0 18px; border-radius: 20px; background: var(--mmc-ink); border: 0;
  color: var(--mmc-on-ink); font-size: calc(14px * var(--mmc-type)); font-weight: 500; font-family: inherit; cursor: pointer;
}
/* padding-bottom clears the floating Add/Cancel bar, which is positioned over
   the grid — without it the last row sits underneath and cannot be clicked. */
.mmc-grid {
  flex: 1; overflow-y: auto; padding: 4px 24px 96px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 14px;
  align-content: start;
  /* The grid is a flex child with a definite height, and implicit auto rows in
     one get fitted into that height rather than sized to their contents: with
     more rows than fit, every row is squeezed and the cards clip. max-content
     pins each row to the cards in it and lets the grid scroll, which is what
     overflow-y is here for. */
  grid-auto-rows: max-content;
}
/* The lazy-load sentinel takes a full grid row of its own: left in the normal
   flow it would sit beside the last cells and be "visible" from the start. */
.mmc-grid-sentinel { grid-column: 1 / -1; height: 1px; }
/* Page numbers for a folder too large to scroll end to end. Floats bottom-left,
   mirroring the foot bottom-right; hidden while everything fits on one page. */
.mmc-pager {
  position: absolute; bottom: 34px; left: 44px;
  display: flex; align-items: center; gap: 4px; padding: 8px 10px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 14px;
  box-shadow: 0 12px 32px var(--mmc-shadow-soft);
}
.mmc-page {
  min-width: calc(28px * var(--mmc-type)); height: calc(28px * var(--mmc-type)); padding: 0 6px; border-radius: 8px;
  background: none; border: 0; color: var(--mmc-dim);
  font-size: calc(12px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-page:hover { color: var(--mmc-text); background: var(--mmc-surface-2); }
.mmc-page[aria-current="true"] { background: var(--mmc-surface-3); color: var(--mmc-strong); }
.mmc-page:disabled { opacity: .35; cursor: default; background: none; }
.mmc-page-gap { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); padding: 0 2px; }
/* The square is height:0 + padding-bottom:100%, not aspect-ratio, and the media
   is positioned out of flow.
   With aspect-ratio and in-flow media, thumbnails rendered at their natural
   height and spilled over the rows above and below. Whatever the host page does
   to img/video sizing, an absolutely positioned child cannot push its
   container taller, so the cell stays square and clips. */
.mmc-cell {
  position: relative; display: block; box-sizing: border-box;
  height: 0; padding: 0 0 100%;
  border-radius: 12px; overflow: hidden;
  background: var(--mmc-surface); border: 2px solid transparent; cursor: pointer;
}
.mmc-cell[aria-selected="true"] { border-color: var(--mmc-strong); }
.mmc-cell:focus-visible { outline: none; border-color: var(--mmc-edge-2); }
.mmc-cell img, .mmc-cell video, .mmc-cell-fallback {
  position: absolute; inset: 0; width: 100%; height: 100%; box-sizing: border-box;
}
.mmc-cell img, .mmc-cell video { object-fit: cover; display: block; }
.mmc-cell-fallback {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 8px; color: var(--mmc-dim);
  font-size: calc(11px * var(--mmc-type)); padding: 8px; text-align: center; word-break: break-all;
}
.mmc-cell-fallback svg { width: 26px; height: 26px; stroke: currentColor; fill: none; stroke-width: 1.5; }
.mmc-check {
  position: absolute; top: 8px; right: 8px; width: 22px; height: 22px;
  border-radius: 50%; background: var(--mmc-blue); display: none;
  align-items: center; justify-content: center;
}
.mmc-cell[aria-selected="true"] .mmc-check { display: flex; }
.mmc-check::after {
  content: ""; width: 5px; height: 10px; border: solid var(--mmc-strong);
  border-width: 0 2px 2px 0; transform: rotate(45deg) translate(-1px,-1px);
}
/* The segment badge. Invisible until the cell is hovered, focused or selected,
   unless it carries a setting — an untouched grid should look untouched. */
.mmc-cell-trim {
  position: absolute; top: 8px; left: 8px; display: none;
  align-items: center; gap: 5px; max-width: calc(100% - 44px);
  padding: 3px 8px 3px 6px; border-radius: 9px; border: 1px solid var(--mmc-line);
  background: var(--mmc-scrim-3); color: var(--mmc-text);
  font-size: calc(10px * var(--mmc-type)); font-family: inherit; cursor: pointer;
  white-space: nowrap; overflow: hidden;
}
.mmc-cell:hover .mmc-cell-trim,
.mmc-cell:focus-visible .mmc-cell-trim,
.mmc-cell[aria-selected="true"] .mmc-cell-trim,
.mmc-cell-trim.set { display: flex; }
.mmc-cell-trim.set { background: color-mix(in srgb, var(--mmc-blue) 90%, transparent); border-color: transparent; }
.mmc-cell-trim:hover { background: var(--mmc-scrim-3); }
.mmc-cell-trim.set:hover { background: var(--mmc-blue); }
.mmc-cell-trim svg { width: 12px; height: 12px; flex: none; stroke: currentColor; fill: none;
  stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

/* --- shelves -------------------------------------------------------------- */
/* One row of places between the search bar and the grid, and one line of it
   whatever the folder holds: a trail on the left saying where you are, then a
   strip of the folders one step inside, scrolled sideways when there are more
   than fit. A wrapping list of every leaf path used to push the gallery off
   the bottom of a deeply filed output folder. The chips are the same family as
   the refiner's language row, so the picker keeps the node's vocabulary. */
.mmc-shelves { display: flex; gap: 10px; align-items: center; padding: 0 24px 12px; min-width: 0; }
.mmc-shelf {
  display: flex; align-items: center; gap: 6px; height: calc(30px * var(--mmc-type)); padding: 0 12px; flex: none;
  max-width: calc(220px * var(--mmc-type));
  border-radius: 15px; background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); font-family: inherit; cursor: pointer;
  transition: background .12s ease, color .12s ease, transform .12s ease;
}
.mmc-shelf-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* Turned a quarter: a chip with folders of its own is a way in, not a filter. */
.mmc-shelf-into { transform: rotate(-90deg); opacity: .5; margin-right: -3px; }

/* The trail. It never scrolls away — leaving a folder is one click from any
   depth — so it takes only the width it needs and truncates the long names. */
.mmc-crumbs { display: flex; align-items: center; gap: 1px; flex: 0 1 auto; min-width: 0; max-width: 45%; }
.mmc-crumb {
  display: block; max-width: calc(130px * var(--mmc-type)); padding: 0 8px; height: calc(28px * var(--mmc-type)); flex: 0 1 auto;
  border-radius: 8px; background: none; border: 0; color: var(--mmc-dim);
  font-size: calc(12px * var(--mmc-type)); font-family: inherit; cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-crumb:hover { color: var(--mmc-text); background: var(--mmc-surface-2); }
/* Where you are keeps its full name; the steps above it give up the width. */
.mmc-crumb[aria-selected="true"] { color: var(--mmc-text); font-weight: 600; flex: none; max-width: 220px; }
.mmc-crumb.drop { color: var(--mmc-text); background: var(--mmc-surface-3); box-shadow: inset 0 0 0 1px var(--mmc-accent); }
.mmc-crumb-sep { transform: rotate(-90deg); opacity: .35; flex: none; }
.mmc-crumbs + .mmc-shelf-strip { border-left: 1px solid var(--mmc-line); padding-left: 10px; }

/* The strip of what is inside. Fixed height, sideways scroll, and a fade on
   whichever end still has chips past it. */
.mmc-shelf-strip {
  display: flex; align-items: center; gap: 8px; flex: 1 1 0; min-width: 0;
  overflow-x: auto; overflow-y: hidden; padding: 3px 0;
  scrollbar-width: thin; scrollbar-color: var(--mmc-line) transparent;
  scroll-behavior: smooth; overscroll-behavior-x: contain;
}
.mmc-shelf-strip::-webkit-scrollbar { height: 5px; }
.mmc-shelf-strip::-webkit-scrollbar-thumb { background: var(--mmc-line); border-radius: 3px; }
.mmc-shelf-strip.more-r { mask-image: linear-gradient(90deg, #000 calc(100% - 40px), transparent); }
.mmc-shelf-strip.more-l { mask-image: linear-gradient(90deg, transparent, #000 40px); }
.mmc-shelf-strip.more-l.more-r {
  mask-image: linear-gradient(90deg, transparent, #000 40px, #000 calc(100% - 40px), transparent);
}
.mmc-shelf:hover { color: var(--mmc-text); background: var(--mmc-surface-3); }
.mmc-shelf[aria-selected="true"],
.mmc-shelf[aria-pressed="true"] { color: var(--mmc-bg); background: var(--mmc-accent); border-color: var(--mmc-accent); }
.mmc-shelf svg { width: 13px; height: 13px; flex: none; }
.mmc-shelf-n { font-size: calc(10px * var(--mmc-type)); opacity: .7; }
/* A chip with cargo hovering over it: swell and light up. The one place the
   picker spends motion. */
.mmc-shelf.drop {
  transform: scale(1.08); color: var(--mmc-text);
  background: var(--mmc-surface-3); border-color: var(--mmc-accent);
}
/* While a cell is riding, the chips announce they are drop targets. */
.mmc-modal.dragging .mmc-shelf { border-style: dashed; }
.mmc-shelf-new { font-size: calc(15px * var(--mmc-type)); line-height: 1; }
/* Throwing an empty shelf away. Quiet until it is armed — it sits at the end of
   a row you click along, and a red chip beside the "+" would read as the danger
   being the row rather than the second press. */
.mmc-shelf-drop { color: var(--mmc-dim); }
.mmc-shelf-drop:hover { color: var(--mmc-warn); border-color: var(--mmc-warn); }
.mmc-shelf-drop.armed,
.mmc-shelf-drop.armed:hover {
  color: var(--mmc-strong); background: var(--mmc-bad-solid); border-color: transparent;
}
.mmc-shelf-input {
  height: calc(30px * var(--mmc-type)); width: calc(140px * var(--mmc-type)); border-radius: 15px; background: var(--mmc-surface);
  border: 1px solid var(--mmc-accent); color: var(--mmc-text); padding: 0 12px;
  font-size: calc(12px * var(--mmc-type)); font-family: inherit; outline: none;
}

/* The star. Same quiet-until-hover rule as the segment badge — an untouched
   grid stays untouched — but a set star stays lit. Steps left when the
   selection check needs the corner. */
.mmc-cell-star {
  position: absolute; top: 8px; right: 8px; width: 24px; height: 24px;
  display: none; align-items: center; justify-content: center;
  border: 0; border-radius: 50%; background: var(--mmc-scrim-2);
  color: var(--mmc-text); cursor: pointer; padding: 0;
}
.mmc-cell:hover .mmc-cell-star,
.mmc-cell:focus-visible .mmc-cell-star,
.mmc-cell-star.on { display: flex; }
.mmc-cell-star.on { color: var(--mmc-accent); }
.mmc-cell-star.on svg { fill: currentColor; }
.mmc-cell-star svg { width: 13px; height: 13px; }
.mmc-cell[aria-selected="true"] .mmc-cell-star { right: 36px; }
/* Where a file lives — worth a caption only on the All shelf, where everything
   is mixed together. Sits above the name gradient. */
.mmc-cell-home {
  position: absolute; left: 6px; bottom: 22px; max-width: calc(100% - 12px);
  padding: 2px 8px; border-radius: 8px; background: var(--mmc-scrim-2);
  color: var(--mmc-text); font-size: calc(10px * var(--mmc-type)); pointer-events: none;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* --- organize mode --------------------------------------------------------- */
/* The bar toggle. Outlined next to the solid Upload button — a mode you enter,
   not an action you fire — and lit like a selected shelf while it is on. */
.mmc-organize {
  display: flex; align-items: center; gap: 7px; height: calc(40px * var(--mmc-type)); padding: 0 16px;
  border-radius: 20px; background: none; border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(14px * var(--mmc-type)); font-family: inherit; cursor: pointer;
  white-space: nowrap;
}
.mmc-organize:hover { color: var(--mmc-text); background: var(--mmc-surface-2); }
.mmc-organize[aria-pressed="true"] {
  color: var(--mmc-bg); background: var(--mmc-accent); border-color: var(--mmc-accent);
}
.mmc-organize svg { width: 14px; height: 14px; flex: none; }
/* Delete reads as danger from the start, and arming it turns it solid: the
   second press is the one that removes files. */
.mmc-del {
  background: none; border: 0; color: var(--mmc-warn); font-size: calc(14px * var(--mmc-type));
  font-family: inherit; cursor: pointer; white-space: nowrap;
}
.mmc-del:hover { color: var(--mmc-warn); }
.mmc-del:disabled { color: var(--mmc-off); cursor: not-allowed; }
.mmc-del.armed {
  height: 36px; padding: 0 14px; border-radius: 10px;
  background: var(--mmc-bad-solid); color: var(--mmc-strong);
}
.mmc-del.armed:hover { color: var(--mmc-strong); background: var(--mmc-bad-solid-hover); }
/* The Move to… popover, pinned above the footer it opened from. */
.mmc-move-menu {
  position: absolute; right: 44px; bottom: 100px; z-index: 5;
  display: flex; flex-direction: column; gap: 2px;
  min-width: 210px; max-height: 320px; overflow-y: auto; padding: 8px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 12px;
  box-shadow: 0 12px 32px var(--mmc-shadow-soft);
}
.mmc-move-opt {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-radius: 8px; background: none; border: 0; color: var(--mmc-text);
  font-size: calc(13px * var(--mmc-type)); font-family: inherit; cursor: pointer; text-align: left;
}
.mmc-move-opt:hover { background: var(--mmc-surface-3); }
.mmc-move-opt svg { width: 13px; height: 13px; flex: none; }
.mmc-move-menu .mmc-shelf-input { margin-top: 6px; width: auto; }


/* --- the sheet editor ------------------------------------------------------
   Its own modal over the picker: the composite exactly as the model will see
   it, the panels in layout order, and the button that takes it — see
   picker.openSheet. */
.mmc-plate-edit {
  width: min(760px, 94vw); max-height: 92vh; overflow: auto;
  display: flex; flex-direction: column; gap: 12px;
  padding: 18px 20px 16px; border-radius: 12px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line-3);
  box-shadow: 0 18px 50px rgba(0, 0, 0, .5);
}
.mmc-plate-title {
  font-size: calc(13px * var(--mmc-type)); color: var(--mmc-strong);
}
.mmc-plate-foot {
  display: flex; align-items: center; justify-content: flex-end; gap: 12px;
}
/* The stage: the canvas the shot generates at, on the family's own backdrop
   (set inline, because only the family knows which grey its panels sit on).
   The aspect ratio and the height cap are inline too — they come off the
   piece's canvas. Panels are absolutely placed children in the same fractions
   the bake reads, so what is arranged here is what the model is handed. */
.mmc-plate-stage-wrap { display: flex; justify-content: center; }
.mmc-plate-stage {
  position: relative; width: 100%; overflow: hidden;
  border: 1px solid var(--mmc-line-3); border-radius: 8px;
  touch-action: none;
}
.mmc-plate-stage.clicking .mmc-st-panel { cursor: crosshair; }
.mmc-st-panel {
  position: absolute; cursor: grab; user-select: none;
}
.mmc-st-panel:active { cursor: grabbing; }
.mmc-st-panel.picked { outline: 1px solid var(--mmc-blue); outline-offset: -1px; }
.mmc-st-img {
  width: 100%; height: 100%; object-fit: contain; display: block;
  pointer-events: none;
}
.mmc-st-no {
  position: absolute; top: 2px; left: 3px; padding: 0 4px; border-radius: 5px;
  background: var(--mmc-scrim-3); color: var(--mmc-strong);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
  font-size: calc(9.5px * var(--mmc-type)); line-height: 1.5;
  pointer-events: none;
}
/* The resize grip, on the panel's bottom-right corner. Visible on the picked
   panel only: nine of them at once is a stage of thumbtacks. */
.mmc-st-grip {
  position: absolute; right: -5px; bottom: -5px; width: 12px; height: 12px;
  border-radius: 3px; cursor: nwse-resize; display: none;
  background: var(--mmc-blue); border: 1px solid var(--mmc-strong);
}
.mmc-st-panel.picked .mmc-st-grip { display: block; }
/* A SAM click: where it landed on the picture, and which way it counts.
   Centred on the spot; blue keeps, red leaves out. */
.mmc-st-dot {
  position: absolute; width: 11px; height: 11px; padding: 0;
  transform: translate(-50%, -50%); border-radius: 50%; cursor: pointer;
  background: var(--mmc-blue); border: 1.5px solid var(--mmc-strong);
}
.mmc-st-dot.out { background: var(--mmc-bad-solid); }
/* The editor's own tools: click-to-pick, forget clicks, auto-arrange. */
.mmc-plate-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mmc-tool.on { border-color: var(--mmc-blue); color: var(--mmc-strong); }
.mmc-plate-say {
  padding: 0 14px; text-align: center; color: var(--mmc-text);
  font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45;
  text-shadow: 0 1px 3px rgba(0, 0, 0, .8);
}
.mmc-plate-say.bad { color: var(--mmc-bad); }
/* Laying out: a rule that sweeps the bottom edge of the frame. A picture being
   composited is not an indeterminate wait for something elsewhere, it is this
   frame filling in — so the sign of it belongs on the frame. */
.mmc-plate-scan {
  position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
  background: linear-gradient(90deg, transparent, var(--mmc-blue), transparent);
  animation: mmc-plate-sweep 1.1s ease-in-out infinite;
}
@keyframes mmc-plate-sweep {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
@media (prefers-reduced-motion: reduce) {
  .mmc-plate-scan { animation: none; opacity: .6; }
}
/* What the sheet is, in numbers: panels, the grid they landed in, the canvas it
   was built at. Tabular figures so the line does not shuffle sideways as the
   numbers change under it. */
.mmc-plate-caliper {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums; letter-spacing: .04em;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-dim);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-height: 1em;
}
.mmc-plate-strip {
  display: flex; align-items: center; gap: 8px; overflow-x: auto; padding-bottom: 4px;
}
.mmc-pl-cell {
  position: relative; flex: none; width: 62px; height: 62px; border-radius: 8px;
  overflow: hidden; border: 1px solid var(--mmc-line-2); background: var(--mmc-surface-2);
}
.mmc-pl-cell.cut { border-color: var(--mmc-blue); }
.mmc-pl-cell.picked { outline: 1px solid var(--mmc-blue); outline-offset: 1px; }
.mmc-pl-thumb { width: 100%; height: 100%; object-fit: cover; display: block; }
/* Which cell of the sheet this is. The number is the citation — panel 3 in the
   caption is this one — so it is set in the same tabular face the caliper is. */
.mmc-pl-no {
  position: absolute; top: 2px; left: 3px; padding: 0 4px; border-radius: 5px;
  background: var(--mmc-scrim-3); color: var(--mmc-strong);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
  font-size: calc(9.5px * var(--mmc-type)); line-height: 1.5;
}
.mmc-pl-cut {
  position: absolute; bottom: 3px; left: 3px; width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center; padding: 0;
  border: 0; border-radius: 6px; cursor: pointer;
  background: var(--mmc-scrim-3); color: var(--mmc-faint);
}
.mmc-pl-cut svg { width: 12px; height: 12px; }
.mmc-pl-cut:hover { color: var(--mmc-text); }
.mmc-pl-cut.on { background: var(--mmc-blue); color: var(--mmc-strong); }
.mmc-pl-x {
  position: absolute; top: 2px; right: 3px; width: 18px; height: 18px;
  display: flex; align-items: center; justify-content: center; padding: 0;
  border: 0; border-radius: 5px; cursor: pointer;
  background: var(--mmc-scrim-3); color: var(--mmc-faint);
  font-size: calc(10px * var(--mmc-type)); font-family: inherit;
}
.mmc-pl-x:hover { color: var(--mmc-strong); background: var(--mmc-bad-solid); }
/* A panel is dragged to rearrange, and the cursor says so. */
.mmc-pl-cell { cursor: grab; }
/* Paired: this grid cell is a panel of the connected sheet, and the number is
   where it sits — the numbering the sheet editor and the caption share. */
.mmc-cell-sheet {
  position: absolute; top: 8px; left: 8px; padding: 0 5px; border-radius: 5px;
  background: var(--mmc-blue); color: var(--mmc-strong);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
  font-size: calc(9.5px * var(--mmc-type)); line-height: 1.6;
  pointer-events: none;
}

/* --- the scissors on the cell ----------------------------------------------
   The chip that cuts a picture where it is picked, and the smaller button
   under it that opens the subject view. Same appearance grammar as the star:
   hidden until the cell is hovered, except that a pressed chip stays — a cut
   cell is showing a cutout, and the sign of why must not vanish with the
   pointer. */
.mmc-cell-cut, .mmc-cell-subject {
  position: absolute; top: 8px; left: 8px; width: 24px; height: 24px;
  display: none; align-items: center; justify-content: center;
  border: 0; border-radius: 50%; background: var(--mmc-scrim-2);
  color: var(--mmc-text); cursor: pointer; padding: 0;
}
.mmc-cell-subject { top: 36px; }
.mmc-cell:hover .mmc-cell-cut,
.mmc-cell:focus-visible .mmc-cell-cut,
.mmc-cell-cut.on { display: flex; }
.mmc-cell:hover .mmc-cell-subject,
.mmc-cell:focus-visible .mmc-cell-subject { display: flex; }
.mmc-cell-cut.on { background: var(--mmc-blue); color: var(--mmc-strong); }
.mmc-cell-cut svg, .mmc-cell-subject svg { width: 13px; height: 13px; }
/* Cut by clicks rather than whole-subject: the mark that a subject was chosen. */
.mmc-cell-cut.pts::after {
  content: ""; position: absolute; right: -1px; top: -1px;
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--mmc-accent); border: 1px solid var(--mmc-ground);
}
/* The paired badge owns the corner where both appear; the scissors move down. */
.mmc-cell-sheet ~ .mmc-cell-cut { top: 34px; }
.mmc-cell-sheet ~ .mmc-cell-subject { top: 62px; }
/* A cut cell is showing the cutout itself, contain-fitted — cover would crop
   the subject against a field whose whole point is showing all of it. The
   field's grey is set inline; only the family knows which one. */
.mmc-cell.cutout img { object-fit: contain; }

/* --- the subject view ------------------------------------------------------
   One picture and the clicks that say which subject its scissors mean — see
   subject.openSubjectView. Reuses the sheet editor's frame, stage chrome and
   dots; what is its own is the polarity pair and the picture-shaped stage. */
.mmc-subject { width: min(640px, 94vw); }
.mmc-subject-name { color: var(--mmc-dim); margin-left: 10px; }
.mmc-subject-stage {
  position: relative; width: 100%; overflow: hidden;
  border: 1px solid var(--mmc-line-3); border-radius: 8px;
  touch-action: none; cursor: crosshair; align-self: center;
}
.mmc-subject-img {
  width: 100%; height: 100%; object-fit: contain; display: block;
  pointer-events: none; user-select: none;
}
/* Keep | Drop: what the next click means, said out loud. One of the two is
   always on — this is a reading of the pointer, not a pair of actions — so it
   gets the segmented chrome the ghost style does not have. */
.mmc-subject-pol { display: flex; }
.mmc-subject-pol .mmc-tool {
  padding: 3px 14px; border: 1px solid var(--mmc-line-3); border-radius: 0;
  font-size: calc(12.5px * var(--mmc-type));
}
.mmc-subject-pol .mmc-tool:first-child { border-radius: 7px 0 0 7px; }
.mmc-subject-pol .mmc-tool:last-child { border-radius: 0 7px 7px 0; margin-left: -1px; }
.mmc-subject-pol .mmc-tool.on {
  background: var(--mmc-blue); border-color: var(--mmc-blue);
  color: var(--mmc-strong);
}

/* What a panel's toolbar is acting on, named in the strip's own numbering. */
.mmc-plate-which {
  min-width: 58px; color: var(--mmc-dim);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
  font-size: calc(10.5px * var(--mmc-type));
}
`;
