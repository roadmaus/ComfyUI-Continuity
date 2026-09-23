#!/usr/bin/env python3
"""Vendor three.js into the pack, for the image-to-3D tool's stage.

Upstream — <https://github.com/mrdoob/three.js>, MIT — is fetched from the npm
package on jsDelivr at a pinned version. Only what the stage uses is taken: the
minified module build, the orbit controls, the glTF loader and the one utility
module it imports, and the room environment the stage is lit by. Everything
lands in `web/creator/vendor/three/` with upstream's licence beside it.

**Why vendored rather than borrowed.** ComfyUI's frontend bundles three.js for
its own 3D nodes, but under hashed chunk names that change with every frontend
release, and nothing about it is published for an extension to import. Blockout
could write its own rasterizer because boxes on a floor are arithmetic; a
textured PBR mesh with baked normal and occlusion maps is not, and a hand-rolled
glTF reader would be a second, worse copy of this one.

**Imports are re-rooted, not patched.** The example modules import the bare
specifier `three`, which a browser without an import map cannot resolve, and
ComfyUI's page is not ours to add one to. So every `from 'three'` becomes a
relative path to the module build as the file is copied — the same mechanical
rewrite `vendor_vdnh3.py` does to Python imports, for the same reason: a hunk in
a patch file would break on every upstream change near an import line.

Re-syncing, at a new version:

    python3 tools/vendor_three.py 0.160.0
"""

import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "web", "creator", "vendor", "three")
VERSION = "0.160.0"

# upstream path in the npm package -> path under DEST
FILES = {
    "build/three.module.min.js": "three.module.min.js",
    "examples/jsm/controls/OrbitControls.js": "OrbitControls.js",
    "examples/jsm/loaders/GLTFLoader.js": "GLTFLoader.js",
    "examples/jsm/utils/BufferGeometryUtils.js": "BufferGeometryUtils.js",
    "examples/jsm/environments/RoomEnvironment.js": "RoomEnvironment.js",
    "LICENSE": "LICENSE",
}

BARE = re.compile(r"""(from\s+)(['"])three\2""")
UPWARD = re.compile(r"""from\s+['"]\.\./""")
SIBLING = re.compile(r"""(from\s+)(['"])\.\./utils/BufferGeometryUtils\.js\2""")


def fetch(version, path):
    url = f"https://cdn.jsdelivr.net/npm/three@{version}/{path}"
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")


def main(version=VERSION):
    os.makedirs(DEST, exist_ok=True)
    for source, target in FILES.items():
        text = fetch(version, source)
        if target.endswith(".js") and target != "three.module.min.js":
            text = BARE.sub(r"\1\2./three.module.min.js\2", text)
            text = SIBLING.sub(r"\1\2./BufferGeometryUtils.js\2", text)
            if BARE.search(text) or UPWARD.search(text):
                sys.exit(f"{source}: an import this script does not know how to re-root")
        if target.endswith(".js"):
            text = f"// three.js r{version.split('.')[1]} ({version}), vendored by tools/vendor_three.py. MIT, see LICENSE.\n" + text
        with open(os.path.join(DEST, target), "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"  {target}  {len(text) // 1024} KB")
    print(f"three.js {version} -> {os.path.relpath(DEST, ROOT)}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
