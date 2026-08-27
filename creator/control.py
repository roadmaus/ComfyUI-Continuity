"""Tracing footage into something a render can be aimed at.

A ControlNet guide is a drawing of a picture you already have — its outlines,
its tones, its blocks of colour — and the reason to want one is that describing
a composition in a sentence is the hard way to get the composition you were
looking at. So this is a *bench for footage rather than a node*: a file goes in,
a cut and a tracing are chosen, and a file comes out into the input folder,
where the pre-stage and the shot already know how to reference it.

**It does not run through the graph, and that is the point.** Every other
picture this pack makes is sampled, which means queueing a prompt, waiting for
weights and watching a progress bar. A tracing is arithmetic over pixels — a
gradient, a difference of blurs, a quantisation — so it answers in the time it
takes to decode the frame, and an answer that fast can be *shown while the
threshold is being dragged*. That is what the surface on the other side of this
module is built around, and it would not have been possible through a queue.

**Nothing here is a new dependency.** `pyproject.toml` declares none, on purpose:
this pack runs on the stack ComfyUI already ships. So the arithmetic operators are
written against numpy and `scipy.ndimage` — both in core's requirements — rather
than against OpenCV, which is the obvious library for exactly one of them (Canny)
and is not installed. The Canny below is the real algorithm, gradient through
non-maximum suppression through hysteresis, in about forty lines; the rest are
shorter than that.

**Depth and pose are not written here at all.** They are the two guides everybody
reaches for and they are both model work, and ComfyUI ships both models: Depth
Anything 3 under `comfy_extras/nodes_depth_anything_3.py`, SDPose — core's
successor to DWPose, and the same OpenPose skeleton on the other side of it —
under `comfy_extras/nodes_sdpose.py`. So the two operators below load what core
loads, run what core runs, and draw with core's own `KeypointDraw`, which is
where the DWPose colour tables the pose ControlNets were trained on actually
live. Reimplementing either against numpy would have produced a second, worse
answer to a question core had already answered, and a skeleton in the wrong
colours is a skeleton a ControlNet reads as a different pose.

They cost what a model costs, and the catalogue says so with `heavy`: the surface
does not chase them while a clip is playing, because a guide that takes a second
a frame cannot be a live preview and pretending otherwise would only queue up a
minute of stale requests.

**A model that is not on the disk is a tracing that is not ready.** `catalogue`
walks the model folders and fills each `choice` dial's options from them, so
"ready" is not a flag anybody maintains — it is whether every file this tracing
needs was found. `needs` says which files and where they go, and the surface
prints it in place of the dials.
"""

import logging
import os
import threading
from fractions import Fraction

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from scipy import ndimage

import folder_paths

from . import settings

log = logging.getLogger(__name__)

# Where a traced file lands. Under input/, because the whole point is that the
# pre-stage and the shot can reference it the moment it exists, and both read
# the input folder. In a subfolder of its own, because a bench that scattered
# forty near-identical edge maps through the root of the picker would be a bench
# nobody used twice.
SUBFOLDER = "continuity/control"

# The long edge a preview frame is cut to before anything is traced. A preview
# exists to answer "is this threshold right", and that question is answered at
# 768 pixels as well as at 4096 — and answered in a tenth of the time, which is
# what makes dragging the slider feel like a control rather than a request.
PREVIEW_LONG_EDGE = 768


class ControlError(ValueError):
    """A file cannot be read, or a tracing cannot be run on it."""


# ---- the catalogue ----------------------------------------------------------
#
# One tuple, read by both ends: the frontend builds its list and its sliders from
# this over the wire, so adding a tracing is adding an entry here and a function
# below, and nothing in the frontend has to learn about it.
#
# `note` is what the surface says under the name. It says what the tracing is
# *for* rather than how it works — "the hard outlines" rather than "Canny at
# sigma 1.2" — because the person choosing between them is choosing what to hand
# the model, not which paper to cite.

_INVERT = {
    "key": "invert", "kind": "switch", "default": False,
    "label": "Invert",
    "note": "Dark on light instead. Most ControlNet models are trained on light "
            "lines against black; a few of the line ones want the other way round.",
}

TRACINGS = (
    {
        "id": "as_shot", "label": "As shot",
        "note": "No tracing. The cut, the sound and nothing else touched — for "
                "when the footage is already the thing you want to hand over.",
        "params": (),
    },
    {
        "id": "edges", "label": "Edges",
        "note": "The hard outlines, and only those. The most literal guide there "
                "is: what it draws is what the render will line up with.",
        "params": (
            {"key": "soften", "kind": "range", "min": 0, "max": 4, "step": 0.1,
             "default": 1.2, "label": "Soften",
             "note": "How much the picture is blurred before the gradient is taken. "
                     "Up, and grain and fabric stop registering as edges; too far "
                     "up and so do the outlines."},
            {"key": "faint", "kind": "range", "min": 1, "max": 99, "step": 1,
             "default": 12, "label": "Keep faint",
             "note": "An edge this strong is kept when it runs into a strong one. "
                     "This is the dial that decides how much of the background survives."},
            {"key": "strong", "kind": "range", "min": 2, "max": 100, "step": 1,
             "default": 30, "label": "Start from",
             "note": "An edge this strong starts a line on its own. Raise it until "
                     "only the subject is drawing."},
            _INVERT,
        ),
    },
    {
        "id": "lines", "label": "Lines",
        "note": "A drawing rather than a trace — strokes that follow the form, the "
                "way a sketch of the same frame would. Softer to aim at than Edges.",
        "params": (
            {"key": "detail", "kind": "range", "min": 0.3, "max": 4, "step": 0.1,
             "default": 1, "label": "Detail",
             "note": "The size of the marks. Small draws hair and creases; large "
                     "draws the shapes and leaves the surface alone."},
            {"key": "ink", "kind": "range", "min": 0, "max": 100, "step": 1,
             "default": 42, "label": "Ink",
             "note": "How dark a mark has to be to be drawn at all. Up for a sparse "
                     "line drawing, down for a shaded one."},
            {"key": "bite", "kind": "range", "min": 1, "max": 60, "step": 1,
             "default": 22, "label": "Bite",
             "note": "How sharply a mark goes from grey to black. Up is pen, down "
                     "is pencil."},
            _INVERT,
        ),
    },
    {
        "id": "blocks", "label": "Blocks",
        "note": "The frame flattened into fields of one colour — where the shapes "
                "are and what colour each is, with the detail thrown away.",
        "params": (
            {"key": "fields", "kind": "range", "min": 2, "max": 12, "step": 1,
             "default": 5, "label": "Fields",
             "note": "How many levels each channel is allowed. Few reads as a "
                     "poster; many keeps the modelling."},
            {"key": "settle", "kind": "range", "min": 0, "max": 12, "step": 1,
             "default": 4, "label": "Settle",
             "note": "How far a field spreads before it is drawn, which is what "
                     "stops the flattening coming out as speckle."},
        ),
    },
    {
        "id": "luma", "label": "Luma",
        "note": "The tones with the colour taken out — what a recolour model reads "
                "when it is being told the lighting and left to choose the palette.",
        "params": (
            {"key": "lift", "kind": "range", "min": -50, "max": 50, "step": 1,
             "default": 0, "label": "Lift",
             "note": "Where black sits. Up opens the shadows, down closes them."},
            {"key": "curve", "kind": "range", "min": 30, "max": 260, "step": 5,
             "default": 100, "label": "Curve",
             "note": "The midtones, bent. Under 100 brightens them, over 100 sinks them."},
            _INVERT,
        ),
    },
    {
        "id": "blur", "label": "Blur",
        "note": "The frame with everything but its masses removed — the guide a tile "
                "or a blur model reads when it is being given a composition and no detail.",
        "params": (
            {"key": "radius", "kind": "range", "min": 1, "max": 60, "step": 1,
             "default": 14, "label": "Radius",
             "note": "How far the picture is spread. Far enough that no shape "
                     "survives, near enough that the layout does."},
        ),
    },
    {
        "id": "depth", "label": "Depth", "heavy": True,
        "note": "How far away everything is, as a grey, near bright. The guide that "
                "hands a render the room rather than the outline — it says where the "
                "walls are and leaves the surface of everything free.",
        "needs": "a Depth Anything 3 model in models/geometry_estimation. "
                 "Comfy-Org/Depth-Anything-3 on Hugging Face has four; Small is the "
                 "one to start with. Nothing is downloaded from here.",
        "params": (
            {"key": "model", "kind": "choice", "from": ("geometry_estimation",),
             "label": "Model", "default": "", "options": (),
             "note": "Small and Base are quick. Mono-Large and Metric-Large are "
                     "slower and sharper, and they are the two that know which part "
                     "of the frame is sky."},
            {"key": "detail", "kind": "range", "min": 140, "max": 1036, "step": 14,
             "default": 504, "label": "Detail",
             "note": "The size the model reads the frame at, on its long edge. The "
                     "answer is stretched back to full size either way, so this buys "
                     "sharpness in the depth itself and costs time."},
            {"key": "sky", "kind": "switch", "default": True, "label": "Sink the sky",
             "note": "Push whatever the model calls sky to the far end instead of "
                     "letting it set the scale. Off, one bright cloud flattens the "
                     "whole street. Only the Mono and Metric models answer this."},
            {"key": "steady", "kind": "switch", "default": True, "label": "Hold the range",
             "note": "Measure near and far once, on the first frame written, and hold "
                     "them for the rest of the cut. Off, every frame is scaled to its "
                     "own extremes and the grey breathes — which is the usual reason a "
                     "depth-guided render flickers."},
            _INVERT,
        ),
    },
    {
        "id": "pose", "label": "Pose", "heavy": True,
        "note": "The skeleton, drawn in the colours the pose ControlNets were trained "
                "on. Nothing of the room survives, and that is the point: the movement "
                "is kept and everything else is left to the prompt.",
        "needs": "an SDPose model and a VAE. sdpose_wholebody_fp16.safetensors from "
                 "Comfy-Org/SDPose goes in models/checkpoints or "
                 "models/diffusion_models; it is an SD 1.5 model, so an SD 1.5 VAE in "
                 "models/vae is the other half. Nothing is downloaded from here.",
        "params": (
            {"key": "model", "kind": "choice",
             "from": ("checkpoints", "diffusion_models", "unet"),
             "label": "Model", "default": "", "options": (),
             "note": "The SDPose checkpoint. Any other model in these folders will "
                     "load and then fail for want of a heatmap head, which is the "
                     "only thing this reads out of it."},
            {"key": "vae", "kind": "choice", "from": ("vae",),
             "label": "VAE", "default": "", "options": (),
             "note": "The SD 1.5 VAE the frame is encoded through — SDPose reads the "
                     "pose out of a latent, so the picture has to be encoded before "
                     "there is anything to read. Any stock SD 1.5 VAE will do."},
            {"key": "body", "kind": "switch", "default": True, "label": "Body",
             "note": "The eighteen trunk and limb points, and the sticks between them. "
                     "This is what every pose ControlNet was trained on; the rest are "
                     "extra that some of them read."},
            {"key": "hands", "kind": "switch", "default": True, "label": "Hands",
             "note": "Twenty-one points per hand. Worth having wherever the hands are "
                     "doing something, and worth turning off where they are a blur — "
                     "a guessed finger is a guide the render will follow."},
            {"key": "face", "kind": "switch", "default": True, "label": "Face",
             "note": "The sixty-eight face landmarks. They pin the expression as well "
                     "as the head, which is more control than a wide shot needs."},
            {"key": "feet", "kind": "switch", "default": False, "label": "Feet",
             "note": "Six more points below the ankles. Off by default because most "
                     "pose ControlNets never saw them."},
            {"key": "certainty", "kind": "range", "min": 5, "max": 90, "step": 1,
             "default": 30, "label": "Certainty",
             "note": "How sure the model has to be before a point is drawn. Up to lose "
                     "the flailing limbs it invents in a crowd, down to keep a figure "
                     "that is half out of frame."},
            {"key": "weight", "kind": "range", "min": 1, "max": 10, "step": 1,
             "default": 4, "label": "Weight",
             "note": "How thick the sticks are drawn, in pixels. Thicker reads further "
                     "down a shrunken frame; thinner is more exact."},
        ),
    },
)

BY_ID = {tracing["id"]: tracing for tracing in TRACINGS}


def _files(folders):
    """Every filename in `folders`, in the order the folders were named.

    Deduplicated, because a name that is in two of them is one file as far as
    the dial is concerned and `_model_path` will find it in whichever folder
    holds it. An unconfigured folder is an empty one rather than an error: a
    ComfyUI without `geometry_estimation` is simply a ComfyUI where Depth is
    not ready yet, and that is the sentence the surface already knows how to say.
    """
    seen, names = set(), []
    for folder in folders:
        try:
            listing = folder_paths.get_filename_list(folder)
        except Exception:  # noqa: BLE001 — an unconfigured folder is an empty one
            continue
        for name in listing:
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def catalogue():
    """The tracings, as the frontend reads them — with this machine filled in.

    Every `choice` dial names the model folders it draws from, and this is where
    that turns into an actual list of files. `ready` falls out of it: a tracing
    is ready when every file it needs was found, so nothing has to be marked by
    hand and a model dropped into the folder makes its tracing work without a
    line changing here.

    Walks the model directories, so callers run it off the event loop.
    """
    out = []
    for tracing in TRACINGS:
        entry = dict(tracing)
        params, ready = [], True
        for spec in tracing["params"]:
            spec = dict(spec)
            if spec["kind"] == "choice":
                spec["options"] = _files(spec.pop("from"))
                spec["default"] = spec["options"][0] if spec["options"] else ""
                ready = ready and bool(spec["options"])
            params.append(spec)
        entry["params"] = params
        entry["ready"] = ready
        out.append(entry)
    return {"tracings": out}


def _params(op, raw):
    """Whatever arrived -> the values this tracing actually takes.

    Clamped rather than rejected, and defaulted where a key is missing: these
    numbers come off sliders that already hold the bounds, so anything out of
    range is a stale frontend or a hand-made request, and neither is worth an
    error page. What is *not* forgiven is an unknown tracing — that one is a
    typo the caller has to see.
    """
    tracing = BY_ID.get(str(op))
    if tracing is None:
        raise ControlError(f"{op!r} is not a tracing this pack knows")
    values = {}
    for spec in tracing["params"]:
        given = raw.get(spec["key"])
        if spec["kind"] == "switch":
            values[spec["key"]] = _truthy(given, spec["default"])
            continue
        if spec["kind"] == "choice":
            # Not clamped like a slider: a name that is not on the disk cannot be
            # nudged into one that is. A stale pick falls back to the first file
            # there is, and no file at all is the one thing this raises for —
            # with `needs`, because "pick a model" is not useful to somebody who
            # has not downloaded one.
            options = _files(spec["from"])
            if not options:
                raise ControlError(f"{tracing['label']} needs {tracing['needs']}")
            values[spec["key"]] = given if given in options else options[0]
            continue
        try:
            number = float(given)
        except (TypeError, ValueError):
            number = float(spec["default"])
        values[spec["key"]] = min(float(spec["max"]), max(float(spec["min"]), number))
    return values


def _truthy(given, fallback):
    if given is None:
        return bool(fallback)
    if isinstance(given, str):
        return given.strip().lower() in ("1", "true", "yes", "on")
    return bool(given)


# ---- the operators ----------------------------------------------------------
#
# Each takes an (H, W, 3) uint8 RGB frame and returns one of the same shape. No
# operator knows whether it is drawing a preview, a still or the four-hundredth
# frame of a clip, which is what lets the surface show the truth while a slider
# is moving: the picture under the pointer went through the same function the
# file will.


def _grey(frame):
    """Rec. 709 luminance in 0..1. The measure every operator here starts from."""
    return (frame[..., 0] * 0.2126 + frame[..., 1] * 0.7152
            + frame[..., 2] * 0.0722) / 255.0


def _mono(value, invert=False):
    """A 0..1 single channel -> the uint8 RGB frame it is drawn as."""
    if invert:
        value = 1.0 - value
    grey = np.clip(value * 255.0, 0, 255).astype(np.uint8)
    return np.repeat(grey[..., None], 3, axis=2)


def _edges(frame, soften, faint, strong, invert):
    """Canny, written out: gradient, thinned to its ridges, then grown.

    The two thresholds are percentages of this frame's own strongest edge rather
    than absolute levels, and that is deliberate — a fixed 100 means something
    different on a foggy exterior and a lit close-up, so a threshold that was
    right for one clip would have to be re-found for the next. As a share of what
    is *in the frame*, the same setting means the same thing everywhere.
    """
    grey = _grey(frame)
    if soften > 0:
        grey = ndimage.gaussian_filter(grey, soften)
    gy = ndimage.sobel(grey, axis=0, mode="nearest")
    gx = ndimage.sobel(grey, axis=1, mode="nearest")
    magnitude = np.hypot(gx, gy)
    peak = magnitude.max()
    if peak <= 0:
        return _mono(np.zeros(grey.shape), invert)

    # Non-maximum suppression. A gradient is a ridge several pixels wide and a
    # line is one pixel wide, so every pixel is kept only if it is at least as
    # strong as the two neighbours the gradient points at. The angle is rounded
    # into four directions, which is all eight neighbours can express.
    angle = np.rad2deg(np.arctan2(gy, gx)) % 180
    sector = (((angle + 22.5) // 45) % 4).astype(np.int8)
    padded = np.pad(magnitude, 1, mode="edge")
    height, width = magnitude.shape
    ridge = np.zeros(magnitude.shape, dtype=bool)
    for index, ((dy1, dx1), (dy2, dx2)) in enumerate(
            (((0, 1), (0, -1)), ((-1, 1), (1, -1)), ((-1, 0), (1, 0)), ((-1, -1), (1, 1)))):
        here = sector == index
        if not here.any():
            continue
        one = padded[1 + dy1:1 + dy1 + height, 1 + dx1:1 + dx1 + width]
        two = padded[1 + dy2:1 + dy2 + height, 1 + dx2:1 + dx2 + width]
        ridge |= here & (magnitude >= one) & (magnitude >= two)

    # Hysteresis. `binary_propagation` is exactly the operation the algorithm
    # describes — flood the strong seeds through the weak mask — and it is in
    # scipy, so there is nothing to write here but the two levels.
    weak = ridge & (magnitude >= peak * faint / 100.0)
    seed = ridge & (magnitude >= peak * strong / 100.0)
    kept = ndimage.binary_propagation(seed, mask=weak)
    return _mono(kept.astype(np.float32), invert)


def _lines(frame, detail, ink, bite, invert):
    """XDoG: two blurs, subtracted, then pushed to ink.

    A difference of Gaussians is what an edge looks like to an eye rather than to
    a gradient operator — it responds to the *step*, at the scale the blurs set
    — and the tanh on the end is what turns a continuous response into strokes
    with a weight. Between them they give the thing Edges cannot: a drawing that
    fades where the form does instead of stopping dead at a threshold.
    """
    grey = _grey(frame)
    near = ndimage.gaussian_filter(grey, detail)
    far = ndimage.gaussian_filter(grey, detail * 1.6)
    # The classic tau, fixed at the value that leaves the response centred on
    # zero: the two dials that are worth having are where the ink starts and how
    # hard it lands, and a third that shifts both at once is a dial nobody can aim.
    response = near - 0.97 * far
    scale = np.abs(response).max()
    if scale <= 0:
        return _mono(np.zeros(grey.shape), invert)
    response = response / scale
    threshold = -0.5 + ink / 100.0
    drawn = np.where(response >= threshold, 0.0,
                     -np.tanh(bite * (response - threshold)))
    return _mono(np.clip(drawn, 0, 1), invert)


def _blocks(frame, fields, settle):
    """Quantise, having first spread each field far enough to have an edge.

    The median rather than a blur, and that is the whole of why this works: a
    blur puts a ramp between two fields and the quantiser then cuts the ramp into
    steps, which is banding. A median filter moves the boundary without inventing
    anything between the two sides of it, so what comes out is flat fields that
    meet along a line.
    """
    picture = frame.astype(np.float32)
    if settle >= 1:
        size = int(settle) * 2 + 1
        picture = np.stack(
            [ndimage.median_filter(picture[..., channel], size=size, mode="nearest")
             for channel in range(3)], axis=2)
    steps = max(2, int(round(fields)))
    quantised = np.round(picture / 255.0 * (steps - 1)) / (steps - 1)
    return np.clip(quantised * 255.0, 0, 255).astype(np.uint8)


def _luma(frame, lift, curve, invert):
    grey = _grey(frame)
    floor = lift / 100.0
    grey = np.clip((grey - max(0.0, -floor)) / max(1e-3, 1.0 - abs(floor)) + max(0.0, floor), 0, 1)
    return _mono(np.power(grey, curve / 100.0), invert)


def _blur(frame, radius):
    spread = np.stack(
        [ndimage.gaussian_filter(frame[..., channel].astype(np.float32), radius)
         for channel in range(3)], axis=2)
    return np.clip(spread, 0, 255).astype(np.uint8)


# ---- the model tracings -----------------------------------------------------
#
# Depth and pose go through core's own code rather than through a graph: the
# nodes in `comfy_extras` are thin wrappers over functions that take tensors and
# return tensors, and a bench that queued a two-node prompt per frame would have
# paid the queue's latency four hundred times over for nothing.
#
# What that costs is one seam of honesty: everything above is numpy in and numpy
# out because that is what PyAV and Pillow speak, and everything here is torch,
# so the two operators below convert at their edges and are torch the whole way
# through. There is no third representation and no arithmetic on the numpy side.

# One tracing at a time. Both of these load a model onto the GPU and the caller
# is a request handler on a thread pool, so without this a slider dragged twice
# would have two frames racing for the same weights — and the prompt queue is
# using that GPU too.
_ONE_AT_A_TIME = threading.Lock()

# Loaded weights, kept between frames and between requests. Keyed by the names
# that were picked, so changing the pick reloads and dragging a slider does not:
# a preview that reloaded two gigabytes per drag would not be a preview.
_MODELS = {"depth": {"key": None, "held": None},
           "pose": {"key": None, "held": None}}


def _keep(kind, key, load):
    slot = _MODELS[kind]
    if slot["key"] != key or slot["held"] is None:
        # Dropped before the load rather than after, so a failed load does not
        # leave the old model pinned in memory under a name nobody asked for.
        slot.update(key=None, held=None)
        slot.update(key=key, held=load())
    return slot["held"]


def _model_path(folders, name):
    for folder in folders:
        path = folder_paths.get_full_path(folder, name)
        if path:
            return path
    raise ControlError(f"{name} is not in models/{' or models/'.join(folders)} any more")


def _torch_frame(frame):
    """uint8 (H, W, 3) -> the (1, H, W, 3) float IMAGE tensor core's code takes."""
    import torch

    return torch.from_numpy(np.ascontiguousarray(frame)).float().div_(255.0).unsqueeze(0)


def _from_torch(picture):
    """(1, H, W, 3) float in 0..1 -> the uint8 frame the encoder takes back."""
    return picture[0].clamp(0, 1).mul(255).round().to("cpu").numpy().astype(np.uint8)


def _depth_model(name):
    def load():
        import comfy.sd

        return comfy.sd.load_diffusion_model(_model_path(("geometry_estimation",), name))

    return _keep("depth", name, load)


def _spread(depth, sky, hold):
    """A depth map -> 0..1 grey with near white.

    The same quantile normalisation core's own `DA3Render` does in `v2_style`,
    with one thing added: `hold`. Core normalises each frame against its own 1st
    and 99th percentile, which is right for a still and wrong for a clip — the
    moment a car leaves the shot the far end moves, every grey in the frame
    shifts with it, and a render guided by the result pumps. Given a `hold`
    dict, the first frame measures and the rest of the cut borrows.
    """
    import torch
    from comfy.ldm.depth_anything_3 import preprocess as da3

    ground = da3.compute_non_sky_mask(sky) if sky is not None else None
    if hold is not None and "lo" in hold:
        lo, hi = hold["lo"], hold["hi"]
    else:
        valid = depth[ground] if ground is not None and ground.any() else depth.flatten()
        if valid.numel() > 100_000:
            valid = valid[torch.randint(0, valid.numel(), (100_000,))]
        lo, hi = torch.quantile(valid, 0.01), torch.quantile(valid, 0.99)
        if hold is not None:
            hold["lo"], hold["hi"] = lo, hi
    grey = 1.0 - ((depth - lo) / (hi - lo).clamp(min=1e-6)).clamp(0.0, 1.0)
    if ground is not None:
        # Sky is far by definition, whatever the model made of its texture.
        grey = torch.where(ground, grey, torch.zeros_like(grey))
    return grey


def _depth(frame, values):
    """Depth Anything 3, through core's own runner.

    `_run_da3` rather than the node around it: the node's job is to package the
    answer as a DA3_GEOMETRY dict for the four other nodes that read one, and the
    only thing wanted here is the depth itself. Mono mode, always — multiview
    treats a batch as views of one scene, and consecutive frames of a moving
    camera are exactly that, but it needs every frame in memory at once and a
    clip does not fit.
    """
    from comfy_extras.nodes_depth_anything_3 import _run_da3

    model = _depth_model(values["model"])
    with _ONE_AT_A_TIME:
        depth, _confidence, sky = _run_da3(
            model, _torch_frame(frame), int(values["detail"]))
    depth = depth[0]
    sky = sky[0] if sky is not None and values["sky"] else None
    grey = _spread(depth, sky, values.setdefault("_hold", {}) if values["steady"] else None)
    if values["invert"]:
        grey = 1.0 - grey
    return _from_torch(grey.unsqueeze(0).unsqueeze(-1).expand(1, *grey.shape, 3))


def _pose_models(model_name, vae_name):
    """(model, vae) for SDPose. Two files, because SDPose is two things.

    It is an SD 1.5 UNet with a heatmap head bolted on, and the frame reaches it
    as a latent — so the picture has to be encoded before the pose can be read
    out of it, and the encoder is a separate download. Whichever folder the model
    file was found in, a checkpoint that carries its own VAE is not used for it:
    the pick is the pick, and a VAE that silently came from somewhere else is a
    file the dial is lying about.
    """
    def load():
        import comfy.sd
        import comfy.utils

        # `load_diffusion_model` whichever folder it came out of: it strips a
        # checkpoint's `model.diffusion_model.` prefix itself, so the one call
        # covers the bare single-file SDPose release and a full checkpoint
        # somebody has fused it into, and nothing here has to guess which it is.
        model = comfy.sd.load_diffusion_model(
            _model_path(("checkpoints", "diffusion_models", "unet"), model_name))
        if not hasattr(model.model.diffusion_model, "heatmap_head"):
            raise ControlError(
                f"{model_name} has no pose head in it. Pose reads SDPose "
                "specifically — sdpose_wholebody_fp16.safetensors from "
                "Comfy-Org/SDPose — and any other SD 1.5 model will load and "
                "then have nothing to answer with.")
        sd, metadata = comfy.utils.load_torch_file(
            _model_path(("vae",), vae_name), return_metadata=True)
        vae = comfy.sd.VAE(sd=sd, metadata=metadata)
        vae.throw_exception_if_invalid()
        return model, vae

    return _keep("pose", (model_name, vae_name), load)


def _pose(frame, values):
    """SDPose, extracted and drawn — both through core's own nodes.

    The drawing especially. A pose ControlNet does not read a skeleton, it reads
    *those* colours: the eighteen limbs each have their own hue and the model
    learned which is which, so a skeleton drawn in a palette of one's own is a
    skeleton it reads as a different pose. `KeypointDraw` in `comfy_extras/pose`
    is the DWPose table, and going through the node that uses it is the only way
    to be sure this bench and a graph built out of the same model agree.
    """
    import torch
    from comfy_extras.nodes_sdpose import SDPoseDrawKeypoints, SDPoseKeypointExtractor

    model, vae = _pose_models(values["model"], values["vae"])
    with _ONE_AT_A_TIME:
        keypoints = SDPoseKeypointExtractor.execute(
            model, vae, _torch_frame(frame), 1).result[0]
        drawn = SDPoseDrawKeypoints.execute(
            keypoints,
            values["body"], values["hands"], values["face"], values["feet"],
            int(values["weight"]), max(1, round(values["weight"] * 0.75)),
            values["certainty"] / 100.0, values["body"],
        ).result[0]
    return _from_torch(drawn.float())


def trace(frame, op, values):
    """One frame, traced. `frame` and the answer are both (H, W, 3) uint8 RGB."""
    if op == "as_shot":
        return frame
    if op == "edges":
        return _edges(frame, values["soften"], values["faint"], values["strong"],
                      values["invert"])
    if op == "lines":
        return _lines(frame, values["detail"], values["ink"], values["bite"],
                      values["invert"])
    if op == "blocks":
        return _blocks(frame, values["fields"], values["settle"])
    if op == "luma":
        return _luma(frame, values["lift"], values["curve"], values["invert"])
    if op == "blur":
        return _blur(frame, values["radius"])
    if op == "depth":
        return _depth(frame, values)
    if op == "pose":
        return _pose(frame, values)
    raise ControlError(f"{op!r} is not a tracing this pack knows")


# ---- reading a source -------------------------------------------------------


def _open_image(path):
    try:
        with Image.open(path) as picture:
            # The camera's rotation tag, applied — a portrait phone clip traced
            # sideways would be a guide the render lines up with sideways.
            return np.asarray(ImageOps.exif_transpose(picture).convert("RGB"))
    except (UnidentifiedImageError, OSError) as exc:
        raise ControlError(f"{os.path.basename(path)} could not be read as a picture") from exc


def _fit(frame, long_edge):
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= long_edge:
        return frame
    scale = long_edge / longest
    picture = Image.fromarray(frame).resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
    return np.asarray(picture)


def is_video(path):
    return bool(folder_paths.filter_files_content_types([os.path.basename(path)], ["video"]))


def _video_frame(path, at):
    """The frame `at` seconds into a clip, as uint8 RGB.

    Seek, then decode forward: a seek lands on the keyframe at or before the
    time asked for, so the frames between it and the mark still have to be run
    through. Best effort on both — a container that will not seek is decoded from
    the top, and a mark past the end takes the last frame there is.
    """
    import av

    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if at > 0 and stream.time_base:
            try:
                container.seek(int(at / stream.time_base), stream=stream)
            except Exception:  # noqa: BLE001 — an unseekable container decodes from zero
                container.seek(0)
        last = None
        for frame in container.decode(stream):
            last = frame
            if frame.time is not None and frame.time >= at:
                break
        if last is None:
            raise ControlError(f"{os.path.basename(path)} has no decodable frame")
        return last.to_ndarray(format="rgb24")


def source_frame(path, at=0.0, long_edge=PREVIEW_LONG_EDGE):
    """One frame off whatever this file is, cut to preview size."""
    frame = _video_frame(path, at) if is_video(path) else _open_image(path)
    return _fit(frame, long_edge)


def preview(path, op, raw, at=0.0):
    """-> (PNG bytes, `(width, height)`) of one frame, traced."""
    import io

    values = _params(op, raw)
    frame = trace(source_frame(path, at), op, values)
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, "PNG", optimize=False, compress_level=1)
    return buffer.getvalue(), (frame.shape[1], frame.shape[0])


# ---- writing the result -----------------------------------------------------


def _free_name(directory, stem, extension):
    """A name in `directory` nothing is using yet.

    Counted rather than stamped: a bench is a place you try the same clip at four
    thresholds, and `clip-edges-2.png` says which attempt this was where a
    timestamp says only when.
    """
    os.makedirs(directory, exist_ok=True)
    name = f"{stem}{extension}"
    index = 2
    while os.path.exists(os.path.join(directory, name)):
        name = f"{stem}-{index}{extension}"
        index += 1
    return name


def _stem(path, op, trim, at=None):
    """What the written file is called before the counter is put on it.

    `at` wins over `trim` because they describe different files: a span is the
    stretch a clip was traced over, and a mark is the single frame cut out of
    it. A still named for the span it came out of would say it was six seconds
    long.
    """
    base = os.path.splitext(os.path.basename(path))[0]
    # Room for the counter and the extension inside the 255 bytes most file
    # systems allow, without truncating the part that says what the file is.
    base = base[:90]
    parts = [base, op]
    if at is not None:
        parts.append(f"{at:.1f}s".replace(".", "-"))
    elif trim:
        parts.append(f"{trim[0]:.0f}-{trim[1]:.0f}s")
    return "-".join(parts)


def _run_image(path, op, values, out_dir, stem):
    frame = trace(_open_image(path), op, values)
    name = _free_name(out_dir, stem, ".png")
    Image.fromarray(frame).save(os.path.join(out_dir, name), "PNG")
    return name


def _run_frame(path, op, values, out_dir, stem, at):
    """One frame of a clip, traced at full size and written as a still.

    A pre-stage renders a single picture, so a clip is not something it can be
    aimed at — but the frame under the bench's playhead is a picture, and it is
    the one that has been on the light box the whole time the dials were being
    moved. Tracing it through the same operator at the same values is what makes
    the file that lands in the pre-stage the thing that was being judged, rather
    than a second guess at it.

    Full size and undecorated, the way `_run_image` is: the preview route fits
    its frame to 768 because it is answering a slider, and this is answering a
    render.
    """
    frame = trace(_video_frame(path, at), op, values)
    name = _free_name(out_dir, stem, ".png")
    Image.fromarray(frame).save(os.path.join(out_dir, name), "PNG")
    return name


def _even(size):
    """H.264 in 4:2:0 cannot encode an odd dimension."""
    return size - (size % 2)


def _run_video(path, op, values, out_dir, stem, trim, keep_sound, on_progress):
    """Decode the chosen span, trace every frame, encode a new clip.

    Streamed rather than loaded: a minute of 1080p is four gigabytes as an array
    and about nothing as a sequence of frames, and there is no stage in this
    that needs two frames at once.

    The sound, where it is kept, goes through an `AudioFifo` for the reason
    `mux.py` carries samples between parts: AAC's frame size is fixed, and
    libavcodec refuses a short frame anywhere but the end of the stream. The
    fifo is the same deal in a library the decode already had open.
    """
    import av

    crf = settings.video_crf()
    # How often the bar moves. Eight frames of arithmetic is a few tenths of a
    # second and a bar that stepped per frame would just be sending; eight frames
    # of Depth Anything is most of a minute, and a bar that had not moved in a
    # minute is a bench that has hung.
    every = 1 if BY_ID[op].get("heavy") else 8
    start, end = trim if trim else (0.0, None)
    name = _free_name(out_dir, stem, ".mp4")
    target = os.path.join(out_dir, name)

    with av.open(path) as source:
        stream = source.streams.video[0]
        stream.thread_type = "AUTO"
        audio_in = next(iter(source.streams.audio), None) if keep_sound else None
        # `guessed_rate` is the frame interval the container actually steps at;
        # `average_rate` is frames over duration, which on variable-rate footage
        # (every phone clip) is neither. Only the hint the encoder is opened with.
        rate = stream.guessed_rate or stream.average_rate or 24
        # The display size, not the storage size: a rotated phone clip stores
        # landscape and plays portrait, and the guide has to match the play.
        width, height = int(stream.width), int(stream.height)
        if int(getattr(stream, "rotation", 0) or 0) % 180:
            width, height = height, width
        width, height = _even(width), _even(height)
        if width < 2 or height < 2:
            raise ControlError(f"{os.path.basename(path)} is too small to trace")
        span = (end - start) if end is not None else None
        expected = max(1, round(float(rate) * span)) if span else None

        with av.open(target, "w") as out:
            video = out.add_stream("libx264", rate=rate)
            video.width, video.height = width, height
            video.pix_fmt = "yuv420p"
            video.options = {"crf": str(crf), "preset": "medium"}
            # The source's own tick, not one over the frame rate, and the frames
            # keep their own timestamps against it — because a guide has to line
            # up with the footage frame for frame. Counting frames out at a
            # constant rate stretched every variable-rate clip: 112 frames of a
            # two-second cut, written at the average rate the container reports,
            # came out as a three-second file playing slow.
            tick = stream.time_base or Fraction(1, 90000)
            video.codec_context.time_base = tick
            audio_out = None
            fifo = None
            resampler = None
            if audio_in is not None:
                audio_out = out.add_stream("aac", rate=audio_in.rate)
                audio_out.layout = "stereo" if audio_in.channels >= 2 else "mono"
                fifo = av.AudioFifo()
                resampler = av.audio.resampler.AudioResampler(
                    format="fltp", layout=audio_out.layout, rate=audio_in.rate)

            if start > 0 and stream.time_base:
                try:
                    source.seek(int(start / stream.time_base), stream=stream)
                except Exception:  # noqa: BLE001
                    source.seek(0)

            written = 0
            zero = None
            streams = [stream] + ([audio_in] if audio_in is not None else [])
            for frame in source.decode(*streams):
                when = frame.time
                if when is None:
                    continue
                if when < start:
                    continue
                if end is not None and when >= end:
                    # Video and audio do not run out together, so this only stops
                    # the stream that has passed the mark.
                    if isinstance(frame, av.VideoFrame):
                        break
                    continue
                if isinstance(frame, av.VideoFrame):
                    if frame.pts is None:
                        continue
                    if zero is None:
                        zero = frame.pts
                    traced = trace(frame.to_ndarray(format="rgb24"), op, values)
                    if traced.shape[1] != width or traced.shape[0] != height:
                        traced = np.asarray(
                            Image.fromarray(traced).resize((width, height), Image.LANCZOS))
                    picture = av.VideoFrame.from_ndarray(traced, format="rgb24")
                    picture.pts = frame.pts - zero
                    picture.time_base = tick
                    out.mux(video.encode(picture))
                    written += 1
                    if on_progress and expected and written % every == 0:
                        on_progress(min(0.99, written / expected))
                elif audio_out is not None:
                    for block in resampler.resample(frame):
                        block.pts = None
                        fifo.write(block)
                        while (chunk := fifo.read(audio_out.frame_size)) is not None:
                            out.mux(audio_out.encode(chunk))

            if audio_out is not None:
                leftover = fifo.read()
                if leftover is not None:
                    out.mux(audio_out.encode(leftover))
                out.mux(audio_out.encode(None))
            out.mux(video.encode(None))

    if not written:
        os.remove(target)
        raise ControlError("that cut has no frames in it")
    return name


def run(filename, op, raw, trim=None, keep_sound=False, on_progress=None, at=None):
    """Trace a file. -> the input-relative path of what was written.

    The answer is a path rather than a payload because the caller's next move is
    to hand it to a pre-stage or a shot, and both of those reference files by
    name in the input folder. Nothing is returned that would have to be uploaded
    back.

    `at` asks for one frame of a clip as a still instead of the whole cut as a
    clip, and it is what lets the bench offer a door rather than a refusal: the
    two places a tracing can go want different shapes, and which shape gets
    written is the caller's to say. Ignored for a source that is already a
    still, which has one frame and it is the file.
    """
    from . import media

    path = media.resolve(filename)
    values = _params(op, raw)
    out_dir = os.path.join(folder_paths.get_input_directory(), *SUBFOLDER.split("/"))
    if is_video(path) and at is not None:
        name = _run_frame(path, op, values, out_dir,
                          _stem(path, op, None, max(0.0, float(at))), max(0.0, float(at)))
        kind = "image"
    elif is_video(path):
        name = _run_video(path, op, values, out_dir, _stem(path, op, trim),
                          trim, keep_sound, on_progress)
        kind = "video"
    else:
        name = _run_image(path, op, values, out_dir, _stem(path, op, trim))
        kind = "image"
    log.info("continuity: traced %s -> %s/%s", os.path.basename(path), SUBFOLDER, name)
    return {"path": f"{SUBFOLDER}/{name}", "kind": kind}
