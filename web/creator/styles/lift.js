// The image-to-3D tool. Its own room rather than the benches' — see lift.js for
// why a mesh is not a light box — but the same bar, the same tokens, and the
// amber spent in the same three kinds of place: the rays in the scene, the
// progress along the track, and the button that runs the build.
//
// No backticks or ${} anywhere in the CSS: the whole sheet is one template literal.
export const css = `
.mmc-lf {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  color: var(--mmc-text); overflow: hidden;
}
.mmc-lf-room {
  flex: 1; min-height: 0; display: grid;
  grid-template-columns: minmax(0, 1fr) min(calc(312px * var(--mmc-type)), 36vw);
}

/* --- the stage ---------------------------------------------------------- */
.mmc-lf-stage {
  position: relative; min-width: 0; min-height: 0; overflow: hidden;
  background: var(--mmc-media-bg);
}
.mmc-lf-glass { position: absolute; inset: 0; }
.mmc-lf-gl { position: absolute; inset: 0; width: 100%; height: 100%; display: block; cursor: grab; }
.mmc-lf-gl:active { cursor: grabbing; }

/* Before anything has been built: what the stage is for, in the middle of it. */
.mmc-lf-empty {
  position: absolute; left: 50%; top: 44%; transform: translate(-50%, -50%);
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  max-width: 34ch; text-align: center; pointer-events: none;
}
.mmc-lf-empty b { font-size: calc(15px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong); }
.mmc-lf-empty span { font-size: calc(12.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-dim); }

/* The pictures, top left. They are the input, so they stay in view over the
   scene they were lifted into. */
.mmc-lf-holder {
  position: absolute; left: 16px; top: 16px; z-index: 2;
  display: flex; flex-direction: column; gap: 8px; max-width: 300px;
}
.mmc-lf-slots { display: flex; gap: 8px; }
.mmc-lf-slot {
  position: relative; width: calc(64px * var(--mmc-type)); aspect-ratio: 1; padding: 0;
  border-radius: 9px; overflow: hidden; cursor: pointer;
  border: 1px solid var(--mmc-line-2); background: var(--mmc-surface);
  display: flex; flex-direction: column; align-items: center; justify-content: flex-end;
  font-family: inherit; color: var(--mmc-text);
}
.mmc-lf-slot img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.mmc-lf-slot span {
  position: relative; width: 100%; padding: 2px 0 4px; text-align: center;
  font-size: calc(11px * var(--mmc-type)); color: #fff;
  background: linear-gradient(transparent, rgba(0, 0, 0, .62));
}
.mmc-lf-slot:hover { border-color: var(--mmc-line-3); }
.mmc-lf-slot:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-lf-slot.empty {
  border-style: dashed; justify-content: center; gap: 2px;
  background: color-mix(in srgb, var(--mmc-media-bg) 70%, transparent);
}
.mmc-lf-slot.empty b { font-size: calc(18px * var(--mmc-type)); font-weight: 300; color: var(--mmc-off); line-height: 1; }
.mmc-lf-slot.empty span { background: none; color: var(--mmc-dim); padding: 0; }
.mmc-lf-x {
  position: absolute; top: 3px; right: 3px; width: 18px; height: 18px; border-radius: 50%;
  display: grid; place-items: center; font-style: normal; font-size: 10px;
  background: rgba(0, 0, 0, .66); color: #fff; opacity: 0; transition: opacity 120ms ease;
}
.mmc-lf-slot:hover .mmc-lf-x, .mmc-lf-slot:focus-visible .mmc-lf-x { opacity: 1; }
.mmc-lf-holdnote {
  font-size: calc(12px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-dim);
  text-shadow: 0 1px 2px rgba(0, 0, 0, .8);
}
.mmc-lf-holdnote:empty { display: none; }

/* How the mesh is drawn, top right. */
.mmc-lf-views {
  position: absolute; right: 16px; top: 16px; z-index: 2;
  display: flex; flex-direction: column; align-items: flex-end; gap: 8px;
}
.mmc-lf-seg {
  display: inline-flex; gap: 2px; padding: 3px; border-radius: 10px;
  background: color-mix(in srgb, var(--mmc-bg) 84%, transparent);
  border: 1px solid var(--mmc-line); backdrop-filter: blur(8px);
}
.mmc-lf-seg button {
  border: 0; background: none; padding: 5px 10px; border-radius: 7px; cursor: pointer;
  font-family: inherit; font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
  white-space: nowrap;
}
.mmc-lf-seg button:hover:not(:disabled) { color: var(--mmc-text); }
.mmc-lf-seg button[aria-pressed="true"] { background: var(--mmc-surface-3); color: var(--mmc-strong); }
.mmc-lf-seg button:disabled { color: var(--mmc-off); opacity: .55; cursor: default; }
.mmc-lf-seg button:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-lf-chips { display: flex; gap: 6px; }
.mmc-lf-chip {
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  padding: 5px 11px; border-radius: 999px; font-family: inherit;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
  border: 1px solid var(--mmc-line); backdrop-filter: blur(8px);
  background: color-mix(in srgb, var(--mmc-bg) 84%, transparent);
}
.mmc-lf-chip:hover:not(:disabled) { color: var(--mmc-text); border-color: var(--mmc-line-2); }
.mmc-lf-chip[aria-pressed="true"] { color: var(--mmc-strong); border-color: var(--mmc-line-3); }
.mmc-lf-chip:disabled { opacity: .45; cursor: default; }
.mmc-lf-chip:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-lf-chip i { width: 7px; height: 7px; border-radius: 50%; background: var(--mmc-off); }
.mmc-lf-chip[aria-pressed="true"] i { background: var(--mmc-accent); }

/* What is on the stage, said once, above the track. */
.mmc-lf-caption {
  position: absolute; left: 50%; bottom: calc(96px * var(--mmc-type)); z-index: 2;
  transform: translateX(-50%); max-width: calc(100% - 32px);
  display: flex; gap: 8px; align-items: baseline; justify-content: center; flex-wrap: wrap;
  padding: 6px 14px; border-radius: 999px; pointer-events: none;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-text); text-align: center;
  background: color-mix(in srgb, var(--mmc-media-bg) 80%, transparent);
  border: 1px solid var(--mmc-line); backdrop-filter: blur(8px);
}
.mmc-lf-caption small { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-lf-caption[hidden] { display: none; }

.mmc-lf-toast {
  position: absolute; left: 50%; top: 16px; z-index: 4; max-width: calc(100% - 32px);
  transform: translate(-50%, -8px); opacity: 0; pointer-events: none;
  padding: 8px 14px; border-radius: 10px; font-size: calc(12.5px * var(--mmc-type));
  background: var(--mmc-surface-3); border: 1px solid var(--mmc-line-2);
  transition: opacity 160ms ease, transform 160ms ease;
}
.mmc-lf-toast.show { opacity: 1; transform: translate(-50%, 0); }

/* --- the track ------------------------------------------------------------ */
/* The pipeline in the order it runs. A finished stage is pressable and puts
   what it made back on the stage; the fill along each one's bottom edge is the
   real progress of the node running in it. */
.mmc-lf-foot {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 2;
  display: flex; align-items: stretch; gap: 12px; padding: 14px 16px 16px;
  background: linear-gradient(transparent, color-mix(in srgb, var(--mmc-media-bg) 92%, transparent) 34%);
}
.mmc-lf-track { flex: 1; min-width: 0; display: flex; gap: 4px; overflow-x: auto; scrollbar-width: none; }
.mmc-lf-step {
  position: relative; flex: 1 1 0; min-width: calc(88px * var(--mmc-type)); overflow: hidden;
  display: flex; flex-direction: column; gap: 1px; text-align: left; cursor: default;
  padding: 8px 10px 10px; border-radius: 8px; font-family: inherit; color: var(--mmc-text);
  background: color-mix(in srgb, var(--mmc-surface) 92%, transparent); border: 1px solid var(--mmc-line);
}
.mmc-lf-step:first-child { border-radius: 12px 8px 8px 12px; }
.mmc-lf-step:last-child { border-radius: 8px 12px 12px 8px; }
.mmc-lf-steptop { display: flex; align-items: baseline; gap: 6px; }
.mmc-lf-stepn { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); font-variant-numeric: tabular-nums; }
.mmc-lf-stepname { font-size: calc(13px * var(--mmc-type)); font-weight: 600; white-space: nowrap; color: var(--mmc-dim); }
.mmc-lf-steptime {
  min-height: 1.4em; font-size: calc(11.5px * var(--mmc-type)); white-space: nowrap;
  color: var(--mmc-off); font-variant-numeric: tabular-nums;
}
.mmc-lf-fill {
  position: absolute; left: 0; bottom: 0; height: 2px;
  width: calc(var(--p, 0) * 100%); background: var(--mmc-accent);
  transition: width 240ms ease;
}
.mmc-lf-step.done { cursor: pointer; }
.mmc-lf-step.done .mmc-lf-stepname, .mmc-lf-step.run .mmc-lf-stepname { color: var(--mmc-strong); }
.mmc-lf-step.done:hover { background: var(--mmc-surface-2); }
.mmc-lf-step.done .mmc-lf-fill { background: color-mix(in srgb, var(--mmc-accent) 55%, transparent); }
.mmc-lf-step.run .mmc-lf-steptime { color: var(--mmc-accent); }
.mmc-lf-step.fail .mmc-lf-steptime { color: var(--mmc-bad); }
.mmc-lf-step.skip { opacity: .5; }
.mmc-lf-step.skip .mmc-lf-steptime { font-style: italic; }
.mmc-lf-step[aria-current="true"] { border-color: var(--mmc-line-3); background: var(--mmc-surface-2); }
.mmc-lf-step[aria-current="true"] .mmc-lf-fill { background: var(--mmc-accent); }
.mmc-lf-step:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-lf-track.stale .mmc-lf-step.done .mmc-lf-fill { background: var(--mmc-line-3); }

.mmc-lf-go {
  flex: none; width: calc(170px * var(--mmc-type));
  display: flex; flex-direction: column; justify-content: center; gap: 4px;
}
.mmc-lf-run {
  border: 0; border-radius: 12px; padding: 11px 14px; cursor: pointer; font-family: inherit;
  background: var(--mmc-accent); color: var(--mmc-on-accent);
  font-size: calc(13.5px * var(--mmc-type)); font-weight: 650;
}
.mmc-lf-run:hover:not(:disabled) { filter: brightness(1.06); }
.mmc-lf-run:disabled { opacity: .45; cursor: default; }
.mmc-lf-run.quiet, .mmc-lf-run.stop { background: var(--mmc-surface-3); color: var(--mmc-strong); font-weight: 600; }
.mmc-lf-run:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-lf-est {
  min-height: 1.4em; text-align: center; font-size: calc(11.5px * var(--mmc-type));
  line-height: 1.35; color: var(--mmc-dim); font-variant-numeric: tabular-nums;
}
.mmc-lf-est.bad { color: var(--mmc-bad); }

/* --- the drawer ------------------------------------------------------------ */
.mmc-lf-drawer {
  min-height: 0; display: flex; flex-direction: column;
  border-left: 1px solid var(--mmc-line); background: var(--mmc-bg);
}
.mmc-lf-drawer-body {
  flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain;
  padding: 18px 18px 10px; display: flex; flex-direction: column; gap: 18px;
}
.mmc-lf-model {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-radius: 12px; background: var(--mmc-surface); border: 1px solid var(--mmc-line);
}
.mmc-lf-modelname { font-size: calc(13px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong); }
.mmc-lf-modelsub { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-lf-dots { display: flex; gap: 3px; margin-left: auto; }
.mmc-lf-dots i { width: 7px; height: 10px; border-radius: 2px; background: var(--mmc-surface-3); }
.mmc-lf-dots i.on { background: var(--mmc-text); }
.mmc-lf-field { display: flex; flex-direction: column; gap: 7px; }
.mmc-lf-label {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong);
}
.mmc-lf-value { font-weight: 500; color: var(--mmc-text); font-variant-numeric: tabular-nums; }
.mmc-lf-seg.wide { display: flex; width: 100%; background: var(--mmc-surface); backdrop-filter: none; }
.mmc-lf-seg.wide button { flex: 1; }
.mmc-lf-note { margin: 0; font-size: calc(12px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-dim); }
.mmc-lf-field input[type="range"] { width: 100%; margin: 0; accent-color: var(--mmc-accent); }
.mmc-lf-rule { flex: none; height: 1px; background: var(--mmc-line); }

/* The files a build needs and this machine does not have, and where they are. */
.mmc-lf-missing {
  display: flex; flex-direction: column; gap: 6px;
  padding-left: 10px; border-left: 2px solid var(--mmc-warn);
}
.mmc-lf-need { display: flex; gap: 8px; align-items: baseline; justify-content: space-between; }
.mmc-lf-needfile {
  min-width: 0; overflow-wrap: anywhere; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-lf-need a { flex: none; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-accent); }

.mmc-lf-maps { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
.mmc-lf-map {
  display: flex; flex-direction: column; gap: 4px; text-decoration: none;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-lf-map img {
  width: 100%; aspect-ratio: 1; object-fit: cover; display: block;
  border-radius: 6px; border: 1px solid var(--mmc-line);
}
.mmc-lf-map:hover span { color: var(--mmc-text); }

/* Where the file went, and where it can go next. */
.mmc-lf-out {
  flex: none; display: flex; flex-direction: column; gap: 10px;
  padding: 14px 18px 16px; border-top: 1px solid var(--mmc-line);
}
.mmc-lf-file { display: flex; align-items: center; gap: 10px; min-width: 0; }
.mmc-lf-glyph {
  flex: none; width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center;
  background: var(--mmc-surface-2); color: var(--mmc-dim);
  font-size: calc(10.5px * var(--mmc-type)); font-weight: 700; letter-spacing: .02em;
}
.mmc-lf-fileword { min-width: 0; }
.mmc-lf-filename {
  font-size: calc(13px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-lf-filepath { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); overflow-wrap: anywhere; }
.mmc-lf-doors { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.mmc-lf-door {
  display: flex; flex-direction: column; gap: 1px; text-align: left; cursor: pointer;
  padding: 8px 10px; border-radius: 10px; font-family: inherit; color: var(--mmc-text);
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
}
.mmc-lf-door:hover:not(:disabled) { background: var(--mmc-surface-2); border-color: var(--mmc-line-2); }
.mmc-lf-door:disabled { cursor: default; }
.mmc-lf-door:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-lf-door b { font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; }
.mmc-lf-door span { font-size: calc(11.5px * var(--mmc-type)); line-height: 1.35; color: var(--mmc-dim); }
.mmc-lf-out.waiting .mmc-lf-file, .mmc-lf-out.waiting .mmc-lf-doors { opacity: .42; }

/* --- narrow ------------------------------------------------------------------ */
@media (max-width: 860px) {
  .mmc-lf-room { grid-template-columns: 1fr; grid-template-rows: minmax(420px, 1fr) auto; overflow: auto; }
  .mmc-lf-drawer { border-left: 0; border-top: 1px solid var(--mmc-line); }
  .mmc-lf-foot { flex-direction: column; gap: 8px; }
  .mmc-lf-go { width: auto; }
  .mmc-lf-caption { bottom: calc(150px * var(--mmc-type)); }
  .mmc-lf-steptime { display: none; }
  .mmc-lf-views { top: auto; bottom: calc(200px * var(--mmc-type)); right: 12px; }
}
@media (prefers-reduced-motion: reduce) {
  .mmc-lf-fill, .mmc-lf-toast, .mmc-lf-x { transition: none; }
}
`;
