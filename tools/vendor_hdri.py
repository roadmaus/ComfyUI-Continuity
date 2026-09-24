#!/usr/bin/env python3
"""Vendor the image-to-3D stage's HDRIs from Poly Haven.

Upstream — <https://polyhaven.com/hdris>, every asset CC0 — is fetched at 4k
as Radiance `.hdr`, which three.js reads with the vendored `RGBELoader`.
Everything lands in `web/creator/vendor/hdri/` with a note of where each file
came from.

**Why two, and why these.** The stage is lit by its environment, so the choice
is really a choice of light, and two kinds cover what a mesh is shot for: a
small studio with softboxes, which reads every surface evenly the way a
product shot does, and an open field under a high sun, which is hard light
from one side and a horizon that is plain enough to stage a turntable in front
of. The third light the tool offers, Neutral, is three.js's procedural room
and costs nothing to ship.

**Why 4k.** The light itself would be the same from a 1k file: it is
prefiltered down to a small cube map either way. The size is for the
background. An equirectangular picture spreads its width over 360°, so at 1k a
40° lens sees about a hundred pixels of it stretched across the frame; at 4k it
sees four hundred and fifty, which holds up behind a turntable. That is about
25 MB a file, and it is in the pack rather than fetched on first use so the
stage never depends on a network being there.

Re-syncing, or changing a pick (edit `FILES` and `liftstage.js`'s `LIGHTS`):

    python3 tools/vendor_hdri.py
"""

import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "web", "creator", "vendor", "hdri")
RESOLUTION = "4k"

# Poly Haven asset id -> what it is, for the credit.
FILES = {
    "studio_small_09": "Studio Small 09",
    "noon_grass": "Noon Grass",
}


def main():
    os.makedirs(DEST, exist_ok=True)
    # A change of size or of pick leaves the old files behind otherwise.
    for stale in os.listdir(DEST):
        if stale.endswith(".hdr"):
            os.remove(os.path.join(DEST, stale))
    credits = ["The image-to-3D stage's environments, from Poly Haven (https://polyhaven.com),",
               f"released under CC0. Fetched at {RESOLUTION} by tools/vendor_hdri.py.", ""]
    for asset, title in FILES.items():
        name = f"{asset}_{RESOLUTION}.hdr"
        url = f"https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/{RESOLUTION}/{name}"
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        with open(os.path.join(DEST, name), "wb") as handle:
            handle.write(data)
        credits.append(f"{name}  {title}  https://polyhaven.com/a/{asset}")
        print(f"  {name}  {len(data) // 1024} KB")
    with open(os.path.join(DEST, "LICENSE"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(credits) + "\n")
    print(f"HDRIs -> {os.path.relpath(DEST, ROOT)}")


if __name__ == "__main__":
    main()
