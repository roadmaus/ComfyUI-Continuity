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
.mmc-tl-dur.off-distribution { color: var(--mmc-warn); }

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
  display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px;
}
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
.mmc-tl-pool-add { display: inline-flex; gap: 5px; align-items: center; }
.mmc-tl-pool-where { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); white-space: nowrap; }
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
/* The global stack, under the pill that counts it. Empty when there is none —
   and then it must take no room at all, or the bar and the strip sit a gap
   apart for a feature nobody used. */
.mmc-tl-loras:empty { display: none; }
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
   colour so the accelerator blue lights the whole pill, chevron included. */
.mmc-turbo-main {
  display: flex; align-items: center; gap: 7px; height: 100%; padding: 0 2px 0 8px;
  background: none; border: 0; color: inherit; font-size: calc(13px * var(--mmc-type));
  font-family: inherit; cursor: pointer; white-space: nowrap;
}
.mmc-turbo-pick {
  display: flex; align-items: center; justify-content: center; width: 22px; color: inherit;
}
/* The turbo quality stops. One pill holding three mutually exclusive answers,
   like the trim editor's track switch — three loose pills would read as
   independent toggles, and draft/med/good are one dial. Lit in the accelerator
   blue, because that is the family it belongs to.

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
.mmc-turbo-opt[aria-pressed="true"] { background: color-mix(in srgb, var(--mmc-role-motion) 14%, transparent); color: var(--mmc-role-motion); }
.mmc-turbo-opt[aria-pressed="true"] .mmc-pill-sub { color: color-mix(in srgb, var(--mmc-role-motion) 75%, transparent); }
.mmc-tl-total { display: flex; gap: 8px; align-items: baseline; margin-left: auto; font-size: calc(13px * var(--mmc-type)); }
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
  height: calc(24px * var(--mmc-type)); padding: 0 10px; border: 0; border-radius: 8px; background: none;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12px * var(--mmc-type)); line-height: 1; cursor: pointer;
}
.mmc-tl-render-opt:hover { color: var(--mmc-text); }
.mmc-tl-render-opt.on { background: var(--mmc-surface); color: var(--mmc-text); }

/* A refusal compile.py would raise, said while the shots are still editable.
   Reads as a note rather than an alarm — the timeline is still saveable, and
   switching back to chained makes it correct again. */
.mmc-tl-problem {
  display: flex; gap: 8px; align-items: baseline;
  font-size: calc(11px * var(--mmc-type)); line-height: 1.4; color: var(--mmc-warn);
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
  border-radius: 14px; padding: 12px; font-size: calc(12px * var(--mmc-type)); cursor: default;
}
.mmc-tl-card:hover { border-color: var(--mmc-line-2); }
.mmc-tl-card-head { display: flex; align-items: center; gap: 8px; }
.mmc-tl-index {
  width: calc(20px * var(--mmc-type)); height: calc(20px * var(--mmc-type)); border-radius: 50%; background: var(--mmc-surface-3);
  display: flex; align-items: center; justify-content: center; font-size: calc(11px * var(--mmc-type)); flex: 0 0 auto;
}
.mmc-tl-dur { color: var(--mmc-text); font-weight: 500; }
.mmc-tl-mode { color: var(--mmc-accent); font-size: calc(11px * var(--mmc-type)); margin-left: auto; }
.mmc-tl-card-prompt {
  flex: 1; color: var(--mmc-text); line-height: 1.45; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
}
.mmc-tl-card-prompt.empty { color: var(--mmc-off); font-style: italic; }
/* The card keeps showing the typed sentence because that is what the shot is
   recognised by — dimmed, because it is not what the shot queues. */
.mmc-tl-card-prompt.superseded { opacity: .42; }
.mmc-tl-card-meta {
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type));
  display: flex; align-items: center; gap: 6px;
}
/* This shot's half of the face pass. Unlit while the shot is opted out, so a
   strip tells you at a glance which cards are being repaired. */
.mmc-tl-card-face {
  border: 0; padding: 1px 6px; border-radius: 6px; cursor: pointer;
  background: var(--mmc-surface-3); color: var(--mmc-dim);
  font-size: calc(10px * var(--mmc-type)); font-family: inherit; margin-left: auto;
  /* The narrowest card wraps its meta text onto two lines; the chip is the
     part that must stay readable, so it neither shrinks nor breaks. */
  flex: none; white-space: nowrap;
}
.mmc-tl-card-face.on { background: color-mix(in srgb, var(--mmc-blue) 18%, transparent); color: var(--mmc-blue); }
.mmc-tl-card-face:hover { filter: brightness(1.25); }
.mmc-tl-card-foot { display: flex; align-items: center; gap: 4px; }
.mmc-tl-edit {
  height: calc(26px * var(--mmc-type)); padding: 0 12px; border-radius: 8px; background: var(--mmc-surface-3);
  border: 0; color: var(--mmc-text); font-size: calc(12px * var(--mmc-type)); font-family: inherit; cursor: pointer;
  margin-right: auto;
}
.mmc-tl-edit:hover { background: var(--mmc-surface-3); }
.mmc-tl-card-foot .mmc-ghost { padding: 0 4px; font-size: calc(12px * var(--mmc-type)); }
.mmc-tl-card-foot button:disabled { opacity: .3; cursor: not-allowed; }

/* The seam between two cards. It is a control, so it is wide enough to hit. */
.mmc-tl-join {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  background: none; border: 0; color: var(--mmc-off); cursor: pointer;
  font-family: inherit; font-size: calc(10px * var(--mmc-type)); line-height: 1.25; padding: 4px 2px;
  border-radius: 8px;
}
.mmc-tl-join span:first-child { font-size: calc(15px * var(--mmc-type)); line-height: 1; }
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
  width: 52px; padding: 0; border: 0; border-left: 1px dashed color-mix(in srgb, var(--mmc-accent) 32%, transparent);
  background: none; color: color-mix(in srgb, var(--mmc-accent) 55%, transparent); font-family: inherit; font-size: calc(9px * var(--mmc-type));
  font-variant-numeric: tabular-nums; cursor: pointer;
}
.mmc-tl-cut span:first-child { font-size: calc(13px * var(--mmc-type)); }
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

/* A card that has not been shot yet: raw stock. A perforation rail across the
   top of the card, which in this pack means film that has not been through the
   gate. Emptied of its fill rather than faded out: everything on it is still
   set, still readable and still editable, which is the whole of what holding a
   card is for. */
.mmc-tl-card.mmc-tl-unshot {
  position: relative; background: none; border-color: var(--mmc-wash);
}
.mmc-tl-card.mmc-tl-unshot::before {
  content: ""; position: absolute; left: 10px; right: 10px; top: 5px; height: 4px;
  background-image: repeating-linear-gradient(90deg,
    var(--mmc-surface-3) 0 8px, transparent 8px 20px);
}
.mmc-tl-card.mmc-tl-unshot .mmc-tl-card-prompt,
.mmc-tl-card.mmc-tl-unshot .mmc-tl-dur { color: var(--mmc-dim); }
/* On a family with a duration head the seconds are a switch, so the chip is a
   button — stripped back to the text it already was, since what says it can be
   clicked is the hover and the lit state, not a box around a number. Lit in the
   accent the shot editor's own auto switch uses. After the unshot rule and at its
   specificity: a card on auto that has not been shot is still on auto. */
.mmc-tl-card button.mmc-tl-dur {
  border: 0; padding: 0; background: none; font: inherit; cursor: pointer;
}
.mmc-tl-card button.mmc-tl-dur:hover { color: var(--mmc-accent); }
.mmc-tl-card .mmc-tl-dur.auto { color: var(--mmc-accent); }

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
  font-size: calc(10px * var(--mmc-type)); flex: none; white-space: nowrap;
}
/* A take that came back and has not been ruled on. Amber, the strip's own
   colour for what the piece is made of, because an undecided take is the one
   thing here that is waiting on the user. */
.mmc-tl-card-state.ready { background: color-mix(in srgb, var(--mmc-accent) 16%, transparent); color: var(--mmc-accent); }
/* ...and the take that has been. Brighter than "not shot" and nothing more:
   this is the state that costs nothing and needs nothing, so it reports and
   gets out of the way. */
.mmc-tl-card-state.kept { color: var(--mmc-text); }
/* ...and a kept take the card has stopped describing. The warm orange the
   off-distribution marks wear, meaning what it means there: a statement about
   what will happen, not a refusal. The take still plays. */
.mmc-tl-card-state.stale { background: color-mix(in srgb, var(--mmc-warn) 16%, transparent); color: var(--mmc-warn); }

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
  background: var(--mmc-accent); color: var(--mmc-on-accent);
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
  background: var(--mmc-surface-2); border-color: color-mix(in srgb, var(--mmc-accent) 32%, transparent);
}
.mmc-tl-pass.on .mmc-tl-card { background: none; border-color: transparent; }
.mmc-tl-pass.on .mmc-tl-card:hover { border-color: var(--mmc-wash-2); }
.mmc-tl-pass-name {
  display: flex; align-items: center; gap: 5px; color: var(--mmc-accent); font-size: calc(11px * var(--mmc-type));
}
.mmc-tl-pass-name svg { width: 13px; height: 13px; stroke: currentColor; fill: none;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
/* The rail is as wide as the shots under it, which for a pass of two short ones
   is not much. The length is what gives first: the name says what the enclosure
   is and Split is the way out of it, and neither is worth losing to a number
   that is also on the bar. */
.mmc-tl-pass-name, .mmc-tl-pass-split { flex: 0 0 auto; }
.mmc-tl-pass-len {
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type));
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-tl-pass-len.off-distribution { color: var(--mmc-warn); }
.mmc-tl-pass-head .mmc-tl-mode { margin-left: 0; }
.mmc-tl-pass-split { margin-left: auto; font-size: calc(11px * var(--mmc-type)); }
/* The refusals compile.py would raise, under the pass they are about. */
.mmc-tl-pass .mmc-tl-problem { padding: 0 4px; }

/* The third answer on a seam: no seam at all. Held at the foot of the seam,
   level with the cards' own buttons, and set apart from the switches above it —
   they say how this join behaves, this says whether it is a join. */
.mmc-tl-join-merge {
  margin-top: auto; padding-top: 6px; border-top: 1px solid var(--mmc-line);
  border-radius: 0 0 8px 8px;
}
.mmc-tl-join-merge span:first-child { font-size: calc(12px * var(--mmc-type)); }
.mmc-tl-join-merge:hover:not(:disabled) { color: var(--mmc-accent); }

/* Reported, not offered: some seams merged and some not is a real state of the
   strip, but there is nothing for clicking it to do. So it is not dressed as
   the selected one of the two answers either — it wears the accent the merged
   passes below it wear, and reads as a readout wedged between them. */
.mmc-tl-render-opt.mmc-tl-render-mixed {
  cursor: default; color: var(--mmc-accent); background: color-mix(in srgb, var(--mmc-accent) 14%, transparent);
}

.mmc-tl-join-sound { padding-top: 0; }
.mmc-tl-join-sound svg { width: 13px; height: 13px; stroke: currentColor; fill: none;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }

/* Where the seam inherits from — one line under the two switches, only shown
   while a seam is live and there is more than one segment to inherit from. */
.mmc-tl-join-from { padding-top: 0; }
.mmc-tl-join-from span:first-child { font-size: calc(10px * var(--mmc-type)); }

.mmc-tl-add {
  width: 108px; box-sizing: border-box; margin: 6px 0 6px 12px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
  background: none; border: 1px dashed var(--mmc-line); border-radius: 14px;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(12px * var(--mmc-type)); cursor: pointer;
}
.mmc-tl-add span:first-child { font-size: calc(20px * var(--mmc-type)); }
.mmc-tl-add:hover:not(:disabled) { color: var(--mmc-text); border-color: var(--mmc-line-2); }
.mmc-tl-add:disabled { cursor: not-allowed; opacity: .4; }

/* Two ways to fill the next stretch of the piece: write one, or bring one.
   Stacked in a single tile so they read as one choice at one place on the
   strip rather than as two unrelated buttons. */
.mmc-tl-add-pair { grid-row: 2; display: flex; flex-direction: column; gap: 6px; }
.mmc-tl-add-pair .mmc-tl-add { margin: 0 0 0 12px; flex: 1; min-height: 0; }
.mmc-tl-add-pair .mmc-tl-add:first-child { margin-top: 6px; }
.mmc-tl-add-pair .mmc-tl-add:last-child { margin-bottom: 6px; }
.mmc-tl-add-pair .mmc-tl-add span:first-child { font-size: calc(15px * var(--mmc-type)); }
.mmc-tl-add-clip { border-style: solid; }

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
   tracks is not a row of crosses. */
.mmc-snd-drop {
  position: absolute; right: 13px; bottom: 2px; z-index: 2;
  border: 0; padding: 0 3px; background: none; cursor: pointer;
  color: var(--mmc-text); opacity: .45; font-family: inherit;
  font-size: calc(11px * var(--mmc-type)); line-height: 1;
  text-shadow: 0 1px 3px var(--mmc-bg), 0 0 6px var(--mmc-bg);
  transition: opacity .12s ease;
}
.mmc-snd-block:hover .mmc-snd-drop, .mmc-snd-drop:focus-visible { opacity: 1; }
.mmc-snd-drop:hover { color: var(--mmc-warn); opacity: 1; }
.mmc-snd-drop:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
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

`;
