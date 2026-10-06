/**
 * The browser half of a pose job (spec §7.9; the server half is
 * `creator/forge/pose.py`).
 *
 * The mannequin is drawn by VNCCS Pose Studio's WebGL core, vendored under
 * `../vendor/posestudio/`, and only a browser has WebGL. So when the forge is
 * asked for mannequin pictures — by the bench, the CLI or an agent — the
 * server announces a job on the websocket and any open ComfyUI tab does it:
 * it claims the job, builds a `PoseViewerCore` on a canvas nobody sees, draws
 * or retargets, and posts the result back. Upstream needs the one tab holding
 * its node; we need a tab.
 *
 * We are a client of their core, not a copy of their widget, so the widget's
 * set-up is done here: the morph worker solves the body sliders, the core
 * `loadData`s the result, the directional skydome goes off (the core's
 * default draws a grid behind the figure; the widget's is off), and the
 * widget's two default lights go on, on white. Proven headless in the lab
 * spike with exactly these steps.
 *
 * The pose page (`posepage.js`) builds its editing viewer from the same parts,
 * so what an artist poses is lit and shaped as the job draws it.
 *
 * Nothing here runs on import: `creator.js` calls `listenForPoseJobs` from
 * the extension's setup, and the 2 MB of three and core are imported only
 * when the first job arrives.
 */

import { api } from "../../../../scripts/api.js";
import { forgeCall } from "../api.js";

const VENDOR = "../vendor/posestudio/";
export const WHITE = [255, 255, 255];
// The widget's defaults (vnccs_pose_studio.js `lightParams`).
export const LIGHTS = [
  { type: "directional", color: "#ffffff", intensity: 2.0, x: 10, y: 20, z: 30 },
  { type: "ambient", color: "#505050", intensity: 1.0, x: 0, y: 0, z: 0 },
];
// A tab nobody is looking at has its timers throttled to a second or more, and
// the core is polled until it is ready to capture; a visible tab is let take
// the job first.
const HIDDEN_DELAY = 2000;

const TAB = crypto.randomUUID();
let modules = null;
let busy = Promise.resolve();

export function vendored() {
  modules ??= Promise.all([
    import(`${VENDOR}vnccs_pose_studio_core.mjs`),
    import(`${VENDOR}vnccs_mixamo_import.mjs`),
  ]).then(([core, mixamo]) => ({ PoseViewerCore: core.PoseViewerCore, importFBX: mixamo.importMixamoFBXAnimation }));
  return modules;
}

/** The body sliders -> the mesh `loadData` takes, solved in the vendored
 *  worker the way the widget does it. */
export function solveBody(body) {
  const worker = new Worker(new URL(`${VENDOR}vnccs_pose_morph_worker.mjs`, import.meta.url), { type: "module" });
  return new Promise((resolve, reject) => {
    worker.onerror = (event) => { worker.terminate(); reject(new Error(event.message || "the morph worker failed")); };
    worker.onmessage = ({ data: m }) => {
      if (m.type === "error") { worker.terminate(); reject(new Error(m.message)); return; }
      if (m.type !== "result") return;
      worker.terminate();
      const s = m.staticData;
      const bones = s.bones.map((bone, i) => {
        const head = Array.from(m.bonePositions.subarray(i * 6, i * 6 + 3));
        const tail = Array.from(m.bonePositions.subarray(i * 6 + 3, i * 6 + 6));
        return { name: bone.name, parent: bone.parent || null, headPos: head, tailPos: tail,
                 length: Math.hypot(tail[0] - head[0], tail[1] - head[1], tail[2] - head[2]) };
      });
      resolve({ status: "success", vertices: m.vertices, uvs: s.uvs, indices: s.indices, bones,
                skinIndices: s.skinIndices, skinWeights: s.skinWeights,
                landmarks: m.landmarks || {}, landmark_indices: m.landmarkIndices || {} });
    };
    worker.postMessage({ type: "solve", seq: 1, clientId: TAB, includeStatic: true,
                         params: { ...body, show_genitals: false } });
  });
}

/** A ready viewer on an off-screen canvas, and how to put it away. The pose
 *  page keeps one for its frame strip's thumbnails. */
export async function makeViewer(body, width, height) {
  const { PoseViewerCore } = await vendored();
  const holder = document.createElement("div");
  holder.style.cssText = "position:fixed;left:-10000px;top:0;opacity:0;pointer-events:none";
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  holder.append(canvas);
  document.body.append(holder);
  const viewer = new PoseViewerCore(canvas, {
    skinMode: "naked", enableTextureSkinning: true, enableMultiPass: true,
    showSkeletonHelper: false, showCaptureFrame: false, syncMode: "end",
  });
  const dispose = () => { try { viewer.dispose(); } finally { holder.remove(); } };
  try {
    await viewer.init();
    viewer.setSkinMode("naked");
    viewer.setDirectionalSkydomeVisible(false);
    viewer.updateLights(LIGHTS);
    viewer.loadData(await solveBody(body), true);
    for (let i = 0; i < 100 && !viewer.isCaptureReady(); i++) await new Promise((r) => setTimeout(r, 100));
    if (!viewer.isCaptureReady()) throw new Error("the mannequin did not finish loading");
  } catch (err) {
    dispose();
    throw err;
  }
  return { viewer, dispose };
}

/** A render task -> one PNG data URL per frame, each at the task's size. */
export async function drawFrames(task) {
  const { viewer, dispose } = await makeViewer(task.body, task.width, task.height);
  try {
    return task.frames.map(({ pose }) => {
      viewer.setPose(pose, true);
      viewer.updateLights(LIGHTS);
      // The core's pitch turns the camera below the figure for a positive
      // angle; ours is how far it looks down, so it goes in negated.
      const png = viewer.capture(task.width, task.height, 1, WHITE, 0, 0, 0, -(task.pitch || 0));
      if (!png) throw new Error("the viewer could not capture");
      return png;
    });
  } finally {
    dispose();
  }
}

/** An FBX clip -> the mannequin's poses, one per sampled frame. The import
 *  retargets every frame onto the standing rig, so a walk comes in in place. */
export async function retarget(file, fps, maxFrames) {
  const { importFBX } = await vendored();
  const { viewer, dispose } = await makeViewer({}, 256, 256);
  try {
    const result = await importFBX(file, viewer, { fps, maxFrames });
    return result.poseSamples;
  } finally {
    dispose();
  }
}

async function inputFile(filename, subfolder) {
  const query = new URLSearchParams({ filename, subfolder, type: "input" });
  const response = await api.fetchApi(`/view?${query}`);
  if (!response.ok) throw new Error(`could not read ${filename} from the input folder (${response.status})`);
  return new File([await response.blob()], filename);
}

async function work(job) {
  let task;
  try {
    task = await forgeCall("/pose/claim", { job, tab: TAB });
  } catch {
    return;  // another tab took it, or it expired
  }
  try {
    const answer = task.kind === "render"
      ? { frames: await drawFrames(task) }
      : { poses: await retarget(await inputFile(task.filename, task.subfolder), task.fps, task.max_frames) };
    await forgeCall("/pose/done", { job, tab: TAB, ...answer });
  } catch (err) {
    console.error("[continuity] pose job failed", err);
    await forgeCall("/pose/done", { job, tab: TAB, problem: String(err?.message || err) }).catch(() => {});
  }
}

/** Do the forge's pose jobs in this tab. One at a time: a job is claimed only
 *  once the one before it is finished, so a free tab can take it meanwhile. */
export function listenForPoseJobs() {
  api.addEventListener("continuity.pose.job", ({ detail }) => {
    busy = busy.then(async () => {
      if (document.hidden) await new Promise((r) => setTimeout(r, HIDDEN_DELAY));
      await work(detail.job);
    });
  });
}
