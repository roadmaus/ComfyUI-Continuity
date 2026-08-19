#!/usr/bin/env python3
"""Vendor the MiniMax H3 Style Atlas into the pack.

The atlas — <https://github.com/hoodtronik/minimax-h3-style-atlas> — is one
generated `index.html` holding every distinct style descriptor in ostris's
`minimax_h3_1k` dataset, each with a still frame from the clip it was read off,
inlined as a base64 webp. This script takes that page apart and writes the two
things the Style tab needs:

* `js/minimax_creator/presets/atlas.js` — the index. Category, phrase and clip
  ids, one line per style, and nothing else. It is a **mirror of upstream**, not
  a design: no titles, no ordering of ours, no editorialising. Everything the
  library decides about how a style is shown lives in `presets/stylelib.js`,
  hand-written, so that re-running this script never clobbers a design decision.
* `js/minimax_creator/presets/atlas/<clip>.webp` — the stills, one file per clip,
  byte-identical to the ones the page carries. Separate files rather than data
  URIs in the module: the grid lazy-loads, so a library of 941 styles fetches the
  dozen it is actually showing, and the browser caches them like any other image.
  Inlined they would be five megabytes of base64 parsed on every library open.

Only stills and text are taken. No video is downloaded, vendored or streamed —
the clips stay where they are, and the offline bundle is not a dependency.

Updating, when upstream regenerates the atlas:

    git clone --depth 1 https://github.com/hoodtronik/minimax-h3-style-atlas /tmp/atlas
    python3 tools/vendor_style_atlas.py /tmp/atlas
    python3 tests/test_style_atlas.py

Stills for clips upstream dropped are deleted, so the folder never accumulates
orphans, and the revision is stamped into the generated header — which is what
makes "is our copy current?" answerable by reading one line.

    python3 tools/vendor_style_atlas.py <path to the atlas clone, or its index.html>
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_MODULE = os.path.join(ROOT, "js", "minimax_creator", "presets", "atlas.js")
OUT_THUMBS = os.path.join(ROOT, "js", "minimax_creator", "presets", "atlas")

UPSTREAM = "hoodtronik/minimax-h3-style-atlas"
DATASET = "ostris/minimax_h3_1k"

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
        "// Styles and stills are from the Style Atlas by hoodtronik, built over the",
        "// `%s` dataset by ostris. Text and one still frame per clip;" % DATASET,
        "// no video is vendored, downloaded or streamed by this pack.",
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

    missing = [clip for style in styles for clip in style["clips"] if clip not in atlas.thumbs]
    if missing:
        parser.error("%d clips have no still: %s" % (len(missing), ", ".join(missing[:5])))
    empty = [s for s in styles if not s["phrase"] or not s["clips"]]
    if empty:
        parser.error("%d styles have no descriptor or no clip" % len(empty))

    clips = sorted({clip for style in styles for clip in style["clips"]})
    counts = {"styles": len(styles), "clips": len(clips)}

    # Stills first, then the index, then the sweep: a half-written run leaves a
    # module that names only files that are already on disk.
    os.makedirs(OUT_THUMBS, exist_ok=True)
    written = 0
    for clip in clips:
        path = os.path.join(OUT_THUMBS, "%s.webp" % clip)
        payload = atlas.thumbs[clip]
        if os.path.exists(path):
            with open(path, "rb") as handle:
                if handle.read() == payload:
                    continue
        with open(path, "wb") as handle:
            handle.write(payload)
        written += 1

    with open(OUT_MODULE, "w", encoding="utf-8") as handle:
        handle.write(render_module(categories, counts, revision))

    keep = {"%s.webp" % clip for clip in clips}
    stale = [name for name in os.listdir(OUT_THUMBS) if name not in keep]
    for name in stale:
        os.remove(os.path.join(OUT_THUMBS, name))

    bytes_on_disk = sum(len(atlas.thumbs[clip]) for clip in clips)
    print("%d styles in %d categories, %d clips (%d stills written, %d removed, %.1f MB)"
          % (counts["styles"], len(categories), counts["clips"], written, len(stale),
             bytes_on_disk / 1e6))
    print("revision %s" % (revision or "unknown"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
