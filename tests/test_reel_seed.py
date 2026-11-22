"""A shot's seed lives on its side of the reel, once, without changing seed ownership.

The reel shows one shot's settings at a time: select a shot and its seed, its
length and its take are on the side. This drives the real `Timeline` modal in
the DOM shim and checks that the seed control is there exactly once, that it
writes only the selected shot's seed, and that changing a kept shot's seed puts
it back in the next render without losing the take it has.
"""

import domshim
import layout
from harness import check


layout.skip_without_node()

SCRIPT = domshim.DOM + r'''
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
import * as S from "./web/creator/state.js";
import { CreatorEditor } from "./web/creator/editor.js";

globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const timelineURL = pathToFileURL(path.join(process.cwd(), "web/creator/timeline.js"));
// Expose the private controller; all methods and imports remain the real ones.
const source = readFileSync(timelineURL, "utf8")
  .replace("class Timeline {", "export class Timeline {")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, timelineURL).href}"`);
const { Timeline } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

const fire = (node, type, value) => {
  if (!node) throw new Error("Missing target for " + type);
  if (value !== undefined) node.value = value;
  const chain = [];
  for (let at = node; at; at = at.parent) chain.push(at);
  const event = { target: node, currentTarget: node, stopped: false,
    stopPropagation() { this.stopped = true; }, preventDefault() {} };
  for (const at of chain) {
    event.currentTarget = at;
    for (const listener of at.listeners?.[type] ?? []) listener(event);
    if (event.stopped) break;
  }
  return event.stopped;
};
const settle = async () => {
  for (let i = 0; i < 4; i++) await new Promise((done) => setTimeout(done, 0));
};
const timeline = S.parseTimeline(JSON.stringify({
  version: 2, render: "chained", prompt: "", aspect: "16:9", short_edge: 768,
  segments: [
    { prompt: "studio lighting", duration_s: 5, assets: [], loras: [] },
    { prompt: "a window", duration_s: 5, assets: [], loras: [] },
    { kind: "clip", filename: "footage/lighting.mp4", duration_s: 4,
      width: 1280, height: 720, continue: true },
  ],
}));
S.attachTakes(timeline, [{ segment: 1, filename: "lighting.mp4", subfolder: "takes",
                         duration_s: 5, seed: 123 }]);
const initialTake = JSON.stringify(timeline.segments[0].take);
const initialClip = JSON.parse(S.serializeTimeline(timeline)).segments[2];
let pieceSeed = 9001;
const snapshots = [];
const modal = new Timeline({ timeline,
  io: () => ({ value: (name, fallback) => name === "seed" ? pieceSeed : fallback, set() {} }),
  onCommit: () => snapshots.push(JSON.parse(S.serializeTimeline(timeline))),
}, () => {});
modal.mount();
await settle();

const cards = () => modal.modal.querySelectorAll(".mmc-reel-card");
const pick = (index) => fire(cards()[index], "click");
const side = () => modal.inspectHost;
const input = () => side().querySelector(".mmc-seed-input");
const read = () => ({
  shown: input().value,
  mode: side().querySelector(".mmc-seed-mode").textContent,
  own: S.segmentSeed(timeline.segments[0]),
  kept: S.isHeld(timeline.segments[0]),
});

const out = {};
out.keptAtFirst = S.isHeld(timeline.segments[0]);
pick(0);
out.seedCount = side().querySelectorAll(".mmc-seed-input").length;
out.inherited = read();
out.takenHint = input().attrs.title.includes("Its take was made on 123.");
const before = snapshots.length;
fire(input(), "change", "42");
out.manual = { ...read(), otherOwn: S.segmentSeed(timeline.segments[1]),
               committedSeed: snapshots.at(-1).segments[0].seed };
fire(side().querySelector(".mmc-seed-last"), "click");
out.reset = read();
out.commits = snapshots.length - before;
pieceSeed = 777;
modal.render();
out.followsNode = input().value;
out.takeRetained = JSON.stringify(timeline.segments[0].take) === initialTake;
pick(2);
out.clipInputs = side().querySelectorAll(".mmc-seed-input").length;
out.clipUnchanged = JSON.stringify(JSON.parse(S.serializeTimeline(timeline)).segments[2]) === JSON.stringify(initialClip);

modal.edit(0);
const sheet = document.body.children.at(-1);
out.editorSeedCount = sheet.querySelectorAll(".mmc-seed-input").length;

// A different caller may still explicitly request the generic editor's seed.
const genericState = S.emptyState();
let genericCommits = 0;
const generic = new CreatorEditor({ state: genericState,
  seedTarget: () => ({ own: S.segmentSeed(genericState), piece: 81, taken: 70 }),
  onCommit: () => { genericCommits++; },
});
fire(generic.root.querySelector(".mmc-seed-input"), "change", "99");
out.generic = { seed: genericState.seed, commits: genericCommits };

// Two shots in one pass: the second keeps a seed of its own, and setting it
// does not split the pass.
const sharedTimeline = S.parseTimeline(JSON.stringify({ version: 2, render: "single",
  segments: [{ prompt: "first", duration_s: 3, seed: 101, assets: [], loras: [] },
             { prompt: "second", duration_s: 3, seed: 202, assets: [], loras: [] }] }));
const shared = new Timeline({ timeline: sharedTimeline, onCommit: () => {} }, () => {});
shared.mount();
await settle();
fire(shared.modal.querySelectorAll(".mmc-reel-card")[1], "click");
out.sharedShown = shared.inspectHost.querySelector(".mmc-seed-input").value;
fire(shared.inspectHost.querySelector(".mmc-seed-input"), "change", "404");
out.shared = { seeds: sharedTimeline.segments.map(S.segmentSeed), passes: S.passes(sharedTimeline).length };
console.log(JSON.stringify(out));
'''

with layout.pack(skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target)

check("a take that lands is kept", got["keptAtFirst"], True)
check("the selected shot's side has exactly one seed control", got["seedCount"], 1)
check("a shot initially inherits the piece seed", got["inherited"],
      {"shown": "9001", "mode": "piece", "own": None, "kept": True})
check("the take's seed is named in the tooltip", got["takenHint"], True)
check("typing commits only this shot's seed and puts it back in the next render",
      got["manual"], {"shown": "42", "mode": "card", "own": 42, "kept": False,
                      "otherOwn": None, "committedSeed": 42})
check("reset returns the shot to the piece seed", got["reset"],
      {"shown": "9001", "mode": "piece", "own": None, "kept": False})
check("each seed action commits exactly once", got["commits"], 2)
check("an inherited seed follows the node on the next redraw", got["followsNode"], "777")
check("the take itself is kept through a reshoot", got["takeRetained"], True)
check("an imported clip has no seed", got["clipInputs"], 0)
check("seed actions leave the imported clip unchanged", got["clipUnchanged"], True)
check("the shot's editor does not repeat the seed control", got["editorSeedCount"], 0)
check("the generic editor still writes a seed when asked to", got["generic"], {"seed": 99, "commits": 1})
check("a shot in a shared pass shows its own seed", got["sharedShown"], "202")
check("...and setting it leaves the pass whole", got["shared"],
      {"seeds": [101, 404], "passes": 1})
