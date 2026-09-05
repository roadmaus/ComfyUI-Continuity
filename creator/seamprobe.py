"""TEMPORARY: measures what the VAE round trip does to the run a seam inherits.

Issue #46 section 5 proposes handing the next pass the sampler's own latent
tail instead of `vae.encode(decode(latent)[-feather:])`. Whether that is worth
building depends on one number nobody has measured on H3: how far the
re-encoded tail sits from the latent it was decoded from, and in which
direction the error points (softer? harder in contrast? a channel offset?).
Issue #41's drift compounds down a strip, so a small *directional* bias here
matters more than a large unbiased one.

Set `CONTINUITY_SEAM_PROBE=1` (or a run width on the 17m+5 grid, e.g. `22`)
and every pass the reel decodes prints, to the console:

  1. latent slice vs re-encode  — the pin the seam sends today against the pin
     a latent handoff would send, as a relative L2 error, per-step, plus the
     channel mean/std shift between them;
  2. pixel round trip           — decode(encode(tail)) against the tail itself:
     PSNR, luma shift, contrast ratio, high-frequency energy ratio;
  3. three iterated round trips — the same numbers after encode∘decode is
     applied again and again, to show whether the VAE alone walks in one
     direction or merely blurs once.

Nothing is changed in the render; a failing probe logs and the pass is written
as it always was. Delete this module and its call in `timeline.py` once the
question is answered.
"""

import math
import os
import sys

import torch

ENV = "CONTINUITY_SEAM_PROBE"
TAG = "[continuity seam probe]"


def enabled():
    return bool(os.environ.get(ENV, "").strip())


def _width(default=22):
    raw = os.environ.get(ENV, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 1 else default


def _say(line=""):
    print(f"{TAG} {line}", file=sys.stderr, flush=True)


def _luma(px):
    """[T,H,W,C] in 0..1 -> [T,H,W] Rec.709 luma."""
    px = px[..., :3].float()
    return 0.2126 * px[..., 0] + 0.7152 * px[..., 1] + 0.0722 * px[..., 2]


def _hf_energy(px):
    """Mean absolute 4-neighbour Laplacian of the luma — a texture proxy."""
    y = _luma(px)
    lap = (4 * y[:, 1:-1, 1:-1] - y[:, :-2, 1:-1] - y[:, 2:, 1:-1]
           - y[:, 1:-1, :-2] - y[:, 1:-1, 2:])
    return float(lap.abs().mean())


def _pixel_stats(ref, got):
    mse = float(((ref[..., :3].float() - got[..., :3].float()) ** 2).mean())
    psnr = 10 * math.log10(1.0 / mse) if mse > 0 else float("inf")
    y_ref, y_got = _luma(ref), _luma(got)
    return {
        "psnr_db": psnr,
        "luma_shift": float(y_got.mean() - y_ref.mean()),
        "contrast_ratio": float(y_got.std() / max(float(y_ref.std()), 1e-8)),
        "hf_ratio": _hf_energy(got) / max(_hf_energy(ref), 1e-12),
    }


def _fmt_px(s):
    return (f"psnr {s['psnr_db']:6.2f} dB  luma shift {s['luma_shift']*255:+6.2f}/255  "
            f"contrast x{s['contrast_ratio']:.4f}  high-freq x{s['hf_ratio']:.4f}")


def _to_video_latent(encoded):
    """Whatever `vae.encode` returned -> [1,C,T,h,w]."""
    if getattr(encoded, "is_nested", False):
        encoded = encoded.unbind()[0]
    if encoded.ndim == 4:                       # [T,C,h,w] -> [1,C,T,h,w]
        encoded = encoded.unsqueeze(0).movedim(1, 2)
    return encoded.float()


def _latent_stats(z_ref, z_got):
    """Both [1,C,T,h,w]. Relative error overall and per temporal step."""
    diff = z_got - z_ref
    rel = float(diff.norm() / max(float(z_ref.norm()), 1e-8))
    per_step = [float(diff[:, :, t].norm() / max(float(z_ref[:, :, t].norm()), 1e-8))
                for t in range(z_ref.shape[2])]
    mean_shift = float((z_got.mean(dim=(0, 2, 3, 4)) - z_ref.mean(dim=(0, 2, 3, 4))).abs().mean())
    std_ratio = float(z_got.std() / max(float(z_ref.std()), 1e-8))
    # Cosine between the two pins, flattened: 1.0 is the same direction.
    cos = float(torch.nn.functional.cosine_similarity(
        z_ref.flatten(), z_got.flatten(), dim=0))
    return rel, per_step, mean_shift, std_ratio, cos


def run(samples, vae, images):
    """Print the probe for one pass. `images` is the untrimmed decode, [T,H,W,C]."""
    try:
        _run(samples, vae, images)
    except Exception as exc:  # a probe must never cost the render
        _say(f"probe failed, pass unaffected: {type(exc).__name__}: {exc}")


def _run(samples, vae, images):
    from .families.h3.encode import _frames_covered

    width = _width()
    latent = samples["samples"]
    z = latent.unbind()[0] if getattr(latent, "is_nested", False) else latent
    z = z.float()
    if z.ndim != 5:
        _say(f"latent is {tuple(z.shape)}, not [B,C,T,h,w]; skipping")
        return
    total_steps = int(z.shape[2])
    steps = next((s for s in range(1, total_steps + 1) if _frames_covered(s) == width), None)
    if steps is None or _frames_covered(total_steps) != int(images.shape[0]):
        _say(f"width {width} is not on the grid, or the {images.shape[0]}-frame decode does "
             f"not match {total_steps} latent steps; skipping")
        return

    tail_px = images[-width:].contiguous()
    z_tail = z[:, :, -steps:].contiguous()

    _say(f"pass: {images.shape[0]} frames / {total_steps} latent steps at "
         f"{images.shape[2]}x{images.shape[1]}; probing the last {width} frames "
         f"({steps} steps)")

    # 1. The pin the seam encodes today, against the latent slice a handoff would send.
    z_enc = _to_video_latent(vae.encode(tail_px[..., :3])).to(z_tail.device)
    if z_enc.shape != z_tail.shape:
        _say(f"re-encode is {tuple(z_enc.shape)} vs slice {tuple(z_tail.shape)}; skipping")
        return
    rel, per_step, mean_shift, std_ratio, cos = _latent_stats(z_tail, z_enc)
    _say("1. re-encoded tail vs sampler latent slice")
    _say(f"   relative L2 error {rel:.4f}   cosine {cos:.5f}   "
         f"channel mean |shift| {mean_shift:.4f}   std ratio x{std_ratio:.4f}")
    _say("   per step: " + "  ".join(f"{e:.3f}" for e in per_step)
         + "   (step 0 covers 1 frame, the rest 4 each)")

    # 2 + 3. Pixel round trips, iterated.
    _say("2. pixel round trip decode(encode(tail)) vs tail, then iterated")
    current = tail_px
    for i in range(1, 4):
        z_i = _to_video_latent(vae.encode(current[..., :3]))
        decoded = vae.decode(z_i)
        if decoded.ndim == 5:                    # [B,T,H,W,C] -> [T,H,W,C]
            decoded = decoded.reshape(-1, *decoded.shape[-3:])
        decoded = decoded[..., :3].clamp(0.0, 1.0).to(tail_px.device)
        if decoded.shape[0] != tail_px.shape[0]:
            _say(f"   round {i}: decode gave {decoded.shape[0]} frames for {tail_px.shape[0]}; stopping")
            return
        _say(f"   round {i} vs original: {_fmt_px(_pixel_stats(tail_px, decoded))}")
        current = decoded
    _say("done")
