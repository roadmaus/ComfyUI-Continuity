"""Clip-only reels bypass optional DLSS; generated passes still refine in order.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_neural_clip_reel.py

CPU only. The actual node executes; dependency checks and frame processing are
spies, so no DLL, weights, server, or user media are needed.
"""

import os
import sys
import tempfile
from unittest.mock import patch

import layout
from harness import check

sys.path.insert(0, os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
with tempfile.TemporaryDirectory(prefix="continuity-neural-reel-") as runtime:
    sys.argv = [__file__, "--cpu", "--base-directory", runtime]
    import comfy.cli_args
    comfy.cli_args.args.cpu = True
    import folder_paths
    for kind in ("input", "output", "temp", "user"):
        path = os.path.join(runtime, kind)
        os.makedirs(path)
        getattr(folder_paths, f"set_{kind}_directory")(path)

    pkg = layout.load("neuralpass")
    neuralpass, neural = pkg.neuralpass, pkg.neural
    node = neuralpass.ContinuityNeuralPass
    options = dict(profile="standard", detail_strength=1.25,
                   colour_strength=0, intensity=1, precision="fast", frame_index=7)
    clips = [{"clip": {"filename": "held-a.mp4", "duration_s": 5}},
             {"clip": {"filename": "supplied-b.mp4", "duration_s": 3}}]

    def missing():
        raise neural.NeuralError("test: optional weights are not installed")

    with patch.object(neural, "require", side_effect=missing) as require, \
            patch.object(neural, "release") as release:
        try:
            out = node.execute(clips, **options).result[0]
        except RuntimeError as exc:
            out = str(exc)
        check("held/supplied clips pass through without dependencies", out, clips)
        check("no weights check for clips", require.call_count, 0)
        check("no pipeline touched for clips", release.call_count, 0)
        for invalid in ([], [{"unexpected": {}}], [clips[0], {}]):
            try:
                node.execute(invalid, **options)
                rejected = False
            except RuntimeError:
                rejected = True
            check("empty or malformed reels remain errors", rejected, True)
        generated = {"pass": {"frames": 2, "name": "a"}}
        try:
            node.execute([generated], **options)
            error = ""
        except RuntimeError as exc:
            error = str(exc)
        check("generated passes still require weights", "not installed" in error, True)
        check("generated dependency failure releases", release.call_count, 1)

    events = []

    class Sequence:
        motion = "test"
        scene_cuts = 0

        def __init__(self, request, frame_index):
            events.append(("start", frame_index))

        def reset(self):
            events.append(("reset",))

    def refine(source, sequence, tick):
        events.append(("refine", source["name"]))
        return {**source, "refined": True}

    second = {"pass": {"frames": 3, "name": "b"}}
    third = {"pass": {"frames": 4, "name": "c"}}
    reel = [generated, second, clips[0], third]
    with patch.object(neural, "require"), patch.object(neural, "release") as release, \
            patch.object(neural, "Sequence", Sequence), \
            patch.object(neuralpass, "_progress", return_value=lambda: None) as progress, \
            patch.object(node, "_one", side_effect=refine):
        out = node.execute(reel, **options).result[0]
        check("generated pass order and reset across a clip", events,
              [("start", 7), ("refine", "a"), ("refine", "b"), ("reset",), ("refine", "c")])
        check("inserted clip is unchanged", out[2] is clips[0], True)
        check("source pass is not modified", "refined" in generated["pass"], False)
        check("only generated frames count towards progress", progress.call_args.args, (9,))
        check("mixed reel releases once", release.call_count, 1)
