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
ComfyUI file name becomes a path, which families exist, how many browser tabs
are connected and how to tell them something. On a running ComfyUI
`routes/forge.py` builds it from `folder_paths`, `media` and the PromptServer;
the suites build one on a temporary folder.

`TAB_ROUTES` are the other half of a pose job (`pose.py`): what a browser tab
calls to take a job and hand back what it drew. They are served like the rest
but are not a capability a client has, so the parity test does not ask the CLI
for a command that calls them.
"""

from . import kinds, pose as poses, project as projects, targets
from .problems import ForgeError

PREFIX = "/continuity/forge"


class Host:
    def __init__(self, base, resolve=None, families=None, tabs=None, announce=None):
        self.base = base
        self._resolve = resolve
        self._families = families
        self._tabs = tabs
        self._announce = announce

    def tabs(self):
        """How many ComfyUI tabs are connected to the websocket."""
        return self._tabs() if self._tabs else 0

    def announce(self, event, data):
        """Tell every connected tab something, on ComfyUI's websocket."""
        if self._announce:
            self._announce(event, data)

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


# ---- post, check, look, export ----------------------------------------------------
#
# These import numpy and PIL, so they are imported here rather than at module
# scope: the storage routes above stay loadable on a bare Python.


def _names(params, key):
    value = params.get(key)
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        value = [v for v in value.split(",") if v]
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ForgeError(f"{key} must be a list of names", "request.field", field=key)
    return value


def post(host, params):
    from . import review

    steps = _names(params, "steps")
    if not steps:
        raise ForgeError("say which post-steps to run", "request.missing", field="steps")
    return review.post(host.base, _text(params, "project"), _text(params, "asset"), steps,
                       _text(params, "target", required=False))


def check(host, params):
    from . import review

    return review.check(host.base, _text(params, "project"), _text(params, "target", required=False),
                        _names(params, "assets"))


def sheet(host, params):
    from . import review

    return review.sheet(host.base, _text(params, "project"), _text(params, "asset"))


def export(host, params):
    from . import export as exporting

    return exporting.export(host.base, _text(params, "project"), _text(params, "target"),
                            _names(params, "assets"))


# ---- poses --------------------------------------------------------------------------


def list_poses(host, params):
    return {"sets": poses.listing(host.base, _text(params, "project"))}


def show_pose(host, params):
    return {"set": poses.load(host.base, _text(params, "project"), _text(params, "set"))}


def new_pose(host, params):
    """A new set: one rest pose, or copied from `from` (`walk`, or `walk/3`)."""
    project = _text(params, "project")
    source = _text(params, "from", required=False)
    frames, body, fps = poses.copy_from(host.base, project, source) if source else (None, None, 12)
    return {"set": poses.create(host.base, project, _text(params, "set"), frames, fps, body)}


def paste_pose(host, params):
    """Pose Studio's `pose_data`, or poses written by hand, as a set."""
    frames, body, fps = poses.from_paste(params.get("data"))
    if params.get("fps") is not None:
        fps = params["fps"]
    return {"set": poses.create(host.base, _text(params, "project"), _text(params, "set"), frames,
                                fps or 12, body, replace=_flag(params, "replace"))}


def set_pose(host, params):
    return {"set": poses.set_bones(host.base, _text(params, "project"), _text(params, "set"),
                                   params.get("frame"), _object(params, "bones"))}


def remove_pose(host, params):
    return poses.remove(host.base, _text(params, "project"), _text(params, "set"))


def import_pose(host, params):
    """An FBX clip (a ComfyUI input file) retargeted onto the mannequin, in a tab."""
    project = _text(params, "project")
    name = _text(params, "set")
    filename = _text(params, "file")
    try:
        host.resolve(filename)
    except ForgeError:
        raise
    except Exception as exc:  # noqa: BLE001 — as in import_files
        raise ForgeError(str(exc), "import.missing", file=filename) from None
    exists = poses.exists(host.base, project, name)
    if exists and not _flag(params, "replace"):
        raise ForgeError(f"{project} already has a pose set called {name!r}; say replace to import over it",
                         "set.exists", status=409, set=name)
    fps = poses._fps(params.get("fps", 12))
    sub, _, leaf = filename.replace("\\", "/").rpartition("/")
    task = {"filename": leaf, "subfolder": sub, "fps": fps, "max_frames": poses.MAX_FRAMES}
    return poses.public(poses.start(host, "import", project, name, task, {"replaced": exists}))


def render_pose(host, params):
    """Mannequin pictures of a set's frames. Frames already drawn are answered
    at once; the rest are a job for a tab."""
    project = _text(params, "project")
    name = _text(params, "set")
    frames = params.get("frames")
    if isinstance(frames, str):
        frames = [f for f in frames.split(",") if f]
    if frames is not None and not isinstance(frames, list):
        raise ForgeError("frames is a list of frame numbers", "request.field", field="frames")
    data, width, height, wanted, missing = poses.plan_render(
        host.base, project, name, frames, params.get("width"), params.get("height"), params.get("yaw"))
    answer = {"width": width, "height": height, "frames": wanted, "drawn": [m["path"] for m in missing]}
    if not missing:
        return {"job": None, "project": project, "set": name, "state": "done", **answer}
    task = {"width": width, "height": height, "body": data["body"],
            "frames": [{"frame": m["frame"], "pose": m["pose"]} for m in missing]}
    return poses.public(poses.start(host, "render", project, name, task, answer))


def pose_job(host, params):
    return poses.public(poses.find_job(_text(params, "job")))


def claim_pose_job(host, params):
    return poses.claim(_text(params, "job"), _text(params, "tab"))


def finish_pose_job(host, params):
    job, tab = _text(params, "job"), _text(params, "tab")
    if params.get("problem"):
        return poses.fail(job, tab, params["problem"])
    return poses.complete(host.base, job, tab, params)


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
    ("POST", "/post", post),
    ("POST", "/check", check),
    ("POST", "/sheet", sheet),
    ("POST", "/export", export),
    ("POST", "/import", import_files),
    ("GET", "/files", list_files),
    ("GET", "/file", read_file),
    ("GET", "/poses", list_poses),
    ("GET", "/pose/show", show_pose),
    ("POST", "/pose/new", new_pose),
    ("POST", "/pose/paste", paste_pose),
    ("POST", "/pose/set", set_pose),
    ("POST", "/pose/rm", remove_pose),
    ("POST", "/pose/import", import_pose),
    ("POST", "/pose/render", render_pose),
    ("GET", "/pose/job", pose_job),
)

TAB_ROUTES = (
    ("POST", "/pose/claim", claim_pose_job),
    ("POST", "/pose/done", finish_pose_job),
)


def call(host, method, path, params):
    """Run the handler for `method path` -> `(status, answer)`.

    The one place a ForgeError becomes an answer, shared by the aiohttp routes
    and the suites' stand-in server, so both refuse in the same words.
    """
    for want_method, want_path, handler in ROUTES + TAB_ROUTES:
        if method == want_method and path == PREFIX + want_path:
            try:
                return 200, handler(host, params)
            except ForgeError as problem:
                return problem.status, problem.answer()
    return 404, {"problem": f"no forge route {method} {path}", "code": "route.missing"}
