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
check("keyframe waits for its sheets", deps["kf.s3"], ["e3"])
check("clip deps: sheets, keyframe, previous", deps["s3"], ["e3", "kf.s3", "s2"])
check("a pin has no keyframe", deps["s4"], ["e3", "s3"])
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
      ("@george picks up @pic-2 from a rock pool", ["pic-2:object"]))
clip3 = director.action_for(done, "s3")
check("cut clip opens on its keyframe, after the clip before",
      (clip3["from"], clip3["after"], clip3["seconds"]), (["pic-5:start", "pic-2:object"], "clip-2", 10))
check("cut wording appended", director.CONTINUITY["cut"] in clip3["prompt"], True)
check("a cut goes on the strip as a hard cut, not carried on from the clip before",
      clip3.get(chat.SEAM_KEY), chat.SEAM_CUT)
clip4 = director.action_for(done, "s4")
check("pin clip has no keyframe", (clip4["from"], clip4["after"]), (["pic-2:object"], "clip-3"))
check("pin wording appended", director.CONTINUITY["pin"] in clip4["prompt"], True)
check("a pin carries on", clip4.get(chat.SEAM_KEY), None)
first = director.action_for(done, "s1")
check("the first clip follows nothing", first["after"], None)

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
