"""One still from the video model, as a graph. The PreStage's H3 branch.

`render.py` emits a video render and `render_image.py` emits an image-model
render; this emits a video render that stops at the first latent frame:

    loaders -> segment -> [preview] -> KSampler -> still slice -> VAEDecode -> save

Every node in that line except the slice is one the video path already uses, and
the segment node is *the* video segment node — same conditioning, same reference
ordering, same LoRA patching, same FL2VA/Ref2VA routing. That reuse is the whole
argument for the branch: a still made here is made by the weights that will
render the shot it is a keyframe for, at the canvas that shot will run at, with
no second model family loaded to get there.

Two things it does not take from `render.py`. There is no audio *decode*: the
sampled latent's audio half is generated and dropped, and the audio VAE is only
loaded when something attached has to be *encoded* into the conditioning — a
reference clip's soundtrack, which a still can cite exactly as a shot can. And there is
no chaining, because there is nothing to chain: one still is one pass.

"""

import json

from . import models, outputs, render

SEGMENT_NODE = "MiniMaxH3TimelineSegment"
STILL_NODE = "MiniMaxH3StillLatent"
SAVE_NODE = "MiniMaxH3SaveImage"

FILENAME_PREFIX = outputs.IMAGE_PREFIX


def weights_from_blob(data):
    """`models.Weights` for the still's request.

    Nothing to lift: the pre-stage's H3 branch is driven by the Creator's own
    editor, so the request carries a weights block in exactly the shape the
    video nodes' does — checkpoints, text encoder, VAEs, precision, devices, and
    the standing route.
    """
    return models.Weights.from_blob(data)


def emit(plan, weights, sampling, unique_id, filename_prefix=FILENAME_PREFIX):
    """-> the graph, which the caller finalizes with `render.expanded`.

    `sampling` is a `render.Sampling`, under the same widget names the two video
    nodes use.
    """
    from comfy_execution.graph_utils import GraphBuilder

    labels = ["This still"]
    payloads = [weights.routed(plan.payload)]
    # `render`'s own two helpers: the same early compile a video render does, so
    # a request that cannot compile fails before a loader is built, and only the
    # checkpoint it actually routes to gets one.
    compiled = render.compile_all(payloads, labels)
    where = render.routed(compiled, labels)
    # A still decodes no sound, but it can *cite* some: a reference audio clip,
    # or a reference video taken with its soundtrack, is encoded into the
    # conditioning exactly as it is for a video render. Read off the compiled
    # requests rather than the blob, so what decides is what the encoder will
    # actually reach for. Nothing attached, nothing loaded.
    audio = any(one.ref_audios or any(v.track == "picture+sound" for v in one.ref_videos)
                for one in compiled)
    models.check(weights, set(where), where, audio=audio)

    graph = GraphBuilder()
    links = models.emit_links(graph, weights, set(where), audio=audio)

    inputs = {
        "clip": links.clip,
        # sort_keys so an unchanged payload serialises identically every time —
        # this string is the segment node's cache key.
        "segment_data": json.dumps(payloads[0], sort_keys=True),
    }
    # Wire each VAE into the encoder only when this still encodes with it — a
    # keyframe or a cited reference. A text-only still needs the video VAE at
    # decode only (line below), so leaving it unwired keeps the loader off the
    # pre-sampling path exactly as the video render does.
    if compiled[0].encodes_video():
        inputs["vae"] = links.vae
    if links.audio_vae is not None and compiled[0].encodes_audio():
        inputs["audio_vae"] = links.audio_vae
    if links.model_fl2va is not None:
        inputs["model_fl2va"] = links.model_fl2va
    if links.model_ref2va is not None:
        inputs["model_ref2va"] = links.model_ref2va
    segment = graph.node(SEGMENT_NODE, **inputs)

    # The distilled H3 checkpoints run at cfg 1.0, where the negative is
    # skipped outright — the same zeroed conditioning the video path uses.
    against = graph.node("ConditioningZeroOut", conditioning=segment.out(1)).out(0)
    # taeh3 in the node body, exactly as on a video render. The preview is a
    # clip of the whole sampled latent, not of the frame that will be kept:
    # watching the motion is how you see the still is going somewhere.
    model = models.graph_preview(graph, segment.out(0), weights)

    sampled = graph.node(
        "KSampler", model=model, positive=segment.out(1), negative=against,
        latent_image=segment.out(2), seed=sampling.seed, steps=sampling.steps,
        cfg=sampling.cfg, sampler_name=sampling.sampler_name,
        scheduler=sampling.scheduler, denoise=1.0,
    )

    still = graph.node(STILL_NODE, samples=sampled.out(0), index=plan.index).out(0)
    image = graph.node("VAEDecode", samples=still, vae=links.vae).out(0)
    save = graph.node(SAVE_NODE, images=image, filename_prefix=filename_prefix)
    # The save node lives in an expanded graph on nobody's canvas; the stamp
    # files its result under the PreStage the user is looking at, which is what
    # lets the stage card show the still it just made.
    save.set_override_display_id(unique_id)

    return graph
