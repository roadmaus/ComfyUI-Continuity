// The chat room.
//
// The shell is the benches' — the overlay, the sheet, the bar with the wordmark
// in it — because a room off the same dashboard should not be a second thing
// to learn. Under the bar it is nothing like a bench: one column, the width of
// a paragraph, with the conversation above and the composer below, the shape
// every chat surface anybody uses has settled on. There is no rail. The three
// choices a message is made against are pills in the composer's foot; the
// model's name is in the bar; everything set once per machine is behind the
// gear beside it.
//
// **The composer is the one built thing on the surface.** A single rounded
// sheet that holds the attachments, the text and the foot, lifted a shade off
// the ground, with the send arrow as the only accent on the page until a render
// arrives. Everything else is type on the ground.
//
// **The transcript is a column, not a chat client.** No avatars, no timestamps,
// no tails on the bubbles. What is said is short and what matters is the render
// under it, so the assistant's line is set flush and quiet and the user's is
// the one that carries a background — the reverse of the convention, and right
// here, because the user's line is the shortest thing on the surface and the
// only one that has to be findable while scrolling back.

export const css = `
/* --- the column ------------------------------------------------------------ */
/* The shelf beside the column; the column itself stacks its two parts. */
.mmc-ch-room { flex-direction: row; }
.mmc-ch-talk {
  flex: 1; min-width: 0; min-height: 0;
  display: flex; flex-direction: column;
  /* The column the transcript and the composer share. Capped and centred rather
     than run to the window's width: a line of prose past about seventy
     characters stops being read and starts being scanned, and this room is
     mostly prose. On the pair rather than on either, so they line up. */
  --mmc-ch-column: min(720px, 100%);
}

/* --- the bar's right end ----------------------------------------------------- */
.mmc-ch-model { display: flex; }
.mmc-ch-modelpill {
  display: inline-flex; align-items: center; gap: 6px; max-width: 34vw;
  height: 30px; padding: 0 8px 0 11px; border-radius: 15px;
  background: none; border: 1px solid transparent; cursor: pointer; font-family: inherit;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ch-modelpill:hover { background: var(--mmc-surface); color: var(--mmc-text); }
.mmc-ch-modelpill svg { flex: none; stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-ch-modelname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-ch-pillkey { color: var(--mmc-dim); }
.mmc-ch-modelpill .mmc-ch-modelname { color: var(--mmc-text); }
.mmc-ch-over .mmc-close { margin-left: 0; }

/* --- the transcript -------------------------------------------------------- */
.mmc-ch-log {
  flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain;
  padding: 28px 22px 12px;
  display: flex; flex-direction: column; gap: 18px;
}
.mmc-ch-msg { width: var(--mmc-ch-column); margin: 0 auto; display: flex; position: relative; }
.mmc-ch-user { justify-content: flex-end; }
/* The verbs a message can be taken back with — edit and send again, ask
   again from here — under the pointer only, in the margin the bubble leaves,
   so the transcript reads as a transcript until a hand is on it. Disabled
   rather than gone while the transcript cannot be cut there. */
.mmc-ch-acts {
  position: absolute; bottom: -19px; display: flex; gap: 2px;
  opacity: 0; transition: opacity .12s ease;
}
.mmc-ch-user .mmc-ch-acts { right: 0; }
.mmc-ch-bot .mmc-ch-acts { left: 0; }
.mmc-ch-msg:hover .mmc-ch-acts, .mmc-ch-acts:focus-within { opacity: 1; }
.mmc-ch-act {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 18px; border-radius: 5px; border: 0; cursor: pointer;
  background: none; color: var(--mmc-dim);
}
.mmc-ch-act svg { stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-ch-act:hover:not(:disabled) { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-ch-act:disabled { opacity: .35; cursor: default; }
.mmc-ch-act:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }

/* The versions of the conversation from one split, under the message that
   changed. Always shown once there are two: unlike the verbs above it, this
   says something about the transcript — that there is more of it. The strip
   is the last picture each version made, so a version is found by what it
   looks like; the one on screen wears the accent. Pushed down past the verbs'
   margin so the two never sit on each other. */
.mmc-ch-versions { margin-top: 6px; }
.mmc-ch-vbar {
  display: flex; align-items: center; gap: 3px;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
  font-variant-numeric: tabular-nums;
}
.mmc-ch-vstep {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 6px; border: 0; padding: 0;
  background: none; color: var(--mmc-dim); cursor: pointer;
}
.mmc-ch-vstep svg { transform: rotate(-90deg); stroke: currentColor; fill: none; stroke-width: 2; }
.mmc-ch-vstep.back svg { transform: rotate(90deg); }
.mmc-ch-vstep:hover:not(:disabled) { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-ch-vstep:disabled { opacity: .3; cursor: default; }
.mmc-ch-vcount { min-width: 34px; text-align: center; }
.mmc-ch-vtakes { display: flex; gap: 4px; margin-left: 4px; }
.mmc-ch-vtake {
  width: 26px; height: 26px; padding: 0; border: 0; border-radius: 6px; overflow: hidden;
  line-height: 0; cursor: pointer; background: var(--mmc-media-bg);
  box-shadow: 0 0 0 1px var(--mmc-line); opacity: .55; transition: opacity .12s ease;
}
.mmc-ch-vtake img { width: 100%; height: 100%; object-fit: cover; display: block; }
.mmc-ch-vtake.words {
  display: inline-flex; align-items: center; justify-content: center; line-height: 1;
  background: var(--mmc-surface-2); color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type));
}
.mmc-ch-vtake:hover:not(:disabled) { opacity: .9; }
.mmc-ch-vtake.on { opacity: 1; box-shadow: 0 0 0 2px var(--mmc-accent); }
.mmc-ch-vtake:disabled { cursor: default; }
.mmc-ch-vtake:focus-visible, .mmc-ch-vstep:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
/* From the message being edited on: still the conversation until the edit is
   sent, so dimmed rather than gone. */
.mmc-ch-revised { opacity: .4; }
.mmc-ch-flip { max-width: 78%; display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.mmc-ch-user .mmc-ch-said {
  padding: 10px 15px; border-radius: 18px 18px 6px 18px;
  background: var(--mmc-surface-2);
}
.mmc-ch-bot .mmc-ch-said { max-width: 100%; color: var(--mmc-text); }
.mmc-ch-said {
  font-size: calc(14px * var(--mmc-type)); line-height: 1.55;
  white-space: pre-wrap; word-break: break-word; user-select: text;
}
.mmc-ch-bad .mmc-ch-said, .mmc-ch-note.mmc-ch-bad { color: var(--mmc-bad); }
.mmc-ch-thinking { display: flex; align-items: center; gap: 10px; color: var(--mmc-faint); }
/* The seed mark, walking, while the model writes: the pill's 5x5 as
   twenty-five cells so each can fade on its own. In the accent — it is the
   one live thing on the surface while it stands. */
.mmc-ch-mark {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 1.4px;
  width: 18px; height: 18px; flex: none; color: var(--mmc-accent);
}
.mmc-ch-mark i {
  display: block; border-radius: 1px; background: currentColor;
  opacity: 0; transform: scale(.55);
  transition: opacity 340ms ease, transform 340ms cubic-bezier(.2, .7, .2, 1);
}
.mmc-ch-mark i.on { opacity: 1; transform: scale(1); }
.mmc-ch-count { font-weight: 500; color: var(--mmc-dim); font-variant-numeric: tabular-nums; }
/* A turn that failed before there was a reply: what went wrong, and the way
   to try it again beside it — a failure is a moment for direction. */
.mmc-ch-fail { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }

/* What went with a message: the pictures, each wearing the handle the model
   knows it by. A button, because the handle is the thing you type next. */
.mmc-ch-thumbs { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.mmc-ch-thumb {
  position: relative; width: 96px; height: 96px; padding: 0; border-radius: 12px;
  overflow: hidden; cursor: pointer; line-height: 0;
  background: var(--mmc-media-bg); border: 1px solid var(--mmc-line);
}
.mmc-ch-thumb:hover { border-color: var(--mmc-accent); }
.mmc-ch-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.mmc-ch-tag {
  position: absolute; left: 6px; bottom: 6px; padding: 2px 6px; border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10px * var(--mmc-type)); line-height: 1.4;
  color: #fff; background: var(--mmc-scrim-2);
}
.mmc-ch-sound {
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
  color: var(--mmc-faint);
}
.mmc-ch-sound svg { stroke: currentColor; fill: none; stroke-width: 1.6; }

/* What an empty room says. A question set large, one line under it, and the
   three lines a first conversation is made of — each a button, so the first
   message can be a press. Centred vertically: the composer is at the foot
   and the eye has to be brought up to it once before it knows where it is. */
.mmc-ch-empty {
  width: var(--mmc-ch-column); margin: auto; padding-bottom: 8vh;
  display: flex; flex-direction: column; align-items: center; text-align: center;
}
.mmc-ch-empty h2 {
  margin: 0 0 8px; font-size: calc(26px * var(--mmc-type)); font-weight: 500;
  letter-spacing: -.015em; color: var(--mmc-strong);
}
.mmc-ch-empty p { margin: 0 0 26px; font-size: calc(14px * var(--mmc-type)); color: var(--mmc-faint); }
.mmc-ch-tries { width: 100%; display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.mmc-ch-try {
  max-width: 100%; padding: 8px 14px; border-radius: 16px; cursor: pointer; font-family: inherit;
  font-size: calc(13px * var(--mmc-type)); color: var(--mmc-dim); text-align: left;
  background: none; border: 1px solid var(--mmc-line-3);
}
.mmc-ch-try:hover { background: var(--mmc-surface); color: var(--mmc-text); }

/* --- a render, from queued to landed --------------------------------------- */
.mmc-ch-card {
  width: 100%; max-width: 520px;
  border: 1px solid var(--mmc-line); border-radius: 16px;
  background: var(--mmc-surface); overflow: hidden;
  display: flex; flex-direction: column;
}
/* The plate is the part that turns. Both faces sit in one grid cell so the
   back is exactly the picture's box, whatever shape the picture is, and the
   doors under it never move. */
.mmc-ch-plate { display: grid; perspective: 1400px; position: relative; }
.mmc-ch-face {
  grid-area: 1 / 1; min-width: 0; min-height: 0;
  backface-visibility: hidden; -webkit-backface-visibility: hidden;
  transform-style: preserve-3d;
  transition: transform 520ms cubic-bezier(.2, .7, .15, 1);
}
.mmc-ch-front { transform: rotateY(0deg); }
/* Out of flow, so the picture alone sets the plate's height and a long prompt
   scrolls inside the back rather than growing the card. */
.mmc-ch-back { position: absolute; inset: 0; transform: rotateY(-180deg); }
.mmc-ch-plate.turned .mmc-ch-front { transform: rotateY(180deg); }
.mmc-ch-plate.turned .mmc-ch-back { transform: rotateY(0deg); }
/* Light across the plate while it turns — the edge coming towards you
   catches it, the edge going away loses it — which is what makes the card
   read as a thing being turned rather than a swap. Off once it has settled. */
.mmc-ch-plate::after {
  content: ""; position: absolute; inset: 0; pointer-events: none; opacity: 0;
  background: linear-gradient(100deg, rgba(255,255,255,.10), transparent 45%, rgba(0,0,0,.18));
  transition: opacity 260ms;
}
.mmc-ch-plate.turning::after { opacity: 1; }
.mmc-ch-shot {
  display: block; width: 100%; height: auto; max-height: 52vh;
  object-fit: contain; background: var(--mmc-media-bg);
}
/* The one control on the picture: top right, on a scrim, turns the plate. */
.mmc-ch-flip {
  position: absolute; top: 10px; right: 10px; z-index: 2;
  width: 30px; height: 30px; border-radius: 50%; padding: 0; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--mmc-scrim-2); border: 1px solid var(--mmc-edge); color: var(--mmc-text);
  backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
}
.mmc-ch-flip:hover { color: var(--mmc-accent); border-color: var(--mmc-accent); }
.mmc-ch-flip svg { stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

/* The back: what was written on the back of a print. The words the render was
   made from first and largest, then what made it, in the readout mono. */
.mmc-ch-slate {
  height: 100%; box-sizing: border-box; overflow: hidden;
  display: flex; flex-direction: column; min-height: 0;
  background: var(--mmc-float); text-align: left;
}
.mmc-ch-prompt {
  flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain;
  padding: 16px 44px 12px 16px;
  font-size: calc(13.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-text);
}
/* The last line fades where the words go on under the facts, so a prompt
   that scrolls says so. */
.mmc-ch-prompt { mask-image: linear-gradient(black calc(100% - 18px), transparent); }
.mmc-ch-prompt p { margin: 0; white-space: pre-wrap; }
/* The magic prompt's caption under the words it was written from: folded,
   because it runs long and the words are what a person reads first. */
.mmc-ch-caption { margin-top: 10px; }
.mmc-ch-caption summary {
  cursor: pointer; color: var(--mmc-off); font-size: calc(11.5px * var(--mmc-type));
}
.mmc-ch-caption pre {
  margin: 6px 0 0; white-space: pre-wrap; word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(11px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-text);
}
.mmc-ch-facts {
  flex: none; margin: 0; display: grid; grid-template-columns: max-content 1fr;
  column-gap: 14px; row-gap: 3px; padding: 10px 16px 12px; border-top: 1px solid var(--mmc-line);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11px * var(--mmc-type));
  line-height: 1.5; font-variant-numeric: tabular-nums;
}
.mmc-ch-facts dt { color: var(--mmc-off); margin: 0; }
.mmc-ch-facts dd { color: var(--mmc-text); margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-ch-facts dd.mmc-ch-took { color: var(--mmc-strong); }
/* Before there is anything to show. A box of the right shape rather than a
   collapsing card: the picture arrives into the space it was always going to
   take, instead of pushing the conversation down when it lands. */
.mmc-ch-blank {
  aspect-ratio: 16 / 9; display: flex; align-items: center; justify-content: center;
}
.mmc-ch-note {
  padding: 8px 12px; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint);
}
/* The real bar, off the queue's own progress. Two pixels and no label: the
   number is in the readout above it and a second copy of it here would be the
   card talking about itself. */
.mmc-ch-bar { height: 2px; background: var(--mmc-line); }
.mmc-ch-fill {
  display: block; height: 100%; background: var(--mmc-accent);
  transition: width 140ms linear;
}
.mmc-ch-doors {
  display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 12px;
  border-top: 1px solid var(--mmc-line);
}
.mmc-ch-handle {
  padding: 0; background: none; border: 0; cursor: pointer;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ch-handle:hover { color: var(--mmc-accent); }
.mmc-ch-door {
  padding: 5px 11px; border-radius: 13px; cursor: pointer; font-family: inherit;
  font-size: calc(11.5px * var(--mmc-type));
  background: none; color: var(--mmc-text);
  border: 1px solid var(--mmc-line-3);
}
.mmc-ch-door:hover:not(:disabled) { background: var(--mmc-lift); }
.mmc-ch-door:disabled { opacity: .45; cursor: default; }
/* The download door is an icon, not a word: square-ish, the glyph centred. */
.mmc-ch-save { display: inline-flex; align-items: center; padding: 4px 8px; }
/* The two that send a still on, in the pre-stage chip's own colours; and the
   one that stops a render, in the colour of stopping. */
.mmc-ch-sendon:hover:not(:disabled) { background: none; border-color: var(--mmc-accent); color: var(--mmc-accent); }
.mmc-ch-cancel:hover:not(:disabled) { background: none; border-color: var(--mmc-bad); color: var(--mmc-bad); }

/* --- the composer ---------------------------------------------------------- */
/* The dock is full width so the sheet can be centred in it; the sheet is the
   column's width. A fade above it rather than a rule: the transcript scrolls
   up into it, the way it does everywhere else. */
.mmc-ch-dock {
  flex: none; padding: 6px 22px 20px; position: relative;
}
.mmc-ch-dock::before {
  content: ""; position: absolute; left: 0; right: 0; top: -28px; height: 28px;
  background: linear-gradient(to bottom, transparent, var(--mmc-bg));
  pointer-events: none;
}
.mmc-ch-compose {
  width: var(--mmc-ch-column); margin: 0 auto;
  display: flex; flex-direction: column; gap: 4px;
  padding: 12px 12px 10px; border-radius: 24px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line-3);
  box-shadow: 0 6px 24px var(--mmc-shadow-soft);
}
.mmc-ch-compose:focus-within { border-color: var(--mmc-line-2); }
/* The node's own prompt box, sized for a composer: one line to start, a few
   lines at most, then it scrolls. The chips, the menus and the placeholder
   are the box's (styles/editor.js); only its footprint is the room's. */
.mmc-ch-compose .mmc-prompt.mmc-ch-box {
  flex: none; width: 100%; min-width: 0; min-height: calc(24px * var(--mmc-type));
  max-height: 200px; font-size: calc(14px * var(--mmc-type)); line-height: 1.5;
  padding: 4px 6px;
}
.mmc-ch-compose .mmc-prompt.mmc-ch-box:empty::before { color: var(--mmc-faint); }
.mmc-ch-compose .mmc-prompt.mmc-ch-off { opacity: .55; }
.mmc-ch-foot { display: flex; align-items: center; gap: 6px; }
/* Over the box while a message is being edited: what sending does, and Cancel. */
.mmc-ch-revising {
  display: flex; align-items: center; gap: 10px; padding: 0 6px 4px;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ch-revising[hidden] { display: none; }
.mmc-ch-tool, .mmc-ch-send {
  flex: none; display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 50%; cursor: pointer; border: 0;
}
.mmc-ch-tool { background: none; color: var(--mmc-dim); }
.mmc-ch-tool:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-ch-tool svg { stroke: currentColor; fill: none; stroke-width: 2; }
.mmc-ch-send { background: var(--mmc-accent); color: var(--mmc-on-accent); }
.mmc-ch-send svg { stroke: currentColor; fill: none; stroke-width: 2.2; }
.mmc-ch-send:disabled { background: var(--mmc-surface-2); color: var(--mmc-off); cursor: default; }
.mmc-ch-tool:focus-visible, .mmc-ch-send:focus-visible, .mmc-ch-pill:focus-visible,
.mmc-ch-try:focus-visible, .mmc-ch-thumb:focus-visible, .mmc-ch-do:focus-visible, .mmc-ch-act:focus-visible,
.mmc-ch-modelpill:focus-visible {
  outline: 2px solid var(--mmc-accent); outline-offset: 2px;
}

/* What a message is made against: text with a glyph, no box, so the three
   read as the composer's own foot and not as a row of controls lifted off a
   node. The shape opens the simple view's own aspect grid. */
.mmc-ch-pills { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; min-width: 0; }
.mmc-ch-pill {
  display: inline-flex; align-items: center; gap: 6px; max-width: 22ch;
  height: 30px; padding: 0 10px; border-radius: 15px; cursor: pointer;
  background: none; border: 0; font-family: inherit;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ch-pill:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-ch-pill svg { flex: none; stroke: currentColor; fill: none; stroke-width: 1.7; }
.mmc-ch-pill span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* The room's seed, as the simple view draws it: the die and the mark, in the
   foot beside the shape. Its stylesheet folds it away wherever the full seed
   group is a line below; here there is no line below. */
.mmc-ch-pills .mmc-seed-pill { display: flex; padding: 0; height: 30px; margin-left: 4px; }
.mmc-ch-pills .mmc-seed-cell { width: 30px; }

/* Files waiting to go. Square, small, with an × in the corner; they get their
   handle when they are sent, not before. */
.mmc-ch-chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 2px 6px 8px; }
.mmc-ch-chips[hidden] { display: none; }
.mmc-ch-chip {
  position: relative; width: 64px; height: 64px; border-radius: 12px; overflow: visible;
  background: var(--mmc-media-bg); border: 1px solid var(--mmc-line); line-height: 0;
}
.mmc-ch-chip img { width: 100%; height: 100%; object-fit: cover; display: block; border-radius: 11px; }
.mmc-ch-unchip {
  position: absolute; top: -6px; right: -6px; width: 20px; height: 20px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center; cursor: pointer;
  background: var(--mmc-strong); color: var(--mmc-ground); border: 2px solid var(--mmc-surface);
  padding: 0;
}
.mmc-ch-unchip svg { stroke: currentColor; fill: none; stroke-width: 2.4; }

/* --- the first run ----------------------------------------------------------- */
/* Three questions asked as the room's own messages. The chips are the
   answers, set like the empty room's tries — a row of outlined pills under
   the line — and a found answer wears the pack's dot in the accent, as the
   refiner's status line does when its server answers. The long form opens under the same bubble
   in a sheet like the composer's: the question and its detail stay one
   thing, and nothing floats over the transcript. */
.mmc-ch-setup { flex-direction: column; gap: 10px; }
.mmc-ch-askbody { display: flex; flex-direction: column; gap: 10px; }
.mmc-ch-asks, .mmc-ch-askrow { display: flex; flex-wrap: wrap; gap: 6px; }
.mmc-ch-ask {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 13px; border-radius: 16px; cursor: pointer; font-family: inherit;
  font-size: calc(13px * var(--mmc-type)); color: var(--mmc-text);
  background: var(--mmc-float); border: 1px solid var(--mmc-line-3);
}
.mmc-ch-ask:hover:not(:disabled) { background: var(--mmc-surface); }
.mmc-ch-ask.open, .mmc-ch-ask.on { border-color: var(--mmc-accent); color: var(--mmc-accent); }
.mmc-ch-ask.primary { background: var(--mmc-strong); color: var(--mmc-ground); border-color: var(--mmc-strong); }
.mmc-ch-ask.primary:hover:not(:disabled) { background: var(--mmc-strong); opacity: .9; }
.mmc-ch-ask:disabled { opacity: .45; cursor: default; }
.mmc-ch-ask:focus-visible, .mmc-ch-choice:focus-visible {
  outline: 2px solid var(--mmc-accent); outline-offset: 2px;
}
.mmc-ch-found { width: 7px; height: 7px; border-radius: 50%; background: var(--mmc-accent); }
.mmc-ch-inline {
  width: 100%; max-width: 520px; padding: 8px 14px 12px;
  border: 1px solid var(--mmc-line); border-radius: 16px; background: var(--mmc-surface);
}
.mmc-ch-wide { max-width: 100%; }
.mmc-ch-askhead {
  padding: 8px 0 6px; font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ch-askinput {
  flex: 1; min-width: 0; max-width: 60%; height: 30px; padding: 0 10px; border-radius: 8px;
  font-family: inherit; font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-text);
  background: var(--mmc-float); border: 1px solid var(--mmc-line-2);
}
.mmc-ch-askinput:focus { outline: 2px solid var(--mmc-accent); outline-offset: 1px; }
.mmc-ch-askfoot { display: flex; align-items: center; gap: 10px; padding-top: 10px; }
.mmc-ch-askerror { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-bad); }
.mmc-ch-setup .mmc-ch-note { padding: 0; }

/* One family per row: its name, how much of it is on this disk, and its
   slots folded under it. The chosen one wears the accent as an inset ring —
   the same mark the aspect tiles use for the one that is picked. */
.mmc-ch-choices { display: flex; flex-direction: column; gap: 6px; }
.mmc-ch-choice {
  display: grid; grid-template-columns: 1fr auto; gap: 2px 12px; align-items: start;
  padding: 10px 12px; border-radius: 12px; cursor: pointer;
  background: var(--mmc-float); border: 1px solid var(--mmc-line-2);
}
.mmc-ch-choice:hover { border-color: var(--mmc-line-3); }
.mmc-ch-choice[aria-checked="true"] { border-color: var(--mmc-accent); box-shadow: inset 0 0 0 1px var(--mmc-accent); }
.mmc-ch-choicename { font-weight: 500; }
.mmc-ch-state { font-size: calc(12px * var(--mmc-type)); white-space: nowrap; }
.mmc-ch-state::before {
  content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  margin-right: 6px; vertical-align: 1px; background: currentColor;
}
.mmc-ch-state.found { color: var(--mmc-accent); }
.mmc-ch-state.missing { color: var(--mmc-warn); }
.mmc-ch-slots { grid-column: 1 / -1; margin-top: 4px; }
.mmc-ch-slots > summary {
  cursor: pointer; list-style: none; display: inline-block;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ch-slots > summary::-webkit-details-marker { display: none; }
.mmc-ch-slots > summary::before { content: "▸ "; }
.mmc-ch-slots[open] > summary::before { content: "▾ "; }
.mmc-ch-slotlist {
  display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 12px; align-items: center;
  margin-top: 8px; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-ch-slotname { color: var(--mmc-dim); }
.mmc-ch-slotlist .mmc-ch-value { max-width: 100%; justify-self: start; }
.mmc-ch-empty-pick { border-color: var(--mmc-warn); color: var(--mmc-warn); }

/* The key line: the box and Connect beside it, since the list of models is
   what the connection answers with. And the note in the composer's foot
   while the questions are open. */
.mmc-ch-keyrow { flex: 1; min-width: 0; flex-wrap: nowrap; justify-content: flex-end; }
.mmc-ch-keyrow .mmc-ch-askinput { max-width: none; }
.mmc-ch-setupnote { padding: 0 8px; font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-faint); }

/* --- the two sheets behind the bar's pills ------------------------------------ */
/* *Makes with*: two sections, one per kind, each line with a badge saying
   whose the setting is. A grid so the labels, the values and the actions
   line up down the sheet; the value cell wraps, because a row of the chat's
   own is the node's own pills drawn in it. */
.mmc-ch-makes { width: 540px; max-width: calc(100vw - 24px); max-height: calc(100vh - 80px); overflow-y: auto; padding: 10px 14px 12px; }
.mmc-ch-thinker { width: 400px; max-width: calc(100vw - 24px); max-height: calc(100vh - 80px); overflow-y: auto; padding: 10px 12px 12px; }
.mmc-ch-thinker-lead { padding: 0 8px 8px; }
.mmc-ch-writes .mmc-ch-line:first-child { border-top: 0; }
.mmc-ch-gearhead {
  display: flex; align-items: center; gap: 8px; min-height: var(--mmc-pill-h);
  padding: 6px 0 4px; font-size: calc(13px * var(--mmc-type));
}
.mmc-ch-gearhead:first-child { padding-top: 0; }
.mmc-ch-gearkind { font-weight: 600; color: var(--mmc-strong); }
.mmc-ch-gearfamily { color: var(--mmc-dim); }
.mmc-ch-line {
  display: grid; grid-template-columns: 6.5em minmax(0, 1fr); column-gap: 12px;
  align-items: center; padding: 7px 0; border-top: 1px solid var(--mmc-line);
}
.mmc-ch-line-foot { border-top: 0; }
.mmc-ch-k { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-ch-v { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; font-size: calc(12.5px * var(--mmc-type)); }
/* A row of the chat's own is the node's pills, flowing across the value cell. */
.mmc-ch-v .mmc-pills { flex-basis: 100%; padding: 0; gap: 6px; }
/* The summary sits beside its badge and wraps inside itself, rather than
   dropping whole to the next line and leaving the badge alone. */
.mmc-ch-sum { flex: 1 1 12em; min-width: 12em; color: var(--mmc-text); }
.mmc-ch-under { flex-basis: 100%; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-faint); line-height: 1.4; }
/* A line's one action, as a link at the right end of the value's first row:
   "Set for chats", "Change". */
.mmc-ch-do {
  margin-left: auto; background: none; border: 0; padding: 0; font-family: inherit; cursor: pointer;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-blue); white-space: nowrap;
}
.mmc-ch-do:hover { text-decoration: underline; }
/* The badge: one word, in the colour of whose it is. Blue is the node (the
   pin's old colour), the accent is this chat (the colour every "on" pill
   already wears), green is this machine's files, and defaults are plain. */
.mmc-ch-src {
  display: inline-flex; align-items: center; height: 18px; padding: 0 7px; border-radius: 9px;
  font-size: calc(11px * var(--mmc-type)); font-weight: 600; white-space: nowrap;
  border: 1px solid var(--mmc-line-2); color: var(--mmc-dim);
}
.mmc-ch-src-node { color: var(--mmc-blue); border-color: color-mix(in srgb, var(--mmc-blue) 50%, transparent); background: color-mix(in srgb, var(--mmc-blue) 12%, transparent); }
.mmc-ch-src-machine { color: var(--mmc-tag-1); border-color: color-mix(in srgb, var(--mmc-tag-1) 45%, transparent); background: color-mix(in srgb, var(--mmc-tag-1) 10%, transparent); }
.mmc-ch-src-chat { color: var(--mmc-accent); border-color: color-mix(in srgb, var(--mmc-accent) 55%, transparent); background: color-mix(in srgb, var(--mmc-accent) 14%, transparent); }
.mmc-ch-legend { display: flex; flex-wrap: wrap; gap: 6px 14px; padding: 2px 0 4px; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); line-height: 1.4; }
.mmc-ch-legend > span { display: inline-flex; align-items: center; gap: 2px; }
/* The first-run form's rows (chatsetup.js): a label and one control. */
.mmc-ch-row { display: flex; align-items: center; gap: 8px; min-height: var(--mmc-pill-h); padding: 2px 0; }
.mmc-ch-label { flex: 1; min-width: 0; font-size: calc(12.5px * var(--mmc-type)); }
.mmc-ch-value { max-width: 62%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-ch-rule { height: 1px; margin: 8px 0; background: var(--mmc-line); }
/* The verbosity dial: a range with the name of the block it lands in beside it. */
.mmc-ch-verbosity { display: flex; align-items: center; gap: 8px; }
.mmc-ch-verbosity input[type="range"] { width: 140px; accent-color: var(--mmc-blue); margin: 0; }
.mmc-ch-tier { min-width: 5.5em; text-align: right; color: var(--mmc-dim); font-size: calc(12.5px * var(--mmc-type)); white-space: nowrap; }
/* The composer's Pictures pill on a pre-stage the room cannot draw through,
   and the bar's pill with no thinker chosen. */
.mmc-ch-pill-off { color: var(--mmc-warn); }

/* --- the shelf --------------------------------------------------------------
   Every conversation, beside the column. Type on the ground, no cards: a row
   is a title and, at its right edge, the last thing that chat made — the
   list reads as a contact sheet of what you have asked for, which is what
   you are looking for when you come back. The row's two verbs appear under
   the pointer and take the cover's place, so the row never grows. */
.mmc-ch-room { position: relative; }
.mmc-ch-side {
  flex: none; width: 264px; min-width: 0; display: none;
  flex-direction: column; border-right: 1px solid var(--mmc-line);
  background: var(--mmc-float);
}
.mmc-ch-sideopen .mmc-ch-side { display: flex; }
.mmc-ch-sidehead { padding: 14px 12px 6px; }
.mmc-ch-new {
  display: flex; align-items: center; gap: 9px; width: 100%; height: 34px; padding: 0 10px;
  border: 0; border-radius: 9px; background: none; cursor: pointer; font: inherit;
  font-size: calc(13px * var(--mmc-type)); color: var(--mmc-text); text-align: left;
}
.mmc-ch-new:hover { background: var(--mmc-surface); }
.mmc-ch-new svg { stroke: currentColor; fill: none; stroke-width: 1.8; flex: none; }
.mmc-ch-sidelist { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 4px 8px 16px; }
.mmc-ch-sidenote { margin: 10px 8px; font-size: calc(12.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-faint); }
.mmc-ch-day {
  padding: 14px 10px 5px; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-faint);
}
.mmc-ch-siderow {
  position: relative; display: flex; align-items: center; height: 40px; border-radius: 9px;
}
.mmc-ch-siderow:hover, .mmc-ch-siderow.on { background: var(--mmc-surface); }
.mmc-ch-siderow.on { color: var(--mmc-strong); }
.mmc-ch-sideopenbtn {
  flex: 1; min-width: 0; height: 100%; display: flex; align-items: center; gap: 10px;
  padding: 0 6px 0 10px; border: 0; background: none; cursor: pointer; font: inherit;
  color: inherit; text-align: left;
}
.mmc-ch-sideopenbtn:disabled { cursor: default; opacity: .55; }
.mmc-ch-sidetitle {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: calc(13px * var(--mmc-type)); line-height: 1.3;
}
.mmc-ch-cover {
  position: relative; flex: none; width: 36px; height: 24px; border-radius: 5px; overflow: hidden;
  background: var(--mmc-media-bg); line-height: 0;
}
.mmc-ch-nocover { background: var(--mmc-line); }
.mmc-ch-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.mmc-ch-coverclip {
  position: absolute; right: 2px; bottom: 2px; width: 12px; height: 12px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; background: var(--mmc-scrim-2);
}
.mmc-ch-coverclip svg { stroke: #fff; fill: #fff; stroke-width: 1; }
.mmc-ch-sideacts {
  position: absolute; right: 6px; top: 0; bottom: 0; display: none; align-items: center; gap: 2px;
  padding-left: 18px;
  background: linear-gradient(90deg, transparent, var(--mmc-surface) 18px);
}
.mmc-ch-siderow:hover .mmc-ch-sideacts, .mmc-ch-siderow:focus-within .mmc-ch-sideacts,
.mmc-ch-sideacts.on { display: flex; }
.mmc-ch-sideact {
  display: inline-flex; align-items: center; justify-content: center; height: 26px; min-width: 26px;
  padding: 0 6px; border: 0; border-radius: 6px; background: none; cursor: pointer; font: inherit;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-ch-sideact:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-ch-sideact svg { stroke: currentColor; fill: none; stroke-width: 1.7; }
.mmc-ch-sidedel { color: var(--mmc-bad); }
.mmc-ch-sidekeep { color: var(--mmc-text); }
.mmc-ch-renaming { padding: 0 4px; background: var(--mmc-surface); }
.mmc-ch-sidebox {
  width: 100%; height: 30px; padding: 0 8px; border-radius: 6px;
  border: 1px solid var(--mmc-accent); background: var(--mmc-ground);
  color: var(--mmc-strong); font: inherit; font-size: calc(13px * var(--mmc-type)); outline: none;
}
.mmc-ch-confirming { padding-left: 10px; background: var(--mmc-surface); }
.mmc-ch-confirming .mmc-ch-sidetitle { color: var(--mmc-dim); font-size: calc(12.5px * var(--mmc-type)); }
.mmc-ch-confirming .mmc-ch-sideacts { position: static; padding-left: 6px; background: none; }
.mmc-ch-scrim { display: none; }

/* The bar: the toggle beside the crumb, and the chat's own name after it. */
.mmc-ch-sidetoggle {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; margin-left: 4px; border-radius: 7px; cursor: pointer;
  background: none; border: 0; color: var(--mmc-dim);
}
.mmc-ch-sidetoggle:hover, .mmc-ch-sidetoggle[aria-pressed="true"] { color: var(--mmc-text); }
.mmc-ch-sidetoggle:hover { background: var(--mmc-surface); }
.mmc-ch-sidetoggle svg { stroke: currentColor; fill: none; stroke-width: 1.7; }
.mmc-ch-title { display: inline-flex; align-items: center; gap: 8px; min-width: 0; }
.mmc-ch-titlebtn {
  max-width: 28vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 3px 7px; border: 0; border-radius: 6px; background: none; cursor: text;
  font: inherit; font-size: calc(13px * var(--mmc-type)); color: var(--mmc-text);
}
.mmc-ch-titlebtn:hover { background: var(--mmc-surface); }

/* Narrow: the shelf is a drawer over the transcript, not beside it. */
@media (max-width: 960px) {
  .mmc-ch-sideopen .mmc-ch-side {
    position: absolute; left: 0; top: 0; bottom: 0; z-index: 3;
    box-shadow: 8px 0 24px var(--mmc-scrim-2);
  }
  .mmc-ch-sideopen .mmc-ch-scrim {
    display: block; position: absolute; inset: 0; z-index: 2; background: var(--mmc-scrim);
  }
  .mmc-ch-title { display: none; }
}

/* --- narrow --------------------------------------------------------------- */
@media (max-width: 720px) {
  .mmc-ch-log { padding-left: 14px; padding-right: 14px; }
  .mmc-ch-dock { padding-left: 10px; padding-right: 10px; }
  .mmc-ch-flip { max-width: 90%; }
  .mmc-ch-modelname { max-width: 18ch; }
}
@media (prefers-reduced-motion: reduce) {
  .mmc-ch-fill { transition: none; }
  .mmc-ch-mark i { transition: none; }
  /* No turn: the faces cross-fade in place. */
  .mmc-ch-face { transition: opacity 200ms; }
  .mmc-ch-front, .mmc-ch-back, .mmc-ch-plate.turned .mmc-ch-front, .mmc-ch-plate.turned .mmc-ch-back { transform: none; }
  .mmc-ch-back, .mmc-ch-plate.turned .mmc-ch-front { opacity: 0; pointer-events: none; }
  .mmc-ch-plate.turned .mmc-ch-back { opacity: 1; pointer-events: auto; }
  .mmc-ch-plate::after { display: none; }
}
`;
