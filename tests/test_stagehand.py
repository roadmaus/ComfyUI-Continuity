"""What the blockout agent's server half promises: the conversation goes out as
it came, and the log holds all of it once, with its pictures as files.

Runs standalone — `python tests/test_stagehand.py` — with no ComfyUI and no network.
"""

import base64
import json
import os
import tempfile

import layout

stagehand = layout.load("prompting", "refine_remote", "stagehand").stagehand

PNG = base64.b64encode(b"a picture").decode()
asked = []


def ask(model, messages, tools):
    asked.append(messages)
    return {"choices": [{"message": {"role": "assistant", "content": "yes"}}]}


def refuse(model, messages, tools):
    raise RuntimeError("down")


with tempfile.TemporaryDirectory() as root:
    first = [{"role": "user", "content": "a street"}]
    stagehand.turn("2026-a", "m", first, [], 0, root=root, ask=ask)
    assert asked == [first], "nothing is put in front of what the user said"
    more = first + [{"role": "assistant", "content": "yes"}, {"role": "tool", "tool_call_id": "c", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}]}]
    stagehand.turn("2026-a", "m", more, [], 2, root=root, ask=ask)
    assert asked[1] == more, "the log's copy is not what is sent"
    try:
        stagehand.turn("2026-a", "m", more, [], 3, root=root, ask=refuse)
        raise AssertionError("a failure is the caller's to hear")
    except RuntimeError:
        pass
    folder = os.path.join(root, "2026-a")
    with open(os.path.join(folder, "log.jsonl"), encoding="utf-8") as handle:
        log = [json.loads(line) for line in handle]
    assert [entry["kind"] for entry in log] == ["tools", "message", "reply", "message", "reply", "error"], log
    with open(os.path.join(folder, log[3]["message"]["content"][0]["file"]), "rb") as handle:
        assert handle.read() == b"a picture"
    for bad in ("../up", "a/b", "", "UP"):
        try:
            stagehand.turn(bad, "m", first, [], 0, root=root, ask=ask)
            raise AssertionError(f"took the session {bad!r}")
        except ValueError:
            pass
