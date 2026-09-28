export const css = `
.mmc-technique-bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; min-width: 0; padding: 5px 0; }
.mmc-technique-bar[hidden] { display: none; }
.mmc-technique-chip { display: inline-flex; max-width: 100%; border: 1px solid var(--mmc-line); border-radius: 12px; background: var(--mmc-surface); overflow: hidden; }
.mmc-technique-chip button { color: var(--mmc-text); background: transparent; border: 0; padding: 4px 8px; cursor: pointer; font: inherit; }
.mmc-technique-chip button:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-technique-chip button:last-child { flex: 0 0 auto; border-left: 1px solid var(--mmc-line); }
.mmc-technique-chip button:hover { background: var(--mmc-surface-2); }
.mmc-technique-chip button:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-technique-chip.stale { border-style: dashed; opacity: .7; }
.mmc-technique-chip button:disabled { cursor: default; opacity: .45; }
.mmc-technique-note { flex: 1 1 100%; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-warn); white-space: normal; overflow-wrap: anywhere; }
.mmc-technique-note:empty { display: none; }
`;
