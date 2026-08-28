// The ControlNet bench. See control.js for what the surface is; this is how it
// is drawn.
//
// It borrows the editor shell's proportions on purpose — a 54-pixel bar with the
// wordmark at the left, a hairline under it, a rail down one side — because a
// person who has opened the fullscreen editor once has already learned where the
// way out is. What is new here is the light box, and it is the only thing on the
// surface allowed to be loud.

export const css = `
/* The bench takes the whole viewport rather than a card in the middle of it.
   The overlay it rides on is the picker's — fixed, scrimmed, centred with a
   40-pixel gutter — and none of that is wanted for a room, so all three are
   undone here rather than a second overlay being invented. */
.mmc-overlay.mmc-ctl-over {
  padding: 0; background: var(--mmc-bg); align-items: stretch; justify-content: stretch;
}
/* A file over the room. The whole surface is the target, so the whole surface
   says so — an inset ring rather than a highlighted well, because there is no
   well and drawing one under the pointer would be inventing a target the moment
   somebody stopped needing it. */
.mmc-overlay.mmc-ctl-over.dropping::after {
  content: ""; position: absolute; inset: 10px; border-radius: 18px;
  border: 2px dashed var(--mmc-accent); pointer-events: none;
}
.mmc-ctl {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  color: var(--mmc-text); overflow: hidden;
}

/* --- the bar ------------------------------------------------------------- */
.mmc-ctl-bar {
  flex: none; min-height: 54px; display: flex; align-items: center; gap: 10px;
  padding: 0 18px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-ctl-mark { display: flex; align-items: center; }
.mmc-ctl-word { font-size: calc(13px * var(--mmc-type)); font-weight: 600; }
.mmc-ctl-slash { color: var(--mmc-off); }
.mmc-ctl-here { font-size: calc(13px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-ctl-gap { flex: 1; }

.mmc-ctl-room { flex: 1; min-height: 0; display: flex; }

/* --- the bench, down the left -------------------------------------------- */
/* A fixed measure rather than a share of the window: everything in it is a
   label, a list or a slider, and none of those get better at 600 pixels — while
   the light box, which does, gets whatever is left. */
.mmc-ctl-bench {
  flex: none; width: calc(320px * var(--mmc-type)); min-width: 0;
  border-right: 1px solid var(--mmc-line); overflow: auto; overscroll-behavior: contain;
  padding: 22px 20px 28px; display: flex; flex-direction: column; gap: 26px;
}
.mmc-ctl-sect { display: flex; flex-direction: column; gap: 12px; }
/* The section's name, and the rule that says how far the section reaches — the
   dashboard's eyebrow, so the two surfaces are labelled in one voice. */
.mmc-ctl-eyebrow {
  display: flex; align-items: center; gap: 12px;
  font-size: calc(11px * var(--mmc-type)); font-weight: 600;
  letter-spacing: .14em; text-transform: uppercase; color: var(--mmc-off);
}
.mmc-ctl-rule { flex: 1; height: 1px; background: var(--mmc-line); }

.mmc-ctl-file { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.mmc-ctl-filename {
  font-size: calc(13.5px * var(--mmc-type)); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-ctl-filenote, .mmc-ctl-empty {
  margin: 0; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ctl-verb {
  width: 100%; display: flex; white-space: nowrap; overflow: hidden; align-items: center; justify-content: center; gap: 7px;
  height: calc(34px * var(--mmc-type)); border-radius: 10px; cursor: pointer;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-family: inherit; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-ctl-verb:hover:not(:disabled) { background: var(--mmc-surface-2); border-color: var(--mmc-line-2); }
.mmc-ctl-verb:disabled { opacity: .5; cursor: default; }
.mmc-ctl-verb svg { flex: none; stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-ctl-verb span { overflow: hidden; text-overflow: ellipsis; }

/* The tracings. A wrapping row of names rather than a dropdown, because the
   choice between them is the choice this bench is *for* — and a list you can
   see all of is a list you can go along. */
.mmc-ctl-ops { display: flex; flex-wrap: wrap; gap: 7px; }
.mmc-ctl-op {
  display: flex; align-items: center; gap: 6px;
  padding: 0 12px; height: calc(32px * var(--mmc-type)); border-radius: 16px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12.5px * var(--mmc-type));
  cursor: pointer; transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
}
.mmc-ctl-op:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-ctl-op.on {
  background: var(--mmc-wash-2); border-color: var(--mmc-line-3); color: var(--mmc-strong);
  font-weight: 500;
}
/* Named, drawn open, and still pressable. Depth and Pose are the two guides
   everybody reaches for first, and a bench that simply lacked them would read
   as one that is missing them by accident — so they are here, dashed rather
   than solid because the file is not, and they take the press because what
   somebody needs at that point is to read which file to go and get. */
.mmc-ctl-op.unready { border-style: dashed; color: var(--mmc-off); }
.mmc-ctl-lack {
  font-size: calc(10px * var(--mmc-type)); letter-spacing: .08em; text-transform: uppercase;
  color: var(--mmc-off);
}
.mmc-ctl-note {
  margin: 0; font-size: calc(12px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-dim);
}
/* What is missing, under the note that says what the tracing is for. Ruled off
   on the left rather than boxed: it is an aside about this machine, not a
   warning about the choice. */
.mmc-ctl-needs {
  margin: 0; padding-left: 10px; border-left: 2px solid var(--mmc-line-3);
  font-size: calc(11.5px * var(--mmc-type)); line-height: 1.55; color: var(--mmc-off);
}

/* The dials. Label and value on one line above the track, so the number is read
   where the name is rather than hunted for at the end of the slider. */
.mmc-ctl-dial { display: flex; flex-direction: column; gap: 5px; }
.mmc-ctl-diallabel {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ctl-value {
  font-variant-numeric: tabular-nums; color: var(--mmc-text);
  font-size: calc(12px * var(--mmc-type));
}
.mmc-ctl-range {
  -webkit-appearance: none; appearance: none; width: 100%; height: 18px;
  background: none; cursor: pointer; margin: 0;
}
.mmc-ctl-range::-webkit-slider-runnable-track {
  height: 3px; border-radius: 2px; background: var(--mmc-wash-2);
}
.mmc-ctl-range::-moz-range-track { height: 3px; border-radius: 2px; background: var(--mmc-wash-2); }
.mmc-ctl-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 13px; height: 13px; margin-top: -5px;
  border-radius: 50%; background: var(--mmc-strong); border: 0;
}
.mmc-ctl-range::-moz-range-thumb {
  width: 13px; height: 13px; border-radius: 50%; background: var(--mmc-strong); border: 0;
}
.mmc-ctl-range:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 4px; }
.mmc-ctl-text {
  width: 100%; box-sizing: border-box; padding: 5px 8px;
  border: 1px solid var(--mmc-wash-2); border-radius: 6px;
  background: var(--mmc-wash); color: var(--mmc-strong);
  font: inherit; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-ctl-text:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-ctl-switch {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ctl-switch input { accent-color: var(--mmc-accent); }
/* Where the weights pill stands. The pill itself is the node's — same class,
   same popover, same chooser — so there is nothing to style here but the room
   it stands in: a row of its own, so it does not sit on the note's last line. */
.mmc-ctl-weights { display: flex; }

/* --- the light box -------------------------------------------------------- */
.mmc-ctl-work {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  padding: 22px 26px 20px; gap: 14px;
}
.mmc-ctl-box {
  flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center;
  background: var(--mmc-media-bg); border-radius: 16px; border: 1px solid var(--mmc-line);
  overflow: hidden; position: relative;
}
.mmc-ctl-box.bare { background: none; border-style: dashed; }
/* The rectangle both layers share, sized in script from the source's own shape
   — see the bench's fit() for why the obvious aspect-ratio version cannot. The
   empty bench has no shape to take and fills the room instead. */
.mmc-ctl-frame {
  position: relative; max-width: 100%; max-height: 100%;
  touch-action: none; cursor: ew-resize;
  --mmc-seam: 50%;
}
.mmc-ctl-box.bare .mmc-ctl-frame { cursor: default; width: 100%; height: 100%; }
.mmc-ctl-layer {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: fill; display: block; user-select: none; -webkit-user-drag: none;
}
/* Only to the right of the seam. A clip path rather than a width, because a
   width would scale the picture instead of revealing it and the two halves
   would no longer line up — which is the one thing the wipe exists to show. */
.mmc-ctl-traced { clip-path: inset(0 0 0 var(--mmc-seam)); }
/* The seam. A hairline at rest, amber under the hand: the accent turns up
   exactly when the control is being used and is not spent standing still. */
.mmc-ctl-seam {
  position: absolute; top: 0; bottom: 0; left: var(--mmc-seam);
  width: 1px; background: var(--mmc-strong); pointer-events: none;
  box-shadow: 0 0 0 1px var(--mmc-scrim-2);
  transition: background 120ms ease;
}
.mmc-ctl-frame:hover .mmc-ctl-seam, .mmc-ctl-frame:active .mmc-ctl-seam { background: var(--mmc-accent); }
.mmc-ctl-grip {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  width: 30px; height: 30px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: var(--mmc-float); border: 1px solid var(--mmc-line-3);
  box-shadow: 0 4px 14px var(--mmc-shadow-soft);
  transition: border-color 120ms ease;
}
.mmc-ctl-grip svg { stroke: var(--mmc-text); fill: none; stroke-width: 1.7; }
.mmc-ctl-frame:hover .mmc-ctl-grip { border-color: var(--mmc-accent); }
.mmc-ctl-frame:hover .mmc-ctl-grip svg { stroke: var(--mmc-accent); }
/* Which side is which, said once at the foot of each half. Without them a wipe
   sat halfway across a low-contrast frame is two pictures nobody can name. */
.mmc-ctl-tag {
  position: absolute; bottom: 10px; padding: 3px 9px; border-radius: 9px;
  background: var(--mmc-scrim-3); color: var(--mmc-dim); pointer-events: none;
  font-size: calc(10.5px * var(--mmc-type)); letter-spacing: .1em; text-transform: uppercase;
}
.mmc-ctl-tag.left { left: 10px; }
/* Room for a filename, which is what this says for the length of the arrival
   sweep — and an ellipsis rather than a second line, because it sits on the
   picture and a tag that grows upward covers the thing being judged. */
.mmc-ctl-tag.right {
  right: 10px; max-width: 55%; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
/* The wait, on the glass rather than in the corner: the picture is what is
   being asked for, so the picture is what says it is coming. Barely there —
   at ninety milliseconds a spinner would be a flash of chrome per drag. */
.mmc-ctl-box.waiting .mmc-ctl-traced { opacity: .55; }
.mmc-ctl-traced { transition: opacity 120ms ease; }
/* The arrival sweep. The seam is dragged by hand every other second of a
   session and never animates; for the half second after a file is written it
   runs out to the edge and back on its own, which is the bench showing you the
   drawing alone under its new name. Written as a state on the frame rather than
   a keyframe so it is the same clip-path and the same left the hand moves —
   there is one seam, and this is it being moved by something other than a
   pointer. */
.mmc-ctl-frame.sweeping .mmc-ctl-traced {
  transition: clip-path 520ms cubic-bezier(.22, 1, .36, 1), opacity 120ms ease;
}
.mmc-ctl-frame.sweeping .mmc-ctl-seam {
  transition: left 520ms cubic-bezier(.22, 1, .36, 1), background 120ms ease;
}
.mmc-ctl-frame.sweeping .mmc-ctl-tag.right { color: var(--mmc-strong); }

/* The empty bench. An invitation rather than a message: there is one thing to
   do here and this says what it is. */
.mmc-ctl-drop {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 10px; text-align: center;
}
.mmc-ctl-drop svg { stroke: var(--mmc-line-3); fill: none; stroke-width: 1.2; }
.mmc-ctl-dropline { margin: 0; font-size: calc(14px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-ctl-dropnote { margin: 0; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-off); }

/* --- the cut ------------------------------------------------------------- */
/*
 * This is the reference trim editor's own bar, mounted inline (trim.js's
 * mountTrim) rather than drawn again — handles, rigid-window drag, arrow keys,
 * looping transport and the waveform behind them, all of it the same code the
 * modal runs. What is styled here is only the room it sits in, because a bench
 * is not a 640-pixel modal: the row breathes wider and the buttons that reset
 * the range sit under it rather than in a foot beside a Cancel that no longer
 * exists.
 */
.mmc-ctl-cut { flex: none; display: flex; flex-direction: column; gap: 8px; }
.mmc-ctl-cut .mmc-trim-inline { display: flex; flex-direction: column; gap: 8px; }
/* Nothing above it to be told apart from, so it can be taller than the modal's
   thirty pixels — which is what makes the waveform under the handles legible
   instead of decorative. */
.mmc-ctl-cut .mmc-trim-track { height: 44px; }
.mmc-ctl-cut .mmc-trim-inline-foot { display: flex; align-items: center; gap: 14px; }
.mmc-ctl-cut .mmc-trim-read { font-size: calc(12.5px * var(--mmc-type)); }

/* --- run, and what came of it --------------------------------------------- */
.mmc-ctl-foot { flex: none; display: flex; align-items: center; gap: 14px; }
.mmc-ctl-run {
  height: calc(42px * var(--mmc-type)); padding: 0 30px; border-radius: 21px; border: 0;
  background: var(--mmc-accent); color: var(--mmc-on-accent); cursor: pointer;
  font-family: inherit; font-size: calc(14px * var(--mmc-type)); font-weight: 600;
}
.mmc-ctl-run:hover:not(:disabled) { filter: brightness(1.08); }
.mmc-ctl-run:disabled { opacity: .3; cursor: default; }
.mmc-ctl-bad { color: var(--mmc-bad); font-size: calc(12.5px * var(--mmc-type)); }

/* The file that was written, and the doors it can go through. Absent until
   there is one — a row of dimmed Send buttons over an empty bench is chrome
   pretending to be a workflow. */
.mmc-ctl-out { flex: none; display: none; }
.mmc-ctl-out.on {
  display: flex; align-items: center; gap: 16px; padding: 12px 12px 12px 16px;
  border-radius: 14px; background: var(--mmc-surface); border: 1px solid var(--mmc-line);
}
.mmc-ctl-outword { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.mmc-ctl-outname {
  font-size: calc(13px * var(--mmc-type)); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-ctl-outnote { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-off); }

/* The doors.
   Two lines each, and the second one is not a caption: it is the difference
   between the three of them. A guide, an init image and a reference are three
   instructions to the sampler, and a row of same-width pills reading "Send
   to…" spends the one moment somebody is deciding on making them look
   interchangeable. Wrapping, because a narrow window should stack them rather
   than shrink three explanations into three columns of one word. */
.mmc-ctl-doors { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.mmc-ctl-door {
  display: flex; flex-direction: column; align-items: flex-start; gap: 3px;
  max-width: calc(250px * var(--mmc-type)); padding: 9px 14px 10px;
  border-radius: 12px; text-align: left; cursor: pointer; font-family: inherit;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line-2);
  color: var(--mmc-text);
  transition: border-color 120ms ease, background 120ms ease;
}
.mmc-ctl-door:hover:not(:disabled) { border-color: var(--mmc-accent); background: var(--mmc-wash-2); }
.mmc-ctl-door:disabled { cursor: default; opacity: .55; }
.mmc-ctl-doorname { font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; white-space: nowrap; }
/* --mmc-dim, not the --mmc-off a footnote gets. This line is the difference
   between the doors and it is read while a decision is being made, which is the
   same job the tracing's own note does in the rail — so it is set at the same
   weight. */
.mmc-ctl-doordoes {
  font-size: calc(11px * var(--mmc-type)); line-height: 1.4; color: var(--mmc-dim);
}
/* The one door that takes the file exactly as it was written — which on a
   family with a control branch is the door this bench was opened for. The only
   amber in the row, and the same amber as Trace: the press that made the file
   and the press that spends it are one errand, and they are lit the same way.
   Where nothing takes it as written, nothing is lit — see paintResult. */
.mmc-ctl-door.lead {
  background: var(--mmc-accent); border-color: var(--mmc-accent); color: var(--mmc-on-accent);
}
.mmc-ctl-door.lead .mmc-ctl-doordoes { color: var(--mmc-on-accent); opacity: .75; }
.mmc-ctl-door.lead:hover:not(:disabled) {
  background: var(--mmc-accent); border-color: var(--mmc-accent); filter: brightness(1.08);
}
/* Pressed already, and still pressable: a drawing can be a shot's guide and a
   reference on the same card, and the send that stays in the room is the one
   somebody may want to repeat after re-trimming. Dashed, the way an unready
   tracing is — the pack's one mark for "this is real but not what it was". */
.mmc-ctl-door.done { border-style: dashed; border-color: var(--mmc-line-3); }
.mmc-ctl-door.done.lead { border-style: solid; }

/* A narrow window puts the bench above the light box rather than beside it: the
   rail is the shorter of the two and the picture is the part that needs the
   width. */
@media (max-width: 900px) {
  .mmc-ctl-room { flex-direction: column; }
  .mmc-ctl-bench {
    width: auto; border-right: 0; border-bottom: 1px solid var(--mmc-line);
    max-height: 45vh; padding: 16px 18px 20px;
  }
  .mmc-ctl-work { padding: 16px 18px 16px; }
  /* The doors are the widest thing in the shelf, so below the break the name of
     the file goes above them rather than beside them. */
  .mmc-ctl-out.on { flex-direction: column; align-items: stretch; }
  .mmc-ctl-out.on .mmc-ctl-gap { display: none; }
  .mmc-ctl-doors { justify-content: flex-start; }
  .mmc-ctl-door { max-width: none; flex: 1 1 180px; }
}
@media (prefers-reduced-motion: reduce) {
  .mmc-ctl-seam, .mmc-ctl-grip, .mmc-ctl-traced, .mmc-ctl-op, .mmc-ctl-door { transition: none; }
  .mmc-ctl-frame.sweeping .mmc-ctl-traced,
  .mmc-ctl-frame.sweeping .mmc-ctl-seam { transition: none; }
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
