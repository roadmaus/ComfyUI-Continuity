"""The ControlNet guide — the family-neutral half of aiming a render.

The bench in `control.py` traces footage into a drawing. This is what happens
after: the drawing is attached to a shot **like any other media**, and the
weights are made to follow it.

**A guide is an asset, not a setting.** It rides in `assets` with `role:
"guide"`, alongside the keyframes and the references, which means it inherits
the whole attachment grammar for free — the picker attaches it, the trim overlay
picks which seconds of it this shot uses, the chip on the card shows it, and
`Asset.trim` answers "which stretch" exactly as it does for a reference clip.
None of that is written here, and an earlier draft of this module that laid one
guide along the whole piece and computed each pass's window by hand is what this
replaced: attaching a clip and trimming it is the same gesture the user already
makes for a reference, and the arithmetic was solving a problem the grammar did
not have.

What is left here is the part that genuinely is not an asset:

- **the switch** (`Guide` below) — whether the control branch is loaded at all,
  and how hard it pulls. A guide attached with the switch off is a file on a
  card and nothing more, which is what makes six gigabytes of branch weights
  something you opt into;
- **the reader** (`read`) — a window of the clip, decoded to the frames one
  generation needs, at the canvas and the rate that generation renders at;
- **`Controlled`** — the wrapper that lets a controlnet replace one of a segment
  node's outs without the sampler, refine and face hooks learning guides exist.

**Three ways a family can take a guide, and only one of them needs any of this.**

- `native` — the weights were post-trained to follow a tracing that arrives in
  an ordinary picture slot. Qwen-Image-Edit 2509 and 2511 do; nothing is loaded
  and nothing is emitted.
- `branch` — a control branch loaded beside the transformer: MiniMax H3's Fun
  ControlNet-Union, Qwen-Image's Fun controlnet, Z-Image's. A file in
  `models/controlnet`, a loader, and a node that puts it on the conditioning or
  on the model.
- nothing at all — the family has no answer, and the switch is not drawn.

Which of the three a family is, is one line in its manifest
(`capabilities.control`).
"""

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# `media` and torch are imported inside the function that reads a file, not
# here. The family manifests name this module for their guide capability's
# numbers, and a manifest has to be importable without ComfyUI — that is the
# invariant `families/h3/declare.py` exists to hold, and a module-level `media`
# (which imports `folder_paths`, `av` and `torch`) quietly broke it for five
# suites.

# The blob key the switch writes, and the weights slot a `branch` family loads.
# Two names because they are two things: the guide is the drawing, and the
# control slot is the branch that reads it. A family with a `native` method has
# a guide and no second.
BLOCK = "guide"
CONTROL_SLOT = "control"

# The pack node one shot reads its slice of the guide off. Family-neutral, and
# named here rather than in `core/emit.py` so a family emitting an apply node
# imports this module and not the loop that calls it.
FRAMES_NODE = "ContinuityGuideFrames"

# What the strength dial may hold. The apply nodes take more — core's H3 node
# allows 10 — but the checkpoint's card calls 1.0 full control and nothing above
# it was trained, so the blob is clamped to the trained range rather than to the
# node's.
MIN_STRENGTH = 0.0
MAX_STRENGTH = 1.0
DEFAULT_STRENGTH = 1.0

# The rate a guide is read at where a caller has no family in hand — the same
# 24 fps every reference in this pack is resampled to.
TARGET_FPS = 24


class GuideError(ValueError):
    """A guide that cannot be honoured — a file that will not read."""


@dataclass(frozen=True)
class Guide:
    """The switch: whether the branch is loaded, and how hard it pulls.

    Not the file. The file is an `Asset` on the shot, because it is media and
    the pack already knows how to attach media. This is the part of a guide that
    is a machine decision rather than a piece of footage: loading a control
    branch costs several gigabytes beside the checkpoint, so it is something you
    throw rather than something that happens because a clip landed on a card.

    `start` and `end` are the stretch of the schedule the branch is in force
    over. On the switch rather than on the asset because they are a statement
    about how much of the denoise the drawing should decide — the same question
    on every shot, and not a property of any one clip.
    """

    on: bool = False
    strength: float = DEFAULT_STRENGTH
    start: float = 0.0
    end: float = 1.0

    @classmethod
    def of(cls, data):
        """The blob's guide block, or None where the switch is off.

        None for every blob written before this existed, for every piece nobody
        has thrown it on, and for a switch explicitly off — all three mean the
        same thing downstream (`emit_control` is never called, the branch is
        never loaded) and none is worth distinguishing here.
        """
        raw = (data or {}).get(BLOCK)
        if not isinstance(raw, dict) or raw.get("on") is not True:
            return None
        start = _clamp(raw.get("start"), 0.0, 1.0, 0.0)
        end = _clamp(raw.get("end"), 0.0, 1.0, 1.0)
        # A window that closes before it opens is a guide never in force.
        # Normalised rather than refused: the two are one control with two ends
        # and dragging them past each other is a thing hands do.
        if end < start:
            start, end = end, start
        return cls(on=True,
                   strength=_clamp(raw.get("strength"), MIN_STRENGTH,
                                   MAX_STRENGTH, DEFAULT_STRENGTH),
                   start=start, end=end)


def _clamp(value, low, high, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:            # NaN, which compares false against both bounds
        return fallback
    return min(high, max(low, number))


def untrained(asset, tracings):
    """Whether these weights were never post-trained on this tracing.

    Never an error. A guide the checkpoint has not seen is still a picture, and
    the render comes out looking like the drawing rather than aimed by it, which
    is worth a word and not worth a wall. The frontend says it where the guide
    is attached; this is here so a hand-edited blob gets the log line instead of
    silence.

    A guide the bench did not write carries no tracing at all, and nothing can
    be said about it: an unknown tracing is not an untrained one.
    """
    op = getattr(asset, "op", "") if asset is not None else ""
    return bool(op) and bool(tracings) and op not in tracings


# ---- reading the guide back ---------------------------------------------------

# Two frames of slack on the decode window, for `media._decode_window`'s reason:
# the resample rounds, and a window that came back one frame short would hand the
# apply node a guide that stops moving a frame before the shot does.
_SLACK_FRAMES = 2


def read(filename, trim, frames, width, height, fps):
    """One shot's worth of the guide — `[frames, height, width, 3]`.

    Read at the render's rate rather than through `media.load_video`, and that
    is the reason this feature is family-neutral at all: that function
    resamples to 24 fps because that is the rate H3 reads *references* at, and
    a guide is not a reference — it is the picture the sampler is aimed at
    frame for frame, at whatever rate the family renders. Handing LTX's 30 fps
    a 24 fps guide would slow the drawing to three-quarters speed against the
    shot it is guiding.

    **Resized here rather than left to the apply node.** Core fits the hint to
    the latent canvas itself, so this is not needed for correctness — it is
    needed for memory. Fifteen seconds of 1080p arrives as float32 and is about
    nine gigabytes; the same window at a 768-edge canvas is under one, and the
    fit core would have done is the one done here.

    `trim` is the asset's own `(start, end)` in seconds, or None for the whole
    clip — the same field a reference video carries, set in the same overlay.
    A window shorter than the shot holds its last frame, which is what the apply
    node does with a short hint anyway; said here as well so the tensor handed
    over is the length it claims to be, and so a guide that runs out is a shot
    that stops moving with the drawing rather than one that fails.
    """
    import comfy.utils
    import torch

    from . import media

    rate = float(fps) or TARGET_FPS
    want = max(1, int(frames))

    # A still guide is one drawing every frame is aimed at. The pre-stage's
    # whole output is one frame, so that is the shape a guide takes there; on a
    # moving shot it is "hold this composition for the length of the shot",
    # which is unusual and legitimate and is what the hold below would do to a
    # clip that ran out on frame one anyway.
    if _is_still(filename):
        one = media.load_image(filename)[..., :3]
        return _fit(comfy.utils, one.expand(want, -1, -1, -1), width, height)

    start = max(0.0, float(trim[0])) if trim else 0.0
    # The shot's own length bounds the decode, whatever the trim says: a guide
    # trimmed to thirty seconds for a six-second shot should cost six seconds of
    # decode. Where the trim is shorter it wins — that is the user saying which
    # stretch, and the hold below covers whatever is left of the shot.
    span = (want + _SLACK_FRAMES) / rate
    if trim:
        span = min(span, max(0.0, float(trim[1]) - start) + _SLACK_FRAMES / rate)

    # The same timestamp-driven resample a supplied clip is spliced with, at
    # the render's rate rather than H3's — see `media._frames_at` for why the
    # average-rate index it replaced put variable-rate footage on the wrong
    # frames.
    try:
        got = media._frames_at(filename, start, span, rate)
    except ValueError as exc:
        raise GuideError(f"the guide {filename!r} has no picture in it") from exc
    if got.shape[0] == 0:
        raise GuideError(
            f"the guide {filename!r} has nothing at {start:.2f} s. Re-trim it on "
            f"the card, or trace it again on the ControlNet bench."
        )

    if trim:
        # The slack was decoder context, not picture: cut back to the trim
        # before anything is held, or the frame held for the rest of the shot
        # is one from *past* the selection — the next scene, on a trim that
        # ends on a cut (issue #47).
        got = got[:max(1, int(round((float(trim[1]) - start) * rate)))]
    if got.shape[0] < want:
        # Held rather than looped or padded black. A guide that ran out should
        # leave the shot pointing where it last pointed; black would drive the
        # branch with an empty drawing, which is a different instruction.
        got = torch.cat([got, got[-1:].expand(want - got.shape[0], -1, -1, -1)], dim=0)
    got = got[:want]

    return _fit(comfy.utils, got, width, height)


# What the picture branch above reads. Off the extension rather than off a probe:
# the bench writes what it traced, and a guide's filename is the bench's own.
_STILL_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def _is_still(filename):
    return str(filename).lower().endswith(_STILL_SUFFIXES)


def _fit(utils, frames, width, height):
    """The frames at the render's canvas, cropped the way core would crop them.

    `center` is the crop core's own `_fit_frames` uses, so a guide traced at one
    aspect and rendered at another is cropped the same way here as it would have
    been there.
    """
    if int(width) > 0 and int(height) > 0 \
            and (frames.shape[2] != int(width) or frames.shape[1] != int(height)):
        frames = utils.common_upscale(
            frames.movedim(-1, 1), int(width), int(height), "bilinear", "center"
        ).movedim(1, -1)
    return frames.clamp(0.0, 1.0)


# ---- the graph-side helpers ---------------------------------------------------


class Controlled:
    """A segment node with a guide applied over it.

    The segment node's four outs are the family contract — `(model, positive,
    latent, lead model)` — and a ControlNet replaces one of the first two,
    depending on the architecture. Core's generic ControlNets and MiniMax H3's
    Fun branch hand back a *conditioning*; Z-Image's and Qwen-Image's Fun
    controlnets hand back a patched *model*. Both are the same statement — "this
    render is aimed at that drawing" — said on different sockets.

    So `emit_control` returns one of these instead of a link, and everything
    downstream keeps reading `.out(0)` and `.out(1)` off a segment as it always
    has. That is what lets `emit_sampler`, `emit_refine` and `emit_face` stay
    unaware that guides exist.

    Nothing is copied and nothing is re-emitted: the outs that were not replaced
    are the segment's own, so a graph with a guide on it differs from one
    without by exactly the nodes the guide added.
    """

    def __init__(self, segment, model=None, positive=None):
        self._segment = segment
        self._replaced = {}
        if model is not None:
            self._replaced[0] = model
        if positive is not None:
            self._replaced[1] = positive

    def out(self, index):
        if index in self._replaced:
            return self._replaced[index]
        return self._segment.out(index)


def without(payload):
    """`payload` with the guide taken out of its request, or unchanged.

    **A guide must not be part of a segment's cache key.** The payload is
    serialised onto the segment node as `segment_data`, and that string is what
    ComfyUI hashes to decide whether the shot's conditioning has to be built
    again. A guide reaches the model through a control branch bolted on *after*
    that node — it is never cited in the prompt, takes no ordinal, and enters no
    reference plan — so leaving it in the key would re-run the text encoder
    every time somebody dragged the trim handle on a drawing the encoder has
    never seen.

    The same argument the sampler row makes for living outside the key, and the
    same shape `prompt_override` uses to get out of one: lifted off the request
    rather than never put there, so the blob keeps saying what it means (a guide
    is a thing attached to a shot) and only the wire changes.

    Returns the payload itself where there is nothing to strip, so a render with
    no guide on it serialises byte-identically to what it always did.
    """
    request = (payload or {}).get("request")
    if not isinstance(request, dict):
        return payload
    assets = request.get("assets")
    if not isinstance(assets, list):
        return payload
    kept = [a for a in assets
            if not (isinstance(a, dict) and a.get("role") == "guide")]
    if len(kept) == len(assets):
        return payload
    request = {**request, "assets": kept}
    # The key goes entirely, not to an empty list. A shot whose only attachment
    # was the guide has to serialise as what it now is — a shot with nothing
    # attached — or it keeps a cache key of its own for the rest of its life and
    # never hits the one every other bare shot shares.
    if not kept:
        del request["assets"]
    return {**payload, "request": request}


def guide_frames(graph, asset, compiled, fps):
    """The node this shot reads its guide off. -> an IMAGE link.

    Emitted through a node rather than decoded in the emitter for the reason
    every other file in this pack is read through one: the emitter runs at queue
    time on the event loop that also carries the prompt queue and the progress
    socket, and decoding six seconds of video there would stall every render
    behind it. This runs where the executor runs it, and ComfyUI caches its
    output across queues that did not change it.

    An `end` of 0 means "to the end of the file", which is `media._decode_window`'s
    own convention for a duration of 0 and is what an untrimmed guide carries.
    """
    trim = getattr(asset, "trim", None)
    return graph.node(
        FRAMES_NODE, filename=asset.filename,
        start=round(float(trim[0]), 3) if trim else 0.0,
        end=round(float(trim[1]), 3) if trim else 0.0,
        frames=int(compiled.frames),
        width=int(compiled.width), height=int(compiled.height),
        fps=float(fps)).out(0)


def node_available(node_id):
    """Whether the core node a family's guide needs is on this ComfyUI.

    The same probe `render.CORE_EMPTY_NOISE_IS_NESTED` and
    `payload.CORE_ANCHORS_ANYWHERE` are, and for the same reason: a capability
    is declared off what the installed core can actually do rather than off a
    version string, so a user on a core without it sees no switch instead of a
    switch that queues a graph naming a node that is not there.

    MiniMax H3's apply node lands with Comfy-Org/ComfyUI#15860, which is not
    merged at the time of writing — this is what lets the rest of the feature
    ship, and be tested, ahead of it.
    """
    try:
        import nodes
    except Exception:      # noqa: BLE001 — no ComfyUI is a probe that says no
        return False
    return node_id in nodes.NODE_CLASS_MAPPINGS
