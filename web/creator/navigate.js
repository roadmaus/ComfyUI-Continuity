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
  const sheet = el("div", { class: "mmc-dash-sheet" });
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
  const art = item.art;
  const treat = art && (art.url || DRAWN.has(art.kind)) ? TREATMENTS[art.kind] : null;
  return el("div", { class: "mmc-dash-plate" }, [
    treat
      ? treat(art)
      : item.glyph ? el("span", { class: "mmc-dash-glyph" }, [icon(item.glyph, 108)]) : null,
  ]);
}

/** The treatments that make their own picture rather than being handed one.
 *
 *  The two Go-to cards show the piece when the piece has a frame, because the
 *  piece is what they take you to. Everything else on this surface is drawn:
 *  one picture per tool, in the plate's own ink, with amber on the one thing
 *  that moves — and what moves under the pointer is the tool doing its job,
 *  not the card lighting up. The first cut shipped a photograph per bench
 *  beside the code (a lens barrel, a mannequin, a depth pass of it) and the
 *  grid read as two surfaces: five stills in one key light and two line
 *  drawings. Drawn, the nine cards are one set, nothing in them is a picture of
 *  something else, and nothing smaller than a bar has to survive two hundred
 *  and thirty pixels. The Go-to cards fall back to a drawing too, on the day
 *  the piece has no frame yet. */
const DRAWN = new Set(["frame", "reel", "chat", "dials", "edges", "blocks", "grow", "lift", "forge"]);

/** A drawn plate: one static SVG in the plate's 16:9, built from the constants
 *  in this module and nothing else — no outside text reaches `innerHTML`. */
const drawn = (cls, markup) => {
  const plate = el("div", { class: `mmc-dash-drawn mmc-dash-${cls}` });
  plate.innerHTML = `<svg viewBox="0 0 160 90" aria-hidden="true">${markup}</svg>`;
  return plate;
};

/** Capsule limbs as lines, `width` mapping each limb's thickness; a limb's far
 *  side is marked so the stylesheet can set it back a step. */
const limbs = (list, width = (w) => w) => list.map(([x1, y1, x2, y2, w, far]) =>
  `<line${far ? ' class="mmc-dash-far"' : ""} x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke-width="${width(w)}"/>`).join("");

/** A stand-in landscape — a sun and a hill line, the shapes the image glyph is
 *  made of — clipped to the frame at (x, y, w, h), panned by `shift`. What a
 *  card draws where a picture would go, on a piece that has none yet. */
const scene = (x, y, w, h, shift = 0, sun = 4) => {
  const id = `mmc-dash-scene-${x}-${y}`.replace(/\./g, "_");
  return `<clipPath id="${id}"><rect x="${x}" y="${y}" width="${w}" height="${h}"/></clipPath>`
    + `<g clip-path="url(#${id})"><g transform="translate(${shift} 0)">`
    + `<circle class="mmc-dash-sun" cx="${x + w * 0.74}" cy="${y + h * 0.3}" r="${sun}"/>`
    + `<path class="mmc-dash-hills" d="M${x} ${y + h}V${y + h * 0.76}C${x + w * 0.17} ${y + h * 0.5} ${x + w * 0.28} ${y + h * 0.45} ${x + w * 0.45} ${y + h * 0.65}`
    + `C${x + w * 0.58} ${y + h * 0.8} ${x + w * 0.67} ${y + h * 0.55} ${x + w * 1.1} ${y + h * 0.6}V${y + h}Z"/></g></g>`;
};

/** The forge card's walk: four frames of one cycle, in the order the cells
 *  show them. The first two are the pose stage's mannequin, as capsules
 *  (x1, y1, x2, y2, width, and a 1 for the far side) around a head, in units
 *  of a 52-tall figure centred on x = 0. The last two are the sprite it
 *  becomes, nine pixels wide: "#" the near side, "+" the far. Both were drawn
 *  from one figure by a seeded generator (seed 555472) and are kept as data —
 *  the sprite is that figure rasterised mode-of-cell, so it is the mannequin
 *  in pixels rather than a second drawing that happens to match. */
const WALK = [
  { head: [-0.7, 6, 5.2], limbs: [[0, 28.6, -3.4, 40.6, 7.3, 1], [-3.4, 40.6, -9.1, 49.7, 6.2, 1], [-0.7, 17.2, 3, 23.9, 5.7, 1], [3, 23.9, 7.7, 31.2, 5.2, 1], [-0.7, 18.7, 0, 27, 11.4], [0, 28.6, 6.6, 39.2, 7.3], [6.6, 39.2, 9.1, 47.4, 6.2], [-0.7, 17.2, -4.4, 23.9, 5.7], [-4.4, 23.9, -7.1, 31.2, 5.2]] },
  { head: [-0.7, 6, 5.2], limbs: [[0, 28.2, -1.7, 38.5, 7.3, 1], [-1.7, 38.5, -5.9, 46.2, 6.2, 1], [-0.7, 17.2, 1.7, 23.9, 5.7, 1], [1.7, 23.9, 5.1, 31.2, 5.2, 1], [-0.7, 18.7, 0, 26.7, 11.4], [0, 28.2, 4.8, 40.6, 7.3], [4.8, 40.6, 5.9, 49.7, 6.2], [-0.7, 17.2, -3.1, 23.9, 5.7], [-3.1, 23.9, -4.5, 31.2, 5.2]] },
  ["...##....", "...###...", "...##....", ".........", "...###...", "...###...", "..+###...", "..+####..", "..+####..", "...##++..", "...##++..", "..##..++.", ".###..++.", ".##......"],
  ["...##....", "...###...", "...##....", ".........", "...###...", "...###...", "...###...", "...###...", "...####..", "...##+...", "...##++..", "..###++..", "..##.++..", ".....++.."],
];

/** A picture, at the plate's size and cropped to it. */
const frame = (url, cls = "") =>
  el("img", { class: `mmc-dash-shot ${cls}`.trim(), src: url, alt: "", loading: "lazy", draggable: false });

/**
 * The treatments, by name.
 *
 * The three photographic ones are the Go-to cards' — the piece's own frame,
 * plain, ruled or moving. The rest draw themselves; see `DRAWN`. The tracing
 * keeps the seam the photographed card had, because a tracing is a
 * *comparison* — this figure, and what the bench would read out of it — and a
 * card that shows only the after has thrown away the half that explains it.
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

  /** The still, before there is one.
   *
   *  A frame with registration marks around it — the picture alone in the
   *  middle of the screen, which is what the card does. The marks step outward
   *  under the pointer: the screen clearing around it. */
  frame: () => drawn("frame", `
    <g class="mmc-dash-marks">
      <path class="mmc-dash-m1" d="M38 19V11H46"/><path class="mmc-dash-m2" d="M114 11H122V19"/>
      <path class="mmc-dash-m3" d="M38 69V77H46"/><path class="mmc-dash-m4" d="M114 77H122V69"/>
    </g>
    <g class="mmc-dash-scene">
      <rect class="mmc-dash-pic" x="44" y="17" width="72" height="54" rx="1.5"/>
      ${scene(44, 17, 72, 54, 0, 5)}
    </g>`),

  /** The shot, before there is a still to rule into frames.
   *
   *  A strip of three cells holding one view that pans a step a cell — a shot
   *  is time, and three copies of the same frame would be a mistake rather
   *  than a filmstrip. The playhead steps cell to cell under the pointer, in
   *  the amber the forge card's does. */
  reel: () => {
    const cell = 140 / 3, holes = [];
    for (let x = 13; x < 146; x += 9.2) {
      holes.push(`<rect x="${x}" y="23" width="3.6" height="2.6"/><rect x="${x}" y="64.4" width="3.6" height="2.6"/>`);
    }
    return drawn("reel", `
      <rect class="mmc-dash-strip" x="10" y="21" width="140" height="48" rx="1.5"/>
      <g class="mmc-dash-holes">${holes.join("")}</g>
      ${[0, 1, 2].map((i) => scene(10 + i * cell, 28, cell, 34, -6 * i)).join("")}
      <line class="mmc-dash-cut" x1="${10 + cell}" y1="21" x2="${10 + cell}" y2="69"/>
      <line class="mmc-dash-cut" x1="${10 + cell * 2}" y1="21" x2="${10 + cell * 2}" y2="69"/>
      <rect class="mmc-dash-playhead" x="10" y="21" width="${cell}" height="48"/>`);
  },

  /** A line said, and the frame it turns into.
   *
   *  The asking line is four word-length bars with an amber caret after them
   *  — not letters, which are a smudge at this size. Under it the frame is
   *  only part drawn; the pointer finishes the stroke and the picture fades in
   *  while the caret blinks, which is the room doing what it does. */
  chat: () => drawn("chat", `
    <g class="mmc-dash-ask">
      <line x1="40" y1="22" x2="58" y2="22"/><line x1="62" y1="22" x2="78" y2="22"/>
      <line x1="82" y1="22" x2="90" y2="22"/><line x1="94" y1="22" x2="114" y2="22"/>
    </g>
    <rect class="mmc-dash-caret" x="118.5" y="18" width="1.2" height="8"/>
    <g class="mmc-dash-made">${scene(40, 34, 80, 44, 0, 4.5)}</g>
    <rect class="mmc-dash-frame" x="40" y="34" width="80" height="44" rx="2" pathLength="100"/>`),

  /** A sheet of settings, and where a saved one puts them.
   *
   *  Three sliders with faint amber ticks at the preset's positions and two
   *  more sheets stacked behind. Under the pointer the knobs slide to the
   *  ticks: a preset is a setup you can put back, and this is it being put
   *  back. */
  dials: () => drawn("dials", `
    <rect class="mmc-dash-back mmc-dash-b2" x="22" y="12" width="100" height="56" rx="3"/>
    <rect class="mmc-dash-back mmc-dash-b1" x="26" y="16" width="100" height="56" rx="3"/>
    <rect class="mmc-dash-sheet" x="30" y="20" width="100" height="56" rx="3"/>
    <g class="mmc-dash-track"><line x1="42" y1="34" x2="118" y2="34"/><line x1="42" y1="48" x2="118" y2="48"/><line x1="42" y1="62" x2="118" y2="62"/></g>
    <g class="mmc-dash-tick"><line x1="92" y1="31" x2="92" y2="37"/><line x1="58" y1="45" x2="58" y2="51"/><line x1="104" y1="59" x2="104" y2="65"/></g>
    <circle class="mmc-dash-knob mmc-dash-k1" cx="64" cy="34" r="3"/>
    <circle class="mmc-dash-knob mmc-dash-k2" cx="98" cy="48" r="3"/>
    <circle class="mmc-dash-knob mmc-dash-k3" cx="76" cy="62" r="3"/>`),

  /** The figure, and the edges the bench reads out of it.
   *
   *  The forge's mannequin stands whole on the right of a seam; left of it the
   *  same figure is only its contour, a thin amber line with nothing inside —
   *  which is what an edge pass hands back. The contour is the figure drawn
   *  thick and masked by the figure drawn at size, so where a near limb
   *  crosses a far one the near one's edge wins, as in a line drawing. The
   *  seam is the pointer's, the same gesture the photographed card had. */
  edges: () => {
    const [pose] = WALK;
    const far = pose.limbs.filter((limb) => limb[5]), near = pose.limbs.filter((limb) => !limb[5]);
    const [hx, hy, hr] = pose.head;
    const ground = `<line class="mmc-dash-ground" x1="20" y1="78" x2="140" y2="78"/>`;
    const solid = `<g class="mmc-dash-soft" transform="translate(80 26)">${limbs(pose.limbs)}<circle cx="${hx}" cy="${hy}" r="${hr}"/></g>`;
    const outline = `<g class="mmc-dash-edges" transform="translate(80 26)">`
      + `<defs><mask id="mmc-dash-edge-mask" maskUnits="userSpaceOnUse" x="-40" y="-10" width="80" height="80">`
      + `<rect x="-40" y="-10" width="80" height="80" fill="#fff"/>`
      + `<g class="mmc-dash-body">${limbs(pose.limbs)}<circle cx="${hx}" cy="${hy}" r="${hr}"/></g></mask></defs>`
      + `<g mask="url(#mmc-dash-edge-mask)"><g class="mmc-dash-far">${limbs(far, (w) => w + 1.6)}</g>`
      + `${limbs(near, (w) => w + 1.6)}<circle cx="${hx}" cy="${hy}" r="${hr + 0.8}"/></g></g>`;
    const wipe = el("div", { class: "mmc-dash-wipe mmc-dash-drawn" });
    wipe.innerHTML = `<svg viewBox="0 0 160 90" aria-hidden="true">${ground}${outline}</svg>`;
    const whole = el("div", { class: "mmc-dash-drawn" });
    whole.innerHTML = `<svg viewBox="0 0 160 90" aria-hidden="true">${ground}${solid}</svg>`;
    return follows(el("div", { class: "mmc-dash-split mmc-dash-trace" }, [
      whole, wipe, el("span", { class: "mmc-dash-seam" }),
    ]));
  },

  /** Boxes on a floor, and one camera walked through them.
   *
   *  Three wire boxes on an isometric grid, a dashed amber path across the
   *  floor, and a small camera on it that dollies along under the pointer.
   *  The grid, boxes and path are precomputed on a 2:1 isometric at 8 units a
   *  cell, origin (80, 50): P(a, b) = (80 + (a − b)·6.93, 50 + (a + b)·4). */
  blocks: () => drawn("blocks", `
    <path class="mmc-dash-floor" d="M80 10L10.7 50M80 10L149.3 50M86.93 14L17.63 54M73.07 14L142.37 54M93.86 18L24.56 58M66.14 18L135.44 58M100.79 22L31.49 62M59.21 22L128.51 62M107.72 26L38.42 66M52.28 26L121.58 66M114.65 30L45.35 70M45.35 30L114.65 70M121.58 34L52.28 74M38.42 34L107.72 74M128.51 38L59.21 78M31.49 38L100.79 78M135.44 42L66.14 82M24.56 42L93.86 82M142.37 46L73.07 86M17.63 46L86.93 86M149.3 50L80 90M10.7 50L80 90"/>
    <path class="mmc-dash-box" d="M66.14 12L80 20L66.14 28L52.28 20ZM80 20L80 42L66.14 50L66.14 28ZM66.14 28L66.14 50L52.28 42L52.28 20Z"/>
    <path class="mmc-dash-box" d="M114.65 24L128.51 32L107.72 44L93.86 36ZM128.51 32L128.51 46L107.72 58L107.72 44ZM107.72 44L107.72 58L93.86 50L93.86 36Z"/>
    <path class="mmc-dash-box" d="M86.93 32L97.33 38L86.93 44L76.53 38ZM97.33 38L97.33 68L86.93 74L86.93 44ZM86.93 44L86.93 74L76.53 68L76.53 38Z"/>
    <path class="mmc-dash-dolly" d="M17.63 50C55.75 56 90.39 48 135.44 54"/>
    <g class="mmc-dash-cam"><rect x="-4" y="-2" width="6" height="4" rx=".6"/><path d="M2 -1L5.5 -3V3L2 1Z"/></g>`),

  /** The file small, and the same subject at the size the bench hands back.
   *
   *  A bust in eight-by-five pixels in a small frame, amber rays projecting it
   *  to a large one where it is a smooth silhouette — blocks becoming curves,
   *  which is what resolution is. The large copy sharpens and takes corner
   *  brackets under the pointer. */
  grow: () => {
    const rows = ["...##...", "...##...", "..####..", ".######.", "########"], px = 3.6;
    const dots = rows.flatMap((row, y) => [...row].map((on, x) => on === "." ? ""
      : `<rect x="${(15.6 + x * px).toFixed(1)}" y="${(33 + y * px).toFixed(1)}" width="${px}" height="${px}"/>`)).join("");
    return drawn("grow", `
      <defs><clipPath id="mmc-dash-grow-clip"><rect x="74" y="25" width="72" height="40.5" rx="1.5"/></clipPath></defs>
      <g class="mmc-dash-rays">
        <line x1="14" y1="33" x2="74" y2="25"/><line x1="46" y1="33" x2="146" y2="25"/>
        <line x1="14" y1="51" x2="74" y2="65.5"/><line x1="46" y1="51" x2="146" y2="65.5"/>
      </g>
      <rect class="mmc-dash-pic" x="14" y="33" width="32" height="18" rx="1"/>
      <g class="mmc-dash-px">${dots}</g>
      <rect class="mmc-dash-pic" x="74" y="25" width="72" height="40.5" rx="1.5"/>
      <g class="mmc-dash-smooth" clip-path="url(#mmc-dash-grow-clip)">
        <circle cx="110" cy="40" r="7.5"/><path d="M86 65.5C86 52 98 50 110 50C122 50 134 52 134 65.5Z"/>
      </g>
      <g class="mmc-dash-corners">
        <path d="M74 31V25H80"/><path d="M140 25H146V31"/><path d="M74 59.5V65.5H80"/><path d="M140 65.5H146V59.5"/>
      </g>`);
  },

  /** A picture, its camera, and the mesh at the end of its rays.
   *
   *  The tool's result is a thing you turn in your hands, and a photograph of
   *  one would be the one view of it the card cannot turn. What the card can
   *  show is the idea the tool is built on — the picture stands in front of
   *  its own camera and the mesh is lifted out along the rays through it — in
   *  the amber the tool's own stage draws those rays in. Under the pointer
   *  the rays light and the cube turns, which is the build happening. */
  lift: () => drawn("lift", `
    <g class="mmc-dash-rays">
      <line x1="8" y1="45" x2="150" y2="6"/><line x1="8" y1="45" x2="150" y2="84"/>
      <line x1="8" y1="45" x2="150" y2="30"/><line x1="8" y1="45" x2="150" y2="60"/>
    </g>
    <rect class="mmc-dash-pic" x="40" y="31" width="22" height="28" rx="1.5"/>
    <ellipse class="mmc-dash-subject" cx="51" cy="47" rx="6" ry="8"/>
    <g class="mmc-dash-cube">
      <path d="M112 25l17 9.5v19L112 63l-17-9.5v-19z"/>
      <path d="M112 44.5L95 34.5M112 44.5l17-10M112 44.5V63"/>
    </g>`),

  /** A walk, as the forge renders one: four frames in one grid on one
   *  baseline.
   *
   *  The forge renders a set of frames as one sheet so they keep one scale and
   *  one ground, and that sheet is the most characteristic thing it makes.
   *  The cells run from the pose stage's mannequin into the sprite it
   *  becomes, so the conversion is read left to right. Under the pointer an
   *  amber frame steps through the cells at a frame a beat, which is the
   *  sheet played as the animation it is. */
  forge: () => {
    const cell = 34, left = 12, top = 14, base = 76, px = 3.6;
    const cells = WALK.map((frame, i) => {
      const x = left + i * cell;
      const box = `<rect class="mmc-dash-cell" x="${x}" y="${top}" width="${cell}" height="${base - top}"/>`;
      if (!Array.isArray(frame)) {
        const [hx, hy, hr] = frame.head;
        return `${box}<g class="mmc-dash-soft" transform="translate(${x + cell / 2} ${base - 52})">${limbs(frame.limbs)}`
          + `<circle cx="${hx}" cy="${hy}" r="${hr}"/></g>`;
      }
      const x0 = x + (cell - frame[0].length * px) / 2, y0 = base - frame.length * px;
      return box + frame.flatMap((row, y) => [...row].map((on, c) => on === "." ? ""
        : `<rect class="${on === "#" ? "mmc-dash-px" : "mmc-dash-px-far"}" x="${x0 + c * px}" y="${y0 + y * px}" width="${px}" height="${px}"/>`)).join("");
    }).join("");
    return drawn("forge", `
      <line class="mmc-dash-ground" x1="${left - 4}" y1="${base}" x2="${left + cell * 4 + 4}" y2="${base}"/>
      ${cells}
      <rect class="mmc-dash-play" x="${left}" y="${top}" width="${cell}" height="${base - top}"/>`);
  },
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

