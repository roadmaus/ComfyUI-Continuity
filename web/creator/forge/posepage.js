/**
 * The pose stage: the forge bench's page for posing a mannequin (spec §7.9).
 *
 * A pose set is a sprite's animation before it has a character in it: one
 * mannequin pose per frame, the body they are drawn on, the speed it plays at.
 * This page is where an artist makes one — drags a joint, steps through the
 * frames with the neighbours ghosted either side, plays it back, imports a
 * Mixamo clip — and draws its frames for the sprite render.
 *
 * **Their viewer, our room.** The 3D viewport is VNCCS Pose Studio's
 * `PoseViewerCore`, vendored; its joint picking, rotation rings, IK, undo and
 * orbit camera are theirs and are not re-implemented. What is ours is
 * everything around it: the sets, the frame strip, the onion skins (their
 * "passive characters", made translucent), playback, the body sliders and the
 * set-up the widget would otherwise do (`pose.js` holds that, shared with the
 * render job, so the figure here is lit and shaped as the job draws it).
 *
 * **Every edit is saved, quietly.** A pose committed by the viewer (its
 * `onPoseChange`, which fires when a drag ends) is written back half a second
 * later by pasting the whole set over itself — `/pose/paste` with `replace`,
 * the route the CLI's `pose paste` uses — so the bench still does nothing the
 * CLI cannot. The thumbnails in the strip are drawn here by a second, hidden
 * viewer, not by a render job: they are this tab's to look at, and a job would
 * cache them into the project.
 *
 * **Drawing frames is the render job**, the same one the CLI's `pose render`
 * starts, so it is claimed by whichever tab gets there first — usually this
 * one — and its PNGs land in the project's cache where the sprite render
 * reads them.
 */

import { el, icon, spinner, dismissable, placeNear, keepScroll } from "../dom.js";
import { forgeCall, forgeFileUrl, upload } from "../api.js";
import { t } from "../i18n.js";
import { LIGHTS, WHITE, vendored, solveBody, makeViewer } from "./pose.js";
import { flipPose, mirrorEdit, mirrorRotation, sideOf, twin } from "./mirror.js";

/** The body sliders, as `creator/forge/pose.py` BODY bounds them. */
const BODY = [
  { key: "age", label: () => t("Age"), low: 1, high: 90, step: 1 },
  { key: "gender", label: () => t("Gender"), low: 0, high: 1, step: 0.01 },
  { key: "height", label: () => t("Height"), low: 0, high: 2, step: 0.01 },
  { key: "weight", label: () => t("Weight"), low: 0, high: 1, step: 0.01 },
  { key: "muscle", label: () => t("Muscle"), low: 0, high: 1, step: 0.01 },
  { key: "breast_size", label: () => t("Chest"), low: 0, high: 2, step: 0.01 },
  { key: "firmness", label: () => t("Firmness"), low: 0, high: 1, step: 0.01 },
];

/** The turns a set can be drawn at, a compass of eight. */
const DIRECTIONS = [0, 45, 90, 135, 180, 225, 270, 315];

/** How far the sprite camera looks down, by the kind of game it suits; the
 *  dial goes anywhere from -30 to 89 (`pose.PITCH`). */
const PITCHES = [
  { deg: 0, label: () => t("Side-on") },
  { deg: 30, label: () => t("Three-quarter") },
  { deg: 45, label: () => t("High") },
  { deg: 89, label: () => t("Top-down") },
];

/** The stage's views, laid out as a cube unfolded: Top over Front, with the
 *  sides either side and Back at the end of the row. `yaw` and `pitch` are
 *  the core's capture-camera angles (its pitch is negative looking down); the
 *  figure faces +Z with its left side at +X, so its left is seen from +90.
 *  `key` is Blender's numpad key for the view, which artists' hands know. */
const VIEWS = [
  { id: "top", label: () => t("Top"), yaw: 0, pitch: -89, key: "7", cell: "top" },
  { id: "right", label: () => t("Right"), yaw: -90, pitch: 0, key: "3", cell: "a" },
  { id: "front", label: () => t("Front"), yaw: 0, pitch: 0, key: "1", cell: "b" },
  { id: "left", label: () => t("Left"), yaw: 90, pitch: 0, key: "", cell: "c" },
  { id: "back", label: () => t("Back"), yaw: 180, pitch: 0, key: "", cell: "d" },
];
/** A drawn frame's size when the page asks for none: the server's default,
 *  one cell of the 2 MP grid (`pose.DEFAULT_SIZE`). */
const CELL = [484, 1088];
/** How much of the stage a view's subject fills. */
const FILL = 0.86;
/** Numpad 9 in Blender: the view from the other side of the one you are in. */
const OPPOSITE = { front: "back", back: "front", left: "right", right: "left" };

/** A strip thumbnail, in the shape of a cell of the 2 MP grid the frames are
 *  rendered in (484×1088), drawn at twice its size for a sharp edge. */
const THUMB = [60, 135];

/** The ghosts either side of the frame you are on: the frame before cool, the
 *  frame after green, as onion skins have been since cel animation. */
const ONION = { prev: "#6ebeff", next: "#7fd37a" };
const ONION_OPACITY = 0.35;

const SAVE_DELAY = 500;
const POLL = 400;
/** One render job draws at most this many frames (`pose.MAX_RENDER`). */
const CHUNK = 64;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** A file name -> a set name the server takes (`project.NAME`). */
function slug(text) {
  const base = text.toLowerCase().replace(/\.[^.]+$/, "").replace(/[^a-z0-9_-]+/g, "-").replace(/^[-_]+|[-_]+$/g, "");
  return (base || "clip").slice(0, 60);
}

/** Only what decides the figure, as the server keeps a pose. */
function cleanPose(pose) {
  return { bones: pose.bones ?? {}, bonePositions: pose.bonePositions ?? {}, modelRotation: pose.modelRotation ?? [0, 0, 0] };
}

function translucent(mesh) {
  for (const material of [].concat(mesh?.material ?? [])) {
    material.transparent = true;
    material.opacity = ONION_OPACITY;
    material.depthWrite = false;
    material.needsUpdate = true;
  }
}

export class PosePage {
  constructor(forge) {
    this.forge = forge;
    this.sets = [];            // the listing: {name, frames, fps, source}
    this.loaded = false;
    this.set = null;           // the open set, as the server keeps it
    this.frame = 0;
    this.thumbs = [];          // a data URL per frame, or null while drawing
    this.onion = true;
    this.playing = null;       // the playback timer
    this.yaw = 0;              // the turn the frames are drawn at
    this.pitch = 0;            // how far the sprite camera looks down
    this.symmetry = false;     // a drag on one side poses the other
    this.angle = "front";      // the stage's view, or "sprite", or null once orbited
    this.drawn = null;         // {set, yaw, pitch, frames: [{frame, path}], at}
    this.view = "pose";        // the stage: "pose" | "drawn"
    this.viewer = null;
    this.sketch = null;        // the hidden viewer the thumbnails are drawn by
    this.removing = false;
    this.applying = false;     // a pose is being put on the viewer by us, not the artist
    this.saveTimer = null;
    this.bodyTimer = null;
    this.bodySeq = 0;
    this.thumbQueue = Promise.resolve();
    this.build();
  }

  // ---- the page ---------------------------------------------------------------

  build() {
    this.shelf = keepScroll(el("nav", { class: "mmc-fg-shelf", "aria-label": t("Pose sets") }));
    this.stagebar = el("div", { class: "mmc-fg-glassbar" });
    this.canvas = el("canvas", { class: "mmc-fg-canvas", tabindex: "0", "aria-label": t("The mannequin") });
    this.drawnLayer = el("div", { class: "mmc-fg-drawn" });
    this.invite = el("div", { class: "mmc-fg-stageinvite" });
    this.hint = el("p", { class: "mmc-fg-stagehint",
      text: t("Click a joint, then drag its rings to turn it. Right-drag to orbit, scroll to zoom.") });
    this.views = el("div", { class: "mmc-fg-views", role: "group", "aria-label": t("View") });
    this.stage = el("div", { class: "mmc-fg-stage" }, [this.canvas, this.drawnLayer, this.invite, this.hint, this.views]);
    this.strip = el("div", { class: "mmc-fg-strip" });
    this.foot = el("div", { class: "mmc-fg-foot" });
    this.inspector = keepScroll(el("aside", { class: "mmc-fg-inspector", "aria-label": t("The pose set") }));
    this.clip = el("input", { type: "file", accept: ".fbx", hidden: true,
      onchange: (event) => { const file = event.target.files[0]; event.target.value = ""; if (file) this.importClip(file); } });
    this.root = el("div", { class: "mmc-fg-page" }, [
      this.shelf,
      el("main", { class: "mmc-fg-middle" }, [this.stagebar, this.stage, this.strip, this.foot]),
      this.inspector,
      this.clip,
    ]);
    this.resizer = new ResizeObserver(() => this.fit());
    this.onKey = (event) => this.key(event);
  }

  show() {
    this.resizer.observe(this.stage);
    document.addEventListener("keydown", this.onKey, true);
    this.paint();
    if (!this.loaded) this.loadSets();
  }

  hide() {
    this.stop();
    this.flush();
    this.resizer.disconnect();
    document.removeEventListener("keydown", this.onKey, true);
  }

  unmount() {
    this.hide();
    try { this.viewer?.dispose(); } catch { /* already gone */ }
    this.sketch?.dispose();
    this.viewer = this.sketch = null;
  }

  get project() { return this.forge.name; }

  paint() {
    this.paintShelf();
    this.paintStagebar();
    this.paintStage();
    this.paintStrip();
    this.paintFoot();
    this.paintInspector();
  }

  paintStatus() { this.paintFoot(); }

  // ---- sets -------------------------------------------------------------------

  async loadSets(open = null) {
    const answer = await this.forge.run(t("Reading the pose sets"), () =>
      forgeCall("/poses", { project: this.project }, { get: true }));
    if (!answer) return;
    this.loaded = true;
    this.sets = answer.sets;
    const name = open ?? this.set?.name ?? this.sets[0]?.name;
    if (name && this.sets.some((s) => s.name === name)) await this.openSet(name);
    else { this.set = null; this.paint(); }
  }

  async openSet(name) {
    this.flush();
    this.stop();
    const answer = await this.forge.run(t("Opening {name}", { name }), () =>
      forgeCall("/pose/show", { project: this.project, set: name }, { get: true }));
    if (!answer) return;
    this.set = answer.set;
    this.frame = 0;
    this.removing = false;
    this.view = "pose";
    if (this.drawn?.set !== name) this.drawn = null;
    this.thumbs = this.set.poses.map(() => null);
    this.paint();
    await this.dress();
    this.drawThumbs();
  }

  /** The viewer, made the first time a set is opened, while the stage is on
   *  screen: its drawing buffer is allocated once, at the size it first sees. */
  async ensureViewer() {
    if (this.viewer) return this.viewer;
    const { PoseViewerCore } = await vendored();
    const box = this.stage.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.round(box.width));
    this.canvas.height = Math.max(1, Math.round(box.height));
    const viewer = new PoseViewerCore(this.canvas, {
      skinMode: "naked", enableTextureSkinning: true, enableMultiPass: true,
      showSkeletonHelper: false, showCaptureFrame: false, syncMode: "end",
      // The stage's own ground shows through, so the figure stands in the room.
      transparentBackground: true, useHandControlPopover: false,
      onPoseChange: (pose) => this.edited(pose),
      onError: (error) => console.error("[continuity] pose viewer", error),
    });
    await viewer.init();
    viewer.setSkinMode("naked");
    viewer.setDirectionalSkydomeVisible(false);
    viewer.updateLights(LIGHTS);
    // Symmetry, live: while a bone is being turned its twin turns with it, so
    // the artist sees both arms move. The pose is made whole when the drag
    // ends (edited), which also covers IK drags that move a chain.
    viewer.transform.addEventListener("objectChange", () => {
      const bone = viewer.transform.object;
      if (!this.symmetry || !bone?.isBone || !sideOf(bone.name)) return;
      const other = viewer.bones[twin(bone.name)];
      if (!other) return;
      const [x, y, z] = mirrorRotation([bone.rotation.x, bone.rotation.y, bone.rotation.z]);
      other.rotation.set(x, y, z);
      viewer.requestRender();
    });
    // Orbiting by hand leaves whichever view was chosen.
    viewer.orbit.addEventListener("start", () => { if (!this.snapping) { this.angle = null; this.paintViews(); } });
    this.viewer = viewer;
    this.fit();
    return viewer;
  }

  fit() {
    const box = this.stage.getBoundingClientRect();
    if (box.width > 0 && box.height > 0) this.viewer?.resize(Math.round(box.width), Math.round(box.height));
  }

  /** Put the set's body on the viewer, then the frame you are on. Called for a
   *  new set and after a body slider moves; a later call wins over an earlier
   *  one still solving. */
  async dress() {
    const seq = ++this.bodySeq;
    const name = this.set.name;
    await this.forge.run(t("Building the mannequin"), async () => {
      const viewer = await this.ensureViewer();
      const mesh = await solveBody(this.set.body);
      if (seq !== this.bodySeq || this.set?.name !== name) return;
      viewer.clearPassiveCharacters();
      this.applying = true;
      try {
        viewer.loadData(mesh, Boolean(this.dressed));
        if (!this.dressed) this.look(this.angle ?? "front");
        this.dressed = true;
        viewer.updateLights(LIGHTS);
        viewer.setPose(this.set.poses[this.frame], true);
      } finally {
        this.applying = false;
      }
      viewer.history = [];
      viewer.future = [];
      this.ghosts();
    });
  }

  /** The frame you are on, onto the viewer, with its neighbours ghosted. */
  showFrame(index) {
    if (!this.set) return;
    const count = this.set.poses.length;
    this.frame = ((index % count) + count) % count;
    if (this.viewer?.isInitialized()) {
      this.applying = true;
      try {
        this.viewer.deselectBone?.();
        this.viewer.setPose(this.set.poses[this.frame], true);
      } finally {
        this.applying = false;
      }
      // Undo is per frame: stepping back through another frame's drags from
      // this one would paste that frame's pose here.
      this.viewer.history = [];
      this.viewer.future = [];
      this.ghosts();
    }
    // Playback steps through here twelve times a second: move the marks, do
    // not rebuild the strip's pictures or the sliders under the pointer.
    this.markStrip();
    if (this.frameLabel) this.frameLabel.textContent = t("Frame {n} of {count}", { n: this.frame + 1, count });
  }

  ghosts() {
    const viewer = this.viewer;
    if (!viewer?.isInitialized() || !this.set) return;
    const poses = this.set.poses;
    const count = poses.length;
    const show = this.onion && !this.playing && this.view === "pose" && count > 1;
    const sides = [["prev", -1, ONION.prev], ["next", 1, ONION.next]];
    for (const [id, step, color] of sides) {
      // Two frames have one neighbour, not the same one twice.
      if (!show || (id === "next" && count === 2)) { viewer.removePassiveCharacter(id); continue; }
      const pose = poses[(this.frame + step + count) % count];
      if (viewer.passiveCharacters.has(id)) viewer.setPassiveCharacterState(id, { pose, color });
      else if (viewer.upsertPassiveCharacterFromActive(id, { pose, color })) translucent(viewer.passiveCharacters.get(id).mesh);
    }
  }

  /** The viewer committed a pose: a drag ended, or an undo. */
  edited(pose) {
    if (this.applying || this.playing || !this.set) return;
    let next = cleanPose(pose);
    if (this.symmetry) {
      next = mirrorEdit(this.set.poses[this.frame], next, sideOf(this.viewer.selectedBone?.name ?? ""));
      this.applying = true;
      try { this.viewer.setPose(next, true); } finally { this.applying = false; }
    }
    this.set.poses[this.frame] = next;
    this.queueThumbs([this.frame]);
    this.saveSoon();
    if (this.drawn) { this.drawn = null; this.paintStagebar(); }
  }

  saveSoon() {
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.save(), SAVE_DELAY);
  }

  flush() {
    if (this.saveTimer) { clearTimeout(this.saveTimer); this.save(); }
  }

  async save() {
    this.saveTimer = null;
    const set = this.set;
    if (!set) return;
    const { name, poses, body, fps, source } = set;
    try {
      await forgeCall("/pose/paste", { project: this.project, set: name, replace: true,
                                       data: { poses, body, fps, source } });
      const row = this.sets.find((s) => s.name === name);
      if (row) { row.frames = poses.length; row.fps = fps; }
      this.paintShelf();
    } catch (error) {
      this.forge.error = t("{name} was not saved: {why}", { name, why: error.message || String(error) });
      this.forge.paintStatus();
    }
  }

  // ---- thumbnails -------------------------------------------------------------

  async ensureSketch() {
    const key = JSON.stringify(this.set.body);
    if (this.sketch?.key === key) return this.sketch;
    this.sketch?.dispose();
    this.sketch = null;
    const made = await makeViewer(this.set.body, THUMB[0] * 2, THUMB[1] * 2);
    this.sketch = { ...made, key };
    return this.sketch;
  }

  drawThumbs() {
    this.thumbs = this.set.poses.map(() => null);
    this.paintStrip();
    this.queueThumbs(this.set.poses.map((_, i) => i));
  }

  /** Draw these frames' thumbnails, one batch after another so two edits in a
   *  row do not fight over the hidden viewer. */
  queueThumbs(indices) {
    const set = this.set;
    this.thumbQueue = this.thumbQueue.then(async () => {
      if (this.set !== set) return;
      try {
        const { viewer } = await this.ensureSketch();
        for (const i of indices) {
          if (this.set !== set || !set.poses[i]) return;
          viewer.setPose(set.poses[i], true);
          viewer.updateLights(LIGHTS);
          this.thumbs[i] = viewer.capture(THUMB[0] * 2, THUMB[1] * 2, 1, WHITE);
          this.paintThumb(i);
          await sleep(0);
        }
      } catch (error) {
        console.error("[continuity] pose thumbnails", error);
      }
    });
  }

  // ---- what the presses do ----------------------------------------------------

  play() {
    if (this.playing) { this.stop(); return; }
    if (!this.set || this.set.poses.length < 2) return;
    this.viewer?.deselectBone?.();
    this.playing = setInterval(() => this.showFrame(this.frame + 1), 1000 / (this.set.fps || 12));
    this.ghosts();
    this.paintStrip();
  }

  stop() {
    if (!this.playing) return;
    clearInterval(this.playing);
    this.playing = null;
    this.ghosts();
    this.paintStrip();
  }

  duplicateFrame() {
    if (!this.set) return;
    this.stop();
    const at = this.frame + 1;
    this.set.poses.splice(at, 0, structuredClone(this.set.poses[this.frame]));
    this.thumbs.splice(at, 0, this.thumbs[this.frame]);
    this.saveSoon();
    this.showFrame(at);
    this.paintStrip();
    this.paintInspector();
  }

  deleteFrame() {
    if (!this.set || this.set.poses.length < 2) return;
    this.stop();
    this.set.poses.splice(this.frame, 1);
    this.thumbs.splice(this.frame, 1);
    this.saveSoon();
    this.showFrame(Math.min(this.frame, this.set.poses.length - 1));
    this.paintStrip();
    this.paintInspector();
  }

  /** The frame as its mirror image: left and right swapped. */
  flipFrame() {
    if (!this.set) return;
    this.set.poses[this.frame] = flipPose(this.set.poses[this.frame]);
    this.queueThumbs([this.frame]);
    this.saveSoon();
    this.showFrame(this.frame);
  }

  /** Point the stage's camera: a named view, or "sprite" for exactly what
   *  Draw frames will see. Drawing turns the figure by the yaw; turning the
   *  camera the other way is the same picture.
   *
   *  The core's snap puts the stage's camera where its capture camera would
   *  be; the zoom is then set here, because the two cameras' lenses differ
   *  (FOV 45 on the stage, 30 for a capture). A named view is zoomed to fit
   *  the figure. The sprite camera is zoomed to fit the frame cell instead,
   *  and keeps the core's capture frame showing: that box is the drawing. */
  look(id) {
    const viewer = this.viewer;
    if (!viewer?.isInitialized()) return;
    const view = id === "sprite" ? { yaw: -this.yaw, pitch: -this.pitch } : VIEWS.find((v) => v.id === id);
    if (!view) return;
    const box = this.stage.getBoundingClientRect();
    const width = Math.max(1, box.width);
    const height = Math.max(1, box.height);
    const lens = Math.tan(Math.PI / 8) / Math.tan(Math.PI / 12);   // tan 22.5° / tan 15°
    let zoom;
    if (id === "sprite") {
      const [cellW, cellH] = CELL;
      zoom = FILL * lens * Math.min(1, (width / height) / (cellW / cellH));
    } else {
      zoom = (viewer.computeModelFitZoom(width, height, 0, 0, view.yaw, view.pitch, 0.08) ?? 1) * lens * FILL;
    }
    this.snapping = true;
    try {
      const [snapW, snapH] = id === "sprite" ? CELL : [width, height];
      viewer.snapToCaptureCamera(snapW, snapH, 1, 0, 0, view.yaw, view.pitch);
      viewer.camera.zoom = zoom;
      viewer.camera.updateProjectionMatrix();
      if (viewer.captureFrame) viewer.captureFrame.visible = id === "sprite";
    } finally {
      this.snapping = false;
    }
    viewer.requestRender();
    this.angle = id;
    this.paintViews();
  }

  toggleSymmetry() {
    this.symmetry = !this.symmetry;
    this.paintStagebar();
  }

  setPitch(deg) {
    this.pitch = deg;
    this.paintInspector();
    this.paintFoot();
    if (this.angle === "sprite") this.look("sprite");
  }

  setYaw(deg) {
    this.yaw = deg;
    this.paintInspector();
    this.paintFoot();
    if (this.angle === "sprite") this.look("sprite");
  }

  resetFrame() {
    if (!this.set) return;
    this.set.poses[this.frame] = { bones: {}, bonePositions: {}, modelRotation: [0, 0, 0] };
    this.queueThumbs([this.frame]);
    this.saveSoon();
    this.showFrame(this.frame);
  }

  setBody(key, value) {
    this.set.body = { ...this.set.body, [key]: value };
    this.drawn = null;
    clearTimeout(this.bodyTimer);
    this.bodyTimer = setTimeout(async () => {
      this.saveSoon();
      await this.dress();
      this.drawThumbs();
    }, 200);
  }

  setFps(value) {
    this.set.fps = value;
    this.saveSoon();
    if (this.playing) { this.stop(); this.play(); }
  }

  async newSet(name, from) {
    const answer = await this.forge.run(t("Making {name}", { name }), () =>
      forgeCall("/pose/new", { project: this.project, set: name, from }));
    if (!answer) return false;
    await this.loadSets(answer.set.name);
    return true;
  }

  async pasteSet(name, text) {
    let data;
    try {
      data = JSON.parse(text);
    } catch (error) {
      this.forge.error = t("That is not JSON: {why}", { why: error.message });
      this.forge.paintStatus();
      return false;
    }
    const answer = await this.forge.run(t("Making {name}", { name }), () =>
      forgeCall("/pose/paste", { project: this.project, set: name, data }));
    if (!answer) return false;
    await this.loadSets(answer.set.name);
    return true;
  }

  async removeSet() {
    if (!this.removing) { this.removing = true; this.paintInspector(); return; }
    const name = this.set.name;
    clearTimeout(this.saveTimer);
    this.saveTimer = null;
    const answer = await this.forge.run(t("Removing {name}", { name }), () =>
      forgeCall("/pose/rm", { project: this.project, set: name }));
    if (!answer) return;
    this.set = null;
    this.drawn = null;
    this.viewer?.clearPassiveCharacters();
    await this.loadSets();
  }

  /** Wait for a pose job to finish -> its last answer, or throw its sentence. */
  async settle(answer) {
    while (answer.state !== "done" && answer.state !== "failed") {
      await sleep(POLL);
      answer = await forgeCall("/pose/job", { job: answer.job }, { get: true });
    }
    if (answer.state === "failed") throw new Error(answer.problem);
    return answer;
  }

  dropped(files) {
    const clip = files.find((file) => /\.fbx$/i.test(file.name));
    if (clip) this.importClip(clip);
    else {
      this.forge.error = t("Drop an FBX clip here, such as a Mixamo animation.");
      this.forge.paintStatus();
    }
  }

  /** A Mixamo FBX -> a new set, retargeted onto the mannequin by a tab. */
  async importClip(file) {
    const taken = new Set(this.sets.map((s) => s.name));
    const stem = slug(file.name);
    let name = stem;
    for (let n = 2; taken.has(name); n++) name = `${stem}-${n}`;
    const answer = await this.forge.run(t("Bringing in {file}", { file: file.name }), async () => {
      const uploaded = await upload(file, "forge");
      return this.settle(await forgeCall("/pose/import", { project: this.project, set: name, file: uploaded.path, fps: 12 }));
    });
    if (answer) await this.loadSets(name);
  }

  /** Draw every frame at the chosen turn, as the sprite render will get them. */
  async drawFrames() {
    if (!this.set) return;
    this.flush();
    this.stop();
    const { name } = this.set;
    const { yaw, pitch } = this;
    const count = this.set.poses.length;
    const frames = [];
    const done = await this.forge.run(t("Drawing {n} frames", { n: count }), async () => {
      for (let start = 0; start < count; start += CHUNK) {
        const chunk = Array.from({ length: Math.min(CHUNK, count - start) }, (_, i) => start + i);
        const answer = await this.settle(await forgeCall("/pose/render",
          { project: this.project, set: name, yaw, pitch, frames: chunk }));
        frames.push(...answer.frames);
      }
      return true;
    });
    if (!done || this.set?.name !== name) return;
    this.drawn = { set: name, yaw, pitch, frames, at: Date.now() };
    this.view = "drawn";
    // The canvas is the sprite grid's cell; a figure it cuts off is said, by
    // frame, so a lean or a reach is not lost without a word.
    const cut = frames.filter((f) => f.marks?.edges?.length).map((f) => f.frame + 1);
    if (cut.length) {
      this.forge.error = t("The frame cuts the figure off in {list}. Turn it, or pose it smaller.",
                           { list: cut.join(", ") });
    }
    this.paint();
  }

  key(event) {
    if (!this.root.isConnected || !this.set || event.defaultPrevented) return;
    if (event.target.closest?.("input, textarea, select, [contenteditable]")) return;
    if (document.querySelector(".mmc-pop")) return;
    const mod = event.metaKey || event.ctrlKey;
    let handled = true;
    if (event.key === "ArrowLeft") { this.stop(); this.showFrame(this.frame - 1); }
    else if (event.key === "ArrowRight") { this.stop(); this.showFrame(this.frame + 1); }
    else if (event.key === " ") this.play();
    else if (!mod && this.view === "pose" && VIEWS.some((v) => v.key && v.key === event.key)) {
      this.look(VIEWS.find((v) => v.key === event.key).id);
    } else if (!mod && this.view === "pose" && event.key === "9" && OPPOSITE[this.angle]) this.look(OPPOSITE[this.angle]);
    else if (!mod && this.view === "pose" && event.key === "0") this.look("sprite");
    else if (!mod && event.key.toLowerCase() === "m") this.toggleSymmetry();
    else if (mod && event.key.toLowerCase() === "z" && this.view === "pose") {
      if (event.shiftKey) this.viewer?.redo(); else this.viewer?.undo();
    } else handled = false;
    if (handled) { event.preventDefault(); event.stopPropagation(); }
  }

  // ---- painting -----------------------------------------------------------------

  paintShelf() {
    this.shelf.replaceChildren(...[
      el("div", { class: "mmc-fg-shelfhead" }, [
        el("span", { class: "mmc-fg-count", text: this.countWords() }),
        el("button", { class: "mmc-fg-add", onclick: (event) => this.newMenu(event.currentTarget) },
          [icon("plus", 14), el("span", { text: t("New") })]),
      ]),
      this.sets.length ? el("div", { class: "mmc-fg-items", role: "listbox", "aria-label": t("Pose sets") },
        this.sets.map((s) => el("button", {
          class: `mmc-fg-item mmc-fg-setrow${s.name === this.set?.name ? " on" : ""}`, role: "option",
          "aria-selected": s.name === this.set?.name, onclick: () => { if (s.name !== this.set?.name) this.openSet(s.name); },
        }, [
          el("span", { class: "mmc-fg-itemname", text: s.name }),
          el("span", { class: "mmc-fg-itemnote", text: s.frames === 1
            ? t("1 pose") : t("{n} frames, {fps} fps", { n: s.frames, fps: Math.round(s.fps * 10) / 10 }) }),
        ]))) : null,
      el("div", { class: "mmc-fg-shelffoot" }, [
        el("button", { class: "mmc-bn-verb", onclick: () => this.clip.click(),
          title: t("A Mixamo animation, or any FBX on the same skeleton") },
          [icon("download", 15), el("span", { text: t("Import an FBX clip") })]),
        el("button", { class: "mmc-bn-verb", onclick: (event) => this.pasteMenu(event.currentTarget) },
          [icon("edit", 15), el("span", { text: t("Paste from Pose Studio") })]),
      ]),
    ].filter(Boolean));
  }

  countWords() {
    if (!this.sets.length) return t("No pose sets");
    if (this.sets.length === 1) return t("1 pose set");
    return t("{n} pose sets", { n: this.sets.length });
  }

  newMenu(anchor) {
    const name = el("input", { class: "mmc-bn-text", placeholder: t("idle"), spellcheck: "false",
      "aria-label": t("Set name"), oninput: () => { make.disabled = !name.value.trim(); },
      onkeydown: (event) => { if (event.key === "Enter" && name.value.trim()) commit(null); } });
    const make = el("button", { class: "mmc-bn-run mmc-fg-small", disabled: true, onclick: () => commit(null) },
      [t("Standing pose")]);
    const copy = this.set ? el("button", { class: "mmc-bn-second mmc-fg-small",
      onclick: () => { if (name.value.trim()) commit(this.set.name); else name.focus(); } },
      [t("Copy of {name}", { name: this.set.name })]) : null;
    const commit = async (from) => { if (await this.newSet(name.value.trim(), from)) close(); };
    const pop = el("div", { class: "mmc-pop mmc-fg-newpop" }, [
      el("div", { class: "mmc-pop-title", text: t("A new pose set") }),
      el("div", { class: "mmc-fg-popbody" }, [name, el("div", { class: "mmc-fg-pair" }, [make, copy])]),
    ]);
    document.body.append(pop);
    placeNear(pop, anchor, { above: false });
    const close = dismissable(pop);
    name.focus();
  }

  pasteMenu(anchor) {
    const name = el("input", { class: "mmc-bn-text", placeholder: t("pasted"), spellcheck: "false",
      "aria-label": t("Set name") });
    const text = el("textarea", { class: "mmc-bn-text mmc-fg-json", rows: "8", spellcheck: "false",
      placeholder: t("Pose Studio's pose_data, one pose, or a list of poses"), "aria-label": t("Pose data") });
    const make = el("button", { class: "mmc-bn-run mmc-fg-small",
      onclick: async () => { if (name.value.trim() && await this.pasteSet(name.value.trim(), text.value)) close(); } },
      [t("Make the set")]);
    const pop = el("div", { class: "mmc-pop mmc-fg-newpop wide" }, [
      el("div", { class: "mmc-pop-title", text: t("Paste poses") }),
      el("div", { class: "mmc-fg-popbody" }, [name, text, make]),
    ]);
    document.body.append(pop);
    placeNear(pop, anchor, { above: true });
    const close = dismissable(pop);
    name.focus();
  }

  paintStagebar() {
    if (!this.set) { this.stagebar.replaceChildren(); return; }
    const views = [{ id: "pose", label: t("Pose") }, { id: "drawn", label: t("Drawn frames"), off: !this.drawn }];
    this.stagebar.replaceChildren(...[
      el("div", { class: "mmc-fg-seg", role: "tablist" }, views.map((view) => el("button", {
        class: `mmc-fg-segbutton${view.id === this.view ? " on" : ""}`, role: "tab", "aria-selected": view.id === this.view,
        disabled: view.off, title: view.off ? t("Press Draw frames first") : null,
        onclick: () => { this.view = view.id; this.ghosts(); this.paint(); },
      }, [view.label]))),
      this.view === "pose" ? el("button", {
        class: `mmc-fg-mirror${this.symmetry ? " on" : ""}`, "aria-pressed": this.symmetry,
        title: t("Pose one side and the other follows, as in a mirror (M)"),
        onclick: () => this.toggleSymmetry(),
      }, [icon("mirrorH", 15), el("span", { text: t("Symmetry") })]) : null,
      el("span", { class: "mmc-bn-gap" }),
      el("span", { class: "mmc-fg-zoom", text: this.drawn && this.view === "drawn" ? this.cameraWords(this.drawn) : "" }),
    ].filter(Boolean));
  }

  paintStage() {
    const posing = Boolean(this.set) && this.view === "pose";
    this.canvas.hidden = !posing;
    this.hint.hidden = !posing;
    this.views.hidden = !posing;
    this.paintViews();
    this.drawnLayer.hidden = !(this.set && this.view === "drawn" && this.drawn);
    this.stage.classList.toggle("drawn", !this.drawnLayer.hidden);
    if (!this.drawnLayer.hidden) {
      this.drawnLayer.replaceChildren(...this.drawn.frames.map(({ frame, path }) => el("figure", { class: "mmc-fg-cell" }, [
        el("img", { alt: t("Frame {n}", { n: frame + 1 }), src: forgeFileUrl(this.project, path, this.drawn.at) }),
        el("figcaption", { text: String(frame + 1) }),
      ])));
    }
    this.invite.hidden = Boolean(this.set);
    if (!this.set) {
      this.invite.replaceChildren(...[
        el("p", { class: "mmc-bn-dropline", text: this.loaded ? t("Pose a mannequin for your sprites") : "" }),
        this.loaded ? el("p", { class: "mmc-bn-dropnote",
          text: t("Start from a standing figure, or drop a Mixamo FBX here to bring in a whole walk.") }) : null,
        this.loaded ? el("div", { class: "mmc-fg-invitebuttons" }, [
          el("button", { class: "mmc-bn-second", onclick: (event) => this.newMenu(event.currentTarget) }, [t("New pose set")]),
          el("button", { class: "mmc-bn-second", onclick: () => this.clip.click() }, [t("Import an FBX clip")]),
        ]) : spinner(),
      ].filter(Boolean));
    }
  }

  /** The view pad: five faces of a cube unfolded, and the sprite camera. */
  paintViews() {
    if (this.views.hidden) return;
    const button = (id, label, title, cell) => el("button", {
      class: `mmc-fg-face${cell === "cam" ? " cam" : ""}${this.angle === id ? " on" : ""}`, style: { gridArea: cell },
      "aria-pressed": this.angle === id, title, onclick: () => this.look(id),
    }, [label]);
    this.views.replaceChildren(
      ...VIEWS.map((v) => button(v.id, v.label(), v.key ? t("{view} view ({key})", { view: v.label(), key: v.key })
        : t("{view} view (9 flips the view you are in)", { view: v.label() }), v.cell)),
      button("sprite", t("Sprite camera"), t("Exactly what Draw frames will draw (0)"), "cam"),
    );
  }

  /** "turned 90°, looking down 30°", or "as posed". */
  cameraWords({ yaw, pitch }) {
    const parts = [];
    if (yaw) parts.push(t("turned {deg}°", { deg: yaw }));
    if (pitch > 0) parts.push(t("looking down {deg}°", { deg: pitch }));
    if (pitch < 0) parts.push(t("looking up {deg}°", { deg: -pitch }));
    return parts.length ? parts.join(", ") : t("as posed");
  }

  paintStrip() {
    if (!this.set) { this.strip.replaceChildren(); this.strip.hidden = true; return; }
    this.strip.hidden = false;
    const count = this.set.poses.length;
    // The current and ghosted marks are markStrip's, once the cells exist.
    this.cells = this.set.poses.map((_, i) => el("button", {
      class: "mmc-fg-frame", title: t("Frame {n}", { n: i + 1 }), "aria-label": t("Frame {n}", { n: i + 1 }),
      onclick: () => { this.stop(); this.showFrame(i); },
    }, [
      this.thumbs[i] ? el("img", { alt: "", src: this.thumbs[i], draggable: false }) : el("span", { class: "mmc-fg-framewait" }),
      el("span", { class: "mmc-fg-framenum", text: String(i + 1) }),
    ]));
    const reel = el("div", { class: "mmc-fg-reel" }, [
      ...this.cells,
      el("button", { class: "mmc-fg-frame mmc-fg-addframe", title: t("Add a frame after this one, as a copy of it"),
        "aria-label": t("Add a frame"), onclick: () => this.duplicateFrame() }, [icon("plus", 16)]),
    ]);
    this.strip.replaceChildren(
      el("button", { class: `mmc-fg-play${this.playing ? " on" : ""}`, disabled: count < 2,
        title: this.playing ? t("Stop (space)") : t("Play (space)"), "aria-label": this.playing ? t("Stop") : t("Play"),
        onclick: () => this.play() }, [icon(this.playing ? "pause" : "play", 16)]),
      reel,
      el("label", { class: "mmc-fg-onion", title: t("Show the frames either side as ghosts") }, [
        el("input", { type: "checkbox", checked: this.onion,
          onchange: (event) => { this.onion = event.target.checked; this.ghosts(); this.paintStrip(); } }),
        el("span", { text: t("Onion skin") }),
      ]),
    );
    this.markStrip();
  }

  /** Which frame is current and which are ghosted, on the cells already there. */
  markStrip() {
    if (!this.cells || this.cells.length !== this.set?.poses.length) { this.paintStrip(); return; }
    const count = this.cells.length;
    const ghosts = this.onion && !this.playing && count > 1;
    this.cells.forEach((cell, i) => {
      cell.classList.toggle("on", i === this.frame);
      cell.setAttribute("aria-current", String(i === this.frame));
      cell.classList.toggle("prev", ghosts && i === (this.frame - 1 + count) % count);
      cell.classList.toggle("next", ghosts && count > 2 && i === (this.frame + 1) % count);
    });
    this.cells[this.frame]?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  paintThumb(i) {
    const cell = this.cells?.[i];
    if (!cell || !this.thumbs[i]) return;
    cell.firstChild.replaceWith(el("img", { alt: "", src: this.thumbs[i], draggable: false }));
  }

  paintFoot() {
    const busy = Boolean(this.forge.working);
    this.foot.replaceChildren(...[
      this.forge.statusLine(),
      el("span", { class: "mmc-bn-gap" }),
      this.set ? el("span", { class: "mmc-fg-footlabel", text: this.set.poses.length === 1
        ? t("1 pose, {camera}", { camera: this.cameraWords(this) })
        : t("{n} frames, {camera}", { n: this.set.poses.length, camera: this.cameraWords(this) }) }) : null,
      el("button", { class: "mmc-bn-run", disabled: busy || !this.set, onclick: () => this.drawFrames(),
        title: t("Draw every frame as the sprite render will see it") }, [t("Draw frames")]),
    ].filter(Boolean));
  }

  paintInspector() {
    if (!this.set) {
      this.inspector.replaceChildren(this.credit());
      return;
    }
    const set = this.set;
    const count = set.poses.length;
    this.inspector.replaceChildren(
      el("header", { class: "mmc-fg-inhead" }, [
        el("h2", { class: "mmc-fg-title", text: set.name }),
        this.frameLabel = el("span", { class: "mmc-fg-kindtag", text: t("Frame {n} of {count}", { n: this.frame + 1, count }) }),
        set.source?.clip ? el("span", { class: "mmc-fg-state", text: t("From {clip}", { clip: set.source.clip }) }) : null,
      ]),
      el("section", { class: "mmc-fg-insection" }, [
        el("h3", { class: "mmc-fg-subhead", text: t("This frame") }),
        el("div", { class: "mmc-fg-pair" }, [
          el("button", { class: "mmc-bn-verb", onclick: () => this.duplicateFrame(), title: t("Add a copy of this frame after it") },
            [el("span", { text: t("Duplicate") })]),
          el("button", { class: "mmc-bn-verb", onclick: () => this.flipFrame(),
            title: t("Swap left and right, as in a mirror. A walk's second half is its first half flipped.") },
            [icon("mirrorH", 15), el("span", { text: t("Flip") })]),
          el("button", { class: "mmc-bn-verb", onclick: () => this.resetFrame(), title: t("Back to standing") },
            [el("span", { text: t("Reset") })]),
          el("button", { class: "mmc-bn-verb", disabled: count < 2, onclick: () => this.deleteFrame() },
            [el("span", { text: t("Delete") })]),
        ]),
      ]),
      el("section", { class: "mmc-fg-insection" }, [
        el("h3", { class: "mmc-fg-subhead", text: t("Speed") }),
        this.dial(t("Frames a second"), set.fps, 1, 60, 1, (value) => this.setFps(value), (v) => String(v)),
      ]),
      el("section", { class: "mmc-fg-insection" }, [
        el("h3", { class: "mmc-fg-subhead", text: t("Body") }),
        el("p", { class: "mmc-fg-hint", text: t("The mannequin's build, for every frame. Match the character's proportions.") }),
        ...BODY.map((slider) => this.dial(slider.label(), set.body[slider.key], slider.low, slider.high, slider.step,
          (value) => this.setBody(slider.key, value), (v) => slider.step >= 1 ? String(v) : v.toFixed(2))),
      ]),
      el("section", { class: "mmc-fg-insection" }, [
        el("h3", { class: "mmc-fg-subhead", text: t("Sprite camera") }),
        el("p", { class: "mmc-fg-hint", text: t("How Draw frames sees the set. Every sprite in a game shares one camera, so set it to match the game.") }),
        el("span", { class: "mmc-fg-label", text: t("Facing") }),
        this.compass(),
        this.dial(t("Looking down"), this.pitch, -30, 89, 1, (value) => this.setPitch(value),
          (v) => (v ? `${v}°` : t("level"))),
        el("div", { class: "mmc-bn-opts" }, PITCHES.map((p) => el("button", {
          class: `mmc-bn-opt${this.pitch === p.deg ? " on" : ""}`, "aria-pressed": this.pitch === p.deg,
          title: `${p.deg}°`, onclick: () => this.setPitch(p.deg),
        }, [p.label()]))),
        el("button", { class: "mmc-bn-verb", onclick: () => this.look("sprite") },
          [el("span", { text: t("Look through it") })]),
      ]),
      el("div", { class: "mmc-fg-inend" }, [
        this.credit(),
        el("button", { class: `mmc-fg-link mmc-fg-remove${this.removing ? " armed" : ""}`, onclick: () => this.removeSet() },
          [this.removing ? t("Press again to remove {name}. Its file is kept in .versions.", { name: set.name })
                         : t("Remove {name}", { name: set.name })]),
      ]),
    );
  }

  dial(label, value, low, high, step, onchange, format) {
    const readout = el("span", { class: "mmc-bn-value", text: format(value) });
    return el("label", { class: "mmc-bn-dial" }, [
      el("span", { class: "mmc-bn-diallabel" }, [el("span", { text: label }), readout]),
      el("input", { class: "mmc-bn-range", type: "range", min: String(low), max: String(high), step: String(step),
        value: String(value),
        oninput: (event) => { readout.textContent = format(Number(event.target.value)); },
        onchange: (event) => onchange(Number(event.target.value)) }),
    ]);
  }

  /** Eight turns round a ring, the figure's facing drawn as the needle. The
   *  ring is the floor seen from above with the camera at its foot, so "as
   *  posed" (facing the camera) points down and a 90° turn, which faces the
   *  figure to the picture's right (checked: its toes go to +X), points right. */
  compass() {
    return el("div", { class: "mmc-fg-compass", role: "radiogroup", "aria-label": t("Direction") }, [
      ...DIRECTIONS.map((deg) => el("button", {
        class: `mmc-fg-point${deg === this.yaw ? " on" : ""}`, role: "radio", "aria-checked": deg === this.yaw,
        style: { "--turn": `${180 - deg}deg` },
        title: deg ? t("Turned {deg}°", { deg }) : t("As posed"),
        "aria-label": deg ? t("Turned {deg}°", { deg }) : t("As posed"),
        onclick: () => this.setYaw(deg),
      })),
      el("span", { class: "mmc-fg-needle", style: { "--turn": `${180 - this.yaw}deg` }, "aria-hidden": "true" }),
      el("span", { class: "mmc-fg-compassread", text: this.yaw ? `${this.yaw}°` : t("as posed") }),
    ]);
  }

  credit() {
    return el("p", { class: "mmc-fg-credit" }, [
      t("Mannequin, posing and FBX import: "),
      el("a", { href: "https://github.com/AHEKOT/ComfyUI_VNCCS_Utils", target: "_blank", rel: "noopener",
        text: "VNCCS Pose Studio" }),
      t(" by AHEKOT (MIT). Body by the MakeHuman project (CC0)."),
    ]);
  }
}
