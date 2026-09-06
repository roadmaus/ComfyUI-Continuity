// The loupe: the room a finished picture is looked *into*.
//
// It is deliberately not a bench. A bench is an instrument with a light box in
// it — a wide rail of dials, a foot that runs a job, a picture in the middle
// standing for the file that will be written. Here there is nothing to run and
// nothing to write: the file exists, and every pixel of the room that is not
// the file is in the way. So the picture goes edge to edge on black, the bar
// carries a name and a size and nothing else, and the controls are one thin
// foot along the bottom that stays out of the picture's light.
//
// **The rail only exists while something is being compared.** A column of dials
// permanently down one side would take a fifth of the room from the thing the
// room is for, to configure something nobody has switched on. Pressing Compare
// is what pays for it.
//
// **The compared rectangle is drawn.** Against a render's own twin it is the
// whole frame; against the refiner run here and now it is the square that pass
// was worth spending on, and a wipe over part of a picture with no edge on it
// is two pictures that do not agree about where they are. So the rectangle has
// a hairline around it either way, its two halves are named at its foot, and
// the seam belongs to it rather than to the glass.

export const css = `
/* The whole viewport, like a bench's, and for the same reason: this is a room.
   The overlay it rides on is the picker's centred card, and none of that is
   wanted here. */
.mmc-overlay.mmc-lp-over {
  padding: 0; background: var(--mmc-bg); align-items: stretch; justify-content: stretch;
}
.mmc-lp {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  color: var(--mmc-text); overflow: hidden;
}

/* --- the bar -------------------------------------------------------------- */
/* What the file is, said once. No wordmark: the loupe is opened from wherever
   the picture already was and closing it puts that back, so a door to the tools
   here would be a way *out* of somewhere nobody travelled to. */
.mmc-lp-bar {
  flex: none; min-height: 50px; display: flex; align-items: baseline; gap: 12px;
  padding: 0 18px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-lp-name {
  font-size: calc(13px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%;
}
.mmc-lp-meta {
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
  font-variant-numeric: tabular-nums;
}
.mmc-lp-gap { flex: 1; }
.mmc-lp-bar .mmc-close { align-self: center; }

.mmc-lp-room { flex: 1; min-height: 0; display: flex; }
.mmc-lp-work {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
}

/* --- the glass ------------------------------------------------------------ */
/* Black, edge to edge, and the only lit thing in the room. The cursor says what
   a drag will do before it is started; inside the compared square the seam takes
   the press and says so itself. */
.mmc-lp-glass {
  flex: 1; min-height: 0; position: relative; overflow: hidden;
  background: var(--mmc-media-bg); cursor: grab; touch-action: none;
}
.mmc-lp-glass:active { cursor: grabbing; }
/* The picture's own coordinate space: sized in source pixels and moved by one
   transform, so everything laid over it — the compared square above all — is
   positioned in the picture's terms and carried along by the same pan and zoom
   without a number being recomputed. */
.mmc-lp-shot {
  position: absolute; top: 0; left: 0; transform-origin: 0 0;
  will-change: transform;
}
.mmc-lp-pic { display: block; width: 100%; height: 100%; user-select: none; -webkit-user-drag: none; }
/* Past 1.5:1 the picture is being looked at for its pixels, and the browser's
   smoothing is the one thing that makes them impossible to see. */
.mmc-lp-shot.pixels .mmc-lp-pic { image-rendering: pixelated; }

/* --- the compared square -------------------------------------------------- */
.mmc-lp-tilebox {
  position: absolute; overflow: hidden;
  box-shadow: 0 0 0 1px var(--mmc-line-3);
  --mmc-seam: 50%;
}
.mmc-lp-tile {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: fill; display: block; user-select: none; -webkit-user-drag: none;
  /* Only to the right of the seam. A clip path rather than a width, because a
     width would scale the tile instead of revealing it and the two halves would
     stop lining up — which is the one thing a wipe exists to show. */
  clip-path: inset(0 0 0 var(--mmc-seam));
}
/* Cooled rather than faded when the dials have moved on: what is on the glass is
   still a true picture of the settings it was made with, and a picture fading
   toward absent would say "loading", which it is not. The bench says this in the
   same words and with the same filter. */
.mmc-lp-tilebox.stale .mmc-lp-tile { filter: saturate(.45) contrast(.95); }
.mmc-lp-seam {
  position: absolute; top: 0; bottom: 0; left: var(--mmc-seam);
  width: 1px; background: var(--mmc-strong); pointer-events: none;
  box-shadow: 0 0 0 1px var(--mmc-scrim-2);
  transition: background 120ms ease;
}
.mmc-lp-tilebox:hover .mmc-lp-seam { background: var(--mmc-accent); }
.mmc-lp-grip {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  width: 26px; height: 26px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--mmc-float); border: 1px solid var(--mmc-line-3);
  box-shadow: 0 4px 14px var(--mmc-shadow-soft);
}
.mmc-lp-grip svg { stroke: var(--mmc-text); fill: none; stroke-width: 1.7; }
.mmc-lp-tilebox:hover .mmc-lp-grip { border-color: var(--mmc-accent); }
/* Which half is which. Without them a wipe sat halfway across a low-contrast
   frame is two pictures nobody can name. */
.mmc-lp-tag {
  position: absolute; bottom: 8px; padding: 3px 8px; border-radius: 7px;
  background: var(--mmc-scrim-3); color: var(--mmc-dim); pointer-events: none;
  font-size: calc(10px * var(--mmc-type)); letter-spacing: .12em; text-transform: uppercase;
  max-width: 45%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-lp-tag.left { left: 8px; }
.mmc-lp-tag.right { right: 8px; }

/* --- the transport -------------------------------------------------------- */
/* A clip's scrubber is the trim editor's bar with its picture switched off — the
   same bar the upscale bench stands on. What is hidden is everything about
   *cutting*: there is nothing to write here, so handles that promise a segment
   would be a control with no job. What is left is the transport and the
   playhead, which is which frame a comparison is of. */
.mmc-lp-transport:empty { display: none; }
.mmc-lp-transport { flex: none; padding: 8px 18px 0; }
.mmc-lp-transport .mmc-trim-handle,
.mmc-lp-transport .mmc-trim-inline-foot { display: none; }
.mmc-lp-transport .mmc-trim-sel { pointer-events: none; opacity: .25; }

/* --- the foot ------------------------------------------------------------- */
/* One thin row. Everything in it is either the zoom or the comparison, and the
   two are separated by the whole width of the room rather than by a divider. */
.mmc-lp-foot {
  flex: none; display: flex; align-items: center; gap: 8px;
  padding: 10px 18px 12px;
}
.mmc-lp-step {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 8px; cursor: pointer;
  background: none; border: 1px solid var(--mmc-line); color: var(--mmc-dim);
  transition: color 120ms ease, border-color 120ms ease;
}
.mmc-lp-step svg { stroke: currentColor; fill: none; stroke-width: 1.7; }
.mmc-lp-step:hover { color: var(--mmc-text); border-color: var(--mmc-line-2); }
.mmc-lp-zoom {
  min-width: 52px; text-align: center; font-variant-numeric: tabular-nums;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-lp-jump {
  padding: 5px 11px; border-radius: 8px; cursor: pointer; font-family: inherit;
  background: none; border: 1px solid transparent; color: var(--mmc-dim);
  font-size: calc(11.5px * var(--mmc-type));
  transition: color 120ms ease, background 120ms ease;
}
.mmc-lp-jump:hover { color: var(--mmc-text); background: var(--mmc-wash); }
.mmc-lp-jump.on { color: var(--mmc-strong); background: var(--mmc-wash-2); }
/* The one press in the room that opens something, so the one thing in it that
   is allowed to be amber — and only once it is on. */
.mmc-lp-compare {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 13px; border-radius: 10px; cursor: pointer; font-family: inherit;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line-2);
  color: var(--mmc-text); font-size: calc(12px * var(--mmc-type)); font-weight: 600;
  transition: border-color 120ms ease, color 120ms ease, background 120ms ease;
}
.mmc-lp-compare svg { stroke: currentColor; fill: none; stroke-width: 1.7; }
.mmc-lp-compare:hover { border-color: var(--mmc-line-3); }
.mmc-lp-compare.on {
  color: var(--mmc-accent); border-color: var(--mmc-accent); background: var(--mmc-wash);
}
.mmc-lp-compare:focus-visible,
.mmc-lp-jump:focus-visible,
.mmc-lp-step:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }

/* --- the rail ------------------------------------------------------------- */
.mmc-lp-rail {
  flex: none; width: 268px; display: flex; flex-direction: column; gap: 13px;
  padding: 18px 18px 20px; overflow-y: auto;
  border-left: 1px solid var(--mmc-line); background: var(--mmc-surface);
}
.mmc-lp-rail[hidden] { display: none; }
.mmc-lp-railtitle {
  font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong);
}
.mmc-lp-railnote {
  margin: -6px 0 0; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-faint);
  line-height: 1.45;
}
.mmc-lp-estimate {
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-faint); line-height: 1.45;
}
.mmc-lp-bad { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-bad); line-height: 1.45; }
/* What the render already ran, where there is nothing to dial. A fact about the
   file rather than a control over it, so it is set as one: the pack's small
   monospace-free readout, indented off the note above it by a rule. */
.mmc-lp-was {
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-text); line-height: 1.5;
  padding: 9px 11px; border-radius: 9px; background: var(--mmc-wash);
}

/* The press that spends a model pass. The only filled button in the room. */
.mmc-lp-run {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px 14px; border-radius: 10px; cursor: pointer; font-family: inherit;
  background: var(--mmc-accent); border: none; color: var(--mmc-on-accent);
  font-size: calc(12.5px * var(--mmc-type)); font-weight: 600;
}
.mmc-lp-run:disabled {
  cursor: default; background: var(--mmc-surface-3); color: var(--mmc-off);
}
.mmc-lp-run:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }

/* --- the saved setups ----------------------------------------------------- */
.mmc-lp-shelf {
  display: flex; flex-direction: column; gap: 7px;
  padding-top: 12px; border-top: 1px solid var(--mmc-line);
}
.mmc-lp-shelftop { display: flex; align-items: center; justify-content: space-between; }
.mmc-lp-profiles { display: flex; flex-wrap: wrap; gap: 5px; }
.mmc-lp-profile {
  padding: 4px 10px; border-radius: 999px; cursor: pointer; font-family: inherit;
  background: var(--mmc-wash); border: 1px solid transparent; color: var(--mmc-text);
  font-size: calc(11.5px * var(--mmc-type));
  transition: border-color 120ms ease, color 120ms ease;
}
.mmc-lp-profile:hover { border-color: var(--mmc-line-2); }
.mmc-lp-profile.on { color: var(--mmc-accent); border-color: var(--mmc-accent); }
.mmc-lp-save, .mmc-lp-start {
  padding: 4px 10px; border-radius: 999px; cursor: pointer; font-family: inherit;
  background: none; border: 1px dashed var(--mmc-line-2); color: var(--mmc-dim);
  font-size: calc(11.5px * var(--mmc-type));
  transition: color 120ms ease, border-color 120ms ease;
}
.mmc-lp-save:hover, .mmc-lp-start:hover { color: var(--mmc-text); border-color: var(--mmc-line-3); }
.mmc-lp-start.on { color: var(--mmc-accent); border-style: solid; border-color: var(--mmc-accent); }
.mmc-lp-namefield {
  flex: 1; min-width: 120px; padding: 4px 10px; border-radius: 999px;
  background: var(--mmc-bg); border: 1px solid var(--mmc-accent); color: var(--mmc-text);
  font-family: inherit; font-size: calc(11.5px * var(--mmc-type));
}
.mmc-lp-namefield:focus { outline: none; }

/* Narrow rooms — a node's window on a laptop. The rail goes under the picture
   rather than beside it: a 268-pixel column beside a 600-pixel glass is a rail
   that has taken the picture's place. */
@media (max-width: 900px) {
  .mmc-lp-room { flex-direction: column; }
  .mmc-lp-rail {
    width: auto; border-left: none; border-top: 1px solid var(--mmc-line);
    max-height: 45%;
  }
}
`;
