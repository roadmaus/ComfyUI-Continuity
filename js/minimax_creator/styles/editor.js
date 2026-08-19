// Tool rail, attached assets, prompt + pills, @ mention menu.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- tool rail ------------------------------------------------------------ */
/* Every icon comes from ICONS, and every path in there is drawn rather than
   filled. Set once, before any component rule, because forgetting it renders a
   stroke-only path as a solid black blob — which is what a missing per-component
   rule looks like, not a missing icon. Components still override the size and
   weight; equal specificity, so the later rule wins. */
.mmc-root svg, .mmc-overlay svg, .mmc-pop svg {
  fill: none; stroke: currentColor; stroke-width: 1.6;
  stroke-linecap: round; stroke-linejoin: round;
}

/* Two clusters: generation tools left, the machine's pair (Gallery, Settings)
   at the far edge. space-between does the split; on a node too narrow for both,
   the right cluster wraps under and keeps its edge. */
.mmc-rail { display: flex; gap: 10px 24px; flex-wrap: wrap; justify-content: space-between; }
.mmc-rail-group { display: flex; gap: 10px; flex-wrap: wrap; }
.mmc-rail-group:last-child { margin-left: auto; }
.mmc-tool {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  background: none; border: 0; padding: 0; cursor: pointer;
  color: var(--mmc-dim); font-size: 12px; font-family: inherit;
}
.mmc-tool-icon {
  width: 56px; height: 56px; border-radius: 14px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  display: flex; align-items: center; justify-content: center;
  transition: background .12s ease;
}
.mmc-tool:hover:not(:disabled) .mmc-tool-icon { background: var(--mmc-surface-3); }
.mmc-tool:hover:not(:disabled) { color: var(--mmc-text); }
.mmc-tool:disabled { cursor: not-allowed; color: var(--mmc-off); }
.mmc-tool:disabled .mmc-tool-icon { opacity: .45; }
.mmc-tool svg { width: 22px; height: 22px; stroke: currentColor; fill: none;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }

/* Clear, the one tool in the rail that takes something away. Idle it is a
   sibling of the rest — a rail where one tile shouts would be a rail that reads
   as a warning — and it declares itself only under the pointer, in the same red
   the picker's Delete uses for files. Armed, the second press is the one that
   empties the piece, so the tile goes solid and the label asks. */
.mmc-tool.mmc-tool-danger:hover:not(:disabled) { color: #e0743c; }
.mmc-tool.mmc-tool-danger:hover:not(:disabled) .mmc-tool-icon {
  background: rgba(224,116,60,.14); border-color: rgba(224,116,60,.45);
}
.mmc-tool.mmc-tool-danger.armed { color: #f08a55; }
.mmc-tool.mmc-tool-danger.armed .mmc-tool-icon,
.mmc-tool.mmc-tool-danger.armed:hover:not(:disabled) .mmc-tool-icon {
  background: #b03a2a; border-color: #b03a2a; color: #fff;
}
.mmc-tool:focus-visible { outline: none; }
.mmc-tool:focus-visible .mmc-tool-icon { border-color: var(--mmc-accent); }

/* --- attached assets ------------------------------------------------------ */
.mmc-assets { display: flex; gap: 8px; flex-wrap: wrap; }
/* On a node face the chips are the other thing that used to grow the node: nine
   references wrap to three rows and push the pills off the bottom. Two rows,
   then it scrolls — the face is a preview, and everything in it is bounded. */
.mmc-root .mmc-assets { max-height: 84px; overflow-y: auto; }
/* ...but not in a window, where there is room and nothing to protect. */
.mmc-tl-modal .mmc-assets, .mmc-editor-sheet .mmc-assets {
  max-height: none; overflow: visible;
}
.mmc-asset {
  display: flex; align-items: center; gap: 8px; padding: 4px 8px 4px 4px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  border-radius: 10px; font-size: 12px;
}
.mmc-asset-thumb {
  width: 30px; height: 30px; border-radius: 7px; object-fit: cover;
  background: var(--mmc-surface-3); display: flex; align-items: center; justify-content: center;
  color: var(--mmc-dim); flex: none;
  /* The identity ring: paints the asset's hue onto the actual picture, which is
     what the same-hued chip in the prompt points back to. Transparent when the
     row carries no tag (LoRA chips share this class). */
  box-shadow: 0 0 0 2px var(--tag, transparent);
}
/* A thumbnail you can click is a thumbnail that swaps the file under the chip's
   handle. Said with the pointer and a lit ring rather than another button in a
   row that already has four — the picture is the affordance. */
.mmc-asset-swap { cursor: pointer; }
.mmc-asset-swap:hover, .mmc-asset-swap:focus-visible {
  filter: brightness(1.3);
  box-shadow: 0 0 0 2px var(--mmc-accent);
  outline: none;
}
.mmc-asset-handle { color: var(--tag, var(--mmc-accent)); font-weight: 500; }
.mmc-asset-role { color: var(--mmc-dim); }
.mmc-asset-x {
  background: none; border: 0; color: var(--mmc-off); cursor: pointer;
  font-size: 15px; line-height: 1; padding: 2px 3px; font-family: inherit;
}
.mmc-asset-x:hover { color: var(--mmc-text); }
/* A LoRA set to the checkpoint this graph does not route to. Still listed —
   removing it on a mode change would throw the setting away — but visibly
   out of the run. */
.mmc-asset.idle { opacity: .5; }
.mmc-asset.idle .mmc-asset-handle { color: var(--mmc-dim); }
.mmc-lora-block { display: flex; flex-direction: column; gap: 6px; }
/* What the LoRAs add to the front of the prompt. Not a warning — it is working
   as intended — but it has to be readable, because the prompt box does not
   show it. */
.mmc-note {
  display: flex; gap: 8px; font-size: 11px; color: var(--mmc-dim); line-height: 1.4;
}
.mmc-note-key {
  color: var(--mmc-off); letter-spacing: .06em; text-transform: uppercase;
  font-size: 10px; padding-top: 1px; flex: none;
}

/* --- prompt + pills ------------------------------------------------------- */
.mmc-panel {
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 20px; padding: 14px; display: flex; flex-direction: column;
  gap: 12px; flex: 1; min-height: 0;
}
/* contenteditable, not a textarea: @references are atomic chips, and a textarea
   can only hold flat text. white-space: pre-wrap so the literal "\n" the box
   inserts on Enter renders as a line break. */
/* --- the face's prompt ---------------------------------------------------- */
/* The box is typed into on the face, capped to what the node can show, and the
   corner control is the way into a window when a prompt outgrows it. Pinned
   over the panel's top-right rather than laid out in the column: it is a way
   out of the box, not a row of the form, and it must not move the box down by
   its own height on every node. */
.mmc-panel { position: relative; }
.mmc-panel-corner { position: absolute; top: 10px; right: 10px; z-index: 1; }
.mmc-expand {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; padding: 0; border-radius: 8px; cursor: pointer;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-off); opacity: .55; transition: opacity .12s ease, color .12s ease;
}
.mmc-panel:hover .mmc-expand { opacity: 1; }
.mmc-expand:hover { color: var(--mmc-text); border-color: rgba(255,255,255,.2); }
/* Lit once the text no longer fits: at that point the window is not a shortcut,
   it is where the writing is. */
.mmc-expand.on { opacity: 1; color: var(--mmc-accent); border-color: rgba(240,166,60,.45); }
/* Room for it, so a long first line does not run under the button. */
.mmc-panel > .mmc-prompt-fold > .mmc-prompt { padding-right: 30px; }

/* The window the face's corner control opens — and the one a timeline segment
   opens over the strip. One window: both are the same node body over the same
   kind of state, and the segment's is the one that was right.

   Two class names, not one: .mmc-modal sizes every modal in the pack and lives
   in picker.js, which the stylesheet concatenates *after* this file — so a
   single-class rule here loses the cascade and the window silently keeps the
   picker's 1100x760. */
/* Wider and taller than the picker it inherits from: this is the one window in
   the pack you *write* in, and 880 was a column for reading a shot back rather
   than for holding a paragraph, a rail, a strip of references and the pills at
   once. Still a measure and not the screen — prose 1700px wide is unreadable
   however much room there is for it, and the overlay's own 40px keeps it a
   window rather than a takeover. */
.mmc-modal.mmc-editor-sheet { width: min(1180px, 100%); height: min(900px, 100%); }
/* The body inside is a node body — built to fill a DOM widget and to clip
   anything that would grow it. In here it is the thing that grows: the window
   scrolls, so the body is free to be as tall as its content. */
.mmc-editor-sheet-body .mmc-root { height: auto; overflow: visible; padding: 18px 24px 24px; }
.mmc-editor-sheet-sub { color: var(--mmc-dim); font-size: 13px; }
.mmc-editor-sheet-body { overflow: auto; flex: 1; min-height: 0; }
/* In the window the box gets the room the face cannot give it — but still a
   cap, because a pasted log is not a thing to scroll the whole window past. */
.mmc-editor-sheet-body .mmc-prompt { max-height: 40vh; }

/* max-height, not just overflow: the box is a flex child of a panel that is
   itself only as tall as its parent lets it be, and in the node body that
   parent takes its height from the content — so a long prompt grew the widget
   and the node with it instead of scrolling. A cap here is the one thing no
   ancestor can undo. Paste a crash log into it and it is a scroll box.

   In lines rather than in vh: vh is the *screen's* height, and the box that has
   to fit is a rectangle on a graph — on a tall display 40vh was half again the
   node, so the box grew the node past what the canvas could show and the text
   never registered as overflowing at all. Seven lines is what the face shows;
   the window holds the rest. */
.mmc-prompt {
  flex: 1; min-height: 56px; max-height: 168px; background: none; border: 0; outline: none;
  color: var(--mmc-text); font-family: inherit; font-size: 15px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word; overflow-y: auto;
}
.mmc-prompt:empty::before {
  content: attr(data-placeholder); color: #6a6a6a; pointer-events: none;
}
/* A rewrite replaces this text rather than joining it, so while one is on the
   box is holding a draft, not the prompt. Dimmed rather than disabled: it is
   still where the next rewrite comes from. */
.mmc-prompt.superseded { opacity: .42; }
.mmc-prompt.superseded:focus { opacity: .72; }

/* ...and folded away, because dimming alone still gave two full descriptions of
   the same shot the same room. The wrapper is what grows, so the box inside it
   goes on filling the panel exactly as it did; closed, it gives its height back
   to the rewrite that is actually queued. */
.mmc-prompt-fold { display: flex; flex-direction: column; gap: 8px; flex: 1; min-height: 0; }
.mmc-prompt-fold:not([open]) { flex: 0 0 auto; }
/* The box has to fill the fold, or the panel is mostly dead space: a
   contenteditable is only clickable where its box is, so a short prompt in a
   tall panel left you with one line's worth of target at the top and nothing
   under it.

   It stopped filling when browsers shipped ::details-content. The children of
   an open <details> used to be its flex items; now they are wrapped in that
   pseudo-element, which is display:block by default — so flex:1 on the box
   inside had no flex container to grow in and it sat at its own min-height.
   Making the wrapper the column the fold used to be puts it back.

   Only while open: closed, the fold gives its height back to the rewrite that is
   actually queued, and the wrapper is hidden by the UA's own content-visibility
   either way. An engine without the pseudo drops this rule and already works —
   there the box is a flex item of the fold, which is what it was written as. */
.mmc-prompt-fold[open]::details-content {
  display: flex; flex-direction: column; flex: 1; min-height: 0;
}
/* No disclosure until there is something standing in for the box: with no
   rewrite this is the prompt, and a prompt does not need announcing. */
.mmc-prompt-head { display: none; }
.mmc-prompt-fold.superseded > .mmc-prompt-head {
  display: flex; align-items: center; gap: 7px; min-width: 0;
  padding: 4px 6px; margin: -4px -6px; border-radius: 9px;
  color: var(--mmc-dim); font-size: 12px; cursor: pointer; list-style: none;
}
.mmc-prompt-head::-webkit-details-marker { display: none; }
.mmc-prompt-fold.superseded > .mmc-prompt-head:hover { color: var(--mmc-text); background: var(--mmc-surface-2); }
.mmc-prompt-head svg {
  width: 12px; height: 12px; flex: none; stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  transform: rotate(-90deg); transition: transform .14s ease;
}
.mmc-prompt-fold[open] > .mmc-prompt-head svg { transform: none; }
.mmc-prompt-head-name { flex: none; }
/* The sentence's own first line, so the box can be recognised without opening
   it. Hidden once it is open — the text itself is right underneath. */
.mmc-prompt-excerpt {
  min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--mmc-off);
}
.mmc-prompt-excerpt.empty { font-style: italic; }
.mmc-prompt-fold[open] .mmc-prompt-excerpt { display: none; }
/* --- the scope band ------------------------------------------------------- */
/* What the compiler writes in front of the description, shown where it lands:
   inside the prompt's fold, above the box. Generated, so it is not a field —
   no border, no background of its own, and never focusable. It reads as a note
   the prompt carries rather than as a second box to write in, which is the one
   thing it must not be mistaken for.

   Held off the box by the fold's own 8px gap and separated by a rule, because
   the two are the same prompt and stacking them with no line between made the
   sentences read as text somebody had typed. */
.mmc-scopes:empty { display: none; }
.mmc-scopes {
  display: flex; flex-direction: column; gap: 5px; flex: none;
  padding-bottom: 9px; border-bottom: 1px solid var(--mmc-line);
  user-select: text; cursor: default;
}
.mmc-scopes-head {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  color: var(--mmc-off); font-size: 10px; letter-spacing: .09em; text-transform: uppercase;
}
/* The one thing the band cannot show honestly: ordinals are allocated at queue
   time, so the names here are handles and the model reads labels. Said once, in
   the quietest type on the row, rather than in a tooltip nobody opens. */
.mmc-scopes-why { letter-spacing: 0; text-transform: none; font-size: 10.5px; opacity: .8; }
.mmc-scopes-line {
  margin: 0; color: var(--mmc-dim); font-size: 12.5px; line-height: 1.55;
}
/* Dimmed with the box it belongs to: while a rewrite stands in for the prompt,
   neither of them is what gets queued. */
.mmc-prompt-fold.superseded > .mmc-scopes { opacity: .42; }

/* .mmc-ref, not .mmc-chip: the refiner's language chips own that name, and the
   two rules fighting over it is what once turned these gray. */
.mmc-ref {
  display: inline-block; padding: 1px 7px; margin: 0 1px; border-radius: 7px;
  background: color-mix(in srgb, var(--tag, var(--mmc-accent)) 14%, transparent);
  color: var(--tag, var(--mmc-accent));
  font-size: .92em; white-space: nowrap; user-select: all;
}

/* --- @ mention menu ------------------------------------------------------- */
.mmc-mention {
  position: fixed; z-index: 1350; width: 330px; max-height: 300px; overflow-y: auto;
  background: #212121; border: 1px solid var(--mmc-line); border-radius: 14px;
  padding: 6px; box-shadow: 0 20px 50px rgba(0,0,0,.65);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
}
.mmc-mention-head {
  color: #7d7d7d; font-size: 10px; letter-spacing: .09em; text-transform: uppercase;
  padding: 10px 10px 6px;
}
/* min-width:0 all the way down: a flex item defaults to min-content width, so
   without it a 90-character generated filename forces the row wider than the
   menu instead of ellipsizing. */
.mmc-mention-row {
  display: flex; align-items: center; gap: 10px; width: 100%; min-width: 0;
  padding: 7px 8px; background: none; border: 1px solid transparent;
  border-radius: 10px; font-family: inherit; text-align: left; cursor: pointer;
  color: #ededed; overflow: hidden;
}
.mmc-mention-row[aria-selected="true"] { background: #2e2e2e; border-color: rgba(255,255,255,.13); }
.mmc-mention-thumb {
  width: 30px; height: 30px; border-radius: 7px; object-fit: cover; flex: none;
  background: #333; display: flex; align-items: center; justify-content: center;
  color: #8b8b8b; font-size: 13px;
}
.mmc-mention-text { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.mmc-mention-handle {
  color: var(--tag, var(--mmc-accent)); font-size: 14px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-mention-sub {
  color: #7d7d7d; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-mention-empty { color: #7d7d7d; font-size: 13px; padding: 14px 10px; }

.mmc-pills { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.mmc-pill {
  display: flex; align-items: center; gap: 7px; height: 38px; padding: 0 14px;
  border-radius: 19px; background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-size: 13px; font-family: inherit; cursor: pointer;
  white-space: nowrap; transition: background .12s ease;
}
.mmc-pill:hover:not(:disabled) { background: var(--mmc-surface-3); }
.mmc-pill:disabled { cursor: not-allowed; color: var(--mmc-off); }
.mmc-pill svg { width: 16px; height: 16px; stroke: currentColor; fill: none;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.mmc-pill-sub { color: var(--mmc-dim); font-size: 11px; }
.mmc-pill-group { gap: 0; padding: 0 6px; }
.mmc-step {
  background: none; border: 0; color: var(--mmc-text); cursor: pointer;
  font-size: 16px; width: 26px; height: 36px; font-family: inherit;
}
.mmc-step:disabled { color: var(--mmc-off); cursor: not-allowed; }
/* No text-transform: the socket name has to read exactly as it does on the
   input, and 'model_fl2va' uppercased is not the name of anything. */
.mmc-mode {
  margin-left: auto; font-size: 11px; letter-spacing: .04em; color: var(--mmc-dim);
  display: flex; align-items: center; gap: 6px;
  background: none; border: 1px solid transparent; border-radius: 13px;
  padding: 5px 10px; font-family: inherit;
}
/* Only the clickable form gets affordances — as a span it is a plain readout. */
button.mmc-mode { cursor: pointer; }
button.mmc-mode:hover { background: var(--mmc-surface-2); border-color: var(--mmc-line); }
.mmc-mode.pinned { border-color: var(--mmc-line); background: var(--mmc-surface-2); }
.mmc-mode b { color: var(--mmc-accent); font-weight: 600; }
.mmc-pin {
  font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
  color: var(--mmc-accent); border: 1px solid currentColor; border-radius: 8px;
  padding: 0 5px; opacity: .8;
}
.mmc-warn { color: #e0743c; font-size: 12px; }

`;
