"""A pass written to disk comes back as the pass that was written.

`spill.py` is what stops a render from holding every decoded pass in memory at
once, and it earns that by being the only copy of the frames there is. So the
things worth asserting are the ones a lost pass would fail silently on: the
frames come back in order and at the values they went in at, a seam reads the
right end of the right length, and a pass long enough to matter is never
resident on the way in or out.

Needs torch and numpy — the ComfyUI venv:

    <comfy-venv>/bin/python3 tests/test_spill.py

Skips itself with a message if they are not importable.
"""

import importlib.util
import os
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    """`spill.py` on its own. It imports nothing from the package, and the one
    thing it wants from ComfyUI is `directory()`, which is replaced below."""
    package = types.ModuleType("mmcspill")
    package.__path__ = [ROOT]
    sys.modules["mmcspill"] = package
    spec = importlib.util.spec_from_file_location(
        "mmcspill.spill", os.path.join(ROOT, "spill.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["mmcspill.spill"] = module
    spec.loader.exec_module(module)
    return module


try:
    import numpy as np
    import torch

    spill = _load()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: needs torch and numpy ({type(exc).__name__}: {exc})")
    sys.exit(0)

WHERE = tempfile.mkdtemp(prefix="mmc-spill-")
spill.directory = lambda: WHERE

from harness import FAILURES, check, passed
FPS = 24
RATE = 48000


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


def ramp(count, height=6, width=8):
    """A pass whose every frame is a different flat value, so a window read back
    off one end says which frames it actually got."""
    values = torch.arange(count, dtype=torch.float32).div(255.0)
    return values.view(count, 1, 1, 1).expand(count, height, width, 3).contiguous()


def tone(seconds, channels=2, rate=RATE):
    samples = int(round(seconds * rate))
    # Channel 0 counts up and channel 1 counts down, so a window says both which
    # end it came from and that the channels were not transposed on the way.
    up = torch.arange(samples, dtype=torch.float32) / max(1, samples)
    return {"waveform": torch.stack([up, 1 - up]).unsqueeze(0), "sample_rate": rate}


# ---- the round trip ---------------------------------------------------------

spec = spill.write(ramp(30), tone(30 / FPS), FPS)
check("the spec counts the frames", spec["frames"], 30)
check("...and their shape", (spec["width"], spec["height"]), (8, 6))
check("...and the sound that went with them",
      (spec["rate"], spec["channels"], spec["samples"]), (RATE, 2, int(30 / FPS * RATE)))
check("the frames are on disk", os.path.exists(spec["frames_path"]), True)
check("...at a byte per channel per pixel",
      os.path.getsize(spec["frames_path"]), 30 * 6 * 8 * 3)

# A pass is 8-bit on disk — see the module docstring for why that costs the file
# nothing — so a value that started as k/255 comes back as exactly k/255.
back = spill.frames(spec, 30, "tail")
check("every frame comes back", tuple(back.shape), (30, 6, 8, 3))
check("...in order and at their own values",
      [round(float(f[0, 0, 0]) * 255) for f in back], list(range(30)))

# ---- what a seam reads ------------------------------------------------------

check("a one-frame seam takes the last frame",
      round(float(spill.frames(spec, 1)[0, 0, 0, 0]) * 255), 29)
check("a blended seam takes the last run",
      [round(float(f[0, 0, 0]) * 255) for f in spill.frames(spec, 5)], [25, 26, 27, 28, 29])
check("...and the head end reads the other way",
      [round(float(f[0, 0, 0]) * 255) for f in spill.frames(spec, 3, "head")], [0, 1, 2])
expect_error("a seam wider than the pass is refused rather than padded",
             lambda: spill.frames(spec, 64), "shorten the blend")

tail = spill.sound(spec, 0.25)
check("a sound seam is the length it asked for",
      int(tail["waveform"].shape[-1]), int(0.25 * RATE))
check("...and comes off the end", round(float(tail["waveform"][0, 0, -1]), 3),
      round(float(tone(30 / FPS)["waveform"][0, 0, -1]), 3))
check("...with the channels the way round they went in",
      bool(tail["waveform"][0, 0, -1] > tail["waveform"][0, 1, -1]), True)
# A pass shorter than the tail hands over what it has: silence we invented is
# not what came before.
check("a pass shorter than the tail gives everything it has",
      int(spill.sound(spec, 10.0)["waveform"].shape[-1]), int(30 / FPS * RATE))

silent = spill.write(ramp(4), None, FPS)
check("a pass with no sound writes none", "audio_path" in silent, False)
expect_error("...and says so rather than inventing silence",
             lambda: spill.sound(silent, 0.5), "decoded none")

# ---- a pass repaired in the picture -----------------------------------------
#
# What the face pass writes back. The frames are new, the sound is the sound it
# already had — and the new spec points at the *same* audio file rather than a
# copy of it, because a pass whose face was redrawn did not have its soundtrack
# re-decided.

middle = spill.sound_between(spec, 10 / FPS, 15 / FPS)
check("a window off the middle is the length it asked for",
      int(middle["waveform"].shape[-1]), int(round(15 / FPS * RATE)) - int(round(10 / FPS * RATE)))
check("...and is the sound under those frames",
      round(float(middle["waveform"][0, 0, 0]), 3),
      round(float(tone(30 / FPS)["waveform"][0, 0, int(round(10 / FPS * RATE))]), 3))
expect_error("a window off a pass that decoded no sound",
             lambda: spill.sound_between(silent, 0, 1), "decoded no sound")

repaired = spill.rewrite(spec, [ramp(20) * 0 + 0.5, ramp(10) * 0 + 0.5])
check("a rewritten pass is as long as the one it replaces",
      repaired["frames"], spec["frames"])
check("...and is a different file", repaired["frames_path"] != spec["frames_path"], True)
check("...holding the new pictures",
      round(float(spill.frames(repaired, 1)[0, 0, 0, 0]) * 255), 127)
check("...while the original is left alone",
      round(float(spill.frames(spec, 1)[0, 0, 0, 0]) * 255), 29)
check("the sound is the same file, not a copy of it",
      repaired["audio_path"], spec["audio_path"])
expect_error("a rewrite that does not cover the pass",
             lambda: spill.rewrite(spec, [ramp(4)]), "as long as the one it replaces")

# ---- the failures a spill has that a tensor did not -------------------------

gone = spill.write(ramp(4), None, FPS)
os.remove(gone["frames_path"])
expect_error("a spill that is no longer there says where it went",
             lambda: spill.frames(gone, 1), "temp directory")

# Pruning is by how long nothing has read the file: the reel holds paths, and a
# re-queue that changes nothing but the save node's quality replays those parts
# without re-decoding them.
fresh = spill.write(ramp(4), None, FPS)
stale = spill.write(ramp(4), None, FPS)
old = time.time() - spill.KEEP_SECONDS - 60
os.utime(stale["frames_path"], (old, old))
# ...and a read is what "in play" means: a reel replayed from the cache reads
# its parts, and that has to be enough to keep them. Otherwise a workflow left
# open overnight comes back to a render it can no longer write.
read_again = spill.write(ramp(4), None, FPS)
os.utime(read_again["frames_path"], (old, old))
spill.frames(read_again, 1)
spill.prune()
check("a spill past its keep time is deleted", os.path.exists(stale["frames_path"]), False)
check("...and a fresh one is not", os.path.exists(fresh["frames_path"]), True)
check("...and neither is one that was just read",
      os.path.exists(read_again["frames_path"]), True)

# ---- nothing is materialised ------------------------------------------------
#
# The whole point. A window off a long pass must not read the pass to take a
# slice of it, and the muxer's reader must not either — both go through a
# memmap, which numpy will say so about.
long_pass = spill.write(ramp(600), None, FPS)
check("the reader is a memmap, not a read",
      isinstance(spill.open_frames(long_pass), np.memmap), True)
check("...and a seam off it costs the seam's width",
      tuple(spill.frames(long_pass, 2).shape), (2, 6, 8, 3))

passed("all spill tests passed — passes written and read back")
