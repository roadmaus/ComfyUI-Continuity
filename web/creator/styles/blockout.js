// What the blockout bench's own controls look like.
//
// The room is `styles/bench.js`, shared with the other two benches. What is
// here is what this bench has that they do not: a viewport HUD, a properties
// panel, a timeline over marks rather than a waveform, and the foot's
// narration of the move.
//
// **The HUD does not use the pack's tokens, and that is deliberate.** Every
// other surface in the pack sits on the page's own ground and takes its colour
// from the theme. The HUD sits on the *canvas*, which paints its own dark sky
// whatever the theme is, so a light-theme `--mmc-surface` would put a white
// pill on a near-black picture. Its greys are therefore literals, tuned against
// the clay the rasterizer draws — the one place in the pack where that is the
// correct answer rather than a shortcut.
//
// **The axis letters in the rail wear the gizmo's colours.** X warm, Y green,
// Z cool, and W/H/D the same three because a piece's width runs along its own
// X. It is the only tie between a number in the rail and a handle on the glass,
// and it costs three declarations.

export const css = `
/* --- the glass ------------------------------------------------------------ */
/* A hand: the whole of this surface is either a camera or a thing being moved,
   and both are grabbed. */
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

/* --- who a piece is --------------------------------------------------------- */
/* The chooser reads like the pack's other pills: the member's dot wears the
   same hue their chip does everywhere else, which is the whole point of it. */
.mmc-bo-who {
  display: flex; align-items: center; gap: 7px; width: 100%;
  height: calc(28px * var(--mmc-type)); padding: 0 9px; border-radius: 7px;
  cursor: pointer; text-align: left; font-family: inherit;
  background: var(--mmc-wash); border: 1px solid var(--mmc-line-2);
  color: var(--mmc-text); font-size: calc(12px * var(--mmc-type));
}
.mmc-bo-who:hover { border-color: var(--mmc-line-3); }
.mmc-bo-who:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-bo-who svg { margin-left: auto; flex: none; stroke: var(--mmc-off); fill: none; stroke-width: 1.6; }
.mmc-bo-whodot {
  flex: none; width: 8px; height: 8px; border-radius: 50%;
  background: var(--tag, var(--mmc-off));
}
.mmc-bo-whoname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

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

/* --- the viewport HUD -------------------------------------------------------- */
/* Floating over the canvas: the two questions you are always answering while
   working — which camera am I, and am I looking at the stage or the file. */
.mmc-bo-hud {
  position: absolute; left: 10px; right: 10px; z-index: 2;
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  pointer-events: none;
}
.mmc-bo-hud.top { top: 10px; }
.mmc-bo-hud.bottom { bottom: 10px; }
.mmc-bo-hud .mmc-bo-switch { pointer-events: auto; }
.mmc-bo-switch {
  display: flex; gap: 2px; padding: 2px; border-radius: 9px;
  background: rgba(14, 15, 17, .74); border: 1px solid rgba(255, 255, 255, .1);
  -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
}
.mmc-bo-seg {
  height: calc(24px * var(--mmc-type)); padding: 0 10px; border: 0; border-radius: 7px;
  background: none; cursor: pointer; white-space: nowrap;
  font-family: inherit; font-size: calc(11.5px * var(--mmc-type));
  color: rgba(233, 231, 226, .58);
}
.mmc-bo-seg:hover { color: rgba(233, 231, 226, .92); }
.mmc-bo-seg.on { background: rgba(233, 231, 226, .15); color: #f0ede7; }
.mmc-bo-seg:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -1px; }

/* --- the frame's shape -------------------------------------------------------- */
/* The strip's own pill, in a rail rather than a bar: it fills the row the three
   shape buttons used to, and reads left to right like every dial above it. */
.mmc-bo-aspect { width: 100%; justify-content: flex-start; }
.mmc-bo-aspect .mmc-pill-sub { margin-left: auto; }

/* --- starting points --------------------------------------------------------- */
.mmc-bo-presets { display: flex; flex-wrap: wrap; gap: 5px; }
.mmc-bo-preset {
  height: calc(24px * var(--mmc-type)); padding: 0 9px; border-radius: 6px; cursor: pointer;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-family: inherit; font-size: calc(11px * var(--mmc-type));
}
.mmc-bo-preset:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-bo-preset:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-bo-verbs { display: flex; gap: 6px; }
.mmc-bo-verbs .mmc-bn-verb { flex: 1; min-width: 0; }

/* --- the properties panel's numbers ------------------------------------------ */
.mmc-bo-vec { display: flex; gap: 5px; }
.mmc-bo-vecslot {
  flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px;
  height: calc(26px * var(--mmc-type)); padding: 0 7px; border-radius: 7px;
  background: var(--mmc-wash); border: 1px solid var(--mmc-line-2);
}
.mmc-bo-vecslot:focus-within { border-color: var(--mmc-line-3); }
.mmc-bo-axis {
  flex: none; font-size: calc(9.5px * var(--mmc-type));
  font-weight: 600; letter-spacing: .06em;
}
.mmc-bo-axis.is-x, .mmc-bo-axis.is-w { color: #e05a52; }
.mmc-bo-axis.is-y, .mmc-bo-axis.is-h { color: #79c85a; }
.mmc-bo-axis.is-z, .mmc-bo-axis.is-d { color: #4f8fe2; }
.mmc-bo-num {
  width: 100%; min-width: 0; padding: 0; border: 0; background: none;
  color: var(--mmc-text); font-family: inherit;
  font-size: calc(11.5px * var(--mmc-type)); font-variant-numeric: tabular-nums;
  -moz-appearance: textfield; appearance: textfield;
}
.mmc-bo-num:focus { outline: none; }
.mmc-bo-num::-webkit-outer-spin-button,
.mmc-bo-num::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }

/* --- a mark, as a place to go back to ---------------------------------------- */
.mmc-bo-markgo {
  padding: 0; border: 0; background: none; cursor: pointer;
  font: inherit; color: inherit; text-align: left;
}
.mmc-bo-markgo:hover { color: var(--mmc-text); }
.mmc-bo-markgo:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; border-radius: 4px; }

@media (max-width: 900px) {
  .mmc-bo-cut { flex-wrap: wrap; }
  .mmc-bo-say { white-space: normal; }
  /* A narrow glass cannot hold both switches on one line; the top one wraps
     rather than either of them shrinking its words away. */
  .mmc-bo-hud { gap: 6px; }
  .mmc-bo-hud .mmc-bn-gap { flex-basis: 100%; height: 0; }
}
`;
