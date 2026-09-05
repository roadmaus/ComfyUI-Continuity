"""Truncation-rectified flow: the pass's latent, read off the middle of the
schedule rather than the end of it.

A rectified-flow sampler walks from noise to picture in steps, and the picture
it ends on is, exactly, the noise minus the velocity it predicted at each step
times that step's width. Regroup the same sum and every step is a full guess at
the clean latent — `x_s - s * v_i`, the estimate the model would have finished
on had it kept the velocity it predicted there — and the sampler's output is
the average of those guesses, each weighted by its step. "Towards Error-Free
Long Video Generation" (arXiv 2606.22370) looks at the guesses one at a time
on a chained Wan model and finds where the drift lives: the late steps, which
add texture and with it the over-sharpening and the small brightness bias that
each continued shot inherits and adds to again, and the very early ones, which
carry the colour cast. The middle of the schedule guesses cleanly. So it keeps
only the guesses whose timestep falls in a window, renormalises the weights,
and hands *that* on as the clip — training-free, and on their chain it is what
stops the compounding. Issues #41 and #46 describe the same ramp on H3.

This is that, as a model patch. A post-cfg hook records each step's velocity
while the sampler runs, and a wrapper round the sampler swaps its output for
the windowed average once the schedule reaches zero. Only the picture: H3's
latent packs the sound beside it, and the sound row leaves as the sampler made
it. The patch sees a schedule sampled in two sittings — the turbo lead-in's
split — as one, because the second sitting starts on the sigma the first
stopped at; a schedule that starts partway, the refine's or the restore's, is
its own trajectory from wherever it starts. A window no step of the schedule
lands in leaves the sampler's output alone.

The maths is the sampler's own: nothing here filters in space or time, and a
window of the whole schedule returns exactly what the sampler returned. What
is thrown away is the late steps' texture, and the paper's [0.3, 0.7] on their
model is a picture slightly softer than the full run and a chain that does not
walk; the windows here are named in `WINDOWS`, and the settings page picks one.
"""

import torch

import comfy.nested_tensor
import comfy.patcher_extension
from comfy_api.latest import io

TRUNCATE_NODE = "MiniMaxH3TruncatedFlow"

# The settings page's named choices, as `(t_low, t_high)` on the model's own
# sigma — `None` is off. "middle" is the paper's window; "tail" drops the late
# steps alone, its Table 3's other column, and keeps the early ones' structure.
# The page's fourth choice, "custom", is two numbers off the settings file and
# not in here. Mind the shift: H3 samples at flow shift 12, so a 20-step
# schedule's last three steps start at sigma 0.68, 0.57 and 0.39 and a turbo
# schedule's steps all start above 0.6 — on sigma, the named windows are about
# the last few steps of a long schedule and catch one step or none of a short
# one, which is what the custom pair is for.
WINDOWS = {"off": None, "tail": (0.3, 1.0), "middle": (0.3, 0.7)}


class Trajectory:
    """One schedule's worth of steps, whatever number of sittings sample it.

    `record` is the sum being built: `start` and `s` are where the schedule was
    entered and the sigma there, and `acc`/`weight` are the windowed steps'
    `d_i * v_i` and `d_i`. `finish` reads the windowed average off them.
    """

    def __init__(self, low, high):
        self.low, self.high = float(low), float(high)
        self.start = None
        self.s = None
        self.acc = None
        self.weight = 0.0
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
        if self.low <= sigma <= self.high:
            term = _float((x - denoised) / sigma) * width
            self.acc = term if self.acc is None else self.acc + term
            self.weight += width

    def finish(self, samples):
        """The windowed average, or `samples` where no step fell in the window."""
        if self.acc is None or self.weight <= 0:
            return samples
        out = self.start - self.acc * (self.s / self.weight)
        if getattr(samples, "is_nested", False):
            # The picture is redrawn from the window; the sound row leaves as
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


def _patch(model, low, high):
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
            _open = Trajectory(low, high)
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
            display_name="MiniMax H3 Truncated Flow",
            category="MiniMax/internal",
            description=("Hands on the average of the sampler's clean-latent guesses "
                         "from the steps whose sigma falls in [t_low, t_high] instead "
                         "of its last step, so the late steps' over-sharpening and "
                         "brightness bias stay out of the clip a seam continues from."),
            inputs=[
                io.Model.Input("model"),
                io.Float.Input("t_low", default=0.3, min=0.0, max=1.0, step=0.01),
                io.Float.Input("t_high", default=0.7, min=0.0, max=1.0, step=0.01),
            ],
            outputs=[io.Model.Output()],
        )

    @classmethod
    def execute(cls, model, t_low, t_high) -> io.NodeOutput:
        return io.NodeOutput(_patch(model, t_low, t_high))


NODES = [MiniMaxH3TruncatedFlow]
