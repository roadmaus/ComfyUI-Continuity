"""Pose sets and the jobs a browser tab does for them (`creator/forge/pose.py`).

    python3 tests/test_forge_pose.py

The CLI round trip is in `test_forge_parity.py`; this suite pins what it cannot
reach from a shell in reasonable time: a job nobody claims fails with a sentence
instead of hanging, a tab that goes quiet fails its job, a second tab cannot take
or answer a job the first holds, a frame of the wrong size is not cached, and a
pose keeps only what draws the figure. No ComfyUI, no numpy.
"""

import base64
import importlib.util
import os
import struct
import sys
import tempfile
import types
import zlib

import layout
from harness import FAILURES, check

package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
for name in ("problems", "kinds", "targets", "style", "project", "manifest", "pose", "api"):
    spec = importlib.util.spec_from_file_location(f"forgepkg.{name}",
                                                  os.path.join(layout.PY_ROOT, "forge", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"forgepkg.{name}"] = module
    spec.loader.exec_module(module)
api = sys.modules["forgepkg.api"]
pose = sys.modules["forgepkg.pose"]
project = sys.modules["forgepkg.project"]
ForgeError = sys.modules["forgepkg.problems"].ForgeError


def refused(label, fn, code):
    try:
        fn()
    except ForgeError as problem:
        check(label, problem.code, code)
        return problem
    FAILURES.append(f"{label}: not refused")
    return None


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"\xff" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def url(data):
    return "data:image/png;base64," + base64.b64encode(data).decode()


base = os.path.join(tempfile.mkdtemp(prefix="forge-pose-"), "forge")
project.create(base, "game")
announced = []
host = api.Host(base, tabs=lambda: 1, announce=lambda event, data: announced.append((event, data)))


def call(path, **params):
    method = "GET" if path in ("/poses", "/pose/show", "/pose/job") else "POST"
    status, answer = api.call(host, method, api.PREFIX + path, params)
    if status != 200:
        raise ForgeError(answer["problem"], answer["code"], status)
    return answer


# ---- a pose keeps what draws the figure ----------------------------------------

mixamo = {"bones": {"thigh_l": [12.5, 0, 0]}, "bonePositions": {"Root": [0, 0.9, 0]},
          "modelRotation": [0, 45, 0], "camera": {"posX": 3}, "_mixamo_sourceWorldRotations": {"x": [0, 0, 0, 1]}}
check("a pose keeps rotations, translations and the model's turn",
      pose.normalise_pose(mixamo),
      {"bones": {"thigh_l": [12.5, 0.0, 0.0]}, "bonePositions": {"Root": [0.0, 0.9, 0.0]},
       "modelRotation": [0.0, 45.0, 0.0]})
refused("a rotation that is not a number", lambda: pose.normalise_pose({"bones": {"head": [1, "a", 0]}}), "pose.value")
refused("an infinite rotation", lambda: pose.normalise_pose({"bones": {"head": [1, float("inf"), 0]}}), "pose.value")
refused("a body slider out of range", lambda: pose.normalise_body({"age": 120}), "pose.body")
check("the male-only sliders are dropped, not refused",
      pose.normalise_body({"penis_len": 0.5, "age": 40})["age"], 40)
check("a set of ours pastes as itself",
      pose.from_paste({"name": "x", "fps": 8, "body": {"age": 30}, "poses": [{"bones": {}}]})[1:], ({"age": 30}, 8))
check("Pose Studio in animation mode keeps its frames in image_poses",
      len(pose.from_paste({"poses": [], "image_poses": [{}, {}]})[0]), 2)
check("a turn wraps", pose.turned(pose.rest_pose(), 450)["modelRotation"], [0.0, 90.0, 0.0])
check("a PNG's size is read from its header", pose.png_size(png(7, 3)), (7, 3))
check("and anything else is not a PNG", pose.png_size(b"GIF89a" + bytes(30)), None)

# ---- a render, claimed by one tab ------------------------------------------------

call("/pose/new", project="game", set="idle")
job = call("/pose/render", project="game", set="idle", width=64, height=96)
check("a render is announced to every tab", announced[-1][0], "continuity.pose.job")
check("and waits for one", job["state"], "waiting")
task = call("/pose/claim", job=job["job"], tab="a")
check("the first tab gets the poses, body and size", (task["width"], task["height"], len(task["frames"])),
      (64, 96, 1))
refused("a second tab cannot take it", lambda: call("/pose/claim", job=job["job"], tab="b"), "job.taken")
refused("nor answer it", lambda: call("/pose/done", job=job["job"], tab="b", frames=[url(png(64, 96))]),
        "job.taken")
refused("a frame of the wrong size is refused",
        lambda: call("/pose/done", job=job["job"], tab="a", frames=[url(png(64, 64))]), "pose.upload")
refused("as is one that is not a PNG",
        lambda: call("/pose/done", job=job["job"], tab="a", frames=[url(b"not a png")]), "pose.upload")
check("and neither was cached", call("/pose/render", project="game", set="idle", width=64, height=96)["drawn"],
      job["drawn"])
done = call("/pose/done", job=job["job"], tab="a", frames=[url(png(64, 96))])
check("the tab's answer completes the job", done["state"], "done")
check("and the frame is on disk", os.path.isfile(os.path.join(base, "game", done["frames"][0]["path"])), True)
check("under build/, where derived files go", done["frames"][0]["path"].startswith("build/poses/idle/000-"), True)

# A changed pose redraws only the frame that changed.
call("/pose/paste", project="game", set="two", data=[{}, {"bones": {"head": [5, 0, 0]}}])
first = call("/pose/render", project="game", set="two", width=64, height=64)
call("/pose/claim", job=first["job"], tab="a")
call("/pose/done", job=first["job"], tab="a", frames=[url(png(64, 64))] * 2)
call("/pose/set", project="game", set="two", frame=1, bones={"head": [9, 0, 0]})
second = call("/pose/render", project="game", set="two", width=64, height=64)
check("only the changed frame is drawn again", [f["frame"] for f in second["frames"]
                                                 if f["path"] in second["drawn"]], [1])
check("a zero rotation leaves the pose", pose.set_bones(base, "game", "two", 1, {"head": [0, 0, 0]})["poses"][1]["bones"],
      {})

# ---- jobs that nobody finishes ----------------------------------------------------

pose.CLAIM_WAIT = 0
orphan = call("/pose/render", project="game", set="two", width=80, height=80)
gone = call("/pose/job", job=orphan["job"])
check("a job no tab takes fails", (gone["state"], gone["code"]), ("failed", "pose.no_tab"))
check("with a sentence that says what to do", "open ComfyUI in a browser" in gone["problem"], True)
pose.CLAIM_WAIT = 15

pose.RUN_WAIT["render"] = 0
quiet = call("/pose/render", project="game", set="two", width=80, height=80)
call("/pose/claim", job=quiet["job"], tab="a")
check("a tab that goes quiet fails its job", call("/pose/job", job=quiet["job"])["code"], "pose.tab_quiet")
pose.RUN_WAIT["render"] = 120

broken = call("/pose/render", project="game", set="two", width=80, height=80)
call("/pose/claim", job=broken["job"], tab="a")
failed = call("/pose/done", job=broken["job"], tab="a", problem="WebGL is not available")
check("a tab can say why it could not", (failed["state"], failed["problem"], failed["code"]),
      ("failed", "WebGL is not available", "pose.render_failed"))

host_without = api.Host(base, tabs=lambda: 0)
status, answer = api.call(host_without, "POST", api.PREFIX + "/pose/render",
                          {"project": "game", "set": "two", "width": 96, "height": 96})
check("no tab connected: refused before anything is queued", (status, answer["code"]), (409, "pose.no_tab"))
status, answer = api.call(host_without, "POST", api.PREFIX + "/pose/render",
                          {"project": "game", "set": "idle", "width": 64, "height": 96})
check("but what is drawn already needs no tab", (status, answer["state"]), (200, "done"))

refused("a set name is checked", lambda: call("/pose/new", project="game", set="../x"), "set.invalid")
refused("a frame too big", lambda: call("/pose/render", project="game", set="idle", width=4096), "pose.size")
kept = call("/pose/rm", project="game", set="idle")["kept"]
check("rm keeps the set as a version", kept.startswith(".versions/poses/idle.json/"), True)
