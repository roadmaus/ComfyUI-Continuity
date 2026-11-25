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
// position, pan, tilt, lens — and the clip goes through them in order over a
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
import { modelTriangles, MODELS } from "./setmodels.js";
import { frameRatio, measureFrame } from "./framesize.js";
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
    id: "labelled", opId: "as_shot", label: "Labelled",
    note: "The stage as you see it: the clay, the cast in their colours, and "
        + "every named piece with its name drawn into the frame. For a family "
        + "that is shown the blockout as a reference video, so the picture "
        + "itself says who and what each block is.",
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
export const BIG = 60;
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
        { kind: "block", x: 0, z: 2.75, w: 1.6, h: 0.74, d: 0.75, word: "table", model: "table" },
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
        { kind: "block", x: 1.7, z: 4.8, w: 0.5, h: 3.6, d: 1.2, ry: -Math.PI / 2, word: "lamp post", model: "streetlamp" },
        { kind: "person", x: -1.3, z: 5.4, w: 0.5, h: 1.75, d: 0.4 },
        { kind: "block", x: 2.9, z: 7.2, w: 1.9, h: 1.35, d: 4.1, ry: 0.1, word: "parked car", model: "car" },
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
    this.part = new Uint8Array(count);      // which part of a model; 0 for a box
    this.wx = new Float32Array(count);      // world x/z, ground pixels only —
    this.wz = new Float32Array(count);      // what the grid is drawn from
    this.image = null;                      // made against a 2d context on demand
  }

  /** World triangles for one piece: a box on its own three turns, or the model
   *  it looks like, filling that box. */
  static tris(out, piece) {
    const { id } = piece;
    const m = basisOf(piece);
    const [ox, oy, oz] = centreOf(piece);
    const hx = piece.w / 2, hy = piece.h / 2, hz = piece.d / 2;
    const model = modelTriangles(piece);
    if (model) {
      for (const tri of model) {
        const v = tri.v.map(([ux, uy, uz]) => {
          const at = applyM(m, [ux * hx, uy * hy, uz * hz]);
          return [ox + at[0], oy + at[1], oz + at[2]];
        });
        const [a, b, c] = v;
        // Wound like the boxes below: the cross of two edges points inward.
        const n = norm3(cross3([c[0] - a[0], c[1] - a[1], c[2] - a[2]], [b[0] - a[0], b[1] - a[1], b[2] - a[2]]));
        out.push({ id, part: tri.part, lit: clamp(0.28 + 0.72 * Math.max(0, dot3(n, LIGHT)), 0, 1), v });
      }
      return;
    }
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
    this.part.fill(0);
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
        const piecePart = tri.part ?? 0;
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
            this.part[at] = piecePart;
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
   * `as_staged` (and `labelled`, which keeps the cast's hues), plus the aids — the floor grid, the selection ring, the cast
   * tints. The aids exist only in `"stage"`, which is why the run can call this
   * with a pass id and be certain the file carries the guide and only the guide.
   */
  shade(context, mode, { selected = 0, tints = null, plan = 0 } = {}) {
    const { w, h } = this;
    if (!this.image || this.image.width !== w || this.image.height !== h) {
      this.image = context.createImageData(w, h);
    }
    const data = this.image.data;
    const stage = mode === "stage";
    const clay = stage || mode === "as_staged" || mode === "labelled";
    const tinted = stage || mode === "labelled";
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
            // A plan is looked at from far above through a long lens: it is lit
            // as a floor a few metres off, and its grid is ruled by the pixel.
            const z = plan ? 6 : 1 / this.z[at];
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
              const near = plan ? plan * 0.8 : 0.009 + z * 0.0022;
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
            const haze = plan ? 1 : clamp(1 - (1 / this.z[at]) / 60, 0.58, 1);
            r = (70 + 112 * l) * haze; g = (68 + 108 * l) * haze; b = (64 + 102 * l) * haze;
            // The member's chip hue, worn as a wash on the clay — stage only,
            // the way every staging aid is. The lambert stays underneath so the
            // piece keeps reading as a solid.
            const tint = tinted && tints ? tints[id] : null;
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
      // Inside a model, where one part meets another and where a face turns.
      if (this.part[at] && (this.part[next] !== this.part[at] || Math.abs(this.lit[next] - this.lit[at]) > 40)) return true;
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
  return { words: `${third} ${band}`, to: `${third.replace(/^at (?=frame)/, "").replace(/^at /, "the ")} ${band}`, depth: at.z };
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

// ---- size, in words ----------------------------------------------------------------
//
// The depth pass shows a person four metres tall; the words have to say so too,
// or the model is handed a giant and told about somebody ordinary. Only what is
// well off its usual size is mentioned: a child or a sofa a little long is not.

/** What a piece is usually: a person's own height, a model's own size. Null for
 *  a plain block, which has no usual size to be off. */
export function usualSize(piece) {
  if (piece?.kind === "person") return { ...S.SET_KINDS.person };
  const model = MODELS.get(piece?.model);
  return model ? { w: model.w, h: model.h, d: model.d } : null;
}

/** How much bigger than usual a piece is: a person by height, a model by all
 *  three at once. 1 for a plain block. */
export function sizeRatio(piece) {
  const usual = usualSize(piece);
  if (!usual) return 1;
  if (piece.kind === "person") return piece.h / usual.h;
  return Math.cbrt((piece.w / usual.w) * (piece.h / usual.h) * (piece.d / usual.d));
}

const metresSaid = (m) => (m < 1 ? t("{n} cm", { n: Math.round(m * 100) }) : t("{n} m", { n: Math.round(m * 10) / 10 }));

/** A person well off their usual height, as words: "towering at 4.4 m",
 *  "tiny, 30 cm tall". "" when they are near enough ordinary. */
export function personSize(piece) {
  if (piece?.kind !== "person") return "";
  const ratio = sizeRatio(piece);
  if (ratio >= 1.5) return t("towering at {m}", { m: metresSaid(piece.h) });
  if (ratio <= 0.45) return t("tiny, {m} tall", { m: metresSaid(piece.h) });
  return "";
}

/** What the staging sentence says of a piece's size, or "". */
export const sizeSaid = (piece) => personSize(piece) || thingSize(piece);

/** A model well off its usual size, as the word before its name. */
function thingSize(piece) {
  if (piece?.kind === "person" || !usualSize(piece)) return "";
  const ratio = sizeRatio(piece);
  return ratio >= 2.5 ? t("giant") : ratio >= 1.6 ? t("huge") : ratio <= 0.4 ? t("tiny") : ratio <= 0.62 ? t("small") : "";
}

/** Who or what a clause is about, with its size where that is worth saying.
 *  A handle comes back without its @, for the templates that add one. */
function whoSaid(piece) {
  if (piece.plays) {
    const size = personSize(piece);
    return size ? `${piece.plays}, ${size},` : piece.plays;
  }
  const size = thingSize(piece);
  return articled(size ? `${size} ${piece.word}` : piece.word);
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

/** How far somebody goes over their marks and how fast, or null for somebody
 *  who stays put. The pace is over the legs they move in: a wait is not part
 *  of a walk. */
function walkOf(marks) {
  let metres = 0, seconds = 0;
  for (let k = 1; k < (marks?.length ?? 0); k++) {
    const far = Math.hypot(marks[k].x - marks[k - 1].x, (marks[k].y ?? 0) - (marks[k - 1].y ?? 0), marks[k].z - marks[k - 1].z);
    if (far < 0.05) continue;
    metres += far;
    seconds += marks[k].t - marks[k - 1].t;
  }
  return metres < 0.5 ? null : { pace: metres / Math.max(0.1, seconds), last: marks[marks.length - 1] };
}

/** Somebody who moves in the shot: how, from where and to where in the frame.
 *  "" for somebody never in it. */
function walkClause(piece, end, walk, from, to, cam) {
  if (!from && !to) return "";
  const who = piece.plays ? `@${whoSaid(piece)}` : whoSaid(piece);
  const posture = postureOf(piece);
  const how = piece.kind !== "person" ? (walk.pace > 5 ? t("moves fast") : walk.pace < 0.5 ? t("moves slowly") : t("moves"))
    : posture || postureOf(end) ? t("moves")
    : walk.pace > 3.2 ? t("runs") : walk.pace > 2 ? t("jogs") : walk.pace < 0.5 ? t("walks slowly") : t("walks");
  if (!from) return t("{who} {how} into frame, to {to}", { who, how, to: to.to });
  const start = posture ? t("{who} is {posture} {place} and", { who, posture, place: from.words })
    : t("{who} starts {place} and", { who, place: from.words });
  if (!to) return t("{start} {how} out of frame", { start, how });
  if (from.words !== to.words) return t("{start} {how} to {to}", { start, how, to: to.to });
  // The same corner of the frame at both ends: which way, rather than where.
  const right = rightOf(cam), ahead = flatForwardOf(cam);
  const dx = (end.x - piece.x) * right[0] + (end.z - piece.z) * right[2];
  const dz = (end.x - piece.x) * ahead[0] + (end.z - piece.z) * ahead[2];
  const way = Math.hypot(dx, dz) < 0.5 ? t("about")
    : Math.abs(dz) > Math.abs(dx) ? (dz < 0 ? t("toward the camera") : t("away from the camera"))
      : dx > 0 ? t("to the right") : t("to the left");
  return t("{start} {how} {way}", { start, how, way });
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
export function stagingSentence(objects, marks, duration, cam, size = { w: 16, h: 9 }, options = {}) {
  const told = stagingClauses(objects, marks, duration, cam, size, options);
  const move = told.find((clause) => clause.id === "camera")?.text ?? "";
  const clauses = told.filter((clause) => clause.id !== "camera").map((clause) => clause.text);
  if (!clauses.length) return move;
  const staging = clauses.join("; ") + ".";
  return `${staging.charAt(0).toUpperCase()}${staging.slice(1)}${move ? ` ${move}` : ""}`;
}

/**
 * The same prose in its parts, each with the piece it is about: `[{ id, text }]`,
 * the camera's sentence last under the id `"camera"`. What the bench lights up
 * on the stage when a clause is pointed at; `stagingSentence` joins them.
 */
export function stagingClauses(objects, marks, duration, cam, size = { w: 16, h: 9 }, { withMove = true, ends = null, people = null, keeping = "", shake = null } = {}) {
  const first = marks.length ? marks[0] : cam;
  const clauses = [];
  const say = (piece, text) => clauses.push({ id: piece.id, text });
  const entering = [];
  const placed = [];
  const walkers = [];
  for (const piece of objects) {
    if (!piece.plays && !piece.word) continue;
    const here = placeOf(piece, first, size.w, size.h);
    const walk = walkOf(people?.[piece.id]);
    if (walk) {
      walkers.push({ piece, walk, here });
      continue;
    }
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
    say(piece, piece.plays
      ? (posture ? t("@{who} is {posture} {place}", { who: whoSaid(piece), posture, place: here.words })
                 : t("@{who} stands {place}", { who: whoSaid(piece), place: here.words }))
      : posture ? t("{what}, {posture}, {place}", { what: whoSaid(piece), posture, place: here.words })
        : t("{what} {place}", { what: whoSaid(piece), place: here.words }));
  }
  const lastCam = marks.length ? marks[marks.length - 1] : cam;
  for (const { piece, walk, here } of walkers) {
    const end = ends?.find((other) => other.id === piece.id) ?? { ...piece, ...walk.last };
    const clause = walkClause(piece, end, walk, here, placeOf(end, lastCam, size.w, size.h), lastCam);
    if (clause) say(piece, clause);
  }
  // A change of posture within the shot, said once at the end: "@anna ends
  // standing". `ends` is the set as it stands at the shot's last frame.
  for (const end of ends ?? []) {
    const start = objects.find((piece) => piece.id === end.id);
    if (!start || (!end.plays && !end.word)) continue;
    const was = postureOf(start), now = postureOf(end);
    if (was === now) continue;
    const who = end.plays ? `@${end.plays}` : articled(end.word);
    say(end, t("{who} ends {posture}", { who, posture: now || (end.kind === "person" ? t("standing") : t("upright")) }));
  }
  for (const piece of entering) {
    say(piece, t("@{who} comes into frame as the camera moves", { who: piece.plays }));
  }
  if (withMove) clauses.push({ id: "camera", text: moveSentence(marks, duration, moveTarget(ends ?? objects, marks, cam, size.w, size.h), { keeping, shake }) });
  return clauses;
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

// The bench says the same move to whoever is working it in everyday words
// (`plain`): nobody should need to know what a truck is to read their own shot.

/** How far one camera is from another, in the units a move's size is judged in. */
const travelOf = (a, b) => Math.hypot((b.x - a.x) / 1.75, b.y - a.y, (b.z - a.z) / 1.75,
  ((b.yaw - a.yaw) * DEG) / 25, ((b.pitch - a.pitch) * DEG) / 25, (b.mm - a.mm) / 30);

/** What the camera does between two marks, strongest first: `{ mag, words }`. */
function movesBetween(a, b, target, plain) {
  const right = rightOf(a), ahead = flatForwardOf(a);
  const dx = (b.x - a.x) * right[0] + (b.z - a.z) * right[2];
  const dz = (b.x - a.x) * ahead[0] + (b.z - a.z) * ahead[2];
  const dy = b.y - a.y;
  const dyaw = b.yaw - a.yaw, dpitch = b.pitch - a.pitch, dmm = b.mm - a.mm;
  const say = (film, everyday) => (plain ? everyday : film);
  const moves = [];
  // An arc is sideways travel with the pan fighting it — the camera keeps
  // looking at what it is circling. Named as one move, not two.
  if (Math.abs(dx) > 0.6 && Math.abs(dyaw * DEG) > 8 && Math.sign(dyaw) !== Math.sign(dx)) {
    // Around whom is geometry's answer where there is one: the cast member the
    // last frame holds at its centre. "The subject" is the honest fallback.
    const around = target ? `@${target}` : t("the subject");
    moves.push({ mag: Math.abs(dx) / 1.5,
                 words: dx > 0 ? say(t("arcs right around {who}", { who: around }), t("circles to the right around {who}", { who: around }))
                               : say(t("arcs left around {who}", { who: around }), t("circles to the left around {who}", { who: around })) });
  } else {
    if (Math.abs(dx) > 0.25) moves.push({ mag: Math.abs(dx) / 1.5,
      words: dx > 0 ? say(t("trucks right"), t("moves right")) : say(t("trucks left"), t("moves left")) });
    if (Math.abs(dyaw * DEG) > 5) moves.push({ mag: Math.abs(dyaw * DEG) / 25,
      words: dyaw > 0 ? say(t("pans right"), t("turns right")) : say(t("pans left"), t("turns left")) });
  }
  if (Math.abs(dz) > 0.3) {
    moves.push({ mag: Math.abs(dz) / 2,
                 words: dz > 0
                   ? (target ? say(t("pushes in toward @{who}", { who: target }), t("moves closer to @{who}", { who: target }))
                             : say(t("pushes in"), t("moves forward")))
                   : say(t("pulls out"), t("moves back")) });
  }
  if (Math.abs(dy) > 0.25) moves.push({ mag: Math.abs(dy),
    words: dy > 0 ? say(t("pedestals up"), t("rises")) : say(t("pedestals down"), t("sinks")) });
  if (Math.abs(dpitch * DEG) > 5) moves.push({ mag: Math.abs(dpitch * DEG) / 25,
    words: dpitch > 0 ? say(t("tilts up"), t("looks up")) : say(t("tilts down"), t("looks down")) });
  if (Math.abs(dmm) > 6) moves.push({ mag: Math.abs(dmm) / 30, words: dmm > 0 ? t("zooms in") : t("zooms out") });
  return moves.sort((p, q) => q.mag - p.mag);
}

const SHAKE_WORDS = {
  barely: { film: "handheld with a barely perceptible sway", plain: "barely shaking" },
  hand: { film: "handheld with a natural sway", plain: "held in hand" },
  walking: { film: "handheld, bobbing with each walking step", plain: "shaking with someone's steps" },
  running: { film: "handheld, shaking hard with each running step", plain: "shaking as someone runs" },
};

export function moveSentence(marks, duration, target = null, { plain = false, keeping = "", shake = null } = {}) {
  const how = SHAKE_WORDS[shake?.kind];
  const held = (!keeping ? "" : plain ? t(", always looking at {who}", { who: keeping }) : t(", keeping {who} in frame", { who: keeping }))
    + (how ? `, ${t(plain ? how.plain : how.film)}` : "") + ".";
  // A shaken camera is not a static one, wherever it stays.
  const still = (plain ? (how ? t("The camera stays in place") : t("The camera stays still"))
    : how ? t("The camera stays in place") : t("The camera holds a static shot")) + held;
  if (!marks || marks.length < 2) return still;
  const a = marks[0], b = marks[marks.length - 1];
  // A camera that goes somewhere and comes back has no move from end to end.
  // It is told in two, out to the mark farthest from the start and on from it.
  let path = 0, seconds = 0, timed = true, turn = a;
  for (let k = 1; k < marks.length; k++) {
    const leg = travelOf(marks[k - 1], marks[k]);
    path += leg;
    if (marks[k].t === undefined) timed = false;
    else if (leg > 0.02) seconds += marks[k].t - marks[k - 1].t;
    if (travelOf(a, marks[k]) > travelOf(a, turn)) turn = marks[k];
  }
  const doubles = turn !== b && path > 1.5 * travelOf(a, b) + 0.3;
  const parts = (doubles ? [movesBetween(a, turn, null, plain), movesBetween(turn, b, target, plain)]
    : [movesBetween(a, b, target, plain)]).filter((moves) => moves.length);
  if (!parts.length) return still;
  // The two strongest, because a prompt should name the move and not inventory
  // it: "pushes in and pedestals up" is a move, five clauses is a flight plan.
  const said = parts.map((moves) => moves.slice(0, 2).map((m) => m.words).join(` ${t("and")} `));
  const mag = Math.max(...parts.map((moves) => moves[0].mag));
  const far = parts.reduce((sum, moves) => sum + moves[0].mag, 0);
  const rate = far / Math.max(0.1, timed && seconds ? seconds : Math.max(0.5, duration));
  let sentence = t("The camera {moves}", { moves: said.join(t(", then ")) });
  if (plain) {
    if (rate > 0.55) sentence += " " + t("quickly"); else if (rate < 0.1) sentence += " " + t("slowly");
    return sentence + held;
  }
  const amp = mag > 1.7 ? t("large") : mag < 0.42 ? t("small") : "";
  const speed = rate > 0.55 ? t("fast") : rate < 0.1 ? t("slow") : "";
  if (amp) sentence += " " + t("with {amp} amplitude", { amp });
  if (speed) sentence += " " + t("at {speed} speed", { speed });
  return sentence + held;
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

/** The slope of one value at mark `k`: the two legs' slopes blended by how long
 *  each takes, or none where it stops or turns back. A hold therefore holds,
 *  and an evenly paced run keeps its pace through every mark. */
function slopeAt(times, values, k) {
  const leg = (at) => (values[at + 1] - values[at]) / Math.max(1e-6, times[at + 1] - times[at]);
  const last = times.length - 1;
  if (k === 0) return leg(0);
  if (k === last) return leg(last - 1);
  const before = leg(k - 1), after = leg(k);
  if (before * after <= 0) return 0;
  const h0 = times[k] - times[k - 1], h1 = times[k + 1] - times[k];
  const w0 = 2 * h1 + h0, w1 = h1 + 2 * h0;
  return (w0 + w1) / (w0 / before + w1 / after);
}

/** One value through its marks at `t`, within leg `i`: a cubic over real time,
 *  so a mark sits at its moment and nothing overshoots one. */
function through(times, values, i, t) {
  const span = Math.max(1e-6, times[i + 1] - times[i]);
  const u = clamp((t - times[i]) / span, 0, 1), u2 = u * u, u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * values[i] + (u3 - 2 * u2 + u) * span * slopeAt(times, values, i)
    + (-2 * u3 + 3 * u2) * values[i + 1] + (u3 - u2) * span * slopeAt(times, values, i + 1);
}

/** Whether a mark's curve was shaped by hand: bent, or made a corner. */
export const shapedMark = (mark) => Boolean(mark.bend || mark.corner);
const shapedLeg = (marks, i) => shapedMark(marks[i]) || shapedMark(marks[i + 1]);

/** How far mark `k`'s curve reaches on the side of leg `i`, as an offset from
 *  the mark: a third of the curve's own slope there. */
export function reachAt(marks, k, i) {
  const mark = marks[k];
  const sign = k === i ? 1 : -1;
  const out = {};
  for (const key of ["x", "y", "z"]) {
    if (mark.corner) out[key] = (sign * ((marks[i + 1][key] ?? 0) - (marks[i][key] ?? 0))) / 3;
    else if (mark.bend) out[key] = sign * mark.bend[key];
    else {
      const span = marks[i + 1].t - marks[i].t;
      out[key] = (sign * span * slopeAt(marks.map((m) => m.t), marks.map((m) => m[key] ?? 0), k)) / 3;
    }
  }
  return out;
}

/** Where leg `i` has got to at `t`: through its marks, or along the curve they
 *  were bent into. */
function placeOn(marks, i, t) {
  const out = {};
  if (!shapedLeg(marks, i)) {
    const times = marks.map((mark) => mark.t);
    for (const key of ["x", "y", "z"]) out[key] = through(times, marks.map((mark) => mark[key] ?? 0), i, t);
    return out;
  }
  const a = marks[i], b = marks[i + 1];
  const u = clamp((t - a.t) / Math.max(1e-6, b.t - a.t), 0, 1), v = 1 - u;
  const p = reachAt(marks, i, i), q = reachAt(marks, i + 1, i);
  for (const key of ["x", "y", "z"]) {
    const from = a[key] ?? 0, to = b[key] ?? 0;
    out[key] = v * v * v * from + 3 * v * v * u * (from + p[key]) + 3 * v * u * u * (to + q[key]) + u * u * u * to;
  }
  return out;
}

/** The fastest a stretch may be left or arrived at, as a multiple of its
 *  average. Past three the progress below could run backwards. */
export const MOST_PACE = 3;

/** How far apart two readings are: in metres, or in degrees turned. */
const apart = (a, b, unit) => (unit === "m"
  ? Math.hypot(b.x - a.x, (b.y ?? 0) - (a.y ?? 0), b.z - a.z)
  : Math.hypot((b.yaw ?? 0) - (a.yaw ?? 0), (b.pitch ?? 0) - (a.pitch ?? 0)) * DEG);
export const legSpeed = (a, b, seconds, unit) => apart(a, b, unit) / seconds;

const LEG_STEPS = 64;

/** The length of leg `i` so far, at even steps of its own parameter. */
function legLengths(marks, i, unit) {
  const times = marks.map((mark) => mark.t);
  const span = times[i + 1] - times[i];
  const turns = unit === "m" ? null : ["yaw", "pitch"].map((key) => [key, marks.map((mark) => mark[key] ?? 0)]);
  const lengths = [0];
  let last = null;
  for (let k = 0; k <= LEG_STEPS; k++) {
    const when = times[i] + (span * k) / LEG_STEPS;
    const at = turns ? Object.fromEntries(turns.map(([key, values]) => [key, through(times, values, i, when)])) : placeOn(marks, i, when);
    if (last) lengths.push(lengths[k - 1] + apart(last, at, unit));
    last = at;
  }
  return lengths;
}

/** What a leg's length is measured in: metres, unless it only turns. */
const unitOfLeg = (marks, i) => (apart(marks[i], marks[i + 1], "m") > 0.02 ? "m" : "deg");

/** How far leg `i` goes. */
export const strideOf = (marks, i, unit) => legLengths(marks, i, unit)[LEG_STEPS];

/** The speeds leg `i` is left and arrived at with, as multiples of its average:
 *  the ones its marks were given, or the ones it has by itself. */
export function legEnds(marks, i, lengths = legLengths(marks, i, unitOfLeg(marks, i))) {
  const total = lengths[LEG_STEPS];
  if (total < 1e-6) return [marks[i].out ?? 1, marks[i + 1].in ?? 1];
  // A bent leg's slope is its shape. Its speed is the one its marks would have
  // had unbent, or where the mark itself was bent, that of the legs either side.
  if (shapedLeg(marks, i)) {
    const span = marks[i + 1].t - marks[i].t;
    const average = total / Math.max(1e-6, span);
    const speed = (k) => {
      const other = k === i ? i - 1 : i + 1;
      if (other < 0 || other > marks.length - 2) return 1;
      const times = marks.map((mark) => mark.t);
      if (!shapedMark(marks[k])) {
        return Math.hypot(...["x", "y", "z"].map((key) => slopeAt(times, marks.map((mark) => mark[key] ?? 0), k))) / average;
      }
      const beside = strideOf(marks, other, "m") / Math.max(1e-6, marks[other + 1].t - marks[other].t);
      return beside < 1e-6 ? 0 : (2 * beside) / (average + beside);
    };
    return [marks[i].out ?? clamp(speed(i), 0, MOST_PACE), marks[i + 1].in ?? clamp(speed(i + 1), 0, MOST_PACE)];
  }
  // The end slope of a cubic, from its first two steps.
  const slope = (one, two) => clamp((LEG_STEPS * (4 * one - two)) / (2 * total), 0, MOST_PACE);
  return [
    marks[i].out ?? slope(lengths[1], lengths[2]),
    marks[i + 1].in ?? slope(total - lengths[LEG_STEPS - 1], total - lengths[LEG_STEPS - 2]),
  ];
}

/** The moment leg `i`'s curve is read at for `t`: `t` itself, unless the leg was
 *  given a pace. Then distance along the curve follows a cubic whose end slopes
 *  are the pace, so the shape of the path has no say in the speed. */
function pacedTime(marks, i, t) {
  if (marks[i].out === undefined && marks[i + 1].in === undefined && !shapedLeg(marks, i)) return t;
  const span = marks[i + 1].t - marks[i].t;
  if (span < 1e-6) return t;
  const lengths = legLengths(marks, i, unitOfLeg(marks, i));
  const [out, into] = legEnds(marks, i, lengths);
  const u = clamp((t - marks[i].t) / span, 0, 1), u2 = u * u, u3 = u2 * u;
  const done = clamp((u3 - 2 * u2 + u) * out + (3 * u2 - 2 * u3) + (u3 - u2) * into, 0, 1);
  const total = lengths[LEG_STEPS];
  if (total < 1e-6) return marks[i].t + span * done;
  let k = 0;
  while (k < LEG_STEPS - 1 && lengths[k + 1] < done * total) k++;
  const step = lengths[k + 1] - lengths[k];
  const along = (k + (step > 1e-9 ? clamp((done * total - lengths[k]) / step, 0, 1) : 0)) / LEG_STEPS;
  return marks[i].t + span * along;
}

/** A mark as a moment: where it is, without how it is arrived at, left or bent. */
const momentOf = ({ in: _in, out: _out, bend: _bend, corner: _corner, ...mark }) => mark;

/** The leg `t` falls in. `t` is inside the marks. */
function legAt(marks, t) {
  let i = 0;
  while (i < marks.length - 2 && marks[i + 1].t <= t) i++;
  return i;
}

/**
 * The shot camera at `t` seconds, through its marks at a steady pace: it is
 * already moving on the first frame and still moving on the last.
 */
export function cameraAt(marks, t) {
  if (!marks?.length) return { ...START_CAMERA };
  if (marks.length === 1 || t <= marks[0].t) return momentOf(marks[0]);
  const last = marks[marks.length - 1];
  if (t >= last.t) return momentOf(last);
  const i = legAt(marks, t);
  const times = marks.map((mark) => mark.t);
  const when = pacedTime(marks, i, t);
  const out = { t, ...placeOn(marks, i, when) };
  for (const key of ["yaw", "pitch", "mm"]) out[key] = through(times, marks.map((mark) => mark[key]), i, when);
  return out;
}

const shortest = (a, b) => {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return d;
};

/** How long somebody setting off takes to turn the way they walk, at most. */
const TURN_SECONDS = 0.4;

/** The way something facing along `(dx, dz)` is turned, or the same a quarter
 *  turn off for a thing longer across than deep: a car drives lengthways. Of
 *  the two ends it could lead with, the one nearer `now`. */
export function facingOf(piece, dx, dz, now = 0) {
  const ahead = Math.atan2(dx, dz);
  // A person and a model have a front; a box goes whichever end first.
  const fronted = piece.kind === "person" || Boolean(piece.model);
  if (fronted || piece.w <= piece.d) {
    return fronted || Math.abs(shortest(ahead, now)) <= Math.PI / 2 ? ahead : shortest(0, ahead + Math.PI);
  }
  const side = shortest(0, ahead - Math.PI / 2);
  return Math.abs(shortest(side, now)) <= Math.PI / 2 ? side : shortest(0, side + Math.PI);
}

/** Where something stands at `t`: along the curve through its marks, turning
 *  the short way round. Somebody whose mark faces the way they go keeps facing
 *  along the path, turning as they set off; any other turn is spread over the
 *  leg, as it was placed. Null where the shot gives it no marks. */
export function poseAt(marks, t, piece = { kind: "person" }) {
  if (!marks?.length) return null;
  if (marks.length === 1 || t <= marks[0].t) return momentOf(marks[0]);
  const last = marks[marks.length - 1];
  if (t >= last.t) return momentOf(last);
  const i = legAt(marks, t);
  const a = marks[i], b = marks[i + 1];
  const span = Math.max(1e-6, b.t - a.t);
  const when = pacedTime(marks, i, t);
  const u = (when - a.t) / span;
  const out = { t, ...placeOn(marks, i, when) };
  for (const key of ["rx", "rz"]) out[key] = (a[key] ?? 0) + shortest(a[key] ?? 0, b[key] ?? 0) * u;
  const from = a.ry ?? 0, to = b.ry ?? 0;
  if (!facesAlong(marks, i, piece)) {
    out.ry = from + shortest(from, to) * u;
    return out;
  }
  const turning = Math.min(TURN_SECONDS, span / 2);
  const ahead = headingAt(marks, i, when, piece, to);
  const set = from + shortest(from, ahead) * Math.min(1, (t - a.t) / turning);
  out.ry = set + shortest(set, to) * Math.max(0, 1 - (b.t - t) / turning);
  return out;
}

/** The way something on leg `i` faces where the curve has got to at `when`. */
function headingAt(marks, i, when, piece, now) {
  const step = (marks[i + 1].t - marks[i].t) / 50;
  const p = placeOn(marks, i, Math.max(marks[i].t, when - step)), q = placeOn(marks, i, Math.min(marks[i + 1].t, when + step));
  if (Math.hypot(q.x - p.x, q.z - p.z) < 1e-3) return facingOf(piece, marks[i + 1].x - marks[i].x, marks[i + 1].z - marks[i].z, now);
  return facingOf(piece, q.x - p.x, q.z - p.z, now);
}

/** Whether whoever walks leg `i` faces the way they go: their mark says so,
 *  by the line between the two marks or by the curve they arrive on. */
export function facesAlong(marks, i, piece) {
  const a = marks[i], b = marks[i + 1];
  if (strideOf(marks, i, "m") <= 0.3) return false;
  const to = b.ry ?? 0;
  const near = (angle) => Math.abs(shortest(angle, to)) < 0.35;
  return (Math.hypot(b.x - a.x, b.z - a.z) > 0.3 && near(facingOf(piece, b.x - a.x, b.z - a.z, to)))
    || near(headingAt(marks, i, b.t, piece, to));
}

/** Face mark `k` the way its leg arrives there. */
export function faceArrival(marks, k, piece) {
  if (k > 0 && strideOf(marks, k - 1, "m") > 0.3) marks[k].ry = headingAt(marks, k - 1, marks[k].t, piece, marks[k].ry ?? 0);
}

/** The set as it stands at `t` in a shot: everything on its marks. */
export function stagedAt(set, staging, t) {
  return (set?.objects ?? []).map((piece) => {
    const at = poseAt(staging?.people?.[piece.id], t, piece);
    return at ? { ...piece, x: at.x, y: at.y, z: at.z, rx: at.rx, ry: at.ry, rz: at.rz } : piece;
  });
}

/** Where the camera looks on a piece: a person's face, or the middle of a thing. */
function lookPoint(piece) {
  const at = centreOf(piece);
  if (piece.kind !== "person") return at;
  const up = applyM(basisOf(piece), [0, piece.h * 0.35, 0]);
  return [at[0] + up[0], at[1] + up[1], at[2] + up[2]];
}

/** The shot camera at `t`, turned to what the shot keeps looking at. */
export function lensAt(set, staging, t) {
  const cam = cameraAt(staging?.camera ?? [], t);
  const piece = staging?.look ? stagedAt(set, staging, t).find((candidate) => candidate.id === staging.look) : null;
  if (!piece) return cam;
  const at = lookPoint(piece);
  const dx = at[0] - cam.x, dy = at[1] - cam.y, dz = at[2] - cam.z;
  const flat = Math.hypot(dx, dz);
  // Straight over or under it there is no telling which way to face.
  if (flat < 0.05) return cam;
  return { ...cam, yaw: cam.yaw + shortest(cam.yaw, Math.atan2(dx, dz)), pitch: clamp(Math.atan2(dy, flat), -1.5, 1.5) };
}

// ---- a camera held by somebody -----------------------------------------------------
//
// Laid over the path and never part of it: a join, a mark and a sentence read
// the path, and only a frame that is drawn is shaken. It is made of a seed and
// the time, so the same shot shakes the same way however often it is drawn.

/** What each shake does: degrees turned, metres carried, how often a second,
 *  and the steps of whoever is carrying it. */
const SHAKE_FEEL = {
  barely: { turn: 0.25, drift: 0.006, often: 0.45 },
  hand: { turn: 0.75, drift: 0.015, often: 0.8 },
  walking: { turn: 0.8, drift: 0.015, often: 0.9, steps: 1.8, bob: 0.03, nod: 0.35 },
  running: { turn: 1.6, drift: 0.03, often: 1.5, steps: 2.8, bob: 0.07, nod: 0.9 },
};

/** A smooth wander between -1 and 1 over time, its own for each seed and channel. */
function wander(seed, channel, time) {
  const at = (n) => {
    let h = Math.imul(seed + 1, 0x9e3779b1) ^ Math.imul(channel + 1, 0x85ebca6b) ^ Math.imul(n, 0xc2b2ae35);
    h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d);
    h = Math.imul(h ^ (h >>> 12), 0x297a2d39);
    return ((h ^ (h >>> 15)) >>> 0) / 0x7fffffff - 1;
  };
  const one = (x) => {
    const n = Math.floor(x), f = x - n;
    return at(n) + (at(n + 1) - at(n)) * f * f * f * (f * (f * 6 - 15) + 10);
  };
  return (one(time) + 0.45 * one(time * 2.3 + 17.5)) / 1.45;
}

/** One shake at a moment: turned, and carried along the camera's right and up. */
function shakeAt(shake, seed, time) {
  if (!shake) return [0, 0, 0, 0];
  const feel = SHAKE_FEEL[shake.kind], k = shake.amount;
  const x = time * feel.often * 2 * shake.rate;
  const step = time * (feel.steps ?? 0) * shake.rate * 2 * Math.PI;
  return [
    (wander(seed, 0, x) * feel.turn * k) / DEG,
    ((wander(seed, 1, x) * feel.turn * 0.8 + Math.sin(step + 0.8) * (feel.nod ?? 0)) * k) / DEG,
    (wander(seed, 2, x) * feel.drift + Math.sin(step / 2) * (feel.bob ?? 0) * 0.6) * k,
    (wander(seed, 3, x) * feel.drift - Math.cos(step) * (feel.bob ?? 0)) * k,
  ];
}

/** How long a shot takes to come out of the shake it continues from. */
const SHAKE_HANDOVER = 0.5;

/** The shot camera as the frame at `t` is drawn: `lensAt`, shaken. `run` is
 *  `state.shakeRun`'s. */
export function filmAt(set, staging, t, run) {
  const cam = lensAt(set, staging, t);
  if (!run) return cam;
  let by = shakeAt(run.shake, run.seed, run.from + t);
  if (run.before && t < SHAKE_HANDOVER) {
    const was = shakeAt(run.before, run.seed, run.from + t);
    by = by.map((value, k) => was[k] + (value - was[k]) * (t / SHAKE_HANDOVER));
  }
  const right = rightOf(cam), up = upOf(cam);
  return { ...cam, yaw: cam.yaw + by[0], pitch: clamp(cam.pitch + by[1], -1.5, 1.5),
    x: cam.x + right[0] * by[2] + up[0] * by[3], y: cam.y + right[1] * by[2] + up[1] * by[3], z: cam.z + right[2] * by[2] + up[2] * by[3] };
}

/** The camera's marks as it is really turned: what the sentences read. A camera
 *  following somebody turns even where it has nothing but its first mark. */
export function aimedMarks(set, staging, seconds) {
  const marks = staging?.camera ?? [];
  if (!staging?.look || !marks.length) return marks;
  const times = [...new Set([0, ...marks.map((mark) => mark.t), seconds])].filter((at) => at <= seconds).sort((a, b) => a - b);
  const out = [];
  for (const at of times) {
    const cam = { ...lensAt(set, staging, at), t: at };
    const before = out[out.length - 1];
    if (before) cam.yaw = before.yaw + shortest(before.yaw, cam.yaw);
    out.push(cam);
  }
  return out;
}

/** What the camera keeps looking at, as the sentences name it. */
export function lookName(set, staging) {
  const piece = staging?.look ? set?.objects.find((candidate) => candidate.id === staging.look) : null;
  if (!piece) return "";
  return piece.plays ? `@${piece.plays}` : piece.word ? t("the {word}", { word: piece.word }) : t("the subject");
}

/** The sentence a staged shot's camera and people make, read as a whole. */
export function stagedSentence(set, staging, seconds, size, { withMove = true } = {}) {
  return stagingSentence(stagedAt(set, staging, 0), aimedMarks(set, staging, seconds), seconds, lensAt(set, staging, 0), size,
    { withMove, ends: stagedAt(set, staging, seconds), people: staging.people, keeping: lookName(set, staging), shake: staging.shake ?? null });
}

/** `stagedSentence` in its parts: `[{ id, text }]`, the camera's last. */
export function stagedClauses(set, staging, seconds, size) {
  return stagingClauses(stagedAt(set, staging, 0), aimedMarks(set, staging, seconds), seconds, lensAt(set, staging, 0), size,
    { ends: stagedAt(set, staging, seconds), people: staging.people, keeping: lookName(set, staging), shake: staging.shake ?? null });
}

/** The pixels a piece's guide is written at: the family's native canvas at the
 *  piece's ratio, snapped to its own grid. */
export function guideSize(timeline) {
  const rules = rulesFor(S.pieceFamily(timeline));
  // The render's own ratio, a still's or a clip's where the frame is taken from
  // one, so what is framed on the stage is what renders.
  const [w, h] = resolveCanvas(frameRatio(timeline, rules), rules.nativeShortEdge, rules);
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
  const { w, h } = guideSize(timeline);
  const seconds = Number(segment.duration_s) || 0;
  // "own": the shot's prose says the scene, and the bench adds nothing about it.
  const words = S.stagingSay(timeline, segment) === "own" ? "" : stagedSentence(set, segment.staging, seconds, { w, h });
  const cite = clipCite(timeline, segment);
  return cite ? `${cite} ${words}`.trim() : words;
}

/** The one line that points the model at a staged shot's reference clip, or ""
 *  where the shot has none. A clip is only followed where the words name it, so
 *  this stays even when the bench writes nothing else. A labelled clip's tags
 *  are said to be labels, so they are read and not painted. */
export function clipCite(timeline, segment) {
  const clip = S.stagedClip(segment);
  if (clip?.role !== "reference") return "";
  const follow = `The camera, framing and staging follow @${clip.handle}, a rough blockout of this shot.`;
  return S.stagingPass(timeline, segment) === "labelled"
    ? `${follow} Its colours and name tags only say who and what each block is: they are not part of the picture.`
    : follow;
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
  const a = lensAt(set, before.staging, end), b = lensAt(set, segment.staging, 0);
  const camera = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  let turn = Math.abs(((b.yaw - a.yaw + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI) * DEG;
  turn = Math.max(turn, Math.abs(b.pitch - a.pitch) * DEG);
  const left = stagedAt(set, before.staging, end), starts = stagedAt(set, segment.staging, 0);
  const who = [];
  for (const piece of starts) {
    if (piece.kind !== "person" && !before.staging.people?.[piece.id] && !segment.staging.people?.[piece.id]) continue;
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
  const camera = lensAt(set, before.staging, end);
  // Where it starts changes; how it sets off is this shot's own.
  const leaving = (marks) => Object.fromEntries(["out", "bend", "corner"]
    .filter((key) => marks?.[0]?.[key] !== undefined).map((key) => [key, marks[0][key]]));
  segment.staging.camera = [{ ...camera, ...leaving(segment.staging.camera), t: 0 }, ...segment.staging.camera.filter((mark) => mark.t > 0.14)];
  const left = stagedAt(set, before.staging, end);
  for (const piece of set.objects) {
    if (piece.kind !== "person" && !before.staging.people?.[piece.id] && !segment.staging.people?.[piece.id]) continue;
    const was = left.find((other) => other.id === piece.id);
    const rest = (segment.staging.people[piece.id] ?? []).filter((mark) => mark.t > 0.14);
    const moved = before.staging.people?.[piece.id]?.length || segment.staging.people[piece.id]?.length;
    if (!moved) continue;
    segment.staging.people[piece.id] = [{ t: 0, x: was.x, y: was.y ?? 0, z: was.z,
                                          rx: was.rx ?? 0, ry: was.ry ?? 0, rz: was.rz ?? 0,
                                          ...leaving(segment.staging.people[piece.id]) }, ...rest];
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
  if (before.staging.shake) segment.staging.shake = { ...before.staging.shake };
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

/** The hue each piece playing somebody wears, by piece id: the member's chip hue. */
export function castTints(objects) {
  const tints = {};
  for (const piece of objects) if (piece.plays) tints[piece.id] = tagRGB(S.tagIndex(piece.plays));
  return tints;
}

/** What a labelled frame calls a piece: the handle as the prose spells it less
 *  its @, or the word it was given. "" for a piece with neither. */
export const tagOf = (piece) => piece.plays || piece.word || "";

/**
 * The name tags of a labelled frame, drawn into it: over each named piece, far
 * ones first so a near one's tag lies on top. A cast member's is their hue with
 * dark letters, a thing's dark with light ones. Sized by the frame, not the
 * screen: this is part of the file.
 */
export function drawLabels(context, cam, objects, width, height) {
  const size = Math.max(10, Math.round(width / 46));
  context.save();
  context.font = `600 ${size}px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  const tags = [];
  for (const piece of objects) {
    const text = tagOf(piece);
    if (!text) continue;
    const top = Math.max(...cornersOf(piece).map((corner) => corner[1]));
    const at = project(cam, [piece.x, top + 0.12, piece.z], width, height);
    if (!at || at.x < 0 || at.x > width || at.y < -size || at.y > height) continue;
    tags.push({ piece, text, at });
  }
  tags.sort((a, b) => b.at.z - a.at.z);
  for (const { piece, text, at } of tags) {
    const wide = Math.round(context.measureText(text).width + size * 0.9), tall = Math.round(size * 1.55);
    const x = Math.round(clamp(at.x - wide / 2, 0, width - wide)), y = Math.round(clamp(at.y - tall, 0, height - tall));
    const hue = piece.plays ? tagRGB(S.tagIndex(piece.plays)) : null;
    context.fillStyle = hue ? `rgb(${hue[0]},${hue[1]},${hue[2]})` : "rgb(14,15,17)";
    context.fillRect(x, y, wide, tall);
    context.fillStyle = hue ? "rgb(14,15,17)" : "rgb(240,237,231)";
    context.fillText(text, x + wide / 2, y + tall / 2 + 1);
  }
  context.restore();
}

/** One frame in a pass, as the file holds it: the set as it stands, through a
 *  camera. The one place a pass is drawn, for the file, the glass and a card. */
export function paintPass(raster, context, pass, objects, cam) {
  raster.raster(objects, cam);
  if (pass !== "labelled") { raster.shade(context, pass); return; }
  raster.shade(context, "labelled", { tints: castTints(objects) });
  drawLabels(context, cam, objects, raster.w, raster.h);
}

/** One frame of a staged shot, drawn at `size` in `pass`, as a PNG blob. */
export function drawStaged(raster, canvas, context, set, staging, at, pass, run = null) {
  paintPass(raster, context, pass, stagedAt(set, staging, at), filmAt(set, staging, at, run));
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
  // A frame taken from a still is that still's shape, which a look at it tells.
  await measureFrame(timeline);
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
    const run = S.shakeRun(timeline, index);
    const seconds = Number(segment.duration_s) || 1;
    const count = Math.max(2, framesForSeconds(seconds, rules));
    const token = crypto.getRandomValues(new Uint32Array(4))
      .reduce((hex, part) => hex + part.toString(16).padStart(8, "0"), "");
    let batch = [];
    for (let frame = 0; frame < count; frame++) {
      step(t("Drawing the guide for shot {n}, frame {f} of {count}…", { n: index + 1, f: frame + 1, count }));
      const at = (frame / (count - 1)) * seconds;
      batch.push({ index: frame, blob: await drawStaged(raster, canvas, context, set, segment.staging, at, pass, run) });
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
  const run = structuredClone(S.shakeRun(timeline, index));
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
    const blob = await drawStaged(raster, canvas, context, set, staging, at, passId, run);
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
    batch.push({ index: frame, blob: await drawStaged(raster, canvas, context, set, staging, (frame / (count - 1)) * seconds, passId, run) });
    if (batch.length >= BATCH || frame === count - 1) {
      step(t("Sending frame {n} of {count}…", { n: frame + 1, count }));
      await blockoutFrames(token, batch);
      batch = [];
    }
  }
  step(t("Writing the clip…"));
  // The scene the old bench saved, so a set written here opens again there.
  const scene = {
    objects: set.objects,
    marks: staging.camera.map(({ t: _t, ...mark }) => mark),
    times: staging.camera.map((mark) => mark.t),
    people: staging.people, ...(staging.look ? { look: staging.look } : {}),
    ...(staging.shake ? { shake: staging.shake } : {}), duration: seconds, aspect: timeline.aspect, pass: passId,
  };
  const written = await blockoutWrite({ token, fps: rules.fps, op: passId, scene });
  return { ...written, ...meta };
}

/** Every derived guide a piece points at — what the sweep keeps. */
export const stagedGuidesOf = (timeline) => (timeline?.segments ?? [])
  .flatMap((segment) => segment.assets ?? []).filter(S.isStagedGuide).map((asset) => asset.filename);
