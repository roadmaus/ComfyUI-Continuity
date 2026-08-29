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
  and re-drawn. Here only the picture is re-noised, and the soundtrack is held
  by a nested denoise mask: ones for the picture, zeros for the sound, which is
  core's own convention and the same one the face pass and supplied sound use.

**Why the mask and not zero noise for the audio half.** Handing the sampler no
noise for the sound is not enough to leave it alone, and this node used to try:
it pre-divided the audio by ``1 - sigma`` so a single-schedule lerp would put it
back, and let it ride. Two things are wrong with that, and together they were
issue #33 — the picture came back sharp and the sound came back as noise.

- H3 is `FLOW_AV`: the audio stream has its *own* flow shift (12 for video, 3
  for audio) and the sampler carries it as ``(sigma_v / sigma_a) * x_audio``,
  not as the constant ``audio_scale = shift / audio_shift`` that
  `process_latent_in` applies. At denoise 0.5 that is 2.5 against 4 — the
  injected sound was 1.6x too hot.
- Nothing held it after the first step. The model is told the audio's timestep
  is ``t_a``, mid-schedule, unless an ``audio_denoise_mask`` says otherwise, so
  it predicted a velocity for a stream with no noise in it and the sampler
  applied that velocity for the whole refine.

With the mask, `comfy/samplers.py` re-injects the sound every step through
`MiniMaxH3.scale_latent_inpaint` — which applies the sigma-dependent factor
itself — and the model pins the audio rows at the cond timestep, so it *reads*
the soundtrack while it redraws the picture. It comes back exactly as the first
pass left it.
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
                        "H3 AV latent and re-samples it partway down the schedule, holding "
                        "the soundtrack out of the denoise. Written into the graph by render.emit.",
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
                            "1.0: at 1.0 nothing of the first pass survives to refine."),
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

        # Noise for the picture, none for the sound. The zeros are not what
        # preserves the audio — the mask below is — but noising a stream the
        # sampler is about to overwrite would only waste the draw.
        noise_video = torch.randn(
            video.size(), dtype=torch.float32, layout=video.layout,
            generator=torch.manual_seed(seed), device="cpu").to(video.dtype)
        noise = comfy.nested_tensor.NestedTensor(
            (noise_video, torch.zeros_like(audio, device="cpu")))

        # One mask, two statements: redraw the picture (ones), hold the sound
        # exactly (zeros). Built fresh rather than carried through from the
        # first pass — a supplied-sound mask is at the first pass's canvas, and
        # the whole soundtrack is held here regardless of which of it was given.
        mask = comfy.nested_tensor.NestedTensor(
            (torch.ones_like(video, dtype=torch.float32),
             torch.zeros_like(audio, dtype=torch.float32)))

        refined = comfy.sample.sample(
            model, noise, steps, cfg, sampler_name, scheduler,
            positive, negative, comfy.nested_tensor.NestedTensor((video, audio)),
            denoise=denoise, noise_mask=mask, seed=seed,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED)

        out = dict(latent)
        out["samples"] = refined
        # The incoming mask, if there was one, is the first pass's canvas and
        # says nothing about this latent.
        out.pop("noise_mask", None)
        return io.NodeOutput(out)


NODES = [MiniMaxH3RefinePass]
