"""Selected-file card labels, tested with the real manager and the DOM shim.

All LoRA names and metadata here are fictitious.
"""

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

API = """
import { readFileSync } from "node:fs";
const store = new Map();
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
    // A cached response predating the display fields must not use raw metadata.
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
    } else if (text.startsWith("/continuity/loras")) {
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

SCRIPT = domshim.DOM + """
import { openLoras } from "./web/creator/loras.js";

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
const state = { loras: [], assets: [] };
openLoras({ state, onChange() {} });
for (let i = 0; i < 4; i++) await new Promise((done) => setTimeout(done, 0));
const out = { count: cards().length, newest: labels(v2), legacy: labels(legacy) };

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
console.log(JSON.stringify(out));
"""

with layout.pack(skip=("atlas",), extra_stubs={"api.js": API}) as target:
    got = layout.in_pack(SCRIPT, target)

V1 = "Lighting/StudioLighting_V1.safetensors"
V2 = "Lighting/StudioLighting_V2.safetensors"
LABELS = ["Studio illumination", "Example base · Softbox"]
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
passed("LoRA card labels follow sidecar display fields and the selected file")
