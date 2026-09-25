"""Segment references and seed controls stay on the strip without changing seed ownership."""

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
  // Capture the path before a click redraws the card, as browser events do.
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
  assets: [{ handle: "ref-2", kind: "image", role: "reference", filename: "lighting/pool.png" }],
  segments: [
    { prompt: "@ref-2 studio lighting", duration_s: 5, hold: true,
      refined: { body: "@ref-2 soft studio lighting", enabled: true },
      assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "lighting/local.png" }],
      loras: [{ name: "Lighting/StudioLighting.safetensors", strength: 0.7 }] },
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
const initialCommits = snapshots.length;
const cards = () => modal.modal.querySelectorAll(".mmc-tl-card");
const card = (index = 0) => cards()[index];
const input = (index = 0) => card(index).querySelector(".mmc-seed-input");
const rewind = () => card().querySelector(".mmc-seed-last");
const read = () => ({
  shown: input().value,
  mode: card().querySelector(".mmc-seed-mode").textContent,
  own: S.segmentSeed(timeline.segments[0]),
  resetDisabled: "disabled" in rewind().attrs,
  stale: [...S.editedSince(timeline)],
  marked: Boolean(card().querySelector(".mmc-tl-card-state.stale")),
});
const refs = card().querySelector(".mmc-tl-card-refs");
const meta = card().querySelector(".mmc-tl-card-meta");
const out = {
  refs: { text: refs.textContent, direct: refs.parent === card(),
          afterPrompt: card().children.indexOf(refs) === card().children.indexOf(card().querySelector(".mmc-tl-card-prompt")) + 1,
          outsideMeta: !meta.contains(refs), absentWhenEmpty: !card(1).querySelector(".mmc-tl-card-refs") },
  metadata: meta.children.map((node) => ({ tag: node.tagName, text: node.text })),
  seedLocation: { count: card().querySelectorAll(".mmc-tl-card-seed").length,
    beforeFoot: card().children.indexOf(card().querySelector(".mmc-tl-card-seed")) + 1
      === card().children.indexOf(card().querySelector(".mmc-tl-card-foot")) },
  inherited: read(),
  takenHint: input().attrs.title.includes("Its take was made on 123."),
  clip: { inputs: card(2).querySelectorAll(".mmc-seed-input").length,
          refs: card(2).querySelectorAll(".mmc-tl-card-refs").length },
};
fire(input(), "change", "42");
out.manual = { ...read(), committedSeed: snapshots.at(-1).segments[0].seed,
               otherOwn: S.segmentSeed(timeline.segments[1]), pieceSeed };
const random = Math.random;
Math.random = () => 0.5;
out.randomStopped = fire(card().querySelector(".mmc-seed-dice"), "click");
Math.random = random;
out.random = read();
out.resetStopped = fire(rewind(), "click");
out.reset = { ...read(), storedOwn: Object.hasOwn(snapshots.at(-1).segments[0], "seed") };
fire(input(), "change", "0");
out.zero = read();
fire(input(), "change", "");
out.blank = read();
out.commits = snapshots.length - initialCommits;
pieceSeed = 777;
modal.render();
out.changedPieceSeed = { shown: input().value, otherShown: input(1).value, own: S.segmentSeed(timeline.segments[0]) };
out.takeRetained = JSON.stringify(timeline.segments[0].take) === initialTake;
out.holdRetained = timeline.segments[0].hold;
out.clipUnchanged = JSON.stringify(JSON.parse(S.serializeTimeline(timeline)).segments[2]) === JSON.stringify(initialClip);

let opened = 0;
const realEdit = modal.edit.bind(modal);
modal.edit = () => { opened++; };
const propagated = { pointerdown: 0, click: 0, dblclick: 0 };
for (const type of Object.keys(propagated)) document.body.addEventListener(type, () => { propagated[type]++; });
out.stops = [];
for (const selector of [".mmc-seed-input", ".mmc-seed-dice", ".mmc-seed-last", ".mmc-seed-mode"]) {
  for (const type of ["pointerdown", "dblclick"]) out.stops.push(fire(card().querySelector(selector), type));
}
out.stops.push(fire(input(), "click"));
out.stops.push(fire(card().querySelector(".mmc-seed-mode"), "click"));
out.propagated = { ...propagated };
out.openedFromSeed = opened;
fire(card().querySelector(".mmc-tl-card-prompt"), "dblclick");
out.openedFromPrompt = opened;
modal.edit = realEdit;

modal.edit(0);
const sheet = document.body.children.at(-1);
out.editorSeedCount = sheet.querySelectorAll(".mmc-seed-input").length;
out.stripSeedCount = modal.modal.querySelectorAll(".mmc-tl-card-seed").length;
// A different caller may still explicitly request the generic editor's seed.
const genericState = S.emptyState();
let genericCommits = 0;
const generic = new CreatorEditor({ state: genericState,
  seedTarget: () => ({ own: S.segmentSeed(genericState), piece: 81, taken: 70 }),
  onCommit: () => { genericCommits++; },
});
out.genericBefore = generic.root.querySelector(".mmc-seed-input").value;
fire(generic.root.querySelector(".mmc-seed-input"), "change", "99");
out.genericAfter = { seed: genericState.seed, shown: generic.root.querySelector(".mmc-seed-input").value,
                     commits: genericCommits };

const sharedTimeline = S.parseTimeline(JSON.stringify({ version: 2, render: "single",
  segments: [{ prompt: "first", duration_s: 3, seed: 101, assets: [], loras: [] },
             { prompt: "second", duration_s: 3, seed: 202, assets: [], loras: [] }] }));
let sharedCommits = 0;
const shared = new Timeline({ timeline: sharedTimeline, onCommit: () => { sharedCommits++; } }, () => {});
shared.mount();
await settle();
// The shim has no descendant selectors; inspect each card's own control.
const sharedSeeds = () => shared.modal.querySelectorAll(".mmc-tl-card").map((node) => node.querySelector(".mmc-seed-input"));
out.sharedBefore = sharedSeeds().map((node) => node.value);
fire(sharedSeeds()[1], "change", "404");
out.sharedAfter = { seeds: sharedTimeline.segments.map(S.segmentSeed),
                    passes: S.passes(sharedTimeline).length, commits: sharedCommits };
console.log(JSON.stringify(out));
'''

with layout.pack(skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target)

check("references get their own row immediately below the prompt", got["refs"],
      {"text": "2 refs", "direct": True, "afterPrompt": True, "outsideMeta": True, "absentWhenEmpty": True})
check("LoRA and refinement metadata remain individual spans", got["metadata"][:2],
      [{"tag": "SPAN", "text": "1 LoRA"}, {"tag": "SPAN", "text": "refined"}])
check("each generated card has one seed row before its footer", got["seedLocation"],
      {"count": 1, "beforeFoot": True})
check("a card initially inherits the piece seed", got["inherited"],
      {"shown": "9001", "mode": "piece", "own": None, "resetDisabled": True, "stale": [], "marked": False})
check("the existing take seed remains in the tooltip", got["takenHint"], True)
check("typing commits only this card's seed and marks its take stale", got["manual"],
      {"shown": "42", "mode": "card", "own": 42, "resetDisabled": False, "stale": [0], "marked": True,
       "committedSeed": 42, "otherOwn": None, "pieceSeed": 9001})
check("rolling uses the existing per-card random seed behavior", got["random"],
      {"shown": "2147483647", "mode": "card", "own": 2147483647, "resetDisabled": False,
       "stale": [0], "marked": True})
check("reset removes the override and restores the original take stamp", got["reset"],
      {**got["inherited"], "storedOwn": False})
check("zero remains a valid explicit seed", got["zero"]["own"], 0)
check("clearing the input returns to inheritance", got["blank"], got["inherited"])
check("each seed action commits exactly once", got["commits"], 5)
check("an inherited seed follows the node on the next redraw", got["changedPieceSeed"],
      {"shown": "777", "otherShown": "777", "own": None})
check("editing seeds retains the existing take and hold", [got["takeRetained"], got["holdRetained"]], [True, True])
check("imported clips acquire neither reference nor seed rows", got["clip"], {"inputs": 0, "refs": 0})
check("seed actions leave the imported clip unchanged", got["clipUnchanged"], True)
check("random and reset clicks stop at the seed row", [got["randomStopped"], got["resetStopped"]], [True, True])
check("pointer and double-click events stop for every seed control", got["stops"], [True] * 10)
check("seed events never reach the outer overlay", got["propagated"], {"pointerdown": 0, "click": 0, "dblclick": 0})
check("seed interaction does not open the card editor", got["openedFromSeed"], 0)
check("the prompt still opens its editor on double-click", got["openedFromPrompt"], 1)
check("Timeline editor does not duplicate strip seed controls", [got["editorSeedCount"], got["stripSeedCount"]], [0, 2])
check("the generic editor still supports inherited seeds", got["genericBefore"], "81")
check("the generic editor still edits its requested seed target", got["genericAfter"], {"seed": 99, "shown": "99", "commits": 1})
check("merged shots retain their individual existing seed overrides", got["sharedBefore"], ["101", "202"])
check("editing a later merged shot preserves the first shot and pass grouping", got["sharedAfter"],
      {"seeds": [101, 404], "passes": 1, "commits": 1})
