"""The finished piece, written part by part into one mp4.

A render is several generations played end to end, and until now they were
*concatenated* to become one: `MiniMaxH3TimelineJoin` folded the passes
pairwise and the save node was handed the single tensor that came out. That
fold is the most expensive thing in a long timeline, and not by a little.

Every intermediate of a pairwise fold is a node output, and ComfyUI keeps node
outputs for the whole execution — so the running totals all stay alive at once.
A 768p frame is 12.4 MB of float32 and a 124-frame pass is 1.5 GB, which makes
ten passes about 81 GB of intermediates on top of the 15 GB of passes. It is
O(N^2) in the length of the piece. Worse, the default cache
(`RAMPressureCache`) evicts current-generation entries over 512 MB when memory
runs short, and re-running an evicted join means re-running what fed it, which
upstream of a join is a KSampler.

Nothing about a video file needs that. An mp4 is written frame by frame, so the
parts only ever have to be *reachable in order* — never adjacent in memory, and
never all at once. So the passes are collected into a reel (`MiniMaxH3Reel`, a
list of parts that copies nothing) and this module walks it, encoding each part
into one open container. No concatenation buffer, and no pass resident either:
each one was written to disk as it decoded and is read back a frame at a time.

Ours rather than core's `VideoFromComponents.save_to`, which this is otherwise
a close copy of: that one takes a single tensor, so using it would mean
building the very thing this exists to avoid. Writing the container here also
retires the CRF version gate — `save_to` only learned `crf` in ComfyUI 0.29 and
the save node had to refuse a quality setting it could not honour on anything
older. This one always can.

Every part is a file, and neither kind is ever held whole.

A **generated pass** was decoded, trimmed and written out by `spill.py`, and
comes through as 8-bit frames on disk that this module memmaps and hands to the
encoder one at a time. That is what stops a pass from having to stay in memory
from its own decode until the save node runs — a minute of 768p video is 18 GB
of float32, and the passes all overlap in time because the file is written from
all of them at the end.

A **supplied clip** is a file the user brought, and is never decoded at all. At
12.4 MB a frame, materialising two minutes of someone's mp4 so the encoder has
something to re-encode would cost 35 GB to say nothing; it is demuxed,
conformed and re-encoded a frame at a time into the same streams instead, so a
five-minute clip costs what a five-second one does. What the *seams* need out
of either kind — a first frame, a last feathered run — is a separate bounded
read; for a clip it goes through the same `conform` the splice does, so the
frame a generation continues from is the frame the file plays before it.

The audio is written part by part too, and each part's soundtrack is held to
its own picture's length. That is not tidiness: the parts are laid end to end,
so a part whose sound runs short by 30 ms does not lose 30 ms, it shifts
everything after it by 30 ms and the drift accumulates down the reel. Sound is
padded with silence or cut to fit, and only ever by the rounding between a
frame count and a sample count.
"""

import json
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import torch

from . import spill

# The layouts PyAV names, by channel count. Anything else is refused rather
# than guessed at: picking a layout decides which speaker each channel goes to.
_LAYOUTS = {1: "mono", 2: "stereo", 6: "5.1"}

# How much sound is handed to the encoder at once. Long enough that the call
# overhead is nothing, short enough that a ten-minute soundtrack is never
# converted to a numpy array in one piece.
_AUDIO_CHUNK_S = 1.0


class MuxError(ValueError):
    """The parts of a reel cannot be written as one file."""


def decode_sample_rate(vae):
    """The rate an audio VAE's decoder outputs at.

    Same two attributes core reads in `VAEDecodeAudio`, in the same order —
    the H3 audio VAE is a 48 kHz Oobleck today, but which rate a checkpoint
    decodes at is a property of the weights and not a number to hard-code.
    """
    return int(getattr(vae, "audio_sample_rate_output",
                       getattr(vae, "audio_sample_rate", 44100)))


def decode_channels(vae):
    """How many channels that decoder produces. Stereo unless it says otherwise."""
    return int(getattr(vae, "output_channels", 2))


def is_clip(part):
    """Whether a reel part is footage to splice rather than a pass to play back.

    Supplied footage arrives as a path and a window and is re-encoded straight
    into the container — see `_write_clip`. A generated pass arrives as
    `spill.py`'s 8-bit frames, which are already in the encoder's own currency
    and only have to be read in order — see `_write_pass`.
    """
    return "clip" in part


def _geometry(part):
    if is_clip(part):
        # A clip is scaled to the canvas on the way in, so what it will be is
        # what the graph told it to be — there is nothing decoded yet to measure.
        return int(part["clip"]["width"]), int(part["clip"]["height"])
    return int(part["pass"]["width"]), int(part["pass"]["height"])


def reel_geometry(parts):
    """(width, height) of a reel, refusing one whose parts disagree.

    The timeline pins one canvas across every pass precisely so this cannot
    happen — this is the check the pairwise join used to make, kept because it
    is the one that says something went wrong upstream rather than that the
    encoder is unhappy.
    """
    if not parts:
        raise MuxError("nothing to save: the reel is empty")
    width, height = _geometry(parts[0])
    for index, part in enumerate(parts[1:], start=2):
        other_w, other_h = _geometry(part)
        if (other_w, other_h) != (width, height):
            raise MuxError(
                f"part {index} is {other_w}x{other_h} and part 1 is "
                f"{width}x{height} — the parts of one render have to match"
            )
    return width, height


def _audio_format(parts):
    """(sample_rate, channels) for the reel, refusing parts that disagree.

    Read off the reel rather than assumed: the rate is the audio VAE's output
    rate, which is a fact about the weights on this disk and not a constant
    this package gets to pick.
    """
    rate = channels = None
    for index, part in enumerate(parts, start=1):
        if is_clip(part):
            # A clip's own rate and layout are the file's, and it is resampled
            # to the reel's on the way in — so what it declares here is the
            # target the graph gave it, read off the audio VAE. A clip playing
            # silent declares nothing and takes the reel's.
            if not (part["clip"].get("sound") or part["clip"].get("mix")) \
                    or part["clip"].get("rate") is None:
                continue
            part_rate = int(part["clip"]["rate"])
            part_channels = int(part["clip"]["channels"])
        elif "audio_path" in part["pass"]:
            part_rate = int(part["pass"]["rate"])
            part_channels = int(part["pass"]["channels"])
        else:
            continue
        if rate is None:
            rate, channels = part_rate, part_channels
        elif (part_rate, part_channels) != (rate, channels):
            raise MuxError(
                f"part {index} has {part_channels} channels at {part_rate} Hz "
                f"and the reel is {channels} at {rate} — the parts of one "
                f"render have to match"
            )
    if rate is not None and channels not in _LAYOUTS:
        raise MuxError(f"cannot write {channels}-channel audio")
    return rate, channels


def _fit(waveform, samples):
    """One part's sound, held to exactly the length of its own picture.

    Cut when it overruns, padded with silence when it falls short. Both are
    rounding between a frame count and a sample count — a generated part's two
    halves are the same span by construction — and the alternative is not
    "faithful", it is every later part sliding by the difference.
    """
    have = waveform.shape[-1]
    if have > samples:
        return waveform[..., :samples]
    if have < samples:
        pad = torch.zeros(waveform.shape[:-1] + (samples - have,), dtype=waveform.dtype)
        return torch.cat([waveform, pad], dim=-1)
    return waveform


@dataclass(frozen=True)
class _Target:
    """The open container and streams a part is written into."""

    output: object
    video: object
    audio: object                 # None when the reel has no sound at all
    pix_fmt: str
    frame_rate: Fraction
    video_time_base: Fraction
    rate: int | None
    channels: int | None
    layout: str | None
    audio_time_base: Fraction | None
    # What the audio encoder will accept in one frame, or 0 for a codec that
    # takes any length. AAC's is 1024 and it is not a suggestion — see
    # `_mux_sound`. Knowable only once the encoder is open, which is why
    # `write` opens it rather than letting the first frame do it.
    audio_frame_size: int = 0
    # The samples left over when a part does not end on a frame boundary, held
    # as `[(at, waveform)]` so the next part continues them rather than sending
    # a short frame of its own. A list because `_Target` is frozen and this is
    # the one thing in it that changes as the reel is written.
    pending: list = field(default_factory=list)


def _encode_sound(av, target, block, at):
    """One frame of sound at sample `at`, encoded and muxed."""
    sound = av.AudioFrame.from_ndarray(
        np.ascontiguousarray(block.contiguous().numpy()),
        format="fltp", layout=target.layout)
    sound.sample_rate = target.rate
    sound.pts = at
    sound.time_base = target.audio_time_base
    target.output.mux(target.audio.encode(sound))


def _mux_sound(av, target, waveform, at):
    """Write one part's fitted waveform, starting at sample `at`.

    In the frames the encoder asks for, and **carried across part boundaries**:
    AAC's frame size is fixed, and libavcodec refuses a short frame anywhere but
    the end of the stream with a bare EINVAL out of `avcodec_send_frame()`. A
    part whose sample count is not a multiple of 1024 — which is most of them,
    since a part's sound is cut to the length of its own picture — would send
    one every time. What is left over rides in `target.pending` and goes out at
    the head of the next part's first frame; `_flush_sound` writes the last of
    it, where a short frame is the one thing that is allowed.

    A codec that takes any length (`audio_frame_size` 0) keeps the one-second
    chunking this had before, which is nothing to do with correctness and
    everything to do with not converting a ten-minute soundtrack in one piece.
    """
    if target.pending:
        held_at, held = target.pending.pop()
        waveform = torch.cat([held, waveform], dim=-1)
        at = held_at
    size = target.audio_frame_size or max(1, int(_AUDIO_CHUNK_S * target.rate))
    total = waveform.shape[-1]
    # Only whole frames while the stream is still open. Without a fixed frame
    # size every part is whole by definition and this is the old loop exactly.
    whole = (total // size) * size if target.audio_frame_size else total
    for start in range(0, whole, size):
        _encode_sound(av, target, waveform[..., start:start + size], at + start)
    if whole < total:
        target.pending.append((at + whole, waveform[..., whole:].contiguous()))


def _flush_sound(av, target):
    """The samples the last part ended on, as the one short frame that is legal."""
    if target.pending:
        at, waveform = target.pending.pop()
        _encode_sound(av, target, waveform, at)


def _write_pass(av, target, spec, at_frame, at_sample):
    """A generated pass, read back off disk. -> (frames, samples).

    The frames come through a memmap and are already the 8-bit RGB the encoder
    wants, so a frame is paged in, encoded and dropped — the pass is never
    resident, whatever its length. `spill.py` owns the format; this end only
    reads it.
    """
    data = spill.open_frames(spec)
    count = int(spec["frames"])
    for index in range(count):
        frame = av.VideoFrame.from_ndarray(
            np.ascontiguousarray(data[index]), format="rgb24")
        frame = frame.reformat(format=target.pix_fmt)
        frame.pts = at_frame + index
        frame.time_base = target.video_time_base
        target.output.mux(target.video.encode(frame))
    del data

    if target.audio is None:
        return count, 0
    # The part's own sound, held to the part's own picture — see `_fit`. A part
    # with no soundtrack at all in a reel that has one is silence of exactly its
    # own length, which is the only thing that keeps the parts after it where
    # they belong.
    wanted = int(round(count / float(target.frame_rate) * target.rate))
    if "audio_path" in spec:
        # Copied off the map rather than aliased: `_fit` may pad it, and the
        # chunks handed to the encoder outlive this line. Sound is three orders
        # of magnitude smaller than the picture it goes with.
        waveform = torch.from_numpy(np.array(
            np.memmap(spec["audio_path"], dtype=np.float32, mode="r",
                      shape=(int(spec["channels"]), int(spec["samples"])))))
    else:
        waveform = torch.zeros(target.channels, 0)
    _mux_sound(av, target, _fit(waveform, wanted), at_sample)
    return count, wanted


def _clip_graph(av, stream, frame, frame_rate, width=None, height=None):
    """The filter chain a supplied clip is conformed through.

    Four things, and ffmpeg does all four properly so this does not:

    - `fps` resamples the source's rate to the render's, duplicating or
      dropping frames **by timestamp**. The reel is one constant-rate stream,
      so a 30 fps source cannot simply be handed over — it would play 25% slow
      — and a variable-rate source (a phone, a screen recording) has no rate to
      hand over at all: its frames are wherever their timestamps say they are,
      and only a filter that reads them lands each one where it belongs.
    - `transpose` turns a phone clip the way its player does. A portrait
      phone recording is stored landscape with a rotation in the container,
      and a decoder hands back the storage picture; the display matrix rides
      on the frame as `rotation`, counter-clockwise degrees, and this is the
      turn ffmpeg's own autorotate makes of it. Before the scale, so the
      cover-crop is of the picture as seen.
    - `scale` with `increase` fills the canvas rather than fitting inside it,
      and `crop` takes the middle of what overflows. Cover, not letterbox: the
      generated passes have no bars and a supplied clip with them would read as
      a different piece rather than as a different shot. Which half of the
      overflow to keep is a real editorial choice and the middle is the only
      defensible default. Skipped when no canvas is given — a reader that
      wants the source's own size goes through the resample alone.
    - `setsar` makes the output square-pixel. Anamorphic sources are scaled by
      their storage size here, which is wrong by their pixel aspect; it is rare
      enough to be worth naming rather than carrying a DAR calculation.

    `fps` comes first so the scaler only ever touches frames that survive,
    and the turn comes next so the scaler is fitting the picture as seen.

    Returns the graph along with its two ends, and the caller has to hold it:
    the filter contexts do not own it, so a graph nothing references is
    collected out from under the push that follows and the process dies rather
    than raising.
    """
    graph = av.filter.Graph()
    source = graph.add_buffer(width=frame.width, height=frame.height,
                              format=frame.format.name,
                              time_base=stream.time_base)
    steps = [("fps", f"fps={frame_rate}"), *_upright(frame.rotation)]
    if width and height:
        steps += [("scale", f"{width}:{height}:force_original_aspect_ratio=increase"),
                  ("crop", f"{width}:{height}")]
    steps.append(("setsar", "1"))
    tail = source
    for name, args in steps:
        step = graph.add(name, args)
        tail.link_to(step)
        tail = step
    sink = graph.add("buffersink")
    tail.link_to(sink)
    graph.configure()
    return graph, source, sink


def _upright(rotation):
    """The filter steps that turn a decoded frame the way its player shows it.

    `rotation` is the frame's, in counter-clockwise degrees as PyAV reads the
    container's display matrix; ffmpeg's autorotate resolves the same number
    to the same transposes, checked against it on all three turns.
    """
    turns = int(round(float(rotation or 0) / 90.0)) % 4
    if turns == 1:
        return [("transpose", "cclock")]
    if turns == 2:
        return [("hflip", ""), ("vflip", "")]
    if turns == 3:
        return [("transpose", "clock")]
    return []


def _file_end(av, container, stream):
    """Where the picture stops, in seconds, or None where the file does not say."""
    if stream.duration is not None and stream.time_base:
        return float(stream.duration * stream.time_base)
    if container.duration is not None:
        return float(container.duration) / av.time_base
    return None


def conform(av, path, start, duration, frame_rate, width=None, height=None):
    """The frames of `path`'s `start`..`start + duration` window, at `frame_rate`.

    A generator of decoded `av.VideoFrame`s, conformed through `_clip_graph`,
    and **the one reading of a supplied clip there is**. The reel splices the
    clip through it, and so does the seam beside the clip when it reads the
    frames a generation continues from — so the run handed to the sampler is,
    by construction, the run the finished file plays right before the cut.
    Two readers with two ideas of where a frame falls would agree on constant-
    rate footage and disagree on variable-rate footage, and a seam that
    continued from a frame the reel never showed was the result.

    `duration` of 0 reads to the end of the file. The frames come out upright
    — a portrait phone clip is portrait here — see `_upright`. They are yielded as
    they leave the filter, one at a time, so a caller that only wants the last
    second of a long clip holds a second and not the clip. Raises `ValueError`
    when the container has no picture; the callers name the clip themselves.
    """
    with av.open(path) as container:
        if not container.streams.video:
            raise ValueError(f"{path!r} has no video stream")
        stream = container.streams.video[0]
        first_pts = start / stream.time_base
        end = (start + duration) / stream.time_base if duration else None
        if start:
            container.seek(int(first_pts), stream=stream)
        chain = source = sink = None
        # How many frames the window is, or None to read to the end of the file.
        # The count is the window's, not the footage's: a frame shown across the
        # window's end is held to it, and the filter stops at it. Without both,
        # a source that holds a frame for seconds — a screen recording with
        # nothing moving, the sparse fixture in issue #47 — came out short of
        # the seconds the strip was told it plays, and the seam beside it read
        # too few frames and refused the blend.
        want = int(round(duration * float(frame_rate))) if duration else None
        # ...bounded by the file: a window that runs past the footage is held
        # to the footage's end, and one that starts past it holds nothing —
        # `media.clip_frames` says "past the end of the clip" for that, and a
        # frame held there would be an answer to a question nobody asked.
        ends = _file_end(av, container, stream)
        if ends is not None and start >= ends:
            return
        made = 0
        last = None
        # Where the last frame captured in the window was, so the hold after the
        # flush can be bounded by the footage: the later of the file's stated
        # end and that frame plus its period, since a container's duration is
        # often the last frame's timestamp with nothing said about how long it
        # showed.
        seen = None

        def drain():
            while True:
                try:
                    yield sink.pull()
                except (av.error.BlockingIOError, av.error.EOFError):
                    return

        def graph_for(frame):
            # `chain` is held for as long as its two ends are used — see
            # `_clip_graph`.
            return _clip_graph(av, stream, frame, frame_rate, width, height)

        # The frame still showing when the window opens. A seek lands on the
        # keyframe at or before the start, and every frame from there up to the
        # start used to be dropped — including the one whose display interval
        # the start falls inside. On constant-rate footage that costs nothing
        # visible; on variable-rate footage it is the frame the player shows at
        # that instant, and the window opened on the *next* one, however far off
        # it was. It is pushed first, re-stamped to the window's start, so the
        # fps filter counts from where the window opens rather than from where
        # the frame was captured.
        showing = None
        for frame in container.decode(stream):
            if frame.pts is not None:
                if frame.pts < first_pts:
                    showing = frame
                    continue
                if end is not None and frame.pts >= end:
                    break
                seen = float(frame.pts * stream.time_base)
            if source is None:
                chain, source, sink = graph_for(showing if showing is not None else frame)
                if showing is not None and frame.pts is not None and frame.pts > first_pts:
                    showing.pts = int(first_pts)
                    source.push(showing)
                showing = None
            source.push(frame)
            for out in drain():
                yield out
                last = out
                made += 1
                if want is not None and made >= want:
                    del chain
                    return
        if source is None and showing is not None:
            # The whole window sits inside one frame's hold: nothing was
            # captured after it opened. That frame is the picture.
            chain, source, sink = graph_for(showing)
            showing.pts = int(first_pts)
            source.push(showing)
            for out in drain():
                yield out
                last = out
                made += 1
                if want is not None and made >= want:
                    del chain
                    return
        if source is not None:
            # The fps filter holds a frame back to decide its duration; without
            # the flush a clip is short by one every time.
            source.push(None)
            for out in drain():
                yield out
                last = out
                made += 1
                if want is not None and made >= want:
                    break
        # The window runs past the last frame captured in it: the last frame is
        # what the player keeps showing, so it is what the reel plays — up to
        # where the footage itself stops, and no further.
        if want is not None and made < want and last is not None:
            stops = ends
            if seen is not None:
                stops = max(stops or 0.0, seen + 1.0 / float(frame_rate))
            if stops is not None:
                want = min(want, int(round((stops - start) * float(frame_rate))))
            while made < want:
                yield last
                made += 1
        del chain


def _write_clip(av, target, spec, at_frame, at_sample):
    """Supplied footage, spliced in without ever being decoded into the reel.

    Two passes over the container: the picture, which is what decides how long
    this part is, and then the sound, capped to the length the picture came out
    at. Two passes rather than one interleaved loop because the cap is not
    known until the frames are counted, and the alternative — holding the
    soundtrack in memory until it is — is the thing this is avoiding, in
    miniature. The second pass demuxes only the audio stream, so it costs a
    read of the file and no video decode at all.
    """
    width, height = int(spec["width"]), int(spec["height"])
    start, duration = float(spec.get("start") or 0.0), float(spec.get("duration") or 0.0)
    path = spec["path"]

    count = 0
    try:
        for out in conform(av, path, start, duration, target.frame_rate, width, height):
            out = out.reformat(format=target.pix_fmt)
            out.pts = at_frame + count
            out.time_base = target.video_time_base
            target.output.mux(target.video.encode(out))
            count += 1
    except ValueError as exc:
        raise MuxError(f"{spec.get('name') or path!r} has no video to play") from exc

    if not count:
        raise MuxError(
            f"{spec.get('name') or path!r} has no frames in the "
            f"{start:.2f}–{start + duration:.2f} s segment asked for"
        )
    if target.audio is None:
        return count, 0

    wanted = int(round(count / float(target.frame_rate) * target.rate))
    waveform = _clip_sound(av, path, spec, start, duration, target) \
        if spec.get("sound") else torch.zeros(target.channels, 0)
    waveform = _fit(waveform, wanted)
    if spec.get("mix"):
        waveform = _mixed(av, waveform, spec["mix"], target)
    _mux_sound(av, target, waveform, at_sample)
    return count, wanted


def _mixed(av, waveform, blocks, target):
    """The lane's cues over a clip, laid onto its soundtrack. -> a new waveform.

    Each block is a window of a file at a frame on the clip's own clock — the
    shape `compile._stamp_sound` writes for a pass, resolved by the clip's reel
    node — and is read the way the clip's own sound is, through the same
    resampler to the reel's rate and layout. Summed rather than substituted:
    the lane's tooltip says *mixed*, the clip's dialogue stays under the cue,
    and a muted clip is silence under it either way. Clamped after, since two
    full-scale tracks add to more than the encoder takes.
    """
    out = waveform.clone()
    length = out.shape[-1]
    for block in blocks:
        at = int(round(float(block["at"]) / float(target.frame_rate) * target.rate))
        room = length - at
        if room < 1:
            continue
        cue = _clip_sound(av, block["path"], block, float(block.get("in_s") or 0.0),
                          float(block.get("seconds") or 0.0), target)
        cue = cue[..., :room]
        if cue.shape[-1]:
            out[..., at:at + cue.shape[-1]] += cue.to(out.dtype)
    return out.clamp_(-1.0, 1.0)


def _clip_sound(av, path, spec, start, duration, target):
    """A supplied clip's soundtrack, at the reel's rate and layout.

    Resampled by ffmpeg rather than by hand: the rate conversion, the format
    and — where a source is mono or 5.1 — the channel mix are all things it has
    correct matrices for and we would be inventing. A clip whose container
    carries no sound at all comes back empty and is padded to its own length by
    `_fit`, which is what a silent shot is.
    """
    with av.open(path) as container:
        stream = next(iter(container.streams.audio), None)
        if stream is None:
            return torch.zeros(target.channels, 0)
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout=target.layout, rate=target.rate)
        end = start + duration if duration else None
        if start:
            container.seek(int(start / stream.time_base), stream=stream)
        blocks = []
        # A seek lands on a packet boundary, which is at or *before* the window
        # — so the first frame kept usually begins early. How early is what
        # gets dropped off the front, and dropping it is what keeps the sound
        # in step with a picture that was cut at the frame.
        began = None
        for frame in container.decode(stream):
            if frame.time is not None:
                if frame.time + frame.samples / float(frame.sample_rate or 1) <= start:
                    continue
                if end is not None and frame.time >= end:
                    break
                if began is None:
                    began = frame.time
            for out in resampler.resample(frame):
                blocks.append(torch.from_numpy(out.to_ndarray()))
        for out in resampler.resample(None):
            blocks.append(torch.from_numpy(out.to_ndarray()))
    if not blocks:
        return torch.zeros(target.channels, 0)
    waveform = torch.cat(blocks, dim=-1)
    # ...and the other way round: sound that begins *after* the window opens
    # — a track whose first packet sits a second in — used to be laid at the
    # window's start, a second early, with the missing second padded onto the
    # end by `_fit`. Its place is where it was in the file (issue #47).
    offset = (began if began is not None else start) - start
    if offset < 0:
        early = int(round(-offset * target.rate))
        return waveform[..., early:] if early else waveform
    late = int(round(offset * target.rate))
    if late:
        waveform = torch.cat(
            [torch.zeros(waveform.shape[:-1] + (late,), dtype=waveform.dtype), waveform],
            dim=-1)
    return waveform


def write(path, parts, fps, crf, metadata=None):
    """Write a reel to `path` as one H.264/AAC mp4. -> (width, height).

    `parts` is the reel: `[{"pass": spill spec} | {"clip": clip spec}, ...]` in
    play order. One container, one video stream and one audio stream, opened
    once and fed part by part — the encoder is never flushed between parts, so
    what comes out is one continuous stream rather than files stitched together.
    """
    import av

    width, height = reel_geometry(parts)
    rate, channels = _audio_format(parts)
    frame_rate = Fraction(round(float(fps)))
    video_time_base = Fraction(1, frame_rate.numerator)
    pix_fmt = "yuv420p"

    # Same flags core writes: metadata tags survive, and faststart puts the
    # index at the front so the stage can play the file as it downloads.
    with av.open(path, mode="w", options={"movflags": "use_metadata_tags+faststart"}) as output:
        # Before any stream, like core's savers — the workflow rides in the
        # container so a render dropped back on the canvas rebuilds its node.
        for key, value in (metadata or {}).items():
            output.metadata[key] = value if isinstance(value, str) else json.dumps(value)

        video = output.add_stream("h264", rate=frame_rate)
        video.width, video.height, video.pix_fmt = width, height, pix_fmt
        video.options = {"crf": str(int(crf))}
        video.codec_context.time_base = video_time_base

        audio = None
        audio_frame_size = 0
        if rate is not None:
            layout = _LAYOUTS[channels]
            audio = output.add_stream("aac", rate=rate, layout=layout)
            audio_time_base = Fraction(1, rate)
            # Opened here rather than left to the first frame, because how many
            # samples this encoder takes at once is only knowable once it is —
            # and on a fixed-frame-size codec that number is a hard requirement
            # rather than a preference. See `_mux_sound`.
            audio.codec_context.open()
            audio_frame_size = int(getattr(audio.codec_context, "frame_size", 0) or 0)

        written_frames = 0
        written_samples = 0
        # Everything a part needs in order to be written into the streams that
        # are already open. Gathered here rather than passed as eight
        # arguments, because the two kinds of part want exactly the same set.
        target = _Target(output, video, audio, pix_fmt, frame_rate,
                         video_time_base, rate, channels,
                         _LAYOUTS[channels] if channels else None,
                         Fraction(1, rate) if rate else None,
                         audio_frame_size)

        for part in parts:
            if is_clip(part):
                frames, samples = _write_clip(av, target, part["clip"],
                                              written_frames, written_samples)
            else:
                frames, samples = _write_pass(av, target, part["pass"],
                                              written_frames, written_samples)
            written_frames += frames
            written_samples += samples

        # Flushed once, at the end of the reel rather than at the end of each
        # part: a flush closes out the encoder's lookahead, and doing it per
        # part would put a keyframe and a GOP boundary at every join.
        output.mux(video.encode(None))
        if audio is not None:
            # The tail the last part did not fill a frame with, before the
            # encoder is closed out — the end of the stream is the one place a
            # short frame is legal, and dropping it would lose up to a frame's
            # worth of the final part's sound.
            _flush_sound(av, target)
            output.mux(audio.encode(None))

    return width, height
