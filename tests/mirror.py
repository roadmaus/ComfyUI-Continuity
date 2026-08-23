"""Where the two sides of a mirrored rule live, and how to run the JS one.

Eight suites check that a rule written twice — once in Python because the node
compiles with it, once in JavaScript because the body draws it live — still says
the same thing in both places. Every one of them opened with the same forty
lines: derive the repo root, spell out `js/minimax_creator/<file>.js`, skip if
`node` is missing, fake a package so the pure modules can be imported without
ComfyUI, and shell out to `node --input-type=module`.

Written eight times, it drifted eight ways: three spellings of the node flag
(`-e`, `--eval`, and `--eval` with the arguments in a different position) and
four names for the fake package (`mmc`, `mmcpkg`, `mmc_outputs`, and none at
all). None of that was a decision anybody made.

It also meant the layout of the repo was written into eight files. That is the
part this exists to fix: **the paths are here and nowhere else**, so moving the
frontend or moving a module into a family package is one edit in this file
rather than eight edits that have to agree.

`skip_without_node()` must be called before anything else — the module-level
import of a mirror is the point where a machine without `node` should bow out,
and it exits rather than raising so `harness.py` reports a skip and not a crash.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The frontend, relative to the repo root. One tuple, because the whole reason
# this module exists is that the tree moves and the suites should not care.
WEB = ("js", "minimax_creator")

# Where a mirrored Python module is found, by its logical name. Anything absent
# is looked up beside the repo root, which is where every one of them lives
# today; the map is what lets a module move into a family package without the
# suite that mirrors it having to learn where it went.
MODULES = {}


def js(name):
    """The path to a mirror module, e.g. `js("state.js")`."""
    return os.path.join(ROOT, *WEB, name)


def skip_without_node():
    """Bow out on a machine with no `node`, the way every mirror suite must."""
    if shutil.which("node") is None:
        print("skipped: node is not installed")
        sys.exit(0)


def load(*names, package="mmcmirror"):
    """Import pure package modules without ComfyUI. -> the package holding them.

    The modules mirrored here import each other relatively (`from . import
    canvas`), so they cannot be loaded as loose files — they need a package to
    be relative *to*. That package is faked rather than real because importing
    the real one runs `__init__.py`, which registers the server routes and pulls
    in torch.

    Load order is the caller's: a module is executed when it is named, so a
    module must be named after whatever it imports. What comes back is the
    package, so the caller binds the two or three it actually asserts against
    and the rest are simply dependencies that had to be present:

        pkg = load("canvas", "contextir", "compile")
        compiler, canvas_mod = pkg.compile, pkg.canvas
    """
    if package not in sys.modules:
        holder = types.ModuleType(package)
        holder.__path__ = [ROOT]
        sys.modules[package] = holder
    holder = sys.modules[package]

    for name in names:
        key = f"{package}.{name}"
        if key not in sys.modules:
            path = MODULES.get(name, os.path.join(ROOT, f"{name}.py"))
            spec = importlib.util.spec_from_file_location(key, path)
            module = importlib.util.module_from_spec(spec)
            # Registered before it is executed: a module that imports a sibling
            # relatively reaches back through `sys.modules` while it runs.
            sys.modules[key] = module
            setattr(holder, name, module)
            spec.loader.exec_module(module)
    return holder


def run(script, *args):
    """Run `script` as an ES module under node and parse what it prints.

    `args` reach it as `process.argv[1]` onwards — the mirror's own path first
    by convention, then whatever cases the suite is asking about, JSON-encoded.
    Anything that is not already a string is encoded here, since every suite was
    calling `json.dumps` on the way in.

    A non-zero exit is fatal and prints node's stderr: a mirror that will not
    even parse is not a disagreement to be collected alongside the others, it is
    a broken file, and reporting it as one failure among twenty buries it.
    """
    argv = [a if isinstance(a, str) else json.dumps(a) for a in args]
    proc = subprocess.run(
        ["node", "--input-type=module", "--eval", script, "--", *argv],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"node failed:\n{proc.stderr}")
        sys.exit(1)
    return json.loads(proc.stdout)
