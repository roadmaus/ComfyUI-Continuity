// What is left of the ControlNet bench's own stylesheet.
//
// The room it is in — the bar, the rail, the light box, the seam, the foot — is
// `styles/bench.js` now, shared with the upscale bench and any bench after it.
// Two things did not move, and both are here because they are *this* bench and
// not a bench in general: the sweep the glass does when a tracing lands, and the
// pill on the shot's own row that decides whether the branch reading a guide is
// loaded at all.

export const css = `
/* --- the arrival sweep ---------------------------------------------------- */
/* The seam is dragged by hand every other second of a session and never
   animates; for the half second after a file is written it runs out to the edge
   and back on its own, which is the bench showing you the drawing alone under
   its new name. Written as a state on the frame rather than as a keyframe, so it
   is the same clip-path and the same left the hand moves — there is one seam,
   and this is it being moved by something other than a pointer. */
.mmc-bn-frame.sweeping .mmc-bn-over-layer {
  transition: clip-path 520ms cubic-bezier(.22, 1, .36, 1), opacity 130ms ease;
}
.mmc-bn-frame.sweeping .mmc-bn-seam {
  transition: left 520ms cubic-bezier(.22, 1, .36, 1), background 120ms ease;
}
.mmc-bn-frame.sweeping .mmc-bn-tag.right { color: var(--mmc-strong); }
@media (prefers-reduced-motion: reduce) {
  .mmc-bn-frame.sweeping .mmc-bn-over-layer,
  .mmc-bn-frame.sweeping .mmc-bn-seam { transition: none; }
}

/* ---- the guide switch -------------------------------------------------------

   The bench's other half, drawn on the pill row rather than in the room: the
   bench makes a drawing, the card holds it, and this decides whether the branch
   that reads it is loaded at all. Here rather than in styles/editor.js because
   it is this feature, and a reader looking for how a guide is drawn should find
   both ends of it in one place.

   Nothing here picks a file. The drawing is an attached asset and wears the
   .mmc-asset chip every other attachment wears, which is why this section is
   four rules rather than a control. */
.mmc-guide-main {
  display: flex; align-items: center; gap: 7px; height: 100%; padding: 0 2px;
  background: none; border: 0; color: inherit; font-size: calc(13px * var(--mmc-type));
  font-family: inherit; cursor: pointer; white-space: nowrap;
}
/* Lit in the accent, not in the accelerator blue beside it. Blue on this row
   means "this render is not native", and a guide does not make it native or
   otherwise -- it decides the composition. The accent is what this pack lights
   the control that is doing the deciding, which is the same reading the
   duration pill gives its auto switch. */
.mmc-pill.mmc-guide-on {
  border-color: color-mix(in srgb, var(--mmc-accent) 45%, transparent);
  color: var(--mmc-accent);
}
.mmc-pill.mmc-guide-on:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--mmc-accent) 70%, transparent);
}
/* The pressed stop. Qualified past .mmc-pill-seg[aria-pressed] rather than left
   to the concatenation order, which is a thing that can be reordered. */
.mmc-pill-set .mmc-pill-seg.mmc-guide-on {
  background: color-mix(in srgb, var(--mmc-accent) 14%, transparent);
  color: var(--mmc-accent);
}
/* The only thing on the pill drawn in the warn colour: a drawing these weights
   never saw. A worse render rather than an impossible one, which is the exact
   thing --mmc-warn is the pack's word for -- so it stays warn inside a lit
   pill, where everything else has gone amber. */
.mmc-pill .mmc-guide-warn { color: var(--mmc-warn); }

`;
