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

# The timeline has a prompt of its own, put in front of what comes from there,
# and a change of place within a conversation is written down with its tools.
reel = {"role": "system", "content": stagehand.system("reel")}
assert reel["content"].startswith("You are building a film on a timeline") and "You cannot render." in reel["content"]
with tempfile.TemporaryDirectory() as root:
    said = [{"role": "user", "content": "a chase, six shots"}]
    stagehand.turn("2026-reel", "m", said, [{"type": "function"}], 0, root=root, ask=ask, place="reel")
    assert asked[-1] == [reel, *said], "the timeline's prompt goes in front of the timeline's exchange"
    across = said + [{"role": "assistant", "content": "ok"}, {"role": "tool", "tool_call_id": "c", "content": "The blockout is open."}]
    stagehand.turn("2026-reel", "m", across, [], 2, root=root, ask=ask, place="blockout")
    assert asked[-1] == [system, *across], "and the bench's once the conversation is there"
    log = entries(root, "2026-reel")
    assert [(entry["kind"], entry.get("place")) for entry in log if entry["kind"] == "tools"] == [("tools", "reel"), ("tools", "blockout")], log
    assert refused(lambda: stagehand.turn("2026-reel", "m", said, [], 0, root=root, ask=ask, place="attic"), ValueError) == "bad place"
    assert stagehand.fenced_system([], "reel").startswith(reel["content"])
del asked[:]

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
    assert "on ComfyUI's queue" in refused(lambda: stagehand.turn("2026-c", "qwen", first, [], 0, backend="local", root=root, ask=ask))
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

# ---- the fenced form: tools in words, a reply read back into calls -------------------

TOOLS = [{"type": "function", "function": {"name": "add_objects", "description": "Put objects into the set.\n\nArgs:\n    objects (list): The objects.", "parameters": {}}},
         {"type": "function", "function": {"name": "see_scene", "description": "Read everything.", "parameters": {}}}]
text = stagehand.fenced_system(TOOLS)
assert text.startswith(system["content"] + "\n\nYou work by calling tools."), "the prompt goes first"
assert text.endswith("## add_objects\nPut objects into the set.\n\nArgs:\n    objects (list): The objects.\n\n## see_scene\nRead everything.")
assert '{"calls": [{"tool":' in text and '{"say":' in text

url = lambda name: "data:image/png;base64," + base64.b64encode(name.encode()).decode()
picture = lambda name: {"type": "image_url", "image_url": {"url": url(name)}}
talk = [
    {"role": "user", "content": [picture("brief"), {"type": "text", "text": "A kitchen like this."}]},
    {"role": "assistant", "content": "Building.", "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "add_objects", "arguments": '{"objects": [{"what": "table"}]}'}},
        {"id": "b", "type": "function", "function": {"name": "look_overview", "arguments": ""}}]},
    {"role": "tool", "tool_call_id": "a", "content": "Added #1 table"},
    {"role": "tool", "tool_call_id": "b", "content": [{"type": "text", "text": ""}, picture("set")]},
    {"role": "assistant", "content": "A kitchen with a table."},
    {"role": "user", "content": "Now a chair."},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "add_objects", "arguments": '{"objects": [{"what": "chair"}]}'}}]},
    {"role": "tool", "tool_call_id": "c", "content": [{"type": "text", "text": "Added #2 chair"}, picture("set2")]},
]
whole = stagehand.turns(talk)
assert [turn["role"] for turn in whole] == ["user", "assistant", "user", "user", "assistant", "user", "assistant", "user"]
assert whole[0] == {"role": "user", "text": "A kitchen like this.", "images": [url("brief")]}
assert whole[1]["text"] == 'Building.\n```json\n{"calls": [{"tool": "add_objects", "args": {"objects": [{"what": "table"}]}}, {"tool": "look_overview", "args": {}}]}\n```'
assert whole[2] == {"role": "user", "text": "add_objects answered:\nAdded #1 table", "images": []}, "each answer is a turn of its own"
assert whole[3] == {"role": "user", "text": "look_overview answered:", "images": [url("set")]}, "with its picture"
assert whole[4]["text"] == '```json\n{"say": "A kitchen with a table."}\n```'
assert whole[7]["images"] == [url("set2")]
assert stagehand.read(whole[1]["text"])["tool_calls"][0]["function"] == talk[1]["tool_calls"][0]["function"], "it reads back what it writes"

folded = stagehand.turns(talk, fold=True)
assert [turn["text"].split("\n")[0] for turn in folded] == [
    "A kitchen like this.", "```json", "Now a chair.", "```json", "add_objects answered:"], folded
assert folded[0]["images"] == [url("brief")], "a person's picture is never taken out"
assert folded[1]["text"] == whole[4]["text"] and folded[3:] == whole[6:], "the current message's calls stay whole"

sent = stagehand.as_messages("sys", whole)
assert sent[0] == {"role": "system", "content": "sys"} and sent[3] == {"role": "user", "content": "add_objects answered:\nAdded #1 table"}
assert sent[4]["content"] == [picture("set"), {"type": "text", "text": "look_overview answered:"}]

# One prompt of several turns, for the model in ComfyUI: each picture where its turn shows it.
prompt = pkg.prompting.chatml_turns("sys", [(turn["role"], turn["text"], len(turn["images"])) for turn in folded])
block = pkg.prompting.VISION_BLOCK
assert prompt.startswith("<|im_start|>system\nsys<|im_end|>\n<|im_start|>user\n" + block + "A kitchen like this.<|im_end|>\n<|im_start|>assistant\n```json")
assert prompt.count(block) == 2 and prompt.index(block, 60) > prompt.index("add_objects answered:") - len(block) - 30
assert prompt.endswith("<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"), "the next turn is begun, with no thinking and no prefill"
assert pkg.prompting.chatml_turns("sys", [("user", "go", 0)], think=True).endswith("<|im_start|>assistant\n")

# Replies, as models write them.
said = stagehand.read('```json\n{"say": "The kitchen is built."}\n```')
assert said == {"role": "assistant", "content": "The kitchen is built."}
several = stagehand.read('I will add a table and look.\n```json\n{"calls": [{"tool": "add_objects", "args": {"objects": [{"what": "table", "x": 0, "z": 2}]}},'
                         ' {"tool": "look_overview", "args": {}}, {"tool": "fly", "args": "up"}, {"name": "see_scene"}]}\n```', at=7)
assert several["content"] == "I will add a table and look."
assert [(call["id"], call["function"]["name"], call["function"]["arguments"]) for call in several["tool_calls"]] == [
    ("f7-0", "add_objects", '{"objects": [{"what": "table", "x": 0, "z": 2}]}'), ("f7-1", "look_overview", "{}"),
    ("f7-2", "fly", '"up"'), ("f7-3", "see_scene", "{}")], "a tool that is not one, or a wrong argument, is the tool's to refuse"
assert stagehand.read("Which room do you mean?") == {"role": "assistant", "content": "Which room do you mean?"}, "no object is a say"
assert stagehand.read("<think>a table, then {maybe} a chair</think>Which room?")["content"] == "Which room?"
opened = stagehand.read('Adding.\n```json\n{"calls": [{"tool": "add_objects", "args": {"objects": [{"what": "table", "name": "a {big} table"}]}}')
assert json.loads(opened["tool_calls"][0]["function"]["arguments"]) == {"objects": [{"what": "table", "name": "a {big} table"}]}, "an object left open is closed"
around = stagehand.read('Sure! Here is my plan.\n\n```json\n{"calls": [{"tool": "see_scene", "args": {}}]}\n```\nLet me know if that works.')
assert around["tool_calls"][0]["function"]["name"] == "see_scene" and around["content"] == "Sure! Here is my plan."
bare = stagehand.read('{"calls": [{"tool": "see_scene"}]}')
assert bare["content"] == "" and bare["tool_calls"][0]["function"]["arguments"] == "{}"
for bad in ("", '```json\n{"calls": []}\n```', '{"plan": "think"}', '{"calls": ["see_scene"]}', '{"say": ""}', '{"calls": [{"tool": "x"'[:-9] + "]]}"):
    refused(lambda: stagehand.read(bad), stagehand.Unreadable)

with tempfile.TemporaryDirectory() as root:
    replies, wrote = [], []

    def write(system_text, turns_):
        wrote.append((system_text, turns_))
        return replies.pop(0)

    # A model in ComfyUI: asked in words, folded, and answered as a server answers.
    replies[:] = ['Adding a lamp.\n```json\n{"calls": [{"tool": "add_objects", "args": {"objects": [{"what": "lamp"}]}}]}\n```']
    body = stagehand.turn("fenced-a", "qwen", talk, TOOLS, 0, backend="local", root=root, write=write)
    assert body["choices"][0]["message"]["tool_calls"][0]["id"] == f"f{len(talk)}-0"
    assert wrote[0] == (text, folded), "the tools are in the system text, and earlier messages are folded"
    log = entries(root, "fenced-a")
    assert (log[-1]["asked"], log[-1]["raw"], log[0]["backend"]) == ("fenced", body["raw"], "local")
    assert log[-1]["reply"]["message"] == body["choices"][0]["message"], "the raw reply is logged beside the message read out of it"

    # Re-asked once with the reason, then given up on.
    replies[:] = ['{"plan": "a lamp"}', '```json\n{"say": "Done."}\n```']
    wrote.clear()
    body = stagehand.turn("fenced-a", "qwen", talk, TOOLS, 0, backend="local", root=root, write=write)
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "Done."} and len(body["raw"]) == 2
    again = wrote[1][1]
    assert again[:-2] == folded and again[-2] == {"role": "assistant", "text": '{"plan": "a lamp"}', "images": []}
    assert again[-1]["text"].startswith('That cannot be used: the object has to hold "calls"'), again[-1]
    replies[:] = ["{", "{{"]
    assert "could not be read as calls, twice" in refused(lambda: stagehand.turn("fenced-a", "qwen", talk, TOOLS, 0, backend="local", root=root, write=write))
    assert not replies and entries(root, "fenced-a")[-1]["kind"] == "error"

    # A server asked the same way, for the bench: whole, and with no tools sent.
    got_tools = []

    def plain(model, conversation, tools, **_):
        got_tools.append((tools, conversation))
        return {"choices": [{"message": {"role": "assistant", "content": '```json\n{"say": "Yes."}\n```'}, "finish_reason": "stop"}]}

    body = stagehand.turn("fenced-b", "m", talk, TOOLS, 0, root=root, ask=plain, fenced=True)
    assert body["choices"][0]["message"]["content"] == "Yes." and got_tools[0][0] is None
    assert got_tools[0][1] == stagehand.as_messages(text, whole), "a server has a context setting of its own, and is not folded for"

    # A server that refuses tools is asked again in plain JSON, and says so once.
    calls = []

    def toolless(model, conversation, tools, **_):
        calls.append(tools)
        if tools is not None:
            raise remote.ServerError("the server answered 400: this model does not support tools", 400, "this model does not support tools")
        return plain(model, conversation, tools)

    body = stagehand.turn("fenced-c", "m", talk, TOOLS, 0, root=root, ask=toolless)
    assert calls == [TOOLS, None] and body["note"] == stagehand.NO_TOOLS and body["choices"][0]["message"]["content"] == "Yes."
    body = stagehand.turn("fenced-c", "m", talk, TOOLS, 0, root=root, ask=toolless)
    assert calls == [TOOLS, None, None] and "note" not in body, "said once, and remembered"

    def broken(model, conversation, tools, **_):
        raise remote.ServerError("the server answered 400: model not found", 400, "model not found")

    assert "model not found" in refused(lambda: stagehand.turn("fenced-d", "m", talk, TOOLS, 0, root=root, ask=broken))

# ---- the pictures that are sent --------------------------------------------------------

look = lambda n: {"role": "tool", "tool_call_id": f"l{n}", "content": [{"type": "text", "text": f"look {n}"}, picture(f"p{n}")]}
long_talk = [talk[0], *[look(n) for n in range(6)]]
assert stagehand.thinned(long_talk) is long_talk, "six are carried"
kept = lambda messages: [base64.b64decode(part["image_url"]["url"].split(",")[1]).decode() for message in messages[1:] for part in message["content"] if part["type"] == "image_url"]
seven = stagehand.thinned([*long_talk, look(6)])
assert kept(seven) == ["p3", "p4", "p5", "p6"], "the seventh takes three with it"
assert seven[1]["content"] == [{"type": "text", "text": "look 0"}, {"type": "text", "text": stagehand.EARLIER_PICTURE}]
assert seven[0] == talk[0] and long_talk[1]["content"][1] == picture("p0"), "the brief stays, and the conversation held is not touched"
assert kept(stagehand.thinned([*long_talk, look(6), look(7), look(8)])) == ["p3", "p4", "p5", "p6", "p7", "p8"], "so the front changes rarely"
assert kept(stagehand.thinned([*long_talk, *[look(n) for n in range(6, 10)]])) == ["p6", "p7", "p8", "p9"]

carried = stagehand.moved(talk)
assert [message["role"] for message in carried] == ["user", "assistant", "tool", "tool", "user", "assistant", "user", "assistant", "tool", "user"]
assert carried[3] == {"role": "tool", "tool_call_id": "b", "content": "(a picture follows)"}
assert carried[4]["content"][1:] == [picture("set")] and carried[9]["content"][1:] == [picture("set2")]
assert carried[8]["content"] == "Added #2 chair\n(a picture follows)"

with tempfile.TemporaryDirectory() as root:
    took = []

    def fussy(model, conversation, tools, **_):
        took.append(conversation)
        if any(message["role"] == "tool" and isinstance(message["content"], list) for message in conversation):
            raise remote.ServerError("the server answered 400: invalid content", 400, "Invalid type for 'messages[3].content'")
        return SAY

    assert stagehand.turn("moved-a", "m", talk, TOOLS, 0, root=root, ask=fussy) == SAY
    assert len(took) == 2 and took[1] == [system, *carried], "sent again with each picture in a user message"
    stagehand.turn("moved-a", "m", talk, TOOLS, 0, root=root, ask=fussy)
    assert len(took) == 3 and took[2] == [system, *carried], "and the session remembers"
    assert entries(root, "moved-a")[-1]["pictures"] == "in a user turn"

    def down(model, conversation, tools, **_):
        took.append(conversation)
        raise remote.ServerError(f"the server answered 400: bad request {len(took)}", 400, f"bad request {len(took)}")

    took.clear()
    assert refused(lambda: stagehand.turn("moved-b", "m", talk, TOOLS, 0, root=root, ask=down)).endswith("bad request 1"), "not the pictures: its first words are heard"
    assert len(took) == 2

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
