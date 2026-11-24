"""The blockout's agent, server side: pass an exchange on, and write it down.

The conversation and its tools live in the browser (`web/creator/stagehand.js`),
where the piece and the renderer are. What is left here is what a browser must
not do: hold the server's key, and keep a log. There is no prompt in this file.
"""

import base64
import json
import os
import re
import time

from . import refine_remote

SESSION = re.compile(r"[a-z0-9-]{4,64}")


def log_root():
    import folder_paths

    return os.path.join(folder_paths.get_user_directory(), "continuity", "stagehand")


def _readable(message, folder, stem):
    """A message as the log keeps it: its pictures as files beside it."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    parts = []
    for at, part in enumerate(content):
        url = (part.get("image_url") or {}).get("url", "")
        if url.startswith("data:image/png;base64,"):
            name = f"{stem}-{at}.png"
            with open(os.path.join(folder, name), "wb") as handle:
                handle.write(base64.b64decode(url.split(",", 1)[1]))
            part = {"type": "image", "file": name}
        parts.append(part)
    return {**message, "content": parts}


def turn(session, model, messages, tools, seen, root=None, ask=None):
    """One exchange -> the server's reply. `messages[seen:]` are new to the log."""
    if not SESSION.fullmatch(session):
        raise ValueError("bad session id")
    folder = os.path.join(root or log_root(), session)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "log.jsonl"), "a", encoding="utf-8") as log:
        def write(kind, **entry):
            log.write(json.dumps({"at": time.time(), "kind": kind, **entry}, ensure_ascii=False) + "\n")
            log.flush()

        if not seen:
            write("tools", model=model, tools=tools)
        for at in range(seen, len(messages)):
            write("message", message=_readable(messages[at], folder, str(at)))
        started = time.time()
        try:
            body = (ask or refine_remote.converse)(model, messages, tools)
        except Exception as exc:
            write("error", error=str(exc), seconds=time.time() - started)
            raise
        write("reply", reply=body["choices"][0], usage=body.get("usage"),
              timings=body.get("timings"), seconds=time.time() - started)
    return body
