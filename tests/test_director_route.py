"""Director's plan route plans with the room's backend, rail and cast.

    COMFYUI_PATH=~/ComfyUI <comfy-venv>/bin/python3 tests/test_director_route.py

`tests/test_director_calls.py` pins the planning loop with a fake `ask`. This is
the route's half, which needs the registry and the manifests: that the rail a
plan is made for is the room's (unknown families falling back as a turn's do,
the video family's own floor and ceiling read off its manifest), that only the
cast members and attached files the brief cites are passed in as already
there, that every call goes through the room's one `_ask` with its schema, that
a brief whose questions were answered is planned without asking again, and that
an edit from the card is held to `director.edit`'s rules. The model is a
replay: no backend is reached.

Skips itself with a message if ComfyUI cannot be imported.
"""

import asyncio
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)

COMFY = os.environ.get("COMFYUI_PATH", os.path.expanduser("~/ComfyUI"))
BASE = os.environ.get("COMFYUI_BASE", COMFY)


def _boot():
    sys.path.insert(0, COMFY)
    sys.argv = ["main.py", "--base-directory", BASE]
    import nodes
    import server

    loop = asyncio.new_event_loop()
    try:
        from app.assets.manager import default_asset_manager
        server.PromptServer(loop, default_asset_manager())
    except (ImportError, TypeError):
        server.PromptServer(loop)
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nodes.init_extra_nodes(init_custom_nodes=False))
    sys.path.insert(0, os.path.dirname(ROOT))


try:
    _boot()
except Exception as exc:  # noqa: BLE001
    print(f"skipped: ComfyUI not importable ({type(exc).__name__}: {exc})")
    sys.exit(0)

importlib.import_module(PACKAGE)
route = importlib.import_module(f"{PACKAGE}.creator.routes.director")
chat_routes = importlib.import_module(f"{PACKAGE}.creator.routes.chat")
director = importlib.import_module(f"{PACKAGE}.creator.director")
manifest = importlib.import_module(f"{PACKAGE}.creator.families.manifest")
registry = importlib.import_module(f"{PACKAGE}.creator.families.registry")

from harness import FAILURES, check, passed  # noqa: E402


# ---- the replay ----------------------------------------------------------------

def fence(obj):
    return "```json\n" + json.dumps(obj) + "\n```"


REPLIES = {
    "questions": {"questions": [], "assumptions": ["no dialogue"]},
    "title": {"title": "The Bottle", "seconds": 12, "look": "overcast, teal"},
    "beats": {"beats": [{"text": "@george finds a bottle on the rocks", "weight": "medium"},
                        {"text": "@george reads the note inside", "weight": "medium"}]},
    "entities": {"entities": [{"name": "bottle", "kind": "thing", "description": "a green glass bottle"},
                              {"name": "george", "kind": "person", "description": "listed anyway"}]},
}
SHOTS = [
    {"shots": [{"action": "@george stoops to lift the bottle from the rocks", "continues": "new"}]},
    {"shots": [{"action": "@george unrolls the damp paper and reads", "continues": "cut"}]},
]

calls = []


def fake_ask(block, system, message, schema=None):
    calls.append({"block": block, "schema": schema, "message": message})
    key = next(k for k in ("questions", "title", "beats", "entities", "shots")
               if k in (schema or {}).get("properties", {}))
    if key == "shots":
        return fence(SHOTS[sum(1 for c in calls if "shots" in c["schema"]["properties"]) - 1])
    return fence(REPLIES[key])


real_ask = chat_routes._ask
chat_routes._ask = fake_ask

PIECE = {"subjects": [{"handle": "george", "from": ["pic-1"], "description": "a weathered man of seventy"},
                      {"handle": "anna", "from": ["pic-2"], "description": "not in this piece"}],
         "assets": []}
LEDGER = [{"handle": "pic-1", "kind": "image", "filename": "g.png", "text": "george"},
          {"handle": "pic-3", "kind": "image", "filename": "rocks.png", "text": "the rocks"},
          {"handle": "pic-4", "kind": "image", "filename": "other.png", "text": "unrelated"}]
SETTINGS = {"backend": "remote", "model": "m", "video_family": "h3", "still_family": "nonsense",
            "aspect": "16:9"}


# ---- the rail --------------------------------------------------------------------

rail = route.rail_of(SETTINGS)
frames = manifest.describe("h3")["canvas"]["frames"]
check("the video family is the room's", rail["video"], "h3")
check("an unknown still family falls back as a turn's does",
      rail["still"], registry.STILL_ARCHES[registry.DEFAULT_STILL_ARCH])
check("the ceiling is the video family's own", rail["max_seconds"], frames.get("max_seconds"))
check("H3 takes references, so its plans open shots from them", rail["references"], True)
check("the floor is the video family's own", rail["min_seconds"], frames.get("min_seconds"))
check("the shape is the room's", rail["aspect"], "16:9")
check("no shape is no shape", route.rail_of({})["aspect"], None)


# ---- what planning is told -------------------------------------------------------

cast = chat_routes.chat.cast_entries(PIECE)
check("only the cast the brief cites is passed in",
      route.cited_cast("@george on the rocks, and @George again", cast),
      [{"name": "george", "description": "a weathered man of seventy"}])
check("a brief citing nobody passes nobody", route.cited_cast("a bottle", cast), [])
check("only the files the brief cites are passed in",
      route.cited_ledger("on the rocks of @pic-3", LEDGER),
      [{"handle": "pic-3", "kind": "image", "text": "the rocks"}])


# ---- a plan ----------------------------------------------------------------------

body = {"brief": "a 12 second piece: @george finds a bottle on the rocks of @pic-3",
        "settings": SETTINGS, "piece": PIECE, "ledger": LEDGER}
result = route._plan(body)
doc = result["plan"]

check("every call went through the room's one ask, with its block",
      {id(c["block"]) for c in calls}, {id(SETTINGS)})
check("every call carried its schema", all(c["schema"] for c in calls), True)
check("the calls were the brief, basics, beats, entities and a shots call per beat",
      len(calls), 6)
check("the plan is valid", director.validate(doc) is doc, True)
check("the person's length beat the model's", doc["seconds"], 12)
check("the rail is snapshotted on the plan", doc["rail"]["video"], "h3")
check("the cited member is cast, not made",
      [(e["name"], e["source"]) for e in doc["entities"]],
      [("george", {"cited": "george"}), ("bottle", {"new": True})])
check("the uncited member was never mentioned to the model",
      any("anna" in c["message"] for c in calls), False)
check("the attached file was", "@pic-3" in calls[0]["message"], True)
check("an uncited file was not", any("@pic-4" in c["message"] for c in calls), False)
check("the assumption is on the plan", doc["assumptions"], ["no dialogue"])
check("the raw log is not sent back to the room", "log" in result, False)
check("the brief planned is the one sent", result["brief"], body["brief"])


# ---- questions, and the answer to them ------------------------------------------

calls.clear()
REPLIES["questions"] = {"questions": ["Day or night?"], "assumptions": []}
asked = route._plan(dict(body, brief="a piece about a bottle"))
check("a question stops planning", (asked["plan"], asked["questions"]), (None, ["Day or night?"]))
check("...after the one call", len(calls), 1)

calls.clear()
answered = route._plan(dict(body, brief="a piece about @george and a bottle", answer="at night"))
check("an answer is planned beside its brief", answered["brief"],
      "a piece about @george and a bottle at night")
check("...without asking again", any("questions" in c["schema"]["properties"] for c in calls), False)
check("...into a plan", answered["plan"] is not None, True)


# ---- the rail's planning setting --------------------------------------------------
#
# `plan_steps: "large"` on the block is the two-call profile; anything else,
# or nothing, is the small calls above. The replay answers by schema, so the
# structure call is told apart by its "beats" and "title" together.

STRUCTURE = {"questions": [], "assumptions": ["dusk"], "title": "The Bottle", "seconds": 12,
             "look": "overcast, teal", "camera": "",
             "beats": REPLIES["beats"]["beats"], "entities": REPLIES["entities"]["entities"]}
SHOTLIST = {"shots": [dict(SHOTS[0]["shots"][0], beat=1), dict(SHOTS[1]["shots"][0], beat=2)]}


def large_ask(block, system, message, schema=None):
    calls.append({"block": block, "schema": schema, "message": message})
    properties = (schema or {}).get("properties", {})
    if "title" in properties and "beats" in properties:
        return fence(STRUCTURE)
    if "shots" in properties:
        return fence(SHOTLIST)
    raise AssertionError("a small call on the large profile: " + ", ".join(properties))


chat_routes._ask = large_ask
calls.clear()
big = route._plan(dict(body, settings={**SETTINGS, "plan_steps": "large"}))["plan"]
check("the large profile plans in two calls", len(calls), 2)
check("...with the reply budget lifted to the profile's floor",
      [c["block"]["reply_tokens"] for c in calls], [route.LARGE_REPLY_TOKENS] * 2)
check("...into the same document", ([b["id"] for b in big["beats"]], [s["beat"] for s in big["shots"]],
                                    big["seconds"], [e["name"] for e in big["entities"]]),
      (["b1", "b2"], ["b1", "b2"], 12, ["george", "bottle"]))
calls.clear()
try:
    route._plan(dict(body, settings={**SETTINGS, "plan_steps": "huge"}))
except AssertionError as small:
    check("a setting this build has no profile for is the small calls", "questions" in str(small), True)
else:
    FAILURES.append("an unknown planning setting did not fall back to the small calls")
chat_routes._ask = fake_ask

try:
    route._plan(dict(body, brief="   "))
except director.PlanError as problem:
    check("an empty brief is refused in a sentence", "brief" in str(problem), True)
else:
    FAILURES.append("an empty brief was planned")


# ---- the schema reaches only the remote backend ----------------------------------

seen = {}


def remote_chat(model, system, message, images, **kw):
    seen["remote"] = kw
    return "{}"


def local_chat(model, system, message, images, **kw):
    seen["local"] = kw
    return "{}"


refine_routes = importlib.import_module(f"{PACKAGE}.creator.refine_routes")
original_backend = refine_routes._backend
refine_routes._backend = lambda block: ((remote_chat if block.get("backend") == "remote" else local_chat), None)
try:
    real_ask({"backend": "remote", "model": "m"}, "s", "m", schema={"type": "object"})
    check("the remote backend is sent the schema", seen["remote"].get("schema"), {"type": "object"})
    real_ask({"backend": "remote", "model": "m"}, "s", "m")
    check("...only when there is one", "schema" in seen["remote"], False)
    real_ask({"backend": "local", "model": "m"}, "s", "m", schema={"type": "object"})
    check("the in-process backend never is", "schema" in seen["local"], False)
finally:
    refine_routes._backend = original_backend


# ---- editing ---------------------------------------------------------------------

edited = route._edit({"plan": doc, "row": "b1", "fields": {"weight": "long"}})["plan"]
check("an edit lands", edited["beats"][0]["weight"], "long")
check("...and the seconds follow", director.allot_plan(edited)["b1"] > director.allot_plan(doc)["b1"], True)
check("the plan sent is not changed in place", doc["beats"][0]["weight"], "medium")

for label, sent, fragment in [
    ("a field a row does not have", {"plan": doc, "row": "b1", "fields": {"seconds": 4}}, "no field"),
    ("a citation of nobody", {"plan": doc, "row": "s1", "fields": {"action": "@nobody waits"}}, "@nobody"),
    ("a row that is not there", {"plan": doc, "row": "s9", "fields": {"action": "x"}}, "no row s9"),
    ("a length too short for its shots", {"plan": doc, "row": "header", "fields": {"seconds": 1}}, "seconds"),
    ("no plan at all", {"plan": None, "row": "b1", "fields": {"text": "x"}}, "not a Director plan"),
]:
    try:
        route._edit(sent)
    except director.PlanError as problem:
        if fragment not in str(problem):
            FAILURES.append(f"{label}: {str(problem)!r} does not mention {fragment!r}")
    else:
        FAILURES.append(f"{label}: was not refused")

# ---- a prep row's action -----------------------------------------------------

made = [r["id"] for r in director.rows(doc) if r["kind"] == "sheet"]
if made:
    first = made[0]
    answer = route._action({"plan": doc, "row": first})
    check("a sheet's action is a still", answer["action"]["kind"], "still")
    check("...with the fingerprint it lands under", answer["mark"], director.fingerprint(doc, first))
frame = next((r for r in director.rows(doc) if r["kind"] == "keyframe" and r["deps"]), None)
if frame:
    try:
        route._action({"plan": doc, "row": frame["id"]})
    except director.PlanError as problem:
        check("a keyframe before its sheet is refused by name", frame["deps"][0] in str(problem), True)
    else:
        FAILURES.append("a keyframe before its sheet was not refused")
try:
    route._action({"plan": doc, "row": "e99"})
except director.PlanError as problem:
    check("a row that is not there is refused", "no row e99" in str(problem), True)
else:
    FAILURES.append("a missing row's action was not refused")

# ---- a plan turn ---------------------------------------------------------------

turn_calls = []


def turn_ask(replies):
    def ask(block, system, message, schema=None):
        turn_calls.append({"block": block, "message": message, "schema": schema})
        return fence(replies.pop(0))
    return ask


chat_routes._ask = turn_ask([{"act": "say", "row": "", "change": "", "say": "Two shots."}])
said = route._turn({"plan": doc, "text": "how many shots?", "settings": SETTINGS,
                    "piece": PIECE, "ledger": LEDGER})
check("a question about the plan is answered, the plan unchanged",
      (said["act"], said["say"], said["plan"]), ("say", "Two shots.", None))
check("...through the room's one ask", turn_calls[0]["block"] is SETTINGS, True)
check("...told who the plan already casts", "@george — cast: a weathered man of seventy"
      in turn_calls[0]["message"], True)
check("...and nothing else the room keeps", "log" in said, False)

turn_calls.clear()
chat_routes._ask = turn_ask([
    {"act": "edit", "row": "shot 1", "change": "Closer.", "say": ""},
    {"shots": [{"action": "Close on @george lifting @bottle from @pic-3.", "continues": "new"}]}])
edited = route._turn({"plan": doc, "text": "closer on the first shot", "settings": SETTINGS,
                      "piece": PIECE, "ledger": LEDGER})
check("an edit comes back as the plan with the row changed",
      (edited["row"], edited["plan"]["shots"][0]["action"]),
      ("s1", "Close on @george lifting @bottle from @pic-3."))
check("...the rewritten shot may cite a file the brief attached",
      "@pic-3 — attached image: the rocks" in turn_calls[1]["message"], True)

turn_calls.clear()
person = director.validate(director.add_entities(
    doc, [{"name": "keeper", "kind": "person", "description": "an old keeper"}]))
chat_routes._ask = turn_ask([{"act": "edit", "row": "@keeper", "change": "Anna plays the keeper.", "say": ""}])
recast = route._turn({"plan": person, "text": "use @anna for the keeper", "settings": SETTINGS,
                      "piece": PIECE, "ledger": LEDGER})
check("a cast member the words cite recasts a person",
      (recast["recast"], recast["plan"]["entities"][-1]["source"]), ("anna", {"cited": "anna"}))
chat_routes._ask = fake_ask

try:
    route._turn({"plan": doc, "text": "  ", "settings": SETTINGS})
except director.PlanError as problem:
    check("an empty message is refused in a sentence", "must say something" in str(problem), True)
else:
    FAILURES.append("an empty plan turn was answered")

# ---- the run's file ------------------------------------------------------------------

import tempfile  # noqa: E402

run_mod = importlib.import_module(f"{PACKAGE}.creator.director_run")
users = tempfile.mkdtemp(prefix="director-runs-")
alive = {"version": run_mod.VERSION, "chat": "abc", "state": "running", "error": None,
         "plan": {"version": 1}, "steps": [], "total": 0}
done = {**alive, "chat": "def", "state": "done"}
for user, record in (("default", alive), ("other", done)):
    route._write_run(os.path.join(users, user, route.RUN_FILE.format(chat=record["chat"])), record)
check("a run file is written whole, with nothing half-written left beside it",
      sorted(os.listdir(os.path.join(users, "default"))), ["continuity.director.abc.json"])
check("a server start stops the runs it finds running, in every user's folder, and only those",
      [os.path.basename(p) for p in route.restart_runs(users)], ["continuity.director.abc.json"])
check("...which come back stopped, never running",
      route._read_run(os.path.join(users, "default", "continuity.director.abc.json"))["state"], "stopped")
try:
    route._run_path(None, "../../etc")
except run_mod.RunError:
    pass
else:
    FAILURES.append("a chat id that walks out of the user folder was given a path")

check("a finished prompt lands with its outputs",
      route._outcome({"status": {"status_str": "success", "completed": True}, "outputs": {"n": {}}}, False),
      ("landed", {"n": {}}))
check("a failed one is said in the error's words",
      route._outcome({"status": {"status_str": "error", "messages": [
          ["execution_error", {"exception_message": "out of memory"}]]}}, False),
      ("failed", "out of memory"))
check("one interrupted by Stop is stopped, not failed",
      route._outcome({"status": {"status_str": "error", "messages": [["execution_interrupted", {}]]}}, True),
      ("stopped", None))
check("one cancelled from ComfyUI's own queue is said so",
      route._outcome({"status": {"status_str": "error", "messages": [["execution_interrupted", {}]]}}, False),
      ("failed", "cancelled"))

passed("the plan route plans with the room's backend, rail and cast")
