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

A latent belongs to one VAE. An H3 mod is a tensor in the H3 video VAE's
space and means nothing to Flux 2 Klein, whose references are latents of a
different VAE at a different stride — which is why "a RefMod per family" is
really one mod per *latent space*, all made from the same picture. `SPACES`
names the spaces this pack reads, keyed by `vaekind`'s ids, and every header
carries (or, for the sibling pack's files, implies) which one its tensor is
in. The picture stays the truth on the piece: an asset carries `mods`, a map
from space to mod, and the family rendering it takes the mod for its own
space or encodes the picture as it always has. See `compile.Asset.mods`.

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
# older files, and so is this; a newer one is refused by name. A version-5
# file is a *bundle* — several references as `ref_<i>` tensors under one
# header — and is read here when it holds exactly one visual reference, which
# is what their Save node writes for a single mod now; a bundle of several is
# refused by count, since one asset is one label — and split into its members
# when it is imported (`split_bundle`), which is the way in for one.
FORMAT_VERSION = 5
BUNDLE_VERSION = 5
# What this pack writes: a standalone file, which is their version 4 — one
# `latent` tensor, the shape every loader of theirs and ours reads.
STANDALONE_VERSION = 4
LATENT_CHANNELS = 24

# The latent spaces a mod can be in, by `vaekind` id. Each says the tensor
# shape its VAE encodes to — `dims` counting the batch — and how a grid turns
# into DiT tokens: H3 patches 2x2 latent cells into one token, Flux 2's VAE
# already packs a 2x2 into its 128 channels so a cell is a token (the reason
# a 1 MP Klein reference is 4,096 tokens, not 1,024). `even` is whether the
# grid has to hold whole patches. `stride` is source pixels per latent cell,
# which is what `media._source_size` reads a mod's picture size off.
#
# MiniMax H3 Image has a space of its own though its tensor has H3's shape:
# core's `H3ImageVAE.encode` draws a seeded sample of the posterior where the
# video VAE returns its mean, and the image model anchors a reference at a
# 1024-2048 short edge where the video model's mods are made at 1024. A file
# that is right for one is the wrong latent at the wrong size for the other.
# H3's stays first: a file that names no space is told by its shape, and the
# sibling pack's are H3's.
SPACES = {
    "h3_video": {"channels": 24, "dims": 5, "patch": 2, "even": True, "stride": 16,
                 "label": "MiniMax H3"},
    "h3_image": {"channels": 24, "dims": 5, "patch": 2, "even": True, "stride": 16,
                 "label": "MiniMax H3 Image"},
    "flux2": {"channels": 128, "dims": 4, "patch": 1, "even": False, "stride": 16,
              "label": "Flux 2"},
}
DEFAULT_SPACE = "h3_video"
# The header field that names the space. Ours; the sibling pack's files have
# none and are H3's by definition, which `_space_of` reads off the channels.
SPACE_KEY = "vae_kind"
# The Klein packs' files. malcolmrey's `ComfyUI-Flux2Klein9Mod` (the
# generator behind the browser's thousand `fk9_*_refmod` files) writes one
# `samples` tensor of `[B, 128, H, W]` — B source pictures of one person,
# each its own reference — under `klein9_refmod_meta`; DainamoLabs'
# `ComfyUI-FluxKleinRefMods` writes `reference_<i>` tensors of `[1, 128, H, W]`
# under `klein_refmod_meta`. Both packs unroll the file into one
# `reference_latents` entry per picture at apply time, and so does this one
# (`refmodnode`). Read here; never written — ours carry `refmod_meta`.
KLEIN_META_KEYS = ("klein_refmod_meta", "klein9_refmod_meta")
KLEIN_SPACE = "flux2"
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

    -> dict: the mod's own metadata, plus `shape`, `dtype`, `tokens`, `space`
    and the dims read off the tensor itself. The dims come from the tensor and
    not from the metadata: the metadata is what somebody wrote, the shape is
    what will be handed to the DiT, and a mismatch between the two is refused
    here rather than discovered as a wrong-sized reference mid-render.
    `tensor` is the key the latent sits under — `latent` in a standalone file,
    `ref_0` in a one-reference bundle — which is what `load_latent` reads.
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

    metadata = table.get("__metadata__") or {}
    written = metadata.get(META_KEY)
    if not written:
        # The sibling pack keeps audio mods under a second key. Named so the
        # refusal says what the file is rather than "no metadata".
        if metadata.get("audio_refmod_meta"):
            raise RefModError(f"{path}: an audio RefMod — voices are bound as files, not mods")
        for key in KLEIN_META_KEYS:
            if metadata.get(key):
                return _klein_header(path, table, metadata[key])
        # Not a mod at all. The file somebody drops here by mistake is a
        # LoRA — the browser the Klein sets come from lists ten of those for
        # every RefMod — so name it, and where it goes.
        if any("lora" in str(key).lower() for key in table):
            raise RefModError(
                f"{path}: a LoRA, not a RefMod — it goes in models/loras and onto "
                f"a member's *wears* row, not their looks")
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
    tensor_key = "latent"
    if version >= BUNDLE_VERSION and str(meta.get("kind")) == "bundle":
        meta, tensor_key = _unbundle(path, meta)
    kind = str(meta.get("kind", "image") or "image")
    if kind == "audio":
        raise RefModError(f"{path}: an audio RefMod — voices are bound as files, not mods")
    if kind not in KINDS:
        raise RefModError(f"{path}: unknown RefMod kind {kind!r}")

    entry = table.get(tensor_key)
    if not isinstance(entry, dict):
        raise RefModError(f"{path}: no {tensor_key!r} tensor in the file")
    shape = [int(v) for v in entry.get("shape", [])]
    space_id = _space_of(path, meta, shape)
    space = SPACES[space_id]
    if len(shape) != space["dims"] or shape[0] != 1 or shape[1] != space["channels"]:
        want = "[1, %d, %s]" % (space["channels"], "T, H, W" if space["dims"] == 5 else "H, W")
        raise RefModError(f"{path}: latent is {shape}, not {want} ({space['label']})")
    if space["dims"] == 5:
        _, _, latent_t, latent_h, latent_w = shape
    else:
        latent_t, latent_h, latent_w = 1, shape[2], shape[3]
        if kind == "video":
            raise RefModError(f"{path}: a video RefMod in a still space ({space['label']})")
    if kind == "image" and latent_t != 1:
        raise RefModError(f"{path}: an image RefMod with {latent_t} latent frames")
    patch = space["patch"]
    if latent_h < patch or latent_w < patch:
        raise RefModError(f"{path}: latent grid {latent_h}x{latent_w} is too small")
    if space["even"] and (latent_h % patch or latent_w % patch):
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
        "tokens": latent_t * (latent_h // patch) * (latent_w // patch),
        "format_version": version,
        "mode": _mode(meta.get("mode")),
        "description": str(meta.get("description", "") or ""),
        "name": str(meta.get("name", "") or ""),
        "space": space_id,
        "tensor": tensor_key,
        # How many references the file holds: one, here. A Klein pack's file
        # holds a picture set (`_klein_header`).
        "members": 1,
        "tensors": [(tensor_key, None)],
    })
    return out


def _klein_header(path, table, written):
    """A Klein pack's file -> the same header dict, one reference per picture.

    `tensors` is what `load_latents` reads: `(key, index)` per member — the
    row of a `samples` batch, or a whole `reference_<i>` tensor. `tokens` is
    every member's cells summed, since every one of them rides into the
    conditioning. `latent_h/w` are the first member's, for the picker's grid
    and `media._source_size`; members may differ (DainamoLabs keeps each
    picture's own shape).
    """
    try:
        meta = json.loads(written)
    except ValueError as exc:
        raise RefModError(f"{path}: Klein RefMod metadata is not JSON") from exc
    if not isinstance(meta, dict):
        raise RefModError(f"{path}: Klein RefMod metadata is not an object")
    space = SPACES[KLEIN_SPACE]
    tensors = []
    if isinstance(table.get("samples"), dict):
        shape = [int(v) for v in table["samples"].get("shape", [])]
        if len(shape) != 4 or shape[1] != space["channels"] or shape[0] < 1:
            raise RefModError(f"{path}: Klein 'samples' is {shape}, not [B, 128, H, W]")
        tensors = [("samples", index, shape[2], shape[3]) for index in range(shape[0])]
        dtype = str(table["samples"].get("dtype", ""))
    else:
        keys = sorted((k for k in table if k.startswith("reference_")),
                      key=lambda k: int(k.rsplit("_", 1)[-1]) if k.rsplit("_", 1)[-1].isdigit() else 0)
        for key in keys:
            shape = [int(v) for v in table[key].get("shape", [])]
            if len(shape) != 4 or shape[1] != space["channels"] or shape[0] != 1:
                raise RefModError(f"{path}: Klein {key!r} is {shape}, not [1, 128, H, W]")
            tensors.append((key, None, shape[2], shape[3]))
        dtype = str(table[keys[0]].get("dtype", "")) if keys else ""
    if not tensors:
        raise RefModError(f"{path}: a Klein RefMod with no reference tensors")
    _, _, first_h, first_w = tensors[0]
    mode = str(meta.get("mode", "encode") or "encode")
    out = dict(meta)
    out.update({
        "kind": "image",
        "latent_t": 1,
        "latent_h": first_h,
        "latent_w": first_w,
        "shape": [1, space["channels"], first_h, first_w],
        "dtype": dtype,
        "tokens": sum(h * w for _, _, h, w in tensors),
        "format_version": int(meta.get("format_version", 0) or 0),
        "mode": "training" if mode in ("pooled", "training", "refined") else "encode",
        "description": str(meta.get("description", "") or ""),
        "name": str(meta.get("name", "") or ""),
        "space": KLEIN_SPACE,
        "tensor": tensors[0][0],
        "members": len(tensors),
        "tensors": [(key, index) for key, index, _, _ in tensors],
        # Theirs: `source` says so for the listing, and nothing here remakes it.
        "source": "set" if len(tensors) > 1 else "image",
    })
    return out


def _space_of(path, meta, shape):
    """Which latent space a file's tensor is in.

    Ours say so (`vae_kind`); a name this build does not know is refused
    rather than guessed at. The sibling pack's say nothing, and theirs are
    H3's — but read off the channel count rather than assumed, so a file that
    is neither is refused by shape rather than handed to the H3 encoder.
    """
    named = meta.get(SPACE_KEY)
    if named:
        if named not in SPACES:
            raise RefModError(
                f"{path}: a RefMod for {named!r}, which this pack does not read "
                f"(it reads {', '.join(SPACES)})")
        return str(named)
    for space_id, space in SPACES.items():
        if len(shape) == space["dims"] and len(shape) > 1 and shape[1] == space["channels"]:
            return space_id
    return DEFAULT_SPACE


def _unbundle(path, meta):
    """A version-5 bundle -> `(the one member's metadata, its tensor key)`.

    Their bundle is an ordered `members` list, each member a version-4 header
    of its own, with tensors under `ref_<index>`. One visual member is one
    reference and reads as one; more than one would be several labels behind
    one handle, which nothing here can cite, so it is refused by count with
    the way out named.
    """
    members = meta.get("members")
    if not isinstance(members, list) or not members:
        raise RefModError(f"{path}: a RefMod bundle with no members")
    visual = [(index, m) for index, m in enumerate(members)
              if isinstance(m, dict) and str(m.get("kind", "image")) != "audio"]
    if len(visual) != 1:
        if not visual:
            raise RefModError(f"{path}: an audio RefMod — voices are bound as files, not mods")
        raise RefModError(
            f"{path}: a bundle of {len(visual)} references — one RefMod is one "
            f"reference here; split it with the sibling pack's Save node")
    index, member = visual[0]
    out = dict(member)
    for key in ("name", "description", "tags", "concept_type", SPACE_KEY, "made_by", "source_file"):
        if key not in out and key in meta:
            out[key] = meta[key]
    return out, f"ref_{index}"


def space_label(space_id):
    """The family name a space goes by in a sentence."""
    return SPACES.get(space_id, {}).get("label", space_id)


def parse_mods(raw, owner="", allowed=None):
    """An asset's `mods` field -> `{space: "refmod:<name>"}`, checked.

    The map a picture carries from latent space to the mod made of it for
    that space. Every key is a space this pack reads, every value a mod name
    that parses; `allowed` narrows the keys further where the caller knows
    which spaces make sense. Absent or empty is `{}`.
    """
    if raw in (None, "", {}):
        return {}
    if not isinstance(raw, dict):
        raise RefModError(f"{owner}mods must be a map of latent space to RefMod")
    out = {}
    for space_id, filename in raw.items():
        if space_id not in SPACES:
            raise RefModError(
                f"{owner}mods names a latent space {space_id!r} this pack does "
                f"not read (it reads {', '.join(SPACES)})")
        if allowed is not None and space_id not in allowed:
            raise RefModError(f"{owner}mods for {space_id!r} means nothing here")
        if not filename:
            continue
        name = str(filename)
        if not is_mod(name):
            raise RefModError(f"{owner}mods[{space_id!r}] is not a RefMod name: {name!r}")
        name_of(name)  # refused by name where it walks out of the folder
        out[space_id] = name
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

    A row is the asset row `assets.scan` produces, with the mod's own
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
                rows.append(row_for(path, name, meta=meta, stat=stat))
    return rows, sorted(folders)


def row_for(path, name, meta=None, stat=None):
    """One mod as the picker row every route answers with — the listing, the
    make job and the file routes below all say the same thing about a file."""
    meta = meta or header(path)
    stat = stat or os.stat(path)
    subfolder, _, stem = name.rpartition("/")
    return {
        "path": filename_of(name),
        "name": stem,
        "subfolder": subfolder,
        "kind": meta["kind"],
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "mod": True,
        "mode": meta["mode"],
        # Which VAE's latent it is, and so which families can read it.
        "space": meta["space"],
        "space_label": space_label(meta["space"]),
        # `stack` for a character-as-one-file — several sources end to end —
        # against `image` / `video` for one encoded source. Their word.
        "source": str(meta.get("source", "") or ""),
        "tokens": meta["tokens"],
        # How many references the file holds — a Klein pack's picture set is
        # several, each riding into the conditioning on its own.
        "members": meta.get("members", 1),
        "grid": [meta["latent_t"], meta["latent_h"], meta["latent_w"]],
        "description": meta["description"],
        # Whose it is, as far as the header says: ours, or the sibling pack's.
        "foreign": meta.get("made_by") != "continuity",
        "preview": preview_path(path) is not None,
        # The picture it was made of, and whether it is still there to be read
        # again — what a re-encode in the other mode needs (`routes/refmod`).
        # Ours only; the sibling pack's files name nothing here.
        "source_file": str(meta.get("source_file", "") or ""),
        "source_present": _source_present(meta.get("source_file")),
    }


def _source_present(source):
    """Whether the input-folder path a header names still resolves. A stack's
    field is several names joined, and a stack is not remade from them."""
    name = str(source or "")
    if not name or "," in name:
        return False
    try:
        import folder_paths
        return bool(folder_paths.exists_annotated_filepath(name))
    except Exception:  # noqa: BLE001 — no core, or a malformed annotation: not there
        return False


# ---- the file itself ------------------------------------------------------------
#
# Rename, move, delete, and one field of the header — the whole of what "edit a
# RefMod" can mean, since the latent is not editable. All of it is stdlib: the
# safetensors layout is an 8-byte length, a JSON header padded to that length,
# and the tensor bytes, whose offsets in the header are relative to their own
# start. So a header can be rewritten without touching a tensor, and a file can
# be moved with its picture as two renames.


def sidecars(path):
    """The files that travel with a mod: its picture, under any name it is kept."""
    return [p for p in (os.path.splitext(path)[0] + ext
                        for ext in (PREVIEW_EXT, ".webp", ".jpg", ".jpeg")) if os.path.isfile(p)]


def move(filename, new_name):
    """`refmod:<name>` -> `refmod:<new_name>`, inside the root it is already in.
    -> the new path. Refuses to overwrite: a mod is somebody's character."""
    import folder_paths

    source = resolve(filename)
    clean = name_of(new_name)
    root = next(r for r in roots() if folder_paths.is_within_directory(r, source))
    target = os.path.join(root, *clean.split("/")) + EXT
    if not folder_paths.is_within_directory(root, os.path.realpath(os.path.dirname(target) or root)):
        raise RefModError(f"{new_name!r} is not a RefMod name")
    if os.path.realpath(target) == os.path.realpath(source):
        return source
    if os.path.exists(target):
        raise RefModError(f"a RefMod named {clean!r} is already there")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    for extra in sidecars(source):
        os.replace(extra, os.path.splitext(target)[0] + os.path.splitext(extra)[1])
    os.replace(source, target)
    return target


def remove(filename):
    """Delete a mod and its picture."""
    path = resolve(filename)
    for extra in sidecars(path):
        os.unlink(extra)
    os.unlink(path)


def rewrite_meta(path, **fields):
    """Change fields of `refmod_meta` in place — the description, mostly.

    The header is re-serialised and padded to a multiple of eight, as the
    format asks; the tensor bytes are copied after it unchanged. Written to a
    temporary file beside the original and swapped in, like `save`.
    """
    with open(path, "rb") as handle:
        (length,) = struct.unpack("<Q", handle.read(8))
        table = json.loads(handle.read(length).decode("utf-8"))
        metadata = table.get("__metadata__") or {}
        meta = json.loads(metadata.get(META_KEY) or "{}")
        meta.update(fields)
        metadata[META_KEY] = json.dumps(meta)
        table["__metadata__"] = metadata
        encoded = json.dumps(table, separators=(",", ":")).encode("utf-8")
        encoded += b" " * (-len(encoded) % 8)
        fd, temporary = tempfile.mkstemp(prefix=".refmod-", suffix=".tmp",
                                         dir=os.path.dirname(path))
        with os.fdopen(fd, "wb") as out:
            out.write(struct.pack("<Q", len(encoded)))
            out.write(encoded)
            while True:
                chunk = handle.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
    os.replace(temporary, path)
    return path


def adopt(temporary, name):
    """Take a file somebody uploaded into the mod folder as `<name>`, once the
    header reads as a mod. -> `(path, meta)`. The temporary file is consumed
    either way; a refusal deletes it.

    A bundle of several references is split on the way in (`split_bundle`):
    one asset is one label here, so the file that cannot be cited whole is
    filed as the references it holds. -> `(first path, its meta)` then, with
    every part's path under `meta["parts"]`.
    """
    try:
        if len(bundle_members(temporary)) > 1:
            paths = split_bundle(temporary, name)
            meta = dict(header(paths[0]))
            meta["parts"] = paths
            return paths[0], meta
        meta = header(temporary)
        clean = name_of(name)
        target = os.path.join(home(), *clean.split("/")) + EXT
        if os.path.exists(target):
            raise RefModError(f"a RefMod named {clean!r} is already there")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target, meta


# ---- bundles ------------------------------------------------------------------
#
# The sibling pack's version-5 file holds several references under one header:
# a `members` list of ordinary version-4 headers, and the tensors as `ref_<i>`.
# One reference reads as one here (`_unbundle`); several are one handle
# standing for several labels, which nothing here can cite. So a bundle of
# several is split when it is imported — each visual member written out as the
# standalone file it would have been — and a member's mods can be written out
# as one bundle for their loader, which is the one file a character travels in
# over there. Both are the safetensors layout copied byte for byte: no tensor
# is decoded, so neither needs torch.


def _table(path):
    """`(the header table, where the tensor bytes start)`. Bounded the way
    `header` is: an upload that is not a safetensors file has a length field
    that is whatever its first eight bytes are, and reading that much is a
    MemoryError, not a refusal."""
    with open(path, "rb") as handle:
        raw = handle.read(8)
        if len(raw) < 8:
            raise ValueError(f"{path}: not a safetensors file")
        (length,) = struct.unpack("<Q", raw)
        if length <= 0 or length > 64 * 1024 * 1024:
            raise ValueError(f"{path}: not a safetensors file")
        return json.loads(handle.read(length).decode("utf-8")), 8 + length


def _bytes_of(path, start, entry):
    first, last = entry["data_offsets"]
    with open(path, "rb") as handle:
        handle.seek(start + first)
        return handle.read(last - first)


def _write_raw(path, tensors, metadata):
    """`tensors` as `[(key, dtype, shape, bytes)]` into one safetensors file,
    written beside its target and swapped in, like `save`."""
    table, offset = {"__metadata__": metadata}, 0
    for key, dtype, shape, data in tensors:
        table[key] = {"dtype": dtype, "shape": list(shape), "data_offsets": [offset, offset + len(data)]}
        offset += len(data)
    encoded = json.dumps(table, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 8)
    fd, temporary = tempfile.mkstemp(prefix=".refmod-", suffix=".tmp", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(struct.pack("<Q", len(encoded)))
            out.write(encoded)
            for *_, data in tensors:
                out.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def bundle_members(path):
    """The visual members of a version-5 bundle, as `[(index, member meta)]`,
    or `[]` for any file that is not one. Audio members are left out: a voice
    is bound as a file here, never as a mod."""
    try:
        table, _ = _table(path)
        meta = json.loads((table.get("__metadata__") or {}).get(META_KEY) or "{}")
    except (OSError, ValueError, struct.error):
        return []
    if not isinstance(meta, dict) or str(meta.get("kind")) != "bundle" \
            or int(meta.get("_format_version", 1) or 1) < BUNDLE_VERSION:
        return []
    members = meta.get("members")
    if not isinstance(members, list):
        return []
    return [(index, member) for index, member in enumerate(members)
            if isinstance(member, dict) and str(member.get("kind", "image")) != "audio"]


def split_bundle(source, name):
    """Every visual member of the bundle at `source` as its own standalone
    file, `<name>-1`, `<name>-2`, ... -> their paths, in the bundle's order.

    All or nothing: a name already taken refuses the whole import before a
    byte is written, and a member that does not read back as a mod takes the
    ones written before it out again.
    """
    table, start = _table(source)
    whole = json.loads(table["__metadata__"][META_KEY])
    members = bundle_members(source)
    clean = name_of(name)
    targets = [os.path.join(home(), *f"{clean}-{n}".split("/")) + EXT for n in range(1, len(members) + 1)]
    for target in targets:
        if os.path.exists(target):
            raise RefModError(f"a RefMod named {os.path.basename(target)[:-len(EXT)]!r} is already there")
    written = []
    try:
        for (index, member), target in zip(members, targets):
            entry = table.get(f"ref_{index}")
            if not isinstance(entry, dict):
                raise RefModError(f"{source}: bundle member {index} has no 'ref_{index}' tensor")
            meta = dict(member)
            for key in ("description", "tags", "concept_type", SPACE_KEY, "made_by", "source_file"):
                if key not in meta and key in whole:
                    meta[key] = whole[key]
            meta["_format_version"] = STANDALONE_VERSION
            meta["name"] = os.path.basename(target)[:-len(EXT)]
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _write_raw(target, [("latent", entry["dtype"], entry["shape"], _bytes_of(source, start, entry))],
                       {META_KEY: json.dumps(meta)})
            written.append(target)
            header(target)
    except Exception:
        for path in written:
            if os.path.exists(path):
                os.unlink(path)
        raise
    return written


def write_bundle(paths, name, target):
    """Several H3 mods as one version-5 bundle at `target`, for the sibling
    pack's loader. -> `target`.

    Each member is the file's own header made a version-4 member, and its
    tensor the file's bytes. H3's space only — theirs is an H3 pack, and a
    Klein latent in their bundle is a file their loader would choke on — and
    one reference per file, since a member is one reference.
    """
    tensors, members = [], []
    for index, path in enumerate(paths):
        meta = header(path)
        if meta["space"] != DEFAULT_SPACE:
            raise RefModError(f"{os.path.basename(path)} is a {space_label(meta['space'])} RefMod; "
                              f"a bundle holds {space_label(DEFAULT_SPACE)} ones")
        if meta.get("members", 1) != 1:
            raise RefModError(f"{os.path.basename(path)} holds several references already")
        table, start = _table(path)
        entry = table[meta["tensor"]]
        tensors.append((f"ref_{index}", entry["dtype"], entry["shape"], _bytes_of(path, start, entry)))
        written = json.loads((table.get("__metadata__") or {}).get(META_KEY) or "{}")
        if meta["tensor"] != "latent":
            written, _ = _unbundle(path, written)
        written.update({"_format_version": STANDALONE_VERSION, "kind": meta["kind"],
                        "latent_t": meta["latent_t"], "latent_h": meta["latent_h"],
                        "latent_w": meta["latent_w"]})
        members.append(written)
    if not members:
        raise RefModError("nothing to bundle")
    return _write_raw(target, tensors, {META_KEY: json.dumps({
        "_format_version": BUNDLE_VERSION, "kind": "bundle", "name": str(name),
        "members": members, "made_by": "continuity", SPACE_KEY: DEFAULT_SPACE,
    })})


# ---- the tensor ---------------------------------------------------------------


def load_latent(path, meta=None):
    """The mod's one latent as a float32 CPU tensor, checked against its
    header. A file of several references is refused here — `load_latents`
    is the reader for those, and the H3 encoder wants one."""
    meta = meta or header(path)
    if meta.get("members", 1) != 1:
        raise RefModError(f"{path}: a set of {meta['members']} references, not one")
    return load_latents(path, meta)[0]


def load_latents(path, meta=None):
    """Every reference in the file, each a float32 CPU tensor of the header's
    shape — one for ours and the sibling pack's, one per picture for a Klein
    pack's set. In the order they were written."""
    from safetensors.torch import load_file

    meta = meta or header(path)
    table = load_file(path, device="cpu")
    out = []
    for key, index in meta.get("tensors") or [(meta.get("tensor", "latent"), None)]:
        tensor = table[key]
        if index is not None:
            tensor = tensor[index:index + 1]
        if meta["members"] == 1 and list(tensor.shape) != meta["shape"]:
            raise RefModError(f"{path}: latent is {list(tensor.shape)}, header says {meta['shape']}")
        # `.clone()` drops the file mmap so the file can be replaced under its
        # name while a render holds the tensor — the same reason the sibling
        # pack does it.
        out.append(tensor.clone().float())
    return out


def save(name, latent, meta, preview=None, space=DEFAULT_SPACE):
    """Write `<home>/<name>.safetensors` and its preview. -> the mod's path.

    The metadata is the sibling pack's schema with three fields of ours beside
    it (`made_by`, `source_file`, `vae_kind`); their loader ignores what it
    does not know and so does ours. `space` is the latent space the tensor is
    in, checked against its shape. Written to a temporary file and renamed, so
    a mod is either whole on disk or not there.
    """
    import torch
    from safetensors.torch import save_file

    rules = SPACES.get(space)
    if rules is None:
        raise RefModError(f"{space!r} is not a latent space this pack writes")
    if not isinstance(latent, torch.Tensor) or latent.ndim != rules["dims"] \
            or latent.shape[0] != 1 or latent.shape[1] != rules["channels"]:
        want = "T, H, W" if rules["dims"] == 5 else "H, W"
        raise RefModError(f"a {rules['label']} RefMod latent is [1, {rules['channels']}, {want}], "
                          f"got {list(getattr(latent, 'shape', []))}")
    clean = name_of(name)
    path = os.path.join(home(), *clean.split("/")) + EXT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if rules["dims"] == 5:
        _, _, latent_t, latent_h, latent_w = latent.shape
    else:
        latent_t, latent_h, latent_w = 1, latent.shape[2], latent.shape[3]
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
        "_format_version": STANDALONE_VERSION,
        "sample_rate": 32000,
        "made_by": "continuity",
        "source_file": str(meta.get("source_file", "") or ""),
        SPACE_KEY: space,
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


def compress(latent, long_edge, steps=150, lr=0.02, tell=None, grid=None, motion=0.0):
    """`[1, C, T, H, W]` (or `[1, C, H, W]`) -> the same at a `long_edge` grid,
    refined `steps` times.

    `grid` names the pooled `(H, W)` outright — a stack pools every source to
    one square grid whatever its aspect, since frames of different shapes
    cannot share a latent — and `long_edge` picks it at the source's aspect
    otherwise. A still space's 4-D latent is pooled and enlarged in two
    dimensions; the loss is the same.

    `motion` weights the fit toward what moves (`motion_weights`): a clip's
    small grid has few cells to spend, and a plain fit spends them evenly over
    a wall that never changes and a hand that does. Zero is the sibling pack's
    plain fit, and a still or a one-frame latent has no motion to weigh.
    """
    import torch
    import torch.nn.functional as F

    flat = latent.ndim == 4
    if flat:
        _, _, h, w = latent.shape
        t = 1
    else:
        _, _, t, h, w = latent.shape
    gh, gw = grid if grid else grid_for(h, w, long_edge)
    if (gh, gw) == (h, w):
        return latent
    full = latent.detach().float()
    if flat:
        small = F.adaptive_avg_pool2d(full, (gh, gw))
        size, mode = (h, w), "bilinear"
    else:
        small = F.adaptive_avg_pool3d(full, (t, gh, gw))
        size, mode = (t, h, w), "trilinear"
    if steps <= 0:
        return small
    weights = motion_weights(full, motion) if not flat else None
    # The queue runs nodes under inference mode; the refinement needs autograd.
    with torch.inference_mode(False), torch.set_grad_enabled(True):
        target = full.clone()
        param = torch.nn.Parameter(small.clone())
        opt = torch.optim.Adam([param], lr=lr)
        for i in range(steps):
            opt.zero_grad()
            up = F.interpolate(param, size=size, mode=mode, align_corners=False)
            if weights is None:
                loss = F.mse_loss(up, target)
            else:
                loss = (weights * (up - target) ** 2).mean()
            loss.backward()
            opt.step()
            if tell and (i + 1) % 10 == 0:
                tell((i + 1) / steps)
        return param.detach()


def motion_weights(latent, strength):
    """Per-cell weights for a clip's fit, heavier where the clip moves. -> a
    `[1, 1, T, H, W]` tensor, or None where there is nothing to weigh.

    Why weights and not a second loss on frame differences, which is the
    obvious first idea: the enlargement is linear and the same on every frame,
    so the grid that best reproduces each frame also best reproduces each
    difference — a difference term has the same optimum as the plain fit and
    would change nothing it converges to. A *weighted* fit has a different
    optimum: the cells over a moving arm are fitted closely and the cells over
    the still background are allowed to drift, which is the trade a motion
    reference wants. Each cell's movement is the larger of its change to the
    frame before and to the frame after, averaged over channels, and the
    weight is `1 + strength * movement / mean movement`, so a static clip
    weighs every cell the same and `strength` 0 is the plain fit.
    """
    if not strength or latent.ndim != 5 or latent.shape[2] < 2:
        return None
    import torch

    step = (latent[:, :, 1:] - latent[:, :, :-1]).abs().mean(dim=1, keepdim=True)
    before = torch.cat([step[:, :, :1], step], dim=2)
    after = torch.cat([step, step[:, :, -1:]], dim=2)
    moved = torch.maximum(before, after)
    mean = float(moved.mean())
    if mean <= 0:
        return None
    return 1.0 + float(strength) * moved / mean


# How alike two latent frames have to be for the second to be dropped by
# `thin`: their mean squared difference over the clip's own variance. A held
# pose under codec noise sits well under it; a slow pan's frames, four source
# frames apart, sit well over. Set by reasoning about the measure, not by a
# render yet — `thin` logs what it saw so the number can be moved on evidence.
THIN = 0.02


def thin(latent, threshold=THIN):
    """Drop latent frames that repeat the one kept before them.
    -> `(latent, kept indices, changes)`.

    The sibling pack's budget policy drops near-duplicate frames before it
    resamples time, because a clip that is mostly a held pose pays a whole
    grid of tokens per frame for nothing. This is that step on its own: walk
    the frames, keep the first, and keep each later one only if it differs
    from the last one kept by more than `threshold` (mean squared difference
    over the latent's variance, so the number means the same at any scale).
    Timing compresses where frames go — a held second becomes a held instant
    — which is the trade, and why `threshold` 0 keeps everything.
    `changes` is every frame's measure against the frame kept before it, for
    the log line that says what a clip was made of.
    """
    if latent.ndim != 5 or latent.shape[2] < 2 or not threshold:
        return latent, list(range(latent.shape[2] if latent.ndim == 5 else 1)), []
    full = latent.detach().float()
    scale = float(full.var())
    if scale <= 0:
        return latent[:, :, :1], [0], [0.0] * (latent.shape[2] - 1)
    kept, changes = [0], []
    for index in range(1, full.shape[2]):
        change = float(((full[:, :, index] - full[:, :, kept[-1]]) ** 2).mean()) / scale
        changes.append(change)
        if change > threshold:
            kept.append(index)
    if len(kept) == latent.shape[2]:
        return latent, kept, changes
    return latent[:, :, kept], kept, changes


def motion_of(frames):
    """`[T, H, W, 3]` frames -> `[T-1, H, W, 3]` of what moved between them.

    The sibling pack's motion-only capture: the absolute frame difference,
    normalised to the clip's own peak so a still stretch is black and the
    largest movement is white. Not optical flow and not a pose track — a
    picture of *where* things changed, which is what the DiT is then shown as
    the clip's content. Their README says the same, and that fast motion
    smears; the render decodes the same frames for the tokenizer's 2 fps look.
    """
    if frames.shape[0] < 2:
        raise RefModError("a motion reference needs at least two frames")
    diff = (frames[1:].float() - frames[:-1].float()).abs()
    peak = float(diff.max())
    return diff / peak if peak > 0 else diff


# ---- a stack: one character, one file ------------------------------------------
#
# The sibling pack's own example, `vanellope_example`, is not a picture: it is
# four photos and three clips, each encoded, each pooled to the same 16x16 grid,
# and laid end to end along the time axis as one 44-frame video latent. That is
# what "a character as a RefMod" means over there — one file per person, motion
# included, cited as one `<Video n>`. `stack` builds the same shape: the
# per-source latents are pooled and refined one at a time (each against its own
# full encode, never averaged together — their README says merging misaligned
# faces blurs them) and concatenated on T. Under a token cap the clips lose
# frames evenly and the stills keep their one.


def stack(latents, grid, steps=150, lr=0.02, max_tokens=0, tell=None, motion=0.0):
    """`[[1, 24, T_i, H_i, W_i], ...]` -> one `[1, 24, sum T_i, grid, grid]`.

    -> `(latent, kept)`, `kept` the frame count each source contributed after
    the cap. `max_tokens` of 0 is no cap. `motion` is `compress`'s, and only
    the clips have any.
    """
    import torch

    grid = max(2, int(grid) // 2 * 2)
    per_frame = (grid // 2) * (grid // 2)
    counts = [int(latent.shape[2]) for latent in latents]
    kept = list(counts)
    if max_tokens and sum(counts) * per_frame > max_tokens:
        room = max(len(counts), max_tokens // per_frame)
        # Stills are one frame and stay; the clips share what is left of the
        # room in proportion, never below a frame each.
        clips = [i for i, n in enumerate(counts) if n > 1]
        spare = room - (len(counts) - len(clips))
        total = sum(counts[i] for i in clips) or 1
        for i in clips:
            kept[i] = max(1, int(spare * counts[i] / total))
    parts = []
    for index, (latent, keep) in enumerate(zip(latents, kept)):
        if keep < latent.shape[2]:
            picks = torch.linspace(0, latent.shape[2] - 1, keep).round().long()
            latent = latent[:, :, picks]
        base = index / len(latents)
        parts.append(compress(latent, grid, steps, lr, grid=(grid, grid), motion=motion,
                              tell=(lambda f, base=base: tell(base + f / len(latents))) if tell else None))
    return torch.cat(parts, dim=2), kept
