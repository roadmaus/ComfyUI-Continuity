"""What `mux.write` actually puts in the file.

The reel replaced a `torch.cat`, and a concatenation is self-evidently in order
while a container written part by part is not: the frames and the samples are
handed to two encoders with timestamps this module computes, and getting those
wrong produces a file that plays rather than an exception. So this writes real
reels and reads the mp4 back with the same decoder ComfyUI uses.

Needs `av` and `torch` — the ComfyUI venv:

    <comfy-venv>/bin/python3 tests/test_mux.py

Skips itself with a message if they are not importable.
"""

import importlib.util
import os
from fractions import Fraction
import sys

import layout
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    """`mux.py` and the `spill.py` it reads its parts back through.

    Neither imports ComfyUI — writing a container needs av, torch and numpy and
    no more than that — so they are loaded into a stand-in package rather than
    through `__init__`, which would drag in the nodes and with them a whole
    install. The one thing `spill` does want from ComfyUI is where to put its
    files, and that is `directory()`, which the harness answers below.
    """
    import types

    package = types.ModuleType("mmcmux")
    package.__path__ = [layout.PY_ROOT]
    sys.modules["mmcmux"] = package
    loaded = []
    for name in ("spill", "mux"):
        spec = importlib.util.spec_from_file_location(
            f"mmcmux.{name}", layout.py(name))
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"mmcmux.{name}"] = module
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded


try:
    import av
    import torch

    spill, mux = _load()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: needs av and torch ({type(exc).__name__}: {exc})")
    sys.exit(0)

# Where the spills go. ComfyUI's temp in a real run; a directory of our own
# here, which is also what proves `directory()` is the only thing in `spill`
# that knows about ComfyUI at all.
SPILLS = tempfile.mkdtemp(prefix="mmc-spill-")
spill.directory = lambda: SPILLS

from harness import FAILURES, check, passed
FPS = 24
RATE = 48000
WIDTH, HEIGHT = 64, 48


def close(label, got, want, slack):
    if abs(got - want) > slack:
        FAILURES.append(f"{label}: got {got!r}, want {want!r} +/- {slack}")


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


def part(frames, seconds=None, level=0.5, size=(WIDTH, HEIGHT), rate=RATE, channels=2):
    """One reel entry: a pass, decoded and spilled. `seconds=None` means silent.

    Written through `spill.write` rather than assembled as a dict, because the
    format is the contract between the two modules and a hand-built spec would
    only test this file's opinion of it.

    The picture is a flat grey at `level`, which is what makes a decoded frame
    identifiable: the parts are told apart by their brightness on the way back
    out, so "did part 2's frames land where part 2 belongs" is answerable.
    """
    width, height = size
    images = torch.full((frames, height, width, 3), float(level))
    audio = None
    if seconds is not None:
        samples = int(round(seconds * rate))
        audio = {"waveform": torch.zeros(1, channels, samples), "sample_rate": rate}
    return {"pass": spill.write(images, audio, FPS)}


def written(parts, crf=23):
    """Write a reel to a temp file and read back (frames, levels, samples)."""
    path = os.path.join(tempfile.mkdtemp(), "reel.mp4")
    mux.write(path, parts, fps=FPS, crf=crf)
    frames, levels, samples = 0, [], 0
    with av.open(path) as container:
        for frame in container.decode(video=0):
            frames += 1
            levels.append(round(float(frame.to_ndarray(format="rgb24")[0, 0, 0]) / 255, 1))
        if container.streams.audio:
            container.seek(0)
            for frame in container.decode(audio=0):
                samples += frame.samples
    return frames, levels, samples, path


# ---- one part, which is what a Creator render is ----------------------------

frames, levels, samples, path = written([part(12, seconds=0.5)])
check("a lone part writes its own frames", frames, 12)
check("...at one brightness", set(levels), {0.5})
# AAC pads and delays; what matters is that the sound is the picture's length
# rather than the 0.5 s it was handed. 12 frames at 24 fps is 0.5 s exactly, so
# this one is also the case where nothing had to be fitted.
close("...with sound the length of the picture", samples, int(0.5 * RATE), 2048)

# ---- several parts, which is what a strip is --------------------------------

frames, levels, samples, _ = written(
    [part(10, seconds=10 / FPS, level=0.2),
     part(5, seconds=5 / FPS, level=0.8)])
check("the parts' frames are all there", frames, 15)
check("...in play order", levels, [0.2] * 10 + [0.8] * 5)
close("...and the sound runs the whole reel", samples, int(15 / FPS * RATE), 2048)

# The claim `_fit` exists for. A part whose sound falls short of its own picture
# does not lose that time — laid end to end, it *shifts* everything after it,
# and the drift accumulates down the reel. Here part 1 is handed a third of the
# sound its picture needs; the reel must still come out the full length.
frames, levels, samples, _ = written(
    [part(24, seconds=1 / 3, level=0.2), part(24, seconds=1.0, level=0.8)])
check("a part with short sound keeps its frames", frames, 48)
close("...and is padded rather than letting the next part slide",
      samples, int(2 * RATE), 2048)

# The other direction: sound that overruns its picture is cut, not carried into
# the part after it.
frames, _, samples, _ = written(
    [part(24, seconds=3.0, level=0.2), part(24, seconds=1.0, level=0.8)])
check("a part with long sound keeps its frames", frames, 48)
close("...and is cut to its own picture", samples, int(2 * RATE), 2048)

# A silent part in a reel that has sound — what a supplied clip with no
# soundtrack will be. Silence of its own length, so the parts after it are
# still where they belong.
frames, levels, samples, _ = written(
    [part(12, seconds=0.5, level=0.2), part(12, seconds=None, level=0.8),
     part(12, seconds=0.5, level=0.4)])
check("a silent part still plays", frames, 36)
check("...in its place", levels, [0.2] * 12 + [0.8] * 12 + [0.4] * 12)
close("...and holds its own time open", samples, int(1.5 * RATE), 2048)

# A reel with no sound anywhere writes no audio stream at all, rather than a
# stream of silence nobody asked for.
_, _, samples, silent_path = written([part(8, seconds=None), part(8, seconds=None)])
check("a reel with no sound has no audio stream", samples, 0)
with av.open(silent_path) as container:
    check("...and none in the container either", len(container.streams.audio), 0)

# ---- a supplied clip, spliced rather than decoded ---------------------------
#
# The point of the file part is that the footage never becomes a tensor, so
# what has to be checked is the conforming: a source at another frame rate,
# another size and another sample rate has to come out on the reel's grid, in
# the right place, and the right length. The source below is deliberately wrong
# on all four axes.

SRC_FPS = 30
SRC_W, SRC_H = 96, 96          # square, against a 64x48 reel: cover-cropped
SRC_RATE = 44100


def source_clip(seconds=2.0, sound=True, fps=SRC_FPS, size=(SRC_W, SRC_H)):
    """A real file on disk to splice — flat white, so it is told from the parts."""
    width, height = size
    path = os.path.join(tempfile.mkdtemp(), "source.mp4")
    with av.open(path, mode="w") as out:
        video = out.add_stream("h264", rate=fps)
        video.width, video.height, video.pix_fmt = width, height, "yuv420p"
        sound_stream = None
        if sound:
            sound_stream = out.add_stream("aac", rate=SRC_RATE, layout="stereo")
        total = int(seconds * fps)
        for index in range(total):
            array = torch.full((height, width, 3), 1.0)
            array = (array * 255).byte().numpy()
            frame = av.VideoFrame.from_ndarray(array, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, fps)
            out.mux(video.encode(frame.reformat(format="yuv420p")))
        out.mux(video.encode(None))
        if sound_stream is not None:
            block = torch.zeros(2, int(seconds * SRC_RATE)).numpy()
            frame = av.AudioFrame.from_ndarray(block, format="fltp", layout="stereo")
            frame.sample_rate = SRC_RATE
            frame.pts = 0
            out.mux(sound_stream.encode(frame))
            out.mux(sound_stream.encode(None))
    return path


def clip_part(path, start=0.0, duration=0.0, sound=True, size=(WIDTH, HEIGHT)):
    return {"clip": {"path": path, "start": start, "duration": duration,
                     "width": size[0], "height": size[1],
                     "sound": sound, "rate": RATE, "channels": 2}}


src = source_clip(seconds=2.0)
frames, levels, samples, _ = written([clip_part(src)])
# 2 s of 30 fps source on a 24 fps reel is 48 frames, not 60: the reel is one
# constant-rate stream and a source handed over at its own rate would play slow.
check("a spliced clip lands on the reel's frame rate", frames, 48)
check("...and is all there at one brightness", set(levels), {1.0})
close("...with its sound resampled to the reel's rate", samples, int(2.0 * RATE), 2048)

# The window. A clip is cut at the source's own timeline and only that stretch
# is demuxed — the rest is never decoded, which is the whole point.
frames, _, samples, _ = written([clip_part(src, start=0.5, duration=1.0)])
close("a trimmed clip contributes only its window", frames, 24, 1)
close("...and its sound is cut to match", samples, int(1.0 * RATE), 2400)

# Spliced between two generated passes: the frames land in play order and
# nothing after the clip slides, which is the property the whole reel rests on.
frames, levels, samples, _ = written(
    [part(12, seconds=0.5, level=0.2), clip_part(src, duration=1.0),
     part(12, seconds=0.5, level=0.4)])
check("a clip between two passes keeps play order",
      (levels[:12], set(levels[12:-12]), levels[-12:]),
      ([0.2] * 12, {1.0}, [0.4] * 12))
close("...and the reel is as long as its parts", frames, 12 + 24 + 12, 1)
close("...with the sound running the whole of it",
      samples, int((12 + 24 + 12) / FPS * RATE), 2400)

# A clip whose sound is switched off, and a clip whose container has none at
# all: both hold their own time open with silence rather than pulling the parts
# after them forward.
silent_src = source_clip(seconds=1.0, sound=False)
frames, levels, _, _ = written(
    [clip_part(src, duration=1.0, sound=False), part(12, seconds=0.5, level=0.4)])
check("a muted clip still plays its picture", frames, 24 + 12)
frames, _, samples, _ = written([clip_part(silent_src), part(12, seconds=0.5)])
check("a clip with no soundtrack still plays", frames, 24 + 12)
close("...and holds its own time open", samples, int(36 / FPS * RATE), 2400)

# Cover, not letterbox. The source is square and the reel is 4:3, so a fitted
# clip would have bars — flat black at the edges against a flat white source.
_, _, _, covered = written([clip_part(src, duration=0.5)])
with av.open(covered) as container:
    edge = next(container.decode(video=0)).to_ndarray(format="rgb24")
if int(edge[edge.shape[0] // 2, 0, 0]) < 128:
    FAILURES.append("a spliced clip is letterboxed: the left edge came back black")

# A phone clip: stored landscape, with a display matrix saying "turn me". The
# reel carries no such matrix — it is one constant stream of pixels — so the
# turn has to be made of the pixels, the way the player makes it. Read
# counter-clockwise: -90 is the common phone case, and it puts the bright
# top-left corner of the storage picture at the top right of a portrait frame.
def turned_clip(rotation):
    path = os.path.join(tempfile.mkdtemp(), "phone.mp4")
    with av.open(path, mode="w") as out:
        video = out.add_stream("h264", rate=SRC_FPS)
        video.width, video.height, video.pix_fmt = 64, 32, "yuv420p"
        video.options = {"crf": "1"}
        video.set_display_rotation(rotation)
        pic = torch.zeros(32, 64, 3)
        pic[:16, :32] = 1.0
        for index in range(SRC_FPS):
            frame = av.VideoFrame.from_ndarray((pic * 255).byte().numpy(), format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, SRC_FPS)
            out.mux(video.encode(frame.reformat(format="yuv420p")))
        out.mux(video.encode(None))
    return path


def bright_corner(path):
    with av.open(path) as container:
        frame = next(container.decode(video=0))
        a = frame.to_ndarray(format="rgb24").astype("float32")
    h, w = a.shape[:2]
    quarters = [a[:h // 2, :w // 2].mean(), a[:h // 2, w // 2:].mean(),
                a[h // 2:, :w // 2].mean(), a[h // 2:, w // 2:].mean()]
    return ["TL", "TR", "BL", "BR"][max(range(4), key=lambda i: quarters[i])], (w, h)


_, _, _, upright = written([clip_part(turned_clip(-90), sound=False, size=(32, 64))])
check("a phone clip is spliced the way its player shows it", bright_corner(upright), ("TR", (32, 64)))
_, _, _, flat = written([clip_part(turned_clip(0), sound=False, size=(64, 32))])
check("an unturned clip is spliced as stored", bright_corner(flat), ("TL", (64, 32)))

# ---- what it refuses --------------------------------------------------------
#
# These were the pairwise join's checks and they say the same thing they always
# did: the timeline pins one canvas across every pass, so parts that disagree
# mean something upstream resized one of them. The error names the part, because
# on a long strip "the parts do not match" is not a place to look.

expect_error("parts of different sizes are refused, by number",
             lambda: mux.reel_geometry([part(4), part(4, size=(32, 24))]),
             "part 2")
expect_error("...saying both sizes",
             lambda: mux.reel_geometry([part(4), part(4, size=(32, 24))]),
             "32x24")
expect_error("an empty reel is refused",
             lambda: mux.reel_geometry([]), "reel is empty")
expect_error("parts at different sample rates are refused",
             lambda: written([part(4, seconds=0.1), part(4, seconds=0.1, rate=44100)]),
             "part 2")
expect_error("parts with different channel counts are refused",
             lambda: written([part(4, seconds=0.1), part(4, seconds=0.1, channels=1)]),
             "part 2")
expect_error("a layout with no name is refused rather than guessed at",
             lambda: written([part(4, seconds=0.1, channels=3)]),
             "3-channel")

# ---- the frames the audio encoder is actually handed ------------------------
#
# AAC's frame size is fixed at 1024 samples and libavcodec refuses anything else
# anywhere but the end of the stream — a bare EINVAL out of
# `avcodec_send_frame()`, four frames deep in PyAV, naming nothing. A part's
# sound is cut to the length of its own picture, so a part landing on a frame
# boundary is the exception rather than the rule: 11 frames at 24 fps is 22000
# samples, which is 21 frames and a remainder of 496.
#
# Read through `_encode_sound` rather than off the file, because what is wrong
# in the failing case is *what the encoder is handed*, and by the time it is a
# container the evidence is gone — some builds and some PyAV versions buffer the
# short frame for you, which is exactly why this went unnoticed until an install
# whose PyAV does not.
handed = []
_encode = mux._encode_sound
mux._encode_sound = lambda av_, target, block, at: (
    handed.append((int(block.shape[-1]), int(at))), _encode(av_, target, block, at))[1]
try:
    written([part(11, seconds=11 / FPS), part(7, seconds=7 / FPS)])
finally:
    mux._encode_sound = _encode

check("every audio frame but the last is the encoder's own size",
      sorted({count for count, _ in handed[:-1]}), [1024])
check("...including across the join between two parts",
      len(handed) > 1 and handed[-1][0] < 1024, True)
check("...and they run from zero without a gap or an overlap",
      [at for _, at in handed],
      [sum(count for count, _ in handed[:index]) for index in range(len(handed))])


# ---- the quality setting reaches the encoder --------------------------------
#
# The old save node had to refuse a CRF on ComfyUI older than 0.29, because
# core's writer only learned the argument there. Writing the container here, it
# is always honoured — and the check that it *is* is that the same reel comes
# out a different size at a different CRF.
noisy = [{"pass": spill.write(torch.rand(24, HEIGHT, WIDTH, 3), None, FPS)}]
small = os.path.getsize(written(noisy, crf=40)[3])
large = os.path.getsize(written(noisy, crf=8)[3])
if not small < large:
    FAILURES.append(f"crf changes nothing: crf 40 wrote {small} bytes, crf 8 wrote {large}")

# --- the lane over supplied footage ------------------------------------------
#
# A cue over a clip is mixed by the writer from the cue's own file, at the frame
# the lane put it — the clip's reel node hands the blocks over as `mix` (issue
# #47: they used to be dropped between the compiler and here). Read back by
# the loudness of each half second: silence, the cue, silence.


def tone_file(seconds=1.0, hz=440):
    path = os.path.join(tempfile.mkdtemp(), "cue.wav")
    with av.open(path, mode="w") as out:
        stream = out.add_stream("pcm_s16le", rate=SRC_RATE, layout="stereo")
        t = torch.arange(int(seconds * SRC_RATE)) / SRC_RATE
        wave = (0.5 * torch.sin(2 * torch.pi * hz * t) * 32767).to(torch.int16)
        frame = av.AudioFrame.from_ndarray(wave.repeat(2, 1).contiguous().numpy(),
                                           format="s16p", layout="stereo")
        frame.sample_rate = SRC_RATE
        frame.pts = 0
        out.mux(stream.encode(frame))
        out.mux(stream.encode(None))
    return path


def loudness(path, step_s=0.5):
    """RMS of the written reel's sound per `step_s`, in play order."""
    with av.open(path) as container:
        blocks = [torch.from_numpy(f.to_ndarray()) for f in container.decode(audio=0)]
    wave = torch.cat(blocks, dim=-1)[0].float()
    if wave.abs().max() > 1.5:          # integer samples
        wave = wave / 32768.0
    size = int(step_s * RATE)
    return [round(float(wave[i:i + size].pow(2).mean().sqrt()), 3)
            for i in range(0, wave.shape[-1] - size + 1, size)]


cue = tone_file(seconds=1.0)
mixed = clip_part(src, duration=2.0, sound=False)
mixed["clip"]["mix"] = [{"path": cue, "at": 12, "frames": 24, "in_s": 0.0, "seconds": 1.0}]
frames, _, samples, path = written([mixed])
check("a cue over a muted clip keeps the clip's frames", frames, 48)
loud = loudness(path)
check("...and is heard where the lane put it, and nowhere else",
      [level > 0.1 for level in loud[:4]], [False, True, True, False])

# Two seconds of picture whose sound begins a second in, as a container may
# carry it. The writer used to lay the sound at the window's start and pad the
# missing second onto the end — the tone a second early (issue #47).
late = os.path.join(tempfile.mkdtemp(), "late.mkv")
with av.open(late, mode="w") as out:
    video = out.add_stream("h264", rate=SRC_FPS)
    video.width, video.height, video.pix_fmt = SRC_W, SRC_H, "yuv420p"
    sound_stream = out.add_stream("pcm_s16le", rate=SRC_RATE, layout="stereo")
    for index in range(int(2.0 * SRC_FPS)):
        frame = av.VideoFrame.from_ndarray(torch.full((SRC_H, SRC_W, 3), 255, dtype=torch.uint8).numpy(),
                                           format="rgb24")
        frame.pts = index
        frame.time_base = Fraction(1, SRC_FPS)
        out.mux(video.encode(frame.reformat(format="yuv420p")))
    out.mux(video.encode(None))
    t = torch.arange(SRC_RATE) / SRC_RATE
    wave = (0.5 * torch.sin(2 * torch.pi * 440 * t) * 32767).to(torch.int16)
    frame = av.AudioFrame.from_ndarray(wave.repeat(2, 1).contiguous().numpy(),
                                       format="s16p", layout="stereo")
    frame.sample_rate = SRC_RATE
    frame.pts = SRC_RATE          # one second in, in the stream's own ticks
    frame.time_base = Fraction(1, SRC_RATE)
    out.mux(sound_stream.encode(frame))
    out.mux(sound_stream.encode(None))
frames, _, _, path = written([clip_part(late, duration=2.0)])
check("a clip whose sound starts late keeps its frames", frames, 48)
check("...and the sound stays where the file had it",
      [level > 0.1 for level in loudness(path)[:4]], [False, False, True, True])

passed("all mux tests passed — reels written and read back")
