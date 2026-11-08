"""Director's run: an approved plan rendered to the end on one command.

Planning and prep are the room's. Every render they make is one the person
asked for and watches land, and the room keeps the plan in the browser and
saves it with the chat (`routes/director.py` argues the statelessness). The
run is the exception the spec makes (§8): it is a dozen clips and can take an
hour, and it must go on when the tab is closed. So the server drives it, and
this module is what it drives: a **run record**, one JSON document per chat,
and the moves it goes through — a step begun, queued, landed, failed, the run
stopped, the server restarted. Pure: no ComfyUI, no disk, no clock. The loop
that puts steps on the queue (`drive`) is here too, but everything it touches
is handed to it, which is what lets `tests/test_director_replay.py` run a whole
piece through a fake renderer.

**A run is the room's renders, done without the room.** Each step is the
plan's next clip (`director.next_step`), made into the chat's own action
(`director.action_for`) and rendered through the same build `chat/render`
uses, so the clip that lands is the clip the person would have got by typing
the shot. What the room would have done on landing it, the record does too:
the clip joins the ledger under its handle and the strip as the built piece
left it, held on its take (`chat.js land`, mirrored by `_landed`), because the
next clip continues from that take with `after`. The room, when it hears the
clip landed, files it the same way from the same numbers; neither side asks
the other what happened.

**Handles are the room's, reserved up front.** The room numbers what it makes
(`clip-7`) and never reuses a number, and the run makes clips while the room
may be making things of its own. So Run sends as many clip handles as the run
has steps, taken off the room's counter at the press, and each step uses the
next one. A step that fails leaves its number unused, which is exactly what a
failed render in the room does.

**Rehearsed before it is queued.** Run first builds every clip in order
against stand-in takes (`rehearse`), so a citation the video family cannot
read or a seam off its grid is refused at the press, by name, rather than an
hour in.

**No gates, and no quiet fallbacks.** A run stops on the first failure — a
render error, a build the compiler refused, a file gone — and says so in the
record; everything landed stays landed, and Run again starts from the first
row still not approved. It stops on Stop. A server that restarts brings it
back *stopped* (`restarted`): a restart is not consent to spend the GPU, and
the step that was on the queue is gone with the queue.

**The plan in the record is the run's copy.** The room's plan may be edited
while the run goes on; the run renders what was approved when Run was pressed,
and every clip it lands carries the fingerprint it was rendered under. A clip
landed for a shot the room has since changed is stale on the room's plan by
that fingerprint, as a prep render is, and the next Run renders it again.
"""

import copy
import json
import random

from . import chat, director

VERSION = 1

# What a run is doing. `done` and `failed` are where a run ends by itself;
# `stopped` is a person's Stop or a server restart.
RUNNING, STOPPED, DONE, FAILED = "running", "stopped", "done", "failed"
RUN_STATES = (RUNNING, STOPPED, DONE, FAILED)

# What one step is doing. `building` is the window between the step being
# chosen and its prompt being on the queue.
BUILDING, QUEUED, LANDED, LOST = "building", "queued", "landed", "lost"
STEP_FAILED = "failed"

# How a step that never landed is said when the run stops around it.
STOPPED_WORDS = "stopped before it finished"
RESTART_WORDS = "lost when ComfyUI restarted; Run renders it again"


class RunError(ValueError):
    """A run that cannot start, said as a sentence for the plan card."""


# ---- starting ----------------------------------------------------------------------


def begin(chat_id, plan, *, ledger, strip, piece, rail, base, handles, prior=None):
    """A new run, or a continued one. -> the run record, running.

    `plan` is the plan as the room holds it now, renders and all; `ledger`,
    `strip` and `piece` are the room's (what a shot may cite, the shots joined
    so far, the cast); `rail` the room's rail as a render reads it; `base` the
    `{piece, widgets}` a clip is built over (`chat.js renderBase`); `handles`
    the clip handles reserved for it. `prior` is this chat's last run record,
    whose steps are kept ahead of the new ones: a run continued after a
    failure is the same run, read as one list.
    """
    if not str(chat_id or "").strip():
        raise RunError("a run belongs to a chat; the room sent none.")
    plan = director.validate(copy.deepcopy(plan))
    if not director.can_run(plan):
        raise RunError("every sheet and opening frame must be approved before the run.")
    todo = director.run_steps(plan)
    if not todo:
        raise RunError("every clip of this plan is already rendered.")
    handles = [str(h) for h in handles or () if str(h or "").startswith("clip-")]
    if len(handles) < len(todo):
        raise RunError(f"the run has {len(todo)} clips to render and the room reserved "
                       f"{len(handles)} handles for them.")
    if prior is not None and prior.get("state") == RUNNING:
        raise RunError("this chat's run is still going. Stop it first.")
    base = base if isinstance(base, dict) else {}
    kept = [s for s in (prior or {}).get("steps") or [] if s.get("state") == LANDED]
    if not isinstance(base.get("piece"), dict):
        raise RunError("the room sent no piece to build the clips over.")
    return {
        "version": VERSION,
        "chat": str(chat_id),
        "state": RUNNING,
        "error": None,
        "plan": plan,
        "ledger": [dict(e) for e in ledger or () if isinstance(e, dict)],
        "strip": [dict(c) for c in strip or () if isinstance(c, dict)],
        "piece": piece if isinstance(piece, dict) else {},
        "rail": dict(rail or {}),
        "base": {"piece": base["piece"], "widgets": dict(base.get("widgets") or {})},
        "handles": handles,
        "total": len(todo),
        "steps": kept,
        # Where this press's steps start in `steps`: the progress line counts
        # what this Run has done, not what an earlier one did.
        "first": len(kept),
    }


# ---- one step ------------------------------------------------------------------------


def _step(run, row):
    for step in reversed(run["steps"]):
        if step["row"] == row and step["state"] in (BUILDING, QUEUED):
            return step
    raise RunError(f"{row} is not a step the run has on the queue.")


def _seed(run):
    """The seed the next clip samples on: the room's own, kept for every clip
    when the rail keeps its seed, and rolled per clip when it rolls one."""
    widgets = run["base"]["widgets"]
    if run["rail"].get("seed_policy") == "random":
        return random.randrange(0xFFFFFFFF)
    return int(widgets.get("seed") or run["rail"].get("seed") or 0)


def next_step(run):
    """The step the run renders next -> `(run, step)`, or `(run, None)` when
    there is nothing to render: the run is done, or cannot go on, which the
    record now says.

    The step carries everything its render needs: the row, the reserved
    handle, the action the row becomes and the fingerprint it lands under.
    The plan marks the row rendering.
    """
    run = copy.deepcopy(run)
    if run["state"] != RUNNING:
        return run, None
    plan = run["plan"]
    row = director.next_step(plan)
    if row is None:
        if not director.run_steps(plan):
            run["state"] = DONE
        else:
            run["state"] = FAILED
            run["error"] = "nothing in the plan is ready to render; something it waits on failed."
        return run, None
    try:
        action = director.action_for(plan, row)
    except director.PlanError as problem:
        run["state"], run["error"] = FAILED, str(problem)
        return run, None
    if not run["handles"]:
        run["state"], run["error"] = FAILED, "the run ran out of reserved handles."
        return run, None
    plan, mark = director.start(plan, row)
    run["plan"] = plan
    step = {"row": row, "handle": run["handles"].pop(0), "mark": mark, "action": action,
            "seed": _seed(run), "state": BUILDING, "prompt_id": None, "piece": None,
            "saved": None, "takes": [], "error": None}
    run["steps"].append(step)
    return run, copy.deepcopy(step)


def queued(run, row, prompt_id, piece):
    """The step's prompt is on the queue as `prompt_id`; `piece` is the blob
    it was built as, which the room lands its strip from."""
    run = copy.deepcopy(run)
    step = _step(run, row)
    step.update(state=QUEUED, prompt_id=str(prompt_id), piece=piece)
    return run


def outputs_of(outputs):
    """A finished prompt's history outputs -> `(saved, takes, is_clip)`, read
    the way `chat.js settle` reads them: the first node that saved a video or
    a picture, and every take any node reported."""
    nodes = [n for n in (outputs or {}).values() if isinstance(n, dict)]
    takes = [t for n in nodes for t in n.get("mmc_takes") or [] if isinstance(t, dict)]
    for node in nodes:
        for key in ("mmc_video", "mmc_image"):
            saved = node.get(key)
            if isinstance(saved, list) and saved and isinstance(saved[0], dict):
                return saved[0], takes, key == "mmc_video"
    return None, takes, False


def _path(saved):
    return "/".join(p for p in (saved.get("subfolder"), saved.get("filename")) if p)


def _landed(run, step, saved, takes, is_clip):
    """The room's `land`, on the run's copies: the ledger line, and for a clip
    the strip as the built piece left it with this shot last, held on its
    take. Kept line for line with `chat.js land` — the next clip continues
    from the strip this writes, and the room writes the same one."""
    piece = step.get("piece") or {}
    segments = list(piece.get("segments") or []) if is_clip else []
    last = len(segments) - 1
    take = next((t for t in takes if _whole(t.get("segment")) == last + 1), None) if is_clip else None
    shot = f"{_path(take)} [output]" if take else None
    action = step["action"]
    entry = {"handle": step["handle"], "kind": "clip" if is_clip else "still",
             "aspect": action.get("aspect") or piece.get("aspect") or run["rail"].get("aspect") or "",
             "turn": 0, "filename": shot or f"{_path(saved)} [{saved.get('type') or 'output'}]",
             "text": action.get("prompt") or ""}
    run["ledger"].append(entry)
    if is_clip and last >= 0:
        held = {**segments[last], chat.STRIP_KEY: step["handle"]}
        if take:
            size = ({"width": _whole(take.get("width")), "height": _whole(take.get("height"))}
                    if take.get("width") and take.get("height") else {})
            held.update(hold=True, take={"filename": shot,
                                         "duration_s": _number(take.get("duration_s")),
                                         **size, "has_audio": take.get("has_audio") is not False})
        run["strip"] = [json.loads(json.dumps(s)) for s in segments[:last]] + [held]
    return entry


def _whole(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value):
    try:
        return float(value) or 0
    except (TypeError, ValueError):
        return 0


def landed(run, row, outputs):
    """The step's render finished with these history outputs. -> the run.

    A prompt that finished without saving anything is a failure, said: the
    next clip has nothing to continue from.
    """
    saved, takes, is_clip = outputs_of(outputs)
    if saved is None:
        return failed(run, row, "the render finished without saving a file")
    run = copy.deepcopy(run)
    step = _step(run, row)
    step.update(state=LANDED, saved=saved, takes=takes, clip=is_clip)
    entry = _landed(run, step, saved, takes, is_clip)
    step["filename"] = entry["filename"]
    run["plan"] = director.land(run["plan"], row, step["handle"], step["mark"])
    return run


def failed(run, row, error):
    """The step failed; so does the run, in the step's words."""
    run = copy.deepcopy(run)
    step = _step(run, row)
    sentence = " ".join(str(error or "the render failed").split())[:600]
    step.update(state=STEP_FAILED, error=sentence)
    run["plan"] = director.fail(run["plan"], row, sentence)
    if run["state"] == RUNNING:
        run["state"] = FAILED
        order = [c["id"] for c in director.clips(run["plan"])]
        run["error"] = (f"clip {order.index(row) + 1} of {len(order)} failed: {sentence}"
                        if row in order else sentence)
    return run


def stopped(run, words=STOPPED_WORDS, state=STOPPED):
    """The run is stopped; a step still building or on the queue is failed in
    `words`, so its row renders again on the next Run."""
    run = copy.deepcopy(run)
    for step in run["steps"]:
        if step["state"] in (BUILDING, QUEUED):
            step.update(state=LOST, error=words)
            run["plan"] = director.fail(run["plan"], step["row"], words)
    if run["state"] == RUNNING:
        run["state"] = state
    return run


def restarted(run):
    """A run read back after the server started: one that was running is
    stopped, never resumed, and its step on the queue is gone with the
    queue."""
    if run.get("state") != RUNNING:
        return run
    return stopped(run, RESTART_WORDS)


# ---- before anything is queued -------------------------------------------------------


def rehearse(run, build):
    """Build every clip of the run in order, sampling none. -> None, or the
    sentence the first clip that would not render is refused in.

    The run stops on its first failure, and a failure an hour in is an hour
    of GPU spent on clips that were going nowhere. Most refusals are not about
    pixels at all — a citation the family cannot read, a seam off its grid, a
    file not picked — and the compiler can say them now. So Run rehearses: each
    step is built with `build(run, step)` (the run's own build, dry-run
    compile included) and landed on a stand-in take of the clip's length, so
    the next one is built `after` it exactly as it will be.
    """
    trial = copy.deepcopy(run)
    order = [c["id"] for c in director.clips(trial["plan"])]
    while True:
        trial, step = next_step(trial)
        if step is None:
            return None if trial["state"] == DONE else trial["error"]
        built = build(trial, step)
        if "problem" in built:
            n = order.index(step["row"]) + 1 if step["row"] in order else "?"
            return f"clip {n} of {len(order)} would not render: {built['problem']}"
        trial = queued(trial, step["row"], "rehearsal", built["piece"])
        take = f"rehearsal-{step['handle']}.mp4"
        trial = landed(trial, step["row"], {"rehearsal": {
            "mmc_video": [{"filename": take, "subfolder": "", "type": "output"}],
            "mmc_takes": [{"segment": len(built["piece"].get("segments") or []), "filename": take,
                           "subfolder": "", "duration_s": step["action"].get("seconds") or 0,
                           "has_audio": True}]}})


# ---- what the room is told --------------------------------------------------------


def public(run):
    """The record as `director/status` answers it: everything the room needs
    to land what it missed and draw the progress line, and nothing only the
    server builds from (the base, the room's ledger and strip as sent)."""
    if not run:
        return None
    current = next((s for s in reversed(run["steps"]) if s["state"] in (BUILDING, QUEUED)), None)
    return {
        "chat": run["chat"], "state": run["state"], "error": run.get("error"),
        # Which plan this is a run of: row ids are minted per plan, so a
        # chat whose plan was replaced must not file this run's clips on it.
        "brief": (run.get("plan") or {}).get("brief"),
        "total": run.get("total") or 0,
        "done": sum(1 for s in run["steps"][run.get("first") or 0:] if s["state"] == LANDED),
        "current": current["row"] if current else None,
        "steps": [{k: s.get(k) for k in ("row", "handle", "mark", "action", "state", "prompt_id",
                                         "piece", "saved", "takes", "clip", "error", "seed")}
                  for s in run["steps"]],
    }


# ---- the loop ---------------------------------------------------------------------------


async def drive(run, io):
    """Run until done, failed or stopped. -> the final record.

    `io` is what the loop may touch, so the same loop runs on ComfyUI's queue
    and in the replay suite:

      * `build(run, step)` -> `{"prompt", "piece"}` or `{"problem": sentence}`,
        the blocking build `chat/render` does (awaitable);
      * `enqueue(prompt)` -> the prompt id;
      * `wait(prompt_id)` -> `("landed", outputs)`, `("failed", sentence)` or
        `("stopped", None)`; it returns early on Stop;
      * `save(run)`, the run file written; `tell(kind, run, step)`, the room
        told on the socket;
      * `stopping()`, whether Stop was pressed.

    Strictly one clip at a time: a `pin` waits for its predecessor's last
    frame, and one GPU does one thing.
    """
    io.save(run)
    io.tell("state", run, None)
    while True:
        if io.stopping():
            run = stopped(run)
            break
        run, step = next_step(run)
        io.save(run)
        if step is None:
            break
        try:
            built = await io.build(run, step)
        except Exception as problem:  # noqa: BLE001 — said in the run, not swallowed
            built = {"problem": f"{type(problem).__name__}: {problem}"}
        if "problem" in built:
            run = failed(run, step["row"], built["problem"])
            io.save(run)
            io.tell("failed", run, _step_of(run, step))
            break
        try:
            prompt_id = await io.enqueue(built["prompt"])
        except Exception as problem:  # noqa: BLE001
            run = failed(run, step["row"], str(problem))
            io.save(run)
            io.tell("failed", run, _step_of(run, step))
            break
        run = queued(run, step["row"], prompt_id, built["piece"])
        io.save(run)
        io.tell("queued", run, _step_of(run, step))
        outcome, detail = await io.wait(prompt_id)
        if outcome == "landed":
            run = landed(run, step["row"], detail)
            io.save(run)
            kind = "landed" if _step_of(run, step)["state"] == LANDED else "failed"
            io.tell(kind, run, _step_of(run, step))
            if kind == "failed":
                break
            continue
        if outcome == "stopped":
            run = stopped(run)
            io.save(run)
            io.tell("failed", run, _step_of(run, step))
            break
        run = failed(run, step["row"], detail)
        io.save(run)
        io.tell("failed", run, _step_of(run, step))
        break
    io.save(run)
    io.tell("state", run, None)
    return run


def _step_of(run, step):
    """The record's copy of `step`, as it stands now."""
    for held in reversed(run["steps"]):
        if held["row"] == step["row"] and held["handle"] == step["handle"]:
            return {k: held.get(k) for k in ("row", "handle", "mark", "action", "state", "prompt_id",
                                             "piece", "saved", "takes", "clip", "error", "seed")}
    return step
