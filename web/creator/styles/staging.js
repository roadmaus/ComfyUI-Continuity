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

/* A piece of one shot of its own: no strip, no joins, no next shot. */
.mmc-st-single .mmc-reel-foot, .mmc-st-single .mmc-reel-next, .mmc-st-single .mmc-reel-gap { display: none; }
.mmc-st-back { background: none; border: 0; padding: 0; cursor: pointer; font: inherit; color: inherit; }
.mmc-st-back:hover { color: var(--mmc-accent); }

/* --- the glass ------------------------------------------------------------------ */
/* --- focus: the stage fills the window, the inspector a drawer over it ---------------- */
.mmc-overlay.mmc-st-focusing { padding: 0; }
.mmc-st-bench.mmc-st-focus { width: 100%; height: 100%; border-radius: 0; border: 0; }
.mmc-st-focus .mmc-reel-main { position: relative; grid-template-columns: minmax(0, 1fr); }
.mmc-st-focus .mmc-reel-script, .mmc-st-focus .mmc-reel-lane { display: none; }
.mmc-st-focus .mmc-reel-foot { padding-top: 0; }
.mmc-st-focus .mmc-reel-side { position: absolute; z-index: 6; top: 22px; right: 30px; bottom: 22px; width: min(360px, calc(100% - 60px)); overflow: auto;
  border: 1px solid var(--mmc-line); border-radius: calc(14px * var(--mmc-round)); background: var(--mmc-float); box-shadow: 0 18px 48px var(--mmc-shadow);
  transform: translateX(calc(100% + 40px)); visibility: hidden; transition: transform .18s ease, visibility 0s linear .18s; }
.mmc-st-focus.mmc-st-drawer .mmc-reel-side { transform: none; visibility: visible; transition: transform .18s ease; }
/* The tools over the stage stay clear of the drawer: its width, less the gap between them. */
.mmc-st-focus.mmc-st-drawer .mmc-st .mmc-bo-hud { right: calc(min(360px, 100% - 60px) + 28px); transition: right .18s ease; }
.mmc-st-col { min-height: 0; display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; }
.mmc-st-glass { position: relative; flex: 1; min-height: 220px; border-radius: calc(14px * var(--mmc-round)); overflow: hidden; background: var(--mmc-media-bg, #0e0f11); }
.mmc-st { position: absolute; inset: 0; }
.mmc-st canvas { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; touch-action: none; display: block; }
.mmc-st video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; background: #000; }
.mmc-st .mmc-st-blank { position: absolute; inset: 0; display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center;
  padding: 24px; text-align: center; color: #d6d3cc; font-size: calc(13.5px * var(--mmc-type, 1)); line-height: 1.5; background: rgba(14, 15, 17, .72); }
.mmc-st .mmc-st-blank[hidden] { display: none; }
.mmc-st .mmc-st-blank p { margin: 0; max-width: 44ch; }
.mmc-st-shelf { position: absolute; inset: 48px 12px 52px; z-index: 5; overflow: auto; padding: 14px; border-radius: calc(12px * var(--mmc-round)); background: rgba(20, 21, 24, .95); color: #f0ede7; }
.mmc-st-shelf .mmc-close { position: sticky; float: right; top: 0; }
.mmc-st-shelfname { margin: 10px 0 6px; font-weight: 600; font-size: calc(12.5px * var(--mmc-type, 1)); }
.mmc-st-models { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 8px; }
.mmc-st-model { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px; border: 1px solid transparent; border-radius: calc(10px * var(--mmc-round));
  background: rgba(255, 255, 255, .05); color: inherit; font: inherit; font-size: calc(12px * var(--mmc-type, 1)); cursor: pointer; }
.mmc-st-model:hover, .mmc-st-model:focus-visible { border-color: var(--mmc-accent); }
.mmc-st-model canvas { position: static; width: 100%; height: auto; border-radius: calc(6px * var(--mmc-round)); }
.mmc-st-scenes { grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); }
.mmc-st-shelfnote { margin: 0 0 4px; max-width: 60ch; color: #c9c5bd; font-size: calc(12.5px * var(--mmc-type, 1)); }
.mmc-st-starts { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; max-width: 560px; }
.mmc-st .mmc-bo-hud > * { pointer-events: auto; }
.mmc-st .mmc-bo-hud .mmc-bn-gap { flex: 1; pointer-events: none; }
.mmc-st-said { height: calc(24px * var(--mmc-type, 1)); padding: 0 10px; display: inline-flex; align-items: center; white-space: nowrap;
  font-size: calc(11.5px * var(--mmc-type, 1)); color: #f0ede7; font-variant-numeric: tabular-nums; }
.mmc-st .mmc-bo-seg { display: inline-flex; align-items: center; gap: 5px; }
.mmc-st .mmc-bo-seg:disabled { opacity: .4; cursor: not-allowed; }

/* --- the shot camera's frame in its corner, and what a drag is about to do --------- */
.mmc-st-monitor { position: absolute; z-index: 3; top: 50px; right: 12px; width: min(31%, 320px); border-radius: calc(8px * var(--mmc-round)); overflow: hidden;
  border: 1px solid rgba(255, 255, 255, .22); background: #000; box-shadow: 0 8px 26px rgba(0, 0, 0, .5); }
.mmc-st-monitor.tall { width: min(17%, 170px); }
.mmc-st-monitor[hidden] { display: none; }
.mmc-st .mmc-st-monitor canvas { position: static; width: 100%; height: auto; cursor: pointer; }
.mmc-st-monitorcap { position: absolute; inset: 0 0 auto 0; display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 3px 4px 8px 8px;
  font-size: calc(11px * var(--mmc-type, 1)); color: #f0ede7; font-variant-numeric: tabular-nums; background: linear-gradient(rgba(0, 0, 0, .7), transparent); pointer-events: none; }
.mmc-st-monitorswitch { display: inline-flex; gap: 2px; pointer-events: auto; }
.mmc-st-monitorswitch .mmc-bo-seg { height: calc(20px * var(--mmc-type, 1)); padding: 0 7px; font-size: calc(10.5px * var(--mmc-type, 1)); }
.mmc-st-focus.mmc-st-drawer .mmc-st-monitor { right: calc(min(360px, 100% - 60px) + 28px); transition: right .18s ease; }
.mmc-st-badge { position: absolute; z-index: 3; top: 50px; left: 12px; max-width: calc(64% - 24px); display: flex; align-items: center; gap: 7px; padding: 4px 10px;
  border-radius: calc(8px * var(--mmc-round)); background: rgba(14, 15, 17, .78); border: 1px solid rgba(255, 255, 255, .16); color: #f0ede7; pointer-events: none;
  font-size: calc(11.5px * var(--mmc-type, 1)); line-height: 1.35; font-variant-numeric: tabular-nums; }
.mmc-st-badge[hidden] { display: none; }
.mmc-st-badge i { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--mmc-dim); }
.mmc-st-badge.new i { background: var(--mmc-accent); }
.mmc-st-badge.move i { background: var(--mmc-role-motion, #6ebeff); }
.mmc-st-badge.path i { border-radius: calc(2px * var(--mmc-round)); transform: rotate(45deg); background: var(--mmc-accent); }

/* --- the mark sheet under the glass: a lane for each mover, a diamond for each stop -- */
.mmc-st-sheet { flex: none; display: flex; flex-direction: column; gap: 6px; padding: 8px 0 8px; border-radius: calc(12px * var(--mmc-round)); background: var(--mmc-surface); }
.mmc-st-sheet [hidden] { display: none; }
.mmc-st-sheethead { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 0 10px; }
.mmc-st-sheethead .mmc-bn-gap { flex: 1; }
.mmc-st-sheethead .mmc-st-said { color: var(--mmc-strong); font-size: calc(12.5px * var(--mmc-type, 1)); }
.mmc-st-bench .mmc-st-key { width: calc(30px * var(--mmc-type, 1)); padding: 0; justify-content: center; }
.mmc-st-stepper { display: inline-flex; align-items: center; gap: 2px; }
.mmc-st-shotname { font-size: calc(12px * var(--mmc-type, 1)); color: var(--mmc-dim); font-variant-numeric: tabular-nums; }
.mmc-st-lanes { position: relative; --mmc-st-lab: 104px; --mmc-st-pad: 12px; }
.mmc-st-lane { display: grid; grid-template-columns: var(--mmc-st-lab) minmax(0, 1fr); align-items: center; }
.mmc-st-lane.held { background: var(--mmc-wash); }
.mmc-st-lanename { display: flex; align-items: center; gap: 7px; min-width: 0; height: 26px; padding: 0 6px 0 12px; border: 0; background: none; cursor: pointer; text-align: left;
  font: inherit; font-size: calc(12px * var(--mmc-type, 1)); color: var(--mmc-dim); }
.mmc-st-lanename span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-st-lane.held .mmc-st-lanename { color: var(--mmc-strong); font-weight: 600; }
.mmc-st-lanename:focus-visible, .mmc-st-stop:focus-visible, .mmc-st-clause:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-st-track { position: relative; height: 26px; margin: 0 var(--mmc-st-pad); cursor: ew-resize; touch-action: none; }
.mmc-st-track::before { content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: var(--mmc-line-2); }
.mmc-st-ruler { height: 18px; }
.mmc-st-ruler::before { display: none; }
.mmc-st-tick { position: absolute; top: 2px; bottom: 0; padding-left: 4px; border-left: 1px solid var(--mmc-line-2); pointer-events: none; white-space: nowrap;
  font-size: calc(10.5px * var(--mmc-type, 1)); color: var(--mmc-off); font-variant-numeric: tabular-nums; }
.mmc-st-tick.end { transform: translateX(-100%); padding: 0 4px 0 0; border-left: 0; border-right: 1px solid var(--mmc-line-2); }
.mmc-st-leg { position: absolute; top: 50%; height: 4px; margin-top: -2px; border-radius: calc(2px * var(--mmc-round)); pointer-events: none; background: color-mix(in srgb, var(--hue) 55%, transparent); }
.mmc-st-leg.still { background: repeating-linear-gradient(90deg, color-mix(in srgb, var(--hue) 45%, transparent) 0 4px, transparent 4px 8px); }
.mmc-st-stop { position: absolute; top: 50%; width: 13px; height: 13px; margin: -6.5px 0 0 -6.5px; padding: 0; transform: rotate(45deg); border-radius: calc(2px * var(--mmc-round));
  background: var(--mmc-surface); border: 2px solid var(--hue); cursor: grab; touch-action: none; }
.mmc-st-stop::after { content: ""; position: absolute; inset: -8px; }
.mmc-st-stop.here { background: var(--hue); }
.mmc-st-stop.rest { border-style: dotted; cursor: default; pointer-events: none; opacity: .7; }
.mmc-st-stop:active { cursor: grabbing; }
.mmc-st-playwrap { position: absolute; top: 0; bottom: 0; left: calc(var(--mmc-st-lab) + var(--mmc-st-pad)); right: var(--mmc-st-pad); pointer-events: none; }
.mmc-st-playhead { position: absolute; top: 0; bottom: 0; width: 0; border-left: 1.5px solid var(--mmc-accent); }
.mmc-st-playhead::before { content: ""; position: absolute; top: 0; left: -5.5px; border: 5px solid transparent; border-top: 7px solid var(--mmc-accent); }
.mmc-st-pacehost { padding: 6px 12px 0; border-top: 1px solid var(--mmc-line); }
.mmc-st-sheethead .mmc-reel-btn[aria-pressed="true"] { color: var(--mmc-strong); background: var(--mmc-wash-2); }

/* --- what the model is given, under the inspector ----------------------------------- */
.mmc-st-gets { flex: none; max-height: 50%; overflow: auto; display: flex; flex-direction: column; gap: 10px; padding: 14px 20px 18px;
  border-top: 1px solid var(--mmc-line); background: color-mix(in oklab, var(--mmc-bg) 94%, var(--mmc-media-bg)); }
.mmc-st-gets[hidden] { display: none; }
.mmc-st-gets > * { flex: none; }
.mmc-st-bench .mmc-reel-inspect { min-height: 38%; }
.mmc-st-getshead { display: flex; align-items: baseline; gap: 8px; }
.mmc-st-getshead b { font-size: calc(14px * var(--mmc-type, 1)); color: var(--mmc-strong); }
.mmc-st-getshead span { flex: 1; font-size: calc(12.5px * var(--mmc-type, 1)); color: var(--mmc-dim); }
.mmc-st-frames { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.mmc-st-frames figure { margin: 0; min-width: 0; }
.mmc-st-frames canvas { display: block; width: 100%; height: auto; border-radius: calc(6px * var(--mmc-round)); border: 1px solid var(--mmc-line); }
.mmc-st-frames figcaption { margin-top: 3px; font-size: calc(11px * var(--mmc-type, 1)); color: var(--mmc-off); }
.mmc-st-file { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: calc(11px * var(--mmc-type, 1)); color: var(--mmc-dim); overflow-wrap: anywhere; }
.mmc-st-given { display: flex; flex-direction: column; gap: 7px; padding: 10px 12px; border-radius: calc(10px * var(--mmc-round)); border: 1px solid var(--mmc-line); background: var(--mmc-surface);
  font-size: calc(13px * var(--mmc-type, 1)); line-height: 1.55; color: var(--mmc-text); }
.mmc-st-prose { white-space: pre-wrap; }
.mmc-st-prose.none { color: var(--mmc-off); }
.mmc-st-cite { color: var(--mmc-role-motion, #6ebeff); }
.mmc-st-clause { border-radius: calc(4px * var(--mmc-round)); cursor: pointer; border-bottom: 1px dotted var(--mmc-line-3); }
.mmc-st-clause:hover { background: color-mix(in srgb, var(--tag, var(--mmc-role-motion, #6ebeff)) 28%, transparent); }
.mmc-st-clause.changed { animation: mmc-st-flash 1.8s ease-out; }
@keyframes mmc-st-flash { from { background: color-mix(in srgb, var(--mmc-accent) 60%, transparent); } to { background: transparent; } }
@media (prefers-reduced-motion: reduce) { .mmc-st-clause.changed { animation: none; } }

/* --- the speed lane under the glass ----------------------------------------------- */
.mmc-st-pace { position: relative; flex: none; display: flex; flex-direction: column; gap: 6px; }
.mmc-st-pace[hidden], .mmc-st-pace [hidden] { display: none; }
.mmc-st-pacehead { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-height: 30px; }
.mmc-st-pacename { font-weight: 600; font-size: calc(12.5px * var(--mmc-type, 1)); }
.mmc-st-pacenow { position: absolute; right: 22px; bottom: 44px; pointer-events: none; font-size: calc(12px * var(--mmc-type, 1)); font-variant-numeric: tabular-nums; color: var(--mmc-dim); }
.mmc-st-pace canvas { width: 100%; height: 64px; display: block; border-radius: calc(10px * var(--mmc-round)); cursor: pointer; touch-action: none;
  color: var(--mmc-text); background: var(--mmc-surface-2); }

/* --- the strip: the sets over the film, a shot's guide on its card, the playhead -- */
.mmc-st-bench .mmc-reel-pass { cursor: pointer; background: none; font: inherit; font-size: calc(10.5px * var(--mmc-type, 1)); text-align: left; line-height: 15px; }
.mmc-st-bench .mmc-reel-pass.selected { color: var(--mmc-accent); border-color: var(--mmc-accent); }
.mmc-st-bench .mmc-reel-card canvas.mmc-st-thumb { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: inherit; opacity: .5; pointer-events: none; }
.mmc-st-bench .mmc-reel-card-tag.mmc-st-quiet { background: rgba(0, 0, 0, .58); color: #fff; font-weight: 500; }
.mmc-st-bench .mmc-reel-join.mmc-st-jump { border-color: var(--mmc-accent); color: var(--mmc-accent); }
.mmc-st-head { position: absolute; top: -3px; height: 90px; width: 2px; margin-left: -1px; background: var(--mmc-accent); z-index: 6; pointer-events: none; }
.mmc-st-head::before { content: ""; position: absolute; top: -4px; left: -4px; width: 10px; height: 10px; border-radius: 50%; background: var(--mmc-accent); }

/* --- the script's sets, and the inspector's own rows ------------------------------- */
.mmc-st-bench .mmc-reel-face canvas { width: 38px; height: 26px; border-radius: calc(6px * var(--mmc-round)); display: block; }
.mmc-st-hue { width: 10px; height: 10px; border-radius: 50%; display: inline-block; background: var(--tag, var(--mmc-surface-3)); flex: none; }
.mmc-st-name { width: 100%; max-width: 240px; }
.mmc-st-bench .mmc-reel-icontrol .mmc-bo-vec { width: 100%; max-width: 300px; min-width: 0; }
.mmc-st-bench .mmc-reel-icontrol .mmc-bo-vecslot { flex: 1 1 0; min-width: 0; padding: 0 5px; gap: 4px; }
.mmc-st-warn { color: var(--mmc-accent); font-size: calc(13px * var(--mmc-type, 1)); line-height: 1.45; }
.mmc-st-range { width: 100%; max-width: 240px; accent-color: var(--mmc-accent); }
.mmc-st-bench .mmc-st-scale { width: 84px; }
.mmc-st-chips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.mmc-st-chips .mmc-reel-btn { padding-inline: 10px; }

@media (max-width: 900px) {
  .mmc-st-bench .mmc-reel-main { display: flex; flex-direction: column; }
  .mmc-st-col { order: -1; }
  .mmc-st-glass { min-height: 0; aspect-ratio: 16 / 9; flex: none; }
}

/* --- an agent at work: said on the glass, on its button, and on what it touched ------- */
/* Stagehand's window is laid over the inspector; in focus the drawer is already positioned. */
.mmc-st-bench:not(.mmc-st-focus) .mmc-reel-side { position: relative; }
.mmc-st-handbtn { display: inline-flex; align-items: center; gap: 8px; }
.mmc-st-handbtn[aria-pressed="true"] { background: var(--mmc-wash); color: var(--mmc-strong); }
.mmc-st-handdot, .mmc-st-agentpill i { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--mmc-accent); animation: mmc-st-agent 1.1s ease-in-out infinite; }
.mmc-st-handdot[hidden], .mmc-st-agentpill[hidden] { display: none; }
.mmc-st-agentpill { position: absolute; z-index: 4; left: 12px; bottom: 54px; max-width: calc(100% - 24px); display: flex; align-items: center; gap: 8px; padding: 5px 11px;
  border-radius: calc(9px * var(--mmc-round)); background: color-mix(in srgb, var(--mmc-ground) 90%, transparent); border: 1px solid color-mix(in srgb, var(--mmc-accent) 45%, transparent);
  color: var(--mmc-accent); font-size: calc(12px * var(--mmc-type)); font-weight: 500; pointer-events: none; }
.mmc-st-lit { animation: mmc-st-lit 1.6s ease-out; border-radius: calc(6px * var(--mmc-round)); }
@keyframes mmc-st-agent { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }
@keyframes mmc-st-lit { 0%, 35% { background-color: color-mix(in srgb, var(--mmc-accent) 26%, transparent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--mmc-accent) 26%, transparent); }
  100% { background-color: transparent; box-shadow: 0 0 0 3px transparent; } }
/* What writes waits while it works; what looks does not. */
.mmc-reel.mmc-agent-working [inert] { opacity: .6; }
.mmc-st-bench.mmc-agent-working .mmc-reel-edge { pointer-events: none; }
@media (prefers-reduced-motion: reduce) { .mmc-st-handdot, .mmc-st-agentpill i, .mmc-st-lit { animation: none; } }
`;
