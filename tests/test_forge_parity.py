"""The forge's CLI can do everything its routes can, and says it the same way.

    python3 tests/test_forge_parity.py
    UPDATE_GOLDENS=1 python3 tests/test_forge_parity.py   # rewrite the goldens

Spec §11.6. Two halves:

**Coverage.** Every route in `creator/forge/api.py`'s `ROUTES` — the list
`routes/forge.py` serves — must be called by some command in the CLI's
`COMMANDS` table, and every route a command names must exist. A capability
added to the bench without a command fails here.

**Behaviour.** The CLI is run, as a subprocess, against the real handlers behind
a standard-library HTTP server standing in for ComfyUI (with its `/upload/image`
too). Each command is checked for its stdout, its `--json` answer and its exit
code, and a refusal for its sentence on stderr and its code on stdout. `schema`
and `status` answers are compared against goldens in `tests/golden/`, because
agents learn those shapes and a change to them is a change to a contract.

No ComfyUI, no numpy: runs on a bare Python 3.9+.
"""

import base64
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import threading
import types
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

import goldens
import layout
from harness import FAILURES, check

ROOT = os.path.dirname(layout.PY_ROOT)
CLI = os.path.join(ROOT, "skills", "continuity-forge", "forge.py")

package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
for name in ("problems", "kinds", "targets", "style", "project", "manifest", "joints", "pose", "api"):
    spec = importlib.util.spec_from_file_location(f"forgepkg.{name}",
                                                  os.path.join(layout.PY_ROOT, "forge", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"forgepkg.{name}"] = module
    spec.loader.exec_module(module)
api = sys.modules["forgepkg.api"]

spec = importlib.util.spec_from_file_location("forge_cli", CLI)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

# ---- coverage ---------------------------------------------------------------------

served = {path for _, path, _ in api.ROUTES}
check("a tab's routes are not a client's", served & {path for _, path, _ in api.TAB_ROUTES}, set())
called = {route for routes in cli.COMMANDS.values() for route in routes}
check("every route has a command", sorted(served - called), [])
check("every command calls a route that exists", sorted(called - served), [])
check("the CLI's prefix is the server's", cli.PREFIX, api.PREFIX)
commands = set(cli.parser()._subparsers._group_actions[0].choices)
for rel in ("../x", "a/../../b", "/etc/x", "c:/x", ""):
    try:
        cli._local("out", rel)
        FAILURES.append(f"the CLI wrote outside its folder for {rel!r}")
    except cli.Refused as refusal:
        check(f"a server path {rel!r} is refused", refusal.answer["code"], "client.path")
check("a server path inside is joined", cli._local("out", "a/b.png"), os.path.join("out", "a", "b.png"))
check("every command in the table is a command", sorted(set(cli.COMMANDS) ^ commands), [])

# ---- a stand-in ComfyUI ---------------------------------------------------------------

work = tempfile.mkdtemp(prefix="forge-parity-")
base = os.path.join(work, "output", "continuity", "forge")
inputs = os.path.join(work, "input")
os.makedirs(inputs)


def resolve(filename):
    path = os.path.realpath(os.path.join(inputs, filename))
    if not path.startswith(os.path.realpath(inputs) + os.sep) or not os.path.isfile(path):
        raise FileNotFoundError(f"{filename!r} is not in the input folder")
    return path


class Tab:
    """A browser tab, as far as a pose job can tell: it hears the announcement,
    claims the job, and answers with what it drew (blank PNGs of the asked size)
    or the poses it retargeted (one per tenth of a second of a pretend clip)."""

    def __init__(self):
        self.open = False
        self.heard = []

    def count(self):
        return 1 if self.open else 0

    def announce(self, event, data):
        self.heard.append(event)
        threading.Thread(target=self._work, args=(data["job"],), daemon=True).start()

    def _work(self, job):
        status, task = api.call(host, "POST", api.PREFIX + "/pose/claim", {"job": job, "tab": "t1"})
        if status != 200:
            return
        if task["kind"] == "render":
            answer = {"frames": ["data:image/png;base64," + base64.b64encode(
                png(task["width"], task["height"])).decode() for _ in task["frames"]]}
        else:
            answer = {"poses": [{"bones": {"thigh_l": [i * 10, 0, 0]}, "camera": {"posX": 1}}
                                for i in range(3)]}
        api.call(host, "POST", api.PREFIX + "/pose/done", {"job": job, "tab": "t1", **answer})


def png(width, height):
    """A white PNG, written by hand: this suite runs without PIL."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"\xff" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class Queue:
    """ComfyUI's queue, as far as a make can tell. Nothing ever lands — this
    suite has no PIL to collect with (`test_forge_make.py` does that) — so a
    render stays queued until the suite says how it ended."""

    def __init__(self):
        self.bodies = []
        self.states = {}

    def render(self, body):
        self.bodies.append(body)
        prompt_id = f"p{len(self.bodies)}"
        self.states[prompt_id] = ("queued", None)
        return {"prompt_id": prompt_id, "speed": "native"}

    def state(self, prompt_id):
        return self.states.get(prompt_id, ("unknown", None))


tab = Tab()
queue = Queue()
host = api.Host(base, resolve, lambda: [{"id": "qwen21", "still": True}], tab.count, tab.announce,
                queue.render, queue.state)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _answer(self, method, params):
        status, answer = api.call(host, method, urlsplit(self.path).path, params)
        if isinstance(answer, api.File):
            with open(answer.path, "rb") as handle:
                return self._send(200, handle.read(), "application/octet-stream")
        self._send(status, answer)

    def do_GET(self):
        self._answer("GET", dict(parse_qsl(urlsplit(self.path).query)))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        if self.path == "/upload/image":
            return self._upload(body)
        # The guard every POST route sits behind (`guard.same_origin`).
        if self.headers.get("Content-Type") != "application/json":
            return self._send(415, {"error": "send application/json"})
        self._answer("POST", json.loads(body))

    def _upload(self, body):
        boundary = self.headers["Content-Type"].split("boundary=", 1)[1].encode()
        fields, filename, data = {}, None, None
        for part in body.split(b"--" + boundary):
            head, _, value = part.partition(b"\r\n\r\n")
            name = re.search(rb'name="([^"]+)"', head)
            if not name:
                continue
            value = value[:-2] if value.endswith(b"\r\n") else value
            found = re.search(rb'filename="([^"]+)"', head)
            if found:
                filename, data = found.group(1).decode(), value
            else:
                fields[name.group(1).decode()] = value.decode()
        sub = fields.get("subfolder", "")
        os.makedirs(os.path.join(inputs, sub), exist_ok=True)
        with open(os.path.join(inputs, sub, filename), "wb") as handle:
            handle.write(data)
        self._send(200, {"name": filename, "subfolder": sub, "type": "input"})


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{server.server_address[1]}"


def forge(*args, json_out=False):
    """Run the CLI -> (exit code, stdout, stderr); stdout parsed when json_out."""
    argv = [sys.executable, CLI, "--url", URL, *args] + (["--json"] if json_out else [])
    done = subprocess.run(argv, capture_output=True, text=True, cwd=work, timeout=60)
    out = done.stdout
    if json_out and out.strip():
        out = json.loads(out)
    return done.returncode, out, done.stderr


def ok(label, *args, json_out=False):
    code, out, err = forge(*args, json_out=json_out)
    check(f"{label}: exit code", code, 0)
    if code:
        FAILURES.append(f"{label}: stderr {err.strip()!r}")
    return out


def golden(name, data):
    path = os.path.join(goldens.GOLDEN_DIR, f"forge_{name}.json")
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if goldens.UPDATE or not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return
    with open(path, encoding="utf-8") as handle:
        check(f"golden {name}", handle.read() == text, True)


# ---- discovery -----------------------------------------------------------------------

caps = ok("capabilities", "capabilities", json_out=True)
check("capabilities name the kinds", "sprite" in [k["id"] for k in caps["kinds"]], True)
check("and the families", caps["families"], [{"id": "qwen21", "still": True}])
text = ok("capabilities as text", "capabilities")
check("text capabilities are lines", "target  gbstudio" in text, True)
check("targets", "gbstudio" in ok("targets", "targets"), True)
check("modes", "pixel" in ok("modes", "modes"), True)
for kind in ("sprite", "tile", "sound"):
    golden(f"schema_{kind}", ok(f"schema {kind}", "schema", kind, json_out=True))
code, out, err = forge("schema", "level", json_out=True)
check("an unknown kind exits 1", code, 1)
check("with its code on stdout", out.get("code") if isinstance(out, dict) else out, "asset.kind")
check("and its sentence on stderr", "is not a kind of asset" in err, True)

# ---- a project, end to end ---------------------------------------------------------

check("new prints the name", ok("new", "new", "mygame", "--mode", "pixel", "--target", "gbstudio",
                                "--target", "godot4", "--seed", "11").strip(), "mygame")
code, out, err = forge("new", "mygame", json_out=True)
check("a second new is refused", (code, out["code"]), (1, "project.exists"))
check("projects", ok("projects", "projects").split()[0], "mygame")

plan = {"assets": [
    {"kind": "character", "name": "hero", "prompt": "a small knight with a red plume", "seed": 7},
    {"kind": "sprite", "name": "hero-walk", "of": "hero", "frame": [16, 16],
     "animations": [{"name": "walk", "frames": 4, "fps": 8, "loop": True}]},
    {"kind": "tile", "name": "grass", "prompt": "short grass", "tile": [8, 8]},
]}
with open(os.path.join(work, "plan.json"), "w") as handle:
    json.dump(plan, handle)
check("plan prints what it added", ok("plan", "plan", "mygame", "plan.json").split(),
      ["added", "hero", "added", "hero-walk", "added", "grass"])
again = ok("plan again", "plan", "mygame", "plan.json", json_out=True)
check("a plan applied twice is unchanged", (again["added"], again["changed"]), ([], []))

check("add", ok("add", "add", "mygame", "--kind", "icon", "--name", "coin", "--set", "icon=[8,8]").strip(), "coin")
check("edit", ok("edit", "edit", "mygame", "coin", "--set", "prompt=a gold coin").strip(), "coin")
code, out, err = forge("edit", "mygame", "coin", "--set", "icon=[0,8]", json_out=True)
check("a bad edit is refused with its field", (code, out["code"], out["field"]), (1, "recipe.field", "icon"))

check("style prints the name", ok("style", "style", "mygame", "--clause", "1-bit pixel art").strip(), "mygame")
check("style with no options prints the style",
      json.loads(ok("style show", "style", "mygame"))["clause"], "1-bit pixel art")
ok("target add", "target", "mygame", "add", "love")
check("target rm", ok("target rm", "target", "mygame", "rm", "love").strip(), "mygame")

with open(os.path.join(work, "hero.png"), "wb") as handle:
    handle.write(b"\x89PNG stand-in")
check("import uploads and prints the master's path",
      ok("import", "import", "mygame", "hero", "hero.png").strip(),
      "assets/character/hero/masters/hero.png")
status = ok("status", "status", "mygame")
check("status says what is made and not looked at", "made      character  hero  (not looked at)" in status, True)
check("status lists planned assets", "planned   tile       grass" in status, True)
answer = ok("status --json", "status", "mygame", json_out=True)
for row in answer["assets"]:
    row["made"] = row["made"] and "<time>"
golden("status", answer)
shown = ok("show", "show", "mygame", json_out=True)
check("show carries the project and its status", sorted(shown), ["project", "status"])

check("files lists the master", "assets/character/hero/masters/hero.png" in ok("files", "files", "mygame"), True)
pulled = ok("pull", "pull", "mygame", "--under", "assets", "--out", "pulled").split()
check("pull writes what files lists", [os.path.relpath(p, "pulled") for p in pulled],
      [os.path.join("assets", "character", "hero", "masters", "hero.png"),
       os.path.join("assets", "character", "hero", "recipe.json")])
with open(os.path.join(work, "pulled", "assets", "character", "hero", "masters", "hero.png"), "rb") as handle:
    check("and the bytes are the file's", handle.read(), b"\x89PNG stand-in")

ok("import again", "import", "mygame", "hero", "hero.png")
check("history lists the replaced set", len(ok("history", "history", "mygame", "hero").splitlines()), 1)
check("rm prints the asset", ok("rm", "rm", "mygame", "coin").strip(), "coin")

# ---- making ------------------------------------------------------------------------

code, out, err = forge("make", "mygame", "--missing", "--dry-run")
check("a dry run of nothing makeable still succeeds", (code, out), (0, ""))
check("a dry run skips what cannot be made, and says why",
      ("hero-walk: skipped" in err, "make.kind" in err, "grass: skipped" in err), (True, True, True))
check("a dry run queues nothing", queue.bodies, [])
code, out, err = forge("make", "mygame", "grass", json_out=True)
check("a named asset that cannot be made", (code, out["code"]), (1, "make.seamless"))
ok("edit a tile to be made", "edit", "mygame", "grass", "--set", "seamless=none")
queued = ok("make --no-wait", "make", "mygame", "grass", "--no-wait", json_out=True)
check("make queues one take", [t["asset"] for t in queued["takes"]], ["grass"])
check("...as one render", len(queue.bodies), 1)
take = queued["takes"][0]["take"]
check("jobs lists it as queued", ok("jobs", "jobs", "mygame").split()[:3], ["queued", "grass", take])
check("status says it is being made", ok("status for making", "status", "mygame", json_out=True)
      ["assets"][2]["making"], take)
queue.states["p1"] = ("failed", "KSampler: out of memory")
code, out, err = forge("wait", "mygame", take)
check("wait on a failed take exits 2", code, 2)
check("and prints the queue's sentence", "grass: failed — KSampler: out of memory" in err, True)
check("wait with nothing out", ok("wait idle", "wait", "mygame").strip(), "")

code, out, err = forge("status", "nothere", json_out=True)
check("a missing project", (code, out["code"]), (1, "project.missing"))
code, out, err = forge("import", "mygame", "hero", "not-a-file.png", json_out=True)
check("an import of nothing", (code, out["code"]), (1, "import.missing"))

# ---- poses ------------------------------------------------------------------------

check("pose new prints the set", ok("pose new", "pose", "mygame", "new", "stand").strip(), "stand")
check("a new set is one rest pose", json.loads(ok("pose show", "pose", "mygame", "show", "stand"))["poses"],
      [{"bones": {}, "bonePositions": {}, "modelRotation": [0.0, 0.0, 0.0]}])
ok("pose set", "pose", "mygame", "set", "stand", "0", "upperarm_l=0,0,-60", "head=10,0,0")
check("pose set turns those bones", json.loads(ok("pose show", "pose", "mygame", "show", "stand"))["poses"][0]["bones"],
      {"head": [10.0, 0.0, 0.0], "upperarm_l": [0.0, 0.0, -60.0]})
code, out, err = forge("pose", "mygame", "set", "stand", "0", "tail=1,2,3", json_out=True)
check("a bone the mannequin lacks is refused", (code, out["code"], out["bones"]), (1, "pose.bone", ["tail"]))
code, out, err = forge("pose", "mygame", "set", "stand", "4", "head=1,2,3", json_out=True)
check("a frame the set lacks is refused", (code, out["code"]), (1, "pose.frame"))

studio = {"schema_version": 3, "mesh": {"age": 30, "gender": 1, "show_genitals": False},
          "poses": [{"bones": {"head": [5, 0, 0]}, "camera": {"posX": 0}, "ikEffectorPositions": {}}],
          "timeline": {"fps": 24}}
with open(os.path.join(work, "studio.json"), "w") as handle:
    json.dump(studio, handle)
pasted = ok("pose paste", "pose", "mygame", "paste", "nod", "studio.json", json_out=True)["set"]
check("a paste keeps Pose Studio's body and rate, and only what draws the figure",
      (pasted["body"]["age"], pasted["body"]["gender"], pasted["fps"], pasted["poses"]),
      (30, 1, 24, [{"bones": {"head": [5.0, 0.0, 0.0]}, "bonePositions": {}, "modelRotation": [0.0, 0.0, 0.0]}]))
code, out, err = forge("pose", "mygame", "paste", "nod", "studio.json", json_out=True)
check("a paste over a set is refused without --replace", (code, out["code"]), (1, "set.exists"))
ok("pose paste --replace", "pose", "mygame", "paste", "nod", "studio.json", "--replace")
ok("pose new --from", "pose", "mygame", "new", "nod2", "--from", "nod/0")
check("poses lists the sets", [line.split()[0] for line in ok("poses", "poses", "mygame").splitlines()],
      ["nod", "nod2", "stand"])

code, out, err = forge("pose", "mygame", "render", "stand", json_out=True)
check("a render with no tab open is refused at once", (code, out["code"]), (1, "pose.no_tab"))
tab.open = True
drawn = ok("pose render", "pose", "mygame", "render", "stand", "--width", "64", "--height", "128",
           "--out", "stand").split()
check("render downloads a PNG per frame", drawn, [os.path.join("stand", "000.png")])
with open(os.path.join(work, drawn[0]), "rb") as handle:
    check("of the size asked for", struct.unpack(">II", handle.read()[16:24]), (64, 128))
heard = len(tab.heard)
again = ok("pose render again", "pose", "mygame", "render", "stand", "--width", "64", "--height", "128",
           "--out", "stand", json_out=True)
check("a frame already drawn is not drawn again", (len(tab.heard), again["job"], again["drawn"]), (heard, None, []))
turned = ok("pose render turned", "pose", "mygame", "render", "stand", "--width", "64", "--height", "128",
            "--yaw", "90", "--out", "side", json_out=True)
check("another direction is another drawing", (len(tab.heard), len(turned["drawn"])), (heard + 1, 1))
looked = ok("pose render pitched", "pose", "mygame", "render", "stand", "--width", "64", "--height", "128",
            "--pitch", "30", "--out", "above", json_out=True)
check("a camera looking down is another drawing, and says its pitch",
      (len(tab.heard), len(looked["drawn"]), looked["pitch"]), (heard + 2, 1, 30.0))
code, out, err = forge("pose", "mygame", "render", "stand", "--pitch", "90", json_out=True)
check("straight down is refused", (code, out["code"]), (1, "pose.pitch"))

with open(os.path.join(work, "walk.fbx"), "wb") as handle:
    handle.write(b"Kaydara FBX Binary  stand-in")
check("pose import prints the set", ok("pose import", "pose", "mygame", "import", "walk", "walk.fbx").strip(), "walk")
walk = json.loads(ok("pose show walk", "pose", "mygame", "show", "walk"))
check("an import keeps a pose per frame, and where it came from",
      (len(walk["poses"]), walk["poses"][2]["bones"], walk["source"]),
      (3, {"thigh_l": [20.0, 0.0, 0.0]}, {"clip": "walk.fbx"}))
code, out, err = forge("pose", "mygame", "import", "walk", "walk.fbx", json_out=True)
check("an import over a set is refused without --replace", (code, out["code"]), (1, "set.exists"))
views = ok("pose render views", "pose", "mygame", "render", "stand", "--width", "64", "--height", "128",
           "--views", "0,90", "--out", "views").split()
check("views draw each frame from each side, named by yaw",
      views, [os.path.join("views", "000-yaw0.png"), os.path.join("views", "000-yaw90.png")])

# ---- posing by joint, keys, flip ------------------------------------------------------

words = ok("joints", "joints")
check("joints lists the vocabulary, a line a joint", any(line.startswith("shoulder_l/_r") for line in words.splitlines()),
      True)
ok("pose keys", "pose", "mygame", "keys", "stand", "0", "4:ease-in-out", "--length", "8", "--loop")
ok("pose set by joint", "pose", "mygame", "set", "stand", "4", "shoulder_l.raise=150", "elbow_l.bend=20",
   "hand_l=fist", "--mirror")
angles = ok("pose show --joints", "pose", "mygame", "show", "stand", "--joints", "--frame", "4").splitlines()
check("show --joints reads a frame back in the same words",
      [line.split()[1:4] for line in angles if line.split()[1] in ("shoulder_l", "shoulder_r")],
      [["shoulder_l", "raise", "150"], ["shoulder_r", "raise", "150"]])
stand = json.loads(ok("pose show stand", "pose", "mygame", "show", "stand"))
check("keys, a length and a loop", (len(stand["poses"]), [k["frame"] for k in stand["keys"]], stand["loop"]),
      (8, [0, 4], True))
code, out, err = forge("pose", "mygame", "set", "stand", "0", "elbow_l.bend=200", json_out=True)
check("a joint past its limit is refused with its range", (code, out["code"], out["high"]), (1, "pose.limit", 150))
code, out, err = forge("pose", "mygame", "set", "stand", "0", "elbow_l", json_out=True)
check("a word that is none of the three is refused by the client", (code, out["code"]), (1, "client.usage"))
ok("pose flip", "pose", "mygame", "flip", "stand", "4", "--to", "6")
stand = json.loads(ok("pose show stand", "pose", "mygame", "show", "stand"))
check("flip writes the mirrored frame, which becomes a key", [k["frame"] for k in stand["keys"]], [0, 4, 6])
ok("pose keys --clear", "pose", "mygame", "keys", "stand", "--clear")

check("pose rm", ok("pose rm", "pose", "mygame", "rm", "nod2").strip(), "nod2")
tab.open = False

# ---- post, check, sheet, export (these need numpy and PIL on the server) ----------

try:
    import numpy as np
    from PIL import Image
except ImportError:
    np = None
if np is not None:
    knight = np.zeros((256, 512, 4), np.uint8)
    knight[40:220, 60:200] = (200, 40, 40, 255)
    knight[40:220, 316:456] = (40, 40, 200, 255)
    Image.fromarray(knight, "RGBA").save(os.path.join(work, "knight.png"))
    ok("add knight", "add", "mygame", "--kind", "sprite", "--name", "knight", "--set", "frame=[16,16]",
       "--set", 'animations=[{"name":"idle","frames":2}]')
    ok("import knight", "import", "mygame", "knight", "knight.png")

    posted = ok("post", "post", "mygame", "knight", "baseline", "--target", "godot4").split()
    check("post prints the frames it kept", posted,
          ["assets/sprite/knight/variants/post/godot4/idle_0.png",
           "assets/sprite/knight/variants/post/godot4/idle_1.png"])
    code, out, err = forge("post", "mygame", "knight", "sharpen", json_out=True)
    check("an unknown step is refused", (code, out["code"]), (1, "post.step"))

    check("a clean check prints nothing on stdout", ok("check", "check", "mygame", "--asset", "knight").strip(), "")
    ok("edit knight off the tile grid", "edit", "mygame", "knight", "--set", "frame=[12,12]")
    code, out, err = forge("check", "mygame", "--target", "gbstudio", "--asset", "knight")
    check("a failing check exits 2", code, 2)
    check("and prints one tab-separated line per problem",
          out.splitlines()[0].split("\t")[:5], ["gbstudio", "knight", "idle_0", "-", "budget.grid"])
    check("with the overlay on stderr", "overlay build/gbstudio/check/knight.png" in err, True)
    code, out, err = forge("check", "mygame", "--target", "gbstudio", "--asset", "knight", json_out=True)
    check("check --json carries the count", (code, out["count"]), (2, 2))
    ok("edit knight back", "edit", "mygame", "knight", "--set", "frame=[16,16]")

    sheet = ok("sheet", "sheet", "mygame", "knight", "--out", "knight-sheet.png").strip()
    check("sheet downloads the PNG and prints where", sheet, "knight-sheet.png")
    with open(os.path.join(work, sheet), "rb") as handle:
        check("and it is a PNG", handle.read(8), b"\x89PNG\r\n\x1a\n")

    pulled = ok("export --pull", "export", "mygame", "godot4", "--asset", "knight", "--pull", "game").split()
    check("export --pull writes the engine files locally", sorted(os.path.relpath(p, "game") for p in pulled),
          ["knight.json", "knight.png", "knight.tres"])
    code, out, err = forge("export", "mygame", "godot4", json_out=True)
    check("an export that skips assets still succeeds", code, 0)
    check("and says which, and why", {s["asset"]: s["code"] for s in out["skipped"]}["hero"], "build.unreadable")
    code, out, err = forge("export", "mygame", "love", json_out=True)
    check("exporting to a target the project lacks", (code, out["code"]), (1, "project.target"))

# ---- the server is the CLI's only way in ------------------------------------------

code, _, err = forge("--url", "http://127.0.0.1:9", "projects")
check("an unreachable server exits 3", code, 3)
check("and says where it looked", "cannot reach" in err, True)

server.shutdown()
