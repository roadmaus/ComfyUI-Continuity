"""The refine pass redraws the picture and hands the soundtrack back untouched.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_hires_audio.py

Issue #33 was a two-pass render coming back with a sharp picture and static for
sound, on generated and supplied audio alike. The graph was right the whole
time — `tests/golden/refine_two_pass.json` pins that the node is wired at the
target canvas with the denoise the blob asked for, and it stayed green — so what
has to be held is what the node hands the *sampler*: the mask that keeps the
audio out of the denoise, and the audio latent itself, unscaled.

Nothing is sampled. `comfy.sample.sample` is replaced with a recorder, because
the four arguments this suite is about are all decided before the first step.

Skips itself with a message if ComfyUI cannot be imported.
"""

import os
import sys

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    import torch

    import layout
    hires = layout.load("hires").hires
    import comfy.nested_tensor
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

from harness import FAILURES, check, passed

# The first pass's canvas and the target: a 512x288 sample refined up to
# 768x432, which is the shape of a real two-pass render and not just of a pair
# of numbers — 288 and 432 both land on the /16 latent grid.
FIRST = (512, 288)
TARGET = (768, 432)

VIDEO = torch.linspace(-1, 1, 24 * 2 * 18 * 32).reshape(1, 24, 2, 18, 32)
# The audio half's shape has nothing to do with the canvas: [B, 32, 2, T40].
AUDIO = torch.linspace(-3, 3, 32 * 2 * 40).reshape(1, 32, 2, 40)


def refine(latent, denoise=0.5):
    """Run the node with the sampler recorded rather than run. -> (out, call)."""
    call = {}

    def recorder(model, noise, steps, cfg, sampler_name, scheduler,
                 positive, negative, latent_image, denoise=1.0,
                 noise_mask=None, seed=None, callback=None, disable_pbar=False,
                 **rest):
        call.update(noise=noise, latent=latent_image, mask=noise_mask,
                    denoise=denoise, seed=seed, steps=steps)
        return latent_image

    was_sample = hires.comfy.sample.sample
    was_callback = hires.latent_preview.prepare_callback
    hires.comfy.sample.sample = recorder
    hires.latent_preview.prepare_callback = lambda model, steps: None
    try:
        out = hires.MiniMaxH3RefinePass.execute(
            model=None, positive=[], negative=[], latent=latent,
            width=TARGET[0], height=TARGET[1], seed=42, steps=20, cfg=1.0,
            sampler_name="res_multistep", scheduler="simple", denoise=denoise)
    finally:
        hires.comfy.sample.sample = was_sample
        hires.latent_preview.prepare_callback = was_callback
    return out.result[0], call


LATENT = {"samples": comfy.nested_tensor.NestedTensor((VIDEO, AUDIO)),
          "batch_index": [0],
          # A supplied-sound mask from the first pass, at the first pass's
          # canvas. It says nothing about this latent and must not survive.
          "noise_mask": comfy.nested_tensor.NestedTensor(
              (torch.ones_like(VIDEO), torch.zeros_like(AUDIO)))}

out, call = refine(LATENT)
noise_video, noise_audio = call["noise"].unbind()
sent_video, sent_audio = call["latent"].unbind()

# The bug. Without a mask the model is told the sound is as noisy as the
# picture, predicts a velocity for a stream that has none, and applies it for
# the whole refine — so the mask is not decoration, it is the fix. Reported
# rather than unbound blind, because the shape this regressed to was `None`.
mask = call["mask"]
check("a mask is handed over", getattr(mask, "is_nested", False), True)
if getattr(mask, "is_nested", False):
    mask_video, mask_audio = mask.unbind()
else:
    mask_video = mask_audio = torch.zeros(0)
check("picture is redrawn", bool(mask_video.numel()) and bool(mask_video.eq(1).all()), True)
check("sound is held", bool(mask_audio.numel()) and bool(mask_audio.eq(0).all()), True)
check("mask video shape", tuple(mask_video.shape), (1, 24, 2, 27, 48))
check("mask audio shape", tuple(mask_audio.shape), tuple(AUDIO.shape))

# The other half of #33: the audio used to be pre-divided by (1 - sigma) on the
# way in, which was 1.6x hot at denoise 0.5. It goes in exactly as it came out
# of the first pass, and the scale is core's business through the mask.
check("audio handed over unscaled", bool(torch.equal(sent_audio, AUDIO)), True)
check("audio not noised", bool(noise_audio.eq(0).all()), True)
check("picture is noised", bool(noise_video.abs().sum() > 0), True)

check("video upscaled", tuple(sent_video.shape), (1, 24, 2, 27, 48))
check("noise matches the picture", tuple(noise_video.shape), (1, 24, 2, 27, 48))
check("denoise passed through", call["denoise"], 0.5)

# The first pass's mask is at the first pass's canvas; carried through, it would
# be handed to whatever samples next as if it described this latent.
check("stale mask dropped", "noise_mask" in out, False)
check("rest of the latent carried", out.get("batch_index"), [0])
check("refined samples returned", tuple(out["samples"].unbind()[0].shape),
      (1, 24, 2, 27, 48))

# A plain latent is a wiring mistake, not something to sample anyway.
try:
    refine({"samples": VIDEO})
    FAILURES.append("a non-nested latent was accepted")
except ValueError:
    pass

passed("all refine-pass audio tests passed")
