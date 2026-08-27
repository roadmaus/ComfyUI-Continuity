// The fullscreen editor's shell, its two views, and the caps it lifts off the
// body inside it.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- the shell ------------------------------------------------------------ */
/*
 * Fixed over everything, including ComfyUI's own chrome: this is a way of
 * working, not a panel docked into somebody else's layout. Below the pack's own
 * modals (1400 and up, see dom.js) because the picker, the preset library and
 * the LoRA sheets all open *from* here and have to land on top of it.
 */
.mmc-fs {
  position: fixed; inset: 0; z-index: 1200;
  display: flex; flex-direction: column;
  background: var(--mmc-bg); color: var(--mmc-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
}

/* Everything ComfyUI's menu used to hold that this still needs, which is less
   than it sounds: the piece's name, which view you are in, and the way back.
   Gallery and Settings are already in the body's rail and are not repeated. */
.mmc-fs-bar {
  flex: none; min-height: 54px; display: flex; align-items: center; gap: 12px;
  padding: 0 18px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-fs-mark {
  display: flex; align-items: center; gap: 9px;
  font-size: calc(13px * var(--mmc-type)); font-weight: 600; letter-spacing: .01em;
  /* A button now — it drops the destinations — but it reads as the wordmark it
     always was until pointed at. The caret is the standing hint. */
  background: none; border: 0; cursor: pointer; padding: 5px 8px; margin-left: -8px;
  border-radius: 10px; color: var(--mmc-text); font-family: inherit;
}
.mmc-fs-mark:hover { background: var(--mmc-surface); }
.mmc-fs-caret { display: flex; }
/* Both classes, or the accent rule two lines down wins the tie and the caret
   comes out amber — it is a hint, not the accent. */
.mmc-fs-mark .mmc-fs-caret svg { stroke: var(--mmc-off); }
.mmc-fs-mark:hover .mmc-fs-caret svg { stroke: var(--mmc-dim); }
/* The mark is artwork, not a glyph — it brings its own fills and its own
   ground — so it is exempt from the stroke rule the rest of the bar's icons
   take. Clipped rather than trusted to its own rounded rect: a tile with a
   1px light seam along one edge is what an un-antialiased corner looks like. */
.mmc-fs-logo {
  display: flex; flex: none; width: 22px; height: 22px;
  border-radius: 7px; overflow: hidden;
}
.mmc-fs-mark svg { stroke: var(--mmc-accent); fill: none; stroke-width: 1.6; }
.mmc-fs-logo svg { stroke: none; fill: initial; stroke-width: initial; display: block; }
.mmc-fs-slash { color: var(--mmc-off); }
/* Which family the piece renders with. The one thing in the bar that changes
   while you work, so it reads a step brighter than the node's name behind it. */
.mmc-fs-family {
  font-size: calc(13px * var(--mmc-type)); color: var(--mmc-text);
}
/* The node's title, which is the piece's name — see fullscreen.js on why this
   pack does not store a second one, and why the group is hidden until there
   is one. */
.mmc-fs-piece-group { display: none; align-items: center; gap: 8px; }
.mmc-fs-piece-group.on { display: flex; }
.mmc-fs-piece { font-size: calc(13px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-fs-gap { flex: 1; }

/* Simple or Full, as one control rather than two: they are two answers to one
   question, and a pair of loose buttons would have read as two features. */
.mmc-fs-views {
  display: flex; padding: 2px; gap: 2px; border-radius: 14px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
}
.mmc-fs-view {
  height: calc(24px * var(--mmc-type)); padding: 0 13px; border-radius: 12px; border: 0; background: none;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12px * var(--mmc-type)); cursor: pointer;
}
.mmc-fs-view:hover { color: var(--mmc-text); }
.mmc-fs-view[aria-pressed="true"] { background: var(--mmc-surface-3); color: var(--mmc-text); }
.mmc-fs-view:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }

.mmc-fs-exit {
  display: flex; align-items: center; gap: 7px; height: calc(30px * var(--mmc-type)); padding: 0 11px;
  border-radius: 15px; background: none; border: 1px solid transparent;
  color: var(--mmc-dim); font-size: calc(12px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-fs-exit:hover { background: var(--mmc-surface-2); border-color: var(--mmc-line); color: var(--mmc-text); }
.mmc-fs-exit svg { stroke: currentColor; fill: none; stroke-width: 1.6; }

/* --- the desk ------------------------------------------------------------- */
/*
 * Three regions used to be three stripes, divided edge to edge by hairlines and
 * all weighted the same — a window with no place to start reading. They are
 * cards on a ground now, and only one of them is raised: the shot you are
 * writing. The pre-stage is upstream of it and the picture is downstream, and
 * both sit *on* the ground rather than beside the work as equals.
 */
.mmc-fs-body {
  flex: 1; display: flex; justify-content: center;
  min-height: 0; gap: 14px; padding: 14px;
  /* Panned rather than clipped once even the floors do not fit. */
  overflow: auto hidden;
  /* Cards on a ground, centred on it — the same thing the simple view does with
     one card, done with three regions. Stretched to the window they were three
     columns of controls with a few hundred pixels of nothing distributed
     somewhere inside each: into the writing well, which made it a black box the
     height of the screen, or under the last row, which made it a hole above
     Render. Neither is a place for slack. Sized to their contents and centred,
     the slack is the ground the cards sit on and it reads as room rather than as
     something missing. */
  align-items: center;
}

/* The desk: the pre-stage card and the shot card, as one object on the ground.
 *
 * It exists for their height. Beside the reel they were three siblings on a
 * centred line, and a centred line gives every card the height of its own
 * contents — so the step before the shot ended somewhere up the side of the
 * shot, two cards of different lengths with no shared edge, which is what made
 * the desk read as debris rather than as a row. Stretching them against the
 * body would have been worse: the body is the window, so both cards would run
 * its full height with the slack falling inside them, under Render.
 *
 * Wrapped, the line they stretch against is this one, and it is only as tall as
 * the taller of them. Same top, same bottom, and the shorter card carries the
 * difference as room at its foot rather than as a ragged edge.
 */
.mmc-fs-desk {
  display: flex; align-items: stretch; gap: 14px;
  flex: 0 1 auto; min-width: 0; min-height: 0; max-height: 100%;
}
/* And the difference goes above the button, not below it. Both cards end in the
   one thing that runs them, so on a shared bottom edge the two buttons are a
   line — slack left under the shorter one would have hung its Render still in
   the middle of a card with a hole beneath it. */
.mmc-fs:not(.simple) .mmc-fs-runrow { margin-top: auto; }

/* The column the body lives in. A measure rather than a share of the window: a
   prompt line that runs the full width of a 32-inch screen is a prompt nobody
   can read back. Wider than it was, because a rail of eleven labelled tools and
   a row of pills were being wrapped into three rows to leave room for a dock
   that, before the first render, has one rectangle in it. */
.mmc-fs-col {
  width: clamp(600px, 40vw, 820px); display: flex; flex-direction: column;
  /* Shrinkable, down to a floor. The measure is what the column wants; on a
     window with no room for all three regions at once it is the picture that was
     paying for it, squeezed to a thumbnail beside two cards at full size. */
  flex: 0 1 auto; min-width: 500px;
  min-height: 0; max-height: 100%; border-radius: 22px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
}
/* The wrapper between the card and the body it is showing. It exists so the
   step change has something stable to turn — the body itself is replaced by the
   swap — and it is otherwise nothing: a column the same shape as the one it
   replaced in the layout. See turnTo() in fullscreen.js. */
.mmc-fs-face { display: flex; flex-direction: column; flex: 0 1 auto; min-height: 0; }
/* As tall as the body in it, up to the height of the window — past that the body
   scrolls inside the card (see the overflow rule below) and Render, which is not
   part of it, stays where it is. */
.mmc-fs-face > .mmc-root { flex: 0 1 auto; min-height: 0; }
/* The card's inset. On the body that draws the furniture, never on the wrapper
   around it: a Creator's body is a .mmc-root.hosting whose only job is to hold
   the shot's own .mmc-root, and padding put on both is the inset twice. */
.mmc-fs .mmc-root:not(.hosting) { padding: 16px 16px 6px; }

/* The PreStage's column, absent unless one is paired and the desk is showing.
   Narrower than the Creator's because the node is — four tools, a prompt, a
   checkpoint.

   A card, like the shot's, and that is the change: its rail, its writing well,
   its pills and its sampler row used to sit loose on the ground with nothing
   round them, so the desk opened on four unrelated groups of controls to the
   left of a card rather than on one step before another. Unraised — the ground
   colour with an edge, where the shot is lifted onto a surface — because it is
   still the step before this one and must not read as its equal. */
.mmc-fs-pre {
  display: none; width: clamp(360px, 24vw, 460px); flex-direction: column;
  flex: 0 1 auto; min-width: 340px;
  min-height: 0; max-height: 100%; border-radius: 22px;
  background: var(--mmc-tint); border: 1px solid var(--mmc-line);
}
.mmc-fs-pre.on { display: flex; }
.mmc-fs-pre > .mmc-prestage-host, .mmc-fs-pre > .mmc-root { flex: 0 1 auto; min-height: 0; }

/* --- what each column is -------------------------------------------------- */
/*
 * Both faces on the desk are built out of the same parts — the same rail, the
 * same writing well, the same pills — so the first thing the eye met on the
 * left was a second copy of the toolbar it was already reading on the right,
 * and nothing on screen said which node either belonged to. A name at the top
 * of each column is the whole fix, and it is the structure talking: left to
 * right the desk is pre-stage, then shot, then the picture they make.
 *
 * Set apart from the body under it rather than boxed: this labels a column, it
 * is not a control, and it must not read as the first row of the rail below.
 */
.mmc-fs-head {
  flex: none; padding: 15px 18px 3px;
  font-size: calc(11px * var(--mmc-type)); font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
  color: var(--mmc-off);
}
/* The simple view has one column and the step switch says what is in it. */
.mmc-fs.simple .mmc-fs-head { display: none; }
/* Quieter than the shot beside it, in the two ways a column can be quieter:
   smaller tools and less contrast. Nothing is hidden — this is still the node's
   whole face — it just stops competing for the eye. */
.mmc-fs-pre { --mmc-tool-tile: calc(42px * var(--mmc-type)); }
.mmc-fs-pre .mmc-tool-icon { border-radius: 11px; }
.mmc-fs-pre .mmc-tool { font-size: calc(11px * var(--mmc-type)); }
.mmc-fs-pre .mmc-tool svg { width: 18px; height: 18px; }
.mmc-fs-pre .mmc-root { opacity: .82; transition: opacity .15s ease; }
.mmc-fs-pre:hover .mmc-root, .mmc-fs-pre:focus-within .mmc-root { opacity: 1; }

/* --- which half of the pair the card is showing --------------------------- */
/*
 * Tabs at the top of the card, and only in the simple view, where the pre-stage
 * is a step rather than a column. The bar's Simple/Full switch is about the
 * window; this is about the work, so it lives on the thing the work is in.
 *
 * The same segmented shape as that switch, deliberately: both answer "which of
 * two", and giving them two different shapes would have made the reader learn
 * the control twice. Wider, because it is the card's own heading rather than a
 * corner of the chrome.
 */
.mmc-fs-stepbar {
  flex: none; display: flex; gap: 2px; padding: 2px; align-self: center;
  border-radius: 15px; background: var(--mmc-bg); border: 1px solid var(--mmc-line);
  position: relative;
}
.mmc-fs-step {
  height: calc(26px * var(--mmc-type)); padding: 0 18px; border-radius: 13px; border: 0; background: none;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12px * var(--mmc-type)); cursor: pointer;
  position: relative;   /* over the ink, which is painted behind the words */
}
.mmc-fs-step:hover { color: var(--mmc-text); }
.mmc-fs-step[aria-pressed="true"] { color: var(--mmc-text); }
/*
 * The lit segment, travelling. It used to be a background on whichever button
 * was pressed, which meant the switch had no motion of its own: the card was
 * replaced and the highlight was somewhere else, two changes in the same frame
 * with nothing joining them. One element that slides is the join — and it is
 * the only thing on the card that survives the switch, so it is what the eye
 * holds on to while everything under it is dealt back in.
 *
 * Sized and placed from fullscreen.js rather than in fractions: the segments
 * are the width of their own words, and those words are translated.
 */
.mmc-fs-step-ink {
  position: absolute; top: 2px; bottom: 2px; left: 0; width: 0;
  border-radius: 13px; background: var(--mmc-surface-3); pointer-events: none;
}
/* Only once it has been placed. A pill that slid in from the left edge on open
   would announce a switch nobody made. */
.mmc-fs-step-ink.travels {
  transition: transform .3s cubic-bezier(.32, .72, 0, 1),
              width .3s cubic-bezier(.32, .72, 0, 1);
}
@media (prefers-reduced-motion: reduce) {
  .mmc-fs-step-ink.travels { transition: none; }
}
.mmc-fs-step:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
/* A segment holds its name and nothing else. It carried an × that took the
   pre-stage back out of the graph, on the grounds that the step you are standing
   on is the safe place for it; the safer reading is that a switch switches. In
   this view you are on one step or the other, and removing the node is the
   desk's — the toggle in the shot's own row, which the desk still draws. */
.mmc-fs-step { display: flex; align-items: center; }

/* The way in, inside. Both faces grow a control that opens the shell — the rail
   tile on a shot, the pill on a strip — and in here the same door is already in
   the corner, saying "Back to the graph" from the other side. */
.mmc-fs .mmc-tool-expand, .mmc-fs .mmc-fs-enter { display: none; }

/* The pill that used to spawn and remove the pre-stage, in the shot's own row.
   The switch above does both now, and a second control over one node was a
   second place to look for it. Still drawn on the desk, which has no switch. */
.mmc-fs.simple .mmc-prestage-toggle { display: none; }
/* The desk shows both halves at once and has no step to be on, so the switch is
   hidden there by fullscreen.js rather than by a rule here — but the card still
   has to close the gap it left. */
.mmc-fs.simple .mmc-fs-col > .mmc-fs-stepbar { margin-bottom: 14px; }

/* --- the writing well ----------------------------------------------------- */
/*
 * The one recessed surface in the room. Everything else in the shell is raised
 * off the ground; the box you type into is cut into it, so the eye lands there
 * first without anything having to be coloured or outlined to say so. It is the
 * same panel the node face draws — only the elevation is reversed.
 */
.mmc-fs .mmc-panel {
  background: var(--mmc-bg);
  border-color: var(--mmc-scrim-2);
  box-shadow: inset 0 1px 2px var(--mmc-shadow);
  padding: 16px;
}
/* A page rather than a field: this is the one surface in the pack that holds
   paragraphs, and on a screen it can afford the measure to show them.

   The node's ten-line cap comes off at the foot of this file, with the other
   bounds a face needs and a window does not. */
.mmc-fs .mmc-prompt { font-size: calc(16px * var(--mmc-type)); line-height: 1.62; }

/* A page to start on, and no more. The well used to be whatever was left of a
   full-height column, which on a desk-sized screen is five hundred pixels of
   empty box with a placeholder in one corner of it. This is a writing surface
   with room for a paragraph; it grows with what is typed into it, up to the cap
   at the foot of this file, and the card grows with it. */
.mmc-fs:not(.simple) .mmc-panel { flex: none; }
.mmc-fs:not(.simple) .mmc-prompt { min-height: 220px; }
/* And once the card outgrows the window — a cast, a shelf of references and a
   long prompt will — the body scrolls inside it rather than being cut off by the
   overflow the node face needs. Render is outside the body, so it stays put. */
.mmc-fs:not(.simple) .mmc-root:not(.hosting) { overflow-y: auto; }

/* Smaller tiles than the node face draws. On a node the rail is most of the
   width and 56px is the only size that reads; in a column with a picture beside
   it, eleven of them wrapped to a second row and the shelf of tools became the
   tallest thing above the writing. */
.mmc-fs { --mmc-tool-tile: calc(48px * var(--mmc-type)); }
.mmc-fs .mmc-tool-icon { border-radius: 13px; }
.mmc-fs .mmc-tool svg { width: 20px; height: 20px; }
/*
 * Eleven labelled tools do not fit a column narrow enough to read a prompt back
 * in, so the rail wraps here whatever the tile size — and everything that went
 * wrong with it went wrong in the wrapping.
 *
 * It is a grid, not a wrapping row. Two things follow, and both were the bug.
 * The track is fixed, so the tools sit on one set of columns instead of each
 * row spacing its own contents out to whatever it happened to hold — a row of
 * eight and a row of three, spread by a gap, share no vertical line at all.
 * And the clusters are set to display:contents, so the rail wraps by tool rather
 * than by cluster: the machine's three used to be one unbreakable block that
 * fell to a line of its own the moment the column narrowed, leaving a hole
 * across the end of the row above it.
 *
 * The track is a column rather than a tile with a gap beside it, because the
 * tile is the narrowest part of a tool: "Add image" is half again as wide as
 * the square above it, so a gap that looked right under the icons left the
 * labels a hair apart and the row read as one run of prose with pictures over
 * it. A column wide enough for the words spaces the words; the squares inside
 * it keep an even rhythm on their own.
 */
.mmc-fs .mmc-rail {
  display: grid; grid-template-columns: repeat(auto-fill, calc(76px * var(--mmc-type)));
  gap: 14px 0; justify-content: start; align-items: start;
}
.mmc-fs .mmc-rail-group { display: contents; margin-left: 0; }
.mmc-fs .mmc-tool { width: 100%; line-height: 1.25; text-align: center; }

/* And the same is true of the row under the prompt. A pill row on a node face
   ends with the route badge held against the far edge, because a face is wide,
   the row is one line, and the badge is what the line ends with. A column is
   neither: every row in here wraps, and an auto margin on a wrapped line pushes
   whatever landed on it to the right — which is a card with a tidy left edge, a
   hole in the middle of its last row, and one lit readout out on its own against
   the right-hand rule. Flowing left, the row reads as one paragraph of controls.
   The simple view centres the same row instead; see its own section. */
.mmc-fs .mmc-pills-tail { margin-left: 0; }

/* The sampler's numbers, ruled off from the shot's. Same pills, same colours;
   what was missing was the line saying that everything below it describes how
   this is run rather than what is in it — which is most of why a dozen chips in
   one heap read as noise. */
.mmc-fs .mmc-sampling-host {
  border-top: 1px solid var(--mmc-line); padding-top: 12px;
}

/* Lit chips, calmed. On a node face two or three are on at once and the tinted
   fill is what makes them findable; across a whole window there are a dozen,
   and a dozen tinted fills is confetti. The state keeps its colour, in the text
   and the border where a state belongs, and the fill goes back to being a
   surface — so the only saturated area left in the room is Render. */
.mmc-fs .mmc-pill-seg[aria-pressed="true"], .mmc-fs .mmc-pill-seg.accel-on {
  background: var(--mmc-surface-3);
}

/* --- the picture region: the plate, and the lip under it ------------------- */
/*
 * Two parts that do not share an axis, which is the whole of the fix.
 *
 * They used to. One scrolling column held every finished render *and* the live
 * stage, so where the live picture sat was a function of how many renders there
 * had been: centred while the column was empty, pushed to the floor by the first
 * take, further down with every one after it. Two rules did it —
 * ".mmc-fs-past:empty + .mmc-fs-dock { margin: auto 0 }" and an auto margin on
 * the oldest take — and no amount of tuning fixes that while history and the
 * picture are stacked on one axis.
 *
 * So: the reel takes the whole height and centres what is in it, unconditionally,
 * and history runs left to right along a shelf beneath the *window* — under the
 * card as much as under the picture. Spanning both is what keeps them level: a
 * lip inside the picture's own column takes its height out of the picture and
 * not out of the writing, and the two then sit half a lip apart for as long as
 * there is any history at all. The live picture now sits level with the card
 * beside it on the first press and on the tenth.
 *
 * Nothing is copied onto the lip: an entry points at the same file the gallery
 * opens, so closing the editor loses the list and no render.
 */
.mmc-fs-reel {
  /* A floor, so the picture is never the region that gives everything up: the
     cards shrink to their own floors first. Below the width where all three
     floors fit, the desk pans — a window that narrow wants the simple view. */
  flex: 1 1 0; min-width: 260px; min-height: 0; max-width: 860px;
  /* The one region that still takes the whole height: the cards are as tall as
     their controls, a picture is as tall as there is room for. */
  align-self: stretch;
  display: flex; align-items: center; justify-content: center;
  padding: 10px; min-width: 0;
}

/*
 * The shelf: every render this editor has finished, under the whole window.
 *
 * Reserved for the whole of "working" rather than grown on the second take — a
 * shelf that arrived when the first render retired would move everything above
 * it, which is the thing all of this is here to stop. It is empty for exactly
 * one render, and while it is empty it is a hairline and a little air, not a box.
 */
/* Everything under the bar, and the box the dashboard covers. It is only a
   position: the two regions inside it lay out exactly as they did when they
   were the shell's own children — see fullscreen.js on why the dashboard
   covers the room rather than replacing it. */
.mmc-fs-room {
  position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column;
}

.mmc-fs-strip {
  flex: none; height: var(--mmc-fs-lip, 104px); box-sizing: border-box;
  display: flex; align-items: center; gap: 10px;
  padding: 10px 18px; border-top: 1px solid var(--mmc-line);
  overflow-x: auto; overflow-y: hidden;
  scrollbar-width: thin;
}
/* The takes are the lip's own children for layout — a wrapper between them and
   the row would have to re-declare the whole of it. */
.mmc-fs-strip-run { display: contents; }
/* Before the first press there is nothing to have a history of, and a hairline
   across the bottom of an empty region with nothing under it is the void this
   pack keeps refusing to draw. It arrives with "working" — the same moment the
   region stops being an outline and starts being a picture — and from then on
   it is reserved whether or not anything has retired into it. */
.mmc-fs:not(.working) .mmc-fs-strip { display: none; }

/* A cell the height of the lip and no wider than what is in it. The media takes
   its height from the row and its width from its own aspect, and the cell hugs
   that — so a portrait take is a narrow frame beside a wide one rather than a
   wide frame with a picture stranded in the middle of it, which is what a cell
   sized off the file's intrinsic width gives you.

   A button, because the whole cell is the press: the thumbnail carries no
   transport of its own (see take() in fullscreen.js) and the one thing it does
   is go up on the picture. Everything below undoes what a <button> assumes —
   its padding, its own background, its font — and none of the geometry above
   changed with it. */
.mmc-fs-take {
  position: relative; flex: none; display: flex; height: 100%;
  border-radius: 10px; overflow: hidden;
  background: var(--mmc-media-bg); border: 1px solid var(--mmc-line);
  padding: 0; margin: 0; font: inherit; color: inherit; cursor: pointer;
  transition: border-color 140ms ease, opacity 200ms ease;
}
.mmc-fs-take:hover { border-color: var(--mmc-line-3); }
.mmc-fs-take:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
/* The cell of the take that is currently on the picture. It keeps its width —
   a lip that reflowed when a take was picked up would move every other take out
   from under the pointer — and gives up its picture, because the picture is
   somewhere else. The accent is the same one the sampling step count uses: it
   means "this one", here as there. */
.mmc-fs-take.up { border-color: var(--mmc-accent); }
.mmc-fs-take.up .mmc-fs-take-media { opacity: .22; }
.mmc-fs-take.up .mmc-fs-take-note { opacity: .5; }
@media (prefers-reduced-motion: reduce) {
  .mmc-fs-take, .mmc-fs-take-media { transition: none; }
}
/* Sized off the lip rather than off the window, so every take is the same height
   whatever shape it is and the row reads as a strip of frames. Smaller than the
   live one, and that is the hierarchy: the plate is the answer to what you just
   queued and these are what it is being compared against. */
.mmc-fs-take-media {
  display: block; height: 100%; width: auto; max-width: 320px;
  object-fit: contain; transition: opacity 200ms ease;
}
/* What it cost, on the frame rather than under it: a caption line would have
   been a row of numbers reading as a second strip. The filename went to the
   tooltip — along a lip of thumbnails it was the same truncated stem eight
   times over, which identifies nothing. */
.mmc-fs-take-note {
  position: absolute; left: 5px; bottom: 4px;
  font-size: calc(10px * var(--mmc-type)); color: var(--mmc-text); font-variant-numeric: tabular-nums;
  background: var(--mmc-scrim-2); border-radius: 999px; padding: 1px 6px;
}
.mmc-fs-take-note:empty { display: none; }

/* --- where the newest picture lands --------------------------------------- */
/*
 * The still keeps the floating card's rule — display:none until the satellite
 * says there is something to show. The dock does not: hidden, it left the
 * piece's column pinned to the left edge with a border ending in mid-air. It is
 * always here, and holds the frame the piece is about to make until there is a
 * picture to put in it.
 *
 * Stretched to the plate rather than hugging its contents, so it is a definite
 * box: the picture's own maxima are percentages of it, and a percentage against
 * an auto height resolves to nothing at all. What hugs the picture is the stage
 * inside, which is where the grip hangs.
 */
.mmc-fs-dock {
  display: flex; flex: 1 1 auto; min-width: 0; min-height: 0; align-self: stretch;
  align-items: center; justify-content: center;
  /* And the ground a reviewed take stands on: the layer is inset to this box
     because this box is the plate, whatever is currently in it. */
  position: relative;
  /* And it is the box the card measures itself against: cqw/cqh below are this
     element's, which is the only way to say "as large as fits in both axes"
     when the two bounds live on different percentage bases. Size containment is
     free here — the dock is stretched by its column and never took its size
     from its contents anyway. */
  container-type: size;
}
.mmc-fs-still { display: none; }
.mmc-fs-still.showing { display: flex; flex: none; padding: 14px 14px 0; }
/* Docked, the stage is sized by its column rather than scaled with the canvas.
   The card's own rules size the media off its *height* alone — right on a
   satellite, whose height is the node's and whose width the picture decides,
   and wrong in a column, where a landscape render scaled to the full height is
   wider than the column and the card's overflow:hidden cuts its sides off.
   Here the media is contained by both edges and the card takes its *shape* from
   what is inside it — its shape, and no longer its size. It used to take both,
   which is a different rule that agreed with this one for as long as every
   picture was bigger than the dock: width auto against a contained image is the
   image's own pixels, and a latent2rgb preview is the latent, 30x17 on an LTX
   canvas. The full-size frame the dock holds until a picture lands would hand
   over to a postage stamp adrift in the middle of the column.

   Both maxima carry the plate scale, which is what the corner grip sets: one
   number, applied to the box rather than to the element, so the picture keeps
   its aspect and stays centred while it changes size. */
/* One room, one elevation. The plate carried "0 8px 30px" — a shadow written for
   a card floating over the canvas at graph scale — while the writing card beside
   it carries "0 24px 64px", so the two objects in the window sat at two
   different heights above the same ground. Matched, and a radius to go with it:
   the picture and the card are the pair this view is made of. */
.mmc-fs-dock .mmc-stage {
  max-width: calc(100% * var(--mmc-plate-scale, 1));
  max-height: calc(100% * var(--mmc-plate-scale, 1));
  width: auto; height: auto;
  /* The shape of what is in it, measured off the media and handed over by
     Stage.setAspect — see there for why CSS cannot work this out for itself.
     Without it a portrait render sat in the middle of a card as wide as the
     file, letterboxed by its own frame. "auto" until the media has loaded,
     which is the same thing as no constraint. */
  aspect-ratio: var(--mmc-media-ar, auto);
  /* The 240px floor is the card's answer to having no media at all — an error
     is a chip of text in an otherwise empty box — and it is the wrong answer for
     a narrow portrait render, which has media and a shape of its own. */
  min-width: 0;
  border-radius: 18px; box-shadow: 0 24px 64px var(--mmc-shadow-soft);
}
/* Once the media has been measured, the card is the largest box of that shape
   the dock will hold: the width it wants is the column's, unless the height that
   implies is taller than the column, in which case the height decides and the
   width follows it. That is the arithmetic the ratio alone cannot do, which is
   why Stage.setAspect hands over the number as well. Both bounds carry the plate
   scale — the grip's one number — and the maxima above stay as the guard for the
   moment between the picture arriving and being measured. */
.mmc-fs-dock .mmc-stage[data-sized] {
  width: min(calc(100cqw * var(--mmc-plate-scale, 1)),
             calc(100cqh * var(--mmc-plate-scale, 1) * var(--mmc-media-arn, 1)));
  height: auto;
}
.mmc-fs-dock .mmc-stage[data-state="failed"] { min-width: 240px; }
.mmc-fs-still .mmc-stage { max-width: 100%; max-height: 66vh; }

/* --- an earlier take, on the picture --------------------------------------- */
/*
 * A layer over the plate rather than a picture written into it.
 *
 * The stage owns the render that is happening and redraws itself on every frame
 * the sampler sends, so an older file handed to it is a picture the next preview
 * erases — and a run to put back afterwards. In front of it there is nothing to
 * put back: the sampler goes on sampling underneath, at full speed, and pressing
 * a take mid-render costs that render nothing. That is why there is no rule here
 * about being busy. There was never a case to write.
 *
 * It fills the dock and swallows the pointer, which is deliberate on both counts.
 * A layer that let clicks through would put the scrub bar of a video you cannot
 * see under the picture you can, and the room around the card is the way out —
 * so every part of this box has a job.
 */
.mmc-fs-review {
  /* Over the size grip as well as over the picture: the grip sizes the plate,
     and while the plate is lent out there is nothing under the corner to size. */
  position: absolute; inset: 0; z-index: 3;
  display: flex; align-items: center; justify-content: center;
  /* The room dims on its own clock; the take crosses it. Two movements, because
     they are two things: where you are, and what you are looking at. */
  background: transparent; transition: background-color 220ms ease;
}
.mmc-fs-review.lit { background: var(--mmc-scrim-2); }

/* The same box the docked stage is, by the same arithmetic and off the same
   plate scale — a take on the picture has to stand exactly where the picture
   stands, or the flight lands somewhere the eye has to re-find. Its own
   custom properties rather than the stage's: both are on screen at once and
   the one underneath is still describing its own render. */
.mmc-fs-review-card {
  position: relative; display: block; overflow: hidden;
  max-width: calc(100% * var(--mmc-plate-scale, 1));
  max-height: calc(100% * var(--mmc-plate-scale, 1));
  width: auto; height: auto;
  aspect-ratio: var(--mmc-review-ar, auto);
  background: var(--mmc-media-bg);
  border-radius: 18px; box-shadow: 0 24px 64px var(--mmc-shadow-soft);
  /* The one thing that says this is not the live plate, and it is a hairline:
     the label in the corner does the saying, and the flight already did. */
  outline: 1px solid color-mix(in srgb, var(--mmc-accent) 45%, transparent);
  outline-offset: -1px;
}
.mmc-fs-review-card[data-sized] {
  width: min(calc(100cqw * var(--mmc-plate-scale, 1)),
             calc(100cqh * var(--mmc-plate-scale, 1) * var(--mmc-review-arn, 1)));
  height: auto;
}
/* Held back until the shape is known — the moment between the element existing
   and its aspect being measured is the moment it is at the file's own pixel
   size, and a 896-wide frame flashing at full size inside a 500-wide plate is
   the flicker this hides. The card itself stays visible throughout, so the way
   back is on screen even if the file never loads at all. */
.mmc-fs-review-media {
  display: block; width: 100%; height: 100%; object-fit: contain;
  opacity: 0; transition: opacity 120ms ease;
}
.mmc-fs-review-card[data-sized] .mmc-fs-review-media { opacity: 1; }

/* In the readout's left slot, where the stage puts Gallery — and opting back
   into the pointer the row gives up, exactly as that button does. */
.mmc-fs-review-back {
  pointer-events: auto; cursor: pointer; font: inherit;
  display: inline-flex; align-items: center; gap: 5px;
  color: var(--mmc-accent);
  border-color: color-mix(in srgb, var(--mmc-accent) 35%, transparent);
}
.mmc-fs-review-back:hover { background: var(--mmc-scrim-3); }
.mmc-fs-review-back:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }

@media (prefers-reduced-motion: reduce) {
  .mmc-fs-review, .mmc-fs-review-media { transition: none; }
}
/* The card used to carry flex-direction but never display:flex, and this is
   where the flex was put back on — which read as a fact about being docked and
   was not one. A row with an auto height is a height no percentage can resolve
   against wherever it is: on the satellite too the media went to its intrinsic
   size, which nobody saw while the only preview there was decoded at roughly the
   render's shape, and which put a 30x17 latent2rgb frame in the corner of a
   full-height card the moment a second family had no taeh to decode through.
   The card carries the display itself now (styles/stage.js). */
/* And the row may be narrower than what is in it. A flex item's automatic
   minimum size is its own intrinsic width, so a 1024-wide render simply refused
   to shrink into a narrower column however the card above it was clamped — and
   the side that went over the edge was the side that got cut. */
/* Centred, because the card keeps a 240px floor for the case it was given — an
   error is a chip of text in an otherwise empty box — and a narrow portrait
   render is under it. Letterboxed on both sides reads as letterboxing; all of
   it on one side reads as a picture that slipped. */
.mmc-fs-dock .mmc-stage-media, .mmc-fs-still .mmc-stage-media {
  min-width: 0; justify-content: center;
}
/* The card is now the picture's own shape, so the media fills it exactly.
   "contain" is the guard for the moment before the aspect has been measured and
   for the odd file that reports one size and decodes at another. */
.mmc-fs-dock .mmc-stage-img, .mmc-fs-dock .mmc-stage-video {
  width: 100%; height: 100%; min-width: 0; object-fit: contain;
}

/* --- the grip ------------------------------------------------------------- */
/*
 * How big the picture is drawn, said by dragging its corner.
 *
 * The top right, and not the bottom: the bottom edge of a render is spoken for
 * three times over — the progress rule, the readout with its clock, and a
 * finished clip's own transport — and a handle you have to reach around a scrub
 * bar for is a handle nobody uses twice.
 *
 * This is the one object in the window with glass in it, and that is deliberate:
 * everything else here is matte, so the single blurred thing reads as a control
 * rather than as a theme. Absent until the pointer is on the picture or the
 * button has focus, because a picture you are judging should have nothing on it.
 */
.mmc-fs-sizer {
  position: absolute; top: 10px; right: 10px; z-index: 2;
  display: flex; align-items: center; gap: 6px;
  opacity: 0; transition: opacity .18s ease;
}
.mmc-stage:hover .mmc-fs-sizer,
.mmc-fs-sizer:focus-within, .mmc-fs-sizer.dragging { opacity: 1; }
.mmc-fs-grip {
  flex: none; display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; padding: 0; border-radius: 9px;
  background: var(--mmc-wash-2); border: 1px solid var(--mmc-line-2);
  -webkit-backdrop-filter: blur(14px) saturate(1.4);
  backdrop-filter: blur(14px) saturate(1.4);
  color: var(--mmc-strong); cursor: nesw-resize; pointer-events: auto;
  /* A drag on this is a resize, not a scroll and not a pan. */
  touch-action: none;
  transition: background .18s ease, transform .18s cubic-bezier(.4,0,.2,1);
}
.mmc-fs-grip svg { stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-fs-grip:hover { background: var(--mmc-wash-3); }
.mmc-fs-grip:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-fs-sizer.dragging .mmc-fs-grip { transform: scale(1.12); background: var(--mmc-wash-3); }
/* The reading, and only while the drag is on: a permanent percentage in the
   corner of every render would be a number nobody asked for. It is a stage chip
   because it is one — the row along the bottom already established what a small
   fact on a picture looks like here. */
.mmc-fs-size { opacity: 0; transition: opacity .12s ease; }
.mmc-fs-sizer.dragging .mmc-fs-size { opacity: 1; }
@media (prefers-reduced-motion: reduce) {
  .mmc-fs-sizer, .mmc-fs-grip, .mmc-fs-size { transition: none; }
  .mmc-fs-sizer.dragging .mmc-fs-grip { transform: none; }
}

/* --- the frame, before there is a picture --------------------------------- */
/*
 * The canvas the piece will render at, drawn at its own ratio with its size and
 * length under it. It is the dock's resting state: it goes when the stage has
 * something to show and comes back when the piece is cleared, and because it
 * stands where the picture will stand, the first render does not move the room
 * around it.
 */
.mmc-fs-frame {
  flex: 1; min-width: 0; min-height: 0; align-self: stretch;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 14px; padding: 8px;
}
.mmc-fs-dock.showing .mmc-fs-frame { display: none; }
/* An <svg> because it is the one box CSS will not contain: an element given
   both a width and a height ignores its aspect-ratio, while preserveAspectRatio
   letterboxes exactly as the media that replaces it does. */
/* Sized the way an <img> is: the width and height attributes give it an
   intrinsic size, and the two maxima shrink it to the dock keeping the ratio.
   Without them the element would take the whole column and letterbox *inside*
   itself, which puts the caption a long way from the frame it captions. */
/* Filled, faintly, and not only stroked: a 1px hairline at a faint alpha
   across a third of a large screen is a line you have to go looking for, and a
   dock that reads as empty is the thing this element exists to prevent. The
   fill is what carries the shape at any size; the stroke only edges it. */
/* Carrying the plate scale too: the frame's whole job is to stand where the
   picture will stand, and an outline at full size in front of a plate set to
   60% would be promising a render twice the size of the one that lands. */
.mmc-fs-frame-box {
  flex: 0 1 auto; min-height: 0; width: auto; height: auto;
  max-width: calc(100% * var(--mmc-plate-scale, 1));
  max-height: calc(100% * var(--mmc-plate-scale, 1));
  fill: var(--mmc-tint); stroke: var(--mmc-line-2); stroke-width: 1;
}
.mmc-fs-frame-note {
  flex: none; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
  letter-spacing: .05em; font-variant-numeric: tabular-nums;
}
/* The running halo is a LiteGraph impression — a 3px stroke placed to match the
   outline core paints around the executing node. There is no node behind this
   to match, so it would just be a black ring on a black screen. The accent rule
   along the picture's bottom edge is what says a render is going. */
.mmc-fs .mmc-stage[data-state="sampling"] { outline: none; }

/* --- the still's own press ------------------------------------------------ */
/*
 * The second run row, at the foot of the pre-stage's column, and the whole of
 * why the desk now has two: a still and a shot are two renders, and one button
 * that ran both meant you could not remake the still without also remaking the
 * clip built on it, or touch the still's prompt without the next Render quietly
 * making one.
 *
 * Outlined where the shot's is filled, because the accent belongs to the piece.
 * The desk has one saturated area in it and this is not it — this is the step
 * before, and a second amber bar would have made the two look like a choice
 * between equals rather than a sequence.
 */
.mmc-fs-prerun { padding: 8px 16px 16px; }
.mmc-fs-run.ghost {
  height: calc(38px * var(--mmc-type)); font-size: calc(13px * var(--mmc-type)); font-weight: 500;
  background: none; border: 1px solid var(--mmc-line); color: var(--mmc-dim);
}
.mmc-fs-run.ghost:hover:not(:disabled) {
  filter: none; background: var(--mmc-surface-2); color: var(--mmc-text);
}
.mmc-fs-run.ghost.busy { border-color: var(--mmc-accent); color: var(--mmc-accent); }

/* --- Render and Cancel ---------------------------------------------------- */
/*
 * ComfyUI's Run button is behind the shell, so the piece grows its own, at the
 * foot of the column that describes it: write, set, run, top to bottom. It is
 * also the queue readout — a second progress indicator in the title bar would
 * be the same number said twice, and the picture already carries the step count.
 */
.mmc-fs-runrow {
  flex: none; display: flex; align-items: center; gap: 12px;
  padding: 12px 16px 16px; min-height: 0;
}
.mmc-fs-run {
  display: flex; align-items: center; justify-content: center;
  /* Fills the foot of a narrow column and stops there on a wide one. Uncapped it
     grew with the card — on a large screen the desk's Render was a metre of
     amber with one word in the middle of it, the loudest thing in a room whose
     subject is the picture. */
  height: calc(44px * var(--mmc-type)); padding: 0 24px; flex: 1; max-width: calc(380px * var(--mmc-type));
  border-radius: 22px; border: 0; cursor: pointer;
  background: var(--mmc-accent); color: var(--mmc-on-accent);
  font-family: inherit; font-size: calc(14px * var(--mmc-type)); font-weight: 600;
}
.mmc-fs-run:hover:not(:disabled) { filter: brightness(1.08); }
.mmc-fs-label { display: flex; align-items: center; gap: 8px; }
.mmc-fs-run svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 1.9; }
/* Running, it reads as the readout it already was — dimmed to the surface the
   pills wear, because the loud control in the row is Cancel now. Still a button
   though, and still pressable: a second press queues a second take, the way
   ComfyUI's own Queue button does. So it keeps the pointer and the hover. */
.mmc-fs-run.busy {
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-weight: 500;
}
.mmc-fs-run.busy:hover { border-color: var(--mmc-accent); color: var(--mmc-text); }
.mmc-fs-steps { color: var(--mmc-accent); font-variant-numeric: tabular-nums; }
.mmc-fs-cancel {
  height: var(--mmc-pill-h); padding: 0 16px; border-radius: 19px; flex: none;
  background: none; border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-family: inherit; font-size: calc(13px * var(--mmc-type)); cursor: pointer;
}
.mmc-fs-cancel:hover { border-color: color-mix(in srgb, var(--mmc-warn) 55%, transparent); color: var(--mmc-warn); }
.mmc-fs-note { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); }

/* The simple view's way to the sampler row it folded away. Only that view draws
   it — see the display:none directly below, which the .simple rule undoes. */
.mmc-fs-more {
  display: none; align-items: center; gap: 7px; flex: none;
  height: var(--mmc-pill-h); padding: 0 14px; border-radius: 19px;
  background: none; border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-family: inherit; font-size: calc(13px * var(--mmc-type)); cursor: pointer;
}
.mmc-fs-more svg { stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-fs-more:hover { color: var(--mmc-text); border-color: var(--mmc-line-2); }
.mmc-fs-more[aria-pressed="true"] { color: var(--mmc-text); background: var(--mmc-surface-2); }

/* --- the simple view ------------------------------------------------------ */
/*
 * One piece, one column, in the middle of the screen: the frame above, the
 * writing below, Render under that. Nothing is removed that the render reads —
 * the rail, the references, the cast and the shot's own pills are all still
 * here — the sampler row is folded because it is the one row you set once and
 * then stop looking at, and it comes back on a press.
 *
 * The order is the reason this is a class and not a second layout: the dock is
 * written *after* the column in the DOM, because on the desk the picture is to
 * the right of the writing. Here it is above it, and the order property
 * says so without anything having to be moved.
 */
/* One number for how wide the middle of the screen is, because the dock, the
   card and the picture inside the dock all have to agree about it — and every
   one of them has to be told in a length rather than a percentage. A percentage
   resolves against a parent that is itself sized by its content here, which is
   the loop that let a render hang over the right-hand edge. */
/* A measure, not a fraction: 720 is what one card wants, and it holds from a
   laptop down to the point where the window itself is narrower than that. The
   middle term is the only concession to a very wide screen — past about 1560 the
   card is a stamp in the middle of an acre, so it takes a little of the room
   back, and stops at 820 because prose and a pill row both stop reading as one
   column somewhere above that. */
.mmc-fs.simple {
  --mmc-fs-measure: min(860px, max(760px, 48vw), calc(100vw - 48px));
}
/*
 * The same two regions the desk has, in the same places — the writing on the
 * left, the picture on the right — with one difference that is the whole point:
 * the right-hand one is not there until there is something in it.
 *
 * So the card sits in the middle of an empty window while you write, and the
 * moment you press Render the reel opens beside it and the card slides left to
 * make room. Nothing appears at a new address: the card is on rails between two
 * positions that both exist in the same row, and the row is centred, so opening
 * the reel *is* the movement. There is no second layout and no swap.
 */
.mmc-fs.simple .mmc-fs-body {
  flex-direction: row; align-items: center; justify-content: center;
  gap: 0; padding: 24px; overflow: hidden;
}
.mmc-fs.simple .mmc-fs-pre { display: none; }
/* No row to make here — one card and the reel, laid out by the body itself. */
.mmc-fs.simple .mmc-fs-desk { display: contents; }
/* Closed, and taking part in the row the whole time: a max-width of zero is a
   column that is there, has no width, and can be given one over a third of a
   second. Animating the reel rather than moving the card is what makes the card
   move — the row is centred, so the card's position is a consequence of how
   wide its neighbour is, and a consequence can be smooth where a repositioning
   would have been a jump. */
.mmc-fs.simple .mmc-fs-reel {
  flex: 1 1 auto; min-width: 0; max-width: 0; align-self: stretch;
  padding: 0; opacity: 0; gap: 12px;
  transition: max-width .32s cubic-bezier(.4, 0, .2, 1),
              padding-left .32s cubic-bezier(.4, 0, .2, 1),
              opacity .22s ease .06s;
}
.mmc-fs.simple.working .mmc-fs-reel {
  max-width: min(880px, 46vw); padding-left: 24px; opacity: 1;
}
/* And on a window with no room for both at full size, the card gives first. It
   is a fixed measure while it is alone in the middle of the screen; once there
   is a picture beside it the picture is the point, and a card that refused to
   yield left a 4K render showing at the size of a playing card. 520 is the floor
   — below that the pill row starts breaking into rows of one. */
.mmc-fs.simple.working .mmc-fs-col { flex: 0 1 auto; min-width: min(520px, 100%); }
/* A window that has never rendered shows the card and nothing else — an outline
   of a frame beside an empty column would be two kinds of nothing. It comes
   back with the reel, so the first press opens onto the shape the picture is
   about to take and the picture lands in the box that was already there. */
.mmc-fs.simple:not(.working) .mmc-fs-frame { display: none; }
/* A taller lip here than on the desk: the simple view gives the picture region
   most of the window, so a strip of takes at desk size would read as a footnote
   under it. */
.mmc-fs.simple { --mmc-fs-lip: 124px; }
/* The reduced-motion answer is the same two positions with nothing between
   them: the reel is open or it is not. */
@media (prefers-reduced-motion: reduce) {
  .mmc-fs.simple .mmc-fs-reel { transition: none; }
}
/* One card in the middle of a dark room, and the well cut into it. Elevation is
   relative, so the shell keeps its one rule in both views: everything is raised
   off the ground except the box you write in. Dropping the card here would have
   left the well recessed into nothing, which on this background is a panel you
   cannot see at all. */
.mmc-fs.simple .mmc-fs-col {
  width: var(--mmc-fs-measure); flex: none;
  /* The measure is the card, edge to edge. Nothing in this pack sets box-sizing
     globally, so content-box would have made the number the width of the inside
     and quietly added 38px of padding and border to it — which is 38px the
     window's own padding had not been asked for at the width where the two meet. */
  box-sizing: border-box;
  /* One height, whatever step you are standing on and whatever you have
     written. The card used to be as tall as its contents, which made the size
     of the room a function of the length of your sentence — and made the step
     switch a jump, because a pre-stage has one pill row where a shot has two.
     A measure in both axes instead: the card is the same rectangle on both
     steps, so switching moves what is *in* it and nothing else. The writing
     inside gives and takes the room (see .mmc-well below); the card does not.
     Capped by the window first, so a short screen still gets a whole card. */
  height: min(calc(620px * var(--mmc-type)), 100%);
  max-height: 100%; min-height: 0; overflow-y: auto;
  /* Positioned, and only for the paint order. The stage is position:relative,
     so an unpositioned card below it in the DOM is painted *under* it — which
     is what put a finished video over the tool rail the moment anything let the
     picture out of the reel. The reel's own scroll is the real containment;
     this is the guarantee that a leak is visible rather than obscuring. */
  position: relative;
  border-radius: 26px; padding: 18px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  box-shadow: 0 24px 64px var(--mmc-shadow-soft);
}
/* The body fills the card and gives room back to it, both. It used to only give
   — the card was as tall as its contents, so growing was the card's business —
   and now the card is a fixed rectangle, so the room between the rail and Render
   belongs to the body and the well inside it. Both roots, wrapper and shot
   alike, or the wrapper caps the body it was only ever holding. */
.mmc-fs.simple .mmc-fs-face,
.mmc-fs.simple .mmc-fs-col .mmc-root { flex: 1 1 auto; min-height: 0; }
/* The turn's axis, and nothing more. Down the middle of the face, so it pivots
   about the line the switch sits on rather than about an edge; the perspective
   is written into the animation's own transform (see turnTo() in fullscreen.js)
   because it belongs to the gesture and not to the layout. No will-change: a
   layer held for the whole session to serve a third of a second of motion is
   the trade the wrong way round, and a promoted layer softens the type in it. */
.mmc-fs.simple .mmc-fs-face { transform-origin: 50% 50%; }
/* The panel fills what the card has left, and the writing inside it is what
   scrolls. This used to be a floor in pixels — 210, hand-counted from the box's
   own minimum plus the rails that share the panel with it — and a floor is a
   number that can be wrong. A rewrite puts a second description of the shot in
   here, which is far taller than any floor written for a panel holding only the
   box; the flex chain above went on shrinking the panel to that number anyway,
   and the rewrite was painted straight over the pill row and Render. That was
   the broken layout: not a scrollbar in the wrong place, a panel smaller than
   the thing inside it.
   Now the card owns the height, the panel takes it, and .mmc-well takes what is
   left of the panel once the pill row has had its line. Nothing is ever asked
   to be shorter than what it holds. */
.mmc-fs.simple .mmc-panel { flex: 1; min-height: 0; }
/* And the scroll is here, on the writing alone, so the pills and Render stay
   where they are however long the rewrite runs. */
.mmc-fs.simple .mmc-well { overflow-y: auto; }
.mmc-fs.simple .mmc-root { height: auto; overflow: visible; }
.mmc-fs.simple .mmc-root:not(.hosting) { padding: 0; gap: 12px; }

/* Centred, and smaller: on the desk the rail is a shelf of tools down one side
   of the work, and here it is a line of them across the top of one card.
   Columns rather than tiles-plus-gap for the reason the shell's rail gives, but
   held by the tools themselves and not by a grid: the card is wide enough that
   this rail is one line, and a grid would put the cluster's hairline in a whole
   track of its own — far more room than a seam wants. */
.mmc-fs.simple { --mmc-tool-tile: calc(44px * var(--mmc-type)); }
.mmc-fs.simple .mmc-rail { display: flex; justify-content: space-between; gap: 14px 0; }
.mmc-fs.simple .mmc-rail-group {
  display: flex; align-items: flex-start; gap: 14px 0; margin-left: 0;
}
.mmc-fs.simple .mmc-tool { width: calc(68px * var(--mmc-type)); font-size: calc(11px * var(--mmc-type)); gap: 6px; }
.mmc-fs.simple .mmc-tool-icon { border-radius: 12px; }
.mmc-fs.simple .mmc-tool svg { width: 19px; height: 19px; }
/* The split the node face makes with the whole width of the node — this
   generation's tools at one end, the machine's at the other — is the split this
   card makes too, and it makes it the same way: the two groups go to the two
   ends and the room between them is the seam. Centred, they were one line of
   nine identical squares that said nothing about it, and the hairline drawn
   between them said it in a mark where the card had a whole edge to say it
   with. */
.mmc-fs.simple .mmc-assets, .mmc-fs.simple .mmc-lora-block { justify-content: center; }
/* The well is the whole composition here, so it gets the room to be one. */
.mmc-fs.simple .mmc-panel { border-radius: 24px; padding: 18px; }
/* And no share-of-the-window cap on it here, unlike the desk (see the foot of
   this file): the card is already bounded by the window, so the well is bounded
   by whatever is left of the card once the rail, the references and the rows
   under the sentence have taken theirs. A cap on top of that is a second,
   smaller bound, and on a tall screen it is a hole under the box. */
.mmc-fs.simple .mmc-prompt {
  font-size: calc(17px * var(--mmc-type)); min-height: calc(84px * var(--mmc-type)); max-height: none;
}

/* Every row on this card is centred on the column — the rail, the step switch,
   the references — and the pill row is the one that was not.
 *
 * On a node face the row is a left-aligned toolbar with the route badge held
 * against the far end by an auto margin, and that is right there: the row is
 * one line, so the margin puts the readout at the end of it. Here the row is
 * always two lines, because the card is a measure rather than a node's width —
 * and an auto margin on a wrapped line pushes whatever landed on it to the right
 * edge. That is what stranded the badge and the Timeline pill out on their own,
 * with a hole between them and everything above.
 *
 * Centred, the second line reads as the rest of the first rather than as a
 * separate right-hand thing, and the margin has to go with it: an auto margin
 * beats justify-content, so leaving it in would have centred nothing. */
.mmc-fs.simple .mmc-pills { justify-content: center; gap: 8px 10px; }
.mmc-fs.simple .mmc-pills-tail { justify-content: center; }
/* Folded away until the press. Nothing about the render changes with it — the
   row is drawing widget values that are set whether or not it is on screen. */
.mmc-fs.simple:not(.advanced) .mmc-sampling-host { display: none; }
/* Render is the one action on the card, not the width of it. Stretched to the
   column it was the largest object in the room — louder than the picture it
   makes, and wide enough that the words sat alone in the middle of a bar — and
   it dragged the row off centre under a card whose every other row is centred.
   Sized to the press and centred with the control beside it: still the only
   filled thing on screen, which is all the emphasis it ever needed. */
.mmc-fs.simple .mmc-fs-runrow {
  padding: 14px 0 0; justify-content: center; flex-wrap: wrap; gap: 10px 12px;
}
.mmc-fs.simple .mmc-fs-run { flex: 0 1 300px; }
.mmc-fs.simple .mmc-fs-more { display: flex; }

/* --- a window too narrow for the desk ------------------------------------- */
/*
 * Three regions with floors of 340, 500 and 260 want about 1160px before the
 * gaps, and under that the body used to pan sideways — which is the one answer
 * a workspace cannot give. You write in the card and judge in the picture, and a
 * pan puts one of the two off the side of the screen while you are using the
 * other.
 *
 * It is not a rare window either. Browser zoom is measured in CSS pixels, so
 * Cmd + twice on a 1440px screen *is* a 1000px window — the desk started panning
 * exactly when somebody zoomed in to read it.
 *
 * So the room gives up its axis before it gives up a region: the picture leaves
 * the line and goes under the desk, full width, and the window scrolls. Left to
 * right the desk still reads pre-stage, then shot; the picture they make is now
 * beneath the pair rather than beside it, which is the same sentence with a line
 * break in it. Nothing is hidden and nothing is folded away.
 */
@media (max-width: 1160px) {
  .mmc-fs:not(.simple) .mmc-fs-body {
    flex-direction: column; align-items: center;
    /* The other axis, for the same reason it was the other axis before: this is
       where the room now runs out. */
    overflow: hidden auto;
  }
  /* Both cards were capped at the height of the body so the row could hold them
     side by side. Stacked, that cap is the thing stopping the column from being
     as long as its contents, and what scrolls is the window. */
  .mmc-fs:not(.simple) .mmc-fs-desk,
  .mmc-fs:not(.simple) .mmc-fs-col,
  .mmc-fs:not(.simple) .mmc-fs-pre { max-height: none; }
  .mmc-fs:not(.simple) .mmc-fs-desk { width: 100%; justify-content: center; }
  /* A definite height rather than the slack in a row, because the plate's own
     maxima are percentages of the region and a percentage of an auto height
     resolves to nothing — the same trap the dock's comment names. Half the
     window is what a picture under a desk can have without the writing above it
     going off the top. */
  .mmc-fs:not(.simple) .mmc-fs-reel {
    flex: none; align-self: stretch; width: 100%; max-width: 100%;
    height: 52vh; min-height: 240px;
  }
}

/*
 * And under about 900 the two faces stop fitting beside each other either — 340
 * and 500 plus the gap is the whole of that width — so the desk takes the same
 * break the body just took. Top to bottom it is pre-stage, shot, picture: the
 * order the row read in, turned through ninety degrees and nothing else.
 */
@media (max-width: 900px) {
  .mmc-fs:not(.simple) .mmc-fs-desk { flex-direction: column; width: 100%; }
  .mmc-fs:not(.simple) .mmc-fs-col,
  .mmc-fs:not(.simple) .mmc-fs-pre {
    width: 100%; min-width: 0;
  }
  /* The measure was a cap on a card sharing a line with two others. Alone on
     one, it is the line. */
  .mmc-fs:not(.simple) .mmc-fs-col { max-width: 820px; }
  .mmc-fs:not(.simple) .mmc-fs-pre { max-width: 820px; }
  /* Both cards end in their own Render, and the rule that pushed it to the foot
     was there to line the two buttons up along a shared bottom edge. Stacked
     there is no shared edge, and an auto margin is then a hole between the
     sampler row and the button under it. */
  .mmc-fs:not(.simple) .mmc-fs-runrow { margin-top: 0; }
}

/* --- a window too narrow for the card beside the picture ------------------ */
/*
 * The simple view's own break, and it comes later because it has less to fit:
 * one card of about 760 and the reel it opens beside it. Below roughly 1080 the
 * two of them do not make a line, and this view clips where the desk panned —
 * hiding the overflow is what makes the reel able to open from nothing.
 *
 * The picture goes above the card here rather than below it, which is the
 * difference between the two views said out loud: the desk is a sequence read
 * left to right and keeps that order when it folds, while this view is one piece
 * with its picture over it. It is also what the view was always described as.
 *
 * The opening animation goes with the axis. Widening a column from nothing is
 * not the same gesture — the card above it would jump down the page rather than
 * slide across it — so the reel simply is or is not there, which is the answer
 * this file already gives to reduced motion.
 */
@media (max-width: 1080px) {
  .mmc-fs.simple .mmc-fs-body {
    flex-direction: column; align-items: center;
    overflow: hidden auto; padding: 16px; gap: 16px;
  }
  .mmc-fs.simple .mmc-fs-col {
    width: 100%; max-width: var(--mmc-fs-measure);
    max-height: none; overflow: visible;
  }
  /* Closed is gone, not zero-width: a column has no width to animate and an
     empty region above the card is the outline of nothing. */
  .mmc-fs.simple:not(.working) .mmc-fs-reel { display: none; }
  .mmc-fs.simple.working .mmc-fs-reel {
    order: -1; flex: none; align-self: stretch;
    width: 100%; max-width: 100%; height: 52vh; min-height: 240px;
    padding: 0; opacity: 1; transition: none;
  }
}

/* --- a window too narrow for the card ------------------------------------- */
/*
 * The measure already gives way to the window (see --mmc-fs-measure), so this is
 * only about what is left once it has: below roughly a tablet's width the card
 * is the window, and the room around it — the shell's padding, the card's, the
 * well's — is room the controls need more than the composition does. Nothing is
 * hidden and nothing moves; the insets come in and the rows go on wrapping the
 * way they already do.
 */
@media (max-width: 720px) {
  /* Written once per view rather than once for the shell, because the two
     blocks above each set this at a specificity a bare ".mmc-fs" cannot reach —
     and a rule that loses is worse than one that was never written. */
  .mmc-fs.simple .mmc-fs-body,
  .mmc-fs:not(.simple) .mmc-fs-body { padding: 12px; gap: 12px; }
  .mmc-fs.simple .mmc-fs-col { padding: 14px; border-radius: 20px; }
  /* The desk's cards keep their inset on the body inside them, so it is that
     rule the shell has to narrow rather than the card's own padding. */
  .mmc-fs:not(.simple) .mmc-root:not(.hosting) { padding: 12px 12px 4px; }
  .mmc-fs:not(.simple) .mmc-fs-col,
  .mmc-fs:not(.simple) .mmc-fs-pre { border-radius: 18px; }
  .mmc-fs.simple .mmc-panel { padding: 14px; border-radius: 18px; }
  .mmc-fs.simple .mmc-prompt { font-size: calc(16px * var(--mmc-type)); }
  /* The reel gave the picture half the window while there was a card beside or
     under it worth reading at the same time. At this width the two take turns,
     and a picture worth judging is worth more than half. */
  .mmc-fs.simple.working .mmc-fs-reel,
  .mmc-fs:not(.simple) .mmc-fs-reel { height: 44vh; }
  /* The strip is a lip, and a lip that is a fifth of a phone-shaped window is a
     second region. */
  .mmc-fs, .mmc-fs.simple { --mmc-fs-lip: 84px; }
  /* The title bar is one line of chrome and it must stay one line. What goes is
     only what is said twice or said elsewhere: the node's name is on the card,
     and the way out keeps its arrow and its tooltip. The family stays — it is
     the one thing up here that is not written anywhere else on this view. */
  .mmc-fs-bar { gap: 8px; padding: 0 12px; }
  .mmc-fs-mark, .mmc-fs-family { white-space: nowrap; }
  .mmc-fs-piece-group, .mmc-fs-piece-group.on { display: none; }
  .mmc-fs-exit span { display: none; }
  .mmc-fs-exit { padding: 0 8px; }
}

/* --- what the simple view leaves out -------------------------------------- */
/*
 * Cast somebody, attach a clip, narrow a reference, and the card that was one
 * prompt in the middle of a window becomes four rows of chips over a paragraph
 * of explanation. Every one of those is right on a node face, where it is the
 * only place the thing can be said — and wrong here, where the point of the view
 * is that there is one thing on screen.
 *
 * One rule decides what goes, and it is not "hide the hard parts":
 * **explanation goes; state stays.** The scopes band, the shelf's standing
 * sentence and the empty shelf's note all describe what the controls beside
 * them already say. Nothing here is the only place a fact is written.
 *
 * There used to be a second rule — "a setting nobody changed is not a setting"
 * — which hid a reference chip's narrowings while they held their default. It
 * was wrong in the one case that mattered: the default is exactly the answer
 * you are trying to leave, so a picture attached here could not be made a style
 * reference at all. The chip now says what was set and its *name* opens the
 * rest -- openReferenceSheet in editor.js -- which is the same card in both
 * views and needs no rule here.
 *
 * Everything dropped is one press away in the full view, and none of it is
 * dropped from the render: these are display rules over the same bodies, and
 * the blob they are drawing has not moved.
 */
/* The cast, both the tool and the drawer it opens. Not a shortening of it — the
   whole shelf, because in this view everything it does is already somewhere
   else and better placed:
 *
 * * **Casting somebody** is what the @ menu's roster does. It reads the cast
 *   library, and picking a name there attaches their pictures and writes the
 *   name into the sentence in one gesture — which is a shorter path than a
 *   drawer that made you find them, cast them, and then go and cite them.
 * * **Building or editing somebody** is the library's Cast tab: New cast
 *   member, the sheet with their description, their files and what each one is
 *   for, Export and Delete. Presets is in the rail two tiles along.
 * * **Taking somebody out** is deleting their chip from the prompt. It is not a
 *   shortcut — compile cuts the cast down to the subjects the text actually
 *   cites (subjects.cited, in compile.py), so a member nobody writes is not in the render.
 *
 * What is left over is a drawer that lists people, and a list of who is in a
 * shot is a thing you can read off the sentence you wrote. The full view keeps
 * it: editing the copy in *this* piece, rather than the library's, is the one
 * thing that still lives there.
 */
.mmc-fs.simple .mmc-cast, .mmc-fs.simple .mmc-tool-cast { display: none; }
/* The drawer's host with it. A hidden shelf inside a host that is still a row
   of the column left the card carrying the gap either side of a drawer nobody
   can see — which is most of the way to still having the drawer. */
.mmc-fs.simple .mmc-cast-host:not(:has(> .mmc-cast.summoned)) { display: none; }
/*
 * ...except summoned, which is the one thing neither the roster nor the library
 * covers: editing the copy of somebody that lives in *this* piece. The library
 * sheet edits the library's copy, and casting them again makes a second person
 * rather than updating the first, so without this there would be no way to
 * change a description or move a file between their slots once they were in.
 *
 * Double-click their name in the sentence and the shelf arrives on them alone;
 * their own chevron takes it away again. Raised, unlike the resident shelf,
 * because it is a thing that just appeared over the card rather than a row of
 * it — and without its head, because you asked about somebody by name and
 * "Cast / From the library / Add someone" is an answer to a different question.
 */
.mmc-fs.simple .mmc-cast.summoned {
  display: flex; padding: 8px; border-radius: 14px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
}
.mmc-fs.simple .mmc-cast.summoned .mmc-cast-head { display: none; }
/* The reference row is the same row in both views. It used to hide the cast's
   own pictures here, on the grounds that a chip for @vera's photo says what the
   @vera in the sentence already says — which was true until a file could be
   muted. A muted picture is a thing you go and look for, and a row that draws
   only some of what is attached is a row you cannot trust to be the answer. So
   both views show everything on the shot, and the chip that is out of the run
   says so where the file is rather than only in the sentence. */
/* --- the face's caps, lifted ---------------------------------------------- */
/*
 * Two rows of chips then scroll; ten lines of prompt then scroll. Both bounds
 * exist because a node face is a preview that must not grow the node, and both
 * are wrong on a screen — the same reason the timeline window and the editor
 * sheet already lift them (styles/editor.js). Same list, one more member.
 *
 * Scoped to the shell rather than to a class on the body, because "the body" is
 * three different elements: the Creator's root is .mmc-root, a Timeline hosting
 * one shot wraps a second .mmc-root inside its own, and the PreStage's root is
 * the .mmc-prestage-host that swaps its editors. An ancestor selector is true of
 * all three and cannot go stale when a fourth arrives.
 */
.mmc-fs .mmc-assets { max-height: none; overflow: visible; }
/* Ten lines is the node's bound and it comes off here — but not to nothing. The
   well is sized by its content now, so an unbounded box grows the card until the
   pill row and the sampler row are off the bottom of the screen. A share of the
   window is the bound a window should have: the box takes the room the screen
   actually has, then scrolls inside itself, with the controls that belong to the
   sentence still under it. */
.mmc-fs .mmc-prompt { max-height: 46vh; }
/* The corner control opens the prompt in a window when it outgrows the face.
   Nothing outgrows this one. */
.mmc-fs .mmc-panel-corner { display: none; }
.mmc-fs .mmc-panel .mmc-prompt-fold .mmc-prompt { padding-right: 0; }

/* --- the wordmark's dashboard: the tools, as cards ------------------------ */
/*
 * A layer over the room, not a popover beside the mark. It is opaque and it is
 * the full width under the bar: the tools are a place you go, and a place you
 * go has to look like somewhere rather than like a panel hung over the work.
 *
 * Inside .mmc-fs-room rather than over the whole shell so the bar survives —
 * the mark you pressed is still there, still under the pointer, and pressing it
 * again is the way back. A layer that covered its own control would have needed
 * a second one drawn on top of itself to close it.
 */
.mmc-dash {
  position: absolute; inset: 0; z-index: 3;
  background: var(--mmc-bg);
  overflow: auto; overscroll-behavior: contain;
}
/* The measure. Not the window: a grid of 260-pixel cards spread across a
   32-inch screen is eleven columns of nothing-much, and the eye has no left
   edge to come back to. Left-aligned inside the measure rather than centred,
   because the cards are a list that grows down and to the right and the first
   one has to stay where it was when there were three. */
.mmc-dash-sheet {
  max-width: 900px; margin: 0 auto; padding: 34px 28px 40px;
  display: flex; flex-direction: column;
}
/* What pressing any card does, said once, so no card has to say it. */
.mmc-dash-lede {
  margin: 0 0 26px; max-width: 46ch;
  font-size: calc(13.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-dim);
}
/* A section's name, and the rule that says how far the section reaches. The
   same eyebrow the desk's columns wear, so the two surfaces of this editor are
   labelled in one voice. */
.mmc-dash-head {
  display: flex; align-items: center; gap: 14px; margin-bottom: 14px;
  font-size: calc(11px * var(--mmc-type)); font-weight: 600;
  letter-spacing: .14em; text-transform: uppercase; color: var(--mmc-off);
}
.mmc-dash-rule { flex: 1; height: 1px; background: var(--mmc-line); }
/* Auto-fill rather than auto-fit: with one tool on the grid, auto-fit would
   stretch that card the width of the sheet and the surface would read as a
   banner. The track is the card's size whether or not anything is in it, which
   is what keeps the first card the same size on the day the eighth arrives. */
.mmc-dash-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(236px, 1fr));
  gap: 14px; margin-bottom: 30px;
}
.mmc-dash-grid:last-child { margin-bottom: 0; }

/* One tool. The whole card is the press. */
.mmc-dash-card {
  display: flex; flex-direction: column; overflow: hidden; text-align: left;
  border-radius: 20px; background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-family: inherit; padding: 0; cursor: pointer;
  transition: background 140ms ease, border-color 140ms ease, transform 140ms ease;
}
.mmc-dash-card:hover { background: var(--mmc-surface-2); border-color: var(--mmc-line-2); transform: translateY(-2px); }
.mmc-dash-card:active { transform: translateY(0); }
.mmc-dash-card:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }

/* The plate, and the one piece of decoration on this surface.
 *
 * It carries the tool's own glyph — the fifteen-pixel drawing off the rail — at
 * poster size, anchored to the plate's lower-left and cropped by its bottom
 * edge. Cropped deliberately: a glyph centred in a box is an icon with padding,
 * and the grid was then eight boxes of the same shape distinguished by a small
 * shape in the middle of each. Run off the edge it is a picture the card is
 * showing, and across a row of them the plates are what the eye tells apart
 * before it reads a single name.
 */
.mmc-dash-plate {
  position: relative; flex: none; height: 96px; overflow: hidden;
  background: var(--mmc-tint); border-bottom: 1px solid var(--mmc-line);
}
.mmc-dash-glyph {
  position: absolute; left: -4px; bottom: -30px; display: flex;
  transition: transform 220ms cubic-bezier(.2, .7, .3, 1);
}
/* Hairline weight, because the stroke scales with the drawing: the 1.6 the rail
   sets would come out as a seven-pixel bar at this size. */
.mmc-dash-glyph svg {
  stroke: var(--mmc-line-3); fill: none; stroke-width: .7;
  transition: stroke 140ms ease;
}
.mmc-dash-card:hover .mmc-dash-glyph { transform: translateY(-6px); }
.mmc-dash-card:hover .mmc-dash-glyph svg { stroke: var(--mmc-accent); }

.mmc-dash-word { display: flex; flex-direction: column; gap: 4px; padding: 14px 16px 16px; }
.mmc-dash-name { font-size: calc(15px * var(--mmc-type)); font-weight: 600; }
.mmc-dash-sub {
  font-size: calc(12px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-dim);
}

/* The place the next tool lands in. Outlined rather than filled — there is no
   surface here yet, only a space kept for one — and it is not pressable, so it
   never takes the pointer or the tab. */
.mmc-dash-card.soon {
  background: none; border-style: dashed; border-color: var(--mmc-line-2);
  cursor: default; pointer-events: none;
}
.mmc-dash-card.soon .mmc-dash-plate { background: none; border-bottom-color: transparent; }
.mmc-dash-card.soon .mmc-dash-name { color: var(--mmc-off); font-weight: 500; }
.mmc-dash-card.soon .mmc-dash-sub { color: var(--mmc-off); }

/* The arrival. One sweep across the grid rather than a scatter of effects: the
   surface is new, so it comes in, and then it is still. The stagger is capped
   so a grid of twenty does not spend two seconds assembling itself. */
.mmc-dash-card {
  animation: mmc-dash-in 180ms ease both;
  animation-delay: calc(min(var(--i, 0), 8) * 28ms);
}
@keyframes mmc-dash-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}
/* The caret is the standing hint that the name is pressable; which way it
   points is which side of the door you are on. */
.mmc-fs-mark[aria-expanded="true"] .mmc-fs-caret { transform: rotate(180deg); }
.mmc-fs-caret { transition: transform 180ms ease; }

@media (prefers-reduced-motion: reduce) {
  .mmc-dash-card { animation: none; }
  .mmc-dash-card:hover { transform: none; }
  .mmc-dash-glyph, .mmc-fs-caret { transition: none; }
}
@media (max-width: 720px) {
  .mmc-dash-sheet { padding: 24px 18px 32px; }
  .mmc-dash-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
  .mmc-dash-plate { height: 84px; }
}

`;
