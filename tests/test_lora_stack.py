"""Which loader a family's LoRAs arrive on, and what a misplaced file does.

`lora.py` had one path: the vendored `h3lora` stack, which exists because the
stock loader is wrong on the quantized checkpoints nearly everybody runs H3 on.
That argument is about H3's weights and not about LoRAs, and a second video
family arrived with adapters of its own — LTX 2.5 takes LTX 2.3's, which is
Lightricks' own word — that core already knows how to place.

So the loader is the family's, declared once in `registry.LORA_STACK`, and this
suite holds three things about the split:

- every family says which stack it takes, and H3 is the only one on the
  vendored one;
- a core-stack family's LoRAs are patched the way `LoraLoaderModelOnly` patches
  them — model only, in stack order, at the strength the entry carries, off the
  file this pack already has in memory;
- a file that places *no* key raises. Nothing here inspects a LoRA to decide
  whether it belongs — what a file was trained for is not knowable from it with
  any confidence, and refusing on a guess would refuse the one that works — but
  a stack that patched nothing at all is a render that is about to come out as
  though the LoRA were not there, and that is worth a minute of somebody's life.

Core's own machinery is stubbed rather than driven: what is being tested is this
pack's dispatch and its accounting, and `test_h3lora.py` is where a real model
gets patched.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_lora_stack.py

Skips itself with a message where ComfyUI is missing.
"""

import os
import sys

import layout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import FAILURES, check, passed, skip

sys.path.insert(0, os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))

try:
    import comfy.lora
    import comfy.lora_convert
except Exception as exc:  # noqa: BLE001
    skip(f"ComfyUI not importable ({type(exc).__name__}: {exc})")

_pkg = layout.load("canvas", "registry", "contextir", "subjects", "compile")
registry = _pkg.registry

# `lora.py` imports `folder_paths`, which is ComfyUI's — hence the skip above.
lora = layout.load("lora").lora

# ---- the table ---------------------------------------------------------------

check("every family says which stack its LoRAs take",
      sorted(registry.LORA_STACK), sorted(registry.FAMILIES))
check("the vendored stack is H3's and nobody else's",
      [f for f, stack in registry.LORA_STACK.items() if stack == "h3lora"], ["h3"])
check("LTX 2.5 takes core's loader", registry.LORA_STACK["ltx25"], "core")

# ---- the dispatch ------------------------------------------------------------

ENTRIES = [{"name": "one.safetensors", "strength": 0.8},
           {"name": "two.safetensors", "strength": 1.0}]

# Neither the file nor its bytes are the point here, so the two things that
# touch a disk are stubbed and everything above them is the real module.
lora.resolve = lambda name: f"/models/loras/{name}"
lora._load = lambda path: {"stub": path}

took = []
_apply_core = lora._apply_core       # the real one, put back below
lora._apply_h3 = lambda model, rows: took.append(("h3lora", rows)) or "h3-patched"
lora._apply_core = lambda model, rows: took.append(("core", rows)) or "core-patched"

check("a piece with no LoRAs is not patched at all, whatever the family",
      (lora.apply("model", [], "", family="ltx25"), took), ("model", []))

check("H3's stack goes to the vendored path",
      lora.apply("model", ENTRIES, "fl2va", family="h3"), "h3-patched")
check("...and LTX's to core's", lora.apply("model", ENTRIES, "", family="ltx25"),
      "core-patched")
check("both were handed the same two rows, in order",
      [(which, [row["name"] for row in rows]) for which, rows in took],
      [("h3lora", ["one.safetensors", "two.safetensors"]),
       ("core", ["one.safetensors", "two.safetensors"])])
check("a family that routes between nothing selects on no claim",
      [row["name"] for row in lora.stack(
          [*ENTRIES, {"name": "h3-only.safetensors", "strength": 1.0,
                      "modes": ["fl2va"]}], "", family="ltx25")],
      ["one.safetensors", "two.safetensors", "h3-only.safetensors"])

# ---- core's path, on a patcher that counts -----------------------------------

lora._apply_core = _apply_core          # the real one from here on


class FakePatcher:
    """As much of a `ModelPatcher` as `_apply_core` touches: it clones, and it
    takes patches. `placed` is what core's `add_patches` returns — the keys that
    found a home, which is the number this pack raises on the absence of."""

    def __init__(self, places, model="the transformer"):
        self.model = model
        self.places = places          # per call, the keys "placed"
        self.calls = []
        self.clones = 0

    def clone(self):
        twin = FakePatcher(self.places, self.model)
        twin.calls, twin.clones = self.calls, self.clones + 1
        return twin

    def add_patches(self, patches, strength):
        self.calls.append((sorted(patches), strength))
        return self.places.pop(0)


mapped = {}
comfy.lora.model_lora_keys_unet = lambda model, key_map: mapped
comfy.lora.load_lora = lambda weights, key_map: {"diffusion_model.blocks.0": weights}
comfy.lora_convert.convert_lora = lambda weights: weights

rows = lora.stack(ENTRIES, "", family="ltx25")
patcher = FakePatcher(places=[["diffusion_model.blocks.0"], ["diffusion_model.blocks.0"]])
patched = lora._apply_core(patcher, rows)

check("each file is patched at the strength its entry carries",
      [strength for _, strength in patched.calls], [0.8, 1.0])
check("...onto a clone rather than the model handed in", patched.clones, 2)

nothing = FakePatcher(places=[[]])
try:
    lora._apply_core(nothing, rows[:1])
    FAILURES.append("a LoRA that placed no key should be raised on")
except ValueError as exc:
    check("...and the file that did nothing is named", "one.safetensors" in str(exc), True)

passed("a family's LoRAs take the loader its registry row names")
