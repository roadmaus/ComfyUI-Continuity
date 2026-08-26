"""The refine pass of a two-pass render: upscale the video latent, re-sample.

Past the native 768 px short edge the weights are off-distribution, so instead
of sampling there directly, the render loop samples at the first-pass edge — the
trained edge by default, lower when the user trades the first pass for speed —
and hands the result here: the video half of the AV latent is interpolated up to the
target canvas, re-noised partway down the schedule, and sampled again against
conditioning that was *rebuilt at the target size* — the same references and
keyframes, re-encoded so their condition latents match the latent they ride
along with. Regeneration from the original context, not classical upscaling,
which is also the shape of MiniMax's own (API-only) H3-Regenerate-2K stage.

Why this is a node and not a stock `LatentUpscaleBy` + `KSampler` pair — and
what Tr1dae's ComfyUI-MiniMaxH3_LatentUpscaler, which pioneered the two-pass
workflow this borrows from, works around the hard way:

- The H3 latent is a NestedTensor pair (video ``[B,24,T,H/16,W/16]``, audio
  ``[B,32,2,T40]``). Core's latent tooling indexes ``shape`` as if there were
  one tensor and breaks on it.
- A stock partial-denoise KSampler noises the *whole* pack, so the soundtrack
  the first pass already resolved — the one the user heard — would be melted
  and re-drawn. Here only the picture is re-noised. H3's flow schedule mixes
  noise in as a lerp (``x = sigma*noise + (1-sigma)*x0``, `CONST`), so handing
  the sampler zero noise for the audio half still scales it by ``1 - sigma``;
  the audio is pre-divided by exactly that so it enters the first step
  unchanged. Exact, because `MiniMaxH3AV.scale_factor` is 1.0 and the AV
  audio_scale is a bare multiplier — there is no shift to break the division.

The audio still rides through the steps (the model attends across the pack),
so it is not bit-identical to the first pass — but it is its sound, not a
re-roll of it.
"""

import torch

import comfy.nested_tensor
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview
from comfy_api.latest import io


def upscale_video_latent(video, width, height):
    """The video half, interpolated to the target canvas. [B,C,T,H,W] in and out.

    Bicubic per frame, like a hires-fix: the temporal axis is already right and
    interpolating across it would smear motion between latent frames.
    """
    batch, channels, frames = video.shape[0], video.shape[1], video.shape[2]
    flat = video.movedim(2, 1).reshape(batch * frames, channels, *video.shape[3:])
    flat = comfy.utils.common_upscale(flat, width // 16, height // 16, "bicubic", "disabled")
    return flat.reshape(batch, frames, channels, *flat.shape[2:]).movedim(1, 2)


class MiniMaxH3RefinePass(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3RefinePass",
            display_name="H3 Refine Pass",
            category="Continuity/internal",
            description="Second pass of a two-pass render: upscales the video half of an "
                        "H3 AV latent and re-samples it partway down the schedule, leaving "
                        "the soundtrack un-noised. Written into the graph by render.emit.",
            is_dev_only=True,
            inputs=[
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Latent.Input("latent",
                    tooltip="The first pass's sampled AV latent, at the native canvas."),
                io.Int.Input("width", default=1344, min=32, max=8192, step=32),
                io.Int.Input("height", default=768, min=32, max=8192, step=32),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
                io.Int.Input("steps", default=20, min=1, max=200),
                io.Float.Input("cfg", default=1.0, min=0.0, max=30.0),
                io.Combo.Input("sampler_name", options=comfy.samplers.KSampler.SAMPLERS),
                io.Combo.Input("scheduler", options=comfy.samplers.KSampler.SCHEDULERS),
                io.Float.Input("denoise", default=0.5, min=0.01, max=0.99, step=0.01,
                    tooltip="How much of the schedule the refinement runs. Strictly under "
                            "1.0: at 1.0 nothing of the first pass survives, and the "
                            "audio carry-through divides by (1 - the starting sigma)."),
            ],
            outputs=[io.Latent.Output()],
        )

    @classmethod
    def execute(cls, model, positive, negative, latent, width, height,
                seed, steps, cfg, sampler_name, scheduler, denoise) -> io.NodeOutput:
        samples = latent["samples"]
        if not samples.is_nested:
            raise ValueError("expected MiniMax H3's AV latent — a (video, audio) pair")
        video, audio = samples.unbind()
        video = upscale_video_latent(video, width, height)

        # The sigma the refinement starts at: the same slice of the schedule
        # KSampler takes for this denoise, computed up front because the audio
        # compensation needs it before sampling begins. Built through the same
        # class so the two cannot drift.
        sigma0 = float(comfy.samplers.KSampler(
            model, steps=steps, device=model.load_device, sampler=sampler_name,
            scheduler=scheduler, denoise=denoise, model_options=model.model_options,
        ).sigmas[0])
        if not 0.0 < sigma0 < 1.0:
            raise ValueError(
                f"refine denoise {denoise} starts the schedule at sigma {sigma0}, "
                f"which leaves nothing of the first pass to refine — it must be "
                f"strictly between 0 and 1."
            )

        # Noise for the picture, none for the sound — and the sound pre-divided
        # by the (1 - sigma) its zero-noise lerp will multiply it by, so it
        # enters the first step exactly as the first pass left it.
        noise_video = torch.randn(
            video.size(), dtype=torch.float32, layout=video.layout,
            generator=torch.manual_seed(seed), device="cpu").to(video.dtype)
        noise = comfy.nested_tensor.NestedTensor(
            (noise_video, torch.zeros_like(audio, device="cpu")))
        start = comfy.nested_tensor.NestedTensor((video, audio / (1.0 - sigma0)))

        refined = comfy.sample.sample(
            model, noise, steps, cfg, sampler_name, scheduler,
            positive, negative, start,
            denoise=denoise, seed=seed,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED)

        out = dict(latent)
        out["samples"] = refined
        return io.NodeOutput(out)


NODES = [MiniMaxH3RefinePass]
