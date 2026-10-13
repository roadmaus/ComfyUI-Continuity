"""What a Download button hands the browser: one file as itself, anything more
as a zip.

The pack is often driven from a machine that is not the one ComfyUI runs on —
a laptop through an ssh tunnel to a GPU box — and every finished thing it
makes lands on the box. Show in folder opens a file manager over there; the
browser is the only thing on this side of the tunnel, so a download is the
only way a render, a mesh or a forge export reaches the laptop at all.

Paths are the picker's vocabulary, `sub/name.png [output]`, unannotated
meaning input/ — the one spelling every surface already holds for what it
shows. A path may name a folder (a mesh with its textures, a forge project,
an export's build directory), which goes into the zip whole. Only input/,
output/ and temp/ are reachable: the realpath is held inside its root, so a
`..` or a symlink out is refused rather than followed.

Pure apart from `folder_paths`, so the planning is testable without a server;
`routes/download.py` is the aiohttp half.
"""

import os
import re
import zipfile

import folder_paths

ROOTS = ("input", "output", "temp")
_ANNOTATED = re.compile(r"\A(.*) \[(input|output|temp)\]\Z")

# Stored rather than deflated: these are compressed already, and deflating a
# 2 GB render costs a minute of CPU to save nothing.
_STORED = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm", ".mkv", ".m4v",
           ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".zip", ".safetensors"}


class DownloadError(ValueError):
    """A path that names nothing a download can hand out."""


def resolve(path):
    """A picker path -> its absolute realpath, inside its root, or DownloadError."""
    raw = str(path or "").strip()
    match = _ANNOTATED.match(raw)
    kind = match.group(2) if match else "input"
    relative = (match.group(1) if match else raw).replace("\\", "/").strip("/")
    root = os.path.realpath(folder_paths.get_directory_by_type(kind))
    target = os.path.realpath(os.path.join(root, relative)) if relative else root
    if not folder_paths.is_within_directory(root, target):
        raise DownloadError(f"{raw!r} is outside the {kind} folder")
    if not os.path.exists(target):
        raise DownloadError(f"{raw!r} is not there any more")
    return target


def _walk(folder):
    """Every file under a folder, hidden ones and hidden folders left out —
    `.DS_Store` and a build's marker are not things anybody asked for.

    `resolve` held the folder inside its root, but a symlink inside it can
    still point anywhere, and the zip would follow it. So each file is held
    inside the folder too; `os.walk` already declines to descend a linked
    directory."""
    for here, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            file = os.path.join(here, name)
            if not name.startswith(".") and folder_paths.is_within_directory(folder, os.path.realpath(file)):
                yield file


def plan(paths):
    """Picker paths -> [(absolute file, name in the zip)], in the order given.

    Names are relative to the deepest folder every path shares, so one folder
    zips as `folder/...`, and files picked off one shelf come out flat while
    files from two shelves keep the shelf that tells them apart. A path given
    twice, or a file inside a folder also given, goes in once.
    """
    targets = [resolve(p) for p in paths]
    if not targets:
        raise DownloadError("nothing to download")
    # A folder's own name belongs in the zip, so the base is its parent.
    base = os.path.commonpath([os.path.dirname(t) for t in targets])
    entries, seen = [], set()
    for target in targets:
        for file in (_walk(target) if os.path.isdir(target) else [target]):
            if file in seen:
                continue
            seen.add(file)
            entries.append((file, os.path.relpath(file, base).replace(os.sep, "/")))
    if not entries:
        raise DownloadError("there are no files in it")
    return entries


def zip_name(paths, entries, name=None):
    """What the browser saves the zip as: the name asked for, else a folder's
    own name when one folder was given, else a count."""
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(name or "")).strip(" ._")
    if not stem and len(paths) == 1:
        stem = os.path.basename(resolve(paths[0]))
    if not stem:
        stem = f"continuity-{len(entries)}-files"
    return stem if stem.lower().endswith(".zip") else f"{stem}.zip"


def write_zip(entries, destination):
    """Write the planned entries to a zip at `destination`."""
    with zipfile.ZipFile(destination, "w") as archive:
        for file, arcname in entries:
            stored = os.path.splitext(file)[1].lower() in _STORED
            archive.write(file, arcname, zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
