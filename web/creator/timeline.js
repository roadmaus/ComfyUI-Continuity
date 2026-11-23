// The timeline modal: a global prompt, one canvas, and a strip of segments.
//
// The strip is the whole idea — cards laid out left to right, each as wide as
// its own duration, with the join between two of them saying whether the second
// cuts or continues. Everything inside a card is a whole generation, so opening
// one hands it to CreatorEditor unchanged: same rail, same @ prompt, same
// LoRAs, same routing badge. There is no reduced "segment UI" to keep in step
// with the node's, because there is only one editor.

import { api } from "../../../scripts/api.js";
import { compiledPrompt, probe, upload, viewUrl, primeSettings, stillUrl, uiSetting } from "./api.js";
import { openRestyle } from "./restyle.js";
import { CastShelf } from "./cast.js";
import { castFamilies, keepAsMod } from "./refmod.js";
import { clearButton } from "./clear.js";
import { dragsFiles, el, icon, mountOverlay } from "./dom.js";
import { CreatorEditor, pickTakes, takesHelp } from "./editor.js";
import { t } from "./i18n.js";
import { settingsHome } from "./slate.js";
import { openLoras, loraBase, settlePins, watchPins } from "./loras.js";
import { openPicker } from "./picker.js";
import { openPresetLibrary, styleCastMember } from "./presetlib.js";
import * as P from "./presets.js";
import { PromptBox, openEditorSheet, focusEnd } from "./prompt.js";
import { openSettings } from "./settings.js";
import { SoundLane } from "./soundlane.js";
import { lane as soundLane } from "./sound.js";
import { openTrim, trimLabel } from "./trim.js";
import { openPicture, editPicture, asPick, cropLabel } from "./picture.js";
import { openAspectPopover, openResolutionPopover, openChoicePopover, facesPill, neuralPill, guideLoraPill,
         resolutionPillText } from "./pills.js";
import { refine, refineButton, RefinePanel, chosenModel as refineModel } from "./refine.js";
import { adopted, blobIO, samplingBar, seedMark, seedPill } from "./sampling.js";
import { Stage, elapsed, failureLead, stageSource } from "./stage.js";
import { cancelPrompt, watchSubmittedPrompts, submittedPrompt, queueNode } from "./queue.js";
import { familyPill, weightsPill, loadCatalog, adoptWeights, rememberedWeights } from "./models.js";
import * as S from "./state.js";
import * as Turbo from "./turbo.js";
import * as Guide from "./guide.js";
import {
  framesForSeconds, secondsForFrames, resolveCanvas, describeRatio,
  rulesFor,
} from "./canvas.js";

/** What the seam picker calls each width, by its place in the family's grid
 *  rather than by the number of frames. The frame counts are the video VAE's
 *  and differ between families — H3's medium blend is 22 frames and LTX 2.5's
 *  is 17 — but "short, medium, long" is what the user is choosing between
 *  either way, and the seconds beside it say what it costs. Keyed on the
 *  numbers, this read "Blend" for every LTX width. */
const BLEND_NAMES = ["None", "Short", "Medium", "Long", "Extra long", "Longest"];

/** A seam blend's width as the user reads it: seconds, one decimal. At the
 *  piece's own rate — the frames were snapped to it. */
const blendSeconds = (frames, rules) => (frames / rules.fps).toFixed(1);

/** Whether a seam's sound tail is decided by its blend rather than by the
 *  piece's setting. Mirrors `compile.compile_request`: a blended seam's sound
 *  and frames are the tail of one source and cover the same instants, so the
 *  blend sets the tail outright. */
const blendSetsTail = (segment, piece) =>
  S.continuesAudio(segment) && S.feather(segment, piece) > 1;

/** The seam's boundary-frame switch, drawn under the width list.
 *
 * A blended seam hands the run in front of it to the DiT as pinned frames; this
 * says whether the *last* of them is also named to the text encoder as a
 * picture. Off by default, because naming it says "arrive at exactly this
 * still" while the run says "carry this motion through" — but naming it is the
 * whole point of an unblended seam, so wanting both is legitimate.
 *
 * Only where the family has a second conditioning channel to say it in
 * (`seam_pin`), and only alongside a blend: at width 1 the boundary frame is
 * the seam and is always named.
 */
/** How the strip names a run of passes a card is shown: their last cards'
 *  numbers, contiguous runs as a range — "#1–3", "#1, #4". The last card,
 *  because that is the number a seam already speaks in (`from #2`) and the
 *  frame a merged run leaves behind. */
function passNumbers(sheet) {
  const numbers = sheet.map(({ pass }) => pass.end);
  const parts = [];
  for (let i = 0; i < numbers.length; i += 1) {
    let j = i;
    while (j + 1 < numbers.length && numbers[j + 1] === numbers[j] + 1) j += 1;
    parts.push(j > i + 1 ? `#${numbers[i]}–${numbers[j]}` : numbers.slice(i, j + 1).map((n) => `#${n}`).join(", "));
    i = j;
  }
  return parts.join(", ");
}

/** filename -> {width, height}, null while a probe is out. Module-level so the
 *  modal bar and the node face — two views of the same strip — measure a file
 *  once between them. Clip cards never land here: they store their own size. */
const ASPECT_SIZES = new Map();
// The source's own size; the framing is applied by whoever reads it — the
// cache is by file, and two chips can frame one file two ways.
const aspectSizeOf = (asset) => ASPECT_SIZES.get(asset.filename) || null;

/** Measure the pictures the timeline's canvas can follow: the resolved source
 *  (or segment 1's anchor under the auto rule), and with `all` every donor the
 *  aspect popover will list. Stills through an <img>, videos through the probe
 *  route; `onReady` re-renders when an answer lands. The backend re-reads the
 *  files at queue time — this is only so the bar can tell the truth early. */
function probeAspectSizes(timeline, onReady, { all = false } = {}) {
  const want = [];
  if (all) {
    for (const segment of timeline.segments) {
      if (!S.isClip(segment)) want.push(...S.aspectDonors(segment));
    }
    for (const asset of timeline.assets ?? []) {
      if (asset.kind !== "audio" && !S.soundOnly(asset)) want.push(asset);
    }
  } else {
    // Just what the bar needs: ask timelineAspectSize what it would read, by
    // reading through a recording lookup.
    S.timelineAspectSize(timeline, (asset) => {
      want.push(asset);
      return aspectSizeOf(asset);
    });
  }
  for (const asset of want) {
    if (ASPECT_SIZES.has(asset.filename)) continue;
    ASPECT_SIZES.set(asset.filename, null);
    if (asset.kind === "video") {
      probe(asset.filename).then(({ width, height }) => {
        if (!width || !height) return;
        ASPECT_SIZES.set(asset.filename, { width, height });
        onReady();
      });
      continue;
    }
    const measure = new Image();
    measure.onload = () => {
      ASPECT_SIZES.set(asset.filename, { width: measure.naturalWidth, height: measure.naturalHeight });
      onReady();
    };
    measure.src = viewUrl(asset.filename);
  }
}

const allDonors = (timeline) => [
  ...timeline.segments.flatMap((s) => (S.isClip(s) ? [] : S.aspectDonors(s))),
  ...(timeline.assets ?? []).filter((a) => a.kind !== "audio" && !S.soundOnly(a)),
];

/** The bar's geometry, source honoured — the mirror of `_timeline_canvas`. */
function timelineGeometry(timeline) {
  const rules = rulesFor(S.pieceFamily(timeline));
  const size = S.timelineAspectSize(timeline, aspectSizeOf);
  const ratio = size ? size.width / size.height
    : rules.aspects.find(([label]) => label === timeline.aspect)?.[1] ?? 16 / 9;
  const [width, height] = resolveCanvas(ratio, timeline.short_edge, rules);
  return { width, height, ratio, fromInput: !!size };
}

/** What the aspect pill's sub-line names as the ratio's source, or null when
 *  the preset rules. */
function aspectSourceLabel(timeline) {
  const source = timeline.aspect_source;
  if (source && typeof source === "object") {
    const card = Number(source.card) || 0;
    if (card && S.isClip(timeline.segments[card - 1])) {
      return t("clip · card {n}", { n: card });
    }
    if (card) return `@${source.handle} · ${t("card {n}", { n: card })}`;
    return `@${source.handle}`;
  }
  const head = timeline.segments[0];
  if (head && !S.isClip(head)
      && (S.frameAsset(head, "first_frame") || S.frameAsset(head, "last_frame"))) {
    return t("from image");
  }
  return t("from clip");
}


/**
 * @param {object} options
 * @param {object} options.timeline    mutated in place
 * @param {() => void} options.onCommit
 * @returns {Promise<void>} resolves when the modal closes
 */
export function openTimeline(options) {
  return new Promise((resolve) => {
    const reel = new Timeline(options, resolve);
    options.opened?.(reel);
    reel.mount();
  });
}

/** A one-line text field that grows to hold what is written in it. */
function fitText(box) {
  if (!box?.style) return;
  box.style.height = "auto";
  if (box.scrollHeight) box.style.height = `${box.scrollHeight}px`;
}

/** The mask a shot comes in through over a blend `width` px wide: slits that
 *  widen until it is all there, the gaps between them dissolving behind. */
function slitMask(width) {
  const count = Math.max(3, Math.round(width / 7));
  const step = width / count;
  const stops = [];
  for (let i = 0; i < count; i += 1) {
    const done = (i + 0.6) / count;
    const gap = 0.55 * done * done * (3 - 2 * done);
    const opens = (i + 1 - done) * step;
    stops.push(`rgba(0, 0, 0, ${gap}) ${i * step}px ${opens}px`, `#000 ${opens}px ${(i + 1) * step}px`);
  }
  return `linear-gradient(90deg, ${stops.join(", ")}, #000 ${width}px)`;
}

/** Whether the caret sits at the end of `root`'s text, with nothing but
 *  whitespace after it — where Enter means "next shot" rather than a line. */
function caretAtEnd(root) {
  const selection = root.ownerDocument.getSelection();
  if (!selection?.rangeCount || !selection.isCollapsed) return false;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.endContainer)) return false;
  const after = root.ownerDocument.createRange();
  after.selectNodeContents(root);
  after.setStart(range.endContainer, range.endOffset);
  return after.toString().trim() === "";
}

/**
 * The finished prompt for the pass holding one card of a piece — what the
 * prompt box's "what the model reads" rail opens onto.
 *
 * It takes the whole piece to compile one shot: the global prompt is folded in,
 * the pool's cited references are merged in front of the card's own, the cast is
 * the piece's, and a run of merged cards is one generation with one description.
 * So this serialises the piece exactly as the node saves it and lets the
 * compiler answer, rather than assembling anything here.
 *
 * `cards` is what turns a card's index into a pass's: on a strip with a merged
 * run in it the two stop being the same number, and showing card 4 the prompt of
 * pass 4 would be showing it somebody else's shot.
 *
 * A function and not a method, because both faces need it and only one of them
 * had it. It was a method on `Timeline`, and `TimelineBody.faceBody` — the
 * lone-shot face, which is most of this node's use — handed the box a hook that
 * looked it up on itself, where it does not exist. Every open of the panel there
 * threw. Out here neither class can have it and the other not.
 *
 * @param {object} timeline  the piece, as the node holds it
 * @param {number} card      which card's pass to answer for
 * @param {number} seed      the piece's seed, the number the node will queue
 */
async function compiledFor(timeline, card, seed) {
  const answer = await compiledPrompt(JSON.parse(S.serializeTimeline(timeline)), seed);
  if (answer.problem) return { problem: answer.problem };

  const index = answer.cards?.[card] ?? 0;
  const pass = answer.passes?.[index];
  if (!pass) return { problem: t("this shot is not in any pass yet") };
  if (pass.clip) {
    // `message`, not `text`: this is the panel talking, not a compiled prompt,
    // and setting it as one would give a sentence of ours a wire key it does
    // not have.
    return { note: t("supplied footage"),
             message: t("This shot is a clip you attached. Nothing is generated for it, so "
                      + "there is no prompt — it is spliced into the piece as it is.") };
  }

  const total = answer.passes.length;
  const held = Object.keys(answer.cards ?? {})
    .filter((key) => answer.cards[key] === index).length;
  const note = [
    total > 1 ? t("pass {n} of {total}", { n: index + 1, total }) : t("one pass"),
    held > 1 ? t("{n} shots merged", { n: held }) : null,
    pass.mode,
    pass.overridden ? t("replaced by hand") : null,
  ].filter(Boolean).join(" · ");
  return { note, text: pass.prompt };
}

class Timeline {
  constructor({ timeline, onCommit, edit = null, io = null, widgets = null, queue = null, stage = null, run = null }, resolve) {
    this.timeline = timeline;
    // The node's stage, for what it says when a render fails. See `failed`.
    this.stage = stage;
    // `{ id, state, cards }` of the node's prompt on the queue, or null.
    this.run = run ?? (() => null);
    // Whether the player follows the render, rather than what is selected.
    this.watching = true;
    // Queue the node this window belongs to: the header's Shoot. Absent where
    // nothing lent it, and then there is no button.
    this.queue = queue;
    // Every write in this window ends here, so this is where a step of its
    // undo is taken. See `record`.
    this.undone = [];
    this.done = [];
    this.onCommit = () => { onCommit?.(); this.record(); };
    this.resolve = resolve;
    // The node's sampler widgets, so a card's preset can carry the row it was
    // dialled at. The modal owns none of them — the sampler belongs to the node,
    // not to one shot — so this is lent by the body that opened the strip. Absent
    // where nothing lent it, and then a speed section simply writes nowhere.
    this.io = io ?? (() => ({ value: (_name, fallback) => fallback, set: () => {} }));
    this.widgets = widgets ?? {};
    // A card to open a window on as soon as the strip is up. Set when the strip
    // was opened *by* growing a shot into it: the new card is where the writing
    // is going, so it opens ready rather than waiting to be found.
    this.openOnMount = edit;
    // The card whose ✕ has been pressed once. Removing a card is the one
    // thing in here that cannot be undone, and its button sits where the strip
    // is scrolled and scrubbed — so it asks twice, the way the library's
    // Delete does, and the arming is forgotten the moment the pointer leaves
    // the card. Never a browser confirm(): see `presetlib.saveCurrent`.
    this.armed = null;
    // The kept takes whose files are not on disk any more. A take is a record
    // on the card and the film is a file under output/, and the two part ways
    // when the folder is cleared out (issue #42): the card still reads as kept,
    // and the render refuses it by name. Filled by `askTakes` as the probes
    // answer, once per filename for the life of the strip — a file put back
    // shows on the next open, and the refusal reads the disk either way.
    this.gone = new Set();
    this.asked = new Set();
  }

  /**
   * Ask the server which kept takes are still on disk.
   *
   * One probe per take, and only the first time the strip sees the name: the
   * answer arrives after the strip has drawn, so a take found missing redraws
   * it once. Nothing is forgotten here — a mounted-later folder or a workflow
   * opened on the wrong machine would lose real film to an automatic ✕ — the
   * chip says so and the pill beside the locks offers to forget them all.
   */
  askTakes() {
    for (const pass of S.passes(this.timeline)) {
      const take = S.takeOn(pass.segments[0]);
      if (!take || this.asked.has(take.filename)) continue;
      this.asked.add(take.filename);
      probe(take.filename).then((answer) => {
        if (!answer.missing || this.gone.has(take.filename)) return;
        this.gone.add(take.filename);
        this.render();
      });
    }
  }

  /** Ask whether each clip has sound: a fact about the file, and older pieces
   *  do not say it. Once per file, when the window opens or a clip arrives. */
  askClips() {
    for (const clip of this.timeline.segments.filter(S.isClip)) {
      if (this.asked.has(clip.filename)) continue;
      this.asked.add(clip.filename);
      probe(clip.filename).then((answer) => {
        if (answer.hasAudio !== false || !this.modal?.isConnected) return;
        let changed = false;
        for (const card of this.timeline.segments) {
          if (S.isClip(card) && card.filename === clip.filename && card.has_audio !== false) {
            card.has_audio = false;
            changed = true;
          }
        }
        if (changed) this.commit();
      }).catch(() => {});
    }
  }

  /** A pin's record changed on another face — a mute in the chat, a strength
   *  on another node: bring this stack's copy in line and write it out. */
  pinsMoved() {
    if (!this.modal?.isConnected) return;
    if (settlePins(this.timeline, S.pieceFamily(this.timeline))) this.commit();
  }

  commit() {
    S.syncTimeline(this.timeline);
    S.releaseRearranged(this.timeline, this.arranged);
    this.arranged = S.arrangement(this.timeline);
    // A kept take of a card that just changed no longer describes it: back in
    // the next render, with everything that follows from it. See `state.reshoot`.
    S.releaseEdited(this.timeline);
    this.refusal = null;
    this.onCommit?.();
    this.render();
    // A handle whose asset just left the pool is no longer a chip, and one
    // whose asset just joined it becomes one. Skipped while the box has the
    // caret, which is exactly when nothing here can have changed.
    this.promptBox?.refresh();
  }

  /**
   * One of the timeline's global text fields.
   *
   * Built once and never re-rendered: a full render would rebuild the element
   * under the caret and lose the selection mid-sentence, which is why `commit`
   * redraws the bar and the strip and leaves these alone.
   */
  textBox(key, { className = "mmc-tl-prompt", placeholder, rows }) {
    const box = el("textarea", {
      class: className,
      placeholder,
      ...(rows ? { rows: String(rows) } : {}),
      oninput: (event) => {
        this.timeline[key] = event.target.value;
        this.wrote(key);
        this.renderBar();
        // The pool shelf reads these fields — a citation typed into the global
        // prompt flips a chip from idle to "everywhere" as it is written. The
        // shelf holds no caret, so rebuilding it here loses nothing.
        this.renderPool();
        this.renderCast();
      },
    });
    box.value = this.timeline[key] ?? "";
    // The canvas is drag-to-pan territory in the graph; a textarea needs its
    // own pointer events.
    box.addEventListener("pointerdown", (event) => event.stopPropagation());
    return box;
  }

  /** The number the node will queue — what every `{day|night}` in the piece
   *  is chosen on. Zero where nothing lent a seed, which is also what the
   *  node's widget starts at. */
  pieceSeed() {
    return Number(this.io().value("seed", 0)) || 0;
  }

  /**
   * The global prompt: the same box a segment's prompt is, chips and all.
   *
   * It was a plain textarea, which made the piece's own references the one
   * place in the pack where "@" did nothing — the pool shelf could write a
   * handle into it but the box could not, and a handle typed by hand stayed
   * grey text. The pool *is* the timeline's attached assets, so `getState`
   * hands the box the timeline itself and the same `@` menu that offers a
   * segment its attachments offers this one the pool, under the pool's own
   * name.
   *
   * Picking a file the pool does not hold yet attaches it to the pool, which is
   * what the "+ Add" button does — the citation then carries it into every
   * segment, which is what a global citation has always meant. Nothing is ever
   * blocked here: the pool takes references and only references, and a start
   * or end frame is a card's business, not the piece's.
   */
  globalPromptBox() {
    const box = new PromptBox({
      getState: () => this.timeline,
      onInput: (text) => {
        this.timeline.prompt = text;
        this.wrote("prompt");
        this.renderBar();
        // A citation typed here flips a pool chip from idle to "everywhere" as
        // it is written. The shelf holds no caret, so rebuilding it here loses
        // nothing — and `renderPool` is why this cannot be a full `render`.
        this.renderPool();
        this.renderCast();
      },
      attachBlocked: () => null,
      attachedLabel: () => t("Piece references"),
      // A `{day|night}` in the standing prompt is chosen once for the whole
      // piece, on the node's seed — a standing description that changed at
      // every cut would not be standing. See `compile.varied_piece`.
      pick: () => ({ seed: this.pieceSeed(), card: "piece" }),
      getCast: () => this.timeline.subjects ?? [],
      onAttach: (row) => this.attachToPool(row),
      castFromLibrary: (member) => this.castFromLibrary(member),
      // The shelf is already in this window, a few rows down — so a name in the
      // standing prompt opens the card that is the whole reason it is there.
      // It was the one prompt box in the pack whose chips did nothing.
      onCastChip: (handle) => this.openCastMember(handle),
      // A look picked out of the `/` menu, onto this window's own piece.
      castStyle: (row) => {
        const subject = P.castIntoPiece(styleCastMember(row, 0), this.timeline);
        this.commit();
        return subject?.handle ?? null;
      },
      // The `/` menu's doors, onto this window's own piece: a style or a cast
      // member chosen here lands on the piece, which is where both belong.
      openLibrary: (scope) => openPresetLibrary({ target: this.pieceTarget(), scope })
        .then(() => { this.renderStrip(); this.renderPool(); this.renderCast(); }),
      onBrowse: () => this.addPoolAssets(),
      // No `onUncited`: a name deleted from the standing prompt leaves the
      // member on the shelf. The shelf's ✕ is what takes them out (#52).
    });
    box.frame.classList.add("mmc-tl-prompt-frame");
    box.frame.addEventListener("pointerdown", (event) => event.stopPropagation());
    return box;
  }

  /** A file picked from the `@` menu, attached to the piece's pool. The same
   *  entry `addPoolAssets` builds, minus the picker's trim and track — those
   *  are the shelf's to set afterwards, and every kind attaches as a reference
   *  because that is the only role a pool asset may have. */
  attachToPool(row) {
    const entry = {
      handle: S.nextPoolHandle(this.timeline),
      kind: row.kind,
      role: "reference",
      filename: row.path,
      ref_size: "max",
    };
    if (row.kind === "video") entry.track = S.trackFor(row);
    this.timeline.assets.push(entry);
    // Not `commit`: the caret is in the box and the chip is about to be written
    // into it, so only the shelf that gained a row is redrawn.
    this.onCommit?.();
    this.renderPool();
    this.renderCast();
    return entry.handle;
  }

  /** The global prompt, in the state and in the box that shows it. The refiner
   *  and the pool shelf both write it from outside the box. */
  setGlobalPrompt(text) {
    this.timeline.prompt = text;
    this.promptBox?.setValue(text);
  }

  mount() {
    this.promptBox = this.globalPromptBox();
    this.promptBox.setValue(this.timeline.prompt ?? "");
    // The scene is the first paragraph of the script: the standing description
    // every shot is written under. Display label only; the key stays `prompt`.
    this.promptBox.root.setAttribute("aria-label", t("Scene"));
    this.promptBox.root.setAttribute("data-placeholder", t("Where it happens, when, and who is in it."));
    this.promptBox.frame.classList.add("mmc-reel-plain");

    // The piece's two audio fields, as lines of the scene rather than boxes:
    // what the room sounds like, and the score only the audience hears. Held
    // rather than built inline: the refiner writes into both.
    this.soundscapeBox = this.textBox("soundscape", {
      className: "mmc-reel-line-text", rows: 1, placeholder: t("Add the sound of the place"),
    });
    this.musicBox = this.textBox("music", {
      className: "mmc-reel-line-text", rows: 1, placeholder: t("Add a score"),
    });
    for (const box of [this.soundscapeBox, this.musicBox]) {
      box.setAttribute("aria-label", box === this.musicBox ? t("Score") : t("Sound"));
      box.addEventListener("input", () => fitText(box));
    }

    watchPins(this, "pinsMoved");
    // The supplied-track machinery: never drawn, only asked to add a track.
    // The reel draws the tracks on its own sound thread.
    this.sound = new SoundLane({
      read: () => this.timeline,
      onCommit: () => this.commit(),
      flash: (message) => this.flash?.(message),
    });

    this.rows = new Map();
    // A shot's refine button and rewrite panel, by card: both outlive a redraw.
    this.refiners = new Map();
    this.refining = new Set();
    this.sel = null;
    // What every pass is made from, as of the last commit: how a reorder is
    // told from an edit. See `state.arrangement`.
    this.arranged = S.arrangement(this.timeline);
    this.titleMeta = el("span", { class: "mmc-reel-meta" });
    this.planEl = el("span", { class: "mmc-reel-plan" });
    this.shootButton = el("button", { class: "mmc-reel-shoot", onclick: () => this.shoot() });
    this.undoButton = el("button", { class: "mmc-reel-step", title: t("Undo (Ctrl+Z)"), disabled: true,
      onclick: () => this.step(this.done, this.undone) }, [icon("rewind", 16)]);
    this.redoButton = el("button", { class: "mmc-reel-step redo", title: t("Redo (Ctrl+Shift+Z)"), disabled: true,
      onclick: () => this.step(this.undone, this.done) }, [icon("rewind", 16)]);
    // Held, not rebuilt: they are repainted on every step, and a button that
    // is replaced under a press loses it.
    this.liveButton = el("button", { class: "mmc-reel-link mmc-reel-live-said", title: t("Watch the render"),
      onclick: () => { this.watching = true; this.renderPlayer(); } });
    this.cancelButton = el("button", { class: "mmc-reel-btn quiet", text: t("Cancel"), hidden: true,
      onclick: () => this.cancel() });
    this.progressBar = el("span", { class: "mmc-reel-progress" });
    this.liveImage = el("img", { class: "mmc-reel-media", alt: "" });
    this.liveMedia = el("div", { class: "mmc-reel-live-media" });
    this.liveLabel = el("span", { class: "mmc-reel-plabel" });
    this.liveRule = el("span", { class: "mmc-reel-live-rule" });
    this.castRow = el("div", { class: "mmc-reel-castrow" });
    this.scriptHost = el("div", { class: "mmc-reel-shots" });
    this.dropMark = el("div", { class: "mmc-reel-drop" });
    this.nextRow = el("div", { class: "mmc-reel-row mmc-reel-next" });
    this.playerHost = el("div", { class: "mmc-reel-player" });
    this.inspectHost = el("div", { class: "mmc-reel-inspect" });
    this.reelHost = el("div", {
      class: "mmc-reel-lane",
      // A video file from outside the page lands as a clip where it is dropped.
      ondragover: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        this.markDrop(this.dropAt(event));
      },
      ondragleave: (event) => { if (!this.reelHost.contains(event.relatedTarget)) this.markDrop(null); },
      ondrop: (event) => {
        if (!dragsFiles(event)) return;
        event.preventDefault();
        event.stopPropagation();
        const at = this.dropAt(event);
        this.markDrop(null);
        this.dropFiles([...event.dataTransfer.files], at?.slot ?? this.timeline.segments.length);
      },
    });
    this.statusHost = el("div", { class: "mmc-reel-status" });
    // Being in the scene's lines is being at the piece: its settings are beside
    // them. A click as well as focus, for a line that kept it.
    const toPiece = () => { if (this.sel) this.select(null); };
    const line = (label, field) => el("div", { class: "mmc-reel-row mmc-reel-quiet", onclick: toPiece, onfocusin: toPiece }, [
      el("span", { class: "mmc-reel-gutter" }, [el("span", { class: "mmc-reel-label", text: label })]),
      field,
    ]);

    this.modal = el("div", { class: "mmc-modal mmc-tl-modal mmc-reel" }, [
      el("div", { class: "mmc-reel-head" }, [
        el("span", { class: "mmc-reel-title", text: t("Timeline") }),
        this.titleMeta,
        this.undoButton,
        this.redoButton,
        this.planEl,
        this.cancelButton,
        ...(this.queue ? [this.shootButton] : []),
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-reel-main" }, [
        el("div", { class: "mmc-reel-script", onclick: (event) => { if (event.target === event.currentTarget) toPiece(); } }, [
          this.castRow,
          el("div", { class: "mmc-reel-row mmc-reel-scene", onclick: toPiece, onfocusin: toPiece }, [
            el("span", { class: "mmc-reel-gutter" }, [el("span", { class: "mmc-reel-label", text: t("Scene") })]),
            this.promptBox.frame,
          ]),
          line(t("Sound"), this.soundscapeBox),
          line(t("Score"), this.musicBox),
          el("div", { class: "mmc-reel-rule" }),
          this.scriptHost,
          this.nextRow,
        ]),
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
    this.toldFailure = this.stage?.failure ?? null;
    // The reel is laid out to the width it has, so a resized window redraws it.
    if (typeof ResizeObserver !== "undefined") {
      this.resize = new ResizeObserver(() => this.renderReel());
      this.resize.observe(this.reelHost);
    }
    if (this.openOnMount != null && this.timeline.segments[this.openOnMount]) {
      this.sel = { kind: "shot", index: this.openOnMount };
    }
    this.render();
    this.now = this.capture();
    fitText(this.soundscapeBox);
    fitText(this.musicBox);
    if (this.openOnMount != null) {
      this.focusShot(this.openOnMount);
      this.openOnMount = null;
    }
  }

  close() {
    this.endDrag?.(false);
    window.removeEventListener("keydown", this.onUndoKey, true);
    this.resize?.disconnect();
    clearTimeout(this.shootTimer);
    this.unmount();
    this.resolve();
  }

  // ---- undo -----------------------------------------------------------------

  capture() {
    return { state: structuredClone(this.timeline), text: S.serializeTimeline(this.timeline) };
  }

  /** A write from a text field: typing in one is one step, until it pauses. */
  wrote(field) {
    this.writing = field;
    this.onCommit();
    this.writing = null;
  }

  /** Take a step, if the piece is not what it was. Writes before the window has
   *  drawn (a family's pins) and those of a step back are not steps. */
  record() {
    if (!this.now || this.stepping) return;
    const text = S.serializeTimeline(this.timeline);
    if (text === this.now.text) return;
    // A sheet over this window writes as it is typed in too.
    const field = this.writing ?? (this.onTop() ? null : "sheet");
    const at = Date.now();
    if (!field || field !== this.lastField || at - this.lastAt > 1500 || this.undone.length) {
      this.done.push(this.now);
      if (this.done.length > 100) this.done.shift();
    }
    this.lastField = field;
    this.lastAt = at;
    this.undone = [];
    this.now = { state: structuredClone(this.timeline), text };
    this.renderSteps();
  }

  renderSteps() {
    this.undoButton.disabled = !this.done.length;
    this.redoButton.disabled = !this.undone.length;
  }

  /** Go to the newest state in `from`, leaving this one in `to`. The piece is
   *  refilled in place: the node holds the same object. */
  step(from, to) {
    if (!from.length || this.endDrag) return;
    to.push(this.now);
    const { state } = from.pop();
    for (const key of Object.keys(this.timeline)) delete this.timeline[key];
    Object.assign(this.timeline, structuredClone(state));
    this.stepping = true;
    this.refiners.clear();   // their toggles hold the rewrite that was there
    this.lastField = null;
    this.armed = null;
    this.refusal = null;
    S.syncTimeline(this.timeline);
    this.arranged = S.arrangement(this.timeline);
    // Only a take that landed since can differ from its card here.
    S.releaseEdited(this.timeline);
    this.promptBox.setValue(this.timeline.prompt ?? "");
    this.onCommit();
    this.render();
    for (const box of [this.soundscapeBox, this.musicBox]) {
      box.value = this.timeline[box === this.musicBox ? "music" : "soundscape"] ?? "";
      fitText(box);
    }
    for (const row of this.rows.values()) {
      if (row.note) { row.note.value = row.segment.prompt ?? ""; fitText(row.note); }
      if (!row.box || row.box.getValue() === (row.segment.prompt ?? "")) continue;
      row.box.setValue(row.segment.prompt ?? "");
      if (document.activeElement === row.box.root) focusEnd(row.box.root);
    }
    this.stepping = false;
    this.now = this.capture();
    this.renderSteps();
  }

  /** A render landed. Film is not a step: going back keeps it on its card, and
   *  it is kept there if it was made from what the card is back to. */
  rebaseSteps() {
    this.now = this.capture();
    const made = S.arrangement(this.timeline);
    for (const snap of [...this.done, ...this.undone]) {
      const then = S.arrangement(snap.state);
      for (const card of this.timeline.segments) {
        const was = snap.state.segments.find((other) => other.card_id === card.card_id);
        if (!was || !S.takeOn(card) || S.takeOn(was)?.filename === card.take.filename) continue;
        was.take = structuredClone(card.take);
        if (S.isHeld(card) && made.get(card.card_id) === then.get(card.card_id)) was.hold = true;
        else delete was.hold;
      }
      snap.text = S.serializeTimeline(snap.state);
    }
  }

  onTop() {
    const open = document.querySelectorAll(".mmc-overlay");
    return open[open.length - 1] === this.overlay;
  }

  undoKey(event) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key !== "z" && key !== "y") return;
    if (!this.onTop()) return;
    // A number being typed into the side has its own.
    if (event.target?.tagName === "INPUT") return;
    const redo = key === "y" || event.shiftKey;
    event.preventDefault();
    event.stopImmediatePropagation();
    // ComfyUI's own undo listens on the window too, perhaps ahead of this, and
    // reads the keys a frame later: it would reload the graph under the window.
    for (const name of ["ctrlKey", "metaKey"]) Object.defineProperty(event, name, { value: false });
    if (redo) this.step(this.undone, this.done); else this.step(this.done, this.undone);
  }

  // ---- render ---------------------------------------------------------------

  render() {
    this.renderLoras();
    this.renderHead();
    this.renderCastRow();
    for (const box of [this.soundscapeBox, this.musicBox]) {
      const key = box === this.musicBox ? "music" : "soundscape";
      if (document.activeElement !== box && box.value !== (this.timeline[key] ?? "")) {
        box.value = this.timeline[key] ?? "";
        fitText(box);
      }
    }
    this.renderStrip();
  }

  /** The family's pins go on before the stack is read; see loras.js. The
   *  stack itself is drawn by the piece's inspector. */
  renderLoras() {
    this.timeline.loras ??= [];
    if (settlePins(this.timeline, S.pieceFamily(this.timeline), () => this.commit())) this.onCommit?.();
  }

  /** The header and, when the piece is what is selected, its inspector: the
   *  two places the piece's own numbers are drawn. */
  renderBar() {
    this.renderHead();
    if (!this.sel) this.renderSide();
  }

  /** The cast and the references are one row now; see `renderCastRow`. */
  renderPool() {
    this.renderCastRow();
    if (this.sel?.kind === "ref" || this.sel?.kind === "cast") this.renderSide();
  }

  renderCast() {
    this.renderPool();
  }

  /** One line of header: how long the piece is, what the next render will do
   *  with it, and the button that does it. */
  renderHead() {
    if (!this.titleMeta) return;
    const seconds = S.timelineSeconds(this.timeline);
    const auto = S.hasAutoDuration(this.timeline);
    const count = this.timeline.segments.length;
    const clips = this.timeline.segments.filter(S.isClip).length;
    const made = count - clips;
    this.titleMeta.textContent = [
      t("{s} s", { s: (auto ? "~" : "") + seconds.toFixed(1) }),
      ...(made || !clips ? [t(made === 1 ? "{n} shot" : "{n} shots", { n: made })] : []),
      ...(clips ? [t(clips === 1 ? "{n} clip" : "{n} clips", { n: clips })] : []),
    ].join(", ");
    const { shoot, kept } = S.shootPlan(this.timeline);
    const shots = shoot.reduce((n, k) => n + S.passes(this.timeline)[k].segments.length, 0);
    const problem = S.stripProblem(this.timeline);
    const said = problem || this.refusal;
    const failure = this.stage?.failure;
    const busy = this.busy();
    this.cancelButton.hidden = !busy;
    this.shootButton.classList.toggle("quiet", busy);
    if (busy) {
      this.liveButton.textContent = this.refusal ? `${this.busyText()}. ${this.refusal}` : this.busyText();
      if (this.liveButton.parentNode !== this.planEl || this.planEl.children.length !== 1) this.planEl.replaceChildren(this.liveButton);
      this.shootButton.textContent = this.shootLabel ?? t("Queue another");
      this.shootButton.title = t("Queue another render behind this one");
      this.shootButton.disabled = Boolean(problem) || !count;
      return;
    }
    this.shootButton.title = "";
    this.planEl.replaceChildren(...(failure && !problem
      ? [el("button", { class: "mmc-reel-link mmc-reel-problem", text: failureLead(failure),
           title: t("Show why"), onclick: () => { this.failureSeen = null; this.playerKey = null; this.renderPlayer(); } })]
      : said
      ? [el("span", { class: "mmc-reel-problem", text: said })]
      : shoot.length
        ? [el("span", { text: t("Next render shoots") + " " }),
           el("b", { text: t(shots === 1 ? "{n} shot" : "{n} shots", { n: shots }) }),
           ...(kept.length ? [el("span", { text: ", " + t("plays") + " " }),
                              el("i", { text: t("{n} kept", { n: kept.length }) })] : [])]
        : [el("span", { text: !count ? t("Nothing in the piece yet.")
            : kept.length ? t("Every shot is kept. The next render puts the piece together.")
              : t("Nothing to shoot. The next render puts your clips together.") })]));
    // With nothing to shoot it still renders: what is kept and what was cut in,
    // as trimmed and ordered now, written out as one piece.
    this.shootButton.textContent = this.shootLabel ?? (count && !shoot.length ? t("Put together") : t("Shoot"));
    this.shootButton.disabled = Boolean(problem) || !count;
  }

  // ---- the render under way --------------------------------------------------

  busy() {
    return Boolean(this.run()) || this.stage?.state === "sampling";
  }

  /** The strip index of the shot being made, or null where nothing has said.
   *  The announce names a card by its number on the strip that was queued. */
  shootingIndex() {
    const stage = this.stage;
    const run = this.run();
    if (!stage || !(stage.state === "sampling" || (run?.state === "running" && stage.segmentPrompt === run.id))) return null;
    const segments = this.timeline.segments;
    if (!stage.segment) return S.passes(this.timeline).length === 1 && !S.isClip(segments[0]) ? 0 : null;
    const id = run?.cards?.[stage.segment - 1];
    const index = id ? segments.findIndex((card) => card.card_id === id) : stage.segment - 1;
    return segments[index] ? index : null;
  }

  busyText() {
    const index = this.shootingIndex();
    if (this.stage?.state === "sampling") {
      const { step, total } = this.stage.progress ?? {};
      return [
        index === null ? t("Rendering") : t("Shooting shot {n}", { n: index + 1 }),
        ...(total ? [`${step} / ${total}`] : []),
        ...(this.stage.startedAt ? [elapsed(Date.now() - this.stage.startedAt)] : []),
      ].join(" · ");
    }
    if (this.run()?.state === "queued") return t("Waiting in the queue");
    return index === null ? t("Getting ready") : t("Getting shot {n} ready", { n: index + 1 });
  }

  /** The stage or the queue has something new to say. */
  staged() {
    if (!this.modal?.isConnected) return;
    if ((this.stage?.failure ?? null) !== (this.toldFailure ?? null)) {
      this.toldFailure = this.stage.failure;
      this.failed();
    }
    // A run that just began is watched from its first word.
    const busy = this.busy();
    if (busy && !this.wasBusy) this.watching = true;
    this.wasBusy = busy;
    this.renderHead();
    this.renderPlayer();
    this.paintShooting();
  }

  /** The pass being made, on the reel and beside its words. */
  paintShooting() {
    const index = this.shootingIndex();
    const row = index === null ? null : this.rowFor(index);
    if (this.shootingRow && this.shootingRow !== row) {
      const was = this.timeline.segments.indexOf(this.shootingRow.segment);
      if (was >= 0) this.updateRow(this.shootingRow, was);
    }
    this.shootingRow = row;
    this.progressBar.remove();
    if (index === null || !this.lay) return;
    const { step, total } = this.stage.progress ?? {};
    if (row) {
      row.tag.className = "mmc-reel-tag shooting";
      row.tag.textContent = total ? t("Shooting, {step} / {total}", { step, total }) : t("Shooting");
    }
    const pass = S.passOf(this.timeline, index);
    const { x, seconds, pps } = this.lay;
    const left = x[pass.start];
    const right = x[pass.end - 1] + seconds[pass.end - 1] * pps;
    this.progressBar.style.left = `${left}px`;
    this.progressBar.style.width = `${right - left}px`;
    this.progressBar.style.setProperty("--done", total ? String(step / total) : "0");
    this.reelHost.querySelector(".mmc-reel-picture")?.append(this.progressBar);
  }

  async cancel() {
    const id = this.run()?.id ?? this.stage?.renderPromptId;
    if (!id) return;
    try { await cancelPrompt(id); } catch (error) { this.refuse(String(error.message || error)); }
  }

  /** The stage's newest frame, in the player. */
  renderLive() {
    const { frame, frameIsClip, progress } = this.stage ?? {};
    if (this.playerKey !== "live") {
      this.playerKey = "live";
      this.liveFrame = undefined;
      this.playerHost.replaceChildren(this.liveMedia, this.liveLabel, this.liveRule);
    }
    this.liveLabel.textContent = this.busyText();
    this.liveRule.style.transform = `scaleX(${progress?.total ? Math.min(1, progress.step / progress.total) : 0})`;
    if (frame === this.liveFrame) return;
    this.liveFrame = frame;
    if (!frame) {
      this.liveMedia.replaceChildren(el("div", { class: "mmc-reel-blank" }, [
        el("span", { text: t("The preview starts here with the first steps.") })]));
    } else if (frameIsClip) {
      const clip = this.stage.previewFrame();
      clip.className = "mmc-reel-media";
      this.liveMedia.replaceChildren(clip);
    } else {
      this.liveImage.src = frame;
      if (this.liveImage.parentNode !== this.liveMedia) this.liveMedia.replaceChildren(this.liveImage);
    }
  }

  /** The stage put a slate up, or took one down. The player shows the same one
   *  until something is selected; the header keeps the way back to it. */
  failed() {
    this.shooting = false;
    this.refusal = null;
    clearTimeout(this.shootTimer);
    this.shootLabel = null;
    this.failureSeen = null;
    this.renderHead();
    this.renderPlayer();
  }

  /** Queue the node this window belongs to, the way its own Render does. */
  shoot() {
    if (!this.queue) return;
    this.refusal = null;
    this.shooting = true;
    this.renderHead();
    this.queue();
  }

  /** The server took the node's prompt: what the press is answered with. */
  accepted() {
    this.staged();
    if (!this.shooting) return;
    this.shooting = false;
    this.shootLabel = t("Queued");
    this.renderHead();
    clearTimeout(this.shootTimer);
    this.shootTimer = setTimeout(() => { this.shootLabel = null; this.renderHead(); }, 2000);
  }

  /** ...or turned it away, and why. Said until the next press or edit. */
  refused(items) {
    if (!this.shooting) return;
    this.shooting = false;
    this.refusal = items.map((item) => item.what).join(" ");
    this.renderHead();
  }

  /** Takes landed on the cards behind this window. A field being typed in on
   *  the side is left standing; it redraws on its own commit. */
  landed() {
    this.rebaseSteps();
    const typing = this.inspectHost?.contains(document.activeElement)
      && document.activeElement.matches("input, textarea, [contenteditable]");
    if (!typing) { this.renderStrip(); return; }
    this.edits = S.editedSince(this.timeline);
    this.askTakes();
    this.renderScript();
    this.renderReel();
    this.renderPlayer();
    this.renderHead();
  }

  // ---- the cast and references row -----------------------------------------

  /** Who and what the piece is made of, as faces and frames above the script.
   *  A member is drawn by their first picture, a reference by its own; each is
   *  selected like a shot, and each is a chip wherever the script names it. */
  renderCastRow() {
    if (!this.castRow) return;
    const assets = S.castAssets(this.timeline);
    const subjects = this.timeline.subjects ?? [];
    const owned = new Set(subjects.flatMap((subject) => S.subjectFiles(subject)));
    const picture = (asset) => (asset && (asset.kind === "image" || asset.kind === "video")
      ? viewUrl(asset.filename, { preview: true }) : null);
    const items = [
      ...subjects.map((subject) => {
        const first = assets.find((asset) => S.subjectFiles(subject).includes(asset.handle));
        const src = picture(first);
        return this.faceWith(() => this.removeMember(subject.handle), t("Take @{handle} out of the piece", { handle: subject.handle }), {
          class: `mmc-reel-face${this.sel?.kind === "cast" && this.sel.handle === subject.handle ? " selected" : ""}`,
          title: t("@{handle}, in the cast", { handle: subject.handle }),
          onclick: () => this.select({ kind: "cast", handle: subject.handle }),
        }, [
          src ? el("img", { src, alt: "", draggable: "false" }) : el("span", { class: "mmc-reel-face-blank" }),
          el("span", { class: "mmc-reel-face-name", text: `@${subject.handle}` }),
        ]);
      }),
      ...(this.timeline.assets ?? []).filter((asset) => !owned.has(asset.handle)).map((asset) => {
        const src = picture(asset);
        return this.faceWith(() => this.removeReference(asset), t("Take @{handle} out of the piece", { handle: asset.handle }), {
          class: `mmc-reel-face frame${this.sel?.kind === "ref" && this.sel.handle === asset.handle ? " selected" : ""}`,
          title: t("@{handle}, a reference", { handle: asset.handle }),
          onclick: () => this.select({ kind: "ref", handle: asset.handle }),
        }, [
          src ? el("img", { src, alt: "", draggable: "false" })
              : el("span", { class: "mmc-reel-face-blank", text: asset.kind === "audio" ? "♪" : "" }),
          el("span", { class: "mmc-reel-face-name", text: `@${asset.handle}` }),
        ]);
      }),
    ];
    const add = el("button", {
      class: "mmc-reel-face-add",
      title: t("Add someone or something to the piece"),
      onclick: (event) => this.addToPiece(event.currentTarget),
    }, [icon("plus", 14)]);
    this.castRow.replaceChildren(...items, add,
      ...(items.length ? [] : [el("span", { class: "mmc-reel-hint", text: t("Who is in it, and what it should look like") })]),
      ...(this.poolError ? [el("span", { class: "mmc-reel-problem", text: this.poolError })] : []));
  }

  /** A face with its ✕, shown on hover or focus; Delete does the same. */
  faceWith(remove, title, props, children) {
    return el("span", { class: "mmc-reel-face-wrap" }, [
      el("button", { ...props, onkeydown: (event) => {
        if (event.key !== "Delete" && event.key !== "Backspace") return;
        event.preventDefault();
        event.stopPropagation();
        remove();
      } }, children),
      el("button", { class: "mmc-reel-x", text: "✕", title, "aria-label": title, onclick: remove }),
    ]);
  }

  // ---- taking things out -------------------------------------------------------
  //
  // One press, and Undo is the way back. Whatever goes takes its mentions with
  // it: a name nothing answers to is refused at the queue.

  everyText() {
    return [this.timeline, ...this.timeline.segments];
  }

  removeMember(handle) {
    const subject = (this.timeline.subjects ?? []).find((s) => s.handle === handle);
    if (!subject) return;
    S.uncite(this.everyText(), handle, handle.replace(/_/g, " "));
    this.promptBox.setValue(this.timeline.prompt ?? "");
    if (this.sel?.handle === handle) this.sel = null;
    // Their files go too, unless another member or a prompt still has them.
    this.castShelfFor().remove(subject);
  }

  removeReference(asset) {
    this.timeline.assets = (this.timeline.assets ?? []).filter((a) => a !== asset);
    S.uncite(this.everyText(), asset.handle);
    S.releaseFromPiece(this.timeline, asset.handle);
    this.promptBox.setValue(this.timeline.prompt ?? "");
    if (this.sel?.handle === asset.handle) this.sel = null;
    this.commit();
  }

  /** One file off a member, and off the piece if nothing else has it. */
  removeMemberFile(subject, asset) {
    S.releaseClaim(subject, asset.handle);
    const claimed = (this.timeline.subjects ?? []).some((s) =>
      S.subjectFiles(s).includes(asset.handle) || S.replacesOf(s).includes(asset.handle));
    if (!claimed && !S.handleWritten(S.allTexts(this.timeline), asset.handle)) {
      for (const host of this.everyText()) {
        if (host.assets) host.assets = host.assets.filter((a) => a !== asset);
      }
    }
    this.commit();
  }

  /** A shot's picture: its own file goes, the piece's is only no longer named
   *  here. Null where this shot has no say: the scene or a member brings it. */
  removerFor(segment, asset) {
    if ((segment.assets ?? []).includes(asset)) {
      return () => {
        segment.assets = segment.assets.filter((a) => a !== asset);
        S.uncite([segment], asset.handle);
        S.releaseFromPiece(this.timeline, asset.handle);
        this.commit();
      };
    }
    if (S.poolCitedGlobally(this.timeline, asset)) return null;
    const own = { texts: [segment.prompt, segment.soundscape, segment.music, segment.refined?.body] };
    if (!S.handleWritten(own.texts, asset.handle)) return null;
    return () => { S.uncite([segment], asset.handle); this.commit(); };
  }

  /** The row's "+": someone from the library, the cast's own card, or a file. */
  addToPiece(anchor) {
    const options = [t("Someone from the library"), t("Someone new"), t("A reference picture, clip or sound")];
    openChoicePopover(anchor, {
      title: t("Add to the piece"),
      options,
      onPick: (choice) => {
        if (choice === options[0]) this.castShelfFor().library?.();
        else if (choice === options[1]) this.openCastSheet(null);
        else this.addPoolAssets();
      },
    });
  }

  /** A name pressed in the script: that member, on the side. */
  openCastMember(handle) {
    if (!(this.timeline.subjects ?? []).some((subject) => subject.handle === handle)) return;
    this.select({ kind: "cast", handle });
  }

  /** The cast's full cards — names, looks, wears, voices, saved latents — as
   *  their own sheet. The row and the inspector show who is in the piece; this
   *  is where a member is built. */
  openCastSheet(handle) {
    const shelf = this.castShelfFor();
    shelf.render();
    openEditorSheet({
      title: t("Cast"),
      subtitle: t("Who is in the piece"),
      content: [shelf.root],
      onClose: () => this.render(),
    });
    if (handle) shelf.openMember(handle, { forceOpen: true });
    else shelf.addSubject();
  }

  /**
   * The cast, in the window: the piece's, built out of the piece's pool.
   *
   * The shelf itself is `cast.js` and is the same one the node face mounts —
   * one node, one cast, one way of editing it. What is the window's is only
   * what it can answer that the shelf cannot: which files there are to build
   * somebody out of, and which cards on the strip write their name.
   *
   * The pool *and* a lone shot's own row, because that is where a piece of one
   * shot keeps its cast's pictures — see `S.castAssets`. Reading the pool alone
   * drew every one of them as a member built out of a file "not attached here",
   * on a piece where the face beside this window shows their photographs.
   */
  castShelfFor() {
    this.castShelf ??= new CastShelf({
      disclosure: true,
      getCast: () => this.timeline.subjects ?? [],
      setCast: (list) => { this.timeline.subjects = list; },
      family: () => S.pieceFamily(this.timeline),
      getAssets: () => S.castAssets(this.timeline),
      addAsset: () => this.attachOneCastAsset(),
      whereCited: (subject) => {
        if (S.subjectCitedGlobally(this.timeline, subject)) {
          return { cited: true, text: t("in every shot") };
        }
        const shots = S.subjectCitations(this.timeline, subject);
        return {
          cited: shots.length > 0,
          text: shots.length
            ? t(shots.length === 1 ? "in shot {list}" : "in shots {list}",
                { list: shots.join(", ") })
            : "",
        };
      },
      // Into the global prompt, which is in front of every shot — the same
      // gesture the pool's own handle button makes, and the answer to "they are
      // in the piece, in all of it".
      cite: (subject) => this.citeName(subject.handle),
      // The roster, both ways — see the same pair on the node face. Casting
      // somebody out of the library attaches their files to the pool, which is
      // the shelf this window is already drawing.
      keep: (subject, assets) => P.keepSubject(subject, assets),
      library: (options = {}) => openPresetLibrary({ target: this.pieceTarget(), scope: "cast", ...options })
        .then(() => { this.renderStrip(); this.renderPool(); this.renderCast(); }),
      // Their pictures as saved latents, landing where the shelf's own "+"
      // lands a picture: the lone shot's row, or the pool.
      mod: (subject, assets, mode, onProgress, family = null) => {
        const single = this.timeline.segments.length === 1;
        const host = single ? this.timeline.segments[0] : this.timeline;
        return keepAsMod(subject, assets, mode, {
          vae: this.timeline.models?.vae ?? "",
          family,
          onProgress,
          list: () => (host.assets ??= []),
          nextHandle: (kind) => (single ? S.nextHandle(host, kind) : S.nextPoolHandle(this.timeline)),
          texts: () => S.allTexts(this.timeline),
          cast: () => this.timeline.subjects ?? [],
          drop: (handles) => {
            for (const owner of [this.timeline, ...(this.timeline.segments ?? [])]) {
              if (owner.assets) owner.assets = owner.assets.filter((a) => !handles.includes(a.handle));
            }
          },
        }).then((rows) => { this.commit(); this.renderStrip(); this.renderPool(); return rows; });
      },
      vae: () => this.timeline.models?.vae ?? "",
      // The families a member's pictures can be saved for, the piece's first.
      families: () => castFamilies(S.pieceFamily(this.timeline), this.timeline.models?.vae ?? "",
                                  rememberedWeights()),
      // The ledger's estimate of a `match` picture is the piece's canvas.
      canvas: () => timelineGeometry(this.timeline),
      // Recasting somebody rewrites every sentence that wrote their name — the
      // piece's own three and each card's, because a member cast into the
      // standing prompt walks on in shots that never mention them by hand.
      // The three global boxes are built once and hold the caret, so a rename
      // made from outside them has to be written back in by hand — the same
      // reason `setGlobalPrompt` exists. A card's own prompt is drawn by the
      // strip, which `commit` redraws.
      rename: (from, to) => {
        S.renameSubjectCitations(
          [this.timeline, ...(this.timeline.segments ?? [])], from, to);
        this.promptBox?.setValue(this.timeline.prompt ?? "");
        if (this.soundscapeBox) this.soundscapeBox.value = this.timeline.soundscape ?? "";
        if (this.musicBox) this.musicBox.value = this.timeline.music ?? "";
      },
      // The pool loses what the departing member alone was built out of. Not a
      // file another shot writes by hand — a pool asset can be cited straight
      // from a prompt without any subject in between, and dropping one would
      // break that sentence.
      //
      // The lone shot's row on the same terms, since that is the other half of
      // what the shelf was built out of.
      dropAssets: (handles) => {
        const texts = S.allTexts(this.timeline);
        const keep = (asset) =>
          !handles.includes(asset.handle) || S.handleWritten(texts, asset.handle);
        this.timeline.assets = (this.timeline.assets ?? []).filter(keep);
        const segments = this.timeline.segments ?? [];
        if (segments.length === 1 && segments[0].assets) {
          segments[0].assets = segments[0].assets.filter(keep);
        }
      },
      // A keystroke in a name or a description: written through, nothing
      // redrawn. The card holds the caret.
      touch: () => this.onCommit?.(),
      commit: () => this.commit(),
    });
    return this.castShelf;
  }

  /**
   * Cast somebody out of the roster, from an `@` typed into any prose in this
   * window — the global prompt or a card's.
   *
   * Their files land in the piece's pool and they land in the piece's cast, which
   * is what the shelf above is already drawing; the caller writes their name where
   * the caret is. Not `commit`: the caret is in a box that is about to receive a
   * chip, so only the two shelves that gained a row are redrawn.
   */
  castFromLibrary(member) {
    const subject = P.addSubjectToPiece(member, this.timeline);
    if (!subject) return null;
    this.onCommit?.();
    this.renderPool();
    this.renderCast();
    this.renderStrip();
    return subject.handle;
  }

  /**
   * The piece, as something a preset can land on — the window's own.
   *
   * The node has one of these already; this window is the same piece with the
   * strip open, and the cast shelf in it needs somewhere to put somebody taken
   * out of the roster. No cover is offered: a cover comes off the stage, the
   * stage belongs to the node, and this window never sees it.
   */
  pieceTarget() {
    return {
      scope: "piece",
      label: t("this piece"),
      // Which family a preset's row and weights would be landing on. Read by
      // `crossable`, which refuses those two sections across families.
      family: () => S.pieceFamily(this.timeline),
      // The VAE a kept member's pictures are encoded through when the library
      // keeps them as RefMods — the piece's own, so a mod made from the roster
      // is the mod a render here would read — and every family this machine
      // could encode for beside it.
      vae: () => this.timeline.models?.vae ?? "",
      families: () => castFamilies(S.pieceFamily(this.timeline), this.timeline.models?.vae ?? "",
                                  rememberedWeights()),
      // What the picker needs to cut a picture out — the scissors ride into
      // the library's own attach flow through this. The pool's spec, because a
      // member's pictures are individual files, not one sheet.
      plate: () => this.poolPlate(),
      capture: () => ({
        data: P.capturePiece(this.timeline, this.io()),
        defaultName: (this.timeline.prompt || this.timeline.segments?.[0]?.prompt || "")
          .trim().split("\n")[0].slice(0, 48),
      }),
      apply: (body, keys, from) => {
        P.applyToPiece(body, keys, this.timeline, this.io(), { from });
        this.commit();
      },
    };
  }

  /** One file, attached for the cast shelf's "attach a file…".
   *  `addPoolAssets` takes several and answers nothing; a subject is being given
   *  one thing, and the shelf needs to know which entry it was.
   *
   *  Onto the pool, or onto a lone shot's own row where that is where the cast's
   *  files live — the same rule `presets.addSubjectToPiece` follows, and for the
   *  same reason: a piece with a pool is not a lone shot any more, so putting a
   *  member's first picture in one would fold the node's face into the strip
   *  summary as the answer to hanging a photograph on somebody. */
  async attachOneCastAsset() {
    const single = this.timeline.segments.length === 1;
    const host = single ? this.timeline.segments[0] : this.timeline;
    const chosen = await openPicker({
      kinds: ["image", "video", "audio", "renders", "refmods"],
      kind: "image",
      capacity: (kind) => (single
        ? S.capacity(host, kind, this.timeline)
        : { used: 0, max: S.refCaps(this.timeline).files, filesLeft: S.refCaps(this.timeline).files }),
      // The scissors ride along: a picture attached while casting somebody is
      // the purest cutout case there is — the `takes` prose already promises
      // the background is dropped, and the chip makes the pixels agree.
      plate: this.poolPlate(),
    });
    if (!chosen?.length) return null;
    const picked = chosen[0];
    if (!Array.isArray(host.assets)) host.assets = [];
    // A cut picture (or a sheet) arrives as a plate: one reference, numbered
    // the way this host numbers — a card's references are img-N, the pool's
    // are ref-N.
    if (picked.plate) {
      const entry = S.plateEntry(picked, S.takenHandles(host),
        single ? {} : { plate: "ref", panel: "ref" });
      host.assets.push(entry);
      this.commit();
      return entry;
    }
    const entry = {
      handle: single ? S.nextHandle(host, picked.kind) : S.nextPoolHandle(this.timeline),
      kind: picked.kind,
      role: "reference",
      filename: picked.path ?? picked.filename,
      ref_size: "max",
    };
    if (picked.trim) entry.trim = picked.trim;
    if (picked.crop) entry.crop = picked.crop;
    if (entry.kind === "video") entry.track = S.trackFor(picked);
    host.assets.push(entry);
    this.commit();
    return entry;
  }

  /** Write a name into the global prompt, so it applies to every shot. The
   *  cast's half of `citeInGlobal`, which does the same for a file. */
  citeName(handle) {
    if (!handle) return;
    const current = this.timeline.prompt ?? "";
    if (new RegExp(`@${handle}\\b`).test(current)) return;
    const joiner = current && !/\s$/.test(current) ? " " : "";
    this.setGlobalPrompt(`${current}${joiner}@${handle} `);
    this.commit();
  }

  /** Write a pool handle into the global prompt — the one-click way to say
   *  "this reference applies to the whole piece". The join then carries the
   *  citation into every segment, which is what attaches the file there. */
  citeInGlobal(asset) {
    if (S.poolCitedGlobally(this.timeline, asset)) return;
    const current = this.timeline.prompt ?? "";
    const joiner = current && !/\s$/.test(current) ? " " : "";
    this.setGlobalPrompt(`${current}${joiner}@${asset.handle} `);
    this.commit();
  }

  /** The plate spec a pool picker gets: the family's, with `sheet` off. The
   *  pool serves many segments — one loose picture per segment is legal even
   *  on a family whose *card* carries one sheet — so multi-select stays loose
   *  and Connect is the deliberate way to build a sheet here. */
  poolPlate(extra = {}) {
    const spec = S.plateSpec(this.timeline, this.frame());
    return spec ? { ...spec, sheet: false, ...extra } : null;
  }

  /** The same picker the segments use, filling the pool instead of a card. */
  async addPoolAssets() {
    const chosen = await openPicker({
      kinds: ["image", "video", "audio", "renders", "refmods"],
      kind: "image",
      // The per-segment reference caps are compile's, applied where a segment
      // actually cites — the pool itself has no ceiling worth enforcing here.
      capacity: () => ({ used: 0, max: S.refCaps(this.timeline).files, filesLeft: S.refCaps(this.timeline).files }),
      plate: this.poolPlate(),
    });
    if (!chosen) return;
    for (const picked of chosen) {
      // A sheet built in the picker lands in the pool as one reference, the way
      // it lands on a card as one — and numbered the pool's way, `ref-N` for
      // the sheet and for every panel on it.
      if (picked.plate) {
        this.timeline.assets.push(S.plateEntry(
          picked, S.takenHandles(this.timeline), { plate: "ref", panel: "ref" }));
        continue;
      }
      this.timeline.assets.push(this.poolEntry(picked));
    }
    this.commit();
  }

  /** One picked file as a pool reference. Its own function because the picker is
   *  no longer the only thing that hands this body a file — see `takeReference`. */
  poolEntry(picked) {
    const entry = {
      handle: S.nextPoolHandle(this.timeline),
      kind: picked.kind,
      role: "reference",
      filename: picked.path,
      // Fidelity is why a reference is attached — same default as the editor.
      ref_size: "max",
    };
    if (picked.kind === "video") entry.track = S.trackFor(picked);
    if (picked.trim) entry.trim = picked.trim;
    if (picked.crop) entry.crop = picked.crop;
    return entry;
  }

  /**
   * A guide off the ControlNet bench, attached where this body keeps references.
   *
   * Which place that is depends on what the body is wearing. A lone shot has an
   * editor and the reference belongs on the card, chip and all, the same as
   * anything the slot buttons attach. A piece on the strip has no single card to
   * attach to and its shared references live in the pool, so that is where this
   * goes — and every segment can then cite it by handle.
   */
  async takeReference(picked) {
    const editor = this.editor;
    if (editor) return editor.attachAssets([picked]);
    this.timeline.assets.push(this.poolEntry(picked));
    this.commit();
  }

  /** Open the sheet editor on a pool sheet, keeping its handle — the pool-side
   *  twin of the editor's `editSheet`, and the same bargain: the pictures that
   *  come back keep the handles and the chips they had, so every segment citing
   *  one still means the picture it meant. Loose picks made in the same session
   *  join the pool as their own references. */
  async editPoolSheet(asset) {
    const spec = this.poolPlate({ edit: true });
    if (!spec) return;
    const chosen = await openPicker({
      kinds: ["image", "renders"],
      kind: "image",
      capacity: () => ({ used: 0, max: S.refCaps(this.timeline).files,
                         filesLeft: S.refCaps(this.timeline).files }),
      plate: { ...spec, panels: (asset.panels?.length
        ? asset.panels.map((panel) => ({ path: panel.filename, cut: Boolean(panel.cut),
            ...(panel.rect ? { rect: [...panel.rect] } : {}),
            ...(panel.points?.length ? { points: panel.points.map((p) => ({ ...p })) } : {}),
            ...(panel.crop ? { crop: { ...panel.crop } } : {}) }))
        : [{ path: asset.filename, cut: false }]) },
    });
    if (!chosen) return;
    this.foldPoolSheet(asset, chosen);
  }

  /** Fold a picker (or scissors) answer back into the pool in `asset`'s place,
   *  keeping its handle — the pool-side twin of the editor's `mergeSheet`,
   *  and the shared tail of Edit sheet…, the chip and the subject view. */
  foldPoolSheet(asset, chosen) {
    const at = this.timeline.assets.indexOf(asset);
    if (at < 0) return;
    const sheet = chosen.find((picked) => picked.plate);
    const loose = chosen.filter((picked) => !picked.plate);
    const kept = new Map((asset.panels ?? []).map((panel) => [panel.filename, panel]));
    if (!asset.panels?.length) kept.set(asset.filename, asset);
    this.timeline.assets.splice(at, 1);
    if (sheet) {
      this.timeline.assets.splice(at, 0, S.plateEntry(
        sheet, S.takenHandles(this.timeline),
        { plate: "ref", panel: "ref", handle: asset.handle, kept }));
    } else {
      // Narrowed to one, or taken apart: the first pick that was a panel steps
      // into the sheet's place and its handle — same rule as the card's.
      const heirAt = loose.findIndex((picked) => kept.has(picked.path));
      if (heirAt >= 0) {
        const [heir] = loose.splice(heirAt, 1);
        const before = kept.get(heir.path);
        this.timeline.assets.splice(at, 0, {
          handle: asset.handle, kind: "image", role: "reference",
          filename: heir.path, ref_size: "max",
          ...(("crop" in heir ? heir.crop : before?.crop)
            ? { crop: "crop" in heir ? heir.crop : before.crop } : {}),
        });
      }
    }
    for (const picked of loose) {
      this.timeline.assets.push({
        handle: S.nextPoolHandle(this.timeline), kind: picked.kind,
        role: "reference", filename: picked.path, ref_size: "max",
        ...(picked.crop ? { crop: picked.crop } : {}),
      });
    }
    this.commit();
    this.renderPool();
  }

  /** The picture editor on a pool picture — the editor's `editPicture`, folded
   *  through the pool's own sheet fold. */
  async editPoolPicture(asset) {
    const { width, height } = this.geometry();
    let answer;
    try {
      answer = await editPicture(asset, {
        plate: this.poolPlate(),
        aspect: width && height ? { ratio: width / height, label: t("canvas") } : null,
        frame: asset.kind === "video" && !S.isRefMod(asset),
      });
    } catch (error) {
      this.poolError = String(error.message || error);
      this.renderPool();
      return;
    }
    if (!answer) return;
    if (answer.frame) return this.usePoolFrame(asset, answer);
    if (asset.kind === "image") {
      this.poolError = null;
      this.foldPoolSheet(asset, [asPick(answer)]);
      return;
    }
    if (answer.crop) asset.crop = answer.crop;
    else delete asset.crop;
    S.dropMods(asset);
    this.commit();
    this.renderPool();
  }

  /** One frame of a pool clip, in the clip's place — the editor's `useFrame`,
   *  pool-side. A pool handle names no kind, so the row keeps it and every
   *  citation with it; what a clip alone can carry — a segment, a soundtrack,
   *  a member's motion or voice — comes off with the clip. */
  usePoolFrame(asset, answer) {
    S.stillForClip(this.timeline, asset, answer.frame.path, answer.crop);
    this.poolError = null;
    this.commit();
    this.renderPool();
  }

  /** Point a pool reference at a different file, keeping its handle — see the
   *  editor's `replaceAsset`, which this is the pool-side twin of. */
  async replacePoolAsset(asset) {
    const chosen = await openPicker({
      kinds: [asset.kind, "renders"],
      kind: asset.kind,
      only: asset.kind,
      single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    const picked = chosen?.[0];
    if (!picked || picked.path === asset.filename) return;
    if (picked.plate) {
      this.foldPoolSheet(asset, chosen);
      return;
    }
    asset.filename = picked.path;
    if (picked.trim) asset.trim = picked.trim;
    else delete asset.trim;
    if (picked.crop) asset.crop = picked.crop;
    else delete asset.crop;
    S.dropMods(asset);
    if (asset.kind === "video") asset.track = S.trackFor(picked);
    this.commit();
  }

  geometry() {
    return timelineGeometry(this.timeline);
  }

  /** The picture this piece is about to make: the canvas, and how long it runs.
   *  For a host that has to draw the frame before there is anything in it —
   *  the fullscreen editor's dock, which is a whole column of nothing until
   *  the first render lands (see fullscreen.js). */
  frame() {
    const { width, height } = this.geometry();
    return { width, height, seconds: S.timelineSeconds(this.timeline) };
  }

  /** The bar's ratio popover: every picture the strip holds is offered as the
   *  canvas's source — any card's frames, references and footage, and the
   *  pool's — with the presets beneath them. */
  openAspect(anchor) {
    const donors = S.timelineAspectSources(this.timeline).map(({ value, card, asset }) => {
      if (S.isClip(asset)) {
        return {
          value, label: t("clip"), tag: null,
          ratio: S.clipSize(asset) ? S.clipSize(asset).width / S.clipSize(asset).height : null,
          sub: t("card {n}", { n: card }),
        };
      }
      const size = S.framedSize(aspectSizeOf(asset), asset.crop);
      const role = asset.role === "first_frame" ? t("start frame")
        : asset.role === "last_frame" ? t("end frame")
        : asset.kind === "video" ? t("reference video") : t("reference image");
      return {
        value, label: `@${asset.handle}`, tag: S.tagIndex(asset.handle),
        ratio: size ? size.width / size.height : null,
        sub: card ? `${role} · ${t("card {n}", { n: card })}` : t("piece reference"),
      };
    });
    const autoSize = S.timelineAspectSize(this.timeline, aspectSizeOf, { ignoreChoice: true });
    openAspectPopover(anchor, this.timeline, () => this.commit(), donors.length ? {
      donors,
      auto: {
        ratio: autoSize ? autoSize.width / autoSize.height
          : rulesFor(S.pieceFamily(this.timeline)).aspects
              .find(([label]) => label === this.timeline.aspect)?.[1] ?? 16 / 9,
        sub: autoSize ? aspectSourceLabel({ ...this.timeline, aspect_source: undefined })
          : this.timeline.aspect,
      },
    } : null);
  }


  /**
   * The seam between two segments, and the only control on it.
   *
   * Continuing means segment N starts on segment N-1's last frame, which makes
   * it a keyframe generation — so it cannot also carry references, and the
   * switch is refused rather than silently dropping them.
   */
  /** Fold the segment at `index` into the pass in front of it. */
  mergeAt(index) {
    if (index < 1) return;
    this.timeline.segments[index].merge = true;
    this.commit();
  }

  /** ...and back out again: the segment at `index` opens its own pass. */
  splitAt(index) {
    delete this.timeline.segments[index].merge;
    this.commit();
  }

  /** The passes that finish before the segment at `index` starts — the ones
   *  whose frames exist by the time this seam is crossed. */
  earlierPasses(index) {
    return S.passes(this.timeline).filter((pass) => pass.end <= index);
  }

  /**
   * How firmly the sheet holds, and what the prompt says carries over (issue
   * #96), under the storyboard pill's three answers.
   *
   * The default holds the room, its light and where things stand, which is
   * what makes objects and tone survive a cut, and also what stands a
   * knocked-over table back up. So the piece can loosen the retention marker,
   * and rewrite the line that goes with it.
   *
   * The box is drawn as the line the model reads, marker first: the marker and
   * the sentence are one statement in `retention_analysis`, and a box holding
   * only the sentence would hide which word it follows. The defaults are the
   * prompt's own words, served in the manifest, so the box starts from what
   * the render would say. Wording equal to the default is stored as nothing,
   * and a line survives changing the hold: it is the user's.
   *
   * Neither control closes the popover. A hold is often picked to be followed
   * by a rewrite, and the rows above close on pick because they are the whole
   * answer.
   */
  storyboardHold() {
    const cap = S.capabilityOf(this.timeline, "storyboard") || {};
    const holds = cap.holds || S.STORYBOARD_HOLDS;
    const defaults = cap.carries || {};
    const words = {
      fully_preserved: [t("Firm"), t("The room, its light and where everything stands. "
        + "Steady across cuts, but things go back to where the sheet shows them.")],
      partially_preserved: [t("Partial"), t("The room and its light. People and things "
        + "move and change as the prompt says.")],
      weak_reference: [t("Loose"), t("Only the broad look of the place and its light. "
        + "The prompt decides the rest, the camera included.")],
    };
    const hold = () => S.storyboardHold(this.timeline);
    const own = () => typeof this.timeline.storyboard_carries === "string"
      && this.timeline.storyboard_carries.trim() !== "";

    // Typing writes the piece at once and commits once it pauses: a commit
    // re-renders the node, which is not a thing to do per keystroke.
    let pending = null;
    const commitSoon = () => {
      clearTimeout(pending);
      pending = setTimeout(() => this.commit(), 400);
    };

    const box = el("textarea", {
      class: "mmc-board-line-text", rows: 4, spellcheck: "false",
      maxlength: cap.max || 400,
      "aria-label": t("What carries over from the storyboard"),
    });
    const marker = el("span", { class: "mmc-board-line-marker" });
    const note = el("span", { class: "mmc-opt-sub mmc-board-hold-note" });
    const reset = el("button", {
      class: "mmc-board-line-reset", text: t("Use the default"),
      onclick: () => {
        delete this.timeline.storyboard_carries;
        draw();
        clearTimeout(pending);
        this.commit();
      },
    });
    const whose = el("span", { class: "mmc-opt-sub" });
    const picks = el("div", { class: "mmc-board-picks mmc-board-holds", role: "radiogroup",
                              "aria-label": t("How firmly the sheet holds") });

    const draw = () => {
      const now = hold();
      picks.replaceChildren(...holds.map((name, index) => el("button", {
        class: "mmc-board-pick mmc-board-hold",
        role: "radio", "aria-checked": name === now,
        title: name,
        onclick: () => {
          if (index === 0) delete this.timeline.storyboard_hold;
          else this.timeline.storyboard_hold = name;
          draw();
          clearTimeout(pending);
          this.commit();
        },
      }, [
        // Strength as bars, strongest first: three, two, one.
        el("span", { class: "mmc-board-hold-bars", "aria-hidden": "true" },
          [0, 1, 2].map((bar) => el("i", { class: bar < holds.length - index ? "on" : "" }))),
        el("span", { text: words[name]?.[0] ?? name }),
      ])));
      note.textContent = words[now]?.[1] ?? "";
      marker.textContent = `${now} -`;
      if (!own()) box.value = defaults[now] ?? "";
      else if (document.activeElement !== box) box.value = this.timeline.storyboard_carries;
      reset.hidden = !own();
      whose.textContent = own() ? t("Your wording") : "";
    };

    box.oninput = () => {
      const text = box.value;
      const same = text.split(/\s+/).join(" ").trim() === (defaults[hold()] ?? "");
      if (!text.trim() || same) delete this.timeline.storyboard_carries;
      else this.timeline.storyboard_carries = text;
      reset.hidden = !own();
      whose.textContent = own() ? t("Your wording") : "";
      commitSoon();
    };

    draw();
    return el("div", { class: "mmc-twopass mmc-board-hold-sect" }, [
      el("div", { class: "mmc-opt-label mmc-opt-col mmc-board-hold-head" }, [
        el("span", { text: t("How firmly the sheet holds") }),
        note,
      ]),
      picks,
      el("label", { class: "mmc-board-line" }, [marker, box]),
      el("div", { class: "mmc-board-line-foot" }, [whose, reset]),
    ]);
  }

  // ---- the reel ---------------------------------------------------------------
  //
  // One window, three views of one piece, kept in step: the script (the scene
  // and a paragraph a shot), the reel (the shots at their real length, the
  // joins between them, the sound under them) and the side (the player, and
  // the inspector for whatever is selected — the piece itself when nothing is).

  /** Everything that shows the strip, without touching a box under the caret.
   *  The name is the old strip's: the editor, the presets and the shelves call
   *  it when a card changed under them. */
  renderStrip() {
    if (!this.scriptHost) return;
    this.edits = S.editedSince(this.timeline);
    this.askTakes();
    this.askClips();
    this.renderScript();
    this.renderReel();
    this.renderSide();
    this.renderHead();
  }

  /** A keystroke in the script: the card changed, so a kept take of it may have
   *  stopped describing it. Lighter than `commit` — the row under the caret is
   *  left alone. */
  scriptEdited(card) {
    S.releaseEdited(this.timeline);
    this.wrote(card);
    this.renderCastRow();
    this.renderStrip();
  }

  select(sel, { reveal = true } = {}) {
    this.sel = sel;
    this.watching = !sel;
    this.failureSeen = this.stage?.failure ?? null;
    this.armed = null;
    this.keepRefused = null;
    this.renderCastRow();
    this.renderStrip();
    if (reveal && sel?.kind === "shot") {
      this.rowFor(sel.index)?.el.scrollIntoView({ block: "nearest" });
    }
  }

  rowFor(index) {
    const segment = this.timeline.segments[index];
    return segment ? this.rows.get(segment.card_id) : null;
  }

  focusShot(index) {
    const row = this.rowFor(index);
    if (!row?.box) return;
    row.el.scrollIntoView({ block: "nearest" });
    focusEnd(row.box.root);
  }

  /** What the reel says about a shot's film: the pass's, because a pass is one
   *  generation and one take. */
  shotState(index) {
    const segment = this.timeline.segments[index];
    if (S.isClip(segment)) return "clip";
    const pass = S.passOf(this.timeline, index);
    const head = pass.segments[0];
    const take = S.takeOn(head);
    if (take && this.gone.has(take.filename)) return "gone";
    if (take && S.isHeld(head)) return "kept";
    if (take) return this.edits?.has(pass.start) ? "changed" : "reshoot";
    return "new";
  }

  /** The word a shot wears — only when it is not what a shot is by default.
   *  Kept is the default once a piece has been shot, and not shot is drawn by
   *  the card itself, so neither is said. */
  stateTag(state) {
    return { changed: t("Changed, reshoots"), reshoot: t("Reshoots"), gone: t("File missing") }[state] ?? "";
  }

  // ---- the script ---------------------------------------------------------

  renderScript() {
    const live = new Set();
    const els = this.timeline.segments.map((segment, index) => {
      live.add(segment.card_id);
      let row = this.rows.get(segment.card_id);
      if (!row || row.clip !== S.isClip(segment)) {
        row = this.scriptRow(segment);
        this.rows.set(segment.card_id, row);
      }
      row.segment = segment;
      this.updateRow(row, index);
      return row.el;
    });
    for (const id of [...this.rows.keys()]) if (!live.has(id)) this.rows.delete(id);
    const now = [...this.scriptHost.children];
    if (now.length !== els.length || now.some((node, i) => node !== els[i])) {
      this.scriptHost.replaceChildren(...els);
    }
    // The paragraph after the last: where the next shot is written.
    const next = this.timeline.segments.length + 1;
    const refused = S.addSegmentRefusal(this.timeline);
    this.nextRow.replaceChildren(
      el("span", { class: "mmc-reel-gutter" }, [el("span", { class: "mmc-reel-num ghost", text: String(next) })]),
      el("div", { class: "mmc-reel-next-body" }, [
        el("button", {
          class: "mmc-reel-ghost",
          text: next === 1 ? t("Write the first shot") : t("Write the next shot"),
          title: refused ?? "",
          disabled: refused ? true : undefined,
          onclick: () => this.insertShot(this.timeline.segments.length),
        }),
        el("button", {
          class: "mmc-reel-ghost small",
          text: next === 1 ? t("or start with a clip you already have") : t("or add a clip you already have"),
          disabled: refused ? true : undefined,
          onclick: () => this.addClip(this.timeline.segments.length),
        }),
      ]),
    );
  }

  /** One shot's row: its number and length in the gutter, its words in the same
   *  box a card's prompt always was, chips and menus included, set as text. */
  scriptRow(segment) {
    const row = { segment, clip: S.isClip(segment) };
    const index = () => this.timeline.segments.indexOf(row.segment);
    row.number = el("button", {
      class: "mmc-reel-num",
      title: t("Select this shot"),
      onclick: () => this.select({ kind: "shot", index: index() }),
    });
    row.seconds = el("span", { class: "mmc-reel-secs" });
    row.tag = el("span", { class: "mmc-reel-tag" });
    if (row.clip) {
      row.body = el("button", {
        class: "mmc-reel-clipname",
        onclick: () => this.select({ kind: "shot", index: index() }),
      });
      row.note = el("textarea", {
        class: "mmc-reel-line-text", rows: 1,
        placeholder: t("What happens in this clip, for rewriting the shots beside it"),
        "aria-label": t("What happens in this clip"),
        oninput: () => {
          row.segment.prompt = row.note.value;
          fitText(row.note);
          this.scriptEdited(row.segment.card_id);
        },
        onfocus: () => {
          if (!(this.sel?.kind === "shot" && this.sel.index === index())) {
            this.select({ kind: "shot", index: index() }, { reveal: false });
          }
        },
      });
      row.note.value = segment.prompt ?? "";
      row.name = row.body;
      row.body = el("div", { class: "mmc-reel-words" }, [row.note, row.name]);
    } else {
      row.box = new PromptBox({
        getState: () => row.segment,
        getPool: () => this.timeline.assets ?? [],
        placeholder: t("What happens in this shot"),
        onInput: (text) => { row.segment.prompt = text; this.scriptEdited(row.segment.card_id); },
        onAttach: (picked) => this.attachToPool(picked),
        attachBlocked: (action) => S.blockedReason(row.segment, action),
        getCast: () => this.timeline.subjects ?? [],
        castFromLibrary: (member) => this.castFromLibrary(member),
        onCastChip: (handle) => this.openCastMember(handle),
        pick: () => ({ seed: S.segmentSeed(row.segment) ?? this.pieceSeed(), card: index() + 1 }),
        // Enter at the end of a shot starts the next one; anywhere else it is
        // still a line break, and Shift+Enter always is.
        onSubmit: () => {
          if (caretAtEnd(row.box.root)) { this.insertShot(index() + 1); return; }
          row.box.insertText("\n");
          row.box.onEdit();
        },
      });
      row.box.setValue(segment.prompt ?? "");
      row.box.frame.classList.add("mmc-reel-plain");
      // In the capture phase, after the box's own: the box stops the event
      // there, which in Chromium also keeps it from this element's bubble phase.
      row.box.root.addEventListener("keydown", (event) => this.scriptKey(event, row), true);
      row.box.root.addEventListener("focus", () => {
        if (!(this.sel?.kind === "shot" && this.sel.index === index())) {
          this.select({ kind: "shot", index: index() }, { reveal: false });
        }
      });
      row.useClip = el("button", {
        class: "mmc-reel-ghost small mmc-reel-useclip",
        onclick: () => this.addClip(index(), { replace: true }),
      });
      row.refine = el("button", { class: "mmc-reel-ghost small", onclick: () => this.refineShot(row.segment.card_id) });
      row.rewritten = el("button", { class: "mmc-reel-ghost small mmc-reel-rewritten",
        onclick: () => this.select({ kind: "shot", index: index() }) });
      row.body = el("div", { class: "mmc-reel-words" }, [row.box.frame, row.rewritten,
        el("div", { class: "mmc-reel-offers" }, [row.refine, row.useClip])]);
    }
    row.gutter = el("span", {
      class: "mmc-reel-gutter mmc-reel-handle",
      title: t("Drag to move it"),
      onpointerdown: (event) => this.dragCard(event, row.segment),
    }, [row.number, row.seconds]);
    row.el = el("div", {
      class: "mmc-reel-row mmc-reel-shot",
      onpointerdown: (event) => event.stopPropagation(),
    }, [
      // The gap above the row: anything can be put in front of any shot, the
      // first included.
      el("div", { class: "mmc-reel-gap" }, [
        el("button", { class: "mmc-reel-gap-add", text: t("Shot here"), title: t("Write a shot here"),
          onclick: () => this.insertShot(index()) }),
        el("button", { class: "mmc-reel-gap-add", text: t("Clip here"), title: t("Put a clip you already have here"),
          onclick: () => this.addClip(index()) }),
      ]),
      row.gutter,
      row.body,
      row.tag,
    ]);
    return row;
  }

  updateRow(row, index) {
    const segment = row.segment;
    const seconds = S.isClip(segment) ? S.clipSeconds(segment) : Number(segment.duration_s) || 0;
    row.number.textContent = String(index + 1);
    row.seconds.textContent = t("{s} s", { s: S.showSeconds(seconds) });
    const state = this.shotState(index);
    row.tag.textContent = this.stateTag(state);
    row.tag.className = `mmc-reel-tag ${state}`;
    row.el.classList.toggle("selected", this.sel?.kind === "shot" && this.sel.index === index);
    row.el.classList.toggle("merged", index > 0 && S.merged(segment));
    if (row.clip) {
      row.name.textContent = t("A clip you added: {name}", { name: (segment.filename || "").split("/").pop() });
      if (document.activeElement !== row.note) row.note.value = segment.prompt ?? "";
      fitText(row.note);
    } else if (document.activeElement !== row.box.root
               && row.box.getValue() !== (segment.prompt ?? "")) {
      // Written from outside the row — a refine, a preset — while it had no caret.
      row.box.setValue(segment.prompt ?? "");
    }
    if (row.useClip) {
      // On a written shot only where it is selected: the words stay and the
      // clip stands in for the film.
      const blank = S.blankShot(segment);
      row.useClip.hidden = !blank && !(this.sel?.kind === "shot" && this.sel.index === index);
      const busy = this.refining.has(segment.card_id);
      const written = Boolean((segment.prompt || "").trim());
      row.refine.hidden = !busy && (!written || row.useClip.hidden);
      row.refine.disabled = busy;
      row.refine.textContent = busy ? t("Refining…") : segment.refined?.body ? t("refine again") : t("refine");
      // The rewrite is what is queued, so a row says when its words are not.
      const replaced = Boolean(S.refinedBody(segment));
      row.box.frame.classList.toggle("mmc-reel-stood-in", replaced);
      row.rewritten.hidden = !replaced;
      row.rewritten.textContent = (segment.refined?.source ?? "") === (segment.prompt ?? "")
        ? t("The model reads a rewrite of this") : t("The model reads a rewrite from before you changed this");
      row.useClip.textContent = !blank ? t("use a clip for this shot") : index ? t("or use a clip you already have") : t("or start with a clip you already have");
    }
  }

  /** Backspace in an empty shot takes it out again, as long as nothing but
   *  the words would go with it. (Enter is the box's `onSubmit`.) */
  scriptKey(event, row) {
    if (event.defaultPrevented || row.box.menu || event.isComposing) return;
    const index = this.timeline.segments.indexOf(row.segment);
    if (event.key === "Backspace" && !(row.segment.prompt ?? "").trim()
        && this.timeline.segments.length > 1 && !S.takeOn(row.segment)
        && !S.references(row.segment).length) {
      event.preventDefault();
      this.remove(index);
      this.focusShot(Math.max(0, index - 1));
    }
  }

  /** A new shot at `at`, continuing from the one before it, with the caret in it. */
  insertShot(at) {
    if (S.addSegmentRefusal(this.timeline)) return;
    const segment = at === 0 ? S.emptySegment() : S.continuingSegment(this.timeline);
    // Between two shots of one pass it is one of them, rather than a split.
    const after = this.timeline.segments[at];
    if (at && after && S.merged(after)) segment.merge = true;
    this.placeSegment(segment, at);
    this.focusShot(at);
  }

  /** Put a card in at `at`, every seam that names a later one following it. */
  placeSegment(segment, at) {
    this.timeline.segments.splice(at, 0, segment);
    S.remapContinueFrom(this.timeline, (n) => (n > at ? n + 1 : n));
    S.ensureCardIds(this.timeline);
    this.sel = { kind: "shot", index: at };
    this.commit();
  }

  // ---- moving cards ----------------------------------------------------------

  /** Where a drop at the pointer would land: `{ slot, on }`, the slot counted
   *  as the gap in front of card `slot`, or null off both surfaces. */
  dropAt({ clientX, clientY }) {
    const inside = (node) => {
      const box = node.getBoundingClientRect();
      return clientX >= box.left && clientX <= box.right && clientY >= box.top && clientY <= box.bottom;
    };
    const count = (nodes, before) => nodes.filter((node) => before(node.getBoundingClientRect())).length;
    if (inside(this.reelHost)) {
      return { on: "reel", slot: count([...this.reelHost.querySelectorAll(".mmc-reel-card")],
        (box) => box.left + box.width / 2 < clientX) };
    }
    if (inside(this.scriptHost.parentElement)) {
      return { on: "script", slot: count([...this.scriptHost.children].filter((node) => node !== this.dropMark),
        (box) => box.top + box.height / 2 < clientY) };
    }
    return null;
  }

  /** The line where a drop would land, on both surfaces' terms; null clears. */
  markDrop(at) {
    const mark = this.dropMark;
    mark.remove();
    if (!at) return;
    const n = this.timeline.segments.length;
    mark.className = `mmc-reel-drop ${at.on}`;
    if (at.on === "reel") {
      const picture = this.reelHost.querySelector(".mmc-reel-picture");
      const { x, seconds, pps } = this.lay;
      const edge = at.slot < n ? x[at.slot] : n ? x[n - 1] + seconds[n - 1] * pps : 0;
      mark.style.cssText = `left:${Math.max(2, Math.min(edge, picture.clientWidth - 2))}px`;
      picture.append(mark);
    } else {
      const row = this.rowFor(Math.min(at.slot, n - 1))?.el;
      const top = row ? (at.slot < n ? row.offsetTop : row.offsetTop + row.offsetHeight) : 0;
      mark.style.cssText = `top:${top}px`;
      this.scriptHost.append(mark);
    }
  }

  /** Drag a card by its place on the reel or its number in the script, and put
   *  it down on either. A press that does not travel is still a click. */
  dragCard(event, segment) {
    if (event.button !== 0 || this.endDrag || this.timeline.segments.length < 2) return;
    const x0 = event.clientX;
    const y0 = event.clientY;
    const script = this.scriptHost.parentElement;
    let at = null;
    let ghost = null;
    let last = event;
    let frame = 0;
    const paint = () => {
      const left = Math.min(last.clientX + 12, window.innerWidth - ghost.offsetWidth - 8);
      const top = Math.min(last.clientY + 12, window.innerHeight - ghost.offsetHeight - 8);
      ghost.style.transform = `translate(${left}px, ${top}px)`;
      const from = this.timeline.segments.indexOf(segment);
      at = this.dropAt(last);
      // Either side of where it already stands is nowhere.
      if (at && (at.slot === from || at.slot === from + 1)) at = null;
      this.markDrop(at);
    };
    // Held near the top or bottom of the script, the script scrolls.
    const scroll = () => {
      const box = script.getBoundingClientRect();
      if (last.clientX >= box.left && last.clientX <= box.right) {
        const step = last.clientY > box.top && last.clientY < box.top + 48 ? -8
          : last.clientY < box.bottom && last.clientY > box.bottom - 48 ? 8 : 0;
        if (step) { script.scrollTop += step; paint(); }
      }
      frame = requestAnimationFrame(scroll);
    };
    const move = (e) => {
      if (e.pointerId !== event.pointerId) return;
      last = e;
      if (!ghost) {
        if (Math.hypot(e.clientX - x0, e.clientY - y0) < 6) return;
        const n = this.timeline.segments.indexOf(segment) + 1;
        const name = (S.isClip(segment) ? (segment.filename || "").split("/").pop() : segment.prompt || "").trim();
        ghost = el("div", { class: "mmc-reel-ghostcard" }, [
          el("b", { text: String(n) }), el("span", { text: name || t("No words yet") })]);
        this.modal.classList.add("mmc-reel-dragging");
        this.overlay.append(ghost);
        this.overlay.ownerDocument.getSelection()?.removeAllRanges();
        scroll();
      }
      e.preventDefault();
      paint();
    };
    const key = (e) => {
      if (e.key !== "Escape" || !ghost) return;
      e.preventDefault();
      e.stopPropagation();
      this.endDrag(false);
    };
    const up = (e) => { if (e.pointerId === event.pointerId) this.endDrag(true); };
    const cancel = (e) => { if (e.pointerId === event.pointerId) this.endDrag(false); };
    this.endDrag = (drop) => {
      this.endDrag = null;
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key, true);
      if (!ghost) return;
      ghost.remove();
      this.modal.classList.remove("mmc-reel-dragging");
      this.markDrop(null);
      // The click that follows a release is the drag's, not the card's.
      const swallow = (e) => { e.preventDefault(); e.stopPropagation(); };
      window.addEventListener("click", swallow, { capture: true, once: true });
      setTimeout(() => window.removeEventListener("click", swallow, true), 0);
      if (!drop || !at) return;
      const from = this.timeline.segments.indexOf(segment);
      if (from < 0) return;
      this.moveTo(from, at.slot > from ? at.slot - 1 : at.slot);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key, true);
  }

  /** Video files dropped on the reel, as clips in the order they came. */
  async dropFiles(files, at) {
    for (const file of files) {
      if (!file.type.startsWith("video/")) {
        this.refuse(t("{file} is not a video. The reel takes videos as clips.", { file: file.name }));
        continue;
      }
      let segment;
      try {
        segment = await this.clipFrom(await upload(file), this.timeline);
      } catch (error) {
        this.refuse(String(error.message || error));
      }
      if (!segment) return;
      this.placeSegment(segment, Math.min(at, this.timeline.segments.length));
      at += 1;
    }
  }

  /** Say in the header why something did not happen, until the next edit. */
  refuse(reason) {
    this.refusal = reason;
    this.renderHead();
  }

  // ---- the reel -----------------------------------------------------------

  /** Where `seconds` into the piece falls on the reel, picture cuts included. */
  reelAt(seconds) {
    const lay = this.lay;
    if (!lay) return 0;
    let start = 0;
    for (let i = 0; i < lay.seconds.length; i += 1) {
      if (seconds <= start + lay.seconds[i] || i === lay.seconds.length - 1) {
        return lay.x[i] + (seconds - start) * lay.pps;
      }
      start += lay.seconds[i];
    }
    return 0;
  }

  /**
   * The piece at its real length: one card per shot, a join between each pair,
   * the sound underneath with any track laid on it. Strictly proportional —
   * this is the one place the lengths are compared — and drawn to the width the
   * window gives it.
   */
  renderReel() {
    const host = this.reelHost;
    if (!host) return;
    const segments = this.timeline.segments;
    const rules = rulesFor(S.pieceFamily(this.timeline));
    const seconds = segments.map((segment) =>
      (S.isClip(segment) ? S.clipSeconds(segment) : Number(segment.duration_s) || 0));
    // A picture cut opens a gap; a continuing join and a cut inside one pass
    // do not, so film that flows reads as touching.
    const GAP = 12;
    const cut = segments.map((segment, i) => i > 0 && !S.merged(segment) && !S.continues(segment));
    const gaps = cut.filter(Boolean).length * GAP;
    const width = Math.max(320, (host.clientWidth || 0));
    const total = seconds.reduce((a, b) => a + b, 0) || 1;
    const pps = (width - gaps) / total;
    const x = [];
    let cursor = 0;
    segments.forEach((_, i) => { if (cut[i]) cursor += GAP; x.push(cursor); cursor += seconds[i] * pps; });
    this.lay = { x, seconds, pps };
    this.pps = pps;
    const at = (i) => x[i];
    const span = (i) => seconds[i] * pps;
    const sel = this.sel;

    const passLane = el("div", { class: "mmc-reel-passes" });
    for (const pass of S.passes(this.timeline)) {
      if (pass.segments.length < 2) continue;
      const left = at(pass.start);
      const right = at(pass.end - 1) + span(pass.end - 1);
      passLane.append(el("div", {
        class: "mmc-reel-pass",
        style: { left: `${left}px`, width: `${right - left}px` },
        title: t("Shots {a} to {b} render as one generation.", { a: pass.start + 1, b: pass.end }),
        text: t("One generation"),
      }));
    }

    // Half a blend's width on the reel, by the shot it leads into: its words
    // start clear of the dissolve.
    const half = segments.map((segment, i) => {
      if (!i || S.merged(segment) || !S.continues(segment)) return 0;
      const frames = S.feather(segment, this.timeline);
      return frames > 1 ? (frames / rules.fps) * pps / 2 : 0;
    });
    const thumbs = segments.map((segment, i) => {
      if (S.isClip(segment)) return viewUrl(segment.filename, { preview: true });
      const take = S.takeOn(S.passOf(this.timeline, i).segments[0]);
      return take && this.shotState(i) !== "gone" ? viewUrl(take.filename, { preview: true }) : null;
    });

    // Two shots with pictures overlap over their blend; otherwise it is ticks.
    const filmed = (i) => Boolean(half[i] && thumbs[i] && thumbs[i - 1]);

    const picture = el("div", { class: "mmc-reel-picture" });
    // The pictures lie under the cards, each running out under the next one's
    // slits, so a picture keeps its own scale right across a blend.
    thumbs.forEach((src, i) => {
      if (!src) return;
      const lead = filmed(i) ? half[i] : 0;
      const tail = filmed(i + 1) ? half[i + 1] : 0;
      const round = [half[i] ? 0 : 8, half[i + 1] ? 0 : 8];
      picture.append(el("div", {
        class: "mmc-reel-film",
        style: { left: `${at(i) - lead}px`, width: `${Math.max(4, span(i) - (half[i + 1] ? 0 : 2)) + lead + tail}px`,
                 borderRadius: `${round[0]}px ${round[1]}px ${round[1]}px ${round[0]}px`,
                 ...(lead ? { maskImage: slitMask(lead * 2) } : {}) },
      }, [el("img", { class: "mmc-reel-thumb", src, alt: "", draggable: "false" })]));
    });
    segments.forEach((segment, i) => {
      const state = this.shotState(i);
      const thumb = thumbs[i];
      const lead = half[i] && span(i) > half[i] + 50 ? half[i] : 0;
      const tail = half[i + 1] ?? 0;
      const tag = this.stateTag(state);
      const card = el("button", {
        class: `mmc-reel-card ${state}${thumb ? " filmed" : ""}${half[i] ? " runs-in" : ""}${half[i + 1] ? " runs-on" : ""}${sel?.kind === "shot" && sel.index === i ? " selected" : ""}`,
        style: { left: `${at(i)}px`, width: `${Math.max(4, span(i) - (half[i + 1] ? 0 : 2))}px`,
                 "--lead": `${lead}px`, "--tail": `${tail && span(i) > lead + tail + 50 ? tail : 0}px` },
        title: (segment.prompt || segment.filename || "").trim(),
        onclick: () => this.select({ kind: "shot", index: i }),
        onpointerdown: (event) => this.dragCard(event, segment),
        ondblclick: () => (S.isClip(segment) ? this.editClip(i) : this.edit(i)),
      }, [
        el("span", { class: "mmc-reel-card-head" }, [
          el("b", { text: String(i + 1) }),
          el("span", { text: t("{s} s", { s: S.showSeconds(seconds[i]) }) }),
        ]),
        ...(thumb ? [] : [el("span", {
          class: "mmc-reel-card-text",
          text: (segment.prompt || "").trim() || t("No words yet"),
        })]),
        ...(tag ? [el("span", { class: `mmc-reel-card-tag ${state}`, text: tag })] : []),
      ]);
      // The right edge sets the length: dragged, it snaps to the family's frame
      // grid and the script's gutter follows. A clip's length is its trim.
      if (!S.isClip(segment)) {
        const edge = el("span", { class: "mmc-reel-edge", title: t("Drag to change the length") });
        edge.addEventListener("pointerdown", (event) => this.dragLength(event, i, rules));
        edge.addEventListener("click", (event) => event.stopPropagation());
        card.append(edge);
      }
      picture.append(card);
    });

    // The joins, on the line under the picture. A click selects one; what it
    // does is changed on the side, so looking at a join never changes it.
    const joins = el("div", { class: "mmc-reel-joins" });
    segments.forEach((segment, i) => {
      if (!i) return;
      const mid = at(i) - (cut[i] ? GAP / 2 : 0);
      const selected = sel?.kind === "join" && sel.index === i;
      const merged = S.merged(segment);
      const intoClip = S.isClip(segment);
      const on = S.continues(segment);
      const join = el("button", {
        class: `mmc-reel-join${merged ? " merged" : on ? " on" : ""}${selected ? " selected" : ""}`,
        style: { left: `${mid}px` },
        title: merged ? t("A cut inside one generation")
          : on ? t("The picture continues here. Click to change the join.")
            : t("The picture cuts here. Click to change the join."),
        onclick: () => this.select({ kind: "join", index: i }),
      }, [icon(merged ? "clapperboard" : on ? "link" : "scissors", 13)]);
      joins.append(join);
      // A blend is the overlap, drawn to scale: ticks for the frames that carry
      // over, or the pictures' own slits (above) once there are some, with a
      // bracket over it saying how long and an edge that sets it.
      if (on && !merged) {
        const frames = S.feather(segment, this.timeline);
        const grip = (title) => {
          const node = el("span", { class: "mmc-reel-grip", title });
          node.addEventListener("pointerdown", (event) => this.dragBlend(event, i, rules));
          return node;
        };
        // No blend yet is still a handle to pull one out of.
        if (frames <= 1 && this.maxBlend(i) > 1) {
          picture.append(el("div", { class: "mmc-reel-blend none", style: { left: `${at(i)}px` } },
            [grip(t("Drag to blend across this join."))]));
        }
        if (frames > 1) {
          const w = (frames / rules.fps) * pps;
          const select = () => this.select({ kind: "join", index: i });
          const band = el("div", {
            class: `mmc-reel-blend${filmed(i) ? " filmed" : ""}${selected ? " selected" : ""}`,
            style: { left: `${at(i) - w / 2}px`, width: `${w}px` },
          }, [el("button", {
            class: "mmc-reel-bracket",
            title: t("A {s} s blend. Click to change the join.", { s: blendSeconds(frames, rules) }),
            text: w > 40 || selected ? t("{s} s", { s: blendSeconds(frames, rules) }) : "",
            onclick: select,
          })]);
          join.addEventListener("pointerenter", () => band.classList.add("hot"));
          join.addEventListener("pointerleave", () => band.classList.remove("hot"));
          band.append(grip(t("A {s} s blend. Drag to change it.", { s: blendSeconds(frames, rules) })));
          picture.append(band);
        }
      }
    });

    // The sound, as a thread: unbroken where it carries over, parted where a
    // join starts it fresh. Its own dots, because the sound and the picture
    // cross a join independently. A track laid down rides on top of it.
    const sound = el("div", { class: "mmc-reel-sound" });
    let runStart = 0;
    const endOf = (i) => at(i) + span(i);
    segments.forEach((segment, i) => {
      if (!i) return;
      const breaks = !S.merged(segment) && !S.continuesAudio(segment);
      if (breaks) {
        sound.append(el("div", { class: "mmc-reel-wave",
          style: { left: `${at(runStart)}px`, width: `${Math.max(0, endOf(i - 1) - at(runStart) - 3)}px` } }));
        runStart = i;
      }
      if (S.merged(segment)) return;
      const carries = S.continuesAudio(segment);
      sound.append(el("button", {
        class: `mmc-reel-sdot${carries ? " on" : ""}`,
        style: { left: `${at(i) - (cut[i] ? GAP / 2 : 0)}px` },
        title: carries ? t("The sound carries over. Click to change the join.")
          : t("The sound starts fresh. Click to change the join."),
        onclick: () => this.select({ kind: "join", index: i }),
      }));
    });
    const last = segments.length - 1;
    if (last >= 0) {
      sound.append(el("div", { class: "mmc-reel-wave",
        style: { left: `${at(runStart)}px`, width: `${Math.max(0, endOf(last) - at(runStart))}px` } }));
    }
    const fps = rules.fps;
    for (const block of soundLane(this.timeline)) {
      const left = this.reelAt(block.at / fps);
      const right = this.reelAt((block.at + block.frames) / fps);
      sound.append(el("button", {
        class: `mmc-reel-track${sel?.kind === "track" && sel.index === block.index ? " selected" : ""}`,
        style: { left: `${left}px`, width: `${Math.max(24, right - left)}px` },
        title: block.filename,
        onclick: () => this.select({ kind: "track", index: block.index }),
      }, [el("span", { text: `♪ ${block.filename.split("/").pop()}` })]));
    }

    host.replaceChildren(el("div", { class: "mmc-reel-track-area", style: { width: `${width}px` } },
      [passLane, picture, joins, sound]));
    this.paintShooting();
    this.renderStatus();
  }

  /** The line under the reel: the one way to lay a track, and how the reel is
   *  handled. */
  renderStatus() {
    if (!this.statusHost) return;
    const supplied = S.familyOf(this.timeline).capabilities?.audio?.supplied;
    this.statusHost.replaceChildren(
      ...(supplied ? [el("button", {
        class: "mmc-reel-link", onclick: () => this.sound.add(),
      }, [el("span", { text: t("Lay a sound track") })])] : []),
      el("span", { class: "mmc-reel-hint", text: t("Drag a shot to move it, or its edge to change its length. Click a join to change it. Drop a video to add it.") }),
    );
  }

  /** Drag a shot's right edge. Live on the reel and in the gutter; written on
   *  release, which is when a kept take of it is released too. */
  dragLength(event, index, rules) {
    event.preventDefault();
    event.stopPropagation();
    const segment = this.timeline.segments[index];
    const start = Number(segment.duration_s) || 0;
    const x0 = event.clientX;
    const move = (e) => {
      const want = Math.min(60, Math.max(1, start + (e.clientX - x0) / this.pps));
      const snapped = secondsForFrames(framesForSeconds(want, rules), rules);
      if (snapped === segment.duration_s) return;
      segment.duration_s = snapped;
      this.renderReel();
      this.renderScript();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      this.sel = { kind: "shot", index };
      this.commit();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  /** The widest blend a join can have. Into a clip it is the shot in front that
   *  pays for it. */
  maxBlend(index) {
    const segment = this.timeline.segments[index];
    return S.isClip(segment) ? S.maxClipFeather(this.timeline, index) : S.maxFeather(segment, this.timeline);
  }

  /** Drag a blend's handle: the band is the overlap, so its width on screen is
   *  its length in seconds. Snaps to the family's grid, capped where the shot
   *  is too short to give more. */
  dragBlend(event, index, rules) {
    event.preventDefault();
    event.stopPropagation();
    const segment = this.timeline.segments[index];
    const grid = S.featherGridOf(this.timeline).filter((f) => f <= this.maxBlend(index));
    const start = S.feather(segment, this.timeline) / rules.fps;
    const x0 = event.clientX;
    const move = (e) => {
      const want = start + (2 * (e.clientX - x0)) / this.pps;
      const best = grid.reduce((a, f) => (Math.abs(f / rules.fps - want) < Math.abs(a / rules.fps - want) ? f : a), grid[0]);
      if (best === S.feather(segment, this.timeline)) return;
      if (best > 1) segment.feather = best; else { delete segment.feather; delete segment.feather_pin; }
      this.renderReel();
      this.renderSide();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      this.sel = { kind: "join", index };
      this.commit();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  // ---- the side -----------------------------------------------------------

  renderSide() {
    if (!this.inspectHost) return;
    const sel = this.sel;
    const count = this.timeline.segments.length;
    if ((sel?.kind === "shot" || sel?.kind === "join") && !(sel.index >= 0 && sel.index < count)) this.sel = null;
    if (sel?.kind === "join" && sel.index < 1) this.sel = null;
    if (sel?.kind === "cast" && !(this.timeline.subjects ?? []).some((s) => s.handle === sel.handle)) this.sel = null;
    if (sel?.kind === "ref" && !(this.timeline.assets ?? []).some((a) => a.handle === sel.handle)) this.sel = null;
    if (sel?.kind === "track" && !(this.timeline.sound ?? [])[sel.index]) this.sel = null;
    this.renderPlayer();
    const kind = this.sel?.kind;
    const body = kind === "join" ? this.inspectJoin(this.sel.index)
      : kind === "shot" ? (S.isClip(this.timeline.segments[this.sel.index])
          ? this.inspectClip(this.sel.index) : this.inspectShot(this.sel.index))
      : kind === "cast" ? this.inspectCast(this.sel.handle)
      : kind === "ref" ? this.inspectRef(this.sel.handle)
      : kind === "track" ? this.inspectTrack(this.sel.index)
      : this.inspectPiece();
    this.inspectHost.replaceChildren(...(this.sel ? [el("button", {
      class: "mmc-reel-link mmc-reel-back", text: t("‹ The piece"), title: t("The settings of the whole piece"),
      onclick: () => this.select(null),
    })] : []), body);
  }

  /** The player: the selected shot's take, a member's or a reference's
   *  picture, or the piece's latest take. Its own chrome — a label and a
   *  timecode — and a click to play or pause. Rebuilt only when what it shows
   *  changes, so typing does not restart it. */
  renderPlayer() {
    const sel = this.sel;
    const failure = this.stage?.failure;
    if (failure && failure !== this.failureSeen) {
      if (this.playerKey === failure) return;
      this.playerKey = failure;
      this.playerHost.replaceChildren(this.stage.slate());
      return;
    }
    const segments = this.timeline.segments;
    let key = "none";
    let media = null;
    let label = "";
    const takeOf = (index) => {
      const take = S.takeOn(S.passOf(this.timeline, index).segments[0]);
      return take && !this.gone.has(take.filename) ? take : null;
    };
    if ((sel?.kind === "shot" || sel?.kind === "join") && segments[sel.index]) {
      const index = sel.index;
      const segment = segments[index];
      if (S.isClip(segment)) {
        media = { video: segment.filename };
        label = t("Clip {n}", { n: index + 1 });
      } else if (takeOf(index)) {
        media = { video: takeOf(index).filename };
        label = sel.kind === "join" ? t("Shot {n}, coming out of join {a} → {b}", { n: index + 1, a: index, b: index + 1 })
                                    : t("Shot {n}", { n: index + 1 });
      } else {
        label = t("Shot {n} isn't shot yet", { n: index + 1 });
      }
    } else if (sel?.kind === "cast" || sel?.kind === "ref") {
      const asset = sel.kind === "ref"
        ? (this.timeline.assets ?? []).find((a) => a.handle === sel.handle)
        : S.castAssets(this.timeline).find((a) => S.subjectFiles(
            (this.timeline.subjects ?? []).find((s) => s.handle === sel.handle) ?? {}).includes(a.handle));
      if (asset?.kind === "video") media = { video: asset.filename };
      else if (asset?.kind === "image") media = { image: asset.filename };
      label = `@${sel.handle}`;
    } else {
      const latest = segments.map((_, i) => i).reverse().find((i) => !S.isClip(segments[i]) && takeOf(i));
      if (latest != null) {
        media = { video: takeOf(latest).filename };
        label = t("Latest take, shot {n}", { n: latest + 1 });
      } else {
        const clip = segments.findIndex(S.isClip);
        if (clip >= 0) media = { video: segments[clip].filename };
        label = clip >= 0 ? t("Clip {n}", { n: clip + 1 }) : t("Nothing shot yet");
      }
    }
    const selected = sel?.kind === "shot" ? S.passIndexOf(this.timeline, sel.index) : -1;
    const shooting = this.shootingIndex();
    if (this.busy() && (this.watching || !media
        || (shooting !== null && selected === S.passIndexOf(this.timeline, shooting)))) {
      this.renderLive();
      return;
    }
    const made = this.stage?.state === "done" && (this.watching || !sel) ? stageSource(this.stage.result) : null;
    if (made) {
      media = { [made.kind]: made.path };
      label = t("The last render");
    }
    key = `${label}|${media?.video ?? media?.image ?? ""}`;
    if (this.playerKey === key) return;
    this.playerKey = key;
    const time = el("span", { class: "mmc-reel-tc" });
    const children = [];
    if (media?.video) {
      const video = el("video", { class: "mmc-reel-media", src: viewUrl(media.video), preload: "metadata", playsinline: "",
        poster: viewUrl(media.video, { preview: true }) });
      const show = () => {
        const s = video.currentTime || 0;
        time.textContent = `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
      };
      video.addEventListener("timeupdate", show);
      video.addEventListener("loadedmetadata", show);
      const toggle = el("button", { class: "mmc-reel-play", title: t("Play or pause"),
        onclick: () => (video.paused ? video.play().catch(() => {}) : video.pause()) }, [icon("play", 20)]);
      video.addEventListener("play", () => toggle.classList.add("playing"));
      video.addEventListener("pause", () => toggle.classList.remove("playing"));
      children.push(video, toggle, time);
    } else if (media?.image) {
      children.push(el("img", { class: "mmc-reel-media", src: viewUrl(media.image, { preview: true }), alt: "" }));
    } else {
      children.push(el("div", { class: "mmc-reel-blank" }, [
        el("span", { text: sel ? t("Its take plays here once it is shot.") : t("The piece plays here once its first shot is done.") }),
      ]));
    }
    this.playerHost.replaceChildren(...children, el("span", { class: "mmc-reel-plabel", text: label }));
  }

  // ---- inspector parts ------------------------------------------------------

  /** A row of the inspector: what it is, then the control. */
  irow(label, control, note = null) {
    return el("div", { class: "mmc-reel-irow" }, [
      el("span", { class: "mmc-reel-ilabel", text: label }),
      el("div", { class: "mmc-reel-icontrol" }, [
        control,
        ...(note ? [el("span", { class: "mmc-reel-note", text: note })] : []),
      ]),
    ]);
  }

  /** Mutually exclusive choices. `options` are [value, label, sub?, disabled?]. */
  segmented(options, current, onPick, tone = "") {
    return el("div", { class: `mmc-reel-seg ${tone}`, role: "group" },
      options.map(([value, label, sub, disabled]) => el("button", {
        "aria-pressed": String(value === current),
        disabled: disabled || undefined,
        onclick: () => { if (value !== current) onPick(value); },
      }, [el("span", { text: label }), ...(sub ? [el("small", { text: sub })] : [])])));
  }

  switchControl(on, onChange, disabled = false) {
    return el("button", {
      class: "mmc-reel-switch", role: "switch", "aria-checked": String(Boolean(on)),
      disabled: disabled || undefined,
      onclick: () => onChange(!on),
    });
  }

  ihead(title, sub = null, tag = null) {
    return el("div", { class: "mmc-reel-ihead" }, [
      el("b", { text: title }),
      ...(tag ? [tag] : []),
      ...(sub ? [el("span", { text: sub })] : []),
    ]);
  }

  /** What this computer does at every seam: the settings the seam rows here
   *  only switch on and off. */
  machineLine() {
    const handoff = { frames: t("frames"), latent: t("latent"), levelled: t("levelled latent"),
      masked: t("masked latent") }[uiSetting("seam_handoff", "latent")] ?? uiSetting("seam_handoff", "latent");
    const keystone = { off: t("no keystone"), keystone: t("the keystone"),
      capstone: t("keystone and capstone") }[uiSetting("keystone", "off")] ?? uiSetting("keystone", "off");
    return el("div", { class: "mmc-reel-machine" }, [
      el("span", { text: t("This computer hands seams over as {handoff} and holds scenes with {keystone}.",
        { handoff, keystone }) + " " }),
      el("button", { class: "mmc-reel-link", text: t("Rendering settings"), onclick: () => openSettings() }),
    ]);
  }

  thumbs(assets, onAdd = null, about = () => ({})) {
    return el("div", { class: "mmc-reel-thumbs" }, [
      ...assets.map((asset) => {
        const { remove, from } = about(asset);
        const title = from ? `@${asset.handle}, ${from}` : `@${asset.handle}`;
        return el("span", { class: "mmc-reel-thumb-wrap" }, [
          asset.kind === "image" || asset.kind === "video"
            ? el("img", { src: viewUrl(asset.filename, { preview: true }), alt: `@${asset.handle}`, title })
            : el("span", { class: "mmc-reel-thumb-blank", text: asset.kind === "audio" ? "♪" : "·", title }),
          ...(remove ? [el("button", { class: "mmc-reel-x", text: "✕", title: t("Remove @{handle}", { handle: asset.handle }),
            "aria-label": t("Remove @{handle}", { handle: asset.handle }), onclick: remove })] : []),
        ]);
      }),
      ...(onAdd ? [el("button", { class: "mmc-reel-thumb-add", title: t("Add"), onclick: onAdd }, [icon("plus", 13)])] : []),
    ]);
  }

  // ---- the piece --------------------------------------------------------------

  /** Nothing selected: the inspector is the piece. Model, frame, resolution,
   *  look, storyboards, rewrite — everything that is the same in every shot. */
  inspectPiece() {
    probeAspectSizes(this.timeline, () => { if (!this.sel) this.renderSide(); }, { all: true });
    const geometry = this.geometry();
    const rules = rulesFor(S.pieceFamily(this.timeline));
    const res = resolutionPillText(this.timeline, geometry);
    const passes = S.passes(this.timeline);
    const refined = this.timeline.segments.some((segment) => segment.refined?.body);
    const value = (text, sub, onclick) => el("button", { class: "mmc-reel-value", onclick }, [
      el("span", { text }), ...(sub ? [el("small", { text: sub })] : []), icon("chevron", 12)]);
    const rows = [
      this.ihead(t("Piece"), t("Select a shot, a join or someone in the cast to see theirs")),
      this.irow(t("Model"), el("div", { class: "mmc-reel-family" }, [
        familyPill({ piece: this.timeline, onChange: () => this.commit() })])),
      this.irow(t("Frame"), value(
        geometry.fromInput ? describeRatio(geometry.ratio, rules) : this.timeline.aspect,
        geometry.fromInput ? aspectSourceLabel(this.timeline) : null,
        (event) => this.openAspect(event.currentTarget))),
      this.irow(t("Resolution"), value(`${this.timeline.short_edge}p`, res.sub,
        (event) => openResolutionPopover(event.currentTarget, this.timeline, () => this.geometry(), () => this.commit()))),
    ];
    const loras = this.timeline.loras ?? [];
    rows.push(this.irow(t("Look"), el("div", { class: "mmc-reel-loras" }, [
      ...loras.map((entry) => el("button", {
        class: `mmc-reel-lora${S.loraOff?.(entry) || entry.enabled === false ? " off" : ""}`,
        title: t("Click to switch it off or on for every shot"),
        onclick: () => { S.toggleLora(this.timeline, entry.name); this.commit(); },
      }, [el("span", { text: loraBase(entry) }),
          el("small", { text: entry.enabled === false ? t("off") : String(entry.strength ?? 1) })])),
      el("button", { class: "mmc-reel-link", text: loras.length ? t("Edit") : t("Add a LoRA"), onclick: () => this.openLoras() }),
    ])));
    const io = this.io();
    rows.push(this.irow(t("Seed"), el("div", { class: "mmc-reel-inline" }, [
      ...seedPill({ widgets: this.widgets, ...io, set: (name, v) => { io.set(name, v); this.renderSide(); } }),
      this.segmented([["each", t("One per shot")], [null, t("Same for every shot")]], this.timeline.seeds ?? null,
        (next) => { if (next) this.timeline.seeds = next; else delete this.timeline.seeds; this.commit(); }),
    ]), this.timeline.seeds
      ? t("The first shot runs on this seed and each later one counts up from it.")
      : t("Every shot starts from the same noise, so a continued shot can fall back to the one before.")));
    if (S.canDo(this.timeline, "storyboard") && passes.length > 1) {
      const policy = S.storyboardPolicy(this.timeline);
      rows.push(this.irow(t("Storyboards"), this.segmented(
        [[null, t("None")], ["previous", t("Previous shot")], ["all", t("Every shot so far")]], policy,
        (next) => { if (next) this.timeline.storyboard = next; else delete this.timeline.storyboard; this.commit(); })));
      const anySheet = this.timeline.segments.some((_, i) => S.storyboardSheet(this.timeline, i).length);
      if (anySheet) {
        const cap = S.capabilityOf(this.timeline, "storyboard") || {};
        const holds = cap.holds || S.STORYBOARD_HOLDS;
        const names = { fully_preserved: t("Firm"), partially_preserved: t("Partial"), weak_reference: t("Loose") };
        rows.push(this.irow(t("A sheet holds"), el("div", { class: "mmc-reel-inline" }, [
          this.segmented(holds.map((h) => [h, names[h] ?? h]), S.storyboardHold(this.timeline),
            (next) => { this.timeline.storyboard_hold = next; this.commit(); }),
          el("button", { class: "mmc-reel-link", text: t("What carries over"),
            onclick: () => openEditorSheet({ title: t("What a storyboard carries over"), content: [this.storyboardHold()], onClose: () => this.render() }) }),
        ])));
      }
    }
    if (passes.slice(1).map((pass) => pass.segments[0]).some(
      (head) => S.continuesAudio(head) && !blendSetsTail(head, this.timeline))) {
      const tail = Number(this.timeline.audio_tail_s);
      const nudge = (delta) => {
        this.timeline.audio_tail_s = Math.min(S.MAX_AUDIO_TAIL_S, Math.max(0.1, Math.round((tail + delta) * 10) / 10));
        this.commit();
      };
      rows.push(this.irow(t("Sound carried"), el("span", { class: "mmc-reel-stepper" }, [
        el("button", { text: "−", onclick: () => nudge(-0.1) }),
        el("span", { text: t("{s} s", { s: tail.toFixed(1) }) }),
        el("button", { text: "+", onclick: () => nudge(0.1) }),
      ]), t("How much sound a join without a blend carries across.")));
    }
    rows.push(this.irow(t("Rewrite"), el("div", { class: "mmc-reel-inline" }, [
      refineButton({
        run: (options) => this.refineAll(options),
        family: () => S.pieceFamily(this.timeline),
        label: refined ? t("Refine every shot again") : t("Refine every shot"),
        className: "mmc-reel-btn",
        title: t("Rewrite the scene and every shot into the description this model was trained to read, in one pass so later shots keep what the first establishes."),
      }),
      ...(refined ? [el("button", { class: "mmc-reel-link", text: t("Go back to what I wrote"), onclick: () => this.revertAll() })] : []),
    ])));
    if (this.refineError) rows.push(el("p", { class: "mmc-reel-problem", text: this.refineError }));
    rows.push(this.machineLine());
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  // ---- a shot -----------------------------------------------------------------

  inspectShot(index) {
    const segment = this.timeline.segments[index];
    const state = this.shotState(index);
    const runs = S.passes(this.timeline);
    const passIndex = S.passIndexOf(this.timeline, index);
    // "Again" is only said of what has been shot.
    const followNames = S.followers(this.timeline, passIndex)
      .filter((k) => S.takeOn(runs[k].segments[0])).map((k) => runs[k].start + 1);
    const tagText = this.stateTag(state);
    const ripple = followNames.length
      ? t(followNames.length === 1 ? "Shot {list} continues from it and is shot again too."
                                   : "Shots {list} continue from it and are shot again too.",
          { list: followNames.join(", ") })
      : t("Nothing else changes.");
    const why = {
      kept: t("Its take is kept. The next render plays it instead of shooting it again."),
      changed: t("You changed it after its take was made, so the next render shoots it again."),
      reshoot: t("The next render shoots it again. Its current take stays until the new one lands."),
      new: t("The next render shoots it."),
      gone: t("Its take's file is not under output/ any more, so the next render shoots it again."),
    }[state] + (state === "kept" || (state === "new" && !followNames.length) ? "" : " " + ripple);
    const take = S.takeOn(runs[passIndex].segments[0]);
    const film = [];
    if (state === "kept") {
      film.push(el("button", { class: "mmc-reel-btn primary", title: ripple,
        onclick: () => { if (S.reshoot(this.timeline, index)) this.commit(); } },
      [icon("rewind", 14), el("span", { text: t("Reshoot") })]));
      film.push(el("span", { class: "mmc-reel-note", text: ripple }));
      film.push(...this.takeTools(index, "mmc-reel-btn quiet"));
    } else if (state === "reshoot") {
      film.push(el("button", { class: "mmc-reel-btn",
        onclick: () => {
          if (S.keepTake(this.timeline, index)) this.commit();
          else { this.keepRefused = index; this.renderSide(); }
        } }, [el("span", { text: t("Keep the old take") })]));
    }
    if (take && state !== "gone") {
      film.push(el("button", { class: "mmc-reel-btn quiet", title: t("The file stays under output/."),
        onclick: () => { if (S.dropTake(this.timeline, index)) this.commit(); } }, [el("span", { text: t("Forget take") })]));
    }

    const rules = rulesFor(S.pieceFamily(this.timeline));
    const predicts = runs[passIndex].segments.length === 1 && S.canDo(this.timeline, "duration");
    const nudge = (delta) => {
      const next = Math.min(60, Math.max(1, (Number(segment.duration_s) || 0) + delta));
      segment.duration_s = secondsForFrames(framesForSeconds(next, rules), rules);
      this.commit();
    };
    const own = S.segmentSeed(segment);
    const seedInput = el("input", {
      class: "mmc-reel-seed", inputmode: "numeric", spellcheck: "false",
      placeholder: t("piece seed, {n}", { n: S.inheritedSeed(this.timeline, index, this.pieceSeed()) }),
      title: take?.seed != null ? t("Its take was made on {n}.", { n: take.seed }) : "",
      onchange: (event) => {
        const raw = String(event.target.value).trim();
        const n = Number(raw);
        if (raw === "" || !Number.isInteger(n) || n < 0) delete segment.seed; else segment.seed = n;
        this.commit();
      },
    });
    seedInput.value = own === null ? "" : String(own);
    const loras = S.activeLoras(segment, S.pieceFamily(this.timeline));
    const pictures = [...(segment.assets ?? []), ...S.citedPool(segment)];
    const cast = S.citedCast(segment);
    const absent = (this.timeline.subjects ?? []).filter((subject) => !cast.includes(subject));
    const bringer = (asset) => cast.find((subject) => S.subjectFiles(subject).includes(asset.handle));

    const rows = [
      this.ihead(t("Shot {n}", { n: index + 1 }), null,
        tagText ? el("span", { class: `mmc-reel-tag ${state}`, text: tagText }) : null),
      el("p", { class: "mmc-reel-why", text: why }),
      ...(film.length ? [el("div", { class: "mmc-reel-actions" }, film)] : []),
      ...(this.keepRefused === index ? [el("p", { class: "mmc-reel-note", text: t("It can't be kept while the shot it continues from is being shot again.") })] : []),
      this.irow(t("Length"), el("div", { class: "mmc-reel-inline" }, [
        el("span", { class: "mmc-reel-stepper" }, [
          el("button", { text: "−", title: t("Shorter"), onclick: () => nudge(-0.5) }),
          el("span", { text: (segment.auto_duration === true && predicts ? "~" : "") + t("{s} s", { s: S.showSeconds(segment.duration_s) }) }),
          el("button", { text: "+", title: t("Longer"), onclick: () => nudge(0.5) }),
        ]),
        ...(predicts ? [this.switchControl(segment.auto_duration === true, (on) => { segment.auto_duration = on; this.commit(); }),
                        el("span", { class: "mmc-reel-note", text: t("let the model choose") })]
                     : [el("span", { class: "mmc-reel-note", text: t("or drag its edge on the reel") })]),
      ])),
      ...((this.timeline.subjects ?? []).length ? [this.irow(t("Cast"), el("div", { class: "mmc-reel-loras" }, [
        ...cast.map((subject) => {
          const everywhere = S.subjectCitedGlobally(this.timeline, subject);
          return el("span", { class: "mmc-reel-lora", title: everywhere ? t("In every shot, from the scene") : "" }, [
            el("button", { class: "mmc-reel-link", text: `@${subject.handle}`,
              onclick: () => this.select({ kind: "cast", handle: subject.handle }) }),
            ...(everywhere ? [el("small", { text: t("scene") })] : [el("button", { class: "mmc-reel-chip-x", text: "✕",
              title: t("Take @{handle} out of this shot", { handle: subject.handle }),
              onclick: () => {
                S.uncite([segment], subject.handle, subject.handle.replace(/_/g, " "));
                this.commit();
              } })]),
          ]);
        }),
        ...(absent.length ? [el("button", { class: "mmc-reel-link", text: t("Add someone"),
          onclick: (event) => openChoicePopover(event.currentTarget, {
            title: t("Into this shot"), options: absent.map((subject) => `@${subject.handle}`),
            onPick: (name) => {
              segment.prompt = `${(segment.prompt ?? "").trimEnd()} ${name} `.trimStart();
              this.commit();
            },
          }) })] : []),
      ]))] : []),
      this.irow(t("Pictures"), this.thumbs(pictures, () => this.edit(index), (asset) => {
        const remove = this.removerFor(segment, asset);
        const member = bringer(asset);
        return { remove, from: remove ? null : member ? t("from @{handle}", { handle: member.handle }) : t("from the scene") };
      })),
      ...this.refineRows(index),
      this.irow(t("Look"), el("div", { class: "mmc-reel-loras" }, [
        ...(loras.length ? loras.map((entry) => el("span", { class: "mmc-reel-lora" }, [el("span", { text: loraBase(entry) }),
          ...((segment.loras ?? []).some((own) => own.name === entry.name) ? [el("button", { class: "mmc-reel-chip-x", text: "✕",
            title: t("Take it off this shot"),
            onclick: () => { segment.loras = segment.loras.filter((own) => own.name !== entry.name); this.commit(); } })] : []),
        ]))
                         : [el("span", { class: "mmc-reel-note", text: t("the piece's look") })]),
        el("button", { class: "mmc-reel-link", text: t("Add a LoRA"), onclick: () => this.edit(index) }),
      ])),
      this.irow(t("Seed"), el("div", { class: "mmc-reel-inline" }, [
        seedMark(S.shotSeed(this.timeline, index, this.pieceSeed())),
        seedInput,
        el("button", { class: "mmc-reel-link mmc-reel-seed-new", text: t("New seed"),
          onclick: () => { segment.seed = Math.floor(Math.random() * 2147483647); this.commit(); } }),
        ...(own !== null ? [el("button", { class: "mmc-reel-link mmc-reel-seed-piece", text: t("Use the piece's"),
          onclick: () => { delete segment.seed; this.commit(); } })] : []),
      ])),
    ];
    if (S.canDo(this.timeline, "motion_fix")) {
      rows.push(this.irow(t("Motion fix"), el("div", { class: "mmc-reel-inline" }, [
        el("span", { class: "mmc-reel-motion" }, [this.switchControl(S.motionFix(segment, this.timeline), (on) => {
          if (on) segment.motion_fix = true; else delete segment.motion_fix;
          this.commit();
        })]),
        el("span", { class: "mmc-reel-note", text: t("slows fast motion down, redraws it, puts it back on time") }),
      ])));
    }
    if (this.timeline.face?.on) {
      rows.push(this.irow(t("Face"), this.switchControl(S.faceOn(this.timeline, segment), (on) => {
        if (on) delete segment.face; else segment.face = "off";
        this.commit();
      })));
    }
    rows.push(el("div", { class: "mmc-reel-actions quiet" }, [
      el("button", { class: "mmc-reel-btn quiet", text: t("What the model reads"), onclick: () => this.showCompiled(index) }),
      el("button", { class: "mmc-reel-btn quiet", text: t("Use a clip"),
        title: t("Play a clip you already have here. The words stay."),
        onclick: () => this.addClip(index, { replace: true }) }),
      el("button", { class: "mmc-reel-btn quiet", text: t("More for this shot"), onclick: () => this.edit(index) }),
      el("button", { class: "mmc-reel-btn quiet", text: t("Earlier"), disabled: index === 0 || undefined,
        onclick: () => this.moveTo(index, index - 1) }),
      el("button", { class: "mmc-reel-btn quiet", text: t("Later"), disabled: index === this.timeline.segments.length - 1 || undefined,
        onclick: () => this.moveTo(index, index + 1) }),
      el("button", { class: "mmc-reel-btn quiet", text: t("Duplicate"),
        disabled: S.addSegmentRefusal(this.timeline, segment.duration_s) ? true : undefined,
        onclick: () => this.duplicate(index) }),
      this.removeButton(index, t("Remove this shot")),
    ]));
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  /** One shot's rewrite: the button, and the rewrite itself to read, edit,
   *  switch off or throw away. */
  refineRows(index) {
    const segment = this.timeline.segments[index];
    const id = segment.card_id;
    if (!this.refiners.has(id)) {
      const find = () => this.timeline.segments.find((card) => card.card_id === id) ?? {};
      this.refiners.set(id, {
        button: refineButton({
          run: (options) => this.refineShot(id, options),
          family: () => S.pieceFamily(this.timeline),
          label: "Refine this shot", className: "mmc-reel-btn",
          title: t("Rewrite this shot alone into the description this model was trained to read. The other shots, the scene, Sound and Score stay as they are."),
        }),
        panel: new RefinePanel({
          getState: find, audioFields: false,
          // Typed into, so the side under the caret is left alone.
          onCommit: () => {
            S.releaseEdited(this.timeline);
            this.wrote(`refined:${id}`);
            this.renderScript();
            this.renderReel();
            this.renderHead();
          },
          onRevert: () => { this.dropTimelineRewrite(); this.commit(); },
        }),
      });
    }
    const { button, panel } = this.refiners.get(id);
    panel.render();
    return [this.irow(t("Rewrite"), button), panel.root];
  }

  async refineShot(id, options) {
    const index = this.timeline.segments.findIndex((card) => card.card_id === id);
    if (index < 0 || this.refining.has(id)) return;
    this.refining.add(id);
    this.refineRows(index);
    this.renderScript();
    let result = null;
    let problem = null;
    try {
      result = await refine({ kind: "segment", index, data: JSON.parse(S.serializeTimeline(this.timeline)) }, options);
      if (!result.shots?.[0]?.body) problem = t("the refiner returned nothing for this prompt");
    } catch (error) {
      problem = String(error.message || error);
    }
    this.refining.delete(id);
    // Found again by its id: the strip may have moved, or lost it, meanwhile.
    const now = this.timeline.segments.findIndex((card) => card.card_id === id);
    if (now < 0 || S.isClip(this.timeline.segments[now])) { this.renderStrip(); return; }
    this.refineRows(now);
    const { panel } = this.refiners.get(id);
    if (problem) {
      panel.fail(problem);
      this.sel = { kind: "shot", index: now };
      this.renderStrip();
      return;
    }
    // Not `takePiece`: one shot's rewrite leaves the piece's sound alone, which
    // every other shot's take was made under.
    panel.apply(result, result.shots[0]);
    if (result.sections && S.isSingle(this.timeline)) {
      this.timeline.refined = { ...(this.timeline.refined || {}), sections: result.sections };
    }
    this.commit();
  }

  /** The finished prompt for a shot's pass, as its own sheet. */
  async showCompiled(index) {
    const body = el("pre", { class: "mmc-reel-compiled", text: t("Asking…") });
    openEditorSheet({ title: t("What the model reads"), subtitle: t("Shot {n}", { n: index + 1 }), content: [body] });
    const answer = await compiledFor(this.timeline, index, this.pieceSeed());
    body.textContent = answer.problem ?? answer.text ?? answer.message ?? "";
  }

  // ---- a clip -----------------------------------------------------------------

  inspectClip(index) {
    const clip = this.timeline.segments[index];
    const silentFile = clip.has_audio === false;
    return el("div", { class: "mmc-reel-inspect-body" }, [
      this.ihead(t("Clip {n}", { n: index + 1 }), (clip.filename || "").split("/").pop()),
      el("p", { class: "mmc-reel-why", text: t("Footage you added. It plays as it is; nothing is generated for it.") }),
      this.irow(t("Plays"), el("div", { class: "mmc-reel-inline" }, [
        el("span", { class: "mmc-reel-mono", text: clip.trim ? trimLabel(clip) : t("{s} s, the whole file", { s: S.showSeconds(S.clipSeconds(clip)) }) }),
        el("button", { class: "mmc-reel-link", text: t("Trim"), onclick: () => this.editClip(index) }),
      ])),
      this.irow(t("Framing"), el("div", { class: "mmc-reel-inline" }, [
        el("span", { class: "mmc-reel-mono", text: cropLabel(clip.crop) || t("the whole frame") }),
        el("button", { class: "mmc-reel-link", text: t("Crop"), onclick: () => this.editClipCrop(index) }),
      ])),
      el("p", { class: "mmc-reel-why", text: t("Its words are read when the shots beside it are rewritten. The video model never reads them.") }),
      this.irow(t("Its sound"), this.segmented([[true, t("Plays")], [false, t("Silent")]], S.clipSound(clip),
        (on) => { if (on) delete clip.sound; else clip.sound = false; this.commit(); }), silentFile ? t("The file has no sound.") : null),
      el("div", { class: "mmc-reel-actions quiet" }, [
        el("button", { class: "mmc-reel-btn quiet", text: t("Replace the file"), onclick: () => this.replaceClip(index) }),
        el("button", { class: "mmc-reel-btn quiet", text: t("Generate it instead"), onclick: () => this.clipToShot(index) }),
        el("button", { class: "mmc-reel-btn quiet", text: t("Earlier"), disabled: index === 0 || undefined,
          onclick: () => this.moveTo(index, index - 1) }),
        el("button", { class: "mmc-reel-btn quiet", text: t("Later"), disabled: index === this.timeline.segments.length - 1 || undefined,
          onclick: () => this.moveTo(index, index + 1) }),
        this.removeButton(index, t("Remove this clip")),
      ]),
    ]);
  }

  // ---- a join -----------------------------------------------------------------

  /** Everything about one join, in one place: picture, sound, where it
   *  continues from, the blend and what rides on it, the storyboard sheet,
   *  and whether the two shots are one generation at all. */
  inspectJoin(index) {
    const segments = this.timeline.segments;
    const segment = segments[index];
    const rules = rulesFor(S.pieceFamily(this.timeline));
    const title = t("Join {a} → {b}", { a: index, b: index + 1 });
    if (S.merged(segment)) {
      const pass = S.passOf(this.timeline, index);
      return el("div", { class: "mmc-reel-inspect-body" }, [
        this.ihead(title),
        el("p", { class: "mmc-reel-why", text: t("Shots {a} to {b} render as one generation, so this cut is drawn by the model. There is no blend, sound switch or source here.",
          { a: pass.start + 1, b: pass.end }) }),
        this.irow(t("One generation"), this.switchControl(true, () => this.splitAt(index))),
      ]);
    }
    const intoClip = S.isClip(segment);
    const afterClip = S.isClip(segments[index - 1]);
    const on = S.continues(segment);
    const sound = S.continuesAudio(segment);
    const blocked = on ? null : intoClip ? S.clipSeamBlocked(this.timeline, index, "continue") : S.blockedReason(segment, "continue");
    const soundBlocked = sound ? null : intoClip ? S.clipSeamBlocked(this.timeline, index, "continue_audio")
      : S.silentSource(this.timeline, index) ? t("The clip it continues from has no sound playing to carry over.")
      : S.blockedReason(segment, "continue_audio");
    const commit = () => this.commit();
    const rows = [
      this.ihead(title, intoClip ? t("into a clip you added") : afterClip ? t("out of a clip you added") : null),
      this.irow(t("Picture"), this.segmented([[true, intoClip ? t("Runs into it") : t("Continues"), null, Boolean(blocked)], [false, t("Cut")]], on,
        (v) => { segment.continue = v; commit(); }, "motion"), blocked),
      this.irow(t("Sound"), this.segmented([[true, t("Carries over"), null, Boolean(soundBlocked)], [false, t("Starts fresh")]], sound,
        (v) => { segment.continue_audio = v; commit(); }, "voice"), soundBlocked),
    ];
    if (!intoClip && (on || sound)) {
      const earlier = this.earlierPasses(index);
      if (earlier.length >= 2) {
        const stored = S.continueSource(segment, index);
        const from = earlier.find((pass) => stored > pass.start && stored <= pass.end)?.end ?? stored;
        rows.push(this.irow(t("Continues from"), this.segmented(
          earlier.map((pass) => [pass.end, t("Shot {n}", { n: pass.end })]), from,
          (n) => { if (n === index) delete segment.continue_from; else segment.continue_from = n; commit(); })));
      }
    }
    if (on) {
      const max = this.maxBlend(index);
      const grid = S.featherGridOf(this.timeline);
      const width = Math.min(S.feather(segment, this.timeline), max);
      rows.push(this.irow(t("Blend"), this.segmented(grid.filter((f) => f <= max).map((f) => [f, t(BLEND_NAMES[grid.indexOf(f)] ?? "Blend"),
        f > 1 ? blendSeconds(f, rules) : null]), width,
      (f) => { if (f > 1) segment.feather = f; else { delete segment.feather; delete segment.feather_pin; } commit(); }),
      grid.some((f) => f > max) ? t("Longer blends would take more than half of a shot this short.") : null));
      if (!intoClip && S.canDo(this.timeline, "seam_restore") && !afterClip) {
        const names = [t("Off"), t("Light"), t("Medium"), t("Strong")];
        const current = S.seamRestore(segment, this.timeline);
        const nearest = S.SEAM_RESTORE_LEVELS.reduce((best, level) => (Math.abs(level - current) < Math.abs(best - current) ? level : best));
        rows.push(this.irow(t("Restore detail"), this.segmented(S.SEAM_RESTORE_LEVELS.map((level, k) => [level, names[k]]), nearest,
          (level) => { if (level > 0) segment.seam_restore = level; else delete segment.seam_restore; commit(); }),
        t("Redraws the frames it hands over, so softening does not build up down the piece.")));
      }
      if (S.canDo(this.timeline, "seam_pin") && S.feather(segment, this.timeline) > 1) {
        rows.push(this.irow(t("Pin the landing frame"), this.switchControl(segment.feather_pin === true,
          (v) => { if (v) segment.feather_pin = true; else delete segment.feather_pin; commit(); }),
        t("Sharper arrival, less carried motion.")));
      }
      if (S.keystoneSeam(segment, this.timeline, index)) {
        const machineOff = uiSetting("keystone", "off") === "off";
        rows.push(this.irow(t("Hold to the scene"), this.switchControl(segment.keystone !== false,
          (v) => { if (v) delete segment.keystone; else segment.keystone = false; commit(); }),
        machineOff ? t("Only matters while the keystone is on in Rendering settings.")
                   : t("Carries the scene's first frame into this shot, so drift cannot stack up.")));
      }
    }
    if (!intoClip && S.canDo(this.timeline, "storyboard") && S.passOf(this.timeline, index).start === index) {
      const raw = segment.storyboard;
      const current = raw === undefined || raw === null ? "piece" : raw === false ? "none"
        : Array.isArray(raw) && raw.length === 1 && Number(raw[0]) === index ? "previous"
        : Array.isArray(raw) && raw.length >= index ? "all" : "custom";
      const sheet = S.storyboardSheet(this.timeline, index);
      rows.push(this.irow(t("Storyboard"), this.segmented([
        ["piece", t("As the piece")], ["none", t("None")], ["previous", t("Previous shot")], ["all", t("Every shot so far")],
        ...(current === "custom" ? [["custom", t("Shots {list}", { list: passNumbers(sheet) })]] : []),
      ], current, (choice) => {
        if (choice === "piece") delete segment.storyboard;
        else if (choice === "none") segment.storyboard = false;
        else if (choice === "previous") segment.storyboard = [index];
        else if (choice === "all") segment.storyboard = Array.from({ length: index }, (_, i) => i + 1);
        commit();
      }), sheet.length ? t("Shown shots {list} on one sheet.", { list: passNumbers(sheet) }) : null));
    }
    if (!intoClip && !afterClip) {
      rows.push(this.irow(t("One generation"), this.switchControl(false, () => this.mergeAt(index)),
        t("Render shots {a} and {b} together, with this cut written into the description.", { a: index, b: index + 1 })));
    }
    rows.push(this.machineLine());
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  // ---- the cast and references ------------------------------------------------

  inspectCast(handle) {
    const subject = (this.timeline.subjects ?? []).find((s) => s.handle === handle);
    const files = S.subjectFiles(subject);
    const assets = S.castAssets(this.timeline).filter((asset) => files.includes(asset.handle));
    const everywhere = S.subjectCitedGlobally(this.timeline, subject);
    // The shots that write their name, and those that cite one of their files
    // by its own handle: both carry the member into the render (#91).
    const shots = [...new Set([
      ...S.subjectCitations(this.timeline, subject),
      ...assets.flatMap((asset) => ((this.timeline.assets ?? []).includes(asset) ? S.poolCitations(this.timeline, asset) : [])),
    ])].sort((a, b) => a - b);
    const where = everywhere ? t("in every shot")
      : shots.length ? t(shots.length === 1 ? "in shot {list}" : "in shots {list}", { list: shots.join(", ") })
      : t("not written into any shot yet");
    return el("div", { class: "mmc-reel-inspect-body" }, [
      this.ihead(`@${handle}`, `${t(S.takeWord(subject.takes ?? "person"))}, ${where}`),
      this.irow(t("Pictures"), this.thumbs(assets, () => this.openCastSheet(handle), (asset) => ({
        // Their last file only goes with them, unless they are written down too.
        remove: files.length > 1 || (subject.description || "").trim() || S.subjectFeatures(subject).length
          ? () => this.removeMemberFile(subject, asset) : null,
      }))),
      el("div", { class: "mmc-reel-actions" }, [
        el("button", { class: "mmc-reel-btn", text: t("Open their card"), onclick: () => this.openCastSheet(handle) }),
        ...(everywhere ? [] : [el("button", { class: "mmc-reel-btn quiet", text: t("Write them into the scene"), onclick: () => this.citeName(handle) })]),
        el("button", { class: "mmc-reel-btn quiet danger", text: t("Remove from the piece"),
          title: t("Their mentions become plain words. Undo brings them back."),
          onclick: () => this.removeMember(handle) }),
      ]),
      el("p", { class: "mmc-reel-note", text: t("Their card is where looks, wears, a voice and saved pictures are set.") }),
    ]);
  }

  inspectRef(handle) {
    const asset = (this.timeline.assets ?? []).find((a) => a.handle === handle);
    const cited = S.poolCitations(this.timeline, asset);
    const everywhere = S.poolCitedGlobally(this.timeline, asset);
    // Uncited, but the same file attached to a shot under its own handle: in
    // use one level down, which "not written into any shot" would hide.
    const doubles = everywhere || cited.length ? [] : S.poolDoubles(this.timeline, asset);
    const where = everywhere ? t("in every shot")
      : cited.length ? t(cited.length === 1 ? "in shot {list}" : "in shots {list}", { list: cited.join(", ") })
      : doubles.length ? t("not written into any shot, but attached to {list} as its own file",
          { list: doubles.map((d) => t("shot {n} (@{handle})", { n: d.segment, handle: d.handle })).join(", ") })
      : t("not written into any shot yet");
    const kind = { image: t("a picture"), video: t("a clip"), audio: t("a sound") }[asset.kind] ?? asset.kind;
    const rows = [this.ihead(`@${handle}`, `${kind}, ${where}`)];
    if (S.takeable(asset) && !(S.isPlate(asset) && asset.panels.length > 1)) {
      rows.push(this.irow(t("Taken for"), el("button", { class: "mmc-reel-value", title: t(takesHelp(asset)),
        onclick: (event) => pickTakes(event.currentTarget, asset, () => this.commit()) },
      [el("span", { text: t(S.takeWord(S.takes(asset))) }), icon("chevron", 12)])));
    }
    if (S.sizeable(asset)) {
      rows.push(this.irow(t("Detail"), this.segmented([["match", t("Match the frame")], ["max", t("Most detail")]], S.refSize(asset),
        (size) => { asset.ref_size = size; this.commit(); }), t("Most detail is several times slower.")));
    }
    rows.push(el("div", { class: "mmc-reel-actions" }, [
      ...(S.croppable(asset) ? [el("button", { class: "mmc-reel-btn", text: t("Crop or cut out"), onclick: () => this.editPoolPicture(asset) })] : []),
      ...(asset.kind === "image" && S.plateSpec(this.timeline)
        ? [el("button", { class: "mmc-reel-btn quiet", text: S.isPlate(asset) && asset.panels.length > 1 ? t("Edit sheet") : t("Combine"),
            onclick: () => this.editPoolSheet(asset) })] : []),
      el("button", { class: "mmc-reel-btn quiet", text: t("Replace the file"), onclick: () => this.replacePoolAsset(asset) }),
      ...(everywhere ? [] : [el("button", { class: "mmc-reel-btn quiet", text: t("Write it into the scene"), onclick: () => this.citeInGlobal(asset) })]),
      el("button", { class: "mmc-reel-btn quiet danger", text: t("Remove"),
        title: t("Its mentions go with it. Undo brings it back."),
        onclick: () => this.removeReference(asset) }),
    ]));
    return el("div", { class: "mmc-reel-inspect-body" }, rows);
  }

  // ---- a sound track --------------------------------------------------------

  inspectTrack(index) {
    const entry = this.timeline.sound[index];
    const at = Number(entry.at_s) || 0;
    const length = (Number(entry.out_s) || 0) - (Number(entry.in_s) || 0);
    const move = (delta) => { entry.at_s = Math.max(0, Math.round((at + delta) * 10) / 10); this.commit(); };
    return el("div", { class: "mmc-reel-inspect-body" }, [
      this.ihead(t("Sound track"), entry.filename.split("/").pop()),
      el("p", { class: "mmc-reel-why", text: t("Laid under the picture. The shots it covers are generated against it instead of writing their own sound.") }),
      this.irow(t("Starts at"), el("span", { class: "mmc-reel-stepper" }, [
        el("button", { text: "−", onclick: () => move(-0.5) }),
        el("span", { text: t("{s} s", { s: at.toFixed(1) }) }),
        el("button", { text: "+", onclick: () => move(0.5) }),
      ])),
      this.irow(t("Plays for"), el("span", { class: "mmc-reel-mono", text: t("{s} s", { s: length.toFixed(1) }) })),
      el("div", { class: "mmc-reel-actions quiet" }, [
        el("button", { class: "mmc-reel-btn quiet danger", text: t("Take it off"),
          onclick: () => { this.timeline.sound.splice(index, 1); this.sel = null; this.commit(); } }),
      ]),
    ]);
  }

  // ---- actions ---------------------------------------------------------------

  add() {
    if (S.addSegmentRefusal(this.timeline)) return;
    this.timeline.segments.push(S.continuingSegment(this.timeline));
    this.commit();
  }

  /**
   * Cut a video already on disk into the piece.
   *
   * The same picker every other attachment goes through, so there is one asset
   * store and no second way to name a file. What is asked of the file after
   * that is its length and its shape — the length because the strip has to
   * price the card without opening it, the shape because the timeline's aspect
   * may come from it — and whether it has a soundtrack at all, which decides
   * what the card's sound switch is allowed to say.
   */
  async addClip(at, { replace = false } = {}) {
    const shot = replace ? this.timeline.segments[at] : null;
    // Priced without the shot it stands in for.
    const budget = shot ? { ...this.timeline,
      segments: this.timeline.segments.filter((card) => card !== shot) } : this.timeline;
    const segment = await this.pickClip(budget);
    if (!segment) return;
    if (!shot) { this.placeSegment(segment, at); return; }
    const index = this.timeline.segments.indexOf(shot);
    if (index < 0) return;
    // Its words say what the clip shows, and the cast keeps its files.
    if ((shot.prompt || "").trim()) segment.prompt = shot.prompt;
    S.rescueCastFiles(this.timeline, shot);
    this.timeline.segments[index] = segment;
    this.sel = { kind: "shot", index };
    this.commit();
  }

  /** The clip's card generated instead, from the words it has. */
  clipToShot(index) {
    const clip = this.timeline.segments[index];
    const shot = index ? S.continuingSegment(this.timeline) : S.emptySegment();
    shot.prompt = clip.prompt ?? "";
    this.timeline.segments[index] = shot;
    this.commit();
  }

  /**
   * Put another file on the clip card at `index`, where it stands.
   *
   * Removing a clip and adding one lands the new card at the end and loses
   * every seam that named the old one, so a clip in the middle of a continued
   * run had to be rebuilt by hand. Here the card keeps its place and its seam
   * — whether the shot before it runs in, the blend it spends, whether it
   * plays its sound — and so does every seam and storyboard that names it by
   * number. What belonged to the old file goes with it: its window and its
   * framing were set against that footage, and mean nothing on another.
   */
  async replaceClip(index) {
    const old = this.timeline.segments[index];
    // Priced without the card it replaces, which is giving its seconds back.
    const without = { ...this.timeline,
                      segments: this.timeline.segments.filter((_, i) => i !== index) };
    const fresh = await this.pickClip(without);
    if (!fresh) return;
    const kept = {};
    for (const key of ["continue", "continue_audio", "feather", "feather_pin", "sound", "prompt"]) {
      if (key in old) kept[key] = old[key];
    }
    // A silent file cannot honour a sound switch left on by the one before it.
    if (fresh.has_audio === false) delete kept.sound;
    this.timeline.segments[index] = { ...fresh, ...kept };
    this.commit();
  }

  /**
   * One video from the picker, read into a clip card — or nothing, with the
   * reason on the strip. `budget` is the timeline the card is priced against.
   *
   * The window and framing chosen in the picker's own segment and crop editors
   * come through on the card: cutting a segment there is how you say which
   * seconds you want, and a card that played the whole file anyway would be
   * ignoring the one thing asked.
   */
  async pickClip(budget) {
    const chosen = await openPicker({
      kinds: ["video", "renders"], kind: "video", single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    if (!chosen?.length) return null;
    return this.clipFrom(chosen[0], budget);
  }

  /** A clip card for a file that is on disk, or null with the reason said. */
  async clipFrom(picked, budget) {
    const probed = await probe(picked.path).catch(() => ({}));
    const segment = S.clipSegment({
      filename: picked.path,
      duration: probed.duration ?? 0,
      width: probed.width ?? 0,
      height: probed.height ?? 0,
      // null means the probe could not answer; the switch stays available and
      // the backend refuses a clip that turns out to be silent, which is a
      // better failure than greying out a control on a guess.
      hasAudio: probed.hasAudio !== false,
    });
    if (picked.trim) segment.trim = picked.trim;
    if (picked.crop) segment.crop = picked.crop;
    if (!segment.duration_s) {
      this.refuse(t("Could not read how long {file} is — a clip card needs its length.",
                    { file: picked.path }));
      return null;
    }
    // Asked again with the card's real length — the window's if one was cut,
    // else the file's — rather than a default: a ten-minute clip and a
    // two-second one are not the same ask of the frame budget.
    const refusal = S.addSegmentRefusal(budget, S.clipSeconds(segment));
    if (refusal) {
      this.refuse(refusal);
      return null;
    }
    return segment;
  }

  /** The clip's window, through the same trim editor a reference video uses. */
  editClip(index) {
    const segment = this.timeline.segments[index];
    return this.trimFile(segment, segment.filename);
  }

  /** The clip's framing, through the same editor a reference picture uses. */
  editClipCrop(index) {
    const segment = this.timeline.segments[index];
    return this.cropFile(segment, segment.filename);
  }

  /** A kept take's window and framing. The take is spliced as a clip card —
   *  see `compile.take_spec` — so these are a clip's settings, held on the take
   *  rather than the card: a retake replaces the take and they go with it. */
  editTake(index) {
    const take = S.takeOn(this.timeline.segments[index]);
    return take && this.trimFile(take, take.filename);
  }

  editTakeCrop(index) {
    const take = S.takeOn(this.timeline.segments[index]);
    return take && this.cropFile(take, take.filename);
  }

  /** Writes `holder.trim`, a clip card or a take. */
  async trimFile(holder, path) {
    const picked = await openTrim({
      path,
      kind: "video",
      trim: holder.trim ?? null,
      // A clip card *is* the picture — its sound rides with it and is switched
      // on the card — so there is no track to choose here, unlike a reference
      // clip, which can be cited for one stream or the other.
      showTrack: false,
    });
    if (!picked) return;
    if (picked.trim) holder.trim = picked.trim;
    else delete holder.trim;
    this.commit();
  }

  /** Writes `holder.crop`. The canvas is offered as the lock; the holder's own
   *  trim bounds the scrub. */
  async cropFile(holder, path) {
    const { width, height } = this.geometry();
    const picked = await openPicture({
      path,
      kind: "video",
      crop: holder.crop ?? null,
      trim: holder.trim ?? null,
      aspect: width && height ? { ratio: width / height, label: t("canvas") } : null,
    });
    if (!picked) return;
    if (picked.crop) holder.crop = picked.crop;
    else delete holder.crop;
    this.commit();
  }

  /** Trim and Crop for a kept take, in the skin of the row they sit in. None
   *  for a card that is not kept, or whose file is gone: there is nothing on
   *  disk to scrub. */
  takeTools(index, skin) {
    const take = S.takeOn(this.timeline.segments[index]);
    if (!S.isKept(this.timeline.segments[index]) || this.gone.has(take.filename)) return [];
    return [
      el("button", {
        class: `${skin}${take.trim ? " on" : ""}`, text: t("Trim"),
        title: take.trim
          ? t("Plays {window} of the take. Click to change it.", { window: trimLabel(take) })
          : t("Play only part of the take"),
        onclick: () => this.editTake(index),
      }),
      el("button", {
        class: `${skin}${take.crop ? " on" : ""}`, text: t("Crop"),
        title: cropLabel(take.crop)
          || t("Crop the take to part of the frame, or turn and mirror it, before it is scaled to the canvas"),
        onclick: () => this.editTakeCrop(index),
      }),
    ];
  }

  duplicate(index) {
    if (S.addSegmentRefusal(this.timeline, this.timeline.segments[index].duration_s)) return;
    const copy = S.cloneSegment(this.timeline.segments[index]);
    // The take is not copied and neither is the hold. A take is the film one
    // card made, and a copy of the card has not been shot — carrying it over
    // would put the same seconds of picture on the strip twice under two
    // numbers, and the second one would claim to be done.
    delete copy.take;
    delete copy.hold;
    this.timeline.segments.splice(index + 1, 0, copy);
    // Every segment after the insertion moved down one card; a seam naming one
    // of them follows it. Nothing pointed at the clone a moment ago, and a seam
    // naming the original still does.
    S.remapContinueFrom(this.timeline, (n) => (n > index + 1 ? n + 1 : n));
    this.commit();
  }

  /**
   * The card's ✕, which asks twice. The first press turns it into the
   * question, in words, where the ✕ was; the second answers it. Anything else
   * — the pointer leaving the card, the strip redrawing for another reason —
   * puts the ✕ back, so a card is never left standing armed.
   */
  removeButton(index, title) {
    if (this.armed === index) {
      return el("button", {
        class: "mmc-asset-x armed", text: t("Really remove?"),
        title: t("Press again to remove it. Leave the card to keep it."),
        onclick: () => this.remove(index),
      });
    }
    return el("button", {
      class: "mmc-asset-x", text: "✕", title,
      onclick: () => { this.armed = index; this.renderStrip(); },
    });
  }

  remove(index) {
    this.armed = null;
    // The cast's pictures first, off the card and into the pool: they are the
    // members', and the members are staying.
    S.rescueCastFiles(this.timeline, this.timeline.segments[index]);
    this.timeline.segments.splice(index, 1);
    // A seam that named the removed segment falls back to the previous one;
    // one naming a later segment follows it up a card.
    S.remapContinueFrom(this.timeline,
      (n) => (n === index + 1 ? null : n > index + 1 ? n - 1 : n));
    this.commit();
  }

  /**
   * Reorder, one step from the side's buttons or anywhere by a drag. A segment
   * carries its continuation flag with it, and `syncTimeline`
   * clears it off whatever ends up first — a segment moved to the front has
   * nothing left to continue from. A named seam source follows the card it
   * points at, and `syncTimeline` likewise drops any source the swap carried
   * to or past its own seam.
   */
  moveTo(from, to) {
    if (!S.moveSegment(this.timeline, from, to)) return;
    this.sel = { kind: "shot", index: to };
    this.commit();
    this.rowFor(to)?.el.scrollIntoView({ block: "nearest" });
  }

  /**
   * The LoRA manager, editing the timeline's own list.
   *
   * Handed the checkpoints the segments actually route to rather than one: a
   * global LoRA is patched onto every segment and the segments need not agree,
   * so "idle" here means it lands on none of them, not on the wrong one.
   */
  async openLoras(entry = null) {
    await openLoras({
      state: this.timeline,
      family: S.pieceFamily(this.timeline),
      targets: S.timelineCheckpoints(this.timeline),
      scope: "piece",
      // The chip that asked, so the grid opens on it. See `loras.revealNow`.
      reveal: entry?.name ?? null,
      onChange: () => this.commit(),
    });
    this.render();
  }

  /**
   * The fields a rewrite writes that belong to the piece rather than a shot:
   * the global prompt, the soundscape and the score.
   *
   * Straight into the timeline's own textareas, which are the ones the user is
   * looking at — a refined soundscape hidden inside a card would be invisible
   * and would then disagree with the box above it. The global prompt lands in
   * its own box the same way, and stays a live input: compile joins it in
   * front of every shot-scoped rewrite exactly as it joins it in front of
   * typed text, so editing it here keeps meaning something. An empty `music`
   * is left alone rather than written: the refiner returns one only when the
   * request asked for music, and clearing a score the user typed is not what
   * "the model had nothing to add" means.
   */
  takePiece(result) {
    // What was in them first, so `revertAll` can put them back. Taken once and
    // then left alone: refining again must not record the last rewrite's prose
    // as the thing the user typed. The prompt joins the snapshot the first
    // time a rewrite actually moves it — older snapshots simply lack the key,
    // and reverting one leaves the prompt exactly where it stands.
    const replaced = this.timeline.refined?.replaced
      ?? { soundscape: this.timeline.soundscape ?? "", music: this.timeline.music ?? "" };

    if (result.piece) {
      if (replaced.prompt === undefined) replaced.prompt = this.timeline.prompt ?? "";
      this.setGlobalPrompt(result.piece);
    }
    if (result.soundscape) this.timeline.soundscape = result.soundscape;
    if (result.music) this.timeline.music = result.music;
    this.timeline.refined = {
      ...(this.timeline.refined || {}),
      replaced,
      // Only the reference form has these, and in one pass they describe the one
      // merged generation, so they are the timeline's. Chained, each reference
      // card carries its own set and they live on the card instead.
      ...(result.sections && S.isSingle(this.timeline) ? { sections: result.sections } : {}),
    };
    this.soundscapeBox.value = this.timeline.soundscape ?? "";
    this.musicBox.value = this.timeline.music ?? "";
    this.onCommit?.();
  }

  /**
   * Throw away every rewrite in the strip and everything written alongside them.
   *
   * The counterpart of `refineAll`, and the only way back from it: a strip
   * refined in one press was queueing prose in place of every card's own
   * sentence, and undoing that card by card means opening every one of them.
   * The timeline's soundscape, score and reference sections go too — they were
   * written by the same call and describe rewrites that no longer exist.
   */
  revertAll() {
    for (const segment of this.timeline.segments) segment.refined = null;
    this.dropTimelineRewrite();
    this.commit();
  }

  /**
   * Drop what the refiner left on the timeline itself, once no card uses it.
   *
   * Reached from `revertAll` and from a single card's own Revert: the audio
   * fields and the reference analysis belong to the rewrite as a whole, so the
   * moment the last one is gone they are prose describing nothing. A card
   * reverted while others stay refined leaves them exactly as they are.
   */
  dropTimelineRewrite() {
    if (this.timeline.segments.some((segment) => segment.refined?.body)) return;
    const replaced = this.timeline.refined?.replaced;
    if (replaced) {
      this.timeline.soundscape = replaced.soundscape ?? "";
      this.timeline.music = replaced.music ?? "";
      // Only when a rewrite actually moved it — see `takePiece` — so reverting
      // an audio-only rewrite cannot blank a global prompt the user typed.
      if (replaced.prompt !== undefined) this.setGlobalPrompt(replaced.prompt);
      if (this.soundscapeBox) this.soundscapeBox.value = this.timeline.soundscape;
      if (this.musicBox) this.musicBox.value = this.timeline.music;
    }
    this.timeline.refined = null;
  }

  /**
   * Rewrite every card in one call.
   *
   * The point of doing the whole strip at once rather than card by card is that
   * a rewrite of shot 4 can only keep what shot 1 established if the same call
   * wrote both — the look, the people, the light and the speakers carry because
   * the model saw them, not because anything here copied them forward.
   */
  async refineAll(options) {
    this.refineError = null;
    try {
      const result = await refine({
        kind: "timeline",
        data: JSON.parse(S.serializeTimeline(this.timeline)),
      }, options);
      for (const shot of result.shots ?? []) {
        const segment = this.timeline.segments[shot.index];
        if (!segment || !shot.body) continue;
        segment.refined = {
          body: shot.body,
          // The rewrite is the shot alone: compile joins the (rewritten) global
          // prompt in front of it, exactly as it joins it in front of typed
          // text, which is what keeps the global box live after refining.
          ...(result.scope ? { scope: result.scope } : {}),
          // Chained, a segment is its own generation over its own references,
          // so each reference card carries its own analysis sections in its
          // shot entry. In one pass there is one merged pool and the one
          // top-level set goes on the timeline instead — see `takePiece`.
          ...(shot.sections ? { sections: shot.sections } : {}),
          ...(result.template ? { template: result.template, forced: !!result.forced } : {}),
          source: segment.prompt ?? "",
          model: refineModel(),
          enabled: true,
        };
      }
      this.takePiece(result);
      this.refineError = (result.problems ?? []).join(" · ") || null;
    } catch (error) {
      this.refineError = String(error.message || error);
    }
    this.commit();
  }


  /** The segment editor: the node's own body, over the strip. */
  edit(index) {
    const segment = this.timeline.segments[index];
    const editor = new CreatorEditor({
      state: segment,
      // Which piece this card belongs to — the same answer the lone shot's
      // editor gets (`faceBody`). Without it the editor fell back to the card
      // itself, a segment carries no `family`, and every family-derived control
      // in the window was drawn as the default family: no auto-duration switch
      // on a family that has a duration head, H3's mode names over LTX's cards,
      // a weights pill for routes LTX does not have, and attach tools for
      // references the compiler would then refuse. The strip underneath had all
      // of it right, because it asks `this.timeline`.
      piece: this.timeline,
      // The shelf as well as the strip: writing `@ref-1` in this card is what
      // makes the pool chip say "in segment 3", and the shelf is the only place
      // that fact is ever shown. Redrawn on the card's own commits rather than
      // waiting for the window to close, because a readout that lags the thing
      // it reports on reads as one that does not work — the chip sat on "cited
      // nowhere yet" for the whole of the edit that cited it. It holds no caret
      // and nothing focusable, so rebuilding it under an open window costs
      // nothing. See `renderPool` and `S.poolCitations`.
      onCommit: () => {
        this.onCommit?.(); this.renderStrip(); this.renderPool(); this.renderCast();
      },
      // A member typed into this card's prose is cast into the *piece* — where
      // the cast lives — and their files land in the piece's pool. The card is
      // where they are written, not where they are kept.
      castFromLibrary: (member) => this.castFromLibrary(member),
      // ...and the same answer to "whose cast is this". Without it the editor
      // looked the piece's subjects up on the segment, found none, and a name
      // clicked in a card opened nothing while deleting one took nobody out.
      // It is also whose cast the card's own shelf draws: the window's shelf is
      // behind the sheet, so the card carries one, and it is this one (#124).
      castPiece: this.timeline,
      compiledPrompt: () => compiledFor(this.timeline, index, this.pieceSeed()),
      // What a `{day|night}` in this card is chosen on: the card's own seed
      // where it was retaken on one, the piece's otherwise — the sampler's
      // rule — and the card's number, so two cards holding the same sentence
      // choose apart. See `compile.varied_piece`.
      varies: () => ({ seed: S.segmentSeed(segment) ?? this.pieceSeed(), card: index + 1 }),
      // Both belong to the timeline rather than to one shot: the canvas because
      // the segments are joined, the continuation because it describes the seam
      // in front of this segment and so does not exist for the first one.
      canvasPills: false,
      // The route belongs to the timeline, like the canvas: a clip whose shots
      // ran on different checkpoints per the same setting would not be one
      // setting. Read here, set from the node body's weights control.
      routeOf: () => this.timeline.models?.route ?? "auto",
      // Only where there is a seam to switch. A shot inside a pass has none —
      // it is a cut inside one generation, and continuity there is the model's
      // to keep rather than a wiring decision — and neither has shot 1.
      continuePill: index > 0 && S.passOf(this.timeline, index).start === index,
      // The card's seed is edited on the strip; the generic editor's optional
      // seedTarget stays unset here so the control has only one location.
      // One card, refined against the whole timeline: the server compiles the
      // strip to build this segment's payload, so the rewrite is written knowing
      // the global prompt, the canvas and whether this shot continues the last.
      refineTarget: () => ({
        kind: "segment",
        index,
        data: JSON.parse(S.serializeTimeline(this.timeline)),
      }),
      // The soundscape and the score describe the piece rather than the shot, so
      // they land on the timeline's own fields where they are visible and
      // editable — not inside the card that happened to be refined. A single
      // card's refine never returns a rewritten global prompt — the other
      // cards' rewrites were written against the standing one — so `takePiece`
      // only moves the audio here.
      // This card, as a preset — the scope that makes the library worth opening
      // mid-edit. A card has no stage of its own and the piece's last render is
      // the whole piece rather than this shot, so there is nothing to take as a
      // cover automatically: one is set by hand from the gallery or not at all.
      presetTarget: () => ({
        scope: "shot",
        label: t(shared ? "Shot {n}" : "Segment {n}", { n: index + 1 }),
        // The piece's family: a card has no row and no weights of its own.
        family: () => S.pieceFamily(this.timeline),
        capture: () => ({
          data: P.captureShot(this.timeline, index, this.io()),
          defaultName: (segment.prompt || "").trim().split("\n")[0].slice(0, 48),
        }),
        apply: (body, keys, from) => {
          P.applyToShot(body, keys, segment, this.io(),
                        { from, piece: this.timeline });
          this.onCommit?.();
          this.renderStrip();
        },
      }),
      onRefined: (result) => this.takePiece(result),
      // …and go with the last rewrite that was using them. The commit is this
      // callback's own: the editor's fired before it, so what it wrote out still
      // had the timeline's audio fields in it.
      onReverted: () => { this.dropTimelineRewrite(); this.onCommit?.(); },
    });

    // A card sharing a pass is a shot of it; a card generated alone is a
    // segment. The two words mean different things in this node and the header
    // is where the user finds out which one they are editing.
    const shared = S.passOf(this.timeline, index).segments.length > 1;
    // The same window the Creator's face opens: one shot's body over whatever
    // it was opened from. It was already this window in all but the code.
    openEditorSheet({
      title: t(shared ? "Shot {n}" : "Segment {n}", { n: index + 1 }),
      subtitle: t("of {count}", { count: this.timeline.segments.length }),
      content: [editor.root],
      onClose: () => this.render(),
    });
  }
}

/** After-generate modes, in the order ComfyUI lists them. */

/**
 * The Timeline node's body in the graph: the piece at a glance, the way in, and
 * the sampler settings.
 *
 * The strip itself lives in the modal — it needs room the node does not have,
 * and drawing an editable one here would be a second implementation to keep in
 * step. What the node shows is the global prompt, the segments at their real
 * relative lengths, and the numbers.
 *
 * The sampler row is drawn as pills like everything else, and its values are in
 * the blob like everything else — `piece.sampling`, read and written through
 * `sampling.blobIO`. It was thirteen stock widgets until a second model family
 * made a static widget list untenable; those widgets are still declared, still
 * hidden, and now only the fallback that carries a workflow saved before the
 * move. The seed alone is still really a widget.
 */
const RUN_EVENTS = ["execution_start", "execution_success", "execution_error", "execution_interrupted", "status"];

export class TimelineBody {
  /** `preStage` and `face` are wiring the node supplies — see creator.js.
   *  `face` is where the piece-view pin is kept, which is a preference about
   *  this node rather than anything the render reads, so it lives on the node
   *  and not in the blob. */
  constructor({ read, write, widgets = {}, onWidgetChange, nodeId,
                preStage = null, face = null, fullscreen = null }) {
    this.read = read;
    this.write = write;
    this.widgets = widgets;
    this.onWidgetChange = onWidgetChange;
    this.nodeId = nodeId;
    this.preStage = preStage;
    this.face = face;
    // The way *into* the shell. The way out is the shell's own corner, and the
    // command and its keybinding have always existed — but a keystroke nobody
    // has been told about is not a door, and the setting in ComfyUI's own page
    // only decides what a *new* node opens as. So the face grows one.
    this.fullscreen = fullscreen;
    this.timeline = S.parseTimeline(read());
    // Persist identities before graphToPrompt reads the widget, including
    // migration of an old strip. They identify UI cards, not render content.
    if (S.ensureCardIds(this.timeline)) {
      // Add only ids here. Serializing all defaults before reload() adopts a
      // legacy node's sampling widgets would overwrite its actual settings.
      let raw;
      try { raw = JSON.parse(read()); } catch { raw = null; }
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        let migrated = false;
        if (Array.isArray(raw.segments)
            && raw.segments.length === this.timeline.segments.length) {
          raw.segments = raw.segments.map((card, index) => ({
            ...card, card_id: this.timeline.segments[index].card_id,
          }));
          migrated = true;
        } else if (!Array.isArray(raw.segments) && this.timeline.segments.length === 1) {
          raw.card_id = this.timeline.segments[0].card_id;
          migrated = true;
        }
        if (migrated) this.write(JSON.stringify(raw, null, 2));
      }
    }
    // The face's editor, when the piece is one shot and the face is wearing
    // one. Null the rest of the time — see `loneShot`.
    this.faceEditor = null;

    // The same stage the Creator has, showing the same thing: a timeline is one
    // clip, and what it is making is one picture whatever the strip looks like.
    // attach() floats it beside the node in a Satellite; it never mounts here.
    this.root = el("div", { class: "mmc-root" });
    this.queued = new Map();
    this.queueLookups = new Map();
    this.takeArrivals = new Map();
    this.takeSequence = 0;
    this.offSubmitted = watchSubmittedPrompts(
      (output) => this.submittedCards(output),
      (promptId, snapshot) => {
        this.rememberQueued(promptId, snapshot);
        this.runs.set(String(promptId), "queued");
        this.reel?.accepted();
      });
    // Where this node's prompts are on the queue, which the stage does not say
    // until a sampler runs: the reel has loading and waiting to report too.
    this.runs = new Map();
    this.onRun = ({ type, detail }) => {
      if (type === "status") {
        if (detail?.exec_info?.queue_remaining !== 0 || !this.runs.size) return;
        this.runs.clear();
      } else {
        const id = String(detail?.prompt_id);
        if (!this.runs.has(id)) return;
        if (type === "execution_start") this.runs.set(id, "running"); else this.runs.delete(id);
      }
      this.reel?.staged();
    };
    for (const name of RUN_EVENTS) api.addEventListener(name, this.onRun);
    // The open window, while there is one: it draws the same strip, and only
    // this body hears what the queue says about it.
    this.reel = null;
    this.onRefused = ({ detail }) => {
      if (detail.items?.some((item) => this.stage.ours(item.nodeId)) || this.stage.claims(detail)) {
        this.reel?.refused(detail.items ?? []);
      }
    };
    api.addEventListener("mmc_refused", this.onRefused);
    this.stage = new Stage({
      nodeId,
      // A look for the finished render, where the family has the pass.
      onRestyle: S.canDo(this.timeline, "guide_lora") ? () => this.restyle() : null,
      // Which generation the queue is on, said over the preview: the strip runs
      // for minutes and a bare step count says nothing about where in the
      // piece the sampler is. Counted in passes, because that is what the
      // announcing node is one of. Read late — the strip may grow between
      // queueing and the announce.
      segmentLabel: (index) => t("Pass {n} of {count}",
        { n: index, count: S.passes(this.timeline).length }),
      // Every pass this render wrote, back onto the card that made it. The card
      // is not held by it: what came back is a take, and whether to keep it is
      // the point of looking at it. See `takeTakes`.
      onTakes: (reported, context) => this.takeTakes(reported, context),
      // View-only: a timeline's references live on its segments, so a pick from
      // here would have no card to land on. The Creator attaches; this browses.
      onGallery: () => openPicker({
        kinds: ["renders"],
        kind: "renders",
        viewOnly: true,
        home: this.settingsHome(),
        capacity: () => ({ used: 0, max: 0, filesLeft: 0 }),
      }),
    });
    loadCatalog(() => this.adoptWeights());
    // ...and again behind the settings, which carry the other half of the
    // rescue: this machine's remembered picks. See `CreatorEditor`.
    primeSettings(() => this.adoptWeights());
    this.render();
  }

  destroy() {
    this.destroyed = true;
    this.offSubmitted?.();
    api.removeEventListener("mmc_refused", this.onRefused);
    for (const name of RUN_EVENTS) api.removeEventListener(name, this.onRun);
    this.stage?.destroy();
    this.laneFit?.disconnect();
    this.dropFaceEditor();
  }

  /** The prompt of this node's that is running, else the next one waiting. */
  currentRun() {
    const all = [...this.runs];
    const [id, state] = all.find((run) => run[1] === "running") ?? all[0] ?? [];
    if (id) return { id, state, cards: this.queued.get(id)?.ids };
    // A run found already going, after a reload.
    return this.stage.state === "sampling" && this.queued.has(this.stage.renderPromptId)
      ? { id: this.stage.renderPromptId, state: "running", cards: this.queued.get(this.stage.renderPromptId).ids } : null;
  }

  /** Only this node's submitted blob, not the strip currently on screen. */
  submittedCards(output) {
    const inputs = output?.[String(this.nodeId())]?.inputs;
    // The unified Creator and the legacy Timeline mount this same body.
    const raw = inputs?.creator_data ?? inputs?.timeline_data;
    if (typeof raw !== "string") return null;
    try {
      const parsed = JSON.parse(raw);
      const cards = S.asPiece(parsed)?.segments;
      // A mixed old/new blob must not turn off known ownership merely because
      // a *different* card has no id. Legacy recovery is per submitted slot.
      const legacy = Array.isArray(cards)
        ? cards.map((card) => typeof card?.card_id !== "string" || !card.card_id) : false;
      return S.queuedCards(S.parseTimeline(raw), { legacy });
    } catch { return null; }
  }

  rememberQueued(promptId, snapshot) {
    this.queued.set(String(promptId), snapshot);
    // Snapshots contain only ids/stamps. Old entries can be recovered from
    // history if a very large pending batch outlives this bounded notebook.
    while (this.queued.size > 128) this.queued.delete(this.queued.keys().next().value);
  }

  async takeTakes(reported, { promptId, prompt = null } = {}) {
    if (!promptId || this.destroyed) return;
    const id = String(promptId);
    const arrival = ++this.takeSequence;
    let snapshot = this.queued.get(id);
    if (!snapshot) {
      if (!this.queueLookups.has(id)) {
        this.queueLookups.set(id, (async () => {
          const output = prompt?.[2] ?? await submittedPrompt(id);
          return this.submittedCards(output);
        })().catch(() => null));
      }
      snapshot = await this.queueLookups.get(id);
      this.queueLookups.delete(id);
      snapshot = this.queued.get(id) ?? snapshot;
      if (!snapshot || this.destroyed) return; // Keep unowned results in history.
      this.rememberQueued(id, snapshot);
    }
    const applicable = reported.filter((report) => {
      const card = snapshot.ids[Number(report.segment) - 1];
      if (!card || (this.takeArrivals.get(card) ?? 0) > arrival) return false;
      // An older history lookup finishing after a newer report must not
      // overwrite that card's newer take. Other cards may still land normally.
      this.takeArrivals.set(card, arrival);
      return true;
    });
    if (S.attachTakes(this.timeline, applicable, snapshot)) {
      this.commit();
      this.reel?.landed();
    }
    const live = new Set(this.timeline.segments.map((card) => card.card_id));
    for (const card of this.takeArrivals.keys()) {
      if (!live.has(card)) this.takeArrivals.delete(card);
    }
  }

  /** See `CreatorEditor.adoptWeights` — same rescue, same reason. */
  adoptWeights() {
    if (adoptWeights(this.timeline)) this.commit();
    else this.render();
  }

  /** Re-read the widget. Loading a saved workflow assigns widget values after
   *  the node is created, so the body built in `nodeCreated` saw the default. */
  reload() {
    // The sampler row moved off the widgets into the blob, and this is where a
    // workflow saved before that crosses over — here rather than in the
    // constructor, because that is the point at which both halves are final.
    // See `sampling.adopted`.
    const adopted_ = adopted(this.read(), this.widgets, S.parseTimeline, S.serializeTimeline);
    if (adopted_) this.write(adopted_);
    this.timeline = S.parseTimeline(this.read());
    if (S.ensureCardIds(this.timeline)) this.write(S.serializeTimeline(this.timeline));
    // The face editor closes over the segment object it was handed, and this is
    // a different one. Dropped rather than re-pointed: `render` builds another
    // against whatever the strip now holds.
    this.dropFaceEditor();
    this.render();
  }

  /**
   * Whether this piece is one shot and nothing else — the rule that picks the
   * face.
   *
   * **The face is the smallest one that can show everything this piece has
   * set.** One segment is not enough on its own: a piece can carry a global
   * prompt, a reference pool, LoRAs patched onto every shot and the two
   * Context-IR audio fields, and none of those has anywhere to live on a face
   * that is one shot's editor. A face that cannot draw a field it still queues
   * is a trap, so the presence of any of them takes the strip face instead.
   *
   * That is also why there is no way back other than emptying them: collapsing
   * is what setting them does, run backwards. Nothing is stored and nothing is
   * toggled — this is asked on every render.
   *
   * A supplied clip is not a shot. A piece of one clip has no generation to put
   * on the face at all, so it keeps the strip.
   */
  /**
   * Which face this node is actually wearing.
   *
   * The content rule below decides what the face *can* be; this is what it is.
   * A piece of one shot can be shown either way and the pin says which — asked
   * for, because a piece holds things a shot does not and there would otherwise
   * be no way to reach them: you would need a second shot before you could set
   * the standing prompt that the second shot is for.
   *
   * The pin only ever adds the strip. It cannot take one away, so the guarantee
   * the content rule makes — that a face never hides a field it still queues —
   * is not something a preference can switch off.
   */
  showsStrip() {
    return !this.loneShot() || !!this.face?.pinned();
  }

  loneShot() {
    const piece = this.timeline;
    return piece.segments.length === 1
      && !S.isClip(piece.segments[0])
      && !(piece.prompt || "").trim()
      && !(piece.soundscape || "").trim()
      && !(piece.music || "").trim()
      && !(piece.assets?.length)
      && !this.heldLoras().length;
  }

  /** The piece LoRAs the shot face has no slot for. The turbo entry is not one
   *  of them: it lives on the piece because turbo is a run-level switch, but
   *  the shot face wears it in full — the lit turbo pill names the file, the
   *  quality picker sets its steps, the weights popover picks it. Counting it
   *  here made throwing turbo on the Creator face flip the node onto the strip
   *  and hold it there, which read as a face that could not be left. */
  heldLoras() {
    const turboFile = this.timeline.turbo?.lora;
    return (this.timeline.loras ?? []).filter((entry) => entry.name !== turboFile);
  }

  /** The editor this body is currently wearing, if it is wearing one. Named to
   *  match `PreStageBody.editor`: both are a body that sometimes *is* a
   *  `CreatorEditor` and sometimes holds one. */
  get editor() { return this.faceEditor; }

  /** The piece-view toggle's wiring, for whichever face is drawing it. Null when
   *  the piece has more than one shot: there is no shot face for it to go back
   *  to, so a control offering one would be a lie. */
  pieceView() {
    if (!this.face) return null;
    if (this.emptyPiece()) {
      // Nothing on the strip is a shot not yet written: going back to the shot
      // face starts the blank one it edits.
      return {
        shown: () => true,
        toggle: () => { this.firstShot(); this.face.pin(false); this.commit(); },
      };
    }
    if (!this.loneShot()) return null;
    return {
      shown: () => this.showsStrip(),
      toggle: () => { this.face.pin(!this.face.pinned()); this.render(); },
    };
  }

  /** A strip with every card deleted and nothing set on the piece either. It
   *  stays empty — the strip window shows its add tile — until the face is
   *  turned back to a shot, which is the one thing that puts a card on it. */
  emptyPiece() {
    return !this.timeline.segments.length && !this.pieceHolds().length;
  }

  dropFaceEditor() {
    this.faceEditor?.destroy();
    this.faceEditor = null;
  }

  /**
   * The one shot's editor, on the node's face.
   *
   * The Creator node's body, unchanged, because it *is* the Creator node's body
   * — the same class the strip opens a card with, mounted on the face instead of
   * in a window. What it is told that a card is not: it owns the node (so it
   * draws the sampler row, the weights pill and the stage), and its canvas and
   * weights live one level up on the piece.
   *
   * Built once per segment object and kept, because it holds a contenteditable
   * with a caret in it: rebuilding it on every commit would take the caret away
   * mid-sentence, which is the whole reason `CreatorEditor` refills hosts rather
   * than re-rendering itself.
   */
  faceBody() {
    const segment = this.timeline.segments[0];
    if (this.faceEditor?.state === segment) return this.faceEditor;
    this.dropFaceEditor();
    this.faceEditor = new CreatorEditor({
      state: segment,
      // The canvas, the weights and the turbo switch are the piece's, exactly as
      // they are for a strip of twenty. Being the only shot changes nothing
      // about where they live — which is what makes growing a second one a
      // matter of adding a card and not of moving any settings.
      piece: this.timeline,
      // The face's rail is the family's stack — it is where a pin is made.
      pinFamily: () => S.pieceFamily(this.timeline),
      // The face is wearing the piece's only card, and the piece is what a cast
      // member is cast into — see the window's own hook of the same name.
      castFromLibrary: (member) => {
        const subject = P.addSubjectToPiece(member, this.timeline);
        if (!subject) return null;
        this.commit();
        return subject.handle;
      },
      onCommit: () => this.commit(),
      // The face wears the piece's first card, so that is the pass it shows.
      compiledPrompt: () => compiledFor(this.timeline, 0, this.pieceSeed()),
      // The face wears card 1, and a `{day|night}` on it chooses as card 1.
      varies: () => ({ seed: S.segmentSeed(segment) ?? this.pieceSeed(), card: 1 }),
      samplingWidgets: this.widgets,
      onWidgetChange: this.onWidgetChange,
      nodeId: this.nodeId,
      // The node's, so a render lands in the satellite the body already owns
      // rather than in a second stage listening for the same previews.
      stage: this.stage,
      setRoute: (route) => { this.timeline.models.route = route; this.commit(); },
      preStage: this.preStage,
      fullscreen: this.fullscreen,
      pieceView: this.pieceView(),
      // The piece's, not this shot's: the face is wearing the only card, but
      // what you save from a node is the node. Growing a second shot changes
      // nothing about it, which is the same promise the canvas and the weights
      // already make.
      presetTarget: () => this.presetTarget(),
      // The piece's, for the same reason: the face is wearing the only card,
      // but what Clear empties is the node.
      clearTool: () => [this.clearTool()],
      // One card of a piece, refined against the piece — the same target the
      // strip gives a card, because that is what this is. The route knows a
      // piece of one segment has no cut times of its own and asks the model for
      // the cuts, which is what the Creator always did.
      refineTarget: () => ({
        kind: "segment",
        index: 0,
        data: JSON.parse(S.serializeTimeline(this.timeline)),
      }),
      // No `onRefined`: with no strip there is nothing above this shot for the
      // soundscape and the score to belong to, so the editor keeps its own audio
      // fields and writes them onto the segment. Setting the *piece's* is what
      // the strip face is for, and doing it is what takes you there.

      // The next shot, as a pill in the row that already carries the piece's
      // other two controls. See `CreatorEditor.renderGrowPill`.
      growShot: {
        full: () => this.timeline.segments.length >= S.MAX_SEGMENTS,
        fullTitle: () => t("This piece is at its limit of {count} shots.",
                           { count: S.MAX_SEGMENTS }),
        add: () => this.growIntoStrip(),
      },
    });
    return this.faceEditor;
  }

  /**
   * One shot becomes two, and the strip opens over it.
   *
   * The face does not mutate behind the user. They have been writing in the box
   * on it, and replacing that box with a summary at the moment they ask for more
   * room would be taking the writing surface away as a reward for wanting one.
   * So the window arrives instead: card 1 is the shot they wrote, card 2 is the
   * new one, open and ready. They watch the promotion happen in the place the
   * new thing lives, and the face has changed by the time they close it.
   *
   * The new card is `continuingSegment` — a live seam on both tracks with a
   * medium blend — because that is already what appending to the strip gives
   * you, and the face must not be a second answer to a question the strip has
   * answered.
   */
  growIntoStrip() {
    if (this.timeline.segments.length >= S.MAX_SEGMENTS) return;
    this.timeline.segments.push(S.continuingSegment(this.timeline));
    this.commit();
    this.open({ edit: this.timeline.segments.length - 1 });
  }

  /** The library as a look picker, this render's frame in the wipe; a pick
   *  writes the guide-LoRA block and queues the node — see `restyle.js`. */
  restyle({ queue = true } = {}) {
    const source = stageSource(this.stage?.result);
    return openRestyle({
      target: this.timeline, family: S.pieceFamily(this.timeline),
      frame: source ? stillUrl(source) : null,
      commit: () => this.commit(),
      nodeId: queue ? this.nodeId : null,
    }).then(() => this.render());
  }

  commit() {
    S.syncTimeline(this.timeline);
    S.ensureCardIds(this.timeline);
    // Removing or disabling the turbo LoRA anywhere — the global stack's
    // manager included — is switching turbo off, and the sampler row has to
    // come back before the blob is written with `on` still in it.
    Turbo.sync(this.timeline, this.widgetIO());
    this.write(S.serializeTimeline(this.timeline));
    this.render();
  }

  /**
   * What the preset library can save from this node and apply back to it.
   *
   * The cover comes off the stage rather than being asked for: the `executed`
   * message stamped with this node's id is already sitting in `stage.result`, so
   * the render this preset was saved from is the render on the card. Nothing to
   * guess and no best frame to pick — and it only ever fills a cover, never
   * replaces one somebody chose.
   *
   * Apply goes through `commit`, which is what runs `syncTimeline`: a restored
   * strip whose durations can no longer afford their seams has them pruned on
   * the way in, rather than failing at queue time.
   */
  /** Where a render's settings land from the gallery — see
   *  `slate.settingsHome`. The whole piece: this is the node's own gallery. */
  settingsHome() {
    return settingsHome({
      kind: "video",
      nodeId: () => this.nodeId?.() ?? null,
      target: () => this.presetTarget(),
      io: () => this.widgetIO(),
    });
  }

  presetTarget() {
    return {
      scope: "piece",
      label: t("this piece"),
      family: () => S.pieceFamily(this.timeline),
      vae: () => this.timeline.models?.vae ?? "",
      families: () => castFamilies(S.pieceFamily(this.timeline), this.timeline.models?.vae ?? "",
                                  rememberedWeights()),
      // See `Timeline.pieceTarget`: the scissors in the library's attach flow.
      // Built here rather than borrowed — `poolPlate` is the window's, and
      // this target is the node body's.
      plate: () => {
        const spec = S.plateSpec(this.timeline, this.frame());
        return spec ? { ...spec, sheet: false } : null;
      },
      capture: () => ({
        data: P.capturePiece(this.timeline, this.widgetIO()),
        cover: P.coverFromResult(this.stage?.result),
        defaultName: (this.timeline.prompt || this.timeline.segments[0]?.prompt || "")
          .trim().split("\n")[0].slice(0, 48),
      }),
      apply: (body, keys, from) => {
        P.applyToPiece(body, keys, this.timeline, this.widgetIO(), { from });
        this.commit();
      },
    };
  }

  /** The strip, over the node. `edit` opens a card's window with it — what the
   *  face does on the way from one shot to two, so the new card is where the
   *  writing already is. */
  open({ edit = null } = {}) {
    openTimeline({
      timeline: this.timeline,
      onCommit: () => this.commit(),
      edit,
      // Lent so a card's preset can carry the sampler row — see `Timeline.io`.
      io: () => this.widgetIO(),
      widgets: this.widgets,
      ...(this.nodeId != null ? { queue: () => queueNode(this.nodeId()) } : {}),
      stage: this.stage,
      run: () => this.currentRun(),
      opened: (reel) => { this.reel = reel; this.stage.onChange = () => reel.staged(); },
    }).then(() => { this.reel = null; this.stage.onChange = null; });
  }

  value(name, fallback) {
    return this.widgetIO().value(name, fallback);
  }

  /** The number the node will queue — the modal's `pieceSeed`, on the body:
   *  the seed is the one sampler setting that is still a widget, and this is
   *  the class that holds the widgets. */
  pieceSeed() {
    return Number(this.value("seed", 0)) || 0;
  }

  /** The sampler row's `{value, set}` pair.
   *
   *  Still called `widgetIO` everywhere that draws the row, and still answers to
   *  the same names, but the values live in the piece now rather than on the
   *  node — see `sampling.blobIO`. The seed is the exception and stays a widget.
   */
  widgetIO() {
    return blobIO(
      () => this.widgets,
      () => this.timeline.sampling,
      // Written straight out rather than through `commit`: commit calls
      // `Turbo.sync`, which sets pills, which would come back here — and the
      // pair would bounce between them. Nothing else in commit applies to a
      // sampler setting anyway; `syncCanvas` is about the strip.
      (block) => { this.timeline.sampling = block; this.write(S.serializeTimeline(this.timeline)); },
      () => this.onWidgetChange?.());
  }

  /** Write the row. Through the same pair as the turbo switch and the preset
   *  menu — the values are in the blob, and the seed rides on to its widget from
   *  there. `blobIO` does not redraw on write; this body does. */
  set(name, value) {
    this.widgetIO().set(name, value);
    this.render();
  }

  render() {
    // One shot wears its own editor; anything more wears the strip's summary.
    // Which of them, on every render, off `loneShot` — there is no mode stored
    // anywhere and nothing to get out of step with the piece.
    if (!this.showsStrip()) {
      const editor = this.faceBody();
      editor.render();
      // The editor's root *is* the body here — it brings its own rail, panel
      // and sampler row, and its `growShot` puts the next shot in the tail of
      // the pill row.
      if (this.root.firstChild !== editor.root) this.root.replaceChildren(editor.root);
      // The editor's root is a body in its own right, padding and all. Hosting
      // it inside another one would inset the face twice — which is a narrower
      // face than the strip's on a node of the same width, and it showed as the
      // sampler pills wrapping a row earlier here than there.
      this.root.classList.add("hosting");
      this.laneFit?.disconnect();
      // A host drawing something derived from this piece — the editor's empty
      // frame — has no other way to hear that the canvas or the length changed.
      this.onRender?.();
      return;
    }
    this.root.classList.remove("hosting");
    this.dropFaceEditor();
    // Same order as the Creator: the rail, what you are asking for, then how it
    // is run. The picture is beside the node, in the satellite.
    this.root.replaceChildren(this.renderRail(), this.renderPanel(),
                              // Wrapped rather than mounted bare: the fullscreen shell folds
                              // the sampler away in its simple view by this class, and a bar
                              // parented straight to the root gave it nothing to fold.
                              el("div", { class: "mmc-sampling-host" }, [this.renderSampling()]));
    // The reel is the one part of the body whose reading depends on the width
    // it ended up with, so it is fitted after it is in the document — once now,
    // and again from its own observer whenever the node is resized.
    this.laneFit?.disconnect();
    this.laneFit?.observe(this.lane);
    this.fitLane();
    this.onRender?.();
  }

  /**
   * The picture this piece is about to make: the canvas, and how long it runs.
   *
   * For a host that has to draw the frame before there is anything in it — the
   * fullscreen shell's dock, which is a column of nothing until the first
   * render lands. A lone shot answers through the editor on its face, because
   * that shot's canvas can be a reference's rather than the piece's; a strip
   * answers from the geometry its summary already prints.
   */
  frame() {
    if (!this.showsStrip()) return this.faceBody().frame();
    const { width, height } = timelineGeometry(this.timeline);
    return { width, height, seconds: S.timelineSeconds(this.timeline) };
  }

  /**
   * The Creator's rail, on the Timeline node.
   *
   * The same two clusters and the same reading: everything on the left acts on
   * this piece, the pair on the right belongs to the machine. What differs is
   * only what "a reference" means here — a Timeline has no single generation to
   * attach one to, so the three add tools fill the *piece's* reference pool,
   * the one the modal's shelf shows. A pool asset rides into exactly the
   * segments whose text cites its @handle, so attaching one here is the first
   * half of the job and the citation is the second; the tools say so rather
   * than leaving a file attached to nothing with no hint of what is missing.
   *
   * The LoRA tool manages the timeline's own stack, which is patched onto every
   * segment — the same stack the modal's LoRAs pill opens.
   */
  renderRail() {
    const tool = (label, iconName, title, onclick) =>
      el("button", { class: "mmc-tool", title, onclick },
         [el("span", { class: "mmc-tool-icon" }, [icon(iconName)]), el("span", { text: t(label) })]);

    // The pool is references, so it is gone on a family that reads none — see
    // `CreatorEditor.renderRail` for why gone rather than greyed. The sound
    // lane is not affected and is not here: a track is laid on the piece's
    // clock, not attached to a shot.
    const takesRefs = S.takesReferences(this.timeline);

    return el("div", { class: "mmc-rail" }, [
      el("div", { class: "mmc-rail-group" }, [
        // Per kind — see `CreatorEditor.renderRail`. A family whose references
        // are a sheet of stills offers the image tool alone.
        ...(takesRefs ? [["image", "Add image", "image"], ["video", "Add video", "video"],
                         ["audio", "Add audio", "audio"]]
                          .filter(([kind]) => S.takesKind(this.timeline, kind))
                      : []).map(([kind, label, iconName]) =>
          tool(label, iconName,
               t("Attach a {kind} to the whole piece. Cite its @handle in a segment's "
               + "prompt — or in the global one, for every segment — to use it there.",
                 { kind: t(kind) }),
               () => this.addPoolAssets(kind))),
        tool("Add LoRA", "effect",
             t("Manage the LoRAs patched onto every segment of this timeline"),
             () => this.manageLoras()),
        // End of the cluster, and the end of the piece: everything above it
        // adds to the scene, and this is the one that takes the scene back.
        this.clearTool(),
      ]),
      el("div", { class: "mmc-rail-group" }, [
        tool("Presets", "star",
             t("Save this setup so you can put it back, or apply one you saved before"),
             () => openPresetLibrary({ target: this.presetTarget() }).then(() => this.render())),
        tool("Gallery", "gallery",
             t("Browse, organize and attach finished renders and pre-stage stills"),
             () => openPicker({
               kinds: ["renders"], kind: "renders", viewOnly: true,
               home: this.settingsHome(),
               capacity: () => ({ used: 0, max: 0, filesLeft: 0 }),
             })),
        tool("Settings", "gear",
             t("Preferences for this ComfyUI — output quality. Not saved into the workflow."),
             // Re-rendered on close: the page can change what the sampler row
             // draws (the shift pills' visibility), and Done should look done.
             () => openSettings().then(() => this.render())),
      ]),
    ]);
  }

  /**
   * Start the next scene: empty what was written, keep the machine.
   *
   * Built here for both faces — the strip's rail draws it directly, and the
   * lone shot's is handed the same factory — because what it empties is the
   * piece either way, and the shot editor holds one card of one.
   */
  clearTool() {
    return clearButton({
      written: S.pieceWritten(this.timeline),
      // Nothing else to do about the hosted editor: the strip is a new array of
      // new cards, and `faceBody` rebuilds off exactly that identity.
      run: () => { S.clearPiece(this.timeline); this.commit(); },
    });
  }

  /** The piece's reference pool, filled from the node body. The same entry the
   *  modal's own "+ Add" builds — see `Timeline.addPoolAssets`, which this is
   *  the node-side twin of. */
  async addPoolAssets(kind) {
    const chosen = await openPicker({
      kinds: [kind, "renders", "refmods"],
      kind,
      capacity: () => ({ used: 0, max: S.refCaps(this.timeline).files, filesLeft: S.refCaps(this.timeline).files }),
      // `sheet` off, as on the modal's pool picker: the pool serves many
      // segments, so loose pictures stay loose and Connect builds a sheet.
      ...(kind === "image" && S.plateSpec(this.timeline, this.frame())
        ? { plate: { ...S.plateSpec(this.timeline, this.frame()), sheet: false } } : {}),
    });
    if (!chosen?.length) return;
    for (const picked of chosen) {
      // As on the modal's own "+ Add": a sheet is one pool reference, numbered
      // the pool's way. See `Timeline.addPoolAssets`.
      if (picked.plate) {
        this.timeline.assets.push(S.plateEntry(
          picked, S.takenHandles(this.timeline), { plate: "ref", panel: "ref" }));
        continue;
      }
      const entry = {
        handle: S.nextPoolHandle(this.timeline),
        kind: picked.kind,
        role: "reference",
        filename: picked.path,
        ref_size: "max",
      };
      if (picked.kind === "video") entry.track = S.trackFor(picked);
      if (picked.trim) entry.trim = picked.trim;
      if (picked.crop) entry.crop = picked.crop;
    if (picked.crop) entry.crop = picked.crop;
      this.timeline.assets.push(entry);
    }
    this.commit();
  }

  async manageLoras(entry = null) {
    await openLoras({
      state: this.timeline,
      family: S.pieceFamily(this.timeline),
      targets: S.timelineCheckpoints(this.timeline),
      scope: "piece",
      reveal: entry?.name ?? null,
      onChange: () => this.commit(),
    });
    this.commit();
  }

  renderPanel() {
    const segments = this.timeline.segments;
    const single = S.isSingle(this.timeline);
    const passes = S.passes(this.timeline);
    const seconds = S.timelineSeconds(this.timeline);
    probeAspectSizes(this.timeline, () => this.render());
    const { width, height, ratio, fromInput } = timelineGeometry(this.timeline);
    const rules = rulesFor(S.pieceFamily(this.timeline));
    const prompt = (this.timeline.prompt || "").trim();
    const globalLoras = S.activeGlobalLoras(this.timeline);
    const audio = [
      ...(this.timeline.soundscape?.trim() ? [t("soundscape")] : []),
      ...(this.timeline.music?.trim() ? [t("music")] : []),
    ];

    return el("div", { class: "mmc-panel mmc-tl-summary" }, [
      // The prompt's room, not the prompt: the text is clamped to six lines
      // (see the stylesheet for why), so this wrapper is what soaks up the
      // panel's free height on a tall node — the reel and the pills dock to
      // the bottom, beside the sampler rows, the way the shot face's writing
      // box already pushes its controls down. All of it opens the strip.
      el("div", { class: "mmc-tl-summary-room", onclick: () => this.open() }, [
        el("div", {
          class: `mmc-tl-summary-prompt${prompt ? "" : " empty"}`,
          text: prompt || (single
            ? t("No global prompt yet — the standing description that opens Shot 1.")
            : t("No global prompt yet — the standing description every segment inherits.")),
        }),
      ]),
      // The one picture of the timeline the node has room for: blocks at their
      // real relative lengths, so a 10-second shot is visibly twice a 5. Merged
      // shots close ranks under one outline — the same reading as the modal's
      // casing, at a tenth the size.
      // Always a lane: `syncTimeline` keeps a piece at one shot or more, and a
      // piece of one wears that shot's editor rather than this summary — so by
      // the time anything gets here there are at least two cards to draw.
      this.renderLane(passes),
      el("div", { class: "mmc-pills" }, [
        // The model leads even the render mode, which is the one thing about
        // this node that changes what all the other numbers mean — because the
        // family is what decides which modes there are. The one control in a row
        // of readouts, and deliberately: it is the same slot in the same place
        // as on the strip's bar and on a shot's face, so switching architecture
        // never depends on which of the three you happen to be looking at.
        familyPill({ piece: this.timeline, onChange: () => this.commit() }),
        el("span", {
          class: "mmc-pill mmc-pill-static",
          title: single
            ? t("One generation: the segments are the shots of a single description, cut times and all.")
            : passes.length === segments.length
              ? t("One generation per segment, joined end to end.")
              : t("One generation per pass, joined end to end. A pass holding several "
                + "shots generates them at once, with the cuts written into its description."),
        }, [
          icon("timeline", 16),
          el("span", { text: single ? t("one pass")
              : passes.length === segments.length ? t("chained")
                : t("{count} passes", { count: passes.length }) }),
          el("span", {
            class: "mmc-pill-sub",
            text: single
              ? t(segments.length === 1 ? "{count} shot" : "{count} shots", { count: segments.length })
              : t(segments.length === 1 ? "{count} segment" : "{count} segments", { count: segments.length }),
          }),
        ]),
        el("span", { class: "mmc-pill mmc-pill-static",
                     title: S.hasAutoDuration(this.timeline)
                       ? t("An estimate: a shot on auto is measured by the model "
                         + "while it renders, so the finished length is not known "
                         + "until it has.")
                       : t("The finished clip's length at {fps} fps",
                           { fps: rules.fps }) }, [
          icon("clock", 16),
          el("span", { text: S.hasAutoDuration(this.timeline)
            ? `~${seconds.toFixed(1)} s` : `${seconds.toFixed(1)} s` }),
        ]),
        el("span", {
          class: "mmc-pill mmc-pill-static",
          title: single
            ? t("The canvas the one generation runs at.")
            : t("Shared by every segment — they are joined end to end and have to match."),
        }, [
          el("span", { text: fromInput ? describeRatio(ratio, rules) : this.timeline.aspect }),
          el("span", { class: "mmc-pill-sub", text: `${width} × ${height}` }),
        ]),
        // Only when there are any: an empty pill would say the timeline has a
        // LoRA feature, which is the modal's job to say, not the node's.
        ...(globalLoras.length ? [el("span", {
          class: "mmc-pill mmc-pill-static",
          title: (single
            ? t("Patched onto the one generation, in front of whatever the shots add.")
            : t("Patched onto every segment, in front of whatever that segment adds."))
            + "\n" + globalLoras.map((entry) => entry.name).join("\n"),
        }, [
          icon("effect", 16),
          el("span", { text: t(globalLoras.length === 1 ? "{count} LoRA" : "{count} LoRAs",
                               { count: globalLoras.length }) }),
          // Which ones, not just how many. The face has no room for the chips
          // the strip window draws, and a bare count is a stack you have to
          // open two things to identify.
          el("span", { class: "mmc-pill-sub", text: globalLoras.map(loraBase).join(", ") }),
        ])] : []),
        // Only when there are any, like the LoRAs: the modal introduces the
        // feature, the node only reports what this timeline uses.
        ...(this.timeline.assets?.length ? [el("span", {
          class: "mmc-pill mmc-pill-static",
          title: t("References attached to the piece itself, cited by @handle from "
               + "the segments where they appear."),
        }, [
          icon("image", 16),
          el("span", { text: t(this.timeline.assets.length === 1
            ? "{count} piece ref" : "{count} piece refs",
            { count: this.timeline.assets.length }) }),
        ])] : []),
        ...(audio.length ? [el("span", {
          class: "mmc-pill mmc-pill-static",
          title: t("The Context-IR audio fields this timeline sets for every segment."),
        }, [icon("audio", 16), el("span", { text: audio.join(" · ") })])] : []),
        el("button", {
          class: "mmc-tl-open",
          title: t("Open the timeline: the global prompt, the segments, and what happens between them"),
          onclick: () => this.open(),
        }, [icon("sliders", 16), el("span", { text: t("Edit timeline") })]),
        ...(this.fullscreen ? [el("button", {
          class: "mmc-pill mmc-fs-enter",
          title: t("Draw this piece over the whole window. The node stays in the graph "
                 + "and is queued exactly as it is now; Escape brings you back."),
          onclick: () => this.fullscreen(),
        }, [icon("expand", 16), el("span", { text: t("Fullscreen") })])] : []),
        ...(this.pieceView() ? [this.renderPieceViewPill()] : this.renderHeldPieceViewPill()),
        ...(this.preStage ? [this.renderPreStagePill()] : []),
      ]),
    ]);
  }

  /** The way back to the shot, on the strip face. Drawn only while there is one
   *  shot to go back to, or none and a blank one to start — see `pieceView`. Deliberately the pill the shot face
   *  draws, in the same place and with the same words: one control with two
   *  states, not two controls that happen to be opposites. */
  renderPieceViewPill() {
    const view = this.pieceView();
    return el("button", {
      class: "mmc-pill mmc-piece-toggle on",
      "aria-pressed": "true",
      title: t("Showing the whole piece. Click to go back to the shot."),
      onclick: () => view.toggle(),
    }, [icon("timeline", 16), el("span", { text: t("Timeline") })]);
  }

  /** What a one-shot piece has set that a shot's face has no slot for — the
   *  fields whose presence keeps this node on the strip. */
  pieceHolds() {
    const piece = this.timeline;
    return [
      ...((piece.prompt || "").trim() ? [t("the global prompt")] : []),
      ...((piece.soundscape || "").trim() ? [t("the soundscape")] : []),
      ...((piece.music || "").trim() ? [t("the music")] : []),
      ...(piece.assets?.length ? [t("the reference pool")] : []),
      ...(this.heldLoras().length ? [t("the piece's LoRAs")] : []),
    ];
  }

  /**
   * The same pill, dead, when the piece is one shot but cannot wear its face.
   *
   * The rule is the face never hides a field it still queues, so a piece
   * carrying a global prompt has no shot face to go back to — but a control
   * that simply vanishes reads as a way back that is broken. Drawn dead
   * instead, naming exactly what holds the strip open, which is also the
   * instruction for getting back: empty those fields and the toggle wakes.
   * A piece of several shots draws nothing — there is no shot to go back to
   * and nothing a user could empty to make one.
   */
  renderHeldPieceViewPill() {
    const segments = this.timeline.segments;
    if (!this.face || segments.length > 1 || S.isClip(segments[0])) return [];
    const holds = this.pieceHolds();
    if (!holds.length) return [];
    return [el("button", {
      class: "mmc-pill mmc-piece-toggle on",
      "aria-pressed": "true",
      disabled: true,
      title: t("Showing the whole piece. The shot face has no place for {fields}, "
             + "so the way back opens when they are emptied.",
             { fields: holds.join(" · ") }),
    }, [icon("timeline", 16), el("span", { text: t("Timeline") })])];
  }

  /**
   * The reel: every shot as a block of the width its own length earns.
   *
   * Two readings out of one markup, chosen by how much room a block gets — see
   * `fitLane`. Roomy, a block is a labelled tile: its number, its length, a link
   * glyph where the seam continues. Crowded, the labels come off and the row
   * closes into a single band with the shots divided by frame lines, numbered
   * along its edge the way footage counters run down the edge of film rather
   * than across the picture. The proportions are the same band either way; what
   * changes is only what there is room to print on it.
   */
  renderLane(passes) {
    this.lane = el("div", { class: "mmc-tl-lane" }, passes.map((pass) => {
      const { at, total } = S.cutTimes(pass.segments);
      const shared = pass.segments.length > 1;
      return el("div", {
        // The run takes the width its shots add up to, and they divide it
        // between themselves — so the lane stays proportional whatever is
        // merged into what.
        class: `mmc-tl-run${shared ? " on" : ""}`,
        style: { flexGrow: String(Math.max(1, total)) },
      }, pass.segments.map((segment, offset) => {
        const index = pass.start + offset;
        // A clip's length is the window that plays, not the file's, and it has
        // no mode: nothing is sampled, so there is no route to name.
        const seconds = S.segmentSeconds(segment);
        const what = S.isClip(segment) ? t("clip") : S.mode(segment, this.timeline);
        // A seam only exists in front of a pass. Inside one the cut is a line
        // of the description, so the block reads as a shot rather than a join.
        const continues = !offset && index > 0 && S.continues(segment);
        // Crowded, the reel marks the exception rather than the rule: a strip
        // whose seams nearly all continue is one unbroken take, and colouring
        // every one of them says only that the feature exists. The hard cut is
        // the thing that happens rarely, so the hard cut is what gets drawn —
        // as a real break in the band, which is what it is.
        const cut = !offset && index > 0 && !continues;
        // ...and the same picture the strip draws, at a tenth the size: a block
        // filled in because the film exists, hollow because it does not. What
        // the node's one honest picture of the piece is for is knowing where
        // the shoot has got to without opening the strip.
        const head = pass.segments[0];
        const state = S.isHeld(head) ? (S.takeOn(head) ? " kept" : " unshot") : "";
        return el("div", {
          class: `mmc-tl-tick${continues ? " on" : ""}${cut ? " cut" : ""}${state}`,
          style: { flexGrow: String(Math.max(1, seconds)) },
          title: shared
            ? (offset
                ? t("Shot {n} · {s} s · cuts in at {time} of this pass",
                    { n: index + 1, s: seconds, time: S.shotTime(at[offset]) })
                : t("Shot {n} · {s} s · opens a pass of {count}",
                    { n: index + 1, s: seconds, count: pass.segments.length }))
            : (continues
                ? t("Segment {n} · {s} s · {mode} · continues from segment {from}",
                    { n: index + 1, s: seconds, mode: what,
                      from: S.continueSource(segment, index) })
                : t("Segment {n} · {s} s · {mode} · hard cut",
                    { n: index + 1, s: seconds, mode: what })),
        }, [
          ...(continues ? [icon("link", 13)] : []),
          el("span", { class: "mmc-tl-tick-n", text: String(index + 1) }),
          el("span", { class: "mmc-tl-tick-s", text: `${Math.round(seconds * 10) / 10}s` }),
        ]);
      }));
    }));
    this.edge = el("div", { class: "mmc-tl-edge" });
    // The observer is the lane's, not the render's: the node is resizable, and
    // dragging it narrower is exactly how a roomy strip becomes a crowded one.
    this.laneFit ??= new ResizeObserver(() => this.fitLane());
    return el("div", { class: "mmc-tl-reel", onclick: () => this.open() }, [this.lane, this.edge]);
  }

  /**
   * Measure the lane and pick the reading that fits.
   *
   * A block needs about 46 px to hold "12" and "15s" side by side, and about
   * 30 to hold the number alone — under which the same markup draws the digits
   * of one shot over the digits of the next, which is what a ten-minute strip
   * of forty-seven shots looked like. So nothing is guessed from the count:
   * the lane asks how wide its own blocks came out and gives up one label at a
   * time, in the order of what it can afford to lose — the length first, since
   * a band drawn to scale is already a picture of the lengths.
   */
  fitLane() {
    const lane = this.lane;
    if (!lane?.isConnected) return;
    const blocks = [...lane.querySelectorAll(".mmc-tl-tick")];
    const width = lane.clientWidth;
    // Called once before layout on every render; the observer calls back the
    // moment there is a width to measure.
    if (!blocks.length || !width) return;

    // The average block, not the narrowest: whether this is a strip of tiles or
    // a band is one decision about the whole lane, and a single three-second
    // shot among twenty long ones should not make that decision for it.
    const per = width / blocks.length;
    const dense = per < 46;
    let crowded = per < 30;

    // What the number itself needs — shot 7 fits where shot 47 does not, and
    // dropping a digit that would have fitted reads as a blank block rather
    // than as a tight one. Measured from the block at full label, never from
    // the block as it was left last time: a hidden label makes a block
    // narrower, so measuring the trimmed one would find it narrower still and
    // never give the label back. Laid-out width, not painted width:
    // getBoundingClientRect() reports the box *after* every transform on the
    // way up the tree, and the fullscreen card is turned on its vertical axis
    // while it swaps steps — so a fit that ran during the turn measured every
    // block as a few pixels wide, went bare on all of them, and stayed that
    // way. offsetWidth is the layout answer, which is the question.
    for (const block of blocks) block.classList.remove("narrow", "bare");
    const bare = (block) => {
      const digits = block.querySelector(".mmc-tl-tick-n")?.textContent.length ?? 2;
      return block.offsetWidth < 16 + 9 * digits;
    };
    // On a band, all the numbers or none of them. A tile with no number among
    // tiles that have them is a tile that is short; a bare cell at the head of
    // a band with no gaps in it is a band that looks cut off at the edge —
    // three short opening shots on a seventeen-shot piece read as "3 4 5 …"
    // with something missing before it. So one short shot on a band takes the
    // whole band to the edge reading, where the counting is done beside the
    // film and no cell has to hold a numeral.
    if (dense && !crowded && blocks.some(bare)) crowded = true;
    lane.classList.toggle("dense", dense);
    lane.classList.toggle("crowded", crowded);

    if (!crowded) {
      // Above that, each block answers for itself: whether the lane is a strip
      // of tiles or a band is one decision about the whole lane, but what fits
      // on a block is a question about that block. A three-second shot beside a
      // twenty is a quarter of its width, and giving both the same labels is
      // how the short one ends up with a clipped one.
      this.edge.replaceChildren();
      for (const block of blocks) {
        block.classList.toggle("narrow", block.offsetWidth < 46);
        block.classList.toggle("bare", bare(block));
      }
      return;
    }

    // Edge code: a numeral every few shots, at the widest cadence that still
    // keeps two numbers well clear of each other. Sparse on purpose — its job
    // is to make the band countable, not to name every block on it.
    const step = [1, 2, 5, 10, 20, 25, 50].find((n) => per * n >= 56) ?? 100;
    // Layout again, and for the same reason — nothing between the lane and a
    // block is positioned, so the two offsets are measured from the same corner
    // and the difference is the block's distance along the lane.
    const origin = lane.offsetLeft;
    this.edge.replaceChildren(...blocks.flatMap((block, index) => (index % step ? [] : [
      el("span", {
        class: "mmc-tl-edge-n",
        style: { left: `${block.offsetLeft - origin}px` },
        text: String(index + 1),
      }),
    ])));
  }

  /** Same pill as the Creator's — see `CreatorEditor.renderPreStagePill`. */
  renderPreStagePill() {
    const on = this.preStage.active();
    return el("button", {
      class: `mmc-pill mmc-prestage-toggle${on ? " on" : ""}`,
      title: on
        ? t("The pre-stage node on the left generates stills for this timeline — the opening "
          + "frame, the closing frame, references. Click to remove it.")
        : t("Add a pre-stage: an image node (Krea 2 / Ideogram 4) at this node's left edge whose "
          + "stills land on the timeline's shots with one click."),
      onclick: () => { this.preStage.toggle(); this.render(); },
    }, [icon("image", 16), el("span", { text: t("pre-stage") })]);
  }

  /**
   * Shot one, started if the strip is empty. A file handed to this node from
   * outside lands on the first card, and a piece whose cards were all deleted
   * still takes it — onto a new shot, which is what attaching it there asks for.
   */
  firstShot() {
    if (!this.timeline.segments.length) {
      this.timeline.segments.push(S.emptySegment());
      S.syncTimeline(this.timeline);
      S.ensureCardIds(this.timeline);
    }
    return this.timeline.segments[0];
  }

  /**
   * A finished pre-stage still, pushed into the timeline by the neighbour's
   * result chips. The roles land where one pass would put them — a start frame
   * opens shot 1, an end frame closes the last shot, a reference joins shot 1 —
   * under each shot's own capacity and exclusivity rules. Returns a refusal
   * message, or null on success.
   */
  attachFromPreStage({ role, filename }) {
    this.firstShot();
    const shots = this.timeline.segments;
    const index = role === "last_frame" ? shots.length - 1 : 0;
    const segment = shots[index];
    const where = t("segment {n}", { n: index + 1 });
    if (role === "reference") {
      const blocked = S.blockedReason(segment, "reference");
      if (blocked) return t("{where}: {blocked}", { where, blocked });
      const { used, max, filesLeft } = S.capacity(segment, "image", this.timeline);
      if (used >= max || filesLeft <= 0) {
        return t("{where}: no image slots left ({used}/{max} used).", { where, used, max });
      }
      segment.assets.push({
        handle: S.nextHandle(segment, "image"),
        kind: "image", role: "reference", filename, ref_size: "max",
      });
      this.commit();
      return null;
    }
    const blocked = S.blockedReason(segment, role);
    if (blocked) return t("{where}: {blocked}", { where, blocked });
    const existing = S.frameAsset(segment, role);
    if (existing) segment.assets = segment.assets.filter((a) => a.handle !== existing.handle);
    segment.assets.push({
      handle: S.nextHandle(segment, "image"),
      kind: "image", role, filename,
    });
    this.commit();
    return null;
  }

  /**
   * Shot one, started if the strip is empty. A file handed to this node from
   * outside lands on the first card, and a piece whose cards were all deleted
   * still takes it — onto a new shot, which is what attaching it there asks for.
   */
  firstShot() {
    if (!this.timeline.segments.length) {
      this.timeline.segments.push(S.emptySegment());
      S.syncTimeline(this.timeline);
      S.ensureCardIds(this.timeline);
    }
    return this.timeline.segments[0];
  }

  /**
   * A drawing off the ControlNet bench, attached to the shot it aims.
   *
   * On the body, not on the editor, because the body is what a caller outside
   * this node can reach: `mmcBody` is a `TimelineBody`, and the door the bench
   * looks for has to be on the object it is looking at. The editor version was
   * on `CreatorEditor` and on the strip window, and neither of those is what
   * `node.mmcBody` is — so the bench asked for a door that was never there and
   * drew the row without it, which is how a piece with a ControlNet came to
   * offer nowhere to send a clip.
   *
   * Shot one, which is where every other hand-off from outside this node lands
   * — see `attachFromPreStage`. A piece is a strip of cards and a file arriving
   * without a card named has to pick one; picking the first is the same answer
   * the pre-stage's chips already give.
   */
  takeGuide({ path, kind = "video", op = "", opId = null, trim = null }) {
    const segment = this.firstShot();
    // Through the editor where one is already built for this shot, so the
    // caret, the chips and the redraw are the editor's own. Straight onto the
    // blob otherwise: on a strip there is no card editor to route through, and
    // `commit` redraws whatever is in front.
    if (this.faceEditor?.state === segment) {
      return this.faceEditor.takeGuide({ path, kind, op: op || opId || "", trim });
    }
    if (!S.attachGuide(segment, this.timeline, { path, kind, op: op || opId || "", trim })) return;
    this.commit();
  }

  /**
   * A file handed to this node from outside, attached as a reference.
   *
   * Shot one for the same reason `takeGuide` uses it. Through the editor where
   * there is one, because `attachAssets` is what settles a clip's sound track
   * with the server — a reference video pushed onto the blob by hand would land
   * silent where a picked one lands with its audio on.
   */
  async takeReference(picked) {
    const segment = this.firstShot();
    if (this.faceEditor?.state === segment) {
      return this.faceEditor.attachAssets([picked]);
    }
    const blocked = S.blockedReason(segment, "reference");
    if (blocked) return;
    const entry = {
      handle: S.nextHandle(segment, picked.kind),
      kind: picked.kind,
      role: "reference",
      filename: picked.path,
      ref_size: "max",
    };
    if (picked.kind === "video") entry.track = S.trackFor(picked);
    if (picked.trim) entry.trim = picked.trim;
    if (picked.crop) entry.crop = picked.crop;
    segment.assets.push(entry);
    this.commit();
  }

  /**
   * The sampler row, shared with the Creator node — see `sampling.js`. Both
   * nodes own their sampler and declare the same widgets, so neither draws its
   * own version of this.
   */
  renderSampling() {
    return samplingBar({
      // See the Creator's own call: which controls the row has is the family's.
      family: S.pieceFamily(this.timeline),
      widgets: this.widgets,
      value: (name, fallback) => this.value(name, fallback),
      set: (name, value) => this.set(name, value),
      // Several generations mean the seed and the step count are asked of each
      // of them; one generation means they are asked once. The passes are the
      // generations, whatever the cards look like.
      perSegment: S.passes(this.timeline).length > 1,
      // The turbo switch, on the timeline's global stack: a speed-up belongs to
      // the run, which is the whole reason the global stack exists. Only where
      // the family declares a distillation at all — every number the switch
      // throws (the step counts, euler + beta, the flow shifts a distill was
      // trained against) is that family's, and a pill offering H3's on another
      // family's row is a shortcut into weights nobody has.
      // The VDN-H3 pill throws the switch too — the same container.
      container: this.timeline,
      turbo: S.turboOf(S.pieceFamily(this.timeline)) ? Turbo.turboPills({
        container: this.timeline,
        ...this.widgetIO(),
        onCommit: () => this.commit(),
      }) : [],
      // The guide switch, on the timeline's own block. Global for a reason of
      // its own rather than by analogy with the stack above: a guide is a clip
      // laid along the piece, and each pass takes its own seconds out of it —
      // so a per-card one would be asking the user to cut the drawing up by
      // hand along boundaries the strip already knows.
      guide: Guide.guidePills({
        container: this.timeline,
        onCommit: () => this.commit(),
      }),
      // A chained timeline legitimately runs some shots on one checkpoint and
      // some on the other, so the pill is asked about the set rather than
      // about one — a Ref2VA it never reaches for is not missing.
      //
      // The family that decides which files these are leads the bar above
      // instead of standing here — see `familyPill`.
      trailing: [
        // Only where the family has the pass, or where one is already on —
        // see the same gate, and the same reason, on the Creator's own row.
        ...(S.canDo(this.timeline, "face") || S.faceAnywhere(this.timeline)
          ? [facesPill({ target: this.timeline, commit: () => this.commit() })] : []),
        // The DLSS 5 refiner, family-neutral: it runs over decoded frames.
        neuralPill({ target: this.timeline, commit: () => this.commit(),
                     // TimelineBody has no geometry() method; the modal does.
                     geometry: () => timelineGeometry(this.timeline),
                     picture: () => stageSource(this.stage?.result) }),
        // The guide-LoRA pass, only where the family has it.
        ...(S.canDo(this.timeline, "guide_lora")
          ? [guideLoraPill({ target: this.timeline, commit: () => this.commit(),
                             onPickLook: () => this.restyle({ queue: false }) })] : []),
        weightsPill({
          piece: this.timeline,
          models: this.timeline.models,
          checkpoints: S.timelineCheckpoints(this.timeline),
          // Only when a shot on the strip actually runs the pass: a piece with
          // it on and every card opted out loads no detector, and a weights
          // pill saying one is missing would be reporting a file nothing opens.
          face: S.faceAnywhere(this.timeline),
          onChange: () => this.commit(),
          turbo: { container: this.timeline, widgetIO: this.widgetIO() },
        }),
      ],
    });
  }
}
