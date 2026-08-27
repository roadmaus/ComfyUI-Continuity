// Two doors to one list: where the editor can go.
//
// The fullscreen shell is the suite's room, and the card in the middle is the
// piece being worked on. Everything else you might reach for — another piece
// in the same graph, a fresh one, and in time the benches (the sheet stage,
// the scene blockout) — is a *destination*, and destinations are a list, not
// chrome. Nothing is docked and no rail appears: the wordmark drops the list
// for the mouse, ⌘K raises the same list for the keyboard, and a new tool is a
// new row in both rather than a new button anywhere.
//
// The list itself is the caller's — fullscreen.js builds it from the graph at
// the moment of opening, because the graph is where pieces live and a list
// built earlier would name nodes that have been deleted or retitled since.
// This module only draws it, twice.

import { el, icon, dismissable, mountOverlay, placeNear } from "./dom.js";
import { t } from "./i18n.js";

/**
 * One destination row, shared by both doors so they cannot drift apart.
 *
 * @param {object} item  { label, sub?, glyph?, here?, go }
 *   `here` marks the piece already on the card — still a row, because a list
 *   with the current thing missing reads as a list with a hole in it, but a
 *   press on it only closes the door.
 */
function row(item, close) {
  return el("button", {
    class: "mmc-nav-item" + (item.here ? " here" : ""),
    ...(item.here ? { "aria-current": "true" } : {}),
    onclick: () => { close(); if (!item.here) item.go(); },
  }, [
    item.glyph ? icon(item.glyph, 15) : null,
    el("span", { class: "mmc-nav-word" }, [
      el("span", { class: "mmc-nav-label", text: item.label }),
      item.sub ? el("span", { class: "mmc-nav-sub", text: item.sub }) : null,
    ]),
  ]);
}

/**
 * The wordmark's menu: the groups as they are, each under its title.
 * A popover like any other in the pack — `dismissable` takes the outside
 * click and Escape, `placeNear` hangs it under the mark.
 */
export function openNavMenu({ anchor, groups }) {
  const pop = el("div", { class: "mmc-pop mmc-nav" });
  const close = dismissable(pop);
  for (const group of groups) {
    if (!group.items.length) continue;
    pop.appendChild(el("div", { class: "mmc-pop-title", text: group.title }));
    for (const item of group.items) pop.appendChild(row(item, close));
  }
  document.body.appendChild(pop);
  placeNear(pop, anchor, { above: false });
}

/**
 * ⌘K: the same list flattened behind a filter, with a group tag on each row
 * where the menu had a heading. Arrows walk it, Enter takes the lit row, and
 * typing narrows — against the label and the sub both, so a piece is found by
 * its family as well as by its name.
 */
export function openNavPalette({ groups }) {
  const all = groups.flatMap((group) =>
    group.items.map((item) => ({ ...item, tag: group.title })));
  let shown = all;
  let hot = 0;

  const list = el("div", { class: "mmc-nav-list" });
  const paint = () => {
    // The current piece is never the answer to "where to?", so the lit row
    // starts on the first row that goes somewhere.
    if (shown[hot]?.here) hot = shown.findIndex((item) => !item.here);
    list.replaceChildren(...(shown.length
      ? shown.map((item, index) => {
          const button = row(item, () => unmount());
          button.classList.toggle("hot", index === hot);
          button.appendChild(el("span", { class: "mmc-nav-tag", text: item.tag }));
          return button;
        })
      : [el("div", { class: "mmc-nav-empty", text: t("Nothing by that name") })]));
  };

  const input = el("input", {
    class: "mmc-nav-input", placeholder: t("Where to?"),
    oninput: () => {
      const want = input.value.trim().toLowerCase();
      shown = want
        ? all.filter((item) =>
            (item.label + " " + (item.sub ?? "")).toLowerCase().includes(want))
        : all;
      hot = 0;
      paint();
    },
    onkeydown: (event) => {
      const move = { ArrowDown: 1, ArrowUp: -1 }[event.key];
      if (move) {
        event.preventDefault();
        if (!shown.length) return;
        hot = (hot + move + shown.length) % shown.length;
        paint();
        return;
      }
      if (event.key !== "Enter") return;
      const item = shown[hot];
      if (!item || item.here) return;
      unmount();
      item.go();
    },
  });

  const overlay = el("div", {
    class: "mmc-overlay mmc-nav-veil",
    // The room around the card is the way out, same as every overlay here.
    onpointerdown: (event) => { if (event.target === overlay) unmount(); },
  }, [el("div", { class: "mmc-nav-palette" }, [input, list])]);

  const unmount = mountOverlay(overlay, () => unmount());
  paint();
  input.focus();
}
