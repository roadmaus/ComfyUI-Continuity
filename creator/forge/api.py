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

`make` and `jobs` put renders on ComfyUI's queue and ask after them; the host
does both (`render`, `prompt_state`), so the handlers stay free of ComfyUI.

`TAB_ROUTES` are the other half of a pose job (`pose.py`): what a browser tab
calls to take a job and hand back what it drew. They are served like the rest
but are not a capability a client has, so the parity test does not ask the CLI
for a command that calls them.
"""

import os
import re

from . import joints, kinds, make as making, pose as poses, project as projects, targets
from .problems import ForgeError

PREFIX = "/continuity/forge"


class Host:
    def __init__(self, base, resolve=None, families=None, tabs=None, announce=None, render=None,
                 prompt_state=None):
        self.base = base
        self._resolve = resolve
        self._families = families
        self._tabs = tabs
        self._announce = announce
        self._render = render
        self._prompt_state = prompt_state

    def render(self, body):
        """Queue one `/continuity/render` request. -> `{prompt_id, speed}`;
        a refusal is a ForgeError carrying the render route's sentence."""
        if self._render is None:
            raise ForgeError("this server cannot render", "host.render")
        return self._render(body)

    def prompt_state(self, prompt_id):
        """-> `(state, message)`: queued, running, done, failed (with the
        error), or unknown when the queue has no record of it."""
        if self._prompt_state is None:
            return "unknown", None
        return self._prompt_state(prompt_id)

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


def _off(params, key):
    """A switch that is on unless said off: absent is on."""
    return key in params and params[key] is not None and not _flag(params, key)


def _object(params, key):
    value = params.get(key)
    if not isinstance(value, dict):
        raise ForgeError(f"{key} must be a JSON object", "request.field", field=key)
    return value


# ---- discovery -------------------------------------------------------------------


def _pack():
    """The pack's version and, in a git checkout, its commit: what a client on
    another machine needs to say which code answered it. Read off the files,
    because a server with no shell is exactly where nobody can run `git`."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out = {"version": None, "commit": None}
    try:
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as handle:
            found = re.search(r'^version\s*=\s*"([^"]+)"', handle.read(), re.M)
        out["version"] = found.group(1) if found else None
        with open(os.path.join(root, ".git", "HEAD"), encoding="utf-8") as handle:
            head = handle.read().strip()
        if head.startswith("ref: "):
            ref = head[5:]
            path = os.path.join(root, ".git", *ref.split("/"))
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as handle:
                    head = handle.read().strip()
            else:
                with open(os.path.join(root, ".git", "packed-refs"), encoding="utf-8") as handle:
                    head = next((line.split()[0] for line in handle if line.strip().endswith(" " + ref)), "")
        out["commit"] = head[:12] or None
    except OSError:
        pass
    return out


def capabilities(host, params):
    """What this machine can make: the kinds, the modes, the targets and the
    still families. Engines and optional packs join this as they land."""
    return {"kinds": [{"id": k, "help": v["help"]} for k, v in kinds.KINDS.items()],
            **targets.catalogue(), "families": host.families(), "makes": list(making.MAKEABLE),
            "pack": _pack()}


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
    answer = status(host, params)
    return {"project": projects.load(host.base, name), "status": answer}


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
    """Every asset's state, after collecting any take that has landed; a row
    whose asset is on the queue says which take."""
    name = _text(params, "project")
    making.collect(host, host.base, name)
    answer = projects.status(host.base, name)
    queued = {t["asset"]: t["take"] for t in making.takes(host.base, name) if t["state"] == "queued"}
    for row in answer["assets"]:
        row["making"] = queued.get(row["name"])
    return answer


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

    size = params.get("size")
    if isinstance(size, str) and size.isdigit():
        size = int(size)
    return review.sheet(host.base, _text(params, "project"), _text(params, "asset"), size)


def export(host, params):
    from . import export as exporting

    return exporting.export(host.base, _text(params, "project"), _text(params, "target"),
                            _names(params, "assets"))


# ---- making -------------------------------------------------------------------------


def make(host, params):
    """Queue the renders that make assets: the named ones, or every planned
    (`missing`) or stale (`stale`) one. `dry_run` says what would be queued.
    Renders are native unless `fast`, which throws the family's turbo switch.
    `new_seed` gives each asset a fresh seed, written into its recipe."""
    return making.start(host, host.base, _text(params, "project"), _names(params, "assets"),
                        _flag(params, "missing"), _flag(params, "stale"), _flag(params, "dry_run"),
                        _flag(params, "fast"), _text(params, "quality", required=False),
                        _flag(params, "new_seed"))


def jobs(host, params):
    """A project's takes (or one asset's, or the named ones), each collected
    into its asset first if its renders have landed."""
    name = _text(params, "project")
    making.collect(host, host.base, name)
    wanted = _names(params, "takes")
    found = making.takes(host.base, name, _text(params, "asset", required=False))
    if wanted:
        missing = sorted(set(wanted) - {t["take"] for t in found})
        if missing:
            raise ForgeError(f"{name} has no take {missing[0]}", "take.missing", status=404, take=missing[0])
        found = [t for t in found if t["take"] in wanted]
    return {"project": name, "takes": found}


# ---- poses --------------------------------------------------------------------------


def list_poses(host, params):
    return {"sets": poses.listing(host.base, _text(params, "project"))}


def show_pose(host, params):
    """A set; with `joints`, also every frame read as joint angles
    (`joints.read`), which is how an agent sees what a pose is without a
    picture."""
    data = poses.load(host.base, _text(params, "project"), _text(params, "set"))
    if not _flag(params, "joints"):
        return {"set": data}
    return {"set": data, "joints": [joints.read(p) for p in data["poses"]]}


def joint_words(host, params):
    """The joint vocabulary: every joint, its motions, their limits, what they mean."""
    return {"joints": joints.vocabulary()}


def new_pose(host, params):
    """A new set: one rest pose, or copied from `from` (`walk`, or `walk/3`)."""
    project = _text(params, "project")
    source = _text(params, "from", required=False)
    frames, body, fps, timing = poses.copy_from(host.base, project, source) if source else (None, None, 12, None)
    return {"set": poses.create(host.base, project, _text(params, "set"), frames, fps, body, timing=timing)}


def paste_pose(host, params):
    """Pose Studio's `pose_data`, or poses written by hand, as a set.

    A set of ours pasted back over itself is how the bench's pose page saves
    an edit, so the set's `source` (the clip it was imported from) comes
    through with it rather than being forgotten on the first touch."""
    data = params.get("data")
    frames, body, fps, timing = poses.from_paste(data)
    if params.get("fps") is not None:
        fps = params["fps"]
    source = data.get("source") if isinstance(data, dict) else None
    return {"set": poses.create(host.base, _text(params, "project"), _text(params, "set"), frames,
                                fps or 12, body, source=source, replace=_flag(params, "replace"), timing=timing)}


def set_pose(host, params):
    """Turn bones of one frame: raw (`bones`, BONE: [x, y, z]) or by joint
    (`joints`, "elbow_l.bend": 90, "hand_r": "fist"), `mirror` for both sides."""
    bones = _object(params, "bones") if params.get("bones") is not None else None
    moves = _object(params, "joints") if params.get("joints") is not None else None
    return {"set": poses.set_bones(host.base, _text(params, "project"), _text(params, "set"),
                                   params.get("frame"), bones, moves, _flag(params, "mirror"))}


def flip_pose(host, params):
    """A frame mirrored left for right, in place or onto frame `to`."""
    return {"set": poses.flip(host.base, _text(params, "project"), _text(params, "set"),
                              params.get("frame"), params.get("to"))}


def key_pose(host, params):
    """A set's keys (frames somebody posed, each with the ease that leaves it),
    its length and whether it loops; the in-betweens follow."""
    keys = params.get("keys")
    loop = params.get("loop")
    return {"set": poses.set_timing(host.base, _text(params, "project"), _text(params, "set"),
                                    keys, params.get("length"), None if loop is None else _flag(params, "loop"),
                                    _flag(params, "clear"))}


def remove_pose(host, params):
    return poses.remove(host.base, _text(params, "project"), _text(params, "set"))


def import_pose(host, params):
    """An FBX clip (a ComfyUI input file) retargeted onto the mannequin, in a tab.
    The tab grounds the feet and faces the clip forward unless `ground` or
    `face` is false."""
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
    # In place means no travel, not no height: the feet are put on the ground
    # each frame and the clip's own lift kept (`ground`), and the clip is
    # turned to face forward on average (`face`), so one yaw is one view
    # across clips. Both on unless asked off.
    task = {"filename": leaf, "subfolder": sub, "fps": fps, "max_frames": poses.MAX_FRAMES,
            "ground": not _off(params, "ground"), "face": not _off(params, "face")}
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
    data, width, height, pitch, wanted, missing = poses.plan_render(
        host.base, project, name, frames, params.get("width"), params.get("height"), params.get("yaw"),
        params.get("pitch"), params.get("views"))
    answer = {"width": width, "height": height, "pitch": pitch, "drawn": [m["path"] for m in missing],
              **poses.summary(wanted, width, height)}
    if not missing:
        return {"job": None, "project": project, "set": name, "state": "done", **answer}
    task = {"width": width, "height": height, "pitch": pitch, "body": data["body"],
            "frames": [{"frame": m["frame"], "pose": m["pose"]} for m in missing]}
    return poses.public(poses.start(host, "render", project, name, task, answer))


def sheet_pose(host, params):
    """Frames already drawn, in one picture: a row per yaw. Takes the same
    frames, size, pitch and views as `/pose/render`, which must have drawn them."""
    project = _text(params, "project")
    name = _text(params, "set")
    frames = params.get("frames")
    if frames is not None and not isinstance(frames, list):
        raise ForgeError("frames is a list of frame numbers", "request.field", field="frames")
    *_, wanted, _ = poses.plan_render(host.base, project, name, frames, params.get("width"),
                                      params.get("height"), params.get("yaw"), params.get("pitch"),
                                      params.get("views"))
    return {"project": project, "set": name,
            "path": poses.contact_sheet(host.base, project, name, wanted, poses._yaw(params.get("yaw")))}


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
    ("POST", "/make", make),
    ("GET", "/jobs", jobs),
    ("POST", "/post", post),
    ("POST", "/check", check),
    ("POST", "/sheet", sheet),
    ("POST", "/export", export),
    ("POST", "/import", import_files),
    ("GET", "/files", list_files),
    ("GET", "/file", read_file),
    ("GET", "/poses", list_poses),
    ("GET", "/pose/joints", joint_words),
    ("GET", "/pose/show", show_pose),
    ("POST", "/pose/new", new_pose),
    ("POST", "/pose/paste", paste_pose),
    ("POST", "/pose/set", set_pose),
    ("POST", "/pose/flip", flip_pose),
    ("POST", "/pose/keys", key_pose),
    ("POST", "/pose/rm", remove_pose),
    ("POST", "/pose/import", import_pose),
    ("POST", "/pose/render", render_pose),
    ("POST", "/pose/sheet", sheet_pose),
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
