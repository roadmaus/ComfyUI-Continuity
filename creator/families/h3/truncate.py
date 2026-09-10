"""The drift guard: a pass's clip read off the model's last few guesses at it,
averaged, rather than off its final one.

A rectified-flow sampler walks from noise to picture in steps, and at every
step the model makes a full guess at the clean picture — the `denoised` the
sampler steps toward. The picture the run ends on is, on a Euler step to zero,
exactly the last of those guesses. "Towards Error-Free Long Video Generation"
(arXiv 2606.22370) writes the output as the step-weighted average of the
guesses instead, looks at them one at a time on a chained Wan model, and finds
where the drift lives: the late steps, which add texture and with it the
over-sharpening and the small brightness bias each continued shot inherits and
adds to again. It hands on the average over a window of the schedule and, on
their chain, that stops the compounding with no training. Issues #41 and #46
describe the same ramp on H3, and on an eight-shot strip averaging the last
few guesses took the frying out of it.

This is that, as a model patch, with two departures from the paper. It is
counted in guesses rather than sigma: H3 samples at flow shift 12, where a
20-step schedule's last three steps start at sigma 0.68, 0.57 and 0.39 and a
turbo schedule's steps all start above 0.6, so a window on sigma is about the
last few steps of a long schedule and catches one step or none of a short one,
while "the last N guesses" means the same thing on both. And the guess is the
model's own prediction at the step, not the paper's `noise - velocity`: the
two agree only when every velocity along the run came from one consistent
model, which a 20-step base run is and a turbo run is not — three lead-in
steps on the base weights and five on the distillation disagree wildly, and
the paper's form folds that disagreement into every guess. Averaging the
predictions themselves needs no such assumption, and one guess is the plain
render. Each guess beyond it is steadier and a little softer; the early guesses
are the model's generic picture, so many of them loosen faces and objects.

A post-cfg hook records each step's prediction while the sampler runs, and a
wrapper round the sampler swaps its output for the average once the schedule
reaches zero. Only the picture: H3's latent packs the sound beside it, and the
sound row leaves as the sampler made it. The patch sees a schedule sampled in
two sittings — the turbo lead-in's split — as one, because the second sitting
starts on the sigma the first stopped at; a schedule that starts partway, the
refine's or the restore's, is its own trajectory from wherever it starts.
"""

from collections import deque
from contextvars import ContextVar

import torch

import comfy.nested_tensor
import comfy.patcher_extension
import comfy.utils
from comfy_api.latest import io

TRUNCATE_NODE = "MiniMaxH3TruncatedFlow"
GUARDED_TURBO_NODE = "MiniMaxH3GuardedTurboSampler"


class Trajectory:
    """One schedule's worth of steps, whatever number of sittings sample it.

    `record` keeps the last `guesses` steps' predictions, each with its step's
    width — every step's, when `guesses` is 0. `finish` reads the weighted
    average off them.
    """

    def __init__(self, guesses=0):
        self.guesses = int(guesses)
        self.terms = deque(maxlen=self.guesses or None)
        self.last = None        # the sigma the latest sitting stopped on

    def continues_at(self, sigma):
        """Whether a sitting starting on `sigma` is this schedule's next one."""
        return self.last is not None and abs(self.last - float(sigma)) < 1e-6

    def record(self, width, denoised):
        """One model call: its prediction, and the width of the step it opens."""
        width = float(width)
        if width <= 0:
            return
        self.terms.append((_float(denoised) * width, width))

    def finish(self, samples, latent_shapes=None):
        """The average of the kept guesses, or `samples` where none was kept.

        Only the picture. The sampler runs H3's two streams as one flat pack
        — `latent_shapes` is how core cuts it, set on the model for the run —
        so the pack is opened, the video slice replaced, and the sound slice
        put back as the sampler made it. A nested pair is the same two
        streams already apart.
        """
        if not self.terms:
            return samples
        acc = None
        weight = 0.0
        for term, width in self.terms:
            acc = term if acc is None else acc + term
            weight += width
        out = acc * (1.0 / weight)
        if getattr(samples, "is_nested", False):
            video, *rest = samples.unbind()
            picture = out.unbind()[0].to(video.dtype)
            return comfy.nested_tensor.NestedTensor([picture, *rest])
        if latent_shapes is not None and len(latent_shapes) > 1:
            averaged = comfy.utils.unpack_latents(out, latent_shapes)
            kept = comfy.utils.unpack_latents(samples, latent_shapes)
            return comfy.utils.pack_latents([averaged[0].to(samples.dtype), *kept[1:]])[0]
        return out.to(samples.dtype)


def _float(x):
    """`x` in float32 — a fresh tensor, so the sampler's own is never held."""
    if getattr(x, "is_nested", False):
        return comfy.nested_tensor.NestedTensor([t.float().clone() for t in x.unbind()])
    return x.float().clone()


def _step_width(sigma, sigmas):
    """The width of the schedule step that starts at `sigma`, or 0 off it."""
    index = int(torch.argmin((sigmas.to(torch.float32) - float(sigma)).abs()))
    if index >= len(sigmas) - 1:
        return 0.0
    return float(sigmas[index] - sigmas[index + 1])


# Legacy separately wired sampler sittings retain their shared state. Newly
# emitted guarded Turbo runs own it in a ContextVar, so the two models share
# one history without sharing it with another concurrent/nested run.
_open = None
_run = ContextVar("continuity_guarded_turbo_run", default=None)


class _Run:
    def __init__(self):
        self.trajectory = None


def _current():
    run = _run.get()
    return run.trajectory if run is not None else _open


def _set_current(trajectory):
    global _open
    run = _run.get()
    if run is not None:
        run.trajectory = trajectory
    else:
        _open = trajectory


def _release(trajectory):
    trajectory.terms.clear()
    if _current() is trajectory:
        _set_current(None)


def _patch(model, guesses):
    """`model` cloned, with the recorder and the wrapper on it."""

    def record(args):
        trajectory = _current()
        if trajectory is not None:
            sigmas = args["model_options"]["transformer_options"]["sample_sigmas"]
            sigma = float(args["sigma"].flatten()[0])
            trajectory.record(_step_width(sigma, sigmas), args["denoised"])
        return args["denoised"]

    def sample(executor, guider, sigmas, *rest):
        first, end = float(sigmas[0]), float(sigmas[-1])
        trajectory = _current()
        if trajectory is None or not trajectory.continues_at(first) or trajectory.guesses != guesses:
            if trajectory is not None:
                _release(trajectory)
            trajectory = Trajectory(guesses)
            _set_current(trajectory)
        keep_open = False
        try:
            samples = executor(guider, sigmas, *rest)
            trajectory.last = end
            if end > 1e-6:
                keep_open = True
                return samples      # a successful sitting with more schedule to come
            # Set on the model by core's `inner_sample` before the sampler runs.
            shapes = getattr(getattr(guider, "inner_model", None), "latent_shapes", None)
            return trajectory.finish(samples, shapes)
        finally:
            # ComfyUI cancellation derives from BaseException, not Exception.
            # Release the predictions even if sampling or finish() is interrupted,
            # while preserving a successful lead-in until its tail consumes it.
            if not keep_open:
                _release(trajectory)

    patched = model.clone()
    patched.set_model_sampler_post_cfg_function(record)
    patched.add_wrapper_with_key(
        comfy.patcher_extension.WrappersMP.SAMPLER_SAMPLE, TRUNCATE_NODE, sample)
    return patched


class MiniMaxH3TruncatedFlow(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=TRUNCATE_NODE,
            display_name="MiniMax H3 Drift Guard",
            category="MiniMax/internal",
            description=("Hands on the step-weighted average of the model's last "
                         "few clean-picture predictions instead of the sampler's last "
                         "step, so the over-sharpening and brightness bias a continued "
                         "shot adds stay out of the clip the next seam continues from. "
                         "One guess is the plain render; 0 means every step's."),
            inputs=[
                io.Model.Input("model"),
                io.Int.Input("guesses", default=3, min=0, max=99,
                             tooltip="How many of the schedule's last steps are averaged; 0 for all of them."),
            ],
            outputs=[io.Model.Output()],
        )

    @classmethod
    def execute(cls, model, guesses) -> io.NodeOutput:
        return io.NodeOutput(_patch(model, guesses))


class MiniMaxH3GuardedTurboSampler(io.ComfyNode):
    """Two core sampler calls, but one cacheable result and one history owner.

    A cached opening LATENT does not contain the post-CFG predictions the guard
    needs. Caching the two sittings independently therefore changes the average
    when only the tail is invalidated. Keep both in one node instead of caching
    GPU prediction tensors or disabling caching for the whole render.
    """

    @classmethod
    def define_schema(cls):
        import comfy.samplers

        return io.Schema(
            node_id=GUARDED_TURBO_NODE,
            display_name="H3 Guarded Turbo Sampler",
            category="Continuity/internal",
            is_dev_only=True,
            description="Runs both Turbo sittings as one drift-guard trajectory and one cache unit.",
            inputs=[
                io.Model.Input("model"),
                io.Model.Input("lead_model"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Latent.Input("latent_image"),
                io.Int.Input("noise_seed", default=0, min=0, max=0xffffffffffffffff),
                io.Int.Input("steps", default=8, min=2, max=10000),
                io.Int.Input("lead_steps", default=3, min=1, max=9999),
                io.Float.Input("cfg", default=1.0, min=0.0, max=100.0),
                io.Combo.Input("sampler_name", options=comfy.samplers.KSampler.SAMPLERS),
                io.Combo.Input("scheduler", options=comfy.samplers.KSampler.SCHEDULERS),
            ],
            outputs=[io.Latent.Output()],
        )

    @classmethod
    def execute(cls, model, lead_model, positive, negative, latent_image,
                noise_seed, steps, lead_steps, cfg, sampler_name, scheduler) -> io.NodeOutput:
        import nodes

        if not 0 < lead_steps < steps:
            raise ValueError("a guarded Turbo lead-in must be between zero and the total step count")
        run = _Run()
        token = _run.set(run)
        try:
            common = dict(noise_seed=noise_seed, steps=steps, cfg=cfg,
                          sampler_name=sampler_name, scheduler=scheduler,
                          positive=positive, negative=negative)
            sampler = nodes.KSamplerAdvanced()
            opening = sampler.sample(
                model=lead_model, latent_image=latent_image,
                add_noise="enable", start_at_step=0, end_at_step=lead_steps,
                return_with_leftover_noise="enable", **common)[0]
            finished = sampler.sample(
                model=model, latent_image=opening,
                add_noise="disable", start_at_step=lead_steps, end_at_step=steps,
                return_with_leftover_noise="disable", **common)[0]
            return io.NodeOutput(finished)
        finally:
            # Also covers cancellation after the lead-in but before the tail's
            # wrapper runs. No prediction history is returned into Comfy's cache.
            if run.trajectory is not None:
                _release(run.trajectory)
            _run.reset(token)


NODES = [MiniMaxH3TruncatedFlow, MiniMaxH3GuardedTurboSampler]
