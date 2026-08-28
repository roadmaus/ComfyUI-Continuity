"""`state.js` still agrees with `subjects.py` about the cast.

Three things are written down twice and have to stay identical, because the band
decides what you *can* say and the compiler decides what is *sent*:

  - the four takes a subject may have, and the four relationship markers;
  - the baseline attributes each take is made of, which the shelf seeds a card's
    feature rows from and the compiler composes the retention line out of. The
    two lists disagreeing would mean a card whose rows say one thing and a
    prompt that says another about the same person;
  - what a name is allowed to be, which is the whole of why `@anna` is safe to
    be a word — the two sides recognising different names would mean a chip in
    the band pointing at a subject the compiler never resolves;
  - which files a subject claims, which is what a citation drags into a shot.
    Disagree here and the band shows a shot carrying references the payload does
    not, or the payload carries some the band never showed.

    python3 tests/test_cast_mirror.py

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")

subjects = layout.load("subjects").subjects


# The names put through both sides' pattern are the ones the distinction turns
# on: a word, a word with a digit, the file shape, the empty string, and the
# things a careless paste produces.
NAMES = ["anna", "Anna", "a", "anna_2", "anna2", "img-1", "anna-1", "2anna",
         "", "anna belle", "anna.belle", "@anna", "a" * 32, "a" * 33]

# Every arrangement of the optional halves, so `files` is compared where each of
# them is present and absent.
CASES = [
    {"handle": "a", "from": ["ref-1"]},
    {"handle": "a", "from": ["ref-1", "ref-2"]},
    {"handle": "a", "from": ["ref-1"], "motion": "ref-3"},
    {"handle": "a", "from": ["ref-1"], "voice": "ref-4"},
    {"handle": "a", "from": ["ref-1"], "motion": "ref-3", "voice": "ref-4"},
    {"handle": "a", "from": [], "replaces": "ref-3"},
    # A file named twice is claimed once, in citation order.
    {"handle": "a", "from": ["ref-1", "ref-1"], "motion": "ref-1"},
    # ...and the features, which are what the marker is now derived from. Every
    # arrangement of them, because the derivation is what the two sides have to
    # agree on: a marker the shelf shows and the compiler does not write is the
    # same class of lie the picker was.
    {"handle": "a", "from": ["ref-1"], "features": ["long dark hair"]},
    {"handle": "a", "from": ["ref-1"],
     "features": [{"is": "long dark hair"}, {"is": "a blue cardigan"}]},
    {"handle": "a", "from": ["ref-1"],
     "features": [{"is": "a blue cardigan", "instead": "a red waxed jacket"}]},
    {"handle": "a", "from": ["ref-1"],
     "features": [{"is": "long dark hair"},
                  {"is": "a blue cardigan", "instead": "a red waxed jacket"}]},
    # A changed feature and a place taken: the transfer leads, because it is the
    # relationship whatever else moves.
    {"handle": "a", "from": ["ref-1"], "replaces": "ref-3",
     "features": [{"is": "a blue cardigan", "instead": "a red waxed jacket"}]},
    # An empty row is what the editor writes the moment somebody presses "add a
    # feature", and an `instead` with no feature to be instead *of* goes with it.
    {"handle": "a", "from": ["ref-1"],
     "features": [{"is": "  "}, {"is": "", "instead": "a red waxed jacket"},
                  {"is": " long dark hair "}]},
    # The override still wins, and it is the only way to reach weak_reference.
    {"handle": "a", "from": ["ref-1"], "relationship": "weak_reference",
     "features": [{"is": "a blue cardigan", "instead": "a red waxed jacket"}]},
    # ...and the seeded rows, which is what a card holds the moment somebody is
    # cast. An untouched one survives on its attribute alone — this is the row
    # that used to be dropped for having no text — and the described, the
    # changed and the dropped are the three things you can do to it.
    {"handle": "a", "from": ["ref-1"],
     "features": [{"attr": "face"}, {"attr": "hair"}, {"attr": "build"},
                  {"attr": "clothing"}]},
    {"handle": "a", "from": ["ref-1"],
     "features": [{"attr": "face"}, {"attr": "hair", "is": "long dark hair"},
                  {"attr": "build"}, {"attr": "clothing"}]},
    {"handle": "a", "from": ["ref-1"],
     "features": [{"attr": "face"}, {"attr": "hair", "instead": "a short blonde bob"},
                  {"attr": "build"}, {"attr": "clothing"}]},
    {"handle": "a", "from": ["ref-1"],
     "features": [{"attr": "face"}, {"attr": "build"}, {"attr": "clothing"}]},
    # Seeded rows and a feature somebody typed, which is the arrangement the
    # single sentence used to get wrong: the typed one replaced the baseline
    # instead of joining it.
    {"handle": "a", "from": ["ref-1"],
     "features": [{"attr": "face"}, {"attr": "hair"}, {"attr": "build"},
                  {"attr": "clothing"}, {"is": "a red leather jacket"}]},
]

SCRIPT = """
const s = await import(process.argv[1]);
const names = JSON.parse(process.argv[2]);
const cases = JSON.parse(process.argv[3]);
console.log(JSON.stringify({
  takes: s.SUBJECT_TAKES,
  markers: s.SUBJECT_MARKERS,
  names: Object.fromEntries(names.map((n) => [n, s.SUBJECT_HANDLE_RE.test(n)])),
  files: cases.map((c) => s.subjectFiles(c)),
  features: cases.map((c) => s.subjectFeatures(c).map((f) => [f.is, f.instead, f.attr ?? ""])),
  attributes: s.SUBJECT_ATTRIBUTES,
  seeded: Object.fromEntries(s.SUBJECT_TAKES.map((t) => [t, s.seedFeatures(t)])),
  derived: cases.map((c) => s.subjectMarker(c)),
  // The citation pattern, exercised rather than compared: a regex written twice
  // is never textually equal and the only thing that matters is what it matches.
  cites: [
    [...("@anna looks at @ben".matchAll(s.subjectCitationRe([{handle: "anna"}, {handle: "ben"}])))]
      .map((m) => m[1]),
    [...("@annabelle walks".matchAll(s.subjectCitationRe([{handle: "anna"}])))].map((m) => m[1]),
    [...("@carol walks".matchAll(s.subjectCitationRe([{handle: "anna"}])))].map((m) => m[1]),
    s.subjectCitationRe([]) === null,
  ],
  // ---- what a file lending itself to somebody is narrowed to ---------------
  //
  // Not a mirror — `subjects.py` never sees this, because by the time it does
  // the narrowing is already a stored field on the asset. It is here because it
  // is the other half of the same idea: the shelf says who somebody is, and the
  // file behind her has to say the same thing to the model.
  narrowing: (() => {
    const image = (handle, takes) => ({ handle, kind: "image", role: "reference",
                                        filename: `${handle}.png`, ...(takes ? { takes } : {}) });
    const clip = (handle) => ({ handle, kind: "video", role: "reference",
                                filename: `${handle}.mp4`, track: "picture" });
    const sound = (handle) => ({ handle, kind: "audio", role: "reference",
                                 filename: `${handle}.wav` });

    // Her looks, her movement, her voice and the place she takes, each narrowed
    // to the word its slot means.
    const her = { handle: "anna", takes: "person", from: ["img-1"],
                  motion: "vid-1", voice: "aud-1", replaces: "vid-2" };
    const assets = [image("img-1"), clip("vid-1"), sound("aud-1"), clip("vid-2")];
    s.inheritTakes(her, assets);
    const slots = assets.map((a) => a.takes ?? "full").join(",");

    // A narrowing somebody chose is theirs. "scene" is not what a person
    // reference would be given, which is the point.
    const chosen = [image("img-1", "scene")];
    s.inheritTakes({ handle: "anna", takes: "person", from: ["img-1"] }, chosen);

    // …until she stops being a person, where the narrowing this rule put there
    // moves with her and the one somebody chose still does not.
    const moved = [image("img-1", "person"), image("img-2", "style")];
    s.inheritTakes({ handle: "loft", takes: "scene", from: ["img-1", "img-2"] },
                   moved, { over: "person" });

    // A blob written before any of this existed, repaired on the way in.
    const loaded = s.parseTimeline(JSON.stringify({
      version: 2, prompt: "@anna waits", models: {},
      subjects: [{ handle: "anna", takes: "person", from: ["img-1"] }],
      segments: [{ prompt: "@anna waits", duration_s: 6, loras: [],
                   assets: [image("img-1")] }],
    }));

    return {
      slots,
      chosen: chosen[0].takes,
      moved: moved.map((a) => a.takes).join(","),
      onLoad: loaded.segments[0].assets[0].takes,
    };
  })(),
}));
"""

reflected = layout.run(SCRIPT, MIRROR, NAMES, CASES)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: js {got!r}, py {want!r}")


check("the subject takes match", reflected["takes"], list(subjects.TAKES))
# The baseline. `subjects.ATTRIBUTES` carries a prose fragment beside each key
# because the compiler has to write the list into a sentence; the shelf only
# needs the keys, which are what it labels a row and stores in the blob. So the
# keys are the mirror and the fragments are the compiler's alone.
for takes in subjects.TAKES:
    check(f"the attributes a {takes} is made of",
          reflected["attributes"][takes],
          [key for key, _ in subjects.ATTRIBUTES[takes][1]])
    # And what casting somebody actually writes: a row per attribute, in order,
    # which is what makes an untouched card compile to the sentence a card with
    # no rows at all always compiled to.
    check(f"...and what seeding a {takes} writes",
          [f["attr"] for f in reflected["seeded"][takes]],
          [key for key, _ in subjects.ATTRIBUTES[takes][1]])
check("the relationship markers match", reflected["markers"], list(subjects.MARKERS))

for name in NAMES:
    check(f"{name!r} is a name, or is not",
          reflected["names"][name], bool(subjects.HANDLE_RE.match(name)))

for case, files in zip(CASES, reflected["files"]):
    check(f"what {case} claims",
          files, list(subjects.parse([case])[0].files))

# The features, and the marker they decide. The shelf shows the marker while you
# type the features, and the compiler writes it — so the two deriving it apart
# is the failure this pair of rows exists for.
for case, features in zip(CASES, reflected["features"]):
    check(f"the features of {case}",
          [tuple(f) for f in features],
          [(f.text, f.instead, f.attr) for f in subjects.parse([case])[0].features])
for case, marker in zip(CASES, reflected["derived"]):
    check(f"the marker {case} derives",
          marker, subjects.parse([case])[0].relationship)

# The pattern, by what it does rather than by how it is written.
cast = subjects.parse([{"handle": "anna", "from": ["ref-1"]},
                       {"handle": "ben", "from": ["ref-2"]}])
one = subjects.parse([{"handle": "anna", "from": ["ref-1"]}])
check("both names are cited",
      reflected["cites"][0], subjects.citation_re(cast).findall("@anna looks at @ben"))
check("a name inside a longer word is not",
      reflected["cites"][1], subjects.citation_re(one).findall("@annabelle walks"))
check("and neither is an undeclared one",
      reflected["cites"][2], subjects.citation_re(one).findall("@carol walks"))
narrowing = reflected["narrowing"]
check("a file hung on somebody is narrowed to what its slot means",
      narrowing["slots"], "person,motion,voice,edit")
check("...and a narrowing somebody chose is left alone",
      narrowing["chosen"], "scene")
check("...while the one this rule put there follows her when she changes",
      narrowing["moved"], "scene,style")
check("a piece written before any of this is repaired on the way in",
      narrowing["onLoad"], "person")

check("an empty cast has no pattern at all",
      reflected["cites"][3], subjects.citation_re([]) is None)

passed("state.js mirrors the cast: takes, markers, names, files, features and citations")
