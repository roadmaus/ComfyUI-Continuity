"""What the remote refiner promises about the key it is trusted with.

Runs standalone — `python tests/test_refine_remote.py` — with no torch, no
ComfyUI and no network. The transport is one urllib call and is not what this
suite is for. What is pinned here is the security contract `refine_remote.py`
states in its docstring, because every clause of it is silent when it breaks:
a key that survives a URL change is delivered to whoever the URL now names, a
key over plain HTTP is on the wire in the clear, a key in an exception string
is in the console log, and a credentials file open to the group is open.

The request building rides along — turn shapes and image order are the same
kind of no-network contract, and `refine.chatml` already has its half pinned.
"""

import json
import os
import stat
import sys
import tempfile

import layout

pkg = layout.load("prompting", "refine_remote")
remote, refine = pkg.refine_remote, pkg.prompting

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if fragment not in str(exc):
            FAILURES.append(f"{label}: raised {exc!r}, want mention of {fragment!r}")
    else:
        FAILURES.append(f"{label}: did not raise")


# The credentials live wherever the suite says for the duration: `_path` is the
# module's one seam into ComfyUI's user directory.
_dir = tempfile.mkdtemp()
remote._path = lambda: os.path.join(_dir, remote.FILE)


# ---- the URL rules -----------------------------------------------------------

check("a clean base URL survives",
      remote.normalize_url("http://localhost:1234/v1"), "http://localhost:1234/v1")
check("a trailing slash is shed",
      remote.normalize_url("http://localhost:1234/v1/"), "http://localhost:1234/v1")
check("the full endpoint pasted from docs is trimmed to its base",
      remote.normalize_url("https://api.openai.com/v1/chat/completions"),
      "https://api.openai.com/v1")
check("the models endpoint pasted is trimmed too",
      remote.normalize_url("http://localhost:11434/v1/models"),
      "http://localhost:11434/v1")
check("empty stays empty rather than erroring", remote.normalize_url(""), "")
expect_error("a bare host without a scheme is refused",
             lambda: remote.normalize_url("localhost:1234"), "http://")
expect_error("a file URL is refused — it would be a read primitive",
             lambda: remote.normalize_url("file:///etc/passwd"), "http://")


# ---- the key-to-URL binding --------------------------------------------------

remote.configure("http://localhost:1234/v1", "sk-test-123")
check("a saved key reads back as set, never as itself",
      remote.status(), {"url": "http://localhost:1234/v1", "key_set": True})

remote.configure("http://localhost:1234/v1")
check("a save with no key keeps the stored one while the URL stands still",
      remote.status()["key_set"], True)

remote.configure("http://elsewhere.example/v1")
check("moving the URL without a new key drops the stored one",
      remote.status(), {"url": "http://elsewhere.example/v1", "key_set": False})

remote.configure("https://api.example/v1", "sk-fresh")
remote.configure("https://api.example/v1", "")
check("an empty key is the explicit forget",
      remote.status()["key_set"], False)

expect_error("a key with no URL has nothing to belong to",
             lambda: remote.configure("", "sk-orphan"), "URL")
expect_error("a control character in the key is a wrong-clipboard paste",
             lambda: remote.configure("https://api.example/v1", "sk-\n-oops"),
             "control characters")

with open(remote._path(), "r", encoding="utf-8") as handle:
    stored = json.load(handle)
check("the file holds the refiner namespace, leaving room for later credentials",
      sorted(stored), ["refiner"])
if sys.platform != "win32":
    mode = stat.S_IMODE(os.stat(remote._path()).st_mode)
    check("the credentials file is owner-only", oct(mode), oct(0o600))


# ---- where a key may travel --------------------------------------------------

check("no key means plain headers whatever the scheme",
      "Authorization" in remote._headers("http://192.168.1.20:11434/v1", ""), False)
check("a key rides to loopback over http — LM Studio's own default",
      remote._headers("http://localhost:1234/v1", "sk-a")["Authorization"],
      "Bearer sk-a")
check("127.x is loopback too",
      "Authorization" in remote._headers("http://127.0.0.1:8080/v1", "sk-a"), True)
check("a key rides anywhere over https",
      "Authorization" in remote._headers("https://openrouter.ai/api/v1", "sk-a"), True)
anthropic = remote._headers("https://api.anthropic.com/v1", "sk-a")
check("anthropic gets its native headers beside the Bearer — its /models wants them",
      (anthropic.get("x-api-key"), anthropic.get("anthropic-version"),
       anthropic.get("Authorization")),
      ("sk-a", "2023-06-01", "Bearer sk-a"))
check("no other host gets the native pair",
      "x-api-key" in remote._headers("https://api.openai.com/v1", "sk-a"), False)
expect_error("a key over plain http to the LAN is refused, with the fix named",
             lambda: remote._headers("http://192.168.1.20:11434/v1", "sk-a"),
             "https")

check("the scrub blots the key out of any text bound for a log",
      remote._scrub("401 for key sk-live-9 at host", "sk-live-9"),
      "401 for key ••• at host")
check("the scrub with no key changes nothing",
      remote._scrub("connection refused", ""), "connection refused")


# ---- the request shape -------------------------------------------------------

turns = remote.messages("SYSTEM", "the request", ())
check("no attachments -> a plain string user turn, the shape every server parses",
      turns, [{"role": "system", "content": "SYSTEM"},
              {"role": "user", "content": "the request"}])

turns = remote.messages("SYSTEM", "the request", ("data:a", "data:b"))
parts = turns[1]["content"]
check("images lead the user turn in order, as refine.chatml binds them",
      [part["type"] for part in parts], ["image_url", "image_url", "text"])
check("the Nth attachment is the Nth image",
      [part["image_url"]["url"] for part in parts[:2]], ["data:a", "data:b"])
check("the text rides behind them whole", parts[2]["text"], "the request")


# ---- parameter negotiation ---------------------------------------------------

payload = {"model": "m", "messages": [], "temperature": 0.3, "max_tokens": 2048,
           "seed": 7, "stream": False}
check("a refused temperature is dropped and named",
      remote.adapt("`temperature` is deprecated for this model.", payload),
      "temperature")
check("…and is gone from the resend", "temperature" in payload, False)
check("max_tokens renames when the complaint offers the successor",
      remote.adapt("Unsupported parameter: 'max_tokens' is not supported with this "
                   "model. Use 'max_completion_tokens' instead.", payload),
      "max_tokens -> max_completion_tokens")
check("…keeping the reply budget under the new name",
      payload.get("max_completion_tokens"), 2048)
check("a refused seed is dropped",
      remote.adapt("Unsupported parameter: 'seed'.", payload), "seed")
check("an unrelated 400 changes nothing and is not retried",
      remote.adapt("model 'qwen3' not found", dict(payload)), None)
check("a complaint about a parameter never sent changes nothing",
      remote.adapt("`temperature` is deprecated for this model.", payload), None)


# ---- the reply shapes --------------------------------------------------------

content, finish = remote._content(
    {"choices": [{"message": {"content": "{\"a\": 1}"}, "finish_reason": "stop"}]})
check("a string content passes through", (content, finish), ('{"a": 1}', "stop"))

content, _ = remote._content(
    {"choices": [{"message": {"content": [
        {"type": "text", "text": "{\"a\":"}, {"type": "text", "text": " 1}"}]}}]})
check("content parts are joined", content, '{"a": 1}')

expect_error("a reply that is not a chat completion says so",
             lambda: remote._content({"detail": "not found"}), "not a chat completion")


passed("all remote refiner contract tests passed")
