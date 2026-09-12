// The picture editor: one door onto everything that can be done to an
// attached picture or clip without touching the file — a window on the
// picture (crop), which way up it is (turn, mirror), and on a picture whose
// family can cut, whether the subject is lifted off its background and which
// subject the scissors mean (the SAM clicks).
//
// It used to be three doors: the segment editor's spatial twin for the crop,
// the subject view for the clicks, and a footer link for the scissors. They
// are one thing to the person using them — "this part of this picture, as a
// cutout" — and were three things only because they were built at three
// times. The subject view's whole job lives here now; `trim.js` stays its own
// editor because a stretch of time is a different question from a part of a
// picture.
//
// What it hands back is what the asset stores: the framing blob
// `creator/crop.py` reads — fractions of the picture *as shown here*, after
// the turn and the mirror — and, where cutting was offered, the scissors and
// the clicks as `plate.cut_panel` reads them, fractions of the *framed*
// picture. Here the clicks live in the stage's own pixels, so a click stays on
// the thing that was clicked while the window moves over it, and are
// converted on the way out; a click that ends up outside the window is
// dropped, since it names nothing the matte will see.
//
// Nothing here knows what the file is for. The one thing a host can add is
// the shape of the shot it is going to — `aspect` — so a reference can be
// cropped to it in one press, which is what the pre-stage's "crop it, or set
// the aspect to match" note was asking for.

import { el, icon, mountOverlay } from "./dom.js";
import { viewUrl, isFramed, isWindowed, cutPanel, buildPlate } from "./api.js";
import { greyField } from "./subject.js";
import { t } from "./i18n.js";

export { isFramed } from "./api.js";

// The longest edge the picture is decoded to for the stage. A 6000 px sheet
// drawn at 6000 px is a 100 MB canvas for a 700 px view; the box is measured
// in fractions, so the readout still says the source's own pixels.
const STAGE_EDGE = 1600;

// The smallest window that is still a picture, as a fraction of either edge —
// `crop.MIN_FRACTION`, and refused there for a blob that slips under it.
const MIN_FRACTION = 0.01;

// A window within this much of the whole picture *is* the whole picture: a
// box dragged to the edge and one pixel short of it is not a crop anybody
// meant, and the asset stays clean of a framing that frames nothing.
const WHOLE_SLACK = 0.004;

const ASPECTS = [
  { key: "free", label: "free", ratio: null },
  { key: "square", label: "1:1", ratio: 1 },
  { key: "wide", label: "16:9", ratio: 16 / 9 },
  { key: "tall", label: "9:16", ratio: 9 / 16 },
];

/** What a chip says about a framing, in the fewest words: "cropped", the
 *  turn, the mirror — each only when set, joined the way the rest of the
 *  chip's summary is. Empty for a picture used as it is. */
export function cropLabel(crop) {
  if (!isFramed(crop)) return "";
  const said = [];
  if (isWindowed(crop)) said.push(t("cropped"));
  if (crop.turn) said.push(`↻ ${crop.turn}°`);
  if (crop.mirror) said.push(t("mirrored"));
  return said.join(" · ");
}

/**
 * @param {object} options
 * @param {string} options.path       input-relative filename
 * @param {string} options.kind       image | video — what the file is
 * @param {?object} options.crop      the framing as stored, null for none
 * @param {?{start:number,end:number}} [options.trim]  a clip's segment, so the
 *   scrub covers the stretch that is actually used
 * @param {?{ratio:number,label:string}} [options.aspect]  the shot's shape, so
 *   the window can be locked to it
 * @param {?object} [options.cutout]  offer the scissors: `{plate, cut, points}`
 *   — `state.plateSpec`'s answer, whether the picture is cut now, and the
 *   clicks so far as `[{x, y, include}]` in fractions of the framed picture.
 *   Null (a clip, a family that cannot cut) leaves the editor to the framing.
 * @returns {Promise<?{crop:?object, cut?:boolean, points?:Array}>} null if
 *   cancelled; `crop` null for the picture whole; `cut` and `points` only
 *   where `cutout` was offered
 */
export function openPicture(options) {
  return new Promise((resolve) => new Picture(options, resolve).mount());
}

/**
 * The editor on something already attached — the whole of it, so every host
 * folds one answer the same way. Opens on the asset's source picture (a
 * cut-out's panel, or the file itself), with the scissors where `plate` is
 * given and the asset may be cut, and when the answer says cut, builds the
 * plate here. -> null on cancel, else `{crop, cut, points, plate}` where
 * `plate` is `{path, panels: [{path, cut, points, crop}]}` for a cutout and
 * null for the picture as it is.
 *
 * @param {object} asset   the attached row: `filename`, `kind`, `trim`,
 *   `crop`, and `panels` on a cut-out
 * @param {object} options `plate` (`state.plateSpec`) and `aspect`
 */
export async function editPicture(asset, { plate = null, aspect = null } = {}) {
  const panel = asset.panels?.length === 1 ? asset.panels[0] : null;
  const source = panel?.filename ?? asset.filename;
  // The scissors are there for every still picture, on every surface. What a
  // role or a scope makes of a cutout is the user's call, not a gate here.
  const cutting = Boolean(plate) && asset.kind === "image";
  const result = await openPicture({
    path: source, kind: asset.kind,
    crop: (panel ? panel.crop : asset.crop) ?? null,
    trim: asset.trim ?? null, aspect,
    cutout: cutting ? { plate, cut: Boolean(panel?.cut), points: panel?.points ?? [] } : null,
  });
  if (!result) return null;
  const answer = { crop: result.crop, cut: Boolean(result.cut), points: result.points ?? [],
                   source, plate: null };
  if (answer.cut) {
    const made = { path: source, cut: true,
                   ...(answer.points.length ? { points: answer.points } : {}),
                   ...(answer.crop ? { crop: answer.crop } : {}) };
    const built = await buildPlate({ ...plate, panels: [made] });
    answer.plate = { path: built.path, panels: [made] };
  }
  return answer;
}

/** A pick — the picker's, or the editor's through `asPick` — onto an attached
 *  row, in place: the handle and everything else on it stay. A plate of one
 *  lands as the built file plus the panel it was cut from, so the editor
 *  opens on the photograph next time. For rows the sheet fold does not own —
 *  a keyframe, a guide, the pre-stage's chips. */
export function applyPick(row, pick) {
  delete row.panels;
  delete row.crop;
  row.filename = pick.path;
  if (pick.plate) {
    row.panels = pick.panels.map((panel) => ({
      filename: panel.path, cut: true,
      ...(panel.points?.length ? { points: panel.points } : {}),
      ...(panel.crop ? { crop: panel.crop } : {}),
    }));
  } else if (pick.crop) {
    row.crop = pick.crop;
  }
  return row;
}

/** `editPicture`'s answer as the picker hands a pick back — a plate of one,
 *  or the source with its framing — so a host folds it exactly as it folds a
 *  fresh attachment (`mergeSheet`, `foldPoolSheet`, `plateEntry`). */
export function asPick(answer) {
  const name = answer.source.split("/").pop();
  if (answer.plate) {
    return { plate: true, kind: "image", path: answer.plate.path,
             name: answer.plate.path.split("/").pop(), panels: answer.plate.panels };
  }
  return { kind: "image", path: answer.source, name, crop: answer.crop };
}

const round = (value) => Math.round(value * 10000) / 10000;
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

class Picture {
  constructor(options, resolve) {
    this.options = options;
    this.resolve = resolve;
    const given = options.crop ?? {};
    this.turn = Number(given.turn) || 0;
    this.mirror = String(given.mirror ?? "");
    // The window, in fractions of the turned, mirrored picture — the same
    // numbers the blob carries — until the picture lands and it becomes
    // pixels of the stage (`box`), which is what the handles move.
    this.pending = { x: given.x ?? 0, y: given.y ?? 0, w: given.w ?? 1, h: given.h ?? 1 };
    this.box = null;
    this.source = null;        // the decoded picture: an <img> or a <video>
    this.sourceSize = null;    // [w, h] as shown, before the turn
    this.aspect = null;        // the locked w/h, or null for free
    this.aspectKey = "free";
    this.duration = 0;
    // The scissors, where offered. Clicks are kept in stage pixels — see the
    // module note — and become fractions of the window on the way out.
    this.cutout = options.cutout ?? null;
    this.cut = Boolean(this.cutout?.cut);
    this.keeping = true;       // what the next click means: keep, or drop
    this.points = [];          // [{x, y, include}] in stage pixels
    this.pendingPoints = (this.cutout?.points ?? []).map((p) => ({ ...p }));
    this.matte = null;         // the cutout preview: an <img> holding the PNG
    this.matteKey = null;      // what the preview was asked for
    this.matteUrl = null;
    this.fetching = null;
    this.error = "";
  }

  // ---- mount ---------------------------------------------------------------

  mount() {
    const { options } = this;
    const isVideo = options.kind === "video";

    this.canvas = el("canvas", { class: "mmc-crop-canvas" });
    this.dots = el("div", { class: "mmc-crop-dots" });
    this.scan = el("div", { class: "mmc-plate-scan" });
    this.window = el("div", {
      class: "mmc-crop-window", tabindex: "0",
      title: t("Drag to move the window; arrow keys nudge it"),
    }, [
      ...["nw", "ne", "sw", "se"].map((corner) => this.handle(corner)),
      ...["n", "s", "w", "e"].map((edge) => this.handle(edge)),
      el("div", { class: "mmc-crop-thirds" }),
    ]);
    this.stage = el("div", {
      class: "mmc-crop-stage",
      onpointerdown: (event) => this.beginDraw(event),
    }, [this.canvas, this.window, this.dots]);
    this.drag(this.window, () => {
      const from = { ...this.box };
      return (dx, dy) => this.moveTo(from.x + dx, from.y + dy);
    }, (at, event) => this.tapped(at, event));
    this.window.addEventListener("keydown", (event) => this.nudge(event));

    // The transport, for a clip: the framing has to hold across the segment,
    // not just on the frame it happened to open on.
    if (isVideo) {
      this.playButton = el("button", {
        class: "mmc-trim-play", title: t("Play the segment"),
        onclick: () => this.togglePlay(),
      }, [icon("play", 16)]);
      this.playhead = el("div", { class: "mmc-trim-head" });
      this.scrub = el("div", {
        class: "mmc-crop-scrub",
        onpointerdown: (event) => this.beginScrub(event),
      }, [this.playhead]);
    }

    this.readout = el("div", { class: "mmc-trim-read" });

    const turns = el("div", { class: "mmc-seg", role: "group", "aria-label": t("Turn or mirror") }, [
      this.tool("turnLeft", t("Turn a quarter anticlockwise"), () => this.turnBy(270)),
      this.tool("turnRight", t("Turn a quarter clockwise"), () => this.turnBy(90)),
      this.tool("mirrorH", t("Mirror left to right"), () => this.flip("h")),
      this.tool("mirrorV", t("Mirror top to bottom"), () => this.flip("v")),
    ]);

    const aspects = [...ASPECTS];
    if (options.aspect?.ratio) {
      // The shot's own shape, first: it is the one most people opened this
      // for, and the pre-stage's warning names it.
      aspects.splice(1, 0, { key: "shot", label: options.aspect.label || t("shot"),
                             ratio: options.aspect.ratio, shot: true });
    }
    this.aspectEntries = aspects;
    this.aspectButtons = aspects.map((entry) => el("button", {
      class: "mmc-seg-opt", text: entry.label,
      title: entry.shot
        ? t("Lock the window to the shape of the shot it is going to")
        : entry.ratio ? t("Lock the window to {ratio}", { ratio: entry.label })
          : t("Any shape"),
      onclick: () => this.lockAspect(entry),
    }));

    this.wholeButton = el("button", {
      class: "mmc-ghost", text: t("Whole picture"),
      title: t("Take the whole picture again — the turn and the mirror stay"),
      onclick: () => { this.setBox(0, 0, this.pw, this.ph); this.changed(); },
    });

    // The scissors row, where the family can cut: on or off, what the next
    // click means, and a way back to the whole-subject cut. Its own row under
    // the framing's, because it is a second decision about the same window.
    if (this.cutout) {
      this.cutButton = el("button", {
        class: "mmc-ghost mmc-crop-cut",
        title: t("Lift the subject off its background, onto the flat field the model reads "
               + "references against. The room it was photographed in stops conditioning "
               + "the render alongside it."),
        onclick: () => { this.cut = !this.cut; this.changed(); },
      }, [icon("scissors", 13), el("span", { text: t("Cut out") })]);
      this.keepButton = el("button", {
        class: "mmc-ghost mmc-tool", text: t("Keep"),
        title: t("Clicks mark the subject to keep"),
        onclick: () => { this.keeping = true; this.paint(); },
      });
      this.dropButton = el("button", {
        class: "mmc-ghost mmc-tool", text: t("Drop"),
        title: t("Clicks mark what to leave out — shift-click does one without switching"),
        onclick: () => { this.keeping = false; this.paint(); },
      });
      this.resetButton = el("button", {
        class: "mmc-ghost", text: t("Start over"),
        title: t("Forget every click and go back to the whole-subject cut"),
        onclick: () => { this.points = []; this.keeping = true; this.changed(); },
      });
      this.say = el("span", { class: "mmc-plate-say" });
    }

    const foot = el("div", { class: "mmc-trim-foot" }, [
      turns,
      el("div", { class: "mmc-seg", role: "group", "aria-label": t("Window shape") }, this.aspectButtons),
      this.wholeButton,
      el("span", { class: "mmc-trim-spacer" }),
      el("button", { class: "mmc-ghost", text: t("Cancel"), onclick: () => this.close(null) }),
      el("button", { class: "mmc-add", text: t("Use"), onclick: () => this.commit() }),
    ]);

    this.modal = el("div", { class: "mmc-trim mmc-crop" }, [
      el("div", { class: "mmc-trim-head-row" }, [
        el("span", { class: "mmc-trim-name", text: options.path.split("/").pop() }),
        el("button", { class: "mmc-close", text: "✕", onclick: () => this.close(null) }),
      ]),
      el("div", { class: "mmc-crop-frame" }, [this.stage]),
      ...(isVideo ? [el("div", { class: "mmc-trim-bar" }, [this.playButton, this.scrub])] : []),
      this.readout,
      ...(this.cutout ? [el("div", { class: "mmc-crop-cutrow" }, [
        this.cutButton,
        el("div", { class: "mmc-subject-pol" }, [this.keepButton, this.dropButton]),
        this.resetButton,
        this.say,
      ])] : []),
      foot,
    ]);
    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(null); },
      // Same seal as the picker's overlays: nothing dropped here may fall
      // through to ComfyUI's file-import drop handler.
      ondragover: (event) => event.preventDefault(),
      ondrop: (event) => { event.preventDefault(); event.stopPropagation(); },
    }, [this.modal]);
    this.unmount = mountOverlay(this.overlay, () => this.close(null));
    this.paint();
    this.load();
  }

  tool(name, title, onclick) {
    return el("button", { class: "mmc-seg-opt mmc-crop-tool", title, onclick }, [icon(name, 15)]);
  }

  handle(where) {
    const corner = where.length === 2;
    const node = el("div", {
      class: `mmc-crop-handle mmc-crop-${where}${corner ? " mmc-crop-corner" : ""}`,
      tabindex: "0", role: "slider",
      title: corner ? t("Drag a corner to resize") : t("Drag an edge to resize"),
    });
    this.drag(node, () => {
      const from = { ...this.box };
      return (dx, dy) => this.resize(where, from, dx, dy);
    });
    node.addEventListener("keydown", (event) => this.nudge(event, where));
    return node;
  }

  // ---- the picture ----------------------------------------------------------

  /** Decode the file. A still through an <img>, a clip through a <video>
   *  kept out of the document and copied onto the canvas frame by frame — the
   *  same reason `trim.js` draws rather than shows: a composited <video> is a
   *  black rectangle on a good many Linux setups. */
  load() {
    const source = viewUrl(this.options.path);
    if (this.options.kind === "video") {
      const video = document.createElement("video");
      video.preload = "auto";
      video.muted = true;
      video.playsInline = true;
      video.src = source;
      video.addEventListener("loadedmetadata", () => {
        this.duration = Number.isFinite(video.duration) ? video.duration : 0;
        this.segment = this.options.trim
          ? [clamp(this.options.trim.start, 0, this.duration), clamp(this.options.trim.end, 0, this.duration)]
          : [0, this.duration];
        video.currentTime = this.segment[0];
      });
      video.addEventListener("loadeddata", () => this.arrived(video, [video.videoWidth, video.videoHeight]));
      video.addEventListener("seeked", () => this.draw());
      video.addEventListener("timeupdate", () => this.onTime());
      video.addEventListener("play", () => this.onPlayState());
      video.addEventListener("pause", () => this.onPlayState());
      video.addEventListener("error", () => this.fail());
      this.source = video;
      return;
    }
    const image = new Image();
    image.onload = () => this.arrived(image, [image.naturalWidth, image.naturalHeight]);
    image.onerror = () => this.fail();
    image.src = source;
    this.source = image;
  }

  arrived(source, size) {
    if (this.sourceSize) { this.draw(); return; }
    if (!size[0] || !size[1]) return this.fail();
    this.sourceSize = size;
    this.stageScale = Math.min(1, STAGE_EDGE / Math.max(...size));
    this.layout();
    // The window the asset came in with, now in pixels of the stage — and
    // the clicks, which were fractions of that window.
    const p = this.pending;
    this.setBox(p.x * this.pw, p.y * this.ph, p.w * this.pw, p.h * this.ph);
    this.points = this.pendingPoints.map((point) => ({
      x: this.box.x + point.x * this.box.w, y: this.box.y + point.y * this.box.h,
      include: point.include !== false,
    }));
    this.changed();
  }

  fail() {
    this.status = t("This browser cannot show this file, so there is nothing to draw the window on.");
    this.paint();
  }

  /** The stage's size after the turn, and the canvas to match. */
  layout() {
    const [w, h] = this.sourceSize;
    const sw = Math.round(w * this.stageScale);
    const sh = Math.round(h * this.stageScale);
    [this.pw, this.ph] = this.turn % 180 ? [sh, sw] : [sw, sh];
    if (this.canvas.width !== this.pw || this.canvas.height !== this.ph) {
      this.canvas.width = this.pw;
      this.canvas.height = this.ph;
    }
    this.draw();
  }

  /** The picture as the blob describes it: turned, then mirrored. Set up in
   *  the reverse order because a canvas transform applies to the drawing
   *  last-set first — see `creator/crop.py` for the order the render uses.
   *  With the scissors on and a matte in hand, the window shows the cutout
   *  on the family's field instead of the picture: the promise, kept. */
  draw() {
    if (!this.sourceSize || !this.source) return;
    const ctx = this.canvas.getContext("2d");
    const [w, h] = this.sourceSize;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.pw, this.ph);
    if (this.mirror.includes("h")) { ctx.translate(this.pw, 0); ctx.scale(-1, 1); }
    if (this.mirror.includes("v")) { ctx.translate(0, this.ph); ctx.scale(1, -1); }
    if (this.turn === 90) { ctx.translate(this.pw, 0); ctx.rotate(Math.PI / 2); }
    else if (this.turn === 180) { ctx.translate(this.pw, this.ph); ctx.rotate(Math.PI); }
    else if (this.turn === 270) { ctx.translate(0, this.ph); ctx.rotate(-Math.PI / 2); }
    ctx.drawImage(this.source, 0, 0, w * this.stageScale, h * this.stageScale);
    if (this.cut && this.matte && this.matteKey === this.key() && this.box) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const { x, y, w: bw, h: bh } = this.box;
      ctx.fillStyle = greyField(this.cutout.plate.backdrop);
      ctx.fillRect(x, y, bw, bh);
      ctx.drawImage(this.matte, x, y, bw, bh);
    }
  }

  // ---- the window ----------------------------------------------------------

  /** Pixels of the stage -> the window's place on screen, and the dots'. */
  place() {
    if (!this.box || !this.pw) return;
    const { x, y, w, h } = this.box;
    Object.assign(this.window.style, {
      left: `${(x / this.pw) * 100}%`, top: `${(y / this.ph) * 100}%`,
      width: `${(w / this.pw) * 100}%`, height: `${(h / this.ph) * 100}%`,
    });
    this.dots.replaceChildren(...(this.cut ? this.points.map((point, at) => {
      const dot = el("button", {
        class: "mmc-st-dot" + (point.include ? "" : " out"),
        title: point.include
          ? t("A click on the subject — press to take it back")
          : t("A click on what to leave out — press to take it back"),
        onpointerdown: (event) => event.stopPropagation(),
        onclick: (event) => {
          event.stopPropagation();
          this.points.splice(at, 1);
          this.changed();
        },
      });
      dot.style.left = `${(point.x / this.pw) * 100}%`;
      dot.style.top = `${(point.y / this.ph) * 100}%`;
      return dot;
    }) : []));
  }

  setBox(x, y, w, h) {
    const minW = Math.max(1, this.pw * MIN_FRACTION);
    const minH = Math.max(1, this.ph * MIN_FRACTION);
    w = clamp(w, minW, this.pw);
    h = clamp(h, minH, this.ph);
    x = clamp(x, 0, this.pw - w);
    y = clamp(y, 0, this.ph - h);
    this.box = { x, y, w, h };
    this.place();
  }

  moveTo(x, y) {
    this.setBox(x, y, this.box.w, this.box.h);
    this.changed();
  }

  /** Resize by a handle, the opposite side held. With a locked shape the
   *  dragged corner follows the pointer along whichever axis moved more and
   *  the other axis follows the ratio; an edge moves its own axis and the
   *  window grows about its centre on the other. */
  resize(where, from, dx, dy) {
    let { x, y, w, h } = from;
    const right = from.x + from.w;
    const bottom = from.y + from.h;
    if (where.includes("e")) w = from.w + dx;
    if (where.includes("w")) { x = from.x + dx; w = right - x; }
    if (where.includes("s")) h = from.h + dy;
    if (where.includes("n")) { y = from.y + dy; h = bottom - y; }
    if (this.aspect) {
      const edge = where.length === 1;
      if (edge && (where === "n" || where === "s")) w = h * this.aspect;
      else if (edge) h = w / this.aspect;
      else if (Math.abs(dx) >= Math.abs(dy)) h = w / this.aspect;
      else w = h * this.aspect;
      // Bounded by the picture: a locked window pushed against an edge stops
      // growing on both axes rather than breaking its shape.
      const maxW = where.includes("w") ? right : where.includes("e") ? this.pw - from.x : this.pw;
      const maxH = where.includes("n") ? bottom : where.includes("s") ? this.ph - from.y : this.ph;
      if (w > maxW) { w = maxW; h = w / this.aspect; }
      if (h > maxH) { h = maxH; w = h * this.aspect; }
      if (edge && (where === "n" || where === "s")) x = from.x + (from.w - w) / 2;
      else if (edge) y = from.y + (from.h - h) / 2;
      if (where.includes("w")) x = right - w;
      if (where.includes("n")) y = bottom - h;
    }
    const minW = Math.max(1, this.pw * MIN_FRACTION);
    const minH = Math.max(1, this.ph * MIN_FRACTION);
    if (w < minW) { w = minW; if (where.includes("w")) x = right - w; }
    if (h < minH) { h = minH; if (where.includes("n")) y = bottom - h; }
    this.setBox(x, y, w, h);
    this.changed();
  }

  /** A press on the bare picture draws a new window from that point. With
   *  the scissors on, the picture outside the window is nothing the matte
   *  sees, so a press there does nothing at all. */
  beginDraw(event) {
    if (!this.box || event.target !== this.canvas || this.cut) return;
    event.preventDefault();
    const origin = this.point(event);
    this.stage.setPointerCapture(event.pointerId);
    let drew = false;
    const move = (event2) => {
      const at = this.point(event2);
      let w = Math.abs(at.x - origin.x);
      let h = Math.abs(at.y - origin.y);
      if (w < 2 && h < 2) return;
      drew = true;
      if (this.aspect) {
        if (w / this.aspect >= h) h = w / this.aspect;
        else w = h * this.aspect;
      }
      const x = at.x >= origin.x ? origin.x : origin.x - w;
      const y = at.y >= origin.y ? origin.y : origin.y - h;
      this.setBox(x, y, w, h);
      this.window.classList.add("dragging");
      this.changed();
    };
    const up = () => {
      this.stage.removeEventListener("pointermove", move);
      this.stage.removeEventListener("pointerup", up);
      this.stage.removeEventListener("pointercancel", up);
      this.window.classList.remove("dragging");
      // A click that drew nothing centres a window of the current size on
      // the point — the one gesture that says "here" without a drag.
      if (!drew) this.moveTo(origin.x - this.box.w / 2, origin.y - this.box.h / 2);
    };
    this.stage.addEventListener("pointermove", move);
    this.stage.addEventListener("pointerup", up);
    this.stage.addEventListener("pointercancel", up);
  }

  /** A tap on the window that moved nothing. With the scissors on it is a
   *  click on the subject — keep, or drop with shift — the way it is in the
   *  sheet editor; otherwise it is nothing, the window is where it was. */
  tapped(at, event) {
    if (!this.cut) return;
    this.points.push({ x: at.x, y: at.y, include: this.keeping !== Boolean(event?.shiftKey || event?.altKey) });
    this.changed();
  }

  /** A pointer event -> pixels of the stage. */
  point(event) {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width) return { x: 0, y: 0 };
    return {
      x: clamp(((event.clientX - rect.left) / rect.width) * this.pw, 0, this.pw),
      y: clamp(((event.clientY - rect.top) / rect.height) * this.ph, 0, this.ph),
    };
  }

  /** Pointer-drag a piece of the window. `begin()` runs on pointerdown and
   *  returns the per-move step, handed the drag in stage pixels — so each
   *  grab closes over where the window was, and a move is a rigid slide.
   *  `tap(at, event)` runs instead of the step when the pointer never moved. */
  drag(node, begin, tap = null) {
    node.addEventListener("pointerdown", (event) => {
      if (!this.box) return;
      event.preventDefault();
      event.stopPropagation();
      node.setPointerCapture(event.pointerId);
      const origin = this.point(event);
      const step = begin();
      let moved = false;
      const move = (event2) => {
        const at = this.point(event2);
        if (!moved && Math.abs(at.x - origin.x) < 2 && Math.abs(at.y - origin.y) < 2) return;
        moved = true;
        this.window.classList.add("dragging");
        step(at.x - origin.x, at.y - origin.y);
      };
      const up = () => {
        node.removeEventListener("pointermove", move);
        node.removeEventListener("pointerup", up);
        node.removeEventListener("pointercancel", up);
        this.window.classList.remove("dragging");
        if (!moved) tap?.(origin, event);
      };
      node.addEventListener("pointermove", move);
      node.addEventListener("pointerup", up);
      node.addEventListener("pointercancel", up);
    });
  }

  /** Arrow keys: a pixel of the source, ten with shift. On the window they
   *  slide it; on a handle they move that edge. */
  nudge(event, where = null) {
    const steps = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const step = steps[event.key];
    if (!step || !this.box) return;
    event.preventDefault();
    event.stopPropagation();
    const by = (event.shiftKey ? 10 : 1) * this.stageScale;
    const [dx, dy] = [step[0] * by, step[1] * by];
    if (!where) return this.moveTo(this.box.x + dx, this.box.y + dy);
    this.resize(where, { ...this.box }, dx, dy);
  }

  // ---- turn and mirror --------------------------------------------------------

  /** A quarter turn, the window and the clicks turning with the picture. A
   *  mirror already set swaps its axis, because turning a mirrored picture is
   *  mirroring the turned one the other way — see `creator/crop.py` for the
   *  order. */
  turnBy(degrees) {
    if (!this.box) return;
    const { x, y, w, h } = this.box;
    const [pw, ph] = [this.pw, this.ph];
    this.turn = (this.turn + degrees) % 360;
    if (this.mirror) {
      this.mirror = [...this.mirror].map((c) => (c === "h" ? "v" : "h")).sort().join("");
    }
    this.layout();
    const cw = degrees === 90;
    this.points = this.points.map((p) => ({
      ...p, x: cw ? ph - p.y : p.y, y: cw ? p.x : pw - p.x,
    }));
    if (cw) this.setBox(ph - (y + h), x, h, w);
    else this.setBox(y, pw - (x + w), h, w);
    if (this.aspect) this.aspect = 1 / this.aspect;
    this.changed();
  }

  flip(axis) {
    if (!this.box) return;
    const { x, y, w, h } = this.box;
    this.mirror = this.mirror.includes(axis)
      ? this.mirror.replace(axis, "")
      : (axis === "h" ? "h" + this.mirror : this.mirror + "v");
    this.draw();
    this.points = this.points.map((p) => ({
      ...p, x: axis === "h" ? this.pw - p.x : p.x, y: axis === "v" ? this.ph - p.y : p.y,
    }));
    if (axis === "h") this.setBox(this.pw - (x + w), y, w, h);
    else this.setBox(x, this.ph - (y + h), w, h);
    this.changed();
  }

  // ---- shape -------------------------------------------------------------------

  /** Lock the window to a shape, cutting the current window to it about its
   *  centre. Locking to the shot from a whole picture is the one-press answer
   *  to "this picture does not match the canvas". */
  lockAspect(entry) {
    this.aspectKey = entry.key;
    this.aspect = entry.ratio;
    if (this.aspect && this.box) {
      const { x, y, w, h } = this.box;
      let nw = w;
      let nh = w / this.aspect;
      if (nh > h) { nh = h; nw = h * this.aspect; }
      this.setBox(x + (w - nw) / 2, y + (h - nh) / 2, nw, nh);
    }
    this.changed();
  }

  // ---- the scissors ---------------------------------------------------------

  /** What the matte preview is asked for: the window and the clicks, as the
   *  route reads them. A string, so "is the one we have still the one we
   *  want" is a comparison. */
  key() {
    return JSON.stringify([this.value().crop, this.clicks()]);
  }

  /** The clicks as `plate.cut_panel` reads them: fractions of the window,
   *  the ones outside it dropped. */
  clicks() {
    if (!this.box) return [];
    const { x, y, w, h } = this.box;
    return this.points
      .filter((p) => p.x >= x && p.x <= x + w && p.y >= y && p.y <= y + h)
      .map((p) => ({ x: round((p.x - x) / w), y: round((p.y - y) / h), include: p.include }));
  }

  /** Fetch the cutout the window would make, after the change settles: a
   *  run of clicks is many mattes, and only where it ends is a picture
   *  anybody is waiting on. From the server's memory, the way the sheet
   *  stage's panels are; nothing is written. */
  askMatte() {
    clearTimeout(this.matteTimer);
    if (!this.cut || !this.box) return;
    const want = this.key();
    if (want === this.matteKey || want === this.fetching) return;
    this.matteTimer = setTimeout(() => {
      if (!this.overlay.isConnected) return;
      this.fetching = want;
      this.paint();
      const { plate } = this.cutout;
      const crop = this.value().crop;
      cutPanel({ model: plate.model, segment: plate.segment,
                 panels: [{ path: this.options.path, cut: true,
                            ...(this.clicks().length ? { points: this.clicks() } : {}),
                            ...(crop ? { crop } : {}) }] })
        .then((url) => {
          if (this.fetching !== want) { URL.revokeObjectURL(url); return; }
          const image = new Image();
          image.onload = () => {
            if (this.matteUrl) URL.revokeObjectURL(this.matteUrl);
            this.matte = image;
            this.matteUrl = url;
            this.matteKey = want;
            this.fetching = null;
            this.error = "";
            this.draw();
            this.paint();
            // The window may have moved while the matte was on its way.
            this.askMatte();
          };
          image.src = url;
        })
        .catch((problem) => {
          if (this.fetching !== want) return;
          this.fetching = null;
          this.error = problem.message;
          this.paint();
        });
    }, 250);
  }

  // ---- transport (video) ----------------------------------------------------

  beginScrub(event) {
    if (!this.duration) return;
    event.preventDefault();
    this.scrub.setPointerCapture(event.pointerId);
    const seek = (event2) => {
      const rect = this.scrub.getBoundingClientRect();
      const fraction = clamp((event2.clientX - rect.left) / (rect.width || 1), 0, 1);
      this.source.pause();
      this.source.currentTime = this.segment[0] + fraction * (this.segment[1] - this.segment[0]);
      this.paintHead();
    };
    const up = () => {
      this.scrub.removeEventListener("pointermove", seek);
      this.scrub.removeEventListener("pointerup", up);
      this.scrub.removeEventListener("pointercancel", up);
    };
    seek(event);
    this.scrub.addEventListener("pointermove", seek);
    this.scrub.addEventListener("pointerup", up);
    this.scrub.addEventListener("pointercancel", up);
  }

  togglePlay() {
    if (!this.duration) return;
    const video = this.source;
    if (video.paused) {
      if (video.currentTime < this.segment[0] || video.currentTime >= this.segment[1] - 0.02) {
        video.currentTime = this.segment[0];
      }
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  }

  onTime() {
    const video = this.source;
    if (this.duration && video.currentTime >= this.segment[1] - 0.02 && !video.paused) {
      video.pause();
      video.currentTime = this.segment[0];
    }
    this.paintHead();
  }

  onPlayState() {
    this.playButton.replaceChildren(icon(this.source.paused ? "play" : "pause", 16));
    if (!this.source.paused && !this.frameTimer) this.follow();
  }

  follow() {
    this.frameTimer = null;
    if (this.source.paused || !this.overlay.isConnected) return;
    this.draw();
    this.frameTimer = requestAnimationFrame(() => this.follow());
  }

  paintHead() {
    if (!this.playhead || !this.duration) return;
    const span = this.segment[1] - this.segment[0] || 1;
    const at = clamp((this.source.currentTime - this.segment[0]) / span, 0, 1);
    this.playhead.style.left = `${at * 100}%`;
  }

  // ---- render --------------------------------------------------------------

  /** The window as fractions of the turned picture. */
  fractions() {
    if (!this.box) return { ...this.pending };
    return { x: this.box.x / this.pw, y: this.box.y / this.ph,
             w: this.box.w / this.pw, h: this.box.h / this.ph };
  }

  isWhole() {
    const f = this.fractions();
    return f.x <= WHOLE_SLACK && f.y <= WHOLE_SLACK && f.w >= 1 - WHOLE_SLACK && f.h >= 1 - WHOLE_SLACK;
  }

  /** The window in the source's own pixels — what the render gets. */
  pixels() {
    const [w, h] = this.sourceSize;
    const [tw, th] = this.turn % 180 ? [h, w] : [w, h];
    const f = this.fractions();
    return [Math.max(1, Math.round(f.w * tw)), Math.max(1, Math.round(f.h * th)), tw, th];
  }

  paint() {
    this.aspectButtons.forEach((button, index) => {
      button.setAttribute("aria-pressed", this.aspectEntries[index].key === this.aspectKey);
    });
    this.wholeButton.disabled = !this.box || this.isWhole() || undefined;
    this.stage.classList.toggle("cutting", this.cut);
    this.window.title = this.cut
      ? t("Click the subject to keep it, shift-click what should go; drag to move the window")
      : t("Drag to move the window; arrow keys nudge it");
    if (this.cutout) {
      this.cutButton.classList.toggle("on", this.cut);
      this.cutButton.setAttribute("aria-pressed", String(this.cut));
      for (const button of [this.keepButton, this.dropButton, this.resetButton]) {
        button.disabled = !this.cut || undefined;
      }
      this.keepButton.classList.toggle("on", this.cut && this.keeping);
      this.keepButton.setAttribute("aria-pressed", String(this.cut && this.keeping));
      this.dropButton.classList.toggle("on", this.cut && !this.keeping);
      this.dropButton.setAttribute("aria-pressed", String(this.cut && !this.keeping));
      this.resetButton.disabled = !this.cut || !this.points.length || undefined;
      const clicks = this.clicks().length;
      this.say.textContent = this.error || (!this.cut
        ? t("Used whole, background and all.")
        : clicks
          ? t("Click anything else that should go — or press a dot to take it back.")
          : t("The whole subject is cut out. Click the subject you mean if the cut grabbed the wrong thing."));
      this.say.classList.toggle("bad", Boolean(this.error));
      // The sweep on the window while a matte is on its way.
      if (this.fetching && this.cut) this.window.appendChild(this.scan);
      else this.scan.remove();
    }
    if (!this.sourceSize) {
      this.readout.textContent = this.status || t("Reading the picture…");
      return;
    }
    const [pw, ph, tw, th] = this.pixels();
    const said = [];
    if (this.turn) said.push(t("turned {degrees}°", { degrees: this.turn }));
    if (this.mirror) said.push(t("mirrored"));
    if (this.cut) said.push(t("cut out"));
    this.readout.replaceChildren(
      el("span", { text: this.isWhole()
        ? t("Whole picture · {w} × {h}", { w: tw, h: th })
        : t("{w} × {h} of {sw} × {sh}", { w: pw, h: ph, sw: tw, sh: th }) }),
      el("span", { class: "mmc-trim-len", text: [ratioLabel(pw / ph), ...said].join(" · ") }),
    );
  }

  changed() {
    this.place();
    this.draw();
    this.paint();
    this.askMatte();
  }

  value() {
    const crop = {};
    if (!this.isWhole()) {
      const f = this.fractions();
      Object.assign(crop, { x: round(f.x), y: round(f.y), w: round(f.w), h: round(f.h) });
    }
    if (this.turn) crop.turn = this.turn;
    if (this.mirror) crop.mirror = this.mirror;
    const result = { crop: Object.keys(crop).length ? crop : null };
    if (this.cutout) {
      result.cut = this.cut;
      result.points = this.cut ? this.clicks() : [];
    }
    return result;
  }

  commit() {
    this.close(this.value());
  }

  close(result) {
    clearTimeout(this.matteTimer);
    this.fetching = null;
    if (this.matteUrl) URL.revokeObjectURL(this.matteUrl);
    if (this.frameTimer) cancelAnimationFrame(this.frameTimer);
    if (this.source?.pause) {
      this.source.pause();
      this.source.removeAttribute("src");
    }
    this.unmount?.();
    this.resolve?.(result);
  }
}

/** "3:2", "16:9", "1:1" for a shape near a common one, else "1.42:1". */
function ratioLabel(ratio) {
  const common = [[1, 1], [4, 3], [3, 2], [16, 9], [21, 9], [3, 4], [2, 3], [9, 16], [4, 5], [5, 4]];
  for (const [a, b] of common) {
    if (Math.abs(ratio - a / b) < 0.015) return `${a}:${b}`;
  }
  return ratio >= 1 ? `${ratio.toFixed(2)}:1` : `1:${(1 / ratio).toFixed(2)}`;
}
