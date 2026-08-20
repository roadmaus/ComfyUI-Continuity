// The cast shelf, on the node face and in the Timeline window.
// No backticks or ${} anywhere in the CSS: each chunk is one template literal.
export const css = `
/* --- the cast ------------------------------------------------------------- */

.mmc-cast { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.mmc-cast-head { display: flex; gap: 10px; align-items: center; min-width: 0; }
.mmc-cast-hint {
  font-size: 11px; color: var(--mmc-off); flex: 1; min-width: 0;
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
.mmc-cast-empty:hover { border-color: rgba(255,255,255,.22); background: var(--mmc-surface); }
.mmc-cast-empty-title { font-size: 12.5px; color: var(--mmc-dim); }
.mmc-cast-empty-note { font-size: 11px; color: var(--mmc-off); line-height: 1.45; }

.mmc-cast-list { display: flex; flex-direction: column; gap: 8px; }

/* One card per subject. The left edge is her identity hue — the same one her
   @name wears as a chip in the sentence — so a cast of five reads as five
   colours down the shelf and a chip mid-prompt can be matched to a face without
   reading either. That is the pack's existing "this chip is that picture"
   device, pointed at a person instead of a file. */
.mmc-cast-card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 12px 10px 13px; min-width: 0;
  background: var(--mmc-surface); border: 1px solid var(--mmc-line);
  border-left: 3px solid var(--tag, var(--mmc-accent)); border-radius: 12px;
}
/* Cast but never written into a prompt: she is in no shot, which is a state
   worth seeing at a glance and not worth shouting about. */
.mmc-cast-card.idle { border-left-color: var(--mmc-off); }
.mmc-cast-card.idle .mmc-cast-face { opacity: .62; }
.mmc-cast-card.bad { border-color: rgba(255,140,120,.45); }

.mmc-cast-top { display: flex; gap: 12px; align-items: flex-start; min-width: 0; }

/* Her face: the first still she is built out of, at a size you can recognise
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
.mmc-cast-namerow .mmc-asset-handle { font-size: 13px; margin-right: -6px; }

/* The name is monospace and the description is not, deliberately: the name is a
   token you type into a sentence and the description is the sentence. */
.mmc-cast-name {
  background: none; border: 0; border-bottom: 1px solid transparent;
  padding: 2px 0; color: var(--tag, var(--mmc-text)); font: inherit;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px; font-weight: 500; width: 12ch; min-width: 0; outline: none;
}
.mmc-cast-name:hover { border-bottom-color: var(--mmc-line); }
.mmc-cast-name:focus { border-bottom-color: var(--tag, var(--mmc-accent)); }
.mmc-cast-name::placeholder { color: var(--mmc-off); font-weight: 400; }

/* What she is. A word, not a pill: it sits inside the name line as the rest of
   the sentence "@anna is a person", and a bordered chip there would read as a
   second control of the same weight as the name itself. */
.mmc-cast-takes {
  background: none; border: 0; padding: 2px 4px; border-radius: 6px;
  color: var(--mmc-dim); font-family: inherit; font-size: 11.5px; cursor: pointer;
}
.mmc-cast-takes:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }

.mmc-cast-desc {
  flex: 1; min-width: 120px; width: 100%; box-sizing: border-box;
  background: var(--mmc-surface-2); border: 1px solid transparent;
  border-radius: 8px; padding: 5px 9px; color: inherit; font: inherit;
  font-size: 12px; outline: none;
}
.mmc-cast-desc:focus { border-color: var(--mmc-line); }
.mmc-cast-desc::placeholder { color: var(--mmc-off); }

.mmc-cast-side { display: flex; gap: 4px; align-items: center; flex: none; }
.mmc-cast-where { font-size: 11px; color: var(--mmc-dim); white-space: nowrap; }
/* The commonest way to lose an afternoon with this feature is to cast somebody
   and never write her name. So the readout that says so is also the button that
   fixes it, and it is dashed to say there is something outstanding here. */
.mmc-cast-where-idle {
  background: none; border: 1px dashed var(--mmc-line); border-radius: 999px;
  padding: 3px 9px; color: var(--mmc-off); font-family: inherit; cursor: pointer;
}
.mmc-cast-where-idle:hover:not(:disabled) {
  border-color: var(--mmc-accent); color: var(--mmc-accent); border-style: solid;
}
.mmc-cast-where-idle:disabled { cursor: default; opacity: .5; }

/* --- what she is made of --------------------------------------------------- */

/* The row the whole redesign is for. Every file behind her is a real thumbnail
   here, wearing its own hue, with a badge saying what it lends her — where this
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
/* A handle the shot no longer holds. Not hidden — she still claims it, and the
   card refuses to queue until somebody says otherwise. */
.mmc-cast-ref.missing .mmc-cast-ref-thumb {
  box-shadow: 0 0 0 2px rgba(255,140,120,.5); color: #ff8c78;
}
.mmc-cast-missing { font-size: 15px; }

/* What the file lends her, in the corner of the file. Small on purpose: the
   picture is the thing you recognise and the badge is the thing you check. */
.mmc-cast-badge {
  position: absolute; right: -3px; bottom: -3px;
  width: 17px; height: 17px; border-radius: 999px;
  display: flex; align-items: center; justify-content: center;
  background: var(--mmc-surface-3); box-shadow: 0 0 0 2px var(--mmc-surface);
  color: var(--mmc-text);
}
/* Her looks are the default and wear no badge at all — see refTile in cast.js. These
   three are the departures from it, and each says which. */
.mmc-cast-badge-motion { color: #6ebeff; }
.mmc-cast-badge-voice { color: #a8c858; }
.mmc-cast-badge-replaces { color: var(--mmc-accent); }

/* The way to hang another file on her: a tile of the same size as the files,
   in the same row, so it reads as the next slot rather than as a control. */
.mmc-cast-add {
  width: 38px; height: 38px; box-sizing: border-box; border-radius: 9px; flex: none;
  border: 1px dashed var(--mmc-line); background: none; cursor: pointer;
  color: var(--mmc-off); font-size: 17px; font-family: inherit; line-height: 1;
  display: flex; align-items: center; justify-content: center;
}
.mmc-cast-add:hover { border-color: var(--mmc-accent); color: var(--mmc-accent); }

.mmc-cast-refs-none { font-size: 11px; color: var(--mmc-off); }
/* The retention marker. Last on the row and quiet, because it is the one thing
   here you set once a year — but a word rather than a code, with the code
   itself in the menu under it. */
.mmc-cast-keep {
  margin-left: auto; background: none; border: 0; padding: 3px 6px;
  /* Anchored right, away from the tiles: it is a statement about all of them
     together, not another slot in the row. */
  border-radius: 6px; color: var(--mmc-off); font-family: inherit;
  font-size: 11px; cursor: pointer; white-space: nowrap;
}
.mmc-cast-keep:hover { background: var(--mmc-surface-2); color: var(--mmc-dim); }

.mmc-cast-line { display: flex; gap: 8px; align-items: center; padding-left: 58px; min-width: 0; }
.mmc-cast-of { font-size: 11px; color: var(--mmc-dim); white-space: nowrap; }
.mmc-cast-bad { font-size: 11px; color: #ff8c78; line-height: 1.45; padding-left: 58px; }

/* On a node face the shelf is bounded, the way the asset row and the prompt box
   are: the face is a preview of one generation, and a cast of nine must not push
   the pills off the bottom of it. */
.mmc-root .mmc-cast-list { max-height: 300px; overflow-y: auto; }

/* The rail's own entry. Lit when the piece has a cast, the way a lit accelerator
   pill is: a generation with somebody in it is not the default, and the rail is
   the only place that says so while the shelf is scrolled out of sight. */
.mmc-tool.on { color: var(--mmc-text); }
.mmc-tool.on .mmc-tool-icon {
  border-color: rgba(240,166,60,.45); color: var(--mmc-accent);
}

/* --- the menus ------------------------------------------------------------- */

/* Two lines and a picture per row, where a sampler's menu is one word. Wider
   than a choice popover for the same reason: "Her looks come from this" and the
   sentence under it are what make the four roles tellable apart. */
.mmc-cast-menu { min-width: 290px; max-width: 340px; }
.mmc-cast-menu .mmc-opt { align-items: flex-start; padding: 8px 10px; }
.mmc-cast-menu .mmc-opt-label { align-items: flex-start; gap: 9px; min-width: 0; }
.mmc-cast-menu-head {
  color: var(--mmc-off); font-size: 10px; letter-spacing: .06em;
  text-transform: uppercase; padding: 8px 10px 4px;
}
.mmc-cast-menu-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mmc-cast-menu-note {
  color: var(--mmc-off); font-size: 11px; line-height: 1.45;
  /* A filename with no spaces in it must not push the popover wider. */
  overflow-wrap: anywhere;
}
.mmc-cast-menu-thumb {
  width: 30px; height: 30px; border-radius: 7px; object-fit: cover; flex: none;
  background: var(--mmc-surface-3); display: flex; align-items: center;
  justify-content: center; color: var(--mmc-dim);
  box-shadow: 0 0 0 2px var(--tag, transparent);
}
.mmc-cast-menu-plus { font-size: 16px; line-height: 1; }
/* The label in a menu row is a sentence, not a token, so it must not be pinned
   to one line the way an option's usually is. */
.mmc-cast-menu .mmc-opt-label > .mmc-cast-menu-text > span:first-child {
  font-size: 13px; line-height: 1.35;
}
`;
