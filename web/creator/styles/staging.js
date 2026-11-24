// What the blockout bench adds to the reel's window: the stage.
//
// The bench is the reel's window with a 3D stage as its main surface: the
// script as a column on the left, the stage in the middle, the inspector on the
// right, and the piece at its length underneath. Everything here is either a
// class of its own (`mmc-st-*`) or a reel class qualified by `.mmc-st-bench`,
// the bench's modal, so nothing in this sheet can change how the timeline's
// window looks. The HUD over the stage is the old bench's (`styles/blockout.js`).

export const css = `
/* --- the window: three columns over the strip ----------------------------------- */
.mmc-st-bench { width: min(1800px, 100%); height: 100%; }
.mmc-st-bench .mmc-reel-main { grid-template-columns: minmax(270px, 0.4fr) minmax(0, 1fr) minmax(340px, 0.46fr); }
/* The script is the reel's own, a size smaller so a shot still reads in a narrow column. */
.mmc-st-bench .mmc-reel-script { --mmc-type: .86; padding: 14px 14px 20px 8px; }
.mmc-st-bench .mmc-reel-row { grid-template-columns: 46px minmax(0, 1fr); }
.mmc-st-bench .mmc-reel-shot .mmc-reel-tag { grid-column: 2; justify-self: start; margin-top: 2px; }
.mmc-st-bench .mmc-reel-castrow { padding-left: 46px; }
.mmc-st-bench .mmc-reel-rule { margin-left: 46px; }
.mmc-st-bench .mmc-reel-player { display: none; }
.mmc-st-bench .mmc-reel-side { border-left: 1px solid var(--mmc-line); }
.mmc-st-cuthint { padding: 6px 0 2px 46px; }

/* --- the glass ------------------------------------------------------------------ */
.mmc-st-col { min-height: 0; display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; }
.mmc-st-glass { position: relative; flex: 1; min-height: 220px; border-radius: 14px; overflow: hidden; background: var(--mmc-media-bg, #0e0f11); }
.mmc-st { position: absolute; inset: 0; }
.mmc-st canvas { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; touch-action: none; display: block; }
.mmc-st video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; background: #000; }
.mmc-st .mmc-st-blank { position: absolute; inset: 0; display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center;
  padding: 24px; text-align: center; color: #d6d3cc; font-size: calc(13.5px * var(--mmc-type, 1)); line-height: 1.5; background: rgba(14, 15, 17, .72); }
.mmc-st .mmc-st-blank[hidden] { display: none; }
.mmc-st .mmc-st-blank p { margin: 0; max-width: 44ch; }
.mmc-st-starts { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; max-width: 560px; }
.mmc-st .mmc-bo-hud > * { pointer-events: auto; }
.mmc-st .mmc-bo-hud .mmc-bn-gap { flex: 1; pointer-events: none; }
.mmc-st-said { height: calc(24px * var(--mmc-type, 1)); padding: 0 10px; display: inline-flex; align-items: center; white-space: nowrap;
  font-size: calc(11.5px * var(--mmc-type, 1)); color: #f0ede7; font-variant-numeric: tabular-nums; }
.mmc-st .mmc-bo-seg { display: inline-flex; align-items: center; gap: 5px; }
.mmc-st .mmc-bo-seg:disabled { opacity: .4; cursor: not-allowed; }

/* --- the strip: the sets over the film, a shot's guide on its card, the playhead -- */
.mmc-st-bench .mmc-reel-pass { cursor: pointer; background: none; font: inherit; font-size: calc(10.5px * var(--mmc-type, 1)); text-align: left; line-height: 15px; }
.mmc-st-bench .mmc-reel-pass.selected { color: var(--mmc-accent); border-color: var(--mmc-accent); }
.mmc-st-bench .mmc-reel-card canvas.mmc-st-thumb { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: inherit; opacity: .5; pointer-events: none; }
.mmc-st-bench .mmc-reel-card-tag.mmc-st-quiet { background: rgba(0, 0, 0, .58); color: #fff; font-weight: 500; }
.mmc-st-bench .mmc-reel-join.mmc-st-jump { border-color: var(--mmc-accent); color: var(--mmc-accent); }
.mmc-st-head { position: absolute; top: -3px; height: 90px; width: 2px; margin-left: -1px; background: var(--mmc-accent); z-index: 6; pointer-events: none; }
.mmc-st-head::before { content: ""; position: absolute; top: -4px; left: -4px; width: 10px; height: 10px; border-radius: 50%; background: var(--mmc-accent); }

/* --- the script's sets, and the inspector's own rows ------------------------------- */
.mmc-st-bench .mmc-reel-face canvas { width: 38px; height: 26px; border-radius: 6px; display: block; }
.mmc-st-hue { width: 10px; height: 10px; border-radius: 50%; display: inline-block; background: var(--tag, var(--mmc-surface-3)); flex: none; }
.mmc-st-name { width: 100%; max-width: 240px; }
.mmc-st-bench .mmc-reel-icontrol .mmc-bo-vec { width: 100%; max-width: 300px; }
.mmc-st-bench .mmc-reel-icontrol .mmc-bo-vecslot { min-width: 82px; }
.mmc-st-warn { color: var(--mmc-accent); font-size: calc(13px * var(--mmc-type, 1)); line-height: 1.45; }
.mmc-st-words { white-space: pre-wrap; }

@media (max-width: 900px) {
  .mmc-st-bench .mmc-reel-main { display: flex; flex-direction: column; }
  .mmc-st-col { order: -1; }
  .mmc-st-glass { min-height: 0; aspect-ratio: 16 / 9; flex: none; }
}
`;
