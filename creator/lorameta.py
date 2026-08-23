"""Everything another tool may have left beside a LoRA, read as one record.

A collection is rarely the product of one program. The same `models/loras` holds
files pulled down by CiviMeta, by Civitai Helper years ago, by CivitAI Browser+,
by ComfyUI-Lora-Manager, and files somebody trained themselves and dropped in
with nothing beside them at all. Each of those tools writes a different set of
companion files, and between them they cover most of what a picker wants to
show — a title, the trigger words, a picture.

So this module is the one place that knows what any of those layouts look like,
and it hands back a single record with the pack's own field names. Nothing above
it — not the routes, not the manager, not the detail sheet — knows which tool
was installed on the machine that filled this folder.

**The record's vocabulary is this pack's, not any one tool's.** That distinction
is the reason this file exists. CiviMeta's `meta.json` is not Civitai's API
shape: it is CiviMeta's normalisation of it, where `name` is the model and
`versionName` the version, while a raw `.civitai.info` is a model-*version*
object where `name` is the version and `model.name` is the model. Reading a
second format through the first one's vocabulary would put the version name on
every card. `_from_version` maps the upstream shape once, and every provider
that carries Civitai data — CiviMeta, Lora Manager, `.civitai.info` — arrives
through it.

**Fields are merged per-field, not per-source.** Different tools are
authoritative about different things. Civitai knows the title, the stats and the
sibling versions; a user who typed an activation text into A1111's metadata
editor knows the trigger words better than Civitai does, because that field *is*
their correction of it. So each field has its own source order (`FIELD_ORDER`),
and a card can legitimately show a Civitai title next to the user's own triggers.

**One readdir per folder, not one stat per guess.** Seven layouts times a dozen
extensions times a few hundred files is fifty thousand `stat` calls for a single
listing. Instead each directory is scanned once into `_Scan`, and every probe
after that is a binary search in memory. The scan is held for `SCAN_TTL` and
keyed by the directory's mtime — which catches files appearing and disappearing
but not a sidecar edited in place, so the TTL is what makes an in-place edit show
up, and the manager's Rescan is what makes it show up now.

Nothing here imports ComfyUI: paths arrive absolute, and `tests/test_lorameta.py`
builds the layouts in a temporary directory and runs this standalone.
"""

import base64
import bisect
import json
import os
import re
import struct
import time
import zlib

# ---------------------------------------------------------------------------
# what counts as media
# ---------------------------------------------------------------------------

# Kept as one map rather than two sets because every caller wants the answer
# "image, video, or not media at all" and none of them wants to ask twice.
MEDIA_KINDS = {
    ".webp": "image", ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".bmp": "image", ".avif": "image", ".jxl": "image",
    ".mp4": "video", ".webm": "video", ".mov": "video", ".mkv": "video",
}

# Which media wins when a file has several. Video first: an H3 LoRA showcases
# clips, and a card that can play one should, rather than settle for whichever
# still happened to sort first. Within each kind, the smaller formats lead.
PREVIEW_ORDER = [
    ".mp4", ".webm", ".mov", ".mkv",
    ".webp", ".png", ".jpg", ".jpeg", ".gif", ".avif", ".jxl", ".bmp",
]

# Every tool in this file writes a stub or a zero-length file at some point —
# CiviMeta on a failed download, Civitai Helper on a 404. Below this many bytes
# a "preview" is a placeholder that would render as a broken image.
MIN_MEDIA_BYTES = 100

# CiviMeta writes `{model}.safetensors.civitai/` beside every file it has
# identified: meta.json (the normalised record), images.json (the showcase's
# metadata), media/NNN.ext (the creator's showcase, downloaded) and
# thumbnails/NNN.webp (generated, images only — a video showcase has no
# thumbnail, so media/ is the fallback).
CIVIMETA_SUFFIX = ".civitai"
CIVIMETA_PREVIEW_DIRS = ("thumbnails", "media")

# How long a directory listing is trusted. Creating or deleting a companion
# bumps the directory's mtime and is caught immediately; editing one in place
# does not, on any filesystem this runs on, so something has to expire.
SCAN_TTL = 30.0

# Directories held at once. A collection browsed folder by folder touches a
# handful; the bound is only so that a session spent walking a deep tree does
# not accumulate one entry per folder for the life of the process.
MAX_SCANS = 256

# Rows held at once, same reasoning. One row is a small dict; the listing asks
# for at most MAX_LORAS of them per folder.
MAX_ROWS = 4000

# A safetensors header is one JSON blob at the front of the file. Anything
# claiming to be bigger than this is not a header, it is a corrupt length field
# about to become a memory allocation.
MAX_HEADER = 64 * 1024 * 1024
# What the listing pass will read. ModelSpec's text fields are a few kilobytes;
# only `ssmd_cover_images` pushes a header into megabytes, and the listing does
# not serve cover images. Reading the full cap once per file across a folder of
# hundreds would be gigabytes of I/O for a title.
MAX_HEADER_SHALLOW = 2 * 1024 * 1024


class _Entry:
    __slots__ = ("name", "mtime", "size", "is_dir")

    def __init__(self, name, mtime, size, is_dir):
        self.name = name
        self.mtime = mtime
        self.size = size
        self.is_dir = is_dir


class _Scan:
    """One directory's names, sorted lowercase, for prefix lookups.

    `keys` is sorted so that "every file whose name starts with this stem" is a
    binary search rather than a walk: in a folder of two thousand LoRAs the
    difference is the listing taking a moment or taking a minute.
    """

    __slots__ = ("mtime", "read_at", "keys", "entries")

    def __init__(self, mtime, entries):
        self.mtime = mtime
        self.read_at = time.monotonic()
        self.entries = entries
        self.keys = sorted(entries)

    def get(self, name):
        return self.entries.get(name.lower())

    def starting(self, prefix):
        """Every entry whose name begins with `prefix`, as (suffix, entry)."""
        prefix = prefix.lower()
        found = []
        for index in range(bisect.bisect_left(self.keys, prefix), len(self.keys)):
            key = self.keys[index]
            if not key.startswith(prefix):
                break
            entry = self.entries[key]
            found.append((entry.name[len(prefix):], entry))
        return found


_SCANS = {}


def _scan(directory):
    """This directory's `_Scan`, cached, or None if it cannot be read."""
    try:
        stamp = os.stat(directory).st_mtime
    except OSError:
        return None

    cached = _SCANS.get(directory)
    if cached is not None and cached.mtime == stamp \
            and time.monotonic() - cached.read_at < SCAN_TTL:
        return cached

    entries = {}
    try:
        with os.scandir(directory) as listing:
            for item in listing:
                try:
                    stat = item.stat()
                    is_dir = item.is_dir()
                except OSError:
                    continue
                entries[item.name.lower()] = _Entry(item.name, stat.st_mtime, stat.st_size, is_dir)
    except OSError:
        return None

    while len(_SCANS) >= MAX_SCANS:
        _SCANS.pop(next(iter(_SCANS)))
    scan = _Scan(stamp, entries)
    _SCANS[directory] = scan
    return scan


def forget():
    """Drop every cache. What the manager's Rescan button reaches."""
    _SCANS.clear()
    _ROWS.clear()
    _SETTINGS.clear()


# ---------------------------------------------------------------------------
# the probe: one LoRA and whatever shares its name
# ---------------------------------------------------------------------------

class Probe:
    """One model file and the companions sitting beside it.

    Everything a provider needs to look something up, so that providers are
    small functions over a scanned directory rather than a dozen `os.path`
    dances each.
    """

    def __init__(self, path):
        self.path = path
        self.directory = os.path.dirname(path)
        self.filename = os.path.basename(path)
        self.stem, self.ext = os.path.splitext(self.filename)
        self.scan = _scan(self.directory)
        # Keyed by what follows the stem, lowercased: ".preview.png",
        # ".civitai.info", ".safetensors.civitai", "_3.jpg". A sibling LoRA
        # whose name merely starts the same ("foo_v2.safetensors" under "foo")
        # lands here too, which is why every pattern below is matched exactly
        # or against a strict regex rather than by "starts with".
        self.rest = {}
        if self.scan is not None:
            for suffix, entry in self.scan.starting(self.stem):
                self.rest[suffix.lower()] = entry
        self._header = None

    # -- lookups ------------------------------------------------------------

    def entry(self, suffix):
        return self.rest.get(suffix.lower())

    def file(self, suffix):
        """The absolute path of `{stem}{suffix}`, or None if there is no file."""
        entry = self.rest.get(suffix.lower())
        if entry is None or entry.is_dir:
            return None
        return os.path.join(self.directory, entry.name)

    def folder(self, suffix):
        entry = self.rest.get(suffix.lower())
        if entry is None or not entry.is_dir:
            return None
        return os.path.join(self.directory, entry.name)

    def load(self, suffix):
        """`{stem}{suffix}` parsed as a JSON object, or None.

        A file that is missing, unreadable, not JSON, or JSON that is not an
        object all read the same: this tool has nothing to say about this LoRA.
        Civitai Helper in particular writes an empty file when a hash is not
        found, precisely so it does not rescan, and that has to read as silence
        rather than as an error.
        """
        path = self.file(suffix)
        if path is None:
            return None
        return read_json(path)

    def text(self, suffix, limit=64 * 1024):
        path = self.file(suffix)
        if path is None:
            return None
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read(limit).strip() or None
        except OSError:
            return None

    def signature(self):
        """What has to change before a cached row is wrong.

        The model's own stat plus every companion's, so adding a sidecar, or
        editing one the scan has since re-read, invalidates the row. Companion
        mtimes come from the scan and cost nothing extra here.
        """
        try:
            stat = os.stat(self.path)
            own = (stat.st_mtime, stat.st_size)
        except OSError:
            own = None
        return (own, tuple(sorted((key, entry.mtime, entry.size)
                                  for key, entry in self.rest.items())))

    def header(self, deep=False):
        """The safetensors header, read at most once per probe.

        `deep` lifts the size cap so embedded cover images are reachable; the
        listing pass never asks for that.
        """
        if self._header is None or (deep and self._header.get("shallow")):
            self._header = read_header(self.path, deep=deep)
        return self._header


def _stat(path):
    """`(size, mtime)`, or zeros for a file that vanished between two calls."""
    try:
        stat = os.stat(path)
    except OSError:
        return 0, 0
    return stat.st_size, stat.st_mtime


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


# ---------------------------------------------------------------------------
# the safetensors header
# ---------------------------------------------------------------------------

def read_header(path, deep=False):
    """What the file itself can say: training metadata, tensor census, rank.

    `metadata` is the trainer's `__metadata__` block verbatim (kohya's ss_*
    keys, ai-toolkit's json-in-string values, ModelSpec's `modelspec.*` — the
    frontend and `_from_header` below know the dialects). `ranks` comes from the
    lora_A/lora_down shapes, which is the ground truth the metadata's
    ss_network_dim merely repeats.
    """
    cap = MAX_HEADER if deep else MAX_HEADER_SHALLOW
    try:
        with open(path, "rb") as handle:
            prefix = handle.read(8)
            if len(prefix) < 8:
                return {"error": "not a safetensors file"}
            (length,) = struct.unpack("<Q", prefix)
            if not 0 < length <= MAX_HEADER:
                return {"error": "no readable header"}
            if length > cap:
                # Only `ssmd_cover_images` gets a header here, and the shallow
                # pass has no use for one. Say so rather than read it.
                return {"metadata": {}, "tensors": 0, "dtypes": {}, "ranks": [],
                        "shallow": True}
            header = json.loads(handle.read(length))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return {"error": str(exc)}
    if not isinstance(header, dict):
        return {"error": "no readable header"}

    metadata = header.pop("__metadata__", None)
    dtypes = {}
    ranks = set()
    for key, tensor in header.items():
        if not isinstance(tensor, dict):
            continue
        dtype = tensor.get("dtype")
        if dtype:
            dtypes[dtype] = dtypes.get(dtype, 0) + 1
        if key.endswith(("lora_A.weight", "lora_down.weight")):
            shape = tensor.get("shape") or []
            if shape:
                ranks.add(shape[0])
    return {
        "metadata": metadata if isinstance(metadata, dict) else {},
        "tensors": len(header),
        "dtypes": dtypes,
        "ranks": sorted(ranks),
    }


# ---------------------------------------------------------------------------
# small normalisers
# ---------------------------------------------------------------------------

def _text(value):
    """A non-empty string, or None. Everything else is unset."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _words(value):
    """A list of non-empty strings, from a list or from a comma-separated one."""
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value:
        word = _text(item)
        if word and word not in out:
            out.append(word)
    return out


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _digest(value):
    """A SHA-256, lowercased. Tools disagree about the case and it is a key:
    Lora Manager's gallery is a directory named after it."""
    digest = _text(value)
    return digest.lower() if digest else None


def _stats(*blocks):
    """Civitai's counters under this pack's names.

    A model-version carries `downloadCount`/`thumbsUpCount`; the model carries
    `downloadCount`/`favoriteCount`/`commentCount`/`rating`. CiviMeta already
    merged and renamed them, so its own names are accepted here too and the
    detail sheet only ever sees one spelling.
    """
    merged = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for target, names in (
            ("downloads", ("downloads", "downloadCount")),
            ("rating", ("rating",)),
            ("favorites", ("favorites", "favoriteCount", "thumbsUpCount")),
            ("comments", ("comments", "commentCount")),
        ):
            if merged.get(target) is not None:
                continue
            for name in names:
                value = _number(block.get(name))
                if value is not None:
                    merged[target] = value
                    break
    return merged or None


# Civitai's own field is an array; CiviMeta stores it as the set literal
# "{Image,Rent,Sell}" it came out of a database as. Both mean the same list.
def _commercial(value):
    if isinstance(value, str):
        value = value.replace("{", "").replace("}", "").replace('"', "").split(",")
    if not isinstance(value, (list, tuple)):
        return []
    return [part for part in (_text(item) for item in value)
            if part and part.lower() != "none"]


def _license(block):
    """The three permissions Civitai records, or None when none were recorded.

    Read from wherever they sit: flat on a model object, which is where the API
    puts them, or nested under `license`, which is where CiviMeta puts them.
    """
    if not isinstance(block, dict):
        return None
    nested = block.get("license")
    if isinstance(nested, dict):
        block = nested
    if not any(key in block for key in
               ("allowCommercialUse", "allowNoCredit", "allowDerivatives")):
        return None
    return {
        "commercial": _commercial(block.get("allowCommercialUse")),
        "credit": not block.get("allowNoCredit"),
        "derivatives": bool(block.get("allowDerivatives")),
    }


def _versions(items):
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        out.append({
            "id": item.get("id"),
            "name": _text(item.get("name")),
            "base_model": _text(item.get("baseModel") or item.get("base_model")),
            "created_at": _text(item.get("createdAt") or item.get("created_at")),
        })
    return out


def _model_hash(files):
    """The SHA-256 of the weights themselves, out of a Civitai file list.

    The primary file is the model; the list also carries training data archives
    and config files, whose hashes would identify the wrong thing.
    """
    for wanted in (True, False):
        for item in files or []:
            if not isinstance(item, dict):
                continue
            if bool(item.get("primary")) is not wanted:
                continue
            digest = _text((item.get("hashes") or {}).get("SHA256"))
            if digest:
                return digest.lower()
    return None


# The per-image generation settings worth showing. Civitai's `meta` carries more
# (the whole Comfy graph, resource lists); the recipe is what a person can act on.
def _recipe(meta):
    """One showcase image's settings, under this pack's names."""
    if not isinstance(meta, dict):
        return None
    recipe = {
        "prompt": _text(meta.get("prompt")),
        "negative_prompt": _text(meta.get("negativePrompt") or meta.get("negative_prompt")),
        "seed": _number(meta.get("seed")),
        "steps": _number(meta.get("steps")),
        "cfg": _number(meta.get("cfgScale") or meta.get("cfg") or meta.get("CFG scale")),
        "sampler": _text(meta.get("sampler")),
        "scheduler": _text(meta.get("scheduler")),
    }
    recipe = {key: value for key, value in recipe.items() if value is not None}
    return recipe or None


# ---------------------------------------------------------------------------
# the Civitai model-version object, wherever it was found
# ---------------------------------------------------------------------------

def _from_version(version, model=None):
    """A Civitai model-version object -> this pack's record.

    The one mapping that matters: on a model-version, `name` is the *version*
    and `model.name` is the model. Every tool that caches Civitai's API caches
    this object — Civitai Helper as `.civitai.info`, Lora Manager under its
    `civitai` key, CivitAI Browser+ as `.api_info.json`'s versions — so getting
    it right once is most of this file's value.
    """
    if not isinstance(version, dict):
        return {}
    if not isinstance(model, dict):
        model = version.get("model") if isinstance(version.get("model"), dict) else {}

    images = [item for item in (version.get("images") or []) if isinstance(item, dict)]
    return {
        "title": _text(model.get("name")),
        "version": _text(version.get("name")),
        "type": _text(model.get("type") or version.get("type")),
        "base_model": _text(version.get("baseModel")),
        "creator": _text((model.get("creator") or {}).get("username")
                         if isinstance(model.get("creator"), dict) else None),
        "description": _text(model.get("description")),
        "version_description": _text(version.get("description")),
        "trained_words": _words(version.get("trainedWords")),
        "tags": _words(model.get("tags")),
        "nsfw": bool(model.get("nsfw") or version.get("nsfw")),
        "model_id": version.get("modelId") or model.get("id"),
        "version_id": version.get("id"),
        "hash": _model_hash(version.get("files")),
        "stats": _stats(model.get("stats"), version.get("stats")),
        "license": _license(model),
        "versions": _versions(model.get("modelVersions")),
        # Kept aside rather than folded into `showcase`: these describe the
        # creator's gallery, which lives on Civitai's servers. A provider that
        # also found the files on disk zips them together; one that did not
        # leaves them unused rather than offering a card that cannot load.
        "recipes": [{"meta": _recipe(item.get("meta")), "nsfw": bool(item.get("nsfw"))}
                    for item in images],
    }


# ---------------------------------------------------------------------------
# showcase media
# ---------------------------------------------------------------------------

def _media(path, size=None):
    """A media file as a showcase entry, or None if it is not one."""
    kind = MEDIA_KINDS.get(os.path.splitext(path)[1].lower())
    if kind is None:
        return None
    try:
        if (size if size is not None else os.path.getsize(path)) < MIN_MEDIA_BYTES:
            return None
    except OSError:
        return None
    return {"kind": kind, "path": path, "thumb": None, "meta": None, "nsfw": False}


_TRAILING_NUMBER = re.compile(r"(\d+)$")


def _ordinal(stem):
    """The number a showcase file is named after, or None.

    Every tool here numbers its gallery in the creator's order — CiviMeta from
    one (`001.webp`), Browser+ from zero (`name_0.jpg`), Lora Manager from zero
    — so the number, not the position in a directory listing, is the link back
    to the metadata. Positional matching would drift the moment one download in
    the middle failed.
    """
    match = _TRAILING_NUMBER.search(stem)
    return int(match.group(1)) if match else None


def _attach(entries, recipes, base=0):
    """Give each showcase entry the recipe recorded for it, by number."""
    for index, entry in enumerate(entries):
        number = _ordinal(os.path.splitext(os.path.basename(entry["path"]))[0])
        at = (number - base) if number is not None else index
        if 0 <= at < len(recipes):
            entry["meta"] = recipes[at].get("meta")
            entry["nsfw"] = recipes[at].get("nsfw", False)
    return entries


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------

def _from_civimeta(probe, deep):
    """CiviMeta: `{model}.safetensors.civitai/` with meta.json and a gallery."""
    sidecar = probe.folder(probe.ext + CIVIMETA_SUFFIX)
    if sidecar is None:
        return None

    record = {}
    meta = read_json(os.path.join(sidecar, "meta.json"))
    if meta:
        # CiviMeta has already flattened the model and the version together, so
        # this is not `_from_version`: `name` here is the model, not the version.
        record = {
            "title": _text(meta.get("name")),
            "version": _text(meta.get("versionName")),
            "type": _text(meta.get("type")),
            "base_model": _text(meta.get("baseModel")),
            "creator": _text((meta.get("creator") or {}).get("username")
                             if isinstance(meta.get("creator"), dict) else meta.get("creator")),
            "description": _text(meta.get("description")),
            "version_description": _text(meta.get("versionDescription")),
            "trained_words": _words(meta.get("trainedWords")),
            "tags": _words(meta.get("tags")),
            "nsfw": bool(meta.get("nsfw")),
            "model_id": meta.get("modelId"),
            "version_id": meta.get("versionId"),
            "hash": _digest(meta.get("hash")),
            "stats": _stats(meta.get("stats")),
            "license": _license(meta),
            "versions": _versions(meta.get("versions")),
            "fetched_at": _text(meta.get("fetchedAt")),
        }

    preview = _civimeta_preview(sidecar)
    if preview:
        record["preview"] = preview
    if deep:
        record["showcase"] = _civimeta_showcase(sidecar)
    # The directory existing is itself the claim that CiviMeta identified this
    # file, so an empty record still counts as this provider having spoken.
    return record or {}


def _civimeta_preview(sidecar):
    """The first thing CiviMeta cached, thumbnails before raw media.

    Thumbnails are generated WebP and a fraction of the bytes; only a video
    showcase has none, which is exactly when media/ is the right answer.
    """
    for sub in CIVIMETA_PREVIEW_DIRS:
        directory = os.path.join(sidecar, sub)
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            entry = _media(os.path.join(directory, name))
            if entry:
                return entry
    return None


def _civimeta_showcase(sidecar):
    """The gallery, each item carrying the recipe images.json holds for it.

    Only media/ is walked — thumbnails are looked up per entry, because a video
    showcase never has one and the sheet needs to know which is which.
    """
    entries = []
    directory = os.path.join(sidecar, "media")
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return entries
    for name in names:
        entry = _media(os.path.join(directory, name))
        if entry is None:
            continue
        thumb = os.path.join(sidecar, "thumbnails", os.path.splitext(name)[0] + ".webp")
        try:
            if os.path.getsize(thumb) >= MIN_MEDIA_BYTES:
                entry["thumb"] = thumb
        except OSError:
            pass
        entries.append(entry)

    items = (read_json(os.path.join(sidecar, "images.json")) or {}).get("items")
    recipes = [{"meta": _recipe(item.get("meta")), "nsfw": bool(item.get("nsfw"))}
               for item in (items or []) if isinstance(item, dict)]
    # CiviMeta numbers from one.
    return _attach(entries, recipes, base=1)


def _from_lora_manager(probe, deep):
    """ComfyUI-Lora-Manager: `{stem}.metadata.json` plus a central gallery.

    Its `civitai` key is the API's model-version object unchanged, so the
    Civitai half of this is `_from_version` and nothing more. What is its own is
    the user's layer on top — notes, favourite, usage tips — and the `sha256` it
    already computed, which is how the gallery is found without this pack ever
    hashing a 700 MB file.
    """
    meta = probe.load(".metadata.json")
    if meta is None:
        return None

    record = _from_version(meta.get("civitai"))
    record["title"] = _text(meta.get("model_name")) or record.get("title")
    record["base_model"] = _text(meta.get("base_model")) or record.get("base_model")
    record["hash"] = _digest(meta.get("sha256")) or record.get("hash")
    record["notes"] = _text(meta.get("notes"))
    record["description"] = _text(meta.get("modelDescription")) or record.get("description")
    tags = _words(meta.get("tags"))
    if tags:
        record["tags"] = tags
    # The manager stores its own trigger list under `civitai.trainedWords` when
    # the user edits it, which `_from_version` has already picked up.

    # usage_tips is JSON in a string: {"strength": 0.8, "clip_strength": 1.0}.
    tips = meta.get("usage_tips")
    if isinstance(tips, str):
        try:
            tips = json.loads(tips)
        except ValueError:
            tips = None
    if isinstance(tips, dict):
        record["strength"] = _number(tips.get("strength"))

    preview = _loose_preview(probe) or _lora_manager_preview(meta, probe)
    if preview:
        record["preview"] = preview
    if deep:
        record["showcase"] = _lora_manager_showcase(record.get("hash"), record.get("recipes") or [])
    return record


def _lora_manager_preview(meta, probe):
    """Its `preview_url`, when it points at a file this pack may serve.

    The path is absolute and written by another program, so it is only used when
    it lands inside the folder the model itself is in — a preview is a companion
    file, and anything else is a path this pack has no business opening.
    """
    candidate = _text(meta.get("preview_url"))
    if candidate is None:
        return None
    candidate = os.path.realpath(candidate)
    root = os.path.realpath(probe.directory)
    if os.path.commonpath([root, candidate]) != root:
        return None
    return _media(candidate)


def _from_civitai_info(probe, deep):
    """Civitai Helper and CivitAI Browser+: `{stem}.civitai.info`.

    The raw model-version response, written verbatim. Browser+ optionally writes
    the model-level item beside it as `{stem}.api_info.json`, which is where the
    description, the tags and the sibling versions live — the version object
    alone has none of those.
    """
    version = probe.load(".civitai.info")
    if version is None:
        return None
    # Civitai Helper writes `{}` when a hash was not found, so that it does not
    # rescan. That is a file saying "this is not on Civitai", not metadata.
    if not version:
        return {}

    model = probe.load(".api_info.json")
    record = _from_version(version, model)

    preview = _loose_preview(probe)
    if preview:
        record["preview"] = preview
    if deep:
        record["showcase"] = _numbered_showcase(probe, record.get("recipes") or [])
    return record


def _numbered_showcase(probe, recipes):
    """CivitAI Browser+'s gallery: `{stem}_0.jpg`, `{stem}_1.jpg`, ...

    Matched strictly against underscore-digits-extension so that a sibling LoRA
    sharing the prefix — `style_v2.safetensors` under `style` — is never mistaken
    for image two of this one's showcase.
    """
    entries = []
    for suffix, entry in probe.rest.items():
        match = re.fullmatch(r"_(\d+)(\.[a-z0-9]+)", suffix)
        if not match or MEDIA_KINDS.get(match.group(2)) is None:
            continue
        item = _media(os.path.join(probe.directory, entry.name), entry.size)
        if item:
            entries.append(item)
    entries.sort(key=lambda item: _ordinal(os.path.splitext(os.path.basename(item["path"]))[0]) or 0)
    return _attach(entries, recipes, base=0)


def _from_a1111(probe, deep):
    """A1111 and everything downstream of it: `{stem}.json` and `{stem}.txt`.

    This is the user's own layer, not a mirror of a website. "activation text" is
    what they decided the trigger words actually are; "preferred weight" is the
    strength they settled on. Both outrank whatever Civitai said, which is why
    `FIELD_ORDER` puts this source first for those two fields and nowhere else.
    """
    meta = probe.load(".json") or {}
    described = probe.text(".txt") or probe.text(".description.txt") or probe.text(".md")
    if not meta and described is None:
        return None

    record = {
        "trained_words": _words(meta.get("activation text")),
        "strength": _number(meta.get("preferred weight")) or None,
        "notes": _text(meta.get("notes")),
        "description": _text(meta.get("description")) or described,
        "base_model": _text(meta.get("sd version")),
        "hash": _digest(meta.get("sha256")),
        "model_id": meta.get("modelId"),
    }
    preview = _loose_preview(probe)
    if preview:
        record["preview"] = preview
    if deep:
        record["showcase"] = _numbered_showcase(probe, [])
    return record


def _loose_preview(probe):
    """`{stem}.preview.{ext}`, else `{stem}.{ext}` — the near-universal layout.

    Every tool in this file writes one of these two, which makes this the single
    lookup that turns a folder of blank cards into a folder of pictures. The
    explicit `.preview.` form wins: a bare `{stem}.png` beside a LoRA is more
    often something a user dropped there than something a tool chose.
    """
    for extension in PREVIEW_ORDER:
        for suffix in (".preview" + extension, extension):
            entry = probe.entry(suffix)
            if entry is None or entry.is_dir:
                continue
            found = _media(os.path.join(probe.directory, entry.name), entry.size)
            if found:
                return found
    return None


def _from_loose(probe, deep):
    """Nothing but pictures: a preview and any numbered gallery beside it.

    The floor everything else stands on. A LoRA that no tool has ever touched
    still gets its card image from here, and if the user dropped their own
    generations beside it, the sheet reads the recipe out of the PNGs.
    """
    record = {}
    preview = _loose_preview(probe)
    if preview:
        record["preview"] = preview
    if deep:
        showcase = _numbered_showcase(probe, [])
        # A single preview image is a gallery of one. Worth saying so: it is
        # very often the user's own generation, and then it is carrying the
        # recipe that the sheet exists to show.
        if not showcase and preview:
            showcase = [dict(preview)]
        for entry in showcase:
            entry["meta"] = png_recipe(entry["path"])
        record["showcase"] = showcase
    return record or None


def _from_header(probe, deep):
    """ModelSpec and the embedded cover images: no sidecar at all.

    The last resort and the only one that works on a file that has never left
    the machine it was trained on. OneTrainer and SwarmUI write ModelSpec;
    kohya's `ssmd_cover_images` is a base64 gallery inside the header, which
    ComfyUI core already serves for its own model library.
    """
    header = probe.header(deep=deep)
    metadata = header.get("metadata") or {}
    if not metadata:
        return None

    trigger = _text(metadata.get("modelspec.trigger_phrase"))
    record = {
        "title": _text(metadata.get("modelspec.title")),
        "description": _text(metadata.get("modelspec.description")),
        "creator": _text(metadata.get("modelspec.author")),
        "base_model": _text(metadata.get("modelspec.architecture")),
        "trained_words": [trigger] if trigger else [],
        "tags": _words(metadata.get("modelspec.tags")),
        "notes": _text(metadata.get("modelspec.usage_hint")),
        "hash": _digest(metadata.get("modelspec.hash_sha256")
                        or metadata.get("sshs_model_hash")),
    }

    thumbnail = _data_uri(metadata.get("modelspec.thumbnail"))
    if thumbnail:
        record["preview"] = thumbnail
    if deep:
        record["showcase"] = _cover_images(metadata)
    return record


def _data_uri(value):
    """`data:image/png;base64,...` as a showcase entry, or None."""
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    head, _, payload = value.partition(",")
    if not payload:
        return None
    mime = head[5:].split(";")[0] or "application/octet-stream"
    try:
        data = base64.b64decode(payload, validate=False)
    except (ValueError, TypeError):
        return None
    if len(data) < MIN_MEDIA_BYTES:
        return None
    return {"kind": "video" if mime.startswith("video/") else "image",
            "path": None, "data": data, "mime": mime, "thumb": None,
            "meta": None, "nsfw": False}


def _cover_images(metadata):
    """kohya's `ssmd_cover_images`: a JSON array of base64 images in the header."""
    raw = metadata.get("ssmd_cover_images")
    if not isinstance(raw, str):
        return []
    try:
        images = json.loads(raw)
    except ValueError:
        return []
    entries = []
    for image in images if isinstance(images, list) else []:
        if not isinstance(image, str):
            continue
        try:
            data = base64.b64decode(image, validate=False)
        except (ValueError, TypeError):
            continue
        if len(data) < MIN_MEDIA_BYTES:
            continue
        entries.append({"kind": "image", "path": None, "data": data,
                        "mime": sniff(data), "thumb": None, "meta": None, "nsfw": False})
    return entries


def sniff(data):
    """A content type from the first bytes, for media that never had a filename."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] in (b"GIF8",):
        return "image/gif"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    return "application/octet-stream"


# ---------------------------------------------------------------------------
# ComfyUI-Lora-Manager's central gallery
# ---------------------------------------------------------------------------

# Its example images do not sit beside the model: they are filed under a root
# the user chose, in a directory named after the model's SHA-256, optionally one
# level deeper when several libraries are configured. Reading another pack's
# settings file is not something to do lightly, so it is done exactly once, it is
# read-only, and every failure is silence — the `.preview.*` file beside the
# model is what the card shows either way.
_LORA_MANAGER_APP = "ComfyUI-LoRA-Manager"
_SETTINGS = {}
_SETTINGS_TTL = 300.0


def _config_dirs():
    """Where `platformdirs.user_config_dir(app, appauthor=False)` would point.

    Resolved through platformdirs when it happens to be installed — Lora Manager
    depends on it, so on a machine that has Lora Manager it is there — and
    otherwise from the same three rules platformdirs applies, so this does not
    take a dependency for one path.
    """
    try:
        from platformdirs import user_config_dir

        return [user_config_dir(_LORA_MANAGER_APP, appauthor=False)]
    except Exception:  # noqa: BLE001 — absent or broken, either way fall through
        pass

    home = os.path.expanduser("~")
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return [os.path.join(base, _LORA_MANAGER_APP)]
    return [
        os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"),
                     _LORA_MANAGER_APP),
        os.path.join(home, "Library", "Application Support", _LORA_MANAGER_APP),
    ]


def _portable_settings():
    """The in-repo `settings.json` of a Lora Manager installed beside this pack."""
    siblings = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        names = os.listdir(siblings)
    except OSError:
        return []
    return [os.path.join(siblings, name, "settings.json") for name in names
            if "lora" in name.lower() and "manager" in name.lower()]


def lora_manager_settings():
    """Lora Manager's settings, or `{}`. Best effort, cached, never raises."""
    cached = _SETTINGS.get("value")
    if cached is not None and time.monotonic() - _SETTINGS["at"] < _SETTINGS_TTL:
        return cached

    settings = {}
    try:
        candidates = [os.path.join(directory, "settings.json") for directory in _config_dirs()]
        candidates += _portable_settings()
        for candidate in candidates:
            loaded = read_json(candidate)
            if loaded:
                settings = loaded
                break
    except Exception:  # noqa: BLE001 — another pack's file, on someone else's disk
        settings = {}

    _SETTINGS["value"] = settings
    _SETTINGS["at"] = time.monotonic()
    return settings


def example_images_root():
    """The configured gallery root, or None."""
    root = _text(lora_manager_settings().get("example_images_path"))
    if root is None:
        return None
    root = os.path.realpath(os.path.expanduser(root))
    return root if os.path.isdir(root) else None


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _lora_manager_showcase(digest, recipes):
    """The gallery filed under this model's hash, zipped with its recipes.

    The hash is checked against what a hash can be before it is joined onto a
    path. It comes out of a JSON file that another program wrote, and this is
    the one lookup in this module that leaves the model's own folder — a
    `sha256` of `../../..` would otherwise be a directory traversal wearing a
    sidecar.
    """
    digest = (digest or "").lower()
    if not _SHA256.match(digest):
        return []
    root = example_images_root()
    if root is None:
        return []

    directory = os.path.join(root, digest)
    if not os.path.isdir(directory):
        # Several libraries configured means one more level: {root}/{library}/{hash}.
        directory = None
        try:
            for name in sorted(os.listdir(root)):
                candidate = os.path.join(root, name, digest)
                if os.path.isdir(candidate):
                    directory = candidate
                    break
        except OSError:
            return []
        if directory is None:
            return []

    entries = []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    for name in names:
        entry = _media(os.path.join(directory, name))
        if entry:
            entries.append(entry)
    entries.sort(key=lambda item: _ordinal(os.path.splitext(os.path.basename(item["path"]))[0]) or 0)
    return _attach(entries, recipes, base=0)


# ---------------------------------------------------------------------------
# PNG generation parameters
# ---------------------------------------------------------------------------

# A1111 and everything that copied it write the whole recipe into one PNG text
# chunk called `parameters`. Read with `struct` rather than Pillow because this
# runs inside a listing: opening an image decoder per showcase file to read
# twenty bytes of text would cost more than everything else here put together.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_PNG_SCAN = 2 * 1024 * 1024

# What makes the last line of a `parameters` block the settings line rather than
# the last line of the prompt. Any one of these is enough; A1111 has written all
# four for as long as the format has existed.
_SETTINGS_LINE = re.compile(r"(?:^|,\s)(?:Steps|Sampler|CFG scale|Seed|Model): ")


def png_text(path):
    """`{keyword: text}` from a PNG's tEXt/zTXt/iTXt chunks, or `{}`."""
    found = {}
    try:
        with open(path, "rb") as handle:
            if handle.read(8) != _PNG_MAGIC:
                return {}
            read = 8
            while read < MAX_PNG_SCAN:
                head = handle.read(8)
                if len(head) < 8:
                    break
                length, kind = struct.unpack(">I4s", head)
                read += 8 + length + 4
                if kind == b"IDAT" or kind == b"IEND":
                    break
                if kind not in (b"tEXt", b"zTXt", b"iTXt") or length > MAX_PNG_SCAN:
                    handle.seek(length + 4, os.SEEK_CUR)
                    continue
                body = handle.read(length)
                handle.seek(4, os.SEEK_CUR)   # past the CRC
                keyword, _, rest = body.partition(b"\x00")
                try:
                    if kind == b"tEXt":
                        text = rest.decode("latin-1")
                    elif kind == b"zTXt":
                        text = zlib.decompress(rest[1:]).decode("latin-1")
                    else:
                        # iTXt: compression flag, method, language, translated
                        # keyword, then the text.
                        flag = rest[0:1]
                        rest = rest[2:].split(b"\x00", 2)[-1]
                        text = (zlib.decompress(rest) if flag == b"\x01" else rest).decode("utf-8")
                except (ValueError, zlib.error, UnicodeDecodeError, IndexError):
                    continue
                found[keyword.decode("latin-1", "replace")] = text
    except OSError:
        return {}
    return found


def parse_a1111(text):
    """A1111's `parameters` block -> this pack's recipe.

    The format is positional and only loosely specified: the prompt, then an
    optional `Negative prompt:` line, then one line of comma-separated settings.
    Only the settings this pack shows are pulled out; the rest is left alone
    rather than half-understood.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    lines = text.split("\n")
    # The settings are the last line, when the last line looks like settings. An
    # image saved before the prompt was finished has none, and then every line
    # is prompt.
    settings = lines.pop() if _SETTINGS_LINE.search(lines[-1]) else ""
    prompt, marker, negative = "\n".join(lines).partition("Negative prompt:")

    fields = {}
    for match in re.finditer(r"(\w[\w ]*?): ([^,]+)", settings):
        fields[match.group(1).strip()] = match.group(2).strip()

    def numeric(name):
        try:
            value = float(fields[name])
        except (KeyError, ValueError):
            return None
        return int(value) if value == int(value) else value

    recipe = {
        "prompt": prompt.strip() or None,
        "negative_prompt": negative.strip() or None if marker else None,
        "seed": numeric("Seed"),
        "steps": numeric("Steps"),
        "cfg": numeric("CFG scale"),
        "sampler": fields.get("Sampler"),
        "scheduler": fields.get("Schedule type") or fields.get("Scheduler"),
    }
    recipe = {key: value for key, value in recipe.items() if value is not None}
    return recipe or None


def png_recipe(path):
    """The generation settings a PNG carries, or None.

    ComfyUI's own `prompt`/`workflow` chunks are deliberately not read: they are
    a whole graph, and picking a "the" prompt out of one is guesswork that would
    put a wrong answer on a sheet whose entire job is to be right about this.
    """
    if path is None or os.path.splitext(path)[1].lower() != ".png":
        return None
    return parse_a1111(png_text(path).get("parameters"))


# ---------------------------------------------------------------------------
# merging
# ---------------------------------------------------------------------------

# Most specific first. CiviMeta leads because it is the only one that caches the
# gallery, the sibling versions and the stats together; the bare-pictures reader
# trails because it knows nothing but where the picture is.
PROVIDERS = (
    ("civimeta", _from_civimeta),
    ("loramanager", _from_lora_manager),
    ("civitai_info", _from_civitai_info),
    ("a1111", _from_a1111),
    ("header", _from_header),
    ("loose", _from_loose),
)

DEFAULT_ORDER = tuple(name for name, _ in PROVIDERS)

# The fields whose best source is not the most specific one. All three are
# things a person edited about a model rather than things a website said about
# it, and a picker that overrode them with the website would be throwing away
# the only opinion in the folder that was formed by using the file.
_USER_FIRST = ("a1111", "loramanager", "civimeta", "civitai_info", "header", "loose")
FIELD_ORDER = {
    "trained_words": _USER_FIRST,
    "strength": _USER_FIRST,
    "notes": _USER_FIRST,
}

FIELDS = (
    "title", "version", "type", "base_model", "creator", "description",
    "version_description", "trained_words", "tags", "nsfw", "model_id",
    "version_id", "hash", "stats", "license", "versions", "fetched_at",
    "notes", "strength", "preview", "showcase",
)

def _absent(value):
    """Whether a provider actually said anything for a field.

    Not a truth test. A `strength` of 0 and a `model_id` of 0 are answers, and
    Python would call both of them equal to False — so emptiness is only ever
    None, or a string/list/dict with nothing in it.
    """
    return value is None or (isinstance(value, (str, list, dict, tuple)) and not value)


def describe(target, deep=False):
    """Every provider's answer for one model file, merged into one record.

    `deep` is the detail sheet: it reads galleries, lifts the header size cap and
    decodes embedded images. The listing never asks for any of that.
    """
    probe = target if isinstance(target, Probe) else Probe(target)
    found = {}
    for name, provider in PROVIDERS:
        # Opening the weights themselves is the one expensive probe here, and
        # ModelSpec is only ever the fallback for a file nothing else described.
        # A listing of six hundred cards must not read six hundred headers to
        # find titles it already has.
        if name == "header" and not deep and any(
                (record or {}).get("title") for record in found.values()):
            continue
        try:
            record = provider(probe, deep)
        except Exception:  # noqa: BLE001 — one bad sidecar must not empty a folder
            record = None
        # `{}` and None are different answers. A provider returns None when its
        # layout is not here at all, and `{}` when it is here and has nothing to
        # say — an empty `.civitai.info` is Civitai Helper recording that this
        # file is not on Civitai, which is knowledge, and a source that spoke.
        if record is not None:
            found[name] = record

    merged = {}
    for field in FIELDS:
        for source in FIELD_ORDER.get(field, DEFAULT_ORDER):
            value = (found.get(source) or {}).get(field)
            # `nsfw` is the one field whose False is a real answer rather than
            # an absence, and it is also the one where any source saying yes
            # settles it.
            if field == "nsfw":
                if value:
                    merged[field] = True
                    break
                continue
            if not _absent(value):
                merged[field] = value
                break
    merged.setdefault("nsfw", False)
    # Membership, not truth: a provider that returned `{}` still found its
    # layout, and the sheet says so rather than implying nothing was there.
    merged["sources"] = [name for name in DEFAULT_ORDER if name in found]
    merged["probe"] = probe
    return merged


# ---------------------------------------------------------------------------
# what the routes serve
# ---------------------------------------------------------------------------

# name -> (signature, row). Reading a handful of small files per LoRA is cheap,
# but not cheap enough to redo on every keystroke in the manager's search box.
_ROWS = {}

# What a listing row carries beyond the file's own facts. Deliberately short:
# this is repeated a few hundred times in one JSON payload.
ROW_FIELDS = ("title", "version", "type", "base_model", "tags", "trained_words",
              "nsfw", "model_id", "version_id", "strength")


def row(name, path):
    """One card's worth of a LoRA, cached against everything beside it."""
    probe = Probe(path)
    signature = probe.signature()
    cached = _ROWS.get(name)
    if cached and cached[0] == signature:
        return cached[1]

    # The model file is its own companion — the scan measured it along with
    # everything else sharing its name, so this is the row's size and date for
    # free rather than two more stat calls per card.
    own = probe.entry(probe.ext)
    size, mtime = (own.size, own.mtime) if own else _stat(path)

    record = describe(probe)
    built = {
        "name": name,
        "base": os.path.splitext(os.path.basename(name))[0],
        "folder": os.path.dirname(name),
        "size": size,
        "mtime": mtime,
        "preview": (record.get("preview") or {}).get("kind"),
        "sources": record["sources"],
        "downloads": (record.get("stats") or {}).get("downloads"),
    }
    for field in ROW_FIELDS:
        built[field] = record.get(field)

    while len(_ROWS) >= MAX_ROWS:
        _ROWS.pop(next(iter(_ROWS)))
    _ROWS[name] = (signature, built)
    return built


def preview(path):
    """The card's image or clip: `(path, None)` or `(None, (bytes, mime))`."""
    found = describe(path).get("preview")
    if not found:
        return None, None
    if found.get("path"):
        return found["path"], None
    return None, (found["data"], found.get("mime") or sniff(found["data"]))


def showcase(path):
    """The detail sheet's gallery, in the creator's order."""
    return describe(path, deep=True).get("showcase") or []


def detail(name, path):
    """Everything one LoRA's sheet needs, in one record.

    `meta` is None when nothing but the file itself had anything to say, which
    is what makes the sheet open as a spec sheet rather than as a gallery.
    """
    record = describe(path, deep=True)
    probe = record["probe"]
    own = probe.entry(probe.ext)
    size, mtime = (own.size, own.mtime) if own else _stat(path)
    gallery = record.get("showcase") or []

    meta = {field: record.get(field) for field in FIELDS
            if field not in ("preview", "showcase")}
    meta["sources"] = record["sources"]
    if record.get("model_id"):
        meta["url"] = ("https://civitai.com/models/"
                       f"{record['model_id']}"
                       + (f"?modelVersionId={record['version_id']}" if record.get("version_id") else ""))
    # Nothing but the safetensors header spoke: the sheet has no story to tell
    # about this file that the file does not tell itself.
    told = [source for source in record["sources"] if source not in ("header", "loose")]
    if not told and not record.get("title"):
        meta = None

    return {
        "name": name,
        "size": size,
        "mtime": mtime,
        "header": probe.header(deep=True),
        "meta": meta,
        "showcase": [{"index": index, "kind": item["kind"],
                      "thumb": bool(item.get("thumb")), "meta": item.get("meta"),
                      "nsfw": item.get("nsfw", False)}
                     for index, item in enumerate(gallery)],
    }
