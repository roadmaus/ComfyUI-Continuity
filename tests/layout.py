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

import contextlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

import harness

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The two facts. Everything else in this file, and every suite that imports it,
# is written in terms of these.
PY_ROOT = os.path.join(ROOT, "creator")
WEB_ROOT = os.path.join(ROOT, "web", "creator")

# Where a module lives when it is not simply `PY_ROOT/<name>.py` — the H3
# protocol modules live in the family package now, named by their dotted path
# under the package root. This map is what lets them move without the suites
# that load them having to learn where they went.
MODULES = {
    "contextir": "families.h3.contextir",
    "subjects": "families.h3.subjects",
    "payload": "families.h3.payload",
    "encode": "families.h3.encode",
    "faces": "families.h3.faces",
    "facepass": "families.h3.facepass",
    "hires": "families.h3.hires",
    "h3_segment": "families.h3.segment",
    "refine": "families.h3.refine",
    "ltx25_refine": "families.ltx25.refine",
    "still": "families.h3.still",
    "ltx25_models": "families.ltx25.models",
    "ltx25_sampling": "families.ltx25.sampling",
    "krea2_still": "families.krea2.still",
    "ideogram4_still": "families.ideogram4.still",
    "h3_declare": "families.h3.declare",
    "h3_models": "families.h3.models",
    "h3_grammar": "families.h3.grammar",
    "ltx25_grammar": "families.ltx25.grammar",
    "ltx25_declare": "families.ltx25.declare",
    "registry": "families.registry",
    "manifest": "families.manifest",
    "grammar": "families.grammar",
    "prompting": "families.refine",
}


def js(*parts):
    """A path inside the frontend, e.g. `js("state.js")`, `js("styles")`."""
    return os.path.join(WEB_ROOT, *parts)


def py(name):
    """The file a package module lives in, e.g. `py("compile")`."""
    dotted = MODULES.get(name)
    if dotted:
        return os.path.join(PY_ROOT, *dotted.split(".")) + ".py"
    return os.path.join(PY_ROOT, f"{name}.py")


def skip_without_node():
    """Bow out on a machine with no `node`, the way every mirror suite must."""
    if shutil.which("node") is None:
        harness.skip("node is not installed")


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
        # `from . import contextir` inside a loaded module finds a sibling at
        # `PY_ROOT` through the path above — but a module in `MODULES` moved off
        # that path, so the finder below serves those flat by name. Without it,
        # every suite would have to know which package a dependency moved into,
        # which is exactly what this file exists to know instead.
        sys.meta_path.append(_MovedModules(package))
    holder = sys.modules[package]

    for name in names:
        key = f"{package}.{name}"
        if key not in sys.modules:
            if name in MODULES:
                # A moved module is imported at its real place in the package,
                # so its upward relative imports (`from ... import canvas`)
                # resolve — a flat copy of it could not reach above itself.
                # Registered under the flat name too, so nothing downstream
                # learns where it went.
                module = importlib.import_module(f"{package}.{MODULES[name]}")
                sys.modules[key] = module
            else:
                spec = importlib.util.spec_from_file_location(key, py(name))
                module = importlib.util.module_from_spec(spec)
                # Registered before it is executed: a module that imports a
                # sibling relatively reaches back through `sys.modules` while
                # it runs.
                sys.modules[key] = module
                spec.loader.exec_module(module)
            setattr(holder, name, module)
    return holder


class _MovedModules:
    """Resolves `<package>.<name>` for the names `MODULES` relocated."""

    def __init__(self, package):
        self.package = package

    def find_spec(self, fullname, path=None, target=None):
        prefix, _, name = fullname.rpartition(".")
        if prefix != self.package or name not in MODULES:
            return None
        return importlib.util.spec_from_file_location(fullname, py(name))


_CATALOG_JSON = None


def catalog_json():
    """`families/manifest.catalog()`, dumped once — what the server serves at
    `/continuity/families`, and what `web/creator/manifest.js` loads.

    The frontend's family knowledge lives in this catalog (phase 5), so any
    suite that imports a frontend module needs it in reach: `run()` injects it
    as `globalThis.__MMC_FAMILIES`, and `pack()`'s stub serves it through the
    route so the packed suites exercise the fetch path the browser takes.
    Building it imports the pure Python side — which is the point: the mirror
    is held against the code, not against a fixture that can drift.
    """
    global _CATALOG_JSON
    if _CATALOG_JSON is None:
        _CATALOG_JSON = json.dumps(load("manifest").manifest.catalog())
    return _CATALOG_JSON


# Runs before a suite's script: `web/creator/manifest.js` awaits its catalog at
# import, and under bare node there is no server to fetch it from.
_PRELUDE = ("if (process.env.MMC_FAMILIES) "
            "globalThis.__MMC_FAMILIES = JSON.parse(process.env.MMC_FAMILIES);\n")


def run(script, *args, catalog=None):
    """Run `script` as an ES module under node and parse what it prints.

    `args` reach it as `process.argv[1]` onwards — the mirror's own path first
    by convention, then whatever cases the suite is asking about, JSON-encoded.
    Anything that is not already a string is encoded here, since every suite was
    calling `json.dumps` on the way in.

    `catalog` serves the frontend a catalog other than this install's. Only one
    suite wants it and for one reason: the family-selection plumbing has to be
    provable while there is still one family to select, and the way to prove a
    control reads the family it is given is to give it a second one. Everything
    else takes the real catalog, which is the point of building it from the
    code.

    A non-zero exit is fatal and prints node's stderr: a mirror that will not
    even parse is not a disagreement to be collected alongside the others, it is
    a broken file, and reporting it as one failure among twenty buries it.
    """
    argv = [a if isinstance(a, str) else json.dumps(a) for a in args]
    served = catalog_json() if catalog is None else json.dumps(catalog)
    proc = subprocess.run(
        ["node", "--input-type=module", "--eval", _PRELUDE + script, "--", *argv],
        capture_output=True, text=True,
        env={**os.environ, "MMC_FAMILIES": served})
    if proc.returncode != 0:
        harness.died(f"node failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


# The ComfyUI modules the frontend imports but a bare node has no idea about.
# The pack's own files reach them as `../../scripts/app.js` from `web/creator.js`
# and `../../../scripts/api.js` from a module under `web/creator/`, so both land
# in one `scripts/` directory beside the copied tree.
STUBS = {
    "app.js": "export const app = { registerExtension() {}, extensionManager: null };",
    "api.js": """
import { readFileSync } from "node:fs";
const store = new Map();
globalThis.__userdata = store;
export const api = {
  apiURL: (u) => u,
  addEventListener() {}, removeEventListener() {},
  async fetchApi(url) {
    // The one route with a real body: the family catalog, written beside this
    // stub by layout.pack() — so the packed suites take the same load path the
    // browser does instead of leaning on the __MMC_FAMILIES injection.
    if (String(url).startsWith("/continuity/families")) {
      const body = readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  },
  async getUserData(file) {
    return store.has(file)
      ? { status: 200, json: async () => JSON.parse(store.get(file)) }
      : { status: 404, json: async () => null };
  },
  async storeUserData(file, value) { store.set(file, JSON.stringify(value)); return { status: 200 }; },
  async deleteUserData(file) { store.delete(file); return { status: 204 }; },
};
""",
    "widgets.js": "export const ComfyWidgets = {};",
}


@contextlib.contextmanager
def pack(extra_stubs=None, skip=None):
    """The frontend in a temp tree it can actually be imported from. -> its dir.

    Modules under `web/creator/` import ComfyUI's own `scripts/api.js` by
    relative path, so `node` cannot load one out of the checkout — there is no
    `scripts/` two directories up from it. The tree is copied somewhere that has
    one, stubbed.

    `skip` is passed to `shutil.ignore_patterns`; the style atlas's half a
    thousand stills are the reason it exists.
    """
    work = tempfile.mkdtemp(prefix="mmc-pack-")
    try:
        target = os.path.join(work, "pack")
        shutil.copytree(os.path.join(ROOT, "web"), os.path.join(target, "web"),
                        ignore=shutil.ignore_patterns(*skip) if skip else None)
        scripts = os.path.join(work, "scripts")
        os.makedirs(scripts, exist_ok=True)
        for name, source in {**STUBS, **(extra_stubs or {})}.items():
            with open(os.path.join(scripts, name), "w", encoding="utf-8") as handle:
                handle.write(source)
        # What the stub api serves at /continuity/families.
        with open(os.path.join(scripts, "families.json"), "w", encoding="utf-8") as handle:
            handle.write(catalog_json())
        yield target
    finally:
        shutil.rmtree(work, ignore_errors=True)


def in_pack(script, target, *args):
    """Run `script` with `target` as the working directory, so its relative
    imports of `./web/creator/…` resolve against the copied tree."""
    argv = [a if isinstance(a, str) else json.dumps(a) for a in args]
    proc = subprocess.run(
        ["node", "--input-type=module", "--eval", script, "--", *argv],
        capture_output=True, text=True, cwd=target)
    if proc.returncode != 0:
        harness.died(f"node failed:\n{proc.stderr}")
    return json.loads(proc.stdout)
