"""LoRAs on top of the routed checkpoint.

The node already decides which of the two H3 checkpoints comes back out, so it
is also the only place that knows what a LoRA would be patching. FL2VA and
Ref2VA are different weights: a LoRA trained against one does nothing on the
other, so every entry names the checkpoints it belongs to and is skipped when
the other one is routed. What a file *is* is the user's call: whether it keyed
onto anything is not second-guessed here — the stack reports what it placed and
what it could not, and that report is the whole story when one does nothing.

**H3's loading does not go through the stock path.** `comfy.sd.load_lora_for_models`
is correct on a bf16 checkpoint and wrong on the quantized ones nearly everybody
runs H3 on, in three separate ways — a merge that requantizes the adapter into
rounding noise, adaLN pairs dropped for a basis mismatch, and key conventions
that resolve by guesswork. `h3lora` is the vendored answer to all three and its
own docstring argues the case; this module's job is to hand it the stack, in one
call, with the files this pack already has in memory.

One call and not one per LoRA, because a stack fuses: several adapters on one
layer concatenate along the rank axis into a single pair, so ten LoRAs cost one
extra matmul per layer rather than ten.

**Every other family goes through core's loader**, which is `registry.LORA_STACK`'s
whole content: the vendored stack is an argument about H3's weights, not about
LoRAs, and a second family's adapters are core's to place. Which is also the
right answer for keeping up — LTX 2.5 takes LTX 2.3's LoRAs, and the key
conventions those were written in are ComfyUI's business to track, not this
pack's.

**A file pointed at the wrong weights is the user's mistake, and is raised as
one.** Nothing here inspects a LoRA to decide whether it belongs: what it is
trained for is not knowable from the file with any confidence, and refusing a
file on a guess would be refusing the one that works. What *is* knowable is
whether it landed — a stack that placed no key at all patched nothing, and
saying so beats a render that comes out looking exactly as it would have with
no LoRA at all.
"""

import logging
import os

import folder_paths

from .compile import active_loras
from .families import registry

LOG = logging.getLogger("continuity")

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


def stack(entries, target, without="", family=registry.DEFAULT_VIDEO):
    """The rows the stack takes: every enabled LoRA claiming `target`, in order.

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
    for entry in active_loras(entries, target, family):
        if without and entry["name"] == without:
            continue
        path = resolve(entry["name"])
        rows.append({"name": entry["name"], "path": path,
                     "strength": float(entry.get("strength", 1.0)),
                     "weights": _load(path), "row": len(rows) + 1})
    return rows


def apply(model, entries, target, without="", family=registry.DEFAULT_VIDEO):
    """Patch `model` with every enabled LoRA that claims the `target` checkpoint.

    Returns the model untouched when the stack is empty — a piece with no LoRAs
    must not pay for a clone, and must not depend on any of this being
    importable either.

    Which stack does the patching is the family's, off `registry.LORA_STACK`;
    see this module's own docstring for the whole of the argument.
    """
    rows = stack(entries, target, without=without, family=family)
    if not rows:
        return model
    if registry.LORA_STACK.get(family) == "h3lora":
        return _apply_h3(model, rows)
    return _apply_core(model, rows)


def _apply_h3(model, rows):
    """The vendored stack, in one call.

    The report goes to the log rather than to the user: it is per-layer
    accounting — what merged, what ran as a live branch, what the adaLN port
    did, how far each file's real perturbation is from the strength it was given
    — and the place to read that is the console, beside the load lines it
    explains. What a *user* has to be told is said by raising.
    """
    from .h3lora import apply as h3lora

    patched, report = h3lora.apply_stack(model, rows)
    LOG.info("Continuity LoRAs:\n%s", report.text())
    return patched


def _apply_core(model, rows):
    """ComfyUI's own loader, one file at a time — `LoraLoaderModelOnly` written
    out, so the already-loaded file is reused instead of read again.

    Model only, no CLIP half: these families' LoRAs are transformer adapters,
    which is also how their official workflows patch them.

    A file that placed no key is raised on. Core logs a `NOT LOADED` line per
    unmatched key and carries on, which is right for the ordinary case of an
    adapter that covers some layers and not others, and wrong for the case that
    actually happens to people — an H3 LoRA left in the stack of a piece that
    has been switched to another family, quietly doing nothing to a render they
    are waiting on.
    """
    import comfy.lora
    import comfy.lora_convert

    patched = model
    for row in rows:
        key_map = comfy.lora.model_lora_keys_unet(patched.model, {})
        loaded = comfy.lora.load_lora(comfy.lora_convert.convert_lora(row["weights"]),
                                      key_map)
        patched = patched.clone()
        placed = patched.add_patches(loaded, row["strength"])
        if not placed:
            raise ValueError(
                f"{row['name']} patched nothing: none of its keys belong to "
                f"the transformer this piece renders with. It is a LoRA for "
                f"other weights — take it out of the stack, or switch the "
                f"piece back to the family it was trained against.")
        LOG.info("Continuity LoRA: %s at %.2f — %d keys patched",
                 row["name"], row["strength"], len(set(placed)))
    return patched
