// What is left of the upscale bench's own stylesheet.
//
// The room is `styles/bench.js`, shared with the tracing bench. What is here is
// the one control this bench has that the other does not — the locator, which
// exists because the glass shows a *tile* rather than the whole frame and
// something has to say which tile — and the one press its result row offers.

export const css = `
/* --- the locator ---------------------------------------------------------- */
/* The whole frame, small, with the square that is on the glass drawn on it. In
   the rail and not on the picture: the glass has one job, and a second
   rectangle inside it would take room from the thing being judged. */
.mmc-up-loc {
  position: relative; width: 100%; border-radius: 8px; overflow: hidden;
  background: var(--mmc-media-bg); border: 1px solid var(--mmc-line);
  touch-action: none; cursor: crosshair; line-height: 0;
}
.mmc-up-locshot { display: block; width: 100%; height: auto; }
/* The square. Ringed rather than filled, and the ring is the accent because this
   is a control being aimed — the same reading the seam gets under the hand. The
   shadow is what keeps it visible over a white frame. */
.mmc-up-locsquare {
  position: absolute; box-sizing: border-box; pointer-events: none;
  border: 1.5px solid var(--mmc-accent); border-radius: 2px;
  box-shadow: 0 0 0 1px var(--mmc-scrim-2);
}

/* --- the press that runs the model on one tile ----------------------------- */
/* In the corner of the light box, over the picture it is about to change. It is
   not in the foot because the foot is where the presses that write a *file*
   live, and it is not tied to the dials because every backend here is weights:
   a preview that followed the sliders put a checkpoint load behind reading what
   a backend was for. */
.mmc-up-try {
  position: absolute; top: 12px; right: 12px; z-index: 2;
  padding: 6px 13px; border-radius: 14px; cursor: pointer; font-family: inherit;
  background: var(--mmc-float); border: 1px solid var(--mmc-line-3);
  color: var(--mmc-text); font-size: calc(11.5px * var(--mmc-type)); font-weight: 600;
  box-shadow: 0 4px 14px var(--mmc-shadow-soft);
  transition: border-color 120ms ease, color 120ms ease;
}
.mmc-up-try:hover:not(:disabled) { border-color: var(--mmc-accent); color: var(--mmc-accent); }
.mmc-up-try:disabled { cursor: default; color: var(--mmc-off); }
.mmc-up-try:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }

/* --- opening what was written --------------------------------------------- */
/* The tracing bench's result goes through a door into a card. This one is the
   finished file on a shelf, so the press that matters is the one that opens it. */
.mmc-up-open {
  flex: none; padding: 8px 15px; border-radius: 10px; text-decoration: none;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line-2);
  color: var(--mmc-text); font-size: calc(12.5px * var(--mmc-type)); font-weight: 600;
  transition: border-color 120ms ease, background 120ms ease;
}
.mmc-up-open:hover { border-color: var(--mmc-accent); background: var(--mmc-wash-2); }
`;
