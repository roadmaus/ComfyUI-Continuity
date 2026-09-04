"""That a thumbnail shows a file the way its player does.

    <comfy-venv>/bin/python3 tests/test_preview.py

A phone stores the photo the sensor took and writes "turn this" beside it; a
phone clip is stored landscape with a rotation in the container. The browser
obeys both on the full picture, so a thumbnail that ignores them is the one
thing on the page lying sideways — which is what core's `/view?preview=`
re-encode did for every still in the pack's grids. `preview._render_thumb`
applies the tag to a still and the display matrix to a clip's frame, and this
checks both by where the bright corner of a lopsided picture ends up.

Needs PIL and av — the ComfyUI venv. Skips itself with a message otherwise.
"""

import importlib.util
import os
import sys
import tempfile
import types

import layout

try:
    import av
    import numpy as np
    from PIL import Image
except Exception as exc:  # noqa: BLE001
    print(f"skipped: needs av and PIL ({type(exc).__name__}: {exc})")
    sys.exit(0)

from harness import FAILURES, check, passed

SCRATCH = tempfile.mkdtemp()

# `preview` wants one thing of ComfyUI: where the user directory is.
sys.modules["folder_paths"] = types.SimpleNamespace(get_user_directory=lambda: SCRATCH)
package = types.ModuleType("mmcprev")
package.__path__ = [layout.PY_ROOT]
sys.modules["mmcprev"] = package
_spec = importlib.util.spec_from_file_location("mmcprev.preview", layout.py("preview"))
preview = importlib.util.module_from_spec(_spec)
sys.modules["mmcprev.preview"] = preview
_spec.loader.exec_module(preview)


def lopsided(width, height):
    """A dark picture with its top-left quarter lit."""
    pic = np.zeros((height, width, 3), np.uint8)
    pic[:height // 2, :width // 2] = 255
    return pic


def corner(image):
    """Which quarter of `image` is the bright one, and the size."""
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    quarters = [a[:h // 2, :w // 2].mean(), a[:h // 2, w // 2:].mean(),
                a[h // 2:, :w // 2].mean(), a[h // 2:, w // 2:].mean()]
    return ["TL", "TR", "BL", "BR"][int(np.argmax(quarters))], image.size


def thumb_of(path):
    out = os.path.join(SCRATCH, os.path.basename(path) + ".webp")
    preview._render_thumb(path, out)
    return Image.open(out)


# --- a still with an orientation tag -----------------------------------------

# Orientation 6: stored landscape, "rotate 90° clockwise to view". Viewed, the
# bright top-left corner is at the top right of a portrait picture.
tagged = os.path.join(SCRATCH, "phone.jpg")
photo = Image.fromarray(lopsided(64, 32))
exif = photo.getexif()
exif[0x0112] = 6
photo.save(tagged, "JPEG", quality=95, exif=exif.tobytes())
check("a tagged still is turned the way the tag says", corner(thumb_of(tagged)), ("TR", (32, 64)))

plain = os.path.join(SCRATCH, "plain.jpg")
Image.fromarray(lopsided(64, 32)).save(plain, "JPEG", quality=95)
check("an untagged still is left alone", corner(thumb_of(plain)), ("TL", (64, 32)))

# --- transparency survives ----------------------------------------------------

clear = os.path.join(SCRATCH, "clear.png")
Image.fromarray(np.dstack([lopsided(64, 32), np.full((32, 64), 128, np.uint8)])).save(clear)
check("a still with transparency keeps it", thumb_of(clear).mode, "RGBA")

# --- a clip with a display matrix --------------------------------------------


def turned_clip(name, rotation):
    path = os.path.join(SCRATCH, name)
    with av.open(path, "w") as out:
        video = out.add_stream("libx264", rate=24)
        video.width, video.height, video.pix_fmt = 64, 32, "yuv420p"
        video.options = {"crf": "1"}
        video.set_display_rotation(rotation)
        for _ in range(6):
            out.mux(video.encode(av.VideoFrame.from_ndarray(lopsided(64, 32), format="rgb24")))
        out.mux(video.encode(None))
    return path


# Read counter-clockwise: 90 puts the top-left corner at the bottom left of a
# portrait frame, -90 (the common phone case) at the top right.
check("a clip turned 90 is portrait, corner bottom-left",
      corner(thumb_of(turned_clip("ccw.mp4", 90))), ("BL", (32, 64)))
check("a clip turned -90 is portrait, corner top-right",
      corner(thumb_of(turned_clip("cw.mp4", -90))), ("TR", (32, 64)))
check("a clip turned 180 is landscape, corner bottom-right",
      corner(thumb_of(turned_clip("flip.mp4", 180))), ("BR", (64, 32)))
check("an unturned clip is left alone",
      corner(thumb_of(turned_clip("flat.mp4", 0))), ("TL", (64, 32)))

passed("all preview tests passed — stills and clips come out the way their player shows them")
