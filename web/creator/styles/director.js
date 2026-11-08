// Director's plan card, in the chat's transcript.
//
// A plan is read before it is changed, so the card is set as a document, not a
// form: the title large, the facts in one quiet line, the piece drawn to scale
// once as a strip, then the beats numbered with their shots under them and the
// seconds in a column on the right. Nothing looks editable until it is pointed
// at; pressing a line turns it into a field the size of what it held. The two
// small choices on a row, a beat's weight and a shot's join, are selects, but
// drawn as their word with a chevron, so the list still reads as a shot list.
//
// The strip is the one drawn thing on the card. It is the arithmetic the card
// already does, beats cut into shots cut into clips, at the widths the seconds
// give them; the accent is kept for the shot pointed at, on the strip and in
// the list at once.
//
// The card is a chat message (.mmc-ch-msg, which lays its children in a row),
// turned into a column here by the qualified selector, so it sits in the same
// column as every other reply.

export const css = `
.mmc-ch-msg.mmc-dr-card {
  flex-direction: column; gap: 16px;
  padding: 18px 20px 14px; box-sizing: border-box;
  border: 1px solid var(--mmc-line); border-radius: 14px;
  background: var(--mmc-surface);
  font-size: calc(13.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-text);
}
.mmc-dr-card.mmc-dr-old { opacity: .6; }
.mmc-dr-card.busy { cursor: progress; }
.mmc-dr-card.busy > * { opacity: .7; }

/* --- the header ---------------------------------------------------------- */
.mmc-dr-head { display: flex; flex-direction: column; gap: 4px; }
.mmc-dr-titleline { display: flex; align-items: flex-start; gap: 9px; min-width: 0; }
.mmc-dr-mark { flex: none; display: inline-flex; margin-top: calc(4px * var(--mmc-type)); color: var(--mmc-accent); }
.mmc-dr-mark svg { stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-dr-title {
  font-size: calc(19px * var(--mmc-type)); font-weight: 600; letter-spacing: -.015em; line-height: 1.3;
  color: var(--mmc-strong);
}
.mmc-dr-facts {
  display: flex; flex-wrap: wrap; align-items: baseline; column-gap: 14px; row-gap: 2px;
  padding-left: 25px;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
  font-variant-numeric: tabular-nums;
}
.mmc-dr-quiet { color: var(--mmc-faint); }
.mmc-dr-facts .mmc-dr-quiet { margin-left: -10px; }
.mmc-dr-facts .mmc-dr-rail { margin-left: auto; }
.mmc-dr-length { display: inline-flex; align-items: baseline; gap: 3px; }
.mmc-dr-number {
  width: 3ch; field-sizing: content; min-width: 1ch; padding: 0 1px; border-radius: 3px;
  font: inherit; color: var(--mmc-strong); text-align: right;
  background: transparent; border: 0; border-bottom: 1px dashed var(--mmc-line-3);
  -moz-appearance: textfield;
}
.mmc-dr-number::-webkit-inner-spin-button, .mmc-dr-number::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
.mmc-dr-number:hover { background: var(--mmc-wash); }
.mmc-dr-number:focus { outline: 0; background: var(--mmc-surface-2); border-bottom-color: var(--mmc-accent); }
.mmc-dr-look, .mmc-dr-assumed {
  display: grid; grid-template-columns: 5.2em 1fr; gap: 12px; align-items: baseline;
  margin-top: 6px;
}
.mmc-dr-assumed { margin-top: 0; }
.mmc-dr-key { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-faint); }
.mmc-dr-assumed ul { margin: 0; padding: 0; list-style: none; color: var(--mmc-dim); }
.mmc-dr-assumed li + li { margin-top: 1px; }

/* --- the strip ----------------------------------------------------------- */
.mmc-dr-strip { display: flex; gap: 5px; }
.mmc-dr-sbeat { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.mmc-dr-sbar { display: flex; gap: 2px; height: 22px; }
.mmc-dr-sshot {
  flex: 1 1 0; min-width: 3px; display: flex; overflow: hidden;
  border-radius: 3px; background: color-mix(in srgb, var(--mmc-ink) 13%, transparent);
  transition: background-color .12s ease;
}
.mmc-dr-sbeat:first-child .mmc-dr-sshot:first-child { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
.mmc-dr-sbeat:last-child .mmc-dr-sshot:last-child { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
.mmc-dr-sclip { flex: 1 1 0; min-width: 0; }
/* A shot too long for one clip: the seam the run carries it on across. */
.mmc-dr-sclip + .mmc-dr-sclip { border-left: 1px dashed var(--mmc-surface); }
.mmc-dr-sshot.hot { background: var(--mmc-accent); }
.mmc-dr-slabel {
  display: flex; gap: 6px; min-width: 0; overflow: hidden; white-space: nowrap;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint); font-variant-numeric: tabular-nums;
}

/* --- sections ------------------------------------------------------------ */
.mmc-dr-section { display: flex; flex-direction: column; gap: 10px; }
.mmc-dr-heading {
  font-size: calc(12px * var(--mmc-type)); font-weight: 500; color: var(--mmc-dim);
  padding-top: 12px; border-top: 1px solid var(--mmc-line);
}
.mmc-dr-beat { display: flex; flex-direction: column; gap: 2px; }
.mmc-dr-beatline, .mmc-dr-shot {
  display: grid; gap: 10px; align-items: baseline; border-radius: 6px;
}
.mmc-dr-beatline {
  grid-template-columns: 1.4em 1fr 7.4em 3.2em; margin-bottom: 2px;
  font-weight: 500; color: var(--mmc-strong);
}
.mmc-dr-shot {
  grid-template-columns: 1.4em 6.6em 1fr 3.2em; color: var(--mmc-text);
  margin: 0 -6px; padding: 1px 6px;
  transition: background-color .12s ease;
}
.mmc-dr-shot::before { content: ""; }
.mmc-dr-shot.hot { background: color-mix(in srgb, var(--mmc-accent) 9%, transparent); }
.mmc-dr-shot.hot .mmc-dr-secs { color: var(--mmc-accent); }
.mmc-dr-num { color: var(--mmc-faint); font-weight: 400; font-variant-numeric: tabular-nums; }
.mmc-dr-secs {
  text-align: right; color: var(--mmc-dim); font-weight: 400;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.mmc-dr-beatline .mmc-dr-secs { color: var(--mmc-text); }
.mmc-dr-action { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.mmc-dr-parts { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint); }
.mmc-dr-entity {
  display: grid; grid-template-columns: 7em 4.4em auto 1fr; gap: 10px; align-items: baseline;
}
.mmc-dr-name { font-weight: 500; color: var(--mmc-strong); overflow: hidden; text-overflow: ellipsis; }
.mmc-dr-source { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-faint); white-space: nowrap; }
.mmc-dr-source.cited { color: var(--mmc-blue); }

/* --- words that change when pressed -------------------------------------- */
.mmc-dr-text { min-width: 0; word-break: break-word; border-radius: 4px; }
.mmc-dr-text.empty { color: var(--mmc-faint); font-style: italic; }
.mmc-dr-text[role="button"] { cursor: text; }
.mmc-dr-text[role="button"]:hover { background: var(--mmc-wash); box-shadow: 0 0 0 3px var(--mmc-wash); }
.mmc-dr-text[role="button"]:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-dr-input {
  width: 100%; box-sizing: border-box; resize: none; overflow: hidden;
  margin: -3px; padding: 2px 3px; border-radius: 6px;
  font: inherit; line-height: inherit; color: var(--mmc-text);
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-accent); outline: 0;
}
.mmc-dr-input.mmc-dr-title { font-size: calc(19px * var(--mmc-type)); font-weight: 600; }
/* A choice among three words, drawn as the word it holds. */
.mmc-dr-beatline .mmc-dr-select, .mmc-dr-beatline .mmc-dr-tag { justify-self: end; }
.mmc-dr-select {
  justify-self: start; max-width: 100%; padding: 0 16px 0 4px; margin-left: -4px; border-radius: 4px;
  cursor: pointer; -webkit-appearance: none; appearance: none;
  font: inherit; font-size: calc(12px * var(--mmc-type)); font-weight: 400; color: var(--mmc-dim);
  background: transparent no-repeat right 3px center / 9px 9px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'%3E%3Cpath d='M2 3.5l3 3 3-3' fill='none' stroke='%23888' stroke-width='1.4'/%3E%3C/svg%3E");
  border: 0;
}
.mmc-dr-select:hover { color: var(--mmc-text); background-color: var(--mmc-wash); }
.mmc-dr-select:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-dr-tag { font-size: calc(12px * var(--mmc-type)); font-weight: 400; color: var(--mmc-faint); white-space: nowrap; }

/* --- what is said under it ----------------------------------------------- */
.mmc-dr-warn, .mmc-dr-error {
  padding: 7px 10px; border-radius: 8px; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-dr-warn { color: var(--mmc-warn); background: color-mix(in srgb, var(--mmc-warn) 9%, transparent); }
.mmc-dr-error { color: var(--mmc-bad); background: color-mix(in srgb, var(--mmc-bad) 9%, transparent); }
.mmc-dr-foot {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  padding-top: 12px; border-top: 1px solid var(--mmc-line);
  font-size: calc(12.5px * var(--mmc-type));
}
.mmc-dr-check { display: inline-flex; align-items: center; gap: 7px; cursor: pointer; color: var(--mmc-text); }
.mmc-dr-check input { margin: 0; accent-color: var(--mmc-accent); }

/* --- prep: what has been made, and what waits for the person -------------- */
.mmc-dr-state {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-faint); white-space: nowrap;
}
.mmc-dr-state.pending { color: var(--mmc-accent); }
.mmc-dr-state.approved { color: var(--mmc-dim); }
.mmc-dr-state.stale, .mmc-dr-state.failed { color: var(--mmc-warn); }
.mmc-dr-thumb {
  width: 22px; height: 22px; object-fit: cover; border-radius: 4px; flex: none;
  align-self: center; background: var(--mmc-wash);
}
.mmc-dr-frame {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint);
}
.mmc-ch-door.mmc-dr-make, .mmc-ch-door.mmc-dr-approve, .mmc-ch-door.mmc-dr-run:not(:disabled) {
  background: var(--mmc-accent); border-color: var(--mmc-accent); color: var(--mmc-on-accent);
}
.mmc-ch-door.mmc-dr-make:hover:not(:disabled), .mmc-ch-door.mmc-dr-approve:hover:not(:disabled),
.mmc-ch-door.mmc-dr-run:hover:not(:disabled) {
  background: color-mix(in srgb, var(--mmc-accent) 85%, var(--mmc-ink));
}
/* While the run goes: Stop is the one thing to press, and it is not a call
   to action, so it keeps the door's own quiet face with the warning hue. */
.mmc-ch-door.mmc-dr-stop { color: var(--mmc-warn); border-color: color-mix(in srgb, var(--mmc-warn) 45%, transparent); }
/* On a prep render's card: which row of the plan it is for, and its verdict. */
.mmc-dr-for { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint); white-space: nowrap; }
.mmc-dr-verdict { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-dr-verdict.stale { color: var(--mmc-warn); }

@media (prefers-reduced-motion: reduce) {
  .mmc-dr-sshot, .mmc-dr-shot { transition: none; }
}
@media (max-width: 560px) {
  .mmc-dr-facts { padding-left: 0; }
  .mmc-dr-facts .mmc-dr-rail { margin-left: 0; }
  .mmc-dr-shot { grid-template-columns: 1fr auto; row-gap: 0; margin-left: calc(1.4em + 4px); }
  .mmc-dr-shot::before { display: none; }
  .mmc-dr-shot > :first-child { grid-column: 1 / -1; }
  .mmc-dr-beatline { grid-template-columns: 1.4em 1fr auto; }
  .mmc-dr-beatline .mmc-dr-secs { grid-column: 3; }
  .mmc-dr-beatline > .mmc-dr-select, .mmc-dr-beatline > .mmc-dr-tag { grid-column: 2; grid-row: 2; justify-self: start; }
  .mmc-dr-entity { grid-template-columns: auto auto 1fr; }
  .mmc-dr-entity > :last-child { grid-column: 1 / -1; }
}
`;
