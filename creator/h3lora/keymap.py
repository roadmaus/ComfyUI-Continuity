"""Key normalisation for MiniMax H3 LoRAs.

Every H3 LoRA in the wild is one of a handful of naming conventions.  Observed
across the local collection:

* ai-toolkit / diffusers  ``diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight``
* same, no prefix         ``blocks.0.attn.qkv_proj.lora_A.weight``
* kohya / musubi          ``lora_unet_blocks_0_attn_qkv_proj.lora_down.weight`` + ``.alpha``
* lycoris                 ``lycoris_blocks_0_attn_qkv_proj.*``
* peft                    ``base_model.model.blocks.0...`` / ``transformer.blocks.0...``

``comfy.lora.model_lora_keys_unet`` already covers the ``diffusion_model.``-
prefixed and ``lora_unet_`` forms, but not the bare form, and it gives us no
handle for rewriting adaLN tensors before they are matched.  So we normalise
everything ourselves onto the canonical ``diffusion_model.<path>`` module key,
resolving underscore forms through the model's own state dict rather than
guessing where the word boundaries are.
"""

from __future__ import annotations

import re

# suffixes comfy.lora.load_lora understands, longest first so that
# ``.lora_down.weight`` is not truncated to ``.weight``
_LORA_SUFFIXES = (
    ".lora_down.weight", ".lora_up.weight",
    ".lora_A.weight", ".lora_B.weight",
    ".lora_A.default.weight", ".lora_B.default.weight",
    ".lora_A", ".lora_B",
    ".lora_mid.weight", ".dora_scale",
    ".diff_b", ".diff", ".set_weight", ".alpha",
    ".hada_w1_a", ".hada_w1_b", ".hada_w2_a", ".hada_w2_b", ".hada_t1", ".hada_t2",
    ".lokr_w1", ".lokr_w2", ".lokr_w1_a", ".lokr_w1_b", ".lokr_w2_a", ".lokr_w2_b",
    ".lokr_t2", ".oft_blocks", ".boft_blocks", ".rescale", ".w_norm", ".b_norm",
)

_STRIP_PREFIXES = (
    "diffusion_model.", "transformer.", "base_model.model.", "pipe.dit.",
    "model.diffusion_model.", "unet.",
)

_UNDERSCORE_PREFIXES = ("lora_unet_", "lycoris_", "lora_transformer_")


def split_suffix(key: str):
    """``blocks.0.mlp.fc1.lora_A.weight`` -> ``('blocks.0.mlp.fc1', '.lora_A.weight')``."""
    for suffix in sorted(_LORA_SUFFIXES, key=len, reverse=True):
        if key.endswith(suffix):
            return key[: -len(suffix)], suffix
    return None, None


def build_module_index(model_sd_keys) -> dict:
    """Map every spelling of a DiT module path to its canonical form.

    Canonical form is the state-dict key minus ``.weight``, e.g.
    ``diffusion_model.blocks.0.attn.qkv_proj``.  Both the dotted path and the
    underscored path (which is what kohya trainers emit) resolve to it, and the
    underscore mapping is derived from the real keys so no heuristic is needed
    to decide whether ``qkv_proj`` is one token or two.
    """
    index: dict[str, str] = {}
    for k in model_sd_keys:
        if not k.startswith("diffusion_model.") or not k.endswith(".weight"):
            continue
        canonical = k[: -len(".weight")]
        bare = canonical[len("diffusion_model."):]
        index[canonical] = canonical
        index[bare] = canonical
        index[bare.replace(".", "_")] = canonical
    return index


def _strip_prefixes(path: str) -> str:
    changed = True
    while changed:
        changed = False
        for pre in _STRIP_PREFIXES:
            if path.startswith(pre):
                path = path[len(pre):]
                changed = True
                break
    for pre in _UNDERSCORE_PREFIXES:
        if path.startswith(pre):
            path = path[len(pre):]
            break
    return path


def canonical_module(key_body: str, index: dict):
    """Resolve one LoRA key body to a canonical module path, or None."""
    body = _strip_prefixes(key_body)
    hit = index.get(body)
    if hit is not None:
        return hit
    # kohya writes ``lora_unet__blocks_0_...`` (double underscore) and some
    # trainers keep a dotted tail after the underscored head
    squashed = body.replace(".", "_")
    hit = index.get(squashed) or index.get(re.sub(r"_{2,}", "_", squashed))
    if hit is not None:
        return hit
    return None


def normalize(lora_sd: dict, index: dict):
    """Rewrite a LoRA state dict onto canonical module keys.

    Returns ``(normalized_sd, unmatched_keys)``.  Non-LoRA passenger tensors
    (``adaln_t_table`` and full ``adaln_proj.linear.weight`` replacements found
    in "complete pruned" LoRA files) are passed through untouched so the caller
    can deal with them.
    """
    out: dict = {}
    unmatched: list[str] = []
    for key, value in lora_sd.items():
        body, suffix = split_suffix(key)
        if body is None:
            out[key] = value          # passenger tensor, handled upstream
            continue
        module = canonical_module(body, index)
        if module is None:
            unmatched.append(key)
            continue
        out[module + suffix] = value
    return out, unmatched
