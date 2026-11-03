"""A LoRA pinned to a family: on every stack drawn for it, off every other.

The pin is a record in `loraPrefs` keyed by family, and `settlePins` is what
brings a stack in line with it before a face draws its row. Four claims:

- pinning from a chip writes the record with the chip's settings, and the chip
  is redrawn as the tack — the tile, the pin, three letters of the file;
- a stack on the pinned family that does not hold the file takes it, at the
  recorded settings, and a stack on any other family drops it;
- the pin follows the entry: a strength dialled on the pinned chip is what the
  next stack gets;
- unpinning leaves the chip in the stack as an ordinary one, and re-pinning on
  another family moves the record rather than copying it.

    python3 tests/test_lora_pins.py

Skips itself if node is not installed.
"""

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

API = """
import { readFileSync } from "node:fs";
const store = new Map();
globalThis.__userdata = store;
export const api = {
  apiURL: (u) => u,
  addEventListener() {}, removeEventListener() {},
  async fetchApi(url) {
    const text = String(url);
    if (text.startsWith("/continuity/families")) {
      const body = readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
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
import { loraBlock, settlePins, isPinned, pinsFor, setPinEnabled, watchPins } from "./web/creator/loras.js";
import { loadLoraPrefs } from "./web/creator/api.js";
import * as S from "./web/creator/state.js";

const all = (cls, node, out = []) => {
  if (node.className && String(node.className).split(" ").includes(cls)) out.push(node);
  for (const kid of node.children ?? []) all(cls, kid, out);
  return out;
};
const find = (cls, node) => all(cls, node)[0] ?? null;
const click = (node) => (node?.listeners?.click ?? []).forEach((fn) => fn({
  stopPropagation() {}, preventDefault() {}, currentTarget: node, target: node,
}));
const settle = async () => { for (let i = 0; i < 4; i += 1) await new Promise((d) => setTimeout(d, 0)); };

const CLAY = { name: "style/clayrender_v2.safetensors", strength: 0.8, enabled: true,
               triggers: ["clayrender"], modes: [] };
const out = {};

// A face: settles, then draws. `commits` counts what a real face would have
// written out.
function face(state, family) {
  const spy = { commits: 0 };
  const draw = () => {
    if (settlePins(state, family, () => { spy.commits += 1; draw(); })) spy.commits += 1;
    spy.root = loraBlock(state, {
      targets: null, family: S.DEFAULT_VIDEO_FAMILY, pinTo: family,
      onPinChange: () => { spy.commits += 1; draw(); },
      onToggle: (entry) => { S.toggleLora(state, entry.name); draw(); },
      onManage: () => {}, onSwap: () => {}, onRemove: () => {},
    });
  };
  draw();
  return spy;
}

// ---- cold: the first draw asks for the prefs and draws again when they land --
const krea = { loras: [{ ...CLAY }], assets: [] };
const first = face(krea, "krea2");
out.coldPinButtons = all("mmc-asset-pin", first.root).length;
await settle();
out.warmPinButtons = all("mmc-asset-pin", first.root).length;

// ---- pin it ----------------------------------------------------------------
click(find("mmc-asset-pin", first.root));
await settle();
const prefs = await loadLoraPrefs();
out.record = prefs.wears;
out.tack = { drawn: Boolean(find("mmc-tack", first.root)),
             mono: find("mmc-tack-mono", first.root)?.text,
             chips: all("mmc-asset", first.root).length };
out.pinned = isPinned(CLAY.name, "krea2");

// ---- another Krea stack takes it; a Flux stack drops it --------------------
const fresh = { loras: [], assets: [] };
const second = face(fresh, "krea2");
out.taken = fresh.loras.map((e) => ({ name: e.name, strength: e.strength, triggers: e.triggers }));
out.takenCommitted = second.commits;

const flux = { assets: [], loras: [{ ...CLAY }, { name: "style/other.safetensors", strength: 1, enabled: true, triggers: [], modes: [] }] };
const third = face(flux, "flux2klein");
out.dropped = flux.loras.map((e) => e.name);
out.droppedCommitted = third.commits;

// ---- the record follows the entry -----------------------------------------
fresh.loras[0].strength = 0.55;
face(fresh, "krea2");
out.followed = (await loadLoraPrefs()).wears.krea2[0].strength;
const later = { loras: [], assets: [] };
face(later, "krea2");
out.laterStrength = later.loras[0].strength;

// ---- a mute on a tack is a mute, not an unpin --------------------------------
click(find("mmc-asset-name", second.root));
out.mutedTack = { off: String(find("mmc-tack", second.root)?.className).includes(" off"),
                  stillPinned: isPinned(CLAY.name, "krea2") };
fresh.loras[0].enabled = true;

// ---- unpin leaves the chip; re-pin elsewhere moves the record ---------------
click(find("mmc-asset-pin", second.root));
out.unpinned = { chips: all("mmc-asset", second.root).length, tacks: all("mmc-tack", second.root).length,
                 still: fresh.loras.map((e) => e.name), record: (await loadLoraPrefs()).wears };
const moved = { loras: [{ ...CLAY }], assets: [] };
const fourth = face(moved, "flux2klein");
click(find("mmc-asset-pin", fourth.root));
face(moved, "h3");
out.moved = { record: Object.keys((await loadLoraPrefs()).wears), h3: moved.loras.map((e) => e.name) };

// ---- the mute is the pin's: kept, carried, and shown everywhere --------------
const INK = { name: "style/ink_v1.safetensors", strength: 0.7, enabled: true, triggers: [], modes: [] };
const node = { loras: [{ ...INK }], assets: [] };
const nodeFace = face(node, "krea2");
click(all("mmc-asset-pin", nodeFace.root).find((b) => !String(b.className).includes(" on")));
click(find("mmc-asset-name", all("mmc-tack", nodeFace.root).find((tack) => tack.text?.includes?.("ink")) ?? nodeFace.root));
const inkOf = (state) => state.loras.find((e) => e.name === INK.name);
out.inkMuted = { entry: inkOf(node)?.enabled,
                 record: (await loadLoraPrefs()).wears.krea2.find((p) => p.name === INK.name)?.enabled };
// The same stack, off to Flux and back: the pin comes off and goes back on muted.
face(node, "flux2klein");
out.inkAway = Boolean(inkOf(node));
face(node, "krea2");
out.inkBack = inkOf(node)?.enabled;
// A second stack already holding the pin takes the mute made on the first.
const other = { loras: [], assets: [] };
face(other, "krea2");
out.otherFresh = inkOf(other)?.enabled;
inkOf(node).enabled = true;
face(node, "krea2");
out.recordUnmuted = (await loadLoraPrefs()).wears.krea2.find((p) => p.name === INK.name)?.enabled;
out.otherFollows = { changed: settlePins(other, "krea2"), enabled: inkOf(other)?.enabled };
// The chat's switch: on the record, read back by pinsFor, taken by every stack,
// and every watching face told.
let told = 0;
const watcher = { pinsMoved() { told += 1; } };
watchPins(watcher, "pinsMoved");
out.chatBefore = pinsFor("krea2").find((p) => p.name === INK.name)?.enabled;
setPinEnabled(INK.name, "krea2", false);
await settle();
out.chatAfter = pinsFor("krea2").find((p) => p.name === INK.name)?.enabled;
out.told = told;
settlePins(node, "krea2"); settlePins(other, "krea2");
out.stacksFollowChat = [inkOf(node)?.enabled, inkOf(other)?.enabled];
out.notPinned = setPinEnabled("style/nothing.safetensors", "krea2", false);
// Settling twice in a row with nothing moved changes nothing.
out.stable = [settlePins(node, "krea2"), settlePins(other, "krea2")];

console.log(JSON.stringify(out));
"""

with layout.pack(skip=("atlas",), extra_stubs={"api.js": API}) as target:
    got = layout.in_pack(SCRIPT, target)

check("before the prefs land the chip has no pin to offer", got["coldPinButtons"], 0)
check("...and wears one once they have", got["warmPinButtons"], 1)
check("pinning writes the chip's settings under the family",
      got["record"], {"krea2": [{"name": "style/clayrender_v2.safetensors", "strength": 0.8,
                                 "triggers": ["clayrender"]}]})
check("...and the chip is redrawn as the tack",
      got["tack"], {"drawn": True, "mono": "cla", "chips": 1})
check("...which the module can be asked about", got["pinned"], True)
check("a new stack on the family takes the pin as recorded",
      got["taken"], [{"name": "style/clayrender_v2.safetensors", "strength": 0.8, "triggers": ["clayrender"]}])
check("...and says so, so it is written out", got["takenCommitted"], 1)
check("a stack on another family drops the pinned file and nothing else",
      got["dropped"], ["style/other.safetensors"])
check("...and says so", got["droppedCommitted"], 1)
check("a strength dialled on the pinned chip becomes the pin's", got["followed"], 0.55)
check("...and the next stack gets it", got["laterStrength"], 0.55)
check("muting a tack mutes it and keeps the pin", got["mutedTack"], {"off": True, "stillPinned": True})
check("unpinning leaves an ordinary chip in the stack",
      got["unpinned"]["chips"], 1)
check("...no tack", got["unpinned"]["tacks"], 0)
check("...the file still there", got["unpinned"]["still"], ["style/clayrender_v2.safetensors"])
check("...and no record", got["unpinned"]["record"], {})
check("pinning on another family moves the record", got["moved"]["record"], ["flux2klein"])
check("...and a third family's stack drops it", got["moved"]["h3"], [])

check("muting a pinned chip mutes the pin's record",
      got["inkMuted"], {"entry": False, "record": False})
check("...a stack switched to another family drops it", got["inkAway"], False)
check("...and switched back takes it muted, not on", got["inkBack"], False)
check("a new stack on the family takes the pin muted", got["otherFresh"], False)
check("bringing it back on one chip clears the record's mute", got.get("recordUnmuted"), None)
check("...and another stack holding it follows",
      got["otherFollows"], {"changed": True, "enabled": True})
check("the chat reads the pin's mute", got["chatBefore"], True)
check("...its switch writes the record", got["chatAfter"], False)
check("...and tells the faces watching", got["told"] >= 1, True)
check("...and every stack holding the pin follows it", got["stacksFollowChat"], [False, False])
check("...and a file that is not pinned is not", got["notPinned"], False)
check("settling an unmoved stack changes nothing", got["stable"], [False, False])
passed("a pin puts a LoRA on every stack of its family and takes it off every other")
