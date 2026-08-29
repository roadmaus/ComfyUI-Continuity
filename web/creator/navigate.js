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
 * @param {Array} options.groups  [{ title, items: [{ label, sub?, glyph?, art?, go }] }]
 *   where `art` is `{ kind, url }` — the picture this card is made of, and which
 *   of the treatments below it is drawn in. Without one the card wears its glyph.
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
 * The plate on top is a picture, and what the card does to that picture is what
 * the tool does to a frame: the ControlNet card traces it, the upscale card
 * shows it soft against sharp, the preset card deals it out as a deck. Which
 * picture is the caller's business — the Go-to cards hand over the piece, the
 * benches hand over a plate of their own — and the treatment is the same either
 * way, which is what keeps the grid one surface.
 *
 * A card with no picture at all — a Go-to card on a piece nobody has rendered
 * or attached anything to yet — falls back to its glyph at poster size, cropped
 * by the plate's bottom edge. That is the surface on its first day, saying so.
 */
function card(item, index, onLeave) {
  const root = el("button", {
    class: "mmc-dash-card",
    onclick: () => { onLeave?.(); item.go(); },
  }, [
    plate(item),
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

/**
 * The picture on a card, in whichever treatment the tool asks for.
 *
 * The caller hands over material — `{ kind, url }` — and never a node, for the
 * same reason it hands over `go` and not a click handler: fullscreen.js knows
 * which frame is the piece's, this module knows what a card looks like, and
 * neither has ever had to learn the other's half.
 */
function plate(item) {
  const treat = item.art?.url ? TREATMENTS[item.art.kind] : null;
  return el("div", { class: "mmc-dash-plate" }, [
    treat
      ? treat(item.art)
      : item.glyph ? el("span", { class: "mmc-dash-glyph" }, [icon(item.glyph, 108)]) : null,
  ]);
}

/** A picture, at the plate's size and cropped to it. */
const frame = (url, cls = "") =>
  el("img", { class: `mmc-dash-shot ${cls}`.trim(), src: url, alt: "", loading: "lazy", draggable: false });

/**
 * The treatments, by name.
 *
 * Two of them — the tracing and the upscale — are the same gesture: the picture
 * twice, one copy over the other, with a seam between them that the pointer
 * moves. That is not decoration either. A tracing and an upscale are both
 * *comparisons* — this frame, and what the tool would hand back — and a card
 * that shows only the after has thrown away the half that explains it.
 */
const TREATMENTS = {
  /** The still, plain and whole. Nothing is done to it, because nothing is what
   *  the pre-stage card does: it takes you to this picture. */
  still: (art) => frame(art.url),

  /** The shot, before there is one.
   *
   *  The still it will be built from, ruled into frames. A shot is time and a
   *  still is not, and the two cards sit side by side at the top of the surface
   *  — without something said in the picture they are the same photograph twice.
   *  Ruled rather than repeated: three copies of the same face across a card is
   *  a mistake, not a filmstrip. */
  strip: (art) => el("div", { class: "mmc-dash-strip" }, [
    frame(art.url),
    el("span", { class: "mmc-dash-frames" }),
  ]),

  /** The shot, moving. Still at rest and playing under the pointer, exactly as
   *  the takes on the lip behave — one clip looping on a dashboard is a card
   *  that is alive, six of them would be noise. */
  clip: (art) => {
    const media = el("video", {
      class: "mmc-dash-shot", src: `${art.url}#t=0.1`,
      loop: true, playsinline: true, preload: "metadata",
    });
    media.muted = true;                 // the property: the attribute is only read at parse
    media.addEventListener("pointerenter", () => media.play?.().catch(() => {}));
    media.addEventListener("pointerleave", () => { media.pause(); media.currentTime = 0.1; });
    return media;
  },

  /** The frame, and the map the bench would make of it.
   *
   *  A real depth pass, run through the same Depth Anything the bench runs and
   *  shipped beside the picture it was made from — not a filter standing in for
   *  one. The browser can convolve an edge kernel over an image and that is what
   *  this card did first, but a Laplacian over a black stage is a handful of thin
   *  lines: at two hundred and thirty pixels wide it read as a dark smudge, and
   *  it was a simulation of the tool rather than the tool's own output. Depth is
   *  a solid, legible thing at any size, and it is what came out of the bench. */
  trace: (art) => follows(el("div", { class: "mmc-dash-split" }, [
    frame(art.url),
    el("div", { class: "mmc-dash-wipe" }, [frame(art.made)]),
    el("span", { class: "mmc-dash-seam" }),
  ])),

  /** The frame, small against large. The left half is genuinely a low-resolution
   *  copy — a thirty-pixel canvas blown up by the browser — rather than a blur
   *  filter, because blur is what a soft photograph looks like and blocks are
   *  what a small file looks like, and the bench is about the second one. */
  scale: (art) => {
    const small = el("canvas", { class: "mmc-dash-shot mmc-dash-blocks", width: 44, height: 25 });
    const source = new Image();
    source.onload = () => {
      // The canvas takes the picture's own shape, so the blocks stay square
      // when the frame is not sixteen by nine.
      small.height = Math.max(1, Math.round(small.width * (source.naturalHeight / source.naturalWidth)));
      small.getContext("2d")?.drawImage(source, 0, 0, small.width, small.height);
    };
    source.src = art.url;
    // The sharp copy is on the right of the seam here rather than the left, so
    // pulling the seam left uncovers what the bench would hand back.
    return follows(el("div", { class: "mmc-dash-split mmc-dash-split-out" }, [
      small,
      el("div", { class: "mmc-dash-wipe mmc-dash-wipe-right" }, [frame(art.url)]),
      el("span", { class: "mmc-dash-seam" }),
    ]));
  },

  /** The frame, dealt out. A preset is a setup you can put back, so the card is
   *  the same picture three times over — one setting, saved, and saved again —
   *  and the deck spreads under the pointer. */
  deck: (art) => el("div", { class: "mmc-dash-deck" }, [
    frame(art.url, "mmc-dash-deck-3"),
    frame(art.url, "mmc-dash-deck-2"),
    frame(art.url, "mmc-dash-deck-1"),
  ]),
};

/**
 * Hand the seam to the pointer.
 *
 * It used to slide to a fixed position on hover, which is a card playing an
 * animation *at* you — the same two frames every time, in the same direction,
 * whatever you did. The seam is a wipe across a picture and a wipe is something
 * you pull: it sits under the pointer's x now, so how much of the tracing you
 * see is how far right you have moved, and the comparison is yours to work.
 *
 * The inline property beats the stylesheet's, so the CSS keeps the rest state
 * and the keyboard's — dropped on the way out, which is what lets it ease back.
 * Tracking itself is untransitioned: a 340ms ease between two pointer samples is
 * a seam that lags the hand by a third of a second.
 */
function follows(split) {
  const put = (event) => {
    const box = split.getBoundingClientRect();
    if (!box.width) return;
    const at = ((event.clientX - box.left) / box.width) * 100;
    split.classList.add("mmc-dash-split-held");
    split.style.setProperty("--wipe", `${Math.min(100, Math.max(0, at))}%`);
  };
  split.addEventListener("pointermove", put);
  split.addEventListener("pointerleave", () => {
    split.classList.remove("mmc-dash-split-held");
    split.style.removeProperty("--wipe");
  });
  return split;
}

