// The blockout bench: a scene staged out of boxes, and a camera walked through it.
//
// The other two benches start from a file. This one starts from nothing at all —
// the composition you can see in your head and cannot photograph: where the
// subject stands, what the room around them is, and how the camera crosses it.
// You block the set out of grey boxes, frame the shot through the one camera
// there is, mark the frames the move passes through, and the bench writes the
// two things a render already understands: a guide file in the input folder,
// and the camera move written in the model's own words.
//
// **The room is the tracing bench's room**, deliberately — the same bar, the
// same rail of stops, the same light box, the same foot that runs the job, the
// same doors the result leaves through. What differs is argued below, departure
// by departure.
//
// **There is no server preview.** The other benches answer a moving dial with a
// round trip because their answer needs the file or the model. This bench's
// answer needs neither: a scene is a few dozen boxes and a projection, which is
// arithmetic, and the pack already has a precedent for browser-side arithmetic
// in the contact sheet — no queue, no weights. The renderer below is a software
// rasterizer, a few hundred lines, no WebGL context to lose and nothing to
// vendor. It draws the viewport live while the set is worked, and the run draws
// the same frames again at full size — one renderer, so what is on the glass is
// exactly what gets written.
//
// **There are two cameras, and one of them is furniture.** The bench opened
// with one — the viewport *was* the lens — on the argument that reconciling two
// is what beginners never stop being confused by. That argument was half right
// and wholly impractical: with one camera you cannot look at the set you are
// building without destroying the shot you framed, so every piece you place
// costs you the framing you had. So the shot camera is now an object in the
// set — drawn where it stands, as a frustum in the marks' blue, with its path
// as a line on the floor and every mark a diamond in space. You fly around it
// in free look; you step inside it with **Through the lens**, where the glass
// is the lens again and every gesture is a word the model was trained on
// (drag pans and tilts, shift-drag trucks and pedestals, the wheel pushes in
// and pulls out). Free look never touches the shot, never stales a written
// result, and never changes a word of the sentence — which is the whole of what
// the split buys.
//
// **The path is marks, not curves.** No keyframe editor and no graph view: you
// frame the shot, you press Mark, you frame the next one, the way a camera
// department works a move out on a set. Each mark is the whole camera —
// position, pan, tilt, lens — and the clip eases through them in order over a
// duration set in seconds.
//
// **The glass shows one thing at a time.** It opened with a seam down the
// middle, half stage and half pass, which spent the working surface on a
// comparison nobody needed twice and stole every drag that landed near it. Now
// it is a switch: **Stage** is the set as you handle it — clay, the grid, the
// gizmo, the camera, the names — and **Depth** (or whichever pass is selected)
// is the frame exactly as the file will hold it, no staging aids at all.
//
// **A piece can be told who or what it is, and the sentence is where that
// pays.** No family here reads identity out of pixels — a depth map is
// identity-free by construction, and even VACE-style masked injection binds a
// reference to its region through the prompt. The one channel that can say
// "who is where" is prose, and the pack already owns the machinery that makes
// a name mean something: the cast. So a block can *play* a cast member, or be
// *called* a word ("table", "doorway"), and the bench writes the staging for
// you — who stands where in frame, computed from the projection it is already
// doing — with `@anna` left as a handle for `compile._substitute` to turn into
// `<Subject N>` the way it does in any other prose. The hue on the stage side
// is the member's own chip hue; like every staging aid it never reaches the
// written file.
//
// **The output is a file in the input folder, and a sentence.** The passes
// wear the tracing bench's own names — Depth, Blocks, Lines — because a user
// who has traced footage already knows what each word buys, and As staged is
// this bench's As shot: no tracing at all, the clay render itself, for the
// families that read plain footage as an init or a reference. The doors are the
// tracing bench's doors, fed by the same targets the shell builds. The sentence
// is the second output and the cheapest: Copy puts it on the clipboard to be
// pasted into the prompt as prose, editable like any other prose.

import { el, icon, mark, spinner, mountOverlay, keepScroll } from "./dom.js";
import { upload, blockoutFrames, blockoutWrite } from "./api.js";
import { openChoicePopover, openAspectPopover, aspectGlyph, PILL_GLYPH } from "./pills.js";
import { rulesFor, resolveCanvas } from "./canvas.js";
import { tagIndex } from "./state.js";
import { t } from "./i18n.js";

/** Where a written blockout lands. The server owns it (`blockout.SUBFOLDER`);
 *  this is the display copy for the line at the foot of the rail. */
const WRITES = "continuity/blockout/";

/** The clip's rate. Fixed rather than dialled: a guide is read frame-for-frame
 *  against the shot, and 24 is what the families sample at. */
const FPS = 24;

/** How many frames ride in one upload batch on the run. */
const BATCH = 24;

// ---- what a blockout can be written as ---------------------------------------
//
// One tuple, the way the server benches keep theirs — except this catalogue
// needs no server: every pass is drawn from the geometry, so nothing about the
// machine can make one unready. `opId` names the tracing bench's operator each
// pass corresponds to, because the far side of a door reads it: the weights
// that follow a guide natively were post-trained on the *tracings*, and a
// blockout depth map should be read as exactly what it is.

const PASSES = [
  {
    id: "as_staged", opId: "as_shot", label: "As staged",
    note: "No tracing — the clay render itself, as footage. Most families read a "
        + "plain clip or picture as a reference or an init, and a blockout is "
        + "footage of a scene that happens to be made of boxes.",
  },
  {
    id: "depth", opId: "depth", label: "Depth",
    note: "Near is bright, far is dark — the map Depth Anything draws from "
        + "footage, drawn here from the geometry itself. No model, and no "
        + "guessing: the bench knows exactly how far everything is.",
  },
  {
    id: "blocks", opId: "blocks", label: "Blocks",
    note: "Each piece one flat field of colour, the way the Blocks tracing "
        + "flattens footage. The loosest guide there is: masses and placement, "
        + "nothing about surface.",
  },
  {
    id: "lines", opId: "lines", label: "Lines",
    note: "The set's edges and nothing else, white on black, the way most line "
        + "models want them.",
  },
];
const PASS_BY_ID = Object.fromEntries(PASSES.map((pass) => [pass.id, pass]));

// ---- what shape a guide is written at ----------------------------------------
//
// This bench shipped with three shapes of its own — 16:9, 9:16, 1:1 — as a row
// of three buttons, which was three of the ten ratios the families actually
// offer and a fourth control that looked like nothing else in the pack. The
// ratio is not this bench's question: it is the family's, the manifest declares
// the answer, and the pack has one popover that asks it. So the rail carries
// the same aspect pill the strip does, over the same grid, off the same
// manifest — and the size is `resolveCanvas`'s, the arithmetic that decides
// every other canvas here. A guide is now written at exactly the canvas the
// render that reads it will use, which the three fixed sizes could not promise.

/** The widest the preview raster is ever allowed to get. The rasterizer is a
 *  per-pixel JS loop run twice a frame, so the ceiling is a frame budget, not a
 *  memory one: past about a megapixel a drag stops keeping up on a laptop. */
const MOST_PREVIEW = 1100;

// ---- the set -----------------------------------------------------------------
//
// Three shapes, and all of them are boxes: a block, a wall (wide and thin), a
// post (tall and thin). A figure used to be a fourth — a little box mannequin —
// and it went, because a guide does not need one: a block the height of a
// person reads as a person in a depth map, and the pack's Pose tracing is the
// tool for actual bodies. What matters here is masses and the move.
//
// A piece carries a floor position (`x`, `z`), a height off the floor (`y`,
// which is the *bottom* of the box, so a piece at 0 sits on the ground and the
// number reads as "how far up"), three extents, and three rotations. It can
// also carry an identity: `plays` is a cast member's handle and `word` is what
// to call it in prose. Neither changes a pixel of any pass — they exist for the
// staging sentence, and for the hue the stage side wears.

const KINDS = {
  block: { label: "Block", w: 1.2, h: 0.9, d: 0.8 },
  wall: { label: "Wall", w: 3.2, h: 2.6, d: 0.14 },
  post: { label: "Post", w: 0.16, h: 2.4, d: 0.16 },
};

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

/** How far a piece may stand from the origin, and how big it may get. Both are
 *  generous against any set worth blocking out and tight against a stray drag
 *  putting a wall past the fog where it cannot be found again. */
const FAR = 40;
const BIG = 20;

const DEG = 180 / Math.PI;

/** A piece, filled in. Everything optional so a preset can say only what it
 *  cares about, and everything clamped so a restored sidecar cannot smuggle a
 *  NaN into the rasterizer. */
function makePiece(id, kind, over = {}) {
  const spec = KINDS[kind] ?? KINDS.block;
  const number = (value, fallback, low, high) =>
    clamp(Number.isFinite(Number(value)) ? Number(value) : fallback, low, high);
  return {
    id, kind,
    x: number(over.x, 0, -FAR, FAR),
    y: number(over.y, 0, 0, BIG),
    z: number(over.z, 0, -FAR, FAR),
    w: number(over.w, spec.w, 0.05, BIG),
    h: number(over.h, spec.h, 0.05, BIG),
    d: number(over.d, spec.d, 0.05, BIG),
    // `rot` is the field this bench shipped with: one turn on Y. It is read as
    // `ry` so a scene written before there were three rotations opens square.
    rx: number(over.rx, 0, -Math.PI, Math.PI),
    ry: number(over.ry ?? over.rot, 0, -Math.PI, Math.PI),
    rz: number(over.rz, 0, -Math.PI, Math.PI),
    plays: String(over.plays ?? "").slice(0, 32),
    word: String(over.word ?? "").slice(0, 48),
  };
}

// ---- what a bench can open on --------------------------------------------------
//
// The bench used to open on six boxes, on the argument that an empty viewport
// is a black rectangle with nothing to operate the camera against. What it
// actually was, was six boxes to delete before the set you wanted could be
// staged. So the floor is bare, and the invitation is these: five arrangements
// out of the vocabulary a shot list already uses, each carrying its own camera
// and its own move, so pressing one gives you something that plays rather than
// something to assemble. Every one of them is a starting point to be pushed
// around — that is the whole of what a blockout is.

const PRESETS = [
  {
    id: "bare", label: "Bare floor",
    note: "Nothing but the grid. The camera at eye height, looking down the room.",
    make: () => ({ objects: [], marks: [] }),
  },
  {
    id: "two", label: "Two-shot",
    note: "Two figures facing each other against a back wall, and a slow push in.",
    make: () => ({
      objects: [
        { kind: "block", x: -0.85, z: 5.0, w: 0.52, h: 1.74, d: 0.42, ry: 0.5 },
        { kind: "block", x: 0.85, z: 5.3, w: 0.52, h: 1.8, d: 0.42, ry: -0.5 },
        { kind: "wall", x: 0.1, z: 7.6, w: 6.2, h: 2.9 },
      ],
      marks: [
        { x: 0, y: 1.6, z: 1.1, yaw: 0, pitch: -0.01, mm: 50 },
        { x: 0, y: 1.58, z: 2.7, yaw: 0, pitch: -0.01, mm: 50 },
      ],
    }),
  },
  {
    id: "corridor", label: "Corridor",
    note: "Two long walls, a rhythm of posts, and the camera travelling through.",
    make: () => ({
      objects: [
        { kind: "wall", x: -1.7, z: 6, w: 14, h: 2.9, d: 0.16, ry: Math.PI / 2 },
        { kind: "wall", x: 1.7, z: 6, w: 14, h: 2.9, d: 0.16, ry: Math.PI / 2 },
        { kind: "post", x: -1.45, z: 3.2, h: 2.6 },
        { kind: "post", x: 1.45, z: 5.6, h: 2.6 },
        { kind: "post", x: -1.45, z: 8, h: 2.6 },
        { kind: "block", x: 0.15, z: 10.4, w: 0.5, h: 1.76, d: 0.4, word: "figure" },
      ],
      marks: [
        { x: 0, y: 1.6, z: -0.6, yaw: 0, pitch: 0, mm: 28 },
        { x: 0, y: 1.6, z: 5.4, yaw: 0, pitch: 0, mm: 28 },
      ],
    }),
  },
  {
    id: "interview", label: "Interview",
    note: "One subject behind a table, a backdrop, and a slow truck across.",
    make: () => ({
      objects: [
        { kind: "block", x: 0, z: 3.6, w: 0.52, h: 1.78, d: 0.42 },
        { kind: "block", x: 0, z: 2.75, w: 1.6, h: 0.74, d: 0.75, word: "table" },
        { kind: "wall", x: 0, z: 5.1, w: 5, h: 2.7 },
      ],
      marks: [
        { x: 1.15, y: 1.42, z: 0.7, yaw: -0.34, pitch: 0.02, mm: 58 },
        { x: 0.05, y: 1.42, z: 0.7, yaw: -0.02, pitch: 0.02, mm: 58 },
      ],
    }),
  },
  {
    id: "street", label: "Street corner",
    note: "Two building masses, a lamp, and the camera arcing round the corner.",
    make: () => ({
      objects: [
        { kind: "wall", x: -5.2, z: 9.5, w: 11, h: 7, d: 0.4, ry: 0.16, word: "building" },
        { kind: "wall", x: 5.6, z: 12, w: 12, h: 8.5, d: 0.4, ry: -0.22, word: "building" },
        { kind: "post", x: 1.7, z: 4.8, w: 0.18, h: 3.6, d: 0.18, word: "lamp post" },
        { kind: "block", x: -1.3, z: 5.4, w: 0.5, h: 1.75, d: 0.4 },
        { kind: "block", x: 2.9, z: 7.2, w: 1.9, h: 1.35, d: 4.1, ry: 0.1, word: "parked car" },
      ],
      marks: [
        { x: -2.6, y: 1.55, z: 0.4, yaw: 0.36, pitch: 0.03, mm: 32 },
        { x: 1.9, y: 1.55, z: 1.2, yaw: -0.28, pitch: 0.03, mm: 32 },
      ],
    }),
  },
];

/** The eight identity hues, as drawn ink. Read off the stylesheet so the tint
 *  on the glass is exactly the hue the member's chip wears; the literals are
 *  `--mmc-tag-0..7`'s own values, for a document that has no tokens loaded
 *  (the test shim). */
const TAG_FALLBACK = ["#5cb8f0", "#63c98e", "#9d95f5", "#f07da0",
                      "#45c4c0", "#f0906b", "#d57de8", "#a8c858"];
const tagInk = [];
function tagRGB(index) {
  if (!tagInk[index]) {
    let hex = "";
    try {
      hex = getComputedStyle(document.documentElement)
        .getPropertyValue(`--mmc-tag-${index}`).trim();
    } catch { /* no document: the fallback is the same eight values */ }
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) hex = TAG_FALLBACK[index % 8];
    tagInk[index] = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16));
  }
  return tagInk[index];
}

// ---- a piece's own frame -------------------------------------------------------
//
// Three rotations, composed Y·X·Z: yaw first because turning a piece on the
// floor is what nine drags out of ten are, and the other two read as tilts of
// an already-turned box, which is how a hand expects them to behave.

const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross3 = (a, b) => [a[1] * b[2] - a[2] * b[1],
                          a[2] * b[0] - a[0] * b[2],
                          a[0] * b[1] - a[1] * b[0]];
const norm3 = (v) => {
  const len = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / len, v[1] / len, v[2] / len];
};

/** The piece's rotation as a row-major 3×3. */
function basisOf(piece) {
  const cx = Math.cos(piece.rx ?? 0), sx = Math.sin(piece.rx ?? 0);
  const ry = piece.ry ?? piece.rot ?? 0;
  const cy = Math.cos(ry), sy = Math.sin(ry);
  const cz = Math.cos(piece.rz ?? 0), sz = Math.sin(piece.rz ?? 0);
  return [
    cy * cz + sy * sx * sz, -cy * sz + sy * sx * cz, sy * cx,
    cx * sz, cx * cz, -sx,
    -sy * cz + cy * sx * sz, sy * sz + cy * sx * cz, cy * cx,
  ];
}

const applyM = (m, v) => [
  m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
  m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
  m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
];

/** The centre of a piece's box, in world. `y` is the bottom, so the centre is
 *  half a height above it — which is also what every placement word is measured
 *  from, and what the gizmo hangs off. */
const centreOf = (piece) => [piece.x, (piece.y ?? 0) + piece.h / 2, piece.z];

/** The eight corners of a piece's box, in world. */
function cornersOf(piece) {
  const m = basisOf(piece);
  const [ox, oy, oz] = centreOf(piece);
  const hx = piece.w / 2, hy = piece.h / 2, hz = piece.d / 2;
  const out = [];
  for (const ux of [-1, 1]) for (const uy of [-1, 1]) for (const uz of [-1, 1]) {
    const v = applyM(m, [ux * hx, uy * hy, uz * hz]);
    out.push([ox + v[0], oy + v[1], oz + v[2]]);
  }
  return out;
}

// ---- the renderer ------------------------------------------------------------
//
// A z-buffered triangle rasterizer over ImageData. It is deliberately the whole
// of the graphics stack: boxes, one directional light, a ground plane carrying
// a perspective-correct grid, and four shaders — clay, depth, flat colour,
// edges. Nothing here knows about the bench; it takes a scene and a camera and
// fills a buffer, which is what lets the run reuse it at full size.

const NEARZ = 0.12;
const DNEAR = 1.0;
const DFAR = 26;
const LIGHT = norm3([0.45, 0.8, -0.35]);

// Unit-cube faces with outward normals; each quad becomes two triangles.
const FACES = [
  { n: [0, 0, -1], q: [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1]] },
  { n: [0, 0, 1], q: [[1, -1, 1], [-1, -1, 1], [-1, 1, 1], [1, 1, 1]] },
  { n: [-1, 0, 0], q: [[-1, -1, 1], [-1, -1, -1], [-1, 1, -1], [-1, 1, 1]] },
  { n: [1, 0, 0], q: [[1, -1, -1], [1, -1, 1], [1, 1, 1], [1, 1, -1]] },
  { n: [0, 1, 0], q: [[-1, 1, -1], [1, 1, -1], [1, 1, 1], [-1, 1, 1]] },
  { n: [0, -1, 0], q: [[-1, -1, 1], [1, -1, 1], [1, -1, -1], [-1, -1, -1]] },
];

/** The Blocks pass's palette. Muted segmentation tones, assigned by piece id so
 *  a piece keeps its colour while it is moved. */
const BLOCK_COLORS = [
  [201, 79, 79], [79, 137, 201], [201, 163, 79], [111, 201, 79],
  [154, 95, 201], [79, 201, 182], [201, 79, 152], [142, 201, 79],
];
const GROUND_ID = 254;
const SKY_ID = 255;

/** 35mm-equivalent focal length -> vertical field of view (24mm sensor height). */
const vfovOf = (mm) => 2 * Math.atan(12 / mm);

const forwardOf = (cam) => {
  const cp = Math.cos(cam.pitch);
  return [Math.sin(cam.yaw) * cp, Math.sin(cam.pitch), Math.cos(cam.yaw) * cp];
};
const flatForwardOf = (cam) => [Math.sin(cam.yaw), 0, Math.cos(cam.yaw)];
const rightOf = (cam) => [Math.cos(cam.yaw), 0, -Math.sin(cam.yaw)];
const upOf = (cam) => cross3(forwardOf(cam), rightOf(cam));

class Raster {
  constructor(width, height) {
    this.w = width;
    this.h = height;
    const count = width * height;
    this.z = new Float32Array(count);       // 1/z; bigger is nearer
    this.id = new Uint8Array(count);        // which piece owns the pixel
    this.lit = new Uint8Array(count);       // lambert, per flat face
    this.wx = new Float32Array(count);      // world x/z, ground pixels only —
    this.wz = new Float32Array(count);      // what the grid is drawn from
    this.image = null;                      // made against a 2d context on demand
  }

  /** World triangles for one piece. A piece is a box on its own three turns. */
  static tris(out, piece) {
    const { id } = piece;
    const m = basisOf(piece);
    const [ox, oy, oz] = centreOf(piece);
    const hx = piece.w / 2, hy = piece.h / 2, hz = piece.d / 2;
    for (const face of FACES) {
      const wn = applyM(m, face.n);
      const lam = Math.max(0, dot3(wn, LIGHT));
      const lit = clamp(0.28 + 0.72 * lam, 0, 1);
      const p = face.q.map(([ux, uy, uz]) => {
        const v = applyM(m, [ux * hx, uy * hy, uz * hz]);
        return [ox + v[0], oy + v[1], oz + v[2]];
      });
      out.push({ id, lit, v: [p[0], p[1], p[2]] }, { id, lit, v: [p[0], p[2], p[3]] });
    }
  }

  /** Sutherland–Hodgman against the near plane, verts carrying `[x,y,z,wx,wz]`. */
  static clipNear(tri) {
    if (tri.every((v) => v[2] >= NEARZ)) return [tri];
    if (tri.every((v) => v[2] < NEARZ)) return [];
    const poly = [];
    for (let i = 0; i < 3; i++) {
      const a = tri[i], b = tri[(i + 1) % 3];
      if (a[2] >= NEARZ) poly.push(a);
      if ((a[2] >= NEARZ) !== (b[2] >= NEARZ)) {
        const s = (NEARZ - a[2]) / (b[2] - a[2]);
        poly.push([a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, NEARZ,
                   a[3] + (b[3] - a[3]) * s, a[4] + (b[4] - a[4]) * s]);
      }
    }
    const out = [];
    for (let i = 1; i + 1 < poly.length; i++) out.push([poly[0], poly[i], poly[i + 1]]);
    return out;
  }

  /** Fill the id/z/light buffers for `objects` seen from `cam`. */
  raster(objects, cam) {
    const { w, h } = this;
    this.z.fill(0);
    this.id.fill(SKY_ID);
    this.lit.fill(0);
    const sy = Math.sin(cam.yaw), cy = Math.cos(cam.yaw);
    const sp = Math.sin(cam.pitch), cp = Math.cos(cam.pitch);
    const fl = (h / 2) / Math.tan(vfovOf(cam.mm) / 2);
    const cxp = w / 2, cyp = h / 2;

    const tris = [];
    // The ground, big enough that its edge is past the fog. The winding is the
    // one that survives the screen-space backface test from above — the same
    // test the boxes pass, whose faces wind counter-clockwise seen from
    // outside and come out clockwise on screen once y flips.
    const G = 90;
    tris.push(
      { id: GROUND_ID, lit: 1, ground: true, v: [[-G, 0, -G], [G, 0, -G], [G, 0, G]] },
      { id: GROUND_ID, lit: 1, ground: true, v: [[-G, 0, -G], [G, 0, G], [-G, 0, G]] });
    for (const piece of objects) Raster.tris(tris, piece);

    for (const tri of tris) {
      const view = tri.v.map((p) => {
        const x = p[0] - cam.x, y = p[1] - cam.y, z = p[2] - cam.z;
        const x1 = cy * x - sy * z, z1 = sy * x + cy * z;
        return [x1, cp * y - sp * z1, sp * y + cp * z1, p[0], p[2]];
      });
      for (const part of Raster.clipNear(view)) {
        const pts = part.map((v) => {
          const iz = 1 / v[2];
          return { x: cxp + fl * v[0] * iz, y: cyp - fl * v[1] * iz,
                   iz, wxz: v[3] * iz, wzz: v[4] * iz };
        });
        const [a, b, d] = pts;
        const area = (b.x - a.x) * (d.y - a.y) - (b.y - a.y) * (d.x - a.x);
        // Backface: front faces come out clockwise on screen once y flips.
        if (area >= -0.001) continue;
        const inv = 1 / area;
        const minX = Math.max(0, Math.floor(Math.min(a.x, b.x, d.x)));
        const maxX = Math.min(w - 1, Math.ceil(Math.max(a.x, b.x, d.x)));
        const minY = Math.max(0, Math.floor(Math.min(a.y, b.y, d.y)));
        const maxY = Math.min(h - 1, Math.ceil(Math.max(a.y, b.y, d.y)));
        if (minX > maxX || minY > maxY) continue;
        const lit = Math.round(tri.lit * 255);
        const isGround = Boolean(tri.ground);
        for (let y = minY; y <= maxY; y++) {
          const py = y + 0.5;
          const row = y * w;
          for (let x = minX; x <= maxX; x++) {
            const px = x + 0.5;
            const w0 = (b.x - a.x) * (py - a.y) - (b.y - a.y) * (px - a.x);
            const w1 = (d.x - b.x) * (py - b.y) - (d.y - b.y) * (px - b.x);
            const w2 = (a.x - d.x) * (py - d.y) - (a.y - d.y) * (px - d.x);
            if (w0 > 0 || w1 > 0 || w2 > 0) continue;
            const l0 = w1 * inv, l1 = w2 * inv, l2 = w0 * inv;
            const iz = l0 * a.iz + l1 * b.iz + l2 * d.iz;
            const at = row + x;
            if (iz <= this.z[at]) continue;
            this.z[at] = iz;
            this.id[at] = tri.id;
            this.lit[at] = lit;
            if (isGround) {
              // Perspective-correct: the attribute rode in divided by view z.
              this.wx[at] = (l0 * a.wxz + l1 * b.wxz + l2 * d.wxz) / iz;
              this.wz[at] = (l0 * a.wzz + l1 * b.wzz + l2 * d.wzz) / iz;
            }
          }
        }
      }
    }
  }

  /**
   * Shade the rastered buffers into `context`'s canvas.
   *
   * `mode` is a pass id, or `"stage"` for the working view: the same clay as
   * `as_staged`, plus the aids — the floor grid, the selection ring, the cast
   * tints. The aids exist only in `"stage"`, which is why the run can call this
   * with a pass id and be certain the file carries the guide and only the guide.
   */
  shade(context, mode, { selected = 0, tints = null } = {}) {
    const { w, h } = this;
    if (!this.image || this.image.width !== w || this.image.height !== h) {
      this.image = context.createImageData(w, h);
    }
    const data = this.image.data;
    const stage = mode === "stage";
    const clay = stage || mode === "as_staged";
    for (let y = 0; y < h; y++) {
      const row = y * w;
      for (let x = 0; x < w; x++) {
        const at = row + x;
        const id = this.id[at];
        let r, g, b;
        if (clay) {
          if (id === SKY_ID) {
            const fade = 1 - y / h;
            r = 38 + 10 * fade; g = 40 + 10 * fade; b = 44 + 12 * fade;
          } else if (id === GROUND_ID) {
            const z = 1 / this.z[at];
            let base = 70, tint = null;
            if (stage) {
              // Three grids over each other, in the order a plan is read: the
              // metre, the five-metre a step is counted in, and the two world
              // axes — which wear the gizmo's own colours, because "which way
              // is X" is the one question a floor plan has to answer and the
              // handles have already answered it once.
              const wx = this.wx[at], wz = this.wz[at];
              const gx = Math.abs(wx - Math.round(wx));
              const gz = Math.abs(wz - Math.round(wz));
              const near = 0.009 + z * 0.0022;
              const onX = Math.abs(wx) < near * 1.6;
              const onZ = Math.abs(wz) < near * 1.6;
              if (onX) tint = [96, 143, 226];        // the Z axis runs along x=0
              else if (onZ) tint = [224, 90, 82];    // and the X axis along z=0
              else if (gx < near || gz < near) {
                const five = Math.abs(wx / 5 - Math.round(wx / 5)) < near / 5
                          || Math.abs(wz / 5 - Math.round(wz / 5)) < near / 5;
                base += clamp((five ? 52 : 30) - z * 1.1, 0, 52);
              }
            }
            const fog = clamp(1 - z / 45, 0.35, 1);
            if (tint) {
              const lift = clamp(1 - z / 34, 0.3, 1);
              r = (base + (tint[0] - base) * 0.55 * lift) * fog;
              g = (base + (tint[1] - base) * 0.55 * lift) * fog;
              b = (base + (tint[2] - base) * 0.55 * lift) * fog;
            } else {
              r = base * fog; g = (base + 1) * fog; b = (base + 3) * fog;
            }
          } else {
            const l = this.lit[at] / 255;
            const haze = clamp(1 - (1 / this.z[at]) / 60, 0.58, 1);
            r = (70 + 112 * l) * haze; g = (68 + 108 * l) * haze; b = (64 + 102 * l) * haze;
            // The member's chip hue, worn as a wash on the clay — stage only,
            // the way every staging aid is. The lambert stays underneath so the
            // piece keeps reading as a solid.
            const tint = stage && tints ? tints[id] : null;
            if (tint) {
              r = r * 0.68 + tint[0] * 0.32;
              g = g * 0.68 + tint[1] * 0.32;
              b = b * 0.68 + tint[2] * 0.32;
            }
            if (stage && id === selected && this.edgeOf(at, x, y)) {
              r = 107; g = 163; b = 214;   // the trim bar's blue: held, not run
            }
          }
        } else if (mode === "depth") {
          if (id === SKY_ID) { r = g = b = 4; } else {
            const z = 1 / this.z[at];
            const v = Math.pow(clamp(1 - (z - DNEAR) / (DFAR - DNEAR), 0, 1), 1.3);
            r = g = b = Math.round(8 + v * 247);
          }
        } else if (mode === "blocks") {
          const tone = id === GROUND_ID ? [42, 46, 52]
            : id === SKY_ID ? [14, 15, 17]
            : BLOCK_COLORS[id % BLOCK_COLORS.length];
          r = tone[0]; g = tone[1]; b = tone[2];
        } else {   // lines
          const v = this.lineAt(at, x, y, id) ? 245 : 6;
          r = v; g = v; b = v;
        }
        const o = at * 4;
        data[o] = r; data[o + 1] = g; data[o + 2] = b; data[o + 3] = 255;
      }
    }
    context.putImageData(this.image, 0, 0);
  }

  /** Whether this pixel is within the selection ring's width of a different
   *  piece. The width is the buffer's own — one pixel was a ring at the 704
   *  this bench shipped with and a hairline at a thousand. */
  edgeOf(at, x, y) {
    const id = this.id[at];
    const wide = this.w > 820 ? 2 : 1;
    for (let step = 1; step <= wide; step++) {
      if ((x + step < this.w && this.id[at + step] !== id)
        || (x >= step && this.id[at - step] !== id)
        || (y + step < this.h && this.id[at + this.w * step] !== id)
        || (y >= step && this.id[at - this.w * step] !== id)) return true;
    }
    return false;
  }

  /**
   * Whether this pixel is a line in the Lines pass.
   *
   * A change of piece is always an edge — that is what makes the horizon one
   * line rather than a band. Within a piece, a depth step marks the internal
   * silhouettes a box has against itself; the ground is exempt because at
   * grazing angles every ground pixel is a depth step from the next.
   */
  lineAt(at, x, y, id) {
    const zHere = this.z[at] > 0 ? 1 / this.z[at] : 1e9;
    for (const step of [1, this.w]) {
      const next = at + step;
      if ((step === 1 && x + 1 >= this.w) || (step !== 1 && y + 1 >= this.h)) continue;
      if (this.id[next] !== id) return true;
      if (id !== SKY_ID && id !== GROUND_ID) {
        const zNext = this.z[next] > 0 ? 1 / this.z[next] : 1e9;
        if (Math.abs(zNext - zHere) > 0.3 + zHere * 0.02) return true;
      }
    }
    return false;
  }

  /** World-space ray through a buffer pixel — what object drags follow. */
  ray(px, py, cam) {
    const fl = (this.h / 2) / Math.tan(vfovOf(cam.mm) / 2);
    const vx = (px - this.w / 2) / fl, vy = (this.h / 2 - py) / fl;
    const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    const y1 = cp * vy + sp, z1 = -sp * vy + cp;
    const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
    return [cy * vx + sy * z1, y1, -sy * vx + cy * z1];
  }
}

// ---- where things stand, in words ----------------------------------------------
//
// The models' one channel for "who is where" is prose (even VACE's masked
// injection binds a reference to its region through the prompt), and the bench
// is the one tool holding both halves of that sentence: it knows the set and it
// knows the lens. So placement is computed, not guessed — the same projection
// the rasterizer applies, run over each named piece at the first and last mark.

/** One world point through a camera, at a buffer size -> screen x/y and view
 *  depth, or null behind the near plane. `Raster.raster`'s arithmetic, applied
 *  to a single point. */
function project(cam, point, width, height) {
  const sy = Math.sin(cam.yaw), cy = Math.cos(cam.yaw);
  const sp = Math.sin(cam.pitch), cp = Math.cos(cam.pitch);
  const x = point[0] - cam.x, y = point[1] - cam.y, z = point[2] - cam.z;
  const x1 = cy * x - sy * z, z1 = sy * x + cy * z;
  const y2 = cp * y - sp * z1, z2 = sp * y + cp * z1;
  if (z2 < NEARZ) return null;
  const fl = (height / 2) / Math.tan(vfovOf(cam.mm) / 2);
  return { x: width / 2 + (fl * x1) / z2, y: height / 2 - (fl * y2) / z2, z: z2 };
}

/** Where a piece sits in this frame, as words — or null when it is out of shot.
 *  Thirds across, three depth bands away: the vocabulary a shot list uses, and
 *  coarse on purpose — "at frame left in the midground" survives the model's
 *  own judgement where pixel coordinates would only pretend precision. */
function placeOf(piece, cam, width, height) {
  const at = project(cam, centreOf(piece), width, height);
  if (!at || at.x < 0 || at.x > width || at.y < -0.2 * height || at.y > 1.2 * height) return null;
  const third = at.x < width * 0.36 ? t("at frame left")
    : at.x > width * 0.64 ? t("at frame right") : t("at centre");
  const band = at.z < 3.2 ? t("in the foreground")
    : at.z < 9 ? t("in the midground") : t("in the distance");
  return { words: `${third} ${band}`, depth: at.z };
}

/** A word with its article, unless it arrived wearing one. */
function articled(word) {
  const said = String(word).trim();
  if (/^(a|an|the|some|its|his|her|their|two|three|four)\b/i.test(said)) return said;
  return `${/^[aeiou]/i.test(said) ? t("an") : t("a")} ${said}`;
}

/** The cast member the move ends on, or null: the piece playing somebody whose
 *  centre the last mark's frame holds nearest its own. What "pushes in toward
 *  @anna" is decided by, and decided from geometry rather than a checkbox. */
function moveTarget(objects, marks, cam, width, height) {
  const last = marks.length ? marks[marks.length - 1] : cam;
  let best = null;
  for (const piece of objects) {
    if (!piece.plays) continue;
    const at = project(last, centreOf(piece), width, height);
    if (!at) continue;
    const off = Math.hypot(at.x - width / 2, at.y - height / 2) / width;
    if (off < 0.22 && (!best || off < best.off)) best = { handle: piece.plays, off };
  }
  return best ? best.handle : null;
}

/**
 * The staging and the move, as one piece of prose.
 *
 * Who stands where at the first mark, in shot-list vocabulary; a cast member
 * out of shot at the start but in it by the end is said to arrive; then the
 * move sentence, aimed at whoever it lands on. Handles stay handles — `@anna`
 * is exactly what the prompt's own substitution reads — so pasting this into a
 * prompt binds the words to the cast's references with no new machinery.
 */
export function stagingSentence(objects, marks, duration, cam, size = { w: 16, h: 9 }) {
  const first = marks.length ? marks[0] : cam;
  const clauses = [];
  const entering = [];
  const placed = [];
  for (const piece of objects) {
    if (!piece.plays && !piece.word) continue;
    const here = placeOf(piece, first, size.w, size.h);
    if (here) placed.push({ piece, here });
    else if (piece.plays && marks.length > 1
             && placeOf(piece, marks[marks.length - 1], size.w, size.h)) {
      entering.push(piece);
    }
  }
  // The cast before the props, and nearer before farther — the order a shot
  // list reads in, and the order the eye does.
  placed.sort((p, q) => ((q.piece.plays ? 1 : 0) - (p.piece.plays ? 1 : 0))
    || (p.here.depth - q.here.depth));
  for (const { piece, here } of placed) {
    clauses.push(piece.plays
      ? t("@{who} stands {place}", { who: piece.plays, place: here.words })
      : t("{what} {place}", { what: articled(piece.word), place: here.words }));
  }
  for (const piece of entering) {
    clauses.push(t("@{who} comes into frame as the camera moves", { who: piece.plays }));
  }
  const move = moveSentence(marks, duration, moveTarget(objects, marks, cam, size.w, size.h));
  if (!clauses.length) return move;
  const staging = clauses.join("; ") + ".";
  return `${staging.charAt(0).toUpperCase()}${staging.slice(1)} ${move}`;
}

// ---- the move, in words --------------------------------------------------------
//
// H3's prompt spec (`families/h3/prompts/base-en.txt`, §4.3) defines camera
// motion as a fixed vocabulary — motion type, amplitude, speed — and asks for
// it as natural English inside the shot. This derives that sentence from the
// marks: deltas in the first mark's own camera space name the motion, the
// dominant magnitude names the amplitude, magnitude over duration names the
// speed, and medium and normal are omitted the way the spec omits them. The
// same words read fine on every other family; LTX's craft guide wants the same
// moves as prose without labels, which this already is.

export function moveSentence(marks, duration, target = null) {
  if (!marks || marks.length < 2) return t("The camera holds a static shot.");
  const a = marks[0], b = marks[marks.length - 1];
  const right = rightOf(a), ahead = flatForwardOf(a);
  const dx = (b.x - a.x) * right[0] + (b.z - a.z) * right[2];
  const dz = (b.x - a.x) * ahead[0] + (b.z - a.z) * ahead[2];
  const dy = b.y - a.y;
  const dyaw = b.yaw - a.yaw, dpitch = b.pitch - a.pitch, dmm = b.mm - a.mm;
  const moves = [];
  // An arc is sideways travel with the pan fighting it — the camera keeps
  // looking at what it is circling. Named as one move, not two.
  if (Math.abs(dx) > 0.6 && Math.abs(dyaw * DEG) > 8 && Math.sign(dyaw) !== Math.sign(dx)) {
    // Around whom is geometry's answer where there is one: the cast member the
    // last frame holds at its centre. "The subject" is the honest fallback.
    const around = target ? `@${target}` : t("the subject");
    moves.push({ mag: Math.abs(dx) / 1.5,
                 words: dx > 0 ? t("arcs right around {who}", { who: around })
                               : t("arcs left around {who}", { who: around }) });
  } else {
    if (Math.abs(dx) > 0.25) moves.push({ mag: Math.abs(dx) / 1.5, words: dx > 0 ? t("trucks right") : t("trucks left") });
    if (Math.abs(dyaw * DEG) > 5) moves.push({ mag: Math.abs(dyaw * DEG) / 25, words: dyaw > 0 ? t("pans right") : t("pans left") });
  }
  if (Math.abs(dz) > 0.3) {
    moves.push({ mag: Math.abs(dz) / 2,
                 words: dz > 0
                   ? (target ? t("pushes in toward @{who}", { who: target }) : t("pushes in"))
                   : t("pulls out") });
  }
  if (Math.abs(dy) > 0.25) moves.push({ mag: Math.abs(dy), words: dy > 0 ? t("pedestals up") : t("pedestals down") });
  if (Math.abs(dpitch * DEG) > 5) moves.push({ mag: Math.abs(dpitch * DEG) / 25, words: dpitch > 0 ? t("tilts up") : t("tilts down") });
  if (Math.abs(dmm) > 6) moves.push({ mag: Math.abs(dmm) / 30, words: dmm > 0 ? t("zooms in") : t("zooms out") });
  if (!moves.length) return t("The camera holds a static shot.");
  moves.sort((p, q) => q.mag - p.mag);
  // The two strongest, because a prompt should name the move and not inventory
  // it: "pushes in and pedestals up" is a move, five clauses is a flight plan.
  const top = moves.slice(0, 2).map((m) => m.words).join(` ${t("and")} `);
  const mag = moves[0].mag;
  const amp = mag > 1.7 ? t("large") : mag < 0.42 ? t("small") : "";
  const rate = mag / Math.max(0.5, duration);
  const speed = rate > 0.55 ? t("fast") : rate < 0.18 ? t("slow") : "";
  let sentence = t("The camera {moves}", { moves: top });
  if (amp) sentence += " " + t("with {amp} amplitude", { amp });
  if (speed) sentence += " " + t("at {speed} speed", { speed });
  return sentence + ".";
}

// ---- the path -----------------------------------------------------------------

/** Catmull–Rom through the marks' every field. Clamped ends: the first and
 *  last mark are where the clip actually starts and stops. */
function pathCam(marks, at) {
  if (!marks.length) return null;
  if (marks.length === 1) return { ...marks[0] };
  const last = marks.length - 1;
  const f = clamp(at, 0, 1) * last;
  const i = Math.min(last - 1, Math.floor(f));
  const u = f - i, u2 = u * u, u3 = u2 * u;
  const m = (k) => marks[clamp(k, 0, last)];
  const p0 = m(i - 1), p1 = m(i), p2 = m(i + 1), p3 = m(i + 2);
  const out = {};
  for (const key of ["x", "y", "z", "yaw", "pitch", "mm"]) {
    out[key] = 0.5 * ((2 * p1[key]) + (-p0[key] + p2[key]) * u
      + (2 * p0[key] - 5 * p1[key] + 4 * p2[key] - p3[key]) * u2
      + (-p0[key] + 3 * p1[key] - 3 * p2[key] + p3[key]) * u3);
  }
  return out;
}

function formatSeconds(seconds) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return `${minutes}:${rest < 10 ? "0" : ""}${rest.toFixed(1)}`;
}

// ---- the gizmo's ink -----------------------------------------------------------
//
// Three axes, in the three colours every 3D tool has used since the first one:
// X warm, Y (up here) green, Z cool. They are the one place on the glass that
// is not the pack's palette, deliberately — a hand that has touched any other
// 3D application already knows what they mean, and inventing a house colour for
// "the X axis" would be a private joke at the user's expense.

const AXIS_INK = { x: "#e05a52", y: "#79c85a", z: "#4f8fe2" };
const AXES = ["x", "y", "z"];
const UNIT = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };

/** Two unit vectors spanning the plane normal to `axis` — the ring's own frame. */
function planeOf(axis) {
  const away = Math.abs(axis[1]) > 0.9 ? [1, 0, 0] : [0, 1, 0];
  const u = norm3(cross3(axis, away));
  return [u, norm3(cross3(axis, u))];
}

/** Shortest distance from a point to a polyline, in the polyline's own units. */
function nearPolyline(pts, px, py) {
  let best = Infinity;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    if (!a || !b) continue;
    const vx = b[0] - a[0], vy = b[1] - a[1];
    const len2 = vx * vx + vy * vy;
    const s = len2 ? clamp(((px - a[0]) * vx + (py - a[1]) * vy) / len2, 0, 1) : 0;
    best = Math.min(best, Math.hypot(a[0] + vx * s - px, a[1] + vy * s - py));
  }
  return best;
}

/** The bench, or null. One at a time: it is the room. */
let open = null;

/**
 * Open the bench.
 *
 * @param {object} [options]
 * @param {Array}  [options.targets]  where a finished guide can be sent — the
 *   same shape the tracing bench takes: `[{ id, label, does, kinds, take }]`.
 * @param {Function} [options.back]  where the wordmark goes, as ever.
 * @param {object} [options.scene]  a saved set to reopen — the sidecar's
 *   `scene` object, put back on the glass exactly as it was written.
 * @returns {Promise<void>}  resolves when the bench is closed
 */
export function openBlockout(options = {}) {
  open?.close();
  return new Promise((resolve) => {
    open = new Bench(options, resolve);
    open.mount();
  });
}

class Bench {
  constructor(options, resolve) {
    this.targets = options.targets ?? [];
    this.back = options.back ?? null;
    this.resolve = resolve;
    // The piece's cast, as handles — who a block can play. Handed over by the
    // shell the way the targets are, because a bench does not know where a
    // roster lives, and resolved at open: the cast a sentence cites is the
    // cast that was on the shelf when the bench went up.
    this.cast = (options.cast ?? []).filter((handle) => typeof handle === "string" && handle);
    // Whose canvas rules the guide is written to. Handed over like the cast and
    // the targets: a bench does not know which family a piece renders with, and
    // the ratios on offer are that family's declaration. An unknown id falls
    // back to the default the way every other reader's does.
    this.family = options.family ?? null;

    // A bare floor. Everything below is the set's furniture, not the set.
    this.objects = [];
    this.nextId = 1;
    this.marks = [];

    // The camera that gets written. Eye height, looking down the room.
    this.shot = { x: 0, y: 1.6, z: -3.6, yaw: 0, pitch: -0.02, mm: 32 };
    // The camera you fly. Its lens is its own business — a working view wants
    // to be wide — and none of it ever reaches the file. Its position is not
    // stated: `placeOrbit` derives it, because the pivot and the distance are
    // the two facts and a third that could disagree with them is a bug waiting.
    this.view = { x: 0, y: 0, z: 0, yaw: -0.62, pitch: -0.2, mm: 26 };
    this.through = false;
    // What free look turns around, and how far off it sits. A shallow pitch on
    // purpose: tip the view down far enough to see the floor plan and the
    // horizon leaves the frame, which makes the whole set look like a carpet.
    this.pivot = { x: 0, y: 1, z: 1.4 };
    this.orbit = 12;

    this.tool = "move";        // which gizmo the selection wears
    this.snap = 0;             // metres, or 0 for off
    this.showPass = false;     // the glass shows the pass, not the stage
    this.scrub = 0;
    this.duration = 4.0;
    this.aspect = "16:9";
    this.pass = "depth";
    this.selected = 0;
    this.playing = false;
    this.busy = false;
    this.progress = null;      // a sentence for the run button while it works
    this.error = null;
    this.result = null;
    this.sentTo = new Set();
    this.sending = null;

    this.rasters = new Map();  // size key -> Raster, so a drag allocates nothing
    this.draft = false;        // half resolution while something is moving
    this.fields = [];          // the rail's live numbers, kept in step with drags
    this.held = new Set();     // which fly keys are down
    this.placeOrbit();
    if (options.scene) this.restore(options.scene);
  }

  /** A saved set, back on the glass. Anything malformed keeps the default. */
  restore(scene) {
    try {
      if (Array.isArray(scene.objects)) {
        this.objects = scene.objects
          .filter((piece) => KINDS[piece.kind])
          .map((piece, index) => makePiece(index + 1, piece.kind, piece));
        this.nextId = this.objects.length + 1;
      }
      if (Array.isArray(scene.marks)) {
        this.marks = scene.marks.map((markAt) => this.cleanCam(markAt));
      }
      if (scene.shot) Object.assign(this.shot, this.cleanCam(scene.shot));
      else if (this.marks.length) Object.assign(this.shot, this.marks[0]);
      if (scene.view) Object.assign(this.view, this.cleanCam(scene.view));
      if (Number.isFinite(scene.duration)) this.duration = clamp(scene.duration, 1, 10);
      // `shape` is what this bench wrote before the ratio came off the
      // manifest; its three values are all labels the grid still offers.
      const said = scene.aspect ?? scene.shape;
      if (this.rules().aspects.some(([label]) => label === said)) this.aspect = said;
      if (PASS_BY_ID[scene.pass]) this.pass = scene.pass;
      this.lookAtSet();
    } catch {
      /* a broken sidecar opens the default set, which is the bench either way */
    }
  }

  /** The canvas rules of the family whose render will read this guide. */
  rules() {
    return rulesFor(this.family);
  }

  /** The chosen label's ratio, or the widest thing the family offers if the
   *  label has gone — a family switched under a saved scene can retire one. */
  ratio() {
    const found = this.rules().aspects.find(([label]) => label === this.aspect);
    return found ? found[1] : (this.rules().aspects[0]?.[1] ?? 16 / 9);
  }

  /** The pixels a frame is written at: the family's native canvas at this
   *  ratio, snapped to its own latent grid. Not `frame`, which is the glass. */
  frameSize() {
    const [w, h] = resolveCanvas(this.ratio(), this.rules().nativeShortEdge, this.rules());
    return { w, h };
  }

  cleanCam(cam) {
    const number = (value, fallback) =>
      Number.isFinite(Number(value)) ? Number(value) : fallback;
    return {
      x: clamp(number(cam.x, 0), -FAR, FAR),
      y: clamp(number(cam.y, 1.6), 0.05, BIG),
      z: clamp(number(cam.z, 0), -FAR, FAR),
      yaw: number(cam.yaw, 0),
      pitch: clamp(number(cam.pitch, 0), -1.45, 1.45),
      mm: clamp(number(cam.mm, 32), 18, 85),
    };
  }

  /** What rides in the sidecar — enough to put all of this back, plus the one
   *  thing written for readers other than this bench: `layout`, each named
   *  piece's screen box at every mark. No family reads it today; the
   *  layout-grounded conditioning the research is converging on does, and the
   *  boxes cost nothing here where they would cost a tracker anywhere else. */
  scene() {
    const { w, h } = this.frameSize();
    const stops = this.marks.length ? this.marks : [this.shot];
    const layout = this.objects
      .filter((piece) => piece.plays || piece.word)
      .map((piece) => ({
        who: piece.plays || undefined, what: piece.word || undefined,
        boxes: stops.map((markAt) => this.screenBox(piece, markAt, w, h)),
      }));
    return {
      objects: this.objects.map(({ id, ...piece }) => piece),
      marks: this.marks.map((markAt) => ({ ...markAt })),
      shot: { ...this.shot }, view: { ...this.view },
      duration: this.duration, aspect: this.aspect, pass: this.pass,
      layout: layout.length ? layout : undefined,
    };
  }

  /** A piece's bounding box on a mark's frame, normalised — or null when the
   *  whole of it is behind the lens. Clamped to the frame, so a box is what a
   *  reader could actually ground against the written pixels. */
  screenBox(piece, cam, width, height) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, seen = false;
    for (const corner of cornersOf(piece)) {
      const at = project(cam, corner, width, height);
      if (!at) continue;
      seen = true;
      x0 = Math.min(x0, at.x); y0 = Math.min(y0, at.y);
      x1 = Math.max(x1, at.x); y1 = Math.max(y1, at.y);
    }
    if (!seen) return null;
    const box = [clamp(x0 / width, 0, 1), clamp(y0 / height, 0, 1),
                 clamp(x1 / width, 0, 1), clamp(y1 / height, 0, 1)];
    if (box[2] - box[0] <= 0 || box[3] - box[1] <= 0) return null;
    return box.map((edge) => Math.round(edge * 1000) / 1000);
  }

  // ---- the room --------------------------------------------------------------

  mount() {
    this.stops = el("div", { class: "mmc-bn-stops" });
    this.rail = keepScroll(el("div", { class: "mmc-bn-rail" }, [
      this.stops,
      el("div", { class: "mmc-bn-where" }, [
        el("b", { text: t("Writes into") }),
        el("span", { class: "mmc-bn-path", text: `input/${WRITES}` }),
      ]),
    ]));
    this.canvas = el("canvas", { class: "mmc-bn-layer", draggable: "false" });
    this.context = this.canvas.getContext("2d");
    this.frame = el("div", { class: "mmc-bn-frame mmc-bo-frame" });
    this.box = el("div", { class: "mmc-bn-box" }, [this.frame]);
    this.cut = el("div", { class: "mmc-bo-cut" });
    this.foot = el("div", { class: "mmc-bn-foot" });
    this.work = el("div", { class: "mmc-bn-work" }, [this.box, this.cut, this.foot]);
    this.room = el("div", { class: "mmc-bn-room" }, [this.rail, this.work]);
    this.sheet = el("div", { class: "mmc-bn mmc-bo" }, [
      el("div", { class: "mmc-bn-bar" }, [
        // The wordmark is the door, exactly as it is on the other benches.
        this.back
          ? el("button", {
              class: "mmc-bn-home", title: t("Back to the tools"),
              onclick: () => { this.close(); this.back(); },
            }, [
              el("span", { class: "mmc-bn-logo" }, [mark(20)]),
              el("span", { text: "Continuity" }),
              el("span", { class: "mmc-bn-caret" }, [icon("chevron", 12)]),
            ])
          : el("span", { class: "mmc-bn-mark" }, [
              el("span", { class: "mmc-bn-logo" }, [mark(20)]),
              el("span", { class: "mmc-bn-word", text: "Continuity" }),
            ]),
        el("span", { class: "mmc-bn-slash", text: "/" }),
        el("span", { class: "mmc-bn-here", text: t("Blockout") }),
        el("span", { class: "mmc-bn-gap" }),
        el("button", {
          class: "mmc-close", text: "✕", title: t("Close the bench"),
          onclick: () => this.close(),
        }),
      ]),
      this.room,
    ]);
    this.overlay = el("div", { class: "mmc-overlay mmc-bn-over" }, [this.sheet]);
    this.unmount = mountOverlay(this.overlay, () => this.close());

    this.keys = (event) => this.onKey(event, true);
    this.keysUp = (event) => this.onKey(event, false);
    this.dropKeys = () => this.held.clear();
    document.addEventListener("keydown", this.keys);
    document.addEventListener("keyup", this.keysUp);
    globalThis.addEventListener("blur", this.dropKeys);

    this.render();
    this.watchBox();
    this.fit();
    this.paint();
  }

  close() {
    if (open === this) open = null;
    this.stopPlay();
    this.held.clear();
    this.watcher?.disconnect();
    document.removeEventListener("keydown", this.keys);
    document.removeEventListener("keyup", this.keysUp);
    globalThis.removeEventListener("blur", this.dropKeys);
    this.unmount?.();
    this.resolve?.();
  }

  // ---- drawing ---------------------------------------------------------------

  render() {
    this.paintBench();
    this.paintBox();
    this.paintCut();
    this.paintFoot();
  }

  section(title, children) {
    return el("div", { class: "mmc-bn-stop" }, [
      el("div", { class: "mmc-bn-stopname", text: title }),
      ...children.filter(Boolean),
    ]);
  }

  passOf() {
    return PASS_BY_ID[this.pass];
  }

  /** Whichever camera the glass is looking through. Everything that draws or
   *  picks goes through here; everything that *writes* goes to `this.shot`. */
  eye() {
    return this.through ? this.shot : this.view;
  }

  piece() {
    return this.objects.find((candidate) => candidate.id === this.selected) ?? null;
  }

  paintBench() {
    this.fields = [];
    this.stops.replaceChildren(
      this.section(t("Set"), [
        el("div", { class: "mmc-bo-adds" }, Object.entries(KINDS).map(([kind, spec]) =>
          el("button", {
            class: "mmc-bn-verb", onclick: () => this.addPiece(kind),
          }, [el("span", { text: t(spec.label) })]))),
        this.objects.length ? null : el("p", { class: "mmc-bn-empty", text:
          t("The floor is bare. Add a piece, or start from one of these.") }),
        el("div", { class: "mmc-bo-presets" }, PRESETS.map((preset) => el("button", {
          class: "mmc-bo-preset", title: t(preset.note),
          onclick: () => this.usePreset(preset),
        }, [el("span", { text: t(preset.label) })]))),
        this.piecePanel(),
        el("div", { class: "mmc-bn-dial" }, [
          el("div", { class: "mmc-bn-diallabel" }, [el("span", { text: t("Snap") })]),
          el("div", { class: "mmc-bn-opts" }, [
            [0, t("Off")], [0.25, "0.25 m"], [1, "1 m"],
          ].map(([step, label]) => el("button", {
            class: `mmc-bn-opt${this.snap === step ? " on" : ""}`,
            "aria-pressed": this.snap === step,
            onclick: () => { this.snap = step; this.paintBench(); },
          }, [el("span", { text: label })]))),
        ]),
        el("p", { class: "mmc-bn-note",
          title: t("Press for the rest"),
          onclick: (event) => event.currentTarget.classList.toggle("open"),
          text: t("Click a piece to select it, then drag its handles. 1 moves, "
            + "2 turns, 3 sizes. Shift+D copies the selection, X removes it, "
            + "F swings the view round to look at it.") }),
      ]),
      this.section(t("Camera"), [
        el("div", { class: "mmc-bo-verbs" }, [
          el("button", {
            class: "mmc-bn-verb", disabled: this.through || null,
            title: t("Move the shot camera to where you are standing now."),
            onclick: () => this.cameraHere(),
          }, [el("span", { text: t("Put the camera here") })]),
          el("button", {
            class: "mmc-bn-verb", disabled: this.through || null,
            title: t("Fly the view round to where the shot camera stands."),
            onclick: () => this.goToCamera(),
          }, [el("span", { text: t("Go to the camera") })]),
        ]),
        this.dial(t("Lens"), this.shot.mm, 18, 85, 1, (value) => {
          this.shot.mm = value;
          this.markStale();
          this.paintSay();
          this.paint();
        }, (value) => `${Math.round(value)} mm`),
        el("div", { class: "mmc-bn-dial" }, [
          el("div", { class: "mmc-bn-diallabel" }, [
            el("span", { text: t("Frame") }),
          ]),
          this.aspectPill(),
        ]),
        el("p", { class: "mmc-bn-note",
          title: t("Press for the rest"),
          onclick: (event) => event.currentTarget.classList.toggle("open"),
          text: t("Free look flies the view and never touches the shot: WASD "
            + "walks, Q and E drop and rise, drag orbits, the wheel zooms, and "
            + "a right-drag slides — as does a middle-drag or a shift-drag. "
            + "Through the lens the glass is the lens — drag pans and tilts, "
            + "the same three slides truck and pedestal, and the wheel pushes "
            + "in and pulls out.") }),
      ]),
      this.section(t("Path"), [
        el("div", { class: "mmc-bo-marks" },
          this.marks.length
            ? this.marks.map((markAt, index) => this.markRow(markAt, index))
            : [el("p", { class: "mmc-bn-empty", text: t("No marks yet. Frame the shot and press Mark.") })]),
        el("div", { class: "mmc-bo-runs" }, [
          el("span", { text: t("Runs") }),
          el("button", { class: "mmc-bo-step", text: "−", "aria-label": t("Shorter"),
            onclick: () => this.setDuration(this.duration - 0.5) }),
          el("b", { text: `${this.duration.toFixed(1)}s` }),
          el("button", { class: "mmc-bo-step", text: "+", "aria-label": t("Longer"),
            onclick: () => this.setDuration(this.duration + 0.5) }),
        ]),
        el("p", { class: "mmc-bn-note", text:
          t("Frame the shot, press Mark, frame the next one. The clip walks the marks in order.") }),
      ]),
      this.section(t("Output"), [
        el("div", { class: "mmc-bn-list" }, PASSES.map((pass) => el("button", {
          class: `mmc-bn-pick${pass.id === this.pass ? " on" : ""}`,
          "aria-pressed": pass.id === this.pass,
          title: t(pass.note),
          onclick: () => this.setPass(pass.id),
        }, [el("span", { class: "mmc-bn-pickname", text: t(pass.label) })]))),
        el("p", {
          class: "mmc-bn-note", text: t(this.passOf().note),
          title: t("Press for the rest"),
          onclick: (event) => event.currentTarget.classList.toggle("open"),
        }),
      ]),
    );
  }

  /** One dial, in the bench's own dress. */
  dial(label, value, min, max, step, onchange, format) {
    const readout = el("span", { class: "mmc-bn-value", text: format(value) });
    return el("div", { class: "mmc-bn-dial" }, [
      el("div", { class: "mmc-bn-diallabel" }, [
        el("span", { text: label }), readout,
      ]),
      el("input", {
        class: "mmc-bn-range", type: "range",
        min: String(min), max: String(max), step: String(step), value: String(value),
        "aria-label": label,
        oninput: (event) => {
          const now = Number(event.target.value);
          readout.textContent = format(now);
          onchange(now);
        },
      }),
    ]);
  }

  /**
   * A row of three numbers, the way a properties panel has always shown a
   * vector. Registered in `this.fields` so a drag on the glass writes back into
   * them — a number that disagrees with the picture is worse than no number,
   * and the whole reason to have them is that they agree.
   */
  vector(label, keys, read, write, { step = 0.05, suffix = "" } = {}) {
    return el("div", { class: "mmc-bn-dial" }, [
      el("div", { class: "mmc-bn-diallabel" }, [el("span", { text: label })]),
      el("div", { class: "mmc-bo-vec" }, keys.map((key) => {
        const input = el("input", {
          class: "mmc-bo-num", type: "number", step: String(step),
          value: read(key).toFixed(2),
          "aria-label": `${label} ${key.toUpperCase()}${suffix}`,
          oninput: (event) => {
            const now = event.target.valueAsNumber;
            if (Number.isFinite(now)) { write(key, now); this.paint(); }
          },
        });
        this.fields.push({ input, read: () => read(key) });
        return el("label", { class: "mmc-bo-vecslot" }, [
          el("span", { class: `mmc-bo-axis is-${key}`, text: key.toUpperCase() }),
          input,
        ]);
      })),
    ]);
  }

  /** The rail's numbers, brought back into step with whatever the glass just
   *  did. Skips whichever field the caret is in: nobody wants a drag to
   *  overwrite the digits they are halfway through typing. */
  syncFields() {
    for (const field of this.fields) {
      if (!field.input.isConnected || field.input === document.activeElement) continue;
      const now = field.read().toFixed(2);
      if (field.input.value !== now) field.input.value = now;
    }
  }

  /** The selected piece's panel. In the rail because that is where numbers
   *  live; which piece they aim at is the click on the glass. */
  piecePanel() {
    const piece = this.piece();
    if (!piece) return null;
    return el("div", { class: "mmc-bo-piece" }, [
      el("div", { class: "mmc-bo-piecename" }, [
        el("span", { text: t(KINDS[piece.kind].label) }),
        el("span", { class: "mmc-bn-gap" }),
        el("button", {
          class: "mmc-bo-remove", text: t("Duplicate"), title: t("Make another of this piece"),
          onclick: () => this.duplicate(),
        }),
        el("button", {
          class: "mmc-bo-remove", text: t("Remove"),
          onclick: () => this.removePiece(),
        }),
      ]),
      // Who this piece is. Two answers and they are different kinds of answer:
      // a cast member, whose handle the prompt's substitution already knows how
      // to spend, or a plain word for a thing. A piece playing somebody needs
      // no word — the handle is the word.
      this.cast.length ? el("div", { class: "mmc-bn-dial" }, [
        el("div", { class: "mmc-bn-diallabel" }, [el("span", { text: t("Plays") })]),
        el("button", {
          class: "mmc-bo-who",
          title: t("Which cast member this piece stands for. Their handle is "
            + "written into the staging sentence, where the prompt turns it "
            + "into their references."),
          onclick: (event) => this.openWho(event.currentTarget, piece),
        }, [
          piece.plays
            ? el("span", { class: `mmc-bo-whodot mmc-tag-${tagIndex(piece.plays)}` })
            : null,
          el("span", { class: "mmc-bo-whoname",
                       text: piece.plays ? `@${piece.plays}` : t("Nobody") }),
          icon("chevron", 11),
        ]),
      ]) : null,
      piece.plays ? null : el("div", { class: "mmc-bn-dial" }, [
        el("div", { class: "mmc-bn-diallabel" }, [el("span", { text: t("Called") })]),
        el("input", {
          class: "mmc-bn-text", type: "text", value: piece.word ?? "",
          placeholder: t("table, doorway, car…"), maxlength: "48",
          "aria-label": t("What to call this piece in the prompt"),
          oninput: (event) => {
            piece.word = event.target.value.trim();
            this.markStale();
            this.paintSay();
            this.paint();
          },
        }),
      ]),
      (piece.plays || piece.word) ? el("p", { class: "mmc-bn-note", text:
        t("Named pieces are written into the staging — who stands where, in the "
          + "prompt's own words.") }) : null,
      this.vector(t("Place"), ["x", "y", "z"],
        (key) => piece[key],
        (key, value) => { piece[key] = clamp(value, key === "y" ? 0 : -FAR, key === "y" ? BIG : FAR); this.markStale(); }),
      this.vector(t("Size"), ["w", "h", "d"],
        (key) => piece[key],
        (key, value) => { piece[key] = clamp(value, 0.05, BIG); this.markStale(); }),
      this.vector(t("Turn"), ["x", "y", "z"],
        (key) => piece[`r${key}`] * DEG,
        (key, value) => { piece[`r${key}`] = clamp(value, -180, 180) / DEG; this.markStale(); },
        { step: 1, suffix: "°" }),
    ]);
  }

  /** The cast, offered. `openChoicePopover` is the pack's own chooser, so the
   *  row reads the way every other choice in the pack reads. */
  openWho(anchor, piece) {
    openChoicePopover(anchor, {
      title: t("Who this piece plays"),
      options: ["", ...this.cast],
      value: piece.plays || "",
      label: (option) => (option ? `@${option}` : t("Nobody")),
      onPick: (option) => {
        piece.plays = option;
        this.markStale();
        this.paintBench();
        this.paintSay();
        this.paint();
      },
    });
  }

  markRow(markAt, index) {
    const when = this.marks.length < 2 ? 0 : (index / (this.marks.length - 1)) * this.duration;
    return el("div", { class: "mmc-bo-markrow" }, [
      el("span", { class: "mmc-bo-markdot" }),
      el("button", {
        class: "mmc-bo-markgo", text: t("Mark {n}", { n: index + 1 }),
        title: t("Put the shot camera back on this mark"),
        onclick: () => {
          Object.assign(this.shot, markAt);
          this.scrub = this.marks.length < 2 ? 0 : index / (this.marks.length - 1);
          this.paintPlayhead();
          this.paintSay();
          this.paint();
        },
      }),
      el("span", { class: "mmc-bo-markwhen", text: formatSeconds(when) }),
      el("button", {
        class: "mmc-bo-remove", text: "✕", title: t("Drop this mark"),
        onclick: () => {
          this.marks.splice(index, 1);
          this.markStale();
          this.paintBench();
          this.paintCut();
          this.paintFoot();
          this.paint();
        },
      }),
    ]);
  }

  // ---- the set, edited -------------------------------------------------------

  addPiece(kind) {
    // In front of whatever you are looking through, on the floor: the piece
    // lands where you were already looking rather than at an origin you would
    // then have to go and find.
    const cam = this.eye();
    const ahead = flatForwardOf(cam);
    const piece = makePiece(this.nextId++, kind, {
      x: clamp(cam.x + ahead[0] * 4.5, -FAR, FAR),
      z: clamp(cam.z + ahead[2] * 4.5, -FAR, FAR),
    });
    this.objects.push(piece);
    this.selected = piece.id;
    this.markStale();
    this.paintBench();
    this.paint();
  }

  duplicate() {
    const piece = this.piece();
    if (!piece) return;
    const copy = makePiece(this.nextId++, piece.kind, { ...piece, x: piece.x + 0.6, z: piece.z + 0.6 });
    this.objects.push(copy);
    this.selected = copy.id;
    this.markStale();
    this.paintBench();
    this.paint();
  }

  removePiece() {
    const piece = this.piece();
    if (!piece) return;
    this.objects = this.objects.filter((candidate) => candidate !== piece);
    this.selected = 0;
    this.markStale();
    this.paintBench();
    this.paint();
  }

  /** A preset, laid out. It replaces the set rather than adding to it — that is
   *  what "start from" means — and it brings its own camera and its own move,
   *  so what lands on the glass is a shot rather than an assembly kit. */
  usePreset(preset) {
    const made = preset.make();
    this.objects = made.objects.map((piece, index) => makePiece(index + 1, piece.kind, piece));
    this.nextId = this.objects.length + 1;
    this.marks = (made.marks ?? []).map((markAt) => this.cleanCam(markAt));
    if (this.marks.length) Object.assign(this.shot, this.marks[0]);
    this.selected = 0;
    this.scrub = 0;
    this.lookAtSet();
    this.markStale();
    this.paintBench();
    this.paintCut();
    this.paintFoot();
    this.paint();
  }

  // ---- getting about ---------------------------------------------------------

  /** Put the free-look camera back where it can see the whole set — and the
   *  shot camera in it, which is half of what there is to look at. */
  lookAtSet() {
    let x0 = Infinity, y0 = Infinity, z0 = Infinity;
    let x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    const points = [[this.shot.x, this.shot.y, this.shot.z]];
    for (const piece of this.objects) points.push(...cornersOf(piece));
    for (const markAt of this.marks) points.push([markAt.x, markAt.y, markAt.z]);
    for (const [x, y, z] of points) {
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); z0 = Math.min(z0, z);
      x1 = Math.max(x1, x); y1 = Math.max(y1, y); z1 = Math.max(z1, z);
    }
    this.pivot = { x: (x0 + x1) / 2, y: (y0 + y1) / 2, z: (z0 + z1) / 2 };
    const span = Math.max(x1 - x0, y1 - y0, z1 - z0, 2.5);
    this.orbit = clamp(span / Math.tan(vfovOf(this.view.mm) / 2) * 0.6, 6, 60);
    this.placeOrbit();
  }

  /** Look at one piece, from where you already are. In free look the view flies
   *  round to orbit it; through the lens it is the shot camera that turns, and
   *  it turns rather than moves — the framing is the thing being kept. */
  focusOn(piece) {
    if (!piece) return this.lookAtSet();
    const centre = centreOf(piece);
    if (this.through) {
      const to = [centre[0] - this.shot.x, centre[1] - this.shot.y, centre[2] - this.shot.z];
      this.shot.yaw = Math.atan2(to[0], to[2]);
      this.shot.pitch = clamp(Math.atan2(to[1], Math.hypot(to[0], to[2])), -1.45, 1.45);
      this.markStale();
      this.paintSay();
      return this.paint();
    }
    this.pivot = { x: centre[0], y: centre[1], z: centre[2] };
    const span = Math.max(piece.w, piece.h, piece.d);
    this.orbit = clamp(span / Math.tan(vfovOf(this.view.mm) / 2) * 1.1 + 0.8, 1.5, 60);
    this.placeOrbit();
    this.paint();
  }

  /** The free-look camera, hung off the pivot at its current angles. */
  placeOrbit() {
    const ahead = forwardOf(this.view);
    this.view.x = this.pivot.x - ahead[0] * this.orbit;
    this.view.y = this.pivot.y - ahead[1] * this.orbit;
    this.view.z = this.pivot.z - ahead[2] * this.orbit;
  }

  /** Keep the pivot the orbit distance ahead — what a fly or a slide leaves
   *  true, so the next orbit turns around what is in front of you. */
  carryPivot() {
    const ahead = forwardOf(this.view);
    this.pivot = {
      x: this.view.x + ahead[0] * this.orbit,
      y: this.view.y + ahead[1] * this.orbit,
      z: this.view.z + ahead[2] * this.orbit,
    };
  }

  setThrough(through) {
    if (this.through === through) return;
    this.through = through;
    this.stopPlay();
    if (!through) this.carryPivotFromShot();
    this.paintBench();
    this.paintBox();
    this.paint();
  }

  /** Stepping back out of the lens leaves you standing where the lens was,
   *  looking at what it was looking at — the one continuity that makes the two
   *  cameras feel like one place rather than two. */
  carryPivotFromShot() {
    const ahead = forwardOf(this.shot);
    this.orbit = clamp(this.orbit, 2.5, 60);
    this.pivot = {
      x: this.shot.x + ahead[0] * this.orbit,
      y: this.shot.y + ahead[1] * this.orbit,
      z: this.shot.z + ahead[2] * this.orbit,
    };
    this.view.yaw = this.shot.yaw;
    this.view.pitch = this.shot.pitch;
    this.placeOrbit();
  }

  cameraHere() {
    Object.assign(this.shot, {
      x: clamp(this.view.x, -FAR, FAR),
      y: clamp(this.view.y, 0.05, BIG),
      z: clamp(this.view.z, -FAR, FAR),
      yaw: this.view.yaw,
      pitch: clamp(this.view.pitch, -1.45, 1.45),
    });
    this.markStale();
    this.paintSay();
    this.paint();
  }

  goToCamera() {
    this.view.yaw = this.shot.yaw;
    this.view.pitch = this.shot.pitch;
    this.orbit = clamp(this.orbit, 2.5, 12);
    const ahead = forwardOf(this.shot);
    this.pivot = {
      x: this.shot.x + ahead[0] * this.orbit,
      y: this.shot.y + ahead[1] * this.orbit,
      z: this.shot.z + ahead[2] * this.orbit,
    };
    this.placeOrbit();
    this.paint();
  }

  setPass(id) {
    this.pass = id;
    this.markStale();
    this.paintBench();
    this.paintBox();
    this.paint();
  }

  setShowPass(showPass) {
    if (this.showPass === showPass) return;
    this.showPass = showPass;
    this.paintBox();
    this.paint();
  }

  setTool(tool) {
    this.tool = tool;
    this.paintBox();
    this.paint();
  }

  /** The aspect pill, and the popover behind it — the strip's, not a copy.
   *  `openAspectPopover` wants something with a family and an `aspect` to
   *  write, so it is handed one: the bench has both, they are just not on a
   *  timeline blob, and a shim is cheaper than a second popover to keep in
   *  step with the first. */
  aspectPill() {
    const { w, h } = this.frameSize();
    return el("button", {
      class: "mmc-pill mmc-bo-aspect",
      title: t("The shape a guide is written at. The frame's pixels are this "
        + "family's own canvas at that ratio, so what is written is the size "
        + "the render will read."),
      onclick: (event) => {
        const shim = { family: this.family, aspect: this.aspect };
        openAspectPopover(event.currentTarget, shim, () => this.setAspect(shim.aspect));
      },
    }, [
      aspectGlyph(this.ratio(), PILL_GLYPH),
      el("span", { text: this.aspect }),
      el("span", { class: "mmc-pill-sub", text: `${w}×${h}` }),
    ]);
  }

  setAspect(aspect) {
    if (!aspect || aspect === this.aspect) return;
    this.aspect = aspect;
    this.rasters.clear();
    this.raster = null;
    this.markStale();
    this.paintBench();
    this.fit();
    this.paint();
  }

  setDuration(seconds) {
    this.duration = clamp(Math.round(seconds * 2) / 2, 1, 10);
    this.markStale();
    this.paintBench();
    this.paintFoot();
  }

  /** A change under a written result: what the file holds is no longer what
   *  the glass says, so the doors close until the next run. Same rule as a
   *  dial on the tracing bench — and note what is *not* here: flying the free
   *  camera changes nothing about the file, and so stales nothing. */
  markStale() {
    if (!this.result) return;
    this.result = null;
    this.sentTo.clear();
    this.paintFoot();
  }

  // ---- the light box ---------------------------------------------------------

  paintBox() {
    const seg = (label, on, onclick, title) => el("button", {
      class: `mmc-bo-seg${on ? " on" : ""}`, "aria-pressed": on,
      title: title ?? null, onclick,
    }, [el("span", { text: label })]);
    this.frame.replaceChildren(
      this.canvas,
      el("div", { class: "mmc-bo-hud top" }, [
        el("div", { class: "mmc-bo-switch" }, [
          seg(t("Free look"), !this.through, () => this.setThrough(false),
              t("Fly around the set. The shot camera stays where it is.")),
          seg(t("Through the lens"), this.through, () => this.setThrough(true),
              t("Stand in the shot camera. What you see is what gets written.")),
        ]),
        el("span", { class: "mmc-bn-gap" }),
        el("div", { class: "mmc-bo-switch" }, [
          seg(t("Stage"), !this.showPass, () => this.setShowPass(false),
              t("The set as you handle it — clay, grid, gizmo, camera.")),
          seg(t(this.passOf().label), this.showPass, () => this.setShowPass(true),
              t("The frame exactly as the file will hold it.")),
        ]),
      ]),
      el("div", { class: "mmc-bo-hud bottom" }, [
        this.selected && !this.showPass
          ? el("div", { class: "mmc-bo-switch" }, [
              seg(t("Move"), this.tool === "move", () => this.setTool("move"), "1"),
              seg(t("Turn"), this.tool === "turn", () => this.setTool("turn"), "2"),
              seg(t("Size"), this.tool === "size", () => this.setTool("size"), "3"),
            ])
          : null,
        el("span", { class: "mmc-bn-gap" }),
      ].filter(Boolean)),
    );
    this.frame.onpointerdown = (event) => this.press(event);
    this.frame.ondblclick = (event) => this.pickFocus(event);
    this.frame.onwheel = (event) => this.wheel(event);
    this.frame.oncontextmenu = (event) => event.preventDefault();
    this.frame.ondragstart = (event) => event.preventDefault();
  }

  /**
   * Size the glass, and the buffer behind it.
   *
   * The frame is the shape's aspect fitted into the room. The buffer used to be
   * a fixed 704×396 whatever that came to, which is where the softness came
   * from: it was being scaled up to fill a box twice its width. Now it is the
   * frame's own pixels — device pixels, capped by what the rasterizer can keep
   * up with, and never past the size the run writes at, because past that it is
   * detail the file will not hold.
   */
  fit() {
    const { w, h } = this.frameSize();
    const room = this.box.getBoundingClientRect();
    if (!room.width || !room.height) return;
    const scale = Math.min(room.width / w, room.height / h);
    const wide = Math.max(1, Math.round(w * scale));
    const tall = Math.max(1, Math.round(h * scale));
    this.frame.style.width = `${wide}px`;
    this.frame.style.height = `${tall}px`;
    this.sizeRaster(wide);
  }

  sizeRaster(wide = this.frame.getBoundingClientRect().width) {
    if (!wide) return;
    const { w, h } = this.frameSize();
    const dpr = Math.min(2, globalThis.devicePixelRatio || 1);
    const want = clamp(Math.round(wide * dpr * (this.draft ? 0.55 : 1)), 360, Math.min(w, MOST_PREVIEW));
    const rw = want, rh = Math.max(1, Math.round((want * h) / w));
    const key = `${rw}x${rh}`;
    if (this.raster && this.raster.w === rw && this.raster.h === rh) return;
    if (!this.rasters.has(key)) {
      // Two sizes get used per shape — full and draft — so the map stays small;
      // it is cleared on a shape change rather than grown.
      this.rasters.set(key, new Raster(rw, rh));
    }
    this.raster = this.rasters.get(key);
    this.canvas.width = rw;
    this.canvas.height = rh;
  }

  /** Half resolution while something is in motion, full when it settles. The
   *  rasterizer is a per-pixel JS loop; a drag at a megapixel is a slideshow,
   *  and a drag at a quarter of one is a drag. */
  setDraft(draft) {
    if (this.draft === draft) return;
    this.draft = draft;
    this.sizeRaster();
    this.draw();
  }

  watchBox() {
    this.watcher?.disconnect();
    this.watcher = new ResizeObserver(() => { this.fit(); this.paint(); });
    this.watcher.observe(this.box);
  }

  /** Everything the glass shows, batched to a frame. */
  paint() {
    if (this.painting) return;
    this.painting = true;
    requestAnimationFrame(() => {
      this.painting = false;
      this.draw();
    });
  }

  /** The same, now. Wanted wherever a buffer has just been swapped and
   *  something is about to read it — a press picks out of the id buffer, and a
   *  handle drag measures its axis in the buffer's own pixels, so both would be
   *  reading a buffer nothing had drawn into yet. */
  draw() {
    if (!this.overlay.isConnected || !this.raster) return;
    const cam = this.eye();
    const tints = {};
    for (const piece of this.objects) {
      if (piece.plays) tints[piece.id] = tagRGB(tagIndex(piece.plays));
    }
    this.raster.raster(this.objects, cam);
    this.raster.shade(this.context, this.showPass ? this.pass : "stage",
                      { selected: this.selected, tints });
    if (!this.showPass) this.paintInk(cam);
    this.syncFields();
    this.paintSay();
  }

  /** How many buffer pixels one CSS pixel is worth — every stroke width, hit
   *  radius and type size on the glass is quoted in the latter and drawn in the
   *  former, so the ink looks the same whatever the buffer is sized at. */
  inkScale() {
    const wide = this.frame.getBoundingClientRect().width;
    return wide ? this.raster.w / wide : 1;
  }

  /**
   * The staging aids, over the shaded buffer.
   *
   * Order is depth order as far as it can be without a second z-buffer: the
   * camera and its path first (they belong to the set), then the names, then
   * the gizmo, which is a control and is always on top of everything because
   * you cannot grab what you cannot see.
   */
  paintInk(cam) {
    const context = this.context;
    const scale = this.inkScale();
    context.save();
    context.lineCap = "round";
    context.lineJoin = "round";
    if (this.through) this.inkThirds(context, scale);
    else { this.inkPath(context, cam, scale); this.inkCamera(context, cam, scale); }
    this.inkNames(context, cam, scale);
    this.inkGizmo(context, cam, scale);
    context.restore();
  }

  /** The rule of thirds, faint, while you are behind the lens. Every camera
   *  has had these in the finder for a century; this is the moment they help. */
  inkThirds(context, scale) {
    const { w, h } = this.raster;
    context.strokeStyle = "rgba(255,255,255,.13)";
    context.lineWidth = 1 * scale;
    context.beginPath();
    for (const at of [1 / 3, 2 / 3]) {
      context.moveTo(Math.round(w * at), 0); context.lineTo(Math.round(w * at), h);
      context.moveTo(0, Math.round(h * at)); context.lineTo(w, Math.round(h * at));
    }
    context.stroke();
  }

  /** The shot camera, standing in the set: a frustum of the shot's own aspect
   *  and lens, so its size on the glass is literally how much it can see. */
  inkCamera(context, cam, scale) {
    const { w, h } = this.raster;
    const shot = this.shot;
    const shape = this.frameSize();
    const th = Math.tan(vfovOf(shot.mm) / 2), tw = th * (shape.w / shape.h);
    const ahead = forwardOf(shot), right = rightOf(shot), up = upOf(shot);
    const far = 1.75;
    const corner = (sx, sy) => project(cam, [
      shot.x + ahead[0] * far + right[0] * tw * far * sx + up[0] * th * far * sy,
      shot.y + ahead[1] * far + right[1] * tw * far * sx + up[1] * th * far * sy,
      shot.z + ahead[2] * far + right[2] * tw * far * sx + up[2] * th * far * sy,
    ], w, h);
    const apex = project(cam, [shot.x, shot.y, shot.z], w, h);
    const face = [corner(-1, 1), corner(1, 1), corner(1, -1), corner(-1, -1)];
    if (!apex || face.some((point) => !point)) return;
    context.strokeStyle = "rgba(107,163,214,.85)";
    context.lineWidth = 1.6 * scale;
    context.beginPath();
    face.forEach((point, index) => {
      index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y);
    });
    context.closePath();
    for (const point of face) {
      context.moveTo(apex.x, apex.y);
      context.lineTo(point.x, point.y);
    }
    context.stroke();
    // The notch that says which way is up — the mark a real camera wears for
    // exactly this reason, and the only cue that tells a frustum from a cone.
    context.beginPath();
    context.moveTo(face[0].x, face[0].y);
    context.lineTo((face[0].x + face[1].x) / 2, (face[0].y + face[1].y) / 2 - 9 * scale);
    context.lineTo(face[1].x, face[1].y);
    context.stroke();
    context.fillStyle = "rgba(107,163,214,.9)";
    context.beginPath();
    context.arc(apex.x, apex.y, 3.2 * scale, 0, Math.PI * 2);
    context.fill();
  }

  /** The move, drawn where it happens: the camera's own line through the set,
   *  a diamond at every mark, and a dropped tick to the floor under each so the
   *  height reads. This is the dolly track, and it is chalk on the floor. */
  inkPath(context, cam, scale) {
    if (this.marks.length < 2) return;
    const { w, h } = this.raster;
    context.strokeStyle = "rgba(107,163,214,.55)";
    context.lineWidth = 1.4 * scale;
    context.beginPath();
    let started = false;
    for (let step = 0; step <= 64; step++) {
      const on = pathCam(this.marks, step / 64);
      const at = project(cam, [on.x, on.y, on.z], w, h);
      if (!at) { started = false; continue; }
      started ? context.lineTo(at.x, at.y) : context.moveTo(at.x, at.y);
      started = true;
    }
    context.stroke();
    for (const markAt of this.marks) {
      const at = project(cam, [markAt.x, markAt.y, markAt.z], w, h);
      const under = project(cam, [markAt.x, 0, markAt.z], w, h);
      if (!at) continue;
      if (under) {
        context.strokeStyle = "rgba(107,163,214,.28)";
        context.lineWidth = 1 * scale;
        context.beginPath();
        context.moveTo(at.x, at.y);
        context.lineTo(under.x, under.y);
        context.stroke();
      }
      context.fillStyle = "rgba(107,163,214,.95)";
      context.save();
      context.translate(at.x, at.y);
      context.rotate(Math.PI / 4);
      const side = 4.5 * scale;
      context.fillRect(-side / 2, -side / 2, side, side);
      context.restore();
    }
  }

  /** Each named piece's name, floated over it. A handle wears its hue; a word
   *  is quiet. Drawn after the buffer lands because it is ink over the picture,
   *  not part of it — which is also why none of it reaches the file. */
  inkNames(context, cam, scale) {
    const { w, h } = this.raster;
    const size = Math.max(10, Math.round(11 * scale));
    context.font = `600 ${size}px system-ui, sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "bottom";
    for (const piece of this.objects) {
      if (!piece.plays && !piece.word) continue;
      const at = project(cam, [piece.x, (piece.y ?? 0) + piece.h + 0.12, piece.z], w, h);
      if (!at || at.x < 8 || at.x > w - 8 || at.y < size || at.y > h) continue;
      const said = piece.plays ? `@${piece.plays}` : piece.word;
      context.lineWidth = 3 * scale;
      context.strokeStyle = "rgba(10,10,10,.75)";
      context.strokeText(said, at.x, at.y);
      if (piece.plays) {
        const [r, g, b] = tagRGB(tagIndex(piece.plays));
        context.fillStyle = `rgb(${r},${g},${b})`;
      } else {
        context.fillStyle = "rgba(233,231,226,.8)";
      }
      context.fillText(said, at.x, at.y);
    }
  }

  // ---- the gizmo -------------------------------------------------------------
  //
  // Three handles hung off the selected piece's centre, projected through
  // whichever camera the glass is using. Move works in world axes — sliding a
  // wall along the room is a spatial act, and a turned piece whose handles have
  // turned with it is the classic way to lose a set. Turn and Size work in the
  // piece's own axes, because both of them are about the box rather than the
  // room: `w` is a width along its own width, and a ring you drag is the ring
  // of the angle you are changing.

  /** The handles, in buffer pixels, or null when there is nothing to draw. */
  gizmo(cam) {
    const piece = this.piece();
    if (!piece || this.showPass) return null;
    const { w, h } = this.raster;
    const origin = centreOf(piece);
    const at = project(cam, origin, w, h);
    if (!at) return null;
    // A world length that comes out a constant share of the frame height, so
    // the handles are the same size to grab whatever the distance.
    const fl = (h / 2) / Math.tan(vfovOf(cam.mm) / 2);
    const len = (at.z * h * 0.17) / fl;
    const m = basisOf(piece);
    const parts = [];
    for (const key of AXES) {
      const axis = this.tool === "move" ? UNIT[key] : norm3(applyM(m, UNIT[key]));
      if (this.tool === "turn") {
        const [u, v] = planeOf(axis);
        const pts = [];
        for (let step = 0; step <= 48; step++) {
          const a = (step / 48) * Math.PI * 2;
          const c = Math.cos(a), s = Math.sin(a);
          const on = project(cam, [
            origin[0] + (u[0] * c + v[0] * s) * len,
            origin[1] + (u[1] * c + v[1] * s) * len,
            origin[2] + (u[2] * c + v[2] * s) * len,
          ], w, h);
          pts.push(on ? [on.x, on.y] : null);
        }
        parts.push({ key, axis, pts, ring: true });
      } else {
        const tip = project(cam, [
          origin[0] + axis[0] * len, origin[1] + axis[1] * len, origin[2] + axis[2] * len,
        ], w, h);
        if (!tip) continue;
        parts.push({ key, axis, pts: [[at.x, at.y], [tip.x, tip.y]] });
      }
    }
    return { piece, origin, at, len, parts };
  }

  inkGizmo(context, cam, scale) {
    const gizmo = this.gizmo(cam);
    if (!gizmo) return;
    for (const part of gizmo.parts) {
      context.strokeStyle = AXIS_INK[part.key];
      context.lineWidth = (part.ring ? 1.8 : 2.4) * scale;
      context.beginPath();
      let started = false;
      for (const point of part.pts) {
        if (!point) { started = false; continue; }
        started ? context.lineTo(point[0], point[1]) : context.moveTo(point[0], point[1]);
        started = true;
      }
      context.stroke();
      if (part.ring) continue;
      const tip = part.pts[1];
      context.fillStyle = AXIS_INK[part.key];
      if (this.tool === "size") {
        const side = 6 * scale;
        context.fillRect(tip[0] - side / 2, tip[1] - side / 2, side, side);
      } else {
        context.beginPath();
        context.arc(tip[0], tip[1], 3.6 * scale, 0, Math.PI * 2);
        context.fill();
      }
    }
    // The centre: the free handle. On Move it slides the piece across the floor
    // under the pointer, which is the gesture this bench had before it had a
    // gizmo and is still the fastest way to rough a set in.
    context.fillStyle = "rgba(233,231,226,.9)";
    context.strokeStyle = "rgba(20,20,20,.6)";
    context.lineWidth = 1.4 * scale;
    context.beginPath();
    context.arc(gizmo.at.x, gizmo.at.y, 4.6 * scale, 0, Math.PI * 2);
    context.fill();
    context.stroke();
  }

  /** Which handle a press landed on, or null. */
  grabbed(gizmo, px, py, scale) {
    if (!gizmo) return null;
    const reach = 11 * scale;
    if (Math.hypot(gizmo.at.x - px, gizmo.at.y - py) <= 8 * scale) return { key: "free" };
    let best = null;
    for (const part of gizmo.parts) {
      const away = nearPolyline(part.pts, px, py);
      if (away <= reach && (!best || away < best.away)) best = { key: part.key, axis: part.axis, away };
    }
    return best;
  }

  // ---- the pointer, and which of several things a press is -------------------
  //
  // The rule that sorts them is the one every 3D application uses, and it is
  // worth stating because it is not obvious from any one gesture: handles
  // first, then geometry, then the camera. Shift always operates the camera,
  // because shift-drag *is* one of its moves; the middle button always slides,
  // because that is what a middle button has always done here.

  glassPoint(event) {
    const rect = this.frame.getBoundingClientRect();
    return {
      rect,
      px: clamp(((event.clientX - rect.left) / rect.width) * this.raster.w, 0, this.raster.w - 1),
      py: clamp(((event.clientY - rect.top) / rect.height) * this.raster.h, 0, this.raster.h - 1),
    };
  }

  press(event) {
    // The HUD floats inside the frame, so its buttons' presses bubble here. A
    // press on a control is that control's, not the camera's.
    if (!this.raster || event.target.closest?.(".mmc-bo-hud")) return;
    event.preventDefault();
    this.stopPlay();
    this.frame.focus?.();
    this.setDraft(true);
    const cam = this.eye();
    const { px, py } = this.glassPoint(event);
    const scale = this.inkScale();
    const slide = event.button === 1 || event.button === 2 || event.shiftKey;
    let move = null;

    if (!slide && !this.showPass) {
      const grab = this.grabbed(this.gizmo(cam), px, py, scale);
      if (grab) move = this.dragHandle(grab, event, cam);
    }
    if (!move && !slide && !this.showPass) {
      const id = this.raster.id[Math.floor(py) * this.raster.w + Math.floor(px)];
      const piece = this.objects.find((candidate) => candidate.id === id);
      if (piece) {
        if (piece.id !== this.selected) {
          this.selected = piece.id;
          this.paintBench();
          this.paintBox();
        }
        // A press on the body of a piece slides it on the floor, gizmo or no —
        // it is the gesture that made this bench worth using before there were
        // handles, and taking it away to make a point about modes would be a
        // worse tool for a purer story.
        move = this.dragFloor(piece, px, py, cam);
      } else if (this.selected) {
        this.selected = 0;
        this.paintBench();
        this.paintBox();
        this.paint();
      }
    }
    if (!move) move = this.dragCamera(event, slide);

    // Guarded: a pointer can be gone by the time this runs — a pen lifted
    // mid-press, a test harness's synthetic event — and a capture that failed
    // only costs the drag following off the element, not the press itself.
    try { this.frame.setPointerCapture(event.pointerId); } catch { /* see above */ }
    const up = () => {
      this.frame.removeEventListener("pointermove", move);
      this.frame.removeEventListener("pointerup", up);
      this.frame.removeEventListener("pointercancel", up);
      this.setDraft(false);
      this.paintBench();
    };
    this.frame.addEventListener("pointermove", move);
    this.frame.addEventListener("pointerup", up);
    this.frame.addEventListener("pointercancel", up);
  }

  /** Snapping, where it is on: whole steps for a place, degrees for a turn. */
  snapped(value, step = this.snap) {
    return step ? Math.round(value / step) * step : value;
  }

  /**
   * One gizmo handle, dragged.
   *
   * The axis is projected once, at the press, into a screen direction and a
   * pixels-per-metre. Everything after that is the pointer's travel projected
   * onto that direction — which is what makes a handle drag feel like sliding a
   * thing along a rail rather than chasing a cursor, and what keeps it stable
   * when the axis is nearly edge-on.
   */
  dragHandle(grab, event, cam) {
    const piece = this.piece();
    if (!piece) return null;
    if (grab.key === "free") {
      const { px, py } = this.glassPoint(event);
      return this.dragFloor(piece, px, py, cam);
    }
    const { w, h } = this.raster;
    const origin = centreOf(piece);
    const from = project(cam, origin, w, h);
    const along = project(cam, [
      origin[0] + grab.axis[0] * 0.5, origin[1] + grab.axis[1] * 0.5, origin[2] + grab.axis[2] * 0.5,
    ], w, h);
    const start = { ...piece };
    const at0 = this.glassPoint(event);

    if (this.tool === "turn") {
      if (!from) return null;
      const key = `r${grab.key}`;
      const toCam = [cam.x - origin[0], cam.y - origin[1], cam.z - origin[2]];
      // A turn about an axis pointing at you reads counter-clockwise on a
      // y-down glass; one pointing away reads the other way. Without this the
      // ring behind the piece turns it backwards.
      const spin = dot3(grab.axis, toCam) >= 0 ? 1 : -1;
      const angle0 = Math.atan2(at0.py - from.y, at0.px - from.x);
      return (moved) => {
        const now = this.glassPoint(moved);
        const angle = Math.atan2(now.py - from.y, now.px - from.x);
        let turn = start[key] + spin * (angle - angle0);
        if (this.snap) turn = (Math.round((turn * DEG) / 15) * 15) / DEG;
        piece[key] = clamp(((turn + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI,
                           -Math.PI, Math.PI);
        this.markStale();
        this.paint();
      };
    }

    if (!from || !along) return null;
    const dirx = along.x - from.x, diry = along.y - from.y;
    const len2 = dirx * dirx + diry * diry;
    if (len2 < 1e-6) return null;
    const size = this.tool === "size";
    const key = size ? { x: "w", y: "h", z: "d" }[grab.key] : grab.key;
    return (moved) => {
      const now = this.glassPoint(moved);
      // Half a metre of world is `len2`'s worth of screen, so this is metres.
      const metres = (((now.px - at0.px) * dirx + (now.py - at0.py) * diry) / len2) * 0.5;
      if (size) {
        // The handle sticks out from the centre, so pulling it a metre adds a
        // metre to each side. The base stays put on height — a piece grows up
        // off the floor it was standing on, which is what a set piece does.
        piece[key] = clamp(this.snapped(start[key] + metres * 2, this.snap && this.snap / 2),
                           0.05, BIG);
      } else {
        const low = grab.key === "y" ? 0 : -FAR;
        const high = grab.key === "y" ? BIG : FAR;
        piece[grab.key] = clamp(this.snapped(start[grab.key] + metres), low, high);
      }
      this.markStale();
      this.paint();
    };
  }

  /** A piece, dragged across the floor under the pointer. Held at the point it
   *  was grabbed by, so a wall does not jump its centre to the cursor. */
  dragFloor(piece, px, py, cam) {
    const grab = this.floorPoint(px, py, cam);
    const held = grab ? { x: grab.x - piece.x, z: grab.z - piece.z } : null;
    return (moved) => {
      if (!held) return;
      const point = this.glassPoint(moved);
      const floor = this.floorPoint(point.px, point.py, cam);
      if (!floor) return;
      piece.x = clamp(this.snapped(floor.x - held.x), -FAR, FAR);
      piece.z = clamp(this.snapped(floor.z - held.z), -FAR, FAR);
      this.markStale();
      this.paint();
    };
  }

  /**
   * The camera, operated.
   *
   * Two vocabularies, because there are two cameras and they are not for the
   * same thing. Through the lens the gestures are the camera department's —
   * pan, tilt, truck, pedestal — because those are the words the sentence at
   * the foot is written in. In free look they are a 3D application's: orbit
   * around the pivot, slide across it. Neither one leaks into the other.
   */
  dragCamera(event, slide) {
    let last = { x: event.clientX, y: event.clientY };
    return (at) => {
      const dx = at.clientX - last.x, dy = at.clientY - last.y;
      last = { x: at.clientX, y: at.clientY };
      const sliding = slide || at.shiftKey;
      if (this.through) {
        if (sliding) {
          this.slideBy(dx, dy);
        } else {
          this.shot.yaw += dx * 0.0038;
          this.shot.pitch = clamp(this.shot.pitch - dy * 0.0032, -1.45, 1.45);
        }
        this.markStale();
        this.paintSay();
      } else if (sliding) {
        this.slideBy(dx, dy);
      } else {
        this.view.yaw += dx * 0.0038;
        this.view.pitch = clamp(this.view.pitch - dy * 0.0032, -1.45, 1.45);
        this.placeOrbit();
      }
      this.paint();
    };
  }

  /**
   * The camera slid sideways and up, by a pointer's travel in CSS pixels.
   *
   * Through the lens that is a truck and a pedestal, and it stales the file
   * like every other thing the shot camera does. In free look it is a slide
   * across the view plane, paced by how far out the pivot is — panning a
   * street should take about as many centimetres of trackpad as panning a room.
   */
  slideBy(dx, dy) {
    if (this.through) {
      const right = rightOf(this.shot);
      this.shot.x = clamp(this.shot.x + right[0] * dx * 0.012, -FAR, FAR);
      this.shot.z = clamp(this.shot.z + right[2] * dx * 0.012, -FAR, FAR);
      this.shot.y = clamp(this.shot.y - dy * 0.012, 0.05, BIG);
      this.markStale();
      this.paintSay();
      return;
    }
    const right = rightOf(this.view), up = upOf(this.view);
    const step = this.orbit * 0.0016;
    for (const [key, index] of [["x", 0], ["y", 1], ["z", 2]]) {
      this.view[key] += (-right[index] * dx + up[index] * dy) * step;
    }
    this.carryPivot();
  }

  /** Where a glass pixel's ray meets the floor, or null when it never does. */
  floorPoint(px, py, cam = this.eye()) {
    const ray = this.raster.ray(px, py, cam);
    if (cam.y <= 0 || ray[1] >= -0.001) return null;
    const along = -cam.y / ray[1];
    if (along > 400) return null;
    return { x: cam.x + ray[0] * along, z: cam.z + ray[2] * along };
  }

  /** A double-click looks at what was under it — the piece, or the whole set. */
  pickFocus(event) {
    const { px, py } = this.glassPoint(event);
    const id = this.raster.id[Math.floor(py) * this.raster.w + Math.floor(px)];
    this.focusOn(this.objects.find((candidate) => candidate.id === id) ?? null);
  }

  wheel(event) {
    event.preventDefault();
    this.stopPlay();
    const step = event.deltaY < 0 ? 1 : -1;
    if (this.through) {
      const ahead = forwardOf(this.shot);
      this.shot.x = clamp(this.shot.x + ahead[0] * step * 0.35, -FAR, FAR);
      this.shot.z = clamp(this.shot.z + ahead[2] * step * 0.35, -FAR, FAR);
      this.shot.y = clamp(this.shot.y + ahead[1] * step * 0.35, 0.05, BIG);
      this.markStale();
      this.paintSay();
    } else {
      this.orbit = clamp(this.orbit * (step > 0 ? 0.86 : 1.16), 0.6, 90);
      this.placeOrbit();
    }
    this.paint();
  }

  // ---- the keyboard ----------------------------------------------------------
  //
  // The letters are the ones a hand that has used any 3D application already
  // has: WASD to walk, Q and E to drop and rise, G/R/S for the three
  // transforms, F to look at the selection, X to remove it. They are read off
  // the document rather than a focused element, and refused whenever a field
  // has the caret — a bench where typing "was" into a piece's name flies the
  // camera across the room is not a bench anybody would use twice.

  typing(event) {
    const at = event.target;
    return Boolean(at && (at.tagName === "INPUT" || at.tagName === "TEXTAREA"
      || at.tagName === "SELECT" || at.isContentEditable));
  }

  onKey(event, down) {
    if (!this.overlay?.isConnected) return;
    if (down && this.typing(event)) return;
    this.boost = event.shiftKey;
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    // Shift+D is the copy every 3D application has, and D is also "strafe
    // right". The selection decides: with something selected and the view not
    // already moving, the letter is the copy.
    if (down && key === "d" && event.shiftKey && this.selected && !this.flying) {
      this.duplicate();
      event.preventDefault();
      return;
    }
    if ("wasdqe".includes(key) && key.length === 1) {
      if (down) this.held.add(key); else this.held.delete(key);
      event.preventDefault();
      if (down) this.startFly();
      return;
    }
    if (!down) return;
    if (event.metaKey || event.ctrlKey) return;
    switch (key) {
      case "1": this.setTool("move"); break;
      case "2": this.setTool("turn"); break;
      case "3": this.setTool("size"); break;
      case "f": this.focusOn(this.piece()); break;
      case "x": case "Delete": this.removePiece(); break;
      case "m": this.setMark(); break;
      case "0": this.setThrough(!this.through); break;
      case " ": this.togglePlay(); break;
      default: return;
    }
    event.preventDefault();
  }

  startFly() {
    if (this.flying) return;
    this.flying = true;
    this.setDraft(true);
    let last = performance.now();
    const tick = (now) => {
      if (!this.overlay?.isConnected || !this.held.size) {
        this.flying = false;
        this.setDraft(false);
        return;
      }
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      this.fly(dt);
      this.flier = requestAnimationFrame(tick);
    };
    this.flier = requestAnimationFrame(tick);
  }

  fly(dt) {
    const cam = this.eye();
    const ahead = forwardOf(cam), right = rightOf(cam);
    // Metres per second, scaled by how far out you are: crossing a room and
    // crossing a street should each take about the same number of seconds.
    const pace = (this.through ? 2.6 : clamp(this.orbit * 0.5, 2, 14))
      * (this.boost ? 3 : 1) * dt;
    let dx = 0, dy = 0, dz = 0;
    if (this.held.has("w")) { dx += ahead[0]; dy += ahead[1]; dz += ahead[2]; }
    if (this.held.has("s")) { dx -= ahead[0]; dy -= ahead[1]; dz -= ahead[2]; }
    if (this.held.has("d")) { dx += right[0]; dz += right[2]; }
    if (this.held.has("a")) { dx -= right[0]; dz -= right[2]; }
    if (this.held.has("e")) dy += 1;
    if (this.held.has("q")) dy -= 1;
    if (!dx && !dy && !dz) return;
    const low = this.through ? 0.05 : -BIG;
    cam.x = clamp(cam.x + dx * pace, -FAR, FAR);
    cam.y = clamp(cam.y + dy * pace, low, BIG);
    cam.z = clamp(cam.z + dz * pace, -FAR, FAR);
    if (this.through) { this.markStale(); this.paintSay(); }
    else this.carryPivot();
    this.paint();
  }

  // ---- the path, under the glass ---------------------------------------------

  paintCut() {
    this.track = el("div", {
      class: "mmc-bo-track",
      onpointerdown: (event) => this.scrubFrom(event),
    }, [
      ...this.marks.map((markAt, index) => el("span", {
        class: "mmc-bo-mark",
        style: { left: `${this.marks.length < 2 ? 0 : (index / (this.marks.length - 1)) * 100}%` },
      })),
      this.playhead = el("span", { class: "mmc-bo-playhead" }),
    ]);
    this.playBtn = el("button", {
      class: "mmc-bo-play", title: t("Play the move"),
      "aria-label": t("Play the move"),
      onclick: () => this.togglePlay(),
    }, [icon("play", 13)]);
    this.cut.replaceChildren(
      this.playBtn,
      this.track,
      el("button", {
        class: "mmc-bo-markbtn",
        title: t("Hold the shot camera where it stands, as a stop on the move."),
        onclick: () => this.setMark(),
      }, [el("span", { class: "mmc-bo-markdot" }), el("span", { text: t("Mark this frame") })]),
    );
    this.paintPlayhead();
  }

  paintPlayhead() {
    if (this.playhead) this.playhead.style.left = `${this.scrub * 100}%`;
  }

  /** Scrubbing moves the shot camera along the path — and, when you are stood
   *  behind the lens, that is the picture moving too. In free look you watch
   *  the frustum travel its own track, which is the better way to judge a move. */
  applyPath(at) {
    if (this.marks.length < 2) return;
    this.scrub = clamp(at, 0, 1);
    Object.assign(this.shot, pathCam(this.marks, this.scrub));
    this.paintPlayhead();
    this.paintSay();
    this.paint();
  }

  scrubFrom(event) {
    this.stopPlay();
    const move = (at) => {
      const rect = this.track.getBoundingClientRect();
      if (rect.width) this.applyPath((at.clientX - rect.left) / rect.width);
    };
    move(event);
    try { this.track.setPointerCapture(event.pointerId); } catch { /* as press() */ }
    const up = () => {
      this.track.removeEventListener("pointermove", move);
      this.track.removeEventListener("pointerup", up);
      this.track.removeEventListener("pointercancel", up);
    };
    this.track.addEventListener("pointermove", move);
    this.track.addEventListener("pointerup", up);
    this.track.addEventListener("pointercancel", up);
  }

  setMark() {
    this.marks.push({ ...this.shot });
    this.scrub = 1;
    this.markStale();
    this.paintBench();
    this.paintCut();
    this.paintFoot();
    this.paint();
  }

  togglePlay() {
    if (this.playing) return this.stopPlay();
    if (this.marks.length < 2) return;
    this.playing = true;
    this.setDraft(true);
    this.playBtn.replaceChildren(icon("pause", 13));
    const from = this.scrub >= 0.999 ? 0 : this.scrub;
    const started = performance.now();
    const tick = (now) => {
      if (!this.playing) return;
      const at = from + (now - started) / 1000 / this.duration;
      if (at >= 1) {
        this.applyPath(1);
        return this.stopPlay();
      }
      this.applyPath(at);
      this.ticking = requestAnimationFrame(tick);
    };
    this.ticking = requestAnimationFrame(tick);
  }

  stopPlay() {
    if (!this.playing) return;
    this.playing = false;
    cancelAnimationFrame(this.ticking);
    this.setDraft(false);
    this.playBtn?.replaceChildren(icon("play", 13));
  }

  // ---- the foot, the run, the doors ------------------------------------------

  /** The whole of the prose — staging and move — as the bench stands now. Said
   *  about the shot camera, never the one you are flying. */
  said() {
    const { w, h } = this.frameSize();
    return stagingSentence(this.objects, this.marks, this.duration, this.shot, { w, h });
  }

  paintSay() {
    if (!this.say) return;
    const words = this.said();
    this.say.textContent = words;
    // The foot clips a long staging to one line; the whole of it is a hover
    // away, which is the note-clamping rule the rail already follows.
    this.say.title = words;
  }

  runLabel() {
    if (this.busy) return this.progress ?? t("Working…");
    return this.marks.length >= 2 ? t("Render the guide") : t("Trace the frame");
  }

  paintFoot() {
    // Filtered, not spread with holes: `replaceChildren` takes strings as well
    // as nodes, so a null reaches the document as the word "null".
    this.foot.replaceChildren(...[
      el("span", { class: "mmc-bo-say" }, [
        this.say = el("span", { text: this.said() }),
      ]),
      el("button", {
        class: "mmc-bn-second mmc-bo-copy", title: t("Copy the move, to be pasted into the prompt as prose."),
        onclick: (event) => {
          navigator.clipboard?.writeText(this.said()).catch(() => {});
          const button = event.currentTarget;
          button.textContent = t("Copied");
          setTimeout(() => { if (button.isConnected) button.textContent = t("Copy"); }, 1200);
        },
        text: t("Copy"),
      }),
      el("span", { class: "mmc-bn-gap" }),
      this.error ? el("span", { class: "mmc-bn-bad", text: this.error }) : null,
      el("button", {
        class: "mmc-bn-run",
        disabled: this.busy || null,
        onclick: () => this.run(),
      }, [
        this.busy ? spinner() : null,
        el("span", { text: this.runLabel() }),
      ].filter(Boolean)),
    ].filter(Boolean));
    this.paintResult();
  }

  /**
   * Draw the run's frames at full size and hand them over.
   *
   * The renderer is the preview's renderer at the run's resolution — the one-
   * renderer promise the whole bench stands on. A still never leaves the
   * browser except as an upload through core's own route; a clip goes to the
   * server in batches and comes back as a name in the input folder.
   */
  async run() {
    if (this.busy) return;
    this.busy = true;
    this.error = null;
    this.result = null;
    this.sentTo.clear();
    this.stopPlay();
    const step = (sentence) => {
      this.progress = sentence;
      if (this.overlay.isConnected) this.paintFoot();
    };
    try {
      const { w, h } = this.frameSize();
      // The set, as it stands at the press. The run yields to the page between
      // frames — that is what keeps the room responsive — so without this a
      // piece dragged mid-render would change sets halfway through the clip.
      const staged = this.objects.map((piece) => ({ ...piece }));
      const still = this.marks.length < 2;
      if (still) {
        step(t("Tracing the frame…"));
        const blob = await this.drawFull(w, h, this.shot, staged);
        const asset = await upload(
          new File([blob], `blockout-${this.pass}.png`, { type: "image/png" }), WRITES.slice(0, -1));
        this.result = { path: asset.path, kind: "image" };
      } else {
        const token = crypto.getRandomValues(new Uint32Array(4))
          .reduce((hex, part) => hex + part.toString(16).padStart(8, "0"), "");
        const count = Math.max(2, Math.round(this.duration * FPS));
        let batch = [];
        for (let index = 0; index < count; index++) {
          step(t("Drawing frame {n} of {count}…", { n: index + 1, count }));
          const cam = pathCam(this.marks, index / (count - 1));
          batch.push({ index, blob: await this.drawFull(w, h, cam, staged) });
          if (batch.length >= BATCH || index === count - 1) {
            step(t("Sending frame {n} of {count}…", { n: index + 1, count }));
            await blockoutFrames(token, batch);
            batch = [];
          }
        }
        step(t("Writing the clip…"));
        this.result = await blockoutWrite({
          token, fps: FPS, op: this.pass, scene: this.scene(),
        });
      }
      const pass = this.passOf();
      this.result.op = pass.label;
      this.result.opId = pass.opId;
      // The prose, stamped on the file's record: staging and move together, so
      // a door's take() — and anything later that wants the words — has them.
      this.result.words = this.said();
    } catch (error) {
      this.error = String(error.message || error);
    }
    this.busy = false;
    this.progress = null;
    if (this.overlay.isConnected) this.paintFoot();
  }

  /** One frame at the run's size, as a PNG blob. */
  drawFull(width, height, cam, staged = this.objects) {
    if (!this.full || this.full.w !== width || this.full.h !== height) {
      this.full = new Raster(width, height);
      this.fullCanvas = el("canvas");
      this.fullCanvas.width = width;
      this.fullCanvas.height = height;
      this.fullContext = this.fullCanvas.getContext("2d");
    }
    this.full.raster(staged, cam);
    this.full.shade(this.fullContext, this.pass);
    return new Promise((resolve, reject) => {
      this.fullCanvas.toBlob((blob) =>
        blob ? resolve(blob) : reject(new Error(t("a frame could not be encoded"))), "image/png");
    });
  }

  // ---- where a guide can go --------------------------------------------------
  //
  // The same doors, by the same rules, as the tracing bench — the targets are
  // the same objects the shell hands both benches, and the code below is its
  // code with one difference: a door that wants a still out of a clip is
  // answered by drawing the frame on the glass, not by cutting one from a file.

  produces() {
    return this.result?.kind === "video" ? ["video", "image"] : ["image"];
  }

  doors() {
    const can = this.produces();
    const written = this.result?.kind ?? null;
    return this.targets
      .filter((target) => !target.kinds || target.kinds.some((kind) => can.includes(kind)))
      .map((target) => ({
        target,
        frame: Boolean(target.kinds) && Boolean(written) && !target.kinds.includes(written),
      }));
  }

  paintResult() {
    if (!this.resultRow) {
      this.resultRow = el("div", { class: "mmc-bn-out" });
      this.work.appendChild(this.resultRow);
    }
    if (!this.result) {
      this.resultRow.replaceChildren();
      this.resultRow.classList.remove("on");
      return;
    }
    this.resultRow.classList.add("on");
    const doors = this.doors();
    const lead = doors.find((door) => !door.frame) ?? null;
    this.resultRow.replaceChildren(
      el("div", { class: "mmc-bn-outword" }, [
        el("span", { class: "mmc-bn-outname", text: this.result.path.split("/").pop() }),
        el("span", { class: "mmc-bn-outnote", text: this.outLine() }),
      ]),
      el("span", { class: "mmc-bn-gap" }),
      doors.length
        ? el("div", { class: "mmc-bn-doors" }, doors.map((door) => this.door(door, door === lead)))
        : el("span", { class: "mmc-bn-outnote", text:
            t("Pick it up from the picker whenever you want it.") }),
    );
  }

  outLine() {
    const parts = [t(this.result.op)];
    if (this.result.kind === "video") parts.push(formatSeconds(this.duration));
    parts.push(`input/${this.result.path.split("/").slice(0, -1).join("/")}`);
    return parts.join(" · ");
  }

  door(door, lead) {
    const id = door.target.id;
    const busy = this.sending === id;
    const done = this.sentTo.has(id);
    return el("button", {
      class: `mmc-bn-door${lead ? " lead" : ""}${done ? " done" : ""}`,
      disabled: Boolean(this.sending) || null,
      onclick: () => this.send(door),
    }, [
      el("span", { class: "mmc-bn-doorname", text: door.target.label }),
      el("span", { class: "mmc-bn-doordoes", text: this.doorLine(door, busy, done) }),
    ]);
  }

  doorLine(door, busy, done) {
    if (busy) return t("Drawing that frame…");
    if (done) return t("Sent. The file is in the input folder either way.");
    if (door.frame) return t("The frame on the glass, drawn as a still.");
    if (this.result?.kind === "image" && door.target.doesStill) return door.target.doesStill;
    return door.target.does ?? "";
  }

  async send(door) {
    if (!this.result || this.sending) return;
    let handed = this.result;
    if (door.frame) {
      this.sending = door.target.id;
      this.error = null;
      this.paintFoot();
      try {
        const { w, h } = this.frameSize();
        const blob = await this.drawFull(w, h, this.shot);
        const asset = await upload(
          new File([blob], `blockout-${this.pass}.png`, { type: "image/png" }), WRITES.slice(0, -1));
        handed = { path: asset.path, kind: "image",
                   op: this.result.op, opId: this.result.opId, words: this.result.words };
      } catch (error) {
        this.error = String(error.message || error);
        this.sending = null;
        this.paintFoot();
        return;
      }
      this.sending = null;
      if (!this.overlay.isConnected) return;
    }
    door.target.take(handed);
    this.sentTo.add(door.target.id);
    if (door.target.closeOnSend) return this.close();
    this.paintFoot();
  }
}
