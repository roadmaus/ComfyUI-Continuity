"""The refiner's plumbing, run end to end over a fake of the vendored `mlxdlss`.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_neural_fake.py

No machine this suite runs on has the weights — they are the one thing the pack
may not carry — so the upstream package is stood in for by a fake that answers
the same calls: a pipeline whose `enhance` brightens by a known amount and a
temporal session that counts the frames and scene cuts it saw. What is then
provable is everything of ours around the model: that a frame goes in as unit
floats and comes back clipped, that a mask reaches the call and refuses a scale,
that a clip on the bench runs through one session across its chunks, that the
"then refine" switch runs after the fit at the target size, and that releasing
puts the graph on the CPU and waking it puts it back.

Skips itself if ComfyUI cannot be imported — `folder_paths` decides where the
weights live, and the bench reads its dials off it.
"""

import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness
import layout
from harness import FAILURES, check

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)
try:
    import numpy as np

    import folder_paths
except Exception as exc:  # noqa: BLE001
    harness.skip(f"ComfyUI not importable ({type(exc).__name__}: {exc})")


# ---- the fake package --------------------------------------------------------

LIFT = 0.1
CALLS = []


class _Model:
    def __init__(self):
        self.where = "cpu"

    def to(self, device):
        self.where = str(device)
        return self


class FakePipeline:
    def __init__(self, path, device="auto", precision="reference"):
        self.path, self.precision = path, precision
        self.device = "fake-gpu"
        self.model = _Model().to(self.device)

    @classmethod
    def from_safetensors(cls, path, *, device="auto", precision="reference"):
        return cls(path, device, precision)

    def enhance(self, image, **options):
        CALLS.append(("enhance", image.shape, dict(options)))
        out = np.clip(image + LIFT, 0, 1)
        if options.get("control_mask") is not None:
            blend = options["control_mask"][..., :1]
            out = image + blend * (out - image)
        return types.SimpleNamespace(image=out.astype(np.float32))


class FakeOptions:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeSession:
    def __init__(self, pipeline, *, options=None, motion="flow"):
        self.pipeline, self.options, self.motion = pipeline, options, motion
        self.frame_index = 0
        self.scene_cuts = 0
        self.resets = 0
        self.seen = []

    def reset(self):
        self.resets += 1
        self.frame_index = 0

    def process(self, frame, *, motion=None, control_mask=None):
        self.seen.append(frame.shape)
        self.frame_index += 1
        return np.clip(frame + LIFT, 0, 1).astype(np.float32)


# Stood in *under the package's own name*: `neural.py` imports the vendored
# copy relatively, so the fake has to be where `mmcpkg.mlxdlss` would resolve.
fake = types.ModuleType("mmcpkg.mlxdlss")
fake.NeuralRenderingPipeline = FakePipeline
fake.TemporalSession = FakeSession
fake.TemporalOptions = FakeOptions
sys.modules["mmcpkg.mlxdlss"] = fake

pkg = layout.load("settings", "bench", "outputs", "neural", "control", "upscale")
neural, upscale, bench = pkg.neural, pkg.upscale, pkg.bench

# A weights file where the pack looks for one, in a models tree of our own.
models = tempfile.mkdtemp()
folder_paths.models_dir = models
os.makedirs(os.path.join(models, neural.FOLDER))
with open(os.path.join(models, neural.FOLDER, neural.WEIGHTS_FILE), "wb") as handle:
    handle.write(b"fake")

state = neural.status()
check("with a weights file, the refiner is ready", state["ready"], True)
check("...and nothing is missing", state["needs"], None)
check("the folder is registered with ComfyUI", neural.FOLDER in folder_paths.folder_names_and_paths, True)


# ---- one frame ------------------------------------------------------------------

frame = np.full((40, 60, 3), 100, dtype=np.uint8)
request = neural.Request(on=True, profile="natural", scale=1, detail=2, colour=0.5, intensity=0.9,
                         precision="fast")
out = neural.refine_frame(frame, request, frame_index=7)
check("a frame comes back float32 in 0..1", (out.dtype, out.shape), (np.float32, (40, 60, 3)))
check("...lifted by the model", round(float(out.mean()) - 100 / 255, 3), round(LIFT, 3))
_, shape, options = CALLS[-1]
check("the model saw unit floats at the frame's size", shape, (40, 60, 3))
check("the request's dials reached the call",
      {key: options[key] for key in ("profile", "processing_scale", "detail_strength",
                                     "colour_strength", "intensity", "frame_index")},
      {"profile": "natural", "processing_scale": 1.0, "detail_strength": 2.0,
       "colour_strength": 0.5, "intensity": 0.9, "frame_index": 7})
check("the pipeline was built at the request's precision",
      neural._HELD["pipeline"].precision, "fast")

# A mask: half the frame untouched.
mask = np.zeros((40, 60), dtype=np.float32)
mask[:, 30:] = 1
masked = neural.refine_frame(frame, request, mask=mask)
check("where the mask is zero the source is untouched",
      float(np.abs(masked[:, :30] - 100 / 255).max()) < 1e-6, True)
check("where it is one the model's answer stands",
      round(float(masked[:, 30:].mean()) - 100 / 255, 3), round(LIFT, 3))
try:
    neural.refine_frame(frame, neural.Request(on=True, scale=2), mask=mask)
    FAILURES.append("a mask at scale 2 was accepted")
except neural.NeuralError as exc:
    check("a mask refuses a processing scale", "scale at 1" in str(exc), True)

# The hold: one pipeline per (weights, precision); release parks it on the CPU.
first = neural._HELD["pipeline"]
neural.refine_frame(frame, request)
check("the same pipeline serves the next call", neural._HELD["pipeline"] is first, True)
neural.release()
check("release puts the graph on the CPU", first.model.where, "cpu")
neural.refine_frame(frame, request)
check("...and the next call wakes it", first.model.where, "fake-gpu")
neural.refine_frame(frame, neural.Request(on=True, precision="reference"))
check("another precision is another pipeline", neural._HELD["pipeline"] is not first, True)


# ---- a sequence --------------------------------------------------------------------

sequence = neural.Sequence(request, frame_index=3)
check("the session starts at the asked frame index", sequence.session.frame_index, 3)
for _ in range(4):
    sequence.process(frame)
check("four frames went through one session", len(sequence.session.seen), 4)
check("the options carried the request",
      (sequence.session.options.profile, sequence.session.options.detail_strength,
       sequence.session.options.colour_strength, sequence.session.options.intensity),
      ("natural", 2.0, 0.5, 0.9))
check("the motion is upstream's flow where OpenCV imports, else zero",
      sequence.motion in ("flow", "zero"), True)


# ---- the bench -----------------------------------------------------------------

values = bench.values(upscale.BY_ID["neural"], {"detail": "1.5", "temporal": "1"}, upscale.UpscaleError)
check("the entry's dials clamp and default like every bench's",
      (values["profile"], values["processing"], values["detail"], values["temporal"]),
      ("standard", 1.0, 1.5, True))
check("the entry keeps the size it is given", upscale.target(60, 40, values), (60, 40))

frames = [frame, frame, frame]
refiner = upscale.Refiner("neural", values, clip=True)
check("a clip on the bench gets one session", refiner.sequence is not None, True)
done = upscale.enlarge_many(frames[:2], "neural", values, refiner) + \
       upscale.enlarge_many(frames[2:], "neural", values, refiner)
check("three frames over two chunks went through the one session",
      len(refiner.sequence.session.seen), 3)
check("...and came back uint8 at the size they were", (done[0].dtype, done[0].shape), (np.uint8, (40, 60, 3)))
check("...lifted", int(done[0][0, 0, 0]) - 100, round(LIFT * 255))

still = upscale.Refiner("neural", values, clip=False)
check("a still gets no session", still.sequence is None, True)
upscale.enlarge_many([frame], "neural", values, still)
check("...and is refined on its own, seeded by its index", CALLS[-1][2]["frame_index"], 0)

# The "then refine" switch on Sharpen: the refiner runs after the fit, at the
# target size, at the entry's defaults. Sharpen's own model is stubbed out —
# what is under test is the order and the size, not the GAN.
upscale._sharpen = lambda picture, values: np.asarray(
    __import__("PIL.Image", fromlist=["Image"]).fromarray(picture).resize(
        upscale.target(picture.shape[1], picture.shape[0], values)))
after = bench.values(dict(upscale.BY_ID["sharpen"], params=tuple(
    spec for spec in upscale.BY_ID["sharpen"]["params"] if spec["kind"] != "choice")),
    {"scale": 2, "neural": "1"}, upscale.UpscaleError)
grown = upscale.enlarge_many([frame], "sharpen", after)
check("Sharpen with the switch comes back at the target size", grown[0].shape, (80, 120, 3))
check("...refined there", CALLS[-1][1], (80, 120, 3))
check("...at the entry's defaults", CALLS[-1][2]["profile"], "standard")
check("...and lifted", int(grown[0][0, 0, 0]) - 100, round(LIFT * 255))
plain = bench.values(dict(upscale.BY_ID["sharpen"], params=tuple(
    spec for spec in upscale.BY_ID["sharpen"]["params"] if spec["kind"] != "choice")),
    {"scale": 2}, upscale.UpscaleError)
calls_before = len(CALLS)
upscale.enlarge_many([frame], "sharpen", plain)
check("without the switch the refiner never runs", len(CALLS), calls_before)

# The catalogue, with the refiner ready: the switch rides on both upscalers.
listed = {entry["id"]: entry for entry in upscale.catalogue()["backends"]}
check("the entry is ready", listed["neural"]["ready"], True)
check("the switch rides on Sharpen", "neural" in [spec["key"] for spec in listed["sharpen"]["params"]], True)
check("...and on Restore", "neural" in [spec["key"] for spec in listed["restore"]["params"]], True)
