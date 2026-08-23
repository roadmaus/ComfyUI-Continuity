"""Where this pack's code lives, and how to load either half of it.

Most of the suite needs a path into the package: the pure Python modules, so
they can be imported without booting ComfyUI, and the frontend modules, so node
can be pointed at them. Every suite derived the repo root and then spelled the
layout out again — `os.path.join(ROOT, "compile.py")`, `os.path.join(ROOT,
"js", "minimax_creator", "state.js")` — which put the directory structure in
twenty-five files that all had to agree.

They did not. The eight mirror suites alone carried three spellings of node's
eval flag (`-e`, `--eval`, and `--eval` with the arguments in another position)
and four names for the fake package they load modules into (`mmc`, `mmcpkg`,
`mmc_outputs`, and none at all). None of that was a decision anybody made.

**The layout is `PY_ROOT` and `WEB_ROOT` and nothing else.** Moving the
frontend, or moving a module into a family package, is an edit here rather than
twenty-five edits that have to be kept in step — which is what makes the
multi-family refactor a change to the code instead of a change to the code and
its whole test suite at once.

`skip_without_node()` must be called before anything else in a suite that shells
out: the import is the point where a machine without node should bow out, and it
exits rather than raising so `harness.py` reports a skip and not a crash.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The two facts. Everything else in this file, and every suite that imports it,
# is written in terms of these.
PY_ROOT = os.path.join(ROOT, "creator")
WEB_ROOT = os.path.join(ROOT, "web", "creator")

# Where a module is found when it is not simply `PY_ROOT/<name>.py`. Empty today;
# this is what lets a module move into a family package without the suites that
# load it having to learn where it went.
MODULES = {}


def js(*parts):
    """A path inside the frontend, e.g. `js("state.js")`, `js("styles")`."""
    return os.path.join(WEB_ROOT, *parts)


def py(name):
    """The file a package module lives in, e.g. `py("compile")`."""
    return MODULES.get(name, os.path.join(PY_ROOT, f"{name}.py"))


def skip_without_node():
    """Bow out on a machine with no `node`, the way every mirror suite must."""
    if shutil.which("node") is None:
        print("skipped: node is not installed")
        sys.exit(0)


def load(*names, package="mmcpkg"):
    """Import pure package modules without ComfyUI. -> the package holding them.

    The modules import each other relatively (`from . import canvas`), so they
    cannot be loaded as loose files — they need a package to
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
        holder.__path__ = [PY_ROOT]
        sys.modules[package] = holder
    holder = sys.modules[package]

    for name in names:
        key = f"{package}.{name}"
        if key not in sys.modules:
            path = py(name)
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
