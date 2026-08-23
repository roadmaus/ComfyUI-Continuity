// Lightbox, LoRA detail sheet, segment editor.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- lightbox ------------------------------------------------------------- */
/* Double-click on any picker cell. Above the picker, like the segment editor. */
.mmc-light {
  display: flex; flex-direction: column; gap: 10px; align-items: center;
  max-width: 100%; max-height: 100%; min-height: 0;
}
.mmc-light-media {
  max-width: min(1400px, 100%); max-height: calc(100vh - 140px);
  min-height: 0; border-radius: 12px; background: var(--mmc-media-bg); object-fit: contain;
  box-shadow: 0 30px 80px var(--mmc-shadow);
}
.mmc-light-audio { width: min(520px, 90vw); }
.mmc-light-name { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }

/* --- LoRA detail sheet ---------------------------------------------------- */
/* Double-click on a manager card. Two shapes on purpose: with a sidecar the
   sheet is showcase-first (media pane + info column); without one there is
   nothing to show, only things to say, so it collapses to a single spec
   column. The layout itself tells you which kind of file you opened. */
.mmc-sheet {
  position: relative; display: flex; overflow: hidden;
  background: var(--mmc-float); border: 1px solid var(--mmc-line); border-radius: 22px;
  width: min(1040px, 100%); height: min(680px, 100%);
  box-shadow: 0 30px 80px var(--mmc-shadow); color: var(--mmc-text);
}
.mmc-sheet.bare { width: min(560px, 100%); height: auto; max-height: min(680px, 100%); }
.mmc-sheet-close { position: absolute; top: 14px; right: 14px; z-index: 2; }

/* left: the showcase */
.mmc-sheet-stage {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  background: var(--mmc-bg); border-right: 1px solid var(--mmc-line);
}
.mmc-sheet-media { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; }
.mmc-sheet-media img, .mmc-sheet-media video {
  max-width: 100%; max-height: 100%; object-fit: contain; display: block;
}
.mmc-sheet-strip {
  display: flex; gap: 8px; padding: 10px 14px 0; overflow-x: auto; flex: none;
}
.mmc-sheet-thumb {
  flex: none; width: 56px; height: 56px; padding: 0; border-radius: 8px; overflow: hidden;
  background: var(--mmc-surface); border: 2px solid transparent; cursor: pointer;
}
.mmc-sheet-thumb[aria-selected="true"] { border-color: var(--mmc-strong); }
.mmc-sheet-thumb img, .mmc-sheet-thumb video {
  width: 100%; height: 100%; object-fit: cover; display: block;
}
/* the recipe strip: how the shown image was actually generated */
.mmc-sheet-recipe { flex: none; padding: 0 14px; }
.mmc-sheet-recipe.on { padding: 10px 14px 12px; display: flex; flex-direction: column; gap: 7px; }
.mmc-sheet-recipe-facts {
  display: flex; gap: 14px; flex-wrap: wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11px * var(--mmc-type));
}
.mmc-sheet-recipe-k { color: var(--mmc-off); }
.mmc-sheet-recipe-v { color: var(--mmc-text); }
.mmc-sheet-prompt { display: flex; gap: 10px; align-items: flex-start; }
.mmc-sheet-prompt-text {
  flex: 1; min-width: 0; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-dim);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.mmc-sheet-copy {
  flex: none; height: calc(24px * var(--mmc-type)); padding: 0 10px; border-radius: 12px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-sheet-copy:hover { color: var(--mmc-text); background: var(--mmc-surface-3); }
.mmc-sheet-negative {
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-off);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* right: the info column */
.mmc-sheet-info {
  flex: none; width: 340px; min-width: 0; overflow-y: auto;
  padding: 22px 24px 24px; display: flex; flex-direction: column; gap: 14px;
}
.mmc-sheet.bare .mmc-sheet-info { flex: 1; width: auto; }
.mmc-sheet-eyebrow {
  display: flex; align-items: center; gap: 8px;
  font-size: calc(10.5px * var(--mmc-type)); letter-spacing: .08em; text-transform: uppercase;
  color: var(--mmc-dim); padding-right: 40px;
}
.mmc-sheet-nsfw { color: var(--mmc-warn); }
.mmc-sheet-mono-mark { display: inline-flex; color: var(--mmc-accent); }
.mmc-sheet-title { font-size: calc(20px * var(--mmc-type)); font-weight: 600; line-height: 1.25; padding-right: 30px; }
.mmc-sheet-byline { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-sheet-stats { display: flex; gap: 18px; padding: 2px 0; }
.mmc-sheet-stat { display: flex; flex-direction: column; gap: 1px; }
.mmc-sheet-stat-v { font-size: calc(14px * var(--mmc-type)); font-weight: 600; font-variant-numeric: tabular-nums; }
.mmc-sheet-stat-k { font-size: calc(10px * var(--mmc-type)); color: var(--mmc-off); }
.mmc-sheet-section { display: flex; flex-direction: column; gap: 6px; }
.mmc-sheet-label {
  font-size: calc(10.5px * var(--mmc-type)); letter-spacing: .08em; text-transform: uppercase; color: var(--mmc-off);
}
.mmc-sheet-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.mmc-sheet-chip {
  display: inline-flex; align-items: baseline; gap: 5px;
  padding: 3px 9px; border-radius: 11px; font-size: calc(11.5px * var(--mmc-type));
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line); color: var(--mmc-text);
}
.mmc-sheet-chip.accent { border-color: color-mix(in srgb, var(--mmc-accent) 40%, transparent); color: var(--mmc-accent); }
.mmc-sheet-chip-n { font-size: calc(9.5px * var(--mmc-type)); color: var(--mmc-off); font-variant-numeric: tabular-nums; }
.mmc-sheet-desc { font-size: calc(12.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-dim); }
.mmc-sheet-desc p { margin: 0 0 8px; }
.mmc-sheet-desc ul, .mmc-sheet-desc ol { margin: 0 0 8px; padding-left: 18px; }
.mmc-sheet-desc code, .mmc-sheet-desc pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11px * var(--mmc-type));
  background: var(--mmc-surface-2); border-radius: 4px; padding: 1px 4px;
}
.mmc-sheet-desc pre { padding: 8px 10px; overflow-x: auto; }
.mmc-sheet-desc blockquote {
  margin: 0 0 8px; padding-left: 10px; border-left: 2px solid var(--mmc-line);
}
.mmc-sheet-desc a { color: var(--mmc-blue); text-decoration: none; }
.mmc-sheet-desc a:hover { text-decoration: underline; }
.mmc-sheet-h { margin: 0 0 6px; font-weight: 600; color: var(--mmc-text); }
.mmc-sheet-versions { display: flex; flex-direction: column; }
.mmc-sheet-version {
  display: flex; align-items: baseline; gap: 8px; padding: 5px 0;
  border-bottom: 1px solid var(--mmc-line); font-size: calc(12px * var(--mmc-type));
}
.mmc-sheet-version:last-child { border-bottom: 0; }
.mmc-sheet-version-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-sheet-version[aria-current="true"] .mmc-sheet-version-name { color: var(--mmc-accent); }
.mmc-sheet-version-sub { margin-left: auto; flex: none; font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-off); }
.mmc-sheet-installed { flex: none; font-size: calc(10px * var(--mmc-type)); color: var(--mmc-accent); }
.mmc-sheet-license, .mmc-sheet-tags, .mmc-sheet-hint { font-size: calc(11.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-dim); }
.mmc-sheet-file { display: flex; flex-direction: column; gap: 3px; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-sheet-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left;
}
.mmc-sheet-hash, .mmc-sheet-file-facts { font-variant-numeric: tabular-nums; }
.mmc-sheet-link { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-blue); text-decoration: none; }
.mmc-sheet-link:hover { text-decoration: underline; }

/* the bare sheet's spec grid and raw-header disclosure */
.mmc-sheet-spec { display: flex; flex-direction: column; }
.mmc-sheet-spec-row {
  display: flex; gap: 14px; padding: 5px 0; font-size: calc(12px * var(--mmc-type));
  border-bottom: 1px solid var(--mmc-line);
}
.mmc-sheet-spec-row:last-child { border-bottom: 0; }
.mmc-sheet-spec-k { flex: none; width: 110px; color: var(--mmc-dim); }
.mmc-sheet-spec-v {
  min-width: 0; overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11.5px * var(--mmc-type));
}
.mmc-sheet-raw { font-size: calc(11px * var(--mmc-type)); }
.mmc-sheet-raw summary { cursor: pointer; color: var(--mmc-off); }
.mmc-sheet-raw summary:hover { color: var(--mmc-dim); }
.mmc-sheet-raw-rows { display: flex; flex-direction: column; gap: 4px; padding-top: 8px; }
.mmc-sheet-raw-row {
  display: flex; gap: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(10.5px * var(--mmc-type));
}
.mmc-sheet-raw-k { flex: none; width: 170px; color: var(--mmc-off); overflow-wrap: anywhere; }
.mmc-sheet-raw-v { min-width: 0; color: var(--mmc-dim); overflow-wrap: anywhere; }

/* --- segment editor ------------------------------------------------------- */
/* Above the picker: it opens on top of it. */
.mmc-trim {
  background: var(--mmc-float); border: 1px solid var(--mmc-line); border-radius: 20px;
  width: min(640px, 100%); padding: 16px 18px 14px;
  display: flex; flex-direction: column; gap: 12px;
  box-shadow: 0 30px 80px var(--mmc-shadow);
}
.mmc-trim-head-row { display: flex; align-items: center; gap: 12px; }
.mmc-trim-name {
  font-size: calc(13px * var(--mmc-type)); color: var(--mmc-dim); min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-trim-media {
  width: 100%; height: auto; max-height: 46vh; border-radius: 12px; background: var(--mmc-media-bg); display: block;
  /* The stage is a canvas sized to the clip. Height follows the aspect on its
     own until max-height clamps it; past that only object-fit keeps the picture
     from being squashed into the box. */
  object-fit: contain;
}
.mmc-trim-bar { display: flex; align-items: center; gap: 12px; }
.mmc-trim-play {
  width: 34px; height: 34px; flex: none; border-radius: 50%;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.mmc-trim-play svg { width: 16px; height: 16px; stroke: currentColor; fill: none;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.mmc-trim-track {
  position: relative; flex: 1; height: 30px; border-radius: 8px;
  background: var(--mmc-surface-2); cursor: pointer; touch-action: none;
}
/* Audio files: no picture, so the waveform is the preview. */
.mmc-trim-track-tall { height: 120px; border-radius: 12px; }
.mmc-trim-wave {
  position: absolute; inset: 0; width: 100%; height: 100%;
  display: block; pointer-events: none;
}
.mmc-trim-sel { position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--mmc-blue) 28%, transparent);
  border-top: 1px solid var(--mmc-blue); border-bottom: 1px solid var(--mmc-blue);
  cursor: grab; touch-action: none; }
.mmc-trim-sel:active { cursor: grabbing; background: color-mix(in srgb, var(--mmc-blue) 36%, transparent); }
.mmc-trim-sel:focus-visible { outline: 2px solid var(--mmc-strong); outline-offset: -2px; }
/* How far into this clip the shot referencing it actually reads — everything
   past the dashed edge is cut on the way to the model. Under the selection rather
   than over it: the selection is what you drag, this is the mark you drag it
   onto. */
.mmc-trim-card {
  position: absolute; top: 0; bottom: 0; pointer-events: none;
  border-right: 1px dashed var(--mmc-strong);
  background: color-mix(in srgb, var(--mmc-strong) 8%, transparent);
}
.mmc-trim-card span {
  position: absolute; right: 8px; bottom: 4px; color: var(--mmc-dim);
  font-size: calc(10px * var(--mmc-type)); white-space: nowrap;
}
.mmc-trim-head { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px;
  background: var(--mmc-strong); opacity: .8; pointer-events: none; }
.mmc-trim-handle {
  position: absolute; top: -3px; bottom: -3px; width: 12px; margin-left: -6px;
  border-radius: 5px; background: var(--mmc-blue); cursor: ew-resize; touch-action: none;
}
.mmc-trim-handle:focus-visible { outline: 2px solid var(--mmc-strong); outline-offset: 1px; }
.mmc-trim-read { display: flex; flex-wrap: wrap; justify-content: space-between; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-text); }
.mmc-trim-len { color: var(--mmc-dim); }
/* Its own line under the times, so the two of them keep their ends of the row. */
.mmc-trim-note { flex: 1 0 100%; margin-top: 4px; color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); }
/* Wraps rather than squeezing: the track switch is three words wide and the
   modal is only 640 px. */
.mmc-trim-foot { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 14px; }
.mmc-trim-spacer { flex: 1; }
/* The track switch: three mutually exclusive choices, so one bordered group
   rather than three loose pills that would read as independent toggles. */
.mmc-seg {
  display: flex; height: 30px; border-radius: 15px; overflow: hidden;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
}
.mmc-seg-opt {
  padding: 0 12px; cursor: pointer; background: none; border: 0;
  border-left: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); font-family: inherit; white-space: nowrap;
}
.mmc-seg-opt:first-child { border-left: 0; }
.mmc-seg-opt:hover:not(:disabled) { color: var(--mmc-text); }
.mmc-seg-opt[aria-pressed="true"] { background: color-mix(in srgb, var(--mmc-blue) 22%, transparent); color: var(--mmc-text); }
.mmc-seg-opt:disabled { color: var(--mmc-off); cursor: not-allowed; }
.mmc-ghost:disabled { color: var(--mmc-off); cursor: not-allowed; }

.mmc-cell-name {
  position: absolute; left: 0; right: 0; bottom: 0; padding: 14px 8px 6px;
  font-size: calc(10px * var(--mmc-type)); color: var(--mmc-text); text-align: left;
  background: linear-gradient(transparent, var(--mmc-scrim-3));
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mmc-empty { grid-column: 1/-1; color: var(--mmc-dim); font-size: calc(14px * var(--mmc-type)); padding: 40px 0; text-align: center; }
.mmc-modal-foot {
  position: absolute; bottom: 34px; right: 44px;
  display: flex; align-items: center; gap: 16px; padding: 10px 12px 10px 20px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 14px;
  box-shadow: 0 12px 32px var(--mmc-shadow-soft); font-size: calc(14px * var(--mmc-type));
}
.mmc-slots { color: var(--mmc-text); }
.mmc-slots.full { color: var(--mmc-warn); }
.mmc-ghost { background: none; border: 0; color: var(--mmc-dim); font-size: calc(14px * var(--mmc-type));
  font-family: inherit; cursor: pointer; }
.mmc-ghost:hover { color: var(--mmc-text); }
.mmc-add {
  height: calc(36px * var(--mmc-type)); padding: 0 20px; border-radius: 10px; background: var(--mmc-blue);
  border: 0; color: var(--mmc-strong); font-size: calc(14px * var(--mmc-type)); font-weight: 500; font-family: inherit; cursor: pointer;
}
.mmc-add:disabled { opacity: .4; cursor: not-allowed; }

`;
