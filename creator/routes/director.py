"""`/continuity/director/*`: the doors Director's plan card knocks on.

Director plans a whole piece in many small model calls
(`creator/director_calls.py`) and keeps the result in a plan whose every rule
is `creator/director.py`'s. Both are pure. What is here is the joining that
cannot be: the room's backend and model, the rail's families and what the
video family declares about length, the rail's planning setting (how many
calls a plan is made in, `director_calls.STEPS`), the chat's cast, and the
queue.

**Planning is one turn, as far as the room can tell.** `director/plan` takes a
brief and answers the plan, the way `chat/turn` takes a message and answers an
action: the remote backend off the queue on the socket (`jobs.answer_later`),
the in-process one on the queue as a `director_plan` job, so `queue.run()` in
the room waits for either. Every call of the plan — brief, basics, beats,
entities, a shots call per beat, and each one's re-ask — runs inside that one
job. A plan is a dozen calls, and a dozen round trips through the browser
would be a dozen waits behind whatever the canvas queued.

**Editing is the server's rules, not a copy of them.** `director/edit` takes
the plan as the card holds it, one row and the fields that changed, and
answers the plan `director.edit` makes of it — through the same readers the
calls' replies went through, so a typed edit is held to exactly what a
model's answer was. It needs no model and no disk, and answers inline. The
card does its own arithmetic (seconds, splits, rows) through the mirror in
`web/creator/director.js`, so a weight changed on the card shows its seconds
before the answer is back; what is *allowed* is decided here.

**A plan turn is a turn.** While a plan is open, what the person says in the
room goes to `director/turn` rather than `chat/turn`, and is answered the
same way: one call decides whether it edits a row, replans, or is a question,
and an edit runs that row's own call again (`director_calls.plan_turn`). A
change to a picture already made comes back as an action for the room to
queue down the edit path, like any prep render.

**A prep render is a chat render.** `director/action` takes the plan and one
row and answers the chat action that row becomes (`director.action_for`) and
its fingerprint now. The room queues the action through `chat/render` like any
other, and when it lands it writes the handle and that fingerprint onto the
plan itself — the record-keeping is the card's mirror of `director.land`, so a
render that lands while the room is closed is still filed (`chat.js land`). A
plan edited while a row rendered lands the render under the old fingerprint,
which is stale against the new one: nothing to reconcile.

**Stateless, like the chat, until the run.** The plan lives in the browser,
on the message that drew its card, and is saved with the chat
(`chatstore.js`). Nothing above keeps one between requests. The run (§8 of
the spec) is the exception, and only because it must outlive the tab:
`director/run` takes the approved plan and everything a clip is built from,
keeps it in one file per chat beside the chats, and a task here puts the next
clip on the queue each time the last one lands (`director_run.drive`). The
room follows it on the socket (`mmc_director`) and lands each clip as it
lands its own; a room opened later asks `director/status` and lands what it
missed. A server that restarts brings a running run back stopped.
"""

import asyncio
import glob
import json
import logging
import os
import re

from aiohttp import web

from server import PromptServer

from .. import chat, director, director_calls, director_run, jobs, settings
from ..families import manifest, refine
from ..guard import same_origin
from . import chat as chat_routes

log = logging.getLogger(__name__)


# ---- what planning is told ------------------------------------------------------


def rail_of(block):
    """The room's rail as a plan snapshots it -> `director.follow_rail`'s
    input: the three families by id, the shape, and the video family's own
    floor and ceiling off its manifest, which `director.limit_of` clamps the
    shot limit to.

    Read through `chat_routes._rail`, so an unknown or absent family is the
    registry's default here exactly as it is for a turn: the plan is made for
    the families a render from this room would use.
    """
    rail = chat_routes._rail(block)
    described = manifest.describe(rail["video_family"]) or {}
    frames = (described.get("canvas") or {}).get("frames") or {}
    # Whether the family is sent pictures as references: then a shot opens
    # from its cast and sheets, and the plan's storyboard starts off
    # (`director.new_plan`).
    pictures = ((described.get("reference") or {}).get("max") or {}).get("image") or 0
    return {"still": rail["still_family"], "edit": rail.get("edit_family"),
            "video": rail["video_family"], "aspect": block.get("aspect") or None,
            "min_seconds": frames.get("min_seconds"), "max_seconds": frames.get("max_seconds"),
            "references": pictures > 0}


def cited_cast(brief, cast):
    """The chat's cast members the brief cites with `@` -> `[{name,
    description}]`, in the order the brief names them.

    Only the cited: the spec's §7. Director does not go through the cast
    looking for somebody who might fit; a member the person did not name is
    a member they did not ask for, and the entity call writes a new one.
    """
    known = {m["name"].lower(): m for m in cast or ()}
    out = []
    for word in director.CITE_RE.findall(brief or ""):
        member = known.get(word.lower())
        if member and member not in out:
            out.append(member)
    return [{"name": m["name"], "description": m.get("description") or ""} for m in out]


def cited_ledger(brief, ledger):
    """The ledger's files the brief cites by handle -> `[{handle, kind, text}]`,
    what the calls are told is already pictured."""
    named = set(director_calls._HANDLE_RE.findall(brief or ""))
    return [{"handle": e["handle"], "kind": e.get("kind") or "picture", "text": e.get("text") or ""}
            for e in ledger or () if isinstance(e, dict) and e.get("handle") in named]


# The least a large-profile reply may run to, in tokens. The rail's reply
# budget is sized for a turn — a plan line and one object, 1024 by default —
# and the small calls fit it; the structure of a long piece and its whole
# shot list in one reply do not, and a reply cut off is a failed call with a
# sentence about the slider. So the large profile lifts the floor to this and
# leaves a slider set higher alone.
LARGE_REPLY_TOKENS = 4096


def asker(block, steps=director_calls.SMALL):
    """`director_calls`'s `ask(system, message, schema, label)` over the room's
    backend. The schema is sent where the backend can constrain to one
    (`refine_remote.chat`'s `response_format`); the in-process refiner gets
    the prompt alone and the reader does the rest, as it does for a turn.
    On the large profile the reply budget is at least `LARGE_REPLY_TOKENS`."""
    if steps == director_calls.LARGE:
        budget = chat.reply_tokens(block.get("reply_tokens"))
        block = {**block, "reply_tokens": max(budget, LARGE_REPLY_TOKENS)}

    def ask(system, message, schema, _label):
        return chat_routes._ask(block, system, message, schema=schema)
    return ask


def _plan(body):
    """The blocking half of `director/plan`. -> `{plan, questions,
    assumptions, warnings}`.

    `answers` is the person's reply to questions the brief call asked: the
    brief and the answer are planned together, and the brief call is not
    asked again — two questions is the most the room puts to anybody before
    planning (§5.2), and a small model asked again asks again.
    """
    block = body.get("settings") or {}
    brief = " ".join(str(body.get("brief") or "").split())
    if not brief:
        raise director.PlanError("a brief must say what the piece is.")
    answer = " ".join(str(body.get("answer") or "").split())
    if answer:
        brief = f"{brief} {answer}"
    ledger, cast = chat_routes._with_piece(body)
    steps = director_calls.steps_of(block.get("plan_steps"))
    result = director_calls.plan_piece(
        brief, rail_of(block), asker(block, steps),
        cast=cited_cast(brief, cast), ledger=cited_ledger(brief, ledger),
        keyframes=body.get("keyframes") if isinstance(body.get("keyframes"), bool) else None,
        questions=not answer and body.get("questions", True) is not False, steps=steps)
    # The log keeps every raw reply, which is the bench's to print and not
    # the room's to carry in a saved chat.
    return {"plan": result["plan"], "brief": brief, "questions": result["questions"],
            "assumptions": result["assumptions"], "warnings": result.get("warnings") or []}


_EXPECTED = (refine.RefineError, chat.ActionError, director.PlanError,
             director_calls.PlanningFailed)


def _plan_job(body):
    """`_plan` on the queue — `routes.chat._run_job`'s terms: the pack's own
    refusals are a sentence for the room, anything else a bug said as one."""
    try:
        return _plan(body)
    except _EXPECTED as problem:
        raise jobs.JobError(str(problem)) from problem


jobs.register("director_plan", _plan_job)


async def _answered(request, work, job):
    """A request that needs the model, answered the way a chat turn is:
    `{"answer_id"}` on the remote backend, `{"prompt_id"}` on the in-process
    one (as the queued `job`), the result on the socket either way."""
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)

    block = body.get("settings") or {}
    refused = chat_routes._no_model(block)
    if refused is not None:
        return refused
    if block.get("backend") == "remote":
        answer_id = jobs.answer_later(lambda: work(body), body.get("client_id"), _EXPECTED)
        return web.json_response({"answer_id": answer_id})
    try:
        prompt_id = await jobs.submit(job, body, body.get("client_id"))
    except jobs.JobError as problem:
        return web.json_response({"error": str(problem)}, status=500)
    return web.json_response({"prompt_id": prompt_id})


@PromptServer.instance.routes.post("/continuity/director/plan")
@same_origin
async def director_plan(request):
    """A brief -> its plan, or the brief call's questions."""
    return await _answered(request, _plan, "director_plan")


# ---- plan turns -------------------------------------------------------------------


def _turn(body):
    """The blocking half of `director/turn`: what the person said about an
    open plan -> `{plan, act, row, say, render, recast, warnings}`
    (`director_calls.plan_turn`; `plan` is None when nothing changed).

    The turn is told about the cast members the plan already uses, so a
    rewritten shot can cite them, and the ones the person's words cite,
    which is how "use @george for the keeper" reaches it. It is told the
    attached files the brief, the shots or the words cite, since a rewritten
    shot may cite them again and nothing else."""
    block = body.get("settings") or {}
    plan = director.validate(body.get("plan"))
    text = " ".join(str(body.get("text") or "").split())
    if not text:
        raise director.PlanError("a message about the plan must say something.")
    ledger, cast = chat_routes._with_piece(body)
    used = " ".join("@" + e["source"]["cited"] for e in plan["entities"]
                    if "cited" in (e.get("source") or {}))
    told = " ".join([plan["brief"], text] + [s["action"] for s in plan["shots"]])
    steps = director_calls.steps_of(block.get("plan_steps"))
    result = director_calls.plan_turn(
        plan, text, asker(block, steps), cast=cited_cast(f"{used} {text}", cast),
        ledger=cited_ledger(told, ledger), steps=steps)
    return {key: result.get(key) for key in
            ("plan", "act", "row", "say", "render", "recast", "warnings")}


def _turn_job(body):
    try:
        return _turn(body)
    except _EXPECTED as problem:
        raise jobs.JobError(str(problem)) from problem


jobs.register("director_turn", _turn_job)


@PromptServer.instance.routes.post("/continuity/director/turn")
@same_origin
async def director_turn(request):
    """Something said in the room while a plan is open -> the plan changed,
    or an answer (§5.4 of the spec)."""
    return await _answered(request, _turn, "director_turn")


# ---- editing --------------------------------------------------------------------


def _edit(body):
    """-> the plan with one row changed, validated. `PlanError` as a sentence
    naming the row and the field when the change is refused."""
    plan = body.get("plan")
    row = str(body.get("row") or "")
    fields = body.get("fields")
    director.validate(plan)
    return {"plan": director.edit(plan, row, fields)}


@PromptServer.instance.routes.post("/continuity/director/edit")
@same_origin
async def director_edit(request):
    """One row of a plan changed on the card. -> `{"result": {plan}}` inline,
    or `{"error"}` with the sentence the card shows under the row."""
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)
    loop = asyncio.get_running_loop()
    try:
        return web.json_response({"result": await loop.run_in_executor(None, _edit, body)})
    except director.PlanError as problem:
        return web.json_response({"error": str(problem)}, status=400)
    except Exception as problem:  # noqa: BLE001 — said to the card, not swallowed
        log.exception("[Continuity] a plan edit failed")
        return web.json_response({"error": f"{type(problem).__name__}: {problem}"}, status=500)


# ---- prep ---------------------------------------------------------------------------


def _action(body):
    """-> `{action, mark}`: what one row renders as, and the fingerprint the
    render lands under. `PlanError` when something the row cites has not
    landed, or the row is not in the plan."""
    plan = director.validate(body.get("plan"))
    row = str(body.get("row") or "")
    return {"action": director.action_for(plan, row), "mark": director.fingerprint(plan, row)}


@PromptServer.instance.routes.post("/continuity/director/action")
@same_origin
async def director_action(request):
    """One row of a plan -> `{"result": {action, mark}}` inline, or `{"error"}`
    in a sentence. No model, no disk: the room queues the action itself."""
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)
    try:
        return web.json_response({"result": _action(body)})
    except director.PlanError as problem:
        return web.json_response({"error": str(problem)}, status=400)
    except Exception as problem:  # noqa: BLE001 — said to the card, not swallowed
        log.exception("[Continuity] a plan row's action failed")
        return web.json_response({"error": f"{type(problem).__name__}: {problem}"}, status=500)


# ---- the run ------------------------------------------------------------------------
#
# The one piece of Director the server keeps (§8 of the spec): a run takes as
# long as a dozen clips take and must go on with the tab closed, so the loop
# that puts the next clip on the queue lives here, in a task beside the
# prompt worker, and what it has done lives in one file per chat. The moves
# are `creator/director_run.py`'s, pure; this is the disk, the queue and the
# socket they are played on.

RUN_EVENT = "mmc_director"
RUN_FILE = "continuity.director.{chat}.json"
_CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# How often a step on the queue is looked for in the history. The history is a
# dict lookup under the queue's mutex; twice a second is nothing to it and
# well inside what a person notices of a clip that took minutes.
POLL_SECONDS = 0.5

# How long a prompt may be neither on the queue nor in the history before it
# is called gone: somebody took it off the queue from ComfyUI's own panel.
GONE_AFTER = 10.0


class _Live:
    """A chat's run while this server holds it: the record, its file, the tab
    whose progress bar and previews the next clip reports to, and Stop."""

    def __init__(self, run, path, client_id):
        self.run, self.path, self.client = run, path, client_id
        self.stop = False
        self.task = None

    def going(self):
        # A run with no task yet is one a press is starting right now.
        if self.task is None:
            return self.run.get("state") == director_run.RUNNING
        return not self.task.done()


_runs = {}
# The loop tasks, held strongly for the same reason `jobs._answering` is.
_driving = set()


def _run_path(request, chat_id):
    """Where a chat's run file lives: beside its chat, in the asking user's
    userdata directory, as `chatstore.js` writes the chat itself."""
    if not _CHAT_ID.match(chat_id or ""):
        raise director_run.RunError("that is not a chat this room saved.")
    name = RUN_FILE.format(chat=chat_id)
    manager = getattr(PromptServer.instance, "user_manager", None)
    if manager is not None and request is not None:
        try:
            path = manager.get_request_user_filepath(request, name)
        except KeyError:
            path = None
        if path:
            return path
    import folder_paths

    return os.path.join(folder_paths.get_user_directory(), "default", name)


def _read_run(path):
    try:
        with open(path, encoding="utf-8") as handle:
            run = json.load(handle)
    except (OSError, ValueError):
        return None
    return run if isinstance(run, dict) and run.get("version") == director_run.VERSION else None


def _write_run(path, run):
    """Whole or not at all: a run file half written by a crash would come back
    as no run, and the clips it had landed with it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.part"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(run, handle, ensure_ascii=False)
    os.replace(temporary, path)


def restart_runs(root=None):
    """Every run file a previous server left running, stopped (§8: a restart
    is not consent to spend the GPU). Called once, when this module is
    imported, which is when the server starts. -> the files changed."""
    import folder_paths

    root = root or folder_paths.get_user_directory()
    changed = []
    for path in glob.glob(os.path.join(root, "*", RUN_FILE.format(chat="*"))):
        run = _read_run(path)
        if run and run.get("state") == director_run.RUNNING:
            try:
                _write_run(path, director_run.restarted(run))
                changed.append(path)
            except OSError:
                log.warning("[Continuity] could not stop the run in %s", path)
    return changed


try:
    restart_runs()
except Exception:  # noqa: BLE001 — a bad user directory must not stop the pack loading
    log.exception("[Continuity] reading Director's run files at start failed")


def _brief(run):
    """The record without its steps: what every socket message carries."""
    public = director_run.public(run) or {}
    return {k: v for k, v in public.items() if k != "steps"}


def _build_step(run, step):
    """One run step's render, built the way `chat/render` builds one: the
    action held to `chat.validate` against the run's ledger, strip and cast,
    then `_build` over the room's base with the step's seed."""
    ledger, cast = chat_routes._with_piece({"piece": run["piece"], "ledger": run["ledger"]})
    try:
        action = chat.with_seam(chat.validate(step["action"], ledger,
                                              strip=[c.get(chat.STRIP_KEY) for c in run["strip"]],
                                              cast=[m.get("name") for m in cast]),
                                step["action"])
        piece = run["base"]["piece"]
        rail = chat_routes._rail({**run["rail"], **chat_routes._families_of(piece, False)})
    except chat.ActionError as problem:
        return {"problem": str(problem)}
    base = (piece, {**run["base"]["widgets"], "seed": step["seed"]})
    return chat_routes._build(action, ledger, rail, settings.load().get("weights") or {},
                              base, run["strip"], cast)


def _outcome(record, cancelled):
    """A prompt's history record -> `director_run.drive`'s wait answer."""
    status = record.get("status") or {}
    if status.get("status_str") == "success" or status.get("completed"):
        return "landed", record.get("outputs") or {}
    if cancelled:
        return "stopped", None
    for event, data in status.get("messages") or []:
        if event == "execution_error":
            return "failed", (data or {}).get("exception_message") or "the render failed"
        if event == "execution_interrupted":
            return "failed", "cancelled"
    return "failed", "the render failed"


def _interrupt(queue, prompt_id):
    """Interrupt `prompt_id` if it is the one sampling, and nothing else.

    Core's own atomic check where it has one (`interrupt_if_running`); on a
    core from before it, the same check without the atomicity, which is what
    `/interrupt` with a prompt id did then."""
    if hasattr(queue, "interrupt_if_running"):
        return queue.interrupt_if_running(prompt_id)
    import nodes

    running, _pending = queue.get_current_queue_volatile()
    if any(item[1] == prompt_id for item in running):
        nodes.interrupt_processing()
        return True
    return False


class _Queue:
    """`director_run.drive`'s io, on ComfyUI's queue."""

    def __init__(self, live):
        self.live = live

    async def build(self, run, step):
        return await asyncio.get_running_loop().run_in_executor(None, _build_step, run, step)

    async def enqueue(self, prompt):
        return await jobs.enqueue(prompt, self.live.client)

    async def wait(self, prompt_id):
        queue = PromptServer.instance.prompt_queue
        cancelled, gone = False, 0.0
        while True:
            if self.live.stop and not cancelled:
                cancelled = True
                if not queue.delete_queue_item(lambda item: item[1] == prompt_id):
                    _interrupt(queue, prompt_id)
            record = queue.get_history(prompt_id=prompt_id).get(prompt_id)
            if record:
                return _outcome(record, cancelled)
            running, pending = queue.get_current_queue_volatile()
            if any(item[1] == prompt_id for item in [*running, *pending]):
                gone = 0.0
            elif cancelled:
                return "stopped", None
            else:
                gone += POLL_SECONDS
                if gone >= GONE_AFTER:
                    return "failed", "it was taken off the queue"
            await asyncio.sleep(POLL_SECONDS)

    def save(self, run):
        self.live.run = run
        _write_run(self.live.path, run)

    def tell(self, kind, run, step):
        PromptServer.instance.send_sync(RUN_EVENT, {"kind": kind, "chat": run["chat"],
                                                    "run": _brief(run), "step": step}, None)

    def stopping(self):
        return self.live.stop


async def _drive(live):
    io = _Queue(live)
    try:
        await director_run.drive(live.run, io)
    except Exception as problem:  # noqa: BLE001 — a bug, said in the run and the log
        log.exception("[Continuity] Director's run stopped on a bug")
        run = director_run.stopped(live.run, words=f"{type(problem).__name__}: {problem}",
                                   state=director_run.FAILED)
        run["error"] = f"{type(problem).__name__}: {problem}"
        try:
            io.save(run)
        except OSError:
            live.run = run
        io.tell("state", run, None)


def _start(request, body):
    chat_id = str(body.get("chat") or "")
    path = _run_path(request, chat_id)
    live = _runs.get(chat_id)
    if live is not None and live.going():
        raise director_run.RunError("this chat's run is still going. Stop it first.")
    prior = live.run if live is not None else _read_run(path)
    run = director_run.begin(
        chat_id, body.get("plan"), ledger=body.get("ledger"), strip=body.get("strip"),
        piece=body.get("piece"), rail=body.get("rail"), base=body.get("base"),
        handles=body.get("handles"), prior=director_run.restarted(prior) if prior else None)
    # Every clip built and compiled first, sampling none: a clip that cannot
    # render is said now, not after the ones in front of it have spent the GPU.
    refused = director_run.rehearse(run, _build_step)
    if refused:
        raise director_run.RunError(refused)
    live = _Live(run, path, body.get("client_id"))
    _runs[chat_id] = live
    return live


@PromptServer.instance.routes.post("/continuity/director/run")
@same_origin
async def director_run_route(request):
    """Run an approved plan to the end. -> `{"result": the run}` once the loop
    has started; every clip after that is told on the socket as
    `mmc_director`, and the run file says the same to a room opened later."""
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)
    # Off the loop: the rehearsal reads the settings, the model folders and
    # every picture a clip opens on.
    loop = asyncio.get_running_loop()
    try:
        live = await loop.run_in_executor(None, _start, request, body)
    except (director_run.RunError, director.PlanError) as problem:
        return web.json_response({"error": str(problem)}, status=400)
    except Exception as problem:  # noqa: BLE001 — said to the card, not swallowed
        log.exception("[Continuity] starting a Director run failed")
        return web.json_response({"error": f"{type(problem).__name__}: {problem}"}, status=500)
    live.task = loop.create_task(_drive(live))
    _driving.add(live.task)
    live.task.add_done_callback(_driving.discard)
    return web.json_response({"result": director_run.public(live.run)})


@PromptServer.instance.routes.post("/continuity/director/stop")
@same_origin
async def director_stop(request):
    """Stop a chat's run: the clip on the queue is taken off it, or interrupted
    if it is sampling, through ComfyUI's own cancel. -> `{"result": the run}`;
    the run says `stopped` on the socket once the clip has let go."""
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "the request body was not JSON"}, status=400)
    live = _runs.get(str(body.get("chat") or ""))
    if live is None:
        return web.json_response({"result": None})
    live.stop = True
    return web.json_response({"result": director_run.public(live.run)})


@PromptServer.instance.routes.get("/continuity/director/status")
async def director_status(request):
    """A chat's run, as the room catches up with it on opening the chat:
    every step with what it landed as. `client_id` makes the asking tab the
    one the next clip's progress and previews go to. -> `{"result": run or
    null}`."""
    chat_id = request.query.get("chat", "")
    live = _runs.get(chat_id)
    if live is not None:
        if request.query.get("client_id") and live.going():
            live.client = request.query["client_id"]
        return web.json_response({"result": director_run.public(live.run)})
    try:
        path = _run_path(request, chat_id)
    except director_run.RunError as problem:
        return web.json_response({"error": str(problem)}, status=400)
    loop = asyncio.get_running_loop()
    run = await loop.run_in_executor(None, _read_run, path)
    return web.json_response({"result": director_run.public(run)})
