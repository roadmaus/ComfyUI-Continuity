// What is Game Forge's own on top of the benches' room.
//
// The room itself is styles/bench.js. What is here is the two things this bench
// has that the others do not: the manifest down the rail, whose rows each
// carry where the asset stands, and a light box that shows pixel art as pixel
// art. The amber is not spent here at all — the room already spends it on the
// stop you are on and the press that exports — and a problem is drawn in the
// room's bad colour, because it is a fault and not a control.

export const css = `
/* The open project, on the bar's path: laid out like the steps before it. */
.mmc-fg-crumb { display: contents; }

/* --- the rail's fields ----------------------------------------------------- */
.mmc-fg-field { display: flex; flex-direction: column; gap: 6px; }
.mmc-fg-label { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-fg-clause, .mmc-fg-recipe { resize: vertical; line-height: 1.45; }
/* A recipe is JSON, and JSON is read by its columns. */
.mmc-fg-recipe {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(11px * var(--mmc-type)); white-space: pre; overflow-x: auto;
}
.mmc-fg-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.mmc-fg-leave, .mmc-fg-remove {
  align-self: flex-start; padding: 0; background: none; border: 0; cursor: pointer;
  font-family: inherit; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-off);
  text-align: left; text-decoration: underline; text-underline-offset: 3px;
  text-decoration-color: var(--mmc-line-3);
}
.mmc-fg-leave:hover, .mmc-fg-remove:hover { color: var(--mmc-text); }
/* The second press of Remove says what it will do, in the colour a fault is
   drawn in: the first press only asked. */
.mmc-fg-remove.armed { color: var(--mmc-bad); text-decoration-color: currentColor; }
.mmc-fg-leave:focus-visible, .mmc-fg-remove:focus-visible {
  outline: 2px solid var(--mmc-accent); outline-offset: 2px;
}
.mmc-fg-add { display: flex; flex-direction: column; gap: 8px; }
.mmc-fg-count, .mmc-fg-kind {
  flex: none; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off);
  font-variant-numeric: tabular-nums;
}
.mmc-fg-summary {
  margin: 0; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
  font-variant-numeric: tabular-nums;
}

/* --- the manifest ---------------------------------------------------------- */
/* One mark per row for where the asset stands, read down the left edge like
   the status column of the MANIFEST.md it mirrors: a ring is a placeholder, a
   dot is a picture, a square has gone out to every engine, and a dashed ring
   is the pack's mark for a thing that is real but no longer what it was. */
.mmc-fg-manifest { max-height: 44vh; overflow: auto; overscroll-behavior: contain; }
.mmc-fg-mark {
  flex: none; width: 8px; height: 8px; border-radius: 50%; box-sizing: border-box;
}
.mmc-fg-mark.planned { border: 1px solid var(--mmc-line-3); }
.mmc-fg-mark.made { background: var(--mmc-dim); }
.mmc-fg-mark.exported { background: var(--mmc-strong); border-radius: 1.5px; }
.mmc-fg-mark.stale { border: 1.5px dashed var(--mmc-dim); }
/* Made and not looked at: the name is heavier, the way an unread letter is.
   An agent's status line says "(not looked at)"; a person reads it here. */
.mmc-fg-row.unseen .mmc-bn-pickname { color: var(--mmc-strong); font-weight: 600; }
/* After a check, how many problems an asset has on the target in the foot. */
.mmc-fg-bad {
  flex: none; min-width: 16px; padding: 0 5px; border-radius: 8px; box-sizing: border-box;
  font-size: calc(10.5px * var(--mmc-type)); font-weight: 600; line-height: 16px;
  text-align: center; font-variant-numeric: tabular-nums;
  color: var(--mmc-bad); border: 1px solid currentColor;
}

/* --- the light box ---------------------------------------------------------- */
.mmc-fg-views { flex: none; display: flex; }
/* Sized in script to a whole-number zoom (forge.js fitGlass), so every pixel of
   a sprite is the same number of screen pixels. Unsmoothed, because a pixel
   blurred into its neighbour is not the pixel the engine will draw. A picture
   larger than the glass is shrunk, and only then smoothed. */
.mmc-fg-glass {
  display: block; image-rendering: pixelated; user-select: none; -webkit-user-drag: none;
}
.mmc-fg-glass.shrunk { image-rendering: auto; }
.mmc-fg-box { cursor: default; }

/* --- problems --------------------------------------------------------------- */
/* Under the glass, one line each: where, what, and the code an agent branches
   on. The code is set as code because it is one; it is never reworded. */
.mmc-fg-problems { flex: none; max-height: 22vh; overflow: auto; }
.mmc-fg-problems:empty { display: none; }
.mmc-fg-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; }
.mmc-fg-list li {
  display: grid; grid-template-columns: minmax(70px, auto) 1fr auto; gap: 12px; align-items: baseline;
  padding: 6px 2px; font-size: calc(12px * var(--mmc-type));
}
.mmc-fg-list li + li { border-top: 1px solid var(--mmc-line); }
.mmc-fg-where { color: var(--mmc-dim); font-variant-numeric: tabular-nums; white-space: nowrap; }
.mmc-fg-what { color: var(--mmc-text); }
.mmc-fg-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-bad);
}

/* --- the foot --------------------------------------------------------------- */
.mmc-fg-status {
  display: flex; align-items: center; gap: 8px; min-width: 0;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-fg-status span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* A target's name is one word to the eye, "Godot 4" included: it never breaks. */
.mmc-fg-foot .mmc-bn-opt { white-space: nowrap; }
@media (max-width: 900px) {
  /* The targets get a line of their own above the two presses rather than
     being squeezed beside them. */
  .mmc-fg-foot { flex-wrap: wrap; row-gap: 10px; }
  .mmc-fg-foot > .mmc-bn-opts { flex-basis: 100%; }
  .mmc-fg-list li { grid-template-columns: 1fr; gap: 2px; }
  .mmc-fg-manifest { max-height: none; }
}
`;
