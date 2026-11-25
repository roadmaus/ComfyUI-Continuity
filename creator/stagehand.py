"""The blockout's agent, server side: put the prompt in front, pass an exchange
on, and write it down.

The conversation and its tools live in the browser (`web/creator/stagehand.js`),
where the piece and the renderer are. What is left here is what a browser must
not do: hold the server's key, and keep a log. The one prompt is a file,
`prompts/stagehand/system.txt`, and goes in front of every exchange as it is.

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

_PROMPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "stagehand", "system.txt")
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


_SESSIONS = {}
_LOCK = threading.Lock()


def system():
    """The system prompt, read once and held."""
    if "system" not in _read:
        with open(_PROMPT, "r", encoding="utf-8") as handle:
            _read["system"] = handle.read().strip()
    return _read["system"]


def log_root():
    import folder_paths

    return os.path.join(folder_paths.get_user_directory(), "continuity", "stagehand")


def refusal(backend, model):
    """Why this backend and model cannot be asked, in the chat's words, or ""."""
    if backend != "remote":
        if not str(model or "").strip():
            return ("No text encoder chosen. Put a Qwen3-VL or Qwen3.5 text encoder in "
                    "models/text_encoders and pick it in the refiner's settings.")
        return ("Stagehand cannot ask a model in ComfyUI yet. Select a server in the "
                "refiner's settings.")
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
         root=None, ask=None):
    """One exchange -> the server's reply.

    `messages` is the conversation as the browser holds it; the system prompt
    is put in front of it here, every time and nowhere else. `messages[seen:]`
    are new to the log, unless the log knows better: after an exchange that
    failed or was stopped the browser has not heard what was written.

    `eject` asks the server to drop the model when the message is over: on the
    reply that calls no tool, and on any failure. Between the exchanges of one
    message it stays loaded, and `stop` drops it if the message ends there.
    """
    if not SESSION.fullmatch(session):
        raise ValueError("bad session id")
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
        body = _exchange(state, session, model, messages, tools, seen, backend, reasoning,
                         root or log_root(), ask or refine_remote.converse, held)
        over = not body["choices"][0]["message"].get("tool_calls")
        return body
    finally:
        with _LOCK:
            state.held = None
            state.warm = model if eject and not over else ""
        if eject and over:
            refine_remote.unload(model)


def _exchange(state, session, model, messages, tools, seen, backend, reasoning, root, ask, held):
    folder = os.path.join(root, session)
    new = not os.path.isdir(folder)
    os.makedirs(folder, exist_ok=True)
    if new:
        _sweep(root)
    with open(os.path.join(folder, "log.jsonl"), "a", encoding="utf-8") as log:
        def write(kind, **entry):
            log.write(json.dumps({"at": time.time(), "kind": kind, **entry}, ensure_ascii=False) + "\n")
            log.flush()

        start = max(int(seen), state.logged)
        if not start:
            write("tools", backend=backend, model=model, system=system(), tools=tools)
        for at in range(start, len(messages)):
            write("message", message=_readable(messages[at], folder, str(at)))
        state.logged = len(messages)
        started = time.time()
        try:
            body = ask(model, [{"role": "system", "content": system()}, *messages], tools,
                       reasoning=reasoning, held=held)
        except Exception as exc:
            if held.closed:
                write("stopped", seconds=time.time() - started)
                raise Stopped("Stopped.") from None
            write("error", error=str(exc), seconds=time.time() - started)
            raise
        choice = body["choices"][0]
        write("reply", asked="tools", reply=choice, usage=body.get("usage"),
              timings=body.get("timings"), seconds=time.time() - started)
        if held.closed:
            raise Stopped("Stopped.")
        if choice.get("finish_reason") == "length":
            # In the log, and not in the conversation: half a call is no call.
            raise refine.RefineError(
                f"The reply of '{model}' was cut off: it ran into the server's own limit "
                f"on the length of a reply.")
        # The browser puts the reply after what it sent.
        state.logged = len(messages) + 1
    return body


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
