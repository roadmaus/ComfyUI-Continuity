"""The vendored ComfyUI-VDN-H3 copy is whole, re-rooted, and behaves as upstream says.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_vdnh3_vendor.py

`creator/vdnh3/` is upstream's code, copied at a pin with its imports re-rooted
into this package. Three things are pinned here. That the copy is whole — the
stamp, the LICENSE, every module the vendoring script names, and no import
left pointing at upstream's top-level name. That the pieces `vdn.py` calls are
there under the names it calls them by, which is the contract a re-sync can
break. And the one piece of upstream's math that needs no model: the released
adapters' three per-projection LoRA pairs fold into ComfyUI's fused QKV as one
pair, exactly — `delta_W = concat(B_i A_i) = B_fused A_fused`.

The first part runs anywhere. The rest wants torch, and the import of the
port's assembly module wants ComfyUI; each skips itself where its half is
missing, after the pure checks have run.
"""

import importlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout
from harness import FAILURES, check, passed, skip

passed("the vendored VDN-H3 copy is whole and folds adapters exactly")

HERE = os.path.join(layout.PY_ROOT, "vdnh3")
MODULES = ("spec", "adapters", "apply", "branch", "window", "hybrid", "nodes")

# ---- the copy is whole ----------------------------------------------------------

with open(os.path.join(HERE, "__init__.py"), encoding="utf-8") as handle:
    header = handle.read()
stamp = re.search(r'^REVISION = "([0-9a-f]*)"$', header, re.M)
check("the copy is stamped with a full commit", len(stamp.group(1)) if stamp else 0, 40)
check("the docstring names the same revision, short",
      bool(re.search(r"revision `" + re.escape(stamp.group(1)[:7]), header)) if stamp else False, True)
check("LICENSE travels with the copy", os.path.isfile(os.path.join(HERE, "LICENSE")), True)
for name in MODULES:
    check(f"{name}.py is there", os.path.isfile(os.path.join(HERE, f"{name}.py")), True)

# Upstream addresses itself as `vdn_h3`; a line still doing so would import a
# package this ComfyUI does not have, and only at the moment a stage is opened.
left = []
for name in MODULES:
    with open(os.path.join(HERE, f"{name}.py"), encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if re.match(r"\s*(from|import) vdn_h3\b", line):
                left.append(f"{name}.py:{number}")
check("no import still points at upstream's package name", left, [])

# `vdn.py` reads the stamp without importing the copy, the way `neural.py` does
# for mlxdlss, so the settings page can print it with no torch loaded.
vdn_source = os.path.join(layout.PY_ROOT, "vdn.py")
with open(vdn_source, encoding="utf-8") as handle:
    vdn_text = handle.read()
check("vdn.py calls the port's assembly function by the name it has",
      "_apply_vdn(" in vdn_text and "def _apply_vdn(" in open(os.path.join(HERE, "nodes.py"), encoding="utf-8").read(),
      True)

# ---- the adapter fold, exactly -----------------------------------------------------

try:
    import torch
except Exception as exc:  # noqa: BLE001
    skip(f"torch not importable ({type(exc).__name__}: {exc})")

sys.path.insert(0, HERE)
adapters = importlib.import_module("adapters")

torch.manual_seed(0)
hidden, rank = 32, 4
sd = {}
pairs = {}
for proj in ("to_q", "to_k", "to_v"):
    a = torch.randn(rank, hidden)
    b = torch.randn(hidden, rank)
    pairs[proj] = (a, b)
    sd[f"transformer_blocks.0.attn.orig.{proj}.lora_A.weight"] = a
    sd[f"transformer_blocks.0.attn.orig.{proj}.lora_B.weight"] = b
converted = adapters.convert_adapter(sd, {"rank": rank, "alpha": rank})
check("the three projections fold into one fused-qkv entry",
      list(converted), ["blocks.0.attn.qkv_proj"])
a_fused, b_fused, scale = converted["blocks.0.attn.qkv_proj"]
check("the fused pair has the fused shape",
      (tuple(a_fused.shape), tuple(b_fused.shape), scale), ((3 * rank, hidden), (3 * hidden, 3 * rank), 1.0))
want = torch.cat([pairs[p][1] @ pairs[p][0] for p in ("to_q", "to_k", "to_v")], dim=0)
check("the fold is exact: concat(B_i A_i) == B_fused A_fused",
      float((b_fused @ a_fused - want).abs().max()) < 1e-5, True)

# The swiglu halves swap: diffusers packs [value; gate], ComfyUI [gate; value].
b_ff = torch.randn(2 * hidden, rank)
ff = adapters.convert_adapter(
    {"transformer_blocks.0.ff.net.0.proj.lora_A.weight": torch.randn(rank, hidden),
     "transformer_blocks.0.ff.net.0.proj.lora_B.weight": b_ff},
    {"rank": rank, "alpha": rank})
check("the swiglu pair lands on fc1 with its halves swapped",
      (list(ff), bool(torch.equal(ff["blocks.0.mlp.fc1"][1],
                                  torch.cat([b_ff[hidden:], b_ff[:hidden]], dim=0)))),
      (["blocks.0.mlp.fc1"], True))

# ---- the assembly imports under ComfyUI ---------------------------------------------

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)
try:
    import comfy.model_patcher  # noqa: F401
    import folder_paths  # noqa: F401
except Exception as exc:  # noqa: BLE001
    skip(f"ComfyUI not importable ({type(exc).__name__}: {exc})")

pkg = layout.load("accel", "vdn", "vdnh3")
check("the pack's module reads the same stamp",
      pkg.vdn.upstream_commit(), stamp.group(1) if stamp else None)
port = importlib.import_module(f"{pkg.vdnh3.__name__}.nodes")
check("the assembly function is there", callable(getattr(port, "_apply_vdn", None)), True)
check("the stage list is a list, and a stage folder is registered with ComfyUI",
      (isinstance(pkg.vdn.checkpoints(), list), "vdn" in folder_paths.folder_names_and_paths),
      (True, True))
# A stage rides on the diffusion models, so it is looked for beside them —
# which on an `extra_model_paths` install is not where the LoRAs are.
wanted = {os.path.join(os.path.dirname(p), "vdn")
          for p in folder_paths.get_folder_paths("diffusion_models")}
check("vdn/ is registered beside every diffusion_models/ folder",
      wanted <= set(folder_paths.get_folder_paths("vdn")), True)
