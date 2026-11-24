"""The scene library: whole sets to start a shot from.

    python3 tests/test_blockout_scenes.py

Every scene is laid out by hand, in metres, so this checks what a hand gets
wrong: a model that is not on the shelf, a value the set would clamp, two
pieces standing in each other, and someone the scene is about who is out of the
camera's sight.

Runs the real modules under the packed stubs. Skips itself if node is not
installed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout
from harness import check, passed

layout.skip_without_node()

SCRIPT = """
const S = await import("./web/creator/state.js");
const B = await import("./web/creator/blockout.js");
const { MODELS } = await import("./web/creator/setmodels.js");
const { SCENE_GROUPS, SCENES } = await import("./web/creator/setscenes.js");
const out = { count: SCENES.size, groups: SCENE_GROUPS.length, ids: new Set([...SCENES.keys(), ...B.PRESETS.map((p) => p.id)]).size === SCENES.size + B.PRESETS.length, bad: [], seen: {} };

/** A piece's footprint, as its four corners on the floor, and its height range. */
const extent = (piece) => {
  const corners = B.cornersOf(piece);
  const ys = corners.map((c) => c[1]);
  return { corners, y: [Math.min(...ys), Math.max(...ys)] };
};
/** Whether two convex outlines on the floor overlap by more than `slack`. */
function overlaps(a, b, slack = 0.03) {
  for (const shape of [a, b]) {
    for (let k = 0; k < shape.length; k++) {
      const [x0, z0] = shape[k], [x1, z1] = shape[(k + 1) % shape.length];
      const axis = [z1 - z0, x0 - x1], len = Math.hypot(...axis) || 1;
      const along = (pts) => pts.map(([x, z]) => (x * axis[0] + z * axis[1]) / len);
      const pa = along(a), pb = along(b);
      if (Math.min(Math.max(...pa), Math.max(...pb)) - Math.max(Math.min(...pa), Math.min(...pb)) <= slack) return false;
    }
  }
  return true;
}
/** The floor outline of a piece: its eight corners' hull, which for an upright
 *  box is its four, and for one laid down is the box it lies in. */
const outline = (piece) => {
  const pts = extent(piece).corners.map(([x, , z]) => [x, z]);
  const xs = pts.map((p) => p[0]), zs = pts.map((p) => p[1]);
  if ((piece.rx ?? 0) || (piece.rz ?? 0)) return [[Math.min(...xs), Math.min(...zs)], [Math.max(...xs), Math.min(...zs)], [Math.max(...xs), Math.max(...zs)], [Math.min(...xs), Math.max(...zs)]];
  // Upright: the top four corners, wound round.
  const top = extent(piece).corners.filter((_, k) => k % 4 >= 2).map(([x, , z]) => [x, z]);
  return [top[0], top[1], top[3], top[2]];
};

for (const scene of SCENES.values()) {
  const made = scene.make();
  const read = S.sceneAsStaging({ ...made, duration: 4 }, { id: "s1", name: scene.label });
  const pieces = read.set.objects;
  if (pieces.length !== made.objects.length) out.bad.push([scene.id, "dropped a piece"]);
  if (pieces.length > 120) out.bad.push([scene.id, "too many pieces", pieces.length]);
  if (read.staging.camera.length < 2) out.bad.push([scene.id, "no move"]);
  pieces.forEach((piece, k) => {
    const raw = made.objects[k];
    if (raw.model && !MODELS.has(raw.model)) out.bad.push([scene.id, "no such model", raw.model]);
    for (const key of ["x", "y", "z", "w", "h", "d", "ry", "rx", "rz"]) {
      if (Math.abs((raw[key] ?? (key === "y" || key[0] === "r" ? 0 : piece[key])) - piece[key]) > 1e-9) out.bad.push([scene.id, "clamped", k, key, raw[key]]);
    }
  });
  const solid = pieces.filter((piece) => piece.kind !== "person");
  for (let i = 0; i < solid.length; i++) {
    for (let j = i + 1; j < solid.length; j++) {
      const a = solid[i], b = solid[j];
      const ya = extent(a).y, yb = extent(b).y;
      if (Math.min(ya[1], yb[1]) - Math.max(ya[0], yb[0]) <= 0.02) continue;
      if (overlaps(outline(a), outline(b))) out.bad.push([scene.id, "overlap", a.word || a.model || a.kind, a.id, b.word || b.model || b.kind, b.id]);
    }
  }
  // Whoever and whatever the scene names is in sight from where it starts.
  const raster = new B.Raster(320, 180);
  raster.raster(pieces, read.staging.camera[0]);
  const counts = new Map();
  for (const id of raster.id) counts.set(id, (counts.get(id) ?? 0) + 1);
  const named = pieces.filter((piece) => piece.kind === "person" || piece.word);
  const unseen = named.filter((piece) => (counts.get(piece.id) ?? 0) < 12).map((piece) => piece.word || `person ${piece.id}`);
  if (unseen.length) out.bad.push([scene.id, "out of sight", unseen]);
  out.seen[scene.id] = Math.round(100 * pieces.reduce((sum, piece) => sum + (counts.get(piece.id) ?? 0), 0) / raster.id.length);
}
console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    said = layout.in_pack(SCRIPT, target)

check("there are scenes enough, in groups", [said["count"] >= 12, said["groups"] >= 3], [True, True])
check("no scene shares an id with another, or with a quick start", said["ids"], True)
check("every scene builds clean: real models, nothing clamped, nothing inside anything, its cast in sight", said["bad"], [])
check("every scene fills a fair part of its first frame", {k: v for k, v in said["seen"].items() if v < 15}, {})

passed("the scene library lays out sets that stand up")
