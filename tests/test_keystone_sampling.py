"""The keystone through core's real sampler, on a tiny random H3.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_keystone_sampling.py

`test_keystone.py` checks the tensors and the wrapper against a stand-in
model. This one runs them through what a render runs: core's `MiniMaxH3`
model class at a toy size (two blocks, random weights, CPU), behind a real
`ModelPatcher`, sampled by `comfy.sample.sample` with the masked seam's run,
the keystone and context noise in the latent and the capstone wrapper on the
model. Nothing about the *picture* is being tested — the weights are noise —
only that the shapes, the mask and the wrapper survive the real forward, the
inpaint path and the AV packing, and that what comes out is restored.
"""

import os
from pathlib import Path
import sys

import layout
from harness import check, skip

comfy = Path(os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
if not (comfy / "folder_paths.py").is_file():
    skip("set COMFYUI_PATH to a ComfyUI installation")
sys.path.insert(0, str(comfy))
sys.argv = ["test_keystone_sampling", "--cpu"]
import comfy.cli_args  # noqa: E402
comfy.cli_args.args.cpu = True
import torch  # noqa: E402
import comfy.model_patcher  # noqa: E402
import comfy.nested_tensor  # noqa: E402
import comfy.sample  # noqa: E402
import comfy.supported_models as supported  # noqa: E402

if not hasattr(supported, "MiniMaxH3"):
    skip("this ComfyUI has no MiniMax H3")

pkg = layout.load("keystone", "encode", package="keystone_sampling")
ks, encoder = pkg.keystone, pkg.encode

torch.manual_seed(0)
config = supported.MiniMaxH3({
    "image_model": "minimax_h3", "hidden_size": 128, "num_layers": 2,
    "token_refiner_num_layers": 1, "num_attention_heads": 1, "attention_head_dim": 128,
    "ffn_hidden_size": 128, "text_dim": 32, "time_embed_hidden_size": 64,
    "time_embed_dim": 64})
config.set_inference_dtype(torch.float32, torch.float32)
model = config.get_model({})
model.requires_grad_(False)
for parameter in model.diffusion_model.parameters():
    torch.nn.init.normal_(parameter, std=0.02)
model.diffusion_model.rope.inv_freq = torch.rand(16)
cpu = torch.device("cpu")
patcher = comfy.model_patcher.ModelPatcher(model, load_device=cpu, offload_device=cpu)
torch.set_grad_enabled(False)

C, H, W, T = 24, 8, 8, 12
silence = torch.zeros(1, 32, 2, 40)
first = torch.randn(1, C, 10, H, W)
run = torch.randn(1, C, 7, H, W)
target = {"samples": comfy.nested_tensor.NestedTensor((torch.zeros(1, C, T, H, W), silence))}
grafted, _ = ks.graft(encoder._masked_prefix(target, run),
                      comfy.nested_tensor.NestedTensor((first, silence)),
                      capstone=True, noise=1.0)

seen = []
locked = ks.lock(patcher, grafted[ks.KEY]["back"], 3)
inner = locked.model_options["model_function_wrapper"]


def spy(apply_model, args):
    def counted(x, t, **c):
        seen.append(c["latent_shapes"][0][2])
        return apply_model(x, t, **c)
    return inner(counted, args)


locked.model_options["model_function_wrapper"] = spy
positive = [[torch.randn(1, 5, 32), {}]]
negative = [[torch.zeros(1, 5, 32), {}]]
noise = comfy.sample.prepare_noise(grafted["samples"], 1)
samples = comfy.sample.sample(locked, noise, 6, 1.0, "euler", "simple", positive, negative,
                              grafted["samples"], denoise=1.0,
                              noise_mask=grafted["noise_mask"], seed=1)
video = samples.unbind()[0]

check("the sampled video keeps the shot's own length", tuple(video.shape), (1, C, T, H, W))
check("...and is finite", bool(torch.isfinite(video).all()), True)
check("the capstone joins from the lock step, one video step longer",
      seen, [T, T, T, T + 1, T + 1, T + 1])
check("the keystone held in latent 0 through sampling",
      torch.allclose(video[:, :, 0], first[:, :, 0], atol=1e-4), True)
restored = ks.restore({"samples": samples}, grafted)["samples"].unbind()[0]
check("after the restore latent 0 is the shot's own again",
      torch.equal(restored[:, :, 0], run[:, :, 0]), True)
check("...and the run context noise touched is the run",
      torch.equal(restored[:, :, 1:6], run[:, :, 1:6]), True)
check("...through the join, which was held outright",
      torch.allclose(restored[:, :, 6], run[:, :, 6], atol=1e-5), True)
