"""The refiner over a server the user already runs: one OpenAI-compatible client.

`refine_local.py` is the default for a reason it states itself — a second
runtime is VRAM ComfyUI cannot see or reclaim. This module is for the machine
where that argument runs the other way: an LM Studio or Ollama that is already
resident for other work, a box on the LAN with the big model, a hosted API. For
that machine the *in-process* load is the redundant copy, and issue #19 is a
user copy-pasting prompts by hand to route around it.

One client, not one per provider. LM Studio, Ollama (`/v1`), llama.cpp's
server, vLLM, KoboldCpp, OpenRouter and OpenAI all speak the same
chat-completions dialect, and Anthropic and Gemini publish compatibility
endpoints for it — so "support everything" is a base URL and a model name, and
a provider this file has never heard of works the day it ships that dialect.

**Where the key lives, and where it never goes.** The API key is written once,
through the save route, into its own file in ComfyUI's user directory with
owner-only permissions — not into `continuity.settings.json`, which is a file
people paste into bug reports, and not anywhere the browser can read it back:
the status route answers "a key is set", never the key, not even a masked
suffix. Nothing here rides in `creator_data` either — a workflow `.json` is
handed around, and the blob carries the model's *name* at most, exactly as it
always has for the local backend. (MITRE's names for the traps this is built
around: CWE-522/312 for a key in localStorage, CWE-319 for one on plaintext
HTTP, CWE-532 for one in a log line, CWE-918 for a server that will attach it
to any URL a request names.)

**The key is bound to the URL it was saved with.** ComfyUI's server has no
authentication, so anyone who can reach it could otherwise repoint the base URL
at a host they control and let the next refine deliver the stored key to it.
`configure` therefore drops the key whenever the URL changes without a new key
arriving in the same save — moving the endpoint is a gesture that re-earns the
credential, never one that inherits it. And the models proxy only ever fetches
the *stored* URL: no route here fetches an address a request supplied.

**A key travels only over HTTPS or to loopback.** `http://localhost:1234/v1`
is LM Studio's own default and never leaves the machine; `http://` to anything
else with a key attached is the key on the wire in the clear, and `_headers`
refuses it with the fix in the message rather than sending it and hoping.

**Ejecting.** A server that keeps the refiner's model resident is holding VRAM
the sampler is about to want, which on one machine is the whole difference
between a refine and a slower render. So a press can end by asking the server
to drop the model again: `unload` walks the two endpoints that exist for it —
LM Studio's `/api/v1/models/unload` and Ollama's `keep_alive: 0` — and a server
with neither is left alone, silently, because failing to free memory is not a
reason to fail a rewrite that already succeeded. It is asked only of a server
on this machine or this LAN: a hosted API has nothing to evict, and an unload
POST at a public host would only be the key on a stranger's wire again.

Errors are wrapped before they are raised: no header ever reaches an exception
string, and `_scrub` blots the key out of any text that might have picked it
up, because a traceback in the ComfyUI console is a log line like any other.

Everything below stdlib: `urllib` is the whole transport, so this adds no
dependency. No torch, no ComfyUI at module scope — the pure suite tests the
request building, the URL rules and the key binding without either.
"""

import base64
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .families import refine

# Its own file, not a corner of `continuity.settings.json`: the settings file
# is quoted in bug reports and synced by people who sync their user folder,
# and a credential in it would be one screenshot from public. Owner-only on
# every write; `refiner` is a namespace so a later credential has a home.
FILE = "continuity.credentials.json"

# How long one call may sit on the wire. Connect fails in seconds on its own;
# this is the read side, and a whole-timeline rewrite on a big model genuinely
# runs for minutes with nothing arriving.
TIMEOUT = 600

# What a fetched error body may contribute to a message shown in the panel.
# Enough to read the provider's complaint, not enough to relay a novel.
ERROR_EXCERPT = 300


class ConfigError(ValueError):
    """A URL or key this module will not store, with the reason."""


class ServerError(refine.RefineError):
    """The server answered with an error status. Carries the pieces `chat`'s
    parameter negotiation reads — the code, and the provider's own complaint —
    while staying the RefineError every caller already handles."""

    def __init__(self, message, code, detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


# ---- the credentials file ----------------------------------------------------


def _path():
    import folder_paths

    return os.path.join(folder_paths.get_user_directory(), FILE)


def _read():
    try:
        with open(_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return {}
    entry = stored.get("refiner")
    return entry if isinstance(entry, dict) else {}


def _write(entry):
    target = _path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    # Created owner-only from the first byte — `open` then `chmod` is a window
    # in which the default umask decides who read the key. Atomic for the same
    # reason `settings.save` is: a half-written file must not eat the key.
    temporary = f"{target}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"refiner": entry}, handle, indent=2)
    os.replace(temporary, target)


def _loopback(host):
    """Traffic to this host never leaves the machine."""
    host = (host or "").lower().strip("[]")
    return (host in ("localhost", "::1")
            or host.startswith("127."))


def _private(host):
    """This host is on this machine or this LAN — the only kind worth ejecting.

    Deliberately coarse: the question is not "is this address safe" (nothing is
    sent that a chat request has not already sent to the same server) but "could
    there be a model here whose memory is mine". A bare name with no dot is a
    LAN hostname the way `lmstudio-box:1234` is one.
    """
    host = (host or "").lower().strip("[]")
    if _loopback(host) or host.endswith(".local") or "." not in host:
        return True
    if host.startswith(("10.", "192.168.", "169.254.")):
        return True
    if host.startswith("172."):
        second = host.split(".")[1] if host.count(".") >= 2 else ""
        return second.isdigit() and 16 <= int(second) <= 31
    return False


def normalize_url(url):
    """A pasted URL -> the base the two endpoints hang off, or ConfigError.

    Tolerant of the obvious paste: a trailing slash, or the full
    `/chat/completions` copied out of a provider's docs. Not tolerant of a
    missing scheme or a scheme that is not HTTP — `file:` here would be a read
    primitive on the server's disk dressed as a setting.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConfigError(
            "the server URL must start with http:// or https:// — "
            "e.g. http://localhost:1234/v1 for LM Studio"
        )
    for tail in ("/chat/completions", "/completions", "/models"):
        if url.endswith(tail):
            url = url[: -len(tail)]
    return url


def configure(url, key=None):
    """Store the endpoint, holding the key-to-URL binding.

    `key=None` means "no key arrived in this save": kept only while the URL is
    the one it was saved against, dropped the moment the URL moves — see the
    module docstring for what that prevents. An empty string is the explicit
    gesture "forget the key". The key is stripped of whitespace and refused if
    it carries control characters, which is what a paste of the wrong clipboard
    looks like.
    """
    url = normalize_url(url)
    stored = _read()
    if key is None:
        key = stored.get("key", "") if url and url == stored.get("url") else ""
    key = (key or "").strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in key):
        raise ConfigError("the API key contains control characters — check the paste")
    if key and not url:
        raise ConfigError("a key needs a server URL to belong to")
    _write({"url": url, "key": key})
    return status()


def status():
    """What the browser may know: the URL, and *whether* a key is set."""
    stored = _read()
    return {"url": stored.get("url", ""), "key_set": bool(stored.get("key"))}


# ---- the wire ----------------------------------------------------------------


def _scrub(text, key):
    """Blot the key out of text bound for a message or a log."""
    return text.replace(key, "•••") if key else text


def _headers(url, key):
    headers = {"Content-Type": "application/json"}
    if key:
        host = urllib.parse.urlparse(url).hostname
        if urllib.parse.urlparse(url).scheme != "https" and not _loopback(host):
            raise refine.RefineError(
                f"the refiner will not send your API key over plain http to "
                f"{host} — use https, or clear the key for an open local server"
            )
        headers["Authorization"] = f"Bearer {key}"
        # Anthropic's compatibility endpoint takes the Bearer for chat, but its
        # `/models` listing is the native API and wants the native headers — so
        # both ride along, and the one endpoint that cares about each reads its
        # own. The lone provider special case, and it is two header lines.
        if host == "api.anthropic.com":
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
    return headers


def _request(url, key, payload=None):
    """One HTTP exchange -> the parsed JSON body, every failure a RefineError.

    The provider's own complaint is worth relaying — "model not found" beats
    "400" — so an error body is excerpted, scrubbed and passed on. Headers are
    never quoted anywhere.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=_headers(url, key),
                                     method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = json.loads(exc.read(4096).decode("utf-8", "replace"))
            detail = ((body.get("error") or {}).get("message")
                      if isinstance(body.get("error"), dict)
                      else body.get("error")) or ""
        except (OSError, ValueError):
            pass
        detail = _scrub(str(detail)[:ERROR_EXCERPT], key)
        raise ServerError(
            f"the server answered {exc.code}" + (f": {detail}" if detail else ""),
            exc.code, detail,
        ) from None
    except urllib.error.URLError as exc:
        raise refine.RefineError(
            f"could not reach {url}: {_scrub(str(exc.reason), key)} — "
            f"is the server running?"
        ) from None
    except (OSError, ValueError) as exc:
        raise refine.RefineError(
            f"the server's reply could not be read: {_scrub(str(exc), key)}"
        ) from None


def list_models(url=None, key=None):
    """The model names the server offers, off its `/models` listing.

    Called with nothing, it lists for the stored endpoint — the only URL the
    routes ever hand it, so no request can point this fetch anywhere. Called
    with an explicit URL by `configure`'s connection test, before anything is
    stored.
    """
    if url is None:
        stored = _read()
        url, key = stored.get("url", ""), stored.get("key", "")
    if not url:
        raise refine.RefineError("no refiner server is configured")
    body = _request(f"{url}/models", key)
    names = [entry.get("id") for entry in body.get("data") or []
             if isinstance(entry, dict) and entry.get("id")]
    return sorted(names)


# How long LM Studio may keep a JIT-loaded model after an ejecting press, in
# seconds. The unload endpoint below is the real mechanism and covers 0.4 and
# later; this is what 0.3, which has no such endpoint, understands — a TTL that
# has all but expired by the time the reply is read. One second rather than zero
# because zero reads as "no TTL" in more dialects than it reads as "now".
EJECT_TTL = 1

# The two ways a local server can be told to drop a model, newest first. Each is
# `(path under the server's root, the body it wants)`; the model name is the
# only variable either takes. LM Studio 0.4 added `/api/v1`; Ollama has always
# taken `keep_alive: 0` on its native generate endpoint, where an empty request
# means "just unload". Everything else — llama.cpp's server, vLLM, KoboldCpp —
# has no such call, answers 404 to both, and is left holding its model.
UNLOADS = (
    ("/api/v1/models/unload", lambda model: {"instance_id": model}),
    ("/api/generate", lambda model: {"model": model, "keep_alive": 0}),
)


def _root(url):
    """`http://host:1234/v1` -> `http://host:1234`.

    The unload endpoints hang off the server itself, not off the OpenAI-shaped
    prefix the chat endpoint lives under.
    """
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def unload(model):
    """Ask the stored server to drop `model`. -> the path that worked, or "".

    Best effort by contract, not by accident: this runs after a rewrite the
    caller already has in hand, so every failure here — a server that has no
    such endpoint, one that has gone away, one that says no — is swallowed. The
    press succeeded; the memory is a preference.
    """
    stored = _read()
    url, key = stored.get("url", ""), stored.get("key", "")
    model = (model or "").strip()
    if not url or not model:
        return ""
    if not _private(urllib.parse.urlparse(url).hostname):
        return ""  # a hosted API holds nothing of ours to free
    root = _root(url)
    for path, body in UNLOADS:
        try:
            _request(f"{root}{path}", key, body(model))
            return path
        except refine.RefineError:
            continue
    return ""


def to_data_url(image):
    """A PIL image -> a `data:` URL, downscaled like `refine_local.to_tensor`.

    JPEG, because the picture is being looked at, not kept: at
    `IMAGE_LONG_EDGE` it is a tenth the bytes of PNG, and every byte is
    base64'd and shipped per call.
    """
    from PIL import Image

    image = image.convert("RGB")
    if max(image.size) > refine.IMAGE_LONG_EDGE:
        image.thumbnail((refine.IMAGE_LONG_EDGE, refine.IMAGE_LONG_EDGE), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


# What `chat` may give up when a server refuses it by name. Hosted reasoning
# models reject sampling controls outright — "`temperature` is deprecated for
# this model", "Unsupported parameter: 'seed'" — and a 400 the user cannot act
# on is the wrong place to stop: the parameters are preferences, the request is
# the prompt. `max_tokens` is the special case with a successor; when the
# complaint names `max_completion_tokens`, it renames instead of dropping, so
# the reply-length budget survives the newer dialect. `ttl` is only ever sent
# by an eject, and only LM Studio knows the word; anything else that bothers to
# complain about it sheds it here and refines anyway.
NEGOTIABLE = ("temperature", "seed", "max_tokens", "ttl")


def adapt(detail, payload):
    """Rewrite `payload` past a 400 naming a parameter. -> what changed, or None.

    Deliberately literal: the named parameter must be one this module sent and
    must appear in the server's own complaint, so an unrelated 400 — a bad
    model name, a malformed message — is never papered over by silently
    resending with less.
    """
    for param in NEGOTIABLE:
        if param not in payload or param not in detail:
            continue
        if param == "max_tokens" and "max_completion_tokens" in detail:
            payload["max_completion_tokens"] = payload.pop("max_tokens")
            return "max_tokens -> max_completion_tokens"
        del payload[param]
        return param
    return None


def messages(system, message, images=()):
    """The two chat turns, images at the head of the user turn.

    The same order `refine.chatml` binds them in, so the glossary's "image N"
    keeps naming the Nth attachment. A plain string when nothing is attached,
    because that is the one shape every server parses.
    """
    if images:
        content = ([{"type": "image_url", "image_url": {"url": url}} for url in images]
                   + [{"type": "text", "text": message}])
    else:
        content = message
    return [{"role": "system", "content": system},
            {"role": "user", "content": content}]


def _content(body):
    """`choices[0].message.content`, whatever shape the server gave it."""
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise refine.RefineError(
            f"the server's reply is not a chat completion: {str(body)[:ERROR_EXCERPT]}"
        ) from None
    content = message.get("content")
    if isinstance(content, list):  # some servers return content parts
        content = "".join(part.get("text", "") for part in content
                          if isinstance(part, dict))
    return content or "", (body.get("choices") or [{}])[0].get("finish_reason")


def chat(model, system, message, images=(), temperature=0.7, seed=-1,
         max_tokens=None, prefill=refine.PREFILL, eject=False):
    """One generation -> the assistant's raw content string.

    The same signature as `refine_local.chat`, which is what lets the routes
    hold one call site per path. Two deliberate differences under it. `images`
    are `data:` URLs, not tensors — `to_data_url` is the counterpart of
    `to_tensor`. And `prefill` shapes nothing: chat-completions has no slot for
    beginning the assistant's turn, so the JSON shape rides on the system
    prompt alone and on `refine.json_object`'s tolerance for a fenced or
    prefaced object — the models people point this at are large enough that
    the brace trick was carrying the small ones.
    """
    stored = _read()
    url, key = stored.get("url", ""), stored.get("key", "")
    if not url:
        raise refine.RefineError(
            "no refiner server is configured — set its URL in the refiner's settings")
    max_tokens = refine.reply_tokens(max_tokens) if max_tokens is not None else refine.NUM_PREDICT

    payload = {
        "model": model,
        "messages": messages(system, message, images),
        "temperature": max(float(temperature), 0.0),
        "max_tokens": max_tokens,
        "stream": False,
    }
    if int(seed) >= 0:
        payload["seed"] = int(seed)
    # Asked for in the same breath as the generation, because LM Studio 0.3 has
    # no unload call and this is the only thing it will hear. Local servers
    # only: `ttl` is a word no hosted provider knows, and the ones that check
    # their parameters would 400 on it — `adapt` sheds it if any of them does.
    if eject and _private(urllib.parse.urlparse(url).hostname):
        payload["ttl"] = EJECT_TTL

    # One try per negotiable parameter, so a server that refuses two sheds
    # both — and a 400 about anything else still surfaces on the first pass.
    try:
        for _ in range(len(NEGOTIABLE) + 1):
            try:
                body = _request(f"{url}/chat/completions", key, payload)
                break
            except ServerError as exc:
                if exc.code != 400 or not adapt(exc.detail, payload):
                    raise
    finally:
        # In a `finally` because a failed press loaded the model just as surely
        # as a successful one did — a refine that errored on the reply's shape
        # must not be the one that leaves the weights sitting in the sampler's
        # memory.
        if eject:
            unload(model)
    content, finish = _content(body)
    if not content.strip():
        raise refine.RefineError(
            f"'{model}' returned nothing — a reasoning model may have spent the "
            f"whole budget thinking. Raise the reply length, or pick another model."
        )
    if finish == "length":
        raise refine.RefineError(
            f"'{model}' ran out of room after {max_tokens} tokens and the reply is "
            f"cut off. Raise the reply length in the refiner's settings, or refine "
            f"fewer cards at once."
        )
    return content
