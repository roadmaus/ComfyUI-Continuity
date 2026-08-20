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
.mmc-pill-group.off-distribution { border-color: rgba(224,116,60,.4); }
.mmc-pill-group.off-distribution > span { color: #e0743c; }
.mmc-tl-dur.off-distribution { color: #e0743c; }

/* Almost the whole screen, like the shot window: the strip is the one thing in
   this pack that is genuinely wide — a ten-card piece is a metre of film — and
   every pixel not given to it is a card you have to scroll for. The overlay's
   40px inset is what keeps it a window rather than a page. */
.mmc-tl-modal { width: min(1800px, 100%); height: 100%; }
.mmc-tl-body {
  display: flex; flex-direction: column; gap: 16px;
  padding: 18px 24px 24px; overflow: auto; flex: 1; min-height: 0;
}
.mmc-tl-prompt {
  width: 100%; box-sizing: border-box; min-height: 84px; max-height: 30vh; resize: vertical;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line); border-radius: 14px;
  color: var(--mmc-text); font-family: inherit; font-size: 14px; line-height: 1.5;
  padding: 14px 16px; outline: none;
}
.mmc-tl-prompt:focus { border-color: rgba(255,255,255,.2); }
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
.mmc-tl-prompt-frame:focus-within { border-color: rgba(255,255,255,.2); }
.mmc-tl-prompt-frame .mmc-prompt {
  font-size: 14px; line-height: 1.5; min-height: 56px; max-height: 26vh;
}

/* The two Context-IR audio fields, side by side under the prompt. They wrap to
   one column when the modal is too narrow to give each a readable measure. */
.mmc-tl-audio {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px;
}
.mmc-tl-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
/* Named for the field they become, not prettified: the value goes into the
   prompt under exactly this key, and someone comparing against MiniMax's guide
   should be able to find it by the same word. */
.mmc-tl-field-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; color: var(--mmc-dim); letter-spacing: .02em;
}
.mmc-tl-small { min-height: 64px; font-size: 13px; padding: 10px 12px; }

/* The piece's reference pool: a shelf between the audio fields and the bar.
   Chips reuse the editor's asset row; what is ours here is only the head line
   and the "used in segments 2, 4" readout. */
.mmc-tl-pool { display: flex; flex-direction: column; gap: 8px; }
.mmc-tl-pool-head { display: flex; gap: 10px; align-items: center; min-width: 0; }
.mmc-tl-pool-hint {
  font-size: 11px; color: var(--mmc-off); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-tl-pool-add { display: inline-flex; gap: 5px; align-items: center; }
.mmc-tl-pool-where { font-size: 11px; color: var(--mmc-dim); white-space: nowrap; }
/* The handle is a button: clicking it writes the citation into the global
   prompt. Reset to read exactly like the editor's handle span. */
.mmc-tl-pool-cite {
  background: none; border: 0; padding: 0; font: inherit; cursor: pointer;
}
.mmc-tl-pool-cite:hover { text-decoration: underline; }

/* The cast shelf sits between the pool and the bar, in a host of its own. The
   shelf itself is mounted from cast.js and wears the stylesheet next door,
   because the same shelf is mounted on the node face. */
.mmc-tl-cast { min-width: 0; }

.mmc-tl-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.mmc-pill.on { border-color: rgba(255,255,255,.22); }
/* An accelerator that is doing something. Lit rather than merely outlined,
   because a render with one on is not a native render and that is worth seeing
   without reading the pill. */
.mmc-pill.accel-on { border-color: rgba(110,190,255,.45); color: #6ebeff; }
.mmc-pill.accel-on:hover:not(:disabled) { border-color: rgba(110,190,255,.7); }
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
.mmc-pill.mmc-experimental { border-style: dashed; border-color: rgba(255,196,110,.5); }
.mmc-pill.mmc-experimental:hover:not(:disabled) { border-color: rgba(255,196,110,.8); }
/* A sweep choice inside the dev popover: the same on/off reading as the turbo
   stops, on ordinary pills because the lists are of no fixed length. */
.mmc-pill[aria-pressed="true"] { border-color: rgba(110,190,255,.45); color: #6ebeff; }
/* The turbo switch: the seed pill's shape — one pill, a big half that throws
   it and a small half that picks what it throws. Both inherit the group's
   colour so the accelerator blue lights the whole pill, chevron included. */
.mmc-turbo-main {
  display: flex; align-items: center; gap: 7px; height: 100%; padding: 0 2px 0 8px;
  background: none; border: 0; color: inherit; font-size: 13px;
  font-family: inherit; cursor: pointer; white-space: nowrap;
}
.mmc-turbo-pick {
  display: flex; align-items: center; justify-content: center; width: 22px; color: inherit;
}
/* The turbo quality stops. One pill holding three mutually exclusive answers,
   like the trim editor's track switch — three loose pills would read as
   independent toggles, and draft/med/good are one dial. Lit in the accelerator
   blue, because that is the family it belongs to. */
.mmc-pill.mmc-turbo-seg { gap: 0; padding: 0; overflow: hidden; }
.mmc-turbo-opt {
  display: flex; align-items: center; gap: 5px; height: 100%; padding: 0 12px;
  background: none; border: 0; border-left: 1px solid var(--mmc-line);
  color: var(--mmc-dim); font-size: 13px; font-family: inherit; cursor: pointer;
}
.mmc-turbo-opt:first-child { border-left: 0; }
.mmc-turbo-opt:hover { color: #ededed; }
.mmc-turbo-opt[aria-pressed="true"] { background: rgba(110,190,255,.14); color: #6ebeff; }
.mmc-turbo-opt[aria-pressed="true"] .mmc-pill-sub { color: rgba(110,190,255,.75); }
.mmc-tl-total { display: flex; gap: 8px; align-items: baseline; margin-left: auto; font-size: 13px; }
.mmc-tl-total span { color: var(--mmc-dim); }

/* Chained / one pass. A segmented control rather than two pills, because they
   are one choice with two answers and every other pill on this bar is a value
   you set independently. It leads the bar for the same reason: it is the one
   control that changes what all the others mean. */
.mmc-tl-render {
  display: flex; gap: 2px; padding: 2px; border-radius: 10px;
  background: var(--mmc-surface-3); border: 1px solid var(--mmc-line);
}
/* Laid out rather than left to the button's own centring, because the middle
   position is a span and an inline box would sit its text a couple of pixels
   above the two buttons' — which is exactly what it looked like. */
.mmc-tl-render-opt {
  display: flex; align-items: center; justify-content: center;
  height: 24px; padding: 0 10px; border: 0; border-radius: 8px; background: none;
  color: var(--mmc-dim); font-family: inherit; font-size: 12px; line-height: 1; cursor: pointer;
}
.mmc-tl-render-opt:hover { color: var(--mmc-text); }
.mmc-tl-render-opt.on { background: var(--mmc-surface); color: var(--mmc-text); }

/* A refusal compile.py would raise, said while the shots are still editable.
   Reads as a note rather than an alarm — the timeline is still saveable, and
   switching back to chained makes it correct again. */
.mmc-tl-problem {
  display: flex; gap: 8px; align-items: baseline;
  font-size: 11px; line-height: 1.4; color: #e0743c;
}
.mmc-tl-problem .mmc-note-key { color: inherit; opacity: .8; }

/* Laid out left to right and scrolled, not wrapped: a timeline that wraps onto
   a second line stops reading as time.
 *
 * Three rows shared by everything on it: the pass rails, the cards, and the
 * notes underneath. One grid rather than one height per column, because a rail
 * that only some columns have and a note that only one column carries used to
 * push their own cards up and down — cards ended up at three different heights
 * on the same strip. On the grid every rail sits on one line, every card top
 * and bottom on another, and a note under one pass moves nothing above it.
 * Columns are min-content so a card's set width is what sizes its column, and
 * a long note wraps into that width instead of stretching the pass to fit it.
 */
.mmc-tl-strip {
  display: grid; grid-auto-flow: column; grid-auto-columns: min-content;
  grid-template-rows: auto 1fr auto; row-gap: 6px;
  overflow-x: auto; padding-bottom: 10px; min-height: 190px;
}
/* The cards row, which is all a seam or the add button occupies: they have no
   rail above them and nothing to say underneath. */
.mmc-tl-seam, .mmc-tl-add { grid-row: 2; }
.mmc-tl-card {
  flex: 0 0 auto; box-sizing: border-box;
  display: flex; flex-direction: column; gap: 8px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 14px; padding: 12px; font-size: 12px; cursor: default;
}
.mmc-tl-card:hover { border-color: rgba(255,255,255,.18); }
.mmc-tl-card-head { display: flex; align-items: center; gap: 8px; }
.mmc-tl-index {
  width: 20px; height: 20px; border-radius: 50%; background: var(--mmc-surface-3);
  display: flex; align-items: center; justify-content: center; font-size: 11px; flex: 0 0 auto;
}
.mmc-tl-dur { color: var(--mmc-text); font-weight: 500; }
.mmc-tl-mode { color: var(--mmc-accent); font-size: 11px; margin-left: auto; }
.mmc-tl-card-prompt {
  flex: 1; color: var(--mmc-text); line-height: 1.45; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
}
.mmc-tl-card-prompt.empty { color: var(--mmc-off); font-style: italic; }
/* The card keeps showing the typed sentence because that is what the shot is
   recognised by — dimmed, because it is not what the shot queues. */
.mmc-tl-card-prompt.superseded { opacity: .42; }
.mmc-tl-card-meta {
  color: var(--mmc-dim); font-size: 11px;
  display: flex; align-items: center; gap: 6px;
}
/* This shot's half of the face pass. Unlit while the shot is opted out, so a
   strip tells you at a glance which cards are being repaired. */
.mmc-tl-card-face {
  border: 0; padding: 1px 6px; border-radius: 6px; cursor: pointer;
  background: var(--mmc-surface-3); color: var(--mmc-dim);
  font-size: 10px; font-family: inherit; margin-left: auto;
  /* The narrowest card wraps its meta text onto two lines; the chip is the
     part that must stay readable, so it neither shrinks nor breaks. */
  flex: none; white-space: nowrap;
}
.mmc-tl-card-face.on { background: rgba(90, 150, 255, 0.18); color: var(--mmc-blue); }
.mmc-tl-card-face:hover { filter: brightness(1.25); }
.mmc-tl-card-foot { display: flex; align-items: center; gap: 4px; }
.mmc-tl-edit {
  height: 26px; padding: 0 12px; border-radius: 8px; background: var(--mmc-surface-3);
  border: 0; color: var(--mmc-text); font-size: 12px; font-family: inherit; cursor: pointer;
  margin-right: auto;
}
.mmc-tl-edit:hover { background: #3a3a3a; }
.mmc-tl-card-foot .mmc-ghost { padding: 0 4px; font-size: 12px; }
.mmc-tl-card-foot button:disabled { opacity: .3; cursor: not-allowed; }

/* The seam between two cards. It is a control, so it is wide enough to hit. */
.mmc-tl-join {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  background: none; border: 0; color: var(--mmc-off); cursor: pointer;
  font-family: inherit; font-size: 10px; line-height: 1.25; padding: 4px 2px;
  border-radius: 8px;
}
.mmc-tl-join span:first-child { font-size: 15px; line-height: 1; }
.mmc-tl-join:hover:not(:disabled) { color: var(--mmc-text); background: var(--mmc-surface-2); }
.mmc-tl-join.on { color: var(--mmc-accent); }
.mmc-tl-join:disabled { cursor: not-allowed; opacity: .5; }

/* Picture above, sound below — the two switches on one seam. Stacked rather
   than side by side so the seam stays as narrow as it was.
 *
 * The padding is the card's own — the enclosure's inset plus the card's padding
 * and head — so the switches open level with the first line of the prompt beside
 * them and the merge button sits on the row of Edit buttons. A seam carrying two
 * chips and a seam carrying four then open and close on the same two lines,
 * instead of each centring itself on a different height. */
.mmc-tl-seam {
  width: 78px; box-sizing: border-box; padding: 47px 3px 19px;
  display: flex; flex-direction: column; align-items: stretch; gap: 2px;
}
/* The join inside a pass. Not the seam's two switches, because there is no seam
   to switch: what it shows is the cut time the description will carry, and what
   clicking it does is split the pass back apart. Narrow, and without the seam's
   breathing room on either side — the cards it separates are one piece of film
   and should look it. */
.mmc-tl-cut {
  flex: 0 0 auto; align-self: stretch;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  width: 52px; padding: 0; border: 0; border-left: 1px dashed rgba(240,166,60,.32);
  background: none; color: rgba(240,166,60,.55); font-family: inherit; font-size: 9px;
  font-variant-numeric: tabular-nums; cursor: pointer;
}
.mmc-tl-cut span:first-child { font-size: 13px; }
.mmc-tl-cut:hover { color: var(--mmc-accent); border-left-color: var(--mmc-accent); }

/* --- a piece shot a pass at a time ----------------------------------------

   A card is in the next render, or it is not. When it is not, the difference
   worth drawing is whether the film exists yet — so the two off states borrow
   the two marks this strip already had for exactly those facts, and nothing new
   is invented and no new colour is spent.

   None of it draws on a strip that has never held anything back, which is every
   strip anyone has rendered so far. */

/* A card playing the take it already has. Solid, which is the clip card's skin
   and for the clip card's stated reason: the difference worth seeing at a
   glance is that this stretch of the piece already exists. Deliberately no
   accent — a kept card is the one thing on the strip that will cost nothing,
   and what deserves the eye is what is about to run. */
.mmc-tl-card.mmc-tl-kept { background: var(--mmc-surface-3); }

/* A card that has not been shot yet: raw stock. The perforation rail the grow
   control wears, which in this pack already means film that has not been
   through the gate — here across the top of the card instead of across the
   panel. Emptied of its fill rather than faded out: everything on it is still
   set, still readable and still editable, which is the whole of what holding a
   card is for. */
.mmc-tl-card.mmc-tl-unshot {
  position: relative; background: none; border-color: rgba(255,255,255,.06);
}
.mmc-tl-card.mmc-tl-unshot::before {
  content: ""; position: absolute; left: 10px; right: 10px; top: 5px; height: 4px;
  background-image: repeating-linear-gradient(90deg,
    var(--mmc-surface-3) 0 8px, transparent 8px 20px);
}
.mmc-tl-card.mmc-tl-unshot .mmc-tl-card-prompt,
.mmc-tl-card.mmc-tl-unshot .mmc-tl-dur { color: var(--mmc-dim); }

/* What a locked card is locked as, in the row that already carries what the
   card costs. The word is a readout — the lock beside the mode badge is the
   switch that changes it — and the only thing it can be clicked for is to stop
   having a take at all. Absent while the card is simply in the render with
   nothing rendered yet, because that is the ordinary state and a mark every
   card carries says nothing. */
.mmc-tl-card-state {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 1px 6px; border-radius: 6px; margin-left: auto;
  background: var(--mmc-surface-3); color: var(--mmc-dim);
  font-size: 10px; flex: none; white-space: nowrap;
}
/* A take that came back and has not been ruled on. Amber, the strip's own
   colour for what the piece is made of, because an undecided take is the one
   thing here that is waiting on the user. */
.mmc-tl-card-state.ready { background: rgba(240,166,60,.16); color: var(--mmc-accent); }
/* ...and the take that has been. Brighter than "not shot" and nothing more:
   this is the state that costs nothing and needs nothing, so it reports and
   gets out of the way. */
.mmc-tl-card-state.kept { color: var(--mmc-text); }
/* ...and a kept take the card has stopped describing. The warm orange the
   off-distribution marks wear, meaning what it means there: a statement about
   what will happen, not a refusal. The take still plays. */
.mmc-tl-card-state.stale { background: rgba(224,116,60,.16); color: #e0743c; }

/* Looking at a take and deciding against it is half of shooting a piece in
   parts, and it is the one thing the strip had no word for: the way to reject a
   take was to render over it. This is that word, kept to a hairline and given
   no colour of its own — it inherits whatever the chip beside it is wearing, so
   the control is tinted by the state it acts on rather than adding a fourth
   colour to a 10px row.

   Out of sight until the card is under the pointer or the keyboard reaches it.
   A strip of finished takes should read as film rather than as a row of things
   to delete, and this is only wanted at the moment somebody has decided. */
.mmc-tl-take-x {
  border: 0; background: none; padding: 0; margin: 0 -2px 0 0;
  font: inherit; line-height: 1; color: inherit; cursor: pointer;
  opacity: 0; transition: opacity .12s ease;
}
.mmc-tl-card:hover .mmc-tl-take-x,
.mmc-tl-pass-head:hover .mmc-tl-take-x,
.mmc-tl-card:focus-within .mmc-tl-take-x,
.mmc-tl-pass-head:focus-within .mmc-tl-take-x { opacity: .55; }
.mmc-tl-take-x:hover, .mmc-tl-take-x:focus-visible { opacity: 1; }
/* A pointer that cannot hover has no way to reveal it, so there it simply is. */
@media (hover: none) { .mmc-tl-take-x { opacity: .55; } }
@media (prefers-reduced-motion: reduce) { .mmc-tl-take-x { transition: none; } }

/* The card's number, doubling as the way to shoot that number and nothing
   else. There is no room in a card's head for a control of its own — a
   five-second card runs out about 26 px after the lock — and the number is
   already what the card is called, so "shoot only 4" is said by clicking the 4.

   It looks exactly like the badge it replaces until it is pointed at, which is
   the whole of the restraint here: the resting strip is a row of numbered
   cards, and the verb surfaces where somebody is already looking. */
.mmc-tl-solo {
  border: 0; font: inherit; color: inherit; cursor: pointer;
  padding: 0; transition: background-color .12s ease, color .12s ease;
}
.mmc-tl-solo:hover, .mmc-tl-solo:focus-visible {
  background: var(--mmc-accent); color: #1a1206;
}
@media (prefers-reduced-motion: reduce) { .mmc-tl-solo { transition: none; } }

/* Lock all and Unlock all sit with Refine all and Revert all, and are the same
   shape of thing: one press for a gesture that is otherwise one press per card,
   offered only while it has something to do. */
.mmc-tl-holdall svg { stroke: currentColor; fill: none; stroke-width: 1.8;
  stroke-linecap: round; stroke-linejoin: round; }
.mmc-tl-holdall[disabled] { opacity: .45; cursor: not-allowed; }

/* The switch, in the card's head with the rest of what the card *is*. One
   control, one question — is this card in the next render — drawn as the one
   metaphor for it nobody has to be taught: a padlock, open or shut. Clicking a
   card that has just rendered is how a take is kept, because keeping is
   locking; there is no second button for it.

   Bigger than the glyphs beside it and given room to be hit. This is the
   control the whole feature is, and at the 10px a ghost button would otherwise
   draw it at, a lock is a smudge. */
.mmc-tl-hold {
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 20px; padding: 0; flex: 0 0 auto;
}
.mmc-tl-hold svg {
  width: 15px; height: 15px; stroke: currentColor; fill: none;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round;
}
/* Shut on a card whose film exists, and shut on one that has not been shot. The
   lock says only that the card is out of the render — which of the two it is
   the card's own skin says, and its chip names. */
.mmc-tl-hold.kept { color: var(--mmc-text); }
/* Dim, not off: what it marks is quiet, but the control is live and --mmc-off
   in this pack is what a dead button wears. */
.mmc-tl-hold.unshot { color: var(--mmc-dim); }

/* A pass of several shots wears it as one piece of film, because that is what
   it is: one generation, one take, one answer. The casing takes the skin the
   lone card takes, and the switch sits on the rail with the other things a pass
   has one of. */
.mmc-tl-pass.on.mmc-tl-kept .mmc-tl-pass-cards { background: var(--mmc-surface-3); }
/* The casing keeps its amber edge: a pass that has not been shot is still one
   generation, and that is the whole of what the casing says. Only the fill goes
   — it is what said the film exists. */
.mmc-tl-pass.on.mmc-tl-unshot .mmc-tl-pass-cards { position: relative; background: none; }
.mmc-tl-pass.on.mmc-tl-unshot .mmc-tl-pass-cards::before {
  content: ""; position: absolute; left: 12px; right: 12px; top: 3px; height: 4px;
  background-image: repeating-linear-gradient(90deg,
    var(--mmc-surface-3) 0 8px, transparent 8px 20px);
}
.mmc-tl-pass.on.mmc-tl-unshot .mmc-tl-card-prompt,
.mmc-tl-pass.on.mmc-tl-unshot .mmc-tl-dur { color: var(--mmc-dim); }
.mmc-tl-pass-head .mmc-tl-hold { flex: 0 0 auto; }

/* What this queue will make, when that is not the whole piece. Left of the
   total it is measured against, and in the strip's own amber: it is a fact
   about the piece's structure, like the pass casings and the cut marks, and it
   is the one number on this bar that changes with every click of a hold. */
.mmc-tl-next { color: var(--mmc-accent); }

/* --- passes --------------------------------------------------------------- */

/* Every card sits in one of these whether or not it shares it, so the cards
   line up whatever the runs look like. Only a pass holding more than one draws
   itself. It takes all three of the strip's rows and hands them straight to its
   rail, its cards and its note, so those line up across passes too. */
.mmc-tl-pass { grid-row: 1 / -1; display: grid; grid-template-rows: subgrid; }
/* Fills the enclosure so the cards inside go on stretching to the strip's
   height, which is what they did when they were its direct children. It carries
   the casing's inset and border whether or not the casing is drawn, so a card
   that shares a pass and a card that is one are the same box either way — the
   alternative was every merged card sitting 6 px shorter than its neighbours. */
.mmc-tl-pass-cards {
  display: flex; align-items: stretch; min-height: 0;
  padding: 5px; border: 1px solid transparent; border-radius: 16px;
}
/* The rail costs nothing until the strip has a pass in it — an untouched
   timeline is the strip it always was, with no empty band above the cards.
   Emptied rather than removed: it is the row every column is measured against,
   and a pass that dropped it would slide its cards up into the rail's line. */
.mmc-tl-pass-head { display: flex; height: 0; align-items: center; gap: 8px; padding: 0 4px; overflow: hidden; }
.mmc-tl-strip.has-pass .mmc-tl-pass-head { height: 20px; }

/* The casing: one generation, drawn as one piece of film. The cards inside give
   up their own borders and become panels of it. */
.mmc-tl-pass.on .mmc-tl-pass-cards {
  background: var(--mmc-surface-2); border-color: rgba(240,166,60,.32);
}
.mmc-tl-pass.on .mmc-tl-card { background: none; border-color: transparent; }
.mmc-tl-pass.on .mmc-tl-card:hover { border-color: rgba(255,255,255,.12); }
.mmc-tl-pass-name {
  display: flex; align-items: center; gap: 5px; color: var(--mmc-accent); font-size: 11px;
}
.mmc-tl-pass-name svg { width: 13px; height: 13px; stroke: currentColor; fill: none;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
/* The rail is as wide as the shots under it, which for a pass of two short ones
   is not much. The length is what gives first: the name says what the enclosure
   is and Split is the way out of it, and neither is worth losing to a number
   that is also on the bar. */
.mmc-tl-pass-name, .mmc-tl-pass-split { flex: 0 0 auto; }
.mmc-tl-pass-len {
  color: var(--mmc-dim); font-size: 11px;
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-tl-pass-len.off-distribution { color: #e0743c; }
.mmc-tl-pass-head .mmc-tl-mode { margin-left: 0; }
.mmc-tl-pass-split { margin-left: auto; font-size: 11px; }
/* The refusals compile.py would raise, under the pass they are about. */
.mmc-tl-pass .mmc-tl-problem { padding: 0 4px; }

/* The third answer on a seam: no seam at all. Held at the foot of the seam,
   level with the cards' own buttons, and set apart from the switches above it —
   they say how this join behaves, this says whether it is a join. */
.mmc-tl-join-merge {
  margin-top: auto; padding-top: 6px; border-top: 1px solid var(--mmc-line);
  border-radius: 0 0 8px 8px;
}
.mmc-tl-join-merge span:first-child { font-size: 12px; }
.mmc-tl-join-merge:hover:not(:disabled) { color: var(--mmc-accent); }

/* Reported, not offered: some seams merged and some not is a real state of the
   strip, but there is nothing for clicking it to do. So it is not dressed as
   the selected one of the two answers either — it wears the accent the merged
   passes below it wear, and reads as a readout wedged between them. */
.mmc-tl-render-opt.mmc-tl-render-mixed {
  cursor: default; color: var(--mmc-accent); background: rgba(240,166,60,.14);
}

.mmc-tl-join-sound { padding-top: 0; }
.mmc-tl-join-sound svg { width: 13px; height: 13px; stroke: currentColor; fill: none;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }

/* Where the seam inherits from — one line under the two switches, only shown
   while a seam is live and there is more than one segment to inherit from. */
.mmc-tl-join-from { padding-top: 0; }
.mmc-tl-join-from span:first-child { font-size: 10px; }

.mmc-tl-add {
  width: 108px; box-sizing: border-box; margin: 6px 0 6px 12px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
  background: none; border: 1px dashed var(--mmc-line); border-radius: 14px;
  color: var(--mmc-dim); font-family: inherit; font-size: 12px; cursor: pointer;
}
.mmc-tl-add span:first-child { font-size: 20px; }
.mmc-tl-add:hover:not(:disabled) { color: var(--mmc-text); border-color: rgba(255,255,255,.2); }
.mmc-tl-add:disabled { cursor: not-allowed; opacity: .4; }

/* Two ways to fill the next stretch of the piece: write one, or bring one.
   Stacked in a single tile so they read as one choice at one place on the
   strip rather than as two unrelated buttons. */
.mmc-tl-add-pair { grid-row: 2; display: flex; flex-direction: column; gap: 6px; }
.mmc-tl-add-pair .mmc-tl-add { margin: 0 0 0 12px; flex: 1; min-height: 0; }
.mmc-tl-add-pair .mmc-tl-add:first-child { margin-top: 6px; }
.mmc-tl-add-pair .mmc-tl-add:last-child { margin-bottom: 6px; }
.mmc-tl-add-pair .mmc-tl-add span:first-child { font-size: 15px; }
.mmc-tl-add-clip { border-style: solid; }

/* The piece-view toggle: which face this node is wearing while it holds one
   shot. Amber, because that is the strip's colour everywhere else in here — the
   lane's ticks, the pass casing, the cut marks — and pointedly not the
   accelerator blue the generic aria-pressed rule above would otherwise give it.
   Blue in this pack means "this render is not native", and a control that only
   decides what you are looking at has nothing to say about the render.

   Three classes, so it beats that rule wherever the two land in the cascade. */
.mmc-pill.mmc-piece-toggle.on {
  border-color: rgba(240,166,60,.45); color: var(--mmc-accent);
}
.mmc-pill.mmc-piece-toggle.on:hover:not(:disabled) { border-color: var(--mmc-accent); }
/* Held: the strip is showing and cannot be left while the piece carries
   fields the shot face has no slot for. Still lit — the view it names is the
   one on screen — but dimmed and dead, with the reason in its tooltip. */
.mmc-pill.mmc-piece-toggle.on:disabled { opacity: .55; cursor: not-allowed; }

/* --- the stretch after the shot ------------------------------------------- */
/* Where a piece of one shot grows a second one. The same perforation rail the
   leader wears, one card later and meaning the same thing: film that has not
   been shot yet. It sits between the prompt and the sampler row because that is
   where the next shot goes — part of what is being asked for, not of how it is
   run.

   Quiet, and it has to be: most renders are one shot, so a control that
   announced itself would be wrong nine times out of ten. It is the only thing
   between the panel and the sampler pills, which is what makes it findable
   without being loud. */
.mmc-tl-grow {
  position: relative; width: 100%; box-sizing: border-box;
  display: flex; align-items: center; justify-content: center; gap: 7px;
  padding: 13px 2px 3px; background: none; border: 0; border-radius: 8px;
  color: var(--mmc-dim); font-family: inherit; font-size: 12px; cursor: pointer;
  transition: color .12s ease;
}
.mmc-tl-grow::before {
  content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4px;
  background-image: repeating-linear-gradient(90deg,
    var(--mmc-surface-3) 0 8px, transparent 8px 20px);
}
.mmc-tl-grow:hover:not(:disabled) { color: var(--mmc-text); }
.mmc-tl-grow:disabled { cursor: not-allowed; opacity: .4; }
.mmc-tl-grow-mark { font-size: 14px; line-height: 1; color: var(--mmc-off); }
.mmc-tl-grow:hover:not(:disabled) .mmc-tl-grow-mark { color: var(--mmc-accent); }

/* A clip card. Solid where a shot's card is not, because the difference worth
   seeing at a glance is that this stretch of the piece already exists. */
.mmc-tl-clip { background: var(--mmc-surface-3); }
.mmc-tl-clip-tag { color: var(--mmc-dim); }
.mmc-tl-clip-name {
  font-style: normal; color: var(--mmc-text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-tl-seam-clip .mmc-tl-join.on { border-style: dashed; }

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
  font-size: 13px; line-height: 1.5; color: var(--mmc-text);
  flex: 1 1 auto; min-height: 40px; max-height: 117px; overflow: hidden; word-break: break-word;
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
  gap: 0; border: 1px solid rgba(240,166,60,.32); border-radius: 8px; padding: 1px;
  background: rgba(240,166,60,.08);
}
.mmc-tl-run.on .mmc-tl-tick {
  background: none; border: 0; border-left: 1px dashed rgba(240,166,60,.4); border-radius: 0;
}
.mmc-tl-run.on .mmc-tl-tick:first-child { border-left: 0; }
.mmc-tl-tick {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  background: var(--mmc-surface-2); border: 1px solid var(--mmc-line);
  border-radius: 8px; min-width: 18px; overflow: hidden; padding: 0 4px;
}
.mmc-tl-tick svg { width: 13px; height: 13px; stroke: currentColor; fill: none;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; flex: 0 0 auto; }
.mmc-tl-tick-n { color: var(--mmc-text); font-size: 12px; font-weight: 500; }
.mmc-tl-tick-s { color: var(--mmc-dim); font-size: 11px; }
.mmc-tl-lane:hover .mmc-tl-tick { border-color: rgba(255,255,255,.18); }
/* Where the shoot has got to, at a tenth the size of the strip's own picture of
   it: a block filled in because that stretch of film exists, hollowed out
   because it has not been shot. Same two readings the cards wear, minus the
   perforations, which at eighteen pixels would be a smudge. */
.mmc-tl-tick.kept { background: var(--mmc-surface-3); }
.mmc-tl-tick.unshot { background: none; border-style: dashed; }
.mmc-tl-tick.unshot .mmc-tl-tick-n, .mmc-tl-tick.unshot .mmc-tl-tick-s { color: var(--mmc-off); }
.mmc-tl-tick.on {
  background: rgba(240,166,60,.13); border-color: rgba(240,166,60,.32); color: var(--mmc-accent);
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
  background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,0) 60%),
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
.mmc-tl-lane.dense .mmc-tl-tick-n { font-size: 11px; color: var(--mmc-dim); }
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
  box-shadow: inset 2px 0 0 rgba(255,255,255,.34);
}
/* A pass keeps its accent — four of them among forty single shots is exactly
   the reading worth spending colour on. Drawn as an inset ring rather than a
   border and padding, which at this width would steal four pixels from the run
   and quietly bend the proportions the lane exists to show. */
.mmc-tl-lane.dense .mmc-tl-run.on {
  border: 0; border-radius: 0; padding: 0;
  background: rgba(240,166,60,.16); box-shadow: inset 0 0 0 1px rgba(240,166,60,.42);
}
.mmc-tl-lane.dense .mmc-tl-run.on .mmc-tl-tick { border-left: 1px dashed rgba(240,166,60,.5); }
.mmc-tl-lane.dense .mmc-tl-tick:hover { background: rgba(255,255,255,.13); }
/* The band is one click target, so the band as a whole answers the pointer —
   the frame lines inside it are structure, not forty separate buttons. */
.mmc-tl-lane.dense:hover { border-color: rgba(255,255,255,.20); }

/* Edge code: the numerals down the side of the film, not across the frame.
   Placed in pixels by fitLane() against the blocks it measured, so a number
   sits on the shot it names however the durations divide the lane. */
.mmc-tl-edge { position: relative; flex: 0 0 10px; }
.mmc-tl-edge:empty { display: none; }
.mmc-tl-edge-n {
  position: absolute; top: 0; padding-left: 3px;
  border-left: 1px solid rgba(255,255,255,.22);
  font-size: 9px; line-height: 10px; color: var(--mmc-dim);
  font-variant-numeric: tabular-nums; letter-spacing: .04em;
}

/* Where the Creator puts its mode badge: the right end of the pill row. */
.mmc-tl-open {
  margin-left: auto; height: 32px; padding: 0 14px; display: flex; align-items: center; gap: 8px;
  border-radius: 999px; background: var(--mmc-surface-3); border: 1px solid var(--mmc-line);
  color: var(--mmc-text); font-family: inherit; font-size: 13px; cursor: pointer;
}
.mmc-tl-open:hover { background: #3a3a3a; border-color: rgba(255,255,255,.18); }
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
  font-size: 12.5px; text-align: center; padding: 0;
  min-width: 5ch; max-width: 21ch;
}
/* Dim on "fixed" — the default, and the state where nothing happens to the seed
   between queues. The three that do move it read at full strength. */
.mmc-seed-mode { font-size: 11px; padding: 0 8px 0 4px; color: var(--mmc-off); }
.mmc-seed-mode.on { color: var(--mmc-text); }
/* Sampler lists are long; the popover scrolls rather than running off screen. */
.mmc-pop-scroll { max-height: 320px; overflow-y: auto; min-width: 190px; }

`;
