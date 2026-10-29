"""The vendored Pose Studio viewer is whole, stays off the page load, and offers the render contract.

    python3 tests/test_posestudio_vendor.py

`web/creator/vendor/posestudio/` is VNCCS Utils' viewer copied at a pin by
`tools/vendor_posestudio.py`. Four things are pinned here. That the copy is
whole: the stamp, the licences, every file the script names. That nothing in
it is a `.js` file, because ComfyUI imports every `.js` under the web
directory on every page load and the morph worker would take over
`window.onmessage` there. That nothing in it reaches the network: no import
from a remote host, no relative file that is not in the folder, and the one
local fix (`// MMC:`) still in place. And the part of `PoseViewerCore` the forge's render job calls,
which is what a re-sync can break without any of the above noticing.

With node installed, the modules are also loaded for real: three is r160, the
FBX loader comes up on that same three, and the mannequin decodes and solves.
"""

import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout
from harness import FAILURES, check, died, passed

passed("the vendored Pose Studio viewer is whole, local, and offers the render contract")

HERE = layout.js("vendor", "posestudio")
SCRIPT = os.path.join(layout.ROOT, "tools", "vendor_posestudio.py")
PATCH = os.path.join(layout.ROOT, "tools", "posestudio.patch")

# ---- the copy is whole ----------------------------------------------------------

with open(os.path.join(HERE, "README.md"), encoding="utf-8") as handle:
    readme = handle.read()
check("the README is stamped with a revision",
      bool(re.search(r"revision `[0-9a-f]{7,}` \(\d{4}-\d\d-\d\d\)", readme)), True)

with open(SCRIPT, encoding="utf-8") as handle:
    script = handle.read()
named = re.findall(r'^\s+"([\w./-]+\.(?:m?js|gz|md|png))",', script, re.M)
named += re.findall(r'"examples/jsm/[\w/.]+": "([\w.]+)"', script)
check("the script names what it copies", len(named) >= 20, True)
for name in named:
    target = name[:-3] + ".mjs" if name.endswith(".js") else name
    check(f"{target} is there", os.path.isfile(os.path.join(HERE, target)), True)
for name in ("LICENSE", "assets/pose_studio_makehuman.v2.CC0-1.0.md",
             "assets/pose_studio_makehuman.v2.LICENSE.md"):
    check(f"{name} travels with the copy", os.path.isfile(os.path.join(HERE, name)), True)

# ---- nothing loads on the page by itself ----------------------------------------

stray = [os.path.relpath(os.path.join(d, f), HERE)
         for d, _, files in os.walk(HERE) for f in files if f.endswith(".js")]
check("no .js file for ComfyUI to auto-import", stray, [])

# ---- nothing leaves the folder ---------------------------------------------------

modules = {}
for name in sorted(os.listdir(HERE)):
    if name.endswith(".mjs"):
        with open(os.path.join(HERE, name), encoding="utf-8") as handle:
            modules[name] = handle.read()

remote = [name for name, text in modules.items()
          if re.search(r"""import\(\s*[`'"]https?:|from\s+['"]https?:""", text)]
check("no module imports from a remote host", remote, [])

reference = re.compile(r"""(?:['"`]\.{0,2}/|\$\{EXTENSION_URL\})([\w./-]+\.(?:m?js|gz|png))\b""")
dangling = [f"{name} -> {target}" for name, text in modules.items()
            for target in sorted(set(reference.findall(text)))
            if not os.path.isfile(os.path.join(HERE, target))]
check("every relative file a module names is in the folder", dangling, [])

check("the skins the core loads are the three copied",
      sorted(set(re.findall(r"""['"](skin\w*\.png)['"]""", modules["vnccs_pose_studio_core.mjs"]))),
      ["skin.png", "skin_dummy.png", "skin_marks.png"])

if shutil.which("git"):
    applied = subprocess.run(["git", "-C", layout.ROOT, "apply", "--check", "--reverse", PATCH],
                             capture_output=True, text=True)
    check("tools/posestudio.patch is applied to the copy", applied.returncode, 0)
check("the local fix is marked at its site", "// MMC:" in modules["vnccs_mixamo_import.mjs"], True)

# ---- the render contract ---------------------------------------------------------

# The forge builds a viewer offscreen and captures it (spec §7.9). These are
# the members it calls; if a re-sync renames one, the render job breaks in a
# browser tab where no test is looking.
core = modules["vnccs_pose_studio_core.mjs"]
check("PoseViewerCore is exported", bool(re.search(r"^export class PoseViewerCore\b", core, re.M)), True)
check("it is constructed from a canvas and options",
      bool(re.search(r"^\s+constructor\(canvas, options", core, re.M)), True)
for method in ("init", "loadData", "setPose", "getPose", "capture", "setSkinMode", "resize", "dispose"):
    check(f"PoseViewerCore.{method} exists",
          bool(re.search(rf"^    (async )?{method}\(", core, re.M)), True)
check("the morph runtime still exports the mannequin loader and solver",
      all(re.search(rf"^export (async )?function {fn}\b", modules["vnccs_pose_morph_runtime.mjs"], re.M)
          for fn in ("loadMorphPack", "parseMorphPack", "solveMorph")), True)

# ---- loaded for real ---------------------------------------------------------------

if shutil.which("node") is None:
    print("node is not installed: the load checks are skipped")
    sys.exit(0)

PROBE = r"""
import fs from "node:fs";
const t = await import("./three.module.mjs");
const { FBXLoader } = await import("./FBXLoader.mjs");
const mixamo = await import("./vnccs_mixamo_import.mjs");
const r = await import("./vnccs_pose_morph_runtime.mjs");
const gz = fs.readFileSync("assets/pose_studio_makehuman.v2.bin.gz");
const raw = await new Response(new Blob([gz]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
const pack = r.parseMorphPack(raw);
const solved = r.solveMorph(pack, {});
console.log(JSON.stringify({
    revision: t.REVISION,
    fbx: new FBXLoader() instanceof t.Loader,
    mixamo: typeof mixamo.importMixamoFBXAnimation,
    bones: pack.bones.length,
    vertices: solved.vertices.length > 0,
}));
"""
result = subprocess.run(["node", "--input-type=module", "-e", PROBE], cwd=HERE,
                        capture_output=True, text=True)
if result.returncode:
    died(f"the vendored modules do not load under node:\n{result.stderr}")
import json
loaded = json.loads(result.stdout.strip().splitlines()[-1])
check("three is upstream's r160", loaded["revision"], "160")
check("the FBX loader is built on that same three", loaded["fbx"], True)
check("the Mixamo importer loads", loaded["mixamo"], "function")
check("the mannequin has its rig", loaded["bones"] > 40, True)
check("the mannequin solves with default body sliders", loaded["vertices"], True)
