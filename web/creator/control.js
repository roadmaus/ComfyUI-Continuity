// The ControlNet bench: footage in, a guide out.
//
// Everything else in this pack starts from a sentence. This starts from a file
// you already have — a clip off a phone, a frame off a film, a photograph — and
// turns it into the drawing a render can be aimed at: the outlines, the strokes,
// the blocks, the tones. It is the answer to the composition you can see and
// cannot describe.
//
// **A room rather than a window.** The picker and the preset library are modals:
// you open one, take a thing out of it and it goes away. This is somewhere you
// stay — you upload, you cut, you try three thresholds, you look, you try a
// fourth — so it takes the whole viewport the way the editor's shell does, with
// a bar of its own along the top and the way out at the end of it.
//
// **The light box is the signature and it is not decoration.** Rotoscoping was
// done by laying the frame on lit glass and drawing on top of it, and that is
// exactly the judgement being made here: is this tracing following the picture
// it came from. So the two are in *one* rectangle with a seam between them —
// footage on the left of the seam, tracing on the right — and the seam is
// dragged. A side-by-side pair would have been the obvious layout and it answers
// a different question: it lets you compare two pictures rather than see one
// through the other, and an edge that has slipped off a shoulder is invisible
// until they are on top of each other.
//
// **The picture answers while the slider is moving.** Nothing here queues. The
// server traces one frame at preview size in the time a round trip takes, and
// the request is a plain GET on an `<img>`, so the browser coalesces the drags
// and serves the repeats out of its cache. It is the reason the thresholds are
// sliders and not a form with an Apply button.
//
// **The output is a file in the input folder, and nothing else.** No node is
// added, no graph is touched, nothing is stored in a workflow. Where the guide
// goes afterwards is a separate press — the pre-stage's init image, or a
// reference on the shot — and both of those are doors this bench opens rather
// than wiring it owns.

import { el, icon, mark, drawFrame, mountOverlay, keepScroll, placeNear, dismissable } from "./dom.js";
import { controlPreviewUrl, controlRun, controlTracings, probe, viewUrl, upload,
         uiSetting, patchSettings, primeSettings } from "./api.js";
import { openChoicePopover } from "./pills.js";
import { openPicker } from "./picker.js";
import { formatTime, mountTrim } from "./trim.js";
import { t } from "./i18n.js";
import { api } from "../../../scripts/api.js";

/** Where an uploaded source lands. Its own shelf, so dragging a phone clip onto
 *  the bench does not put it in the root of everybody's picker. */
const SUBFOLDER = "continuity/footage";

/** How long the dials wait after the last movement before the picture is asked
 *  for again. Short enough that letting go of a slider feels like the picture
 *  was already coming; long enough that a drag across the whole track is one
 *  request at the end rather than sixty on the way. */
const SETTLE_MS = 90;

/**
 * What this machine last picked for each model-backed tracing.
 *
 * The pre-stage and the shot keep their weights in the piece, because a piece is
 * a record of what a render used and the file it used is part of that record.
 * The bench has no piece — it writes a file into the input folder and forgets —
 * so its picks go where the pack's other per-machine answers go: the user
 * settings, beside `weights` and the turbo lead-in. Which file on this disk is
 * the depth model is a fact about the disk rather than about any one tracing,
 * and asking again every time the bench opens would be asking it forever.
 */
const remembered = () => uiSetting("control_weights", {}) ?? {};

/** Record this tracing's picks as the machine's. Fire and forget, the way
 *  `models.rememberWeights` is: the bench already has the answer, and a memory
 *  that failed to write is next time's problem rather than this click's. */
function remember(op, picks) {
  patchSettings({ control_weights: { ...remembered(), [op]: picks } });
}

/** The bench, or null. One at a time: it is the room. */
let open = null;

/**
 * Open the bench.
 *
 * @param {object} [options]
 * @param {Array}  [options.targets]  where a finished guide can be sent:
 *   `[{ id, label, note, kinds, take(result) }]`. Empty is legitimate — the
 *   bench still writes the file, and the picker can find it.
 * @param {object} [options.source]  a file to start on, `{path, kind}`
 * @returns {Promise<void>}  resolves when the bench is closed
 */
export function openControl(options = {}) {
  open?.close();
  return new Promise((resolve) => {
    open = new Bench(options, resolve);
    open.mount();
  });
}

class Bench {
  constructor(options, resolve) {
    this.targets = options.targets ?? [];
    this.resolve = resolve;
    this.source = options.source ?? null;
    this.tracings = [];
    this.op = "as_shot";
    // Per tracing, so switching from Edges to Lines and back finds the
    // thresholds where they were left. A bench you have to re-dial every time
    // you compare two tracings is a bench that makes comparing them expensive.
    this.values = {};
    this.seam = 0.5;
    // The source's own pixel size, once something has reported one — the light
    // box's rectangle is derived from it. See `fit`.
    this.natural = null;
    // The span the guide is written from, in the shape the trim editor speaks:
    // null is the whole clip. Reported by the bar, never computed here.
    this.trim = null;
    // Where the bar's playhead is, and so which frame the glass is showing.
    this.at = 0;
    this.keepSound = false;
    this.hasAudio = false;
    this.busy = false;
    this.progress = null;
    // Which doors this tracing has already gone through, by target id. A set
    // rather than a name, because sending is not one press: a drawing can be
    // the shot's guide *and* a reference on the same card, and a row that
    // forgot the first send the moment the second happened would be a row that
    // cannot say what it has done.
    this.sentTo = new Set();
    // The door whose file is being cut right now — see `send`.
    this.sending = null;
    this.result = null;
    // Whether the tracing on the glass is currently being asked for over and
    // over because the clip is running. See `chase`.
    this.chasing = false;
    // Whether the still on the glass has anything on it yet — kept here rather
    // than read back off the element, because while the clip runs the still is
    // hidden and its own visibility no longer says whether it has landed.
    this.overReady = false;
    this.error = null;
    this.token = `ctl-${Math.random().toString(36).slice(2)}`;
  }

  // ---- the room --------------------------------------------------------------

  mount() {
    this.bench = keepScroll(el("div", { class: "mmc-ctl-bench" }));
    this.frame = el("div", { class: "mmc-ctl-frame" });
    this.box = el("div", { class: "mmc-ctl-box" }, [this.frame]);
    // Where the trim editor's bar goes, for a clip. Empty for a picture: a
    // still has no span, and an inert bar under one is a control claiming the
    // file has a length.
    this.cut = el("div", { class: "mmc-ctl-cut" });
    this.foot = el("div", { class: "mmc-ctl-foot" });
    this.work = el("div", { class: "mmc-ctl-work" }, [this.box, this.cut, this.foot]);

    this.room = el("div", { class: "mmc-ctl-room" }, [this.bench, this.work]);
    this.sheet = el("div", { class: "mmc-ctl" }, [
      el("div", { class: "mmc-ctl-bar" }, [
        el("span", { class: "mmc-ctl-mark" }, [mark(20)]),
        // The pack's name, not a sentence: the shell writes it untranslated too.
        el("span", { class: "mmc-ctl-word", text: "Continuity" }),
        el("span", { class: "mmc-ctl-slash", text: "/" }),
        el("span", { class: "mmc-ctl-here", text: t("ControlNet") }),
        el("span", { class: "mmc-ctl-gap" }),
        el("button", {
          class: "mmc-close", text: "✕", title: t("Close the bench"),
          onclick: () => this.close(),
        }),
      ]),
      this.room,
    ]);

    this.overlay = el("div", {
      class: "mmc-overlay mmc-ctl-over",
      // A file dropped anywhere on the bench is the source. The whole surface
      // takes it rather than a well in the corner, because the gesture is
      // "here, work on this" and asking somebody to aim it is asking them to
      // find the target first.
      ondragover: (event) => { event.preventDefault(); this.overlay.classList.add("dropping"); },
      ondragleave: (event) => { if (event.target === this.overlay) this.overlay.classList.remove("dropping"); },
      ondrop: (event) => {
        event.preventDefault();
        this.overlay.classList.remove("dropping");
        const file = event.dataTransfer?.files?.[0];
        if (file) this.take(file);
      },
    }, [this.sheet]);

    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.onProgress = ({ detail }) => {
      if (detail?.token !== this.token) return;
      this.progress = detail.progress;
      this.paintFoot();
    };
    api.addEventListener("continuity.control", this.onProgress);

    this.render();
    this.watchBox();
    this.load();
  }

  async load() {
    try {
      this.tracings = await controlTracings();
    } catch (error) {
      this.error = String(error.message || error);
    }
    if (!this.overlay.isConnected) return;
    this.adopt();
    this.render();
    if (this.source) this.openSource(this.source);
    // The picks are remembered in the settings, which may not have landed yet —
    // the bench can be opened before anything else on the page has asked for
    // them. Adopting again when they arrive is what makes the memory show up on
    // a cold open rather than on the second one.
    primeSettings(() => {
      if (!this.overlay.isConnected) return;
      this.adopt();
      this.paintBench();
      this.askForTrace();
    });
  }

  /**
   * Fill every tracing's dials, and its model picks from what this machine
   * last chose.
   *
   * A remembered name is taken only if the file is still on the disk. A model
   * deleted out from under a memory would otherwise be a pick the bench goes on
   * displaying and the server quietly refuses — which is the one failure a
   * picker must not have, because the name on screen is the whole of what it
   * promises. Anything already dialled wins over both: this runs again whenever
   * the listing is re-read, and it must not undo a choice made since.
   */
  adopt() {
    for (const tracing of this.tracings) {
      const held = this.values[tracing.id] ?? {};
      const kept = remembered()[tracing.id] ?? {};
      this.values[tracing.id] = Object.fromEntries((tracing.params ?? []).map((spec) => {
        if (spec.kind !== "choice") return [spec.key, held[spec.key] ?? spec.default];
        const options = spec.options ?? [];
        const known = [held[spec.key], kept[spec.key]].find((name) => options.includes(name));
        return [spec.key, known ?? spec.default];
      }));
    }
  }

  /**
   * Ask the server again what is on the disk.
   *
   * The catalogue is cached for the life of the page, which is right for a list
   * of tracings and wrong the moment a model is copied into a folder while the
   * bench is open — a listing that never expires is a file that can never be
   * picked. Opening the weights control is the one moment the listing is being
   * read rather than displayed, so that is where the question is asked again.
   */
  async freshen(onChanged) {
    const before = JSON.stringify(this.tracings);
    try {
      this.tracings = await controlTracings({ fresh: true });
    } catch { return; }
    if (!this.overlay.isConnected) return;
    this.adopt();
    if (JSON.stringify(this.tracings) !== before) onChanged?.();
  }

  close() {
    if (open === this) open = null;
    api.removeEventListener("continuity.control", this.onProgress);
    this.chasing = false;
    clearTimeout(this.sweeping);
    clearTimeout(this.settling);
    this.overVideo?.pause();
    this.watcher?.disconnect();
    this.cutter?.destroy();
    this.cutter = null;
    this.unmount?.();
    this.resolve?.();
  }

  // ---- the source ------------------------------------------------------------

  /** A dropped or chosen `File` -> uploaded, then opened. */
  async take(file) {
    this.error = null;
    this.busy = true;
    this.paintBench();
    try {
      const asset = await upload(file, SUBFOLDER);
      this.busy = false;
      this.openSource(asset);
    } catch (error) {
      this.busy = false;
      this.error = String(error.message || error);
      this.render();
    }
  }

  async browse() {
    const chosen = await openPicker({
      kinds: ["image", "video", "renders"], kind: "video", single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    if (chosen?.[0]) this.openSource(chosen[0]);
  }

  /**
   * Put a file on the bench.
   *
   * The result is cleared with it. A guide that stayed on screen after the
   * footage under it was replaced would be a file offered for sending that had
   * nothing to do with what the bench is showing.
   */
  openSource(asset) {
    this.source = asset;
    this.result = null;
    this.sentTo.clear();
    this.sending = null;
    this.error = null;
    this.trim = null;
    this.at = 0;
    this.hasAudio = false;
    this.natural = null;
    this.sized = false;
    this.under = null;
    this.chasing = false;
    this.cutter?.destroy();
    this.cutter = null;
    if (asset.kind === "video") {
      // The cut, and the decoder, in one thing: `mountTrim` is the reference
      // trim editor's own bar mounted here instead of in a modal, and the clip
      // it is already decoding for its playhead is the clip the light box wants
      // a frame of. Two <video> elements over one file would have been two
      // downloads and two seeks answering the same question.
      this.cutter = mountTrim({
        path: asset.path, kind: "video", trim: null, showTrack: false,
        // The bench draws the frame itself, on the glass, with the tracing over
        // it — a second picture inside the bar would be the same frame twice.
        picture: false,
        onFrame: (media) => this.paintUnder(media),
        onChange: ({ trim }) => this.onCut(trim),
      });
      this.cut.replaceChildren(this.cutter.root);
      // The transport is the bar's, so the bench hears about it rather than
      // owning it: what happens on the right of the seam when a clip starts
      // running is a different question from what happens when it is parked,
      // and `onRun` is where the two are told apart.
      this.cutter.media.addEventListener("play", () => this.onRun(true));
      this.cutter.media.addEventListener("pause", () => this.onRun(false));
      this.askAboutSound(asset.path);
    } else {
      this.cut.replaceChildren();
    }
    this.render();
    this.askForTrace();
  }

  /** Whether this clip has a soundtrack to keep. Not guessed: no browser
   *  answers it portably, and a silent clip offered a Keep the sound switch is
   *  a switch that does nothing whichever way it is thrown. */
  async askAboutSound(path) {
    const { hasAudio } = await probe(path);
    if (this.source?.path !== path) return;
    this.hasAudio = hasAudio === true;
    this.paintFoot();
  }

  /**
   * The bar reporting where the cut is now.
   *
   * Two things follow from it and they are different. The span is what will be
   * written, so it is kept. The *frame* is where the bar's playhead is sitting
   * — which the bar moves to the handle you are dragging — so the tracing on
   * the glass is asked for at whatever the transport is showing, and dragging
   * the in point traces the in point as it goes.
   */
  onCut(trim) {
    this.trim = trim;
    this.at = this.cutter?.at() ?? 0;
    this.mountTraced();
    this.askForTrace();
    this.paintBench();
  }

  // ---- the tracing ------------------------------------------------------------

  tracing() {
    return this.tracings.find((entry) => entry.id === this.op) ?? null;
  }

  /** Whether the current tracing has, on this machine, everything it needs.
   *
   *  False only for Depth and Pose, and only until their models are on the
   *  disk — the server decides it by looking, so a file dropped into
   *  models/geometry_estimation makes Depth work without anything here
   *  learning about it. An unready tracing is still selectable: what somebody
   *  needs at that point is to read what is missing, and a button that refuses
   *  the press cannot tell them. */
  ready() {
    return this.tracing()?.ready !== false;
  }

  setOp(id) {
    const tracing = this.tracings.find((entry) => entry.id === id);
    if (!tracing || id === this.op) return;
    this.op = id;
    // Not the result: a guide already written is still a file that exists, and
    // clearing it because a different tracing was *selected* would throw away
    // work on the strength of a change nobody has run yet. The foot says which
    // tracing the standing result came from.
    this.render();
    this.askForTrace();
    this.chasing = false;
  }

  setValue(key, value) {
    this.values[this.op] = { ...this.values[this.op], [key]: value };
    // A dial moved is a written file that no longer says what the bench says.
    // It is still a file — the foot goes on offering it — but it comes off the
    // glass, because the glass is showing what these dials mean.
    this.mountTraced();
    this.askForTrace();
  }

  /**
   * Ask the server for this frame under the current dials.
   *
   * Double-buffered: the new picture is loaded into a detached `Image` and only
   * swapped in once it has decoded. Setting `src` on the visible element would
   * blank it for the length of the round trip, and a light box that flickers
   * every time a threshold moves is a light box you cannot judge anything on.
   */
  askForTrace() {
    if (!this.source || !this.ready()) return;
    clearTimeout(this.settle);
    this.settle = setTimeout(() => this.fetchTrace(), SETTLE_MS);
  }

  /** @param {?function} done  called once this request is out of the air,
   *   however it ended — the chase asks for the next frame from here, so a
   *   failed or superseded request has to report as loudly as a good one or the
   *   chase stops for the rest of the clip. */
  fetchTrace(done) {
    const url = controlPreviewUrl(this.source.path, this.op, this.values[this.op] ?? {}, this.at);
    if (url === this.wanted) { done?.(); return; }
    this.wanted = url;
    this.box.classList.add("waiting");
    const picture = new Image();
    picture.onload = () => {
      done?.();
      // A slower request that started earlier can land after a faster one that
      // started later. Only the picture the dials are currently asking for is
      // allowed onto the glass.
      if (url !== this.wanted || !this.overlay.isConnected) return;
      this.box.classList.remove("waiting");
      this.over.src = url;
      this.overReady = true;
      this.showLayer();
    };
    picture.onerror = () => {
      done?.();
      if (url !== this.wanted) return;
      this.box.classList.remove("waiting");
      this.error = t("That frame could not be traced.");
      this.paintFoot();
    };
    picture.src = url;
  }

  // ---- the right of the seam, in motion ----------------------------------------
  //
  // Parked, the tracing on the glass is a still the server drew from the dials
  // as they stand — which is the picture a threshold is judged on. Running, it
  // cannot be: a still that stays put while the footage beside it moves is the
  // one thing that makes a wipe unreadable, because the two halves stop being
  // the same moment. So a running clip gets one of two other things, and which
  // one depends on whether there is a written file to show.

  /** The dials as they stand, as one comparable string. What a written guide
   *  was made from is stamped with this, so a file traced before a threshold
   *  moved can be told from one that still matches — it is a real file either
   *  way, but only the matching one is what this tracing means now. */
  dialled() {
    return JSON.stringify([this.op, this.values[this.op] ?? {}, this.trim]);
  }

  /** The written guide, if it is a clip and still matches the dials. */
  playable() {
    return this.result?.kind === "video" && this.result.dialled === this.dialled()
      ? this.result : null;
  }

  /** Put the written guide on the glass, or take it off again.
   *
   *  Its own `<video>` rather than the canvas the footage goes through: the
   *  footage is drawn frame by frame because the bar owns that decoder and the
   *  bench is only borrowing its output, whereas this file is the bench's own
   *  and there is nothing to be gained by decoding it by hand. */
  mountTraced() {
    const wanted = this.playable() ? viewUrl(this.result.path) : null;
    if ((this.overVideo?.dataset.src ?? null) === wanted) return;
    this.overVideo?.pause();
    this.overVideo?.remove();
    this.overVideo = null;
    if (!wanted || !this.over?.isConnected) return;
    this.overVideo = el("video", {
      class: "mmc-ctl-layer mmc-ctl-traced", src: wanted,
      playsinline: true, preload: "auto", style: { visibility: "hidden" },
    });
    // The property, not only the attribute: a muted attribute set after the
    // element exists is ignored by the autoplay rules in some browsers, and a
    // guide that will not start because it might make a noise is a guide that
    // silently never plays. It has no soundtrack to make a noise with anyway.
    this.overVideo.muted = true;
    this.overVideo.dataset.src = wanted;
    this.over.after(this.overVideo);
  }

  /** Which of the two tracings — the still or the file — is the visible one.
   *  Never both: they occupy the same rectangle. */
  showLayer() {
    const running = !!this.overVideo && this.cutter?.media?.paused === false;
    if (this.over) {
      this.over.style.visibility = !running && this.overReady ? "visible" : "hidden";
    }
    if (this.overVideo) {
      this.overVideo.style.visibility = running ? "visible" : "hidden";
    }
  }

  /**
   * Hold the written guide against the footage, frame for frame.
   *
   * The footage is the clock — it is the one the transport, the playhead and
   * the waveform are all already reading — and the guide follows it, offset by
   * the in point, because the file was written from the cut and starts where
   * the cut does.
   *
   * Parked, it is put exactly where the footage is; running, only when the two
   * have come more than a sixth of a second apart. Assigning `currentTime` to a
   * playing `<video>` is a seek, and a seek every frame is a stutter — the
   * point of letting it run on its own clock is that it mostly does not need
   * correcting at all.
   */
  syncTraced(media) {
    this.showLayer();
    const shadow = this.overVideo;
    if (!shadow || !media) return;
    const want = Math.max(0, (media.currentTime || 0) - (this.trim?.start ?? 0));
    if (media.paused) {
      if (!shadow.paused) shadow.pause();
      if (Math.abs(shadow.currentTime - want) > 0.02) shadow.currentTime = want;
      return;
    }
    if (shadow.paused) shadow.play().catch(() => {});
    if (Math.abs(shadow.currentTime - want) > 0.16) shadow.currentTime = want;
  }

  /**
   * The transport started or stopped.
   *
   * Starting is where the chase begins, and stopping is where the still has to
   * be brought back to the frame the clip actually stopped on — nothing else
   * reports that, because the cut did not change and the bar only speaks when
   * it does.
   */
  onRun(running) {
    if (running) {
      this.chasing = !this.playable() && !this.tracing()?.heavy && this.ready();
      if (this.chasing) this.chase();
    } else {
      this.chasing = false;
      this.at = this.cutter?.at() ?? this.at;
      this.askForTrace();
    }
    this.showLayer();
  }

  /**
   * The tracing, chased through a running clip.
   *
   * With no written file to show, the honest thing on the right of the seam is
   * the frame under the playhead traced *now*, and the server can very nearly
   * do that: at preview size these operators are a few milliseconds of
   * arithmetic and the round trip is most of the cost. So one request is kept
   * in the air and the next is asked for the moment the last one has decoded —
   * which makes the rate whatever this machine can actually answer at, and
   * makes a slow one degrade to a slower wipe instead of a queue of frames the
   * playhead has already gone past.
   *
   * The mark is rounded to a twelfth of a second so a looping segment asks
   * twice for frames it has already been given, and the browser answers the
   * second time out of its own cache.
   *
   * Not for Depth and Pose. Those are a model per frame; a chase over them
   * would put a request in the air that lands after the shot it was asked about
   * has left the screen. They show the written file or they show nothing, and
   * `heavy` in the catalogue is how they say so.
   */
  chase() {
    if (!this.chasing) return;
    const media = this.cutter?.media;
    if (!media || media.paused || !this.overlay.isConnected) {
      this.chasing = false;
      this.showLayer();
      return;
    }
    this.at = Math.round((media.currentTime || 0) * 12) / 12;
    this.fetchTrace(() => {
      if (this.chasing) requestAnimationFrame(() => this.chase());
    });
  }

  // ---- tracing the whole file --------------------------------------------------

  async trace() {
    if (this.busy || !this.source) return;
    this.busy = true;
    this.progress = null;
    this.sentTo.clear();
    this.error = null;
    this.result = null;
    this.paintFoot();
    try {
      this.result = await controlRun({
        filename: this.source.path,
        op: this.op,
        params: this.values[this.op] ?? {},
        trim: this.trim,
        keep_sound: this.keepSound,
        token: this.token,
      });
      this.result.op = this.tracing()?.label ?? this.op;
      // The tracing's id as well as its name. A target may need to know *which*
      // tracing this is and not only what to call it: the weights that follow a
      // guide natively were post-trained on three of them, and a fourth handed
      // over reads as a picture of a drawing.
      this.result.opId = this.op;
      // What it was traced from, so the light box can tell later whether the
      // file it is about to play is still what the dials mean. Read before any
      // repaint, because a dial moved after this is a file that has gone stale.
      this.result.dialled = this.dialled();
      this.arrive();
    } catch (error) {
      this.error = String(error.message || error);
    }
    this.busy = false;
    this.progress = null;
    if (this.overlay.isConnected) this.paintFoot();
  }

  /**
   * The tracing has landed.
   *
   * The bench's whole argument is that a tracing is judged *through* the
   * footage, so the moment a file exists is the one moment worth seeing it
   * alone: the seam runs out to the left edge, the drawing takes the whole
   * glass for half a second under its own name, and the seam eases back to
   * wherever it was being held. One gesture, on the one element in the room
   * allowed to be loud, made out of the control the room is already built
   * around — rather than a tick, a toast or a colour that means "good".
   *
   * The name goes back to the tracing's afterwards. A tag that kept the
   * filename would be a label that goes stale the next time a dial moves, and
   * the tag's standing job is to say which half of the glass you are looking
   * at.
   */
  arrive() {
    this.mountTraced();
    const named = this.result?.path.split("/").pop() ?? "";
    const settle = () => {
      if (this.tagRight) this.tagRight.textContent = t(this.tracing()?.label ?? "");
      this.frame?.classList.remove("sweeping");
    };
    clearTimeout(this.sweeping);
    clearTimeout(this.settling);
    if (!this.frame || !this.tagRight
        || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    this.tagRight.textContent = named;
    const held = this.seam;
    this.frame.classList.add("sweeping");
    this.seam = 0;
    this.paintSeam();
    this.sweeping = setTimeout(() => {
      this.seam = held;
      this.paintSeam();
      this.settling = setTimeout(settle, 520);
    }, 560);
  }

  /**
   * A door pressed.
   *
   * Most doors take the file that was written. One kind does not, and it is the
   * reason this is asynchronous: a pre-stage renders a still, so a clip has
   * nothing it can hand over — but the frame under the playhead is a still, and
   * the bench can write it. So the press cuts that frame first, through the
   * same operator at the same dials, and hands over what comes back.
   *
   * That is the whole of the answer to "a clip cannot go to a pre-stage". It
   * was true and it was useless: it named a shape mismatch at the one moment
   * nothing could be done about it. What somebody wants at that point is the
   * composition they were just looking at, in the step that draws stills, and
   * the bench is holding every part needed to make it.
   *
   * @param {{target: object, frame: boolean}} door
   */
  async send(door) {
    if (!this.result || this.sending) return;
    let handed = this.result;
    if (door.frame) {
      this.sending = door.target.id;
      this.error = null;
      this.paintFoot();
      try {
        const cut = await controlRun({
          filename: this.source.path,
          op: this.op,
          params: this.values[this.op] ?? {},
          at: this.at,
        });
        // Stamped like a full run's answer, because the far side reads the same
        // fields off both: which tracing this is decides whether the weights it
        // lands in front of were ever post-trained on it.
        handed = { ...cut, op: this.result.op, opId: this.op, dialled: this.dialled() };
      } catch (error) {
        this.error = String(error.message || error);
        this.sending = null;
        this.paintFoot();
        return;
      }
      this.sending = null;
      if (!this.overlay.isConnected) return;
    }
    door.target.take(handed);
    this.sentTo.add(door.target.id);
    // Some sends are the end of the errand rather than one of several: a guide
    // handed to the pre-stage is there to have a prompt written around it, and
    // leaving the bench in front of the thing that just received the file makes
    // the room something to dismiss before the work can start. The file is
    // written either way, so nothing is lost by closing — the picker finds it.
    if (door.target.closeOnSend) return this.close();
    this.paintFoot();
  }

  // ---- where a tracing can go ---------------------------------------------------

  /**
   * What this source can be written as.
   *
   * A clip can be a clip, and — through the playhead — any one of its frames. A
   * photograph can only ever be a still. The distinction is a fact about the
   * *source*, known the moment it lands on the bench, which is why the doors are
   * decided from it rather than from whatever the last press happened to write.
   */
  produces() {
    return this.source?.kind === "video" ? ["video", "image"] : ["image"];
  }

  /** Every door this source can reach, and whether reaching it means cutting a
   *  frame first. Order is the targets' own: they arrive strongest-aim-first,
   *  which is the order somebody reads them in. */
  doors() {
    const can = this.produces();
    const written = this.result?.kind ?? null;
    return this.targets
      .filter((target) => !target.kinds || target.kinds.some((kind) => can.includes(kind)))
      .map((target) => ({
        target,
        frame: Boolean(target.kinds) && Boolean(written) && !target.kinds.includes(written),
      }));
  }


  // ---- drawing ------------------------------------------------------------------

  render() {
    this.paintBench();
    this.paintBox();
    this.paintFoot();
  }

  /** A titled section of the bench. The rule is the section's width, drawn —
   *  the same eyebrow the shell's columns and the dashboard's groups wear, so
   *  the three surfaces of this pack are labelled in one voice. */
  section(title, children) {
    return el("div", { class: "mmc-ctl-sect" }, [
      el("div", { class: "mmc-ctl-eyebrow" }, [
        el("span", { text: title }),
        el("span", { class: "mmc-ctl-rule" }),
      ]),
      ...children.filter(Boolean),
    ]);
  }

  paintBench() {
    const source = this.source;
    this.bench.replaceChildren(
      this.section(t("Source"), [
        source
          ? el("div", { class: "mmc-ctl-file" }, [
              el("span", { class: "mmc-ctl-filename", text: source.path.split("/").pop(), title: source.path }),
              el("span", { class: "mmc-ctl-filenote", text: this.sourceLine() }),
            ])
          : el("p", { class: "mmc-ctl-empty", text: t("Nothing on the bench yet.") }),
        // One door, not two. The picker already carries an Upload of its own, so
        // a second one here would be the same act reachable two ways — and a
        // file dragged onto the room does not need a button at all.
        el("button", {
          class: "mmc-ctl-verb", onclick: () => this.browse(), disabled: this.busy,
        }, [icon("folder", 14), el("span", {
          text: this.busy ? t("Uploading…") : source ? t("Change the footage") : t("Choose footage"),
        })]),
      ]),
      this.section(t("Tracing"), [
        el("div", { class: "mmc-ctl-ops" }, this.tracings.map((tracing) => el("button", {
          class: `mmc-ctl-op${tracing.id === this.op ? " on" : ""}${tracing.ready === false ? " unready" : ""}`,
          "aria-pressed": tracing.id === this.op,
          title: t(tracing.note),
          onclick: () => this.setOp(tracing.id),
        }, [
          el("span", { class: "mmc-ctl-opname", text: t(tracing.label) }),
          tracing.ready === false
            ? el("span", { class: "mmc-ctl-lack", text: t("no model") }) : null,
        ]))),
        el("p", { class: "mmc-ctl-note", text: this.tracing() ? t(this.tracing().note) : "" }),
        // What is missing, in full, and only for the tracing being looked at.
        // A pill that says "no model" and nothing else is a dead end; this is
        // the file to download and the folder to put it in.
        this.ready() ? null : el("p", { class: "mmc-ctl-needs", text:
          t("Not ready. This needs {what}", { what: t(this.tracing().needs) }) }),
        // Under the tracing it belongs to rather than among the dials: it is
        // part of choosing Depth, not part of aiming it.
        this.models().length ? el("div", { class: "mmc-ctl-weights" }, [this.weightsPill()]) : null,
      ]),
      ...(this.dials().length ? [this.section(t("Dials"), this.dials())] : []),
    );
  }

  // ---- weights ---------------------------------------------------------------
  //
  // Depth and Pose need a file on this disk, and which file is not a dial. It is
  // set once when the model is installed and then never again, which is the same
  // shape as the pre-stage's weights and the shot's — so it wears the same pill,
  // opens the same popover and lists through the same chooser, rather than a
  // select among the thresholds that would read as one more thing to tune. And
  // because it is a fact about the machine rather than about this session, it is
  // remembered: see `remembered` at the top of this module.

  /** The current tracing's model picks, as the catalogue declares them. */
  models() {
    return (this.tracing()?.params ?? []).filter((spec) => spec.kind === "choice");
  }

  pick(spec) {
    return this.values[this.op]?.[spec.key] ?? "";
  }

  setModel(key, name) {
    this.values[this.op] = { ...this.values[this.op], [key]: name };
    remember(this.op, Object.fromEntries(
      this.models().map((spec) => [spec.key, this.pick(spec)])));
    // The written guide came off a different model, so it is no longer what the
    // bench says — the same rule any other dial follows.
    this.mountTraced();
    this.paintBench();
    this.askForTrace();
  }

  weightsPill() {
    const fields = this.models();
    const missing = fields.filter((spec) => !this.pick(spec));
    const label = missing.length === 0
      ? t("weights")
      : missing.length === 1
        ? t("no {field}", { field: t(missing[0].label).toLowerCase() })
        : t("{count} weights missing", { count: missing.length });
    return el("button", {
      class: `mmc-pill mmc-weights${missing.length ? " missing" : ""}`,
      title: missing.length
        ? t("Not picked yet: {fields}. The tracing is refused without them.",
            { fields: missing.map((spec) => t(spec.label)).join(", ") })
        : t("Which files {tracing} runs.", { tracing: t(this.tracing().label) }),
      onclick: (event) => this.openWeights(event.currentTarget),
    }, [icon("weights", 16), el("span", { text: label })]);
  }

  /**
   * A row per file, each opening the list for its folder.
   *
   * Rebuilt in place after a pick rather than closed, for the reason the
   * pre-stage's is: Pose takes two files, and closing between them would make
   * setting the tracing up two round trips through a pill.
   */
  openWeights(anchor) {
    const pop = el("div", { class: "mmc-pop mmc-weights-pop" });
    const body = el("div");
    const render = () => body.replaceChildren(...this.models().map((spec) => {
      const held = this.pick(spec);
      const options = spec.options ?? [];
      return el("div", { class: `mmc-weight-row${held ? "" : " missing"}` }, [
        el("span", { class: "mmc-weight-name", text: t(spec.label) }),
        el("button", {
          class: `mmc-weight-file${held ? "" : " empty"}`,
          title: t(spec.note),
          text: held || (options.length ? t("not set") : t("nothing installed")),
          disabled: options.length ? null : true,
          onclick: (event) => openChoicePopover(event.currentTarget, {
            title: t(spec.label),
            options,
            value: held,
            onPick: (picked) => { this.setModel(spec.key, picked); render(); },
          }),
        }),
      ]);
    }));

    pop.append(
      el("div", { class: "mmc-pop-title",
                  text: t("Weights — {tracing}", { tracing: t(this.tracing().label) }) }),
      body,
    );
    render();
    document.body.appendChild(pop);
    placeNear(pop, anchor);
    dismissable(pop);
    // A model copied in while this was open is the reason to ask again, and the
    // bench behind the popover has to hear about it too — it is what turns the
    // tracing from not-ready to ready.
    this.freshen(() => {
      if (!pop.isConnected) return;
      this.paintBench();
      render();
    });
  }

  sourceLine() {
    const media = this.cutter?.media;
    const parts = [];
    if (this.source.kind === "video") {
      if (media?.videoWidth) parts.push(`${media.videoWidth}×${media.videoHeight}`);
      if (media?.duration) parts.push(formatTime(media.duration));
    }
    parts.push(this.source.kind === "video" ? t("video") : t("picture"));
    return parts.join(" · ");
  }

  /** The current tracing's dials. Built from the server's own spec, which is why
   *  adding a tracing over there needs nothing here. */
  dials() {
    const tracing = this.tracing();
    if (!tracing) return [];
    // Model picks are not dials and are not drawn here — see `weightsPill`.
    return (tracing.params ?? []).filter((spec) => spec.kind !== "choice").map((spec) => {
      const held = this.values[this.op]?.[spec.key] ?? spec.default;
      if (spec.kind === "switch") {
        return el("label", { class: "mmc-ctl-switch", title: t(spec.note) }, [
          el("input", {
            type: "checkbox", checked: held || null,
            onchange: (event) => this.setValue(spec.key, event.target.checked),
          }),
          el("span", { text: t(spec.label) }),
        ]);
      }
      const readout = el("span", { class: "mmc-ctl-value", text: String(held) });
      return el("div", { class: "mmc-ctl-dial", title: t(spec.note) }, [
        el("div", { class: "mmc-ctl-diallabel" }, [
          el("span", { text: t(spec.label) }), readout,
        ]),
        el("input", {
          type: "range", class: "mmc-ctl-range",
          min: String(spec.min), max: String(spec.max), step: String(spec.step),
          value: String(held),
          oninput: (event) => {
            readout.textContent = event.target.value;
            this.setValue(spec.key, Number(event.target.value));
          },
        }),
      ]);
    });
  }

  /**
   * The light box.
   *
   * Two layers in one rectangle at the source's own aspect: the footage
   * underneath, the tracing on top clipped to the right of the seam. Dragging
   * anywhere on the picture moves the seam, because the seam is the only thing
   * on this surface there is to drag and making people find a four-pixel grip
   * first is making them work for it.
   */
  paintBox() {
    if (!this.source) {
      this.frame.replaceChildren(el("div", { class: "mmc-ctl-drop" }, [
        icon("image", 40),
        el("p", { class: "mmc-ctl-dropline", text: t("Drop a picture or a clip here") }),
        el("p", { class: "mmc-ctl-dropnote", text: t("Or upload one from the bench on the left.") }),
      ]));
      this.natural = null;
      this.frame.style.width = this.frame.style.height = "";
      this.box.classList.add("bare");
      return;
    }
    this.box.classList.remove("bare");
    this.under = this.source.kind === "video"
      ? el("canvas", { class: "mmc-ctl-layer" })
      : el("img", { class: "mmc-ctl-layer", src: viewUrl(this.source.path), alt: "" });
    if (this.under.tagName === "IMG") {
      const sized = () => this.fit(this.under.naturalWidth, this.under.naturalHeight);
      // `complete` as well as the event: a picture already in the browser's
      // cache is decoded before this listener exists, and `load` never fires.
      this.under.addEventListener("load", sized);
      if (this.under.complete) sized();
    }
    this.over = el("img", {
      class: "mmc-ctl-layer mmc-ctl-traced", alt: "",
      style: { visibility: "hidden" },
    });
    // A new element has nothing on it, whatever the old one had.
    this.overReady = false;
    this.overVideo = null;
    this.seamEl = el("div", { class: "mmc-ctl-seam" }, [
      el("span", { class: "mmc-ctl-grip" }, [icon("swap", 14)]),
    ]);
    this.frame.replaceChildren(
      this.under, this.over, this.seamEl,
      el("span", { class: "mmc-ctl-tag left", text: t("Footage") }),
      // Kept, because it is the one label on the glass that changes: for the
      // length of the arrival sweep it says the name of the file that was just
      // written, and then goes back to saying which tracing this is. See
      // `arrive`.
      this.tagRight = el("span", {
        class: "mmc-ctl-tag right", text: t(this.tracing()?.label ?? ""),
      }),
    );
    this.frame.onpointerdown = (event) => this.dragSeam(event);
    this.paintSeam();
    this.mountTraced();
    this.paintUnder();
  }

  dragSeam(event) {
    const move = (at) => {
      const box = this.frame.getBoundingClientRect();
      if (!box.width) return;
      this.seam = Math.max(0, Math.min(1, (at.clientX - box.left) / box.width));
      this.paintSeam();
    };
    move(event);
    this.frame.setPointerCapture(event.pointerId);
    const up = () => {
      this.frame.removeEventListener("pointermove", move);
      this.frame.removeEventListener("pointerup", up);
      this.frame.removeEventListener("pointercancel", up);
    };
    this.frame.addEventListener("pointermove", move);
    this.frame.addEventListener("pointerup", up);
    this.frame.addEventListener("pointercancel", up);
  }

  paintSeam() {
    const at = `${(this.seam * 100).toFixed(2)}%`;
    this.frame.style.setProperty("--mmc-seam", at);
  }

  paintUnder(media = this.cutter?.media) {
    if (media && this.under?.tagName === "CANVAS") {
      drawFrame(this.under, media);
      this.fit(media.videoWidth, media.videoHeight);
      // The bar knows the clip's shape before the bench does, so the readout
      // that names it is redrawn once the first frame has landed.
      if (!this.sized) { this.sized = true; this.paintBench(); }
    }
    // The bar calls this once per displayed frame while the clip runs, which
    // makes it the right place to keep the other half of the wipe alongside.
    this.syncTraced(media);
  }

  /**
   * Size the light box's rectangle to the source's own shape.
   *
   * In script rather than in `aspect-ratio`, and not for want of trying: a box
   * with a ratio and both a max-width and a max-height either distorts (given a
   * width to start from) or collapses to nothing (given neither). Every layer
   * here has to occupy *exactly* the same rectangle — that is what a wipe is —
   * so "near enough, and object-fit will letterbox the difference" is not
   * available: the letterboxing is where the seam and the tags would then sit.
   */
  fit(width, height) {
    if (!width || !height) return;
    this.natural = { width, height };
    const room = this.box.getBoundingClientRect();
    if (!room.width || !room.height) return;
    const scale = Math.min(room.width / width, room.height / height);
    this.frame.style.width = `${Math.round(width * scale)}px`;
    this.frame.style.height = `${Math.round(height * scale)}px`;
  }

  /** And again whenever the room changes shape under it. */
  watchBox() {
    this.watcher?.disconnect();
    this.watcher = new ResizeObserver(() => {
      if (this.natural) this.fit(this.natural.width, this.natural.height);
    });
    this.watcher.observe(this.box);
  }

  /**
   * The row that runs the tracing, and what came of it.
   *
   * The result is not a picture. What the bench produces is a file, and the
   * useful thing to say about a file is its name and where it can go — so this
   * says both, and the light box goes on showing the frame you were judging.
   */
  paintFoot() {
    const run = el("button", {
      class: "mmc-ctl-run", disabled: !this.source || this.busy || !this.ready() || null,
      onclick: () => this.trace(),
      text: this.busy
        ? (this.progress != null
            ? t("Tracing… {percent}%", { percent: Math.round(this.progress * 100) })
            : t("Tracing…"))
        : t("Trace"),
    });
    // Filtered, not spread with holes: `replaceChildren` takes strings as well
    // as nodes, so a null reaches the document as the word "null".
    this.foot.replaceChildren(...[
      // Only for a clip that has a soundtrack to keep. A switch over a silent
      // file does nothing whichever way it is thrown, and the probe is what
      // settles it — no browser answers the question portably.
      this.hasAudio ? el("label", { class: "mmc-ctl-switch", title: t(
        "Carry the clip's own soundtrack into the file this writes. Off, the guide "
        + "comes out silent — which is what a guide usually wants to be.") }, [
        el("input", {
          type: "checkbox", checked: this.keepSound || null,
          onchange: (event) => { this.keepSound = event.target.checked; },
        }),
        el("span", { text: t("Keep the sound") }),
      ]) : null,
      el("span", { class: "mmc-ctl-gap" }),
      this.error ? el("span", { class: "mmc-ctl-bad", text: this.error }) : null,
      run,
    ].filter(Boolean));
    this.paintResult();
  }

  /**
   * The file that was written, and the doors it can go through.
   *
   * The doors are the reason this is a shelf rather than a row of buttons. Every
   * one of them takes the same drawing and does something different with it —
   * aims a shot at it frame for frame, builds a still on it, hands it over as a
   * look to be named in a prompt — and three identical pills reading "Send to…"
   * make three instructions look like one act with three destinations. So each
   * door says what it does underneath what it is called, in the vocabulary the
   * card it lands on uses.
   *
   * One of them is filled: the door that takes the file exactly as it was
   * written, which on a family with a control branch is the door this bench was
   * opened for. Where no door takes it as written — every remaining door wants a
   * frame cut out of it — none is filled, because there is nothing here that is
   * simply the obvious next press.
   */
  paintResult() {
    if (!this.resultRow) {
      this.resultRow = el("div", { class: "mmc-ctl-out" });
      this.work.appendChild(this.resultRow);
    }
    if (!this.result) {
      this.resultRow.replaceChildren();
      this.resultRow.classList.remove("on");
      return;
    }
    this.resultRow.classList.add("on");
    const doors = this.doors();
    const lead = doors.find((door) => !door.frame) ?? null;
    this.resultRow.replaceChildren(
      el("div", { class: "mmc-ctl-outword" }, [
        el("span", { class: "mmc-ctl-outname", text: this.result.path.split("/").pop() }),
        el("span", { class: "mmc-ctl-outnote", text: this.outLine() }),
      ]),
      el("span", { class: "mmc-ctl-gap" }),
      doors.length
        ? el("div", { class: "mmc-ctl-doors" }, doors.map((door) => this.door(door, door === lead)))
        // No piece to send to — the bench was opened without targets. Not a
        // failure and not worth a warning: the file is on the disk under a name
        // the picker lists, which is the whole of what happened.
        : el("span", { class: "mmc-ctl-outnote", text:
            t("Pick it up from the picker whenever you want it.") }),
    );
  }

  /** What the written file is, in the three facts worth having: which tracing
   *  drew it, how long it runs, and the folder to look in. Not a sentence — a
   *  line that reads "Written into the input folder." is a log entry wearing the
   *  clothes of help. */
  outLine() {
    const parts = [t(this.result.op)];
    const span = this.result.kind === "video"
      ? (this.trim ? this.trim.end - this.trim.start : this.cutter?.media?.duration ?? 0)
      : 0;
    if (span > 0) parts.push(formatTime(span));
    parts.push(`input/${this.result.path.split("/").slice(0, -1).join("/")}`);
    return parts.join(" · ");
  }

  /** One door: what it is called, and what happens when it is pressed. */
  door(door, lead) {
    const id = door.target.id;
    const busy = this.sending === id;
    const done = this.sentTo.has(id);
    return el("button", {
      class: `mmc-ctl-door${lead ? " lead" : ""}${done ? " done" : ""}`,
      disabled: Boolean(this.sending) || null,
      onclick: () => this.send(door),
    }, [
      el("span", { class: "mmc-ctl-doorname", text: door.target.label }),
      el("span", { class: "mmc-ctl-doordoes", text: this.doorLine(door, busy, done) }),
    ]);
  }

  doorLine(door, busy, done) {
    // A door that needs a frame says which frame, by the mark on the bar — the
    // one thing somebody would want to check before pressing it, and the one
    // thing they can still go and change.
    if (busy) return t("Tracing that frame…");
    if (done) return t("Sent. The file is in the input folder either way.");
    if (door.frame) return t("The frame at {when}, traced as a still.", { when: formatTime(this.at) });
    // A door that takes either shape says which one it is being handed: a shot
    // aimed at a clip and a shot aimed at one drawing are the same attach and
    // not the same instruction.
    if (this.result?.kind === "image" && door.target.doesStill) return door.target.doesStill;
    return door.target.does ?? "";
  }
}
