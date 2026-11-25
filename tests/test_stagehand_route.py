"""The doors of `/continuity/stagehand`: an exchange is answered with an id and
its reply follows on the socket, what cannot be asked is refused inside the
request, and Stop takes a session.

    python3 tests/test_stagehand_route.py

`routes/stagehand.py` is imported over a stub server with the socket's half
(`jobs.answer_later`) and the agent's (`stagehand.turn`) replaced: what is
checked is what the route hands each of them.
"""

import asyncio
import json
import sys
from types import ModuleType

import layout
from harness import check, passed

later, turned, stopped, queued, kinds = [], [], [], [], {}


class _Jobs:
    class JobError(ValueError):
        pass

    @staticmethod
    def register(kind, run):
        kinds[kind] = run

    @staticmethod
    async def submit(kind, body, client_id=None):
        queued.append((kind, body, client_id))
        return "prompt-9"

    @staticmethod
    def answer_later(work, client_id=None, expected=()):
        later.append((client_id, expected))
        work()
        return "answer-3"


PACKAGE = "stagehand_route_test"
handlers = layout.stub_server()
pkg = layout.load("prompting", "refine_remote", "stagehand", package=PACKAGE)
sys.modules[f"{PACKAGE}.jobs"] = _Jobs
pkg.jobs = _Jobs
# The model in ComfyUI and its devices, stood in for: torch is not here.
wrote = []
local = ModuleType("refine_local")
local.converse = lambda name, system, turns, images, **options: wrote.append((name, system, turns, images, options)) or '```json\n{"say": "Done."}\n```'
local.to_tensor = lambda image: image.size
models = ModuleType("models")
models.device_options = lambda: ["cuda:1"]
for name, stub in (("refine_local", local), ("models", models)):
    sys.modules[f"{PACKAGE}.{name}"] = stub
    setattr(pkg, name, stub)
guard = ModuleType("guard")
guard.same_origin = lambda handler: handler   # test_guard.py holds the real one
sys.modules[f"{PACKAGE}.guard"] = guard
layout.load("stagehand_route", package=PACKAGE)
stagehand = pkg.stagehand
real_turn = stagehand.turn
stagehand.turn = lambda *args, **options: turned.append((args, options))
stagehand.stop = lambda session: stopped.append(session) or True


class Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        if self.body is None:
            raise json.JSONDecodeError("no", "", 0)
        return self.body


def post(path, body):
    response = asyncio.run(handlers[path](Request(body)))
    return response.status, json.loads(response.text)


said = [{"role": "user", "content": "a street"}]
body = {"session": "2026-a", "backend": "remote", "model": "big", "device": "", "eject": True,
        "messages": said, "tools": [], "seen": 0, "client_id": "tab"}
check("an exchange is answered with an id", post("/continuity/stagehand", body), (200, {"answer_id": "answer-3"}))
check("addressed to the tab that asked", later[0][0], "tab")
check("with a refusal said as a sentence", pkg.prompting.RefineError in later[0][1], True)
check("and the agent given the request", turned,
      [(("2026-a", "big", said, [], 0), {"backend": "remote", "eject": True})])

for label, change, said_as in (
        ("no model", {"model": ""}, "No model chosen"),
        ("no text encoder", {"model": "", "backend": "local"}, "No text encoder chosen"),
        ("a bad session", {"session": "../up"}, "bad session id"),
        ("no messages", {"messages": None}, "expected a JSON body")):
    status, answer = post("/continuity/stagehand", {**body, **change})
    check(f"{label} is refused inside the request", (status, said_as in answer["error"]), (400, True))
check("no body is refused", post("/continuity/stagehand", None)[0], 400)
check("and none of those was asked", len(turned), 1)

# A model in ComfyUI is a job on the queue, and the job asks it in words.
status, answer = post("/continuity/stagehand", {**body, "backend": "local", "model": "qwen35_27b", "device": "cuda:1"})
check("a model in ComfyUI is queued", (status, answer), (200, {"prompt_id": "prompt-9"}))
check("under its kind, addressed to the tab", [(kind, client) for kind, _, client in queued], [("stagehand", "tab")])
check("a backend nobody named is the one in ComfyUI",
      post("/continuity/stagehand", {**body, "backend": "elsewhere", "model": "qwen35_27b"})[1], {"prompt_id": "prompt-9"})
check("and neither was asked inside the request", len(turned), 1)

import base64  # noqa: E402
import io  # noqa: E402
import tempfile  # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None
stagehand.turn = real_turn
with tempfile.TemporaryDirectory() as root:
    stagehand.log_root = lambda: root
    job = queued[0][1]
    if Image is not None:
        raw = io.BytesIO()
        Image.new("RGB", (8, 4)).save(raw, "PNG")
        job = {**job, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(raw.getvalue()).decode()}},
            {"type": "text", "text": "a street like this"}]}]}
    reply = kinds["stagehand"](job)
    check("the job answers as a server answers", reply["choices"][0]["message"], {"role": "assistant", "content": "Done."})
    name, system, turns, images, options = wrote[0]
    check("on the selected text encoder", name, "qwen35_27b")
    check("with the prompt in front", system.startswith(stagehand.system()), True)
    check("the conversation as turns", turns, [("user", "a street like this" if Image else "a street", 1 if Image else 0)])
    check("its pictures as tensors, in order", images, [(8, 4)] if Image else [])
    check("on the device, cold, with a budget of its own",
          options, {"temperature": 0.3, "seed": -1, "max_tokens": stagehand.FENCED_TOKENS, "device": "cuda:1"})
    try:
        kinds["stagehand"]({**job, "device": "cuda:7", "session": "2026-b"})
        check("a device that is gone is refused", "taken", "refused")
    except _Jobs.JobError as problem:
        check("a device that is gone is refused in the chat's words", str(problem),
              "the selected local LLM device 'cuda:7' is no longer available")
stagehand.turn = lambda *args, **options: turned.append((args, options))

check("Stop takes the session", post("/continuity/stagehand/stop", {"session": "2026-a"}), (200, {"stopped": True}))
check("and hands it on", stopped, ["2026-a"])
check("Stop with no session is refused", post("/continuity/stagehand/stop", {})[0], 400)

passed("the stagehand's doors answer as a chat turn's do")
