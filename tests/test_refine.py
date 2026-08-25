"""What the refiner promises about the model's reply.

Runs standalone — `python tests/test_refine.py` — with no torch and no ComfyUI.
Everything here is the boundary between a language model's output and
a prompt that will be encoded, which is the part worth pinning down: the model
is the one component of this package that cannot be relied on to do what it was
asked, so what happens when it does not is the contract.

The load-bearing one is `normalize_handles`. The rewrite is stored with
`@handles` so that `compile._substitute` assigns the ordinals at queue time and
a rewrite survives an asset being added — but the guide the model has just read
is written entirely in ordinals, so it reaches for them anyway. Converting them
back is what keeps one representation in the blob. Getting it wrong is silent:
the prompt still compiles, and points at the wrong tensor.
"""

import importlib.util
import os
import sys

import layout
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Through `layout.load`, which knows where a module that moved into a family
# package went — the hand-rolled loader this replaces knew only `PY_ROOT`.
pkg = layout.load("prompting", "refine")
# The two halves the refiner came apart into: `prompting` is the harness —
# handles, checks, the ChatML turns, the reply budget — and `refine` is H3's
# own templates, contract and glossary. See `families/refine.py`.
prompting, refine = pkg.prompting, pkg.refine

from harness import FAILURES, check, passed


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
# One compact template per mode replaces the embedded four-to-five-thousand-
# token guide. Each ends in a worked request-and-reply pair written in the
# reply's own JSON shape with `@handles` — the pair is what teaches "expand,
# don't answer", and the shape is what keeps the model from imitating the
# guides' finished-document form.

for mode in ("T2VA", "I2VA", "L2VA", "FL2VA", "REF2VA"):
    template = refine.MODE_TEMPLATE[mode]
    check(f"the {mode} template carries a fenced worked example",
          "<request>" in template and "</request>" in template, True)
    check(f"the {mode} example replies in the contract's shape",
          '"shots"' in template, True)
    check(f"the {mode} example writes handles, not ordinals",
          "<Picture" in template, False)
    check(f"the {mode} example claims its scene as its own",
          "belongs to this example alone" in template, True)

for mode in ("I2VA", "L2VA", "FL2VA", "REF2VA"):
    check(f"the {mode} example demonstrates looking at the pictures first",
          prompting.SEEN_FIELD in refine.MODE_TEMPLATE[mode], True)
check("the text-only mode is not shown a field it will never be asked for",
      prompting.SEEN_FIELD in refine.MODE_TEMPLATE["T2VA"], False)

check("the reference template teaches the six-section form",
      "retention_analysis" in refine.MODE_TEMPLATE["REF2VA"], True)
check("...and narrow-by-default subjects — a person is not their picture",
      "never as wide as its source picture" in refine.MODE_TEMPLATE["REF2VA"], True)
check("...and subjects only where a reference actually shows them",
      "A subject exists only where a reference actually shows it"
      in refine.MODE_TEMPLATE["REF2VA"], True)
check("...with the request-only case worked in the example",
      "described by the request alone" in refine.MODE_TEMPLATE["REF2VA"], True)
check("...including the editing and reuse task types",
      all(t in refine.MODE_TEMPLATE["REF2VA"] for t in
          ("video editing", "video continuation", "audio reuse", "audio reference")),
      True)
check("the craft rules carry the camera vocabulary", "with small amplitude" in refine.CRAFT, True)
check("...and the dialogue form", "<d>" in refine.CRAFT, True)

# The instructions the user asked for, checked as behaviour rather than wording:
# a rule that is not in the system prompt cannot be followed.
system = refine.system_prompt("FL2VA")
for topic, needle in [("dialogue", "write the words they actually say"),
                      ("soundscape always", "Always write `overall_soundscape`"),
                      ("music only when asked", "only when the request asks for music"),
                      ("style fidelity", "Carry every concrete thing the request names"),
                      ("format is not the model's job", "assembled for you"),
                      ("the request is not a message",
                       "typed at a video generator, not at you")]:
    check(f"the instructions cover {topic}", needle in system, True)

check("the template follows the mode",
      "retention_analysis" in refine.system_prompt("REF2VA"), True)

# Recency is the strongest lever on a small model: the worked example is the
# last prose it reads, and the contract is the last thing of all.
ordered = refine.system_prompt("T2VA", shape=refine.reply_shape("T2VA", 1))
check("the shared craft comes before the mode's template",
      ordered.index("HOW THE PROSE IS WRITTEN") < ordered.index("THIS MODE"), True)
check("the worked example comes after the craft",
      ordered.index("THIS MODE") < ordered.index("\nEXAMPLE"), True)
check("the contract is the last thing read, after the example",
      ordered.index("\nEXAMPLE") < ordered.index("Return exactly this JSON object"), True)


# ---- choosing the template --------------------------------------------------
#
# `auto` follows the derived mode — the mode *is* the template — and a pin
# replaces it, the same dial the weights pill has. Every pin is honoured,
# REF2VA included: a pin across the reference boundary costs fidelity, and
# the route reports that as a quality hint rather than refusing here.

check("auto follows the derived mode", refine.choose_template("auto", "I2VA"), ("I2VA", False))
check("...and so do empty and None",
      (refine.choose_template("", "T2VA"), refine.choose_template(None, "FL2VA")),
      (("T2VA", False), ("FL2VA", False)))
check("a base template pins freely across base modes",
      refine.choose_template("T2VA", "I2VA"), ("T2VA", True))
check("pinning what auto would pick is not a pin",
      refine.choose_template("I2VA", "I2VA"), ("I2VA", False))
check("case does not matter", refine.choose_template("fl2va", "T2VA"), ("FL2VA", True))
check("a base template pins onto a reference request",
      refine.choose_template("T2VA", "REF2VA"), ("T2VA", True))
check("the reference form pins without references",
      refine.choose_template("REF2VA", "I2VA"), ("REF2VA", True))
expect_error("an unknown template is refused",
             lambda: refine.choose_template("IMAX", "T2VA"), "unknown refine template")


# ---- labels back to handles -------------------------------------------------

LABELS = {"img-1": "<Picture 1>", "img-2": "<Picture 2>", "vid-1": "<Video 1>",
          "vid-1:audio": "<Audio 1>"}

check("an ordinal the model wrote becomes the handle behind it",
      prompting.normalize_handles("<Picture 2> shows her face, cut against <Video 1>.", LABELS),
      "@img-2 shows her face, cut against @vid-1.")
check("a handle it wrote correctly is left alone",
      prompting.normalize_handles("@img-1 opens the shot", LABELS), "@img-1 opens the shot")
check("spacing inside the label does not hide it",
      prompting.normalize_handles("<Picture  2>", LABELS), "@img-2")
# A video's soundtrack has a label but no handle of its own — `<Audio 1>` is
# already the only way to name it, and rewriting it to `@vid-1` would move it
# from the sound slot into the picture one.
check("a soundtrack's label stays a label",
      prompting.normalize_handles("<Audio 1> carries the room tone", LABELS),
      "<Audio 1> carries the room tone")
# Left exactly as written rather than deleted: it is the one mistake that would
# otherwise produce a wrong video instead of an error, so `check` reports it.
check("an ordinal nothing backs is left for the check to find",
      prompting.normalize_handles("<Picture 9> is empty", LABELS), "<Picture 9> is empty")
check("nothing attached means nothing to convert",
      prompting.normalize_handles("<Picture 1>", {}), "<Picture 1>")

check("a clean rewrite has nothing to report",
      prompting.check("@img-1 and <Audio 1>", {"img-1", "vid-1"}, LABELS), [])
check("an invented handle is reported",
      any("@img-7" in p for p in prompting.check("@img-7 waves", {"img-1"}, LABELS)), True)
check("an invented ordinal is reported",
      any("<Picture 9>" in p for p in prompting.check("<Picture 9>", {"img-1"}, LABELS)), True)

# The one failure `check` cannot see: a rewrite that simply never mentions an
# attached reference. It compiles, it queues, and the file conditions nothing.
# `uncited` reads the whole reply at once because the reference form cites a
# picture in `subject_definitions` and nowhere else — a citation anywhere is a
# citation.
check("a reference cited by handle is not missing",
      prompting.uncited("@img-1 opens", {"img-1"}, LABELS), [])
check("a reference cited by its label is not missing",
      prompting.uncited("<Picture 1> opens", {"img-1"}, LABELS), [])
check("a soundtrack cited by its audio label covers its video's handle",
      prompting.uncited("<Audio 1> carries the tone", {"vid-1"}, LABELS), [])
check("a reference the rewrite never names is missing",
      prompting.uncited("a woman sings", {"img-1", "vid-1"}, LABELS), ["img-1", "vid-1"])
check("nothing attached, nothing missing", prompting.uncited("a walk", set(), {}), [])


# ---- the reply --------------------------------------------------------------

GOOD = '{"shots": [{"body": "a courier waits"}], "overall_soundscape": "rain", ' \
       '"non_diegetic_music": ""}'

check("a plain reply parses",
      refine.parse_reply(GOOD, "FL2VA", 1),
      {"shots": ["a courier waits"], "soundscape": "rain", "music": "", "seen": ""})
check("a fenced reply parses", refine.parse_reply(f"```json\n{GOOD}\n```", "FL2VA", 1)["shots"],
      ["a courier waits"])
check("a reasoning model's preamble is dropped",
      refine.parse_reply(f"<think>hmm</think>\n{GOOD}", "FL2VA", 1)["shots"], ["a courier waits"])
check("chat around the JSON is dropped",
      refine.parse_reply(f"Sure! Here you go:\n{GOOD}\nHope that helps.", "FL2VA", 1)["shots"],
      ["a courier waits"])

# Refused rather than padded: a short array would leave a timeline card silently
# keeping the text the user asked to have rewritten, which reads as the refiner
# having decided that card was fine.
expect_error("too few shots", lambda: refine.parse_reply(GOOD, "FL2VA", 2), "got 1")
expect_error("no JSON at all", lambda: refine.parse_reply("I cannot do that.", "FL2VA", 1),
             "did not return JSON")
expect_error("broken JSON", lambda: refine.parse_reply('{"shots": [', "FL2VA", 1),
             "could not be read")

check("an empty music field survives as empty",
      refine.parse_reply(GOOD, "FL2VA", 1)["music"], "")
check("the reference form carries its three extra sections",
      sorted(refine.parse_reply(
          '{"subject_definitions": "a", "summary": "b", "retention_analysis": "c",'
          ' "shots": [{"body": "d"}], "overall_soundscape": "e", "non_diegetic_music": ""}',
          "REF2VA", 1)["sections"]),
      ["retention_analysis", "subject_definitions", "summary"])
check("the base form has none", "sections" in refine.parse_reply(GOOD, "FL2VA", 1), False)


# ---- the message ------------------------------------------------------------
#
# Handles are allocated per segment, so two cards each have an `@img-1` and it is
# a different file in each. The glossary is therefore printed per shot, and the
# ordinal hint is only shown where there is one shot to be confused about.

message = refine.user_message([
    {"text": "she walks in", "seconds": 5, "mode": "I2VA",
     "slots": [{"handle": "img-1", "what": "the first frame (a.png)", "label": "<Picture 1>"}]},
    {"text": "her hands", "seconds": 4, "mode": "T2VA", "continues": True, "slots": []},
], seconds=9.04, images=1, mode="I2VA")

check("each shot's own attachments are listed under it", "@img-1" in message, True)
# Fenced, so the rules have something to point at when they say the text is not
# addressed to the model. Raw, it is just the last conversational-looking thing
# in the turn, and a small model answers it.
check("the request rides behind a fence",
      "<request>\nshe walks in\n</request>" in message, True)
check("...every shot's own text does",
      "<request>\nher hands\n</request>" in message, True)
check("the total duration is stated", "9.04 seconds" in message, True)
check("a strip is asked for as one piece", "2 shots of one piece" in message, True)
check("a shot whose mode differs says so", refine.MODE_NOTES["T2VA"] in message, True)
check("the mode already in the system prompt is not repeated",
      message.count(refine.MODE_NOTES["I2VA"]), 0)
check("a continuing shot is told what it opens on", prompting.CONTINUES_NOTE in message, True)

# Only some attached assets have a picture in the message — an audio reference
# has none, a video taken for its soundtrack alone has none — so the Nth image is
# not the Nth line, and the number is what says which line it is of.
numbered = prompting.describe_slots([
    {"handle": "img-1", "what": "the target video's first frame (a.png)",
     "label": "<Picture 1>", "image": 1},
    {"handle": "aud-1", "what": "a reference audio clip (b.wav)",
     "note": "you cannot hear it; take what it holds from the request"},
    {"handle": "img-2", "what": "the target video's final frame (c.png)",
     "label": "<Picture 2>", "image": 2},
])
check("a picture says which of the message's images it is",
      numbered[0], "@img-1 (becomes <Picture 1>) [image 1]: the target video's first frame (a.png)")
check("an asset with no picture is not numbered", "[image" in numbered[1], False)
check("...and the next picture keeps counting from the pictures, not the lines",
      "[image 2]" in numbered[2], True)

# ---- the glossary ------------------------------------------------------------
#
# What each attached file is, said once for the model. The narrowing lives here
# and nowhere else on the way to the DiT — encode hands over the same tensor
# whatever `takes` says — so a row that stops carrying it is a setting that
# silently does nothing.


class Slot:
    """As much of `compile.Asset` as a glossary row reads."""

    def __init__(self, handle, kind, takes="full", role="reference", track=None):
        self.handle, self.kind, self.role = handle, kind, role
        self.takes, self.track = takes, track
        self.filename = f"clips/{handle}.mp4" if kind != "image" else f"stills/{handle}.png"


check("an un-narrowed picture is still scoped to what it shows",
      "only what you can actually see in it" in refine.slot_row(Slot("img-1", "image"))["note"],
      True)
check("a person reference says the background is not part of it",
      "background, palette, lighting" in refine.slot_row(Slot("img-1", "image", "person"))["note"],
      True)
check("a keyframe is described by its role, not its narrowing",
      refine.slot_row(Slot("img-1", "image", role="first_frame"))["what"],
      "the target video's first frame (img-1.png)")

# A clip's four extra takes are the reference guide's video roles, and each one
# is a different label in the rewrite. The notes are what say which.
video = lambda takes, track="picture": refine.slot_row(Slot("vid-1", "video", takes, track=track))
check("an un-narrowed clip is described by its streams",
      video("full")["what"], "a reference video, picture only (vid-1.mp4)")
check("...and carries no scope note",
      "note" in video("full"), False)
check("a camera reference is a Video entry",
      "<Video N> entry for its camera and pacing structure" in video("camera")["note"], True)
check("...and puts nobody from the clip on screen",
      "Nobody and nothing visible in the clip appears" in video("camera")["note"], True)
check("a motion reference is an attribute transfer onto the target subject",
      "attribute_transfer" in video("motion")["note"], True)
check("...and is not a Video entry",
      "give the clip no <Video N> entry of its own" in video("motion")["note"], True)
check("an edit says the target is an edited version of the clip",
      "The target video is an edited version of <Video N>." in video("edit")["note"], True)
check("a continuation asks for the task type by name",
      "'video continuation' in the task-type" in video("continue")["note"], True)
check("a clip taken for its sound is told it cannot be heard",
      video("full", track="sound")["note"],
      "you cannot hear it; take what it holds from the request")

# Audio's own four, which are the guide's audio roles. The split that decides
# both the task-type prefix and the retention marker is copy against reference,
# so the notes name the marker rather than leave it to be inferred — and every
# one of them still opens on the deafness, because what the refiner cannot hear
# governs everything else it might have said about the file.
sound = lambda takes, kind="audio", track=None: refine.slot_row(
    Slot("aud-1" if kind == "audio" else "vid-1", kind, takes, track=track))

check("an un-narrowed audio reference says only that it cannot be heard",
      sound("full")["note"], "you cannot hear it; take what it holds from the request")
check("a voice reference binds the speaker and refuses the words",
      "Only the voice is the reference" in sound("voice")["note"], True)
check("...and marks the retention line for it",
      "mark that line reference in retention_analysis" in sound("voice")["note"], True)
check("...and still opens on what cannot be heard",
      sound("voice")["note"].startswith("you cannot hear it"), True)
check("a music reference is written into non_diegetic_music",
      "Say so in non_diegetic_music" in sound("music")["note"], True)
check("an ambience reference is written into overall_soundscape",
      "Say so in overall_soundscape" in sound("ambience")["note"], True)
check("a copied signal asks for the task-type prefix by name",
      "'audio reuse' in the task-type prefix" in sound("copy")["note"], True)
check("...and for fully_copy in retention_analysis",
      "fully_copy in retention_analysis" in sound("copy")["note"], True)
check("a narrowed audio reference says what it is for",
      sound("voice")["what"], "a reference audio clip, for the voice in it (aud-1.mp4)")

# A clip taken for its soundtrack alone is an audio reference in a container
# with a picture in it: it scopes with the audio vocabulary, but it is still
# described as the clip it came from.
check("a sound-only clip keeps its own description",
      sound("full", kind="video", track="sound")["what"],
      "a reference video used for its soundtrack alone (vid-1.mp4)")
check("...and takes the audio scopes",
      "Only the musical style is the reference"
      in sound("music", kind="video", track="sound")["note"], True)


# ---- the transport ----------------------------------------------------------
#
# ComfyUI is handed one string and samples plain logits, so the turns, the
# reasoning suppression and the shape all have to be written into that string —
# and the reply comes back missing the brace it was started on.

shape = refine.reply_shape("REF2VA", 2)
check("the shape asks for as many bodies as there are shots",
      shape.count('{"body": "..."}'), 2)
check("...and for the reference form's own sections", "retention_analysis" in shape, True)
check("the base form is not asked for them", "retention_analysis" in refine.reply_shape("T2VA", 1), False)
check("the shape reaches the system prompt when it is handed one",
      "Return exactly this JSON object" in refine.system_prompt("T2VA", shape=shape), True)

prompt = prompting.chatml("RULES", "REQUEST", images=2)
check("the system turn carries the guide", "<|im_start|>system\nRULES<|im_end|>" in prompt, True)
check("one vision block per image", prompt.count(prompting.VISION_BLOCK), 2)
check("the images come before the text they are described by",
      prompt.index(prompting.VISION_BLOCK) < prompt.index("REQUEST"), True)
check("reasoning is suppressed", "<think>\n\n</think>" in prompt, True)
check("the reply is already begun", prompt.endswith("\n\n" + prompting.PREFILL), True)
check("a text-only call has no vision block", prompting.VISION_BLOCK in prompting.chatml("R", "M"), False)

# The prefill is why: what an unconstrained model actually does is answer "Here
# is the rewrite:" first. Starting its turn inside the object removes the place
# that goes — and `parse_reply` has to be given the brace back.
check("a reply that continues the prefill parses",
      refine.parse_reply(prompting.PREFILL + GOOD[1:], "FL2VA", 1)["shots"], ["a courier waits"])

# ---- the cuts ---------------------------------------------------------------
#
# The Creator node is one card with one duration, and nothing in it divides a
# clip into shots — so without asking the model where the cuts go, a twenty-
# second clip is one uncut shot exactly like a six-second one. `cuts` is that
# ask, and everything here is what happens when the answer is not usable: the
# times are the model's, the ordering and the fit are not.

check("a clip too short to cut is not asked to", prompting.shot_limit(3), 1)
check("a longer one is, up to what fits", prompting.shot_limit(10), 5)
check("...and never past the ceiling", prompting.shot_limit(600), prompting.MAX_SHOTS)
check("no duration is no choice", prompting.shot_limit(0), 1)

TIMED = ('{"shots": [{"at_seconds": 0, "body": "a"}, {"at_seconds": 4, "body": "b"}], '
         '"overall_soundscape": "rain", "non_diegetic_music": ""}')

check("a timed reply keeps its times", refine.parse_reply(TIMED, "T2VA", 1, cuts=5)["cuts"],
      [0, 4])
check("...and its bodies", refine.parse_reply(TIMED, "T2VA", 1, cuts=5)["shots"], ["a", "b"])
# The count is the model's to pick here, so the one shot it was nominally asked
# about is not the contract — the ceiling is.
check("one shot is a valid answer to the ask",
      len(refine.parse_reply(GOOD, "T2VA", 1, cuts=5)["shots"]), 1)
check("a fixed request still has no times", "cuts" in refine.parse_reply(GOOD, "T2VA", 1), False)

check("the model's cuts become the marked description",
      refine.join_shots(["a", "b"], [0, 4], 12),
      "[Shot 1] a [Shot 2] At 00:04.000, b")
# Written by the model, not clamped by us, is the whole point — but the order is
# ours, or `contextir` would emit a cut that runs backwards.
check("a cut before the one in front of it is pushed past it",
      refine.join_shots(["a", "b", "c"], [0, 6, 2], 20),
      "[Shot 1] a [Shot 2] At 00:06.000, b [Shot 3] At 00:08.000, c")
check("a cut past the end is pulled back inside it",
      refine.join_shots(["a", "b"], [0, 99], 10),
      "[Shot 1] a [Shot 2] At 00:08.000, b")
# Merged rather than dropped: the prose is the only copy of that part of the
# description, and a rewrite quietly one paragraph shorter is worse than a cut
# that did not happen.
check("a shot with no room left joins the one before it",
      refine.join_shots(["a", "b", "c"], [0, 8, 9], 10),
      "[Shot 1] a [Shot 2] At 00:08.000, b c")
check("markers the model wrote itself are taken back out",
      refine.join_shots(["[Shot 1] a", "[Shot 2] At 00:09.000, b"], [0, 4], 12),
      "[Shot 1] a [Shot 2] At 00:04.000, b")

check("the timed shape bounds the count by what fits",
      "1 to 3 entries" in refine.reply_shape("T2VA", 1, cuts=3), True)
check("...and asks for the time each one starts on",
      "at_seconds" in refine.reply_shape("T2VA", 1, cuts=3), True)
check("a fixed request is not offered the choice",
      "at_seconds" in refine.reply_shape("T2VA", 1), False)
check("the rule reaches the system prompt only when the cuts are the model's",
      "SHOTS AND CUTS" in refine.system_prompt("T2VA", cuts=3), True)
check("...and a timeline, whose cuts are the cards', never sees it",
      "SHOTS AND CUTS" in refine.system_prompt("T2VA"), False)


# ---- looking at the pictures ------------------------------------------------
#
# Reasoning is suppressed and the reply is prefilled with `{`, so the first token
# generated is already the rewrite: without being made to, the model can write a
# whole description having never attended to the images. `SEEN_FIELD` is the
# grounding pass, and it is asked for only where there is something to see.

with_images = refine.reply_shape("I2VA", 1, images=2)
check("a picture buys a field to describe it in", prompting.SEEN_FIELD in with_images, True)
check("...and it is the first thing written",
      with_images.index(prompting.SEEN_FIELD) < with_images.index('"shots"'), True)
check("a text-only request is not asked for one",
      prompting.SEEN_FIELD in refine.reply_shape("T2VA", 1), False)

SEEN = ('{"what_i_see": "@img-1 is a red door.", "shots": [{"body": "a courier waits"}], '
        '"overall_soundscape": "rain", "non_diegetic_music": ""}')
check("what it saw is read back", refine.parse_reply(SEEN, "I2VA", 1)["seen"],
      "@img-1 is a red door.")
# Empty rather than absent: the route reports a model that skipped it, which is
# the failure the field exists to make visible, so the key has to be there to be
# found empty.
check("a model that skipped it leaves the field empty",
      refine.parse_reply(GOOD, "I2VA", 1)["seen"], "")

# Repeated beside the handles it governs. The count at the top of the message is
# thousands of tokens back by the time a twelve-card refine reaches shot 9.
looked = refine.user_message([
    {"text": "she walks in", "seconds": 5, "mode": "I2VA",
     "slots": [{"handle": "img-1", "what": "the first frame (a.png)",
                "label": "<Picture 1>", "image": 1}]},
], seconds=5, images=1, mode="I2VA")
check("the shot holding a picture is told to look at it",
      "Look at [image 1] before writing this shot" in looked, True)
check("a shot with nothing attached is not", "Look at [image" in refine.user_message(
    [{"text": "a street", "seconds": 5, "mode": "T2VA", "slots": []}], mode="T2VA"), False)


# ---- quoted words -----------------------------------------------------------
#
# Quotation marks in a request are the user dictating exact words, and their
# survival is the one fidelity promise that can be checked mechanically. The
# comparison forgives what the craft rules themselves change — casing, curly
# marks, spacing, terminal punctuation — and nothing else.

check("a quoted line that survives is not reported",
      prompting.dropped_quotes(['she says "hold the line"'],
                            "She (S1) says: <d>[English] Hold the line.</d>"), [])
check("a quoted line the rewrite dropped is",
      prompting.dropped_quotes(['a sign reading "OPEN ALL NIGHT"'], "a sign glows above"),
      ["OPEN ALL NIGHT"])
check("curly quotation marks in the request still count",
      prompting.dropped_quotes(["she says “over the hills”"], "nothing survives"),
      ["over the hills"])
check("a curly apostrophe in the reply still matches a straight one",
      prompting.dropped_quotes(['says "let\'s go home"'],
                            "she says: <d>[English] Let’s go home!</d>"), [])
check("several requests are checked together",
      prompting.dropped_quotes(['a "red" door', 'a "blue" door'], "the red door opens"),
      ["blue"])
check("no quotes means nothing to report", prompting.dropped_quotes(["a dog runs"], ""), [])


# ---- the reply's length -----------------------------------------------------
#
# Not a context size. `Qwen3VLSDTokenizer` is built with `max_length=99999999`
# and never truncates, so the prompt is embedded whole however long it runs and
# the only budget that exists is the one on the answer.

check("the default is what it always was", prompting.reply_tokens(None), prompting.NUM_PREDICT)
check("a number the user set is kept", prompting.reply_tokens(8192), 8192)
check("...clamped to what is worth reserving a cache for",
      (prompting.reply_tokens(1), prompting.reply_tokens(10 ** 9)),
      (prompting.MIN_PREDICT, prompting.MAX_PREDICT))
check("junk falls back rather than failing a refine",
      prompting.reply_tokens("lots"), prompting.NUM_PREDICT)


# ---- the piece --------------------------------------------------------------
#
# A whole-timeline refine rewrites the global prompt as a field of its own —
# `PIECE_FIELD` — instead of absorbing it into every body. The join onto each
# segment stays compile-time (`compile.refined_scope`), which is what keeps the
# timeline's global box a live input after refining. And a chained strip's
# reference cards carry their own analysis sections inside their shot entries,
# because each card is its own generation over its own reference pool — the one
# reason mixed and all-reference strips used to be refused.

piece_shape = refine.reply_shape("REF2VA", 3, piece=True, ref_shots=(1,))
check("a whole-timeline shape asks for the global prompt",
      '"%s": "...",' % prompting.PIECE_FIELD in piece_shape, True)
check("the marked entries carry their own sections",
      '{"subject_definitions": "...", "summary": "...", "retention_analysis": "...", '
      '"body": "..."}' in piece_shape, True)
check("...the unmarked entries stay plain", '{"body": "..."},' in piece_shape, True)
check("...and the top-level set is gone",
      '\n  "subject_definitions"' in piece_shape, False)
check("which entries carry sections is said in words",
      "Shot entry 2 carries its own" in piece_shape, True)
check("several are said in the plural",
      "Shot entries 1, 3 each carry their own"
      in refine.reply_shape("REF2VA", 3, ref_shots=(0, 2)), True)
check("a single-document reply keeps the top-level set",
      '\n  "subject_definitions": "...",' in refine.reply_shape("REF2VA", 1), True)

PIECED = (
    '{"global_prompt": "A live-action piece.", "shots": ['
    '{"body": "a courier waits"}, '
    '{"subject_definitions": "<Subject 1> is the woman in @img-1", '
    '"summary": "[Ref2VA] a portrait", "retention_analysis": "fully_preserved", '
    '"body": "she turns"}], '
    '"overall_soundscape": "rain", "non_diegetic_music": ""}'
)
pieced = refine.parse_reply(PIECED, "REF2VA", 2, piece=True, ref_shots=(1,))
check("the rewritten global prompt is read back", pieced["piece"], "A live-action piece.")
check("per-shot sections come back aligned with the bodies",
      [own is None for own in pieced["shot_sections"]], [True, False])
check("...holding that shot's own analysis",
      pieced["shot_sections"][1]["summary"], "[Ref2VA] a portrait")
check("with per-shot sections there is no top-level set", "sections" in pieced, False)
check("a skipped global prompt reads back empty",
      refine.parse_reply(GOOD, "FL2VA", 1, piece=True)["piece"], "")
check("an unasked reply carries no piece", "piece" in refine.parse_reply(GOOD, "FL2VA", 1), False)

piece_msg = refine.user_message(
    [{"text": "a courier waits", "seconds": 6}, {"text": "her hands", "seconds": 6}],
    seconds=12, mode="T2VA", piece={"text": "Live-action, 16mm.", "rewrite": True})
check("the piece is shown once, fenced",
      "<global>\nLive-action, 16mm.\n</global>" in piece_msg, True)
check("...and asked for as its own field", prompting.PIECE_FIELD in piece_msg, True)
check("...with the no-references rule beside it", "no @handle" in piece_msg, True)
check("the shots' own requests stay their own",
      ("<request>\na courier waits\n</request>" in piece_msg
       and "Live-action, 16mm. a courier waits" not in piece_msg), True)

check("an empty global prompt is still asked for",
      "hoist what every shot shares"
      in refine.user_message([{"text": "x"}], piece={"text": "", "rewrite": True}), True)

context_msg = refine.user_message([{"text": "her hands", "seconds": 6}], seconds=6,
                                  mode="T2VA", piece={"text": "Live-action.", "rewrite": False})
check("a single-card refine shows the piece as context",
      "It is context, not material" in context_msg, True)
check("...and does not ask for the field", prompting.PIECE_FIELD in context_msg, False)
check("an empty global with nothing to rewrite adds no block",
      "THE PIECE" in refine.user_message([{"text": "x"}],
                                         piece={"text": "", "rewrite": False}), False)
check("no piece, no block",
      "THE PIECE" in refine.user_message([{"text": "x"}]), False)

# --- the reference pool -------------------------------------------------------
#
# The piece's own references, listed once at the top: their handles are the only
# ones stable across every shot, and citing one in a shot's prose is what
# attaches it there at queue time.

pool_msg = refine.user_message(
    [{"text": "she waits", "seconds": 6}, {"text": "her hands", "seconds": 6}],
    seconds=12, mode="T2VA",
    pool=[{"handle": "ref-1", "what": "a person reference (sheet.png)", "image": 1}])
check("the pool is shown once, at the top",
      "ATTACHED TO THE PIECE" in pool_msg, True)
check("...with the handle's glossary line",
      "@ref-1 [image 1]: a person reference (sheet.png)" in pool_msg, True)
check("...and the citing rule beside it",
      "Writing one's handle in a shot's prose is what attaches it" in pool_msg, True)
check("no pool, no block",
      "ATTACHED TO THE PIECE" in refine.user_message([{"text": "x"}]), False)

# With a pool beside the piece, the global rewrite may cite the pool — a
# citation there applies the reference to every shot — and only the pool.
piece_pool_msg = refine.user_message(
    [{"text": "she waits", "seconds": 6}], seconds=6, mode="T2VA",
    piece={"text": "The piece follows @ref-1.", "rewrite": True},
    pool=[{"handle": "ref-1", "what": "a person reference (sheet.png)"}])
check("with a pool, the piece may cite it",
      "no @handle except the piece's own references" in piece_pool_msg, True)
check("...and without one, the old rule stands",
      "Write no @handle and no <Picture N> label" in refine.user_message(
          [{"text": "x"}], piece={"text": "y", "rewrite": True}), True)


passed("all refiner tests passed")
