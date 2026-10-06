"""Pose sets, and the jobs that turn them into mannequin pictures in a browser.

A pose set is project data (spec §5.1, §7.9): `poses/<set>.json` holds the
mannequin's body sliders, a frame rate, and one pose per frame in Pose Studio's
own `pose_data` shape — bone rotations in degrees, the bone translations an IK
drag leaves behind, the model's rotation. Only those three fields are kept: the
camera, the IK helpers and the Mixamo debug fields a pose can carry decide
nothing about how the figure looks in a capture (checked: a Mixamo walk drawn
with and without them is the same to the pixel). Bone names are checked against
the mannequin's skeleton, because the core skips a bone it does not know without
a word, and a typo would render the rest pose and call it done.

**Rendering happens in a browser tab, not here.** The mannequin is drawn by
VNCCS Pose Studio's WebGL core (vendored under `web/creator/vendor/posestudio/`),
and the server has no WebGL. So a render — and an FBX import, which retargets a
clip onto the same rig — is a job that *any* open ComfyUI tab with the pack loaded
does: the server announces it on the websocket, the first tab to claim it gets
the task, and its answer completes the job (`web/creator/forge/pose.js`). No tab
connected, the request is refused before anything is queued; a tab that claims
and then goes quiet fails the job after `RUN_WAIT`.

These jobs are not ComfyUI prompts and do not go through `jobs.py`: they use no
GPU on the server, and holding the queue while a browser draws would stop the
renders the forge exists to make. They live in this process's memory, which is
honest about their lifetime — a render takes seconds and its pictures are on disk
before the job is answered.

**A drawn frame says where things are in it.** Beside each PNG the tab stores
the frame's marks (`<frame>.json`): the figure's bounding box in pixels, the
point on the ground under the hips, the lowest point of each foot, and which
edges of the canvas the figure touches. An agent lines frames up on the ground
point instead of measuring silhouettes, and a figure cut off by the canvas is
said, with the size that would hold every frame (`fit`).

**Renders are a cache.** A frame's picture depends on its pose, the body, the
size, the yaw and the camera's pitch, and on nothing else, so each frame is stored under
`build/poses/<set>/` with a hash of those in its name. Asking again for what is
already drawn answers at once without a tab; a changed frame redraws that frame
only. `build/` is derived: none of it is kept as a version.

Like the rest of the storage half, standard library only: the parity suite and
the CLI's stand-in server run this module on a bare Python.
"""

import base64
import hashlib
import json
import os
import struct
import threading
import time
import uuid

from . import project as projects
from .problems import ForgeError

FORMAT = 1
POSES = "poses"
CACHE = "build/poses"

# The mannequin's skeleton, as `pose_studio_makehuman.v2`'s header lists it.
# `Root` is the one bone with no parent.
BONES = frozenset((
    "Root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head",
    "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "ball_l", "ball_r",
    "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r",
    "hand_l", "hand_r",
    *(f"{finger}_0{joint}_{side}" for finger in ("index", "middle", "pinky", "ring", "thumb")
      for joint in (1, 2, 3) for side in ("l", "r")),
))

# Pose Studio's morph sliders, their ranges and its defaults. The male-only
# sliders are left out: the forge's mannequin is the neutral figure.
BODY = {
    "age": (1, 90, 25),
    "gender": (0, 1, 0.5),
    "weight": (0, 1, 0.5),
    "muscle": (0, 1, 0.5),
    "height": (0, 2, 0.5),
    "breast_size": (0, 2, 0.5),
    "firmness": (0, 1, 0.5),
}

MAX_FRAMES = 240
MAX_RENDER = 64        # frames one render job may draw
SIZE = (64, 2048)      # a frame's width and height, each
# A cell of the 2 MP grid four frames are rendered in (spec §7.1 step 6).
DEFAULT_SIZE = (484, 1088)
# Bumped when what a capture looks like changes (lights, background, the core),
# so cached frames drawn the old way are not served as current.
LOOK = 1

CLAIM_WAIT = 15        # seconds for some tab to take a job
RUN_WAIT = {"render": 120, "import": 300}
KEEP = 600             # seconds a finished job is remembered


# ---- one pose, and a set -------------------------------------------------------


def _triple(value, what):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        raise ForgeError(f"{what} must be three numbers", "pose.value")
    out = []
    for v in value[:3]:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
            raise ForgeError(f"{what} must be three finite numbers", "pose.value")
        # Not rounded: six decimals already move pixels in a capture, and JSON
        # carries a double exactly.
        out.append(float(v))
    return out


def _bones(table, what):
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise ForgeError(f"a pose's {what} must be an object of bone: [x, y, z]", "pose.shape")
    unknown = sorted(set(table) - BONES)
    if unknown:
        raise ForgeError(f"the mannequin has no bone called {unknown[0]!r}", "pose.bone", bones=unknown)
    return {name: _triple(value, f"{name}'s {what}") for name, value in sorted(table.items())}


def normalise_pose(pose):
    """A Pose Studio `pose_data` pose -> the three fields that decide the figure."""
    if not isinstance(pose, dict):
        raise ForgeError("a pose is a JSON object with bones", "pose.shape")
    rotation = pose.get("modelRotation")
    return {"bones": _bones(pose.get("bones"), "rotation"),
            "bonePositions": _bones(pose.get("bonePositions"), "position"),
            "modelRotation": _triple(rotation, "modelRotation") if rotation is not None else [0.0, 0.0, 0.0]}


def rest_pose():
    return {"bones": {}, "bonePositions": {}, "modelRotation": [0.0, 0.0, 0.0]}


def normalise_body(body, base=None):
    out = dict(base or {k: default for k, (_, _, default) in BODY.items()})
    if body is None:
        return out
    if not isinstance(body, dict):
        raise ForgeError("a body is an object of slider: value", "pose.body")
    for key, value in body.items():
        if key not in BODY:
            continue  # Pose Studio's mesh carries more than the morph sliders
        low, high, _ = BODY[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise ForgeError(f"{key} is a number from {low} to {high}", "pose.body", field=key)
        out[key] = value
    return out


def _fps(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 60:
        raise ForgeError("fps is a number from 1 to 60", "pose.fps")
    return value


def make_set(name, poses, fps=12, body=None, source=None):
    projects.check_name(name, "set")
    if not isinstance(poses, list) or not poses:
        raise ForgeError("a pose set needs at least one pose", "pose.empty", set=name)
    if len(poses) > MAX_FRAMES:
        raise ForgeError(f"a pose set holds at most {MAX_FRAMES} poses", "pose.many", set=name)
    out = {"format": FORMAT, "name": name, "fps": _fps(fps), "body": normalise_body(body),
           "poses": [normalise_pose(p) for p in poses]}
    if source:
        out["source"] = source
    return out


def from_paste(data):
    """What a person might paste -> `(poses, body, fps)`.

    One pose (`{"bones": …}`), a list of them, a set of ours, or what Pose
    Studio keeps in its node's `pose_data` widget: its `poses` (or, in animation
    mode, `image_poses`), its `mesh` sliders, and its timeline's rate.
    """
    if isinstance(data, list):
        return data, None, None
    if not isinstance(data, dict):
        raise ForgeError("paste a pose, a list of poses, or Pose Studio's pose_data", "pose.shape")
    if "bones" in data and "poses" not in data:
        return [data], None, None
    poses = data.get("poses") or data.get("image_poses")
    if not isinstance(poses, list) or not poses:
        raise ForgeError("that pose_data has no poses in it", "pose.empty")
    timeline = data.get("timeline") if isinstance(data.get("timeline"), dict) else {}
    fps = data.get("fps") or timeline.get("fps")
    return poses, data.get("body") or data.get("mesh"), fps if isinstance(fps, (int, float)) else None


# ---- storage --------------------------------------------------------------------


def _rel(name):
    return f"{POSES}/{projects.check_name(name, 'set')}.json"


def load(base, project, name):
    projects.load(base, project)
    path = projects.inside(projects.folder(base, project), _rel(name))
    data = projects._read_json(path)
    if data is None:
        raise ForgeError(f"{project} has no pose set called {name!r}", "set.missing", status=404, set=name)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ForgeError(f"{_rel(name)} is not a pose set this version can read", "set.format", set=name)
    return data


def save(base, project, data):
    projects.write_file(projects.folder(base, project), _rel(data["name"]), projects._dump(data))
    return data


def listing(base, project):
    projects.load(base, project)
    where = projects.inside(projects.folder(base, project), POSES)
    out = []
    for filename in sorted(os.listdir(where)) if os.path.isdir(where) else []:
        stem, ext = os.path.splitext(filename)
        if ext != ".json" or not projects.NAME.match(stem):
            continue
        data = projects._read_json(os.path.join(where, filename)) or {}
        out.append({"name": stem, "frames": len(data.get("poses", [])), "fps": data.get("fps"),
                    "source": data.get("source")})
    return out


def exists(base, project, name):
    projects.load(base, project)
    return os.path.exists(projects.inside(projects.folder(base, project), _rel(name)))


def create(base, project, name, poses=None, fps=12, body=None, source=None, replace=False):
    data = make_set(name, poses or [rest_pose()], fps, body, source)
    with projects.LOCK:
        if exists(base, project, name) and not replace:
            raise ForgeError(f"{project} already has a pose set called {name!r}", "set.exists",
                             status=409, set=name)
        return save(base, project, data)


def copy_from(base, project, ref):
    """`walk/3` -> that frame's pose; `walk` -> the whole set, body and rate."""
    name, _, frame = ref.partition("/")
    source = load(base, project, name)
    chosen = [source["poses"][_index(source, frame)]] if frame else source["poses"]
    return chosen, source["body"], source["fps"]


def _index(data, frame):
    try:
        index = int(frame)
    except (TypeError, ValueError):
        raise ForgeError(f"{frame!r} is not a frame number", "pose.frame") from None
    if not 0 <= index < len(data["poses"]):
        raise ForgeError(f"{data['name']} has frames 0 to {len(data['poses']) - 1}", "pose.frame",
                         set=data["name"], frame=index)
    return index


def set_bones(base, project, name, frame, rotations):
    """Turn some bones of one frame, in degrees; the rest of the pose stays."""
    with projects.LOCK:
        data = load(base, project, name)
        index = _index(data, frame)
        pose = data["poses"][index]
        pose["bones"] = {**pose["bones"], **_bones(rotations, "rotation")}
        # A zero rotation is the rest pose; Pose Studio leaves those out too.
        pose["bones"] = {k: v for k, v in sorted(pose["bones"].items()) if any(v)}
        return save(base, project, data)


def remove(base, project, name):
    with projects.LOCK:
        load(base, project, name)
        root = projects.folder(base, project)
        moved = projects._retire(root, projects.inside(root, _rel(name)))
    return {"removed": name, "kept": os.path.relpath(moved, root)}


# ---- the render cache ----------------------------------------------------------


def turned(pose, yaw):
    """The pose with the model turned `yaw` degrees more about its up axis —
    how a set is drawn from another direction (spec §7.9)."""
    if not yaw:
        return pose
    x, y, z = pose["modelRotation"]
    return {**pose, "modelRotation": [x, (y + yaw) % 360, z]}


# How far the camera may look down on (or up at) the figure. Straight down is
# left out: the capture camera's up is the world's, and at 90° it has none.
PITCH = 89


def frame_key(pose, body, width, height, pitch=0):
    what = {"pose": pose, "body": body, "size": [width, height], "look": LOOK}
    # Only when it is not level, so frames drawn before pitch existed keep
    # their names and stay cached.
    if pitch:
        what["pitch"] = pitch
    text = json.dumps(what, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def frame_rel(name, index, key):
    return f"{CACHE}/{name}/{index:03d}-{key}.png"


def marks_rel(rel):
    return rel[:-len(".png")] + ".json"


EDGES = ("left", "top", "right", "bottom")
FIT_MARGIN = 0.06      # of the figure's span, either side, when a size is suggested


def _point(value, what):
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or v != v for v in value)):
        raise ForgeError(f"a frame's {what} is two numbers", "pose.upload")
    return [round(float(v), 1) for v in value]


def clean_marks(marks, width, height):
    """What a tab measured on one frame, checked: pixels, top-left origin."""
    if not isinstance(marks, dict):
        raise ForgeError("a frame's marks are an object", "pose.upload")
    box = marks.get("bbox")
    if box is not None:
        if (not isinstance(box, (list, tuple)) or len(box) != 4
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in box)):
            raise ForgeError("a frame's bbox is [left, top, right, bottom]", "pose.upload")
        box = [int(v) for v in box]
    feet = marks.get("feet") or {}
    if not isinstance(feet, dict):
        raise ForgeError("a frame's feet are {l, r}", "pose.upload")
    edges = [] if box is None else [edge for edge, touching in zip(
        EDGES, (box[0] <= 0, box[1] <= 0, box[2] >= width - 1, box[3] >= height - 1)) if touching]
    return {"bbox": box, "ground": _point(marks.get("ground"), "ground point"),
            "feet": {side: _point(feet.get(side), f"{side} foot") for side in ("l", "r")}, "edges": edges}


def read_marks(root, rel):
    return projects._read_json(projects.inside(root, marks_rel(rel)))


def fit(frames, width, height):
    """The canvas that holds every frame's figure with a margin, the figure kept
    where it is drawn (the capture is centred on the body), or None if every
    frame already fits. Whole multiples of four, within `SIZE`."""
    boxes = [f["marks"]["bbox"] for f in frames if (f.get("marks") or {}).get("bbox")]
    if not boxes or not any(f["marks"]["edges"] for f in frames if f.get("marks")):
        return None

    def span(low, high, size):
        half = max(max(size / 2 - lo, hi - size / 2) for lo, hi in zip(low, high))
        return 2 * half * (1 + FIT_MARGIN)

    w = span([b[0] for b in boxes], [b[2] for b in boxes], width)
    h = span([b[1] for b in boxes], [b[3] for b in boxes], height)
    # A figure cut off by the canvas is bigger than its box says, by however
    # much was cut, so a touched direction asks for half as much again at least.
    edges = {e for f in frames if f.get("marks") for e in f["marks"]["edges"]}
    if {"left", "right"} & edges:
        w = max(w, width * 1.5)
    if {"top", "bottom"} & edges:
        h = max(h, height * 1.5)
    def whole(need, now):
        return min(SIZE[1], max(now, int(-(-need // 4) * 4)))

    return [whole(w, width), whole(h, height)]


def _size(value, default):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ForgeError("a frame's width and height are whole numbers of pixels", "pose.size") from None
    if not SIZE[0] <= number <= SIZE[1]:
        raise ForgeError(f"a frame is {SIZE[0]} to {SIZE[1]} pixels on each side", "pose.size")
    return number


def _pitch(value):
    """Degrees the camera looks down on the figure: 0 level, as a side-on
    platformer draws it; about 30 for a three-quarter RPG; negative looks up."""
    try:
        pitch = float(value or 0)
    except (TypeError, ValueError):
        raise ForgeError("pitch is a number of degrees", "pose.pitch") from None
    if not -PITCH <= pitch <= PITCH:
        raise ForgeError(f"pitch is from -{PITCH} to {PITCH} degrees", "pose.pitch")
    return pitch


def plan_render(base, project, name, frames=None, width=None, height=None, yaw=0, pitch=0):
    """What a render of these frames needs: every frame's file, and which of
    them are not drawn yet."""
    data = load(base, project, name)
    width = _size(width, DEFAULT_SIZE[0])
    height = _size(height, DEFAULT_SIZE[1])
    try:
        yaw = float(yaw or 0)
    except (TypeError, ValueError):
        raise ForgeError("yaw is a number of degrees", "pose.yaw") from None
    pitch = _pitch(pitch)
    indices = list(range(len(data["poses"]))) if frames in (None, "", []) else [_index(data, f) for f in frames]
    root = projects.folder(base, project)
    wanted, missing = [], []
    for index in indices:
        pose = turned(data["poses"][index], yaw)
        rel = frame_rel(name, index, frame_key(pose, data["body"], width, height, pitch))
        if os.path.isfile(projects.inside(root, rel)):
            wanted.append({"frame": index, "path": rel, "marks": read_marks(root, rel)})
        else:
            wanted.append({"frame": index, "path": rel, "marks": None})
            missing.append({"frame": index, "path": rel, "pose": pose})
    if len(missing) > MAX_RENDER:
        raise ForgeError(f"one render draws at most {MAX_RENDER} frames; ask for fewer", "pose.many")
    return data, width, height, pitch, wanted, missing


# ---- jobs a browser tab does ---------------------------------------------------

JOBS = {}
_JOBS_LOCK = threading.RLock()


def _expire(job, now):
    """A job nobody took, or whose tab went quiet, fails here — checked lazily
    whenever a job is looked at, so no timer thread runs beside the server."""
    if job["state"] == "waiting" and now - job["created"] > CLAIM_WAIT:
        job.update(state="failed", code="pose.no_tab", problem=(
            "no ComfyUI tab took the job: open ComfyUI in a browser, with this pack loaded, "
            "and keep the tab open while poses are drawn"))
    elif job["state"] == "claimed" and now - job["claimed"] > RUN_WAIT[job["kind"]]:
        job.update(state="failed", code="pose.tab_quiet",
                   problem="the ComfyUI tab that took the job stopped answering")


def _sweep(now):
    for job_id in [j for j, job in JOBS.items() if job["state"] in ("done", "failed")
                   and now - job.get("finished", now) > KEEP]:
        del JOBS[job_id]


def start(host, kind, project, name, task, answer=None):
    """Announce a job to every tab. Refused at once when no tab is connected."""
    if not host.tabs():
        raise ForgeError("no ComfyUI tab is open to draw the mannequin: open ComfyUI in a browser, "
                         "with this pack loaded, and try again", "pose.no_tab", status=409)
    now = time.time()
    job = {"id": uuid.uuid4().hex[:12], "kind": kind, "project": project, "set": name,
           "state": "waiting", "created": now, "claimed": None, "tab": None,
           "task": task, "answer": answer or {}}
    with _JOBS_LOCK:
        _sweep(now)
        JOBS[job["id"]] = job
    host.announce("continuity.pose.job", {"job": job["id"], "kind": kind, "project": project, "set": name})
    return job


def public(job):
    out = {"job": job["id"], "kind": job["kind"], "project": job["project"], "set": job["set"],
           "state": job["state"], **job["answer"]}
    if job["state"] == "failed":
        out.update(problem=job["problem"], code=job["code"])
    return out


def find_job(job_id):
    with _JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ForgeError(f"there is no pose job {job_id!r}; finished jobs are forgotten after "
                             f"{KEEP // 60} minutes", "job.missing", status=404, job=job_id)
        _expire(job, time.time())
        return job


def claim(job_id, tab):
    """The first tab to ask gets the task; any later one is told it is taken."""
    with _JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ForgeError("that job is gone", "job.missing", status=404, job=job_id)
        _expire(job, time.time())
        if job["state"] != "waiting":
            raise ForgeError("another tab took that job", "job.taken", status=409, job=job_id)
        job.update(state="claimed", claimed=time.time(), tab=tab)
        return {"job": job_id, "kind": job["kind"], **job["task"]}


def _owned(job_id, tab):
    job = find_job(job_id)
    if job["state"] != "claimed" or job["tab"] != tab:
        raise ForgeError("this tab does not hold that job", "job.taken", status=409, job=job_id)
    return job


def fail(job_id, tab, problem):
    with _JOBS_LOCK:
        job = _owned(job_id, tab)
        job.update(state="failed", code=f"pose.{job['kind']}_failed", finished=time.time(),
                   problem=str(problem or "the tab could not do it")[:500])
    return public(job)


def png_size(data):
    """`(width, height)` from a PNG's header, or None when it is not a PNG."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _decode_png(value, width, height):
    if not isinstance(value, str):
        raise ForgeError("a frame comes back as a PNG data URL", "pose.upload")
    _, _, payload = value.partition("base64,")
    try:
        data = base64.b64decode(payload or value, validate=True)
    except ValueError:
        raise ForgeError("a frame came back that is not base64", "pose.upload") from None
    if png_size(data) != (width, height):
        raise ForgeError(f"a frame came back that is not a {width}x{height} PNG", "pose.upload")
    return data


def summary(frames, width, height):
    """A render's frames with their marks, which of them the canvas cuts, and
    the size that would hold them all."""
    clipped = [f["frame"] for f in frames if (f.get("marks") or {}).get("edges")]
    return {"frames": frames, "clipped": clipped, "fit": fit(frames, width, height)}


def complete(base, job_id, tab, result):
    """The tab's answer: drawn frames for a render, retargeted poses for an import."""
    job = _owned(job_id, tab)
    task = job["task"]
    if job["kind"] == "render":
        root = projects.folder(base, job["project"])
        pictures = result.get("frames")
        if not isinstance(pictures, list) or len(pictures) != len(task["frames"]):
            raise ForgeError(f"the render should come back with {len(task['frames'])} frames", "pose.upload")
        decoded = [_decode_png(p, task["width"], task["height"]) for p in pictures]
        measured = result.get("marks")
        if measured is not None and (not isinstance(measured, list) or len(measured) != len(pictures)):
            raise ForgeError("a render's marks come one per frame", "pose.upload")
        marks = [clean_marks(m, task["width"], task["height"]) for m in measured] if measured else [None] * len(decoded)
        drawn = {}
        for rel, data, mark in zip(job["answer"]["drawn"], decoded, marks):
            projects.write_derived(root, rel, data)
            if mark is not None:
                projects.write_derived(root, marks_rel(rel), projects._dump(mark).encode())
            drawn[rel] = mark
        frames = [{**f, "marks": drawn.get(f["path"], f.get("marks"))} for f in job["answer"]["frames"]]
        job["answer"] = {**job["answer"], **summary(frames, task["width"], task["height"])}
    else:
        poses = result.get("poses")
        if not isinstance(poses, list) or not poses:
            raise ForgeError("the import came back with no poses", "pose.upload")
        # Whether a set may be replaced was settled when the job started.
        create(base, job["project"], job["set"], poses[:MAX_FRAMES], task["fps"], None,
               {"clip": task["filename"]}, replace=True)
        job["answer"] = {**job["answer"], "frames": min(len(poses), MAX_FRAMES)}
    with _JOBS_LOCK:
        job.update(state="done", finished=time.time())
    return public(job)
