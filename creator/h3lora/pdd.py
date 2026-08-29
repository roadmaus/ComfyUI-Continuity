"""Parallel Decoding Distillation: an H3 acceleration LoRA that is not only a LoRA.

alibaba-pai's `MiniMax-H3-Acc-LoRAs` are two files that each hold a rank-64
trunk adapter *and* a bank of 32 copies of the model's two output heads. The
trunk is an ordinary LoRA and `apply.py` places it like any other. The bank is
the part no LoRA loader can do anything with, and it is where the eight steps
come from.

**What the bank is.** PDD (Shaul et al., arXiv 2607.26004) distils the model
against a fixed grid of 32 flow intervals and gives every interval its own final
projection. Sampling then takes one Euler step per *block* of four intervals,
and the head that step runs on is the block's four heads averaged by their
interval widths — the block's mean velocity, in one forward instead of four. So
the head is a function of where on the schedule the sampler is, which is a thing
a state dict cannot say and `comfy.lora.load_lora` would drop on the floor.
Hence this module: the bank rides as an object patch on the two heads and a plan
is armed on every step by an APPLY_MODEL wrapper, which is the same shape as the
scheduled LoRA branch in `branch.py` and shares its idiom on purpose.

**The schedule is not a suggestion.** The intervals sit at fixed places on the
flow grid — `shift * b / (1 + (shift - 1) * b)` over a base grid uniform in
`[0, 1]` — which is exactly what core's `simple` scheduler hands a flow model, so
a 4-, 8- or 16-step `simple` render already lands on them and no sigmas have to
be plumbed anywhere. `beta`, `karras` and the rest do not.

Which block a step covers is therefore read off the step's own two sigmas rather
than counted: invert them through the shift they were made with and the base
grid says which intervals this Euler step spans. That is what makes this hold
everywhere the pack samples — a refine pass starts halfway down the schedule, a
turbo lead-in hands its second sitting the tail of one, a CFG render calls the
model twice on one sigma — instead of only on a render that starts at step zero.
A step that lands between intervals arms nothing and gets the checkpoint's own
heads, and `verify` says so in the log the first time it sees such a schedule.

**Two clocks.** H3 runs the audio stream on its own flow shift, and PDD follows:
the video head's plan is built off the video grid and the audio head's off the
audio one, which is why the two heads carry separate banks and separate plans
rather than one plan for the pack. Both shifts are read off `model_sampling` at
sampling time, so a user who moves the shift pills moves the grid with them.

**The trunk needs converting, from one form only.** The released files are in
diffusers' module names — `to_q/to_k/to_v` where H3 has one fused `qkv_proj`,
`ff.net.0.proj` where it has a SwiGLU `mlp.fc1` whose halves are the other way
round. `convert_trunk` is that rewrite and nothing more; a file already in
ComfyUI's names (the community repackagings) passes through `keymap` untouched
and only its bank is taken here.
"""

from __future__ import annotations

import logging
import threading

import torch
import torch.nn as nn
import torch.nn.functional as F

import comfy.model_management

LOG = logging.getLogger("continuity")

# The bank's own key names, which both the released files and the community
# repackagings of them use — they are diffusers' names for the two heads and
# nobody has had a reason to rename them.
VIDEO_BANK = "proj_out"
AUDIO_BANK = "audio_proj_out"

# Where those two heads are on this side. H3's final layer holds both, and the
# module paths carry the `diffusion_model.` prefix because that is what
# `ModelPatcher.get_model_object` and the rest of `apply.py` speak.
HEAD_MODULE = {
    VIDEO_BANK: "diffusion_model.final_layer.video_out",
    AUDIO_BANK: "diffusion_model.final_layer.audio_out",
}

# How far off a whole interval a step may land before it counts as off the grid.
# In grid units, so it is the same number at every step count and under either
# clock. Wide enough for the one honest source of error — core's `simple`
# scheduler walks a 1000-entry table, so a step count that does not divide 1000
# lands slightly off the value it means (16 steps is 0.05 of an interval out; 4,
# 8 and 20 are exact) — and far under half an interval, which is where rounding
# would start picking the neighbour.
GRID_TOLERANCE = 0.2


# ---- reading the file -------------------------------------------------------


def take_heads(state_dict: dict):
    """Pop the head bank out of a LoRA state dict. -> ``{name: (weight, bias)}``.

    Returns ``None`` for an ordinary LoRA, which is every other file this pack
    has ever been handed, so the cost of asking is one dictionary lookup.

    The bank is popped rather than copied because what is left has to be a
    plain LoRA: `keymap.normalize` passes a key it does not recognise through
    as a passenger tensor and `comfy.lora.load_lora` then drops it with a line
    in the log, which is exactly the silent half-application this module exists
    to prevent.
    """
    weight = state_dict.get(f"{VIDEO_BANK}.weight")
    if weight is None or getattr(weight, "ndim", 0) != 3:
        return None
    banks = {}
    for name in (VIDEO_BANK, AUDIO_BANK):
        bank = state_dict.pop(f"{name}.weight", None)
        if bank is None:
            raise ValueError(
                f"this looks like a PDD acceleration LoRA but has no {name}.weight — "
                f"the file is incomplete")
        banks[name] = (bank, state_dict.pop(f"{name}.bias", None))
    if banks[VIDEO_BANK][0].shape[0] != banks[AUDIO_BANK][0].shape[0]:
        raise ValueError("the two PDD head banks disagree about how many intervals "
                         "the model was distilled against")
    return banks


def num_steps(banks) -> int:
    """The grid the file was distilled against — 32 in every release so far."""
    return int(banks[VIDEO_BANK][0].shape[0])


def is_diffusers(state_dict: dict) -> bool:
    """Whether the trunk is in diffusers' module names rather than ComfyUI's."""
    return any(".to_q." in key or ".refiner_blocks." in key for key in state_dict)


# ---- the trunk rewrite ------------------------------------------------------

# `to_q/to_k/to_v` are one fused `qkv_proj` here, split q, k, v in that order —
# so the three adapters concatenate into one, and the order is the split's.
_QKV = ("to_q", "to_k", "to_v")

# Everything that is a rename and nothing else. `to_out.0` is diffusers' way of
# writing the linear inside its output `ModuleList`.
_RENAME = {
    "attn.to_out.0": "attn.out_proj",
    "ff.net.0.proj": "mlp.fc1",
    "ff.net.2": "mlp.fc2",
    "adaln_proj.linear": "adaln_proj.linear",
}

_DOWN = (".lora_down", ".lora_A", ".lora_down.weight", ".lora_A.weight")
_UP = (".lora_up", ".lora_B", ".lora_up.weight", ".lora_B.weight")


def _split(key: str):
    """``blocks.0.attn.to_q.lora_down`` -> ``('blocks.0.attn.to_q', 'down')``."""
    if key.endswith(".alpha"):
        return key[: -len(".alpha")], "alpha"
    for suffix in sorted(_DOWN + _UP, key=len, reverse=True):
        if key.endswith(suffix):
            side = "down" if suffix in _DOWN else "up"
            return key[: -len(suffix)], side
    return None, None


def _module_pairs(state_dict: dict):
    """The file as ``{module: {'down': tensor, 'up': tensor}}``, in file order."""
    pairs: dict[str, dict] = {}
    for key, value in state_dict.items():
        module, side = _split(key)
        if module is None:
            raise ValueError(f"{key} is neither a LoRA pair nor part of the head bank")
        pairs.setdefault(module, {})[side] = value
    return pairs


def convert_trunk(state_dict: dict) -> dict:
    """diffusers module names -> ComfyUI H3 ones. -> a plain LoRA state dict.

    Three of the rewrites are more than a rename, and each is exact rather than
    approximate — the fused delta this builds is the concatenation of the three
    it was given, not a fit to it:

    * **q, k and v fuse.** ``A`` stacks along the rank axis and ``B`` goes block
      diagonal, so ``B @ A`` is ``[B_q A_q; B_k A_k; B_v A_v]`` — the three
      deltas, in the order the fused projection splits. The rank triples with
      them, so the alpha does too or core's ``alpha / rank`` would divide the
      strength by three.
    * **fc1's halves swap.** diffusers' SwiGLU is ``value * silu(gate)`` and
      core's is ``silu(gate) * value``, so the two halves of the projection's
      output sit the other way round and the ``B`` rows move with them.
    * **the token refiner's blocks are just ``blocks``.**

    Rank and alpha are the file's own: the released files carry no ``.alpha``,
    which core reads as alpha equal to rank — a scale of 1.0, which is what
    ``lora_alpha == lora_rank == 64`` in their metadata says.
    """
    pairs = _module_pairs(state_dict)
    out: dict = {}

    def emit(module: str, down, up, alpha=None):
        out[f"diffusion_model.{module}.lora_A.weight"] = down
        out[f"diffusion_model.{module}.lora_B.weight"] = up
        if alpha is not None:
            out[f"diffusion_model.{module}.alpha"] = alpha

    for module, sides in pairs.items():
        if "down" not in sides or "up" not in sides:
            raise ValueError(f"{module} has half a LoRA pair")

    seen_qkv = set()
    for module, sides in pairs.items():
        path = module.replace("token_refiner.refiner_blocks.", "token_refiner.blocks.")
        head, _, leaf = path.rpartition(".")
        attn, _, which = head.rpartition(".")

        if leaf in _QKV and which == "attn":
            if head in seen_qkv:
                continue
            seen_qkv.add(head)
            downs, ups = [], []
            for name in _QKV:
                branch = pairs.get(f"{module[: -len(leaf)]}{name}")
                if branch is None:
                    raise ValueError(f"{head} has {leaf} but no {name}")
                downs.append(branch["down"])
                ups.append(branch["up"])
            rank = downs[0].shape[0]
            if any(d.shape[0] != rank for d in downs):
                raise ValueError(f"{head}: q, k and v were trained at different ranks")
            alpha = sides.get("alpha")
            fused_up = torch.zeros(
                sum(u.shape[0] for u in ups), rank * len(ups), dtype=ups[0].dtype)
            row = col = 0
            for up in ups:
                fused_up[row: row + up.shape[0], col: col + rank] = up
                row += up.shape[0]
                col += rank
            # The rank tripled, so the alpha does: core's scale is alpha/rank and
            # each branch has to keep the one it was trained with. A file with no
            # alpha at all is read by core as alpha equal to rank, which is the
            # same 1.0 either way, so nothing is written for one.
            emit(f"{head}.qkv_proj", torch.cat(downs, dim=0), fused_up,
                 None if alpha is None else alpha * len(ups))
            continue

        for source, target in _RENAME.items():
            if path.endswith("." + source):
                renamed = path[: -len(source)] + target
                up = sides["up"]
                if target.endswith("mlp.fc1"):
                    half = up.shape[0] // 2
                    up = torch.cat((up[half:], up[:half]), dim=0)
                emit(renamed, sides["down"], up, sides.get("alpha"))
                break
        else:
            raise ValueError(f"{path} is not a layer this pack knows how to place")

    return out


# ---- the grid ---------------------------------------------------------------


def shifted(shift: float, base):
    """One flow shift applied to a base grid. Core's `time_snr_shift`, verbatim."""
    return shift * base / (1.0 + (shift - 1.0) * base)


def time_grid(shift: float, steps: int) -> torch.Tensor:
    """The ascending distillation grid `0 = t_0 < ... < t_N = 1` for one clock."""
    base = torch.linspace(1.0, 0.0, steps + 1, dtype=torch.float64)
    return 1.0 - shifted(float(shift), base)


def block_plan(grid: torch.Tensor, start: int, block: int) -> torch.Tensor:
    """One block's heads, weighted by interval width. -> a length-N vector.

    The weights are the block's intervals over their span, so the mixed head is
    the block's mean velocity — which is what an Euler step across the block's
    two boundaries consumes.
    """
    widths = grid.diff()
    plan = torch.zeros(widths.shape[0], dtype=widths.dtype)
    span = widths[start: start + block].sum()
    plan[start: start + block] = widths[start: start + block] / span
    return plan


def base_of(sigma: float, shift: float) -> float:
    """One shifted sigma back onto the base grid — the inversion core's
    `time_shift_sigma` does before re-applying the other shift.

    The base grid is the one thing the two clocks and every step count have in
    common: a sigma inverted through the shift it was made with says where on
    the distillation's 32 intervals this step is standing, whatever schedule
    produced it.
    """
    sigma = float(sigma)
    return sigma / (shift + sigma * (1.0 - shift))


def interval_of(sigma, next_sigma, shift: float, steps: int):
    """Which intervals one Euler step covers. -> ``(start, block)``, or None.

    Derived from the two sigmas the step runs between rather than from a step
    counter, which is what makes this hold everywhere the pack samples: a
    partial-denoise refine starts halfway down the schedule, a turbo lead-in
    hands its second sitting the tail of one, and a CFG render calls the model
    twice on the same sigma. All three are the same question — which slice of
    the trained grid is this — and the sigmas answer it.

    None where the step does not land on the grid at all. That is a schedule
    the file was not distilled for; the plan is left unarmed and the
    checkpoint's own heads answer, which is the honest output for it.
    """
    start = (1.0 - base_of(sigma, shift)) * steps
    end = (1.0 - base_of(next_sigma, shift)) * steps
    first, last = round(start), round(end)
    if max(abs(start - first), abs(end - last)) > GRID_TOLERANCE:
        return None
    if not 0 <= first < last <= steps:
        return None
    return first, last - first


def verify(sample_sigmas, shift: float, steps: int) -> str:
    """Empty if every step of this render lands on the grid, else why one does not.

    A schedule that misses is not refused — the numbers here are the released
    files' and trying another is a user's business — but a render that quietly
    falls back to the checkpoint's heads for the whole of itself, having loaded
    a file whose point is the other ones, is not something to leave unsaid.
    """
    samples = torch.as_tensor(sample_sigmas).detach().double().flatten().tolist()
    if len(samples) < 2:
        return "the sampler is taking no steps"
    for index in range(len(samples) - 1):
        if interval_of(samples[index], samples[index + 1], shift, steps) is None:
            return (f"step {index + 1} of {len(samples) - 1} does not land on the "
                    f"{steps}-interval grid this file was distilled against — it "
                    f"wants the simple scheduler at a step count that divides "
                    f"{steps}, and the shift the file was trained at")
    return ""


# ---- the heads at runtime ---------------------------------------------------


class HeadBank(nn.Module):
    """Both banks as one movable, accountable module, the way `LoraBank` is."""

    def __init__(self, banks):
        super().__init__()
        self.names = list(banks)
        for i, name in enumerate(self.names):
            weight, bias = banks[name]
            self.register_parameter(f"w{i}", nn.Parameter(weight, requires_grad=False))
            if bias is not None:
                self.register_parameter(f"b{i}", nn.Parameter(bias, requires_grad=False))

    def get(self, name: str):
        i = self.names.index(name)
        return getattr(self, f"w{i}"), getattr(self, f"b{i}", None)


class PlanState:
    """Per-thread live plans, one per head. The `ScheduleState` of this module."""

    def __init__(self):
        self._local = threading.local()

    def set(self, plans: dict):
        self._local.plans = plans

    def clear(self):
        self._local.plans = {}

    def plan_for(self, name: str):
        return getattr(self._local, "plans", {}).get(name)


class ParallelHead:
    """Object patch for one head's ``Linear.forward``: the block's mixed head.

    The bank replaces the checkpoint's head rather than adding to it — every
    interval was initialised from that head and then trained, so what is stored
    is the whole weight and the original is not read at all. Which also means
    there is nothing here for a quantized checkpoint to trip over: H3's two
    output heads are the fp32 island of every build.
    """

    def __init__(self, bank_patcher, state: PlanState, name: str, original):
        self.bank_patcher = bank_patcher
        self.bank: HeadBank = bank_patcher.model
        self.state = state
        self.name = name
        self.original = original

    def __call__(self, input: torch.Tensor, *args, **kwargs):
        plan = self.state.plan_for(self.name)
        if plan is None:
            # No plan means no sampler around this call — a probe, a shape pass,
            # anything that is not a step. The checkpoint's own head is the
            # honest answer there.
            return self.original(input, *args, **kwargs)
        weight, bias = self.bank.get(self.name)
        start, mix = plan
        weight = comfy.model_management.cast_to_device(
            weight[start: start + mix.shape[0]], input.device, input.dtype)
        mix = comfy.model_management.cast_to_device(mix, input.device, input.dtype)
        mixed = torch.einsum("n,noi->oi", mix, weight)
        mixed_bias = None
        if bias is not None:
            bias = comfy.model_management.cast_to_device(
                bias[start: start + mix.shape[0]], input.device, input.dtype)
            mixed_bias = torch.einsum("n,no->o", mix, bias)
        return F.linear(input, mixed, mixed_bias)


class PlanController:
    """APPLY_MODEL wrapper: arm both heads for the step this call belongs to."""

    def __init__(self, state: PlanState, steps: int, name: str = ""):
        self.state = state
        self.steps = steps
        self.name = name
        self.warned = False
        # One grid per shift, built once. The shifts are read every call because
        # they are the render's and a user may move them, but they rarely move.
        self._grids: dict[float, torch.Tensor] = {}

    def shifts(self, model):
        """The two flow clocks, as the render is actually running them."""
        sampling = getattr(model, "model_sampling", None)
        video = float(getattr(sampling, "shift", 1.0) or 1.0)
        audio = getattr(sampling, "audio_shift", None)
        return video, float(audio or video)

    def grid(self, shift: float) -> torch.Tensor:
        if shift not in self._grids:
            self._grids[shift] = time_grid(shift, self.steps)
        return self._grids[shift]

    def step_sigmas(self, sigma, sample_sigmas):
        """The two sigmas this step runs between. -> ``(from, to)``, or None."""
        if sample_sigmas is None:
            return None
        samples = torch.as_tensor(sample_sigmas).detach().double().flatten()
        current = torch.as_tensor(sigma).detach().double().flatten()
        if samples.numel() < 2 or current.numel() == 0:
            return None
        # Nearest rather than equal: a CFG render calls the model twice on one
        # sigma and the value has been through a dtype or a device on the way.
        index = int(torch.argmin((samples - current[0]).abs()).item())
        if index >= samples.numel() - 1:
            return None
        return float(samples[index].item()), float(samples[index + 1].item())

    def __call__(self, executor, x, t, c_concat=None, c_crossattn=None, control=None,
                 transformer_options=None, **kwargs):
        transformer_options = transformer_options or {}
        sample_sigmas = transformer_options.get("sample_sigmas")
        video_shift, audio_shift = self.shifts(executor.class_obj)
        if not self.warned and sample_sigmas is not None:
            self.warned = True
            complaint = verify(sample_sigmas, video_shift, self.steps)
            if complaint:
                LOG.warning("Continuity PDD%s: %s",
                            f" ({self.name})" if self.name else "", complaint)
        plans = {}
        step = self.step_sigmas(t, sample_sigmas)
        if step is not None:
            # The interval is the *video* clock's: it is the sampler's own sigma,
            # and the audio stream is at the matching place on its own grid by
            # construction. So both heads take the same slice and weight it by
            # their own interval widths, which is what the release does.
            covers = interval_of(step[0], step[1], video_shift, self.steps)
            if covers is not None:
                start, block = covers
                for bank, shift in ((VIDEO_BANK, video_shift), (AUDIO_BANK, audio_shift)):
                    weights = block_plan(self.grid(shift), start, block)[start: start + block]
                    plans[bank] = (start, weights.float())
        self.state.set(plans)
        try:
            return executor(x, t, c_concat, c_crossattn, control, transformer_options, **kwargs)
        finally:
            self.state.clear()


def attach(model_patcher, banks, tag: str, name: str = ""):
    """Patch both heads onto the bank and hand back the wrapper that arms them."""
    import comfy.model_patcher

    bank = HeadBank(banks)
    state = PlanState()
    bank_patcher = comfy.model_patcher.ModelPatcher(
        bank,
        load_device=comfy.model_management.get_torch_device(),
        offload_device=comfy.model_management.unet_offload_device(),
    )
    model_patcher.set_additional_models(tag, [bank_patcher])

    for bank_name in banks:
        forward_key = f"{HEAD_MODULE[bank_name]}.forward"
        original = model_patcher.get_model_object(forward_key)
        model_patcher.add_object_patch(
            forward_key, ParallelHead(bank_patcher, state, bank_name, original))
    return PlanController(state, num_steps(banks), name)


def bank_bytes(banks) -> int:
    """What the two banks will occupy, for the same report line the branches get."""
    total = 0
    for weight, bias in banks.values():
        total += weight.numel() * weight.element_size()
        if bias is not None:
            total += bias.numel() * bias.element_size()
    return total
