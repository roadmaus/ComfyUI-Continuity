"""`state.js` and `compile.py` write a saved RefMod the same way, round-trip.

The bug this exists for: `state.js`'s `serializeAssets` rebuilt every asset from
a fixed field list and dropped `mod`, while adding `track` for any video. So a
mod attached in the browser was saved as an ordinary video file — the face drew
a picture, the queue opened a mod name as media, and the render died with "not
in the input folder". `state.serializeState` and `compile._asset_dict` are the
two writers of one shape, and `_parse_assets` is the one reader; this holds all
three to it.

    python3 tests/test_refmod_mirror.py

Skips itself if node is not installed.
"""

import json
import os
import struct
import tempfile

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")
pkg = layout.load("refmod", "compile")
compiler, refmod = pkg.compile, pkg.refmod

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


ROOT = tempfile.mkdtemp(prefix="mmc-refmod-mirror-")
os.environ["CONTINUITY_REFMODS"] = ROOT


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
    with open(full, "wb") as handle:
        handle.write(struct.pack("<Q", len(raw)) + raw + b"\x00" * (numel * 2))


_write("person", {"name": "person", "kind": "video", "latent_h": 16, "latent_w": 16,
                  "latent_t": 4, "concept_type": "identity", "_format_version": 4})

# What the picker hands the editor when a RefMod is attached: the stored kind,
# the mod's name as the filename, and the flag.
ASSET = {"handle": "vid-1", "kind": "video", "role": "reference",
         "filename": "person", "mod": True}

SCRIPT = """
const s = await import(process.argv[1]);
const asset = JSON.parse(process.argv[2]);
const state = { version: 2, prompt: "", aspect: "16:9", short_edge: 768, models: {},
                assets: [asset], loras: [], duration_s: 6 };
// The cast's face source: a still first, then a saved RefMod (which has a
// thumbnail even when it is a clip), and nothing for a plain clip or words.
const assets = [
  { handle: "vid-1", kind: "video", filename: "person", mod: true },
  { handle: "img-1", kind: "image", filename: "a.png" },
  { handle: "vid-2", kind: "video", filename: "b.mp4" },
];
console.log(JSON.stringify({
  asset: JSON.parse(s.serializeState(state)).assets[0],
  face: {
    modOnly: s.castFaceSource({ from: ["vid-1"] }, assets)?.handle ?? null,
    stillWins: s.castFaceSource({ from: ["vid-1", "img-1"] }, assets)?.handle ?? null,
    plainClip: s.castFaceSource({ from: ["vid-2"] }, assets)?.handle ?? null,
    nothing: s.castFaceSource({ from: [] }, assets),
  },
}));
"""

reflected = layout.run(SCRIPT, MIRROR, ASSET)
asset = reflected["asset"]
face = reflected["face"]

# ---- the frontend writer ----------------------------------------------------

check("serializeState keeps the mod flag", asset.get("mod"), True)
check("...and writes no track", "track" in asset, False)
check("...and writes no ref_size", "ref_size" in asset, False)

# ---- the backend reads it ---------------------------------------------------

parsed = compiler._parse_assets([asset])[0]
check("_parse_assets reads it as a mod", parsed.mod, "person")
check("...keeping the declared kind", parsed.kind, "video")
resolved = compiler._resolve_refmods([parsed])[0]
check("resolve keeps it a video", resolved.kind, "video")
check("resolve seeds takes from concept_type", resolved.takes, "person")

# ---- and the backend writer agrees with the frontend writer -----------------

back = compiler._asset_dict(parsed)
check("_asset_dict keeps the mod flag", back.get("mod"), True)
check("_asset_dict writes no track", "track" in back, False)
check("the two writers produce the same object", asset, back)

# ---- and a RefMod can supply a cast member's face ---------------------------

check("a mod supplies a cast face when there is no still", face["modOnly"], "vid-1")
check("a still beats a mod for the face", face["stillWins"], "img-1")
check("a plain clip supplies no face", face["plainClip"], None)
check("words alone supply no face", face["nothing"], None)

passed("state.js and compile.py agree about a saved RefMod")
