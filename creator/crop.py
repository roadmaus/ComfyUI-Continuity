"""The framing set on a picture or a clip: a turn, a mirror, and a window.

The spatial half of `trim`. A trim says which stretch of a file is the
reference; this says which part of the picture — and which way up. Both are
kept on the asset rather than baked into a file, so the source stays whole on
disk, the framing can be changed on the card, and the thing survives a reload
of the workflow (issue #75).

One blob shape everywhere it is written::

    {"x": 0.25, "y": 0.1, "w": 0.4, "h": 0.6, "turn": 90, "mirror": "h"}

Fractions of the picture *as the browser shows it* — orientation tag applied,
display matrix applied — after the turn and the mirror, in that order. The
frontend draws the box on the turned, mirrored picture, so its numbers are
these numbers with no arithmetic in between. `turn` is clockwise degrees, one
of 0/90/180/270; `mirror` is "" / "h" / "v" / "hv" for left-right, top-bottom,
both. Every field is optional and defaults to identity; a blob that is all
identity parses to None, so a card somebody opened the editor on and left
alone is byte-identical to one that never had it.

Four readers, one arithmetic: `pil` for a still, `tensor` for decoded frames,
`filters` for the ffmpeg graph a supplied clip is spliced through, and
`nodes` for the graph the still families emit. The pixel box comes out of
`box` for all four, so a thumbnail, a reference and a clip card cropped the
same way show the same pixels.
"""

from dataclasses import dataclass

TURNS = (0, 90, 180, 270)
MIRRORS = ("", "h", "v", "hv")

# A window narrower than this is a slip of the hand, not a framing: at 1% of a
# 4000 px sheet that is 40 px, and the model reads nothing off less. Refused
# rather than clamped, because the number came off a box somebody drew and a
# box that came back different from the one drawn is a bug report.
MIN_FRACTION = 0.01


class CropError(ValueError):
    """A framing blob that does not describe a window on a picture."""


@dataclass(frozen=True)
class Crop:
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0
    turn: int = 0
    mirror: str = ""

    @property
    def windowed(self):
        """Whether the box leaves anything out."""
        return not (self.x <= 0 and self.y <= 0 and self.w >= 1 and self.h >= 1)

    @property
    def turned(self):
        return self.turn != 0 or bool(self.mirror)

    def key(self):
        """What a cache key holds for this framing — a plain tuple, rounded
        the way the blob is written, so a re-open that wrote 0.30000001 finds
        the entry 0.3 made."""
        return (round(self.x, 4), round(self.y, 4), round(self.w, 4), round(self.h, 4),
                self.turn, self.mirror)


def parse(raw, what="picture"):
    """A blob -> `Crop`, or None for absent or identity. Raises `CropError`."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CropError(f"{what}: crop must be an object")
    try:
        x = float(raw.get("x", 0.0))
        y = float(raw.get("y", 0.0))
        w = float(raw.get("w", 1.0))
        h = float(raw.get("h", 1.0))
    except (TypeError, ValueError) as exc:
        raise CropError(f"{what}: crop needs numeric x, y, w, h fractions") from exc
    try:
        turn = int(raw.get("turn", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise CropError(f"{what}: crop turn must be 0, 90, 180 or 270") from exc
    if turn not in TURNS:
        raise CropError(f"{what}: crop turn must be 0, 90, 180 or 270 (got {turn})")
    mirror = str(raw.get("mirror") or "")
    if mirror not in MIRRORS:
        raise CropError(f"{what}: crop mirror must be one of h, v, hv (got {mirror!r})")
    if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x + w <= 1 + 1e-6 and y + h <= 1 + 1e-6):
        raise CropError(
            f"{what}: the crop window must lie inside the picture "
            f"(got x {x:.3f} y {y:.3f} w {w:.3f} h {h:.3f})")
    if w < MIN_FRACTION or h < MIN_FRACTION:
        raise CropError(f"{what}: the crop window is too small to be a picture")
    crop = Crop(x=x, y=y, w=min(w, 1 - x), h=min(h, 1 - y), turn=turn, mirror=mirror)
    return crop if (crop.windowed or crop.turned) else None


def to_dict(crop):
    """`Crop` -> the blob shape `parse` reads; only what differs from identity."""
    out = {}
    if crop.windowed:
        out.update(x=round(crop.x, 4), y=round(crop.y, 4),
                   w=round(crop.w, 4), h=round(crop.h, 4))
    if crop.turn:
        out["turn"] = crop.turn
    if crop.mirror:
        out["mirror"] = crop.mirror
    return out


def turned_size(size, crop):
    """(w, h) of the picture after the turn — a quarter turn swaps them."""
    width, height = int(size[0]), int(size[1])
    return (height, width) if crop is not None and crop.turn % 180 else (width, height)


def box(size, crop):
    """The pixel window on the *turned* picture -> (left, top, right, bottom).

    Rounded to the nearest pixel and never empty. `size` is the source's own
    (w, h); the turn is applied here, so callers hand in what they have.
    """
    width, height = turned_size(size, crop)
    if crop is None or not crop.windowed:
        return 0, 0, width, height
    left = min(width - 1, int(round(crop.x * width)))
    top = min(height - 1, int(round(crop.y * height)))
    right = max(left + 1, min(width, int(round((crop.x + crop.w) * width))))
    bottom = max(top + 1, min(height, int(round((crop.y + crop.h) * height))))
    return left, top, right, bottom


def size(source, crop):
    """(w, h) the framed picture comes out at, from the source's (w, h)."""
    left, top, right, bottom = box(source, crop)
    return right - left, bottom - top


def pil(image, crop):
    """A PIL image, framed. Returns the input untouched when there is nothing to do."""
    if crop is None:
        return image
    from PIL import Image

    turn = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_90}.get(crop.turn)
    if turn is not None:
        image = image.transpose(turn)
    if "h" in crop.mirror:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if "v" in crop.mirror:
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if crop.windowed:
        image = image.crop(box((image.width, image.height), Crop(crop.x, crop.y, crop.w, crop.h)))
    return image


def tensor(frames, crop):
    """`[N, H, W, C]` frames, framed. The same picture `pil` makes of a still."""
    if crop is None:
        return frames
    import torch

    if crop.turn:
        # dims (2, 1) turns clockwise — the sense core's ImageRotate uses.
        frames = torch.rot90(frames, k=crop.turn // 90, dims=(2, 1))
    if "h" in crop.mirror:
        frames = torch.flip(frames, dims=[2])
    if "v" in crop.mirror:
        frames = torch.flip(frames, dims=[1])
    if crop.windowed:
        left, top, right, bottom = box(
            (frames.shape[2], frames.shape[1]), Crop(crop.x, crop.y, crop.w, crop.h))
        frames = frames[:, top:bottom, left:right, :]
    return frames.contiguous()


def filters(crop):
    """The ffmpeg filter steps for this framing, as `(name, args)` pairs.

    For `mux._clip_graph`, after the picture is upright and before it is
    scaled to the canvas. The window is in `iw`/`ih` so the graph needs no
    size handed in; rounding is ffmpeg's rather than `box`'s, which can differ
    by a pixel on an odd-sized source and cannot matter after the scale.
    """
    if crop is None:
        return []
    steps = []
    if crop.turn == 90:
        steps.append(("transpose", "clock"))
    elif crop.turn == 180:
        steps += [("hflip", ""), ("vflip", "")]
    elif crop.turn == 270:
        steps.append(("transpose", "cclock"))
    if "h" in crop.mirror:
        steps.append(("hflip", ""))
    if "v" in crop.mirror:
        steps.append(("vflip", ""))
    if crop.windowed:
        steps.append(("crop", f"round(iw*{crop.w:.6f}):round(ih*{crop.h:.6f})"
                              f":round(iw*{crop.x:.6f}):round(ih*{crop.y:.6f})"))
    return steps


def nodes(graph, image, crop, source_size):
    """Core nodes that frame `image` (an output socket) the same way. -> socket.

    For the still families, which load their pictures with core's `LoadImage`
    in the graph rather than through `media`. `ImageCrop` takes pixels, so the
    source's size is needed here and nowhere else in this module — the
    compile resolved it, see `compile_image._framed`.
    """
    if crop is None:
        return image
    if crop.turn:
        image = graph.node("ImageRotate", image=image,
                           rotation=f"{crop.turn} degrees").out(0)
    if "h" in crop.mirror:
        image = graph.node("ImageFlip", image=image,
                           flip_method="y-axis: horizontally").out(0)
    if "v" in crop.mirror:
        image = graph.node("ImageFlip", image=image,
                           flip_method="x-axis: vertically").out(0)
    if crop.windowed:
        left, top, right, bottom = box(source_size, crop)
        image = graph.node("ImageCrop", image=image, x=left, y=top,
                           width=right - left, height=bottom - top).out(0)
    return image
