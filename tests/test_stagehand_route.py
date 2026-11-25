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

later, turned, stopped = [], [], []


class _Jobs:
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
guard = ModuleType("guard")
guard.same_origin = lambda handler: handler   # test_guard.py holds the real one
sys.modules[f"{PACKAGE}.guard"] = guard
layout.load("stagehand_route", package=PACKAGE)
stagehand = pkg.stagehand
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
        ("a backend nobody named is the one in ComfyUI", {"backend": "elsewhere"}, "cannot ask a model in ComfyUI yet"),
        ("a bad session", {"session": "../up"}, "bad session id"),
        ("no messages", {"messages": None}, "expected a JSON body")):
    status, answer = post("/continuity/stagehand", {**body, **change})
    check(f"{label} is refused inside the request", (status, said_as in answer["error"]), (400, True))
check("no body is refused", post("/continuity/stagehand", None)[0], 400)
check("and none of those was asked", len(turned), 1)

check("Stop takes the session", post("/continuity/stagehand/stop", {"session": "2026-a"}), (200, {"stopped": True}))
check("and hands it on", stopped, ["2026-a"])
check("Stop with no session is refused", post("/continuity/stagehand/stop", {})[0], 400)

passed("the stagehand's doors answer as a chat turn's do")
