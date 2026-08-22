// Popovers: output prefix, chips, short-edge slider.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- popovers ------------------------------------------------------------- */
.mmc-pop {
  position: fixed; z-index: 1300; background: var(--mmc-float); border: 1px solid var(--mmc-line);
  border-radius: 16px; padding: 8px; min-width: 190px;
  box-shadow: 0 18px 48px var(--mmc-shadow);
  /* Never taller than the screen: on a 1080p display the refine popover's
     stacked sections can outgrow the viewport, and placeNear can only clamp
     the top edge. The popover scrolls instead of the bottom clipping off. */
  max-height: calc(100vh - 16px); overflow-y: auto;
}
.mmc-pop-title { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); padding: 6px 10px 8px; }

/* The output-prefix field and its live reading — Settings → Folders is the only
   place these appear now that the per-node popover is gone. */
.mmc-out-field {
  width: 100%; box-sizing: border-box; padding: 8px 10px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 10px; color: var(--mmc-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-out-field:focus { outline: none; border-color: var(--mmc-blue); }
.mmc-out-field.bad { border-color: var(--mmc-warn); }
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
.mmc-out-token {
  padding: 3px 7px; background: var(--mmc-surface-2); border: 0; border-radius: 7px;
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); font-family: ui-monospace, Menlo, monospace;
  cursor: pointer;
}
.mmc-out-token:hover { background: var(--mmc-surface-3); color: var(--mmc-text); }
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

`;
