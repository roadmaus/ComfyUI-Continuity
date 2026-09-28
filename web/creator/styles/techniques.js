// Native Continuity surfaces and type scale; only the category layout differs
// from the existing horizontal shelves so all thirteen groups remain visible.
export const css = `
.mmc-tech-overlay { padding: 24px; }
.mmc-tech-modal { width: min(1420px, 100%); height: min(980px, 100%); }
.mmc-tech-modal button, .mmc-tech-modal input, .mmc-tech-modal select, .mmc-tech-modal textarea {
  font: inherit; color: var(--mmc-text); box-sizing: border-box;
}
.mmc-tech-modal button { cursor: pointer; }
.mmc-tech-modal button:disabled { cursor: default; opacity: .48; }
.mmc-tech-modal button:focus-visible, .mmc-tech-modal a:focus-visible,
.mmc-tech-modal input:focus-visible, .mmc-tech-modal select:focus-visible,
.mmc-tech-modal textarea:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-tech-modal [hidden] { display: none !important; }
.mmc-tech-modal .mmc-modal-head { gap: 14px; flex-shrink: 0; }
.mmc-tech-modal .mmc-modal-head > strong { font-size: calc(18px * var(--mmc-type)); }
.mmc-tech-count { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-tech-search { display: flex; padding: 14px 20px 10px; flex-shrink: 0; }
.mmc-tech-search .mmc-search { min-width: 0; width: 100%; }
.mmc-tech-language { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); line-height: 1.45; }
.mmc-tech-filters { padding: 0 20px 14px; display: flex; flex-direction: column; gap: 9px; flex-shrink: 0; }
.mmc-tech-categories, .mmc-tech-modes { display: flex; flex-wrap: wrap; gap: 7px; }
.mmc-tech-categories button, .mmc-tech-modes button {
  border: 1px solid var(--mmc-line); border-radius: 9px; background: var(--mmc-surface);
  padding: 7px 11px; line-height: 1.3; font-size: calc(12px * var(--mmc-type)); white-space: nowrap;
}
.mmc-tech-categories button[aria-pressed="true"],
.mmc-tech-modes button[aria-pressed="true"] { background: var(--mmc-surface-3); border-color: var(--mmc-accent); color: var(--mmc-strong); }
.mmc-tech-list { flex: 1; min-height: 0; overflow: auto; }
.mmc-tech-grid { min-width: 0; padding: 17px; display: grid; border-top: 1px solid var(--mmc-line);
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); align-content: start; gap: 13px; grid-auto-rows: max-content;
}
.mmc-tech-card-holder { position: relative; min-width: 0; display: flex; }
.mmc-tech-card { background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 13px;
  text-align: left; padding: 0 0 12px; min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 7px; overflow: hidden;
}
.mmc-tech-card:hover, .mmc-tech-card[aria-pressed="true"] { background: var(--mmc-surface-2); border-color: var(--mmc-line-3); }
.mmc-tech-card[aria-pressed="true"] { box-shadow: inset 0 0 0 1px var(--mmc-accent); }
.mmc-tech-card > strong, .mmc-tech-card > span { padding: 0 12px; overflow-wrap: anywhere; }
.mmc-tech-card > strong { font-size: calc(13px * var(--mmc-type)); line-height: 1.35; }
.mmc-tech-card-hero { aspect-ratio: 16 / 9; width: 100%; background: var(--mmc-scrim); position: relative; overflow: hidden; margin-bottom: 3px; }
.mmc-tech-card-hero img, .mmc-tech-card-hero video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.mmc-tech-card-hero > span { display: grid; place-items: center; height: 100%; color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); }
.mmc-tech-description { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.mmc-tech-star { position: absolute; right: 7px; top: 7px; width: 29px; height: 29px; border-radius: 50%;
  border: 1px solid var(--mmc-line-2); background: var(--mmc-scrim-2); color: var(--mmc-strong); font-size: 19px; padding: 0;
}
.mmc-tech-star[aria-pressed="true"] { color: var(--mmc-accent); }
.mmc-tech-muted { color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); line-height: 1.5; }
.mmc-tech-more { grid-column: 1 / -1; background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 10px; padding: 12px; }
.mmc-tech-empty { grid-column: 1 / -1; padding: 28px 15px; color: var(--mmc-dim); line-height: 1.6; }
.mmc-tech-inspector { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.mmc-tech-detail-nav { display: flex; align-items: center; gap: 14px; padding: 10px 20px; border-bottom: 1px solid var(--mmc-line); flex-shrink: 0; }
.mmc-tech-back, .mmc-tech-previous, .mmc-tech-copy, .mmc-tech-detail-bookmark, .mmc-tech-reset-original, .mmc-tech-play { background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 9px; padding: 8px 12px; }
.mmc-tech-reset-original { align-self: flex-start; }
.mmc-tech-previous { flex-shrink: 0; }
.mmc-tech-back { flex-shrink: 0; }
.mmc-tech-detail-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-tech-detail-bookmark { font-size: 20px !important; line-height: 1; flex-shrink: 0; }
.mmc-tech-detail-bookmark[aria-pressed="true"] { color: var(--mmc-accent); }
.mmc-tech-detail-body { flex: 1; overflow: auto; min-height: 0; padding: 20px; }
.mmc-tech-article { max-width: 1100px; margin: 0 auto; font-size: calc(13px * var(--mmc-type)); line-height: 1.65; overflow-wrap: anywhere; }
.mmc-tech-detail-title { display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px; }
.mmc-tech-detail-title h2 { margin: 0; font-size: calc(21px * var(--mmc-type)); line-height: 1.3; }
.mmc-tech-article a { color: var(--mmc-accent); }
.mmc-tech-article p { margin: 10px 0; white-space: pre-line; }
.mmc-tech-source-section { border-top: 1px solid var(--mmc-line); padding-top: 13px; margin-top: 20px; }
.mmc-tech-source-section h3 { font-size: calc(16px * var(--mmc-type)); margin: 0 0 10px; }
.mmc-tech-source-section h4 { font-size: calc(14px * var(--mmc-type)); margin: 16px 0 8px; }
.mmc-tech-source-section ul { padding-left: 22px; }
.mmc-tech-source-section li { margin: 6px 0; white-space: pre-line; }
.mmc-tech-inline-link { display: inline; background: none; border: 0; border-bottom: 1px solid var(--mmc-accent); border-radius: 0; color: var(--mmc-accent) !important; padding: 0; text-align: inherit; line-height: inherit; }
.mmc-tech-inline-related { display: inline-flex; flex-wrap: wrap; gap: 5px 10px; margin-left: 8px; }
.mmc-tech-group-card { display: flex; align-items: center; gap: 20px; padding: 16px; margin: 14px 0; background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 12px; }
.mmc-tech-group-navigable { cursor: pointer; }
.mmc-tech-group-navigable:hover { border-color: var(--mmc-line-3); background: var(--mmc-surface-2); }
.mmc-tech-group-card > .mmc-tech-media { width: 34%; max-width: 360px; flex-shrink: 0; margin: 0; }
.mmc-tech-group-card > .mmc-tech-media img, .mmc-tech-group-card > .mmc-tech-media video { aspect-ratio: 16 / 9; object-fit: cover; }
.mmc-tech-group-card .mmc-tech-caption { display: none; }
.mmc-tech-group-text { flex: 1; min-width: 0; }
.mmc-tech-group-text p { margin: 8px 0 0; }
.mmc-tech-card-link { background: none; border: 0; color: var(--mmc-strong) !important; font-weight: 600 !important; padding: 0; text-align: left; }
.mmc-tech-card-link:hover { color: var(--mmc-accent) !important; }
.mmc-tech-recommended { display: flex; flex-wrap: wrap; gap: 12px 20px; }
.mmc-tech-source-section blockquote { margin: 12px 0; padding: 4px 13px; border-left: 3px solid var(--mmc-line-3); white-space: pre-line; }
.mmc-tech-source-links { display: flex; flex-wrap: wrap; gap: 7px 14px; font-size: calc(12px * var(--mmc-type)); }
.mmc-tech-media { margin: 16px 0; min-width: 0; }
.mmc-tech-media img, .mmc-tech-media video { display: block; width: 100%; max-height: 380px; object-fit: contain; border-radius: 10px; background: var(--mmc-scrim); }
.mmc-tech-media video { aspect-ratio: 16 / 9; }
.mmc-tech-hero img, .mmc-tech-hero video { max-height: min(340px, 35vh); }
.mmc-tech-media figcaption { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); margin-top: 6px; }
.mmc-tech-preview { width: 100%; resize: vertical; background: var(--mmc-surface); border: 1px solid var(--mmc-line-2); border-radius: 9px; padding: 10px; line-height: 1.5; font-size: calc(12px * var(--mmc-type)); min-height: 74px; }
.mmc-tech-application { margin: 20px 0; border: 1px solid var(--mmc-line); border-radius: 12px; background: var(--mmc-surface); }
.mmc-tech-application-controls { display: flex; flex-direction: column; gap: 12px; padding: 18px; }
.mmc-tech-application-footer { flex-shrink: 0; display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10px; padding: 10px 20px;
  border-top: 1px solid var(--mmc-line); background: var(--mmc-float);
}
.mmc-tech-preview { flex-shrink: 0; }
.mmc-tech-target { display: flex; gap: 10px; align-items: center; font-size: calc(12px * var(--mmc-type)); }
.mmc-tech-target > span { flex-shrink: 0; font-weight: 600; }
.mmc-tech-target select { flex: 1; min-width: 0; padding: 7px; background: var(--mmc-surface); border: 1px solid var(--mmc-line-2); border-radius: 8px; }
.mmc-tech-warnings { color: var(--mmc-accent); font-size: calc(12px * var(--mmc-type)); line-height: 1.45; }
.mmc-tech-warnings p { margin: 4px 0; }
.mmc-tech-substitutions { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 8px; }
.mmc-tech-substitutions label { display: flex; flex-direction: column; gap: 4px; min-width: 0; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-tech-substitutions input, .mmc-tech-substitutions select { min-width: 0; width: 100%; padding: 6px; background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 7px; }
.mmc-tech-refine-ack { display: flex; align-items: flex-start; gap: 8px; font-size: calc(12px * var(--mmc-type)); line-height: 1.4; }
.mmc-tech-refine-ack input { flex-shrink: 0; margin-top: 3px; }
.mmc-tech-apply { align-self: flex-end; background: var(--mmc-ink); color: var(--mmc-on-ink) !important; border: 0; border-radius: 9px; padding: 9px 16px; font-weight: 600 !important; flex-shrink: 0; }
.mmc-tech-status { flex-shrink: 0; padding: 8px 20px; min-height: 31px; border-top: 1px solid var(--mmc-line);
  font-size: calc(12px * var(--mmc-type)); line-height: 1.4; color: var(--mmc-dim); word-break: keep-all; overflow-wrap: anywhere;
}
.mmc-tech-status[data-error="true"] { color: var(--mmc-accent); }
.mmc-tech-focus-guard { width: 1px; height: 1px; overflow: hidden; position: absolute; opacity: 0; }
@media (max-width: 900px) {
  .mmc-tech-overlay { padding: 10px; }
  .mmc-tech-modal { border-radius: 15px; }
  .mmc-tech-modal .mmc-modal-head { padding: 14px 16px; }
  .mmc-tech-filters { padding: 0 14px 10px; }
  .mmc-tech-search { padding: 10px 14px; }
  .mmc-tech-grid { padding: 10px; }
}
/* List and detail each own exactly one body scroll. No fixed-height nested
   explanation/editor panels, including at large UI type scales on a phone. */
@media (max-width: 800px) {
  .mmc-tech-count { margin-left: auto; font-size: 10px; }
  .mmc-tech-modal .mmc-close { margin-left: auto; flex-shrink: 0; }
  .mmc-tech-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .mmc-tech-detail-body, .mmc-tech-application-controls { padding: 14px; }
  .mmc-tech-detail-nav, .mmc-tech-application-footer { padding: 10px 14px; }
  .mmc-tech-detail-nav { gap: 8px; }
  .mmc-tech-back { max-width: 65%; white-space: normal; }
  .mmc-tech-categories button { max-width: 100%; white-space: normal; text-align: left; }
  .mmc-tech-card > strong { font-size: 12px; }
  .mmc-tech-description { font-size: 11px; -webkit-line-clamp: 2; }
}
@media (max-width: 620px) {
  .mmc-tech-group-card { flex-direction: column; align-items: stretch; gap: 12px; padding: 12px; }
  .mmc-tech-group-card > .mmc-tech-media { width: 100%; max-width: none; }
  .mmc-tech-detail-nav { flex-wrap: wrap; }
  .mmc-tech-detail-name { min-width: 100px; }
}
@media (max-width: 440px) {
  .mmc-tech-target { flex-direction: column; align-items: stretch; }
  .mmc-tech-substitutions { grid-template-columns: minmax(0, 1fr); }
  .mmc-tech-status { padding: 8px 14px; }
}
`;
