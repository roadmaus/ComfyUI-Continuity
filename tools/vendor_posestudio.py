#!/usr/bin/env python3
"""Vendor VNCCS Pose Studio's viewer into the pack, for the forge's pose stage.

Upstream — <https://github.com/AHEKOT/ComfyUI_VNCCS_Utils>, MIT, the mannequin
CC0 — draws a lit MakeHuman mannequin that its pose LoRAs were trained to read
(spec §3.9). Only the viewer is taken: `PoseViewerCore` and its IK, the
animation timeline, the Mixamo and OpenPose importers, the hand presets, the
character and morph runtime with its worker, their three.js r160 with the two
controls, the mannequin, the three skins and the licences. Not taken:
`PoseStudioWidget` and its node, UniCanvas, the 3D factory, SAM 3D Body, the
model manager — those are upstream's product around the viewer, and the forge
builds its own (§7.9). Everything lands in `web/creator/vendor/posestudio/`.

**Not the pose library.** `PoseLibrary/` is not in the repo: upstream's server
downloads it from the Hugging Face dataset `MIUProject/VNCCS_PoseLibrary_Main`,
which declares no licence. Nothing of it is copied until it does.

**Every module is copied as `.mjs`.** ComfyUI's frontend imports every `.js`
under an extension's web directory on every page load. As `.js`, the morph
worker's top-level `self.onmessage = …` would run on the page itself and take
over `window.onmessage`, and three, the core and the importers (about 2 MB)
would be parsed for every user whether the forge is opened or not. As `.mjs`
they load only when the pose stage imports them. The file names inside the
copied text are rewritten to match as the files are copied — a mechanical
rename, the way `vendor_three.py` re-roots imports, and never a patch hunk.

**FBXLoader comes from npm, at upstream's three revision.** Upstream imports
three and `FBXLoader` from esm.sh at run time, a second copy of three from a
third-party host. The loader and the three modules it imports (`fflate`,
`NURBSCurve`, `NURBSUtils`) are fetched here from the three@0.160.0 npm
package on jsDelivr, re-rooted onto upstream's own `three.module.mjs`, and the
Mixamo importer is patched to load them from beside it. Their three stays
r160 and theirs: the lift stage's 0.170 is a different module instance, which
is fine because no three object crosses between the two (§7.9).

**Local deltas are re-applied, not re-invented.** Each is marked `// MMC:` at
its site and held as `tools/posestudio.patch`, applied after the copy and the
rename. A hunk that no longer applies stops the script: upstream has changed
the code a fix sits on, and somebody has to look.

    python3 tools/vendor_posestudio.py ~/src/ComfyUI_VNCCS_Utils
    python3 tools/vendor_posestudio.py --save    # local edits -> the patch
    python3 tests/test_posestudio_vendor.py

The revision is stamped into the copy's `README.md`. After a re-sync, check
the render contract the test pins (`PoseViewerCore`'s constructor, `init`,
`loadData`, `setPose`, `capture`) against the new core before trusting it.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "web", "creator", "vendor", "posestudio")
PATCH = os.path.join(ROOT, "tools", "posestudio.patch")
README = os.path.join(DEST, "README.md")

UPSTREAM = "AHEKOT/ComfyUI_VNCCS_Utils"
THREE = "0.160.0"  # upstream's three.module.js revision; FBXLoader must match it

# Upstream path under the clone's web/ -> path under DEST. `.js` modules
# become `.mjs` (see the docstring); everything else keeps its name.
MODULES = (
    "vnccs_pose_studio_core.js",
    "vnccs_pose_animation.mjs",
    "vnccs_custom_select.mjs",  # the animation module imports it
    "vnccs_mixamo_import.js",
    "vnccs_openpose_import.js",
    "vnccs_hand_presets.js",
    "vnccs_pose_characters.mjs",
    "vnccs_pose_morph_runtime.mjs",
    "vnccs_pose_morph_worker.js",
    "three.module.js",
    "OrbitControls.js",
    "TransformControls.js",
)
ASSETS = (
    "assets/pose_studio_makehuman.v2.bin.gz",
    "assets/pose_studio_makehuman.v2.CC0-1.0.md",
    "assets/pose_studio_makehuman.v2.LICENSE.md",
    "textures/skin.png",
    "textures/skin_marks.png",
    "textures/skin_dummy.png",
)

# Path in the three npm package -> name under DEST.
NPM = {
    "examples/jsm/loaders/FBXLoader.js": "FBXLoader.mjs",
    "examples/jsm/libs/fflate.module.js": "fflate.module.mjs",
    "examples/jsm/curves/NURBSCurve.js": "NURBSCurve.mjs",
    "examples/jsm/curves/NURBSUtils.js": "NURBSUtils.mjs",
}
NPM_ROOTS = (
    (re.compile(r"""(from\s+)(['"])three\2"""), r"\1\2./three.module.mjs\2"),
    (re.compile(r"""(['"])\.\./libs/fflate\.module\.js\1"""), r"\1./fflate.module.mjs\1"),
    (re.compile(r"""(['"])\.\./curves/NURBSCurve\.js\1"""), r"\1./NURBSCurve.mjs\1"),
    (re.compile(r"""(['"])\.\./curves/NURBSUtils\.js\1"""), r"\1./NURBSUtils.mjs\1"),
)

# A relative reference to a file of ours, in an import, a `new URL`, or a
# `${EXTENSION_URL}` template: what the guard below resolves against DEST.
REFERENCE = re.compile(r"""(?:['"`]\.{0,2}/|\$\{EXTENSION_URL\})([\w./-]+\.m?js)\b""")


def renamed(name):
    return name[:-3] + ".mjs" if name.endswith(".js") else name


def rename_references(text):
    """Point every mention of a copied `.js` module at its `.mjs` name."""
    for name in MODULES:
        if name.endswith(".js"):
            stem = re.escape(name[:-3])
            text = re.sub(r"(?<=[/'\"`}])" + stem + r"\.js\b", renamed(name), text)
    return text


def git(clone, *args):
    try:
        return subprocess.run(["git", "-C", clone, *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def save_patch():
    """The working tree's deltas against the committed copy -> the patch."""
    diff = subprocess.run(
        ["git", "-C", ROOT, "diff", "--", os.path.relpath(DEST, ROOT)],
        capture_output=True, text=True, check=True).stdout
    if not diff.strip():
        sys.exit("nothing to save: the vendored copy has no uncommitted changes")
    with open(PATCH, "w", encoding="utf-8") as handle:
        handle.write(diff)
    print(f"wrote {os.path.relpath(PATCH, ROOT)} ({len(diff.splitlines())} lines)")


def stamp(rev, when):
    with open(README, encoding="utf-8") as handle:
        text = handle.read()
    stamped, count = re.subn(r"revision `[^`]+` \([^)]*\)",
                             f"revision `{rev}` ({when})", text, count=1)
    if not count:
        sys.exit(f"{README} no longer carries a revision line to stamp")
    with open(README, "w", encoding="utf-8") as handle:
        handle.write(stamped)


def check_references():
    """Every relative module a copied file names must be in DEST.

    This is what catches upstream starting to import a module this script
    does not copy: without it the stage would fail only when it is opened.
    """
    missing = []
    for name in sorted(os.listdir(DEST)):
        if not name.endswith(".mjs"):
            continue
        with open(os.path.join(DEST, name), encoding="utf-8") as handle:
            text = handle.read()
        for target in sorted(set(REFERENCE.findall(text))):
            if not os.path.isfile(os.path.join(DEST, target)):
                missing.append(f"{name} -> {target}")
    if missing:
        sys.exit("references to files this script does not copy:\n  " + "\n  ".join(missing))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clone", nargs="?", help="path to a clone of " + UPSTREAM)
    parser.add_argument("--save", action="store_true",
                        help="write the current local edits to tools/posestudio.patch")
    args = parser.parse_args()

    if args.save:
        save_patch()
        return
    if not args.clone:
        parser.error("a path to an upstream clone is required")
    web = os.path.join(args.clone, "web")
    if not os.path.isfile(os.path.join(web, "vnccs_pose_studio_core.js")):
        sys.exit(f"{web} has no vnccs_pose_studio_core.js — point this at the clone's root")

    os.makedirs(os.path.join(DEST, "assets"), exist_ok=True)
    os.makedirs(os.path.join(DEST, "textures"), exist_ok=True)

    for name in MODULES:
        src = os.path.join(web, name)
        if not os.path.isfile(src):
            sys.exit(f"upstream no longer ships web/{name} — check what replaced it")
        with open(src, encoding="utf-8") as handle:
            text = rename_references(handle.read())
        with open(os.path.join(DEST, renamed(name)), "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"  {renamed(name)}  {len(text) // 1024} KB")

    for name in ASSETS:
        src = os.path.join(web, name)
        if not os.path.isfile(src):
            sys.exit(f"upstream no longer ships web/{name} — check what replaced it")
        shutil.copyfile(src, os.path.join(DEST, name))
        print(f"  {name}  {os.path.getsize(src) // 1024} KB")
    shutil.copyfile(os.path.join(args.clone, "LICENSE"), os.path.join(DEST, "LICENSE"))

    for source, target in NPM.items():
        url = f"https://cdn.jsdelivr.net/npm/three@{THREE}/{source}"
        with urllib.request.urlopen(url, timeout=60) as response:
            text = response.read().decode("utf-8")
        for pattern, replacement in NPM_ROOTS:
            text = pattern.sub(replacement, text)
        if re.search(r"""from\s+['"](three|\.\./)""", text):
            sys.exit(f"{source}: an import this script does not know how to re-root")
        text = f"// three {THREE} {source}, vendored by tools/vendor_posestudio.py. MIT, (c) three.js authors.\n" + text
        with open(os.path.join(DEST, target), "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"  {target}  {len(text) // 1024} KB  (npm three@{THREE})")

    if os.path.isfile(PATCH):
        result = subprocess.run(["git", "-C", ROOT, "apply", "--verbose", PATCH],
                                capture_output=True, text=True)
        if result.returncode:
            sys.exit(
                f"{os.path.relpath(PATCH, ROOT)} no longer applies:\n{result.stderr}\n"
                "Upstream has changed the code a local fix sits on. Read the "
                "hunks — upstream may have made the fix themselves."
            )
        print(f"applied {os.path.relpath(PATCH, ROOT)}")

    check_references()
    rev, when = git(args.clone, "rev-parse", "--short", "HEAD"), git(args.clone, "log", "-1", "--format=%cs")
    stamp(rev, when)
    print(f"stamped {UPSTREAM} @ {rev} ({when}) -> {os.path.relpath(DEST, ROOT)}")


if __name__ == "__main__":
    main()
