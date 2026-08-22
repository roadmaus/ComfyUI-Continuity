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

`;
