"""A whole Director piece, from brief to finished run, with no model and no GPU.

    python tests/test_director_replay.py

Pure. The model is a replay of recorded replies (`director_calls.plan_piece`
with a scripted `ask`), prep is the room's bookkeeping done by hand
(`director.start`/`land`/`approve`, what `chat.js` does when a sheet lands and
is approved), and the run is `director_run.drive` against a fake renderer
that writes a placeholder file per clip and answers the way ComfyUI's history
does. What is under test is the order of things and the record they leave:
that Run waits for every approval, that a changed sheet makes what cites it
stale, that each clip continues from the take before it, that a failure stops
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

check("the first press makes the sheet, and the frame citing only the cast; the frame citing the "
      "place waits for its sheet", director.prep_steps(plan), ["e2", "kf.s3"])
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
check("a changed sheet is stale, and so is the frame citing it, but not the one that does not",
      [director.state_of(plan, r) for r in ("e2", "kf.s1", "kf.s3")], ["stale", "stale", "approved"])
check("…and Run is disabled again", director.can_run(plan), False)
plan = director.approve(prep(plan, "e2"), "e2")
check("the redone sheet is a new handle, so the frame still needs redoing",
      director.state_of(plan, "kf.s1"), "stale")
plan = director.approve(prep(plan, "kf.s1"), "kf.s1")
check("redone and approved: Run is enabled", director.can_run(plan), True)

# ---- the fake renderer --------------------------------------------------------------

FILES = tempfile.mkdtemp(prefix="director-replay-")


class Fake:
    """`drive`'s io. Builds the piece `chat.video_piece` would (the strip up to
    `after`, then this card), queues nothing, and answers each prompt as
    ComfyUI's history would: a joined reel and this shot's take, both
    written as placeholder files. `fail_at` fails that step's render;
    `stop_at` presses Stop while that step is on the queue."""

    def __init__(self, fail_at=None, stop_at=None, problem_at=None):
        self.fail_at, self.stop_at, self.problem_at = fail_at, stop_at, problem_at
        self.built, self.saves, self.told, self.stop = [], 0, [], False
        self.count = 0

    async def build(self, run, step):
        self.built.append({"row": step["row"], "after": step["action"]["after"],
                           "strip": [c.get("chat_handle") for c in run["strip"]],
                           "from": step["action"]["from"]})
        if self.problem_at == len(self.built):
            return {"problem": "no file is picked for the video model."}
        after = step["action"]["after"]
        kept = []
        if after:
            at = [c.get("chat_handle") for c in run["strip"]].index(after)
            kept = [{**c, "hold": True} for c in run["strip"][:at + 1]]
        card = {"prompt": step["action"]["prompt"], "duration_s": step["action"]["seconds"]}
        return {"prompt": {"node": step["row"]}, "piece": {"family": "ltx25", "segments": kept + [card]}}

    async def enqueue(self, _prompt):
        self.count += 1
        return f"p{self.count}"

    async def wait(self, prompt_id):
        n = int(prompt_id[1:])
        if self.stop_at == n:
            self.stop = True
            return "stopped", None
        if self.fail_at == n:
            return "failed", "CUDA out of memory"
        step = self.current
        segment = len(step["piece"]["segments"])
        for name in (f"reel_{n}.mp4", f"take_{n}.mp4"):
            with open(os.path.join(FILES, name), "wb") as placeholder:
                placeholder.write(b"\0")
        return "landed", {"continuity-chat": {
            "mmc_video": [{"filename": f"reel_{n}.mp4", "subfolder": "", "type": "output"}],
            "mmc_takes": [{"segment": segment, "filename": f"take_{n}.mp4", "subfolder": "",
                           "duration_s": step["action"]["seconds"], "width": 1280, "height": 720,
                           "has_audio": True}]}}

    def save(self, _run):
        self.saves += 1

    def tell(self, kind, run, step):
        self.told.append((kind, step["row"] if step else run["state"]))
        if kind == "queued":
            self.current = step

    def stopping(self):
        return self.stop


def drive(run, fake):
    return asyncio.run(run_mod.drive(run, fake))


# ---- a run that fails, then carries on --------------------------------------------------

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
        after = step["action"]["after"]
        kept = []
        if after:
            at = [c.get("chat_handle") for c in run["strip"]].index(after)
            kept = run["strip"][:at + 1]
        return {"prompt": {}, "piece": {"segments": kept + [{"prompt": step["action"]["prompt"]}]}}
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
