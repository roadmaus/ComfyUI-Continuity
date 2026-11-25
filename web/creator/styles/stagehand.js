// Stagehand's window in the blockout bench (`stagehandwindow.js`).
//
// A window over the inspector's column, with an edge and a shadow so it reads
// as a window and not as a panel of the bench. Everything is a class of its own
// (`mmc-sh-*`); what the bench itself shows of the agent, the pill on the glass,
// the dot on its button and the light on what a call touched, is `mmc-st-*` and
// lives in the bench's own sheet.

export const css = `
.mmc-sh { position: absolute; z-index: 7; inset: 10px 10px 10px -12px; display: flex; flex-direction: column; overflow: hidden;
  border-radius: 14px; background: var(--mmc-float); border: 1px solid var(--mmc-edge); box-shadow: 0 18px 50px var(--mmc-shadow);
  font-size: calc(13px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-text); }
.mmc-sh[hidden] { display: none; }
.mmc-sh-head { display: flex; flex-direction: column; gap: 7px; padding: 11px 12px 11px 15px; border-bottom: 1px solid var(--mmc-line); }
.mmc-sh-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.mmc-sh-title { flex: 1; font-size: calc(15px * var(--mmc-type)); font-weight: 700; color: var(--mmc-strong); }
.mmc-sh-model { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); }
.mmc-sh-model b { color: var(--mmc-strong); font-weight: 600; }
.mmc-sh-size { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); }
.mmc-sh-btn { flex: none; height: 28px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--mmc-edge); background: none; color: var(--mmc-text);
  font: inherit; font-size: calc(12px * var(--mmc-type)); cursor: pointer; }
.mmc-sh-btn:hover:not(:disabled) { border-color: var(--mmc-dim); color: var(--mmc-strong); }
.mmc-sh-btn:disabled { opacity: .45; cursor: default; }
.mmc-sh-x { width: 28px; padding: 0; border-color: transparent; color: var(--mmc-dim); }

.mmc-sh-log { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 15px; display: flex; flex-direction: column; gap: 10px; }
.mmc-sh-empty, .mmc-sh-quiet { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); }
.mmc-sh-quiet { text-align: center; }
.mmc-sh-user { align-self: flex-end; max-width: 88%; padding: 9px 12px; border-radius: 12px 12px 3px 12px; background: var(--mmc-wash); color: var(--mmc-strong); }
.mmc-sh-words, .mmc-sh-say { white-space: pre-wrap; overflow-wrap: anywhere; }
.mmc-sh-say { align-self: flex-start; max-width: 92%; padding: 9px 12px; border-radius: 12px 12px 12px 3px; background: var(--mmc-surface); color: var(--mmc-strong); }
.mmc-sh-call { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-sh-call summary { display: flex; align-items: baseline; gap: 8px; cursor: pointer; list-style: none; }
.mmc-sh-call summary::-webkit-details-marker { display: none; }
.mmc-sh-call summary i { flex: none; width: 12px; font-style: normal; text-align: center; color: var(--mmc-role-voice); }
.mmc-sh-call.looks summary i { color: var(--mmc-role-motion); }
.mmc-sh-call.refused summary { color: var(--mmc-bad); }
.mmc-sh-call.refused summary i { color: var(--mmc-bad); }
.mmc-sh-call summary:hover span { color: var(--mmc-text); }
.mmc-sh-answer { margin: 6px 0 2px 20px; padding: 7px 9px; border-radius: 8px; background: var(--mmc-tint); border: 1px solid var(--mmc-line); color: var(--mmc-text);
  font: inherit; font-size: calc(11.5px * var(--mmc-type)); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 220px; overflow: auto; }
.mmc-sh-pics { display: flex; flex-wrap: wrap; gap: 6px; }
.mmc-sh-call .mmc-sh-pics { margin: 6px 0 0 20px; }
.mmc-sh-user .mmc-sh-pics { margin-bottom: 8px; }
.mmc-sh-pic { padding: 0; border: 1px solid var(--mmc-edge); border-radius: 8px; overflow: hidden; background: var(--mmc-media-bg); cursor: zoom-in; line-height: 0; }
.mmc-sh-pic img { display: block; width: 176px; max-width: 100%; height: auto; }
.mmc-sh-user .mmc-sh-pic img { width: 72px; height: 52px; object-fit: cover; }
.mmc-sh-error { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 8px 11px; border-radius: 10px; border: 1px solid var(--mmc-bad); color: var(--mmc-bad);
  overflow-wrap: anywhere; }
.mmc-sh-working { display: flex; align-items: center; gap: 8px; color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); }
.mmc-sh-working i { width: 7px; height: 7px; border-radius: 50%; background: var(--mmc-accent); animation: mmc-sh-pulse 1.1s ease-in-out infinite; }
@keyframes mmc-sh-pulse { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }

.mmc-sh-composer { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px 12px; border-top: 1px solid var(--mmc-line); }
.mmc-sh-write { align-items: flex-end; }
.mmc-sh-picture { flex: none; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: 10px;
  border: 1px solid var(--mmc-edge); background: none; color: var(--mmc-text); cursor: pointer; }
.mmc-sh-picture:disabled { opacity: .45; cursor: default; }
.mmc-sh-box { flex: 1; min-width: 0; min-height: 44px; max-height: 160px; box-sizing: border-box; resize: none; padding: 6px 10px; border-radius: 10px;
  border: 1px solid var(--mmc-edge); background: var(--mmc-bg); color: var(--mmc-strong); font: inherit; line-height: 1.35; field-sizing: content; }
.mmc-sh-box:disabled { opacity: .6; }
.mmc-sh-send { flex: none; height: 44px; padding: 0 16px; border-radius: 10px; border: 0; background: var(--mmc-accent); color: var(--mmc-on-accent);
  font: inherit; font-weight: 700; cursor: pointer; }
.mmc-sh-send.stop { background: none; border: 1px solid var(--mmc-dim); color: var(--mmc-strong); font-weight: 600; }
.mmc-sh-send:disabled { opacity: .45; cursor: default; }
.mmc-sh-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.mmc-sh-chips[hidden], .mmc-sh-note[hidden] { display: none; }
.mmc-sh-chip { display: flex; align-items: center; gap: 7px; max-width: 100%; padding: 3px 4px; border-radius: 8px; background: var(--mmc-wash); font-size: calc(12px * var(--mmc-type)); }
.mmc-sh-chip img { width: 34px; height: 24px; border-radius: 4px; object-fit: cover; }
.mmc-sh-chip span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-sh-chip button { flex: none; width: 24px; height: 24px; border: 0; background: none; color: var(--mmc-dim); cursor: pointer; font: inherit; }
.mmc-sh-note { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); }
.mmc-sh-link { margin-left: 6px; padding: 0; border: 0; background: none; color: var(--mmc-accent); font: inherit; cursor: pointer; text-decoration: underline; }
.mmc-sh button:focus-visible, .mmc-sh-box:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-sh-zoom { position: absolute; z-index: 20; inset: 0; display: flex; align-items: center; justify-content: center; padding: 28px; border: 0;
  background: var(--mmc-scrim); backdrop-filter: blur(3px); cursor: zoom-out; }
.mmc-sh-zoom img { max-width: 100%; max-height: 100%; border-radius: 10px; border: 1px solid var(--mmc-edge); box-shadow: 0 18px 50px var(--mmc-shadow); }
@media (prefers-reduced-motion: reduce) { .mmc-sh-working i { animation: none; } }
`;
