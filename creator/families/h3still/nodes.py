"""The two nodes a MiniMax H3 still is made with: a one-frame latent to sample
and a decode that reads it.

Both follow shootthesound's Fizgig H3 Still (MIT,
github.com/shootthesound/ComfyUI-Fizgig-H3-Still), which is where the method
was worked out; `still.py` says why the family uses it.

**Why a latent of its own.** Core's H3 latents start at five frames — two
latent frames — and snap to the 17k+5 grid, because core's nodes make clips.
The model's own image convention is one latent frame, and sampling one is a
fraction of the cost of sampling the shortest clip and discarding half of it.

**Why a decode of its own.** The video VAE's decoder works in groups of five
latent frames and places its tokens by their position in the latent's length.
A lone latent frame is outside anything it was fitted on and comes back
banded and dark. Repeated into a full group it is inside it, and one of the
twenty pixel frames that come back is the picture — the fourth, the first
past the decoder's causal lead-in. Fizgig measured 30 dB for that round trip
against 17 dB for the lone frame.

Internal nodes, written into the graph by the pre-stage and not meant to be
placed by hand, though both work in a hand-built graph: anything that is not a
one-frame H3 latent on the H3 video VAE goes to the stock decode untouched.
"""

import torch

import comfy.model_management
import comfy.nested_tensor
from comfy_api.latest import io

# The latent's shape, which is the H3 VAE's: 24 channels on a /16 grid.
CHANNELS, DOWNSCALE = 24, 16
# The audio half the DiT samples beside the picture: 32 channels by 2, forty
# latent steps a second. One frame at 24 fps is 1/24 s, which rounds to two
# steps — the least the model is handed, and never decoded.
AUDIO_CHANNELS, AUDIO_BANDS, AUDIO_LATENT_FPS, FPS = 32, 2, 40, 24

# How many copies of the frame the decoder is shown, and which pixel frame of
# the twenty it returns is kept.
GROUP, KEEP = 5, 3


class ContinuityH3StillLatent(io.ComfyNode):
    """An empty MiniMax H3 latent of one frame, with the audio half the model
    samples beside it."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityH3StillLatent",
            display_name="H3 Still Latent",
            category="Continuity/internal",
            description="An empty one-frame MiniMax H3 latent: what the video model samples to make a still.",
            is_dev_only=True,
            inputs=[
                io.Int.Input("width", default=2272, min=64, max=8192, step=32),
                io.Int.Input("height", default=1280, min=64, max=8192, step=32),
                io.Int.Input("batch_size", default=1, min=1, max=64),
            ],
            outputs=[io.Latent.Output()],
        )

    @classmethod
    def execute(cls, width, height, batch_size) -> io.NodeOutput:
        device = comfy.model_management.intermediate_device()
        # The DiT patches 2x2 over the latent, so both sides have to be even.
        rows = (height // DOWNSCALE) // 2 * 2
        cols = (width // DOWNSCALE) // 2 * 2
        video = torch.zeros([batch_size, CHANNELS, 1, rows, cols], device=device)
        steps = max(1, round(AUDIO_LATENT_FPS / FPS))
        audio = torch.zeros([batch_size, AUDIO_CHANNELS, AUDIO_BANDS, steps], device=device)
        return io.NodeOutput({"samples": comfy.nested_tensor.NestedTensor((video, audio))})


class ContinuityH3StillDecode(io.ComfyNode):
    """A one-frame MiniMax H3 latent -> its picture, through the video VAE."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ContinuityH3StillDecode",
            display_name="H3 Still Decode",
            category="Continuity/internal",
            description="Decodes a one-frame MiniMax H3 latent as a still: the frame is repeated into a full "
                        "group for the video VAE's decoder and one pixel frame of the result is kept.",
            is_dev_only=True,
            inputs=[io.Latent.Input("samples"), io.Vae.Input("vae")],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def execute(cls, samples, vae) -> io.NodeOutput:
        latent = samples["samples"]
        # The pair arrives nested from the sampler; the picture is its first half.
        if getattr(latent, "is_nested", False):
            latent = latent.unbind()[0]
        model = vae.first_stage_model
        grouped = (latent.ndim == 5 and latent.shape[2] == 1
                   and hasattr(model, "_adaptive_decode")
                   and hasattr(model, "_finalize_pixels"))
        if not grouped:
            # A clip, another VAE, or a core whose H3 VAE is laid out
            # differently: the stock decode, which is right for the first two
            # and the best available for the third.
            images = vae.decode(latent)
            if images.ndim == 5:
                images = images.reshape(-1, *images.shape[-3:])
            return io.NodeOutput(images)

        shape = (1, latent.shape[1], GROUP, latent.shape[3], latent.shape[4])
        comfy.model_management.load_models_gpu(
            [vae.patcher], memory_required=vae.memory_used_decode(shape, vae.vae_dtype),
            force_full_load=getattr(vae, "disable_offload", False))
        pictures = []
        with torch.no_grad():
            for one in latent.split(1):
                one = one.to(device=vae.device, dtype=vae.vae_dtype)
                # The sampler's latent is normalised; the decoder's own entry
                # point takes it raw, so the statistics go back on first.
                mean = model.latents_mean.view(1, -1, 1, 1, 1).to(one)
                std = model.latents_std.view(1, -1, 1, 1, 1).to(one)
                group = (one * std + mean).repeat(1, 1, GROUP, 1, 1)
                # Tiled inside, as any decode at this size is.
                frames = model._adaptive_decode(group)
                picture = model._finalize_pixels(frames[:, :, KEEP:KEEP + 1])
                pictures.append(picture[:, :, 0].movedim(1, -1).to(
                    comfy.model_management.intermediate_device()))
                del frames, group
        return io.NodeOutput(torch.cat(pictures))


NODES = [ContinuityH3StillLatent, ContinuityH3StillDecode]
