"""LoRAs on top of the routed checkpoint.

The node already decides which of the two H3 checkpoints comes back out, so it
is also the only place that knows what a LoRA would be patching. FL2VA and
Ref2VA are different weights: a LoRA trained against one does nothing on the
other, so every entry names the checkpoints it belongs to and is skipped when
the other one is routed. What a file *is* is the user's call: whether it keyed
onto anything is not second-guessed here — `comfy.lora.load_lora` logs the keys
it could not place, and that log is the whole story when one does nothing.

Loading goes through the stock path (`comfy.sd.load_lora_for_models`), which
means whatever ComfyUI can key onto the H3 DiT, this can too. There is no
MiniMax branch in `comfy.lora.model_lora_keys_unet`, so H3 LoRAs match through
the generic `diffusion_model.*` / `lora_unet_*` mapping.
"""

import os

import comfy.sd
import comfy.utils
import folder_paths

from .compile import active_loras

# One spare, no more. These files are ~700 MB each, and the point of holding any
# is only so re-queueing the same graph does not re-read from disk.
MAX_CACHED = 2

_CACHE = {}   # (path, mtime) -> state dict


def resolve(name):
    path = folder_paths.get_full_path("loras", name)
    if path is None:
        raise ValueError(f"LoRA not found in models/loras: {name}")
    return path


def _load(path):
    key = (path, os.path.getmtime(path))
    weights = _CACHE.get(key)
    if weights is None:
        while len(_CACHE) >= MAX_CACHED:
            _CACHE.pop(next(iter(_CACHE)))
        weights = comfy.utils.load_torch_file(path, safe_load=True)
        _CACHE[key] = weights
    return weights


def apply(model, entries, target, without=""):
    """Patch `model` with every enabled LoRA that claims the `target` checkpoint.

    `without` names one file to leave off — the turbo lead-in's, and nothing
    else so far. It is a name and not an index because the stack a payload
    carries is the merged one (`compile.merge_loras`), where a segment naming
    the same file replaces the piece's entry rather than adding to it, so the
    position of an entry is not stable and the file it names is.
    """
    for entry in active_loras(entries, target):
        if without and entry["name"] == without:
            continue
        weights = _load(resolve(entry["name"]))
        model = comfy.sd.load_lora_for_models(
            model, None, weights, float(entry.get("strength", 1.0)), 0)[0]
    return model
