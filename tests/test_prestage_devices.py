"""A still's weights can be pinned to a device the way a clip's can.

The pre-stage once had no device control at all: its manifests said
`"device": False` for every field, `render_image.ImageWeights` had nowhere to
keep a pin, and the popover drew no pill. These pin the frontend half of the
fix against the Python half:

- which fields can be pinned is the manifest's answer, which
  `render_image.manifest_weight` derives from `render_image.LOADERS` against
  `models.MULTIGPU` — the rule the video slots follow;
- a side's pins survive `serializePreStage` / `parsePreStage`, per arch, and a
  pin on a field nothing can move is dropped as `models.pinned_devices` drops it;
- the weights popover draws the same device pill the Creator's does, and a pick
  in it lands on the side and in the machine's memory.
"""
import json

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

pkg = layout.load("models", "render_image")
ri, core = pkg.render_image, pkg.models

SCRIPT = r'''
const S = await import("./web/creator/state.js");
const M = await import("./web/creator/models.js");
const { PreStageRow } = await import("./web/creator/prestage.js");
const out = {};
out.fields = S.PRESTAGE_DEVICE_FIELDS;

const raw = {
  arch: "krea2", prompt: "x",
  models: {
    krea2: { model: "k.safetensors", clip: "c.safetensors", vae: "v.safetensors",
             devices: { clip: "cuda:1", vae: " cpu ", nonsense: "cuda:0", model: "" } },
    ideogram4: { model: "i.safetensors", devices: { uncond_model: "cuda:1" } },
    qwen21: { control: "branch.safetensors", devices: { control: "cuda:1" } },
  },
};
const state = S.parsePreStage(JSON.stringify(raw));
out.parsed = structuredClone(Object.fromEntries(
  S.PRESTAGE_IMAGE_ARCHES.map((a) => [a, state.models[a].devices])));
out.saved = JSON.parse(S.serializePreStage(state)).models;
out.reopened = S.parsePreStage(S.serializePreStage(state)).models.krea2.devices;
out.empty = JSON.parse(S.serializePreStage(S.parsePreStage(JSON.stringify({ arch: "krea2" })))).models ?? null;

// The popover, with ComfyUI-MultiGPU "installed": the listing names devices,
// which is all the pill keys off.
const { api } = await import("./../scripts/api.js");
const fetchApi = api.fetchApi.bind(api);
api.fetchApi = async (url, options = {}) => String(url) === "/continuity/models"
  ? { ok: true, status: 200, json: async () => ({ files: {}, by_folder: {},
      devices: ["cpu", "cuda:0", "cuda:1"] }) }
  : fetchApi(url, options);
await new Promise((resolve) => { if (M.loadCatalog(resolve)) resolve(); });
// The chat room's own construction (`chat.js openFiles`).
const io = { value: (name, fallback) => fallback, set: () => {} };
const row = new PreStageRow({ state, widgetIO: () => io, commit() {} });
const all = (n) => [n, ...n.children.flatMap(all)];
const pills = () => all(document.body).filter((n) => n.classList.contains("mmc-weight-device"));
const anchor = document.createElement("button");
document.body.appendChild(anchor);
row.openWeights(anchor);
out.pills = pills().map((p) => p.textContent);
out.label = all(row.renderWeightsPill()).map((n) => n.textContent).filter(Boolean).at(-1);
// Pin the DiT through the pill's own choice list: it lands on the side and in
// the machine's memory, beside the files rather than instead of them.
pills()[0].listeners.click[0]({ currentTarget: pills()[0] });
const list = all(document.body).filter((n) => n.classList.contains("mmc-pop-list")).at(-1);
const choice = list?.children.find((n) => all(n).some((c) => c.textContent === "cuda:0"));
choice?.listeners.click[0]({ currentTarget: choice });
out.pickedPin = state.models.krea2.devices.model ?? null;
await new Promise((r) => setTimeout(r, 0));
out.remembered = globalThis.__settings.weights?.krea2 ?? null;
console.log(JSON.stringify(out));
'''

with layout.pack(skip=["atlas"]) as target:
    got = layout.in_pack(DOM + SCRIPT, target)

# ---- which fields: the manifest's, from the loader table ------------------------

catalog = {f["id"]: f for f in json.loads(layout.catalog_json())["families"]}
for arch, fields in got["fields"].items():
    family = next(f for f in catalog.values()
                  if f["id"] == arch or f.get("legacy_still_block") == arch)
    want = [w["id"] for w in family["weights"]
            if ri.LOADERS.get(w["id"]) in core.MULTIGPU]
    check(f"{arch}: the pinnable fields are the ones a MultiGPU loader wraps", fields, want)
check("a ControlNet branch cannot be pinned (ModelPatchLoader is not wrapped)",
      "control" in got["fields"]["qwen21"], False)
check("...but a still's encoder can", "clip" in got["fields"]["krea2"], True)

# ---- parse / save, per side -----------------------------------------------------

check("pins are read per side, trimmed, and only for fields that can move",
      {a: d for a, d in got["parsed"].items() if d},
      {"krea2": {"clip": "cuda:1", "vae": "cpu"}, "ideogram4": {"uncond_model": "cuda:1"}})
check("...matching the Python reading of the same block",
      core.pinned_devices(
          {"clip": "cuda:1", "vae": " cpu ", "nonsense": "cuda:0", "model": ""},
          {name: ri.LOADERS.get(name) for name in ("model", "turbo_model", "clip", "vae",
                                                    "nonsense")}),
      {"clip": "cuda:1", "vae": "cpu"})
check("saved on the side they belong to",
      (got["saved"]["krea2"].get("devices"), got["saved"]["ideogram4"].get("devices"),
       "devices" in got["saved"].get("qwen21", {})),
      ({"clip": "cuda:1", "vae": "cpu"}, {"uncond_model": "cuda:1"}, False))
check("and read back unchanged", got["reopened"], {"clip": "cuda:1", "vae": "cpu"})
check("a node with nothing pinned saves no devices key", got["empty"], None)

# ---- the popover ----------------------------------------------------------------

check("the popover draws a device pill per pinnable field of the arch",
      got["pills"], ["auto", "auto", "cuda:1", "cpu"])
check("the weights pill reports the spread the way the Creator's does",
      got["label"], "weights · 2 devices")
check("a pick in the pill pins the field on the side", got["pickedPin"], "cuda:0")
check("...and the machine remembers the pins with the files",
      got["remembered"],
      {"model": "k.safetensors", "clip": "c.safetensors", "vae": "v.safetensors",
       "devices": {"clip": "cuda:1", "vae": "cpu", "model": "cuda:0"}})
