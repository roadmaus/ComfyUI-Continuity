"""A reference encoded once stays encoded, and stays encoded to the same thing.

The claim `latents.py` makes is narrow and easy to get wrong in either
direction. Too eager a key and a reference comes back after something that
really did change it — a replaced file, another canvas, other weights — which is
a wrong render nothing raises about. Too timid a key and the cache never hits,
which is the feature not existing. So the suite is mostly a table of what must
miss and what must not.

The other half is the invariant that makes it safe to ship: a hit and a miss
hand the model the same tensors. `encode._quantize` runs on both paths for that
reason, so turning the cache off can change how long a render takes and nothing
else.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_latents.py

Skips itself with a message if ComfyUI core cannot be imported.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)

try:
    import torch
except Exception as exc:  # noqa: BLE001
    print(f"skipped: needs torch ({type(exc).__name__}: {exc})")
    sys.exit(0)


def _load(name):
    if "mmc" not in sys.modules:
        package = types.ModuleType("mmc")
        package.__path__ = [ROOT]
        sys.modules["mmc"] = package
    spec = importlib.util.spec_from_file_location(f"mmc.{name}", os.path.join(ROOT, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmc.{name}"] = module
    spec.loader.exec_module(module)
    return module


try:
    latents = _load("latents")
    compiler = _load("compile")
    media = _load("media")
    encoder = _load("encode")
except Exception as exc:  # noqa: BLE001
    print(f"skipped: package not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

from harness import FAILURES, check, passed

# The store lives in a temporary of its own, and the settings file this machine
# happens to be carrying is not allowed to decide whether the suite runs.
STORE = tempfile.mkdtemp(prefix="mmc-latents-")
INPUT = tempfile.mkdtemp(prefix="mmc-refs-")
latents.directory = lambda: STORE
latents.enabled = lambda: True
latents.disk_bytes = lambda: 64 * 1024 ** 3
latents.keep_seconds = lambda: latents.DEFAULT_KEEP_DAYS * 24 * 60 * 60
media.resolve = lambda filename: os.path.join(INPUT, str(filename))


def written(name, body=b"x"):
    """A file for a reference to stand on. Only its stat is ever read here."""
    path = os.path.join(INPUT, name)
    with open(path, "wb") as handle:
        handle.write(body)
    return name


def entries():
    return sorted(f for f in os.listdir(STORE) if f.endswith(".safetensors"))


# ---- the store ---------------------------------------------------------------

latents.forget()
latents.store("alpha", {"latent": torch.arange(24, dtype=torch.float32).reshape(2, 12)},
              {"latent_h": 3, "note": "kept"})

tensors, meta, where = latents.fetch("alpha")
check("a stored latent comes back", tensors["latent"].tolist(),
      torch.arange(24, dtype=torch.float32).reshape(2, 12).tolist())
check("...with its metadata", meta, {"latent_h": 3, "note": "kept"})
check("...and says it came out of memory", where, "memory")
check("an unknown key is a miss", latents.fetch("nothing-here"), None)

# The memory tier is a convenience over the disk tier, never a second source of
# truth: dropping it has to change how fast the answer arrives and not the
# answer. This is the only assertion that proves the file on disk is real.
latents.forget()
from_disk, _, where = latents.fetch("alpha")
check("...off the disk too, once memory has forgotten it",
      from_disk["latent"].tolist(), tensors["latent"].tolist())
# Said out loud on the terminal, because a disk hit is the store having survived
# a restart and that is the half of this nobody can otherwise see happening.
check("...and says so", where, "disk")

# Every handout is a copy. An entry is read by every render that keys onto it,
# and a conditioning block is not obviously read-only — one caller writing
# through a cached tensor would be a bug that only shows on the second render.
from_disk["latent"][0][0] = -999.0
again, _, _ = latents.fetch("alpha")
check("a caller cannot write through a cached tensor", float(again["latent"][0][0]), 0.0)

# A key is its parts, not the order they were written in.
check("key order does not matter",
      latents.key({"a": 1, "b": 2}), latents.key({"b": 2, "a": 1}))
check("a changed part is a different key",
      latents.key({"a": 1}) == latents.key({"a": 2}), False)

# A half-written entry has to read as a miss. It cannot be repaired and it
# must not be trusted, so it is deleted and the encode it stood in for runs.
with open(os.path.join(STORE, "alpha.safetensors"), "r+b") as handle:
    handle.truncate(11)
latents.forget()
check("a truncated entry is a miss", latents.fetch("alpha"), None)
check("...and is not left on disk to be missed again", entries(), [])


# ---- what ages out, and what is squeezed out ---------------------------------

def fill(name, megabytes):
    latents.store(name, {"latent": torch.zeros(megabytes * 1024 ** 2 // 4)}, {})


shutil.rmtree(STORE, ignore_errors=True)
os.makedirs(STORE, exist_ok=True)
latents.forget()
for name in ("old", "new"):
    fill(name, 1)
old_enough = time.time() - latents.DEFAULT_KEEP_DAYS * 24 * 60 * 60 - 60
os.utime(os.path.join(STORE, "old.safetensors"), (old_enough,) * 2)
latents.prune()
check("an entry nothing has read in the keep window goes", entries(), ["new.safetensors"])

# "Forever" on the settings page. The ceiling is then the only bound, which is
# the whole reason 0 is offered rather than being a way to fill a disk.
fill("old", 1)
os.utime(os.path.join(STORE, "old.safetensors"), (old_enough,) * 2)
latents.prune(keep=None)
check("kept forever, age stops deciding", entries(), ["new.safetensors", "old.safetensors"])
latents.prune(keep=None, ceiling=3 * 1024 ** 2 // 2)
check("...and the ceiling still does, oldest read first", entries(), ["new.safetensors"])

shutil.rmtree(STORE, ignore_errors=True)
os.makedirs(STORE, exist_ok=True)
latents.forget()
for index, name in enumerate(("first", "second", "third")):
    fill(name, 4)
    # Distinct stamps, so "least recently read" is a real ordering rather than
    # whatever order the filesystem happens to answer in.
    os.utime(os.path.join(STORE, f"{name}.safetensors"), (time.time() - 100 + index,) * 2)
latents.fetch("first")     # reading it is what keeps it
latents.prune(ceiling=9 * 1024 ** 2)
check("the ceiling drops the least recently read first",
      entries(), ["first.safetensors", "third.safetensors"])

count, size = latents.usage()
check("usage counts what is left", count, 2)
check("...and its bytes", size > 8 * 1024 ** 2, True)
check("clearing takes the rest", latents.clear() > 0, True)
check("...leaving nothing", entries(), [])


# ---- a VAE is identified by its weights --------------------------------------

class Weights(torch.nn.Module):
    def __init__(self, value):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.full((8, 8), float(value)))


class Vae:
    """One latent step per encoded frame run, shaped [B, C, T, H, W].

    The same stub `test_seam_anchor.py` encodes against, with real weights
    hung off it so it can be told apart from another one.
    """

    latent_channels = 24

    def __init__(self, value=1.0):
        self.first_stage_model = Weights(value)
        self.calls = 0

    def encode(self, image):
        self.calls += 1
        frames = image.shape[0]
        steps = 1
        if frames > 1:
            covered, steps = 0, 0
            while covered < frames:
                covered += encoder.FRAME_PER_TOKEN[steps % 5]
                steps += 1
        # Something derived from the pixels, so a cached latent that came back
        # from the wrong entry is visible rather than a plausible zero.
        return torch.full((1, 24, steps, 4, 4), float(image.mean()))


# A checkpoint is identified by its file, and this is the assertion the whole
# cache rests on: the same checkpoint has to fingerprint the same *in a process
# that has never seen it before*, or nothing can ever come back off the disk.
#
# It did not. `fingerprint` used to fold `str(vae.downscale_ratio)` into the
# digest, and on the H3 video VAE that attribute is a tuple holding a lambda —
# so the digest carried a function's memory address, new every restart. Video
# and image references could never hit; the audio VAE, whose ratios are the
# plain int 800, hit every time. Nothing raised. A cache that silently never
# hits is worse than no cache, because it looks like it is working.
written("h3-video-vae.safetensors")
sys.modules["folder_paths"] = types.SimpleNamespace(
    get_full_path=lambda folder, name: os.path.join(INPUT, name))


class Lambdas(Vae):
    """A VAE wearing the attributes the real one wears, freshly built.

    Two of these are what one checkpoint looks like to two different processes:
    the same file, and every unhashable attribute at a new address.
    """

    def __init__(self, value=1.0):
        super().__init__(value)
        self.downscale_ratio = (lambda a: a, 16, 16)
        self.upscale_ratio = (lambda a: a, 16, 16)


check("one checkpoint fingerprints the same to a process that has never seen it",
      latents.fingerprint(Lambdas(), "h3-video-vae.safetensors"),
      latents.fingerprint(Lambdas(), "h3-video-vae.safetensors"))
check("two checkpoints do not",
      latents.fingerprint(Lambdas(), "h3-video-vae.safetensors")
      == latents.fingerprint(Lambdas(), "other-vae.safetensors"), False)
# The same stamp a reference gets, for the same reason: a checkpoint replaced in
# place under its own name is a different checkpoint.
before = latents.fingerprint(Lambdas(), "h3-video-vae.safetensors")
written("h3-video-vae.safetensors", b"a different checkpoint entirely")
check("a checkpoint replaced in place is a different one",
      latents.fingerprint(Lambdas(), "h3-video-vae.safetensors") == before, False)

# Unnamed — a hand-built graph wiring the segment node itself. The weights'
# shape, and deliberately not their values: reading those means touching tensors
# an offloading backend may have staged elsewhere, which is the same class of
# bug in a subtler form. Two same-shaped checkpoints are indistinguishable here,
# which is the documented cost of a path no graph this pack writes takes.
check("without a name, weights of the same shape fingerprint alike",
      latents.fingerprint(Lambdas(1.0)), latents.fingerprint(Lambdas(2.0)))
check("...and the lambdas still do not move it",
      latents.fingerprint(Lambdas()), latents.fingerprint(Vae()))


# ---- the encoder -------------------------------------------------------------

class Clip:
    def __init__(self):
        self.tokenized = None

    def tokenize(self, prompt, **kwargs):
        self.tokenized = kwargs
        return "tokens"

    def encode_from_tokens_scheduled(self, tokens):
        return [[torch.zeros(1, 9, 8), {}]]


class AudioVae:
    audio_sample_rate = 32000

    def __init__(self):
        self.first_stage_model = Weights(3.0)
        self.calls = 0

    def encode(self, waveform):
        self.calls += 1
        seconds = waveform.shape[1] / self.audio_sample_rate
        return torch.zeros(1, 32, 2, max(1, round(seconds * 40)))


class Counted(media.Deferred):
    """A deferred entry that says whether anything ever asked it to decode."""

    def __init__(self, build):
        self.reads = 0

        def decode():
            self.reads += 1
            return build()

        super().__init__(decode)


written("face.png")
written("clip.mp4")


def request(prompt="she turns to face @img-1", short_edge=768,
            duration=6.0, ref_size="max", video=True):
    assets = [{"handle": "img-1", "kind": "image", "role": "reference",
               "filename": "face.png", "ref_size": ref_size}]
    if video:
        assets.append({"handle": "vid-1", "kind": "video", "role": "reference",
                       "filename": "clip.mp4", "ref_size": ref_size})
    return compiler.compile_request(
        {"prompt": prompt, "duration_s": duration, "aspect": "16:9",
         "short_edge": short_edge, "assets": assets},
        image_size_lookup=lambda _f: (1344, 768))


# Decoded once and handed out as clones, so a run's pixels are the same pixels
# every time: a cache that came back with the wrong entry has to be visible as a
# difference in the latents, and it cannot be if the source is noise.
SOURCE_IMAGE = torch.rand(1, 512, 512, 3)
SOURCE_FRAMES = torch.rand(97, 480, 854, 3)


def run(compiled, vae, audio_vae=None, names=None):
    """-> (the conditioning's values, the deferred entries it did or did not read)."""
    clip = Clip()
    pool = {
        "img-1": Counted(lambda: {"image": SOURCE_IMAGE.clone()}),
        "vid-1": Counted(lambda: {"frames": SOURCE_FRAMES.clone(), "audio": None}),
    }
    cond, _ = encoder._encode_references(
        clip, vae, audio_vae or AudioVae(), compiled, pool,
        names if names is not None else {"vae": "h3-video-vae.safetensors",
                                         "audio_vae": "h3-audio-vae.safetensors"})
    return cond[0][1], pool, clip


def blocks(values):
    return values.get("minimax_refs") or []


def shape_of(values):
    return [(b["kind"], b.get("latent_t"), b["latent_h"], b["latent_w"],
             round(float(b["latent"].float().mean()), 5)) for b in blocks(values)]


shutil.rmtree(STORE, ignore_errors=True)
os.makedirs(STORE, exist_ok=True)
latents.forget()

vae = Vae()
first, pool, clip = run(request(), vae)
check("both references encode the first time", vae.calls, 2)
check("...and both files were read", [pool["img-1"].reads, pool["vid-1"].reads], [1, 1])
first_items = [(item["type"], tuple(item["data"].shape)) for item in clip.tokenized["minimax_ref_items"]]

# The claim the whole thing exists for.
second, pool, clip = run(request(prompt="she turns away from @img-1"), vae)
check("a different prompt encodes nothing again", vae.calls, 2)
check("...and opens no file", [pool["img-1"].reads, pool["vid-1"].reads], [0, 0])
check("the blocks are the ones that were encoded", shape_of(second), shape_of(first))
check("the presentation is the one that was encoded",
      [(item["type"], tuple(item["data"].shape))
       for item in clip.tokenized["minimax_ref_items"]], first_items)

# `max` is sized from the reference's own source, so it survives a change of
# canvas — which is the point of caching it at all: the expensive setting is
# the one that stops being expensive.
wider, _, _ = run(request(short_edge=512), vae)
check("a 'max' reference survives another canvas", vae.calls, 2)
check("...as the same blocks", shape_of(wider), shape_of(first))

# `match` reads the generation's canvas, so it must not.
latents.forget()
matched = Vae()
run(request(ref_size="match"), matched)
check("a 'match' reference encodes for its canvas", matched.calls, 2)
run(request(ref_size="match", prompt="another line"), matched)
check("...and not again for the same one", matched.calls, 2)
run(request(ref_size="match", short_edge=512), matched)
check("...but does for a different one", matched.calls, 4)

# A video is cut to the generation's length before it is encoded, so its length
# is in the key whatever the canvas setting is. The image beside it is not.
latents.clear()
lengths = Vae()
run(request(duration=6.0), lengths)
run(request(duration=8.0), lengths)
check("a longer generation re-encodes the video and not the image", lengths.calls, 3)

# A file replaced in place under the same name is a different file.
latents.clear()
swapped = Vae()
run(request(video=False), swapped)
written("face.png", b"different bytes entirely")
run(request(video=False), swapped)
check("a replaced source re-encodes", swapped.calls, 2)

# Another checkpoint is other latents — and the same checkpoint in a brand new
# VAE object is not, which is the case a restart makes and the one that was
# broken.
latents.clear()
swap = Vae()
run(request(video=False), swap)
run(request(video=False, prompt="one more"), Vae())
check("the same checkpoint in a fresh object still hits", swap.calls, 1)
other = Vae()
run(request(video=False), other, names={"vae": "some-other-vae.safetensors"})
check("another checkpoint re-encodes", other.calls, 1)

# Off, the encoder does what it always did — including producing exactly what
# the cache would have handed back, which is what makes the switch safe.
latents.forget()
try:
    latents.enabled = lambda: False
    plain = Vae()
    off_first, _, _ = run(request(), plain)
    off_second, _, _ = run(request(prompt="a different line again"), plain)
    check("with the cache off every render encodes", plain.calls, 4)
    check("...to the same blocks a hit would have given",
          shape_of(off_second), shape_of(off_first))
finally:
    latents.enabled = lambda: True

# A reference whose file is gone is not the cache's to complain about — the
# decode says so, by name. Here the decode is supplied, so it simply encodes.
latents.clear()
os.remove(os.path.join(INPUT, "clip.mp4"))
homeless = Vae()
run(request(), homeless)
run(request(prompt="one more line"), homeless)
# Two renders: the image is encoded once and cached, the clip is encoded both
# times because there is no file to key it on.
check("an unstampable reference encodes every render, and the one beside it does not",
      homeless.calls, 3)
written("clip.mp4")


# ---- a reference that is cited for its sound as well --------------------------
#
# `picture+sound` is two plan steps against one file, so if only the picture
# came out of the cache the clip would still be opened and decoded for its
# soundtrack — the whole cost the picture's entry had just avoided.

latents.clear()


def sounding(prompt="the room sounds like @vid-1"):
    return compiler.compile_request(
        {"prompt": prompt, "duration_s": 6.0, "aspect": "16:9", "short_edge": 768,
         "assets": [{"handle": "vid-1", "kind": "video", "role": "reference",
                     "filename": "clip.mp4", "ref_size": "max",
                     "track": "picture+sound"}]},
        image_size_lookup=lambda _f: (1344, 768))


SOURCE_AUDIO = {"waveform": torch.rand(1, 2, 32000 * 3), "sample_rate": 32000}


def run_sounding(compiled, vae, audio_vae):
    clip = Clip()
    entry = Counted(lambda: {"frames": SOURCE_FRAMES.clone(),
                             "audio": {"waveform": SOURCE_AUDIO["waveform"].clone(),
                                       "sample_rate": 32000}})
    cond, _ = encoder._encode_references(clip, vae, audio_vae, compiled, {"vid-1": entry})
    return cond[0][1], entry


sounded = sounding()
paired, audio_vae = Vae(), AudioVae()
values, entry = run_sounding(sounded, paired, audio_vae)
check("a picture+sound reference compiles to one block", [b["kind"] for b in blocks(values)],
      ["video_audio"])
check("...encoding both halves the first time",
      (paired.calls, audio_vae.calls, entry.reads), (1, 1, 1))

again, entry = run_sounding(sounding("the room is silent now"), paired, audio_vae)
check("...and neither half again for another prompt",
      (paired.calls, audio_vae.calls), (1, 1))
check("...so the clip is never opened", entry.reads, 0)
check("the block is the one that was encoded", shape_of(again), shape_of(values))
check("...including how long its sound is",
      [b["ref_audio_t"] for b in blocks(again)], [b["ref_audio_t"] for b in blocks(values)])


# ---- what the terminal is told -----------------------------------------------
#
# A render that sits silent for a minute is the complaint this answers, so the
# lines are part of the feature and not decoration around it. Two things have to
# hold: a miss says it is about to work *before* it does, and a hit says where it
# came from.

import logging


class Heard(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


heard = Heard()
root = logging.getLogger()
# The suite's own handlers stand aside for the duration: these lines are the
# thing under test, not something to read past on the way to the result.
stood_aside, root.handlers = root.handlers, [heard]
was = root.level
root.setLevel(logging.INFO)

latents.clear()
spoken = Vae()
run(request(video=False), spoken)
missed = [line for line in heard.lines if "@img-1" in line]
check("a miss says it is encoding before it encodes",
      missed[0], "[MiniMax] @img-1 image (max): encoding, nothing cached")
check("...and what that cost once it has",
      missed[1].split(" in ")[0], "[MiniMax] @img-1 image (max): encoded")

heard.lines.clear()
run(request(video=False, prompt="a different line"), spoken)
check("a hit says where it came from",
      [line for line in heard.lines if "@img-1" in line][0].rsplit(" (", 1)[0],
      "[MiniMax] @img-1 image (max): reused from memory")
check("...and the render says whether the cache worked at all",
      [line for line in heard.lines if "references:" in line][0].startswith(
          "[MiniMax] references: all 1 reused"), True)

# Off, the lines still come — otherwise "no output" would mean both "the cache
# is off" and "the pack is not loaded", and those need different fixes.
heard.lines.clear()
latents.enabled = lambda: False
try:
    run(request(video=False), Vae())
finally:
    latents.enabled = lambda: True
check("with the cache off it says that is why it is encoding",
      [line for line in heard.lines if "@img-1" in line][0],
      "[MiniMax] @img-1 image (max): encoding (cache off)")

# A soundtrack latent is a few hundred kilobytes against a video's forty
# megabytes. Reported in megabytes it read as "0 MB", which beside the word
# "reused" says the opposite of what the line is for.
check("a small entry is not reported as nothing",
      [encoder._said(n) for n in (400 * 1024, 15 * 1024 ** 2, 2 * 1024 ** 3)],
      ["400 KB", "15 MB", "2.00 GB"])

root.handlers, root.level = stood_aside, was


# ---- deferred decoding -------------------------------------------------------

reads = []
entry = media.Deferred(lambda: (reads.append(1), {"image": "decoded"})[1])
check("a deferred entry has not decoded yet", reads, [])
check("reading it decodes", entry["image"], "decoded")
check("...once", (entry["image"], entry.get("image"), "image" in entry, len(reads)),
      ("decoded", "decoded", True, 1))

shutil.rmtree(STORE, ignore_errors=True)
shutil.rmtree(INPUT, ignore_errors=True)
passed("reference latents survive the prompt, and nothing else")
