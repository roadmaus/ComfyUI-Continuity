// Director's plan card, in the chat's transcript.
//
// A plan is read before it is changed, so the card is set as a document, not a
// form: the title large, the facts in one quiet line, the beats numbered with
// their shots indented under them and the seconds in a ragged column on the
// right. Nothing looks editable until it is pointed at; pressing a line turns it
// into a field the size of what it held. The two small choices on a row, a
// beat's weight and a shot's join, are the only controls drawn as controls,
// because they are choices among three words and a select says so.
//
// The card is a chat message (.mmc-ch-msg, which lays its children in a row),
// turned into a column here by the qualified selector, so it sits in the same
// column as every other reply.

export const css = `
.mmc-ch-msg.mmc-dr-card {
  flex-direction: column; gap: 14px;
  padding: 16px 18px; box-sizing: border-box;
  border: 1px solid var(--mmc-line); border-radius: 16px;
  background: var(--mmc-surface);
  font-size: calc(13.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-text);
}
.mmc-dr-card.mmc-dr-old { opacity: .6; }
.mmc-dr-card.busy { cursor: progress; }
.mmc-dr-card.busy > * { opacity: .7; }

/* --- the header ---------------------------------------------------------- */
.mmc-dr-head { display: flex; flex-direction: column; gap: 6px; }
.mmc-dr-titleline { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.mmc-dr-badge {
  flex: none; display: inline-flex; align-items: center; gap: 4px; align-self: center;
  padding: 2px 8px; border-radius: 10px;
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-accent);
  background: color-mix(in srgb, var(--mmc-accent) 14%, transparent);
}
.mmc-dr-badge svg { stroke: currentColor; fill: none; stroke-width: 2; }
.mmc-dr-title {
  font-size: calc(18px * var(--mmc-type)); font-weight: 500; letter-spacing: -.01em;
  color: var(--mmc-strong);
}
.mmc-dr-facts {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
  font-variant-numeric: tabular-nums;
}
.mmc-dr-dot, .mmc-dr-quiet { color: var(--mmc-faint); }
.mmc-dr-length { display: inline-flex; align-items: center; gap: 4px; }
.mmc-dr-number {
  width: 5ch; padding: 1px 4px; border-radius: 6px; font: inherit; color: var(--mmc-text);
  background: transparent; border: 1px solid transparent;
}
.mmc-dr-number:hover, .mmc-dr-number:focus { border-color: var(--mmc-line-3); background: var(--mmc-surface-2); }
.mmc-dr-look, .mmc-dr-assumed { display: flex; gap: 10px; align-items: baseline; }
.mmc-dr-key {
  flex: none; width: 6em;
  font-size: calc(11px * var(--mmc-type)); text-transform: uppercase; letter-spacing: .06em;
  color: var(--mmc-faint);
}
.mmc-dr-assumed ul { margin: 0; padding-left: 1.1em; color: var(--mmc-dim); }

/* --- sections ------------------------------------------------------------ */
.mmc-dr-section { display: flex; flex-direction: column; gap: 8px; }
.mmc-dr-heading {
  font-size: calc(11px * var(--mmc-type)); text-transform: uppercase; letter-spacing: .06em;
  color: var(--mmc-faint); padding-top: 10px; border-top: 1px solid var(--mmc-line);
}
.mmc-dr-beat { display: flex; flex-direction: column; gap: 4px; }
.mmc-dr-beatline, .mmc-dr-shot {
  display: grid; grid-template-columns: 4.6em 1fr auto; gap: 10px; align-items: baseline;
}
.mmc-dr-beatline { grid-template-columns: 1.6em 1fr auto 3.4em; color: var(--mmc-strong); }
.mmc-dr-shot { padding-left: 1.6em; color: var(--mmc-text); }
.mmc-dr-shot .mmc-dr-secs { width: 3.4em; }
.mmc-dr-num { color: var(--mmc-faint); font-variant-numeric: tabular-nums; }
.mmc-dr-secs {
  text-align: right; color: var(--mmc-dim); font-variant-numeric: tabular-nums; white-space: nowrap;
}
.mmc-dr-action { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mmc-dr-parts { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint); }
.mmc-dr-entity {
  display: grid; grid-template-columns: minmax(6em, auto) auto auto 1fr; gap: 10px; align-items: baseline;
}
.mmc-dr-name { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--mmc-strong); }
.mmc-dr-source { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint); white-space: nowrap; }
.mmc-dr-source.cited { color: var(--mmc-blue); }

/* --- words that change when pressed -------------------------------------- */
.mmc-dr-text { min-width: 0; word-break: break-word; border-radius: 6px; }
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
.mmc-dr-input.mmc-dr-title { font-size: calc(18px * var(--mmc-type)); font-weight: 500; }
.mmc-dr-select {
  max-width: 100%; padding: 1px 4px; border-radius: 6px; cursor: pointer;
  font: inherit; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
}
.mmc-dr-select:hover { color: var(--mmc-text); }
.mmc-dr-tag { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-faint); }

/* --- what is said under it ----------------------------------------------- */
.mmc-dr-warn { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-warn); }
.mmc-dr-error { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-bad); }
.mmc-dr-foot {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  padding-top: 10px; border-top: 1px solid var(--mmc-line);
  font-size: calc(12.5px * var(--mmc-type));
}
.mmc-dr-check { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; color: var(--mmc-dim); }
.mmc-dr-check input { margin: 0; accent-color: var(--mmc-accent); }

@media (max-width: 560px) {
  .mmc-dr-shot { padding-left: 0; grid-template-columns: 1fr auto; }
  .mmc-dr-shot > :first-child { grid-column: 1 / -1; }
  .mmc-dr-entity { grid-template-columns: auto auto 1fr; }
  .mmc-dr-entity > :last-child { grid-column: 1 / -1; }
}
`;
