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

import { el } from "./dom.js";
import { upload, blockoutFrames, blockoutWrite, probe } from "./api.js";
import { rulesFor, resolveCanvas, framesForSeconds } from "./canvas.js";
import * as S from "./state.js";
import { t } from "./i18n.js";

/** Where a written blockout lands. The server owns it (`blockout.SUBFOLDER`);
 *  this is the display copy for the line at the foot of the rail. */
export const WRITES = "continuity/blockout/";

/** The clip's rate. Fixed rather than dialled: a guide is read frame-for-frame
 *  against the shot, and 24 is what the families sample at. */
export const FPS = 24;

/** How many frames ride in one upload batch on the run. */
export const BATCH = 24;

// ---- what a blockout can be written as ---------------------------------------
//
// One tuple, the way the server benches keep theirs — except this catalogue
// needs no server: every pass is drawn from the geometry, so nothing about the
// machine can make one unready. `opId` names the tracing bench's operator each
// pass corresponds to, because the far side of a door reads it: the weights
// that follow a guide natively were post-trained on the *tracings*, and a
// blockout depth map should be read as exactly what it is.

export const PASSES = [
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
export const PASS_BY_ID = Object.fromEntries(PASSES.map((pass) => [pass.id, pass]));

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
export const MOST_PREVIEW = 1100;

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

export const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
export const FAR = 40;
export const BIG = 20;
export const DEG = 180 / Math.PI;

// ---- what a set can start from ---------------------------------------------------
//
// The five arrangements are now ways to start a set (the bench's glass offers
// them on a shot with no staging). A figure in them is a person, so it can be
// cast and blocked; the rest is the set.
//
// The bench used to open on six boxes, on the argument that an empty viewport
// is a black rectangle with nothing to operate the camera against. What it
// actually was, was six boxes to delete before the set you wanted could be
// staged. So the floor is bare, and the invitation is these: five arrangements
// out of the vocabulary a shot list already uses, each carrying its own camera
// and its own move, so pressing one gives you something that plays rather than
// something to assemble. Every one of them is a starting point to be pushed
// around — that is the whole of what a blockout is.

export const PRESETS = [
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
        { kind: "person", x: -0.85, z: 5.0, w: 0.52, h: 1.74, d: 0.42, ry: 0.5 },
        { kind: "person", x: 0.85, z: 5.3, w: 0.52, h: 1.8, d: 0.42, ry: -0.5 },
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
        { kind: "person", x: 0.15, z: 10.4, w: 0.5, h: 1.76, d: 0.4 },
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
        { kind: "person", x: 0, z: 3.6, w: 0.52, h: 1.78, d: 0.42 },
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
        { kind: "person", x: -1.3, z: 5.4, w: 0.5, h: 1.75, d: 0.4 },
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
export function tagRGB(index) {
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

export const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross3 = (a, b) => [a[1] * b[2] - a[2] * b[1],
                          a[2] * b[0] - a[0] * b[2],
                          a[0] * b[1] - a[1] * b[0]];
export const norm3 = (v) => {
  const len = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / len, v[1] / len, v[2] / len];
};

/** The piece's rotation as a row-major 3×3. */
export function basisOf(piece) {
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

export const applyM = (m, v) => [
  m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
  m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
  m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
];

/** The centre of a piece's box, in world. `y` is the bottom, so the centre is
 *  half a height above it — which is also what every placement word is measured
 *  from, and what the gizmo hangs off. */
export const centreOf = (piece) => [piece.x, (piece.y ?? 0) + restHeight(piece), piece.z];

/** How far a piece's centre sits above its lowest point, whichever way up it
 *  is: the box's half-extent along the world's up, turned. So `y` is always how
 *  far the lowest point is off the floor, and a figure laid flat rests on it
 *  rather than sinking into it. Upright, it is half the height, as it was. */
export function restHeight(piece) {
  const m = basisOf(piece);
  return (Math.abs(m[3]) * piece.w + Math.abs(m[4]) * piece.h + Math.abs(m[5]) * piece.d) / 2;
}

/** The eight corners of a piece's box, in world. */
export function cornersOf(piece) {
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
export const vfovOf = (mm) => 2 * Math.atan(12 / mm);

export const forwardOf = (cam) => {
  const cp = Math.cos(cam.pitch);
  return [Math.sin(cam.yaw) * cp, Math.sin(cam.pitch), Math.cos(cam.yaw) * cp];
};
export const flatForwardOf = (cam) => [Math.sin(cam.yaw), 0, Math.cos(cam.yaw)];
export const rightOf = (cam) => [Math.cos(cam.yaw), 0, -Math.sin(cam.yaw)];
export const upOf = (cam) => cross3(forwardOf(cam), rightOf(cam));

export class Raster {
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
export function project(cam, point, width, height) {
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

/**
 * A piece's posture, in words, or "" for standing on the floor: how far it is
 * tipped off upright, and how far its lowest point is off the ground. The words
 * carry the action; the guide only places the body (spec 3.4).
 */
export function postureOf(piece, person = piece?.kind === "person") {
  if (!piece) return "";
  const m = basisOf(piece);
  const tipped = Math.acos(clamp(m[4], -1, 1)) * DEG;
  const off = piece.y ?? 0;
  const lift = off > 0.3 ? t("{m} m off the ground", { m: off.toFixed(1) }) : "";
  if (tipped > 150) return lift ? `${t("upside down")}, ${lift}` : t("upside down");
  if (tipped > 60) return lift ? t("lying {lift}", { lift }) : t("lying on the floor");
  if (tipped > 20) return lift ? `${t("leaning")}, ${lift}` : t("leaning");
  return lift || "";
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
export function stagingSentence(objects, marks, duration, cam, size = { w: 16, h: 9 }, { withMove = true, ends = null } = {}) {
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
    const posture = postureOf(piece);
    clauses.push(piece.plays
      ? (posture ? t("@{who} is {posture} {place}", { who: piece.plays, posture, place: here.words })
                 : t("@{who} stands {place}", { who: piece.plays, place: here.words }))
      : posture ? t("{what}, {posture}, {place}", { what: articled(piece.word), posture, place: here.words })
        : t("{what} {place}", { what: articled(piece.word), place: here.words }));
  }
  // A change of posture within the shot, said once at the end: "@anna ends
  // standing". `ends` is the set as it stands at the shot's last frame.
  for (const end of ends ?? []) {
    const start = objects.find((piece) => piece.id === end.id);
    if (!start || (!end.plays && !end.word)) continue;
    const was = postureOf(start), now = postureOf(end);
    if (was === now) continue;
    const who = end.plays ? `@${end.plays}` : articled(end.word);
    clauses.push(t("{who} ends {posture}", { who, posture: now || (end.kind === "person" ? t("standing") : t("upright")) }));
  }
  for (const piece of entering) {
    clauses.push(t("@{who} comes into frame as the camera moves", { who: piece.plays }));
  }
  const move = withMove ? moveSentence(marks, duration, moveTarget(objects, marks, cam, size.w, size.h)) : "";
  if (!clauses.length) return move;
  const staging = clauses.join("; ") + ".";
  return `${staging.charAt(0).toUpperCase()}${staging.slice(1)}${move ? ` ${move}` : ""}`;
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



// ---- the gizmo's ink -----------------------------------------------------------
//
// Three axes, in the three colours every 3D tool has used since the first one:
// X warm, Y (up here) green, Z cool. They are the one place on the glass that
// is not the pack's palette, deliberately — a hand that has touched any other
// 3D application already knows what they mean, and inventing a house colour for
// "the X axis" would be a private joke at the user's expense.

export const AXIS_INK = { x: "#e05a52", y: "#79c85a", z: "#4f8fe2" };
export const AXES = ["x", "y", "z"];
export const UNIT = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };

/** Two unit vectors spanning the plane normal to `axis` — the ring's own frame. */
export function planeOf(axis) {
  const away = Math.abs(axis[1]) > 0.9 ? [1, 0, 0] : [0, 1, 0];
  const u = norm3(cross3(axis, away));
  return [u, norm3(cross3(axis, u))];
}

/** Shortest distance from a point to a polyline, in the polyline's own units. */
export function nearPolyline(pts, px, py) {
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

// ---- a staging, in time ----------------------------------------------------------
//
// The new bench stages a piece, not one shot: a set (`state.parseSets`) shared
// by the shots of its scene, and per shot a staging (`state.parseStaging`) of
// timed marks — the shot camera's, and each person's. What follows is that
// staging read at a moment: where the camera is, where everyone stands. The
// renderer above is untouched; it is handed the set as it stands at `t`.

/** The default shot camera: eye height, looking down the room. */
export const START_CAMERA = { x: 0, y: 1.6, z: -3.6, yaw: 0, pitch: -0.02, mm: 32 };

/**
 * The shot camera at `t` seconds. Catmull–Rom through the marks, the way the
 * old bench walked its path — over time rather than over the mark count, so a
 * mark sits at its moment. Marks evenly spread (every scene the old bench
 * saved) come out exactly on the old path.
 */
export function cameraAt(marks, t) {
  if (!marks?.length) return { ...START_CAMERA };
  if (marks.length === 1 || t <= marks[0].t) return { ...marks[0] };
  const last = marks.length - 1;
  if (t >= marks[last].t) return { ...marks[last] };
  let i = 0;
  while (i < last - 1 && marks[i + 1].t <= t) i++;
  const span = Math.max(1e-6, marks[i + 1].t - marks[i].t);
  const u = clamp((t - marks[i].t) / span, 0, 1), u2 = u * u, u3 = u2 * u;
  const m = (k) => marks[clamp(k, 0, last)];
  const p0 = m(i - 1), p1 = m(i), p2 = m(i + 1), p3 = m(i + 2);
  const out = { t };
  for (const key of ["x", "y", "z", "yaw", "pitch", "mm"]) {
    out[key] = 0.5 * ((2 * p1[key]) + (-p0[key] + p2[key]) * u
      + (2 * p0[key] - 5 * p1[key] + 4 * p2[key] - p3[key]) * u2
      + (-p0[key] + 3 * p1[key] - 3 * p2[key] + p3[key]) * u3);
  }
  return out;
}

const shortest = (a, b) => {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return d;
};

/** Where one person stands at `t`: straight from mark to mark, turning the
 *  short way round. Null where the shot gives them no marks. */
export function poseAt(marks, t) {
  if (!marks?.length) return null;
  if (marks.length === 1 || t <= marks[0].t) return { ...marks[0] };
  const last = marks[marks.length - 1];
  if (t >= last.t) return { ...last };
  let i = 0;
  while (marks[i + 1].t < t) i++;
  const a = marks[i], b = marks[i + 1];
  const u = (t - a.t) / Math.max(1e-6, b.t - a.t);
  const out = { t };
  for (const key of ["x", "y", "z"]) out[key] = a[key] + (b[key] - a[key]) * u;
  for (const key of ["rx", "ry", "rz"]) out[key] = a[key] + shortest(a[key], b[key]) * u;
  return out;
}

/** The set as it stands at `t` in a shot: everyone on their marks. */
export function stagedAt(set, staging, t) {
  return (set?.objects ?? []).map((piece) => {
    const at = piece.kind === "person" ? poseAt(staging?.people?.[piece.id], t) : null;
    return at ? { ...piece, x: at.x, y: at.y, z: at.z, rx: at.rx, ry: at.ry, rz: at.rz } : piece;
  });
}

/** The pixels a piece's guide is written at: the family's native canvas at the
 *  piece's ratio, snapped to its own grid. */
export function guideSize(timeline) {
  const rules = rulesFor(S.pieceFamily(timeline));
  const found = rules.aspects.find(([label]) => label === timeline.aspect);
  const [w, h] = resolveCanvas(found ? found[1] : (rules.aspects[0]?.[1] ?? 16 / 9),
                               rules.nativeShortEdge, rules);
  return { w, h };
}

/** The pixels a reference clip is written at: half the render's short edge, or
 *  all of it where the piece asks (`state.fullStagingClip`). */
export function referenceSize(timeline) {
  const { w, h } = guideSize(timeline);
  const scale = Math.min(1, timeline.short_edge / (S.fullStagingClip(timeline) ? 1 : 2) / Math.min(w, h));
  const snap = (edge) => Math.max(32, Math.round((edge * scale) / 32) * 32);
  return { w: snap(w), h: snap(h) };
}

/**
 * The words a staged shot sends: who stands where and how the camera moves,
 * from the bench's own sentences, at the first frame of the shot.
 */
export function stagingWords(timeline, index) {
  const segment = timeline.segments[index];
  const set = S.setOf(timeline, segment);
  if (!set || !segment.staging) return "";
  const marks = segment.staging.camera;
  const { w, h } = guideSize(timeline);
  const seconds = Number(segment.duration_s) || 0;
  const words = stagingSentence(stagedAt(set, segment.staging, 0), marks, seconds, cameraAt(marks, 0), { w, h },
                                { ends: stagedAt(set, segment.staging, seconds) });
  const clip = S.stagedClip(segment);
  if (clip?.role !== "reference") return words;
  return `The camera, framing and staging follow @${clip.handle}, a rough blockout of this shot. ${words}`.trim();
}

/**
 * What does not line up at a continuing join: the frames handed over come from
 * the previous shot's end, so a next shot whose first marks put the camera or a
 * person somewhere else has a guide that contradicts them (spec 3.3).
 *
 * -> null where it lines up (or there is no such join), else `{ camera, turn,
 * who: [{ piece, metres, posture }] }`: the camera's distance in metres and its
 * turn in degrees, and each person who moved or changed posture.
 */
export function joinGap(timeline, index) {
  const segment = timeline.segments[index];
  const before = timeline.segments[index - 1];
  if (!index || !before || !S.continues(segment) || S.merged(segment)) return null;
  if (!S.isStaged(timeline, segment) || !S.isStaged(timeline, before) || segment.set !== before.set) return null;
  const set = S.setOf(timeline, segment);
  const end = Number(before.duration_s) || 0;
  const a = cameraAt(before.staging.camera, end), b = cameraAt(segment.staging.camera, 0);
  const camera = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  let turn = Math.abs(((b.yaw - a.yaw + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI) * DEG;
  turn = Math.max(turn, Math.abs(b.pitch - a.pitch) * DEG);
  const left = stagedAt(set, before.staging, end), starts = stagedAt(set, segment.staging, 0);
  const who = [];
  for (const piece of starts) {
    if (piece.kind !== "person") continue;
    const was = left.find((other) => other.id === piece.id);
    const metres = Math.hypot(was.x - piece.x, was.z - piece.z, (was.y ?? 0) - (piece.y ?? 0));
    const posture = postureOf(was) !== postureOf(piece);
    if (metres >= 0.2 || posture) who.push({ piece, metres, posture });
  }
  if (camera < 0.2 && turn < 5 && Math.abs(a.mm - b.mm) < 2 && !who.length) return null;
  return { camera, turn, lens: Math.abs(a.mm - b.mm), who };
}

/**
 * Start shot `index` where shot `index - 1` ends: its first camera mark becomes
 * the camera the last shot stopped on, and everyone's first mark the mark they
 * stopped on. Later marks are left where they are. -> whether anything moved.
 */
export function lineUp(timeline, index) {
  const segment = timeline.segments[index];
  const before = timeline.segments[index - 1];
  if (!S.isStaged(timeline, before) || !segment?.staging) return false;
  const set = S.setOf(timeline, before);
  const end = Number(before.duration_s) || 0;
  const camera = cameraAt(before.staging.camera, end);
  segment.staging.camera = [{ ...camera, t: 0 }, ...segment.staging.camera.filter((mark) => mark.t > 0.14)];
  const left = stagedAt(set, before.staging, end);
  for (const piece of set.objects) {
    if (piece.kind !== "person") continue;
    const was = left.find((other) => other.id === piece.id);
    const rest = (segment.staging.people[piece.id] ?? []).filter((mark) => mark.t > 0.14);
    const moved = before.staging.people?.[piece.id]?.length || segment.staging.people[piece.id]?.length;
    if (!moved) continue;
    segment.staging.people[piece.id] = [{ t: 0, x: was.x, y: was.y ?? 0, z: was.z,
                                          rx: was.rx ?? 0, ry: was.ry ?? 0, rz: was.rz ?? 0 }, ...rest];
  }
  return true;
}

/** A staging continuing from shot `index - 1`'s end: same set, the camera
 *  where it stopped, everyone on their last marks (spec 3.2). Null where that
 *  shot has no staging. */
export function stagingFrom(timeline, index) {
  const before = timeline.segments[index - 1];
  if (!S.isStaged(timeline, before)) return null;
  const segment = { staging: { camera: [], people: {} } };
  const scratch = { ...timeline, segments: [before, segment] };
  lineUp(scratch, 1);
  return { set: before.set, staging: segment.staging };
}

/** Whether anyone changes posture or leaves the floor in shot `index`: what
 *  makes Loosely the better hold. */
export function postureChanges(timeline, index) {
  const segment = timeline.segments[index];
  const set = S.setOf(timeline, segment);
  if (!set || !segment.staging) return false;
  const start = stagedAt(set, segment.staging, 0);
  const end = stagedAt(set, segment.staging, Number(segment.duration_s) || 0);
  return start.some((piece, k) => piece.kind === "person"
    && (postureOf(piece) !== postureOf(end[k]) || (piece.y ?? 0) > 0.3 || (end[k].y ?? 0) > 0.3));
}

/** Bring every staged shot's words in line with its staging. -> changed. */
export function syncStagingWords(timeline) {
  let changed = false;
  timeline.segments.forEach((segment, index) => {
    if (!S.isStaged(timeline, segment)) return;
    const words = stagingWords(timeline, index);
    if ((segment.staging.words ?? "") === words) return;
    if (words) segment.staging.words = words; else delete segment.staging.words;
    changed = true;
  });
  return changed;
}

/** The shots the next render samples whose derived guide is not the one their
 *  staging calls for — what Shoot has to draw before it can queue. */
export function guidesWanted(timeline) {
  const { shoot } = S.shootPlan(timeline);
  const runs = S.passes(timeline);
  const out = [];
  for (const k of shoot) {
    for (let index = runs[k].start; index < runs[k].end; index++) {
      const segment = timeline.segments[index];
      if (!S.isStaged(timeline, segment)) continue;
      const name = S.stagedGuideName(timeline, index);
      const reference = S.stagesByReference(timeline);
      const guide = reference ? S.stagedClip(segment) : S.guideAsset(segment);
      if (!name) { if (S.stagedClip(segment)) out.push({ index, name: null }); continue; }
      const path = `${S.STAGED_GUIDE_DIR}/${name}.mp4`;
      if (guide?.filename !== path || guide.role !== (reference ? "reference" : "guide")
          || (!reference && Math.abs((guide.strength ?? 1) - S.stagingStrength(segment)) > 1e-6)) {
        out.push({ index, name, path });
      } else {
        out.push({ index, name, path, check: true });
      }
    }
  }
  return out;
}

/** One frame of a staged shot, drawn at `size` in `pass`, as a PNG blob. */
export function drawStaged(raster, canvas, context, set, staging, at, pass) {
  raster.raster(stagedAt(set, staging, at), cameraAt(staging.camera, at));
  raster.shade(context, pass);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error(t("a frame could not be encoded")))), "image/png");
  });
}

/**
 * Draw and attach the guide every staged shot in the next render calls for.
 *
 * The guide is derived, never a file the user manages: it is written under
 * the shot's staging stamp (`state.stagedGuideName`) and reused wherever the
 * stamp has not moved and the file is still there. A shot whose pass is None
 * loses a derived guide it had; one it was handed by hand is left alone only
 * while the shot is not staged. -> whether anything on the piece changed.
 *
 * `step(sentence)` is told what is happening, for the button that waits.
 */
export async function deriveGuides(timeline, { step = () => {} } = {}) {
  let changed = syncStagingWords(timeline);
  const wanted = guidesWanted(timeline);
  if (!wanted.length) return changed;
  const rules = rulesFor(S.pieceFamily(timeline));
  const { w, h } = S.stagesByReference(timeline) ? referenceSize(timeline) : guideSize(timeline);
  let raster = null, canvas = null, context = null;
  for (const { index, name, path, check } of wanted) {
    const segment = timeline.segments[index];
    if (!name) {
      segment.assets = segment.assets.filter((asset) => !S.isStagedGuide(asset));
      changed = true;
      continue;
    }
    if (check) {
      const answer = await probe(path).catch(() => ({}));
      if (!answer?.missing) continue;
    }
    if (!raster) {
      raster = new Raster(w, h);
      canvas = el("canvas");
      canvas.width = w;
      canvas.height = h;
      context = canvas.getContext("2d");
    }
    const set = S.setOf(timeline, segment);
    const pass = S.stagingPass(timeline, segment);
    const seconds = Number(segment.duration_s) || 1;
    const count = Math.max(2, framesForSeconds(seconds, rules));
    const token = crypto.getRandomValues(new Uint32Array(4))
      .reduce((hex, part) => hex + part.toString(16).padStart(8, "0"), "");
    let batch = [];
    for (let frame = 0; frame < count; frame++) {
      step(t("Drawing the guide for shot {n}, frame {f} of {count}…", { n: index + 1, f: frame + 1, count }));
      const at = (frame / (count - 1)) * seconds;
      batch.push({ index: frame, blob: await drawStaged(raster, canvas, context, set, segment.staging, at, pass) });
      if (batch.length >= BATCH || frame === count - 1) {
        await blockoutFrames(token, batch);
        batch = [];
      }
    }
    step(t("Writing the guide for shot {n}…", { n: index + 1 }));
    const written = await blockoutWrite({ token, fps: rules.fps, op: pass, name });
    if (S.stagesByReference(timeline)) S.attachStagedReference(segment, written.path);
    else {
      S.attachGuide(segment, timeline, {
        path: written.path, kind: "video", op: PASS_BY_ID[pass]?.opId ?? pass,
        strength: S.stagingStrength(segment),
      });
    }
    changed = true;
  }
  // The words cite the clip, which may only just have been given its handle.
  return syncStagingWords(timeline) || changed;
}

/**
 * Write one shot's guide as a file and say where it went: what *Write the
 * guide* does in a piece of one shot, and what a door is handed.
 *
 * Drawn from a copy taken before the first frame, so editing the set or the
 * staging while the frames are drawn and sent cannot mix two scenes into one
 * file. One camera mark (or `still`) writes a picture at the playhead through
 * core's upload; more write a clip along the path, with the scene beside it as
 * the old bench saved one, so it can be read back in (`state.sceneAsStaging`).
 *
 * -> `{ path, kind, op, opId, words }`.
 */
export async function writeGuide(timeline, index, { at = 0, still = false, step = () => {} } = {}) {
  const segment = timeline.segments[index];
  const set = structuredClone(S.setOf(timeline, segment));
  const staging = structuredClone(segment.staging);
  const passId = S.stagingPass(timeline, segment) === "none" ? "as_staged" : S.stagingPass(timeline, segment);
  const pass = PASS_BY_ID[passId];
  const seconds = Number(segment.duration_s) || 4;
  const words = stagingWords({ ...timeline, segments: [{ ...segment, set: set.id, staging }], sets: [set] }, 0);
  const { w, h } = guideSize(timeline);
  const raster = new Raster(w, h);
  const canvas = el("canvas");
  canvas.width = w;
  canvas.height = h;
  const context = canvas.getContext("2d");
  const meta = { op: t(pass.label), opId: pass.opId, words };
  if (still || staging.camera.length < 2) {
    step(t("Tracing the frame…"));
    const blob = await drawStaged(raster, canvas, context, set, staging, at, passId);
    const asset = await upload(new File([blob], `blockout-${passId}.png`, { type: "image/png" }), WRITES.slice(0, -1));
    return { path: asset.path, kind: "image", ...meta };
  }
  const rules = rulesFor(S.pieceFamily(timeline));
  const count = Math.max(2, framesForSeconds(seconds, rules));
  const token = crypto.getRandomValues(new Uint32Array(4))
    .reduce((hex, part) => hex + part.toString(16).padStart(8, "0"), "");
  let batch = [];
  for (let frame = 0; frame < count; frame++) {
    step(t("Drawing frame {n} of {count}…", { n: frame + 1, count }));
    batch.push({ index: frame, blob: await drawStaged(raster, canvas, context, set, staging, (frame / (count - 1)) * seconds, passId) });
    if (batch.length >= BATCH || frame === count - 1) {
      step(t("Sending frame {n} of {count}…", { n: frame + 1, count }));
      await blockoutFrames(token, batch);
      batch = [];
    }
  }
  step(t("Writing the clip…"));
  // The scene the old bench saved, so a set written here opens again there.
  const scene = {
    objects: set.objects.map(({ id, ...piece }) => piece),
    marks: staging.camera.map(({ t: _t, ...mark }) => mark),
    times: staging.camera.map((mark) => mark.t),
    people: staging.people, duration: seconds, aspect: timeline.aspect, pass: passId,
  };
  const written = await blockoutWrite({ token, fps: rules.fps, op: passId, scene });
  return { ...written, ...meta };
}

/** Every derived guide a piece points at — what the sweep keeps. */
export const stagedGuidesOf = (timeline) => (timeline?.segments ?? [])
  .flatMap((segment) => segment.assets ?? []).filter(S.isStagedGuide).map((asset) => asset.filename);
