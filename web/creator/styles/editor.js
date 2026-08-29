// Tool rail, attached assets, prompt + pills, @ mention menu.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- tool rail ------------------------------------------------------------ */
/* Every icon comes from ICONS, and every path in there is drawn rather than
   filled. Set once, before any component rule, because forgetting it renders a
   stroke-only path as a solid black blob — which is what a missing per-component
   rule looks like, not a missing icon. Components still override the size and
   weight; equal specificity, so the later rule wins. */
.mmc-root svg, .mmc-overlay svg, .mmc-pop svg, .mmc-mention svg {
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
  color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); font-family: inherit;
}
.mmc-tool-icon {
  width: var(--mmc-tool-tile); height: var(--mmc-tool-tile); border-radius: 14px;
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
.mmc-tool.mmc-tool-danger:hover:not(:disabled) { color: var(--mmc-warn); }
.mmc-tool.mmc-tool-danger:hover:not(:disabled) .mmc-tool-icon {
  background: color-mix(in srgb, var(--mmc-warn) 14%, transparent); border-color: color-mix(in srgb, var(--mmc-warn) 45%, transparent);
}
.mmc-tool.mmc-tool-danger.armed { color: var(--mmc-warn); }
.mmc-tool.mmc-tool-danger.armed .mmc-tool-icon,
.mmc-tool.mmc-tool-danger.armed:hover:not(:disabled) .mmc-tool-icon {
  background: var(--mmc-bad-solid); border-color: var(--mmc-bad-solid); color: var(--mmc-strong);
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
  border-radius: 10px; font-size: calc(12px * var(--mmc-type));
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
/* A reference's handle is a door: it opens the card holding everything about
   that reference (see .mmc-refsheet). Drawn as the label it has always been —
   no chrome, the tag's own colour — with the pointer and an underline on hover
   as the only tell, because a row of chips that each grew a button would be the
   crowding this card was made to undo. */
.mmc-asset-door {
  background: none; border: 0; padding: 0; font: inherit; font-weight: 500;
  color: var(--tag, var(--mmc-accent)); cursor: pointer; line-height: inherit;
}
.mmc-asset-door:hover, .mmc-asset-door:focus-visible {
  text-decoration: underline; text-underline-offset: 3px; outline: none;
}
/* What somebody set on this reference, and only that — "style", "0:00–0:08",
   "sound off". Read, not pressed: the four buttons this replaces were four
   places to click on a chip whose name is now the one place. Dim, because the
   handle is what identifies the chip and this is a footnote to it. */
.mmc-asset-said { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); }
/* The scissors a chip wears when its one picture was cut out. The picker styles
   this class as a button pinned into the corner of a 62px cell; on a chip it is
   a mark in a row, so the position and the chrome come off and the colour is
   the whole of it. */
.mmc-asset .mmc-pl-cut {
  position: static; width: auto; height: auto; padding: 0;
  background: none; color: var(--mmc-blue); cursor: default;
}
/* The same scissors as a live control: on any single picture that could be
   cut, the badge is the press itself — off is faint, on is the blue the badge
   always wore, and the hand plus the hover is what says it does something. */
.mmc-asset .mmc-asset-scissors { border: 0; cursor: pointer; display: inline-flex; }
.mmc-asset .mmc-asset-scissors:not(.on) { color: var(--mmc-faint); }
.mmc-asset .mmc-asset-scissors:hover { color: var(--mmc-strong); }
/* How many pictures a plate holds. The one fact about a sheet that is worth
   reading off the card, set in the tabular face its panel numbers are in. */
.mmc-asset-panels {
  color: var(--mmc-faint);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums; letter-spacing: .03em;
  font-size: calc(10px * var(--mmc-type));
}
/* The LoRA chip's name, which is its mute switch. A button that has to keep
   reading as the label it replaced: no chrome, and the pointer plus the hover
   is what says it does something. */
.mmc-asset-name {
  background: none; border: 0; padding: 0; font: inherit; font-weight: 500;
  cursor: pointer; line-height: inherit;
}
.mmc-asset-name:hover, .mmc-asset-name:focus-visible { color: var(--mmc-text); outline: none; }
.mmc-asset-role { color: var(--mmc-dim); }
/* The one role that is a decision: on an edit family the first picture is the
   thing being changed by default and need not be, so the word is the switch.
   Drawn as the label it replaced until it is hovered — the same trade
   .mmc-asset-name makes. */
.mmc-asset-role-pick {
  background: none; border: 0; padding: 0 2px; font: inherit; cursor: pointer;
  line-height: inherit; border-radius: 5px;
}
.mmc-asset-role-pick.on { color: var(--mmc-accent); }
.mmc-asset-role-pick:hover, .mmc-asset-role-pick:focus-visible {
  background: var(--mmc-surface-3); color: var(--mmc-text); outline: none;
}
/* A reference the compile will refuse, drawn rather than dropped: the blob
   keeps every picture it was given, so the chip is where the cap is said. Read
   as struck out, because the file is still attached and still recoverable by
   moving the cap rather than by finding the picture again. */
.mmc-asset-refused {
  border-color: color-mix(in srgb, var(--mmc-bad) 55%, transparent);
  color: var(--mmc-off);
}
.mmc-asset-refused .mmc-asset-handle, .mmc-asset-refused .mmc-asset-role {
  text-decoration: line-through;
}
/* ...and the softer one: attached, read, and a shape the adapter was not
   trained to hold against this canvas. A worse render, not a refused one, so it
   is the warning colour and nothing is struck. */
.mmc-asset-offshape { border-color: color-mix(in srgb, var(--mmc-warn) 55%, transparent); }
.mmc-asset-offshape .mmc-asset-role { color: var(--mmc-warn); }
.mmc-asset-x {
  background: none; border: 0; color: var(--mmc-off); cursor: pointer;
  font-size: calc(15px * var(--mmc-type)); line-height: 1; padding: 2px 3px; font-family: inherit;
}
.mmc-asset-x:hover { color: var(--mmc-text); }
/* Somebody's picture rather than a file you attached: the cast put it here, and
   on a strip of more than one card the piece's shelf is where it has to live.
   The cast card's own device, borrowed — a rule down the left edge in the
   identity hue — because that is already what "this belongs to a member" looks
   like everywhere else in the pack, and it is the difference between a shelf
   that reads as duplicated faces and one that reads as the cast's files. */
.mmc-asset-cast {
  border-left: 3px solid var(--tag, var(--mmc-accent)); padding-left: 9px;
}

/* A LoRA set to the checkpoint this graph does not route to. Still listed —
   removing it on a mode change would throw the setting away — but visibly
   out of the run. */
.mmc-asset.idle { opacity: .5; }
.mmc-asset.idle .mmc-asset-handle { color: var(--mmc-dim); }
/* Muted: switched off by hand, and kept. Struck through rather than merely
   dimmed, because idle already spends dimming on "not on this checkpoint"
   and the two have to be tellable apart on a chip that can be both. */
.mmc-asset.off { opacity: .6; }
.mmc-asset.off .mmc-asset-name { color: var(--mmc-dim); text-decoration: line-through; }
/* Muted the other way round: a LoRA spells this on its name, and a reference's
   name is already the door onto its card — so the switch is a glyph beside the
   ✕, and the strike-through above has no name to land on. The chip is dimmed
   instead, and the glyph stays lit while it is the reason. */
.mmc-asset-mute { display: flex; align-items: center; padding: 2px; }
.mmc-asset-mute:hover { color: var(--mmc-text); }
.mmc-asset-mute.on { color: var(--mmc-accent); }
.mmc-asset.off .mmc-asset-handle { color: var(--mmc-dim); }
.mmc-asset.off .mmc-asset-thumb { filter: grayscale(1); }

/* The swap button sits in the ✕'s row and wears its colours; the glyph needs
   the extra line-height reset a text button does not. */
.mmc-asset-shuffle { display: flex; align-items: center; padding: 2px; }
.mmc-asset-shuffle:hover { color: var(--mmc-text); }
.mmc-lora-block { display: flex; flex-direction: column; gap: 6px; }
/* What the LoRAs add to the front of the prompt. Not a warning — it is working
   as intended — but it has to be readable, because the prompt box does not
   show it. */
.mmc-note {
  display: flex; gap: 8px; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.4;
}
.mmc-note-key {
  color: var(--mmc-off); letter-spacing: .06em; text-transform: uppercase;
  font-size: calc(10px * var(--mmc-type)); padding-top: 1px; flex: none;
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
/* The writing half of the well: the box and, under it, the rewrite that stands
   in for it. A column of its own so that "the writing scrolls" can be said
   about the writing alone — the pill row is a sibling of this, not of the box,
   and so it stays put wherever the room runs out.

   The scroll is here, not on the pieces: a rewrite plus an open prompt is far
   taller than any node face, and without an overflow the flex chain answered
   by crushing each box toward zero and letting its text paint over the row
   below — the fullscreen card's old bug (see styles/fullscreen.js), replayed
   on the face. The wheel works over it on the canvas via keepScroll, wired
   where the well is built. */
.mmc-well {
  display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0;
  overflow-y: auto;
}
/* Nothing in the well may be shorter than what it holds — the well scrolls
   instead. Without this the rewrite's textareas were the give in the chain. */
.mmc-well > * { flex-shrink: 0; }
.mmc-panel-corner { position: absolute; top: 10px; right: 10px; z-index: 1; }
.mmc-expand {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; padding: 0; border-radius: 8px; cursor: pointer;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-off); opacity: .55; transition: opacity .12s ease, color .12s ease;
}
.mmc-panel:hover .mmc-expand { opacity: 1; }
.mmc-expand:hover { color: var(--mmc-text); border-color: var(--mmc-line-2); }
/* Lit once the text no longer fits: at that point the window is not a shortcut,
   it is where the writing is. */
.mmc-expand.on { opacity: 1; color: var(--mmc-accent); border-color: color-mix(in srgb, var(--mmc-accent) 45%, transparent); }
/* Room for it, so a long first line does not run under the button. */
.mmc-panel .mmc-well > .mmc-prompt-fold > .mmc-prompt { padding-right: 30px; }

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
.mmc-editor-sheet-sub { color: var(--mmc-dim); font-size: calc(13px * var(--mmc-type)); }
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
  flex: 1; min-height: calc(56px * var(--mmc-type)); max-height: calc(168px * var(--mmc-type)); background: none; border: 0; outline: none;
  color: var(--mmc-text); font-family: inherit; font-size: calc(15px * var(--mmc-type)); line-height: 1.6;
  white-space: pre-wrap; word-break: break-word; overflow-y: auto;
}
.mmc-prompt:empty::before {
  content: attr(data-placeholder); color: var(--mmc-off); pointer-events: none;
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
/* flex-basis auto, shrink 0: the fold may grow into spare room but never below
   its content — undersized, it is the well that scrolls, not this that folds
   its text over the rewrite underneath. */
.mmc-prompt-fold { display: flex; flex-direction: column; gap: 8px; flex: 1 0 auto; min-height: 0; }
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
   rewrite this is the prompt, and a prompt does not need announcing.

   Nothing else may live in here. The compiled prompt's control was put on this
   row for one release and the row is a <summary>: a click anywhere it did not
   land on the button folded the whole prompt away, which read as the control
   doing nothing and then showing you your own sentence. It is a rail under the
   box now — see .mmc-compiled. */
.mmc-prompt-head { display: none; }
.mmc-prompt-fold.superseded > .mmc-prompt-head {
  display: flex; align-items: center; gap: 7px; min-width: 0;
  padding: 4px 6px; margin: -4px -6px; border-radius: 9px;
  color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); cursor: pointer; list-style: none;
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
/* --- what the model reads -------------------------------------------------- */
/* The compiled prompt, under the sentence it is built from rather than in place
   of it. It *contains* that sentence, so a view that swapped the two asked you
   to hold the first in your head to see what the second added — and on a shot
   with nothing to declare the two are near enough identical that the panel read
   as broken. Stacked, the difference is the thing on screen.

   The rail is a button and not a <summary>: this used to sit on the prompt's own
   fold head, where every click that missed the control folded the prompt away
   instead. */
.mmc-compiled { display: flex; flex-direction: column; flex: none; }
.mmc-compiled:empty { display: none; }
.mmc-compiled-rail {
  display: flex; align-items: center; gap: 7px; width: 100%; text-align: left;
  appearance: none; border: 0; background: none; cursor: pointer;
  padding: 7px 0 0; margin-top: 3px; border-top: 1px solid var(--mmc-line);
  color: var(--mmc-off); font: inherit; font-size: calc(11.5px * var(--mmc-type));
}
.mmc-compiled-rail:hover { color: var(--mmc-text); }
.mmc-compiled-rail:focus-visible {
  outline: 1px solid var(--mmc-accent); outline-offset: 3px; border-radius: 6px;
}
.mmc-compiled-title { flex: none; }
.mmc-compiled-rail svg {
  flex: none; transform: rotate(-90deg); transition: transform .14s ease;
}
.mmc-compiled.open .mmc-compiled-rail svg { transform: none; }
/* Which pass this is, and anything true of it the text does not say: a merged
   run, a prompt replaced by hand, a clip that generates nothing. */
.mmc-compiled-status {
  margin-left: auto; min-width: 0; overflow: hidden; white-space: nowrap;
  text-overflow: ellipsis; color: var(--mmc-off);
  font-size: calc(10px * var(--mmc-type)); letter-spacing: .09em; text-transform: uppercase;
}
.mmc-compiled.problem .mmc-compiled-status { color: var(--mmc-warn); }
/* Dimmed, never emptied, while a re-read is out: the panel re-reads on every
   keystroke, and replacing prose somebody is reading with a waiting state that
   often is worse than one stale word. */
.mmc-compiled.loading .mmc-compiled-doc { opacity: .55; }

.mmc-compiled-doc { display: none; }
/* Capped and scrolled — a node face is a fixed rectangle, and a twenty-line
   document opened inside one would push the render button off the bottom of it.
   A little taller than the box above it, because six sections is a document and
   four lines of one is a teaser; the wheel scrolls the rest (see keepScroll in dom.js),
   which on a graph canvas it otherwise would not. */
.mmc-compiled.open .mmc-compiled-doc {
  display: flex; flex-direction: column; gap: 11px;
  max-height: 220px; overflow-y: auto;
  /* The left inset is the accent rule's lane — see .mine below, which hangs
     into it. Without it the rule fell outside the scroll box and was clipped
     away, which took the panel's one mark with it. */
  padding: 11px 2px 2px 12px;
  user-select: text; cursor: default;
}
.mmc-editor-sheet-body .mmc-compiled.open .mmc-compiled-doc { max-height: 40vh; }

.mmc-compiled-block { display: flex; flex-direction: column; gap: 3px; }
/* The wire key, set as a wire key: the one monospaced thing in this pack, which
   is what says at a glance that this half of the panel is machine-facing and
   the box above it is not. Left in snake_case and not prettified — it is the
   field name the model is handed, and renaming it here would be inventing a
   second name for it. */
.mmc-compiled-key {
  display: flex; align-items: baseline; gap: 7px;
  color: var(--mmc-off); font-size: calc(10px * var(--mmc-type)); letter-spacing: .04em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.mmc-compiled-value {
  margin: 0; color: var(--mmc-dim); font-size: calc(12.5px * var(--mmc-type)); line-height: 1.6;
  white-space: pre-wrap; overflow-wrap: anywhere;
}
/* The one mark in here, on the one block that is yours. Everything above and
   below it is what the compiler added, which is the question the panel exists
   to answer — so it is answered with an accent rather than with a legend. */
.mmc-compiled-block.mine {
  border-left: 2px solid var(--mmc-accent); padding-left: 10px; margin-left: -12px;
}
.mmc-compiled-block.mine .mmc-compiled-value { color: var(--mmc-text); }
.mmc-compiled-mine {
  color: var(--mmc-accent); font-family: inherit; font-size: calc(10px * var(--mmc-type));
  letter-spacing: .06em; text-transform: uppercase;
}
.mmc-compiled-note, .mmc-compiled-empty {
  margin: 0; color: var(--mmc-off); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.55;
}
.mmc-compiled-problem {
  margin: 0; color: var(--mmc-warn); font-size: calc(12.5px * var(--mmc-type)); line-height: 1.6;
}
/* Where the sections will be, while the first answer is outstanding. */
.mmc-compiled-bar {
  height: 9px; border-radius: 4px; background: var(--mmc-surface-2);
  animation: mmc-compiled-pulse 1.2s ease-in-out infinite;
}
@keyframes mmc-compiled-pulse { 0%, 100% { opacity: .45; } 50% { opacity: .9; } }
@media (prefers-reduced-motion: reduce) {
  .mmc-compiled-bar { animation: none; }
  .mmc-compiled-rail svg { transition: none; }
}
/* Dimmed with the box it belongs to: while a rewrite stands in for the prompt,
   neither of them is what gets queued. */
.mmc-prompt-fold.superseded > .mmc-compiled { opacity: .42; }

/* .mmc-ref, not .mmc-chip: the refiner's language chips own that name, and the
   two rules fighting over it is what once turned these gray. */
.mmc-ref {
  display: inline-block; padding: 1px 7px; margin: 0 1px; border-radius: 7px;
  background: color-mix(in srgb, var(--tag, var(--mmc-accent)) 14%, transparent);
  color: var(--tag, var(--mmc-accent));
  font-size: .92em; white-space: nowrap; user-select: all;
}
/* A name whose file is muted. The tag colour is what says "this is a picture in
   this shot", so a muted one gives it up and keeps only the shape: the sentence
   still reads, and the word no longer claims something the render is not doing.
   Struck through for the same reason a muted LoRA's name is. */
.mmc-ref.mmc-ref-off {
  background: var(--mmc-wash); color: var(--mmc-dim); text-decoration: line-through;
}

/* --- a spoken line --------------------------------------------------------
 *
 * Deliberately not a .mmc-ref pill. A reference chip is a label: it stands in
 * for a file, and reading as a token is the whole of its job. A line of
 * dialogue is not a label for anything — it is words that are heard, sitting
 * inside a sentence about what is seen — so it gives the pill up and takes a
 * rule down its left edge instead. That mark is already in this pack, on
 * .mmc-compiled-block.mine, where it says "this part of the text is yours".
 * Here it says: this part is heard.
 *
 * Wrapping, unlike a handle: a line can be a sentence long, and a chip that
 * refused to break would push the box sideways. The rule draws once at the
 * start rather than on every fragment, which is what slicing already does.
 *
 * No ground behind it, and that is the whole of what was learned by looking at
 * it: a tint under a chip that wraps is drawn again on the continuation, and
 * the second block reads as a second line of dialogue. It also put two tinted
 * shapes in a box whose one tinted shape used to mean "a file is cited here".
 * The rule alone says everything the tint was saying, and says it once.
 */
.mmc-say {
  display: inline; padding-left: 7px; margin-right: 4px;
  border-left: 2px solid var(--tag, var(--mmc-accent));
  user-select: all;
}
/* A voice in the room and a voice over the picture are the same words and a
   different sound. A broken line is what that difference looks like. */
.mmc-say-over { border-left-style: dashed; }
/* Pressable, and saying so. Clicking the line reopens the menu on it, which is
   the only way to change who says it or how without deleting the whole thing
   and typing the quote again — so the chip claims the pointer the way a cast
   name does, and lifts under it. */
.mmc-say { cursor: pointer; }
.mmc-say:hover { background: color-mix(in srgb, var(--tag, var(--mmc-accent)) 12%, transparent); }
.mmc-say-who { color: var(--tag, var(--mmc-accent)); font-size: .92em; }
/* The two that are usually silent. Set as the micro-label this pack already
   uses for a mark on a block (see .mmc-compiled-mine), because that is what
   they are: not part of the sentence, and not competing with the words. */
.mmc-say-how, .mmc-say-lang {
  color: var(--mmc-faint); font-size: calc(9.5px * var(--mmc-type));
  letter-spacing: .07em; text-transform: uppercase; margin-left: 5px;
}
/* The words are the content of the chip and are set as such: the plain body
   colour, at the box's own size, inside the quotes that say they are spoken. */
.mmc-say-words { color: var(--mmc-strong); margin-left: 5px; }

/* Somebody's name, where clicking it opens them (see PromptBox's click handler
   and CreatorEditor.openCastMember). Inside a contenteditable the
   cursor is a caret by default, which says "text" about the one thing in the
   box that is not text — so the chip claims the pointer, and lifts under it,
   the way everything else in the pack that does something does. */
.mmc-prompt-castable .mmc-ref-cast { cursor: pointer; }
.mmc-prompt-castable .mmc-ref-cast:hover {
  background: color-mix(in srgb, var(--tag, var(--mmc-accent)) 26%, transparent);
}

/* --- @ mention menu ------------------------------------------------------- */
.mmc-mention {
  position: fixed; z-index: 1350; width: 330px; max-height: 300px; overflow-y: auto;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 14px;
  padding: 6px; box-shadow: 0 20px 50px var(--mmc-shadow);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
}
.mmc-mention-head {
  color: var(--mmc-faint); font-size: calc(10px * var(--mmc-type)); letter-spacing: .09em; text-transform: uppercase;
  padding: 10px 10px 6px;
}
/* min-width:0 all the way down: a flex item defaults to min-content width, so
   without it a 90-character generated filename forces the row wider than the
   menu instead of ellipsizing. */
.mmc-mention-row {
  display: flex; align-items: center; gap: 10px; width: 100%; min-width: 0;
  padding: 7px 8px; background: none; border: 1px solid transparent;
  border-radius: 10px; font-family: inherit; text-align: left; cursor: pointer;
  color: var(--mmc-text); overflow: hidden;
}
.mmc-mention-row[aria-selected="true"] { background: var(--mmc-surface-3); border-color: var(--mmc-wash-2); }
.mmc-mention-thumb {
  width: calc(30px * var(--mmc-type)); height: calc(30px * var(--mmc-type)); border-radius: 7px; object-fit: cover; flex: none;
  background: var(--mmc-surface-3); display: flex; align-items: center; justify-content: center;
  color: var(--mmc-dim); font-size: calc(13px * var(--mmc-type));
}
.mmc-mention-text { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.mmc-mention-handle {
  color: var(--tag, var(--mmc-accent)); font-size: calc(14px * var(--mmc-type));
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-mention-sub {
  color: var(--mmc-faint); font-size: calc(11px * var(--mmc-type)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-mention-empty { color: var(--mmc-faint); font-size: calc(13px * var(--mmc-type)); padding: 14px 10px; }

/* --- the quote menu's own rows ---------------------------------------------
 *
 * The same rows, answering a different kind of question. Everywhere else in
 * this menu a row is a result — a file, a person, a look — and choosing one
 * puts it in the sentence. Here a row is a setting, and one of them is already
 * in force, so the list has to be able to say which. That mark is the only
 * thing these rows add.
 */
/* The mark, and only the mark. Recolouring the name to the accent was the
   first try and it took a person's tag colour off them — that colour is who
   they are everywhere else in this pack, and a row that changes it to say
   "chosen" is answering a different question from the one it was asked. */
.mmc-say-row[aria-checked="true"]::after {
  content: "✓"; color: var(--mmc-accent); font-size: calc(12px * var(--mmc-type));
  flex: none; padding-right: 2px;
}
/* What Enter would write, under the two answers it would write it from.
   A readout that happens to be pressable rather than three more rows: they are
   not alternatives to Spoken, they are what Spoken currently means. */
.mmc-say-bar {
  display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
  margin: 4px 2px 0; padding: 8px 6px 2px; border-top: 1px solid var(--mmc-line);
}
.mmc-say-dial {
  padding: 3px 9px; border-radius: 7px; border: 1px solid var(--mmc-line);
  background: var(--mmc-surface-3); color: var(--mmc-dim);
  font-family: inherit; font-size: calc(11px * var(--mmc-type));
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;
}
.mmc-say-dial.wide { color: var(--mmc-text); max-width: 150px; }
.mmc-say-dial:hover { background: var(--mmc-wash); color: var(--mmc-text); }
.mmc-say-dial:focus-visible { outline: none; border-color: var(--mmc-blue); }
.mmc-say-more { color: var(--mmc-faint); font-size: calc(14px * var(--mmc-type)); margin-left: auto; }
/* Describing a voice is casting one, so the menu becomes the one field that
   asks. Nothing else is left in it: there is no list any more, only a question. */
.mmc-say-ask { display: flex; flex-direction: column; gap: 6px; padding: 2px 8px 8px; }
/* Deeper than the card it sits in, and outlined. On the menu's own surface it
   was neither, and a line of text with no edge to it reads as something being
   shown rather than something to type in — which is the one thing this field
   has to say. */
.mmc-say-field {
  width: 100%; padding: 9px 11px; border-radius: 9px;
  border: 1px solid var(--mmc-wash-2); background: var(--mmc-surface-3);
  color: var(--mmc-text); font-family: inherit; font-size: calc(13.5px * var(--mmc-type));
}
.mmc-say-field::placeholder { color: var(--mmc-off); }
.mmc-say-field:focus { outline: none; border-color: var(--mmc-blue); background: var(--mmc-surface-2); }
.mmc-say-field::selection { background: color-mix(in srgb, var(--mmc-blue) 40%, transparent); }
.mmc-say-ask .mmc-mention-sub { white-space: normal; }
.mmc-say-row .mmc-mention-sub { white-space: normal; }
.mmc-say-row { align-items: flex-start; }
.mmc-say-row .mmc-mention-thumb { margin-top: 1px; }
/* A word on its own still starts where the words beside a tile do, so the two
   kinds of list read as one menu rather than as two left edges. */
.mmc-say-bare { padding-left: 18px; }

/* --- the / menu's own rows -------------------------------------------------
 *
 * The same menu with a layer over it. A source row is not a thing you can cite
 * — it is the question of where a thing comes from — so it reads as a heading
 * you can press rather than as a result: the name in the body colour instead of
 * a handle's, and a chevron saying the list goes on behind it.
 */
.mmc-mention-branch .mmc-mention-handle { color: var(--mmc-text); }
/* A look's row is the descriptor, not a handle — it has no name until it is
   cast, so the tag colour every other row wears would be a promise about a
   thing that does not exist yet. Its frame is the picture beside it, and the
   rest of the descriptor is the second line. */
.mmc-mention-style .mmc-mention-handle { color: var(--mmc-text); font-size: calc(13px * var(--mmc-type)); }
.mmc-mention-style .mmc-mention-thumb { object-fit: cover; }
.mmc-mention-glyph { color: var(--mmc-dim); }
.mmc-mention-more { color: var(--mmc-faint); font-size: calc(15px * var(--mmc-type)); flex: none; padding-right: 2px; }
/* The way back, above the narrowed list and reading as the thing it undoes.
   Full width so it is a bar rather than a fourth row in the results. */
.mmc-mention-back {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 6px 10px; margin-bottom: 2px; background: none; border: 0;
  border-bottom: 1px solid var(--mmc-line); border-radius: 0;
  color: var(--mmc-faint); font-family: inherit; font-size: calc(11px * var(--mmc-type)); text-align: left; cursor: pointer;
}
.mmc-mention-back:hover { color: var(--mmc-text); }

.mmc-pills { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.mmc-pill {
  display: flex; align-items: center; gap: 7px; height: var(--mmc-pill-h); padding: 0 14px;
  border-radius: 19px; background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-size: calc(13px * var(--mmc-type)); font-family: inherit; cursor: pointer;
  white-space: nowrap; transition: background .12s ease;
}
.mmc-pill:hover:not(:disabled) { background: var(--mmc-surface-3); }
.mmc-pill:disabled { cursor: not-allowed; color: var(--mmc-off); }
.mmc-pill svg { width: 16px; height: 16px; stroke: currentColor; fill: none;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.mmc-pill-sub { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); }
/* The pill that leads a piece's row: which architecture renders it. No fill and
   no accent — both are taken, and neither is what this says. A model is a name,
   not a state, so the only mark it gets is the weight a name is set in. That is
   enough to make the row read as "MiniMax H3: these frames, this long, this
   canvas" rather than as five equal settings. */
.mmc-pill-model .mmc-model-name { color: var(--mmc-strong); font-weight: 500; }
.mmc-pill-group { gap: 0; padding: 0 6px; }
/* Several closely related controls in one pill, divided by hairlines — the two
   ends of the shot, the canvas and its short edge, the sampler and its
   scheduler, Spectrum and its blend. Two loose pills read as two unrelated
   features; one pill with a divider through it says they are two halves of one
   setting.

   The body is the turbo switch's quality stops (styles/timeline.js), declaration
   for declaration, with as many segments as the control has answers. That pill
   is the prototype and it keeps its own rules: it was right before there was a
   general one, and anything here that drifted from it would be a second opinion
   about a question already settled. What is added below is only what a segment
   that is not one of three stops still needs — a disabled state, a focus ring
   the clipped corners cannot cut, and room for a stepper.

   Not .mmc-seg: that name is taken twice already — the LoRA card's tri-state
   and the trim editor's track switch (styles/loras.js, styles/overlays.js) —
   and both of those are the *container* of a segmented control, bordered and
   rounded. Both load after this file, so a segment wearing that name was drawn
   as a pill inside the pill. */
.mmc-pill-set { gap: 0; padding: 0; overflow: hidden; }
.mmc-pill-seg {
  display: flex; align-items: center; gap: 5px; height: 100%; padding: 0 12px;
  background: none; border: 0; border-left: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(13px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-pill-seg:first-child { border-left: 0; }
.mmc-pill-seg:hover { color: var(--mmc-text); }
.mmc-pill-seg[aria-pressed="true"], .mmc-pill-seg.accel-on {
  background: color-mix(in srgb, var(--mmc-role-motion) 14%, transparent); color: var(--mmc-role-motion);
}
.mmc-pill-seg[aria-pressed="true"] .mmc-pill-sub, .mmc-pill-seg.accel-on .mmc-pill-sub {
  color: color-mix(in srgb, var(--mmc-role-motion) 75%, transparent);
}
/* Lit, a stepper lights through — the rule .mmc-pill.accel-on already follows. */
.mmc-pill-seg.accel-on .mmc-step:not(:disabled) { color: inherit; }
.mmc-pill-seg:disabled { color: var(--mmc-off); cursor: not-allowed; }
/* The set clips its corners, so a ring drawn outside a segment is cut in half.
   Inset, and it stays a ring. */
.mmc-pill-seg:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
/* A stepper as a segment: the +/- sit as tight against the divider as they do
   against a standalone group's edge. */
.mmc-pill-seg-group { padding: 0 4px; gap: 0; }
/* The duration pill's tail: how long the reference this shot is generated
   against runs, and one click to land the card on it. Divided off like a
   segment, because it answers a different question from the stepper beside it —
   that one sets a length, this one reports one. Agreement wears the same place
   and the same divider with no affordance at all: there is nothing to press
   when the two lengths already agree. */
.mmc-dur-match, .mmc-dur-match.on {
  display: flex; align-items: center; gap: 6px; height: 100%; margin-left: 6px; padding: 0 10px;
  background: none; border: 0; border-left: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12px * var(--mmc-type));
  white-space: nowrap;
}
.mmc-dur-match { cursor: pointer; }
.mmc-dur-match:hover { color: var(--mmc-text); }
.mmc-dur-match:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-dur-match.on { color: var(--mmc-off); cursor: default; }
/* The duration group's other tail: the switch that hands the length to the
   model. Same shape as the match above — a word behind a hairline at the end of
   the group — because it is the same slot answering the same question. It is a
   switch rather than a readout, so it lights in the accent when it is the one
   deciding, and the seconds beside it go dim and grow a "~" to match. */
.mmc-dur-auto {
  display: flex; align-items: center; height: 100%; margin-left: 6px; padding: 0 10px;
  background: none; border: 0; border-left: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12px * var(--mmc-type));
  white-space: nowrap; cursor: pointer;
}
.mmc-dur-auto:hover { color: var(--mmc-text); }
.mmc-dur-auto:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-dur-auto.on { color: var(--mmc-accent); }
.mmc-step {
  background: none; border: 0; color: var(--mmc-text); cursor: pointer;
  font-size: calc(16px * var(--mmc-type)); width: calc(26px * var(--mmc-type)); height: calc(36px * var(--mmc-type)); font-family: inherit;
}
.mmc-step:disabled { color: var(--mmc-off); cursor: not-allowed; }
/* No text-transform: the socket name has to read exactly as it does on the
   input, and 'model_fl2va' uppercased is not the name of anything. */
/* The row's tail: the route badge and the pills that say what this shot belongs
   to. Held against the far end of a row that fits, and wrapped as one thing by a
   row that does not — see CreatorEditor.renderPills. The auto margin is on the
   group rather than on the badge for exactly that: an auto margin on a bare
   badge is inherited by the line it happens to wrap onto, which is how a lone
   Timeline pill ended up alone against the right edge of the fullscreen card. */
.mmc-pills-tail {
  display: flex; align-items: center; gap: 8px; margin-left: auto;
  /* And if the tail alone outgrows the row, it breaks inside itself rather than
     off the edge of the card. */
  flex-wrap: wrap;
}
/* The route badge. A readout rather than a control, but it stands in the pill
   row and takes the row's height — padding-sized, it was two-thirds as tall as
   everything beside it, which read as a fragment of the row rather than the end
   of it. Transparent, so height is all it borrows. */
.mmc-mode {
  font-size: calc(11px * var(--mmc-type)); letter-spacing: .04em; color: var(--mmc-dim);
  display: flex; align-items: center; gap: 6px; height: var(--mmc-pill-h);
  background: none; border: 1px solid transparent; border-radius: 19px;
  padding: 0 12px; font-family: inherit; box-sizing: border-box;
}
/* Only the clickable form gets affordances — as a span it is a plain readout. */
button.mmc-mode { cursor: pointer; }
button.mmc-mode:hover { background: var(--mmc-surface-2); border-color: var(--mmc-line); }
.mmc-mode.pinned { border-color: var(--mmc-line); background: var(--mmc-surface-2); }
.mmc-mode b { color: var(--mmc-accent); font-weight: 600; }
.mmc-pin {
  font-size: calc(10px * var(--mmc-type)); letter-spacing: .06em; text-transform: uppercase;
  color: var(--mmc-accent); border: 1px solid currentColor; border-radius: 8px;
  padding: 0 5px; opacity: .8;
}
.mmc-warn { color: var(--mmc-warn); font-size: calc(12px * var(--mmc-type)); }

`;
