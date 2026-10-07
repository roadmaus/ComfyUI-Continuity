"""Animating a pose set: keys and in-betweens, flip, joints, views (`creator/forge/pose.py`).

    python3 tests/test_pose_keys.py

A set with keys is a set somebody posed on a few frames and the server drew
the rest, so this pins what the in-betweens are: half way between two keys is
the turn half way between them (not the Euler numbers averaged), an ease bends
that, a loop runs the last key back into the first, and editing an in-between
makes it a key rather than losing the edit to the next recompute. Then the
routes an agent poses through — joint words, flip, keys — and the multi-view
render with its contact sheet, all through `api.call` on a temporary folder.
The sheet needs PIL, as on ComfyUI; nothing else here does.
"""

import base64
import importlib.util
import math
import os
import struct
import sys
import tempfile
import types
import zlib

import layout
from harness import FAILURES, check, passed

package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
for name in ("problems", "kinds", "targets", "style", "project", "manifest", "joints", "pose", "api"):
    spec = importlib.util.spec_from_file_location(f"forgepkg.{name}",
                                                  os.path.join(layout.PY_ROOT, "forge", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"forgepkg.{name}"] = module
    spec.loader.exec_module(module)
api = sys.modules["forgepkg.api"]
pose = sys.modules["forgepkg.pose"]
joints = sys.modules["forgepkg.joints"]
project = sys.modules["forgepkg.project"]
ForgeError = sys.modules["forgepkg.problems"].ForgeError

base = os.path.join(tempfile.mkdtemp(prefix="forge-keys-"), "forge")
project.create(base, "game")
host = api.Host(base, tabs=lambda: 1, announce=lambda event, data: None)


def call(path, **params):
    method = "GET" if path in ("/pose/show", "/pose/joints") else "POST"
    status, answer = api.call(host, method, api.PREFIX + path, params)
    if status != 200:
        raise ForgeError(answer["problem"], answer["code"], status)
    return answer


def refused(label, fn, code):
    try:
        fn()
    except ForgeError as problem:
        check(label, problem.code, code)
        return
    FAILURES.append(f"{label}: not refused")


def near(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def frame(bones):
    return {"bones": bones, "bonePositions": {}, "modelRotation": [0.0, 0.0, 0.0]}


# ---- in-betweens --------------------------------------------------------------------

poses = [frame({"head": [40.0, 0.0, 0.0]})] + [frame({}) for _ in range(3)] + [frame({"head": [80.0, 0.0, 0.0]})]
data = pose.make_set("nod", poses, timing={"keys": [0, 4]})
check("frames between two keys are drawn between them", [round(p["bones"]["head"][0], 6) for p in data["poses"]],
      [40.0, 50.0, 60.0, 70.0, 80.0])
check("the keys are said, each with its ease", data["keys"], [{"frame": 0, "ease": "linear"}, {"frame": 4, "ease": "linear"}])

eased = pose.make_set("nod", poses, timing={"keys": [{"frame": 0, "ease": "ease-in-out"}, 4]})
check("an ease bends the stretch that leaves its key",
      [round(p["bones"]["head"][0], 4) for p in eased["poses"]], [40.0, 46.25, 60.0, 73.75, 80.0])
held = pose.make_set("nod", poses, timing={"keys": [{"frame": 0, "ease": "hold"}, 4]})
check("hold stays on the key until the next", [p["bones"]["head"][0] for p in held["poses"]], [40.0] * 4 + [80.0])

# Two turns about different axes: averaging the Euler numbers would give a pose
# neither key is on the way to; the short turn between them does not.
a, b = frame({"upperarm_l": [0.0, 0.0, 80.0]}), frame({"upperarm_l": [80.0, 0.0, 0.0]})
half = pose._blend(a, b, 0.5)["bones"]["upperarm_l"]
qa = joints.matrix_quaternion(joints.degrees_matrix([0.0, 0.0, 80.0]))
qb = joints.matrix_quaternion(joints.degrees_matrix([80.0, 0.0, 0.0]))
qh = joints.matrix_quaternion(joints.degrees_matrix(half))


def angle(p, q):
    return 2 * math.degrees(math.acos(min(1.0, abs(sum(x * y for x, y in zip(p, q))))))


check("half way is half the turn from each key", (round(angle(qa, qh), 6), round(angle(qh, qb), 6)),
      (round(angle(qa, qb) / 2, 6),) * 2)
check("not the Euler numbers averaged", near(half, [40.0, 0.0, 40.0], 0.5), False)

loop = [frame({"head": [0.0, 0.0, 0.0]}), frame({}), frame({"head": [30.0, 0.0, 0.0]}), frame({}), frame({}), frame({})]
looped = pose.make_set("bob", loop, timing={"keys": [0, 2], "loop": True})
check("a loop runs the last key back into the first",
      [round(p["bones"].get("head", [0.0])[0], 6) for p in looped["poses"]], [0.0, 15.0, 30.0, 22.5, 15.0, 7.5])
open_ended = pose.make_set("bob", loop, timing={"keys": [2, 4]})
check("without one, the frames past either end hold their key",
      [round(p["bones"].get("head", [0.0])[0], 6) for p in open_ended["poses"]], [30.0, 30.0, 30.0, 15.0, 0.0, 0.0])

moved = [{"bones": {}, "bonePositions": {"pelvis": [0.0, 1.0, 0.0]}, "modelRotation": [0.0, 0.0, 0.0]},
         frame({}), frame({})]
refused("a translation only one key has cannot be blended",
        lambda: pose.make_set("hop", moved, timing={"keys": [0, 2]}), "pose.tween_position")
refused("a key past the end", lambda: pose.make_set("nod", poses, timing={"keys": [0, 9]}), "pose.keys")
refused("an ease nobody knows", lambda: pose.make_set("nod", poses, timing={"keys": [{"frame": 0, "ease": "bounce"}]}),
        "pose.ease")

# ---- through the routes ----------------------------------------------------------

call("/pose/new", project="game", set="wave")
walk = call("/pose/keys", project="game", set="wave", keys=[0, {"frame": 4, "ease": "ease-in-out"}], length=8,
            loop=True)["set"]
check("keys and a length make a set of in-betweens", (len(walk["poses"]), walk["keys"], walk["loop"]),
      (8, [{"frame": 0, "ease": "linear"}, {"frame": 4, "ease": "ease-in-out"}], True))
after = call("/pose/set", project="game", set="wave", frame=4, joints={"shoulder_l.raise": 150, "elbow_l.bend": 30},
             mirror=True)["set"]
read = joints.read(after["poses"][4])
check("a frame is posed by joint words, both sides with mirror",
      (read["shoulder_l"]["raise"], read["shoulder_r"]["raise"], read["elbow_r"]["bend"]), (150.0, 150.0, 30.0))
check("and its in-betweens follow it", 39 < joints.read(after["poses"][2])["shoulder_l"]["raise"] < 150, True)
check("round the loop too", 39 < joints.read(after["poses"][6])["shoulder_l"]["raise"] < 150, True)

edited = call("/pose/set", project="game", set="wave", frame=2, joints={"head.turn": 30})["set"]
check("posing an in-between makes it a key, with the ease of its stretch",
      edited["keys"], [{"frame": 0, "ease": "linear"}, {"frame": 2, "ease": "linear"},
                       {"frame": 4, "ease": "ease-in-out"}])
check("so the next write keeps the edit", joints.read(edited["poses"][2])["head"]["turn"], 30.0)
raw = call("/pose/set", project="game", set="wave", frame=0, bones={"head": [10, 0, 0]})["set"]
check("raw bones still turn", raw["poses"][0]["bones"]["head"], [10.0, 0.0, 0.0])
refused("a limit is refused through the route",
        lambda: call("/pose/set", project="game", set="wave", frame=0, joints={"knee_l.bend": -20}), "pose.limit")
refused("a set with nothing to set", lambda: call("/pose/set", project="game", set="wave", frame=0), "pose.shape")

flipped = call("/pose/flip", project="game", set="wave", frame=2, to=6)["set"]
check("a frame flipped onto another", joints.read(flipped["poses"][6])["head"]["turn"], -30.0)
check("which becomes a key", 6 in [k["frame"] for k in flipped["keys"]], True)

shown = call("/pose/show", project="game", set="wave", joints=True)
check("show reads every frame as joints", (len(shown["joints"]), shown["joints"][2]["head"]["turn"]), (8, 30.0))
check("the vocabulary is served", "shoulder_l/_r" in [j["joint"] for j in call("/pose/joints")["joints"]], True)

copy = call("/pose/new", project="game", set="wave2", **{"from": "wave"})["set"]
check("a copied set keeps its keys and loop", (copy["keys"], copy["loop"]), (flipped["keys"], True))
pasted = call("/pose/paste", project="game", set="wave", replace=True, data={**flipped, "poses": flipped["poses"]})["set"]
check("a set pasted over itself (the bench's save) keeps its keys", pasted["keys"], flipped["keys"])

shorter = call("/pose/keys", project="game", set="wave", length=5)["set"]
check("shortening drops the frames and keys past the end", (len(shorter["poses"]), [k["frame"] for k in shorter["keys"]]),
      (5, [0, 2, 4]))
refused("looping a set with no keys", lambda: call("/pose/keys", project="game", set="wave2", clear=True, loop=True),
        "pose.keys")
cleared = call("/pose/keys", project="game", set="wave", clear=True)["set"]
check("cleared, every frame is its own again", ("keys" in cleared, "loop" in cleared), (False, False))

# ---- views and the contact sheet -----------------------------------------------------


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"\x80" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


job = call("/pose/render", project="game", set="wave", frames=[0, 1], width=64, height=96, views=[0, 90])
check("views draw each frame at each yaw, in one job", [(f["frame"], f["yaw"]) for f in job["frames"]],
      [(0, 0.0), (1, 0.0), (0, 90.0), (1, 90.0)])
refused("a sheet of frames not drawn yet",
        lambda: call("/pose/sheet", project="game", set="wave", frames=[0, 1], width=64, height=96, views=[0, 90]),
        "pose.undrawn")
task = call("/pose/claim", job=job["job"], tab="t")
picture = "data:image/png;base64," + base64.b64encode(png(64, 96)).decode()
call("/pose/done", job=job["job"], tab="t", frames=[picture] * len(task["frames"]))
sheet = call("/pose/sheet", project="game", set="wave", frames=[0, 1], width=64, height=96, views=[0, 90])["path"]
refused("a sheet of more pictures than a render draws",
        lambda: pose.contact_sheet(base, "game", "wave", [{"frame": 0, "path": "x.png"}] * (pose.MAX_RENDER + 1)),
        "pose.many")
from PIL import Image  # noqa: E402 — only the sheet needs it

with Image.open(os.path.join(base, "game", sheet)) as drawn:
    check("the sheet is a row per view, a column per frame", drawn.size, (128, 2 * (96 + 18)))

passed("keys, in-betweens, joints, flips and views work as they say")
