"""The `/continuity/forge/*` surface, as a table.

The bench and the CLI are two clients of one HTTP surface, and neither may do
anything the other cannot (spec §2, §11). Keeping the surface as data is what
makes that checkable: `ROUTES` is every route the forge serves, `routes/forge.py`
registers exactly these on ComfyUI's server, and `tests/test_forge_parity.py`
fails when one of them has no command in `skills/continuity-forge/forge.py` —
and runs the CLI against these same handlers behind a standard-library server.

A handler is `handler(host, params) -> answer`. `params` is the query string
for a GET and the JSON body for a POST. The answer is a JSON-able dict, or a
`File` to send as bytes. Refusals are `ForgeError`s, answered as
`{problem, code, …}` with the error's status.

`Host` is what a handler needs from the machine: where projects live, how a
ComfyUI file name becomes a path, which families exist. On a running ComfyUI
`routes/forge.py` builds it from `folder_paths` and `media`; the suites build
one on a temporary folder.
"""

from . import kinds, project as projects, targets
from .problems import ForgeError

PREFIX = "/continuity/forge"


class Host:
    def __init__(self, base, resolve=None, families=None):
        self.base = base
        self._resolve = resolve
        self._families = families

    def resolve(self, filename):
        """A ComfyUI file name (input/, or `name [output]`) -> an absolute path."""
        if self._resolve is None:
            raise ForgeError("this server cannot read ComfyUI files", "host.resolve")
        return self._resolve(filename)

    def families(self):
        return self._families() if self._families else []


class File:
    """A handler's answer that is a file rather than JSON."""

    def __init__(self, path):
        self.path = path


def _text(params, key, required=True):
    value = params.get(key)
    if value is None or value == "":
        if required:
            raise ForgeError(f"say which {key}", "request.missing", field=key)
        return None
    if not isinstance(value, str):
        raise ForgeError(f"{key} must be text", "request.field", field=key)
    return value


def _flag(params, key):
    value = params.get(key, False)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def _object(params, key):
    value = params.get(key)
    if not isinstance(value, dict):
        raise ForgeError(f"{key} must be a JSON object", "request.field", field=key)
    return value


# ---- discovery -------------------------------------------------------------------


def capabilities(host, params):
    """What this machine can make: the kinds, the modes, the targets and the
    still families. Engines and optional packs join this as they land."""
    return {"kinds": [{"id": k, "help": v["help"]} for k, v in kinds.KINDS.items()],
            **targets.catalogue(), "families": host.families()}


def list_targets(host, params):
    return {"targets": targets.catalogue()["targets"]}


def list_modes(host, params):
    return {"modes": targets.catalogue()["modes"]}


def schema(host, params):
    return kinds.schema(_text(params, "kind"))


# ---- projects ---------------------------------------------------------------------


def list_projects(host, params):
    return {"projects": projects.listing(host.base)}


def new_project(host, params):
    chosen = params.get("targets") or []
    if not isinstance(chosen, list):
        raise ForgeError("targets must be a list", "request.field", field="targets")
    style = params.get("style") or {}
    project = projects.create(host.base, _text(params, "project"), params.get("mode"), chosen, style)
    return {"project": project}


def show(host, params):
    name = _text(params, "project")
    project = projects.load(host.base, name)
    return {"project": project, "status": projects.status(host.base, name)}


def set_style(host, params):
    return {"project": projects.set_style(host.base, _text(params, "project"), _object(params, "style"))}


def add_target(host, params):
    return {"project": projects.add_target(host.base, _text(params, "project"), _text(params, "target"))}


def remove_target(host, params):
    return {"project": projects.remove_target(host.base, _text(params, "project"), _text(params, "target"))}


# ---- assets -----------------------------------------------------------------------


def plan(host, params):
    return projects.merge_plan(host.base, _text(params, "project"), _object(params, "plan"))


def add_asset(host, params):
    return {"asset": projects.add_asset(host.base, _text(params, "project"), _object(params, "asset"))}


def edit_asset(host, params):
    return {"asset": projects.edit_asset(host.base, _text(params, "project"), _text(params, "asset"),
                                         _object(params, "changes"))}


def remove_asset(host, params):
    return projects.remove_asset(host.base, _text(params, "project"), _text(params, "asset"))


def status(host, params):
    return projects.status(host.base, _text(params, "project"))


def history(host, params):
    return projects.history(host.base, _text(params, "project"), _text(params, "asset"))


# ---- moving files ----------------------------------------------------------------


def import_files(host, params):
    """ComfyUI files (input/, or annotated output/) become an asset's masters.

    The CLI uploads a local file to ComfyUI's input folder first, as the render
    client does, and names it here; the bench names what is already there.
    """
    names = params.get("files")
    if not isinstance(names, list) or not names or any(not isinstance(n, str) for n in names):
        raise ForgeError("say which files to import", "request.missing", field="files")
    sources = {}
    for name in names:
        try:
            path = host.resolve(name)
        except ForgeError:
            raise
        except Exception as exc:  # noqa: BLE001 — media.MediaError and friends, as a sentence
            raise ForgeError(str(exc), "import.missing", file=name) from None
        filename = name.split(" [", 1)[0].replace("\\", "/").rsplit("/", 1)[-1]
        if filename in sources:
            raise ForgeError(f"two files are called {filename}", "import.duplicate", file=filename)
        sources[filename] = path
    return {"asset": projects.put_masters(host.base, _text(params, "project"), _text(params, "asset"),
                                          sources)}


def list_files(host, params):
    return {"files": projects.files(host.base, _text(params, "project"),
                                    _text(params, "under", required=False) or "", _flag(params, "versions"))}


def read_file(host, params):
    return File(projects.file_path(host.base, _text(params, "project"), _text(params, "path")))


# Every route the forge serves: method, path under PREFIX, handler. The CLI's
# command table is held against this list by `tests/test_forge_parity.py`.
ROUTES = (
    ("GET", "/capabilities", capabilities),
    ("GET", "/targets", list_targets),
    ("GET", "/modes", list_modes),
    ("GET", "/schema", schema),
    ("GET", "/projects", list_projects),
    ("POST", "/new", new_project),
    ("GET", "/show", show),
    ("POST", "/style", set_style),
    ("POST", "/target/add", add_target),
    ("POST", "/target/rm", remove_target),
    ("POST", "/plan", plan),
    ("POST", "/add", add_asset),
    ("POST", "/edit", edit_asset),
    ("POST", "/rm", remove_asset),
    ("GET", "/status", status),
    ("GET", "/history", history),
    ("POST", "/import", import_files),
    ("GET", "/files", list_files),
    ("GET", "/file", read_file),
)


def call(host, method, path, params):
    """Run the handler for `method path` -> `(status, answer)`.

    The one place a ForgeError becomes an answer, shared by the aiohttp routes
    and the suites' stand-in server, so both refuse in the same words.
    """
    for want_method, want_path, handler in ROUTES:
        if method == want_method and path == PREFIX + want_path:
            try:
                return 200, handler(host, params)
            except ForgeError as problem:
                return problem.status, problem.answer()
    return 404, {"problem": f"no forge route {method} {path}", "code": "route.missing"}
