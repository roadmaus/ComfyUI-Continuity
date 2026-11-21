"""The keystone: the scene's first latent carried into every continued shot.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_keystone.py

CPU tensors through `creator/keystone.py` and the encoder's masked road; no
model, no VAE, no sampler. What this checks is the contract the sampler and
the restore read: the keystone sits in latent 0 under a held mask, context
noise ramps the rest of the held run from `noise` down toward the join, the
capstone rides beside the latent and never in it, everything the graft
replaced comes back after sampling, and the capstone wrapper tacks a held
step onto the end of every model call from the lock step on — and cuts it off
again.
"""

import os
from pathlib import Path
import sys

import layout
from harness import check, skip

comfy = Path(os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
if not (comfy / "folder_paths.py").is_file():
    skip("set COMFYUI_PATH to a ComfyUI installation")
sys.path.insert(0, str(comfy))
sys.argv = ["test_keystone", "--cpu"]
import comfy.cli_args  # noqa: E402
comfy.cli_args.args.cpu = True
import torch  # noqa: E402
import comfy.nested_tensor  # noqa: E402
import comfy.utils  # noqa: E402

pkg = layout.load("keystone", "encode", package="keystone_contract")
ks, encoder = pkg.keystone, pkg.encode

torch.manual_seed(0)
C, H, W = 24, 30, 42


def av(video, audio=None):
    audio = torch.randn(1, 32, 2, 65) if audio is None else audio
    return comfy.nested_tensor.NestedTensor((video, audio))


# A 39-frame feather is 12 latent steps of a 22-step target, written in by
# the masked road; the scene's first pass is 20 steps.
run = torch.randn(1, C, 12, H, W)
target = {"samples": av(torch.zeros(1, C, 22, H, W))}
masked = encoder._masked_prefix(target, run)
first = torch.randn(1, C, 20, H, W)

check("the masked run is what the graft sees as held",
      ks.held_steps(masked), list(range(12)))

out, note = ks.graft(masked, av(first), capstone=True, noise=1.0)
v, a = out["samples"].unbind()
vm, am = out["noise_mask"].unbind()
check("the keystone is the scene's first latent, in latent 0",
      torch.equal(v[:, :, 0], first[:, :, 0]), True)
check("...held outright", float(vm[:, :, 0].max()), 0.0)
check("the rest of the run is still the run", torch.equal(v[:, :, 1:12], run[:, :, 1:]), True)
check("context noise ramps from 1 at the oldest held step...",
      round(float(vm[0, 0, 1, 0, 0]), 3), 1.0)
check("...down to 0 at the join", float(vm[0, 0, 11, 0, 0]), 0.0)
check("...through the steps between, falling",
      all(float(vm[0, 0, t, 0, 0]) > float(vm[0, 0, t + 1, 0, 0]) for t in range(1, 11)), True)
check("the new frames are still ones", float(vm[:, :, 12:].min()), 1.0)
check("the audio stream and its mask are untouched",
      (torch.equal(a, masked["samples"].unbind()[1]), float(am.min())), (True, 1.0))
check("the capstone is the first pass's last single-frame step",
      torch.equal(out[ks.KEY]["back"], first[:, :, 15:16]), True)
check("...and rides beside the latent, not in it", tuple(v.shape), (1, C, 22, H, W))
check("the originals are latent 0 and the noised steps",
      sorted(out[ks.KEY]["originals"]), list(range(0, 11)))
check("the note says what was done", note.startswith("keystone in latent 0"), True)
check("the masked latent is not written to",
      torch.equal(masked["samples"].unbind()[0][:, :, 0], run[:, :, 0]), True)

# Noise off and no capstone: the keystone alone.
bare, _ = ks.graft(masked, av(first), capstone=False, noise=0.0)
bvm, _ = bare["noise_mask"].unbind()
check("without noise the run stays held outright", float(bvm[:, :, :12].max()), 0.0)
check("without a capstone there is none", bare[ks.KEY]["back"], None)
check("...and only latent 0 to put back", sorted(bare[ks.KEY]["originals"]), [0])

# Standing down: no masked run, another canvas.
plain = {"samples": av(torch.zeros(1, C, 22, H, W))}
same, why = ks.graft(plain, av(first))
check("no masked run, no keystone", same is plain, True)
check("...and says so", "no masked run" in why, True)
wide = torch.randn(1, C, 20, H, W + 2)
same, why = ks.graft(masked, av(wide))
check("a first pass at another canvas stands it down", same is masked, True)

# After sampling: everything the graft replaced comes back.
sampled = {"samples": av(torch.randn(1, C, 22, H, W)), "batch_index": [0]}
restored = ks.restore(sampled, out)
rv, ra = restored["samples"].unbind()
check("latent 0 is the shot's own again", torch.equal(rv[:, :, 0], run[:, :, 0]), True)
check("...and the noised run too", torch.equal(rv[:, :, 1:11], run[:, :, 1:11]), True)
check("...the rest is what was sampled",
      torch.equal(rv[:, :, 11:], sampled["samples"].unbind()[0][:, :, 11:]), True)
check("...the audio as sampled", torch.equal(ra, sampled["samples"].unbind()[1]), True)
check("...other keys ride through", restored.get("batch_index"), [0])
check("a pass without a keystone comes back as it was",
      ks.restore(sampled, plain) is sampled, True)



# ---- the capstone wrapper ---------------------------------------------------

class _Patcher:
    """Just enough of a ModelPatcher for `lock` and `unlock`."""

    def __init__(self, options=None):
        self.model_options = options or {}

    def clone(self):
        return _Patcher({**self.model_options})

    def set_model_unet_function_wrapper(self, fn):
        self.model_options["model_function_wrapper"] = fn


seen = []


def apply_model(x, t, **c):
    seen.append((tuple(x.shape), c.get("latent_shapes"),
                 None if c.get("denoise_mask") is None else tuple(c["denoise_mask"].shape)))
    return x * 2


sigmas = torch.tensor([1.0, 0.9, 0.7, 0.5, 0.3, 0.1, 0.0])
video = torch.randn(1, C, 22, H, W)
audio = torch.randn(1, 32, 2, 65)
x, shapes = comfy.utils.pack_latents([video, audio])
back = first[:, :, 15:16]
wrapped = ks.lock(_Patcher(), back, 3).model_options["model_function_wrapper"]


def call(sigma, model=wrapped, offset_sigmas=sigmas):
    c = {"latent_shapes": shapes, "transformer_options": {"sample_sigmas": offset_sigmas},
         "denoise_mask": torch.zeros(1, 1, 22, H, W)}
    return model(apply_model, {"input": x, "timestep": torch.tensor([sigma]), "c": c})


seen.clear()
early = call(0.7)
check("before the lock step the call goes through untouched", seen[-1][0], tuple(x.shape))
check("...and so does its answer", torch.equal(early, x * 2), True)
late = call(0.5)
check("from the lock step the video is one step longer",
      seen[-1][1][0][2], 23)
check("...the audio keeps its shape", tuple(seen[-1][1][1]), tuple(audio.shape))
check("...the mask holds the tacked step", seen[-1][2], (1, 1, 23, H, W))
check("...and the answer is cut back to the shot", tuple(late.shape), tuple(x.shape))
lv, la = comfy.utils.unpack_latents(late, shapes)
check("...with the shot's own prediction in it", torch.equal(lv, video * 2), True)
check("...and the audio's", torch.equal(la, audio * 2), True)

# A lead-in's second sitting is handed the tail of the schedule: the offset
# puts it back on the whole run's count.
second = ks.lock(_Patcher(), back, 3, offset=2).model_options["model_function_wrapper"]
seen.clear()
call(0.5, model=second, offset_sigmas=sigmas[2:])
check("offset: step 1 of the second sitting is step 3 of the run", seen[-1][1][0][2], 23)
seen.clear()
call(0.7, model=second, offset_sigmas=sigmas[2:])
check("offset: its step 0 is still before the lock", seen[-1][0], tuple(x.shape))

# Installing twice replaces; unlocking unwinds to what was there.
def other(apply_model, args):
    return apply_model(args["input"], args["timestep"], **args["c"])


base = _Patcher({"model_function_wrapper": other})
twice = ks.lock(ks.lock(base, back, 3), back, 5)
check("a second lock replaces the first", twice.model_options["model_function_wrapper"]._prev, other)
check("unlock puts back what was under it",
      ks.unlock(twice).model_options["model_function_wrapper"], other)
check("unlock on a bare model leaves no wrapper",
      "model_function_wrapper" in ks.unlock(ks.lock(_Patcher(), back, 3)).model_options, False)
check("the Ray halves are the same two",
      (ks.ray_install(_Patcher(), back, 3).model_options["model_function_wrapper"]._prev,
       "model_function_wrapper" in ks.ray_remove(ks.ray_install(_Patcher(), back, 3)).model_options),
      (None, False))

# ---- the module ships by value ---------------------------------------------

source = Path(ks.__file__).read_text()
check("the module imports nothing of the pack's (Ray pickles it by value)",
      any(line.lstrip().startswith(("from .", "import .")) for line in source.splitlines()),
      False)

# ---- keystone attention: the re-split, against the softmax written out -------
#
# On one block call: the keystone's share of every token's attention moves to
# S·b·pK/(b·pK + pC) inside the slice S it shares with the carried run, and
# every other key keeps exactly its weight. Checked against attention computed
# the long way with those weights.


class _Layout:
    def __init__(self, text, frames, per, extra):
        self.segments = [(0, text, "text"), (text, text + frames * per, "video"),
                         (text + frames * per, text + frames * per + extra, "audio")]
        self.seq_len = text + frames * per + extra


frames, per = 6, 4
lay = _Layout(5, frames, per, 7)
state = {"anchors": [0], "carried": [1, 2, 3], "frames": frames, "cache": {}, "said": True}
q = torch.randn(1, 2, lay.seq_len, 16)
k = torch.randn(1, 2, lay.seq_len, 16)
v = torch.randn(1, 2, lay.seq_len, 16)
b = 20.0
override = ks._balanced(state, b, 31)
got = override(None, q, k, v, 2, skip_reshape=True,
               transformer_options={"minimax_h3_layout": lay})
weights = torch.softmax((q @ k.transpose(-1, -2)) * 16 ** -0.5, dim=-1)
key_cols = torch.arange(5, 5 + per)
run_cols = torch.arange(5 + per, 5 + 4 * per)
p_key = weights[..., key_cols].sum(-1, keepdim=True)
p_run = weights[..., run_cols].sum(-1, keepdim=True)
new_key = (p_key + p_run) * b * p_key / (b * p_key + p_run)
reweighted = weights.clone()
reweighted[..., key_cols] *= new_key / p_key
reweighted[..., run_cols] *= (p_key + p_run - new_key) / p_run
want = (reweighted @ v).transpose(1, 2).reshape(1, lay.seq_len, 32)
check("keystone attention is the re-split softmax, exactly",
      torch.allclose(got, want, atol=1e-4), True)
check("...every row still sums to one", torch.allclose(reweighted.sum(-1), torch.ones(1), atol=1e-5),
      True)
outside = torch.cat([torch.arange(0, 5), torch.arange(5 + 4 * per, lay.seq_len)])
check("...and nobody outside the slice gives anything up",
      torch.allclose(reweighted[..., outside], weights[..., outside]), True)
check("the keystone's token rows are the video's first frame",
      state["cache"][(lay.seq_len, "cpu")][0].tolist(), list(range(5, 5 + per)))
called = []
override(lambda *a, **kw: called.append(True) or "plain", q, k, v, 2, skip_reshape=True,
         transformer_options={"minimax_h3_layout": _Layout(5, 5, per, 7)})
check("a sequence the layout does not match goes to the model's own attention", called, [True])
check("held frames off a token-grid mask",
      ks._held_frames(torch.tensor([0.0, 0.2, 0.7, 1.0]).view(1, 1, 4, 1, 1).expand(1, 1, 4, 2, 2), 4),
      [True, True, False, False])
