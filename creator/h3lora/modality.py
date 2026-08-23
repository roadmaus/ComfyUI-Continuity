"""Per-modality scaling of adaLN LoRA rows.

MiniMax H3 is not built like LTX 2.3.  LTX duplicates the tower per modality
(``audio_attn``, ``audio_ff``, ``audio_patchify_proj``, ``audio_to_video_attn``),
so a LoRA can be steered by picking layers.  H3 packs audio and video into one
token sequence and pushes both through the same 50 blocks, and the only
modality-specific weights in the whole checkpoint are four tensors --
``video_patch_proj``, ``audio_patch_proj``, ``final_layer.video_out``,
``final_layer.audio_out`` -- none of which any observed LoRA touches.

One place does separate cleanly: **adaLN**.  ``AdalnProj.forward`` computes
``linear(t) -> [M, expand*hidden*modalities]`` and then
``view(M*modalities, expand*hidden)``, so output feature ``j`` belongs to
modality ``j // (expand*hidden)``.  The 96768 rows are three contiguous blocks
of 32256, and ``comfy/ldm/minimax/model.py`` tags segments
``{video: 0, text: 1, audio: 2}`` (``seg_tag``, and ``row_base + tag`` when the
modulation rows are built).

Scaling a slice of ``lora_B``'s rows therefore scales that modality's modulation
exactly, with no runtime hook.  It is a property of the trained weights rather
than of ComfyUI: any LoRA that loads onto ``adaln_proj.linear`` at all must have
its rows in this order, so this holds for future adapters by construction --
independent of rank, alpha, trainer convention, and of whether the adaLN basis
is dense (2688) or curve (8), which only affects the ``A`` side.

Two things this deliberately does not do:

* The geometry is read off the model's own ``AdalnProj`` rather than hardcoded,
  and every layer is shape-checked before it is touched.  A future H3 variant
  with different geometry silently keeps today's behaviour instead of slicing
  at the wrong offsets.
* ``final_layer.adaln_proj`` is ``AdalnProj(t_dim, hidden, 2, 1)`` -- one
  modality, differentiated only by timestep -- so it has 10752 rows, fails the
  shape check, and is left alone.

It is also worth being clear about the ceiling: attention is joint over the
packed sequence, so damping the video modality changes where the LoRA is applied,
not everything it eventually reaches.
"""

from __future__ import annotations

import logging

import torch

LOG = logging.getLogger("h3.powerlorastack")

# Index is the modality tag from comfy/ldm/minimax/model.py ``seg_tag``.
TAGS = ("video", "text", "audio")

# lora_B spellings; ``.diff`` is a full-weight replacement, which slices the same
# way.  ``.set_weight`` is an absolute value, not a delta, so it is never scaled.
_ROW_KEYS = (".lora_B.weight", ".lora_up.weight", ".diff")

_ADALN_SUFFIX = "adaln_proj.linear"


def geometry(diffusion_model):
    """``(expand, modalities, hidden)`` read off the model's own AdalnProj.

    Returns ``None`` when the model does not look like an H3 whose adaLN splits
    into the three tags this module knows how to name.
    """
    blocks = getattr(diffusion_model, "blocks", None)
    if not blocks or len(blocks) == 0:
        return None
    proj = getattr(blocks[0], "adaln_proj", None)
    if proj is None:
        return None
    try:
        expand = int(proj.expand)
        modalities = int(proj.modalities)
        hidden = int(proj.hidden)
    except (AttributeError, TypeError, ValueError):
        return None
    if modalities != len(TAGS) or expand <= 0 or hidden <= 0:
        LOG.warning("H3 PowerLoraStack: adaLN has %d modalities, expected %d - "
                    "modality control disabled", modalities, len(TAGS))
        return None
    return expand, modalities, hidden


def normalize_scales(scales) -> tuple:
    """``{'video':..,'text':..,'audio':..}`` -> a tuple in tag order."""
    if scales is None:
        return None
    if isinstance(scales, dict):
        values = tuple(float(scales.get(tag, 1.0)) for tag in TAGS)
    else:
        values = tuple(float(v) for v in scales)
    if len(values) != len(TAGS):
        return None
    return values


def is_identity(values) -> bool:
    return values is None or all(v == 1.0 for v in values)


def _scale_rows(tensor, values, block):
    out = tensor.to(torch.float32).clone()
    for i, scale in enumerate(values):
        if scale != 1.0:
            out[i * block:(i + 1) * block] *= scale
    return out.to(tensor.dtype)


def apply_to_state_dict(sd: dict, values, geom):
    """Scale every block-level adaLN ``lora_B`` in ``sd`` by modality.

    Must run **before** :func:`h3lora.adaln.port_adaln_pairs`: the port derives
    its bias delta as ``B @ const``, so scaling B's rows first carries through to
    the emitted ``.diff_b`` with no extra work.

    Returns ``(new_sd, stats)``; ``sd`` is not mutated.
    """
    stats = {"scaled": 0, "mismatched": 0, "present": 0}
    if is_identity(values) or geom is None:
        return sd, stats
    expand, modalities, hidden = geom
    rows = expand * modalities * hidden
    block = expand * hidden

    out = dict(sd)
    for key, tensor in sd.items():
        suffix = next((s for s in _ROW_KEYS if key.endswith(s)), None)
        if suffix is None:
            continue
        module = key[: -len(suffix)]
        if not module.endswith(_ADALN_SUFFIX):
            continue
        stats["present"] += 1
        shape = getattr(tensor, "shape", None)
        if shape is None or len(shape) != 2 or shape[0] != rows:
            # final_layer.adaln_proj (one modality) and any future geometry land
            # here and are left exactly as they were
            stats["mismatched"] += 1
            continue
        out[key] = _scale_rows(tensor, values, block)
        stats["scaled"] += 1
    return out, stats


def describe(values, stats) -> str:
    """One-line account for the node's report, including when nothing happened."""
    if is_identity(values):
        return ""
    setting = "/".join(f"{v:g}" for v in values)
    if stats["scaled"]:
        note = f", adaLN modality {'/'.join(TAGS)} = {setting} x{stats['scaled']}"
        if stats["mismatched"]:
            note += f" ({stats['mismatched']} unsplittable)"
        return note
    if stats["present"]:
        return f", adaLN modality {setting} INACTIVE (no layer matched the split)"
    return f", adaLN modality {setting} INACTIVE (LoRA has no adaLN pairs)"
