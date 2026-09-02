// Popovers: output prefix, chips, short-edge slider.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- popovers ------------------------------------------------------------- */
.mmc-pop {
  position: fixed; z-index: 1300; background: var(--mmc-float); border: 1px solid var(--mmc-line);
  border-radius: 16px; padding: 8px; min-width: 190px;
  /* Said out loud, because a popover is portaled to document.body and so stands
     outside every root this pack draws: what it inherits is ComfyUI's own body
     colour, whatever the installed theme makes that. Every other line in here
     names its colour and looked right; the one that did not — the short-edge
     readout, the biggest number on the card — came out at whatever the page
     underneath happened to be, which on the dark theme is barely on the panel
     at all. The floor is the pack's own text colour and the rest still overrides
     it downward. */
  color: var(--mmc-text);
  /* And the face, for the same reason and from the same omission — every other
     portaled root in the pack (.mmc-overlay, .mmc-sheet) states its own. */
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
  box-shadow: 0 18px 48px var(--mmc-shadow);
  /* Never taller than the screen: on a 1080p display the refine popover's
     stacked sections can outgrow the viewport, and placeNear can only clamp
     the top edge. The popover scrolls instead of the bottom clipping off. */
  max-height: calc(100vh - 16px); overflow-y: auto;
}
.mmc-pop-title { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); padding: 6px 10px 8px; }

/* The find line on a long list. It sits where the title sits and is set like
   the title — dim, small, no box — so a list of files opens looking as it did
   and answers typing at once. It stays put while the list scrolls under it. */
.mmc-pop-findrow {
  display: flex; align-items: baseline; gap: 10px;
  position: sticky; top: -8px; z-index: 1;
  margin: -8px -8px 2px; padding: 14px 18px 8px;
  background: var(--mmc-float); border-bottom: 1px solid var(--mmc-line);
}
.mmc-pop-find {
  flex: 1; min-width: 0; padding: 0; background: none; border: 0; outline: 0;
  color: var(--mmc-text); font: inherit; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-pop-find::placeholder { color: var(--mmc-dim); }
.mmc-pop-count {
  flex: none; color: var(--mmc-faint); font-size: calc(11px * var(--mmc-type));
  font-variant-numeric: tabular-nums;
}
.mmc-pop-none { color: var(--mmc-dim); font-size: calc(12.5px * var(--mmc-type)); padding: 10px 10px 8px; }
/* What the query found, inside a name: underlined in the accent rather than
   set bold, because a filename is long and a bold fragment breaks its rhythm. */
.mmc-hit {
  text-decoration: underline; text-decoration-color: var(--mmc-accent);
  text-decoration-thickness: 1.5px; text-underline-offset: 3px;
}
/* The keyboard's row while finding — Enter picks it, the arrows move it. */
.mmc-opt[data-cursor="true"] { background: var(--mmc-surface-2); }

/* The output-prefix field and its live reading — Settings → Folders is the only
   place these appear now that the per-node popover is gone. */
.mmc-out-field {
  width: 100%; box-sizing: border-box; padding: 8px 10px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 10px; color: var(--mmc-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(12.5px * var(--mmc-type));
  /* A contenteditable, not an input — see folderRow. So it has to be told the
     things an input knows by itself: that it is one line tall when empty, that
     a click anywhere in it is a caret, and that the spaces someone types are
     theirs to keep until the path is cleaned. */
  min-height: calc(19px * var(--mmc-type)); line-height: calc(19px * var(--mmc-type));
  cursor: text; white-space: pre-wrap; overflow-wrap: anywhere;
}
.mmc-out-field:focus { outline: none; border-color: var(--mmc-blue); }
.mmc-out-field.bad { border-color: var(--mmc-warn); }
/* A token, whole. Set in the path's own type at the path's own size and only a
   shade lifted off it, because it is a piece of the folder name and not a
   control sitting on top of one — the tile says "this part is filled in later",
   and saying more than that would make the literal text look like the guest. */
.mmc-out-tile {
  display: inline-block; padding: 0 4px; border-radius: 5px;
  background: var(--mmc-surface-3); color: var(--mmc-text);
  /* The caret parks either side of a tile and never inside it; a drag across
     the field must not be able to take half of one either. */
  user-select: none; -webkit-user-select: none; white-space: nowrap;
}
.mmc-out-problem { color: var(--mmc-warn); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; padding: 6px 2px 0; }
/* One line, two colours: the folder half dim, the filename bright. The colour
   break carries what two labelled rows used to — that the last path part names
   the files, not a folder. */
.mmc-out-example {
  padding: 8px 2px 2px; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.6;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--mmc-text);
  /* A dated folder name is long, and the card must not scroll sideways for it. */
  overflow-wrap: anywhere;
}
.mmc-out-dim { color: var(--mmc-off); }
.mmc-out-tokens { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 8px 2px 2px; }
/* Says what the chips do, in the same voice the note-keys use — a bare row of
   single words reads as filters until something names the action. */
.mmc-out-tokens-key {
  color: var(--mmc-off); font-size: calc(10px * var(--mmc-type)); letter-spacing: .06em;
  text-transform: uppercase; padding-right: 4px;
}
/* A chip says the word it writes and what that word is worth right now. The
   value is the useful half — "month" never said whether it meant 08 or August,
   and that is the folder name — so it is shown at the point of choosing rather
   than only in the reading underneath. */
.mmc-out-token {
  display: inline-flex; align-items: baseline; gap: 5px;
  padding: 3px 7px; background: var(--mmc-surface-2); border: 0; border-radius: 7px;
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); font-family: ui-monospace, Menlo, monospace;
  cursor: pointer;
}
.mmc-out-token:hover { background: var(--mmc-surface-3); color: var(--mmc-text); }
.mmc-out-token-now { color: var(--mmc-off); }
.mmc-out-token:hover .mmc-out-token-now { color: var(--mmc-dim); }

.mmc-opt {
  display: flex; align-items: center; justify-content: space-between; width: 100%;
  padding: 9px 10px; background: none; border: 0; border-radius: 10px;
  color: var(--mmc-text); font-size: calc(14px * var(--mmc-type)); font-family: inherit; cursor: pointer;
  /* A button centres its text by default, which nothing notices while every
     option is one short word and looks broken the moment one wraps. */
  text-align: left;
}
.mmc-opt:hover { background: var(--mmc-surface-2); }
.mmc-opt-label { display: flex; align-items: center; gap: 10px; }
.mmc-aspect-glyph {
  width: 18px; height: 18px; flex: none;
  display: flex; align-items: center; justify-content: center;
}
.mmc-aspect-glyph > span { box-sizing: border-box; border: 1.5px solid var(--mmc-edge-2); border-radius: 2px; }
.mmc-opt[aria-checked="true"] .mmc-aspect-glyph > span { border-color: var(--mmc-blue); }
/* On a pill it is a glyph beside a label rather than a swatch in a list, so it
   takes the pill's own colour — and greys out with it when the ratio is coming
   from a keyframe and the pill is disabled. */
.mmc-pill .mmc-aspect-glyph > span { border-color: currentColor; border-width: 1.25px; }
/* --- the aspect grid ------------------------------------------------------
   Six shapes across two rows instead of ten rows of near-identical text: the
   glyph is what is being chosen here, so it is what the tile is mostly made
   of, and the numbers under it are the caption. Ordered widest to squarest, so
   the grid is aimed at rather than read.

   Not .mmc-seg for the switch: that name belongs to two other controls already
   (styles/loras.js, styles/overlays.js) and both load after this file, so a
   switch wearing it would be redrawn by whichever won. */
.mmc-aspect-head { display: flex; align-items: center; gap: 8px; padding: 2px 2px 6px; }
.mmc-aspect-title { flex: 1; padding: 0 0 0 8px; }
.mmc-aspect-flip {
  flex: 1; display: flex; height: 26px; border-radius: 13px; overflow: hidden;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
}
.mmc-flip-opt {
  flex: 1; padding: 0 10px; cursor: pointer; background: none; border: 0;
  border-left: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); font-family: inherit;
}
.mmc-flip-opt:first-child { border-left: 0; }
.mmc-flip-opt:hover { color: var(--mmc-text); }
.mmc-flip-opt[aria-pressed="true"] {
  background: color-mix(in srgb, var(--mmc-blue) 22%, transparent); color: var(--mmc-text);
}
.mmc-aspect-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; }
.mmc-aspect-tile {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px;
  padding: 10px 4px; background: none; border: 0; border-radius: 10px; cursor: pointer;
  color: var(--mmc-dim); font-family: inherit;
  font-size: calc(12px * var(--mmc-type)); font-variant-numeric: tabular-nums;
}
.mmc-aspect-tile:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-aspect-tile[aria-checked="true"] {
  background: color-mix(in srgb, var(--mmc-blue) 14%, transparent); color: var(--mmc-text);
  box-shadow: inset 0 0 0 1px var(--mmc-blue);
}
.mmc-aspect-tile[aria-checked="true"] .mmc-aspect-glyph > span { border-color: var(--mmc-blue); }
/* A shape the family lists one way up only, seen the other way: it holds its
   column so the grid does not change width under the switch, and goes dead so
   that a tile which looks identical in both settings cannot read as a switch
   that did nothing. Still lit when it is the ratio in force — that pairing is
   the whole message, "what you have is not available tall". */
.mmc-aspect-tile:disabled { color: var(--mmc-off); cursor: not-allowed; }
.mmc-aspect-tile:disabled:hover { background: none; color: var(--mmc-off); }
.mmc-aspect-tile:disabled .mmc-aspect-glyph > span,
.mmc-aspect-tile:disabled[aria-checked="true"] .mmc-aspect-glyph > span {
  border-color: var(--mmc-off); border-style: dashed;
}
.mmc-aspect-tile:disabled[aria-checked="true"] {
  background: none; box-shadow: inset 0 0 0 1px var(--mmc-line-2);
}
.mmc-flip-opt:focus-visible, .mmc-aspect-tile:focus-visible {
  outline: 2px solid var(--mmc-accent); outline-offset: -2px;
}

.mmc-radio {
  width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid var(--mmc-edge); flex: none;
}
.mmc-opt[aria-checked="true"] .mmc-radio {
  border-color: var(--mmc-blue); background: var(--mmc-blue);
  display: flex; align-items: center; justify-content: center;
}
.mmc-opt[aria-checked="true"] .mmc-radio::after {
  content: ""; width: 5px; height: 9px; border: solid var(--mmc-strong);
  border-width: 0 2px 2px 0; transform: rotate(45deg) translate(-1px,-1px);
}
/* The short-edge popover. Every measurement here is fixed on purpose: a range
   input reads the pointer against the width of its own track, so a popover that
   grows by a digit — or reflows a note onto a second line — slides the track out
   from under the thumb and the value jumps. Fixed width, tabular digits, and a
   note that always occupies two lines. Nothing in it may size to its text. */
.mmc-slider { width: 300px; padding: 12px; box-sizing: border-box; }
.mmc-slider-body { display: flex; flex-direction: column; gap: 8px; }
.mmc-slider-read {
  display: flex; align-items: baseline; justify-content: space-between;
  font-size: calc(13px * var(--mmc-type)); font-variant-numeric: tabular-nums; line-height: 20px;
}
.mmc-slider-read .mmc-edge { font-size: calc(16px * var(--mmc-type)); }
.mmc-slider-read .mmc-edge-unit { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); margin-left: 3px; }
.mmc-slider-read > span:last-child { color: var(--mmc-dim); }

.mmc-slider-row { display: flex; align-items: center; gap: 2px; }
/* The tick sits below the rail rather than over it, so it can be a real click
   target without eating the drag it is standing next to. */
.mmc-slider-track { position: relative; flex: 1; padding-bottom: 14px; min-width: 0; }
.mmc-slider input[type="range"] {
  display: block; width: 100%; margin: 0; height: 20px; accent-color: var(--mmc-blue);
}
.mmc-slider-mark {
  position: absolute; bottom: 0; height: calc(14px * var(--mmc-type)); width: calc(34px * var(--mmc-type)); padding: 0; border: 0;
  background: none; cursor: pointer; font-family: inherit; font-size: calc(9px * var(--mmc-type));
  letter-spacing: .04em; color: var(--mmc-off);
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  /* A range thumb is 16px, so the track it travels is inset 8px each side —
     the tick has to land on the value, not on the box. */
  left: calc(8px + var(--p) * (100% - 16px)); margin-left: -17px;
}
.mmc-slider-mark::before { content: ""; width: 2px; height: 4px; border-radius: 1px; background: currentColor; }
.mmc-slider-mark:hover { color: var(--mmc-text); }
.mmc-slider-mark.on { color: var(--mmc-blue); }

.mmc-native { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); line-height: 1.45; min-height: calc(32px * var(--mmc-type)); }
.mmc-native.over { color: var(--mmc-warn); }

/* The two-pass section under the slider, drawn only past the native edge. Its
   option rows are the aspect popover's; only the second line is its own. */
.mmc-twopass {
  border-top: 1px solid var(--mmc-line); margin-top: 10px; padding-top: 6px;
  display: flex; flex-direction: column; gap: 2px;
}
.mmc-opt-col { flex-direction: column; align-items: flex-start; gap: 2px; }
.mmc-opt-sub { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); }
.mmc-refine-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 10px 0;
}
.mmc-refine-label { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); }

/* The face-pass popover: the same option rows and knob rows as the two-pass
   section above, plus one line saying what it costs. Fixed width so the note
   does not reflow the popover as the knobs change. */
.mmc-faces-pop { width: 260px; }
.mmc-pop-note {
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); line-height: 1.45;
  padding: 8px 10px 2px; border-top: 1px solid var(--mmc-line); margin-top: 6px;
}

/* --- the reference card ---------------------------------------------------- */
/*
 * One reference, opened from its name in the chip row. It replaces four small
 * buttons that sat inside the chip itself — which fit a node face only by being
 * tiny, and which the simple fullscreen view hid whenever they still held their
 * default. The default is the answer you are trying to leave, so that view
 * could not narrow a reference at all.
 *
 * Wider than a menu because the rows are label-and-answers rather than a list,
 * and a fixed width so picking "person" after "full" does not resize the card
 * under the pointer.
 */
.mmc-refsheet { width: 300px; padding: 10px; }
.mmc-refsheet-head {
  display: flex; align-items: baseline; gap: 8px; padding: 2px 2px 10px;
  border-bottom: 1px solid var(--mmc-line); margin-bottom: 8px;
}
.mmc-refsheet-handle { color: var(--tag, var(--mmc-accent)); font-weight: 500; font-size: calc(13px * var(--mmc-type)); }
/* The filename is provenance, not the title: it is often a long generated name,
   so it takes what room is left and gives up the middle rather than wrapping
   the card to three lines. */
.mmc-refsheet-file {
  color: var(--mmc-off); font-size: calc(11px * var(--mmc-type)); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left;
}
.mmc-refsheet-row {
  display: flex; align-items: center; gap: 10px; padding: 4px 2px;
}
.mmc-refsheet-name {
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); flex: none; width: 56px;
  /* Helped, not decorated: every one of these rows carries a paragraph of
     explanation on the label, and a dotted underline is how the rest of this
     pack says a word has more behind it. */
  cursor: help;
}
/* What this card does with the clip's length — a sentence rather than a
   choice, so it takes the width the options would have and reads as prose. */
.mmc-refsheet-len { align-items: flex-start; }
.mmc-refsheet-note {
  flex: 1; color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); line-height: 1.45;
}
.mmc-refsheet-opts { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; }
.mmc-refsheet-opt {
  padding: 4px 9px; background: var(--mmc-surface-2); border: 1px solid transparent;
  border-radius: 8px; color: var(--mmc-dim); font: inherit; font-size: calc(11.5px * var(--mmc-type));
  cursor: pointer; line-height: 1.3;
}
.mmc-refsheet-opt:hover { background: var(--mmc-surface-3); color: var(--mmc-text); }
.mmc-refsheet-opt[aria-checked="true"] {
  background: var(--mmc-surface-3); border-color: var(--mmc-blue); color: var(--mmc-text);
}
.mmc-refsheet-opt:focus-visible { outline: none; border-color: var(--mmc-blue); }
/* An answer this file cannot give. Drawn rather than dropped — a row missing
   its third option says the question has two answers — and still pressable,
   because the press is what says why: the reason goes to the body's notice,
   where a disabled button's tooltip would never have been read. */
.mmc-refsheet-opt.off { background: none; color: var(--mmc-faint); cursor: help; }
.mmc-refsheet-opt.off:hover { background: none; color: var(--mmc-off); }
/* The three that open something else, ruled off from the answers above them:
   everything over the line changes this reference, everything under it leaves
   the card. */
.mmc-refsheet-foot {
  display: flex; flex-wrap: wrap; gap: 6px; padding-top: 10px; margin-top: 6px;
  border-top: 1px solid var(--mmc-line);
}
.mmc-refsheet-go {
  padding: 5px 10px; background: none; border: 1px solid var(--mmc-line);
  border-radius: 9px; color: var(--mmc-dim); font: inherit; font-size: calc(11.5px * var(--mmc-type)); cursor: pointer;
}
.mmc-refsheet-go:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-refsheet-go.danger { margin-left: auto; }
.mmc-refsheet-go.danger:hover { color: var(--mmc-warn); border-color: var(--mmc-warn); background: none; }


/* --- a plate's panels, on its card ----------------------------------------
   What a sheet is made of, one row per cell. The chip is editable here because
   it is prose; the scissors are a mark and not a control, because the sheet on
   disk is the cut-out version — see editor.panelRows. */
.mmc-pl-rows { display: flex; flex-direction: column; gap: 6px; }
.mmc-pl-row { display: flex; align-items: center; gap: 8px; }
.mmc-pl-row .mmc-refsheet-opts { margin-left: auto; }
.mmc-pl-row .mmc-pl-no {
  position: static; flex: none; min-width: 14px; padding: 0; background: none;
  color: var(--mmc-faint);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums; font-size: calc(10.5px * var(--mmc-type));
}
.mmc-pl-row .mmc-pl-thumb {
  flex: none; width: 26px; height: 26px; border-radius: 5px; object-fit: cover;
  border: 1px solid var(--mmc-line-2);
}
.mmc-pl-handle {
  font-size: calc(11px * var(--mmc-type)); white-space: nowrap;
}
.mmc-pl-row .mmc-pl-cut {
  position: static; flex: none; width: 18px; height: 18px; background: none;
  color: var(--mmc-off); cursor: default;
}
.mmc-pl-row .mmc-pl-cut.on { background: none; color: var(--mmc-blue); }

`;
