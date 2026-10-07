"""The joint vocabulary over raw bone rotations (`creator/forge/joints.py`).

    python3 tests/test_pose_joints.py

What a joint's words mean on the figure — that `shoulder_l.raise=90` holds the
arm out level, that `elbow.twist` + turns the palm up — was checked by drawing
each motion on the mannequin in a browser (spec §7.9); a suite cannot look. What
it pins is everything that has to stay true for those checks to keep holding:
the standing pose reads as the measured A-pose, every motion written reads back
as itself and leaves the others alone, the right side means what the left means,
limits refuse rather than clamp, and the two things copied from the vendored
JavaScript — three.js's Euler conversions and Pose Studio's hand presets — still
match it. Those last two shell out to node and are skipped without it.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types

import layout
from harness import FAILURES, check, passed

# The forge's storage half as a package of its own, as test_forge_pose loads it.
package = types.ModuleType("forgepkg")
package.__path__ = [os.path.join(layout.PY_ROOT, "forge")]
sys.modules["forgepkg"] = package
for name in ("problems", "joints"):
    spec = importlib.util.spec_from_file_location(f"forgepkg.{name}",
                                                  os.path.join(layout.PY_ROOT, "forge", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"forgepkg.{name}"] = module
    spec.loader.exec_module(module)
joints = sys.modules["forgepkg.joints"]
ForgeError = sys.modules["forgepkg.problems"].ForgeError

REST = {"bones": {}, "bonePositions": {}, "modelRotation": [0.0, 0.0, 0.0]}


def refused(label, fn, code):
    try:
        fn()
    except ForgeError as problem:
        check(label, problem.code, code)
        return
    FAILURES.append(f"{label}: not refused")


def close(a, b, tol=0.05):
    return all(abs(a[k] - b[k]) <= tol for k in b)


# ---- the standing pose -------------------------------------------------------------

rest = joints.read(REST)
check("the standing arm is raised about 40 degrees", round(rest["shoulder_l"]["raise"]), 40)
check("with the elbow bent about 47", round(rest["elbow_l"]["bend"]), 47)
check("and the right side reads the same", rest["shoulder_r"], rest["shoulder_l"])
check("a centre joint stands at zero", rest["spine"], {"bend": 0.0, "lean": 0.0, "turn": 0.0})
check("so does the wrist", rest["wrist_l"], {"side": 0.0, "bend": 0.0, "twist": 0.0})

# ---- every motion reads back as itself -----------------------------------------

drifted = []
for name, joint in joints.JOINTS.items():
    for side in ("l", "r") if name in joints.SIDED else (None,):
        full = f"{name}_{side}" if side else name
        for motion in joint.motions:
            low, high = joint.limits[motion]
            for value in (low * 0.6, high * 0.6, low * 0.95, high * 0.95):
                posed = joints.set_joints(REST, {f"{full}.{motion}": value})
                got = joints.joint_angles(posed, full)
                want = {**joints.joint_angles(REST, full), motion: round(value, 1)}
                if not close(got, want, 0.15):
                    drifted.append((full, motion, value, got))
check("every motion of every joint reads back as written, the others kept", drifted, [])

arm = joints.set_joints(REST, {"shoulder_l.raise": 90, "elbow_l.bend": 10})
arm = joints.set_joints(arm, {"elbow_l.bend": 120})
check("setting one motion keeps the joint's others", joints.joint_angles(arm, "shoulder_l")["raise"], 90.0)
check("and a later write wins", joints.joint_angles(arm, "elbow_l")["bend"], 120.0)

left = joints.set_joints(REST, {"shoulder_l.raise": 90, "hip_l.forward": 60, "wrist_l.bend": 30})
right = joints.set_joints(REST, {"shoulder_r.raise": 90, "hip_r.forward": 60, "wrist_r.bend": 30})
check("the right side is the left in a mirror", joints.flip_pose(left)["bones"].keys(), right["bones"].keys())
check("to the degree", all(abs(a - b) < 1e-9 for k in right["bones"]
                           for a, b in zip(joints.flip_pose(left)["bones"][k], right["bones"][k])), True)
check("--mirror sends the twin too", joints.mirrored_keys({"elbow_l.bend": 90, "head.turn": 10}),
      {"elbow_l.bend": 90, "elbow_r.bend": 90, "head.turn": 10})

spine = joints.set_joints(REST, {"spine.bend": 30})["bones"]
check("the spine's bend is shared by its three bones", [round(spine[b][0], 6) for b in
                                                        ("spine_01", "spine_02", "spine_03")], [10.0] * 3)

# ---- refusals ---------------------------------------------------------------------

refused("past a limit is refused, not clamped", lambda: joints.set_joints(REST, {"elbow_l.bend": 170}), "pose.limit")
refused("a joint the figure lacks", lambda: joints.set_joints(REST, {"tail.bend": 1}), "pose.joint")
refused("a sided joint needs its side", lambda: joints.set_joints(REST, {"elbow.bend": 1}), "pose.joint")
refused("a centre joint has none", lambda: joints.set_joints(REST, {"head_l.turn": 1}), "pose.joint")
refused("a motion the joint lacks", lambda: joints.set_joints(REST, {"elbow_l.raise": 1}), "pose.motion")
refused("a hand shape Pose Studio lacks", lambda: joints.set_joints(REST, {"hand_l": "peace"}), "pose.hand")
refused("a number that is not one", lambda: joints.set_joints(REST, {"head.turn": "a"}), "pose.value")

fist = joints.set_joints(REST, {"hand_l": "fist"})
check("a hand shape turns that hand's fingers", sorted({b[-1] for b in fist["bones"]}), ["l"])
check("and rest puts them back", joints.set_joints(fist, {"hand_l": "rest"})["bones"], {})

check("every joint is in the vocabulary", len(joints.vocabulary()), len(joints.JOINTS) + 1)

# ---- what is copied from the vendored JavaScript -----------------------------------

if shutil.which("node"):
    SCRIPT = """
const THREE = await import("./web/creator/vendor/posestudio/three.module.mjs");
const { HAND_PRESETS } = await import("./web/creator/vendor/posestudio/vnccs_hand_presets.mjs");
const [angles, quats] = JSON.parse(process.argv[1]);
const out = { euler: [], quat: [], hands: {} };
for (const a of angles) {
  const m = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(...a, "XYZ"));
  const e = new THREE.Euler().setFromRotationMatrix(m, "XYZ");
  out.euler.push([m.elements, [e.x, e.y, e.z]]);
}
for (const q of quats) {
  const e = new THREE.Euler().setFromQuaternion(new THREE.Quaternion(...q).normalize(), "XYZ");
  out.quat.push([e.x, e.y, e.z]);
}
for (const [name, p] of Object.entries(HAND_PRESETS)) out.hands[name.toLowerCase()] = [p.preset_l, p.preset_r];
console.log(JSON.stringify(out));
"""
    angles = [[0.3, -1.1, 2.0], [-2.5, 0.7, -0.4], [1.0, 1.5, 0.2], [0.0, 0.0, 0.0]]
    quats = [list(q) for q in joints.HANDS["fist"].values()]
    proc = subprocess.run(["node", "--input-type=module", "--eval", SCRIPT, "--", json.dumps([angles, quats])],
                          capture_output=True, text=True, cwd=layout.ROOT)
    if proc.returncode:
        FAILURES.append(f"node failed: {proc.stderr[-500:]}")
    else:
        got = json.loads(proc.stdout)
        worst = 0.0
        for a, (elements, back) in zip(angles, got["euler"]):
            ours = joints.euler_matrix(*a)
            # three's elements are column-major.
            worst = max(worst, max(abs(ours[r][c] - elements[c * 4 + r]) for r in range(3) for c in range(3)))
            worst = max(worst, max(abs(x - y) for x, y in zip(joints.matrix_euler(ours), back)))
        for q, e in zip(quats, got["quat"]):
            worst = max(worst, max(abs(x - y) for x, y in zip(joints.matrix_euler(joints.quaternion_matrix(q)), e)))
        check("Euler and quaternion conversions agree with three.js", worst < 1e-9, True)
        check("the hand shapes are Pose Studio's", sorted(got["hands"]), sorted(joints.HANDS))
        same, mirrored = True, True
        for shape, (preset_l, preset_r) in got["hands"].items():
            for finger in joints.FINGERS:
                same &= all(abs(x - y) < 1e-12 for x, y in zip(preset_l[finger], joints.HANDS[shape][finger]))
                ours = joints.hand_bones("r", shape)[f"{finger}_r"]
                theirs = joints.matrix_degrees(joints.quaternion_matrix(preset_r[finger]))
                a, b = joints.degrees_matrix(ours), joints.degrees_matrix(theirs)
                mirrored &= all(abs(a[r][c] - b[r][c]) < 1e-9 for r in range(3) for c in range(3))
        check("copied quaternion for quaternion", same, True)
        check("and the right hand, mirrored here, is their right hand", mirrored, True)
else:
    print("node not found: the three.js and hand preset checks were skipped")

passed("the joints read and write as they say")
