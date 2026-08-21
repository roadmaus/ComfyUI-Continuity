"""LoRAs on top of the routed checkpoint.

The node already decides which of the two H3 checkpoints comes back out, so it
is also the only place that knows what a LoRA would be patching. FL2VA and
Ref2VA are different weights: a LoRA trained against one does nothing on the
other, so every entry names the checkpoints it belongs to and is skipped when
the other one is routed. What a file *is* is the user's call: whether it keyed
onto anything is not second-guessed here — the stack reports what it placed and
what it could not, and that report is the whole story when one does nothing.

**Loading does not go through the stock path any more.** `comfy.sd.load_lora_for_models`
is correct on a bf16 checkpoint and wrong on the quantized ones nearly everybody
runs H3 on, in three separate ways — a merge that requantizes the adapter into
rounding noise, adaLN pairs dropped for a basis mismatch, and key conventions
that resolve by guesswork. `h3lora` is the vendored answer to all three and its
own docstring argues the case; this module's job is to hand it the stack, in one
call, with the files this pack already has in memory.

One call and not one per LoRA, because a stack fuses: several adapters on one
layer concatenate along the rank axis into a single pair, so ten LoRAs cost one
extra matmul per layer rather than ten.
"""

import logging
import os

import folder_paths

from .compile import active_loras

LOG = logging.getLogger("minimax_creator")

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
    import comfy.utils

    key = (path, os.path.getmtime(path))
    weights = _CACHE.get(key)
    if weights is None:
        while len(_CACHE) >= MAX_CACHED:
            _CACHE.pop(next(iter(_CACHE)))
        weights = comfy.utils.load_torch_file(path, safe_load=True)
        _CACHE[key] = weights
    return weights


def stack(entries, target, without=""):
    """The rows `h3lora` takes: every enabled LoRA claiming `target`, in order.

    `without` names one file to leave off — the turbo lead-in's, and nothing
    else so far. It is a name and not an index because the stack a payload
    carries is the merged one (`compile.merge_loras`), where a segment naming
    the same file replaces the piece's entry rather than adding to it, so the
    position of an entry is not stable and the file it names is.

    `row` is the position on the strip and is passed through because that is
    what a per-row control would select on. `weights` is the file itself: this
    pack holds it already, and a piece of six segments applies the same stack
    six times.
    """
    rows = []
    for entry in active_loras(entries, target):
        if without and entry["name"] == without:
            continue
        path = resolve(entry["name"])
        rows.append({"name": entry["name"], "path": path,
                     "strength": float(entry.get("strength", 1.0)),
                     "weights": _load(path), "row": len(rows) + 1})
    return rows


def apply(model, entries, target, without=""):
    """Patch `model` with every enabled LoRA that claims the `target` checkpoint.

    Returns the model untouched when the stack is empty — a piece with no LoRAs
    must not pay for a clone, and must not depend on any of this being
    importable either.

    The report goes to the log rather than to the user: it is per-layer
    accounting — what merged, what ran as a live branch, what the adaLN port
    did, how far each file's real perturbation is from the strength it was given
    — and the place to read that is the console, beside the load lines it
    explains. What a *user* has to be told is said by raising.
    """
    rows = stack(entries, target, without=without)
    if not rows:
        return model

    from .h3lora import apply as h3lora

    patched, report = h3lora.apply_stack(model, rows)
    LOG.info("MiniMax Creator LoRAs:\n%s", report.text())
    return patched
