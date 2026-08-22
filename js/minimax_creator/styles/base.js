// Tokens and the pre-stage root body.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* Tokens live on :root, not .mmc-root: popovers and the picker portal to
   document.body, so anything scoped to the node body would leave them
   resolving to nothing. */
:root {
  --mmc-bg: #0e0e0e;
  --mmc-surface: #1c1c1c;
  --mmc-surface-2: #262626;
  --mmc-surface-3: #2f2f2f;
  --mmc-line: rgba(255,255,255,.09);
  --mmc-text: #ededed;
  --mmc-dim: #8b8b8b;
  --mmc-off: #565656;
  --mmc-accent: #f0a63c;
  /* One height for everything pill-shaped. A row that mixes a 38px control with
     a 32px one and a 23px readout reads as three unrelated things rather than
     as a row, and every one of those numbers was set locally by whoever added
     the control. Tokenised so the next one cannot be a fourth. */
  --mmc-pill-h: 38px;
  /* The rail's tile, and everything positioned against it — the refiner's
     corner chevron is the one that kept drifting off the box when the shell
     drew a smaller square. One token, so the shell is a single override
     rather than a second set of offsets that has to be kept in step. */
  --mmc-tool-tile: 56px;
  /* What a file lends a subject, as colour. Their looks are the default and
     wear none; these are the three departures from it, and they are worn by the
     shelf's badges and dots and by the library's editor tiles. Tokens rather
     than three literals per surface, because the surfaces disagree about
     cascade order and a caption that lost its colour to a later stylesheet is
     how that was found out. */
  --mmc-role-motion: #6ebeff;
  --mmc-role-voice: #a8c858;
  --mmc-role-replaces: var(--mmc-accent);
  --mmc-blue: #2f7bf6;
  /* Reference identity hues: one per attached asset, worn by its thumbnail
     ring, its handle in the bar, and its chip in the prompt, so a chip in the
     sentence can be matched to a picture without reading. Equal perceived
     lightness on the dark surfaces; the amber zone is skipped so an asset
     never masquerades as the accent. Index comes from state.tagIndex(). */
  --mmc-tag-0: #5cb8f0;
  --mmc-tag-1: #63c98e;
  --mmc-tag-2: #9d95f5;
  --mmc-tag-3: #f07da0;
  --mmc-tag-4: #45c4c0;
  --mmc-tag-5: #f0906b;
  --mmc-tag-6: #d57de8;
  --mmc-tag-7: #a8c858;
}

/* Setting --tag is all these do; components read it with an accent fallback,
   so an untagged element (a LoRA row, a dangling handle) keeps today's look. */
.mmc-tag-0 { --tag: var(--mmc-tag-0); }
.mmc-tag-1 { --tag: var(--mmc-tag-1); }
.mmc-tag-2 { --tag: var(--mmc-tag-2); }
.mmc-tag-3 { --tag: var(--mmc-tag-3); }
.mmc-tag-4 { --tag: var(--mmc-tag-4); }
.mmc-tag-5 { --tag: var(--mmc-tag-5); }
.mmc-tag-6 { --tag: var(--mmc-tag-6); }
.mmc-tag-7 { --tag: var(--mmc-tag-7); }

/* A body is a column of hosts, and most of them are empty most of the time: no
   references, no LoRAs, no notice, no next shot. Empty they are still rows of
   the column, and a flex gap is paid between rows whether or not either has a
   height — which is how a card with a rail and a prompt on it opened with sixty
   pixels of nothing stacked between them. Nothing to draw, no row. */
.mmc-root > div:empty { display: none; }
.mmc-root {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
  color: var(--mmc-text);
  display: flex; flex-direction: column; gap: 10px;
  padding: 12px; box-sizing: border-box; height: 100%; overflow: hidden;
}

/* A body that is hosting another one — the piece of one shot, whose face is that
   shot's own editor. It is a slot rather than a layout: the body inside brings
   its own padding, and a second inset here would draw a narrower face than the
   strip's on a node of the same width. */
.mmc-root.hosting { padding: 0; gap: 0; }

/* What the DOM widget is actually given, on all three nodes. The widget writes
   left/top/width/height onto whatever element it holds, every frame, so the body
   itself cannot be that element — it has to be able to leave for the fullscreen
   editor and come back. This is the part that stays behind and keeps being
   positioned; see attach() in minimax_creator.js. */
.mmc-widget-host { height: 100%; }
.mmc-widget-host > * { height: 100%; }

/* The pre-stage's outer body. It holds whichever editor the architecture calls
   for and is swapped when that changes, so it has to be the full height the DOM
   widget gave it — the .mmc-root inside is what does the layout. */
.mmc-prestage-host { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.mmc-prestage-host > * { flex: 1 1 auto; min-height: 0; }

`;
