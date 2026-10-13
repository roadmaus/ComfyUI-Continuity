"""What a Download hands out: which files, under which names, and what it
refuses to reach.

`downloads.py` wants core's `folder_paths` and nothing else, so that is
stubbed over three temporary roots and the real module is imported.

    python3 tests/test_downloads.py
"""

import os
import sys
import tempfile
import zipfile

import layout
from harness import check

BASE = tempfile.mkdtemp()
DIRS = {kind: os.path.join(BASE, kind) for kind in ("input", "output", "temp")}


class _FolderPaths:
    @staticmethod
    def get_directory_by_type(kind):
        return DIRS.get(kind)

    @staticmethod
    def is_within_directory(root, path):
        root, target = os.path.realpath(root), os.path.realpath(path)
        return target == root or target.startswith(root + os.sep)


sys.modules["folder_paths"] = _FolderPaths
downloads = layout.load("downloads").downloads


def _touch(*parts, payload=b"x"):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


_touch(DIRS["input"], "a.png")
_touch(DIRS["input"], "shelf", "b.png")
_touch(DIRS["output"], "clip.mp4")
_touch(DIRS["output"], "mesh", "model.glb")
_touch(DIRS["output"], "mesh", "tex", "albedo.png")
_touch(DIRS["output"], "mesh", ".DS_Store")
_touch(DIRS["output"], "empty", ".hidden")
_touch(BASE, "secret.txt")


def _refused(path):
    try:
        downloads.resolve(path)
    except downloads.DownloadError:
        return True
    return False


def _names(paths):
    return [name for _, name in downloads.plan(paths)]


check("unannotated is input/", downloads.resolve("a.png"), os.path.realpath(os.path.join(DIRS["input"], "a.png")))
check("annotation picks the root", downloads.resolve("clip.mp4 [output]"),
      os.path.realpath(os.path.join(DIRS["output"], "clip.mp4")))
check("dot-dot out of the root is refused", _refused("../secret.txt"), True)
check("dot-dot out of an annotated root is refused", _refused("../secret.txt [output]"), True)
check("a missing file is refused", _refused("gone.png"), True)

os.symlink(os.path.join(BASE, "secret.txt"), os.path.join(DIRS["input"], "link.txt"))
check("a symlink out of the root is refused", _refused("link.txt"), True)

os.symlink(os.path.join(BASE, "secret.txt"), os.path.join(DIRS["output"], "mesh", "leak.txt"))
check("a symlink out of a zipped folder is left out",
      _names(["mesh [output]"]), ["mesh/model.glb", "mesh/tex/albedo.png"])

check("one folder zips under its own name, hidden files left out",
      _names(["mesh [output]"]), ["mesh/model.glb", "mesh/tex/albedo.png"])
check("files off one shelf come out flat", _names(["shelf/b.png"]), ["b.png"])
check("files off two shelves keep the shelf", _names(["a.png", "shelf/b.png"]), ["a.png", "shelf/b.png"])
check("a file inside a folder also given goes in once",
      _names(["mesh [output]", "mesh/model.glb [output]"]), ["mesh/model.glb", "mesh/tex/albedo.png"])
try:
    downloads.plan(["empty [output]"])
    empty = "planned"
except downloads.DownloadError:
    empty = "refused"
check("a folder of nothing is refused", empty, "refused")

check("one folder names the zip", downloads.zip_name(["mesh [output]"], [None, None]), "mesh.zip")
check("a selection is counted", downloads.zip_name(["a.png", "shelf/b.png"], [None, None]), "continuity-2-files.zip")
check("an asked-for name wins, made safe", downloads.zip_name(["a.png"], [None], "my/game"), "my_game.zip")

archive = os.path.join(BASE, "out.zip")
downloads.write_zip(downloads.plan(["mesh [output]", "clip.mp4 [output]"]), archive)
with zipfile.ZipFile(archive) as written:
    kinds = {info.filename: info.compress_type for info in written.infolist()}
check("the zip holds what was planned", sorted(kinds), ["clip.mp4", "mesh/model.glb", "mesh/tex/albedo.png"])
check("a video is stored, not deflated", kinds["clip.mp4"], zipfile.ZIP_STORED)
check("a mesh is deflated", kinds["mesh/model.glb"], zipfile.ZIP_DEFLATED)
