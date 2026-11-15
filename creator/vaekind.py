"""Which VAE is this file — and is it the one the family decodes with?

Every family in this pack decodes through exactly one VAE, and the picker
lists every file in `models/vae`, so the Flux 2 VAE sits one row from the Qwen
image VAE and nothing about either filename says which model it belongs to.
Pick the wrong one and the render samples the whole clip before core's decode
raises `The size of tensor a (16) must match the size of tensor b (128)` —
issue #94, from a user who could not have known which of the two rows was
theirs. The sentence they should have read is "this file is the Flux 2 VAE,
and Krea 2 decodes with the Qwen image VAE", and it should have come before
sampling rather than after.

The identification is core's own. `comfy/sd.py` picks a VAE's architecture off
which tensor names are in its state dict, and each `KINDS` entry here is that
same test read off the safetensors header — so a file this module calls the
Flux 2 VAE is a file core will load as one. Nothing here opens a tensor: the
header is a JSON blob at the front of the file (`visionweights.safetensors_header`),
and shapes are in it, which is how a 4-channel SD VAE and a 16-channel Flux 1
VAE are told apart when both are spelled `decoder.conv_in.weight`.

The answer is `None` for a file the table does not know — an unreadable
container, a VAE no family here loads — and `None` is *not* a refusal, for the
reason `visionweights` gives: the loader downstream gets to complain about a
file we could not read, and grounding a render over a header this table has
not learned would be a worse bug than the one it fixes. Only a file this module
positively recognises as the wrong one is refused.

`tests/test_vaekind.py` builds the headers and runs this standalone.
"""

import os
import struct
from dataclasses import dataclass
from typing import Callable

from . import visionweights


@dataclass(frozen=True)
class Kind:
    id: str
    label: str                      # what a sentence calls it
    test: Callable[[dict], bool]    # core's own detection, over the header


def _channels(header, key):
    """The input channel count of a conv weight — index 1 of its shape — or
    None when the key is absent or the shape is not one."""
    shape = header.get(key, {}).get("shape")
    if not isinstance(shape, list) or len(shape) < 2:
        return None
    return shape[1]


def _time_kernel(header, key):
    """The temporal extent of a 3D conv weight — index 2 of a 5-long shape —
    or None when the key is absent or the weight is not a 3D conv."""
    shape = header.get(key, {}).get("shape")
    if not isinstance(shape, list) or len(shape) != 5:
        return None
    return shape[2]


# Ordered: an entry's test may assume the ones above it said no, the way core's
# `elif` chain does. The keys are quoted from `comfy/sd.py`'s VAE branches.
KINDS = (
    # The H3 encoder with a single-frame decoder: `sd.py` tells it by a 768-row
    # `decoder.proj_out` and, for MiniMax H3 Image as against p-h3-image, a
    # 1024-wide `decoder.x_embedder`. First, because it carries the video
    # VAE's `transformer_blocks` and encoder too and `h3_video` would claim it;
    # the video decoder's `proj_out` is 3072 rows (four frames per token).
    Kind("h3_image", "the MiniMax H3 Image VAE",
         lambda h: (h.get("decoder.proj_out.weight", {}).get("shape") or [0])[0] == 768
         and (h.get("decoder.x_embedder.weight", {}).get("shape") or [0])[0] == 1024),
    Kind("h3_video", "the MiniMax H3 video VAE",
         lambda h: "decoder.transformer_blocks.0.scale1" in h
         and "encoder.down.5.block.0.conv1.weight" in h),
    Kind("h3_audio", "the MiniMax H3 audio VAE",
         lambda h: "pre_block.attn.zero_k_bias" in h),
    # LTX's video VAE ships as two decoders — the plain diffusion one (2.4's
    # `conv_in_x_t`) and the '-conv-' one (the original ltxv layout) — and both
    # are the same 128-channel latent space, so one kind covers the pair.
    Kind("ltx_video", "the LTX video VAE",
         lambda h: "decoder.conv_in_x_t.weight" in h
         or "decoder.up_blocks.0.res_blocks.0.conv1.conv.weight" in h),
    Kind("ltx_audio", "the LTX audio VAE",
         lambda h: "vocoder.resblocks.0.convs1.0.weight" in h
         or "vocoder.vocoder.resblocks.0.convs1.0.weight" in h),
    # The Wan layout, three ways. 2.1's 16 channels are Qwen Image's VAE; 2.2's
    # 48 are not; and Qwen Image 2.1's VAE is the 2.2 layout with a temporal
    # kernel of 1 — core's own tell is the head conv's time axis (`sd.py`:
    # `head.ndim == 5 and head.shape[2] == 1`), and it is read the same way
    # off the header, before the 2.2 test that would otherwise claim it.
    Kind("qwen_image21", "the Qwen Image 2.1 VAE",
         lambda h: "decoder.upsamples.0.upsamples.0.residual.2.weight" in h
         and _time_kernel(h, "decoder.head.2.weight") == 1),
    Kind("wan22", "the Wan 2.2 VAE",
         lambda h: "decoder.middle.0.residual.0.gamma" in h
         and "decoder.upsamples.0.upsamples.0.residual.2.weight" in h),
    Kind("qwen_image", "the Qwen image VAE",
         lambda h: "decoder.middle.0.residual.0.gamma" in h),
    # The batch-normed, pixel-shuffled latent: 32 channels in the file, 128
    # once core unshuffles it — the `128` in issue #94's error.
    Kind("flux2", "the Flux 2 VAE",
         lambda h: "bn.running_mean" in h and "decoder.conv_in.weight" in h),
    # The plain AutoencoderKL layout, told apart by width alone.
    Kind("sd", "an SD 1.x / SDXL VAE",
         lambda h: _channels(h, "decoder.conv_in.weight") == 4),
    Kind("flux1", "a Flux 1 / SD3 VAE",
         lambda h: _channels(h, "decoder.conv_in.weight") == 16),
)

LABEL = {kind.id: kind.label for kind in KINDS}


def identify(path):
    """The kind id of the VAE at `path`, or None when the file did not say."""
    if not path or not os.path.isfile(path):
        return None
    if os.path.splitext(path)[1].lower() not in (".safetensors", ".sft"):
        return None
    try:
        header = visionweights.safetensors_header(path)
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return None
    if not header:
        return None
    for kind in KINDS:
        if kind.test(header):
            return kind.id
    return None


def check(path, wanted, filename):
    """Raise if the file at `path` is positively some other VAE than `wanted`.

    `filename` is what the picker showed, which is the name the user will go
    looking for; the sentence names both files so the right row is findable
    from the wrong one.
    """
    found = identify(path)
    if found is None or found == wanted:
        return
    raise ValueError(
        f"{filename} is {LABEL[found]}. This family decodes with "
        f"{LABEL[wanted]} — pick that one from models/vae."
    )
