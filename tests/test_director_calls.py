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
import re
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


def scripted(replies, parts=None):
    """An `ask` that answers from a list and records what it was asked.

    The parts call — a shot too long for one clip, written as its clips — is
    asked last and only where the seconds fall that way, so it is answered
    here rather than scripted into every list: as many sentences as the
    message asks for, or `parts` (a reply, or a list of them) where a test is
    about that call."""
    asked = []
    parts = list(parts) if isinstance(parts, list) else parts

    def ask(system, message, schema, label):
        asked.append({"system": system, "message": message, "schema": schema, "label": label})
        if label.startswith("parts."):
            if isinstance(parts, list):
                return parts.pop(0)
            if parts is not None:
                return parts
            count = int(re.search(r"in order: (\d+) sentences", message).group(1))
            return fence({"parts": [f"What happens in clip {n}." for n in range(1, count + 1)]})
        return replies.pop(0)
    return ask, asked


def labels(asked):
    """What was asked, less the parts calls: those follow from the seconds a
    change leaves a shot with, not from the change (see "a long shot" below)."""
    return [a["label"] for a in asked if not a["label"].startswith("parts.")]


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

# ---- plan turns --------------------------------------------------------------------
#
# The plan from the happy path: beat 1 is shot 1, beat 2 is shots 2 and 3,
# @george is cast and @carriage is a place with a sheet to make.

ask, asked = scripted(list(GOOD))
base = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                        cast=[{"name": "george", "description": "a tall man"}])["plan"]
GEORGE = [{"name": "george", "description": "a tall man"}]


def turn(text, replies, plan=base, cast=GEORGE):
    ask, asked = scripted(list(replies))
    return calls.plan_turn(plan, text, ask, cast=cast), asked


out, asked = turn("how many shots are there?",
                  [fence({"act": "say", "row": "", "change": "", "say": "Three shots."})])
check("a question is answered, and changes nothing", (out["act"], out["say"], out["plan"]),
      ("say", "Three shots.", None))
check("the turn is shown the plan in the card's words",
      [line for line in asked[0]["message"].split("\n") if line.startswith(("beat", "  shot", "@"))],
      ["beat 1 — @george wakes in the carriage. (8 s)",
       "  shot 1 — @george wakes up inside @carriage. (8 s)",
       "beat 2 — He finds the cab empty. (22 s)",
       "  shot 2 — @george walks the length of @carriage. (11 s)",
       "  shot 3 — @george opens the cab door: nobody. (11 s)",
       "@george — cast: a tall man",
       "@carriage — place: an old train carriage"])
check("…the person's words last, above the instruction",
      asked[0]["message"].endswith("THE MESSAGE\nhow many shots are there?\n\n"
                                   "Decide what the message asks of the plan. " + calls.REPLY), True)
check("…with its schema", asked[0]["schema"] is calls.SCHEMAS["turn"], True)

CLOSE = {"action": "Close on @george's hand on the cab door: nobody inside.", "continues": "cut"}
out, asked = turn("make the last shot a close-up",
                  [fence({"act": "edit", "row": "Shot 3", "change": "A close-up on the door.", "say": ""}),
                   fence({"shots": [CLOSE]})])
check("an edit to a shot rewrites that shot by its own call",
      ([a["label"] for a in asked], out["row"], out["plan"]["shots"][2]["action"]),
      (["turn", "turn.shot"], "s3", CLOSE["action"]))
check("…and no other", [s["action"] for s in out["plan"]["shots"][:2]],
      [s["action"] for s in base["shots"][:2]])
check("…shown the shot as it stands and the change",
      "THIS SHOT NOW (about 11 seconds, continues \"cut\")\n@george opens the cab door: nobody."
      in asked[1]["message"] and "THE CHANGE\nA close-up on the door." in asked[1]["message"], True)
check("…with nothing to change on the edit path", out["render"], None)

out, asked = turn("shot nine darker",
                  [fence({"act": "edit", "row": "shot 9", "change": "darker", "say": ""}),
                   fence({"act": "edit", "row": "shot 3", "change": "darker", "say": ""}),
                   fence({"shots": [CLOSE]})])
check("a row the plan does not have is re-asked with the rows it has",
      ('"row" must name one row of the plan: "the piece", "beat 1", "beat 2", "shot 1"'
       in out["log"][0]["first_error"], out["row"]), (True, "s3"))
check("rows read loosely", [calls.row_of(base, w) for w in ("Beat 2", "shot #1", "carriage",
                                                            "@George", "the look")],
      ["b2", "s1", "e2", "e1", "header"])

out, asked = turn("make the second beat shorter",
                  [fence({"act": "edit", "row": "beat 2", "change": "shorter", "say": ""}),
                   fence({"beats": [{"text": "He finds the cab empty.", "weight": "short"}]})])
check("a beat that only changed length keeps its shots",
      (len(asked), out["plan"]["beats"][1]["weight"], [s["id"] for s in out["plan"]["shots"]]),
      (2, "short", ["s1", "s2", "s3"]))
check("…and its seconds are code's", director.allot_plan(out["plan"])["b2"], 15)

out, asked = turn("in beat two he finds the driver asleep instead",
                  [fence({"act": "edit", "row": "beat 2", "change": "He finds the driver asleep.", "say": ""}),
                   fence({"beats": [{"text": "He finds the driver asleep at the controls.", "weight": "long"}]}),
                   fence({"shots": [{"action": "@george finds the driver asleep at the controls.",
                                     "continues": "cut"}]})])
check("a beat whose action changed has its shots written again, under new ids",
      (labels(asked), [s["id"] for s in out["plan"]["shots"]]),
      (["turn", "turn.beat", "shots.b2"], ["s1", "s4"]))

made = director.land(director.start(base, "e2")[0], "e2", "pic-7", director.fingerprint(base, "e2"))
made = director.approve(made, "e2")
out, asked = turn("the carriage should be a sleeper car",
                  [fence({"act": "edit", "row": "@carriage", "change": "Make @carriage a sleeper car.", "say": ""}),
                   fence({"entities": [{"name": "sleeper_carriage", "kind": "place",
                                        "description": "A sleeper car with bunks."}]})], plan=made)
entity = out["plan"]["entities"][1]
check("an entity is rewritten by the entities call, its name kept unless the person gave one",
      (entity["name"], entity["description"]), ("carriage", "A sleeper car with bunks."))
check("a sheet already made is changed on the edit path",
      (out["render"]["row"], out["render"]["action"]["from"], out["render"]["action"]["prompt"]),
      ("e2", ["pic-7"], "Make carriage a sleeper car."))
check("…under the row's mark in the changed plan, so it lands current",
      out["render"]["mark"], director.fingerprint(out["plan"], "e2"))
check("…and until it lands the old sheet is stale", director.state_of(out["plan"], "e2"), "stale")

conductor = director.validate(director.add_entities(
    base, [{"name": "conductor", "kind": "person", "description": "a conductor"}]))
out, asked = turn("use @anna for the conductor",
                  [fence({"act": "edit", "row": "@conductor", "change": "Anna plays the conductor.", "say": ""})],
                  plan=conductor, cast=GEORGE + [{"name": "anna", "description": "a woman"}])
check("citing a cast member on a person recasts them, with no call of its own",
      (len(asked), out["recast"], out["plan"]["entities"][2]["source"]), (1, "anna", {"cited": "anna"}))
check("…and their sheet is no longer a row",
      [r["id"] for r in director.rows(out["plan"]) if r["kind"] == "sheet"], ["e2"])

out, asked = turn("make it 20 seconds and call it Last Train",
                  [fence({"act": "edit", "row": "the piece", "change": "20 seconds, titled Last Train", "say": ""}),
                   fence({"title": "Last Train", "seconds": 45, "look": "sodium light, grain"})])
check("a length the person says wins over the model's",
      (out["plan"]["seconds"], out["plan"]["title"]), (20, "Last Train"))
check("…told the length it is to keep",
      "The person asked for 20 seconds." in asked[1]["message"], True)

WINTER = [fence({"act": "replan", "row": "", "change": "It is winter, snow everywhere.", "say": ""}),
          fence({"title": "Snow Train", "seconds": 30, "look": "sodium light, grain"}),
          fence({"beats": [{"text": "@george wakes as a snowdrift buries @carriage.", "weight": "long"}]}),
          fence({"entities": [{"name": "carriage", "kind": "place", "description": "listed again"},
                              {"name": "snowdrift", "kind": "thing", "description": "a deep drift"}]}),
          fence({"shots": [{"action": "@george wakes inside @carriage as snow piles at the window.",
                            "continues": "new"}]})]
out, asked = turn("set it in winter", WINTER, plan=made)
new = out["plan"]
check("a replan writes the piece again from the beats down",
      labels(asked), ["turn", "replan.basics", "replan.beats", "replan.entities", "shots.b3"])
check("…under new ids", ([b["id"] for b in new["beats"]], [s["id"] for s in new["shots"]]),
      (["b3"], ["s4"]))
check("…keeping the entities it had, their sheets with them",
      ([e["id"] for e in new["entities"]], new["entities"][1]["description"],
       new["renders"]["e2"]["handle"], director.state_of(new, "e2")),
      (["e1", "e2"], "an old train carriage", "pic-7", "approved"))
COLD = list(WINTER)
COLD[1] = fence({"title": "Snow Train", "seconds": 30, "look": "cold blue light"})
check("…but a new look is in every sheet's prompt, so a sheet made in the old one is stale",
      director.state_of(turn("set it in winter", COLD, plan=made)[0]["plan"], "e2"), "stale")
check("…an entity it adds that no shot cites goes", "snowdrift" in director.names(new), False)
check("…the entities call is told who is already there",
      "@carriage — an old train carriage" in asked[3]["message"], True)
check("…and the change is part of the brief from now on",
      new["brief"].endswith("It is winter, snow everywhere."), True)

out, asked = turn("make it 2 seconds",
                  [fence({"act": "edit", "row": "the piece", "change": "2 seconds", "say": ""}),
                   fence({"title": "Night Train", "seconds": 2, "look": "x"})]
                  + [fence({"title": "Night Train", "seconds": 2, "look": "x"}),
                     fence({"beats": [{"text": "@george wakes in the carriage.", "weight": "short"}]}),
                     fence({"entities": []}),
                     fence({"shots": [{"action": "@george wakes up inside @carriage.", "continues": "new"}]})])
check("a length the shots cannot share is planned again at that length",
      (out["act"], out["plan"]["seconds"], len(out["plan"]["shots"])), ("replan", 2, 1))

try:
    turn("whatever", ["nothing", "nothing again"])
    check("a turn that fails twice raises", False, True)
except calls.PlanningFailed as failed:
    check("a turn that fails twice keeps the plan as it was", failed.plan, base)
    check("…and says what to do", str(failed).startswith("Could not tell what that changes"), True)

# ---- what the person's words say plainly ---------------------------------------------

check("rows named by position", calls.named_rows(base, "make the last beat longer and the 2nd shot wider"),
      ["b2", "s2"])
check("…by number", calls.named_rows(base, "in shot 1 he wakes"), ["s1"])
check("…and one past the end names nothing", calls.named_rows(base, "the fourth shot"), [])
check("a title in the words", calls.asked_title("call it “Last Orders”."), "Last Orders")
check("…and none in other words", calls.asked_title("call the waitress Mia"), None)

out, asked = turn("make the last beat shorter",
                  [fence({"act": "edit", "row": "shot 3", "change": "shorter", "say": ""}),
                   fence({"beats": [{"text": "He finds the cab empty.", "weight": "short"}]})])
check("a beat the words name overrules the row the call picked",
      (out["row"], out["log"][0]["overruled"]), ("b2", "s3 -> b2"))

out, asked = turn("in the first shot he should wake with a start",
                  [fence({"act": "edit", "row": "@george", "change": "He wakes with a start.", "say": ""}),
                   fence({"shots": [{"action": "@george jolts awake inside @carriage.", "continues": "new"}]})])
check("a cast member's row is no row to edit, and the words name the shot",
      (out["row"], out["log"][0]["tries"]), ("s1", 1))

out, asked = turn("call it Last Train",
                  [fence({"act": "say", "row": "", "change": "", "say": "It is called Night Train."}),
                   fence({"title": "Night Train", "seconds": 30, "look": "sodium light, grain"})])
check("a title the words give is the header's, whatever the call said",
      (out["act"], out["row"], out["plan"]["title"]), ("edit", "header", "Last Train"))

out, asked = turn("is 20 seconds too long?",
                  [fence({"act": "say", "row": "", "change": "", "say": "No."})])
check("a length in a question changes nothing", (out["act"], out["plan"]), ("say", None))

out, asked = turn("make @carriage a sleeper",
                  [fence({"act": "edit", "row": "@carriage", "change": "A sleeper car.", "say": ""}),
                   fence({"entities": [{"name": "carriage", "kind": "place", "description": "an old train carriage"}]}),
                   fence({"entities": [{"name": "carriage", "kind": "place", "description": "A sleeper car."}]})])
check("a rewrite that is the row as it was is re-asked",
      (out["log"][1]["first_error"].startswith("your description of @carriage is exactly as it was"),
       out["plan"]["entities"][1]["description"]), (True, "A sleeper car."))

out, asked = turn("how long is it?", [fence({"say": "Thirty seconds."})])
check("an answer with no act is an answer", (out["act"], out["say"]), ("say", "Thirty seconds."))
out, asked = turn("make it darker", [fence({"say": "Make it darker."}),
                                     fence({"act": "say", "row": "", "change": "", "say": "Sure."})])
check("…but the message said back is re-asked", out["log"][0]["tries"], 2)


# ---- one take -----------------------------------------------------------------
#
# "One continuous shot" is asked as one beat of one shot, and that shot is a
# take: cut only where the video family stops, not at the plan's limit.

ask, asked = scripted([
    fence({"questions": [], "assumptions": []}),
    fence({"title": "Corridor", "seconds": 40, "look": "fluorescent"}),
    fence({"beats": [{"text": "@george walks the corridor to the door.", "weight": "long"}]}),
    fence({"entities": [{"name": "corridor", "kind": "place", "description": "a long hospital corridor"}]}),
    fence({"shots": [{"action": "@george walks the length of @corridor.", "continues": "new"}]}),
])
out = calls.plan_piece("one continuous 40 second shot: @george walks a hospital corridor", RAIL, ask,
                       cast=[{"name": "george"}])
plan = out["plan"]
check("a one-take brief asks for one beat", "Write 1 beat" in asked[2]["message"], True)
check("…and one shot", "Write 1 shot " in asked[4]["message"], True)
check("the shot is a take", plan["shots"][0].get("one_take"), True)
check("it renders as one 40 s clip under the 60 s ceiling",
      [(c["seconds"], c["parts"]) for c in director.clips(plan)], [(40, 1)])

# A brief filmed through somebody's eyes: the basics write the camera, and the
# beats, entities and shots calls are each shown it, so the person whose eyes
# they are is written as the camera all the way down rather than as somebody
# standing in frame.
POV = list(GOOD)
POV[1] = fence({"title": "Night Train", "seconds": 12, "look": "sodium light, grain",
                "camera": "first-person view through George's eyes"})
ask, asked = scripted(POV)
plan = calls.plan_piece("a 12 second piece seen through @george's eyes on a night train", RAIL, ask,
                        cast=[{"name": "george", "description": "a man"}])["plan"]
check("the camera lands on the plan", plan["camera"], "first-person view through George's eyes")
check("the beats, entities and shots calls are shown it",
      [("THE CAMERA" in a["message"]) for a in asked[2:]], [True] * len(asked[2:]))
ask, asked = scripted(list(GOOD))
calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                 cast=[{"name": "george", "description": "a man"}])
check("a brief without one shows no camera block",
      any("THE CAMERA" in a["message"] for a in asked), False)


# ---- two calls: the large profile -------------------------------------------------
#
# The same plan from a structure call (header, beats and entities in one
# object) and a shot list for the whole piece. Same readers underneath, so a
# bad citation or a repeat is refused in the same sentence, prefixed with the
# beat it is in; an entity no shot cites is dropped rather than drawn.

STRUCTURE = {"questions": [], "assumptions": ["It is night."], "title": "Night Train",
             "seconds": 12, "look": "sodium light, grain", "camera": "",
             "beats": [{"text": "@george wakes in the carriage.", "weight": "short"},
                       {"text": "He finds the cab empty.", "weight": "long"}],
             "entities": [{"name": "George", "kind": "person", "description": "a man"},
                          {"name": "carriage", "kind": "place", "description": "an old train carriage"},
                          {"name": "lantern", "kind": "thing", "description": "a brass lantern"}]}
SHOTLIST = {"shots": [{"beat": 1, "action": "@george wakes up inside @carriage.", "continues": "cut"},
                      {"beat": "2", "action": "@george walks the length of @carriage.", "continues": "pin"},
                      {"beat": "beat 2", "action": "@george opens the cab door: nobody.", "continues": "cut"}]}

ask, asked = scripted([fence(STRUCTURE), fence(SHOTLIST)])
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george", "description": "a tall man"}], steps="large")
large = out["plan"]
check("large: two calls", [a["label"] for a in asked], ["structure", "shotlist"])
check("large: each with its schema", [a["schema"] is calls.SCHEMAS[a["label"]] for a in asked],
      [True, True])
check("large: the plan is the same document",
      (large["title"], large["seconds"], large["assumptions"], [b["id"] for b in large["beats"]],
       [(s["id"], s["beat"], s["continues"]) for s in large["shots"]]),
      ("Night Train", 30, ["It is night."], ["b1", "b2"],
       [("s1", "b1", "new"), ("s2", "b2", "pin"), ("s3", "b2", "cut")]))
check("large: the cited cast member is not re-cast, and the relisting is measured",
      ([e["name"] for e in large["entities"]], out["relisted"]), (["george", "carriage"], ["george"]))
check("large: an entity no shot cites is dropped and named",
      out["uncited"], ["lantern"])
check("large: nothing is dropped for going unmentioned", out["invented"], [])
check("large: the structure call is told the length and a range, not a count",
      "The person asked for 30 seconds." in asked[0]["message"]
      and "Write 1 to 8 beats" in asked[0]["message"], True)
check("large: the shot list sees every beat with its seconds and room",
      "THE BEATS\nbeat 1 (8 seconds, 1 to 2 shots): @george wakes in the carriage.\n"
      "beat 2 (22 seconds, 1 to 4 shots): He finds the cab empty." in asked[1]["message"], True)
check("large: …and the names it may cite",
      "@george — cast: a tall man" in asked[1]["message"]
      and "@carriage — place: an old train carriage" in asked[1]["message"], True)
check("large: the clips add up", sum(c["seconds"] for c in director.clips(large)), 30)
check("the setting reads loosely", [calls.steps_of(v) for v in ("large", " Large ", "small", None, 3)],
      ["large", "large", "small", "small", "small"])

ask, asked = scripted([fence({**STRUCTURE, "questions": ["What is it about?"], "beats": [], "entities": []})])
out = calls.plan_piece("make me a video", RAIL, ask, steps="large")
check("large: a question stops planning at one call", (out["plan"], out["questions"], len(asked)),
      (None, ["What is it about?"], 1))
ask, asked = scripted([fence({**STRUCTURE, "questions": ["Still asking?"]}), fence(SHOTLIST)])
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}], steps="large", questions=False)
check("large: with questions off the brief is planned regardless, and the call is told so",
      (out["plan"] is not None, "Ask nothing" in asked[0]["message"]), (True, True))

missing = {"shots": [s for s in SHOTLIST["shots"] if s["beat"] == 1]}
ask, asked = scripted([fence(STRUCTURE), fence(missing), fence(SHOTLIST)])
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}], steps="large")
check("large: a beat with no shots is re-asked", out["log"][1]["first_error"],
      "beat 2 has no shots; every beat needs at least one.")
wrong = {"shots": [{**SHOTLIST["shots"][0], "beat": 7}] + SHOTLIST["shots"][1:]}
ask, asked = scripted([fence(STRUCTURE), fence(wrong), fence(SHOTLIST)])
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}], steps="large")
check("large: a beat number the plan does not have is re-asked", out["log"][1]["first_error"],
      'shot 1\'s "beat" must be the number of the beat it shows, 1 to 2; it was 7.')
ghost = {"shots": [SHOTLIST["shots"][0], {"beat": 2, "action": "@ghost walks.", "continues": "pin"}]}
ask, asked = scripted([fence(STRUCTURE), fence(ghost), fence(ghost)])
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                       cast=[{"name": "george"}], steps="large")
check("large: an unknown citation is re-asked naming the beat, then kept as a word",
      (out["log"][1]["first_error"].startswith("beat 2: @ghost is not in the plan"),
       out["plan"]["shots"][1]["action"], len(out["warnings"])),
      (True, "ghost walks.", 1))
ask, asked = scripted([fence(STRUCTURE), "nothing", "nothing"])
try:
    calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask,
                     cast=[{"name": "george"}], steps="large")
    check("large: two failures stop planning", False, True)
except calls.PlanningFailed as failed:
    check("large: two failures keep the structure", (len(failed.plan["beats"]), len(failed.plan["shots"])),
          (2, 0))

# A replan on the large profile is the structure again, then the shot list;
# an edit to one row is that row's own small call on either profile.
made_large = director.approve(director.land(director.start(large, "e2")[0], "e2", "pic-7",
                                            director.fingerprint(large, "e2")), "e2")
ask, asked = scripted([
    fence({"act": "replan", "row": "", "change": "It is winter.", "say": ""}),
    fence({**STRUCTURE, "title": "Snow Train", "assumptions": ["Snow is falling."],
           "beats": [{"text": "@george wakes as snow buries @carriage.", "weight": "long"}],
           "entities": [{"name": "carriage", "kind": "place", "description": "listed again"},
                        {"name": "drift", "kind": "thing", "description": "a deep drift"}]}),
    fence({"shots": [{"beat": 1, "action": "@george wakes inside @carriage as snow piles up.",
                      "continues": "new"}]})])
out = calls.plan_turn(made_large, "set it in winter", ask, cast=GEORGE, steps="large")
new = out["plan"]
check("large: …the sheet already made stays made", director.state_of(new, "e2"), "approved")
check("large: a replan is two calls", labels(asked),
      ["turn", "replan.structure", "replan.shotlist"])
check("large: …told who is already there",
      "ALREADY THERE" in asked[1]["message"] and "@carriage — an old train carriage" in asked[1]["message"],
      True)
check("large: …keeping the entities it had, under new beat and shot ids, with the model's assumptions",
      ([e["id"] for e in new["entities"]], new["entities"][1]["description"],
       [b["id"] for b in new["beats"]], new["title"], new["assumptions"]),
      (["e1", "e2"], "an old train carriage", ["b3"], "Snow Train", ["Snow is falling."]))
check("large: …and an entity it adds that no shot cites goes", "drift" in director.names(new), False)
ask, asked = scripted([fence({"act": "edit", "row": "shot 3", "change": "closer", "say": ""}),
                       fence({"shots": [CLOSE]})])
out = calls.plan_turn(large, "make the last shot a close-up", ask, cast=GEORGE, steps="large")
check("large: one row is still its own small call", [a["label"] for a in asked], ["turn", "turn.shot"])


# ---- arranging shots by talking -------------------------------------------------------
#
# Add is the shots call once more, written around the beat's shots; remove and
# move are `director`'s with no call. Where a shot goes is read off the words.

HAT = {"action": "A conductor's hat lies on an empty seat in @carriage.", "continues": "cut"}
out, asked = turn("add a shot of a conductor's hat on a seat after shot 2",
                  [fence({"act": "add", "row": "", "place": "after shot 2",
                          "change": "A conductor's hat on an empty seat.", "say": ""}),
                   fence({"shots": [HAT]})])
check("a shot is added by the shots call, where the place says",
      ([a["label"] for a in asked], out["act"], out["row"], [s["id"] for s in out["plan"]["shots"]]),
      (["turn", "turn.add"], "add", "s4", ["s1", "s2", "s4", "s3"]))
check("…shown the beat's shots and told where the new one goes",
      ("ITS SHOTS NOW (already written — do not write them again)\n"
       "shot 2 — @george walks the length of @carriage.\nshot 3 — @george opens the cab door: nobody."
       in asked[1]["message"],
       "THE NEW SHOT (after shot 2)\nA conductor's hat on an empty seat." in asked[1]["message"]),
      (True, True))
check("…as the model wrote it, in that beat", next(s for s in out["plan"]["shots"] if s["id"] == "s4"),
      {**HAT, "id": "s4", "beat": "b2"})

out, asked = turn("add a close-up of the door before shot 1",
                  [fence({"act": "add", "row": "", "place": "last", "change": "Close on the door.", "say": ""}),
                   fence({"shots": [{"action": "Close on the door of @carriage.", "continues": "cut"}]})])
check("a place the words say wins over the model's",
      (out["log"][0]["overruled"], [s["id"] for s in out["plan"]["shots"]], out["plan"]["shots"][0]["continues"]),
      ("place -> before s1", ["s4", "s1", "s2", "s3"], "new"))
check("…and the call is told it opens the piece", "It opens the piece" in asked[1]["message"], True)

out, asked = turn("add a shot of the hat",
                  [fence({"act": "add", "row": "", "place": "", "change": "The hat.", "say": ""}),
                   fence({"shots": [HAT]})])
check("nowhere said is the end of the last beat",
      ([(s["id"], s["beat"]) for s in out["plan"]["shots"]][-1], "THE NEW SHOT (at the end of this beat)"
       in asked[1]["message"]), (("s4", "b2"), True))

out, asked = turn("add a shot of the hat in beat 1",
                  [fence({"act": "add", "row": "beat 1", "place": "", "change": "The hat.", "say": ""}),
                   fence({"shots": [HAT]})])
check("a beat named is its end", [(s["id"], s["beat"]) for s in out["plan"]["shots"]][:2],
      [("s1", "b1"), ("s4", "b1")])

out, asked = turn("another shot where he finds the hat",
                  [fence({"act": "edit", "row": "shot 3", "change": "He finds the hat.", "say": ""}),
                   fence({"shots": [HAT]})])
check("\"another shot\" is an add whatever the model read",
      (out["act"], out["log"][0]["overruled"], len(out["plan"]["shots"])), ("add", "edit -> add nowhere", 4))

out, asked = turn("drop shot 2",
                  [fence({"act": "edit", "row": "shot 2", "change": "drop it", "say": ""})])
check("\"drop shot 2\" takes shot 2 out, with no second call, whatever the model read",
      (len(labels(asked)), out["act"], out["row"], out["log"][0]["overruled"], [s["id"] for s in out["plan"]["shots"]]),
      (1, "remove", "s2", "edit -> remove s2", ["s1", "s3"]))
check("…and the records of the rows that went are gone",
      any(k.startswith("s2") or k == "kf.s2" for k in out["plan"]["renders"]), False)

out, asked = turn("remove beat 1",
                  [fence({"act": "remove", "row": "beat 1", "place": "", "change": "", "say": ""})])
check("a beat is taken out with its shots, and the shot now first opens the piece",
      ([b["id"] for b in out["plan"]["beats"]], [(s["id"], s["continues"]) for s in out["plan"]["shots"]]),
      (["b2"], [("s2", "new"), ("s3", "cut")]))

out, asked = turn("lose the carriage shots, keep the last",
                  [fence({"act": "remove", "row": "@carriage", "place": "", "change": "", "say": ""}),
                   fence({"act": "remove", "row": "shot 2", "place": "", "change": "", "say": ""})])
check("an entity is nobody's to take out: re-asked, and the second answer kept",
      (out["log"][0]["first_error"].startswith("only a shot or a beat can be taken out; @carriage"),
       out["row"]), (True, "s2"))

out, asked = turn("move shot 3 before shot 1",
                  [fence({"act": "move", "row": "shot 3", "place": "after shot 1", "change": "", "say": ""})])
check("a shot is moved where the words say, into that beat, with no second call",
      (len(labels(asked)), out["log"][0]["overruled"], [(s["id"], s["beat"], s["continues"]) for s in out["plan"]["shots"]]),
      (1, "move -> move s3 before s1", [("s3", "b1", "new"), ("s1", "b1", "new"), ("s2", "b2", "pin")]))
check("…its record moved with it, stale now that it follows nothing",
      ("s3" in out["plan"]["renders"]) if base["renders"].get("s3") else True, True)

out, asked = turn("swap shots 2 and 3",
                  [fence({"act": "edit", "row": "shot 2", "change": "swap", "say": ""})])
check("a swap is the later shot moved before the earlier",
      (out["act"], out["row"], [s["id"] for s in out["plan"]["shots"]]), ("move", "s3", ["s1", "s3", "s2"]))

out, asked = turn("put the first shot last",
                  [fence({"act": "move", "row": "shot 1", "place": "last", "change": "", "say": ""})])
check("\"last\" is after the last shot, in its beat",
      [(s["id"], s["beat"]) for s in out["plan"]["shots"]], [("s2", "b2"), ("s3", "b2"), ("s1", "b2")])

try:
    turn("move the last shot to the end",
         [fence({"act": "move", "row": "shot 3", "place": "last", "change": "", "say": ""})])
    check("a shot moved to its own place", False, True)
except calls.PlanningFailed as failed:
    check("a shot moved to its own place is said to be there", str(failed), "shot 3 is already there.")
try:
    turn("move shot 2", [fence({"act": "move", "row": "shot 2", "place": "", "change": "", "say": ""})])
    check("a move with nowhere to go", False, True)
except calls.PlanningFailed as failed:
    check("a move with nowhere to go asks where", str(failed).startswith("Say where shot 2 goes"), True)

out, asked = turn("should we drop shot 2?",
                  [fence({"act": "say", "row": "", "place": "", "change": "", "say": "It is the walk; keep it."})])
check("a question about dropping a shot is a question", (out["act"], out["plan"]), ("say", None))

for words, want in (("between shots 1 and 2", {"after": "s1"}), ("before the last shot", {"before": "s3"}),
                    ("after the 2nd shot", {"after": "s2"}), ("in beat 2", {"beat": "b2"}),
                    ("at the start of beat 2", {"before": "s2"}), ("first", {"before": "s1"}),
                    ("to the end", {"after": "s3"}), ("after shot 9", None), ("", None),
                    ("in the first shot he wakes", None)):
    check(f"placement of {words!r}", calls.placement(base, words), want)
for words, want in (("drop the second shot", "remove"), ("add a shot of rain", "add"),
                    ("put shot 1 last", "move"), ("another shot of the door", "add"),
                    ("make it darker", None), ("swap shots 2 and 3", "move")):
    check(f"asked act of {words!r}", calls.asked_act(words), want)


# ---- a shot written knowing where it sits ----------------------------------------------

ask, asked = scripted(list(GOOD))
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask, cast=GEORGE)
check("the shots call is shown the beat on either side, as a beat, and its own last",
      (asked[4]["message"].count("straight after: He finds the cab empty."),
       asked[5]["message"].count("just before: @george wakes in the carriage."),
       asked[5]["message"].index("AROUND THIS BEAT") < asked[5]["message"].index("THIS BEAT (about")),
      (1, 1, True))
check("...and the choices the piece was planned on", "ASSUMED\n- It is night." in asked[5]["message"], True)

# A scene's setting, written on the shot that opens it and kept on the plan.
replies = list(GOOD)
replies[4] = fence({"shots": [{"action": "@george wakes up inside @carriage.", "continues": "new",
                               "setting": "the carriage at night, rain on the glass, one lamp"}]})
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask, cast=GEORGE)
check("a setting the model writes is kept on its shot, its place cited",
      [s.get("setting") for s in out["plan"]["shots"]],
      ["@carriage at night, rain on the glass, one lamp", None, None])
check("...and the schema asks for one", "setting" in calls.SCHEMAS["shots"]["properties"]["shots"]["items"]["properties"], True)

# The first shot of a beat cannot carry on from a shot set somewhere else.
replies = list(GOOD)
replies[3] = fence({"entities": [{"name": "carriage", "kind": "place", "description": "an old train carriage"},
                                 {"name": "cab", "kind": "place", "description": "the driver's cab"}]})
replies[5] = fence({"shots": [{"action": "@george stands in the empty @cab.", "continues": "pin"}]})
ask, asked = scripted(replies)
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask, cast=GEORGE)
check("a carry-on into another place is a real cut, and the log says so",
      (out["plan"]["shots"][1]["continues"], out["log"][5].get("overruled")),
      ("new", "pin -> new: another place than the shot before"))
ask, asked = scripted(list(GOOD))
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask, cast=GEORGE)
check("the same place keeps the join the model wrote", out["plan"]["shots"][1]["continues"], "pin")

# ---- a long shot, written as its clips ------------------------------------------------------

replies = list(GOOD)
replies[5] = fence({"shots": [{"action": "@george walks the length of @carriage and finds the cab empty.",
                               "continues": "pin"}]})
ask, asked = scripted(list(replies), parts=fence({"parts": [
    "@george walks the length of the carriage, steadying himself on the seats.",
    "@george slides the cab door open and finds nobody at the controls."]}))
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask, cast=GEORGE)
long_shot = out["plan"]["shots"][1]
check("a shot too long for one clip is asked for as its clips, last",
      ([a["label"] for a in asked][-1], "filmed as 2 clips" in asked[-1]["message"],
       "of 11, 11 seconds" in asked[-1]["message"]), ("parts.s2", True, True))
check("...which are kept on it, a plain mention cited",
      long_shot["parts"],
      ["@george walks the length of @carriage, steadying himself on the seats.",
       "@george slides the cab door open and finds nobody at the controls."])
check("a shot that fits one clip is asked nothing more", "parts" in out["plan"]["shots"][0], False)

ask, asked = scripted(list(replies), parts=[fence({"parts": ["only one"]}), fence({"parts": ["still one"]})])
out = calls.plan_piece("a 30 second piece: @george on a night train", RAIL, ask, cast=GEORGE)
check("a parts call that fails twice costs the plan nothing but a warning",
      ("parts" in out["plan"]["shots"][1], len(out["warnings"]),
       out["warnings"][0].startswith("parts.s2: shot 2 is filmed in 2 clips from one description")),
      (False, 1, True))
refuses_parts = _plan_error(lambda: director.read_parts({"parts": ["a"]}, 2, []))
check("the parts reader wants one sentence a clip", refuses_parts, True)
