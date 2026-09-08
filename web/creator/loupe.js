// The loupe: a finished file, large, with something to hold it against.
//
// Double-clicking a render used to call `requestFullscreen` on the picture
// itself. That was the cheap answer and it was defensible — the whole display
// rather than the whole window, Escape already meaning what everyone expects —
// but it is the browser's room and not this pack's, and the browser charges for
// it: Firefox throws a black banner across the top of the screen every time,
// the picture is fitted to the display and cannot be looked *into*, and there
// is nowhere to put a second picture. A render is a claim about detail. A
// viewer that cannot magnify one, and cannot show what the alternative looked
// like, is a wallpaper preview.
//
// So this is a room of ours, and it has the two things the browser's has not:
//
// **Zoom that goes to the pixel.** The wheel magnifies about the pointer, a
// drag pans, a double-click flips between fitting the window and 1:1. The
// readout in the foot says which, because "is this actual size" is the first
// question anybody looking for artefacts asks.
//
// **A seam, over any picture in the pack.** The upscale bench proved the shape:
// two versions of the same rectangle, one wipe, tags naming each half. What was
// wrong was that the bench was the only place you could ever see one — the
// refiner is a pill on three surfaces and a switch in a settings page, and
// until now the only way to find out what it did to a shot was to render the
// shot twice. Here the right of the seam is the DLSS 5 pass run on the region
// you are looking at, at the settings on the rail, on a press.
//
// **For a render of this pack's, the other half is the other version of it.**
// Running the refiner over a picture that was already refined compares one pass
// against two, which answers nothing. What the question actually is — what did
// the refiner do to this shot — is answered by the same render without it, and
// that render is nearly free: a finished file carries the prompt that made it,
// the refiner is one boolean in that prompt's blob, and ComfyUI keys an
// expanding node's subcache by its id rather than by its inputs. So the twin
// re-expands the node and hits every sampler underneath it. The save runs; the
// render does not. `creator/neuraltwin.py` is that argument in full.
//
// **For everything else there is the tile.** A photograph, a piece of footage,
// somebody else's render: nothing to re-queue, and the question is the other
// way round — what *would* the refiner do to this. That costs a model pass, so
// it is asked of a square rather than a frame: the part of the picture actually
// on screen, bounded, laid back exactly over the pixels it came from.
//
// **Nothing runs a model until it is asked to.** The same rule the bench holds,
// for the same reason: every change here is a press away from a model pass, and
// a viewer that refined on every wheel notch would put a checkpoint behind the
// act of looking at a picture. Moving anything marks what is on the glass as no
// longer what the rail says, and says so on the press.

import { el, icon, spinner, mountOverlay, drawFrame } from "./dom.js";
import { viewUrl, upscalePreviewUrl, probe, primeSettings, neuralOf,
         neuralTwin } from "./api.js";
import { api } from "../../../scripts/api.js";
import { NEURAL } from "./manifest.js";
import { NEURAL_RANGES, emptyNeural, neuralEstimateGb, parseNeural } from "./state.js";
import { neuralRail, savedProfiles, saveProfile, forgetProfile, sameProfile,
         applyProfile, profileOf, startingBlock, hasStartingBlock, setStartingBlock,
         MAX_NAME } from "./neural.js";
import { tileRect, tileShare, tileSide } from "./tile.js";
import { mountTrim } from "./trim.js";
import { t } from "./i18n.js";
import { busy as queueBusy, watch as watchQueue } from "./queue.js";

/** How far in the wheel may go. Past 8:1 a picture is a swatch of four pixels
 *  and the thing being judged is the browser's interpolation. */
const MAX_ZOOM = 8;

/** How much one wheel notch moves it. Multiplicative rather than additive, so a
 *  notch means the same amount of magnification at 1:1 as at 8:1. */
const ZOOM_STEP = 1.0015;

/** The loupe, or null. One at a time: it is a room, and two of them would each
 *  be holding the same file at a different zoom. */
let open = null;

/**
 * Open the loupe on one file.
 *
 * @param {object} options
 * @param {{path: string, kind: string}} options.source  what to look at
 * @param {boolean} [options.compare]  open with the seam and the rail up
 * @param {object} [options.neural]  the refiner block the rail edits. Passed by
 *   a surface that owns one — a piece, a timeline, a pre-stage — and mutated in
 *   place, so a dial moved while comparing is the dial that piece renders with.
 *   Absent means the loupe carries its own, starting from this machine's saved
 *   answer, and nothing is committed anywhere.
 * @param {() => void} [options.onNeural]  called after every change to that block
 * @param {string} [options.title]  what to call the file, if not its own name
 * @returns {Promise<void>}  resolves when it closes
 */
export function openLoupe(options = {}) {
  open?.close();
  return new Promise((resolve) => {
    open = new Loupe(options, resolve);
    open.mount();
  });
}

/** Whether the refiner can be run on this machine at all. The compare press
 *  still draws when it cannot — unlit, saying what is missing, the same rule
 *  the pill holds: the answer to "why is this greyed out" has to be on it. */
export const refinerReady = () => NEURAL.ready !== false;

class Loupe {
  constructor(options, resolve) {
    this.options = options;
    this.resolve = resolve;
    this.source = options.source;
    this.owned = Boolean(options.neural);
    // The piece's block, or one of our own. Either way it is on: a rail that
    // opened switched off would be a comparison against nothing.
    this.neural = options.neural ?? parseNeural({ ...emptyNeural(), ...startingBlock() });
    this.neural.on = true;
    // The source's own pixels, off the probe. Never off a thumbnail — that was
    // the bug this pack shipped in the bench, where every figure derived from a
    // picture's size described a 320-pixel copy of it.
    this.natural = null;
    this.compare = Boolean(options.compare);
    this.seam = 0.5;
    // Where the picture sits in the glass: the top-left corner in glass pixels
    // and how much it is magnified. One number and two offsets rather than a
    // rectangle, because every gesture here changes exactly one of them.
    this.zoom = 1;
    this.at = { x: 0, y: 0 };
    this.fitted = true;
    // What this file says about the refiner, once the server has read its own
    // prompt back out of it: `{ours, on, settings}`. Null until it answers, and
    // `ours: false` for a file that carries no prompt of ours — which is what
    // decides which of the two comparisons this room is offering.
    this.render = null;
    // The other version, once it has been rendered: `{path, kind, on}`.
    this.twin = null;
    this.twinBusy = false;
    // The queue item it is riding on, so the one `executed` in a hundred that
    // belongs to this room can be told from the rest.
    this.twinId = null;
    // The refined tile: the rectangle it covers in source pixels, and whether
    // it still answers to the rail as it stands.
    this.tile = null;
    this.stale = false;
    this.working = false;
    this.error = null;
    this.saving = false;
  }

  // ---- the room --------------------------------------------------------------

  mount() {
    this.shot = el("div", { class: "mmc-lp-shot" });
    this.glass = el("div", { class: "mmc-lp-glass" }, [this.shot]);
    this.glass.addEventListener("wheel", (event) => this.onWheel(event), { passive: false });
    this.glass.onpointerdown = (event) => this.onGrab(event);
    this.glass.ondblclick = (event) => this.onDoubleClick(event);
    this.glass.ondragstart = (event) => event.preventDefault();

    this.rail = el("div", { class: "mmc-lp-rail" });
    this.transport = el("div", { class: "mmc-lp-transport" });
    this.foot = el("div", { class: "mmc-lp-foot" });
    this.name = el("span", { class: "mmc-lp-name" });
    this.meta = el("span", { class: "mmc-lp-meta" });

    this.sheet = el("div", { class: "mmc-lp" }, [
      el("div", { class: "mmc-lp-bar" }, [
        this.name, this.meta,
        el("span", { class: "mmc-lp-gap" }),
        el("button", {
          class: "mmc-close", text: "✕", title: t("Close"),
          onclick: () => this.close(),
        }),
      ]),
      el("div", { class: "mmc-lp-room" }, [
        el("div", { class: "mmc-lp-work" }, [this.glass, this.transport, this.foot]),
        this.rail,
      ]),
    ]);
    this.overlay = el("div", { class: "mmc-overlay mmc-lp-over" }, [this.sheet]);
    this.unmount = mountOverlay(this.overlay, () => this.close());

    // The keys a viewer has: the zoom's three, and the seam's one. Escape is
    // the overlay's own and is not repeated here.
    this.onKey = (event) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const keys = {
        "+": () => this.zoomBy(1.25), "=": () => this.zoomBy(1.25),
        "-": () => this.zoomBy(0.8), "0": () => this.toFit(),
        1: () => this.toActual(), c: () => this.toggleCompare(),
      };
      const act = keys[event.key];
      if (!act) return;
      event.preventDefault();
      act();
    };
    document.addEventListener("keydown", this.onKey);

    // A refined tile is a model pass and the server refuses one while a render
    // has the GPU, so the press says so rather than failing at the end of a
    // wait. See `jobs.refuse_if_busy` and the bench's held slate.
    // The two messages that end a twin render. Listened for on the wire rather
    // than polled out of the history: it is the same signal the stage opens on,
    // and the prompt id is what tells this room's queue item from every other.
    this.wire = (event) => this.onWire(event);
    for (const name of ["executed", "execution_error", "execution_interrupted"]) {
      api.addEventListener(name, this.wire);
    }

    let wasBusy = queueBusy();
    this.unwatchQueue = watchQueue(() => {
      // Only when the answer changed. `status` fires on every step of every
      // render, and the rail holds sliders somebody may have their hand on — a
      // repaint per step would rebuild the dial under the pointer. The bench
      // guards its own foot the same way and for the same reason.
      const nowBusy = queueBusy();
      if (nowBusy === wasBusy) return;
      wasBusy = nowBusy;
      if (this.overlay.isConnected) this.paintRail();
    });

    this.watcher = new ResizeObserver(() => {
      if (this.fitted) this.toFit();
      else this.paintView();
    });
    this.watcher.observe(this.glass);

    // The saved setups live in the settings, which a node body primes when it
    // mounts. A loupe opened before one has is not a case that happens today,
    // and it is one line to make it not a case at all.
    primeSettings(() => { if (this.overlay.isConnected && this.compare) this.paintRail(); });

    this.paintShot();
    this.paintBar();
    this.paintFoot();
    this.paintRail();
    this.load();
  }

  async load() {
    const { width, height } = await probe(this.source.path);
    if (!this.overlay.isConnected) return;
    if (width && height) {
      this.natural = { width, height };
      this.toFit();
      this.paintBar();
    }
    // What made this file, if it says. Asked on opening rather than on the
    // compare press: it decides what the press is *called*, and a button whose
    // words arrive a moment after it does is a button nobody trusts.
    this.render = await neuralOf(this.source.path);
    if (!this.overlay.isConnected) return;
    // A piece's own block is what the pill handed over; where this room brought
    // its own and the file says what it was rendered with, that is the better
    // starting point — it is what these dials were, on this picture.
    if (!this.owned && this.render?.settings) {
      applyProfile(this.neural, parseNeural(this.render.settings));
    }
    this.paintBar();
    this.paintFoot();
    this.paintRail();
  }

  close() {
    if (open === this) open = null;
    document.removeEventListener("keydown", this.onKey);
    for (const name of ["executed", "execution_error", "execution_interrupted"]) {
      api.removeEventListener(name, this.wire);
    }
    this.twinMedia?.removeAttribute("src");
    this.watcher?.disconnect();
    this.unwatchQueue?.();
    this.cutter?.destroy();
    this.unmount?.();
    this.resolve?.();
  }

  // ---- the picture -------------------------------------------------------------

  /**
   * What is under the zoom: a picture, or a canvas the clip is painted into.
   *
   * A canvas rather than a `<video>` for the reason `trim.js` gives — a video
   * element is composited by the browser rather than painted into the page, and
   * on Linux that path hands back a black rectangle often enough that this pack
   * draws every clip through `drawImage` instead. It also means the clip's
   * frame and the refined tile over it are one picture at one zoom, rather than
   * a video the browser scales by its own rules and an image on top of it.
   */
  paintShot() {
    const clip = this.source.kind === "video";
    this.picture = clip
      ? el("canvas", { class: "mmc-lp-pic", draggable: "false" })
      : el("img", {
          class: "mmc-lp-pic", src: viewUrl(this.source.path), alt: "", draggable: "false",
          // The size the probe answers is the size this is drawn at, so a
          // picture that lands before the probe does still lands right.
          onload: (event) => {
            if (this.natural) return;
            this.natural = { width: event.target.naturalWidth, height: event.target.naturalHeight };
            this.toFit();
            this.paintBar();
          },
        });
    this.overLayer = el("img", {
      class: "mmc-lp-tile", alt: "", draggable: "false",
      style: { visibility: "hidden" },
    });
    this.seamEl = el("div", { class: "mmc-lp-seam" }, [
      el("span", { class: "mmc-lp-grip" }, [icon("swap", 14)]),
    ]);
    this.tagLeft = el("span", { class: "mmc-lp-tag left" });
    this.tagRight = el("span", { class: "mmc-lp-tag right" });
    this.tileBox = el("div", { class: "mmc-lp-tilebox", hidden: true }, [
      this.overLayer, this.seamEl, this.tagLeft, this.tagRight,
    ]);
    this.paintTags();
    this.shot.replaceChildren(this.picture, this.tileBox);

    if (clip) this.mountTransport();
  }

  /** The clip's transport: the trim editor's bar, with its picture switched off
   *  because the glass above is already showing the frame. The same bar the
   *  upscale bench stands on, so scrubbing is one thing to learn — and its
   *  playhead is which frame a comparison is of. */
  mountTransport() {
    this.cutter = mountTrim({
      path: this.source.path, kind: "video", trim: null, showTrack: false,
      picture: false,
      onFrame: (media) => this.onFrame(media),
      onChange: () => { this.markStale(); this.syncTwin(); this.paintRail(); },
    });
    this.transport.replaceChildren(this.cutter.root);
  }

  onFrame(media) {
    if (!this.picture || this.picture.tagName !== "CANVAS") return;
    // At the clip's own height, not `drawFrame`'s 720 default. That cap is for
    // the thumbnails and locators every other surface draws with this; here the
    // canvas *is* the picture and the room exists to be zoomed into it, so a
    // frame quietly resampled to 720 would be the one lie this whole room is
    // built to catch.
    drawFrame(this.picture, media, media.videoHeight || 720);
    if (!this.natural && media.videoWidth) {
      this.natural = { width: media.videoWidth, height: media.videoHeight };
      this.toFit();
      this.paintBar();
    }
  }

  // ---- the zoom ----------------------------------------------------------------

  /** How much of the picture the glass can hold, at most 1:1. A still smaller
   *  than the room is shown at its own size rather than blown up to fill it: a
   *  magnified picture is a claim about detail nothing here can back up, and a
   *  viewer that opens already lying about sharpness is worse than a small one. */
  fitZoom() {
    const room = this.glass.getBoundingClientRect();
    if (!this.natural || !room.width || !room.height) return 1;
    return Math.min(1, room.width / this.natural.width, room.height / this.natural.height);
  }

  toFit() {
    this.zoom = this.fitZoom();
    this.fitted = true;
    this.centreView();
    this.paintView();
    this.paintFoot();
  }

  toActual() {
    this.zoomTo(1, null);
  }

  zoomBy(factor) {
    this.zoomTo(this.zoom * factor, null);
  }

  /**
   * Magnify about a point of the glass, or about its centre.
   *
   * The point under the pointer stays under the pointer — which is the whole of
   * what makes a wheel zoom feel like moving a lens rather than resizing a
   * picture. In picture coordinates: the point is `(glass - at) / zoom` before
   * and must be the same after, which is the line below.
   */
  zoomTo(wanted, anchor) {
    if (!this.natural) return;
    const room = this.glass.getBoundingClientRect();
    const low = this.fitZoom();
    const next = Math.max(low, Math.min(MAX_ZOOM, wanted));
    const point = anchor ?? { x: room.width / 2, y: room.height / 2 };
    const before = { x: (point.x - this.at.x) / this.zoom, y: (point.y - this.at.y) / this.zoom };
    this.zoom = next;
    this.at = { x: point.x - before.x * next, y: point.y - before.y * next };
    this.fitted = Math.abs(next - low) < 0.0005;
    this.clampView();
    this.paintView();
    this.paintFoot();
    this.markStale();
  }

  /** The picture centred in the glass, for the zoom where it fits inside it. */
  centreView() {
    const room = this.glass.getBoundingClientRect();
    if (!this.natural) return;
    this.at = {
      x: (room.width - this.natural.width * this.zoom) / 2,
      y: (room.height - this.natural.height * this.zoom) / 2,
    };
  }

  /** No dragging the picture off the glass. An axis it is smaller than stays
   *  centred on; an axis it overflows may be moved as far as its own edges. */
  clampView() {
    const room = this.glass.getBoundingClientRect();
    if (!this.natural || !room.width) return;
    const shown = { width: this.natural.width * this.zoom, height: this.natural.height * this.zoom };
    const hold = (offset, size, room_) => (size <= room_
      ? (room_ - size) / 2
      : Math.max(room_ - size, Math.min(0, offset)));
    this.at = {
      x: hold(this.at.x, shown.width, room.width),
      y: hold(this.at.y, shown.height, room.height),
    };
  }

  paintView() {
    if (!this.natural) return;
    this.clampView();
    this.shot.style.width = `${this.natural.width}px`;
    this.shot.style.height = `${this.natural.height}px`;
    this.shot.style.transform =
      `translate(${this.at.x.toFixed(2)}px, ${this.at.y.toFixed(2)}px) scale(${this.zoom})`;
    // Crisp above 1:1. A picture magnified past its own pixels is being looked
    // at *for* its pixels, and the browser's smoothing is the one thing that
    // makes them impossible to see.
    this.shot.classList.toggle("pixels", this.zoom > 1.5);
  }

  onWheel(event) {
    if (!this.natural) return;
    event.preventDefault();
    const room = this.glass.getBoundingClientRect();
    this.zoomTo(this.zoom * ZOOM_STEP ** -event.deltaY,
                { x: event.clientX - room.left, y: event.clientY - room.top });
  }

  /**
   * A press on the glass: the seam if it is on the seam, the picture otherwise.
   *
   * The seam wins inside the compared square, because that is the control being
   * aimed there; anywhere else on the glass a drag is a pan. Two gestures on one
   * surface, told apart by where the press lands rather than by a mode.
   */
  onGrab(event) {
    if (this.compare && this.tile && this.overSeam(event)) {
      this.dragSeam(event);
      return;
    }
    this.dragView(event);
  }

  /** Whether a press landed inside the compared square. */
  overSeam(event) {
    const box = this.tileBox.getBoundingClientRect();
    return box.width > 0 && event.clientX >= box.left && event.clientX <= box.right
      && event.clientY >= box.top && event.clientY <= box.bottom;
  }

  dragView(event) {
    event.preventDefault();
    const start = { x: event.clientX, y: event.clientY };
    const from = { ...this.at };
    const move = (at) => {
      this.at = { x: from.x + (at.clientX - start.x), y: from.y + (at.clientY - start.y) };
      this.fitted = false;
      this.paintView();
    };
    this.grip(event, move, () => { this.markStale(); this.paintFoot(); });
  }

  dragSeam(event) {
    event.preventDefault();
    const move = (at) => {
      const box = this.tileBox.getBoundingClientRect();
      if (!box.width) return;
      this.seam = Math.max(0, Math.min(1, (at.clientX - box.left) / box.width));
      this.paintSeam();
    };
    move(event);
    this.grip(event, move);
  }

  /** One pointer capture, two draggers. */
  grip(event, move, done = null) {
    this.glass.setPointerCapture(event.pointerId);
    const up = () => {
      this.glass.removeEventListener("pointermove", move);
      this.glass.removeEventListener("pointerup", up);
      this.glass.removeEventListener("pointercancel", up);
      done?.();
    };
    this.glass.addEventListener("pointermove", move);
    this.glass.addEventListener("pointerup", up);
    this.glass.addEventListener("pointercancel", up);
  }

  /** Fitting the window and 1:1 are the two zooms anybody actually asks for,
   *  and a double-click is how every viewer ever written moves between them. */
  onDoubleClick(event) {
    const room = this.glass.getBoundingClientRect();
    const anchor = { x: event.clientX - room.left, y: event.clientY - room.top };
    if (this.fitted) this.zoomTo(1, anchor);
    else this.toFit();
  }

  // ---- the comparison ----------------------------------------------------------

  toggleCompare() {
    this.compare = !this.compare;
    this.paintRail();
    this.paintFoot();
    this.paintTile();
  }

  /** Which square of the source is being compared, and how much of it.
   *
   *  The part of the picture on the glass, bounded by what the refiner is worth
   *  running on: below the floor there is nothing to judge, above the ceiling
   *  one press is a render. Standing back from a 4K frame therefore compares a
   *  1024-pixel square of it rather than the frame — which is honest, and is
   *  why the square is drawn rather than assumed. */
  region() {
    const room = this.glass.getBoundingClientRect();
    if (!this.natural || !room.width) return null;
    const visible = {
      width: Math.min(this.natural.width, room.width / this.zoom),
      height: Math.min(this.natural.height, room.height / this.zoom),
    };
    const left = Math.max(0, Math.min(this.natural.width - visible.width, -this.at.x / this.zoom));
    const top = Math.max(0, Math.min(this.natural.height - visible.height, -this.at.y / this.zoom));
    const side = tileSide(this.natural, Math.min(visible.width, visible.height));
    return {
      side,
      centre: [(left + visible.width / 2) / this.natural.width,
               (top + visible.height / 2) / this.natural.height],
    };
  }

  /**
   * Which comparison this file gets.
   *
   * "twin" for a render of this pack's: the other version of it, whole. "tile"
   * for everything else: the refiner run on a square, because there is no other
   * version to ask for. Null until the server has answered what the file is —
   * the press draws unlit rather than guessing and changing its mind.
   */
  mode() {
    if (!this.render) return null;
    return this.render.ours ? "twin" : "tile";
  }

  /**
   * Render this piece again with the refiner the other way round.
   *
   * The press that answers the actual question. It goes on ComfyUI's own
   * queue as the user's own prompt with one boolean moved, so Cancel reaches
   * it, the progress bar is the real one, and — because the node's subcache
   * survives a change to its blob — what runs is the pass and the save rather
   * than the render. See `creator/neuraltwin.py`.
   */
  async renderTwin() {
    if (this.twinBusy || !this.render?.ours) return;
    const wanted = !this.render.on;
    this.twinBusy = true;
    this.error = null;
    this.paintRail();
    try {
      // The dials only go with it where the twin is the one being refined.
      // Taking the pass *out* has no settings, and sending some would suggest
      // the picture on the left could have been made differently.
      this.twinId = await neuralTwin(this.source.path, wanted,
                                     wanted ? profileOf(this.neural) : null);
    } catch (error) {
      this.twinId = null;
      this.twinBusy = false;
      this.error = String(error?.message ?? error);
      this.paintRail();
    }
  }

  /** The wire, while a twin is in flight. One handler for the two messages
   *  that end one: the file it wrote, or the failure that stopped it. */
  onWire(event) {
    const detail = event.detail ?? {};
    if (!this.twinId || detail.prompt_id !== this.twinId) return;
    if (event.type === "execution_error" || event.type === "execution_interrupted") {
      this.twinBusy = false;
      this.twinId = null;
      this.error = event.type === "execution_interrupted"
        ? t("That render was cancelled.")
        : t("That render stopped: {what}", { what: detail.exception_message || detail.node_type || "" });
      this.paintRail();
      return;
    }
    const saved = detail.output?.mmc_video?.[0] ?? detail.output?.mmc_image?.[0];
    if (!saved?.filename) return;
    const folder = saved.subfolder ? `${saved.subfolder}/` : "";
    this.twinBusy = false;
    this.twinId = null;
    this.twin = {
      path: `${folder}${saved.filename} [${saved.type || "output"}]`,
      kind: detail.output?.mmc_video ? "video" : "image",
      on: !this.render.on,
    };
    this.showTwin();
    this.paintRail();
  }

  /**
   * The other version, over the picture, edge to edge.
   *
   * No tile here: the twin is the same render at the same size, so the wipe is
   * the whole frame and the square that bounds a model pass has no reason to
   * exist. A clip's twin is a second decoder parked on the same mark — one
   * frame each, which is what a wipe between two clips can honestly be.
   */
  showTwin() {
    if (!this.twin) return;
    if (this.twin.kind === "video") {
      this.twinMedia = el("video", { src: viewUrl(this.twin.path), preload: "auto",
                                     playsinline: true, muted: true });
      this.twinMedia.addEventListener("seeked", () => this.drawTwinFrame());
      this.twinMedia.addEventListener("loadeddata", () => this.syncTwin());
      this.twinCanvas = el("canvas", { class: "mmc-lp-tile" });
      this.overLayer.replaceWith(this.twinCanvas);
      this.overLayer = this.twinCanvas;
      this.syncTwin();
    } else {
      this.overLayer.src = viewUrl(this.twin.path);
      this.overLayer.style.visibility = "";
    }
    this.stale = false;
    this.paintTags();
    this.paintTile();
  }

  /** Park the twin's decoder on the mark the transport is showing. */
  syncTwin() {
    if (!this.twinMedia) return;
    const at = this.cutter?.at() ?? 0;
    if (Math.abs(this.twinMedia.currentTime - at) < 0.001) this.drawTwinFrame();
    else this.twinMedia.currentTime = at;
  }

  drawTwinFrame() {
    if (this.twinMedia?.videoWidth) {
      drawFrame(this.twinCanvas, this.twinMedia, this.twinMedia.videoHeight);
    }
  }

  /** Put the refiner on the square in front of you. */
  async refine() {
    const region = this.region();
    if (!region || this.working) return;
    this.working = true;
    this.error = null;
    this.paintRail();
    const values = {
      profile: this.neural.profile, processing: this.neural.scale,
      detail: this.neural.detail, colour: this.neural.colour,
      intensity: this.neural.intensity, precision: this.neural.precision,
    };
    const url = upscalePreviewUrl(this.source.path, "neural", values, {
      at: this.cutter?.at() ?? 0, centre: region.centre, side: region.side,
    });
    try {
      // Loaded detached and swapped in once it has decoded, the way the bench
      // does it: setting `src` on the visible layer blanks it for the length of
      // a model pass, and the half being compared against is exactly what has
      // to stay up while the other one is made.
      await new Promise((done, fail) => {
        const next = new Image();
        next.onload = () => {
          this.overLayer.src = next.src;
          this.overLayer.style.visibility = "";
          done();
        };
        next.onerror = () => fail(new Error("no tile"));
        next.src = url;
      });
      this.tile = { ...region, rect: tileRect(this.natural, region.centre, region.side) };
      this.stale = false;
      this.paintTile();
    } catch {
      this.error = t("That square could not be refined.");
    } finally {
      this.working = false;
      this.paintRail();
    }
  }

  /** The tile back over the pixels it is a picture of. In the picture's own
   *  coordinate space rather than the glass's, so panning and zooming carry it
   *  along without a single number being recomputed. */
  paintTile() {
    const show = this.compare && this.natural && (this.tile || this.twin);
    this.tileBox.hidden = !show;
    if (!show) return;
    // The twin is the whole picture; a refined tile is the square it was cut
    // from. One box either way, so the seam, the grip and the two tags are the
    // same control in both comparisons.
    const share = this.twin
      ? { left: 0, top: 0, width: 1, height: 1 }
      : tileShare(this.natural, this.tile.centre, this.tile.side);
    Object.assign(this.tileBox.style, {
      left: `${share.left * 100}%`, top: `${share.top * 100}%`,
      width: `${share.width * 100}%`, height: `${share.height * 100}%`,
    });
    this.tileBox.classList.toggle("stale", this.stale && !this.twin);
    this.paintSeam();
  }

  /** What each half is, said at its foot. Which way round depends on what is
   *  being compared: against a twin the file you opened is on the left and the
   *  version you asked for is on the right, and either of those may be the one
   *  with the refiner in it. */
  paintTags() {
    const on = t("Refiner on");
    const off = t("Refiner off");
    if (this.twin) {
      this.tagLeft.textContent = this.render?.on ? on : off;
      this.tagRight.textContent = this.twin.on ? on : off;
    } else {
      this.tagLeft.textContent = t("As it is");
      this.tagRight.textContent = t("Refined here");
    }
  }

  paintSeam() {
    this.tileBox.style.setProperty("--mmc-seam", `${(this.seam * 100).toFixed(2)}%`);
  }

  /** What is on the glass is still a true picture of the settings it was made
   *  with — so it stays, and the press that would redo it is what says the
   *  settings have moved since. The bench's rule, and the same words. */
  markStale() {
    if (!this.tile || this.stale) return;
    this.stale = true;
    this.paintTile();
    this.paintRail();
  }

  // ---- the chrome --------------------------------------------------------------

  paintBar() {
    const name = this.options.title
      ?? String(this.source.path).replace(/ \[[a-z]+\]$/, "").split("/").pop();
    this.name.textContent = name;
    this.meta.textContent = this.natural
      ? `${this.natural.width} × ${this.natural.height}`
      : "";
  }

  paintFoot() {
    const percent = this.natural ? Math.round(this.zoom * 100) : 100;
    this.foot.replaceChildren(...[
      el("button", {
        class: "mmc-lp-step", title: t("Zoom out"), "aria-label": t("Zoom out"),
        onclick: () => this.zoomBy(0.8),
      }, [icon("zoomOut", 15)]),
      el("span", { class: "mmc-lp-zoom", text: `${percent}%` }),
      el("button", {
        class: "mmc-lp-step", title: t("Zoom in"), "aria-label": t("Zoom in"),
        onclick: () => this.zoomBy(1.25),
      }, [icon("zoomIn", 15)]),
      el("button", {
        class: `mmc-lp-jump${this.fitted ? " on" : ""}`, text: t("Fit"),
        title: t("The whole picture in the window."),
        onclick: () => this.toFit(),
      }),
      el("button", {
        class: `mmc-lp-jump${Math.abs(this.zoom - 1) < 0.0005 ? " on" : ""}`, text: "1:1",
        title: t("One screen pixel per picture pixel."),
        onclick: () => this.toActual(),
      }),
      el("span", { class: "mmc-lp-gap" }),
      el("button", {
        class: `mmc-lp-compare${this.compare ? " on" : ""}`,
        "aria-pressed": this.compare,
        title: refinerReady()
          ? t("Hold this picture against the DLSS 5 refiner's answer for it.")
          : t("The neural refiner is not set up on this machine. It needs {what}",
              { what: NEURAL.needs || t("the weights extracted from your own DLSS DLL") }),
        onclick: () => this.toggleCompare(),
      }, [icon("swap", 14), el("span", { text: t("Compare") })]),
    ]);
  }

  /**
   * The rail: what the right of the seam is, and what it is set to.
   *
   * Drawn only while comparing. A column of dials beside a picture nobody is
   * comparing is a settings page that has taken a third of the room from the
   * thing it is settings for.
   */
  paintRail() {
    this.rail.hidden = !this.compare;
    if (!this.compare) return;
    const rows = [el("div", { class: "mmc-lp-railtitle", text: t("Neural refiner (DLSS 5)") })];
    rows.push(...(this.mode() === "twin" ? this.twinRows() : this.tileRows()));
    if (this.error) rows.push(el("div", { class: "mmc-lp-bad", text: this.error }));
    this.rail.replaceChildren(...rows);
  }

  /**
   * The rail for a render of ours: the other version of it.
   *
   * There are no dials on it while the file already has the pass — what is
   * being asked for is the render *without*, which has no settings, and a
   * column of sliders over that press would suggest the picture on the left
   * could have come out differently. Where the file was rendered without one,
   * the dials are what the twin will be refined with and they are the whole
   * point of the rail.
   */
  twinRows() {
    const ready = refinerReady();
    const has = this.render.on;
    const rows = [el("p", { class: "mmc-lp-railnote", text: has
      ? t("This render was made with the refiner on. The other half of the seam is "
        + "the same render without it.")
      : t("This render was made without the refiner. The other half of the seam is "
        + "the same render with it.") })];
    if (has && this.render.settings) {
      const block = parseNeural(this.render.settings);
      rows.push(el("div", { class: "mmc-lp-was", text: t(
        "It ran {profile} · detail {detail} · colour {colour} · blend {blend} · {precision}.",
        { profile: t(block.profile), detail: block.detail.toFixed(2),
          colour: block.colour.toFixed(2), blend: block.intensity.toFixed(2),
          precision: t(block.precision) }) }));
    } else {
      if (!ready) {
        rows.push(el("div", { class: "mmc-lp-bad", text:
          t("Not set up on this machine: the settings page's 'Neural refiner' section says what is missing.") }));
      }
      rows.push(...neuralRail({
        block: this.neural, ranges: NEURAL_RANGES,
        still: this.source.kind !== "video",
        onChange: () => { this.options.onNeural?.(); },
        redraw: () => { this.paintRail(); },
      }));
      rows.push(this.profileShelf());
    }
    rows.push(el("div", { class: "mmc-lp-estimate", text: this.twin
      ? t("Both versions are on the shelf beside your other renders.")
      : t("This goes on the queue as the same render with one setting moved. "
        + "Everything before the refiner is already in ComfyUI's cache, so what "
        + "runs is the pass and the file — not the sampler.") }));
    const label = this.twinBusy ? t("Rendering the other version…")
      : this.twin ? t("Render it again")
      : has ? t("Render it without the refiner")
      : t("Render it with the refiner");
    rows.push(el("button", {
      class: "mmc-lp-run",
      disabled: (this.twinBusy || (!has && !ready)) || null,
      onclick: () => this.renderTwin(),
    }, [this.twinBusy ? spinner() : null, el("span", { text: label })].filter(Boolean)));
    return rows;
  }

  /**
   * The rail for everything else: what the refiner would do to a square of it.
   *
   * A photograph, a piece of footage, a render from another pack. There is no
   * other version of it to ask the queue for, and the question is the one the
   * dials answer — so this is where a setup is actually arrived at.
   */
  tileRows() {
    const ready = refinerReady();
    const held = queueBusy();
    const rows = [el("p", { class: "mmc-lp-railnote", text: this.owned
      ? t("These are this piece's own settings. What you change here is what it renders with.")
      : t("This file carries no render of ours to re-run, so the seam is the "
        + "refiner run here, on the square you are looking at.") })];
    if (!ready) {
      rows.push(el("div", { class: "mmc-lp-bad", text:
        t("Not set up on this machine: the settings page's 'Neural refiner' section says what is missing.") }));
    }
    rows.push(...neuralRail({
      block: this.neural, ranges: NEURAL_RANGES,
      still: this.source.kind !== "video",
      onChange: () => { this.options.onNeural?.(); this.markStale(); },
      redraw: () => { this.paintRail(); },
    }));
    rows.push(this.profileShelf());

    const region = this.region();
    const gigabytes = region && this.natural
      ? neuralEstimateGb(region.side, region.side, this.neural.scale, this.neural.precision)
      : null;
    rows.push(el("div", { class: "mmc-lp-estimate", text: [
      region ? t("A {side}-pixel square of the picture, refined where you are looking.",
                 { side: region.side }) : "",
      gigabytes != null ? t("About {gb} GB.", { gb: gigabytes.toFixed(1) }) : "",
    ].filter(Boolean).join(" ") }));

    const label = this.working ? t("Refining…")
      : held ? t("Waiting for the render")
      : this.tile && !this.stale ? t("This square is refined")
      : this.tile ? t("Refine it again")
      : t("Refine this square");
    rows.push(el("button", {
      class: "mmc-lp-run",
      disabled: (!ready || this.working || held || (this.tile && !this.stale)) || null,
      onclick: () => this.refine(),
    }, [this.working ? spinner() : null, el("span", { text: label })].filter(Boolean)));
    return rows;
  }

  /**
   * The shelf of saved setups.
   *
   * A chip per profile, the one matching the dials lit. Pressing one applies
   * it; the star under them keeps what is on the rail now, under a name, and
   * "start here" makes it what a piece's refiner begins at — which is the whole
   * point of saving one at all, since the dials are found on one picture and
   * wanted on every piece after it.
   */
  profileShelf() {
    const saved = savedProfiles();
    const current = saved.find((entry) => sameProfile(entry.block, this.neural));
    const chips = saved.map((entry) => el("button", {
      class: `mmc-lp-profile${entry === current ? " on" : ""}`,
      "aria-pressed": entry === current,
      title: t("Put these dials on the rail. Hold Alt and press to forget it."),
      onclick: (event) => {
        if (event.altKey) { forgetProfile(entry.name).then(() => this.paintRail()); return; }
        applyProfile(this.neural, entry.block);
        this.options.onNeural?.();
        this.markStale();
        this.paintRail();
      },
    }, [el("span", { text: entry.name })]));

    const field = this.saving
      ? el("input", {
          type: "text", class: "mmc-lp-namefield", maxlength: String(MAX_NAME),
          placeholder: t("Name this setup"), spellcheck: "false",
          onkeydown: (event) => {
            event.stopPropagation();
            if (event.key === "Enter") {
              saveProfile(event.target.value, this.neural).then(() => {
                this.saving = false;
                this.paintRail();
              });
            }
            if (event.key === "Escape") { this.saving = false; this.paintRail(); }
          },
          onblur: () => { this.saving = false; this.paintRail(); },
        })
      : el("button", {
          class: "mmc-lp-save", text: t("Save these"),
          title: t("Keep this setup on this machine, under a name."),
          onclick: () => { this.saving = true; this.paintRail(); this.rail
            .querySelector(".mmc-lp-namefield")?.focus(); },
        });

    return el("div", { class: "mmc-lp-shelf" }, [
      el("div", { class: "mmc-lp-shelftop" }, [
        el("span", { class: "mmc-nr-label", text: t("saved") }),
        el("button", {
          // Lit only where this machine has actually said so. Without the
          // first half it lights up on a fresh install the moment the dials
          // are at their defaults, which is a press claiming to have been made.
          class: `mmc-lp-start${hasStartingBlock() && sameProfile(startingBlock(), this.neural) ? " on" : ""}`,
          text: t("Start here"),
          title: t("What a piece's refiner begins at the first time it is switched on."),
          onclick: () => setStartingBlock(this.neural).then(() => this.paintRail()),
        }),
      ]),
      el("div", { class: "mmc-lp-profiles" }, [...chips, field]),
    ]);
  }
}
