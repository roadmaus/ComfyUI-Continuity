// The wordmark's menu: the editor's tools, as a list.
//
// The fullscreen shell is the suite's room, and the card in the middle is the
// piece being worked on. The tools — the preset library today, the benches in
// time — are destinations, and destinations are a list rather than chrome:
// nothing is docked, no rail stands open, and a new tool is a new row here
// rather than a new button anywhere.
//
// There was a ⌘K palette over the same list once. It went: every pack on the
// canvas wants that keystroke, and a list one press long does not need a
// filter. The list itself is the caller's — fullscreen.js builds it at the
// moment of opening, because the right preset target is whatever body is on
// the card just then. This module only draws it.

import { el, icon, dismissable, placeNear } from "./dom.js";

/**
 * Drop the menu under the mark. A popover like any other in the pack —
 * `dismissable` takes the outside click and Escape, `placeNear` hangs it
 * under the anchor.
 *
 * @param {object} options
 * @param {HTMLElement} options.anchor  the wordmark button
 * @param {Array} options.groups  [{ title, items: [{ label, sub?, glyph?, go }] }]
 */
export function openNavMenu({ anchor, groups }) {
  const pop = el("div", { class: "mmc-pop mmc-nav" });
  const close = dismissable(pop);
  for (const group of groups) {
    if (!group.items.length) continue;
    pop.appendChild(el("div", { class: "mmc-pop-title", text: group.title }));
    for (const item of group.items) {
      pop.appendChild(el("button", {
        class: "mmc-nav-item",
        onclick: () => { close(); item.go(); },
      }, [
        item.glyph ? icon(item.glyph, 15) : null,
        el("span", { class: "mmc-nav-word" }, [
          el("span", { class: "mmc-nav-label", text: item.label }),
          item.sub ? el("span", { class: "mmc-nav-sub", text: item.sub }) : null,
        ]),
      ]));
    }
  }
  document.body.appendChild(pop);
  placeNear(pop, anchor, { above: false });
}
