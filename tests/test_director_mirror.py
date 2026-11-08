"""The plan card's arithmetic is `director.py`'s.

    python3 tests/test_director_mirror.py

The card works out a plan's seconds, its clip splits and its rows itself
(`web/creator/director.js`), so a weight changed on it shows its seconds before
the server has answered. That is only honest while the two agree to the
second: a card that says a shot runs 8 s when the run renders 7 is a plan that
lies about itself, and nothing else would catch it — the server never sees
what the card drew.

So the same plans go to both sides: real ones built through `director.py`'s own
readers, the edges where the arithmetic has a decision to make (a tie in the
remainders, a floor that lifts a share, a shot split at the limit, a rail
whose video family clamps the limit or raises the floor, the keyframes toggle
off), and a few hundred `allot` calls over awkward weights. Python is
authoritative.

Skips itself if node is not installed.
"""

import random

import layout

layout.skip_without_node()

MIRROR = layout.js("director.js")

director = layout.load("prompting", "chat", "director").director

from harness import FAILURES, check, passed  # noqa: E402


def plan(seconds, beats, shots, rail=None, keyframes=True, limit=15, entities=()):
    """A plan through the module's own builders. `beats` is `[weight]`,
    `shots` is `{beat index: [(action, continues)]}`."""
    doc = director.new_plan("a brief", {"title": "T", "seconds": seconds, "look": ""},
                            rail or {"still": "krea2", "video": "h3"},
                            keyframes=keyframes, shot_limit=limit)
    doc = director.add_beats(doc, [{"text": f"beat {i}", "weight": w} for i, w in enumerate(beats)])
    doc = director.add_entities(doc, [dict(e) for e in entities])
    for at, beat in enumerate(doc["beats"]):
        doc = director.set_shots(doc, beat["id"],
                                 [{"action": a, "continues": c} for a, c in shots.get(at, [])])
    return director.validate(doc)


KEEPER = {"name": "keeper", "kind": "person", "description": "an old keeper"}
BOTTLE = {"name": "bottle", "kind": "thing", "description": "a green bottle"}
COAST = {"name": "coast", "kind": "place", "description": "a rocky coast"}

PLANS = {
    "one beat, one shot": plan(6, ["medium"], {0: [("a heron lifts off", "new")]}),
    "three beats": plan(40, ["medium", "short", "long"], {
        0: [("@keeper climbs the stairs", "new"), ("@keeper reaches the lamp", "pin")],
        1: [("@keeper sees @bottle on @coast", "cut")],
        2: [("@keeper reads the note", "new"), ("close on the note", "cut"), ("he looks up", "pin")],
    }, entities=(KEEPER, BOTTLE, COAST)),
    "a shot over the limit": plan(40, ["medium"], {0: [("one long take", "new")]}),
    "just at the limit": plan(15, ["medium"], {0: [("one take", "new")]}),
    "the rail clamps the limit": plan(30, ["short", "long"], {
        0: [("a", "new")], 1: [("b", "cut")]}, rail={"video": "x", "max_seconds": 8}),
    "the rail raises the floor": plan(12, ["short", "long"], {
        0: [("a", "new"), ("b", "cut")], 1: [("c", "pin"), ("d", "cut")]},
        rail={"video": "x", "min_seconds": 2.5, "max_seconds": 10}),
    "keyframes off": plan(20, ["medium", "medium"], {
        0: [("@keeper waits", "new")], 1: [("@keeper turns", "cut")]},
        keyframes=False, entities=(KEEPER,)),
    "a tie in the remainders": plan(10, ["short", "short", "short"], {
        0: [("a", "new")], 1: [("b", "cut")], 2: [("c", "cut")]}),
    "a long piece": plan(600, ["long", "short", "medium", "long"], {
        0: [("a", "new")], 1: [("b", "cut")], 2: [("c", "new")], 3: [("d", "pin")]}, limit=60),
}

# One take: a shot asked for unbroken runs to the family's ceiling before it
# is cut, beside chained shots that still split at the plan's limit; and with
# no ceiling on the rail, to the plan's own maximum.
_takes = plan(70, ["long", "medium"], {0: [("one unbroken take", "new")], 1: [("b", "cut")]},
              rail={"video": "x", "max_seconds": 20})
PLANS["one take beside chained shots"] = director.edit(_takes, "s1", {"one_take": True})
# A camera line: a shot's fingerprint holds it, a sheet's does not.
PLANS["a camera rule"] = director.edit(
    plan(20, ["medium", "medium"], {0: [("@keeper waits", "new")], 1: [("@keeper turns", "cut")]},
         entities=(KEEPER,)),
    director.HEADER, {"camera": "first-person, through the keeper's eyes"})
PLANS["one take with no ceiling"] = director.edit(
    plan(90, ["medium"], {0: [("a", "new")]}), "s1", {"one_take": True})

# Plans with renders on them, for the states: a walk through prep and the run
# the way the room makes one, with a redo and an edit that leave rows stale,
# and words that make the JSON escape (quotes, a newline, accents, a CJK
# name) since the fingerprint hashes the text Python writes.
def _render(doc, row, handle):
    doc, mark = director.start(doc, row)
    return director.land(doc, row, handle, mark)


def walk():
    doc = plan(40, ["medium", "short", "long"], {
        0: [("@keeper climbs the stairs", "new"), ("@keeper reaches the lamp", "pin")],
        1: [("@keeper sees @bottle on @coast", "cut")],
        2: [("@keeper reads the note", "new"), ("close on the note", "cut")],
    }, entities=(KEEPER, BOTTLE, {"name": "coast", "kind": "place",
                                  "description": 'a "rocky" coast,\nwind — café 灯台'}))
    doc = {**doc, "look": "désaturé teal, 35mm \"grain\"", "rail": {**doc["rail"], "aspect": "16:9"}}
    steps = {"fresh": doc}
    doc = _render(doc, "e1", "pic-1")
    steps["a sheet waiting"] = doc
    doc = director.approve(doc, "e1")
    doc, _mark = director.start(doc, "e2")
    steps["one approved, one rendering"] = doc
    doc = director.fail(doc, "e2", "  out of\\nmemory ")
    steps["a failed sheet"] = doc
    doc = director.approve(_render(doc, "e2", "pic-2"), "e2")
    doc = director.approve(_render(doc, "e3", "pic-3"), "e3")
    steps["sheets approved"] = doc
    for at, row in enumerate(r["id"] for r in director.rows(doc) if r["kind"] == "keyframe"):
        doc = director.approve(_render(doc, row, f"pic-{4 + at}"), row)
    steps["ready to run"] = doc
    for at, row in enumerate(director.run_steps(doc)[:2]):
        doc = _render(doc, row, f"clip-{1 + at}")
    steps["two clips in"] = doc
    steps["the bottle redone"] = _render(doc, "e2", "pic-20")
    steps["a shot edited"] = director.edit(doc, "s1", {"action": "@keeper runs up the stairs"})
    steps["the rail moved"] = director.follow_rail(doc, {**doc["rail"], "video": "ltx", "max_seconds": 5})[0]
    return steps


STEPS = walk()

rng = random.Random(7)
ALLOTS = []
for _ in range(300):
    count = rng.randint(1, 7)
    weights = [rng.choice([0, 1, 1, 2, 3, 5]) for _ in range(count)]
    floors = [rng.randint(1, 3) for _ in range(count)] if rng.random() < .5 else None
    least = sum(floors) if floors else count
    ALLOTS.append([rng.randint(least, least + 60), weights, floors])

SCRIPT = """
const d = await import(process.argv[1]);
const plans = JSON.parse(process.argv[2]);
const allots = JSON.parse(process.argv[3]);
const out = { plans: {}, allots: [], refused: null };
for (const [name, plan] of Object.entries(plans)) {
  out.plans[name] = { seconds: d.allotPlan(plan), clips: d.clips(plan), rows: d.rows(plan),
                      limit: d.limitOf(plan), floor: d.floorOf(plan),
                      shotLimits: plan.shots.map((shot) => d.limitOf(plan, shot)) };
}
for (const [total, weights, floors] of allots) out.allots.push(d.allot(total, weights, floors));
try { d.allot(3, [1, 1], [2, 2]); } catch (error) { out.refused = error.message; }
out.weights = d.WEIGHTS; out.continues = d.CONTINUES; out.kinds = d.KINDS; out.limit = d.SHOT_LIMIT;
console.log(JSON.stringify(out));
"""

STATE_SCRIPT = """
const d = await import(process.argv[1]);
const steps = JSON.parse(process.argv[2]);
const out = {};
for (const [name, plan] of Object.entries(steps)) {
  const marks = {};
  for (const row of d.rows(plan)) marks[row.id] = d.fingerprint(plan, row.id);
  out[name] = { marks, states: d.states(plan), prep: d.prepSteps(plan), canRun: d.canRun(plan),
                runSteps: d.runSteps(plan), handles: d.handlesOf(plan) };
}
const fresh = steps.fresh;
const mark = d.fingerprint(fresh, "e2");
const landed = d.land(d.start(fresh, "e2", mark), "e2", "pic-1", mark);
out.records = { started: d.start(fresh, "e2", mark).renders, landed: landed.renders,
                approved: d.approve(landed, "e2").renders,
                failed: d.fail(d.start(fresh, "e2", mark), "e2", "  out of\\nmemory ").renders };
try { d.approve(fresh, "e3"); } catch (error) { out.refused = error.message; }
out.sha = [d.sha1(""), d.sha1("abc"), d.sha1("é灯".repeat(40))];
console.log(JSON.stringify(out));
"""

got = layout.run(SCRIPT, MIRROR, PLANS, ALLOTS)
stated = layout.run(STATE_SCRIPT, MIRROR, STEPS)

check("the weights are the same three", got["weights"], director.WEIGHTS)
check("the joins are the same three", got["continues"], list(director.CONTINUES))
check("the kinds are the same three", got["kinds"], list(director.KINDS))
check("the shot limit is the same", got["limit"], director.SHOT_LIMIT)

for name, doc in PLANS.items():
    mine = got["plans"][name]
    check(f"{name}: seconds", mine["seconds"], director.allot_plan(doc))
    check(f"{name}: clips", mine["clips"], director.clips(doc))
    check(f"{name}: rows", mine["rows"], director.rows(doc))
    check(f"{name}: each shot's limit", mine["shotLimits"],
          [director.limit_of(doc, shot) for shot in doc["shots"]])
    check(f"{name}: limit", mine["limit"], director.limit_of(doc))
    check(f"{name}: floor", mine["floor"], director.floor_of(doc))

for (total, weights, floors), mine in zip(ALLOTS, got["allots"]):
    want = director.allot(total, weights, floors)
    if mine != want:
        FAILURES.append(f"allot({total}, {weights}, {floors}): js {mine} != py {want}")

try:
    director.allot(3, [1, 1], [2, 2])
except director.PlanError as problem:
    check("a total too short for its floors is refused in the same words", got["refused"], str(problem))

import hashlib  # noqa: E402

check("sha1 is sha1", stated["sha"],
      [hashlib.sha1(x.encode("utf-8")).hexdigest() for x in ("", "abc", "é灯" * 40)])
for name, doc in STEPS.items():
    mine = stated[name]
    check(f"{name}: fingerprints",
          mine["marks"], {r["id"]: director.fingerprint(doc, r["id"]) for r in director.rows(doc)})
    check(f"{name}: states", mine["states"], director.states(doc))
    check(f"{name}: prep steps", mine["prep"], director.prep_steps(doc))
    check(f"{name}: can run", mine["canRun"], director.can_run(doc))
    check(f"{name}: run steps", mine["runSteps"], director.run_steps(doc))
    check(f"{name}: handles", mine["handles"], director.handles_of(doc))
fresh = STEPS["fresh"]
started, mark = director.start(fresh, "e2")
landed = director.land(started, "e2", "pic-1", mark)
check("start records as director.start", stated["records"]["started"], started["renders"])
check("land records as director.land", stated["records"]["landed"], landed["renders"])
check("approve records as director.approve", stated["records"]["approved"],
      director.approve(landed, "e2")["renders"])
check("fail records as director.fail", stated["records"]["failed"],
      director.fail(started, "e2", "  out of\nmemory ")["renders"])
try:
    director.approve(fresh, "e3")
except director.PlanError as problem:
    check("approving a row not waiting is refused in the same words", stated.get("refused"), str(problem))
# The walk is worth what it reaches.
check("the walk reaches every state",
      {s for doc in STEPS.values() for s in director.states(doc).values()} >= set(director.STATES), True)

# The cases are worth what they exercise: a split, a clamp and a raised floor
# that never happened would be agreement about nothing.
check("the long shot really is split", len(director.clips(PLANS["a shot over the limit"])), 3)
check("the rail really clamps", director.limit_of(PLANS["the rail clamps the limit"]), 8)
check("the rail really raises the floor", director.floor_of(PLANS["the rail raises the floor"]), 3)
check("keyframes off really leaves none",
      [r for r in director.rows(PLANS["keyframes off"]) if r["kind"] == "keyframe"], [])

passed("the plan card's arithmetic is director.py's")
