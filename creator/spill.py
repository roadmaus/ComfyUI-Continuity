"""A decoded pass, on disk instead of in memory.

A render is several generations played end to end, and the file is written from
all of them at the end. So every pass has to survive from its own decode until
the save node runs — and a pass is *big*. A 768p frame is 12.4 MB of float32 and
a ten-second pass is 3 GB, so a minute of finished video is 18 GB of tensors
held alive at once, on top of whatever the weights are costing. On a box where
the model is streamed from host RAM — 40 GB of it, staged — that is the
difference between a render and the OOM killer.

The passes do not have to be in memory. They have to be *readable in order* when
the muxer asks, and read one frame at a time at that. So a pass is decoded,
trimmed, and written straight out to a file here; what travels the reel is this
module's spec, and `mux.py` streams the frames back off the disk as it encodes
them. Peak memory becomes the largest single pass rather than the sum of all of
them, and it stops growing with the length of the piece.

**uint8, because that is what the encoder is given anyway.** `mux` writes
`(frame * 255).byte()`, so storing 8-bit RGB costs the file nothing it would not
already have lost, and is a quarter of the size of the float32 the decoder
returned. The seam frames a later pass inherits come back through the same 8-bit
door — which is exactly the fidelity a keyframe attached from a PNG has always
had, and the VAE encoder is unbothered by it either way. The sound is kept as
the float32 it decoded to: it is three orders of magnitude smaller and it is the
one thing a re-encode would audibly cost.

**Under ComfyUI's temp directory**, which core wipes on startup and on exit, so
a crashed render leaves nothing behind for the next one to find. `directory()`
is the one place that decides where, because it is the thing to change when
these files should outlive the process — a spill that survives a restart is a
pass that never has to be sampled twice, and that is a feature built on top of
this one rather than a property of it.

Nothing here imports torch at module level and nothing here knows about
ComfyUI's node API: this is the file format and the two ways of reading it.
"""

import json
import os
import time
import uuid

import numpy as np

# The subdirectory spills live in, under whatever `directory()` resolves to.
# Named rather than derived so that a stray file in temp is identifiable as
# ours by looking at it.
DIR_NAME = "minimax_passes"

# How long a spill nobody has read is kept before the next render deletes it.
# Counted from the last read rather than from the write — see `_touch` — because
# the reel holds paths and a re-queue replays them, so a file that vanishes
# under a live cache entry is a broken re-queue. Core wipes the whole directory
# on restart in any case; this is only for a server left up for days.
KEEP_SECONDS = 12 * 60 * 60

# How much of a pass is converted to bytes at a time on the way out. Big enough
# that the write is not one syscall per frame, small enough that the temporary
# is nothing next to the pass itself: 32 frames of 768p is 75 MB.
CHUNK_FRAMES = 32


class SpillError(RuntimeError):
    """A pass could not be written to or read back from disk."""


def directory():
    """Where spills live. Created on demand.

    ComfyUI's temp, which is wiped on startup and on exit — see the module
    docstring for why that is the right place today and the one thing to change
    when it stops being.
    """
    import folder_paths

    path = os.path.join(folder_paths.get_temp_directory(), DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def prune(now=None):
    """Delete spills nothing has read in `KEEP_SECONDS`. -> how many bytes went.

    Called when a pass is written rather than when one is finished with: the
    reel that names a file is itself a cached node output, and a re-queue that
    changes only the save node's quality replays those parts without
    re-decoding them. Deleting at save time would break exactly that, and
    deleting by write time would break the same thing on a slower clock — so
    every read pushes the file's stamp forward and only what is genuinely out
    of play ages out.
    """
    now = time.time() if now is None else now
    freed = 0
    try:
        entries = os.scandir(directory())
    except OSError:
        return 0
    with entries:
        for entry in entries:
            try:
                if not entry.is_file() or now - entry.stat().st_mtime <= KEEP_SECONDS:
                    continue
                size = entry.stat().st_size
                os.remove(entry.path)
                freed += size
            except OSError:
                # A spill another process is mid-write on, or one already gone.
                # Neither is this render's business to insist on.
                continue
    return freed


def _paths(name):
    root = directory()
    return (os.path.join(root, f"{name}.frames"),
            os.path.join(root, f"{name}.audio"),
            os.path.join(root, f"{name}.json"))


def _touch(spec):
    """Mark a spill as still in play, so `prune` leaves it alone.

    Read from every read, because a reel is a cached node output and a re-queue
    replays its parts without re-decoding them: what makes a spill safe to
    delete is not its age but that nothing has come back for it. Anything this
    machine has actually written out in the keep window stays.
    """
    for path in (spec.get("frames_path"), spec.get("audio_path")):
        try:
            if path:
                os.utime(path, None)
        except OSError:
            pass


def write(images, audio, fps, name=None):
    """A decoded pass -> the spec that names it on the reel.

    `images` is the IMAGE batch the video decoder produced and `audio` the AUDIO
    dict the audio decoder produced, or None. The frames are converted a chunk
    at a time so that the 8-bit copy is never the size of the pass, and the
    tensors are the caller's to drop the moment this returns — which is the
    whole point of the exercise.

    The sidecar `.json` says nothing the returned spec does not; it is there so
    a spill on disk can be identified without the graph that made it.
    """
    if images is None or images.shape[0] == 0:
        raise SpillError("a pass with no frames cannot be written")

    name = name or uuid.uuid4().hex
    frames_path, audio_path, meta_path = _paths(name)
    count, height, width = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])

    try:
        with open(frames_path, "wb") as handle:
            for start in range(0, count, CHUNK_FRAMES):
                block = images[start:start + CHUNK_FRAMES]
                handle.write(
                    (block * 255).clamp(0, 255).byte().cpu().numpy().tobytes())
    except OSError as exc:
        raise SpillError(f"could not write this pass to {frames_path}: {exc}") from exc

    spec = {"frames_path": frames_path, "frames": count,
            "width": width, "height": height, "fps": float(fps)}

    if audio is not None and audio["waveform"].shape[-1]:
        waveform = audio["waveform"][0].float().cpu().contiguous().numpy()
        try:
            with open(audio_path, "wb") as handle:
                handle.write(np.ascontiguousarray(waveform, dtype=np.float32).tobytes())
        except OSError as exc:
            raise SpillError(f"could not write this pass's sound to {audio_path}: {exc}") from exc
        spec.update(audio_path=audio_path, channels=int(waveform.shape[0]),
                    samples=int(waveform.shape[1]), rate=int(audio["sample_rate"]))

    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(spec, handle, sort_keys=True)
    prune()
    return spec


def rewrite(spec, blocks, name=None, geometry=None):
    """The same pass with new pictures: -> a spec for the rewritten one.

    `blocks` yields IMAGE batches in play order, together as long as the source
    — a caller that repairs a pass a chunk at a time, so the rewritten pass is
    never held whole any more than the original was. What comes back is the
    source spec with a new frames file under it.

    `geometry` is `(width, height)` for a pass that comes back at a *different*
    size — the re-detail pass, which re-renders a finished pass at twice the
    canvas. Absent means the size it already was, which is every repair that
    works in place. Either way the blocks are measured rather than trusted: the
    spec is what `open_frames` shapes its memmap from, so a spec that disagrees
    with the bytes on disk is a pass that reads back as garbage rather than as
    an error.

    **The sound is not rewritten, and not copied either: the new spec points at
    the same file.** A pass that has been repaired in the picture has the
    soundtrack it already had — the one the user heard when they decided the
    picture needed work — and re-deriving it would be a re-roll of something
    nobody asked to change. Two specs naming one audio file is safe: spills are
    deleted by age, never by whoever is finished with them.
    """
    width, height = geometry or (int(spec["width"]), int(spec["height"]))
    frames_path, _, meta_path = _paths(name or uuid.uuid4().hex)
    written = 0
    try:
        with open(frames_path, "wb") as handle:
            for block in blocks:
                shape = (int(block.shape[2]), int(block.shape[1]))
                if shape != (width, height):
                    raise SpillError(
                        f"a rewritten pass has to be the size its spec says: "
                        f"{shape[0]}x{shape[1]} written where the spec says "
                        f"{width}x{height}")
                handle.write((block * 255).clamp(0, 255).byte().cpu().numpy().tobytes())
                written += int(block.shape[0])
    except OSError as exc:
        raise SpillError(f"could not write this pass to {frames_path}: {exc}") from exc

    if written != int(spec["frames"]):
        raise SpillError(
            f"a rewritten pass has to be as long as the one it replaces: "
            f"{written} frames written over {spec['frames']}")

    out = {**spec, "frames_path": frames_path, "frames": written,
           "width": width, "height": height}
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, sort_keys=True)
    prune()
    return out


def open_frames(spec):
    """The pass's frames as a read-only memmap, shaped (N, H, W, 3) uint8.

    A memmap rather than a read: the muxer walks it one frame at a time and the
    kernel pages in what it touches, so writing a ten-minute reel never has more
    than the encoder's own window of it resident.
    """
    path = spec["frames_path"]
    shape = (int(spec["frames"]), int(spec["height"]), int(spec["width"]), 3)
    _touch(spec)
    try:
        return np.memmap(path, dtype=np.uint8, mode="r", shape=shape)
    except OSError as exc:
        raise SpillError(
            f"this render's pass is no longer on disk at {path}. Passes are "
            f"written to ComfyUI's temp directory, which core empties when it "
            f"restarts and which drops anything nothing has read for "
            f"{KEEP_SECONDS // 3600} hours. Change something on the timeline, or "
            f"restart, and render it again — an unchanged re-queue would replay "
            f"the same missing file."
        ) from exc


def frames(spec, count, at="tail"):
    """`count` frames off one end of a pass, as an IMAGE batch.

    What a seam inherits. Read back through the same memmap the muxer uses, so
    a one-frame seam off a ten-second pass costs one frame — the pass itself is
    never materialised to take a slice of it.
    """
    import torch

    count = max(1, int(count))
    have = int(spec["frames"])
    if have < count:
        # Padding or repeating would pin motion that never happened; the seam's
        # width has to come down instead.
        raise SpillError(
            f"the source pass has {have} frames and this seam inherits {count} — "
            f"shorten the blend or lengthen the source")
    data = open_frames(spec)
    window = data[:count] if at == "head" else data[have - count:]
    # `np.array` rather than a view of the memmap: the caller keeps this for the
    # length of a generation, and a tensor aliasing a mapped file is a tensor
    # whose contents depend on the file still being there. It is the seam's
    # width — a frame, or at most 39 — so the copy is nothing.
    return torch.from_numpy(np.array(window)).float().div_(255.0)


def sound_between(spec, start_seconds, end_seconds):
    """The soundtrack under one stretch of a pass, as an AUDIO dict.

    What `sound` does at the ends, said about the middle: the face pass
    re-generates a window of frames and has to hand the model the sound that
    plays under exactly those frames, or the mouth it draws is answering
    somebody else's syllable. Clamped to what the pass has rather than padded —
    the window is derived from the frame count, so anything outside it is
    rounding at the last sample.
    """
    import torch

    if "audio_path" not in spec:
        raise SpillError("that pass decoded no sound")
    rate, channels = int(spec["rate"]), int(spec["channels"])
    have = int(spec["samples"])
    start = max(0, min(have, int(round(float(start_seconds) * rate))))
    end = max(start + 1, min(have, int(round(float(end_seconds) * rate))))
    _touch(spec)
    try:
        data = np.memmap(spec["audio_path"], dtype=np.float32, mode="r",
                         shape=(channels, have))
    except OSError as exc:
        raise SpillError(
            f"this render's sound is no longer on disk at {spec['audio_path']} — "
            f"see the frames it went with. Queue the render again.") from exc
    window = np.array(data[:, start:end])            # copied — see `frames`
    return {"waveform": torch.from_numpy(window).unsqueeze(0), "sample_rate": rate}


def sound(spec, seconds, at="tail"):
    """`seconds` of a pass's soundtrack off one end, as an AUDIO dict."""
    import torch

    if "audio_path" not in spec:
        raise SpillError("no sound to continue from: that pass decoded none")
    rate, channels = int(spec["rate"]), int(spec["channels"])
    have = int(spec["samples"])
    # A pass shorter than the tail hands over everything it has rather than
    # being padded: silence we invented is not what came before.
    wanted = min(have, max(1, int(round(float(seconds) * rate))))
    offset = 0 if at == "head" else have - wanted
    _touch(spec)
    try:
        data = np.memmap(spec["audio_path"], dtype=np.float32, mode="r",
                         shape=(channels, have))
    except OSError as exc:
        raise SpillError(
            f"this render's sound is no longer on disk at {spec['audio_path']} — "
            f"see the frames it went with. Queue the render again.") from exc
    window = np.array(data[:, offset:offset + wanted])   # copied — see `frames`
    return {"waveform": torch.from_numpy(window).unsqueeze(0), "sample_rate": rate}
