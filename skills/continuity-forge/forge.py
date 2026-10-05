#!/usr/bin/env python3
"""Make a game's assets on a running ComfyUI with this pack, from a shell.

    python3 skills/continuity-forge/forge.py capabilities
    python3 skills/continuity-forge/forge.py new mygame --mode pixel --target gbstudio --target godot4
    python3 skills/continuity-forge/forge.py plan mygame plan.json
    python3 skills/continuity-forge/forge.py status mygame
    python3 skills/continuity-forge/forge.py import mygame hero hero.png
    python3 skills/continuity-forge/forge.py pull mygame --out ./mygame

The client half of `/continuity/forge/*` (`creator/forge/api.py`, served by
`creator/routes/forge.py`). The bench is the other client, and neither can do
anything the other cannot: `tests/test_forge_parity.py` fails when a route has
no command here. Standard library only; run it with any Python 3.9+, on the
ComfyUI machine or anywhere that can reach its port.

The server is `--url`, else `$COMFY_URL`, else http://127.0.0.1:8188.

stdout is data: paths or names one per line, or with `--json` the server's
whole answer. Progress and sentences go to stderr. A refusal prints the
server's sentence and exits 1; with `--json` the refusal itself — `{problem,
code, …}` — is printed on stdout too, so a caller can branch on the code. A
server that cannot be reached exits 3.
"""

import argparse
import json
import mimetypes
import os
import sys
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
    "import": ["/import"],
    "files": ["/files"],
    "pull": ["/files", "/file"],
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
            path = os.path.join(out, *item["path"].split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
            written.append(path)
        say(f"{len(written)} files into {out}")
        return {"files": written}, lambda a: _lines(*a["files"])
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
