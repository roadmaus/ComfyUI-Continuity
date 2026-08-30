"""The queue this pack's work goes on, and what still stays off it.

    python tests/test_jobs.py

Runs standalone: no torch, no ComfyUI, no GPU. `server` is a stub holding a fake
prompt queue with the two attributes `jobs.busy` reads, which is all this needs
— what is under test is the plumbing, not the work.

Three things are worth pinning here, and each of them was a decision rather than
an accident.

**A job is a real prompt.** `submit` builds a one-node prompt, validates it and
puts it on ComfyUI's own queue, so the tuple it pushes has to be the shape
`prompt_worker` pops. A body that arrived as anything but JSON-able would fail
at the far end of the queue, minutes later, in a traceback nobody can act on.

**`busy` means both halves.** A job that is merely *pending* is one a preview
would jump ahead of, and one that is *running* is the GPU in use. Reading only
`currently_running` would have let a slider drag start in front of three queued
renders.

**The remote refiner is not a job.** It spends somebody else's GPU. If it ever
drifts onto the queue it will start waiting for renders it has no reason to wait
for, and nothing else in the suite would notice.
"""

import asyncio
import importlib.util
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check, passed  # noqa: E402


class FakeQueue:
    """The two fields `jobs.busy` reads, and a record of what was put on it."""

    def __init__(self):
        self.mutex = _Mutex()
        self.queue = []
        self.currently_running = {}

    def put(self, item):
        self.queue.append(item)


class _Mutex:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def load():
    """`jobs`, with the ComfyUI server it talks to replaced by a fake."""
    server = types.ModuleType("server")
    queue = FakeQueue()
    server.PromptServer = types.SimpleNamespace(
        instance=types.SimpleNamespace(prompt_queue=queue, number=0))
    sys.modules["server"] = server

    web = types.ModuleType("aiohttp.web")

    class Response:
        """Enough of `web.json_response` to read a status and a body off it."""

        def __init__(self, body, status=200):
            self.body, self.status = body, status

    web.json_response = lambda body, status=200: Response(body, status)
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = web
    sys.modules.setdefault("aiohttp", aiohttp)
    sys.modules["aiohttp.web"] = web

    spec = importlib.util.spec_from_file_location("mmcjobs.jobs", layout.py("jobs"))
    module = importlib.util.module_from_spec(spec)
    package = types.ModuleType("mmcjobs")
    package.__path__ = [layout.PY_ROOT]
    sys.modules["mmcjobs"] = package
    sys.modules["mmcjobs.jobs"] = module
    spec.loader.exec_module(module)
    return module, queue


jobs, queue = load()

# ---- the table --------------------------------------------------------------
#
# A kind is registered by whichever module owns that work, so the node stays a
# dispatcher and adding a job is not an edit to it.

check("an unregistered kind has no runner", jobs.runner("nothing"), None)
jobs.register("spell", lambda body: {"said": body["word"]})
check("a registered one does", jobs.runner("spell")({"word": "hello"}), {"said": "hello"})

# ---- busy -------------------------------------------------------------------

check("an empty queue is not busy", jobs.busy(), False)
queue.queue.append(("pending",))
check("one waiting is busy", jobs.busy(), True)
queue.queue.clear()
queue.currently_running[0] = ("running",)
check("and so is one on the sampler", jobs.busy(), True)

# The 409 the gated routes answer with. The frontend reads the status, not the
# sentence — which is why the status is what this checks.
refusal = jobs.refuse_if_busy()
check("a busy queue refuses a preview", refusal.status, 409)
check("and says so in a field, not only in prose", refusal.body["busy"], True)
queue.currently_running.clear()
check("an idle one lets it through", jobs.refuse_if_busy(), None)

# ---- submitting -------------------------------------------------------------
#
# `validate_prompt` is core's and is stubbed: what is under test is the tuple
# this pushes and the body it carries, not core's validator.


async def _validates(prompt_id, prompt, targets):
    _validates.saw = (prompt_id, prompt, targets)
    return (True, None, ["1"], {})


execution = types.ModuleType("execution")
execution.validate_prompt = _validates
sys.modules["execution"] = execution

body = {"filename": "clip.mp4", "op": "restore",
        "params": {"scale": 2}, "trim": [1.0, 4.0], "keep_sound": True, "at": None}
prompt_id = asyncio.run(jobs.submit("upscale", body, "tab-7"))

check("one job is one item on the queue", len(queue.queue), 1)
number, queued_id, prompt, extra, outputs, sensitive = queue.queue[0]
check("queued under the id the caller was given", queued_id, prompt_id)
check("as one node", list(prompt), ["1"])
check("and it is ours", prompt["1"]["class_type"], jobs.NODE_ID)
# The body rides as a string, so anything in it that will not serialize fails
# here rather than inside `prompt_worker` some minutes later — and it rides
# *nested*, which is the whole of the next case.
envelope = json.loads(prompt["1"]["inputs"]["job"])
check("the body rides whole", envelope["body"], body)
check("under the kind that says who runs it", envelope["kind"], "upscale")
# Which tab hears `executed`. Without this the answer goes to whoever queued
# last, which on a second browser tab is somebody else.
check("addressed to the tab that pressed", extra["client_id"], "tab-7")
check("the outputs are the validator's", outputs, ["1"])
check("validated before it was queued", _validates.saw[0], prompt_id)

# A press with no tab named is still a job — a client_id is how the answer is
# addressed, not permission to run.
asyncio.run(jobs.submit("control", {}, None))
check("an unaddressed job still queues", len(queue.queue), 2)
check("and carries no client id", queue.queue[1][3], {})

# Two presses are two items, and the second is behind the first. This is the
# whole point: it used to be two threads on one GPU.
check("presses do not merge", queue.queue[0][1] != queue.queue[1][1], True)
check("and they are ordered", queue.queue[0][0] < queue.queue[1][0], True)


# The envelope and the body do not share a namespace. A refine request has a
# `kind` of its own — which shot, or the whole timeline — and when the two were
# spread into one dict the request's won: the queue got a job of kind "segment",
# and the node raised on a kind nothing in this pack does. It reached a real
# server before anything here noticed, which is why it is pinned.
execution.validate_prompt = _validates
asyncio.run(jobs.submit("refine", {"kind": "segment", "data": {}}, None))
sent = json.loads(queue.queue[-1][2]["1"]["inputs"]["job"])
check("the job's kind is the caller's", sent["kind"], "refine")
check("and the body keeps its own", sent["body"]["kind"], "segment")

# A validator that refuses is a bug in this pack rather than something the
# person pressing can act on, and it must not reach the queue.
async def _refuses(prompt_id, prompt, targets):
    return (False, {"message": "no such node"}, [], {})


execution.validate_prompt = _refuses
before = len(queue.queue)
try:
    asyncio.run(jobs.submit("control", {}, None))
    FAILURES.append("a prompt that would not validate was queued anyway")
except jobs.JobError:
    pass
check("nothing reached the queue", len(queue.queue), before)

# ---- what stays off the queue -----------------------------------------------
#
# Read off the routes rather than asserted about them in prose. The remote
# refiner answers inside its request and the previews are gated, and both of
# those are the kind of decision a later edit undoes without meaning to.

refine_source = open(layout.py("refine_routes"), encoding="utf-8").read()
check("the remote refiner answers in the request",
      'if remote:' in refine_source and 'return web.json_response({"result": result})' in refine_source,
      True)
check("and the local one is queued",
      'jobs.submit("refine"' in refine_source, True)

for module, route in (("routes/control", "preview_frame"),
                      ("routes/upscale", "preview_tile"),
                      ("server_routes", "cut_plate_panel")):
    source = open(os.path.join(layout.PY_ROOT, f"{module}.py"), encoding="utf-8").read()
    body = source[source.index(f"def {route}("):]
    check(f"{route} is gated", "jobs.refuse_if_busy()" in body[:900], True)

passed("jobs queue, gate what should be gated, and leave the cloud alone")
