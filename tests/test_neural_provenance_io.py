"""Both actual savers persist producer identity and per-image batch position.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_neural_provenance_io.py

CPU tensors and tiny synthetic media only. Input/output/temp are confined to a
TemporaryDirectory; no installed models, workflow or existing files are used.
"""

import ast
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import harness
import layout
from harness import check

comfy = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, comfy)
try:
    import av
    import numpy as np
    import torch
    from PIL import Image
    import comfy.cli_args
except ImportError as error:
    harness.skip(f"ComfyUI save dependencies unavailable: {error}")

with tempfile.TemporaryDirectory(prefix="continuity-producer-") as work:
    comfy.cli_args.args.cpu = True
    comfy.cli_args.args.base_directory = work
    comfy.cli_args.args.disable_metadata = False
    import folder_paths
    from comfy_api.latest import io

    for kind in ("input", "output", "temp", "user"):
        directory = Path(work) / kind
        directory.mkdir(exist_ok=True)
        getattr(folder_paths, f"set_{kind}_directory")(str(directory))
    pkg = layout.load("prestage", "timeline", "neuraltwin")
    prompt = {"A": {"class_type": "MiniMaxH3Creator", "inputs": {"creator_data": "{}"}},
              "B": {"class_type": "MiniMaxH3PreStage", "inputs": {"prestage_data": "{}"}}}
    workflow = {"nodes": [{"id": "A"}, {"id": "B"}]}

    # Only the standalone metadata reader is loaded from the route module: a
    # server singleton/routes are not needed to read actual PNG and MP4 files.
    route_path = Path(layout.py("server_routes"))
    tree = ast.parse(route_path.read_text(encoding="utf-8"))
    reader = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_read_embedded")
    namespace = {"os": os, "json": json}
    exec(compile(ast.Module(body=[reader], type_ignores=[]), str(route_path), "exec"), namespace)
    read_embedded = namespace["_read_embedded"]

    def hidden(owner):
        return io.HiddenHolder(unique_id=f"{owner}.0.save", prompt=prompt,
                               extra_pnginfo={"workflow": workflow},
                               dynprompt=SimpleNamespace(get_real_node_id=lambda unique_id: owner),
                               auth_token_comfy_org=None, api_key_comfy_org=None)

    image_save = pkg.prestage.MiniMaxH3SaveImage
    check("image saver requests the real node context",
          all(key in image_save.define_schema().hidden for key in (io.Hidden.unique_id, io.Hidden.dynprompt)), True)
    image_save.hidden = hidden("B")
    image_save.execute(torch.zeros((2, 16, 16, 3)), "stills/test")
    images = sorted((Path(work) / "output" / "stills").glob("*.png"))
    check("two independent saved batch files", len(images), 2)
    for index, filename in enumerate(images):
        meta = read_embedded(str(filename), ("prompt", "workflow", pkg.neuraltwin.PRODUCER_KEY))
        check(f"image {index} producer", meta[pkg.neuraltwin.PRODUCER_KEY], {"node": "B", "index": index})
        check(f"image {index} prompt preserved", meta["prompt"], prompt)
        check(f"image {index} workflow preserved", meta["workflow"], workflow)
        check(f"image {index} default reader shape unchanged", set(read_embedded(str(filename))), {"prompt", "workflow"})

    source = Path(work) / "input" / "source.mp4"
    with av.open(str(source), "w") as output:
        stream = output.add_stream("h264", rate=24)
        stream.width = stream.height = 16
        stream.pix_fmt = "yuv420p"
        for index in range(2):
            frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")
            output.mux(stream.encode(frame))
        output.mux(stream.encode(None))
    video_save = pkg.timeline.MiniMaxH3Save
    check("video saver requests the real node context",
          all(key in video_save.define_schema().hidden for key in (io.Hidden.unique_id, io.Hidden.dynprompt)), True)
    video_save.hidden = hidden("A")
    video_save.execute([{"clip": {"path": str(source), "width": 16, "height": 16}}],
                       24, "videos/test")
    video = next((Path(work) / "output" / "videos").glob("*.mp4"))
    meta = read_embedded(str(video), ("prompt", "workflow", pkg.neuraltwin.PRODUCER_KEY))
    check("video producer survives the MP4 container", meta[pkg.neuraltwin.PRODUCER_KEY], {"node": "A", "index": 0})
    check("video prompt preserved", meta["prompt"], prompt)
    check("video workflow preserved", meta["workflow"], workflow)

    comfy.cli_args.args.disable_metadata = True
    image_save.execute(torch.zeros((1, 16, 16, 3)), "private/test")
    private = next((Path(work) / "output" / "private").glob("*.png"))
    with Image.open(private) as image:
        check("disable-metadata writes no producer", pkg.neuraltwin.PRODUCER_KEY in image.info, False)
        check("disable-metadata writes no prompt", "prompt" in image.info, False)
