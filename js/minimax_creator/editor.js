// The generation body: tool rail, attached assets, prompt, pill row, mode badge.
//
// Used twice — as the MiniMax Creator node's body, and as a timeline segment's
// editor — because a segment is a whole generation and deserves the same
// controls. It owns a state object and calls back when it changes; who persists
// that state, and where, is the caller's business.
//
// Every mutation funnels through commit(), which notifies the owner and
// re-renders. The skeleton is built once and render() only refills the four
// volatile hosts — the prompt box must survive untouched, because rebuilding a
// contenteditable destroys the caret, and attaching an asset from the @ menu
// commits *while the user is typing in it*.

import { el, icon, ICONS, keepScroll, svg, swappable } from "./dom.js";
import { t } from "./i18n.js";
import { openPicker } from "./picker.js";
import { openLoras } from "./loras.js";
import { openSettings } from "./settings.js";
import { openPresetLibrary } from "./presetlib.js";
import { openTrim, trimLabel } from "./trim.js";
import { PromptBox, focusEnd, openEditorSheet } from "./prompt.js";
import { RefinePanel, refineButton, refine } from "./refine.js";
import { openAspectPopover, openResolutionPopover, openChoicePopover, facesPill, aspectGlyph,
         PILL_GLYPH } from "./pills.js";
import { samplingBar, segmentSeedPill, widgetIO } from "./sampling.js";
import { Stage } from "./stage.js";
import { weightsPill, loadCatalog, catalogFiles } from "./models.js";
import * as Turbo from "./turbo.js";
import { viewUrl, probeAudio } from "./api.js";
import * as S from "./state.js";
import { MIN_SECONDS, MAX_SECONDS, describeRatio, isTrainedLength } from "./canvas.js";

const HANDLE_RE = /@([A-Za-z]+-\d+)/g;

// What a reference video's chip says it is doing, and what the chip switches to
// when you click it. "sound only" goes back to bringing the picture along,
// because the way out of it is the way you got in.
const TRACK_CHIP = {
  "picture+sound": { text: "sound on", next: "picture" },
  "picture": { text: "sound off", next: "picture+sound" },
  "sound": { text: "sound only", next: "picture+sound" },
};

// What the narrowing chip explains, per kind. Both lists say the same thing
// about the four takes they share; a clip's other four are the whole-video
// roles, which is a different sentence and a longer one.
export const IMAGE_TAKES_HELP =
  "What of this picture is the reference. full: the whole image. "
  + "person / object / scene / style: only that — a person reference keeps the "
  + "likeness and drops the picture's background, palette, pose and action. "
  + "Read by Refine, and worth saying in the prompt too if you skip refining.";
export const VIDEO_TAKES_HELP =
  "What of this clip is the reference. full: the whole thing. "
  + "person / object / scene / style: only that much of what it shows. "
  + "motion: the action alone, carried onto whoever the prompt puts in the "
  + "shot. camera: the camera move, cuts and pacing, with nothing in it "
  + "appearing. edit: the clip is the video being edited. continue: the video "
  + "picks up where it ends. Read by Refine, and worth saying in the prompt "
  + "too if you skip refining.";

/** The narrowing menu, shared by the chip on a card and the one in the
 *  timeline's pool. Labels are translated, so the pick maps back by key. */
export function pickTakes(anchor, asset, commit) {
  const options = S.takeOptions(asset);
  openChoicePopover(anchor, {
    title: t("@{handle} is a reference to", { handle: asset.handle }),
    options: options.map((key) => t(key)),
    value: t(S.takes(asset)),
    onPick: (choice) => {
      const key = options.find((k) => t(k) === choice) ?? "full";
      if (key === "full") delete asset.takes;
      else asset.takes = key;
      commit();
    },
  });
}

export class CreatorEditor {
  /**
   * @param {object} options
   * @param {object} options.state        mutated in place; the caller owns persistence
   * @param {() => void} options.onCommit  after every change, before the re-render
   * @param {boolean} [options.canvasPills]  false in a timeline segment, where the
   *   aspect and resolution belong to the timeline and not to one shot
   * @param {boolean} [options.continuePill]  true for a timeline segment after the
   *   first, which may start from the previous segment's last frame
   * @param {() => object} [options.refineTarget]  the payload the refine route
   *   wants — `{kind, data, index}`. Supplied by the owner because only it knows
   *   whether this state is a whole `creator_data` or one card of a timeline;
   *   without it the Refine button is not drawn at all.
   * @param {(result: object) => void} [options.onRefined]  the parts of a reply
   *   that are not this state's: in a timeline the soundscape and the score
   *   belong to the timeline, so the owner takes them.
   * @param {() => void} [options.onReverted]  the rewrite was thrown away — the
   *   other half of `onRefined`, so an owner holding parts of a reply can drop
   *   them too rather than keep prose nothing refers to any more.
   */
  /**
   * @param {() => string|number} [options.nodeId]  the ComfyUI node this body is
   *   mounted on. Supplied only for a node body, never for a timeline segment
   *   editor: it is what the stage listens for its own previews with, and what
   *   says this editor owns the weights rather than inheriting them.
   */
  /**
   * @param {{shown: () => boolean, toggle: () => void}} [options.pieceView]
   *   the piece-view toggle, supplied only for the face of a piece of one shot.
   *   A piece holds things a shot does not — the standing prompt, the reference
   *   pool, the LoRAs on every shot — and while there is one shot none of them
   *   has anywhere to be shown, so without this they cannot be set at all: you
   *   would need a second shot to reach the controls that make the first one
   *   part of a piece.
   */
  /**
   * @param {{active: () => boolean, toggle: () => void}} [options.preStage]
   *   the pre-stage pill's wiring, supplied only for a node body: whether a
   *   PreStage currently claims this node, and spawning/removing one. The state
   *   is derived by scan on every render, never stored — see minimax_creator.js.
   */
  /**
   * @param {boolean} [options.durationPill]  false where the generation's length
   *   is not the user's seconds — the pre-stage's H3 branch samples the shortest
   *   clip it can and keeps one frame, so it puts its own length pill in
   *   `extraPills` instead.
   * @param {() => Element[]} [options.extraPills]  pills for the row, in the
   *   duration pill's place. What a caller that is *not* rendering a video
   *   needs to say about the generation.
   * @param {() => Element[]} [options.extraTools]  extra rail tools, after the
   *   gallery. What a body needs that a Creator does not — the pre-stage's
   *   frame grabber is the only one.
   * @param {() => Element[]} [options.clearTool]  the piece's Clear, last in the
   *   rail's own cluster. Supplied by the owner rather than built here for the
   *   same reason `presetTarget` is: this editor is one shot, and what Clear
   *   empties is the piece the shot belongs to — see `clear.js`.
   * @param {boolean} [options.settingsTool]  false where the settings page has
   *   nothing to say about what this body makes. It holds the video rate
   *   control, and a pre-stage writes PNGs.
   * @param {() => object} [options.presetTarget]  what the preset library saves
   *   from and applies to here, when this body is somewhere presets make sense.
   *   Absent on a body whose owner already offers the tool for the thing this
   *   editor is one card of — the piece's own face passes its piece's target,
   *   and the strip's card editor passes that card's.
   * @param {string} [options.editorTitle]  what to call the window the face's
   *   prompt opens — "Shot" for a clip, "Still" for a pre-stage. Node bodies
   *   only: in a modal the body is already the window.
   * @param {Stage} [options.stage]  a stage to use instead of building one.
   *   Supplied by an owner that outlives this editor — the pre-stage rebuilds
   *   its body when the architecture changes, and the satellite floating the
   *   stage beside the node was bound once, to the owner's.
   */
  /**
   * @param {object} [options.piece]  where the settings that belong to the whole
   *   node live: the canvas, the weights and the turbo switch. Defaults to the
   *   state, which is right whenever this editor's state *is* the node's — the
   *   pre-stage's, and the shot editor inside a window, which owns none of them
   *   anyway. The one shot of a piece passes the piece: its canvas and weights
   *   are held one level up, because they are what every shot on the strip is
   *   held to, and there is nothing else different about being the only one.
   *
   *   Read as well as written through this. `syncTimeline` mirrors the canvas
   *   back down onto every segment, so `resolved(state)` goes on answering — it
   *   is only the writes that have to land where the value actually lives, or
   *   the next mirror would wipe them.
   */
  constructor({ state, onCommit, canvasPills = true, continuePill = false,
                refineTarget = null, onRefined = null, onReverted = null,
                samplingWidgets = null, onWidgetChange = null, nodeId = null,
                routeOf = null, setRoute = null, preStage = null, pieceView = null,
                durationPill = true, extraPills = null, extraTools = null,
                settingsTool = true, stage = null, editorTitle = null,
                piece = null, afterPanel = null, presetTarget = null,
                clearTool = null, seedTarget = null }) {
    // The one sampler setting a card may answer for itself — see
    // `segmentSeedPill`. Null on a node body, which owns the whole row.
    this.seedTarget = seedTarget;
    this.presetTarget = presetTarget;
    this.piece = piece ?? state;
    this.afterPanel = afterPanel;
    // What the window this body opens into is called. A node face is a preview
    // of one generation, and the window is that generation — so the owner names
    // it for what it makes rather than for the control that opened it.
    this.editorTitle = editorTitle ?? t("Shot");
    this.preStage = preStage;
    this.pieceView = pieceView;
    this.durationPill = durationPill;
    this.settingsTool = settingsTool;
    this.extraPills = extraPills;
    this.extraTools = extraTools;
    this.clearTool = clearTool;
    this.state = state;
    // Where the standing checkpoint route is read from and written to. A node
    // body owns its own; a timeline segment editor reads the timeline's and
    // cannot set it, because a route that differed between two shots of one clip
    // would not be a route.
    this.routeOf = routeOf ?? (() => this.piece.models?.route ?? "auto");
    this.setRoute = setRoute;
    this.onCommit = onCommit;
    this.canvasPills = canvasPills;
    this.continuePill = continuePill;
    this.refineTarget = refineTarget;
    this.onRefined = onRefined;
    this.onReverted = onReverted;
    // Only the node body has these. The same editor opens as a timeline
    // segment, where the sampler belongs to the timeline and not to one shot.
    this.samplingWidgets = samplingWidgets;
    this.onWidgetChange = onWidgetChange;
    this.nodeId = nodeId;
    this.sizes = new Map();   // filename -> {width,height}, for the adaptive canvas readout

    this.prompt = new PromptBox({
      getState: () => this.state,
      onInput: (text) => {
        this.state.prompt = text;
        this.onCommit?.();
        this.renderNotices();   // dangling-handle warning, without disturbing the caret
      },
      onAttach: (row) => this.attachFromMention(row),
      attachBlocked: (action) => S.blockedReason(this.state, action),
      // The piece's reference pool, where this state is a timeline segment —
      // `syncTimeline` mirrors it on as `pool`, the way the canvas rides on.
      // Citable by chip, never attached: the citation is the attachment.
      getPool: () => this.state.pool ?? [],
      onOverflow: (over) => this.onPromptOverflow(over),
    });
    // Leaving the box arms the escalation again — see `onPromptOverflow`.
    this.prompt.root.addEventListener("blur", () => { this.overflowWaived = false; });

    // Built once and refreshed in place: it holds textareas that are typed into,
    // and a full render would rebuild the one under the caret. `onRefined`
    // decides whether the two audio fields live here — in a timeline they are
    // the timeline's and are edited in its own modal.
    this.refinePanel = new RefinePanel({
      getState: () => this.state,
      // Also the dimming: the panel's toggle and its Revert both change whether
      // the prompt above is queued, and neither goes through a full render.
      onCommit: () => { this.onCommit?.(); this.syncPrompt(); },
      audioFields: !this.onRefined,
      onRevert: () => this.onReverted?.(),
    });

    this.railHost = el("div");
    this.assetsHost = el("div");
    this.loraHost = el("div");
    this.pillsHost = el("div");
    this.noticeHost = el("div");
    // Between what is being asked for and how it is run — which is where the
    // next shot goes, because a second shot is part of the first question and
    // not of the second. Empty unless an owner has something to put there; the
    // one that does is a piece of one shot, which puts the unexposed stretch of
    // film that grows it into a strip. See `TimelineBody.renderGrow`.
    this.growHost = el("div");
    // Last, the way the Timeline puts it last: the panel says what the piece is
    // and this says how it is run.
    this.samplingHost = el("div");

    // The stage, for a node only. A timeline segment editor is a modal over
    // a node that has its own — two stages listening for the same previews would
    // be two answers to one question. Not mounted here: attach() hands it to a
    // Satellite, which floats it beside the node, so the body's layout never
    // changes when a render lands.
    this.stage = stage ?? (this.nodeId ? new Stage({
      nodeId: this.nodeId,
      onGallery: () => this.openGallery(),
    }) : null);
    // An injected stage belongs to whoever injected it, and outlives this
    // editor — so `destroy` leaves it alone.
    this.ownsStage = !stage;

    // The box is on the face, and typed into there, exactly as it always was.
    // What is new is only what happens when it runs out of room: a node is a
    // fixed rectangle on a graph, so past a certain length the box is a
    // four-line slot you are writing a paragraph into — and at that point the
    // window takes over. See `onPromptOverflow`.
    //
    // `onFace` is what tells the two apart: the same editor is also *inside*
    // that window, and there it is the window, so nothing about it escalates.
    this.onFace = !!this.nodeId;
    this.expandHost = el("div", { class: "mmc-panel-corner" });
    this.root = el("div", { class: "mmc-root" }, [
      this.railHost,
      this.assetsHost,
      this.loraHost,
      // `frame`, not `root`: the box brings its own disclosure, which folds it
      // away once a rewrite is what gets queued.
      this.panel = el("div", { class: "mmc-panel" }, [
        ...(this.onFace ? [this.expandHost] : []),
        this.prompt.frame, this.refinePanel.root, this.pillsHost,
      ]),
      this.noticeHost,
      this.growHost,
      this.samplingHost,
    ]);

    // The whole panel is the writing area, not just the box inside it — see
    // `PromptBox.claim`.
    this.prompt.claim(this.panel);

    // The weights pill needs the file lists to say anything useful, and every
    // node body on the canvas shares the one request.
    //
    // Only when this editor owns the piece. Handed one — the face of a piece of
    // one shot — the owner is already watching the catalog for the same weights
    // block, and two watchers guess at it twice and redraw twice for the one
    // answer.
    if (this.nodeId && this.piece === this.state) loadCatalog(() => this.adoptWeights());

    this.prompt.setValue(this.state.prompt ?? "");
    this.render();
    this.probeKeyframe();
  }

  /** Called when the node body goes away. */
  destroy() {
    if (this.ownsStage) this.stage?.destroy();
  }

  /**
   * Fill weights nobody has picked from unambiguous filename matches.
   *
   * The one case this is really for: a workflow saved when these were sockets
   * loads with the links dropped and nothing chosen, and the files are already
   * on disk under recognisable names. Committed like any other change, so it
   * saves with the workflow and can be overridden by picking something else.
   */
  adoptWeights() {
    if (S.guessModels(this.piece.models, catalogFiles())) this.commit();
    else this.render();
  }


  /** See `sampling.widgetIO`. */
  widgetIO() {
    return widgetIO(() => this.samplingWidgets, () => this.onWidgetChange?.());
  }

  commit() {
    // Before notifying, because attaching a reference can invalidate a
    // checkpoint pin that was legal when it was made.
    S.normalizeCheckpoint(this.state);
    // Same timing, same reason: removing or disabling the turbo LoRA anywhere —
    // the chip's ✕, the manager — is switching turbo off, and the sampler row
    // has to come back before this state is serialized with `on` still in it.
    if (this.samplingWidgets && this.piece.turbo) Turbo.sync(this.piece, this.widgetIO());
    this.onCommit?.();
    this.render();
  }

  /** Point the editor at a different state object.
   *
   *  The Creator node needs this because loading a saved workflow assigns widget
   *  values after the node is created, so the editor built in `nodeCreated` saw
   *  an empty blob and has to catch up once the graph has finished configuring.
   */
  setState(state) {
    this.state = state;
    this.sizes.clear();
    this.prompt.setValue(this.state.prompt ?? "");
    this.refinePanel.problems = [];
    this.render();
    this.probeKeyframe();
  }

  /**
   * Ask the refiner to rewrite this state's prompt.
   *
   * The reply is a whole-request answer even when only one shot was asked for —
   * the soundscape and the score describe the piece — so the shot body lands
   * here and the rest goes wherever the owner keeps it.
   */
  async refine() {
    try {
      const result = await refine(this.refineTarget());
      const shot = result.shots?.[0];
      if (!shot?.body) throw new Error(t("the refiner returned nothing for this prompt"));
      this.refinePanel.apply(result, shot);
      this.onRefined?.(result);
      this.commit();
    } catch (error) {
      this.refinePanel.fail(String(error.message || error));
    }
  }

  /**
   * Attach a file the user picked from the @ menu, and return its new handle.
   * Selecting from the input folder is what creates the reference — there is no
   * separate "add it first, then mention it" step.
   */
  attachFromMention(row) {
    const blocked = S.blockedReason(this.state, "reference");
    if (blocked) { this.flash(blocked); return null; }
    const { used, max, filesLeft } = S.capacity(this.state, row.kind);
    if (used >= max || filesLeft <= 0) {
      this.flash(t("No {kind} slots left ({used}/{max} used, {filesLeft} files free of {maxFiles}).",
        { kind: t(row.kind), used, max, filesLeft, maxFiles: S.MAX_REF_FILES }));
      return null;
    }
    const handle = S.nextHandle(this.state, row.kind);
    const entry = {
      handle, kind: row.kind, role: "reference", filename: row.path,
      // Max by default, for a picture and for a clip alike: fidelity is why a
      // reference is attached, and "match" trading it for speed is a downgrade
      // to opt into, not out of. Ignored for audio, which has no size.
      ref_size: "max",
    };
    if (row.kind === "video") entry.track = S.DEFAULT_TRACK;
    this.state.assets.push(entry);
    this.commit();
    // The caller needs the handle now, to put a chip under a live caret; the
    // sound default settles a round trip later and commits again.
    if (row.kind === "video") this.applySoundDefault(entry);
    return handle;
  }

  // ---- asset actions -------------------------------------------------------

  async addReferences(kind) {
    const blocked = S.blockedReason(this.state, "reference");
    if (blocked) return this.flash(blocked);
    const { used, max, filesLeft } = S.capacity(this.state, kind);
    if (used >= max || filesLeft <= 0) {
      return this.flash(t("No {kind} slots left ({used}/{max} used, {filesLeft} files free of {maxFiles}).",
        { kind: t(kind), used, max, filesLeft, maxFiles: S.MAX_REF_FILES }));
    }
    const chosen = await openPicker({
      kinds: ["image", "video", "audio", "renders"],
      kind,
      capacity: (k) => S.capacity(this.state, k),
    });
    if (!chosen) return;
    await this.attachAssets(chosen);
  }

  /**
   * The gallery: the same picker, opened on the renders tab. No capacity
   * precheck, unlike addReferences — looking at finished renders is legal with
   * every slot full; only an actual pick has to answer for room, and the
   * picker's own counters already hold it to that.
   */
  async openGallery() {
    const chosen = await openPicker({
      kinds: ["renders", "image", "video", "audio"],
      kind: "renders",
      capacity: (k) => S.capacity(this.state, k),
    });
    if (!chosen) return;
    const blocked = S.blockedReason(this.state, "reference");
    if (blocked) return this.flash(blocked);
    await this.attachAssets(chosen);
  }

  /** Turn picked assets into reference entries. The shared tail of both the
   *  slot buttons and the gallery. */
  async attachAssets(chosen) {
    const undecided = [];
    for (const asset of chosen) {
      const entry = {
        handle: S.nextHandle(this.state, asset.kind),
        kind: asset.kind,
        role: "reference",
        filename: asset.path,
        ref_size: "max",
      };
      if (asset.kind === "video") entry.track = S.DEFAULT_TRACK;
      if (asset.trim) entry.trim = asset.trim;
      this.state.assets.push(entry);
      if (asset.kind !== "video") continue;
      // A track means the user opened the segment editor and said so. Anything
      // else is the default, which needs a round trip to settle. Both are applied
      // after the push, so the file the video occupies counts against the total.
      if (asset.track) this.setTrack(entry, asset.track, { defer: true });
      else undecided.push(entry);
    }
    this.commit();
    for (const entry of undecided) await this.applySoundDefault(entry);
  }

  /**
   * A reference video is attached with its sound on — that is what you almost
   * always want from a clip you chose for its motion *and* its audio. Sequenced
   * one at a time, so the three audio slots are handed out in pick order rather
   * than raced for.
   */
  async applySoundDefault(asset) {
    const has = await probeAudio(asset.filename);
    // A silent clip stays silent: switching sound on for a file with no audio
    // track would fail at queue time over a choice the user never made.
    if (has === false) return;
    if (!this.state.assets.includes(asset)) return;   // removed while we were asking
    if (this.setTrack(asset, "picture+sound", { defer: true })) this.commit();
  }

  /**
   * Choose which of a reference video's streams are referenced. Applied first
   * and rolled back if the result would not compile: a track change can move the
   * clip between the video and audio buckets, so whether it fits is a question
   * about the whole reference set rather than about one counter.
   */
  setTrack(asset, track, { defer = false } = {}) {
    const previous = asset.track;
    if (previous === track) return true;
    asset.track = track;
    const problem = S.overflow(this.state);
    if (problem) {
      asset.track = previous;
      this.flash(t("@{handle} stays {track} — {problem}", {
        handle: asset.handle,
        track: t(TRACK_CHIP[previous]?.text || previous),
        problem,
      }));
      return false;
    }
    if (!defer) this.commit();
    return true;
  }

  /**
   * Point an attached reference at a different file, keeping its handle.
   *
   * Trying the same reference with another picture is one substitution, not a
   * removal and a re-add: the handle survives, so every @mention in the prompt
   * still means this row and the prompt does not have to be rewritten around
   * the renumbering. Same kind only, for the same reason — @img-1 has to go on
   * being an image.
   */
  async replaceAsset(asset) {
    const chosen = await openPicker({
      kinds: [asset.kind, "renders"],
      kind: asset.kind,
      only: asset.kind,
      single: true,
      // The slot it occupies is the slot it will occupy: a swap adds nothing to
      // count, so the reference caps have nothing to say about it.
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    const picked = chosen?.[0];
    if (!picked || picked.path === asset.filename) return;
    asset.filename = picked.path;
    // A trim is a range in the old file's timeline and means nothing in
    // another's — either the picker's segment editor set one for this pick, or
    // the new file starts whole.
    if (picked.trim) asset.trim = picked.trim;
    else delete asset.trim;
    // Same for sound: whether this clip has any is a fact about this clip, and
    // the old one's answer must not carry over onto a silent replacement.
    if (asset.kind === "video") asset.track = picked.track ?? S.DEFAULT_TRACK;
    this.commit();
    if (asset.role !== "reference") this.probeKeyframe();
    else if (asset.kind === "video" && !picked.track) await this.applySoundDefault(asset);
  }

  /** The segment editor, on an already-attached clip. */
  async editSegment(asset) {
    const result = await openTrim({
      path: asset.filename,
      kind: asset.kind,
      trim: asset.trim ?? null,
      track: asset.track,
      showTrack: asset.kind === "video",
    });
    if (!result) return;
    if (result.trim) asset.trim = result.trim;
    else delete asset.trim;
    if (result.track) this.setTrack(asset, result.track, { defer: true });
    this.commit();
  }

  async setFrame(role) {
    const blocked = S.blockedReason(this.state, role);
    if (blocked) return this.flash(blocked);
    const existing = S.frameAsset(this.state, role);
    const chosen = await openPicker({ kinds: ["image"], kind: "image", single: true, capacity: () => ({ used: 0, max: 1, filesLeft: 1 }) });
    if (!chosen) return;
    const asset = chosen[0];
    if (existing) this.remove(existing.handle, { silent: true });
    this.state.assets.push({
      handle: S.nextHandle(this.state, "image"),
      kind: "image",
      role,
      filename: asset.path,
    });
    this.commit();
    this.probeKeyframe();
  }

  remove(handle, { silent = false } = {}) {
    this.state.assets = this.state.assets.filter((a) => a.handle !== handle);
    if (!silent) this.commit();
  }

  /** Image dimensions for the adaptive-canvas readout. The backend re-reads
   *  them from disk; this is only so the pills can tell the truth early. */
  probeKeyframe() {
    const anchor = S.frameAsset(this.state, "first_frame") || S.frameAsset(this.state, "last_frame");
    if (!anchor || this.sizes.has(anchor.filename)) return;
    const probe = new Image();
    probe.onload = () => {
      this.sizes.set(anchor.filename, { width: probe.naturalWidth, height: probe.naturalHeight });
      this.render();
    };
    probe.src = viewUrl(anchor.filename);
  }

  flash(message) {
    this.notice = message;
    this.render();
    clearTimeout(this.noticeTimer);
    this.noticeTimer = setTimeout(() => { this.notice = null; this.render(); }, 6000);
  }

  // ---- render --------------------------------------------------------------

  render() {
    const state = this.state;
    const anchor = S.frameAsset(state, "first_frame") || S.frameAsset(state, "last_frame");
    const geometry = S.resolved(state, anchor ? this.sizes.get(anchor.filename) : null);

    this.railHost.replaceChildren(this.renderRail());
    this.assetsHost.replaceChildren(...(state.assets.length ? [this.renderAssets()] : []));
    this.loraHost.replaceChildren(...(state.loras.length ? [this.renderLoras()] : []));
    this.pillsHost.replaceChildren(this.renderPills(geometry, S.mode(state)));
    // A card's own seed, where the sampler row belongs to the node above it.
    // It takes the row's place on the body, holding the one pill of that row
    // this card is entitled to set.
    if (!this.samplingWidgets && this.seedTarget) {
      const target = this.seedTarget();
      this.samplingHost.replaceChildren(el("div", { class: "mmc-pills" }, [
        segmentSeedPill({
          own: target.own,
          piece: target.piece,
          taken: target.taken,
          onChange: (seed) => {
            if (seed === null) delete this.state.seed; else this.state.seed = seed;
            this.onCommit?.();
            this.render();
          },
        }),
      ]));
    }
    else this.samplingHost.replaceChildren(...(this.samplingWidgets ? [samplingBar({
      widgets: this.samplingWidgets,
      value: (name, fallback) => {
        const widget = this.samplingWidgets[name];
        return widget ? widget.value : fallback;
      },
      // Write through to the real widget, callback included — some of them (the
      // seed's after-generate control) hang behaviour off it.
      set: (name, value) => {
        const widget = this.samplingWidgets[name];
        if (!widget) return;
        widget.value = value;
        widget.callback?.(value);
        this.onWidgetChange?.();
        this.render();
      },
      // One generation, always: a Creator render has no segments to spread a
      // seed across.
      perSegment: false,
      // The turbo switch, for a node body only: a timeline segment has no
      // sampler of its own to throw it on.
      turbo: this.nodeId ? Turbo.turboPills({
        container: this.piece,
        ...this.widgetIO(),
        onCommit: () => this.commit(),
      }) : [],
      // Last on the row, because it is the one thing there you set when you
      // install a checkpoint rather than when you write a prompt. The face pass
      // goes in front of it: it is a thing done to the render, like the
      // accelerators it sits beside, rather than a file you picked once.
      trailing: this.nodeId ? [
        facesPill({ target: this.piece, commit: () => this.commit() }),
        weightsPill({
          models: this.piece.models,
          checkpoints: [S.checkpoint(this.state)],
          face: Boolean(this.piece.face?.on),
          onChange: () => this.commit(),
          turbo: { container: this.piece, widgetIO: this.widgetIO() },
        }),
      ] : [],
    })] : []));
    this.prompt.refresh();
    this.syncPrompt();
    this.refinePanel.render();
    this.renderExpand();
    this.renderNotices();
    this.growHost.replaceChildren(...(this.afterPanel?.() ?? []));
    // The window over the same state, if one is open. Render, never commit —
    // this is the end of the chain, not another link in it.
    this.sheetEditor?.render();
  }

  /**
   * The way out of a box that has run out of room.
   *
   * Always there, so the window is never something you have to discover by
   * overflowing into it, and lit once the text no longer fits — at which point
   * it is not a shortcut any more, it is where the writing is.
   */
  renderExpand() {
    if (!this.onFace) return;
    this.expandHost.replaceChildren(el("button", {
      class: `mmc-expand${this.overflowing ? " on" : ""}`,
      title: this.overflowing
        ? t("This prompt is longer than the node can show. Open it in a window.")
        : t("Open this shot in a window — the prompt, its references, LoRAs and canvas."),
      onclick: () => this.openEditor({ caret: "end" }),
    }, [icon("expand", 14)]));
  }

  /**
   * The text stopped fitting the box, or started fitting it again.
   *
   * A node face is a fixed rectangle, so there is a length past which the box
   * on it is a slot you are writing a paragraph through. When that happens
   * *while you are typing*, the window opens and takes the caret with it — the
   * sentence carries on where it left off, in a box the size of the job.
   *
   * It happens once. Close the window and the face will not grab the caret
   * again for the sentence you go back to writing, so a prompt you deliberately
   * left long is a prompt you can keep editing on the face, scrolled, exactly as
   * any other overlong box in this pack behaves. The corner control is the way
   * back in, and it stays lit.
   *
   * The waiver is about that visit to the box and not about the text: it lifts
   * when the box has fitted again *or* when you leave it (see the blur above).
   * Latched on the text it never lifted at all — a prompt long enough to need
   * the window is a prompt that stays long, so after one close the face was the
   * only place it could ever be written again, and the feature read as broken.
   */
  onPromptOverflow(over) {
    if (!this.onFace || over === this.overflowing) return;
    this.overflowing = over;
    this.renderExpand();
    if (!over) {
      this.overflowWaived = false;
      return;
    }
    if (this.sheet || this.overflowWaived) return;
    // Only mid-sentence: a state loaded from a workflow overflows the moment it
    // is drawn, and opening a window over a graph nobody has touched yet would
    // be the node shouting at the room.
    if (document.activeElement !== this.prompt.root) return;
    this.openEditor({ caret: "end" });
  }

  /**
   * The whole shot, in a window: the same editor, in a room the size of the job.
   *
   * Not a prompt box on its own. Writing a shot is choosing its references and
   * its length and its canvas as much as it is typing a sentence, and those
   * controls were never the problem — the *node face* was, because it is a
   * rectangle on a graph and everything in it has to stay one height. So the
   * face keeps the rail, the chips and the pills as a preview of the shot, and
   * this opens the same body full size with the live box in it.
   *
   * A second editor over the same state object rather than the face's own
   * moved into the overlay: the face's root is a ComfyUI DOM widget, and the
   * frontend goes on positioning it against the node whatever it is parented
   * to. Both editors mutate one state and commit through this one, so there is
   * nothing to keep in step — it is the same arrangement a timeline segment's
   * editor has always used.
   */
  openEditor({ caret = null } = {}) {
    if (this.sheet) return;
    const editor = new CreatorEditor({
      state: this.state,
      onCommit: () => { this.onCommit?.(); this.render(); },
      canvasPills: this.canvasPills,
      piece: this.piece,
      durationPill: this.durationPill,
      extraPills: this.extraPills,
      extraTools: this.extraTools,
      settingsTool: this.settingsTool,
      refineTarget: this.refineTarget,
      onRefined: this.onRefined,
      onReverted: this.onReverted,
      routeOf: this.routeOf,
      setRoute: this.setRoute,
      // No nodeId: the sampler row, the weights pill and the stage belong to
      // the node and stay on its face. What is in here is the generation.
    });
    // Held so the face can redraw it. Every control in the window whose write
    // goes through a callback the *owner* supplied — the route badge is the one
    // that showed it — lands on the node's own editor and re-renders that one;
    // without this the window goes on drawing what it drew before the click and
    // reads as a dead control.
    this.sheetEditor = editor;
    this.sheet = openEditorSheet({
      title: this.editorTitle,
      subtitle: t("Prompt, references, LoRAs and canvas. The sampler stays on the node."),
      content: [editor.root],
      onClose: () => {
        this.sheet = null;
        this.sheetEditor = null;
        editor.destroy();
        // The face is about to show a box the text still does not fit. It is
        // not to grab the caret again for it — see `onPromptOverflow`.
        this.overflowWaived = this.overflowing;
        this.render();
      },
    });
    if (caret === "end") focusEnd(editor.prompt.root);
    else editor.prompt.root.focus();
  }

  /**
   * Show whether the typed prompt is the thing being queued.
   *
   * A rewrite replaces it at compile time rather than joining it, so while one
   * is on the box is holding a draft. Said by dimming it, beside the panel's own
   * line, because the panel is below the fold on a small node and the box is
   * what the eye lands on. Called on the panel's commits too — the toggle
   * changes this and nothing else in the editor.
   */
  syncPrompt() {
    const refined = this.state.refined;
    this.prompt.setSuperseded(!!refined?.body?.trim() && refined.enabled !== false);
  }

  renderNotices() {
    this.noticeHost.replaceChildren(
      ...(this.notice ? [el("div", { class: "mmc-warn", text: this.notice })] : []),
      ...(this.renderDangling() || []),
    );
  }

  renderRail() {
    const disabled = !!S.blockedReason(this.state, "reference");
    const tool = (kind, label, iconName) =>
      el("button", {
        class: "mmc-tool",
        disabled: disabled || undefined,
        title: disabled ? S.blockedReason(this.state, "reference") : t("Attach a reference {kind}", { kind: t(kind) }),
        onclick: () => this.addReferences(kind),
      }, [el("span", { class: "mmc-tool-icon" }, [icon(iconName)]), el("span", { text: t(label) })]);

    // Two clusters, split by the whole width of the node: everything on the
    // left acts on this generation, and the pair on the right belongs to the
    // machine — the Gallery is what this ComfyUI has already made, Settings is
    // how it writes the next one, and neither moves whatever the prompt says.
    // Seven equal siblings said none of that.
    return el("div", { class: "mmc-rail" }, [
      el("div", { class: "mmc-rail-group" }, [
        tool("image", "Add image", "image"),
        tool("video", "Add video", "video"),
        tool("audio", "Add audio", "audio"),
        // Not gated like the reference tools: LoRAs sit on the checkpoint, not in the
        // reference slots, so they are the one thing frames and references share.
        el("button", {
          class: "mmc-tool",
          title: t("Manage the LoRAs patched onto the routed checkpoint"),
          onclick: () => this.manageLoras(),
        }, [el("span", { class: "mmc-tool-icon" }, [icon("effect")]), el("span", { text: t("Add LoRA") })]),
        // With the adds because they are one: the PreStage's frame grab puts an
        // init image on this generation, whatever tool the host lends the rail.
        ...(this.extraTools?.() ?? []),
        // After the adds because it is the step after them: the rewrite is
        // written against the references and the duration, so it wants them
        // settled first.
        ...(this.refineTarget ? [refineButton({ run: () => this.refine() })] : []),
        // Then the end of the cluster, and the end of the piece: everything to
        // its left writes the scene, and this is the one that takes it back.
        ...(this.clearTool?.() ?? []),
      ]),
      el("div", { class: "mmc-rail-group" }, [
        // With the machine's cluster rather than the piece's: a preset outlives
        // this generation the way the gallery and the settings do, and applying
        // one is reaching for something already made rather than making it.
        ...(this.presetTarget ? [el("button", {
          class: "mmc-tool",
          title: t("Save this setup so you can put it back, or apply one you saved before"),
          onclick: () => openPresetLibrary({ target: this.presetTarget() }).then(() => this.render()),
        }, [el("span", { class: "mmc-tool-icon" }, [icon("star")]), el("span", { text: t("Presets") })])] : []),
        // Ungated, and here rather than only on the stage: the stage grows a
        // Gallery chip when a render finishes, which is exactly the moment you
        // do not need one — before the first render of a session there was no
        // way into the output folder at all, and organizing what is already
        // there is not something you should have to queue a render to reach.
        el("button", {
          class: "mmc-tool",
          title: t("Browse, organize and attach finished renders and pre-stage stills"),
          onclick: () => this.openGallery(),
        }, [el("span", { class: "mmc-tool-icon" }, [icon("gallery")]), el("span", { text: t("Gallery") })]),
        // Absent where it would be a control over nothing — see `settingsTool`.
        ...(this.settingsTool ? [el("button", {
          class: "mmc-tool",
          title: t("Preferences for this ComfyUI — output quality. Not saved into the workflow."),
          // Re-rendered on close: the page can change what the sampler row
          // draws (the shift pills' visibility), and Done should look done.
          onclick: () => openSettings().then(() => this.render()),
        }, [el("span", { class: "mmc-tool-icon" }, [icon("gear")]), el("span", { text: t("Settings") })])] : []),
      ]),
    ]);
  }

  async manageLoras() {
    await openLoras({ state: this.state, onChange: () => this.commit() });
    this.commit();
  }

  renderLoras() {
    const target = S.checkpoint(this.state);
    const chip = (entry) => {
      const modes = S.loraModes(entry);
      const idle = !modes.includes(target);
      return el("div", {
        class: `mmc-asset${idle ? " idle" : ""}`,
        title: idle
          ? t("{name} — set to {modes}, but this graph routes to {target}.", {
              name: entry.name,
              modes: modes.map((m) => S.CHECKPOINT_LABEL[m]).join(" + "),
              target: S.CHECKPOINT_LABEL[target],
            })
          : entry.name,
      }, [
        el("span", { class: "mmc-asset-thumb" }, [svg(ICONS.effect, 15)]),
        el("span", { class: "mmc-asset-handle", text: entry.name.split("/").pop().replace(/\.[^.]+$/, "") }),
        el("button", {
          class: "mmc-ghost",
          style: { fontSize: "11px" },
          title: t("Strength, and which checkpoint this LoRA belongs to"),
          text: `${Number(entry.strength ?? 1).toFixed(2)} · ${S.claimsBoth(entry) ? t("both") : S.CHECKPOINT_LABEL[modes[0]]}`,
          onclick: () => this.manageLoras(),
        }),
        el("button", {
          class: "mmc-asset-x", text: "✕", title: t("Remove {name}", { name: entry.name }),
          onclick: () => { S.removeLora(this.state, entry.name); this.commit(); },
        }),
      ]);
    };

    const parts = [el("div", { class: "mmc-assets" }, this.state.loras.map(chip))];
    // Trigger words go in front of the prompt at compile time. Showing the
    // prefix is the difference between that and the prompt quietly not being
    // what the box says it is.
    const triggers = S.promptTriggers(this.state);
    if (triggers.length) {
      parts.push(el("div", {
        class: "mmc-note",
        title: t("Prefixed to the prompt when this queues. Edit the list on the LoRA cards."),
      }, [
        el("span", { class: "mmc-note-key", text: t("triggers") }),
        el("span", { text: triggers.join(", ") }),
      ]));
    }
    return el("div", { class: "mmc-lora-block" }, parts);
  }

  renderAssets() {
    const chip = (asset) => {
      const thumb = asset.kind === "image"
        ? el("img", { class: "mmc-asset-thumb", src: viewUrl(asset.filename, { preview: true }), alt: asset.filename })
        : el("span", { class: "mmc-asset-thumb" }, [svg(ICONS[asset.kind], 15)]);
      swappable(thumb, {
        title: t("Swap the file behind @{handle} — the handle stays, so the prompt still fits.",
                 { handle: asset.handle }),
        onclick: () => this.replaceAsset(asset),
      });

      const parts = [thumb, el("span", { class: "mmc-asset-handle", text: `@${asset.handle}` })];

      if (asset.role !== "reference") {
        parts.push(el("span", { class: "mmc-asset-role", text: asset.role === "first_frame" ? t("start") : t("end") }));
      }
      if (asset.kind !== "image") {
        parts.push(el("button", {
          class: "mmc-ghost",
          style: { fontSize: "11px" },
          title: t("Use the whole clip, or only a segment of it"),
          text: trimLabel(asset),
          onclick: () => this.editSegment(asset),
        }));
      }
      if (asset.kind === "video") {
        const chip = TRACK_CHIP[asset.track] || TRACK_CHIP[S.DEFAULT_TRACK];
        parts.push(el("button", {
          class: "mmc-ghost",
          style: { fontSize: "11px" },
          title: t("On by default: this clip's soundtrack is bound as a reference audio, taking an "
               + "<Audio> slot before the video's own label, and needing the audio VAE connected. "
               + "Off references the picture silently. Pick 'sound only' in the segment editor to "
               + "reference the soundtrack without the picture."),
          text: t(chip.text),
          onclick: () => this.setTrack(asset, chip.next),
        }));
      }
      if (S.takeable(asset)) {
        parts.push(el("button", {
          class: "mmc-ghost",
          style: { fontSize: "11px" },
          title: asset.kind === "video" ? t(VIDEO_TAKES_HELP) : t(IMAGE_TAKES_HELP),
          text: t(S.takes(asset)),
          onclick: (event) => pickTakes(event.currentTarget, asset, () => this.commit()),
        }));
      }
      if (S.sizeable(asset)) {
        const size = S.refSize(asset);
        parts.push(el("button", {
          class: "mmc-ghost",
          style: { fontSize: "11px" },
          title: asset.kind === "video"
            ? t("match: scale to the generation's pixel area. max: core's 768 reference canvas — "
              + "more detail, and much the slower of the two. A video's reference tokens are its "
              + "whole grid once per latent frame, so at full length one clip is about as long as "
              + "the target video itself, and all of it rides through every sampling step.")
            : t("match: scale to the generation's pixel area. max: 2048 short edge — better identity, "
              + "several times slower, because reference tokens ride through every sampling step."),
          text: t(size),
          onclick: () => { asset.ref_size = size === "max" ? "match" : "max"; this.commit(); },
        }));
      }
      parts.push(el("button", {
        class: "mmc-asset-x", text: "✕", title: t("Remove @{handle}", { handle: asset.handle }),
        onclick: () => this.remove(asset.handle),
      }));
      return el("div", {
        class: `mmc-asset mmc-tag-${S.tagIndex(asset.handle)}`,
        title: asset.filename,
      }, parts);
    };

    // Bounded on the face (see the stylesheet), so it needs the wheel the way
    // the prompt box does — otherwise the row that scrolls zooms the canvas.
    return keepScroll(el("div", { class: "mmc-assets" }, this.state.assets.map(chip)));
  }

  renderPills(geometry, currentMode) {
    const state = this.state;
    const refs = S.hasReferences(state);
    const frameLabel = (role, fallback) => {
      const asset = S.frameAsset(state, role);
      return asset ? `@${asset.handle}` : t(fallback);
    };

    const framePill = (role, label, iconName) => {
      const blocked = S.blockedReason(state, role);
      return el("button", {
        class: "mmc-pill",
        disabled: blocked ? true : undefined,
        title: blocked || t("Choose the {label}", { label: t(label).toLowerCase() }),
        onclick: blocked ? undefined : () => this.setFrame(role),
      }, [
        icon(iconName, 16),
        el("span", {
          text: role === "first_frame" && S.continues(state)
            ? t("from last frame") : frameLabel(role, label),
        }),
      ]);
    };

    // Steps of one second up to the trained ceiling, then of five: past 15 s the
    // pill is a coarse control by then anyway, and nudging 15 → 60 one second at
    // a time is 45 clicks.
    const grain = state.duration_s >= 15 ? 5 : 1;
    const trained = isTrainedLength(geometry.frames);
    const duration = el("div", {
      class: `mmc-pill mmc-pill-group${trained ? "" : " off-distribution"}`,
      title: t("{frames} frames · {seconds} s at 24 fps", { frames: geometry.frames, seconds: geometry.seconds.toFixed(2) })
           + (trained ? "" : "\n" + t("Outside the ~5–15 s the open weights were trained on. It will "
                           + "generate, but coherence and motion are on their own past here — "
                           + "and cost rises with the square of the length.")),
    }, [
      el("button", {
        class: "mmc-step", text: "−", disabled: state.duration_s <= MIN_SECONDS || undefined,
        onclick: () => {
          const step = state.duration_s > 15 ? 5 : 1;
          state.duration_s = Math.max(MIN_SECONDS, state.duration_s - step);
          this.commit();
        },
      }),
      icon("clock", 16),
      el("span", { text: t("{seconds} s", { seconds: state.duration_s }), style: { minWidth: "38px", textAlign: "center" } }),
      el("button", {
        class: "mmc-step", text: "+", disabled: state.duration_s >= MAX_SECONDS || undefined,
        onclick: () => {
          state.duration_s = Math.min(MAX_SECONDS, state.duration_s + grain);
          this.commit();
        },
      }),
    ]);

    const aspectPill = el("button", {
      class: "mmc-pill",
      disabled: geometry.fromImage || undefined,
      title: geometry.fromImage
        ? t("The aspect ratio comes from the keyframe in the image modes — the resolution slider still sets the scale.")
        : t("Aspect Ratio"),
      onclick: (event) => this.openAspect(event.currentTarget),
    }, geometry.fromImage
      // The ratio the keyframe brought with it, which is the one case where the
      // pill is showing a shape no entry in the list would have drawn.
      ? [aspectGlyph(geometry.ratio, PILL_GLYPH),
         el("span", { text: describeRatio(geometry.ratio) }),
         el("span", { class: "mmc-pill-sub", text: t("from image") })]
      : [aspectGlyph(geometry.ratio, PILL_GLYPH), el("span", { text: state.aspect })]);

    // With two passes on, the sub says so in one glance: sampled at the
    // first-pass edge, refined up to the size beside it.
    const refined = S.twoPass(state);
    const resPill = el("button", {
      class: "mmc-pill",
      title: refined
        ? t("Sampled at a {edge} px short edge, refined up to {width} × {height} by a second pass.",
            { edge: S.sampleEdge(state), width: geometry.width, height: geometry.height })
        : t("Short edge. Lower is faster; 768 is what the open weights were trained at."),
      onclick: (event) => this.openResolution(event.currentTarget),
    }, [
      icon("res", 16),
      el("span", { text: `${state.short_edge}p` }),
      el("span", { class: "mmc-pill-sub", text: refined
        ? `${S.sampleEdge(state)} → ${geometry.width} × ${geometry.height}`
        : `${geometry.width} × ${geometry.height}` }),
    ]);

    return el("div", { class: "mmc-pills" }, [
      ...(this.continuePill ? [this.renderContinue()] : []),
      framePill("first_frame", "Start frame", "frameIn"),
      framePill("last_frame", "End frame", "frameOut"),
      // A body that is not making a video says how long it runs in its own
      // terms, or not at all — see `extraPills`.
      ...(this.durationPill ? [duration] : []),
      ...(this.extraPills?.() ?? []),
      // In a timeline the canvas belongs to the timeline, not to one shot: the
      // segments are concatenated at the end and have to come out the same size.
      // The output folder is the timeline's for the same reason — one file.
      ...(this.canvasPills ? [aspectPill, resPill] : []),
      this.renderRouting(currentMode),
      ...(this.pieceView ? [this.renderPieceViewPill()] : []),
      ...(this.preStage ? [this.renderPreStagePill()] : []),
    ]);
  }

  /** The piece-view toggle. See `options.pieceView` — it is the only way to the
   *  piece's own controls while the piece is one shot, and the way back once
   *  you are there. */
  renderPieceViewPill() {
    const on = this.pieceView.shown();
    return el("button", {
      class: `mmc-pill mmc-piece-toggle${on ? " on" : ""}`,
      "aria-pressed": on ? "true" : "false",
      title: on
        ? t("Showing the whole piece. Click to go back to the shot.")
        : t("Show the whole piece: the standing prompt every shot inherits, the "
          + "reference pool, and the LoRAs patched onto all of them."),
      onclick: () => this.pieceView.toggle(),
    }, [icon("timeline", 16), el("span", { text: t("Timeline") })]);
  }

  /** The pre-stage pill: an image-generation node at this node's left edge,
   *  spawned and removed here because the pre-stage is a property of the shot
   *  being set up, not a node to hunt the menu for. */
  renderPreStagePill() {
    const on = this.preStage.active();
    return el("button", {
      class: `mmc-pill mmc-prestage-toggle${on ? " on" : ""}`,
      title: on
        ? t("The pre-stage node on the left generates stills for this render — start and end "
          + "frames, references, style sheets. Click to remove it.")
        : t("Add a pre-stage: an image node (Krea 2 / Ideogram 4) at this node's left edge whose "
          + "stills land here as start/end frames or references with one click."),
      onclick: () => { this.preStage.toggle(); this.render(); },
    }, [icon("image", 16), el("span", { text: t("pre-stage") })]);
  }

  /**
   * A finished pre-stage still, pushed into this state by the neighbour's
   * result chips. Returns a refusal message, or null on success — the same
   * capacity and exclusivity rules every other attach path answers to, said to
   * the PreStage so it can show them where the click happened.
   */
  attachFromPreStage({ role, filename }) {
    if (role === "reference") {
      const blocked = S.blockedReason(this.state, "reference");
      if (blocked) return blocked;
      const { used, max, filesLeft } = S.capacity(this.state, "image");
      if (used >= max || filesLeft <= 0) {
        return t("No {kind} slots left ({used}/{max} used, {filesLeft} files free of {maxFiles}).",
          { kind: t("image"), used, max, filesLeft, maxFiles: S.MAX_REF_FILES });
      }
      this.state.assets.push({
        handle: S.nextHandle(this.state, "image"),
        kind: "image", role: "reference", filename, ref_size: "max",
      });
      this.commit();
      return null;
    }
    const blocked = S.blockedReason(this.state, role);
    if (blocked) return blocked;
    const existing = S.frameAsset(this.state, role);
    if (existing) this.remove(existing.handle, { silent: true });
    this.state.assets.push({
      handle: S.nextHandle(this.state, "image"),
      kind: "image", role, filename,
    });
    this.commit();
    this.probeKeyframe();
    return null;
  }

  /**
   * The continuation switch, on a timeline segment after the first.
   *
   * Off is a hard cut. On makes the previous segment's last frame this one's
   * start frame — which is a keyframe generation, and so locks the references
   * out for the same reason a real start frame does.
   */
  renderContinue() {
    const on = S.continues(this.state);
    const blocked = on ? null : S.blockedReason(this.state, "continue");
    return el("button", {
      class: `mmc-pill mmc-continue${on ? " on" : ""}`,
      disabled: blocked ? true : undefined,
      title: blocked || (on
        ? t("Starts from the previous segment's last frame. Click for a hard cut instead.")
        : t("Hard cut from the previous segment. Click to start from its last frame.")),
      onclick: blocked ? undefined : () => {
        this.state.continue = !on;
        this.commit();
      },
    }, [icon("frameIn", 16), el("span", { text: on ? t("continues") : t("hard cut") })]);
  }

  /**
   * The mode and the weights it runs on, and — where there is a choice — the
   * control that changes the second without changing the first.
   *
   * Two things can decide the weights. The node-level **route** is a standing
   * instruction and wins outright; failing that, this generation's own pin does,
   * and failing that the mode. Clicking cycles the route, because that is the
   * one of the two that survives a mode change: pinning per generation is
   * dropped the moment attaching a reference makes it illegal, so a preference
   * expressed there quietly evaporates. `routeOf` is null in a timeline segment
   * editor, where the route belongs to the timeline and this is a readout.
   */
  renderRouting(currentMode) {
    const state = this.state;
    const route = this.routeOf?.() ?? "auto";
    const forced = route !== "auto";
    const routed = forced ? route : S.checkpoint(state);
    const pinned = !forced && S.checkpointPinned(state);
    // Forcing FL2VA on a reference generation is refused at compile time, so the
    // badge says so here rather than letting the queue do it.
    const impossible = forced && route === "fl2va" && S.hasReferences(state);
    const canCycle = !!this.setRoute;

    const badge = el(canCycle ? "button" : "span", {
      class: `mmc-mode${forced || pinned ? " pinned" : ""}${impossible ? " bad" : ""}`,
      title: impossible
        ? t("This generation has references, which are encoded for Ref2VA and cannot be "
          + "read by FL2VA. It will be refused — change the route to auto or Ref2VA.")
        : forced
          ? t("Every generation on this node runs on {label}, whatever the mode derives. Click to change it.",
              { label: S.CHECKPOINT_LABEL[route] })
          : canCycle
            ? t("Following the mode. Click to run everything on one checkpoint instead — "
              + "Ref2VA takes the text-only and keyframe payloads too.")
            : t("Following the timeline's route."),
      onclick: canCycle ? () => this.setRoute(S.nextRoute(route)) : undefined,
    });
    badge.appendChild(el("b", { text: currentMode }));
    badge.appendChild(document.createTextNode(` → ${S.CHECKPOINT_LABEL[routed]}`));
    if (forced) badge.appendChild(el("span", { class: "mmc-pin", text: t("always") }));
    else if (pinned) badge.appendChild(el("span", { class: "mmc-pin", text: t("pinned") }));
    return badge;
  }

  /** Handles in the prompt with no asset behind them — the state's own or the
   *  piece's pool. compile.py rejects these, so say so here rather than at
   *  queue time. */
  renderDangling() {
    const known = new Set([
      ...this.state.assets.map((a) => a.handle),
      ...(this.state.pool ?? []).map((a) => a.handle),
    ]);
    const missing = [...new Set(Array.from(this.state.prompt.matchAll(HANDLE_RE), (m) => m[1]))]
      .filter((handle) => !known.has(handle));
    if (!missing.length) return null;
    return [el("div", {
      class: "mmc-warn",
      text: missing.length > 1
        ? t("{handles} are in the prompt but not attached.", { handles: missing.map((h) => "@" + h).join(", ") })
        : t("{handles} is in the prompt but not attached.", { handles: missing.map((h) => "@" + h).join(", ") }),
    })];
  }

  // ---- popovers ------------------------------------------------------------

  openAspect(anchor) {
    openAspectPopover(anchor, this.piece, () => this.commit());
  }

  openResolution(anchor) {
    openResolutionPopover(anchor, this.piece, () => {
      const asset = S.frameAsset(this.state, "first_frame") || S.frameAsset(this.state, "last_frame");
      return S.resolved(this.state, asset ? this.sizes.get(asset.filename) : null);
    }, () => this.commit());
  }
}
