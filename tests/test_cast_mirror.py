"""`state.js` still agrees with `subjects.py` about the cast.

Three things are written down twice and have to stay identical, because the band
decides what you *can* say and the compiler decides what is *sent*:

  - the four takes a subject may have, and the four relationship markers;
  - what a name is allowed to be, which is the whole of why `@anna` is safe to
    be a word — the two sides recognising different names would mean a chip in
    the band pointing at a subject the compiler never resolves;
  - which files a subject claims, which is what a citation drags into a shot.
    Disagree here and the band shows a shot carrying references the payload does
    not, or the payload carries some the band never showed.

    python3 tests/test_cast_mirror.py

Skips itself if node is not installed.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "js", "minimax_creator", "state.js")

if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)


def _load():
    package = types.ModuleType("mmc")
    package.__path__ = [ROOT]
    sys.modules["mmc"] = package
    spec = importlib.util.spec_from_file_location("mmc.subjects", os.path.join(ROOT, "subjects.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["mmc.subjects"] = module
    setattr(package, "subjects", module)
    spec.loader.exec_module(module)
    return module


subjects = _load()

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

proc = subprocess.run(
    ["node", "--input-type=module", "-e", SCRIPT, "--",
     MIRROR, json.dumps(NAMES), json.dumps(CASES)],
    capture_output=True, text=True)
if proc.returncode != 0:
    print(f"node failed:\n{proc.stderr}")
    sys.exit(1)
mirror = json.loads(proc.stdout)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: js {got!r}, py {want!r}")


check("the subject takes match", mirror["takes"], list(subjects.TAKES))
check("the relationship markers match", mirror["markers"], list(subjects.MARKERS))

for name in NAMES:
    check(f"{name!r} is a name, or is not",
          mirror["names"][name], bool(subjects.HANDLE_RE.match(name)))

for case, files in zip(CASES, mirror["files"]):
    check(f"what {case} claims",
          files, list(subjects.parse([case])[0].files))

# The pattern, by what it does rather than by how it is written.
cast = subjects.parse([{"handle": "anna", "from": ["ref-1"]},
                       {"handle": "ben", "from": ["ref-2"]}])
one = subjects.parse([{"handle": "anna", "from": ["ref-1"]}])
check("both names are cited",
      mirror["cites"][0], subjects.citation_re(cast).findall("@anna looks at @ben"))
check("a name inside a longer word is not",
      mirror["cites"][1], subjects.citation_re(one).findall("@annabelle walks"))
check("and neither is an undeclared one",
      mirror["cites"][2], subjects.citation_re(one).findall("@carol walks"))
narrowing = mirror["narrowing"]
check("a file hung on somebody is narrowed to what its slot means",
      narrowing["slots"], "person,motion,voice,edit")
check("...and a narrowing somebody chose is left alone",
      narrowing["chosen"], "scene")
check("...while the one this rule put there follows her when she changes",
      narrowing["moved"], "scene,style")
check("a piece written before any of this is repaired on the way in",
      narrowing["onLoad"], "person")

check("an empty cast has no pattern at all",
      mirror["cites"][3], subjects.citation_re([]) is None)

passed("state.js mirrors the cast: takes, markers, names, files and citations")
