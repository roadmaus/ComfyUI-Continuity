"""What a reference means on LTX 2.5.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_ltx25_refs.py

This family used to refuse every attachment, because a citation reached Gemma as
a bare `<Picture 1>` with no picture behind it. It has a reference grammar now,
and it is Lightricks' own: the attached stills become the panels of one
composite sheet, the sheet goes in as a guide with the Ingredients IC-LoRA's
downscale factor, and the caption is written in two parts.

What is pinned here is everything about that which is *not* H3's, because the
whole risk of reusing the reference pipeline across two families is that one
family's answer quietly becomes the other's:

- **a citation is words**, `panel 1`, not `<Picture 1>` — and H3's is unchanged,
- **the caption is two-part**, `Reference sheet: … Generated video: …`,
- **only stills are taken**, and the refusal for the other two says what works,
- **the sheet is a grid**, numbered the way the panels were cited,
- **the cutout skips `scene` and `style`**, where the background is the citation,
- **a plate is one file and several citations**, and which of the two a family
  counts in is its own answer,
- **and the graph carries the IC-LoRA**, or refuses by name — and carries no
  matte at all any more, because the sheet is made in the picker.

Nothing is sampled. The sheet compositing is real tensors, because it is
arithmetic and getting a panel in the wrong cell is exactly the failure this
cannot see any other way.

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))

    sys.path.insert(0, os.path.dirname(ROOT))
    return nodes


try:
    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

import torch

importlib.import_module(PACKAGE)
cn = importlib.import_module(f"{PACKAGE}.creator.creator_node")
compiler = importlib.import_module(f"{PACKAGE}.creator.compile")
cutout = importlib.import_module(f"{PACKAGE}.creator.cutout")
grammar = importlib.import_module(f"{PACKAGE}.creator.families.grammar")
plate = importlib.import_module(f"{PACKAGE}.creator.plate")
sheet = importlib.import_module(f"{PACKAGE}.creator.families.ltx25.sheet")
ltx_grammar = importlib.import_module(f"{PACKAGE}.creator.families.ltx25.grammar")
ltx_declare = importlib.import_module(f"{PACKAGE}.creator.families.ltx25.declare")
h3_declare = importlib.import_module(f"{PACKAGE}.creator.families.h3.declare")

from harness import FAILURES, check, passed

LTX25 = ltx_declare.RULES

MODELS = {
    "dit": "ltx/ltx-2.5-22b-distilled.safetensors",
    "clip": "ltx/gemma4-12b-with-proj.safetensors",
    "vae": "ltx/ltx-2.5-video-vae-bf16.safetensors",
    "audio_vae": "ltx/ltx-2.5-audio-vae-bf16.safetensors",
    "ic_lora": "ltx/ltx-2.3-22b-ic-lora-ingredients.safetensors",
}

NODE_ID = "9"


def ref(handle, takes="full"):
    return {"handle": handle, "kind": "image", "role": "reference",
            "filename": f"{handle}.png", "takes": takes}


def plate_ref(handle, panels):
    """A plate as the picker attaches one: the composite, and what it is of.

    `panels` is `[(handle, takes)]`. The plate's own filename is the file the
    picker wrote; the panels' are the pictures it was laid out from, and those
    are the handles the prompt cites.
    """
    return {"handle": handle, "kind": "image", "role": "reference",
            "filename": f"_plates/{handle}.png",
            "panels": [{"handle": h, "filename": f"{h}.png", "takes": takes,
                        "cut": True}
                       for h, takes in panels]}


def request(prompt, assets=(), family="ltx25", **extra):
    return {"prompt": prompt, "assets": [dict(a) for a in assets],
            "loras": [], "duration_s": 5, **extra}


def compiled(prompt, assets=(), family="ltx25", **extra):
    return compiler.compile_request(request(prompt, assets, **extra), family=family)


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: expected an error mentioning {fragment!r}, got none")


# ---- the citation ------------------------------------------------------------
#
# The one thing that must not leak between the families. `<Picture 1>` is a form
# of H3's training — the tokenizer is presented the files in that order and the
# prompt addresses them by the ordinal each took — and Gemma has never seen the
# token sequence at all.

one = compiled("the woman from @img-1 walks in", [ref("img-1")])
check("a reference makes this a REF2V generation", one.mode, "REF2V")
check("...cited as words, not as an ordinal", one.labels["img-1"], "panel 1")
check("...and the body carries the words",
      "the woman from panel 1 walks in" in one.body, True)
check("...with no ordinal anywhere in the prompt",
      "<Picture" in one.prompt or "<Video" in one.prompt, False)

three = compiled("@img-1 @img-2 @img-3",
                 [plate_ref("plate-1", [("img-1", "full"), ("img-2", "full"),
                                        ("img-3", "full")])])
check("panels are numbered in layout order",
      [three.labels[h] for h in ("img-1", "img-2", "img-3")],
      ["panel 1", "panel 2", "panel 3"])

# H3 is untouched, which is the other half of the same check: the hook has a
# default and the default is what was there before it existed.
h3 = compiled("the woman from @img-1 walks in", [ref("img-1")], family="h3")
check("H3 still cites by ordinal", h3.labels["img-1"], "<Picture 1>")
check("...and still routes a citation to Ref2VA", h3.checkpoint, "ref2va")

# A frame is not a panel and is not an ordinal either: it is a guide the model is
# already looking at, so what the caption needs is which end of the shot it is.
framed = compiled(
    "it opens on @img-9",
    [{"handle": "img-9", "kind": "image", "role": "first_frame", "filename": "a.png"}])
check("a start frame is named as a frame", framed.labels["img-9"], "the first frame")
check("...and H3 still numbers it",
      compiled("@img-9", [{"handle": "img-9", "kind": "image",
                           "role": "first_frame", "filename": "a.png"}],
               family="h3").labels["img-9"],
      "<Picture 1>")


# ---- the two-part caption ----------------------------------------------------

check("the caption opens on the sheet",
      one.prompt.startswith(ltx_grammar.SHEET_LEAD), True)
check("...and the video half is announced",
      ltx_grammar.VIDEO_LEAD in one.prompt, True)
check("...with the sheet defining the panel the body cites",
      "panel 1 is" in one.prompt, True)
# A card with no references composes exactly the caption it did before any of
# this existed: one paragraph, no leads.
plain = compiled("a red room")
check("no references, no sheet", plain.prompt, "a red room")
check("...and no lead either", ltx_grammar.SHEET_LEAD in plain.prompt, False)

# The chip is what the scaffold has to go on, and it is a clause per panel.
chips = compiled("@img-1 and @img-2",
                 [plate_ref("plate-1", [("img-1", "person"),
                                        ("img-2", "object")])])
check("each chip becomes a clause, placed on the sheet",
      "panel 1 is the person left; panel 2 is the object right." in chips.prompt, True)
# ...and the default chip, which says only "this whole picture is a reference",
# falls back to where the panel is — the weakest true sentence available, and one
# the model can check against the sheet in front of it. Never nothing: a caption
# naming `panel 1` with nothing defining it is a label pointing at nothing.
check("an undescribed panel is placed",
      "panel 1 is top left; panel 2 is top right; panel 3 is bottom left."
      in three.prompt, True)

# A rewrite wins over the scaffold, which is the whole reason the sheet is a
# section rather than something `compose` builds for itself.
written = compiler.compile_request(
    request("@img-1 walks in", [ref("img-1")],
            refined={"sections": {"reference_sheet": "@img-1 is a woman in a red coat"}}),
    family="ltx25")
check("a refined sheet replaces the scaffold",
      "panel 1 is a woman in a red coat" in written.prompt, True)
check("...and is substituted like any other field",
      "@img-1" in written.prompt, False)


# ---- what may be attached ----------------------------------------------------

check("nine stills", ltx_grammar.GRAMMAR.max_images, 9)
check("...and nothing that is not a still",
      (ltx_grammar.GRAMMAR.max_videos, ltx_grammar.GRAMMAR.max_audios), (0, 0))

expect_error(
    "a reference video is refused by what works, not by counting to zero",
    lambda: compiled("@vid-1", [{"handle": "vid-1", "kind": "video",
                                 "role": "reference", "filename": "a.mp4"}]),
    "sheet of stills")
expect_error(
    "...and so is a reference sound",
    lambda: compiled("@aud-1", [{"handle": "aud-1", "kind": "audio",
                                 "role": "reference", "filename": "a.wav"}]),
    "sound lane")
# One image file, and it is the sheet. Several loose pictures would ask the
# render to lay out a composite nobody saw — the invisible compose this family
# removed — so the request is refused, naming the picker.
expect_error(
    "a second image file is refused: the sheet is laid out in the picker",
    lambda: compiled("@img-1 @img-2", [ref("img-1"), ref("img-2")]),
    "one reference image")


# ---- the sheet ---------------------------------------------------------------

check("the grid stays near square",
      [plate.grid(n) for n in (1, 2, 3, 4, 5, 6, 7, 8, 9)],
      [(1, 1), (2, 1), (2, 2), (2, 2), (3, 2), (3, 2), (3, 3), (3, 3), (3, 3)])

# Panel N of the caption is cell N of the grid, reading left to right and then
# down. Checked with a solid colour per panel, because "which cell did it land
# in" is not a thing a shape assertion can see.
colours = []
for index in range(4):
    picture = torch.zeros(1, 8, 8, 3)
    picture[..., 0] = (index + 1) / 4.0
    colours.append(picture)
laid = plate.compose(colours, 64, 64, 0.0)
check("the sheet is one picture at the canvas", tuple(laid.shape), (1, 64, 64, 3))
# 2x2 for four panels: the centre of each quadrant is that panel's own red.
corners = {"top left": (16, 16), "top right": (16, 48),
           "bottom left": (48, 16), "bottom right": (48, 48)}
# Rounded to two places: the fit is lanczos, which rings very slightly even over
# a flat colour, and what is being asked here is which cell a panel landed in.
check("panels fill the grid in reading order",
      [round(float(laid[0, y, x, 0]), 2) for y, x in corners.values()],
      [0.25, 0.5, 0.75, 1.0])

# A panel narrower than its cell is centred on the backdrop rather than stretched
# onto it — a reference is a picture somebody chose, and cropping or distorting
# one here would silently re-frame the thing being cited.
tall = torch.ones(1, 16, 4, 3)
boxed = plate.compose([tall], 32, 32, 0.0)
check("a panel keeps its aspect", tuple(boxed.shape), (1, 32, 32, 3))
check("...centred, with backdrop either side",
      (round(float(boxed[0, 16, 1, 0]), 3), round(float(boxed[0, 16, 16, 0]), 3)),
      (0.0, 1.0))

# An arranged panel goes where its rect says, not where its grid cell would be:
# one solid panel, told to sit in the bottom-right quarter of the canvas.
placed = plate.compose([colours[3]], 64, 64, 0.0, rects=[[0.5, 0.5, 0.5, 0.5]])
check("an arranged panel sits in its rect",
      (round(float(placed[0, 48, 48, 0]), 2), round(float(placed[0, 16, 16, 0]), 2)),
      (1.0, 0.0))
# Dragged half off the right edge: what fits is painted, the overhang is
# clipped, and nothing raises.
hung = plate.compose([colours[3]], 64, 64, 0.0, rects=[[0.75, 0.25, 0.5, 0.5]])
check("a panel may hang off the edge",
      (tuple(hung.shape), round(float(hung[0, 32, 60, 0]), 2)),
      ((1, 64, 64, 3), 1.0))

# The name is the content, layout and clicks included: the same panels arranged
# or clicked differently are a different file, while panels carrying neither
# hash exactly as they did before arranging existed — old plates keep their
# names. The stamp is faked: `key` is about the recipe, not the disk.
_stamp = plate.media.stamp
plate.media.stamp = lambda p: (p, 0, 0)
plain_key = plate.key([{"path": "a.png"}, {"path": "b.png"}], 0.0, 64, 64)
same_key = plate.key([{"path": "a.png", "rect": None, "points": []},
                      {"path": "b.png"}], 0.0, 64, 64)
moved_key = plate.key([{"path": "a.png", "rect": [0.1, 0.1, 0.5, 0.5]},
                       {"path": "b.png"}], 0.0, 64, 64)
click_key = plate.key([{"path": "a.png",
                        "points": [{"x": 0.5, "y": 0.5, "include": True}]},
                       {"path": "b.png"}], 0.0, 64, 64)
plate.media.stamp = _stamp
check("empty layout and clicks change nothing about the name",
      plain_key == same_key, True)
check("the arrangement is part of the plate's name", plain_key != moved_key, True)
check("the clicks are part of the plate's name", plain_key != click_key, True)

# An arranged panel is placed by where it actually sits, in the caption too:
# the rect's centre against thirds of the canvas, in the grid words.
check("a dragged panel is described where it was put",
      [sheet._placed(r) for r in ([0.6, 0.0, 0.4, 0.3], [0.0, 0.7, 0.3, 0.3],
                                  [0.35, 0.35, 0.3, 0.3])],
      ["top right", "bottom left", ""])

# The prose half is numbered off the same walk the labels came from, so a clause
# and a citation cannot drift apart.
plan = compiler.plan_references([ref_asset for ref_asset in three.ref_images], [], [],
                                ltx_grammar.GRAMMAR)
check("the sheet's clauses are the plan's labels",
      [step["label"] for step in plan], ["panel 1", "panel 2", "panel 3"])


# ---- the plate ---------------------------------------------------------------
#
# A plate is one file and several pictures, made when the pictures are picked.
# What has to hold is that the two families count it in different units, and both
# are right about their own encoder: LTX is handed the composite and addresses
# what is on it, so a panel is a citation; H3 is handed the composite as one
# `<Picture N>`, so the plate is the citation and its panels are named against it.

sheeted = compiled("@img-1 and @img-2",
                   [plate_ref("plate-1", [("img-1", "person"), ("img-2", "object")])])
check("a plate is one attached picture", len(sheeted.ref_images), 1)
check("...whose file is the composite", sheeted.ref_images[0].filename,
      "_plates/plate-1.png")
check("...and whose panels are what the prompt cites",
      [sheeted.labels[h] for h in ("img-1", "img-2")], ["panel 1", "panel 2"])
check("...substituted into the body",
      "panel 1 and panel 2" in sheeted.body, True)
check("...and defined on the sheet",
      "panel 1 is the person left; panel 2 is the object right." in sheeted.prompt,
      True)

# A panel the user dragged carries its rect through the blob, and the caption
# defines it by where it landed rather than by the grid cell it left.
moved = compiled("@img-1 and @img-2",
                 [{"handle": "plate-1", "kind": "image", "role": "reference",
                   "filename": "_plates/plate-1.png",
                   "panels": [
                       {"handle": "img-1", "filename": "img-1.png",
                        "takes": "person", "cut": True,
                        "rect": [0.6, 0.0, 0.4, 0.4]},
                       {"handle": "img-2", "filename": "img-2.png",
                        "takes": "object", "cut": True}]}])
check("an arranged panel is defined where it was put",
      "panel 1 is the person top right; panel 2 is the object right."
      in moved.prompt, True)

# H3 reads the same blob and answers differently, which is the whole point of the
# seam. One picture is presented, so one ordinal is spent — and the panels are
# named against it rather than given ordinals of pictures nobody was shown.
h3_plate = compiled("@img-1 and @img-2",
                    [plate_ref("plate-1", [("img-1", "person"), ("img-2", "object")])],
                    family="h3")
check("H3 spends one ordinal on the whole plate",
      h3_plate.labels["plate-1"], "<Picture 1>")
check("...and names its panels against it",
      [h3_plate.labels[h] for h in ("img-1", "img-2")],
      ["panel 1 of <Picture 1>", "panel 2 of <Picture 1>"])
# A plate of one panel is its panel: there is no inside to point at, and
# "panel 1 of <Picture 1>" would send the model looking for a cell that is the
# whole frame. This is the H3 shape of a picture cut out in the picker.
lone = compiled("@img-1", [plate_ref("plate-1", [("img-1", "person")])], family="h3")
check("a one-panel plate is cited as the picture it is",
      lone.labels["img-1"], "<Picture 1>")
check("...and so is the plate itself", lone.labels["plate-1"], "<Picture 1>")

check("which family does which is declared, not branched on",
      (ltx_grammar.GRAMMAR.cites_panels, grammar.of("h3").cites_panels),
      (True, False))

# The cap counts panels. Counting attachments would count to one and let a sheet
# of twelve through a limit that is about how many panels stay legible.
expect_error(
    "a tenth panel is refused by the number",
    lambda: compiled("@img-1",
                     [plate_ref("plate-1", [(f"img-{n}", "full") for n in range(1, 11)])]),
    "at most 9 reference images")

# A panel handle is a handle: a blob whose plate holds @img-1 while a loose
# attachment is also @img-1 is a prompt with two answers, and it is refused
# rather than resolved in favour of whichever was read first.
expect_error(
    "a panel cannot shadow an attachment",
    lambda: compiled("@img-1", [ref("img-1"), plate_ref("plate-1", [("img-1", "full")])]),
    "duplicate asset handle")

# The plate's identity is its content. Same pictures, same flags, same canvas ->
# the same filename, which is what makes re-picking a selection you already had
# cost a stat instead of a matte.
_stamps = {}
plate.media.stamp = lambda name: _stamps.setdefault(name, (name, 1, 2))
same = plate.key([{"path": "a.png", "cut": True}], 0.0, 1280, 704)
check("a plate's name is its content",
      same, plate.key([{"path": "a.png", "cut": True}], 0.0, 1280, 704))
check("...and the cutout flag is part of it",
      same == plate.key([{"path": "a.png", "cut": False}], 0.0, 1280, 704), False)
check("...as is the backdrop the panels sit on",
      same == plate.key([{"path": "a.png", "cut": True}], 0.5, 1280, 704), False)


# ---- the cutout --------------------------------------------------------------
#
# Now a question the picker asks about one picture rather than a filter a render
# pass applies. The list is the thing that must not drift: `state.js` keeps its
# own copy for the scissors, and both are about the same two chips.

check("a person is cut out", cutout.wanted("person"), True)
check("...and so is the default chip", cutout.wanted("full"), True)
check("a scene keeps its background", cutout.wanted("scene"), False)
check("...and so does a style", cutout.wanted("style"), False)

# The two families composite onto different fields, and that is a statement about
# each one's training rather than a taste: LTX's sheets are black, and H3 has no
# sheet at all — mid grey, because white clips the light end of skin and hair
# into the field it is meant to be distinct from.
check("LTX composites onto black", ltx_declare.REF_BACKDROP, 0.0)
check("H3 composites onto mid grey", h3_declare.REF_BACKDROP, 0.5)
check("LTX cuts out by default", ltx_declare.CUTOUT_DEFAULT, True)
check("...and H3 does not, so no saved workflow moves",
      h3_declare.CUTOUT_DEFAULT, False)

# The compositing itself: alpha 1 keeps the picture, alpha 0 is the field.
white = torch.ones(1, 2, 2, 3)
alpha = torch.tensor([[[1.0, 0.0], [0.5, 0.0]]])
over = cutout.over(white, alpha, 0.0)
check("the matte composites straight",
      [round(float(v), 3) for v in over[0, :, :, 0].flatten()], [1.0, 0.0, 0.5, 0.0])


# ---- the graph ---------------------------------------------------------------

def piece(segments, **overrides):
    data = {
        "version": 2, "family": "ltx25", "prompt": "",
        "aspect": "16:9", "short_edge": LTX25.native_short_edge,
        "models": dict(MODELS), "segments": segments,
    }
    data.update(overrides)
    return json.dumps(data)


def build(data):
    from comfy_api.latest import io as comfy_io

    previous = cn.MiniMaxH3Creator.hidden
    cn.MiniMaxH3Creator.hidden = comfy_io.HiddenHolder(
        unique_id=NODE_ID, prompt=None, extra_pnginfo=None, dynprompt=None,
        auth_token_comfy_org=None, api_key_comfy_org=None)
    try:
        return cn.MiniMaxH3Creator.execute(
            creator_data=data, seed=100, steps=20, cfg=1.0,
            sampler_name="res_multistep", scheduler="simple")
    finally:
        cn.MiniMaxH3Creator.hidden = previous


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


cited = [request("the woman from @img-1 walks in", [ref("img-1")])]
kinds = by_class(build(piece(cited)).expand)
segment = kinds["MiniMaxLTX25Segment"][0][1]
check("the segment is handed the Ingredients IC-LoRA by name",
      segment.get("ic_lora"), MODELS["ic_lora"])

# **No matte anywhere in the graph, on any card.** A cut-out reference is a file
# the picker already wrote, so a render has nothing left to cut — and a graph
# that still loaded BiRefNet would be loading a model to do a pass that no longer
# exists.
check("a citing card loads no background remover",
      "LoadBackgroundRemovalModel" in kinds, False)
check("...and its segment node carries no cutout input", "cutout" in segment, False)

# The IC-LoRA is a pass rather than a component: a card that cites nothing must
# not load it, and its segment node must keep the inputs it had before any of
# this existed — that string is its cache key.
bare = by_class(build(piece([request("a red room")])).expand)
check("a card with no references gets no IC-LoRA",
      "ic_lora" in bare["MiniMaxLTX25Segment"][0][1], False)

# The one file still refused by name, before a loader is built.
missing_lora = dict(MODELS)
missing_lora.pop("ic_lora")
expect_error("a citation with no IC-LoRA is refused by name",
             lambda: build(piece(cited, models=missing_lora)),
             "Ingredients IC-LoRA")

# H3's graph does not move.
h3_graph = by_class(build(json.dumps({
    "version": 2, "family": "h3", "prompt": "", "aspect": "16:9",
    "short_edge": h3_declare.RULES.native_short_edge,
    "models": {"ref2va": "h3/ref2va.safetensors", "clip": "h3/clip.safetensors",
               "vae": "h3/vae.safetensors", "audio_vae": "h3/audio.safetensors"},
    "segments": [request("the woman from @img-1 walks in", [ref("img-1")])],
})).expand)
check("an H3 reference card loads no matte",
      "LoadBackgroundRemovalModel" in h3_graph, False)
check("...and its segment node carries no cutout input",
      "cutout" in h3_graph["MiniMaxH3TimelineSegment"][0][1], False)

passed("a reference on LTX 2.5 is a panel of a sheet, and H3's is still an ordinal")
