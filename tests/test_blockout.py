"""The blockout bench's server half: staging, and the encode.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_blockout.py

`blockout.py` is the smallest server half a bench has — the browser renders,
the server encodes — and what is worth a net under it is exactly the part a
refactor would break silently: the token that confines staging to hex (it
becomes a directory name, so it must never be a path), the PNG gate on what a
batch may hold, and the write that turns staged frames into an mp4 beside its
scene sidecar and leaves nothing behind in staging.

Runs against temp directories, never the machine's own input folder: the
folder functions are rebound for the length of the suite.

Skips itself with a message if ComfyUI cannot be imported — `folder_paths` is
where the input folder comes from, and there is no answering that without it.
"""

import io
import json
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
    import av  # noqa: F401
    from PIL import Image

    import folder_paths
except Exception as exc:  # noqa: BLE001
    harness.skip(f"ComfyUI not importable ({type(exc).__name__}: {exc})")

pkg = layout.load("settings", "bench", "blockout")
blockout = pkg.blockout

# ---- the token is hex or it is nothing ---------------------------------------
#
# It names a directory. Every rejected shape below is a thing a directory name
# must never be handed: empty, a traversal, a separator, the wrong alphabet.

for bad in ("", "..", "../evil", "a/b", "DEADBEEF", "deadbeef genuinely not",
            "abc", "x" * 65, None, 7):
    try:
        blockout._staging(bad)
        FAILURES.append(f"token {bad!r} was accepted")
    except blockout.BlockoutError:
        pass
try:
    path = blockout._staging("deadbeef00")
    check("a hex token resolves under staging", blockout.STAGING in path, True)
except blockout.BlockoutError:
    FAILURES.append("token 'deadbeef00' was refused")


def png_bytes(width=32, height=18, tone=128):
    frame = Image.new("RGB", (width, height), (tone, tone, tone))
    held = io.BytesIO()
    frame.save(held, "PNG")
    return held.getvalue()


with tempfile.TemporaryDirectory() as temp_root, \
     tempfile.TemporaryDirectory() as input_root:
    held_temp = folder_paths.get_temp_directory
    held_input = folder_paths.get_input_directory
    folder_paths.get_temp_directory = lambda: temp_root
    folder_paths.get_input_directory = lambda: input_root
    try:
        token = "cafe0123cafe0123"

        # ---- staging gates ---------------------------------------------------
        try:
            blockout.take_frames(token, [(0, b"not a png at all")])
            FAILURES.append("non-PNG bytes were staged")
        except blockout.BlockoutError:
            pass
        try:
            blockout.take_frames(token, [(blockout.MOST_FRAMES, png_bytes())])
            FAILURES.append("an out-of-range index was staged")
        except blockout.BlockoutError:
            pass

        # ---- one frame is a still, not a clip --------------------------------
        blockout.take_frames(token, [(0, png_bytes())])
        try:
            blockout.write(token, 24, "depth")
            FAILURES.append("a one-frame write was accepted")
        except blockout.BlockoutError:
            pass

        # ---- the round trip --------------------------------------------------
        # Batches out of order, an overwrite among them: the index names the
        # frame, so both are the contract rather than edge cases.
        blockout.take_frames(token, [(2, png_bytes(tone=40)), (1, png_bytes(tone=80))])
        blockout.take_frames(token, [(3, png_bytes(tone=20)), (0, png_bytes(tone=120))])
        answer = blockout.write(token, 24, "depth", scene={"marks": [1, 2]})
        check("the answer is a clip", answer.get("kind"), "video")
        check("the answer names the shelf",
              answer.get("path", "").startswith(f"{blockout.SUBFOLDER}/blockout-depth"), True)

        written = os.path.join(input_root, *answer["path"].split("/"))
        check("the clip exists", os.path.isfile(written), True)
        with av.open(written) as clip:
            stream = clip.streams.video[0]
            check("four frames were encoded", stream.frames, 4)
            check("the rate is what was asked", int(stream.average_rate), 24)

        sidecar = os.path.splitext(written)[0] + ".json"
        check("the sidecar exists", os.path.isfile(sidecar), True)
        with open(sidecar, encoding="utf-8") as held:
            body = json.load(held)
        check("the sidecar carries the scene", body.get("scene"), {"marks": [1, 2]})
        check("the sidecar names the pass", body.get("op"), "depth")

        check("staging was swept", os.path.isdir(os.path.join(
            temp_root, blockout.STAGING, token)), False)

        # ---- a second write does not overwrite the first ---------------------
        blockout.take_frames(token, [(0, png_bytes()), (1, png_bytes())])
        again = blockout.write(token, 24, "depth")
        check("the counter moved", again["path"] != answer["path"], True)
    finally:
        folder_paths.get_temp_directory = held_temp
        folder_paths.get_input_directory = held_input

passed("all blockout tests passed")
