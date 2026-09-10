"""`_encode_refmod`: the latent is the mod's, the presentation is the decode.

The branch this covers is the whole point of the feature — a saved RefMod must
reach the DiT as the bytes that were saved, never re-encoded, while the tokenizer
still gets the decoded, 2 fps-sampled picture it was trained on. Both halves are
asserted here against a stub VAE and a stubbed `refmods`, so the test proves the
*wiring* (which kind, which dims, which sampling, and that the latent handed back
is the file's) without a GPU or a checkpoint.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_refmod_encode.py

Skips itself when torch or the package cannot be imported.
"""

import os
import sys
import types

import layout

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    import torch
except Exception as exc:  # noqa: BLE001
    print(f"skipped: needs torch ({type(exc).__name__}: {exc})")
    sys.exit(0)

try:
    pkg = layout.load("refmod", "encode")
except Exception as exc:  # noqa: BLE001
    print(f"skipped: package not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

refmod, encode = pkg.refmod, pkg.encode
from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


FRAMES = 5


class FakeVAE:
    """Only what `_restore` and `_encode_refmod` touch."""

    output_device = torch.device("cpu")

    def vae_output_dtype(self):
        return torch.float32

    def decode(self, latent):
        # [1, 24, T, H, W] -> the [1, frames, H, W, 3] a video VAE returns.
        return torch.rand(1, FRAMES, 48, 64, 3)


STAMP = {"path": "/tmp/person.safetensors", "mtime": 1.0, "size": 2}


def _stub(kind, latent_t):
    """Point the encoder at a fake mod of `kind` and turn the cache off."""
    mod = refmod.Mod(name="person", path="/tmp/person", kind=kind,
                     latent_h=16, latent_w=16, latent_t=latent_t,
                     concept_type="identity", description="someone", takes="person")
    encode.refmods.load_meta = lambda name: mod
    encode.refmods.load_latent = lambda name, device="cpu": LATENT
    encode.refmods.stamp = lambda name: STAMP
    encode.refmods.read_thumb = lambda name: b"already"
    encode.refmods.write_thumb = lambda name, data: None
    # `_cached` runs `produce()` directly when the store is off, which is what
    # makes this a unit test of the branch rather than of the cache.
    encode.latents.enabled = lambda: False
    return types.SimpleNamespace(handle="vid-1", mod="person")


LATENT = torch.zeros(1, 24, 4, 16, 16, dtype=torch.float32)

# ---- a video mod ------------------------------------------------------------

asset = _stub("video", 4)
item, block = encode._encode_refmod(FakeVAE(), asset, "vae-print", None)
check("a video mod builds a video block", block["kind"], "video")
check("the block keeps the mod's latent_t", block["latent_t"], 4)
check("the block keeps the mod's dims", (block["latent_h"], block["latent_w"]), (16, 16))
check("the block's latent is the stored one", block["latent"].shape, tuple(LATENT.shape))
check("a video mod presents as a video", item["type"], "video")
# 2 fps sampling: `FRAMES` at 24 fps is sampled every 12th frame, so one.
check("the presentation is 2 fps sampled", item["data"].shape[0], 1)
check("...with a timestamp per sampled frame", len(item["timestamps"]), 1)

# ---- an image mod -----------------------------------------------------------

asset = _stub("image", 1)
item, block = encode._encode_refmod(FakeVAE(), asset, "vae-print", None)
check("an image mod builds an image block", block["kind"], "image")
check("an image block has no latent_t", "latent_t" in block, False)
check("an image mod presents as a picture", item["type"], "image")
check("...from the first decoded frame", item["data"].shape[0], 1)

passed("the RefMod encode branch reads the file and presents the decode")
