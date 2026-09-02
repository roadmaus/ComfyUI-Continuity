// The upscale bench: a finished file in, a bigger one out.
//
// The rest of this pack enlarges things on the way *out of* a render — a first
// pass sampled small and refined, a family's second stage, the LTX re-detail.
// All of those need a piece to be attached to. This is the other question, the
// one anybody with a folder of renders asks eventually: here is a file, make it
// bigger. It does not care which family made it, or whether this pack made it
// at all.
//
// **The room is the tracing bench's room**, deliberately — the same bar, the
// same column of dials on the left, the same light box with a seam through it,
// the same foot that runs the job and says what came of it. Two benches that
// were laid out differently would be two things to learn, and the second one
// would be learned worse.
//
// **What is on the glass is a tile, not the frame.** An upscale is a claim
// about detail, and detail is exactly what does not survive being fitted into a
// light box: a whole 4K frame shown at 900 pixels is a picture of everything
// except the thing being judged. So the glass holds one square of the source at
// the size it will actually come out, and the locator on the left is where that
// square is moved to.
//
// **The other side of the seam is Lanczos, not the source.** Comparing a model
// against the small picture it started from flatters every model ever written —
// of course it is bigger and sharper, it is four times the pixels. The
// comparison worth making is against the same tile blown up with plain
// arithmetic, which is what you would have had for free. That is what is on the
// left of the seam.
//
// **Nothing here runs a model until it is asked to.** The tracing bench redraws
// while a slider is under the pointer because a tracing is arithmetic; every
// backend here is weights, and the first version of this surface fetched a tile
// on every change — so picking *Restore* to read what it was loaded a
// multi-gigabyte checkpoint, took the GPU lock, and made the whole room feel
// stuck behind a job nobody had started. So the left half of the seam follows
// the dials, because it costs a resize, and the right half is a press: **Try
// it** puts the model on this one tile, and moving anything afterwards marks
// what is on the glass as no longer what the dials say.
//
// **The result is a file on a shelf, and it can be handed on from there.** It
// lands in `continuity/upscaled/` in the output folder, beside the renders,
// where the gallery already looks — that is the difference from the tracing
// bench, whose output is an ingredient and lands in `input/`. But a finished
// file is often the next shot's reference, or the picture the next still is
// built on, so the same doors the tracing bench offers are here too. The file
// exists either way; a door only saves the trip through the picker.

import { el, icon, mark, spinner, heldNote, drawFrame, dragsFiles, mountOverlay,
         keepScroll, placeNear, dismissable } from "./dom.js";
import { upscaleBackends, upscalePreviewUrl, upscaleRun, outputUrl, probe, viewUrl,
         upload, uiSetting, patchSettings, primeSettings } from "./api.js";
import { openChoicePopover } from "./pills.js";
import { openPicker } from "./picker.js";
import { formatTime, mountTrim } from "./trim.js";
import { t } from "./i18n.js";
import { api } from "../../../scripts/api.js";
import { busy as queueBusy, watch as watchQueue } from "./queue.js";

/** Where an uploaded source lands — the same shelf the tracing bench uploads
 *  to, because it is the same act: footage brought in from outside to be worked
 *  on, and two folders for it would be two places to look for it afterwards. */
const SUBFOLDER = "continuity/footage";

/** The shelf the finished file lands on, for the line at the foot of the rail.
 *  The server owns it (`outputs.UPSCALED`) and this is the display copy — what
 *  the rail can say before a file exists to be named. */
const SHELF = "continuity/upscaled/";

/** How long the dials wait after the last movement before the tile is asked for
 *  again. Longer than the tracing bench's, because every request here is a model
 *  pass rather than a few milliseconds of arithmetic: a drag across the scale
 *  slider should be one upscale at the end of it, not four on the way. */
const SETTLE_MS = 220;

/** What this machine last picked for each backend. The bench has no piece to
 *  record it in — it writes a file and forgets — so the pick goes where the
 *  pack's other per-machine answers go. See `control.remembered`, which does
 *  the same for the tracings and for the same reason. */
const remembered = () => uiSetting("upscale_weights", {}) ?? {};

function remember(op, picks) {
  patchSettings({ upscale_weights: { ...remembered(), [op]: picks } });
}

/**
 * The stops a dial actually has, drawn under its track — or nothing.
 *
 * Only where there are few enough to count. A dial with forty steps is a
 * continuous one as far as the hand is concerned; a dial with six is a switch
 * wearing a slider's shape, and the ticks are what say so before it is dragged.
 */
function ticks(spec) {
  const steps = Math.round((Number(spec.max) - Number(spec.min)) / Number(spec.step)) + 1;
  if (!Number.isFinite(steps) || steps < 2 || steps > 12) return null;
  return el("div", { class: "mmc-bn-ticks" },
    Array.from({ length: steps }, () => el("span")));
}

/** The bench, or null. One at a time: it is the room. */
let open = null;

/**
 * Open the bench.
 *
 * @param {object} [options]
 * @param {Array}  [options.targets]  where the finished file can be sent:
 *   `[{ id, label, does, kinds, take(result) }]`. Empty is legitimate — the file
 *   is on the shelf and the gallery lists it.
   * @param {Function} [options.back]  where the wordmark goes: called after the
   *   bench closes. Absent means the wordmark is not a door — see `mount`.
 * @param {object} [options.source]  a file to start on, `{path, kind}`
 * @returns {Promise<void>}  resolves when the bench is closed
 */
export function openUpscale(options = {}) {
  open?.close();
  return new Promise((resolve) => {
    open = new Bench(options, resolve);
    open.mount();
  });
}

class Bench {
  constructor(options, resolve) {
    this.resolve = resolve;
    this.targets = options.targets ?? [];
    this.source = options.source ?? null;
    this.back = options.back ?? null;
    this.backends = [];
    this.op = "sharpen";
    // Per backend, so trying Sharpen and coming back to it finds the scale
    // where it was left.
    this.values = {};
    this.seam = 0.5;
    // Which square of the source is on the glass, in 0..1 of the frame. The
    // middle to start with, which is where the subject usually is and always
    // where the eye goes first.
    this.centre = [0.5, 0.5];
    // The source's own pixel size, once something has reported one. Both the
    // locator's square and the readout under the glass are derived from it.
    this.natural = null;
    this.trim = null;
    this.at = 0;
    this.keepSound = true;
    this.hasAudio = false;
    this.busy = false;
    this.progress = null;
    this.result = null;
    // Whether the tile on the right of the seam has landed yet — kept here
    // rather than read back off the element, because it is hidden until it has.
    this.overReady = false;
    // Whether the tile on the glass still answers to the dials as they stand.
    // Moving a dial does not throw the picture away — it is still a real answer
    // to a real question, and the one before it is what you were comparing
    // against — so it stays up and the press that would redo it says so.
    this.stale = false;
    this.trying = false;
    // Which doors this file has already gone through, by target id — a set,
    // because sending is not one press: an upscale can be a shot's reference
    // *and* the picture the next still is built on.
    this.sentTo = new Set();
    // The door whose frame is being cut right now — see `send`.
    this.sending = null;
    this.error = null;
    // Whether a plain tile was asked for while something else had the GPU, and
    // so is owed once the queue drains. One flag, not a list: what is owed is
    // the tile the dials describe *then*.
    this.heldPreview = false;
    // What the queue is doing. See `web/creator/queue.js`.
    this.queue = { remaining: 0, running: false };
  }

  // ---- the room --------------------------------------------------------------

  mount() {
    // The rail: the stops hung off the film edge, and one line at the foot
    // saying which shelf what this makes lands on. See styles/bench.js.
    this.stops = el("div", { class: "mmc-bn-stops" });
    this.bench = keepScroll(el("div", { class: "mmc-bn-rail" }, [
      this.stops,
      el("div", { class: "mmc-bn-where" }, [
        el("b", { text: t("Lands on the shelf") }),
        el("span", { class: "mmc-bn-path", text: `output/${SHELF}` }),
      ]),
    ]));
    this.frame = el("div", { class: "mmc-bn-frame" });
    // Made once and re-adopted by `paintHeld` — the frame it sits in is rebuilt
    // whenever the layers are. The argument is `control.js`'s, and so is the slate.
    this.held = heldNote(
      t("Preview waiting for the render"),
      t("The dials still work. This refreshes as soon as the render is done."));
    this.box = el("div", { class: "mmc-bn-box" }, [this.frame]);
    // Where the trim editor's bar goes, for a clip. Empty for a picture: a still
    // has no span, and an inert bar under one is a control claiming the file has
    // a length.
    // The one press that runs a model on anything less than the whole file. On
    // the box rather than in the foot: what it changes is the picture, and the
    // foot is where the two presses that *write a file* live.
    this.tryButton = el("button", {
      class: "mmc-up-try",
      onpointerdown: (event) => event.stopPropagation(),
      onclick: () => this.tryTile(),
    });
    this.box.append(this.tryButton);
    this.cut = el("div", { class: "mmc-bn-cut" });
    this.foot = el("div", { class: "mmc-bn-foot" });
    this.work = el("div", { class: "mmc-bn-work" }, [this.box, this.cut, this.foot]);

    this.room = el("div", { class: "mmc-bn-room" }, [this.bench, this.work]);
    this.sheet = el("div", { class: "mmc-bn" }, [
      el("div", { class: "mmc-bn-bar" }, [
        // The wordmark is the door, here as much as in the shell — it is the
        // same mark in the same corner, and somewhere that reads as the way out
        // has to be the way out. Pressing it closes the bench and puts the
        // tools back up, so leaving is one press on the thing you already know
        // rather than a hunt for the ✕ at the far end of the bar.
        //
        // Without a `back` it is not a button at all. A bench opened from
        // somewhere with no dashboard behind it would otherwise offer a door
        // onto nothing.
        this.back
          ? el("button", {
              class: "mmc-bn-home", title: t("Back to the tools"),
              onclick: () => { this.close(); this.back(); },
            }, [
              el("span", { class: "mmc-bn-logo" }, [mark(20)]),
              // A product name rather than copy, so it is not translated — the
              // shell writes it the same way.
              el("span", { text: "Continuity" }),
              el("span", { class: "mmc-bn-caret" }, [icon("chevron", 12)]),
            ])
          : el("span", { class: "mmc-bn-mark" }, [
              el("span", { class: "mmc-bn-logo" }, [mark(20)]),
              el("span", { class: "mmc-bn-word", text: "Continuity" }),
            ]),
        el("span", { class: "mmc-bn-slash", text: "/" }),
        el("span", { class: "mmc-bn-here", text: t("Upscale") }),
        el("span", { class: "mmc-bn-gap" }),
        el("button", {
          class: "mmc-close", text: "✕", title: t("Close the bench"),
          onclick: () => this.close(),
        }),
      ]),
      this.room,
    ]);

    this.overlay = el("div", {
      class: "mmc-overlay mmc-bn-over",
      // A file dropped anywhere on the bench is the source — the gesture is
      // "here, work on this", and asking somebody to aim it at a well in the
      // corner is asking them to find the target first.
      // Files only. Every drag inside the page crosses this surface too — the
      // seam is dragged across it a hundred times a session — and a room that
      // lit up as a drop target while its own control was being used was
      // telling the user they were about to drop something they never picked up.
      ondragover: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        this.overlay.classList.add("dropping");
      },
      ondragleave: (event) => { if (event.target === this.overlay) this.overlay.classList.remove("dropping"); },
      ondrop: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        this.overlay.classList.remove("dropping");
        const file = event.dataTransfer?.files?.[0];
        if (file) this.take(file);
      },
    }, [this.sheet]);

    this.unmount = mountOverlay(this.overlay, () => this.close());
    // The queue, watched rather than guessed at: the held tile goes out when
    // nothing else has the GPU, and the run row and Try press say which of them
    // is waiting and which is working.
    let wasBusy = queueBusy();
    this.unwatchQueue = watchQueue((state) => {
      this.queue = state;
      const nowBusy = queueBusy();
      if (!nowBusy && this.heldPreview) {
        // Cleared here rather than inside `askForTile`, which bails on a bench
        // with no source — see `control.js`.
        this.heldPreview = false;
        this.paintHeld();
        this.askForTile();
      }
      // Only when the answer changed: `status` fires on every step of every
      // render, and a repaint per step is not a report, it is a cost.
      if (nowBusy !== wasBusy) {
        wasBusy = nowBusy;
        if (this.overlay.isConnected) { this.paintFoot(); this.paintTry(); }
      }
    });

    this.render();
    this.watchBox();
    this.load();
  }

  async load() {
    try {
      this.backends = await upscaleBackends();
    } catch (error) {
      this.error = String(error.message || error);
    }
    if (!this.overlay.isConnected) return;
    this.op = this.backends[0]?.id ?? this.op;
    this.adopt();
    this.render();
    if (this.source) this.openSource(this.source);
    // The picks live in the settings, which may not have landed yet — the bench
    // can be opened before anything else on the page has asked for them.
    primeSettings(() => {
      if (!this.overlay.isConnected) return;
      this.adopt();
      this.paintBench();
      this.askForTile();
    });
  }

  /**
   * Fill every backend's dials, and its model pick from what this machine last
   * chose.
   *
   * A remembered name is taken only if the file is still on the disk — a model
   * deleted out from under a memory would otherwise be a pick the bench goes on
   * displaying and the server quietly refuses. Anything already dialled wins
   * over both: this runs again whenever the listing is re-read, and it must not
   * undo a choice made since.
   */
  adopt() {
    for (const backend of this.backends) {
      const held = this.values[backend.id] ?? {};
      const kept = remembered()[backend.id] ?? {};
      this.values[backend.id] = Object.fromEntries((backend.params ?? []).map((spec) => {
        if (spec.kind !== "choice") return [spec.key, held[spec.key] ?? spec.default];
        const options = spec.options ?? [];
        const known = [held[spec.key], kept[spec.key]].find((name) => options.includes(name));
        return [spec.key, known ?? spec.default];
      }));
    }
  }

  /** Ask the server again what is on the disk. A model copied into the folder
   *  while the bench is open is the whole reason the catalogue can go stale, and
   *  opening the weights control is the one moment it is being read rather than
   *  displayed. */
  async freshen(onChanged) {
    const before = JSON.stringify(this.backends);
    try {
      this.backends = await upscaleBackends({ fresh: true });
    } catch { return; }
    if (!this.overlay.isConnected) return;
    this.adopt();
    if (JSON.stringify(this.backends) !== before) onChanged?.();
  }

  close() {
    if (open === this) open = null;
    this.unwatchQueue?.();
    clearTimeout(this.settle);
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
   * The result goes with it: a written file that came off different footage is
   * a name in the foot that has nothing to do with what the room is showing.
   */
  openSource(asset) {
    this.source = asset;
    this.result = null;
    this.sentTo.clear();
    this.sending = null;
    this.error = null;
    this.trim = null;
    this.at = 0;
    this.centre = [0.5, 0.5];
    this.stale = false;
    this.trying = false;
    this.hasAudio = false;
    this.natural = null;
    this.sized = false;
    this.cutter?.destroy();
    this.cutter = null;
    if (asset.kind === "video") {
      // The cut and the decoder in one thing, exactly as the tracing bench does
      // it: the clip the bar is already decoding for its playhead is the clip
      // the locator wants a frame of, and two <video> elements over one file
      // would be two downloads answering the same question.
      this.cutter = mountTrim({
        path: asset.path, kind: "video", trim: null, showTrack: false,
        picture: false,
        onFrame: (media) => this.paintLocator(media),
        onChange: ({ trim }) => this.onCut(trim),
      });
      this.cut.replaceChildren(this.cutter.root);
      this.cutter.media.addEventListener("pause", () => this.onPark());
      this.askAboutSound(asset.path);
    } else {
      this.cut.replaceChildren();
    }
    this.render();
    this.askForTile();
  }

  /** Whether this clip has a soundtrack to carry across. Not guessed: no
   *  browser answers it portably, and a silent clip offered a switch is a switch
   *  that does nothing whichever way it is thrown. */
  async askAboutSound(path) {
    const { hasAudio, width, height } = await probe(path);
    if (this.source?.path !== path) return;
    this.hasAudio = hasAudio === true;
    if (width && height && !this.natural) this.natural = { width, height };
    this.paintFoot();
    this.paintBench();
  }

  /** The bar reporting where the cut is now. The span is what will be written;
   *  the playhead is which frame the tile comes out of, and dragging a handle
   *  moves both. */
  onCut(trim) {
    this.trim = trim;
    this.at = this.cutter?.at() ?? 0;
    this.askForTile();
    this.markStale();
    this.paintBench();
  }

  /** The clip stopped. Nothing chases a running clip here — every tile is a
   *  model pass, and a request put in the air at 12 frames a second would land
   *  after the frame it was asked about had gone. So the tile is asked for at
   *  the frame the transport actually stopped on, and nowhere else. */
  onPark() {
    this.at = this.cutter?.at() ?? this.at;
    this.askForTile();
    this.markStale();
  }

  // ---- the backend -------------------------------------------------------------

  backend() {
    return this.backends.find((entry) => entry.id === this.op) ?? null;
  }

  /** Whether the current backend has, on this machine, everything it needs. The
   *  server decides it by looking, so a model dropped into the folder makes the
   *  backend work without anything here learning about it. An unready backend is
   *  still selectable: what somebody needs at that point is to read what is
   *  missing, and a button that refuses the press cannot tell them. */
  ready() {
    return this.backend()?.ready !== false;
  }

  setOp(id) {
    const backend = this.backends.find((entry) => entry.id === id);
    if (!backend || id === this.op) return;
    this.op = id;
    // Reading what a backend is must not run it. The tile that is up came off
    // the other one, so it is stale by definition — and stale is the honest
    // state, not a reason to start a checkpoint load nobody asked for.
    this.markStale();
    // Not the result: a file already written is still a file that exists, and
    // clearing it because a different backend was *selected* would throw away
    // work on the strength of a change nobody has run yet.
    this.render();
    this.askForTile();
  }

  setValue(key, value) {
    this.values[this.op] = { ...this.values[this.op], [key]: value };
    this.askForTile();
    this.markStale();
    this.paintFoot();
  }

  /** The current backend's model picks, as the catalogue declares them. */
  models() {
    return (this.backend()?.params ?? []).filter((spec) => spec.kind === "choice");
  }

  pick(spec) {
    return this.values[this.op]?.[spec.key] ?? "";
  }

  setModel(key, name) {
    this.values[this.op] = { ...this.values[this.op], [key]: name };
    remember(this.op, Object.fromEntries(
      this.models().map((spec) => [spec.key, this.pick(spec)])));
    this.paintBench();
    this.askForTile();
    this.markStale();
  }

  /** How much bigger the result is, as the dials stand. */
  scale() {
    return Number(this.values[this.op]?.scale ?? this.backend()?.params
      ?.find((spec) => spec.key === "scale")?.default ?? 2);
  }

  // ---- the tile ----------------------------------------------------------------

  /**
   * Ask the server for this square, upscaled, under the current dials.
   *
   * Both halves of the seam are asked for together and neither is fetched: they
   * are `<img src>`s, so the browser coalesces the drags, drops the request the
   * last one started and answers out of its own cache when a dial comes back to
   * where it was.
   *
   * The model half is double-buffered — loaded detached and swapped in once it
   * has decoded — because setting `src` on the visible element blanks it for the
   * length of a model pass, and a light box that goes white every time the scale
   * moves is one nothing can be judged on.
   */
  askForTile() {
    // The cheap half only, and never the model. Not gated on `ready()` either:
    // resampling needs no weights, and a bench with no model installed is the
    // one where seeing what you would get for free is worth most.
    if (!this.source) return;
    clearTimeout(this.settle);
    // Held rather than queued while something else has the GPU — the argument
    // is `control.js`'s and is the same one: a tile per drag position, replayed
    // after the render ahead of it, is not what anybody asked for by moving a
    // dial. `jobs.refuse_if_busy` stands under this on the server.
    if (queueBusy()) {
      this.heldPreview = true;
      this.paintHeld();
      return;
    }
    this.heldPreview = false;
    this.paintHeld();
    this.settle = setTimeout(() => this.fetchPlain(), SETTLE_MS);
  }

  /** The held state on the glass. The same two marks the tracing bench puts up,
   *  and for the same reason: the slate says why nothing is arriving, and the
   *  frame goes cold so the tile under it is not read as the answer to the dial
   *  that was just moved. See `control.js`. */
  paintHeld() {
    // Into the frame rather than the box: the frame is the picture's own
    // rectangle — the box is letterboxed around it — and a slate anchored to the
    // box would sit half on the glass and half on the black beside it at any
    // aspect but one. In and out rather than shown and hidden, because
    // `.mmc-bn-held` sets `display` and a class selector beats `[hidden]`; see
    // `heldNote`. Appended on every held paint, since `mountLayers` rebuilds the
    // frame's children and would otherwise drop it.
    if (this.heldPreview) this.frame.appendChild(this.held);
    else this.held.remove();
    this.box.classList.toggle("held", this.heldPreview);
    if (this.heldPreview) this.box.classList.remove("waiting");
  }

  /** The tile as plain arithmetic would enlarge it. A resize on the server and
   *  an `<img src>` here, so the browser coalesces the drags and answers a
   *  setting dragged back to where it was out of its own cache. */
  fetchPlain() {
    if (!this.source || !this.under) return;
    const plain = this.tileUrl({ plain: true });
    if (this.under.src === plain) return;
    // The glass takes its rectangle from whichever half lands first, and until
    // the model has been asked this is the only half there is.
    this.under.onload = () => this.fit(this.under.naturalWidth, this.under.naturalHeight);
    this.under.src = plain;
  }

  tileUrl({ plain = false } = {}) {
    return upscalePreviewUrl(this.source.path, this.op, this.values[this.op] ?? {},
                             { at: this.at, centre: this.centre, plain });
  }

  /** Whether pressing Try would ask for something the glass is not already
   *  showing. False while one is in the air, and on a backend whose weights are
   *  not on this disk. */
  canTry() {
    return Boolean(this.source) && this.ready() && !this.trying
      && (!this.overReady || this.stale);
  }

  /**
   * Put the model on this one tile.
   *
   * A press rather than a consequence of moving something. Every backend here
   * loads weights and takes the GPU lock, so a preview that followed the dials
   * would put a checkpoint load behind a click on a *row* — which is what made
   * choosing between the two backends feel like running one of them.
   *
   * Double-buffered: the answer is decoded detached and swapped in when it is
   * ready, so the half you are comparing against stays on the glass for the
   * length of the pass instead of going white.
   */
  tryTile() {
    if (!this.canTry()) return;
    const url = this.tileUrl();
    this.trying = true;
    this.wanted = url;
    this.error = null;
    this.box.classList.add("waiting");
    this.paintTry();
    const picture = new Image();
    const settle = () => {
      this.trying = false;
      this.box.classList.remove("waiting");
      this.paintTry();
    };
    picture.onload = () => {
      // A slower request that started earlier can land after a faster one that
      // started later. Only the tile that was last asked for goes on the glass.
      if (url !== this.wanted || !this.overlay.isConnected) return;
      this.over.src = url;
      this.overReady = true;
      this.stale = false;
      this.over.style.visibility = "visible";
      this.frame?.classList.remove("solo");
      this.fit(picture.naturalWidth, picture.naturalHeight);
      settle();
    };
    picture.onerror = () => {
      if (url !== this.wanted || !this.overlay.isConnected) return;
      this.error = t("That tile could not be upscaled.");
      settle();
      this.paintFoot();
    };
    picture.src = url;
  }

  /** The dials moved. What is on the glass is still a real answer, so it stays —
   *  and the press that would bring it up to date says which it is. */
  markStale() {
    if (this.overReady) this.stale = true;
    this.paintTry();
  }

  // ---- upscaling the whole file --------------------------------------------------

  /** @param {boolean} frameOnly  one frame out of a clip instead of the cut. */
  async enlarge(frameOnly = false) {
    if (this.busy || !this.source) return;
    this.busy = true;
    this.progress = null;
    this.error = null;
    this.result = null;
    this.paintFoot();
    try {
      this.result = await upscaleRun({
        filename: this.source.path,
        op: this.op,
        params: this.values[this.op] ?? {},
        trim: frameOnly ? null : this.trim,
        at: frameOnly ? this.at : null,
        keep_sound: this.keepSound,
      }, { onProgress: (fraction) => {
        this.progress = fraction;
        if (this.overlay.isConnected) this.paintFoot();
      } });
      this.result.op = this.backend()?.label ?? this.op;
      this.result.scale = this.scale();
      this.sentTo.clear();
    } catch (error) {
      this.error = String(error.message || error);
    }
    this.busy = false;
    this.progress = null;
    if (this.overlay.isConnected) this.paintFoot();
  }

  // ---- drawing ------------------------------------------------------------------

  render() {
    this.paintBench();
    this.paintBox();
    this.paintFoot();
    this.paintTry();
  }

  /**
   * The Try press, in whichever of its three states it is in.
   *
   * Gone when there is nothing to ask for — a tile that is up and still answers
   * the dials needs no button over it, and a backend whose weights are not on
   * this disk has nothing to try. That is the whole of the control: it appears
   * exactly when pressing it would show you something you cannot already see.
   */
  paintTry() {
    if (!this.tryButton) return;
    const backend = t(this.backend()?.label ?? "");
    // A tile is a model pass and is not queued — it is the thing a person is
    // dragging dials against, and it goes behind nothing. So while the queue has
    // the GPU the press is not offered: it would be refused (`jobs.refuse_if_busy`)
    // and a button that fails on principle is worse than one that says why.
    const held = queueBusy();
    this.tryButton.disabled = this.trying || held;
    this.tryButton.replaceChildren(...[
      this.trying || held ? spinner() : null,
      el("span", {
        text: held ? t("Waiting for the render…")
          : this.trying ? t("Trying…")
          : this.overReady ? t("Try it again") : t("Try it here"),
      }),
    ].filter(Boolean));
    this.tryButton.classList.toggle("busy", this.trying || held);
    this.tryButton.title = held
      ? t("This runs once the render ahead of it is done.")
      : t("Runs {backend} on this square alone, so you can see it before spending the file.",
          { backend });
    this.tryButton.style.display = this.canTry() || this.trying || held ? "" : "none";
  }

  /**
   * What the run row says, in whichever of its four states it is in.
   *
   * The fourth is the one the queue brought: a press that has been accepted but
   * is behind somebody else's render is not upscaling yet, and until the queue
   * reaches it there is no progress to report. See `control.js` for the same
   * four states on the other bench.
   */
  runLabel(clip) {
    if (!this.busy) return clip ? t("Upscale the clip") : t("Upscale");
    if (this.progress != null) {
      return t("Upscaling… {percent}%", { percent: Math.round(this.progress * 100) });
    }
    return this.queue.remaining > 1 ? t("Waiting for the render…") : t("Upscaling…");
  }

  /** A titled section of the bench — the same eyebrow the tracing bench and the
   *  shell's columns wear, so the surfaces of this pack are labelled in one
   *  voice. */
  section(title, children) {
    return el("div", { class: "mmc-bn-stop" }, [
      el("div", { class: "mmc-bn-stopname", text: title }),
      ...children.filter(Boolean),
    ]);
  }

  paintBench() {
    const source = this.source;
    this.stops.replaceChildren(
      this.section(t("Source"), [
        source
          ? el("div", { class: "mmc-bn-file" }, [
              el("span", { class: "mmc-bn-filename", text: source.path.split("/").pop(), title: source.path }),
              el("span", { class: "mmc-bn-filenote", text: this.sourceLine() }),
            ])
          : el("p", { class: "mmc-bn-empty", text: t("Nothing on the bench yet.") }),
        el("button", {
          class: "mmc-bn-verb", onclick: () => this.browse(), disabled: this.busy,
        }, [icon("folder", 14), el("span", {
          text: this.busy ? t("Uploading…") : source ? t("Change the file") : t("Choose a file"),
        })]),
      ]),
      this.section(t("Upscaler"), [
        // A row apiece, the same list the tracing bench draws — the choice
        // between backends is a choice between promises about the result, and a
        // promise is read down a column rather than out of a wrapping row.
        el("div", { class: "mmc-bn-list" }, this.backends.map((backend) => el("button", {
          class: `mmc-bn-pick${backend.id === this.op ? " on" : ""}`,
          "aria-pressed": backend.id === this.op,
          title: t(backend.note),
          onclick: () => this.setOp(backend.id),
        }, [
          el("span", { class: "mmc-bn-pickname", text: t(backend.label) }),
          backend.ready === false ? el("span", {
            class: "mmc-bn-pickmark", title: t("Its model is not on this disk yet."),
          }) : null,
        ]))),
        el("p", {
          class: "mmc-bn-note", text: this.backend() ? t(this.backend().note) : "",
          title: t("Press for the rest"),
          onclick: (event) => event.currentTarget.classList.toggle("open"),
        }),
        // What is missing, and only for the backend being looked at. A ring on
        // the row is a dead end on its own; this is the file to download and
        // the folder to put it in.
        this.ready() ? null : el("p", {
          class: "mmc-bn-needs",
          text: t("Not ready. This needs {what}", { what: t(this.backend().needs) }),
          title: t("Press for the rest"),
          onclick: (event) => event.currentTarget.classList.toggle("open"),
        }),
        this.models().length ? el("div", { class: "mmc-bn-weights" }, [this.weightsPill()]) : null,
      ]),
      ...(this.dials().length ? [this.section(t("Dials"), this.dials())] : []),
      ...(source ? [this.section(t("Where to look"), [this.locator()])] : []),
    );
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
        ? t("Not picked yet: {fields}. The upscale is refused without them.",
            { fields: missing.map((spec) => t(spec.label)).join(", ") })
        : t("Which files {backend} runs.", { backend: t(this.backend().label) }),
      onclick: (event) => this.openWeights(event.currentTarget),
    }, [icon("weights", 16), el("span", { text: label })]);
  }

  /** A row per file, each opening the list for its folder — the same popover the
   *  tracing bench and the pre-stage open, because it is the same question. */
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
            find: true,
            options,
            value: held,
            onPick: (picked) => { this.setModel(spec.key, picked); render(); },
          }),
        }),
      ]);
    }));

    pop.append(
      el("div", { class: "mmc-pop-title",
                  text: t("Weights — {backend}", { backend: t(this.backend().label) }) }),
      body,
    );
    render();
    document.body.appendChild(pop);
    placeNear(pop, anchor);
    dismissable(pop);
    this.freshen(() => {
      if (!pop.isConnected) return;
      this.paintBench();
      render();
    });
  }

  /** What the source is, and what it is about to become. The second half is the
   *  point: the one number somebody wants before pressing anything is how big
   *  the file that comes out is going to be. */
  sourceLine() {
    const parts = [];
    const size = this.naturalSize();
    if (size) parts.push(`${size.width}×${size.height}`);
    if (this.source.kind === "video" && this.cutter?.media?.duration) {
      parts.push(formatTime(this.cutter.media.duration));
    }
    if (size) {
      parts.push(`→ ${Math.round(size.width * this.scale())}×${Math.round(size.height * this.scale())}`);
    } else {
      parts.push(this.source.kind === "video" ? t("video") : t("picture"));
    }
    return parts.join(" · ");
  }

  naturalSize() {
    if (this.natural) return this.natural;
    const media = this.cutter?.media;
    if (media?.videoWidth) return { width: media.videoWidth, height: media.videoHeight };
    return null;
  }

  /** The current backend's dials. Built from the server's own spec, which is why
   *  adding a backend over there needs nothing here. */
  dials() {
    const backend = this.backend();
    if (!backend) return [];
    // Model picks are not dials and are not drawn here — see `weightsPill`.
    return (backend.params ?? []).filter((spec) => spec.kind !== "choice").map((spec) => {
      const held = this.values[this.op]?.[spec.key] ?? spec.default;
      if (spec.kind === "switch") {
        return el("label", { class: "mmc-bn-switch", title: t(spec.note) }, [
          el("input", {
            type: "checkbox", checked: held || null,
            onchange: (event) => this.setValue(spec.key, event.target.checked),
          }),
          el("span", { text: t(spec.label) }),
        ]);
      }
      if (spec.kind === "option") {
        // Four short words. A popover to choose between four short words is a
        // door in front of a door, so they are all on the rail as stops.
        return el("div", { class: "mmc-bn-dial", title: t(spec.note) }, [
          el("div", { class: "mmc-bn-diallabel" }, [el("span", { text: t(spec.label) })]),
          el("div", { class: "mmc-bn-opts" }, (spec.options ?? []).map((option) => el("button", {
            class: `mmc-bn-opt${option === held ? " on" : ""}`,
            "aria-pressed": option === held,
            text: t(option),
            onclick: () => { this.setValue(spec.key, option); this.paintBench(); },
          }))),
        ]);
      }
      // How the number reads: a scale is "2×" and a frame count is a count.
      const shown = (value) => (spec.key === "scale" ? `${value}×` : String(value));
      const readout = el("span", { class: "mmc-bn-value", text: shown(held) });
      return el("div", { class: "mmc-bn-dial", title: t(spec.note) }, [
        el("div", { class: "mmc-bn-diallabel" }, [
          el("span", { text: t(spec.label) }), readout,
        ]),
        el("input", {
          type: "range", class: "mmc-bn-range",
          min: String(spec.min), max: String(spec.max), step: String(spec.step),
          value: String(held),
          oninput: (event) => {
            readout.textContent = shown(event.target.value);
            this.setValue(spec.key, Number(event.target.value));
          },
        }),
        ticks(spec),
      ]);
    });
  }

  /**
   * The locator: the whole frame, small, with the square that is on the glass
   * drawn on it.
   *
   * It is here in the column rather than on the glass because the glass has one
   * job — showing the tile at the size it will be — and a second rectangle
   * inside it would take room from exactly the thing being judged. Dragging
   * anywhere on it moves the square, so the gesture is "look there" rather than
   * "find the handle first".
   */
  locator() {
    const shot = this.source.kind === "video"
      ? el("canvas", { class: "mmc-up-locshot", draggable: "false" })
      : el("img", {
          class: "mmc-up-locshot", src: viewUrl(this.source.path, { preview: true }),
          alt: "", draggable: "false",
        });
    if (shot.tagName === "IMG") {
      const sized = () => {
        this.natural = { width: shot.naturalWidth, height: shot.naturalHeight };
        this.paintBench();
      };
      // `complete` as well as the event: a picture already in the browser's
      // cache is decoded before this listener exists, and `load` never fires.
      shot.addEventListener("load", sized);
      if (shot.complete && shot.naturalWidth && !this.natural) sized();
    }
    this.locShot = shot;
    this.locSquare = el("div", { class: "mmc-up-locsquare" });
    const pad = el("div", { class: "mmc-up-loc" }, [shot, this.locSquare]);
    pad.onpointerdown = (event) => this.dragLocator(event, pad);
    pad.ondragstart = (event) => event.preventDefault();
    this.paintSquare();
    if (this.source.kind === "video") this.paintLocator();
    return pad;
  }

  dragLocator(event, pad) {
    event.preventDefault();
    const move = (at) => {
      const box = pad.getBoundingClientRect();
      if (!box.width || !box.height) return;
      this.centre = [
        Math.max(0, Math.min(1, (at.clientX - box.left) / box.width)),
        Math.max(0, Math.min(1, (at.clientY - box.top) / box.height)),
      ];
      this.paintSquare();
      this.askForTile();
      this.markStale();
    };
    move(event);
    pad.setPointerCapture(event.pointerId);
    const up = () => {
      pad.removeEventListener("pointermove", move);
      pad.removeEventListener("pointerup", up);
      pad.removeEventListener("pointercancel", up);
    };
    pad.addEventListener("pointermove", move);
    pad.addEventListener("pointerup", up);
    pad.addEventListener("pointercancel", up);
  }

  /** The square, placed and sized as a share of the frame. The server clamps the
   *  tile to the edges of the picture, so this clamps too — a square drawn half
   *  off the frame would be pointing at pixels the glass is not showing. */
  paintSquare() {
    if (!this.locSquare) return;
    const size = this.naturalSize();
    if (!size) { this.locSquare.style.display = "none"; return; }
    const side = Math.min(384, size.width, size.height);
    const wide = side / size.width;
    const tall = side / size.height;
    this.locSquare.style.display = "";
    this.locSquare.style.width = `${wide * 100}%`;
    this.locSquare.style.height = `${tall * 100}%`;
    this.locSquare.style.left = `${Math.max(0, Math.min(1 - wide, this.centre[0] - wide / 2)) * 100}%`;
    this.locSquare.style.top = `${Math.max(0, Math.min(1 - tall, this.centre[1] - tall / 2)) * 100}%`;
  }

  /** The clip's current frame, drawn into the locator. Called once per displayed
   *  frame by the bar, which is the only thing that knows when there is a new
   *  one. */
  paintLocator(media = this.cutter?.media) {
    if (!media || this.locShot?.tagName !== "CANVAS") return;
    drawFrame(this.locShot, media);
    if (!this.sized && media.videoWidth) {
      this.sized = true;
      this.natural = { width: media.videoWidth, height: media.videoHeight };
      this.paintBench();
      this.askForTile();
    }
  }

  /**
   * The light box: one tile, twice, in one rectangle with a seam through it.
   *
   * Both layers are the same square at the same output size — plain resampling
   * on the left, the model on the right — so the seam is a wipe between two
   * pictures of the same thing rather than a comparison of two sizes. Dragging
   * anywhere on the picture moves it.
   */
  paintBox() {
    if (!this.source) {
      this.frame.replaceChildren(el("div", { class: "mmc-bn-drop" }, [
        icon("image", 40),
        el("p", { class: "mmc-bn-dropline", text: t("Drop a picture or a clip here") }),
        el("p", { class: "mmc-bn-dropnote", text: t("Or choose one from the bench on the left.") }),
      ]));
      this.natural = null;
      this.frame.style.width = this.frame.style.height = "";
      this.box.classList.add("bare");
      return;
    }
    this.box.classList.remove("bare");
    // `draggable="false"` on both halves, and a dragstart stopped on the frame.
    // A pointer that presses an <img> and moves is a drag of the picture as far
    // as the browser is concerned: it lifts a ghost of the tile, offers it to
    // the room's own drop zone, and the seam stops following the hand.
    this.under = el("img", { class: "mmc-bn-layer", alt: "", draggable: "false" });
    this.over = el("img", {
      class: "mmc-bn-layer mmc-bn-over-layer", alt: "", draggable: "false",
      style: { visibility: "hidden" },
    });
    this.overReady = false;
    // Nothing to compare against yet, so the seam and the two tags stay out of
    // the way — a wipe between a picture and an empty layer is a control that
    // does nothing, drawn over the only thing on the glass.
    this.frame.classList.add("solo");
    this.seamEl = el("div", { class: "mmc-bn-seam" }, [
      el("span", { class: "mmc-bn-grip" }, [icon("swap", 14)]),
    ]);
    this.frame.replaceChildren(
      this.under, this.over, this.seamEl,
      // Named for what each half actually is. "Source" would be a lie on the
      // left: the source is a quarter of this size, and what is drawn there is
      // the source resampled — the thing this bench has to beat.
      el("span", { class: "mmc-bn-tag left", text: t("Resized") }),
      this.tagRight = el("span", {
        class: "mmc-bn-tag right", text: t(this.backend()?.label ?? ""),
      }),
    );
    this.frame.onpointerdown = (event) => this.dragSeam(event);
    this.frame.ondragstart = (event) => event.preventDefault();
    this.paintSeam();
    this.paintHeld();
    this.paintTry();
  }

  dragSeam(event) {
    // The press itself is stopped from meaning anything else. Between this and
    // the frame's `dragstart`, there is no path left by which pulling the seam
    // becomes the browser dragging a picture.
    event.preventDefault();
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
    this.frame.style.setProperty("--mmc-seam", `${(this.seam * 100).toFixed(2)}%`);
  }

  /**
   * Size the glass to the tile's own shape.
   *
   * The tile is square at the source's own scale, so what governs is how much
   * room there is: shown larger than 1:1 it would be a magnified picture of a
   * magnified picture, which is a claim about detail that nothing here can back
   * up. So it is never scaled above its own pixels, and shrunk when the room is
   * smaller than they are.
   */
  fit(width, height) {
    if (!width || !height) return;
    this.tile = { width, height };
    const room = this.box.getBoundingClientRect();
    if (!room.width || !room.height) return;
    const scale = Math.min(1, room.width / width, room.height / height);
    this.frame.style.width = `${Math.round(width * scale)}px`;
    this.frame.style.height = `${Math.round(height * scale)}px`;
  }

  /** And again whenever the room changes shape under it. */
  watchBox() {
    this.watcher?.disconnect();
    this.watcher = new ResizeObserver(() => {
      if (this.tile) this.fit(this.tile.width, this.tile.height);
    });
    this.watcher.observe(this.box);
  }

  /**
   * The row that runs the job, and what came of it.
   *
   * Two presses for a clip, not one. The whole cut is the job; the frame under
   * the playhead is the other thing people actually want from a bench like this
   * — one still, at four times the size, out of a shot they like — and it costs
   * one frame instead of the clip's whole render.
   */
  paintFoot() {
    const clip = this.source?.kind === "video";
    const stop = !this.source || this.busy || !this.ready() || null;
    const run = el("button", {
      class: this.busy ? "mmc-bn-run busy" : "mmc-bn-run",
      disabled: stop,
      onclick: () => this.enlarge(false),
    }, [
      this.busy ? spinner() : null,
      el("span", { text: this.runLabel(clip) }),
    ].filter(Boolean));
    // Filtered, not spread with holes: `replaceChildren` takes strings as well
    // as nodes, so a null reaches the document as the word "null".
    this.foot.replaceChildren(...[
      // Only for a clip that has a soundtrack. On by default, unlike the tracing
      // bench's: what comes off this bench is the clip itself, larger, and one
      // that came back mute would be one nobody could use.
      this.hasAudio ? el("label", { class: "mmc-bn-switch", title: t(
        "Carry the clip's own soundtrack into the file this writes. It is copied "
        + "across untouched — nothing here re-encodes what you can hear.") }, [
        el("input", {
          type: "checkbox", checked: this.keepSound || null,
          onchange: (event) => { this.keepSound = event.target.checked; },
        }),
        el("span", { text: t("Keep the sound") }),
      ]) : null,
      el("span", { class: "mmc-bn-gap" }),
      this.error ? el("span", { class: "mmc-bn-bad", text: this.error }) : null,
      clip ? el("button", {
        class: "mmc-bn-second", disabled: stop,
        onclick: () => this.enlarge(true),
        title: t("The one frame under the playhead, as a picture."),
        text: t("This frame at {when}", { when: formatTime(this.at) }),
      }) : null,
      run,
    ].filter(Boolean));
    this.paintResult();
  }

  /**
   * What this source can be handed on as.
   *
   * A clip can be a clip and — through the playhead — any one of its frames. A
   * picture can only ever be a still. It is a fact about the *source*, known
   * the moment it lands, which is why the doors are decided from it rather than
   * from whatever the last press happened to write.
   */
  produces() {
    return this.source?.kind === "video" ? ["video", "image"] : ["image"];
  }

  /** Every door this source can reach, and whether reaching it means upscaling
   *  one frame first. */
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

  /**
   * A door pressed.
   *
   * Most doors take the file that was written. One kind cannot: a pre-stage
   * makes a single picture, so a clip has nothing it can hand over — but the
   * frame under the playhead is a picture, and this bench can make it at the
   * same size with the same weights. So the press upscales that frame first and
   * hands over what comes back, which costs one frame instead of the clip.
   *
   * What goes through the door is the *annotated* path — `… [output]` — because
   * this file is on a shelf in the output folder and everything downstream, from
   * `viewUrl` to `media.resolve`, reads that annotation as the gallery's own.
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
        handed = await upscaleRun({
          filename: this.source.path,
          op: this.op,
          params: this.values[this.op] ?? {},
          at: this.at,
        });
      } catch (error) {
        this.error = String(error.message || error);
        this.sending = null;
        this.paintFoot();
        return;
      }
      this.sending = null;
      if (!this.overlay.isConnected) return;
    }
    door.target.take({ path: `${handed.path} [output]`, kind: handed.kind });
    this.sentTo.add(door.target.id);
    if (door.target.closeOnSend) return this.close();
    this.paintFoot();
  }

  /** One door: what it is called, and what happens when it is pressed. */
  door(door, lead) {
    const id = door.target.id;
    const busy = this.sending === id;
    const done = this.sentTo.has(id);
    return el("button", {
      class: `mmc-bn-door${lead ? " lead" : ""}${done ? " done" : ""}`,
      disabled: Boolean(this.sending) || null,
      onclick: () => this.send(door),
    }, [
      el("span", { class: "mmc-bn-doorname", text: door.target.label }),
      el("span", { class: "mmc-bn-doordoes", text: this.doorLine(door, busy, done) }),
    ]);
  }

  doorLine(door, busy, done) {
    if (busy) return t("Upscaling that frame…");
    if (done) return t("Sent. The file is on the shelf either way.");
    // A door that needs a still says which frame it will make — the one thing
    // somebody would want to check before pressing it, and the one thing they
    // can still go and change.
    if (door.frame) return t("The frame at {when}, upscaled on its own.", { when: formatTime(this.at) });
    return door.target.does ?? "";
  }

  /**
   * The file that was written, where it can go, and how to open it.
   *
   * The doors are the tracing bench's, and they are here for the same reason
   * they are there: the thing you just made is usually wanted somewhere, and
   * the trip through the picker to find it is the part worth saving. What is
   * different is that this file is finished — so opening it is a door too, and
   * on a bench with no piece behind it, the only one.
   */
  paintResult() {
    if (!this.resultRow) {
      this.resultRow = el("div", { class: "mmc-bn-out" });
      this.work.appendChild(this.resultRow);
    }
    if (!this.result) {
      this.resultRow.replaceChildren();
      this.resultRow.classList.remove("on");
      return;
    }
    this.resultRow.classList.add("on");
    const name = this.result.path.split("/").pop();
    const subfolder = this.result.path.split("/").slice(0, -1).join("/");
    const doors = this.doors();
    // The lit one is the door that takes the file exactly as it was written.
    // Where every door wants a frame cut out of a clip, none is lit: there is no
    // obvious next press then, only a choice.
    const lead = doors.find((door) => !door.frame) ?? null;
    this.resultRow.replaceChildren(
      el("div", { class: "mmc-bn-outword" }, [
        el("span", { class: "mmc-bn-outname", text: name }),
        el("span", { class: "mmc-bn-outnote", text: this.outLine() }),
      ]),
      el("span", { class: "mmc-bn-gap" }),
      el("div", { class: "mmc-bn-doors" }, [
        ...doors.map((door) => this.door(door, door === lead)),
        el("a", {
          class: "mmc-up-open", href: outputUrl({ filename: name, subfolder, type: "output" }),
          target: "_blank", rel: "noreferrer", text: t("Open it"),
        }),
      ]),
    );
  }

  /** What the written file is, in the facts worth having: what made it, how much
   *  bigger it is, how long it runs, and the shelf to look on. */
  outLine() {
    const parts = [t(this.result.op), `${this.result.scale}×`];
    const span = this.result.kind === "video"
      ? (this.trim ? this.trim.end - this.trim.start : this.cutter?.media?.duration ?? 0)
      : 0;
    if (span > 0) parts.push(formatTime(span));
    parts.push(`output/${this.result.path.split("/").slice(0, -1).join("/")}`);
    return parts.join(" · ");
  }
}
