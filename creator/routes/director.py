"""`/continuity/director/*`: the doors Director's plan card knocks on.

Director plans a whole piece in many small model calls
(`creator/director_calls.py`) and keeps the result in a plan whose every rule
is `creator/director.py`'s. Both are pure. What is here is the joining that
cannot be: the room's backend and model, the rail's families and what the
video family declares about length, the chat's cast, and the queue.

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

**Stateless, like the chat.** The plan lives in the browser, on the message
that drew its card, and is saved with the chat (`chatstore.js`). Nothing here
keeps one between requests. The run (§8 of the spec) will be the exception,
and only because it must outlive the tab.
"""

import asyncio
import logging

from aiohttp import web

from server import PromptServer

from .. import chat, director, director_calls, jobs
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


def asker(block):
    """`director_calls`'s `ask(system, message, schema, label)` over the room's
    backend. The schema is sent where the backend can constrain to one
    (`refine_remote.chat`'s `response_format`); the in-process refiner gets
    the prompt alone and the reader does the rest, as it does for a turn."""
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
    result = director_calls.plan_piece(
        brief, rail_of(block), asker(block),
        cast=cited_cast(brief, cast), ledger=cited_ledger(brief, ledger),
        keyframes=body.get("keyframes") if isinstance(body.get("keyframes"), bool) else None,
        questions=not answer and body.get("questions", True) is not False)
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
    result = director_calls.plan_turn(
        plan, text, asker(block), cast=cited_cast(f"{used} {text}", cast),
        ledger=cited_ledger(told, ledger))
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
