"""What a bench is made of, apart from the work it does.

A bench is a file going in, a surface with dials on it, and a file coming out.
Two of those three are the same whichever bench it is: reading a frame off
whatever was dropped on it, filling a `choice` dial from the model folders,
clamping whatever the sliders sent, naming the result, and — the long one —
decoding a clip, putting every frame through something and encoding it again
with its sound and its timing intact.

All of it was written for the tracing bench and all of it was general the day it
was written; this module is where it moved when the upscale bench needed the
same plumbing. `control.py` and `upscale.py` are now the two things that are
genuinely different about a bench: what a frame goes through, and what the
result is *for*.

**The two things `transcode` does that a per-frame function cannot.**

A tracing comes back the size it went in and an upscale does not, so the size of
the file being written is not a property of the source. `size` is the policy —
given the source's display dimensions it says what the output's are — and every
frame is fitted to that answer. The tracing bench passes the identity and gets
exactly what it had before; the upscale bench passes the scale, which is also
what makes a x4 model land on a x2 target without a second code path.

And some work is not per-frame at all. A tracing looks at one frame because
that is all a tracing is; a restoration model looks at several at once, which is
the whole of how it keeps a clip from boiling. So `work` takes a list and
returns a list, `chunk` says how many go in at a time, and `overlap` says how
many of them the next chunk re-does so the two can be crossfaded into each other
— because chunks sampled independently do not join invisibly, and a step every
few seconds is the artefact somebody would notice first.
"""

import os
import threading
from fractions import Fraction

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

import folder_paths

from . import settings

# The long edge a preview frame is cut to before anything is done to it. A
# preview exists to answer "is this dial right", and that question is answered
# at 768 pixels as well as at 4096 — and answered in a tenth of the time, which
# is what makes dragging a slider feel like a control rather than a request.
PREVIEW_LONG_EDGE = 768


# One piece of model work at a time. The runs no longer need this — they are
# queued jobs now (`creator/jobs.py`) and the queue runs one thing at a time —
# but the *previews* are still plain HTTP handlers on a thread pool, so without
# it a slider dragged in two tabs would have two frames racing for the same
# weights. One lock across every bench rather than one apiece for the same
# reason as ever: there is one GPU, and both benches can be open.
#
# It cannot pile up behind a job any more: a preview asked for while the queue is
# busy is refused before it reaches this (`jobs.refuse_if_busy`), so the only
# overlap left is the one preview that was already in flight when a job started.
ONE_AT_A_TIME = threading.Lock()


class BenchError(ValueError):
    """A file cannot be read, or the work cannot be run on it.

    Every bench's own error subclasses this, so a route that catches its own
    bench's error catches what the plumbing raises underneath it too.
    """


# ---- the dials --------------------------------------------------------------
#
# Every bench keeps one tuple of what it can do, and each entry keeps a `params`
# tuple of dials. The frontend builds its list and its sliders from that over the
# wire, so adding an operator is adding an entry and a function, and nothing in
# the frontend has to learn about it. The three functions below are the two ends
# of that: filling the machine-specific parts in on the way out, and clamping
# whatever came back on the way in.


def files(folders):
    """Every filename in `folders`, in the order the folders were named.

    Deduplicated, because a name that is in two of them is one file as far as
    the dial is concerned and the caller will find it in whichever folder holds
    it. An unconfigured folder is an empty one rather than an error: a ComfyUI
    without `geometry_estimation` is simply a ComfyUI where Depth is not ready
    yet, and that is the sentence the surface already knows how to say.
    """
    seen, names = set(), []
    for folder in folders:
        try:
            listing = folder_paths.get_filename_list(folder)
        except Exception:  # noqa: BLE001 — an unconfigured folder is an empty one
            continue
        for name in listing:
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def catalogue(operators):
    """The operators, as the frontend reads them — with this machine filled in.

    Every `choice` dial names the model folders it draws from, and this is where
    that turns into an actual list of files. `ready` falls out of it: an operator
    is ready when every file it needs was found, so nothing has to be marked by
    hand and a model dropped into the folder makes its operator work without a
    line changing anywhere.

    Walks the model directories, so callers run it off the event loop.
    """
    out = []
    for operator in operators:
        entry = dict(operator)
        params, ready = [], True
        for spec in operator["params"]:
            spec = dict(spec)
            if spec["kind"] == "choice":
                spec["options"] = files(spec.pop("from"))
                spec["default"] = spec["options"][0] if spec["options"] else ""
                ready = ready and bool(spec["options"])
            params.append(spec)
        entry["params"] = params
        entry["ready"] = ready
        out.append(entry)
    return out


def values(operator, raw, error=BenchError):
    """Whatever arrived -> the values this operator actually takes.

    Clamped rather than rejected, and defaulted where a key is missing: these
    numbers come off sliders that already hold the bounds, so anything out of
    range is a stale frontend or a hand-made request, and neither is worth an
    error page.
    """
    picked = {}
    for spec in operator["params"]:
        given = raw.get(spec["key"])
        if spec["kind"] == "switch":
            picked[spec["key"]] = truthy(given, spec["default"])
            continue
        if spec["kind"] == "text":
            # Free words, defaulted rather than refused: an emptied box means
            # the default question, not no question.
            picked[spec["key"]] = str(given or "").strip() or spec["default"]
            continue
        if spec["kind"] == "option":
            # A fixed set the operator declares, rather than a walk of a folder:
            # nothing about the machine can change what a colour transfer is
            # called, so an unknown value is a stale frontend and takes the
            # default rather than an error page.
            picked[spec["key"]] = (given if given in spec["options"]
                                   else spec["default"])
            continue
        if spec["kind"] == "choice":
            # Not clamped like a slider: a name that is not on the disk cannot be
            # nudged into one that is. A stale pick falls back to the first file
            # there is, and no file at all is the one thing this raises for —
            # with `needs`, because "pick a model" is not useful to somebody who
            # has not downloaded one.
            options = files(spec["from"])
            if not options:
                raise error(f"{operator['label']} needs {operator['needs']}")
            picked[spec["key"]] = given if given in options else options[0]
            continue
        try:
            number = float(given)
        except (TypeError, ValueError):
            number = float(spec["default"])
        picked[spec["key"]] = min(float(spec["max"]), max(float(spec["min"]), number))
    return picked


def truthy(given, fallback):
    if given is None:
        return bool(fallback)
    if isinstance(given, str):
        return given.strip().lower() in ("1", "true", "yes", "on")
    return bool(given)


def model_path(folders, name):
    """Where `name` actually is, across the folders a dial draws from."""
    for folder in folders:
        try:
            found = folder_paths.get_full_path(folder, name)
        except Exception:  # noqa: BLE001 — an unconfigured folder holds nothing
            continue
        if found:
            return found
    raise BenchError(f"{name} is not in models/{' or models/'.join(folders)} any more")


# What is loaded, and under what. One slot per kind, keyed by whatever names the
# file that is in it: a preview is asked for on every drag of a dial, and one
# that reloaded two gigabytes per drag would not be a preview.
_HELD = {}


def hold(kind, key, load):
    """The model for `key`, loading it only when the key changed."""
    slot = _HELD.setdefault(kind, {"key": None, "held": None})
    if slot["key"] != key or slot["held"] is None:
        # Dropped before the load rather than after, so a failed load does not
        # leave the old model pinned in memory under a name nobody asked for.
        slot.update(key=None, held=None)
        slot.update(key=key, held=load())
    return slot["held"]


def _patchers(held):
    """Every ComfyUI model patcher inside a held slot, whatever shape it is in.

    A slot holds what its loader returned, and the four loaders return four
    shapes: a bare patcher from `load_diffusion_model`, a `VAE` and an upscale
    model that each carry one on `.patcher`, and a tuple of both from
    `load_checkpoint_guess_config`. Rather than teach this function about each,
    it flattens and asks every piece for a patcher.
    """
    stack = list(held) if isinstance(held, (tuple, list)) else [held]
    for item in stack:
        patcher = getattr(item, "patcher", item)
        if hasattr(patcher, "model"):
            yield patcher


def release():
    """Hand every held model's weights back to the offload device.

    Called at the end of every job. The models stay in `_HELD` — reloading two
    gigabytes because a dial moved is what `hold` exists to prevent — but idle
    VRAM should be nobody's, and a bench is a button rather than a node in a
    graph: a Restore may be the last thing that happens for an hour, and until
    this existed its SeedVR2 and VAE sat in ComfyUI's loaded-model list against
    the next render's budget until something else needed the space.

    `refine_local.release` is the same call for the same reason, and was the only
    one of these that had it.
    """
    try:
        import comfy.model_management as mm
    except Exception:  # noqa: BLE001 — freeing is best effort; the work already happened
        return
    for slot in _HELD.values():
        if slot["held"] is None:
            continue
        for patcher in _patchers(slot["held"]):
            try:
                mm.unload_model_and_clones(patcher)
            except Exception:  # noqa: BLE001 — one that will not unload is not worth a failed job
                pass


def torch_frame(frame):
    """uint8 (H, W, 3) -> the (1, H, W, 3) float IMAGE tensor core's code takes."""
    import torch

    return torch.from_numpy(np.ascontiguousarray(frame)).float().div_(255.0).unsqueeze(0)


def from_torch(picture):
    """(1, H, W, 3) float in 0..1 -> the uint8 frame the encoder takes back."""
    return picture[0].clamp(0, 1).mul(255).round().to("cpu").numpy().astype(np.uint8)


# ---- reading a source -------------------------------------------------------


def open_image(path):
    try:
        with Image.open(path) as picture:
            # The camera's rotation tag, applied — a portrait phone clip worked
            # on sideways would come back sideways.
            return np.asarray(ImageOps.exif_transpose(picture).convert("RGB"))
    except (UnidentifiedImageError, OSError) as exc:
        raise BenchError(f"{os.path.basename(path)} could not be read as a picture") from exc


def fit(frame, long_edge):
    """`frame` shrunk to fit `long_edge`, or left alone if it already does."""
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= long_edge:
        return frame
    scale = long_edge / longest
    picture = Image.fromarray(frame).resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
    return np.asarray(picture)


def is_video(path):
    return bool(folder_paths.filter_files_content_types([os.path.basename(path)], ["video"]))


def video_frame(path, at):
    """The frame `at` seconds into a clip, as uint8 RGB.

    Seek, then decode forward: a seek lands on the keyframe at or before the
    time asked for, so the frames between it and the mark still have to be run
    through. Best effort on both — a container that will not seek is decoded from
    the top, and a mark past the end takes the last frame there is.
    """
    import av

    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if at > 0 and stream.time_base:
            try:
                container.seek(int(at / stream.time_base), stream=stream)
            except Exception:  # noqa: BLE001 — an unseekable container decodes from zero
                container.seek(0)
        last = None
        for frame in container.decode(stream):
            last = frame
            if frame.time is not None and frame.time >= at:
                break
        if last is None:
            raise BenchError(f"{os.path.basename(path)} has no decodable frame")
        return last.to_ndarray(format="rgb24")


def source_frame(path, at=0.0, long_edge=PREVIEW_LONG_EDGE):
    """One frame off whatever this file is, cut to preview size."""
    frame = video_frame(path, at) if is_video(path) else open_image(path)
    return fit(frame, long_edge) if long_edge else frame


def png(frame):
    """-> (PNG bytes, `(width, height)`). The wire format of every preview here."""
    import io

    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, "PNG", optimize=False, compress_level=1)
    return buffer.getvalue(), (frame.shape[1], frame.shape[0])


# ---- writing the result -----------------------------------------------------


def free_name(directory, stem, extension):
    """A name in `directory` nothing is using yet.

    Counted rather than stamped: a bench is a place you try the same clip at four
    settings, and `clip-edges-2.png` says which attempt this was where a
    timestamp says only when.
    """
    os.makedirs(directory, exist_ok=True)
    name = f"{stem}{extension}"
    index = 2
    while os.path.exists(os.path.join(directory, name)):
        name = f"{stem}-{index}{extension}"
        index += 1
    return name


def stem(path, op, trim=None, at=None):
    """What the written file is called before the counter is put on it.

    `at` wins over `trim` because they describe different files: a span is the
    stretch a clip was worked over, and a mark is the single frame cut out of
    it. A still named for the span it came out of would say it was six seconds
    long.
    """
    base = os.path.splitext(os.path.basename(path))[0]
    # Room for the counter and the extension inside the 255 bytes most file
    # systems allow, without truncating the part that says what the file is.
    base = base[:90]
    parts = [base, op]
    if at is not None:
        parts.append(f"{at:.1f}s".replace(".", "-"))
    elif trim:
        parts.append(f"{trim[0]:.0f}-{trim[1]:.0f}s")
    return "-".join(parts)


def write_still(frame, out_dir, name_stem):
    """One finished frame, written as a PNG. -> the name it got."""
    name = free_name(out_dir, name_stem, ".png")
    Image.fromarray(frame).save(os.path.join(out_dir, name), "PNG")
    return name


def even(size):
    """H.264 in 4:2:0 cannot encode an odd dimension."""
    return size - (size % 2)


def _fade(count):
    """Descending weights for the previous chunk across an overlap of `count`.

    The next chunk gets `1 - w`. It is the curve core's own SeedVR2 chunk merge
    uses — flat shoulders, a raised cosine over the middle third — rather than a
    straight ramp, because a linear crossfade over a few frames reads as a dip
    in detail at the join where this reads as nothing at all.
    """
    import math

    if count <= 1:
        return [1.0]
    weights = []
    for index in range(count):
        ramp = min(1.0, max(0.0, (index / (count - 1) - 1 / 3) / (1 / 3)))
        weights.append(0.5 + 0.5 * math.cos(math.pi * ramp))
    return weights


def _expected(stream, rate, span):
    """How many frames the bar is counting towards, or None if nothing says.

    A cut has a length and the arithmetic is obvious. A whole clip does not, and
    for a long time that meant no bar at all on the commonest press there is —
    which is survivable while a frame is a millisecond of arithmetic and is not
    once every frame is a model pass. So the container is asked: the frame count
    where it was written down, and the duration where it was not. Both are
    hints, which is why the fraction is capped at 0.99 below rather than trusted
    to arrive at 1.
    """
    if span:
        return max(1, round(float(rate) * span))
    if stream.frames:
        return int(stream.frames)
    if stream.duration and stream.time_base:
        return max(1, round(float(rate) * float(stream.duration * stream.time_base)))
    return None


def transcode(path, out_dir, name_stem, work, size=None, trim=None, chunk=1,
              overlap=0, keep_sound=False, on_progress=None, every=8):
    """Decode the chosen span, put the frames through `work`, encode them again.

    Streamed rather than loaded: a minute of 1080p is four gigabytes as an array
    and about nothing as a sequence of frames, and there is no stage in this that
    needs two frames at once.

    `work` takes a list of `chunk` frames and returns a list of the same length.
    One at a time is the ordinary case and the tracing bench's; more than one is
    for work that reads across frames, and `overlap` is how many frames the next
    chunk repeats and blends over so the joins do not show.

    `size` is `(width, height) -> (width, height)` over the source's *display*
    dimensions, and None means unchanged. It is asked once, before anything is
    decoded, because an encoder is opened with a size and cannot be told a new
    one halfway through — so an operator whose output size depends on the frame
    rather than on the dial is one this cannot carry.

    The sound, where it is kept, goes through an `AudioFifo` for the reason
    `mux.py` carries samples between parts: AAC's frame size is fixed, and
    libavcodec refuses a short frame anywhere but the end of the stream. The
    fifo is the same deal in a library the decode already had open.
    """
    import av

    crf = settings.video_crf()
    start, end = trim if trim else (0.0, None)
    name = free_name(out_dir, name_stem, ".mp4")
    target = os.path.join(out_dir, name)

    try:
        with av.open(path) as source:
            stream = source.streams.video[0]
            stream.thread_type = "AUTO"
            audio_in = next(iter(source.streams.audio), None) if keep_sound else None
            # `guessed_rate` is the frame interval the container actually steps at;
            # `average_rate` is frames over duration, which on variable-rate footage
            # (every phone clip) is neither. Only the hint the encoder is opened with.
            rate = stream.guessed_rate or stream.average_rate or 24
            # The display size, not the storage size: a rotated phone clip stores
            # landscape and plays portrait, and the result has to match the play.
            width, height = int(stream.width), int(stream.height)
            if int(getattr(stream, "rotation", 0) or 0) % 180:
                width, height = height, width
            if size is not None:
                width, height = size(width, height)
            width, height = even(width), even(height)
            if width < 2 or height < 2:
                raise BenchError(f"{os.path.basename(path)} is too small to work on")
            span = (end - start) if end is not None else None
            expected = _expected(stream, rate, span)

            with av.open(target, "w") as out:
                video = out.add_stream("libx264", rate=rate)
                video.width, video.height = width, height
                video.pix_fmt = "yuv420p"
                video.options = {"crf": str(crf), "preset": "medium"}
                # The source's own tick, not one over the frame rate, and the frames
                # keep their own timestamps against it — because the result has to
                # line up with the footage frame for frame. Counting frames out at a
                # constant rate stretched every variable-rate clip: 112 frames of a
                # two-second cut, written at the average rate the container reports,
                # came out as a three-second file playing slow.
                tick = stream.time_base or Fraction(1, 90000)
                video.codec_context.time_base = tick
                audio_out = None
                fifo = None
                resampler = None
                if audio_in is not None:
                    audio_out = out.add_stream("aac", rate=audio_in.rate)
                    audio_out.layout = "stereo" if audio_in.channels >= 2 else "mono"
                    fifo = av.AudioFifo()
                    resampler = av.audio.resampler.AudioResampler(
                        format="fltp", layout=audio_out.layout, rate=audio_in.rate)

                if start > 0 and stream.time_base:
                    try:
                        source.seek(int(start / stream.time_base), stream=stream)
                    except Exception:  # noqa: BLE001
                        source.seek(0)

                written = 0
                zero = None
                # The frames waiting to go through `work` — each with the timestamp
                # it came in on, because what is written has to line up with the
                # footage frame for frame — and the tail of the last chunk's answer,
                # held back to be crossfaded into the next one's.
                waiting = []
                held = []
                fade = _fade(overlap) if overlap else []

                def emit(pts, done):
                    nonlocal written
                    if done.shape[1] != width or done.shape[0] != height:
                        done = np.asarray(
                            Image.fromarray(done).resize((width, height), Image.LANCZOS))
                    picture = av.VideoFrame.from_ndarray(done, format="rgb24")
                    picture.pts = pts - zero
                    picture.time_base = tick
                    out.mux(video.encode(picture))
                    written += 1
                    if on_progress and expected and written % every == 0:
                        on_progress(min(0.99, written / expected))

                def run_chunk(last):
                    """Put what is waiting through `work` and write what is settled.

                    Settled means "no later chunk will touch it again": with an
                    overlap, the final `overlap` frames are re-done by the next
                    chunk and only written once the two have been blended, so
                    nothing is written twice and nothing is written early.
                    """
                    nonlocal waiting, held
                    answer = work([picture for _, picture in waiting])
                    if len(answer) != len(waiting):
                        raise BenchError("the work gave back a different number of frames")
                    for index, weight in enumerate(fade[:len(held)]):
                        answer[index] = (held[index].astype(np.float32) * weight
                                         + answer[index].astype(np.float32) * (1 - weight)
                                         ).round().clip(0, 255).astype(np.uint8)
                    keep = 0 if last else min(overlap, len(answer) - 1)
                    for (pts, _), done in zip(waiting[:len(answer) - keep], answer):
                        emit(pts, done)
                    held = answer[len(answer) - keep:] if keep else []
                    waiting = waiting[len(waiting) - keep:] if keep else []

                streams = [stream] + ([audio_in] if audio_in is not None else [])
                for frame in source.decode(*streams):
                    when = frame.time
                    if when is None:
                        continue
                    if when < start:
                        continue
                    if end is not None and when >= end:
                        # Video and audio do not run out together, so this only stops
                        # the stream that has passed the mark.
                        if isinstance(frame, av.VideoFrame):
                            break
                        continue
                    if isinstance(frame, av.VideoFrame):
                        if frame.pts is None:
                            continue
                        if zero is None:
                            zero = frame.pts
                        waiting.append((frame.pts, frame.to_ndarray(format="rgb24")))
                        if len(waiting) >= max(1, chunk):
                            run_chunk(last=False)
                    elif audio_out is not None:
                        for block in resampler.resample(frame):
                            block.pts = None
                            fifo.write(block)
                            # Not `chunk`: that is this function's frames-per-work
                            # parameter, and a walrus here rebound it to an audio
                            # frame and then to None, so the next video frame hit
                            # `max(1, None)`. Every upscale of a clip with sound
                            # died there — `keep_sound` defaults to true on that
                            # bench — after the model had already run.
                            while (piece := fifo.read(audio_out.frame_size)) is not None:
                                out.mux(audio_out.encode(piece))

                # Whatever the last full chunk did not cover, including the frames
                # held back for a crossfade that now has nothing to fade into.
                if waiting:
                    run_chunk(last=True)

                if audio_out is not None:
                    leftover = fifo.read()
                    if leftover is not None:
                        out.mux(audio_out.encode(leftover))
                    out.mux(audio_out.encode(None))
                out.mux(video.encode(None))
    except BaseException:
        # A run that dies partway has already created the file, and
        # `free_name` counts up — so a bench pressed three times left three
        # unplayable mp4s on the shelf beside the renders. Broad on purpose:
        # an interrupt is as much a half-written file as an error is.
        if os.path.exists(target):
            os.remove(target)
        raise

    if not written:
        os.remove(target)
        raise BenchError("that cut has no frames in it")
    return name
