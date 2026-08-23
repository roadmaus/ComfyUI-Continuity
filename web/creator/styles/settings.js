// The settings page.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- settings page -------------------------------------------------------- */
/* A sibling of the LoRA manager rather than a new species: same overlay, same
   head, same Done. Narrower, and only as tall as what is in it — the picker's
   1100×760 shell around one control reads as a page left half-built. */
.mmc-settings { width: min(600px, 100%); height: auto; max-height: min(760px, 100%); }
.mmc-set-body { overflow-y: auto; min-height: 0; padding: 4px 24px 8px; }
/* Static, unlike the picker's, which floats over a scrolling grid. There is no
   grid here to hover above and nothing for it to clear. */
.mmc-settings .mmc-modal-foot {
  position: static; justify-content: flex-end; background: none; border: 0;
  box-shadow: none; padding: 8px 24px 20px;
}
.mmc-set-section { padding: 16px 0 4px; display: flex; flex-direction: column; gap: 4px; }
.mmc-set-title { font-size: calc(15px * var(--mmc-type)); }
/* Measured, not full-bleed: a 600px line of 12px text is a paragraph nobody
   finishes. Wide enough to reach the choice box below it, though — a
   description visibly narrower than the control it describes reads as a
   column that lost its other half. */
.mmc-set-desc { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); line-height: 1.5; max-width: 62ch; }
.mmc-set-choices {
  margin-top: 10px; background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 14px; padding: 4px;
}
/* Three columns: the radio, the words, and the value the encoder is actually
   given. Fixed on the right so the numbers stack under each other — they are a
   scale, and a scale you have to read across for is not one. */
.mmc-set-opt {
  display: grid; grid-template-columns: 18px 1fr auto; gap: 12px;
  align-items: start; padding: 11px 12px; border-radius: 11px;
}
.mmc-set-opt .mmc-radio { margin-top: 1px; }
.mmc-set-opt-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.mmc-set-opt-label { font-size: calc(14px * var(--mmc-type)); }
.mmc-set-opt-note { color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; }
.mmc-set-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11.5px * var(--mmc-type));
  color: var(--mmc-dim); font-variant-numeric: tabular-nums; padding-top: 2px;
}
/* The value in force reads as text, the rest as labels. This column is the one
   thing on the page you might want to read across before choosing, so none of
   it is allowed to be decoration. */
.mmc-set-opt[aria-checked="true"] .mmc-set-value { color: var(--mmc-text); }
/* A typed setting, in the box the chosen settings use. Same border, radius and
   inset as .mmc-set-choices above — one is a list of answers and the other is a
   field, and on this page they are the same kind of thing. */
.mmc-set-field {
  margin-top: 10px; background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 14px; padding: 12px;
}
/* A destination: name and note on one line, the field, the reading under it.
   Two of these share the card, split by a hairline — they are one setting
   asked twice, and the quality list above answers the same way. */
.mmc-set-dest { display: flex; flex-direction: column; gap: 8px; padding: 6px 4px; }
.mmc-set-dest + .mmc-set-dest {
  border-top: 1px solid var(--mmc-line); margin-top: 10px; padding-top: 16px;
}
.mmc-set-dest-head { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.mmc-set-dest-name { font-size: calc(14px * var(--mmc-type)); }
.mmc-set-dest-sub {
  color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type));
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-set-dest .mmc-out-example { padding: 0 2px; }
/* The token chips exist while the destination is being edited and not
   otherwise: at rest the tab is two fields and their readings, not sixteen
   buttons. :focus-within keeps them up while a chip itself is the click. */
.mmc-set-dest .mmc-out-tokens { display: none; padding: 2px 0 0; }
.mmc-set-dest:focus-within .mmc-out-tokens { display: flex; }
.mmc-set-foot {
  color: var(--mmc-off); font-size: calc(11px * var(--mmc-type)); line-height: 1.55; padding: 10px 2px 0;
}
.mmc-set-foot code {
  font-family: ui-monospace, Menlo, monospace; font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-dim);
}
/* The reference cache's two limits: how long, and how much. One card split by
   the same hairline the two output folders share — they are one setting asked
   twice, and this page already has a shape for that. */
.mmc-set-bounds { padding: 14px 14px 6px; }
.mmc-set-slider { display: flex; flex-direction: column; gap: 2px; }
.mmc-set-slider + .mmc-set-slider {
  border-top: 1px solid var(--mmc-line); margin-top: 16px; padding-top: 16px;
}
.mmc-set-slider .mmc-slider-read { padding-bottom: 2px; }
/* The consequence of the value, in the dim column the popover sliders use. It
   turns warn when the store is already past where the thumb is standing. */
.mmc-set-slider .mmc-slider-read .over { color: var(--mmc-warn); }
/* Room above the rail for the gauge, and below it for the stop labels. Tight
   above: the gauge is read *against* the thumb, and a gap wide enough to read
   as a separate row is a gap that stops the comparison being made. */
.mmc-set-slider .mmc-slider-track { padding-top: 3px; padding-bottom: calc(16px * var(--mmc-type)); }
.mmc-set-slider input[type="range"] {
  display: block; width: 100%; margin: 0; height: 20px; accent-color: var(--mmc-blue);
}
/* Wider than the popover's, because these stops carry words and not just
   numbers, and a label that wraps is a label that moves the rail. */
.mmc-set-slider .mmc-slider-mark {
  width: calc(48px * var(--mmc-type)); margin-left: calc(-24px * var(--mmc-type)); white-space: nowrap;
}
/* How full the store actually is, against the ceiling being set. A gauge in the
   rail's own stop space, so it can be read straight against the thumb below it:
   longer than the thumb is over the limit. The pack's accent rather than the
   rail's blue — this is a reading, and a second blue would be a second thumb. */
.mmc-set-usage {
  position: absolute; top: 0; left: 8px; right: 8px; height: 3px;
  border-radius: 2px; background: var(--mmc-wash-2); overflow: hidden;
}
.mmc-set-usage > span {
  display: block; height: 100%; width: calc(var(--p) * 100%);
  border-radius: 2px; background: var(--mmc-accent);
}
.mmc-set-usage.over > span { background: var(--mmc-warn); }
/* Off, the retention rail has nothing on disk to age. It stays on the page —
   it is still what would happen once there is — and goes quiet: the value
   included, or a setting with no effect would be the loudest thing in the card. */
.mmc-set-slider input[type="range"]:disabled,
.mmc-set-slider .mmc-slider-mark:disabled { opacity: .4; cursor: default; }
.mmc-set-slider.off .mmc-edge, .mmc-set-slider.off .mmc-edge-unit { color: var(--mmc-off); }

/* The reference cache's foot carries a control as well as a reading — the only
   foot on the page that does, which is why the button is styled here rather
   than by .mmc-set-foot growing a layout every other one would inherit. */
.mmc-set-clear {
  margin-top: 9px; padding: 3px 12px; font-size: calc(11.5px * var(--mmc-type));
}
.mmc-set-wait { color: var(--mmc-dim); font-size: calc(13px * var(--mmc-type)); padding: 28px 0 24px; }
.mmc-set-problem { color: var(--mmc-warn); font-size: calc(12px * var(--mmc-type)); line-height: 1.45; padding: 14px 0 0; }

`;
