"""The framing on a picture: one arithmetic, four readers, the same pixels.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_crop.py

`creator/crop.py` is read by a still (`pil`), by decoded frames (`tensor`),
by the ffmpeg graph a clip card is spliced through (`filters`) and by the
graph the still families emit (`nodes`). A chip's thumbnail is drawn by the
first and its reference is read by one of the other three, so what this suite
pins is that they agree: the same quadrant of the same picture, turned the
same way, whichever door it came through.

The picture is four flat colours in four quadrants, so a turn or a mirror is
told from the original by which colour lands where — and a window of it is
one colour, which is what makes "the crop is the top-right quadrant" a claim
a mean can check. Skips itself if ComfyUI or PyAV cannot be imported.
"""

import importlib.util
import os
import sys
import types

import layout

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import folder_paths  # noqa: F401


try:
    import av
    import numpy as np
    import torch
    from PIL import Image

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


crop = _load("crop")
media = _load("media")

from harness import FAILURES, check, passed  # noqa: E402

passed("all crop tests passed")

# ---- the picture -------------------------------------------------------------

W, H = 64, 32
RED, GREEN, BLUE, WHITE = (220, 30, 30), (30, 200, 30), (30, 30, 220), (240, 240, 240)


def quadrants(tl, tr, bl, br):
    plane = np.zeros((H, W, 3), dtype=np.uint8)
    plane[:H // 2, :W // 2] = tl
    plane[:H // 2, W // 2:] = tr
    plane[H // 2:, :W // 2] = bl
    plane[H // 2:, W // 2:] = br
    return plane


PLANE = quadrants(RED, GREEN, BLUE, WHITE)


def colour_of(array):
    """The one colour a flat window is, as the nearest of the four."""
    mean = np.asarray(array, dtype=np.float32).reshape(-1, 3).mean(axis=0)
    names = {"red": RED, "green": GREEN, "blue": BLUE, "white": WHITE}
    return min(names, key=lambda n: np.abs(mean - np.array(names[n])).sum())


def corners(array):
    """Which colour sits in each corner: (tl, tr, bl, br)."""
    a = np.asarray(array)
    h, w = a.shape[0], a.shape[1]
    return tuple(colour_of(a[y:y + 2, x:x + 2]) for y, x in
                 ((0, 0), (0, w - 2), (h - 2, 0), (h - 2, w - 2)))


# ---- parse -------------------------------------------------------------------

check("absent is None", crop.parse(None), None)
check("identity is None", crop.parse({"x": 0, "y": 0, "w": 1, "h": 1}), None)
check("a bare turn is a framing", crop.parse({"turn": 90}).turn, 90)
check("to_dict writes only what differs",
      crop.to_dict(crop.parse({"x": 0.5, "y": 0, "w": 0.5, "h": 0.5, "turn": 0})),
      {"x": 0.5, "y": 0.0, "w": 0.5, "h": 0.5})
for bad in ({"x": -0.1}, {"w": 0}, {"x": 0.8, "w": 0.5}, {"turn": 45}, {"mirror": "x"},
            {"w": 0.001, "h": 0.5}):
    try:
        crop.parse(bad)
    except crop.CropError:
        pass
    else:
        FAILURES.append(f"{bad!r} should not parse")

# ---- size --------------------------------------------------------------------

check("a quarter turn swaps the size", crop.size((W, H), crop.parse({"turn": 90})), (H, W))
check("a window's size is its pixels",
      crop.size((W, H), crop.parse({"x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5})), (W // 2, H // 2))
check("a window on a turned picture is measured after the turn",
      crop.size((W, H), crop.parse({"x": 0, "y": 0, "w": 0.5, "h": 0.5, "turn": 90})),
      (H // 2, W // 2))

# ---- the readers agree --------------------------------------------------------

CASES = {
    # what it is                 the framing                          corners after
    "top-right quadrant":       ({"x": 0.5, "y": 0, "w": 0.5, "h": 0.5}, ("green",) * 4),
    "turned 90 clockwise":      ({"turn": 90}, ("blue", "red", "white", "green")),
    "turned 180":               ({"turn": 180}, ("white", "blue", "green", "red")),
    "turned 270 clockwise":     ({"turn": 270}, ("green", "white", "red", "blue")),
    "mirrored left-right":      ({"mirror": "h"}, ("green", "red", "white", "blue")),
    "mirrored top-bottom":      ({"mirror": "v"}, ("blue", "white", "red", "green")),
    "turned then windowed":     ({"turn": 90, "x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5}, ("green",) * 4),
    "mirrored then windowed":   ({"mirror": "h", "x": 0, "y": 0, "w": 0.5, "h": 0.5}, ("green",) * 4),
}

for label, (raw, want) in CASES.items():
    framing = crop.parse(raw)
    via_pil = np.array(crop.pil(Image.fromarray(PLANE), framing))
    check(f"pil: {label}", corners(via_pil), want)
    via_tensor = (crop.tensor(torch.from_numpy(PLANE).float().unsqueeze(0) / 255.0, framing)[0] * 255)
    check(f"tensor: {label}", corners(via_tensor.numpy()), want)
    check(f"pil and tensor are the same size: {label}", via_tensor.shape[:2], via_pil.shape[:2])

# ---- the ffmpeg graph reads the same window ----------------------------------

SCRATCH = os.environ.get("TMPDIR", "/tmp")
CLIP = os.path.join(SCRATCH, "mmc_test_crop.mp4")
container = av.open(CLIP, mode="w")
video = container.add_stream("libx264", rate=24)
video.width, video.height = W, H
video.pix_fmt = "yuv420p"
for _ in range(12):
    container.mux(video.encode(av.VideoFrame.from_ndarray(PLANE, format="rgb24")))
container.mux(video.encode(None))
container.close()
media.resolve = lambda filename: filename

for label, (raw, want) in CASES.items():
    framing = crop.parse(raw)
    frames, _ = media.load_video(CLIP, crop=framing)
    check(f"ffmpeg: {label}", corners((frames[0] * 255).numpy()), want)
    check(f"ffmpeg and pil agree on the size: {label}",
          tuple(frames.shape[1:3]), crop.size((W, H), framing)[::-1])

# A still through `load_image` takes the same door.
STILL = os.path.join(SCRATCH, "mmc_test_crop.png")
Image.fromarray(PLANE).save(STILL)
for label, (raw, want) in CASES.items():
    got = media.load_image(STILL, crop=crop.parse(raw))
    check(f"load_image: {label}", corners((got[0] * 255).numpy()), want)
check("image_size follows the window",
      media.image_size(STILL, crop.parse({"turn": 90, "w": 0.5, "h": 0.5})), (H // 2, W // 2))

# ---- the graph the still families emit -----------------------------------------


class Graph:
    def __init__(self):
        self.nodes = []

    def node(self, kind, **inputs):
        self.nodes.append((kind, inputs))
        graph = self

        class Out:
            def out(self, index):
                return (kind, len(graph.nodes) - 1, index)
        return Out()


graph = Graph()
crop.nodes(graph, "img", crop.parse({"turn": 90, "mirror": "hv", "x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5}), (W, H))
check("the graph turns, flips twice and crops",
      [kind for kind, _ in graph.nodes], ["ImageRotate", "ImageFlip", "ImageFlip", "ImageCrop"])
check("the graph's crop is in pixels of the turned picture",
      graph.nodes[-1][1], {"image": ("ImageFlip", 2, 0), "x": H // 2, "y": W // 2,
                            "width": H // 2, "height": W // 2})
check("nothing framed emits nothing", crop.nodes(Graph(), "img", None, (W, H)), "img")

# The core nodes, when this ComfyUI has them, turn the same way `tensor` does.
try:
    from comfy_extras import nodes_images
except Exception:  # noqa: BLE001
    nodes_images = None
if nodes_images is not None:
    one = torch.from_numpy(PLANE).float().unsqueeze(0) / 255.0
    turned = nodes_images.ImageRotate.execute(one, "90 degrees")
    turned = getattr(turned, "args", turned)
    turned = turned[0] if isinstance(turned, (tuple, list)) else turned
    check("core's ImageRotate turns clockwise like tensor does",
          corners((turned[0] * 255).numpy()), CASES["turned 90 clockwise"][1])

for path in (CLIP, STILL):
    os.remove(path)
