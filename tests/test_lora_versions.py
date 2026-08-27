"""A model's versions on one card, and a slider LoRA's range.

Two things the manager used to leave to the user's memory of their own filenames.

**Versions.** A LoRA retrained four times is four files on disk, and it was four
cards: four near-identical thumbnails under four identical titles, with nothing
on any of them saying that the other three existed. Now the files a model has
are one card and the version is a row of pills wearing only the part of the name
that differs — which is also the part you are choosing between. Clicking one
while another is in the stack is a swap in place, so changing version keeps the
weight you dialled in and the checkpoint you pinned it to; the pin says which
version the card opens on tomorrow.

The grouping has to be careful in one direction in particular: Wan's split
LoRAs ship a high-noise file and a low-noise one under a single model id, and
those two go in a stack *together*. A card offering a choice between them would
be a card that hides half of what you need, so they stay two cards.

**Range.** A style LoRA lives inside ±2 and a slider LoRA is trained to be
driven to ±10 and past it. One track for both is a track where the whole useful
range of every ordinary LoRA is a few pixels wide, so the span is a control on
the row — picked for you off the file's own name, then yours — and the weight
beside it is typed, which is the one way to reach any value at all.

    python3 tests/test_lora_versions.py

Skips itself if node is not installed.
"""

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

# Three retrains of one character, the two halves of one split LoRA, and a
# slider — the three shapes the grouping has to tell apart.
LENA = [
    {"name": "chars/lena_v1.safetensors", "base": "lena_v1",
     "trained_words": ["lena woman"], "strength": 0.9},
    {"name": "chars/lena_v2.safetensors", "base": "lena_v2",
     "trained_words": ["lena v2 woman"], "strength": 0.8},
    # Out of order on purpose: the card sorts naturally, so v10 lands after v2
    # rather than between v1 and v2 the way a plain string sort would put it.
    {"name": "chars/lena_v10.safetensors", "base": "lena_v10",
     "trained_words": ["lena woman"], "strength": 0.7},
]
SPLIT = [
    {"name": "wan/detail_high_noise.safetensors", "base": "detail_high_noise",
     "model_id": 42, "trained_words": [], "strength": 1.0},
    {"name": "wan/detail_low_noise.safetensors", "base": "detail_low_noise",
     "model_id": 42, "trained_words": [], "strength": 1.0},
]
SLIDER = [
    {"name": "sliders/age_slider.safetensors", "base": "age_slider",
     "trained_words": [], "strength": None},
]

ROWS = {
    "": LENA + SPLIT + SLIDER,
    "chars": LENA,
    "wan": SPLIT,
    "sliders": SLIDER,
}

FOLDERS = [{"path": "", "count": 6}, {"path": "chars", "count": 3},
           {"path": "wan", "count": 2}, {"path": "sliders", "count": 1}]

API = """
import { readFileSync } from "node:fs";
const store = new Map();
globalThis.__userdata = store;
const ROWS = JSON.parse(process.env.MMC_ROWS);
const FOLDERS = JSON.parse(process.env.MMC_FOLDERS);
export const api = {
  apiURL: (u) => u,
  addEventListener() {}, removeEventListener() {},
  async fetchApi(url, init) {
    const text = String(url);
    if (text.startsWith("/continuity/families")) {
      const body = readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
    }
    if (text.startsWith("/continuity/loras_named")) {
      const asked = JSON.parse(init.body).names;
      const all = ROWS[""];
      const found = asked.map((n) => all.find((r) => r.name === n)).filter(Boolean);
      return { ok: true, status: 200, json: async () => ({
        loras: found, folders: FOLDERS, missing: [],
      }) };
    }
    if (text.startsWith("/continuity/loras")) {
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
const fire = (node, type, event = {}) =>
  (node?.listeners?.[type] ?? []).forEach((fn) => fn({
    stopPropagation() {}, preventDefault() {}, currentTarget: node, target: node, ...event,
  }));
const click = (node) => fire(node, "click");
const settle = async () => { for (let i = 0; i < 4; i += 1) await new Promise((d) => setTimeout(d, 0)); };

async function open(state, options = {}) {
  document.body.children.length = 0;
  openLoras({ state, onChange() {}, ...options });
  await settle();
  return state;
}

const cards = () => all("mmc-lora").filter((node) => find("mmc-lora-art", node));
// Loud rather than falling back on document.body, which is what `find` does
// when handed nothing and which turns "the card is not there" into a click on
// whichever card happens to be first.
const card = (title) => {
  const hit = cards().find((node) => find("mmc-lora-name", node)?.textContent === title);
  if (!hit) throw new Error("no card titled " + title);
  return hit;
};
const pills = (title) => all("mmc-ver", card(title));
const pill = (title, label) => pills(title).find((node) => node.textContent === label);
const shown = (title) => pills(title).find((node) => node.attrs["aria-pressed"] === "true");
const add = (title) => click(find("mmc-lora-art", card(title)));
const rangeIn = (node) => node.querySelectorAll("input").find((n) => n.attrs.type === "range");

const out = {};

// ---- 1. one model, one card -------------------------------------------------

{
  await open({ loras: [], assets: [] });
  out.grouped = {
    // Six files, four cards: three lenas became one, and the split pair did not.
    cards: cards().length,
    pills: pills("lena").map((node) => node.textContent),
    // Nothing pinned and nothing in the stack, so the card opens on the newest
    // — which natural order says is v10, not v2.
    opensOn: shown("lena")?.textContent ?? null,
    split: cards().map((node) => find("mmc-lora-name", node).textContent).sort(),
  };

  // The folder picker still decides what is on screen; grouping happens inside
  // whatever it sent.
  const picker = find("mmc-folder");
  picker.value = "chars";
  fire(picker, "change", { target: picker });
  await settle();
  out.scoped = { cards: cards().length, pills: pills("lena").length };

  // Back to everything: the scope is remembered across openings, and the cases
  // below want the whole collection.
  picker.value = "";
  fire(picker, "change", { target: picker });
  await settle();
}

// ---- 2. switching version keeps the setup -----------------------------------

{
  const state = await open({ loras: [], assets: [] });
  add("lena");
  const slider = rangeIn(find("mmc-lora-ctl", card("lena")));
  fire(slider, "input", { target: { value: "0.42" } });
  fire(slider, "change");
  state.loras[0].modes = ["ref2va"];   // one of this family's routed slots
  out.before = { name: state.loras[0].name, strength: state.loras[0].strength };

  click(pill("lena", "v1"));
  out.after = {
    // One entry still, on the other file, at the weight it was dialled to.
    count: state.loras.length,
    name: state.loras[0].name,
    strength: state.loras[0].strength,
    modes: state.loras[0].modes.slice(),
    // ...and the words came from the file now loaded, not the one that left.
    triggers: state.loras[0].triggers.slice(),
  };
}

// ---- 3. a pin outlives the window -------------------------------------------

{
  await open({ loras: [], assets: [] });
  click(pill("lena", "v2"));                 // nothing in the stack: only a look
  click(find("mmc-ver-pin", card("lena")));
  await settle();

  await open({ loras: [], assets: [] });
  out.pinned = {
    opensOn: shown("lena")?.textContent ?? null,
    marked: find("mmc-ver-pin", card("lena")).className.includes("on"),
  };
}

// ---- 4. the range follows the LoRA ------------------------------------------

{
  const state = await open({ loras: [], assets: [] });
  add("lena");
  out.styleSpan = find("mmc-lora-span", card("lena")).textContent;

  // Nothing but its own name says this one is a slider, and that is enough:
  // ±2 would put its whole working range inside a fifth of the track.
  add("age_slider");
  const box = card("age_slider");
  out.sliderSpan = find("mmc-lora-span", box).textContent;
  out.sliderTrack = rangeIn(find("mmc-lora-ctl", box)).attrs.max;

  // Typed rather than dragged, and past what the track can reach: the span
  // follows instead of clipping the number.
  const num = find("mmc-lora-num", box);
  fire(num, "change", { target: { value: "14" } });
  const after = state.loras.find((entry) => entry.name === "sliders/age_slider.safetensors");
  out.typed = {
    strength: after.strength,
    span: find("mmc-lora-span", card("age_slider")).textContent,
    track: rangeIn(find("mmc-lora-ctl", card("age_slider"))).attrs.max,
  };
}

console.log(JSON.stringify(out));
"""


import json
import os

with layout.pack(skip=("atlas",), extra_stubs={"api.js": API}) as target:
    os.environ["MMC_ROWS"] = json.dumps(ROWS)
    os.environ["MMC_FOLDERS"] = json.dumps(FOLDERS)
    got = layout.in_pack(SCRIPT, target)

# ---- one model, one card ----------------------------------------------------

check("six files draw four cards", got["grouped"]["cards"], 4)
check("the pills wear what differs, in natural order",
      got["grouped"]["pills"], ["v1", "v2", "v10"])
check("...and the card opens on the newest of them", got["grouped"]["opensOn"], "v10")
# The one direction the grouping must not be clever in: these two go in a stack
# together, so a card offering a choice between them would hide half the answer.
check("a split LoRA's two halves stay two cards", got["grouped"]["split"],
      ["age_slider", "detail_high_noise", "detail_low_noise", "lena"])
check("a folder still decides what is on screen", got["scoped"], {"cards": 1, "pills": 3})

# ---- switching version ------------------------------------------------------

check("switching version replaces rather than adds", got["after"]["count"], 1)
check("...to the file that was clicked", got["after"]["name"], "chars/lena_v1.safetensors")
check("...at the weight it was dialled to", got["after"]["strength"], 0.42)
check("...on the checkpoint it was pinned to", got["after"]["modes"], ["ref2va"])
# The half that does not carry over, and should not: a retrain renames its
# words, and the old ones would be prompting for something not loaded.
check("...with the trigger words of the file now loaded",
      got["after"]["triggers"], ["lena woman"])

# ---- pinning ----------------------------------------------------------------

check("a pinned version is what the card opens on next time",
      got["pinned"], {"opensOn": "v2", "marked": True})

# ---- the range follows the LoRA ---------------------------------------------

check("an ordinary LoRA gets the tight span", got["styleSpan"], "\u00b12")
check("a LoRA whose own name says slider opens wide", got["sliderSpan"], "\u00b110")
check("...and its track goes there", got["sliderTrack"], 10)
check("a typed weight past the track widens the span rather than clipping it",
      got["typed"], {"strength": 14, "span": "\u00b125", "track": 25})

passed("a model's versions are one card you can switch and pin, "
       "and the weight's range follows the LoRA")
