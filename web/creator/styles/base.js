// Tokens and the pre-stage root body.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* Tokens live on :root, not .mmc-root: popovers and the picker portal to
   document.body, so anything scoped to the node body would leave them
   resolving to nothing.

   Every colour here that is not this pack's own identity is derived from
   ComfyUI's, so the pack follows whatever palette the Appearance tab is set to
   rather than drawing its own dark one over the top of a light graph.

   Two families of ComfyUI variable exist and they are not equivalent. The
   palette writes seventeen properties onto document.documentElement for every
   palette there is -- Dark, Light, Github, Nord, Solarized, and any the user
   made -- so anything anchored to those follows all of them. The semantic
   layer (--warning-background, --primary-background, and the rest) is declared
   in the frontend's stylesheet under :root and .dark-theme and only flips
   between two states. Everything structural below reads the palette; only the
   two hues the palette has no word for read the semantic layer, and that is
   noted where it happens. */
:root {
  /* The two anchors the ramp is built from. Ground is the darkest chrome the
     palette names, which is what a node body sits on; ink is the colour the
     palette writes text in. Every surface, line, wash and scrim below is a
     mix of the two, so the ramp keeps its own relationships -- the step from a
     card to the tile on it, the weight of a hairline against the surface
     behind it -- on a ground of any lightness. Mixing toward ink always moves
     away from the ground, which is the property that makes this survive a
     light palette; a ramp written as fixed greys does not.

     The ground-to-ink steps mix in oklab rather than sRGB. An sRGB mix is even
     in its numbers and not in the eye: the same 6% step that reads as one step
     down from a near-black ground almost vanishes against a near-white one,
     and the four surfaces stopped being four surfaces on the Light palette.
     The alpha families below stay in sRGB, where mixing with transparent is
     what a browser does anyway and oklab would only bend the hue. */
  --mmc-ground: var(--comfy-menu-bg);
  --mmc-ink: var(--fg-color);

  /* How far each rung of the ramp steps off the ground, as a multiplier on all
     of them at once. 1 is the ladder as drawn; the Appearance tab offers either
     side of it and settings.py will hold anything between 0.4 and 2.

     It exists because the ladder is proportional and some palettes have very
     little contrast to be proportional to: on Github, Nord and Solarized the
     four surfaces come out close enough together to read as two, and there is
     no single set of percentages that is right for a ground of #ffffff and one
     of #073642. This is the knob for that, and it is one knob rather than four
     because the *ratios* between the rungs were chosen and only the distance
     was ever in question.

     Written onto the document element by applySurfaceLift() in styles.js. It
     has to be a multiplier inside each calc() rather than a rewritten set of
     values because a var() inside a :root declaration resolves against :root --
     setting it lower down would leave every surface at the value :root already
     computed. */
  --mmc-lift: 1;

  /* Surfaces, ground upward. Four steps, plus the one that floats: a popover,
     a modal and the picker are not on the page, they are over it, and they sit
     a little above the page's own ground so their edge reads without a border
     doing the work. */
  --mmc-bg: var(--mmc-ground);
  --mmc-float: color-mix(in oklab, var(--mmc-ground) calc(100% - 3% * var(--mmc-lift)), var(--mmc-ink));
  --mmc-surface: color-mix(in oklab, var(--mmc-ground) calc(100% - 6% * var(--mmc-lift)), var(--mmc-ink));
  --mmc-surface-2: color-mix(in oklab, var(--mmc-ground) calc(100% - 10% * var(--mmc-lift)), var(--mmc-ink));
  --mmc-surface-3: color-mix(in oklab, var(--mmc-ground) calc(100% - 14% * var(--mmc-lift)), var(--mmc-ink));

  /* Borders. The line family is translucent and belongs on top of a surface,
     where it has to let the surface through or a card on a card draws two
     greys; the edge family is opaque and belongs on a control that has to hold
     its own outline whatever it is standing on. */
  --mmc-line: color-mix(in srgb, var(--mmc-ink) 9%, transparent);
  --mmc-line-2: color-mix(in srgb, var(--mmc-ink) 18%, transparent);
  --mmc-line-3: color-mix(in srgb, var(--mmc-ink) 28%, transparent);
  --mmc-edge: color-mix(in oklab, var(--mmc-ground) calc(100% - 24% * var(--mmc-lift)), var(--mmc-ink));
  --mmc-edge-2: color-mix(in oklab, var(--mmc-ground) calc(100% - 43% * var(--mmc-lift)), var(--mmc-ink));

  /* Fills for a state rather than a surface -- hover, pressed, selected. Ink
     at an alpha rather than a step on the ramp, because the thing underneath
     is not always the same surface and a state has to read on all of them. */
  --mmc-tint: color-mix(in srgb, var(--mmc-ink) 2%, transparent);
  --mmc-wash: color-mix(in srgb, var(--mmc-ink) 6%, transparent);
  --mmc-wash-2: color-mix(in srgb, var(--mmc-ink) 12%, transparent);
  --mmc-wash-3: color-mix(in srgb, var(--mmc-ink) 22%, transparent);

  /* Text. Four weights, and the palette has a word for the middle two. */
  --mmc-strong: var(--mmc-ink);
  --mmc-text: var(--input-text);
  --mmc-dim: var(--descrip-text);
  --mmc-faint: color-mix(in oklab, var(--mmc-ground) 51%, var(--mmc-ink));
  --mmc-off: color-mix(in oklab, var(--mmc-ground) 66%, var(--mmc-ink));

  /* The inverse pair: a surface painted in the text colour, with the page's
     own ground written on it. This is what the primary button in the picker
     and the library is, and it is why that button cannot be a literal white --
     on a light palette a white button on a white sheet is not a button. */
  --mmc-on-ink: var(--bg-color);

  /* Scrims are the ground at an alpha, not black at an alpha. What is written
     on a scrim is --mmc-text, which follows the palette, so the scrim has to
     follow it too or a light palette puts dark words on a dark film. */
  --mmc-scrim: color-mix(in srgb, var(--mmc-ground) 50%, transparent);
  --mmc-scrim-2: color-mix(in srgb, var(--mmc-ground) 65%, transparent);
  --mmc-scrim-3: color-mix(in srgb, var(--mmc-ground) 85%, transparent);

  /* Shadows do not follow the palette and are not meant to. A shadow is the
     absence of light on whatever is behind it, and that is dark under a light
     theme as much as a dark one -- the frontend's own --bar-shadow is a black
     at three-quarters alpha in every palette it ships. Tokens all the same, so
     the depth of the pack is one decision rather than nine. */
  --mmc-shadow: color-mix(in srgb, black 55%, transparent);
  --mmc-shadow-soft: color-mix(in srgb, black 40%, transparent);

  /* The ground behind a picture or a video. Black in every palette, because a
     letterbox is not chrome: it is the part of the frame the picture did not
     reach, and anything lighter than the picture reads as a border on it. */
  --mmc-media-bg: black;
  /* The pack's own, and the only colour here chosen rather than derived. The
     amber is what the pack is recognised by; it does not move with the palette
     because it is not describing the palette. Its pair is the colour that goes
     on top of it -- fixed for the same reason, since what is legible on this
     amber does not depend on what the graph behind it is set to. */
  --mmc-accent: #f0a63c;
  --mmc-on-accent: #141414;

  /* The two states the palette has no word for. ComfyUI names an error colour
     in every palette, so --mmc-bad reads that one and matches the host's; it
     has no palette word for a warning, so the warn pair reaches into the
     semantic layer instead and only follows light and dark. --warning-background
     was the obvious candidate there and is not used: it is a gold, and a gold
     warning sitting beside this pack's amber accent is two accents. The coral
     the semantic layer calls destructive is the nearer match to the orange the
     pack has always warned in, and it is far enough from the accent to read. */
  --mmc-warn: color-mix(in oklab, var(--destructive-background) 70%, var(--mmc-ink));
  --mmc-bad: var(--error-text);
  --mmc-bad-solid: var(--destructive-background);
  --mmc-bad-solid-hover: var(--destructive-background-hover);
  /* Selection blue, worn by the trim bar and the segmented controls. Semantic
     layer again, for want of a palette word for it.

     Both of these are pulled toward ink rather than used as the semantic layer
     writes them, because over there they are the colour of a *button* and this
     pack wears them as words. --destructive-background is a coral dark enough
     to sit under white text, which on our own surface came out at a contrast
     of 2.1; the same colour mixed toward whatever the palette writes text in
     lands near 4.5 on a dark palette and near 5 on a light one, because the
     mix moves in whichever direction that palette's ink is. Same for the
     blue, which as the semantic layer ships it is a bright azure that
     disappears against Light's white. */
  --mmc-blue: color-mix(in oklab, var(--primary-background) 72%, var(--mmc-ink));
  /* How large the pack's text is drawn, as a multiplier on every size in it.
     1 is what every one of those sizes was written to be; the Appearance tab
     offers four points either side of it and settings.py will store any of them.

     A multiplier rather than a set of named sizes because the sizes were never
     a scale: fifteen distinct values across the pack, each chosen against the
     thing beside it, and collapsing them into six tokens would have thrown away
     the choices to gain a knob. Every "font-size: 13px" in styles/ is now
     "calc(13px * var(--mmc-type))" and means what it always did at 1.

     It lives on :root and not on .mmc-root for the reason the colours do —
     popovers and the picker portal to document.body — and it is written there
     by applyTextScale() in styles.js, off the settings the server holds. Only
     this pack's own rules read it, so nothing of ComfyUI's moves with it.

     What follows the text is what holds text: the pill and tile tokens below,
     and the fixed heights of the controls that carry a label (a 24px segment
     with 15px type in it is a segment with its own words hanging out). What
     does not follow is the room around them — the insets, the gaps, the
     picture. This is a text size, not a magnifier; the browser already has one
     of those on Cmd +. */
  --mmc-type: 1;
  /* One height for everything pill-shaped. A row that mixes a 38px control with
     a 32px one and a 23px readout reads as three unrelated things rather than
     as a row, and every one of those numbers was set locally by whoever added
     the control. Tokenised so the next one cannot be a fourth. */
  --mmc-pill-h: calc(38px * var(--mmc-type));
  /* The rail's tile, and everything positioned against it — the refiner's
     corner chevron is the one that kept drifting off the box when the shell
     drew a smaller square. One token, so the shell is a single override
     rather than a second set of offsets that has to be kept in step. */
  --mmc-tool-tile: calc(56px * var(--mmc-type));
  /* What a file lends a subject, as colour. Their looks are the default and
     wear none; these are the three departures from it, and they are worn by the
     shelf's badges and dots and by the library's editor tiles. Tokens rather
     than three literals per surface, because the surfaces disagree about
     cascade order and a caption that lost its colour to a later stylesheet is
     how that was found out. */
  --mmc-role-motion: #6ebeff;
  --mmc-role-voice: #a8c858;
  --mmc-role-replaces: var(--mmc-accent);
  /* Reference identity hues: one per attached asset, worn by its thumbnail
     ring, its handle in the bar, and its chip in the prompt, so a chip in the
     sentence can be matched to a picture without reading. Equal perceived
     lightness against each other, and chosen rather than derived for the reason
     the accent is: they identify an asset, they do not describe the palette.
     The amber zone is skipped so an asset never masquerades as the accent.
     Index comes from state.tagIndex(). */
  --mmc-tag-0: #5cb8f0;
  --mmc-tag-1: #63c98e;
  --mmc-tag-2: #9d95f5;
  --mmc-tag-3: #f07da0;
  --mmc-tag-4: #45c4c0;
  --mmc-tag-5: #f0906b;
  --mmc-tag-6: #d57de8;
  --mmc-tag-7: #a8c858;
}

/* The one thing the accent cannot do is stay exactly itself on a pale ground.
   Amber at #f0a63c is a mid-light colour: on every dark palette it carries a
   contrast of five to seven against the surface behind it, and on the Light
   palette it carries 1.8, which is not a colour a word can be written in. So on
   a light palette -- and only there -- the amber is taken down toward that
   palette's own ink until it holds, and what is written on top of it flips to
   the palette's ground. It is the same hue either way; what changes is how far
   down the ladder it sits, which is the only part of it the ground has a say in.

   ComfyUI puts .dark-theme on the document element for every palette whose
   light_theme flag is not set, which is all of them but Light, so the default
   here is the light correction and the class turns it back off. Written that
   way round because a palette someone builds themselves inherits the flag, and
   an unreadable accent is a worse thing to default to than a slightly deep one. */
:root:not(.dark-theme):not(.mmc-force-dark) {
  --mmc-accent: color-mix(in oklab, #f0a63c 62%, var(--mmc-ink));
  --mmc-on-accent: var(--mmc-ground);
}

/* The pack pinned to a dark ground -- the Appearance tab's "Dark in fullscreen",
   written onto the document element by applyTheme() in styles.js and only ever
   while the fullscreen shell is up.

   Only while the shell is up because a node body is part of a node, and ComfyUI
   draws the node around it in the host's own palette: pinning a body dark on a
   light desk does not give you a dark editor, it gives you a dark island in a
   white card. The shell covers the viewport and so has no host chrome left to
   disagree with. See applyTheme() for the whole of that reasoning.

   This is the one place a palette's colours are restated rather than read, and
   it is not a lapse: a ground that does not move is by definition one there is
   nothing to read it from. The values are ComfyUI's own Dark palette, so that
   pinning does not invent a second dark nobody chose. Only the tokens that read
   the palette are listed -- everything else on the ramp is a mix of these two
   and follows on its own.

   The accent pair is here as well, and has to be: the light correction below
   keys off ComfyUI's .dark-theme, and a light desk with the shell pinned dark is
   exactly the case where the host says light and this surface is not. The
   correction's :not() keeps it off the shell; these two put the brand amber and
   its dark text back. */
:root.mmc-force-dark {
  --mmc-ground: #171718;
  --mmc-ink: #fff;
  --mmc-text: #ddd;
  --mmc-dim: #999;
  --mmc-on-ink: #202020;
  --mmc-bad: #ff4444;
  --mmc-warn: color-mix(in oklab, #b33a3a 70%, var(--mmc-ink));
  --mmc-bad-solid: #b33a3a;
  --mmc-bad-solid-hover: #e04e48;
  --mmc-blue: color-mix(in oklab, #0b8ce9 72%, var(--mmc-ink));
  --mmc-accent: #f0a63c;
  --mmc-on-accent: #141414;
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
   positioned; see attach() in creator.js. */
.mmc-widget-host { height: 100%; }
.mmc-widget-host > * { height: 100%; }

/* The pre-stage's outer body. It holds whichever editor the architecture calls
   for and is swapped when that changes, so it has to be the full height the DOM
   widget gave it — the .mmc-root inside is what does the layout. */
.mmc-prestage-host { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.mmc-prestage-host > * { flex: 1 1 auto; min-height: 0; }

/* The waiting mark. One ring, drawn with a border and turned — no SVG, no image,
   and it works at whatever size the thing it sits in gives it, which is why the
   colour is currentColor and the size is an em. It appears wherever a press is
   in the air: on a bench's run row, on the refine pill, on a Render button, and
   on a preview that is holding while the queue is busy. */
@keyframes mmc-spin { to { transform: rotate(360deg); } }
.mmc-spin {
  display: inline-block; flex: none;
  width: 1em; height: 1em; box-sizing: border-box;
  border: 2px solid currentColor; border-top-color: transparent;
  border-radius: 50%; opacity: .8;
  animation: mmc-spin 700ms linear infinite;
}
/* A class selector beats the user agent's [hidden] rule, so the display above
   would keep the ring on screen for a button that hid it — which is exactly what
   the refine pill did: it spun from the moment the page loaded, on every tab,
   with nothing running. Anything that toggles the ring by attribute needs this
   line to exist. */
.mmc-spin[hidden] { display: none; }
/* A person who has asked not to see motion still has to be able to tell a
   button that is waiting from one that is not, so the ring stays and stops. */
@media (prefers-reduced-motion: reduce) {
  .mmc-spin { animation-duration: 0s; border-top-color: currentColor; opacity: .45; }
}

`;
