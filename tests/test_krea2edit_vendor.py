"""The vendored Krea2Edit copy is whole, and its patch still fits core's Krea 2.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_krea2edit_vendor.py

`creator/krea2edit/` is upstream's one module, copied at a pin as `nodes.py`.
Three things are pinned here. That the copy is whole — the stamp, the LICENSE,
and the two classes `families/krea2/edit.py` calls, under the names and with the
arguments it calls them by, which is the contract a re-sync can break. That the
DIFFUSION_MODEL wrapper takes the positional shape core's Krea 2 forward calls
it with — upstream broke once already when core added `ref_latents` (upstream's
own regression test, adapted). And that a real Krea 2 DiT from this core,
shrunk to a few layers and sampled on the CPU through `ContinuityKrea2EditPatch`,
comes out finite, comes out different for being shown the pictures, and never
VAE-encodes while the sampler is running.

The first part runs anywhere; the rest wants torch and ComfyUI and skips itself
where either is missing, after the pure checks have run.
"""

import asyncio
import importlib
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout
from harness import FAILURES, check, passed, skip

passed("the vendored Krea2Edit copy is whole and fits this core's Krea 2")

HERE = os.path.join(layout.PY_ROOT, "krea2edit")

# ---- the copy is whole ------------------------------------------------------------

with open(os.path.join(HERE, "__init__.py"), encoding="utf-8") as handle:
    header = handle.read()
stamp = re.search(r'^REVISION = "([0-9a-f]*)"$', header, re.M)
check("the copy is stamped with a full commit", len(stamp.group(1)) if stamp else 0, 40)
check("the docstring names the same revision, short",
      bool(re.search(r"revision `" + re.escape(stamp.group(1)[:7]), header)) if stamp else False,
      True)
release = re.search(r'^VERSION = "(\d+)\.\d+\.\d+"$', header, re.M)
check("the copy is a V2 release of the nodes — the V2 LoRAs need one",
      int(release.group(1)) >= 2 if release else False, True)
check("LICENSE travels with the copy", os.path.isfile(os.path.join(HERE, "LICENSE")), True)
with open(os.path.join(HERE, "nodes.py"), encoding="utf-8") as handle:
    body = handle.read()
for name in ("class Krea2EditModelPatch", "class Krea2EditGroundedEncode",
             "def krea2_edit_forward", "REF_POSITIONS = "):
    check(f"nodes.py still has {name}", name in body, True)

# ---- the contract edit.py calls ---------------------------------------------------

try:
    import torch  # noqa: F401
except Exception as exc:  # noqa: BLE001
    skip(f"torch not importable ({type(exc).__name__}: {exc})")

ROOT = os.path.dirname(layout.PY_ROOT)
PACKAGE = os.path.basename(ROOT)
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    try:
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
        server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))
    sys.path.insert(0, os.path.dirname(ROOT))


try:
    _boot()
except Exception as exc:  # noqa: BLE001
    skip(f"ComfyUI not importable ({type(exc).__name__}: {exc})")

# Outside the skip guard: a pack that will not import is a failure, not a skip.
port = importlib.import_module(f"{PACKAGE}.creator.krea2edit.nodes")
edit = importlib.import_module(f"{PACKAGE}.creator.families.krea2.edit")
k2 = importlib.import_module(f"{PACKAGE}.creator.families.krea2.still")

patch_args = inspect.signature(port.Krea2EditModelPatch.patch).parameters
for name in ("source_latent", "source_image", "source_image_b", "vae", "target_latent",
             "fit_mode", "ref_boost", "ref_boost_a", "ref_position", "ref_position_a"):
    check(f"the patch still takes {name}", name in patch_args, True)
encode_args = inspect.signature(port.Krea2EditGroundedEncode.encode).parameters
for name in ("clip", "prompt", "image", "image_b", "grounding_px"):
    check(f"the grounded encode still takes {name}", name in encode_args, True)
check("every placement offered is one upstream knows",
      set(k2.PLACEMENTS.values()) <= set(port.REF_POSITIONS), True)

# ---- the wrapper takes core's call shape --------------------------------------------

import comfy.patcher_extension as pe  # noqa: E402


class _Inner:
    def process_latent_in(self, x):
        return x


class _Patcher:
    def __init__(self):
        self.model = _Inner()
        self.model_options = {}

    def clone(self):
        twin = _Patcher()
        twin.model = self.model
        return twin


def _wrapper():
    (patched,) = port.Krea2EditModelPatch().patch(_Patcher(), {"samples": object()})
    return patched.model_options["transformer_options"]["wrappers"][
        pe.WrappersMP.DIFFUSION_MODEL]["krea2_edit"][0]


captured = {}
real_forward = port.krea2_edit_forward
port.krea2_edit_forward = lambda dm, x, t, ctx, src, to, **k: captured.__setitem__("to", to)
try:
    for shape, args in (("before ref_latents", (None, None, None, None, {"tag": "old"})),
                        ("with ref_latents", (None, None, None, None, ["ref"], {"tag": "new"}))):
        pe.WrapperExecutor(original=lambda *a, **k: None, class_obj=object(),
                           wrappers=[_wrapper()], idx=0).execute(*args)
        check(f"the wrapper binds transformer_options to the trailing dict ({shape})",
              captured.get("to"), args[-1])
finally:
    port.krea2_edit_forward = real_forward

# ---- a real Krea 2 DiT, small, through the internal node ------------------------------

import comfy.model_patcher  # noqa: E402
import comfy.sample  # noqa: E402
import comfy.supported_models  # noqa: E402

config = comfy.supported_models.Krea2({
    "image_model": "krea2", "features": 64, "heads": 4, "kvheads": 2, "layers": 2,
    "txtdim": 32, "txtlayers": 2, "txtheads": 2, "txtkvheads": 2, "tdim": 32})
config.set_inference_dtype(torch.float32, None)
base = config.get_model({}, device="cpu")
torch.manual_seed(0)
for parameter in base.diffusion_model.parameters():
    torch.nn.init.normal_(parameter, std=0.05)
cpu = torch.device("cpu")
model = comfy.model_patcher.ModelPatcher(base, load_device=cpu, offload_device=cpu)


class FakeVAE:
    """Encodes a picture to a latent of the right grid, counting the calls."""

    calls = 0

    def encode(self, pixels):
        FakeVAE.calls += 1
        b, h, w, _ = pixels.shape
        seeded = torch.Generator().manual_seed(int(pixels.sum() * 1000) % 2 ** 31)
        return torch.randn(b, 16, h // 8, w // 8, generator=seeded)


target = {"samples": torch.zeros(1, 16, 8, 12)}            # a 64x96 canvas
scene, person = torch.rand(1, 80, 120, 3), torch.rand(1, 96, 64, 3)
context = torch.randn(1, 5, 64)


def sample(patched):
    noise = torch.randn(1, 16, 8, 12, generator=torch.Generator().manual_seed(1))
    return comfy.sample.sample(patched, noise, 2, 1.0, "euler", "simple",
                               [[context, {}]], [[torch.zeros_like(context), {}]],
                               target["samples"], denoise=1.0, seed=1)


plain = sample(model)
for label, extra in (("one picture", {}), ("a scene and a person", {"image_b": person})):
    out = edit.ContinuityKrea2EditPatch.execute(model, FakeVAE(), target, scene, 2.5, 1.0,
                                                "beside", "aligned", **extra)
    patched = out.args[0] if hasattr(out, "args") else out[0]
    before = FakeVAE.calls
    got = sample(patched)
    check(f"{label}: the render is finite", bool(torch.isfinite(got).all()), True)
    check(f"{label}: the pictures change it", bool((got - plain).abs().max() > 1e-4), True)
    check(f"{label}: nothing is encoded while the sampler runs", FakeVAE.calls - before, 0)
check("the unpatched model is left alone",
      bool((sample(model) - plain).abs().max() < 1e-6), True)


# Dropped here rather than at interpreter teardown, where a ModelPatcher's
# `__del__` runs after the modules it calls into are gone.
del model, patched, out, base
