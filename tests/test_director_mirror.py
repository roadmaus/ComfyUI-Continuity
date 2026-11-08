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
                      limit: d.limitOf(plan), floor: d.floorOf(plan) };
}
for (const [total, weights, floors] of allots) out.allots.push(d.allot(total, weights, floors));
try { d.allot(3, [1, 1], [2, 2]); } catch (error) { out.refused = error.message; }
out.weights = d.WEIGHTS; out.continues = d.CONTINUES; out.kinds = d.KINDS; out.limit = d.SHOT_LIMIT;
console.log(JSON.stringify(out));
"""

got = layout.run(SCRIPT, MIRROR, PLANS, ALLOTS)

check("the weights are the same three", got["weights"], director.WEIGHTS)
check("the joins are the same three", got["continues"], list(director.CONTINUES))
check("the kinds are the same three", got["kinds"], list(director.KINDS))
check("the shot limit is the same", got["limit"], director.SHOT_LIMIT)

for name, doc in PLANS.items():
    mine = got["plans"][name]
    check(f"{name}: seconds", mine["seconds"], director.allot_plan(doc))
    check(f"{name}: clips", mine["clips"], director.clips(doc))
    check(f"{name}: rows", mine["rows"], director.rows(doc))
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

# The cases are worth what they exercise: a split, a clamp and a raised floor
# that never happened would be agreement about nothing.
check("the long shot really is split", len(director.clips(PLANS["a shot over the limit"])), 3)
check("the rail really clamps", director.limit_of(PLANS["the rail clamps the limit"]), 8)
check("the rail really raises the floor", director.floor_of(PLANS["the rail raises the floor"]), 3)
check("keyframes off really moves them to the run",
      {r["phase"] for r in director.rows(PLANS["keyframes off"]) if r["kind"] == "keyframe"}, {"run"})

passed("the plan card's arithmetic is director.py's")
