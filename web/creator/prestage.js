// The PreStage node: stills for the pipeline, made on the left.
//
// Two classes. `PreStageEditor` is the body for the *image* architectures —
// Krea 2, Ideogram 4 and Qwen Image Edit — same skeleton as CreatorEditor
// (rail, chips, panel, pills, sampler row) because it is driven the same way,
// and the same prompt box for the same reason.
//
// It was a plain textarea, on the reasoning that an image prompt references
// nothing by handle — that the Qwen-edit encoder labels the style references
// itself, so a mention menu would be empty. The first half is true and it is
// exactly why the second half is not: the encoder writes `Picture 1:` in front
// of each image, so `Picture N` is a name the prompt can use, and the ordinal
// is the payload's to decide rather than the user's to count. The chips said as
// much all along — they have worn `@ref-1` since they existed — and there was
// no way to write what they were offering.
//
// `PreStageBody` below owns the node, and on the third architecture it mounts
// `CreatorEditor` instead — MiniMax H3's still is a video generation with one
// latent frame decoded, so the body that drives a shot drives it too, on a
// request in the same shape. Its docstring says what that buys.
//
// The model pill is the one control the video nodes do not have, and it belongs
// to the body rather than to either editor: it is the control that swaps them.
// The architectures want different sampler rows — Krea RAW runs 52 steps at cfg
// 3.5, Qwen Image Edit 20 at cfg 4, Ideogram its preset's steps at cfg 7 on its
// own schedule — so switching the arch rewrites the row from the arriving
// family's own widget defaults, and the turbo pill means a different thing on
// each (a checkpoint on Krea, a distillation LoRA on the other two).

import { el, icon, ICONS, svg, dismissable, keepScroll, placeNear, swappable } from "./dom.js";
import { DEFAULT_STILL_ARCH, stillFamily } from "./manifest.js";
import { openPicker } from "./picker.js";
import { openLoras, loraBlock, loraBase } from "./loras.js";
import { openFrameGrab } from "./framegrab.js";
import { openContactSheet } from "./contact.js";
import { openChoicePopover, stepperPill, aspectGlyph, edgeSlider, PILL_GLYPH } from "./pills.js";
import { revealPreStage } from "./fullscreen.js";
import { CreatorEditor } from "./editor.js";
import { openPresetLibrary } from "./presetlib.js";
import * as P from "./presets.js";
import { PromptBox, focusEnd, openEditorSheet } from "./prompt.js";
import { blobIO, samplingBar } from "./sampling.js";
import { loadLoraNames, loraNames } from "./turbo.js";
import { Stage } from "./stage.js";
import { loadCatalog, refreshCatalog, catalogByFolder } from "./models.js";
import { viewUrl } from "./api.js";
import { t } from "./i18n.js";
import * as S from "./state.js";

const QUALITY_TITLE = {
  quality: "48 steps on the tight schedule — the hosted service's 'Quality' tier.",
  default: "20 steps — the hosted service's default tier.",
  turbo: "12 steps on the shifted schedule — the hosted service's 'Turbo' tier.",
};

// Keyed by arch, because the same three words mean different step counts on
// each side — Krea's ladder is the distilled checkpoint's, Ideogram's is what a
// distillation LoRA over an undistilled checkpoint will hold up at.
const TURBO_TITLE = {
  krea2: {
    draft: "4 steps — the fast look. Softer detail.",
    medium: "6 steps — quick and usable.",
    good: "8 steps — what the Turbo checkpoint was distilled for.",
  },
  ideogram4: {
    draft: "2 steps — as short as the distillation goes. For framing, not for finals.",
    medium: "4 steps — quick and usable.",
    good: "8 steps — where a distilled Ideogram stops gaining.",
  },
  qwenedit: {
    draft: "4 steps — what the 4-step Lightning LoRA was distilled for.",
    medium: "6 steps — a little more than the short LoRA's own number.",
    good: "8 steps — what the 8-step Lightning LoRA was distilled for.",
  },
  flux2klein: {
    draft: "2 steps — below the distillation's own number. For framing, not for finals.",
    medium: "4 steps — what the Klein distillation was trained for.",
    good: "6 steps — a little headroom over the distillation's own number.",
  },
};

/** The distilled-checkpoint answer in the turbo source picker: not a file, and
 *  only offered by an arch that ships one. */
const TURBO_CHECKPOINT = "— distilled checkpoint —";

/** A filename as the pill wears it: no folder, no extension. Forty characters
 *  of `..._turbo_v4_step600_ema_pruned` is not a label. */
const shortLora = (name) => name.split("/").pop().replace(/\.[^.]+$/, "");

export class PreStageEditor {
  /**
   * @param {object} options
   * @param {object} options.state    a parsePreStage state, mutated in place
   * @param {() => void} options.onCommit
   * @param {object} options.samplingWidgets  the node's hidden sampler widgets
   * @param {() => void} options.onWidgetChange
   * @param {() => string|number} options.nodeId
   */
  constructor({ state, onCommit, samplingWidgets, onWidgetChange, nodeId,
                stage = null, archPill = null, presetTarget = null }) {
    // Supplied by `PreStageBody` for the same reason the arch pill is: a preset
    // can change the architecture, and remounting the body is not something the
    // body being remounted can do.
    this.presetTarget = presetTarget;
    this.state = state;
    this.onCommit = onCommit;
    this.samplingWidgets = samplingWidgets;
    this.onWidgetChange = onWidgetChange;
    this.nodeId = nodeId;
    // Both supplied by `PreStageBody`, which outlives this editor: it rebuilds
    // the body when the architecture changes, and the stage was floated beside
    // the node once. The arch pill is the control that does the rebuilding, so
    // it cannot belong to the thing being rebuilt.
    this.stage = stage;
    this.archPill = archPill;
    this.sizes = new Map();   // filename -> {width,height}, for the adaptive canvas readout

    // The Creator's box, over this state. `assets` is what it reads its chips
    // and its menu from, and here that is the style references — the same
    // `{handle, filename}` rows under a name this state does not use, so it is
    // handed a view rather than being made to carry a second list.
    this.prompt = new PromptBox({
      getState: () => ({ ...this.state, assets: this.state.refs ?? [] }),
      onInput: (text) => {
        this.state.prompt = text;
        this.onCommit?.();
      },
      onAttach: (row) => this.attachFromMention(row),
      attachBlocked: () => this.refBlocked(),
      onOverflow: (over) => this.onPromptOverflow(over),
      // The `/` menu's doors. No cast branch here and none offered — an image
      // node has no piece to cast anybody into, which `commandOptions` reads off
      // the missing `castFromLibrary` above. A style is another matter: the
      // atlas applies to a pre-stage, and this is where its look is set.
      openLibrary: this.presetTarget
        ? (scope) => openPresetLibrary({ target: this.presetTarget(), scope })
            .then(() => this.render())
        : null,
      onBrowse: () => this.addRefs(false),
    });
    this.prompt.root.dataset.placeholder = this.placeholder();
    // Leaving the box arms the escalation again: the waiver is about the
    // sentence being written, not about the text. See
    // `CreatorEditor.onPromptOverflow`.
    this.prompt.root.addEventListener("blur", () => { this.overflowWaived = false; });
    // What the rest of this class still calls it. The box is the editable; the
    // frame is what gets mounted, because the box brings its own disclosure.
    this.promptBox = this.prompt.root;

    this.railHost = el("div");
    this.assetsHost = el("div");
    this.loraHost = el("div");
    this.pillsHost = el("div");
    this.noticeHost = el("div");
    // Classed, because the fullscreen shell folds the sampler away in its simple
    // view by this name — see styles/fullscreen.js. The Creator body carries the
    // same class for the same reason.
    this.samplingHost = el("div", { class: "mmc-sampling-host" });

    // The box is typed into here, on the face, and the window takes over only
    // once the text outgrows it. `onFace` tells the face from the window: the
    // same body is inside that window, and there nothing escalates.
    this.onFace = !!nodeId;
    this.expandHost = el("div", { class: "mmc-panel-corner" });
    this.root = el("div", { class: "mmc-root mmc-prestage" }, [
      this.railHost,
      this.assetsHost,
      this.loraHost,
      this.panel = el("div", { class: "mmc-panel" }, [
        ...(this.onFace ? [this.expandHost] : []),
        this.prompt.frame, this.pillsHost,
      ]),
      this.noticeHost,
      this.samplingHost,
    ]);

    // The whole panel is the writing area — see `PromptBox.claim`.
    this.prompt.claim(this.panel);

    loadCatalog(() => this.adoptWeights());
    this.prompt.setValue(this.state.prompt ?? "");
    this.render();
    this.probeInit();
  }

  destroy() {
    // The stage is the body's — see the constructor.
  }

  adoptWeights() {
    if (S.guessPreStageModels(this.state.models, catalogByFolder())) this.commit();
    else this.render();
  }

  /** The sampler row's `{value, set}` pair, over the pre-stage's own blob.
   *
   *  Same move as the piece's — see `sampling.blobIO`. This node is the one that
   *  wanted it most: its three architectures want three different rows and there
   *  is one static widget schema underneath them, wearing Krea's numbers. */
  widgetIO() {
    return blobIO(
      () => this.samplingWidgets,
      () => this.state.sampling,
      (block) => { this.state.sampling = block; this.onCommit?.(); },
      () => this.onWidgetChange?.());
  }

  commit() {
    // Before anything is drawn or written out: the adapter that reads the
    // references and the Qwen edition are both fields the blob has to carry,
    // and both have exactly one thing that can be guessed at. See
    // `S.syncPreStageGuesses` for what is and is not guessed.
    S.syncPreStageGuesses(this.state);
    this.onCommit?.();
    this.render();
    // Cheap after the first time — `probeInit` returns at once for a picture
    // already measured — and here rather than only behind the init picker
    // because on an edit family attaching a *reference* moves the canvas too.
    this.probeInit();
  }

  setState(state) {
    this.state = state;
    this.sizes.clear();
    this.prompt.setValue(this.state.prompt ?? "");
    this.render();
    this.probeInit();
  }

  /** Why another style reference cannot be attached, or null. The menu asks
   *  before it offers the input folder, and `attachFromMention` asks again
   *  before it takes one. */
  refBlocked() {
    if (!S.PRESTAGE_REFS[this.state.arch]?.reads) {
      return t("{arch} has no local reference conditioning — switch the model pill to "
             + "one that reads pictures.", { arch: S.PRESTAGE_ARCH_LABEL[this.state.arch] });
    }
    const max = S.preStageMaxRefs(this.state);
    if ((this.state.refs?.length ?? 0) >= max) {
      // Two different caps wearing one number. The encoder has three image
      // slots on every family; what a checkpoint was post-trained to *read* is
      // its own answer, and the first Qwen-Image-Edit weights read one picture.
      return max === 1
        ? t("The {edition} weights were post-trained on a single picture. Move the "
          + "edition pill to 2509 or 2511 for three.", { edition: this.state.edition })
        : t("At most {max} {noun} — the Qwen edit encoder the model reads them "
          + "through has exactly three image slots.",
          { max, noun: t(refs.noun?.[1] ?? "style references") });
    }
    return null;
  }

  /** A file picked from the @ menu, attached as a style reference. Returns its
   *  handle so the box can write the chip, or null when it was refused — the
   *  same contract the Creator's box has. */
  attachFromMention(row) {
    if (this.refBlocked()) return null;
    // Images only. The encoder's three slots are pictures, and a clip has to be
    // grabbed to a frame first — which the rail's own tool does.
    if (row.kind && row.kind !== "image") return null;
    const handle = S.nextPreStageHandle(this.state);
    this.state.refs.push({ handle, filename: row.path });
    this.commit();
    return handle;
  }

  // ---- init image and style references --------------------------------------

  /** Pick the init image — the still this render restyles rather than starts
   *  from nothing. From the picker, or grabbed off a video's playhead. */
  async setInit(fromVideo = false) {
    let path = null;
    if (fromVideo) {
      const clip = await openPicker({
        kinds: ["video", "renders"], kind: "video", single: true,
        capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
      });
      if (!clip) return;
      const grabbed = await openFrameGrab({ path: clip[0].path });
      if (!grabbed) return;
      path = grabbed.path;
    } else {
      const chosen = await openPicker({
        kinds: ["image", "renders"], kind: "image", single: true,
        capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
      });
      if (!chosen) return;
      path = chosen[0].path;
    }
    this.state.init = { filename: path, denoise: this.state.init?.denoise ?? S.PRESTAGE_DEFAULT_DENOISE };
    this.commit();
    this.probeInit();
  }

  /**
   * The contact-sheet tool, over a clip or over a sheet.
   *
   * Which half opens is decided by the file, not by a switch here — see
   * `contact.js`. What comes back is either one sheet or the frames cut out of
   * one, and only the first has anywhere to go: a sheet is the picture this
   * render is about, so it takes the first reference slot on a family that
   * reads references and the init slot on one that does not. Cut frames are
   * left in the input folder, which is where a start frame is picked from.
   */
  async contactSheet() {
    const chosen = await openPicker({
      kinds: ["video", "image", "renders"], kind: "video", single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    if (!chosen) return;
    const source = chosen[0];
    const result = await openContactSheet({
      path: source.path, video: source.kind === "video",
    });
    if (!result?.paths?.length) return;
    if (result.paths.length > 1) {
      return this.flash(t("{count} frames cut into the input folder — attach them from "
                        + "the picker, or send one to a shot as its start frame.",
                        { count: result.paths.length }));
    }
    const [sheet] = result.paths;
    if (!this.refBlocked()) {
      this.state.refs.unshift({ handle: S.nextPreStageHandle(this.state), filename: sheet });
    } else {
      this.state.init = { filename: sheet, denoise: this.state.init?.denoise ?? S.PRESTAGE_DEFAULT_DENOISE };
    }
    this.commit();
  }

  async addRefs(fromVideo = false) {
    // The same two refusals the `@` menu asks for, said out loud here because
    // this door was pressed rather than typed into.
    const blocked = this.refBlocked();
    if (blocked) return this.flash(blocked);
    const room = S.PRESTAGE_MAX_REFS - this.state.refs.length;
    if (fromVideo) {
      const clip = await openPicker({
        kinds: ["video", "renders"], kind: "video", single: true,
        capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
      });
      if (!clip) return;
      const grabbed = await openFrameGrab({ path: clip[0].path });
      if (!grabbed) return;
      this.state.refs.push({ handle: S.nextPreStageHandle(this.state), filename: grabbed.path });
      return this.commit();
    }
    const chosen = await openPicker({
      kinds: ["image", "renders"], kind: "image",
      capacity: () => ({ used: this.state.refs.length, max: S.PRESTAGE_MAX_REFS, filesLeft: room }),
    });
    if (!chosen) return;
    for (const asset of chosen.slice(0, room)) {
      this.state.refs.push({ handle: S.nextPreStageHandle(this.state), filename: asset.path });
    }
    this.commit();
  }

  /**
   * A guide off the ControlNet bench, taken as the picture this still is built on.
   *
   * The init image rather than a style reference, and the difference is what the
   * two slots mean: a reference is *what this should look like*, and an edge map
   * or a depth pass is not a look — it is where things are. The init slot is the
   * one that says "start from this arrangement", which is the whole reason
   * somebody traced a frame.
   *
   * The denoise it lands with is whatever the pre-stage already had, so a still
   * that has been dialled in does not have its strength reset by a new guide.
   */
  takeGuide({ path, opId = null }) {
    // Where a guide goes is what the weights in front of it can read.
    //
    // On 2509 and 2511 the ControlNet is built in: a depth pass, an edge map or
    // a pose skeleton arriving in an ordinary image slot is followed, and there
    // is no node to load and no strength to set. So the guide is a *picture*,
    // and the render is aimed at it. Sent to the init slot instead — where
    // every guide went before these weights existed — an edge map is a picture
    // being restyled at denoise 0.65, and what comes back is a tidied edge map.
    //
    // Everywhere else that is still the right slot, because the init image is
    // the only thing those families have that means "start from this
    // arrangement".
    if (S.preStageReadsGuides(this.state)) return this.takeGuideAsPicture(path, opId);
    this.state.init = {
      filename: path,
      denoise: this.state.init?.denoise ?? S.PRESTAGE_DEFAULT_DENOISE,
    };
    this.commit();
    this.probeInit();
  }

  /** The guide as the picture the render is aimed at.
   *
   *  It replaces a guide already in the pool rather than joining it: re-tracing
   *  a frame at a different threshold is the loop the bench exists for, and
   *  three presses of it would otherwise fill every slot with the same picture
   *  at three settings. A guide the pool has no room for is refused out loud,
   *  the way a fourth picture is. */
  takeGuideAsPicture(path, opId = null) {
    const standing = this.state.refs.find((ref) => ref.role === "guide");
    if (standing) {
      standing.filename = path;
      standing.guide = opId;
    } else {
      const blocked = this.refBlocked();
      if (blocked) return this.flash(blocked);
      this.state.refs.push({
        handle: S.nextPreStageHandle(this.state), filename: path,
        role: "guide", guide: opId,
      });
    }
    this.commit();
    this.probeInit();
  }

  /** Point a style reference at a different image, keeping its handle — the
   *  prompt cites it by handle, and a re-add would renumber. */
  async replaceRef(ref) {
    const chosen = await openPicker({
      kinds: ["image", "renders"], kind: "image", only: "image", single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    const picked = chosen?.[0];
    if (!picked || picked.path === ref.filename) return;
    ref.filename = picked.path;
    this.commit();
  }

  async manageLoras(entry = null) {
    await openLoras({ state: this.state, checkpointModes: false, scope: "prestage",
                      reveal: entry?.name ?? null, onChange: () => this.commit() });
    this.commit();
  }

  /** Try another file in this LoRA's slot. See `state.replaceLora`. */
  async swapLora(entry) {
    await openLoras({
      state: this.state, checkpointModes: false, scope: "prestage",
      swapping: entry.name, onChange: () => this.commit(),
    });
    this.commit();
  }

  /** Measure the picture the canvas follows, so the aspect pill can show its
   *  shape. Not always the init image — on an edit family it is the first
   *  reference; see `S.preStageSource`. */
  probeInit() {
    for (const name of this.measurable()) {
      if (!name || this.sizes.has(name)) continue;
      const probe = new Image();
      probe.onload = () => {
        this.sizes.set(name, { width: probe.naturalWidth, height: probe.naturalHeight });
        this.render();
      };
      probe.src = viewUrl(name);
    }
  }

  /** Which pictures this editor needs the shape of.
   *
   *  The one the canvas follows, always. And on a family whose references do
   *  *not* set the canvas, every reference as well: an adapter trained on pairs
   *  that agreed about their aspect preserves visibly less from one that does
   *  not, and nothing about the render says so. Where the first reference is
   *  the canvas there is nothing to disagree with. */
  measurable() {
    const names = [S.preStageSource(this.state)];
    const refs = S.PRESTAGE_REFS[this.state.arch];
    if (refs?.reads && !refs.editsFirst) {
      names.push(...(this.state.refs ?? []).map((ref) => ref.filename));
    }
    return names;
  }

  /** The measured size of that picture, or null while it is still loading. */
  sourceSize() {
    const source = S.preStageSource(this.state);
    return source ? this.sizes.get(source) : null;
  }

  flash(message) {
    this.notice = message;
    this.render();
    clearTimeout(this.noticeTimer);
    this.noticeTimer = setTimeout(() => { this.notice = null; this.render(); }, 6000);
  }

  // ---- render ----------------------------------------------------------------


  /** The still this editor is about to make. No seconds: a still has no length,
   *  and the shell's frame draws what it is given. See `CreatorEditor.frame`. */
  frame() {
    const { width, height } = S.resolvedPreStage(this.state, this.sourceSize());
    return { width, height };
  }

  /** What the empty prompt box says, which is not one sentence for every
   *  family: what `@` names is a style reference on Krea 2 and the picture the
   *  instruction is about on an edit family. Re-read on every render, because
   *  the arch pill can move under it. */
  placeholder() {
    const refs = S.PRESTAGE_REFS[this.state.arch] ?? {};
    if (!refs.reads) {
      return t("Describe the image. These models were trained on long, detailed "
             + "natural-language prompts.");
    }
    return refs.editsFirst
      ? t("Say what to change. The first picture is the one being changed; name "
        + "the others with @ and they arrive as Picture 2 and Picture 3.")
      : t("Describe the image. These models were trained on long, detailed "
        + "natural-language prompts. Use @ to name a style reference.");
  }

  render() {
    const state = this.state;
    this.prompt.root.dataset.placeholder = this.placeholder();
    this.railHost.replaceChildren(this.renderRail());
    this.renderExpand();
    const chips = [
      ...(state.init ? [this.renderInitChip()] : []),
      ...state.refs.map((ref, slot) => this.renderRefChip(ref, slot)),
    ];
    this.assetsHost.replaceChildren(...(chips.length ? [keepScroll(el("div", { class: "mmc-assets" }, chips))] : []));
    this.loraHost.replaceChildren(...(state.loras.length ? [this.renderLoras()] : []));
    this.pillsHost.replaceChildren(this.renderPills());
    this.noticeHost.replaceChildren(
      ...(this.notice ? [el("div", { class: "mmc-warn", text: this.notice })] : []));
    // Only where there are widgets to drive: the window this body also opens
    // into is a second editor over the same state with no node behind it, and
    // the sampler row belongs to the node. `samplingBar` reads `widgets.seed`
    // on the way in, so an absent set is a throw rather than an empty row.
    this.samplingHost.replaceChildren(...(this.samplingWidgets ? [samplingBar({
      widgets: this.samplingWidgets,
      ...this.widgetIO(),
      set: (name, value) => { this.widgetIO().set(name, value); this.render(); },
      perSegment: false,
      turbo: this.renderTurbo(),
      trailing: [this.renderWeightsPill()],
    })] : []));
    this.sheetEditor?.render();
  }

  /** The way into the window, always there and lit once the text no longer
   *  fits. See `CreatorEditor.renderExpand`. */
  renderExpand() {
    if (!this.onFace) return;
    this.expandHost.replaceChildren(el("button", {
      class: `mmc-expand${this.overflowing ? " on" : ""}`,
      title: this.overflowing
        ? t("This prompt is longer than the node can show. Open it in a window.")
        : t("Open this still in a window — the prompt, its init image, references and LoRAs."),
      onclick: () => this.openEditor({ caret: "end" }),
    }, [icon("expand", 14)]));
  }

  /** See `CreatorEditor.onPromptOverflow`: the window takes the caret the once,
   *  and not again until the text has fitted and outgrown the box afresh. */
  onPromptOverflow(over) {
    if (!this.onFace || over === this.overflowing) return;
    this.overflowing = over;
    this.renderExpand();
    if (!over) {
      this.overflowWaived = false;
      return;
    }
    if (this.sheet || this.overflowWaived) return;
    if (document.activeElement !== this.promptBox) return;
    this.openEditor({ caret: "end" });
  }

  /**
   * The whole still, in a window — the same body, full size. See
   * `CreatorEditor.openEditor`: a second editor over the same state, because
   * the face's root is a ComfyUI DOM widget and cannot be re-parented into an
   * overlay. The arch pill goes with it, so the architecture can be changed
   * from either place; the sampler row and the stage stay on the node.
   */
  openEditor({ caret = null } = {}) {
    if (this.sheet) return;
    const editor = new PreStageEditor({
      state: this.state,
      onCommit: () => { this.onCommit?.(); this.render(); },
      archPill: this.archPill,
    });
    // See `CreatorEditor.openEditor`: a control in the window that writes
    // through an owner's callback re-renders the *face*, so the face redraws
    // the window or it draws a stale answer to a click that worked.
    this.sheetEditor = editor;
    this.sheet = openEditorSheet({
      title: t("Still"),
      subtitle: t("Prompt, init image, {noun} and LoRAs. The sampler stays on the node.",
                  { noun: t(S.PRESTAGE_REFS[this.state.arch]?.noun?.[1] ?? "style references") }),
      content: [editor.root],
      onClose: () => {
        this.sheet = null;
        this.sheetEditor = null;
        this.overflowWaived = this.overflowing;
        this.render();
      },
    });
    // The box is a contenteditable now, so the caret is a range rather than an
    // index — `focusEnd` is the same call the Creator's window makes.
    if (caret === "end") focusEnd(editor.prompt.root);
    else editor.prompt.root.focus();
  }

  /** What the rail's picture tool says it will do, which is a different
   *  sentence on each of the three architectures — see `S.PRESTAGE_REFS`. */
  refsTitle(refs) {
    if (!refs.reads) {
      return t("{arch} has no local reference conditioning — switch the model pill to "
             + "one that reads pictures.", { arch: S.PRESTAGE_ARCH_LABEL[this.state.arch] });
    }
    const max = S.preStageMaxRefs(this.state);
    if (refs.editsFirst) {
      return max === 1
        ? t("The picture the instruction is about. It sets the canvas and the render "
          + "starts from it. These weights read one — the 2509 and 2511 editions are "
          + "the ones post-trained on three.")
        : t("Up to {max} pictures the instruction is about. The first one is the "
          + "picture being changed — it sets the canvas and the render starts from "
          + "it; the others are there to be cited, as Picture 2 and Picture 3.", { max });
    }
    return t("Up to {max} images whose look this render should carry. Encoded through "
           + "the Qwen edit path Krea 2 was post-trained against — and only read at "
           + "all through a reference LoRA, which the adapter pill names.", { max });
  }

  renderRail() {
    const refs = S.PRESTAGE_REFS[this.state.arch] ?? { reads: false };
    const tool = (label, iconName, title, onclick) => el("button", {
      class: "mmc-tool", title, onclick,
    }, [el("span", { class: "mmc-tool-icon" }, [icon(iconName)]), el("span", { text: label })]);

    // Two groups, like the Creator's rail and the Timeline's: `.mmc-rail` is a
    // space-between row, and the seam between the groups is what puts this
    // render's tools at one end and the machine's at the other. Bare tools on
    // the rail get spread across the whole card instead, each one an equal
    // sibling of the next, which says nothing about which is which.
    return el("div", { class: "mmc-rail" }, [
      el("div", { class: "mmc-rail-group" }, [
        tool(t("Init image"), "frameIn",
             t("Start from an image instead of noise — img2img. The strength pill says how much of it survives."),
             () => this.setInit(false)),
        tool(t(refs.editsFirst ? "Pictures" : "Style refs"), "image",
             this.refsTitle(refs),
             () => this.addRefs(false)),
        tool(t("From video"), "video",
             t("Pull a single frame off a video's playhead — as the init image, saved as a PNG in the input folder."),
             () => this.setInit(true)),
        tool(t("Contact sheet"), "gallery",
             t("A strip of footage as one picture, so an edit model can be asked about a "
             + "whole shot at once — and the same tool cuts the edited sheet back into "
             + "frames. Hand it a clip to lay one, or a sheet to split one."),
             () => this.contactSheet()),
        tool(t("Add LoRA"), "effect",
             t("Manage the LoRAs patched onto the image model. Krea LoRAs train on RAW and apply on Turbo too."),
             () => this.manageLoras()),
      ]),
      el("div", { class: "mmc-rail-group" }, [
        tool(t("Presets"), "star",
             t("Save this setup so you can put it back, or apply one you saved before"),
             () => openPresetLibrary({ target: this.presetTarget?.() ?? null })),
      ]),
    ]);
  }

  renderInitChip() {
    const init = this.state.init;
    return el("div", { class: "mmc-asset mmc-tag-0", title: init.filename }, [
      // Straight back into the same picker the tool opens, which already keeps
      // the denoise you dialled in — the whole point of swapping the still is
      // to see the settings you have against a different picture.
      swappable(
        el("img", { class: "mmc-asset-thumb", src: viewUrl(init.filename, { preview: true }), alt: init.filename }),
        { title: t("Pick a different init image — the denoise stays"), onclick: () => this.setInit(false) },
      ),
      el("span", { class: "mmc-asset-handle", text: t("init") }),
      el("button", {
        class: "mmc-ghost",
        style: { fontSize: "11px" },
        title: t("How much of the render is new. 1.00 ignores the init entirely; low values keep its "
               + "composition and only restyle. Click to step down, right-click to step up."),
        text: init.denoise.toFixed(2),
        onclick: () => {
          init.denoise = Math.max(S.PRESTAGE_MIN_DENOISE, Math.round((init.denoise - 0.05) * 100) / 100);
          this.commit();
        },
        oncontextmenu: (event) => {
          event.preventDefault();
          init.denoise = Math.min(1, Math.round((init.denoise + 0.05) * 100) / 100);
          this.commit();
        },
      }),
      el("button", {
        class: "mmc-asset-x", text: "✕", title: t("Remove the init image"),
        onclick: () => { this.state.init = null; this.commit(); },
      }),
    ]);
  }

  renderRefChip(ref, slot = 0) {
    const refs = S.PRESTAGE_REFS[this.state.arch] ?? {};
    // What this picture is *for*, in the family's own words. On an edit family
    // nothing here is a style input: the first slot is the picture being
    // changed, and the rest are pictures the instruction names — so they wear
    // the label the encoder itself writes in front of them, which is also the
    // string the prompt cites them by. "style" is Krea 2's answer and Krea 2's
    // alone, where what an attached image contributes really is its look.
    // The first slot on an edit family is the one picture whose role is a
    // decision rather than a fact: it is the thing being changed by default,
    // and it does not have to be. So there it is a button, and everywhere else
    // it is the label it has always been.
    // A guide is never the picture being edited: it is the drawing the render
    // is aimed at, so the slot it happens to sit in does not make it a subject.
    const guide = ref.role === "guide";
    // A guide these weights were never post-trained on. Not a refusal — the
    // file is a picture and the encoder will read it as one — but the render
    // will be *of* the drawing rather than aimed at it, which is worth saying
    // where the drawing is.
    const untrained = guide && ref.guide
      && !(refs.nativeControl ?? []).includes(ref.guide);
    const edits = refs.editsFirst && slot === 0 && !this.state.init && !guide;
    const blank = S.preStageStartsBlank(this.state);
    const role = guide
      ? t("guide")
      : refs.editsFirst
        ? (edits && !blank ? t("editing") : t("Picture {n}", { n: slot + 1 }))
        : t(refs.noun?.[0] ?? "style reference");
    // Past the cap, and drawn rather than dropped: the blob keeps every
    // reference it was given so the compile is the one place that decides, and
    // a chip that vanished when the edition pill moved would take two pictures
    // with it and say nothing. See `parsePreStage`.
    const refused = slot >= S.preStageMaxRefs(this.state);
    // ...and the softer one: a shape the adapter was not trained to hold
    // against this canvas. A warning, because it is a worse render rather than
    // an impossible one — see `S.preStageRefOffShape`.
    const canvas = S.resolvedPreStage(this.state, this.sourceSize());
    const offShape = !refused && !untrained && S.preStageRefOffShape(
      this.state, this.sizes.get(ref.filename), canvas.width / canvas.height);
    return el("div", {
      class: `mmc-asset mmc-tag-${S.tagIndex(ref.handle)}`
             + (refused ? " mmc-asset-refused"
                : untrained || offShape ? " mmc-asset-offshape" : ""),
      title: refused
        ? t("This render will be refused: {arch} reads {max} of these, and this is "
          + "the one past it. Remove it, or move the edition pill.",
          { arch: S.PRESTAGE_ARCH_LABEL[this.state.arch], max: S.preStageMaxRefs(this.state) })
        : untrained
          ? t("These weights follow a depth, edge or pose map — this tracing is none "
            + "of the three, so it will be read as a picture of a drawing rather "
            + "than as a guide to aim at.")
        : offShape
          ? t("This picture's shape does not match the canvas. The reference adapters "
            + "were trained on pairs that agreed, so what they hold on to falls off "
            + "when it does not — crop it, or set the aspect to match.")
          : ref.filename,
    }, [
      swappable(
        el("img", { class: "mmc-asset-thumb", src: viewUrl(ref.filename, { preview: true }), alt: ref.filename }),
        {
          title: t("Swap the file behind @{handle} — the handle stays, so the prompt still fits.",
                   { handle: ref.handle }),
          onclick: () => this.replaceRef(ref),
        },
      ),
      el("span", { class: "mmc-asset-handle", text: `@${ref.handle}` }),
      // What this picture is *for*, which is not the same on every arch: a
      // style reference on Krea 2, and on an edit family the first slot is the
      // picture being changed while the rest are cited beside it.
      edits
        ? el("button", {
            class: `mmc-asset-role mmc-asset-role-pick${blank ? "" : " on"}`,
            text: role,
            title: blank
              ? t("Drawing onto an empty canvas — these pictures are only cited, and "
                + "the aspect pill sets the shape. Click to edit this picture instead.")
              : t("Editing this picture: the canvas follows its shape and the render "
                + "starts from it. Click to draw onto an empty canvas instead and "
                + "leave it as Picture 1, cited like the others."),
            onclick: () => {
              this.state.start_blank = !this.state.start_blank;
              this.commit();
            },
          })
        : el("span", { class: "mmc-asset-role", text: role }),
      el("button", {
        class: "mmc-asset-x", text: "✕", title: t("Remove @{handle}", { handle: ref.handle }),
        onclick: () => {
          this.state.refs = this.state.refs.filter((r) => r.handle !== ref.handle);
          this.commit();
        },
      }),
    ]);
  }

  renderLoras() {
    // No targets: the PreStage's image models have one DiT each, so "which
    // checkpoint does this LoRA claim" is not a question here — the same
    // reason the manager drops the mode row for them.
    return loraBlock(this.state, {
      targets: null,
      onToggle: (entry) => { S.toggleLora(this.state, entry.name); this.commit(); },
      onManage: (entry) => this.manageLoras(entry),
      onSwap: (entry) => this.swapLora(entry),
      onRemove: (entry) => { S.removeLora(this.state, entry.name); this.commit(); },
    });
  }

  renderPills() {
    const state = this.state;
    const geometry = S.resolvedPreStage(state, this.sourceSize());

    const archPill = this.archPill?.() ?? el("span");

    const aspectPill = el("button", {
      class: "mmc-pill",
      disabled: geometry.fromImage || undefined,
      title: geometry.fromImage
        ? t("The aspect follows the picture this render starts from — the resolution "
          + "pill still sets the scale.")
        : t("Aspect Ratio"),
      onclick: (event) => this.openAspect(event.currentTarget),
    }, geometry.fromImage
      ? [aspectGlyph(geometry.ratio, PILL_GLYPH), el("span", { class: "mmc-pill-sub", text: t("from image") })]
      : [aspectGlyph(geometry.ratio, PILL_GLYPH), el("span", { text: state.aspect })]);

    const resPill = el("button", {
      class: "mmc-pill",
      title: t("Short edge. Every image model here is comfortable up to a 2048×2048 area."),
      onclick: (event) => this.openResolution(event.currentTarget),
    }, [
      icon("res", 16),
      el("span", { text: `${state.short_edge}p` }),
      el("span", { class: "mmc-pill-sub", text: `${geometry.width} × ${geometry.height}` }),
    ]);

    const pills = [archPill, aspectPill, resPill];

    if (state.arch === "ideogram4") {
      // Ideogram's speed axis. The preset owns the schedule shape as well as
      // the step count, which is why this is a preset pill and not a slider.
      pills.push(el("button", {
        class: "mmc-pill",
        title: t(QUALITY_TITLE[state.quality]),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("Ideogram preset"),
          options: [...S.PRESTAGE_IDEOGRAM_QUALITIES],
          value: state.quality,
          onPick: (picked) => {
            state.quality = picked;
            this.widgetIO().set("steps", S.PRESTAGE_IDEOGRAM_STEPS[picked]);
            this.commit();
          },
        }),
      }, [icon("steps", 16), el("span", { text: `${state.quality} · ${S.PRESTAGE_IDEOGRAM_STEPS[state.quality]}` })]));
    }

    // The reference layout, and only where there is a reference to lay out and
    // a layout to pick. Krea 2's base weights read none: core hands the DiT no
    // default method because it never learned one, and every way of reading a
    // reference on this model is a LoRA. The published adapters disagree about
    // the layout and neither disagreement is an error, so the pill is where
    // that is said. Qwen Image Edit declares no methods and gets no pill — its
    // base weights read references, so core's detection already gives them the
    // layout they were trained with.
    // Which release of the Qwen edit weights is loaded, because nothing in the
    // file says and the answer decides how many pictures they read. A pill
    // rather than a filename guess alone: the guess is right for a file that
    // kept its published name and has nothing to go on for one that did not.
    if (S.PRESTAGE_REFS[state.arch]?.editions) {
      const max = S.preStageMaxRefs(state);
      pills.push(el("button", {
        class: "mmc-pill",
        title: t("Which Qwen-Image-Edit release this checkpoint is. It is not in the "
               + "file — only the filename hints at it — and it decides how many "
               + "pictures the weights were post-trained to read: one on the first "
               + "edition, three on 2509 and 2511."),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("Edition"),
          options: Object.keys(S.PRESTAGE_EDITIONS),
          value: state.edition,
          onPick: (picked) => { state.edition = picked; this.commit(); },
        }),
      }, [icon("weights", 16), el("span", { text: state.edition }),
          el("span", { class: "mmc-pill-sub",
                       text: t(max === 1 ? "{count} ref" : "{count} refs", { count: max }) })]));
    }

    // Which entry in the stack reads the references, on the family where one
    // has to. Named and not counted: a stack holding a style LoRA and nothing
    // that reads pictures is the same silent failure as an empty one, and this
    // pill is where the difference is said out loud.
    const adapterField = S.PRESTAGE_REFS[state.arch]?.adapter;
    if (adapterField && state.refs.length) {
      const stack = (state.loras ?? [])
        .filter((entry) => entry?.name && entry.enabled !== false)
        .map((entry) => entry.name);
      const named = state.ref_lora && stack.includes(state.ref_lora);
      pills.push(el("button", {
        class: `mmc-pill${named ? "" : " missing"}`,
        title: named
          ? t("The LoRA that reads these references. Krea 2's base weights never "
            + "learned to, so this is the only thing that makes the pictures render "
            + "at all.")
          : state.ref_lora
            ? t("{name} is named as the reference adapter but is no longer in the "
              + "stack. The render is refused until one is picked.", { name: state.ref_lora })
            : t("These references will not render: Krea 2 reads them only through a "
              + "reference LoRA, and none is named. Add one to the stack — "
              + "krea2_style_reference for style, an ai-toolkit edit LoRA for edits — "
              + "and pick it here."),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("Reference adapter"),
          options: stack,
          value: named ? state.ref_lora : null,
          onPick: (picked) => { state.ref_lora = picked; this.commit(); },
        }),
      }, [icon("model", 16), el("span", {
        text: named ? loraBase({ name: state.ref_lora }) : t("no adapter"),
      })]));
    }

    if (S.PRESTAGE_REFS[state.arch]?.methods.length && state.refs.length) {
      const adapted = state.ref_lora
        && (state.loras ?? []).some((entry) => entry?.name === state.ref_lora
                                            && entry.enabled !== false);
      pills.push(el("button", {
        class: `mmc-pill${adapted ? "" : " missing"}`,
        title: adapted
          ? t("How the references are laid into the token sequence. The ai-toolkit edit "
            + "LoRAs pin theirs at timestep zero; the identity-edit ones index them like "
            + "any other frame. Match the adapter named beside this pill.")
          : t("The layout only matters once an adapter reads the references — see the "
            + "adapter pill."),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("Reference layout"),
          options: [...S.PRESTAGE_REF_METHODS],
          value: state.ref_method,
          onPick: (picked) => { state.ref_method = picked; this.commit(); },
        }),
      }, [icon("image", 16), el("span", {
        text: state.ref_method === "index" ? t("indexed") : t("t=0 refs"),
      })]));
    }

    if (state.init) {
      pills.push(stepperPill({
        value: state.init.denoise, min: S.PRESTAGE_MIN_DENOISE, max: 1, step: 0.05, width: "52px",
        title: t("img2img strength — how much of the render is new. 1.00 ignores the init entirely; "
               + "low values keep its composition and only restyle."),
        format: (n) => t("img {value}", { value: n.toFixed(2) }),
        onChange: (next) => { state.init.denoise = next; this.commit(); },
      }));
    }

    return el("div", { class: "mmc-pills" }, pills);
  }

  // ---- turbo -----------------------------------------------------------------

  /** The turbo pill, under the H3 contract: save the sampler row once per
   *  throw, put it back exactly on release, own no second stack.
   *
   *  What it throws is the arch's business and the manifest says which. Krea 2
   *  ships the distillation twice — as its own checkpoint and as an SVD
   *  extraction of the same weight difference — so its pill offers both, and
   *  the LoRA route is the one that keeps RAW resident across a flick of the
   *  switch and lets a content LoRA ride along. Ideogram ships no distilled
   *  checkpoint at all: its pill is a LoRA or it does not engage.
   *
   *  A LoRA route is an ordinary stack entry the whole way — the manager's
   *  card, the chip's ✕ and the strength slider all work on it — which is the
   *  same bargain `turbo.js` strikes on the video side. */
  renderTurbo() {
    const state = this.state;
    const spec = S.turboOfArch(state.arch);
    if (!spec) return [];
    const turbo = state.turbo[state.arch];
    const io = this.widgetIO();
    const titles = TURBO_TITLE[state.arch] ?? {};

    if (spec.lora && !turbo.lora) loadLoraNames();

    const pills = [];
    pills.push(el("div", { class: `mmc-pill mmc-pill-group${turbo.on ? " accel-on" : ""}` }, [
      el("button", {
        class: "mmc-turbo-main",
        title: this.turboTitle(spec, turbo, io),
        onclick: (event) => {
          if (turbo.on) { this.throwTurbo(false); return; }
          // Nothing to throw yet on a LoRA-only arch: the first press is the
          // picking, on the spot — the pill was pressed to go faster, not to
          // go configure something.
          if (!spec.checkpoint && !turbo.lora) {
            this.openTurboSource(event.currentTarget, spec, turbo,
                                 () => this.throwTurbo(true));
            return;
          }
          this.throwTurbo(true);
        },
      }, [icon("bolt", 16), el("span", { text: t(turbo.on ? "turbo" : "turbo off") })]),
    ]));

    if (turbo.on) {
      const steps = Number(io.value("steps", 0));
      pills.push(el("div", { class: "mmc-pill mmc-turbo-seg" },
        Object.keys(spec.steps).map((quality) => el("button", {
          class: "mmc-turbo-opt",
          "aria-pressed": steps === spec.steps[quality],
          title: t(titles[quality] ?? ""),
          onclick: () => {
            turbo.quality = quality;
            io.set("steps", spec.steps[quality]);
            this.commit();
          },
        }, [
          el("span", { text: t(quality === "medium" ? "med" : quality) }),
          el("span", { class: "mmc-pill-sub", text: String(spec.steps[quality]) }),
        ]))));

      // Which of the two the run is on, and the way to the other. Only where
      // there are two: an arch with one route has nothing to say here.
      if (spec.lora && spec.checkpoint) {
        pills.push(el("button", {
          class: "mmc-pill",
          title: turbo.lora
            ? t("Running the distillation as a LoRA over RAW — the base checkpoint stays "
              + "loaded and the rest of the stack rides along. Press to swap to the "
              + "distilled checkpoint.", {})
            : t("Running the distilled checkpoint. Press to run the distillation as a "
              + "LoRA over RAW instead, which keeps one file resident and lets the rest "
              + "of the stack ride along."),
          onclick: (event) => this.openTurboSource(event.currentTarget, spec, turbo,
                                                   () => this.retrowTurbo()),
        }, [icon("model", 16), el("span", {
          text: turbo.lora ? shortLora(turbo.lora) : t("checkpoint"),
        })]));
      }
    }

    return pills;
  }

  /** What the switch says it will do, per arch and per route. */
  turboTitle(spec, turbo, io) {
    if (turbo.on) {
      return turbo.lora
        ? t("Turbo — {lora} over the ordinary checkpoint at {steps} steps, cfg 1. "
          + "Switching off removes the LoRA and puts the sampler row back.",
          { lora: shortLora(turbo.lora), steps: io.value("steps", "?") })
        : t("Turbo — running the Turbo checkpoint at {steps} steps, cfg 1. "
          + "Switching off loads RAW again and puts the sampler row back.",
          { steps: io.value("steps", "?") });
    }
    return spec.checkpoint
      ? t("Turbo off — running RAW. On, the distillation is loaded — the Turbo checkpoint, "
        + "or the same weights as a LoRA — and the row drops to the picked quality at cfg 1.")
      : t("Turbo off. Ideogram ships no distilled checkpoint, so this runs a distillation "
        + "LoRA over the ordinary one: a handful of steps at cfg 1, with the unconditional "
        + "checkpoint left unloaded. The first press picks the file.");
  }

  /** The source popover: the distilled checkpoint where there is one, then the
   *  LoRA files, distillation-shaped names first. */
  openTurboSource(anchor, spec, turbo, after) {
    const names = loraNames();
    const matched = names.filter((name) => /turbo|distill/i.test(name));
    const listed = matched.length ? matched : names;
    openChoicePopover(anchor, {
      title: t("Turbo source"),
      options: [
        ...(spec.checkpoint ? [t(TURBO_CHECKPOINT)] : []),
        ...listed,
      ],
      value: turbo.lora ?? (spec.checkpoint ? t(TURBO_CHECKPOINT) : ""),
      onPick: (picked) => {
        turbo.lora = picked === t(TURBO_CHECKPOINT) ? null : picked;
        after();
      },
    });
  }

  /** Throw the switch, saving the row on the way on and restoring it on the
   *  way off. The row it writes and the row it returns to are both the arch's
   *  declarations — see `setArch`, which resets to the same place. */
  throwTurbo(on) {
    const state = this.state;
    const spec = S.turboOfArch(state.arch);
    const turbo = state.turbo[state.arch];
    const io = this.widgetIO();

    if (!on) {
      const saved = turbo.saved ?? this.nativeRow();
      for (const [key, value] of Object.entries(saved)) io.set(key, value);
      if (turbo.lora) S.removeLora(state, turbo.lora);
      turbo.on = false;
      turbo.saved = null;
      this.commit();
      return;
    }

    // Saved once per throw, not per quality change: the row being remembered is
    // the pre-turbo one, and draft → good in between must not overwrite it.
    if (!turbo.on) {
      const native = this.nativeRow();
      turbo.saved = Object.fromEntries(Object.entries(native)
        .map(([key, value]) => [key, typeof value === "string"
          ? String(io.value(key, value)) : Number(io.value(key, value))]));
    }
    turbo.on = true;
    if (turbo.lora) {
      const entry = S.findLora(state, turbo.lora) ?? S.addLora(state, turbo.lora, []);
      if (entry) {
        entry.enabled = true;
        entry.strength = spec.default_strength ?? 1.0;
      }
    }
    io.set("steps", spec.steps[turbo.quality] ?? spec.steps[spec.default_quality]);
    for (const [key, value] of Object.entries(spec.row)) io.set(key, value);
    this.commit();
  }

  /** Swap route while the switch is on: drop whatever the old route added and
   *  engage the new one, so a run never carries both distillations at once. */
  retrowTurbo() {
    const state = this.state;
    const turbo = state.turbo[state.arch];
    for (const entry of state.loras ?? []) {
      if (entry.name !== turbo.lora && /turbo|distill/i.test(entry.name)) {
        S.removeLora(state, entry.name);
      }
    }
    turbo.on = false;
    this.throwTurbo(true);
  }

  /** The sampler row this arch runs at with the switch off — where `throwTurbo`
   *  returns to when nothing was saved, and what `setArch` writes. */
  nativeRow() {
    if (this.state.arch === "ideogram4") {
      // The one arch whose steps are not a widget default: the quality preset
      // owns them, and it owns the schedule they land on as well.
      return {
        steps: S.PRESTAGE_IDEOGRAM_STEPS[this.state.quality],
        cfg: S.PRESTAGE_IDEOGRAM_ROW.cfg,
        sampler_name: S.PRESTAGE_IDEOGRAM_ROW.sampler_name,
      };
    }
    return { ...S.PRESTAGE_BASE_ROW[this.state.arch] };
  }

  // ---- weights ---------------------------------------------------------------

  renderWeightsPill() {
    const missing = S.missingPreStageModels(this.state);
    const label = missing.length
      ? (missing.length === 1
          ? t("no {field}", { field: t(S.PRESTAGE_FIELD_LABEL[missing[0]]).toLowerCase() })
          : t("{count} weights missing", { count: missing.length }))
      : this.state.models.dtype === "default"
        ? t("weights") : t("weights · {dtype}", { dtype: this.state.models.dtype.replace("fp8_", "fp8 ") });
    return el("button", {
      class: `mmc-pill mmc-weights${missing.length ? " missing" : ""}`,
      title: missing.length
        ? t("Not picked yet: {fields}. The render is refused without them.",
            { fields: missing.map((f) => t(S.PRESTAGE_FIELD_LABEL[f])).join(", ") })
        : t("Which files {arch} loads.", { arch: S.PRESTAGE_ARCH_LABEL[this.state.arch] }),
      onclick: (event) => this.openWeights(event.currentTarget),
    }, [icon("weights", 16), el("span", { text: label })]);
  }

  openWeights(anchor) {
    const NONE = t("— none —");
    const state = this.state;
    const pop = el("div", { class: "mmc-pop mmc-weights-pop" });
    const body = el("div");

    const render = () => {
      const byFolder = catalogByFolder();
      const lists = {
        model: byFolder.diffusion_models ?? [], turbo_model: byFolder.diffusion_models ?? [],
        uncond_model: byFolder.diffusion_models ?? [],
        clip: byFolder.text_encoders ?? [], vae: byFolder.vae ?? [],
      };
      const side = state.models[state.arch];
      const missing = new Set(S.missingPreStageModels(state));

      const rows = S.PRESTAGE_FIELDS[state.arch].map((field) => el("div", {
        class: `mmc-weight-row${missing.has(field) ? " missing" : ""}`,
      }, [
        el("span", { class: "mmc-weight-name", text: t(S.PRESTAGE_FIELD_LABEL[field]) }),
        el("button", {
          class: `mmc-weight-file${side[field] ? "" : " empty"}`,
          title: t(S.PRESTAGE_FIELD_HINT[state.arch][field]),
          text: side[field] || t("not set"),
          onclick: (event) => openChoicePopover(event.currentTarget, {
            title: t(S.PRESTAGE_FIELD_LABEL[field]),
            options: [NONE, ...lists[field]],
            value: side[field] || NONE,
            onPick: (picked) => {
              side[field] = picked === NONE ? "" : picked;
              this.commit();
              render();
            },
          }),
        }),
      ]));

      rows.push(el("div", { class: "mmc-weight-row" }, [
        el("span", { class: "mmc-weight-name", text: t("Precision") }),
        el("button", {
          class: "mmc-weight-file",
          title: t("How the checkpoints are loaded. fp8 halves the weights in VRAM at some cost "
                 + "in fidelity; 'default' loads them as they were saved. GGUF files ignore "
                 + "this — their precision was baked in when they were quantized."),
          text: state.models.dtype,
          onclick: (event) => openChoicePopover(event.currentTarget, {
            title: t("Precision"),
            options: S.MODEL_DTYPES,
            value: state.models.dtype,
            onPick: (picked) => { state.models.dtype = picked; this.commit(); render(); },
          }),
        }),
      ]));

      body.replaceChildren(...rows);
    };

    pop.append(el("div", { class: "mmc-pop-title", text: t("Weights — {arch}", { arch: S.PRESTAGE_ARCH_LABEL[state.arch] }) }), body);
    render();
    document.body.appendChild(pop);
    placeNear(pop, anchor);
    dismissable(pop);
    loadCatalog(() => pop.isConnected && render());
    refreshCatalog(() => pop.isConnected && render());
  }

  // ---- popovers --------------------------------------------------------------

  openAspect(anchor) {
    const pop = el("div", { class: "mmc-pop" }, [el("div", { class: "mmc-pop-title", text: t("Aspect Ratio") })]);
    for (const [label, ratio] of S.PRESTAGE_ASPECTS) {
      pop.appendChild(el("button", {
        class: "mmc-opt",
        "aria-checked": this.state.aspect === label,
        onclick: () => { this.state.aspect = label; close(); this.commit(); },
      }, [
        el("span", { class: "mmc-opt-label" }, [aspectGlyph(ratio), el("span", { text: label })]),
        el("span", { class: "mmc-radio" }),
      ]));
    }
    document.body.appendChild(pop);
    placeNear(pop, anchor);
    const close = dismissable(pop);
  }

  openResolution(anchor) {
    const body = edgeSlider({
      min: S.PRESTAGE_MIN_EDGE, max: S.PRESTAGE_MAX_EDGE, step: S.PRESTAGE_CANVAS_MULTIPLE,
      value: this.state.short_edge,
      mark: S.PRESTAGE_DEFAULT_EDGE, markLabel: t("default"),
      apply: (edge) => { this.state.short_edge = edge; },
      describe: () => {
        const geometry = S.resolvedPreStage(this.state, this.sourceSize());
        return {
          size: `${geometry.width} × ${geometry.height}`,
          note: this.state.short_edge >= S.PRESTAGE_MAX_EDGE
            ? t("The models' 2048 ceiling — wide ratios trade the short edge down to hold the area.")
            : t("{speed} {edge} is the comfortable default on every image model here.", {
                speed: t(this.state.short_edge < S.PRESTAGE_DEFAULT_EDGE ? "Faster, softer." : "Sharper, slower."),
                edge: S.PRESTAGE_DEFAULT_EDGE,
              }),
        };
      },
      commit: () => this.commit(),
    });
    const pop = el("div", { class: "mmc-pop mmc-slider" }, [body]);
    document.body.appendChild(pop);
    placeNear(pop, anchor);
    dismissable(pop);
  }
}

/**
 * The PreStage node's body: the blob, the stage, and whichever editor the
 * architecture calls for.
 *
 * Two of the three architectures are image models and are driven by the editor
 * above. The third is MiniMax H3, whose still is a *video generation* with one
 * latent frame decoded — so it is driven by `CreatorEditor`, the same body the
 * Creator node and every timeline segment use, on a request in the same shape.
 * That is not a saving of a few lines: the reference pipeline, the keyframe
 * pair, the slot arithmetic, the @-mention prompt, the routing badge and the
 * weights popover are one implementation, and a still gets all of them by
 * being what it is rather than by having them re-described.
 *
 * What this owns is what has to outlive a switch between the two: the blob, the
 * stage floated beside the node (the satellite bound it once), and the arch
 * pill itself — the control that does the switching cannot belong to the thing
 * being switched.
 */
export class PreStageBody {
  constructor({ state, onCommit, samplingWidgets, onWidgetChange, nodeId, peer = null }) {
    this.state = state;
    this.onCommit = onCommit;
    this.samplingWidgets = samplingWidgets;
    this.onWidgetChange = onWidgetChange;
    this.nodeId = nodeId;
    this.peer = peer;

    this.stage = new Stage({
      nodeId: this.nodeId,
      resultChips: (saved) => this.renderResultChips(saved),
    });

    this.host = el("div", { class: "mmc-prestage-host" });
    this.root = this.host;
    this.mount();
  }

  destroy() {
    this.editor?.destroy();
    this.stage?.destroy();
  }

  commit() {
    this.onCommit?.();
    this.editor?.render();
    this.onRender?.();
  }

  /** The still this node is about to make, from whichever editor is mounted —
   *  the Krea branch's own, or the H3 branch's Creator body over the still's
   *  request. For the fullscreen shell's frame; see `CreatorEditor.frame`. */
  frame() {
    return this.editor?.frame?.() ?? null;
  }

  /** A saved workflow, or a stash restored onto a freshly spawned node. The
   *  architecture may differ from what is mounted, so this remounts. */
  setState(state) {
    this.state = state;
    this.mount();
  }

  mount() {
    this.editor?.destroy();
    this.editor = S.isStill(this.state) ? this.mountStill() : this.mountImage();
    // Same hand-off the piece's face makes: the view this body is drawn in is
    // the body's to remember, because swapping architectures builds a new
    // editor that was never told. See `Fullscreen.setCastResident`.
    this.editor.castResident = this.castResident;
    this.host.replaceChildren(this.editor.root);
    // The architecture decides the canvas, so swapping editors is exactly when
    // a host drawing the frame has to redraw it.
    this.onRender?.();
  }

  mountImage() {
    return new PreStageEditor({
      state: this.state,
      onCommit: () => this.onCommit?.(),
      samplingWidgets: this.samplingWidgets,
      onWidgetChange: this.onWidgetChange,
      nodeId: this.nodeId,
      stage: this.stage,
      archPill: () => this.renderArchPill(),
      presetTarget: () => this.presetTarget(),
    });
  }

  /** The H3 branch: a Creator body on the still's own request.
   *
   *  Everything it is handed is what a Creator node hands it, minus three
   *  things a still has no use for — the seconds pill (how much video gets
   *  sampled to obtain the one frame is its own pill), the settings tool (it
   *  holds the video rate control), and the pre-stage pill, because this *is*
   *  the pre-stage.
   */
  mountStill() {
    const still = this.state[S.PRESTAGE_STILL_ARCH];
    const editor = new CreatorEditor({
      state: still.request,
      // The sampler row is the *node's*, not this request's: one row serves all
      // three architectures, and `serializeStill` carries no row of its own.
      samplingStore: {
        read: () => this.state.sampling,
        write: (block) => { this.state.sampling = block; },
      },
      onCommit: () => this.onCommit?.(),
      samplingWidgets: this.samplingWidgets,
      onWidgetChange: this.onWidgetChange,
      nodeId: this.nodeId,
      stage: this.stage,
      durationPill: false,
      // The settings page holds the video rate control and this node writes
      // PNGs, so it would be a button over nothing.
      settingsTool: false,
      // The pre-stage's, not the request's: what you save from this node is
      // this node, and on the H3 branch the request is only where it keeps its
      // files. Same reasoning as the piece's face wearing its one shot.
      presetTarget: () => this.presetTarget(),
      // The arch pill takes the video family's slot at the head of the row —
      // same question, a different list of answers. The still's own two pills
      // stay where a video's duration would be, because that is what they say.
      modelPill: () => [this.renderArchPill()],
      extraPills: () => this.renderStillPills(),
      extraTools: () => [this.renderFrameGrabTool()],
      // The `@` menu's roster, exactly as the video face wires it — a still on
      // this branch is a video generation, and the request is the piece a
      // member is cast into: its assets are the shot's row, its subjects the
      // whole of the cast.
      castFromLibrary: (member) => {
        const subject = P.addSubjectToPiece(member, still.request);
        if (!subject) return null;
        this.commit();
        return subject.handle;
      },
      setRoute: (route) => {
        still.request.models.route = route;
        this.commit();
      },
    });
    return editor;
  }

  /** The sampler row's `{value, set}` pair, over the pre-stage's own blob.
   *
   *  Same move as the piece's — see `sampling.blobIO`. This node is the one that
   *  wanted it most: its three architectures want three different rows and there
   *  is one static widget schema underneath them, wearing Krea's numbers. */
  widgetIO() {
    return blobIO(
      () => this.samplingWidgets,
      () => this.state.sampling,
      (block) => { this.state.sampling = block; this.onCommit?.(); },
      () => this.onWidgetChange?.());
  }

  /**
   * What the preset library saves from this node and applies back to it.
   *
   * Owned here rather than by the editor because applying one can change the
   * architecture, and each architecture has a body of its own — so the apply
   * ends in `mount`, which is the same remount the arch pill does.
   *
   * The cover comes off the stage, exactly as the Creator's does: a still this
   * node just made is stamped with this node's id, so it is already sitting in
   * `stage.result` by the time anyone presses Save.
   */
  presetTarget() {
    return {
      scope: "prestage",
      label: t("this pre-stage"),
      arch: () => this.state.arch,
      capture: () => ({
        data: P.capturePreStage(this.state, this.widgetIO()),
        cover: P.coverFromResult(this.stage?.result),
        defaultName: (this.promptOf() || "").trim().split("\n")[0].slice(0, 48),
      }),
      apply: (body, keys, from) => {
        P.applyToPreStage(body, keys, this.state, this.widgetIO(), { from });
        this.onCommit?.();
        // Not `commit`: the architecture may have moved, and the body that draws
        // one architecture cannot draw another.
        this.mount();
      },
    };
  }

  // ---- the model pill --------------------------------------------------------

  /** Switch architectures. Each side keeps its own state — its files, its
   *  canvas, its attachments — because the two have nothing in common but the
   *  node they are on; only the prompt is carried across, since that is the
   *  thing you were in the middle of writing. The sampler row is rewritten,
   *  because these models run at numbers that have nothing to do with each
   *  other and carrying the row across would be wrong on arrival. */
  setArch(arch) {
    if (arch === this.state.arch) return;
    const io = this.widgetIO();
    const from = this.promptOf();

    // The switch is per arch, so leaving one does not throw the other's — but
    // the row on the way out is this node's one row, and it belongs to whoever
    // is arriving. Released here rather than carried across.
    const leaving = this.state.turbo[this.state.arch];
    if (leaving?.on && leaving.lora) S.removeLora(this.state, leaving.lora);
    if (leaving) { leaving.on = false; leaving.saved = null; }
    this.state.arch = arch;

    if (arch === "ideogram4") {
      io.set("steps", S.PRESTAGE_IDEOGRAM_STEPS[this.state.quality]);
      io.set("cfg", S.PRESTAGE_IDEOGRAM_ROW.cfg);
      io.set("sampler_name", S.PRESTAGE_IDEOGRAM_ROW.sampler_name);
    } else if (S.PRESTAGE_BASE_ROW[arch]) {
      const row = S.PRESTAGE_BASE_ROW[arch];
      io.set("steps", row.steps);
      io.set("cfg", row.cfg);
      io.set("sampler_name", row.sampler_name);
      // A family without a scheduler control (Klein's schedule is the model's
      // own) declares none, and the widget is left where it was rather than
      // written undefined.
      if (row.scheduler !== undefined) io.set("scheduler", row.scheduler);
    } else {
      const row = S.PRESTAGE_STILL_ROW;
      io.set("steps", row.steps);
      io.set("cfg", row.cfg);
      io.set("sampler_name", row.sampler_name);
      io.set("scheduler", row.scheduler);
    }

    if (from && !this.promptOf()) this.setPrompt(from);
    this.onCommit?.();
    this.mount();
  }

  promptOf() {
    return (S.isStill(this.state) ? this.state[S.PRESTAGE_STILL_ARCH].request.prompt : this.state.prompt) ?? "";
  }

  setPrompt(text) {
    if (S.isStill(this.state)) this.state[S.PRESTAGE_STILL_ARCH].request.prompt = text;
    else this.state.prompt = text;
  }

  renderArchPill() {
    const state = this.state;
    return el("button", {
      class: `mmc-pill mmc-pill-model mmc-prestage-arch${S.isStill(state) ? " mmc-experimental" : ""}`,
      // The description is the family's own, off its manifest — a translation
      // key like any string written in source.
      title: t("{arch} Click to switch.", { arch: t(stillFamily(state.arch).description) }),
      onclick: (event) => openChoicePopover(event.currentTarget, {
        title: t("Image model"),
        options: S.PRESTAGE_ARCHES.map((arch) => S.PRESTAGE_ARCH_LABEL[arch]),
        value: S.PRESTAGE_ARCH_LABEL[state.arch],
        onPick: (picked) => this.setArch(
          S.PRESTAGE_ARCHES.find((arch) => S.PRESTAGE_ARCH_LABEL[arch] === picked)
            ?? DEFAULT_STILL_ARCH),
      }),
    }, [icon("model", 16),
        el("span", { class: "mmc-model-name", text: S.PRESTAGE_ARCH_LABEL[state.arch] })]);
  }

  // ---- the H3 branch's own pills ---------------------------------------------

  /** What a still costs and which moment of it is kept — the two things H3 has
   *  that a video render does not, because a video render keeps all of them.
   *
   *  Both are written in the artist's units rather than the VAE's. The length
   *  is a cost against the cheapest pass, because a still is one picture at
   *  every length and what the longer ones buy is distribution, not frames.
   *  The index is a time, because "the same shot a moment later" is what
   *  moving off the causal frame gets you — and it is only offered once there
   *  is somewhere to move to. */
  renderStillPills() {
    const still = this.state[S.PRESTAGE_STILL_ARCH];
    const lengths = S.PRESTAGE_STILL_LENGTHS;
    const cheapest = lengths[0];
    const longest = lengths[lengths.length - 1];
    const latents = S.stillLatentFrames(still.frames);

    // The list is a cost ladder whose top rung is named for what it buys.
    const lengthLabel = (n) =>
      (n === cheapest ? t("Draft")
        : n === longest ? t("Trained range")
        : t("≈{factor}× draft", { factor: S.stillCostFactor(n) }));
    const lengthSub = (n) =>
      (n === cheapest ? t("the cheapest pass — {frames} frames", { frames: n })
        : n === longest ? t("{frames} frames, what the weights saw — ≈{factor}× draft",
                            { frames: n, factor: S.stillCostFactor(n) })
        : t("{frames} frames", { frames: n }));

    const length = el("button", {
      class: "mmc-pill",
      title: t("How long a clip is sampled to get this one picture. Every length yields the "
           + "same single frame; a longer one is more in-distribution — the weights were "
           + "trained from {trained} frames up — and costs proportionally more. Sampling "
           + "{frames} frames now, ≈{factor}× the cheapest pass.",
           { trained: longest, frames: still.frames, factor: S.stillCostFactor(still.frames) }),
      onclick: (event) => openChoicePopover(event.currentTarget, {
        title: t("Sampled length"),
        options: lengths,
        value: still.frames,
        label: lengthLabel,
        sub: lengthSub,
        onPick: (frames) => {
          still.frames = frames;
          // A shorter clip can leave the kept frame past the end of it.
          const total = S.stillLatentFrames(frames);
          if (still.latent_index >= total) still.latent_index = total - 1;
          if (still.latent_index < -total) still.latent_index = 0;
          this.commit();
        },
      }),
    }, [icon("clock", 16), el("span", { text: `${still.frames}f` }),
        el("span", { class: "mmc-pill-sub",
                     text: still.frames === cheapest ? t("draft")
                       : still.frames === longest ? t("trained")
                       : t("≈{factor}×", { factor: S.stillCostFactor(still.frames) }) })]);

    // At the cheapest length there are two frames and one of them is right, so
    // the pill is noise until either the clip is long enough for the choice to
    // be a choice or a saved graph already made one.
    if (still.frames === cheapest && still.latent_index === 0) return [length];

    const index = stepperPill({
      value: still.latent_index, min: 0, max: latents - 1, step: 1, width: "64px",
      title: t("Which moment of the sampled clip becomes the picture. The first frame is the "
             + "causal one — a function of that video frame alone, and the only one the "
             + "decode is exact for. Later frames are the same shot a moment on, blended "
             + "from a few frames each and correspondingly softer."),
      format: (n) => (n === 0 ? t("first frame")
                        : t("+{seconds} s", { seconds: S.stillLatentSeconds(n, still.frames).toFixed(2) })),
      onChange: (next) => { still.latent_index = Math.round(next); this.commit(); },
    });

    return [length, index];
  }

  // ---- the rest of the rail --------------------------------------------------

  /** Not on the Creator's rail, because the Creator has this node. Here it is
   *  the only way to turn a moment of a clip into a keyframe. */
  renderFrameGrabTool() {
    return el("button", {
      class: "mmc-tool",
      title: t("Pull a single frame off a video's playhead and open on it — saved as a PNG in "
             + "the input folder."),
      onclick: () => this.grabFrame(),
    }, [el("span", { class: "mmc-tool-icon" }, [icon("video")]), el("span", { text: t("From video") })]);
  }

  async grabFrame() {
    const request = this.state[S.PRESTAGE_STILL_ARCH].request;
    const blocked = S.blockedReason(request, "first_frame");
    if (blocked) return;
    const clip = await openPicker({
      kinds: ["video", "renders"], kind: "video", single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    if (!clip) return;
    const grabbed = await openFrameGrab({ path: clip[0].path });
    if (!grabbed) return;
    this.setStillFrame(grabbed.path);
  }

  /** The H3 branch's own "start from this picture": the request's first frame,
   *  replaced rather than added to, because there is only one of them. */
  setStillFrame(filename) {
    const request = this.state[S.PRESTAGE_STILL_ARCH].request;
    if (S.blockedReason(request, "first_frame")) return;
    const existing = S.frameAsset(request, "first_frame");
    if (existing) request.assets = request.assets.filter((a) => a.handle !== existing.handle);
    request.assets.push({
      handle: S.nextHandle(request, "image"),
      kind: "image",
      role: "first_frame",
      filename,
    });
    this.commit();
  }

  // ---- taking a picture in ---------------------------------------------------

  /**
   * A guide off the ControlNet bench, or any other picture handed to this node
   * from outside it, taken as the thing the still is built on.
   *
   * The body's, not the editor's, because the body is what a caller can reach:
   * `mmcBody` is a `PreStageBody`, and the door the bench looks for has to be on
   * the object it is looking at. Which slot "built on" means is the arch's — an
   * init image on the two that draw, the request's start frame on the H3 branch
   * — and the editor already owns that answer for its own architecture.
   */
  takeGuide({ path, opId = null }) {
    if (this.state.arch === S.PRESTAGE_STILL_ARCH) {
      // **H3's still is a one-frame video generation, so it is aimed the way a
      // shot is.** The Fun ControlNet branch loads beside the same checkpoint
      // and reads the same drawing; the only difference is that one frame comes
      // back instead of a hundred and forty. So a tracing goes to the request's
      // guide slot, through the same door a shot's does.
      //
      // It used to go to the start frame, which is the worst available answer:
      // the render *opens* on the edge map and develops away from it, so what
      // comes back is a tidied edge map rather than a picture aimed at one.
      // That was the fallback for a family with nothing to read a guide with,
      // and this branch was reaching it because it had never been given the
      // ControlNet the video path had.
      const editor = this.editor;
      if (editor?.takeGuide && S.controlOf(S.pieceFamily(editor.piece))) {
        // A still, and said so: the pre-stage renders one frame, so the drawing
        // it is aimed at is one drawing. `guide.read` holds it for the whole of
        // a one-frame generation, which is the length of it.
        return editor.takeGuide({ path, kind: "image", op: opId ?? "" });
      }
      return this.setStillFrame(path);
    }
    this.editor?.takeGuide?.({ path, opId });
  }

  /**
   * The finished still, back into this same node as the next render's subject.
   *
   * The three chips beside this one send the picture *on* — to the shot, as a
   * start frame or a reference. This one is the loop that has no other door:
   * you edited a picture, the edit is right about one thing and wrong about
   * another, and what you want to change now is the render you are looking at.
   * Without it the way round is the picker, four presses away, hunting for your
   * own output among everything else in the folder.
   *
   * Where it lands is the arch's own answer to "the picture this render is
   * about": the first reference slot on a family that edits, the init image on
   * one that draws, the request's start frame on the H3 branch. On an edit
   * family the slot is *replaced* and its handle kept, so a prompt that cites
   * `@ref-1` is still citing the picture in front of it.
   */
  takeBack(filename) {
    if (this.state.arch === S.PRESTAGE_STILL_ARCH) {
      this.setStillFrame(filename);
      return this.reveal();
    }
    if (!S.PRESTAGE_REFS[this.state.arch]?.editsFirst) {
      this.editor?.takeGuide?.({ path: filename });
      return this.reveal();
    }
    const first = this.state.refs[0];
    if (first) first.filename = filename;
    else this.state.refs.unshift({ handle: S.nextPreStageHandle(this.state), filename });
    this.commit();
    this.editor?.probeInit?.();
    this.reveal();
  }

  /**
   * Put this pre-stage in front of whoever just sent something to it.
   *
   * A picture handed over lands in a blob, and a blob is not somewhere anybody
   * is looking: the press that sends it is followed, every time, by writing the
   * instruction that goes with it. So the send opens the place to write.
   *
   * Where that is depends on where the press happened. Inside the fullscreen
   * shell the pre-stage is a step and the shell turns to it — a window on top of
   * a window would be two rooms for one node. On the canvas there is no shell,
   * and the window is the only place with room for the prompt.
   */
  reveal() {
    if (revealPreStage(this.nodeId)) return;
    this.editor?.openEditor?.();
  }

  // ---- the hand-off ----------------------------------------------------------

  /** The chips on the finished still: one click writes it into the peer's blob
   *  as a start frame, end frame or reference — or back into this node as the
   *  next render's subject. The annotated `[output]` path is the same currency
   *  the gallery attach uses — one store, no copy. */
  renderResultChips(saved) {
    const filename = `${saved.subfolder ? `${saved.subfolder}/` : ""}${saved.filename} [output]`;
    const chips = [this.renderAgainChip(filename)];
    const target = this.peer?.();
    if (!target) return chips;
    const chip = (role, label, title) => el("button", {
      class: "mmc-stage-chip mmc-stage-send",
      text: t(label),
      title: t("{action} on {target}.", { action: t(title), target: target.label }),
      onpointerdown: (event) => event.stopPropagation(),
      onclick: () => target.attach(role, filename),
    });
    chips.push(
      chip("first_frame", "→ start", "Use this still as the start frame"),
      chip("last_frame", "→ end", "Use this still as the end frame"),
      chip("reference", "→ ref", "Attach this still as a reference"),
    );
    return chips;
  }

  /** The way back in. Drawn whether or not this node has a peer: iterating on
   *  your own still is a thing to want on a pre-stage nobody has attached to a
   *  shot yet, and it is the only chip here that does not need one. */
  renderAgainChip(filename) {
    const edits = S.PRESTAGE_REFS[this.state.arch]?.editsFirst;
    return el("button", {
      class: "mmc-stage-chip mmc-stage-send",
      text: t(edits ? "↻ edit" : "↻ again"),
      title: this.state.arch === S.PRESTAGE_STILL_ARCH
        ? t("Build the next still on this one — it becomes the start frame of the "
          + "clip this branch samples.")
        : edits
          ? t("Edit this again. It replaces the picture in the first slot, so the next "
            + "instruction is about the render you are looking at.")
          : t("Start the next render from this one — it becomes the init image, at the "
            + "strength already dialled in."),
      onpointerdown: (event) => event.stopPropagation(),
      onclick: () => this.takeBack(filename),
    });
  }
}
