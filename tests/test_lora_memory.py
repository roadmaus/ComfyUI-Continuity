"""What the LoRA manager remembers, and the four ways that shows.

Everything here is about the window outliving itself. The manager used to
remember exactly one thing — which folder you were in — and every other decision
lived on the entry in creator_data, which is to say it lived until the LoRA left
the stack. A strength you arrived at by trying it, and the two words out of the
sidecar's nine that actually did anything, were thrown away by the ✕ and started
again from the file's own guess the next time you reached for it.

Four claims, one per thing that now survives:

- what a LoRA was set to comes back when it is added again, on any node, and the
  sidecar is still what a LoRA nobody has used yet starts from;
- a trigger word of your own survives being switched off, which the old flat
  `entry.triggers` could not express at all — and can still be forgotten for
  good, which is the affordance switching-off used to double as;
- opening the manager from a chip lands on that LoRA, in whatever folder it is
  in, rather than at the top of the newest one;
- a star is a way back to a file, and a shelf reads by name rather than by
  scanning — which is the whole point, since a favorite can easily sit in a
  folder past the listing cap.

Then the Stacks tab, which is the preset store wearing this window's clothes: a
saved stack has to be a body the preset library would have written, or the two
halves will drift and a stack kept here will not open over there.

    python3 tests/test_lora_memory.py

Skips itself if node is not installed.
"""

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

# A collection with a folder deep enough that "the newest of what fits" would not
# reach it, which is what `reveal` and the shelves are both about.
ROWS = {
    "": [
        {"name": "new.safetensors", "base": "new", "trained_words": ["shiny"], "strength": 1.0},
        {"name": "chars/lena.safetensors", "base": "lena",
         "trained_words": ["lena woman", "portrait"], "strength": 0.9},
        {"name": "style/ink.safetensors", "base": "ink", "trained_words": [], "strength": 0.6},
    ],
    "chars": [
        {"name": "chars/lena.safetensors", "base": "lena",
         "trained_words": ["lena woman", "portrait"], "strength": 0.9},
    ],
    "style": [
        {"name": "style/ink.safetensors", "base": "ink", "trained_words": [], "strength": 0.6},
    ],
}

# The listing routes, answered off ROWS. `loras_named` is the one that matters
# here: it is what a shelf is built on, and it answers for files by name rather
# than by walking a folder, so a starred file is reachable wherever it sits.
API = """
import { readFileSync } from "node:fs";
const store = new Map();
globalThis.__userdata = store;
const ROWS = JSON.parse(process.env.MMC_ROWS);
const FOLDERS = [{path: "", count: 3}, {path: "chars", count: 1}, {path: "style", count: 1}];
globalThis.__calls = [];
export const api = {
  apiURL: (u) => u,
  addEventListener() {}, removeEventListener() {},
  async fetchApi(url, init) {
    const text = String(url);
    globalThis.__calls.push(text.split("?")[0]);
    if (text.startsWith("/minimax_creator/families")) {
      const body = readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
    }
    if (text.startsWith("/minimax_creator/loras_named")) {
      const asked = JSON.parse(init.body).names;
      const all = ROWS[""];
      const found = asked.map((n) => all.find((r) => r.name === n)).filter(Boolean);
      return { ok: true, status: 200, json: async () => ({
        loras: found, folders: FOLDERS,
        missing: asked.filter((n) => !all.some((r) => r.name === n)),
      }) };
    }
    if (text.startsWith("/minimax_creator/loras")) {
      const folder = new URLSearchParams(text.split("?")[1] || "").get("folder") || "";
      const rows = ROWS[folder] ?? [];
      return { ok: true, status: 200, json: async () => ({
        loras: rows, folders: FOLDERS, folder, matched: rows.length, truncated: false,
      }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  },
  async getUserData(file) {
    return store.has(file)
      ? { status: 200, json: async () => JSON.parse(store.get(file)) }
      : { status: 404, json: async () => null };
  },
  async storeUserData(file, value) { store.set(file, JSON.stringify(value)); return { status: 200 }; },
  async deleteUserData(file) { store.delete(file); return { status: 204 }; },
};
"""

SCRIPT = domshim.DOM + """
import { openLoras } from "./web/creator/loras.js";

const find = (cls, node = document.body) => {
  if (node.className && String(node.className).split(" ").includes(cls)) return node;
  for (const kid of node.children ?? []) {
    const hit = find(cls, kid);
    if (hit) return hit;
  }
  return null;
};
const all = (cls, node = document.body, out = []) => {
  if (node.className && String(node.className).split(" ").includes(cls)) out.push(node);
  for (const kid of node.children ?? []) all(cls, kid, out);
  return out;
};
// The shim keeps handlers in `listeners`; el() put every `onclick` there.
const fire = (node, type, event = {}) =>
  (node?.listeners?.[type] ?? []).forEach((fn) => fn({
    stopPropagation() {}, preventDefault() {}, currentTarget: node, target: node, ...event,
  }));
const click = (node) => fire(node, "click");
const settle = async () => { for (let i = 0; i < 4; i += 1) await new Promise((d) => setTimeout(d, 0)); };

// The manager edits in place and only resolves on Done, so each case holds the
// state it handed in and reads it back once the window has been driven.
async function open(state, options = {}) {
  document.body.children.length = 0;
  openLoras({ state, onChange() {}, ...options });
  await settle();          // the prefs read, then the listing it triggers
  return state;
}

const card = (base) => all("mmc-lora").find(
  (node) => find("mmc-lora-name", node)?.textContent === base);
const add = (base) => { click(find("mmc-lora-art", card(base))); };
const rangeIn = (node) => node.querySelectorAll("input").find((n) => n.attrs.type === "range");
const tab = (label) => all("mmc-tab").find((node) => node.textContent === label);

const out = {};

// ---- 1. what a LoRA was set to comes back -----------------------------------

{
  const first = await open({ loras: [], assets: [] });
  add("lena");
  // Driven through the controls rather than written onto the entry, so what is
  // remembered is what the window actually commits.
  const slider = rangeIn(find("mmc-lora-ctl", card("lena")));
  fire(slider, "input", { target: { value: "0.42" } });
  fire(slider, "change");
  // Two sidecar words offered; one dropped.
  const chips = all("mmc-trig", find("mmc-trigs", card("lena")));
  click(chips.find((chip) => chip.textContent === "lena woman"));
  out.left = { strength: first.loras[0].strength, triggers: first.loras[0].triggers.slice() };

  // A different node entirely, opened fresh: the memory is per file, not per
  // piece, which is the whole claim.
  const second = await open({ loras: [], assets: [] });
  add("lena");
  out.restored = { strength: second.loras[0].strength, triggers: second.loras[0].triggers };
  out.memoNote = !!find("mmc-lora-memo", card("lena"));

  // ...and one nobody has touched still starts from its sidecar.
  add("new");
  const fresh = second.loras.find((entry) => entry.name === "new.safetensors");
  out.fresh = { strength: fresh.strength, triggers: fresh.triggers };
  out.freshNote = !!find("mmc-lora-memo", card("new"));
}

// ---- 2. a word of your own survives being switched off ----------------------

{
  const state = await open({ loras: [], assets: [] });
  add("ink");                                   // no sidecar words at all
  const box = () => find("mmc-trigs", card("ink"));
  const input = find("mmc-trig-add", card("ink"));
  input.value = "sumi-e";
  fire(input, "keydown", { key: "Enter", target: input });
  out.typed = state.loras[0].triggers.slice();

  // Off, and still a chip. The old flat list dropped the word and the chip with
  // it, and there was no way back but typing it again.
  click(find("mmc-trig-word", all("mmc-trig", box())[0]));
  out.afterOff = {
    inPrompt: state.loras[0].triggers.slice(),
    stillAChip: all("mmc-trig", box()).length,
  };

  // ...so the ✕ is what removes it for good, now that a second click does not.
  click(find("mmc-trig-forget", all("mmc-trig", box())[0]));
  out.afterForget = all("mmc-trig", box()).length;
}

// ---- 3. opening on one LoRA -------------------------------------------------

{
  // Its own folder, not the one the window was last left in: the name says
  // where the file is, and no other scope is guaranteed to hold it.
  await open({ loras: [], assets: [] }, { reveal: "chars/lena.safetensors" });
  out.revealed = {
    scope: find("mmc-folder").value,
    marked: all("mmc-lora-found").length,
    which: find("mmc-lora-name", all("mmc-lora-found")[0])?.textContent ?? null,
  };
}

// ---- 4. stars, and a shelf read by name -------------------------------------

{
  await open({ loras: [], assets: [] });
  click(find("mmc-lora-star", card("lena")));
  await settle();
  globalThis.__calls.length = 0;
  const picker = find("mmc-folder");
  picker.value = ":favorites";
  fire(picker, "change", { target: picker });
  await settle();
  out.shelf = {
    // By name: the one route a listing cap cannot hide a starred file behind.
    route: globalThis.__calls.some((url) => url.endsWith("/loras_named")),
    showing: all("mmc-lora").map((node) => find("mmc-lora-name", node).textContent),
  };
}

// ---- 5. a saved stack is a preset body --------------------------------------

{
  await open({ assets: [], loras: [
    { name: "chars/lena.safetensors", strength: 0.7, enabled: true, modes: [], triggers: ["lena woman"] },
    { name: "style/ink.safetensors", strength: 1.1, enabled: false, modes: [], triggers: [] },
  ] });
  click(tab("Stacks"));
  await settle();
  find("mmc-stack-name").value = "the look";
  click(find("mmc-add", find("mmc-stack-save")));
  await settle();

  const index = JSON.parse(globalThis.__userdata.get("minimax_creator.presets.json"));
  const row = index.presets[0];
  const body = JSON.parse(globalThis.__userdata.get(
    "minimax_creator.preset." + row.id + ".json"));
  out.stack = { name: row.name, sections: row.sections, entries: body.data.loras };

  // ...and what applying one does to a node that already has something on it.
  const held = () => ({ name: "new.safetensors", strength: 1, enabled: true, modes: [], triggers: [] });

  const merged = await open({ loras: [held()], assets: [] });
  click(tab("Stacks"));
  await settle();
  click(find("mmc-ghost", find("mmc-stack")));                 // Add
  out.merged = merged.loras.map((entry) => entry.name);

  const replaced = await open({ loras: [held()], assets: [] });
  click(tab("Stacks"));
  await settle();
  click(find("mmc-add", find("mmc-stack")));                   // Replace
  out.replaced = replaced.loras.map((entry) => entry.name);
}

console.log(JSON.stringify(out));
"""

import json
import os

with layout.pack(skip=("atlas",), extra_stubs={"api.js": API}) as target:
    os.environ["MMC_ROWS"] = json.dumps(ROWS)
    got = layout.in_pack(SCRIPT, target)

# ---- what it was set to comes back ------------------------------------------

check("the window commits what its controls were dragged to", got["left"],
      {"strength": 0.42, "triggers": ["portrait"]})
check("a LoRA comes back at the strength it was left at", got["restored"]["strength"], 0.42)
check("...with the sidecar words that were actually kept, and not the dropped one",
      got["restored"]["triggers"], ["portrait"])
check("...and says the setup is yours rather than the file's", got["memoNote"], True)
check("a LoRA nobody has used still starts from its sidecar's weight",
      got["fresh"]["strength"], 1.0)
check("...and its sidecar's words", got["fresh"]["triggers"], ["shiny"])
check("...with nothing claiming you set it", got["freshNote"], False)

# ---- a word of your own -----------------------------------------------------

check("a typed word goes into the prompt", got["typed"], ["sumi-e"])
check("...switching it off takes it out of the prompt", got["afterOff"]["inPrompt"], [])
check("...and leaves the chip, which is what could not be expressed before",
      got["afterOff"]["stillAChip"], 1)
check("...and the ✕ is what forgets it", got["afterForget"], 0)

# ---- opening on one ---------------------------------------------------------

check("the window opens on the folder holding the LoRA it was asked for",
      got["revealed"]["scope"], "chars")
check("...marking exactly one card", got["revealed"]["marked"], 1)
check("...and it is that one", got["revealed"]["which"], "lena")

# ---- shelves ----------------------------------------------------------------

check("a shelf is read by name, not by scanning a folder", got["shelf"]["route"], True)
check("...and holds what was starred", got["shelf"]["showing"], ["lena"])

# ---- stacks -----------------------------------------------------------------

check("a saved stack is filed under the name it was given", got["stack"]["name"], "the look")
# The claim that keeps this window and the preset library in step: one section,
# and it is the same one `presets.capturePiece` writes.
check("...as a preset holding nothing but its LoRAs", got["stack"]["sections"], ["loras"])
check("...through the same serializer, muted entries and all",
      got["stack"]["entries"],
      [{"name": "chars/lena.safetensors", "strength": 0.7, "triggers": ["lena woman"]},
       {"name": "style/ink.safetensors", "strength": 1.1, "enabled": False}])
check("Add leaves what was already on the node",
      got["merged"], ["new.safetensors", "chars/lena.safetensors", "style/ink.safetensors"])
check("...and Replace does not",
      got["replaced"], ["chars/lena.safetensors", "style/ink.safetensors"])

passed("the manager remembers what you set, opens where you point it, "
       "shelves what you star, and keeps a stack as a preset")
