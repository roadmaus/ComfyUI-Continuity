"""The pose stage's mirror: symmetry while posing, and Flip.

    python3 tests/test_pose_symmetry.py

`web/creator/forge/mirror.js` has no Python twin (the server never mirrors a
pose), so this runs it in node against the cases that matter: every bone's twin
is a bone the server accepts, a flip twice is the pose it started as, and a
drag on one side is copied, reflected, onto the other and onto nothing else.
The reflection itself, `[x, -y, -z]`, rests on the rig's world-aligned rest
frames; that was checked in a browser, not here.

Skips itself if node is not installed.
"""

import importlib.util
import os
import sys
import types

import layout

layout.skip_without_node()

# The forge's storage half as a package of its own, as test_forge_pose loads it.
package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
for name in ("problems", "kinds", "targets", "style", "project", "manifest", "pose"):
    spec = importlib.util.spec_from_file_location(f"forgepkg.{name}",
                                                  os.path.join(layout.PY_ROOT, "forge", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"forgepkg.{name}"] = module
    spec.loader.exec_module(module)
pose = sys.modules["forgepkg.pose"]

from harness import check, passed

SCRIPT = """
const m = await import("./web/creator/forge/mirror.js");
const [bones, walk, before, after, ik] = JSON.parse(process.argv[1]);
console.log(JSON.stringify({
  twins: bones.map(m.twin),
  sides: ["hand_l", "hand_r", "head"].map(m.sideOf),
  once: m.flipPose(walk),
  twice: m.flipPose(m.flipPose(walk)),
  edit: m.mirrorEdit(before, after, "l"),
  back: m.mirrorEdit(after, before, "l"),
  guessed: m.mirrorEdit(before, ik),
}));
"""

WALK = {
    "bones": {"upperarm_l": [10.0, 20.0, -60.0], "calf_r": [35.0, 0.0, 0.0], "spine_01": [0.0, 15.0, 5.0]},
    "bonePositions": {"Root": [0.5, 1.0, 0.25]},
    "modelRotation": [0.0, 90.0, 0.0],
}
BEFORE = {"bones": {"head": [5.0, 0.0, 0.0]}, "bonePositions": {}, "modelRotation": [0.0, 0.0, 0.0]}
AFTER = {"bones": {"head": [5.0, 0.0, 0.0], "lowerarm_l": [0.0, -40.0, 0.0]}, "bonePositions": {},
         "modelRotation": [0.0, 0.0, 0.0]}
# An IK drag on the right leg: three right bones move and nothing is selected.
IK = {"bones": {"head": [5.0, 0.0, 0.0], "thigh_r": [-30.0, 0.0, 5.0], "calf_r": [50.0, 0.0, 0.0],
                "foot_r": [-20.0, 0.0, 0.0]}, "bonePositions": {}, "modelRotation": [0.0, 0.0, 0.0]}

bones = sorted(pose.BONES)
with layout.pack() as tree:
    got = layout.in_pack(SCRIPT, tree, [bones, WALK, BEFORE, AFTER, IK])

check("every bone's twin is a bone the server takes", sorted(set(got["twins"]) - pose.BONES), [])
check("and twinning pairs them, left with right", sum(1 for a, b in zip(bones, got["twins"]) if a != b), 46)
check("a bone knows its side", got["sides"], ["l", "r", None])
check("a flip swaps the sides and reflects them", got["once"]["bones"],
      {"upperarm_r": [10.0, -20.0, 60.0], "calf_l": [35.0, 0.0, 0.0], "spine_01": [0.0, -15.0, -5.0]})
check("an offset reflects across the centre", got["once"]["bonePositions"], {"Root": [-0.5, 1.0, 0.25]})
check("a figure turned one way is turned the other", got["once"]["modelRotation"], [0, 270, 0])
check("two flips are the pose it was", got["twice"], WALK)
check("under symmetry, the arm posed on the left is posed on the right",
      got["edit"]["bones"], {"head": [5.0, 0.0, 0.0], "lowerarm_l": [0.0, -40.0, 0.0], "lowerarm_r": [0.0, 40.0, 0.0]})
check("and put back to rest, both sides rest", got["back"]["bones"], {"head": [5.0, 0.0, 0.0]})
check("an IK drag with nothing selected mirrors the side that moved",
      sorted(got["guessed"]["bones"]), ["calf_l", "calf_r", "foot_l", "foot_r", "head", "thigh_l", "thigh_r"])
check("reflected", got["guessed"]["bones"]["thigh_l"], [-30.0, 0.0, -5.0])

passed("the pose mirror swaps, reflects and copies as it should")
