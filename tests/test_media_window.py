"""That a reference clip is decoded through a window rather than in full.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_media_window.py

`media.load_video` hands its trim and its length cap to PyAV as a seek window,
so the frames outside it are never decoded. That is worth a real file rather than
a mock: the saving depends on the container seek landing before the window, on
the frames ahead of it being discarded, on ffmpeg's `fps` filter putting the
resampled frames where the timestamps say, and on the soundtrack being cut to
the same span. Most of that is not our code, and all of it is what the speed-up
rests on.

The assertions avoid absolute colour entirely — a synthetic clip goes through
yuv420p and comes back through swscale, so the levels shift. Instead each second
of the clip is a different flat grey and the window is checked *against the full
decode of the same file*: frame 0 of a clip trimmed to 2 s must be the frame the
untrimmed decode has at 2 s. That holds whatever the colour pipeline does to it.

Skips itself with a message if ComfyUI or PyAV cannot be imported.
"""

import importlib.util
import os
import sys

import layout
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A stock install is one tree and `--base-directory` defaults to it. Point
# COMFYUI_PATH at the ComfyUI that actually runs, and set COMFYUI_BASE as well
# if the base directory is somewhere else (a Desktop install: it usually is).
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)

SECONDS = 10
SRC_FPS = 30
SIZE = 64
AUDIO_RATE = 16000


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import folder_paths  # noqa: F401  (proves the install is usable)


try:
    import av
    import numpy as np

    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

# The pack's module loads *outside* the skip guard: the guard proves the
# environment, and a module of ours that will not import is a failure, not a
# machine allowed to bow out.
package = types.ModuleType("mmc")
package.__path__ = [layout.PY_ROOT]
sys.modules["mmc"] = package
_spec = importlib.util.spec_from_file_location("mmc.media", layout.py("media"))
media = importlib.util.module_from_spec(_spec)
sys.modules["mmc.media"] = media
_spec.loader.exec_module(media)

from harness import FAILURES, check, passed


def close(label, got, want, tol):
    if abs(got - want) > tol:
        FAILURES.append(f"{label}: got {got!r}, want {want!r} +/- {tol}")


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


def write_clip(path):
    """A 10 s 30 fps clip whose every second is a different flat grey, plus tone.

    Deliberately not 24 fps: the resample to H3's rate has to survive the window,
    and a clip that needed no resampling would not prove it.
    """
    container = av.open(path, mode="w")
    video = container.add_stream("libx264", rate=SRC_FPS)
    video.width, video.height = SIZE, SIZE
    video.pix_fmt = "yuv420p"
    audio = container.add_stream("aac", rate=AUDIO_RATE)
    audio.layout = "mono"

    for index in range(SECONDS * SRC_FPS):
        level = 20 + (index // SRC_FPS) * 20      # one flat grey per second
        plane = np.full((SIZE, SIZE, 3), level, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(plane, format="rgb24")
        container.mux(video.encode(frame))
    container.mux(video.encode(None))

    # AAC wants 1024 samples a frame. The tone itself is never inspected; only
    # how much of it comes back is.
    total = SECONDS * AUDIO_RATE
    time = np.arange(total, dtype=np.float32) / AUDIO_RATE
    tone = (0.2 * np.sin(2 * np.pi * 440.0 * time)).astype(np.float32)
    for start in range(0, total - 1024, 1024):
        chunk = tone[start:start + 1024].reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="mono")
        frame.sample_rate = AUDIO_RATE
        frame.pts = start
        frame.time_base = __import__("fractions").Fraction(1, AUDIO_RATE)
        container.mux(audio.encode(frame))
    container.mux(audio.encode(None))
    container.close()


SCRATCH = os.environ.get("TMPDIR", "/tmp")
CLIP = os.path.join(SCRATCH, "mmc_test_window.mp4")
write_clip(CLIP)

# `resolve` is the only thing between a filename and the disk, and this clip is
# not in ComfyUI/input — pointing it at the scratch file is the whole stub.
media.resolve = lambda filename: filename


def grey(frames, index):
    return float(frames[index].mean())


# --- the whole clip, as the baseline ------------------------------------------

full, _ = media.load_video(CLIP)
# 10 s resampled from 30 fps to 24: 240 frames, give or take the rounding at the
# end of the last second.
close("a whole clip is resampled to 24 fps", full.shape[0], SECONDS * media.TARGET_FPS, 2)

# --- trim becomes a seek window ----------------------------------------------

window, _ = media.load_video(CLIP, trim=(2.0, 4.0))
close("a 2 s trim yields 2 s of frames", window.shape[0], 2 * media.TARGET_FPS, 2)
# The load-bearing one: the window starts where it says it does. Not "roughly
# brighter" — the same frame the untrimmed decode has at the 2 s mark.
close("the window starts at 2 s", grey(window, 0), grey(full, 2 * media.TARGET_FPS), 0.02)
close("the window ends before 4 s", grey(window, -1),
      grey(full, 4 * media.TARGET_FPS - 1), 0.02)

# A window that starts late still starts in the right place, which is what says
# the container seek landed before it and the frames ahead of it were dropped.
late, _ = media.load_video(CLIP, trim=(7.0, 8.0))
close("a late window starts at 7 s", grey(late, 0), grey(full, 7 * media.TARGET_FPS), 0.02)

# --- the generation-length cap ------------------------------------------------

capped, _ = media.load_video(CLIP, max_seconds=1.0)
# One second plus the two frames of slack `_decode_window` adds, and never the
# other nine seconds: this is the case that used to decode the whole file.
if not media.TARGET_FPS <= capped.shape[0] <= media.TARGET_FPS + 4:
    FAILURES.append(f"a 1 s cap decodes about 1 s: got {capped.shape[0]} frames")
close("a capped decode still starts at 0 s", grey(capped, 0), grey(full, 0), 0.02)

# The cap and a trim compose: the window is the trim, bounded by the cap.
both, _ = media.load_video(CLIP, trim=(3.0, 9.0), max_seconds=1.0)
if not media.TARGET_FPS <= both.shape[0] <= media.TARGET_FPS + 4:
    FAILURES.append(f"a cap shortens a longer trim: got {both.shape[0]} frames")
close("a capped trim still starts at 3 s", grey(both, 0), grey(full, 3 * media.TARGET_FPS), 0.02)

# A cap longer than the clip is not a truncation.
close("a cap past the end changes nothing",
      media.load_video(CLIP, max_seconds=60.0)[0].shape[0], full.shape[0], 2)

# --- the soundtrack rides the same window -------------------------------------

_, whole_sound = media.load_video(CLIP, want_audio=True)
rate = int(whole_sound["sample_rate"])
close("the whole soundtrack comes back", whole_sound["waveform"].shape[-1] / rate, SECONDS, 0.2)

_, windowed = media.load_video(CLIP, want_audio=True, trim=(2.0, 4.0))
close("the soundtrack is cut to the trim",
      windowed["waveform"].shape[-1] / int(windowed["sample_rate"]), 2.0, 0.2)

# The change of behaviour worth pinning: a soundtrack used to be sent at its full
# length while its picture was cut to the generation, so one reference described
# two different spans. The cap now holds both to the same window.
_, short = media.load_video(CLIP, want_audio=True, max_seconds=1.0)
close("the soundtrack obeys the length cap",
      short["waveform"].shape[-1] / int(short["sample_rate"]), 1.0, 0.2)

# --- windows that ask for nothing ---------------------------------------------

expect_error("a trim past the end says so",
             lambda: media.load_video(CLIP, trim=(30.0, 32.0)),
             "past the end of the clip")

os.remove(CLIP)

passed("all decode-window tests passed")
