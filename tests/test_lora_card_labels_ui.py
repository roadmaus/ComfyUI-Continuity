"""Metadata labels by default, with selected-file labels as an opt-in setting.

All LoRA names and metadata here are fictitious.
"""

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

API = """
import { readFileSync } from "node:fs";
const store = new Map();
globalThis.__settingsCalls = 0;
globalThis.__listingCalls = 0;
const rows = [
  {
    name: "Lighting/StudioLighting_V1.safetensors", base: "StudioLighting_V1",
    card_title: "Studio illumination", card_subtitle: "Example base · Softbox",
    title: "Embedded training name", base_model: "Embedded base", version: "1",
    model_id: 123, trained_words: ["studio light"], strength: 0.7, preview: "image",
  },
  {
    name: "Lighting/StudioLighting_V2.safetensors", base: "StudioLighting_V2",
    card_title: "StudioLighting_V2", card_subtitle: "Lighting/StudioLighting_V2.safetensors",
    title: "Another embedded name", base_model: "Embedded base", version: "2",
    model_id: 123, trained_words: ["soft light"], strength: 0.8, preview: "image",
  },
  {
    // In the opt-in mode, older responses must still use filename fallbacks.
    name: "Lighting/WindowLight_V1.safetensors", base: "WindowLight_V1",
    title: "Legacy embedded name", base_model: "Legacy base", version: "1",
    trained_words: [], strength: 1.0,
  },
];
export const api = {
  apiURL: (u) => u,
  addEventListener() {}, removeEventListener() {},
  async fetchApi(url) {
    const text = String(url);
    let body = {};
    if (text.startsWith("/continuity/families")) {
      body = JSON.parse(readFileSync(new URL("./families.json", import.meta.url), "utf8"));
    } else if (text === "/continuity/settings") {
      globalThis.__settingsCalls++;
      if (process.argv[1] !== "roundtrip") {
        await new Promise((resolve) => { globalThis.__releaseSettings = resolve; });
      }
      body = { settings: process.argv[1] === "roundtrip" ? {} : {lora_skip_metadata: true} };
    } else if (text.startsWith("/continuity/loras")) {
      globalThis.__listingCalls++;
      if (process.argv[1] === "close-listing") {
        await new Promise((resolve) => { globalThis.__releaseLoras = resolve; });
      }
      body = { loras: rows, folders: [{path: "", count: rows.length}],
               folder: "", matched: rows.length, truncated: false };
    }
    return { ok: true, status: 200, json: async () => body };
  },
  async getUserData(file) {
    return store.has(file)
      ? { status: 200, json: async () => JSON.parse(store.get(file)) }
      : { status: 404, json: async () => null };
  },
  async storeUserData(file, value) { store.set(file, JSON.stringify(value)); return { status: 200 }; },
};
"""

HELPERS = domshim.DOM + """
import { openLoras } from "./web/creator/loras.js";
import { noteSettings } from "./web/creator/api.js";

const all = (cls, node = document.body, out = []) => {
  if (String(node.className || "").split(" ").includes(cls)) out.push(node);
  for (const child of node.children ?? []) all(cls, child, out);
  return out;
};
const one = (cls, node) => all(cls, node)[0];
const fire = (node, type, event = {}) => {
  if (!node) throw new Error("missing target for " + type);
  for (const fn of node.listeners?.[type] ?? []) fn({
    stopPropagation() {}, preventDefault() {}, currentTarget: node, target: node, ...event,
  });
};
const cards = () => all("mmc-lora").filter((node) => one("mmc-lora-art", node));
const card = (name) => {
  const found = cards().find((node) => one("mmc-lora-name", node).attrs.title === name);
  if (!found) throw new Error("missing card for " + name);
  return found;
};
const labels = (name) => {
  const node = card(name);
  return [one("mmc-lora-name", node).textContent, one("mmc-lora-sub", node).textContent];
};
const v1 = "Lighting/StudioLighting_V1.safetensors";
const v2 = "Lighting/StudioLighting_V2.safetensors";
const legacy = "Lighting/WindowLight_V1.safetensors";
const settle = async () => {
  for (let i = 0; i < 4; i++) await new Promise((done) => setTimeout(done, 0));
};
const close = () => fire(one("mmc-close"), "click");
const open = async (state) => {
  openLoras({ state, onChange() {} });
  await settle();
};
"""

SCRIPT = HELPERS + """
const state = { loras: [], assets: [] };
await open(state);
const out = { defaults: {count: cards().length, newest: labels(v2), legacy: labels(legacy)} };
close();
noteSettings({lora_skip_metadata: true});
await open(state);
Object.assign(out, { count: cards().length, newest: labels(v2), legacy: labels(legacy) });

fire(all("mmc-ver", card(v2)).find((node) => node.textContent === "V1"), "click");
out.sidecar = labels(v1);
out.preview = card(v1).querySelectorAll("img")[0].attrs.src;
fire(one("mmc-lora-art", card(v1)), "click");
out.added = { name: state.loras[0].name, strength: state.loras[0].strength,
              triggers: state.loras[0].triggers.slice() };
fire(one("mmc-lora-num", card(v1)), "change", { target: {value: "0.42"} });
fire(all("mmc-ver", card(v1)).find((node) => node.textContent === "V2"), "click");
out.switched = { labels: labels(v2), name: state.loras[0].name,
                 strength: state.loras[0].strength, triggers: state.loras[0].triggers.slice() };

const search = one("mmc-search");
fire(search, "input", { target: {value: "Softbox"} });
out.searchSubtitle = { count: cards().length, labels: labels(v1) };
fire(search, "input", { target: {value: "Studio illumination"} });
out.searchTitle = labels(v1);
close();
noteSettings({lora_skip_metadata: false});
await open(state);
out.restored = { labels: labels(v2), name: state.loras[0].name,
                 strength: state.loras[0].strength, triggers: state.loras[0].triggers.slice() };
close();
noteSettings({});
await open(state);
out.missingAgain = labels(v2);
out.settingsCalls = globalThis.__settingsCalls;
close();
console.log(JSON.stringify(out));
"""

PENDING_SCRIPT = HELPERS + """
const state = { loras: [], assets: [] };
await open(state);
const overlay = one("mmc-overlay");
const grid = one("mmc-lora-grid");
const out = { before: cards().length, settingsCalls: globalThis.__settingsCalls };
if (process.argv[1] === "close-settings") {
  close();
  const before = grid.children.slice();
  globalThis.__releaseSettings();
  await settle();
  out.after = cards().length;
  out.listings = globalThis.__listingCalls;
  out.unchanged = grid.children.length === before.length
    && grid.children.every((node, i) => node === before[i]);
} else {
  globalThis.__releaseSettings();
  await settle();
  if (process.argv[1] === "close-listing") {
    close();
    const before = grid.children.slice();
    globalThis.__releaseLoras();
    await settle();
    out.after = cards().length;
    out.listings = globalThis.__listingCalls;
    out.unchanged = grid.children.length === before.length
      && grid.children.every((node, i) => node === before[i]);
  } else {
    out.labels = labels(v2);
    close();
  }
}
out.closed = !overlay.isConnected;
console.log(JSON.stringify(out));
"""

with layout.pack(skip=("atlas",), extra_stubs={"api.js": API}) as target:
    got = layout.in_pack(SCRIPT, target, "roundtrip")
    persisted = layout.in_pack(PENDING_SCRIPT, target, "persisted")
    closing = layout.in_pack(PENDING_SCRIPT, target, "close-settings")
    listing = layout.in_pack(PENDING_SCRIPT, target, "close-listing")

V1 = "Lighting/StudioLighting_V1.safetensors"
V2 = "Lighting/StudioLighting_V2.safetensors"
LABELS = ["Studio illumination", "Example base · Softbox"]
METADATA_LABELS = ["Embedded training name", "Embedded base · 2"]
check("missing setting preserves original grouped title and metadata subtitle",
      got["defaults"], {"count": 2, "newest": METADATA_LABELS,
                        "legacy": ["Legacy embedded name", "Legacy base · 1"]})
check("model id still groups two versions into one card", got["count"], 2)
check("newest uses its full filename, not a common prefix or sibling title",
      got["newest"], ["StudioLighting_V2", V2])
check("older responses fall back to the file instead of embedded metadata",
      got["legacy"], ["WindowLight_V1", "Lighting/WindowLight_V1.safetensors"])
check("switching to a sidecar-described file updates both labels", got["sidecar"], LABELS)
check("preview still points to the selected file", V1.replace("/", "%2F") in got["preview"], True)
check("adding still uses the actual name, weight and triggers", got["added"],
      {"name": V1, "strength": 0.7, "triggers": ["studio light"]})
check("switching back updates labels, preserves weight, and uses the selected triggers",
      got["switched"], {"labels": ["StudioLighting_V2", V2], "name": V2,
                        "strength": 0.42, "triggers": ["soft light"]})
check("display subtitles are searchable", got["searchSubtitle"], {"count": 1, "labels": LABELS})
check("display titles are searchable", got["searchTitle"], LABELS)
check("turning off filename display restores metadata and retains the selected setup",
      got["restored"], {"labels": METADATA_LABELS, "name": V2,
                        "strength": 0.42, "triggers": ["soft light"]})
check("removing the setting also restores metadata labels", got["missingAgain"], METADATA_LABELS)
check("reopening uses the current shared setting without another fetch", got["settingsCalls"], 1)
check("a saved true setting reaches the first cards even before another node mounts",
      persisted, {"before": 0, "settingsCalls": 1,
                  "labels": ["StudioLighting_V2", V2], "closed": True})
check("closing during settings loading prevents a listing and detached rendering",
      closing, {"before": 0, "settingsCalls": 1, "after": 0,
                "listings": 0, "unchanged": True, "closed": True})
check("closing during listing prevents detached rendering",
      listing, {"before": 0, "settingsCalls": 1, "after": 0,
                "listings": 1, "unchanged": True, "closed": True})
passed("LoRA card metadata stays the default and filename display is opt-in")
