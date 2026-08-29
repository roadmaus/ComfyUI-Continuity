// The benches — the room both of them are, drawn once.
//
// A bench is a file on a light box with an instrument beside it. There are two
// (tracing, upscale) and there will be more, and they are the same room: the
// same bar, the same rail down the left, the same rectangle with a seam through
// it, the same foot. So this is one stylesheet with a `mmc-bn-` prefix, and
// `styles/control.js` and `styles/upscale.js` keep only what is genuinely one
// bench's own — the arrival sweep, the locator, the guide pill.
//
// **The rail is a film edge.** It used to be four groups of controls floating in
// a very wide column, each under a label with a hairline ruled across the whole
// width — which is the layout every settings panel has, and at this pack's type
// scale it read as a page of documentation with some sliders in it. A strip of
// film is printed down its edge instead: a line, a tick at every stop, the
// stop's name set small against it. That is the structure here. It gives the
// column a spine to hang on, it makes the stops read as one instrument rather
// than four cards, and it takes the width back — everything is measured from
// the spine, so the rail can be narrow and stay legible.
//
// **The rail is dense and the light box is loud.** Every decision below follows
// from that: rows rather than pills (a pill wraps ragged and a row does not),
// two lines of prose rather than a paragraph (the surface says what a thing is
// *for*, and the manual is a hover away), tabular numerals on every value, and
// the amber spent in exactly three places — the tick on the stop you are on, the
// seam under your hand, and the button that runs the job. Nothing else in the
// room is allowed to be that colour.

export const css = `
/* The bench takes the whole viewport rather than a card in the middle of it.
   The overlay it rides on is the picker's — fixed, scrimmed, centred with a
   40-pixel gutter — and none of that is wanted for a room. */
.mmc-overlay.mmc-bn-over {
  padding: 0; background: var(--mmc-bg); align-items: stretch; justify-content: stretch;
}
/* A file over the room. The whole surface is the target, so the whole surface
   says so — an inset ring rather than a highlighted well, because there is no
   well and drawing one under the pointer would invent a target the moment
   somebody stopped needing it. */
.mmc-overlay.mmc-bn-over.dropping::after {
  content: ""; position: absolute; inset: 10px; border-radius: 18px;
  border: 2px dashed var(--mmc-accent); pointer-events: none;
}
.mmc-bn {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  color: var(--mmc-text); overflow: hidden;
}

/* --- the bar ------------------------------------------------------------- */
.mmc-bn-bar {
  flex: none; min-height: 54px; display: flex; align-items: center; gap: 10px;
  padding: 0 18px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-bn-mark { display: flex; align-items: center; gap: 9px; }
.mmc-bn-word { font-size: calc(13px * var(--mmc-type)); font-weight: 600; }
/* The wordmark, and it is the way back to the tools — the same door it is in
   the editor's own bar, so it is drawn the same: a button that reads as the
   wordmark it was until you point at it, with the caret as the standing hint
   that it goes somewhere. */
.mmc-bn-home {
  display: flex; align-items: center; gap: 9px;
  font-size: calc(13px * var(--mmc-type)); font-weight: 600; letter-spacing: .01em;
  background: none; border: 0; cursor: pointer; padding: 5px 8px; margin-left: -8px;
  border-radius: 10px; color: var(--mmc-text); font-family: inherit;
}
.mmc-bn-home:hover { background: var(--mmc-surface); }
.mmc-bn-home:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-bn-caret { display: flex; }
.mmc-bn-home .mmc-bn-caret svg { stroke: var(--mmc-off); fill: none; stroke-width: 1.6; }
.mmc-bn-home:hover .mmc-bn-caret svg { stroke: var(--mmc-dim); }
/* The mark is artwork rather than a glyph — it brings its own fills and its own
   ground — so it is clipped rather than trusted to its own rounded rect: a tile
   with a 1px light seam along one edge is what an un-antialiased corner looks
   like. Same treatment as the shell's, for the same reason. */
.mmc-bn-logo {
  display: flex; flex: none; width: 20px; height: 20px;
  border-radius: 6px; overflow: hidden;
}
.mmc-bn-logo svg { stroke: none; fill: initial; stroke-width: initial; display: block; }
.mmc-bn-slash { color: var(--mmc-off); }
.mmc-bn-here { font-size: calc(13px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-bn-gap { flex: 1; }

.mmc-bn-room { flex: 1; min-height: 0; display: flex; }

/* --- the rail ------------------------------------------------------------ */
/* Capped in viewport units as well as in text size. It is a rail of labels,
   rows and sliders and none of those get better past about three hundred
   pixels, while the light box — which does — gets everything that is left. At
   the pack's larger text scales the unbounded version took nearly half the
   window and turned the notes into a column of prose. */
.mmc-bn-rail {
  flex: none; width: min(calc(292px * var(--mmc-type)), 34vw); min-width: 0;
  border-right: 1px solid var(--mmc-line); overflow: auto; overscroll-behavior: contain;
  padding: 20px 18px 18px; display: flex; flex-direction: column;
}
/* The edge itself: one line down the rail, with the stops hung off it. It is on
   an inner wrapper rather than on the scrolling rail so it runs the length of
   the content instead of the length of the window. */
.mmc-bn-stops {
  position: relative; padding-left: 20px;
  display: flex; flex-direction: column; gap: 22px;
}
.mmc-bn-stops::before {
  content: ""; position: absolute; left: 3px; top: 4px; bottom: 2px;
  width: 1px; background: var(--mmc-line);
}
.mmc-bn-stop { position: relative; display: flex; flex-direction: column; gap: 10px; }
/* The tick. Short, hard, and level with the label's own text — it is a frame
   mark on an edge, not a bullet. */
.mmc-bn-stopname {
  position: relative;
  font-size: calc(10.5px * var(--mmc-type)); font-weight: 600;
  letter-spacing: .16em; text-transform: uppercase; color: var(--mmc-off);
}
.mmc-bn-stopname::before {
  content: ""; position: absolute; left: -17px; top: .55em;
  width: 9px; height: 1px; background: var(--mmc-line-3);
}

/* What is on the bench. */
.mmc-bn-file { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.mmc-bn-filename {
  font-size: calc(13px * var(--mmc-type)); font-weight: 500; color: var(--mmc-strong);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* The size, the length, and what it is about to become. Tabular, because these
   are numbers somebody compares against the numbers in the dials. */
.mmc-bn-filenote {
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
  font-variant-numeric: tabular-nums;
}
.mmc-bn-empty { margin: 0; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-bn-verb {
  width: 100%; display: flex; white-space: nowrap; overflow: hidden;
  align-items: center; justify-content: center; gap: 7px;
  height: calc(32px * var(--mmc-type)); border-radius: 8px; cursor: pointer;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-family: inherit; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-bn-verb:hover:not(:disabled) { background: var(--mmc-surface-2); border-color: var(--mmc-line-2); }
.mmc-bn-verb:disabled { opacity: .5; cursor: default; }
.mmc-bn-verb svg { flex: none; stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-bn-verb span { overflow: hidden; text-overflow: ellipsis; }

/* --- what this bench can do ---------------------------------------------- */
/* Rows, not pills. Nine tracings as pills wrapped into a ragged block three
   lines deep, each one a different width because some of them carried a "NO
   MODEL" tag inside the shape — so the list had no left edge to read down and
   the tags made the ones you cannot use the loudest things in it. A row per
   operator gives the rail a column to scan, and the two states worth showing
   get one mark each: the amber edge for the one you are on, a hollow ring for
   the one whose file is not on this disk. */
.mmc-bn-list {
  display: flex; flex-direction: column;
  border-top: 1px solid var(--mmc-line); border-bottom: 1px solid var(--mmc-line);
}
.mmc-bn-pick {
  display: flex; align-items: center; gap: 9px; text-align: left;
  height: calc(31px * var(--mmc-type)); padding: 0 8px; cursor: pointer;
  background: none; border: 0; border-left: 2px solid transparent;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12.5px * var(--mmc-type));
  transition: background 110ms ease, color 110ms ease;
}
.mmc-bn-pick + .mmc-bn-pick { border-top: 1px solid var(--mmc-line); }
.mmc-bn-pick:hover { background: var(--mmc-wash); color: var(--mmc-text); }
.mmc-bn-pick.on {
  background: var(--mmc-tint); border-left-color: var(--mmc-accent);
  color: var(--mmc-strong); font-weight: 500;
}
.mmc-bn-pick:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-bn-pickname { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* The one state a row has to carry: this one's weights are not on the disk. A
   ring rather than a word — the word is under the list, in the sentence that
   says which file to go and get. */
.mmc-bn-pickmark {
  flex: none; width: 7px; height: 7px; border-radius: 50%;
  border: 1px solid var(--mmc-line-3);
}
.mmc-bn-pick.on .mmc-bn-pickmark { border-color: var(--mmc-off); }

/* What the operator you are on is for. Two lines and then an ellipsis: this is
   the sentence that separates Edges from Lines, not the manual — the whole of
   it is on the row's own tooltip, and the missing-file line below carries the
   only other thing the rail has to say. */
.mmc-bn-note {
  margin: 0; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-dim);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.mmc-bn-note.open { -webkit-line-clamp: unset; }
/* Pressing it is how the rest of the sentence arrives. A cursor and nothing
   else — a "more" link under a two-line note is more chrome than the note. */
.mmc-bn-note { cursor: pointer; }
/* What is missing, and where it goes. Ruled off on the left rather than boxed:
   it is an aside about this machine, not a warning about the choice. Clamped
   like the note, and opened the same way. */
.mmc-bn-needs {
  margin: 0; padding-left: 10px; border-left: 2px solid var(--mmc-line-3); cursor: pointer;
  font-size: calc(11px * var(--mmc-type)); line-height: 1.55; color: var(--mmc-off);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.mmc-bn-needs.open { -webkit-line-clamp: unset; }
.mmc-bn-weights { display: flex; }

/* --- the dials ----------------------------------------------------------- */
/* Name on the left, value on the right, track underneath, a hairline between
   one dial and the next. The value is tabular so a drag moves the number and
   not the layout. */
.mmc-bn-dial { display: flex; flex-direction: column; gap: 6px; }
.mmc-bn-dial + .mmc-bn-dial, .mmc-bn-dial + .mmc-bn-switch, .mmc-bn-switch + .mmc-bn-dial {
  border-top: 1px solid var(--mmc-line); padding-top: 12px;
}
.mmc-bn-diallabel {
  display: flex; justify-content: space-between; align-items: baseline; gap: 8px;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-bn-value {
  font-variant-numeric: tabular-nums; color: var(--mmc-strong);
  font-size: calc(12px * var(--mmc-type)); font-weight: 500;
}
.mmc-bn-range {
  -webkit-appearance: none; appearance: none; width: 100%; height: 16px;
  background: none; cursor: pointer; margin: 0;
}
.mmc-bn-range::-webkit-slider-runnable-track {
  height: 2px; border-radius: 1px; background: var(--mmc-line-2);
}
.mmc-bn-range::-moz-range-track { height: 2px; border-radius: 1px; background: var(--mmc-line-2); }
/* Square, not round. Every other slider on the internet has a dot on it; this
   is an instrument, and the mark that says where a stepped dial is sitting is
   the same shape as the ticks it is sitting between. */
.mmc-bn-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 4px; height: 14px; margin-top: -6px;
  border-radius: 1px; background: var(--mmc-strong); border: 0;
}
.mmc-bn-range::-moz-range-thumb {
  width: 4px; height: 14px; border-radius: 1px; background: var(--mmc-strong); border: 0;
}
.mmc-bn-range:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 3px; }
/* The stops a stepped dial actually has. Drawn only where there are few enough
   to count — a dial with forty of them is a continuous one and a row of forty
   ticks is a texture, not information. */
.mmc-bn-ticks { display: flex; justify-content: space-between; margin-top: -4px; }
.mmc-bn-ticks span { width: 1px; height: 4px; background: var(--mmc-line-2); }
.mmc-bn-text {
  width: 100%; box-sizing: border-box; padding: 5px 8px;
  border: 1px solid var(--mmc-line-2); border-radius: 6px;
  background: var(--mmc-wash); color: var(--mmc-strong);
  font: inherit; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-bn-text:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-bn-switch {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-bn-switch input { accent-color: var(--mmc-accent); }
/* A dial whose values are words rather than a range — how the colour is carried
   back, which way a tracing runs. Small stops in a row: the whole set is four
   short words, and a popover to choose between four words is a door in front of
   a door. */
.mmc-bn-opts { display: flex; flex-wrap: wrap; gap: 4px; }
.mmc-bn-opt {
  padding: 3px 9px; border-radius: 6px; cursor: pointer; font-family: inherit;
  background: none; border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type));
}
.mmc-bn-opt:hover { border-color: var(--mmc-line-2); color: var(--mmc-text); }
.mmc-bn-opt.on {
  background: var(--mmc-wash-2); border-color: var(--mmc-line-3); color: var(--mmc-strong);
}
.mmc-bn-opt:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }

/* --- where the file goes -------------------------------------------------- */
/* Pinned to the foot of the rail, which is also what stops the column ending in
   a hundred pixels of nothing. One line, and it is the line somebody goes
   looking for afterwards: which folder the thing they just made is in. */
.mmc-bn-where {
  margin-top: auto; padding-top: 16px;
  font-size: calc(11px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-off);
}
.mmc-bn-where b { display: block; font-weight: 600; color: var(--mmc-dim); }
.mmc-bn-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-dim);
  overflow-wrap: anywhere;
}

/* --- the light box -------------------------------------------------------- */
.mmc-bn-work {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  padding: 20px 24px 18px; gap: 14px;
}
.mmc-bn-box {
  flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center;
  background: var(--mmc-media-bg); border-radius: 14px; border: 1px solid var(--mmc-line);
  overflow: hidden; position: relative;
}
.mmc-bn-box.bare { background: none; border-style: dashed; }
/* The rectangle every layer shares, sized in script — see each bench's fit():
   a box with a ratio and both a max-width and a max-height either distorts or
   collapses, and every layer here has to occupy *exactly* the same rectangle,
   because that is what a wipe is. */
.mmc-bn-frame {
  position: relative; max-width: 100%; max-height: 100%;
  touch-action: none; cursor: ew-resize;
  --mmc-seam: 50%;
}
.mmc-bn-box.bare .mmc-bn-frame { cursor: default; width: 100%; height: 100%; }
.mmc-bn-layer {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: fill; display: block; user-select: none; -webkit-user-drag: none;
}
/* Only to the right of the seam. A clip path rather than a width, because a
   width would scale the picture instead of revealing it and the two halves
   would stop lining up — which is the one thing the wipe exists to show. */
.mmc-bn-over-layer { clip-path: inset(0 0 0 var(--mmc-seam)); transition: opacity 130ms ease; }
/* The seam. A hairline at rest, amber under the hand: the accent turns up
   exactly when the control is being used and is not spent standing still. */
.mmc-bn-seam {
  position: absolute; top: 0; bottom: 0; left: var(--mmc-seam);
  width: 1px; background: var(--mmc-strong); pointer-events: none;
  box-shadow: 0 0 0 1px var(--mmc-scrim-2);
  transition: background 120ms ease;
}
.mmc-bn-frame:hover .mmc-bn-seam, .mmc-bn-frame:active .mmc-bn-seam { background: var(--mmc-accent); }
.mmc-bn-grip {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--mmc-float); border: 1px solid var(--mmc-line-3);
  box-shadow: 0 4px 14px var(--mmc-shadow-soft);
  transition: border-color 120ms ease;
}
.mmc-bn-grip svg { stroke: var(--mmc-text); fill: none; stroke-width: 1.7; }
.mmc-bn-frame:hover .mmc-bn-grip { border-color: var(--mmc-accent); }
.mmc-bn-frame:hover .mmc-bn-grip svg { stroke: var(--mmc-accent); }
/* Which side is which, said once at the foot of each half. Without them a wipe
   sat halfway across a low-contrast frame is two pictures nobody can name. */
.mmc-bn-tag {
  position: absolute; bottom: 10px; padding: 3px 8px; border-radius: 7px;
  background: var(--mmc-scrim-3); color: var(--mmc-dim); pointer-events: none;
  font-size: calc(10px * var(--mmc-type)); letter-spacing: .12em; text-transform: uppercase;
}
.mmc-bn-tag.left { left: 10px; }
.mmc-bn-tag.right {
  right: 10px; max-width: 55%; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
/* The wait, on the glass rather than in the corner: the picture is what is being
   asked for, so the picture is what says it is coming. */
.mmc-bn-box.waiting .mmc-bn-over-layer { opacity: .5; }
/* Before there is a second picture there is nothing to wipe between, so the seam
   and the tags that name its two halves stay out of the way. A wipe drawn over
   one picture is a control that does nothing, sitting on the only thing there is
   to look at. */
.mmc-bn-frame.solo { cursor: default; }
.mmc-bn-frame.solo .mmc-bn-seam,
.mmc-bn-frame.solo .mmc-bn-grip,
.mmc-bn-frame.solo .mmc-bn-tag { display: none; }

/* The empty bench. An invitation rather than a message: there is one thing to do
   here and this says what it is. */
.mmc-bn-drop {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 10px; text-align: center;
}
.mmc-bn-drop svg { stroke: var(--mmc-line-3); fill: none; stroke-width: 1.2; }
.mmc-bn-dropline { margin: 0; font-size: calc(13.5px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-bn-dropnote { margin: 0; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-off); }

/* --- the cut -------------------------------------------------------------- */
/* The reference trim editor's own bar, mounted inline (trim.js's mountTrim)
   rather than drawn again. What is styled here is only the room it sits in: a
   bench is not a 640-pixel modal, so the row breathes wider and the track is
   tall enough to make the waveform legible instead of decorative. */
.mmc-bn-cut { flex: none; display: flex; flex-direction: column; gap: 8px; }
.mmc-bn-cut .mmc-trim-inline { display: flex; flex-direction: column; gap: 8px; }
.mmc-bn-cut .mmc-trim-track { height: 44px; }
.mmc-bn-cut .mmc-trim-inline-foot { display: flex; align-items: center; gap: 14px; }
.mmc-bn-cut .mmc-trim-read { font-size: calc(12.5px * var(--mmc-type)); }

/* --- run, and what came of it --------------------------------------------- */
.mmc-bn-foot { flex: none; display: flex; align-items: center; gap: 14px; }
.mmc-bn-run {
  height: calc(40px * var(--mmc-type)); padding: 0 28px; border-radius: 20px; border: 0;
  background: var(--mmc-accent); color: var(--mmc-on-accent); cursor: pointer;
  font-family: inherit; font-size: calc(13.5px * var(--mmc-type)); font-weight: 600;
}
.mmc-bn-run:hover:not(:disabled) { filter: brightness(1.08); }
/* Not a faded amber. A button that cannot be pressed is not the same button at
   thirty per cent — it is the room saying the job is not ready, and it says that
   in the same grey everything else unavailable is drawn in. */
.mmc-bn-run:disabled {
  background: var(--mmc-surface-2); color: var(--mmc-off); cursor: default;
}
/* The second press, where there is one: quieter than the first, because it is
   the smaller errand and lighting both the same way would make the room ask
   twice which one you meant. */
.mmc-bn-second {
  height: calc(40px * var(--mmc-type)); padding: 0 16px; border-radius: 20px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line-2);
  color: var(--mmc-text); cursor: pointer; font-family: inherit;
  font-size: calc(12.5px * var(--mmc-type));
}
.mmc-bn-second:hover:not(:disabled) { border-color: var(--mmc-line-3); background: var(--mmc-surface-2); }
.mmc-bn-second:disabled { opacity: .35; cursor: default; }
.mmc-bn-bad { color: var(--mmc-bad); font-size: calc(12.5px * var(--mmc-type)); }

/* The file that was written, and the doors it can go through. Absent until there
   is one — a row of dimmed Send buttons over an empty bench is chrome pretending
   to be a workflow. */
.mmc-bn-out { flex: none; display: none; }
.mmc-bn-out.on {
  display: flex; align-items: center; gap: 16px; padding: 11px 12px 11px 14px;
  border-radius: 12px; background: var(--mmc-surface); border: 1px solid var(--mmc-line);
}
.mmc-bn-outword { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.mmc-bn-outname {
  font-size: calc(12.5px * var(--mmc-type)); font-weight: 500; color: var(--mmc-strong);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-bn-outnote {
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off);
  font-variant-numeric: tabular-nums;
}

/* The doors.
   Two lines each, and the second is not a caption: it is the difference between
   them. A guide, an init image and a reference are three instructions to the
   sampler, and a row of same-width pills reading "Send to…" spends the one
   moment somebody is deciding on making them look interchangeable. */
.mmc-bn-doors { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.mmc-bn-door {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  max-width: calc(240px * var(--mmc-type)); padding: 8px 13px 9px;
  border-radius: 10px; text-align: left; cursor: pointer; font-family: inherit;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line-2);
  color: var(--mmc-text);
  transition: border-color 120ms ease, background 120ms ease;
}
.mmc-bn-door:hover:not(:disabled) { border-color: var(--mmc-accent); background: var(--mmc-wash-2); }
.mmc-bn-door:disabled { cursor: default; opacity: .55; }
.mmc-bn-doorname { font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; white-space: nowrap; }
.mmc-bn-doordoes { font-size: calc(11px * var(--mmc-type)); line-height: 1.4; color: var(--mmc-dim); }
/* The one door that takes the file exactly as it was written. The only amber in
   the row, and the same amber as the run button: the press that made the file
   and the press that spends it are one errand. Where nothing takes it as
   written, nothing is lit. */
.mmc-bn-door.lead {
  background: var(--mmc-accent); border-color: var(--mmc-accent); color: var(--mmc-on-accent);
}
.mmc-bn-door.lead .mmc-bn-doordoes { color: var(--mmc-on-accent); opacity: .75; }
.mmc-bn-door.lead:hover:not(:disabled) {
  background: var(--mmc-accent); border-color: var(--mmc-accent); filter: brightness(1.08);
}
/* Pressed already, and still pressable: a file can be a shot's guide and a
   reference on the same card. Dashed, the way an unready operator's ring is —
   the pack's one mark for "this is real but not what it was". */
.mmc-bn-door.done { border-style: dashed; border-color: var(--mmc-line-3); }
.mmc-bn-door.done.lead { border-style: solid; }

/* A narrow window puts the rail above the light box rather than beside it: the
   rail is the shorter of the two and the picture is the part that needs width. */
@media (max-width: 900px) {
  .mmc-bn-room { flex-direction: column; }
  .mmc-bn-rail {
    width: auto; border-right: 0; border-bottom: 1px solid var(--mmc-line);
    max-height: 45vh; padding: 14px 16px 16px;
  }
  .mmc-bn-where { margin-top: 16px; }
  .mmc-bn-work { padding: 14px 16px; }
  .mmc-bn-out.on { flex-direction: column; align-items: stretch; }
  .mmc-bn-out.on .mmc-bn-gap { display: none; }
  .mmc-bn-doors { justify-content: flex-start; }
  .mmc-bn-door { max-width: none; flex: 1 1 170px; }
}
@media (prefers-reduced-motion: reduce) {
  .mmc-bn-seam, .mmc-bn-grip, .mmc-bn-over-layer, .mmc-bn-pick, .mmc-bn-door { transition: none; }
}
`;
