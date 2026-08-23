"""`web/creator/manifest.js` really carries the catalog the server serves.

Phase 5 moves the frontend's family knowledge out of `state.js` and into the
`/minimax_creator/families` catalog, which makes `manifest.js` the one file
everything else reads it from. This holds the loading contract from both
directions the module can be reached:

- injected, the way every direct mirror suite reaches it (`layout.run` sets
  `globalThis.__MMC_FAMILIES` from the same `catalog()` the route serves);
- fetched, the way the browser reaches it — `layout.pack`'s stub serves the
  catalog through `api.fetchApi`, so the packed import takes the real path.

Either way, what comes out the far side must be the catalog `families/
manifest.py` built, keyed and ordered the way the registry says.

    python3 tests/test_manifest_mirror.py

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

from harness import FAILURES, check, passed

_pkg = layout.load("registry", "manifest")
registry = _pkg.registry
catalog = _pkg.manifest.catalog()

SCRIPT = """
const m = await import(process.argv[1]);
console.log(JSON.stringify({
  ids: m.FAMILIES.map((f) => f.id),
  video: m.VIDEO?.id ?? null,
  arches: m.STILL_ARCHES,
  defaultArch: m.DEFAULT_STILL_ARCH,
  byId: m.family("h3").label,
  byArch: m.stillFamily("minimax").id,
}));
"""

MANIFEST = layout.js("manifest.js")

# ---- injected, the direct-suite path ----------------------------------------

reflected = layout.run(SCRIPT, MANIFEST)
check("families, in registry order", reflected["ids"], list(registry.FAMILIES))
check("the video family", reflected["video"],
      next(f for f in registry.FAMILIES if "video" in registry.PRODUCES[f]))
check("still arches", reflected["arches"], dict(registry.STILL_ARCHES))
check("default still arch", reflected["defaultArch"], registry.DEFAULT_STILL_ARCH)
check("family() resolves by id", reflected["byId"],
      catalog["families"][0]["label"])
check("stillFamily() follows the arch alias", reflected["byArch"], "h3")

# ---- fetched, the browser path ----------------------------------------------

with layout.pack(skip=("atlas",)) as target:
    fetched = layout.in_pack(
        "const m = await import('./web/creator/manifest.js');\n"
        "console.log(JSON.stringify({ ids: m.FAMILIES.map((f) => f.id) }));",
        target)
check("the packed import fetches the same catalog", fetched["ids"],
      list(registry.FAMILIES))

# ---- an unknown family is a bug, not a state --------------------------------

thrown = layout.run("""
const m = await import(process.argv[1]);
let refused = false;
try { m.family("no-such-family"); } catch { refused = true; }
console.log(JSON.stringify({ refused }));
""", MANIFEST)
check("family() refuses an unknown id", thrown["refused"], True)

passed("manifest.js carries the served catalog on both load paths")
