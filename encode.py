"""Conditioning + AV latent for a compiled request.

This is a re-dispatch of core's `MiniMaxH3ImageToVideo` / `MiniMaxH3ReferenceToVideo`
against `Compiled` instead of against node sockets. The sizing and payload
helpers are imported from core rather than copied, so upstream fixes to the
canvas math or the reference presentation reach us without a re-port.

The reference path does not decide its own ordering. It executes
`compiled.plan`, the same walk `compile.py` numbered `<Picture N>` / `<Video N>`
/ `<Audio N>` from, one step at a time. That is deliberate: a mis-binding
between the labels in the prompt and the tensors in the payload produces a
subtly wrong video rather than an exception, so the two sides are built from one
list instead of two loops that have to be kept in agreement by hand.
"""

import logging
import math
import time

import node_helpers
import torch
from comfy.ldm.minimax.model import FRAME_PER_TOKEN
from . import latents, media
from .payload import AUDIO_END_KEY, CORE_ANCHORS_ANYWHERE, FRAME_INDEX_KEY
from comfy_extras.nodes_minimax_h3 import (
    CANVAS_MULTIPLE,
    FPS,
    REF_IMAGE_SHORT_EDGE,
    _empty_av_latent,
    _resize,
    adapt_canvas,
)

# Two spellings of one function, because a pack does not choose which core its
# users run. Core 2026-08-13 ("Add MiniMaxH3AddGuide", e01fb4c5) lifted this out
# of the node class to module level; the body and the signature are the same on
# both sides, so this is which import works, not which behaviour is wanted.
try:
    from comfy_extras.nodes_minimax_h3 import _encode_ref_audio
except ImportError:  # core before 2026-08-13: a static method on the node
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo
    _encode_ref_audio = MiniMaxH3ReferenceToVideo._encode_ref_audio

# Where a timeline segment's inherited start frame arrives in `loaded`. It is the
# previous segment's decoded last frame, so unlike every other entry it has no
# Asset and no filename — a reserved key rather than a handle, because handles
# are the user's namespace and this frame is not something they attached.
PREV_FRAME = "__prev__"

# Where a timeline segment's inherited audio tail arrives. Same reasoning as
# PREV_FRAME: it is the previous segment's *generated* sound, so there is no file
# and no handle behind it.
PREV_AUDIO = "__prev_audio__"

# The same two, at the other end of the segment: the opening of the supplied
# clip this generation runs into. Reserved keys for the same reason — they are
# read out of a file the timeline holds, not out of anything the user attached
# to this shot, so they have no handle in the user's namespace.
NEXT_FRAME = "__next__"
NEXT_AUDIO = "__next_audio__"


def _quantize(images):
    """A presentation tensor -> the 8-bit form it is both sent and cached as.

    The tokenizer's half of a reference is a picture, and a picture is what
    `latents.py` has to keep if a cache hit is to skip the decode as well as the
    encode. Eight bits of it, for the reason `spill.py` keeps eight: the source
    was 8-bit before `_resize` interpolated it, the tokenizer bilinearly
    resamples whatever it is given all over again (`process_video_block`), and
    a quarter of the bytes is the difference between a cache that holds a
    project's references and one that holds four of them.

    Applied on the way *in* as well as the way out — unconditionally, whether
    the cache is on, off, or missing. That is the point of it being here rather
    than inside `latents.py`: a hit and a miss send the tokenizer the same
    tensor, so switching the cache off can only change how long a render takes
    and never what it produces.

    Two things about a reference's presentation therefore changed when the cache
    landed, both of them here and both only on the tokenizer's copy — the latent
    is encoded from the untouched `_resize` output exactly as before. It is
    rounded to eight bits, and it is clamped to 0..1, which lanczos overshoots
    at a hard edge. Under a normalisation that already assumes 0..1 and a
    resample that runs again inside the tokenizer, neither is visible; they are
    named because "the cache cannot change a render" is a claim, and this is
    where it is paid for.
    """
    return (images * 255.0).round_().clamp_(0, 255).to(torch.uint8)


def _present(stored):
    """The 8-bit form back as the float image the tokenizer is handed."""
    return stored.to(torch.float32).div_(255.0)


def _restore(vae, latent):
    """A cached latent, back where `vae.encode` would have left it.

    Cached entries are held on the CPU; `vae.encode` returns on the VAE's own
    output device in its own output dtype. Both are read off the VAE rather than
    off the fresh tensor so that a hit and a miss are indistinguishable
    downstream — and because the dtype never changes, the round trip a miss
    makes through the CPU is bit-exact rather than merely close.
    """
    device = getattr(vae, "output_device", None) or latent.device
    dtype = vae.vae_output_dtype() if hasattr(vae, "vae_output_dtype") else latent.dtype
    return latent.to(device, dtype=dtype)


def _said(count):
    """A byte count in the unit that makes it legible.

    Down to kilobytes because a reference's soundtrack is a few hundred of them
    against a video's forty megabytes, and "0 MB" beside "reused" reads as
    nothing having happened — which is the opposite of what the line is for.
    """
    if count >= 1024 ** 3:
        return f"{count / 1024 ** 3:.2f} GB"
    if count >= 1024 ** 2:
        return f"{count / 1024 ** 2:.0f} MB"
    return f"{count / 1024:.0f} KB"


class Tally:
    """What the references cost this generation, for one line at the end of it.

    The per-reference lines below say what is happening while it happens, which
    is what a render that sits silent for a minute actually needs. This says
    whether the thing worked, which is the question you ask once.
    """

    def __init__(self):
        self.reused = 0
        self.encoded = 0
        self.seconds = 0.0
        self.saved = 0

    def hit(self, size):
        self.reused += 1
        # What the encode would have cost is not knowable on a hit, so this is
        # bytes served rather than time saved. Time is on the miss lines.
        self.saved += size

    def miss(self, seconds):
        self.encoded += 1
        self.seconds += seconds

    def say(self):
        if not (self.reused or self.encoded):
            return
        if not self.encoded:
            logging.info("[MiniMax] references: all %d reused (%s) — nothing encoded",
                         self.reused, _said(self.saved))
        elif not self.reused:
            logging.info("[MiniMax] references: %d encoded in %.1f s",
                         self.encoded, self.seconds)
        else:
            logging.info("[MiniMax] references: %d reused (%s), %d encoded in %.1f s",
                         self.reused, _said(self.saved), self.encoded, self.seconds)


def _cached(label, parts, produce, tally=None):
    """`produce()`, unless `latents` already holds what it would return.

    -> (tensors, meta). `parts` is everything the encode depended on *except*
    the prompt, which is the whole reason this exists: see `latents.py`. None
    means this one is not cacheable — see `_ref_key`.

    A store hands back its own CPU copies rather than the tensors it was given,
    so a miss and a hit return the same shapes on the same device and the call
    sites have one path instead of two.

    This is also the only place that knows whether a reference was reused, so it
    is where that is said out loud. A miss announces itself *before* it runs:
    decoding a long source and pushing it through the VAE is the wait, and a
    render that goes quiet for a minute with nothing on the terminal is the
    complaint this exists to answer.
    """
    off = not latents.enabled()
    if parts is None or off:
        logging.info("[MiniMax] %s: encoding (%s)", label,
                     "cache off" if off else "nothing to key it on")
        started = time.monotonic()
        tensors, meta = produce()
        spent = time.monotonic() - started
        logging.info("[MiniMax] %s: encoded in %.1f s", label, spent)
        if tally is not None:
            tally.miss(spent)
        return tensors, meta

    name = latents.key(parts)
    found = latents.fetch(name)
    if found is not None:
        tensors, meta, where = found
        size = latents.size_of(tensors)
        logging.info("[MiniMax] %s: reused from %s (%s)", label, where, _said(size))
        if tally is not None:
            tally.hit(size)
        return tensors, meta

    logging.info("[MiniMax] %s: encoding, nothing cached", label)
    started = time.monotonic()
    tensors, meta = produce()
    spent = time.monotonic() - started
    kept = latents.store(name, tensors, meta)
    logging.info("[MiniMax] %s: encoded in %.1f s, cached %s",
                 label, spent, _said(latents.size_of(kept)))
    if tally is not None:
        tally.miss(spent)
    return kept, meta


def _ref_key(kind, asset, vae, compiled):
    """What a reference's encode depends on — and deliberately not one word more.

    Every term here is something that changes the tensors; nothing that merely
    changes the *generation* is in it. The prompt is the one the whole exercise
    is about, but the same goes for the seed, the sampler, the LoRAs, the other
    references and the order they are cited in.

    The terms that are here, and why each of them is:

    `file`      the source, by path and mtime and size — a clip replaced in
                place under the same name is a different clip (`media.stamp`).
    `vae`       the weights doing the encoding (`latents.fingerprint`).
    `ref_size`  which canvas rule applies, `match` or `max`.
    `gen_w/h`   the generation's canvas — but *only* under `match`, which is the
                setting that reads it. A `max` reference is sized from its own
                source alone, so it survives a change of resolution, which is
                what makes the expensive setting the one worth caching.
    `gen_frames` the generation's length, for video and for a video's
                soundtrack: it bounds the decode window (`media.load_all`) and
                then cuts the clip to the VAE's 17n+5 grid.
    `trim`      which stretch of the source was asked for.

    Nothing is derived here — not the canvas, not the frame count — because
    working either of them out means decoding the file, and a key that has to
    open the clip to be built is a key that cannot save opening the clip. Both
    are functions of the terms above, and the source's own dimensions are
    pinned by `file`.

    -> None when the source cannot be stamped, which means this reference is
    encoded rather than cached. A file that is not there is not this function's
    to complain about: `media.load_all` will say so, by name, the moment the
    decode is asked for. A hand-built graph that supplies the media directly is
    the other caller this reaches, and it has no file to be missing.
    """
    try:
        stamp = media.stamp(asset.filename)
    except (media.MediaError, OSError):
        return None
    parts = {"kind": kind, "file": stamp,
             "vae": latents.fingerprint(vae), "trim": asset.trim}
    if kind in ("image", "video"):
        parts["ref_size"] = asset.ref_size
        if asset.ref_size == "match":
            parts["gen_w"], parts["gen_h"] = compiled.width, compiled.height
    if kind in ("video", "soundtrack"):
        parts["gen_frames"] = compiled.frames
    return parts


def _cached_ref_audio(kind, audio_vae, asset, entry, compiled, tally=None):
    """A file-backed audio reference, encoded once. -> (latent, ref_audio_t).

    Cached for the decode at least as much as for the encode: a `picture+sound`
    reference is two plan steps against one file, so if only the picture came
    back out of the cache the clip would still be opened and decoded for its
    soundtrack — which is exactly the cost the picture's entry had just avoided.

    `ref_audio_t` is read back off the latent rather than stored beside it,
    because that is where core reads it from too (`_encode_ref_audio` returns
    `z.shape[-1]`) and two copies of one number is a way for them to disagree.
    """
    tensors, _ = _cached(
        f"@{asset.handle} {kind}", _ref_key(kind, asset, audio_vae, compiled),
        lambda: ({"audio_latent": _encode_ref_audio(audio_vae, entry["audio"])[0]}, {}),
        tally)
    latent = _restore(audio_vae, tensors["audio_latent"])
    return latent, latent.shape[-1]


def _pin(keyframe, index, stock=0):
    """Pin a guide at pixel `index` of the target's own timeline.

    A core with the general anchor (`CORE_ANCHORS_ANYWHERE`) takes the index
    directly and places it right even with references in the layout. An older
    core accepts only frame 0 and the last frame, so the entry passes the
    nearest legal `stock` anchor and carries the real index for `payload.py`
    to write in.
    """
    if CORE_ANCHORS_ANYWHERE:
        return {"resolved_frame_index": index, **keyframe}
    return {"resolved_frame_index": stock, FRAME_INDEX_KEY: index, **keyframe}


def _frames_covered(steps):
    """Pixel frames the first `steps` latent steps of a video encode cover."""
    return sum(FRAME_PER_TOKEN[k % 5] for k in range(steps))


def _context_keyframes(vae, tail, feather, at=0):
    """The inherited run as pinned guides on this segment's own timeline.

    One video-VAE call over the whole tail — the motion lives inside the
    temporal compression — then one guide block per latent step, each pinned
    (`_pin`) at the pixel offset that step's content starts at.

    `at` is where the run starts on this segment's timeline: 0 for the run
    inherited from the pass in front, and `frames - feather` for the opening of
    a supplied clip this segment runs into. The offsets are the same arithmetic
    either way *because* of what the feather grid is: the legal widths are
    17m+5 and a generation is 17n+5 frames, so an end-aligned run begins at
    frame 17(n-m) — a whole number of the VAE's seventeen-frame cycles from the
    origin, and therefore in phase with the five-step pattern `_frames_covered`
    walks. A run pinned anywhere else would sit between latent steps.

    The coverage check is the seam's integrity check: `compile` only allows
    feathers on the VAE's own grid, so steps that cover a different span mean
    the VAE's downscale changed underneath us — the pinned run would end short
    of the source's last frame and the join would jump by the difference.
    """
    encoded = vae.encode(tail)
    if getattr(encoded, "ndim", 0) != 5:
        # The batch axis is time to the H3 video VAE; anything that came back
        # flat is some other VAE, and slicing it by "step" would pin noise.
        raise ValueError(
            f"encoding the inherited run returned shape "
            f"{tuple(getattr(encoded, 'shape', ()))}, expected [B, C, T, H, W] "
            f"— is the H3 video VAE wired to 'vae'?"
        )
    steps = int(encoded.shape[2])
    covered = _frames_covered(steps)
    if covered != feather:
        raise ValueError(
            f"{feather} inherited frames encoded to {steps} latent steps "
            f"covering {covered} frames — the video VAE's temporal grid no "
            f"longer matches the seam's. Refusing to render a shifted join."
        )
    return [_pin({"latent": encoded[:, :, k:k + 1]}, at + _frames_covered(k))
            for k in range(steps)]


def _seam_audio(audio_vae, audio, ends_at=None):
    """One seam's sound as an audio reference block.

    Unpinned it sits where core puts reference audio — the span before the
    clip, which the model imitates. Pinned (`ends_at`, a pixel-frame
    coordinate) it is placed end-aligned on this segment's own timeline
    instead, so the model reads it as this clip's sound at that moment and
    carries it phase-locked; `compile` sets the length from the blend so the
    sound and the frames cover the same instants.

    Both seams use it. The inherited run ends at frame `feather`, at the head;
    the run into a supplied clip ends at the last frame, so the generated
    soundtrack arrives already on the clip's.
    """
    audio_latent, ref_audio_t = _encode_ref_audio(audio_vae, audio)
    seam = {"kind": "audio", "ref_audio_t": ref_audio_t, "audio_latent": audio_latent}
    if ends_at is not None:
        seam[AUDIO_END_KEY] = ends_at
    return seam


def _seam_blocks(audio_vae, compiled, loaded, frame_count):
    """Every seam audio block this generation carries, in layout order.

    At most two: the pass in front of it and the clip after it. Blended, a
    seam's sound is pinned where its frames are; unblended it is an ordinary
    reference the model imitates, which is also the only form the tokenizer is
    shown — see `_encode_frames`.
    """
    blocks = []
    if compiled.continues_audio:
        blocks.append(_seam_audio(
            audio_vae, loaded[PREV_AUDIO]["audio"],
            compiled.feather if compiled.feather > 1 else None))
    if compiled.ends_on_audio:
        blocks.append(_seam_audio(
            audio_vae, loaded[NEXT_AUDIO]["audio"],
            frame_count if compiled.ends_feather > 1 else None))
    return blocks


def encode(clip, vae, audio_vae, compiled, loaded):
    """-> (conditioning, latent). `loaded` maps asset handle -> decoded media."""
    if compiled.mode == "REF2VA":
        return _encode_references(clip, vae, audio_vae, compiled, loaded)
    return _encode_frames(clip, vae, audio_vae, compiled, loaded)


def _encode_frames(clip, vae, audio_vae, compiled, loaded):
    """T2VA / I2VA / L2VA / FL2VA, optionally continuing the previous sound.

    The sound continuation is the one thing here core has no node for: the
    previous segment's audio tail rides in as a `ref_audio` block, which the
    FL2VA weights read even though their documented inputs are text and frames.
    See `payload.py` for the one core line that has to be worked around to send
    it alongside a keyframe.

    Every keyframe here is pinned (`_pin`) at its real pixel index, including
    the ones an old core's stock arithmetic would place correctly. A sound
    seam is a `ref_audio` block, and a reference block advances the cursor the
    target clip then starts at — so the moment sound crosses a seam, old
    stock's "frame 0" lands `ref_audio_t` time units *before* the clip's
    opening rather than on it, and the model reads the inherited frame as
    something from a second ago instead of as this clip's first frame. A core
    with the general anchor counts from the target's own origin natively; on
    an older one the keyed rows are repositioned there by `payload.py`, whose
    rewrite reproduces stock's arithmetic exactly when no references are in
    the layout, so nothing that was already right moves. `_encode_references`
    has pinned its seam for the same reason since references existed — this is
    the same repair on the FL2VA road.
    """
    latent, frame_count = _empty_av_latent(compiled.width, compiled.height, compiled.frames)

    images = []
    keyframes = []

    if compiled.continues:
        # The source segment's tail. It was generated on this same canvas
        # — the timeline pins one geometry across every segment — so the resize
        # is a no-op that exists only so a hand-built request cannot skip it.
        tail = _resize(loaded[PREV_FRAME]["image"], compiled.width, compiled.height, "center")
        # What Qwen sees is the last frame either way: the feather's extra
        # frames are motion context for the DiT, not something the prompt
        # names, so the presentation — and with it the prompt cache — does not
        # change with the seam's width.
        images.append(tail[-1:])
        if compiled.feather > 1:
            keyframes.extend(_context_keyframes(vae, tail[-compiled.feather:], compiled.feather))
        else:
            keyframes.append(_pin({"image": tail[-1:]}, 0))
    elif compiled.first_frame is not None:
        # Geometry anchor: plain stretch when the canvas was derived from this
        # image's own aspect ratio (`ratio_from_image`) and already matches it.
        # Cover-cropped when something else decided the canvas — a chosen
        # aspect source, a clip's, or the pill forced against it.
        crop = "disabled" if compiled.ratio_from_image else "center"
        image = _resize(loaded[compiled.first_frame.handle]["image"], compiled.width, compiled.height, crop)
        images.append(image)
        keyframes.append(_pin({"image": image}, 0))

    if compiled.last_frame is not None:
        # Follower: cover-crop onto whatever canvas the first frame established.
        # Follower whenever something already set the canvas — a first frame,
        # in a timeline the frame inherited from the previous segment, or any
        # canvas that is not this image's own shape.
        crop = "center" if (compiled.first_frame is not None or compiled.continues
                            or not compiled.ratio_from_image) else "disabled"
        image = _resize(loaded[compiled.last_frame.handle]["image"], compiled.width, compiled.height, crop)
        images.append(image)
        keyframes.append(_pin({"image": image}, frame_count - 1, stock=frame_count - 1))
    elif compiled.ends_on:
        # The supplied clip this segment runs into, opening where this one
        # ends. Cover-cropped like any follower — the clip is conformed to the
        # timeline's canvas on its way into the file and the frames pinned here
        # have to be the same picture.
        head = _resize(loaded[NEXT_FRAME]["image"], compiled.width, compiled.height, "center")
        # What Qwen sees is the frame the shot arrives on, blended or not —
        # the same rule the head seam follows, so widening the blend does not
        # change the presentation or the prompt cache.
        images.append(head[:1])
        if compiled.ends_feather > 1:
            # End-aligned: the clip's first frames occupy this segment's last
            # ones, so the motion runs through the cut instead of stopping at
            # it. Those frames are re-generated here and trimmed off the tail
            # before the pass is written out — `MiniMaxH3Reel` — so the clip
            # plays them once.
            keyframes.extend(_context_keyframes(
                vae, head[:compiled.ends_feather], compiled.ends_feather,
                at=frame_count - compiled.ends_feather))
        else:
            keyframes.append(_pin({"image": head[:1]}, frame_count - 1, stock=frame_count - 1))

    seam_audio = _seam_blocks(audio_vae, compiled, loaded, frame_count) \
        if compiled.encodes_audio() else []
    unpinned = [block for block in seam_audio if AUDIO_END_KEY not in block]
    if unpinned:
        # The tokenizer's `images=` branch is an `else` on `minimax_ref_items`:
        # pass both and the keyframes vanish from the presentation. So when there
        # is an audio reference to send, the keyframes are presented as reference
        # items instead. The two branches emit the same "<Picture N>: " + vision
        # tokens, so this is the same presentation by a different road — and the
        # keyframe *latents* still go in through `minimax_keyframes`, which is
        # what makes them pinned frames rather than loose references.
        #
        # Only unblended seams: a blended one's sound is pinned on this
        # segment's own timeline rather than sent as a reference, so it takes
        # no <Audio N> and the prompt carries no seam line naming one. One item
        # per block, so a segment with a live seam at both ends presents both.
        items = [{"type": "image", "data": image} for image in images]
        items.extend({"type": "audio"} for _ in unpinned)
        tokens = clip.tokenize(compiled.prompt, minimax_ref_items=items)
    else:
        tokens = clip.tokenize(compiled.prompt, images=images)
    cond = clip.encode_from_tokens_scheduled(tokens)

    if keyframes:
        for keyframe in keyframes:
            # A feathered seam's context blocks arrive already encoded — one
            # VAE call over the run, not one per frame.
            if "image" in keyframe:
                keyframe["latent"] = vae.encode(keyframe.pop("image"))
        cond = node_helpers.conditioning_set_values(cond, {
            "minimax_keyframes": keyframes,
            "minimax_frame_count": frame_count,
        })

    if seam_audio:
        cond = node_helpers.conditioning_set_values(cond, {"minimax_refs": seam_audio})
    return cond, latent


def _snap(value):
    return max(CANVAS_MULTIPLE, round(value / CANVAS_MULTIPLE) * CANVAS_MULTIPLE)


def video_canvas(source_w, source_h, gen_w, gen_h, ref_size):
    """What a reference video is encoded at. -> (width, height).

    'max' is core's own reference canvas: a 768 short edge under a 768*1344 area
    cap, or the clip's native size when that is already smaller. It is the
    ceiling — unlike a reference image, whose 'max' reaches for 2048, a video
    never gets more than this, so the setting only ever buys speed.

    'match' takes the generation's pixel area instead, scaled down from whatever
    'max' would have used and keeping the clip's own aspect. Down-only and
    measured against the 'max' canvas rather than the source, which is what makes
    it impossible for 'match' to come out the more expensive of the two.

    Worth the knob because of how a video block is shaped: it is `latent_t`
    copies of this grid, not one, so at full length a single reference clip is
    about as long as the target video itself and every row of it rides through
    every sampling step.
    """
    width, height = adapt_canvas(source_w, source_h)
    if source_w * source_h < width * height:
        width, height = _snap(source_w), _snap(source_h)
    if ref_size == "match":
        scale = min(1.0, math.sqrt((gen_w * gen_h) / (width * height)))
        width, height = _snap(width * scale), _snap(height * scale)
    return width, height


def _encode_references(clip, vae, audio_vae, compiled, loaded):
    """REF2VA."""
    latent, frame_count = _empty_av_latent(compiled.width, compiled.height, compiled.frames)

    items = []   # tokenizer presentation, in request order
    blocks = []  # DiT payload, same order
    pending_soundtrack = None  # set by a 'soundtrack' step, consumed by the 'video' step after it
    tally = Tally()  # what the references cost, for one line at the end

    for step in compiled.plan:
        asset = step["asset"]
        entry = loaded[asset.handle]

        if step["op"] == "image":
            def encode_image(entry=entry, asset=asset):
                image = entry["image"]
                height, width = image.shape[1], image.shape[2]
                if asset.ref_size == "match":
                    # Down-only, to the generation's pixel area.
                    scale = min(1.0, math.sqrt(
                        (compiled.width * compiled.height) / (width * height)))
                else:
                    # 'max': the reference pipeline's own 2048 short edge. Best identity
                    # retention, and several times slower — reference tokens ride through
                    # every sampling step.
                    scale = min(1.0, REF_IMAGE_SHORT_EDGE / min(width, height))
                target_w, target_h = _snap(width * scale), _snap(height * scale)
                resized = _resize(image, target_w, target_h, "disabled")
                return ({"latent": vae.encode(resized),
                         "presentation": _quantize(resized)},
                        {"latent_h": target_h // 16, "latent_w": target_w // 16})

            tensors, meta = _cached(
                f"@{asset.handle} image ({asset.ref_size})",
                _ref_key("image", asset, vae, compiled), encode_image, tally)
            items.append({"type": "image", "data": _present(tensors["presentation"])})
            blocks.append({
                "kind": "image",
                "latent_h": meta["latent_h"],
                "latent_w": meta["latent_w"],
                "latent": _restore(vae, tensors["latent"]),
            })

        elif step["op"] == "soundtrack":
            pending_soundtrack = _cached_ref_audio(
                "soundtrack", audio_vae, asset, entry, compiled, tally)
            items.append({"type": "audio"})

        elif step["op"] == "video":
            def encode_video(entry=entry, asset=asset):
                frames = entry["frames"]
                source_h, source_w = frames.shape[1], frames.shape[2]
                canvas_w, canvas_h = video_canvas(
                    source_w, source_h, compiled.width, compiled.height, asset.ref_size)
                frames = _resize(frames, canvas_w, canvas_h, "disabled")

                if frames.shape[0] > frame_count:
                    frames = frames[:frame_count]
                count = frames.shape[0]
                if count < 5:
                    raise ValueError(
                        f"@{asset.handle}: reference videos need at least 5 frames "
                        f"(~0.2 s at 24 fps), got {count}"
                    )
                while count % 17 != 5:
                    count -= 1
                frames = frames[:count]

                # Qwen sees the clip at 2 fps with timestamps, not every frame.
                sampled = list(range(0, frames.shape[0], FPS // 2))
                encoded = vae.encode(frames)
                return ({"latent": encoded,
                         "presentation": _quantize(frames[sampled])},
                        {"latent_t": int(encoded.shape[2]),
                         "latent_h": canvas_h // 16,
                         "latent_w": canvas_w // 16,
                         "timestamps": [i / 2.0 for i in range(len(sampled))]})

            tensors, meta = _cached(
                f"@{asset.handle} video ({asset.ref_size})",
                _ref_key("video", asset, vae, compiled), encode_video, tally)

            audio_latent, ref_audio_t = pending_soundtrack or (None, 0)
            pending_soundtrack = None

            items.append({
                "type": "video",
                "data": _present(tensors["presentation"]),
                "timestamps": meta["timestamps"],
            })
            blocks.append({
                "kind": "video_audio" if ref_audio_t else "video",
                "latent_t": meta["latent_t"],
                "latent_h": meta["latent_h"],
                "latent_w": meta["latent_w"],
                "ref_audio_t": ref_audio_t,
                "latent": _restore(vae, tensors["latent"]),
                "audio_latent": audio_latent,
            })

        elif step["op"] == "audio":
            audio_latent, ref_audio_t = _cached_ref_audio(
                "audio", audio_vae, asset, entry, compiled, tally)
            items.append({"type": "audio"})
            blocks.append({"kind": "audio", "ref_audio_t": ref_audio_t, "audio_latent": audio_latent})

        else:
            raise ValueError(f"unknown reference plan step {step['op']!r}")

    if compiled.encodes_audio():
        # After the user's blocks, so their <Audio N> numbering is untouched.
        # No presentation item and no label: a seam's sound is not a reference
        # the prompt cites, it is the seam's own sound riding in conditioning.
        blocks.extend(_seam_blocks(audio_vae, compiled, loaded, frame_count))

    keyframes = []
    if compiled.continues:
        # The seam alongside references — a combination old core's node
        # surface stops short of. The inherited frames ride as guides pinned
        # at their real positions: with references in the layout the target
        # clip no longer starts where old stock computes keyframe anchors, so
        # even the classic single-frame seam is pinned — natively on a core
        # with the general anchor, via `payload.py` on an older one, which
        # also rebuilds the latent list that core's `extra_conds` overwrites.
        tail = _resize(loaded[PREV_FRAME]["image"], compiled.width, compiled.height, "center")
        if compiled.feather > 1:
            keyframes.extend(_context_keyframes(vae, tail[-compiled.feather:], compiled.feather))
        else:
            keyframes.append(_pin({"latent": vae.encode(tail[-1:])}, 0))
    elif compiled.first_frame is not None:
        # The segment's own start frame, riding with references the same way
        # the seam does — pinned at frame 0 on this segment's own timeline.
        # Unlike the seam it *is* presented: it has a handle, the prompt may
        # cite it, and `_trailing_frame_labels` gave it the `<Picture N>` after
        # the references' own — so the item is appended after the plan's, where
        # the tokenizer counts it at exactly that ordinal. Stretched only when
        # the canvas is its own shape (`ratio_from_image`), cover-cropped
        # otherwise, like any follower of a canvas something else decided.
        crop = "disabled" if compiled.ratio_from_image else "center"
        image = _resize(loaded[compiled.first_frame.handle]["image"],
                        compiled.width, compiled.height, crop)
        items.append({"type": "image", "data": image})
        keyframes.append(_pin({"latent": vae.encode(image)}, 0))

    if compiled.last_frame is not None:
        # Follower whenever something else set the canvas; its own shape only
        # when it is the anchor itself (no first frame, no seam).
        crop = "center" if (compiled.first_frame is not None or compiled.continues
                            or not compiled.ratio_from_image) else "disabled"
        image = _resize(loaded[compiled.last_frame.handle]["image"],
                        compiled.width, compiled.height, crop)
        items.append({"type": "image", "data": image})
        keyframes.append(_pin({"latent": vae.encode(image)},
                              frame_count - 1, stock=frame_count - 1))
    elif compiled.ends_on:
        # The seam into a supplied clip, alongside references — the mirror of
        # `continues` above, and like it unpresented: the clip's opening frames
        # have no handle and the prompt never cites them.
        head = _resize(loaded[NEXT_FRAME]["image"], compiled.width, compiled.height, "center")
        if compiled.ends_feather > 1:
            keyframes.extend(_context_keyframes(
                vae, head[:compiled.ends_feather], compiled.ends_feather,
                at=frame_count - compiled.ends_feather))
        else:
            keyframes.append(_pin({"latent": vae.encode(head[:1])},
                                  frame_count - 1, stock=frame_count - 1))

    tally.say()
    tokens = clip.tokenize(compiled.prompt, minimax_ref_items=items)
    cond = clip.encode_from_tokens_scheduled(tokens)
    if blocks:
        cond = node_helpers.conditioning_set_values(cond, {"minimax_refs": blocks})
    if keyframes:
        cond = node_helpers.conditioning_set_values(cond, {
            "minimax_keyframes": keyframes,
            "minimax_frame_count": frame_count,
        })
    return cond, latent
