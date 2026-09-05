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

import torch

import comfy.nested_tensor
import comfy.patcher_extension
from comfy_api.latest import io

TRUNCATE_NODE = "MiniMaxH3TruncatedFlow"


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

    def finish(self, samples):
        """The average of the kept guesses, or `samples` where none was kept."""
        if not self.terms:
            return samples
        acc = None
        weight = 0.0
        for term, width in self.terms:
            acc = term if acc is None else acc + term
            weight += width
        out = acc * (1.0 / weight)
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
            _open.record(_step_width(sigma, sigmas), args["denoised"])
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


NODES = [MiniMaxH3TruncatedFlow]
