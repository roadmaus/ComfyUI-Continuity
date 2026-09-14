"""A LoRA hung on a cast member goes on with them (discussion #82).

The stack entry lives on the subject and is merged into a shot's stack only
while the shot cites them, with its trigger words in front of that shot's
prompt and no other. Runs standalone, like `test_subjects.py`.

    python3 tests/test_cast_lora.py
"""

import os
import sys

import layout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "registry", "contextir", "subjects", "compile")
subjects, compiler = _pkg.subjects, _pkg.compile


def image(handle):
    return {"handle": handle, "kind": "image", "role": "reference", "filename": f"{handle}.png"}


def piece(*segments, **extra):
    return {"version": 2, "prompt": "", "segments": list(segments),
            "aspect": "16:9", "short_edge": 768, **extra}


def shot(prompt, **extra):
    return {"prompt": prompt, "duration_s": 6, **extra}


ANNA_LORA = {"name": "people/anna_v3.safetensors", "strength": 0.85, "triggers": ["ohwx anna"]}
GRAIN = {"name": "film_grain.safetensors", "strength": 0.6, "triggers": ["grainy"]}


def names(payload):
    return [entry["name"] for entry in payload["request"].get("loras") or []]


# ---- parsing ----------------------------------------------------------------

_anna = subjects.parse([{"handle": "anna", "from": ["ref-1"], "loras": [ANNA_LORA]}])[0]
check("the entry is kept in the stack's own shape",
      _anna.loras, ({"name": "people/anna_v3.safetensors", "strength": 0.85,
                     "triggers": ["ohwx anna"]},))
check("a typed line of words is read as the list it means, casing kept",
      subjects.parse([{"handle": "a", "from": ["ref-1"],
                       "loras": [{"name": "x", "triggers": "OHWX anna, Blue"}]}])[0].loras[0]["triggers"],
      ["OHWX anna", "Blue"])
check("an entry with no name is a slot nobody filled",
      subjects.parse([{"handle": "a", "from": ["ref-1"], "loras": [{"strength": 1}]}])[0].loras, ())
check("a muted entry's words are not theirs",
      subjects.parse([{"handle": "a", "from": ["ref-1"],
                       "loras": [dict(ANNA_LORA, enabled=False), GRAIN]}])[0].lora_words,
      ["grainy"])

try:
    subjects.parse([{"handle": "a", "loras": [{"name": "x"}]}])
    FAILURES.append("a LoRA with no word counts as something behind them")
except subjects.SubjectError as exc:
    check("...and the refusal offers the way out", "trigger word" in str(exc), True)

_worded = subjects.parse([{"handle": "anna", "loras": [ANNA_LORA]}])
check("a LoRA with a trigger word is enough to stand behind a name", len(_worded), 1)
check("...and the definition binds the label to the word",
      subjects.definitions(_worded, {}), "<Subject 1> is the person, ohwx anna.")

# Trimming unavailable files must leave a worded LoRA intact. It is still the
# member's appearance, even when the last reference picture is muted.
_trimmed = compiler.compile_request({
    "prompt": "@anna walks in.",
    "assets": [dict(image("ref-1"), enabled=False)],
    "subjects": [{"handle": "anna", "from": ["ref-1"], "loras": [ANNA_LORA]}]})
check("losing the last picture preserves a worded LoRA's definition",
      "<Subject 1> is the person, ohwx anna." in _trimmed.prompt, True)
_survivor = subjects.here(
    subjects.parse([{"handle": "anna", "from": ["ref-1"], "loras": [ANNA_LORA]}]), [])
check("trimming files preserves the LoRA stack itself", _survivor[0].loras, (ANNA_LORA,))

for _raw in ({"handle": "anna"}, {"handle": "anna", "from": ["ref-1"]}):
    try:
        compiler.compile_request({
            "prompt": "@anna walks in.", "assets": [],
            "subjects": [{**_raw, "features": [{"attr": "face"}],
                          "loras": [dict(ANNA_LORA, enabled=False)]}]})
        FAILURES.append("a muted LoRA and seeded attributes define a subject without files")
    except (subjects.SubjectError, compiler.CompileError):
        pass

# ---- through a timeline -----------------------------------------------------

_piece = piece(shot("@anna walks in."), shot("an empty room."), shot("@anna sits down."),
               assets=[image("ref-1")],
               loras=[GRAIN],
               subjects=[{"handle": "anna", "from": ["ref-1"], "loras": [ANNA_LORA]}])
_payloads = compiler.timeline_payloads(_piece)

check("her LoRA rides into the shots that cite her, after the piece's",
      [names(p) for p in _payloads],
      [["film_grain.safetensors", "people/anna_v3.safetensors"],
       ["film_grain.safetensors"],
       ["film_grain.safetensors", "people/anna_v3.safetensors"]])
check("...at the strength she wears it",
      _payloads[0]["request"]["loras"][1]["strength"], 0.85)
check("the cast dict the segment node re-parses carries the entry",
      _payloads[0]["request"]["subjects"][0]["loras"], [ANNA_LORA])

_first = compiler.compile_segment(_payloads[0])
_second = compiler.compile_segment(_payloads[1])
check("her trigger word is in front of the shot she is in",
      _first.body.startswith("grainy, ohwx anna, "), True)
check("...and not in front of the one she is not",
      (_second.body.startswith("grainy, "), "ohwx" in _second.body), (True, False))

# A shot naming the same file is the more specific entry and wins.
_shot_own = piece(shot("@anna walks in.", loras=[dict(ANNA_LORA, strength=0.4)]),
                  assets=[image("ref-1")],
                  subjects=[{"handle": "anna", "from": ["ref-1"], "loras": [ANNA_LORA]}])
check("a shot's own entry for the same file replaces hers",
      [(e["name"], e["strength"]) for e in compiler.timeline_payloads(_shot_own)[0]["request"]["loras"]],
      [("people/anna_v3.safetensors", 0.4)])

# A global citation is a citation in every shot.
_global = piece(shot("she walks in."), shot("she sits down."),
                prompt="@anna is the only person here.",
                assets=[image("ref-1")],
                subjects=[{"handle": "anna", "from": ["ref-1"], "loras": [ANNA_LORA]}])
check("cited globally, her LoRA is on every shot",
      [names(p) for p in compiler.timeline_payloads(_global)],
      [["people/anna_v3.safetensors"]] * 2)

# One pass: the merged request's stack holds it once.
_single = compiler.single_payload(piece(
    shot("@anna walks in."), shot("@anna sits down.", merge=True),
    assets=[image("ref-1")],
    subjects=[{"handle": "anna", "from": ["ref-1"], "loras": [ANNA_LORA]}]))
check("a merged pass wears it once", names(_single), ["people/anna_v3.safetensors"])

# A piece whose cast wears nothing compiles to the bytes it always did.
_plain = piece(shot("@anna walks in."), assets=[image("ref-1")],
               subjects=[{"handle": "anna", "from": ["ref-1"]}])
check("a cast wearing nothing leaves the request as it was",
      (compiler.timeline_payloads(_plain)[0]["request"]["loras"],
       "loras" in compiler.timeline_payloads(_plain)[0]["request"]["subjects"][0]),
      ([], False))

# A muted entry rides along but is not patched, the same as on the piece.
_muted = piece(shot("@anna walks in."), assets=[image("ref-1")],
               subjects=[{"handle": "anna", "from": ["ref-1"],
                          "loras": [dict(ANNA_LORA, enabled=False)]}])
_muted_first = compiler.compile_segment(compiler.timeline_payloads(_muted)[0])
check("a muted LoRA contributes no words", "ohwx" in _muted_first.body, False)

passed("a cast member's LoRA is patched onto their shots and worded there")
