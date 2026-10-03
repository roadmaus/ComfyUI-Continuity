#!/usr/bin/env python3
"""Render a clip or a picture on a running ComfyUI with this pack, from a shell.

    python3 skills/continuity-render/render.py families
    python3 skills/continuity-render/render.py h3 "a cat stretches on a sunny windowsill"
    python3 skills/continuity-render/render.py h3 "@pic-1 turns and walks off" --image cat.png --seconds 5
    python3 skills/continuity-render/render.py krea2 "a tabby cat, studio portrait" --aspect 4:5

The client half of `/continuity/render` (`creator/routes/render.py`): it uploads
the files you name, asks the server to build and queue the render — the server
picks every weight from what is on its disk and throws the family's turbo switch
— waits for it, and downloads what it made. Standard library only; run it with
any Python 3.9+, on the ComfyUI machine or anywhere that can reach its port.

The server is `--url`, else `$COMFY_URL`, else http://127.0.0.1:8188. What it
prints on stdout is the downloaded path, one per file, so a caller can use the
output directly; progress goes to stderr. It exits non-zero with the server's
own sentence when a render cannot be built or fails.

Renders are fast by default: the family's turbo switch, at its default quality.
`--native` renders at the family's full step count instead (slow on video).
When the server cannot tell which LoRA is the turbo one it says so and names
the candidates; pass one with `--turbo-lora`, or `--merged` when the checkpoint
has the distillation merged in and wants no LoRA. `families` lists what the machine
can render and what fast would use for each family.

Pictures: `--image PATH[:AS]`, repeatable. A local file is uploaded to the
server's input folder; a name that is not a local file is taken as one already
there (`photo.png`, or `H3_00012_.png [output]` for an earlier render). They are
cited in the prompt as `@pic-1`, `@pic-2`, ... (videos `@clip-N`, sounds
`@snd-N`), in the order given. AS is start, end, ref, or a reference scope like
style or person; without it the first picture opens the shot.
"""

import argparse
import json
import mimetypes
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_URL = "http://127.0.0.1:8188"


def say(*parts):
    print(*parts, file=sys.stderr, flush=True)


def fail(message):
    say(f"error: {message}")
    sys.exit(1)


class Server:
    def __init__(self, url):
        self.url = url.rstrip("/")

    def _open(self, request, timeout=600):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")
            try:
                data = json.loads(body)
                body = data.get("problem") or data.get("error") or body
            except ValueError:
                pass
            if err.code == 404 and "/continuity/" in request.full_url:
                body = ("this server has no /continuity/render — is the Continuity "
                        "pack installed, and recent enough?")
            fail(f"{request.get_method()} {request.full_url}: {body}")
        except urllib.error.URLError as err:
            fail(f"cannot reach {self.url} ({err.reason}). Is ComfyUI running there? "
                 f"Set --url or COMFY_URL.")

    def get(self, path, **query):
        url = f"{self.url}{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
        return self._open(urllib.request.Request(url))

    def get_json(self, path, **query):
        return json.loads(self.get(path, **query))

    def post_json(self, path, body):
        request = urllib.request.Request(
            f"{self.url}{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        return json.loads(self._open(request))

    def upload(self, path):
        """A local file into the server's input folder -> the name to cite it by."""
        boundary = uuid.uuid4().hex
        name = os.path.basename(path)
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            data = handle.read()
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{name}\"\r\nContent-Type: {kind}\r\n\r\n".encode(),
            data, f"\r\n--{boundary}--\r\n".encode()])
        request = urllib.request.Request(
            f"{self.url}/upload/image", data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        answer = json.loads(self._open(request))
        sub = answer.get("subfolder") or ""
        return f"{sub}/{answer['name']}" if sub else answer["name"]


def families(server):
    data = server.get_json("/continuity/render")
    for family in data["families"]:
        state = "ready" if family["ready"] else "missing " + ", ".join(family["missing"])
        print(f"{family['id']:<11} {family['label']:<22} {'/'.join(family['produces']):<12} {state}")
        fast = family["fast"]
        if not fast["switch"]:
            print(f"{'':11} fast: no turbo switch (renders at its native row)")
            continue
        if fast.get("checkpoint"):
            print(f"{'':11} fast: turbo checkpoint {fast['checkpoint']}")
        loras = fast.get("loras")
        if isinstance(loras, dict):
            for checkpoint, names in loras.items():
                print(f"{'':11} fast on {checkpoint}: {', '.join(names) or 'no turbo LoRA found'}")
        elif loras is not None and not fast.get("checkpoint"):
            print(f"{'':11} fast: {', '.join(loras) or 'no turbo LoRA found'}")
        print(f"{'':11} qualities: " + ", ".join(f"{q}={n} steps" for q, n in fast["qualities"].items())
              + f" (default {fast['default_quality']})")


def _picture(server, spec):
    """`PATH[:AS]` -> `{"filename", "as"}`, uploading PATH when it is local."""
    path, role = spec, None
    if not os.path.exists(spec) and ":" in spec:
        head, tail = spec.rsplit(":", 1)
        if tail and "/" not in tail and "\\" not in tail:
            path, role = head, tail
    if os.path.isfile(path):
        say(f"uploading {path}")
        filename = server.upload(path)
    else:
        filename = path
    return {"filename": filename, **({"as": role} if role else {})}


def _outputs(entry):
    """Every file the render saved, off its /history entry."""
    files = []
    for node in (entry.get("outputs") or {}).values():
        for key in ("mmc_video", "mmc_image", "videos", "images"):
            files += [f for f in node.get(key) or [] if f.get("type") == "output"]
    return files


def _failure(entry):
    for kind, data in (entry.get("status") or {}).get("messages") or []:
        if kind == "execution_error":
            return f"{data.get('node_type')}: {data.get('exception_message', '').strip()}"
        if kind == "execution_interrupted":
            return "the render was cancelled"
    return None


def wait(server, prompt_id, poll):
    started, last = time.time(), None
    while True:
        history = server.get_json(f"/history/{prompt_id}")
        entry = history.get(prompt_id)
        if entry and (entry.get("status") or {}).get("completed") is not None:
            if not entry["status"]["completed"] or _failure(entry):
                fail(_failure(entry) or "the render failed")
            return entry, time.time() - started
        if entry is None:
            queue = server.get_json("/queue")
            running = [item[1] for item in queue.get("queue_running") or []]
            pending = [item[1] for item in queue.get("queue_pending") or []]
            if prompt_id in running:
                state = "rendering"
            elif prompt_id in pending:
                state = f"queued, {pending.index(prompt_id) + len(running)} ahead"
            else:
                state = "waiting for the server"
            if state != last:
                say(f"{state} ({time.time() - started:.0f}s)")
                last = state
        time.sleep(poll)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run `families` first to see what the server can render.")
    parser.add_argument("family", help="a family id (h3, ltx25, krea2, ...), or `families` to list them")
    parser.add_argument("prompt", nargs="?", help="what to render")
    parser.add_argument("--image", action="append", default=[], metavar="PATH[:AS]",
                        help="a picture, clip or sound to attach; cite it as @pic-1, @clip-1, @snd-1")
    parser.add_argument("--still", action="store_true", help="a picture rather than a clip")
    parser.add_argument("--seconds", type=float, help="clip length (the family's default otherwise)")
    parser.add_argument("--aspect", help="16:9, 9:16, 1:1, 4:5, ...")
    parser.add_argument("--edge", type=int, help="short edge in pixels (the family's native otherwise)")
    parser.add_argument("--seed", type=int, help="random otherwise; printed either way")
    parser.add_argument("--native", action="store_true", help="the family's full step count, not turbo")
    parser.add_argument("--quality", help="turbo quality stop: draft, medium or good")
    parser.add_argument("--turbo-lora", help="the turbo LoRA to use, when the server cannot tell")
    parser.add_argument("--merged", action="store_true",
                        help="the checkpoint has the distillation merged in: turbo steps, no LoRA")
    parser.add_argument("--model", action="append", default=[], metavar="SLOT=FILE",
                        help="a weight file for one slot, over the server's own pick")
    parser.add_argument("--device", action="append", default=[], metavar="SLOT=DEVICE",
                        help="where one slot loads (e.g. clip=cuda:1), over the server's pins")
    parser.add_argument("--attention", help="default, sage, kitchen or sla, over the server's row")
    parser.add_argument("--low-vram", action=argparse.BooleanOptionalAction, default=None,
                        help="chunk the feed-forward to fit the card, over the server's row")
    parser.add_argument("--fast-math", action=argparse.BooleanOptionalAction, default=None,
                        help="fp16 accumulation, over the server's row")
    parser.add_argument("--out", default="renders", help="download folder (default ./renders)")
    parser.add_argument("--no-wait", action="store_true", help="queue and print the prompt id")
    parser.add_argument("--url", default=os.environ.get("COMFY_URL") or DEFAULT_URL,
                        help=f"the ComfyUI server (default $COMFY_URL or {DEFAULT_URL})")
    parser.add_argument("--poll", type=float, default=3.0, help=argparse.SUPPRESS)
    args = parser.parse_args()

    server = Server(args.url)
    if args.family == "families":
        families(server)
        return
    if not args.prompt:
        parser.error("say what to render")

    models = {}
    for item in args.model:
        slot, sep, filename = item.partition("=")
        if not sep:
            parser.error(f"--model takes SLOT=FILE; got {item!r}")
        models[slot] = filename
    devices = {}
    for item in args.device:
        slot, sep, device = item.partition("=")
        if not sep:
            parser.error(f"--device takes SLOT=DEVICE; got {item!r}")
        devices[slot] = device
    seed = args.seed if args.seed is not None else random.randrange(2 ** 32)
    body = {"family": args.family, "prompt": args.prompt,
            "pictures": [_picture(server, spec) for spec in args.image],
            "seed": seed, "fast": not args.native, "models": models}
    if args.still:
        body["still"] = True
    if args.merged:
        body["merged"] = True
    if devices:
        body["devices"] = devices
    accel = {key: value for key, value in (("attention", args.attention),
                                           ("chunk_ffn", args.low_vram),
                                           ("fp16_accumulation", args.fast_math))
             if value is not None}
    if accel:
        body["accel"] = accel
    for key, value in (("seconds", args.seconds), ("aspect", args.aspect),
                       ("short_edge", args.edge), ("quality", args.quality),
                       ("turbo_lora", args.turbo_lora)):
        if value is not None:
            body[key] = value

    queued = server.post_json("/continuity/render", body)
    speed = queued["speed"]
    if isinstance(speed, dict):
        turbo = speed["turbo"]
        using = (turbo.get("checkpoint") or ", ".join(turbo.get("loras") or [])
                 or ("merged checkpoint" if turbo.get("merged") else ""))
        speed = f"turbo {turbo['quality']}, {turbo['steps']} steps, {using}"
    # The checkpoint a video render samples on, said beside the speed: whether a
    # turbo LoRA belongs on it at all depends on which file it is.
    models = (queued.get("piece") or {}).get("models") or {}
    on = f", on {models[models['route']]}" if models.get(models.get("route")) else ""
    # And where each model loads: everything on one card is the slow render
    # nobody asked for, and it is invisible from the speed line alone.
    pins = models.get("devices") or {}
    on += (" (" + ", ".join(f"{slot} on {device}" for slot, device in sorted(pins.items())) + ")"
           if pins else " (every model on ComfyUI's default device)")
    # And how the card runs it, which the node's row sets in the browser and the
    # server's memory of that row sets here: plain attention where the browser
    # runs a kernel is the other slow render nobody asked for.
    row = (queued.get("piece") or {}).get("sampling") or {}
    if queued.get("node") == "MiniMaxH3Creator":
        machine = [f"attention {row.get('attention', 'default')}"]
        machine += ["low vram"] if row.get("chunk_ffn") else []
        machine += ["fast math"] if row.get("fp16_accumulation") else []
        on += ", " + ", ".join(machine)
    say(f"queued {queued['prompt_id']} — seed {seed}, {speed}{on}")
    if args.no_wait:
        print(queued["prompt_id"])
        return

    entry, took = wait(server, queued["prompt_id"], args.poll)
    files = _outputs(entry)
    if not files:
        fail("the render finished but reported no file")
    os.makedirs(args.out, exist_ok=True)
    say(f"done in {took:.0f}s")
    for item in files:
        data = server.get("/view", filename=item["filename"],
                          subfolder=item.get("subfolder") or "", type="output")
        path = os.path.join(args.out, item["filename"])
        with open(path, "wb") as handle:
            handle.write(data)
        print(path)


if __name__ == "__main__":
    main()
