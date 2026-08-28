#!/usr/bin/env python3
"""Vendor the MiniMax H3 Style Atlas into the pack.

The atlas — <https://github.com/hoodtronik/minimax-h3-style-atlas> — is one
generated `index.html` holding every distinct style descriptor in ostris's
`minimax_h3_1k` dataset, each with a still frame from the clip it was read off,
inlined as a base64 webp. This script takes that page apart, pulls the clips it
cites, and writes the three things the Style tab needs:

* `web/creator/presets/atlas.js` — the index. Category, phrase and clip
  ids, one line per style, and nothing else. It is a **mirror of upstream**, not
  a design: no titles, no ordering of ours, no editorialising. Everything the
  library decides about how a style is shown lives in `presets/stylelib.js`,
  hand-written, so that re-running this script never clobbers a design decision.
* `web/creator/presets/atlas/<clip>.webp` — the card pictures, 192px wide,
  one per clip. Separate files rather than data URIs in the module: the grid
  lazy-loads, so a library of 941 styles fetches the dozen it is actually showing,
  and the browser caches them like any other image. Inlined they would be five
  megabytes of base64 parsed on every library open.
* `web/creator/presets/atlas/full/<clip>.webp` — the same frames at the
  clip's own resolution, ~30 MB for the set. **This is what makes a style usable
  as a reference picture rather than only as a phrase.** A 192px card picture is
  not a reference; the clip is 512 to 1088 across, and `encode.py` scales a
  reference image up to a 2048 short edge, so every pixel of the source counts.

**Both sizes are cut from one frame of the clip, not from the atlas page.** The
page's inlined stills are a fine 192px, but they are the only pictures it has,
and a card showing one moment beside a reference taken from another is a small
lie about what you are choosing. Taking both from the dataset also means the page
is the text mirror and the dataset is the picture source, which is the honest
division — `atlas.js` says nothing about pictures at all.

**Clips are pulled here so that the pack never pulls anything.** Roughly 1.3 GB
of video crosses the network at vendor time, is decoded to one frame each, and is
thrown away; the installed node reads nothing but its own folder and works with
the machine offline. They are cached under `--clips` between runs, so a re-vendor
after an upstream text change costs nothing.

Frames are decoded with PyAV, which ComfyUI already depends on — no ffmpeg binary.

**Re-vendoring does not carry the scene cut with it.** What a style *applies* is
`presets/atlasstyle.js`, compiled from `tools/style_cuts.jsonl` — one reviewed
decision per style, see `tools/distil_style_atlas.py`. A style upstream adds has
no decision here, falls back to its verbatim descriptor, and fails
`test_style_atlas.py` until one is written. So the sequence below ends with that
test for a reason.

Updating, when upstream regenerates the atlas:

    git clone --depth 1 https://github.com/hoodtronik/minimax-h3-style-atlas /tmp/atlas
    python3 tools/vendor_style_atlas.py /tmp/atlas --clips /tmp/atlas-clips
    python3 tools/distil_style_atlas.py
    python3 tests/test_style_atlas.py

Pictures for clips upstream dropped are deleted, so the folder never accumulates
orphans, and the revision is stamped into the generated header — which is what
makes "is our copy current?" answerable by reading one line.

    python3 tools/vendor_style_atlas.py <path to the atlas clone, or its index.html>
"""

import argparse
import base64
import concurrent.futures
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# `web/creator/`, which is where the frontend has lived since it became a
# package. These said `js/minimax_creator/` — the layout before that move, and
# before the pack was renamed — so a re-vendor would have written the atlas into
# a directory nothing loads.
OUT_MODULE = os.path.join(ROOT, "web", "creator", "presets", "atlas.js")
OUT_THUMBS = os.path.join(ROOT, "web", "creator", "presets", "atlas")
OUT_STILLS = os.path.join(OUT_THUMBS, "full")

UPSTREAM = "hoodtronik/minimax-h3-style-atlas"
DATASET = "ostris/minimax_h3_1k"

CLIP_URL = "https://huggingface.co/datasets/%s/resolve/main/%%s.mp4" % DATASET

#: What a card picture is: 192 across, height free. Upstream's own shape, kept so
#: regenerating the pictures is not also a re-layout of the grid.
THUMB_WIDTH = 192

#: WebP quality for the full-size stills. Measured over a spread of fifteen clips:
#: q75 averages 33 KB against 43 KB at q82, and on the hardest detail in the set —
#: translucent LEGO flame pieces against a lit backdrop — the two are
#: indistinguishable at 2x. Thirty megabytes buys the whole atlas as references.
STILL_QUALITY = 75

#: Card pictures are small enough that quality is free, and they are the thing a
#: user judges nine hundred styles by.
THUMB_QUALITY = 82

DATA_URI = re.compile(r"^data:image/webp;base64,(.+)$", re.S)


class AtlasParser(HTMLParser):
    """The atlas page, as categories of styles.

    The markup is generated and uniform — `section.cat > h2` names a category and
    each `li.row` is one style: an `span.ph` holding the descriptor, then a
    `figure.clip` per clip carrying `data-f` and an inlined still. So this tracks
    which of those three things it is inside and collects text as it goes, rather
    than pattern-matching the serialised HTML, which would break on the first
    time upstream reflows the file.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.categories = []      # [{name, styles: [{phrase, clips: [id]}]}]
        self.thumbs = {}          # clip id -> webp bytes
        self._in_h2 = False
        self._in_phrase = False
        self._text = []
        self._clip = None

    # -- helpers ---------------------------------------------------------------

    @property
    def _category(self):
        return self.categories[-1] if self.categories else None

    @property
    def _style(self):
        category = self._category
        return category["styles"][-1] if category and category["styles"] else None

    @staticmethod
    def _classes(attrs):
        return set((dict(attrs).get("class") or "").split())

    # -- the three things we are ever inside ------------------------------------

    def handle_starttag(self, tag, attrs):
        classes = self._classes(attrs)
        values = dict(attrs)
        if tag == "section" and "cat" in classes:
            self.categories.append({"name": "", "styles": []})
        elif tag == "h2" and self._category is not None and not self._category["name"]:
            self._in_h2, self._text = True, []
        elif tag == "li" and "row" in classes and self._category is not None:
            self._category["styles"].append({"phrase": "", "clips": []})
        elif tag == "span" and "ph" in classes:
            self._in_phrase, self._text = True, []
        elif tag == "button" and "play" in classes:
            # `data-f` is the clip's file — "000513.mp4". The id is its stem, and
            # it is what the caption chip shows and what the dataset calls it.
            name = values.get("data-f") or ""
            self._clip = os.path.splitext(name)[0] or None
            style = self._style
            if self._clip and style is not None and self._clip not in style["clips"]:
                style["clips"].append(self._clip)
        elif tag == "img" and self._clip:
            match = DATA_URI.match(values.get("src") or "")
            if match:
                self.thumbs[self._clip] = base64.b64decode(match.group(1))

    def handle_endtag(self, tag):
        if tag == "h2" and self._in_h2:
            self._in_h2 = False
            if self._category is not None:
                self._category["name"] = "".join(self._text).strip()
        elif tag == "span" and self._in_phrase:
            self._in_phrase = False
            style = self._style
            if style is not None:
                style["phrase"] = " ".join("".join(self._text).split())
        elif tag == "button":
            self._clip = None

    def handle_data(self, data):
        if self._in_h2 or self._in_phrase:
            self._text.append(data)


# ---- the clips ---------------------------------------------------------------
#
# One frame of each is the whole point of the network half. Everything here is
# vendor-time only; nothing in this section has a counterpart in the pack.


def fetch_clip(clip, cache):
    """Put `<clip>.mp4` in `cache` if it is not there. -> the path, or None.

    Written to `.part` and moved into place, so an interrupted run leaves no
    truncated file that the next run would happily decode a green frame out of.
    """
    path = os.path.join(cache, "%s.mp4" % clip)
    if os.path.exists(path) and os.path.getsize(path):
        return path
    part = path + ".part"
    try:
        with urllib.request.urlopen(CLIP_URL % clip, timeout=300) as response, \
                open(part, "wb") as handle:
            while True:
                block = response.read(1 << 20)
                if not block:
                    break
                handle.write(block)
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        if os.path.exists(part):
            os.remove(part)
        print("  %s: %s" % (clip, error), file=sys.stderr)
        return None
    os.replace(part, path)
    return path


#: Where along a clip to look for its picture. Weighted towards the middle —
#: these are generated clips and the opening frames are routinely the weakest, a
#: fade up, a camera still settling, the subject not yet in shot — but not only
#: the middle, because some of them cut to black there. Seeks land on keyframes,
#: so seven marks over five seconds is nothing like seven distinct frames; it is
#: enough spread to get past a dark passage.
FRAME_MARKS = (0.5, 0.35, 0.65, 0.2, 0.8, 0.05, 0.95)

#: Below this spread of luminance a frame is a black card or a white flash, not a
#: picture of anything. Two clips in the thousand cut to black across their
#: middle and one opens on black for two thirds of its length; taking their
#: midpoint gave a 164-byte file that was a hole on the card and useless as a
#: reference. Measured against the set: the flattest frame that is genuinely a
#: picture — fog over water — sits at 18.
FLAT = 6.0


def best_frame(path):
    """The most legible frame of a clip, as a PIL image. -> image, or None.

    Several marks are sampled and the one with the widest spread of luminance
    wins. Not "the middle, and something else if the middle is black": a rule
    with a fallback in it picks the fallback silently and nobody ever learns the
    rule was wrong. This picks the best of what it looked at, every time, and the
    middle wins whenever the middle is worth having.
    """
    import av
    from PIL import ImageStat

    best, best_spread = None, -1.0
    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        seconds = float(stream.duration * stream.time_base) if stream.duration else 0.0
        for mark in FRAME_MARKS:
            if seconds > 0:
                container.seek(int((seconds * mark) / stream.time_base), stream=stream)
            else:
                container.seek(0)
            frame = next(container.decode(stream), None)
            if frame is None:
                continue
            image = frame.to_image()
            spread = ImageStat.Stat(image.convert("L")).stddev[0]
            if spread > best_spread:
                best, best_spread = image, spread
            # The middle is tried first, so a middle worth having ends this.
            if best_spread >= FLAT * 4:
                break
    return None if best_spread < FLAT else best


def encode_pictures(image):
    """One frame as the two files it becomes. -> (thumb bytes, still bytes)."""
    from PIL import Image

    still = io.BytesIO()
    image.save(still, "WEBP", quality=STILL_QUALITY, method=6)

    width, height = image.size
    thumb_size = (THUMB_WIDTH, max(1, round(height * THUMB_WIDTH / width)))
    thumb = io.BytesIO()
    image.resize(thumb_size, Image.LANCZOS).save(
        thumb, "WEBP", quality=THUMB_QUALITY, method=6)
    return thumb.getvalue(), still.getvalue()


def revision_of(directory):
    """The upstream commit this copy was taken from, when the source is a clone."""
    try:
        out = subprocess.run(["git", "-C", directory, "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def render_module(categories, counts, revision):
    """The generated index, one line per style so an update reads as a diff."""
    names = [category["name"] for category in categories]
    lines = [
        "// The MiniMax H3 Style Atlas, vendored. GENERATED — do not edit by hand.",
        "//",
        "// Regenerate with `python3 tools/vendor_style_atlas.py <path to the atlas>`;",
        "// everything about how a style is *shown* lives in `stylelib.js`, which is",
        "// hand-written, so re-running the generator cannot clobber a design decision.",
        "//",
        "// Styles are from the Style Atlas by hoodtronik, built over the `%s`" % DATASET,
        "// dataset by ostris; the pictures are one frame of each clip, cut from the",
        "// dataset at vendor time. No video is vendored, and nothing this pack does at",
        "// runtime touches the network — the frames are on disk.",
        "//",
        "//   upstream  https://github.com/%s" % UPSTREAM,
        "//   revision  %s" % (revision or "unknown"),
        "//   dataset   https://huggingface.co/datasets/%s" % DATASET,
        "",
        "export const ATLAS = {",
        "  upstream: %s," % json.dumps(UPSTREAM),
        "  revision: %s," % json.dumps(revision or ""),
        "  dataset: %s," % json.dumps(DATASET),
        "  styles: %d," % counts["styles"],
        "  clips: %d," % counts["clips"],
        "};",
        "",
        "/** The eight media categories, in the order the atlas lists them. */",
        "export const CATEGORIES = [",
    ]
    lines += ["  %s," % json.dumps(name) for name in names]
    lines += [
        "];",
        "",
        "/** One style per line: `[category index, descriptor, [clip ids]]`. The",
        " *  descriptor is the opening style clause of the clip's caption, verbatim. */",
        "export const STYLES = [",
    ]
    for index, category in enumerate(categories):
        for style in category["styles"]:
            lines.append("[%d,%s,%s]," % (index, json.dumps(style["phrase"]),
                                          json.dumps(style["clips"], separators=(",", ":"))))
    lines += ["];", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="the atlas clone, or its index.html")
    parser.add_argument("--revision", default=None,
                        help="upstream commit to stamp, when the source is not a clone")
    parser.add_argument("--clips", default=os.path.join(ROOT, ".atlas-clips"),
                        help="where dataset clips are cached between runs "
                             "(~1.3 GB; git-ignored, safe to delete)")
    parser.add_argument("--offline", action="store_true",
                        help="decode only clips already in --clips, and fail if any "
                             "the atlas cites is missing")
    parser.add_argument("--jobs", type=int, default=6,
                        help="how many clips to pull at once (default 6)")
    args = parser.parse_args(argv)

    source = os.path.abspath(args.source)
    if os.path.isdir(source):
        page, revision = os.path.join(source, "index.html"), args.revision or revision_of(source)
    else:
        page, revision = source, args.revision
    if not os.path.isfile(page):
        parser.error("no index.html at %s" % page)

    with open(page, encoding="utf-8") as handle:
        atlas = AtlasParser()
        atlas.feed(handle.read())

    categories = [c for c in atlas.categories if c["name"] and c["styles"]]
    styles = [s for c in categories for s in c["styles"]]
    if not styles:
        parser.error("that page holds no styles — is it the atlas?")

    empty = [s for s in styles if not s["phrase"] or not s["clips"]]
    if empty:
        parser.error("%d styles have no descriptor or no clip" % len(empty))

    clips = sorted({clip for style in styles for clip in style["clips"]})
    counts = {"styles": len(styles), "clips": len(clips)}

    # The page's own inlined stills are parsed but no longer written — they are
    # the check that the page is the atlas and that it names the clips we are
    # about to go and fetch. The pictures come from the clips.
    unlisted = [clip for clip in clips if clip not in atlas.thumbs]
    if unlisted:
        parser.error("%d clips have no still on the page: %s"
                     % (len(unlisted), ", ".join(unlisted[:5])))

    os.makedirs(args.clips, exist_ok=True)
    if args.offline:
        held = [c for c in clips if os.path.exists(os.path.join(args.clips, "%s.mp4" % c))]
        if len(held) < len(clips):
            parser.error("--offline, but %d of %d clips are not in %s"
                         % (len(clips) - len(held), len(clips), args.clips))
        fetched = {c: os.path.join(args.clips, "%s.mp4" % c) for c in clips}
    else:
        print("pulling %d clips into %s (~1.3 GB, cached between runs)"
              % (len(clips), args.clips))
        fetched = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for clip, path in zip(clips, pool.map(
                    lambda c: fetch_clip(c, args.clips), clips)):
                fetched[clip] = path
        lost = sorted(c for c, path in fetched.items() if not path)
        if lost:
            parser.error("%d clips could not be pulled: %s"
                         % (len(lost), ", ".join(lost[:5])))

    # Pictures first, then the index, then the sweep: a half-written run leaves a
    # module that names only files that are already on disk.
    os.makedirs(OUT_STILLS, exist_ok=True)
    written = 0
    on_disk = 0
    for index, clip in enumerate(clips, 1):
        frame = best_frame(fetched[clip])
        if frame is None:
            parser.error("every frame sampled out of %s is flat — a black card is "
                         "not a picture of a style" % fetched[clip])
        thumb, still = encode_pictures(frame.convert("RGB"))
        on_disk += len(thumb) + len(still)
        for path, payload in ((os.path.join(OUT_THUMBS, "%s.webp" % clip), thumb),
                              (os.path.join(OUT_STILLS, "%s.webp" % clip), still)):
            if os.path.exists(path):
                with open(path, "rb") as handle:
                    if handle.read() == payload:
                        continue
            with open(path, "wb") as handle:
                handle.write(payload)
            written += 1
        if index % 100 == 0:
            print("  %d/%d frames" % (index, len(clips)))

    with open(OUT_MODULE, "w", encoding="utf-8") as handle:
        handle.write(render_module(categories, counts, revision))

    keep = {"%s.webp" % clip for clip in clips}
    stale = [name for name in os.listdir(OUT_THUMBS)
             if name not in keep and name != "full"]
    stale += [os.path.join("full", name) for name in os.listdir(OUT_STILLS)
              if name not in keep]
    for name in stale:
        os.remove(os.path.join(OUT_THUMBS, name))

    print("%d styles in %d categories, %d clips (%d pictures written, %d removed, %.1f MB)"
          % (counts["styles"], len(categories), counts["clips"], written, len(stale),
             on_disk / 1e6))
    print("revision %s" % (revision or "unknown"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
