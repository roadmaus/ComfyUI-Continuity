"""The bench plumbing, and the upscale bench that was the second user of it.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_bench.py

`bench.py` is code that was written for the tracing bench and moved when the
upscale bench needed the same of it — reading a source, filling a dial from the
model folders, clamping what the sliders sent, naming the file, transcoding a
clip. A move is exactly the change no other suite here would notice: the
frontend reads the catalogue over the wire, and every part of it that matters is
prose the mirrors do not check. So the first block below is a net under that
move — the nine tracings and the dials each one takes, spelled out, so a
refactor that quietly drops one has something to fail.

The rest is the arithmetic the upscale bench is: which size a scale means, which
square of a frame is on the glass, and what the catalogue says on a machine that
has no upscale model on it.

Skips itself with a message if ComfyUI cannot be imported — `folder_paths` is
what a dial reads its options from, and there is no answering that without it.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness
import layout
from harness import FAILURES, check, passed

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)
try:
    import av
    import numpy as np

    import folder_paths  # noqa: F401
except Exception as exc:  # noqa: BLE001
    harness.skip(f"ComfyUI not importable ({type(exc).__name__}: {exc})")

pkg = layout.load("settings", "bench", "outputs", "control", "upscale")
bench, control, upscale, outputs = pkg.bench, pkg.control, pkg.upscale, pkg.outputs

# ---- the tracings survived the move ------------------------------------------
#
# Every tracing, and the dials it takes, in the order the surface draws them. A
# dial that goes missing here is a control that vanishes off the bench with
# nothing else in this suite noticing.

TRACINGS = {
    "as_shot": [],
    "edges": ["soften", "faint", "strong", "invert"],
    "lines": ["detail", "ink", "bite", "invert"],
    "blocks": ["fields", "settle"],
    "luma": ["lift", "curve", "invert"],
    "blur": ["radius"],
    "depth": ["model", "detail", "sky", "steady", "invert"],
    "pose": ["model", "vae", "body", "hands", "face", "feet", "certainty", "weight"],
    "matte": ["model", "who", "certainty", "grow", "invert"],
}

served = control.catalogue()["tracings"]
check("tracings listed", [entry["id"] for entry in served], list(TRACINGS))
for entry in served:
    check(f"{entry['id']} dials", [spec["key"] for spec in entry["params"]],
          TRACINGS[entry["id"]])
    # `ready` is this machine's answer and cannot be asserted; that it is an
    # answer at all is the contract the surface draws its dashed pill from.
    check(f"{entry['id']} ready is a verdict", isinstance(entry["ready"], bool), True)
    # The folders a choice dial draws from are the server's business and are
    # spent on the way out — a `from` that reached the browser would be a model
    # folder named in a payload nothing there can use.
    for spec in entry["params"]:
        if spec["kind"] == "choice":
            check(f"{entry['id']}.{spec['key']} options listed",
                  isinstance(spec.get("options"), list), True)
            check(f"{entry['id']}.{spec['key']} folders kept back", "from" in spec, False)

# An unknown operator is a typo the caller has to see, not a default.
try:
    control._params("sharpen", {})
    FAILURES.append("an unknown tracing was accepted")
except control.ControlError:
    pass

# ---- the dials ----------------------------------------------------------------

DIALS = {
    "id": "test", "label": "Test", "needs": "nothing at all",
    "params": (
        {"key": "amount", "kind": "range", "min": 1, "max": 4, "step": 0.5, "default": 2},
        {"key": "on", "kind": "switch", "default": True},
        {"key": "who", "kind": "text", "default": "person"},
    ),
}

check("a slider past its ceiling is clamped", bench.values(DIALS, {"amount": 9})["amount"], 4.0)
check("a slider under its floor is clamped", bench.values(DIALS, {"amount": -3})["amount"], 1.0)
check("a missing slider takes its default", bench.values(DIALS, {})["amount"], 2.0)
check("nonsense takes the default too", bench.values(DIALS, {"amount": "wide"})["amount"], 2.0)
check("a switch off the query string", bench.values(DIALS, {"on": "0"})["on"], False)
check("a switch left out keeps its default", bench.values(DIALS, {})["on"], True)
check("an emptied box is the default question", bench.values(DIALS, {"who": "  "})["who"], "person")
check("free words are kept", bench.values(DIALS, {"who": " the man in red "})["who"],
      "the man in red")

# A choice with nothing on the disk is the one thing this raises for, and it
# raises with `needs` — "pick a model" is no use to somebody who has not
# downloaded one.
EMPTY = {"id": "t", "label": "Test", "needs": "a model nobody has",
         "params": ({"key": "model", "kind": "choice", "from": ("no_such_folder",),
                     "default": ""},)}
try:
    bench.values(EMPTY, {})
    FAILURES.append("a choice with no files was accepted")
except bench.BenchError as exc:
    check("the refusal says what is missing", "a model nobody has" in str(exc), True)

# ---- naming what comes out -----------------------------------------------------

check("a stem says what was done to what",
      bench.stem("/tmp/my clip.mp4", "edges"), "my clip-edges")
check("a span is named by its seconds",
      bench.stem("/tmp/clip.mp4", "edges", (1.2, 6.8)), "clip-edges-1-7s")
check("a mark wins over a span",
      bench.stem("/tmp/clip.mp4", "edges", (1.0, 6.0), 2.25), "clip-edges-2-2s")
check("a long name leaves room for the counter",
      len(bench.stem(f"/tmp/{'x' * 200}.mp4", "sharpen")), 98)

with tempfile.TemporaryDirectory() as shelf:
    first = bench.free_name(shelf, "clip-sharpen", ".png")
    open(os.path.join(shelf, first), "w").close()
    second = bench.free_name(shelf, "clip-sharpen", ".png")
    check("the first file is unnumbered", first, "clip-sharpen.png")
    check("the second is counted", second, "clip-sharpen-2.png")

check("an odd dimension is brought down", bench.even(1081), 1080)
check("an even one is left alone", bench.even(1080), 1080)

# ---- carrying a clip through ---------------------------------------------------
#
# `transcode` is the long one — decode the chosen span, put every frame through
# `work`, encode it again with its sound and its timing intact — and it had never
# been run in this suite. What that cost was every clip with an audio track: the
# audio fifo's walrus was named `chunk`, which is also this function's
# frames-per-work parameter, so the first audio frame rebound it and the loop
# left it None, and the next video frame died on `max(1, None)`. It was reached
# by the upscale bench on ordinary settings, `keep_sound` defaulting to true
# there, after the model had already run on the frames before it.


def clip_with_sound(path, frames=24, rate=24):
    """A short clip that really has both streams — the shape that broke."""
    with av.open(path, "w") as out:
        video = out.add_stream("libx264", rate=rate)
        video.width, video.height = 64, 64
        video.pix_fmt = "yuv420p"
        audio = out.add_stream("aac", rate=48000)
        audio.layout = "stereo"
        for index in range(frames):
            out.mux(video.encode(av.VideoFrame.from_ndarray(
                np.full((64, 64, 3), index * 10 % 255, np.uint8), format="rgb24")))
        samples = av.AudioFrame.from_ndarray(
            np.zeros((2, 48000 * frames // rate), np.float32),
            format="fltp", layout="stereo")
        samples.rate = 48000
        fifo = av.AudioFifo()
        fifo.write(samples)
        while (piece := fifo.read(audio.frame_size)) is not None:
            out.mux(audio.encode(piece))
        out.mux(audio.encode(None))
        out.mux(video.encode(None))


def streams_of(path):
    """-> (frames written, whether the sound came with them)."""
    with av.open(path) as container:
        written = sum(1 for _ in container.decode(container.streams.video[0]))
        return written, bool(list(container.streams.audio))


with tempfile.TemporaryDirectory() as shelf:
    source = os.path.join(shelf, "clip.mp4")
    clip_with_sound(source)

    # One frame at a time, sound kept: the upscale bench's Sharpen, exactly.
    name = bench.transcode(source, shelf, "one", work=lambda frames: frames,
                           chunk=1, keep_sound=True)
    check("a clip with sound comes through", streams_of(os.path.join(shelf, name)),
          (24, True))

    # And in chunks with a crossfade: Restore's shape, where `chunk` being read
    # correctly decides how many frames reach `work` at a time.
    seen = []
    name = bench.transcode(source, shelf, "many",
                           work=lambda frames: (seen.append(len(frames)), frames)[1],
                           chunk=4, overlap=2, keep_sound=True)
    check("chunked work sees its chunk", max(seen), 4)
    check("and the clip still comes through",
          streams_of(os.path.join(shelf, name)), (24, True))

    # Sound left behind on purpose — the tracing bench's default.
    name = bench.transcode(source, shelf, "silent", work=lambda frames: frames,
                           chunk=1, keep_sound=False)
    check("and is dropped when it is not asked for",
          streams_of(os.path.join(shelf, name)), (24, False))

    # A run that dies partway has already created its file, and `free_name`
    # counts up — so a bench pressed three times left three unplayable mp4s on
    # the shelf beside the renders.
    class BenchExploded(Exception):
        pass

    def explode(frames):
        raise BenchExploded("the work gave up")

    before = sorted(os.listdir(shelf))
    try:
        bench.transcode(source, shelf, "doomed", work=explode, chunk=1, keep_sound=True)
        FAILURES.append("a work that raised was reported as a finished file")
    except BenchExploded:
        pass
    check("a failed run leaves nothing behind", sorted(os.listdir(shelf)), before)


# ---- the upscale bench ----------------------------------------------------------

backends = upscale.catalogue()["backends"]
check("the backends, weakest promise first", [entry["id"] for entry in backends],
      ["sharpen", "restore"])
check("Sharpen's dials", [spec["key"] for spec in backends[0]["params"]],
      ["model", "scale"])
check("Restore's dials", [spec["key"] for spec in backends[1]["params"]],
      ["model", "vae", "scale", "colour", "frames"])
for entry in backends:
    check(f"{entry['id']} is model work", entry["heavy"], True)
    check(f"{entry['id']} readiness is a verdict", isinstance(entry["ready"], bool), True)

try:
    upscale._params("seedvr", {})
    FAILURES.append("a backend that does not exist was accepted")
except upscale.UpscaleError:
    pass

# A fixed set the operator declares: an unknown value is a stale frontend and
# takes the default, where an unknown *file* would have been a refusal.
check("a colour method off the list", upscale._params(
    "restore", {"colour": "sepia"}, weights=False)["colour"], "lab")
check("and one on it is kept", upscale._params(
    "restore", {"colour": "wavelet"}, weights=False)["colour"], "wavelet")

# How much of a clip each backend reads at once, and how much of that the next
# chunk re-does. Per-frame work has no join to hide; Restore's chunks are
# separate samples of the same clip, which is exactly the join that shows.
check("Sharpen takes one frame", upscale.chunk_of("sharpen", {}), 1)
check("and has nothing to blend", upscale.overlap_of("sharpen", {}), 0)
check("Restore takes the dial", upscale.chunk_of("restore", {"frames": 13}), 13)
check("and blends four", upscale.overlap_of("restore", {"frames": 13}), 4)
check("an overlap never eats its chunk",
      upscale.overlap_of("restore", {"frames": 5}) < upscale.chunk_of("restore", {"frames": 5}),
      True)

# The crossfade weights: the previous chunk holds the join, hands it over in the
# middle, and is gone by the end.
fade = bench._fade(8)
check("the fade starts on the old chunk", fade[0], 1.0)
check("and ends on the new one", fade[-1], 0.0)
check("and never turns back", all(a >= b for a, b in zip(fade, fade[1:])), True)

check("x2 of an odd size rounds", upscale.target(1067, 601, {"scale": 2}), (2134, 1202))
check("x1.5 rounds to the nearest pixel", upscale.target(101, 101, {"scale": 1.5}), (152, 152))
check("nothing collapses to nothing", upscale.target(1, 1, {"scale": 1.5}), (2, 2))

# The tile: a square of `PREVIEW_TILE`, or the whole frame where the frame is
# smaller, and never running off an edge — a tile that did would show the model's
# answer for a border that is not in the file.
frame = np.zeros((500, 1000, 3), dtype=np.uint8)
frame[0:100, 0:100] = 255
check("the tile is square", upscale._tile(frame, (0.5, 0.5)).shape, (384, 384, 3))
corner = upscale._tile(frame, (0.0, 0.0))
check("a tile at the corner stays inside", corner.shape, (384, 384, 3))
check("and it is the corner", int(corner[0, 0, 0]), 255)
far = upscale._tile(frame, (1.0, 1.0))
check("the far corner is clamped too", far.shape, (384, 384, 3))
small = np.zeros((120, 200, 3), dtype=np.uint8)
check("a small source is the whole source", upscale._tile(small, (0.5, 0.5)).shape, (120, 120, 3))

check("the shelf is under the pack's own folder",
      outputs.UPSCALED.startswith("continuity/"), True)

passed("the bench plumbing holds, and the upscale bench with it")
