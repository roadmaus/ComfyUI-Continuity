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
import { viewUrl } from "./api.js";
import * as S from "./state.js";
import { Reel, fitText } from "./reel.js";
import {
  Raster, project, cameraAt, stagedAt, guideSize, stagingSentence, moveSentence,
  PASSES, PRESETS, tagRGB, vfovOf, forwardOf, rightOf, upOf, MOST_PREVIEW, clamp,
  syncStagingWords, drawStaged, START_CAMERA, cornersOf,
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

    this.modal = el("div", { class: "mmc-modal mmc-tl-modal mmc-reel mmc-st-bench" }, [
      el("div", { class: "mmc-reel-head" }, [
        el("span", { class: "mmc-reel-title", text: t("Blockout") }),
        this.titleMeta,
        this.undoButton,
        this.redoButton,
        this.planEl,
        this.cancelButton,
        ...(this.openTimelineWindow ? [this.openButton] : []),
        ...(this.queue ? [this.shootButton] : []),
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
      rows.push(el("div", { class: "mmc-reel-machine" }, [
        el("div", { text: t("What the model is given for this shot") }),
        el("pre", { class: "mmc-reel-compiled mmc-st-words",
          text: (S.stagingPass(this.timeline, segment) === "none" || !guide
            ? "" : `input/${S.STAGED_GUIDE_DIR}/${guide}.mp4 · ${t("{n} frames", { n: frames })} · ${t(PASSES.find((p) => p.id === pass)?.label ?? pass)}\n`)
            + (segment.staging.words || this.wordsOf(index)) }),
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
    const posture = this.postureChanges?.(index) ?? false;
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
        text: stagingSentence(stagedAt(set, staging, 0), marks, this.seconds(index), cameraAt(marks, 0), { w, h }, { withMove: false })
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
}

/** The family's frame rate, for counting a guide's frames. */
const rulesFps = (timeline) => rulesFor(S.pieceFamily(timeline)).fps;

/** The heights of a piece's corners, for hanging a label over it. */
const cornersY = (piece) => cornersOf(piece).map((corner) => corner[1]);

export { Blockout, drawStaged };
