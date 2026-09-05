"""A plate's name carries the matte model that cut it (issue #47).

    <comfy-venv>/bin/python3 tests/test_plate_key.py

`plate.build` returns an existing file before it consults the model, so the
model has to be part of the name where it changes the pixels — a cut panel — and
nowhere else, so every uncut sheet keeps the name it was written under.
"""

import os
import sys
import tempfile

import layout
from harness import check, passed

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)
try:
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import folder_paths  # noqa: F401
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

_pkg = layout.load("media")
media = _pkg.media

# `plate` imports `folder_paths` and the cutout for real; only `key` is under
# test, and it reads nothing but `media.stamp`.
import importlib.util
spec = importlib.util.spec_from_file_location("mmcpkg.plate", layout.py("plate"))
try:
    plate = importlib.util.module_from_spec(spec)
    sys.modules["mmcpkg.plate"] = plate
    spec.loader.exec_module(plate)
except Exception as exc:  # noqa: BLE001
    print(f"skipped: plate not importable here ({type(exc).__name__}: {exc})")
    sys.exit(0)

# `media.stamp` only answers for a file under the input folder.
scratch = tempfile.mkdtemp(prefix="plate-key-", dir=folder_paths.get_input_directory())
picture = os.path.join(scratch, "a.png")
with open(picture, "wb") as handle:
    handle.write(b"\x89PNG not really")

cut = [{"path": picture, "cut": True}]
plain = [{"path": picture, "cut": False}]
a = {"cutout": "model-A.safetensors", "segment": ""}
b = {"cutout": "model-B.safetensors", "segment": ""}

check("a cut sheet is named by its model too",
      plate.key(cut, 0.5, 64, 64, a) == plate.key(cut, 0.5, 64, 64, b), False)
check("an uncut sheet is not",
      plate.key(plain, 0.5, 64, 64, a), plate.key(plain, 0.5, 64, 64, b))
check("...and keeps the name it had before the model was part of it",
      plate.key(plain, 0.5, 64, 64, a), plate.key(plain, 0.5, 64, 64))

import shutil
shutil.rmtree(scratch, ignore_errors=True)
passed("a plate is named by what cut it")
