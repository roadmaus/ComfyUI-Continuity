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
// same rail of stops, the same light box with a seam through it, the same foot
// that runs the job, the same doors the result leaves through. What differs is
// argued below, departure by departure.
//
// **There is no server preview.** The other benches answer a moving dial with a
// round trip because their answer needs the file or the model. This bench's
// answer needs neither: a scene is a few dozen boxes and a projection, which is
// arithmetic, and the pack already has a precedent for browser-side arithmetic
// in the contact sheet — no queue, no weights. The renderer below is a software
// rasterizer, a few hundred lines, no WebGL context to lose and nothing to
// vendor. It draws the light box live while the camera is dragged, and the run
// draws the same frames again at full size — one renderer, so what is on the
// glass is exactly what gets written.
//
// **There is one camera.** Every 3D tool has two — the one you fly around with
// and the one that renders — and reconciling them is what beginners never stop
// being confused by. Here the light box *is* the lens: you are always looking
// at what the guide will be. Getting around the set is therefore operating the
// camera, and each gesture is a word the model was trained on — drag pans and
// tilts, shift-drag trucks and pedestals, the wheel pushes in and pulls out.
// The foot narrates the move in exactly that vocabulary as the marks are set.
//
// **The path is marks, not curves.** No keyframe editor and no graph view: you
// frame the shot, you press Mark, you frame the next one, the way a camera
// department works a move out on a set. Each mark is the whole camera —
// position, pan, tilt, lens — and the clip eases through them in order over a
// duration set in seconds.
//
// **The seam compares the stage against the guide.** The left half is the set
// as you work it — clay, the floor grid, the selection — and the right half is
// the pass that will be written, with none of the staging aids on it. That
// holds even for As staged, where the two halves differ only by the aids: the
// comparison is what you are handling against what the file will hold.
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
import { openChoicePopover } from "./pills.js";
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

/** What each frame shape renders at. The preview draws smaller (see `Bench`);
 *  these are the run's, and they are the sizes the families sample near. */
const SHAPES = {
  "16:9": { w: 1280, h: 720, pw: 704, ph: 396 },
  "9:16": { w: 720, h: 1280, pw: 306, ph: 544 },
  "1:1": { w: 960, h: 960, pw: 480, ph: 480 },
};

// ---- the set -----------------------------------------------------------------
//
// Three shapes, and all of them are boxes: a block, a wall (wide and thin), a
// post (tall and thin). A figure used to be a fourth — a little box mannequin —
// and it went, because a guide does not need one: a block the height of a
// person reads as a person in a depth map, and the pack's Pose tracing is the
// tool for actual bodies. What matters here is masses and the move.

// Any piece can also carry an identity: `plays` is a cast member's handle and
// `word` is what to call it in prose. Neither changes a pixel of any pass —
// they exist for the staging sentence, and for the hue the stage side wears.
const KINDS = {
  block: { label: "Block", w: 1.2, h: 0.9, d: 0.8 },
  wall: { label: "Wall", w: 3.2, h: 2.6, d: 0.14 },
  post: { label: "Post", w: 0.16, h: 2.4, d: 0.16 },
};

/** The set a fresh bench opens on. Not empty: an empty viewport is a black
 *  rectangle with nothing to operate the camera against, and the first thing
 *  anybody does with a staged set is move its pieces — which is the tutorial. */
function defaultSet() {
  let id = 1;
  const piece = (kind, over) => ({ id: id++, kind, rot: 0, ...KINDS[kind], ...over });
  return [
    piece("wall", { x: -1.9, z: 7.4, rot: 0.06, w: 3.4 }),
    piece("wall", { x: 2.6, z: 7.9, rot: -0.1, w: 2.6 }),
    piece("block", { x: 0.45, z: 5.2, rot: -0.35, w: 0.5, h: 1.8, d: 0.4 }),
    piece("block", { x: -1.25, z: 4.3, rot: 0.25, w: 1.4, h: 0.85, d: 0.9 }),
    piece("post", { x: 1.95, z: 4.6 }),
    piece("post", { x: -2.6, z: 5.9 }),
  ];
}

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

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
const LIGHT = (() => {
  const v = [0.45, 0.8, -0.35];
  const l = Math.hypot(...v);
  return v.map((n) => n / l);
})();

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

  /** World triangles for one piece. A piece is a box; `rot` turns it on Y. */
  static tris(out, piece) {
    const { id, x, z, rot } = piece;
    const sx = piece.w / 2, sy = piece.h / 2, sz = piece.d / 2;
    const cy = x, cyy = sy, cz = z;   // the box sits on the floor
    const cr = Math.cos(rot), sr = Math.sin(rot);
    for (const face of FACES) {
      const wn = [face.n[0] * cr + face.n[2] * sr, face.n[1], -face.n[0] * sr + face.n[2] * cr];
      const lam = Math.max(0, wn[0] * LIGHT[0] + wn[1] * LIGHT[1] + wn[2] * LIGHT[2]);
      const lit = clamp(0.28 + 0.72 * lam, 0, 1);
      const p = face.q.map(([ux, uy, uz]) => {
        const lx = ux * sx, ly = uy * sy, lz = uz * sz;
        return [cy + lx * cr + lz * sr, cyy + ly, cz - lx * sr + lz * cr];
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
    const G = 60;
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
   * `seamX` splits the picture: left of it is the stage — clay, the grid, the
   * selection ring — and right of it is `pass`, with no staging aids. Pass -1
   * for no stage half at all, which is what the run uses: the file carries the
   * guide and only the guide.
   */
  shade(context, pass, { seamX = -1, selected = 0, tints = null } = {}) {
    const { w, h } = this;
    if (!this.image || this.image.width !== w || this.image.height !== h) {
      this.image = context.createImageData(w, h);
    }
    const data = this.image.data;
    const asStaged = pass === "as_staged";
    for (let y = 0; y < h; y++) {
      const row = y * w;
      for (let x = 0; x < w; x++) {
        const at = row + x;
        const id = this.id[at];
        const stage = x < seamX;
        let r, g, b;
        if (stage || asStaged) {
          // The clay. Shared by the stage half and the As staged pass; the
          // aids — grid, selection — only ever land on the stage half.
          if (id === SKY_ID) {
            const fade = 1 - y / h;
            r = 38 + 10 * fade; g = 40 + 10 * fade; b = 44 + 12 * fade;
          } else if (id === GROUND_ID) {
            const z = 1 / this.z[at];
            let base = 70;
            if (stage) {
              const gx = Math.abs(this.wx[at] - Math.round(this.wx[at]));
              const gz = Math.abs(this.wz[at] - Math.round(this.wz[at]));
              if (gx < 0.012 + z * 0.004 || gz < 0.012 + z * 0.004) {
                base += clamp(46 - z * 1.8, 0, 46);
              }
            }
            const fog = clamp(1 - z / 40, 0.4, 1);
            r = base * fog; g = (base + 1) * fog; b = (base + 3) * fog;
          } else {
            const l = this.lit[at] / 255;
            r = 70 + 112 * l; g = 68 + 108 * l; b = 64 + 102 * l;
            // The member's chip hue, worn as a wash on the clay — stage side
            // only, the way every staging aid is. The lambert stays underneath
            // so the piece keeps reading as a solid.
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
        } else if (pass === "depth") {
          if (id === SKY_ID) { r = g = b = 4; } else {
            const z = 1 / this.z[at];
            const v = Math.pow(clamp(1 - (z - DNEAR) / (DFAR - DNEAR), 0, 1), 1.3);
            r = g = b = Math.round(8 + v * 247);
          }
        } else if (pass === "blocks") {
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

  /** Whether this pixel touches a different piece — the selection ring. */
  edgeOf(at, x, y) {
    const id = this.id[at];
    return (x + 1 < this.w && this.id[at + 1] !== id)
        || (x > 0 && this.id[at - 1] !== id)
        || (y + 1 < this.h && this.id[at + this.w] !== id)
        || (y > 0 && this.id[at - this.w] !== id);
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
  const at = project(cam, [piece.x, piece.h / 2, piece.z], width, height);
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
    const at = project(last, [piece.x, piece.h / 2, piece.z], width, height);
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

const DEG = 180 / Math.PI;

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

    this.objects = defaultSet();
    this.nextId = this.objects.length + 1;
    this.cam = { x: 0.15, y: 1.6, z: -0.8, yaw: 0.03, pitch: -0.02, mm: 32 };
    // Two marks out of the box — a gentle push-in — so the path, the play
    // button and the sentence all have something true to say on arrival,
    // which is also how the bench teaches what a mark is.
    this.marks = [
      { x: 0.15, y: 1.6, z: -0.8, yaw: 0.03, pitch: -0.02, mm: 32 },
      { x: 0.24, y: 1.54, z: 0.6, yaw: -0.01, pitch: -0.01, mm: 32 },
    ];
    this.scrub = 0;
    this.duration = 4.0;
    this.shape = "16:9";
    this.pass = "depth";
    this.seam = 0.46;
    this.selected = 0;
    this.playing = false;
    this.busy = false;
    this.progress = null;   // a sentence for the run button while it works
    this.error = null;
    this.result = null;
    this.sentTo = new Set();
    this.sending = null;
    if (options.scene) this.restore(options.scene);
  }

  /** A saved set, back on the glass. Anything malformed keeps the default. */
  restore(scene) {
    try {
      if (Array.isArray(scene.objects) && scene.objects.length) {
        this.objects = scene.objects
          .filter((piece) => KINDS[piece.kind])
          .map((piece, index) => ({
            id: index + 1, kind: piece.kind, rot: Number(piece.rot) || 0,
            x: clamp(Number(piece.x) || 0, -30, 30), z: clamp(Number(piece.z) || 0, -30, 30),
            w: clamp(Number(piece.w) || KINDS[piece.kind].w, 0.1, 8),
            h: clamp(Number(piece.h) || KINDS[piece.kind].h, 0.1, 8),
            d: clamp(Number(piece.d) || KINDS[piece.kind].d, 0.1, 8),
            // Kept even when the handle is no longer on the shelf: the sentence
            // still cites it, and a stale citation is the user's to notice —
            // the same rule a prompt's own chips follow.
            plays: String(piece.plays ?? "").slice(0, 32),
            word: String(piece.word ?? "").slice(0, 48),
          }));
        this.nextId = this.objects.length + 1;
      }
      if (Array.isArray(scene.marks)) {
        this.marks = scene.marks.map((markAt) => ({
          x: Number(markAt.x) || 0, y: clamp(Number(markAt.y) || 1.6, 0.2, 12),
          z: Number(markAt.z) || 0, yaw: Number(markAt.yaw) || 0,
          pitch: clamp(Number(markAt.pitch) || 0, -1.35, 1.35),
          mm: clamp(Number(markAt.mm) || 32, 18, 85),
        }));
      }
      if (Number.isFinite(scene.duration)) this.duration = clamp(scene.duration, 1, 10);
      if (SHAPES[scene.shape]) this.shape = scene.shape;
      if (PASS_BY_ID[scene.pass]) this.pass = scene.pass;
      if (this.marks.length) Object.assign(this.cam, this.marks[0]);
    } catch {
      /* a broken sidecar opens the default set, which is the bench either way */
    }
  }

  /** What rides in the sidecar — enough to put all of this back, plus the one
   *  thing written for readers other than this bench: `layout`, each named
   *  piece's screen box at every mark. No family reads it today; the
   *  layout-grounded conditioning the research is converging on does, and the
   *  boxes cost nothing here where they would cost a tracker anywhere else. */
  scene() {
    const { w, h } = SHAPES[this.shape];
    const stops = this.marks.length ? this.marks : [this.cam];
    const layout = this.objects
      .filter((piece) => piece.plays || piece.word)
      .map((piece) => ({
        who: piece.plays || undefined, what: piece.word || undefined,
        boxes: stops.map((markAt) => this.screenBox(piece, markAt, w, h)),
      }));
    return {
      objects: this.objects.map(({ id, ...piece }) => piece),
      marks: this.marks.map((markAt) => ({ ...markAt })),
      duration: this.duration, shape: this.shape, pass: this.pass,
      layout: layout.length ? layout : undefined,
    };
  }

  /** A piece's bounding box on a mark's frame, normalised — or null when the
   *  whole of it is behind the lens. Clamped to the frame, so a box is what a
   *  reader could actually ground against the written pixels. */
  screenBox(piece, cam, width, height) {
    const cr = Math.cos(piece.rot), sr = Math.sin(piece.rot);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, seen = false;
    for (const ux of [-1, 1]) for (const uy of [0, 1]) for (const uz of [-1, 1]) {
      const lx = (ux * piece.w) / 2, lz = (uz * piece.d) / 2;
      const at = project(cam,
        [piece.x + lx * cr + lz * sr, uy * piece.h, piece.z - lx * sr + lz * cr],
        width, height);
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

    this.setShape(this.shape, { first: true });
    this.render();
    this.watchBox();
    this.paint();
  }

  close() {
    if (open === this) open = null;
    this.stopPlay();
    this.watcher?.disconnect();
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

  paintBench() {
    this.stops.replaceChildren(
      this.section(t("Set"), [
        el("div", { class: "mmc-bo-adds" }, Object.entries(KINDS).map(([kind, spec]) =>
          el("button", {
            class: "mmc-bn-verb", onclick: () => this.addPiece(kind),
          }, [el("span", { text: t(spec.label) })]))),
        this.piecePanel(),
        el("p", { class: "mmc-bn-note", text:
          t("Drag a piece to move it on the floor; drag anywhere else and you are operating the camera.") }),
      ]),
      this.section(t("Camera"), [
        this.dial(t("Lens"), this.cam.mm, 18, 85, 1, (value) => {
          this.cam.mm = value;
          this.markStale();
          this.paint();
        }, (value) => `${Math.round(value)} mm`),
        el("div", { class: "mmc-bn-dial" }, [
          el("div", { class: "mmc-bn-diallabel" }, [
            el("span", { text: t("Frame") }),
          ]),
          el("div", { class: "mmc-bn-opts" }, Object.keys(SHAPES).map((shape) =>
            el("button", {
              class: `mmc-bn-opt${shape === this.shape ? " on" : ""}`,
              "aria-pressed": shape === this.shape,
              onclick: () => this.setShape(shape),
            }, [el("span", { text: shape })]))),
        ]),
        el("p", { class: "mmc-bn-note",
          title: t("Press for the rest"),
          onclick: (event) => event.currentTarget.classList.toggle("open"),
          text: t("You are looking through the lens — there is no second camera. "
            + "Drag pans and tilts, shift-drag trucks and pedestals, the wheel "
            + "pushes in and pulls out.") }),
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

  /** The selected piece's dials, or nothing. In the rail because that is where
   *  dials live; which piece they aim at is the click on the glass. */
  piecePanel() {
    const piece = this.objects.find((candidate) => candidate.id === this.selected);
    if (!piece) return null;
    const metres = (value) => `${value.toFixed(2)} m`;
    const redial = (key) => (value) => { piece[key] = value; this.paint(); };
    return el("div", { class: "mmc-bo-piece" }, [
      el("div", { class: "mmc-bo-piecename" }, [
        el("span", { text: t(KINDS[piece.kind].label) }),
        el("span", { class: "mmc-bn-gap" }),
        el("button", {
          class: "mmc-bo-remove", text: t("Remove"),
          onclick: () => {
            this.objects = this.objects.filter((candidate) => candidate !== piece);
            this.selected = 0;
            this.paintBench();
            this.paint();
          },
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
      this.dial(t("Width"), piece.w, 0.1, 8, 0.05, redial("w"), metres),
      this.dial(t("Height"), piece.h, 0.1, 8, 0.05, redial("h"), metres),
      this.dial(t("Depth"), piece.d, 0.1, 8, 0.05, redial("d"), metres),
      this.dial(t("Turn"), piece.rot * DEG, -180, 180, 1,
        (value) => { piece.rot = value / DEG; this.paint(); },
        (value) => `${Math.round(value)}°`),
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
      el("span", { text: t("Mark {n}", { n: index + 1 }) }),
      el("span", { class: "mmc-bo-markwhen", text: formatSeconds(when) }),
      el("button", {
        class: "mmc-bo-remove", text: "✕", title: t("Drop this mark"),
        onclick: () => {
          this.marks.splice(index, 1);
          this.markStale();
          this.paintBench();
          this.paintCut();
          this.paintFoot();
        },
      }),
    ]);
  }

  addPiece(kind) {
    const ahead = forwardOf(this.cam);
    const piece = {
      id: this.nextId++, kind, rot: 0, ...KINDS[kind],
      x: clamp(this.cam.x + ahead[0] * 4.5, -30, 30),
      z: clamp(this.cam.z + ahead[2] * 4.5, -30, 30),
    };
    this.objects.push(piece);
    this.selected = piece.id;
    this.paintBench();
    this.paint();
  }

  setPass(id) {
    this.pass = id;
    this.markStale();
    this.paintBench();
    this.paintBox();
    this.paint();
  }

  setShape(shape, { first = false } = {}) {
    this.shape = shape;
    const { pw, ph } = SHAPES[shape];
    this.canvas.width = pw;
    this.canvas.height = ph;
    this.raster = new Raster(pw, ph);
    this.markStale();
    if (!first) {
      this.paintBench();
      this.fit();
      this.paint();
    }
  }

  setDuration(seconds) {
    this.duration = clamp(Math.round(seconds * 2) / 2, 1, 10);
    this.markStale();
    this.paintBench();
    this.paintFoot();
  }

  /** A change under a written result: what the file holds is no longer what
   *  the glass says, so the doors close until the next run. Same rule as a
   *  dial on the tracing bench. */
  markStale() {
    if (!this.result) return;
    this.result = null;
    this.sentTo.clear();
    this.paintFoot();
  }

  // ---- the light box ---------------------------------------------------------

  paintBox() {
    this.seamEl = el("div", { class: "mmc-bn-seam" }, [
      el("span", { class: "mmc-bn-grip" }, [icon("swap", 14)]),
    ]);
    this.frame.replaceChildren(
      this.canvas, this.seamEl,
      el("span", { class: "mmc-bn-tag left", text: t("Stage") }),
      el("span", { class: "mmc-bn-tag right", text: t(this.passOf().label) }),
    );
    this.frame.onpointerdown = (event) => this.press(event);
    this.frame.onwheel = (event) => this.dolly(event);
    this.frame.ondragstart = (event) => event.preventDefault();
    this.paintSeam();
    this.fit();
  }

  paintSeam() {
    this.frame.style.setProperty("--mmc-seam", `${(this.seam * 100).toFixed(2)}%`);
  }

  fit() {
    const { pw, ph } = SHAPES[this.shape];
    const room = this.box.getBoundingClientRect();
    if (!room.width || !room.height) return;
    const scale = Math.min(room.width / pw, room.height / ph);
    this.frame.style.width = `${Math.round(pw * scale)}px`;
    this.frame.style.height = `${Math.round(ph * scale)}px`;
  }

  watchBox() {
    this.watcher?.disconnect();
    this.watcher = new ResizeObserver(() => this.fit());
    this.watcher.observe(this.box);
  }

  /** Everything the glass shows, batched to a frame. */
  paint() {
    if (this.painting) return;
    this.painting = true;
    requestAnimationFrame(() => {
      this.painting = false;
      if (!this.overlay.isConnected) return;
      const seamX = Math.round(this.seam * this.raster.w);
      const tints = {};
      for (const piece of this.objects) {
        if (piece.plays) tints[piece.id] = tagRGB(tagIndex(piece.plays));
      }
      this.raster.raster(this.objects, this.cam);
      this.raster.shade(this.context, this.pass, {
        seamX, selected: this.selected, tints,
      });
      this.paintNames(seamX);
      this.paintSay();
    });
  }

  /** Each named piece's name, floated over it — stage side only, like every
   *  other aid. A handle wears its hue; a word is quiet. Drawn after the
   *  buffer lands because it is ink over the picture, not part of it. */
  paintNames(seamX) {
    const context = this.context;
    const size = Math.max(9, Math.round(this.raster.w * 0.017));
    context.font = `600 ${size}px system-ui, sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "bottom";
    for (const piece of this.objects) {
      if (!piece.plays && !piece.word) continue;
      const at = project(this.cam, [piece.x, piece.h + 0.12, piece.z],
                         this.raster.w, this.raster.h);
      if (!at || at.x < 8 || at.x > seamX - 8 || at.y < size || at.y > this.raster.h) continue;
      const said = piece.plays ? `@${piece.plays}` : piece.word;
      context.lineWidth = 3;
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

  // ---- the pointer, and which of three things a press is ---------------------
  //
  // One surface, three controls, and the rule that sorts them is spatial: a
  // press within reach of the seam drags the seam; a press on a piece selects
  // it and drags it across the floor; a press on anything else — ground, sky,
  // a piece that stays where it is put — operates the camera. Shift always
  // operates the camera, because shift-drag *is* one of its moves.

  glassPoint(event) {
    const rect = this.frame.getBoundingClientRect();
    return {
      rect,
      px: clamp(((event.clientX - rect.left) / rect.width) * this.raster.w, 0, this.raster.w - 1),
      py: clamp(((event.clientY - rect.top) / rect.height) * this.raster.h, 0, this.raster.h - 1),
    };
  }

  press(event) {
    event.preventDefault();
    this.stopPlay();
    const { rect, px, py } = this.glassPoint(event);
    const nearSeam = Math.abs((event.clientX - rect.left) - this.seam * rect.width) < 10;
    let move;
    if (nearSeam) {
      move = (at) => {
        this.seam = clamp((at.clientX - rect.left) / rect.width, 0, 1);
        this.paintSeam();
        this.paint();
      };
      move(event);
    } else {
      const id = this.raster.id[Math.floor(py) * this.raster.w + Math.floor(px)];
      const piece = this.objects.find((candidate) => candidate.id === id);
      if (piece && !event.shiftKey) {
        this.selected = piece.id;
        this.paintBench();
        const grab = this.floorPoint(px, py);
        const held = grab ? { x: grab.x - piece.x, z: grab.z - piece.z } : null;
        move = (at) => {
          if (!held) return;
          const point = this.glassPoint(at);
          const floor = this.floorPoint(point.px, point.py);
          if (!floor) return;
          piece.x = clamp(floor.x - held.x, -30, 30);
          piece.z = clamp(floor.z - held.z, -30, 30);
          this.markStale();
          this.paint();
        };
      } else {
        if (!piece) { this.selected = 0; this.paintBench(); }
        let last = { x: event.clientX, y: event.clientY };
        move = (at) => {
          const dx = at.clientX - last.x, dy = at.clientY - last.y;
          last = { x: at.clientX, y: at.clientY };
          if (at.shiftKey || event.shiftKey) {
            const right = rightOf(this.cam);
            this.cam.x += right[0] * dx * 0.012;
            this.cam.z += right[2] * dx * 0.012;
            this.cam.y = clamp(this.cam.y - dy * 0.012, 0.2, 12);
          } else {
            this.cam.yaw += dx * 0.0038;
            this.cam.pitch = clamp(this.cam.pitch - dy * 0.0032, -1.35, 1.35);
          }
          this.markStale();
          this.paintSay();
          this.paint();
        };
      }
      this.paint();
    }
    // Guarded: a pointer can be gone by the time this runs — a pen lifted
    // mid-press, a test harness's synthetic event — and a capture that failed
    // only costs the drag following off the element, not the press itself.
    try { this.frame.setPointerCapture(event.pointerId); } catch { /* see above */ }
    const up = () => {
      this.frame.removeEventListener("pointermove", move);
      this.frame.removeEventListener("pointerup", up);
      this.frame.removeEventListener("pointercancel", up);
    };
    this.frame.addEventListener("pointermove", move);
    this.frame.addEventListener("pointerup", up);
    this.frame.addEventListener("pointercancel", up);
  }

  /** Where a glass pixel's ray meets the floor, or null when it never does. */
  floorPoint(px, py) {
    const ray = this.raster.ray(px, py, this.cam);
    if (ray[1] >= -0.001) return null;
    const along = -this.cam.y / ray[1];
    return { x: this.cam.x + ray[0] * along, z: this.cam.z + ray[2] * along };
  }

  dolly(event) {
    event.preventDefault();
    this.stopPlay();
    const ahead = forwardOf(this.cam);
    const step = (event.deltaY < 0 ? 1 : -1) * 0.35;
    this.cam.x += ahead[0] * step;
    this.cam.z += ahead[2] * step;
    this.cam.y = clamp(this.cam.y + ahead[1] * step, 0.2, 12);
    this.markStale();
    this.paintSay();
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
        class: "mmc-bo-markbtn", onclick: () => this.setMark(),
      }, [el("span", { class: "mmc-bo-markdot" }), el("span", { text: t("Mark this frame") })]),
    );
    this.paintPlayhead();
  }

  paintPlayhead() {
    if (this.playhead) this.playhead.style.left = `${this.scrub * 100}%`;
  }

  applyPath(at) {
    if (this.marks.length < 2) return;
    this.scrub = clamp(at, 0, 1);
    Object.assign(this.cam, pathCam(this.marks, this.scrub));
    this.paintPlayhead();
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
    this.marks.push({ ...this.cam });
    this.scrub = 1;
    this.markStale();
    this.paintBench();
    this.paintCut();
    this.paintFoot();
  }

  togglePlay() {
    if (this.playing) return this.stopPlay();
    if (this.marks.length < 2) return;
    this.playing = true;
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
    this.playBtn?.replaceChildren(icon("play", 13));
  }

  // ---- the foot, the run, the doors ------------------------------------------

  /** The whole of the prose — staging and move — as the bench stands now. */
  said() {
    return stagingSentence(this.objects, this.marks, this.duration, this.cam,
                           { w: this.raster.w, h: this.raster.h });
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
      const { w, h } = SHAPES[this.shape];
      // The set, as it stands at the press. The run yields to the page between
      // frames — that is what keeps the room responsive — so without this a
      // piece dragged mid-render would change sets halfway through the clip.
      const staged = this.objects.map((piece) => ({ ...piece }));
      const still = this.marks.length < 2;
      if (still) {
        step(t("Tracing the frame…"));
        const blob = await this.drawFull(w, h, this.cam, staged);
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
        const { w, h } = SHAPES[this.shape];
        const blob = await this.drawFull(w, h, this.cam);
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
