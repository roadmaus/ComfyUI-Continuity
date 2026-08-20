"""Loading assets by filename out of ComfyUI/input.

The whole point of the Creator node is that media is not wired in — the user
picks files in the UI and the node fetches them here at execute time. That makes
this the only module that touches disk.
"""

import av
import numpy as np
import torch
from PIL import Image, ImageOps, UnidentifiedImageError

import folder_paths
from comfy_api.latest import InputImpl
# Core's PyAV-based loader, not torchaudio.load: recent torchaudio routes load()
# through torchcodec, which ComfyUI does not ship. This is the same decoder
# LoadAudio uses, so we accept exactly the files the rest of ComfyUI accepts.
from comfy_extras.nodes_audio import load as _load_audio_file
# The same snapping `encode` will do, so `load_all` can work out how much of a
# reference clip can possibly survive it.
from comfy_extras.nodes_minimax_h3 import align_frame_count

TARGET_FPS = 24


class MediaError(ValueError):
    """A referenced file is missing or cannot be read as its declared kind."""


def resolve(filename):
    """Filename from the picker -> absolute path, honouring ComfyUI annotations."""
    if not folder_paths.exists_annotated_filepath(filename):
        raise MediaError(f"{filename!r} is not in the input folder any more")
    return folder_paths.get_annotated_filepath(filename)


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

    `VideoFromFile` takes a window, seeks to it and stops demuxing at the end of
    it, so frames outside the window are never decoded. Handing it the window is
    the whole difference between reading a 60-second source and reading the two
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


def load_video(filename, want_audio=False, trim=None, max_seconds=None):
    """-> (frames [N, H, W, 3] resampled to 24 fps, audio dict or None).

    H3 reads reference video at 24 fps, so a clip shot at any other rate is
    resampled by nearest-frame index here rather than being handed over at the
    wrong tempo — the model would read a 30 fps clip as 25% slow motion.

    `trim` is (start, end) in seconds and `max_seconds` bounds how much of the
    clip can matter downstream. Both go to the decoder as one seek window rather
    than being sliced off a fully decoded clip — see `_decode_window`. The
    soundtrack is cut to that same window by the decoder, which is what keeps
    the picture and the sound from drifting apart.

    The window anchors the resample at the requested second rather than at a
    24 fps index counted from the head of the file. On a trim that lands on a
    frame boundary the two agree exactly; off one they can pick a source frame
    either side of it, which is a difference of one frame at 24 fps and is the
    more faithful of the two readings of what was asked for.
    """
    start, duration = _decode_window(trim, max_seconds)
    components = InputImpl.VideoFromFile(
        resolve(filename), start_time=start, duration=duration).get_components()
    frames = components.images
    if frames is None or frames.shape[0] == 0:
        if trim is not None:
            raise MediaError(
                f"{filename!r}: the {trim[0]:.2f}–{trim[1]:.2f} s segment is past the end of the clip"
            )
        raise MediaError(f"{filename!r} has no video frames")
    frames = frames[..., :3]

    source_fps = float(components.frame_rate)
    if source_fps > 0 and abs(source_fps - TARGET_FPS) > 1e-3:
        count = max(1, round(frames.shape[0] / source_fps * TARGET_FPS))
        index = torch.arange(count, dtype=torch.float64) * (source_fps / TARGET_FPS)
        index = index.floor().clamp(0, frames.shape[0] - 1).long()
        frames = frames[index]

    audio = None
    if want_audio:
        if components.audio is None:
            raise MediaError(f"{filename!r} has no audio track to use as a reference")
        audio = components.audio

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

    loaded = {}
    for asset in (compiled.first_frame, compiled.last_frame):
        if asset is not None:
            loaded[asset.handle] = {"image": load_image(asset.filename)}
    for asset in compiled.ref_images:
        loaded[asset.handle] = {"image": load_image(asset.filename)}
    for asset in compiled.ref_videos:
        frames, audio = load_video(
            asset.filename, want_audio=asset.track == "picture+sound",
            trim=asset.trim, max_seconds=limit)
        loaded[asset.handle] = {"frames": frames, "audio": audio}
    # Both real audio files and videos referenced for their sound alone: the
    # decoder reads a soundtrack out of a video container the same way.
    for asset in compiled.ref_audios:
        loaded[asset.handle] = {"audio": load_audio(asset.filename, trim=asset.trim)}
    return loaded
