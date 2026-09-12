"""`state.js` still agrees with `compile.py` and `contextir.py` about scopes.

Three lists and one sentence per entry, written down twice: the compiler holds
them because it is what queues the prose, and the box holds them because the
band above the prompt shows that prose while you are still setting the chips.

The duplication is what makes this worth a suite of its own. `Asset.takes` never
reaches the encode path — the DiT is handed the same tensor whatever the chip
says — so the *only* thing a scope does is put words in front of the
description. A value that exists on one side and not the other is therefore not
a cosmetic drift: it is a chip you can set that sends nothing, or a sentence the
band promises and the render never writes.

    python3 tests/test_scopes_mirror.py

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")

_pkg = layout.load("canvas", "contextir", "subjects", "compile")
compiler = _pkg.compile
contextir = _pkg.contextir
subjects = _pkg.subjects


SCRIPT = """
const s = await import(process.argv[1]);
const asset = (kind, takes, rest = {}) =>
  ({ handle: `${kind}-1`, kind, role: "reference", takes, ...rest });
console.log(JSON.stringify({
  takes: { image: s.IMAGE_TAKES, video: s.VIDEO_TAKES, audio: s.AUDIO_TAKES },
  map: Object.fromEntries(Object.entries(s.TAKES)),
  // A sound-only clip scopes as audio on both sides, which is the one place the
  // kind on the blob and the vocabulary it may use disagree.
  soundOnly: s.takeOptions(asset("video", "full", { track: "sound" })),
  audioOfAudio: s.takeOptions(asset("audio", "full")),
  keyframe: s.takeOptions({ handle: "img-1", kind: "image", role: "first_frame" }),
}));
"""

reflected = layout.run(SCRIPT, MIRROR)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: js {got!r}, py {want!r}")


# ---- the vocabularies -------------------------------------------------------

for kind in ("image", "video", "audio"):
    check(f"the {kind} scopes match",
          reflected["takes"][kind], list(compiler.TAKES[kind]))
check("...and so does the map they are looked up in",
      {k: list(v) for k, v in reflected["map"].items()},
      {k: list(v) for k, v in compiler.TAKES.items()})

# Which vocabulary a file may choose from. The interesting one is the clip taken
# for its soundtrack alone: it arrives among the audio, takes an `<Audio N>` and
# never has its picture encoded, so offering it "camera" would be offering a
# narrowing of a file that is not there.
check("a sound-only clip is offered the audio scopes",
      reflected["soundOnly"], list(compiler.TAKES["audio"]))
check("...and so is an audio file", reflected["audioOfAudio"], list(compiler.TAKES["audio"]))
check("a keyframe is offered nothing", reflected["keyframe"], [])

# ---- and every scope says something, in both sections ------------------------
#
# The gap this half exists for: `Asset.takes` never reaches the encode path — the
# DiT is handed the same tensor whatever the chip says — so the *only* thing a
# scope does is put words in the prompt. A value the chip offers and `contextir`
# has no sentence for is a chip you can set that sends nothing at all.
#
# Two sentences per scope now, not one. The reference form says what a label
# denotes (`subject_definitions`) and separately what becomes of it
# (`retention_analysis`), and section 4.1 asks for one retention line per label —
# so a scope with a definition and no marker is half-declared, which is the same
# bug one step further along.

python_define = {f"{kind}:{takes}": text
                 for (kind, takes), text in contextir._DEFINE.items()}

for kind, values in compiler.TAKES.items():
    for takes in values:
        key = f"{kind}:{takes}"
        if key not in python_define:
            FAILURES.append(f"compile offers {key} but contextir defines no sentence for it")
        if (kind, takes) not in contextir._MARKER:
            FAILURES.append(f"compile offers {key} but contextir gives it no retention marker")
        if (kind, takes) not in contextir._BECOMES:
            FAILURES.append(f"compile offers {key} but contextir says nothing about what becomes of it")

# ...and the reverse, which is a sentence nothing can ever ask for.
for key in python_define:
    kind, takes = key.split(":", 1)
    if takes not in compiler.TAKES.get(kind, ()):
        FAILURES.append(f"contextir defines {key}, which is not a scope compile allows")

# Every definition has exactly one place for the label to go. The two whole-video
# relationships used to borrow the summary's opening sentence here, which read as
# a statement about the target video rather than about the label — and said it
# once per clip, so two edited sources each claimed to be the whole source.
for key, text in python_define.items():
    if text.count("%s") != 1:
        FAILURES.append(f"{key}: expected one %s, got {text.count('%s')}")

# The markers are the guide's fixed four, per category. Anything else is a token
# the weights were never trained on in the one field whose vocabulary is fixed.
VISIBLE = {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"}
AUDIO = {"fully_copy", "partially_copy", "reference", "weak_reference"}
for (kind, takes), marker in contextir._MARKER.items():
    allowed = AUDIO if kind == "audio" else VISIBLE
    if marker not in allowed:
        FAILURES.append(f"{kind}:{takes} is marked {marker}, which is not one of {sorted(allowed)}")

# And the cast's own markers are the visible four, since a subject is visible
# content by definition.
if set(subjects.MARKERS) != VISIBLE:
    FAILURES.append(f"subjects.MARKERS is {list(subjects.MARKERS)}, want {sorted(VISIBLE)}")

# The task-type prefixes are section 3's table and nothing else.
TASKS = {"keyframe completion", "reference generation", "video editing",
         "video continuation", "audio reuse", "audio reference"}
if set(contextir.TASK_ORDER) != TASKS:
    FAILURES.append(f"TASK_ORDER is {list(contextir.TASK_ORDER)}, want {sorted(TASKS)}")

passed("state.js mirrors the scope vocabulary; every scope is defined and scoped")
