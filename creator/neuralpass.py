"""The DLSS 5 refiner as nodes: one over an IMAGE, one over the whole reel.

`neural.py` decides — whether the machine has the refiner, what a request is,
the one held pipeline. This is the half that holds pixels.

**The IMAGE node is the standalone surface and the still surface at once.** A
user assembling their own graph places it by hand; a pre-stage render gets one
written between its decode and its save (`emit_still`). Same node, same
defaults, because a still refined on the way out of a PreStage should be the
still the same node would make from the saved file.

**The reel node runs after the whole render, like the re-detail pass, and for
a different reason.** ReDetail runs at the end because it changes the size and
a seam that inherited a bigger frame would hand the next segment the wrong
canvas. This keeps the size — it *could* run inline. It runs at the end anyway
because the spec's seam hypothesis is exactly the thing to keep out of v1: a
refined tail handed to the next segment as its anchor trades a seam between
shots for a jump inside one (the refined anchor no longer matches the frames
before it). A uniform pass over the finished reel, with the temporal history
carried across the parts in play order, puts every frame in the same domain
and leaves the seams where the render put them. That is the form worth
measuring, and it is the only form this builds.

**Memory is per frame here, not per pass.** A pass is a memmap read one frame
at a time and written back a chunk at a time through `spill.rewrite`, so the
peak is one network input (about a gigabyte per megapixel) rather than the
pass — which is what makes a ten-second 768p pass cost what one frame costs.
"""

import logging

import numpy as np
import torch

import comfy.model_management
import comfy.utils
from comfy_api.latest import io

from . import neural, spill
from .timeline import REEL_TYPE

REFINE_NODE = "ContinuityNeuralRefine"
PASS_NODE = "ContinuityNeuralPass"

# How many refined frames are gathered before they are handed to the spill.
# Sixteen 768p frames is 75 MB of float32, which is nothing next to the
# network's own working set.
CHUNK = 16

_PROFILE_TIP = ("The model's own style presets. Standard is what the driver runs; "
                "natural and cinematic move its style index; neutral switches the "
                "local tone and structure off.")
_PRECISION_TIP = ("Reference is float32 with the driver's own rounding points and "
                  "matches it to 0.005 MAE; fast is float16 on the GPU and halves "
                  "the memory.")


def _progress(total):
    bar = comfy.utils.ProgressBar(total)
    done = 0

    def tick():
        nonlocal done
        done += 1
        bar.update_absolute(done, total)

    return tick


class ContinuityNeuralRefine(io.ComfyNode):
    """NVIDIA's DLSS 5 neural renderer over an IMAGE, at the size it already is."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=REFINE_NODE,
            display_name="Continuity Neural Refine (DLSS 5)",
            category="Continuity",
            description=(
                "Re-draws material — skin, hair, fabric, contact shadows, subsurface — "
                "with NVIDIA's DLSS 5 neural renderer. Not an upscaler: the picture "
                "comes back the size it went in. A batch is refined as a clip, with "
                "the previous frame's result carried into the next. Needs the mlxdlss "
                "package and weights extracted from your own DLSS DLL; see the "
                "settings page. About a gigabyte of VRAM per megapixel, times the "
                "square of the processing scale."
            ),
            inputs=[
                io.Image.Input("image"),
                io.Mask.Input("mask", optional=True,
                    tooltip="Where to refine, per pixel. 1 is full strength, 0 leaves "
                            "the source untouched. It drives the model's blend, tone "
                            "and structure together. Needs the processing scale at 1."),
                io.Combo.Input("profile", options=list(neural.PROFILES),
                               default=neural.DEFAULT_PROFILE, tooltip=_PROFILE_TIP),
                io.Float.Input("processing_scale", default=neural.DEFAULT_SCALE,
                               min=neural.MIN_SCALE, max=neural.MAX_SCALE, step=0.25,
                               tooltip="Run the network on the picture resampled by this "
                                       "factor and bring the result back. Finer material "
                                       "past 1, and memory grows with the square. Ignored "
                                       "on a batch with history on, which runs at 1."),
                io.Float.Input("detail_strength", default=neural.DEFAULT_DETAIL,
                               min=neural.MIN_DETAIL, max=neural.MAX_DETAIL, step=0.05,
                               tooltip="How much of the model's high-frequency change is "
                                       "kept. 1 is its own answer."),
                io.Float.Input("colour_strength", default=neural.DEFAULT_COLOUR,
                               min=neural.MIN_COLOUR, max=neural.MAX_COLOUR, step=0.05,
                               tooltip="How much of the model's low-frequency change — "
                                       "tone and colour — is kept."),
                io.Float.Input("intensity", default=neural.DEFAULT_INTENSITY,
                               min=neural.MIN_INTENSITY, max=neural.MAX_INTENSITY, step=0.05,
                               tooltip="The blend of the refined picture over the source."),
                io.Combo.Input("precision", options=list(neural.PRECISIONS),
                               default=neural.DEFAULT_PRECISION, tooltip=_PRECISION_TIP),
                io.Boolean.Input("history", default=True,
                    tooltip="On a batch, carry each frame's result into the next through "
                            "optical flow and the model's learned blend, so a clip does "
                            "not boil. Off refines every frame on its own."),
                io.Int.Input("frame_index", default=0, min=0, max=0x7fffffff,
                    tooltip="Seeds the model's deterministic noise; frames of a batch "
                            "count up from it. The same picture at the same index is "
                            "the same answer."),
            ],
            outputs=[io.Image.Output()],
        )

    @classmethod
    def execute(cls, image, profile, processing_scale, detail_strength, colour_strength,
                intensity, precision, history, frame_index, mask=None) -> io.NodeOutput:
        request = neural.Request(
            on=True, profile=profile, scale=processing_scale, detail=detail_strength,
            colour=colour_strength, intensity=intensity, precision=precision)
        try:
            neural.require()
            frames = image.detach().to("cpu").float().numpy()
            masks = mask.detach().to("cpu").float().numpy() if mask is not None else None
            out = refine_batch(frames, request, masks=masks, history=history,
                               frame_index=int(frame_index))
        except neural.NeuralError as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            # The same policy as every other model this pack holds: the graph
            # is loaded once and kept, but it does not keep the GPU.
            neural.release()
        return io.NodeOutput(torch.from_numpy(out))


def refine_batch(frames, request, masks=None, history=True, frame_index=0, tick=None):
    """(N, H, W, 3) float or uint8 -> (N, H, W, 3) float32 in 0..1.

    A batch of one, or a batch refined without history, goes through the
    single-frame path with the frame's index as its noise seed. A batch with
    history goes through upstream's temporal session, one frame after another,
    which is where a clip's steadiness comes from.
    """
    count = int(frames.shape[0])
    height, width = int(frames.shape[1]), int(frames.shape[2])
    tick = tick or _progress(count)
    mask_at = (lambda index: masks[min(index, masks.shape[0] - 1)]) if masks is not None else (lambda index: None)
    out = np.empty((count, height, width, 3), dtype=np.float32)
    if count > 1 and history:
        sequence = neural.Sequence(request, frame_index=frame_index)
        logging.info("continuity: DLSS 5 refine, %d frames of %dx%d with %s motion, "
                     "about %.1f GB", count, width, height, sequence.motion,
                     neural.estimate_gb(width, height, 1.0, request.precision))
        for index in range(count):
            comfy.model_management.throw_exception_if_processing_interrupted()
            out[index] = sequence.process(frames[index], mask=mask_at(index))
            tick()
        return out
    for index in range(count):
        comfy.model_management.throw_exception_if_processing_interrupted()
        out[index] = neural.refine_frame(frames[index], request, mask=mask_at(index),
                                         frame_index=frame_index + index)
        tick()
    return out


class ContinuityNeuralPass(io.ComfyNode):
    """Every generated pass on a reel through the DLSS 5 refiner, in play order.

    Written into the graph by the render loop (`core/emit.py`) after the last
    pass is on the reel and after a re-detail pass if there is one — it keeps
    whatever size the reel is at by then.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=PASS_NODE,
            display_name="Continuity Neural Pass (DLSS 5)",
            category="Continuity/internal",
            description="Refines every generated pass on the reel with NVIDIA's DLSS 5 "
                        "neural renderer, history carried across the parts in play "
                        "order. Written into the graph by render.emit.",
            is_dev_only=True,
            inputs=[
                io.Custom(REEL_TYPE).Input("reel"),
                io.Combo.Input("profile", options=list(neural.PROFILES),
                               default=neural.DEFAULT_PROFILE, tooltip=_PROFILE_TIP),
                io.Float.Input("detail_strength", default=neural.DEFAULT_DETAIL,
                               min=neural.MIN_DETAIL, max=neural.MAX_DETAIL, step=0.05),
                io.Float.Input("colour_strength", default=neural.DEFAULT_COLOUR,
                               min=neural.MIN_COLOUR, max=neural.MAX_COLOUR, step=0.05),
                io.Float.Input("intensity", default=neural.DEFAULT_INTENSITY,
                               min=neural.MIN_INTENSITY, max=neural.MAX_INTENSITY, step=0.05),
                io.Combo.Input("precision", options=list(neural.PRECISIONS),
                               default=neural.DEFAULT_PRECISION, tooltip=_PRECISION_TIP),
                io.Int.Input("frame_index", default=0, min=0, max=0x7fffffff,
                    tooltip="Seeds the model's deterministic noise for the first frame; "
                            "every frame after counts up from it, so a re-queue is the "
                            "same answer."),
            ],
            outputs=[io.Custom(REEL_TYPE).Output(display_name="reel")],
        )

    @classmethod
    def execute(cls, reel, profile, detail_strength, colour_strength, intensity,
                precision, frame_index) -> io.NodeOutput:
        request = neural.Request(
            on=True, profile=profile, detail=detail_strength, colour=colour_strength,
            intensity=intensity, precision=precision)
        parts = list(reel or [])
        passes = [index for index, part in enumerate(parts) if "pass" in part]
        if not passes:
            raise RuntimeError("the neural pass was given a reel with nothing "
                               "generated on it — there is nothing to refine.")
        try:
            neural.require()
            out = list(parts)
            total = sum(int(parts[index]["pass"]["frames"]) for index in passes)
            tick = _progress(total)
            sequence = neural.Sequence(request, frame_index=int(frame_index))
            logging.info("continuity: DLSS 5 pass over %d parts, %d frames, %s motion",
                         len(passes), total, sequence.motion)
            previous = None
            for index in passes:
                # History runs across parts that follow one another on the reel.
                # A clip spliced between two passes is footage nobody refined,
                # so the pass after it starts its history afresh.
                if previous is not None and index != previous + 1:
                    sequence.reset()
                out[index] = {"pass": cls._one(parts[index]["pass"], sequence, tick)}
                previous = index
            if sequence.scene_cuts:
                logging.info("continuity: the neural pass reset its history at %d "
                             "scene cuts", sequence.scene_cuts)
        except neural.NeuralError as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            neural.release()
        return io.NodeOutput(out)

    @classmethod
    def _one(cls, source, sequence, tick):
        """One pass off the reel, refined. -> the spec for its replacement."""
        frames = spill.open_frames(source)
        count = int(source["frames"])

        def blocks():
            for start in range(0, count, CHUNK):
                stop = min(start + CHUNK, count)
                block = np.empty((stop - start, frames.shape[1], frames.shape[2], 3),
                                 dtype=np.float32)
                for offset in range(stop - start):
                    comfy.model_management.throw_exception_if_processing_interrupted()
                    block[offset] = sequence.process(frames[start + offset])
                    tick()
                yield torch.from_numpy(block)

        return spill.rewrite(source, blocks())


# ---- writing them into graphs --------------------------------------------------


def emit_still(graph, image, request, frame_index=0):
    """The refine node between a still's decode and its save. -> the image link."""
    return graph.node(
        REFINE_NODE, image=image, profile=request.profile,
        processing_scale=float(request.scale), detail_strength=float(request.detail),
        colour_strength=float(request.colour), intensity=float(request.intensity),
        precision=request.precision, history=False, frame_index=int(frame_index),
    ).out(0)


def emit(graph, reel, request, seed=0):
    """The reel pass, wired onto the end of a render. -> the new reel link.

    The seed is the render's own, so a re-queue refines to the same frames,
    and a piece re-rolled refines to different noise the way it samples to.
    """
    return graph.node(
        PASS_NODE, reel=reel, profile=request.profile,
        detail_strength=float(request.detail), colour_strength=float(request.colour),
        intensity=float(request.intensity), precision=request.precision,
        frame_index=int(seed) % 0x7fffffff,
    ).out(0)


NODES = [ContinuityNeuralRefine, ContinuityNeuralPass]
