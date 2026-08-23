"""`outputs.js` still agrees with `outputs.py`.

The duplication is deliberate — the output field says what is wrong while you
are typing, and shows the folder the files will land in, neither of which can
wait for a queue round-trip — but it is only safe while the two agree, and
nothing else checks that. `outputs.py` is authoritative; this asserts the mirror
reflects it.

    python3 tests/test_outputs_mirror.py

The interesting half is the *refusals*: a browser that accepts a prefix the
backend will refuse turns a typo into a failed queue, and a browser that refuses
one the backend would take makes a legal folder untypeable.

Skips itself if node is not installed.
"""

import layout

layout.skip_without_node()

MIRROR = layout.js("outputs.js")
outputs = layout.load("outputs").outputs

# Every string worth asking both sides about, in one subprocess rather than one
# per case. Legal values, refusals, and the shapes that sit on the boundary.
CASES = [
    "", "   ", "H3", "minimax/renders/H3", "my-project/scene-a/take",
    "  shots/a  ", "my-project\\take", "my-project/", "shots/",
    "minimax/%year%-%month%-%day%/H3", "H3_%width%x%height%",
    "a b/c d", "a-b/c_d", "2026-08-10/take-1",
    "../../etc/H3", "minimax/../../H3", "..", ".", "./H3",
    "/var/renders/H3", "C:/renders/H3", "\\\\server\\share\\H3",
    ".secret/H3", "minimax//H3", "minimax/a:b/H3", "minimax /H3", "minimax./H3",
    "a<b/H3", 'a"b/H3', "a|b/H3", "a?b/H3", "a*b/H3",
]

SCRIPT = """
const m = await import(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
const out = { constants: { VIDEO_PREFIX: m.VIDEO_PREFIX, IMAGE_PREFIX: m.IMAGE_PREFIX,
                           TOKENS: m.TOKENS },
              cleaned: {} };
for (const raw of cases) {
  const result = m.cleanPrefix(raw, m.VIDEO_PREFIX);
  out.cleaned[raw] = result.error ? { error: true } : { prefix: result.prefix };
}
out.folders = { "a/b/c": m.folderOf("a/b/c"), "abc": m.folderOf("abc") };
out.stems = { "a/b/c": m.stemOf("a/b/c"), "abc": m.stemOf("abc") };
console.log(JSON.stringify(out));
"""

reflected = layout.run(SCRIPT, MIRROR, CASES)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: js {got!r}, py {want!r}")


check("the video default matches", reflected["constants"]["VIDEO_PREFIX"], outputs.VIDEO_PREFIX)
check("the image default matches", reflected["constants"]["IMAGE_PREFIX"], outputs.IMAGE_PREFIX)
check("the token list matches", reflected["constants"]["TOKENS"], list(outputs.TOKENS))

for raw in CASES:
    got = reflected["cleaned"][raw]
    try:
        want = {"prefix": outputs.clean(raw, outputs.VIDEO_PREFIX)}
    except outputs.PrefixError:
        want = {"error": True}
    check(f"clean({raw!r})", got, want)

# The two splitting helpers exist only in the mirror — the backend gets the same
# split from `get_save_image_path` — so they are checked against what that does.
check("folderOf splits at the last separator", reflected["folders"], {"a/b/c": "a/b", "abc": ""})
check("stemOf is the rest", reflected["stems"], {"a/b/c": "c", "abc": "abc"})

passed(f"outputs.js mirrors outputs.py across {len(CASES)} prefixes")
