"""That a render previews on an install whose previews are switched off.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_livepreview.py

`livepreview.py` is the pack's own previewer, emitted wherever KJNodes is not
installed. Its whole reason to exist is that core's previewer is gated on
`--preview-method`, which ships as `none`, while the sampler's step callback
runs regardless — so this suite pins that claim first, with the preview method
set to none, and then what the wrapper does with the callback it is handed:

- every step's x0 reaches the wire as a picture, drawn through the latent
  format's own latent2rgb factors (core's real H3, LTX and Flux formats),
- a video latent is drawn across its whole clip and a still as one frame,
- LTX guide frames are cropped and an AV latent's audio half is never drawn,
- the sampler's own callback still runs, with the x0 it was always given,
- core's previewer is silenced while ours samples and restored after, even
  when the sampler raises,
- and the frame names the node sampling *now*, not the one that built it.

Nothing is sampled; the executor is a stand-in that calls the callback the way
`KSAMPLER` does. Skips itself without torch and core.
"""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)
sys.argv = ["main.py", "--preview-method", "none"]

try:
    import torch
    from PIL import Image

    import comfy.latent_formats as formats
    import comfy.nested_tensor
    import latent_preview
    from comfy.cli_args import LatentPreviewMethod, args
except Exception as exc:  # noqa: BLE001
    print(f"skipped: needs torch and ComfyUI ({type(exc).__name__}: {exc})")
    sys.exit(0)

sys.path.insert(0, os.path.join(ROOT, "tests"))
from harness import FAILURES, check, passed  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "mmc_livepreview", os.path.join(ROOT, "creator", "livepreview.py"))
lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lp)

# ---- the premise ------------------------------------------------------------

check("this install's previews are off, as a fresh one's are",
      args.preview_method, LatentPreviewMethod.NoPreviews)
check("so core draws nothing for an H3 latent",
      latent_preview.get_previewer("cpu", formats.MiniMaxH3Video()), None)

# ---- decoding ---------------------------------------------------------------

h3 = formats.MiniMaxH3Video()
clip = torch.randn(1, h3.latent_channels, 9, 6, 8)
frames = lp.latent2rgb(clip, h3, 1024)
check("a video latent is drawn across its whole clip", len(frames), 9)
check("...each frame at the latent's own size", frames[0].size, (8, 6))
check("...as RGB pictures", (frames[0].mode, isinstance(frames[0], Image.Image)),
      ("RGB", True))
check("a frame ceiling spreads the frames rather than taking the head",
      len(lp.latent2rgb(clip, h3, 4)), 4)

flux = formats.Flux()
still = lp.latent2rgb(torch.randn(1, flux.latent_channels, 6, 8), flux, 1024)
check("a still latent is one frame", [f.size for f in still], [(8, 6)])


class NoFactors:
    latent_rgb_factors = None


check("a format with no factors draws nothing rather than failing",
      lp.latent2rgb(clip, NoFactors(), 1024), [])

packed = lp.encode(frames, 640, 80, 24.0)
check("a clip goes out as an animated WebP", packed[1], "image/webp")
check("a still goes out as a JPEG", lp.encode(still, 640, 80, 24.0)[1], "image/jpeg")
big = [Image.new("RGB", (2000, 1000))]
check("a frame over the size ceiling is shrunk to it",
      lp.encode(big, 640, 80, 24.0)[2:], (640, 320))
check("nothing to draw is nothing sent", lp.encode([], 640, 80, 24.0), None)

audio = torch.randn(1, 8, 20, 1)
nested = comfy.nested_tensor.NestedTensor([clip, audio])
check("an AV latent's picture half is the one drawn",
      lp.video_part(nested).shape, clip.shape)


class Guider:
    def __init__(self, conds):
        self.conds = conds


guided = torch.randn(1, 128, 7, 4, 5)
idxs = torch.zeros(1, 3, 2 * 4 * 5, 2)          # two guide frames of 4x5 tokens
check("LTX guide frames are counted off the conditioning",
      lp.guide_frames(Guider({"positive": [{"keyframe_idxs": idxs}]}), guided), 2)
check("...and a family with none crops nothing",
      lp.guide_frames(Guider({"positive": [{}]}), guided), 0)
check("...nor does a still", lp.guide_frames(Guider({}), torch.randn(1, 16, 4, 5)), 0)

# ---- the wrapper ------------------------------------------------------------

sent = []
lp._send = sent.append
lp._prompt_id = lambda: "prompt-1"
owner = {"id": "42"}
lp._owner = lambda built: owner["id"] or built


class Executor:
    """`OUTER_SAMPLE`'s executor, reduced to calling the callback per step."""

    def __init__(self, model_format, conds=None, x0=None, fail=False):
        model = types.SimpleNamespace(latent_format=model_format)
        self.class_obj = types.SimpleNamespace(
            model_patcher=types.SimpleNamespace(model=model), conds=conds or {})
        self.x0 = x0
        self.fail = fail
        self.silenced = None

    def __call__(self, noise, latent_image, sampler, sigmas, denoise_mask, callback,
                 disable_pbar, seed, latent_shapes=None):
        # What core's own previewer would hand the progress bar right now.
        self.silenced = latent_preview.Latent2RGBPreviewer(
            h3.latent_rgb_factors).decode_latent_to_preview_image("JPEG", clip)
        steps = int(sigmas.shape[-1]) - 1
        for i in range(steps):
            callback(i, self.x0, self.x0, steps)
        if self.fail:
            raise RuntimeError("out of memory")
        return "sampled"


heard = []


def upstream(step, x0, x, total):
    heard.append((step, x0 is executor.x0, total))


wrapper = lp.PreviewWrapper("7", 640, 80, 24.0, 1024)
executor = Executor(h3, x0=clip)
result = wrapper(executor, None, None, None, torch.linspace(1, 0, 4), None,
                 upstream, False, 0, latent_shapes=[clip.shape])
check("the sampler's result is handed back", result, "sampled")
check("the sampler's own callback runs every step, with its own x0",
      heard, [(0, True, 3), (1, True, 3), (2, True, 3)])
check("the opening message carries the schedule length and no picture",
      (sent[0]["step"], sent[0]["total"], "image" in sent[0]), (0, 3, False))
frames_sent = [m for m in sent if "image" in m]
# The worker drops a frame rather than queue it, so a fast fake sampler may
# outrun it; the last step is the one that must always land.
check("pictures reach the wire", len(frames_sent) >= 1, True)
check("...the last step's among them", frames_sent[-1]["step"], 3)
check("...as an animated clip at the family's rate",
      (frames_sent[-1]["mime"], frames_sent[-1]["fps"]), ("image/webp", 24.0))
check("...named for the node sampling now and this prompt",
      {(m["node_id"], m["prompt_id"]) for m in sent}, {("42", "prompt-1")})
check("core's own picture was silenced while ours sampled", executor.silenced, None)
restored = latent_preview.Latent2RGBPreviewer(
    h3.latent_rgb_factors).decode_latent_to_preview_image("JPEG", clip)
check("...and is back afterwards", restored[0], "JPEG")

# A sampler that raises leaves core's previewer as it found it.
sent.clear()
try:
    wrapper(Executor(h3, x0=clip, fail=True), None, None, None, torch.linspace(1, 0, 3),
            None, None, False, 0)
    raised = False
except RuntimeError:
    raised = True
check("a failing sampler's error is not swallowed", raised, True)
check("...and core's previewer is restored after it",
      latent_preview.Latent2RGBPreviewer(h3.latent_rgb_factors)
      .decode_latent_to_preview_image("JPEG", clip)[0], "JPEG")

# With no node executing (nothing on the server's books), the id it was built
# under is the one it uses.
owner["id"] = None
sent.clear()
wrapper(Executor(h3, x0=clip), None, None, None, torch.linspace(1, 0, 2), None,
        None, False, 0)
check("the built id is the fallback", {m["node_id"] for m in sent}, {"7"})

# A preview that cannot be drawn is a missing picture, not a failed render.
sent.clear()
broken = Executor(h3, x0="not a tensor")
check("an undrawable step still samples",
      wrapper(broken, None, None, None, torch.linspace(1, 0, 3), None, None, False, 0),
      "sampled")
check("...and sends no picture", [m for m in sent if "image" in m], [])

passed("a render previews with core's previews off, on every latent it samples")
