"""Making a finished file bigger, on a bench of its own.

Every other way this pack enlarges anything is attached to a render: the first
pass sampled small and refined, the second stage of a family that has one, the
LTX re-detail. `compile.UPSCALE_MODES` is all three, and all three need a piece
to be attached to. What none of them answer is the question anybody with a
folder of renders eventually asks — *here is a file, make it bigger* — because
by then the piece it came out of may not be on the canvas any more, and the file
may not have come out of this pack at all.

So this is a bench, in the sense `control.py` established: a file goes in, a
surface with dials on it decides what happens to it, and a file comes out. What
differs is where it lands. A tracing is an ingredient and lands in `input/`
where a render can reference it; an upscale is the finished thing and lands on a
shelf in the output folder next to the renders, where the gallery already looks.

**What is here, and what is deliberately not.**

- **Sharpen**, below, is a GAN — ESRGAN and everything else spandrel loads,
  through core's own `ImageUpscaleWithModel` and its tiling. One forward pass
  per frame, no prompt, no sampler, nothing invented: it resolves what the
  pixels already imply and stops. That is its ceiling and it is worth saying out
  loud, because the failure it will be blamed for — soft footage that comes back
  bigger and still soft — is not a bug in it.
- **Restore** is SeedVR2, through the nodes core ships in
  `comfy_extras/nodes_seedvr.py`. One sampling step at cfg 1 over a source
  latent, so it is a restoration rather than a generation: it takes the picture
  resampled to the target and repairs what resampling could not invent —
  compression, grain, the softness of a frame that was small to begin with. It
  is the answer for footage with damage in it, and it costs what a model costs.
  On a clip it reads several frames at once and that is the whole point: a
  restoration done frame by frame boils, and the temporal chunk is what stops
  it. `bench.transcode` carries the chunking and the crossfade between chunks;
  what is here is which frames go in and what comes back.
- **Re-detail is not offered here at all**, and that is a decision rather than an
  omission. It re-renders rather than resolves — see `redetail.py`, where the
  freckles that were never on the face are written down — so it is a promise
  about a *different picture coming back*, and the two backends here promise the
  same picture, larger. A bench that offered all three under one verb would be
  lying about one of them.

**Nothing here is a new dependency,** which is the same rule the tracing bench
is written under: the model is loaded by core's loader, run through core's node,
and tiled by core's tiler. What this module owns is the arithmetic around it —
which target a scale means, how many passes of a x4 model a x2 target is, and
where the file goes.
"""

import logging
import os

import numpy as np
from PIL import Image

import folder_paths

from . import bench
from . import outputs

log = logging.getLogger(__name__)

# The square cut out of the source for the light box, in source pixels. A
# preview here cannot be the whole frame the way a tracing's is: an upscale is a
# claim about detail, and detail is exactly what survives being fitted to 768
# pixels least. So the answer is a *tile at full size* — small enough to run in
# the time it takes to look up, large enough to hold a face.
PREVIEW_TILE = 384

# What Restore samples at. One step at cfg 1 is not a shortcut — it is the model:
# SeedVR2 is a one-step restorer, and a second step is a second guess at a
# picture that was already answered. `denoise` is 1 because the source is not in
# the noise, it is in the conditioning.
RESTORE_STEPS = 1
RESTORE_SAMPLER = ("euler", "simple")
# Fixed, and not a dial. At one step over a source latent the seed moves almost
# nothing, and a seed control on a restoration would suggest there is a better
# roll waiting — which is the promise this backend is built not to make.
RESTORE_SEED = 0
# How the VAE is tiled. Core's own template's numbers, kept rather than tuned:
# they are what the model was shipped being run at, and this bench has no
# measurement of its own to put in their place.
TILE, TILE_OVERLAP = 512, 128
# How many frames of a chunk the next one re-does and blends over. Four is the
# model's own temporal grid (its frame counts are 4n+1), so an overlap of four
# costs one grid step and lands the join inside a fade rather than on a frame.
RESTORE_OVERLAP = 4

# How many times a model may be run over its own output to reach the target.
# Two is enough for every combination the dial allows (a x2 model asked for x4)
# and the cap is what stops a mislabelled x1 model looping forever.
MAX_PASSES = 2


class UpscaleError(bench.BenchError):
    """A file cannot be read, or it cannot be enlarged the way that was asked."""


# ---- the catalogue ----------------------------------------------------------
#
# Read by both ends, exactly as `control.TRACINGS` is: the surface builds its
# list and its dials from this over the wire. `note` says what the backend is
# *for* rather than what architecture it is, because the person choosing is
# choosing what to promise about the result.

BACKENDS = (
    {
        "id": "sharpen", "label": "Sharpen", "heavy": True,
        "note": "The detail that is already there, resolved and enlarged. Nothing "
                "is invented and nothing is re-imagined — a face comes back the "
                "same face, a logo the same logo. Soft footage comes back soft "
                "and bigger, which is the honest answer for it.",
        "needs": "an upscale model in models/upscale_models. RealESRGAN_x4plus is "
                 "the one core's own templates use — Comfy-Org/Real-ESRGAN_repackaged "
                 "on Hugging Face — and 4x-UltraSharp is the usual pick for "
                 "photographs. Nothing is downloaded from here.",
        "params": (
            {"key": "model", "kind": "choice", "from": ("upscale_models",),
             "label": "Model", "default": "", "options": (),
             "note": "Anything spandrel loads: ESRGAN and its descendants, DAT, "
                     "SwinIR, SPAN. The model's own factor is not this dial — a "
                     "x4 model asked for x2 is run once and brought back down, "
                     "which is sharper than running a x2 model."},
            {"key": "scale", "kind": "range", "min": 1.5, "max": 4, "step": 0.5,
             "default": 2, "label": "Bigger by",
             "note": "How much larger the result is than the source, whatever the "
                     "model's own factor happens to be. Past the model's factor "
                     "it is run a second time over its own output."},
        ),
    },

    {
        "id": "restore", "label": "Restore", "heavy": True,
        "note": "The picture repaired as it is enlarged — compression, grain and "
                "the softness of a frame that was small to begin with. It reads "
                "several frames of a clip at once, so movement holds together "
                "instead of boiling. Slower than Sharpen by a lot, and the right "
                "answer for footage that has something wrong with it.",
        "needs": "SeedVR2: a model in models/diffusion_models and its VAE in "
                 "models/vae. Comfy-Org/SeedVR2 on Hugging Face has both — "
                 "seedvr2_3b_int8_convrot.safetensors is the one to start with, "
                 "the 7B is sharper and wants more room, and "
                 "seedvr2_ema_vae_fp16.safetensors is the VAE for all of them. "
                 "Nothing is downloaded from here.",
        "params": (
            {"key": "model", "kind": "choice", "from": ("diffusion_models", "unet"),
             "label": "Model", "default": "", "options": (),
             "note": "A SeedVR2 checkpoint. 3B is the one that fits everywhere; "
                     "7B is sharper and slower. Any other model in the folder "
                     "will load and then have no conditioning to answer with."},
            {"key": "vae", "kind": "choice", "from": ("vae",),
             "label": "VAE", "default": "", "options": (),
             "note": "SeedVR2's own VAE. It is shared by every size of the "
                     "model, so this is set once whichever checkpoint is picked."},
            {"key": "scale", "kind": "range", "min": 1.5, "max": 4, "step": 0.5,
             "default": 2, "label": "Bigger by",
             "note": "The size the model works at. The picture is resampled to "
                     "it first and then repaired there, which is why this costs "
                     "time rather than only pixels."},
            {"key": "colour", "kind": "option",
             "options": ("lab", "wavelet", "adain", "none"), "default": "lab",
             "label": "Match colour",
             "note": "How the result is brought back to the source's colour. "
                     "Lab is the faithful one and the default; wavelet keeps "
                     "more of the model's own contrast; adain is a global tint; "
                     "none leaves the model's answer alone."},
            {"key": "frames", "kind": "range", "min": 5, "max": 33, "step": 4,
             "default": 13, "label": "Frames at a time",
             "note": "How much of a clip the model sees at once — more holds "
                     "movement together better and costs memory for it. This is "
                     "the dial to bring down when a clip runs out of VRAM. It "
                     "does nothing to a still."},
        ),
    },
)

BY_ID = {backend["id"]: backend for backend in BACKENDS}


def catalogue():
    """The backends, as the frontend reads them — with this machine filled in.

    Walks the model directories, so callers run it off the event loop.
    """
    return {"backends": bench.catalogue(BACKENDS)}


def _params(op, raw, weights=True):
    """Whatever arrived -> the values this backend actually takes.

    `weights` False leaves the model picks out, and it is not a shortcut: the
    plain half of the light box is Lanczos, which needs no weights at all, and a
    machine with nothing in `models/upscale_models` is exactly the machine that
    should still be shown what it would get for free. Asking for the model there
    would refuse the one picture the bench can honestly draw.
    """
    backend = BY_ID.get(str(op))
    if backend is None:
        raise UpscaleError(f"{op!r} is not a backend this pack knows")
    if not weights:
        backend = dict(backend, params=tuple(
            spec for spec in backend["params"] if spec["kind"] != "choice"))
    return bench.values(backend, raw, UpscaleError)


# ---- the backends -----------------------------------------------------------


def target(width, height, values):
    """The size a source of `width` x `height` comes back at.

    One function, asked by three callers that must agree: the still that is
    written, the encoder a clip is opened with, and the tile the light box
    shows. The rounding is here rather than in any of them because a preview
    that was a pixel wider than the file would be a preview of something else.
    """
    scale = float(values["scale"])
    return max(1, round(width * scale)), max(1, round(height * scale))


def _gan_model(name):
    def load():
        from comfy_extras.nodes_upscale_model import UpscaleModelLoader

        return UpscaleModelLoader.execute(name).result[0]

    return bench.hold("upscale", name, load)


def _sharpen(frame, values):
    """The GAN, run enough times to pass the target, then fitted to it exactly.

    Fitting down afterwards is not a compromise — it is what makes the dial mean
    what it says. Every one of these models has one factor it was trained at, so
    the choice is between running the model at its own factor and resampling, or
    offering a dial that only allows x4 and pretending the source's size was
    always convenient. Lanczos down off a model's native output is the sharper
    of the two, and it is what core's own 2K template does with a x4 model.
    """
    from .cutout import _node_context
    from comfy_extras.nodes_upscale_model import ImageUpscaleWithModel

    model = _gan_model(values["model"])
    wanted = float(values["scale"])
    picture = bench.torch_frame(frame)
    # The same two contexts a queued prompt would have wrapped the node in — no
    # grad, and a progress id of our own so the node's ProgressBar does not reach
    # for a prompt that is not running. See `cutout._node_context`.
    with bench.ONE_AT_A_TIME, _node_context():
        grown, passes = 1.0, 0
        while grown + 1e-3 < wanted and passes < MAX_PASSES:
            picture = ImageUpscaleWithModel.execute(model, picture).result[0]
            grown *= max(1.0, float(getattr(model, "scale", 1) or 1))
            passes += 1
            if float(getattr(model, "scale", 1) or 1) <= 1:
                # A model that does not enlarge cannot be run towards a target.
                break
    return bench.from_torch(picture)


def _resampled(frame, values):
    """The frame at the target size, by arithmetic alone.

    Where Sharpen ends up here only when its model has overshot, Restore *starts*
    here: SeedVR2 repairs a picture at the size it is given rather than enlarging
    one, so the resampling is the enlargement and the model is the repair.
    """
    return np.asarray(Image.fromarray(frame).resize(
        target(frame.shape[1], frame.shape[0], values), Image.LANCZOS))


def _restore_weights(model_name, vae_name):
    """SeedVR2's two files. Two, because the VAE is a separate download and is
    shared by every size of the model."""
    def load():
        import comfy.sd
        import comfy.utils

        model = comfy.sd.load_diffusion_model(
            bench.model_path(("diffusion_models", "unet"), model_name))
        # The conditioning node reads these two off the diffusion model, and a
        # checkpoint that is not SeedVR2 fails there with a sentence about
        # attribute structure. Asked here instead, where the answer is the name
        # of the file somebody picked.
        inner = getattr(getattr(model, "model", None), "diffusion_model", None)
        if not hasattr(inner, "positive_conditioning"):
            raise UpscaleError(
                f"{model_name} is not a SeedVR2 model. Restore reads SeedVR2 "
                "specifically — Comfy-Org/SeedVR2 on Hugging Face — and any "
                "other model in that folder will load and then have no "
                "conditioning to restore with.")
        sd, metadata = comfy.utils.load_torch_file(
            bench.model_path(("vae",), vae_name), return_metadata=True)
        vae = comfy.sd.VAE(sd=sd, metadata=metadata)
        vae.throw_exception_if_invalid()
        return model, vae

    return bench.hold("restore", (model_name, vae_name), load)


def _restore(frames, values):
    """SeedVR2 over a run of frames. -> the same number back, at the target size.

    The chain is core's own, in the order core's own template wires it: the
    frames are resampled to the target, padded to the model's grid, encoded
    tiled, turned into the conditioning that carries the source, sampled for one
    step, decoded tiled, and brought back to the source's colour. Every step is
    a `comfy_extras.nodes_seedvr` node or a core one — what this function owns is
    the numpy on either end and the order.

    It takes a list rather than a frame because that is the difference between
    Restore and Sharpen: the model attends across the frames it is given, so
    handing it one at a time would be running a video restorer as a photo
    retoucher and paying for the privilege.
    """
    import torch

    from comfy_extras.nodes_seedvr import (SeedVR2Conditioning, SeedVR2PostProcessing,
                                           SeedVR2Preprocess)
    import nodes

    from .cutout import _node_context

    model, vae = _restore_weights(values["model"], values["vae"])
    resized = np.stack([_resampled(frame, values) for frame in frames])
    # How much of the run the VAE sees at once. A still has one frame and no
    # temporal anything, so the window is opened wide enough to be irrelevant;
    # a run is left on core's own default window.
    window = 4096 if len(frames) == 1 else 64

    with bench.ONE_AT_A_TIME, _node_context():
        source = torch.from_numpy(resized).float().div_(255.0)
        padded = SeedVR2Preprocess.execute(source).result[0]
        latent = {"samples": vae.encode_tiled(
            padded, tile_x=TILE, tile_y=TILE, overlap=TILE_OVERLAP,
            tile_t=window, overlap_t=8)}
        positive, negative = SeedVR2Conditioning.execute(model, latent).result
        sampled = nodes.common_ksampler(
            model, RESTORE_SEED, RESTORE_STEPS, 1.0, *RESTORE_SAMPLER,
            positive, negative, latent, denoise=1.0)[0]
        decoded = nodes.VAEDecodeTiled().decode(
            vae, sampled, TILE, TILE_OVERLAP, window, 8)[0]
        # The reference is the resampled source rather than the padded one: the
        # padding is the model's grid and not part of the picture, and this is
        # also what trims the run back to the length that went in.
        answer = SeedVR2PostProcessing.execute(decoded, source, values["colour"]).result[0]

    out = bench.from_torch(answer.unsqueeze(0)) if answer.ndim == 3 else None
    if out is None:
        out = answer.clamp(0, 1).mul(255).round().to("cpu").numpy().astype(np.uint8)
    return [picture for picture in out[:len(frames)]]


def enlarge_many(frames, op, values):
    """A run of frames, upscaled. In and out are (H, W, 3) uint8 RGB.

    The answer is always exactly the target size, whatever the backend's own
    factor was, so nothing downstream has to know which model ran — an encoder
    was opened at that size before a frame was decoded.
    """
    if op == "sharpen":
        done = [_sharpen(frame, values) for frame in frames]
    elif op == "restore":
        done = _restore(frames, values)
    else:
        raise UpscaleError(f"{op!r} is not a backend this pack knows")
    fitted = []
    for source, picture in zip(frames, done):
        wanted = target(source.shape[1], source.shape[0], values)
        if (picture.shape[1], picture.shape[0]) != wanted:
            picture = np.asarray(Image.fromarray(picture).resize(wanted, Image.LANCZOS))
        fitted.append(picture)
    return fitted


def enlarge(frame, op, values):
    """One frame, upscaled — a still, or the tile in the light box."""
    return enlarge_many([frame], op, values)[0]


def chunk_of(op, values):
    """How many frames of a clip this backend takes at once."""
    return int(values.get("frames", 1)) if op == "restore" else 1


def overlap_of(op, values):
    """How many frames the next chunk re-does and blends over.

    None at all for work that is per-frame: two chunks of Sharpen join
    invisibly because neither knows the other happened. Restore's chunks are
    separate samples of the same clip, which is exactly the join that shows.
    """
    if op != "restore":
        return 0
    return min(RESTORE_OVERLAP, max(0, chunk_of(op, values) - 1))


# ---- the two answers ---------------------------------------------------------
#
# A tile for the light box, and a file for the shelf.


def _tile(frame, centre):
    """The `PREVIEW_TILE` square of `frame` around a point given in 0..1.

    Clamped to the frame rather than padded: a tile that ran off the edge would
    show the model's answer for a border that is not in the file. A source
    smaller than the tile is simply the whole source.
    """
    height, width = frame.shape[:2]
    side = min(PREVIEW_TILE, width, height)
    x, y = centre
    left = int(round(min(max(0.0, x), 1.0) * width - side / 2))
    top = int(round(min(max(0.0, y), 1.0) * height - side / 2))
    left = max(0, min(left, width - side))
    top = max(0, min(top, height - side))
    return frame[top:top + side, left:left + side]


def preview(path, op, raw, at=0.0, centre=(0.5, 0.5), plain=False):
    """-> (PNG bytes, `(width, height)`) of one tile, at the size it will be.

    `plain` is the other half of the comparison: the same tile enlarged by
    Lanczos to the same size, which is what the file would look like with no
    model in it at all. That is the honest thing to hold a backend against — not
    the source at half the size, which would flatter anything.
    """
    values = _params(op, raw, weights=not plain)
    cut = _tile(bench.source_frame(path, at, long_edge=0), centre)
    if plain:
        wanted = target(cut.shape[1], cut.shape[0], values)
        return bench.png(np.asarray(Image.fromarray(cut).resize(wanted, Image.LANCZOS)))
    return bench.png(enlarge(cut, op, values))


def run(filename, op, raw, trim=None, keep_sound=True, on_progress=None, at=None):
    """Upscale a file. -> where it landed under the output folder.

    `keep_sound` defaults to True where the tracing bench defaults it to False,
    and the difference is what the two are for: a tracing is a drawing handed to
    a model, and the sound of it is meaningless. This is the clip itself, larger,
    and one that came back mute would be one nobody could use.

    `at` asks for the single frame under the playhead as a still instead of the
    whole cut — the same door the tracing bench offers, and here it is what lets
    somebody pull one frame out of a clip at four times the size without
    spending the clip's whole render on it.
    """
    from . import media

    path = media.resolve(filename)
    values = _params(op, raw)
    out_dir = os.path.join(folder_paths.get_output_directory(), *outputs.UPSCALED.split("/"))
    if bench.is_video(path) and at is not None:
        at = max(0.0, float(at))
        frame = enlarge(bench.video_frame(path, at), op, values)
        name = bench.write_still(frame, out_dir, bench.stem(path, op, None, at))
        kind = "image"
    elif bench.is_video(path):
        name = bench.transcode(
            path, out_dir, bench.stem(path, op, trim),
            lambda frames: enlarge_many(frames, op, values),
            size=lambda width, height: target(width, height, values),
            trim=trim, chunk=chunk_of(op, values), overlap=overlap_of(op, values),
            keep_sound=keep_sound, on_progress=on_progress,
            # Every frame, because every frame is a model pass: a bar that had
            # not moved in a minute is a bench that has hung.
            every=1)
        kind = "video"
    else:
        name = bench.write_still(enlarge(bench.open_image(path), op, values),
                                 out_dir, bench.stem(path, op, trim))
        kind = "image"
    log.info("continuity: upscaled %s -> %s/%s", os.path.basename(path), outputs.UPSCALED, name)
    return {"path": f"{outputs.UPSCALED}/{name}", "kind": kind, "root": "output"}
