"""The masked seam road: the inherited run becomes the target latent's head.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_masked_seam.py

CPU tensors through the real encoder helpers; no model, no VAE, no sampler.
What this checks is the contract the sampler reads: the run is the first steps
of the video stream, the mask is 0 over exactly those steps and 1 elsewhere,
the audio stream and its mask are untouched, and the head seam pins no guides
for a run that is already in the latent.
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
sys.argv = ["test_masked_seam", "--cpu"]
import comfy.cli_args  # noqa: E402
comfy.cli_args.args.cpu = True
import torch  # noqa: E402
import comfy.nested_tensor  # noqa: E402

encoder = layout.load("encode", package="masked_seam_contract").encode

# A 22-frame feather is 7 latent steps; a 39-frame target is 12.
run = torch.randn(1, 24, 7, 30, 42)
video = torch.zeros(1, 24, 12, 30, 42)
audio = torch.randn(1, 32, 2, 65)
latent = {"samples": comfy.nested_tensor.NestedTensor((video, audio))}

out = encoder._masked_prefix(latent, run)
v, a = out["samples"].unbind()
vm, am = out["noise_mask"].unbind()
check("the run is the target's first steps", torch.equal(v[:, :, :7], run), True)
check("...and the rest is still the empty target", float(v[:, :, 7:].abs().sum()), 0.0)
check("the mask holds exactly those steps", (float(vm[:, :, :7].sum()), float(vm[:, :, 7:].min())),
      (0.0, 1.0))
check("the mask is the video's own shape", tuple(vm.shape), tuple(video.shape))
check("the audio stream is untouched", torch.equal(a, audio), True)
check("...and its mask is ones", (tuple(am.shape), float(am.min())), (tuple(audio.shape), 1.0))
check("the source latent is not written to", float(video.abs().sum()), 0.0)

# A sound lane's mask already on the latent survives on the audio half.
lane_mask = torch.ones_like(audio)
lane_mask[..., :10] = 0.0
laned = {**latent, "noise_mask": comfy.nested_tensor.NestedTensor((torch.ones_like(video), lane_mask))}
_, am2 = encoder._masked_prefix(laned, run)["noise_mask"].unbind()
check("a sound lane's audio mask rides through", torch.equal(am2, lane_mask), True)

# The head seam pins nothing when the run is in the latent already.
loaded = {encoder.MASKED_RUN: {"latent": run},
          encoder.PREV_LATENT: {"latent": torch.randn(1, 24, 12, 30, 42)}}
class _Compiled:
    feather, width, height = 22, 672, 480
check("no guides are pinned for a masked run",
      encoder._inherited_run(None, _Compiled, loaded, None), [])

# The slice itself, at the target's canvas and off it.
source = torch.randn(1, 24, 12, 30, 42)
sliced = encoder._context_run(source, 22, 672, 480)
check("the run is the source's last seven steps", torch.equal(sliced, source[:, :, -7:]), True)
check("another canvas hands back nothing", encoder._context_run(source, 22, 640, 480), None)

# A run that would be the whole shot is refused, not written.
try:
    encoder._masked_prefix({"samples": comfy.nested_tensor.NestedTensor(
        (torch.zeros(1, 24, 7, 30, 42), audio))}, run)
    refused = False
except ValueError:
    refused = True
check("a run as long as the target is refused", refused, True)
