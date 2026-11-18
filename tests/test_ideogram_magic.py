"""Ideogram 4.0's magic prompt: the request, the caption, and where it goes.

    python tests/test_ideogram_magic.py

Pure: no model, no ComfyUI. What is pinned is everything around the one
generation — that the vendored instruction is the one sent and the user turn is
upstream's own, that a reply becomes a caption in the model's key order with
the aspect and (by default) the boxes gone, that the two promises a prompt box
makes (quoted words, `{a|b}` groups) are held against the answer, that a caption
survives the seed's choosing, and that the chat renders the caption while
keeping the prose.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check, passed  # noqa: E402

_pkg = layout.load("variations", "ideogram4_magic", "ideogram4_still", "chat")
magic, still, variations, chat = (_pkg.ideogram4_magic, _pkg.ideogram4_still,
                                  _pkg.variations, _pkg.chat)


def raises(label, call, error, *fragments):
    try:
        call()
    except error as problem:
        for fragment in fragments:
            if fragment not in str(problem):
                FAILURES.append(f"{label}: said {str(problem)!r}, want {fragment!r} in it")
    except Exception as other:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {other!r}, want {error.__name__}")
    else:
        FAILURES.append(f"{label}: did not raise")


# ---- the request ------------------------------------------------------------

system = magic.system_prompt(())
check("the system prompt is the vendored [SYSTEM] block",
      (system.startswith("You convert a natural-language user idea"), "[USER]" in system),
      (True, False))
message = magic.user_message("a fox on a ridge", "16:9", ())
check("the user turn is upstream's template, filled in",
      message, "TARGET IMAGE ASPECT RATIO: 16:9 (width:height).\nUser idea: a fox on a ridge")
check("a bare ratio is written as W:H", magic.aspect_ratio("1.5"), "3:2")
check("the groups note is said only when there is a group",
      (magic.GROUPS_NOTE in message,
       magic.GROUPS_NOTE in magic.user_message("a fox at {dawn|dusk}", "1:1", ())),
      (False, True))


# ---- the reply --------------------------------------------------------------

REPLY = {
    "aspect_ratio": "16:9",
    "compositional_deconstruction": {
        "elements": [
            {"desc": "Red fox standing, ears up.", "bbox": [300, 100, 800, 400], "type": "obj"},
            {"text": "OPEN", "type": "text", "desc": "Painted sign, white serif."},
        ],
        "background": "Snowy ridge under an overcast sky.",
    },
    "high_level_description": "A photograph of a red fox on a snowy ridge.",
}
fenced = "<think>\n</think>\nHere it is:\n```json\n" + json.dumps(REPLY) + "\n```"
caption = magic.caption(fenced, 'a fox beside a sign reading "OPEN"')
check("a reply becomes a minified caption in the trained key order, aspect and boxes gone",
      caption,
      '{"high_level_description":"A photograph of a red fox on a snowy ridge.",'
      '"compositional_deconstruction":{"background":"Snowy ridge under an overcast sky.",'
      '"elements":[{"type":"obj","desc":"Red fox standing, ears up."},'
      '{"type":"text","text":"OPEN","desc":"Painted sign, white serif."}]}}')
kept = json.loads(magic.caption(json.dumps(REPLY), "a fox", keep_bboxes=True))
check("the boxes stay when asked, after the type",
      list(kept["compositional_deconstruction"]["elements"][0]), ["type", "bbox", "desc"])

raises("a caption with no composition is refused by name",
       lambda: magic.caption('{"high_level_description": "x"}', "x"),
       magic.MagicError, "compositional_deconstruction")
raises("a reply that is not JSON is refused",
       lambda: magic.caption("I would draw a fox.", "a fox"), magic.MagicError, "JSON")
# The 4B's slip on the lab: a whole caption in the instruction's order, the
# composition last, and the root's closing brace never written.
short = json.dumps({"aspect_ratio": "16:9", **json.loads(caption)})[:-1]
check("a caption one brace short at the end is closed",
      magic.caption(short, 'a fox beside a sign reading "OPEN"'), caption)
# A reply that stopped writing is not that slip: after a complete element it
# would close just as cleanly, with the rest of the caption missing.
cut = json.dumps({"compositional_deconstruction": {"background": "b", "elements": [
    {"type": "obj", "desc": "one"}, {"type": "obj", "desc": "two"}]}})
raises("a reply cut off after a complete element is not closed",
       lambda: magic.caption(cut[:cut.index("}, {") + 1], "x"), magic.MagicError, "did not parse")
raises("nor one cut off inside a string",
       lambda: magic.caption(json.dumps(REPLY)[:105], "a fox"), magic.MagicError, "did not parse")
raises("nor one cut off after a comma",
       lambda: magic.caption('{"compositional_deconstruction":{"background":"b","elements":[],',
                             "x"), magic.MagicError, "did not parse")
# A caption breaks a thousand characters in, where a quoted head of the reply
# shows nothing: where it broke is kept for the person, off the sentence the
# model is shown.
try:
    magic.caption('{"high_level_description": "' + "x" * 1200
                  + ' a sign reading "OPEN" in red"}', "x")
except magic.MagicError as problem:
    check("broken JSON keeps where it broke, off the sentence",
          (problem.broken, 'reading "⟨HERE⟩OPEN' in problem.where, "⟨HERE⟩" in str(problem)),
          (True, True, False))
else:
    FAILURES.append("broken JSON did not raise")
raises("an element of an unknown type is refused",
       lambda: magic.caption(json.dumps({"compositional_deconstruction": {
           "background": "b", "elements": [{"type": "person", "desc": "d"}]}}), "x"),
       magic.MagicError, 'elements[0].type')
raises("a lowercase colour is refused",
       lambda: magic.caption(json.dumps({"compositional_deconstruction": {
           "background": "b", "elements": [{"type": "obj", "desc": "d",
                                             "color_palette": ["#ff0000"]}]}}), "x"),
       magic.MagicError, "#RRGGBB")
raises("a box out of range is refused when boxes are kept",
       lambda: magic.caption(json.dumps({"compositional_deconstruction": {
           "background": "b", "elements": [{"type": "obj", "bbox": [0, 0, 1200, 10],
                                             "desc": "d"}]}}), "x", keep_bboxes=True),
       magic.MagicError, "bbox")
raises("quoted words that are not a text element are refused",
       lambda: magic.caption(json.dumps(REPLY), 'a sign reading "CLOSED"'),
       magic.MagicError, '"CLOSED"')

GROUPED = {"high_level_description": "A fox at {dawn|dusk}.",
           "compositional_deconstruction": {"background": "Snow at {dawn|dusk}.", "elements": []}}
check("a group the prose offered and the caption keeps passes",
      json.loads(magic.caption(json.dumps(GROUPED), "a fox at {dawn|dusk}"))["high_level_description"],
      "A fox at {dawn|dusk}.")
raises("a group the caption chose for the seed is refused",
       lambda: magic.caption(json.dumps({"compositional_deconstruction": {
           "background": "Snow at dawn.", "elements": []}}), "a fox at {dawn|dusk}"),
       magic.MagicError, "{dawn|dusk}")

check("a re-ask over a rule quotes the reply and the rule",
      all(part in magic.reask("ASK", "REPLY", magic.MagicError("WHY")) for part in ("ASK", "REPLY", "WHY")),
      True)
broken_ask = magic.reask("ASK", "REPLY", magic.MagicError("WHY", broken=True, where="…X⟨HERE⟩"))
check("a re-ask over broken JSON says why, and shows neither the reply nor the break",
      ("ASK" in broken_ask, "WHY" in broken_ask, "REPLY" in broken_ask, "HERE" in broken_ask),
      (True, True, False, False))


# ---- a caption written by hand ----------------------------------------------

pasted = json.dumps({"compositional_deconstruction": {"elements": [
    {"desc": "d", "bbox": [1, 2, 3, 4], "type": "obj"}], "background": "b"}}, indent=2)
check("a pasted caption keeps its boxes and words, in the trained order, minified",
      still.format_prompt(pasted),
      '{"compositional_deconstruction":{"background":"b",'
      '"elements":[{"type":"obj","bbox":[1,2,3,4],"desc":"d"}]}}')
check("prose is still wrapped", json.loads(still.format_prompt("a fox"))["high_level_description"],
      "a fox")


# ---- the seed's choice inside a caption -------------------------------------

sign = json.dumps({"compositional_deconstruction": {"background": "b", "elements": [
    {"type": "text", "text": "EAT | DRINK", "desc": "sign"}]}}, separators=(",", ":"))
check("a bar inside a caption's value is a word, not a choice",
      variations.vary_mapping({"prompt": sign}, 7, 1, keys=("prompt",))["prompt"], sign)
for seed in range(12):
    chosen = json.loads(variations.vary_mapping(
        {"prompt": json.dumps(GROUPED)}, seed, 1, keys=("prompt",))["prompt"])
    top = chosen["high_level_description"]
    ground = chosen["compositional_deconstruction"]["background"]
    if top[len("A fox at "):-1] != ground[len("Snow at "):-1]:
        FAILURES.append(f"seed {seed}: one group chose twice ({top!r} / {ground!r})")
seen = {json.loads(variations.vary_mapping({"prompt": json.dumps(GROUPED)}, seed, 1,
                                           keys=("prompt",))["prompt"])["high_level_description"]
        for seed in range(12)}
check("and across seeds both alternatives come up", seen, {"A fox at dawn.", "A fox at dusk."})


# ---- the chat ---------------------------------------------------------------

LEDGER = [{"handle": "img-1", "kind": "still", "filename": "a.png", "text": "x"}]
ANNA = [{"name": "anna", "takes": "person", "from": ["img-1"], "description": "red coat"}]
RAIL = {"still_arch": "ideogram4", "still_family": "ideogram4", "aspect": "",
        "still_pictures": {"takes": False, "refusal": "no pictures"}}
action = chat.validate({"act": "render", "kind": "still", "prompt": "@anna at dusk"},
                       LEDGER, cast=["anna"])
check("the magic prompt is given the member as words, never a name",
      chat.still_prose(action, LEDGER, RAIL, ANNA), "red coat at dusk")
check("the shape it is told is the render's, the family default when nobody chose",
      (chat.still_aspect(action, RAIL), chat.still_aspect({**action, "aspect": "1:1"}, RAIL)),
      ("16:9", "1:1"))
piece = chat.still_piece({**action, "caption": caption}, LEDGER, RAIL, cast=ANNA)
check("the render reads the caption", piece["prompt"], caption)
check("without one it reads the prose",
      chat.still_piece(action, LEDGER, RAIL, cast=ANNA)["prompt"], "red coat at dusk")


passed("the magic prompt asks, checks and carries its caption as specified")
