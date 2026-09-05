"""The drift guard: a pass's clip read off the model's last few guesses at it,
averaged, rather than off its final one.

A rectified-flow sampler walks from noise to picture in steps, and the picture
it ends on is, exactly, the noise minus the velocity it predicted at each step
times that step's width. Regroup the same sum and every step is a full guess at
the clean latent — `x_s - s * v_i`, the picture the model would have finished
on had it kept the velocity it predicted there — and the sampler's output is
the average of those guesses, each weighted by its step. "Towards Error-Free
Long Video Generation" (arXiv 2606.22370) looks at the guesses one at a time
on a chained Wan model and finds where the drift lives: the late steps, which
add texture and with it the over-sharpening and the small brightness bias that
each continued shot inherits and adds to again, and the very early ones, which
carry the colour cast. It keeps the guesses from a window of the schedule,
renormalises, and hands *that* on as the clip — training-free, and on their
chain it is what stops the compounding. Issues #41 and #46 describe the same
ramp on H3, and on an eight-shot strip this took the frying out of it.

This is that, as a model patch, counted in guesses rather than in the paper's
sigma. H3 samples at flow shift 12, where a 20-step schedule's last three
steps start at sigma 0.68, 0.57 and 0.39 and a turbo schedule's steps all
start above 0.6: a window on sigma is about the last few steps of a long
schedule and catches one step or none of a short one. "The last N guesses"
means the same thing on both, and it is what the settings page's one rail
says. Fewer guesses hold the shot before more truly and come out softer; every
guess comes out crisper and a little less faithful, since the early guesses
are the model's generic ones. Measured, not derived: the strip said so.

A post-cfg hook records each step's velocity while the sampler runs, and a
wrapper round the sampler swaps its output for the average once the schedule
reaches zero. Only the picture: H3's latent packs the sound beside it, and the
sound row leaves as the sampler made it. The patch sees a schedule sampled in
two sittings — the turbo lead-in's split — as one, because the second sitting
starts on the sigma the first stopped at; a schedule that starts partway, the
refine's or the restore's, is its own trajectory from wherever it starts.
"""

from collections import deque

import torch

import comfy.nested_tensor
import comfy.patcher_extension
from comfy_api.latest import io

TRUNCATE_NODE = "MiniMaxH3TruncatedFlow"


class Trajectory:
    """One schedule's worth of steps, whatever number of sittings sample it.

    `record` keeps the last `guesses` steps' `d_i * v_i` and `d_i` — every
    step's, when `guesses` is 0 — beside where the schedule was entered and the
    sigma there. `finish` reads the average off them.
    """

    def __init__(self, guesses=0):
        self.guesses = int(guesses)
        self.start = None
        self.s = None
        self.terms = deque(maxlen=self.guesses or None)
        self.last = None        # the sigma the latest sitting stopped on

    def continues_at(self, sigma):
        """Whether a sitting starting on `sigma` is this schedule's next one."""
        return self.last is not None and abs(self.last - float(sigma)) < 1e-6

    def record(self, sigma, width, x, denoised):
        """One model call: `x` at `sigma`, and what the model made of it."""
        sigma, width = float(sigma), float(width)
        if width <= 0:
            return
        if self.start is None:
            self.start, self.s = _float(x), sigma
        self.terms.append((_float((x - denoised) / sigma) * width, width))

    def finish(self, samples):
        """The average of the kept guesses, or `samples` where none was kept."""
        if not self.terms:
            return samples
        acc = None
        weight = 0.0
        for term, width in self.terms:
            acc = term if acc is None else acc + term
            weight += width
        out = self.start - acc * (self.s / weight)
        if getattr(samples, "is_nested", False):
            # The picture is redrawn from the guesses; the sound row leaves as
            # the sampler made it.
            video, *rest = samples.unbind()
            picture = out.unbind()[0].to(video.dtype)
            return comfy.nested_tensor.NestedTensor([picture, *rest])
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


# The trajectory in flight. Module state rather than the patch's own because
# the lead-in's two sittings run on two different models — one with the
# distillation held off — and both halves have to write the one sum. ComfyUI
# samples one graph at a time.
_open = None


def _patch(model, guesses):
    """`model` cloned, with the recorder and the wrapper on it."""

    def record(args):
        if _open is not None:
            sigmas = args["model_options"]["transformer_options"]["sample_sigmas"]
            sigma = float(args["sigma"].flatten()[0])
            _open.record(sigma, _step_width(sigma, sigmas), args["input"], args["denoised"])
        return args["denoised"]

    def sample(executor, guider, sigmas, *rest):
        global _open
        first, end = float(sigmas[0]), float(sigmas[-1])
        if _open is None or not _open.continues_at(first):
            _open = Trajectory(guesses)
        trajectory = _open
        samples = executor(guider, sigmas, *rest)
        trajectory.last = end
        if end > 1e-6:
            return samples          # a sitting with more schedule to come
        _open = None
        return trajectory.finish(samples)

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
            description=("Hands on the step-weighted average of the sampler's last "
                         "few clean-latent guesses instead of its last step, so the "
                         "over-sharpening and brightness bias a continued shot adds "
                         "stay out of the clip the next seam continues from. 0 "
                         "guesses means every step's."),
            inputs=[
                io.Model.Input("model"),
                io.Int.Input("guesses", default=3, min=0, max=999,
                             tooltip="How many of the schedule's last steps are averaged; 0 for all of them."),
            ],
            outputs=[io.Model.Output()],
        )

    @classmethod
    def execute(cls, model, guesses) -> io.NodeOutput:
        return io.NodeOutput(_patch(model, guesses))


NODES = [MiniMaxH3TruncatedFlow]
