"""The Open folder route: what it hands the OS, and what it refuses (#23).

Lifted out of `server_routes.py` the way `test_assets.py` lifts the walk — the
route's own text, with `folder_paths`, aiohttp's `web` and `subprocess.Popen`
stood in for — because the server cannot be imported without ComfyUI and the
route has no opinion about it.

    python3 tests/test_reveal.py
"""

import ast
import asyncio
import os
import pathlib
import sys
import tempfile

import layout
from harness import check, passed


class _FolderPaths:
    output = ""
    input = ""

    @staticmethod
    def get_output_directory():
        return _FolderPaths.output

    @staticmethod
    def get_input_directory():
        return _FolderPaths.input

    @staticmethod
    def is_within_directory(root, path):
        root = os.path.realpath(root)
        target = os.path.realpath(path)
        return target == root or target.startswith(root + os.sep)


class _Web:
    @staticmethod
    def json_response(body, status=200):
        return (status, body)


LAUNCHED = []


class _Subprocess:
    DEVNULL = -3
    fail = None

    @staticmethod
    def Popen(argv, **kwargs):
        if _Subprocess.fail:
            raise _Subprocess.fail
        LAUNCHED.append(list(argv))


def _load():
    source = pathlib.Path(layout.py("server_routes")).read_text(encoding="utf-8")
    wanted = {"_reveal_command", "_picker_root", "_clean_subfolder", "reveal_folder"}
    picked = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            node.decorator_list = []          # the PromptServer route hook
            picked.append(node)
    missing = wanted - {n.name for n in picked}
    assert not missing, f"server_routes no longer defines {missing}"
    namespace = {"os": os, "sys": sys, "folder_paths": _FolderPaths, "web": _Web,
                 "subprocess": _Subprocess}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "server_routes.py", "exec"), namespace)
    return namespace


NS = _load()


class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def call(body):
    LAUNCHED.clear()
    return asyncio.run(NS["reveal_folder"](_Request(body)))


# ---- the argv is the platform's own -----------------------------------------

want = {"darwin": "open", "win32": "explorer", "linux": "xdg-open"}[
    "darwin" if sys.platform == "darwin" else "win32" if sys.platform.startswith("win") else "linux"]
check("the command is this platform's file manager", NS["_reveal_command"]("/x")[0], want)
check("...handed the folder itself", NS["_reveal_command"]("/x")[-1], "/x")

# ---- the two roots, and the folder being browsed ----------------------------

with tempfile.TemporaryDirectory() as tmp:
    _FolderPaths.output = os.path.join(tmp, "output")
    _FolderPaths.input = os.path.join(tmp, "input")
    os.makedirs(os.path.join(_FolderPaths.output, "day one"))
    os.makedirs(_FolderPaths.input)
    real_out = os.path.realpath(_FolderPaths.output)

    status, body = call({"root": "output"})
    check("the output root opens", (status, body["path"]), (200, real_out))
    check("...and is what was launched", LAUNCHED, [NS["_reveal_command"](real_out)])

    status, body = call({"root": "output", "subfolder": "day one"})
    check("a shelf opens as its directory", (status, body["path"]),
          (200, os.path.join(real_out, "day one")))

    status, body = call({"root": "input", "subfolder": ""})
    check("the input root opens too", (status, body["path"]), (200, os.path.realpath(_FolderPaths.input)))

    status, body = call({"root": "temp"})
    check("a root the picker does not browse is refused", (status, LAUNCHED), (400, []))

    status, body = call({"root": "output", "subfolder": "../input"})
    check("a path that climbs out is refused before anything launches", (status, LAUNCHED), (400, []))

    status, body = call({"root": "output", "subfolder": ".hidden"})
    check("a dotted name is refused as a bad name", (status, LAUNCHED), (400, []))

    status, body = call({"root": "output", "subfolder": "never made"})
    check("a shelf that is not there is refused", (status, LAUNCHED), (404, []))

    # A headless box: nothing to hand the folder to. The path is still the
    # answer, and the status says the machine, not the request, is the problem.
    _Subprocess.fail = FileNotFoundError("xdg-open")
    status, body = call({"root": "output"})
    _Subprocess.fail = None
    check("no file manager: the path comes back with the refusal",
          (status, body["path"], "no file manager" in body["error"]), (501, real_out, True))

passed("the Open folder route opens the right folder and refuses the rest")
