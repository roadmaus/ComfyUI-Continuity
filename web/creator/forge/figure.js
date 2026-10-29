/**
 * Where the mannequin is: its ground, its feet, its heading. Measured in the tab
 * that drew it, because only the tab has the skinned mesh.
 *
 * Two jobs use it (`pose.js`):
 *
 * - **An imported clip is settled.** Pose Studio's Mixamo import retargets
 *   every frame onto the standing rig by keypoints anchored at the resting
 *   pelvis, so a clip comes in place — and with no height either: the hips
 *   stay at standing height in every frame, and a crouching clip's feet float
 *   (seen on Mixamo's Sneak Walk: the lowest foot 25 to 330 px above the
 *   ground in a 1088 frame). Mixamo's own "In Place" drops only the travel.
 *   So each frame is moved, by its Root bone, until the lowest point of the
 *   mannequin's feet is on the standing figure's ground, plus however far the
 *   clip's own feet are off its ground in that frame (a jump stays a jump). And
 *   the clip is turned to face forward on average, read from the line across
 *   its hips, so one yaw is one view across clips (Sneak Walk came in 20° off
 *   Standard Walk's).
 *
 * - **A drawn frame is measured** (its "marks"): the figure's box in the PNG,
 *   the point on the ground under the hips, the lowest point of each foot,
 *   all in the frame's pixels. The server stores them beside the frame.
 *
 * The mesh is read the way the core's own `computeModelFitZoom` reads it:
 * every vertex skinned by its bones, sampled down to a few thousand.
 */

const FEET = { l: new Set(["foot_l", "ball_l"]), r: new Set(["foot_r", "ball_r"]) };
const SAMPLES = 8000;
const LIFT_FROM = 0.1;
const REST = { bones: {}, bonePositions: {}, modelRotation: [0, 0, 0] };

/** The skinned mesh's points in world space, each with the bone that moves it
 *  most. -> [{x, y, z, bone}] */
function skinned(viewer) {
  const THREE = viewer.THREE;
  const mesh = viewer.skinnedMesh;
  mesh.updateMatrixWorld(true);
  viewer.skeleton?.update();
  const geometry = mesh.geometry;
  const position = geometry.attributes.position;
  const index = geometry.attributes.skinIndex;
  const weight = geometry.attributes.skinWeight;
  const bones = mesh.skeleton.bones;
  const step = Math.max(1, Math.ceil(position.count / SAMPLES));
  const point = new THREE.Vector3();
  const out = [];
  for (let i = 0; i < position.count; i += step) {
    point.fromBufferAttribute(position, i);
    mesh.applyBoneTransform(i, point);
    point.applyMatrix4(mesh.matrixWorld);
    let strongest = 0;
    for (let k = 1; k < 4; k++) if (weight.getComponent(i, k) > weight.getComponent(i, strongest)) strongest = k;
    out.push({ x: point.x, y: point.y, z: point.z, bone: bones[index.getComponent(i, strongest)]?.name });
  }
  return out;
}

function lowest(points) {
  let low = null;
  for (const p of points) if (!low || p.y < low.y) low = p;
  return low;
}

function worldOf(viewer, name) {
  return viewer.bones[name].getWorldPosition(new viewer.THREE.Vector3());
}

/** The pose on the viewer, as we put it there (not an edit). */
function wear(viewer, pose) {
  viewer.setPose(pose, true);
  viewer.skinnedMesh.updateMatrixWorld(true);
}

/** The ground: the lowest point of the standing figure, in world units. */
export function groundOf(viewer) {
  wear(viewer, REST);
  return lowest(skinned(viewer)).y;
}

/** Which way the figure faces, in degrees about the up axis: read off the line
 *  from its right hip to its left, which points +X when it faces +Z. */
function heading(viewer) {
  const left = worldOf(viewer, "thigh_l");
  const right = worldOf(viewer, "thigh_r");
  return Math.atan2(-(left.z - right.z), left.x - right.x);
}

/**
 * Settle a clip the import retargeted: faced forward, feet on the ground.
 *
 * @param viewer  the viewer the import ran on, with the set's body
 * @param poses   the imported poses (`{bones, bonePositions, modelRotation}`)
 * @param lift    how far the clip's own feet are off its ground in each frame,
 *                in the mannequin's units, or null to treat every frame as
 *                standing on it
 */
export function settleClip(viewer, poses, lift, { ground = true, face = true } = {}) {
  const THREE = viewer.THREE;
  let out = poses.map((pose) => ({ ...pose, modelRotation: [...(pose.modelRotation ?? [0, 0, 0])] }));
  if (face && out.length) {
    let sin = 0;
    let cos = 0;
    for (const pose of out) {
      wear(viewer, pose);
      const angle = heading(viewer);
      sin += Math.sin(angle);
      cos += Math.cos(angle);
    }
    const turn = Math.atan2(sin, cos) * 180 / Math.PI;
    out = out.map((pose) => {
      const [x, y, z] = pose.modelRotation;
      return { ...pose, modelRotation: [x, (((y - turn) % 360) + 360) % 360, z] };
    });
  }
  if (!ground) return out;
  const floor = groundOf(viewer);
  return out.map((pose, i) => {
    wear(viewer, pose);
    const feet = skinned(viewer).filter((p) => FEET.l.has(p.bone) || FEET.r.has(p.bone));
    const low = lowest(feet);
    if (!low) return pose;
    const rise = floor + (lift?.[i] ?? 0) - low.y;
    // Root's offset is in its parent's space, which need not be the world's.
    const root = viewer.bones.Root;
    const parent = root.parent;
    const at = worldOf(viewer, "Root");
    const step = parent.worldToLocal(at.clone().add(new THREE.Vector3(0, rise, 0)))
      .sub(parent.worldToLocal(at.clone()));
    const moved = root.position.clone().add(step);
    return { ...pose, bonePositions: { ...pose.bonePositions, Root: [moved.x, moved.y, moved.z] } };
  });
}

/**
 * How far the clip's feet are off its ground in each sampled frame, scaled to
 * the mannequin's legs. Read from the FBX itself, at the times the import
 * sampled, because the import keeps none of it.
 */
export async function clipLift(viewer, file, times, modules) {
  const { THREE, FBXLoader } = modules;
  const url = URL.createObjectURL(file);
  try {
    const root = await new FBXLoader().loadAsync(url);
    const clip = root.animations?.[0];
    if (!clip) return null;
    const named = {};
    root.traverse((node) => {
      if (node.isBone || node.type === "Bone") named[node.name.replace(/^mixamorig\d*:?/i, "")] = node;
    });
    const need = ["LeftUpLeg", "LeftLeg", "LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase"];
    if (need.some((name) => !named[name])) return null;
    const at = (name) => named[name].getWorldPosition(new THREE.Vector3());
    const mixer = new THREE.AnimationMixer(root);
    mixer.clipAction(clip).play();
    let legs = 0;
    const lows = times.map((time, i) => {
      mixer.setTime(time);
      root.updateMatrixWorld(true);
      if (i === 0) legs = at("LeftUpLeg").distanceTo(at("LeftLeg")) + at("LeftLeg").distanceTo(at("LeftFoot"));
      return Math.min(...["LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase"].map((name) => at(name).y));
    });
    wear(viewer, REST);
    const ours = worldOf(viewer, "thigh_l").distanceTo(worldOf(viewer, "calf_l"))
      + worldOf(viewer, "calf_l").distanceTo(worldOf(viewer, "foot_l"));
    if (!(legs > 0)) return null;
    // A foot rolling from heel to toe moves its joints a few centimetres while
    // it stands; read as lift, that floats a crouch (seen: up to 22 px in a
    // 1088 frame on Sneak Walk). A jump clears far more, so less than a tenth
    // of a leg off the clip's ground is standing.
    const floor = Math.min(...lows);
    return lows.map((y) => ((y - floor) / legs < LIFT_FROM ? 0 : (y - floor) * (ours / legs)));
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** What a drawn frame shows, in its pixels (origin top left). `png` is the
 *  frame's data URL; the viewer still holds the pose and the capture camera
 *  it was drawn with. */
export async function marksOf(viewer, png, width, height, floor) {
  const THREE = viewer.THREE;
  const project = (x, y, z) => {
    const p = new THREE.Vector3(x, y, z).project(viewer.captureCamera);
    return [(p.x + 1) / 2 * width, (1 - p.y) / 2 * height];
  };
  const points = skinned(viewer);
  const feet = {};
  for (const side of ["l", "r"]) {
    const low = lowest(points.filter((p) => FEET[side].has(p.bone)));
    feet[side] = low ? project(low.x, low.y, low.z) : null;
  }
  const hips = worldOf(viewer, "pelvis");
  return { bbox: await inked(png, width, height), ground: project(hips.x, floor, hips.z), feet };
}

/** The box around everything in the frame that is not the white ground. */
async function inked(png, width, height) {
  const image = new Image();
  image.src = png;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(image, 0, 0);
  const data = context.getImageData(0, 0, width, height).data;
  let left = width;
  let top = height;
  let right = -1;
  let bottom = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      if (data[i] > 247 && data[i + 1] > 247 && data[i + 2] > 247) continue;
      if (x < left) left = x;
      if (x > right) right = x;
      if (y < top) top = y;
      if (y > bottom) bottom = y;
    }
  }
  return right < 0 ? null : [left, top, right, bottom];
}
