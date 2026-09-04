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


# ---- ejecting ----------------------------------------------------------------
#
# What the unload promises is that it is asked of the right servers and that it
# can never turn a finished rewrite into a failure. Both are checkable without a
# socket: `_request` is the module's one seam onto the wire.

check("a ttl is negotiable — only LM Studio knows the word",
      remote.adapt("Unrecognized request argument supplied: ttl",
                   {"model": "m", "ttl": 1}), "ttl")

for host in ("localhost", "127.0.0.1", "::1", "192.168.1.20", "10.0.0.4",
             "172.16.3.9", "172.31.255.1", "studio-box", "studio.local"):
    check(f"{host} is a machine whose memory could be ours", remote._private(host), True)
for host in ("api.openai.com", "openrouter.ai", "172.15.0.1", "172.32.0.1",
             "8.8.8.8"):
    check(f"{host} holds nothing of ours to free", remote._private(host), False)

calls = []
real_request = remote._request


def _fake(answers):
    """Record every call and answer from `answers`, keyed by the whole URL."""
    def request(url, key, payload=None):
        calls.append((url, payload))
        answer = answers.get(url)
        if isinstance(answer, Exception):
            raise answer
        return answer if answer is not None else {}
    return request


remote.configure("http://localhost:1234/v1", "")

# LM Studio 0.4 and later answer the first endpoint; nothing else is tried.
calls.clear()
remote._request = _fake({"http://localhost:1234/api/v1/models/unload": {"ok": True}})
check("the unload goes to the server's root, not under the /v1 prefix",
      remote.unload("qwen3-vl"), "/api/v1/models/unload")
check("…and stops at the one that answered", len(calls), 1)
check("…naming the model as the instance to drop",
      calls[0][1], {"instance_id": "qwen3-vl"})

# Ollama has no such endpoint; the ladder falls through to keep_alive.
calls.clear()
remote._request = _fake({
    "http://localhost:1234/api/v1/models/unload": remote.ServerError("404", 404, ""),
    "http://localhost:1234/api/generate": {"done": True},
})
check("a server without the newer endpoint gets the keep_alive call",
      remote.unload("qwen3:8b"), "/api/generate")
check("…which says zero seconds, which is Ollama for now",
      calls[-1][1], {"model": "qwen3:8b", "keep_alive": 0})

# llama.cpp, vLLM, KoboldCpp: neither call exists, and that is not an error.
calls.clear()
remote._request = _fake({
    "http://localhost:1234/api/v1/models/unload": remote.ServerError("404", 404, ""),
    "http://localhost:1234/api/generate": refine.RefineError("could not reach"),
})
check("a server that can do neither is left alone, silently", remote.unload("m"), "")
check("…after asking both ways", len(calls), 2)

remote.configure("https://api.openai.com/v1", "sk-hosted")
calls.clear()
remote._request = _fake({})
check("a hosted API is never asked to unload anything", remote.unload("gpt-4o"), "")
check("…and nothing went out to it", calls, [])
remote._request = real_request
remote.configure("http://localhost:1234/v1", "")

# ---- thinking -----------------------------------------------------------------
#
# Chat-completions has no prefill slot, so reasoning is switched off by the one
# field the dialect has for it — and shed like any other parameter where the
# provider does not know the value. Where a build reasons regardless, the
# empty reply is named for what it is rather than reported as a broken server.

# OpenAI's actual wording names the field only in `param`, which `_request`
# appends to the detail; this is the detail as `adapt` then sees it.
check("reasoning is negotiable",
      remote.adapt("Invalid value: 'none'. Supported values are: 'low', 'medium', "
                   "and 'high'. (param: reasoning_effort)",
                   {"model": "m", "reasoning_effort": "none"}), "reasoning_effort")

remote.configure("http://localhost:1234/v1", "")
calls.clear()
remote._request = _fake({"http://localhost:1234/v1/chat/completions": {
    "choices": [{"message": {"role": "assistant", "content": "{\"shots\": []}"},
                 "finish_reason": "stop"}]}})
check("the request asks for no reasoning", remote.chat("m", "sys", "hi"), '{"shots": []}')
check("…in the OpenAI spelling", calls[-1][1].get("reasoning_effort"), "none")

remote._request = _fake({"http://localhost:1234/v1/chat/completions": {
    "choices": [{"message": {"role": "assistant", "content": "",
                             "reasoning": "Hmm, the user wants a video…"},
                 "finish_reason": "length"}],
    "usage": {"completion_tokens": 6144}}})
try:
    remote.chat("qwen3-vl:4b", "sys", "hi")
    check("an empty reply with a trace beside it is refused", False, True)
except refine.RefineError as exc:
    check("an empty reply with a trace beside it names the thinking",
          "spent its whole reply of 6144 tokens thinking" in str(exc), True)

remote._request = _fake({"http://localhost:1234/v1/chat/completions": {
    "choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]}})
try:
    remote.chat("m", "sys", "hi")
    check("an empty reply with no trace is refused", False, True)
except refine.RefineError as exc:
    check("an empty reply with no trace is not blamed on thinking",
          "returned nothing" in str(exc), True)
remote._request = real_request


# ---- the reply shapes --------------------------------------------------------

content, finish, _ = remote._content(
    {"choices": [{"message": {"content": "{\"a\": 1}"}, "finish_reason": "stop"}]})
check("a string content passes through", (content, finish), ('{"a": 1}', "stop"))

content, _, _ = remote._content(
    {"choices": [{"message": {"content": [
        {"type": "text", "text": "{\"a\":"}, {"type": "text", "text": " 1}"}]}}]})
check("content parts are joined", content, '{"a": 1}')

expect_error("a reply that is not a chat completion says so",
             lambda: remote._content({"detail": "not found"}), "not a chat completion")


passed("all remote refiner contract tests passed")
