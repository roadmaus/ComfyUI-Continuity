#!/usr/bin/env python3
"""Cut the scene out of every vendored atlas descriptor, once, by hand.

Upstream's descriptor is the opening of an H3 caption, and H3's captions fuse
the look with the shot: "LEGO brickfilm stop motion with glossy plastic textures
under warm kitchen lighting, inside a brick-built restaurant kitchen set a chef
minifig flips a tiny brick pan…". Applied whole, that asks for the chef and the
pan along with the plastic sheen. `stylelib.js` used to cut this with three
regexes and a hand-maintained list of nouns — fisherman, chef, dentist — fitted
to the 941 rows that happened to be vendored, which is a rule that stops being
true the first time upstream adds a barista.

So the cut is a *decision per style*, made once, reviewed, and committed as
content: `tools/style_cuts.jsonl`, one line per clip. It is read here and
compiled into `web/creator/presets/atlasstyle.js`.

    python3 tools/distil_style_atlas.py          # write the module
    python3 tools/distil_style_atlas.py --check  # audit only, write nothing

**A decision is a clause count, not prose.** `{"clip": "000482", "keep": 1,
"edits": [["under warm kitchen lighting", "under warm set lighting"]]}` means:
keep the first clause of upstream's chain, then apply that substitution inside
it. The kept text is therefore *reconstructed* from `atlas.js` rather than
retyped, so it cannot drift from upstream's words except exactly where an edit
says it does — and every edit is in the file, in one column, auditable in a pass.

Two rules produced these, and they are the two worth knowing when adding rows:

* **Extent is a prefix cut.** Walk the clause chain, stop at the first clause
  that is about the scene rather than the look, never reach past it. A style
  clause stranded inside a scene clause ("in a cramped clay basement lit by a
  single bare bulb") is lost rather than salvaged, because salvage means
  reordering and reordering means the output stops being checkable against
  the source.
* **Content inside the kept clauses is generalised.** Fifty-seven descriptors
  carry literal on-screen text — `"ROUND 1 FIGHT"`, `"09/03/2024 11:10 AM"` —
  which H3 will burn into the frame as text if it is left in; thirty weld the
  lighting to a room ("warm kitchen lighting"). Those become generic. Every
  substitution is logged as an edit.

Re-vendoring does not invalidate this file. Clips upstream keeps carry their
decision forward untouched; only new or changed ones need a line, and `--check`
names them.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATLAS = os.path.join(ROOT, "web", "creator", "presets", "atlas.js")
CUTS = os.path.join(ROOT, "tools", "style_cuts.jsonl")
OUT = os.path.join(ROOT, "web", "creator", "presets", "atlasstyle.js")

# The dataset's subject token — `(S1)`, `(S2)`. A reference to a character
# defined elsewhere in a caption this pack never had. Stripped before the chain
# is split; it has never once fallen inside a clause that a decision keeps.
SUBJECT = re.compile(r"\s*\(S\d+\)")

# ---- the audit --------------------------------------------------------------
#
# None of these decide a cut. They are read *after* one, and they exist because
# a hand-made file of 941 rows needs something that notices the row where the
# hand slipped.

LOCATIVE = re.compile(r"^(?:on|in|inside|at|across|along|atop|down|through|under|over|"
                      r"outside|beside|behind|beneath|amid|among|within|near|past)\s", re.I)
LEAK = re.compile(r"\b(?:m[ae]n|wom[ae]n|boy|girl|kid|child|teenager|fisherman|chef|dentist|"
                  r"farmer|worker|driver|soldier|dancer|singer|astronaut|mechanic|clerk|"
                  r"investigator|rider|player|kitchen|classroom|basement|warehouse|hacienda|"
                  r"balcony|bedroom|garage|cavern|asylum|corridor)\b", re.I)
# `stadium` is deliberately not in that list: in this corpus it only ever
# appears as "stadium floodlights" / "stadium lighting", which names a
# quality of light rather than a place, and is exactly the kind of thing a
# style should keep.
# Burned-in on-screen text, which H3 will render as text if it is left in. A
# quoted name used as a style reference — `"How It's Made"-style factory
# footage` — is not that, and is what the negative lookahead spares.
QUOTED = re.compile(r'"[^"]{2,}"(?!-style)')
MAXLEN = 260


def atlas():
    """Upstream's mirror: `[category, descriptor, [clip ids]]` per style."""
    src = open(ATLAS, encoding="utf-8").read()
    rows = [json.loads(line[:-1]) for line in src.splitlines()
            if line.startswith("[") and line.endswith("],")]
    block = src.split("CATEGORIES = [")[1].split("\n];")[0]
    cats = [json.loads(m) for m in re.findall(r'"(?:[^"\\]|\\.)*"', block)]
    return rows, cats


def clauses(phrase):
    """The descriptor's clause chain. `, ` is the atlas's own join."""
    return [c.strip() for c in SUBJECT.sub("", phrase).split(", ") if c.strip()]


def decisions():
    for line in open(CUTS, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            yield json.loads(line)


def build():
    rows, cats = atlas()
    by_clip = {r[2][0]: r for r in rows}
    out, problems, seen = [], [], set()
    for d in decisions():
        clip = d["clip"]
        if clip in seen:
            problems.append((clip, "decided twice"))
            continue
        seen.add(clip)
        row = by_clip.get(clip)
        if row is None:
            problems.append((clip, "names no style in atlas.js"))
            continue
        chain = clauses(row[1])
        keep = d["keep"]
        if not 1 <= keep <= len(chain):
            problems.append((clip, "keep=%d outside 1..%d" % (keep, len(chain))))
            continue
        style = ", ".join(chain[:keep])
        for frm, to in d.get("edits", []):
            if frm not in style:
                problems.append((clip, "edit matches nothing: %r" % frm))
                continue
            style = style.replace(frm, to)
        style = re.sub(r"\s+", " ", style).strip().strip(",").strip()
        if not style:
            problems.append((clip, "empty after edits"))
            continue
        if LOCATIVE.match(style):
            problems.append((clip, "opens on a locative: %r" % style[:60]))
        if QUOTED.search(style):
            problems.append((clip, "kept on-screen text: %s" % QUOTED.findall(style)))
        if len(style) > MAXLEN:
            problems.append((clip, "%d chars, over %d" % (len(style), MAXLEN)))
        leak = sorted(set(m.group(0).lower() for m in LEAK.finditer(style)))
        if leak:
            problems.append((clip, "scene word survived: %s" % ", ".join(leak)))
        out.append({"clip": clip, "category": row[0], "style": style,
                    "source": row[1], "edits": d.get("edits", [])})
    return rows, cats, out, problems, seen


HEADER = '''// The style-only descriptor of every vendored style. GENERATED — do not edit by hand.
//
// Regenerate with `python3 tools/distil_style_atlas.py`; the decisions it
// compiles are `tools/style_cuts.jsonl`, which is reviewed content and the file
// to edit. See that script's docstring for the two rules the cuts follow.
//
// Upstream's descriptor is kept beside this, untouched, in `atlas.js` — that
// file stays a faithful mirror, and this one is what a style *applies*. The
// inspector shows both, so the caption a clip was read off is never lost.

'''


def write(out):
    body = ["export const CUTS = {"]
    for r in sorted(out, key=lambda r: r["clip"]):
        body.append('  "%s": %s,' % (r["clip"], json.dumps(r["style"], ensure_ascii=False)))
    body.append("};")
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(HEADER + "\n".join(body) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="audit only, write nothing")
    args = ap.parse_args()

    rows, cats, out, problems, seen = build()
    todo = [r for r in rows if r[2][0] not in seen]
    print("cut %d of %d styles" % (len(out), len(rows)))
    if todo:
        from collections import Counter
        print("undecided: %d" % len(todo))
        for name, n in Counter(cats[r[0]] for r in todo).most_common():
            print("    %-42s %d" % (name, n))
    for clip, why in problems:
        print("  ! %s  %s" % (clip, why))
    if problems:
        sys.exit(1)
    if not args.check and not todo:
        write(out)
        print("wrote %s" % os.path.relpath(OUT, ROOT))
