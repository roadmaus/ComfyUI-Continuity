"""A trained upscaler for the H3 video latent, as the refine pass's alternative
to bicubic.

The refine pass (`hires.py`) interpolates the first pass's picture up to the
target canvas and re-samples it partway down the schedule. Bicubic across a
24-channel latent whose every cell is a 16x16 patch does not draw a bigger
picture, it draws a blurred one, and the second pass has to invent every
detail from there. LBH-123-AI trained a network to do the drawing instead —
<https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler>, Apache-2.0 on
the model card, ~80k low/high-res latent pairs at 1x–4x — and this is that
network, rewritten here so the refine pass can call it on the video half of
the AV latent without a second install. Discussion #85 is where it was asked
for; the question it has to answer on the lab is whether the second pass gets
a better start from it than from bicubic, and whether that better start lets
the refine run at a lower denoise and fewer steps.

**The architecture**, read off the checkpoint rather than configured: Ttl's
NNLatentUpscale shape — `conv_in`, a stack of ResBlocks modulated by an
embedding of the scale, a trilinear resize of the *features* to the target,
a second stack, `conv_out` — with a depthwise temporal conv after every second
block. Attention blocks exist upstream and are never on; they are not here.
The scale embedding is what lets one file serve any factor in 1x–4x, which
matters because this pack's factor is whatever the target is over the
first-pass edge (768 -> 1080 is 1.41x), not a fixed 2.

**Normalization** is upstream's per-channel mean/std of the H3 latent; the
network sees and returns standardized values.

**Temporal chunking** runs the network over windows of 32 latent frames with a
replicate-padded halo the width of the temporal kernel and a linear blend over
the halo. Upstream's fix for its own end-of-clip flicker; kept, because a
15-second card is past the window.

**VRAM.** The weights ride in a `ModelPatcher` so ComfyUI's manager makes room
for them beside the DiT that is about to sample, and offloads them the same
way. The plain patcher, deliberately: under `--fast` dynamic VRAM the plain
`nn.Conv3d` modules here are not the lazily-cast ops core's own models are
built from, and Tr1dae measured that path collapsing the residual to a
bilinear.
"""

import torch
import torch.nn.functional as F
from torch import nn

import comfy.model_management
import comfy.model_patcher
import comfy.utils
import folder_paths

FOLDER = "latent_upscale_models"

# Upstream's H3 latent statistics, per channel.
MEAN = [
    0.858090341091156, -0.9606591463088989, 1.0661640167236328, -0.5090325474739075,
    -0.2727581858634949, -1.3675414323806763, -0.2553254961967468, -0.26907554268836975,
    -0.5376840829849243, -0.0464097298681736, 0.6657370328903198, 0.19690127670764923,
    -0.5460608005523682, -0.4035342037677765, -0.23683024942874908, 0.25928452610969543,
    -0.30133944749832153, 0.211341992020607, -1.1206848621368408, 0.3581933379173279,
    -0.04225143790245056, 0.2604829967021942, 0.22864092886447906, 0.7056031823158264,
]
STD = [
    1.2223774194717407, 1.2767263650894165, 1.6831774711608887, 1.7549455165863037,
    1.5636216402053833, 2.194143533706665, 0.9653137922286987, 1.0569885969161987,
    0.841948926448822, 0.7729952931404114, 1.8955937623977661, 0.946841835975647,
    0.7996809482574463, 0.44988900423049927, 0.7197399735450745, 0.6936293244361877,
    2.961095094680786, 2.7694199085235596, 3.0496184825897217, 2.1088054180145264,
    3.276226282119751, 3.1627357006073, 2.2816812992095947, 2.6127843856811523,
]

# Latent frames per window, and the blocks a temporal conv follows.
CHUNK = 32
TEMPORAL_EVERY = 2
EMBED = 64


def _norm(channels):
    return nn.GroupNorm(32, channels)


class ResBlock(nn.Module):
    """A ResBlock whose second norm is modulated by the scale embedding."""

    def __init__(self, channels, dropout):
        super().__init__()
        self.in_layers = nn.Sequential(
            _norm(channels), nn.SiLU(), nn.Conv3d(channels, channels, 3, padding=1))
        self.emb_layers = nn.Sequential(nn.SiLU(), nn.Linear(EMBED, 2 * channels))
        self.out_norm = _norm(channels)
        self.out_layers = nn.Sequential(
            nn.SiLU(), nn.Dropout(p=dropout), nn.Conv3d(channels, channels, 3, padding=1))
        self.skip = nn.Identity()

    def forward(self, x, emb):
        h = self.in_layers(x)
        scale, shift = torch.chunk(
            self.emb_layers(emb).type(h.dtype)[:, :, None, None, None], 2, dim=1)
        h = self.out_norm(h) * (1 + scale) + shift
        return self.skip(x) + self.out_layers(h)


class TemporalConv(nn.Module):
    """Depthwise conv along time, pointwise mix, residual."""

    def __init__(self, channels, kernel):
        super().__init__()
        self.norm = _norm(channels)
        self.dwconv = nn.Conv3d(channels, channels, kernel_size=(kernel, 1, 1),
                                padding=(kernel // 2, 0, 0), groups=channels)
        self.pwconv = nn.Conv3d(channels, channels, kernel_size=1)

    def forward(self, x):
        return x + self.pwconv(self.dwconv(F.silu(self.norm(x))))


class LatentResizer3D(nn.Module):
    def __init__(self, in_channels, in_blocks, out_blocks, channels, temporal_kernel,
                 dropout=0.1):
        super().__init__()
        self.temporal_kernel = temporal_kernel
        self.conv_in = nn.Conv3d(in_channels, channels, 3, padding=1)
        self.embed = nn.Sequential(nn.Linear(1, EMBED), nn.SiLU(), nn.Linear(EMBED, EMBED))
        self.in_blocks = self._stack(in_blocks, channels, temporal_kernel, dropout)
        self.out_blocks = self._stack(out_blocks, channels, temporal_kernel, dropout)
        self.norm_out = _norm(channels)
        self.conv_out = nn.Conv3d(channels, in_channels, 3, padding=1)

    @staticmethod
    def _stack(count, channels, kernel, dropout):
        blocks = nn.ModuleList()
        for index in range(count):
            blocks.append(ResBlock(channels, dropout))
            if index % TEMPORAL_EVERY == 0:
                blocks.append(TemporalConv(channels, kernel))
        return blocks

    @staticmethod
    def _run(blocks, x, emb):
        for block in blocks:
            x = block(x, emb) if isinstance(block, ResBlock) else block(x)
        return x

    def _segment(self, x, scale, size):
        # The embedding is of `scale - 1`, so 1x is the zero vector.
        emb = self.embed(torch.tensor([[scale - 1.0]], dtype=x.dtype, device=x.device))
        emb = emb.expand(x.shape[0], -1)
        x = self._run(self.in_blocks, self.conv_in(x), emb)
        x = F.interpolate(x, size=size, mode="trilinear", align_corners=False)
        x = self._run(self.out_blocks, x, emb)
        return self.conv_out(F.silu(self.norm_out(x)))

    def forward(self, x, scale, height, width):
        """[B,C,T,H,W] standardized -> [B,C,T,height,width] standardized."""
        frames = x.shape[2]
        if frames <= CHUNK:
            return self._segment(x, scale, (frames, height, width))

        halo = self.temporal_kernel
        padded = F.pad(x, (0, 0, 0, 0, halo, halo), mode="replicate")
        out = torch.zeros(*x.shape[:3], height, width, device=x.device, dtype=x.dtype)
        weight = torch.zeros(1, 1, frames, 1, 1, device=x.device, dtype=x.dtype)
        for start in range(0, frames, CHUNK):
            end = min(frames, start + CHUNK)
            # The window with its halo on either side, in padded coordinates,
            # then the halo's own halo so the temporal convs see real frames.
            lo, hi = max(0, start - halo), min(frames, end + halo)
            seg = padded[:, :, lo:hi + 2 * halo]
            seg_out = self._segment(seg, scale, (seg.shape[2], height, width))
            seg_out = seg_out[:, :, halo:halo + (hi - lo)]
            ramp = torch.ones(hi - lo, device=x.device, dtype=x.dtype)
            if start > lo:
                n = start - lo
                ramp[:n] = torch.arange(1, n + 1, device=x.device, dtype=x.dtype) / (n + 1)
            if hi > end:
                n = hi - end
                ramp[-n:] = torch.arange(n, 0, -1, device=x.device, dtype=x.dtype) / (n + 1)
            ramp = ramp.view(1, 1, -1, 1, 1)
            out[:, :, lo:hi] += seg_out * ramp
            weight[:, :, lo:hi] += ramp
        return out / weight


_LOADED = {}


def _build(sd):
    """The network the checkpoint describes."""
    conv_in = sd["conv_in.weight"]
    in_blocks = len({k.split(".")[1] for k in sd if k.startswith("in_blocks.") and ".in_layers." in k})
    out_blocks = len({k.split(".")[1] for k in sd if k.startswith("out_blocks.") and ".in_layers." in k})
    kernels = [v.shape[2] for k, v in sd.items() if k.endswith("dwconv.weight")]
    if not kernels:
        raise ValueError("this latent upscaler has no temporal convs; this pack runs the 3D one")
    if any("attn" in k or k.endswith(".q.weight") for k in sd):
        raise ValueError("this latent upscaler has attention blocks, which this pack does not run")
    return LatentResizer3D(conv_in.shape[1], in_blocks, out_blocks, conv_in.shape[0], kernels[0])


def _checkpoint_dtype(sd):
    # Only a uniformly half-precision file opts into half computation. Mixed
    # files retain the old FP32 road, so a full-precision layer is never silently
    # downcast just because conv_in happened to be half. Integer buffers do not
    # select a floating-point computation dtype.
    dtypes = {value.dtype for value in sd.values()
              if isinstance(value, torch.Tensor) and value.is_floating_point()}
    if dtypes == {torch.float16}:
        return torch.float16
    if dtypes == {torch.bfloat16}:
        return torch.bfloat16
    return torch.float32


def load(name):
    """The upscaler `name` (a file under models/latent_upscale_models), as a patcher."""
    if name in _LOADED:
        return _LOADED[name]
    path = folder_paths.get_full_path_or_raise(FOLDER, name)
    sd = comfy.utils.load_torch_file(path, safe_load=True)
    if "model" in sd and isinstance(sd["model"], dict):
        sd = sd["model"]
    sd = {k[len("upscaler."):] if k.startswith("upscaler.") else k: v for k, v in sd.items()}
    # load_state_dict copies into the destination's dtype; a freshly built
    # nn.Module is FP32 even when the file is FP16/BF16. Select the checkpoint's
    # precision before copying so the published half files stay half in memory
    # and during the forward. An explicit FP32 checkpoint remains FP32.
    model = _build(sd).to(dtype=_checkpoint_dtype(sd))
    model.load_state_dict(sd, strict=True)
    model.eval().requires_grad_(False)
    patcher = comfy.model_patcher.ModelPatcher(
        model, load_device=comfy.model_management.get_torch_device(),
        offload_device=comfy.model_management.unet_offload_device())
    _LOADED[name] = patcher
    return patcher


def upscale(video, width, height, name):
    """The video half, drawn up to the target canvas by the trained net.

    [B,C,T,H,W] in and out, like the bicubic path. The scale the embedding is
    told is the mean of the two axes' factors, as upstream does for a target
    given in pixels.
    """
    patcher = load(name)
    model = patcher.model
    h_out, w_out = height // 16, width // 16
    scale = (w_out / video.shape[-1] + h_out / video.shape[-2]) / 2
    if scale < 1.0:
        raise ValueError("the latent upscaler only draws up: the refine target is "
                         "under the first pass's canvas")
    dtype = next(model.parameters()).dtype
    # Room for the weights and the widest feature map the stack holds: 512
    # channels at the target size, a few of them alive at once.
    activations = 6 * video.shape[0] * 512 * min(video.shape[2], CHUNK + 2 * model.temporal_kernel) \
        * h_out * w_out * torch.tensor([], dtype=dtype).element_size()
    comfy.model_management.load_models_gpu([patcher], memory_required=activations)
    device = patcher.load_device
    mean = torch.tensor(MEAN, dtype=dtype, device=device).view(1, -1, 1, 1, 1)
    std = torch.tensor(STD, dtype=dtype, device=device).view(1, -1, 1, 1, 1)
    with torch.inference_mode():
        x = (video.to(device=device, dtype=dtype) - mean) / std
        out = model(x, scale, h_out, w_out) * std + mean
    return out.to(device=video.device, dtype=video.dtype)
