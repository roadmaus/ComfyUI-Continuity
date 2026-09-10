"""Decode a thumbnail for RefMods that have none. Maintenance, run by hand.

`server_routes._refmod_thumb` only ever *serves* a thumbnail that already exists:
the preview embedded when Save as RefMod wrote the file, or the sidecar a render
writes the first time it decodes the mod for the tokenizer. It must not decode —
that runs on a thread-pool worker, and ComfyUI's model management is not
thread-safe off the render thread, which is exactly how a route that tried it
segfaulted the process.

So a mod made by the sibling pack, before Save as RefMod embedded previews, has
no picture until a render touches it. This is the one-off backfill for those:

    COMFYUI_PATH=~/ComfyUI ~/ComfyUI/.venv/bin/python3 -m creator.refmod_thumbs

Idempotent: every mod that already has a preview or a sidecar is skipped, and
each of the rest gets one `models/refmods/.thumbs/<name>.png` — the same file a
render would have written.
"""

from __future__ import annotations

import io
import os
import sys

# A mod records no VAE of its own (its latent is the mod's, whatever encoded
# it), so the decode borrows one. The needles are this pack's own file names.
VAE_NEEDLES = ("minimax_h3_video_vae", "h3_video_vae", "minimax_h3", "video_vae")


def _comfy_path():
    return os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))


def _h3_vae_name(folder_paths):
    try:
        names = folder_paths.get_filename_list("vae")
    except Exception:  # noqa: BLE001
        return None
    for needle in VAE_NEEDLES:
        for name in names:
            if needle in name.lower():
                return name
    return None


def _png(latent, vae, torch, Image):
    """The mod's first latent frame -> small PNG bytes."""
    with torch.no_grad():
        pixels = vae.decode(latent[:, :, :1])
    if pixels.ndim == 5 and pixels.shape[0] == 1:
        pixels = pixels[0]
    if pixels.ndim != 4 or pixels.shape[0] < 1:
        raise ValueError(f"decoded to {tuple(pixels.shape)}, expected [T, H, W, C]")
    frame = pixels[0].detach().float().clamp(0, 1).cpu().numpy()
    image = Image.fromarray((frame * 255).round().astype("uint8"))
    image.thumbnail((192, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main(argv=None):
    sys.path.insert(0, _comfy_path())
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import folder_paths
    import nodes
    import torch
    from PIL import Image
    from creator import refmod
    # The extra model roots live in `extra_model_paths.yaml`, which ComfyUI's own
    # `main.py` loads and a standalone process does not. Without it the H3 VAE —
    # under a mapped root like `/models/vision/vae` — is invisible.
    from utils import extra_config
    config = os.path.join(_comfy_path(), "extra_model_paths.yaml")
    if os.path.isfile(config):
        extra_config.load_extra_path_config(config)

    pending = [name for name in refmod.list_names()
               if refmod.read_preview(name) is None and refmod.read_thumb(name) is None]
    if not pending:
        print("refmods: every mod already has a thumbnail.")
        return 0

    vae_name = _h3_vae_name(folder_paths)
    if not vae_name:
        print("refmods: no H3 video VAE found under models/vae.", file=sys.stderr)
        return 1
    print(f"refmods: {len(pending)} to do, decoding with {vae_name}")
    vae = nodes.VAELoader().load_vae(vae_name)[0]
    failed = 0
    for name in pending:
        try:
            refmod.write_thumb(name, _png(refmod.load_latent(name), vae, torch, Image))
            print(f"  {name}: wrote a thumbnail")
        except Exception as exc:  # noqa: BLE001 — one bad mod must not stop the rest
            failed += 1
            print(f"  {name}: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 1 if failed == len(pending) else 0


if __name__ == "__main__":
    raise SystemExit(main())
