"""A saved reference round-trips through the file and into the payload.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_refmod_encode.py

Skips itself with a message if torch or ComfyUI core cannot be imported.

Three claims, each the one a render depends on. A mod written by `refmod.save`
reads back as the file the sibling pack would write: the header names it, the
tensor is what was handed in, and a picture sits beside it. `compress` keeps
the latent's aspect and lands on the grid the dial asked for. And the encode
branch hands the DiT the stored latent *untouched* — not a re-encode of the
decoded picture — while the tokenizer gets a picture decoded from it, sized
the way the VAE decodes: for a compressed mod, a small blurred one.
"""

import os
import sys
import tempfile

import layout

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
sys.path.insert(0, COMFY)
try:
    import torch
except Exception as exc:  # noqa: BLE001
    print(f"skipped: needs torch ({type(exc).__name__}: {exc})")
    sys.exit(0)


try:
    _pkg = layout.load("refmod", "latents", "canvas", "h3_declare", "contextir", "subjects",
                       "compile", "media", "encode", package="mmc")
    refmod, latents, compiler = _pkg.refmod, _pkg.latents, _pkg.compile
    media, encoder = _pkg.media, _pkg.encode
except Exception as exc:  # noqa: BLE001
    print(f"skipped: package not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

from harness import FAILURES, check, passed

ROOT = tempfile.mkdtemp(prefix="mmc-refmods-")
STORE = tempfile.mkdtemp(prefix="mmc-latents-")
latents.directory = lambda: STORE
latents.enabled = lambda: True
latents.disk_bytes = lambda: 64 * 1024 ** 3
latents.keep_seconds = lambda: latents.DEFAULT_KEEP_DAYS * 24 * 60 * 60
# The model folders, without ComfyUI's registry: one root, this temporary.
refmod.roots = lambda: [ROOT]
refmod.register = lambda: None


class FakeVAE:
    """Enough of `comfy.sd.VAE` for the branch: 16px per latent cell, a decode
    that paints each frame a flat grey from its latent mean, and a record of
    what was asked so the test can prove the latent was never re-encoded."""

    output_device = torch.device("cpu")
    device = torch.device("cpu")

    def __init__(self):
        self.encoded = 0
        self.decoded = 0

    def vae_output_dtype(self):
        return torch.float32

    def encode(self, pixels):
        self.encoded += 1
        frames, height, width = pixels.shape[0], pixels.shape[1], pixels.shape[2]
        return torch.zeros(1, 24, frames, height // 16, width // 16)

    def decode(self, latent):
        self.decoded += 1
        _, _, t, h, w = latent.shape
        level = latent.float().mean().clamp(0, 1)
        return torch.full((1, t, h * 16, w * 16, 3), float(level))


# ---- save and read back ----------------------------------------------------------

full = torch.rand(1, 24, 1, 40, 64)
path = refmod.save("cast/anna", full, {"kind": "image", "mode": "encode",
                                        "description": "green coat", "concept_type": "identity"},
                   preview=torch.rand(1, 640, 1024, 3))
check("the file lands in the root", os.path.relpath(path, ROOT), os.path.join("cast", "anna.safetensors"))
meta = refmod.header(path)
check("...and reads back as an image mod",
      (meta["kind"], meta["mode"], meta["latent_h"], meta["latent_w"], meta["tokens"]),
      ("image", "encode", 40, 64, 20 * 32))
check("...with its words", (meta["description"], meta["concept_type"]), ("green coat", "identity"))
check("...as the sibling format", (meta["format_version"], meta.get("made_by")), (4, "continuity"))
back = refmod.load_latent(path)
check("the latent survives the file (to fp16)", torch.allclose(back, full, atol=1e-3), True)
check("a picture sits beside it", os.path.basename(refmod.preview_path(path) or ""), "anna.png")
check("it lists", [(r["path"], r["kind"], r["tokens"], r["preview"]) for r in refmod.listing()[0]],
      [("refmod:cast/anna", "image", 640, True)])
check("...with its folder", refmod.listing()[1], ["cast"])
check("it resolves", refmod.resolve("refmod:cast/anna"), path)

# ---- compression -----------------------------------------------------------------

small = refmod.compress(full, 16, steps=5)
check("a compressed latent lands on the dial at the source's aspect",
      list(small.shape), [1, 24, 1, 10, 16])
check("...and pooling alone is the mean", torch.allclose(
    refmod.compress(full, 16, steps=0),
    torch.nn.functional.adaptive_avg_pool3d(full, (1, 10, 16))), True)
check("a grid the source already is passes through", refmod.compress(full, 64, steps=5) is full, True)

# ---- a stack ------------------------------------------------------------------------
# One character as one file: sources of different shapes, each pooled to one
# square grid, end to end on T. A cap takes frames off the clips, never the stills.

tall = torch.randn(1, 24, 1, 64, 40)
clip = torch.randn(1, 24, 9, 32, 48)
stacked, kept = refmod.stack([full, tall, clip], 16, steps=2)
check("a stack is one square-grid latent, sources end to end",
      (list(stacked.shape), kept), ([1, 24, 11, 16, 16], [1, 1, 9]))
check("...and the still's frame is its own pooled grid", torch.allclose(
    stacked[:, :, 1:2], refmod.compress(tall, 16, steps=2, grid=(16, 16))), True)
capped, kept = refmod.stack([full, clip, tall], 16, steps=0, max_tokens=64 * 5)
check("under a cap the clip loses frames and the stills keep theirs",
      (list(capped.shape), kept), ([1, 24, 5, 16, 16], [1, 3, 1]))
stackfile = refmod.save("cast/pair", stacked, {"kind": "video", "mode": "training", "source": "stack",
                                                 "tags": ["2 img, 1 vid"]})
smeta = refmod.header(stackfile)
check("a stack reads back as a video mod with its frames' tokens",
      (smeta["kind"], smeta["latent_t"], smeta["tokens"], smeta["source"]), ("video", 11, 11 * 64, "stack"))

# ---- the encode branch -----------------------------------------------------------

compressed = refmod.save("cast/anna-small", small, {"kind": "image", "mode": "training"})


class Asset:
    def __init__(self, handle, filename, kind="image"):
        self.handle, self.filename, self.kind = handle, filename, kind
        self.ref_size, self.trim = "match", None
        self.mod = True


class Compiled:
    width, height, frames = 1024, 640, 121


vae = FakeVAE()
asset = Asset("img-1", "refmod:cast/anna-small")
key = encoder._mod_key(asset.filename, "vae-print")
check("the key is the file and the VAE, nothing about the canvas",
      sorted(key), ["file", "kind", "vae"])
tensors, meta = encoder._mod_tensors(vae, asset, compressed)
check("the DiT half is the stored latent, untouched",
      torch.allclose(tensors["latent"], small.half().float(), atol=1e-3), True)
check("...never re-encoded", vae.encoded, 0)
check("the tokenizer half is decoded from it, at the latent's own size",
      list(tensors["presentation"].shape), [1, 160, 256, 3])
check("...as 8-bit, like every presentation", tensors["presentation"].dtype, torch.uint8)
check("the block dims are the latent's", (meta["latent_h"], meta["latent_w"]), (10, 16))

# A picture carrying its rendition in H3's space is read from the file, and
# its pixels are never opened: the entry is a `Deferred` whose decode is the
# failure. A rendition for another family alone is a picture to H3.


class Bound(Asset):
    def __init__(self, handle, filename, mods, kind="image"):
        super().__init__(handle, filename, kind)
        self.mod = False
        self.mods = mods

    def mod_for(self, space):
        return self.mods.get(space)


never = media.Deferred(lambda: (_ for _ in ()).throw(AssertionError("the picture was decoded")))
bound = Bound("img-3", "anna.png", {"h3_video": "refmod:cast/anna-small", "flux2": "refmod:cast/anna.flux2"})
check("a bound picture is read from its H3 rendition, pixels unopened",
      encoder._mod_of(bound, never), compressed)
check("...and a picture whose only rendition is Klein's is encoded here",
      encoder._mod_of(Bound("img-4", "anna.png", {"flux2": "refmod:cast/anna.flux2"}), never), None)
try:
    encoder._mod_of(Bound("img-5", "anna.png", {"h3_video": "refmod:cast/gone"}), never)
    missing = ""
except ValueError as exc:
    missing = str(exc)
check("a rendition that has gone is refused by name, not encoded around",
      ("@img-5" in missing, "gone" in missing), (True, True))

# A mod made elsewhere has no picture; the first decode writes one beside it.
foreign = refmod.save("theirs", torch.rand(1, 24, 1, 16, 16), {"kind": "image"})
check("a mod made elsewhere has no picture", refmod.preview_path(foreign), None)
encoder._mod_tensors(vae, Asset("img-2", "refmod:theirs"), foreign)
check("...until a render decodes it", os.path.basename(refmod.preview_path(foreign) or ""), "theirs.png")

# A clip mod presents a 2 fps sampling with timestamps, as `encode_video` does.
clip = refmod.save("walk", torch.rand(1, 24, 3, 16, 16), {"kind": "video", "mode": "encode"})
tensors, meta = encoder._mod_tensors(vae, Asset("vid-1", "refmod:walk", "video"), clip)
check("a clip mod presents its first frame per half second",
      (list(tensors["presentation"].shape), meta["timestamps"], meta["latent_t"]),
      ([1, 256, 256, 3], [0.0], 3))

# Through the cache, the second read is a hit and hands back the same tensors.
media.resolve = lambda filename: refmod.resolve(filename)
latents.forget()
first, _ = encoder._cached("@img-1 mod", encoder._mod_key(asset.filename, "vae-print"),
                           lambda: encoder._mod_tensors(vae, asset, compressed))
decodes = vae.decoded
second, _ = encoder._cached("@img-1 mod", encoder._mod_key(asset.filename, "vae-print"),
                            lambda: encoder._mod_tensors(vae, asset, compressed))
check("a second render reads the cache, not the VAE", vae.decoded, decodes)
check("...and gets the same latent", torch.equal(first["latent"], second["latent"]), True)

# ---- written again, in the other mode --------------------------------------------
# The route module registers itself on the server at import; a stand-in server
# takes the registrations and does nothing with them, which is all this needs.

import importlib.util  # noqa: E402
import types  # noqa: E402


class _Routes:
    def get(self, *_a, **_k): return lambda fn: fn
    def post(self, *_a, **_k): return lambda fn: fn


server_stub = types.ModuleType("server")
server_stub.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=_Routes()))
sys.modules.setdefault("server", server_stub)
try:
    _pkg = layout.load("jobs", package="mmc")
    routes_pkg = types.ModuleType("mmc.routes")
    routes_pkg.__path__ = [os.path.join(layout.PY_ROOT, "routes")]
    sys.modules["mmc.routes"] = routes_pkg
    spec = importlib.util.spec_from_file_location(
        "mmc.routes.refmod", os.path.join(layout.PY_ROOT, "routes", "refmod.py"))
    remake_routes = importlib.util.module_from_spec(spec)
    sys.modules["mmc.routes.refmod"] = remake_routes
    spec.loader.exec_module(remake_routes)
except Exception as exc:  # noqa: BLE001
    print(f"remake: skipped ({type(exc).__name__}: {exc})")
    remake_routes = None

if remake_routes is not None:
    jobs = _pkg.jobs
    jobs.progress = lambda: (lambda fraction: None)
    remake_routes._vae = lambda name, space=None: vae
    # One picture in the "input folder", by name; everything else is gone.
    picture = torch.rand(1, 640, 1024, 3)
    media.resolve = lambda filename: (refmod.resolve(filename) if refmod.is_mod(filename)
                                      else filename if filename == "anna/face.png"
                                      else (_ for _ in ()).throw(media.MediaError(f"{filename!r} gone")))
    media.load_image = lambda filename, crop=None: picture

    # Made full from the picture, the way `_run_job` writes it: the header
    # keeps the picker's path, which is what a remake reads it back from.
    made = remake_routes._run_job({"name": "anna-full", "subfolder": "cast", "sources": ["anna/face.png"],
                                   "mode": "full", "vae": "x"})
    row = made["mods"][0]
    check("a mod names the picture it was made of, path and all",
          (row["source_file"], row["source_present"] in (True, False)), ("anna/face.png", True))
    fullpath = refmod.resolve(row["path"])
    check("...as a full encode of it", refmod.header(fullpath)["mode"], "encode")
    stamp = os.stat(fullpath).st_mtime_ns
    encodes = vae.encoded

    # Full -> compressed, from the picture: same file, new grid, words kept.
    out = remake_routes._run_remake({"mods": ["refmod:cast/anna-full"], "mode": "compressed",
                                     "grid": 16, "steps": 2, "vae": "x"})
    again = refmod.header(fullpath)
    check("re-encoded in place: the file keeps its name",
          out["mods"][0]["path"], "refmod:cast/anna-full")
    check("...and is now compressed, on the grid asked for",
          (again["mode"], again["latent_h"], again["latent_w"]), ("training", 10, 16))
    check("...read from the picture again", vae.encoded, encodes + 1)
    check("...still naming it", again["source_file"], "anna/face.png")
    check("...and rewritten on disk, so a render's cache key moves",
          os.stat(fullpath).st_mtime_ns != stamp, True)

    # Compressed -> full, from the picture, back to the encode.
    remake_routes._run_remake({"mods": ["refmod:cast/anna-full"], "mode": "full", "vae": "x"})
    check("...and back to full", (refmod.header(fullpath)["mode"], refmod.header(fullpath)["latent_h"]),
          ("encode", 40))

    # The picture gone: a full mod is still the encode, so it compresses from
    # itself; it cannot be made full again, and the refusal names the picture.
    orphan = refmod.save("cast/orphan", full, {"kind": "image", "mode": "encode",
                                                "source_file": "lost/face.png"})
    encodes = vae.encoded
    remake_routes._run_remake({"mods": ["refmod:cast/orphan"], "mode": "compressed",
                               "grid": 16, "steps": 0, "vae": "x"})
    check("a full mod whose picture is gone compresses from its own latent",
          (refmod.header(orphan)["mode"], vae.encoded), ("training", encodes))
    try:
        remake_routes._run_remake({"mods": ["refmod:cast/orphan"], "mode": "full", "vae": "x"})
        refused = ""
    except jobs.JobError as exc:
        refused = str(exc)
    check("...and cannot be made full again without it", "lost/face.png" in refused, True)
    try:
        remake_routes._run_remake({"mods": ["refmod:cast/pair"], "mode": "full", "vae": "x"})
        refused = ""
    except jobs.JobError as exc:
        refused = str(exc)
    check("a stack is refused by name", "stack" in refused, True)

# ---- a clip: thinned, weighted toward motion ------------------------------------

# A held pose: four frames, the middle two copies of the first. Thinning keeps
# the first, drops the copies, keeps the one that moved.
still = torch.randn(1, 24, 1, 8, 8)
moved = torch.randn(1, 24, 1, 8, 8)
held = torch.cat([still, still, still + 1e-4, moved], dim=2)
kept_latent, kept, changes = refmod.thin(held)
check("thinning drops the frames that repeat the one kept before",
      (kept, list(kept_latent.shape)), ([0, 3], [1, 24, 2, 8, 8]))
check("...and measures every frame against the last one kept", len(changes), 3)
check("threshold 0 keeps every frame", refmod.thin(held, 0)[1], [0, 1, 2, 3])
check("a still has nothing to thin", refmod.thin(full)[1], [0])

# Motion weights: flat where nothing moves, heavier where something does.
check("a clip that never changes is weighed evenly (no weights)",
      refmod.motion_weights(torch.cat([still, still, still], dim=2), 1.0), None)
arm = torch.zeros(1, 24, 3, 8, 8)
arm[:, :, 1, :4, :4] = 1.0
weights = refmod.motion_weights(arm, 1.0)
check("...and a moving corner outweighs the still rest",
      (list(weights.shape), float(weights[0, 0, 1, 0, 0]) > float(weights[0, 0, 1, 7, 7])),
      ([1, 1, 3, 8, 8], True))
check("strength 0 is the plain fit", refmod.motion_weights(arm, 0), None)
torch.manual_seed(0)
noisy = arm + torch.randn_like(arm) * 0.1
weighted = refmod.compress(noisy, 4, steps=30, motion=4.0)
check("a weighted fit lands somewhere else than the plain one",
      torch.allclose(weighted, refmod.compress(noisy, 4, steps=30), atol=1e-4), False)

# ---- bundles ----------------------------------------------------------------------
# Two of ours out as one version-5 bundle, the way the sibling pack writes one,
# and back in through the import, split into the members it holds.

bundled = os.path.join(tempfile.mkdtemp(prefix="mmc-bundle-"), "anna.safetensors")
refmod.write_bundle([refmod.resolve("refmod:cast/anna"), refmod.resolve("refmod:walk")], "anna", bundled)
members = refmod.bundle_members(bundled)
check("a bundle holds both, in order, as version-4 members",
      [(m["kind"], m["_format_version"], m["latent_t"]) for _, m in members],
      [("image", 4, 1), ("video", 4, 3)])
try:
    refmod.header(bundled)
    whole = ""
except refmod.RefModError as exc:
    whole = str(exc)
check("...which this pack refuses to cite whole", "bundle of 2" in whole, True)
upload = os.path.join(ROOT, ".upload.tmp")
import shutil  # noqa: E402
shutil.copy(bundled, upload)
first, meta = refmod.adopt(upload, "imported/anna")
check("imported, it is split into its members", [os.path.relpath(p, ROOT) for p in meta["parts"]],
      [os.path.join("imported", "anna-1.safetensors"), os.path.join("imported", "anna-2.safetensors")])
check("...each the latent it was",
      (torch.allclose(refmod.load_latent(meta["parts"][0]), refmod.load_latent(refmod.resolve("refmod:cast/anna"))),
       refmod.header(meta["parts"][1])["latent_t"]), (True, 3))
check("...and the upload is consumed", os.path.exists(upload), False)
shutil.copy(bundled, upload)
try:
    refmod.adopt(upload, "imported/anna")
    again = ""
except refmod.RefModError as exc:
    again = str(exc)
check("importing it twice refuses rather than writes over", "already there" in again, True)
try:
    refmod.write_bundle([refmod.resolve("refmod:cast/anna")] * 1 + [bundled], "x",
                        os.path.join(tempfile.mkdtemp(), "x.safetensors"))
    nested = ""
except refmod.RefModError as exc:
    nested = str(exc)
check("a bundle is not bundled again", bool(nested), True)

if remake_routes is not None:
    # ---- the frames a clip is read as -------------------------------------------
    check("the run is the longest 17k+5 that fits",
          [remake_routes.causal_count(n) for n in (4, 5, 21, 22, 30, 56, 60)], [0, 5, 5, 22, 22, 56, 56])
    clip_frames = torch.arange(40, dtype=torch.float32).view(40, 1, 1, 1).expand(40, 2, 2, 3).clone()
    media.load_video = lambda filename, max_seconds=None, crop=None: (clip_frames, None)
    picked = remake_routes._frames("walk.mp4", 30)
    check("a count off the grid is snapped before the picks, which span first frame to last",
          (picked.shape[0], float(picked[0, 0, 0, 0]), float(picked[-1, 0, 0, 0])), (22, 0.0, 39.0))
    short = remake_routes._frames("walk.mp4", 56)
    check("a clip shorter than the count gives its longest whole run, end included",
          (short.shape[0], float(short[-1, 0, 0, 0])), (39, 39.0))
    motion_run = remake_routes._frames("walk.mp4", 22, capture="motion")
    check("a motion capture picks one more and keeps a whole run", motion_run.shape[0], 22)

    # ---- kept for its motion -----------------------------------------------------
    class ClipVAE(FakeVAE):
        """An encode with something in it: each latent frame is its first
        source frame's level, so the run keeps its movement."""
        def encode(self, pixels):
            self.encoded += 1
            frames, height, width = pixels.shape[0], pixels.shape[1], pixels.shape[2]
            t = 1 + (frames - 1) // 4
            levels = pixels[::4, 0, 0, 0][:t].float()
            return levels.view(1, 1, t, 1, 1).expand(1, 24, t, height // 16, width // 16).clone()

    remake_routes._vae = lambda name, space=None: ClipVAE()
    clip_frames = torch.rand(120, 432, 768, 3)
    media.load_video = lambda filename, max_seconds=None, crop=None: (clip_frames, None)
    made = remake_routes._run_job({"name": "mia", "subfolder": "cast", "sources": ["walk.mp4"],
                                   "mode": "clip", "use": "motion", "steps": 2, "vae": "x"})
    motion_meta = refmod.header(refmod.resolve(made["mods"][0]["path"]))
    check("a clip kept for its motion is fifty-six frames on a 16-grid, compressed",
          (motion_meta["mode"], motion_meta["latent_w"], motion_meta["concept_type"],
           "56 frames" in motion_meta["tags"], "motion" in motion_meta["tags"]),
          ("training", 16, "pose_motion", True, True))
    look = remake_routes._run_job({"name": "mia-look", "subfolder": "cast", "sources": ["walk.mp4"],
                                   "mode": "clip", "vae": "x"})
    look_meta = refmod.header(refmod.resolve(look["mods"][0]["path"]))
    check("one kept for its look is the full encode of twenty-two",
          (look_meta["mode"], look_meta["latent_w"], "22 frames" in look_meta["tags"]),
          ("encode", 48, True))
    squeezed = remake_routes._run_job({"name": "mia-small", "subfolder": "cast", "sources": ["walk.mp4"],
                                       "mode": "clip", "compressed": True, "steps": 0, "vae": "x"})
    check("...and compressed for its look, a 32-grid",
          refmod.header(refmod.resolve(squeezed["mods"][0]["path"]))["latent_w"], 32)
    clip_frames = torch.full((120, 432, 768, 3), 0.5)
    frozen = remake_routes._run_job({"name": "mia-still", "subfolder": "cast", "sources": ["walk.mp4"],
                                     "mode": "clip", "vae": "x"})
    check("a clip that never moves is thinned to one frame",
          refmod.header(refmod.resolve(frozen["mods"][0]["path"]))["latent_t"], 1)
    kept_all = remake_routes._run_job({"name": "mia-all", "subfolder": "cast", "sources": ["walk.mp4"],
                                       "mode": "clip", "thin": 0, "vae": "x"})
    check("...unless thinning is off",
          refmod.header(refmod.resolve(kept_all["mods"][0]["path"]))["latent_t"], 6)

passed("all RefMod encode tests passed")
