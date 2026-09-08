"""The DLSS 5 neural refiner: what it is, whether this machine has it, and the
one session every surface shares.

NVIDIA's DLSS 5 "neural rendering" network is a material and detail pass —
skin, hair, fabric, contact shadows, subsurface — recovered from the driver DLL
by `iamwavecut/MLX-DLSS` (Apache-2.0) and run here through its PyTorch backend.
**It is not an upscaler.** Resolution in equals resolution out; upstream
measured DLSS Super Resolution and left it out because without engine motion
vectors it loses to Lanczos. What the network answers is *material response*,
which is why it is a refiner in this pack and sits beside the upscalers rather
than among them.

Four surfaces use it — a pre-stage still, every pass of a video render, the
upscale bench, and a plain IMAGE node — and they all resolve to one pipeline
object held here. `neuralpass.py` is the half that holds pixels and nodes; this
is the half that decides.

**Nothing of NVIDIA's ships with this pack, and that is the whole legal
posture.** The weights live inside `nvngx_dlssnr.dll` (file version 310.8.0.0),
which NVIDIA distributes in its Streamline SDK and with games that carry DLSS 5.
The user supplies their own copy; this module checks its SHA-256 against
upstream's table, runs upstream's extraction code on it *locally*, and writes
the logical safetensors into `models/dlss/`. Nothing is hosted, mirrored,
bundled or downloaded from here — not the DLL, not the weights.

**The port's code is vendored, in `creator/mlxdlss/`** — the inference path
and the two extraction modules, copied at a pinned commit by
`tools/vendor_mlxdlss.py`, with the reasons in that package's own docstring.
It is imported lazily, inside the functions that run it, because its model
module imports torch and this module is read by the compilers, which the pure
test suites load with no torch at all. Without the *weights* the bench's entry
reads as not ready and says why, the pill says so, and a queued render that
asks for the pass fails with a sentence.

**Memory is the setting nobody sees coming.** The network's input is the frame
resampled by the processing scale and padded to a 64-multiple of at least 320,
and the graph costs about 1 GB per megapixel of *that* at float32 — half in
fast precision. The scale multiplies it by its square. `estimate_gb` is what
every surface prints before running, because an out-of-memory three minutes
into a clip is the failure this can predict.

Expect it to be strong on figurative work and weak or odd on flat, graphic or
abstract material: it was trained on game frames with heavy supervision on
skin, hair and fabric. The copy says so.
"""

import hashlib
import logging
import math
import os
import threading

import numpy as np

log = logging.getLogger(__name__)

# Where the vendored code comes from. The commit is stamped into the copy by
# the vendoring script; asked of it rather than written twice.
UPSTREAM = "https://github.com/iamwavecut/MLX-DLSS"

# ComfyUI's model folder the weights live in, and the one file name upstream's
# tool writes. One file, one place: the extraction is deterministic for the one
# supported DLL, so a "which file" dial would be a dial with one answer.
FOLDER = "dlss"
WEIGHTS_FILE = "dlssnr-weights-logical.safetensors"
PACKED_FILE = "dlssnr-weights-packed.safetensors"

# The supported DLL, by content. Upstream's table (`mlxdlss.tools.cli`, which
# is not vendored), copied here so the check needs no torch — the first
# question a user asks is "is this the right file".
DLL_NAME = "nvngx_dlssnr.dll"
DLL_VERSION = "310.8.0.0"
DLL_SHA256 = "ceb6432f6fbdf44d886014bcd47241932bf8b67439feef9bbdd0961436662650"

PROFILES = ("standard", "natural", "cinematic", "neutral")
PRECISIONS = ("reference", "fast")

# The controls, with upstream's ranges and this pack's defaults.
#
# The bounds are narrower than the model accepts, because the width upstream
# exposes is not usable width. `detail` past 2 etches skin and embosses brick,
# and by 8 it puts blue-orange fringes on every lit edge — a stop nobody should
# be able to reach by dragging. `colour` past 2 is the same story in tone. Both
# stop where the bench already stopped, which also settles a dial that used to
# read one range in the popover and another on the bench.
MIN_SCALE, MAX_SCALE, DEFAULT_SCALE = 1.0, 4.0, 1.0
MIN_DETAIL, MAX_DETAIL = 0.0, 4.0
MIN_COLOUR, MAX_COLOUR = 0.0, 2.0
MIN_INTENSITY, MAX_INTENSITY, DEFAULT_INTENSITY = 0.0, 1.0, 1.0
DEFAULT_PROFILE = "standard"
DEFAULT_PRECISION = "reference"

# What each style preset opens at, measured rather than assumed.
#
# The model's own answer is 1 on both strengths, and that is what this shipped
# with. It was wrong on `colour`: the low-frequency half is a grade, and at 1 it
# darkens skin, flattens knitwear and muddies brick on every source tried —
# a tone change nobody asked the refiner for. At 0 the tone is left alone and
# the material work survives intact, so 0 is where every preset starts.
#
# `detail` then differs by preset only because the presets sit at different
# style indices and so arrive at the same place from different distances:
# natural is the most eager on skin and wants the least, standard and cinematic
# take a quarter more. Measured on three 1024x1360 Krea 2 stills — a face, a
# still life, a wet street — compared against the source at 1:1.
#
# `neutral` is in the table for completeness and not because the numbers do
# anything there: upstream defines it with local tone *and* local structure at
# zero, so both strengths scale nothing and the pass is within half a level of
# the source at every setting. It is an off switch, not a style.
PROFILE_DEFAULTS = {
    "standard": {"detail": 1.25, "colour": 0.0, "intensity": 1.0},
    "natural": {"detail": 1.0, "colour": 0.0, "intensity": 1.0},
    "cinematic": {"detail": 1.25, "colour": 0.0, "intensity": 1.0},
    "neutral": {"detail": 1.0, "colour": 0.0, "intensity": 1.0},
}

DEFAULT_DETAIL = PROFILE_DEFAULTS[DEFAULT_PROFILE]["detail"]
DEFAULT_COLOUR = PROFILE_DEFAULTS[DEFAULT_PROFILE]["colour"]

# Upstream's measurement: about 1 GB per megapixel of network input at float32
# (1080p 2.0 GB, 2560x2880 5.5 GB), half of that in fast precision. Rounded
# up rather than fitted — this is a warning, not a budget.
GB_PER_MEGAPIXEL = 1.0
FAST_FRACTION = 0.5
# The network's extent rules (`mlxdlss.features`): at least 320 on a side, on
# a 64 grid. Mirrored here so the estimate needs no import.
MIN_EXTENT, EXTENT_MULTIPLE = 320, 64

# The blob's block, and what every field means when it is missing.
DEFAULTS = {
    "on": False,
    "profile": DEFAULT_PROFILE,
    "scale": DEFAULT_SCALE,
    "detail": DEFAULT_DETAIL,
    "colour": DEFAULT_COLOUR,
    "intensity": DEFAULT_INTENSITY,
    "precision": DEFAULT_PRECISION,
}


def defaults_for(profile):
    """The whole block a preset opens at — its own name and strengths, the
    shared rest. An unknown name opens the default preset, as `Request` does."""
    name = profile if profile in PROFILES else DEFAULT_PROFILE
    return {**DEFAULTS, "profile": name, **PROFILE_DEFAULTS[name]}


class NeuralError(RuntimeError):
    """The refiner cannot run here: no package, no weights, or a bad request."""


# ---- is it here -------------------------------------------------------------


def upstream_commit():
    """The commit the vendored copy was taken from, without importing torch."""
    import re

    here = os.path.join(os.path.dirname(__file__), "mlxdlss", "__init__.py")
    try:
        with open(here, "r", encoding="utf-8") as handle:
            found = re.search(r'^REVISION = "([0-9a-f]*)"$', handle.read(), re.M)
    except OSError:
        return ""
    return found.group(1) if found else ""


def weights_dir():
    """`models/dlss/`, registered with ComfyUI so it is listed like any folder."""
    import folder_paths

    path = os.path.join(folder_paths.models_dir, FOLDER)
    if FOLDER not in folder_paths.folder_names_and_paths:
        folder_paths.add_model_folder_path(FOLDER, path, is_default=True)
    return path


def weights_path():
    """Where the logical weights are, or None if they have not been extracted."""
    candidate = os.path.join(weights_dir(), WEIGHTS_FILE)
    return candidate if os.path.isfile(candidate) else None


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_dll(path):
    """Is this the supported DLL? -> {path, exists, sha256, version, supported,
    verified, reason}.

    Two grades of yes. `verified` is the file upstream hashed — the build the
    decoder was checked against bit for bit. `supported` without `verified` is
    the same file version carrying the same weights resource in different
    bytes: the copy this pack was first tested on hashed differently from
    upstream's table (a re-signing or a repack) and decoded to exactly the
    tensors the spec names, so refusing on the hash alone would refuse a
    working file. The loader is the real gate — every tensor's name and shape
    is validated against `weight_spec.json` before anything runs — and the
    verdict says which grade it gave.
    """
    path = os.path.expanduser(str(path or "").strip())
    out = {"path": path, "exists": False, "sha256": None, "version": None,
           "supported": False, "verified": False, "reason": None}
    if not path:
        out["reason"] = "no file given"
        return out
    if not os.path.isfile(path):
        out["reason"] = "there is no file at that path"
        return out
    out["exists"] = True
    try:
        out["sha256"] = sha256_of(path)
    except OSError as exc:
        out["reason"] = f"could not read it: {exc}"
        return out
    if out["sha256"] == DLL_SHA256:
        out["supported"] = out["verified"] = True
        out["version"] = DLL_VERSION
        return out
    out["version"] = _pe_version(path)
    if out["version"] == DLL_VERSION and _has_weights(path):
        out["supported"] = True
        out["reason"] = (f"file version {DLL_VERSION} with the weights resource, "
                         f"but not the bytes upstream verified (SHA-256 "
                         f"{out['sha256'][:12]}… against {DLL_SHA256[:12]}…). "
                         f"The extraction checks every tensor against the "
                         f"spec, so it is safe to run; the result is only "
                         f"as verified as that check.")
        return out
    out["reason"] = (f"not the supported build. This needs {DLL_NAME} file "
                     f"version {DLL_VERSION}; this file "
                     + (f"is version {out['version']}" if out["version"] else
                        "carries no version resource")
                     + f" and hashes to {out['sha256'][:12]}…")
    return out


def _pe_version(path):
    """The DLL's FileVersion as `a.b.c.d`, or None. Upstream's reader, which
    needs numpy and safetensors but no torch."""
    try:
        from .mlxdlss.extract_dlssnr_weights import pe_file_version

        with open(path, "rb") as handle:
            found = pe_file_version(handle.read())
    except Exception:  # noqa: BLE001 — an unreadable header is no version
        return None
    return found.replace(",", ".").replace(" ", "") if found else None


def _has_weights(path):
    """Whether the DLL carries the WEIGHTS_HT resource the extraction reads."""
    try:
        from .mlxdlss.extract_dlssnr_weights import extract_pe_resource

        with open(path, "rb") as handle:
            return len(extract_pe_resource(handle.read())) > 0
    except Exception:  # noqa: BLE001
        return False


def status(dll=None):
    """Everything the settings page and the pills need to say where things stand."""
    present = None
    try:
        present = weights_path()
    except Exception:  # noqa: BLE001 — no folder_paths outside ComfyUI
        pass
    out = {
        "upstream": UPSTREAM,
        "commit": upstream_commit(),
        "weights": present,
        "weights_file": WEIGHTS_FILE,
        "folder": f"models/{FOLDER}",
        "dll_name": DLL_NAME,
        "dll_version": DLL_VERSION,
        "dll_sha256": DLL_SHA256,
        "extracting": _EXTRACTING.locked(),
    }
    out["ready"] = bool(out["weights"])
    out["needs"] = needs(out)
    if dll:
        out["dll"] = check_dll(dll)
    return out


def needs(state=None):
    """The one sentence about what is missing, or None when nothing is.

    Written for the bench's "Not ready. This needs …" line and the pill's
    title, so it names the extraction rather than a file to download — there
    is nothing to download, and saying so is the point.
    """
    state = state or status()
    if not state["weights"]:
        return (f"the weights extracted from your own {DLL_NAME} (file version "
                f"{DLL_VERSION}) into models/{FOLDER}/. The settings page's "
                f"'Neural refiner' section checks the DLL and runs the "
                f"extraction. Nothing is downloaded.")
    return None


def require():
    """Raise a plain sentence if the refiner cannot run on this machine."""
    missing = needs()
    if missing:
        raise NeuralError(f"The neural refiner is not ready: it needs {missing}")


# ---- the extraction ---------------------------------------------------------

# One extraction at a time. It is a few seconds of CPU over a 100 MB file, but
# two presses writing the same safetensors would race on the bytes.
_EXTRACTING = threading.Lock()


def extract(dll):
    """Run upstream's extraction over the user's DLL. -> the weights path.

    Two steps, as upstream's `all` command runs them — the DLL's WEIGHTS_HT
    resource to a packed intermediate, the intermediate decoded to the logical
    tensors — and without the Metal package that `all` builds third: this is
    the CUDA path and the `.dlssmodel` would be 300 MB nobody here loads. The
    packed intermediate is removed afterwards; the logical file is the only
    artefact that stays. In-process, on the caller's thread: it is a few
    seconds of CPU over a 100 MB file and wants no GPU.
    """
    import pathlib

    from . import mlxdlss as port

    checked = check_dll(dll)
    if not checked["supported"]:
        raise NeuralError(checked["reason"])
    if not _EXTRACTING.acquire(blocking=False):
        raise NeuralError("an extraction is already running")
    try:
        directory = weights_dir()
        os.makedirs(directory, exist_ok=True)
        packed = pathlib.Path(directory, PACKED_FILE)
        logical = pathlib.Path(directory, WEIGHTS_FILE)
        for step, run in (("extract", lambda: port.extract_dll(pathlib.Path(checked["path"]), packed)),
                          ("decode", lambda: port.convert(packed, logical))):
            try:
                run()
            except NeuralError:
                raise
            except Exception as exc:  # noqa: BLE001 — upstream's own failure, as a sentence
                raise NeuralError(f"the {step} step failed: {exc}") from exc
        if packed.exists():
            packed.unlink()
        if not os.path.isfile(logical):
            raise NeuralError("the extraction finished without writing the weights")
        log.info("continuity: DLSS 5 weights extracted to %s", logical)
        return logical
    finally:
        _EXTRACTING.release()


# ---- the arithmetic ---------------------------------------------------------


def aligned_extent(extent):
    """The network's side for an image side: at least 320, on the 64 grid."""
    minimum = max(MIN_EXTENT, int(extent))
    return (minimum + EXTENT_MULTIPLE - 1) // EXTENT_MULTIPLE * EXTENT_MULTIPLE


def network_extent(width, height, scale=1.0):
    """(width, height) the network actually runs at for a frame at `scale`."""
    scaled_w = int(round(int(width) * float(scale)))
    scaled_h = int(round(int(height) * float(scale)))
    return aligned_extent(scaled_w), aligned_extent(scaled_h)


def estimate_gb(width, height, scale=1.0, precision=DEFAULT_PRECISION):
    """About how much device memory one frame costs. A warning, not a budget."""
    net_w, net_h = network_extent(width, height, scale)
    gigabytes = (net_w * net_h / 1_000_000) * GB_PER_MEGAPIXEL
    if precision == "fast":
        gigabytes *= FAST_FRACTION
    return round(gigabytes, 2)


def estimate(width, height, scale=1.0, precision=DEFAULT_PRECISION):
    net_w, net_h = network_extent(width, height, scale)
    return {"width": int(width), "height": int(height), "scale": float(scale),
            "precision": precision, "network": [net_w, net_h],
            "gb": estimate_gb(width, height, scale, precision)}


def _number(value, low, high, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if not math.isfinite(number):
        return float(fallback)
    return min(float(high), max(float(low), number))


class Request:
    """The refiner as a piece, a still or a bench asks for it.

    One shape for all four surfaces, read off a blob's `neural` block or built
    by hand. Clamped rather than refused, on the bench's rule: these numbers
    come off controls that already hold the bounds, so anything out of range
    is a stale frontend or a hand edit and takes the nearest honest value.
    """

    __slots__ = ("on", "profile", "scale", "detail", "colour", "intensity", "precision")

    def __init__(self, on=False, profile=DEFAULT_PROFILE, scale=DEFAULT_SCALE,
                 detail=DEFAULT_DETAIL, colour=DEFAULT_COLOUR,
                 intensity=DEFAULT_INTENSITY, precision=DEFAULT_PRECISION):
        # A real boolean only, on both sides of the wire: a hand-edited blob
        # saying "true" does not switch a model pass on by itself.
        self.on = on is True
        self.profile = profile if profile in PROFILES else DEFAULT_PROFILE
        self.scale = _number(scale, MIN_SCALE, MAX_SCALE, DEFAULT_SCALE)
        self.detail = _number(detail, MIN_DETAIL, MAX_DETAIL, DEFAULT_DETAIL)
        self.colour = _number(colour, MIN_COLOUR, MAX_COLOUR, DEFAULT_COLOUR)
        self.intensity = _number(intensity, MIN_INTENSITY, MAX_INTENSITY, DEFAULT_INTENSITY)
        self.precision = precision if precision in PRECISIONS else DEFAULT_PRECISION

    @classmethod
    def of(cls, data):
        """The blob's `neural` block, or an off request where there is none.

        A missing strength falls back to the *preset's* default rather than the
        table's, so a block that names only a profile opens where that profile
        is meant to open. Every block this pack writes carries all seven fields;
        the partial ones are hand edits and blobs from before the presets had
        their own numbers.
        """
        raw = (data or {}).get("neural") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return cls()
        fallback = defaults_for(raw.get("profile"))
        return cls(**{key: raw.get(key, fallback[key]) for key in DEFAULTS})

    def __bool__(self):
        return self.on

    def as_dict(self):
        return {key: getattr(self, key) for key in DEFAULTS}

    def __eq__(self, other):
        return isinstance(other, Request) and self.as_dict() == other.as_dict()

    def __repr__(self):
        return f"Request({self.as_dict()})"


# ---- the session ------------------------------------------------------------
#
# One pipeline, loaded once per (weights, precision), held across calls, and
# put back on the CPU between jobs under the same policy as the benches'
# models (`bench.release`, `jobs.release_all`). Model load is a few hundred MB
# of safetensors and a second or two; the graph on the GPU is what should not
# sit there while a render needs the room.

_HELD = {"key": None, "pipeline": None, "device": None}
_LOCK = threading.Lock()


def device_name():
    """What the refiner runs on: CUDA where there is one, then MPS, then CPU.

    ComfyUI's own answer where it has one, so a `--cpu` ComfyUI runs the
    refiner on the CPU too and a multi-GPU box uses the card core picked.
    """
    try:
        import comfy.model_management as mm

        return str(mm.get_torch_device())
    except Exception:  # noqa: BLE001 — outside ComfyUI, upstream's own resolver
        return "auto"


def pipeline(precision=DEFAULT_PRECISION):
    """The loaded pipeline, on its device. Loads only when the key changes."""
    require()
    from .mlxdlss import NeuralRenderingPipeline

    path = weights_path()
    key = (path, os.path.getmtime(path), precision)
    with _LOCK:
        held = _HELD["pipeline"]
        if held is None or _HELD["key"] != key:
            _HELD.update(key=None, pipeline=None, device=None)
            device = device_name()
            log.info("continuity: loading DLSS 5 refiner (%s, %s) on %s",
                     os.path.basename(path), precision, device)
            held = NeuralRenderingPipeline.from_safetensors(path, device=device, precision=precision)
            _HELD.update(key=key, pipeline=held, device=held.device)
        else:
            # Back from the CPU after `release`. A no-op when it never left.
            held.model.to(_HELD["device"])
        return held


def release():
    """Hand the graph's weights back to the CPU. Called at the end of every job."""
    with _LOCK:
        held = _HELD["pipeline"]
        if held is None:
            return
        try:
            held.model.to("cpu")
        except Exception:  # noqa: BLE001 — freeing is best effort
            log.debug("continuity: releasing the neural refiner failed", exc_info=True)
    try:
        import comfy.model_management as mm

        mm.soft_empty_cache()
    except Exception:  # noqa: BLE001
        pass


def unload():
    """Drop the pipeline entirely — a re-extraction changes the file under it."""
    with _LOCK:
        _HELD.update(key=None, pipeline=None, device=None)


# ---- running it -------------------------------------------------------------


def as_float(frame):
    """uint8 or float (H, W, 3) -> float32 (H, W, 3) in 0..1, contiguous."""
    array = np.asarray(frame)
    if array.ndim != 3 or array.shape[2] < 3:
        raise NeuralError(f"a frame has to be (height, width, 3); got {array.shape}")
    array = array[..., :3]
    if array.dtype == np.uint8:
        return np.ascontiguousarray(array.astype(np.float32) / 255.0)
    return np.ascontiguousarray(np.clip(array.astype(np.float32), 0.0, 1.0))


def control_mask(mask, height, width):
    """A single-channel mask -> upstream's (H, W, 3) control mask, or None.

    Red is the blend, green the tone, blue the structure, per pixel; one mask
    drives all three, so where it is zero the frame passes through untouched
    and where it is one the refiner runs at full strength. Resampled to the
    frame if it arrived at another size — a MASK off a smaller matte should
    still mean the same region.
    """
    if mask is None:
        return None
    array = np.asarray(mask, dtype=np.float32)
    if array.ndim == 3:
        array = array[0]
    if array.ndim != 2:
        raise NeuralError(f"a mask has to be (height, width); got {array.shape}")
    if array.shape != (height, width):
        from PIL import Image

        picture = Image.fromarray(np.clip(array, 0, 1) * 255.0).convert("F")
        array = np.asarray(picture.resize((width, height), Image.BILINEAR),
                           dtype=np.float32) / 255.0
    array = np.clip(array, 0.0, 1.0)
    return np.ascontiguousarray(np.repeat(array[..., None], 3, axis=2))


def refine_frame(frame, request, mask=None, frame_index=0):
    """One frame through the refiner. -> float32 (H, W, 3) in 0..1.

    `frame_index` seeds the deterministic noise, so the same frame at the same
    index is the same answer — which is what makes a bench preview and the
    file it promised agree.
    """
    source = as_float(frame)
    height, width = source.shape[:2]
    control = control_mask(mask, height, width)
    if control is not None and request.scale != 1:
        raise NeuralError(
            "a mask needs the processing scale at 1: the network reads the mask "
            "at the frame's own size, and a scaled run has no frame at that size")
    engine = pipeline(request.precision)
    log.info("continuity: DLSS 5 refine %dx%d at x%.2g, about %.1f GB",
             width, height, request.scale,
             estimate_gb(width, height, request.scale, request.precision))
    result = engine.enhance(
        source, profile=request.profile, processing_scale=request.scale,
        detail_strength=request.detail, colour_strength=request.colour,
        intensity=request.intensity, frame_index=int(frame_index), control_mask=control)
    return np.clip(np.asarray(result.image, dtype=np.float32), 0.0, 1.0)


class Sequence:
    """A run of frames through upstream's temporal session.

    History reprojected by optical flow and the learned blend — the reason a
    clip refined frame by frame does not boil. Motion comes from OpenCV's DIS
    flow where OpenCV is installed and is zero otherwise, which upstream also
    offers; zero motion still carries the history and is still steadier than
    no session at all, and the log says which one ran.

    The temporal path runs at the frame's own scale — upstream's session has
    no processing scale — so a request's `scale` is not read here. A scene cut
    (a luma jump over upstream's threshold) resets the history by itself.
    """

    def __init__(self, request, frame_index=0):
        from .mlxdlss import TemporalOptions, TemporalSession

        self.request = request
        engine = pipeline(request.precision)
        options = TemporalOptions(
            profile=request.profile, intensity=request.intensity,
            detail_strength=request.detail, colour_strength=request.colour)
        motion = "flow"
        try:
            import cv2  # noqa: F401
        except Exception:  # noqa: BLE001
            motion = "zero"
            log.info("continuity: OpenCV is not installed, so the neural refiner's "
                     "history is carried without motion")
        self.session = TemporalSession(engine, options=options, motion=motion)
        self.session.frame_index = int(frame_index)
        self.motion = motion

    def reset(self):
        self.session.reset()

    def process(self, frame, mask=None):
        source = as_float(frame)
        height, width = source.shape[:2]
        control = control_mask(mask, height, width)
        out = self.session.process(source, control_mask=control)
        return np.clip(np.asarray(out, dtype=np.float32), 0.0, 1.0)

    @property
    def scene_cuts(self):
        return int(self.session.scene_cuts)


# ---- what the upscale bench reads --------------------------------------------
#
# The bench's catalogue entry. Beside the upscalers rather than among them, with
# the label saying what it does not do. `scale` is deliberately not one of its
# dials: `upscale.target` reads an absent one as 1.

BENCH = {
    "id": "neural", "label": "Refine (DLSS 5)", "heavy": True,
    "note": "NVIDIA's DLSS 5 neural renderer as a material pass: skin, hair, "
            "fabric, contact shadows and subsurface, re-drawn at the size the "
            "picture already is. It does not enlarge anything — pair it with "
            "Sharpen or Restore, which each offer it as a second stage. Strong "
            "on figures and faces; flat, graphic or abstract material may come "
            "back odd. Nothing of NVIDIA's ships with this pack: the weights "
            "are extracted from your own DLSS DLL on the settings page.",
    "needs": "",  # filled in by `bench_entry`
    "params": (
        {"key": "profile", "kind": "option",
         "options": PROFILES, "default": DEFAULT_PROFILE,
         "label": "Profile",
         "note": "The model's own style presets, each with its own opening "
                 "strengths. Standard is what the driver runs; natural and "
                 "cinematic move its style index; neutral switches the local "
                 "tone and structure off, which leaves the strengths nothing "
                 "to scale.",
         "defaults": {name: dict(row) for name, row in PROFILE_DEFAULTS.items()}},
        {"key": "processing", "kind": "range", "min": MIN_SCALE, "max": 2.0,
         "step": 0.25, "default": DEFAULT_SCALE, "label": "Processing scale",
         "note": "Run the network on the picture resampled by this factor and "
                 "bring the result back. Finer material at 2, and about four "
                 "times the memory — the estimate under the dials is the "
                 "number to watch."},
        {"key": "detail", "kind": "range", "min": MIN_DETAIL, "max": MAX_DETAIL,
         "step": 0.25, "default": DEFAULT_DETAIL, "label": "Detail",
         "note": "How much of the model's high-frequency change is kept. 1 is "
                 "the model's answer; 0 keeps only its colour."},
        {"key": "colour", "kind": "range", "min": MIN_COLOUR, "max": MAX_COLOUR,
         "step": 0.25, "default": DEFAULT_COLOUR, "label": "Colour",
         "note": "How much of the model's low-frequency change — tone and "
                 "colour — is kept. 0 keeps only its detail."},
        {"key": "intensity", "kind": "range", "min": MIN_INTENSITY, "max": MAX_INTENSITY,
         "step": 0.05, "default": DEFAULT_INTENSITY, "label": "Intensity",
         "note": "The blend of the refined picture over the source."},
        {"key": "precision", "kind": "option",
         "options": PRECISIONS, "default": DEFAULT_PRECISION, "label": "Precision",
         "note": "Reference is float32 with the driver's rounding points and "
                 "matches it to 0.005; fast is float16 on the GPU and halves "
                 "the memory."},
        {"key": "temporal", "kind": "switch", "default": True,
         "label": "Carry history between frames",
         "note": "On a clip, each frame is refined with the previous result "
                 "reprojected into it, so the material does not boil. It runs "
                 "at the frame's own size, so the processing scale does nothing "
                 "while this is on. Nothing to a still."},
    ),
    # What the bench's foot prints before a run: the estimate's shape.
    "cost": {"gb_per_megapixel": GB_PER_MEGAPIXEL, "fast": FAST_FRACTION,
             "min_extent": MIN_EXTENT, "multiple": EXTENT_MULTIPLE},
}

# The switch Sharpen and Restore each carry: the refiner as a second stage over
# their output, which is the composition the spec asks for and the one that
# makes sense — material drawn onto the enlarged picture, not enlarged after.
AFTER_SWITCH = {
    "key": "neural", "kind": "switch", "default": False,
    "label": "Then refine (DLSS 5)",
    "note": "Run the DLSS 5 material pass over the enlarged result, at that "
            "size, with the Refine entry's own defaults. Costs its memory on "
            "top — about a gigabyte per megapixel of the result.",
}


def bench_entry():
    """The catalogue entry, with this machine's readiness filled in."""
    state = status()
    entry = dict(BENCH)
    entry["params"] = [dict(spec) for spec in BENCH["params"]]
    entry["ready"] = bool(state["ready"])
    entry["needs"] = state["needs"] or ""
    entry["status"] = {key: state[key] for key in ("weights", "extracting")}
    return entry


def request_from_values(values):
    """A bench's clamped dial values -> a `Request`."""
    return Request(on=True, profile=values.get("profile", DEFAULT_PROFILE),
                   scale=values.get("processing", DEFAULT_SCALE),
                   detail=values.get("detail", DEFAULT_DETAIL),
                   colour=values.get("colour", DEFAULT_COLOUR),
                   intensity=values.get("intensity", DEFAULT_INTENSITY),
                   precision=values.get("precision", DEFAULT_PRECISION))
