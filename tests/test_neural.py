"""The DLSS 5 refiner's decisions, on a machine that has no weights.

    python3 tests/test_neural.py

`neural.py` is written so the pack runs whether or not the weights exist, and
this suite is what keeps that true: it loads the module with no ComfyUI and no
torch and asks every question a surface asks before running —
what a request reads as, what a frame costs, whether a DLL is the right one,
what is missing and how it is said. Nothing here loads weights, because the
weights are the one thing the pack is not allowed to have.

The bench arithmetic (`upscale.target` with no scale dial) is pinned in
`test_bench.py`; the graphs are `test_neural_graph.py`.
"""

import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness
import layout
from harness import FAILURES, check

try:
    import numpy as np
except Exception as exc:  # noqa: BLE001
    harness.skip(f"numpy not importable ({type(exc).__name__}: {exc})")

pkg = layout.load("outputs", "settings", "neural")
neural, settings = pkg.neural, pkg.settings

# ---- the request ---------------------------------------------------------------

off = neural.Request.of({})
check("no block is an off request", bool(off), False)
check("...at the defaults", off.as_dict(), neural.DEFAULTS)
check("a blob with the block off is off", bool(neural.Request.of({"neural": {"on": False}})), False)
check("garbage where the block should be is off", bool(neural.Request.of({"neural": "yes"})), False)

on = neural.Request.of({"neural": {"on": True, "profile": "cinematic", "scale": 2,
                                   "detail": 1.5, "colour": 0.5, "intensity": 0.8,
                                   "precision": "fast"}})
check("a full block reads back", on.as_dict(),
      {"on": True, "profile": "cinematic", "scale": 2.0, "detail": 1.5, "colour": 0.5,
       "intensity": 0.8, "precision": "fast"})
check("a missing field is its default",
      neural.Request.of({"neural": {"on": True}}).as_dict(), {**neural.DEFAULTS, "on": True})

clamped = neural.Request(on=True, profile="vivid", scale=9, detail=-1, colour="lots",
                         intensity=float("nan"), precision="int4")
check("an unknown profile is the standard one", clamped.profile, "standard")
check("the scale is clamped to upstream's range", clamped.scale, neural.MAX_SCALE)
check("negative detail is none", clamped.detail, 0.0)
check("a word where a number goes is the default", clamped.colour, neural.DEFAULT_COLOUR)
check("NaN is the default too", clamped.intensity, neural.DEFAULT_INTENSITY)
check("an unknown precision is the reference one", clamped.precision, "reference")
check("only a real true is on — a string is not", neural.Request(on="yes").on, False)
check("two equal requests compare equal", neural.Request(on=True), neural.Request(on=True))

# ---- the memory arithmetic ------------------------------------------------------
#
# Upstream's rule: at least 320 a side, on a 64 grid, about 1 GB a megapixel of
# that at float32. The numbers below are the README's own worked examples.

check("a small frame is padded to the network's floor", neural.network_extent(256, 256), (320, 320))
check("1080p lands on the 64 grid", neural.network_extent(1920, 1080), (1920, 1088))
check("the scale multiplies the frame before the grid", neural.network_extent(640, 360, 2), (1280, 768))
check("1080p is about two gigabytes", neural.estimate_gb(1920, 1080), 2.09)
check("...half of that fast", neural.estimate_gb(1920, 1080, precision="fast"), 1.04)
# Not exactly four: the small frame pads 540 up to 576 and the large one 1080
# up to 1088, so the grid eats some of the square.
ratio = neural.estimate_gb(960, 540, 2) / neural.estimate_gb(960, 540)
check("scale 2 is about four times", 3.5 <= ratio <= 4.0, True)
shaped = neural.estimate(1024, 576, 1.5, "fast")
check("the estimate names its inputs", (shaped["width"], shaped["height"], shaped["scale"], shaped["precision"]),
      (1024, 576, 1.5, "fast"))
check("...and the network's extent", shaped["network"], [1536, 896])

# ---- the mask ------------------------------------------------------------------

check("no mask is no mask", neural.control_mask(None, 4, 4), None)
plain = neural.control_mask(np.ones((4, 6), dtype=np.float32), 4, 6)
check("a mask becomes three identical channels", (plain.shape, float(plain.min()), float(plain.max())),
      ((4, 6, 3), 1.0, 1.0))
batched = neural.control_mask(np.zeros((2, 4, 6), dtype=np.float32), 4, 6)
check("a batch of masks takes the first", batched.shape, (4, 6, 3))
resized = neural.control_mask(np.ones((2, 3), dtype=np.float32) * 0.5, 8, 12)
check("a mask at another size is resampled to the frame", (resized.shape, round(float(resized.mean()), 2)),
      ((8, 12, 3), 0.5))
check("values are clamped into 0..1", float(neural.control_mask(np.full((2, 2), 7.0), 2, 2).max()), 1.0)

as_float = neural.as_float(np.full((2, 2, 3), 255, dtype=np.uint8))
check("uint8 frames come in as unit floats", (as_float.dtype, float(as_float.max())), (np.float32, 1.0))
check("an alpha channel is dropped", neural.as_float(np.zeros((2, 2, 4), dtype=np.float32)).shape, (2, 2, 3))

# ---- what is missing, and how it is said ---------------------------------------
#
# This machine has no `mlxdlss`, which is the state most machines are in, and
# every sentence below is one somebody will read.

state = neural.status()
check("no weights, so nothing is ready", state["ready"], False)
check("what is needed names the DLL and the settings page",
      neural.DLL_NAME in state["needs"] and "settings page" in state["needs"], True)
check("...and says nothing is downloaded", "nothing is downloaded" in state["needs"].lower(), True)
check("the status carries the vendored commit, read without torch",
      (state["upstream"], len(state["commit"])), (neural.UPSTREAM, 40))
check("the status names the DLL by version and hash",
      (state["dll_version"], state["dll_sha256"]), (neural.DLL_VERSION, neural.DLL_SHA256))

try:
    neural.require()
    FAILURES.append("require() let a machine without the package through")
except neural.NeuralError as exc:
    check("require() says it plainly", "not ready" in str(exc), True)

# The bench's entry, with this machine's answer in it.
entry = neural.bench_entry()
check("the bench entry is not ready here", entry["ready"], False)
check("...and carries the sentence", entry["needs"], state["needs"])
check("the bench entry has no scale dial", "scale" in [spec["key"] for spec in entry["params"]], False)
check("the bench entry's dials are copies", entry["params"] is not neural.BENCH["params"], True)
check("the 'then refine' switch is a switch", neural.AFTER_SWITCH["kind"], "switch")

# ---- the DLL check --------------------------------------------------------------

check("no path is no file", neural.check_dll("")["reason"], "no file given")
check("a path to nothing says so", neural.check_dll("/nowhere/nvngx_dlssnr.dll")["exists"], False)
with tempfile.TemporaryDirectory() as directory:
    wrong = os.path.join(directory, "nvngx_dlssnr.dll")
    with open(wrong, "wb") as handle:
        handle.write(b"not the driver")
    checked = neural.check_dll(wrong)
    check("a file that is not the build hashes and is refused",
          (checked["exists"], checked["supported"], checked["sha256"]),
          (True, False, hashlib.sha256(b"not the driver").hexdigest()))
    check("...naming the build it wanted", neural.DLL_VERSION in checked["reason"], True)
    check("...and that this file has no version at all", "no version" in checked["reason"], True)
    check("the name means nothing: only the bytes do", checked["supported"] or checked["verified"], False)

    try:
        neural.extract(wrong)
        FAILURES.append("extract ran over a file that is not the build")
    except neural.NeuralError as exc:
        check("extraction refuses a file that is not the build, before touching it",
              "not the supported build" in str(exc), True)

# ---- the settings key ------------------------------------------------------------

check("the DLL path is a setting", settings.DEFAULTS["neural_dll"], "")
check("a path is stored trimmed", settings.clean({"neural_dll": "  ~/dlss/nvngx_dlssnr.dll "})["neural_dll"],
      "~/dlss/nvngx_dlssnr.dll")
try:
    settings.clean({"neural_dll": 7})
    FAILURES.append("a number was accepted as a path")
except ValueError as exc:
    check("a number is refused as a path", "path" in str(exc), True)

# ---- the request from the bench's dials -------------------------------------------

request = neural.request_from_values({"profile": "natural", "processing": 1.5, "detail": 2,
                                      "colour": 0.25, "intensity": 0.9, "precision": "fast"})
check("bench dials become a request", request.as_dict(),
      {"on": True, "profile": "natural", "scale": 1.5, "detail": 2.0, "colour": 0.25,
       "intensity": 0.9, "precision": "fast"})
check("absent dials are the defaults", neural.request_from_values({}).as_dict(),
      {**neural.DEFAULTS, "on": True})
