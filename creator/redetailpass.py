"""The re-detail pass: every pass on the reel, re-rendered at twice the canvas.

`redetail.py` decides what the backend is and what it is allowed to promise;
this is the half that holds the weights and the pixels.

**Why it runs over the whole reel and not beside the face pass.** The face pass
runs inline, between one pass being written and the next being emitted, because
a seam inherits the frames of the pass in front and should inherit the repaired
ones. This is the opposite case: what comes back is a *different size*, and a
seam that inherited it would hand the next segment a guide at twice the canvas
it is about to sample at. So it runs once, at the end, after every pass has been
written and every seam has already taken what it needed.

That also makes the chunking free. ReDetail's own CLI works hard to split a long
clip on its own cuts, because a split with no cut near it can show a seam; a reel
is already one part per shot, and the cuts are where the parts meet.

**One node for the whole reel, not one per part.** The four files this loads are
21.5 GB, 15.4 GB and two VAEs, and they are loaded for a pass that runs at the
very end of a render that may have spent an hour in another family's weights. One
node means one set of loaders, executed only when the reel reaches them, and the
parts re-rendered in play order inside a single call.

**What rides through untouched.** The soundtrack — `spill.rewrite` points the new
pass at the same audio file, exactly as the face pass does, so nothing is
re-decoded and nothing is re-rolled. The model is still handed the sound as a
reference (`LTXVReferenceAudio`), because a packed AV latent is what it was
trained to denoise and the picture attends to the sound; what it generates is
thrown away.

**Where the seams are still honest and where they are not.** Each part is
anchored on its own first frame, which is what ReDetail does per chunk. Across a
hard cut that is exactly right. Across a *feathered* seam — two passes that
continue one another — each part invents its detail independently, so the join
can show it. That is the one thing this pass does not yet solve, and it is
written here rather than left to be discovered.
"""

import logging

import numpy as np
import torch

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview
from comfy_api.latest import io

from . import models as core, redetail, spill
from .families.ltx25.segment import _empty_video_latent
from .timeline import REEL_TYPE

REDETAIL_NODE = "MiniMaxReDetailPass"

# How many frames are converted at a time, in either direction. The guide is
# built up to this size at a step and the decoded pass is streamed out at it, so
# neither the read nor the write is ever a second copy of the whole pass.
CHUNK = 16


class ReDetailError(RuntimeError):
    """The re-detail pass could not run on this reel."""


def _core_node(node_id):
    """One of core's LTX nodes, by registry key — see `ltx25/segment._core`."""
    import nodes

    try:
        return nodes.NODE_CLASS_MAPPINGS[node_id]
    except KeyError:
        raise ReDetailError(
            f"the re-detail pass needs core's '{node_id}' node, which this "
            f"ComfyUI does not have. It runs on LTX 2.5, so it needs a ComfyUI "
            f"new enough to ship the LTX-AV nodes; update it, or set the "
            f"upscale pill back to a pass this family makes on its own."
        ) from None


def _guide(frames, length):
    """The finished pass as the model's guide: `[length, H, W, 3]`, 0..1 float.

    Padded up to `length` with its own last frame rather than trimmed down to it
    — see `redetail.padded_frames`. The padding is re-generated with everything
    else and dropped after decode, which is what makes an H3 pass's `17n+5`
    length cost a few frames of sampling instead of a silently missing tail.
    """
    count, height, width = frames.shape[0], frames.shape[1], frames.shape[2]
    out = torch.empty((length, height, width, 3), dtype=torch.float32)
    for start in range(0, count, CHUNK):
        stop = min(start + CHUNK, count)
        block = torch.from_numpy(np.array(frames[start:stop, ..., :3]))
        out[start:stop] = block.float().div_(255.0)
    if length > count:
        out[count:] = out[count - 1]
    return out


def _blocks(decoded, count):
    """The re-detailed pass, a chunk at a time, for `spill.rewrite` to stream.

    Trimmed back to the length that went in: everything past `count` is the
    padding `_guide` added to reach the frame grid.
    """
    for start in range(0, count, CHUNK):
        yield decoded[start:min(start + CHUNK, count), ..., :3]


class MiniMaxReDetailPass(io.ComfyNode):
    """Every generated pass on a reel, re-rendered at twice its canvas.

    Written into the graph by the render loop (`core/emit.py`) after the last
    pass has been added to the reel, when the piece's upscale pill names this
    backend. See the module docstring for the whole of why.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=REDETAIL_NODE,
            display_name="MiniMax ReDetail Pass",
            category="MiniMax/internal",
            description="Re-renders every pass on the reel through LTX 2.5's pixel "
                        "spatial upscaler at twice the canvas. Written into the graph "
                        "by render.emit.",
            is_dev_only=True,
            inputs=[
                io.Model.Input("model",
                    tooltip="LTX 2.5's transformer. Not the model the piece rendered "
                            "with — this pass is a second family's weights."),
                io.Clip.Input("clip",
                    tooltip="LTX 2.5's text encoder. The pass runs on empty prompts, so "
                            "what this computes is a constant."),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.Custom(REEL_TYPE).Input("reel"),
                io.String.Input("ic_lora",
                    tooltip="The x2 pixel spatial upscaler IC-LoRA, from models/loras."),
                io.Int.Input("width", default=1536, min=64, max=16384, step=64,
                    tooltip="The finished width — twice what was sampled, on the /64 "
                            "grid the guide's dilation needs."),
                io.Int.Input("height", default=2688, min=64, max=16384, step=64),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
            ],
            outputs=[io.Custom(REEL_TYPE).Output(display_name="reel")],
        )

    @classmethod
    def execute(cls, model, clip, vae, audio_vae, reel, ic_lora, width, height,
                seed) -> io.NodeOutput:
        import nodes

        parts = list(reel or [])
        passes = [index for index, part in enumerate(parts) if "pass" in part]
        if not passes:
            raise ReDetailError(
                "the re-detail pass was given a reel with nothing generated on "
                "it — there is nothing to re-render.")

        width, height = int(width), int(height)
        # The IC-LoRA goes onto the transformer here rather than through a loader
        # in the graph: it is one file answering two questions — what to patch
        # the model with, and what the guide's downscale factor is, which
        # `GetICLoRAParameters` reads out of its own metadata.
        if not str(ic_lora or "").strip():
            raise ReDetailError(
                "the re-detail pass has no IC-LoRA. Open the node's weights "
                "control and pick the x2 pixel spatial upscaler from "
                "models/loras — it is the whole of what makes this pass a "
                "re-detail rather than a re-render.")
        patched = nodes.LoraLoaderModelOnly().load_lora_model_only(
            model, ic_lora, 1.0)[0]
        parameters = _core_node("GetICLoRAParameters").execute(patched)[0]

        # Empty prompts, both of them. The IC-LoRA's guide is the whole of what
        # this pass is told to draw, and a description of the shot would be a
        # second opinion about a picture that already exists.
        tokens = clip.tokenize("")
        conditioning = clip.encode_from_tokens_scheduled(tokens)

        out = list(parts)
        for position, index in enumerate(passes):
            comfy.model_management.throw_exception_if_processing_interrupted()
            out[index] = {"pass": cls._one(
                parts[index]["pass"], patched, parameters, conditioning,
                vae, audio_vae, width, height, seed + position)}
        return io.NodeOutput(out)

    @classmethod
    def _one(cls, source, model, parameters, conditioning, vae, audio_vae,
             width, height, seed):
        """One pass off the reel, re-detailed. -> the spec for its replacement."""
        import nodes

        frames = spill.open_frames(source)
        count = int(source["frames"])
        source_w, source_h = int(source["width"]), int(source["height"])
        if (source_w * redetail.SCALE, source_h * redetail.SCALE) != (width, height):
            raise ReDetailError(
                f"this pass is {source_w}x{source_h} and the re-detail pass was "
                f"built for {width // redetail.SCALE}x{height // redetail.SCALE} "
                f"— every part of one reel is rendered at one canvas, so this is "
                f"a graph built against a different piece than the one it ran on.")

        length = redetail.padded_frames(count)
        logging.info(
            "[MiniMax] re-detail: %d frames (%d on the grid) from %dx%d to %dx%d "
            "— %.0f frame-megapixels",
            count, length, source_w, source_h, width, height,
            redetail.frame_megapixels(length, width, height))

        latent = _empty_video_latent(width, height, length)
        # The pass's own first frame, pinned before the guide goes on. It is what
        # keeps a chunk from drifting away from where it starts, and it is what
        # ReDetail's own graph does per chunk — see the module docstring for the
        # seam this does *not* fix.
        anchor = _guide(frames[:1], 1)
        latent = _core_node("LTXVImgToVideoInplace").execute(
            vae, anchor, latent, redetail.ANCHOR_STRENGTH)[0]

        # The guide: the whole finished pass, at strength 1. With the IC-LoRA's
        # downscale factor of 2 this is encoded at exactly the size it already
        # is — half the target — so the picture the model is given back is the
        # picture that was rendered, resampled by nothing.
        positive, negative, latent = _core_node("LTXVAddGuide").execute(
            conditioning, conditioning, vae, latent, _guide(frames, length), 0,
            redetail.GUIDE_STRENGTH, iclora_parameters=parameters)

        model, positive, negative = cls._sound(
            source, model, positive, negative, audio_vae)
        audio_latent = _core_node("LTXVEmptyLatentAudio").execute(
            length, float(source.get("fps") or redetail.RULES.fps), 1, audio_vae)[0]
        packed = _core_node("LTXVConcatAVLatent").execute(latent, audio_latent)[0]

        sampled = cls._sample(model, positive, negative, packed, seed)

        # The guides come off before anything decodes: `LTXVAddGuide` appends the
        # guide's condition latent past the end of the sequence, and the crop is
        # a slice in time that the packed soundtrack shares — so the pass is
        # unpacked, cropped, and only the picture is decoded. The sound is not:
        # the rewritten spec points at the file the pass already had.
        split = _core_node("LTXVSeparateAVLatent").execute(sampled)
        cropped = _core_node("LTXVCropGuides").execute(positive, negative, split[0])[2]
        # Core's own decoder, which retries tiled by itself if the full-size
        # decode runs out of memory (`comfy/sd.py`). ReDetail's workflow pins
        # tiled decoding because a graph cannot make that decision at runtime;
        # this can, so it takes the sharper one where it fits.
        decoded = nodes.VAEDecode().decode(vae, cropped)[0]
        del sampled, split, cropped
        comfy.model_management.soft_empty_cache()

        return spill.rewrite(source, _blocks(decoded, count),
                             geometry=(width, height))

    @classmethod
    def _sound(cls, source, model, positive, negative, audio_vae):
        """The pass's own soundtrack, as a reference the model draws to.

        A silent pass is not an error here, which is the one place this differs
        from ReDetail's own graph: it feeds the encoder directly and a clip with
        no audio track stops the render, which is why its README opens with an
        ffmpeg line that muxes silence in. Every pass this pack makes has sound,
        and the one that does not is a soundless H3 render — so the reference is
        simply not set, the empty audio latent is packed as usual, and the pass
        goes through.
        """
        if "audio_path" not in source:
            logging.info("[MiniMax] re-detail: this pass decoded no sound, so "
                         "the model is drawing to the picture alone")
            return model, positive, negative
        seconds = int(source["frames"]) / float(source.get("fps") or redetail.RULES.fps)
        return _core_node("LTXVReferenceAudio").execute(
            model, positive, negative, spill.sound(source, seconds), audio_vae,
            # No identity guidance. Its extra forward pass per step is for
            # transferring a speaker's identity onto generated speech; here the
            # soundtrack is already the pass's own and is thrown away after
            # sampling, so the pass would be paid for nothing.
            0.0, 0.0, 1.0)[:3]

    @classmethod
    def _sample(cls, model, positive, negative, latent, seed):
        """The eight steps, on the schedule the model shipped with.

        Not the family's sampler row and not `LTXVScheduler`: the distilled
        upscaler has one curve, it is fixed, and none of the widgets a piece
        carries says anything about it (`redetail.SIGMAS`).
        """
        sigmas = torch.FloatTensor([float(value)
                                    for value in redetail.SIGMAS.split(",")])
        guider = comfy.samplers.CFGGuider(model)
        guider.set_conds(positive, negative)
        guider.set_cfg(redetail.CFG)

        samples = latent["samples"]
        samples = comfy.sample.fix_empty_latent_channels(
            guider.model_patcher, samples,
            latent.get("downscale_ratio_spacial"),
            latent.get("downscale_ratio_temporal"))
        noise = comfy.sample.prepare_noise(samples, seed)
        sampled = guider.sample(
            noise, samples, comfy.samplers.sampler_object(redetail.SAMPLER),
            sigmas, denoise_mask=latent.get("noise_mask"),
            callback=latent_preview.prepare_callback(
                guider.model_patcher, sigmas.shape[-1] - 1),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed)
        out = {key: value for key, value in latent.items()
               if key not in ("downscale_ratio_spacial", "downscale_ratio_temporal")}
        out["samples"] = sampled.to(comfy.model_management.intermediate_device())
        return out


def emit(graph, family, links, weights, compiled, reel, seed):
    """The re-detail pass, wired onto the end of a render. -> the new reel link.

    The loaders are built here and nowhere else, and only on the way to this
    node: a piece that never asks for the pass never names LTX 2.5's files in
    its graph, and a render that does asks ComfyUI to load them at the point the
    reel reaches this node rather than at the top of the render.

    **A piece that renders on LTX 2.5 borrows its own.** The four shared slots
    are the same files under the same slot ids, and building a second set would
    put a 21.5 GB transformer in memory twice for one render. So the family's
    links answer where the family is the one whose weights these are, and the
    backend's own block answers everywhere else — which is what
    `redetail.needed` says out loud.
    """
    redetail.check(weights, family.id)
    target = next(one.redetail for one in compiled if one is not None and one.redetail)

    if family.id == redetail.SHARED_WITH:
        loaded = {name: getattr(links, name) for name in ("dit", "clip", "vae",
                                                          "audio_vae")}
    else:
        loaded = {}
        for name in ("dit", "clip", "vae", "audio_vae"):
            slot = redetail.SLOTS[name]
            filename = weights.get(name)
            wrapper, extra = core.loader_for(slot.loader, None, filename)
            inputs = {slot.input: filename, **(slot.extra or {})}
            if not core.is_gguf(filename) and slot.loader == "UNETLoader":
                inputs["weight_dtype"] = weights.dtype
            loaded[name] = graph.node(wrapper, **inputs, **extra).out(0)

    return graph.node(
        REDETAIL_NODE, model=loaded["dit"], clip=loaded["clip"],
        vae=loaded["vae"], audio_vae=loaded["audio_vae"], reel=reel,
        ic_lora=weights.get("ic_lora"),
        width=target.width, height=target.height, seed=seed).out(0)


NODES = [MiniMaxReDetailPass]
