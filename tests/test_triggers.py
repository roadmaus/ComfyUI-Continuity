"""Wake words: a cast member's plate is in the shot only while the prose says
its word (issue #72), and their actions are a list.

Runs standalone — `python tests/test_triggers.py` — with no torch and no
ComfyUI. What is pinned here is the contract the UI mirrors (`state.asleepHere`,
held to this file by `tests/test_triggers_mirror.py`):

  - the words are read off the line as typed — commas, spaces, case forgiven;
  - matched as a substring of the lowercased prose, so "smok" wakes on
    "smoking", and a file named outright by handle wakes whatever its words;
  - the cut happens wherever a cited member's files are gathered — the piece's
    pool on the way into a segment, and the card's own row — and before the
    mode, the labels and the limits are read;
  - it happens after `{a|b}` is chosen, so a word inside an alternative the
    seed passes over does not wake anything;
  - a member with every plate asleep and no words of their own is refused by
    name, with the words that would wake one.
"""

import layout

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "compile",
                   "variations", package="mmc")
subjects, compiler = _pkg.subjects, _pkg.compile

from harness import FAILURES, check, passed


def image(handle, **extra):
    return {"handle": handle, "kind": "image", "role": "reference",
            "filename": f"{handle}.png", **extra}


def video(handle, **extra):
    return {"handle": handle, "kind": "video", "role": "reference",
            "filename": f"{handle}.mp4", "track": "picture", **extra}


def request(prompt, assets, cast, **extra):
    return {"prompt": prompt, "assets": assets, "subjects": cast,
            "duration_s": 6, "aspect": "16:9", "short_edge": 768, **extra}


def build(prompt, assets, cast, **extra):
    return compiler.compile_request(request(prompt, assets, cast, **extra),
                                    image_size_lookup=lambda _f: (1500, 1000))


def expect_error(label, fn, fragment):
    try:
        fn()
    except compiler.CompileError as exc:
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {type(exc).__name__}: {exc}")
    else:
        FAILURES.append(f"{label}: expected a CompileError, got none")


# --- the words ---------------------------------------------------------------

check("the line is split on commas, trimmed and lowercased",
      subjects.split_triggers("Day, sun,    STUPID SPACES    "),
      ("day", "sun", "stupid spaces"))
check("blanks are dropped", subjects.split_triggers(" , ,smok,"), ("smok",))
check("nothing is nothing", subjects.split_triggers(""), ())

VERA = {"handle": "vera", "from": ["img-1", "img-2", "img-3"],
        "notes": {"img-2": "the red hat"},
        "triggers": {"img-2": "hat, cap", "img-3": "smok", "img-9": "gone"}}

_vera = subjects.parse([VERA])[0]
check("triggers are parsed by handle, words split, on files they claim",
      _vera.triggers, {"img-2": ("hat", "cap"), "img-3": ("smok",)})
check("a file with no words is never asleep",
      subjects.asleep(_vera, ["she waits"]), {"img-2", "img-3"})
check("a substring wakes it — smok on smoking",
      subjects.asleep(_vera, ["she is Smoking by the door"]), {"img-2"})
check("any of the words will do, in any case",
      subjects.asleep(_vera, ["a CAP pulled low"]), {"img-3"})
check("naming the file outright wakes it whatever its words",
      subjects.asleep(_vera, ["@img-3 shows her by the door"]), {"img-2"})
# The reporter asked for substrings, not words, and this is the price: "what"
# says "hat". Pinned so nobody "fixes" it into a word match without a test
# saying so — the sheet that wakes on "smok" is why it is a substring.
check("a substring is a substring — what wakes the hat",
      subjects.asleep(_vera, ["what she does"]), {"img-3"})
check("...but @img-30 is not @img-3",
      subjects.asleep(_vera, ["@img-30 by the door"]), {"img-2", "img-3"})
check("the words are read across every text handed in",
      subjects.asleep(_vera, ["she waits", "", "smoke curls on the soundtrack"]), {"img-2"})
check("awake is what a cast carries in, minus the sleepers",
      subjects.awake([_vera], ["hat"]), {"img-1", "img-2"})
check("a member with no triggers sleeps nowhere",
      subjects.asleep(subjects.parse([{"handle": "a", "from": ["img-1"]}])[0], [""]), set())

_junk = subjects.parse([{**VERA, "triggers": {"img-2": "  ,  ", "img-3": "smok"}}])[0]
check("an entry with no word in it is dropped", _junk.triggers, {"img-3": ("smok",)})
try:
    subjects.parse([{**VERA, "triggers": ["hat"]}])
    FAILURES.append("a list of triggers was not refused")
except subjects.SubjectError as exc:
    check("a list of triggers is refused by name", "triggers" in str(exc), True)

# --- the cut, on a card's own row --------------------------------------------

ROW = [image("img-1"), image("img-2"), image("img-3")]

_plain = build("@vera waits by the door.", ROW, [VERA])
check("with no word said, only the wordless plate is sent",
      [a.handle for a in _plain.ref_images], ["img-1"])
check("...and the definition cites what was sent",
      "<Subject 1> is the person in <Picture 1>." in _plain.prompt, True)

_hat = build("@vera, in her hat, waits.", ROW, [VERA])
check("the hat wakes the hat's plate", [a.handle for a in _hat.ref_images], ["img-1", "img-2"])
check("...with its words after its label",
      "<Picture 1> and <Picture 2> (the red hat)" in _hat.prompt, True)

_both = build("@vera, hat on, smokes.", ROW, [VERA])
check("two words, two plates", [a.handle for a in _both.ref_images], ["img-1", "img-2", "img-3"])

_muted = build("@vera, hat on, smokes.",
               [image("img-1"), image("img-2", enabled=False), image("img-3")], [VERA])
check("a plate muted by hand stays muted whatever the sentence says",
      [a.handle for a in _muted.ref_images], ["img-1", "img-3"])

_own = build("@vera waits. @img-3 shows how.", ROW, [VERA])
check("a plate named outright is in, words or no words",
      [a.handle for a in _own.ref_images], ["img-1", "img-3"])

# A file the user attached in their own right is nobody's to hold back.
_loose = build("a room.", [image("img-1")],
               [{"handle": "vera", "from": ["img-2"], "triggers": {"img-2": "hat"}}])
check("an unclaimed file is untouched", [a.handle for a in _loose.ref_images], ["img-1"])

# Sole claims only, as the uncited cut works: a plate two members share is in
# while it is awake on either of them.
_shared = build("@vera and @ben wait.", [image("img-1")],
                [{"handle": "vera", "from": ["img-1"], "triggers": {"img-1": "hat"}},
                 {"handle": "ben", "from": ["img-1"]}])
check("a shared plate stays while it is awake on either member",
      [a.handle for a in _shared.ref_images], ["img-1"])

# The limits are read after the cut — which is the whole reason the feature
# exists: thirty plates on one member, nine in any one shot.
MANY = [image(f"img-{n}") for n in range(1, 13)]
_crowd = {"handle": "vera", "from": [f"img-{n}" for n in range(1, 13)],
          "triggers": {f"img-{n}": f"word{n}" for n in range(2, 13)}}
_under = build("@vera, word4.", MANY, [_crowd])
check("twelve plates on one member fit a shot that wakes one",
      [a.handle for a in _under.ref_images], ["img-1", "img-4"])

# Every plate asleep, nothing else to stand on: refused with the words.
expect_error("a member with every plate asleep is refused by name",
             lambda: build("@vera waits.", [image("img-2"), image("img-3")],
                           [{"handle": "vera", "from": ["img-2", "img-3"],
                             "triggers": {"img-2": "hat, cap", "img-3": "smok"}}]),
             "waits for a word this shot does not say (cap, hat, smok)")
_described = build("@vera waits.", [image("img-2")],
                   [{"handle": "vera", "from": ["img-2"], "description": "a tall woman",
                     "triggers": {"img-2": "hat"}}])
check("...but one with words of their own is built out of them",
      ([a.handle for a in _described.ref_images], "<Subject 1> is a tall woman." in _described.prompt),
      ([], True))

# --- the cut, on the way out of the pool ---------------------------------------

_pool = compiler.compile_timeline({
    "prompt": "", "assets": ROW, "subjects": [VERA],
    "segments": [{"prompt": "@vera waits.", "assets": [], "loras": [], "duration_s": 6},
                 {"prompt": "@vera lights a cigarette, smoking.", "assets": [], "loras": [], "duration_s": 6}],
})
check("a pool plate rides into the segment that says its word",
      [[a.handle for a in p.ref_images] for p in _pool], [["img-1"], ["img-1", "img-3"]])

# --- after the seed has chosen -------------------------------------------------

_varied = {"prompt": "", "assets": ROW, "subjects": [VERA],
           "segments": [{"prompt": "@vera {waits|smokes}.", "assets": [], "loras": [],
                         "duration_s": 6}]}
outcomes = set()
for seed in range(12):
    chosen = compiler.varied_piece(_varied, seed)
    outcomes.add(tuple(a.handle for a in compiler.compile_timeline(chosen)[0].ref_images))
check("a word inside an alternative wakes the plate only when the seed takes it",
      outcomes, {("img-1",), ("img-1", "img-3")})

# --- their actions are a list ---------------------------------------------------

_swing = subjects.parse([{"handle": "ana", "from": ["img-1"], "motion": "vid-1"}])[0]
check("a bare string is read as the list it meant", _swing.motion, ("vid-1",))
_two = subjects.parse([{"handle": "ana", "from": ["img-1"], "motion": ["vid-1", "img-2"],
                        "notes": {"vid-1": "the swing", "img-2": "the left hand"}}])[0]
check("two actions are two files of theirs", _two.files, ["img-1", "vid-1", "img-2"])
_acted = build("@ana swings.", [image("img-1"), video("vid-1"), image("img-2")],
               [{"handle": "ana", "from": ["img-1"], "motion": ["vid-1", "img-2"],
                 "notes": {"vid-1": "the swing", "img-2": "the left hand"}}])
check("...and the definition names both",
      "whose motion comes from <Video 1> (the swing) and <Picture 2> (the left hand)"
      in _acted.prompt, True)
check("...and the retention line follows both",
      "the movement in <Video 1> (the swing) and <Picture 2> (the left hand), its path"
      in _acted.prompt, True)
_worded = build("@ana lights up, smoking.", [image("img-1"), video("vid-1"), image("img-2")],
                [{"handle": "ana", "from": ["img-1"], "motion": ["vid-1", "img-2"],
                  "triggers": {"vid-1": "swing", "img-2": "smok"}}])
check("an action sleeps on its word like a look does",
      [a.handle for a in _worded.ref_images] + [a.handle for a in _worded.ref_videos],
      ["img-1", "img-2"])
check("a merged pass writes the list back as a list",
      compiler._subject_dict(_two).get("motion"), ["vid-1", "img-2"])
check("...and the words as the line they were typed as",
      compiler._subject_dict(_vera).get("triggers"),
      {"img-2": "hat, cap", "img-3": "smok"})

passed("a plate wakes on its word, and their actions are a list")
