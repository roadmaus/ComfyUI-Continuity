"""Reference latents that outlive the prompt they were encoded beside.

A segment node caches on its whole payload — `render.emit` serialises the
request into `segment_data` and that string is the node's key — so editing one
word of the prompt re-executes it, and re-executing it re-decodes every
reference file and pushes every one of them through the VAE again. That is the
right key for the *generation*: the prompt is conditioning, and conditioning is
what the node returns. It is the wrong key for the references, whose latents do
not know the prompt exists.

So this is a second cache underneath the first, keyed on what a reference latent
actually depends on: the file, the canvas it is encoded at, and the VAE doing
the encoding. Not in that list, and therefore free to change: the prompt, the
seed, the sampler, the LoRAs, the other references, and their order. The seed is
already kept out of the segment payload for exactly this reason (`render.emit`)
— this is the same argument made about the reference instead of the sampler.

**What is cached is the pair, not the latent.** `encode._encode_references`
builds two things out of one decode: the DiT's latent block, and the 2 fps
presentation the tokenizer is shown. Caching only the latent would leave the
container decode and the resize to run, and on a high-resolution source that is
most of the wait. Both go into one entry, which is why `media.load_all` hands
back entries that decode on first read rather than files it has already read: a
hit never touches the disk the file is on.

**Two tiers.** In memory for the session, where a prompt edit is a re-queue
seconds later, and on disk for everything longer — including a restart, a
rebuild, or a week off. The disk tier is what makes `ref_size: max` affordable:
a reference encoded at the full canvas once stays encoded at the full canvas,
so the setting stops being a speed trade and goes back to being a quality one.
That only holds if the store outlives the process, which is why it is not in
temp — see `directory`.

**Safetensors, with the shape written into the file.** A spill is named by a
uuid only its writer knows, so `spill.py` can write raw bytes and a sidecar. An
entry here is looked up by content from another render, possibly another
process, so it has to be self-describing and it has to appear atomically:
written to a temporary and renamed, or a half-flushed file is a corrupt latent
that reads back as a plausible one.

Nothing here decides *what* is cacheable. `encode.py` builds the keys, because
it is the file that knows what an encode depended on.
"""

import hashlib
import json
import os
import time
import uuid

# Where entries live under the user directory, beside the previews cache that
# is keyed the same way and kept for the same reason.
DIR_NAME = os.path.join("continuity", "latents")

# How long an entry nobody has read is kept, when nothing has been set. Counted
# from the last read (see `_touch`), not from the write: what makes an entry
# safe to delete is not its age but that no render has come back for it. A month
# because the store survives restarts and a project is worked on across days —
# the ceiling is the bound that actually does the work, and ageing is only for
# the reference nobody is ever coming back to. The settings page moves it, and
# 0 there means never.
DEFAULT_KEEP_DAYS = 30

# How long a staging file may sit before it is assumed abandoned. Its own clock,
# and not the retention above: a `.tmp` is a write in flight, so a day is
# already several orders of magnitude longer than any of them, and it must be
# cleaned up even where references are kept forever.
STAGING_SECONDS = 24 * 60 * 60

# The ceiling on the whole directory. Past it, the least recently read entries
# go until it fits. A video reference is the large resident here — its 2 fps
# presentation is tens of megabytes where its latent is single digits — so this
# is counted in gigabytes and not in entries.
DEFAULT_DISK_BYTES = 8 * 1024 ** 3

# What the in-memory tier will hold before it starts dropping its oldest reads.
# Small on purpose: it exists to make the re-queue after a prompt edit instant,
# and everything it drops is still on disk.
MEMORY_BYTES = 2 * 1024 ** 3

# Where a nameless VAE's fingerprint is parked once computed. On the object,
# because ComfyUI keeps the loaded VAE alive across queued prompts and computing
# it walks the whole state dict — a real cost, per reference per render, for an
# answer that cannot change while the object exists. A *named* VAE is a file
# stamp and is not memoised: it is one stat, and caching it would be how a
# replaced checkpoint went unnoticed.
_FINGERPRINT_ATTR = "_mmc_latent_fingerprint"

_memory = {}        # key -> (tensors, meta, bytes); insertion order is read order


def directory():
    """Where entries live. Created on demand.

    Under ComfyUI's user directory — the same place the settings file and the
    picker's thumbnail cache already sit — and deliberately *not* under temp,
    which core empties on startup and on exit. A store wiped by a restart is a
    store that pays for `ref_size: max` again every morning, and the argument
    for caching at all is that the reference has not changed. On a rented box
    the user directory is on the volume that persists; the render's own
    scratch, which genuinely should not survive, is `spill.py`.

    Nothing wipes this, so the ageing in `prune` is the only thing that does,
    and both of its numbers are the settings page's: how long an unread entry is
    kept, and how large the store may get.

    Two files beside each other under `previews/` and `latents/` for one clip,
    keyed by the same (path, mtime, size) identity — `preview._cache_path`
    builds its name the same way `media.stamp` builds this one's.
    """
    import folder_paths

    path = os.path.join(folder_paths.get_user_directory(), DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def enabled():
    """Whether references are cached at all. Off means encode every time."""
    from . import settings

    return bool(settings.load().get("latent_cache", True))


def disk_bytes():
    """The ceiling on the on-disk store, in bytes. 0 keeps the memory tier and
    writes nothing, which is the setting for a box with no room to spare."""
    from . import settings

    gigabytes = settings.load().get("latent_cache_gb", DEFAULT_DISK_BYTES / 1024 ** 3)
    return int(float(gigabytes) * 1024 ** 3)


def keep_seconds():
    """How long an unread entry is kept, in seconds -> None for forever."""
    from . import settings

    days = float(settings.load().get("latent_cache_days", DEFAULT_KEEP_DAYS))
    return None if days <= 0 else days * 24 * 60 * 60


def key(parts):
    """The parts an encode depended on -> the name of its entry.

    A digest rather than a readable name: the parts include absolute paths and a
    VAE fingerprint, and a filename built out of those is either unreadable or
    too long for the filesystem. `sort_keys` so a caller that builds the dict in
    a different order still lands on the same entry.
    """
    blob = json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:40]


def fingerprint(vae, name=None, folder="vae"):
    """A VAE -> a string that changes when its weights do.

    `name` is the checkpoint's filename, which is what actually identifies it.
    Given one, this is a stamp of that file — path, mtime and size, the same
    identity `media.stamp` gives a reference — and nothing is read out of the
    loaded object at all.

    **Nothing here may touch the live object's attributes.** That is not fussiness,
    it is the bug this function shipped with: it used to fold
    `str(vae.downscale_ratio)` into the digest, and on the H3 *video* VAE that
    attribute is a tuple holding a lambda (`comfy/sd.py`, the MiniMax H3 video
    branch), so the string carried a function's memory address. A new address
    every process meant a new key every restart, and no video or image reference
    could ever come back off the disk — while the audio VAE, whose ratios are the
    plain int 800, hit every time. A cache that silently never hits is worse than
    no cache, because it looks like it is working.

    Without a name — a hand-built graph wiring the segment node itself — it falls
    back to the shape of the weights: every parameter's key, shape and dtype.
    Deliberately no *values*: reading them means touching tensors an offloading
    backend may have staged elsewhere, and a digest that depends on what happened
    to be resident is the same class of bug in a subtler form. The cost is that
    two same-shaped checkpoints of the same architecture cannot be told apart on
    that path. Named VAEs — every graph this pack writes — do not use it.
    """
    if name:
        return _named_fingerprint(name, folder)

    found = getattr(vae, _FINGERPRINT_ATTR, None)
    if found is not None:
        return found

    digest = hashlib.sha256()
    digest.update(f"{getattr(vae, 'latent_channels', 0)}|"
                  f"{getattr(vae, 'latent_dim', 0)}|"
                  f"{getattr(vae, 'vae_dtype', None)}".encode("utf-8"))
    try:
        state = vae.first_stage_model.state_dict()
        for key in sorted(state):
            tensor = state[key]
            digest.update(f"{key}|{tuple(tensor.shape)}|{tensor.dtype}".encode("utf-8"))
    except Exception:  # noqa: BLE001 - a stub VAE in a test, or no state dict
        pass

    found = digest.hexdigest()[:32]
    try:
        setattr(vae, _FINGERPRINT_ATTR, found)
    except Exception:  # noqa: BLE001 - a VAE with __slots__; recompute per call
        pass
    return found


def _named_fingerprint(name, folder):
    """The checkpoint file behind `name`, stamped. Falls back to the name alone.

    A name that cannot be resolved still identifies the checkpoint better than
    nothing does — what the stamp adds is noticing a file replaced in place.
    """
    try:
        import folder_paths

        path = folder_paths.get_full_path(folder, name)
        info = os.stat(path)
        seed = f"{path}|{info.st_mtime_ns}|{info.st_size}"
    except Exception:  # noqa: BLE001
        seed = str(name)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def size_of(tensors):
    return sum(t.numel() * t.element_size() for t in tensors.values())


def _path(name):
    return os.path.join(directory(), f"{name}.safetensors")


def _touch(path):
    """Mark an entry as still in play, so `prune` reaches for another one."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def _remember(name, tensors, meta):
    """Put an entry in the memory tier, dropping the oldest reads to fit."""
    total = size_of(tensors)
    if total > MEMORY_BYTES:
        # One entry larger than the whole tier would evict everything and then
        # itself on the next store. It stays on disk, where it fits.
        return
    _memory.pop(name, None)
    _memory[name] = (tensors, meta, total)
    held = sum(entry[2] for entry in _memory.values())
    for oldest in list(_memory):
        if held <= MEMORY_BYTES:
            break
        held -= _memory.pop(oldest)[2]


def prune(now=None, ceiling=None, keep=False):
    """Delete what has aged out, then the least recently read until it fits.

    -> how many bytes went. Called when an entry is written rather than when one
    stops being useful, for the reason `spill.prune` is: nothing here knows when
    a project is finished with a reference, and every read pushes the file's
    stamp forward, so what ages out is what nothing has come back for.

    `keep` is the retention window in seconds; None keeps everything the ceiling
    has room for, which is what the settings page's "Forever" means. It defaults
    to `False` rather than to None because None is a *setting* here and not an
    absence — the two have to be tellable apart.
    """
    now = time.time() if now is None else now
    ceiling = disk_bytes() if ceiling is None else ceiling
    keep = keep_seconds() if keep is False else keep
    freed = 0
    try:
        entries = list(os.scandir(directory()))
    except OSError:
        return 0

    live = []
    for entry in entries:
        try:
            if not entry.is_file():
                continue
            stat = entry.stat()
            if entry.name.endswith(".tmp"):
                # A write another process is mid-flight on, or one that died
                # before its rename. Only the second is ours to clean up, and a
                # day is far longer than any write.
                if now - stat.st_mtime > STAGING_SECONDS:
                    os.remove(entry.path)
                continue
            if keep is not None and now - stat.st_mtime > keep:
                os.remove(entry.path)
                freed += stat.st_size
                continue
            live.append((stat.st_mtime, stat.st_size, entry.path))
        except OSError:
            # Gone under us, or another process's to worry about. Neither is
            # this render's business to insist on.
            continue

    held = sum(size for _, size, _ in live)
    for _, size, path in sorted(live):
        if held <= ceiling:
            break
        try:
            os.remove(path)
        except OSError:
            continue
        held -= size
        freed += size
    return freed


def fetch(name):
    """-> (tensors, meta, where) for `name`, or None. Tensors are the caller's.

    `where` is "memory" or "disk". It is handed back rather than logged here
    because this module has no idea which reference it is holding — and the
    difference is worth saying out loud: a disk hit is the store having survived
    a restart, which is the half of this feature that is otherwise invisible.

    A disk hit is promoted into memory, so the second prompt edit costs what the
    first one made cheap, and a memory hit still stamps the file behind it — see
    `_touch`. Memory hits are handed out as clones: an entry is read
    by every render that keys onto it and a conditioning block is not obviously
    read-only, so one caller writing through a cached tensor would be a bug that
    only appears on the second render.
    """
    path = _path(name)
    found = _memory.get(name)
    if found is not None:
        tensors, meta, _ = found
        # Re-insert so insertion order stays read order for the eviction above.
        _memory[name] = _memory.pop(name)
        # And stamp the file, even though it was not the file that answered:
        # what `prune` deletes is what nothing has come back for, and an entry
        # answered out of memory all week has been come back for all week.
        # Without this the hottest references are the ones that age off disk.
        _touch(path)
        return ({field: value.clone() for field, value in tensors.items()},
                dict(meta), "memory")

    if not os.path.isfile(path):
        return None
    try:
        from safetensors import safe_open
        from safetensors.torch import load_file

        with safe_open(path, framework="pt") as handle:
            raw = (handle.metadata() or {}).get("mmc")
        meta = json.loads(raw) if raw else {}
        tensors = load_file(path)
    except Exception:  # noqa: BLE001
        # A truncated or unreadable entry is a miss, not a render that stops:
        # the encode it stands in for is still there to run.
        try:
            os.remove(path)
        except OSError:
            pass
        return None

    _touch(path)
    _remember(name, tensors, meta)
    return ({field: value.clone() for field, value in tensors.items()},
            dict(meta), "disk")


def store(name, tensors, meta):
    """Keep an encode under `name`. -> the CPU copies it kept.

    Handing the copies back rather than nothing is what lets `encode._cached`
    have one path: a miss returns the same tensors on the same device a hit
    does, so the call sites never ask which one they got.

    Never raises. A cache that cannot be written is a slow render, and turning
    it into a failed one would be the cache deciding that a render it exists to
    speed up may not happen at all.
    """
    tensors = {field: value.detach().to("cpu").contiguous()
               for field, value in tensors.items()}
    _remember(name, tensors, meta)
    # Clones, for the reason `fetch` hands out clones: what the memory tier
    # holds is private to it, or the second render keys onto whatever the first
    # one wrote through its copy.
    handed = {field: value.clone() for field, value in tensors.items()}
    if disk_bytes() <= 0:
        return handed

    # A unique temporary rather than `{name}.tmp`: two renders can key onto the
    # same reference at once, and one flushing into the other's file would
    # rename a mixture of the two into place.
    staging = None
    try:
        from safetensors.torch import save_file

        path = _path(name)
        staging = os.path.join(directory(), f"{uuid.uuid4().hex}.tmp")
        save_file(tensors, staging, metadata={"mmc": json.dumps(meta, sort_keys=True)})
        os.replace(staging, path)
    except Exception:  # noqa: BLE001 - see the docstring
        if staging:
            try:
                os.remove(staging)
            except OSError:
                pass
        return handed
    prune()
    return handed


def forget():
    """Drop the memory tier. For tests, and for a settings page that turns the
    cache off — an entry held in RAM would otherwise outlive the switch."""
    _memory.clear()


def usage():
    """-> (entries, bytes) on disk. What the settings page reports."""
    count = total = 0
    try:
        entries = list(os.scandir(directory()))
    except OSError:
        return 0, 0
    for entry in entries:
        try:
            if entry.is_file() and not entry.name.endswith(".tmp"):
                count += 1
                total += entry.stat().st_size
        except OSError:
            continue
    return count, total


def clear():
    """Delete every entry. -> how many bytes went.

    A ceiling of nothing, so age does not come into it: this is somebody
    pressing Clear, not the store tidying up after itself.
    """
    forget()
    return prune(ceiling=0, keep=None)
