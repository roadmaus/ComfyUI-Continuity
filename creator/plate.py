"""Plates: the picture the picker makes out of the pictures you chose.

A reference used to be a file plus two promises about what would happen to it
later — the piece's `cut out` pill said the subject would be lifted off its
background at render time, and LTX 2.5's `sheet.compose` said the attachments
would be laid out as one composite before they were encoded. Both promises were
kept, and neither was ever *shown*. You attached three photographs, saw three
photographs on the card, and found out what the model had actually been handed
by reading a log line after a two-minute render.

A plate is that same picture, made at the moment you pick the files and written
to disk. It is a real image in the input folder: it has a thumbnail, it opens in
the picker, it can be thrown away, and what the card carries is it rather than a
description of it. Cutting out and laying out stop being render-time behaviour
and become the two things this module does, once, where you can see the result.

**One panel is a cutout; several are a sheet.** With one picture there is no
layout to make, so the plate is that picture with its background lifted, at its
own resolution — which is the whole of what a cutout buys on a family that
encodes its references one at a time (H3). With two or more the panels are
fitted into a near-square grid on the family's backdrop, which is the composite
sheet Lightricks' `Ingredients` adapter reads. Same route, same file, and the
difference is how many files you handed it.

**The name is the content.** A plate's filename is a hash of the panels, their
cutout flags and clicks, their layout, the backdrop and the canvas, so
re-accepting the same selection finds the file already there and returns it
without a second matte.

**Nothing is written until the sheet is accepted.** The editor previews by
compositing in the browser from per-panel cutouts served straight out of memory
(`server_routes.cut_panel`), and `build` — the only writer — runs when Accept
is pressed. It used to run on every click of the grid, which filled `_plates/`
with one near-identical composite per glance and made the input folder a
midden of discarded previews.

**A panel may say where it sits.** `rect` is `[x, y, w, h]` as fractions of the
canvas — the editor's arrangement — and a panel without one takes its cell from
the near-square grid, which is what every sheet was before arranging existed
and still is when Add is pressed without opening the editor.

The matte itself is `creator/cutout.py`: BiRefNet whole-subject by default, and
SAM3 point-prompted where the panel carries clicks.
"""

import hashlib
import json
import logging
import math
import os

import folder_paths

from . import cutout, media

# Where plates are written, as a subfolder of the input directory. Its own shelf
# rather than loose among the uploads: a plate is a derived file and the picker's
# grid is somewhere you look for the picture you took, so mixing them would
# mean every sheet you ever built came back as a candidate panel for the next
# one. The leading underscore keeps it at the top of an alphabetical shelf list.
PLATE_DIR = "_plates"

# The matte models, held across requests. Loading BiRefNet is seconds, SAM3 is
# more, and a cutout is retaken on every click in the editor, so a reload per
# click would make the live preview unusable. One entry per kind, keyed by
# filename: the weights control can be changed mid-session, and the second
# model has to actually load when it is.
_MODELS = {"cutout": {"name": None, "model": None},
           "segment": {"name": None, "model": None}}


def _keep(kind, name, load):
    held = _MODELS[kind]
    if held["name"] == name and held["model"] is not None:
        return held["model"]
    held.update(name=name, model=load())
    return held["model"]


def _model(name):
    """The loaded background-removal model named by the weights control.

    Through core's registry node for the reason `cutout.matte` goes through it:
    an install without background removal has to fail here, naming the pass,
    rather than fail on an attribute somewhere inside a matte.
    """
    if not name:
        raise ValueError(
            "Cutting a picture out of its background needs a background-removal "
            "model. Pick one under the node's weights control "
            "(models/background_removal)."
        )
    import nodes

    loader = nodes.NODE_CLASS_MAPPINGS.get("LoadBackgroundRemovalModel")
    if loader is None:
        raise ValueError(
            "Cutting a picture out of its background needs core's "
            "'LoadBackgroundRemovalModel' node, which this ComfyUI does not "
            "have. Update it, or build the plate without cutting anything out."
        )
    return _keep("cutout", name, lambda: loader.execute(name)[0])


def _segment_model(name):
    """The loaded SAM3 checkpoint named by the weights control.

    SAM3 is a fused checkpoint — model and text encoder in one file — so it is
    loaded the way H3's face pass loads the same file
    (`families/h3/facepass._detector`): `comfy.sd` over models/checkpoints,
    rather than a split loader node. On H3 this *is* the face detector's slot,
    so one download answers both "where is the face" and "what did you click".
    The text encoder is left unloaded: the point path needs none.
    """
    if not name:
        raise ValueError(
            "Picking a subject by clicking on it needs a SAM 3 checkpoint. "
            "Pick one under the node's weights control (models/checkpoints)."
        )

    def load():
        import comfy.sd

        path = folder_paths.get_full_path_or_raise("checkpoints", name)
        return comfy.sd.load_checkpoint_guess_config(
            path, output_vae=False, output_clip=False)[0]

    return _keep("segment", name, load)


def cut_panel(panel, models):
    """One panel, loaded and matted the way it asked. -> (image, alpha or None).

    `panel` is one `{"path", "cut", "points"?}` dict; `models` is
    `{"cutout": name, "segment": name}` off the piece's weights. Clicks pick the
    model: a panel with points is a SAM3 question ("this thing, not that one"),
    a panel without is BiRefNet's ("the subject"). Alpha is None on a panel
    used whole, which is what lets the preview route hand the browser the
    original file untouched.
    """
    image = media.load_image(panel["path"])
    if not panel.get("cut"):
        return image, None
    points = panel.get("points") or []
    if points:
        return image, cutout.matte_points(
            _segment_model(models.get("segment")), image, points)
    return image, cutout.matte(_model(models.get("cutout")), image)


def grid(count):
    """How many columns and rows `count` panels are laid out in. -> (cols, rows).

    Near-square by construction — 1, 2 across, 2x2, 3x2, 3x3 — which is what
    keeps a panel legible on a wide canvas and on a tall one alike: three panels
    in one row across 16:9 gives each a 1.9:1 letterbox slot most of which is
    backdrop, and the same three in a 2x2 give them nearly the whole cell.

    The walk order is load-bearing rather than cosmetic: `panel 3` in the caption
    has to be the third cell of this grid, and both the numbering here and the
    numbering in `compile.plan_references` come off the same order — the order
    the panels were picked.
    """
    count = max(1, int(count))
    cols = math.ceil(math.sqrt(count))
    return cols, math.ceil(count / cols)


def compose(images, width, height, backdrop, rects=None):
    """The panels, laid out as one picture. -> an IMAGE tensor [1, H, W, 3].

    `images` are the panels in order, each already cut out onto the backdrop
    where the picker asked for that — so this only ever lays out, and the two
    steps stay separable.

    `rects` — parallel to `images`, each `[x, y, w, h]` fractions of the canvas
    or None — is the editor's arrangement. A panel with a rect is fitted into
    it; one without takes its grid cell, so an untouched sheet lays out exactly
    as it always has. Later panels paint over earlier ones, which makes the
    layout order a z-order the editor can rely on.

    **Each panel is fitted, never cropped.** A reference is a picture the user
    chose; cropping one here would silently decide the framing of the thing being
    cited. So a panel is scaled to fit its cell whole and centred, and what is
    left over is the backdrop.

    The sheet is built at the generation's own canvas. Not because the guide is
    used at that size — `LTXVAddGuide.encode` resamples it to the latent's pixel
    size divided by the IC-LoRA's downscale factor, whatever it is handed — but
    because building at the canvas is the one choice that needs no justification
    later: the panels are downsampled once, by the node, from a sheet whose shape
    already matches what it is being resampled into.
    """
    import comfy.utils
    import torch

    cols, rows = grid(len(images))
    cell_w, cell_h = max(1, width // cols), max(1, height // rows)
    sheet = torch.full((1, height, width, 3), float(backdrop), dtype=torch.float32)

    for index, image in enumerate(images):
        # One frame of it. A still is [1, H, W, 3] already; a caller that hands
        # in several takes the first, which is the panel a moving reference
        # would contribute if the caps ever allowed one.
        frame = image[:1]
        source_h, source_w = frame.shape[1], frame.shape[2]

        rect = (rects or [None] * len(images))[index]
        if rect:
            x, y, w, h = (float(v) for v in rect)
            box_w = max(1, round(w * width))
            box_h = max(1, round(h * height))
            box_left, box_top = round(x * width), round(y * height)
        else:
            row, col = divmod(index, cols)
            box_w, box_h = cell_w, cell_h
            box_left, box_top = col * cell_w, row * cell_h

        # Contain, not cover: the whole picture, scaled until one axis fills.
        scale = min(box_w / source_w, box_h / source_h)
        fit_w, fit_h = max(1, round(source_w * scale)), max(1, round(source_h * scale))
        fitted = comfy.utils.common_upscale(
            frame.movedim(-1, 1), fit_w, fit_h, "lanczos", "disabled").movedim(1, -1)

        top = box_top + (box_h - fit_h) // 2
        left = box_left + (box_w - fit_w) // 2
        # An arranged panel may hang over the edge; what shows is what fits.
        src_top, src_left = max(0, -top), max(0, -left)
        top, left = max(0, top), max(0, left)
        show_h = min(fit_h - src_top, height - top)
        show_w = min(fit_w - src_left, width - left)
        if show_h <= 0 or show_w <= 0:
            continue
        sheet[:, top:top + show_h, left:left + show_w, :] = fitted[
            :, src_top:src_top + show_h, src_left:src_left + show_w, :].to(sheet.dtype)
    return sheet


def key(panels, backdrop, width, height):
    """The plate's identity: everything that changes what the file looks like.

    The panels' *stamps* rather than their names (`media.stamp` — path, mtime,
    size), so replacing a source picture in place under the same filename builds
    a new plate instead of finding the old one still sitting there. Same
    argument as the latent cache's, said about a composite.
    """
    material = []
    for panel in panels:
        path, mtime, size = media.stamp(panel["path"])
        entry = [os.path.basename(path), mtime, size, bool(panel.get("cut"))]
        # Layout and clicks change the pixels, so they are the name's business
        # too — appended only when present, so every plate hashed before they
        # existed keeps the name it was written under.
        if panel.get("rect"):
            entry.append([round(float(v), 4) for v in panel["rect"]])
        if panel.get("points"):
            entry.append([[round(float(p["x"]), 4), round(float(p["y"]), 4),
                           bool(p.get("include", True))] for p in panel["points"]])
        material.append(entry)
    material.append([round(float(backdrop), 4), int(width), int(height)])
    blob = json.dumps(material, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


def _write(image, relative, panels):
    """One IMAGE tensor [1, H, W, 3] -> a PNG under input/`PLATE_DIR`.

    The panel list rides along in a `minimax_plate` text chunk. Nothing reads it
    back today — the card carries its own copy — and it is written anyway
    because a plate outlives the card that made it: a file in the input folder
    that cannot say which photographs it was built from is a picture nobody can
    rebuild or trust six months later.
    """
    import numpy as np
    from PIL import Image, PngImagePlugin

    path = os.path.join(folder_paths.get_input_directory(), relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    array = image[0].clamp(0.0, 1.0).mul(255.0).round().to("cpu").numpy().astype(np.uint8)
    info = PngImagePlugin.PngInfo()
    info.add_text("minimax_plate", json.dumps(panels, separators=(",", ":")))
    Image.fromarray(array, "RGB").save(path, pnginfo=info, compress_level=4)
    return path


def build(panels, models, backdrop, width, height):
    """The plate for `panels`. -> `{"path", "width", "height", "cols", "rows"}`.

    `panels` is `[{"path": str, "cut": bool, "rect"?: [x,y,w,h],
    "points"?: [{"x","y","include"}]}, ...]` in the order they are to be laid
    out — the picker's click order, which is also the order the panel numbering
    in the prompt comes off (`compile.plan_references`). `models` is the matte
    weights, `{"cutout": name, "segment": name}`.

    This is the only writer, and it runs when the sheet is accepted — never
    while it is merely being looked at. Returns the existing file where the
    same selection has already been built, so re-accepting an unchanged sheet
    costs a `stat`.
    """
    if not panels:
        raise ValueError("a plate needs at least one picture")

    name = f"plate-{key(panels, backdrop, width, height)}.png"
    relative = f"{PLATE_DIR}/{name}"
    existing = os.path.join(folder_paths.get_input_directory(), relative)
    if os.path.isfile(existing):
        from PIL import Image

        with Image.open(existing) as img:
            size = img.size
        cols, rows = grid(len(panels))
        return {"path": relative, "width": size[0], "height": size[1],
                "cols": cols, "rows": rows, "panels": len(panels)}

    images = []
    for panel in panels:
        image, alpha = cut_panel(panel, models)
        if alpha is not None:
            image = cutout.over(image, alpha, backdrop)
            logging.info("[MiniMax] cut %s out of its background onto %.2f grey",
                         os.path.basename(str(panel["path"])), float(backdrop))
        images.append(image)

    # One picture, unarranged, is a cutout and keeps its own resolution;
    # several — or one somebody placed — are a sheet and are fitted to the
    # canvas. See the module docstring.
    if len(images) == 1 and not panels[0].get("rect"):
        composed, cols, rows = images[0], 1, 1
    else:
        composed = compose(images, int(width), int(height), float(backdrop),
                           rects=[panel.get("rect") for panel in panels])
        cols, rows = grid(len(images))

    _write(composed, relative, panels)
    return {"path": relative, "width": int(composed.shape[2]),
            "height": int(composed.shape[1]), "cols": cols, "rows": rows,
            "panels": len(panels)}
