"""The drift guard's arithmetic, against a sampler it can be checked by hand on.

`truncate.py` claims two things: that every guess averaged returns exactly what
an Euler sampler returned, and that the last few return the start minus those
steps' velocities, weighted by their widths. Both are one
Euler loop away from being checked, so this runs one — velocities made up, so
the identity is the thing under test and not a model — through the real
`Trajectory`, and then through the real patch on a stand-in ModelPatcher, in
one sitting and in the two the turbo lead-in splits a schedule into.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_truncate.py

Skips itself with a message if ComfyUI core cannot be imported.
"""

import importlib.util
import os
import sys
import types

import layout

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    import torch
    import comfy.nested_tensor
    import comfy.patcher_extension
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI core not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)


def _load(name):
    if "mmc" not in sys.modules:
        package = types.ModuleType("mmc")
        package.__path__ = [layout.PY_ROOT]
        sys.modules["mmc"] = package
    spec = importlib.util.spec_from_file_location(f"mmc.{name}", layout.py(name))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmc.{name}"] = module
    spec.loader.exec_module(module)
    return module


try:
    truncate = _load("truncate")
except Exception as exc:  # noqa: BLE001
    print(f"skipped: package not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

from harness import FAILURES, check, passed

torch.manual_seed(7)
SHAPE = (1, 4, 3, 2, 2)
SIGMAS = torch.linspace(1.0, 0.0, 11)          # ten steps, widths 0.1
NOISE = torch.randn(SHAPE)
CLEAN = torch.randn(SHAPE)
# One velocity per step: the straight line's plus a per-step wobble, so the
# steps disagree and a window that drops some of them changes the answer.
VELOCITIES = [NOISE - CLEAN + 0.2 * torch.randn(SHAPE) for _ in range(10)]


def euler(sigmas, velocities, x, on_step=None):
    """Plain Euler down `sigmas`, reporting each step the way the post-cfg hook sees it."""
    for i in range(len(sigmas) - 1):
        sigma, nxt = float(sigmas[i]), float(sigmas[i + 1])
        v = velocities[i]
        denoised = x - v * sigma
        if on_step is not None:
            on_step(sigma, x, denoised)
        x = x - v * (sigma - nxt)
    return x


def by_hand(guesses, start_sigma=1.0, start=NOISE):
    """The paper's sum over the last `guesses` steps, 0 for all of them."""
    acc, weight = torch.zeros(SHAPE), 0.0
    for i in range(10 - guesses if guesses else 0, 10):
        acc = acc + VELOCITIES[i] * 0.1
        weight += 0.1
    return start - acc * (start_sigma / weight)


def close(a, b):
    return torch.allclose(a, b, atol=1e-5)


# ---- the trajectory alone ---------------------------------------------------

def run(guesses):
    trajectory = truncate.Trajectory(guesses)
    end = euler(SIGMAS, VELOCITIES, NOISE,
                lambda sigma, x, d: trajectory.record(sigma, truncate._step_width(sigma, SIGMAS), x, d))
    return trajectory, end


trajectory, end = run(0)
check("every guess averaged is the sampler's own output",
      close(trajectory.finish(end), end), True)
check("...and that output is the straight-line identity",
      close(end, NOISE - sum(v * 0.1 for v in VELOCITIES)), True)

trajectory, end = run(3)
check("the last three guesses are the start minus their velocities' mean",
      close(trajectory.finish(end), by_hand(3)), True)
check("...which is not what the sampler returned", close(trajectory.finish(end), end), False)
check("...and only three are held", len(trajectory.terms), 3)

trajectory, end = run(50)
check("a count past the schedule is every guess", close(trajectory.finish(end), end), True)

trajectory = truncate.Trajectory(3)
check("nothing recorded hands the sampler's output back untouched",
      trajectory.finish(end) is end, True)

# A schedule entered partway — the refine's — is its own trajectory from there:
# the start is the first x it sees and the weights are over that sigma.
partial = SIGMAS[4:]                                   # 0.6 down to 0
trajectory = truncate.Trajectory(3)
start = torch.randn(SHAPE)
end = euler(partial, VELOCITIES[4:], start,
            lambda sigma, x, d: trajectory.record(sigma, truncate._step_width(sigma, partial), x, d))
acc = sum(VELOCITIES[i] * 0.1 for i in range(7, 10))
check("a schedule entered at 0.6 is weighted over 0.6 from the latent it entered with",
      close(trajectory.finish(end), start - acc * (0.6 / 0.3)), True)

# Nested: the picture is redrawn from the window and the sound row is the
# sampler's, exactly.
trajectory = truncate.Trajectory(3)
audio_v = [torch.randn(1, 8, 5) for _ in range(10)]
nested_x = comfy.nested_tensor.NestedTensor([NOISE, torch.randn(1, 8, 5)])
nested_end = euler(SIGMAS, [comfy.nested_tensor.NestedTensor([v, a]) for v, a in zip(VELOCITIES, audio_v)],
                   nested_x,
                   lambda sigma, x, d: trajectory.record(sigma, truncate._step_width(sigma, SIGMAS), x, d))
out = trajectory.finish(nested_end)
check("a nested latent comes back nested", getattr(out, "is_nested", False), True)
check("...its picture from the last three guesses", close(out.unbind()[0], by_hand(3)), True)
check("...and its sound row the sampler's own", out.unbind()[1] is nested_end.unbind()[1], True)

# The sampler's own tensor is never held: the start is a copy.
trajectory = truncate.Trajectory(0)
x = NOISE.clone()
trajectory.record(1.0, 0.1, x, x - VELOCITIES[0])
x.add_(1.0)
check("the recorded start is a copy of the sampler's latent, not the latent",
      close(trajectory.start, NOISE), True)
check("...in float32", trajectory.start.dtype, torch.float32)
half = NOISE.to(torch.bfloat16)
trajectory = truncate.Trajectory(3)
euler(SIGMAS, [v.to(torch.bfloat16) for v in VELOCITIES], half,
      lambda sigma, x, d: trajectory.record(sigma, truncate._step_width(sigma, SIGMAS), x, d))
check("a bf16 run comes back in the sampler's dtype", trajectory.finish(half).dtype, torch.bfloat16)

check("a sigma between two steps snaps to the nearest one", truncate._step_width(0.55, SIGMAS) > 0, True)
check("the last sigma has no width", truncate._step_width(0.0, SIGMAS), 0.0)


# ---- the patch on a stand-in ModelPatcher ---------------------------------------

class FakePatcher:
    """The three things `_patch` asks of a ModelPatcher, and a way to read them back."""

    def __init__(self):
        self.post_cfg = []
        self.wrappers = {}

    def clone(self):
        c = FakePatcher()
        c.post_cfg = list(self.post_cfg)
        c.wrappers = {k: dict(v) for k, v in self.wrappers.items()}
        return c

    def set_model_sampler_post_cfg_function(self, fn, disable_cfg1_optimization=False):
        self.post_cfg.append(fn)

    def add_wrapper_with_key(self, kind, key, fn):
        self.wrappers.setdefault(kind, {}).setdefault(key, []).append(fn)


def sitting(patched, sigmas, velocities, x):
    """One sampler call through the patch: the wrapper round an Euler loop that
    reports each step to the post-cfg hooks the way `cfg_function` does."""
    (wrapper,) = patched.wrappers[comfy.patcher_extension.WrappersMP.SAMPLER_SAMPLE][truncate.TRUNCATE_NODE]
    options = {"transformer_options": {"sample_sigmas": sigmas}}

    def report(sigma, x, denoised):
        args = {"denoised": denoised, "input": x, "sigma": torch.tensor([sigma]),
                "model_options": options}
        for fn in patched.post_cfg:
            args["denoised"] = fn(args)

    def executor(guider, sigmas, *rest):
        return euler(sigmas, velocities, x, report)

    return wrapper(executor, None, sigmas, {}, None, None, None, None, False)


base = FakePatcher()
patched = truncate._patch(base, 3)
check("the patch clones rather than patching the model it was handed",
      (base.post_cfg, base.wrappers), ([], {}))
check("one sitting down the whole schedule is the last three guesses' average",
      close(sitting(patched, SIGMAS, VELOCITIES, NOISE), by_hand(3)), True)
check("...and the trajectory is closed behind it", truncate._open, None)

# The lead-in: three opening steps on one patched model, the rest on another,
# the second starting on the sigma the first stopped at. One sum.
opening_model = truncate._patch(FakePatcher(), 3)
rest_model = truncate._patch(FakePatcher(), 3)
partway = sitting(opening_model, SIGMAS[:4], VELOCITIES[:3], NOISE)
check("a sitting that stops short of zero returns the sampler's own latent",
      close(partway, NOISE - sum(v * 0.1 for v in VELOCITIES[:3])), True)
check("...and leaves the trajectory open at the sigma it stopped on",
      (truncate._open is not None, round(truncate._open.last, 6)), (True, 0.7))
finished = sitting(rest_model, SIGMAS[3:], VELOCITIES[3:], partway)
check("the second sitting finishes the one sum from the first's start",
      close(finished, by_hand(3)), True)
check("...and closes it", truncate._open, None)

# A sitting that does not start where the last one stopped is a new schedule —
# a restore pass after an interrupted lead-in must not inherit its half-sum.
sitting(opening_model, SIGMAS[:4], VELOCITIES[:3], NOISE)
own = sitting(rest_model, SIGMAS[4:], VELOCITIES[4:], NOISE)
check("a sitting starting elsewhere is its own trajectory",
      close(own, NOISE - acc * (0.6 / 0.3)), True)

passed("all truncation tests passed")
