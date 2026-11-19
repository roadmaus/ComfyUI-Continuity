// Screens: the chips under the attachments, their popover, and the tracker
// preview on the settings page. See screens.js.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- the row of screens ---------------------------------------------------
   Under the attachments and set like them, because a screen is picked like a
   file and sits on the card like one. What makes it a screen and not a
   reference is the pair inside the chip: the tracker the model is shown, an
   arrow, and what goes on the screen afterwards. */
.mmc-screens { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.mmc-screen-chip {
  display: flex; align-items: center; gap: 6px; padding: 4px 10px 4px 5px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  border-radius: calc(10px * var(--mmc-round)); cursor: pointer; font-family: inherit;
  color: var(--mmc-text); font-size: calc(12px * var(--mmc-type)); text-align: left;
}
.mmc-screen-chip:hover { border-color: var(--mmc-line-3); }
.mmc-screen-chip:focus-visible { outline: 2px solid var(--mmc-blue); outline-offset: 1px; }
.mmc-screen-chip-bad { border-color: var(--mmc-bad); }
/* The tracker is drawn at its screen's own shape, so a phone and a monitor
   read as a phone and a monitor before a word of the label. The hairline is
   what keeps a white tracker from dissolving into a light palette. */
.mmc-screen-tracker {
  display: block; flex: none; border-radius: calc(3px * var(--mmc-round));
  box-shadow: 0 0 0 1px var(--mmc-line-2);
}
.mmc-screen-arrow { color: var(--mmc-faint); font-size: calc(11px * var(--mmc-type)); }
.mmc-screen-thumb {
  width: 26px; height: 26px; flex: none; border-radius: calc(6px * var(--mmc-round)); object-fit: cover;
  background: var(--mmc-surface-3); color: var(--mmc-dim);
  display: flex; align-items: center; justify-content: center;
}
.mmc-screen-name { display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
/* The handle the prompt cites it by, in the hue its chip wears there. */
.mmc-screen-handle { color: var(--tag, var(--mmc-accent)); font-weight: 500; }
.mmc-screen-pop .mmc-screen-head .mmc-pop-title { color: var(--tag, var(--mmc-accent)); font-weight: 500; }
.mmc-screen-file {
  color: var(--mmc-dim); max-width: 150px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* --- the popover ------------------------------------------------------------ */
.mmc-screen-pop { width: 300px; }
.mmc-screen-head { display: flex; align-items: center; justify-content: space-between; }
.mmc-screen-pop .mmc-pop-title { color: var(--mmc-strong); font-weight: 600; }
.mmc-screen-remove {
  display: inline-flex; padding: 6px; margin-right: 4px; border: 0; border-radius: calc(8px * var(--mmc-round));
  background: none; color: var(--mmc-dim); cursor: pointer;
}
.mmc-screen-remove:hover { background: var(--mmc-surface-2); color: var(--mmc-bad); }

/* The pair: what the model is shown beside what the viewer gets. The one
   picture in the popover, so it gets the room — everything under it is a
   control that changes one half of it. */
.mmc-screen-pair {
  display: flex; align-items: center; justify-content: center; gap: 14px;
  padding: 10px 10px 14px; margin: 0 2px 6px;
  background: var(--mmc-surface); border-radius: calc(12px * var(--mmc-round));
}
.mmc-screen-side { margin: 0; display: flex; flex-direction: column; align-items: center; gap: 7px; }
.mmc-screen-side figcaption { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); }
.mmc-screen-frame {
  display: flex; align-items: center; justify-content: center;
  border-radius: calc(5px * var(--mmc-round)); overflow: hidden; box-shadow: 0 0 0 1px var(--mmc-line-2);
}
.mmc-screen-frame .mmc-screen-tracker { border-radius: 0; box-shadow: none; }
/* Black, because that is what the pass letterboxes with: a fit that leaves
   bars shows them here the colour they will be. */
.mmc-screen-frame-content { background: var(--mmc-media-bg); }
.mmc-screen-content { width: 100%; height: 100%; display: block; }

/* The devices, as the aspect popover draws its ratios: the shape is what is
   being chosen, so it is most of the tile. */
.mmc-screen-devices {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; padding: 0 2px 6px;
}
.mmc-screen-device {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 9px 4px 7px; border: 0; border-radius: calc(10px * var(--mmc-round)); background: none; cursor: pointer;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(11.5px * var(--mmc-type));
}
.mmc-screen-device:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-screen-device[aria-checked="true"] {
  background: color-mix(in srgb, var(--mmc-blue) 14%, transparent); color: var(--mmc-text);
  box-shadow: inset 0 0 0 1px var(--mmc-blue);
}
.mmc-screen-glyph { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; }
.mmc-screen-glyph > span {
  box-sizing: border-box; border: 1.5px solid var(--mmc-edge-2); border-radius: calc(2px * var(--mmc-round));
}
.mmc-screen-device[aria-checked="true"] .mmc-screen-glyph > span { border-color: var(--mmc-blue); }

.mmc-screen-pop .mmc-refine-row { gap: 10px; padding-top: 7px; }
.mmc-screen-pop .mmc-refine-row > .mmc-screen-file { flex: 1; text-align: right; }
.mmc-screen-flip { flex: 0 1 auto; min-width: 0; }
/* Three long choices do not fit beside their label; they take the line under
   it instead. */
.mmc-screen-stack { flex-wrap: wrap; }
.mmc-screen-stack .mmc-screen-flip { flex: 1 0 100%; }
.mmc-screen-change {
  flex: none; padding: 4px 10px; border: 1px solid var(--mmc-line-2); border-radius: calc(12px * var(--mmc-round));
  background: none; color: var(--mmc-text); cursor: pointer;
  font-family: inherit; font-size: calc(12px * var(--mmc-type));
}
.mmc-screen-change:hover { background: var(--mmc-surface-2); }
.mmc-screen-ratio {
  width: 56px; padding: 4px 6px; border: 1px solid var(--mmc-line-2); border-radius: calc(8px * var(--mmc-round));
  background: var(--mmc-surface); color: var(--mmc-text);
  font-family: inherit; font-size: calc(12px * var(--mmc-type)); font-variant-numeric: tabular-nums;
}
.mmc-screen-by { color: var(--mmc-faint); }
.mmc-screen-pop .mmc-pop-note { padding: 10px 10px 4px; }

/* --- the settings page -------------------------------------------------------
   The colour buttons wear a swatch and the marker buttons a small tracker in
   the colour in force; the hairline keeps white visible on a light palette. */
.mmc-set-swatch {
  width: 11px; height: 11px; flex: none; border-radius: calc(3px * var(--mmc-round));
  box-shadow: 0 0 0 1px var(--mmc-line-3);
}
/* The specimen: the tracker in force on a phone and a laptop, big enough to
   see the markers on, with what it is for beside them. */
.mmc-set-trackers {
  display: flex; align-items: flex-end; gap: 22px; flex-wrap: wrap;
  padding: 14px 0 16px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-set-tracker { margin: 0; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.mmc-set-tracker .mmc-screen-tracker { border-radius: calc(6px * var(--mmc-round)); }
.mmc-set-tracker figcaption { color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); }
.mmc-set-tracker-note {
  flex: 1 1 180px; margin: 0 0 22px; max-width: 34ch;
  color: var(--mmc-dim); font-size: calc(12.5px * var(--mmc-type)); line-height: 1.5;
}
`;
