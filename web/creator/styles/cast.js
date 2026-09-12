// The cast shelf, on the node face and in the Timeline window.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- the cast ------------------------------------------------------------- */

.mmc-cast { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.mmc-cast-head { display: flex; gap: 10px; align-items: center; min-width: 0; }
.mmc-cast-hint {
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-cast-new { display: inline-flex; gap: 5px; align-items: center; flex: none; }

/* Nobody cast yet. A card-shaped invitation rather than a line of grey text,
   because the shelf is only ever drawn when somebody went looking for it, and
   what they were looking for is the way in. */
.mmc-cast-empty {
  display: flex; flex-direction: column; gap: 3px; align-items: flex-start;
  padding: 12px 14px; border: 1px dashed var(--mmc-line); border-radius: 12px;
  background: none; color: inherit; font-family: inherit; cursor: pointer;
  text-align: left; width: 100%;
}
.mmc-cast-empty:hover { border-color: var(--mmc-line-2); background: var(--mmc-surface); }
.mmc-cast-empty-title { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-cast-empty-note { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); line-height: 1.45; }

/* The shelf is one list rather than a stack of loose cards: a cast is a call
   sheet, and hairlines between the lines of one sheet read as a roster where
   eight separately bordered boxes read as eight unrelated things. */
.mmc-cast-list {
  display: flex; flex-direction: column; min-width: 0;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-radius: 12px; overflow: hidden;
}

/* One entry per subject. The left edge is their identity hue — the same one their
   @name wears as a chip in the sentence — so a cast of five reads as five
   colours down the shelf and a chip mid-prompt can be matched to a face without
   reading either. That is the pack's existing "this chip is that picture"
   device, pointed at a person instead of a file. */
.mmc-cast-card {
  display: flex; flex-direction: column; min-width: 0;
  border-left: 3px solid var(--tag, var(--mmc-accent));
}
.mmc-cast-card + .mmc-cast-card { border-top: 1px solid var(--mmc-line); }
/* Open is the editor, and it is lifted off the sheet so the fields in it read as
   one card rather than as more rows of the list. */
.mmc-cast-card.open {
  gap: 8px; padding: 10px 12px 11px 10px; background: var(--mmc-surface-2);
}
/* Cast but never written into a prompt: they are in no shot, which is a state
   worth seeing at a glance and not worth shouting about. */
.mmc-cast-card.idle { border-left-color: var(--mmc-off); }
.mmc-cast-card.idle .mmc-cast-face { opacity: .62; }
.mmc-cast-card.bad { border-left-color: var(--mmc-bad); }

/* --- shut: one line ------------------------------------------------------- */

.mmc-cast-row { display: flex; align-items: center; gap: 4px; min-width: 0; padding-right: 8px; }
/* The line is the button. Nothing else on it can be pressed, so opening
   somebody is a click anywhere along them — and the ✕ beside it is the one thing
   you can hit on purpose. */
.mmc-cast-grip {
  flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px;
  padding: 7px 4px 7px 9px; background: none; border: 0; cursor: pointer;
  color: inherit; font: inherit; text-align: left;
}
.mmc-cast-grip:hover { background: var(--mmc-surface-2); }
.mmc-cast-grip:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: -2px; }
.mmc-cast-grip .mmc-cast-face { width: 30px; height: 30px; border-radius: 8px; }
.mmc-cast-grip .mmc-cast-face-blank svg { width: 16px; height: 16px; }

.mmc-cast-line-ident { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
.mmc-cast-line-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--tag, var(--mmc-text));
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mmc-cast-line-takes { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); flex: none; }

/* Their files as a texture rather than a row of controls — the reading a shut
   line owes is "two pictures and a voice", not "which picture". */
.mmc-cast-minis { display: flex; gap: 3px; flex: none; }
.mmc-cast-mini { position: relative; display: block; line-height: 0; }
.mmc-cast-mini-thumb {
  width: 22px; height: 22px; border-radius: 6px; object-fit: cover;
  background: var(--mmc-surface-3); display: flex; align-items: center;
  justify-content: center; color: var(--mmc-dim);
}
.mmc-cast-mini-thumb svg { width: 11px; height: 11px; }
/* The three that are not their looks say so with the colour their badge wears on
   the open card. A dot, because at 22px a glyph is a smudge. */
.mmc-cast-mini-motion::after, .mmc-cast-mini-voice::after,
.mmc-cast-mini-replaces::after {
  content: ""; position: absolute; right: -1px; bottom: -1px;
  width: 7px; height: 7px; border-radius: 999px;
  box-shadow: 0 0 0 1.5px var(--mmc-surface);
}
.mmc-cast-mini-motion::after { background: var(--mmc-role-motion); }
.mmc-cast-mini-voice::after { background: var(--mmc-role-voice); }
.mmc-cast-mini-replaces::after { background: var(--mmc-role-replaces); }
.mmc-cast-mini.missing .mmc-cast-mini-thumb { box-shadow: 0 0 0 1.5px color-mix(in srgb, var(--mmc-bad) 50%, transparent); }
.mmc-cast-line-words { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); flex: none; }
/* What their looks cost a render, in the marker's monospace — it is a number
   the model is handed. Amber once every look is a saved file, which is the
   one reading a cast of six is scanned for. */
.mmc-cast-line-cost {
  flex: none; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-dim); font-variant-numeric: tabular-nums;
}
.mmc-cast-line-cost.saved { color: var(--mmc-accent); }

/* Where they walk on, or what is wrong with them — the two things a shut line is
   read for, in the place the eye already goes for a status. */
.mmc-cast-line-state {
  margin-left: auto; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); flex: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 46%;
}
.mmc-cast-card.idle .mmc-cast-line-state { color: var(--mmc-off); }
.mmc-cast-line-state.bad { color: var(--mmc-bad); }
.mmc-cast-chev { display: flex; color: var(--mmc-off); flex: none; }

/* --- open: the way back out ----------------------------------------------- */

.mmc-cast-shut {
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; padding: 0; border: 0; border-radius: 6px;
  background: none; color: var(--mmc-off); cursor: pointer; flex: none;
  transform: rotate(180deg);
}
.mmc-cast-shut:hover { background: var(--mmc-surface-3); color: var(--mmc-text); }

/* --- the ledger ------------------------------------------------------------ */
/* One line under their tiles: what their looks cost a render, and the one
   thing that changes it. The number is the argument for a RefMod, so it is
   drawn where the pictures are rather than hinted at by a cube in the header.
   Shared with the library sheet, which draws the same line under its rows. */
.mmc-cast-ledger {
  display: flex; align-items: center; gap: 8px 10px; flex-wrap: wrap; min-width: 0;
  margin-left: 58px; padding: 6px 10px; border-radius: 9px;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-cast-ledger-what { flex: 1; min-width: 16ch; }
.mmc-cast-ledger-what b { font-weight: 500; color: var(--mmc-text); }
.mmc-cast-ledger-dot { color: var(--mmc-off); }
.mmc-cast-ledger-n {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums; color: var(--mmc-text);
}
.mmc-cast-ledger-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--mmc-off);
  overflow-wrap: anywhere;
}
/* Saved: the line is the receipt, and the only amber on the card. */
.mmc-cast-ledger.saved { border-color: color-mix(in srgb, var(--mmc-accent) 35%, transparent); }
.mmc-cast-ledger.saved .mmc-cast-ledger-what b { color: var(--mmc-accent); }
.mmc-cast-ledger-act {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  padding: 3px 9px; border-radius: 999px; border: 1px solid var(--mmc-line-2);
  background: none; color: var(--mmc-text); font: inherit; font-size: calc(11.5px * var(--mmc-type));
  cursor: pointer; text-decoration: none; white-space: nowrap;
}
.mmc-cast-ledger-act:hover { border-color: var(--mmc-line-3); background: var(--mmc-surface-2); }
.mmc-cast-ledger-act.on { border-color: color-mix(in srgb, var(--mmc-accent) 60%, transparent); color: var(--mmc-accent); }
.mmc-cast-ledger-act.on:hover { background: color-mix(in srgb, var(--mmc-accent) 10%, transparent); }
.mmc-cast-ledger-queued { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); flex: none; }
/* Encoding: the same line grows a bar across its foot and nothing else moves. */
.mmc-cast-ledger-bar {
  flex-basis: 100%; height: 3px; border-radius: 2px; background: var(--mmc-surface-3); overflow: hidden;
}
.mmc-cast-ledger-bar i { display: block; height: 100%; background: var(--mmc-accent); transition: width .3s ease; }
.mmc-cast-ledger-note { flex-basis: 100%; color: var(--mmc-bad); line-height: 1.45; }

/* --- the footer -------------------------------------------------------------- */
/* The two verbs a finished member is for, with their words on: keeping them in
   the library, and recasting. A star and two arrows at 13px in the header were
   the same two verbs and nobody found either. */
.mmc-cast-foot {
  display: flex; gap: 4px; align-items: center; flex-wrap: wrap;
  margin-left: 58px; padding-top: 8px; border-top: 1px solid var(--mmc-line);
}
.mmc-cast-foot-act {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 9px; border-radius: 999px; border: 1px solid transparent;
  background: none; color: var(--mmc-dim); font: inherit; font-size: calc(11.5px * var(--mmc-type));
  cursor: pointer; white-space: nowrap;
}
.mmc-cast-foot-act:hover:not(:disabled) { border-color: var(--mmc-line-2); color: var(--mmc-text); }
.mmc-cast-foot-act:disabled { opacity: .4; cursor: default; }
/* Kept: the star fills, the way a starred preset's does in the library. Waiting
   on the library window for a swap: lit, so the card says which press the
   window belongs to when it comes back. */
.mmc-cast-foot-act.on { color: var(--mmc-accent); opacity: 1; }
.mmc-cast-foot-act.on svg { fill: currentColor; }

.mmc-cast-top { display: flex; gap: 12px; align-items: flex-start; min-width: 0; }

/* Their face: the first still they are built out of, at a size you can recognise
   somebody at. Square, because every other thumbnail in the pack is. */
.mmc-cast-face {
  width: 46px; height: 46px; border-radius: 10px; object-fit: cover; flex: none;
  background: var(--mmc-surface-3); box-shadow: 0 0 0 2px var(--tag, transparent);
}
.mmc-cast-face-blank {
  display: flex; align-items: center; justify-content: center; color: var(--mmc-off);
  box-shadow: inset 0 0 0 1px var(--mmc-line);
}

.mmc-cast-ident { display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 0; }
.mmc-cast-namerow { display: flex; gap: 8px; align-items: center; min-width: 0; }
/* The @ belongs to the name, not to the row: it is one token with a gap in it
   otherwise. */
.mmc-cast-namerow .mmc-asset-handle { font-size: calc(13px * var(--mmc-type)); margin-right: -6px; }

/* The name is monospace and the description is not, deliberately: the name is a
   token you type into a sentence and the description is the sentence. */
.mmc-cast-name {
  background: none; border: 0; border-bottom: 1px solid transparent;
  padding: 2px 0; color: var(--tag, var(--mmc-text)); font: inherit;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(13px * var(--mmc-type)); font-weight: 500; width: 12ch; min-width: 0; outline: none;
}
.mmc-cast-name:hover { border-bottom-color: var(--mmc-line); }
.mmc-cast-name:focus { border-bottom-color: var(--tag, var(--mmc-accent)); }
.mmc-cast-name::placeholder { color: var(--mmc-off); font-weight: 400; }

/* What they are. A word, not a pill: it sits inside the name line as the rest of
   the sentence "@anna is a person", and a bordered chip there would read as a
   second control of the same weight as the name itself. */
.mmc-cast-takes {
  background: none; border: 0; padding: 2px 4px; border-radius: 6px;
  color: var(--mmc-dim); font-family: inherit; font-size: calc(11.5px * var(--mmc-type)); cursor: pointer;
}
.mmc-cast-takes:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }

.mmc-cast-desc {
  flex: 1; min-width: 120px; width: 100%; box-sizing: border-box;
  background: var(--mmc-surface-2); border: 1px solid transparent;
  border-radius: 8px; padding: 5px 9px; color: inherit; font: inherit;
  font-size: calc(12px * var(--mmc-type)); outline: none;
}
.mmc-cast-desc:focus { border-color: var(--mmc-line); }
.mmc-cast-desc::placeholder { color: var(--mmc-off); }

.mmc-cast-side { display: flex; gap: 4px; align-items: center; flex: none; }
.mmc-cast-where { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); white-space: nowrap; }
/* The commonest way to lose an afternoon with this feature is to cast somebody
   and never write their name. So the readout that says so is also the button that
   fixes it, and it is dashed to say there is something outstanding here. */
.mmc-cast-where-idle {
  background: none; border: 1px dashed var(--mmc-line); border-radius: 999px;
  padding: 3px 9px; color: var(--mmc-off); font-family: inherit; cursor: pointer;
}
.mmc-cast-where-idle:hover:not(:disabled) {
  border-color: var(--mmc-accent); color: var(--mmc-accent); border-style: solid;
}
.mmc-cast-where-idle:disabled { cursor: default; opacity: .5; }

/* --- what they are made of --------------------------------------------------- */

/* The row the whole redesign is for. Every file behind them is a real thumbnail
   here, wearing its own hue, with a badge saying what it lends them — where this
   used to be four ghost chips that all looked like every other ghost chip in
   the pack, and the way to add one was a "+" character among them. */
.mmc-cast-refs {
  display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
  padding-left: 58px; min-width: 0;
}
.mmc-cast-ref {
  position: relative; padding: 0; border: 0; background: none; cursor: pointer;
  border-radius: 9px; line-height: 0; flex: none;
}
.mmc-cast-ref:hover .mmc-cast-ref-thumb, .mmc-cast-ref:focus-visible .mmc-cast-ref-thumb {
  filter: brightness(1.25);
}
.mmc-cast-ref:focus-visible { outline: 2px solid var(--mmc-accent); outline-offset: 2px; }
.mmc-cast-ref-thumb {
  width: 38px; height: 38px; border-radius: 9px; object-fit: cover;
  background: var(--mmc-surface-3); display: flex; align-items: center;
  justify-content: center; color: var(--mmc-dim);
  box-shadow: 0 0 0 2px var(--tag, transparent);
}
/* A handle the shot no longer holds. Not hidden — they still claims it, and the
   card refuses to queue until somebody says otherwise. */
.mmc-cast-ref.missing .mmc-cast-ref-thumb {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--mmc-bad) 50%, transparent); color: var(--mmc-bad);
}
.mmc-cast-missing { font-size: calc(15px * var(--mmc-type)); }

/* What the file lends them, in the corner of the file. Small on purpose: the
   picture is the thing you recognise and the badge is the thing you check. */
.mmc-cast-badge {
  position: absolute; right: -3px; bottom: -3px;
  width: 17px; height: 17px; border-radius: 999px;
  display: flex; align-items: center; justify-content: center;
  background: var(--mmc-surface-3); box-shadow: 0 0 0 2px var(--mmc-surface);
  color: var(--mmc-text);
}
/* The other two corners. Top-left: the file is encoded at full detail, in the
   marker's monospace — it is what the model is handed, and it is the setting
   that costs. Top-right: words are attached to this file; the tooltip and the
   tile's menu carry them. Both shared with the library sheet's tiles, which say
   the same two things about the same files. */
.mmc-cast-size {
  position: absolute; left: -3px; top: -3px; padding: 0 3px; border-radius: 4px;
  line-height: 12px; font-size: calc(8.5px * var(--mmc-type)); letter-spacing: .04em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--mmc-surface-3); color: var(--mmc-dim);
  box-shadow: 0 0 0 2px var(--mmc-surface);
}
.mmc-cast-noted {
  position: absolute; right: -2px; top: -2px; width: 7px; height: 7px; border-radius: 999px;
  background: var(--mmc-accent); box-shadow: 0 0 0 2px var(--mmc-surface);
}
/* ...and hollow where the file has words to wake on: a rule rather than a
   caption. The same ring the card's chip draws in front of the words. */
.mmc-cast-noted.wake {
  background: var(--mmc-surface);
  box-shadow: 0 0 0 2px var(--mmc-surface), inset 0 0 0 1.5px var(--mmc-accent);
}
/* The words themselves, at the head of the tile's menu. */
.mmc-cast-menu-lead { padding: 2px 8px 6px; }
/* Two of them, stacked: what the file shows, then what it wakes on. The second
   wears the hollow ring inside its left edge — filled in, the two fields are
   two lines of words, and the ring is what says which line is the rule. */
.mmc-cast-menu-words { display: flex; flex-direction: column; }
.mmc-cast-menu-words .mmc-cast-menu-lead + .mmc-cast-menu-lead { padding-top: 0; }
.mmc-cast-menu-wake { position: relative; }
.mmc-cast-menu-wake::before {
  content: ""; position: absolute; left: 17px; top: 50%; margin-top: -6.5px;
  width: 7px; height: 7px; border-radius: 999px; pointer-events: none;
  box-shadow: inset 0 0 0 1.5px var(--mmc-accent);
}
.mmc-cast-menu-wake .mmc-cast-menu-field { padding-left: 22px; }
.mmc-cast-menu-field {
  width: 100%; box-sizing: border-box; min-width: 260px;
  padding: 5px 8px; border-radius: 6px; border: 1px solid var(--mmc-line);
  background: var(--mmc-surface-2); color: var(--mmc-text);
  font: inherit; font-size: calc(12px * var(--mmc-type)); outline: none;
}
.mmc-cast-menu-field:focus { border-color: var(--mmc-accent); }
.mmc-cast-menu-field::placeholder { color: var(--mmc-off); }

/* Their looks are the default and wear no badge at all — see refTile in cast.js. These
   three are the departures from it, and each says which. */
.mmc-cast-badge-motion { color: var(--mmc-role-motion); }
.mmc-cast-badge-voice { color: var(--mmc-role-voice); }
.mmc-cast-badge-replaces { color: var(--mmc-role-replaces); }

/* The way to hang another file on them: a tile of the same size as the files,
   in the same row, so it reads as the next slot rather than as a control. */
.mmc-cast-add {
  width: calc(38px * var(--mmc-type)); height: calc(38px * var(--mmc-type)); box-sizing: border-box; border-radius: 9px; flex: none;
  border: 1px dashed var(--mmc-line); background: none; cursor: pointer;
  color: var(--mmc-off); font-size: calc(17px * var(--mmc-type)); font-family: inherit; line-height: 1;
  display: flex; align-items: center; justify-content: center;
}
.mmc-cast-add:hover { border-color: var(--mmc-accent); color: var(--mmc-accent); }

.mmc-cast-refs-none { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); }

/* --- feature by feature ---------------------------------------------------- */
/* The guide writes a subject as a named list of features and names the same
   features again in retention_analysis, so this list is the shape of the thing
   being edited rather than a form invented for the shelf.

   Set as a list and not as a row of fields: every line is one claim about one
   person, and lines are what you read down. Indented to the tiles' own lane, so
   the card reads as a column of statements about the same somebody. */
.mmc-cast-features {
  display: flex; flex-direction: column; gap: 4px;
  padding-left: 58px; min-width: 0;
}
.mmc-cast-features-head {
  display: flex; align-items: baseline; gap: 10px; min-width: 0; margin-bottom: 1px;
}
.mmc-cast-features-title {
  color: var(--mmc-off); font-size: calc(10px * var(--mmc-type)); letter-spacing: .09em; text-transform: uppercase;
}
.mmc-cast-feature-add {
  margin-left: auto; flex: none; appearance: none; border: 0; background: none;
  padding: 2px 5px; margin-right: -5px; border-radius: 6px; cursor: pointer;
  color: var(--mmc-off); font: inherit; font-size: calc(11px * var(--mmc-type)); white-space: nowrap;
}
.mmc-cast-feature-add:hover { color: var(--mmc-accent); background: var(--mmc-surface-2); }

.mmc-cast-feature {
  display: flex; align-items: center; gap: 7px; min-width: 0; flex-wrap: wrap;
}
/* A seeded row opens with the attribute it stands for. Set in the off colour
   and boxed to one width, so the four names read down the card as the list they
   are and the words somebody types beside them are the only text at full
   weight. Dim, because the name is the card talking and the box is the user. */
.mmc-cast-feature-attr {
  flex: 0 0 5.5em; min-width: 0; color: var(--mmc-off);
  font-size: calc(11.5px * var(--mmc-type)); white-space: nowrap;
}
/* Narrower, because the name in front of it has already spent part of the lane
   and the arrows still have to line up with the rows that have no name. */
.mmc-cast-feature.attr .mmc-cast-feature-is { flex: 0 1 9.5em; }
/* The fields are the line. No border and no box: a bordered input per feature
   turns four facts about one person into a form to fill in, and what this is is
   a sentence somebody is writing. The rule under it is the only edge. */
/* A fixed lane rather than the whole row: at flex:1 the phrase and the word
   after it ended up at opposite ends of the card, reading as two unrelated
   things, and no two rows put their arrows in the same place. Boxed to one
   width, the arrows line up into a column and each row reads as one phrase. */
.mmc-cast-feature-is, .mmc-cast-feature-instead {
  flex: 0 1 15em; min-width: 7em; appearance: none; background: none;
  border: 0; border-bottom: 1px solid transparent; outline: none;
  padding: 3px 0; color: var(--mmc-text); font: inherit; font-size: calc(12.5px * var(--mmc-type));
}
.mmc-cast-feature-is::placeholder, .mmc-cast-feature-instead::placeholder { color: var(--mmc-off); }
.mmc-cast-feature-is:hover, .mmc-cast-feature-instead:hover { border-bottom-color: var(--mmc-line); }
.mmc-cast-feature-is:focus, .mmc-cast-feature-instead:focus {
  border-bottom-color: var(--mmc-accent);
}
/* The one device on the card. A kept feature is a plain line; a changed one is
   the only thing here with horizontal motion in it, and it reads as what it is —
   this, now that. Nothing else is highlighted, boxed or coloured to say so. */
.mmc-cast-feature-arrow {
  flex: none; color: var(--mmc-accent); font-size: calc(13px * var(--mmc-type)); line-height: 1;
}
.mmc-cast-feature.changed .mmc-cast-feature-is { color: var(--mmc-dim); }
.mmc-cast-feature.changed .mmc-cast-feature-instead { color: var(--mmc-text); }
/* Kept is the quiet state, so it is a word and not a control: no border, no
   background, nothing to look at until you go looking for it. */
.mmc-cast-feature-kept {
  flex: none; appearance: none; border: 0; background: none; cursor: pointer;
  padding: 3px 6px; border-radius: 6px; color: var(--mmc-off);
  font: inherit; font-size: calc(11px * var(--mmc-type)); white-space: nowrap;
}
.mmc-cast-feature-kept:hover { color: var(--mmc-accent); background: var(--mmc-surface-2); }
.mmc-cast-feature-x {
  flex: none; margin-left: auto; opacity: 0; transition: opacity .12s ease;
}
.mmc-cast-feature:hover .mmc-cast-feature-x,
.mmc-cast-feature:focus-within .mmc-cast-feature-x { opacity: 1; }

/* What the rows add up to, in the guide's own vocabulary. Monospaced, which is
   the same face the compiled prompt sets its field names in: across both
   surfaces that face means "this is the word the model is handed". */
.mmc-cast-marker {
  display: flex; align-items: baseline; gap: 8px; align-self: flex-start;
  appearance: none; border: 0; background: none; cursor: pointer;
  padding: 3px 6px; margin: 6px 0 0 -6px; border-radius: 6px;
  font: inherit; text-align: left;
}
.mmc-cast-marker:hover { background: var(--mmc-surface-2); }
.mmc-cast-marker-value {
  color: var(--mmc-dim); font-size: calc(11px * var(--mmc-type)); letter-spacing: .04em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.mmc-cast-marker-say, .mmc-cast-marker-forced { color: var(--mmc-off); font-size: calc(10.5px * var(--mmc-type)); }
.mmc-cast-marker.forced .mmc-cast-marker-value { color: var(--mmc-accent); }

.mmc-cast-line { display: flex; gap: 8px; align-items: center; padding-left: 58px; min-width: 0; }
/* The place they take, offered rather than hidden behind a thumbnail's menu:
   this is the one relationship the model cannot infer and the one people most
   want to state. Dim until it holds something, so a card where nobody takes
   anyone's place reads as an offer and not as an unanswered question. */
.mmc-cast-place { opacity: .62; }
.mmc-cast-place:hover, .mmc-cast-place:focus-within, .mmc-cast-place.on { opacity: 1; }
.mmc-cast-place-clip {
  flex: none; appearance: none; background: none; cursor: pointer;
  border: 1px solid var(--mmc-line); border-radius: 7px; padding: 3px 8px;
  color: var(--mmc-dim); font: inherit; font-size: calc(11.5px * var(--mmc-type)); white-space: nowrap;
}
.mmc-cast-place-clip:hover { border-color: var(--mmc-accent); color: var(--mmc-text); }
.mmc-cast-of { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); white-space: nowrap; }
.mmc-cast-bad { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-bad); line-height: 1.45; padding-left: 58px; }

/* On a node face the shelf is bounded, the way the asset row and the prompt box
   are: the face is a preview of one generation, and a cast of nine must not push
   the pills off the bottom of it. */
.mmc-root .mmc-cast-list { max-height: 300px; overflow-y: auto; }

/* The rail's own entry: a switch. Lit while the shelf is up, and wearing the
   head count whether or not it is — a folded shelf with two people on it must
   read as two people, because the rail is the only thing that says so while
   the shelf is folded or scrolled out of sight. */
.mmc-tool.on { color: var(--mmc-text); }
.mmc-tool.on .mmc-tool-icon {
  border-color: color-mix(in srgb, var(--mmc-accent) 45%, transparent); color: var(--mmc-accent);
}
.mmc-tool-cast { position: relative; }
.mmc-tool-count {
  position: absolute; top: -4px; right: calc(50% - var(--mmc-tool-tile) / 2 - 6px);
  min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px;
  background: var(--mmc-accent); color: var(--mmc-strong);
  font-size: 10px; font-weight: 600; line-height: 16px; text-align: center;
  font-variant-numeric: tabular-nums;
}

/* --- the menus ------------------------------------------------------------- */

/* Two lines and a picture per row, where a sampler's menu is one word. Wider
   than a choice popover for the same reason: "Their looks come from this" and the
   sentence under it are what make the four roles tellable apart. */
.mmc-cast-menu { min-width: 290px; max-width: 340px; }
.mmc-cast-menu .mmc-opt { align-items: flex-start; padding: 8px 10px; }
.mmc-cast-menu .mmc-opt-label { align-items: flex-start; gap: 9px; min-width: 0; }
.mmc-cast-menu-head {
  color: var(--mmc-off); font-size: calc(10px * var(--mmc-type)); letter-spacing: .06em;
  text-transform: uppercase; padding: 8px 10px 4px;
}
.mmc-cast-menu-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mmc-cast-menu-note {
  color: var(--mmc-off); font-size: calc(11px * var(--mmc-type)); line-height: 1.45;
  /* A filename with no spaces in it must not push the popover wider. */
  overflow-wrap: anywhere;
}
.mmc-cast-menu-thumb {
  width: 30px; height: 30px; border-radius: 7px; object-fit: cover; flex: none;
  background: var(--mmc-surface-3); display: flex; align-items: center;
  justify-content: center; color: var(--mmc-dim);
  box-shadow: 0 0 0 2px var(--tag, transparent);
}
.mmc-cast-menu-plus { font-size: calc(16px * var(--mmc-type)); line-height: 1; }
/* The label in a menu row is a sentence, not a token, so it must not be pinned
   to one line the way an option's usually is. */
.mmc-cast-menu .mmc-opt-label > .mmc-cast-menu-text > span:first-child {
  font-size: calc(13px * var(--mmc-type)); line-height: 1.35;
}
`;
