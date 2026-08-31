// What is the blockout bench's own.
//
// The room is `styles/bench.js`, shared with the other two benches. What is
// here is the three controls this bench has that they do not: the timeline the
// camera path lives on (the trim bar's species, drawn in the trim bar's blue,
// but over marks rather than a waveform — there is no media to decode), the
// piece card in the rail, and the foot's narration of the move. The glass gets
// one qualified override: its cursor is a hand, because dragging it operates a
// camera rather than a seam.

export const css = `
/* --- the glass ------------------------------------------------------------ */
/* A hand, not the seam's ew-resize: most of this surface operates the camera,
   and the seam still says what it is by its own grip. */
.mmc-bo .mmc-bo-frame { cursor: grab; }
.mmc-bo .mmc-bo-frame:active { cursor: grabbing; }
/* The canvas is the one layer there is; it holds the frame's whole rectangle
   the way the benches' media layers do. */
.mmc-bo-frame canvas { image-rendering: auto; }

/* --- the set --------------------------------------------------------------- */
.mmc-bo-adds { display: flex; gap: 6px; }
.mmc-bo-adds .mmc-bn-verb { flex: 1; min-width: 0; }
.mmc-bo-piece {
  display: flex; flex-direction: column; gap: 10px;
  padding: 10px; border-radius: 10px;
  background: var(--mmc-tint); border: 1px solid var(--mmc-line);
}
.mmc-bo-piecename {
  display: flex; align-items: center; gap: 8px;
  font-size: calc(12.5px * var(--mmc-type)); font-weight: 500; color: var(--mmc-strong);
}
.mmc-bo-remove {
  background: none; border: 0; cursor: pointer; padding: 2px 4px;
  color: var(--mmc-off); font-family: inherit; font-size: calc(11px * var(--mmc-type));
}
.mmc-bo-remove:hover { color: var(--mmc-text); }
.mmc-bo-remove:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; border-radius: 4px; }

/* --- the path, in the rail -------------------------------------------------- */
.mmc-bo-marks {
  display: flex; flex-direction: column;
  border-top: 1px solid var(--mmc-line);
}
.mmc-bo-markrow {
  display: flex; align-items: center; gap: 8px; min-height: calc(27px * var(--mmc-type));
  padding: 0 2px; border-bottom: 1px solid var(--mmc-line);
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-bo-markwhen {
  margin-left: auto; font-variant-numeric: tabular-nums;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-off);
}
/* The mark. A diamond in the trim bar's blue — a held position, not a job. */
.mmc-bo-markdot {
  flex: none; width: 7px; height: 7px; border-radius: 2px;
  background: var(--mmc-blue); transform: rotate(45deg);
}
.mmc-bo-runs {
  display: flex; align-items: center; gap: 6px;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-bo-runs b {
  min-width: 34px; text-align: center; font-weight: 500; color: var(--mmc-strong);
  font-variant-numeric: tabular-nums; font-size: calc(11.5px * var(--mmc-type));
}
.mmc-bo-step {
  width: 20px; height: 20px; padding: 0; border-radius: 6px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-family: inherit; font-size: calc(11px * var(--mmc-type));
}
.mmc-bo-step:hover { background: var(--mmc-surface-2); }
.mmc-bo-step:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }

/* --- the path, under the glass ---------------------------------------------- */
.mmc-bo-cut { flex: none; display: flex; align-items: center; gap: 10px; }
.mmc-bo-play {
  flex: none; width: calc(30px * var(--mmc-type)); height: calc(30px * var(--mmc-type));
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px; cursor: pointer;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); color: var(--mmc-text);
}
.mmc-bo-play:hover { background: var(--mmc-surface-2); }
.mmc-bo-play svg { stroke: currentColor; fill: currentColor; stroke-width: 1; }
.mmc-bo-play:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-bo-track {
  position: relative; flex: 1; height: calc(30px * var(--mmc-type));
  border-radius: 8px; cursor: pointer; touch-action: none;
  background: var(--mmc-tint); border: 1px solid var(--mmc-line);
}
.mmc-bo-track .mmc-bo-mark {
  position: absolute; top: 50%; width: 8px; height: 8px; pointer-events: none;
  transform: translate(-50%, -50%) rotate(45deg);
  background: var(--mmc-blue); border-radius: 2px;
}
.mmc-bo-playhead {
  position: absolute; top: 2px; bottom: 2px; width: 2px; border-radius: 1px;
  background: var(--mmc-blue); pointer-events: none;
}
/* The one control on the row that makes something: outlined in the marks' own
   blue, because pressing it mints one. Not amber — amber is the run's. */
.mmc-bo-markbtn {
  flex: none; display: flex; align-items: center; gap: 7px;
  height: calc(30px * var(--mmc-type)); padding: 0 13px; border-radius: 8px; cursor: pointer;
  background: none; border: 1px solid var(--mmc-blue); color: var(--mmc-blue);
  font-family: inherit; font-size: calc(12px * var(--mmc-type)); font-weight: 500;
}
.mmc-bo-markbtn:hover { background: color-mix(in srgb, var(--mmc-blue) 12%, transparent); }
.mmc-bo-markbtn:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }

/* --- the move, said --------------------------------------------------------- */
/* A sentence, not a label: italic, quoted, and quiet. It is the second output
   being drafted live, and the Copy beside it is its door. */
.mmc-bo-say {
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: calc(12px * var(--mmc-type)); font-style: italic; color: var(--mmc-dim);
}
.mmc-bo-say::before { content: "\\201C"; color: var(--mmc-off); }
.mmc-bo-say::after { content: "\\201D"; color: var(--mmc-off); }
.mmc-bo-copy { flex: none; }

@media (max-width: 900px) {
  .mmc-bo-cut { flex-wrap: wrap; }
  .mmc-bo-say { white-space: normal; }
}
`;
