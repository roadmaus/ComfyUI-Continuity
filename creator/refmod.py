"""Saved RefMods as a reference source for the H3 reference pipeline.

A RefMod is a pre-encoded (and optionally compressed) reference latent produced
by the sibling `ComfyUI-MiniMaxH3Mod` pack. Attaching one is meant to be
indistinguishable, downstream, from attaching the picture or clip it was made
from: `compile.py` resolves its stored kind and `takes`, the plan numbers it,
and the encoder is handed the latent instead of decoding a file and running the
VAE. So this module is deliberately the *only* thing that knows a RefMod is a
file format rather than a media file.

**It reads the header, and only the header.** Listing, name resolution, the
cache stamp and the metadata an `Asset` is seeded from are all answered from the
safetensors header, which is a length-prefixed JSON blob. Nothing here imports
torch, ComfyUI or the sibling pack at module scope, for the same reason
`latents.py` does not: `compile.py` has to know which checkpoint a piece routes
between before any loader exists. The tensor itself is a separate, lazy read
(`load_latent`), reached only from the render half where torch is already up.

**The format is a contract owned by this pack, not an import of the sibling
one.** The two packs must install independently — a Creator with no RefMod pack
is a Creator whose picker lists nothing, not one that will not load — and a
header is a far smaller thing to agree on than a Python API. `_format_version`
exists in the file for exactly this: this reader accepts what it can prove it
understands and refuses the rest by name.
"""

from __future__ import annotations

import base64
import json
import os
import struct
from dataclasses import dataclass
from typing import Optional

# The header key the sibling pack writes, and the one legacy audio files carry.
META_KEY = "refmod_meta"
LEGACY_META_KEY = "audio_refmod_meta"

# The newest header this reader claims to understand. A file stamped higher is a
# refusal rather than a guess: the whole point of the version is to be the one
# place a future format change is allowed to reach this pack.
FORMAT_VERSION = 4

# A `concept_type` is the mod's own word for what it is; `takes` is the
# reference guide's word for what of it is the reference. Seeding one from the
# other is a convenience, and where they do not line up the mapping is the
# honest approximation rather than a fact — see `CONCEPT_TAKES`. Anything not
# named here stays `full`, which is the safe reading of "I do not know what
# this is": retain the whole reference rather than silently narrow it.
CONCEPT_TAKES = {
    "identity": "person",
    "pose_motion": "motion",
    "clothing": "object",
    "background": "scene",
    "style": "style",
    "generic": "full",
    "voice": "voice",
    "singing": "voice",
    "music_style": "music",
    "sound_fx": "ambience",
    "ambience": "ambience",
}

# How the storage root is overridden, for a test or a non-standard install. A
# path list, in the platform's own separator.
ROOTS_ENV = "CONTINUITY_REFMODS"

_EXT = ".safetensors"
_HEADER_LENGTH = 8


class RefModError(ValueError):
    """A RefMod that cannot be read, named, or is of a version we do not know."""


@dataclass(frozen=True)
class Mod:
    """One saved RefMod, as far as the compiler needs to know it.

    `path` is the file without its extension, which is what `load_latent` and
    `stamp` take; `name` is how the user and the blob address it.
    """

    name: str
    path: str
    kind: str                 # image | video | audio
    latent_h: int
    latent_w: int
    latent_t: int
    mode: str = ""
    concept_type: str = "generic"
    description: str = ""
    takes: str = ""           # seeded from concept_type; "" means unset

    @property
    def tokens(self) -> int:
        """The DiT tokens this mod injects, as the sibling pack counts them."""
        if self.kind == "audio":
            return 2 * self.latent_t
        return self.latent_t * (self.latent_h // 2) * (self.latent_w // 2)


def roots():
    """Every registered `refmods` root, in priority order.

    An explicit override wins; otherwise the folder registry, which is only
    populated once the sibling pack has registered the type. Falling back to
    `models/refmods` rather than raising is what keeps this pack usable when
    that sibling is not installed — the picker is empty, not broken.
    """
    override = os.environ.get(ROOTS_ENV)
    if override:
        return [path for path in override.split(os.pathsep) if path]
    try:
        import folder_paths
        try:
            found = [path for path in folder_paths.get_folder_paths("refmods") if path]
        except KeyError:
            found = []
        if found:
            return found
        return [os.path.join(folder_paths.models_dir, "refmods")]
    except Exception:  # noqa: BLE001 - no ComfyUI is a supported state here
        return []


def normalize(name: str) -> str:
    """A blob's mod reference -> the key `find`/`load_meta` are addressed by.

    Names use `/` whatever the platform, may carry the extension, and may not
    leave the root. This is the one place that shape is decided so a filename
    written on Windows and one written here cannot disagree.
    """
    name = str(name or "").strip().replace("\\", "/")
    if name.endswith(_EXT):
        name = name[: -len(_EXT)]
    name = name.strip("/")
    if not name:
        raise RefModError("a RefMod reference is empty")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise RefModError(f"RefMod reference {name!r} leaves the mods folder")
    return name


def _read_header(path: str) -> Optional[dict]:
    """The safetensors JSON header, or None if the file is not readable as one.

    Eight bytes of little-endian length, then that many bytes of JSON. Anything
    shorter, longer or unparseable is not a safetensors file, which for this
    reader and a missing file are the same answer: not a mod.
    """
    try:
        with open(path, "rb") as handle:
            size = struct.unpack("<Q", handle.read(_HEADER_LENGTH))[0]
            raw = handle.read(size)
    except (OSError, struct.error):
        return None
    try:
        header = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return header if isinstance(header, dict) else None


def _meta_of(path: str) -> Optional[dict]:
    header = _read_header(path)
    if header is None:
        return None
    meta = header.get("__metadata__") or {}
    for key in (META_KEY, LEGACY_META_KEY):
        blob = meta.get(key)
        if not isinstance(blob, str):
            continue
        try:
            parsed = json.loads(blob)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _kind_of(meta: dict, shape) -> str:
    kind = str(meta.get("kind") or "").strip()
    if kind in ("image", "video", "audio"):
        return kind
    # A v2 header predates a trustworthy `kind` on some files; the rank of the
    # latent is the fact behind it. Audio is [1, 32, 2, T] and visual is
    # [1, 24, T, H, W], so the channel count tells them apart.
    if shape and len(shape) == 4 and shape[1] == 32:
        return "audio"
    if shape and len(shape) == 5:
        return "image" if int(shape[2]) == 1 else "video"
    return "image"


def find(name: str) -> Optional[str]:
    """The mod's path without extension, or None. First root wins."""
    key = normalize(name)
    for root in roots():
        candidate = os.path.join(root, *key.split("/"))
        if os.path.isfile(candidate + _EXT):
            return candidate
        # A legacy JSON sidecar with no safetensors beside it is not a mod, so
        # nothing to do here — the header is the source of truth.
    return None


def load_meta(name: str) -> Optional[Mod]:
    """The header a mod declares, or None when it is not there or not a mod."""
    path = find(name)
    if path is None:
        return None
    meta = _meta_of(path + _EXT)
    if meta is None:
        return None
    version = int(meta.get("_format_version", 2) or 2)
    if version > FORMAT_VERSION:
        raise RefModError(
            f"RefMod {normalize(name)!r} is format v{version}; this build "
            f"understands up to v{FORMAT_VERSION}. Update the pack."
        )
    # The tensor shape lives in the header beside the metadata, so the declared
    # dims can be checked against it without loading anything.
    header = _read_header(path + _EXT) or {}
    tensor = header.get("latent") or {}
    shape = tensor.get("shape")
    kind = _kind_of(meta, shape)
    latent_h = int(meta.get("latent_h") or (shape[3] if shape and len(shape) == 5 else 0))
    latent_w = int(meta.get("latent_w") or (shape[4] if shape and len(shape) == 5 else 0))
    latent_t = int(meta.get("latent_t") or (shape[2] if shape and len(shape) == 5
                                            else (shape[-1] if shape else 1)))
    concept = str(meta.get("concept_type") or "generic").strip() or "generic"
    return Mod(
        name=normalize(name),
        path=path,
        kind=kind,
        latent_h=latent_h,
        latent_w=latent_w,
        latent_t=latent_t,
        mode=str(meta.get("mode") or ""),
        concept_type=concept,
        description=str(meta.get("description") or ""),
        takes=CONCEPT_TAKES.get(concept, ""),
    )


def list_names() -> list[str]:
    """Every readable mod under every root, `sub/name` form, sorted.

    Subfolders are walked, and a file without a RefMod header is not listed —
    the folder is the sibling pack's, and anything else in it is not ours to
    offer.
    """
    seen: dict[str, None] = {}
    for root in roots():
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in (".git", "__pycache__", "graph_presets",
                                        THUMB_DIR)]
            for filename in filenames:
                if not filename.endswith(_EXT):
                    continue
                full = os.path.join(dirpath, filename)
                if _meta_of(full) is None:
                    continue
                rel = os.path.relpath(full, root)[: -len(_EXT)].replace(os.sep, "/")
                seen.setdefault(rel, None)
    return sorted(seen)


def stamp(name: str) -> Optional[dict]:
    """What a presentation decode of this mod depends on, for a cache key.

    The file's identity — path, mtime and size — exactly as `media.stamp` gives
    it for a media file, so re-saving a mod under the same name misses the
    cache. None when the file is gone, which the caller must treat as "not
    cacheable" rather than "unchanged".
    """
    path = find(name)
    if path is None:
        return None
    full = path + _EXT
    try:
        info = os.stat(full)
    except OSError:
        return None
    return {"path": os.path.realpath(full), "mtime": info.st_mtime, "size": info.st_size}


def read_preview(name: str):
    """The stored thumbnail bytes, or None. A header read, no tensor."""
    path = find(name)
    if path is None:
        return None
    meta = _meta_of(path + _EXT) or {}
    blob = meta.get("preview")
    if not isinstance(blob, str) or not blob:
        return None
    try:
        return base64.b64decode(blob)
    except (ValueError, TypeError):
        return None


# Where a decoded preview is cached, under the mods root. A dot-directory so it
# is not listed as a shelf; `list_names` skips it by name.
THUMB_DIR = ".thumbs"


def thumb_file(name: str) -> str:
    """Where a mod's decoded-preview cache lives. -> absolute path, not made."""
    destinations = roots()
    if not destinations:
        raise RefModError("no refmods folder is registered")
    rel = normalize(name)
    return os.path.join(destinations[0], THUMB_DIR, *rel.split("/")) + ".png"


def read_thumb(name: str):
    """A previously decoded preview, or None."""
    try:
        path = thumb_file(name)
    except RefModError:
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def write_thumb(name: str, data: bytes) -> None:
    """Cache a decoded preview. Atomic, so a half-written PNG never reads back."""
    path = thumb_file(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    staging = path + ".tmp"
    try:
        with open(staging, "wb") as handle:
            handle.write(data)
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def load_latent(name: str, device: str = "cpu"):
    """The stored tensor. The one function here that needs torch/safetensors.

    Imported at call time rather than module scope, so the compiler half can
    keep importing this module under bare Python. `device` is honoured by the
    loader; the caller moves it onto the render device if it needs to.
    """
    path = find(name)
    if path is None:
        raise RefModError(f"RefMod {normalize(name)!r} was not found in {roots()}")
    from safetensors.torch import load_file  # noqa: PLC0415 - see docstring
    return load_file(path + _EXT, device=device)["latent"].clone()


def save_mod(name: str, latent, *, concept_type: str = "generic",
             description: str = "", mode: str = "encode", source: str = "",
             pool: str = "", subfolder: str = "", tags=(), preview=None) -> str:
    """Write `latent` as a RefMod under the first root. -> path without extension.

    The inverse of `load_latent` and the same one lazy import: the Creator's own
    "Save as RefMod" node is the caller, and the compiler half must never need
    torch to reach this module. The header is the one `load_meta` reads back —
    the two are held to each other by `tests/test_refmod.py` round-tripping a
    file written here.
    """
    if latent.ndim != 5 or int(latent.shape[1]) != 24:
        raise RefModError(
            f"a visual RefMod needs a [1, 24, T, H, W] latent, got {tuple(latent.shape)}")
    roots_found = roots()
    if not roots_found:
        raise RefModError("no refmods folder is registered; nothing to save into")
    key = normalize(name)
    rel = "/".join(part for part in
                   (str(subfolder or "").replace("\\", "/").strip("/"), key) if part)
    if any(part in ("..", ".", "graph_presets") for part in rel.split("/")):
        raise RefModError(f"RefMod name {rel!r} leaves the mods folder")
    destination = os.path.join(roots_found[0], *rel.split("/")) + _EXT
    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)

    tensor = latent.detach().to("cpu").contiguous()
    _, _, latent_t, latent_h, latent_w = tensor.shape
    kind = "image" if int(latent_t) == 1 else "video"
    meta = {
        "name": key,
        "kind": kind,
        "latent_h": int(latent_h),
        "latent_w": int(latent_w),
        "latent_t": int(latent_t),
        "mode": mode,
        "source": source,
        "source_shape": f"{int(latent_t)}x{int(latent_h)}x{int(latent_w)}",
        "pool": pool,
        "optimize_steps": 0,
        "tags": list(tags),
        "description": str(description or ""),
        "concept_type": str(concept_type or "generic"),
        "_format_version": FORMAT_VERSION,
        "sample_rate": 32000,
    }
    # A thumbnail of what was saved, in the header: the picker has no VAE to
    # decode a latent with, and a preview written at the one moment the pixels
    # are already in hand is cheaper than decoding on every grid paint.
    if preview:
        meta["preview"] = base64.b64encode(bytes(preview)).decode("ascii")
    # Atomic, like the sibling pack's writer: a half-flushed file is a corrupt
    # latent that reads back as a plausible one.
    from safetensors.torch import save_file  # noqa: PLC0415 - see docstring
    staging = destination + ".tmp"
    try:
        save_file({"latent": tensor}, staging,
                  metadata={META_KEY: json.dumps(meta)})
        os.replace(staging, destination)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)
    return destination[: -len(_EXT)]
