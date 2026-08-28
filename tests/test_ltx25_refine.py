"""What LTX 2.5's half of the refiner promises.

    python3 tests/test_ltx25_refine.py

Runs standalone — no torch, no ComfyUI, no model. `tests/test_refine.py` is the
same suite for H3, and the two are deliberately not merged: what each asserts is
a statement about a different set of weights, and the day they agree about
something is a coincidence rather than a shared rule.

The load-bearing claim here is a negative one. Lightricks caption their training
footage as one continuous paragraph with "no section headers, bullet points, or
labels", so every piece of markup H3's refiner emits — `[Shot 2]` markers, cut
timestamps, `<Picture 1>` ordinals, `<d>` speech tags, the six-section reference
form — is a token sequence these weights were trained never to see, standing
exactly where a description belongs. Most of what follows checks that none of it
can reach this family's prompt.
"""

import re

import layout

pkg = layout.load("canvas", "compile", "grammar", "ltx25_grammar",
                  "prompting", "ltx25_refine")
prompting, refine = pkg.prompting, pkg.ltx25_refine

from harness import FAILURES, check, passed


def flat(text):
    """The prompt text with its hard wrapping collapsed.

    The prompt files are wrapped to read as prose in an editor, so a phrase this
    suite looks for is as likely to straddle a line break as not — and a check
    that failed on where the wrap fell would be testing the wrap.
    """
    return re.sub(r"\s+", " ", text)


def expect_error(label, fn, fragment):
    try:
        fn()
    except prompting.RefineError as exc:
        if fragment not in str(exc):
            FAILURES.append(f"{label}: raised {exc!r}, wanted it to mention {fragment!r}")
        return
    FAILURES.append(f"{label}: did not raise")


# ---- the templates ----------------------------------------------------------
#
# Five: one per guide configuration the segment node builds, plus the reference
# form — which is a real fifth here, because a REF2V card builds a guide the
# other four do not (the Ingredients sheet) and asks for a field they do not.

check("the family declares the four guide configurations and the reference form",
      sorted(refine.MODE_TEMPLATE), ["FL2V", "I2V", "L2V", "REF2V", "T2V"])
check("...and offers them under auto in the pill's order",
      refine.PROMPTING.templates, ("auto", "REF2V", "T2V", "I2V", "L2V", "FL2V"))
# The reference form is the superset a whole-strip refine is written under: a
# card with no references writes no handles, where a strip written under a guide
# template would have nowhere to put the sheet at all.
check("a strip with one reference card is written under the reference form",
      refine.PROMPTING.representative(["I2V", "REF2V", "T2V"]), "REF2V")
check("...and a strip with none takes the first card's",
      refine.PROMPTING.representative(["I2V", "T2V"]), "I2V")
# The sheet field is asked for on the reference form and on nothing else.
check("REF2V asks for the sheet",
      refine.SHEET_SECTION in refine.PROMPTING.reply_shape("REF2V", 1), True)
check("...and I2V does not",
      refine.SHEET_SECTION in refine.PROMPTING.reply_shape("I2V", 1), False)

for mode, template in refine.MODE_TEMPLATE.items():
    check(f"the {mode} template carries a fenced worked example",
          "<request>" in template and "</request>" in template, True)
    check(f"the {mode} example replies in the contract's shape",
          '"shots"' in template, True)
    check(f"the {mode} example claims its scene as its own",
          "belongs to this example alone" in template, True)
    check(f"the {mode} example writes no ordinal citation",
          "<Picture" in template or "<Video" in template, False)
    check(f"the {mode} example writes no shot marker",
          "[Shot" in template, False)
    check(f"the {mode} example writes no speech tag", "<d>" in template, False)

for mode in ("I2V", "L2V", "FL2V"):
    check(f"the {mode} example demonstrates looking at the pictures first",
          prompting.SEEN_FIELD in refine.MODE_TEMPLATE[mode], True)
check("the text-only mode is not shown a field it will never be asked for",
      prompting.SEEN_FIELD in refine.MODE_TEMPLATE["T2V"], False)

craft, multishot = flat(refine.CRAFT), flat(refine.MULTISHOT)
check("the craft rules forbid the labels the trainer never saw",
      all(phrase in craft for phrase in
          ("No headers, no bullet points, no numbered beats",
           'labels such as "Audio:", "Visual:", "Shot:"')), True)
check("...and put dialogue in quotation marks rather than in a tag",
      "inside double quotation marks" in craft, True)
check("...and name the camera vocabulary the guide uses",
      all(word in craft for word in ("pans across", "pushes in", "tracks")), True)
check("...and ask for the subject as it is after the move",
      "after* the move" in craft, True)
check("the cut rules make a cut a sentence, not a marker",
      "A hard cut transitions to" in multishot, True)
check("...and carry Lightricks' own two-to-four advice",
      "Two to four shots in one generation" in multishot, True)
check("...and say what happens to the sound across it",
      "continues across the cut" in multishot, True)


# ---- the instructions -------------------------------------------------------
#
# A rule that is not in the system prompt cannot be followed, so each is checked
# as behaviour rather than as wording.

system = refine.system_prompt("I2V")
for topic, needle in [("no markup in the prose", "no headers, no bullet points"),
                      ("style fidelity", "Carry every concrete thing the request names"),
                      ("the request is not a message",
                       "typed at a video generator, not at you"),
                      ("one shot's worth of subjects", "Keep the frame focused"),
                      ("the mode's own frames", refine.MODE_NOTES["I2V"])]:
    check(f"the instructions cover {topic}", needle in system, True)

check("the instructions name this family's model, not another's",
      "LTX 2.5" in system and "H3" not in system, True)
check("the template follows the mode",
      "the video's first frame" in system
      and "final frame" not in refine.system_prompt("I2V"), True)

# Recency is the strongest lever on a small model: the worked example is the
# last prose it reads, and the contract is the last thing of all.
ordered = refine.system_prompt("T2V", shape=refine.reply_shape(1))
check("the craft comes before the cut rules",
      ordered.index("HOW LTX 2.5 IS WRITTEN") < ordered.index("CUTS INSIDE ONE DESCRIPTION"),
      True)
check("the cut rules come before the mode's template",
      ordered.index("CUTS INSIDE ONE DESCRIPTION") < ordered.index("THIS MODE"), True)
check("the worked example comes after the template",
      ordered.index("THIS MODE") < ordered.index("\nEXAMPLE"), True)
check("the contract is the last thing read, after the example",
      ordered.index("\nEXAMPLE") < ordered.index("Return exactly this JSON object"), True)

check("a language other than English reaches the prose and the dialogue",
      "Write all descriptive prose, dialogue and lyrics in Japanese"
      in refine.system_prompt("T2V", "Japanese"), True)
check("...and English says nothing at all",
      "LANGUAGE" in refine.system_prompt("T2V", "English"), False)


# ---- choosing the template --------------------------------------------------

check("auto follows the derived mode", refine.choose_template("auto", "I2V"), ("I2V", False))
check("...and so do empty and None",
      (refine.choose_template("", "T2V"), refine.choose_template(None, "FL2V")),
      (("T2V", False), ("FL2V", False)))
check("a pin replaces the derived mode", refine.choose_template("T2V", "I2V"), ("T2V", True))
check("pinning what auto would pick is not a pin",
      refine.choose_template("I2V", "I2V"), ("I2V", False))
check("case does not matter", refine.choose_template("fl2v", "T2V"), ("FL2V", True))
expect_error("an unknown template is refused",
             lambda: refine.choose_template("IMAX", "T2V"), "unknown refine template")
expect_error("...including another family's, which is the pin a family switch leaves behind",
             lambda: refine.choose_template("REF2VA", "T2V"), "unknown refine template")


# ---- the reply contract -----------------------------------------------------

shape = refine.reply_shape(3, shown=("img-1", "img-2"), piece=True)
check("the contract asks for one entry per shot",
      shape.count('{"body": "..."}'), 3)
check("...for the grounding pass first, where there are pictures",
      prompting.SEEN_FIELD in shape, True)
check("...for the rewritten global prompt on a whole-timeline refine",
      prompting.PIECE_FIELD in shape, True)
check("...and for the two sound fields",
      '"overall_soundscape"' in shape and '"non_diegetic_music"' in shape, True)
check("a cut inside a shot is said to stay inside its body",
      "not a second entry" in shape, True)
check("nothing asks for a cut time", "at_seconds" in shape, False)
check("nothing asks for the reference form",
      "subject_definitions" in shape or "retention_analysis" in shape, False)

bare = refine.reply_shape(1)
check("no pictures means no grounding field to skip",
      prompting.SEEN_FIELD in bare, False)
check("a single card is not asked for a global prompt",
      prompting.PIECE_FIELD in bare, False)


# ---- reading the reply ------------------------------------------------------

REPLY = ('{"shots": [{"body": "A wide shot of a harbour."}], '
         '"overall_soundscape": "Gulls and rigging.", "non_diegetic_music": ""}')

parsed = refine.parse_reply(REPLY, 1)
check("one shot comes back as its prose", parsed["shots"], ["A wide shot of a harbour."])
check("...with the soundscape beside it", parsed["soundscape"], "Gulls and rigging.")
check("...and an unasked-for score left empty", parsed["music"], "")
check("a reply with no global prompt asked for carries none", "piece" in parsed, False)

check("a leaked reasoning block is transport, not content",
      refine.parse_reply("<think>hmm</think>" + REPLY, 1)["shots"],
      ["A wide shot of a harbour."])
check("...and so is a markdown fence",
      refine.parse_reply("```json\n" + REPLY + "\n```", 1)["shots"],
      ["A wide shot of a harbour."])
check("a bare string in `shots` is read as the body it is",
      refine.parse_reply('{"shots": ["Just prose."], "overall_soundscape": "x", '
                         '"non_diegetic_music": ""}', 1)["shots"],
      ["Just prose."])
check("the global prompt comes back when it was asked for",
      refine.parse_reply('{"%s": "A cold film.", "shots": [{"body": "b"}], '
                         '"overall_soundscape": "", "non_diegetic_music": ""}'
                         % prompting.PIECE_FIELD, 1, piece=True)["piece"],
      "A cold film.")

# The one failure worth refusing over: a short `shots` array would leave a
# timeline card silently holding its old text.
expect_error("a short reply is refused rather than half-applied",
             lambda: refine.parse_reply(REPLY, 3), "asked for 3 shots and got 1")
expect_error("a reply that is not JSON at all is refused",
             lambda: refine.parse_reply("Sure! Here you go.", 1),
             "did not return JSON")


# ---- the glossary -----------------------------------------------------------
#
# Frames and nothing else, because `grammar.refuse` turns every reference away.


class Asset:
    def __init__(self, handle, role, filename):
        self.handle, self.role, self.filename = handle, role, filename
        self.kind, self.track, self.takes = "image", "picture", "full"


check("a start frame is named as what it is",
      refine.slot_row(Asset("img-1", "first_frame", "/in/open.png"))["what"],
      "the target video's first frame (open.png)")
check("an end frame likewise",
      refine.slot_row(Asset("img-2", "last_frame", "/in/close.png"))["what"],
      "the target video's final frame (close.png)")
check("a frame is shown no ordinal to write, because there is none",
      "label" in refine.slot_row(Asset("img-1", "first_frame", "/in/a.png"),
                                 "<Picture 1>", True),
      False)


# ---- the message ------------------------------------------------------------

SHOT = {"text": "a kite gets airborne", "seconds": 8, "mode": "FL2V",
        "slots": [{"handle": "img-1", "what": "the target video's first frame (kite.png)",
                   "image": 1}]}

message = refine.user_message([SHOT], seconds=8, shown=("img-1",), mode="FL2V")
check("the request is fenced, so it reads as material and not as a question",
      "<request>\na kite gets airborne\n</request>" in message, True)
check("the attached picture is bound to the handle it is of",
      "@img-1 [image 1]: the target video's first frame (kite.png)" in message, True)
check("...and the model is told to look at it beside that handle",
      "Look at [image 1] before writing this shot" in message, True)
check("the duration is stated", "runs 8.00 seconds" in message, True)

strip = refine.user_message([SHOT, {**SHOT, "text": "it comes down again", "continues": True}],
                            seconds=16, shown=("img-1",), mode="FL2V")
check("a strip says how many entries it wants back",
      "Return exactly 2 entries in `shots`" in strip, True)
check("...and a seam is said to be one", prompting.CONTINUES_NOTE in strip, True)


# ---- the family's half, through the seam ------------------------------------

P = refine.PROMPTING
check("the family never asks the model to cut a lone card up",
      [P.shot_limit(s) for s in (0, 4, 30, 600)], [1, 1, 1, 1])
check("a strip of mixed modes is written under the first card's",
      P.representative(["I2V", "T2V"]), "I2V")
check("an empty strip still names a mode", P.representative([]), "T2V")
check("no shot carries its own reference sections",
      P.ref_shots("timeline", "T2V", [{"mode": "T2V"}], False), ())
check("a pin costs nothing worth warning about here",
      P.pin_note("T2V", "I2V"), None)
check("a cast writes no sections this family would have to drop",
      P.cast_sections, ())

passed("LTX 2.5 writes captions, and nothing of H3's markup can reach one")
