// The blockout bench: the piece, directed in 3D.
//
// The old bench staged one shot: you built a set, walked a camera through it,
// wrote a guide clip, and attached it to a shot by hand. This one stages the
// piece. It is the reel's window (`reel.js`: the same script, strip, inspector
// rows, kept takes, undo and Shoot) with a stage as its main surface — the
// script as a column on the left, the stage in the middle, the inspector on
// the right, and the piece at its length underneath. Nothing selected means the
// piece is selected.
//
// The bench and the timeline are two windows on the same piece: a shot staged
// and shot here is a kept take there, and a shot written there is in this
// script with no staging until it is given one. What a staging is, how it is
// stamped and what releases a take is `state.js`'s (sets and staging); how it is
// drawn is the old bench's renderer, reused as it is (`blockout.js`). What a
// shot sends to the render — a guide derived from its staging, its words, and
// how firmly the guide holds — is drawn and attached by Shoot (`deriveGuides`),
// so the timeline renders a staged shot exactly as this window does.

import { el, mountOverlay } from "./dom.js";
import { t } from "./i18n.js";
import { viewUrl, blockoutSweep } from "./api.js";
import * as S from "./state.js";
import { Reel, fitText } from "./reel.js";
import {
  Raster, project, cameraAt, stagedAt, guideSize, stagingSentence, moveSentence,
  PASSES, PRESETS, tagRGB, vfovOf, forwardOf, rightOf, upOf, MOST_PREVIEW, clamp,
  syncStagingWords, drawStaged, START_CAMERA, stagedGuidesOf, cornersOf, centreOf, basisOf, applyM, norm3, dot3,
  planeOf, nearPolyline, AXIS_INK, AXES, UNIT, DEG, FAR, BIG,
  joinGap, lineUp, stagingFrom, postureChanges, postureOf, writeGuide,
} from "./blockout.js";
import { rulesFor } from "./canvas.js";

/** The four views of the glass. Still is drawn and not yet built (spec 7). */
const VIEWS = ["stage", "guide", "still", "take"];

/** The window, or null. One at a time, like every window on a piece. */
let open = null;

/**
 * Open the bench on a piece.
 *
 * `options` is what the timeline's window is lent (`Timeline`'s constructor:
 * `timeline`, `onCommit`, `queue`, `stage`, `run`, `io`, `widgets`), plus
 * `openTimeline`, which opens the reel on the same piece, and `opened`, told
 * the window once it exists. Resolves when the window closes.
 */
export function openStaging(options) {
  open?.close();
  return new Promise((resolve) => {
    const bench = new Blockout(options, resolve);
    open = bench;
    options.opened?.(bench);
    bench.mount();
  });
}

/**
 * Open the blockout bench: the call the shell's Blockout card makes.
 *
 * Handed the piece (the node's body), it stages that piece, in the same window
 * the strip opens, on the same shots and takes. Handed none — opened from the
 * pre-stage, or anywhere there is no strip — it is a piece of one shot of its
 * own: no strip, no joins, and *Write the guide* in place of Shoot, its guide
 * going through the doors `targets` names (`fullscreen.guideTargets`).
 *
 * @param {object} [options]
 * @param {object} [options.piece]    the node's body, where it has a strip
 * @param {Array}  [options.targets]  where a written guide can be sent
 * @param {Array}  [options.cast]     who a person can play, without a piece
 * @param {string} [options.family]   whose canvas a guide is written at, without one
 * @param {Function} [options.back]   the way back to the tools
 */
export function openBlockout(options = {}) {
  const piece = options.piece;
  if (piece?.openBlockout && piece.timeline) {
    return piece.openBlockout({ targets: options.targets ?? [], back: options.back ?? null });
  }
  const timeline = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", aspect: "16:9",
    ...(options.family ? { family: options.family } : {}),
    subjects: (options.cast ?? []).filter((handle) => typeof handle === "string" && handle)
      .map((handle) => ({ handle, takes: "person" })),
    segments: [{ prompt: "", duration_s: 4, assets: [], loras: [] }],
  }));
  return openStaging({ timeline, single: true, targets: options.targets ?? [], back: options.back ?? null });
}

const secondsText = (seconds) => t("{s} s", { s: (Number(seconds) || 0).toFixed(1) });

/** "shot 2", "shots 1–3", "shots 1, 4", or "no shot yet". */
export function rangeText(indices) {
  if (!indices.length) return t("no shot yet");
  const n = indices.map((index) => index + 1);
  if (n.length === 1) return t("shot {n}", { n: n[0] });
  const run = n.every((value, k) => k === 0 || value === n[k - 1] + 1);
  return run ? t("shots {a}–{b}", { a: n[0], b: n[n.length - 1] }) : t("shots {list}", { list: n.join(", ") });
}

class Blockout extends Reel {
  constructor(options, resolve) {
    super(options, resolve);
    this.openTimelineWindow = options.openTimeline ?? null;
    // A piece of one shot of its own: no strip, no joins, Write the guide.
    this.single = options.single === true;
    this.targets = options.targets ?? [];
    this.back = options.back ?? null;
    this.result = null;
    // Where the glass is: which shot, and how far into it.
    this.at = { index: 0, t: 0 };
    this.view = "stage";
    this.tool = "move";
    this.lens = false;
    this.playing = false;
    this.rasters = new Map();
    this.said = "";
  }

  // ---- where the glass is ----------------------------------------------------

  /** The shot the glass is on: the selected one, or the last one looked at. */
  index() {
    const count = this.timeline.segments.length;
    this.at.index = clamp(this.at.index, 0, Math.max(0, count - 1));
    return this.at.index;
  }

  segment() {
    return this.timeline.segments[this.index()] ?? null;
  }

  /** The set the glass is on, or null for a shot with no staging. */
  set() {
    return S.isStaged(this.timeline, this.segment()) ? S.setOf(this.timeline, this.segment()) : null;
  }

  staging() {
    return this.set() ? this.segment().staging : null;
  }

  seconds(index = this.index()) {
    const segment = this.timeline.segments[index];
    return S.isClip(segment) ? S.clipSeconds(segment) : Number(segment?.duration_s) || 0;
  }

  /** Where the shot starts on the piece's clock. */
  startOf(index) {
    let start = 0;
    for (let i = 0; i < index; i++) start += this.seconds(i);
    return start;
  }

  /** The shot camera at the playhead. */
  lensCam() {
    return cameraAt(this.staging()?.camera ?? [], this.at.t);
  }

  /** The set as it stands at the playhead. */
  objectsNow() {
    const set = this.set();
    return set ? stagedAt(set, this.staging(), this.at.t) : [];
  }

  /** The free look's camera, off the set's saved view: an orbit round a pivot. */
  freeCam() {
    const set = this.set();
    const view = set?.view ?? this.defaultView(set);
    const ahead = forwardOf({ yaw: view.yaw, pitch: view.pitch });
    return { x: view.x - ahead[0] * view.orbit, y: view.y - ahead[1] * view.orbit,
             z: view.z - ahead[2] * view.orbit, yaw: view.yaw, pitch: view.pitch, mm: 26 };
  }

  /** Where free look starts on a set it has never looked at: the whole set. */
  defaultView(set) {
    const objects = set?.objects ?? [];
    if (!objects.length) return { yaw: -0.62, pitch: -0.36, orbit: 11, x: 0, y: 0.8, z: 1.6 };
    const xs = objects.map((piece) => piece.x), zs = objects.map((piece) => piece.z);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cz = (Math.min(...zs) + Math.max(...zs)) / 2;
    const reach = Math.max(4, Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs));
    return { yaw: -0.62, pitch: -0.42, orbit: clamp(reach * 1.5, 6, 60), x: cx, y: 0.8, z: cz };
  }

  /** Whichever camera the glass is looking through. */
  eye() {
    return this.view === "stage" && !this.lens ? this.freeCam() : this.lensCam();
  }

  /** Move the glass to a shot, keeping the playhead where it is if it is the same one. */
  goTo(index, t = 0) {
    if (index !== this.at.index) this.stopPlay();
    this.at = { index, t: clamp(t, 0, this.seconds(index)) };
  }

  // ---- the window ------------------------------------------------------------

  mount() {
    this.buildParts();
    this.canvas = el("canvas", { "aria-label": t("The stage"), draggable: "false" });
    this.context = this.canvas.getContext("2d");
    this.video = el("video", { muted: "", playsinline: "", preload: "auto", hidden: true });
    this.blank = el("div", { class: "mmc-st-blank", hidden: true });
    this.hudTop = el("div", { class: "mmc-bo-hud top" });
    this.hudBottom = el("div", { class: "mmc-bo-hud bottom" });
    this.timeSaid = el("span", { class: "mmc-st-said" });
    this.stageEl = el("div", { class: "mmc-st" }, [this.canvas, this.video, this.blank, this.hudTop, this.hudBottom]);
    this.glass = el("div", { class: "mmc-st-glass" }, [this.stageEl]);
    this.openButton = el("button", {
      class: "mmc-reel-btn quiet", text: t("Open the timeline"), title: t("The reel, on the same piece"),
      onclick: () => { const go = this.openTimelineWindow; this.close(); go?.(); },
    });

    this.writeButton = el("button", { class: "mmc-reel-shoot", text: t("Write the guide"), onclick: () => this.writeHere() });
    this.modal = el("div", { class: `mmc-modal mmc-tl-modal mmc-reel mmc-st-bench${this.single ? " mmc-st-single" : ""}` }, [
      el("div", { class: "mmc-reel-head" }, [
        this.back
          ? el("button", { class: "mmc-reel-title mmc-st-back", text: t("Blockout"), title: t("Back to the tools"),
              onclick: () => { const back = this.back; this.close(); back(); } })
          : el("span", { class: "mmc-reel-title", text: t("Blockout") }),
        this.titleMeta,
        this.undoButton,
        this.redoButton,
        this.planEl,
        this.cancelButton,
        ...(this.openTimelineWindow ? [this.openButton] : []),
        ...(this.single ? [this.writeButton] : this.queue ? [this.shootButton] : []),
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-reel-main" }, [
        this.scriptColumn(),
        el("div", { class: "mmc-st-col" }, [this.glass]),
        el("div", { class: "mmc-reel-side" }, [this.playerHost, this.inspectHost]),
      ]),
      el("div", { class: "mmc-reel-foot" }, [this.reelHost, this.statusHost]),
    ]);
    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(); },
    }, [this.modal]);
    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.onUndoKey = (event) => this.undoKey(event);
    window.addEventListener("keydown", this.onUndoKey, true);
    this.onKeys = (event) => this.key(event);
    document.addEventListener("keydown", this.onKeys);
    this.toldFailure = this.stage?.failure ?? null;
    if (typeof ResizeObserver !== "undefined") {
      this.resize = new ResizeObserver(() => this.renderReel());
      this.resize.observe(this.reelHost);
      this.glassWatch = new ResizeObserver(() => { this.fit(); this.paint(); });
      this.glassWatch.observe(this.glass);
    }
    this.mountGlass?.();
    if (!this.single) this.adoptSaved();
    // Opened with nothing selected, the glass goes to the first shot.
    this.render();
    this.now = this.capture();
    fitText(this.soundscapeBox);
    fitText(this.musicBox);
    this.fit();
    this.paint();
  }

  close() {
    if (open === this) open = null;
    // The derived guides no shot in the open graph points at any more. Every
    // piece in the graph is asked, not only this one: a guide is a file in the
    // input folder, and another node's shot may be the one that names it.
    const pieces = (globalThis.app?.graph?._nodes ?? []).map((node) => node.mmcBody?.timeline).filter(Boolean);
    if (!pieces.includes(this.timeline)) pieces.push(this.timeline);
    if (pieces.some((piece) => (piece.sets ?? []).length)) blockoutSweep(pieces.flatMap(stagedGuidesOf));
    this.stopPlay();
    this.endDrag?.(false);
    window.removeEventListener("keydown", this.onUndoKey, true);
    document.removeEventListener("keydown", this.onKeys);
    this.resize?.disconnect();
    this.glassWatch?.disconnect();
    clearTimeout(this.shootTimer);
    clearTimeout(this.thumbTimer);
    clearTimeout(this.sayTimer);
    this.unmount?.();
    this.resolve?.();
  }

  /** Every edit ends here: the words follow the staging before the piece is
   *  stamped, so a take is released by what changed and not by the prose. */
  commit() {
    syncStagingWords(this.timeline);
    super.commit();
  }

  select(sel, options) {
    if (sel?.kind === "shot" || sel?.kind === "join") {
      if (sel.index !== this.at.index) this.goTo(sel.index, 0);
    }
    // A set selected from the script or the strip puts the glass on it.
    if (sel?.kind === "set") this.onSet(sel.id);
    // A face in the cast row is the person who plays them on this set, where
    // there is one; otherwise it is the reel's page for them.
    if (sel?.kind === "cast") {
      const piece = this.set()?.objects.find((candidate) => candidate.kind === "person" && candidate.plays === sel.handle);
      if (piece) sel = { kind: "thing", id: piece.id };
    }
    super.select(sel, options);
  }

  /** Say something in the line under the reel, for a moment. */
  say(text) {
    this.said = text;
    this.renderStatus();
    clearTimeout(this.sayTimer);
    this.sayTimer = setTimeout(() => { this.said = ""; this.renderStatus(); }, 2600);
  }

  // ---- the header ------------------------------------------------------------

  /** The reel's header, said the bench's way: how many shots and how long,
   *  then what the next render shoots and what it plays. While a render runs,
   *  or something stands in the way of one, it is the reel's own. */
  renderHead() {
    if (!this.titleMeta) return;
    const count = this.timeline.segments.length;
    super.renderHead();
    this.titleMeta.textContent = `${t(count === 1 ? "{n} shot" : "{n} shots", { n: count })} · ${secondsText(S.timelineSeconds(this.timeline))}`;
    if (this.single) {
      this.planEl.replaceChildren(...(this.writeError ? [el("span", { class: "mmc-reel-problem", text: this.writeError })]
        : this.result ? [el("span", { text: `${t("Wrote")} ` }), el("b", { text: this.result.path.split("/").pop() })] : []));
      this.writeButton.textContent = this.writing ?? t("Write the guide");
      this.writeButton.disabled = Boolean(this.writing) || !this.set();
      return;
    }
    if (this.busy() || S.stripProblem(this.timeline) || this.refusal || this.stage?.failure || !count) return;
    const { shoot, kept } = S.shootPlan(this.timeline);
    const runs = S.passes(this.timeline);
    const shots = shoot.reduce((n, k) => n + runs[k].segments.length, 0);
    const keptShots = kept.reduce((n, k) => n + runs[k].segments.length, 0);
    const keptText = t(keptShots === 1 ? "{n} kept take" : "{n} kept takes", { n: keptShots });
    this.planEl.replaceChildren(...(shots
      ? [el("span", { text: `${t("Shoots")} ` }), el("b", { text: t(shots === 1 ? "{n} shot" : "{n} shots", { n: shots }) }),
         ...(keptShots ? [el("span", { text: ` · ${t("plays")} ` }), el("i", { text: keptText })] : [])]
      : [el("span", { text: `${t("Plays")} ` }), el("i", { text: keptText })]));
  }

  // ---- the script ------------------------------------------------------------

  /** The cast as faces, as the reel draws them, and then the sets as frames. */
  renderCastRow() {
    super.renderCastRow();
    if (!this.castRow) return;
    for (const set of this.timeline.sets ?? []) {
      const on = S.shotsOnSet(this.timeline, set.id);
      this.castRow.append(el("button", {
        class: `mmc-reel-face frame${this.sel?.kind === "set" && this.sel.id === set.id ? " selected" : ""}`,
        title: t("The {name} set, {range}", { name: set.name.toLowerCase(), range: rangeText(on) }),
        onclick: () => this.select({ kind: "set", id: set.id }),
      }, [this.setThumb(set), el("span", { class: "mmc-reel-face-name", text: set.name })]));
    }
  }

  /** A set, seen from above at a corner, as a thumbnail. */
  setThumb(set) {
    const canvas = el("canvas", { width: "76", height: "52" });
    const raster = new Raster(76, 52);
    const view = this.defaultView(set);
    const cam = { x: view.x - 5, y: 5.5, z: view.z - 9, yaw: Math.atan2(5, 9), pitch: -0.45, mm: 24 };
    raster.raster(set.objects, cam);
    raster.shade(canvas.getContext("2d"), "as_staged");
    return canvas;
  }

  /** A hard cut says which set it goes to. */
  rowLead(index) {
    const segment = this.timeline.segments[index];
    if (!index || S.isClip(segment) || S.merged(segment) || S.continues(segment)) return null;
    const set = S.setOf(this.timeline, segment);
    const before = S.setOf(this.timeline, this.timeline.segments[index - 1]);
    const where = !set ? t("not staged yet")
      : set === before ? t("same set, a new keystone")
        : t("the {name} set", { name: set.name.toLowerCase() });
    return el("div", { class: "mmc-reel-hint mmc-st-cuthint", text: `${t("Hard cut")} · ${where}` });
  }

  // ---- the glass -------------------------------------------------------------

  /** The glass has no player: the stage is drawn wherever the reel would play. */
  renderPlayer() {
    this.paintHud();
    this.paint();
  }

  /** Size the buffer to the glass: the piece's frame fitted into it, in device
   *  pixels, capped where the rasterizer stops keeping up with a drag. */
  fit() {
    const room = this.glass?.getBoundingClientRect();
    if (!room?.width || !room.height) return;
    const { w, h } = guideSize(this.timeline);
    const scale = Math.min(room.width / w, room.height / h);
    const dpr = Math.min(2, globalThis.devicePixelRatio || 1);
    const want = clamp(Math.round(w * scale * dpr * (this.draft ? 0.55 : 1)), 320, Math.min(w, MOST_PREVIEW));
    const rw = want, rh = Math.max(1, Math.round((want * h) / w));
    const key = `${rw}x${rh}`;
    if (!this.rasters.has(key)) this.rasters.set(key, new Raster(rw, rh));
    this.raster = this.rasters.get(key);
    if (this.canvas.width !== rw || this.canvas.height !== rh) {
      this.canvas.width = rw;
      this.canvas.height = rh;
    }
  }

  /** Everything on the glass, batched to a frame. */
  paint() {
    if (this.painting) return;
    this.painting = true;
    requestAnimationFrame(() => { this.painting = false; this.draw(); });
  }

  /** What the glass shows: the stage as you handle it, the guide exactly as the
   *  file will hold it, the still (not yet), or the take. */
  draw() {
    if (!this.overlay?.isConnected) return;
    if (!this.raster) this.fit();
    if (!this.raster) return;
    const segment = this.segment();
    const set = this.set();
    this.video.hidden = true;
    this.showBlank(null);
    this.syncTime();
    if (!segment) {
      this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.showBlank(t("Nothing in the piece yet. Write the first shot in the script."));
      return;
    }
    if (this.view === "take") { this.drawTake(); return; }
    if (S.isClip(segment)) {
      this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.showBlank(t("Shot {n} is a clip you added. It has no staging: it plays as it is.", { n: this.index() + 1 }));
      return;
    }
    if (!set) {
      this.raster.raster([], this.freeCam());
      this.raster.shade(this.context, "stage");
      this.showStarts();
      return;
    }
    if (this.view === "guide" || this.view === "still") {
      const pass = S.stagingPass(this.timeline, segment);
      if (this.view === "still" || pass === "none") {
        this.raster.raster(this.objectsNow(), this.lensCam());
        this.raster.shade(this.context, "as_staged");
        this.showBlank(this.view === "still"
          ? t("One frame of this shot, rendered by the image model from the depth pass. Not built yet.")
          : t("This shot carries no guide. The model gets the words alone."));
        return;
      }
      this.raster.raster(this.objectsNow(), this.lensCam());
      this.raster.shade(this.context, pass);
      return;
    }
    const cam = this.eye();
    const objects = this.objectsNow();
    const tints = {};
    for (const piece of objects) if (piece.plays) tints[piece.id] = tagRGB(S.tagIndex(piece.plays));
    this.raster.raster(objects, cam);
    this.raster.shade(this.context, "stage", { selected: this.selectedThing()?.id ?? 0, tints });
    this.paintInk(cam, objects);
  }

  /** The take, at the playhead; or why there is none. */
  drawTake() {
    const take = S.takeOn(S.passOf(this.timeline, this.index()).segments[0]);
    this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!take || this.gone.has(take.filename)) {
      this.showBlank(t("Shot {n} has no take yet. Shoot renders it from this staging.", { n: this.index() + 1 }),
        this.queue ? [t("Shoot"), () => this.shoot()] : null);
      return;
    }
    const src = viewUrl(take.filename);
    if (this.video.dataset.src !== src) {
      this.video.dataset.src = src;
      this.video.src = src;
    }
    this.video.hidden = false;
    const at = this.startInPass(this.index()) + this.at.t;
    if (Math.abs((this.video.currentTime || 0) - at) > 0.05) {
      try { this.video.currentTime = at; } catch { /* not loaded yet: it seeks when it is */ }
    }
  }

  /** How far into its pass's take a shot starts: a pass is one generation and
   *  one file, so a shot merged into one is a stretch of it. */
  startInPass(index) {
    const pass = S.passOf(this.timeline, index);
    let start = 0;
    for (let i = pass.start; i < index; i++) start += this.seconds(i);
    return start;
  }

  showBlank(text, action = null, extra = null) {
    if (!text) { this.blank.hidden = true; this.blank.replaceChildren(); return; }
    this.blank.hidden = false;
    this.blank.replaceChildren(...[
      el("p", { text }),
      action ? el("button", { class: "mmc-reel-btn", text: action[0], onclick: action[1] }) : null,
      extra,
    ].filter(Boolean));
  }

  /** A shot with no staging: the ways to start one. An existing set, or one of
   *  the arrangements a shot list already uses. */
  showStarts() {
    const sets = this.timeline.sets ?? [];
    this.showBlank(t("Shot {n} has no staging yet. Stage it on a set, or start a new one.", { n: this.index() + 1 }), null,
      el("div", { class: "mmc-st-starts" }, [
        ...sets.map((set) => el("button", { class: "mmc-reel-btn",
          text: t("On the {name} set", { name: set.name.toLowerCase() }),
          onclick: () => this.stageOn(set.id) })),
        ...PRESETS.map((preset) => el("button", { class: "mmc-reel-btn quiet", text: t(preset.label), title: t(preset.note),
          onclick: () => this.startSet(preset) })),
      ]));
  }

  /** A new set from an arrangement, and this shot staged on it. */
  startSet(preset) {
    const segment = this.segment();
    if (!segment || S.isClip(segment)) return;
    const made = preset.make();
    const id = this.newSetId();
    const read = S.sceneAsStaging({ ...made, duration: Number(segment.duration_s) || 4 },
                                  { id, name: t(preset.id === "bare" ? "Set" : preset.label) });
    this.timeline.sets = [...(this.timeline.sets ?? []), read.set];
    segment.set = id;
    segment.staging = read.staging;
    this.view = "stage";
    this.commit();
    this.say(t("Shot {n} is staged on a new set. Shots after it can share it.", { n: this.index() + 1 }));
  }

  /** This shot staged on a set that exists: the camera where the last shot on
   *  it stopped, or at eye height. */
  stageOn(id) {
    const segment = this.segment();
    if (!segment || S.isClip(segment)) return;
    const index = this.index();
    const before = S.shotsOnSet(this.timeline, id).filter((i) => i < index && this.timeline.segments[i].staging).pop();
    const from = before != null ? this.timeline.segments[before] : null;
    const end = from ? cameraAt(from.staging.camera, this.seconds(before)) : { ...START_CAMERA };
    delete end.t;
    segment.set = id;
    segment.staging = { camera: [{ ...end, t: 0 }], people: {} };
    this.commit();
  }

  newSetId() {
    const taken = new Set((this.timeline.sets ?? []).map((set) => set.id));
    let n = taken.size + 1;
    while (taken.has(`s${n}`)) n++;
    return `s${n}`;
  }

  /** The time under the glass: which shot, and how far into it. */
  syncTime() {
    if (!this.timeSaid) return;
    this.timeSaid.textContent = `${t("Shot {n}", { n: this.index() + 1 })} · ${this.at.t.toFixed(1)} / ${secondsText(this.seconds())}`;
    if (this.headEl && this.lay) {
      this.headEl.style.left = `${this.reelAt(this.startOf(this.index()) + this.at.t)}px`;
    }
  }

  /** The HUD over the glass. */
  paintHud() {
    if (!this.hudTop) return;
    const seg = (label, on, onclick, extra = {}) => el("button", {
      class: `mmc-bo-seg${on ? " on" : ""}`, "aria-pressed": String(Boolean(on)), onclick, ...extra,
    }, [el("span", { text: label })]);
    const staged = Boolean(this.set());
    const stageView = this.view === "stage" && staged;
    this.hudTop.replaceChildren(...[
      el("div", { class: "mmc-bo-switch", role: "group", "aria-label": t("What the glass shows") }, [
        seg(t("Stage"), this.view === "stage", () => this.setView("stage"), { title: t("The set as you handle it: clay, grid, camera, names.") }),
        seg(t("Guide"), this.view === "guide", () => this.setView("guide"), { title: t("The pass exactly as the file will hold it.") }),
        seg(t("Still"), this.view === "still", () => this.setView("still"), {
          disabled: true, title: t("One frame rendered by the image model from the depth pass, to check the look. Not built yet.") }),
        seg(t("Take"), this.view === "take", () => this.setView("take"), { title: t("What came back.") }),
      ]),
      ...(this.toolSwitch && stageView && !this.lens ? [this.toolSwitch(seg)] : []),
      el("span", { class: "mmc-bn-gap" }),
      ...(stageView ? [el("div", { class: "mmc-bo-switch", role: "group", "aria-label": t("Which camera") }, [
        seg(t("Free look"), !this.lens, () => this.setLens(false), { title: t("Fly around the set. The shot camera stays where it is.") }),
        seg(t("Through the lens"), this.lens, () => this.setLens(true), { title: t("Stand in the shot camera. Every gesture writes a camera mark at the playhead.") }),
      ])] : []),
    ]);
    const play = el("button", { class: "mmc-bo-seg", "aria-label": this.playing ? t("Pause") : t("Play"),
      onclick: () => (this.playing ? this.stopPlay() : this.startPlay()) }, [el("span", { text: this.playing ? "❚❚" : "▶" })]);
    this.hudBottom.replaceChildren(...[
      el("div", { class: "mmc-bo-switch" }, [play, this.timeSaid]),
      el("span", { class: "mmc-bn-gap" }),
      ...(this.hudAdds && stageView ? this.hudAdds(seg) : []),
    ]);
    this.syncTime();
  }

  setView(view) {
    if (!VIEWS.includes(view)) return;
    this.view = view;
    this.paintHud();
    this.paint();
    this.renderStatus();
  }

  setLens(on) {
    this.lens = on;
    this.paintHud();
    this.paint();
    this.renderStatus();
  }

  // ---- the ink over the stage ----------------------------------------------------

  /** How many buffer pixels one CSS pixel is worth on the glass. */
  inkScale() {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return 1;
    return Math.max(this.raster.w / rect.width, this.raster.h / rect.height);
  }

  /** The aids over the clay: where people walk, the shot camera and its path
   *  (in free look), the rule of thirds (through the lens), and the names. */
  paintInk(cam, objects) {
    const context = this.context;
    const scale = this.inkScale();
    context.save();
    context.lineCap = "round";
    context.lineJoin = "round";
    this.inkWalks(context, cam, scale);
    if (this.lens) this.inkThirds(context, scale);
    else { this.inkPath(context, cam, scale); this.inkCamera(context, cam, scale); }
    this.inkNames(context, cam, scale, objects);
    this.inkGizmo?.(context, cam, scale);
    context.restore();
  }

  inkThirds(context, scale) {
    const { w, h } = this.raster;
    context.strokeStyle = "rgba(255,255,255,.13)";
    context.lineWidth = scale;
    context.beginPath();
    for (const at of [1 / 3, 2 / 3]) {
      context.moveTo(Math.round(w * at), 0); context.lineTo(Math.round(w * at), h);
      context.moveTo(0, Math.round(h * at)); context.lineTo(w, Math.round(h * at));
    }
    context.stroke();
  }

  /** The line through a list of world points, broken where one is behind the eye. */
  polyline(context, cam, points) {
    const { w, h } = this.raster;
    context.beginPath();
    let started = false;
    for (const point of points) {
      const at = project(cam, point, w, h);
      if (!at) { started = false; continue; }
      started ? context.lineTo(at.x, at.y) : context.moveTo(at.x, at.y);
      started = true;
    }
    context.stroke();
  }

  /** Where each person walks in this shot: a dashed line on the floor from mark
   *  to mark, in their own hue, with a dot at every mark. */
  inkWalks(context, cam, scale) {
    const set = this.set();
    const staging = this.staging();
    const { w, h } = this.raster;
    for (const piece of set.objects) {
      const marks = staging.people?.[piece.id];
      if (piece.kind !== "person" || !marks || marks.length < 2) continue;
      const [r, g, b] = piece.plays ? tagRGB(S.tagIndex(piece.plays)) : [189, 184, 174];
      context.strokeStyle = `rgb(${r},${g},${b})`;
      context.fillStyle = context.strokeStyle;
      context.lineWidth = 2 * scale;
      context.setLineDash([5 * scale, 5 * scale]);
      this.polyline(context, cam, marks.map((mark) => [mark.x, mark.y + 0.02, mark.z]));
      context.setLineDash([]);
      for (const mark of marks) {
        const at = project(cam, [mark.x, mark.y + 0.02, mark.z], w, h);
        if (!at) continue;
        context.beginPath();
        context.arc(at.x, at.y, 3.5 * scale, 0, Math.PI * 2);
        context.fill();
      }
    }
  }

  /** The shot camera's path through the set, a diamond at every mark, and a
   *  dropped tick under each so its height reads. */
  inkPath(context, cam, scale) {
    const marks = this.staging().camera;
    if (!marks.length) return;
    const { w, h } = this.raster;
    const seconds = this.seconds();
    const along = [];
    for (let k = 0; k <= 48; k++) along.push(cameraAt(marks, (seconds * k) / 48));
    context.strokeStyle = "rgba(110,190,255,.85)";
    context.lineWidth = 1.6 * scale;
    this.polyline(context, cam, along.map((c) => [c.x, c.y, c.z]));
    context.globalAlpha = 0.35;
    this.polyline(context, cam, along.map((c) => [c.x, 0.02, c.z]));
    context.globalAlpha = 1;
    for (const mark of marks) {
      const at = project(cam, [mark.x, mark.y, mark.z], w, h);
      if (!at) continue;
      context.fillStyle = "rgba(110,190,255,.95)";
      context.save();
      context.translate(at.x, at.y);
      context.rotate(Math.PI / 4);
      const side = 9 * scale;
      context.fillRect(-side / 2, -side / 2, side, side);
      context.restore();
    }
  }

  /** The shot camera where it stands at the playhead: a frustum of the piece's
   *  own frame and the lens, so its size on the glass is how much it sees. */
  inkCamera(context, cam, scale) {
    const { w, h } = this.raster;
    const shot = this.lensCam();
    const shape = guideSize(this.timeline);
    const th = Math.tan(vfovOf(shot.mm) / 2), tw = th * (shape.w / shape.h);
    const ahead = forwardOf(shot), right = rightOf(shot), up = upOf(shot);
    const far = 1.3;
    const corner = (sx, sy) => [
      shot.x + ahead[0] * far + right[0] * tw * far * sx + up[0] * th * far * sy,
      shot.y + ahead[1] * far + right[1] * tw * far * sx + up[1] * th * far * sy,
      shot.z + ahead[2] * far + right[2] * tw * far * sx + up[2] * th * far * sy,
    ];
    const apex = [shot.x, shot.y, shot.z];
    const face = [corner(-1, 1), corner(1, 1), corner(1, -1), corner(-1, -1)];
    context.strokeStyle = "rgba(110,190,255,.95)";
    context.lineWidth = 2 * scale;
    this.polyline(context, cam, [...face, face[0]]);
    for (const point of face) this.polyline(context, cam, [apex, point]);
    context.globalAlpha = 0.25;
    this.polyline(context, cam, [apex, [shot.x, 0, shot.z]]);
    context.globalAlpha = 1;
    const at = project(cam, apex, w, h);
    if (at) {
      context.fillStyle = "rgba(110,190,255,.95)";
      context.beginPath();
      context.arc(at.x, at.y, 3.2 * scale, 0, Math.PI * 2);
      context.fill();
    }
  }

  /** What each named piece is, floated over it in a little label: a cast
   *  member in their hue, a word quiet, an unnamed person by their kind. */
  inkNames(context, cam, scale, objects) {
    const { w, h } = this.raster;
    const size = Math.round(12 * scale);
    context.font = `600 ${size}px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "alphabetic";
    for (const piece of objects) {
      if (!piece.plays && !piece.word) continue;
      const top = Math.max(...cornersY(piece));
      const at = project(cam, [piece.x, top + 0.16, piece.z], w, h);
      if (!at || at.x < 0 || at.x > w || at.y < 0 || at.y > h) continue;
      const text = this.labelOf(piece);
      const width = context.measureText(text).width + 12 * scale;
      context.fillStyle = "rgba(14,15,17,.74)";
      context.beginPath();
      context.roundRect?.(at.x - width / 2, at.y - 17 * scale, width, 18 * scale, 6 * scale);
      context.fill();
      if (piece.plays) {
        const [r, g, b] = tagRGB(S.tagIndex(piece.plays));
        context.fillStyle = `rgb(${r},${g},${b})`;
      } else context.fillStyle = "#e9e7e2";
      context.fillText(text, at.x, at.y - 4 * scale);
    }
  }

  /** What a piece of a set is called on the glass and in the inspector. */
  labelOf(piece) {
    if (piece.plays) return `@${piece.plays}`;
    if (piece.word) return piece.word.charAt(0).toUpperCase() + piece.word.slice(1);
    return t({ person: "Person", block: "Block", wall: "Wall", post: "Post" }[piece.kind] ?? "Block");
  }

  /** The piece of the set that is selected, as it stands at the playhead. */
  selectedThing() {
    if (this.sel?.kind !== "thing") return null;
    return this.objectsNow().find((piece) => piece.id === this.sel.id) ?? null;
  }

  // ---- playing -------------------------------------------------------------------

  startPlay() {
    if (this.playing) return;
    if (this.at.t >= this.seconds() - 0.05) {
      if (this.index() >= this.timeline.segments.length - 1) this.goTo(0, 0);
      else this.at.t = 0;
    }
    this.playing = true;
    let last = performance.now();
    const tick = (now) => {
      if (!this.playing || !this.overlay?.isConnected) return;
      this.at.t += Math.min(0.1, (now - last) / 1000);
      last = now;
      if (this.at.t >= this.seconds()) {
        if (this.index() < this.timeline.segments.length - 1) {
          const next = this.index() + 1;
          this.at = { index: next, t: 0 };
          if (this.sel?.kind === "shot" || this.sel?.kind === "thing") this.sel = { kind: "shot", index: next };
          this.renderStrip();
        } else {
          this.at.t = this.seconds();
          this.stopPlay();
        }
      }
      this.draw();
      if (this.playing) requestAnimationFrame(tick);
    };
    this.paintHud();
    requestAnimationFrame(tick);
  }

  stopPlay() {
    if (!this.playing) return;
    this.playing = false;
    this.paintHud();
    this.renderSide?.();
  }

  // ---- the strip -------------------------------------------------------------

  /** A shot with no take shows its guide on its card, dimmed. */
  dressCard(card, index, { thumb }) {
    const segment = this.timeline.segments[index];
    if (thumb || !S.isStaged(this.timeline, segment)) return;
    card.classList.add("mmc-st-guide");
    card.querySelector(".mmc-reel-card-text")?.remove();
    const pass = S.stagingPass(this.timeline, segment);
    const canvas = el("canvas", { class: "mmc-st-thumb", "data-card": String(index) });
    card.prepend(canvas);
    if (!card.querySelector(".mmc-reel-card-tag")) {
      card.append(el("span", { class: "mmc-reel-card-tag mmc-st-quiet",
        text: pass === "none" ? t("Not shot yet") : t("Not shot yet · its guide") }));
    }
    clearTimeout(this.thumbTimer);
    this.thumbTimer = setTimeout(() => this.drawThumbs(), 60);
  }

  /** The guide frames on the cards of shots not shot yet, a few across each. */
  drawThumbs() {
    if (!this.reelHost?.isConnected) return;
    const tile = { w: 150, h: 84 };
    const raster = this.thumbRaster ?? (this.thumbRaster = new Raster(tile.w, tile.h));
    const scratch = this.thumbCanvas ?? (this.thumbCanvas = el("canvas", { width: String(tile.w), height: String(tile.h) }));
    const scratchContext = scratch.getContext("2d");
    for (const canvas of this.reelHost.querySelectorAll("canvas.mmc-st-thumb")) {
      const index = Number(canvas.dataset.card);
      const segment = this.timeline.segments[index];
      if (!S.isStaged(this.timeline, segment)) continue;
      const set = S.setOf(this.timeline, segment);
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(2, Math.round(rect.width || 150));
      canvas.width = width;
      canvas.height = tile.h;
      const context = canvas.getContext("2d");
      const tiles = Math.max(1, Math.round(width / tile.w));
      const each = width / tiles;
      const pass = S.stagingPass(this.timeline, segment);
      for (let k = 0; k < tiles; k++) {
        const at = ((k + 0.5) / tiles) * this.seconds(index);
        raster.raster(stagedAt(set, segment.staging, at), cameraAt(segment.staging.camera, at));
        raster.shade(scratchContext, pass === "none" ? "as_staged" : pass);
        context.drawImage(scratch, Math.max(0, (tile.w - each) / 2), 0, Math.min(tile.w, each), tile.h, k * each, 0, each, tile.h);
      }
    }
  }

  /** A press on a card scrubs it: the glass follows the pointer through the shot. */
  pressCard(event, segment, index) {
    if (event.button !== 0 || event.target.closest?.(".mmc-reel-edge")) return;
    // Measured once, at the press: selecting the shot redraws the reel.
    const rect = event.currentTarget.getBoundingClientRect();
    const seek = (e) => {
      const t = clamp((e.clientX - rect.left) / Math.max(1, rect.width), 0, 1) * this.seconds(index);
      this.at = { index, t: Math.round(t * 20) / 20 };
      this.syncTime();
      this.paint();
    };
    this.stopPlay();
    if (!(this.sel?.kind === "shot" && this.sel.index === index)) this.select({ kind: "shot", index });
    seek(event);
    const up = () => {
      window.removeEventListener("pointermove", seek);
      window.removeEventListener("pointerup", up);
      this.renderSide();
    };
    window.addEventListener("pointermove", seek);
    window.addEventListener("pointerup", up);
  }

  /** The playhead, over the film. */
  overReel(picture) {
    this.headEl = el("div", { class: "mmc-st-head" });
    picture.append(this.headEl);
    queueMicrotask(() => this.syncTime());
  }

  /** The line under the reel: how the glass is handled, or what just happened. */
  renderStatus() {
    if (!this.statusHost) return;
    let hint = t("Stage shows the set as you handle it. Guide is the pass as the model gets it, Take is what came back.");
    if (this.view === "stage" && this.set()) {
      hint = this.lens
        ? t("Through the lens: drag pans and tilts, shift-drag trucks and pedestals, the wheel pushes in. Each writes a camera mark at the playhead.")
        : this.tool === "turn"
          ? t("Turn: drag a ring to turn a piece on that axis. It snaps to 15° and rests on the floor whichever way up it is.")
          : this.tool === "lift"
            ? t("Lift: drag a piece up to take it off the floor, down to put it back. Move the playhead first and it rises or falls between the two marks.")
            : t("Move: drag a person to block them, drag a wall or the table to change the set. Drag the floor to orbit, shift-drag to slide, wheel to zoom.");
    }
    this.statusHost.replaceChildren(
      el("button", { class: "mmc-reel-link", text: t("The piece"), onclick: () => this.select(null) }),
      el("span", { class: "mmc-reel-hint", text: this.said || hint }),
    );
  }

  // ---- staging on the glass ----------------------------------------------------
  //
  // The old bench's handles, kept: Move hangs three world-axis arrows and a free
  // centre off the selected piece, Turn three rings in its own axes snapping to
  // 15°, and Lift the arrow that takes it off the floor. A press on a piece's
  // body slides it across the floor. What a handle changes depends on what is
  // held: a person is blocked in this shot (a mark at the playhead), anything
  // else is the set (every shot staged on it). Free look moves only the view;
  // through the lens every gesture writes a camera mark at the playhead.

  mountGlass() {
    this.canvas.addEventListener("pointerdown", (event) => this.press(event));
    this.canvas.addEventListener("wheel", (event) => this.wheel(event), { passive: false });
    this.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  }

  /** The three tools, as the HUD offers them. */
  toolSwitch(seg) {
    return el("div", { class: "mmc-bo-switch", role: "group", "aria-label": t("What a drag on a piece does") },
      [["move", t("Move"), "1"], ["turn", t("Turn"), "2"], ["lift", t("Lift"), "3"]].map(([tool, label, key]) =>
        seg(label, this.tool === tool, () => this.setTool(tool), { title: `${label} (${key})` })));
  }

  /** The four adds, and the camera put where you stand. */
  hudAdds(seg) {
    return [
      el("div", { class: "mmc-bo-switch", role: "group", "aria-label": t("Add to the set") },
        ["person", "block", "wall", "post"].map((kind) => seg(`+ ${this.kindLabel(kind)}`, false, () => this.addThing(kind)))),
      ...(!this.lens ? [el("div", { class: "mmc-bo-switch" }, [seg(t("Put the camera here"), false, () => this.cameraHere())])] : []),
    ];
  }

  kindLabel(kind) {
    return t({ person: "Person", block: "Block", wall: "Wall", post: "Post" }[kind] ?? "Block");
  }

  setTool(tool) {
    this.tool = tool;
    this.paintHud();
    this.paint();
    this.renderStatus();
  }

  /** A glass pixel, in the buffer: the canvas is fitted into the glass, so the
   *  picture is letterboxed inside the element. */
  glassPoint(event) {
    const rect = this.canvas.getBoundingClientRect();
    const scale = Math.min(rect.width / this.raster.w, rect.height / this.raster.h) || 1;
    const left = rect.left + (rect.width - this.raster.w * scale) / 2;
    const top = rect.top + (rect.height - this.raster.h * scale) / 2;
    return {
      px: clamp((event.clientX - left) / scale, 0, this.raster.w - 1),
      py: clamp((event.clientY - top) / scale, 0, this.raster.h - 1),
    };
  }

  /** The handles of the selected piece, in buffer pixels, or null. */
  gizmo(cam) {
    const piece = this.selectedThing();
    if (!piece || this.view !== "stage" || this.lens) return null;
    const { w, h } = this.raster;
    const origin = centreOf(piece);
    const at = project(cam, origin, w, h);
    if (!at) return null;
    const fl = (h / 2) / Math.tan(vfovOf(cam.mm) / 2);
    const len = (at.z * h * 0.17) / fl;
    const m = basisOf(piece);
    const parts = [];
    const keys = this.tool === "lift" ? ["y"] : AXES;
    for (const key of keys) {
      const axis = this.tool === "turn" ? norm3(applyM(m, UNIT[key])) : UNIT[key];
      if (this.tool === "turn") {
        const [u, v] = planeOf(axis);
        const pts = [];
        for (let step = 0; step <= 48; step++) {
          const a = (step / 48) * Math.PI * 2;
          const c = Math.cos(a), s = Math.sin(a);
          const on = project(cam, [origin[0] + (u[0] * c + v[0] * s) * len, origin[1] + (u[1] * c + v[1] * s) * len,
                                   origin[2] + (u[2] * c + v[2] * s) * len], w, h);
          pts.push(on ? [on.x, on.y] : null);
        }
        parts.push({ key, axis, pts, ring: true });
      } else {
        const tip = project(cam, [origin[0] + axis[0] * len, origin[1] + axis[1] * len, origin[2] + axis[2] * len], w, h);
        if (tip) parts.push({ key, axis, pts: [[at.x, at.y], [tip.x, tip.y]] });
      }
    }
    return { piece, origin, at, parts };
  }

  inkGizmo(context, cam, scale) {
    const gizmo = this.gizmo(cam);
    if (!gizmo) return;
    for (const part of gizmo.parts) {
      context.strokeStyle = AXIS_INK[part.key];
      context.lineWidth = (part.ring ? 1.8 : 2.4) * scale;
      context.beginPath();
      let started = false;
      for (const point of part.pts) {
        if (!point) { started = false; continue; }
        started ? context.lineTo(point[0], point[1]) : context.moveTo(point[0], point[1]);
        started = true;
      }
      context.stroke();
      if (part.ring) continue;
      const tip = part.pts[1];
      context.fillStyle = AXIS_INK[part.key];
      context.beginPath();
      context.arc(tip[0], tip[1], 3.6 * scale, 0, Math.PI * 2);
      context.fill();
    }
    if (this.tool === "move") {
      context.fillStyle = "rgba(233,231,226,.9)";
      context.strokeStyle = "rgba(20,20,20,.6)";
      context.lineWidth = 1.4 * scale;
      context.beginPath();
      context.arc(gizmo.at.x, gizmo.at.y, 4.6 * scale, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    }
  }

  /** Which handle a press landed on, or null. */
  grabbed(gizmo, px, py, scale) {
    if (!gizmo) return null;
    if (this.tool === "move" && Math.hypot(gizmo.at.x - px, gizmo.at.y - py) <= 8 * scale) return { key: "free" };
    let best = null;
    for (const part of gizmo.parts) {
      const away = nearPolyline(part.pts, px, py);
      if (away <= 11 * scale && (!best || away < best.away)) best = { key: part.key, axis: part.axis, away };
    }
    return best;
  }

  /**
   * What an edit to a piece of the set writes to. A person is blocked in this
   * shot: a mark at the playhead, made from where they stand now if there is
   * none there yet (their first mark too, if they have none). Anything else is
   * the set itself.
   */
  holdOf(id) {
    const set = this.set();
    const piece = set?.objects.find((candidate) => candidate.id === id);
    if (!piece) return null;
    if (piece.kind !== "person") return { piece, target: piece, person: false };
    const staging = this.staging();
    const t = snapTime(this.at.t, this.seconds());
    const marks = staging.people[id] ?? (staging.people[id] = [restMark(piece, 0)]);
    let mark = marks.find((candidate) => Math.abs(candidate.t - t) < 0.14);
    if (!mark) {
      const now = this.objectsNow().find((candidate) => candidate.id === id) ?? piece;
      mark = restMark(now, t);
      marks.push(mark);
      marks.sort((a, b) => a.t - b.t);
    }
    return { piece, target: mark, person: true };
  }

  /** The shot camera's mark at the playhead, made from where it is if there is
   *  none there yet. */
  cameraMark() {
    const staging = this.staging();
    const t = snapTime(this.at.t, this.seconds());
    let mark = staging.camera.find((candidate) => Math.abs(candidate.t - t) < 0.14);
    if (!mark) {
      mark = { ...cameraAt(staging.camera, t), t };
      staging.camera.push(mark);
      staging.camera.sort((a, b) => a.t - b.t);
    }
    return mark;
  }

  press(event) {
    if (!this.raster || this.view !== "stage" || !this.set()) return;
    event.preventDefault();
    this.stopPlay();
    // The draft buffer from the press on: everything below measures in it.
    this.setDraft(true);
    const cam = this.eye();
    const { px, py } = this.glassPoint(event);
    const scale = this.inkScale();
    const slide = event.button === 1 || event.button === 2 || event.shiftKey;
    let move = null;
    let edits = false;
    if (!this.lens && !slide) {
      const grab = this.grabbed(this.gizmo(cam), px, py, scale);
      if (grab) { move = this.dragHandle(grab, event, cam); edits = Boolean(move); }
    }
    let pressedThing = false;
    if (!move && !this.lens && !slide) {
      this.raster.raster(this.objectsNow(), cam);
      const id = this.raster.id[Math.floor(py) * this.raster.w + Math.floor(px)];
      const piece = this.objectsNow().find((candidate) => candidate.id === id);
      if (piece) {
        pressedThing = true;
        if (!(this.sel?.kind === "thing" && this.sel.id === id)) this.select({ kind: "thing", id });
        move = this.tool === "lift" ? this.dragLift(id, event) : this.dragFloor(id, px, py, cam);
        edits = true;
      }
    }
    if (!move) move = this.dragCamera(event, slide);
    const x0 = event.clientX, y0 = event.clientY;
    let moved = false;
    const step = (e) => {
      if (!moved && Math.hypot(e.clientX - x0, e.clientY - y0) < 3) return;
      moved = true;
      move(e);
    };
    try { this.canvas.setPointerCapture(event.pointerId); } catch { /* a pointer already gone */ }
    const up = () => {
      this.canvas.removeEventListener("pointermove", step);
      this.canvas.removeEventListener("pointerup", up);
      this.canvas.removeEventListener("pointercancel", up);
      this.endDrag = null;
      this.setDraft(false);
      if (moved && (edits || this.lens)) { this.commit(); return; }
      // A click on the floor, not a drag: back to the shot.
      if (!moved && !pressedThing && !edits && this.sel?.kind === "thing") {
        this.select({ kind: "shot", index: this.index() });
        return;
      }
      this.paint();
    };
    this.endDrag = up;
    this.canvas.addEventListener("pointermove", step);
    this.canvas.addEventListener("pointerup", up);
    this.canvas.addEventListener("pointercancel", up);
  }

  /** Half resolution while something moves: the rasterizer is a per-pixel loop. */
  setDraft(draft) {
    if (this.draft === draft) return;
    this.draft = draft;
    this.fit();
    this.draw();
  }

  /** One handle, dragged. The axis is projected once, at the press, into a
   *  screen direction; the pointer's travel along it is metres. */
  dragHandle(grab, event, cam) {
    const id = this.sel?.id;
    const now = this.selectedThing();
    if (!now) return null;
    if (grab.key === "free") {
      const { px, py } = this.glassPoint(event);
      return this.dragFloor(id, px, py, cam);
    }
    const { w, h } = this.raster;
    const origin = centreOf(now);
    const from = project(cam, origin, w, h);
    const along = project(cam, [origin[0] + grab.axis[0] * 0.5, origin[1] + grab.axis[1] * 0.5, origin[2] + grab.axis[2] * 0.5], w, h);
    const at0 = this.glassPoint(event);
    let hold = null;
    const target = () => (hold ??= this.holdOf(id))?.target;
    const start = { x: now.x, y: now.y ?? 0, z: now.z, rx: now.rx ?? 0, ry: now.ry ?? 0, rz: now.rz ?? 0 };
    if (this.tool === "turn") {
      if (!from) return null;
      const key = `r${grab.key}`;
      const toCam = [cam.x - origin[0], cam.y - origin[1], cam.z - origin[2]];
      const spin = dot3(grab.axis, toCam) >= 0 ? 1 : -1;
      const angle0 = Math.atan2(at0.py - from.y, at0.px - from.x);
      return (moved) => {
        const point = this.glassPoint(moved);
        const angle = Math.atan2(point.py - from.y, point.px - from.x);
        const turned = Math.round(((start[key] + spin * (angle - angle0)) * DEG) / 15) * 15 / DEG;
        target()[key] = wrapTurn(turned);
        this.paint();
      };
    }
    if (!from || !along) return null;
    const dirx = along.x - from.x, diry = along.y - from.y;
    const len2 = dirx * dirx + diry * diry;
    if (len2 < 1e-6) return null;
    return (moved) => {
      const point = this.glassPoint(moved);
      const metres = (((point.px - at0.px) * dirx + (point.py - at0.py) * diry) / len2) * 0.5;
      const low = grab.key === "y" ? 0 : -FAR;
      const high = grab.key === "y" ? BIG : FAR;
      target()[grab.key] = clamp(Math.round((start[grab.key] + metres) * 20) / 20, low, high);
      this.paint();
    };
  }

  /** A piece slid across the floor under the pointer, held where it was grabbed.
   *  A person walking to a new mark turns to face the way they walk. */
  dragFloor(id, px, py, cam) {
    const now = this.objectsNow().find((candidate) => candidate.id === id);
    if (!now) return null;
    const grab = this.floorPoint(px, py, cam);
    const held = grab ? { x: grab.x - now.x, z: grab.z - now.z } : null;
    let hold = null;
    return (moved) => {
      if (!held) return;
      const point = this.glassPoint(moved);
      const floor = this.floorPoint(point.px, point.py, cam);
      if (!floor) return;
      hold ??= this.holdOf(id);
      const target = hold.target;
      const x = clamp(Math.round((floor.x - held.x) * 20) / 20, -FAR, FAR);
      const z = clamp(Math.round((floor.z - held.z) * 20) / 20, -FAR, FAR);
      if (hold.person) {
        const marks = this.staging().people[id];
        const before = marks[marks.indexOf(target) - 1];
        if (before && Math.hypot(x - before.x, z - before.z) > 0.3) target.ry = Math.atan2(x - before.x, z - before.z);
      }
      target.x = x;
      target.z = z;
      this.paint();
    };
  }

  /** Lift: drag up to take a piece off the floor, down to put it back. */
  dragLift(id, event) {
    const now = this.objectsNow().find((candidate) => candidate.id === id);
    if (!now) return null;
    const y0 = now.y ?? 0, start = event.clientY;
    let hold = null;
    return (moved) => {
      hold ??= this.holdOf(id);
      hold.target.y = clamp(Math.round((y0 - (moved.clientY - start) * 0.012) * 20) / 20, 0, 8);
      this.paint();
    };
  }

  /** Where a glass pixel's ray meets the floor, or null. */
  floorPoint(px, py, cam) {
    const ray = this.raster.ray(px, py, cam);
    if (cam.y <= 0 || ray[1] >= -0.001) return null;
    const along = -cam.y / ray[1];
    return along > 400 ? null : { x: cam.x + ray[0] * along, z: cam.z + ray[2] * along };
  }

  /** The camera, operated. Free look orbits round the set's pivot and slides
   *  across it; through the lens, the camera department's moves, each a mark. */
  dragCamera(event, slide) {
    let last = { x: event.clientX, y: event.clientY };
    return (at) => {
      const dx = at.clientX - last.x, dy = at.clientY - last.y;
      last = { x: at.clientX, y: at.clientY };
      const sliding = slide || at.shiftKey;
      if (this.lens) {
        const mark = this.cameraMark();
        if (sliding) {
          const right = rightOf(mark);
          mark.x = clamp(mark.x - right[0] * dx * 0.008, -FAR, FAR);
          mark.z = clamp(mark.z - right[2] * dx * 0.008, -FAR, FAR);
          mark.y = clamp(mark.y + dy * 0.008, 0.2, 6);
        } else {
          const k = (0.0022 * 35) / mark.mm;
          mark.yaw -= dx * k;
          mark.pitch = clamp(mark.pitch + dy * k, -1.2, 1.2);
        }
      } else {
        const set = this.set();
        const view = set.view ?? (set.view = this.defaultView(set));
        if (sliding) {
          const right = rightOf(view), up = upOf(view);
          const k = view.orbit * 0.0016;
          view.x = clamp(view.x - right[0] * dx * k + up[0] * dy * k, -FAR, FAR);
          view.y = clamp(view.y + up[1] * dy * k, -2, 8);
          view.z = clamp(view.z - right[2] * dx * k + up[2] * dy * k, -FAR, FAR);
        } else {
          view.yaw += dx * 0.006;
          view.pitch = clamp(view.pitch - dy * 0.005, -1.45, -0.04);
        }
      }
      this.paint();
    };
  }

  wheel(event) {
    if (this.view !== "stage" || !this.set()) return;
    event.preventDefault();
    if (this.lens) {
      const mark = this.cameraMark();
      const ahead = forwardOf(mark);
      const k = -event.deltaY * 0.0022;
      mark.x = clamp(mark.x + ahead[0] * k, -FAR, FAR);
      mark.z = clamp(mark.z + ahead[2] * k, -FAR, FAR);
      clearTimeout(this.wheelTimer);
      this.wheelTimer = setTimeout(() => this.commit(), 350);
    } else {
      const set = this.set();
      const view = set.view ?? (set.view = this.defaultView(set));
      view.orbit = clamp(view.orbit * Math.exp(event.deltaY * 0.0012), 2.5, 60);
    }
    this.paint();
  }

  /** A piece of the set, where free look is centred. Its name is the kind's
   *  until it is given one; a person plays nobody until told. */
  addThing(kind) {
    const set = this.set();
    if (!set) return;
    const view = set.view ?? this.defaultView(set);
    const id = Math.max(0, ...set.objects.map((piece) => piece.id)) + 1;
    if (id > 253) { this.say(t("A set holds at most 253 pieces.")); return; }
    set.objects.push(S.setPiece({ kind, x: Math.round(view.x * 4) / 4, z: Math.round(view.z * 4) / 4 }, id));
    this.sel = { kind: "thing", id };
    this.commit();
    this.say(t("Added to the {name} set: {range} will reshoot.", { name: set.name.toLowerCase(),
      range: rangeText(S.shotsOnSet(this.timeline, set.id).filter((i) => S.takeOn(this.timeline.segments[i]))) }));
  }

  /** Take the selected piece off the set, and out of every shot's blocking. */
  removeThing() {
    const set = this.set();
    if (!set || this.sel?.kind !== "thing") return;
    const id = this.sel.id;
    set.objects = set.objects.filter((piece) => piece.id !== id);
    for (const index of S.shotsOnSet(this.timeline, set.id)) {
      const people = this.timeline.segments[index].staging?.people;
      if (people) delete people[id];
    }
    this.sel = { kind: "set", id: set.id };
    this.commit();
  }

  /** The shot camera, put where free look is standing, at the playhead. */
  cameraHere() {
    if (!this.set()) return;
    const free = this.freeCam();
    const mark = this.cameraMark();
    Object.assign(mark, { x: free.x, y: clamp(free.y, 0.2, 6), z: free.z, yaw: free.yaw, pitch: free.pitch });
    this.lens = true;
    this.commit();
    this.say(t("The shot camera is where you stood, at {s}.", { s: secondsText(mark.t) }));
  }

  /** The keys the glass answers to, when nothing is being typed. */
  key(event) {
    if (!this.overlay?.isConnected || !this.onTop()) return;
    const at = event.target;
    if (at && (at.tagName === "INPUT" || at.tagName === "TEXTAREA" || at.tagName === "SELECT" || at.isContentEditable)) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === " " && at?.tagName !== "BUTTON") { this.playing ? this.stopPlay() : this.startPlay(); }
    else if ((event.key === "Delete" || event.key === "Backspace") && this.sel?.kind === "thing") this.removeThing();
    else if (event.key === "Escape" && this.sel) this.select(null);
    else if (["1", "2", "3"].includes(event.key) && this.set()) this.setTool(["move", "turn", "lift"][Number(event.key) - 1]);
    else return;
    event.preventDefault();
  }

  // ---- writing a guide, and where it can go -----------------------------------

  /** The doors a written guide can go through. On a piece the shot's own guide
   *  is derived and attached by Shoot, so the door that would attach it by hand
   *  is not offered; the others (the pre-stage) are. */
  doors() {
    return this.targets.filter((target) => this.single || target.id !== "guide");
  }

  /** Whether the guide this shot writes is a picture rather than a clip. */
  writesStill(index) {
    return this.single ? (this.timeline.segments[index]?.staging?.camera?.length ?? 0) < 2 : false;
  }

  /** The doors, as a row of the shot's inspector, and what was last written. */
  sendRows(index) {
    const doors = this.doors();
    const rows = [];
    if (this.result && this.single) {
      rows.push(this.irow(t("Written"), el("span", { class: "mmc-reel-note",
        text: `${this.result.path.split("/").pop()} · ${this.result.op} · input/${this.result.path.split("/").slice(0, -1).join("/")}` })));
    }
    if (!doors.length) return rows;
    const kind = this.writesStill(index) ? "image" : "video";
    rows.push(this.irow(t("Send"), el("div", { class: "mmc-reel-inline" }, doors.map((target) => {
      const frame = Boolean(target.kinds) && !target.kinds.includes(kind);
      return el("button", {
        class: `mmc-reel-btn${this.sentTo?.has(target.id) ? " quiet" : ""}`, disabled: Boolean(this.writing) || undefined,
        title: frame ? t("The frame at the playhead, drawn as a still.")
          : kind === "image" && target.doesStill ? target.doesStill : target.does ?? "",
        text: target.label,
        onclick: () => this.send(target, index, frame || kind === "image"),
      });
    })), this.sentTo?.size ? t("Sent. The file is in the input folder either way.") : null));
    return rows;
  }

  /** Write the guide of the shot on the glass: a piece of one shot's Shoot. */
  async writeHere() {
    if (this.writing || !this.set()) return;
    await this.write(this.index(), this.writesStill(this.index()));
  }

  async write(index, still) {
    this.writing = t("Working…");
    this.writeError = null;
    this.renderHead();
    try {
      this.result = await writeGuide(this.timeline, index, { at: this.at.t, still,
        step: (sentence) => { this.writing = sentence; this.renderHead(); } });
      this.sentTo = new Set();
    } catch (error) {
      this.writeError = String(error?.message || error);
      this.result = null;
    }
    this.writing = null;
    if (this.overlay?.isConnected) { this.renderHead(); this.renderSide(); }
    return this.result;
  }

  /** Through a door: written for it, then handed over. */
  async send(target, index, still) {
    const result = await this.write(index, still);
    if (!result) return;
    target.take(result);
    (this.sentTo ??= new Set()).add(target.id);
    if (target.closeOnSend) { this.close(); return; }
    this.renderSide();
  }

  /**
   * Read in the scenes the old bench saved. A shot with no staging whose guide
   * is an old bench clip, with its `.json` beside it, takes that scene as a new
   * set and as its own staging, the first time the bench opens on it.
   */
  adoptSaved() {
    this.timeline.segments.forEach((segment) => {
      if (S.isClip(segment) || segment.staging) return;
      const guide = S.guideAsset(segment);
      const path = String(guide?.filename ?? "");
      if (!/^continuity\/blockout\/blockout-[a-z_]+(?:[-_ ]?\(?\d+\)?)?\.mp4$/.test(path)) return;
      fetch(viewUrl(path.replace(/\.mp4$/, ".json")))
        .then((response) => (response.ok ? response.json() : null))
        .then((sidecar) => {
          const scene = sidecar?.scene;
          if (!scene || segment.staging || !this.timeline.segments.includes(segment)) return;
          const id = this.newSetId();
          const read = S.sceneAsStaging(scene, { id, name: t("Saved set") });
          if (!read) return;
          // The scene's marks over the shot's own length.
          const k = (Number(segment.duration_s) || read.duration) / read.duration;
          for (const mark of read.staging.camera) mark.t *= k;
          for (const marks of Object.values(read.staging.people)) for (const mark of marks) mark.t *= k;
          this.timeline.sets = [...(this.timeline.sets ?? []), read.set];
          segment.set = id;
          segment.staging = read.staging;
          if (this.overlay?.isConnected) {
            this.commit();
            this.say(t("Shot {n}'s saved blockout is its staging now, on a set of its own.", { n: this.timeline.segments.indexOf(segment) + 1 }));
          }
        })
        .catch(() => {});
    });
  }

  // ---- continuity ------------------------------------------------------------

  /** A new shot after a staged one starts where it ended: the same set, the
   *  camera where it stopped, everyone on their last marks (spec 3.2). */
  prepareShot(segment, at) {
    if (!at || !S.continues(segment)) return;
    const from = stagingFrom(this.timeline, at);
    if (!from) return;
    segment.set = from.set;
    segment.staging = from.staging;
    this.at = { index: at, t: 0 };
    this.said = t("Shot {n} starts where shot {m} ends: same set, same marks, the camera where it stopped.", { n: at + 1, m: at });
    clearTimeout(this.sayTimer);
    this.sayTimer = setTimeout(() => { this.said = ""; this.renderStatus(); }, 2600);
  }

  /** A continuing join that does not line up wears the accent on the strip. */
  joinFlag(index) {
    return joinGap(this.timeline, index) ? " mmc-st-jump" : "";
  }

  /** Start shot `index` where the shot before it ends. */
  lineUp(index, { commit = true } = {}) {
    if (lineUp(this.timeline, index) && commit) this.commit();
  }

  /** The join's own check: what does not line up, said, and the fix offered. */
  lineUpRows(index) {
    const gap = joinGap(this.timeline, index);
    const segment = this.timeline.segments[index];
    if (!S.isStaged(this.timeline, segment) || !S.isStaged(this.timeline, this.timeline.segments[index - 1])) return [];
    if (!gap) {
      return [this.irow(t("Staging"), el("span", { class: "mmc-reel-note",
        text: t("Lines up. The camera and everyone on set start where shot {n} leaves them.", { n: index }) }))];
    }
    const parts = [];
    if (gap.camera >= 0.2) parts.push(t("the camera starts {m} m from where shot {n} leaves it", { m: gap.camera.toFixed(1), n: index }));
    else if (gap.turn >= 5) parts.push(t("the camera starts turned {d}° from how shot {n} leaves it", { d: Math.round(gap.turn), n: index }));
    else if (gap.lens >= 2) parts.push(t("the lens changes at the join"));
    for (const { piece, metres, posture } of gap.who) {
      const who = this.labelOf(piece);
      if (metres >= 0.2) parts.push(t("{who} stands {m} m from where they stopped", { who, m: metres.toFixed(1) }));
      if (posture) parts.push(t("{who} changes posture", { who }));
    }
    return [this.irow(t("Staging"), el("div", { class: "mmc-reel-inline" }, [
      el("span", { class: "mmc-st-warn", text: t("Does not line up: {what}. The model will be handed frames that contradict the guide.", { what: parts.join(t(", and ")) }) }),
      el("button", { class: "mmc-reel-btn", text: t("Start shot {n} where shot {m} ends", { n: index + 1, m: index }),
        onclick: () => this.lineUp(index) }),
    ]))];
  }

  /** Whether someone changes posture or leaves the floor in a shot. */
  postureChanges(index) {
    return postureChanges(this.timeline, index);
  }

  /** A piece's posture, in words. */
  postureOf(piece) {
    return postureOf(piece);
  }

  // ---- the sets on the strip -------------------------------------------------

  /** The lane over the film: one bracket per run of shots on one set. */
  laneAbove(at, span) {
    const lane = el("div", { class: "mmc-reel-passes" });
    const segments = this.timeline.segments;
    let run = null;
    const runs = [];
    segments.forEach((segment, index) => {
      const set = S.isStaged(this.timeline, segment) ? S.setOf(this.timeline, segment) : null;
      if (run && set && run.set === set) run.end = index;
      else { run = set ? { set, start: index, end: index } : null; if (run) runs.push(run); }
    });
    for (const { set, start, end } of runs) {
      const left = at(start), right = at(end) + span(end);
      lane.append(el("button", {
        class: `mmc-reel-pass${this.sel?.kind === "set" && this.sel.id === set.id ? " selected" : ""}`,
        style: { left: `${left}px`, width: `${right - left - 2}px` },
        title: t("The {name} set", { name: set.name.toLowerCase() }),
        text: t("{name} set", { name: set.name }),
        onclick: () => this.select({ kind: "set", id: set.id }),
      }));
    }
    return lane;
  }

  // ---- the inspector ---------------------------------------------------------

  renderSide() {
    if (!this.inspectHost) return;
    const sel = this.sel;
    const count = this.timeline.segments.length;
    if ((sel?.kind === "shot" || sel?.kind === "join") && !(sel.index >= 0 && sel.index < count)) this.sel = null;
    if (sel?.kind === "join" && sel.index < 1) this.sel = null;
    if (sel?.kind === "set" && !(this.timeline.sets ?? []).some((set) => set.id === sel.id)) this.sel = null;
    if (sel?.kind === "thing" && !this.selectedThing()) this.sel = null;
    this.renderPlayer();
    const kind = this.sel?.kind;
    const segment = kind === "shot" ? this.timeline.segments[this.sel.index] : null;
    const body = kind === "join" ? this.inspectJoin(this.sel.index)
      : kind === "shot" ? (S.isClip(segment) ? this.inspectClip(this.sel.index) : this.inspectStagedShot(this.sel.index))
      : kind === "cast" ? this.inspectCast(this.sel.handle)
      : kind === "ref" ? this.inspectRef(this.sel.handle)
      : kind === "track" ? this.inspectTrack(this.sel.index)
      : kind === "set" && this.inspectSet ? this.inspectSet(this.sel.id)
      : kind === "thing" && this.inspectThing ? this.inspectThing()
      : this.inspectBenchPiece();
    this.inspectHost.replaceChildren(...(this.sel ? [this.backLink()] : []), body);
  }

  backLink() {
    if (this.sel?.kind === "thing") {
      return el("button", { class: "mmc-reel-link mmc-reel-back", text: `‹ ${t("Shot {n}", { n: this.index() + 1 })}`,
        onclick: () => this.select({ kind: "shot", index: this.index() }) });
    }
    return el("button", { class: "mmc-reel-link mmc-reel-back", text: t("‹ The piece"), title: t("The settings of the whole piece"),
      onclick: () => this.select(null) });
  }

  /** A row of mutually exclusive passes: the four the bench writes, and None. */
  passOptions() {
    return [...PASSES.map((pass) => [pass.id, t(pass.label)]), ["none", t("None")]];
  }

  /** Nothing selected: the piece. Model and frame, the pass staged shots send,
   *  and the sets. */
  inspectBenchPiece() {
    const family = S.pieceFamily(this.timeline);
    const control = S.controlOf(family);
    const sets = this.timeline.sets ?? [];
    const pass = S.pieceStagingPass(this.timeline);
    const passNote = !control
      ? t("{family} has no guide to follow, so a staged shot sends the words alone.", { family: S.FAMILY_LABEL[family] ?? family })
      : pass === "none"
        ? t("No shot carries a guide unless it says so itself. The stage still writes the staging and the camera into the words.")
        : family === "ltx25"
          ? t("LTX 2.5 follows the guide through the Union Control IC-LoRA.")
          : t("MiniMax H3 follows the guide through its ControlNet-Union branch, which is loaded only for shots that carry one.");
    const rows = [
      this.ihead(t("The piece"), `${t(this.timeline.segments.length === 1 ? "{n} shot" : "{n} shots", { n: this.timeline.segments.length })} · ${secondsText(S.timelineSeconds(this.timeline))}`),
      ...this.canvasRows().slice(0, 2),
      this.irow(t("Guide"), this.segmented(this.passOptions(), pass, (value) => {
        if (value === S.DEFAULT_STAGING_PASS) delete this.timeline.staging_pass; else this.timeline.staging_pass = value;
        this.commit();
      }), passNote),
      this.irow(t("Sets"), el("div", { class: "mmc-reel-inline" }, sets.length
        ? sets.map((set) => el("button", { class: "mmc-reel-value", onclick: () => this.select({ kind: "set", id: set.id }) }, [
            el("span", { text: set.name }), el("small", { text: rangeText(S.shotsOnSet(this.timeline, set.id)) })]))
        : [el("span", { class: "mmc-reel-note", text: t("None yet. Select a shot to stage it.") })]),
      t("A hard cut starts a new scene, and a scene has one set.")),
      el("div", { class: "mmc-reel-machine", text: t("Every shot is staged on its scene's set. The stage writes two things for the render: a guide clip along the shot camera's path, and the staging and the move in the model's own words.") }),
    ];
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  /** A shot: its film and its length, then its staging. */
  inspectStagedShot(index) {
    const segment = this.timeline.segments[index];
    const { state, why, tagText, film } = this.shotFilm(index);
    const set = S.isStaged(this.timeline, segment) ? S.setOf(this.timeline, segment) : null;
    const sub = `${secondsText(this.seconds(index))}${set ? ` · ${t("the {name} set", { name: set.name.toLowerCase() })}` : ""}`;
    const rows = [
      this.ihead(t("Shot {n}", { n: index + 1 }), sub,
        tagText ? el("span", { class: `mmc-reel-tag ${state}`, text: tagText }) : null),
      el("p", { class: "mmc-reel-why", text: why }),
      ...this.filmRows(index, film),
      this.lengthRow(index),
    ];
    if (set) rows.push(...this.stagingRows(index));
    else {
      rows.push(this.irow(t("Staging"), el("span", { class: "mmc-reel-note",
        text: t("None yet. The glass offers a set to stage it on.") })));
    }
    rows.push(this.seedRow(index));
    if (set) {
      const pass = S.stagingPass(this.timeline, segment);
      const guide = S.stagedGuideName(this.timeline, index);
      const frames = Math.max(2, Math.round((Number(segment.duration_s) || 0) * rulesFps(this.timeline)));
      const words = segment.staging.words || this.wordsOf(index);
      rows.push(...this.sendRows(index));
      rows.push(el("div", { class: "mmc-reel-machine" }, [
        el("div", { class: "mmc-reel-inline" }, [
          el("span", { text: t("What the model is given for this shot") }),
          el("button", { class: "mmc-reel-link", text: t("Copy"), title: t("Copy the staging and the move, to paste into a prompt as prose."),
            onclick: (event) => {
              navigator.clipboard?.writeText(words).catch(() => {});
              const button = event.currentTarget;
              button.textContent = t("Copied");
              setTimeout(() => { if (button.isConnected) button.textContent = t("Copy"); }, 1200);
            } }),
        ]),
        el("pre", { class: "mmc-reel-compiled mmc-st-words",
          text: (S.stagingPass(this.timeline, segment) === "none" || !guide
            ? "" : `input/${S.STAGED_GUIDE_DIR}/${guide}.mp4 · ${t("{n} frames", { n: frames })} · ${t(PASSES.find((p) => p.id === pass)?.label ?? pass)}\n`)
            + words }),
      ]));
    }
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  /** The words a staged shot sends, as they would be now. */
  wordsOf(index) {
    const segment = this.timeline.segments[index];
    const set = S.setOf(this.timeline, segment);
    if (!set) return "";
    const { w, h } = guideSize(this.timeline);
    return stagingSentence(stagedAt(set, segment.staging, 0), segment.staging.camera,
                           Number(segment.duration_s) || 0, cameraAt(segment.staging.camera, 0), { w, h });
  }

  /** A staged shot's own rows: the move, the marks, the lens, who stands where,
   *  the pass it sends and how firmly it holds. */
  stagingRows(index) {
    const segment = this.timeline.segments[index];
    const staging = segment.staging;
    const set = S.setOf(this.timeline, segment);
    const { w, h } = guideSize(this.timeline);
    const marks = staging.camera;
    const here = (mark) => index === this.index() && Math.abs(mark.t - this.at.t) < 0.07;
    const lens = Math.round(cameraAt(marks, index === this.index() ? this.at.t : 0).mm);
    const family = S.pieceFamily(this.timeline);
    const control = S.controlOf(family);
    const pass = S.stagingPass(this.timeline, segment);
    const own = staging.pass !== undefined;
    const loose = staging.hold === "loose";
    const posture = this.postureChanges(index);
    return [
      this.irow(t("Camera"), el("span", { class: "mmc-reel-note", text: moveSentence(marks, this.seconds(index)) })),
      this.irow(t("Marks"), el("div", { class: "mmc-reel-inline" }, [
        ...marks.map((mark) => el("button", { class: "mmc-reel-value", title: t("Go to this mark"),
          onclick: () => { this.goTo(index, mark.t); this.renderSide(); } }, [
          el("span", { text: secondsText(mark.t) }), ...(here(mark) ? [el("small", { text: t("here") })] : [])])),
        ...(marks.length > 1 && marks.some(here) ? [el("button", { class: "mmc-reel-link", text: t("Take this mark out"),
          onclick: () => { staging.camera = marks.filter((mark) => !here(mark)); this.commit(); } })] : []),
      ])),
      this.irow(t("Lens"), this.segmented([24, 28, 35, 50, 85].map((mm) => [mm, String(mm), "mm"]),
        [24, 28, 35, 50, 85].includes(lens) ? lens : null,
        (mm) => { for (const mark of staging.camera) mark.mm = mm; this.commit(); })),
      this.irow(t("Staging"), el("span", { class: "mmc-reel-note",
        text: stagingSentence(stagedAt(set, staging, 0), marks, this.seconds(index), cameraAt(marks, 0), { w, h },
          { withMove: false, ends: stagedAt(set, staging, this.seconds(index)) })
          || t("Nothing named is in frame.") })),
      this.irow(t("Guide"), this.segmented(this.passOptions(), pass, (value) => {
        if (value === S.pieceStagingPass(this.timeline)) delete staging.pass; else staging.pass = value;
        this.commit();
      }), !control ? t("This model has no guide to follow: the shot is given the words alone.")
        : own ? t("Differs from the piece, which sends {pass}.", { pass: t(PASSES.find((p) => p.id === S.pieceStagingPass(this.timeline))?.label ?? "None").toLowerCase() })
          : null),
      ...(pass !== "none" && control ? [this.irow(t("Guide holds"), this.segmented(
        [["loose", t("Loosely"), "0.6"], ["firm", t("Firmly"), "1.0"]], loose ? "loose" : "firm",
        (value) => { if (value === "loose") staging.hold = "loose"; else delete staging.hold; this.commit(); }),
      loose ? t("The blocks are a suggestion. More life, less exact marks.")
        : posture ? t("Someone changes posture or leaves the floor in this shot: Loosely may suit it better.")
          : t("The blocks are where things are."))] : []),
    ];
  }

  /** A set: its name, what is on it, and what can be added. Shared by every
   *  shot of its scene, so the note says what moving it costs. */
  inspectSet(id) {
    const set = (this.timeline.sets ?? []).find((candidate) => candidate.id === id);
    const used = S.shotsOnSet(this.timeline, id);
    const named = set.objects.filter((piece) => piece.plays || piece.word || piece.kind === "person");
    const rest = set.objects.length - named.length;
    const name = el("input", { class: "mmc-reel-seed mmc-st-name", type: "text", value: set.name, "aria-label": t("Name of the set"),
      onchange: (event) => { set.name = event.target.value.trim().slice(0, 48) || set.name; this.commit(); } });
    return el("div", { class: "mmc-reel-inspect-body" }, [
      this.ihead(set.name, `${t("set")} · ${rangeText(used)}`),
      el("p", { class: "mmc-reel-why", text: t("The set is shared by every shot of its scene. Moving a wall or the table reshoots all of them. Moving a person only changes the shot you are on.") }),
      this.irow(t("Name"), name),
      this.irow(t("On it"), el("div", { class: "mmc-reel-inline" }, named.map((piece) => el("button", {
        class: "mmc-reel-value", onclick: () => this.showThing(set.id, piece.id) }, [
        el("span", { class: "mmc-st-hue", style: piece.plays ? { "--tag": `var(--mmc-tag-${S.tagIndex(piece.plays) % 8})` } : {} }),
        el("span", { text: this.labelOf(piece) })]))),
      rest ? t(rest === 1 ? "One unnamed wall or block besides." : "{n} unnamed walls and blocks besides.", { n: rest }) : null),
      this.irow(t("Add"), el("div", { class: "mmc-reel-inline" }, ["person", "block", "wall", "post"].map((kind) =>
        el("button", { class: "mmc-reel-btn", text: this.kindLabel(kind), onclick: () => { this.onSet(set.id); this.addThing(kind); } })))),
      el("div", { class: "mmc-reel-machine", text: t("A piece that is named or plays someone is put into the staging sentence. Unnamed pieces only shape the depth pass.") }),
    ]);
  }

  /** Put the glass on a shot staged on this set, if it is not on one already. */
  onSet(id) {
    if (this.set()?.id === id) return;
    const first = S.shotsOnSet(this.timeline, id).find((index) => S.isStaged(this.timeline, this.timeline.segments[index]));
    if (first != null) this.goTo(first, 0);
  }

  /** A piece of a set, selected from outside the glass. */
  showThing(setId, id) {
    this.onSet(setId);
    if (this.set()?.id === setId) this.select({ kind: "thing", id });
  }

  /** A piece of the set, as it stands at the playhead. A person is blocked in
   *  this shot; anything else is the set. */
  inspectThing() {
    const set = this.set();
    const id = this.sel.id;
    const base = set.objects.find((piece) => piece.id === id);
    const now = this.selectedThing();
    const person = base.kind === "person";
    const index = this.index();
    const marks = this.staging().people?.[id];
    const used = S.shotsOnSet(this.timeline, set.id);
    const edit = (write) => { write(); this.commit(); };
    const pose = (key, value) => edit(() => { this.holdOf(id).target[key] = value; });
    const nudge = (key, by) => {
      const value = Math.round((((now[key] ?? 0) + by) * DEG) / 15) * 15 / DEG;
      pose(key, key === "ry" ? wrapTurn(value) : clamp(value, -Math.PI, Math.PI));
    };
    const stepper = (text, minus, plus) => el("span", { class: "mmc-reel-stepper" }, [
      el("button", { text: "−", "aria-label": t("Less"), onclick: minus }), el("span", { text }),
      el("button", { text: "+", "aria-label": t("More"), onclick: plus })]);
    const deg = (angle) => Math.round((angle ?? 0) * DEG);
    const lean = (angle, positive, negative) => {
      const d = deg(angle);
      return d === 0 ? "0°" : `${Math.abs(d)}° ${d > 0 ? positive : negative}`;
    };
    const vec = (slots) => el("div", { class: "mmc-bo-vec" }, slots.map(([axis, value, write]) => el("label", { class: "mmc-bo-vecslot" }, [
      el("span", { class: `mmc-bo-axis is-${axis.toLowerCase()}`, text: axis }),
      el("input", { class: "mmc-bo-num", type: "number", step: "0.05", value: String(Math.round(value * 100) / 100), "aria-label": axis,
        onchange: (event) => { const v = parseFloat(event.target.value); if (Number.isFinite(v)) edit(() => write(v)); } }),
    ])));
    const posture = this.postureOf(now);
    const walk = marks && marks.length > 1
      ? Math.hypot(marks[0].x - marks[marks.length - 1].x, marks[0].z - marks[marks.length - 1].z, marks[0].y - marks[marks.length - 1].y) : 0;
    const others = (handle) => set.objects.some((piece) => piece.plays === handle && piece.id !== id);
    const rows = [
      this.ihead(this.labelOf(base), person ? t("in shot {n} at {s}", { n: index + 1, s: secondsText(this.at.t) })
        : `${t("the {name} set", { name: set.name.toLowerCase() })} · ${rangeText(used)}`),
      el("p", { class: "mmc-reel-why", text: person
        ? t("Drag them to block this shot: Move slides them, Turn tips them over, Lift takes them off the floor. Move the playhead first to give them a second mark, and they go from one to the other.")
        : t("Part of the set. Moving it reshoots {range}.", { range: rangeText(used) }) }),
      person
        ? this.irow(t("Plays"), this.segmented([["", t("Nobody")], ...(this.timeline.subjects ?? []).map((subject) => [subject.handle, `@${subject.handle}`, null,
            others(subject.handle) ? t("@{who} already stands on this set", { who: subject.handle }) : null])], base.plays,
          (handle) => edit(() => { base.plays = handle; })))
        : this.irow(t("Called"), el("input", { class: "mmc-reel-seed", type: "text", value: base.word, placeholder: t("table, doorway, car…"),
            "aria-label": t("What this piece is called"),
            onchange: (event) => edit(() => { base.word = event.target.value.trim().toLowerCase().slice(0, 48); }) }),
          base.word ? t("Named in the staging sentence.") : t("Unnamed: it only shapes the depth pass.")),
      this.irow(t("Place"), vec([
        ["X", now.x, (v) => { this.holdOf(id).target.x = clamp(v, -FAR, FAR); }],
        ["Y", now.y ?? 0, (v) => { this.holdOf(id).target.y = clamp(v, 0, BIG); }],
        ["Z", now.z, (v) => { this.holdOf(id).target.z = clamp(v, -FAR, FAR); }]]),
      (now.y ?? 0) > 0.02 ? t("Y is how far its lowest point is off the floor.") : null),
      this.irow(t("Turned"), stepper(`${((deg(now.ry) % 360) + 360) % 360}°`, () => nudge("ry", -Math.PI / 12), () => nudge("ry", Math.PI / 12))),
      this.irow(t("Tipped"), el("div", { class: "mmc-reel-inline" }, [
        stepper(lean(now.rx, t("forward"), t("back")), () => nudge("rx", -Math.PI / 12), () => nudge("rx", Math.PI / 12)),
        stepper(lean(now.rz, t("right"), t("left")), () => nudge("rz", -Math.PI / 12), () => nudge("rz", Math.PI / 12)),
        ...(posture ? [el("button", { class: "mmc-reel-btn", text: person ? t("Stand them up") : t("Stand it up"),
          onclick: () => edit(() => { Object.assign(this.holdOf(id).target, { rx: 0, rz: 0, y: 0 }); }) })] : []),
      ]), posture ? `${posture.charAt(0).toUpperCase()}${posture.slice(1)}. ${t("The staging sentence says so.")}`
        : person ? t("Standing.") : t("Upright.")),
      person
        ? this.irow(t("In this shot"), el("div", { class: "mmc-reel-inline" }, [
            el("span", { class: "mmc-reel-note", text: walk > 0.3 ? t("Travels {m} m between {n} marks.", { m: walk.toFixed(1), n: marks.length })
              : marks && marks.length > 1 ? t("Changes where they stand, on the spot.") : t("Holds one mark.") }),
            ...(marks && marks.length > 1 ? [el("button", { class: "mmc-reel-btn", text: t("Hold the first mark"),
              onclick: () => edit(() => { this.staging().people[id] = [marks[0]]; }) })] : []),
          ]))
        : this.irow(t("Size"), vec([
            ["W", base.w, (v) => { base.w = clamp(v, 0.05, BIG); }],
            ["H", base.h, (v) => { base.h = clamp(v, 0.05, BIG); }],
            ["D", base.d, (v) => { base.d = clamp(v, 0.05, BIG); }]])),
      el("div", { class: "mmc-reel-actions quiet" }, [el("button", { class: "mmc-reel-btn quiet danger", text: t("Take off the set"),
        onclick: () => this.removeThing() })]),
    ];
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  /** A join: whether the second shot continues from the first, and on a hard
   *  cut which set it goes to. A clip on either side is the reel's join. */
  inspectJoin(index) {
    const segments = this.timeline.segments;
    const segment = segments[index];
    const before = segments[index - 1];
    if (S.isClip(segment) || S.isClip(before) || S.merged(segment)) return super.inspectJoin(index);
    const on = S.continues(segment);
    const blocked = on ? null : S.blockedReason(segment, "continue");
    const rows = [
      this.ihead(t("Join {a} → {b}", { a: index, b: index + 1 }), on ? t("continues") : t("hard cut")),
      el("p", { class: "mmc-reel-why", text: on
        ? t("Shot {b} continues from the last frames of shot {a}, on the same set.", { a: index, b: index + 1 })
        : t("A hard cut. Shot {b} starts a new scene, with a set and a keystone of its own.", { b: index + 1 }) }),
      this.irow(t("Continues"), this.switchControl(on, (value) => this.setContinues(index, value), Boolean(blocked)), blocked),
    ];
    if (on) {
      rows.push(this.blendRow(index));
      rows.push(...this.lineUpRows(index));
    } else {
      const sets = this.timeline.sets ?? [];
      if (sets.length) {
        rows.push(this.irow(t("Set"), this.segmented(sets.map((set) => [set.id, set.name]),
          S.isStaged(this.timeline, segment) ? segment.set : null, (id) => this.moveToSet(index, id)),
        t("Every shot that continues from shot {n} moves with it.", { n: index + 1 })));
      }
    }
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  /** Continue a join, or cut it. A shot continuing from another is on its set:
   *  it carries on in the same room. */
  setContinues(index, on) {
    const segment = this.timeline.segments[index];
    const before = this.timeline.segments[index - 1];
    segment.continue = on;
    segment.continue_audio = on;
    if (on && S.isStaged(this.timeline, before) && segment.set !== before.set) {
      segment.set = before.set;
      segment.staging = { camera: segment.staging?.camera?.length ? segment.staging.camera : [], people: {} };
      lineUp(this.timeline, index);
      if (!segment.staging.camera.length) {
        const end = cameraAt(before.staging.camera, this.seconds(index - 1));
        delete end.t;
        segment.staging.camera = [{ ...end, t: 0 }];
      }
    }
    this.commit();
  }

  /** A hard cut's shot onto another set, with every shot continuing from it. */
  moveToSet(index, id) {
    const segments = this.timeline.segments;
    for (let i = index; i < segments.length; i++) {
      if (i > index && (!S.continues(segments[i]) || S.isClip(segments[i]))) break;
      const segment = segments[i];
      segment.set = id;
      segment.staging = { camera: segment.staging?.camera?.length ? segment.staging.camera : [{ ...START_CAMERA, t: 0 }], people: {},
        ...(segment.staging?.pass !== undefined ? { pass: segment.staging.pass } : {}),
        ...(segment.staging?.hold ? { hold: segment.staging.hold } : {}) };
    }
    this.commit();
  }
}

/** A playhead snapped to its shot: to its ends within a frame or so, else to
 *  a twentieth of a second, so marks land where they can be found again. */
function snapTime(t, seconds) {
  if (t < 0.14) return 0;
  if (seconds - t < 0.14) return seconds;
  return Math.round(t * 20) / 20;
}

/** A person's pose as a mark at `t`. */
const restMark = (piece, t) => ({ t, x: piece.x, y: piece.y ?? 0, z: piece.z,
  rx: piece.rx ?? 0, ry: piece.ry ?? 0, rz: piece.rz ?? 0 });

/** An angle folded into (-π, π]. */
const wrapTurn = (angle) => (((angle + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;

/** The family's frame rate, for counting a guide's frames. */
const rulesFps = (timeline) => rulesFor(S.pieceFamily(timeline)).fps;

/** The heights of a piece's corners, for hanging a label over it. */
const cornersY = (piece) => cornersOf(piece).map((corner) => corner[1]);

export { Blockout, drawStaged };
