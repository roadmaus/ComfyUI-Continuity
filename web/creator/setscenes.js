// Whole sets to start from: a kitchen, a bus stop, a forest clearing, each laid
// out from the model shelf with people standing in it and a camera move through
// it, the way the five plain arrangements in `blockout.PRESETS` are.
//
// A scene is only where to begin. Starting one makes a set like any other, and
// everything on it can be moved, resized, renamed or taken away. The camera
// looks down +z from near the origin, so a room's open side is towards it.
//
// Only what a staging sentence should mention is named; the second chair and
// the fourth fence panel only shape the depth pass.

import { MODELS } from "./setmodels.js";

/** A model's front, turned to face the camera. */
const BACK = Math.PI;
/** Facing +x (to the camera's right), or -x. */
const RIGHT = Math.PI / 2, LEFT = -Math.PI / 2;
/** Which way a piece at `from` faces to look at `to`, both as [x, z]. */
const toward = ([x0, z0], [x1, z1]) => Math.atan2(x1 - x0, z1 - z0);

/** A model, at its own size unless `size` gives [w, h, d], facing `ry`. A name
 *  of "" leaves it out of the staging sentence. */
const put = (id, x, z, ry = 0, { size, name, y = 0 } = {}) => {
  const model = MODELS.get(id);
  const [w, h, d] = size ?? [model.w, model.h, model.d];
  return { kind: "block", model: id, word: name ?? model.word, x, y, z, w, h, d, ry };
};

/** Someone standing, facing `ry`. Seated, they are shorter. */
const person = (x, z, ry = 0, { seated = false, h = 1.75 } = {}) =>
  ({ kind: "person", x, z, ry, w: 0.5, h: seated ? 1.28 : h, d: 0.38 });

/** A plain wall `w` long, centred at x, z; turned a quarter it runs along z. */
const wall = (x, z, w, h = 2.7, { ry = 0, y = 0, name = "" } = {}) => ({ kind: "wall", x, y, z, w, h, d: 0.14, ry, word: name });

/** A plain block, for what the shelf has no model of. */
const block = (x, z, [w, h, d], name, { y = 0, ry = 0 } = {}) => ({ kind: "block", x, y, z, w, h, d, ry, word: name });

/** A camera mark at x, y, z, looking at [x, z] `at`. */
const mark = (x, y, z, at, { pitch = -0.02, mm = 32 } = {}) => ({ x, y, z, yaw: toward([x, z], at), pitch, mm });

/** id, name, a line on what it is, and how to lay it out. */
const scene = (id, label, note, make) => ({ id, label, note, make });

export const SCENE_GROUPS = [
  { id: "home", label: "At home", scenes: [
    scene("kitchen", "Kitchen", "A table for four, a counter under the window, shelves, and someone at the sink.", () => ({
      objects: [
        wall(-2.75, 5.6, 2.5), put("windowwall", 0, 5.6, 0, { name: "" }), wall(2.75, 5.6, 2.5),
        put("counter", -0.9, 5.1, BACK, { name: "kitchen counter" }),
        put("shelf", 2.9, 5.3, BACK, { name: "" }),
        put("table", 0.4, 3, 0, { name: "kitchen table" }),
        put("chair", -0.05, 2.25, 0, { name: "" }), put("chair", 0.85, 2.25, 0, { name: "" }),
        put("chair", -0.05, 3.75, BACK, { name: "" }), put("chair", 0.85, 3.75, BACK, { name: "" }),
        person(-1.2, 4.4, 0),
        person(0.85, 3.8, BACK, { seated: true }),
      ],
      marks: [mark(-0.6, 1.6, -0.6, [0.2, 3.6]), mark(-0.2, 1.55, 0.6, [0.2, 3.6])],
    })),
    scene("living", "Living room", "A sofa and an armchair round a low table, a lamp, shelves on the wall, and a slow drift left.", () => ({
      objects: [
        wall(-3.75, 6, 1.5), put("windowwall", -1.5, 6, 0, { name: "" }), wall(2.25, 6, 4.5),
        wall(4.57, 4, 4, 2.7, { ry: RIGHT }),
        put("sofa", -0.5, 4.6, BACK),
        put("table", -0.5, 3.4, 0, { size: [1.1, 0.42, 0.6], name: "coffee table" }),
        put("armchair", 1.6, 3.6, toward([1.6, 3.6], [-0.5, 3.0])),
        put("lamp", -1.95, 5.2, 0),
        put("shelf", 4.2, 4, LEFT, { name: "" }),
        person(-0.9, 4.5, BACK, { seated: true }),
        person(1.1, 2.4, toward([1.1, 2.4], [-0.5, 4.4])),
      ],
      marks: [mark(0.6, 1.5, -1, [-0.2, 3.8], { mm: 28 }), mark(-0.7, 1.5, -0.7, [-0.4, 3.8], { mm: 28 })],
    })),
    scene("bedroom", "Bedroom", "A bed against the wall, a desk under the window, and someone in the doorway.", () => ({
      objects: [
        wall(-2, 5, 4), put("windowwall", 1.5, 5, 0, { name: "" }),
        put("doorwall", 3.07, 3.5, LEFT, { name: "doorway" }),
        put("bed", -1.6, 3.88, BACK),
        put("lamp", -0.4, 4.6, 0, { size: [0.35, 1.1, 0.35], name: "" }),
        put("desk", 1.5, 4.55, BACK, { name: "" }),
        put("chair", 1.5, 3.85, 0, { name: "" }),
        put("shelf", -3.75, 2.2, RIGHT, { name: "" }),
        person(2.7, 3.5, LEFT),
        person(-1.4, 2.6, BACK, { seated: true }),
      ],
      marks: [mark(0.2, 1.55, -0.9, [0, 3.6]), mark(0.1, 1.5, 0.5, [-0.4, 3.6])],
    })),
  ] },
  { id: "public", label: "Work and public", scenes: [
    scene("cafe", "Café", "Three small tables by the window, a counter with someone behind it, and a pan across the room.", () => ({
      objects: [
        wall(0, 6.1, 9),
        put("windowwall", -4.2, 3, RIGHT, { name: "" }), wall(-4.2, 5.25, 1.5, 2.7, { ry: RIGHT }),
        put("counter", 1.5, 5.4, BACK),
        ...[[-2.6, 2.5], [-2.6, 4.6], [-0.6, 3.4]].flatMap(([x, z], k) => [
          put("roundtable", x, z, 0, { name: k ? "" : "café table" }),
          put("chair", x - 0.75, z, RIGHT, { name: "" }), put("chair", x + 0.75, z, LEFT, { name: "" }),
        ]),
        person(1.5, 5.88, BACK),
        person(1.2, 4.5, 0),
        person(-1.35, 3.4, RIGHT, { seated: true }),
      ],
      marks: [mark(1.8, 1.5, -0.6, [-1, 3.8], { mm: 28 }), mark(0.4, 1.5, -0.3, [-1.4, 3.6], { mm: 28 })],
    })),
    scene("office", "Open office", "Four desks in two rows with screens, shelving on one side, a big window behind.", () => ({
      objects: [
        wall(-4, 6.6, 2, 2.9), put("windowwall", -1.5, 6.6, 0, { size: [3, 2.9, 0.18], name: "" }),
        put("windowwall", 1.5, 6.6, 0, { size: [3, 2.9, 0.18], name: "" }), wall(4, 6.6, 2, 2.9),
        ...[[-1.6, 3], [1.6, 3], [-1.6, 5], [1.6, 5]].flatMap(([x, z], k) => [
          put("desk", x, z, 0, { name: k ? "" : "desk" }),
          put("screen", x - 0.15, z - 0.1, 0, { size: [0.6, 0.42, 0.2], y: 0.75, name: k ? "" : "computer screen" }),
          put("chair", x, z + 0.75, BACK, { name: "" }),
        ]),
        put("shelf", -4.6, 2, RIGHT, { name: "" }), put("shelf", -4.6, 3.1, RIGHT, { name: "" }),
        person(-1.6, 3.8, BACK, { seated: true }),
        person(1.6, 5.8, BACK, { seated: true }),
        person(0, 4.2, toward([0, 4.2], [-1.6, 3.8])),
      ],
      marks: [mark(0, 1.6, -1.2, [0, 4.4], { mm: 28 }), mark(0, 1.6, 0.8, [0, 4.6], { mm: 28 })],
    })),
    scene("meeting", "Meeting room", "A long table seen down its length, chairs either side, a screen on the far wall.", () => ({
      objects: [
        wall(0, 6.6, 6.2),
        put("windowwall", 3, 3.6, LEFT, { name: "" }), wall(3, 5.8, 1.4, 2.7, { ry: RIGHT }),
        put("table", 0, 3.6, RIGHT, { size: [3.2, 0.75, 1.1], name: "meeting table" }),
        ...[2.6, 3.6, 4.6].flatMap((z) => [put("chair", -1, z, RIGHT, { name: "" }), put("chair", 1, z, LEFT, { name: "" })]),
        put("chair", 0, 5.8, BACK, { name: "" }),
        put("screen", 0, 6.38, BACK, { size: [1.8, 1.1, 0.22], y: 0.95, name: "wall screen" }),
        person(-1.7, 5.7, toward([-1.7, 5.7], [0, 3.6])),
        person(-1, 3.6, RIGHT, { seated: true }),
        person(1, 2.6, LEFT, { seated: true }),
        person(1, 4.6, LEFT, { seated: true }),
      ],
      marks: [mark(0, 1.45, 0.2, [0, 4.6], { mm: 35 }), mark(0.5, 1.7, 0.6, [-0.3, 4.8], { mm: 35, pitch: -0.08 })],
    })),
    scene("warehouse", "Warehouse", "Tall racks, crates and barrels on the floor, a truck backed in, under a high roof.", () => ({
      objects: [
        wall(0, 12, 16, 6),
        put("column", -2.5, 10.8, 0, { size: [0.5, 6, 0.5], name: "" }), put("column", 1.5, 10.8, 0, { size: [0.5, 6, 0.5], name: "" }),
        put("shelf", -4.5, 4, RIGHT, { size: [3, 3.2, 0.9], name: "storage rack" }),
        put("shelf", -4.5, 7.5, RIGHT, { size: [3, 3.2, 0.9], name: "" }),
        put("ladder", -3.95, 9.4, RIGHT, { size: [0.5, 3, 0.1], name: "" }),
        put("truck", 4, 6.5, BACK),
        put("crate", -1.8, 5, 0, { name: "crates" }), put("crate", -0.95, 5, 0.1, { name: "" }),
        put("crate", -1.4, 5, 0.05, { y: 0.8, name: "" }),
        put("barrel", 0.6, 8, 0, { name: "" }), put("barrel", 1.3, 8.2, 0, { name: "" }), put("barrel", 0.9, 8.8, 0, { name: "" }),
        person(-0.4, 4, toward([-0.4, 4], [-1.4, 5])),
        person(2.3, 3.5, LEFT),
      ],
      marks: [mark(-1, 1.7, -2.5, [0.2, 6], { mm: 24 }), mark(1, 1.7, -2, [-0.4, 6], { mm: 24 })],
    })),
    scene("gallery", "Gallery", "Three pieces on plinths, a bench, columns down both sides, an arch through to the next room.", () => ({
      objects: [
        wall(-3.65, 8, 4.7, 4), put("arch", 0, 8, 0), wall(3.65, 8, 4.7, 4), wall(0, 8, 2.6, 1, { y: 3 }),
        ...[2.5, 5.5].flatMap((z) => [-4.5, 4.5].map((x) => put("column", x, z, 0, { size: [0.6, 4, 0.6], name: "" }))),
        put("plinth", -1.5, 4, 0, { name: "plinth" }), put("plinth", 1.5, 4, 0, { name: "" }), put("plinth", 0, 6.3, 0, { name: "" }),
        put("bench", 0, 2.3, 0, { name: "" }),
        person(-1.2, 3, toward([-1.2, 3], [-1.5, 4])),
        person(2.3, 4.6, toward([2.3, 4.6], [1.5, 4])),
      ],
      marks: [mark(-3, 1.5, -1, [0, 4.5], { mm: 28 }), mark(3, 1.5, -1, [0, 4.5], { mm: 28 })],
    })),
    scene("lobby", "Lobby with stairs", "A reception desk, a stair up to a landing, a column, and someone walking in.", () => ({
      objects: [
        wall(0, 8.2, 10, 4),
        put("stairs", -2.5, 5, BACK, { size: [1.4, 1.6, 2.8], name: "staircase" }),
        block(-2.5, 7.3, [1.4, 1.6, 1.6], "landing"),
        put("railing", -1.75, 7.3, RIGHT, { size: [1.6, 1, 0.08], y: 1.6, name: "" }),
        put("counter", 2, 4.5, BACK, { name: "reception desk" }),
        put("column", 0.2, 6, 0, { size: [0.6, 4, 0.6], name: "" }),
        put("bush", 4.2, 7.4, 0, { size: [0.9, 1.3, 0.9], name: "plant" }),
        person(2, 5.2, BACK),
        person(0.8, 1.6, toward([0.8, 1.6], [2, 4])),
      ],
      marks: [mark(0.5, 1.6, -2.5, [0.3, 5], { mm: 28 }), mark(-0.4, 1.6, -1.6, [-1.2, 5.4], { mm: 28, pitch: 0.06 })],
    })),
  ] },
  { id: "streets", label: "Streets", scenes: [
    scene("busstop", "Bus stop", "A shelter with people waiting, a bus pulling in, shopfronts behind.", () => ({
      objects: [
        wall(0, 9, 20, 6, { name: "shopfronts" }),
        put("busstop", 0.5, 6.5, BACK),
        put("bus", -6, 3.5, RIGHT),
        put("streetlamp", 3.6, 5.6, BACK, { name: "" }),
        put("bin", 2.6, 6.2, 0, { name: "" }),
        person(0, 6.6, BACK, { seated: true }),
        person(1.6, 6.1, LEFT),
      ],
      marks: [mark(2.5, 1.5, -1.5, [0, 6.5]), mark(1.2, 1.5, -1, [-2.5, 5.5])],
    })),
    scene("crossroads", "Crossroads", "Four tall blocks, traffic lights on the corners, cars waiting and crossing, people on the zebra.", () => ({
      objects: [
        put("tower", -8.5, 3.5, 0, { size: [8, 14, 8], name: "" }), put("tower", 8.5, 3.5, 0, { size: [8, 10, 8], name: "" }),
        put("tower", -8.5, 20.5, 0, { size: [8, 18, 8], name: "" }), put("tower", 8.5, 20.5, 0, { size: [8, 12, 8], name: "" }),
        ...[[-4.5, 8], [4.5, 8], [-4.5, 16], [4.5, 16]].map(([x, z], k) => put("trafficlight", x, z, BACK, { name: k ? "" : "traffic light" })),
        put("car", -1.8, 6, 0, { name: "car" }),
        put("car", 1.8, 18, BACK, { name: "" }),
        put("car", -7, 13.6, RIGHT, { name: "" }),
        put("van", 7, 10.4, LEFT),
        person(-3, 8.8, RIGHT), person(-2.3, 9.4, RIGHT),
      ],
      marks: [mark(-0.8, 1.5, -1, [-0.5, 12], { mm: 28, pitch: 0.03 }), mark(-0.8, 1.5, 2, [-0.5, 12], { mm: 28, pitch: 0.05 })],
    })),
    scene("frontyard", "Front yard", "A house behind a picket fence, a tree, a car in the drive, someone at the gate.", () => ({
      objects: [
        put("house", 0, 10, BACK),
        ...[-6, -3, 3].map((x, k) => put("fence", x, 5.5, 0, { name: k ? "" : "fence" })),
        put("tree", -5.3, 8.2, 0),
        put("bush", 2.4, 6.4, 0, { name: "" }), put("bush", -1.6, 6.2, 0, { name: "" }),
        put("car", 5.4, 8.6, BACK, { name: "" }),
        put("bike", -3.3, 6.3, RIGHT, { name: "" }),
        person(0, 4.8, 0),
        person(0.3, 6.6, BACK),
      ],
      marks: [mark(-1.5, 1.6, -2, [0, 7.5]), mark(1.5, 1.6, -1.5, [0, 7.5])],
    })),
    scene("alley", "Back alley", "A narrow lane between high walls: a van, bins, a door with crates, a fire escape.", () => ({
      objects: [
        wall(-3.2, 8, 16, 7, { ry: RIGHT, name: "building" }),
        wall(3.2, 2.25, 4.5, 7, { ry: RIGHT }), put("doorwall", 3.2, 6, LEFT, { name: "back door" }),
        wall(3.2, 6, 3, 4.4, { ry: RIGHT, y: 2.6 }), wall(3.2, 11.75, 8.5, 7, { ry: RIGHT }),
        put("van", -1.8, 9, BACK),
        block(2.5, 9.5, [1.8, 1.3, 1], "dumpster", { ry: RIGHT }),
        put("bin", 2.75, 3.5, 0, { name: "" }), put("bin", 2.75, 4.1, 0, { name: "" }),
        put("crate", 2.6, 7.5, 0, { name: "" }), put("crate", 2.6, 7.5, 0.2, { y: 0.8, name: "" }),
        put("barrel", -2.6, 4.5, 0, { name: "" }),
        block(2.55, 12, [2.6, 0.1, 1.15], "fire escape", { y: 3.3, ry: RIGHT }),
        put("railing", 2, 12, RIGHT, { size: [2.6, 1, 0.08], y: 3.4, name: "" }),
        put("ladder", 2.2, 13.6, RIGHT, { size: [0.5, 3.3, 0.1], name: "" }),
        person(2.4, 6, LEFT),
        person(0.2, 12.5, BACK),
      ],
      marks: [mark(0.3, 1.6, -1.5, [0.2, 10], { mm: 28 }), mark(0.3, 1.6, 1.5, [0.2, 10], { mm: 28 })],
    })),
    scene("rooftop", "Rooftop", "Two people at the railing over a city skyline, vents and a water tank behind them.", () => ({
      objects: [
        ...[-3.6, -1.2, 1.2, 3.6].map((x, k) => put("railing", x, 8, 0, { name: k ? "" : "railing" })),
        put("crate", -3, 4, 0, { size: [1.2, 1, 1], name: "air vent" }), put("crate", -1.6, 4, 0, { size: [1.2, 1, 1], name: "" }),
        put("barrel", 4, 5, 0, { size: [2, 3, 2], name: "water tank" }),
        block(-4.6, 5.8, [2.4, 2.6, 2.4], "stair hut"),
        put("tower", -11, 26, 0, { size: [8, 18, 8], name: "" }), put("tower", 0, 30, 0, { size: [10, 20, 10], name: "" }),
        put("tower", 11, 24, 0, { size: [8, 14, 8], name: "" }),
        person(0.3, 7.4, 0), person(1.1, 7.45, -0.2),
      ],
      marks: [mark(0, 1.6, 0, [0.5, 12], { mm: 35, pitch: 0.06 }), mark(-1.5, 1.6, 2, [0.5, 12], { mm: 35, pitch: 0.08 })],
    })),
  ] },
  { id: "outdoors", label: "Outdoors", scenes: [
    scene("park", "Park", "A path past two benches under trees, a lamp and a bin, someone sitting and someone walking.", () => ({
      objects: [
        put("bench", -2, 5, BACK),
        put("bench", 3, 8, BACK, { name: "" }),
        put("bin", -0.8, 5, 0, { name: "" }),
        put("streetlamp", 0.8, 6.5, LEFT, { name: "" }),
        put("tree", -4.5, 7.5, 0), put("tree", 6, 11, 0, { name: "" }), put("tree", -1, 12, 0, { name: "" }),
        put("pine", -7, 13, 0, { name: "" }),
        put("bush", 1.4, 4.2, 0, { name: "" }), put("bush", 4.6, 6.2, 0, { name: "" }),
        person(-2.3, 5, BACK, { seated: true }),
        person(-0.4, 2.8, 0.2),
      ],
      marks: [mark(0, 1.5, -2, [-0.6, 6], { mm: 35 }), mark(-1.5, 1.5, -1.6, [-1.2, 6], { mm: 35 })],
    })),
    scene("forest", "Forest clearing", "A ring of pines round a fallen log, rocks and undergrowth, two people at the log.", () => ({
      objects: [
        ...[[-6, 6], [-7.5, 10], [-4, 13.2], [0.5, 15], [5, 13.5], [7.5, 9.5], [6, 5.5], [-9, 3.5], [9, 3], [-3.6, 1]]
          .map(([x, z], k) => put("pine", x, z, (k % 5) * 0.6, { name: k ? "" : "pine trees" })),
        { ...put("barrel", 0, 7, 0, { size: [0.45, 2.2, 0.45], name: "fallen log" }), rz: Math.PI / 2 },
        put("rock", 2.2, 8.8, 0.4), put("rock", -2.5, 9, -0.8, { size: [0.9, 0.6, 0.8], name: "" }),
        put("bush", 3.5, 10.5, 0, { name: "undergrowth" }), put("bush", -2.2, 11, 0.5, { name: "" }),
        person(-0.5, 6.4, BACK, { seated: true }),
        person(1.6, 7.6, toward([1.6, 7.6], [0, 7])),
      ],
      marks: [mark(0.5, 1.4, -1.5, [0, 8], { mm: 28, pitch: 0.02 }), mark(-1, 1.3, 0.5, [0, 7.5], { mm: 28 })],
    })),
  ] },
];

export const SCENES = new Map(SCENE_GROUPS.flatMap((group) => group.scenes).map((one) => [one.id, one]));
