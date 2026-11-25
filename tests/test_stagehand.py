"""What the blockout agent's server half promises: the system prompt goes in
front and nothing else does, the log holds everything once with its pictures as
files, one exchange a session at a time, a Stop closes the connection that is
being waited on, and the model is dropped once when a message is over.

Runs standalone — `python tests/test_stagehand.py` — with no ComfyUI. The one
server it talks to is its own, on loopback.
"""

import base64
import http.server
import json
import os
import tempfile
import threading
import time

import layout

pkg = layout.load("prompting", "refine_remote", "stagehand")
stagehand, remote, RefineError = pkg.stagehand, pkg.refine_remote, pkg.prompting.RefineError

PNG = base64.b64encode(b"a picture").decode()
JPEG = base64.b64encode(b"a photograph").decode()
SAY = {"choices": [{"message": {"role": "assistant", "content": "yes"}, "finish_reason": "stop"}]}
CALL = {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
    {"id": "c", "type": "function", "function": {"name": "see_scene", "arguments": "{}"}}]},
    "finish_reason": "tool_calls"}]}
asked, dropped = [], []
remote.unload = dropped.append


def ask(model, messages, tools, **_):
    asked.append(messages)
    return SAY


def call(model, messages, tools, **_):
    return CALL


def refuse(model, messages, tools, **_):
    raise RuntimeError("down")


def refused(work, *expected):
    try:
        work()
    except expected or RefineError as exc:
        return str(exc)
    raise AssertionError("it was taken")


def entries(root, session):
    with open(os.path.join(root, session, "log.jsonl"), encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


system = {"role": "system", "content": stagehand.system()}
assert system["content"].startswith("You are staging a film in a blockout bench")
assert "You cannot render." in system["content"]

# ---- the prompt, and the log ------------------------------------------------------

with tempfile.TemporaryDirectory() as root:
    first = [{"role": "user", "content": [
        {"type": "text", "text": "a street like this"},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{JPEG}"}}]}]
    stagehand.turn("2026-a", "m", first, [{"type": "function"}], 0, root=root, ask=ask)
    assert asked == [[system, *first]], "only the prompt is put in front of what the user said"
    more = first + [{"role": "assistant", "content": "yes"}, {"role": "tool", "tool_call_id": "c", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}]}]
    stagehand.turn("2026-a", "m", more, [], 2, root=root, ask=ask)
    assert asked[1] == [system, *more], "the prompt goes first and once, and the log's copy is not what is sent"
    assert refused(lambda: stagehand.turn("2026-a", "m", more, [], 3, root=root, ask=refuse), RuntimeError) == "down"
    log = entries(root, "2026-a")
    assert [entry["kind"] for entry in log] == ["tools", "message", "reply", "message", "reply", "error"], log
    assert log[0]["system"] == system["content"] and log[0]["tools"] == [{"type": "function"}]
    assert (log[0]["backend"], log[0]["model"], log[2]["asked"]) == ("remote", "m", "tools")
    folder = os.path.join(root, "2026-a")
    for entry, at, name, data in ((log[1], 1, "0-1.jpg", b"a photograph"), (log[3], 0, "2-0.png", b"a picture")):
        assert entry["message"]["content"][at] == {"type": "image", "file": name}, entry
        with open(os.path.join(folder, name), "rb") as handle:
            assert handle.read() == data
    assert "base64" not in json.dumps(log), "a picture is a file, not a line of the log"

    # What a failed exchange wrote is not written again by the next, whatever
    # the browser thinks is new.
    stagehand.turn("2026-b", "m", first, [], 0, root=root, ask=call)
    refused(lambda: stagehand.turn("2026-b", "m", first + more[1:], [], 2, root=root, ask=refuse), RuntimeError)
    stagehand.turn("2026-b", "m", first + more[1:], [], 2, root=root, ask=ask)
    assert [entry["kind"] for entry in entries(root, "2026-b")] == ["tools", "message", "reply", "message", "error", "reply"]

    for bad in ("../up", "a/b", "", "UP"):
        refused(lambda: stagehand.turn(bad, "m", first, [], 0, root=root, ask=ask), ValueError)
    assert sorted(os.listdir(root)) == ["2026-a", "2026-b"]

    # ---- what is refused ----------------------------------------------------------

    before = len(asked)
    assert "No model chosen" in refused(lambda: stagehand.turn("2026-c", "  ", first, [], 0, root=root, ask=ask))
    assert "No text encoder chosen" in refused(lambda: stagehand.turn("2026-c", "", first, [], 0, backend="local", root=root, ask=ask))
    assert "cannot ask a model in ComfyUI yet" in refused(lambda: stagehand.turn("2026-c", "qwen", first, [], 0, backend="local", root=root, ask=ask))
    assert len(asked) == before and not os.path.exists(os.path.join(root, "2026-c")), "a refused request asks and logs nothing"

    cut = {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": CALL["choices"][0]["message"]["tool_calls"]},
                        "finish_reason": "length"}]}
    assert "cut off" in refused(lambda: stagehand.turn("2026-d", "m", first, [], 0, root=root, ask=lambda *a, **k: cut))
    assert entries(root, "2026-d")[-1]["kind"] == "reply", "the log keeps the reply that was cut"

    # ---- one exchange a session at a time -------------------------------------------

    entered, leave = threading.Event(), threading.Event()

    def slow(model, messages, tools, **_):
        entered.set()
        leave.wait(5)
        return SAY

    one = threading.Thread(target=stagehand.turn, args=("2026-e", "m", first, [], 0), kwargs={"root": root, "ask": slow})
    one.start()
    entered.wait(5)
    assert "still working" in refused(lambda: stagehand.turn("2026-e", "m", first, [], 0, root=root, ask=ask))
    stagehand.turn("2026-f", "m", first, [], 0, root=root, ask=ask)   # another conversation is not held up
    leave.set()
    one.join()
    stagehand.turn("2026-e", "m", first, [], 0, root=root, ask=ask)

# ---- dropping the model -------------------------------------------------------------

with tempfile.TemporaryDirectory() as root:
    said = [{"role": "user", "content": "go"}]
    assert not dropped, "nothing is dropped that was not asked to be"
    stagehand.turn("eject-a", "m", said, [], 0, eject=True, root=root, ask=call)
    assert not dropped, "the model stays between the exchanges of a message"
    stagehand.turn("eject-a", "m", said, [], 0, eject=True, root=root, ask=ask)
    assert dropped == ["m"], "and goes with the reply that calls nothing"
    assert stagehand.stop("eject-a") is False and dropped == ["m"], "once"
    stagehand.turn("eject-a", "m", said, [], 0, eject=True, root=root, ask=call)
    assert stagehand.stop("eject-a") is False and dropped == ["m", "m"], "a Stop between two exchanges drops it"
    assert stagehand.stop("eject-a") is False and stagehand.stop("nobody") is False and len(dropped) == 2
    refused(lambda: stagehand.turn("eject-a", "m", said, [], 0, eject=True, root=root, ask=refuse), RuntimeError)
    assert len(dropped) == 3, "a failure ends the message too"
    stagehand.turn("eject-b", "m", said, [], 0, root=root, ask=call)
    assert stagehand.stop("eject-b") is False and len(dropped) == 3

# ---- the sweep --------------------------------------------------------------------

with tempfile.TemporaryDirectory() as root:
    os.makedirs(os.path.join(root, "not a session"))
    for at in range(stagehand.KEPT + 3):
        name = f"sweep-{at:02d}"
        stagehand.turn(name, "m", [{"role": "user", "content": "go"}], [], 0, root=root, ask=ask)
        os.utime(os.path.join(root, name, "log.jsonl"), (at, at))
    stagehand.turn("sweep-new", "m", [{"role": "user", "content": "go"}], [], 0, root=root, ask=ask)
    kept = sorted(os.listdir(root))
    assert len(kept) == stagehand.KEPT + 1 and "not a session" in kept, kept
    assert "sweep-new" in kept and "sweep-04" in kept and "sweep-03" not in kept, kept

# ---- a server, and the Stop under it -----------------------------------------------

got, hang, gone = [], threading.Event(), threading.Event()


class Server(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["content-length"])))
        got.append(payload)
        if payload["model"] == "slow":
            hang.set()
            # What a server does that is still generating: nothing, until the
            # client is gone.
            self.connection.settimeout(10)
            try:
                if not self.connection.recv(1):
                    gone.set()
            except OSError:
                pass
            return
        refuses = payload["model"] == "strict" and "reasoning_effort" in payload
        body = {"error": {"message": "Unsupported parameter: 'reasoning_effort'"}} if refuses else SAY
        raw = json.dumps(body).encode()
        self.send_response(400 if refuses else 200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Server)
server.daemon_threads = True
threading.Thread(target=server.serve_forever, daemon=True).start()
remote._read = lambda: {"url": f"http://127.0.0.1:{server.server_port}/v1", "key": ""}

talk = [{"role": "user", "content": "go"}]
assert remote.converse("m", talk, [{"type": "function"}], reasoning=False) == SAY
assert got[-1] == {"model": "m", "messages": talk, "tools": [{"type": "function"}], "stream": False,
                   "reasoning_effort": "none"}, "nothing is sent that the settings do not ask for"
remote.converse("m", talk, [], reasoning=True)
assert "reasoning_effort" not in got[-1], "thinking on leaves the server's default"
remote.converse("strict", talk, [], reasoning=False)
assert "reasoning_effort" in got[-2] and "reasoning_effort" not in got[-1], "a server that refuses the word is asked without it"

with tempfile.TemporaryDirectory() as root:
    stagehand.turn("wire-a", "m", talk, [], 0, reasoning=False, root=root)
    assert got[-1]["messages"] == [system, *talk]

    ended = []
    count = len(dropped)

    def run():
        ended.append(refused(lambda: stagehand.turn("wire-a", "slow", talk, [], 0, eject=True, reasoning=False, root=root),
                             stagehand.Stopped))

    worker = threading.Thread(target=run)
    worker.start()
    assert hang.wait(5), "the request never reached the server"
    started = time.time()
    assert stagehand.stop("wire-a") is True
    worker.join(5)
    assert ended == ["Stopped."] and time.time() - started < 3, "a Stop ends the wait at once"
    assert gone.wait(5), "the server was not told the client had gone"
    assert entries(root, "wire-a")[-1]["kind"] == "stopped"
    assert dropped[count:] == ["slow"], "a stopped message drops the model once"
    stagehand.turn("wire-a", "m", talk, [], 0, reasoning=False, root=root)   # and the conversation can go on

    # A Stop that lands before the connection is open still closes it.
    held = remote.Held()
    held.close()
    hang.clear()
    refused(lambda: remote.converse("slow", talk, [], reasoning=False, held=held))
    assert held.closed

server.shutdown()
