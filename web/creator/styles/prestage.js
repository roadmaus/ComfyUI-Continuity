// Pre-stage and the frame grab.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* ---- pre-stage --------------------------------------------------------------
   The image node wears the Creator's clothes: same tokens, same pills, same
   chip vocabulary. Only what it does not share is styled here. */

/* A plain textarea, not the contenteditable PromptBox: an image prompt has no
   @-handles to chip. Dressed exactly like the timeline's prompt box. */
/* The prompt is the Creator's box now — see prestage.js — so it wears the
   editor's own rules and the panel around it is its frame. What was here was a
   textarea's skin: its own border, background and padding, which the panel
   already draws. */

/* The spawn pill. On, it wears the accent the continue pill wears — the
   pre-stage is part of this shot now, which is a stronger statement than the
   accelerators' blue "not native". */
.mmc-prestage-toggle.on { border-color: color-mix(in srgb, var(--mmc-accent) 50%, transparent); color: var(--mmc-accent); }
.mmc-prestage-toggle.on:hover:not(:disabled) { border-color: color-mix(in srgb, var(--mmc-accent) 80%, transparent); }

/* The left-hand satellite anchors on its right edge (satellite.js sets the
   transform); nothing else about the card changes side. */
.mmc-satellite-left { transform-origin: 100% 0; }

/* The hand-off chips on a finished still — real buttons in the readout row,
   dressed like the gallery chip so the overlay stays one vocabulary. The
   readout swallows the pointer (see above), so like the gallery chip these
   have to opt back in or they are pictures of buttons. */
.mmc-stage-send {
  pointer-events: auto;
  background: var(--mmc-scrim-2); border: 1px solid var(--mmc-edge); border-radius: 999px;
  padding: 3px 10px; cursor: pointer; font-family: inherit; font-size: calc(12px * var(--mmc-type));
  color: var(--mmc-text);
}
.mmc-stage-send:hover { border-color: var(--mmc-accent); color: var(--mmc-accent); }

/* ---- the frame grab ---------------------------------------------------------
   The trim editor's scrubbing with a different ending; dressed like it too. */
.mmc-grab-card {
  display: flex; flex-direction: column; gap: 14px;
  width: min(720px, 92vw); padding: 20px 24px;
  background: var(--mmc-bg); border: 1px solid var(--mmc-line); border-radius: 18px;
  box-shadow: 0 24px 64px var(--mmc-shadow-soft);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
  color: var(--mmc-text); font-size: calc(13px * var(--mmc-type));
}
.mmc-grab-title { display: flex; align-items: center; gap: 8px; font-size: calc(14px * var(--mmc-type)); }
.mmc-grab-title svg { stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-grab-stage {
  width: 100%; max-height: 46vh; object-fit: contain;
  background: var(--mmc-media-bg); border-radius: 12px;
}
.mmc-grab-row { display: flex; align-items: center; gap: 10px; }
.mmc-grab-scrub { flex: 1; }
.mmc-grab-time { min-width: 64px; text-align: right; color: var(--mmc-dim); font-variant-numeric: tabular-nums; }
.mmc-grab-actions { display: flex; justify-content: flex-end; gap: 12px; }
.mmc-grab-actions .mmc-btn {
  padding: 8px 18px; border-radius: 999px; cursor: pointer; font-family: inherit;
  font-size: calc(13px * var(--mmc-type)); background: var(--mmc-surface-2); color: var(--mmc-text);
  border: 1px solid var(--mmc-line);
}
.mmc-grab-actions .mmc-btn:hover:not(:disabled) { border-color: var(--mmc-line-3); }
.mmc-grab-actions .mmc-btn-primary { background: var(--mmc-accent); color: var(--mmc-on-accent); border-color: transparent; }
.mmc-grab-actions .mmc-btn:disabled { opacity: .5; cursor: progress; }

/* ---- the contact sheet (contact.js, not the Ingredients sheet) -------------------------------------------------------
   The grab's card with a grid of shapes where its scrubber is: what the tool
   asks for is a layout, and a layout is worth showing as one. */
.mmc-contact-stage { max-height: 52vh; }
.mmc-contact-grid { display: flex; gap: 8px; flex-wrap: wrap; }
.mmc-contact-cell {
  padding: 7px 14px; border-radius: 999px; cursor: pointer; font-family: inherit;
  font-size: calc(12px * var(--mmc-type)); font-variant-numeric: tabular-nums;
  background: var(--mmc-surface-2); color: var(--mmc-text);
  border: 1px solid var(--mmc-line);
}
.mmc-contact-cell:hover { border-color: var(--mmc-line-3); }
.mmc-contact-cell.on { background: var(--mmc-accent); color: var(--mmc-on-accent); border-color: transparent; }
.mmc-contact-note { color: var(--mmc-dim); line-height: 1.5; min-height: 2.6em; }
`;
