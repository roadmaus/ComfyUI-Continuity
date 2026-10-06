#!/usr/bin/env python3
"""Make a game's assets on a running ComfyUI with this pack, from a shell.

    python3 skills/continuity-forge/forge.py capabilities
    python3 skills/continuity-forge/forge.py new mygame --mode pixel --target gbstudio --target godot4
    python3 skills/continuity-forge/forge.py plan mygame plan.json
    python3 skills/continuity-forge/forge.py status mygame
    python3 skills/continuity-forge/forge.py import mygame hero hero.png
    python3 skills/continuity-forge/forge.py pull mygame --out ./mygame
    python3 skills/continuity-forge/forge.py pose mygame import walk walk.fbx --fps 12
    python3 skills/continuity-forge/forge.py pose mygame render walk --out ./walk

The client half of `/continuity/forge/*` (`creator/forge/api.py`, served by
`creator/routes/forge.py`). The bench is the other client, and neither can do
anything the other cannot: `tests/test_forge_parity.py` fails when a route has
no command here. Standard library only; run it with any Python 3.9+, on the
ComfyUI machine or anywhere that can reach its port.

The server is `--url`, else `$COMFY_URL`, else http://127.0.0.1:8188.

stdout is data: paths or names one per line, or with `--json` the server's
whole answer. Progress and sentences go to stderr. A refusal prints the
server's sentence and exits 1; with `--json` the refusal itself — `{problem,
code, …}` — is printed on stdout too, so a caller can branch on the code.
`check`, `export` and `post` exit 2 when they did their work but something
breaks a target's budget (the problems are on stderr, and in the JSON). A
server that cannot be reached exits 3.
"""

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_URL = "http://127.0.0.1:8188"
PREFIX = "/continuity/forge"

# Every command, and the routes it calls. The parity test reads this table and
# fails on any route in `creator/forge/api.py` that no command calls.
COMMANDS = {
    "capabilities": ["/capabilities"],
    "targets": ["/targets"],
    "modes": ["/modes"],
    "schema": ["/schema"],
    "projects": ["/projects"],
    "new": ["/new"],
    "show": ["/show"],
    "style": ["/style"],
    "target": ["/target/add", "/target/rm"],
    "plan": ["/plan"],
    "add": ["/add"],
    "edit": ["/edit"],
    "rm": ["/rm"],
    "status": ["/status"],
    "history": ["/history"],
    "post": ["/post"],
    "check": ["/check"],
    "sheet": ["/sheet", "/file"],
    "export": ["/export", "/files", "/file"],
    "import": ["/import"],
    "files": ["/files"],
    "pull": ["/files", "/file"],
    "poses": ["/poses"],
    "pose": ["/pose/show", "/pose/new", "/pose/paste", "/pose/set", "/pose/rm", "/pose/import",
             "/pose/render", "/pose/job", "/file"],
}


def say(*parts):
    print(*parts, file=sys.stderr, flush=True)


class Refused(Exception):
    def __init__(self, answer):
        super().__init__(answer.get("problem") or answer.get("error") or "refused")
        self.answer = answer


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
                answer = json.loads(body)
            except ValueError:
                answer = {"problem": body.strip() or f"HTTP {err.code}", "code": f"http.{err.code}"}
            if not isinstance(answer, dict):
                answer = {"problem": str(answer), "code": f"http.{err.code}"}
            if err.code == 404 and answer.get("code") is None:
                answer = {"problem": "this server has no /continuity/forge — is the Continuity pack "
                                     "installed, and recent enough?", "code": "server.no_forge"}
            answer.setdefault("code", f"http.{err.code}")
            answer.setdefault("problem", answer.get("error") or f"HTTP {err.code}")
            raise Refused(answer) from None
        except urllib.error.URLError as err:
            say(f"error: cannot reach {self.url} ({err.reason}). Is ComfyUI running there? "
                "Set --url or COMFY_URL.")
            sys.exit(3)

    def get(self, route, **query):
        query = {k: v for k, v in query.items() if v is not None}
        url = f"{self.url}{PREFIX}{route}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
        return self._open(urllib.request.Request(url))

    def get_json(self, route, **query):
        return json.loads(self.get(route, **query))

    def post(self, route, body):
        request = urllib.request.Request(
            f"{self.url}{PREFIX}{route}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        return json.loads(self._open(request))

    def upload(self, path, subfolder="forge"):
        """A local file into the server's input folder -> the name to cite it by."""
        boundary = uuid.uuid4().hex
        name = os.path.basename(path)
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            data = handle.read()
        fields = [("overwrite", "true"), ("subfolder", subfolder)]
        body = b"".join(
            [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
             for k, v in fields]
            + [f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
               f"filename=\"{name}\"\r\nContent-Type: {kind}\r\n\r\n".encode(),
               data, f"\r\n--{boundary}--\r\n".encode()])
        request = urllib.request.Request(
            f"{self.url}/upload/image", data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        answer = json.loads(self._open(request))
        sub = answer.get("subfolder") or ""
        return f"{sub}/{answer['name']}" if sub else answer["name"]


def _read_json_file(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise Refused({"problem": f"cannot read {path}: {exc.strerror}", "code": "client.file"}) from None
    except ValueError as exc:
        raise Refused({"problem": f"{path} is not JSON: {exc}", "code": "client.json"}) from None


def _value(text):
    """A `--set field=VALUE` value: JSON when it parses, text otherwise."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def _settings(pairs, flag):
    out = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise Refused({"problem": f"{flag} takes FIELD=VALUE; got {pair!r}", "code": "client.usage"})
        out[key] = _value(value)
    return out


# ---- printing ----------------------------------------------------------------------


def _lines(*rows):
    for row in rows:
        print(row)


def _print_project(answer):
    project = answer["project"]
    style = project["style"]
    say(f"{project['name']}: {style['mode']}, {len(project['assets'])} assets, "
        f"targets {', '.join(project['targets'])}")
    print(project["name"])


def _print_status(answer):
    counts = answer["counts"]
    say(", ".join(f"{n} {k}" for k, n in counts.items()))
    for row in answer["assets"]:
        flag = "" if row["status"] == "planned" or row["viewed"] else "  (not looked at)"
        print(f"{row['status']:<9} {row['kind']:<10} {row['name']}{flag}")


def _print_problems(problems):
    for p in problems:
        where = f" at tile {tuple(p['at'])}" if "at" in p else ""
        frame = f" frame {p['frame']}" if p.get("frame") else ""
        say(f"problem: {p.get('asset', '')}{frame}{where}: {p['problem']} [{p['code']}]")


def _download(server, project, rel, dest):
    data = server.get("/file", project=project, path=rel)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "wb") as handle:
        handle.write(data)
    return dest


def _local(root, rel):
    """`root/rel` for a path the server named, refused if it would leave `root`.
    The server is trusted to answer, not to choose where this machine writes."""
    parts = rel.replace("\\", "/").split("/")
    if not rel or rel.startswith("/") or any(p in ("", ".", "..") or ":" in p for p in parts):
        raise Refused({"problem": f"the server named a file outside the project: {rel!r}", "code": "client.path"})
    return os.path.join(root, *parts)


def _wait(server, answer):
    """Poll a pose job until a tab has done it. A job a tab never takes fails on
    the server's side within seconds, so this needs no clock of its own."""
    said = None
    while answer["state"] in ("waiting", "claimed"):
        if answer["state"] != said:
            said = answer["state"]
            say("waiting for a ComfyUI tab to take it" if said == "waiting" else "a tab is drawing it")
        time.sleep(0.5)
        answer = server.get_json("/pose/job", job=answer["job"])
    if answer["state"] == "failed":
        raise Refused(answer)
    return answer


def _pose(server, args):
    project, op = args.project, args.op
    if op == "show":
        return server.get_json("/pose/show", project=project, set=args.set), \
            lambda a: print(json.dumps(a["set"], indent=2))

    def named(a):
        print(a["set"]["name"])
    if op == "new":
        body = {"project": project, "set": args.set}
        if getattr(args, "from"):
            body["from"] = getattr(args, "from")
        return server.post("/pose/new", body), named
    if op == "paste":
        body = {"project": project, "set": args.set, "data": _read_json_file(args.file),
                "replace": args.replace}
        if args.fps is not None:
            body["fps"] = args.fps
        return server.post("/pose/paste", body), named
    if op == "set":
        bones = {}
        for spec in args.bones:
            bone, sep, value = spec.partition("=")
            numbers = value.split(",")
            if not sep or len(numbers) != 3 or not all(_is_number(n) for n in numbers):
                raise Refused({"problem": f"a bone is BONE=X,Y,Z in degrees; got {spec!r}", "code": "client.usage"})
            bones[bone] = [float(n) for n in numbers]
        return server.post("/pose/set", {"project": project, "set": args.set, "frame": args.frame,
                                         "bones": bones}), named
    if op == "rm":
        answer = server.post("/pose/rm", {"project": project, "set": args.set})

        def show(a):
            say(f"it is kept in {a['kept']}")
            print(a["removed"])
        return answer, show
    if op == "import":
        name = args.clip
        if os.path.isfile(name):
            say(f"uploading {name}")
            name = server.upload(name)
        answer = _wait(server, server.post("/pose/import", {
            "project": project, "set": args.set, "file": name, "fps": args.fps, "replace": args.replace}))

        def show(a):
            say(f"{a['frames']} frames")
            print(args.set)
        return answer, show
    if op == "render":
        body = {"project": project, "set": args.set}
        for key in ("width", "height", "yaw", "pitch"):
            if getattr(args, key) is not None:
                body[key] = getattr(args, key)
        if args.frame:
            body["frames"] = args.frame
        answer = server.post("/pose/render", body)
        if answer["state"] != "done":
            say(f"drawing {len(answer['drawn'])} of {len(answer['frames'])} frames")
            answer = _wait(server, answer)
        out = args.out or f"{args.set}-poses"
        answer["local"] = [_download(server, project, f["path"], os.path.join(out, f"{f['frame']:03d}.png"))
                           for f in answer["frames"]]
        return answer, lambda a: _lines(*a["local"])
    raise AssertionError(op)


def problem_count(command, answer):
    if command == "check":
        return answer.get("count", 0)
    if command in ("export", "post"):
        return len(answer.get("problems", []))
    return 0


# ---- the commands -------------------------------------------------------------------


def run(server, args):
    """One command -> the server's answer (a dict) and how to print it."""
    command = args.command
    if command == "capabilities":
        answer = server.get_json("/capabilities")

        def show(a):
            _lines(*(f"kind    {k['id']:<11} {k['help']}" for k in a["kinds"]))
            _lines(*(f"mode    {m['id']:<11} {m['help']}" for m in a["modes"]))
            _lines(*(f"target  {t['id']:<11} {t['label']}" for t in a["targets"]))
            _lines(*(f"family  {f['id']:<11} {'still' if f.get('still') else 'video'}" for f in a["families"]))
        return answer, show
    if command == "targets":
        return server.get_json("/targets"), lambda a: _lines(
            *(f"{t['id']:<10} {t['label']} — {t['help']}" for t in a["targets"]))
    if command == "modes":
        return server.get_json("/modes"), lambda a: _lines(
            *(f"{m['id']:<8} {m['help']} ({' → '.join(m['chain'])})" for m in a["modes"]))
    if command == "schema":
        # A schema is data whichever way it is asked for.
        return server.get_json("/schema", kind=args.kind), lambda a: print(json.dumps(a, indent=2))
    if command == "projects":
        return server.get_json("/projects"), lambda a: _lines(
            *(f"{p['name']:<20} {p['mode']:<8} {p['assets']:>4} assets  {', '.join(p['targets'])}"
              for p in a["projects"]))
    if command == "new":
        style = {}
        for key in ("clause", "seed", "family"):
            if getattr(args, key) is not None:
                style[key] = getattr(args, key)
        body = {"project": args.project, "targets": args.target, "style": style}
        if args.mode:
            body["mode"] = args.mode
        return server.post("/new", body), _print_project
    if command == "show":
        answer = server.get_json("/show", project=args.project)

        def show(a):
            _print_project(a)
            _print_status(a["status"])
        return answer, show
    if command == "style":
        style = _settings(args.set, "--set")
        for key in ("clause", "mode", "seed", "family", "grid"):
            if getattr(args, key) is not None:
                style[key] = getattr(args, key)
        if args.texel_density is not None:
            style["texel_density"] = args.texel_density
        if args.palette is not None:
            style["palette"] = [c if c.startswith("#") else f"#{c}" for c in args.palette.replace(",", " ").split()]
        if args.reference:
            style["references"] = args.reference
        if args.lora:
            loras = []
            for spec in args.lora:
                name, sep, strength = spec.rpartition(":")
                loras.append({"name": name, "strength": float(strength)} if sep and _is_number(strength)
                             else {"name": spec})
            style["loras"] = loras
        if not style:
            answer = server.get_json("/show", project=args.project)
            return answer, lambda a: print(json.dumps(a["project"]["style"], indent=2))
        return server.post("/style", {"project": args.project, "style": style}), _print_project
    if command == "target":
        route = "/target/add" if args.op == "add" else "/target/rm"
        return server.post(route, {"project": args.project, "target": args.target}), _print_project
    if command == "plan":
        answer = server.post("/plan", {"project": args.project, "plan": _read_json_file(args.file)})

        def show(a):
            for key in ("added", "changed", "unchanged"):
                _lines(*(f"{key:<9} {name}" for name in a[key]))
            if a["style"]:
                say("the style changed")
            if a["targets"]:
                say("targets added: " + ", ".join(a["targets"]))
        return answer, show
    if command == "add":
        entry = _read_json_file(args.file) if args.file else {}
        entry.update(_settings(args.set, "--set"))
        if args.kind:
            entry["kind"] = args.kind
        if args.name:
            entry["name"] = args.name
        return server.post("/add", {"project": args.project, "asset": entry}), \
            lambda a: print(a["asset"]["name"])
    if command == "edit":
        changes = _read_json_file(args.file) if args.file else {}
        changes.update(_settings(args.set, "--set"))
        if not changes:
            raise Refused({"problem": "say what to change: --set FIELD=VALUE, or a JSON file",
                           "code": "client.usage"})
        return server.post("/edit", {"project": args.project, "asset": args.asset, "changes": changes}), \
            lambda a: print(a["asset"]["name"])
    if command == "rm":
        answer = server.post("/rm", {"project": args.project, "asset": args.asset})

        def show(a):
            if a["kept"]:
                say(f"its files are kept in {a['kept']}")
            print(a["removed"])
        return answer, show
    if command == "status":
        return server.get_json("/status", project=args.project), _print_status
    if command == "history":
        return server.get_json("/history", project=args.project, asset=args.asset), lambda a: _lines(
            *(f"{v['version']:>4}  {v['at'] or '—':<25} {v['source'] or '—':<7} {v['path']}" for v in a["versions"]))
    if command == "post":
        body = {"project": args.project, "asset": args.asset, "steps": args.steps}
        if args.target:
            body["target"] = args.target
        answer = server.post("/post", body)

        def show(a):
            say(f"{a['target']}: " + " → ".join(a["steps"]))
            _print_problems(a["problems"])
            _lines(*a["files"])
        return answer, show
    if command == "check":
        body = {"project": args.project}
        if args.target:
            body["target"] = args.target
        if args.asset:
            body["assets"] = args.asset
        answer = server.post("/check", body)

        def show(a):
            for report in a["targets"]:
                for row in report["assets"]:
                    for p in row["problems"]:
                        at = ",".join(map(str, p["at"])) if "at" in p else "-"
                        print(f"{report['target']}\t{row['asset']}\t{p.get('frame') or '-'}\t{at}\t"
                              f"{p['code']}\t{p['problem']}")
                    if row["overlay"]:
                        say(f"{report['target']} {row['asset']}: overlay {row['overlay']}")
                for skip in report["skipped"]:
                    say(f"{report['target']} {skip['asset']}: skipped, {skip['why']}")
            say(f"{a['count']} problem{'s' if a['count'] != 1 else ''}")
        return answer, show
    if command == "sheet":
        answer = server.post("/sheet", {"project": args.project, "asset": args.asset})
        answer["local"] = _download(server, args.project, answer["path"], args.out or f"{args.asset}-sheet.png")
        return answer, lambda a: print(a["local"])
    if command == "export":
        body = {"project": args.project, "target": args.target}
        if args.asset:
            body["assets"] = args.asset
        answer = server.post("/export", body)
        if args.pull:
            prefix = f"build/{args.target}/"
            listing = server.get_json("/files", project=args.project, under=prefix.rstrip("/"))
            answer["pulled"] = [
                _download(server, args.project, item["path"],
                          _local(args.pull, item["path"][len(prefix):]))
                for item in listing["files"]
                if item["path"].startswith(prefix) and "/check/" not in item["path"]
                and not item["path"].rsplit("/", 1)[-1].startswith(".")]

        def show(a):
            for skip in a["skipped"]:
                say(f"{skip['asset']}: skipped, {skip['why']}")
            _print_problems(a["problems"])
            _lines(*(a.get("pulled") or a["written"]))
        return answer, show
    if command == "import":
        names = []
        for spec in args.files:
            if os.path.isfile(spec):
                say(f"uploading {spec}")
                names.append(server.upload(spec))
            else:
                names.append(spec)
        answer = server.post("/import", {"project": args.project, "asset": args.asset, "files": names})
        return answer, lambda a: _lines(
            *(f"assets/{a['asset']['kind']}/{a['asset']['name']}/masters/{f}" for f in a["asset"]["masters"]))
    if command == "files":
        return server.get_json("/files", project=args.project, under=args.under,
                               versions="1" if args.versions else None), \
            lambda a: _lines(*(f["path"] for f in a["files"]))
    if command == "pull":
        listing = server.get_json("/files", project=args.project, under=args.under)
        out = args.out or args.project
        written = []
        for item in listing["files"]:
            data = server.get("/file", project=args.project, path=item["path"])
            path = _local(out, item["path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
            written.append(path)
        say(f"{len(written)} files into {out}")
        return {"files": written}, lambda a: _lines(*a["files"])
    if command == "poses":
        return server.get_json("/poses", project=args.project), lambda a: _lines(
            *(f"{p['name']:<20} {p['frames']:>4} frames  {p['fps']} fps" for p in a["sets"]))
    if command == "pose":
        return _pose(server, args)
    raise AssertionError(command)


def _is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def parser():
    top = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Start with `capabilities`. Write a plan rather than many `add` calls.")
    top.add_argument("--url", default=os.environ.get("COMFY_URL") or DEFAULT_URL,
                     help=f"the ComfyUI server (default $COMFY_URL or {DEFAULT_URL})")
    top.add_argument("--json", action="store_true", help="print the server's whole answer as JSON")
    sub = top.add_subparsers(dest="command", required=True, metavar="command")
    # The two global options are accepted after the command too — `status
    # mygame --json` is how an agent writes it. SUPPRESS keeps a command that
    # does not repeat them from resetting what was given before it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    def command(name, help):
        return sub.add_parser(name, help=help, description=help, parents=[common])

    command("capabilities", "kinds, modes, targets and families this server has")
    command("targets", "the engine targets a project can export to")
    command("modes", "the render modes, and the post-chain each gives")
    command("schema", "the JSON schema of a kind's recipe").add_argument("kind")
    command("projects", "every project on the server")

    p = command("new", "make a project")
    p.add_argument("project")
    p.add_argument("--mode", help="painted, flat, toon, pixel or pbr")
    p.add_argument("--target", action="append", default=[], help="a target id; repeat for more")
    p.add_argument("--clause", help="the style clause every prompt ends with")
    p.add_argument("--seed", type=int, help="the project seed")
    p.add_argument("--family", help="the still family that makes its pictures")

    command("show", "a project's style, targets and asset status").add_argument("project")

    p = command("style", "change a project's style; with no options, print it")
    p.add_argument("project")
    p.add_argument("--clause")
    p.add_argument("--mode")
    p.add_argument("--seed", type=int)
    p.add_argument("--family")
    p.add_argument("--grid", type=int, help="master pixels per art pixel (pixel mode)")
    p.add_argument("--palette", help="colours as hex, comma or space separated")
    p.add_argument("--texel-density", type=float)
    p.add_argument("--reference", action="append", help="a style reference picture; repeat for more")
    p.add_argument("--lora", action="append", metavar="NAME[:STRENGTH]")
    p.add_argument("--set", action="append", metavar="FIELD=VALUE", help="any style field; VALUE may be JSON")

    p = command("target", "add or remove an export target")
    p.add_argument("project")
    p.add_argument("op", choices=("add", "rm"))
    p.add_argument("target")

    p = command("plan", "merge a plan (JSON) into a project, by asset name; idempotent")
    p.add_argument("project")
    p.add_argument("file")

    p = command("add", "add one asset")
    p.add_argument("project")
    p.add_argument("file", nargs="?", help="the recipe as JSON")
    p.add_argument("--kind")
    p.add_argument("--name")
    p.add_argument("--set", action="append", metavar="FIELD=VALUE")

    p = command("edit", "change some fields of one asset")
    p.add_argument("project")
    p.add_argument("asset")
    p.add_argument("file", nargs="?", help="the changes as JSON")
    p.add_argument("--set", action="append", metavar="FIELD=VALUE")

    p = command("rm", "remove an asset; its files move to .versions/")
    p.add_argument("project")
    p.add_argument("asset")

    command("status", "planned / made / exported / stale, per asset").add_argument("project")

    p = command("history", "the versions an asset has been through")
    p.add_argument("project")
    p.add_argument("asset")

    p = command("post", "run post-steps on an asset for one target; the frames go to variants/post/")
    p.add_argument("project")
    p.add_argument("asset")
    p.add_argument("steps", nargs="+", help="matte, bleed, baseline, colormatch, pixelize, …")
    p.add_argument("--target", help="the target to convert for (default: the project's first)")

    p = command("check", "every target's budgets against every made asset; overlays for what breaks")
    p.add_argument("project")
    p.add_argument("--target", help="only this target")
    p.add_argument("--asset", action="append", help="only this asset; repeat for more")

    p = command("sheet", "a contact sheet PNG of an asset: masters, then each target's frames")
    p.add_argument("project")
    p.add_argument("asset")
    p.add_argument("--out", help="where to save it (default ./<asset>-sheet.png)")

    p = command("export", "write a target's engine files into build/<target>/")
    p.add_argument("project")
    p.add_argument("target")
    p.add_argument("--asset", action="append", help="only this asset; repeat for more")
    p.add_argument("--pull", metavar="DIR", help="then download build/<target>/ into DIR")

    p = command("import", "pictures, meshes or sounds become an asset's masters")
    p.add_argument("project")
    p.add_argument("asset")
    p.add_argument("files", nargs="+", help="local files (uploaded) or names already on the server")

    p = command("files", "list a project's files")
    p.add_argument("project")
    p.add_argument("--under", help="only under this folder, e.g. build/godot4")
    p.add_argument("--versions", action="store_true", help="include .versions/")

    p = command("pull", "download a project, or one folder of it")
    p.add_argument("project")
    p.add_argument("--under", help="only this folder, e.g. build/godot4")
    p.add_argument("--out", help="where to write (default ./<project>)")

    command("poses", "a project's pose sets").add_argument("project")

    p = command("pose", "make, change and draw pose sets; import and render need an open ComfyUI tab")
    p.add_argument("project")
    ops = p.add_subparsers(dest="op", required=True, metavar="op")

    def op(name, help):
        q = ops.add_parser(name, help=help, description=help, parents=[common])
        q.add_argument("set")
        return q

    op("show", "a set as JSON: body, fps, one pose per frame")
    q = op("new", "a set of one rest pose, or a copy")
    q.add_argument("--from", metavar="SET[/FRAME]", help="copy a whole set, or one frame of it")
    q = op("paste", "a set from Pose Studio's pose_data, or poses as JSON")
    q.add_argument("file")
    q.add_argument("--fps", type=float)
    q.add_argument("--replace", action="store_true", help="paste over a set that exists")
    q = op("set", "turn bones of one frame, in degrees")
    q.add_argument("frame", type=int)
    q.add_argument("bones", nargs="+", metavar="BONE=X,Y,Z")
    op("rm", "remove a set; it moves to .versions/")
    q = op("import", "an FBX clip (Mixamo) retargeted onto the mannequin, a pose per sampled frame")
    q.add_argument("clip", help="a local .fbx (uploaded) or a name already on the server")
    q.add_argument("--fps", type=float, default=12, help="the rate the clip is sampled at (default 12)")
    q.add_argument("--replace", action="store_true", help="import over a set that exists")
    q = op("render", "mannequin PNGs of a set's frames, downloaded")
    q.add_argument("--frame", action="append", type=int, help="only this frame; repeat for more")
    q.add_argument("--width", type=int, help="pixels (default 484, a cell of the 4-frame grid)")
    q.add_argument("--height", type=int, help="pixels (default 1088)")
    q.add_argument("--yaw", type=float, help="turn the figure this many degrees, for another direction")
    q.add_argument("--pitch", type=float, help="degrees the camera looks down on the figure: 0 side-on "
                   "(default), ~30 a three-quarter RPG, up to 89 top-down; negative looks up")
    q.add_argument("--out", help="where to save them (default ./<set>-poses)")
    return top


def main(argv=None):
    args = parser().parse_args(argv)
    server = Server(args.url)
    try:
        answer, show = run(server, args)
    except Refused as refused:
        say(f"error: {refused}")
        if args.json:
            print(json.dumps(refused.answer, indent=2))
        return 1
    if args.json:
        print(json.dumps(answer, indent=2))
    else:
        show(answer)
    return 2 if problem_count(args.command, answer) else 0


if __name__ == "__main__":
    sys.exit(main())
