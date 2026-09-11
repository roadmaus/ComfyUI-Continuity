"""Saved references: a RefMod is one H3 VAE latent kept on disk.

The file format is the one `ComfyUI-MiniMaxH3Mod` writes and reads — a single
safetensors holding a `latent` of `[1, 24, T, H, W]` and a JSON block in the
header under `refmod_meta` — so a character somebody made there, or downloaded,
is a character here, and one kept here loads in their nodes. The format is
documented in that pack's README; nothing about it is ours to change, which is
why the reader below refuses a version newer than the one it knows rather than
guessing at fields.

What a RefMod *is* in this pack's terms: the DiT half of a reference, already
encoded. `encode._encode_references` builds two things for every picture it is
handed — the VAE latent the DiT attends to and the pixels the tokenizer is shown
as `<Picture N>` — and a mod carries only the first. The second is decoded from
it at render time (`encode._mod_tensors`), which is what lets a mod take an
ordinal, be cited by name and hang on a cast member exactly as a photograph
does. So a mod is an ordinary reference asset whose `filename` starts with
`refmod:` — `media.resolve` knows the scheme the way it knows `atlas:`, and
nothing between the picker and the payload has to know a mod from a picture.

Why anyone wants one: a *compressed* mod is the latent average-pooled to a
small grid and refined against the full encode, and a 16x16 grid is 64 tokens
where a `match` encode of the same face is several hundred. Reference tokens
ride through every sampling step, so that is the difference between two
references fitting a shot and six. A *full* mod is the encode itself, cached
on disk and shareable as one file. Neither is a concept extractor — pooling
keeps colours and large structure and loses detail, and the sibling pack's own
README says so — which is why the cast is the door: the member's own words and
pictures carry what the latent cannot.

Header reading is stdlib only, so `compile.py` and the listing route can ask
what a file is without torch. Loading and saving the tensor import safetensors
and torch where they are called, on the render thread or the job queue.
"""

import json
import logging
import os
import struct
import tempfile

log = logging.getLogger(__name__)

# The filename prefix a mod wears in a blob. Chosen to read the way `atlas:`
# does: a scheme, then a name relative to the mod folders, never a path.
SCHEME = "refmod:"
# The model folder both packs share. `models/refmods/` under ComfyUI's own
# models directory, plus whatever `extra_model_paths.yaml` maps to it.
FOLDER = "refmods"
EXT = ".safetensors"
# The sidecar a mod's picture is kept in: `<name>.png` beside `<name>.safetensors`.
# Ours are written when the mod is made, from the source picture. A mod made
# elsewhere has none, and gets one the first time a render decodes it.
PREVIEW_EXT = ".png"
# Metadata key in the safetensors header. The sibling pack's, verbatim.
META_KEY = "refmod_meta"
# The newest header this reader understands. Their loader is lenient about
# older files, and so is this; a newer one is refused by name.
FORMAT_VERSION = 4
LATENT_CHANNELS = 24
# What a mod can be here. Audio mods exist in the format and are refused: a
# voice is bound to a cast member as a file with a speaker ID, and nothing in
# that path takes a latent yet.
KINDS = ("image", "video")
# How far the preview is scaled down before it is written: a thumbnail, not the
# reference. The picker draws it at 140px.
PREVIEW_EDGE = 512
# A mod name: subfolders allowed, parent references and absolute paths not.
_BAD_SEGMENTS = ("", ".", "..")


class RefModError(ValueError):
    """A mod that cannot be used: missing, malformed, or of a kind this pack
    does not take. The message names the file and says which."""


def is_mod(filename):
    return str(filename or "").startswith(SCHEME)


def name_of(filename):
    """`refmod:cast/anna` -> `cast/anna`, checked to stay inside the folders.

    Backslashes are folded to slashes so a name typed on Windows lists the same
    file; a segment that walks upward is refused rather than joined onto a root.
    """
    name = str(filename or "")
    if name.startswith(SCHEME):
        name = name[len(SCHEME):]
    name = name.replace("\\", "/").strip().strip("/")
    if name.lower().endswith(EXT):
        name = name[:-len(EXT)]
    parts = name.split("/")
    if not name or any(part in _BAD_SEGMENTS for part in parts):
        raise RefModError(f"{filename!r} is not a RefMod name")
    return name


def filename_of(name):
    return SCHEME + name


# ---- the header ---------------------------------------------------------------


def header(path):
    """What one file says it is, without reading its tensor.

    -> dict: the mod's own metadata, plus `shape`, `dtype`, `tokens` and the
    dims read off the tensor itself. The dims come from the tensor and not from
    the metadata: the metadata is what somebody wrote, the shape is what will be
    handed to the DiT, and a mismatch between the two is refused here rather
    than discovered as a wrong-sized reference mid-render.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read(8)
            if len(raw) < 8:
                raise RefModError(f"{path}: not a safetensors file")
            (length,) = struct.unpack("<Q", raw)
            if length <= 0 or length > 64 * 1024 * 1024:
                raise RefModError(f"{path}: not a safetensors file")
            table = json.loads(handle.read(length).decode("utf-8"))
    except OSError as exc:
        raise RefModError(f"{path}: {exc.strerror or exc}") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise RefModError(f"{path}: not a safetensors file ({exc})") from exc

    written = (table.get("__metadata__") or {}).get(META_KEY)
    if not written:
        # The sibling pack keeps audio mods under a second key. Named so the
        # refusal says what the file is rather than "no metadata".
        if (table.get("__metadata__") or {}).get("audio_refmod_meta"):
            raise RefModError(f"{path}: an audio RefMod — voices are bound as files, not mods")
        raise RefModError(f"{path}: no RefMod metadata in the header")
    try:
        meta = json.loads(written)
    except ValueError as exc:
        raise RefModError(f"{path}: RefMod metadata is not JSON") from exc
    if not isinstance(meta, dict):
        raise RefModError(f"{path}: RefMod metadata is not an object")

    version = int(meta.get("_format_version", 1) or 1)
    if version > FORMAT_VERSION:
        raise RefModError(
            f"{path}: RefMod format {version} is newer than this pack reads "
            f"({FORMAT_VERSION}) — update Continuity")
    kind = str(meta.get("kind", "image") or "image")
    if kind == "audio":
        raise RefModError(f"{path}: an audio RefMod — voices are bound as files, not mods")
    if kind not in KINDS:
        raise RefModError(f"{path}: unknown RefMod kind {kind!r}")

    entry = table.get("latent")
    if not isinstance(entry, dict):
        raise RefModError(f"{path}: no 'latent' tensor in the file")
    shape = [int(v) for v in entry.get("shape", [])]
    if len(shape) != 5 or shape[0] != 1 or shape[1] != LATENT_CHANNELS:
        raise RefModError(
            f"{path}: latent is {shape}, not [1, {LATENT_CHANNELS}, T, H, W]")
    _, _, latent_t, latent_h, latent_w = shape
    if kind == "image" and latent_t != 1:
        raise RefModError(f"{path}: an image RefMod with {latent_t} latent frames")
    if latent_h % 2 or latent_w % 2 or latent_h < 2 or latent_w < 2:
        # The DiT patches 2x2 latent cells into one token; an odd grid has no
        # whole number of them.
        raise RefModError(f"{path}: latent grid {latent_h}x{latent_w} is not even")

    out = dict(meta)
    out.update({
        "kind": kind,
        "latent_t": latent_t,
        "latent_h": latent_h,
        "latent_w": latent_w,
        "shape": shape,
        "dtype": str(entry.get("dtype", "")),
        "tokens": latent_t * (latent_h // 2) * (latent_w // 2),
        "format_version": version,
        "mode": _mode(meta.get("mode")),
        "description": str(meta.get("description", "") or ""),
        "name": str(meta.get("name", "") or ""),
    })
    return out


# The two modes, in the words the file uses. `encode` is the VAE encode as it
# is; `training` is the pooled-and-refined grid. The UI says full and compressed.
_MODES = {"encode": "encode", "training": "training", "full": "encode",
          "pooled": "training", "Full Reference": "encode",
          "Compressed Reference": "training"}


def _mode(value):
    return _MODES.get(str(value or "training"), "training")


# ---- the folders --------------------------------------------------------------


def register():
    """Make `refmods` a model folder ComfyUI knows, once.

    The sibling pack registers the same folder; `add_model_folder_path` keeps
    one entry per path, so whichever loads first, both see one list.
    """
    import folder_paths

    folder_paths.add_model_folder_path(
        FOLDER, os.path.join(folder_paths.models_dir, FOLDER))


def roots():
    """Every folder a mod may be in, registered ones first."""
    import folder_paths

    register()
    return list(folder_paths.get_folder_paths(FOLDER))


def home():
    """Where a new mod is written: the first registered root, made if missing."""
    root = roots()[0]
    os.makedirs(root, exist_ok=True)
    return root


def resolve(filename):
    """`refmod:<name>` -> the absolute path of its file, or RefModError."""
    import folder_paths

    name = name_of(filename)
    for root in roots():
        path = os.path.join(root, *name.split("/")) + EXT
        if os.path.isfile(path) and folder_paths.is_within_directory(root, os.path.realpath(path)):
            return path
    raise RefModError(f"RefMod {name!r} is not in models/{FOLDER}/ (or any mapped refmods folder)")


def preview_path(path):
    """The picture beside a mod, or None where it has none yet."""
    for ext in (PREVIEW_EXT, ".webp", ".jpg", ".jpeg"):
        candidate = os.path.splitext(path)[0] + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def listing():
    """Every mod in every root -> `(rows, folders)`, the picker's shapes.

    A row is the asset row `server_routes._scan` produces, with the mod's own
    facts added: `mode`, `tokens`, `description`, `grid`. A file that does not
    read as a mod is skipped rather than listed with a broken thumbnail — the
    folder holds graph presets and whatever else the sibling pack keeps there.
    """
    rows = []
    folders = set()
    seen = set()
    for root in roots():
        if not os.path.isdir(root):
            continue
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames
                                 if not d.startswith(".") and d not in ("__pycache__", "graph_presets"))
            subfolder = os.path.relpath(directory, root)
            subfolder = "" if subfolder == "." else subfolder.replace(os.sep, "/")
            if subfolder:
                folders.add(subfolder)
            for filename in sorted(filenames):
                if not filename.lower().endswith(EXT):
                    continue
                stem = filename[:-len(EXT)]
                name = f"{subfolder}/{stem}" if subfolder else stem
                if name in seen:
                    continue  # a mapped root shadowing another's file: first wins
                path = os.path.join(directory, filename)
                try:
                    meta = header(path)
                    stat = os.stat(path)
                except (RefModError, OSError):
                    continue
                seen.add(name)
                rows.append({
                    "path": filename_of(name),
                    "name": stem,
                    "subfolder": subfolder,
                    "kind": meta["kind"],
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mod": True,
                    "mode": meta["mode"],
                    "tokens": meta["tokens"],
                    "grid": [meta["latent_t"], meta["latent_h"], meta["latent_w"]],
                    "description": meta["description"],
                    "preview": preview_path(path) is not None,
                })
    return rows, sorted(folders)


# ---- the tensor ---------------------------------------------------------------


def load_latent(path, meta=None):
    """The mod's latent as a float32 CPU tensor, checked against its header."""
    from safetensors.torch import load_file

    meta = meta or header(path)
    latent = load_file(path, device="cpu")["latent"]
    if list(latent.shape) != meta["shape"]:
        raise RefModError(f"{path}: latent is {list(latent.shape)}, header says {meta['shape']}")
    # `.clone()` drops the file mmap so the file can be replaced under its name
    # while a render holds the tensor — the same reason the sibling pack does it.
    return latent.clone().float()


def save(name, latent, meta, preview=None):
    """Write `<home>/<name>.safetensors` and its preview. -> the mod's path.

    The metadata is the sibling pack's schema with two fields of ours beside it
    (`made_by`, `source_file`); their loader ignores what it does not know and
    so does ours. Written to a temporary file and renamed, so a mod is either
    whole on disk or not there.
    """
    import torch
    from safetensors.torch import save_file

    if not isinstance(latent, torch.Tensor) or latent.ndim != 5 \
            or latent.shape[0] != 1 or latent.shape[1] != LATENT_CHANNELS:
        raise RefModError(f"a RefMod latent is [1, {LATENT_CHANNELS}, T, H, W], "
                          f"got {list(getattr(latent, 'shape', []))}")
    clean = name_of(name)
    path = os.path.join(home(), *clean.split("/")) + EXT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _, _, latent_t, latent_h, latent_w = latent.shape
    written = {
        "name": clean.rsplit("/", 1)[-1],
        "kind": str(meta.get("kind", "image")),
        "latent_h": int(latent_h),
        "latent_w": int(latent_w),
        "latent_t": int(latent_t),
        "mode": _mode(meta.get("mode")),
        "source": str(meta.get("source", "image")),
        "source_shape": str(meta.get("source_shape", "")),
        "pool": str(meta.get("pool", f"1x{latent_h}x{latent_w}")),
        "optimize_steps": int(meta.get("optimize_steps", 0)),
        "tags": list(meta.get("tags", [])),
        "description": str(meta.get("description", "") or ""),
        "concept_type": str(meta.get("concept_type", "generic") or "generic"),
        "_format_version": FORMAT_VERSION,
        "sample_rate": 32000,
        "made_by": "continuity",
        "source_file": str(meta.get("source_file", "") or ""),
    }
    fd, temporary = tempfile.mkstemp(prefix=".refmod-", suffix=".tmp", dir=os.path.dirname(path))
    os.close(fd)
    try:
        save_file({"latent": latent.detach().to("cpu", torch.float16).contiguous()},
                  temporary, metadata={META_KEY: json.dumps(written)})
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if preview is not None:
        write_preview(path, preview)
    return path


def write_preview(path, image):
    """Keep a picture beside a mod. `image` is a `[H, W, 3]` or `[1, H, W, 3]`
    float tensor in 0..1. Best effort: a mod without a picture is still a mod."""
    try:
        import numpy as np
        from PIL import Image

        array = image.detach().float().cpu()
        if array.ndim == 4:
            array = array[0]
        array = (array.clamp(0, 1) * 255).round().to("cpu").numpy().astype(np.uint8)
        picture = Image.fromarray(array)
        picture.thumbnail((PREVIEW_EDGE * 4, PREVIEW_EDGE * 4))
        short = min(picture.size)
        if short > PREVIEW_EDGE:
            scale = PREVIEW_EDGE / short
            picture = picture.resize((max(1, round(picture.width * scale)),
                                      max(1, round(picture.height * scale))))
        target = os.path.splitext(path)[0] + PREVIEW_EXT
        fd, temporary = tempfile.mkstemp(prefix=".refmod-", suffix=".png", dir=os.path.dirname(path))
        os.close(fd)
        picture.save(temporary, format="PNG")
        os.replace(temporary, target)
        return target
    except Exception:  # noqa: BLE001 — the picture is a convenience, the mod is the point
        log.warning("[Continuity] could not write a preview beside %s", path, exc_info=True)
        return None


# ---- making one ---------------------------------------------------------------
#
# The compression the sibling pack does, done the same way so a compressed mod
# made here reads as one of theirs: average-pool the full encode down to a small
# even grid that keeps the source's aspect, then nudge that grid so its
# trilinear enlargement matches the full latent. Nothing but the small grid is
# optimised and no diffusion model is loaded — it is a better thumbnail of the
# latent, not a concept extractor, and the docs say so.


def grid_for(latent_h, latent_w, long_edge):
    """The even pooled grid whose long edge is `long_edge`, at the source's aspect."""
    long_edge = max(2, int(long_edge))
    if latent_h >= latent_w:
        h, w = long_edge, long_edge * latent_w / latent_h
    else:
        w, h = long_edge, long_edge * latent_h / latent_w
    h = max(2, round(h / 2) * 2)
    w = max(2, round(w / 2) * 2)
    return min(h, latent_h - latent_h % 2), min(w, latent_w - latent_w % 2)


def compress(latent, long_edge, steps=150, lr=0.02, tell=None):
    """`[1, 24, T, H, W]` -> the same at a `long_edge` grid, refined `steps` times."""
    import torch
    import torch.nn.functional as F

    _, _, t, h, w = latent.shape
    gh, gw = grid_for(h, w, long_edge)
    if (gh, gw) == (h, w):
        return latent
    full = latent.detach().float()
    small = F.adaptive_avg_pool3d(full, (t, gh, gw))
    if steps <= 0:
        return small
    # The queue runs nodes under inference mode; the refinement needs autograd.
    with torch.inference_mode(False), torch.set_grad_enabled(True):
        target = full.clone()
        param = torch.nn.Parameter(small.clone())
        opt = torch.optim.Adam([param], lr=lr)
        for i in range(steps):
            opt.zero_grad()
            up = F.interpolate(param, size=(t, h, w), mode="trilinear", align_corners=False)
            F.mse_loss(up, target).backward()
            opt.step()
            if tell and (i + 1) % 10 == 0:
                tell((i + 1) / steps)
        return param.detach()
