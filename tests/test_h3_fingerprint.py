"""H3 fingerprints track referenced files after moving into the family package.

COMFYUI_PATH points at a ComfyUI installation. This imports the actual node and
shared stamp function on CPU; it does not start a server or load model weights.
All file fixtures and ComfyUI base directories live in a temporary directory.
"""

import json
import os
from pathlib import Path
import sys
import tempfile

import layout
from harness import check, skip

comfy = Path(os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI")))
if not (comfy / "folder_paths.py").is_file():
    skip("set COMFYUI_PATH to a ComfyUI installation")
sys.path.insert(0, str(comfy))

with tempfile.TemporaryDirectory(prefix="continuity-fingerprint-") as temporary:
    root = Path(temporary)
    sys.argv = ["test_h3_fingerprint", "--cpu", "--base-directory", str(root)]
    import comfy.cli_args
    comfy.cli_args.args.cpu = True
    import folder_paths
    for kind in ("input", "output", "temp", "user"):
        directory = root / kind
        directory.mkdir()
        getattr(folder_paths, f"set_{kind}_directory")(str(directory))

    pkg = layout.load("h3_segment", "timeline", package="fingerprint_contract")
    node = pkg.h3_segment.MiniMaxH3TimelineSegment
    # Only path resolution is replaced; timeline.stamps really stats these files.
    pkg.timeline.media.resolve = lambda name: str(root / name)
    pkg.timeline.lora.resolve = lambda name: str(root / name)
    names = ("reference.png", "motion.mp4", "speech.wav", "model.safetensors")
    for name in names:
        (root / name).write_bytes(b"fixture")
        os.utime(root / name, (1700000000, 1700000000))

    payload = {"request": {
        "assets": [{"filename": name} for name in names[:2]],
        "loras": [{"name": names[3]}]},
        "sound": [{"filename": names[2]}]}
    data = json.dumps(payload)
    before = node.fingerprint_inputs(data)
    check("payload remains part of the cache key", before[0], data)
    check("all reference/sound/LoRA stamps are present", len(before[1]), 4)
    check("unchanged files remain cache hits", node.fingerprint_inputs(data), before)
    for index, name in enumerate(names, start=1):
        os.utime(root / name, (1700000000 + index, 1700000000 + index))
        after = node.fingerprint_inputs(data)
        check(f"same-name replacement invalidates {name}", after != before, True)
        check(f"{name} matches shared file stamps", after[1],
              pkg.timeline.stamps({"segments": [payload["request"]], "sound": payload["sound"]}))
        before = after

    check("missing file keeps a stable sentinel",
          node.fingerprint_inputs(json.dumps({"request": {"assets": [{"filename": "missing"}]}}))[1],
          (None,))
    check("text-only request has no file dependencies",
          node.fingerprint_inputs(json.dumps({"request": {"prompt": "a room"}}))[1], ())
    check("malformed JSON preserves existing fallback",
          node.fingerprint_inputs("not json"), ("not json", ()))
