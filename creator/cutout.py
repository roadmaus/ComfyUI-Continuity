"""Reference cutouts: the subject lifted off its background onto a flat field.

A reference image is a photograph, and a photograph is mostly not the thing it
is a reference *of*. Cite somebody's portrait for their face and the model is
also handed the room they stood in, the light that fell on them and the palette
of the wall behind — all of which condition the render exactly as hard as the
face does. That is the leak `Asset.takes` has always named and never fixed:
saying "them from @img-1" narrowed the *prose* (H3's `retention_analysis`) while
the tensor stayed the whole picture.

This is the fix, and it is one forward pass. Core ships BiRefNet under
`models/background_removal` — `LoadBackgroundRemovalModel` and `RemoveBackground`
in `comfy_extras/nodes_bg_removal.py` — which is *salient object* matting: no
prompt, no box, no click, a soft alpha at the input's own resolution. Hand it a
picture of a person and it returns the person. That is the whole interface, and
it is the default for exactly that reason: a picture with one subject needs
nobody to say which.

A picture with *two* subjects does. That is what `matte_points` is for: SAM3
(`SAM3_Detect`, `comfy_extras/nodes_sam3.py`) is promptable segmentation, and
its point-prompt path — click the thing you mean, click again on what you
don't — needs no text and no CLIP encoder, just pixel coordinates. Its masks
are hard where BiRefNet's are soft, and a hard edge against a flat field is a
halo through hair, so the mask is feathered a couple of pixels before it
composites. The sheet editor is where the clicks happen; a panel with no
clicks stays on BiRefNet.

**This runs in the picker, not in a render.** It used to be a pass: a toggle on
the piece, a background-removal model wired into the segment node, and a matte
taken every time the graph ran. What that produced was invisible until the
render finished, and it was taken again on every render of the same file. Now
the picker calls this once, `creator/plate.py` writes the result into the input
folder, and what the card carries is that picture — so what the model gets
handed is what you were looking at when you queued it.

**The field is the family's, because it is a statement about training.** LTX 2.5
composites its cut-outs into an Ingredients reference sheet, which Lightricks
describes as panels "on a black background" — so black, exactly. H3 has no sheet;
its references are encoded one at a time, and what a cutout buys there is the
absence of a background rather than a layout. Mid grey for that: white clips the
light end of skin, hair and pale clothing into the field it is supposed to be
distinct from, and the VAE encodes the clipping. `declare.REF_BACKDROP` is where
each family says which.

**What is never cut out**: a reference whose chip is `scene` or `style`. There
the background *is* the reference — the palette, the light, the location — and
lifting the subject off it deletes the thing being cited. `wanted` is that rule,
and it is now advice the picker takes rather than a filter a pass applies: the
scissors on such a picture are switched off and say why.
"""

import logging

# The chips a cutout would destroy the meaning of. `scene` cites where a picture
# was taken and `style` cites how it looks; both live in exactly the pixels a
# matte throws away, so the toggle does not reach them. Every other chip —
# `full` included, which is the default and means "this whole picture is a
# reference to something" — is a subject the render wants and a background it
# does not.
KEEPS_BACKGROUND = ("scene", "style")


def wanted(takes):
    """Whether a picture chipped `takes` is one a cutout would improve. -> bool.

    Asked per picture rather than per request because the chips differ across
    one card's attachments, and a strip that cites a character and a location
    wants the first lifted and the second left alone. The frontend asks the same
    question of the same list (`web/creator/state.js`), which is why the
    vocabulary above is the only place either side keeps the answer.
    """
    return str(takes or "full") not in KEEPS_BACKGROUND


def matte(model, image):
    """The foreground alpha of `image`. -> float tensor [B, H, W] in 0..1.

    Through core's registry node rather than `model.encode_image` directly, for
    the reason `families/ltx25/segment.py` looks its LTX nodes up by key: the
    method is core's internals and the node id is core's contract. An install
    without it fails here, naming the pass, instead of failing on an attribute.
    """
    import nodes

    node = nodes.NODE_CLASS_MAPPINGS.get("RemoveBackground")
    if node is None:
        raise ValueError(
            "Cutting a reference out of its background needs core's "
            "'RemoveBackground' node, which this ComfyUI does not have. Update "
            "it, or switch the piece's 'cut out references' toggle off."
        )
    return node.execute(model, image)[0]


def matte_points(model, image, points):
    """The alpha of whatever `points` say, via SAM3. -> float tensor [B, H, W].

    `points` is `[{"x": frac, "y": frac, "include": bool}, ...]` — fractions of
    the picture, not pixels, because that is how the editor stores a click (it
    survives every resize of the preview) — converted to the pixel coordinates
    `SAM3_Detect`'s point path reads here, against this image's own size.

    The mask comes back hard and goes out feathered: a box blur of a few pixels,
    scaled to the picture, so the composite blends where BiRefNet's soft matte
    would have. Without it every SAM cutout carried a razor edge that reads as a
    sticker on the sheet.
    """
    import json as _json

    import nodes
    import torch

    node = nodes.NODE_CLASS_MAPPINGS.get("SAM3_Detect")
    if node is None:
        raise ValueError(
            "Picking a subject by clicking on it needs core's 'SAM3_Detect' "
            "node, which this ComfyUI does not have. Update it, or use the "
            "scissors without clicks (BiRefNet)."
        )
    height, width = int(image.shape[1]), int(image.shape[2])
    positive = [{"x": int(round(p["x"] * (width - 1))), "y": int(round(p["y"] * (height - 1)))}
                for p in points if p.get("include", True)]
    negative = [{"x": int(round(p["x"] * (width - 1))), "y": int(round(p["y"] * (height - 1)))}
                for p in points if not p.get("include", True)]
    if not positive:
        raise ValueError("clicking a subject out needs at least one point on it")
    mask = node.execute(model, image,
                        positive_coords=_json.dumps(positive),
                        negative_coords=_json.dumps(negative) if negative else None)[0]
    mask = mask.to(torch.float32)

    # Feather: two passes of a small box blur, radius scaled to the picture so a
    # 4K portrait and a 512 thumbnail soften by the same visible amount.
    radius = max(1, round(min(width, height) / 400))
    kernel = 2 * radius + 1
    soft = mask.unsqueeze(1)
    for _ in range(2):
        soft = torch.nn.functional.avg_pool2d(
            soft, kernel_size=kernel, stride=1, padding=radius,
            count_include_pad=False)
    return soft.squeeze(1).clamp(0.0, 1.0)


def over(image, alpha, backdrop):
    """`image` composited onto a flat `backdrop` through `alpha`.

    Straight alpha-over, at the picture's own resolution: the matte is soft at
    the edges and the point of a soft matte is that the blend happens in the
    pixels rather than at a threshold. `backdrop` is one grey level rather than
    a colour because both families want a neutral field and a tint would be a
    cast every reference in the piece shared.
    """
    alpha = alpha.unsqueeze(-1).to(image.dtype).to(image.device)
    return image * alpha + float(backdrop) * (1.0 - alpha)


def apply(model, image, backdrop, what=""):
    """One reference, cut out. -> the composited image tensor.

    `what` names the asset in the log line. Worth logging at all because a
    cutout is invisible in the finished render when it works and indistinguishable
    from a bad reference when the matte is wrong — so the log is where "did this
    picture get cut out" is answerable without re-running anything.
    """
    out = over(image, matte(model, image), backdrop)
    logging.info("[MiniMax] cut %s out of its background onto %.2f grey",
                 what or "a reference", float(backdrop))
    return out
