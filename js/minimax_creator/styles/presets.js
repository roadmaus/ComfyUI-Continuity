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
  color: var(--mmc-dim); font-size: 13.5px; line-height: 1.6;
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
  border-color: rgba(255,255,255,.28); background: var(--mmc-surface-2);
}
.mmc-preset-card:focus-visible { outline: none; border-color: #7a7a7a; }
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
  background: #131313; display: flex; flex-direction: column;
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
  border: 1px solid rgba(255,255,255,.16); border-radius: 5px; padding: 1px;
}
.mmc-preset-blk {
  background: #3d3d3d; border-radius: 3px; min-width: 2px; position: relative;
  overflow: hidden;
}
.mmc-preset-blk img {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; display: block;
}
/* Footage rather than a generation: the same hatch the strip draws a clip with. */
.mmc-preset-blk[data-clip]::after {
  content: ""; position: absolute; inset: 0;
  background: repeating-linear-gradient(135deg, rgba(0,0,0,.38) 0 4px, rgba(0,0,0,0) 4px 8px);
}

/* With a cover the lane is demoted to a ruler over the picture's foot: the shape
   stays legible without competing with the render for the band. */
.mmc-preset-hero[data-cover] .mmc-preset-lane {
  position: absolute; left: 0; right: 0; bottom: 0; height: 7px;
  padding: 3px 3px 0; gap: 2px;
  background: linear-gradient(transparent, rgba(0,0,0,.62));
}
.mmc-preset-hero[data-cover] .mmc-preset-pass {
  border-color: rgba(255,255,255,.55); border-radius: 2px; padding: 0;
}
.mmc-preset-hero[data-cover] .mmc-preset-blk {
  background: rgba(255,255,255,.72); border-radius: 1px;
}
.mmc-preset-hero[data-cover] .mmc-preset-blk img { display: none; }
.mmc-preset-hero[data-cover] .mmc-preset-blk[data-clip]::after { opacity: .5; }

/* A pre-stage has no strip, so it draws the canvas at its true aspect — a
   still's characteristic artifact the way a strip is a piece's. */
.mmc-preset-canvas { height: 100%; display: flex; align-items: center; justify-content: center; }
.mmc-preset-canvas span {
  display: block; height: 84px; position: relative; overflow: hidden;
  border: 1.5px solid rgba(255,255,255,.16); border-radius: 4px;
  background: var(--mmc-surface-3);
}
.mmc-preset-canvas img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }

/* One shot: a single block at the width its seconds earn against the card. */
.mmc-preset-solo { height: 100%; display: flex; align-items: center; gap: 8px; padding: 0 4px; }
.mmc-preset-solo .mmc-preset-blk { height: 100%; border: 1px solid rgba(255,255,255,.16); }
.mmc-preset-solo em {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px; color: var(--mmc-off); font-style: normal; flex: none;
}

.mmc-preset-star {
  position: absolute; top: 8px; right: 9px; width: 24px; height: 24px;
  display: grid; place-items: center; border: 0; border-radius: 50%;
  background: rgba(0,0,0,.45); color: var(--mmc-off); cursor: pointer; padding: 0;
}
.mmc-preset-star svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-preset-star[aria-pressed="true"] { color: var(--mmc-accent); }
.mmc-preset-star[aria-pressed="true"] svg { fill: currentColor; }

/* Bigger and tighter than anything else in this pack: the library is a place,
   not a popover, and the type scale should say so before you read a word. */
.mmc-preset-name {
  font-size: 15px; font-weight: 600; letter-spacing: -.01em; line-height: 1.3;
  margin: 0; padding-right: 22px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Instrument reading, not prose — the one register this pack had no face for. */
.mmc-preset-facts {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10.5px; color: var(--mmc-dim); letter-spacing: .01em;
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
  font-size: 10px; letter-spacing: .04em; padding: 2px 7px; border-radius: 7px;
  color: var(--tag, var(--mmc-dim));
  background: color-mix(in srgb, var(--tag, var(--mmc-off)) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--tag, var(--mmc-off)) 26%, transparent);
}
.mmc-preset-chip.plain { color: var(--mmc-off); background: none; border-color: var(--mmc-line); }

/* ---- inspector ----------------------------------------------------------- */

.mmc-preset-insp {
  width: 306px; flex: none; border-left: 1px solid var(--mmc-line);
  background: #131313; padding: 18px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 13px;
}
.mmc-preset-insp-title {
  font-size: 16px; font-weight: 600; letter-spacing: -.01em; line-height: 1.3;
}
.mmc-preset-insp-name {
  width: 100%; box-sizing: border-box; height: 34px; border-radius: 9px;
  background: #202020; border: 1px solid var(--mmc-line); color: var(--mmc-text);
  padding: 0 11px; font-size: 14px; font-family: inherit; outline: none;
}
.mmc-preset-insp-name:focus { border-color: rgba(255,255,255,.28); }
.mmc-preset-insp-meta {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10.5px; color: var(--mmc-off); line-height: 1.7; margin: -6px 0 0;
}
.mmc-preset-insp-meta button {
  background: none; border: 0; padding: 0; font: inherit; cursor: pointer;
  color: var(--mmc-tag-0);
}
.mmc-preset-insp-hint { font-size: 12px; color: var(--mmc-dim); line-height: 1.55; }

.mmc-preset-rows { display: flex; flex-direction: column; gap: 1px; }
.mmc-preset-row {
  display: flex; align-items: flex-start; gap: 9px; padding: 7px 8px;
  border-radius: 8px; background: none; border: 0; text-align: left;
  color: var(--mmc-text); font-family: inherit; font-size: 12.5px; cursor: pointer;
}
.mmc-preset-row:hover:not(:disabled) { background: var(--mmc-surface-2); }
.mmc-preset-row:disabled { opacity: .45; cursor: default; }
.mmc-preset-box {
  width: 14px; height: 14px; border-radius: 4px; flex: none; margin-top: 2px;
  border: 1px solid rgba(255,255,255,.24); display: grid; place-items: center;
}
.mmc-preset-row[aria-checked="true"] .mmc-preset-box { background: #fff; border-color: #fff; }
.mmc-preset-row[aria-checked="true"] .mmc-preset-box::after {
  content: ""; width: 4px; height: 8px; border: solid #111;
  border-width: 0 2px 2px 0; transform: rotate(45deg) translate(-1px,-1px);
}
.mmc-preset-row:disabled .mmc-preset-box { border-style: dashed; }
/* The reading is targeted through its own wrapper, not through a bare span
   selector on the row — the box is a span too, and an element selector at that
   specificity beat its grid display and knocked the tick off centre. */
.mmc-preset-text { min-width: 0; }
.mmc-preset-text b { font-weight: 500; display: block; }
.mmc-preset-text span {
  display: block; color: var(--mmc-dim); font-size: 11.5px; line-height: 1.45;
}

.mmc-preset-apply {
  margin-top: auto; height: 38px; border-radius: 19px; background: #fff; border: 0;
  color: #111; font-size: 13.5px; font-weight: 500; font-family: inherit; cursor: pointer;
}
.mmc-preset-apply:disabled { background: var(--mmc-surface-3); color: var(--mmc-off); cursor: default; }
.mmc-preset-danger {
  height: 32px; border-radius: 16px; background: none; color: var(--mmc-dim);
  border: 1px solid var(--mmc-line); font-size: 12.5px; font-family: inherit; cursor: pointer;
}
.mmc-preset-danger:hover { color: #f07da0; border-color: rgba(240,125,160,.4); }
.mmc-preset-danger.armed {
  color: #fff; background: rgba(240,125,160,.22); border-color: rgba(240,125,160,.55);
}
.mmc-preset-insp-acts { display: flex; gap: 8px; }
.mmc-preset-insp-acts button { flex: 1; }

.mmc-preset-problem {
  margin: 0 22px 12px; padding: 9px 12px; border-radius: 10px;
  background: rgba(240,125,160,.12); border: 1px solid rgba(240,125,160,.3);
  color: #f0b3c5; font-size: 12.5px;
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
  font-size: 13.5px; line-height: 1.35; white-space: normal; padding-right: 0;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  line-clamp: 2; overflow: hidden;
}
/* The rest of the descriptor, which is what tells one entry from the twenty
   beside it that open on the same three words. */
.mmc-style-rest {
  margin: -6px 0 0; font-size: 11.5px; line-height: 1.45; color: var(--mmc-dim);
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  line-clamp: 2; overflow: hidden;
}
/* One descriptor can be read off several clips. The first fills the band and the
   rest are counted here; all of them are in the inspector. */
.mmc-style-more {
  position: absolute; right: 6px; bottom: 6px; padding: 1px 6px; border-radius: 7px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9.5px; font-style: normal; color: #e6e6e6; background: rgba(0,0,0,.62);
}

.mmc-style-full {
  margin: -6px 0 0; font-size: 12.5px; line-height: 1.55; color: var(--mmc-dim);
}
/* Every frame the descriptor was read off. Two style sentences can read almost
   alike; the frames are what tell them apart, and this is where there is room
   for all of them. */
.mmc-style-shots { display: flex; flex-wrap: wrap; gap: 7px; }
.mmc-style-shots figure { margin: 0; width: 74px; }
.mmc-style-shots img {
  width: 74px; height: 56px; object-fit: cover; display: block;
  border-radius: 6px; background: #131313;
}
.mmc-style-shots figcaption {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9.5px; color: var(--mmc-off); text-align: center; margin-top: 3px;
}
.mmc-style-credit {
  margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9.5px; line-height: 1.6; color: var(--mmc-off);
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
  font-size: 14px; font-weight: 500; padding-right: 22px;
}

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
  font-size: 9.5px; line-height: 1.35; color: var(--mmc-off);
  text-align: center; margin-top: 3px;
}
.mmc-cast-insp-desc {
  margin: 0; font-size: 12px; line-height: 1.55; color: var(--mmc-dim);
}

/* ---- the save sheet ------------------------------------------------------ */

.mmc-preset-save { display: flex; flex-direction: column; gap: 14px; padding: 20px 22px; }
.mmc-preset-save-hint { font-size: 12.5px; color: var(--mmc-dim); line-height: 1.55; margin: -6px 0 0; }
`;
