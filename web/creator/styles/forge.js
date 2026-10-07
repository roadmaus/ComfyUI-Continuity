// Game Forge's room.
//
// It borrows the benches' bar, buttons, dials and light box from
// styles/bench.js and nothing else: the forge is not a file on a light box with
// an instrument beside it, it is a game's whole cast of pictures, so its room
// is three places — the shelf, the glass, the inspector — with the project's
// settings in a drawer and the pose stage on a page of its own (forge.js says
// why at length).
//
// **The pictures are the loudest thing in it.** Every row on the shelf carries
// its asset's picture, pixel-true on a checkerboard so transparency reads as
// transparency; the pose strip's frames are white sheets of animation paper in
// a dark room, the one place the forge spends a large light area. Everything
// else is set quiet: sentence-case headings, no tracked-out labels, one weight
// change per level.
//
// **The amber marks where you are**: the asset or frame you are on, the press
// that exports or draws, playback while it runs. A problem is drawn in the
// room's bad colour, because it is a fault and not a control. The onion skins
// carry the two colours the pose page's ghosts are drawn in (ONION in
// forge/posepage.js); keep the two in step.

export const css = `
.mmc-fg {
  --mmc-fg-prev: #6ebeff;
  --mmc-fg-next: #7fd37a;
  --mmc-fg-check: conic-gradient(
    var(--mmc-surface-2) 25%, var(--mmc-surface) 0 50%, var(--mmc-surface-2) 0 75%, var(--mmc-surface) 0)
    0 0 / 8px 8px;
  --mmc-fg-paper: #fbfbf8;
}
/* Classes here set display, and a class beats the user agent's [hidden] rule. */
.mmc-fg [hidden] { display: none !important; }
.mmc-fg button:focus-visible, .mmc-fg-menu button:focus-visible, .mmc-fg-newpop button:focus-visible,
.mmc-fg summary:focus-visible, .mmc-fg-canvas:focus-visible {
  outline: 2px solid var(--mmc-accent); outline-offset: 1px;
}

/* --- the bar --------------------------------------------------------------- */
.mmc-fg-crumb { display: contents; }
/* The project's name is the way to another project: a crumb that opens. */
.mmc-fg-switch {
  display: flex; align-items: center; gap: 6px; padding: 4px 8px; margin-left: -4px;
  border-radius: 8px; border: 0; background: none; cursor: pointer; font-family: inherit;
  font-size: calc(13px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong);
}
.mmc-fg-switch:hover { background: var(--mmc-surface); }
.mmc-fg-switch svg { stroke: var(--mmc-off); fill: none; stroke-width: 1.6; }
/* The two pages, as one control in the middle of the bar. */
.mmc-fg-tabs { display: flex; gap: 2px; padding: 3px; border-radius: 11px; background: var(--mmc-surface); }
.mmc-fg-tabs:empty { display: none; }
.mmc-fg-tab {
  padding: 5px 16px; border-radius: 8px; border: 0; background: none; cursor: pointer;
  font-family: inherit; font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-fg-tab:hover { color: var(--mmc-text); }
.mmc-fg-tab.on { background: var(--mmc-surface-3); color: var(--mmc-strong); font-weight: 600; }
.mmc-fg-barbutton {
  display: flex; align-items: center; gap: 7px; padding: 6px 12px; border-radius: 9px;
  border: 1px solid var(--mmc-line-2); background: none; cursor: pointer; font-family: inherit;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-text);
}
.mmc-fg-barbutton svg { stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-fg-barbutton:hover, .mmc-fg-barbutton.on { background: var(--mmc-surface-2); }

/* --- the room ---------------------------------------------------------------- */
.mmc-fg-body { flex: 1; min-height: 0; display: flex; position: relative; overflow: hidden; }
.mmc-fg-room, .mmc-fg-page { flex: 1; min-width: 0; display: flex; }
.mmc-fg-shelf {
  flex: none; width: min(calc(236px * var(--mmc-type)), 28vw); box-sizing: border-box;
  border-right: 1px solid var(--mmc-line); overflow: auto; overscroll-behavior: contain;
  padding: 14px 10px 14px 12px; display: flex; flex-direction: column; gap: 18px;
}
.mmc-fg-middle {
  flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; padding: 14px 20px 16px;
}
.mmc-fg-inspector {
  flex: none; width: min(calc(304px * var(--mmc-type)), 32vw); box-sizing: border-box;
  border-left: 1px solid var(--mmc-line); overflow: auto; overscroll-behavior: contain;
  padding: 18px 18px 16px; display: flex; flex-direction: column; gap: 18px;
}

/* --- words, and the fields they label ----------------------------------------- */
.mmc-fg-h {
  margin: 0; font-size: calc(18px * var(--mmc-type)); font-weight: 600; letter-spacing: -.01em;
  color: var(--mmc-strong);
}
.mmc-fg-quiet { margin: 0; font-size: calc(12.5px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-dim); }
.mmc-fg-field { display: flex; flex-direction: column; gap: 6px; }
.mmc-fg-label { font-size: calc(12px * var(--mmc-type)); font-weight: 500; color: var(--mmc-dim); }
.mmc-fg-hint { margin: 0; font-size: calc(11.5px * var(--mmc-type)); line-height: 1.45; color: var(--mmc-off); }
.mmc-fg-prose { resize: vertical; line-height: 1.45; }
.mmc-fg-num { width: calc(76px * var(--mmc-type)); font-variant-numeric: tabular-nums; }
.mmc-fg-inline { display: flex; align-items: center; gap: 6px; }
.mmc-fg-unit { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-fg-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.mmc-fg-make { width: 100%; justify-content: center; gap: 8px; margin-bottom: 6px; }
.mmc-fg-trio { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
/* JSON is read by its columns. The one place the forge sets type in mono. */
.mmc-fg-json {
  resize: vertical; white-space: pre; overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: calc(11px * var(--mmc-type));
}
.mmc-fg-check {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-text);
}
.mmc-fg-check input, .mmc-fg-loop input, .mmc-fg-onion input { accent-color: var(--mmc-accent); margin: 0; }
.mmc-fg-link {
  align-self: flex-start; padding: 0; background: none; border: 0; cursor: pointer; text-align: left;
  font-family: inherit; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
  text-decoration: underline; text-underline-offset: 3px; text-decoration-color: var(--mmc-line-3);
}
.mmc-fg-link:hover { color: var(--mmc-text); }
/* The second press of Remove says what it will do, in the colour a fault is
   drawn in: the first press only asked. */
.mmc-fg-remove.armed { color: var(--mmc-bad); text-decoration-color: currentColor; }
.mmc-fg-iconbutton {
  flex: none; display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; padding: 0; border-radius: 7px; border: 0; background: none;
  color: var(--mmc-dim); cursor: pointer;
}
.mmc-fg-iconbutton:hover { background: var(--mmc-surface-2); color: var(--mmc-text); }
.mmc-fg-iconbutton svg { stroke: currentColor; fill: none; stroke-width: 1.7; }
.mmc-fg-small { height: calc(32px * var(--mmc-type)); padding: 0 14px; font-size: calc(12.5px * var(--mmc-type)); }
.mmc-fg-select { width: auto; height: calc(32px * var(--mmc-type)); padding: 0 8px; cursor: pointer; }

/* --- choosing: a name and what it means -------------------------------------- */
.mmc-fg-choices {
  display: flex; flex-direction: column; border: 1px solid var(--mmc-line); border-radius: 10px; overflow: hidden;
}
.mmc-fg-choice {
  display: grid; grid-template-columns: 16px 1fr; gap: 10px; align-items: start;
  padding: 9px 12px; border: 0; background: none; cursor: pointer; text-align: left; font-family: inherit;
}
.mmc-fg-choice + .mmc-fg-choice { border-top: 1px solid var(--mmc-line); }
.mmc-fg-choice:hover { background: var(--mmc-wash); }
.mmc-fg-choice.on { background: var(--mmc-tint); }
.mmc-fg-tick {
  width: 14px; height: 14px; margin-top: 1px; box-sizing: border-box;
  border: 1.5px solid var(--mmc-line-3); border-radius: 50%; position: relative;
}
.mmc-fg-choice.checkbox .mmc-fg-tick { border-radius: 4px; }
.mmc-fg-choice.on .mmc-fg-tick { border-color: var(--mmc-strong); }
.mmc-fg-choice.on .mmc-fg-tick::after {
  content: ""; position: absolute; inset: 2.5px; border-radius: inherit; background: var(--mmc-strong);
}
.mmc-fg-choice.checkbox.on .mmc-fg-tick::after { border-radius: 1.5px; }
.mmc-fg-choicetext { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mmc-fg-choicename { display: block; font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-text); }
/* Look names are ids (pixel, toon); said as words, they start with a capital. */
.mmc-fg-choicename::first-letter { text-transform: uppercase; }
.mmc-fg-choice.on .mmc-fg-choicename { color: var(--mmc-strong); font-weight: 600; }
.mmc-fg-choicehelp { font-size: calc(11.5px * var(--mmc-type)); line-height: 1.4; color: var(--mmc-dim); }

/* --- the start page ------------------------------------------------------------ */
.mmc-fg-start {
  flex: 1; overflow: auto; display: grid; align-content: start; justify-content: center;
  grid-template-columns: minmax(0, 320px) minmax(0, 440px); gap: 56px; padding: 8vh 32px 40px;
}
.mmc-fg-startcol { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.mmc-fg-games { display: flex; flex-direction: column; gap: 8px; }
.mmc-fg-game {
  display: flex; flex-direction: column; gap: 3px; padding: 12px 14px; text-align: left; cursor: pointer;
  border-radius: 12px; border: 1px solid var(--mmc-line); background: var(--mmc-tint); font-family: inherit;
}
.mmc-fg-game:hover { background: var(--mmc-surface); border-color: var(--mmc-line-2); }
.mmc-fg-gamename { font-size: calc(15px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong); }
.mmc-fg-gamenote { font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); }
.mmc-fg-bigname { height: calc(38px * var(--mmc-type)); font-size: calc(15px * var(--mmc-type)); }
.mmc-fg-startfoot { display: flex; align-items: center; gap: 12px; margin-top: 4px; }

/* --- the shelf ------------------------------------------------------------------- */
.mmc-fg-shelfhead { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-left: 4px; }
.mmc-fg-count { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim); font-variant-numeric: tabular-nums; }
.mmc-fg-add {
  display: flex; align-items: center; gap: 5px; padding: 5px 11px 5px 8px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--mmc-line-2); background: var(--mmc-surface); color: var(--mmc-text);
  font-family: inherit; font-size: calc(12px * var(--mmc-type));
}
.mmc-fg-add:hover { background: var(--mmc-surface-2); }
.mmc-fg-add svg { stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-fg-group { display: flex; flex-direction: column; gap: 4px; }
.mmc-fg-grouphead {
  display: flex; align-items: baseline; margin: 0; padding: 0 8px 0 5px;
  font-size: calc(11.5px * var(--mmc-type)); font-weight: 600; color: var(--mmc-off);
}
.mmc-fg-groupcount { margin-left: auto; font-weight: 400; font-variant-numeric: tabular-nums; color: var(--mmc-faint); }
.mmc-fg-items { display: flex; flex-direction: column; gap: 2px; }
.mmc-fg-item {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 4px 8px 4px 4px; border-radius: 9px;
  border: 0; background: none; cursor: pointer; text-align: left; font-family: inherit;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-fg-item:hover { background: var(--mmc-wash); color: var(--mmc-text); }
/* The one you are on: an amber edge, as on every rail in the pack. */
.mmc-fg-item.on { background: var(--mmc-wash-2); color: var(--mmc-strong); box-shadow: inset 2px 0 0 var(--mmc-accent); }
.mmc-fg-itemname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-fg-itemnote { flex: none; font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off); font-variant-numeric: tabular-nums; }
/* Made and not looked at: the name is heavier, the way an unread letter is. */
.mmc-fg-item.unseen .mmc-fg-itemname { color: var(--mmc-strong); font-weight: 600; }
.mmc-fg-setrow { padding: 8px 10px; }
.mmc-fg-shelffoot { margin-top: auto; display: flex; flex-direction: column; gap: 6px; }
/* A thumbnail is pixel art at a whole zoom, on a checkerboard so a sprite's
   transparency is seen as transparency and not as the shelf's grey. */
.mmc-fg-thumb {
  flex: none; width: 36px; height: 36px; border-radius: 7px; overflow: hidden; box-sizing: border-box;
  display: flex; align-items: center; justify-content: center; background: var(--mmc-fg-check);
}
.mmc-fg-thumb.empty { background: none; border: 1px dashed var(--mmc-line-2); }
.mmc-fg-thumb img {
  max-width: 100%; max-height: 100%; display: block; image-rendering: pixelated; -webkit-user-drag: none;
}
.mmc-fg-thumb.big { width: auto; height: auto; aspect-ratio: 1; border-radius: 9px; }
/* Where an asset stands, one small mark at the row's end: a ring planned, a
   dot made, a square gone out to every engine, a dashed ring the pack's mark
   for "real, but not what it was". The words are the row's tooltip. */
.mmc-fg-mark { flex: none; width: 7px; height: 7px; border-radius: 50%; box-sizing: border-box; }
.mmc-fg-mark.planned { border: 1px solid var(--mmc-line-3); }
.mmc-fg-mark.made { background: var(--mmc-dim); }
.mmc-fg-mark.exported { background: var(--mmc-strong); border-radius: 1.5px; }
.mmc-fg-mark.stale { border: 1.5px dashed var(--mmc-dim); }
/* After a check, how many problems an asset has for the engine in the foot. */
.mmc-fg-bad {
  flex: none; min-width: 16px; padding: 0 5px; border-radius: 8px; box-sizing: border-box;
  font-size: calc(10.5px * var(--mmc-type)); font-weight: 600; line-height: 16px;
  text-align: center; font-variant-numeric: tabular-nums;
  color: var(--mmc-bad); border: 1px solid currentColor;
}

/* --- the glass --------------------------------------------------------------------- */
.mmc-fg-glassbar { flex: none; display: flex; align-items: center; gap: 10px; min-height: 30px; }
.mmc-fg-seg { display: flex; gap: 2px; padding: 2px; border-radius: 9px; background: var(--mmc-surface); }
.mmc-fg-segbutton {
  padding: 4px 12px; border-radius: 7px; border: 0; background: none; cursor: pointer; font-family: inherit;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); font-variant-numeric: tabular-nums;
}
.mmc-fg-segbutton:hover:not(:disabled) { color: var(--mmc-text); }
.mmc-fg-segbutton:disabled { opacity: .45; cursor: default; }
.mmc-fg-segbutton.on { background: var(--mmc-surface-3); color: var(--mmc-strong); font-weight: 600; }
.mmc-fg-zoom { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-off); font-variant-numeric: tabular-nums; }
/* Sized in script to a whole-number zoom (forge.js fitGlass), so every pixel of
   a sprite is the same number of screen pixels. Unsmoothed, because a pixel
   blurred into its neighbour is not the pixel the engine will draw. A picture
   larger than the glass is shrunk, and only then smoothed. */
.mmc-fg-glass { display: block; image-rendering: pixelated; user-select: none; -webkit-user-drag: none; }
.mmc-fg-glass.shrunk { image-rendering: auto; }

/* Under the glass, one line each: where, what, and the code an agent branches
   on. The code is set as code because it is one; it is never reworded. */
.mmc-fg-problems { flex: none; max-height: 22vh; overflow: auto; }
.mmc-fg-problems:empty { display: none; }
.mmc-fg-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; }
.mmc-fg-list li {
  display: grid; grid-template-columns: minmax(70px, auto) 1fr auto; gap: 12px; align-items: baseline;
  padding: 6px 2px; font-size: calc(12px * var(--mmc-type));
}
.mmc-fg-list li + li { border-top: 1px solid var(--mmc-line); }
.mmc-fg-wherein { color: var(--mmc-dim); font-variant-numeric: tabular-nums; white-space: nowrap; }
.mmc-fg-what { color: var(--mmc-text); }
.mmc-fg-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-bad);
}

/* --- the foot ------------------------------------------------------------------------ */
.mmc-fg-foot { flex: none; display: flex; align-items: center; gap: 10px; min-height: calc(40px * var(--mmc-type)); }
.mmc-fg-statusline {
  flex: 1 1 auto; min-width: 0; display: flex; align-items: center; gap: 8px;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}
.mmc-fg-statusline span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-fg-footlabel { flex: none; font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim); font-variant-numeric: tabular-nums; }

/* --- the inspector --------------------------------------------------------------------- */
.mmc-fg-inhead { display: flex; flex-direction: column; gap: 3px; }
.mmc-fg-title {
  margin: 0; font-size: calc(20px * var(--mmc-type)); font-weight: 600; letter-spacing: -.01em;
  color: var(--mmc-strong); overflow-wrap: anywhere;
}
.mmc-fg-kindtag { font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-text); font-variant-numeric: tabular-nums; }
.mmc-fg-state { font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-off); }
.mmc-fg-state.stale { color: var(--mmc-warn); }
.mmc-fg-insection { display: flex; flex-direction: column; gap: 10px; padding-top: 16px; border-top: 1px solid var(--mmc-line); }
.mmc-fg-subhead { margin: 0; font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; color: var(--mmc-text); }
.mmc-fg-masters { display: grid; grid-template-columns: repeat(auto-fill, minmax(64px, 1fr)); gap: 6px; }
.mmc-fg-more { padding-top: 14px; border-top: 1px solid var(--mmc-line); }
.mmc-fg-more > summary {
  cursor: pointer; font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; color: var(--mmc-text);
}
.mmc-fg-more > * + * { margin-top: 12px; }
.mmc-fg-inend { margin-top: auto; display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
.mmc-fg-anims { display: flex; flex-direction: column; gap: 4px; }
.mmc-fg-anim, .mmc-fg-animhead {
  display: grid; grid-template-columns: minmax(0, 1fr) 50px 50px auto 22px; gap: 4px; align-items: center;
}
.mmc-fg-anim .mmc-fg-num { width: 100%; }
.mmc-fg-animhead { font-size: calc(10.5px * var(--mmc-type)); color: var(--mmc-off); }
.mmc-fg-loop { display: flex; align-items: center; gap: 4px; font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim); }

/* --- the drawer -------------------------------------------------------------------- */
/* The project's settings slide over the inspector's side of the room: seldom
   touched, so never in the way, and the glass stays in view while they change. */
.mmc-fg-drawer {
  position: absolute; top: 0; right: 0; bottom: 0; z-index: 3; width: min(400px, 92vw); box-sizing: border-box;
  display: flex; flex-direction: column; background: var(--mmc-float);
  border-left: 1px solid var(--mmc-line-2); box-shadow: -18px 0 40px var(--mmc-shadow-soft);
  transform: translateX(104%); visibility: hidden;
  transition: transform 220ms cubic-bezier(.2, .7, .2, 1), visibility 0s linear 220ms;
}
.mmc-fg-drawer.open { transform: none; visibility: visible; transition: transform 220ms cubic-bezier(.2, .7, .2, 1); }
.mmc-fg-drawerhead {
  flex: none; display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 16px 16px 12px 20px; border-bottom: 1px solid var(--mmc-line);
}
.mmc-fg-drawerbody { flex: 1; overflow: auto; padding: 18px 20px 24px; display: flex; flex-direction: column; gap: 22px; }
.mmc-fg-where {
  margin: 0; display: flex; flex-direction: column; gap: 3px;
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-off);
}
.mmc-fg-swatches { display: flex; flex-wrap: wrap; gap: 6px; }
.mmc-fg-swatch {
  position: relative; width: 28px; height: 28px; padding: 0; border-radius: 7px; cursor: pointer;
  border: 1px solid var(--mmc-line-2); background: var(--swatch); box-sizing: border-box;
}
.mmc-fg-swatch:hover:not(.mmc-fg-wellnew) { box-shadow: 0 0 0 2px var(--mmc-bad); }
.mmc-fg-wellnew {
  display: flex; align-items: center; justify-content: center; background: none;
  border: 1px dashed var(--mmc-line-3); color: var(--mmc-dim);
}
.mmc-fg-wellnew:hover { color: var(--mmc-text); border-color: var(--mmc-dim); }
.mmc-fg-wellnew svg { stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-fg-addcolour { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; }

/* --- menus -------------------------------------------------------------------------- */
.mmc-fg-menu { min-width: 230px; display: flex; flex-direction: column; gap: 1px; }
.mmc-fg-menurow {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 7px 10px; border-radius: 9px;
  border: 0; background: none; cursor: pointer; text-align: left; font-family: inherit;
  font-size: calc(12.5px * var(--mmc-type)); color: var(--mmc-text);
}
.mmc-fg-menurow:hover { background: var(--mmc-wash); }
.mmc-fg-menurow.on { color: var(--mmc-strong); font-weight: 600; }
.mmc-fg-menuname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mmc-fg-menunote { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); font-weight: 400; }
.mmc-fg-menunew { margin-top: 4px; color: var(--mmc-dim); }
.mmc-fg-menunew svg { stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-fg-newpop { width: min(360px, 92vw); box-sizing: border-box; }
.mmc-fg-newpop.wide { width: min(440px, 92vw); }
.mmc-fg-kinds { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
.mmc-fg-kind {
  display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--mmc-line); background: none; text-align: left; font-family: inherit;
}
.mmc-fg-kind:hover { background: var(--mmc-wash); }
.mmc-fg-kind.on { border-color: var(--mmc-line-3); background: var(--mmc-wash-2); }
.mmc-fg-kindname { font-size: calc(12.5px * var(--mmc-type)); font-weight: 600; color: var(--mmc-strong); }
.mmc-fg-kindhelp {
  font-size: calc(11px * var(--mmc-type)); line-height: 1.35; color: var(--mmc-dim);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.mmc-fg-newname { display: flex; gap: 6px; margin-top: 10px; }
.mmc-fg-popbody { display: flex; flex-direction: column; gap: 8px; padding: 0 2px 2px; }

/* --- the pose stage -------------------------------------------------------------------- */
/* A floor of light under the figure, so it stands in the room rather than
   floating on a card. The viewer's canvas is transparent over it. */
.mmc-fg-stage {
  flex: 1; min-height: 0; position: relative; overflow: hidden; border-radius: 14px;
  border: 1px solid var(--mmc-line);
  background: radial-gradient(ellipse 60% 38% at 50% 92%,
    color-mix(in oklab, var(--mmc-ground) 80%, var(--mmc-ink)) 0, transparent 70%), var(--mmc-surface);
}
.mmc-fg-stage.drawn { background: var(--mmc-media-bg); }
.mmc-fg-canvas { display: block; width: 100%; height: 100%; touch-action: none; outline: none; }
.mmc-fg-stagehint {
  position: absolute; left: 14px; bottom: 10px; right: 14px; margin: 0; pointer-events: none;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-off);
}
.mmc-fg-stageinvite {
  position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 10px; text-align: center; padding: 24px;
}
.mmc-fg-invitebuttons { display: flex; gap: 8px; margin-top: 8px; }
/* What the render job drew, side by side as the sprite grid will hold them. */
.mmc-fg-drawn { position: absolute; inset: 0; display: flex; align-items: center; gap: 10px; padding: 16px; overflow-x: auto; }
.mmc-fg-cell { margin: 0; height: 100%; flex: none; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.mmc-fg-cell img { height: calc(100% - 24px); width: auto; border-radius: 6px; background: #fff; display: block; }
.mmc-fg-cell figcaption { font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); font-variant-numeric: tabular-nums; }

/* The frame strip: each frame a sheet of animation paper. The one you are on
   has the amber edge; the ones either side carry their ghost's colour. */
.mmc-fg-strip { flex: none; display: flex; align-items: center; gap: 12px; }
.mmc-fg-reel {
  flex: 1; min-width: 0; display: flex; gap: 6px; overflow-x: auto; padding: 4px 3px 6px;
  scrollbar-width: thin;
}
.mmc-fg-frame {
  position: relative; flex: none; width: 44px; height: 99px; padding: 0; box-sizing: border-box;
  border-radius: 6px; overflow: hidden; cursor: pointer;
  border: 1px solid var(--mmc-line-2); background: var(--mmc-fg-paper);
}
.mmc-fg-frame img { display: block; width: 100%; height: 100%; object-fit: cover; -webkit-user-drag: none; }
.mmc-fg-frame:hover { border-color: var(--mmc-dim); }
.mmc-fg-frame.on { outline: 2px solid var(--mmc-accent); outline-offset: 1px; border-color: transparent; }
.mmc-fg-frame.prev::after, .mmc-fg-frame.next::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: var(--mmc-fg-prev);
}
.mmc-fg-frame.next::after { background: var(--mmc-fg-next); }
/* With keys: the frames somebody posed carry a diamond, and the in-betweens
   the server drew are fainter, so the strip reads as an animator's chart. */
.mmc-fg-frame.key::before {
  content: ""; position: absolute; right: 5px; top: 5px; width: 6px; height: 6px; z-index: 1;
  background: var(--mmc-accent); transform: rotate(45deg); border-radius: 1px;
}
.mmc-fg-frame.tween img { opacity: 0.55; }
.mmc-fg-keybutton.on { border-color: var(--mmc-accent); color: var(--mmc-strong); }
.mmc-fg-easerow { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.mmc-fg-easerow span { color: var(--mmc-dim); }
.mmc-fg-framewait { position: absolute; inset: 0; background: linear-gradient(#0000, #0000 60%, #00000010); }
.mmc-fg-framenum {
  position: absolute; left: 4px; top: 2px; font-size: 10px; font-weight: 600; color: #6b6b66;
  font-variant-numeric: tabular-nums;
}
.mmc-fg-addframe {
  display: flex; align-items: center; justify-content: center; background: none;
  border: 1px dashed var(--mmc-line-3); color: var(--mmc-dim);
}
.mmc-fg-addframe:hover { color: var(--mmc-text); }
.mmc-fg-addframe svg { stroke: currentColor; fill: none; stroke-width: 1.8; }
.mmc-fg-play {
  flex: none; display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; padding: 0; border-radius: 50%; cursor: pointer;
  border: 1px solid var(--mmc-line-2); background: var(--mmc-surface); color: var(--mmc-strong);
}
.mmc-fg-play:hover:not(:disabled) { background: var(--mmc-surface-2); }
.mmc-fg-play:disabled { opacity: .4; cursor: default; }
.mmc-fg-play.on, .mmc-fg-play.on:hover:not(:disabled) { background: var(--mmc-accent); border-color: transparent; color: var(--mmc-on-accent); }
.mmc-fg-play svg { stroke: currentColor; fill: currentColor; stroke-width: 1.4; }
.mmc-fg-onion {
  flex: none; display: flex; align-items: center; gap: 6px; cursor: pointer;
  font-size: calc(12px * var(--mmc-type)); color: var(--mmc-dim);
}

/* Symmetry, beside the Pose and Drawn switch: a mode, so amber while it is on. */
.mmc-fg-mirror {
  display: flex; align-items: center; gap: 6px; padding: 4px 11px 4px 9px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--mmc-line-2); background: none; color: var(--mmc-dim); font-family: inherit;
  font-size: calc(12px * var(--mmc-type));
}
.mmc-fg-mirror:hover { color: var(--mmc-text); }
.mmc-fg-mirror svg { stroke: currentColor; fill: none; stroke-width: 1.6; }
.mmc-fg-mirror.on { border-color: var(--mmc-accent); color: var(--mmc-strong); background: color-mix(in srgb, var(--mmc-accent) 14%, transparent); }
.mmc-fg-mirror.on svg { stroke: var(--mmc-accent); }

/* The view pad: a cube unfolded in the stage's corner. Top sits over Front,
   Right and Left either side of it, Back at the end of the row, as the faces
   of a box lie when it is opened flat; the sprite camera hangs under Front,
   because it is the view the drawing is made from. */
.mmc-fg-views {
  position: absolute; top: 12px; right: 12px; z-index: 2;
  display: grid; gap: 2px; padding: 4px; border-radius: 10px;
  grid-template-columns: repeat(4, auto);
  grid-template-areas: ". top . ." "a b c d" ". cam cam .";
  background: var(--mmc-scrim-3); border: 1px solid var(--mmc-line);
}
.mmc-fg-face {
  min-width: 44px; height: 26px; padding: 0 8px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--mmc-line); background: var(--mmc-surface); font-family: inherit;
  font-size: calc(11px * var(--mmc-type)); color: var(--mmc-dim); white-space: nowrap;
}
.mmc-fg-face:hover { color: var(--mmc-text); border-color: var(--mmc-line-3); }
.mmc-fg-face.on { color: var(--mmc-strong); border-color: var(--mmc-strong); background: var(--mmc-surface-3); }
.mmc-fg-face.cam { margin-top: 3px; }

/* The turn a set is drawn at: eight points round a ring, the needle the way
   the figure will face. Turned, not chosen from a list, because a direction
   is a direction. */
.mmc-fg-compass {
  position: relative; width: 128px; height: 128px; margin: 6px auto 26px; border-radius: 50%;
  border: 1px solid var(--mmc-line-2); background: var(--mmc-tint);
}
.mmc-fg-compass::after {
  content: ""; position: absolute; left: 50%; top: 50%; width: 8px; height: 8px; margin: -4px;
  border-radius: 50%; background: var(--mmc-strong);
}
.mmc-fg-point {
  position: absolute; left: 50%; top: 50%; width: 16px; height: 16px; margin: -8px; padding: 0;
  border-radius: 50%; cursor: pointer; border: 1.5px solid var(--mmc-line-3); background: var(--mmc-bg);
  transform: rotate(var(--turn)) translateY(-54px);
}
.mmc-fg-point:hover { border-color: var(--mmc-dim); }
.mmc-fg-point.on { background: var(--mmc-accent); border-color: var(--mmc-accent); }
.mmc-fg-needle {
  position: absolute; left: 50%; top: calc(50% - 40px); width: 2px; height: 40px; margin-left: -1px;
  border-radius: 1px; background: var(--mmc-strong); transform-origin: 50% 100%; transform: rotate(var(--turn));
  transition: transform 180ms ease;
}
.mmc-fg-compassread {
  position: absolute; left: 0; right: 0; bottom: -22px; text-align: center; pointer-events: none;
  font-size: calc(11.5px * var(--mmc-type)); color: var(--mmc-dim); font-variant-numeric: tabular-nums;
}
.mmc-fg-credit { margin: 0; font-size: calc(11px * var(--mmc-type)); line-height: 1.5; color: var(--mmc-off); }
.mmc-fg-credit a { color: var(--mmc-dim); text-underline-offset: 2px; }

@media (prefers-reduced-motion: reduce) {
  .mmc-fg-drawer, .mmc-fg-drawer.open, .mmc-fg-needle { transition: none; }
}
/* A narrow window stacks the three places: the shelf a short strip on top,
   the glass, then the inspector under it, all in one scroll. */
@media (max-width: 900px) {
  .mmc-fg-room, .mmc-fg-page { flex-direction: column; overflow: auto; }
  .mmc-fg-shelf, .mmc-fg-inspector { width: auto; border: 0; overflow: visible; }
  .mmc-fg-shelf { border-bottom: 1px solid var(--mmc-line); max-height: none; }
  .mmc-fg-middle { min-height: 70vh; padding: 12px 16px; }
  .mmc-fg-inspector { border-top: 1px solid var(--mmc-line); }
  .mmc-fg-start { grid-template-columns: minmax(0, 1fr); gap: 32px; padding: 24px 16px; }
  .mmc-fg-tab { padding: 5px 10px; }
  .mmc-fg-barbutton span { display: none; }
  .mmc-fg-list li { grid-template-columns: 1fr; gap: 2px; }
}
`;
