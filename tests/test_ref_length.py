"""A card can be made as long as the reference it is generated against.

Three things have to hold for that offer to be worth making, and none of them
is visible from either side alone:

  - the length the pill writes is a real duration, not a rounded second, and it
    compiles back to the frame count it was chosen from (`canvas.match_seconds`,
    covered here through `compile.py` rather than in the mirror test, because it
    is the compiler that has to accept a fractional `duration_s`);
  - every clip can be matched to, a cast member's voice and the clip they stand
    in for included — those arrive narrowed to "voice" and "edit", which is
    exactly where a rule about takes would have withheld the offer;
  - the length itself is the trim's where there is one, and the file's otherwise.

    python3 tests/test_ref_length.py

Skips the JS half if node is not installed.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys

import layout
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
MIRROR = layout.js("state.js")

package = types.ModuleType("mmcref")
package.__path__ = [layout.PY_ROOT]
sys.modules["mmcref"] = package
for name in ("canvas", "contextir", "subjects", "compile"):
    spec = importlib.util.spec_from_file_location(f"mmcref.{name}", layout.py(name))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"mmcref.{name}"] = module
    setattr(package, name, module)
    spec.loader.exec_module(module)
canvas = sys.modules["mmcref.canvas"]
compiler = sys.modules["mmcref.compile"]

from harness import FAILURES, check, passed

# ---- the fractional duration a match writes ---------------------------------

# 9.33 s of music, 6.6 s of dialogue, a 12 s clip: the lengths a reference
# actually comes in, none of them a whole second.
for length in (2.5, 6.6, 9.33, 12.0, 41.7):
    matched = canvas.match_seconds(length, canvas.H3)
    compiled = compiler.compile_request({"prompt": "a courier waits", "duration_s": matched})
    check(f"{length}s matched compiles to its own count",
          compiled.frames, canvas.frames_for_seconds(length, canvas.H3))
    # And it is the nearest count there is, which is the claim the pill makes.
    target = length * canvas.H3.fps
    nearest = min(canvas.legal_frame_counts(canvas.H3), key=lambda n: abs(n - target))
    check(f"{length}s matched is the nearest count", compiled.frames, nearest)

# The pill's own range still holds: a three-minute cue cannot ask for a card the
# UI could not then show.
check("a long cue clamps", canvas.match_seconds(180, canvas.H3),
      canvas.match_seconds(canvas.H3.max_seconds, canvas.H3))
check("a fragment clamps", canvas.match_seconds(0.2, canvas.H3),
      canvas.match_seconds(canvas.H3.min_seconds, canvas.H3))

# ---- the JS half ------------------------------------------------------------

if shutil.which("node") is None:
    passed("a matched card compiles to the reference's own frame count "
           "(skipped the mirror: node is not installed)")

SCRIPT = """
const S = await import(process.argv[1]);
const shot = (assets, duration_s) => ({ prompt: "", assets, loras: [], duration_s });
const ref = (extra) => ({ handle: "aud-1", kind: "audio", role: "reference", ...extra });
const lengths = { "song.wav": 9.33, "plate.mp4": 12, "quiet.wav": 3 };
const lengthOf = (name) => lengths[name] ?? null;

const out = { led: S.LENGTH_LED, cases: {} };
const record = (label, state) => {
  const match = S.lengthMatch(state, lengthOf);
  out.cases[label] = match && { handle: match.asset.handle, seconds: match.seconds,
                                duration: match.duration, matched: match.matched };
};

// The whole file, and the same file trimmed: the trim is the length.
record("whole", shot([ref({ filename: "song.wav" })], 6));
record("trimmed", shot([ref({ filename: "song.wav", trim: { start: 2, end: 5 } })], 6));
// Already matched, and matched through a second that is not the stored one:
// agreement is about the frame count, not about the number on the pill.
record("matched", shot([ref({ filename: "song.wav" })], 9.42));
record("matched from a whole second", shot([ref({ filename: "song.wav" })], 9.33));
// However the reference is narrowed, it still occupies the card's time.
record("voice", shot([ref({ filename: "song.wav", takes: "voice" })], 6));
record("copy", shot([ref({ filename: "song.wav", takes: "copy" })], 6));
// A muted reference is not a reference of this render.
record("muted", shot([ref({ filename: "song.wav", enabled: false })], 6));
// Nothing to say about a card of stills, or one with no references at all.
record("image", shot([{ handle: "img-1", kind: "image", role: "reference",
                        filename: "a.png" }], 6));
record("bare", shot([], 6));
// A length nobody has probed yet.
record("unprobed", shot([ref({ filename: "unknown.wav" })], 6));
// Two clips: the longest, because that is the one being cut.
record("two", shot([ref({ filename: "quiet.wav" }),
                    ref({ handle: "vid-1", kind: "video", filename: "plate.mp4" })], 6));
// ...unless the shorter one is what the card is actually timed by: a line of
// dialogue against a long plate the shot only takes a look from.
record("led", shot([ref({ filename: "quiet.wav", takes: "copy" }),
                    ref({ handle: "vid-1", kind: "video", filename: "plate.mp4",
                          takes: "style" })], 6));

// A cast member on a piece: their files are in the pool and reach this card
// because its sentence names them. Their voice arrives narrowed to "voice" and
// the clip they stand in for to "edit" — the two the offer used to miss.
const anna = { handle: "anna", takes: "person", voice: "aud-2", replaces: ["vid-2"] };
const piece = {
  ...shot([], 6),
  prompt: "@anna turns to the camera",
  cast: [anna],
  pool: [{ handle: "aud-2", kind: "audio", role: "reference",
           filename: "song.wav", takes: "voice" },
         { handle: "vid-2", kind: "video", role: "reference",
           filename: "plate.mp4", takes: "edit" }],
  globalTexts: { prompt: "", soundscape: "", music: "" },
};
record("cast voice and stand-in", piece);
record("cast, uncited", { ...piece, prompt: "an empty street" });
record("cast voice alone", { ...piece, pool: [piece.pool[0]] });
console.log(JSON.stringify(out));
"""

mirror = layout.run(SCRIPT, MIRROR)

# The tiebreak names takes that exist, or it silently never fires.
for kind, takes in mirror["led"].items():
    known = compiler.TAKES[kind]
    for take in takes:
        if take not in known:
            FAILURES.append(f"LENGTH_LED.{kind} names {take!r}, which compile.py "
                            f"does not define for {kind}")

cases = mirror["cases"]
check("whole file", cases["whole"],
      {"handle": "aud-1", "seconds": 9.33, "duration": 9.42, "matched": False})
check("trimmed", cases["trimmed"],
      {"handle": "aud-1", "seconds": 3, "duration": 3.04, "matched": False})
check("matched", cases["matched"]["matched"], True)
check("matched from a whole second", cases["matched from a whole second"]["matched"], True)
check("a voice reference can be matched to", cases["voice"]["duration"], 9.42)
check("so can a copied one", cases["copy"]["duration"], 9.42)
check("muted", cases["muted"], None)
check("stills", cases["image"], None)
check("no references", cases["bare"], None)
check("unprobed", cases["unprobed"], None)
check("the longest of two", cases["two"]["handle"], "vid-1")
check("...unless the shorter one is what the shot is timed by",
      cases["led"]["handle"], "aud-1")
# The whole of the reported failure: a piece whose card names @anna is generated
# against her voice and the clip she stands in, and both were unmatchable.
check("a cast member's files reach the card that names them — the longer of "
      "the two here, which is the one being cut",
      cases["cast voice and stand-in"]["handle"], "vid-2")
check("...their voice on its own just as much",
      cases["cast voice alone"]["handle"], "aud-2")
check("...and none of it while the card does not name them",
      cases["cast, uncited"], None)

passed("a matched card compiles to the reference's own frame count")
