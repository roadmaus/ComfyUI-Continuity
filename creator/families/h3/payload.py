"""Seam conditioning core cannot express: keyframes with references, and
guides at real timeline positions.

The open weights accept more than their documented input conditions. FL2VA
reads reference audio; Ref2VA reads pinned frames; and a conditioning row's
time coordinate can sit anywhere on the target timeline, not just at its first
or last frame. All three are what a timeline seam is made of — the previous
segment's last frames pinned where the new segment starts, its audio tail
pinned so the sound carries phase-locked across the join, references intact
alongside.

Core has since caught up on the video half: e01fb4c5 ("Add MiniMaxH3AddGuide",
2026-08-13) rebuilt `PackedLayout` around the general anchor — `cond_t =
target_origin + FRAME_RESCALE * resolved_frame_index`, the same formula this
module wrote in by hand — and made `extra_conds` append rather than overwrite,
so keyframes and references coexist. On such a core `encode.py` passes real
indices straight through (`CORE_ANCHORS_ANYWHERE` below), the two video
repairs here have nothing keyed to act on, and the wrapper's remaining job is
the audio tail: core anchors a guide's sound *starting* at its frame, and a
ref-audio block sits in the imitation span before the clip, but a seam needs a
tail that *ends* on a frame of the target's own timeline. No core release
expresses that, so the `AUDIO_END_KEY` rewrite runs on every core.

On an older core, both of the original gaps are still there, and the wrapper
still repairs them in full. First, `MiniMaxH3.extra_conds` cannot carry
keyframes and references at once:

    keyframes = kwargs.get("minimax_keyframes", None)
    if keyframes is not None:
        payload["cond_video_latents"] = [kf["latent"] for kf in keyframes]
    refs = kwargs.get("minimax_refs", None)
    if refs is not None:
        payload["cond_video_latents"] = [r["latent"] for r in refs if "latent" in r]

    -- comfy/model_base.py

The reference branch *overwrites* the keyframe branch. The layout still lays
out `cond` rows for the keyframes, and the DiT gets the wrong tensors — or
none — to put in them. `PackedLayout` itself is fine with the combination: the
forward pass walks `cond`, `ref_img` and `video` segments off one running
offset, so the list only has to be rebuilt in that same order.

Second, `PackedLayout` places rows at two coordinates only:

  - A keyframe's time is computed from `text_len` directly, and only frame 0
    and the last frame are accepted. But references advance a cursor that the
    target clip then *starts at* — so the moment references are present, a
    "frame 0" keyframe sits at the references' coordinate, not on the clip.
    The general position, from core's own grid (each pixel frame spans
    FRAME_RESCALE time units, at every index), is

        cond_t = target_origin + FRAME_RESCALE * pixel_index

    where `target_origin` is where the target rows actually begin.

  - A reference audio block sits in the span *before* the clip, which the
    model imitates — similar sound, not a continuation. A seam wants the tail
    end-aligned on the clip's own timeline, so the model reads it as this
    clip's sound so far and continues it.

Rather than patch core, this installs a diffusion-model wrapper that repairs
the payload just before the forward: it rebuilds `cond_video_latents` when
keyframes and refs coexist, and rewrites the time column of any row whose
entry carries one of the keys below. Entries pass the stock constructor with
`resolved_frame_index: 0` — always legal — and their real position rides under
the key; a payload with no keys is passed through untouched. RoPE is built at
forward time from `position_ids`, so the rewrite lands before anything reads
it. The layout structure is verified against what the rewrite expects and the
wrapper raises on a mismatch: a core layout change should be heard about, not
papered over with misplaced anchors.
"""

import inspect

import torch

import comfy.patcher_extension
from comfy.ldm.minimax.model import FRAME_RESCALE, PackedLayout

# Whether this core places a keyframe anchor at any frame and lets keyframes
# ride alongside references (e01fb4c5 and later). Probed off the semantic
# itself rather than a version string: the general constructor computes the
# anchor from `resolved_frame_index` directly and lost the `frame_count`
# parameter the old first/last-only arithmetic needed.
CORE_ANCHORS_ANYWHERE = (
    "frame_count" not in inspect.signature(PackedLayout.__init__).parameters)

# **The four `minimax_creator_*` keys below keep that spelling forever.** They
# were not renamed when the pack was, because they are not the pack's name —
# they are the surface the `AUDIO_END_KEY` repair matches against inside core's
# conditioning dict on every core release, and the one thing a compatibility
# probe cannot afford is to be a moving target.
WRAPPER_KEY = "minimax_creator_cond_video_latents"

# On a keyframe dict: the pixel-frame index this guide is really pinned at, on
# the target clip's own timeline. 0 is the clip's true first frame — distinct
# from stock's frame 0, which references shift off the clip.
FRAME_INDEX_KEY = "minimax_creator_frame_index"

# On an audio ref dict: the pixel-frame coordinate the pinned audio *ends* at.
# End-aligned because both the audio and the pinned frames are the tail of the
# same source segment, so both must end at the same instant of the new
# timeline. One audio latent step spans exactly one time unit, and one pixel
# frame spans FRAME_RESCALE of them.
AUDIO_END_KEY = "minimax_creator_audio_end_frame"

# Stamped on a layout whose positions were already rewritten. The layout is
# built once per sampling run and shared across steps; the rewrite is
# idempotent in effect but not in arithmetic, so it must run exactly once.
_DONE = "_minimax_creator_repositioned"


def _needs_reposition(payload):
    return (any(FRAME_INDEX_KEY in kf for kf in payload.get("keyframes") or [])
            or any(AUDIO_END_KEY in ref for ref in payload.get("refs") or []))


def _rebuild(payload):
    """`cond_video_latents` in layout order: keyframes, then reference images."""
    latents = [kf["latent"] for kf in payload.get("keyframes") or []]
    latents += [ref["latent"] for ref in payload.get("refs") or [] if "latent" in ref]
    return latents


def _target_origin(layout):
    """The time coordinate the target clip's rows start at.

    Read off the built layout rather than recomputed: the target video rows
    are always the last segment, and their first row carries the cursor's
    final value — whatever reference kinds advanced it by.
    """
    a, b, kind = layout.segments[-1]
    if kind != "video" or b <= a:
        raise RuntimeError(
            f"Continuity: expected the target video rows to be the last "
            f"layout segment, found {kind!r} spanning {b - a} rows. Core's H3 "
            f"layout changed; refusing to reposition seam guides."
        )
    return float(layout.position_ids[a, 0])


def _ref_audio_segments(layout):
    """The layout's `ref_audio` segments, in emission order."""
    return [(a, b) for a, b, kind in layout.segments if kind == "ref_audio"]


def _reposition(layout, payload):
    """Rewrite the time column of every keyed row. Once per layout."""
    if getattr(layout, _DONE, False):
        return
    origin = _target_origin(layout)

    keyframes = payload.get("keyframes") or []
    cond = [(a, b) for a, b, kind in layout.segments if kind == "cond"]
    if len(cond) != len(keyframes):
        raise RuntimeError(
            f"Continuity: {len(keyframes)} keyframes should emit "
            f"{len(keyframes)} cond segments, the layout has {len(cond)}. "
            f"Core's H3 layout changed; refusing to reposition seam guides."
        )
    for (a, b), keyframe in zip(cond, keyframes):
        index = keyframe.get(FRAME_INDEX_KEY)
        if index is not None:
            layout.position_ids[a:b, 0] = origin + FRAME_RESCALE * float(index)

    # Audio blocks map to ref_audio segments in order — every ref kind that
    # carries sound emits exactly one, and none of ours ever has zero steps.
    audio = [ref for ref in payload.get("refs") or []
             if ref["kind"] in ("audio", "video_audio") and ref["ref_audio_t"] > 0]
    segments = _ref_audio_segments(layout)
    if len(segments) != len(audio):
        raise RuntimeError(
            f"Continuity: {len(audio)} audio reference blocks should emit "
            f"{len(audio)} ref_audio segments, the layout has {len(segments)}. "
            f"Core's H3 layout changed; refusing to reposition seam guides."
        )
    for (a, b), ref in zip(segments, audio):
        end_frame = ref.get(AUDIO_END_KEY)
        if end_frame is None:
            continue
        steps = int(ref["ref_audio_t"])
        if b - a != steps * 2:
            raise RuntimeError(
                f"Continuity: an audio block of {steps} latent steps "
                f"should span {steps * 2} rows, found {b - a}. Core's H3 "
                f"layout changed; refusing to reposition seam guides."
            )
        start = origin + FRAME_RESCALE * float(end_frame) - steps
        # Channel-major stereo: t advances per latent step, twice over.
        times = start + torch.arange(steps, dtype=torch.float64)
        layout.position_ids[a:b, 0] = times.repeat(2)

    setattr(layout, _DONE, True)


def _wrapper(executor, *args, **kwargs):
    payload = kwargs.get("minimax_payload")
    if payload:
        # Only on a core whose `extra_conds` overwrites, and only when both are
        # present. Either one alone is already correct, and rewriting it would
        # be this module claiming a behaviour it lacks.
        if (not CORE_ANCHORS_ANYWHERE
                and payload.get("keyframes") and payload.get("refs")):
            payload = dict(payload)
            payload["cond_video_latents"] = _rebuild(payload)
            kwargs = {**kwargs, "minimax_payload": payload}
        if _needs_reposition(payload):
            layout = payload.get("layout")
            # The forward silently rebuilds a layout whose signature does not
            # match the streams it was handed — and a rebuilt layout would
            # carry stock's misplaced anchors. Verify here, where the answer
            # is a loud error instead of a subtly wrong video. Same rounding
            # as extra_conds: h/w up to the DiT's 2x2 patch.
            video, audio = args[0][0], args[0][1]
            expected = (args[2].shape[1], video.shape[2],
                        (video.shape[3] + 1) // 2 * 2,
                        (video.shape[4] + 1) // 2 * 2, audio.shape[-1])
            if layout is None or layout.signature != expected:
                raise RuntimeError(
                    "Continuity: seam guides present but the prebuilt "
                    "layout is missing or does not match the sampled streams "
                    f"({None if layout is None else layout.signature} vs "
                    f"{expected}) — the forward would rebuild it with the "
                    "guides at stock's misplaced coordinates."
                )
            _reposition(layout, payload)
    return executor(*args, **kwargs)


def repair(model):
    """A clone of `model` whose seams survive core's payload assembly.

    Inert on payloads with nothing to repair, so it is safe to apply to any
    continuing segment. Keyed, so applying it twice — the Timeline node
    patches per segment — leaves one wrapper rather than a stack.
    """
    patched = model.clone()
    patched.add_wrapper_with_key(
        comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL, WRAPPER_KEY, _wrapper)
    return patched
