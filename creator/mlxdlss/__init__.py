"""The DLSS 5 neural renderer's PyTorch path, vendored from MLX-DLSS.

Upstream: <https://github.com/iamwavecut/MLX-DLSS>, Apache-2.0,
revision `7debaaf` (2026-09-05). Its LICENSE and NOTICE sit beside this file.
Every line in the other modules here is upstream's; `tools/vendor_mlxdlss.py`
copies them and holds any local edit as a patch.

**Why this is copied and not installed.** The first version of the refiner
asked the user to `pip install` the port from a git URL, and that was the
wrong shape for what it is: the port's Python package is four hundred
kilobytes of pure Python whose runtime dependencies — numpy, torch,
safetensors, Pillow — every ComfyUI already has. Asking for a second install
step bought nothing except a second thing to go wrong, on top of the one step
that genuinely cannot be taken away from the user: finding their own copy of
NVIDIA's DLL. So the code travels with the pack, the way `h3lora/` does, and
the DLL stays the user's.

**What is here, and what is not.** The inference path (`features`,
`composition`, `model`, `pipeline`, `temporal`) and the two modules that turn
a DLL into the logical safetensors the pipeline loads (`extract_dlssnr_weights`,
`unpack_dlssnr_weights`). Not here: the web front end, the video CLI, frame
generation, the Metal packager and the Core ML converter — upstream's product
and its other backends, none of which this pack runs.

**Nothing of NVIDIA's is in this directory.** `weight_spec.json` is the
*shape* of the weights — tensor names and dimensions — which the loader
validates a file against; the values come out of the user's DLL on their own
machine (`neural.extract`).

Imported lazily by `neural.py`: `model.py` imports torch at module level, and
`neural` is read by the compilers, which the pure test suites load with no
torch at all.
"""

# The upstream commit this copy was taken from. Stamped by the vendoring script.
REVISION = "7debaaf28c8f3b789e0d95cc06abd9796da00170"

from .extract_dlssnr_weights import extract_dll, pe_file_version  # noqa: E402
from .pipeline import (EnhanceResult, NeuralRenderingPipeline,  # noqa: E402
                       NeuralRenderingSession, load_weights, resolve_device)
from .temporal import TemporalOptions, TemporalSession  # noqa: E402
from .unpack_dlssnr_weights import convert  # noqa: E402

__all__ = [
    "REVISION",
    "EnhanceResult", "NeuralRenderingPipeline", "NeuralRenderingSession",
    "load_weights", "resolve_device",
    "TemporalOptions", "TemporalSession",
    "extract_dll", "pe_file_version", "convert",
]
