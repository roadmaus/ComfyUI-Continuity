"""The vendored MLX-DLSS copy imports, and its graph runs end to end without weights.

    <comfy-venv>/bin/python3 tests/test_mlxdlss_vendor.py

`creator/mlxdlss/` is upstream's code, copied at a pin. What this suite pins is
that the copy is whole — every module the hand-written `__init__` re-exports is
there and imports on this interpreter — and that the pieces `neural.py` calls
behave as upstream documents them: the network's extent rule, the feature
layout, the head composition, the temporal session with a stand-in network.
No weights are loaded; the one thing checked about the loader is that it
refuses a file that is not the logical format.

Skips itself if torch is not importable — the model module needs it at import.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness
import layout
from harness import FAILURES, check

try:
    import numpy as np
    import torch  # noqa: F401
except Exception as exc:  # noqa: BLE001
    harness.skip(f"torch not importable ({type(exc).__name__}: {exc})")

pkg = layout.load("outputs", "settings", "neural", "mlxdlss")
port, neural = pkg.mlxdlss, pkg.neural

check("the copy is stamped with a full commit", len(port.REVISION), 40)
check("neural.py reads the same stamp without importing the copy",
      neural.upstream_commit(), port.REVISION)
for name in ("LICENSE", "NOTICE", "weight_spec.json"):
    check(f"{name} travels with the copy",
          os.path.isfile(os.path.join(layout.PY_ROOT, "mlxdlss", name)), True)

# ---- the extent rule, both sides ------------------------------------------------

from_port = port.pipeline.NetworkGeometry.vendor_aligned(1920, 1080)
check("neural.network_extent mirrors upstream's vendor alignment",
      neural.network_extent(1920, 1080), (from_port.network_width, from_port.network_height))
small = port.pipeline.NetworkGeometry.vendor_aligned(100, 60)
check("...including the 320 floor", (small.network_width, small.network_height),
      neural.network_extent(100, 60))

# ---- features and composition ----------------------------------------------------

image = np.random.default_rng(1).random((64, 96, 3), dtype=np.float32)
geometry = port.pipeline.NetworkGeometry.vendor_aligned(96, 64)
features = port.pipeline.make_features(image, frame_index=0, geometry=geometry)
check("features are the network's extent by 16 channels",
      features.shape, (geometry.network_height, geometry.network_width, 16))
check("channel 3 is the constant one", float(features[..., 3].min()), 1.0)
check("the colour sits in 4-6 scaled from half", float(np.abs(features[:64, :96, 4:7] - features[:64, :96, 7:10]).max()), 0.0)

zero_head = np.zeros((64, 96, 4), dtype=np.float32)
composed = port.pipeline.compose_head(zero_head, image)
check("a zero head composes to the input", float(np.abs(composed - image).max()), 0.0)
mask = np.zeros((64, 96, 3), dtype=np.float32)
lift = np.full((64, 96, 4), 1.0, dtype=np.float32)
masked = port.pipeline.compose_head(lift, image, control_mask=mask)
check("a zero control mask leaves the input alone whatever the head says",
      float(np.abs(masked - image).max()), 0.0)
detail = port.pipeline.compose_detail(image, image, detail_strength=2.0, colour_strength=0.5)
check("no change composes to no change", float(np.abs(detail - image).max()) < 1e-6, True)


# ---- the temporal session over a stand-in network ---------------------------------

class ZeroNetwork:
    """`run_features` answering a zero head: predicted = input, blend from the logit."""

    device = "cpu"

    def run_features(self, features):
        return np.zeros((features.shape[0], features.shape[1], 4), dtype=np.float32)


session = port.TemporalSession(ZeroNetwork(), options=port.TemporalOptions(), motion="zero")
first = session.process(image)
check("the first frame through the session is the input (zero head)",
      float(np.abs(first - image).max()) < 1e-5, True)
second = session.process(image)
check("the second frame is float32 at the frame's size", (second.dtype, second.shape), (np.float32, (64, 96, 3)))
check("a static scene through a zero head stays put", float(np.abs(second - image).max()) < 1e-3, True)
check("the frame index advanced", session.frame_index, 2)
cut = np.ones_like(image)
session.process(cut)
check("a luma jump is a scene cut", session.scene_cuts, 1)

# ---- the loader refuses what it should ---------------------------------------------

with tempfile.TemporaryDirectory() as directory:
    bogus = os.path.join(directory, "weights.safetensors")
    from safetensors.numpy import save_file

    save_file({"x": np.zeros((2,), dtype=np.float32)}, bogus, metadata={"format": "nothing"})
    try:
        port.load_weights(bogus)
        FAILURES.append("a file of the wrong format loaded")
    except ValueError as exc:
        check("the loader names the format it wanted", "dlssnr-logical" in str(exc), True)

    import pathlib

    fake_dll = os.path.join(directory, "nvngx_dlssnr.dll")
    with open(fake_dll, "wb") as handle:
        handle.write(b"MZ" + b"\0" * 100)
    try:
        port.extract_dll(pathlib.Path(fake_dll), pathlib.Path(directory, "packed.safetensors"))
        FAILURES.append("a stub DLL extracted")
    except Exception as exc:  # noqa: BLE001
        check("a stub DLL is refused with a sentence", bool(str(exc)), True)
