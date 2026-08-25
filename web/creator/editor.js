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

import { el, icon, ICONS, dismissable, keepScroll, placeNear, svg, swappable } from "./dom.js";
import { CastShelf } from "./cast.js";
import { t } from "./i18n.js";
import { openPicker } from "./picker.js";
import { openLoras, loraBlock } from "./loras.js";
import { openSettings } from "./settings.js";
import { openPresetLibrary, styleCastMember } from "./presetlib.js";
import { castIntoPiece, keepSubject } from "./presets.js";
import { openTrim, trimLabel } from "./trim.js";
import { PromptBox, focusEnd, openEditorSheet } from "./prompt.js";
import { RefinePanel, refineButton, refine } from "./refine.js";
import { openAspectPopover, openResolutionPopover, openChoicePopover, facesPill, aspectGlyph,
         resolutionPillText,
         PILL_GLYPH, pillSet, pillClass } from "./pills.js";
import { blobIO, samplingBar, segmentSeedPill } from "./sampling.js";
import { Stage } from "./stage.js";
import { familyPill, weightsPill, loadCatalog, adoptWeights } from "./models.js";
import * as Turbo from "./turbo.js";
import { viewUrl, probe, probeAudio, primeSettings } from "./api.js";
import * as S from "./state.js";
import { describeRatio, framesForSeconds, isTrainedLength,
         rulesFor, secondsForFrames } from "./canvas.js";

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
export const AUDIO_TAKES_HELP =
  "What of this sound is the reference. full: the whole clip. voice: its "
  + "timbre and delivery, carried onto whoever speaks, without its words. "
  + "music: its genre, instrumentation and mood, not the recording. ambience: "
  + "its room tone and texture. copy: the signal itself becomes the video's "
  + "own audio. Read by Refine, and worth saying in the prompt too if you skip "
  + "refining.";

/** The tooltip for a scope chip — one per vocabulary, so a clip taken for its
 *  soundtrack alone is explained as the audio it has become. */
export const takesHelp = (asset) =>
  ({ image: IMAGE_TAKES_HELP, video: VIDEO_TAKES_HELP, audio: AUDIO_TAKES_HELP })[S.scopeKind(asset)];

/**
 * What somebody has set on a reference, in the fewest words that still say it.
 *
 * Only the answers that were chosen. Every one of these has a default that is
 * the whole file, whole clip, sound on, canvas-matched — and a chip reciting
 * four of those said nothing four times. Empty for an ordinary file, which is
 * most of them.
 */
export function referenceSummary(asset) {
  const said = [];
  if (S.takeable(asset) && S.takes(asset) !== "full") said.push(t(S.takes(asset)));
  if (asset.kind !== "image" && asset.trim) said.push(trimLabel(asset));
  if (asset.kind === "video" && (asset.track ?? S.DEFAULT_TRACK) !== S.DEFAULT_TRACK) {
    said.push(t(TRACK_CHIP[asset.track]?.text ?? ""));
  }
  if (S.sizeable(asset) && S.refSize(asset) !== S.DEFAULT_REF_SIZE[asset.kind]) {
    said.push(t(S.refSize(asset)));
  }
  return said.filter(Boolean).join(" · ");
}

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
   * @param {() => Element[]} [options.modelPill]  what to put in the row's first
   *   slot instead of the video family pill. Supplied by a body whose model is
   *   not one of the video families — the pre-stage names an image architecture
   *   there — so the slot holds the same question on every surface even where
   *   the answer comes from a different list.
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
                durationPill = true, extraPills = null, modelPill = null, extraTools = null,
                settingsTool = true, stage = null, editorTitle = null,
                piece = null, castPiece = null, growShot = null, presetTarget = null,
                samplingStore = null,
                clearTool = null, seedTarget = null, compiledPrompt = null,
                castFromLibrary = null, fullscreen = null }) {
    // The one sampler setting a card may answer for itself — see
    // `segmentSeedPill`. Null on a node body, which owns the whole row.
    this.seedTarget = seedTarget;
    this.presetTarget = presetTarget;
    // Who to hand a kept cast member to. Not derivable here: this body is a
    // node face on one host and one card of a strip on another, and only the
    // second one is a shot whose cast is owned a level up. See the `@` menu's
    // `castFromLibrary` hook.
    this.castFromLibrary = castFromLibrary;
    this.piece = piece ?? state;
    // Where the sampler row is kept, which is not always where the piece is.
    // The pre-stage's H3 branch mounts this body on a *nested* creator request
    // (`state.minimax.request`) while the sampler widgets belong to the
    // pre-stage node itself — one row for all three architectures — so a row
    // written into the request would be serialized by `serializeStill`, which
    // does not carry one, and would be gone by the next load. Defaults to the
    // piece, which is the answer on every body that owns its own row.
    this.samplingStore = samplingStore ?? {
      read: () => this.piece.sampling,
      write: (block) => { this.piece.sampling = block; },
    };
    // Where the cast lives, which is not always where the piece does. A card of
    // a strip is one shot of a piece whose subjects are kept a level up, and its
    // `piece` is the card itself — so without this, clicking somebody's name in
    // a card looked them up in an empty list and deleting their chip took them
    // out of nothing. Defaults to the piece, which is the answer on every body
    // that owns its own cast.
    this.castPiece = castPiece ?? this.piece;
    // The piece's way to grow a shot, when this body's owner has one — a pill
    // in the tail of the row, beside the other two controls that act on the
    // piece rather than on this shot. See `renderGrowPill`.
    this.growShot = growShot;
    // What the window this body opens into is called. A node face is a preview
    // of one generation, and the window is that generation — so the owner names
    // it for what it makes rather than for the control that opened it.
    this.editorTitle = editorTitle ?? t("Shot");
    this.preStage = preStage;
    this.pieceView = pieceView;
    this.durationPill = durationPill;
    this.settingsTool = settingsTool;
    // The finished, sectioned prompt for whichever pass this body's shot lands
    // in — what the box's second view shows. Not derivable here: it takes the
    // whole piece to compile one shot, and this body is handed one card. Absent
    // where nothing can answer, and the view goes with it.
    this.compiledPrompt = compiledPrompt;
    this.extraPills = extraPills;
    this.modelPill = modelPill;
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
    // Opens the shell on this piece, where the host has a node to open it on.
    // Null in a window and in a card's editor: both are already something other
    // than a node face, and neither has a node of its own to draw over.
    this.fullscreen = fullscreen;
    this.sizes = new Map();   // filename -> {width,height}, for the adaptive canvas readout
    // filename -> seconds, null while the probe is out. The other half of the
    // same header: how long a reference runs, which is what the duration pill
    // offers to match the card to.
    this.lengths = new Map();

    this.prompt = new PromptBox({
      getState: () => this.state,
      onInput: (text) => {
        this.state.prompt = text;
        this.onCommit?.();
        this.renderNotices();   // dangling-handle warning, without disturbing the caret
        // Citing a pool reference is what attaches it, so the finished prompt
        // moves on keystrokes that never touch the sentence's own words.
        this.prompt.refreshCompiled();
      },
      compiled: this.compiledPrompt ? () => this.compiledPrompt() : null,
      onAttach: (row) => this.attachFromMention(row),
      attachBlocked: (action) => S.blockedReason(this.state, action),
      // The piece's reference pool, where this state is a timeline segment —
      // `syncTimeline` mirrors it on as `pool`, the way the canvas rides on.
      // Citable by chip, never attached: the citation is the attachment.
      getPool: () => this.state.pool ?? [],
      // Mirrored down by `syncTimeline` beside the pool — see `state.cast`.
      getCast: () => this.state.cast ?? [],
      // Typing `@ann` into the sentence offers the roster, and picking somebody
      // out of it casts them here with their files. The shelf opens with them: they
      // have just arrived, and the card that says what they are made of is the
      // thing to look at next.
      castFromLibrary: this.castFromLibrary
        ? (member) => {
            const handle = this.castFromLibrary(member);
            if (handle) { this.castOpen = true; this.render(); }
            return handle;
          }
        : null,
      // A look picked out of the `/` menu. Onto the piece, where a cast lives —
      // the same place `castFromLibrary` puts somebody, and for the same reason:
      // this body may be one shot of a piece owned a level up. Offered only
      // where the cast lands on a piece — a pre-stage's body is this same class
      // over one image request, which has no cast and no segments, so the Style
      // rows stay out of its menu the way the roster already does.
      castStyle: this.castPiece?.subjects !== undefined || this.nodeId
        ? (row) => {
            const subject = castIntoPiece(styleCastMember(row, 0), this.castPiece);
            this.commit();
            return subject?.handle ?? null;
          }
        : null,
      onOverflow: (over) => this.onPromptOverflow(over),
      // The `/` menu's two doors. Both are rail tools already — this only puts
      // them on the keyboard, in the box where the sentence that needs them is
      // being written. Omitted where the tool itself is: a body with no preset
      // target has no library to open.
      openLibrary: this.presetTarget
        ? (scope) => openPresetLibrary({ target: this.presetTarget(), scope })
            .then(() => this.render())
        : null,
      onBrowse: () => this.addReferences("image"),
      // A name is a door, on every body that draws one. This used to be offered
      // only on a node face, on the grounds that a card of a strip has its cast
      // a level up — but the cast is reachable from here now (`castPiece`), and
      // a chip you could see and not open was the same dead end from the other
      // side.
      onCastChip: (handle) => this.openCastMember(handle),
      onUncited: (handles) => this.dropCited(handles),
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
    // Named because a host holding a hidden row is still a row of the column,
    // costing the gap either side of it — the stylesheet needs something to
    // fold away rather than an empty div to leave standing. See
    // styles/fullscreen.js, where the cast's host is folded exactly that way.
    this.assetsHost = el("div", { class: "mmc-assets-host" });
    // The cast, under the files it is built out of, because a subject is built
    // out of what is there and reads as nonsense above it. Empty unless this
    // body owns the piece's cast — see `renderCastShelf`.
    this.castHost = el("div", { class: "mmc-cast-host" });
    this.loraHost = el("div");
    this.pillsHost = el("div");
    this.noticeHost = el("div");
    // Last, the way the Timeline puts it last: the panel says what the piece is
    // and this says how it is run.
    // Named so the fullscreen shell can fold it away in the simple view —
    // see styles/fullscreen.js. Nothing else keys off the class.
    this.samplingHost = el("div", { class: "mmc-sampling-host" });

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
      this.castHost,
      this.loraHost,
      // `frame`, not `root`: the box brings its own disclosure, which folds it
      // away once a rewrite is what gets queued.
      this.panel = el("div", { class: "mmc-panel" }, [
        ...(this.onFace ? [this.expandHost] : []),
        this.prompt.frame, this.refinePanel.root, this.pillsHost,
      ]),
      this.noticeHost,
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
    // Both answers the rescue draws on arrive asynchronously — the folder
    // listing and this machine's remembered picks — so it is run behind each of
    // them rather than behind whichever happens to land second.
    if (this.nodeId && this.piece === this.state) {
      loadCatalog(() => this.adoptWeights());
      primeSettings(() => this.adoptWeights());
    }

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
    if (adoptWeights(this.piece)) this.commit();
    else this.render();
  }


  /** The sampler row's `{value, set}` pair — the piece's, not the card's.
   *
   *  Still spelled `widgetIO` at every call site and still keyed by the same
   *  names, but the values are in `piece.sampling` now rather than on the node's
   *  widgets; the seed is the exception. See `sampling.blobIO`.
   *
   *  `onCommit` rather than `commit`: commit calls `Turbo.sync`, which sets
   *  pills, which would come back through here.
   */
  widgetIO() {
    return blobIO(
      () => this.samplingWidgets,
      () => this.samplingStore.read(),
      (block) => { this.samplingStore.write(block); this.onCommit?.(); },
      () => this.onWidgetChange?.());
  }

  commit() {
    // Before notifying, because attaching a reference can invalidate a
    // checkpoint pin that was legal when it was made.
    S.normalizeCheckpoint(this.state, S.pieceFamily(this.piece));
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
    this.lengths.clear();
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
      cardSeconds: this.cardSeconds(),
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
      cardSeconds: this.cardSeconds(),
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
    this.probeKeyframe();
    if (asset.role === "reference" && asset.kind === "video" && !picked.track) {
      await this.applySoundDefault(asset);
    }
  }

  /**
   * Every text of this shot a citation could be written into.
   *
   * The rewrite is in the list because `compile.refined_body` puts it in *place*
   * of the prompt: a shot whose rewrite is on and still writes `@img-1` cites
   * `@img-1`, and the sentence it was rewritten from no longer decides anything.
   * Mirrors `state.poolTexts` and `compile.cited_pool` — the same three fields
   * and the same rewrite, which is what makes "cited" mean one thing.
   */
  citingTexts() {
    const refined = this.state.refined;
    const rewrite = refined && refined.enabled !== false
      ? [refined.body, ...Object.values(refined.sections ?? {})]
      : [];
    return [this.state.prompt, this.state.soundscape, this.state.music, ...rewrite];
  }

  /**
   * Chips just deleted out of the sentence: take what they named out of the run.
   *
   * The @ menu is how a file is attached in this redesign and how somebody is
   * cast — picking one writes the chip and creates the thing at once — so the
   * chip *is* the attachment, and deleting it has to mean something. It used to
   * mean nothing: the file stayed on the reference row and the member stayed on
   * the cast shelf, both invisible to a user who had just taken them out of the
   * shot, and both still sent. An uncited cast member is cut at queue time
   * (`compile` does it, and its files with it) but a bare `@img-1` reference is
   * not — it is in `assets`, and everything live in `assets` is encoded and
   * shown to the model. So deleting the mention left a picture conditioning a
   * render that never mentions it, which is exactly as strong a conditioning as
   * one that does.
   *
   * Then it meant too much: the reference was detached outright, and a mention
   * deleted while trying a sentence without it cost the file, the handle, the
   * narrowing and the trim. A member leaves — that is what deleting their name
   * is for — but their picture is muted rather than binned, which is the state
   * "out of this shot, still on the node" already had a word for.
   *
   * Only what is no longer written anywhere. A handle the same shot still cites
   * from its soundscape, or another card of the same piece still cites, stays —
   * the deletion was of one occurrence, not of the reference.
   *
   * The pool is not touched. It belongs to the piece, one card is not the place
   * a file is taken off every other card, and it does not need to be: an uncited
   * pool asset is already not injected into this generation.
   */
  dropCited(handles) {
    if (!handles?.length) return;
    let dropped = false;

    // The cast first, so the pictures a departing member alone was built out of
    // are still findable when the files are swept below.
    const orphans = [];
    for (const handle of handles) {
      const cast = this.castPiece.subjects ?? [];
      const subject = cast.find((s) => s.handle === handle);
      if (!subject) continue;
      // Piece-wide: a member deleted from shot 3 is still in the piece while
      // shot 5 writes them. `match` rather than `test`, because the pattern is
      // global and a global regex tested twice in a row answers from wherever
      // the first test left off.
      const pattern = S.subjectCitationRe([subject]);
      const stillCited = [...this.citingTexts(),
                          ...(this.castPiece === this.state ? [] : S.allTexts(this.castPiece))]
        .some((text) => String(text ?? "").match(pattern));
      if (stillCited) continue;
      orphans.push(...S.soleClaims(subject, cast));
      // The shelf drops an open card whose member is no longer in the cast on
      // its next render, so there is nothing to tell it.
      this.castPiece.subjects = cast.filter((s) => s !== subject);
      dropped = true;
    }

    const texts = [...this.citingTexts(),
                   ...(this.castPiece === this.state ? [] : S.allTexts(this.castPiece))];
    const gone = (handle) => !S.handleWritten(texts, handle);

    // A departing member's leavings do go. Their pictures are on this shot
    // because casting them put them there, so with nobody left to be a picture
    // *of* there is nothing to mute — see `soleClaims`.
    const orphaned = new Set(orphans);
    const before = this.state.assets.length;
    this.state.assets = this.state.assets.filter(
      (asset) => asset.role !== "reference" || !orphaned.has(asset.handle) || !gone(asset.handle));
    if (this.state.assets.length !== before) dropped = true;

    // The reference whose name was deleted is muted, not detached.
    //
    // Deleting the mention is how you take a picture out of a shot, and taking
    // something out of a shot is not the same as throwing it away. It used to
    // be both, so a mention deleted by accident — or on purpose, while trying a
    // sentence without it — cost the file, the handle, the narrowing and the
    // trim, and getting it back meant the picker and setting all of that up
    // again. Muted it is still in the row, dimmed, one press from live, and it
    // does not reach the model in the meantime. Which is what the deletion
    // meant.
    //
    // Only this shot's own attachments. A keyframe is where the shot opens or
    // closes rather than something the prompt reaches for, and keeps its handle
    // whether or not the text ever writes it; the pool is the piece's, and one
    // card is not the place a file is taken off every other card.
    for (const asset of this.state.assets) {
      if (asset.role !== "reference" || S.muted(asset)) continue;
      if (!handles.includes(asset.handle) || !gone(asset.handle)) continue;
      asset.enabled = false;
      dropped = true;
    }

    // `commit` redraws — the reference row and the cast shelf are both what
    // just changed, and both are what the user is looking at. The box itself is
    // left alone: `refresh` stands down while it holds the caret, which it does,
    // because a keystroke in it is what brought us here.
    if (dropped) this.commit();
  }

  /**
   * Everything about one reference, opened from its name.
   *
   * The row of chips this replaces had one button per narrowing, sized to fit a
   * node face, and the simple fullscreen view hid any of them still holding a
   * default — so on the view meant to become the only one, a picture you had
   * just attached could not be made a style reference at all. The default is
   * precisely the state you are trying to leave.
   *
   * So the chip says what was *set* and the name opens the rest. One card,
   * identical on a node face and in either fullscreen view, which is one fewer
   * thing that has to be true twice.
   *
   * No nested popovers: every choice here is a row of options in the card
   * itself, because a menu opened from a menu is dismissed by the click that
   * opens it — `dismissable` closes on any pointerdown outside its own element,
   * and a child popover is outside its parent.
   */
  openReferenceSheet(anchor, asset) {
    const pop = el("div", { class: "mmc-pop mmc-refsheet" });

    // A row of answers, one of them current. Written flat rather than as a menu
    // because the whole list is four or five words, and because a menu opened
    // from a menu is dismissed by the click that opens it — `dismissable`
    // closes on any pointerdown outside its own element, and a child popover
    // is outside its parent.
    const choose = (name, help, options, current, pick) => el("div", {
      class: "mmc-refsheet-row",
    }, [
      el("span", { class: "mmc-refsheet-name", title: help, text: name }),
      el("div", { class: "mmc-refsheet-opts" }, options.map(({ key, label }) => el("button", {
        class: "mmc-refsheet-opt",
        "aria-checked": String(key === current),
        onclick: () => { pick(key); paint(); },
      }, [el("span", { text: label })]))),
    ]);

    // The two that open a window of their own close this card first: a popover
    // left standing under a modal is one the modal's own Escape would have to
    // know about.
    const opens = (label, title, run, danger = false) => el("button", {
      class: `mmc-refsheet-go${danger ? " danger" : ""}`,
      title, text: label,
      onclick: () => { close(); run(); },
    });

    // Rebuilt after every pick rather than patched: a commit redraws the body
    // and replaces the chip this hangs off, so the marks in here are the only
    // state left to keep true, and rewriting six buttons is cheaper than
    // reasoning about which one changed. The card is portalled to <body>, so
    // the body's redraw does not take it with it; `placeNear` leaves it where
    // it is once its anchor goes.
    const paint = () => {
      const rows = [];
      if (S.takeable(asset)) {
        // The one people came here for. "Reads as" rather than "takes": it says
        // what the model does with the file, which is the question being asked.
        rows.push(choose(t("reads as"), t(takesHelp(asset)),
          S.takeOptions(asset).map((key) => ({ key, label: t(key) })),
          S.takes(asset),
          (key) => {
            if (key === "full") delete asset.takes;
            else asset.takes = key;
            this.commit();
          }));
      }
      if (asset.kind === "video") {
        rows.push(choose(t("sound"),
          t("On by default: this clip's soundtrack is bound as a reference audio, taking an "
          + "<Audio> slot before the video's own label, and needing the audio VAE connected. "
          + "Off references the picture silently. Sound only references the soundtrack "
          + "without the picture."),
          Object.entries(TRACK_CHIP).map(([key, chip]) => ({ key, label: t(chip.text) })),
          asset.track ?? S.DEFAULT_TRACK,
          (key) => this.setTrack(asset, key)));
      }
      if (S.sizeable(asset)) {
        rows.push(choose(t("detail"),
          asset.kind === "video"
            ? t("match: scale to the generation's pixel area. max: core's 768 reference canvas — "
              + "more detail, and much the slower of the two. A video's reference tokens are its "
              + "whole grid once per latent frame, so at full length one clip is about as long as "
              + "the target video itself, and all of it rides through every sampling step.")
            : t("match: scale to the generation's pixel area. max: 2048 short edge — better identity, "
              + "several times slower, because reference tokens ride through every sampling step."),
          [{ key: "match", label: t("match") }, { key: "max", label: t("max") }],
          S.refSize(asset),
          (key) => { asset.ref_size = key; this.commit(); }));
      }

      const note = asset.kind === "image" ? null : this.lengthNote(asset);
      if (note) rows.push(el("div", { class: "mmc-refsheet-row mmc-refsheet-len" }, [
        el("span", { class: "mmc-refsheet-name", text: t("length") }),
        el("span", { class: "mmc-refsheet-note", text: note }),
      ]));

      const foot = [];
      if (asset.kind !== "image") {
        foot.push(opens(trimLabel(asset), t("Use the whole clip, or only a segment of it"),
                        () => this.editSegment(asset)));
      }
      foot.push(opens(t("Swap file"),
                      t("Swap the file behind @{handle} — the handle stays, so the prompt still fits.",
                        { handle: asset.handle }),
                      () => this.replaceAsset(asset)));
      foot.push(opens(t("Remove"), t("Remove @{handle}", { handle: asset.handle }),
                      () => this.remove(asset.handle), true));

      pop.replaceChildren(
        el("div", { class: "mmc-pop-title mmc-refsheet-head" }, [
          el("span", { class: `mmc-refsheet-handle mmc-tag-${S.tagIndex(asset.handle)}`,
                       text: `@${asset.handle}` }),
          el("span", { class: "mmc-refsheet-file", text: asset.filename }),
        ]),
        ...rows,
        el("div", { class: "mmc-refsheet-foot" }, foot),
      );
    };

    paint();
    document.body.appendChild(pop);
    placeNear(pop, anchor);
    const close = dismissable(pop);
  }

  /** How long this card actually runs — the frame count's own length, not the
   *  number on the pill. What the segment editor cuts a reference to, and what
   *  a reference longer than it loses. */
  cardSeconds() {
    // The piece's family's grid and rate: the count this snaps to is the
    // weights', and a card carries neither.
    const rules = rulesFor(S.pieceFamily(this.piece));
    return secondsForFrames(framesForSeconds(this.state.duration_s, rules), rules);
  }

  /** The segment editor, on an already-attached clip. */
  async editSegment(asset) {
    const result = await openTrim({
      path: asset.filename,
      kind: asset.kind,
      trim: asset.trim ?? null,
      track: asset.track,
      showTrack: asset.kind === "video",
      cardSeconds: this.cardSeconds(),
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

  /** Pixel sizes for the adaptive-canvas readout: the frames, and every
   *  attached picture the aspect popover can offer as a source. The backend
   *  re-reads them from disk; this is only so the pills and the list can tell
   *  the truth early. Stills are measured in an <img>; a video's size comes
   *  off the probe route, like a clip card's. A file that cannot be read
   *  stays unmeasured and the readout keeps the preset. */
  probeKeyframe() {
    for (const asset of S.aspectDonors(this.state)) {
      if (this.sizes.has(asset.filename)) continue;
      this.sizes.set(asset.filename, null);
      if (asset.kind === "video") {
        probe(asset.filename).then(({ width, height }) => {
          if (!width || !height) return;
          this.sizes.set(asset.filename, { width, height });
          this.render();
        });
        continue;
      }
      const measure = new Image();
      measure.onload = () => {
        this.sizes.set(asset.filename, { width: measure.naturalWidth, height: measure.naturalHeight });
        this.render();
      };
      measure.src = viewUrl(asset.filename);
    }
  }

  /** How long every reference on this card runs, off the same header the sizes
   *  come from. Stills are not asked, so a card of pictures costs no round
   *  trips; a trimmed clip is not asked either, because the range is the
   *  length. */
  probeLengths() {
    for (const asset of [...S.references(this.state), ...S.citedPool(this.state)]) {
      if (asset.kind === "image") continue;
      if (asset.trim || this.lengths.has(asset.filename)) continue;
      this.lengths.set(asset.filename, null);
      probe(asset.filename).then(({ duration }) => {
        if (!duration) return;
        this.lengths.set(asset.filename, duration);
        this.render();
      });
    }
  }

  /** The seconds cache as `S.refSeconds` wants it. */
  lengthOf(filename) {
    return this.lengths.get(filename) ?? null;
  }

  /** The picture this editor is about to make: the canvas, and how long it runs.
   *  For a host that has to draw the frame before there is anything in it — the
   *  fullscreen editor's dock, which is a column of nothing until the first
   *  render lands (see fullscreen.js). The same shape `TimelineBody.frame`
   *  returns, because it is the same question asked of one shot. */
  frame() {
    const source = S.aspectSourceAsset(this.state);
    const { width, height, seconds } =
      S.resolved(this.state, source ? this.sizes.get(source.filename) : null, this.piece);
    return { width, height, seconds };
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
    this.onRender?.();
    this.probeKeyframe();
    this.probeLengths();
    const source = S.aspectSourceAsset(state);
    const geometry = S.resolved(state, source ? this.sizes.get(source.filename) : null, this.piece);

    this.railHost.replaceChildren(this.renderRail());
    this.assetsHost.replaceChildren(...(state.assets.length ? [this.renderAssets()] : []));
    this.renderCastShelf();
    this.loraHost.replaceChildren(...(state.loras.length ? [this.renderLoras()] : []));
    this.pillsHost.replaceChildren(
      this.renderPills(geometry, S.mode(state, this.piece)));
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
      // Which family's row to draw. The values still go through the same
      // `{value, set}` pair — they are in the blob either way — but which
      // controls exist is the family's, and H3's are not a superset of LTX's.
      family: S.pieceFamily(this.piece),
      widgets: this.samplingWidgets,
      // The piece's pair, not a second one over the widgets: the row moved into
      // the blob and this call site did not follow it. Every pill went on
      // drawing and writing widgets nothing else reads, so the turbo switch put
      // its six steps and euler + beta in the blob — where the render takes
      // them from — while the row kept showing twenty and res_multistep, and a
      // step count dialled afterwards was overruled by the blob it never wrote.
      ...this.widgetIO(),
      // `blobIO` does not redraw on write, by design; a body that wants the
      // redraw does it in its own `set`. See `sampling.widgetIO`.
      set: (name, value) => { this.widgetIO().set(name, value); this.render(); },
      // One generation, always: a Creator render has no segments to spread a
      // seed across.
      perSegment: false,
      // The turbo switch, for a node body only: a timeline segment has no
      // sampler of its own to throw it on — and only for a family that declares
      // a distillation, since every number the switch throws is that family's.
      turbo: this.nodeId && S.turboOf(S.pieceFamily(this.piece)) ? Turbo.turboPills({
        container: this.piece,
        ...this.widgetIO(),
        onCommit: () => this.commit(),
      }) : [],
      // Last on the row, because it is the one thing there you set when you
      // install a checkpoint rather than when you write a prompt. The face pass
      // goes in front of it: it is a thing done to the render, like the
      // accelerators it sits beside, rather than a file you picked once.
      //
      // The family pill used to stand between them, and does not any more: it
      // leads the pill row above instead — see `familyPill`.
      trailing: this.nodeId ? [
        // Only where there is a face pass to switch on. It is H3's crop-and-
        // repair loop, written against its detector and its re-encode, and a
        // family that declares `face: false` has no such pass — so the pill was
        // a switch for something that could never run, sitting on the row
        // saying "faces off" as though the choice were yours.
        //
        // Or where one is already on, which is a piece carried onto such a
        // family with the pass switched on behind it. In force means visible,
        // and here it is not a nicety: `emit.py` asks the family for a
        // `face_payload` the moment it sees one, and a family that has no such
        // method raises. A pill you can switch off is the difference between a
        // render that says what is wrong and one that stops.
        ...(S.canDo(this.piece, "face") || this.piece.face?.on
          ? [facesPill({ target: this.piece, commit: () => this.commit() })] : []),
        weightsPill({
          piece: this.piece,
          models: this.piece.models,
          checkpoints: S.checkpointsFor(this.state, S.pieceFamily(this.piece)),
          face: Boolean(this.piece.face?.on),
          onChange: () => this.commit(),
          turbo: { container: this.piece, widgetIO: this.widgetIO() },
        }),
      ] : [],
    })] : []));
    this.prompt.refresh();
    this.syncPrompt();
    this.prompt.refreshCompiled();
    this.refinePanel.render();
    this.renderExpand();
    this.renderNotices();
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
      castPiece: this.castPiece,
      durationPill: this.durationPill,
      extraPills: this.extraPills,
      extraTools: this.extraTools,
      settingsTool: this.settingsTool,
      compiledPrompt: this.compiledPrompt,
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

  /**
   * The cast, on the node's own face.
   *
   * There is one node, and a cast belongs to the piece it makes — so the shelf
   * that was only ever in the Timeline window belongs here too, and it is
   * literally the same shelf (`cast.js`). What is different here is only the
   * scope: the files somebody can be built out of are this shot's own
   * attachments plus whatever pool rides on it, and "where is they cited" has
   * one answer, this prompt.
   *
   * Drawn where this body owns the piece's cast — a node face. Inside the
   * Timeline window a card's editor is one shot of a piece whose cast is edited
   * one level up, in the same window, and a second editable copy of it there
   * would be two places to change one thing.
   *
   * Hidden until there is a cast or somebody asks for one, because most
   * generations have neither, and a node face is a preview with no room to
   * spend on a shelf nobody opened. The rail is what asks.
   */
  /**
   * Does this view draw the shelf as a row of the body?
   *
   * A node face does: it owns the piece's cast and has a rail tool to ask for
   * it. The simple card does not — casting is the @ menu, building is the
   * library, removing somebody is deleting their chip — and it says so by
   * setting `castResident` false on the body it borrows (fullscreen.js). Which
   * matters because the body it borrows is the node's own, `nodeId` and all:
   * asking `nodeId` alone answered "yes, resident" for a card that draws no
   * shelf at all, and everything that press-to-open does hung off that answer.
   */
  castResidentHere() { return this.castResident !== false && !!this.nodeId; }

  renderCastShelf() {
    // Where the shelf is not a row of the body it is only ever here because a
    // name was clicked — see `openCastMember` — so it comes with the summons
    // and goes with it. Not built at all otherwise: a shelf hidden by a
    // stylesheet is still a row of the column, and the column pays it a gap.
    if (!this.castResidentHere() && !this.castSummoned) {
      this.castHost.replaceChildren(); return;
    }
    const cast = this.castPiece.subjects ?? [];
    if (!cast.length && !this.castOpen) { this.castHost.replaceChildren(); return; }
    this.castShelf ??= new CastShelf({
      getCast: () => this.castPiece.subjects ?? [],
      setCast: (list) => { this.castPiece.subjects = list; },
      // This shot's attachments and the piece's pool together: both are files
      // this generation carries, and `subjects.check` runs against the two of
      // them merged. A keyframe is in the list rather than filtered out of it —
      // it is refused, and the shelf says why, which is more use than a picture
      // that is on the node and not in the menu.
      getAssets: () => [...(this.state.assets ?? []), ...(this.state.pool ?? [])],
      addAsset: () => this.attachOneAsset(),
      whereCited: (subject) => {
        const cited = S.citedCast({ ...this.state, cast: [subject] }).length > 0;
        return { cited, text: cited ? t("in the prompt") : "" };
      },
      cite: (subject) => this.citeName(subject.handle),
      // The roster, both ways. Kept against this shot's own files, and taken out
      // of the library through the piece's preset target — which is what knows
      // where a pool asset lands and what has to be redrawn once one has.
      keep: (subject, assets) => keepSubject(subject, assets),
      // Offered only where somebody could actually land: a cast belongs to a
      // piece, and this body is also what a PreStage's H3 branch draws, where
      // the roster would open on a tab whose every Apply is refused.
      library: this.presetTarget?.()?.scope === "piece"
        ? () => openPresetLibrary({ target: this.presetTarget(), scope: "cast" })
            .then(() => this.render())
        : null,
      // This shot's own attachments lose what the departing member alone was
      // built out of. The pool is left alone even though `getAssets` merges it
      // in: it belongs to the piece, and one card is not the place a file is
      // taken off every other card.
      dropAssets: (handles) => {
        const texts = [this.state.prompt, this.state.soundscape, this.state.music,
                       ...(this.castPiece === this.state ? [] : S.allTexts(this.castPiece))];
        this.state.assets = (this.state.assets ?? []).filter(
          (asset) => !handles.includes(asset.handle) || S.handleWritten(texts, asset.handle));
      },
      touch: () => this.onCommit?.(),
      commit: () => this.commit(),
      // Closing the card closes the shelf, but only when the shelf was put up
      // for that card. A face with a standing shelf keeps it — see
      // `openCastMember` for the other half.
      onShut: () => {
        if (!this.castSummoned) return;
        this.castSummoned = false;
        this.castOpen = false;
        this.render();
      },
    });
    // Mounted once. `replaceChildren` with the same node still detaches and
    // reattaches it, and a detached input loses the caret — which on a host that
    // redraws per keystroke is the whole bug over again, one level up.
    if (this.castHost.firstChild !== this.castShelf.root) {
      this.castHost.replaceChildren(this.castShelf.root);
    }
    // Summoned rather than resident, for the one view that has no Cast tool.
    // On the element, because what has to know is the stylesheet: a shelf that
    // is hidden there by default has to come back for exactly this.
    this.castShelf.root.classList.toggle("summoned", !!this.castSummoned);
    this.castShelf.render();
  }

  /**
   * Somebody's name in the sentence was clicked: show what they are made of, and
   * nothing else.
   *
   * The shelf is a permanent fixture on a node face, where there is a Cast tool
   * to put it there — and in the simple fullscreen view there is neither, because
   * casting is the @ menu's roster, building is the library's Cast tab and
   * removing somebody is deleting their chip (compile cuts the cast to the
   * subjects the text cites). What was missing was the one thing neither of
   * those covers: editing the copy of somebody that lives in *this* piece,
   * which is not the library's copy and cannot be reached by casting them again.
   *
   * So the shelf is summoned rather than resident. It arrives on the member you
   * asked about, with nobody else open, and their own chevron takes it away —
   * see the `onShut` hook above. Nothing is stored: `castSummoned` lasts as long
   * as the shelf is up.
   */
  openCastMember(handle) {
    // What was on screen before the press. Where the shelf is a row of the body
    // it is up whenever there is a cast or somebody opened it; where it is not,
    // a summons is the only thing that can have put it there.
    const already = this.castResidentHere()
      ? (this.castOpen || (this.castPiece.subjects ?? []).length > 0)
      : !!this.castSummoned;
    const summoned = this.castSummoned;
    const openBefore = this.castOpen;
    // Both raised *before* the render, not after it. On a body with no node the
    // shelf is drawn only for a summons, so a render that ran with the flag
    // still down built no shelf — and the `openMember` below would have been
    // asking `undefined` to open somebody.
    this.castOpen = true;
    this.castSummoned = summoned || !already;
    this.render();
    const what = this.castShelf?.openMember(handle);
    if (!what) {
      // A chip whose name nobody answers to — a subject deleted out from under
      // a sentence that still writes them. Leave the shelf exactly as it was.
      this.castOpen = openBefore;
      this.castSummoned = summoned;
      this.render();
      return;
    }
    // Pressing the name of the member already open shuts them, and a shelf that
    // was only here for that summons goes with them — the same way their own
    // chevron takes it away. A resident shelf stays; there was a cast on it
    // before the press and there is one after.
    if (what === "shut" && this.castSummoned && !this.castResidentHere()) {
      this.castSummoned = false;
      this.castOpen = false;
    }
    this.render();
  }

  /** Open the shelf and cast the first person, in one press of the rail. Once
   *  somebody is on it the shelf stays, so this only ever has to do the second
   *  half on the way in. */
  toggleCast() {
    const cast = this.castPiece.subjects ?? [];
    if (cast.length) {
      // Already open and populated: the rail's job here is to put the shelf
      // back if it was closed, and otherwise to add the next person.
      this.castOpen = true;
      this.render();
      this.castShelf?.addSubject();
      return;
    }
    this.castOpen = !this.castOpen;
    this.render();
    if (this.castOpen) this.castShelf?.addSubject();
  }

  /** One file, attached to this shot, for the cast shelf's "attach a file…".
   *  `addReferences` takes several and answers nothing; a subject is being given
   *  one thing, and the shelf needs to know which entry it was. */
  async attachOneAsset() {
    const blocked = S.blockedReason(this.state, "reference");
    if (blocked) { this.flash(blocked); return null; }
    const chosen = await openPicker({
      kinds: ["image", "video", "audio", "renders"],
      kind: "image",
      capacity: (k) => S.capacity(this.state, k),
    });
    if (!chosen?.length) return null;
    const before = new Set(this.state.assets.map((a) => a.handle));
    await this.attachAssets(chosen.slice(0, 1));
    return this.state.assets.find((a) => !before.has(a.handle)) ?? null;
  }

  /** Write a subject's name into the prompt. The answer to the commonest way to
   *  lose an afternoon with this feature: casting somebody and never citing them,
   *  which leaves them in no shot and nothing on screen to say so. */
  citeName(handle) {
    if (!handle) return;
    const current = this.state.prompt ?? "";
    if (new RegExp(`@${handle}\\b`).test(current)) return;
    const joiner = current && !/\s$/.test(current) ? " " : "";
    this.state.prompt = `${current}${joiner}@${handle} `;
    this.prompt.setValue(this.state.prompt);
    this.commit();
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
        // LoRAs sit on the checkpoint, not in the reference slots, so no
        // attach rule ever gates them.
        el("button", {
          class: "mmc-tool",
          title: t("Manage the LoRAs patched onto the routed checkpoint"),
          onclick: () => this.manageLoras(),
        }, [el("span", { class: "mmc-tool-icon" }, [icon("effect")]), el("span", { text: t("Add LoRA") })]),
        // Who is in it, as against what is attached to it. Ungated, and
        // deliberately: a subject can be a name and a description with no file
        // behind them at all, which is what a cast is in a text-only generation
        // — and gating this on having attached something is what made the
        // feature invisible to exactly the prompt that needed it most.
        ...(this.nodeId ? [el("button", {
          class: `mmc-tool mmc-tool-cast${(this.castPiece.subjects ?? []).length || this.castOpen ? " on" : ""}`,
          title: t("Who is in the video: a person, an object, a place or a look that "
                 + "comes back shot after shot. Name them once, write @anna in the "
                 + "prompt, and whatever is behind them rides in with them."),
          onclick: () => this.toggleCast(),
        }, [el("span", { class: "mmc-tool-icon" }, [icon("face")]), el("span", { text: t("Cast") })])] : []),
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
        // The way into the shell, with the machine's cluster rather than the
        // piece's: which window you look at a piece through outlives the
        // generation, exactly as the gallery and the settings page do. Absent
        // inside the shell, where "Back to the graph" is the same door from the
        // other side (styles/fullscreen.js hides it).
        ...(this.fullscreen ? [el("button", {
          class: "mmc-tool mmc-tool-expand",
          title: t("Draw this piece over the whole window. The node stays in the graph "
                 + "and is queued exactly as it is now; Escape brings you back."),
          onclick: () => this.fullscreen(),
        }, [el("span", { class: "mmc-tool-icon" }, [icon("expand")]),
            el("span", { text: t("Fullscreen") })])] : []),
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
    await openLoras({ state: this.state, family: S.pieceFamily(this.piece),
                      onChange: () => this.commit() });
    this.commit();
  }

  /** Try another file in this LoRA's slot — the grid opens as a one-shot
   *  picker and the pick lands where this entry stood. See `state.replaceLora`. */
  async swapLora(entry) {
    await openLoras({ state: this.state, family: S.pieceFamily(this.piece),
                      swapping: entry.name, onChange: () => this.commit() });
    this.commit();
  }

  renderLoras() {
    return loraBlock(this.state, {
      family: S.pieceFamily(this.piece),
      targets: S.checkpointsFor(this.state, S.pieceFamily(this.piece)),
      onToggle: (entry) => { S.toggleLora(this.state, entry.name); this.commit(); },
      onManage: () => this.manageLoras(),
      onSwap: (entry) => this.swapLora(entry),
      onRemove: (entry) => { S.removeLora(this.state, entry.name); this.commit(); },
    });
  }

  renderAssets() {
    // Whose files these are. Casting somebody attaches their pictures — the
    // roster does it, `presets.addSubjectToPiece` does it — so some of this row
    // is there because a name in the sentence put it there rather than because
    // you picked it. Marked, not filtered: the simple view used to leave them
    // out on the grounds that the @name says it already, and a row drawing only
    // some of what is attached is a row you cannot trust to be the answer —
    // which matters now that a file can be sitting there muted.
    const cast = new Set();
    for (const subject of this.castPiece.subjects ?? []) {
      for (const handle of S.subjectFiles(subject)) cast.add(handle);
      for (const handle of S.replacesOf(subject)) cast.add(handle);
    }
    const chip = (asset) => {
      const thumb = asset.kind === "image"
        ? el("img", { class: "mmc-asset-thumb", src: viewUrl(asset.filename, { preview: true }), alt: asset.filename })
        : el("span", { class: "mmc-asset-thumb" }, [svg(ICONS[asset.kind], 15)]);
      swappable(thumb, {
        title: t("Swap the file behind @{handle} — the handle stays, so the prompt still fits.",
                 { handle: asset.handle }),
        onclick: () => this.replaceAsset(asset),
      });

      // The name is the door. It used to be dead text with four narrowing
      // buttons beside it, three of which the simple view hid while they held
      // their default — which is exactly when you need them, because the
      // default is the answer you are trying to change. One gesture instead,
      // the same one a cast member's name already answers to: click the name,
      // get the card. See `openReferenceSheet`.
      const handle = el("button", {
        class: "mmc-asset-handle mmc-asset-door",
        title: t("Open @{handle} — what it is a reference to, and everything else about it",
                 { handle: asset.handle }),
        text: `@${asset.handle}`,
        onclick: (event) => this.openReferenceSheet(event.currentTarget, asset),
      });

      const parts = [thumb, handle];

      if (asset.role !== "reference") {
        parts.push(el("span", { class: "mmc-asset-role", text: asset.role === "first_frame" ? t("start") : t("end") }));
      }
      // What somebody set, and nothing else — read, not pressed. A file left
      // ordinary says nothing at all, and the row stays as short as the files
      // in it are plain; a clip trimmed to eight seconds still says so, on the
      // face and in both fullscreen views alike.
      const said = referenceSummary(asset);
      if (said) parts.push(el("span", { class: "mmc-asset-said", text: said }));

      // The mute, on references only: a keyframe is where the shot opens or
      // closes rather than something the prompt reaches for, so there is
      // nothing for it to be out of. The same switch a LoRA carries and the
      // same word for it — out of the run, kept exactly as you attached it —
      // because it is the same question asked about a different file.
      //
      // Not the name, which is how a LoRA spells this: a reference's name is
      // already the door onto its card. So it is a glyph beside the ✕, in the
      // row where the other thing you can do to a whole file lives.
      if (asset.role === "reference") parts.push(this.muteButton(asset));
      parts.push(el("button", {
        class: "mmc-asset-x", text: "✕", title: t("Remove @{handle}", { handle: asset.handle }),
        onclick: () => this.remove(asset.handle),
      }));
      return el("div", {
        class: `mmc-asset mmc-tag-${S.tagIndex(asset.handle)}${
          cast.has(asset.handle) ? " mmc-asset-cast" : ""}${S.muted(asset) ? " off" : ""}`,
        title: asset.filename,
      }, parts);
    };

    // Bounded on the face (see the stylesheet), so it needs the wheel the way
    // the prompt box does — otherwise the row that scrolls zooms the canvas.
    return keepScroll(el("div", { class: "mmc-assets" }, this.state.assets.map(chip)));
  }

  /** Take one reference out of the run, or bring it back. Everything about it
   *  survives — the file, the handle, the narrowing, the trim — because that is
   *  the whole difference between this and the ✕ beside it. */
  muteButton(asset) {
    const off = S.muted(asset);
    return el("button", {
      class: `mmc-asset-x mmc-asset-mute${off ? " on" : ""}`,
      "aria-pressed": off ? "true" : "false",
      title: off
        ? t("@{handle} is muted — out of the run, and kept exactly as you attached it. Click to bring it back.",
            { handle: asset.handle })
        : t("Mute @{handle}: out of the run, but the file, the handle and the narrowing all stay.",
            { handle: asset.handle }),
      onclick: () => {
        if (off) delete asset.enabled;
        else asset.enabled = false;
        // A muted reference is not a reference of this render, so bringing one
        // back can overrun a limit that was legal while it was off — the same
        // check a track change answers to, and the same rollback.
        const problem = off ? S.overflow(this.state) : null;
        if (problem) {
          asset.enabled = false;
          return this.flash(t("@{handle} stays muted — {problem}",
                              { handle: asset.handle, problem }));
        }
        this.commit();
      },
    }, [svg(ICONS.mute, 13)]);
  }

  /**
   * What this card does with a reference's length, as one sentence — or null
   * while the length is not known.
   *
   * The fact worth stating is not the number, it is the difference: `load_all`
   * cuts every reference video down to the card's own frame count, so half of a
   * long clip can be missing with nothing on screen saying so. Audio is not cut,
   * which is the opposite surprise and needs saying just as much. Said for every
   * clip, whatever it is taken for, because the cut happens either way — the
   * offer to *fix* it is the pill's, and that one is take-gated.
   */
  lengthNote(asset) {
    const seconds = S.refSeconds(asset, (filename) => this.lengthOf(filename));
    if (seconds === null) return null;
    const rules = rulesFor(S.pieceFamily(this.piece));
    const card = secondsForFrames(framesForSeconds(this.state.duration_s, rules), rules);
    const length = seconds.toFixed(2);
    if (Math.abs(seconds - card) <= 1 / rules.fps) {
      return t("{length} s — the same length as this card.", { length });
    }
    if (seconds < card) {
      return t("{length} s, against a card of {card} s.", { length, card: card.toFixed(2) });
    }
    return S.scopeKind(asset) === "audio"
      ? t("{length} s, against a card of {card} s. Audio is sent whole — the shot ends "
        + "before the sound does.", { length, card: card.toFixed(2) })
      : t("{length} s, against a card of {card} s. Only the first {card} s is encoded; "
        + "the rest of the clip is never read.", { length, card: card.toFixed(2) });
  }

  /**
   * The duration pill's tail: how long the reference runs, and one click to
   * land the card on it.
   *
   * On the pill rather than on the reference chip, because it is the card's
   * length that moves — this is the one control that sets it, and an offer to
   * set it belongs beside the number it would change. Every clip can be matched
   * to, a cast member's voice and the clip they stand in for included; where a
   * card carries several, the one offered is the one its length leads — see
   * `S.lengthMatch`. Empty for a card of stills, which is most of them.
   */
  matchTail() {
    // Nothing to offer while the model is choosing the length: "matches
    // @vid-1" would be a claim about a frame count that does not exist yet,
    // and the offer to set one is an offer to do what auto is already doing.
    // Turning auto off brings both back.
    if (this.state.auto_duration) return [];
    const match = S.lengthMatch(this.state, (filename) => this.lengthOf(filename),
                                this.piece);
    if (!match) return [];
    const handle = match.asset.handle;
    const length = match.seconds.toFixed(2);
    if (match.matched) {
      return [el("span", {
        class: "mmc-dur-match on",
        text: t("matches @{handle}", { handle }),
        title: t("@{handle} runs {length} s and this card lands on the same frame count.",
                 { handle, length }),
      })];
    }
    return [el("button", {
      class: "mmc-dur-match",
      title: t("@{handle} runs {length} s. Set this card to {target} s, which is the nearest "
             + "length the model can make — frame counts come {step} apart, so a whole second is "
             + "often not the closest one.",
               { handle, length, target: match.duration.toFixed(2),
                 step: rulesFor(S.pieceFamily(this.piece)).frameStep }),
      onclick: () => {
        this.state.duration_s = match.duration;
        this.commit();
      },
    }, [
      el("span", { text: t("match @{handle}", { handle }) }),
      el("span", { class: "mmc-pill-sub", text: t("{seconds} s", { seconds: length }) }),
    ])];
  }

  renderPills(geometry, currentMode) {
    const state = this.state;
    const refs = S.hasReferences(state);
    const frameLabel = (role, fallback) => {
      const asset = S.frameAsset(state, role);
      return asset ? `@${asset.handle}` : t(fallback);
    };

    const framePill = (role, label, iconName) => (seg) => {
      const blocked = S.blockedReason(state, role);
      return el("button", {
        class: pillClass(seg),
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
    const rules = rulesFor(S.pieceFamily(this.piece));
    const trained = isTrainedLength(geometry.frames, rules);
    // A card matched to a reference carries a fractional length, so a step from
    // one lands on the whole second either side of it rather than 0.42 away
    // from where it started. From a whole second both are the plain step.
    const stepTo = (delta) => {
      const from = Number(state.duration_s) || 0;
      const step = delta < 0 ? (from > 15 ? 5 : 1) : grain;
      return delta < 0 ? Math.max(rules.minSeconds, Math.ceil(from) - step)
                       : Math.min(rules.maxSeconds, Math.floor(from) + step);
    };
    // Whether this family can be asked how long the shot wants to be. A
    // capability, not an id: H3 has no such weights, and a later family might.
    const predicts = S.canDo(this.piece, "duration");
    const auto = predicts && state.auto_duration === true;
    const setAuto = (on) => { state.auto_duration = on; this.commit(); };
    const duration = el("div", {
      class: `mmc-pill mmc-pill-group${trained || auto ? "" : " off-distribution"}`,
      title: (auto
        // Deliberately not a frame count: on auto there isn't one yet. The
        // number the pill shows is what the strip's bar counts with and what
        // the card falls back to, and saying so is the whole honesty of it.
        ? t("The model picks this shot's length when it renders, from the prompt "
          + "itself. {seconds} s is the estimate everything before the render "
          + "counts with — the bar, the queue guard — and the length this card "
          + "goes back to if you turn auto off.",
            { seconds: S.showSeconds(state.duration_s) })
        : t("{frames} frames · {seconds} s at {fps} fps",
            { frames: geometry.frames, seconds: geometry.seconds.toFixed(2),
              fps: rules.fps }))
           + (trained || auto ? "" : "\n" + t("Outside the ~5–15 s the open weights were trained on. It will "
                           + "generate, but coherence and motion are on their own past here — "
                           + "and cost rises with the square of the length.")),
    }, [
      el("button", {
        class: "mmc-step", text: "−",
        disabled: auto || state.duration_s <= rules.minSeconds || undefined,
        onclick: () => {
          state.duration_s = stepTo(-1);
          this.commit();
        },
      }),
      icon("clock", 16),
      // Room for "9.42 s" as well as "6 s": a matched card carries two decimals,
      // and at the old width they sat against the clock. On auto the same slot
      // holds the estimate with a "~" in front of it, because the number is
      // still the one everything else in the UI is counting with.
      el("span", { text: auto
                     ? t("~{seconds} s", { seconds: S.showSeconds(state.duration_s) })
                     : t("{seconds} s", { seconds: S.showSeconds(state.duration_s) }),
                   style: { minWidth: "38px", padding: "0 5px", textAlign: "center",
                            ...(auto ? { opacity: "0.6" } : {}) } }),
      el("button", {
        class: "mmc-step", text: "+",
        disabled: auto || state.duration_s >= rules.maxSeconds || undefined,
        onclick: () => {
          state.duration_s = stepTo(1);
          this.commit();
        },
      }),
      // The switch, only on a family that has the weights to answer. It is the
      // last thing in the group rather than a pill of its own because it is
      // the same question the steppers ask — how long is this shot — answered
      // by somebody else. A word behind a hairline, which is the shape this
      // group already uses for one: `matchTail` sits in the same slot and says
      // its piece the same way. Not a `.mmc-step` — that is a 26px box sized
      // for one glyph, and "auto" spilled straight out of it.
      ...(predicts ? [el("button", {
        class: `mmc-dur-auto${auto ? " on" : ""}`,
        text: t("auto"),
        title: auto
          ? t("The duration head is picking this shot's length. Click to set it yourself.")
          : t("Let the model pick this shot's length from its prompt, between "
            + "{min} and {max} s — the range its duration head was trained on. "
            + "Needs the duration head picked under 'weights'.",
              { min: Math.round(S.familyOf(this.piece).capabilities.duration.min_seconds),
                max: Math.round(S.familyOf(this.piece).capabilities.duration.max_seconds) }),
        onclick: () => setAuto(!auto),
      })] : []),
      ...this.matchTail(),
    ]);

    // Live even when a picture decides the ratio: the list is where the source
    // itself is chosen now — any attached picture, or the preset over them.
    const sourceAsset = S.aspectSourceAsset(state);
    const chosen = (state.aspect_source ?? "auto") !== "auto";
    const aspectPill = (seg) => el("button", {
      class: pillClass(seg),
      title: geometry.fromImage
        ? t("The aspect ratio comes from this picture — the resolution slider still sets the scale. Click to take it from another input, or force a preset.")
        : t("Aspect Ratio"),
      onclick: (event) => this.openAspect(event.currentTarget),
    }, geometry.fromImage
      // The ratio the picture brought with it, which is the one case where the
      // pill is showing a shape no entry in the list would have drawn.
      ? [aspectGlyph(geometry.ratio, PILL_GLYPH),
         el("span", { text: describeRatio(geometry.ratio, rules) }),
         el("span", { class: "mmc-pill-sub",
                      text: chosen ? `@${sourceAsset.handle}` : t("from image") })]
      : [aspectGlyph(geometry.ratio, PILL_GLYPH), el("span", { text: state.aspect })]);

    // The sub says the whole answer in one glance: what was sampled, and what
    // comes out of it. Written in `pills.js` because the two hosts that draw
    // this pill were answering the same three-way question separately.
    const res = resolutionPillText(state, geometry);
    const resPill = (seg) => el("button", {
      class: pillClass(seg),
      title: res.title,
      onclick: (event) => this.openResolution(event.currentTarget),
    }, [
      icon("res", 16),
      el("span", { text: `${state.short_edge}p` }),
      el("span", { class: "mmc-pill-sub", text: res.sub }),
    ]);

    return el("div", { class: "mmc-pills" }, [
      // The model leads, because it is the one thing here that changes what
      // everything after it means — the route the badge at the end names, the
      // step the seconds round to, the sizes the canvas offers. Node bodies
      // only, like the weights and the sampler row: the family belongs to the
      // piece, so a card of a strip would be drawing its neighbour's answer,
      // and the prompt window deliberately leaves the node's own settings on
      // the node. See `familyPill`.
      ...(this.modelPill?.() ?? (this.nodeId
        ? [familyPill({ piece: this.piece, onChange: () => this.commit() })] : [])),
      ...(this.continuePill ? [this.renderContinue()] : []),
      // The two ends of the shot in one pill: they are one question asked twice,
      // and either of them can be a file, a handle or nothing at all.
      pillSet([framePill("first_frame", "Start frame", "frameIn"),
               framePill("last_frame", "End frame", "frameOut")]),
      // A body that is not making a video says how long it runs in its own
      // terms, or not at all — see `extraPills`.
      ...(this.durationPill ? [duration] : []),
      ...(this.extraPills?.() ?? []),
      // In a timeline the canvas belongs to the timeline, not to one shot: the
      // segments are concatenated at the end and have to come out the same size.
      // The output folder is the timeline's for the same reason — one file.
      //
      // Shape and scale share a pill because they are one canvas: the ratio
      // decides what the short edge is the short edge *of*, and the size on the
      // second half is the product of the two.
      ...(this.canvasPills ? [pillSet([aspectPill, resPill])] : []),
      // The end of the row, and one flex item rather than three. Everything
      // above says what the shot *is*; these say where it runs and what it
      // belongs to, and the auto margin that holds them against the far end of
      // the row lives on this wrapper now rather than on the badge inside it.
      //
      // Two reasons, and the second is why it is a wrapper and not a margin
      // moved. A row that fits is unchanged: the group is pushed right, in the
      // order it always read in. A row that wraps — which is every row in the
      // fullscreen card, where the width is a measure and not the node's — used
      // to break wherever it ran out, stranding a lone Timeline pill on a line
      // of its own. Grouped, the tail wraps whole or not at all.
      el("div", { class: "mmc-pills-tail" }, [
        this.renderRouting(currentMode),
        ...(this.growShot ? [this.renderGrowPill()] : []),
        ...(this.pieceView ? [this.renderPieceViewPill()] : []),
        ...(this.preStage ? [this.renderPreStagePill()] : []),
      ]),
    ]);
  }

  /**
   * The next shot, from the face.
   *
   * A second shot is part of what is being asked for, so the control for it
   * belongs with the writing rather than with the machine — and this is the one
   * row of the panel that is about the *piece* and not about this shot: the
   * route it runs on, the piece behind it, the node feeding it. The pill sits
   * with them because it is one of them.
   *
   * It used to be a dashed rule across the whole body, which is a horizon line
   * spent on one quiet button, and the fullscreen shell hid it for exactly that
   * reason. A pill in a row of pills is the same act at its own size, and it is
   * the same act on both faces.
   */
  renderGrowPill() {
    const full = this.growShot.full();
    return el("button", {
      class: "mmc-pill mmc-grow-shot",
      disabled: full,
      title: full
        ? this.growShot.fullTitle()
        : t("Add a shot after this one and open it. One shot or twenty, it is "
          + "the same node."),
      onclick: () => this.growShot.add(),
    }, [el("span", { class: "mmc-grow-mark", text: "+" }),
        el("span", { text: t("Add shot") })]);
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
   * standing statement of the two — a per-generation pin speaks for one
   * generation. Either direction is honoured: the slots name inputs, not
   * trainings, and merges of the two checkpoints exist. `routeOf` is null in a
   * timeline segment editor, where the route belongs to the timeline and this
   * is a readout.
   */
  renderRouting(currentMode) {
    const state = this.state;
    const family = S.pieceFamily(this.piece);

    // A family with one transformer has no arrow to draw and nothing to cycle:
    // the mode still says what this generation is — text-only, a keyframe, a
    // reference — but there is no second set of weights for it to point at, and
    // an arrow to the only checkpoint there is would be describing a choice
    // nobody has.
    if (!S.routing(family)) {
      // And with no checkpoint to name, the badge says the shape in words
      // rather than in the family's codename for it — see `MODE_SHAPE_LABEL`.
      // The codename stays in the tooltip, where somebody reading Lightricks'
      // own docs will find it.
      const shape = S.MODE_SHAPE_LABEL[S.modeShape(this.piece, currentMode)];
      return el("span", {
        class: "mmc-mode",
        title: shape
          ? t("What this generation is. {family} calls it {mode}.",
              { family: S.FAMILY_LABEL[S.pieceFamily(this.piece)], mode: currentMode })
          : t("What this generation is."),
      }, [el("b", { text: shape ? t(shape) : currentMode })]);
    }

    const label = S.checkpointLabels(family);
    const route = this.routeOf?.() ?? "auto";
    const forced = route !== "auto";
    const routed = forced ? route : S.checkpoint(state, family);
    const pinned = !forced && S.checkpointPinned(state, family);
    const canCycle = !!this.setRoute;

    const badge = el(canCycle ? "button" : "span", {
      class: `mmc-mode${forced || pinned ? " pinned" : ""}`,
      title: forced
        ? t("Every generation on this node runs on {label}, whatever the mode derives. Click to change it.",
            { label: label[route] })
        : canCycle
          ? t("Following the mode. Click to run everything on one checkpoint instead — "
            + "Ref2VA takes the text-only and keyframe payloads too.")
          : t("Following the timeline's route."),
      onclick: canCycle ? () => this.setRoute(S.nextRoute(route, family)) : undefined,
    });
    badge.appendChild(el("b", { text: currentMode }));
    badge.appendChild(document.createTextNode(` → ${label[routed]}`));
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
    // The canvas pill only renders on the face of a piece of one shot, so this
    // shot is card 1 and the piece form of every source says so. The mirrored
    // per-segment form (`syncCanvas`) is what `aspectSourceAsset` reads back.
    const ratioOf = (asset) => {
      const size = this.sizes.get(asset.filename);
      return size?.width ? size.width / size.height : null;
    };
    const roleOf = (asset) =>
      asset.role === "first_frame" ? t("start frame")
        : asset.role === "last_frame" ? t("end frame")
        : asset.kind === "video" ? t("reference video") : t("reference image");
    const donors = S.aspectDonors(this.state).map((asset) => ({
      value: { card: 1, handle: asset.handle },
      label: `@${asset.handle}`,
      tag: S.tagIndex(asset.handle),
      ratio: ratioOf(asset),
      sub: roleOf(asset),
    }));
    const anchorAsset = S.frameAsset(this.state, "first_frame")
      || S.frameAsset(this.state, "last_frame");
    openAspectPopover(anchor, this.piece, () => this.commit(), donors.length ? {
      donors,
      auto: anchorAsset
        ? { ratio: ratioOf(anchorAsset), sub: `@${anchorAsset.handle}` }
        : { ratio: S.resolved(this.state, null, this.piece).ratio, sub: this.state.aspect },
    } : null);
  }

  openResolution(anchor) {
    openResolutionPopover(anchor, this.piece, () => {
      const asset = S.aspectSourceAsset(this.state);
      return S.resolved(this.state, asset ? this.sizes.get(asset.filename) : null, this.piece);
    }, () => this.commit());
  }
}
