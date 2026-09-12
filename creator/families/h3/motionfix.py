"""The motion fix: a finished pass slowed down where it moves too fast, drawn
again, and put back on its own clock.

`derope.py` says why and decides where; this is the half that holds the
weights and the pixels. The shape is the face pass's (`facepass.py`): the pass
is read back off the reel through `spill.open_frames`, the replacement is
streamed to a new spill, and the node hands back the reel with that pass in
place of the one it was given — so a later seam inherits the fixed frames.

What one run does:

1. reads the jerk profile off the sampler's own latent (the pass before it was
   trimmed and written, which is why `head` rides along — delivered frame `f`
   is latent frame `f + head`);
2. plans the holds, or returns the pass untouched when the profile says the
   pass is calm — said in the log rather than left to look like a render that
   did something;
3. repeats the delivered frames by their holds onto the 17k+5 grid, encodes the
   slowed clip with the video VAE, packs it with an empty soundtrack and
   samples it again from partway down the schedule, behind a mask that freezes
   the tokens covering the protected first and last frames;
4. decodes, keeps the first frame of every hold group, puts the protected
   frames' original pixels back verbatim, and writes that as the pass.

**The soundtrack rides through untouched.** The rewritten pass points at the
same audio file (`spill.rewrite`). The second pass is a joint AV model and is
given audio rows to draw — empty ones, fully re-noised, as the method does —
and what it draws is discarded: it was scored for a slowed performance and the
delivered track is already on the right clock.

**The conditioning is a segment node of its own** (`render.motion_payload`):
the shot's prompt and references at the delivered canvas, without its keyframes
— a keyframe is pinned to a frame index of the pass's own length, and the
slowed clip is another length. The protected ends do that job instead: held
at 1, frozen in the latent, and spliced back in pixels.
"""

import logging

import numpy as np
import torch

import comfy.model_management
import comfy.nested_tensor
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview
from comfy_api.latest import io

from ... import spill
from ...timeline import PASS_TYPE, REEL_TYPE
from . import derope

MOTION_FIX_NODE = "MiniMaxH3MotionFix"

# Frames per block on the way back to disk, as the face pass streams.
WRITE_CHUNK = 32


class MotionFixError(ValueError):
    """The motion fix was handed a pass it cannot re-draw."""


class MiniMaxH3MotionFix(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=MOTION_FIX_NODE,
            display_name="MiniMax H3 Motion Fix",
            category="Continuity/internal",
            description=("Slows a finished pass down where its motion is too fast for "
                         "the model, re-samples it partway down the schedule, and "
                         "recovers the original clock by frame selection. Written into "
                         "the graph by render.emit."),
            is_dev_only=True,
            inputs=[
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                io.Custom(PASS_TYPE).Input("source",
                    tooltip="The pass as written by the reel node."),
                io.Latent.Input("latent",
                    tooltip="The sampler's AV latent the pass was decoded from; only "
                            "its motion profile is read."),
                io.Int.Input("head", default=0, min=0, max=64,
                    tooltip="Frames trimmed off the front of the latent when the "
                            "pass was written."),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
                io.Int.Input("steps", default=20, min=1, max=200),
                io.Float.Input("cfg", default=1.0, min=0.0, max=30.0),
                io.Combo.Input("sampler_name", options=comfy.samplers.KSampler.SAMPLERS),
                io.Combo.Input("scheduler", options=comfy.samplers.KSampler.SCHEDULERS),
                io.Float.Input("denoise", default=derope.INJECT, min=0.05, max=0.99, step=0.01,
                    tooltip="How much of the schedule runs over the slowed init. "
                            "0.5–0.8 keeps the choreography and re-rolls the "
                            "rendering; lower keeps the smear, higher invents."),
                io.Float.Input("abstain", default=derope.ABSTAIN, min=0.0, max=10.0, step=0.1,
                    tooltip="A pass whose jerk profile peaks under this many times "
                            "its mean is left alone. 0 fixes every pass."),
                io.Custom(REEL_TYPE).Input("reel"),
            ],
            outputs=[io.Custom(REEL_TYPE).Output(display_name="reel"),
                     io.Custom(PASS_TYPE).Output(display_name="pass")],
        )

    @classmethod
    def execute(cls, model, positive, negative, vae, source, latent, head, seed,
                steps, cfg, sampler_name, scheduler, denoise, abstain, reel) -> io.NodeOutput:
        import nodes
        from comfy_extras.nodes_minimax_h3 import _empty_av_latent

        samples = latent["samples"]
        if not getattr(samples, "is_nested", False):
            raise MotionFixError("expected MiniMax H3's AV latent — a (video, audio) pair")
        video_latent = samples.unbind()[0]
        profile = derope.jerk_profile(video_latent.detach().float().cpu().numpy())

        frames = spill.open_frames(source)
        count = int(source["frames"])
        width, height = int(source["width"]), int(source["height"])
        plan = derope.plan(profile, count, int(head), abstain=float(abstain))
        # The decision goes into the history as well as the log, so a run can
        # be read back over the API: what the profile looked like, and whether
        # the pass was touched.
        seen = derope.contrast(profile)
        if plan is None:
            report = f"calm (contrast {seen:.2f} under {float(abstain):g}) — left as it is"
            logging.info("[MiniMax] motion fix: %s", report)
            return io.NodeOutput(reel, source, ui={"mmc_motion": [
                {"fixed": False, "contrast": seen, "report": report}]})
        logging.info("[MiniMax] motion fix: %s", plan.report)

        # The slowed clip, on the CPU: it is up to four times the pass and the
        # encoder moves it over a batch at a time.
        order = torch.tensor(derope.smear_index(plan.holds))
        images = torch.from_numpy(np.array(frames)).float().div_(255.0)[order]

        shell, aligned = _empty_av_latent(width, height, plan.dilated)
        if aligned != plan.dilated:
            raise MotionFixError(
                f"a {plan.dilated}-frame slowed clip is not on H3's frame grid "
                f"({aligned} is) — derope.pad_to_grid exists to prevent this")
        shell_video, audio = shell["samples"].unbind()
        encoded = vae.encode(images[..., :3])
        if encoded.ndim == 4:                     # [B,C,H,W] -> [1,C,T,H,W]
            encoded = encoded.unsqueeze(0).movedim(1, 2)
        encoded = encoded.to(shell_video.device, shell_video.dtype)
        if encoded.shape[-3:] != shell_video.shape[-3:]:
            raise MotionFixError(
                f"the slowed clip encoded to {tuple(encoded.shape[-3:])} where a "
                f"{plan.dilated}-frame run wants {tuple(shell_video.shape[-3:])}")
        del images

        # Redraw the picture except the frozen tokens (zeros there), and let the
        # empty soundtrack be drawn freely — it is thrown away below. Core
        # unbinds the mask per stream and packs it with the latent.
        video_mask = torch.ones_like(encoded, dtype=torch.float32)
        for t in plan.frozen:
            video_mask[:, :, t] = 0.0
        mask = comfy.nested_tensor.NestedTensor(
            (video_mask, torch.ones_like(audio, dtype=torch.float32)))
        packed = comfy.nested_tensor.NestedTensor((encoded, audio))
        noise = comfy.sample.prepare_noise(packed, seed)
        sampled = comfy.sample.sample(
            model, noise, steps, cfg, sampler_name, scheduler, positive, negative,
            packed, denoise=denoise, noise_mask=mask, seed=seed,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED)

        decoded = nodes.VAEDecode().decode(vae, {"samples": sampled})[0]
        if int(decoded.shape[0]) != plan.dilated:
            raise MotionFixError(
                f"the slowed clip decoded to {int(decoded.shape[0])} frames, "
                f"not the {plan.dilated} it was sampled at")
        recovered = decoded[torch.tensor(derope.recover_index(plan.holds))][..., :3]
        recovered = recovered.clamp(0.0, 1.0).cpu()
        del decoded, sampled
        written = spill.rewrite(source, cls._blocks(frames, recovered, plan.protected))
        # The reel this was handed already ends with the pass that has just
        # been fixed — this node runs after the one that put it there — so the
        # replacement goes in its place rather than after it.
        return io.NodeOutput([*reel[:-1], {"pass": written}], written, ui={"mmc_motion": [
            {"fixed": True, "contrast": seen, "report": plan.report,
             "holds": list(plan.holds), "frozen": list(plan.frozen)}]})

    @classmethod
    def _blocks(cls, frames, recovered, protected):
        """The fixed pass a chunk at a time, the protected frames' pixels put
        back from the original — a pure copy, so the join with the passes on
        either side is byte-for-byte what was delivered."""
        count = int(recovered.shape[0])
        for base in range(0, count, WRITE_CHUNK):
            comfy.model_management.throw_exception_if_processing_interrupted()
            stop = min(base + WRITE_CHUNK, count)
            block = recovered[base:stop].clone()
            for f in range(base, stop):
                if f in protected:
                    block[f - base] = torch.from_numpy(np.array(frames[f])).float().div_(255.0)
            yield block


NODES = [MiniMaxH3MotionFix]
