"""`state.js` still agrees with `subjects.py` about which plates are asleep.

The card's chip is greyed by `state.asleepHere` and the file is cut by
`compile_request`; the two deciding apart would mean a row showing a picture
the render never sends, or sending one the row said was out. So the same
sentences are put through both, with the same members, and the answers have
to match — including the `{a|b}` case, where the box lights the alternative
the seed takes and the plate has to wake on the chosen text and not the typed
one.

    python3 tests/test_triggers_mirror.py

Skips itself if node is not installed.
"""

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "compile",
                   "variations", package="mmc")
subjects, compiler = _pkg.subjects, _pkg.compile

CAST = [
    {"handle": "vera", "from": ["img-1", "img-2"], "motion": ["img-3", "vid-1"],
     "triggers": {"img-2": "Hat, cap", "img-3": "smok", "vid-1": "swing"}},
    {"handle": "ben", "from": ["img-2"]},
]

# What is typed, and what the words are held against.
LINES = [
    "Day, sun,    STUPID SPACES    ",
    " , ,smok,",
    "",
    "hat",
]
SENTENCES = [
    "@vera waits.",
    "@vera, in her hat, waits.",
    "@vera is Smoking by the door.",
    "@vera swings; @ben watches.",
    "@ben watches.",
    "@vera waits. @img-3 shows how.",
    "@vera waits. @img-30 by the door.",
    "what she does",
    "two hats, (hat), her-hat, chapeau",
    "@vera swings; a smokarilly smokilly evening.",
    "a room, empty.",
]
# A `{a|b}` under twelve seeds: the sentence the seed makes is what wakes
# the plate, on both sides.
VARIED = "@vera {waits|smokes}."

SCRIPT = """
const s = await import(process.argv[1]);
const cast = JSON.parse(process.argv[2]);
const lines = JSON.parse(process.argv[3]);
const sentences = JSON.parse(process.argv[4]);
const varied = process.argv[5];
const row = ["img-1", "img-2", "img-3", "vid-1"].map((h) => ({
  handle: h, kind: h.startsWith("vid") ? "video" : "image", role: "reference", filename: h + ".png",
}));
console.log(JSON.stringify({
  split: lines.map((line) => s.splitTriggers(line)),
  parsed: s.subjectTriggers(cast[0]),
  asleep: sentences.map((text) => [...s.asleepHere({ prompt: text, assets: row, subjects: cast })].sort()),
  chosen: Array.from({ length: 12 }, (_, seed) =>
    [...s.asleepHere({ prompt: varied, assets: row, subjects: cast }, { seed, card: 1 })].sort()),
  // Read as typed, both alternatives at once: the superset the counters use.
  unchosen: [...s.asleepHere({ prompt: varied, assets: row, subjects: cast })].sort(),
  files: cast.map((c) => s.subjectFiles(c)),
}));
"""

reflected = layout.run(SCRIPT, MIRROR, CAST, LINES, SENTENCES, VARIED)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: js {got!r}, py {want!r}")


for line, words in zip(LINES, reflected["split"]):
    check(f"the words in {line!r}", words, list(subjects.split_triggers(line)))

parsed = subjects.parse(CAST)
check("the words each file waits for",
      {h: list(subjects.split_triggers(t)) for h, t in reflected["parsed"].items()},
      {h: list(w) for h, w in parsed[0].triggers.items()})
for case, files in zip(CAST, reflected["files"]):
    check(f"what {case['handle']} claims, actions included",
          files, list(subjects.parse([case])[0].files))


def py_asleep(prompt):
    """What `compile_request` cuts for want of a word, as the mirror reports it:
    a cited member's files, minus what stays awake on anybody cited."""
    cited = subjects.cited(parsed, [prompt])
    claimed = {h for s in cited for h in s.files}
    return sorted(claimed - subjects.awake(cited, [prompt]))


for text, handles in zip(SENTENCES, reflected["asleep"]):
    check(f"asleep under {text!r}", handles, py_asleep(text))

piece = {"prompt": "", "assets": [], "subjects": CAST,
         "segments": [{"prompt": VARIED, "assets": [], "loras": [], "duration_s": 6}]}
for seed, handles in enumerate(reflected["chosen"]):
    chosen = compiler.varied_piece(piece, seed)["segments"][0]["prompt"]
    check(f"asleep under seed {seed} ({chosen!r})", handles, py_asleep(chosen))
check("read as typed, a word in either alternative wakes the plate",
      reflected["unchosen"], py_asleep(VARIED))

passed("state.js and subjects.py agree about which plates are asleep")
