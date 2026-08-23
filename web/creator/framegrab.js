// Grab one frame of a video as an image file.
//
// The PreStage takes images — an init to restyle, a style reference — and the
// frame you want is routinely inside a clip: yesterday's render, location
// footage, the shot this one has to match. This is the trim editor's scrubbing
// (canvas + seeked + drawFrame, so the frame survives compositors that hand
// <video> back as a black box) with a different ending: instead of returning
// in/out points, "use this frame" paints the current frame at the clip's own
// resolution and uploads the PNG through core's /upload/image, which hands back
// an input-relative path that is immediately attachable. No server half at all.

import { el, icon, drawFrame, mountOverlay } from "./dom.js";
import { viewUrl, upload } from "./api.js";
import { t } from "./i18n.js";

/** Where grabbed frames land under input/ — a shelf of their own, so the picker
 *  does not mix them into the root. */
const SUBFOLDER = "prestage_frames";

/**
 * @param {object} spec
 * @param {string} spec.path  input-relative path of the video to scrub
 * @returns {Promise<{path: string}|null>}  the uploaded frame, or null on cancel
 */
export function openFrameGrab({ path }) {
  return new Promise((resolve) => new FrameGrab(path, resolve).mount());
}

class FrameGrab {
  constructor(path, resolve) {
    this.path = path;
    this.resolve = resolve;
    this.duration = 0;
    this.busy = false;
  }

  mount() {
    // Painted onto a canvas, never shown as the element — see dom.drawFrame.
    this.stage = el("canvas", { class: "mmc-grab-stage" });
    this.media = el("video", { src: viewUrl(this.path), preload: "auto", playsinline: true });
    this.media.muted = true;
    this.media.addEventListener("loadedmetadata", () => {
      this.duration = this.media.duration || 0;
      this.scrub.max = String(this.duration);
      this.renderTime();
    });
    // `seeked`, never a timeout: Firefox reports the old frame until it fires
    // (the still-capture caveat the trim editor already survives).
    this.media.addEventListener("loadeddata", () => this.draw());
    this.media.addEventListener("seeked", () => this.draw());

    this.time = el("span", { class: "mmc-grab-time", text: t("{seconds} s", { seconds: "0.00" }) });
    this.scrub = el("input", {
      class: "mmc-grab-scrub",
      type: "range", min: "0", max: "0", step: "0.001", value: "0",
      oninput: () => {
        this.media.currentTime = Number(this.scrub.value);
        this.renderTime();
      },
      onpointerdown: (event) => event.stopPropagation(),
    });

    const stepButton = (label, delta, title) => el("button", {
      class: "mmc-step", text: label, title,
      onclick: () => {
        const next = Math.min(this.duration, Math.max(0, (this.media.currentTime || 0) + delta));
        this.media.currentTime = next;
        this.scrub.value = String(next);
        this.renderTime();
      },
    });

    this.use = el("button", {
      class: "mmc-btn mmc-btn-primary",
      text: t("Use this frame"),
      title: t("Save the frame on the playhead as a PNG in the input folder, at the clip's own resolution."),
      onclick: () => this.commit(),
    });

    const card = el("div", { class: "mmc-grab-card", onpointerdown: (e) => e.stopPropagation() }, [
      el("div", { class: "mmc-grab-title" }, [icon("scissors", 16),
        el("span", { text: this.path.split("/").pop() })]),
      this.stage,
      el("div", { class: "mmc-grab-row" }, [
        stepButton("−1s", -1, t("Back one second")),
        // 1/24 s: the pipeline's own frame grid. The clip may not be 24 fps,
        // but a step the size of ours is the useful nudge either way.
        stepButton("−f", -1 / 24, t("Back one frame")),
        this.scrub,
        stepButton("+f", 1 / 24, t("Forward one frame")),
        stepButton("+1s", 1, t("Forward one second")),
        this.time,
      ]),
      el("div", { class: "mmc-grab-actions" }, [
        el("button", { class: "mmc-btn", text: t("Cancel"), onclick: () => this.close(null) }),
        this.use,
      ]),
    ]);
    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: () => this.close(null),
    }, [card]);
    this.unmount = mountOverlay(this.overlay, () => this.close(null));
  }

  draw() {
    // Full resolution, not the 720px preview default: this frame is about to
    // become a generation's input, and downscaling it here would be the one
    // lossy step nobody asked for.
    drawFrame(this.stage, this.media, this.media.videoHeight || 720);
  }

  renderTime() {
    this.time.textContent = t("{seconds} s", { seconds: (Number(this.scrub.value) || 0).toFixed(2) });
  }

  async commit() {
    if (this.busy || !this.media.videoWidth) return;
    this.busy = true;
    this.use.textContent = t("Saving…");
    this.use.disabled = true;
    try {
      this.draw();
      const blob = await new Promise((done) => this.stage.toBlob(done, "image/png"));
      if (!blob) throw new Error(t("could not read the frame"));
      const stem = this.path.split("/").pop().replace(/\.[^.]+$/, "");
      const name = `${stem}_t${(this.media.currentTime || 0).toFixed(2)}s.png`;
      const saved = await upload(new File([blob], name, { type: "image/png" }), SUBFOLDER);
      this.close({ path: saved.path });
    } catch (error) {
      this.use.textContent = t("failed — {error}", { error: String(error.message || error) });
      this.use.disabled = false;
      this.busy = false;
    }
  }

  close(result) {
    this.media.pause?.();
    this.media.removeAttribute("src");
    this.unmount();
    this.resolve(result);
  }
}
