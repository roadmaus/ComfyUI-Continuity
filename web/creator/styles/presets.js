// The preset library: the card grid, its three-state hero, and the inspector.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* The library reuses .mmc-modal, .mmc-tab, .mmc-search and .mmc-shelves from the
   picker — a user who has opened the asset picker once has already learned this
   window. What is new below is the card, which is a different kind of thing from
   a 140px media square and is laid out as one. */

.mmc-preset-split { flex: 1; display: flex; min-height: 0; }
.mmc-preset-grid {
  flex: 1; overflow-y: auto; padding: 2px 22px 22px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(272px, 1fr));
  gap: 13px; align-content: start; grid-auto-rows: max-content;
}
.mmc-preset-empty {
  grid-column: 1 / -1; padding: 60px 20px; text-align: center;
  color: var(--mmc-dim); font-size: calc(13.5px * var(--mmc-type)); line-height: 1.6;
}

/* ---- the card ------------------------------------------------------------ */

/* The card and its star, which cannot be nested — see renderCard. */
.mmc-preset-holder { position: relative; display: flex; min-width: 0; }
.mmc-preset-holder > .mmc-preset-card { flex: 1; min-width: 0; }

.mmc-preset-card {
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 14px; padding: 12px 13px 11px; text-align: left;
  display: flex; flex-direction: column; gap: 10px; position: relative;
  color: var(--mmc-text); font-family: inherit; cursor: pointer; min-width: 0;
}
.mmc-preset-card:hover { background: var(--mmc-surface-2); }
.mmc-preset-card[aria-selected="true"] {
  border-color: var(--mmc-line-3); background: var(--mmc-surface-2);
}
.mmc-preset-card:focus-visible { outline: none; border-color: var(--mmc-edge-2); }
/* A shipped starter, which cannot be overwritten — quieter, so a library of
   your own work does not read as half somebody else's. */
.mmc-preset-card[data-builtin] { background: none; border-style: dashed; }

/* The hero: one band, three states. Cover fills it and the lane becomes a ruler
   across its foot; no cover and the lane fills it outright; neither and the lane
   is the flat blocks it always was. Fixed height throughout, so the grid keeps
   its rhythm whatever a card holds. */
.mmc-preset-hero {
  height: 96px; border-radius: 9px; overflow: hidden; position: relative;
  /* Darker than the blocks that sit on it, so a shot with no picture still
     reads as a block rather than as a hole in the band. */
  background: var(--mmc-float); display: flex; flex-direction: column;
}
.mmc-preset-cover {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; display: block;
}

/* The lane, at true relative durations — the same reading the node face's reel
   gives, which is the one picture in this pack nothing else looks like. */
.mmc-preset-lane { display: flex; gap: 2px; height: 100%; align-items: stretch; padding: 0; }
.mmc-preset-pass {
  display: flex; gap: 1px; min-width: 0;
  border: 1px solid var(--mmc-line-2); border-radius: 5px; padding: 1px;
}
.mmc-preset-blk {
  background: var(--mmc-surface-3); border-radius: 3px; min-width: 2px; position: relative;
  overflow: hidden;
}
.mmc-preset-blk img {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; display: block;
}
/* Footage rather than a generation: the same hatch the strip draws a clip with. */
.mmc-preset-blk[data-clip]::after {
  content: ""; position: absolute; inset: 0;
  background: repeating-linear-gradient(135deg, var(--mmc-scrim) 0 4px, transparent 4px 8px);
}

/* With a cover the lane is demoted to a ruler over the picture's foot: the shape
   stays legible without competing with the render for the band. */
.mmc-preset-hero[data-cover] .mmc-preset-lane {
  position: absolute; left: 0; right: 0; bottom: 0; height: 7px;
  padding: 3px 3px 0; gap: 2px;
  background: linear-gradient(transparent, var(--mmc-scrim-2));
}
.mmc-preset-hero[data-cover] .mmc-preset-pass {
  border-color: color-mix(in srgb, var(--mmc-strong) 55%, transparent); border-radius: 2px; padding: 0;
}
.mmc-preset-hero[data-cover] .mmc-preset-blk {
  background: color-mix(in srgb, var(--mmc-strong) 72%, transparent); border-radius: 1px;
}
.mmc-preset-hero[data-cover] .mmc-preset-blk img { display: none; }
.mmc-preset-hero[data-cover] .mmc-preset-blk[data-clip]::after { opacity: .5; }

/* A pre-stage has no strip, so it draws the canvas at its true aspect — a
   still's characteristic artifact the way a strip is a piece's. */
.mmc-preset-canvas { height: 100%; display: flex; align-items: center; justify-content: center; }
.mmc-preset-canvas span {
  display: block; height: 84px; position: relative; overflow: hidden;
  border: 1.5px solid var(--mmc-line-2); border-radius: 4px;
  background: var(--mmc-surface-3);
}
.mmc-preset-canvas img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }

/* One shot: a single block at the width its seconds earn against the card. */
.mmc-preset-solo { height: 100%; display: flex; align-items: center; gap: 8px; padding: 0 4px; }
.mmc-preset-solo .mmc-preset-blk { height: 100%; border: 1px solid var(--mmc-line-2); }
.mmc-preset-solo em {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10px * var(--mmc-type)); color: var(--mmc-off); font-style: normal; flex: none;
}

.mmc-preset-star {
  position: absolute; top: 8px; right: 9px; width: 24px; height: 24px;
  display: grid; place-items: center; border: 0; border-radius: 50%;
  background: var(--mmc-scrim); color: var(--mmc-off); cursor: pointer; padding: 0;
}
.mmc-preset-star svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-preset-star[aria-pressed="true"] { color: var(--mmc-accent); }
.mmc-preset-star[aria-pressed="true"] svg { fill: currentColor; }

/* Bigger and tighter than anything else in this pack: the library is a place,
   not a popover, and the type scale should say so before you read a word. */
.mmc-preset-name {
  font-size: calc(15px * var(--mmc-type)); font-weight: 600; letter-spacing: -.01em; line-height: 1.3;
  margin: 0; padding-right: 22px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Instrument reading, not prose — the one register this pack had no face for. */
.mmc-preset-facts {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-dim); letter-spacing: .01em;
  margin: -6px 0 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* Section chips take the reference-identity hues from base.js, one fixed hue
   each: the eye is already trained on them in the prompt box, so a chip row
   becomes scannable for nothing and no eighth colour has to be invented.
   Nothing here takes the amber accent — that means *on* in this pack, and a card
   is not a state. */
.mmc-preset-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.mmc-preset-chip {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10px * var(--mmc-type)); letter-spacing: .04em; padding: 2px 7px; border-radius: 7px;
  color: var(--tag, var(--mmc-dim));
  background: color-mix(in srgb, var(--tag, var(--mmc-off)) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--tag, var(--mmc-off)) 26%, transparent);
}
.mmc-preset-chip.plain { color: var(--mmc-off); background: none; border-color: var(--mmc-line); }

/* ---- inspector ----------------------------------------------------------- */

.mmc-preset-insp {
  width: 306px; flex: none; border-left: 1px solid var(--mmc-line);
  background: var(--mmc-float); padding: 18px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 13px;
}
.mmc-preset-insp-title {
  font-size: calc(16px * var(--mmc-type)); font-weight: 600; letter-spacing: -.01em; line-height: 1.3;
}
.mmc-preset-insp-name {
  width: 100%; box-sizing: border-box; height: calc(34px * var(--mmc-type)); border-radius: 9px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); color: var(--mmc-text);
  padding: 0 11px; font-size: calc(14px * var(--mmc-type)); font-family: inherit; outline: none;
}
.mmc-preset-insp-name:focus { border-color: var(--mmc-line-3); }
.mmc-preset-insp-meta {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-off); line-height: 1.7; margin: -6px 0 0;
}
.mmc-preset-insp-meta button {
  background: none; border: 0; padding: 0; font: inherit; cursor: pointer;
  color: var(--mmc-tag-0);
}
.mmc-preset-insp-hint { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.55; }

.mmc-preset-rows { display: flex; flex-direction: column; gap: 1px; }
.mmc-preset-row {
  display: flex; align-items: flex-start; gap: 9px; padding: 7px 8px;
  border-radius: 8px; background: none; border: 0; text-align: left;
  color: var(--mmc-text); font-family: inherit; font-size: calc(12.5px * var(--mmc-type)); cursor: pointer;
}
.mmc-preset-row:hover:not(:disabled) { background: var(--mmc-surface-2); }
.mmc-preset-row:disabled { opacity: .45; cursor: default; }
.mmc-preset-box {
  width: 14px; height: 14px; border-radius: 4px; flex: none; margin-top: 2px;
  border: 1px solid var(--mmc-line-3); display: grid; place-items: center;
}
.mmc-preset-row[aria-checked="true"] .mmc-preset-box { background: var(--mmc-ink); border-color: var(--mmc-ink); }
.mmc-preset-row[aria-checked="true"] .mmc-preset-box::after {
  content: ""; width: 4px; height: 8px; border: solid var(--mmc-on-ink);
  border-width: 0 2px 2px 0; transform: rotate(45deg) translate(-1px,-1px);
}
.mmc-preset-row:disabled .mmc-preset-box { border-style: dashed; }
/* The reading is targeted through its own wrapper, not through a bare span
   selector on the row — the box is a span too, and an element selector at that
   specificity beat its grid display and knocked the tick off centre. */
.mmc-preset-text { min-width: 0; }
.mmc-preset-text b { font-weight: 500; display: block; }
.mmc-preset-text span {
  display: block; color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45;
}

.mmc-preset-apply {
  margin-top: auto; height: calc(38px * var(--mmc-type)); border-radius: 19px; background: var(--mmc-ink); border: 0;
  color: var(--mmc-on-ink); font-size: calc(13.5px * var(--mmc-type)); font-weight: 500; font-family: inherit; cursor: pointer;
}
.mmc-preset-apply:disabled { background: var(--mmc-surface-3); color: var(--mmc-off); cursor: default; }
.mmc-preset-danger {
  height: calc(32px * var(--mmc-type)); border-radius: 16px; background: none; color: var(--mmc-dim);
  border: 1px solid var(--mmc-line); font-size: calc(12.5px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-preset-danger:hover { color: var(--mmc-tag-3); border-color: color-mix(in srgb, var(--mmc-tag-3) 40%, transparent); }
.mmc-preset-danger.armed {
  color: var(--mmc-strong); background: color-mix(in srgb, var(--mmc-tag-3) 22%, transparent); border-color: color-mix(in srgb, var(--mmc-tag-3) 55%, transparent);
}
.mmc-preset-insp-acts { display: flex; gap: 8px; }
.mmc-preset-insp-acts button { flex: 1; }

.mmc-preset-problem {
  margin: 0 22px 12px; padding: 9px 12px; border-radius: 10px;
  background: color-mix(in srgb, var(--mmc-tag-3) 12%, transparent); border: 1px solid color-mix(in srgb, var(--mmc-tag-3) 30%, transparent);
  color: color-mix(in srgb, var(--mmc-tag-3) 60%, var(--mmc-ink)); font-size: calc(12.5px * var(--mmc-type));
}

/* ---- the Style tab ------------------------------------------------------- */
/* The catalogue's card is the preset card with its middle swapped: the hero is a
   still rather than a strip, and the descriptor stands where the section chips
   would. A row of chips all reading "style", under nine hundred cards on a tab
   that holds nothing else, would be nine hundred repetitions of the tab's own
   name — so the words go there instead, and they are the words that are about to
   land in the prompt.

   Taller band than a preset's, and the still fills it rather than fitting inside
   it. The atlas keeps each clip's true shape, so a fitted still would draw a
   4:3 clip at half the width of a 16:9 one — and the shape of somebody else's
   dataset clip has no bearing on the canvas you are about to render. What is
   being judged here is grain, palette and medium, and those want pixels. */
.mmc-preset-card[data-style] .mmc-preset-hero { height: 132px; }
.mmc-preset-card[data-style] .mmc-preset-name {
  font-size: calc(13.5px * var(--mmc-type)); line-height: 1.35; white-space: normal; padding-right: 0;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  line-clamp: 2; overflow: hidden;
}
/* The rest of the descriptor, which is what tells one entry from the twenty
   beside it that open on the same three words. */
.mmc-style-rest {
  margin: -6px 0 0; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-dim);
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  line-clamp: 2; overflow: hidden;
}
/* One descriptor can be read off several clips. The first fills the band and the
   rest are counted here; all of them are in the inspector. */
.mmc-style-more {
  position: absolute; right: 6px; bottom: 6px; padding: 1px 6px; border-radius: 7px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(9.5px * var(--mmc-type)); font-style: normal; color: var(--mmc-text); background: var(--mmc-scrim-2);
}

.mmc-style-full {
  margin: -6px 0 0; font-size: calc(12.5px * var(--mmc-type)); line-height: 1.55; color: var(--mmc-dim);
}
/* Every frame the descriptor was read off. Two style sentences can read almost
   alike; the frames are what tell them apart, and this is where there is room
   for all of them. */
.mmc-style-shots { display: flex; flex-wrap: wrap; gap: 7px; }
.mmc-style-shots figure { margin: 0; width: 74px; }
.mmc-style-shots img {
  width: 74px; height: 56px; object-fit: cover; display: block;
  border-radius: 6px; background: var(--mmc-float);
}
.mmc-style-shots figcaption {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(9.5px * var(--mmc-type)); color: var(--mmc-off); text-align: center; margin-top: 3px;
}
/* Where a descriptor was read off several clips, the frames pick as well as
   show — one of them is the one that gets cast. A single-clip style has nothing
   to choose, so its figure stays a figure. */
.mmc-style-shot {
  padding: 0; border: 0; background: none; cursor: pointer; border-radius: 8px;
}
.mmc-style-shot:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-style-shot img { opacity: .55; transition: opacity .12s ease; }
.mmc-style-shot:hover img { opacity: .85; }
.mmc-style-shots figure[data-chosen] img {
  opacity: 1; box-shadow: 0 0 0 2px var(--mmc-accent);
}
.mmc-style-shots figure[data-chosen] figcaption { color: var(--mmc-text); }

/* The frame, offered as plainly as the phrase. A style is half a sentence and
   half a picture, and for a medium nobody has a folder of the picture is the
   only half you can get anywhere else. */
.mmc-style-cast {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; padding: 7px 10px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--mmc-line); background: var(--mmc-surface-2);
  color: var(--mmc-text); font-size: calc(12px * var(--mmc-type));
}
.mmc-style-cast:hover:not(:disabled) {
  background: var(--mmc-surface-3); border-color: var(--mmc-line-2);
}
.mmc-style-cast:disabled { opacity: .5; cursor: default; }

/* What the clip's caption said, where the style clause is a cut of it. Folded
   away: it is provenance, not the text going into the prompt, and the whole
   point of cutting it was that it is mostly somebody else's scene. */
.mmc-style-caption > summary {
  cursor: pointer; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); list-style: none;
}
.mmc-style-caption > summary::-webkit-details-marker { display: none; }
.mmc-style-caption > summary::before { content: "▸ "; }
.mmc-style-caption[open] > summary::before { content: "▾ "; }
.mmc-style-caption > summary:hover { color: var(--mmc-dim); }
.mmc-style-caption p {
  margin: 6px 0 0; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.55; color: var(--mmc-off);
}
.mmc-style-credit {
  margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(9.5px * var(--mmc-type)); line-height: 1.6; color: var(--mmc-off);
}

/* ---- the Cast tab -------------------------------------------------------- */

/* A roster card is a portrait, so its hero is taller than a strip's band and its
   picture is framed rather than filled edge to edge: what you are reading off it
   is a face, and a face wants the head-room a 96px letterbox crops off. */
.mmc-preset-card[data-cast] .mmc-preset-hero { height: 124px; }
.mmc-cast-hero { background: var(--mmc-surface-3); }
.mmc-cast-hero-blank {
  position: absolute; inset: 0; display: flex; align-items: center;
  justify-content: center; color: var(--mmc-off);
}
/* Their name is a handle — the token you type into a sentence — so it is set in
   the face the prompt box sets handles in, at the size a card's title wants. */
.mmc-preset-card[data-cast] .mmc-preset-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(14px * var(--mmc-type)); font-weight: 500; padding-right: 22px;
}

/* A member's own prose on their card, under the numbers. Two lines: enough to
   tell twelve people apart, not enough to turn the grid into a page of text. */
.mmc-cast-blurb {
  margin: -4px 0 0; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-off);
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  line-clamp: 2; overflow: hidden;
}

/* ---- the editor sheet ----------------------------------------------------- */

/* Making somebody takes the whole window rather than the 306px inspector: the
   files sit in one row at the size you recognise a face at, and the description
   is a box instead of a line. The roster is not on screen while you are in here,
   which is what the one way out at the top is for. */
.mmc-cast-sheet { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.mmc-cast-sheet-bar {
  display: flex; align-items: center; gap: 8px; padding: 14px 24px;
  border-bottom: 1px solid var(--mmc-line);
}
.mmc-cast-sheet-back {
  display: flex; align-items: center; gap: 8px; padding: 0; border: 0;
  background: none; color: var(--mmc-dim); font-family: inherit; font-size: calc(14px * var(--mmc-type));
  cursor: pointer;
}
.mmc-cast-sheet-back:hover { color: var(--mmc-text); }
/* The chevron points back the way it points down on a card. */
.mmc-cast-sheet-back svg {
  width: 15px; height: 15px; transform: rotate(90deg); flex: none;
}
/* There is no Save: the row existed from the moment New was pressed. This says
   so once, quietly, rather than a button implying the work is not kept yet. */
.mmc-cast-sheet-saved {
  margin-left: auto; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-off);
}
.mmc-cast-sheet-body {
  flex: 1; overflow-y: auto; padding: 26px 40px;
  display: flex; flex-direction: column; gap: 26px; min-height: 0;
}
/* The words band takes what the two above it leave. The description is the field
   this sheet exists to make writable; a fixed 78px box under three hundred
   pixels of nothing says the opposite. */
.mmc-cast-sheet-body > .mmc-cast-sheet-band:last-child {
  flex: 1; display: flex; flex-direction: column; min-height: 120px;
}
.mmc-cast-sheet-body > .mmc-cast-sheet-band:last-child .mmc-cast-sheet-desc { flex: 1; }
/* The sheet has room the inspector never had, so the three things a member is
   made of get named instead of inferred. */
.mmc-cast-sheet-legend {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10px * var(--mmc-type)); letter-spacing: .06em; text-transform: uppercase;
  color: var(--mmc-off); margin-bottom: 10px;
}
.mmc-cast-sheet-band { min-width: 0; }
.mmc-cast-sheet-who { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.mmc-cast-sheet-face {
  width: 46px; height: 46px; border-radius: 10px; object-fit: cover; flex: none;
  background: var(--mmc-surface-3); box-shadow: 0 0 0 2px var(--tag, transparent);
}
.mmc-cast-sheet-face-blank {
  display: flex; align-items: center; justify-content: center; color: var(--mmc-off);
  box-shadow: inset 0 0 0 1px var(--mmc-line);
}
/* The @ belongs to the name, not to the row: it is one token with a gap in it
   otherwise. */
.mmc-cast-sheet-at {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(20px * var(--mmc-type)); color: var(--mmc-off); margin-right: -13px;
}
.mmc-cast-sheet-name {
  background: none; border: 0; border-bottom: 1px solid var(--mmc-line);
  padding: 2px 2px 4px; color: var(--tag, var(--mmc-text)); font: inherit;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(20px * var(--mmc-type)); font-weight: 500; width: 11ch; min-width: 0; outline: none;
}
.mmc-cast-sheet-name:focus { border-bottom-color: var(--tag, var(--mmc-accent)); }
.mmc-cast-sheet-name::placeholder { color: var(--mmc-off); font-weight: 400; }
.mmc-cast-sheet-is { font-size: calc(13px * var(--mmc-type)); color: var(--mmc-dim); }
/* A word inside the sentence "@ana is a person", not a control of the same
   weight as the name beside it. */
.mmc-cast-sheet-takes {
  padding: 3px 8px; border-radius: 7px; border: 0; background: var(--mmc-surface-2);
  color: var(--mmc-dim); font-family: inherit; font-size: calc(13px * var(--mmc-type)); cursor: pointer;
}
.mmc-cast-sheet-takes:hover { background: var(--mmc-surface-3); color: var(--mmc-text); }

.mmc-cast-sheet-refs { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
.mmc-cast-sheet-ref {
  width: 46px; display: flex; flex-direction: column; align-items: center; flex: none;
}
.mmc-cast-sheet-tile {
  position: relative; padding: 0; border: 0; background: none; cursor: pointer;
  border-radius: 10px; line-height: 0;
}
.mmc-cast-sheet-tile:hover .mmc-cast-sheet-thumb { filter: brightness(1.25); }
.mmc-cast-sheet-tile:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 3px; }
.mmc-cast-sheet-thumb {
  width: 46px; height: 46px; border-radius: 10px; object-fit: cover; display: flex;
  align-items: center; justify-content: center; color: var(--mmc-dim);
  background: var(--mmc-surface-3);
}
/* One colour per tile, set on the wrapper and read by both the badge and the
   caption. Their looks are the default and wear no badge at all; the three
   departures from it each say which, in the shelf's own colours. */
.mmc-cast-sheet-ref { --role: var(--mmc-dim); }
.mmc-role-motion { --role: var(--mmc-role-motion); }
.mmc-role-voice { --role: var(--mmc-role-voice); }
.mmc-role-replaces { --role: var(--mmc-role-replaces); }
.mmc-cast-sheet-badge {
  position: absolute; right: -4px; bottom: -4px; width: 18px; height: 18px;
  border-radius: 999px; display: flex; align-items: center; justify-content: center;
  background: var(--mmc-surface-3); box-shadow: 0 0 0 2px var(--mmc-float);
  color: var(--role);
}
.mmc-cast-sheet-cap {
  margin-top: 7px; font-size: calc(10.5px * var(--mmc-type)); color: var(--role); text-align: center;
  white-space: nowrap;
}
.mmc-cast-sheet-add {
  width: calc(46px * var(--mmc-type)); height: calc(46px * var(--mmc-type)); box-sizing: border-box; border-radius: 10px;
  border: 1px dashed var(--mmc-line); background: none; cursor: pointer;
  color: var(--mmc-off); font-size: calc(20px * var(--mmc-type)); font-family: inherit; line-height: 1;
  display: flex; align-items: center; justify-content: center;
}
.mmc-cast-sheet-add:hover { border-color: var(--mmc-accent); color: var(--mmc-accent); }
.mmc-cast-sheet-nothing {
  margin: 0; padding-top: 4px; font-size: calc(12.5px * var(--mmc-type)); line-height: 1.55;
  color: var(--mmc-dim); max-width: 44ch;
}
/* A footnote to the row above it. Under the tiles rather than at the far end of
   their row: on a sheet this wide, anchoring it right put it three hundred
   pixels from the files it is about. */
.mmc-cast-sheet-keeprow { display: flex; margin-top: 14px; margin-left: -8px; }
.mmc-cast-sheet-keep {
  background: none; border: 0; padding: 3px 8px; border-radius: 6px;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(11.5px * var(--mmc-type));
  cursor: pointer; white-space: nowrap;
}
.mmc-cast-sheet-keep:hover { background: var(--mmc-surface-2); color: var(--mmc-dim); }

.mmc-cast-sheet-desc {
  width: 100%; box-sizing: border-box; background: var(--mmc-surface-2);
  border: 1px solid transparent; border-radius: 10px; padding: 11px 13px;
  color: var(--mmc-text); font: inherit; font-size: calc(13.5px * var(--mmc-type)); line-height: 1.55;
  outline: none; resize: vertical; min-height: calc(78px * var(--mmc-type));
}
.mmc-cast-sheet-desc:focus { border-color: var(--mmc-line); }
.mmc-cast-sheet-desc::placeholder { color: var(--mmc-off); }
.mmc-cast-sheet-line {
  display: flex; gap: 10px; align-items: center; margin-top: 12px; min-width: 0;
}
.mmc-cast-sheet-of { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim); white-space: nowrap; }
.mmc-cast-sheet-replaces { min-height: 0; resize: none; }

.mmc-cast-sheet-foot {
  display: flex; align-items: center; gap: 10px; padding: 16px 40px;
  border-top: 1px solid var(--mmc-line);
}
.mmc-cast-sheet-foot .mmc-preset-danger { padding: 0 16px; }
/* Not the inspector's full-width pill: here it is one of three things on a row,
   and the only one that does anything to a node. */
.mmc-cast-sheet-apply { margin: 0 0 0 auto; padding: 0 22px; }

/* Their references, in the inspector: what they are made of, captioned with what
   each one lends them. The captions are the panel's argument — four pictures of
   the same person say nothing about why there are four. */
.mmc-cast-insp { display: flex; flex-direction: column; gap: 9px; }
.mmc-cast-insp-files { display: flex; flex-wrap: wrap; gap: 7px; }
.mmc-cast-insp-files figure { margin: 0; width: 66px; }
.mmc-cast-insp-files img, .mmc-cast-insp-glyph {
  width: 66px; height: 66px; object-fit: cover; display: flex;
  align-items: center; justify-content: center; color: var(--mmc-dim);
  border-radius: 8px; background: var(--mmc-surface-3);
}
.mmc-cast-insp-files figcaption {
  font-size: calc(9.5px * var(--mmc-type)); line-height: 1.35; color: var(--mmc-off);
  text-align: center; margin-top: 3px;
}
.mmc-cast-insp-desc {
  margin: 0; font-size: calc(12px * var(--mmc-type)); line-height: 1.55; color: var(--mmc-dim);
}

/* ---- the save sheet ------------------------------------------------------ */

.mmc-preset-save { display: flex; flex-direction: column; gap: 14px; padding: 20px 22px; }
.mmc-preset-save-hint { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.55; margin: -6px 0 0; }
`;
