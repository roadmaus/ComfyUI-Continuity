"""A stand-in ComfyUI host for looking at the frontend without ComfyUI.

    python3 tools/ui_harness/server.py [port]        # default 8188

Serves this checkout's real `web/` at `/extensions/continuity/`, two shims for
the host modules the frontend imports (`/scripts/app.js`, `/scripts/api.js`),
and the real family catalog at `/continuity/families`, built from the Python
side exactly as the test suites build it. Every other route answers 404, so
anything that needs a backend (settings, model and LoRA lists, renders) shows
its empty or error state. Drop a JSON file in `stubs/` to answer a route:
`/continuity/settings` is read from `stubs/continuity__settings.json`.

Nothing here is imported by the pack; it needs no torch and no ComfyUI.
"""

import atexit
import http.server
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WEB = os.path.join(ROOT, "web")
STUBS = os.path.join(HERE, "stubs")
TYPES = {"js": "text/javascript", "mjs": "text/javascript", "html": "text/html",
         "css": "text/css", "json": "application/json", "png": "image/png",
         "webp": "image/webp", "svg": "image/svg+xml"}


def catalog():
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import harness
    import layout
    # The suites' exit report has nothing to say about a server.
    atexit.unregister(harness._report)
    return layout.catalog_json().encode()


CATALOG = catalog()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def file(self, base, relative):
        path = os.path.realpath(os.path.join(base, relative))
        if not path.startswith(os.path.realpath(base) + os.sep) or not os.path.isfile(path):
            return self.answer(404, b'{"error": "not found"}', "application/json")
        with open(path, "rb") as handle:
            self.answer(200, handle.read(), TYPES.get(path.rsplit(".", 1)[-1], "application/octet-stream"))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/extensions/continuity/"):
            return self.file(WEB, path[len("/extensions/continuity/"):])
        if path.startswith("/scripts/"):
            return self.file(HERE, path.lstrip("/"))
        if path in ("/", "/index.html"):
            return self.file(HERE, "index.html")
        if path == "/continuity/families":
            return self.answer(200, CATALOG, "application/json")
        stub = path.strip("/").replace("/", "__") + ".json"
        if os.path.isfile(os.path.join(STUBS, stub)):
            return self.file(STUBS, stub)
        print(f"unstubbed: {self.command} {self.path}", flush=True)
        self.answer(404, b'{"error": "no stub"}', "application/json")

    do_POST = do_GET


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8188
    print(f"http://127.0.0.1:{port}/", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
