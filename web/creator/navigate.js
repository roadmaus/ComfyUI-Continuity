// The wordmark's dashboard: the editor's tools, as cards.
//
// The fullscreen shell is the suite's room, and the card in the middle is the
// piece being worked on. The tools — the preset library today, the benches in
// time — are destinations, and pressing the mark turns the room over to show
// them: nothing is docked, no rail stands open, and a new tool is a new card
// here rather than a new button anywhere.
//
// It was a dropdown of rows before this, and a ⌘K palette over the same list
// before that. The palette went because every pack on the canvas wants that
// keystroke. The dropdown went because a tool is not a menu item: a row four
// hundred pixels wide can say a name and half a sentence, and the thing being
// named is a whole surface with a shape of its own. A card has room to show
// what it is before you commit to opening it, and a grid of them has room to
// grow — which is the part that matters, because today's grid holds one tool
// and next year's holds eight.
//
// The list is still the caller's — fullscreen.js builds it at the moment of
// opening, because the right preset target is whatever body is on the card
// just then. This module only draws it.

import { el, icon } from "./dom.js";
import { t } from "./i18n.js";

/**
 * Build the dashboard surface. The caller mounts it, owns whether it is up,
 * and gets `onLeave` when a card is pressed — going somewhere is the one thing
 * that closes it besides the mark and Escape.
 *
 * @param {object} options
 * @param {Array} options.groups  [{ title, items: [{ label, sub?, glyph?, soon?, go }] }]
 * @param {Function} options.onLeave  called before the destination opens
 */
export function buildDashboard({ groups, onLeave }) {
  const dash = el("div", { class: "mmc-dash" });
  const sheet = el("div", { class: "mmc-dash-sheet" }, [
    // What every card on this surface has in common, said once. Without it the
    // grid is a set of names with no statement of what pressing one does to the
    // piece you left behind on the card.
    el("p", { class: "mmc-dash-lede", text: t("Each tool opens over the piece on the card.") }),
  ]);
  // The stagger is one order across the whole surface rather than per section,
  // so the cards arrive as one sweep — see the styles for the cap on it.
  let n = 0;
  let last = null;
  for (const group of groups) {
    if (!group.items.length) continue;
    sheet.appendChild(el("div", { class: "mmc-dash-head" }, [
      el("span", { text: group.title }),
      // The rule is the section's width, drawn. It is why the eyebrow does not
      // need a box: the line says where the group ends.
      el("span", { class: "mmc-dash-rule" }),
    ]));
    last = el("div", { class: "mmc-dash-grid" });
    for (const item of group.items) last.appendChild(card(item, n++, onLeave));
    sheet.appendChild(last);
  }
  // And the one card that is not a tool: the empty place the next one lands in.
  // A grid of one card reads as a surface that failed to load; a grid of one
  // card and a marked-out space beside it reads as the first of a set, which is
  // what it is. In the last grid rather than under it, because that is where a
  // tool would actually appear — a dashed tile on a row of its own is a second
  // section about nothing. It is not a button and it does not take focus: there
  // is nothing there to press yet.
  (last ?? sheet.appendChild(el("div", { class: "mmc-dash-grid" }))).appendChild(
    el("div", { class: "mmc-dash-card soon" }, [
      el("div", { class: "mmc-dash-plate" }),
      el("div", { class: "mmc-dash-word" }, [
        el("span", { class: "mmc-dash-name", text: t("More to come") }),
        el("span", { class: "mmc-dash-sub", text: t("New tools arrive here as cards.") }),
      ]),
    ]));
  dash.appendChild(sheet);
  return dash;
}

/**
 * One tool.
 *
 * The plate on top carries the tool's own glyph at poster size, cropped by the
 * plate's bottom edge — the same drawing the rail uses at fifteen pixels, given
 * enough room to be a picture instead of a bullet. It is the only decoration on
 * the surface, and it is doing a job: at a glance across the grid the plates
 * are what tell the cards apart, before any of the names are read.
 */
function card(item, index, onLeave) {
  const root = el("button", {
    class: "mmc-dash-card",
    onclick: () => { onLeave?.(); item.go(); },
  }, [
    el("div", { class: "mmc-dash-plate" }, [
      item.glyph ? el("span", { class: "mmc-dash-glyph" }, [icon(item.glyph, 108)]) : null,
    ]),
    el("div", { class: "mmc-dash-word" }, [
      el("span", { class: "mmc-dash-name", text: item.label }),
      item.sub ? el("span", { class: "mmc-dash-sub", text: item.sub }) : null,
    ]),
  ]);
  // Its place in the arrival sweep. A custom property rather than a delay
  // written here, so the styles keep the whole of the timing — including the
  // cap that stops the twentieth card arriving a second late.
  root.style.setProperty("--i", String(index));
  return root;
}
