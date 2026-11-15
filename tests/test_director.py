"""Director's plan: the arithmetic and bookkeeping the model is never asked for.

    python tests/test_director.py

Pure — no ComfyUI, no model. Everything under test is `creator/director.py`.
What is pinned here is the spec's non-negotiable that *the model never does
arithmetic or bookkeeping*: seconds add up to the target whatever weights
arrive, a shot over the limit is cut into continuation parts and re-cut when
the rail's ceiling moves, a row renders only after what it cites, a redone
sheet makes everything downstream of it stale without anybody marking it, and
every row becomes an action `chat.validate` accepts as it stands.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check  # noqa: E402

pkg = layout.load("prompting", "chat", "director")
director, chat = pkg.director, pkg.chat
subjects = layout.load("subjects").subjects


def refuses(label, call, *fragments):
    try:
        call()
    except director.PlanError as problem:
        for fragment in fragments:
            if fragment not in str(problem):
                FAILURES.append(f"{label}: said {str(problem)!r}, want {fragment!r} in it")
    except Exception as other:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {other!r}, want a PlanError")
    else:
        FAILURES.append(f"{label}: did not refuse")


RAIL = {"still_family": "krea2", "edit_family": "qwenedit", "video_family": "h3",
        "aspect": "16:9", "min_seconds": 1, "max_seconds": 60}


def lighthouse(seconds=40, rail=RAIL, keyframes=True):
    """The spec's example: the keeper is @george, cited by the person; the
    lighthouse and the bottle are made up; three beats."""
    plan = director.new_plan(
        "a lighthouse keeper finds a message in a bottle, rain, moody",
        director.read_basics({"title": "The Bottle", "seconds": seconds,
                              "look": "overcast, desaturated teal, 35mm grain"}),
        rail, cast=["george"], keyframes=keyframes)
    plan = director.add_beats(plan, director.read_beats({"beats": [
        {"text": "the keeper climbs the stairs at dusk", "weight": "medium"},
        {"text": "he finds a bottle on the rocks", "weight": "long"},
        {"text": "he reads the message by lamplight", "weight": "short"},
    ]}))
    plan = director.add_entities(plan, director.read_entities({"entities": [
        {"name": "Lighthouse", "kind": "place", "description": "a white lighthouse on a cliff"},
        {"name": "bottle", "kind": "thing", "description": "a green glass bottle, corked"},
        {"name": "george", "kind": "person", "description": "should be dropped"},
    ]}, cast=["george"]))
    names = director.names(plan)
    plan = director.set_shots(plan, "b1", director.read_shots({"shots": [
        {"action": "@george climbs the spiral stairs of @lighthouse", "continues": "pin"},
    ]}, names))
    plan = director.set_shots(plan, "b2", director.read_shots({"shots": [
        {"action": "@george walks the rocks below @lighthouse", "continues": "new"},
        {"action": "@george picks up @bottle from a rock pool", "continues": "cut"},
    ]}, names))
    plan = director.set_shots(plan, "b3", director.read_shots({"shots": [
        {"action": "@george unrolls the note from @bottle", "continues": "pin"},
    ]}, names))
    return director.validate(plan)


# ---- the cast name rule is the subjects module's --------------------------------

check("NAME_RE is subjects.HANDLE_RE", director.NAME_RE.pattern, subjects.HANDLE_RE.pattern)
check("name_of reads a phrase", director.name_of("Old Keeper"), "old_keeper")
check("name_of drops the @", director.name_of("@Anna"), "anna")
check("name_of refuses a digit start", director.name_of("3 crows"), "")

# ---- allot: whole seconds, exactly the total -------------------------------------

check("allot by weight", director.allot(40, [2, 3, 1]), [13, 20, 7])
check("allot even", director.allot(10, [1, 1, 1]), [4, 3, 3])
check("allot exact", director.allot(12, [1, 1]), [6, 6])
check("allot lifts a floor", director.allot(10, [1, 8, 1], [3, 1, 3]), [3, 4, 3])
for total, weights in ((40, [2, 3, 1]), (7, [1, 1, 1, 1]), (61, [3, 3, 2, 1, 1]), (9, [1, 2])):
    check(f"allot {total} {weights} sums", sum(director.allot(total, weights)), total)
refuses("allot too short", lambda: director.allot(3, [1, 1], [2, 2]), "3 seconds cannot hold 2 parts")

# ---- the model's calls ----------------------------------------------------------

check("basics default seconds", director.read_basics({"title": "T", "look": ""})["seconds"],
      director.DEFAULT_SECONDS)
check("basics: the person's number wins",
      director.read_basics({"title": "T", "seconds": 12}, seconds=40)["seconds"], 40)
check("basics numeric string", director.read_basics({"title": "T", "seconds": "20"})["seconds"], 20)
refuses("basics bool seconds", lambda: director.read_basics({"title": "T", "seconds": True}),
        '"seconds" must be a number')
refuses("basics no title", lambda: director.read_basics({"seconds": 10}), '"title"')
check("one beat is a piece of one moment",
      director.read_beats({"beats": [{"text": "x"}]}), [{"text": "x", "weight": "medium"}])
refuses("no beats", lambda: director.read_beats({"beats": []}), "1 to 8 beats")
refuses("bad weight", lambda: director.read_beats([{"text": "a", "weight": "huge"}, "b"]),
        "beat 1's \"weight\" must be short, medium or long")
check("beat as a string reads as medium", director.read_beats(["a", "b"])[0],
      {"text": "a", "weight": "medium"})
refuses("entity bad kind",
        lambda: director.read_entities([{"name": "x", "kind": "animal", "description": "d"}]),
        "person, place or thing")
check("entity dup dropped",
      len(director.read_entities([{"name": "Cat", "kind": "thing", "description": "d"},
                                  {"name": "cat", "kind": "thing", "description": "e"}])), 1)
refuses("shot cites nobody", lambda: director.read_shots([{"action": "@ghost waves"}], ["keeper"]),
        "cites @ghost", "@keeper")
check("shot cites a ledger handle untouched",
      director.read_shots([{"action": "@keeper holds @pic-2"}], ["keeper"])[0]["action"],
      "@keeper holds @pic-2")
refuses("shot bad join", lambda: director.read_shots([{"action": "x", "continues": "dissolve"}], []),
        "cut, pin or new")

# ---- the plan ---------------------------------------------------------------------

plan = lighthouse()
check("ids minted in order", [b["id"] for b in plan["beats"]], ["b1", "b2", "b3"])
check("entities: cited then new, cast dup dropped", [(e["id"], e["name"]) for e in plan["entities"]],
      [("e1", "george"), ("e2", "lighthouse"), ("e3", "bottle")])
check("first shot is forced new", plan["shots"][0]["continues"], "new")
check("rail snapshot", plan["rail"], {"still": "krea2", "edit": "qwenedit", "video": "h3",
                                       "aspect": "16:9", "min_seconds": 1, "max_seconds": 60,
                                       "references": False})

seconds = director.allot_plan(plan)
check("beats share the 40 s by weight", [seconds[b] for b in ("b1", "b2", "b3")], [13, 20, 7])
check("shots share their beat", [seconds[s] for s in ("s2", "s3")], [10, 10])
check("shots add to the piece", sum(seconds[s["id"]] for s in plan["shots"]), 40)

# Over the limit: s1 (13 s) fits under 15; at a 60 s piece it does not.
long = lighthouse(seconds=90)
cl = director.clips(long)
check("long shots split into parts", [c["id"] for c in cl],
      ["s1.1", "s1.2", "s2.1", "s2.2", "s3.1", "s3.2", "s4"])
check("parts after the first are pins", [c["continues"] for c in cl],
      ["new", "pin", "new", "pin", "cut", "pin", "pin"])
check("every part within the limit", all(c["seconds"] <= 15 for c in cl), True)
check("parts add to the piece", sum(c["seconds"] for c in cl), 90)

# A rail whose video family stops at 10 s re-splits the same plan.
moved_plan, moved = director.follow_rail(plan, {**RAIL, "video_family": "ltx25", "max_seconds": 10})
check("rail change re-splits", [c["id"] for c in director.clips(moved_plan)],
      ["s1.1", "s1.2", "s2", "s3", "s4"])
check("rail change says what moved", moved, ["-s1", "+s1.1", "+s1.2"])
check("rail follows the room", moved_plan["rail"]["video"], "ltx25")
check("the plan's own limit still binds under a high ceiling",
      director.limit_of({**plan, "shot_limit": 8}), 8)

refuses("a beat with no shots",
        lambda: director.validate({**plan, "shots": [s for s in plan["shots"] if s["beat"] != "b3"]}),
        "beat b3 has no shots")
refuses("too many shots for the length", lambda: director.edit(plan, "header", {"seconds": 3}),
        "cannot hold")

# ---- rows and their order ---------------------------------------------------------

every = director.rows(plan)
check("row order", [r["id"] for r in every],
      ["e2", "e3", "kf.s1", "kf.s2", "kf.s3", "s1", "s2", "s3", "s4"])
check("a cited person has no sheet", any(r["id"] == "e1" for r in every), False)
deps = {r["id"]: r["deps"] for r in every}
# s3 is a new angle in the scene s2 opened below the lighthouse, so the
# lighthouse's sheet rides into it though its words name only the bottle.
check("keyframe waits for its sheets, its scene's place among them", deps["kf.s3"], ["e3", "e2"])
check("clip deps: sheets, keyframe, previous", deps["s3"], ["e3", "e2", "kf.s3", "s2"])
check("a pin has no keyframe", deps["s4"], ["e3", "e2", "s3"])
for row in every:
    at = [r["id"] for r in every].index(row["id"])
    for dep in row["deps"]:
        if [r["id"] for r in every].index(dep) >= at:
            FAILURES.append(f"{row['id']} comes before its dep {dep}")
off = lighthouse(keyframes=False)
check("storyboard off: no keyframes at all",
      [r["id"] for r in director.rows(off) if r["kind"] == "keyframe"], [])
check("...so a clip opens from what it cites, its sheets and the clip before",
      all(not d.startswith("kf.") for r in director.rows(off) for d in r["deps"]), True)
check("the storyboard starts off for a video family that takes references",
      director.new_plan("b", {"title": "T", "seconds": 10, "look": ""},
                        {**RAIL, "references": True})["keyframes"], False)
check("...and on for one that takes none",
      director.new_plan("b", {"title": "T", "seconds": 10, "look": ""},
                        {**RAIL, "references": False})["keyframes"], True)
check("...unless the person said",
      director.new_plan("b", {"title": "T", "seconds": 10, "look": ""},
                        {**RAIL, "references": True}, keyframes=True)["keyframes"], True)
check("the rail snapshot keeps whether it takes references",
      director.follow_rail({}, {**RAIL, "references": True})[0]["rail"]["references"], True)

# ---- states, approval, staleness ----------------------------------------------------

st = director.states(plan)
check("fresh plan: all planned, cited approved",
      (st["e1"], st["e2"], st["kf.s1"], st["s1"]), ("approved", "planned", "planned", "planned"))
check("Run disabled before prep", director.can_run(plan), False)
check("prep starts with the sheets", director.prep_steps(plan), ["e2", "e3"])


check("a description's leading article reads inside the sentence",
      [director._inline(d) for d in ("A man in his forties.", "An old coat", "The bay", "Anna's coat.", "A")],
      ["a man in his forties", "an old coat", "the bay", "Anna's coat", "A"])


def render(plan, row_id, handle):
    plan, mark = director.start(plan, row_id)
    return director.land(plan, row_id, handle, mark)


p = render(plan, "e2", "pic-1")
check("a landed sheet waits", director.state_of(p, "e2"), "pending")
refuses("approve a planned row", lambda: director.approve(p, "e3"), "not waiting for approval")
p = director.approve(p, "e2")
check("approved", director.state_of(p, "e2"), "approved")
check("kf.s1 cites only e2, so it is ready", director.prep_steps(p), ["e3", "kf.s1", "kf.s2"])
p = director.approve(render(p, "e3", "pic-2"), "e3")
for i, row in enumerate(("kf.s1", "kf.s2", "kf.s3")):
    p = director.approve(render(p, row, f"pic-{3 + i}"), row)
check("Run enabled once prep is approved", director.can_run(p), True)
check("run steps in order", director.run_steps(p), ["s1", "s2", "s3", "s4"])
check("next step", director.next_step(p), "s1")

running, mark = director.start(p, "s1")
check("one at a time", director.next_step(running), None)
p = director.land(running, "s1", "clip-1", mark)
check("a landed clip is done", director.state_of(p, "s1"), "approved")
p = director.fail(director.start(p, "s2")[0], "s2", "out of memory")
check("failed", director.state_of(p, "s2"), "failed")
check("Run continues from the failure", director.next_step(p), "s2")
for i, row in enumerate(("s2", "s3", "s4")):
    p = render(p, row, f"clip-{2 + i}")
check("all done", (director.run_steps(p), director.next_step(p)), ([], None))
done = p

# Redoing the bottle's sheet: a new handle, so its keyframe, and every clip
# from there down the strip, are stale. Nothing else is.
p = render(done, "e3", "pic-9")
st = director.states(p)
check("redo leaves the sheet pending", st["e3"], "pending")
check("redo stales what cites it, down the strip",
      {k: v for k, v in st.items() if v == "stale"},
      {"kf.s3": "stale", "s3": "stale", "s4": "stale"})
check("Run disabled until the redo is approved", director.can_run(p), False)
p = director.approve(p, "e3")
check("the stale keyframe is prep again", director.prep_steps(p), ["kf.s3"])

# An edit to one shot stales it and what follows; a rename stales nothing.
p = director.edit(done, "s2", {"action": "@george runs across the rocks below @lighthouse"})
check("shot edit stales the strip from there",
      sorted(k for k, v in director.states(p).items() if v == "stale"), ["kf.s2", "s2", "s3", "s4"])
p = render(director.approve(render(p, "kf.s2", "pic-8"), "kf.s2"), "s2", "clip-6")
check("re-rendering the edited shot leaves the next one stale",
      sorted(k for k, v in director.states(p).items() if v == "stale"), ["s3", "s4"])
check("and the run picks up there", director.next_step(p), "s3")
p = director.edit(done, "e2", {"name": "Tower"})
check("rename rewrites citations", p["shots"][0]["action"], "@george climbs the spiral stairs of @tower")
check("rename stales nothing", [k for k, v in director.states(p).items() if v == "stale"], [])
refuses("rename onto another", lambda: director.edit(done, "e2", {"name": "bottle"}), "already in the plan")
refuses("edit a derived row", lambda: director.edit(done, "s1.2", {"action": "x"}), "not a row that can be edited")
refuses("edit an unknown field", lambda: director.edit(done, "b1", {"seconds": 3}), "has no field 'seconds'")

# "use @anna for the bottle" is refused; a person can be recast, which drops the sheet.
refuses("cast a thing", lambda: director.edit(done, "e3", {"source": "anna"}), "only a person")
cast_plan = director.add_entities(plan, [{"name": "girl", "kind": "person", "description": "a girl"}])
check("a new person has a sheet", any(r["id"] == "e4" for r in director.rows(cast_plan)), True)
recast = director.edit(cast_plan, "e4", {"source": "@anna"})
check("recast drops the sheet", any(r["id"] == "e4" for r in director.rows(recast)), False)
check("recast reads as cast", "anna" in director.cast_of(recast), True)
recast = director.set_shots(recast, "b3", [{"action": "@girl hands @george the note", "continues": "pin"}])
check("a recast entity is cited as its member",
      director._resolve(recast, "@girl hands @george the note", {})[0], "@anna hands @george the note")

# A header change moves every second.
check("seconds edit re-allots", sum(c["seconds"] for c in director.clips(
    director.edit(plan, "header", {"seconds": 24}))), 24)

# ---- ids are never reused ----------------------------------------------------------

again = director.set_shots(plan, "b3", [{"action": "@george reads", "continues": "pin"}])
check("replacing a beat's shots mints a new id", [s["id"] for s in again["shots"]][-1], "s5")

# ---- rows -> actions the room accepts ----------------------------------------------

LEDGER = [{"handle": f"pic-{n}", "kind": "still", "filename": f"p{n}.png"} for n in range(1, 10)] + \
         [{"handle": f"clip-{n}", "kind": "clip", "filename": f"c{n}.mp4"} for n in range(1, 6)]
CAST = director.cast_of(done)
check("cast_of", CAST, ["george"])
handles = director.handles_of(done)

sheet = director.action_for(done, "e2")
check("sheet prompt", sheet["prompt"],
      "Empty establishing view of a white lighthouse on a cliff. Wide shot, no people, nothing "
      "happening, the whole place readable.\n\nLook: overcast, desaturated teal, 35mm grain.")
kf = director.action_for(done, "kf.s3")
check("keyframe resolves cast and entities", (kf["prompt"].split("\n")[0], kf["from"]),
      ("@george picks up @pic-2 from a rock pool", ["pic-2:object", "pic-1:scene"]))
check("...and is set in its scene's place", "Setting: @pic-1." in kf["prompt"], True)
clip3 = director.action_for(done, "s3")
check("cut clip opens on its keyframe, after the clip before",
      (clip3["from"], clip3["after"], clip3["seconds"]), (["pic-5:start", "pic-2:object", "pic-1:scene"], "clip-2", 10))
check("cut wording appended", director.CONTINUITY["cut"] in clip3["prompt"], True)
check("a cut goes on the strip as a hard cut, not carried on from the clip before",
      clip3.get(chat.SEAM_KEY), chat.SEAM_CUT)
clip4 = director.action_for(done, "s4")
check("pin clip has no keyframe", (clip4["from"], clip4["after"]),
      (["pic-2:object", "pic-1:scene"], "clip-3"))
check("a pin is told what the clip before it showed, in plain words",
      "which showed: george picks up bottle from a rock pool." in clip4["prompt"], True)
check("a pin carries on", clip4.get(chat.SEAM_KEY), None)
first = director.action_for(done, "s1")
check("the first clip follows nothing", first["after"], None)

# The camera: how every shot is filmed, when the brief said. It goes on the
# shots' prompts and not on the sheets, and a plan without one fingerprints
# exactly as plans did before the field.
check("basics read a camera", director.read_basics(
    {"title": "T", "seconds": 10, "look": "", "camera": "first-person, through the visor"})["camera"],
    "first-person, through the visor")
check("basics without one read it as empty", director.read_basics({"title": "T", "look": ""})["camera"], "")
pov = director.edit(done, director.HEADER, {"camera": "first-person view through George's eyes"})
check("a clip carries the camera before the look", director.action_for(pov, "s1")["prompt"].split("\n\n")[1:],
      ["Camera: first-person view through George's eyes.", "Look: overcast, desaturated teal, 35mm grain."])
check("a keyframe carries it too", "Camera:" in director.action_for(pov, "kf.s3")["prompt"], True)
check("a sheet does not", director.action_for(pov, "e2")["prompt"], sheet["prompt"])
check("a sheet's fingerprint ignores the camera",
      director.fingerprint(pov, "e2"), director.fingerprint(done, "e2"))
check("a shot's fingerprint holds it", director.fingerprint(pov, "s1") != director.fingerprint(done, "s1"), True)
check("an empty camera is no camera",
      director.fingerprint(director.edit(done, director.HEADER, {"camera": ""}), "s1"),
      director.fingerprint(done, "s1"))

strip = [handles[c["id"]] for c in director.clips(done)]
for row in director.rows(done):
    action = director.action_for(done, row["id"])
    try:
        valid = chat.validate(action, LEDGER, strip=strip, cast=CAST)
    except chat.ActionError as problem:
        FAILURES.append(f"{row['id']}: chat refused the action: {problem}")
        continue
    check(f"{row['id']} survives chat.validate, the hard cut put back by with_seam",
          chat.with_seam(valid, action), action)
check("actions carry the chat's fields", sorted(sheet), sorted(chat.FIELDS))

refuses("a row before its deps", lambda: director.action_for(plan, "kf.s1"), "needs e2")

change = director.change_action(done, "e3", "make @bottle blue")
check("a sheet change edits the old picture, the name said plainly",
      (change["from"], change["prompt"]), (["pic-2"], "make bottle blue"))
frame = director.change_action(done, "kf.s3", "a lower angle")
check("an opening frame is changed the same way", frame["from"], [done["renders"]["kf.s3"]["handle"]])
refuses("a clip is not changed on the edit path", lambda: director.change_action(done, "s3", "x"),
        "not a picture made for approval")
refuses("a picture not made yet", lambda: director.change_action(plan, "e3", "x"), "no picture")

stray = {**done, "renders": {**done["renders"], "s9": {"handle": "clip-9", "state": "approved"}}}
check("prune drops the records of rows the plan no longer has",
      sorted(director.prune(stray)["renders"]), sorted(done["renders"]))


# ---- one take, and when a chat request is planned ----------------------------
#
# Chained shots are the default for a long piece; one unbroken take is allowed
# up to what the video family itself renders, and asked for in plain words.

for said in ("one continuous shot of the sea", "a single take, 30 seconds", "a oner down the hall",
             "no cuts", "an unbroken 40 s shot", "film it in one go"):
    check(f"one take is read in {said!r}", director.asks_one_take(said), True)
check("a plain request asks for no one take", director.asks_one_take("a 40 second spot of the sea"), False)
for said in ("three shots of a fox", "2 quick shots", "a few shots of rain", "a montage of the city",
             "several cuts between them"):
    check(f"many shots are read in {said!r}", director.asks_many_shots(said), True)
for said in ("a shot of a fox", "one shot", "make shot 3 darker", "1 shots"):
    check(f"no many shots in {said!r}", director.asks_many_shots(said), False)

CLIP = {"act": "render", "kind": "video", "prompt": "the sea", "from": [], "seconds": 40,
        "aspect": None, "say": "", "after": None, "replaces": None}
check("a 40 s clip is planned as a piece", director.wants_plan(CLIP, "a 40 second spot", 60),
      director.TOO_LONG)
check("a 40 s clip asked as one take is rendered as one",
      director.wants_plan(CLIP, "one continuous 40 second shot", 60), None)
check("one take or not, past the family's ceiling it is planned",
      director.wants_plan({**CLIP, "seconds": 90}, "one continuous 90 second shot", 60),
      director.OVER_CEILING)
check("a clip at the limit is rendered", director.wants_plan({**CLIP, "seconds": 15}, "x", 60), None)
check("three shots named are planned", director.wants_plan({**CLIP, "seconds": 8}, "three shots of a fox", 60),
      director.MANY_SHOTS)
check("a clip after one on the strip is never planned",
      director.wants_plan({**CLIP, "after": "clip-1"}, "a 40 second spot", 60), None)
check("a clip in place of one is never planned",
      director.wants_plan({**CLIP, "replaces": "clip-1"}, "make it 40 seconds", 60), None)
check("a still is never planned", director.wants_plan({**CLIP, "kind": "still"}, "three shots", 60), None)

took = director.edit(lighthouse(seconds=60), "s2", {"one_take": True})
parts = [c for c in director.clips(took) if c["shot"] == "s2"]
check("a one-take shot runs to the family's ceiling uncut", [c["parts"] for c in parts], [1])
check("its neighbours still split at the plan's limit",
      all(c["seconds"] <= director.SHOT_LIMIT for c in director.clips(took) if c["shot"] != "s2"), True)
long_take = director.edit(director.edit(took, director.HEADER, {"seconds": 200}), "s2", {"one_take": True})
check("a one take past the ceiling is cut there, into pins",
      [(c["seconds"] <= 60, c["continues"]) for c in director.clips(long_take) if c["shot"] == "s2"][1:],
      [(True, "pin")] * (len([c for c in director.clips(long_take) if c["shot"] == "s2"]) - 1))
check("one take off again leaves no field behind",
      "one_take" in next(s for s in director.edit(took, "s2", {"one_take": False})["shots"]
                         if s["id"] == "s2"), False)
check("one take on a shot is all an edit needs: the action stays",
      next(s for s in took["shots"] if s["id"] == "s2")["action"],
      next(s for s in lighthouse(seconds=60)["shots"] if s["id"] == "s2")["action"])


# ---- arranging shots: added, taken out, moved ---------------------------------------
#
# Rows are named by id, so a shot that moves keeps its record, and what moved
# around it goes stale on its own: the clip behind it now follows another
# clip's handle. A beat is where its shots are; one left empty goes.

CLOSE = {"action": "close on @bottle in @george's hand", "continues": "cut"}
added = director.add_shot(done, CLOSE, beat="b2")
check("a shot added to a beat goes at its end, under a new id",
      [(s["id"], s["beat"]) for s in added["shots"]],
      [("s1", "b1"), ("s2", "b2"), ("s3", "b2"), ("s5", "b2"), ("s4", "b3")])
check("…and the seconds still add up", sum(c["seconds"] for c in director.clips(added)), 40)
st = director.states(added)
check("…the beat's other shots are stale (shorter), the one before the beat is not",
      (st["s1"], st["s2"], st["s3"], st["s5"]), ("approved", "stale", "stale", "planned"))
check("…and so is the clip now behind the new shot", st["s4"], "stale")
check("a shot added before another goes in that shot's beat, before it",
      [s["id"] for s in director.add_shot(done, CLOSE, before="s2")["shots"]], ["s1", "s5", "s2", "s3", "s4"])
check("…after another, after it, in its beat",
      [(s["id"], s["beat"]) for s in director.add_shot(done, CLOSE, after="s4")["shots"]][-1], ("s5", "b3"))
check("a shot added before the first opens the piece as new",
      director.add_shot(done, CLOSE, before="s1")["shots"][0]["continues"], "new")
refuses("a shot with nowhere to go", lambda: director.add_shot(done, CLOSE), "say where")
refuses("a shot with two places to go", lambda: director.add_shot(done, CLOSE, before="s1", after="s2"),
        "say where")
refuses("a shot placed by a shot that is not there", lambda: director.add_shot(done, CLOSE, after="s9"),
        "no shot s9")
refuses("a shot placed in a beat that is not there", lambda: director.add_shot(done, CLOSE, beat="b9"),
        "no beat b9")

less = director.remove_shot(done, "s3")
check("a shot taken out leaves the others as they were",
      [s["id"] for s in less["shots"]], ["s1", "s2", "s4"])
check("…its records go with it", sorted(k for k in less["renders"] if k in ("s3", "kf.s3")), [])
st = director.states(less)
check("…what came before it is still current, what came after is stale; the shot left alone in "
      "its beat has the whole beat now, which is over the limit, so it is cut in two",
      (st["s1"], sorted(k for k in st if k.startswith("s2")), st["s4"]),
      ("approved", ["s2.1", "s2.2"], "stale"))
alone = director.remove_shot(done, "s1")
check("a beat's last shot takes the beat with it",
      ([b["id"] for b in alone["beats"]], [s["id"] for s in alone["shots"]]), (["b2", "b3"], ["s2", "s3", "s4"]))
check("…and the shot now first opens the piece", alone["shots"][0]["continues"], "new")
refuses("a shot the plan does not have", lambda: director.remove_shot(done, "s9"), "no shot s9")
single = director.new_plan("one", director.read_basics({"title": "One", "seconds": 6, "look": ""}), RAIL)
single = director.set_shots(director.add_beats(single, [{"text": "a heron", "weight": "medium"}]), "b1",
                            [{"action": "a heron lifts off", "continues": "new"}])
refuses("the plan's only shot", lambda: director.remove_shot(single, "s1"), "only shot")
refuses("the plan's only beat", lambda: director.remove_beat(single, "b1"), "only beat")
check("a beat taken out takes its shots",
      [s["id"] for s in director.remove_beat(done, "b2")["shots"]], ["s1", "s4"])

moved = director.move_shot(done, "s4", before="s1")
check("a shot moved before the first opens the piece, in the first beat, and its empty beat goes",
      ([(s["id"], s["beat"], s["continues"]) for s in moved["shots"]], [b["id"] for b in moved["beats"]]),
      ([("s4", "b1", "new"), ("s1", "b1", "new"), ("s2", "b2", "new"), ("s3", "b2", "cut")], ["b1", "b2"]))
check("…its record moved with it", moved["renders"]["s4"]["handle"], done["renders"]["s4"]["handle"])
check("…stale, since it follows nothing now, and everything behind it is too",
      [k for k, v in director.states(moved).items() if v == "stale" and k.startswith("s")],
      ["s4", "s1", "s2", "s3"])
within = director.move_shot(done, "s2", after="s3")
check("a shot moved within its beat", [s["id"] for s in within["shots"]], ["s1", "s3", "s2", "s4"])
check("…before a later one", [s["id"] for s in director.move_shot(done, "s1", before="s3")["shots"]],
      ["s2", "s1", "s3", "s4"])
check("…before an earlier one", [s["id"] for s in director.move_shot(done, "s3", before="s2")["shots"]],
      ["s1", "s3", "s2", "s4"])
check("…to its own place is no move", [s["id"] for s in director.move_shot(done, "s2", before="s3")["shots"]],
      [s["id"] for s in done["shots"]])
check("…to the end of another beat", [(s["id"], s["beat"]) for s in director.move_shot(done, "s1", beat="b3")["shots"]],
      [("s2", "b2"), ("s3", "b2"), ("s4", "b3"), ("s1", "b3")])
refuses("a shot moved next to itself", lambda: director.move_shot(done, "s2", after="s2"), "next to itself")
refuses("a shot that is not there moved", lambda: director.move_shot(done, "s9", before="s1"), "no shot s9")

check("an id freed by a removal is never minted again",
      director.add_shot(director.remove_shot(done, "s4"), CLOSE, beat="b2")["shots"][-1]["id"], "s5")

check("arrange: add reads the words as a model's",
      director.arrange(done, "add", beat="b2", action="close on @bottle", continues="cut")["shots"][3]["action"],
      "close on @bottle")
refuses("arrange: an added shot citing nobody", lambda: director.arrange(
    done, "add", beat="b2", action="close on @nobody", continues="cut"), "cites @nobody")
check("arrange: remove a shot", len(director.arrange(done, "remove", shot="s3")["shots"]), 3)
check("arrange: remove a beat", len(director.arrange(done, "remove", beat="b2")["beats"]), 2)
check("arrange: move", director.arrange(done, "move", shot="s4", before="s1")["shots"][0]["id"], "s4")
refuses("arrange: something else", lambda: director.arrange(done, "swap", shot="s1"), "add, remove or move")

# ---- scenes: a place and a setting carried through the shots of one ---------------------


def kitchen(seconds=30, keyframes=False, rail=RAIL, weights=("medium", "medium")):
    """Two scenes. The first opens in the kitchen and has a new angle and a
    carry-on that never name it; the second is somewhere else."""
    doc = director.new_plan("a cook burns the soup", director.read_basics(
        {"title": "Soup", "seconds": seconds, "look": "warm"}), rail, keyframes=keyframes)
    doc = director.add_beats(doc, director.read_beats(
        [{"text": "she cooks", "weight": weights[0]}, {"text": "she leaves", "weight": weights[1]}]))
    doc = director.add_entities(doc, director.read_entities([
        {"name": "cook", "kind": "person", "description": "a cook in whites"},
        {"name": "kitchen", "kind": "place", "description": "a narrow steel kitchen"},
        {"name": "yard", "kind": "place", "description": "a wet back yard"}]))
    names = director.names(doc)
    doc = director.set_shots(doc, "b1", director.read_shots([
        {"action": "@cook stirs a pot in @kitchen. Wide.", "continues": "new",
         "setting": "late evening service, steam, hard overhead light."},
        {"action": "@cook's hand lifts the spoon. Close.", "continues": "cut"},
        {"action": "@cook tastes it and winces.", "continues": "pin"}], names))
    doc = director.set_shots(doc, "b2", director.read_shots([
        {"action": "@cook steps out into @yard and lights a cigarette.", "continues": "new"}], names))
    return director.validate(doc)


soup = kitchen()
check("a scene runs from one real cut to the next",
      [[s["id"] for s in scene] for scene in director.scenes(soup)], [["s1", "s2", "s3"], ["s4"]])
check("a setting is kept on the shot that wrote it, and only there",
      [s.get("setting") for s in soup["shots"]],
      ["late evening service, steam, hard overhead light.", None, None, None])
held = director.scenery(soup)
check("a shot that names its place inherits none; the others take the scene's",
      [(held[s][0] or {}).get("name") for s in ("s1", "s2", "s3", "s4")],
      [None, "kitchen", "kitchen", None])
check("the setting line cites the place a shot did not",
      [director.setting_line(soup, s) for s in soup["shots"]],
      ["Setting: late evening service, steam, hard overhead light.",
       "Setting: @kitchen — late evening service, steam, hard overhead light.",
       "Setting: @kitchen — late evening service, steam, hard overhead light.", ""])
soup_deps = {r["id"]: r["deps"] for r in director.rows(soup)}
check("so the place's sheet is something every shot of the scene waits for",
      (soup_deps["s2"], soup_deps["s3"], soup_deps["s4"]),
      (["e1", "e2", "cut.s2", "s1"], ["e1", "e2", "s2"], ["e1", "e3", "s3"]))
refuses("a setting citing nobody", lambda: director.edit(soup, "s1", {"setting": "in @cellar"}),
        "cites @cellar")
check("a setting can be taken off again",
      "setting" in director.edit(soup, "s1", {"setting": ""})["shots"][0], False)
check("an edit to the action keeps the setting",
      director.edit(soup, "s1", {"action": "@cook salts a pot in @kitchen."})["shots"][0]["setting"],
      "late evening service, steam, hard overhead light.")


def through(doc, upto):
    """`doc` with its sheets approved and its clips landed up to `upto`."""
    pictures = clips = 0
    for row in director.rows(doc):
        if row["kind"] == "sheet":
            pictures += 1
            doc = director.approve(render(doc, row["id"], f"pic-{pictures}"), row["id"])
    for row in director.rows(doc):
        if row["kind"] != "clip":
            continue
        if row["id"] == upto:
            break
        clips += 1
        doc = render(doc, row["id"], f"clip-{clips}")
    return doc


plain = director.edit(soup, "header", {"match_cuts": False})
ready = through(soup, "s2")
angle2 = director.action_for(through(plain, "s2"), "s2")
check("a new angle is sent the scene's place though its words never name it",
      angle2["from"], ["pic-2:scene"])
check("...and is told what must not change, not about a shot it was never shown",
      (director.CONTINUITY["cut"] in angle2["prompt"], "previous" in angle2["prompt"]), (True, False))
check("...with the setting after its own words and before the look",
      angle2["prompt"].split("\n\n")[1:],
      ["Setting: @pic-2 — late evening service, steam, hard overhead light.", "Look: warm."])

# A setting changes what the scene's shots render from, so it stales them; a
# plan with no setting and no place to inherit hashes as it always did.
check("a setting edited stales every shot of its scene and nothing before it",
      [director.fingerprint(soup, r) != director.fingerprint(
          director.edit(soup, "s1", {"setting": "dawn"}), r) for r in ("e1", "s1", "s2", "s3")],
      [False, True, True, True])

# ---- a long shot, written as its clips ----------------------------------------------------

long_soup = director.edit(kitchen(seconds=35, weights=("short", "long")), "header", {"shot_limit": 7})
split = [c for c in director.clips(long_soup) if c["shot"] == "s4"]
check("the last shot is cut in parts", [c["id"] for c in split], ["s4.1", "s4.2", "s4.3", "s4.4"])
check("unwritten, every part is the whole action and says so",
      director.part_text(long_soup["shots"][3], 2, 4),
      ("@cook steps out into @yard and lights a cigarette.", False))
parted = director.edit(long_soup, "s4", {"parts": [
    "@cook pushes the door open and steps into @yard.", "@cook shakes a cigarette from the pack.",
    "@cook lights it, cupping the flame.", "@cook breathes out and leans on the wall."]})
check("written, each part is its own sentence",
      director.part_text(parted["shots"][3], 3, 4), ("@cook lights it, cupping the flame.", True))
refuses("a part citing nobody",
        lambda: director.edit(long_soup, "s4", {"parts": ["@ghost waves", "b", "c", "d"]}), "cites @ghost")
check("parts written for another split are not used",
      director.part_text({**parted["shots"][3], "parts": ["a", "b"]}, 1, 4)[1], False)
check("a new action drops the parts written for the old one",
      "parts" in director.edit(parted, "s4", {"action": "@cook kicks a can across @yard."})["shots"][3],
      False)
check("...and the same action said again keeps them",
      len(director.edit(parted, "s4", {"action": parted["shots"][3]["action"]})["shots"][3]["parts"]), 4)
check("writing the parts stales the clips of that shot and no other",
      sorted(r["id"] for r in director.rows(parted)
             if director.fingerprint(parted, r["id"]) != director.fingerprint(long_soup, r["id"])),
      ["s4.1", "s4.2", "s4.3", "s4.4"])


third = director.action_for(through(parted, "s4.3"), "s4.3")
check("a written part is its own words, told what the part before showed",
      (third["prompt"].split("\n\n")[0],
       "which showed: cook shakes a cigarette from the pack." in third["prompt"]),
      ("@cook lights it, cupping the flame.", True))
whole = director.action_for(through(long_soup, "s4.3"), "s4.3")
check("an unwritten part is told which part of the shot it is, and not to begin again",
      (director.PART.format(part=3, parts=4) in whole["prompt"], "which showed" in whole["prompt"]),
      (True, False))
check("the first part of a shot says neither",
      "Continuity" in director.action_for(through(long_soup, "s4.1"), "s4.1")["prompt"], False)

# ---- a cut that opens on the frame before it -----------------------------------------------

check("a new plan matches its cuts", soup["match_cuts"], True)
angled = director.rows(soup)
check("with the storyboard off and an edit family, a cut gets an angle row in front of it",
      [(r["id"], r["kind"], r["phase"]) for r in angled if r["phase"] == "run"],
      [("s1", "clip", "run"), ("cut.s2", "angle", "run"), ("s2", "clip", "run"),
       ("s3", "clip", "run"), ("s4", "clip", "run")])
check("the angle waits for the clip before; the cut waits for the angle",
      ({r["id"]: r["deps"] for r in angled}["cut.s2"], soup_deps["s2"]), (["s1"], ["e1", "e2", "cut.s2", "s1"]))
check("off on the card, there is none",
      [r["id"] for r in director.rows(director.edit(soup, "header", {"match_cuts": False}))
       if r["kind"] == "angle"], [])
check("a plan written before the switch has none",
      [r["id"] for r in director.rows({k: v for k, v in soup.items() if k != "match_cuts"})
       if r["kind"] == "angle"], [])
check("a rail with no edit family has none",
      [r["id"] for r in director.rows(kitchen(rail={k: v for k, v in RAIL.items() if k != "edit_family"}))
       if r["kind"] == "angle"], [])
check("the storyboard's own opening frame stands in its place",
      [r["kind"] for r in director.rows(kitchen(keyframes=True)) if r.get("shot") == "s2"],
      ["keyframe", "clip"])
turn = director.action_for(ready, "cut.s2")
check("the angle is the frame the clip before ended on, changed in place",
      (turn["kind"], turn["from"], turn[chat.GRAB_KEY]), ("still", ["clip-1"], chat.GRAB_LAST))
check("...asked for in the shot's own words, names plain",
      turn["prompt"], director.ANGLE.format(action="cook's hand lifts the spoon. Close."))
ready = render(ready, "cut.s2", "pic-9")
check("an angle is the run's: landed, it is approved with nobody asked",
      director.state_of(ready, "cut.s2"), "approved")
check("the cut opens on it", director.action_for(ready, "s2")["from"], ["pic-9:start", "pic-2:scene"])
check("the run renders the angle between the two clips",
      director.run_steps(soup), ["s1", "cut.s2", "s2", "s3", "s4"])

# ---- clips that carry straight on, rendered as one piece ------------------------------------

check("a clip is queued with the clips that carry on from it",
      director.chain(through(plain, "s2"), "s2"), ["s2", "s3"])
check("a cut ends the chain: it opens on its own picture",
      director.chain(through(plain, "s1"), "s1"), ["s1"])
check("a still is always alone", director.chain(soup, "e1"), ["e1"])
tail = through(director.edit(long_soup, "header", {"match_cuts": False}), "s4.1")
check("...up to the limit, and no further",
      (director.CHAIN_LIMIT, director.chain(tail, "s4.1")), (4, ["s4.1", "s4.2", "s4.3", "s4.4"]))
check("a clip already rendered ends the chain in front of it",
      director.chain(render(tail, "s4.3", "clip-40"), "s4.1"), ["s4.1", "s4.2"])
queued, made = director.start_chain(tail, ["s4.1", "s4.2", "s4.3"], ["clip-7", "clip-8", "clip-9"])
check("a chain's rows are all rendering", [director.state_of(queued, r) for r, _m, _a in made],
      ["rendering"] * 3)
check("each row behind the first continues from the handle reserved for the one before",
      [a["after"] for _r, _m, a in made], ["clip-3", "clip-7", "clip-8"])
landing = queued
for (row, mark, _action), handle in zip(made, ["clip-7", "clip-8", "clip-9"]):
    landing = director.land(landing, row, handle, mark)
check("...and lands current under the mark it was queued with",
      [director.state_of(landing, r) for r, _m, _a in made], ["approved"] * 3)
check("nothing is ready while a chain renders", director.next_step(queued), None)
