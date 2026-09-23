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
    pkg.timeline.media.resolve = lambda name: str(root / name.removeprefix("refmod:"))
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

    # The photo stays the same while "remake saved reference" overwrites a
    # bound mod. Both the Creator's pool and a segment's local references use
    # this helper; the encoder's private cache cannot rescue an executor hit.
    mods = {"h3_video": "refmod:person.h3", "flux2": "refmod:person.flux2"}
    for name in mods.values():
        path = root / name.removeprefix("refmod:")
        path.write_bytes(b"saved rendition")
        os.utime(path, (1700000100, 1700000100))
    asset = {"filename": names[0], "mods": mods}
    bound = json.dumps({"request": {"assets": [asset]}})
    before = node.fingerprint_inputs(bound)
    check("photo and both bound files are dependencies", len(before[1]), 3)
    check("unchanged bound files stay cached", node.fingerprint_inputs(bound), before)
    check("pool and local references carry the same file dependencies",
          pkg.timeline.stamps({"assets": [asset]}), before[1])
    check("space ordering is not a file-identity change",
          pkg.timeline.stamps({"assets": [{**asset, "mods": dict(reversed(list(mods.items())))}]}),
          before[1])
    for index, name in enumerate(mods.values(), start=1):
        path = root / name.removeprefix("refmod:")
        path.write_bytes(b"remade rendition")
        os.utime(path, (1700000100 + index, 1700000100 + index))
        after = node.fingerprint_inputs(bound)
        check(f"overwriting bound {name} invalidates the segment", after != before, True)
        check(f"overwriting bound {name} invalidates the outer pool",
              pkg.timeline.stamps({"assets": [asset]}), after[1])
        before = after

    # Missing/removed mods use the same stable sentinel as other dependencies,
    # then creation at the same name invalidates it without editing the blob.
    path = root / "person.h3"
    path.unlink()
    missing = node.fingerprint_inputs(bound)
    check("deleting a bound file invalidates its former value", missing != before, True)
    check("a missing bound file has a stable key", node.fingerprint_inputs(bound), missing)
    path.write_bytes(b"created again")
    os.utime(path, (1700000110, 1700000110))
    check("recreating a bound file invalidates its missing sentinel",
          node.fingerprint_inputs(bound) != missing, True)
    check("an empty mod map preserves the old no-mod key",
          pkg.timeline.stamps({"assets": [{"filename": names[0], "mods": {}}]}),
          pkg.timeline.stamps({"assets": [{"filename": names[0]}]}))
