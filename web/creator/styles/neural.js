// The refiner's dials, wherever they are set.
//
// Two surfaces draw them — the pill's popover and the loupe's rail — and until
// this sheet existed each drew its own control: steppers in the popover,
// sliders on the bench, the same six numbers reading two different ways. So the
// dial is here once, under its own prefix, owned by neither room.
//
// **A dial is a label, its number and a track.** The number is set in tabular
// figures on the right of the label, so a column of them lines up and a value
// that changes under the pointer does not shift the word beside it. The track
// is a plain range input drawn in this pack's own terms — a hairline with a
// small round head, amber only while it is being used, because the accent in
// this pack means "the control is in your hand" and a rail of six permanently
// amber sliders would spend it six times over standing still.

export const css = `
/* On or off. A track and a knob, sized to the row it sits in rather than to a
   phone's idea of a toggle: this is a header control beside a title, not the
   subject of the panel. */
.mmc-nr-switch {
  flex: none; position: relative; width: 34px; height: 19px; padding: 0;
  border-radius: 999px; cursor: pointer; border: 1px solid var(--mmc-line-2);
  background: var(--mmc-wash); transition: background 140ms ease, border-color 140ms ease;
}
.mmc-nr-knob {
  position: absolute; top: 2px; left: 2px; width: 13px; height: 13px;
  border-radius: 50%; background: var(--mmc-dim);
  transition: transform 140ms ease, background 140ms ease;
}
.mmc-nr-switch.on { background: var(--mmc-accent); border-color: var(--mmc-accent); }
.mmc-nr-switch.on .mmc-nr-knob { transform: translateX(15px); background: var(--mmc-on-accent); }
.mmc-nr-switch:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
  .mmc-nr-switch, .mmc-nr-knob { transition: none; }
}

.mmc-nr-dial { display: flex; flex-direction: column; gap: 5px; }
.mmc-nr-diallabel {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-nr-value {
  font-variant-numeric: tabular-nums; color: var(--mmc-text); font-weight: 600;
}
.mmc-nr-range {
  -webkit-appearance: none; appearance: none; width: 100%; height: 14px;
  background: none; cursor: pointer; margin: 0;
}
.mmc-nr-range::-webkit-slider-runnable-track {
  height: 2px; border-radius: 2px; background: var(--mmc-line-2);
}
.mmc-nr-range::-moz-range-track {
  height: 2px; border-radius: 2px; background: var(--mmc-line-2);
}
.mmc-nr-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 11px; height: 11px;
  margin-top: -4.5px; border-radius: 50%;
  background: var(--mmc-text); border: none;
  transition: background 120ms ease, transform 120ms ease;
}
.mmc-nr-range::-moz-range-thumb {
  width: 11px; height: 11px; border-radius: 50%; border: none;
  background: var(--mmc-text);
}
.mmc-nr-range:hover::-webkit-slider-thumb,
.mmc-nr-range:active::-webkit-slider-thumb { background: var(--mmc-accent); transform: scale(1.15); }
.mmc-nr-range:hover::-moz-range-thumb,
.mmc-nr-range:active::-moz-range-thumb { background: var(--mmc-accent); }
.mmc-nr-range:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 3px; }

/* A word chosen from a few. The row is label-left, choices-right — the same
   shape as a dial's own label line, so the rail reads as one column of rows
   rather than as two kinds of control that happen to be stacked. */
.mmc-nr-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.mmc-nr-label {
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim); flex: none;
}
.mmc-nr-opts { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; }
/* Four choices, under their label rather than beside it. */
.mmc-nr-row.stacked { flex-direction: column; align-items: stretch; gap: 5px; }
.mmc-nr-row.stacked .mmc-nr-opts { justify-content: flex-start; }
.mmc-nr-opt {
  padding: 4px 9px; border-radius: 8px; cursor: pointer; font-family: inherit;
  background: none; border: 1px solid transparent; color: var(--mmc-dim);
  font-size: calc(11.5px * var(--mmc-type));
  transition: color 120ms ease, background 120ms ease;
}
.mmc-nr-opt:hover { color: var(--mmc-text); background: var(--mmc-wash); }
.mmc-nr-opt.on {
  background: var(--mmc-wash-2); color: var(--mmc-strong); border-color: var(--mmc-line-2);
}
.mmc-nr-opt:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
`;
