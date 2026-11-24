"""The blockout bench's server half: frames in, a clip out.

The other two benches take a file off the disk and hand a different one back,
so their server halves are where the work lives. This bench is the other way
round. Its source is a scene the browser is holding — boxes, a camera, a list
of marks — and the browser is also the renderer: the light box redraws it live
while the camera is dragged, and the run draws the same frames again at full
size. What is on the glass is exactly what gets written, because one renderer
drew both. The server's whole share is the one thing a browser cannot do
without a codec of its own: put the frames it drew into an mp4 in the input
folder.

**Not a job.** Every queued run in this pack (`creator/jobs.py`) is on the
queue because it wants the GPU, and an encode wants none of it — it is libx264
on the CPU while the queue's own work is a sampler on the device. A blockout
written during a render would otherwise wait minutes behind a job it shares
nothing with. So the routes run this in an executor, the way the previews run,
and the still path does not reach this module at all: the browser uploads one
PNG through core's own `/upload/image` and the server never learns it happened.

**The staging directory is the handshake.** A clip is a few hundred frames and
one request carrying all of them would be a hundred-megabyte POST, so the
browser sends batches against a token it minted, and `write` turns whatever
has accumulated under that token into the file. The token is confined to hex
so it can never be a path, and stale staging — a tab closed mid-send — is
swept whenever the next write comes through.

**The sidecar is the way back in.** The scene that made a clip is a couple of
kilobytes of JSON, and a guide whose set cannot be re-opened is a guide that
has to be rebuilt from memory to move one wall. So `write` puts the scene
beside the mp4 under the same stem, and the bench can put a saved set back on
the glass from it.
"""

import json
import logging
import os
import re
import shutil
import time
from fractions import Fraction

import numpy as np
from PIL import Image

import folder_paths

from . import bench, settings

log = logging.getLogger("continuity")

# Where a written blockout lands. Under input/ for the reason a tracing is:
# the whole point is that the pre-stage and the shot can reference it the
# moment it exists, and both read the input folder.
SUBFOLDER = "continuity/blockout"

# Where the frames wait between batches, under ComfyUI's own temp directory —
# which core already treats as disposable, so a crash mid-send leaves nothing
# that outlives a restart.
STAGING = "continuity_blockout"

# A batch that has seen no write for this long belongs to a tab that is gone.
STALE_AFTER = 6 * 3600


class BlockoutError(bench.BenchError):
    """A staging token is malformed, or a clip cannot be written from it."""


# Hex only, and long enough to be minted rather than typed. The token is used
# as a directory name, and this pattern is what makes that safe: nothing in it
# can be a separator, a dot, or anybody else's name.
_TOKEN = re.compile(r"^[0-9a-f]{8,64}$")

# The frames a run may hold at once. A cap rather than trust, because the
# staging directory is written by whoever can reach the route: ten seconds at
# sixty frames a second is the most the bench itself would ever send.
MOST_FRAMES = 600


def _staging(token):
    if not _TOKEN.match(str(token or "")):
        raise BlockoutError("that is not a staging token this bench minted")
    return os.path.join(folder_paths.get_temp_directory(), STAGING, token)


def prune(keep=None):
    """Sweep staging that nothing is coming back for.

    Called on every write rather than on a timer, because a timer is a thread
    this pack would then own forever: the next person to finish a clip cleans
    up after the last person who never did.
    """
    root = os.path.join(folder_paths.get_temp_directory(), STAGING)
    if not os.path.isdir(root):
        return
    now = time.time()
    for name in os.listdir(root):
        if name == keep:
            continue
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) > STALE_AFTER:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


def take_frames(token, frames):
    """A batch of rendered frames into the token's staging. -> frames held.

    `frames` is `[(index, png_bytes)]`. The index names the file, so batches
    can arrive in any order and a retry overwrites rather than duplicates.
    """
    root = _staging(token)
    os.makedirs(root, exist_ok=True)
    held = len([name for name in os.listdir(root) if name.endswith(".png")])
    for index, data in frames:
        index = int(index)
        if index < 0 or index >= MOST_FRAMES:
            raise BlockoutError(f"frame {index} is outside what a run can hold")
        if not data.startswith(b"\x89PNG"):
            raise BlockoutError("a frame arrived that is not a PNG")
        with open(os.path.join(root, f"{index:06d}.png"), "wb") as out:
            out.write(data)
    return held + len(frames)


# The name a derived guide is written under: the shot's staging stamp and its
# pass (`state.stagedGuideName`). Its own alphabet for the reason the token has
# one — it becomes a filename — and a prefix of its own, so the sweep below can
# never touch a guide somebody wrote by hand.
_STAGED = re.compile(r"^staged-[0-9a-z]{1,16}-[a-z_]{1,16}$")

# How long an unreferenced derived guide is left alone: a tab that has just
# written one may not have saved the piece that names it yet.
SWEEP_AFTER = 600


def staged_name(name):
    if not _STAGED.match(str(name or "")):
        raise BlockoutError("that is not a name the bench derives a guide under")
    return str(name)


def sweep(keep):
    """Remove the derived guides no shot points at. -> how many went.

    `keep` is every derived guide the open graph names, as `staged-…` stems or
    paths. Only files the bench derived are ever considered, and only once they
    are old enough not to belong to a write still on its way to a saved piece.
    A guide swept by mistake costs nothing but time: a staged shot that needs it
    derives it again before it renders.
    """
    kept = {os.path.splitext(os.path.basename(str(item)))[0] for item in keep or []}
    out_dir = os.path.join(folder_paths.get_input_directory(), *SUBFOLDER.split("/"))
    if not os.path.isdir(out_dir):
        return 0
    now = time.time()
    gone = 0
    for name in os.listdir(out_dir):
        stem, ext = os.path.splitext(name)
        if ext not in (".mp4", ".png") or not _STAGED.match(stem) or stem in kept:
            continue
        path = os.path.join(out_dir, name)
        try:
            if now - os.path.getmtime(path) < SWEEP_AFTER:
                continue
            os.remove(path)
            gone += 1
        except OSError:
            continue
    return gone


def write(token, fps, op, scene=None, name=None):
    """The staged frames -> one mp4 in the input folder. -> `{path, kind}`.

    `name`, where given, is a derived guide's (`staged_name`), written in
    place. The frames are encoded in index order at a constant rate — there is no
    source clip whose timestamps could disagree, the browser drew these at
    exactly the spacing it is naming. The scene, where one is handed over, goes
    beside the file under the same stem; see the module note.
    """
    import av

    root = _staging(token)
    if not os.path.isdir(root):
        raise BlockoutError("no frames are staged under that token")
    names = sorted(name for name in os.listdir(root) if name.endswith(".png"))
    if len(names) < 2:
        raise BlockoutError("a clip needs at least two frames — one frame is a still, "
                            "and a still goes through the upload route instead")
    try:
        fps = min(60, max(1, int(fps)))
    except (TypeError, ValueError):
        fps = 24
    op = re.sub(r"[^a-z0-9_]", "", str(op or "guide")) or "guide"

    out_dir = os.path.join(folder_paths.get_input_directory(), *SUBFOLDER.split("/"))
    # A derived guide goes under its staging stamp and overwrites: the same
    # stamp is the same frames. Anything else gets a fresh name, as ever.
    name = (f"{staged_name(name)}.mp4" if name
            else bench.free_name(out_dir, f"blockout-{op}", ".mp4"))
    target = os.path.join(out_dir, name)

    first = np.asarray(Image.open(os.path.join(root, names[0])).convert("RGB"))
    height, width = first.shape[:2]
    width, height = bench.even(width), bench.even(height)
    if width < 2 or height < 2:
        raise BlockoutError("the staged frames are too small to encode")

    crf = settings.video_crf()
    with av.open(target, "w") as out:
        video = out.add_stream("libx264", rate=Fraction(fps))
        video.width, video.height = width, height
        video.pix_fmt = "yuv420p"
        video.options = {"crf": str(crf), "preset": "medium"}
        for filename in names:
            frame = np.asarray(Image.open(os.path.join(root, filename)).convert("RGB"))
            frame = frame[:height, :width]
            for packet in video.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
                out.mux(packet)
        for packet in video.encode():
            out.mux(packet)

    if scene is not None:
        sidecar = os.path.join(out_dir, os.path.splitext(name)[0] + ".json")
        with open(sidecar, "w", encoding="utf-8") as out_file:
            json.dump({"continuity_blockout": 1, "op": op, "fps": fps, "scene": scene},
                      out_file, separators=(",", ":"))

    shutil.rmtree(root, ignore_errors=True)
    prune(keep=None)
    log.info("continuity: blockout wrote %d frames -> %s/%s", len(names), SUBFOLDER, name)
    return {"path": f"{SUBFOLDER}/{name}", "kind": "video"}
