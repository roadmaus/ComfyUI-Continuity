"""What the render loop wires for a storyboard (issue #43).

Boots the real ComfyUI like `test_timeline_graph.py` — the thing worth checking
is the graph: which passes a segment's sheet is read off, on which road, at how
many cells each, and that a strip without one builds the graph it always did.
Nothing is sampled.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_storyboard_graph.py
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

importlib.import_module(PACKAGE)
cn = importlib.import_module(f"{PACKAGE}.creator.creator_node")
tl = importlib.import_module(f"{PACKAGE}.creator.timeline")
spill = importlib.import_module(f"{PACKAGE}.creator.spill")

from harness import FAILURES, check, passed

MODELS = {
    "fl2va": "h3/fl2va.safetensors",
    "ref2va": "h3/ref2va.safetensors",
    "clip": "h3/text_encoder.safetensors",
    "vae": "h3/video_vae.safetensors",
    "audio_vae": "h3/audio_vae.safetensors",
}


def build(**fields):
    from comfy_api.latest import io as comfy_io

    data = json.dumps({"version": 2, "models": MODELS, "aspect": "16:9",
                       "short_edge": 768, **fields})
    previous = cn.MiniMaxH3Timeline.hidden
    cn.MiniMaxH3Timeline.hidden = comfy_io.HiddenHolder(
        unique_id="12", prompt=None, extra_pnginfo=None, dynprompt=None,
        auth_token_comfy_org=None, api_key_comfy_org=None)
    try:
        return cn.MiniMaxH3Timeline.execute(
            timeline_data=data, seed=100, steps=20, cfg=6.0,
            sampler_name="euler", scheduler="simple").expand
    finally:
        cn.MiniMaxH3Timeline.hidden = previous


def by_class(graph):
    out = {}
    for node_id, node in graph.items():
        out.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    return out


def segments(graph, prompts):
    keyed = {json.loads(i["segment_data"])["request"]["prompt"]: (node_id, i)
             for node_id, i in by_class(graph).get("MiniMaxH3TimelineSegment", [])}
    return [keyed[p] for p in prompts]


def sheet_of(graph, inputs):
    """A segment's storyboard node -> [(reader class, count, whose pass)]."""
    link = inputs.get("storyboard_image")
    if link is None:
        return None
    node = graph[link[0]]
    if node["class_type"] != "ContinuityStoryboard":
        return f"<ContinuityStoryboard expected, found {node['class_type']}>"
    cells = []
    for slot in range(1, 10):
        frames = node["inputs"].get(f"frames_{slot}")
        if frames is None:
            continue
        reader = graph[frames[0]]
        if reader["class_type"] == "MiniMaxH3PassFrames":
            # pass frames -> reel -> sampler -> segment: whose pass this is
            reel = graph[reader["inputs"]["source"][0]]
            sampler = graph[reel["inputs"]["samples"][0]]
            model = sampler["inputs"]["model"]
            # The model may go through a patcher or two on its way; walk to
            # the segment node.
            seen = model
            while graph[seen[0]]["class_type"] != "MiniMaxH3TimelineSegment":
                seen = graph[seen[0]]["inputs"]["model"]
            whose = json.loads(graph[seen[0]]["inputs"]["segment_data"])["request"]["prompt"]
        else:
            whose = json.loads(reader["inputs"]["clip_data"])["filename"]
        cells.append((reader["class_type"], reader["inputs"]["count"],
                      reader["inputs"]["at"], whose))
    return (node["inputs"]["width"], node["inputs"]["height"]), cells


three = [{"prompt": "one", "duration_s": 5},
         {"prompt": "two", "duration_s": 4},
         {"prompt": "three", "duration_s": 7}]

# Off: the graph it always built.
plain = build(segments=three)
check("no storyboard, no sheet node", "ContinuityStoryboard" in by_class(plain), False)
check("...and no reader spread over anything",
      [i.get("at") for _, i in by_class(plain).get("MiniMaxH3PassFrames", [])], [])
check("...and no socket on any segment",
      [("storyboard_image" in i) for _, i in segments(plain, ["one", "two", "three"])],
      [False, False, False])

# 'all': each card is shown the passes before it, at their allotted cells.
shown = build(segments=three, storyboard="all")
one, two, three_ = segments(shown, ["one", "two", "three"])
check("the first card is shown nothing", sheet_of(shown, one[1]), None)
check("the second is shown the first, nine cells, off its spill",
      sheet_of(shown, two[1]),
      ((1344, 768), [("MiniMaxH3PassFrames", 9, "spread", "one")]))
check("the third is shown both, by duration, in play order",
      sheet_of(shown, three_[1]),
      ((1344, 768), [("MiniMaxH3PassFrames", 5, "spread", "one"),
                     ("MiniMaxH3PassFrames", 4, "spread", "two")]))
check("the sheet is on the payload, so it is in the cache key",
      json.loads(three_[1]["segment_data"]).get("storyboard"), {"cells": [[0, 5], [1, 4]]})
check("a shown card runs on ref2va", "model_ref2va" in two[1], True)
check("...with the video VAE wired for the encode", "vae" in two[1], True)

# A seam's own reader is untouched: it still reads the tail, no `at` written.
seamed = build(segments=[three[0], {**three[1], "continue": True}], storyboard="previous")
readers = by_class(seamed)["MiniMaxH3PassFrames"]
check("the seam reads the tail as it always did, the sheet reads across",
      sorted((i.get("at", "<absent>"), i.get("count", 1)) for _, i in readers),
      [("<absent>", 1), ("spread", 9)])
check("both hang off the same pass",
      len({i["source"][0] for _, i in readers}), 1)

# Supplied footage is a source too, off the clip's own window.
with_clip = build(segments=[
    three[0],
    {"kind": "clip", "filename": "insert.mp4", "duration_s": 3.0,
     "width": 1920, "height": 1080},
    three[2]], storyboard="all")
last = segments(with_clip, ["three"])[0]
check("a cut-in clip fills its cells from its file",
      sheet_of(with_clip, last[1]),
      ((1344, 768), [("MiniMaxH3PassFrames", 5, "spread", "one"),
                     ("MiniMaxH3ClipFrames", 4, "spread", "insert.mp4")]))

# The sheet rides the refine's segment node too: the second pass re-encodes
# the same references at the target canvas.
refined = build(segments=three[:2], storyboard="previous", short_edge=1024)
nodes = [i for _, i in by_class(refined)["MiniMaxH3TimelineSegment"]
         if json.loads(i["segment_data"])["request"]["prompt"] == "two"]
check("a two-pass card's both segment nodes are shown the sheet",
      [("storyboard_image" in i) for i in nodes], [True, True])
check("...the same sheet", len({i["storyboard_image"][0] for i in nodes}), 1)

# `spill.spread` — the cells' positions.
check("nine cells of a 120-frame pass are its bin centres",
      spill.spread(120, 9), [6, 20, 33, 46, 60, 73, 86, 100, 113])
check("one cell is the middle", spill.spread(120, 1), [60])
check("fewer frames than cells repeats what there is", spill.spread(2, 4), [0, 0, 1, 1])
check("the last cell never runs off the end", max(spill.spread(7, 9)), 6)

# The layout node itself, on fake frames.
import torch

frames = torch.zeros(9, 90, 160, 3)
for index in range(9):
    frames[index, :, :, 0] = (index + 1) / 9
sheet = tl.ContinuityStoryboard.execute(width=480, height=270, frames_1=frames[:5],
                                        frames_2=frames[5:]).args[0]
check("the sheet is one picture at the canvas", tuple(sheet.shape), (1, 270, 480, 3))
# Cell (row, col) holds frame row*3+col: sample each cell's centre.
got = [round(float(sheet[0, row * 90 + 45, col * 160 + 80, 0]) * 9)
       for row in range(3) for col in range(3)]
check("cells run left to right, top to bottom, in the order the frames came",
      got, list(range(1, 10)))

passed("the storyboard is read off the passes before a shot and laid out in order")
