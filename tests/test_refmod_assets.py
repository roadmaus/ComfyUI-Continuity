"""A RefMod asset through the parser, the resolver and the plan walk.

The invariant the Creator cares about is that a label's ordinal in the prose and
the tensor's place in the payload come from one walk. A RefMod must therefore
look, to `plan_references` and everything after it, exactly like the file it
replaces: same kind, same `takes`, same `<Picture N>` / `<Video N>`. This suite
holds the two seams that make that true — `_parse_assets` keeps the mod as its
own kind long enough for `_resolve_refmods` to read the header, and the resolved
asset then walks and cites like any other.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_refmod_assets.py

Loads `compile`, so it needs the environment `test_compile.py` needs (numpy);
the header reader itself is covered torch-free by `test_refmod.py`.
"""

import json
import os
import struct
import sys
import tempfile

import harness
import layout

ROOT = tempfile.mkdtemp(prefix="mmc-refmod-assets-")
os.environ["CONTINUITY_REFMODS"] = ROOT

try:
    pkg = layout.load("refmod", "compile")
except Exception as exc:  # noqa: BLE001
    print(f"skipped: package not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

refmod, compiler = pkg.refmod, pkg.compile
check = harness.check


def _write(name, meta, shape=(1, 24, 4, 16, 16)):
    numel = 1
    for dim in shape:
        numel *= dim
    header = {
        "latent": {"dtype": "F16", "shape": list(shape), "data_offsets": [0, numel * 2]},
        "__metadata__": {refmod.META_KEY: json.dumps(meta)},
    }
    raw = json.dumps(header).encode("utf-8")
    full = os.path.join(ROOT, name + ".safetensors")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as handle:
        handle.write(struct.pack("<Q", len(raw)) + raw + b"\x00" * (numel * 2))


# One of each shape the resolver has to place: an identity video, a background
# still, an audio mod, and a future version.
_write("person", {"name": "person", "kind": "video", "latent_h": 16, "latent_w": 16,
                  "latent_t": 4, "concept_type": "identity", "_format_version": 4})
_write("still", {"name": "still", "kind": "image", "latent_h": 32, "latent_w": 32,
                 "latent_t": 1, "concept_type": "background", "_format_version": 4},
       shape=(1, 24, 1, 32, 32))
_write("sound", {"name": "sound", "kind": "audio", "latent_t": 40,
                 "concept_type": "voice", "_format_version": 4},
       shape=(1, 32, 2, 40))
_write("future", {"name": "future", "kind": "video", "latent_h": 16, "latent_w": 16,
                  "latent_t": 4, "_format_version": 99})


def _asset(handle, name, **over):
    item = {"handle": handle, "kind": "refmod", "role": "reference", "filename": name}
    item.update(over)
    return compiler._parse_assets([item])[0]


# ---- parse: a mod keeps its own kind until the header is read -----------------

_parsed = _asset("mod-1", "person")
check("parse carries kind=refmod", _parsed.kind, "refmod")
check("parse records the mod name", _parsed.mod, "person")
check("parse leaves takes unset", _parsed.takes, "")

# ---- resolve: the header decides kind and seeds takes -------------------------

_resolved = compiler._resolve_refmods([_parsed])[0]
check("identity video resolves to video", _resolved.kind, "video")
check("concept_type seeds takes", _resolved.takes, "person")
check("mod name is kept as the identity", _resolved.filename, "person")

_plan = compiler.plan_references([], [_resolved], [])
check("a resolved mod plans as a video", _plan[0]["op"], "video")
check("...and cites as <Video 1>", _plan[0]["label"], "<Video 1>")

_still = compiler._resolve_refmods([_asset("pic-1", "still")])[0]
check("image mod resolves to image", _still.kind, "image")
check("background seeds takes=scene", _still.takes, "scene")
_plan = compiler.plan_references([_still], [], [])
check("an image mod plans as a picture", _plan[0]["op"], "image")
check("...and cites as <Picture 1>", _plan[0]["label"], "<Picture 1>")

# An explicit take narrows the seeded one; a video-only take is refused on a
# still, where it means nothing.
check("explicit takes wins over the seed",
      compiler._resolve_refmods([_asset("mod-2", "person", takes="motion")])[0].takes,
      "motion")
try:
    compiler._resolve_refmods([_asset("mod-3", "still", takes="camera")])
    check("camera refused on an image mod", "accepted", "refused")
except compiler.CompileError:
    pass
check("camera is allowed on a video mod",
      compiler._resolve_refmods([_asset("mod-4", "person", takes="camera")])[0].takes,
      "camera")

# ---- the refusals ------------------------------------------------------------

def _refuses(label, build):
    try:
        build()
    except compiler.CompileError:
        return
    harness.check(label, "accepted", "refused")


_refuses("a missing RefMod is a compile error",
         lambda: compiler._resolve_refmods([_asset("mod-5", "ghost")]))
_refuses("an audio RefMod is refused for now",
         lambda: compiler._resolve_refmods([_asset("mod-6", "sound")]))
_refuses("a future format version is refused",
         lambda: compiler._resolve_refmods([_asset("mod-7", "future")]))
_refuses("a RefMod cannot be a keyframe",
         lambda: compiler._parse_assets([
             {"handle": "f-1", "kind": "refmod", "role": "first_frame", "filename": "still"}]))
_refuses("a RefMod cannot carry a trim",
         lambda: compiler._parse_assets([
             {"handle": "mod-8", "kind": "refmod", "role": "reference",
              "filename": "person", "trim": {"start": 0, "end": 1}}]))
_refuses("an unknown takes is refused at parse",
         lambda: compiler._parse_assets([
             {"handle": "mod-9", "kind": "refmod", "role": "reference",
              "filename": "person", "takes": "nonsense"}]))

# ---- the merge pass: serialise back, rename, and parse again ----------------
#
# A timeline merge rebuilds a merged request out of parsed assets and re-parses
# it, so `_asset_dict` has to keep a mod a mod, and the rename table has to have
# a prefix for the kind. Both were gaps this suite would have missed.
_blob = compiler._asset_dict(_parsed)
check("asset_dict keeps kind=refmod", _blob["kind"], "refmod")
check("asset_dict keeps the mod name", _blob["filename"], "person")
check("a refmod round-trips through the blob",
      compiler._parse_assets([_blob])[0].mod, "person")
check("the merge has a rename prefix for refmod",
      compiler._HANDLE_PREFIX.get("refmod"), "mod")

# ---- the picker's form: kind image/video plus a mod flag ---------------------
_flagged = compiler._parse_assets([{
    "handle": "vid-1", "kind": "video", "role": "reference",
    "filename": "person", "mod": True}])[0]
check("the mod flag keeps the declared kind", _flagged.kind, "video")
check("the mod flag records the name", _flagged.mod, "person")
check("a mod-flagged video resolves to video",
      compiler._resolve_refmods([_flagged])[0].kind, "video")
_blob2 = compiler._asset_dict(_flagged)
check("asset_dict writes the mod flag", _blob2.get("mod"), True)
check("a mod-flagged asset round-trips",
      compiler._parse_assets([_blob2])[0].mod, "person")
_refuses("a kind/header mismatch is refused",
         lambda: compiler._resolve_refmods(compiler._parse_assets([{
             "handle": "img-9", "kind": "image", "role": "reference",
             "filename": "person", "mod": True}])))

harness.passed("all refmod asset tests passed")
