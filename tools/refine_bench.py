#!/usr/bin/env python3
"""Run the built-in refiner headless, against a local OpenAI-compatible server.

The refine button is a server round trip through `refine_routes._run`: compile
the piece, look at the pictures, ask the model, parse, normalise the handles,
check what points at nothing. Iterating on the prompts through the ComfyUI
panel means a browser, a queue and a screenshot per attempt. This runs the
same `_run`, on the same code, with only disk and the server registration
stubbed — so what it prints is exactly what the panel would show, problems
included, for a piece built here out of two pictures and a cast.

    python3 tools/refine_bench.py --person face.png --scene room.jpg
    python3 tools/refine_bench.py ... --model qwen3-vl:4b --target timeline --dump

`--target` is which press to make: `simple` (the default) is a one-card piece
whose text is "@<name> is eating a sandwich"; `0` and `1` are the two cards of
a two-card piece — the first cites the member and the scene, the second says
only "she" — and `timeline` refines both at once. `--dump` prints the system
prompt and the message before the reply. `--url` is the server, Ollama's by
default; nothing is read from or written to the node's credential file.

Any OpenAI-compatible server works. On an 8 GB Mac, an Ollama Qwen3-VL 2B
with an 8k context (`PARAMETER num_ctx 8192` in a Modelfile) answers in about
thirty seconds and shows every prompting failure a 4B does. Ollama's
`qwen3-vl:4b` build reasons before it answers and nothing on the OpenAI route
switches that off, so it spends the reply budget thinking and returns nothing
— use a bigger budget with `--max-tokens`, or the 2B.

Needs the ComfyUI venv for PIL only: no torch, no ComfyUI, no model on this
side of the wire.
"""

import argparse
import importlib.util
import os
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import layout  # noqa: E402 — tests' loader, which knows where the family modules live


def _load_routes(url):
    """`refine_routes`, with the server, the disk and the job queue stubbed out."""
    web = types.ModuleType("aiohttp.web")
    for name in ("get", "post", "json_response", "Response"):
        setattr(web, name, lambda *a, **k: None)
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = web
    route = lambda *a, **k: (lambda handler: handler)
    server = types.ModuleType("server")
    server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(
        routes=types.SimpleNamespace(get=route, post=route)))
    sys.modules.setdefault("aiohttp", aiohttp)
    sys.modules.setdefault("aiohttp.web", web)
    sys.modules.setdefault("server", server)
    layout.load("canvas", "contextir", "compile", "prompting", "refine", package="mmc")
    for name in ("media", "preview", "refine_local", "refine_skill", "jobs"):
        stub = types.ModuleType(f"mmc.{name}")
        stub.register = lambda *a, **k: None
        sys.modules[f"mmc.{name}"] = stub
    sys.modules["mmc.media"].image_size = lambda *a, **k: (1024, 1024)

    def load(name):
        spec = importlib.util.spec_from_file_location(
            f"mmc.{name}", os.path.join(ROOT, "creator", f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"mmc.{name}"] = module
        spec.loader.exec_module(module)
        return module

    remote = load("refine_remote")
    # The URL given here and no key: the node's own credential file is not
    # read, so a bench run never picks up a hosted endpoint by accident.
    remote._read = lambda: {"url": url, "key": ""}
    return load("refine_routes"), remote


def piece(name, person, scene, target):
    """The blob the panel would post: a pool of two pictures and one member."""
    blob = {
        "version": 2, "render": "chained", "aspect": "16:9",
        "prompt": "a quiet late afternoon in a small flat, painterly light",
        "assets": [
            {"handle": "img-1", "kind": "image", "role": "reference",
             "filename": os.path.basename(person), "takes": "person"},
            {"handle": "img-2", "kind": "image", "role": "reference",
             "filename": os.path.basename(scene), "takes": "scene"},
        ],
        "subjects": [{"handle": name, "from": ["img-1"], "takes": "person"}],
        "segments": [
            {"prompt": f"@{name} walks into the living room from @img-2 and sits down at the table",
             "duration_s": 5, "assets": [], "loras": []},
            {"prompt": "she looks out of the window and says \"it's later than I thought\"",
             "duration_s": 5, "assets": [], "loras": []},
        ],
    }
    if target == "simple":
        blob = {**blob, "prompt": "", "segments": [
            {"prompt": f"@{name} is eating a sandwich", "duration_s": 5, "assets": [], "loras": []}]}
        return {"kind": "segment", "index": 0, "data": blob}
    if target == "timeline":
        return {"kind": "timeline", "data": blob}
    return {"kind": "segment", "index": int(target), "data": blob}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--person", required=True, help="a picture of the cast member")
    parser.add_argument("--scene", required=True, help="a picture of a place")
    parser.add_argument("--name", default="juno", help="the member's handle")
    parser.add_argument("--model", default="qwen3-vl:4b")
    parser.add_argument("--url", default="http://localhost:11434/v1")
    parser.add_argument("--target", default="simple", choices=("simple", "0", "1", "timeline"))
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--dump", action="store_true", help="print the prompt before the reply")
    args = parser.parse_args()

    from PIL import Image

    routes, remote = _load_routes(args.url)
    files = {os.path.basename(args.person): args.person, os.path.basename(args.scene): args.scene}
    routes._picture = lambda asset: Image.open(files[asset.filename]) if asset.kind == "image" else None

    if args.dump:
        real = remote.chat

        def chat(model, system, message, images=(), **kw):
            print(f"===== SYSTEM =====\n{system}\n===== USER =====\n{message}\n===== END =====\n")
            return real(model, system, message, images, **kw)

        remote.chat = chat

    body = piece(args.name, args.person, args.scene, args.target)
    body.update({"backend": "remote", "model": args.model,
                 "temperature": args.temperature, "seed": args.seed})
    if args.max_tokens:
        body["max_tokens"] = args.max_tokens

    started = time.time()
    try:
        out = routes._run(body)
    except Exception as exc:  # noqa: BLE001 — the message is the result
        print(f"FAILED after {time.time() - started:.0f}s: {type(exc).__name__}: {exc}")
        return 1
    print(f"took {time.time() - started:.0f}s, model {args.model}, target {args.target}\n")
    print("SEEN:", out.get("seen"), "\n")
    if out.get("piece"):
        print("PIECE:", out["piece"], "\n")
    for number, shot in enumerate(out["shots"], 1):
        print(f"SHOT {number}:", shot["body"])
        for key, value in (shot.get("sections") or {}).items():
            print(f"  {key}: {value}")
        print()
    for key, value in (out.get("sections") or {}).items():
        print(f"{key}: {value}\n")
    print("SOUND:", out["soundscape"], "\nMUSIC:", out["music"], "\n")
    print("PROBLEMS:")
    for problem in out.get("problems") or []:
        print(" -", problem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
