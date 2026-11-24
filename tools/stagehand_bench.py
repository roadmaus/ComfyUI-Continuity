#!/usr/bin/env python3
"""Run the blockout's agent headless: the real `stagehand.js` and its real tools
in a Firefox without a window, against the refiner server saved in the pack.

    python3 tools/stagehand_bench.py --out DIR --brief "a lighthouse..."
    python3 tools/stagehand_bench.py --out DIR --fake calls.json

Nothing is rendered or queued. `--brief` may be given again for a next message.
`--fake` takes a list of `[tool, arguments]` and asks no model. DIR gets the log,
the pictures the model looked at, and the piece it made (`piece.json`).
"""

import argparse
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import layout  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--brief", action="append", default=[])
parser.add_argument("--fake")
parser.add_argument("--model", default="Ternary-Bonsai-2-27B-PTQ1_0.gguf")
parser.add_argument("--piece", help="a piece to start from, as JSON")
parser.add_argument("--comfy", default=os.path.dirname(os.path.dirname(ROOT)))
parser.add_argument("--minutes", type=float, default=30)
args = parser.parse_args()

sys.path.append(args.comfy)
pkg = layout.load("prompting", "refine_remote", "stagehand")
# ComfyUI's `folder_paths` reads the command line, which is this script's.
sys.argv = sys.argv[:1]
OUT = os.path.abspath(args.out)
os.makedirs(OUT, exist_ok=True)

fake = json.load(open(args.fake)) if args.fake else None


def scripted(model, messages, tools):
    at = sum(1 for message in messages if message["role"] == "assistant")
    message = {"role": "assistant", "content": "done"}
    if at < len(fake):
        name, given = fake[at]
        message = {"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{at}", "type": "function", "function": {"name": name, "arguments": json.dumps(given)}}]}
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


CATALOG = re.sub(r"\}[^}]*$", "}", layout.catalog_json())
API = ("const ok=(b)=>new Response(JSON.stringify(b),{status:200,headers:{'content-type':'application/json'}});"
       "const CATALOG=" + CATALOG + ";export const api={async fetchApi(u,i){"
       "if(u==='/continuity/stagehand')return fetch(u,i);"
       "return u.startsWith('/continuity/families')?ok(CATALOG):ok({});},apiURL:(u)=>u,"
       "getUserData:async()=>new Response('{}',{status:404}),storeUserData:async()=>{},"
       "addEventListener(){},removeEventListener(){}};")
APP = ("export const app={graph:{_nodes:[]},extensionManager:{setting:{get(){}}},"
       "ui:{settings:{getSettingValue(){}}}};globalThis.app=app;")
PAGE = """<!doctype html><body><script type="module">
const tell = (body) => fetch('/told', { method: 'POST', body: JSON.stringify(body) });
let t = null;
try {
  await (await import('/ext/web/creator/manifest.js')).loadManifest?.();
  const S = await import('/ext/web/creator/state.js');
  const { Stagehand } = await import('/ext/web/creator/stagehand.js');
  t = S.parseTimeline(PIECE);
  S.syncTimeline(t);
  const hand = new Stagehand({ model: MODEL, timeline: () => t, apply: (next) => { t = next; }, told: tell });
  for (const brief of BRIEFS) { const said = await hand.send(brief); await tell({ kind: 'said', said, usage: hand.usage }); }
} catch (exc) { await tell({ kind: 'error', error: String(exc), stack: exc.stack }); }
await tell({ kind: 'end', piece: t && (await import('/ext/web/creator/state.js')).serializeTimeline(t) });
</script>"""
piece = open(args.piece).read() if args.piece else "{}"
for key, value in (("PIECE", piece), ("MODEL", args.model), ("BRIEFS", args.brief or ["go"])):
    PAGE = PAGE.replace(key, json.dumps(value).replace("</", "<\\/"), 1)
ended = threading.Event()
# Stopped from outside, it still closes its Firefox.
signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def out(self, kind, body, status=200):
        self.send_response(status)
        self.send_header("content-type", kind)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        file = os.path.realpath(os.path.join(ROOT, path[len("/ext/"):]))
        if path == "/":
            self.out("text/html;charset=utf-8", PAGE.encode())
        elif path == "/scripts/api.js":
            self.out("text/javascript", API.encode())
        elif path == "/scripts/app.js":
            self.out("text/javascript", APP.encode())
        elif path.startswith("/ext/web/") and file.startswith(os.path.join(ROOT, "web") + os.sep) and os.path.isfile(file):
            self.out("text/javascript", open(file, "rb").read())
        else:
            self.out("text/plain", b"", 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if self.path == "/continuity/stagehand":
            try:
                answer = pkg.stagehand.turn(body["session"], body["model"], body["messages"], body["tools"],
                                            body["seen"], root=OUT, ask=scripted if fake is not None else None)
                self.out("application/json", json.dumps(answer).encode())
            except Exception as exc:  # noqa: BLE001 — told to the page, as the route does
                self.out("application/json", json.dumps({"error": str(exc)}).encode(), 400)
            return
        if body["kind"] == "end":
            if body["piece"]:
                with open(os.path.join(OUT, "piece.json"), "w") as handle:
                    handle.write(body["piece"])
            ended.set()
        elif body["kind"] == "result":
            text = body["content"] if isinstance(body["content"], str) else " ".join(p.get("text", "(a picture)") for p in body["content"])
            print(f"  -> {body['name']}: {text[:600]}", flush=True)
        elif body["kind"] == "reply":
            for call in body["message"].get("tool_calls") or []:
                print(f"{call['function']['name']} {call['function']['arguments'][:200]}", flush=True)
        else:
            print(json.dumps(body, ensure_ascii=False)[:1500], flush=True)
        self.out("text/plain", b"")


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as profile:
    firefox = subprocess.Popen(["firefox-esr", "--headless", "--no-remote", "--profile", profile,
                                f"http://127.0.0.1:{server.server_port}/"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not ended.wait(args.minutes * 60):
            print(f"stopped after {args.minutes:g} minutes")
    finally:
        firefox.terminate()
        firefox.wait()
# Not `layout`'s own ending, which reports a test run.
sys.stdout.flush()
os._exit(0 if ended.is_set() else 1)
