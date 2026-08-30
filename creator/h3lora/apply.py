"""Stack orchestration: normalise, port, partition, apply."""

from __future__ import annotations

import logging
from collections import OrderedDict

import comfy.lora
import comfy.patcher_extension
import comfy.utils
from comfy.quant_ops import QuantizedTensor
from comfy.weight_adapter import LoRAAdapter

from . import adaln as adaln_mod
from . import branch as branch_mod
from . import gain
from . import keymap
from . import modality as modality_mod
from . import pdd as pdd_mod
from . import schedule as schedule_mod

LOG = logging.getLogger("h3.powerlorastack")

# Layers whose forward is bypassed by a fused kernel, per weight layout.  A
# runtime branch on these would be silently dropped, so they must merge.
_FORWARD_BYPASSED = {"TensorWiseINT8Layout": ("mlp.fc2",)}


class StackReport:
    """Human-readable account of what happened, surfaced on the node."""

    def __init__(self):
        self.lines: list[str] = []
        self.merged = 0
        self.branched = 0
        self.skipped = 0
        self.bank_bytes = 0

    def add(self, line: str):
        self.lines.append(line)

    def text(self) -> str:
        return "\n".join(self.lines)


def _module_weight(model_patcher, module_path: str):
    try:
        module = model_patcher.get_model_object(module_path)
    except Exception:
        return None
    return getattr(module, "weight", None)


def _is_plain_lora(adapter) -> bool:
    """True for a bare rank-decomposition with no locon/dora/reshape extras."""
    return (
        isinstance(adapter, LoRAAdapter)
        and adapter.weights[3] is None      # locon mid
        and adapter.weights[4] is None      # dora scale
        and adapter.weights[5] is None      # reshape / pad
        and adapter.weights[0].ndim == 2
    )


def _branchable(weight, module_path: str, mode: str) -> bool:
    if weight is None or mode == "merge":
        return False
    if mode == "auto" and not isinstance(weight, QuantizedTensor):
        return False        # unquantized merges are exact and free at runtime
    layout = getattr(weight, "_layout_cls", None)
    for suffix in _FORWARD_BYPASSED.get(layout, ()):
        if module_path.endswith(suffix):
            return False
    return True


def detect_quantization(model_patcher) -> str:
    """Report the DiT's dominant weight format for the node's status line."""
    layouts: dict[str, int] = {}
    plain = 0
    try:
        diffusion_model = model_patcher.get_model_object("diffusion_model")
    except Exception:
        return "unknown"
    for module in diffusion_model.modules():
        weight = getattr(module, "weight", None)
        if weight is None:
            continue
        if isinstance(weight, QuantizedTensor):
            layout = getattr(weight, "_layout_cls", "quantized")
            layouts[layout] = layouts.get(layout, 0) + 1
        else:
            plain += 1
    if not layouts:
        return "unquantized"
    parts = [f"{k.replace('TensorCore', '').replace('TensorWise', '').replace('Layout', '')}"
             f" x{v}" for k, v in sorted(layouts.items(), key=lambda kv: -kv[1])]
    if plain:
        parts.append(f"plain x{plain}")
    return ", ".join(parts)


def apply_stack(model, entries, mode="auto", adaln_mode="auto", grid_path="",
                report: StackReport | None = None, modality=None, schedule=None):
    """Apply a list of ``{'path', 'name', 'strength'}`` LoRAs to an H3 model.

    ``mode`` is ``auto`` (branch quantized layers, merge the rest), ``merge``
    (stock behaviour) or ``branch`` (never touch a weight).

    ``modality`` optionally scales each LoRA's adaLN modulation per modality;
    see :mod:`h3lora.modality`. MMC: an entry may carry its own ``modality`` and
    is scaled by that instead.
    """
    report = report or StackReport()
    patcher = model.clone()

    model_sd = patcher.model.state_dict()
    index = keymap.build_module_index(model_sd.keys())
    key_map = {k[: -len(".weight")]: k for k in model_sd
               if k.startswith("diffusion_model.") and k.endswith(".weight")}

    try:
        diffusion_model = patcher.get_model_object("diffusion_model")
    except Exception as exc:
        raise ValueError("H3 Power LoRA Stack requires a MiniMax H3 model") from exc
    target_dim, table = adaln_mod.read_target(diffusion_model)
    if adaln_mode == "off":
        adaln_ctx = None
    else:
        if not grid_path:
            grid_path = adaln_mod.find_silu_grid()
        adaln_ctx = adaln_mod.AdalnContext(target_dim, table, grid_path)

    mod_values = modality_mod.normalize_scales(modality)
    # MMC: an entry may carry its own `modality`, which overrides the stack's.
    # Whether an adapter should reach the soundtrack is a property of how that
    # file was trained — H3 denoises audio and video through one tower, so a
    # character LoRA trained on clips with junk audio drags the sound of every
    # render it is in — and that is per file, not per stack. Upstream's
    # stack-level argument stays the default for a row that names none.
    row_modality = [modality_mod.normalize_scales(e.get("modality")) or mod_values
                    for e in entries]
    wanted = [v for v in [mod_values, *row_modality] if not modality_mod.is_identity(v)]
    mod_geom = modality_mod.geometry(diffusion_model) if wanted else None

    report.add(f"base: {detect_quantization(patcher)}")
    report.add(f"adaLN: {'curve' if table is not None else 'dense'} (input dim {target_dim})")
    if wanted and mod_geom is None:
        report.add("  ! adaLN modality control requested but this model's adaLN "
                   "does not split into the expected modalities - ignored")
        # the header carries the reason; keep the per-LoRA notes from blaming it
        # on the LoRAs, which are not at fault here
        mod_values = None
        row_modality = [None] * len(row_modality)

    per_module: "OrderedDict[str, list]" = OrderedDict()
    compute_dtype = model.model_dtype()
    # One stack holds at most one parallel decoder: the heads are a replacement,
    # not a contribution, so a second file's would overwrite the first's rather
    # than compose with it.
    pdd_banks = None
    pdd_name = ""

    for fallback_row, entry in enumerate(entries, start=1):
        row_index = int(entry.get("row", fallback_row))
        name = entry.get("name") or entry["path"]
        strength = float(entry.get("strength", 1.0))
        row_schedule = schedule_mod.resolve(schedule, row_index)
        # MMC: a caller that already holds the file hands it over rather than
        # naming it. `lora.py` keeps a small cache of these — they are ~700 MB
        # each and a piece of six segments applies the same stack six times — so
        # reading from `path` here would be six reads of a file already in RAM.
        lora_sd = entry.get("weights")
        if lora_sd is None:
            lora_sd = comfy.utils.load_torch_file(entry["path"], safe_load=True)

        # A PDD acceleration file is a trunk LoRA and a bank of per-interval
        # output heads; `pdd.take_heads` lifts the bank out so what follows is
        # an ordinary LoRA, and the bank is attached after the stack is built.
        # Copied first because the caller's dict is the one it caches — the next
        # queue of the same graph would otherwise get a file with no bank in it.
        lora_sd = dict(lora_sd)
        banks = pdd_mod.take_heads(lora_sd)
        if banks is not None:
            if pdd_mod.is_diffusers(lora_sd):
                lora_sd = pdd_mod.convert_trunk(lora_sd)
            if pdd_banks is None:
                pdd_banks, pdd_name = banks, name
            else:
                report.add(f"  ! {name}'s parallel decoder is ignored: "
                           f"{pdd_name} already holds the output heads")
                banks = None

        normalized, unmatched = keymap.normalize(lora_sd, index)
        # MMC: cached on the file — see `gain.measure_state_dict`.
        measured = gain.measure_state_dict(normalized, name, path=entry.get("path", ""))

        # before porting: the port derives its bias delta as ``B @ const``, so
        # scaling B's rows here carries through to the emitted .diff_b
        # MMC: this row's scales, which are the stack's unless it named its own.
        entry_modality = row_modality[fallback_row - 1]
        normalized, mod_stats = modality_mod.apply_to_state_dict(
            normalized, entry_modality, mod_geom)
        mod_note = modality_mod.describe(entry_modality, mod_stats)
        adaln_note = ""
        if adaln_ctx is not None and target_dim:
            source_table = normalized.pop("adaln_t_table", None)
            normalized, stats = adaln_mod.port_adaln_pairs(
                normalized, adaln_ctx, source_table=source_table)
            if stats["ported"]:
                adaln_note = f", adaLN ported x{stats['ported']}"
            if stats["rebased"]:
                adaln_note += f", adaLN rebased x{stats['rebased']}"
            if stats["skipped"]:
                adaln_note += f", adaLN dropped x{stats['skipped']}"
            if stats["residual"] is not None:
                adaln_note += f" (basis fit {stats['residual']:.1e})"

        loaded = comfy.lora.load_lora(normalized, key_map)

        merge: dict = dict(loaded)
        branched_here = 0
        for weight_key, adapter in loaded.items():
            if not weight_key.endswith(".weight"):
                continue
            module_path = weight_key[: -len(".weight")] if weight_key.endswith(".weight") else None
            if module_path is None or not _is_plain_lora(adapter):
                continue
            weight = _module_weight(patcher, module_path)
            effective_mode = "branch" if row_schedule is not None else mode
            if not _branchable(weight, module_path, effective_mode):
                continue
            up, down = adapter.weights[0], adapter.weights[1]
            if up.shape[0] != weight.shape[0] or down.shape[1] != weight.shape[1]:
                LOG.warning("H3 PowerLoraStack: shape mismatch on %s, skipped", weight_key)
                report.skipped += 1
                merge.pop(weight_key, None)
                continue
            alpha = adapter.weights[2]
            alpha_scale = float(alpha) / down.shape[0] if alpha is not None else 1.0
            bias = None
            if row_schedule is not None:
                bias_key = f"{module_path}.bias"
                bias_patch = loaded.get(bias_key)
                if (isinstance(bias_patch, tuple) and len(bias_patch) > 1
                        and bias_patch[0] == "diff" and bias_patch[1]):
                    candidate = bias_patch[1][0]
                    if getattr(candidate, "ndim", None) == 1 and candidate.shape[0] == weight.shape[0]:
                        bias = candidate
                        merge.pop(bias_key, None)
                per_module.setdefault(module_path, []).append(
                    (up, down, alpha_scale, row_schedule, bias))
            else:
                # Preserve the original strength-folded contribution exactly.
                per_module.setdefault(module_path, []).append(
                    (up, down, strength * alpha_scale))
            merge.pop(weight_key, None)
            branched_here += 1

        if merge:
            patcher.add_patches(merge, strength)
        report.merged += len(merge)
        report.branched += branched_here

        detail = f"{len(merge)} merged, {branched_here} branched"
        if unmatched:
            detail += f", {len(unmatched)} unmatched"
        report.add(f"{name} @ {strength:g}: {detail}{adaln_note}{mod_note}")
        if row_schedule is not None:
            arrow = "\u2192"
            report.add(
                f"  sched: {row_schedule.start_strength:.2f} {arrow} "
                f"{row_schedule.end_strength:.2f} {row_schedule.curve} "
                f"({row_schedule.domain} {row_schedule.start_percent:g}\u2013"
                f"{row_schedule.end_percent:g}%)"
            )
            if merge:
                report.add(
                    f"  ! {len(merge)} patches on {name} cannot be scheduled "
                    f"(merged at {strength:.2f})"
                )
        if banks is not None:
            report.add(f"  parallel decoder: {pdd_mod.num_steps(banks)} intervals, "
                       f"{pdd_mod.bank_bytes(banks) / (1024 ** 2):.0f} MB")
            if abs(strength - 1.0) > 1e-6:
                report.add(f"  ! the output heads are a replacement and ignore "
                           f"strength {strength:g}; only the trunk is scaled")
        if measured.get("rel"):
            # what this LoRA actually does to the weights, so a strength that is
            # far off the calibrated unit is visible without the UI button
            note = f"  rel dW {measured['rel'] * 100:.3f}%"
            suggested = measured["factor"]
            if abs(strength - suggested) > 0.1 * max(suggested, 1e-6):
                note += f" (auto-balance would use {suggested:.2f})"
            report.add(note)
        if not merge and not branched_here:
            report.add(f"  ! {name} matched no layers on this model")

    if per_module:
        report.bank_bytes = branch_mod.bank_bytes(per_module, compute_dtype)
        # a chain of stack nodes must not overwrite each other's bank
        n = 0
        while patcher.get_additional_models_with_key(f"h3_power_lora_bank_{n}"):
            n += 1
        tag = f"h3_power_lora_bank_{n}"
        _count, controller = branch_mod.attach(patcher, per_module, compute_dtype, tag)
        if controller is not None:
            patcher.add_wrapper_with_key(
                comfy.patcher_extension.WrappersMP.APPLY_MODEL,
                f"h3_lora_schedule_{n}",
                controller,
            )
        report.add(f"branch bank: {len(per_module)} layers, "
                   f"{report.bank_bytes / (1024 ** 2):.0f} MB")

    if pdd_banks is not None:
        n = 0
        while patcher.get_additional_models_with_key(f"h3_pdd_heads_{n}"):
            n += 1
        controller = pdd_mod.attach(patcher, pdd_banks, f"h3_pdd_heads_{n}", pdd_name)
        patcher.add_wrapper_with_key(
            comfy.patcher_extension.WrappersMP.APPLY_MODEL,
            f"h3_pdd_plan_{n}",
            controller,
        )

    return patcher, report
