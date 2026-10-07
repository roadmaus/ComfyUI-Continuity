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
import io
import json
import os
import struct
import threading
import time
import uuid

from . import joints as rig, project as projects
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


def make_set(name, poses, fps=12, body=None, source=None, timing=None):
    projects.check_name(name, "set")
    if not isinstance(poses, list) or not poses:
        raise ForgeError("a pose set needs at least one pose", "pose.empty", set=name)
    if len(poses) > MAX_FRAMES:
        raise ForgeError(f"a pose set holds at most {MAX_FRAMES} poses", "pose.many", set=name)
    out = {"format": FORMAT, "name": name, "fps": _fps(fps), "body": normalise_body(body),
           "poses": [normalise_pose(p) for p in poses]}
    if source:
        out["source"] = source
    timing = timing or {}
    if timing.get("keys"):
        out["keys"] = _keys(timing["keys"], len(out["poses"]))
        out["loop"] = bool(timing.get("loop"))
        tween(out)
    return out


# ---- keys and in-betweens ---------------------------------------------------------
#
# A set may name some of its frames as keys. Then those are the frames somebody
# posed, and every other frame is drawn between the keys either side of it —
# recomputed here whenever the set is written, so an edited key moves its
# neighbours with it and nobody keeps in-betweens up to date by hand. A set
# without `keys` is what it always was: every frame its own pose (an import, a
# frame-by-frame set). The in-betweens are worked out on the server, not in the
# vendored animation module, so an agent with no browser tab open gets them too,
# and the bench and the CLI cannot disagree about them.
#
# Each key carries the ease of the stretch that starts at it. With `loop`, the
# stretch after the last key runs on into the first, so a walk's last frames
# lead back into its first; without it the frames past the last key hold it,
# as the frames before the first hold that.
#
# Rotations are turned the short way between keys (quaternion slerp), never
# blended as Euler numbers, which swing a limb through poses neither key has.
# Bone translations are blended straight; a translation one key has and the
# other does not cannot be, because the server does not know the bone's rest
# position (it depends on the body), so that is refused with both frames named.

EASES = ("linear", "ease-in", "ease-out", "ease-in-out", "hold")


def ease(name, t):
    if name == "ease-in":
        return t * t
    if name == "ease-out":
        return 1 - (1 - t) * (1 - t)
    if name == "ease-in-out":
        return t * t * (3 - 2 * t)
    if name == "hold":
        return 0.0
    return t


def _keys(value, count):
    """`[{"frame": 0, "ease": "linear"}, …]`, or bare frame numbers -> checked and sorted."""
    if not isinstance(value, list) or not value:
        raise ForgeError("keys is a list of frames, each {frame, ease}", "pose.keys")
    out = {}
    for item in value:
        entry = item if isinstance(item, dict) else {"frame": item}
        frame = entry.get("frame")
        if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame < count:
            raise ForgeError(f"a key is a frame from 0 to {count - 1}; got {frame!r}", "pose.keys", frame=frame)
        how = entry.get("ease") or "linear"
        if how not in EASES:
            raise ForgeError(f"an ease is one of {', '.join(EASES)}; got {how!r}", "pose.ease", eases=list(EASES))
        out[frame] = how
    return [{"frame": f, "ease": out[f]} for f in sorted(out)]


def _blend(a, b, t):
    """Pose `a` -> pose `b` at `t` (0..1)."""
    if t <= 0:
        return a
    if t >= 1:
        return b
    bones = {}
    for name in sorted(set(a["bones"]) | set(b["bones"])):
        qa = rig.matrix_quaternion(rig.degrees_matrix(a["bones"].get(name, [0.0, 0.0, 0.0])))
        qb = rig.matrix_quaternion(rig.degrees_matrix(b["bones"].get(name, [0.0, 0.0, 0.0])))
        value = rig.matrix_degrees(rig.quaternion_matrix(rig.slerp(qa, qb, t)))
        if any(abs(v) > 1e-9 for v in value):
            bones[name] = value
    positions = {}
    for name in sorted(set(a["bonePositions"]) | set(b["bonePositions"])):
        pa, pb = a["bonePositions"].get(name), b["bonePositions"].get(name)
        if pa is None or pb is None:
            raise ForgeError(f"one key moves {name} and the other leaves it where the body puts it, and the "
                             "server cannot blend between those; give both keys a position for it, or neither",
                             "pose.tween_position", bone=name)
        positions[name] = [x + (y - x) * t for x, y in zip(pa, pb)]
    if a["modelRotation"] == b["modelRotation"]:
        model = list(a["modelRotation"])
    else:
        qa = rig.matrix_quaternion(rig.degrees_matrix(a["modelRotation"]))
        qb = rig.matrix_quaternion(rig.degrees_matrix(b["modelRotation"]))
        model = rig.matrix_degrees(rig.quaternion_matrix(rig.slerp(qa, qb, t)))
    return {"bones": bones, "bonePositions": positions, "modelRotation": model}


def tween(data):
    """Draw every frame that is not a key between the keys either side of it, in place."""
    keys = data.get("keys")
    if not keys:
        return data
    poses = data["poses"]
    count = len(poses)
    frames = [k["frame"] for k in keys]
    eases = {k["frame"]: k["ease"] for k in keys}
    first, last = frames[0], frames[-1]
    for f in range(count):
        if f in eases:
            continue
        before = max((k for k in frames if k < f), default=None)
        after = min((k for k in frames if k > f), default=None)
        if data.get("loop") and len(frames) > 1 and (before is None or after is None):
            # The stretch from the last key round the end into the first.
            span = count - last + first
            into = f - last if f > last else count - last + f
            poses[f] = _blend(poses[last], poses[first], ease(eases[last], into / span))
        elif before is None or after is None:
            poses[f] = dict(poses[after if before is None else before])
        else:
            poses[f] = _blend(poses[before], poses[after], ease(eases[before], (f - before) / (after - before)))
    return data


def _keyed(data, frame):
    """A frame somebody just posed becomes a key, taking the ease of the stretch
    it falls in, so editing an in-between keeps the edit."""
    keys = data.get("keys")
    if keys and frame not in [k["frame"] for k in keys]:
        before = [k for k in keys if k["frame"] < frame]
        how = (before[-1] if before else keys[-1])["ease"]
        data["keys"] = _keys(keys + [{"frame": frame, "ease": how}], len(data["poses"]))


def from_paste(data):
    """What a person might paste -> `(poses, body, fps, timing)`.

    One pose (`{"bones": …}`), a list of them, a set of ours, or what Pose
    Studio keeps in its node's `pose_data` widget: its `poses` (or, in animation
    mode, `image_poses`), its `mesh` sliders, and its timeline's rate. A set
    of ours brings its keys and loop (`timing`), so the in-betweens are
    worked out again from the pasted keys.
    """
    if isinstance(data, list):
        return data, None, None, None
    if not isinstance(data, dict):
        raise ForgeError("paste a pose, a list of poses, or Pose Studio's pose_data", "pose.shape")
    if "bones" in data and "poses" not in data:
        return [data], None, None, None
    poses = data.get("poses") or data.get("image_poses")
    if not isinstance(poses, list) or not poses:
        raise ForgeError("that pose_data has no poses in it", "pose.empty")
    timeline = data.get("timeline") if isinstance(data.get("timeline"), dict) else {}
    fps = data.get("fps") or timeline.get("fps")
    timing = {"keys": data["keys"], "loop": data.get("loop")} if data.get("keys") else None
    return poses, data.get("body") or data.get("mesh"), fps if isinstance(fps, (int, float)) else None, timing


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


def create(base, project, name, poses=None, fps=12, body=None, source=None, replace=False, timing=None):
    data = make_set(name, poses or [rest_pose()], fps, body, source, timing)
    with projects.LOCK:
        if exists(base, project, name) and not replace:
            raise ForgeError(f"{project} already has a pose set called {name!r}", "set.exists",
                             status=409, set=name)
        return save(base, project, data)


def copy_from(base, project, ref):
    """`walk/3` -> that frame's pose; `walk` -> the whole set, body, rate and keys."""
    name, _, frame = ref.partition("/")
    source = load(base, project, name)
    if frame:
        return [source["poses"][_index(source, frame)]], source["body"], source["fps"], None
    timing = {"keys": source["keys"], "loop": source.get("loop")} if source.get("keys") else None
    return source["poses"], source["body"], source["fps"], timing


def _index(data, frame):
    try:
        index = int(frame)
    except (TypeError, ValueError):
        raise ForgeError(f"{frame!r} is not a frame number", "pose.frame") from None
    if not 0 <= index < len(data["poses"]):
        raise ForgeError(f"{data['name']} has frames 0 to {len(data['poses']) - 1}", "pose.frame",
                         set=data["name"], frame=index)
    return index


def set_bones(base, project, name, frame, rotations=None, joints=None, mirror=False):
    """Turn some bones of one frame — raw (`rotations`, degrees on the bone's
    own axes) or by joint (`joints`, `joints.set_joints`'s words) — the rest of
    the pose stays. `mirror` does the same to the other side. In a set with
    keys the frame becomes a key, and the in-betweens are drawn again."""
    if not rotations and not joints:
        raise ForgeError("say which bones or joints to turn", "pose.shape")
    with projects.LOCK:
        data = load(base, project, name)
        index = _index(data, frame)
        pose = data["poses"][index]
        turns = _bones(rotations, "rotation")
        if mirror:
            turns = {**{rig.twin(k): rig.mirror_rotation(v) for k, v in turns.items()}, **turns}
        pose["bones"] = {**pose["bones"], **turns}
        if joints:
            pose = rig.set_joints(pose, rig.mirrored_keys(joints) if mirror else joints)
        # A zero rotation is the rest pose; Pose Studio leaves those out too.
        pose["bones"] = {k: v for k, v in sorted(pose["bones"].items()) if any(v)}
        data["poses"][index] = pose
        _keyed(data, index)
        return save(base, project, tween(data))


def flip(base, project, name, frame, to=None):
    """Frame `frame` seen in a mirror, written over itself or over frame `to`:
    a walk's second half is its first half flipped."""
    with projects.LOCK:
        data = load(base, project, name)
        source = _index(data, frame)
        target = source if to in (None, "") else _index(data, to)
        data["poses"][target] = rig.flip_pose(data["poses"][source])
        _keyed(data, target)
        return save(base, project, tween(data))


def set_timing(base, project, name, keys=None, length=None, loop=None, clear=False):
    """A set's keys, its length and whether it loops. Growing a set adds frames
    after its last (in-betweens when it has keys, copies of the last pose when
    it has none); shrinking drops frames from the end, and their keys."""
    with projects.LOCK:
        data = load(base, project, name)
        if length is not None:
            if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= MAX_FRAMES:
                raise ForgeError(f"a set is 1 to {MAX_FRAMES} frames long", "pose.many", set=name)
            poses = data["poses"]
            data["poses"] = poses[:length] + [dict(poses[-1]) for _ in range(length - len(poses))]
            if data.get("keys"):
                kept = [k for k in data["keys"] if k["frame"] < length]
                if not kept:
                    raise ForgeError(f"{name} would lose every key; keep frame {data['keys'][0]['frame']} "
                                     "or clear the keys", "pose.keys", set=name)
                data["keys"] = kept
        if clear:
            data.pop("keys", None)
            data.pop("loop", None)
        elif keys is not None:
            data["keys"] = _keys(keys, len(data["poses"]))
        if loop is not None:
            if not data.get("keys"):
                raise ForgeError("only a set with keys loops: the loop is how its in-betweens wrap",
                                 "pose.keys", set=name)
            data["loop"] = bool(loop)
        elif data.get("keys"):
            data.setdefault("loop", False)
        return save(base, project, tween(data))


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


def _yaw(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        raise ForgeError("yaw is a number of degrees", "pose.yaw") from None


def plan_render(base, project, name, frames=None, width=None, height=None, yaw=0, pitch=0, views=None):
    """What a render of these frames needs: every frame's file, and which of
    them are not drawn yet.

    `views` draws each frame at several yaws in one job — front and side, so
    one look shows a pose in depth — and tags every frame with its yaw."""
    data = load(base, project, name)
    width = _size(width, DEFAULT_SIZE[0])
    height = _size(height, DEFAULT_SIZE[1])
    if views not in (None, "", []):
        if not isinstance(views, list) or len(views) > 8:
            raise ForgeError("views is a list of up to eight yaws, in degrees", "pose.yaw")
        yaws, tagged = [_yaw(v) for v in views], True
    else:
        yaws, tagged = [_yaw(yaw)], False
    pitch = _pitch(pitch)
    indices = list(range(len(data["poses"]))) if frames in (None, "", []) else [_index(data, f) for f in frames]
    root = projects.folder(base, project)
    wanted, missing = [], []
    for turn in yaws:
        for index in indices:
            pose = turned(data["poses"][index], turn)
            rel = frame_rel(name, index, frame_key(pose, data["body"], width, height, pitch))
            tag = {"yaw": turn} if tagged else {}
            if os.path.isfile(projects.inside(root, rel)):
                wanted.append({"frame": index, **tag, "path": rel, "marks": read_marks(root, rel)})
            else:
                wanted.append({"frame": index, **tag, "path": rel, "marks": None})
                missing.append({"frame": index, "path": rel, "pose": pose})
    if len(missing) > MAX_RENDER:
        raise ForgeError(f"one render draws at most {MAX_RENDER} frames; ask for fewer", "pose.many")
    return data, width, height, pitch, wanted, missing


def contact_sheet(base, project, name, frames):
    """Drawn frames -> one PNG, a row per yaw, a column per frame, each labelled:
    the agent's single look at a pose from several sides. Every frame must be
    drawn already (`render` first); the sheet is derived and cached by what is
    in it. At most `MAX_RENDER` pictures, as a render: cached frames cost no
    tab, so without the cap one request could ask for every frame of a long
    set at eight yaws, full size, in memory at once."""
    from PIL import Image, ImageDraw  # ComfyUI has it; the storage half stays standard library

    root = projects.folder(base, project)
    if len(frames) > MAX_RENDER:
        raise ForgeError(f"a sheet holds at most {MAX_RENDER} pictures; ask for fewer frames or views",
                         "pose.many")
    missing = [f["frame"] for f in frames if not os.path.isfile(projects.inside(root, f["path"]))]
    if missing:
        raise ForgeError(f"frames {', '.join(map(str, missing))} are not drawn yet; render them first",
                         "pose.undrawn", frames=missing)
    rows = {}
    for f in frames:
        rows.setdefault(f.get("yaw", 0.0), []).append(f)
    key = hashlib.sha256("|".join(f["path"] for f in frames).encode()).hexdigest()[:12]
    rel = f"{CACHE}/{name}/sheet-{key}.png"
    if not os.path.isfile(projects.inside(root, rel)):
        pictures = {f["path"]: Image.open(projects.inside(root, f["path"])).convert("RGB") for f in frames}
        width = max(p.width for p in pictures.values())
        height = max(p.height for p in pictures.values())
        label = 18
        columns = max(len(r) for r in rows.values())
        sheet = Image.new("RGB", (width * columns, (height + label) * len(rows)), "white")
        draw = ImageDraw.Draw(sheet)
        for r, (turn, row) in enumerate(rows.items()):
            for c, f in enumerate(row):
                x, y = c * width, r * (height + label)
                sheet.paste(pictures[f["path"]], (x, y + label))
                draw.text((x + 4, y + 3), f"frame {f['frame']}  yaw {turn:g}", fill=(40, 40, 40))
        out = io.BytesIO()
        sheet.save(out, "PNG")
        projects.write_derived(root, rel, out.getvalue())
    return rel


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
