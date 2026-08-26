"""One still from the video model: the PreStage's MiniMax H3 branch, compile
and graph together.

The other pre-stage architectures are image models. This one is not: H3 is the
video model the rest of the pack already loads, and a still from it is *a video
generation whose first latent frame is decoded as a picture*. So the compile
half reduces a pre-stage blob to exactly the request shape
`compile.compile_request` already takes, and `emit` builds a video render that
stops at the first latent frame:

    loaders -> segment -> [preview] -> KSampler -> still slice -> VAEDecode -> save

Every node in that line except the slice is one the video path already uses, and
the segment node is *the* video segment node — same conditioning, same reference
ordering, same LoRA patching, same FL2VA/Ref2VA routing. That reuse is the whole
argument for the branch: a still made here is made by the weights that will
render the shot it is a keyframe for, at the canvas that shot will run at, with
no second model family loaded to get there — and it is why this module lives in
the family package: everything about it is H3 protocol.

Two things `emit` does not take from the video loop. There is no audio
*decode*: the sampled latent's audio half is generated and dropped, and the
audio VAE is only loaded when something attached has to be *encoded* into the
conditioning — a reference clip's soundtrack, which a still can cite exactly as
a shot can. And there is no chaining, because there is nothing to chain: one
still is one pass.

**Why the first latent frame is a still at all.** The H3 VAE is causal on the
17k+5 <-> 5k+2 grid: a 5-frame clip has two latent frames, and the first of them
is a function of frame 0 alone. Encoding a single image produces that same
one-frame latent (core's `downscale_ratio` returns 1 for a single frame), which
is what the experimental T=1 image decoder was trained against. Decoding latent
index 0 is therefore not a trick — it is the one temporal slice the image VAE
was fitted to.

**How long a clip, and which frame of it.** The DiT's trained range is 124-362
frames (`canvas.TRAINED_MIN_FRAMES`), so the short end of `STILL_LENGTHS` is
off-distribution temporally even though the *latent* it produces is in
distribution spatially. Both are pills rather than constants because the answer
is a property of the weights, not of this code, and the weights keep changing.

The compile half is pure — no torch, no ComfyUI, no disk — and the suites load
it without booting a server, which is why `emit` imports the render loop lazily
rather than at the top. The canvas and duration rules are `canvas.py`'s,
because they are the video model's.
"""

from dataclasses import dataclass

from ... import canvas, models as core, outputs
from ...compile import CHECKPOINTS, CompileError, active_loras, collect_triggers
from . import declare, models as slots

ARCH = "minimax"

# The shortest legal clip: 5 frames, two latent frames, the cheapest sampler
# pass H3 can be asked for. The default because a still only needs the first
# latent frame and everything past it is paid for and thrown away.
DEFAULT_FRAMES = 5

# What the length pill offers. Every one is a legal 17n+5 count; the top of the
# list is the bottom of the trained range, so the pill spans "cheapest possible"
# to "what the weights actually saw".
STILL_LENGTHS = (5, 22, 39, 56, 90, 124)

# Which latent frame is decoded. 0 is the causal first frame — the slice the
# image VAE was trained on. Negative indexes from the end, so -1 is the last
# frame of the clip and is how you ask for "the shot a moment later".
DEFAULT_LATENT_INDEX = 0

# How the prompt reaches the DiT. "context-ir" is what a video render does: the
# shot description is composed into the model's documented Context-IR form,
# duration line and all. "plain" sends the typed sentence verbatim through
# `prompt_override`, which is the same escape hatch the refiner uses — worth
# having because a Context-IR block describes a 0.21-second video, and whether
# that helps or hurts a still is exactly the kind of thing only a render says.
PROMPT_MODES = ("context-ir", "plain")
DEFAULT_PROMPT_MODE = "context-ir"


def latent_frames(frames):
    """Frames -> how many latent frames the VAE packs them into.

    Mirror of core's `nodes_minimax_h3.video_latent_t`, kept here so an index
    can be refused before anything is queued. 5 -> 2, 22 -> 5, 124 -> 25.
    """
    return 2 if frames <= 5 else ((frames - 5) // 17) * 5 + 2


def resolve_index(index, frames):
    """A latent index (possibly negative) -> a real one, or refuse it."""
    total = latent_frames(frames)
    resolved = index if index >= 0 else total + index
    if not 0 <= resolved < total:
        raise CompileError(
            f"latent frame {index} does not exist in a {frames}-frame clip — "
            f"it packs into {total} latent frames (0..{total - 1})"
        )
    return resolved


@dataclass(frozen=True)
class StillPlan:
    """One sampler pass, and the frame taken out of it."""

    request: dict
    frames: int = DEFAULT_FRAMES
    index: int = DEFAULT_LATENT_INDEX
    prompt_override: str = None
    # Whether anything attached will be encoded as sound. False for almost every
    # still, and that is what leaves the audio VAE unloaded.
    audio: bool = False

    @property
    def payload(self):
        """The segment payload — the same shape `MiniMaxH3Creator` builds."""
        payload = {"request": self.request, "continue": False, "continue_audio": False}
        if self.prompt_override:
            payload["prompt_override"] = self.prompt_override
        return payload


def _checkpoint(request):
    """Which H3 checkpoint this still will route to.

    The same derivation `compile._resolve_checkpoint` makes, needed here only so
    the plain-prompt branch can collect the trigger words of the LoRAs that will
    actually be patched on. The authoritative answer is still the compiled
    request's, which is what the render path reads.
    """
    route = ((request.get("models") or {}).get("route")) or "auto"
    if route in CHECKPOINTS:
        return route
    pin = request.get("checkpoint") or "auto"
    if pin in CHECKPOINTS:
        return pin
    refs = [a for a in request.get("assets") or [] if a.get("role", "reference") == "reference"]
    return "ref2va" if refs else "fl2va"


def needs_audio(request):
    """Whether this still will reach for the audio VAE.

    A reference audio clip, or a reference video cited for its soundtrack. Most
    stills touch neither, and a loader in the graph is a file loaded whether or
    not anything reads it — so this is what decides the audio VAE is required.
    """
    for asset in request.get("assets") or []:
        if asset.get("role", "reference") != "reference":
            continue
        if asset.get("kind") == "audio":
            return True
        if asset.get("kind") == "video" and asset.get("track") in ("picture+sound", "sound"):
            return True
    return False


def _frames(raw):
    """A requested frame count -> the legal 17n+5 count actually generated."""
    try:
        frames = int(raw)
    except (TypeError, ValueError):
        raise CompileError("the still length must be a whole number of frames")
    return canvas.frames_for_seconds(max(1, frames) / declare.RULES.fps, declare.RULES)


def _block(data):
    block = data.get(ARCH)
    return block if isinstance(block, dict) else {}


def _request(block, frames):
    """The request one pass generates from: the still's own, at this length.

    A copy rather than the stored dict, because the length it is generated at
    is the still's setting rather than the request's.
    """
    request = dict(block.get("request") or {})
    if not isinstance(request, dict):
        raise CompileError("the still's request must be a JSON object")
    # The duration the video side speaks in. `frames` is already snapped, so
    # `frames_for_seconds` inside `compile_request` lands back on it exactly.
    request["duration_s"] = canvas.seconds_for_frames(frames, declare.RULES)
    # Never two-pass: a still past the native edge upscales through the
    # single-image VAE decode, and the still graph has no refine pass to hand
    # a capped canvas to — left unpinned, `compile_request` would sample at
    # 768 and the slider above it would quietly do nothing.
    request["upscale"] = "direct"
    return request


def _plain_prompt(request, checkpoint):
    """The typed sentence, trigger words in front, and nothing composed.

    Same construction as the video body's prefix — a word only counts if its
    LoRA is actually in this run — because that is the one part of the composed
    prompt an override would otherwise drop on the floor.
    """
    prompt = str(request.get("prompt") or "").strip()
    triggers = collect_triggers(active_loras(request.get("loras"), checkpoint))
    if triggers:
        prompt = f"{', '.join(triggers)}, {prompt}" if prompt else ", ".join(triggers)
    return prompt


def compile_still(data, image_size_lookup=None):
    """A pre-stage blob (arch 'minimax') -> `StillPlan`.

    `image_size_lookup` is the uniform still-family surface's argument and is
    unused here: an H3 still's canvas is resolved where a shot's is, by the
    segment node compiling the request it is handed.

    The request inside the blob is already in `compile.compile_request`'s shape —
    the pre-stage's H3 branch is driven by the Creator's own editor, which writes
    the Creator's own state — so this settles only what is the *still's*: how
    long a clip to sample, which of its latent frames to keep, and how the prompt
    reaches the DiT. Everything else is validated where it is for a shot, by the
    segment node compiling the request it is handed.
    """
    if not isinstance(data, dict):
        raise CompileError("prestage_data must be a JSON object")

    block = _block(data)
    frames = _frames(block.get("frames", DEFAULT_FRAMES))
    request = _request(block, frames)
    if not str(request.get("prompt") or "").strip() and not (
            (request.get("refined") or {}).get("body") or "").strip():
        raise CompileError("describe the still first — the prompt is empty")

    mode = block.get("prompt_mode", DEFAULT_PROMPT_MODE)
    if mode not in PROMPT_MODES:
        raise CompileError(f"unknown prompt mode {mode!r}")
    override = _plain_prompt(request, _checkpoint(request)) if mode == "plain" else None

    try:
        index = int(block.get("latent_index", DEFAULT_LATENT_INDEX))
    except (TypeError, ValueError):
        raise CompileError("the latent frame index must be a whole number")

    return StillPlan(
        request=request,
        frames=frames,
        index=resolve_index(index, frames),
        prompt_override=override,
        audio=needs_audio(request),
    )


# --- the graph half -------------------------------------------------------

SEGMENT_NODE = declare.SEGMENT_NODE
STILL_NODE = "MiniMaxH3StillLatent"
SAVE_NODE = "MiniMaxH3SaveImage"

FILENAME_PREFIX = outputs.default_image(declare.ID, declare.OUTPUT_STEM)


def weights_from_blob(data):
    """`core.Weights` for the still's request.

    Nothing to lift: the pre-stage's H3 branch is driven by the Creator's own
    editor, so the request carries a weights block in exactly the shape the
    video nodes' does — checkpoints, text encoder, VAEs, precision, devices, and
    the standing route.
    """
    return slots.weights_from_blob(data)


def emit(plan, weights, sampling, unique_id, filename_prefix=FILENAME_PREFIX):
    """-> the graph, which the caller finalizes with `core.emit.expanded`.

    `sampling` is a `sampling.Sampling`, under the same widget names the two
    video nodes use.
    """
    import json

    from comfy_execution.graph_utils import GraphBuilder

    from ...core import emit as loop
    from . import render as h3

    labels = ["This still"]
    payloads = [weights.routed(plan.payload)]
    # The loop's own early compile and H3's routing, so a request that cannot
    # compile fails before a loader is built, and only the checkpoint it
    # actually routes to gets one.
    compiled = loop.compile_all(h3.FAMILY, payloads, labels)
    where = h3.routed(compiled, labels)
    # A still decodes no sound, but it can *cite* some: a reference audio clip,
    # or a reference video taken with its soundtrack, is encoded into the
    # conditioning exactly as it is for a video render. Read off the compiled
    # requests rather than the blob, so what decides is what the encoder will
    # actually reach for. Nothing attached, nothing loaded.
    audio = any(one.ref_audios or any(v.track == "picture+sound" for v in one.ref_videos)
                for one in compiled)
    core.check(weights, slots.needs(where, audio=audio), where)

    graph = GraphBuilder()
    links = core.Links(graph, weights, set(where), audio=audio)

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
    for name in slots.ROUTED_SLOTS:
        if links.get(name) is not None:
            inputs[f"model_{name}"] = links.get(name)
    segment = graph.node(SEGMENT_NODE, **inputs)

    # The distilled H3 checkpoints run at cfg 1.0, where the negative is
    # skipped outright — the same zeroed conditioning the video path uses.
    against = graph.node("ConditioningZeroOut", conditioning=segment.out(1)).out(0)
    # taeh3 in the node body, exactly as on a video render. The preview is a
    # clip of the whole sampled latent, not of the frame that will be kept:
    # watching the motion is how you see the still is going somewhere.
    model = core.graph_preview(graph, segment.out(0), weights,
                               declare.RULES.fps)

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


def emit_still(data, plan, sampling, unique_id):
    """The uniform still surface over `emit` — see `families/registry.py`.

    The request owns the weights and the output prefix, because it is an
    ordinary creator request; `data` — the pre-stage blob around it — has
    nothing this branch reads.
    """
    from ... import outputs, settings

    return emit(plan, weights_from_blob(plan.request), sampling, unique_id,
                filename_prefix=outputs.image(plan.request,
                                              settings.image_prefix(declare.ID)))
