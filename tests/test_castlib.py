"""A kept cast member, landed on a piece without a browser: `creator/castlib.py`.

    python3 tests/test_castlib.py

Runs standalone — no torch, no ComfyUI. The library's two files are written
here in the shape `web/creator/presets.js` stores them, and what `land` makes
of a member is put through the compiler and the chat's piece builder, since
"their LoRA goes on with their name" is those two's to say.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import check, passed  # noqa: E402

pkg = layout.load("canvas", "registry", "contextir", "subjects", "compile", "prompting",
                  "chat", "castlib")
castlib, chat, compiler = pkg.castlib, pkg.chat, pkg.compile

LORA = {"name": "people/anna_v3.safetensors", "strength": 0.85, "triggers": ["ohwx anna"]}
INDEX = {"version": 1, "presets": [
    {"id": "a1", "name": "anna", "scope": "cast", "updated": 5},
    {"id": "b2", "name": "ben", "scope": "cast", "updated": 9},
    {"id": "c3", "name": "anna", "scope": "cast", "updated": 2},
    {"id": "s4", "name": "noir", "scope": "style", "updated": 7},
    {"id": "x5", "name": "shipped", "scope": "cast", "builtin": True},
]}
ANNA = {"version": 1, "id": "a1", "data": {"cast": {
    "handle": "anna", "takes": "person", "description": "a tall woman in a green coat",
    "files": [
        {"slot": "from", "filename": "anna_face.png", "kind": "image", "ref_size": "max",
         "note": "her face, front-lit"},
        {"slot": "from", "filename": "anna_hat.png", "kind": "image", "trigger": "hat, cap"},
        {"slot": "voice", "filename": "anna.mp3", "kind": "audio"},
    ],
    "wears": {"h3": {"loras": [LORA]}},
}}}

rows = castlib.roster(INDEX)
check("the roster is the kept people, newest first",
      [row["id"] for row in rows], ["b2", "a1", "c3"])
check("a prompt cites them by name, in any case, once, and the newer of two",
      [row["id"] for row in castlib.cited("@Anna meets @ben, and @anna waves at @pic-1 and @carol", rows)],
      ["a1", "b2"])
check("an address is nobody", castlib.cited("write to me@anna.example", rows), [])
check("a body with nobody in it is nobody", castlib.member({"data": {"look": {}}}), None)

stored = castlib.member(ANNA)
check("a listing says what is behind them",
      castlib.summary(rows[1], stored),
      {"name": "anna", "takes": "person", "description": "a tall woman in a green coat",
       "pictures": 2, "voice": True, "loras": ["h3"]})

piece = {"assets": [{"handle": "ref-1", "kind": "image", "role": "reference",
                     "filename": "anna_hat.png", "ref_size": "match"}]}
anna = castlib.land(stored, piece)
check("their files land on the shelf, and one already there is used",
      [(a["handle"], a["filename"]) for a in piece["assets"]],
      [("ref-1", "anna_hat.png"), ("ref-2", "anna_face.png"), ("ref-3", "anna.mp3")])
check("each narrowed to what its slot says",
      [a.get("takes") for a in piece["assets"]], ["person", "person", "voice"])
check("the subject claims them by handle, in the order they were kept",
      (anna["from"], anna["voice"]), (["ref-2", "ref-1"], "ref-3"))
check("with the words kept on each file",
      (anna["notes"], anna["triggers"]),
      ({"ref-2": "her face, front-lit"}, {"ref-1": "hat, cap"}))
check("and the baseline rows a card is seeded with",
      ([f["attr"] for f in anna["features"]], anna["seeded"]),
      (["face", "hair", "build", "clothing"], True))
check("somebody of the same name is kept apart",
      castlib.land(stored, piece)["handle"], "anna_2")

# What the name then carries into a clip.
landed = {}
castlib.land(stored, landed)
payloads = compiler.timeline_payloads(
    {"version": 2, "family": "h3", "prompt": "", "aspect": "16:9", "short_edge": 768,
     "segments": [{"prompt": "@anna, in her hat, walks in.", "duration_s": 6},
                  {"prompt": "an empty room.", "duration_s": 6}], **landed})
check("citing them puts their LoRA on that shot and no other",
      [[entry["name"] for entry in payload["request"].get("loras") or []] for payload in payloads],
      [[LORA["name"]], []])
check("with their trigger words in front of its prompt",
      compiler.compile_segment(payloads[0]).body.startswith("ohwx anna, "), True)

entries = chat.cast_entries(landed)
check("and the room reads them off the same blob, for a still",
      (entries[0]["name"], sorted(entries[0]["files"]), entries[0]["wears"]),
      ("anna", ["ref-1", "ref-2", "ref-3"], {"h3": {"loras": [LORA]}}))
action = chat.validate({"act": "render", "kind": "video", "prompt": "@ANNA walks in."},
                       [], cast=[s["handle"] for s in landed["subjects"]])
check("a name written in another case leaves in theirs", action["prompt"], "@anna walks in.")

passed("a kept cast member lands on a piece as the library's own page lands them")
