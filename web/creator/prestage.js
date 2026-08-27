// The PreStage node: stills for the pipeline, made on the left.
//
// Two classes. `PreStageEditor` is the body for the two *image* architectures,
// Krea 2 and Ideogram 4 — same skeleton as CreatorEditor (rail, chips, panel,
// pills, sampler row) because it is driven the same way, and the same prompt
// box for the same reason.
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
// Krea 2 and Ideogram 4 want different sampler rows — RAW runs 52 steps at cfg
// 3.5 where Ideogram runs its preset's steps at cfg 7 on its own schedule — so
// switching the arch rewrites the row, and the turbo pill exists only on Krea
// (Turbo *is* a checkpoint there; Ideogram's speed axis is its preset table).

import { el, icon, ICONS, svg, dismissable, keepScroll, placeNear, swappable } from "./dom.js";
import { DEFAULT_STILL_ARCH, stillFamily } from "./manifest.js";
import { openPicker } from "./picker.js";
import { openLoras, loraBlock } from "./loras.js";
import { openFrameGrab } from "./framegrab.js";
import { openChoicePopover, stepperPill, aspectGlyph, edgeSlider, PILL_GLYPH } from "./pills.js";
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
    this.prompt.root.dataset.placeholder =
      t("Describe the image. Both models were trained on long, detailed "
      + "natural-language prompts. Use @ to name a style reference.");
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
    this.onCommit?.();
    this.render();
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
    if (this.state.arch === "ideogram4") {
      return t("Ideogram 4.0 has no local reference conditioning — switch the model "
             + "pill to Krea 2 to use style references.");
    }
    if ((this.state.refs?.length ?? 0) >= S.PRESTAGE_MAX_REFS) {
      return t("At most {max} style references — the Qwen edit encoder the model "
             + "reads them through has exactly three image slots.",
             { max: S.PRESTAGE_MAX_REFS });
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

  async addRefs(fromVideo = false) {
    if (this.state.arch === "ideogram4") {
      return this.flash(t("Ideogram 4.0 has no local reference conditioning — switch the model "
                        + "pill to Krea 2 to use style references."));
    }
    const room = S.PRESTAGE_MAX_REFS - this.state.refs.length;
    if (room <= 0) {
      return this.flash(t("At most {max} style references — the Qwen edit encoder "
                        + "the model reads them through has exactly three image slots.",
                        { max: S.PRESTAGE_MAX_REFS }));
    }
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

  probeInit() {
    const init = this.state.init;
    if (!init || this.sizes.has(init.filename)) return;
    const probe = new Image();
    probe.onload = () => {
      this.sizes.set(init.filename, { width: probe.naturalWidth, height: probe.naturalHeight });
      this.render();
    };
    probe.src = viewUrl(init.filename);
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
    const { width, height } =
      S.resolvedPreStage(this.state, this.state.init ? this.sizes.get(this.state.init.filename) : null);
    return { width, height };
  }

  render() {
    const state = this.state;
    this.railHost.replaceChildren(this.renderRail());
    this.renderExpand();
    const chips = [
      ...(state.init ? [this.renderInitChip()] : []),
      ...state.refs.map((ref) => this.renderRefChip(ref)),
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
      subtitle: t("Prompt, init image, style references and LoRAs. The sampler stays on the node."),
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

  renderRail() {
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
        tool(t("Style refs"), "image",
             this.state.arch === "ideogram4"
               ? t("Ideogram 4.0 has no local reference conditioning — style references are a Krea 2 feature.")
               : t("Up to three images whose look this render should carry. Encoded through the Qwen edit "
                 + "path Krea 2 was post-trained against; the krea2_style_reference LoRA strengthens it."),
             () => this.addRefs(false)),
        tool(t("From video"), "video",
             t("Pull a single frame off a video's playhead — as the init image, saved as a PNG in the input folder."),
             () => this.setInit(true)),
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

  renderRefChip(ref) {
    return el("div", {
      class: `mmc-asset mmc-tag-${S.tagIndex(ref.handle)}`,
      title: ref.filename,
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
      el("span", { class: "mmc-asset-role", text: t("style") }),
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
    const geometry = S.resolvedPreStage(state, state.init ? this.sizes.get(state.init.filename) : null);

    const archPill = this.archPill?.() ?? el("span");

    const aspectPill = el("button", {
      class: "mmc-pill",
      disabled: geometry.fromImage || undefined,
      title: geometry.fromImage
        ? t("The aspect follows the init image — the resolution pill still sets the scale.")
        : t("Aspect Ratio"),
      onclick: (event) => this.openAspect(event.currentTarget),
    }, geometry.fromImage
      ? [aspectGlyph(geometry.ratio, PILL_GLYPH), el("span", { class: "mmc-pill-sub", text: t("from image") })]
      : [aspectGlyph(geometry.ratio, PILL_GLYPH), el("span", { text: state.aspect })]);

    const resPill = el("button", {
      class: "mmc-pill",
      title: t("Short edge. Both models are comfortable up to a 2048×2048 area."),
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

    // The reference layout, and only where there is a reference to lay out.
    // Krea 2's base weights read none: core hands the DiT no default method
    // because it never learned one, and every way of reading a reference on
    // this model is a LoRA. The published adapters disagree about the layout
    // and neither disagreement is an error, so the pill is where that is said.
    if (state.arch === "krea2" && state.refs.length) {
      const adapted = (state.loras ?? []).some((entry) => entry.enabled !== false);
      pills.push(el("button", {
        class: `mmc-pill${adapted ? "" : " missing"}`,
        title: adapted
          ? t("How the references are laid into the token sequence. The ai-toolkit edit "
            + "LoRAs pin theirs at timestep zero; the identity-edit ones index them like "
            + "any other frame. Match the adapter in the stack.")
          : t("These references will not render: Krea 2 reads them only through a "
            + "reference LoRA. Add one to the stack — krea2_style_reference for style, "
            + "an ai-toolkit edit LoRA for edits."),
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
      return {
        steps: S.PRESTAGE_IDEOGRAM_STEPS[this.state.quality],
        cfg: S.PRESTAGE_IDEOGRAM_ROW.cfg,
        sampler_name: S.PRESTAGE_IDEOGRAM_ROW.sampler_name,
      };
    }
    return { ...S.PRESTAGE_KREA_RAW };
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
        const geometry = S.resolvedPreStage(this.state,
          this.state.init ? this.sizes.get(this.state.init.filename) : null);
        return {
          size: `${geometry.width} × ${geometry.height}`,
          note: this.state.short_edge >= S.PRESTAGE_MAX_EDGE
            ? t("The models' 2048 ceiling — wide ratios trade the short edge down to hold the area.")
            : t("{speed} {edge} is the comfortable default for both models.", {
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

    if (arch === "krea2") {
      const row = S.PRESTAGE_KREA_RAW;
      io.set("steps", row.steps);
      io.set("cfg", row.cfg);
      io.set("sampler_name", row.sampler_name);
      io.set("scheduler", row.scheduler);
    } else if (arch === "ideogram4") {
      io.set("steps", S.PRESTAGE_IDEOGRAM_STEPS[this.state.quality]);
      io.set("cfg", S.PRESTAGE_IDEOGRAM_ROW.cfg);
      io.set("sampler_name", S.PRESTAGE_IDEOGRAM_ROW.sampler_name);
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

  /** What a still costs and which frame of it is kept — the two things H3 has
   *  that a video render does not, because a video render keeps all of them. */
  renderStillPills() {
    const still = this.state[S.PRESTAGE_STILL_ARCH];
    const latents = S.stillLatentFrames(still.frames);

    const lengthLabel = (n) => t("{frames} frames · {latents} latent",
                                 { frames: n, latents: S.stillLatentFrames(n) });
    const length = el("button", {
      class: "mmc-pill",
      title: t("{frames} frames sampled — {latents} latent frames, of which one is "
           + "decoded. The shortest clip is the cheapest still; H3's trained range starts at "
           + "124 frames, so longer is more in-distribution and proportionally slower.",
           { frames: still.frames, latents }),
      onclick: (event) => openChoicePopover(event.currentTarget, {
        title: t("Sampled length"),
        options: S.PRESTAGE_STILL_LENGTHS.map(lengthLabel),
        value: lengthLabel(still.frames),
        onPick: (picked) => {
          const frames = S.PRESTAGE_STILL_LENGTHS.find((n) => lengthLabel(n) === picked);
          if (frames == null) return;
          still.frames = frames;
          // A shorter clip can leave the kept frame past the end of it.
          const total = S.stillLatentFrames(still.frames);
          if (still.latent_index >= total) still.latent_index = total - 1;
          if (still.latent_index < -total) still.latent_index = 0;
          this.commit();
        },
      }),
    }, [icon("clock", 16), el("span", { text: `${still.frames}f` }),
        el("span", { class: "mmc-pill-sub", text: t("{latents} latent", { latents }) })]);

    const index = stepperPill({
      value: still.latent_index, min: -latents, max: latents - 1, step: 1, width: "56px",
      title: t("Which latent frame becomes the picture. 0 is the causal first frame — the one "
             + "slice the single-image VAE was trained on, and the only one that is a function "
             + "of a single video frame. Negative counts from the end."),
      format: (n) => t("latent {n}", { n }),
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
    const existing = S.frameAsset(request, "first_frame");
    if (existing) request.assets = request.assets.filter((a) => a.handle !== existing.handle);
    request.assets.push({
      handle: S.nextHandle(request, "image"),
      kind: "image",
      role: "first_frame",
      filename: grabbed.path,
    });
    this.commit();
  }

  // ---- the hand-off ----------------------------------------------------------

  /** The chips on the finished still: one click writes it into the peer's blob
   *  as a start frame, end frame or reference. The annotated `[output]` path is
   *  the same currency the gallery attach uses — one store, no copy. */
  renderResultChips(saved) {
    const target = this.peer?.();
    if (!target) return [];
    const filename = `${saved.subfolder ? `${saved.subfolder}/` : ""}${saved.filename} [output]`;
    const chip = (role, label, title) => el("button", {
      class: "mmc-stage-chip mmc-stage-send",
      text: t(label),
      title: t("{action} on {target}.", { action: t(title), target: target.label }),
      onpointerdown: (event) => event.stopPropagation(),
      onclick: () => target.attach(role, filename),
    });
    return [
      chip("first_frame", "→ start", "Use this still as the start frame"),
      chip("last_frame", "→ end", "Use this still as the end frame"),
      chip("reference", "→ ref", "Attach this still as a reference"),
    ];
  }
}
