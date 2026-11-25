// The timeline modal: a global prompt, one canvas, and a strip of segments.
//
// The strip is the whole idea — cards laid out left to right, each as wide as
// its own duration, with the join between two of them saying whether the second
// cuts or continues. Everything inside a card is a whole generation, so opening
// one hands it to CreatorEditor unchanged: same rail, same @ prompt, same
// LoRAs, same routing badge. There is no reduced "segment UI" to keep in step
// with the node's, because there is only one editor.

import { api } from "../../../scripts/api.js";
import { viewUrl, primeSettings, stillUrl } from "./api.js";
import { openRestyle } from "./restyle.js";
import { castFamilies } from "./refmod.js";
import { clearButton } from "./clear.js";
import { el, icon, mountOverlay } from "./dom.js";
import { CreatorEditor } from "./editor.js";
import { t } from "./i18n.js";
import { settingsHome } from "./slate.js";
import { openLoras, loraBase } from "./loras.js";
import { openPicker } from "./picker.js";
import { openPresetLibrary } from "./presetlib.js";
import * as P from "./presets.js";
import { openSettings } from "./settings.js";
import { facesPill, neuralPill, guideLoraPill } from "./pills.js";
import { adopted, blobIO, samplingBar } from "./sampling.js";
import { Stage, stageSource } from "./stage.js";
import { watchSubmittedPrompts, submittedPrompt, queueNode } from "./queue.js";
import { familyPill, weightsPill, loadCatalog, adoptWeights, rememberedWeights } from "./models.js";
import * as S from "./state.js";
import * as Turbo from "./turbo.js";
import * as Guide from "./guide.js";
import { describeRatio, rulesFor } from "./canvas.js";
import { openStaging } from "./staging.js";
import { Reel, probeAspectSizes, timelineGeometry, fitText, compiledFor } from "./reel.js";

export function openTimeline(options) {
  return new Promise((resolve) => {
    const reel = new Timeline(options, resolve);
    options.opened?.(reel);
    reel.mount();
  });
}

/** The timeline's window: the reel's parts (`reel.js`) laid out around a
 *  player. Everything both windows share is on `Reel`; what is here is this
 *  window's own. */
export class Timeline extends Reel {
  constructor(options, resolve) {
    super(options, resolve);
    this.openBlockoutWindow = options.openBlockout ?? null;
  }

  mount() {
    this.buildParts();

    this.modal = el("div", { class: "mmc-modal mmc-tl-modal mmc-reel" }, [
      el("div", { class: "mmc-reel-head" }, [
        el("span", { class: "mmc-reel-title", text: t("Timeline") }),
        this.titleMeta,
        this.undoButton,
        this.redoButton,
        this.planEl,
        this.cancelButton,
        ...(this.openBlockoutWindow ? [el("button", {
          class: "mmc-reel-btn", title: t("The stage, on the same piece"),
          onclick: () => { const go = this.openBlockoutWindow; this.close(); go(); },
        }, [icon("cube", 16), el("span", { text: t("Open the blockout") })])] : []),
        ...(this.queue ? [this.shootButton] : []),
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-reel-main" }, [
        this.scriptColumn(),
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
        onclick: () => (!video.paused ? video.pause()
          // Nothing selected is the piece, which plays from its first film.
          : !sel && !made ? this.playFrom(0) : video.play().catch(() => {})) }, [icon("play", 20)]);
      // A shot runs on into the next one there is film of.
      if (sel?.kind === "shot") {
        video.addEventListener("ended", () => this.playFrom(S.passOf(this.timeline, sel.index).end));
      }
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

  /** Play the first shot from `index` on that there is film of. */
  playFrom(index) {
    const next = this.timeline.segments.findIndex((segment, k) => {
      if (k < index) return false;
      const take = S.isClip(segment) ? segment : S.takeOn(S.passOf(this.timeline, k).segments[0]);
      return take && !this.gone.has(take.filename);
    });
    if (next < 0) return;
    this.select({ kind: "shot", index: next });
    this.playerHost.querySelector("video")?.play().catch(() => {});
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
      onFilm: (promptId) => this.filmMade(promptId),
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

  /** The whole piece came out as one film: it is put together, unless it was
   *  changed while that film was being made. */
  filmMade(promptId) {
    const snapshot = this.queued.get(String(promptId));
    if (!snapshot || this.destroyed || S.cutStamp(this.timeline, snapshot.shot) !== snapshot.cut) return;
    this.timeline.cut = S.cutStamp(this.timeline);
    this.commit();
    this.reel?.landed();
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
   *  writing already is. `bench` is what the blockout bench was opened with,
   *  handed back to it on the way across. */
  open({ edit = null, bench = {} } = {}) {
    let held = null;
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
      openBlockout: () => this.openBlockout(bench),
      opened: (reel) => { held = reel; this.reel = reel; this.stage.onChange = () => reel.staged(); },
    }).then(() => { if (this.reel === held) { this.reel = null; this.stage.onChange = null; } });
  }

  /** The blockout bench, over the node: the same piece as the strip, staged
   *  in 3D. Lent what the strip is lent, and the way across to it. */
  openBlockout({ targets = [], back = null } = {}) {
    let held = null;
    return openStaging({
      targets, back,
      timeline: this.timeline,
      onCommit: () => this.commit(),
      io: () => this.widgetIO(),
      widgets: this.widgets,
      ...(this.nodeId != null ? { queue: () => queueNode(this.nodeId()) } : {}),
      stage: this.stage,
      run: () => this.currentRun(),
      openTimeline: () => this.open({ bench: { targets, back } }),
      opened: (bench) => { held = bench; this.reel = bench; this.stage.onChange = () => bench.staged(); },
    }).then(() => { if (this.reel === held) { this.reel = null; this.stage.onChange = null; } });
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
             t("Browse and organize finished renders and pre-stage stills"),
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
