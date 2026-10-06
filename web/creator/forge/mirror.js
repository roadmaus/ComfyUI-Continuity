/**
 * A pose in the mirror: the pose stage's symmetry and its Flip.
 *
 * Pose Studio has no symmetry of its own, so this is ours, and it rests on one
 * fact about its MakeHuman rig, checked in the browser: every bone's rest
 * frame is the world's (identity world rotation), the figure faces +Z and its
 * left side is +X. A left bone and its right twin are therefore reflections of
 * each other through the YZ plane, and reflecting a rotation through that
 * plane keeps its turn about X and reverses its turns about Y and Z. For the
 * rig's XYZ Euler order that is simply `[x, -y, -z]`, and a bone's offset
 * reflects as `[-x, y, z]`. Bones on the centre line (spine, neck, head,
 * pelvis, root) are their own twin.
 *
 * Plain functions on the `{bones, bonePositions, modelRotation}` shape the
 * server keeps, so `tests/test_pose_mirror.py` can run them without a browser.
 */

const SIDE = /_(l|r)$/;

/** `upperarm_l` -> `upperarm_r`; a centre bone is its own twin. */
export function twin(name) {
  return name.replace(SIDE, (_, side) => (side === "l" ? "_r" : "_l"));
}

/** Which side a bone is on: "l", "r", or null on the centre line. */
export function sideOf(name) {
  return SIDE.exec(name)?.[1] ?? null;
}

export const mirrorRotation = ([x, y, z]) => [x, -y, -z];
export const mirrorPosition = ([x, y, z]) => [-x, y, z];

/** A zero rotation is the rest pose, and the stored pose leaves it out. */
const resting = (value) => !value.some((v) => Math.abs(v) > 1e-9);

function reflect(table, mirror, dropRest) {
  const out = {};
  for (const [name, value] of Object.entries(table ?? {})) {
    const reflected = mirror(value).map((v) => (Object.is(v, -0) ? 0 : v));
    if (!(dropRest && resting(reflected))) out[twin(name)] = reflected;
  }
  return out;
}

/** The whole pose seen in a mirror: left and right swap, and each reflects.
 *  A walk's second half is its first half flipped. */
export function flipPose(pose) {
  const [x, y, z] = pose.modelRotation ?? [0, 0, 0];
  return {
    bones: reflect(pose.bones, mirrorRotation, true),
    bonePositions: reflect(pose.bonePositions, mirrorPosition, false),
    modelRotation: [x, (360 - y) % 360, (360 - z) % 360],
  };
}

const same = (a, b) => (a == null && b == null) || (a != null && b != null && a.every((v, i) => Math.abs(v - b[i]) < 1e-9));

/** The sided bones whose rotation or offset differ between two poses. */
function changed(before, after) {
  const names = new Set();
  for (const key of ["bones", "bonePositions"]) {
    const a = before?.[key] ?? {};
    const b = after?.[key] ?? {};
    for (const name of new Set([...Object.keys(a), ...Object.keys(b)])) {
      if (sideOf(name) && !same(a[name], b[name])) names.add(name);
    }
  }
  return [...names];
}

/**
 * With symmetry on: the side that was just posed, copied onto the other.
 *
 * `side` is the side of the bone that was being dragged, when the viewer knows
 * it. Without it (an IK drag moves a chain and selects no bone) the side that
 * changed more wins. The other side's own changes, if any, are replaced: under
 * symmetry the two are one.
 */
export function mirrorEdit(before, after, side = null) {
  const moved = changed(before, after);
  if (!moved.length) return after;
  if (!side) {
    const left = moved.filter((name) => sideOf(name) === "l").length;
    side = left >= moved.length - left ? "l" : "r";
  }
  const out = {
    bones: { ...after.bones },
    bonePositions: { ...after.bonePositions },
    modelRotation: after.modelRotation,
  };
  for (const name of moved.filter((n) => sideOf(n) === side)) {
    const other = twin(name);
    const rotation = after.bones?.[name];
    if (rotation) out.bones[other] = mirrorRotation(rotation);
    else delete out.bones[other];
    const position = after.bonePositions?.[name];
    if (position) out.bonePositions[other] = mirrorPosition(position);
    else delete out.bonePositions[other];
  }
  return out;
}
