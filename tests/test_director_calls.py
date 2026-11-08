"""Director's planning calls, driven by scripted replies instead of a model.

    python tests/test_director_calls.py

Pure — no ComfyUI, no model. What is under test is `creator/director_calls.py`:
that a brief goes through the calls in order and comes out a plan
`director.validate` takes; that a length the person wrote overrules the
model's; that a refused reply is re-asked once with the refusal quoted, and a
second refusal stops planning with the plan kept as far as it got; that a
question stops planning; and that the counts written into the messages are
the ones code worked out. The bench (`tools/director_bench.py`) measures the
same loop against a real model.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check  # noqa: E402

pkg = layout.load("prompting", "chat", "director", "director_calls")
director, calls = pkg.director, pkg.director_calls

RAIL = {"still": "krea2", "edit": "qwenedit", "video": "h3", "aspect": "16:9",
        "min_seconds": 1, "max_seconds": 60}


def fence(obj):
    return "Here you go.\n```json\n" + json.dumps(obj) + "\n```"


def scripted(replies):
    """An `ask` that answers from a list and records what it was asked."""
    asked = []

    def ask(system, message, schema, label):
        asked.append({"system": system, "message": message, "schema": schema, "label": label})
        return replies.pop(0)
    return ask, asked


GOOD = [
    fence({"questions": [], "assumptions": ["It is night."]}),
    fence({"title": "Night Train", "seconds": 12, "look": "sodium light, grain"}),
    fence({"beats": [{"text": "@george wakes in the carriage.", "weight": "short"},
                     {"text": "He finds the cab empty.", "weight": "long"}]}),
    fence({"entities": [{"name": "George", "kind": "person", "description": "a man"},
                        {"name": "carriage", "kind": "place", "description": "an old train carriage"}]}),
    fence({"shots": [{"action": "@george wakes up inside @carriage.", "continues": "cut"}]}),
    fence({"shots": [{"action": "@george walks the length of @carriage.", "continues": "pin"},
                     {"action": "@george opens the cab door: nobody.", "continues": "cut"}]}),
]

# ---- the happy path -----------------------------------------------------------

ask, asked = scripted(list(GOOD))
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george", "description": "a tall man"}])
plan = out["plan"]
check("the calls run in order", [a["label"] for a in asked],
      ["brief", "basics", "beats", "entities", "shots.b1", "shots.b2"])
check("every call is first-try", [e["tries"] for e in out["log"]], [1] * 6)
check("the brief's 30 seconds overrules the model's 12", plan["seconds"], 30)
check("the clips add up to the target", sum(c["seconds"] for c in director.clips(plan)), 30)
check("the cited cast member is not re-cast", [e["name"] for e in plan["entities"]],
      ["george", "carriage"])
check("…and the relisting is measured", out["relisted"], ["george"])
check("the first shot is new whatever the model wrote", plan["shots"][0]["continues"], "new")
check("assumptions land in the header", plan["assumptions"], ["It is night."])
check("each call sends its schema", [a["schema"] is calls.SCHEMAS[a["label"].split(".")[0]]
                                     for a in asked], [True] * 6)
check("the beats call is told the count", "Write 3 beats" in asked[2]["message"], True)
check("the shots call is told the beat's seconds and limit",
      "THIS BEAT (about 22 seconds)\nHe finds the cab empty." in asked[5]["message"]
      and "Write 1 to 4 shots" in asked[5]["message"], True)
check("the shots call is not shown the shot before (a small model copies it)",
      "@george wakes up inside @carriage." in asked[5]["message"], False)
check("the cast reads as cast in the names block",
      "@george — cast: a tall man" in asked[4]["message"], True)

# ---- re-ask, then failure -----------------------------------------------------

bad_cite = fence({"shots": [{"action": "@ghost wakes up.", "continues": "new"}]})
replies = list(GOOD)
replies[4:5] = [bad_cite, GOOD[4]]
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}])
entry = out["log"][4]
check("a bad citation is re-asked once", (entry["tries"], entry["ok"]), (2, True))
check("…quoting the doubt and the names", "@ghost is not in the plan"
      in asked[5]["message"] and "@carriage" in asked[5]["message"], True)

replies = list(GOOD)
replies[4:5] = [bad_cite, bad_cite]
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}])
check("…and kept as a plain word if the re-ask cites it again",
      (out["plan"]["shots"][0]["action"], len(out["warnings"])), ("ghost wakes up.", 1))

replies = list(GOOD)
replies[4:5] = ["no json here", "still none"]
ask, asked = scripted(replies)
try:
    calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                     cast=[{"name": "george"}])
    check("two failures stop planning", False, True)
except calls.PlanningFailed as failed:
    check("two failures stop planning with a sentence", "no JSON object" in str(failed), True)
    check("…keeping the plan as far as it got",
          (len(failed.plan["beats"]), len(failed.plan["shots"])), (2, 0))
    check("…and the log says which call", failed.log[-1]["label"], "shots.b1")

# ---- questions ---------------------------------------------------------------

ask, asked = scripted([fence({"questions": ["What about?", "Who?", "Why?"], "assumptions": []})])
out = calls.plan_piece("make me a video", RAIL, ask)
check("a question stops planning", out["plan"], None)
check("…at two questions at most", out["questions"], ["What about?", "Who?"])

ask, asked = scripted(list(GOOD[1:]))
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}], questions=False)
check("questions off skips the brief call", asked[0]["label"], "basics")

# ---- attached pictures ---------------------------------------------------------

replies = list(GOOD)
replies[4:5] = [fence({"shots": [{"action": "@george wakes in @pic-9.", "continues": "new"}]}),
                fence({"shots": [{"action": "@george wakes in @pic-1.", "continues": "new"}]})]
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}],
                       ledger=[{"handle": "pic-1", "kind": "picture", "text": "a carriage"}])
check("an unattached handle is re-asked", out["log"][4]["first_error"],
      "shot 1 cites @pic-9, which is not attached. The attached pictures are: @pic-1.")
check("the attached picture is a name the shots may cite",
      "@pic-1 — attached picture: a carriage" in asked[4]["message"], True)

# ---- what code counts ------------------------------------------------------------

def _refused(call):
    try:
        call()
    except calls.Doubt:
        return True
    return False


def _plan_error(call):
    try:
        call()
    except director.PlanError:
        return True
    return False


# ---- what code corrects in a shot ---------------------------------------------

plan_for_cites = {"entities": [{"name": "bottle"}, {"name": "red_boat"}, {"name": "keeper"},
                               {"name": "lighthouse"}]}
check("a plain mention is cited, its 'the' dropped",
      calls.cite_mentions("The keeper sees the bottle by the red boat.", plan_for_cites),
      "@keeper sees @bottle by @red_boat.")
check("only the first mention, and a citation is left alone",
      calls.cite_mentions("@keeper waves; the keeper smiles at the lighthouse keeper.",
                          plan_for_cites),
      "@keeper waves; the keeper smiles at @lighthouse keeper.")
check("a word inside another is not a mention",
      calls.cite_mentions("bottleneck traffic", plan_for_cites), "bottleneck traffic")

replies = list(GOOD)
replies[3] = fence({"entities": [{"name": "Pic-1", "kind": "person", "description": "a waitress"},
                                 {"name": "carriage", "kind": "place", "description": "a carriage"}]})
LONG = "rocks gently along dark rails past sleeping towns."
replies[4:5] = [fence({"shots": [{"action": f"The carriage {LONG} Continues: new", "continues": "new"}]})]
replies[5:6] = [fence({"shots": [{"action": f"@carriage {LONG}", "continues": "cut"}]}),
                fence({"shots": [{"action": "@george finds the cab empty.", "continues": "cut"}]})]
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}],
                       ledger=[{"handle": "pic-1", "kind": "picture", "text": "a waitress"}])
check("an entity named after an attached handle is dropped",
      [e["name"] for e in out["plan"]["entities"]], ["george", "carriage"])
check("the entities call is told what is attached",
      "ATTACHED (already pictured" in asked[3]["message"], True)
check("a join written into the action comes off, and the mention is cited",
      out["plan"]["shots"][0]["action"], f"@carriage {LONG}")
check("a shot repeating an earlier one is re-asked", out["log"][5]["first_error"],
      "shot 1 repeats shot s1 nearly word for word. Write what happens in this beat instead.")
check("an apostrophe and an accent still find the mention",
      calls.cite_mentions("He opens the driver's cab of the café.",
                          {"entities": [{"name": "driver_s_cab"}, {"name": "cafe"}]}),
      "He opens @driver_s_cab of @cafe.")
check("a shot that is an earlier one plus a clause is a repeat",
      calls._check_repeats.__name__ and _refused(lambda: calls._check_repeats(
          [{"action": "@george walks slowly into @carriage toward the dark cab. Close on his face."}],
          {"shots": [{"id": "s1", "beat": "b1",
                      "action": "@george walks slowly into @carriage toward the dark cab."}]}, "b2")),
      True)
check("two short shots sharing a verb are not a repeat", _refused(lambda: calls._check_repeats(
          [{"action": "@keeper reads the message inside @bottle."}],
          {"shots": [{"id": "s1", "beat": "b1",
                      "action": "@keeper pulls @bottle down and reads the message."}]}, "b2")),
      False)
check("a pin that carries on is not a repeat", _refused(lambda: calls._check_repeats(
          [{"action": "@george pulls the cab door open and freezes."}],
          {"shots": [{"id": "s1", "beat": "b1",
                      "action": "@george walks into @carriage toward the cab."}]}, "b2")),
      False)
check("an entity the brief and beats never mention is dropped",
      out["invented"], [])
replies = list(GOOD)
replies[3] = fence({"entities": [{"name": "carriage", "kind": "place", "description": "a carriage"},
                                 {"name": "oven", "kind": "thing", "description": "a brick oven"}]})
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}])
check("…the worked example's oven, in a train", (out["invented"],
      [e["name"] for e in out["plan"]["entities"]]), (["oven"], ["george", "carriage"]))
check("a word of the name is a mention", calls.mentioned(
      {"name": "lighthouse_keeper"}, "the keeper climbs"), True)
replies = list(GOOD)
replies[4:5] = [fence({"shots": [{"action": f"@carriage {LONG}", "continues": "new"}]})]
replies[5:6] = [fence({"shots": [{"action": f"@carriage {LONG}", "continues": "cut"}]})] * 2
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}])
check("a repeat the re-ask keeps is kept, with a warning",
      (len(out["plan"]["shots"]), out["warnings"]),
      (2, ["shots.b2: shot 1 repeats shot s1 nearly word for word. "
           "Write what happens in this beat instead."]))
check("an object left open is closed", calls._object(
      '```json\n{"entities": [\n  {"name": "a]b", "kind": "thing"}\n]\n```'),
      {"entities": [{"name": "a]b", "kind": "thing"}]})
check("…but a mismatched bracket is still a re-ask", _plan_error(
      lambda: calls._object('{"a": [1}')), True)
check("a café is a cafe", director.name_of("Café"), "cafe")

check("seconds: 40-second", calls.asked_seconds("a 40-second spot"), 40)
check("seconds: 15 s", calls.asked_seconds("a 15 s shot"), 15)
check("seconds: minutes", calls.asked_seconds("a 1.5 minute piece"), 90)
check("seconds: a count is not a length", calls.asked_seconds("3 shots of a fox"), None)
check("seconds: 35mm is not a length", calls.asked_seconds("shot on 35mm"), None)
check("beats: one moment", calls.beats_for(6), 1)
check("beats: a minute", [calls.beats_for(s) for s in (12, 15, 40, 60, 600)], [2, 2, 4, 6, 8])
check("shots: per beat", [calls.shots_for(s) for s in (3, 6, 12, 40)], [1, 1, 2, 4])

for name in calls.CALLS:
    check(f"{name}.txt has a worked example", "```json" in calls.prompt_file(name), True)
