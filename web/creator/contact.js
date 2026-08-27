// A strip of footage as one picture, and back again.
//
// An edit model reads a picture, so the way to ask one about a *shot* is to
// hand it the shot as a picture: nine frames laid out as a contact sheet, one
// instruction over all of them, and the model holds the subject across the
// tiles because as far as it is concerned they are one image. That is not a
// trick this pack invented — it is the observation Qwen-Video-Edit is built on,
// and the half of it that needs no training, no projections and no second VAE
// is exactly this: a grid of frames, edited, cut back up.
//
// So there are two halves here and they are inverses. **Lay** takes a clip and
// N marks along it and draws one sheet; **split** takes a sheet and hands back
// N frames. In between is an ordinary pre-stage render on Qwen Image Edit, with
// the sheet as the picture being changed.
//
// No server half, for the reason `framegrab.js` has none: a browser already
// decodes video and already draws to a canvas, and every frame this touches is
// on its way to `/upload/image` anyway. The seek/`seeked` dance is the trim
// editor's, done N times in a row instead of once.
//
// **The grid is gutterless on purpose.** A seam is one more thing for the model
// to reproduce, and a bare grid makes the split exact arithmetic rather than a
// measurement — `x = round(i * width / cols)` on the way out is the same line
// as on the way in.

import { el, icon, mountOverlay } from "./dom.js";
import { viewUrl, upload } from "./api.js";
import { t } from "./i18n.js";

/** Where sheets and the frames cut out of them land under input/ — the shelf
 *  grabbed frames already use, because they are the same kind of thing: a
 *  picture derived from footage, on its way into a render. */
const SUBFOLDER = "prestage_frames";

/** The grids offered, as [rows, cols]. Nine is the shape the empirical result
 *  was shown on; the others are for a shorter strip or a wider one. Past 4×4
 *  a tile is smaller than the thumbnail the encoder makes of it, which is not
 *  a sheet any more, it is a mosaic. */
const GRIDS = [[2, 2], [3, 2], [2, 3], [3, 3], [4, 3], [4, 4]];
const DEFAULT_GRID = 3;   // 3×3, the index into GRIDS above

/** The sheet's ceiling, per axis and in area — the pre-stage's own canvas
 *  envelope (`compile_image.MAX_SHORT_EDGE`, `MAX_PIXELS`), because the sheet
 *  is about to be one. Under it the tiles are as large as the grid allows. */
const MAX_EDGE = 2048;
const MAX_PIXELS = 2048 * 2048;

/** `-3x3` written into a sheet's name on the way out, read back on the way in
 *  so the splitter opens on the grid the sheet was laid on. */
const GRID_IN_NAME = /-(\d+)x(\d+)(?:-\d+)?\.[^.]+$/;

/**
 * Open the contact-sheet tool over `path`.
 *
 * Which half it is is decided by what it was handed, not by a mode switch: a
 * clip has frames to lay out and a picture has tiles to cut up, and there is
 * no third thing either of them could have meant.
 *
 * @param {object} spec
 * @param {string} spec.path   input-relative path of the clip or the sheet
 * @param {boolean} spec.video whether that path is a clip
 * @returns {Promise<{paths: string[]}|null>} what was written, or null on cancel
 */
export function openContactSheet({ path, video }) {
  return new Promise((resolve) =>
    (video ? new SheetLay(path, resolve) : new SheetSplit(path, resolve)).mount());
}

/** The grid pills, shared by both halves: one row, one lit. */
function gridRow(index, onPick) {
  return el("div", { class: "mmc-contact-grid" }, GRIDS.map(([rows, cols], i) => el("button", {
    class: `mmc-contact-cell${i === index ? " on" : ""}`,
    title: t("{count} frames, {cols} across", { count: rows * cols, cols }),
    onclick: () => onPick(i),
  }, [el("span", { text: `${cols}×${rows}` })])));
}

/** The sheet's pixel size for a tile of this shape, under the ceiling above.
 *  Whole tiles, so `cols * tile.width` is the sheet's width exactly — which is
 *  what makes the split reversible. */
export function sheetSize(tileAspect, rows, cols) {
  const aspect = tileAspect > 0 ? tileAspect : 1;
  // Floored at every step, never rounded: `cols * tileWidth` *is* the sheet's
  // width, so a tile rounded up by half a pixel is a sheet over the ceiling.
  let tileHeight = Math.floor(Math.min(MAX_EDGE / rows, MAX_EDGE / cols / aspect));
  let tileWidth = Math.floor(tileHeight * aspect);
  // The per-axis cap is the binding one on most grids; the area cap only bites
  // on a square-ish sheet, and this walks down to it a row of pixels at a time
  // rather than guessing a scale that would have to be floored again anyway.
  while (tileHeight > 2 && rows * tileHeight * cols * tileWidth > MAX_PIXELS) {
    tileHeight -= 1;
    tileWidth = Math.floor(tileHeight * aspect);
  }
  tileHeight = Math.max(2, tileHeight);
  tileWidth = Math.max(2, tileWidth);
  return { tileWidth, tileHeight, width: tileWidth * cols, height: tileHeight * rows };
}

/** Where tile `index` sits in a picture of this size.
 *
 *  Both edges are rounded off the *true* boundary rather than off a tile size,
 *  so consecutive tiles always meet and the last one always ends at the edge:
 *  the render an edited sheet comes back from snapped its canvas to a /16 grid,
 *  which need not divide by three, and a fixed tile size would leave a sliver
 *  of the ninth frame uncut. */
export function tileRect(width, height, rows, cols, index) {
  const col = index % cols;
  const row = Math.floor(index / cols);
  const x = Math.round((col * width) / cols);
  const y = Math.round((row * height) / rows);
  return {
    x, y,
    width: Math.round(((col + 1) * width) / cols) - x,
    height: Math.round(((row + 1) * height) / rows) - y,
  };
}

/** The card both halves are drawn in: title, canvas, a row of controls, and
 *  the two buttons. Kept here so the two are the same object with a different
 *  middle, rather than two overlays that drifted. */
class SheetCard {
  constructor(path, resolve, { glyph, title, action }) {
    this.path = path;
    this.resolve = resolve;
    this.glyph = glyph;
    this.title = title;
    this.actionLabel = action;
    this.grid = DEFAULT_GRID;
    this.busy = false;
  }

  get rows() { return GRIDS[this.grid][0]; }
  get cols() { return GRIDS[this.grid][1]; }

  /** The stem a written file is named off: the source's, trimmed to leave room
   *  for the grid and the counter inside a file name. */
  stem() {
    return this.path.split("/").pop().replace(/\.[^.]+$/, "").slice(0, 90);
  }

  mount() {
    this.stage = el("canvas", { class: "mmc-grab-stage mmc-contact-stage" });
    this.note = el("div", { class: "mmc-contact-note" });
    this.gridHost = el("div");
    this.act = el("button", {
      class: "mmc-btn mmc-btn-primary", text: t(this.actionLabel),
      onclick: () => this.commit(),
    });

    const card = el("div", { class: "mmc-grab-card", onpointerdown: (e) => e.stopPropagation() }, [
      el("div", { class: "mmc-grab-title" }, [icon(this.glyph, 16),
        el("span", { text: t(this.title) }),
        el("span", { class: "mmc-pill-sub", text: this.path.split("/").pop() })]),
      this.stage,
      this.gridHost,
      ...this.middle(),
      this.note,
      el("div", { class: "mmc-grab-actions" }, [
        el("button", { class: "mmc-btn", text: t("Cancel"), onclick: () => this.close(null) }),
        this.act,
      ]),
    ]);
    this.overlay = el("div", { class: "mmc-overlay", onpointerdown: () => this.close(null) }, [card]);
    this.unmount = mountOverlay(this.overlay, () => this.close(null));
    this.renderGrid();
    this.begin();
  }

  /** Whatever sits between the grid pills and the note. Nothing, by default. */
  middle() { return []; }

  renderGrid() {
    this.gridHost.replaceChildren(gridRow(this.grid, (index) => {
      this.grid = index;
      this.renderGrid();
      this.redraw();
    }));
  }

  say(message) { this.note.textContent = message; }

  fail(error) {
    this.act.textContent = t("failed — {error}", { error: String(error?.message || error) });
    this.act.disabled = false;
    this.busy = false;
  }

  /** Upload one canvas as a PNG under `name`. */
  async put(canvas, name) {
    const blob = await new Promise((done) => canvas.toBlob(done, "image/png"));
    if (!blob) throw new Error(t("could not read the picture"));
    const saved = await upload(new File([blob], name, { type: "image/png" }), SUBFOLDER);
    return saved.path;
  }

  close(result) {
    this.release?.();
    this.unmount();
    this.resolve(result);
  }
}

/** A clip -> one sheet. */
class SheetLay extends SheetCard {
  constructor(path, resolve) {
    super(path, resolve, {
      glyph: "video", title: "Lay a contact sheet", action: "Use this sheet",
    });
    this.duration = 0;
  }

  begin() {
    this.media = el("video", { src: viewUrl(this.path), preload: "auto", playsinline: true });
    this.media.muted = true;
    this.media.addEventListener("loadedmetadata", () => {
      this.duration = this.media.duration || 0;
      this.redraw();
    });
    this.say(t("Reading the clip…"));
  }

  release() {
    this.media.pause?.();
    this.media.removeAttribute("src");
  }

  /** Seconds into the clip for each tile, first frame to last.
   *
   *  Endpoints included rather than the middle of N equal slices: a sheet is a
   *  reading of the whole shot, and a reading that never shows the last frame
   *  is not one. The tail is held a hair back from the duration, where many
   *  containers have no frame to give.
   */
  marks() {
    const count = this.rows * this.cols;
    const end = Math.max(0, this.duration - 0.05);
    if (count === 1 || end <= 0) return [0];
    return Array.from({ length: count }, (_, i) => (i * end) / (count - 1));
  }

  /** Seek and wait. `seeked`, never a timeout: Firefox hands back the previous
   *  frame until it fires, which on a nine-tile sheet is eight wrong frames. */
  seek(at) {
    return new Promise((done) => {
      const settled = () => { this.media.removeEventListener("seeked", settled); done(); };
      this.media.addEventListener("seeked", settled);
      this.media.currentTime = at;
    });
  }

  async redraw() {
    if (!this.media.videoWidth || this.drawing) return;
    this.drawing = true;
    try {
      const { tileWidth, tileHeight, width, height } =
        sheetSize(this.media.videoWidth / this.media.videoHeight, this.rows, this.cols);
      this.stage.width = width;
      this.stage.height = height;
      const paint = this.stage.getContext("2d");
      const marks = this.marks();
      for (let i = 0; i < marks.length; i += 1) {
        this.say(t("Frame {n} of {count}…", { n: i + 1, count: marks.length }));
        await this.seek(marks[i]);
        paint.drawImage(this.media,
                        (i % this.cols) * tileWidth, Math.floor(i / this.cols) * tileHeight,
                        tileWidth, tileHeight);
      }
      this.say(t("{count} frames as one {w}×{h} picture. Attach it as the picture being "
              + "changed, write one instruction for all of them, and split the result back "
              + "up afterwards.",
              { count: marks.length, w: width, h: height }));
    } catch (error) {
      this.say(String(error?.message || error));
    } finally {
      this.drawing = false;
    }
  }

  async commit() {
    if (this.busy || this.drawing || !this.media.videoWidth) return;
    this.busy = true;
    this.act.textContent = t("Saving…");
    this.act.disabled = true;
    try {
      // The grid in the name, so the splitter opens on the right one later —
      // the edit itself will be a different file under a different name, and
      // this is the only place the shape can be written down.
      const path = await this.put(this.stage, `${this.stem()}-sheet-${this.cols}x${this.rows}.png`);
      this.close({ paths: [path] });
    } catch (error) {
      this.fail(error);
    }
  }
}

/** One sheet -> N frames. */
class SheetSplit extends SheetCard {
  constructor(path, resolve) {
    super(path, resolve, {
      glyph: "scissors", title: "Split a contact sheet", action: "Cut the frames out",
    });
    // The shape the sheet says it is, where it says so. An edited sheet comes
    // back from the pre-stage under the render's own name and says nothing, so
    // this is a head start rather than an answer.
    const named = GRID_IN_NAME.exec(path);
    if (named) {
      const found = GRIDS.findIndex(([rows, cols]) =>
        cols === Number(named[1]) && rows === Number(named[2]));
      if (found >= 0) this.grid = found;
    }
  }

  begin() {
    this.source = new Image();
    this.source.onload = () => this.redraw();
    this.source.onerror = () => this.say(t("That picture could not be read."));
    this.source.src = viewUrl(this.path);
    this.say(t("Reading the picture…"));
  }

  cut(i) {
    return tileRect(this.source.width, this.source.height, this.rows, this.cols, i);
  }

  redraw() {
    const { width, height } = this.source;
    if (!width) return;
    this.stage.width = width;
    this.stage.height = height;
    const paint = this.stage.getContext("2d");
    paint.drawImage(this.source, 0, 0);
    // The cuts, drawn: this is the one control whose effect is invisible until
    // the files are already written, and a grid that lands half a frame off is
    // exactly what a preview is for.
    paint.strokeStyle = "rgba(255,255,255,.85)";
    paint.lineWidth = Math.max(1, Math.round(Math.max(width, height) / 400));
    paint.setLineDash([paint.lineWidth * 6, paint.lineWidth * 4]);
    for (let col = 1; col < this.cols; col += 1) {
      const x = Math.round((col * width) / this.cols);
      paint.beginPath(); paint.moveTo(x, 0); paint.lineTo(x, height); paint.stroke();
    }
    for (let row = 1; row < this.rows; row += 1) {
      const y = Math.round((row * height) / this.rows);
      paint.beginPath(); paint.moveTo(0, y); paint.lineTo(width, y); paint.stroke();
    }
    const first = this.cut(0);
    this.say(t("{count} frames of {w}×{h}, saved into the input folder in order.",
            { count: this.rows * this.cols, w: first.width, h: first.height }));
  }

  async commit() {
    if (this.busy || !this.source.width) return;
    this.busy = true;
    this.act.textContent = t("Cutting…");
    this.act.disabled = true;
    try {
      const tile = el("canvas");
      const paint = tile.getContext("2d");
      const stem = `${this.stem()}-${this.cols}x${this.rows}`;
      const paths = [];
      for (let i = 0; i < this.rows * this.cols; i += 1) {
        const { x, y, width, height } = this.cut(i);
        tile.width = width;
        tile.height = height;
        paint.drawImage(this.source, x, y, width, height, 0, 0, width, height);
        // Zero-padded, because nine frames sorted as text put 10 after 1 — and
        // the order is the whole point of a strip.
        paths.push(await this.put(tile, `${stem}-${String(i + 1).padStart(2, "0")}.png`));
        this.act.textContent = t("Cutting… {n}/{count}",
                                 { n: i + 1, count: this.rows * this.cols });
      }
      this.close({ paths });
    } catch (error) {
      this.fail(error);
    }
  }
}
