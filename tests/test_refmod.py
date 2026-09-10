"""The RefMod reader: header-only, standalone, and honest about what it refuses.

`creator/refmod.py` is the one place the Creator knows a RefMod is a file
format rather than a media file, and it has to answer four questions without
torch, ComfyUI or the sibling pack: is this a mod, what kind is it, how big is
it in DiT tokens, and has the file changed since the last decode. The suite
builds those files by hand — a length-prefixed JSON header and zeroed data — so
it tests the reader's own contract rather than the sibling pack's writer.

    python3 tests/test_refmod.py

No torch: `load_latent` is the one function that needs it, and it is the one
check that bows out when torch is absent.
"""

import json
import os
import struct
import sys
import tempfile

import harness
import layout
from harness import check

ROOT = tempfile.mkdtemp(prefix="mmc-refmods-")
os.environ["CONTINUITY_REFMODS"] = ROOT

refmod = layout.load("refmod").refmod


def _write(path, meta, shape=(1, 24, 4, 16, 16), tensor="latent"):
    """A minimal valid safetensors file: header, then zeroed tensor bytes."""
    numel = 1
    for dim in shape:
        numel *= dim
    header = {
        tensor: {"dtype": "F16", "shape": list(shape), "data_offsets": [0, numel * 2]},
        "__metadata__": {refmod.META_KEY: json.dumps(meta)},
    }
    raw = json.dumps(header).encode("utf-8")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", len(raw)))
        handle.write(raw)
        handle.write(b"\x00" * (numel * 2))


def _mod(name, **over):
    meta = {"name": name, "kind": "video", "latent_h": 16, "latent_w": 16,
            "latent_t": 4, "mode": "training", "concept_type": "generic",
            "description": "", "_format_version": 4}
    meta.update(over)
    return meta


# ---- names ------------------------------------------------------------------

check("normalize strips extension", refmod.normalize("a/b.safetensors"), "a/b")
check("normalize windows separators", refmod.normalize("a\\b"), "a/b")
check("normalize strips leading slash", refmod.normalize("/a"), "a")
for bad in ("", "..", "a/../b", "a//b", "."):
    try:
        refmod.normalize(bad)
        harness.check(f"normalize refuses {bad!r}", "accepted", "refused")
    except refmod.RefModError:
        pass


# ---- listing ----------------------------------------------------------------

os.environ["CONTINUITY_REFMODS"] = ROOT
_write(os.path.join(ROOT, "alpha.safetensors"), _mod("alpha"))
_write(os.path.join(ROOT, "celebs", "person.safetensors"), _mod("person"))
with open(os.path.join(ROOT, "notes.txt"), "w") as _notes:
    _notes.write("not media\n")
# A safetensors file with no RefMod header is not one of ours.
with open(os.path.join(ROOT, "foreign.safetensors"), "wb") as _h:
    _raw = json.dumps({"latent": {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]}}).encode()
    _h.write(struct.pack("<Q", len(_raw)) + _raw + b"\x00\x00")
# A hidden tree nobody lists.
_write(os.path.join(ROOT, "__pycache__", "junk.safetensors"), _mod("junk"))

harness.check("list_names finds nested mods, skips foreign and hidden",
              refmod.list_names(), ["alpha", "celebs/person"])


# ---- metadata ---------------------------------------------------------------

harness.check("find resolves a nested name",
              os.path.basename(refmod.find("celebs/person")), "person")
harness.check("find missing is None", refmod.find("nope"), None)

_image = refmod.load_meta("alpha")
harness.check("a T=4 mod reads as video", _image.kind, "video")
harness.check("video tokens = T*H/2*W/2", _image.tokens, 4 * 8 * 8)
harness.check("path is extensionless", _image.path.endswith("alpha"), True)

_write(os.path.join(ROOT, "flat.safetensors"),
       _mod("flat", kind="image", latent_t=1, latent_h=32, latent_w=32),
       shape=(1, 24, 1, 32, 32))
harness.check("a T=1 mod reads as image", refmod.load_meta("flat").kind, "image")

_write(os.path.join(ROOT, "who.safetensors"),
       _mod("who", concept_type="identity", description="brucelee"))
_who = refmod.load_meta("who")
harness.check("concept_type seeds takes (identity)", _who.takes, "person")
harness.check("description survives", _who.description, "brucelee")

for concept, takes in (("pose_motion", "motion"), ("background", "scene"),
                       ("style", "style"), ("clothing", "object"),
                       ("generic", "full"), ("unheard_of", "")):
    _write(os.path.join(ROOT, "c.safetensors"), _mod("c", concept_type=concept))
    harness.check(f"concept {concept} -> {takes!r}", refmod.load_meta("c").takes, takes)

# A v2 file with no `kind` still reads its rank.
_write(os.path.join(ROOT, "legacy.safetensors"),
       {"name": "legacy", "_format_version": 2}, shape=(1, 24, 4, 16, 16))
harness.check("v2 without kind reads video from rank",
              refmod.load_meta("legacy").kind, "video")

# A version we do not know is refused, not guessed at.
_write(os.path.join(ROOT, "future.safetensors"), _mod("future", _format_version=99))
try:
    refmod.load_meta("future")
    harness.check("future version refused", "accepted", "refused")
except refmod.RefModError:
    pass


# ---- stamp ------------------------------------------------------------------

_first = refmod.stamp("alpha")
harness.check("stamp names the file", os.path.basename(_first["path"]), "alpha.safetensors")
harness.check("stamp has size", _first["size"] > 0, True)
os.utime(os.path.join(ROOT, "alpha.safetensors"), (1, 1))
harness.check("stamp moves when the file does",
              refmod.stamp("alpha")["mtime"] != _first["mtime"], True)
harness.check("stamp missing is None", refmod.stamp("nope"), None)


# ---- the lazy tensor read ---------------------------------------------------

try:
    import torch  # noqa: F401
except Exception:  # noqa: BLE001
    print("(torch absent: load_latent not exercised)")
else:
    latent = refmod.load_latent("alpha")
    harness.check("load_latent returns the stored shape", tuple(latent.shape),
                  (1, 24, 4, 16, 16))

    # The writer and the reader are held to each other: save, then read back the
    # header and the tensor through the same functions the picker and encoder
    # use.
    import torch  # noqa: F401
    made = torch.zeros(1, 24, 4, 16, 16, dtype=torch.float16)
    written = refmod.save_mod("roundtrip", made, concept_type="identity",
                              description="a saved reference")
    harness.check("save_mod writes under the root", written.endswith("roundtrip"), True)
    back = refmod.load_meta("roundtrip")
    harness.check("round-trip kind", back.kind, "video")
    harness.check("round-trip seeds takes", back.takes, "person")
    harness.check("round-trip description", back.description, "a saved reference")
    harness.check("round-trip tokens", back.tokens, 4 * 8 * 8)
    harness.check("round-trip latent", tuple(refmod.load_latent("roundtrip").shape),
                  (1, 24, 4, 16, 16))

    one = torch.zeros(1, 24, 1, 32, 32, dtype=torch.float16)
    refmod.save_mod("single", one)
    harness.check("a T=1 save reads back as image",
                  refmod.load_meta("single").kind, "image")

    # The preview the picker draws without a VAE: written into the header at
    # save time, read back with no tensor touched.
    png = b"\x89PNG\r\n\x1a\npreview-bytes"
    refmod.save_mod("withpreview", made, preview=png)
    harness.check("the stored preview round-trips",
                  refmod.read_preview("withpreview"), png)
    harness.check("a mod without one reads as None",
                  refmod.read_preview("single"), None)


# ---- the picker's listing ---------------------------------------------------
#
# `_scan_refmods` is lifted out of `server_routes.py` the way `test_assets.py`
# lifts `_scan`: the function is the walk, and importing the module would drag
# in aiohttp and a live PromptServer to test a header read.

import ast  # noqa: E402 - after the module under test, matching the file's shape
import pathlib

_source = pathlib.Path(layout.py("server_routes")).read_text(encoding="utf-8")
_picked = [node for node in ast.parse(_source).body
           if isinstance(node, ast.FunctionDef) and node.name == "_scan_refmods"]
assert _picked, "server_routes no longer defines _scan_refmods"
_namespace = {"os": os, "refmod": refmod}
exec(compile(ast.Module(body=_picked, type_ignores=[]), "server_routes.py", "exec"),
     _namespace)
_rows = _namespace["_scan_refmods"]()["assets"]
_listed = {row["path"]: row for row in _rows}
harness.check("the listing finds the visual mods",
              "alpha" in _listed and "celebs/person" in _listed, True)
harness.check("...and skips a version it cannot read", "future" in _listed, False)
harness.check("a row carries the kind", _listed["alpha"]["kind"], "video")
harness.check("a row is flagged as a mod", _listed["alpha"]["mod"], True)
harness.check("a row reports its token cost", _listed["alpha"]["tokens"], 4 * 8 * 8)
harness.check("a nested name keeps its subfolder",
              _listed["celebs/person"]["subfolder"], "celebs")

harness.passed("all refmod tests passed")
