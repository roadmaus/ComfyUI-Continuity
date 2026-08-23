"""Exact, fused runtime low-rank branches for quantized MiniMax H3 weights.

Unscheduled branches fold strength into ``up`` exactly as before. Scheduled
branches retain one contiguous rank slice per LoRA and multiply the small
rank-width intermediate at model-call time.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

import comfy.model_management

from .schedule import Schedule, ScheduleState, progress_from


@dataclass
class FusedBranch:
    up: torch.Tensor
    down: torch.Tensor
    # rank start, rank end, schedule (None means constant), constant/alpha scale
    slices: list[tuple[int, int, Schedule | None, float]]
    biases: list[tuple[torch.Tensor, Schedule]]


class LoraBank(nn.Module):
    """Holds every runtime branch's factors as one movable, accountable module."""

    def __init__(self, pairs):
        super().__init__()
        self.index: dict[str, int] = {}
        self.scheduled: dict[str, FusedBranch] = {}
        for i, (name, fused) in enumerate(pairs.items()):
            if isinstance(fused, FusedBranch):
                up, down = fused.up, fused.down
                self.scheduled[name] = fused
            else:
                up, down = fused
            self.register_parameter(f"up{i}", nn.Parameter(up, requires_grad=False))
            self.register_parameter(f"down{i}", nn.Parameter(down, requires_grad=False))
            if isinstance(fused, FusedBranch):
                initial = torch.cat([
                    torch.full(
                        (end - start,),
                        schedule.evaluate(0.0) * scale if schedule is not None else scale,
                        dtype=up.dtype,
                    )
                    for start, end, schedule, scale in fused.slices
                ])
                self.register_buffer(f"scale{i}", initial, persistent=False)
                if fused.biases:
                    bias = torch.stack([item[0].to(up.dtype) for item in fused.biases])
                    self.register_buffer(f"bias{i}", bias, persistent=False)
            self.index[name] = i

    def get(self, name: str):
        i = self.index[name]
        return getattr(self, f"up{i}"), getattr(self, f"down{i}")

    def get_bias(self, name: str):
        return getattr(self, f"bias{self.index[name]}", None)


class LoraBranch:
    """Object patch for ``Linear.forward`` with a live optional rank scale."""

    def __init__(self, bank_patcher, state: ScheduleState, name: str, original):
        self.bank_patcher = bank_patcher
        self.bank: LoraBank = bank_patcher.model
        self.state = state
        self.name = name
        self.original = original

    def __call__(self, input: torch.Tensor, *args, **kwargs):
        # ``out`` is the widest tensor the branch ever sees -- for the SwiGLU MLP it is
        # the fc1 activation -- so everything below accumulates into it rather than
        # materialising a same-shaped delta. A second live copy is an OOM on long
        # sequences; a third one certainly is. ``out`` is freshly produced by the
        # wrapped forward, so it is ours to write into.
        out = self.original(input, *args, **kwargs)
        up, down = self.bank.get(self.name)
        h = F.linear(input, comfy.model_management.cast_to_device(down, input.device, input.dtype))
        scales = self.state.scales_for(self.name)
        if scales is not None:
            h *= comfy.model_management.cast_to_device(scales, input.device, input.dtype)
        up = comfy.model_management.cast_to_device(up, input.device, input.dtype)
        bias = self.bank.get_bias(self.name)
        bias_scales = self.state.bias_scales_for(self.name)
        if bias is not None and bias_scales is not None:
            bias = comfy.model_management.cast_to_device(bias, input.device, input.dtype)
            bias_scales = comfy.model_management.cast_to_device(
                bias_scales, input.device, input.dtype)
            out += torch.matmul(bias_scales, bias).to(out.dtype)
        if out.dtype == up.dtype and out.is_contiguous():
            out.view(-1, out.shape[-1]).addmm_(h.reshape(-1, h.shape[-1]), up.t())
        else:
            out += F.linear(h, up).to(out.dtype)
        return out


def fuse(contributions, compute_dtype):
    """Fuse contributions, retaining rank boundaries only when scheduled."""
    if all(len(item) == 3 for item in contributions):
        # This is the original path, intentionally unchanged for bit identity.
        ups, downs = [], []
        for up, down, scale in contributions:
            ups.append((up.to(torch.float32) * float(scale)).to(compute_dtype))
            downs.append(down.to(compute_dtype))
        if len(ups) == 1:
            return ups[0], downs[0]
        return torch.cat(ups, dim=1).contiguous(), torch.cat(downs, dim=0).contiguous()

    ups, downs, slices, biases = [], [], [], []
    rank_start = 0
    for item in contributions:
        if len(item) == 3:
            up, down, scale = item
            schedule = None
            bias = None
        else:
            up, down, scale, schedule, bias = item
        rank_end = rank_start + down.shape[0]
        ups.append(up.to(compute_dtype))
        downs.append(down.to(compute_dtype))
        slices.append((rank_start, rank_end, schedule, float(scale)))
        if bias is not None:
            biases.append((bias, schedule))
        rank_start = rank_end
    up = ups[0] if len(ups) == 1 else torch.cat(ups, dim=1).contiguous()
    down = downs[0] if len(downs) == 1 else torch.cat(downs, dim=0).contiguous()
    return FusedBranch(up, down, slices, biases)


class ScheduleController:
    """Stackable APPLY_MODEL wrapper publishing scales for one bank."""

    def __init__(self, state: ScheduleState, scheduled: dict[str, FusedBranch], dtype):
        self.state = state
        self.scheduled = scheduled
        self.dtype = dtype

    def __call__(self, executor, x, t, c_concat=None, c_crossattn=None, control=None,
                 transformer_options=None, **kwargs):
        transformer_options = transformer_options or {}
        scales, bias_scales = {}, {}
        progress_cache = {}
        device = torch.as_tensor(t).device

        def strength(schedule):
            progress = progress_cache.setdefault(
                schedule.domain, progress_from(t, transformer_options, schedule.domain))
            return schedule.evaluate(progress)

        for name, fused in self.scheduled.items():
            scales[name] = torch.cat([
                torch.full(
                    (end - start,),
                    strength(schedule) * factor if schedule is not None else factor,
                    dtype=self.dtype,
                    device=device,
                )
                for start, end, schedule, factor in fused.slices
            ])
            if fused.biases:
                bias_scales[name] = torch.tensor(
                    [strength(schedule) for _bias, schedule in fused.biases],
                    dtype=self.dtype,
                    device=device,
                )
        self.state.set(scales, bias_scales)
        try:
            return executor(x, t, c_concat, c_crossattn, control, transformer_options, **kwargs)
        finally:
            self.state.clear()


def attach(model_patcher, per_module, compute_dtype, tag: str):
    """Build the bank, register it for VRAM accounting, and patch forwards."""
    if not per_module:
        return 0, None

    import comfy.model_patcher

    pairs = OrderedDict(
        (module_path, fuse(contributions, compute_dtype))
        for module_path, contributions in per_module.items()
    )
    bank = LoraBank(pairs)
    state = ScheduleState()
    bank_patcher = comfy.model_patcher.ModelPatcher(
        bank,
        load_device=comfy.model_management.get_torch_device(),
        offload_device=comfy.model_management.unet_offload_device(),
    )
    model_patcher.set_additional_models(tag, [bank_patcher])

    for module_path in pairs:
        forward_key = f"{module_path}.forward"
        original = model_patcher.get_model_object(forward_key)
        model_patcher.add_object_patch(
            forward_key, LoraBranch(bank_patcher, state, module_path, original))
    controller = ScheduleController(state, bank.scheduled, compute_dtype) if bank.scheduled else None
    return len(pairs), controller


def bank_bytes(per_module, compute_dtype) -> int:
    """Approximate VRAM the bank will occupy, for reporting."""
    itemsize = torch.empty((), dtype=compute_dtype).element_size()
    total = 0
    for contributions in per_module.values():
        for item in contributions:
            up, down = item[:2]
            total += (up.numel() + down.numel()) * itemsize
            if len(item) > 3 and item[4] is not None:
                total += item[4].numel() * itemsize
    return total
