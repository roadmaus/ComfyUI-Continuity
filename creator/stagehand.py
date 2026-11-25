"""Stagehand, server side: put the prompt in front, pass an exchange on, and
write it down.

The conversation and its tools live in the browser (`web/creator/stagehand.js`),
where the piece and the renderer are. What is left here is what a browser must
not do: hold the server's key, and keep a log. There is a prompt for each place
it works in, a file each: `prompts/stagehand/system.txt` for the blockout bench
and `reel.txt` for the timeline. The one of the place an exchange comes from
goes in front of it as it is.

**Two ways of asking.** A server is asked with native tool calls: the
conversation goes as the browser holds it, with the tools as `tools`. A model
in ComfyUI has no tool calling, and neither has every server, so there is the
fenced form, the chat's own bargain: the tools are written into the system
text, the conversation is written as turns, and the reply is a line of plan and
one JSON object naming the calls, read back here into the message a server
would have sent. The browser cannot tell which way a reply was asked for.

**What is sent is not always what is held.** The browser sends the whole
conversation every time and the log keeps all of it. Of the pictures the tools
made only the newest few go to the model (`thinned`), a server that will not
take a picture in a tool's answer is sent them in a user turn instead
(`moved`), and a model in ComfyUI, which reserves memory for the whole prompt,
is not sent the calls of messages that are over (`turns`, folded).

No ComfyUI at module scope: `tests/test_stagehand.py` runs all of this with a
model that is a function.
"""

import base64
import json
import os
import re
import shutil
import threading
import time

from . import refine_remote
from .families import refine

SESSION = re.compile(r"[a-z0-9-]{4,64}")

# How many conversations the log keeps. A session is a folder of pictures, and
# nobody reads the fortieth one back.
KEPT = 20

# How many of the pictures the tools made a request carries, and how many go
# at a time when there are more: in steps, so the front of the conversation
# changes rarely and a server's cache of it keeps holding. A first guess.
PICTURES_KEPT = 6
PICTURES_DROPPED = 3
EARLIER_PICTURE = "(an earlier picture of the set)"

# The reply budget of a model in ComfyUI, which reserves memory for the prompt
# plus this and so cannot be left open: sized for a list of calls. Its
# temperature is the chat's cold default. Neither is measured yet.
FENCED_TOKENS = 4096
FENCED_TEMPERATURE = 0.3

NO_TOOLS = "This server does not call tools; Stagehand is asking in plain JSON instead."

_PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "stagehand")
# Where it works, and the prompt of each.
PLACES = {"blockout": "system.txt", "reel": "reel.txt"}
_PICTURE = re.compile(r"data:image/(png|jpeg|webp);base64,")
_EXTENSIONS = {"png": "png", "jpeg": "jpg", "webp": "webp"}
_read = {}


class Stopped(refine.RefineError):
    """The person pressed Stop under an exchange."""


class _Session:
    def __init__(self):
        self.held = None     # the connection of the exchange that is out, if one is
        self.logged = 0      # how many of the browser's messages the log holds
        self.warm = ""       # the model a server still holds for this conversation
        self.fenced = False  # the server refused tools, and is asked in plain JSON
        self.moved = False   # the server refused a picture in a tool's answer
        self.place = ""      # where the last exchange came from


_SESSIONS = {}
_LOCK = threading.Lock()


def system(place="blockout"):
    """The system prompt of a place, read once and held."""
    if place not in _read:
        with open(os.path.join(_PROMPTS, PLACES[place]), "r", encoding="utf-8") as handle:
            _read[place] = handle.read().strip()
    return _read[place]


def fenced_prompt():
    """How the fenced form is asked for, read once and held."""
    if "fenced" not in _read:
        with open(os.path.join(_PROMPTS, "fenced.txt"), "r", encoding="utf-8") as handle:
            _read["fenced"] = handle.read().strip()
    return _read["fenced"]


def log_root():
    import folder_paths

    return os.path.join(folder_paths.get_user_directory(), "continuity", "stagehand")


def refusal(backend, model):
    """Why this backend and model cannot be asked, in the chat's words, or ""."""
    if backend != "remote":
        if not str(model or "").strip():
            return ("No text encoder chosen. Put a Qwen3-VL or Qwen3.5 text encoder in "
                    "models/text_encoders and pick it in the refiner's settings.")
        return ""
    if not str(model or "").strip():
        return "No model chosen. Pick one of the server's models in the refiner's settings."
    return ""


def _readable(message, folder, stem):
    """A message as the log keeps it: its pictures as files beside it."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    parts = []
    for at, part in enumerate(content):
        url = (part.get("image_url") or {}).get("url", "")
        kind = _PICTURE.match(url)
        if kind:
            name = f"{stem}-{at}.{_EXTENSIONS[kind.group(1)]}"
            with open(os.path.join(folder, name), "wb") as handle:
                handle.write(base64.b64decode(url[kind.end():]))
            part = {"type": "image", "file": name}
        parts.append(part)
    return {**message, "content": parts}


def _sweep(root):
    """Keep the newest `KEPT` sessions' folders. One with an exchange out stays."""
    def touched(entry):
        try:
            return os.stat(os.path.join(entry.path, "log.jsonl")).st_mtime
        except OSError:
            return entry.stat().st_mtime

    with os.scandir(root) as entries:
        folders = sorted((entry for entry in entries if entry.is_dir() and SESSION.fullmatch(entry.name)),
                         key=touched, reverse=True)
    for entry in folders[KEPT:]:
        with _LOCK:
            if getattr(_SESSIONS.get(entry.name), "held", None) is not None:
                continue
            _SESSIONS.pop(entry.name, None)
        shutil.rmtree(entry.path, ignore_errors=True)


def turn(session, model, messages, tools, seen, backend="remote", eject=False, reasoning=None,
         root=None, ask=None, write=None, fenced=False, place="blockout"):
    """One exchange -> the reply, as a chat-completions server gives one.

    `ask(model, conversation, tools, reasoning=, held=)` is a server asked with
    tool calls, and `write(system, turns)` a model that can only write: the one
    in ComfyUI, handed in by the route, which is where torch is. With neither
    given the refiner's server is asked. `fenced` asks a server the way a model
    in ComfyUI is asked, for the bench.

    `messages` is the conversation as the browser holds it; the system prompt
    is put in front of it here, every time and nowhere else. `messages[seen:]`
    are new to the log, unless the log knows better: after an exchange that
    failed or was stopped the browser has not heard what was written.

    `place` is where the exchange comes from, "blockout" or "reel": whose
    prompt goes in front. It can change within a conversation, and the tools
    the browser sends change with it.

    `eject` asks the server to drop the model when the message is over: on the
    reply that calls no tool, and on any failure. Between the exchanges of one
    message it stays loaded, and `stop` drops it if the message ends there.
    """
    if not SESSION.fullmatch(session):
        raise ValueError("bad session id")
    if place not in PLACES:
        raise ValueError("bad place")
    refused = refusal(backend, model)
    if refused:
        raise refine.RefineError(refused)
    held = refine_remote.Held()
    with _LOCK:
        state = _SESSIONS.setdefault(session, _Session())
        if state.held is not None:
            raise refine.RefineError("Stagehand is still working on this conversation.")
        state.held = held
    over = True
    try:
        if backend != "remote" and write is None:
            raise refine.RefineError("a model in ComfyUI is asked on ComfyUI's queue")
        body = _exchange(state, session, model, messages, tools, seen, backend, reasoning,
                         root or log_root(), ask or refine_remote.converse, held, write, fenced, place)
        over = not body["choices"][0]["message"].get("tool_calls")
        return body
    finally:
        with _LOCK:
            state.held = None
            state.warm = model if eject and not over else ""
        if eject and over:
            refine_remote.unload(model)


def _exchange(state, session, model, messages, tools, seen, backend, reasoning, root, ask, held, write, fenced, place):
    folder = os.path.join(root, session)
    new = not os.path.isdir(folder)
    os.makedirs(folder, exist_ok=True)
    if new:
        _sweep(root)
    with open(os.path.join(folder, "log.jsonl"), "a", encoding="utf-8") as log:
        def write_log(kind, **entry):
            log.write(json.dumps({"at": time.time(), "kind": kind, **entry}, ensure_ascii=False) + "\n")
            log.flush()

        start = max(int(seen), state.logged)
        # Again when the place changed: the prompt and the tools did with it.
        if not start or state.place != place:
            write_log("tools", backend=backend, model=model, place=place, system=system(place), tools=tools)
        state.place = place
        for at in range(start, len(messages)):
            write_log("message", message=_readable(messages[at], folder, str(at)))
        state.logged = len(messages)
        started = time.time()
        sent = thinned(messages)
        local = backend != "remote"
        note = ""

        def written(system_text, turns_):
            """A server asked to write, where it is not a model in ComfyUI that is."""
            if write is not None:
                return write(system_text, turns_)
            return refine_remote._content(ask(model, as_messages(system_text, turns_), None,
                                              reasoning=reasoning, held=held))[0]

        try:
            body = None
            if not (local or fenced or state.fenced):
                try:
                    body = _native(state, ask, model, sent, tools, reasoning, held, place)
                except refine_remote.ServerError as exc:
                    if not _refuses_tools(exc):
                        raise
                    # Said once, and remembered for the conversation.
                    state.fenced, note = True, NO_TOOLS
            if body is None:
                body = _fenced(written, sent, tools, local, place)
        except Exception as exc:
            if held.closed:
                write_log("stopped", seconds=time.time() - started)
                raise Stopped("Stopped.") from None
            write_log("error", error=str(exc), seconds=time.time() - started)
            raise
        choice = body["choices"][0]
        write_log("reply", asked="fenced" if "raw" in body else "tools", reply=choice, usage=body.get("usage"),
                  timings=body.get("timings"), seconds=time.time() - started,
                  **({"raw": body["raw"]} if "raw" in body else {}),
                  **({"pictures": "in a user turn"} if state.moved else {}))
        if held.closed:
            raise Stopped("Stopped.")
        if choice.get("finish_reason") == "length":
            # In the log, and not in the conversation: half a call is no call.
            raise refine.RefineError(
                f"The reply of '{model}' was cut off: it ran into the server's own limit "
                f"on the length of a reply.")
        if note:
            body = {**body, "note": note}
        # The browser puts the reply after what it sent.
        state.logged = len(messages) + 1
    return body


# ---- asking with tool calls ---------------------------------------------------------


def _refuses_tools(exc):
    """Whether a server's refusal is of tool calling itself: a runtime or a
    model without it says so by name."""
    return exc.code in (400, 404, 422, 501) and "tool" in str(exc.detail).lower() and "image" not in str(exc.detail).lower()


def _native(state, ask, model, sent, tools, reasoning, held, place):
    """The conversation as it is, with the tools as `tools`.

    A server that will not take a picture in a tool's answer refuses the whole
    request. It is asked once more with each picture moved into a user message
    straight after the answers, and the session remembers to send them so.
    """
    conversation = [{"role": "system", "content": system(place)}, *(moved(sent) if state.moved else sent)]
    try:
        return ask(model, conversation, tools, reasoning=reasoning, held=held)
    except refine_remote.ServerError as exc:
        pictured = any(message.get("role") == "tool" and isinstance(message.get("content"), list) for message in sent)
        if state.moved or not pictured or exc.code not in (400, 415, 422) or _refuses_tools(exc):
            raise
        first = exc
    try:
        body = ask(model, [{"role": "system", "content": system(place)}, *moved(sent)], tools,
                   reasoning=reasoning, held=held)
    except refine_remote.ServerError:
        # Not the pictures, then: the server's first words are the ones to hear.
        raise first from None
    state.moved = True
    return body


def _pictures(message):
    content = message.get("content")
    return [part for part in content if part.get("type") == "image_url"] if isinstance(content, list) else []


def _words(message):
    content = message.get("content")
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
    return content or ""


def thinned(messages):
    """The conversation with only the newest pictures the tools made.

    An older one is a line of text in what is sent. A person's pictures are the
    brief and are never taken out.
    """
    made = [at for at, message in enumerate(messages) if message.get("role") == "tool" for _ in _pictures(message)]
    over = len(made) - PICTURES_KEPT
    if over <= 0:
        return messages
    drop = min(len(made), -(-over // PICTURES_DROPPED) * PICTURES_DROPPED)
    out, left = [], drop
    for message in messages:
        if left and message.get("role") == "tool" and _pictures(message):
            parts = []
            for part in message["content"]:
                if part.get("type") == "image_url" and left:
                    left -= 1
                    part = {"type": "text", "text": EARLIER_PICTURE}
                parts.append(part)
            message = {**message, "content": parts}
        out.append(message)
    return out


def moved(messages):
    """Each picture in a tool's answer, in a user message straight after the
    answers of that reply instead."""
    out, waiting = [], []

    def flush():
        if waiting:
            out.append({"role": "user", "content": [
                {"type": "text", "text": "The pictures the tools answered with, in order:"}, *waiting]})
            waiting.clear()

    for message in messages:
        if message.get("role") != "tool":
            flush()
            out.append(message)
            continue
        pictures = _pictures(message)
        if pictures:
            waiting.extend(pictures)
            message = {**message, "content": "\n".join(filter(None, [_words(message), "(a picture follows)"]))}
        out.append(message)
    flush()
    return out


# ---- asking in plain JSON -----------------------------------------------------------


class Unreadable(ValueError):
    """A fenced reply that names neither calls nor words, with why."""


def fenced_system(tools, place="blockout"):
    """The system text of the fenced form: the prompt, how to reply, and each
    tool's name and docstring as `stagehand.js` writes them. One source for
    both ways of asking."""
    described = "\n\n".join(f"## {tool['function']['name']}\n{tool['function'].get('description', '').strip()}"
                            for tool in tools)
    return f"{system(place)}\n\n{fenced_prompt()}\n\n{described}"


def _as_fence(message):
    """One of the model's own replies, as it would have written it."""
    calls = message.get("tool_calls") or []
    words = _words(message).strip()
    if not calls:
        return "```json\n" + json.dumps({"say": words}, ensure_ascii=False) + "\n```"

    def given(call):
        try:
            return json.loads(call["function"].get("arguments") or "{}")
        except ValueError:
            return {}

    wrote = {"calls": [{"tool": call["function"]["name"], "args": given(call)} for call in calls]}
    return "\n".join(filter(None, [words, "```json\n" + json.dumps(wrote, ensure_ascii=False) + "\n```"]))


def turns(messages, fold=False):
    """The conversation as turns of text: `[{"role", "text", "images"}]`.

    The person's messages, the model's own replies as it would have written
    them, and each tool's answer as a turn of its own with its picture.
    `images` are `data:` URLs, in the order the turn shows them.

    Folded, every message before the current one keeps the person's words and
    the model's closing words and loses the calls between. Nothing the model
    needs goes with them: each message carries the scene as it stands.
    """
    current = max((at for at, message in enumerate(messages) if message.get("role") == "user"), default=0)
    names, out = {}, []
    for at, message in enumerate(messages):
        role = message.get("role")
        images = [part["image_url"]["url"] for part in _pictures(message)]
        if role == "user":
            out.append({"role": "user", "text": _words(message), "images": images})
        elif role == "assistant":
            for call in message.get("tool_calls") or []:
                names[call.get("id")] = call["function"]["name"]
            if fold and at < current and message.get("tool_calls"):
                continue
            out.append({"role": "assistant", "text": _as_fence(message), "images": []})
        elif role == "tool":
            if fold and at < current:
                continue
            name = names.get(message.get("tool_call_id"), "a tool")
            out.append({"role": "user", "text": f"{name} answered:\n{_words(message)}".rstrip(), "images": images})
    return out


def as_messages(system_text, turns_):
    """Turns -> what a chat-completions server takes, with no tools in it."""
    out = [{"role": "system", "content": system_text}]
    for turn_ in turns_:
        content = turn_["text"]
        if turn_["images"]:
            content = [*({"type": "image_url", "image_url": {"url": url}} for url in turn_["images"]),
                       {"type": "text", "text": turn_["text"]}]
        out.append({"role": turn_["role"], "content": content})
    return out


def _closed(text):
    """An object the model forgot to close -> the object, or None. Only the
    missing brackets are put back, outside strings, in the order they are owed."""
    start = text.find("{")
    if start < 0:
        return None
    text = re.sub(r"\s*```\s*$", "", text[start:])
    stack, quoted, escaped = [], False, False
    for char in text:
        if quoted:
            escaped = char == "\\" and not escaped
            if char == '"' and not escaped:
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or stack.pop() != char:
                return None
    if quoted or not stack:
        return None
    try:
        data = json.loads(text + "".join(reversed(stack)))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def read(reply, at=0):
    """A fenced reply -> the message a server would have sent, calls as `tool_calls`.

    Read tolerantly, as the chat reads one: the object is found past a trace,
    a fence and a sentence in front of it, and one left open is closed. A reply
    with no object at all is the model's words. What a call names and is given
    is not judged here: a tool that does not exist or a wrong argument goes to
    the tool, which answers with why, exactly as for a native call. `at` makes
    the calls' ids the conversation's own.
    """
    text = refine.THINK_RE.sub("", reply or "").strip()
    if "{" not in text:
        if not text:
            raise Unreadable("your reply was empty.")
        return {"role": "assistant", "content": text}
    try:
        wrote = refine.json_object(text)
    except refine.RefineError:
        wrote = _closed(text)
    if wrote is None:
        raise Unreadable("the JSON in your reply could not be read.")
    calls = wrote.get("calls")
    if isinstance(calls, list) and calls:
        if not all(isinstance(call, dict) for call in calls):
            raise Unreadable('each entry of "calls" has to be an object with "tool" and "args".')
        plan = text[:text.find("{")].split("```")[0].strip()
        return {"role": "assistant", "content": plan, "tool_calls": [
            {"id": f"f{at}-{k}", "type": "function", "function": {
                "name": str(call.get("tool") or call.get("name") or ""),
                "arguments": json.dumps(call.get("args") if call.get("args") is not None else call.get("arguments", {}),
                                        ensure_ascii=False)}}
            for k, call in enumerate(calls)]}
    if isinstance(wrote.get("say"), str) and wrote["say"].strip():
        return {"role": "assistant", "content": wrote["say"].strip()}
    raise Unreadable('the object has to hold "calls", a list with at least one call, or "say", your words.')


def _fenced(written, messages, tools, fold, place):
    """One exchange in the fenced form. A reply that cannot be read is asked
    for once more with the reason; a second ends the message."""
    system_text, asked = fenced_system(tools, place), turns(messages, fold=fold)
    raw = [written(system_text, asked)]
    try:
        message = read(raw[0], len(messages))
    except Unreadable as why:
        again = [*asked, {"role": "assistant", "text": refine.THINK_RE.sub("", raw[0] or "").strip(), "images": []},
                 {"role": "user", "images": [], "text": (
                     f"That cannot be used: {why} Answer again, the same way: one line of what you are "
                     "about to do, then the object in a ``` fence.")}]
        raw.append(written(system_text, again))
        try:
            message = read(raw[1], len(messages))
        except Unreadable as second:
            raise refine.RefineError(
                f"The model's reply could not be read as calls, twice: {second}") from None
    return {"choices": [{"message": message, "finish_reason": "stop"}], "raw": raw}


def stop(session):
    """End what a session has out. -> whether an exchange was.

    An exchange that is out has its connection closed, and `turn` ends as
    `Stopped`. Between two exchanges there is nothing to close, and the model
    the message left on the server is dropped if the settings asked for that.
    """
    with _LOCK:
        state = _SESSIONS.get(session)
        held = state.held if state else None
        warm = state.warm if state else ""
        if state and held is None:
            state.warm = ""
    if held is not None:
        held.close()
        return True
    if warm:
        refine_remote.unload(warm)
    return False
