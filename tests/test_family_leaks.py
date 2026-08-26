"""No family knowledge in the frontend's code — the phase-5 audit, executable.

The plan's pass condition is a grep: family tokens (`fl2va`, `ref2va`, `h3`,
`minimax`) must not appear in `web/creator/` outside `manifest.js`, because
anything the UI *branches on* that is not in the served manifest is a leak the
next family trips over. Run raw, that grep drowns in things that are not
leaks: comments that explain H3, localized copy that names it, the frozen
`/continuity/*` routes and `MiniMaxH3*` node ids, SVG path data that
happens to contain `h3`.

So this suite strips every file down to what the grep was actually after —
**code**: comments and string-literal contents removed, template-literal
`${...}` interpolations kept (they are code). A family token that survives is
an identifier, a property name, or a bare key — `state.minimax`, `H3_RULES`,
`route === "auto" ? ... : "fl2va"` would all be caught (the last because only
the quotes' *contents* are dropped, so the token in a comparison lives in the
string... which is why frozen-value comparisons read manifest constants
instead).

What this deliberately does not police: prose. Tooltips and dictionary keys
may say "H3" — they are copy, keyed by their English text, and the ones tied
to a manifest-declared control already travel in the manifest. The frozen
strings (routes, node ids, storage keys) are contracts, not leaks.

Excluded wholesale: `manifest.js` (the one file allowed to know), `locales/`
and `presets/` (dictionaries and the vendored atlas), `creator.js` at the web
root (the extension shell that owns the frozen node-id table).

    python3 tests/test_family_leaks.py
"""

import os
import re

import layout
from harness import FAILURES, passed

TOKEN = re.compile(r"fl2va|ref2va|h3|minimax", re.IGNORECASE)

SKIP_DIRS = {"locales", "presets"}
SKIP_FILES = {os.path.join(layout.WEB_ROOT, "manifest.js")}


def strip(source):
    """JS source with comments and string contents removed, code kept.

    A character scanner rather than regexes, because `//` inside a string is
    not a comment and `"` inside a comment is not a string. Template-literal
    interpolations are re-entered as code — `` `x ${state.minimax}` `` must
    not hide its access. Regex literals are not modelled; a family token in
    one would be caught as code, which is the safe direction.
    """
    out = []
    i, n = 0, len(source)
    mode = "code"          # code | line | block | single | double | template
    depth = []             # template nesting: interpolation brace depth
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if mode == "code":
            if ch == "/" and nxt == "/":
                mode = "line"; i += 2; continue
            if ch == "/" and nxt == "*":
                mode = "block"; i += 2; continue
            if ch == "'":
                mode = "single"; out.append(ch); i += 1; continue
            if ch == '"':
                mode = "double"; out.append(ch); i += 1; continue
            if ch == "`":
                mode = "template"; out.append(ch); i += 1; continue
            if ch == "}" and depth and depth[-1] == 0:
                depth.pop(); mode = "template"; out.append(ch); i += 1; continue
            if ch == "{" and depth:
                depth[-1] += 1
            elif ch == "}" and depth:
                depth[-1] -= 1
            out.append(ch); i += 1; continue
        if mode == "line":
            if ch == "\n":
                mode = "code"; out.append(ch)
            i += 1; continue
        if mode == "block":
            if ch == "*" and nxt == "/":
                mode = "code"; i += 2; continue
            if ch == "\n":
                out.append(ch)
            i += 1; continue
        if mode in ("single", "double"):
            if ch == "\\":
                i += 2; continue
            if (mode == "single" and ch == "'") or (mode == "double" and ch == '"'):
                mode = "code"; out.append(ch)
            i += 1; continue
        # template
        if ch == "\\":
            i += 2; continue
        if ch == "$" and nxt == "{":
            depth.append(0); mode = "code"; out.append("${"); i += 2; continue
        if ch == "`":
            mode = "code"; out.append(ch)
        elif ch == "\n":
            out.append(ch)
        i += 1
    return "".join(out)


def files():
    for base, dirs, names in os.walk(layout.WEB_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name.endswith(".js"):
                path = os.path.join(base, name)
                if path not in SKIP_FILES:
                    yield path


for path in files():
    with open(path, encoding="utf-8") as handle:
        code = strip(handle.read())
    for lineno, line in enumerate(code.splitlines(), 1):
        if TOKEN.search(line):
            rel = os.path.relpath(path, layout.WEB_ROOT)
            FAILURES.append(f"{rel}:{lineno}: family token in code: {line.strip()[:80]}")

passed("no family tokens in frontend code outside manifest.js")
