"""The parallel decoder: the grid it steps on, the trunk rewrite, the mixed head.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_pdd.py

alibaba-pai's acceleration files are a trunk LoRA plus a bank of 32 per-interval
output heads, and every claim `h3lora/pdd.py` makes about them is checkable
without a checkpoint or a GPU:

* the block boundaries it says a render has to step on are the sigmas core's
  `simple` scheduler already produces, which is why nothing is plumbed;
* the grid and the block plan are the released implementation's, formula for
  formula (`minimax_h3_pdd.py`, restated here rather than imported so the test
  is an independent statement of it);
* the trunk rewrite is exact — the fused q/k/v delta *is* the three deltas it
  was given, and the SwiGLU swap leaves the function alone;
* a bank whose intervals all hold the same head reproduces that head, whatever
  the plan, which is the invariant that makes a mixed head a mean velocity.

Skips itself with a message if ComfyUI cannot be imported.
"""

import os
import sys

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    import layout
    pdd = layout.load("h3_pdd").h3_pdd
    import comfy.model_sampling
    import comfy.samplers
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

from harness import FAILURES, check, passed

# The two clocks as H3 ships them, and the grid the released files were
# distilled against.
VIDEO_SHIFT, AUDIO_SHIFT = 12.0, 3.0
STEPS, BLOCK = 32, 4


# ---- the released implementation, restated ----------------------------------
#
# `minimax_h3_pdd.py` from the model card, reduced to the two functions this
# module claims to reproduce. Written out rather than imported: a test that
# fetches its own oracle proves nothing when the fetch fails.

def ref_time_grid(shift, steps):
    sigma = torch.linspace(1.0, 0.0, steps + 1, dtype=torch.float64)
    return 1.0 - (shift * sigma / (1 + (shift - 1) * sigma))


def ref_plan(step_sizes, start, block):
    plan = torch.zeros(1, step_sizes.shape[0], dtype=step_sizes.dtype)
    span = step_sizes[start: start + block].sum()
    plan[0, start: start + block] = step_sizes[start: start + block] / span
    return plan


for shift in (VIDEO_SHIFT, AUDIO_SHIFT, 1.0):
    check(f"grid matches the release at shift {shift:g}",
          bool(torch.allclose(pdd.time_grid(shift, STEPS), ref_time_grid(shift, STEPS))),
          True)
    sizes = ref_time_grid(shift, STEPS).diff()
    for start in (0, 4, 28):
        check(f"plan matches the release at shift {shift:g} block {start}",
              bool(torch.allclose(pdd.block_plan(pdd.time_grid(shift, STEPS), start, BLOCK),
                                  ref_plan(sizes, start, BLOCK)[0])),
              True)

# A block's weights are a weighted mean, so they sum to one - that is what makes
# the mixed head a velocity rather than a scaled one.
plan = pdd.block_plan(pdd.time_grid(VIDEO_SHIFT, STEPS), 8, BLOCK)
check("a block's weights sum to 1", round(float(plan.sum()), 12), 1.0)
check("only the block is weighted", int((plan != 0).sum()), BLOCK)


# ---- the boundaries are core's own simple schedule ---------------------------
#
# The whole reason a PDD render needs no sigma plumbing. If this ever stops
# holding, the node has to hand the sampler its own sigmas.

def simple_sigmas(shift, steps):
    sampling = comfy.model_sampling.ModelSamplingDiscreteFlow()
    sampling.set_parameters(shift=shift)
    return comfy.samplers.simple_scheduler(sampling, steps).double()


def covered(sigmas, shift=VIDEO_SHIFT):
    """Every step of a schedule as the intervals it covers, or None where it misses."""
    return [pdd.interval_of(float(sigmas[i]), float(sigmas[i + 1]), shift, STEPS)
            for i in range(len(sigmas) - 1)]

for nfe in (4, 8, 16):
    sigmas = simple_sigmas(VIDEO_SHIFT, nfe)
    check(f"simple at {nfe} steps walks the grid a block at a time",
          covered(sigmas), [(k * (STEPS // nfe), STEPS // nfe) for k in range(nfe)])
    check(f"{nfe} steps verifies clean", pdd.verify(sigmas, VIDEO_SHIFT, STEPS), "")

# ... and the schedules that are not it are reported rather than run silently.
check("a 6-step render does not divide the grid",
      pdd.verify(simple_sigmas(VIDEO_SHIFT, 6), VIDEO_SHIFT, STEPS) != "", True)
beta = comfy.samplers.calculate_sigmas(
    (lambda s: (s.set_parameters(shift=VIDEO_SHIFT), s)[1])(
        comfy.model_sampling.ModelSamplingDiscreteFlow()), "beta", 8).double()
check("the beta scheduler is reported", pdd.verify(beta, VIDEO_SHIFT, STEPS) != "", True)
check("the wrong shift is reported",
      pdd.verify(simple_sigmas(6.0, 8), VIDEO_SHIFT, STEPS) != "", True)
# 16 steps is the one place `simple`'s 1000-entry table cannot land exactly; the
# tolerance is in grid units so it is the same slack everywhere, and this is
# what it is there for.
check("the table's own rounding is still on the grid",
      covered(simple_sigmas(VIDEO_SHIFT, 16))[0], (0, 2))

# The two places this pack samples something other than a whole schedule. Both
# used to be unreachable — a step counter would have called the first step of
# each block zero — and both are ordinary here, because the sigmas say where
# they are.
half = comfy.samplers.calculate_sigmas(
    (lambda s: (s.set_parameters(shift=VIDEO_SHIFT), s)[1])(
        comfy.model_sampling.ModelSamplingDiscreteFlow()), "simple", 16).double()[-9:]
check("a refine pass picks up halfway down the grid",
      covered(half), [(16 + 2 * k, 2) for k in range(8)])
check("...and verifies clean", pdd.verify(half, VIDEO_SHIFT, STEPS), "")

lead = simple_sigmas(VIDEO_SHIFT, 8)[2:]
check("a lead-in's second sitting starts where the first left off",
      covered(lead), [(8 + 4 * k, 4) for k in range(6)])


# ---- the trunk rewrite -------------------------------------------------------

RANK, HIDDEN, HEADS, FFN = 4, 8, 6, 10
torch.manual_seed(0)


def lora(out_dim, in_dim=HIDDEN):
    return (torch.randn(RANK, in_dim, dtype=torch.float64),
            torch.randn(out_dim, RANK, dtype=torch.float64))


qkv = {name: lora(HEADS) for name in ("to_q", "to_k", "to_v")}
fc1 = lora(FFN * 2)
source = {}
for name, (down, up) in qkv.items():
    source[f"blocks.0.attn.{name}.lora_down"] = down
    source[f"blocks.0.attn.{name}.lora_up"] = up
source["blocks.0.ff.net.0.proj.lora_down"], source["blocks.0.ff.net.0.proj.lora_up"] = fc1
source["blocks.0.ff.net.2.lora_down"], source["blocks.0.ff.net.2.lora_up"] = lora(HIDDEN, FFN)
source["blocks.0.attn.to_out.0.lora_down"], source["blocks.0.attn.to_out.0.lora_up"] = lora(HIDDEN, HEADS)
source["blocks.0.adaln_proj.linear.lora_down"], source["blocks.0.adaln_proj.linear.lora_up"] = lora(HIDDEN)
source["token_refiner.refiner_blocks.1.attn.to_q.lora_down"] = qkv["to_q"][0]
source["token_refiner.refiner_blocks.1.attn.to_q.lora_up"] = qkv["to_q"][1]
source["token_refiner.refiner_blocks.1.attn.to_k.lora_down"] = qkv["to_k"][0]
source["token_refiner.refiner_blocks.1.attn.to_k.lora_up"] = qkv["to_k"][1]
source["token_refiner.refiner_blocks.1.attn.to_v.lora_down"] = qkv["to_v"][0]
source["token_refiner.refiner_blocks.1.attn.to_v.lora_up"] = qkv["to_v"][1]

check("the released form is recognised", pdd.is_diffusers(source), True)
converted = pdd.convert_trunk(source)

check("modules land on H3's names", sorted({
    key.rsplit(".lora_", 1)[0].rsplit(".alpha", 1)[0] for key in converted}), [
    "diffusion_model.blocks.0.adaln_proj.linear",
    "diffusion_model.blocks.0.attn.out_proj",
    "diffusion_model.blocks.0.attn.qkv_proj",
    "diffusion_model.blocks.0.mlp.fc1",
    "diffusion_model.blocks.0.mlp.fc2",
    "diffusion_model.token_refiner.blocks.1.attn.qkv_proj",
])

# The fused delta is the three deltas, in the order the projection splits.
fused = (converted["diffusion_model.blocks.0.attn.qkv_proj.lora_B.weight"]
         @ converted["diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight"])
want = torch.cat([up @ down for down, up in (qkv["to_q"], qkv["to_k"], qkv["to_v"])], dim=0)
check("q, k and v fuse exactly", bool(torch.allclose(fused, want)), True)
check("the fused rank is three ranks",
      converted["diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight"].shape[0], RANK * 3)
# Core reads scale as alpha/rank, so an unwritten alpha and a rank three times
# as long have to mean the same 1.0 the branches were trained at.
check("no alpha is invented",
      "diffusion_model.blocks.0.attn.qkv_proj.alpha" in converted, False)

# The SwiGLU swap is a claim about the *function*: diffusers computes
# value * silu(gate) from [value; gate], core computes silu(gate) * value from
# [gate; value], so the same adapter has to come out doing the same thing.
base_comfy = torch.randn(FFN * 2, HIDDEN, dtype=torch.float64)     # [gate; value]
base_diffusers = torch.cat((base_comfy[FFN:], base_comfy[:FFN]))   # [value; gate]
x = torch.randn(3, HIDDEN, dtype=torch.float64)

diff_delta = fc1[1] @ fc1[0]
value, gate = F.linear(x, base_diffusers + diff_delta).chunk(2, dim=-1)
diffusers_out = value * F.silu(gate)

comfy_delta = (converted["diffusion_model.blocks.0.mlp.fc1.lora_B.weight"]
               @ converted["diffusion_model.blocks.0.mlp.fc1.lora_A.weight"])
gate, value = F.linear(x, base_comfy + comfy_delta).chunk(2, dim=-1)
comfy_out = F.silu(gate) * value

check("the SwiGLU halves swap into the same function",
      bool(torch.allclose(diffusers_out, comfy_out)), True)

# A file already in ComfyUI's names is not this module's business.
check("a repackaged file is left to keymap",
      pdd.is_diffusers({"diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight": x}), False)


# ---- reading the bank out of the file ---------------------------------------

banks_sd = {
    "proj_out.weight": torch.randn(STEPS, 6, HIDDEN),
    "proj_out.bias": torch.randn(STEPS, 6),
    "audio_proj_out.weight": torch.randn(STEPS, 2, HIDDEN),
    "audio_proj_out.bias": torch.randn(STEPS, 2),
    "blocks.0.attn.to_q.lora_down": torch.randn(RANK, HIDDEN),
}
banks = pdd.take_heads(banks_sd)
check("the bank comes out", sorted(banks), ["audio_proj_out", "proj_out"])
check("the grid is read off the bank", pdd.num_steps(banks), STEPS)
check("what is left is a plain LoRA", sorted(banks_sd), ["blocks.0.attn.to_q.lora_down"])
check("an ordinary LoRA has no bank",
      pdd.take_heads({"diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight": x}), None)
# A two-dimensional head is a "complete pruned" LoRA's full-weight passenger,
# not a bank, and must not be mistaken for one.
check("a plain head replacement is not a bank",
      pdd.take_heads({"proj_out.weight": torch.randn(6, HIDDEN)}), None)


# ---- the mixed head ----------------------------------------------------------

head = nn.Linear(HIDDEN, 6)
state = pdd.PlanState()


class _Patcher:
    """Just enough of a bank patcher for the head to read its weights off."""

    def __init__(self, model):
        self.model = model


def mixed(bank_weight, bank_bias, start, mix, x):
    bank = pdd.HeadBank({"proj_out": (bank_weight, bank_bias)})
    patched = pdd.ParallelHead(_Patcher(bank), state, "proj_out", head.forward)
    state.set({"proj_out": (start, mix)})
    try:
        return patched(x)
    finally:
        state.clear()


x = torch.randn(3, HIDDEN)
repeated = head.weight.detach()[None].repeat(STEPS, 1, 1).clone()
repeated_bias = head.bias.detach()[None].repeat(STEPS, 1).clone()
plan = pdd.block_plan(pdd.time_grid(VIDEO_SHIFT, STEPS), 8, BLOCK)[8: 8 + BLOCK].float()

check("a flat bank reproduces the head it was made from",
      bool(torch.allclose(mixed(repeated, repeated_bias, 8, plan, x), head(x), atol=1e-6)), True)

# The mix is the weighting it was handed, and it reads the block it was pointed
# at rather than the front of the bank.
bank_weight = torch.randn(STEPS, 6, HIDDEN)
bank_bias = torch.randn(STEPS, 6)
want_weight = torch.einsum("n,noi->oi", plan, bank_weight[8: 8 + BLOCK])
want_bias = torch.einsum("n,no->o", plan, bank_bias[8: 8 + BLOCK])
check("the mixed head is the block's weighted mean",
      bool(torch.allclose(mixed(bank_weight, bank_bias, 8, plan, x),
                          F.linear(x, want_weight, want_bias), atol=1e-5)), True)

# Off the sampler there is no plan, and the checkpoint's own head answers.
check("no plan falls back to the checkpoint's head",
      bool(torch.allclose(
          pdd.ParallelHead(_Patcher(pdd.HeadBank({"proj_out": (bank_weight, bank_bias)})),
                           state, "proj_out", head.forward)(x),
          head(x))), True)


# ---- arming, step by step ----------------------------------------------------

class _Sampling:
    shift = VIDEO_SHIFT
    audio_shift = AUDIO_SHIFT


class _Executor:
    class_obj = type("Model", (), {"model_sampling": _Sampling()})()

    def __init__(self):
        self.seen = None

    def __call__(self, x, t, *args, **kwargs):
        self.seen = {name: (start, mix.clone())
                     for name, (start, mix) in controller.state._local.plans.items()}
        return x


controller = pdd.PlanController(pdd.PlanState(), STEPS, "acc-8step")


def arm(sigmas, at):
    """One forward at `sigmas[at]`, as the sampler would make it."""
    executor = _Executor()
    controller(executor, torch.zeros(1), torch.tensor([float(sigmas[at])]),
               transformer_options={"sample_sigmas": sigmas})
    return executor.seen


sigmas = simple_sigmas(VIDEO_SHIFT, 8)

for step in range(8):
    seen = arm(sigmas, step)
    check(f"step {step} arms block {step}", seen["proj_out"][0], step * BLOCK)
    check(f"step {step} arms the audio head too", seen["audio_proj_out"][0], step * BLOCK)
    check(f"step {step} weights the video grid",
          bool(torch.allclose(
              seen["proj_out"][1].double(),
              pdd.block_plan(pdd.time_grid(VIDEO_SHIFT, STEPS), step * BLOCK, BLOCK)[
                  step * BLOCK: (step + 1) * BLOCK])), True)
    # The audio stream runs its own clock, so its plan is a different one.
    check(f"step {step} weights the audio grid on the audio shift",
          bool(torch.allclose(
              seen["audio_proj_out"][1].double(),
              pdd.block_plan(pdd.time_grid(AUDIO_SHIFT, STEPS), step * BLOCK, BLOCK)[
                  step * BLOCK: (step + 1) * BLOCK])), True)

check("the two clocks disagree",
      bool(torch.allclose(
          pdd.block_plan(pdd.time_grid(VIDEO_SHIFT, STEPS), 16, BLOCK),
          pdd.block_plan(pdd.time_grid(AUDIO_SHIFT, STEPS), 16, BLOCK))), False)

# A CFG render calls the model twice on the same sigma; both calls are the same
# step and must arm the same block.
executor = _Executor()
controller(executor, torch.zeros(1), torch.tensor([float(sigmas[3]), float(sigmas[3])]),
           transformer_options={"sample_sigmas": sigmas})
check("a doubled forward is still one step", executor.seen["proj_out"][0], 3 * BLOCK)

# And the plan is cleared afterwards, so a head called outside a step does not
# read the last one's.
check("the plan does not outlive the call", controller.state.plan_for("proj_out"), None)

# A four-step render is the other released count: eight intervals a block.
short = simple_sigmas(VIDEO_SHIFT, 4)
check("four steps take eight intervals a block", arm(short, 2)["proj_out"][0], 16)
check("four steps mix eight heads", int(arm(short, 2)["proj_out"][1].numel()), 8)

# The refine pass and the lead-in, at the sampler rather than on paper: neither
# starts at the top of the schedule and both have to arm where they really are.
check("a refine pass arms the half of the grid it is refining",
      [arm(half, at)["proj_out"][0] for at in (0, 7)], [16, 30])
check("a lead-in's second sitting arms where the first stopped",
      [arm(lead, at)["proj_out"][0] for at in (0, 5)], [8, 28])

# A step that lands between intervals arms nothing at all, and the heads fall
# back to the checkpoint's rather than to a block that is not this step's.
check("a schedule off the grid arms nothing", arm(beta, 3), {})

passed("all PDD tests passed")
