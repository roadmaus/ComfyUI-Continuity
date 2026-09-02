"""The seam restore: the run a continued shot inherits, re-drawn before it is
conditioned on.

Every continued pass comes out a little softer and a little harder in contrast
than the pass it continues — the DiT's own bias when it anchors on its own
output — and because the *next* seam anchors on that tail, the loss compounds
down a strip (issue #41; H3-Continuum meets the same wall on a pure latent
handoff). No arrangement of the handoff cures it, so this breaks the chain
instead: the tail the seam is about to hand over is re-noised partway down the
schedule and sampled again against the source shot's own references and
prompt, at the same canvas, and *that* is what the next pass continues from.
Partway, not fresh — the picture, its motion and its light are held in the
latent, and what the schedule's lower half re-resolves is texture and edge.

Only the run the seam inherits, never the pass: the source was written as it
came out and stays that way, so a restore costs one short generation per seam —
a few frames at the pass's canvas — whatever the shots are long. The join is
then the source's own last frames against a continuation that started from a
sharper copy of them, and at these strengths that is a step in detail, not in
composition; it is the trade the pass makes on purpose.

The mechanics are the face pass's (`facepass.py`): the frames are encoded with
the video VAE, packed with an empty audio latent, and sampled behind a nested
denoise mask — ones for the picture, zeros for the sound — so the sampler
redraws the picture and holds the sound row exactly (`hires.py` has the whole
of why the mask and not zero noise). The sound is empty rather than the
source's: the run is at most a second and a half, the seam carries its sound
by another road (`inherited_audio`), and what is restored here is the picture.
"""

import torch

import comfy.nested_tensor
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview
from comfy_api.latest import io

SEAM_RESTORE_NODE = "MiniMaxH3SeamRestore"


class SeamRestoreError(ValueError):
    """The seam restore was handed frames it cannot encode."""


class MiniMaxH3SeamRestore(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=SEAM_RESTORE_NODE,
            display_name="MiniMax H3 Seam Restore",
            category="MiniMax/internal",
            description=("Re-samples the frames a seam inherits from partway down "
                         "the schedule, against the source shot's own conditioning, "
                         "so the next pass continues from a restored copy rather "
                         "than a softened one. Written into the graph by render.emit."),
            is_dev_only=True,
            inputs=[
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                # The source pass's tail, at a length on H3's 17k+5 grid — the
                # loop widens a single-frame seam's read to the grid's first
                # member, and every blend width is already on it.
                io.Image.Input("frames"),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
                io.Int.Input("steps", default=20, min=1, max=10000),
                io.Float.Input("cfg", default=1.0, min=0.0, max=100.0, step=0.1),
                io.Combo.Input("sampler_name", options=comfy.samplers.KSampler.SAMPLERS),
                io.Combo.Input("scheduler", options=comfy.samplers.KSampler.SCHEDULERS),
                io.Float.Input("denoise", default=0.45, min=0.01, max=0.99, step=0.01),
            ],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def execute(cls, model, positive, negative, vae, frames, seed, steps, cfg,
                sampler_name, scheduler, denoise) -> io.NodeOutput:
        import nodes
        from comfy_extras.nodes_minimax_h3 import _empty_av_latent

        length = int(frames.shape[0])
        height, width = int(frames.shape[1]), int(frames.shape[2])
        latent, aligned = _empty_av_latent(width, height, length)
        if aligned != length:
            # The loop only ever reads a run off `legal_frame_counts`, so this is
            # the graph having been built against other arithmetic.
            raise SeamRestoreError(
                f"a {length}-frame seam is not on H3's frame grid ({aligned} is)")
        shell_video, audio = latent["samples"].unbind()

        video = vae.encode(frames[..., :3])
        if video.ndim == 4:                       # [B,C,H,W] -> [1,C,T,H,W]
            video = video.unsqueeze(0).movedim(1, 2)
        video = video.to(shell_video.device, shell_video.dtype)
        if video.shape[-3:] != shell_video.shape[-3:]:
            raise SeamRestoreError(
                f"the seam encoded to {tuple(video.shape[-3:])} where a "
                f"{length}-frame run wants {tuple(shell_video.shape[-3:])}")

        # Redraw the picture (ones), hold the sound exactly (zeros) — core
        # unbinds the mask per stream and packs it with the latent.
        mask = comfy.nested_tensor.NestedTensor(
            (torch.ones_like(video, dtype=torch.float32),
             torch.zeros_like(audio, dtype=torch.float32)))
        samples = comfy.nested_tensor.NestedTensor((video, audio))
        noise = comfy.sample.prepare_noise(samples, seed)
        restored = comfy.sample.sample(
            model, noise, steps, cfg, sampler_name, scheduler, positive, negative,
            samples, denoise=denoise, noise_mask=mask, seed=seed,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED)

        images = nodes.VAEDecode().decode(vae, {"samples": restored})[0]
        return io.NodeOutput(images[..., :3].clamp(0.0, 1.0))


NODES = [MiniMaxH3SeamRestore]
