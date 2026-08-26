"""Frame and waveform previews, decoded here rather than in the browser.

Both of these used to be the page's job. The picker grid painted a `<video>` per
cell and let the browser seek to 0.1 s for a still; the segment editor fetched
the whole file and handed it to Web Audio to get a waveform. On a fast local
media stack that is invisible, and everywhere else it collapses: a grid of thirty
clips is thirty parallel media loads squeezed through a six-connection budget,
each pulling megabytes to paint a 140 px thumbnail, and opening the editor adds a
whole-file download on top of them. It also assumes the browser can decode H.264
and AAC at all, which a distro-built Chromium often cannot.

Decoding one frame and one peak array server-side turns all of that into a few
kilobytes of JPEG and JSON, over one connection, with no codec support required
of the client beyond baseline JPEG.

Results are cached on disk under the user directory, keyed by the source file's
identity, so the cost is paid once per clip rather than once per time the picker
is opened.
"""

import asyncio
import hashlib
import json
import os

from PIL import Image

import folder_paths

# The grid draws at ~140 px and the editor is not a viewer, so the long side of a
# thumbnail never needs to be larger than a retina version of that cell.
THUMB_LONG_EDGE = 320
THUMB_QUALITY = 78

# ~1 px per bucket on a wide editor modal, matching what the canvas can show.
PEAK_BUCKETS = 1400
# Peaks are a picture of where the sound is, not an analysis: 8 kHz mono is
# plenty for that and keeps the decode cheap on a long clip.
PEAK_RATE = 8000

# Decoding is CPU work on a thread, and the picker will happily ask for thirty
# thumbnails at once. Without a ceiling that is thirty decoder threads fighting
# over the same cores while ComfyUI is trying to run a graph.
MAX_PARALLEL_DECODES = 3

# Cache keys whose decode already failed. A file that is not really a video must
# not be re-decoded every single time the grid is rendered.
_FAILED = set()

_gate = None
_gate_loop = None


def _semaphore():
    """One semaphore per event loop — ComfyUI only has the one, but a semaphore
    bound to a dead loop is a deadlock rather than an error."""
    global _gate, _gate_loop
    loop = asyncio.get_running_loop()
    if _gate is None or _gate_loop is not loop:
        _gate = asyncio.Semaphore(MAX_PARALLEL_DECODES)
        _gate_loop = loop
    return _gate


def _cache_dir():
    directory = os.path.join(folder_paths.get_user_directory(), "continuity", "previews")
    os.makedirs(directory, exist_ok=True)
    return directory


def _cache_path(path, kind, suffix):
    """Cache file for `path`, invalidated by the source's mtime and size.

    Keyed by identity rather than name so replacing a file in the input folder
    re-decodes it, and so two clips of the same name in different subfolders do
    not share a thumbnail.
    """
    stat = os.stat(path)
    key = hashlib.sha1(
        f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{kind}".encode("utf-8", "surrogateescape")
    ).hexdigest()
    return os.path.join(_cache_dir(), f"{key}.{suffix}")


def _write_atomically(target, write):
    """Write through a temp file so a half-decoded thumbnail is never served —
    two picker cells can ask for the same clip at the same moment."""
    temporary = f"{target}.{os.getpid()}.part"
    try:
        write(temporary)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


async def _produce(path, kind, suffix, render):
    """-> cache path, or None if this file cannot be decoded as `kind`.

    The decode runs on a thread: PyAV blocks, and blocking here would stall the
    whole ComfyUI server, queue and websocket included.
    """
    try:
        target = _cache_path(path, kind, suffix)
    except OSError:
        return None
    if os.path.exists(target):
        return target
    if target in _FAILED:
        return None

    async with _semaphore():
        # Another request may have finished this one while we waited for a slot.
        if os.path.exists(target):
            return target
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _write_atomically, target, lambda tmp: render(path, tmp))
        except Exception:  # noqa: BLE001 — an undecodable file is a missing preview, not an error
            _FAILED.add(target)
            return None
    return target


# ---- video frame ------------------------------------------------------------


def _seek_past_the_leader(container, stream):
    """Move to ~10% in, capped at a second.

    Frame zero of a real clip is very often a fade-in from black, which makes a
    grid of them look like a grid of empty cells. Best effort: a container with
    no duration or no index stays where it is.
    """
    import av

    if not container.duration:
        return
    seconds = min(1.0, float(container.duration / av.time_base) * 0.1)
    if seconds <= 0:
        return
    try:
        container.seek(int(seconds / stream.time_base), stream=stream)
    except Exception:  # noqa: BLE001
        pass


def _render_thumb(path, out):
    import av

    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        _seek_past_the_leader(container, stream)
        frame = next(container.decode(stream), None)
        if frame is None:
            # The seek landed past the last usable keyframe: take it from the top.
            container.seek(0)
            frame = next(container.decode(stream), None)
        if frame is None:
            raise ValueError("no decodable video frame")
        image = frame.to_image()

    image.thumbnail((THUMB_LONG_EDGE, THUMB_LONG_EDGE), Image.LANCZOS)
    image.convert("RGB").save(out, "JPEG", quality=THUMB_QUALITY, optimize=True)


async def thumbnail(path):
    """-> path to a JPEG still of this clip, or None if it has no readable frame."""
    return await _produce(path, "thumb", "jpg", _render_thumb)


# ---- waveform ---------------------------------------------------------------


def _render_peaks(path, out):
    import av
    import numpy as np

    windows = []
    with av.open(path) as container:
        if not container.streams.audio:
            # A silent clip is a real answer, not a failure: cache it so the
            # editor stops asking, and let the timeline stay plain.
            with open(out, "w", encoding="utf-8") as handle:
                json.dump({"peaks": None}, handle)
            return
        stream = container.streams.audio[0]
        stream.thread_type = "AUTO"
        resampler = av.AudioResampler(format="flt", layout="mono", rate=PEAK_RATE)
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                samples = resampled.to_ndarray()
                if samples.size:
                    windows.append(float(np.abs(samples).max()))

    peaks = None
    if windows:
        source = np.asarray(windows, dtype=np.float32)
        # One decoded frame is ~20 ms, so a short clip has fewer windows than
        # buckets — send what there is and let the canvas stretch it.
        count = min(PEAK_BUCKETS, source.size)
        edges = np.linspace(0, source.size, count + 1).astype(int)
        bucketed = np.array([source[a:b].max() if b > a else 0.0 for a, b in zip(edges, edges[1:])])
        loudest = float(bucketed.max())
        if loudest > 0:
            # Normalised, because a quiet recording drawn at true scale is a flat
            # line and says nothing about where the sound is.
            peaks = [round(float(value) / loudest * 0.94, 3) for value in bucketed]

    with open(out, "w", encoding="utf-8") as handle:
        json.dump({"peaks": peaks}, handle)


async def waveform(path):
    """-> {"peaks": [0..1] or None}, or None if the file could not be decoded.

    The duration is deliberately not here: the segment editor takes it from the
    header probe, which answers in milliseconds instead of waiting on a decode.
    """
    cached = await _produce(path, "peaks", "json", _render_peaks)
    if cached is None:
        return None
    try:
        with open(cached, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None
