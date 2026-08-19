// The segment editor for reference video and audio: an in/out range over the
// clip, plus the track switch for video — picture, picture and sound, or the
// soundtrack on its own.
//
// One component, two call sites — the picker opens it before a file is attached
// and the asset chip opens it afterwards — so the segment is chosen the same way
// wherever you are. Whole clip is always the default: this modal only ever opens
// because the user asked for it.

import { el, icon, drawFrame, mountOverlay } from "./dom.js";
import { viewUrl, probe } from "./api.js";
import { peaks, draw } from "./waveform.js";
import { t } from "./i18n.js";

const WAVE_COLOUR = "rgba(255,255,255,.34)";

// 6 frames at 24 fps. encode.py refuses a reference video under 5, and a handle
// that can be dragged into an empty selection is a trap rather than a control.
const MIN_SEGMENT = 0.25;

export function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return "–";
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return `${minutes}:${rest < 10 ? "0" : ""}${rest.toFixed(1)}`;
}

/** What the "whole / 0:02–0:07" buttons show.
 *
 *  "whole", not "full", and the difference matters on a video chip: the scope
 *  dial two pills along says "full" for a reference nobody has narrowed, so an
 *  untrimmed clip used to read `@vid-1 full sound on full max` — one word for
 *  the entire duration and the same word for the entire content. This is the
 *  duration one, and `isWhole` below is already what this module calls it. */
export function trimLabel(asset) {
  return asset.trim ? `${formatTime(asset.trim.start)}–${formatTime(asset.trim.end)}` : t("whole");
}

// The track switch, in the order it reads on screen. The labels say what comes
// out of the clip rather than what a switch is doing, because "sound only" is a
// different kind of reference and not a louder version of "sound on".
const TRACK_LABEL = {
  "picture+sound": "Picture + sound",
  "picture": "Picture only",
  "sound": "Sound only",
};
const TRACK_ORDER = ["picture+sound", "picture", "sound"];
const TRACK_TITLE = {
  "picture+sound": "Reference the picture, and bind this clip's own soundtrack alongside it. "
    + "Costs a video slot and an audio slot, and the soundtrack's <Audio> label comes "
    + "before the video's own <Video> label.",
  "picture": "Reference the picture silently. Costs a video slot only.",
  "sound": "Reference the soundtrack and nothing else — the picture is never encoded. "
    + "Costs an audio slot only, and the clip takes an <Audio> label in place of its <Video> one.",
};

/**
 * @param {object} options
 * @param {string} options.path        input-relative filename
 * @param {string} options.kind        video | audio — what the file is, not how it is used
 * @param {?{start:number,end:number}} options.trim   current segment, null for whole clip
 * @param {string} options.track       current track choice (video only), undefined if undecided
 * @param {boolean} options.showTrack  offer the track switch at all
 * @returns {Promise<?{trim:?{start:number,end:number}, track:string}>} null if cancelled
 */
export function openTrim(options) {
  return new Promise((resolve) => new Trim(options, resolve).mount());
}

const round = (value) => Math.round(value * 1000) / 1000;

class Trim {
  constructor(options, resolve) {
    this.options = options;
    this.resolve = resolve;
    this.duration = 0;
    this.start = options.trim?.start ?? 0;
    this.end = options.trim?.end ?? Infinity;   // resolved to the real end once metadata lands
    // undefined means "nobody has decided yet" — the default brings the sound
    // along, but only for a clip that has one, which the probe settles.
    this.track = options.track;
    this.hasAudio = null;
  }

  mount() {
    const isVideo = this.options.kind === "video";
    const source = viewUrl(this.options.path);
    // The decoder, never the picture: the element stays out of the document and
    // every frame is copied into `stage` instead. A <video> in the page is
    // composited by the browser rather than painted into it, and on Linux that
    // path routinely hands back a black rectangle — the same reason the LTX
    // Director timeline draws its filmstrip through a canvas. drawImage() reads
    // the decoded frame directly and cannot be composited away.
    this.media = document.createElement(isVideo ? "video" : "audio");
    // `metadata` is enough for a duration but not for a frame, and a frame is
    // the whole point of the picture.
    this.media.preload = isVideo ? "auto" : "metadata";
    this.media.playsInline = true;
    this.media.src = source;
    this.stage = isVideo ? el("canvas", { class: "mmc-trim-media" }) : null;
    if (isVideo) {
      this.media.addEventListener("loadeddata", () => this.drawFrame());
      this.media.addEventListener("seeked", () => this.drawFrame());
    }
    this.media.addEventListener("loadedmetadata", () => this.onMetadata());
    this.media.addEventListener("error", () => this.fail());
    this.media.addEventListener("timeupdate", () => this.onTime());
    this.media.addEventListener("play", () => this.onPlayState());
    this.media.addEventListener("pause", () => this.onPlayState());

    this.playButton = el("button", {
      class: "mmc-trim-play", title: t("Play the segment"), onclick: () => this.togglePlay(),
    }, [icon("play", 16)]);

    this.selection = this.buildSelection();
    this.playhead = el("div", { class: "mmc-trim-head" });
    this.startHandle = this.handle("start");
    this.endHandle = this.handle("end");
    this.wave = el("canvas", { class: "mmc-trim-wave" });
    // `trackEl` is the scrub bar; `track` is the picture/sound choice. Two very
    // different things that both want to be called "track" — the DOM one takes
    // the suffix.
    this.trackEl = el("div", {
      // An audio file has no picture to look at, so its waveform *is* the
      // preview and the track carries it at full height.
      class: `mmc-trim-track${isVideo ? "" : " mmc-trim-track-tall"}`,
      // Only reached for the bare track: the selection and the handles are
      // grabbable and stop the event where it lands.
      onpointerdown: (event) => this.seek(this.fraction(event) * this.duration),
    }, [this.wave, this.selection, this.playhead, this.startHandle, this.endHandle]);

    this.readout = el("div", { class: "mmc-trim-read" });
    this.fullButton = el("button", {
      class: "mmc-ghost", text: t("Whole clip"), title: t("Reset to the whole file"),
      onclick: () => { this.start = 0; this.end = this.duration; this.paint(); },
    });

    const foot = [this.fullButton];
    if (this.options.showTrack) {
      this.trackButtons = TRACK_ORDER.map((track) => el("button", {
        class: "mmc-seg-opt",
        text: t(TRACK_LABEL[track]),
        onclick: () => {
          if (this.hasAudio === false && track !== "picture") return;
          this.track = track;
          this.paint();
        },
      }));
      foot.push(el("div", {
        class: "mmc-seg", role: "group", "aria-label": t("What to reference from this clip"),
      }, this.trackButtons));
    }
    foot.push(
      el("span", { class: "mmc-trim-spacer" }),
      el("button", { class: "mmc-ghost", text: t("Cancel"), onclick: () => this.close(null) }),
      el("button", { class: "mmc-add", text: t("Use"), onclick: () => this.commit() }),
    );

    this.modal = el("div", { class: "mmc-trim" }, [
      el("div", { class: "mmc-trim-head-row" }, [
        el("span", { class: "mmc-trim-name", text: this.options.path.split("/").pop() }),
        el("button", { class: "mmc-close", text: "✕", onclick: () => this.close(null) }),
      ]),
      // Only the canvas is on screen. A detached media element still decodes and
      // still plays its sound, so nothing else needs a place in the document.
      this.stage,
      el("div", { class: "mmc-trim-bar" }, [this.playButton, this.trackEl]),
      this.readout,
      el("div", { class: "mmc-trim-foot" }, foot),
    ]);

    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(null); },
    }, [this.modal]);

    this.unmount = mountOverlay(this.overlay, () => this.close(null));
    this.paint();
    this.loadWave();
    this.loadHeader();
  }

  /** What the container header settles: the track switch — picture and sound by
   *  default, picture-only and locked there for a clip with no audio track — and
   *  the duration, when the browser could not read it for itself. */
  async loadHeader() {
    const { hasAudio, duration } = await probe(this.options.path);
    if (this.options.showTrack) {
      this.hasAudio = hasAudio !== false;
      if (!this.hasAudio) this.track = "picture";
      else if (this.track === undefined) this.track = "picture+sound";
    }
    // The media element is still what you scrub, but a browser with no decoder
    // for this container never fires loadedmetadata — Chromium built without
    // proprietary codecs is the common case. A segment dialled in by time alone
    // beats a modal that never comes up.
    if (!this.duration && duration) this.setDuration(duration);
    this.paint();
  }

  /** Decode the soundtrack in the background and paint it behind the range.
   *  Null — an undecodable container, a silent video, a file too big — leaves
   *  the plain track, which is what every other case draws on top of anyway. */
  async loadWave() {
    this.observer = new ResizeObserver(() => this.paintWave());
    this.observer.observe(this.trackEl);
    this.peaks = await peaks(this.options.path);
    if (this.overlay.isConnected) this.paintWave();
  }

  paintWave() {
    draw(this.wave, this.peaks, WAVE_COLOUR);
  }

  drawFrame() {
    drawFrame(this.stage, this.media);
  }

  /** Playback fires no `seeked`, so the stage runs off the display's clock for
   *  as long as the clip is running. */
  follow() {
    this.frameTimer = null;
    if (this.media.paused || !this.overlay.isConnected) return;
    this.drawFrame();
    this.frameTimer = requestAnimationFrame(() => this.follow());
  }

  onMetadata() {
    // The element wins over the header once it has an answer: it is what the
    // playhead and the seeks are actually addressing.
    this.setDuration(Number.isFinite(this.media.duration) ? this.media.duration : 0);
    this.status = null;
    this.paint();
  }

  /** Adopt a clip length and fit the current range inside it. */
  setDuration(seconds) {
    this.duration = seconds;
    this.end = Math.min(this.end, this.duration);
    this.start = Math.max(0, Math.min(this.start, Math.max(0, this.end - MIN_SEGMENT)));
    if (this.end <= this.start) { this.start = 0; this.end = this.duration; }
  }

  fail() {
    // The duration is left alone: the header probe may already have supplied it,
    // or may be about to, and the range is still editable without a picture.
    this.status = t("This browser cannot play this file — the segment can still be set by time.");
    this.paint();
  }

  // ---- range ---------------------------------------------------------------

  fraction(event) {
    const rect = this.trackEl.getBoundingClientRect();
    if (!rect.width) return 0;
    return Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
  }

  /**
   * Pointer-drag a child of the track. `begin(fraction)` runs on pointerdown and
   * returns the per-move step, so each grab can close over where it started —
   * which is what lets the selection move as a rigid window instead of being
   * recomputed from the pointer every frame.
   */
  drag(node, begin) {
    node.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      // The track underneath would otherwise treat the grab as a seek.
      event.stopPropagation();
      if (!this.duration) return;
      node.setPointerCapture(event.pointerId);
      const from = this.fraction(event);
      const step = begin(from);
      let moved = false;
      const move = (event2) => {
        const at = this.fraction(event2);
        if (Math.abs(at - from) * this.duration > 0.02) moved = true;
        step(at);
      };
      const up = (event2) => {
        node.removeEventListener("pointermove", move);
        node.removeEventListener("pointerup", up);
        node.removeEventListener("pointercancel", up);
        // A tap that never moved is still a seek, so clicking inside the
        // selection puts the playhead where you pointed rather than doing
        // nothing.
        if (!moved) this.seek(this.fraction(event2) * this.duration);
      };
      node.addEventListener("pointermove", move);
      node.addEventListener("pointerup", up);
      node.addEventListener("pointercancel", up);
    });
  }

  arrows(node, apply) {
    node.addEventListener("keydown", (event) => {
      const step = event.shiftKey ? 1 : 1 / 24;   // a second, or a frame
      if (event.key === "ArrowLeft") apply(-step);
      else if (event.key === "ArrowRight") apply(step);
      else return;
      event.preventDefault();
      event.stopPropagation();
    });
    return node;
  }

  handle(edge) {
    const node = el("div", {
      class: `mmc-trim-handle mmc-trim-${edge}`,
      role: "slider", tabindex: "0",
      title: edge === "start" ? t("Segment start") : t("Segment end"),
    });
    this.drag(node, () => (at) => this.setEdge(edge, at * this.duration));
    return this.arrows(node, (delta) => this.setEdge(edge, this[edge] + delta));
  }

  /** The selection itself, draggable as a whole so a segment of the right length
   *  can be slid along the clip without re-dialling both edges. */
  buildSelection() {
    const node = el("div", {
      class: "mmc-trim-sel", tabindex: "0", title: t("Drag to slide the segment"),
    });
    this.drag(node, (from) => {
      // Frozen at grab time: the length must not creep as the window is pushed
      // against either end of the clip.
      const origin = this.start;
      const length = this.end - this.start;
      return (at) => this.slide(origin + (at - from) * this.duration, length);
    });
    return this.arrows(node, (delta) => this.slide(this.start + delta, this.end - this.start));
  }

  slide(start, length) {
    if (!this.duration) return;
    this.start = Math.min(Math.max(0, start), Math.max(0, this.duration - length));
    this.end = this.start + length;
    this.seek(this.start, { pause: true });
    this.paint();
  }

  setEdge(edge, value) {
    if (this.duration <= MIN_SEGMENT) return;
    if (edge === "start") this.start = Math.min(Math.max(0, value), this.end - MIN_SEGMENT);
    else this.end = Math.max(Math.min(this.duration, value), this.start + MIN_SEGMENT);
    // Follow the handle being dragged, so the frame under it is visible.
    this.seek(edge === "start" ? this.start : Math.max(this.start, this.end - 1 / 24), { pause: true });
    this.paint();
  }

  // ---- playback ------------------------------------------------------------

  seek(time, { pause = false } = {}) {
    if (!this.duration) return;
    if (pause) this.media.pause();
    this.media.currentTime = Math.min(Math.max(0, time), this.duration);
    this.paint();
  }

  togglePlay() {
    if (!this.duration) return;
    if (this.media.paused) {
      if (this.media.currentTime < this.start || this.media.currentTime >= this.end - 0.02) {
        this.media.currentTime = this.start;
      }
      this.media.play().catch(() => {});
    } else {
      this.media.pause();
    }
  }

  onTime() {
    // The segment loops rather than running on into the part being cut away —
    // hearing the cut is how you know the out point is in the right place.
    if (this.duration && this.media.currentTime >= this.end - 0.02 && !this.media.paused) {
      this.media.pause();
      this.media.currentTime = this.start;
    }
    this.paint();
  }

  onPlayState() {
    this.playButton.replaceChildren(icon(this.media.paused ? "play" : "pause", 16));
    if (!this.media.paused && !this.frameTimer) this.follow();
  }

  // ---- render --------------------------------------------------------------

  paint() {
    const percent = (time) => (this.duration ? (time / this.duration) * 100 : 0);
    const end = this.duration ? Math.min(this.end, this.duration) : 0;
    this.selection.style.left = `${percent(this.start)}%`;
    this.selection.style.width = `${Math.max(0, percent(end) - percent(this.start))}%`;
    this.startHandle.style.left = `${percent(this.start)}%`;
    this.endHandle.style.left = `${percent(end)}%`;
    this.playhead.style.left = `${percent(this.media.currentTime || 0)}%`;

    const whole = this.isWhole();
    this.fullButton.disabled = whole || !this.duration || undefined;
    if (this.trackButtons) {
      const silent = this.hasAudio === false;
      // Until the probe lands nothing has been decided, but the default it will
      // land on is known — showing it beats showing three unpressed buttons.
      const shown = this.track ?? "picture+sound";
      this.trackButtons.forEach((button, index) => {
        const track = TRACK_ORDER[index];
        const unavailable = silent && track !== "picture";
        button.disabled = unavailable || undefined;
        button.setAttribute("aria-pressed", track === shown);
        button.title = unavailable ? t("This clip has no audio track.") : t(TRACK_TITLE[track]);
      });
    }
    if (!this.duration) {
      this.readout.textContent = this.status || t("Reading the clip…");
      return;
    }
    this.readout.replaceChildren(
      el("span", { text: whole ? t("Whole clip · {time}", { time: formatTime(this.duration) }) : `${formatTime(this.start)} – ${formatTime(end)}` }),
      el("span", { class: "mmc-trim-len", text: t("{length} s", { length: (end - this.start).toFixed(1) }) }),
      // A length that came from the header rather than the player: say so, or the
      // dead picture above looks like a bug rather than a missing codec.
      ...(this.status ? [el("span", { class: "mmc-trim-note", text: this.status })] : []),
    );
  }

  isWhole() {
    return !this.duration || (this.start <= 0.001 && this.end >= this.duration - 0.001);
  }

  commit() {
    // A range that covers everything is stored as no range at all, so a clip the
    // user opened and left alone stays "full" in creator_data.
    const result = { trim: this.isWhole() ? null : { start: round(this.start), end: round(this.end) } };
    if (this.options.showTrack) {
      // A clip with no soundtrack has nothing to offer either audio track, so
      // the answer is "picture" whatever the switch was showing.
      result.track = this.hasAudio === false ? "picture" : (this.track || "picture+sound");
    }
    this.close(result);
  }

  close(result) {
    this.observer?.disconnect();
    if (this.frameTimer) cancelAnimationFrame(this.frameTimer);
    this.media.pause();
    this.media.removeAttribute("src");
    this.unmount();
    this.resolve(result);
  }
}
