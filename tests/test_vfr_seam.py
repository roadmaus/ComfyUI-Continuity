"""That a seam beside a supplied clip continues from the frame the reel plays.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_vfr_seam.py

A supplied clip reaches the finished file through `mux._write_clip`, which
splices it through ffmpeg's `fps` filter by timestamp. The seam beside it used
to read its inherited frames through core's `VideoFromFile` and resample the
stack by the stream's *average* rate — fine on constant-rate footage, wrong on
variable-rate footage (phones, screen recordings), where an average says
nothing about where any one frame falls. Issue #46: the run handed to the
sampler was not the run the file played before the cut.

Both now read through `mux.conform`, and this pins it from the outside: a
constant-rate and a variable-rate clip, each frame its own flat grey, are read
through the seam's path and through a written reel, and the two must agree on
how many frames the window holds and on which frames sit at its ends. The
variable-rate clip also gets a tempo check at a point where the old average-
rate index picked a visibly different frame.

Skips itself with a message if ComfyUI or PyAV cannot be imported.
"""

import importlib.util
import os
import sys
import tempfile
import types
from fractions import Fraction

import layout

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)

SIZE = 64
FPS = 24


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import folder_paths  # noqa: F401


try:
    import av
    import numpy as np

    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

package = types.ModuleType("mmc")
package.__path__ = [layout.PY_ROOT]
sys.modules["mmc"] = package


def _load(name):
    spec = importlib.util.spec_from_file_location(f"mmc.{name}", layout.py(name))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmc.{name}"] = module
    spec.loader.exec_module(module)
    return module


media = _load("media")
mux = _load("mux")
guide = _load("guide")

from harness import FAILURES, check, passed

media.resolve = lambda filename: filename

SCRATCH = tempfile.mkdtemp()


def write_clip(name, stamps, tick):
    """A clip with one frame per (pts, grey level) in `stamps`, pts in `tick`s.

    The timestamps are written as given, so an irregular list makes a
    variable-rate file — which is the whole fixture: the container's average
    rate then describes none of the intervals in it.
    """
    path = os.path.join(SCRATCH, name)
    with av.open(path, mode="w") as out:
        video = out.add_stream("libx264", rate=FPS)
        video.width, video.height, video.pix_fmt = SIZE, SIZE, "yuv420p"
        video.codec_context.time_base = tick
        video.options = {"crf": "1"}
        for pts, level in stamps:
            plane = np.full((SIZE, SIZE, 3), level, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(plane, format="rgb24")
            frame.pts = pts
            frame.time_base = tick
            out.mux(video.encode(frame))
        out.mux(video.encode(None))
    return path


def reel_levels(path, start, duration):
    """The grey of every frame a reel made of this one clip plays."""
    out = os.path.join(SCRATCH, "reel.mp4")
    mux.write(out, [{"clip": {"path": path, "start": start, "duration": duration,
                               "width": SIZE, "height": SIZE, "sound": False}}],
              fps=FPS, crf=1)
    levels = []
    with av.open(out) as container:
        for frame in container.decode(video=0):
            levels.append(float(frame.to_ndarray(format="rgb24")[..., 0].mean()) / 255)
    return levels


def grey(frames, index):
    return float(frames[index].mean())


def close(label, got, want, tol):
    if abs(got - want) > tol:
        FAILURES.append(f"{label}: got {got!r}, want {want!r} +/- {tol}")


# Two encodes apart (the fixture's, then the reel's) at crf 1, flat frames come
# back within a level or so. Adjacent fixture frames are four or more apart.
TOL = 2.5 / 255


def agree(label, path, duration, seam):
    """The seam's reading of a window and the reel's must be one reading."""
    spec = {"filename": path, "start": 0.0, "duration": duration}
    reel = reel_levels(path, 0.0, duration)
    whole, _ = media.load_video(path, trim=(0.0, duration))
    check(f"{label}: the seam path and the reel hold the same frames",
          whole.shape[0], len(reel))

    tail = media.clip_frames(spec, seam, at="tail")
    check(f"{label}: a {seam}-frame tail is {seam} frames", tail.shape[0], seam)
    for offset in range(1, seam + 1):
        close(f"{label}: tail frame -{offset} is the reel's",
              grey(tail, -offset), reel[-offset], TOL)

    head = media.clip_frames(spec, 1, at="head")
    close(f"{label}: the head frame is the reel's first", grey(head, 0), reel[0], TOL)
    return reel


# --- constant rate: 30 fps, two seconds, 60 frames -----------------------------

cfr = write_clip("cfr.mp4", [(i, 16 + 4 * i) for i in range(60)], Fraction(1, 30))
reel = agree("CFR", cfr, 2.0, 22)
check("CFR: two seconds at 30 fps are 48 reel frames", len(reel), 48)

# --- variable rate: a dense second, then a sparse one --------------------------

# Twelve frames in the first second, four in the next: sixteen frames the
# container averages to eight a second, which is the interval of none of them.
TICK = Fraction(1, 1200)
dense = [(i * 100, 30 + 12 * i) for i in range(12)]
sparse = [(1200 + (i - 12) * 300, 30 + 12 * i) for i in range(12, 16)]
vfr = write_clip("vfr.mp4", dense + sparse, TICK)
reel = agree("VFR", vfr, 2.0, 22)

# The tempo. At 1.5 s the source shows its fifteenth frame (pts 1.5 s, level
# 198). Indexing sixteen frames uniformly over the window — the average-rate
# reading — lands on the thirteenth (level 174) instead.
AT_1_5 = int(1.5 * FPS)
close("VFR: the reel shows the 1.5 s frame at 1.5 s", reel[AT_1_5], 198 / 255, TOL)
window, _ = media.load_video(vfr, trim=(0.0, 2.0))
close("VFR: so does the seam path", grey(window, AT_1_5), 198 / 255, TOL)

# --- the guide reads by timestamp too -----------------------------------------

hint = guide.read(vfr, None, 48, SIZE, SIZE, FPS)
check("VFR: a 48-frame guide is 48 frames", hint.shape[0], 48)
close("VFR: the guide shows the 1.5 s frame at 1.5 s", grey(hint, AT_1_5), 198 / 255, TOL)
close("VFR: the guide starts on the first frame", grey(hint, 0), 30 / 255, TOL)

# --- a phone clip reaches the seam upright ------------------------------------

# Stored landscape with "turn me -90" in the container: portrait to its player,
# and the bright top-left corner of the storage picture at the top right.
turned = os.path.join(SCRATCH, "phone.mp4")
with av.open(turned, mode="w") as out:
    video = out.add_stream("libx264", rate=FPS)
    video.width, video.height, video.pix_fmt = 64, 32, "yuv420p"
    video.options = {"crf": "1"}
    video.set_display_rotation(-90)
    lopsided = np.zeros((32, 64, 3), np.uint8)
    lopsided[:16, :32] = 255
    for _ in range(FPS):
        out.mux(video.encode(av.VideoFrame.from_ndarray(lopsided, format="rgb24")))
    out.mux(video.encode(None))

check("the probe reports the size the player shows", media.image_size(turned), (32, 64))
tail = media.clip_frames({"filename": turned, "start": 0.0, "duration": 1.0}, 3, at="tail")
check("the seam's frames are portrait", tuple(tail.shape[1:3]), (64, 32))
quarters = [float(tail[-1, :32, :16].mean()), float(tail[-1, :32, 16:].mean()),
            float(tail[-1, 32:, :16].mean()), float(tail[-1, 32:, 16:].mean())]
check("...and turned the way the player turns them",
      ["TL", "TR", "BL", "BR"][quarters.index(max(quarters))], "TR")

# --- a guide trimmed to a cut holds the last frame *inside* the trim -------------

# Dark for a second, then bright. A guide trimmed to the dark second on a
# three-second shot must hold a dark frame, not the two frames of decoder slack
# past the cut (issue #47).
cut = write_clip("cut.mp4", [(n * 1000 // FPS, 20 if n < FPS else 220) for n in range(3 * FPS)],
                 Fraction(1, 1000))
held = guide.read(cut, (0.0, 1.0), 3 * FPS, SIZE, SIZE, FPS)
check("a guide trimmed to a cut is the shot's length", held.shape[0], 3 * FPS)
close("...opens dark", grey(held, 0), 20 / 255, TOL)
close("...is still dark on the trim's last frame", grey(held, FPS - 1), 20 / 255, TOL)
close("...and holds a dark frame past the trim, not the bright one after the cut",
      grey(held, 3 * FPS - 1), 20 / 255, TOL)

# --- the bench reads a phone clip upright too -----------------------------------

bench = _load("bench")
still = bench.video_frame(turned, 0.0)
check("the bench's frame is portrait", tuple(still.shape[:2]), (64, 32))
quarters = [float(still[:32, :16].mean()), float(still[:32, 16:].mean()),
            float(still[32:, :16].mean()), float(still[32:, 16:].mean())]
check("...and turned the way the player turns it",
      ["TL", "TR", "BL", "BR"][quarters.index(max(quarters))], "TR")

passed("all VFR seam tests passed")
