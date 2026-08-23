"""What `lora.py` now does to a model, on a miniature H3.

The stock loader was replaced by the vendored `h3lora` stack — see that
package's docstring for why — and this is the test that says the replacement
does the job on a model shaped like the real one. Nothing is sampled: what is
checked is where the adapter *went*, which is the whole of what changed.

The model here is a four-block DiT with H3's own module names and H3's own adaLN
geometry, at toy widths. That is enough for every decision the stack makes:
which keys resolve, which layers branch rather than merge, what the adaLN port
does with a basis that does not match, and that a stack of two fuses into one
pair per layer.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_h3lora.py

Skips itself with a message where ComfyUI or torch is missing.
"""

import gc
import importlib.util
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import FAILURES, check, passed, skip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    import torch
    import torch.nn as nn
    import comfy.model_patcher
except Exception as exc:  # noqa: BLE001
    skip(f"ComfyUI not importable ({type(exc).__name__}: {exc})")


def _load(name):
    """One vendored module, without importing the pack — `__init__` wants a server."""
    for parent, path in (("mmc", ROOT), ("mmc.h3lora", os.path.join(ROOT, "h3lora"))):
        if parent not in sys.modules:
            package = types.ModuleType(parent)
            package.__path__ = [path]
            sys.modules[parent] = package
    spec = importlib.util.spec_from_file_location(
        f"mmc.h3lora.{name}", os.path.join(ROOT, "h3lora", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmc.h3lora.{name}"] = module
    spec.loader.exec_module(module)
    return module


keymap = _load("keymap")
adaln = _load("adaln")
h3lora = _load("apply")

# ---- a miniature H3 ---------------------------------------------------------

HIDDEN = 16
HEADS = 2
HEAD_DIM = 8
EXPAND = 6          # shift/scale/gate for attention and for the MLP
MODALITIES = 3      # video, text, audio — the three H3 packs into one sequence
ADALN_DIM = 8       # a curve bake: the pruned checkpoints' table width
BLOCKS = 4
RANK = 4


class AdalnProj(nn.Module):
    """H3's `AdalnProj`, at toy widths and with the attributes it is read by."""

    def __init__(self):
        super().__init__()
        self.expand, self.modalities, self.hidden = EXPAND, MODALITIES, HIDDEN
        self.linear = nn.Linear(ADALN_DIM, EXPAND * MODALITIES * HIDDEN, bias=True)


class Attention(nn.Module):
    def __init__(self):
        super().__init__()
        self.qkv_proj = nn.Linear(HIDDEN, 3 * HEADS * HEAD_DIM, bias=False)
        self.out_proj = nn.Linear(HEADS * HEAD_DIM, HIDDEN, bias=False)


class Mlp(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(HIDDEN, 4 * HIDDEN, bias=False)
        self.fc2 = nn.Linear(2 * HIDDEN, HIDDEN, bias=False)


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.attn = Attention()
        self.mlp = Mlp()
        self.adaln_proj = AdalnProj()


class DiT(nn.Module):
    def __init__(self, table):
        super().__init__()
        self.blocks = nn.ModuleList(Block() for _ in range(BLOCKS))
        self.adaln_t_table = table


class Model(nn.Module):
    """What a `ModelPatcher` wraps: the DiT under `diffusion_model`."""

    def __init__(self, table):
        super().__init__()
        self.diffusion_model = DiT(table)


def patcher(table=None):
    if table is None:
        table = torch.linspace(0, 1, 64).reshape(8, ADALN_DIM)
    model = Model(table)
    return comfy.model_patcher.ModelPatcher(
        model, load_device=torch.device("cpu"), offload_device=torch.device("cpu"))


# ---- LoRA files, in the conventions the trainers actually emit ---------------

def lora_pair(out_dim, in_dim, scale=1.0):
    return (torch.randn(out_dim, RANK) * scale, torch.randn(RANK, in_dim) * scale)


def diffusers_lora(adaln_dim=ADALN_DIM):
    """ai-toolkit / diffusers keys: `diffusion_model.blocks.N.attn.qkv_proj.lora_A`."""
    sd = {}
    for index in range(BLOCKS):
        up, down = lora_pair(3 * HEADS * HEAD_DIM, HIDDEN)
        sd[f"diffusion_model.blocks.{index}.attn.qkv_proj.lora_B.weight"] = up
        sd[f"diffusion_model.blocks.{index}.attn.qkv_proj.lora_A.weight"] = down
        up, down = lora_pair(EXPAND * MODALITIES * HIDDEN, adaln_dim)
        sd[f"diffusion_model.blocks.{index}.adaln_proj.linear.lora_B.weight"] = up
        sd[f"diffusion_model.blocks.{index}.adaln_proj.linear.lora_A.weight"] = down
    return sd


def kohya_lora():
    """kohya / musubi keys, underscored and alpha-carrying."""
    sd = {}
    for index in range(BLOCKS):
        up, down = lora_pair(HIDDEN, HEADS * HEAD_DIM)
        stem = f"lora_unet_blocks_{index}_attn_out_proj"
        sd[f"{stem}.lora_up.weight"] = up
        sd[f"{stem}.lora_down.weight"] = down
        sd[f"{stem}.alpha"] = torch.tensor(float(RANK))
    return sd


def entry(name, sd, strength=1.0, row=1):
    return {"name": name, "path": "", "weights": sd, "strength": strength, "row": row}


# ---- the key conventions all resolve ----------------------------------------

model = patcher()
index = keymap.build_module_index(model.model.state_dict().keys())

for label, sd in (("diffusers", diffusers_lora()), ("kohya", kohya_lora())):
    normalized, unmatched = keymap.normalize(sd, index)
    check(f"{label} keys all resolve", unmatched, [])
    check(f"{label} keys land under diffusion_model",
          all(key.startswith("diffusion_model.blocks.") for key in normalized), True)

# `qkv_proj` is one token and must never be split into `qkv` and `proj`.
normalized, _ = keymap.normalize(kohya_lora(), index)
check("underscored module names are resolved against the model's own keys",
      any(".attn.out_proj." in key for key in normalized), True)

# ---- one LoRA, applied ------------------------------------------------------

model = patcher()
patched, report = h3lora.apply_stack(model, [entry("style", diffusers_lora())])
text = report.text()
check("the stack reports the file it was given", "style @ 1" in text, True)
check("nothing was left unmatched", "unmatched" in text, False)
check("no layer was missed", "matched no layers" in text, False)
# An unquantized base merges: the merge is exact there, and a runtime branch
# would cost FLOPs for nothing. That is `auto`, and it is the default.
check("an unquantized base merges rather than branches", report.branched, 0)
check("every layer of the file was placed", report.merged, len(diffusers_lora()) // 2)
check("the model it was handed is untouched", patched is not model, True)

# ---- `branch` never touches a weight ----------------------------------------

model = patcher()
patched, report = h3lora.apply_stack(model, [entry("style", diffusers_lora())], mode="branch")
check("branch mode branches every plain pair", report.merged, 0)
check("branch mode leaves a live bank behind", report.bank_bytes > 0, True)

# ---- a stack of two fuses ---------------------------------------------------

model = patcher()
patched, report = h3lora.apply_stack(
    model,
    [entry("style", diffusers_lora(), row=1),
     entry("motion", diffusers_lora(), strength=0.5, row=2)],
    mode="branch")
check("both files are accounted for",
      ("style @ 1" in report.text(), "motion @ 0.5" in report.text()), (True, True))
check("two files on one layer are one bank of layers, not two",
      report.text().count("branch bank:"), 1)

# ---- the adaLN basis is per source table, not per stack ----------------------
#
# Upstream's context memoised the first fit and handed it to every later LoRA
# (AUDIT_REPORT H1). Two curve bakes have different tables, so on a dense target
# that silently rebases the second adapter onto the first one's basis.

table_a = torch.linspace(0, 1, 64).reshape(8, ADALN_DIM)
table_b = torch.linspace(0, 2, 64).reshape(8, ADALN_DIM) ** 2

context = adaln.AdalnContext(ADALN_DIM, table=None, grid_path="")   # dense target
check("a dense target with no grid cannot port", context.basis(curve_table=table_a), None)
check("and the next LoRA is not poisoned by that",
      context.basis(curve_table=table_b), None)

# With a grid to fit against, the two tables must produce two bases — and the
# context must hand each LoRA its own. Upstream returned the first fit to every
# later caller, which is the silent half of the bug: plausibly shaped, wrong.
# The grid is pushed into the loader's own cache rather than written to disk;
# what is under test is the context, not safetensors.
GRID = "<test grid>"
adaln._grid_cache[GRID] = torch.randn(8, 2688)
context = adaln.AdalnContext(2688, table=None, grid_path=GRID)
first = context.basis(curve_table=table_a)
second = context.basis(curve_table=table_b)
check("a dense target fits both tables", (first is None, second is None), (False, False))
check("and gives each source table its own basis",
      torch.allclose(first[0], second[0]), False)
check("the same table twice is fitted once and cached",
      context.basis(curve_table=table_a)[0] is first[0], True)

# Table-to-table needs no grid at all, and must survive a table on another
# device the way a model's own table arrives (AUDIT_REPORT H5). CPU here is the
# only device this test can count on; what is pinned is that both sides are
# moved rather than assumed.
m, a_const, residual = adaln.fit_table_to_table(table_a, table_b)
check("a table-to-table fit comes back the right shape",
      (tuple(m.shape), tuple(a_const.shape)), ((ADALN_DIM, ADALN_DIM), (ADALN_DIM,)))
check("and reports how well it fit", 0.0 <= residual < 1.0, True)

# ---- an adaLN width the checkpoint does not have ----------------------------
#
# A LoRA trained against the dense bake carries 2688-wide adaLN A-matrices. On
# this curve model they cannot be applied as they are, and dropping them
# silently is what the port exists to avoid — with no grid to fit against, the
# pairs are dropped and *said*, and the rest of the file still lands.

model = patcher()
patched, report = h3lora.apply_stack(model, [entry("dense-turbo", diffusers_lora(adaln_dim=2688))])
check("adaLN pairs that cannot be ported are reported as dropped",
      "adaLN dropped" in report.text(), True)
check("the rest of the file still lands", report.merged > 0, True)

# ---- the branch forward writes into its own accumulator ---------------------
#
# `out` at a branched linear is the widest tensor in the model — for H3's SwiGLU
# MLP it is the fc1 activation, gigabytes of it at video sequence lengths — and
# the forward used to hold three of them at once (`out`, `delta`, `out + delta`).
# That third copy is what OOM'd a 32 GB card mid-block. The maths below must
# still be out + up @ (scale * (down @ x)) + bias_scale @ bias; what is new is
# that it lands in the tensor the wrapped linear already returned.

branch_mod = sys.modules["mmc.h3lora.branch"]
schedule_mod = sys.modules["mmc.h3lora.schedule"]
torch.manual_seed(0)
D_IN, D_OUT, RANK = 16, 24, 4
linear = nn.Linear(D_IN, D_OUT, bias=False)
up, down = torch.randn(D_OUT, RANK), torch.randn(RANK, D_IN)
curve = schedule_mod.Schedule()
port = torch.randn(D_OUT)
bank = branch_mod.LoraBank(
    {"m": branch_mod.FusedBranch(up, down, [(0, RANK, curve, 2.0)], [(port, curve)])})
state = schedule_mod.ScheduleState()
seen = {}


def wrapped(value):
    seen["out"] = linear(value)
    return seen["out"]


forward = branch_mod.LoraBranch(types.SimpleNamespace(model=bank), state, "m", wrapped)
x = torch.randn(2, 5, D_IN)
rank_scales, bias_scales = torch.full((RANK,), 0.7), torch.tensor([0.3])

state.clear()
got = forward(x)
check("an unscheduled branch is exactly out + up @ down @ x",
      torch.equal(got, linear(x) + torch.nn.functional.linear(
          torch.nn.functional.linear(x, down), up)), True)
check("and it is the wrapped linear's own tensor, not a third copy",
      got.data_ptr() == seen["out"].data_ptr(), True)

state.set({"m": rank_scales.clone()}, {"m": bias_scales.clone()})
scaled = torch.nn.functional.linear(x, down) * rank_scales
want = linear(x) + torch.nn.functional.linear(scaled, up) + bias_scales @ bank.get_bias("m")
got = forward(x)
state.clear()
check("a scheduled branch still scales the rank slice and adds the ported bias",
      torch.allclose(got, want, atol=1e-5), True)
check("and it too accumulates in place",
      got.data_ptr() == seen["out"].data_ptr(), True)

# Every patcher built here is dropped while ComfyUI is still importable.
# `ModelPatcher.__del__` reaches for `comfy.patcher_extension` on the way out,
# and at interpreter shutdown that module is already None — which prints a
# traceback under a suite that passed.
del model, patched
gc.collect()

passed("the vendored H3 LoRA stack holds: keys, merge, branch, fusion and adaLN")
