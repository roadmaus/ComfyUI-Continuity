// The refiner and the rewrite.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- the refiner ---------------------------------------------------------- */
/* One press refines; the corner opens the settings. The corner sits inside the
   tile's own rounded box rather than floating over it, so the rail keeps its
   alignment and the control cannot be mistaken for a badge on its neighbour. */
.mmc-refine-split { position: relative; display: flex; }
/* Anchored off the tile's centre rather than the wrapper's left edge, so a
   longer label cannot slide it off the corner it belongs in — and measured from
   the tile's own size, because the shell draws a 44px square and the two fixed
   offsets that suited 56 hung the chevron out past its right edge. */
.mmc-refine-more {
  position: absolute; left: 50%; width: 18px; height: 18px;
  top: calc(var(--mmc-tool-tile) - 20px);
  margin-left: calc(var(--mmc-tool-tile) / 2 - 20px);
  display: flex; align-items: center; justify-content: center;
  background: none; border: 0; border-radius: 6px; padding: 0;
  color: var(--mmc-off); cursor: pointer; transition: color .12s ease, background .12s ease;
}
.mmc-refine-more svg { width: 12px; height: 12px; }
.mmc-refine-split:hover .mmc-refine-more { color: var(--mmc-dim); }
.mmc-refine-more:hover { color: var(--mmc-text); background: var(--mmc-surface-3); }
/* Only the keyboard gets a ring. Clicking left one sitting on the tile, which
   is exactly what made the old control read as a notification dot. */
.mmc-refine-more:focus:not(:focus-visible) { outline: none; }

/* A refine is a round trip to a local model and can take a minute. The pulse is
   the only thing saying the click landed. */
.mmc-tool.busy, .mmc-pill.busy { color: var(--mmc-accent); cursor: progress; }
.mmc-tool.busy .mmc-tool-icon { animation: mmc-pulse 1.4s ease-in-out infinite; }
.mmc-pill.busy { animation: mmc-pulse 1.4s ease-in-out infinite; }
@keyframes mmc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }

/* On the timeline bar the same control is a pill, so the corner becomes an
   ordinary chevron at the end of the label. */
.mmc-tl-refine .mmc-tool-icon {
  width: auto; height: auto; background: none; border: 0; border-radius: 0;
}
.mmc-tl-refine svg { width: 15px; height: 15px; }
/* Beside it, and quieter than it: undoing is the rarer press of the two. */
.mmc-tl-unrefine { color: var(--mmc-dim); }
.mmc-tl-unrefine:hover { color: var(--mmc-text); }
.mmc-refine-split.pill { align-items: stretch; }
.mmc-refine-split.pill .mmc-refine-more {
  position: static; width: 24px; height: 38px; border-radius: 0 19px 19px 0;
  margin-left: -10px; background: var(--mmc-surface-2);
  border: 1px solid var(--mmc-line); border-left: 0; color: var(--mmc-dim);
}
.mmc-refine-split.pill .mmc-refine-more:hover { background: var(--mmc-surface-3); }
.mmc-refine-split.pill .mmc-pill { padding-right: 16px; }

/* A card, not a strip: 264px stacked every section into a scroll of wrapped
   chips and paragraphs. At 420 the chips sit in rows, the dials share a line,
   and the popover reads top to bottom as decisions rather than documentation. */
.mmc-refine-pop { width: 420px; max-width: calc(100vw - 24px); padding: 10px; }

/* The header holds the first decision: the title names the tool, the switch
   says where it runs. A segmented track rather than two loose chips — this is
   a mode, not a tag. */
.mmc-refine-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; padding: 2px 2px 8px;
}
.mmc-refine-head .mmc-pop-title { padding: 0 0 0 8px; }
.mmc-refine-seg {
  display: flex; padding: 2px; border-radius: 999px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
}
.mmc-refine-seg-btn {
  border: 0; background: none; border-radius: 999px; cursor: pointer;
  padding: 4px 12px; color: var(--mmc-dim); font-family: inherit;
  font-size: calc(11px * var(--mmc-type)); transition: all .12s ease;
}
.mmc-refine-seg-btn:hover { color: var(--mmc-text); }
.mmc-refine-seg-btn[aria-checked="true"] {
  background: var(--mmc-accent); color: var(--mmc-bg);
}

/* The server is one object with a state, so it is one card: URL and Connect
   on a line, the write-only key box under it, and a status line whose dot is
   the card's condition. The model list hangs below, outside the card. */
.mmc-refine-server {
  display: flex; flex-direction: column; gap: 8px;
  margin: 0 2px 8px; padding: 10px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 12px;
}
.mmc-refine-server .mmc-refine-row { flex-wrap: nowrap; align-items: center; }
.mmc-refine-connect {
  flex: none; height: calc(30px * var(--mmc-type)); padding: 0 14px;
  border: 0; border-radius: 15px; cursor: pointer;
  background: var(--mmc-accent); color: var(--mmc-bg);
  font-family: inherit; font-size: calc(12px * var(--mmc-type));
}
.mmc-refine-connect:hover { filter: brightness(1.08); }
.mmc-refine-forget { flex: none; font-size: calc(11px * var(--mmc-type)); }
.mmc-refine-status {
  display: flex; align-items: center; gap: 7px;
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.4;
}
.mmc-refine-status .mmc-dot { color: var(--mmc-off); opacity: 1; flex: none; }
.mmc-refine-status.ok { color: var(--mmc-text); }
.mmc-refine-status.ok .mmc-dot { color: var(--mmc-accent); }
.mmc-refine-status.bad { color: var(--mmc-warn); }
.mmc-refine-status.bad .mmc-dot { color: var(--mmc-warn); }
.mmc-refine-status-text { min-width: 0; }

/* Only the lists scroll; the card and the sections stay put. */
.mmc-refine-list, .mmc-refine-remote-rows { max-height: 210px; overflow-y: auto; }

/* A hairline starts each section, which is what lets the uppercase eyebrows
   read as headings instead of drowning between paragraphs. */
.mmc-refine-section { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--mmc-line); }
.mmc-refine-section:empty { display: none; }
.mmc-refine-section > .mmc-note-key { display: block; padding: 0 10px 6px; }
.mmc-refine-section > .mmc-chips { padding: 0 10px 4px; }
/* Names run to a folder-qualified qwen3vl/qwen3vl_4b_instruct_fp8.safetensors.
   The row ellipsises and the title carries the whole of it. */
.mmc-refine-name {
  display: block; min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
/* What kind of prompting a row is — "prompt" or "skill" — said as a tiny tag
   between the name and the radio, because the rows otherwise look like two of
   the same thing and behave like two different ones. */
.mmc-opt-kind {
  flex: none; margin-left: auto; margin-right: 8px;
  font-size: calc(10px * var(--mmc-type)); color: var(--mmc-dim);
  border: 1px solid var(--mmc-line); border-radius: 999px; padding: 1px 7px;
}
.mmc-refine-hint { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.4; }
/* The eject chip sits inside the server card, under its hint: it is a
   property of that server, not of the popover. */
.mmc-refine-eject { padding-top: 2px; }
/* Replace or add, and one line saying what the answer costs. Indented to the
   rows above it, since it is about whichever of them is checked. */
.mmc-refine-modes { padding: 6px 10px 2px; }
.mmc-refine-note { padding: 2px 10px 8px; }
.mmc-refine-empty {
  display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
  padding: 4px 10px 10px; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-refine-empty code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11px * var(--mmc-type));
  color: var(--mmc-text); background: var(--mmc-surface-2);
  border: 1px solid var(--mmc-line); border-radius: 7px; padding: 5px 8px;
}
.mmc-refine-empty .mmc-ghost { font-size: calc(12px * var(--mmc-type)); }

/* The URL and the key are the popover's only text inputs; they take the shelf
   input's dress and share their row with the button beside them. The key box
   is write-only — a placeholder says one is stored, the value never returns. */
.mmc-refine-field { width: 100%; flex: 1; min-width: 0; }

/* Everything but the model, folded away: it is set once and the model is not. */
.mmc-refine-fold { font-size: calc(12px * var(--mmc-type)); }
.mmc-refine-fold > summary {
  cursor: pointer; color: var(--mmc-dim); padding: 8px 10px;
  border-top: 1px solid var(--mmc-line); list-style-position: inside;
}
.mmc-refine-fold > summary:hover { color: var(--mmc-text); }
.mmc-refine-more-body {
  display: flex; flex-direction: column; gap: 12px; padding: 4px 10px 8px;
}
.mmc-refine-group { display: flex; flex-direction: column; gap: 7px; }
.mmc-refine-row { display: flex; gap: 8px; flex-wrap: wrap; }

/* The three dials share a line each with its label above it — three controls
   never needed three paragraph-bearing rows. The seed pair runs wider than a
   half column, so it takes the row under the two steppers whole. */
.mmc-refine-dials { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
.mmc-refine-dial { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.mmc-refine-dial.wide { grid-column: 1 / -1; }
.mmc-refine-seed { font-size: calc(12px * var(--mmc-type)); padding: 0 10px 0 2px; }

/* Eleven languages: chips wrap into three lines and stay scannable, where a
   list would scroll and a <select> would be the only browser chrome in the node. */
.mmc-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.mmc-chip {
  padding: 4px 10px; border-radius: 12px; background: var(--mmc-surface-2);
  border: 1px solid var(--mmc-line); color: var(--mmc-dim);
  font-family: inherit; font-size: calc(11px * var(--mmc-type)); cursor: pointer; transition: all .12s ease;
}
.mmc-chip:hover { color: var(--mmc-text); background: var(--mmc-surface-3); }
.mmc-chip[aria-checked="true"] {
  color: var(--mmc-bg); background: var(--mmc-accent); border-color: var(--mmc-accent);
}

/* --- the rewrite ---------------------------------------------------------- */
/* An editor, not a readout: the rewrite is a draft, and correcting one word of
   it should not mean running the model again. */
.mmc-refined { display: flex; flex-direction: column; gap: 8px; }
.mmc-refined:empty { display: none; }
.mmc-refined-head { display: flex; align-items: center; gap: 8px; font-size: calc(12px * var(--mmc-type)); }
.mmc-refined-toggle {
  display: flex; align-items: center; gap: 6px; background: none; border: 0;
  padding: 0; cursor: pointer; color: var(--mmc-off); font: inherit; font-size: calc(12px * var(--mmc-type));
}
.mmc-refined-toggle.on { color: var(--mmc-accent); }
.mmc-dot {
  width: 7px; height: 7px; border-radius: 50%; background: currentColor; opacity: .5;
}
.mmc-refined-toggle.on .mmc-dot { opacity: 1; }
.mmc-refined-model { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type));
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.mmc-refined-stale { color: var(--mmc-accent); font-size: calc(11px * var(--mmc-type)); opacity: .8; }
/* Said once, next to the dimmed prompt it is talking about. */
.mmc-refined-lede { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); margin-top: -4px; }
.mmc-refined-box {
  width: 100%; box-sizing: border-box; resize: vertical;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 12px;
  color: var(--mmc-text); font-family: inherit; font-size: calc(13px * var(--mmc-type)); line-height: 1.5;
  padding: 10px 12px; outline: none;
}
.mmc-refined-box:focus { border-color: var(--mmc-line-2); }
.mmc-refined-fold { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-refined-fold summary { cursor: pointer; padding: 2px 0; }
.mmc-refined-sections { display: flex; flex-direction: column; gap: 8px; padding-top: 8px; }
.mmc-refined-section { display: flex; flex-direction: column; gap: 4px; }
/* A readout, not a field: it is the model's own account of the pictures and
   editing it would change nothing that gets queued. */
.mmc-refined-seen {
  padding: 8px 12px; border-left: 2px solid var(--mmc-line);
  white-space: pre-wrap; user-select: text;
  /* The one unbounded readout in here — every box beside it is a textarea with
     a row count. A long account scrolls rather than growing the panel, and the
     cap is in pixels on a node face for the reason .mmc-prompt's is: vh is the
     screen's height, and what has to hold this is a rectangle on a graph. */
  max-height: 160px; overflow-y: auto;
}
.mmc-editor-sheet-body .mmc-refined-seen, .mmc-tl-modal .mmc-refined-seen { max-height: 30vh; }

`;
