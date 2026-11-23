// Timeline, timeline node body, sampler pills.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- timeline ------------------------------------------------------------- */

/* The continuation switch, on a segment's pill row. Lit when on, because a
   segment that inherits its first frame is not the default and should not
   look like it. */
.mmc-continue.on { border-color: var(--mmc-accent); color: var(--mmc-accent); }

/* Past the ~5-15 s the weights were trained on. The same warm orange the
   resolution slider uses above 768: a statement about distribution, not a
   refusal, so it marks rather than disables. */
.mmc-pill-group.off-distribution { border-color: color-mix(in srgb, var(--mmc-warn) 40%, transparent); }
.mmc-pill-group.off-distribution > span { color: var(--mmc-warn); }

/* Almost the whole screen, like the shot window: the strip is the one thing in
   this pack that is genuinely wide — a ten-card piece is a metre of film — and
   every pixel not given to it is a card you have to scroll for. The overlay's
   40px inset is what keeps it a window rather than a page. */
.mmc-tl-modal { width: min(1800px, 100%); height: 100%; }
.mmc-tl-prompt {
  width: 100%; box-sizing: border-box; min-height: calc(84px * var(--mmc-type)); max-height: 30vh; resize: vertical;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 14px;
  color: var(--mmc-text); font-family: inherit; font-size: calc(14px * var(--mmc-type)); line-height: 1.5;
  padding: 14px 16px; outline: none;
}
.mmc-tl-prompt:focus { border-color: var(--mmc-line-2); }
.mmc-tl-prompt::placeholder { color: var(--mmc-off); }

/* The global prompt is the same rich box a segment's is — chips and the @ menu
   — so it is a contenteditable in a frame rather than a textarea, and the frame
   is what wears the field skin the two audio boxes beside it wear. Bounded for
   the reason .mmc-prompt is: a long prompt scrolls inside the modal instead of
   pushing the strip off the bottom of it. */
.mmc-tl-prompt-frame {
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 14px;
  padding: 14px 16px; flex: 0 0 auto;
}
.mmc-tl-prompt-frame:focus-within { border-color: var(--mmc-line-2); }
.mmc-tl-prompt-frame .mmc-prompt {
  font-size: calc(14px * var(--mmc-type)); line-height: 1.5; min-height: calc(56px * var(--mmc-type)); max-height: 26vh;
}

/* The two Context-IR audio fields, side by side under the prompt. They wrap to
   one column when the modal is too narrow to give each a readable measure. */
.mmc-tl-audio {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 12px;
}
/* Presentation-only folding; the editors stay mounted. Action buttons are
   siblings of the wide toggle so their click cannot collapse the section. */
.mmc-tl-section { display: flex; flex-direction: column; gap: 6px; min-width: 0; flex: 0 0 auto; }
.mmc-tl-section-head { display: flex; align-items: stretch; gap: 8px; flex-wrap: wrap; min-width: 0; }
.mmc-tl-section-toggle {
  display: flex; flex: 1 1 220px; min-width: 0; gap: 8px; align-items: center;
  padding: 8px 10px; border: 1px solid var(--mmc-line); border-radius: 7px;
  background: var(--mmc-surface); color: var(--mmc-text); font-family: inherit;
  text-align: left; cursor: pointer;
}
.mmc-tl-section-toggle:hover { background: var(--mmc-surface-2); border-color: var(--mmc-line-2); }
.mmc-tl-section-toggle:active { background: var(--mmc-line); }
.mmc-tl-section-toggle:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-tl-section-arrow { flex: 0 0 12px; text-align: center; font-size: 15px; }
.mmc-tl-section-copy { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; min-width: 0; }
.mmc-tl-section-title { font-family: inherit; font-size: calc(13px * var(--mmc-type)); font-weight: 600; word-break: keep-all; overflow-wrap: anywhere; }
.mmc-tl-section-hint { font-size: calc(11px * var(--mmc-type)); font-weight: 400; color: var(--mmc-dim); word-break: normal; overflow-wrap: anywhere; }
.mmc-tl-section-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; flex: 0 1 auto; min-width: 0; }
.mmc-tl-section-actions:empty { display: none; }
.mmc-tl-section-actions button { white-space: normal; }
.mmc-tl-section-body { min-width: 0; }
.mmc-tl-section-body[hidden], .mmc-tl-pool[hidden] { display: none; }
.mmc-tl-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
/* Named for the field they become, not prettified: the value goes into the
   prompt under exactly this key, and someone comparing against MiniMax's guide
   should be able to find it by the same word. */
.mmc-tl-field-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); letter-spacing: .02em;
}
.mmc-tl-small { min-height: calc(64px * var(--mmc-type)); font-size: calc(13px * var(--mmc-type)); padding: 10px 12px; }

/* The piece's reference pool: a shelf between the audio fields and the bar.
   Chips reuse the editor's asset row; what is ours here is only the head line
   and the "used in segments 2, 4" readout. */
.mmc-tl-pool { display: flex; flex-direction: column; gap: 8px; }
.mmc-tl-pool-head { display: flex; gap: 10px; align-items: center; min-width: 0; }
.mmc-tl-pool-hint {
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* What the shelf's last scissors press ran into — a missing matte model,
   mostly. One line, the shelf's own red. */
.mmc-tl-pool-bad { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-bad); }

.mmc-pill.on { border-color: var(--mmc-line-2); }
/* An accelerator that is doing something. Lit rather than merely outlined,
   because a render with one on is not a native render and that is worth seeing
   without reading the pill. */
.mmc-pill.accel-on { border-color: color-mix(in srgb, var(--mmc-role-motion) 45%, transparent); color: var(--mmc-role-motion); }
.mmc-pill.accel-on:hover:not(:disabled) { border-color: color-mix(in srgb, var(--mmc-role-motion) 70%, transparent); }
/* A lit stepper lights all the way through: the turbo lead-in's +/- are part
   of the same control as the number between them, and .mmc-step's own
   --mmc-text left them reading as two grey buttons flanking a blue value.
   Inherit, the rule .mmc-turbo-main and .mmc-turbo-pick already follow. The
   :not() keeps a stepper at the end of its range dim, which is the arrow
   saying it has nowhere left to go. */
.mmc-pill.accel-on .mmc-step:not(:disabled) { color: inherit; }
/* An architecture that is not settled yet. Dashed rather than coloured: this
   says "the output may not be good", which is a different statement from the
   accelerator blue's "this render is not native". */
.mmc-pill.mmc-experimental { border-style: dashed; border-color: color-mix(in srgb, var(--mmc-accent) 50%, transparent); }
.mmc-pill.mmc-experimental:hover:not(:disabled) { border-color: color-mix(in srgb, var(--mmc-accent) 80%, transparent); }
/* A sweep choice inside the dev popover: the same on/off reading as the turbo
   stops, on ordinary pills because the lists are of no fixed length. */
.mmc-pill[aria-pressed="true"] { border-color: color-mix(in srgb, var(--mmc-role-motion) 45%, transparent); color: var(--mmc-role-motion); }
/* The turbo switch: the seed pill's shape — one pill, a big half that throws
   it and a small half that picks what it throws. Both inherit the group's
   colour so the accelerator blue lights the whole pill, chevron included.
   The VDN-H3 switch (sampling.js) wears the same two classes: it is the same
   shape making the same kind of decision, and a second name would be a second
   place for the shape to drift. */
.mmc-turbo-main {
  display: flex; align-items: center; gap: 7px; height: 100%; padding: 0 2px 0 12px;
  background: none; border: 0; color: inherit; font-size: calc(13px * var(--mmc-type));
  font-family: inherit; cursor: pointer; white-space: nowrap;
}
.mmc-turbo-pick {
  display: flex; align-items: center; justify-content: center; width: 26px; color: inherit;
}
/* The turbo pill: the switch, then its quality stops and the lead-in, each
   behind a hairline. One pill holding three mutually exclusive answers, like
   the trim editor's track switch — three loose pills would read as independent
   toggles, and draft/med/good are one dial; and the switch that puts them there
   belongs in front of them, not two chips away. Lit in the accelerator blue,
   because that is the family it belongs to. The stops keep their own grey
   until pressed: the pill's colour says turbo is on, a stop's says which.

   This pill is the prototype the shared segmented pill (.mmc-pill-set, styles/
   editor.js) is drawn after. It keeps its own rules: it was right before there
   was a general one and nothing about it is up for negotiation with it. */
.mmc-pill.mmc-turbo-seg { gap: 0; padding: 0; overflow: hidden; }
.mmc-turbo-opt {
  display: flex; align-items: center; gap: 5px; height: 100%; padding: 0 12px;
  background: none; border: 0; border-left: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: calc(13px * var(--mmc-type)); font-family: inherit; cursor: pointer;
}
.mmc-turbo-opt:first-child { border-left: 0; }
.mmc-turbo-opt:hover { color: var(--mmc-text); }
.mmc-turbo-seg > .mmc-pill-seg { border-left: 1px solid var(--mmc-line); }
.mmc-turbo-opt[aria-pressed="true"] { background: color-mix(in srgb, var(--mmc-role-motion) 14%, transparent); color: var(--mmc-role-motion); }
.mmc-turbo-opt[aria-pressed="true"] .mmc-pill-sub { color: color-mix(in srgb, var(--mmc-role-motion) 75%, transparent); }

/* The sheet, in the chip's popover: nine cells carrying the number of the card
   each is filled from, in the order the frames land. A picture of the layout
   rather than the layout — the frames do not exist until the shots have
   rendered — so it is small and reads as a diagram: the canvas's own shape,
   sources told apart by two tones of the accent, the number in each cell. */
.mmc-board {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px;
  width: 132px; aspect-ratio: 16 / 9; margin: 8px 10px 4px; padding: 2px;
  border-radius: 6px; background: var(--mmc-ground);
}
/* The row of earlier shots to draw the sheet on, as toggles. Lit ones are in. */
.mmc-board-picks { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 10px 2px; }
.mmc-board-pick {
  border: 1px solid var(--mmc-line); border-radius: 6px; padding: 3px 8px;
  background: var(--mmc-surface-2); color: var(--mmc-dim); cursor: pointer;
  font-family: inherit; font-size: calc(11px * var(--mmc-type));
}
.mmc-board-pick:hover { color: var(--mmc-text); border-color: var(--mmc-line-2); }
.mmc-board-pick[aria-checked="true"] {
  color: var(--mmc-accent); border-color: color-mix(in srgb, var(--mmc-accent) 50%, transparent);
  background: color-mix(in srgb, var(--mmc-accent) 14%, transparent);
}
.mmc-board-pick:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }

/* How firmly the sheet holds, under the storyboard pill's answers (issue #96).
   As wide as the popover the answers above already make it, and never so
   narrow that the line below reads as a column of words. The popover it sits
   in is a choice list, capped short for long lists of samplers; this one is
   three rows and a section, and is let run to the screen's own limit on
   .mmc-pop instead of hiding its sentence under a scroll. */
.mmc-board-hold-sect { min-width: 300px; box-sizing: border-box; }
.mmc-pop-scroll:has(.mmc-board-hold-sect) { max-height: calc(100vh - 16px); }
.mmc-board-hold-head { padding: 4px 10px 0; }
.mmc-board-hold-note { line-height: 1.4; }
/* The three holds are the shot toggles above in the same row shape, split
   evenly, each led by a strength gauge: three bars, two, one. */
.mmc-board-holds { flex-wrap: nowrap; }
.mmc-board-hold { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; }
.mmc-board-hold-bars { display: inline-flex; align-items: flex-end; gap: 1.5px; height: 9px; }
.mmc-board-hold-bars i { width: 2.5px; border-radius: 1px; background: currentColor; opacity: .22; }
.mmc-board-hold-bars i:nth-child(1) { height: 4px; }
.mmc-board-hold-bars i:nth-child(2) { height: 6.5px; }
.mmc-board-hold-bars i:nth-child(3) { height: 9px; }
.mmc-board-hold-bars i.on { opacity: 1; }

/* The line, drawn as the model reads it in retention_analysis: the marker in
   the accent, then the sentence, which is the part that edits. One frame
   around both, so they read as one statement and the caret lands in the
   sentence wherever the frame is clicked. */
.mmc-board-line {
  display: block; margin: 8px 10px 0; padding: 8px 10px 6px; cursor: text;
  border: 1px solid var(--mmc-line); border-radius: 10px; background: var(--mmc-ground);
}
.mmc-board-line:focus-within { border-color: color-mix(in srgb, var(--mmc-accent) 60%, transparent); }
.mmc-board-line-marker {
  display: block; color: var(--mmc-accent); font-weight: 600;
  font-size: calc(11.5px * var(--mmc-type)); margin-bottom: 3px;
}
.mmc-board-line-text {
  display: block; width: 100%; box-sizing: border-box; margin: 0; padding: 0;
  background: none; border: 0; outline: 0; resize: vertical;
  color: var(--mmc-text); font: inherit; font-size: calc(12.5px * var(--mmc-type)); line-height: 1.45;
}
.mmc-board-line-foot {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  padding: 5px 10px 2px;
}
.mmc-board-line-reset {
  background: none; border: 0; padding: 0; cursor: pointer; font: inherit;
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-accent);
}
.mmc-board-line-reset:hover { text-decoration: underline; }
.mmc-board-line-reset[hidden] { display: none; }
@media (prefers-reduced-motion: no-preference) {
  .mmc-board-line { transition: border-color .12s ease; }
}

/* The piece-view toggle: which face this node is wearing while it holds one
   shot. Amber, because that is the strip's colour everywhere else in here — the
   lane's ticks, the pass casing, the cut marks — and pointedly not the
   accelerator blue the generic aria-pressed rule above would otherwise give it.
   Blue in this pack means "this render is not native", and a control that only
   decides what you are looking at has nothing to say about the render.

   Three classes, so it beats that rule wherever the two land in the cascade. */
.mmc-pill.mmc-piece-toggle.on {
  border-color: color-mix(in srgb, var(--mmc-accent) 45%, transparent); color: var(--mmc-accent);
}
.mmc-pill.mmc-piece-toggle.on:hover:not(:disabled) { border-color: var(--mmc-accent); }
/* Held: the strip is showing and cannot be left while the piece carries
   fields the shot face has no slot for. Still lit — the view it names is the
   one on screen — but dimmed and dead, with the reason in its tooltip. */
.mmc-pill.mmc-piece-toggle.on:disabled { opacity: .55; cursor: not-allowed; }

/* --- the next shot -------------------------------------------------------- */
/* Where a piece of one shot grows a second one. It lives in the tail of the
   pill row, with the route badge and the Timeline pill: the one part of the
   panel that is about the piece rather than about this shot.

   It was a dashed perforation rail across the whole body — a horizon line spent
   on one quiet button, which the fullscreen shell then hid outright rather than
   draw. Quiet is still right (most renders are one shot), so it is quiet the way
   a pill is quiet: dimmed until you are on it, with only the mark taking the
   accent. Loud enough to find in a row you already read, small enough to be
   wrong nine times out of ten without being in the way. */
.mmc-grow-shot { color: var(--mmc-dim); }
.mmc-grow-shot:hover:not(:disabled) { color: var(--mmc-text); }
.mmc-grow-mark {
  font-size: calc(14px * var(--mmc-type)); line-height: 1; color: var(--mmc-off);
  transition: color .12s ease;
}
.mmc-grow-shot:hover:not(:disabled) .mmc-grow-mark { color: var(--mmc-accent); }

/* The segment editor, over the strip, is the editor sheet — see styles/editor.js.
   Its body is the Creator node's, unchanged, and so is the window around it. */

/* --- timeline node body --------------------------------------------------- */

.mmc-tl-summary { gap: 14px; flex: 1; min-height: 0; }
/* The room grows; the text does not. On a tall node the room soaks up the
   panel's free height so the reel and the pills dock at the bottom, next to
   the sampler rows — the shot face's silhouette. On a node sized by content
   the room is only as tall as the clamped text, so nothing balloons. */
.mmc-tl-summary-room {
  display: flex; flex-direction: column;
  flex: 1 1 auto; min-height: 40px; cursor: text;
}
/* Clamped by lines, not by its flex parent: the node body takes its height from
   what is in it, so "fill the room and hide the rest" gives a prompt of any
   length all the room it asks for — flex against a parent that grows is not
   a bound at all, and a pasted log made the node taller than the canvas. The
   max-height is the bound. Six lines at this size and leading is what the
   summary is for; the modal holds the rest. */
.mmc-tl-summary-prompt {
  font-size: calc(13px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-text);
  flex: 1 1 auto; min-height: calc(40px * var(--mmc-type)); max-height: calc(117px * var(--mmc-type)); overflow: hidden; word-break: break-word;
  -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 26px), transparent);
  mask-image: linear-gradient(to bottom, #000 calc(100% - 26px), transparent);
}
.mmc-tl-summary-prompt.empty { color: var(--mmc-off); }
/* Segments at their real relative lengths — the node's one honest picture of
   the timeline without room for the strip itself. */
.mmc-tl-reel {
  display: flex; flex-direction: column; gap: 3px; height: 40px; cursor: pointer; flex: 0 0 auto;
}
.mmc-tl-lane { display: flex; gap: 4px; flex: 1 1 auto; min-height: 0; overflow: hidden; }
/* A pass in the lane: its shots close ranks and share one outline, which is the
   casing's reading at a tenth the size. A pass of one is just its own tick. */
.mmc-tl-run { display: flex; gap: 4px; min-width: 0; }
.mmc-tl-run.on {
  gap: 0; border: 1px solid color-mix(in srgb, var(--mmc-accent) 32%, transparent); border-radius: 8px; padding: 1px;
  background: color-mix(in srgb, var(--mmc-accent) 8%, transparent);
}
.mmc-tl-run.on .mmc-tl-tick {
  background: none; border: 0; border-left: 1px dashed color-mix(in srgb, var(--mmc-accent) 40%, transparent); border-radius: 0;
}
.mmc-tl-run.on .mmc-tl-tick:first-child { border-left: 0; }
.mmc-tl-tick {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  border-radius: 8px; min-width: 18px; overflow: hidden; padding: 0 4px;
}
.mmc-tl-tick svg { width: 13px; height: 13px; stroke: currentColor; fill: none;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; flex: 0 0 auto; }
.mmc-tl-tick-n { color: var(--mmc-text); font-size: calc(12px * var(--mmc-type)); font-weight: 500; }
.mmc-tl-tick-s { color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); }
.mmc-tl-lane:hover .mmc-tl-tick { border-color: var(--mmc-line-2); }
/* Where the shoot has got to, at a tenth the size of the strip's own picture of
   it: a block filled in because that stretch of film exists, hollowed out
   because it has not been shot. Same two readings the cards wear, minus the
   perforations, which at eighteen pixels would be a smudge. */
.mmc-tl-tick.kept { background: var(--mmc-surface-3); }
.mmc-tl-tick.unshot { background: none; border-style: dashed; }
.mmc-tl-tick.unshot .mmc-tl-tick-n, .mmc-tl-tick.unshot .mmc-tl-tick-s { color: var(--mmc-off); }
.mmc-tl-tick.on {
  background: color-mix(in srgb, var(--mmc-accent) 13%, transparent); border-color: color-mix(in srgb, var(--mmc-accent) 32%, transparent); color: var(--mmc-accent);
}
.mmc-tl-tick.on .mmc-tl-tick-n { color: var(--mmc-accent); }

/* --- the crowded reel ------------------------------------------------------

   Past about forty shots a block is twenty pixels wide, and a tile with a
   number, a length and a rounded border is a smear. So the lane closes: no
   gaps, no radius, one continuous band divided by frame lines, and the labels
   move off the picture and onto the edge. What is drawn inside the band is only
   what is not true of the whole strip — a merged pass, a hard cut — because a
   mark every shot carries is a mark that says nothing.

   Set from fitLane(), which measures rather than counts: the same forty shots
   are roomy on a wide node and crowded on a narrow one. */

.mmc-tl-lane.dense {
  gap: 0; border: 1px solid var(--mmc-line); border-radius: 4px;
  /* Lit from the top, so the row of cells reads as one physical strip rather
     than as a grid of empty boxes. */
  background: linear-gradient(180deg, var(--mmc-wash), transparent 60%),
              var(--mmc-surface-2);
}
.mmc-tl-lane.dense .mmc-tl-run { gap: 0; flex-basis: 0; }
.mmc-tl-lane.dense .mmc-tl-tick {
  border: 0; border-left: 1px solid var(--mmc-line); border-radius: 0;
  background: none; min-width: 0; padding: 0;
  /* Length alone decides the width here. With the default auto basis a block
     starts at the width of its own label and grows from there, so a two-digit
     number quietly buys its shot a few pixels the shot has not earned — which
     at this scale is most of a block. */
  flex-basis: 0;
}
.mmc-tl-lane.dense .mmc-tl-run:first-child .mmc-tl-tick:first-child { border-left: 0; }
.mmc-tl-lane.dense .mmc-tl-tick-n { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-tl-lane.dense .mmc-tl-tick.on .mmc-tl-tick-n { color: var(--mmc-dim); }
/* What a block gives up as it narrows, in order. The length goes first — a band
   drawn to scale is already a picture of the lengths — and the seam glyph goes
   with it, since the join itself says that. Then the number. Set per block by
   fitLane(), so a short shot beside a long one gives up its own labels without
   taking the long one's with it. */
.mmc-tl-tick.narrow .mmc-tl-tick-s,
.mmc-tl-tick.narrow svg { display: none; }
.mmc-tl-tick.bare .mmc-tl-tick-n { display: none; }
/* And nothing at all once no block on the lane can hold a number: the band goes
   bare and the edge row below does the counting. */
.mmc-tl-lane.crowded .mmc-tl-tick-n,
.mmc-tl-lane.crowded .mmc-tl-tick-s,
.mmc-tl-lane.crowded .mmc-tl-tick svg { display: none; }
/* Continuing is the ordinary case in a long strip, so it is drawn as the
   ordinary case: an unbroken band. */
.mmc-tl-lane.dense .mmc-tl-tick.on { background: none; border-color: var(--mmc-line); }
/* A hard cut is the exception, so it is the thing that shows: a real break in
   the film with a bright edge on the far side of it — a splice. */
.mmc-tl-lane.dense .mmc-tl-tick.cut {
  margin-left: 3px; border-left-color: transparent;
  box-shadow: inset 2px 0 0 var(--mmc-line-3);
}
/* A pass keeps its accent — four of them among forty single shots is exactly
   the reading worth spending colour on. Drawn as an inset ring rather than a
   border and padding, which at this width would steal four pixels from the run
   and quietly bend the proportions the lane exists to show. */
.mmc-tl-lane.dense .mmc-tl-run.on {
  border: 0; border-radius: 0; padding: 0;
  background: color-mix(in srgb, var(--mmc-accent) 16%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mmc-accent) 42%, transparent);
}
.mmc-tl-lane.dense .mmc-tl-run.on .mmc-tl-tick { border-left: 1px dashed color-mix(in srgb, var(--mmc-accent) 50%, transparent); }
.mmc-tl-lane.dense .mmc-tl-tick:hover { background: var(--mmc-wash-2); }
/* The band is one click target, so the band as a whole answers the pointer —
   the frame lines inside it are structure, not forty separate buttons. */
.mmc-tl-lane.dense:hover { border-color: var(--mmc-line-2); }

/* Edge code: the numerals down the side of the film, not across the frame.
   Placed in pixels by fitLane() against the blocks it measured, so a number
   sits on the shot it names however the durations divide the lane. */
.mmc-tl-edge { position: relative; flex: 0 0 10px; }
.mmc-tl-edge:empty { display: none; }
.mmc-tl-edge-n {
  position: absolute; top: 0; padding-left: 3px;
  border-left: 1px solid var(--mmc-line-2);
  font-size: calc(9px * var(--mmc-type)); line-height: 10px; color: var(--mmc-dim);
  font-variant-numeric: tabular-nums; letter-spacing: .04em;
}

/* Where the Creator puts its mode badge: the right end of the pill row. */
.mmc-tl-open {
  margin-left: auto; height: var(--mmc-pill-h); padding: 0 14px; display: flex; align-items: center; gap: 8px;
  border-radius: 999px; background: var(--mmc-surface-3); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-family: inherit; font-size: calc(13px * var(--mmc-type)); cursor: pointer;
}
.mmc-tl-open:hover { background: var(--mmc-surface-3); border-color: var(--mmc-line-2); }
.mmc-tl-open svg { width: 16px; height: 16px; stroke: currentColor; fill: none;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }

/* --- sampler pills -------------------------------------------------------- */

/* A pill that only reports. Same shape, no hover lift — it is not a control. */
.mmc-pill-static { cursor: default; }
.mmc-pill-static:hover { background: var(--mmc-surface-2); }
.mmc-pill-static svg { color: var(--mmc-dim); }
/* The seed pill's two icon buttons — the die that rolls it, the arrow that puts
   the last one back — under one rule, because they sit side by side and any
   difference between them reads as a mistake rather than as a distinction. The
   arrow inherited neither: an SVG in a button with no flex sits on the text
   baseline, so it rode above the die, and .mmc-pill svg drew it a pixel larger
   at 16. Centred both ways and the same 15px for both. */
.mmc-seed-dice, .mmc-seed-last {
  display: flex; align-items: center; justify-content: center;
  /* Narrower than a stepper's +/-, which is what .mmc-step is sized for: two
     34px boxes around 15px of glyph put 68px of nothing in front of the digits.
     Still a 26px target, and the row's rhythm is set by the ink, not the box. */
  width: 22px; padding: 0 2px;
}
.mmc-seed-dice svg, .mmc-seed-last svg {
  width: 15px; height: 15px; stroke: currentColor; fill: none;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round;
}
/* The die is a closed square and the arrow an open arc, so at equal stroke the
   arrow reads lighter than its neighbour. A hair more weight, not a larger
   glyph — the boxes stay identical. */
.mmc-seed-last svg { stroke-width: 1.85; }
/* The seed is an identifier, not a quantity — nobody reads it as one billion
   and something, they compare it against another one and copy it. So it is set
   the way the sheet sets a hash: mono, tabular, every digit in its own column,
   which is what makes "is this the same seed" answerable at a glance. The width
   comes from the digit count (see samplingBar) and one ch is one digit in this
   face; the bounds below are guard rails, not the size. */
.mmc-seed-input {
  background: none; border: 0; outline: none; color: var(--mmc-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
  font-size: calc(12.5px * var(--mmc-type)); text-align: center; padding: 0;
  min-width: 5ch; max-width: 21ch;
}
/* A typed value inside a pill: the manifest's "text" control, whose one user so
   far is the block list LTX's detail guidance degrades. The seed field's face —
   mono, so a comma-separated list reads as a list — with its own bounds, since
   what is in it is names rather than a fixed count of digits. */
.mmc-pill-text {
  background: none; border: 0; outline: none; color: var(--mmc-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(12.5px * var(--mmc-type)); text-align: center; padding: 0;
  min-width: 3ch; max-width: 18ch;
}
/* The seed as one small pill (sampling.seedPill): two halves, like the set
   beside it — a die that rolls it, and the seed's own mark. Hidden by default —
   only the simple view shows it, and that rule is the shell's
   (styles/fullscreen.js), since which face has folded the sampler row away is
   the shell's to know. */
.mmc-seed-pill { display: none; gap: 0; padding: 0; overflow: hidden; cursor: default; }
/* One half: the same box whichever glyph it holds, on the pill or on the ghost,
   so the four glyphs land on two centres and the ghost is the pill's twin. */
.mmc-seed-cell {
  display: flex; align-items: center; justify-content: center; flex: none;
  width: 34px; height: 100%; padding: 0; background: none; border: 0;
  color: var(--mmc-dim); font: inherit;
}
.mmc-seed-cell + .mmc-seed-cell { border-left: 1px solid var(--mmc-line); }
.mmc-seed-cell > svg {
  width: 20px; height: 20px; stroke: currentColor; fill: none;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round;
}
.mmc-seed-roll, .mmc-seed-id { cursor: pointer; }
/* Each half answers on its own, so both press-targets show before a click. A
   wash of ink rather than a surface: the simple view paints the pill in the
   surface a hover would otherwise reach for. */
.mmc-seed-roll:hover { color: var(--mmc-strong); background: color-mix(in srgb, var(--mmc-strong) 7%, transparent); }
.mmc-seed-roll svg { transition: transform .18s ease; }
.mmc-seed-roll:active svg { transform: rotate(90deg); }
/* The ink is the state. White: a glyph like any other, and the next render
   rolls again. Accent on a lit half: this seed, every render — the pressed
   stop of a set, in the pack's own colour for a thing that is held. Hovering
   a fresh mark shows the accent it would take. */
.mmc-seed-id { color: var(--mmc-strong); }
.mmc-seed-id:hover { color: var(--mmc-accent); background: color-mix(in srgb, var(--mmc-strong) 7%, transparent); }
.mmc-seed-pill[data-mode="kept"] .mmc-seed-id {
  color: var(--mmc-accent); background: color-mix(in srgb, var(--mmc-accent) 14%, transparent);
}
.mmc-seed-pill[data-mode="kept"] .mmc-seed-id:hover { background: color-mix(in srgb, var(--mmc-accent) 24%, transparent); }
/* The mark: five by five, mirrored, in whatever ink its holder has. Fill
   only — the pill's rule strokes every svg at 1.7, which in a 5-unit box is a
   third of a cell and welds the mark into one solid square. */
.mmc-seed-mark { display: flex; }
.mmc-seed-mark svg { display: block; width: 14px; height: 14px; stroke: none; }
.mmc-seed-fieldrow .mmc-seed-mark svg { width: 16px; height: 16px; }
.mmc-seed-mark rect { fill: currentColor; stroke: none; }
/* The last render's seed, as a ghost beside the pill — the pill's own two
   halves, in dim ink, with no fill and a dashed line, because it is an offer
   and not a state; drawn only while it differs from the seed on the pill
   (sampling.seedPill decides). Press it and it is the seed, kept. */
.mmc-seed-ghost {
  display: none; gap: 0; padding: 0; overflow: hidden; background: none;
  border: 1px dashed var(--mmc-line-2); color: var(--mmc-dim);
}
.mmc-seed-ghost .mmc-seed-cell + .mmc-seed-cell { border-left-style: dashed; border-left-color: var(--mmc-line-2); }
.mmc-seed-ghost:hover { border-style: solid; background: none; }
.mmc-seed-ghost:hover .mmc-seed-cell { color: var(--mmc-strong); }
/* The editor under the mark: the number, typeable, with its mark beside it
   following the keys, and the two ways a seed can go after a render. */
/* As wide as its two ways need, never narrower than the field wants: at a
   larger text size a fixed 250 broke "Fresh every render" onto two lines. */
.mmc-seed-pop { width: max-content; min-width: 250px; padding: 10px; }
.mmc-seed-fieldrow {
  display: flex; align-items: center; gap: 8px; height: 38px; padding: 0 10px 0 9px;
  background: var(--mmc-bg); border: 1px solid var(--mmc-line); border-radius: 12px;
  color: var(--mmc-strong);
}
.mmc-seed-fieldrow .mmc-seed-mark { flex: none; }
.mmc-seed-field {
  flex: 1; min-width: 0; max-width: none; text-align: left;
  font-size: calc(14px * var(--mmc-type)); letter-spacing: .03em; color: var(--mmc-strong);
}
.mmc-seed-ways {
  display: grid; grid-template-columns: 1fr 1fr; gap: 2px; padding: 3px; margin-top: 8px;
  background: var(--mmc-bg); border: 1px solid var(--mmc-line); border-radius: 12px;
}
.mmc-seed-way {
  height: 28px; padding: 0 12px; border: 0; border-radius: 9px; background: none; color: var(--mmc-dim);
  font: inherit; font-size: calc(12.5px * var(--mmc-type)); cursor: pointer; white-space: nowrap;
}
.mmc-seed-way:hover { color: var(--mmc-text); }
.mmc-seed-way[aria-checked="true"] { background: var(--mmc-surface-3); color: var(--mmc-strong); }

/* Dim on "fixed" — the default, and the state where nothing happens to the seed
   between queues. The three that do move it read at full strength. */
.mmc-seed-mode { font-size: calc(11px * var(--mmc-type)); padding: 0 8px 0 4px; color: var(--mmc-off); }
.mmc-seed-mode.on { color: var(--mmc-text); }
/* Sampler lists are long; the popover scrolls rather than running off screen. */
.mmc-pop-scroll { max-height: 320px; overflow-y: auto; min-width: 190px; }

/* ---- the sound lane -------------------------------------------------------

   Four rows that share one axis: a header, the piece drawn to scale, the band,
   and the clock. The strip above them is not on that axis and cannot be — see
   sound.js — which is exactly why the reel is here: it is the bridge between
   the storyboard's reading and the clock's.

   The reel says which shot, the ruler says which second, and the cut guides
   carry the first answer down through the second so a cue can be seen crossing
   a boundary rather than measured against one.

   Everything inside the tracks is positioned as a percentage of the whole, so
   the lane survives the modal being resized without measuring anything. */
.mmc-snd { display: flex; flex-direction: column; gap: 6px; }
/* An author rule that sets display beats the user agent's hidden-attribute rule
   whatever the specificity, so the lane this hides (timeline.js, for a family
   that supplies no audio) stayed on screen with the attribute set. The spinner
   in base.js carries the same line for the same reason. */
.mmc-snd[hidden] { display: none; }
.mmc-snd-head {
  display: flex; align-items: center; gap: 10px;
  font-size: calc(11px * var(--mmc-type));
}
.mmc-snd-head .mmc-snd-name { color: var(--mmc-text); font-weight: 500; }
.mmc-snd-hint { color: var(--mmc-dim); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* The only line that names the gestures. Dimmer than the count beside it — it
   is there to be found once and then stopped being read. */
.mmc-snd-how { color: var(--mmc-off); flex: 0 1 auto; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* At the header's own size, not .mmc-ghost's 14px — the same override the
   pass rail's Split button makes, for the same reason. */
.mmc-snd-add { flex: none; font-size: calc(11px * var(--mmc-type)); }

/* The piece to scale. Deliberately slight — it is a ruler, not a second strip,
   and anything taller starts competing with the cards it is explaining. */
.mmc-snd-reel { position: relative; height: calc(17px * var(--mmc-type)); }
.mmc-snd-pass {
  position: absolute; top: 0; bottom: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--mmc-surface-3); border-radius: 3px;
  color: var(--mmc-dim); font-size: calc(10px * var(--mmc-type));
  /* The gap between passes is the cut, and it is drawn by inset rather than by
     a margin so the block's own left edge stays the true frame it starts on —
     which is what the lane below snaps to. */
  box-shadow: inset 1px 0 0 var(--mmc-bg), inset -1px 0 0 var(--mmc-bg);
  overflow: hidden;
}
/* Supplied footage: solid, because that film exists — the same statement the
   strip makes about a clip card. */
.mmc-snd-pass.clip { background: var(--mmc-wash-2); color: var(--mmc-text); }
.mmc-snd-pass.kept { background: var(--mmc-wash-2); }
.mmc-snd-pass.unshot { background: none; box-shadow: inset 0 0 0 1px var(--mmc-line); }
/* Pointing at a shot is a question about where it is, and the lane answers. */
.mmc-snd-pass:hover { color: var(--mmc-text); background: var(--mmc-wash-3); }

/* The lane holds two zones that share its axis and must never overlap: the band,
   which is placed in time, and the gutter, which belongs to the cards. A
   reference drawn across a block would read as being *under* it — as though it
   were the sound there — which is the one thing this surface must not imply. */
.mmc-snd-lane {
  position: relative; height: calc(52px * var(--mmc-type));
  border-radius: 8px; background: var(--mmc-surface); overflow: hidden;
  border: 1px solid var(--mmc-line);
}
.mmc-snd-lane.has-refs { height: calc(68px * var(--mmc-type)); }

/* Where the shots cut, drawn through the sound rather than beside it. Dashed
   so it reads as a guide and not as an edge of something — the only solid
   vertical lines in this lane are the ends of blocks, and a cut is not one. */
/* Over the band rather than under it. Under, a cut vanished the moment a block
   or a gap's own fill was laid across it — which is every cut worth seeing.
   Stopped at the gutter, because a reference belongs to a shot and drawing the
   shot's own boundary through it would say it was placed in time. */
.mmc-snd-cuts { position: absolute; inset: 0; z-index: 2; pointer-events: none; }
.mmc-snd-lane.has-refs .mmc-snd-cuts { bottom: calc(16px * var(--mmc-type)); }
.mmc-snd-cut {
  position: absolute; top: 0; bottom: 0; width: 1px; margin-left: -1px;
  background: repeating-linear-gradient(180deg,
    color-mix(in srgb, var(--mmc-ink) 42%, transparent) 0 4px, transparent 4px 8px);
}
/* The stretch one shot owns, lit while its block in the reel is pointed at.
   Bracketed at both ends, because the question being asked is where it starts
   and stops and a wash alone answers neither precisely. */
.mmc-snd-shot {
  position: absolute; top: 0; bottom: 0; opacity: 0; pointer-events: none;
  background: var(--mmc-wash-2); transition: opacity .12s ease;
  box-shadow: inset 1px 0 0 var(--mmc-line-3), inset -1px 0 0 var(--mmc-line-3);
}
.mmc-snd-shot.on { opacity: 1; }
/* The band. Always full: what is not a block is a gap, and a gap is the model
   writing the sound rather than an absence. */
.mmc-snd-band { position: absolute; left: 0; right: 0; top: 0; bottom: 0; }
.mmc-snd-lane.has-refs .mmc-snd-band { bottom: calc(16px * var(--mmc-type)); }
.mmc-snd-refs {
  position: absolute; left: 0; right: 0; bottom: 0;
  height: calc(16px * var(--mmc-type));
  border-top: 1px solid var(--mmc-line);
  background: var(--mmc-bg);
}
/* The perforations, in a layer of their own under the band. A drag redraws them
   on every move — the block it is carrying leaves one stretch and covers
   another — and it cannot redraw the list the block itself is in without
   pulling the pointer out of the document with it. */
.mmc-snd-gaps { position: absolute; left: 0; right: 0; top: 0; bottom: 0; }
.mmc-snd-lane.has-refs .mmc-snd-gaps { bottom: calc(16px * var(--mmc-type)); }

/* Perforated, in the same grammar the strip uses for film that does not exist
   yet. The label is dim and small: it names the state, it does not advertise
   it. */
.mmc-snd-gap {
  position: absolute; top: 0; bottom: 0;
  display: flex; align-items: center; justify-content: center;
  background-image: repeating-linear-gradient(90deg,
    var(--mmc-surface-3) 0 7px, transparent 7px 17px);
  color: var(--mmc-off); font-size: calc(9px * var(--mmc-type));
  letter-spacing: .04em; pointer-events: none;
}
.mmc-snd-gap span { background: var(--mmc-surface); padding: 0 6px; border-radius: 4px; }

/* A laid-down track. The blue is the trim bar's, on purpose: what you drag here
   is the same act as what you drag in the trim modal, and a second accent for
   it would say they were different things. */
.mmc-snd-block {
  position: absolute; top: 3px; bottom: 3px;
  border-radius: 6px; overflow: hidden; cursor: grab;
  background: color-mix(in srgb, var(--mmc-blue) 26%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mmc-blue) 55%, transparent);
}
.mmc-snd-block:active { cursor: grabbing; }
.mmc-snd-block:hover { background: color-mix(in srgb, var(--mmc-blue) 34%, transparent); }
.mmc-snd-block:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
/* Lifted over its neighbours while it is being dragged, so a block butted up
   against a wall still reads as the one in hand. */
.mmc-snd-block.dragging {
  z-index: 3; background: color-mix(in srgb, var(--mmc-blue) 40%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mmc-blue) 85%, transparent),
              0 2px 10px var(--mmc-shadow-soft);
}
.mmc-snd-wave {
  position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none;
}
/* Inset past the grips at both ends, so the name never sits on a handle. The
   shadow is what keeps it readable over a loud waveform — a scrim box behind it
   would cut a hole in the very thing the block is drawn to show. */
.mmc-snd-label {
  position: absolute; left: 13px; right: 13px; top: 4px;
  display: flex; gap: 6px; align-items: baseline; justify-content: space-between;
  pointer-events: none;
  font-size: calc(10px * var(--mmc-type)); overflow: hidden; white-space: nowrap;
  text-shadow: 0 1px 3px var(--mmc-bg), 0 0 6px var(--mmc-bg);
}
.mmc-snd-file { color: var(--mmc-text); overflow: hidden; text-overflow: ellipsis; }
.mmc-snd-len { color: var(--mmc-dim); flex: none; font-variant-numeric: tabular-nums; }

/* Wide enough to grab on a trackpad, narrow enough not to eat a short block.
   Drawn at rest, unlike the rest of this pack's handles: the whole complaint
   about this lane was that nothing said a block could be trimmed, and a handle
   that only exists once you are already on top of it says it too late. Faint
   until then, so six tracks do not read as a fence. */
.mmc-snd-grip {
  position: absolute; top: 0; bottom: 0; width: 11px; border: 0; padding: 0;
  background: none; cursor: ew-resize; opacity: .5;
  transition: opacity .12s ease;
}
.mmc-snd-grip.head { left: 0; }
.mmc-snd-grip.tail { right: 0; }
.mmc-snd-block:hover .mmc-snd-grip,
.mmc-snd-block.dragging .mmc-snd-grip,
.mmc-snd-grip:focus-visible { opacity: 1; }
.mmc-snd-grip::after {
  content: ""; position: absolute; top: 4px; bottom: 4px; left: 4px; width: 3px;
  border-radius: 2px; background: var(--mmc-blue);
  box-shadow: 0 0 0 1px var(--mmc-scrim-2);
}
.mmc-snd-grip:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }

/* Takes the track off the lane. Bottom right, because the label runs along the
   top and the grips hold both ends — this is the one corner of a block nothing
   else is using, on a block as narrow as the shortest one the lane allows.
   Drawn at rest on the grips' terms and faint like them, so a lane of six
   tracks is not a row of crosses.

   The box is always this size and only ever paints when the block is under the
   pointer. That split is the whole control: the target has to be constant or
   the press lands on a cross that grew after the aim, and the chrome has to be
   conditional or every block wears a button it is not being asked about. What
   is left at rest is a faint mark, which is all the resting state has to say —
   there is something here — and what arrives on hover is a chip solid enough to
   read over a waveform's loudest stretch, which is what this corner is. */
.mmc-snd-drop {
  position: absolute; right: 11px; bottom: 3px; z-index: 2;
  display: grid; place-items: center; width: 18px; height: 18px;
  border: 1px solid transparent; border-radius: 5px; padding: 0;
  background: none; cursor: pointer; color: var(--mmc-text); opacity: .5;
  transition: opacity .12s ease, background .12s ease, border-color .12s ease;
}
.mmc-snd-drop svg {
  width: 11px; height: 11px; stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round;
  /* The mark carries its own legibility at rest, when it has no chip behind it
     and the peaks it is drawn over are whatever the file happens to be loud at. */
  filter: drop-shadow(0 1px 2px var(--mmc-bg)) drop-shadow(0 0 4px var(--mmc-bg));
}
.mmc-snd-block:hover .mmc-snd-drop, .mmc-snd-drop:focus-visible {
  opacity: 1; background: var(--mmc-scrim-2);
  border-color: color-mix(in srgb, var(--mmc-blue) 55%, transparent);
}
.mmc-snd-block:hover .mmc-snd-drop svg, .mmc-snd-drop:focus-visible svg { filter: none; }
.mmc-snd-drop:hover {
  color: var(--mmc-warn);
  background: color-mix(in srgb, var(--mmc-warn) 18%, var(--mmc-scrim-2));
  border-color: color-mix(in srgb, var(--mmc-warn) 65%, transparent);
}
.mmc-snd-drop:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
/* Nothing to remove mid-drag, and a cross under the pointer during one is a
   target the gesture can end on by accident. */
.mmc-snd-block.dragging .mmc-snd-drop { opacity: 0; pointer-events: none; }

/* Where the block has got to, while it is being moved or trimmed. The piece's
   clock, not the file's: a drag is a question about the cut. Clamped off the
   lane's own edges so a block at 0:00 still reads its numbers in full. */
.mmc-snd-read {
  position: absolute; top: 50%; z-index: 4; transform: translate(-50%, -50%);
  /* Built with the lane and moved by the drag, so it has to be invisible until
     there is a drag to talk about. */
  opacity: 0;
  display: flex; gap: 7px; align-items: baseline; pointer-events: none;
  padding: 3px 8px; border-radius: 5px; white-space: nowrap;
  background: var(--mmc-float); border: 1px solid var(--mmc-line-2);
  box-shadow: 0 2px 10px var(--mmc-shadow-soft);
  font-size: calc(10px * var(--mmc-type)); font-variant-numeric: tabular-nums;
}
.mmc-snd-read.on { opacity: 1; }
.mmc-snd-read-at { color: var(--mmc-text); }
.mmc-snd-read-len { color: var(--mmc-accent); }

/* The clock. Ticks only where a number is written — a ruler with minor marks
   between them would out-detail the band it is measuring. */
.mmc-snd-ruler {
  position: relative; height: calc(15px * var(--mmc-type));
  font-size: calc(9px * var(--mmc-type)); color: var(--mmc-off);
  font-variant-numeric: tabular-nums;
}
.mmc-snd-tick { position: absolute; top: 0; }
.mmc-snd-tick::before {
  content: ""; position: absolute; top: 0; left: -1px; width: 1px; height: 4px;
  background: var(--mmc-line-3);
}
.mmc-snd-tick span {
  position: absolute; top: 5px; left: 0; transform: translateX(-50%);
  white-space: nowrap;
}
.mmc-snd-tick.first span { transform: none; }
/* The length of the piece, hung inside its own end so it cannot be clipped. */
.mmc-snd-tick.last span { transform: translateX(-100%); }
.mmc-snd-tick.last { color: var(--mmc-dim); }

/* An imitation reference, under the card it is attached to. A hairline because
   it is not placed in time — the shot decides where it is — and dashed because
   what it asks for is a resemblance rather than a signal. */
.mmc-snd-ref {
  position: absolute; top: 2px; bottom: 2px;
  display: flex; align-items: center; padding: 0 6px; overflow: hidden;
  border-radius: 3px;
  border: 1px dashed color-mix(in srgb, var(--mmc-ink) 22%, transparent);
  color: var(--mmc-off); font-size: calc(9px * var(--mmc-type));
  white-space: nowrap; cursor: help;
}
/* The one take that is not imitation never draws as a hairline — it is the
   signal itself and appears as a block. Named here so the rule is visible
   rather than only implied by sound.js filtering it out. */
.mmc-snd-ref.take-copy { display: none; }

/* Why a drag stopped where it did. One hairline in the accent, which is the
   pack's word for "here". */
.mmc-snd-snap {
  position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px;
  z-index: 5; background: var(--mmc-accent); opacity: 0; pointer-events: none;
}
.mmc-snd-snap.on { opacity: .9; }

@media (prefers-reduced-motion: reduce) {
  .mmc-snd-block, .mmc-snd-grip, .mmc-snd-shot { transition: none; }
}

/* --- the reel ----------------------------------------------------------------
   The timeline as one window: one line of header, the script on the left, the
   player over the inspector on the right, and the piece at its real length
   underneath. Nothing is boxed that is not a separate thing: the script is set
   as text, the inspector as rows. Blue is a continuing picture, green is sound
   that carries over, the accent is the selection and anything that needs a
   look. */
.mmc-reel { display: flex; flex-direction: column; overflow: hidden; }
.mmc-reel-head {
  flex: none; display: flex; align-items: center; gap: 14px; height: 58px; padding: 0 18px 0 24px;
  border-bottom: 1px solid var(--mmc-line);
}
.mmc-reel-title { font-size: calc(17px * var(--mmc-type)); font-weight: 650; color: var(--mmc-strong); }
.mmc-reel-meta { color: var(--mmc-dim); font-size: calc(13.5px * var(--mmc-type)); font-variant-numeric: tabular-nums; }
.mmc-reel-plan { margin-left: auto; color: var(--mmc-dim); font-size: calc(13.5px * var(--mmc-type)); }
.mmc-reel-plan b { color: var(--mmc-text); font-weight: 550; }
.mmc-reel-plan i { font-style: normal; color: var(--mmc-role-voice); }
.mmc-reel-problem { color: var(--mmc-warn); font-size: calc(13px * var(--mmc-type)); }
.mmc-reel-shoot {
  height: 36px; padding: 0 18px; border-radius: 10px; border: 0; cursor: pointer;
  background: var(--mmc-accent); color: var(--mmc-on-accent); font: inherit; font-weight: 650;
  font-size: calc(14px * var(--mmc-type));
}
.mmc-reel-shoot:disabled { opacity: .45; cursor: default; }

.mmc-reel-main { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, 0.72fr); }
.mmc-reel-script { min-height: 0; overflow: auto; padding: 16px 24px 24px 18px; border-right: 1px solid var(--mmc-line); }
.mmc-reel-row { display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; align-items: baseline; gap: 6px; padding: 7px 10px 7px 0; border-radius: 12px; }
.mmc-reel-shot.selected { background: var(--mmc-tint); }
.mmc-reel-shot.merged .mmc-reel-gutter { border-left: 2px dotted var(--mmc-line-3); }
.mmc-reel-gutter { display: flex; flex-direction: column; align-items: flex-start; padding-left: 12px; }
.mmc-reel-label { font-size: calc(13px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-reel-num {
  font: inherit; font-weight: 650; font-size: calc(16px * var(--mmc-type)); color: var(--mmc-strong);
  background: none; border: 0; padding: 0; cursor: pointer; text-align: left;
}
.mmc-reel-num.ghost { color: var(--mmc-faint); cursor: default; }
.mmc-reel-shot.selected .mmc-reel-num { color: var(--mmc-accent); }
.mmc-reel-secs { font-variant-numeric: tabular-nums; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint); margin-top: 1px; }
/* The prompt box, set as text: no frame, no fill, the same box underneath. */
.mmc-reel-plain, .mmc-reel-plain .mmc-prompt { border: 0 !important; background: none !important; box-shadow: none !important; padding: 0 !important; min-height: 0 !important; }
.mmc-reel-plain .mmc-prompt { font-size: calc(16.5px * var(--mmc-type)); line-height: 1.55; color: var(--mmc-text); }
.mmc-reel-scene .mmc-reel-plain .mmc-prompt { font-size: calc(18.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-strong); }
.mmc-reel-plain .mmc-prompt:focus { outline: none; }
.mmc-reel-quiet { padding-top: 1px; padding-bottom: 1px; }
.mmc-reel-line-text {
  width: 100%; resize: none; overflow: hidden; border: 0; background: none; padding: 0; margin: 0;
  color: var(--mmc-dim); font: inherit; font-size: calc(15px * var(--mmc-type)); line-height: 1.5;
}
.mmc-reel-line-text:focus { outline: none; color: var(--mmc-text); }
.mmc-reel-line-text::placeholder { color: var(--mmc-faint); }
.mmc-reel-rule { height: 1px; background: var(--mmc-line); margin: 10px 0 10px 64px; }
.mmc-reel-clipname { font: inherit; text-align: left; background: none; border: 0; padding: 0; color: var(--mmc-dim); cursor: pointer; font-size: calc(15px * var(--mmc-type)); }
.mmc-reel-tag {
  align-self: center; white-space: nowrap; font-size: calc(11.5px * var(--mmc-type)); font-weight: 600;
  padding: 2px 8px; border-radius: 6px;
}
.mmc-reel-tag:empty { display: none; }
.mmc-reel-tag.changed, .mmc-reel-tag.reshoot { color: var(--mmc-on-accent); background: var(--mmc-accent); }
.mmc-reel-tag.gone { color: var(--mmc-bad); background: color-mix(in srgb, var(--mmc-bad) 14%, transparent); }
.mmc-reel-next-body { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
.mmc-reel-ghost {
  font: inherit; font-size: calc(16.5px * var(--mmc-type)); color: var(--mmc-faint); background: none; border: 0;
  padding: 0; cursor: text; text-align: left;
}
.mmc-reel-ghost:hover { color: var(--mmc-dim); }
.mmc-reel-ghost.small { font-size: calc(13.5px * var(--mmc-type)); color: var(--mmc-dim); cursor: pointer; }
.mmc-reel-ghost:disabled { cursor: not-allowed; opacity: .5; }

/* The cast and references, as faces and frames above the script. */
.mmc-reel-castrow { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 2px 0 14px 64px; }
.mmc-reel-face {
  display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 12px 0 3px; border-radius: 999px;
  border: 0; background: var(--mmc-surface); color: var(--mmc-accent); font: inherit; font-weight: 550;
  font-size: calc(13.5px * var(--mmc-type)); cursor: pointer;
}
.mmc-reel-face.frame { color: var(--mmc-role-motion); padding-left: 4px; }
.mmc-reel-face img, .mmc-reel-face-blank { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; background: var(--mmc-surface-3); display: grid; place-items: center; color: var(--mmc-dim); }
.mmc-reel-face.frame img, .mmc-reel-face.frame .mmc-reel-face-blank { width: 38px; height: 26px; border-radius: 6px; }
.mmc-reel-face.selected { box-shadow: 0 0 0 2px var(--mmc-accent); }
.mmc-reel-face-add {
  width: 32px; height: 32px; border-radius: 50%; border: 1px dashed var(--mmc-line-3); background: none;
  color: var(--mmc-dim); display: grid; place-items: center; cursor: pointer;
}
.mmc-reel-face-add:hover { color: var(--mmc-strong); border-color: var(--mmc-strong); }
.mmc-reel-hint { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-faint); }

/* The side: the player, then the inspector. */
.mmc-reel-side { min-height: 0; display: flex; flex-direction: column; }
.mmc-reel-player {
  position: relative; flex: none; margin: 16px 20px 0; height: clamp(150px, 24vh, 290px); border-radius: 14px;
  overflow: hidden; background: var(--mmc-media-bg);
}
.mmc-reel-media { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.mmc-reel-blank {
  position: absolute; inset: 0; display: grid; place-items: center; padding: 20px; text-align: center;
  color: var(--mmc-dim); background: repeating-linear-gradient(135deg, var(--mmc-surface) 0 14px, var(--mmc-surface-2) 14px 28px);
}
.mmc-reel-plabel, .mmc-reel-tc {
  position: absolute; top: 12px; padding: 4px 10px; border-radius: 8px; font-size: calc(13px * var(--mmc-type));
  color: #fff; background: rgba(0, 0, 0, .58);
}
.mmc-reel-plabel { left: 12px; }
.mmc-reel-tc { right: 12px; font-variant-numeric: tabular-nums; }
.mmc-reel-tc:empty { display: none; }
.mmc-reel-play {
  position: absolute; left: 50%; top: 50%; width: 54px; height: 54px; margin: -27px; border-radius: 50%; border: 0;
  background: rgba(0, 0, 0, .5); color: #fff; display: grid; place-items: center; cursor: pointer; transition: opacity .2s;
}
.mmc-reel-play.playing { opacity: 0; }
.mmc-reel-player:hover .mmc-reel-play.playing { opacity: .8; }
.mmc-reel-inspect { flex: 1; min-height: 0; overflow: auto; padding: 16px 20px 22px; }
.mmc-reel-inspect-body { display: flex; flex-direction: column; gap: 8px; }
.mmc-reel-ihead { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin-bottom: 4px; }
.mmc-reel-ihead b { font-size: calc(19px * var(--mmc-type)); color: var(--mmc-strong); font-weight: 650; }
.mmc-reel-ihead > span { color: var(--mmc-dim); font-size: calc(13.5px * var(--mmc-type)); }
.mmc-reel-ihead .mmc-reel-tag { align-self: baseline; }
.mmc-reel-why { margin: 0 0 4px; color: var(--mmc-text); line-height: 1.5; font-size: calc(14px * var(--mmc-type)); max-width: 60ch; }
.mmc-reel-irow { display: grid; grid-template-columns: 136px minmax(0, 1fr); align-items: center; gap: 12px; min-height: 34px; }
.mmc-reel-ilabel { color: var(--mmc-dim); font-size: calc(13.5px * var(--mmc-type)); }
.mmc-reel-icontrol { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; min-width: 0; }
.mmc-reel .mmc-seed-pill, .mmc-reel .mmc-seed-ghost { display: flex; }
.mmc-reel-inline { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.mmc-reel-note { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.45; }
.mmc-reel-mono { font-variant-numeric: tabular-nums; color: var(--mmc-text); }
.mmc-reel-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 2px 0 6px; }
.mmc-reel-actions.quiet { margin-top: 8px; padding-top: 10px; border-top: 1px solid var(--mmc-line); }
.mmc-reel-btn {
  display: inline-flex; align-items: center; gap: 7px; height: 32px; padding: 0 14px; border-radius: 10px;
  border: 1px solid var(--mmc-line-2); background: var(--mmc-surface); color: var(--mmc-text);
  font: inherit; font-size: calc(13.5px * var(--mmc-type)); cursor: pointer;
}
.mmc-reel-btn:hover { background: var(--mmc-surface-2); }
.mmc-reel-btn.primary { background: var(--mmc-accent); color: var(--mmc-on-accent); border-color: transparent; font-weight: 650; }
.mmc-reel-btn.quiet { background: none; border-color: transparent; color: var(--mmc-dim); padding: 0 10px; }
.mmc-reel-btn.quiet:hover { color: var(--mmc-strong); background: var(--mmc-wash); }
.mmc-reel-btn.danger, .mmc-reel-btn.quiet.danger { color: var(--mmc-bad); }
.mmc-reel-btn:disabled { opacity: .4; cursor: not-allowed; }
.mmc-reel-link {
  font: inherit; font-size: calc(13px * var(--mmc-type)); background: none; border: 0; padding: 2px 4px;
  color: var(--mmc-accent); cursor: pointer; border-radius: 5px;
}
.mmc-reel-link:hover { background: var(--mmc-wash); }
.mmc-reel-value {
  display: inline-flex; align-items: baseline; gap: 8px; height: 32px; padding: 0 12px; border-radius: 9px;
  border: 0; background: var(--mmc-surface-2); color: var(--mmc-strong); font: inherit; font-size: calc(13.5px * var(--mmc-type)); cursor: pointer;
}
.mmc-reel-value small { color: var(--mmc-dim); font-size: calc(11.5px * var(--mmc-type)); }
.mmc-reel-value { align-items: center; }
.mmc-reel-value svg { color: var(--mmc-dim); }
.mmc-reel .mmc-refine-split { display: inline-flex; align-items: center; position: static; }
.mmc-reel .mmc-refine-split .mmc-tool-icon { display: none; }
.mmc-reel .mmc-refine-split .mmc-reel-btn { border-radius: 10px 0 0 10px; }
.mmc-reel .mmc-refine-more {
  position: static; height: 32px; width: 30px; border: 1px solid var(--mmc-line-2); border-left: 0;
  border-radius: 0 10px 10px 0; background: var(--mmc-surface); color: var(--mmc-dim); cursor: pointer;
  display: grid; place-items: center; padding: 0;
}
.mmc-reel-family .mmc-pill { height: 32px; border-radius: 9px; border: 0; background: var(--mmc-surface-2); }
.mmc-reel-seg { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 3px; border-radius: 10px; background: var(--mmc-surface-2); }
.mmc-reel-seg button {
  display: inline-flex; align-items: baseline; gap: 5px; border: 0; background: none; padding: 5px 11px; border-radius: 8px;
  color: var(--mmc-dim); font: inherit; font-size: calc(13px * var(--mmc-type)); cursor: pointer;
}
.mmc-reel-seg button small { font-variant-numeric: tabular-nums; font-size: calc(11px * var(--mmc-type)); opacity: .75; }
.mmc-reel-seg button[aria-pressed="true"] { background: var(--mmc-bg); color: var(--mmc-strong); box-shadow: 0 1px 2px var(--mmc-shadow-soft); }
.mmc-reel-seg.motion button[aria-pressed="true"] { color: var(--mmc-role-motion); }
.mmc-reel-seg.voice button[aria-pressed="true"] { color: var(--mmc-role-voice); }
.mmc-reel-seg button:disabled { opacity: .38; cursor: not-allowed; }
.mmc-reel-switch {
  position: relative; width: 38px; height: 22px; border-radius: 11px; border: 0; padding: 0; cursor: pointer;
  background: var(--mmc-surface-3); flex: none;
}
.mmc-reel-switch::after {
  content: ""; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%;
  background: var(--mmc-dim); transition: transform .15s;
}
.mmc-reel-switch[aria-checked="true"] { background: var(--mmc-accent); }
.mmc-reel-switch[aria-checked="true"]::after { transform: translateX(16px); background: var(--mmc-on-accent); }
.mmc-reel-switch:disabled { opacity: .4; cursor: not-allowed; }
.mmc-reel-stepper { display: inline-flex; align-items: center; border-radius: 9px; background: var(--mmc-surface-2); overflow: hidden; }
.mmc-reel-stepper button { width: 28px; height: 30px; border: 0; background: none; color: var(--mmc-dim); cursor: pointer; font: inherit; }
.mmc-reel-stepper button:hover { color: var(--mmc-strong); }
.mmc-reel-stepper span { min-width: 56px; text-align: center; font-variant-numeric: tabular-nums; font-size: calc(13px * var(--mmc-type)); color: var(--mmc-strong); }
.mmc-reel-seed {
  width: 150px; height: 30px; padding: 0 10px; border-radius: 9px; border: 0; background: var(--mmc-surface-2);
  color: var(--mmc-strong); font: inherit; font-variant-numeric: tabular-nums; font-size: calc(13px * var(--mmc-type));
}
.mmc-reel-seed::placeholder { color: var(--mmc-dim); }
.mmc-reel-thumbs { display: flex; flex-wrap: wrap; gap: 8px; }
.mmc-reel-thumbs img, .mmc-reel-thumb-blank, .mmc-reel-thumb-add { width: 62px; height: 40px; border-radius: 7px; object-fit: cover; }
.mmc-reel-thumb-blank { display: grid; place-items: center; background: var(--mmc-surface-2); color: var(--mmc-dim); }
.mmc-reel-thumb-add { display: grid; place-items: center; border: 1px dashed var(--mmc-line-3); background: none; color: var(--mmc-dim); cursor: pointer; }
.mmc-reel-loras { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.mmc-reel-lora {
  display: inline-flex; align-items: baseline; gap: 6px; padding: 4px 10px; border-radius: 7px; border: 0;
  background: color-mix(in srgb, var(--mmc-role-voice) 15%, transparent); color: var(--mmc-role-voice);
  font: inherit; font-size: calc(13px * var(--mmc-type)); cursor: pointer;
}
.mmc-reel-lora small { font-variant-numeric: tabular-nums; font-size: calc(11px * var(--mmc-type)); opacity: .8; }
.mmc-reel-lora.off { opacity: .45; }
.mmc-reel-machine { margin-top: 10px; padding-top: 12px; border-top: 1px solid var(--mmc-line); font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.5; }
.mmc-reel-compiled { white-space: pre-wrap; font-size: calc(13px * var(--mmc-type)); line-height: 1.55; color: var(--mmc-text); margin: 0; padding: 4px 2px; }

/* The reel: to scale, the one place lengths are compared. */
.mmc-reel-foot { flex: none; border-top: 1px solid var(--mmc-line); background: color-mix(in oklab, var(--mmc-bg) 94%, var(--mmc-media-bg)); padding: 12px 22px 0; }
.mmc-reel-lane { overflow: hidden; }
.mmc-reel-track-area { position: relative; display: flex; flex-direction: column; gap: 3px; }
.mmc-reel-passes { position: relative; height: 16px; }
.mmc-reel-pass {
  position: absolute; top: 0; height: 16px; border: 1px solid var(--mmc-line-3); border-bottom: 0;
  border-radius: 6px 6px 0 0; font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-dim);
  padding: 0 8px; overflow: hidden; white-space: nowrap; box-sizing: border-box;
}
.mmc-reel-picture { position: relative; height: 84px; }
.mmc-reel-card {
  position: absolute; top: 0; height: 84px; padding: 0; border-radius: 8px; overflow: hidden; cursor: pointer;
  border: 1px solid var(--mmc-line-2); color: var(--mmc-text); font: inherit; text-align: left;
  background: repeating-linear-gradient(135deg, var(--mmc-surface) 0 9px, var(--mmc-surface-2) 9px 18px);
}
.mmc-reel-card.kept, .mmc-reel-card.reshoot, .mmc-reel-card.changed { background: var(--mmc-media-bg); }
.mmc-reel-card.selected { box-shadow: 0 0 0 2px var(--mmc-accent); z-index: 2; }
.mmc-reel-thumb { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.mmc-reel-card-head {
  position: absolute; left: 8px; top: 6px; display: flex; gap: 6px; align-items: baseline;
  font-size: calc(12.5px * var(--mmc-type)); color: #fff; text-shadow: 0 1px 3px rgba(0, 0, 0, .8);
}
.mmc-reel-card-head span { font-variant-numeric: tabular-nums; font-size: calc(11px * var(--mmc-type)); }
.mmc-reel-card.new .mmc-reel-card-head { color: var(--mmc-strong); text-shadow: none; }
.mmc-reel-card-text {
  position: absolute; left: 8px; right: 12px; top: 26px; font-size: calc(12px * var(--mmc-type)); line-height: 1.3;
  color: var(--mmc-dim); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
}
.mmc-reel-card-tag {
  position: absolute; left: 7px; bottom: 6px; z-index: 5; font-size: calc(10.5px * var(--mmc-type)); font-weight: 650;
  padding: 1px 7px; border-radius: 5px; background: var(--mmc-accent); color: var(--mmc-on-accent);
}
.mmc-reel-card-tag.gone { background: var(--mmc-bad); color: #fff; }
.mmc-reel-edge { position: absolute; top: 0; right: 0; width: 10px; height: 100%; cursor: ew-resize; display: grid; place-items: center; z-index: 3; }
.mmc-reel-edge::after { content: ""; width: 2px; height: 24px; border-radius: 1px; background: rgba(255, 255, 255, .45); }
.mmc-reel-card:hover .mmc-reel-edge::after { background: #fff; }
.mmc-reel-blend {
  position: absolute; top: -3px; height: 90px; z-index: 4; border-radius: 6px; pointer-events: none;
  border: 1.5px solid var(--mmc-role-motion);
  background: repeating-linear-gradient(135deg, color-mix(in srgb, var(--mmc-role-motion) 40%, transparent) 0 3px, transparent 3px 7px);
}
.mmc-reel-blend.selected { box-shadow: 0 0 0 2px var(--mmc-accent); }
.mmc-reel-grip {
  position: absolute; right: -6px; top: 50%; width: 11px; height: 28px; margin-top: -14px; border-radius: 4px;
  background: var(--mmc-role-motion); cursor: ew-resize; pointer-events: auto;
}
.mmc-reel-joins { position: relative; height: 28px; }
.mmc-reel-join {
  position: absolute; top: 1px; width: 26px; height: 26px; margin-left: -13px; border-radius: 50%; padding: 0;
  display: grid; place-items: center; cursor: pointer; background: var(--mmc-bg); color: var(--mmc-dim);
  border: 1.5px solid var(--mmc-line-3);
}
.mmc-reel-join.on { color: var(--mmc-role-motion); border-color: var(--mmc-role-motion); }
.mmc-reel-join.merged { border-style: dashed; color: var(--mmc-faint); }
.mmc-reel-join.selected { box-shadow: 0 0 0 3px color-mix(in srgb, var(--mmc-accent) 60%, transparent); }
.mmc-reel-sound { position: relative; height: 26px; }
.mmc-reel-wave {
  position: absolute; top: 5px; height: 16px; border-radius: 3px;
  background: repeating-linear-gradient(90deg, color-mix(in srgb, var(--mmc-role-voice) 55%, transparent) 0 2px, transparent 2px 5px);
}
.mmc-reel-sdot {
  position: absolute; top: 6px; width: 14px; height: 14px; margin-left: -7px; border-radius: 50%; padding: 0; z-index: 2;
  background: var(--mmc-bg); border: 1.5px solid var(--mmc-line-3); cursor: pointer;
}
.mmc-reel-sdot.on { border-color: var(--mmc-role-voice); background: var(--mmc-role-voice); }
.mmc-reel-track {
  position: absolute; top: 1px; height: 24px; border-radius: 6px; padding: 0 8px; z-index: 3; cursor: pointer;
  border: 1px solid var(--mmc-role-voice); background: color-mix(in oklab, var(--mmc-role-voice) 26%, var(--mmc-bg));
  color: var(--mmc-strong); font: inherit; font-size: calc(11.5px * var(--mmc-type)); text-align: left;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.mmc-reel-track.selected { box-shadow: 0 0 0 2px var(--mmc-accent); }
.mmc-reel-status { display: flex; align-items: center; gap: 16px; padding: 8px 0 10px; }
.mmc-reel-status .mmc-reel-link { color: var(--mmc-text); }
.mmc-reel-status .mmc-reel-hint { margin-left: auto; }

@media (max-width: 900px) {
  .mmc-reel-main { grid-template-columns: minmax(0, 1fr); }
  .mmc-reel-script { border-right: 0; }
}
`;
