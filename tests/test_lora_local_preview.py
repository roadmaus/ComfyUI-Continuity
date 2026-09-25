"""Local preview companions agree between the card row and image endpoint."""

import base64
import json
import os
import struct
import tempfile

import layout
from harness import check


lorameta = layout.load("lorameta").lorameta

# Resolution checks inspect size and extension, not media decoding.
IMAGE = b"\x89PNG\r\n\x1a\n" + b"\0" * 200
EMBEDDED = "data:image/png;base64," + base64.b64encode(IMAGE).decode("ascii")


def write(path, data=IMAGE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def write_json(path, data):
    return write(path, json.dumps(data).encode("utf-8"))


def fresh(directory, embedded=True, cm_info=False):
    lorameta.forget()
    holder = os.path.join(directory, str(len(os.listdir(directory))))
    path = os.path.join(holder, "Lighting.safetensors")
    metadata = {"modelspec.thumbnail": EMBEDDED} if embedded else {}
    header = json.dumps({"__metadata__": metadata}).encode("utf-8")
    write(path, struct.pack("<Q", len(header)) + header)
    if cm_info:
        write_json(path.removesuffix(".safetensors") + ".cm-info.json", {
            "ModelName": "Studio Lighting", "VersionName": "v2",
            "BaseModel": "MiniMax H3",
        })
    return path


def local_preview(label, path, expected, kind="image"):
    check(label + " card kind", lorameta.row("Lighting.safetensors", path)["preview"], kind)
    found, embedded = lorameta.preview(path)
    check(label + " endpoint path", found, expected)
    check(label + " has no embedded payload", embedded is None, True)


def embedded_preview(label, path):
    check(label + " card kind", lorameta.row("Lighting.safetensors", path)["preview"], "image")
    found, embedded = lorameta.preview(path)
    check(label + " has no local path", found, None)
    check(label + " endpoint payload", embedded == (IMAGE, "image/png"), True)


with tempfile.TemporaryDirectory() as directory:
    for cm_info in (False, True):
        for embedded in (False, True):
            path = fresh(directory, embedded=embedded, cm_info=cm_info)
            companion = write(path.removesuffix(".safetensors") + ".preview.jpeg")
            local_preview(f"jpeg cm-info={cm_info} embedded={embedded}", path, companion)

    for extension, kind in (
        (".webp", "image"), (".png", "image"), (".jpg", "image"),
        (".gif", "image"), (".bmp", "image"), (".avif", "image"), (".jxl", "image"),
        (".mp4", "video"), (".webm", "video"), (".mov", "video"), (".mkv", "video"),
    ):
        path = fresh(directory)
        companion = write(path.removesuffix(".safetensors") + ".preview" + extension)
        local_preview(extension + " overrides embedded", path, companion, kind)

    path = fresh(directory, cm_info=True)
    companion = write(os.path.join(os.path.dirname(path), "LIGHTING.PREVIEW.JPEG"))
    local_preview("case-insensitive companion", path, companion)

    for size in (0, 1, lorameta.MIN_MEDIA_BYTES - 1):
        path = fresh(directory)
        write(path.removesuffix(".safetensors") + ".preview.jpeg", b"\0" * size)
        embedded_preview(f"placeholder of {size} bytes ignored", path)

    path = fresh(directory)
    companion = write(path.removesuffix(".safetensors") + ".preview.jpeg",
                      b"\0" * lorameta.MIN_MEDIA_BYTES)
    local_preview("minimum accepted media size", path, companion)

    path = fresh(directory)
    holder = os.path.dirname(path)
    write(os.path.join(holder, "StudioLighting.preview.jpeg"))
    write(os.path.join(holder, "Lighting_v2.preview.jpeg"))
    write(path + ".preview.jpeg")
    embedded_preview("other stems and extension-bearing name ignored", path)

    path = fresh(directory)
    os.makedirs(path.removesuffix(".safetensors") + ".preview.jpeg")
    embedded_preview("directory named as preview ignored", path)

    path = fresh(directory)
    embedded_preview("embedded fallback without companion", path)

    path = fresh(directory, embedded=False)
    companion = write(path.removesuffix(".safetensors") + ".jpeg")
    local_preview("bare-image fallback", path, companion)

    path = fresh(directory)
    sidecar = path + ".civitai"
    write_json(os.path.join(sidecar, "meta.json"), {"name": "Studio Lighting"})
    companion = write(os.path.join(sidecar, "thumbnails", "001.webp"))
    local_preview("CiviMeta fallback without explicit companion", path, companion)

    path = fresh(directory)
    stem = path.removesuffix(".safetensors")
    write(stem + ".mp4")
    companion = write(stem + ".preview.jpeg")
    local_preview("explicit jpeg wins over bare video", path, companion)

    path = fresh(directory)
    sidecar = path + ".civitai"
    write_json(os.path.join(sidecar, "meta.json"), {"name": "Studio Lighting"})
    gallery_preview = write(os.path.join(sidecar, "thumbnails", "001.webp"))
    gallery_clip = write(os.path.join(sidecar, "media", "001.mp4"))
    companion = write(path.removesuffix(".safetensors") + ".preview.jpeg")
    local_preview("explicit jpeg wins over CiviMeta thumbnail", path, companion)
    detail = lorameta.describe(path, deep=True)
    check("card priority preserves the described preview", detail["preview"]["path"], gallery_preview)
    check("card priority preserves the CiviMeta gallery",
          [item["path"] for item in detail["showcase"]], [gallery_clip])

    path = fresh(directory, embedded=False)
    write(path.removesuffix(".safetensors") + ".preview.jpeg", b"")
    check("no usable media gives no card kind",
          lorameta.row("Lighting.safetensors", path)["preview"], None)
    check("no usable media gives no endpoint source", lorameta.preview(path), (None, None))
