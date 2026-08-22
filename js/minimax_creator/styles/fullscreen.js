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
  flex: none; height: 54px; display: flex; align-items: center; gap: 12px;
  padding: 0 18px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-fs-mark {
  display: flex; align-items: center; gap: 9px;
  font-size: 13px; font-weight: 600; letter-spacing: .01em;
}
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
/* The node's title, which is the piece's name — see fullscreen.js on why this
   pack does not store a second one. */
.mmc-fs-piece { font-size: 13px; color: var(--mmc-dim); }
.mmc-fs-gap { flex: 1; }

/* Simple or Full, as one control rather than two: they are two answers to one
   question, and a pair of loose buttons would have read as two features. */
.mmc-fs-views {
  display: flex; padding: 2px; gap: 2px; border-radius: 14px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
}
.mmc-fs-view {
  height: 24px; padding: 0 13px; border-radius: 12px; border: 0; background: none;
  color: var(--mmc-dim); font-family: inherit; font-size: 12px; cursor: pointer;
}
.mmc-fs-view:hover { color: var(--mmc-text); }
.mmc-fs-view[aria-pressed="true"] { background: var(--mmc-surface-3); color: var(--mmc-text); }
.mmc-fs-view:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }

.mmc-fs-exit {
  display: flex; align-items: center; gap: 7px; height: 30px; padding: 0 11px;
  border-radius: 15px; background: none; border: 1px solid transparent;
  color: var(--mmc-dim); font-size: 12px; font-family: inherit; cursor: pointer;
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
/* As tall as the body in it, up to the height of the window — past that the body
   scrolls inside the card (see the overflow rule below) and Render, which is not
   part of it, stays where it is. */
.mmc-fs-col > .mmc-root { flex: 0 1 auto; min-height: 0; }
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
  background: rgba(255,255,255,.018); border: 1px solid var(--mmc-line);
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
  font-size: 11px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
  color: var(--mmc-off);
}
/* The simple view has one column and the step switch says what is in it. */
.mmc-fs.simple .mmc-fs-head { display: none; }
/* Quieter than the shot beside it, in the two ways a column can be quieter:
   smaller tools and less contrast. Nothing is hidden — this is still the node's
   whole face — it just stops competing for the eye. */
.mmc-fs-pre .mmc-tool-icon { width: 42px; height: 42px; border-radius: 11px; }
.mmc-fs-pre .mmc-tool { font-size: 11px; }
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
}
.mmc-fs-step {
  height: 26px; padding: 0 18px; border-radius: 13px; border: 0; background: none;
  color: var(--mmc-dim); font-family: inherit; font-size: 12px; cursor: pointer;
}
.mmc-fs-step:hover { color: var(--mmc-text); }
.mmc-fs-step[aria-pressed="true"] { background: var(--mmc-surface-3); color: var(--mmc-text); }
.mmc-fs-step:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
/* Inside the segment it acts on, and shown only while you are standing on that
   segment — the one place where "remove the pre-stage" cannot be a slip of the
   hand on the way to switching to it. */
.mmc-fs-step { display: flex; align-items: center; gap: 8px; }
.mmc-fs-step-drop {
  display: flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; padding: 0; margin-right: -4px;
  border: 0; border-radius: 50%; background: none; cursor: pointer;
  color: var(--mmc-off); font-family: inherit; font-size: 14px; line-height: 1;
}
.mmc-fs-step-drop:hover { background: rgba(224,116,60,.18); color: #e0743c; }

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
  border-color: rgba(0,0,0,.55);
  box-shadow: inset 0 1px 2px rgba(0,0,0,.6);
  padding: 16px;
}
/* A page rather than a field: this is the one surface in the pack that holds
   paragraphs, and on a screen it can afford the measure to show them.

   The node's ten-line cap comes off at the foot of this file, with the other
   bounds a face needs and a window does not. */
.mmc-fs .mmc-prompt { font-size: 16px; line-height: 1.62; }

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
.mmc-fs .mmc-tool-icon { width: 48px; height: 48px; border-radius: 13px; }
.mmc-fs .mmc-tool svg { width: 20px; height: 20px; }
/* Eleven labelled tools do not fit a column narrow enough to read a prompt back
   in, so the rail wraps here whatever the tile size — and on the node face the
   machine's pair keeps its own edge, which left the wrapped row hanging off the
   right with a hole beside it. In the shell the two clusters stay two clusters
   by the column gap alone and the second row starts where the first did. */
.mmc-fs .mmc-rail { gap: 10px 20px; justify-content: flex-start; }
.mmc-fs .mmc-rail-group:last-child { margin-left: 0; }

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

/* --- the reel ------------------------------------------------------------- */
/*
 * Every render this editor has finished, oldest at the top and the live stage
 * at the bottom, so the newest picture is the one nearest the writing and the
 * older ones are up the scroll.
 *
 * It exists because the stage is one box and execution_start clears it. That
 * is right on a canvas — a card beside a node still showing last week's render
 * while this week's samples would be a card that lies — and it is exactly wrong
 * in a window with room for both, because the reason you queue a second take is
 * to see it beside the first. Nothing is copied: an entry points at the same
 * file the gallery opens, so closing the editor loses the list and no render.
 *
 * Scrolls itself to the bottom on every arrival (see keepTake in fullscreen.js), which is the
 * one behaviour that makes a log readable: what just happened is where you are
 * already looking, and history is a scroll away rather than a mode.
 */
.mmc-fs-reel {
  /* A floor, so the picture is never the region that gives everything up: the
     cards shrink to their own floors first. Below the width where all three
     floors fit, the desk pans — a window that narrow wants the simple view. */
  flex: 1 1 0; min-width: 260px; min-height: 0; max-width: 860px;
  /* The one region that still takes the whole height: the cards are as tall as
     their controls, a picture is as tall as there is room for. */
  align-self: stretch;
  display: flex; flex-direction: column; justify-content: flex-start;
  gap: 14px; padding: 10px; overflow-y: auto;
}
/* The takes are the reel's own children for layout — a wrapper between them and
   the column would have to re-declare the whole of it, and the empty-reel rule
   below needs the wrapper to still be a sibling in the DOM. */
.mmc-fs-past { display: contents; }
/* Packed to the bottom by an auto margin on the oldest take rather than by
   justify-content: flex-end, for the same reason the simple view centres this
   way — content packed against the end of a scroll container overflows past the
   start, where there is nothing to scroll back with. The margin takes the free
   space when there is any and collapses when there is not. */
.mmc-fs-past .mmc-fs-take:first-child { margin-top: auto; }
/* One picture in the room and it sits in the middle of it; a second and the
   column packs to the bottom and starts scrolling. The auto margins are the
   whole of that switch — no class, no measurement, and nothing to keep in sync
   with how many renders there have been. */
.mmc-fs-past:empty + .mmc-fs-dock { flex: 1; margin: auto 0; }

.mmc-fs-take {
  flex: none; display: flex; flex-direction: column; align-items: center; gap: 6px;
}
/* Smaller than the live one, and that is the hierarchy: the picture at the
   bottom is the answer to what you just queued, and the ones above it are what
   it is being compared against. At the same size the column held one take and
   the comparison needed a scroll to make. */
.mmc-fs-take-media {
  max-width: 100%; max-height: 30vh; width: auto; height: auto; min-width: 0;
  border-radius: 14px; background: #000; border: 1px solid var(--mmc-line);
  display: block;
}
/* The filename, which is how a take is found again in the folder. Quiet: the
   picture is the entry and this is its label, not its title. */
.mmc-fs-take-name {
  flex: none; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; font-size: 11px; color: var(--mmc-off);
}

/* --- where the newest picture lands --------------------------------------- */
/*
 * The still keeps the floating card's rule — display:none until the satellite
 * says there is something to show. The dock does not: hidden, it left the
 * piece's column pinned to the left edge with a border ending in mid-air. It is
 * always here, and holds the frame the piece is about to make until there is a
 * picture to put in it.
 */
.mmc-fs-dock {
  display: flex; flex: none; min-width: 0; max-height: 66vh;
  align-items: center; justify-content: center;
}
.mmc-fs-still { display: none; }
.mmc-fs-still.showing { display: flex; flex: none; padding: 14px 14px 0; }
/* Docked, the stage is sized by its column rather than scaled with the canvas.
   The card's own rules size the media off its *height* alone — right on a
   satellite, whose height is the node's and whose width the picture decides,
   and wrong in a column, where a landscape render scaled to the full height is
   wider than the column and the card's overflow:hidden cuts its sides off.
   Here the media is contained by both edges and the card takes its shape from
   what is inside it. */
.mmc-fs-dock .mmc-stage, .mmc-fs-still .mmc-stage { max-width: 100%; max-height: 66vh; }
.mmc-fs-dock .mmc-stage { height: auto; }
/* The card carries flex-direction but never display:flex — on a satellite it
   does not need it, because the card's height is the node's and the media is
   sized off that height alone. Docked, the card is sized by the *column*, and
   without the flex the row inside it has an auto height, which is a height no
   percentage can resolve against: the media went to its intrinsic size and the
   card's overflow:hidden took whatever stuck out. */
.mmc-fs-dock .mmc-stage, .mmc-fs-still .mmc-stage { display: flex; }
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
.mmc-fs-dock .mmc-stage-img, .mmc-fs-dock .mmc-stage-video {
  width: auto; height: auto; min-width: 0; max-width: 100%; max-height: 66vh;
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
/* Filled, faintly, and not only stroked: a 1px hairline at rgba(255,255,255,.16)
   across a third of a large screen is a line you have to go looking for, and a
   dock that reads as empty is the thing this element exists to prevent. The
   fill is what carries the shape at any size; the stroke only edges it. */
.mmc-fs-frame-box {
  flex: 0 1 auto; min-height: 0; width: auto; height: auto;
  max-width: 100%; max-height: 100%;
  fill: rgba(255,255,255,.028); stroke: rgba(255,255,255,.2); stroke-width: 1;
}
.mmc-fs-frame-note {
  flex: none; font-size: 12px; color: var(--mmc-dim);
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
  height: 38px; font-size: 13px; font-weight: 500;
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
  height: 44px; padding: 0 24px; flex: 1; max-width: 380px;
  border-radius: 22px; border: 0; cursor: pointer;
  background: var(--mmc-accent); color: #141414;
  font-family: inherit; font-size: 14px; font-weight: 600;
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
  color: var(--mmc-dim); font-family: inherit; font-size: 13px; cursor: pointer;
}
.mmc-fs-cancel:hover { border-color: rgba(224,116,60,.55); color: #e0743c; }
.mmc-fs-note { font-size: 11px; color: var(--mmc-off); }

/* The simple view's way to the sampler row it folded away. Only that view draws
   it — see the display:none directly below, which the .simple rule undoes. */
.mmc-fs-more {
  display: none; align-items: center; gap: 7px; flex: none;
  height: var(--mmc-pill-h); padding: 0 14px; border-radius: 19px;
  background: none; border: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-family: inherit; font-size: 13px; cursor: pointer;
}
.mmc-fs-more svg { stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-fs-more:hover { color: var(--mmc-text); border-color: rgba(255,255,255,.2); }
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
.mmc-fs.simple .mmc-fs-dock { max-height: 100%; }
.mmc-fs.simple .mmc-fs-reel .mmc-stage,
.mmc-fs.simple .mmc-fs-reel .mmc-stage-img,
.mmc-fs.simple .mmc-fs-reel .mmc-stage-video {
  max-width: 100%; max-height: 74vh;
}
.mmc-fs.simple .mmc-fs-take-media { max-width: 100%; }
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
  /* Its own scroll, so a card taller than the window keeps Render reachable
     without the window scrolling the picture beside it out of view. */
  max-height: 100%; min-height: 0; overflow-y: auto;
  /* Positioned, and only for the paint order. The stage is position:relative,
     so an unpositioned card below it in the DOM is painted *under* it — which
     is what put a finished video over the tool rail the moment anything let the
     picture out of the reel. The reel's own scroll is the real containment;
     this is the guarantee that a leak is visible rather than obscuring. */
  position: relative;
  border-radius: 26px; padding: 18px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  box-shadow: 0 24px 64px rgba(0,0,0,.5);
}
/* On the desk the body fills a column and scrolls inside it. Here the body is
   as tall as what is in it and the *window* is what scrolls, so the group can
   be centred as one thing — a column pinned to full height cannot be. Both
   roots, wrapper and shot alike, or the wrapper goes on clipping the body it
   was only ever holding. */
.mmc-fs.simple .mmc-fs-col > .mmc-root { flex: none; }
.mmc-fs.simple .mmc-root { height: auto; overflow: visible; }
.mmc-fs.simple .mmc-root:not(.hosting) { padding: 0; gap: 12px; }

/* Centred, and smaller: on the desk the rail is a shelf of tools down one side
   of the work, and here it is a line of them across the top of one card. */
.mmc-fs.simple .mmc-rail { justify-content: center; gap: 8px 14px; }
.mmc-fs.simple .mmc-rail-group:last-child { margin-left: 0; }
.mmc-fs.simple .mmc-tool-icon { width: 44px; height: 44px; border-radius: 12px; }
.mmc-fs.simple .mmc-tool { font-size: 11px; gap: 5px; }
.mmc-fs.simple .mmc-tool svg { width: 19px; height: 19px; }
.mmc-fs.simple .mmc-assets, .mmc-fs.simple .mmc-lora-block { justify-content: center; }
/* The well is the whole composition here, so it gets the room to be one. */
.mmc-fs.simple .mmc-panel { border-radius: 24px; padding: 18px; }
.mmc-fs.simple .mmc-prompt { font-size: 17px; min-height: 84px; }

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
  .mmc-fs.simple .mmc-fs-body { padding: 12px; }
  .mmc-fs.simple .mmc-fs-col { padding: 14px; border-radius: 20px; }
  .mmc-fs.simple .mmc-panel { padding: 14px; border-radius: 18px; }
  .mmc-fs.simple .mmc-prompt { font-size: 16px; }
  /* The title bar is one line of chrome and it must stay one line. What goes is
     only what is said twice or said elsewhere: the node's name is on the card,
     and the way out keeps its arrow and its tooltip. */
  .mmc-fs-bar { gap: 8px; padding: 0 12px; }
  .mmc-fs-mark { white-space: nowrap; }
  .mmc-fs-slash, .mmc-fs-piece { display: none; }
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
.mmc-fs.simple .mmc-scopes { display: none; }
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
/* And the cast's own pictures out of the reference row entirely. Casting
   somebody attaches their files, so one person in a shot grew a chip saying
   what the @name in the sentence already says — and here the sentence is the
   only place a subject is written, so the chip was a second, worse copy of it.
   The row is what *you* attached: the frames, the footage, the references.
   Empty of those, it goes with them rather than leaving a gap where it was. */
.mmc-fs.simple .mmc-asset-cast { display: none; }
.mmc-fs.simple .mmc-assets:not(:has(.mmc-asset:not(.mmc-asset-cast))) { display: none; }
/* Growing a second shot is the strip's gesture, and the strip is the full view's
   half of the pack. The Timeline pill in the shot's own row is still the way
   there — this is the dashed rule under the card, which is a whole horizon line
   drawn for one button. */
.mmc-fs.simple .mmc-tl-grow { display: none; }

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

`;
