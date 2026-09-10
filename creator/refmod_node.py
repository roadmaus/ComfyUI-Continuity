"""Save a chosen picture or clip as a RefMod.

The Creator's own way to make one of the compressed references its picker and
encoder already read. The node wears a Continuity body (`web/creator/refmod.js`)
that picks the media through the same picker every other attachment uses and
asks the two questions a picture cannot answer for itself — what the reference
is *of* (`type`) and whether to keep the whole picture or only the movement
(`capture`). This half owns everything the user should never have to: where the
file came from, the causal trim, the resolution, the token cost, the format.

The picked media and the two answers ride in the hidden `refmod_data` blob.
The H3 video VAE is chosen there too, from the same model list the Creator's
settings popover reads, and loaded by the node itself — so there are no sockets
at all.
"""

import json

from comfy_api.latest import ComfyExtension, io

from . import media, refmod

# The sibling pack's own words for what a reference is *of*. Kept in step by
# hand rather than imported: the two packs install independently, and
# `refmod.CONCEPT_TAKES` is the mapping that actually matters — a concept type
# this list has never heard of still seeds `full`.
CONCEPT_TYPES = ("generic", "identity", "pose_motion", "clothing", "background",
                 "style")
CAPTURES = ("full", "motion")

_GRID = 32          # canvas multiple, as everywhere else in this pack
_MIN_EDGE = 320     # the VAE's tiled encoder floor; below it the tiler can make a zero tile
_DEFAULT_EDGE = 1024
_MAX_SECONDS = 30   # how much of a clip is decoded; the sibling caps its refs too


def _resize(pixels, short_edge):
    """Aspect-preserving downscale to the short-edge dial, dims snapped to /32."""
    import comfy.utils  # noqa: PLC0415 - ComfyUI is the node's environment.
    height, width = pixels.shape[1], pixels.shape[2]
    scale = min(1.0, short_edge / min(height, width))
    target_w = max(_GRID, round(width * scale / _GRID) * _GRID)
    target_h = max(_GRID, round(height * scale / _GRID) * _GRID)
    samples = pixels[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, target_w, target_h, "lanczos", "disabled")
    return samples.movedim(1, -1), target_h, target_w


def _ensure_min_edge(pixels, floor=_MIN_EDGE):
    """Upscale (never down) so both dims clear the VAE tiler's floor."""
    import comfy.utils  # noqa: PLC0415
    height, width = pixels.shape[1], pixels.shape[2]
    if height >= floor and width >= floor:
        return pixels
    scale = floor / min(height, width)
    target_w = max(floor, round(width * scale / _GRID) * _GRID)
    target_h = max(floor, round(height * scale / _GRID) * _GRID)
    samples = pixels[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, target_w, target_h, "lanczos", "disabled")
    return samples.movedim(1, -1)


def _preview_png(pixels):
    """The first frame as a small PNG, for the picker's cell.

    Written into the mod header at save time, because this is the one moment
    the pixels are already in hand — a grid cell has no VAE to decode a latent
    with, and decoding on every paint is the kind of cost a thumbnail must not
    have.
    """
    import io

    from PIL import Image
    frame = pixels[0].detach().float().clamp(0, 1).cpu().numpy()
    image = Image.fromarray((frame * 255).round().astype("uint8"))
    image.thumbnail((192, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ContinuitySaveRefMod(io.ComfyNode):
    """One picked file -> one saved RefMod in the library."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuitySaveRefMod",
            display_name="Save as RefMod",
            category="Continuity",
            description=(
                "Save a picture or clip as a RefMod for the continuity picker. "
                "Pick the media on the node, choose what the reference is of and "
                "whether to keep the whole picture or only what moves, and Save."
            ),
            is_output_node=True,
            inputs=[
                io.String.Input("refmod_data", multiline=True, default="{}"),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, refmod_data="{}"):
        try:
            blob = json.loads(refmod_data or "{}")
        except ValueError as exc:
            raise ValueError(f"Save as RefMod: the node's data is not valid JSON: {exc}") from exc
        if not isinstance(blob, dict):
            blob = {}
        filename = str(blob.get("filename") or "").strip()
        if not filename:
            raise ValueError("Save as RefMod: choose a picture or clip in the node first.")
        kind = blob.get("kind") if blob.get("kind") in ("image", "video") else "image"
        name = str(blob.get("name") or "").strip() or "my_reference"
        reference_type = blob.get("type") if blob.get("type") in CONCEPT_TYPES else "generic"
        capture = blob.get("capture") if blob.get("capture") in CAPTURES else "full"
        vae_name = str(blob.get("vae") or "").strip()
        if not vae_name:
            raise ValueError(
                "Save as RefMod: choose the H3 video VAE in the node's settings.")
        # Core's own loader, called directly: the node executes rather than
        # emitting a subgraph, so there is no graph in which to place a loader.
        # `load_vae` (the node's FUNCTION), not `load` — and it goes through
        # ComfyUI's model cache, so a second save with the same VAE is free.
        import nodes  # noqa: PLC0415 - ComfyUI is this node's environment.
        vae = nodes.VAELoader().load_vae(vae_name)[0]

        if kind == "video":
            pixels, _audio = media.load_video(filename, max_seconds=_MAX_SECONDS)
        else:
            pixels = media.load_image(filename)
        if pixels.ndim != 4 or pixels.shape[-1] < 3:
            raise ValueError(
                f"Save as RefMod: {filename!r} read as {tuple(pixels.shape)}, "
                f"expected [T, H, W, C] images")

        # Before `capture` turns the frames into differences: the preview is of
        # the picture the user chose, not of the motion trace.
        preview = _preview_png(pixels)

        if capture == "motion":
            if int(pixels.shape[0]) < 2:
                raise ValueError(
                    "Save as RefMod: capture='motion' needs at least two frames — "
                    "a single still has no movement to keep. Use capture='full'.")
            # |f[t+1] - f[t]|, normalized to the clip's own peak so static frames
            # stay dark and only the movement lights up.
            differences = (pixels[1:] - pixels[:-1]).abs()
            peak = differences.max()
            if float(peak) > 1e-6:
                differences = differences / peak
            pixels = differences

        count = int(pixels.shape[0])
        # A clip is cut to the VAE's causal 4k+1 grid before it is encoded —
        # anything else makes the temporal chunker produce an empty chunk.
        if count > 1:
            valid = ((count - 1) // 4) * 4 + 1
            if valid != count:
                print(f"[Save as RefMod] trimming {count} -> {valid} frames to the "
                      f"VAE's causal 4k+1 grid")
            pixels = pixels[:valid]
        pixels, target_h, target_w = _resize(pixels.float(), _DEFAULT_EDGE)
        pixels = _ensure_min_edge(pixels)

        latent = vae.encode(pixels)
        if latent.ndim != 5 or int(latent.shape[1]) != 24:
            raise ValueError(
                f"Save as RefMod: expected a MiniMax H3 video VAE latent "
                f"[1, 24, T, H, W], got {tuple(latent.shape)} — is the connected "
                f"VAE the H3 video VAE?")
        latent_t = int(latent.shape[2])
        latent_h = int(latent.shape[3])
        latent_w = int(latent.shape[4])
        tokens = latent_t * (latent_h // 2) * (latent_w // 2)
        stored_kind = "image" if latent_t == 1 else "video"

        path = refmod.save_mod(
            name, latent, concept_type=reference_type, mode="encode",
            subfolder="", source=f"creator/{capture}",
            pool=f"full-res {target_w}x{target_h}px",
            tags=[stored_kind, capture] if capture != "full" else [stored_kind],
            preview=preview)
        print(f"[Save as RefMod] {stored_kind} RefMod ({capture}): "
              f"{latent_t}x{latent_h}x{latent_w} latent, {tokens} tokens -> "
              f"{path}.safetensors")
        return io.NodeOutput()


NODES = [ContinuitySaveRefMod]


class RefModSaveExtension(ComfyExtension):
    async def get_node_list(self):
        return list(NODES)
