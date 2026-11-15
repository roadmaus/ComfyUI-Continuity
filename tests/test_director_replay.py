"""A whole Director piece, from brief to finished run, with no model and no GPU.

    python tests/test_director_replay.py

Pure. The model is a replay of recorded replies (`director_calls.plan_piece`
with a scripted `ask`), prep is the room's bookkeeping done by hand
(`director.start`/`land`/`approve`, what `chat.js` does when a sheet lands and
is approved), and the run is `director_run.drive` against a fake renderer
that writes a placeholder file per clip and answers the way ComfyUI's history
does. What is under test is the order of things and the record they leave:
that Run waits for every approval, that a changed sheet makes what cites it
stale, that each clip continues from the take before it, that clips which
carry straight on are one render landing as their own shots, that a cut can
open on the frame before it, that a failure stops
the run with what landed kept and Run again carries on from there, that a
server restart brings a run back stopped, that Stop stops, and that a second
Run after an edit renders only what the edit made stale. The planning
fixtures (malformed JSON, a bad citation, a model that keeps asking) are the
ones the room meets before any of this, and are kept here so the whole path
is in one place.
"""

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check  # noqa: E402

pkg = layout.load("prompting", "chat", "director", "director_calls", "director_run")
director, calls, run_mod = pkg.director, pkg.director_calls, pkg.director_run

RAIL = {"still": "krea2", "edit": "qwenedit", "video": "ltx25", "aspect": "16:9",
        "min_seconds": 1, "max_seconds": 60, "references": False}
ROOM_RAIL = {"aspect": "16:9", "video_family": "ltx25", "seed": 7, "seed_policy": "fixed"}
BASE = {"piece": {"version": 2, "family": "ltx25", "segments": []}, "widgets": {"seed": 7}}


def fence(obj):
    return "```json\n" + json.dumps(obj) + "\n```"


def scripted(replies):
    def ask(_system, _message, _schema, _label):
        return replies.pop(0)
    return ask


BRIEF = "a 30 second piece: @george on a night train"
CAST = [{"name": "george", "description": "a tall man"}]
REPLIES = [
    fence({"questions": [], "assumptions": ["It is night."]}),
    fence({"title": "Night Train", "seconds": 30, "look": "sodium light, grain"}),
    fence({"beats": [{"text": "@george wakes in the carriage.", "weight": "short"},
                     {"text": "He finds the cab empty.", "weight": "long"}]}),
    fence({"entities": [{"name": "carriage", "kind": "place", "description": "an old train carriage"}]}),
    fence({"shots": [{"action": "@george wakes up inside @carriage.", "continues": "new"}]}),
    fence({"shots": [{"action": "@george walks the length of @carriage.", "continues": "pin"},
                     {"action": "@george opens the cab door: nobody.", "continues": "cut"}]}),
]

# ---- the planning fixtures ----------------------------------------------------------

replies = list(REPLIES)
replies[4:5] = ["not json at all {", "still not"]
try:
    calls.plan_piece(BRIEF, RAIL, scripted(replies), cast=CAST)
    check("malformed JSON twice stops planning", False, True)
except calls.PlanningFailed as failed:
    check("malformed JSON twice stops planning, with the plan as far as it got",
          (failed.log[-1]["label"], len(failed.plan["beats"])), ("shots.b1", 2))

replies = list(REPLIES)
replies[4:5] = [fence({"shots": [{"action": "@ghost wakes up.", "continues": "new"}]}), REPLIES[4]]
out = calls.plan_piece(BRIEF, RAIL, scripted(replies), cast=CAST)
check("a bad citation is re-asked and the second answer kept",
      out["plan"]["shots"][0]["action"], "@george wakes up inside @carriage.")

asking = [fence({"questions": ["Which train?"], "assumptions": []})]
out = calls.plan_piece("make me a video", RAIL, scripted(asking))
check("a model that asks is answered with its question, and no plan", (out["plan"], out["questions"]),
      (None, ["Which train?"]))

# ---- plan ---------------------------------------------------------------------------

plan = calls.plan_piece(BRIEF, RAIL, scripted(list(REPLIES)), cast=CAST)["plan"]
every = director.rows(plan)
check("the plan's rows: a sheet, two opening frames, three clips",
      [(r["id"], r["kind"]) for r in every],
      [("e2", "sheet"), ("kf.s1", "keyframe"), ("kf.s3", "keyframe"),
       ("s1", "clip"), ("s2", "clip"), ("s3", "clip")])

counter = {"pic": 0, "clip": 0}


def handle(kind):
    counter[kind] += 1
    return f"{kind}-{counter[kind]}"


LEDGER = []


def prep(plan, row):
    """The room's prep render of `row`: started, landed as a new picture."""
    plan, mark = director.start(plan, row)
    picture = handle("pic")
    LEDGER.append({"handle": picture, "kind": "still", "filename": f"{picture}.png [output]",
                   "text": row, "aspect": "16:9", "turn": 1})
    return director.land(plan, row, picture, mark)


def begin(plan, prior=None, strip=()):
    todo = director.run_steps(plan)
    return run_mod.begin("chat1", plan, ledger=LEDGER, strip=list(strip), piece={},
                         rail=ROOM_RAIL, base=BASE,
                         handles=[handle("clip") for _ in todo], prior=prior)


def refused(label, call, fragment):
    try:
        call()
    except (run_mod.RunError, director.PlanError) as problem:
        if fragment not in str(problem):
            FAILURES.append(f"{label}: {str(problem)!r} does not say {fragment!r}")
    else:
        FAILURES.append(f"{label}: was not refused")


refused("Run is refused before anything is approved", lambda: begin(plan), "approved")
counter["clip"] = 0  # The refused press reserved nothing the room would keep.

# ---- prep ---------------------------------------------------------------------------

check("the first press makes the sheet; both frames wait for it, the one that names the place and "
      "the one that is only in the same scene", director.prep_steps(plan), ["e2"])
plan = prep(plan, "e2")
check("a landed sheet waits for the person", director.state_of(plan, "e2"), "pending")
plan = director.approve(plan, "e2")
check("approved, the frames that cite it are ready", director.prep_steps(plan), ["kf.s1", "kf.s3"])
for row in ("kf.s1", "kf.s3"):
    plan = director.approve(prep(plan, row), row)
check("everything approved: Run is enabled", director.can_run(plan), True)

# A sheet changed by talking: the new picture replaces the old and needs
# approving again, and the frame that cites the place goes stale with it.
plan = director.edit(plan, "e2", {"description": "an old sleeper carriage, brass lamps"})
check("a changed sheet is stale, and so is every frame set in that place",
      [director.state_of(plan, r) for r in ("e2", "kf.s1", "kf.s3")], ["stale", "stale", "stale"])
check("…and Run is disabled again", director.can_run(plan), False)
plan = director.approve(prep(plan, "e2"), "e2")
check("the redone sheet is a new handle, so the frames still need redoing",
      [director.state_of(plan, r) for r in ("kf.s1", "kf.s3")], ["stale", "stale"])
for row in ("kf.s1", "kf.s3"):
    plan = director.approve(prep(plan, row), row)
check("redone and approved: Run is enabled", director.can_run(plan), True)

# ---- the fake renderer --------------------------------------------------------------

FILES = tempfile.mkdtemp(prefix="director-replay-")


def pieced(run, step):
    """The segments `chat.video_piece` would build for a step: the strip up
    to `after`, held, then this shot's card and a card for each shot that
    carries on from it in the same render, those stamped with their handles."""
    after = step["action"]["after"]
    kept = []
    if after:
        at = [c.get("chat_handle") for c in run["strip"]].index(after)
        kept = [{**c, "hold": True} for c in run["strip"][:at + 1]]
    cards = [{"prompt": one["action"]["prompt"], "duration_s": one["action"]["seconds"],
              **({"chat_handle": one["handle"]} if step["mates"] else {})}
             for one in (step, *step["mates"])]
    return kept + cards


class Fake:
    """`drive`'s io. Builds the piece `chat.video_piece` would (`pieced`),
    queues nothing, and answers each prompt as ComfyUI's history would: a
    joined reel and a take for each shot sampled, written as placeholder
    files; a still answers as a picture. `fail_at` fails that step's render;
    `stop_at` presses Stop while that step is on the queue."""

    def __init__(self, fail_at=None, stop_at=None, problem_at=None):
        self.fail_at, self.stop_at, self.problem_at = fail_at, stop_at, problem_at
        self.built, self.saves, self.told, self.stop = [], 0, [], False
        self.count = 0

    async def build(self, run, step):
        self.built.append({"row": step["row"], "after": step["action"]["after"],
                           "strip": [c.get("chat_handle") for c in run["strip"]],
                           "from": step["action"]["from"],
                           "with": [m["row"] for m in step["mates"]]})
        if self.problem_at == len(self.built):
            return {"problem": "no file is picked for the video model."}
        if step["action"]["kind"] == "still":
            return {"prompt": {"node": step["row"]}, "piece": {"arch": "qwenedit"}}
        return {"prompt": {"node": step["row"]}, "piece": {"family": "ltx25",
                                                           "segments": pieced(run, step)}}

    async def enqueue(self, _prompt):
        self.count += 1
        self.queued = []
        return f"p{self.count}"

    async def wait(self, prompt_id):
        n = int(prompt_id[1:])
        if self.stop_at == n:
            self.stop = True
            return "stopped", None
        if self.fail_at == n:
            return "failed", "CUDA out of memory"
        if self.queued[0]["action"]["kind"] == "still":
            return "landed", {"continuity-chat": {
                "mmc_image": [{"filename": f"frame_{n}.png", "subfolder": "", "type": "output"}]}}
        takes = []
        for at, step in enumerate(self.queued):
            name = f"take_{n}.mp4" if not at else f"take_{n}_{at + 1}.mp4"
            takes.append({"segment": len(step["piece"]["segments"]), "filename": name,
                          "subfolder": "", "duration_s": step["action"]["seconds"],
                          "width": 1280, "height": 720, "has_audio": True})
        for name in (f"reel_{n}.mp4", *(t["filename"] for t in takes)):
            with open(os.path.join(FILES, name), "wb") as placeholder:
                placeholder.write(b"\0")
        return "landed", {"continuity-chat": {
            "mmc_video": [{"filename": f"reel_{n}.mp4", "subfolder": "", "type": "output"}],
            "mmc_takes": takes}}

    def save(self, _run):
        self.saves += 1

    def tell(self, kind, run, step):
        self.told.append((kind, step["row"] if step else run["state"]))
        if kind == "queued":
            self.queued.append(step)

    def stopping(self):
        return self.stop


def drive(run, fake):
    return asyncio.run(run_mod.drive(run, fake))


# ---- a run that fails, then carries on --------------------------------------------------
#
# One clip a render, which is how a run goes wherever no clip carries on from
# another, and is said here by turning the chain off: what is under test down
# to "clips that carry straight on" is the order of the steps and the record
# each leaves, a clip at a time.

director.CHAIN_LIMIT = 1

run = begin(plan)
check("the run holds a handle per clip, from the room's counter",
      run["handles"], ["clip-1", "clip-2", "clip-3"])
fake = Fake(fail_at=2)
run = drive(run, fake)
check("a failure stops the run, said in the clip's words",
      (run["state"], run["error"]), ("failed", "clip 2 of 3 failed: CUDA out of memory"))
check("what landed stays landed; the failed row is failed; the rest untouched",
      [director.state_of(run["plan"], r) for r in ("s1", "s2", "s3")], ["approved", "failed", "planned"])
check("the first clip opens on its approved frame and cites its place",
      fake.built[0]["from"][0].endswith(":start") and any(f.endswith(":scene") for f in fake.built[0]["from"]),
      True)
check("the second is put after the first, which the strip holds by its handle",
      (fake.built[1]["after"], fake.built[1]["strip"]), ("clip-1", ["clip-1"]))
held = run["strip"][0]
check("the strip holds the landed shot on its take, as the room's land does",
      (held["chat_handle"], held["hold"], held["take"]["filename"], held["take"]["duration_s"]),
      ("clip-1", True, "take_1.mp4 [output]", 8.0))
check("and the ledger cites the take, not the joined reel",
      [(e["handle"], e["filename"]) for e in run["ledger"] if e["kind"] == "clip"],
      [("clip-1", "take_1.mp4 [output]")])
check("the room was told each step", fake.told,
      [("state", "running"), ("queued", "s1"), ("landed", "s1"), ("queued", "s2"), ("failed", "s2"),
       ("state", "failed")])
check("the status the room catches up with",
      {k: v for k, v in run_mod.public(run).items() if k in ("state", "done", "total", "current")},
      {"state": "failed", "done": 1, "total": 3, "current": None})

# The room filed clip-1 on its own plan when it landed, so the plan sent with
# the second Run is the run's plan.
again = begin(run["plan"], prior=run, strip=run["strip"])
check("Run again carries on from the first unfinished clip", director.run_steps(again["plan"]), ["s2", "s3"])
check("…with the landed step kept on the record ahead of the new ones",
      [s["handle"] for s in again["steps"]], ["clip-1"])
fake = Fake()
again = drive(again, fake)
check("and finishes", (again["state"], [b["row"] for b in fake.built]), ("done", ["s2", "s3"]))
check("each clip continues from the one before",
      [(b["after"], b["strip"]) for b in fake.built],
      [("clip-1", ["clip-1"]), ("clip-4", ["clip-1", "clip-4"])])
check("the strip is the whole piece, in order", [c["chat_handle"] for c in again["strip"]],
      ["clip-1", "clip-4", "clip-5"])
check("the progress counts this press", run_mod.public(again)["done"], 2)
refused("a finished plan has nothing to run", lambda: begin(again["plan"], prior=again), "already rendered")

# ---- only what an edit made stale is rendered again -----------------------------------------

done = again
edited = director.edit(done["plan"], "s3", {"action": "@george opens the cab door: the driver is asleep."})
check("an edit to the last shot leaves only it to render", director.run_steps(edited), ["s3"])
edited = director.edit(done["plan"], "s2", {"action": "@george runs the length of @carriage."})
check("an edit to the middle shot renders it and what continues from it",
      director.run_steps(edited), ["s2", "s3"])
fake = Fake()
rerun = drive(begin(edited, prior=done, strip=done["strip"]), fake)
check("…and nothing else", [b["row"] for b in fake.built], ["s2", "s3"])
check("the redone shot is put after the first, cutting the old tail off the strip",
      (fake.built[0]["after"], fake.built[0]["strip"]), ("clip-1", ["clip-1", "clip-4", "clip-5"]))

# ---- restart, Stop, a refused build -------------------------------------------------------------

run = begin(plan)
run, step = run_mod.next_step(run)
run = run_mod.queued(run, step["row"], "p9", {"segments": [{}]})
back = run_mod.restarted(run)
check("a server restart brings a running run back stopped, never running", back["state"], "stopped")
check("…the clip that was on the queue is failed, to be rendered again",
      (back["steps"][-1]["state"], director.state_of(back["plan"], "s1")), ("lost", "failed"))
check("…and Run continues it", director.run_steps(begin(back["plan"], prior=back)["plan"]),
      ["s1", "s2", "s3"])
check("a run that was not running is left as it was", run_mod.restarted(again), again)

fake = Fake(stop_at=2)
stopped = drive(begin(plan), fake)
check("Stop stops: the clip on the queue lets go and nothing more is queued",
      (stopped["state"], [b["row"] for b in fake.built]), ("stopped", ["s1", "s2"]))
check("…and the stopped clip renders again on the next Run",
      director.run_steps(stopped["plan"]), ["s2", "s3"])

fake = Fake(problem_at=1)
refusal = drive(begin(plan), fake)
check("a build the compiler refuses fails the run in its sentence, before anything is queued",
      (refusal["state"], refusal["error"], fake.count),
      ("failed", "clip 1 of 3 failed: no file is picked for the video model.", 0))

# ---- rehearsal -------------------------------------------------------------------------

def rehearsal_build(problem_at=None):
    built = []

    def build(run, step):
        built.append((step["row"], step["action"]["after"]))
        if problem_at == len(built):
            return {"problem": "LTX 2.5 reads one reference image."}
        return {"prompt": {}, "piece": {"segments": pieced(run, step)}}
    return build, built


fresh = begin(plan)
build, built = rehearsal_build()
check("a rehearsal builds every clip in order, each after the last, and passes",
      (run_mod.rehearse(fresh, build), built),
      (None, [("s1", None), ("s2", fresh["handles"][0]), ("s3", fresh["handles"][1])]))
build, built = rehearsal_build(problem_at=3)
check("a clip that would not render is said before anything is queued",
      run_mod.rehearse(fresh, build), "clip 3 of 3 would not render: LTX 2.5 reads one reference image.")
check("and the rehearsal leaves the run as it was",
      (fresh["state"], len(fresh["handles"]), fresh["steps"]), ("running", 3, []))

running = begin(plan)
refused("a chat runs one run at a time", lambda: begin(plan, prior=running), "still going")
refused("a run is refused handles it does not have",
        lambda: run_mod.begin("chat1", plan, ledger=LEDGER, strip=[], piece={}, rail=ROOM_RAIL,
                              base=BASE, handles=["clip-1"]), "reserved 1")


# ---- clips that carry straight on are one render ------------------------------------------
#
# s2 carries on from s1 (`pin`), so the two are queued as one piece and
# sampled in one prompt; s3 is a cut and renders alone, after them.

director.CHAIN_LIMIT = 4
counter["clip"] = 20
fake = Fake()
chained = drive(begin(plan), fake)
check("a clip is built with the clip that carries on from it, and a cut by itself",
      [(b["row"], b["with"]) for b in fake.built], [("s1", ["s2"]), ("s3", [])])
check("two prompts for three clips", fake.count, 2)
check("the room is told of each shot, in order, though they were one render", fake.told,
      [("state", "running"), ("queued", "s1"), ("queued", "s2"), ("landed", "s1"), ("landed", "s2"),
       ("queued", "s3"), ("landed", "s3"), ("state", "done")])
check("the shots of one render share its prompt id and keep their own handles",
      [(st["row"], st["handle"], st["prompt_id"]) for st in chained["steps"]],
      [("s1", "clip-21", "p1"), ("s2", "clip-22", "p1"), ("s3", "clip-23", "p2")])
check("each lands as its own shot on the strip, held on its own take",
      [(c["chat_handle"], c["hold"], c["take"]["filename"]) for c in chained["strip"]],
      [("clip-21", True, "take_1.mp4 [output]"), ("clip-22", True, "take_1_2.mp4 [output]"),
       ("clip-23", True, "take_2.mp4 [output]")])
check("each step holds the piece up to its own shot, which is what the room lands it from",
      [len(st["piece"]["segments"]) for st in chained["steps"]], [1, 2, 3])
check("the second shot was written to continue from the handle reserved for the first",
      chained["steps"][1]["action"]["after"], "clip-21")
check("every clip is filed current under the mark it was queued with",
      [director.state_of(chained["plan"], r) for r in ("s1", "s2", "s3")], ["approved"] * 3)
check("the progress counts shots, not renders", run_mod.public(chained)["done"], 3)

counter["clip"] = 30
fake = Fake(fail_at=1)
broken = drive(begin(plan), fake)
check("a render of two shots that fails, fails both, and the run with them",
      (broken["state"], broken["error"],
       [director.state_of(broken["plan"], r) for r in ("s1", "s2", "s3")]),
      ("failed", "clip 1 of 3 failed: CUDA out of memory", ["failed", "failed", "planned"]))
check("...and the room hears it of each", [t for t in fake.told if t[0] == "failed"],
      [("failed", "s1"), ("failed", "s2")])
check("...so Run renders them again", director.run_steps(broken["plan"]), ["s1", "s2", "s3"])

fake = Fake(stop_at=1)
halted = drive(begin(plan), fake)
check("Stop lets go of every shot on the queue",
      (halted["state"], [st["state"] for st in halted["steps"]]), ("stopped", ["lost", "lost"]))

fresh = begin(plan)
build, built = rehearsal_build()
check("a rehearsal builds the same renders the run will",
      (run_mod.rehearse(fresh, build), built), (None, [("s1", None), ("s3", fresh["handles"][1])]))

# ---- a cut that opens on the frame before it ------------------------------------------------
#
# The storyboard off: s3, a new angle, has no approved opening frame, so the
# run makes one in front of it — the last frame of the clip before, turned to
# the new angle on the edit path — and the cut opens on that.

matched = director.edit(plan, director.HEADER, {"keyframes": False})
check("the run's steps: the clips, and the frame the cut opens on",
      director.run_steps(matched), ["s1", "s2", "cut.s3", "s3"])
refused("a run is refused the picture handle it was not given",
        lambda: run_mod.begin("chat1", matched, ledger=LEDGER, strip=[], piece={}, rail=ROOM_RAIL,
                              base=BASE, handles=["clip-41", "clip-42", "clip-43"]),
        "1 opening frames to render and the room reserved 0")


def begin_matched(doc):
    return run_mod.begin("chat1", doc, ledger=LEDGER, strip=[], piece={}, rail=ROOM_RAIL, base=BASE,
                         handles=["clip-41", "clip-42", "pic-90", "clip-43"])


fake = Fake()
cut = drive(begin_matched(matched), fake)
check("the frame is rendered between the clips, alone, from the clip before it",
      [(b["row"], b["with"], b["from"]) for b in fake.built][1], ("cut.s3", [], ["clip-42"]))
check("...as a still that says which frame of that clip it is",
      (cut["steps"][2]["action"]["kind"], cut["steps"][2]["action"].get("grab"), cut["steps"][2]["handle"]),
      ("still", "last", "pic-90"))
check("...and joins the ledger as a picture, leaving the strip as it was",
      ([(e["handle"], e["kind"]) for e in cut["ledger"] if e["handle"] == "pic-90"],
       [c["chat_handle"] for c in cut["strip"]]),
      ([("pic-90", "still")], ["clip-41", "clip-42", "clip-43"]))
check("the cut opens on it", fake.built[2]["from"][0], "pic-90:start")
check("the progress counts the three shots and not the frame",
      {k: v for k, v in run_mod.public(cut).items() if k in ("state", "done", "total")},
      {"state": "done", "done": 3, "total": 3})
build, built = rehearsal_build()
check("a rehearsal builds the clips and leaves the frame, which has no clip to be cut from yet",
      (run_mod.rehearse(begin_matched(matched), build), [row for row, _after in built]),
      (None, ["s1", "s3"]))
