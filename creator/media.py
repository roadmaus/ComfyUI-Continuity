"""Loading assets by filename out of ComfyUI/input.

The whole point of the Creator node is that media is not wired in — the user
picks files in the UI and the node fetches them here at execute time. That makes
this the only module that touches disk.
"""

import logging
import os
import re

import av
import numpy as np
import torch
from PIL import Image, ImageOps, UnidentifiedImageError

import folder_paths
# Core's PyAV-based loader, not torchaudio.load: recent torchaudio routes load()
# through torchcodec, which ComfyUI does not ship. This is the same decoder
# LoadAudio uses, so we accept exactly the files the rest of ComfyUI accepts.
from comfy_extras.nodes_audio import load as _load_audio_file
# The same snapping `encode` will do, so `load_all` can work out how much of a
# reference clip can possibly survive it.
from comfy_extras.nodes_minimax_h3 import align_frame_count

from . import mux

TARGET_FPS = 24


class MediaError(ValueError):
    """A referenced file is missing or cannot be read as its declared kind."""


# A cast look's frame, addressed where it already sits: `atlas:000123` names one
# of the thousand stills this pack ships under `web/creator/presets/atlas/
# full/`. Casting a look used to copy the frame into `input/style_refs/` purely so
# it would have an input-relative path — a file per look ever cast, kept forever,
# cluttering the picker and every core LoadImage combo. The frontend half of the
# pair is `web/creator/presets/atlasref.js`; between the two of them this
# is the only place on either side that has to know a second kind of path exists.
ATLAS_SCHEME = "atlas:"
# Out of the package and back down into the frontend: the atlas is shipped as
# part of `web/` because the picker draws from it, and this is the one place the
# backend reaches across that line.
ATLAS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "web", "creator", "presets", "atlas", "full")
# The id and nothing else. A reference is built by this pack from the vendored
# index, never typed, so anything that is not digits is either a corrupted blob
# or a crafted one — and either way the answer is no, rather than a filename
# joined onto a path.
_ATLAS_CLIP = re.compile(r"\A\d+\Z")


def resolve(filename):
    """Filename from the picker -> absolute path, honouring ComfyUI annotations.

    A catalogue frame resolves to the file the pack ships; everything else is a
    path under input/ (or output/, annotated) exactly as before.
    """
    name = str(filename)
    if name.startswith(ATLAS_SCHEME):
        clip = name[len(ATLAS_SCHEME):]
        if not _ATLAS_CLIP.match(clip):
            raise MediaError(f"{name!r} is not a style frame this pack ships")
        path = os.path.join(ATLAS_DIR, f"{clip}.webp")
        if not os.path.isfile(path):
            raise MediaError(f"{name!r} is not a style frame this pack ships")
        return path
    if not folder_paths.exists_annotated_filepath(filename):
        raise MediaError(f"{filename!r} is not in the input folder any more")
    return folder_paths.get_annotated_filepath(filename)


def stamp(filename):
    """A file's identity for a cache key -> (absolute path, mtime_ns, size).

    Content addressing without reading the content: a reference file is a video
    somebody may have replaced in place under the same name, and a cache that
    keyed on the name alone would hand back the old clip's latents forever.
    The same reasoning `timeline.stamps` uses to invalidate the segment node,
    said about one file instead of a whole request — and like it, mtime rather
    than a hash, because hashing a gigabyte of source to save one encode is the
    wrong way round.
    """
    path = resolve(filename)
    try:
        info = os.stat(path)
    except OSError as exc:
        raise MediaError(f"{filename!r} could not be read: {exc}") from exc
    return path, int(info.st_mtime_ns), int(info.st_size)


class Deferred(dict):
    """A `load_all` entry that decodes the file the first time it is read.

    `load_all` used to decode everything a request named before `encode` was
    handed any of it, which is the right shape when every decoded file is about
    to be used. It stopped being right when references started coming back out
    of `latents.py`: a cached reference needs neither its pixels nor its
    soundtrack, and decoding a high-resolution source to then throw it away is
    most of what the cache was built to avoid.

    A dict subclass rather than a wrapper because `encode` reads these as
    `entry["frames"]` in half a dozen places and a seam assigns a plain dict
    into the same map — so the lazy ones have to *be* dicts, not stand in for
    them. Decoded once: the second read is the first read's result, which
    matters for a `picture+sound` reference whose picture and soundtrack are
    two plan steps against one file.
    """

    def __init__(self, decode):
        super().__init__()
        self._decode = decode

    def _fill(self):
        # Cleared only once the decode has actually returned. A file that fails
        # to open has to fail again on the next read rather than quietly read
        # as an entry with nothing in it.
        if self._decode is not None:
            self.update(self._decode())
            self._decode = None

    def __getitem__(self, key):
        self._fill()
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._fill()
        return super().get(key, default)

    def __contains__(self, key):
        self._fill()
        return super().__contains__(key)


def image_size(filename):
    """(width, height) without decoding pixels — used for the adaptive canvas.

    A video container answers the same question since the aspect source became
    a choice: any attached picture can set the canvas, and a reference clip's
    picture is read off its header (rotation honoured) exactly as the probe
    route reads it. Dispatch is by what the file actually is — PIL knows every
    still format and says so when handed anything else.
    """
    path = resolve(filename)
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            return img.size
    except UnidentifiedImageError:
        pass
    with av.open(path) as container:
        stream = next(iter(container.streams.video), None)
        if stream is None:
            raise MediaError(f"{filename!r} has no picture to take a size from")
        width, height = int(stream.width), int(stream.height)
        if int(getattr(stream, "rotation", 0) or 0) % 180:
            width, height = height, width
        return width, height


def load_image(filename):
    """-> float tensor [1, H, W, 3] in 0..1, the ComfyUI IMAGE layout."""
    with Image.open(resolve(filename)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        array = np.array(img, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def _cut_audio(filename, audio, trim):
    """Cut an AUDIO dict {waveform [1, C, L], sample_rate} down to `trim` seconds."""
    if trim is None:
        return audio
    start, end = trim
    rate = int(audio["sample_rate"])
    length = audio["waveform"].shape[-1]
    first = min(int(round(start * rate)), length)
    last = min(int(round(end * rate)), length)
    if last - first < 1:
        raise MediaError(
            f"{filename!r}: the {start:.2f}–{end:.2f} s segment is past the end of the audio"
        )
    return {"waveform": audio["waveform"][..., first:last], "sample_rate": rate}


def load_audio(filename, trim=None):
    """-> the ComfyUI AUDIO dict {waveform [1, C, L], sample_rate}.

    The container may be a video: referencing a clip's soundtrack alone means
    decoding the audio stream out of the same mp4 the picture would come from.
    """
    path = resolve(filename)
    try:
        waveform, sample_rate = _load_audio_file(path)
    except ValueError as exc:
        # The decoder names no file, and "No audio stream found" on its own does
        # not say which of a dozen references it is talking about.
        raise MediaError(f"{filename!r}: {exc}") from exc
    audio = {"waveform": waveform.unsqueeze(0), "sample_rate": int(sample_rate)}
    return _cut_audio(filename, audio, trim)


def _decode_window(trim, max_seconds):
    """-> (start_time, duration) for the decoder. A duration of 0 means "to EOF".

    The decoder seeks to the window and stops demuxing at the end of it, so
    frames outside the window are never decoded. Handing it the window is the
    whole difference between reading a 60-second source and reading the two
    seconds of it that were asked for — and decode is where a long clip hurts,
    because frames arrive as float32 and cost ~25 MB each at 1080p.
    """
    start = trim[0] if trim is not None else 0.0
    duration = (trim[1] - trim[0]) if trim is not None else 0.0
    if max_seconds is not None:
        # Two frames of slack. The 24 fps resample rounds, and a reference that
        # came back one frame short of the generation's length would lose a frame
        # off the end of the window the user actually asked for.
        cap = max_seconds + 2.0 / TARGET_FPS
        duration = min(duration, cap) if duration else cap
    return start, duration


def _frames_at(filename, start, duration, fps):
    """The window's picture at `fps` -> [N, H, W, 3] float32, or empty.

    Through `mux.conform` — the same timestamp-driven resample the finished
    file splices a clip with — rather than through core's `VideoFromFile`,
    which hands back a bare stack of frames and the stream's *average* rate.
    Resampling that stack by the average is right for constant-rate footage
    and wrong for anything else: a phone clip or a screen recording carries
    its frames at whatever intervals they were captured, an average says
    nothing about where any one of them falls, and a seam that read its tail
    that way continued from a frame the reel never showed. Reading both
    through one filter is what makes them the same frame.
    """
    frames = [
        torch.from_numpy(frame.to_ndarray(format="rgb24"))
        for frame in mux.conform(av, resolve(filename), start, duration, fps)
    ]
    if not frames:
        return torch.zeros(0, 1, 1, 3)
    return torch.stack(frames).float() / 255.0


def load_video(filename, want_audio=False, trim=None, max_seconds=None):
    """-> (frames [N, H, W, 3] resampled to 24 fps, audio dict or None).

    H3 reads reference video at 24 fps, so a clip shot at any other rate is
    resampled here rather than being handed over at the wrong tempo — the
    model would read a 30 fps clip as 25% slow motion. The resample is by
    timestamp, see `_frames_at`.

    `trim` is (start, end) in seconds and `max_seconds` bounds how much of the
    clip can matter downstream. Both go to the decoder as one seek window rather
    than being sliced off a fully decoded clip — see `_decode_window`. The
    soundtrack is cut to that same window, which is what keeps the picture and
    the sound from drifting apart.

    The window anchors the resample at the requested second: the first frame
    out is the source frame nearest the window's start, and the rest fall on a
    24 fps grid from there.
    """
    start, duration = _decode_window(trim, max_seconds)
    try:
        frames = _frames_at(filename, start, duration, TARGET_FPS)
    except ValueError as exc:
        raise MediaError(f"{filename!r} has no video frames") from exc
    if frames.shape[0] == 0:
        if trim is not None:
            raise MediaError(
                f"{filename!r}: the {trim[0]:.2f}–{trim[1]:.2f} s segment is past the end of the clip"
            )
        raise MediaError(f"{filename!r} has no video frames")

    audio = None
    if want_audio:
        # The window's own soundtrack, cut in seconds: the picture's frame count
        # was decided by the timestamps, so the sound is cut by them too. Read
        # to the end of the file when the window is; a bare start still cuts.
        audio = load_audio(filename)
        end = start + duration if duration else \
            audio["waveform"].shape[-1] / audio["sample_rate"]
        audio = _cut_audio(filename, audio, (start, end))

    return frames, audio


# A supplied clip's window is cut at the second and its frames are resampled to
# 24 fps, so asking for exactly `count / 24` seconds can come back one frame
# short of `count`. The window is widened by this much and the run is taken
# from the end of what arrives — cheap, since it is still a seek window and not
# the clip.
_SEAM_SLACK_S = 0.5


def _clip_window(spec):
    """(start, end) of a clip card's own stretch, in the source's seconds."""
    start = float(spec.get("start") or 0.0)
    return start, start + float(spec.get("duration") or 0.0)


def clip_frames(spec, count, at="tail"):
    """The first or last `count` frames of a clip card's window, at 24 fps.

    What a seam beside supplied footage inherits, and the whole of what the
    clip is ever decoded into memory for: at the head it is one frame (the
    shot before it ends there), at the tail a feathered run of at most 39. The
    clip itself reaches the finished file without being decoded at all — see
    `mux._write_clip` — so this is bounded by the seam's width rather than by
    the clip's length, and a five-minute source costs what a five-second one
    does.
    """
    start, end = _clip_window(spec)
    span = count / TARGET_FPS + _SEAM_SLACK_S
    window = (start, min(end, start + span)) if at == "head" \
        else (max(start, end - span), end)
    frames, _ = load_video(spec["filename"], trim=window)
    if frames.shape[0] < count:
        raise MediaError(
            f"{spec['filename']!r}: this seam needs {count} frames and the "
            f"clip's segment only holds {frames.shape[0]} at 24 fps — shorten "
            f"the blend, or use more of the clip"
        )
    return frames[:count] if at == "head" else frames[-count:]


def clip_audio(spec, seconds, at="tail"):
    """The first or last `seconds` of a clip card's soundtrack.

    Refused rather than silenced when the file carries no sound: a seam that
    inherits silence is a real thing to ask for, but it is not what "carry the
    clip's sound across" means, and inventing it here would hide a clip the
    user thought was noisy.
    """
    start, end = _clip_window(spec)
    window = (start, min(end, start + seconds)) if at == "head" \
        else (max(start, end - seconds), end)
    return load_audio(spec["filename"], trim=window)


def load_all(compiled):
    """Every file a `Compiled` names -> {handle: decoded media}, for `encode`.

    Shared by the Creator node and by a timeline segment, which have the same
    job here: a segment is a whole generation, so it loads its media the same
    way. A continuing segment's inherited start frame is the one thing not from
    disk, so the caller adds it under `encode.PREV_FRAME`.
    """
    # How much of a reference clip can possibly reach the model: `encode` cuts
    # every reference video down to the generation's own frame count, so a
    # 60-second source spends 60 seconds of decode to have 6 seconds of it used.
    # Bounding the decode by the same number instead makes a long source cost
    # what a short one does, and changes nothing about what is sent.
    #
    # It bounds the soundtrack of a `picture+sound` video too, which is a real
    # change: that audio used to be sent at its full trimmed length while its
    # picture was cut short, so the two halves of one reference described
    # different spans of time. A standalone audio reference is not bounded — it
    # is not paired with a picture and a long music cue is an ordinary thing to
    # cite.
    limit = align_frame_count(max(5, compiled.frames)) / TARGET_FPS

    # Keyframes are decoded here and now; everything the reference cache can
    # stand in for is deferred (`Deferred`) so that a hit never reaches the
    # disk the file is on. A first or last frame is a single still that is
    # wanted either way, so deferring it would buy nothing and cost a class.
    loaded = {}
    for asset in (compiled.first_frame, compiled.last_frame):
        if asset is not None:
            loaded[asset.handle] = {"image": load_image(asset.filename)}
    for asset in compiled.ref_images:
        loaded[asset.handle] = Deferred(
            lambda asset=asset: {"image": load_image(asset.filename)})
    for asset in compiled.ref_videos:
        def decode(asset=asset):
            # The one decode long enough to be worth announcing. It only runs on
            # a cache miss (`Deferred`), and on a high-resolution source it is a
            # real part of the wait before sampling — `encode._cached` has just
            # said this reference is being encoded, and this says which half of
            # that is happening now.
            logging.info("[MiniMax] @%s: decoding %s", asset.handle, asset.filename)
            frames, audio = load_video(
                asset.filename, want_audio=asset.track == "picture+sound",
                trim=asset.trim, max_seconds=limit)
            return {"frames": frames, "audio": audio}
        loaded[asset.handle] = Deferred(decode)
    # Both real audio files and videos referenced for their sound alone: the
    # decoder reads a soundtrack out of a video container the same way.
    for asset in compiled.ref_audios:
        loaded[asset.handle] = Deferred(
            lambda asset=asset: {"audio": load_audio(asset.filename, trim=asset.trim)})
    return loaded
