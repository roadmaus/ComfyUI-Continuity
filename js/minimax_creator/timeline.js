// The timeline modal: a global prompt, one canvas, and a strip of segments.
//
// The strip is the whole idea — cards laid out left to right, each as wide as
// its own duration, with the join between two of them saying whether the second
// cuts or continues. Everything inside a card is a whole generation, so opening
// one hands it to CreatorEditor unchanged: same rail, same @ prompt, same
// LoRAs, same routing badge. There is no reduced "segment UI" to keep in step
// with the node's, because there is only one editor.

import { probe, viewUrl } from "./api.js";
import { clearButton } from "./clear.js";
import { el, icon, mountOverlay, swappable } from "./dom.js";
import { CreatorEditor } from "./editor.js";
import { t } from "./i18n.js";
import { openLoras } from "./loras.js";
import { openPicker } from "./picker.js";
import { openPresetLibrary } from "./presetlib.js";
import * as P from "./presets.js";
import { PromptBox, openEditorSheet } from "./prompt.js";
import { openSettings } from "./settings.js";
import { openTrim } from "./trim.js";
import { openAspectPopover, openResolutionPopover, openChoicePopover, facesPill, stepperPill, aspectGlyph, PILL_GLYPH } from "./pills.js";
import { refine, refineButton, chosenModel as refineModel } from "./refine.js";
import { samplingBar, widgetIO } from "./sampling.js";
import { Stage } from "./stage.js";
import { weightsPill, loadCatalog, catalogFiles } from "./models.js";
import * as S from "./state.js";
import * as Turbo from "./turbo.js";
import {
  FPS, framesForSeconds, secondsForFrames, resolveCanvas, ASPECT_PRESETS, describeRatio, isTrainedLength,
} from "./canvas.js";

/** A seam blend's width as the user reads it: seconds, one decimal. */
const blendSeconds = (frames) => (frames / FPS).toFixed(1);

/** Whether a seam's sound tail is decided by its blend rather than by the
 *  piece's setting. Mirrors `compile.compile_request`: a blended seam's sound
 *  and frames are the tail of one source and cover the same instants, so the
 *  blend sets the tail outright. */
const blendSetsTail = (segment) => S.continuesAudio(segment) && S.feather(segment) > 1;


/**
 * @param {object} options
 * @param {object} options.timeline    mutated in place
 * @param {() => void} options.onCommit
 * @returns {Promise<void>} resolves when the modal closes
 */
export function openTimeline(options) {
  return new Promise((resolve) => new Timeline(options, resolve).mount());
}

/**
 * Card width from duration. Compressed rather than linear: durations run 1 s to
 * 60 s, and at any scale that keeps a 1-second card wide enough for its own
 * buttons a 60-second one would be most of a metre. Square root keeps the
 * ordering legible — a longer shot is visibly a wider card — without that.
 * The lane in the node body stays strictly proportional; that is its whole job.
 */
const cardWidth = (seconds) => 132 + Math.round(Math.sqrt(seconds) * 26);

class Timeline {
  constructor({ timeline, onCommit, edit = null, io = null }, resolve) {
    this.timeline = timeline;
    this.onCommit = onCommit;
    this.resolve = resolve;
    // The node's sampler widgets, so a card's preset can carry the row it was
    // dialled at. The modal owns none of them — the sampler belongs to the node,
    // not to one shot — so this is lent by the body that opened the strip. Absent
    // where nothing lent it, and then a speed section simply writes nowhere.
    this.io = io ?? (() => ({ value: (_name, fallback) => fallback, set: () => {} }));
    // A card to open a window on as soon as the strip is up. Set when the strip
    // was opened *by* growing a shot into it: the new card is where the writing
    // is going, so it opens ready rather than waiting to be found.
    this.openOnMount = edit;
  }

  commit() {
    S.syncTimeline(this.timeline);
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
        this.onCommit?.();
        this.renderBar();
        // The pool shelf reads these fields — a citation typed into the global
        // prompt flips a chip from idle to "everywhere" as it is written. The
        // shelf holds no caret, so rebuilding it here loses nothing.
        this.renderPool();
      },
    });
    box.value = this.timeline[key] ?? "";
    // The canvas is drag-to-pan territory in the graph; a textarea needs its
    // own pointer events.
    box.addEventListener("pointerdown", (event) => event.stopPropagation());
    return box;
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
        this.onCommit?.();
        this.renderBar();
        // A citation typed here flips a pool chip from idle to "everywhere" as
        // it is written. The shelf holds no caret, so rebuilding it here loses
        // nothing — and `renderPool` is why this cannot be a full `render`.
        this.renderPool();
      },
      attachBlocked: () => null,
      attachedLabel: () => t("Piece references"),
      onAttach: (row) => this.attachToPool(row),
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
    if (row.kind === "video") entry.track = S.DEFAULT_TRACK;
    this.timeline.assets.push(entry);
    // Not `commit`: the caret is in the box and the chip is about to be written
    // into it, so only the shelf that gained a row is redrawn.
    this.onCommit?.();
    this.renderPool();
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

    // The two audio fields H3's own prompt format has, kept side by side and
    // shorter than the prompt: they are a few sentences each, and putting them
    // under the picture description is the order the model reads them in.
    // Held rather than built inline: the refiner writes into both, and it has to
    // put the text where the user can see it rather than only into the state
    // behind them.
    this.soundscapeBox = this.textBox("soundscape", {
      className: "mmc-tl-prompt mmc-tl-small", rows: 3,
      placeholder: t("Ambience, action sounds, breathing — everything heard in the room. "
                   + "Empty leaves it to the model; write N/A for silence."),
    });
    this.musicBox = this.textBox("music", {
      className: "mmc-tl-prompt mmc-tl-small", rows: 3,
      placeholder: t("The score only the audience hears: instruments, tempo, how it moves. "
                   + "Empty leaves it to the model; write N/A for none."),
    });

    this.audioHost = el("div", { class: "mmc-tl-audio" }, [
      el("label", { class: "mmc-tl-field" }, [
        el("span", { class: "mmc-tl-field-name", text: t("overall_soundscape") }),
        this.soundscapeBox,
      ]),
      el("label", { class: "mmc-tl-field" }, [
        el("span", { class: "mmc-tl-field-name", text: t("non_diegetic_music") }),
        this.musicBox,
      ]),
    ]);

    this.poolHost = el("div", { class: "mmc-tl-pool" });
    this.barHost = el("div", { class: "mmc-tl-bar" });
    this.stripHost = el("div", { class: "mmc-tl-strip" });

    this.modal = el("div", { class: "mmc-modal mmc-tl-modal" }, [
      el("div", { class: "mmc-modal-head" }, [
        el("span", { class: "mmc-tab", "aria-selected": "true", text: t("Timeline") }),
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-tl-body" }, [
        this.promptBox.frame, this.audioHost, this.poolHost, this.barHost, this.stripHost,
      ]),
    ]);

    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(); },
    }, [this.modal]);

    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.render();
    if (this.openOnMount != null && this.timeline.segments[this.openOnMount]) {
      this.edit(this.openOnMount);
      this.openOnMount = null;
    }
  }

  close() {
    this.unmount();
    this.resolve();
  }

  // ---- render ---------------------------------------------------------------

  render() {
    // The global prompt is the same field either way but lands in a different
    // place: in front of every segment when chained, at the head of Shot 1's
    // description when not — which is where the guide puts the style and the
    // opening composition, and is worth saying because it changes how to write it.
    // A contenteditable has no `placeholder`; the box draws `data-placeholder`
    // itself while it is empty.
    this.promptBox.root.setAttribute("data-placeholder", S.isSingle(this.timeline)
      ? t("The whole piece: setting, look, who is in it. Opens Shot 1's description, so write it as the start of one.")
      : t("The whole piece: setting, look, who is in it. Added in front of every segment's own prompt."));
    this.renderPool();
    this.renderBar();
    this.renderStrip();
  }

  /**
   * The piece's reference pool: files attached to the timeline itself.
   *
   * A pool asset is cited by its @handle from any segment's text, and the
   * citation is what attaches it — the file rides into exactly the segments
   * that write the handle, and no other. That is the whole point: a character
   * sheet is attached once here instead of once per segment it appears in,
   * and every citing segment gets the same reference under the same handle.
   */
  renderPool() {
    const assets = this.timeline.assets ?? [];
    this.poolHost.replaceChildren(
      el("div", { class: "mmc-tl-pool-head" }, [
        el("span", { class: "mmc-tl-field-name", text: t("Piece references") }),
        el("span", {
          class: "mmc-tl-pool-hint",
          text: t("Attached once. Cite the @handle in the global prompt to use it in every "
                + "segment, or in a segment's own prompt to use it just there."),
        }),
        el("button", {
          class: "mmc-ghost mmc-tl-pool-add",
          title: t("Attach a reference to the whole piece — a character sheet, a location, "
               + "a voice. Cite it with its @handle in every segment where it appears."),
          onclick: () => this.addPoolAssets(),
        }, [el("span", { text: "+" }), el("span", { text: t("Add") })]),
      ]),
      ...(assets.length ? [el("div", { class: "mmc-assets" }, assets.map((a) => this.poolChip(a)))] : []),
    );
  }

  poolChip(asset) {
    const everywhere = S.poolCitedGlobally(this.timeline, asset);
    const cited = S.poolCitations(this.timeline, asset);
    // Uncited, but the same file is attached to a card under its own handle:
    // the reference *is* in use, one level down, and saying "cited nowhere yet"
    // about it is technically true and useless. Say which card and which handle
    // instead — that is the whole of what happened, and it is enough to decide
    // whether to cite the piece copy or drop it. See `S.poolDoubles`.
    const doubles = everywhere || cited.length ? [] : S.poolDoubles(this.timeline, asset);
    const where = everywhere
      ? t("everywhere — cited in the global prompt")
      : cited.length
        ? t(cited.length === 1 ? "in segment {list}" : "in segments {list}", { list: cited.join(", ") })
        : doubles.length
          ? t(doubles.length === 1
                ? "not cited — attached to segment {list} instead"
                : "not cited — attached to segments {list} instead",
              { list: doubles.map((d) => `${d.segment} (@${d.handle})`).join(", ") })
          : t("cited nowhere yet");
    const thumb = asset.kind === "image"
      ? el("img", { class: "mmc-asset-thumb", src: viewUrl(asset.filename, { preview: true }), alt: "" })
      : el("span", { class: "mmc-asset-thumb", text: asset.kind === "video" ? "▶" : "♪" });
    // The pool is the one place a swap pays the most: @char rides into every
    // segment that cites it, so re-casting the character is one click here
    // rather than a re-add and a rewrite in each of them.
    swappable(thumb, {
      title: t("Swap the file behind @{handle} — the handle stays, so every citation still fits.",
               { handle: asset.handle }),
      onclick: () => this.replacePoolAsset(asset),
    });
    return el("div", {
      // Not idle where a double exists: the file is being used, and dimming the
      // chip that says so would contradict its own text.
      class: `mmc-asset${everywhere || cited.length || doubles.length ? "" : " idle"}`,
      title: everywhere || cited.length
        ? t("{file} — {where}", { file: asset.filename, where })
        : doubles.length
          ? t("{file} — this same file is attached to segment {list} under its own handle, "
            + "so that copy is the one being used and @{handle} rides into nothing. "
            + "Cite @{handle} there and remove the card's copy to keep one reference "
            + "for the whole piece.",
              { file: asset.filename, handle: asset.handle,
                list: doubles.map((d) => `${d.segment} (@${d.handle})`).join(", ") })
          : t("{file} — no segment cites @{handle} yet, so it rides into none of them.",
              { file: asset.filename, handle: asset.handle }),
    }, [
      thumb,
      el("button", {
        class: `mmc-asset-handle mmc-tl-pool-cite mmc-tag-${S.tagIndex(asset.handle)}`,
        text: `@${asset.handle}`,
        title: t("Write @{handle} into the global prompt, so it applies to every segment.",
                 { handle: asset.handle }),
        onclick: () => this.citeInGlobal(asset),
      }),
      el("span", { class: "mmc-tl-pool-where", text: where }),
      // What of the picture is the reference — a character sheet is usually the
      // person, not the sheet's background. Images only, like the editor's own.
      ...(asset.kind === "image" ? [el("button", {
        class: "mmc-ghost",
        style: { fontSize: "11px" },
        title: t("What of this picture is the reference — narrowing it keeps the picture's "
             + "background and palette out of the video."),
        text: t(S.takes(asset)),
        onclick: (event) => this.pickPoolTakes(event.currentTarget, asset),
      })] : []),
      // What the reference is encoded at. The pool's copy is the only place a
      // shared reference can be set, so without it every citation of it is
      // stuck on the kind's default — see the editor's own button.
      ...(S.sizeable(asset) ? [el("button", {
        class: "mmc-ghost",
        style: { fontSize: "11px" },
        title: asset.kind === "video"
          ? t("match: scale to the generation's pixel area. max: core's 768 reference canvas — "
            + "more detail, and much the slower of the two. A video's reference tokens are its "
            + "whole grid once per latent frame, so at full length one clip is about as long as "
            + "the target video itself, and all of it rides through every sampling step.")
          : t("match: scale to the generation's pixel area. max: 2048 short edge — better identity, "
            + "several times slower, because reference tokens ride through every sampling step."),
        text: t(S.refSize(asset)),
        onclick: () => {
          asset.ref_size = S.refSize(asset) === "max" ? "match" : "max";
          this.commit();
        },
      })] : []),
      el("button", {
        class: "mmc-asset-x", text: "✕",
        title: cited.length
          ? t("Remove @{handle} — segments {list} still cite it and will refuse to queue "
            + "until the mentions are edited out.", { handle: asset.handle, list: cited.join(", ") })
          : t("Remove @{handle}", { handle: asset.handle }),
        onclick: () => {
          this.timeline.assets = (this.timeline.assets ?? []).filter((a) => a !== asset);
          this.commit();
        },
      }),
    ]);
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

  pickPoolTakes(anchor, asset) {
    const label = (key) => t(key);
    openChoicePopover(anchor, {
      title: t("@{handle} is a reference to", { handle: asset.handle }),
      options: S.TAKES.map(label),
      value: label(S.takes(asset)),
      onPick: (choice) => {
        const key = S.TAKES.find((k) => label(k) === choice) ?? "full";
        if (key === "full") delete asset.takes;
        else asset.takes = key;
        this.commit();
      },
    });
  }

  /** The same picker the segments use, filling the pool instead of a card. */
  async addPoolAssets() {
    const chosen = await openPicker({
      kinds: ["image", "video", "audio", "renders"],
      kind: "image",
      // The per-segment reference caps are compile's, applied where a segment
      // actually cites — the pool itself has no ceiling worth enforcing here.
      capacity: () => ({ used: 0, max: S.MAX_REF_FILES, filesLeft: S.MAX_REF_FILES }),
    });
    if (!chosen) return;
    for (const picked of chosen) {
      const entry = {
        handle: S.nextPoolHandle(this.timeline),
        kind: picked.kind,
        role: "reference",
        filename: picked.path,
        // Fidelity is why a reference is attached — same default as the editor.
        ref_size: "max",
      };
      if (picked.kind === "video") entry.track = picked.track ?? S.DEFAULT_TRACK;
      if (picked.trim) entry.trim = picked.trim;
      this.timeline.assets.push(entry);
    }
    this.commit();
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
    asset.filename = picked.path;
    if (picked.trim) asset.trim = picked.trim;
    else delete asset.trim;
    if (asset.kind === "video") asset.track = picked.track ?? S.DEFAULT_TRACK;
    this.commit();
  }

  geometry() {
    const ratio = ASPECT_PRESETS.find(([label]) => label === this.timeline.aspect)?.[1] ?? 16 / 9;
    const [width, height] = resolveCanvas(ratio, this.timeline.short_edge);
    return { width, height, ratio };
  }

  /**
   * Chained or one pass — the two ends of the same dial.
   *
   * Both are now the same statement made on every seam at once, which is why
   * the control has a third position it never asks for: a strip with some of
   * its seams merged is neither, and saying "chained" about it would be a lie
   * told by the one control on the bar that changes what all the others mean.
   * Mixed is reported, not offered — the seams themselves are where a pass is
   * made, and there is no sensible thing for clicking it to do.
   */
  renderMode() {
    const single = S.isSingle(this.timeline);
    const passes = S.passes(this.timeline);
    const mixed = !single && passes.length < this.timeline.segments.length;
    const option = (merge, label, title) => el("button", {
      class: `mmc-tl-render-opt${!mixed && merge === single ? " on" : ""}`,
      text: t(label),
      title,
      onclick: () => { if (mixed || merge !== single) this.mergeAll(merge); },
    });
    return el("div", { class: "mmc-tl-render" }, [
      option(false, "Chained",
        t("One generation per segment, joined end to end. No limit on the finished length, "
        + "and a segment can start from the previous one's last frame — but every join is a real seam.")),
      ...(mixed ? [el("span", {
        class: "mmc-tl-render-opt mmc-tl-render-mixed",
        text: t("Mixed"),
        title: t("Some of this strip's segments are merged into passes and some are "
             + "generated alone — {passes} generations for {count} segments. Merge or "
             + "split a seam to change it, or use the two ends of this control to make "
             + "the whole strip one or the other.",
             { passes: passes.length, count: this.timeline.segments.length }),
      })] : []),
      option(true, "One pass",
        t("One generation. The segments become the shots of a single description, cut times and all, "
        + "so nothing is decoded and re-encoded mid-clip and there is no seam to cross. "
        + "Everything a single pass can only have one of — mode, checkpoint, LoRAs — "
        + "becomes the timeline's.")),
    ]);
  }

  /**
   * The mode, the canvas, and the running total.
   *
   * The canvas sits here rather than on a segment because chained segments are
   * concatenated frame by frame at the end, which is only defined if they all
   * came out the same size. compile.py enforces it by compiling every segment
   * against the geometry the first one resolved; this is where the user sets it.
   */
  renderBar() {
    const single = S.isSingle(this.timeline);
    const { width, height, ratio } = this.geometry();
    const seconds = S.timelineSeconds(this.timeline);
    const frames = S.timelineFrames(this.timeline);
    const count = this.timeline.segments.length;
    // What the queue costs and what a seam sits between: the generations, not
    // the cards. They are the same number until a pass holds more than one.
    const passes = S.passes(this.timeline);
    const active = S.activeGlobalLoras(this.timeline).length;
    const idle = (this.timeline.loras?.length ?? 0) - active;
    const refined = this.timeline.segments.some((segment) => segment.refined?.body);

    this.barHost.replaceChildren(
      this.renderMode(),
      el("button", {
        class: "mmc-pill",
        title: t("Aspect ratio, shared by every segment — they are joined end to end and have to match."),
        onclick: (event) => openAspectPopover(event.currentTarget, this.timeline, () => this.commit()),
      }, [aspectGlyph(ratio, PILL_GLYPH),
          el("span", { text: this.timeline.aspect }),
          el("span", { class: "mmc-pill-sub", text: describeRatio(ratio) })]),
      el("button", {
        class: "mmc-pill",
        title: S.twoPass(this.timeline)
          ? t("Sampled at a {edge} px short edge, refined up to "
            + "{width} × {height} by a second pass — every segment alike.",
              { edge: S.sampleEdge(this.timeline), width, height })
          : t("Short edge. Lower is faster; 768 is what the open weights were trained at."),
        onclick: (event) => openResolutionPopover(
          event.currentTarget, this.timeline, () => this.geometry(), () => this.commit()),
      }, [
        icon("res", 16),
        el("span", { text: `${this.timeline.short_edge}p` }),
        el("span", { class: "mmc-pill-sub", text: S.twoPass(this.timeline)
          ? `${S.sampleEdge(this.timeline)} → ${width} × ${height}`
          : `${width} × ${height}` }),
      ]),
      // Global LoRAs sit on the bar with the canvas rather than inside a
      // segment, because that is what they are: patched onto every segment,
      // which is the whole reason to have them separately from a segment's own.
      el("button", {
        class: `mmc-pill${active ? " on" : ""}`,
        title: t("LoRAs patched onto every segment, in front of whatever that segment adds. "
             + "Where a turbo LoRA belongs."),
        onclick: () => this.openLoras(),
      }, [
        icon("effect", 16),
        el("span", { text: active
          ? t(active === 1 ? "{count} LoRA" : "{count} LoRAs", { count: active })
          : t("LoRAs") }),
        ...(idle ? [el("span", { class: "mmc-pill-sub", text: t("{idle} idle", { idle }) })] : []),
      ]),
      // Only once a seam actually carries sound *and* is the kind this governs:
      // a blended seam takes its tail from its blend, so a strip where every
      // sound seam is blended has nothing left for this to set. Until then it
      // is a control for a feature not in use — which includes all of one-pass
      // mode, where there are no seams to carry anything.
      ...(passes.slice(1).map((pass) => pass.segments[0]).some(
        (head) => S.continuesAudio(head) && !blendSetsTail(head)) ? [stepperPill({
        value: Number(this.timeline.audio_tail_s), min: 0.1, max: S.MAX_AUDIO_TAIL_S,
        step: 0.1, width: "52px", iconName: "audio",
        title: t("How much of the previous segment's sound an unblended seam inherits. "
             + "Longer costs sampling time. A blended seam takes its tail from its blend "
             + "instead, so its sound and its picture cross on the same instants."),
        format: (n) => t("{n}s tail", { n: n.toFixed(1) }),
        onChange: (next) => { this.timeline.audio_tail_s = next; this.commit(); },
      })] : []),
      // The mode belongs to a generation, and in one pass there is one for the
      // whole timeline rather than one per card.
      ...(single ? [el("span", {
        class: "mmc-pill mmc-pill-static",
        title: t("What the merged request compiles to — every shot's references and "
             + "keyframes are one pool, so this is asked of the whole timeline at once."),
      }, [el("span", { text: S.passMode(this.timeline.segments) })])] : []),
      // One call for the whole strip, not one per card: continuity across a cut
      // is only kept by a rewrite that wrote both sides of it.
      refineButton({
        run: () => this.refineAll(),
        label: refined ? t("Refine again") : t("Refine all"),
        className: "mmc-pill mmc-tl-refine",
        title: t("Rewrite {what} into the expanded "
             + "description H3 was trained to read, in one pass so the later shots keep what the "
             + "first establishes. The global prompt is rewritten too, in its own box, and still "
             + "stands in front of every shot. Everything you wrote is kept and expanded. A "
             + "rewrite is queued in place of the card's own prompt, not alongside it.",
             { what: count === 1 ? t("the shot") : t("all {count} shots", { count }) }),
      }),
      // The way back from that one press. Without it, undoing a whole-strip
      // refine means opening every card in turn.
      ...(refined ? [el("button", {
        class: "mmc-pill mmc-tl-unrefine",
        title: t("Throw every rewrite away and go back to the prompts you typed. The global "
             + "prompt, soundscape and score the refiner wrote go with them."),
        onclick: () => this.revertAll(),
      }, [el("span", { text: t("Revert all") })])] : []),
      el("div", { class: "mmc-tl-total" }, [
        el("b", { text: `${seconds.toFixed(1)} s` }),
        el("span", { text: single
          ? t(count === 1 ? "{count} shot · {frames} frames" : "{count} shots · {frames} frames",
              { count, frames })
          : t(count === 1 ? "{count} segment" : "{count} segments", { count }) }),
      ]),
      // How many sampler passes this queue costs, which is not obvious from the
      // strip: a row of cards looks like several small edits, and a merged run
      // of them is the whole stretch riding on a single denoise.
      el("div", {
        class: "mmc-note",
        title: single
          ? t("The whole timeline is generated at once, so the shots cost no more than one clip of the same length.")
          : passes.length === count
            ? t("Each segment is generated separately and they run one after another.")
            : t("One generation per pass, run one after another. A pass holding several "
              + "shots costs no more than one clip of the same length."),
      }, [
        el("span", { class: "mmc-note-key", text: t("cost") }),
        el("span", { text: t(passes.length === 1 ? "{count} generation per queue"
          : "{count} generations per queue", { count: passes.length }) }),
      ]),
      // Whatever the last refine had to say — no text encoder is chosen, or it
      // wrote a label nothing backs. Shown on the bar rather than in a card,
      // because the call was about all of them.
      ...(this.refineError ? [el("div", { class: "mmc-warn", text: this.refineError })] : []),
    );
  }

  /**
   * The strip: one enclosure per pass, seams between them.
   *
   * A pass is what one queue generates, so it is what the strip is built out of
   * — usually one card, which is what the whole strip used to be. Every card
   * sits in an enclosure whether or not it shares one, so the cards line up
   * whatever the run lengths are; the enclosure only draws itself when it holds
   * more than one, and the head rails only take up room once the strip has a
   * pass in it at all.
   */
  renderStrip() {
    const parts = [];
    const passes = S.passes(this.timeline);
    passes.forEach((pass, position) => {
      if (position > 0) parts.push(this.renderJoin(pass.start));
      parts.push(this.renderPass(pass));
    });
    // No empty case: `syncTimeline` keeps a piece at one shot or more, so the
    // strip always has a card to draw. What used to be here was the leader —
    // the unexposed head of a reel, with the two ways to begin on it — and it
    // went when the last card stopped being deletable down to nothing. The two
    // ways are still both offered, on the add tile beside the card, which is
    // where they were every other time.
    const what = S.isSingle(this.timeline) ? "Shot" : "Segment";
    // The refusal is the tooltip when there is one: the button says why it is
    // dead rather than leaving the user to find out at queue time.
    const refusal = S.addSegmentRefusal(this.timeline);
    // Two things a card can be, so two buttons in one tile. A shot is written
    // and generated; a clip is footage that already exists and is played. They
    // sit together because they occupy the same place on the strip — the
    // choice is what the next stretch of the piece is made of, not which tool
    // to reach for.
    parts.push(el("div", { class: "mmc-tl-add-pair" }, [
      el("button", {
        class: "mmc-tl-add",
        title: refusal ?? t("Add a {what} to the end", { what: t(what.toLowerCase()) }),
        disabled: refusal ? true : undefined,
        onclick: () => this.add(),
      }, [el("span", { text: "+" }), el("span", { text: t(what) })]),
      el("button", {
        class: "mmc-tl-add mmc-tl-add-clip",
        title: refusal ?? t("Cut a video you already have into the piece. It is played as it "
                          + "is — scaled to the render's size, never generated."),
        disabled: refusal ? true : undefined,
        onclick: () => this.addClip(),
      }, [el("span", { text: "+" }), el("span", { text: t("Clip") })]),
    ]));
    this.stripHost.classList.toggle(
      "has-pass", passes.some((pass) => pass.segments.length > 1));
    this.stripHost.replaceChildren(...parts);
  }

  /**
   * One pass: its cards, and — once there are several — the casing that says
   * they are one generation.
   *
   * The casing is the whole visual idea. Inside it the cards lose their own
   * borders and become panels of one strip of film, and the gaps between them
   * become the cut times the description will carry. What the rail says is
   * everything the pass can only have one of, which is exactly what merging
   * cost: one mode, one length, one generation.
   */
  renderPass(pass) {
    const cards = [];
    pass.segments.forEach((segment, offset) => {
      if (offset > 0) cards.push(this.renderCut(pass, offset));
      cards.push(this.renderCard(segment, pass.start + offset, pass));
    });
    if (pass.segments.length === 1) {
      return el("div", { class: "mmc-tl-pass" }, [
        el("div", { class: "mmc-tl-pass-head" }),
        el("div", { class: "mmc-tl-pass-cards" }, cards),
      ]);
    }

    const count = pass.segments.length;
    const frames = framesForSeconds(S.cutTimes(pass.segments).total);
    const seconds = secondsForFrames(frames);
    const problem = S.passProblem(this.timeline, pass);

    return el("div", { class: "mmc-tl-pass on" }, [
      el("div", { class: "mmc-tl-pass-head" }, [
        el("span", { class: "mmc-tl-pass-name" }, [
          icon("timeline", 13), el("span", { text: t("one pass") }),
        ]),
        el("span", {
          class: `mmc-tl-pass-len${isTrainedLength(frames) ? "" : " off-distribution"}`,
          text: t("{count} shots · {s} s", { count, s: seconds.toFixed(1) }),
          title: isTrainedLength(frames)
            ? t("{frames} frames at 24 fps, generated in one go.", { frames })
            : t("{frames} frames in one generation — outside the ~5-15 s the weights "
              + "were trained on. Split the pass to bring each side back inside it.",
                { frames }),
        }),
        el("span", { class: "mmc-tl-mode", text: S.passMode(pass.segments) }),
        el("button", {
          class: "mmc-ghost mmc-tl-pass-split",
          text: t("Split"),
          title: t("Generate these {count} shots separately again. Every cut between "
               + "them becomes a seam you can set, and each shot gets its own mode, "
               + "checkpoint and length back — nothing written is lost either way.",
                 { count }),
          onclick: () => this.splitPass(pass),
        }),
      ]),
      el("div", { class: "mmc-tl-pass-cards" }, cards),
      ...(problem ? [el("div", { class: "mmc-tl-problem" }, [
        el("span", { class: "mmc-note-key", text: t("one pass") }),
        el("span", { text: problem }),
      ])] : []),
    ]);
  }

  /**
   * The seam between two segments, and the only control on it.
   *
   * Continuing means segment N starts on segment N-1's last frame, which makes
   * it a keyframe generation — so it cannot also carry references, and the
   * switch is refused rather than silently dropping them.
   */
  /**
   * The join inside a pass: a cut, and when it happens.
   *
   * No seam to switch, because there is no seam — a cut inside one generation
   * is a line of the description, `[Shot 3] At 00:09.000, ...`, and the model
   * draws it. So what there is to show is the timestamp the compiler will
   * write, which is the one number the shot durations decide that is not
   * visible anywhere else. Timed from the pass rather than from the timeline,
   * because that is what the description says: every pass opens at 00:00.
   *
   * Clicking splits the pass here, which is the way back out.
   */
  renderCut(pass, offset) {
    const { at } = S.cutTimes(pass.segments);
    const time = S.shotTime(at[offset]);
    const n = pass.start + offset + 1;
    return el("button", {
      class: "mmc-tl-cut",
      title: t("Shot {n} cuts in {time} into this pass. "
           + 'Write its prompt as the cut — "the camera cuts to…", "the shot transitions to…" — '
           + "and the timestamp is added for you. Click to split the pass here, so the two "
           + "sides are generated separately and this cut becomes a seam.",
           { n, time }),
      onclick: () => this.splitAt(pass.start + offset),
    }, [el("span", { text: "✂" }), el("span", { text: time })]);
  }

  /**
   * The seam in front of a supplied clip, which can only run the other way.
   *
   * Everywhere else the switches say what the card after the cut starts from.
   * A clip is not generated, so there is nothing to condition — what they say
   * here is what the card *before* the cut ends on: the clip's opening frame,
   * and its opening sound. The controls stay where the seam is, because that
   * is where the cut is; only their sentence changes.
   *
   * The picture switch pins the previous generation's last frame, which makes
   * it a keyframe generation — so a shot carrying references cannot have one,
   * and the control goes dead saying which shot and why rather than letting
   * the queue refuse it.
   */
  renderClipJoin(index) {
    const clip = this.timeline.segments[index];
    const on = S.continues(clip);
    const sound = S.continuesAudio(clip);
    const blocked = S.clipSeamBlocked(this.timeline, index, "continue");
    const soundBlocked = S.clipSeamBlocked(this.timeline, index, "continue_audio");
    const width = S.feather(clip);

    return el("div", { class: "mmc-tl-seam mmc-tl-seam-clip" }, [
      el("button", {
        class: `mmc-tl-join${on ? " on" : ""}`,
        disabled: blocked ? true : undefined,
        title: blocked || (on
          ? t("Segment {n} ends on this clip's first frame, so the shot arrives where the "
            + "footage begins. Click for a hard cut.", { n: index })
          : t("Hard cut into this clip. Click to end segment {n} on the clip's first frame "
            + "instead, so the generated shot arrives where the footage begins.", { n: index })),
        onclick: blocked ? undefined : () => { clip.continue = !on; this.commit(); },
      }, [el("span", { text: on ? "↝" : "✂" }), el("span", { text: on ? t("runs in") : t("cut") })]),
      el("button", {
        class: `mmc-tl-join mmc-tl-join-sound${sound ? " on" : ""}`,
        disabled: soundBlocked ? true : undefined,
        title: soundBlocked || (sound
          ? t("Segment {n}'s sound arrives on this clip's, so the room tone and the tempo "
            + "are already the footage's when it starts. Click to let it end on its own.",
              { n: index })
          : t("Segment {n} ends on its own sound and this clip starts on the footage's. "
            + "Click to carry the clip's opening back across the cut.", { n: index })),
        onclick: soundBlocked ? undefined : () => { clip.continue_audio = !sound; this.commit(); },
      }, [icon("audio", 13), el("span", { text: sound ? t("sound") : t("silent seam") })]),
      // The blend is spent by the segment *behind* the clip — those frames are
      // re-generated at its tail and trimmed off it — so its width is bounded
      // by that card's length and not by the clip's.
      ...(on && S.maxClipFeather(this.timeline, index) > 1 ? [el("button", {
        class: `mmc-tl-join mmc-tl-join-from${width > 1 ? " on" : ""}`,
        title: width > 1
          ? t("The clip's first {s} s are blended across the end of segment {n}, so its motion "
            + "runs into the footage instead of stopping at it. That blended moment is "
            + "re-generated and removed, so segment {n} plays about {s} s shorter.",
              { s: blendSeconds(width), n: index })
          : t("Segment {n} arrives on the clip's first frame. Click to blend a moment of the "
            + "clip's opening across the end of it instead — a smoother handoff, in exchange "
            + "for segment {n} playing slightly shorter.", { n: index }),
        onclick: (event) => this.pickClipFeather(event.currentTarget, clip, index),
      }, [el("span", {
        text: width > 1 ? t("blend {s} s", { s: blendSeconds(width) }) : t("no blend"),
      })])] : []),
    ]);
  }

  /** The blend into a clip. Same grid as any seam; the ceiling is the length of
   *  the segment that pays for it. */
  pickClipFeather(anchor, clip, index) {
    const max = S.maxClipFeather(this.timeline, index);
    const label = (f) => (f === 1 ? t("None — arrive on the clip's first frame")
      : t("{name} · {s} s of motion",
          { name: t({ 5: "Short", 22: "Medium", 39: "Long" }[f] ?? "Blend"), s: blendSeconds(f) }));
    openChoicePopover(anchor, {
      title: t("Blend into this clip"),
      options: S.FEATHER_GRID.filter((f) => f <= max).map(label),
      value: label(Math.min(S.feather(clip), max)),
      onPick: (choice) => {
        const width = S.FEATHER_GRID.find((f) => label(f) === choice) ?? 1;
        if (width > 1) clip.feather = width;
        else delete clip.feather;
        this.commit();
      },
    });
  }

  renderJoin(index) {
    const segment = this.timeline.segments[index];
    if (S.isClip(segment)) return this.renderClipJoin(index);
    const on = S.continues(segment);
    const blocked = on ? null : S.blockedReason(segment, "continue");

    const sound = S.continuesAudio(segment);
    const soundBlocked = sound ? null : S.blockedReason(segment, "continue_audio");

    // Which earlier segment a live seam inherits from — the previous one unless
    // the seam names another, which is what makes a circular narrative possible:
    // segment 3 can return to segment 1's hallway after an unrelated segment 2.
    // Resolved through the passes, because the frames that exist to inherit are
    // a generation's: a source merged into the middle of a pass means the pass,
    // which is what compile.py reaches for and so what this has to say.
    const stored = S.continueSource(segment, index);
    const from = this.earlierPasses(index)
      .find((pass) => stored > pass.start && stored <= pass.end)?.end ?? stored;

    // Two switches, not one control with three states. The picture and the sound
    // cross a seam independently: a hard cut whose score keeps playing is as
    // ordinary as a match cut that resets the room tone.
    return el("div", { class: "mmc-tl-seam" }, [
      el("button", {
        class: `mmc-tl-join${on ? " on" : ""}`,
        disabled: blocked ? true : undefined,
        title: blocked || (on
          ? t("Segment {n} starts on segment {from}'s last frame. Click for a hard cut.",
              { n: index + 1, from })
          : t("Hard cut into segment {n}. Click to start it on segment {prev}'s last frame.",
              { n: index + 1, prev: index })),
        onclick: blocked ? undefined : () => { segment.continue = !on; this.commit(); },
      }, [el("span", { text: on ? "↝" : "✂" }), el("span", { text: on ? t("continues") : t("cut") })]),
      el("button", {
        class: `mmc-tl-join mmc-tl-join-sound${sound ? " on" : ""}`,
        disabled: soundBlocked ? true : undefined,
        title: soundBlocked || (sound
          ? t("Segment {n}'s sound carries on from segment {from}'s. "
            + "Click to let it start its own.", { n: index + 1, from })
          : t("Segment {n} generates its own sound from scratch. "
            + "Click to carry the last {tail}s of segment {from}'s into it.",
              { n: index + 1, tail: this.timeline.audio_tail_s, from })),
        onclick: soundBlocked ? undefined : () => { segment.continue_audio = !sound; this.commit(); },
      }, [icon("audio", 13), el("span", { text: sound ? t("sound") : t("silent seam") })]),
      // Where the seam inherits from. Only on a live seam, and only once there
      // is a choice to make: the second pass can only continue from the first,
      // and a one-option picker would only raise the question it answers.
      ...((on || sound) && this.earlierPasses(index).length >= 2 ? [el("button", {
        class: `mmc-tl-join mmc-tl-join-from${from !== index ? " on" : ""}`,
        title: t("What continues across this seam is segment {from}'s last {what}. "
             + "Click to inherit from a different earlier segment — a story returning to "
             + "segment 1 after an unrelated shot continues from segment 1.",
             { from, what: t(on && sound ? "frame and sound" : on ? "frame" : "sound") }),
        onclick: (event) => this.pickContinueFrom(event.currentTarget, segment, index),
      }, [el("span", { text: t("from #{from}", { from }) })])] : []),
      // How much of the source's tail crosses the seam. Only on a live picture
      // seam: the width is a property of the inherited frames, and the classic
      // last-frame seam is what it says until widened. The chip and its picker
      // speak in seconds of motion — the frame counts are the encoder's
      // business, not the user's.
      ...(on ? [el("button", {
        class: `mmc-tl-join mmc-tl-join-from${S.feather(segment) > 1 ? " on" : ""}`,
        title: (S.feather(segment) > 1
          ? t("The last {s} s of segment {from}'s motion "
            + "carries across this cut, so the movement flows through instead of restarting "
            + "from a still. That blended moment is redone at the start of segment {n} "
            + "and removed from the final video, so it plays about "
            + "{s} s shorter than its set length.",
              { s: blendSeconds(S.feather(segment)), from, n: index + 1 })
          : t("This cut picks up from segment {from}'s last frame. Click to blend a moment "
            + "of its motion across instead — a smoother handoff, in exchange for segment "
            + "{n} playing slightly shorter.", { from, n: index + 1 }))
          // The sound rides the same inherited instants as the frames, so the
          // blend sets the tail rather than the piece's setting. Said here
          // because this chip is where the number that wins is on screen.
          + (blendSetsTail(segment)
            ? " " + t("Its sound carries the same {s} s, so the soundtrack and the "
                    + "picture cross the seam on the same instants.",
                      { s: blendSeconds(S.feather(segment)) })
            : ""),
        onclick: (event) => this.pickFeather(event.currentTarget, segment, index),
      }, [el("span", {
        text: S.feather(segment) > 1
          ? t("blend {s} s", { s: blendSeconds(S.feather(segment)) }) : t("no blend"),
      })])] : []),
      // The third answer to what happens here, and the only structural one: no
      // seam at all, because the two sides are one generation. Kept apart from
      // the two switches above rather than folded in as a third state of the
      // picture one — those say how this seam behaves, this one says whether
      // there is a seam to behave.
      //
      // Absent behind supplied footage: a clip is played rather than
      // generated, so there is no generation on the far side of this cut for
      // this card to be folded into.
      ...(S.isClip(this.timeline.segments[index - 1]) ? [] : [el("button", {
        class: "mmc-tl-join mmc-tl-join-merge",
        title: t("Generate segment {n} in the same pass as the one before it: one "
             + "generation, with this cut written into its description for the model to "
             + "draw. Nothing is decoded and re-encoded here, so there is no seam to "
             + "cross — in exchange the two shots share one mode, one checkpoint and "
             + "one LoRA stack. Everything you set here is kept, and comes "
             + "back if you split the pass again.", { n: index + 1 }),
        onclick: () => this.mergeAt(index),
      }, [el("span", { text: "▤" }), el("span", { text: t("one pass") })])]),
    ]);
  }

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

  /** Every shot of a pass back to a generation of its own. */
  splitPass(pass) {
    for (let index = pass.start + 1; index < pass.end; index += 1) {
      delete this.timeline.segments[index].merge;
    }
    this.commit();
  }

  /** The bar's two ends: the whole strip as one pass, or none of it.
   *
   *  Written to `render` as well as to the flags, because the flags cannot say
   *  it on a strip of one: a merge flag is a statement about the seam in front
   *  of a card, and card 1 has no seam. `syncTimeline` re-derives `render` from
   *  the flags the moment there are two cards and agrees with what is set here,
   *  so the only strip this decides on its own is the one with no seam in it —
   *  where it is still a real choice, and the only thing that says whether the
   *  card is a shot of one pass or a pass of its own. */
  mergeAll(merge) {
    this.timeline.render = merge ? "single" : "chained";
    this.timeline.segments.forEach((segment, index) => {
      if (!index) return;
      if (merge) segment.merge = true;
      else delete segment.merge;
    });
    this.commit();
  }

  /** The seam's width. The options are the runs the video VAE can encode
   *  standalone (state.FEATHER_GRID), named by what the user hears and sees:
   *  how long a moment of motion crosses the cut. */
  pickFeather(anchor, segment, index) {
    const max = S.maxFeather(segment);
    const label = (f) => (f === 1 ? t("None — start from the last frame")
      : t("{name} · {s} s of motion",
          { name: t({ 5: "Short", 22: "Medium", 39: "Long" }[f] ?? "Blend"), s: blendSeconds(f) }));
    openChoicePopover(anchor, {
      title: t("Blend into segment {n}", { n: index + 1 }),
      options: S.FEATHER_GRID.filter((f) => f <= max).map(label),
      value: label(Math.min(S.feather(segment), max)),
      onPick: (choice) => {
        const width = S.FEATHER_GRID.find((f) => label(f) === choice) ?? 1;
        if (width > 1) segment.feather = width;
        else delete segment.feather;
        this.commit();
      },
    });
  }

  /** The passes that finish before the segment at `index` starts — the ones
   *  whose frames exist by the time this seam is crossed. */
  earlierPasses(index) {
    return S.passes(this.timeline).filter((pass) => pass.end <= index);
  }

  /**
   * The seam's source, chosen from the passes before this one.
   *
   * Passes rather than segments, because a pass is one generation and what it
   * leaves behind is one clip: a shot merged into the middle of one has no last
   * frame of its own to inherit. Stored as the number of the pass's last
   * segment, which is the frame it means and the card the user can point at.
   */
  pickContinueFrom(anchor, segment, index) {
    const earlier = this.earlierPasses(index);
    const options = earlier.map((pass, position) => {
      const previous = position === earlier.length - 1;
      if (pass.segments.length > 1) {
        return previous
          ? t("segments {first}-{last}, one pass — previous",
              { first: pass.start + 1, last: pass.end })
          : t("segments {first}-{last}, one pass", { first: pass.start + 1, last: pass.end });
      }
      return previous ? t("segment {n} — previous", { n: pass.end }) : t("segment {n}", { n: pass.end });
    });
    // Whatever is stored resolves to the pass that holds it, which is the frame
    // compile.py will actually reach for.
    const source = S.continueSource(segment, index);
    const current = earlier.findIndex((pass) => source > pass.start && source <= pass.end);

    openChoicePopover(anchor, {
      title: t("Segment {n} continues from", { n: index + 1 }),
      options,
      value: options[current >= 0 ? current : earlier.length - 1],
      onPick: (choice) => {
        const picked = earlier[options.indexOf(choice)];
        if (!picked) return;
        // The previous pass is the default, so choosing it is choosing to store
        // nothing — an absent key survives reordering with no bookkeeping.
        if (picked === earlier[earlier.length - 1]) delete segment.continue_from;
        else segment.continue_from = picked.end;
        this.commit();
      },
    });
  }

  /**
   * A supplied clip, as a card.
   *
   * The same shape as a shot's card and deliberately not the same skin: it is
   * not generated, so the things a shot's card carries — a prompt, a mode, a
   * reference count — have nothing to say here. What it shows instead is the
   * file, the window that plays, and whether its sound is on.
   */
  renderClipCard(segment, index) {
    const seconds = S.clipSeconds(segment);
    const name = (segment.filename || "").split("/").pop();
    const trimmed = Boolean(segment.trim);
    const scaled = this.geometry();

    return el("div", {
      class: "mmc-tl-card mmc-tl-clip",
      style: { width: `${cardWidth(seconds)}px` },
      ondblclick: () => this.editClip(index),
    }, [
      el("div", { class: "mmc-tl-card-head" }, [
        el("span", { class: "mmc-tl-index", text: String(index + 1) }),
        el("span", {
          class: "mmc-tl-dur",
          text: `${seconds.toFixed(1)} s`,
          // No off-distribution mark: nothing is sampled, so the trained
          // length has nothing to say about a clip.
          title: trimmed
            ? t("{s} s of {file}, from {start} s.",
                { s: seconds.toFixed(1), file: name, start: segment.trim.start.toFixed(2) })
            : t("All {s} s of {file}.", { s: seconds.toFixed(1), file: name }),
        }),
        el("span", { class: "mmc-tl-mode mmc-tl-clip-tag", text: t("clip") }),
      ]),
      el("div", { class: "mmc-tl-card-prompt mmc-tl-clip-name", text: name, title: segment.filename }),
      el("div", {
        class: "mmc-tl-card-meta",
        title: t("Supplied footage is played as it is — scaled to the render's size and "
               + "spliced in without being generated. It has not been through the model, "
               + "so its colour and grain will not match the shots around it."),
        text: [
          segment.width && segment.height ? `${segment.width}×${segment.height} → ${scaled.width}×${scaled.height}` : null,
          S.clipSound(segment) ? t("sound") : t("silent"),
        ].filter(Boolean).join(" · "),
      }),
      el("div", { class: "mmc-tl-card-foot" }, [
        el("button", { class: "mmc-tl-edit", text: t("Trim"), onclick: () => this.editClip(index) }),
        el("button", {
          class: `mmc-ghost${S.clipSound(segment) ? " on" : ""}`,
          title: segment.has_audio === false
            ? t("This clip has no soundtrack.")
            : S.clipSound(segment) ? t("Playing with its own sound. Click to mute it.")
              : t("Playing silent. Click to use the clip's own sound."),
          disabled: segment.has_audio === false || undefined,
          onclick: () => {
            segment.sound = !S.clipSound(segment);
            this.commit();
          },
        }, [icon("audio", 13)]),
        el("button", {
          class: "mmc-ghost", text: "◀", title: t("Move earlier"),
          disabled: index === 0 || undefined,
          onclick: () => this.move(index, -1),
        }),
        el("button", {
          class: "mmc-ghost", text: "▶", title: t("Move later"),
          disabled: index === this.timeline.segments.length - 1 || undefined,
          onclick: () => this.move(index, 1),
        }),
        el("button", {
          class: "mmc-asset-x", text: "✕", title: t("Remove this clip"),
          onclick: () => this.remove(index),
        }),
      ]),
    ]);
  }

  renderCard(segment, index, pass) {
    if (S.isClip(segment)) return this.renderClipCard(segment, index);
    // Whether this card is a generation or a shot inside one. Everything below
    // that used to ask the timeline's render mode is really asking this.
    const shared = pass.segments.length > 1;
    // In a pass the shot does not snap to the grid on its own — the pass's
    // total does — so the card shows what the user set and the rail above it
    // shows the truth.
    const frames = framesForSeconds(segment.duration_s);
    const seconds = shared ? Number(segment.duration_s) || 0 : secondsForFrames(frames);
    // The segment's own references plus the piece references its text cites —
    // both ride into this generation, so the card counts both.
    const refs = S.references(segment).length + S.citedPool(segment).length;
    const loras = S.activeLoras(segment).length;
    const typed = (segment.prompt || "").trim();
    const rewrite = segment.refined?.body?.trim();
    const using = rewrite && segment.refined.enabled !== false;
    // The typed sentence is what the user recognises the card by, so it stays
    // the caption and the rewrite is only marked — a paragraph of generated
    // prose on a 160 px card says less about which shot this is, not more. A
    // card refined from nothing falls back to the rewrite, which is then the
    // only description it has.
    const prompt = typed || rewrite || "";

    const meta = [];
    if (refs) meta.push(t(refs === 1 ? "{count} ref" : "{count} refs", { count: refs }));
    if (loras) meta.push(t(loras === 1 ? "{count} LoRA" : "{count} LoRAs", { count: loras }));
    if (rewrite) meta.push(using ? t("refined") : t("refined (off)"));

    // The card's half of the face pass, and only while the piece is running
    // one: a switch for something that is not happening is a switch that lies.
    // Two states, because with the piece on, "on" and "inherit" are the same
    // thing — what a card gets to say is that *this* shot does not need it.
    const repaired = S.faceOn(this.timeline, segment);
    const faceChip = this.timeline.face?.on ? el("button", {
      class: `mmc-tl-card-face${repaired ? " on" : ""}`,
      text: repaired ? t("face") : t("no face"),
      title: repaired
        ? t("This shot's face is re-drawn after it renders. Click to leave it alone.")
        : t("This shot is left as it renders. Click to have its face re-drawn."),
      onclick: (event) => {
        event.stopPropagation();
        if (repaired) segment.face = "off";
        else delete segment.face;
        this.commit();
      },
    }) : null;

    return el("div", {
      class: "mmc-tl-card",
      style: { width: `${cardWidth(seconds)}px` },
      // Double-click anywhere on the card, because "Edit" is a small target and
      // opening a segment is the thing you do most in here.
      ondblclick: () => this.edit(index),
    }, [
      el("div", { class: "mmc-tl-card-head" }, [
        el("span", { class: "mmc-tl-index", text: String(index + 1) }),
        // The off-distribution mark belongs to whatever is actually generated in
        // one go. Alone, that is this card; in a pass it is the pass, and
        // marking every card would say it about the wrong thing — the rail
        // carries it there instead.
        el("span", {
          class: `mmc-tl-dur${shared || isTrainedLength(frames) ? "" : " off-distribution"}`,
          text: `${segment.duration_s} s`,
          title: shared
            ? t("{s} s of this pass — the frame count is the pass's.", { s: segment.duration_s })
            : isTrainedLength(frames)
              ? t("{frames} frames at 24 fps", { frames })
              : t("{frames} frames — outside the ~5–15 s the weights were trained on.", { frames }),
        }),
        // The mode is a property of the generation, and a pass holding several
        // shots has one of those for all of them — so it moves to the rail.
        ...(shared ? [] : [el("span", { class: "mmc-tl-mode", text: S.mode(segment) })]),
      ]),
      // Dimmed while a rewrite stands in for it, the same way the editor dims the
      // box this caption is showing: the card would otherwise read as if the
      // sentence under it were what this shot queues.
      el("div", {
        class: `mmc-tl-card-prompt${prompt ? "" : " empty"}${using && typed ? " superseded" : ""}`,
        text: prompt || t("No prompt yet"),
        title: using && typed ? t("Not queued — this card's rewrite is. Open it to read or revert.") : "",
      }),
      ...(meta.length || faceChip
        ? [el("div", { class: "mmc-tl-card-meta" }, [
            ...(meta.length ? [el("span", { text: meta.join(" · ") })] : []),
            ...(faceChip ? [faceChip] : []),
          ])]
        : []),
      el("div", { class: "mmc-tl-card-foot" }, [
        el("button", { class: "mmc-tl-edit", text: t("Edit"), onclick: () => this.edit(index) }),
        el("button", {
          class: "mmc-ghost", text: "◀", title: t("Move earlier"),
          disabled: index === 0 || undefined,
          onclick: () => this.move(index, -1),
        }),
        el("button", {
          class: "mmc-ghost", text: "▶", title: t("Move later"),
          disabled: index === this.timeline.segments.length - 1 || undefined,
          onclick: () => this.move(index, 1),
        }),
        // Weighed against this card's own length, not a fresh card's: a copy of
        // a twenty-second shot costs twenty seconds of the budget.
        el("button", {
          class: "mmc-ghost", text: "⧉",
          title: S.addSegmentRefusal(this.timeline, segment.duration_s) ?? t("Duplicate"),
          disabled: S.addSegmentRefusal(this.timeline, segment.duration_s) ? true : undefined,
          onclick: () => this.duplicate(index),
        }),
        el("button", {
          class: "mmc-asset-x", text: "✕", title: t("Remove this segment"),
          onclick: () => this.remove(index),
        }),
      ]),
    ]);
  }

  // ---- actions ---------------------------------------------------------------

  add() {
    if (S.addSegmentRefusal(this.timeline)) return;
    this.timeline.segments.push(S.continuingSegment());
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
  async addClip() {
    if (S.addSegmentRefusal(this.timeline)) return;
    const chosen = await openPicker({
      kinds: ["video", "renders"], kind: "video", single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    if (!chosen?.length) return;

    const probed = await probe(chosen[0].path).catch(() => ({}));
    const segment = S.clipSegment({
      filename: chosen[0].path,
      duration: probed.duration ?? 0,
      width: probed.width ?? 0,
      height: probed.height ?? 0,
      // null means the probe could not answer; the switch stays available and
      // the backend refuses a clip that turns out to be silent, which is a
      // better failure than greying out a control on a guess.
      hasAudio: probed.hasAudio !== false,
    });
    // Asked again with the card's real length, which is the file's rather than
    // a default: a ten-minute clip and a two-second one are not the same ask
    // of the frame budget.
    const refusal = S.addSegmentRefusal(this.timeline, S.clipSeconds(segment));
    if (refusal) {
      this.refineError = refusal;
      this.render();
      return;
    }
    if (!segment.duration_s) {
      this.refineError = t("Could not read how long {file} is — a clip card needs its length.",
                           { file: chosen[0].path });
      this.render();
      return;
    }
    this.timeline.segments.push(segment);
    this.commit();
  }

  /** The clip's window, through the same trim editor a reference video uses. */
  async editClip(index) {
    const segment = this.timeline.segments[index];
    const picked = await openTrim({
      path: segment.filename,
      kind: "video",
      trim: segment.trim ?? null,
      // A clip card *is* the picture — its sound rides with it and is switched
      // on the card — so there is no track to choose here, unlike a reference
      // clip, which can be cited for one stream or the other.
      showTrack: false,
    });
    if (!picked) return;
    if (picked.trim) segment.trim = picked.trim;
    else delete segment.trim;
    this.commit();
  }

  duplicate(index) {
    if (S.addSegmentRefusal(this.timeline, this.timeline.segments[index].duration_s)) return;
    this.timeline.segments.splice(index + 1, 0, S.cloneSegment(this.timeline.segments[index]));
    // Every segment after the insertion moved down one card; a seam naming one
    // of them follows it. Nothing pointed at the clone a moment ago, and a seam
    // naming the original still does.
    S.remapContinueFrom(this.timeline, (n) => (n > index + 1 ? n + 1 : n));
    this.commit();
  }

  remove(index) {
    this.timeline.segments.splice(index, 1);
    // A seam that named the removed segment falls back to the previous one;
    // one naming a later segment follows it up a card.
    S.remapContinueFrom(this.timeline,
      (n) => (n === index + 1 ? null : n > index + 1 ? n - 1 : n));
    this.commit();
  }

  /**
   * Reorder. A segment carries its continuation flag with it, and `syncTimeline`
   * clears it off whatever ends up first — a segment moved to the front has
   * nothing left to continue from. A named seam source follows the card it
   * points at, and `syncTimeline` likewise drops any source the swap carried
   * to or past its own seam.
   */
  move(index, delta) {
    const target = index + delta;
    const segments = this.timeline.segments;
    if (target < 0 || target >= segments.length) return;
    [segments[index], segments[target]] = [segments[target], segments[index]];
    S.remapContinueFrom(this.timeline,
      (n) => (n === index + 1 ? target + 1 : n === target + 1 ? index + 1 : n));
    this.commit();
  }

  /**
   * The LoRA manager, editing the timeline's own list.
   *
   * Handed the checkpoints the segments actually route to rather than one: a
   * global LoRA is patched onto every segment and the segments need not agree,
   * so "idle" here means it lands on none of them, not on the wrong one.
   */
  async openLoras() {
    await openLoras({
      state: this.timeline,
      targets: S.timelineCheckpoints(this.timeline),
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
  async refineAll() {
    this.refineError = null;
    try {
      const result = await refine({
        kind: "timeline",
        data: JSON.parse(S.serializeTimeline(this.timeline)),
      });
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
      // The shelf as well as the strip: writing `@ref-1` in this card is what
      // makes the pool chip say "in segment 3", and the shelf is the only place
      // that fact is ever shown. Redrawn on the card's own commits rather than
      // waiting for the window to close, because a readout that lags the thing
      // it reports on reads as one that does not work — the chip sat on "cited
      // nowhere yet" for the whole of the edit that cited it. It holds no caret
      // and nothing focusable, so rebuilding it under an open window costs
      // nothing. See `renderPool` and `S.poolCitations`.
      onCommit: () => { this.onCommit?.(); this.renderStrip(); this.renderPool(); },
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
        capture: () => ({
          data: P.captureShot(this.timeline, index, this.io()),
          defaultName: (segment.prompt || "").trim().split("\n")[0].slice(0, 48),
        }),
        apply: (body, keys, from) => {
          P.applyToShot(body, keys, segment, this.io(), { from });
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
 * The sampler widgets are ComfyUI's own, hidden and re-drawn as pills. This node
 * owns the sampler because it writes the KSampler into the graph, but that is no
 * reason for half the node to be stock widgets and half of it to be this. The
 * widgets still hold the values — they are what `graphToPrompt` reads — so the
 * pills only read and write `widget.value`, exactly as the JSON blob does.
 */
export class TimelineBody {
  /** `preStage` and `face` are wiring the node supplies — see minimax_creator.js.
   *  `face` is where the piece-view pin is kept, which is a preference about
   *  this node rather than anything the render reads, so it lives on the node
   *  and not in the blob. */
  constructor({ read, write, widgets = {}, onWidgetChange, nodeId,
                preStage = null, face = null }) {
    this.read = read;
    this.write = write;
    this.widgets = widgets;
    this.onWidgetChange = onWidgetChange;
    this.nodeId = nodeId;
    this.preStage = preStage;
    this.face = face;
    this.timeline = S.parseTimeline(read());
    // The face's editor, when the piece is one shot and the face is wearing
    // one. Null the rest of the time — see `loneShot`.
    this.faceEditor = null;

    // The same stage the Creator has, showing the same thing: a timeline is one
    // clip, and what it is making is one picture whatever the strip looks like.
    // attach() floats it beside the node in a Satellite; it never mounts here.
    this.root = el("div", { class: "mmc-root" });
    this.stage = new Stage({
      nodeId,
      // Which generation the queue is on, said over the preview: the strip runs
      // for minutes and a bare step count says nothing about where in the
      // piece the sampler is. Counted in passes, because that is what the
      // announcing node is one of. Read late — the strip may grow between
      // queueing and the announce.
      segmentLabel: (index) => t("Pass {n} of {count}",
        { n: index, count: S.passes(this.timeline).length }),
      // View-only: a timeline's references live on its segments, so a pick from
      // here would have no card to land on. The Creator attaches; this browses.
      onGallery: () => openPicker({
        kinds: ["renders"],
        kind: "renders",
        viewOnly: true,
        capacity: () => ({ used: 0, max: 0, filesLeft: 0 }),
      }),
    });
    loadCatalog(() => this.adoptWeights());
    this.render();
  }

  destroy() {
    this.stage?.destroy();
    this.laneFit?.disconnect();
    this.dropFaceEditor();
  }

  /** See `CreatorEditor.adoptWeights` — same rescue, same reason. */
  adoptWeights() {
    if (S.guessModels(this.timeline.models, catalogFiles())) this.commit();
    else this.render();
  }

  /** Re-read the widget. Loading a saved workflow assigns widget values after
   *  the node is created, so the body built in `nodeCreated` saw the default. */
  reload() {
    this.timeline = S.parseTimeline(this.read());
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
    if (!this.face || !this.loneShot()) return null;
    return {
      shown: () => this.showsStrip(),
      toggle: () => { this.face.pin(!this.face.pinned()); this.render(); },
    };
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
      onCommit: () => this.commit(),
      samplingWidgets: this.widgets,
      onWidgetChange: this.onWidgetChange,
      nodeId: this.nodeId,
      // The node's, so a render lands in the satellite the body already owns
      // rather than in a second stage listening for the same previews.
      stage: this.stage,
      setRoute: (route) => { this.timeline.models.route = route; this.commit(); },
      preStage: this.preStage,
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
      afterPanel: () => [this.renderGrow()],
    });
    return this.faceEditor;
  }

  /**
   * Unexposed film: the stretch after the shot, where the next one goes.
   *
   * The leader is the unexposed head of a reel, and this is the same idea one
   * card later: a perforation rail across the body, meaning film that has not
   * been shot. The strip used to draw a leader of its own for a piece with
   * nothing on it; a piece cannot be empty any more, so this is the only place
   * the rail is left — and the only place it was ever really needed.
   *
   * Quiet on purpose. Most renders are one shot, and a control that announced
   * itself would be wrong nine times out of ten. It is the only thing between
   * the prompt and the sampler row, on a face read top to bottom.
   */
  renderGrow() {
    const full = this.timeline.segments.length >= S.MAX_SEGMENTS;
    return el("button", {
      class: "mmc-tl-grow",
      disabled: full,
      title: full
        ? t("This piece is at its limit of {count} shots.", { count: S.MAX_SEGMENTS })
        : t("Add a second shot and open the strip. One shot or twenty, it is the same node."),
      onclick: () => this.growIntoStrip(),
    }, [el("span", { class: "mmc-tl-grow-mark", text: "+" }),
        el("span", { text: t("Write the next shot") })]);
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
    this.timeline.segments.push(S.continuingSegment());
    this.commit();
    this.open({ edit: this.timeline.segments.length - 1 });
  }

  commit() {
    S.syncTimeline(this.timeline);
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
  presetTarget() {
    return {
      scope: "piece",
      label: t("this piece"),
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
    });
  }

  value(name, fallback) {
    const widget = this.widgets[name];
    return widget ? widget.value : fallback;
  }

  /** See `sampling.widgetIO`. */
  widgetIO() {
    return widgetIO(() => this.widgets, () => this.onWidgetChange?.());
  }

  /** Write through to the real widget, callback included — some of them (the
   *  seed's after-generate control) hang behaviour off it. */
  set(name, value) {
    const widget = this.widgets[name];
    if (!widget) return;
    widget.value = value;
    widget.callback?.(value);
    this.onWidgetChange?.();
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
      // and sampler row, and its `afterPanel` puts the unexposed film between
      // the last two.
      if (this.root.firstChild !== editor.root) this.root.replaceChildren(editor.root);
      // The editor's root is a body in its own right, padding and all. Hosting
      // it inside another one would inset the face twice — which is a narrower
      // face than the strip's on a node of the same width, and it showed as the
      // sampler pills wrapping a row earlier here than there.
      this.root.classList.add("hosting");
      this.laneFit?.disconnect();
      return;
    }
    this.root.classList.remove("hosting");
    this.dropFaceEditor();
    // Same order as the Creator: the rail, what you are asking for, then how it
    // is run. The picture is beside the node, in the satellite.
    this.root.replaceChildren(this.renderRail(), this.renderPanel(), this.renderSampling());
    // The reel is the one part of the body whose reading depends on the width
    // it ended up with, so it is fitted after it is in the document — once now,
    // and again from its own observer whenever the node is resized.
    this.laneFit?.disconnect();
    this.laneFit?.observe(this.lane);
    this.fitLane();
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

    return el("div", { class: "mmc-rail" }, [
      el("div", { class: "mmc-rail-group" }, [
        ...[["image", "Add image", "image"], ["video", "Add video", "video"],
            ["audio", "Add audio", "audio"]].map(([kind, label, iconName]) =>
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
      kinds: [kind, "renders"],
      kind,
      capacity: () => ({ used: 0, max: S.MAX_REF_FILES, filesLeft: S.MAX_REF_FILES }),
    });
    if (!chosen?.length) return;
    for (const picked of chosen) {
      const entry = {
        handle: S.nextPoolHandle(this.timeline),
        kind: picked.kind,
        role: "reference",
        filename: picked.path,
        ref_size: "max",
      };
      if (picked.kind === "video") entry.track = picked.track ?? S.DEFAULT_TRACK;
      if (picked.trim) entry.trim = picked.trim;
      this.timeline.assets.push(entry);
    }
    this.commit();
  }

  async manageLoras() {
    await openLoras({
      state: this.timeline,
      targets: S.timelineCheckpoints(this.timeline),
      onChange: () => this.commit(),
    });
    this.commit();
  }

  renderPanel() {
    const segments = this.timeline.segments;
    const single = S.isSingle(this.timeline);
    const passes = S.passes(this.timeline);
    const seconds = S.timelineSeconds(this.timeline);
    const [width, height] = resolveCanvas(
      ASPECT_PRESETS.find(([label]) => label === this.timeline.aspect)?.[1] ?? 16 / 9,
      this.timeline.short_edge);
    const prompt = (this.timeline.prompt || "").trim();
    const globalLoras = S.activeGlobalLoras(this.timeline).length;
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
        // The render mode leads, because it is the one thing about this node
        // that changes what all the other numbers mean.
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
        el("span", { class: "mmc-pill mmc-pill-static", title: t("The finished clip's length at 24 fps") }, [
          icon("clock", 16),
          el("span", { text: `${seconds.toFixed(1)} s` }),
        ]),
        el("span", {
          class: "mmc-pill mmc-pill-static",
          title: single
            ? t("The canvas the one generation runs at.")
            : t("Shared by every segment — they are joined end to end and have to match."),
        }, [
          el("span", { text: this.timeline.aspect }),
          el("span", { class: "mmc-pill-sub", text: `${width} × ${height}` }),
        ]),
        // Only when there are any: an empty pill would say the timeline has a
        // LoRA feature, which is the modal's job to say, not the node's.
        ...(globalLoras ? [el("span", {
          class: "mmc-pill mmc-pill-static",
          title: single
            ? t("Patched onto the one generation, in front of whatever the shots add.")
            : t("Patched onto every segment, in front of whatever that segment adds."),
        }, [
          icon("effect", 16),
          el("span", { text: t(globalLoras === 1 ? "{count} LoRA" : "{count} LoRAs", { count: globalLoras }) }),
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
        ...(this.pieceView() ? [this.renderPieceViewPill()] : this.renderHeldPieceViewPill()),
        ...(this.preStage ? [this.renderPreStagePill()] : []),
      ]),
    ]);
  }

  /** The way back to the shot, on the strip face. Drawn only while there is one
   *  shot to go back to — see `pieceView`. Deliberately the pill the shot face
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
    if (!this.face || segments.length !== 1 || S.isClip(segments[0])) return [];
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
        const what = S.isClip(segment) ? t("clip") : S.mode(segment);
        // A seam only exists in front of a pass. Inside one the cut is a line
        // of the description, so the block reads as a shot rather than a join.
        const continues = !offset && index > 0 && S.continues(segment);
        // Crowded, the reel marks the exception rather than the rule: a strip
        // whose seams nearly all continue is one unbroken take, and colouring
        // every one of them says only that the feature exists. The hard cut is
        // the thing that happens rarely, so the hard cut is what gets drawn —
        // as a real break in the band, which is what it is.
        const cut = !offset && index > 0 && !continues;
        return el("div", {
          class: `mmc-tl-tick${continues ? " on" : ""}${cut ? " cut" : ""}`,
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
    const crowded = per < 30;
    lane.classList.toggle("dense", dense);
    lane.classList.toggle("crowded", crowded);

    if (!crowded) {
      // Above that, each block answers for itself: whether the lane is a strip
      // of tiles or a band is one decision about the whole lane, but what fits
      // on a block is a question about that block. A three-second shot beside a
      // twenty is a quarter of its width, and giving both the same labels is
      // how the short one ends up with a clipped one.
      this.edge.replaceChildren();
      // Measured from the block at full label, never from the block as it was
      // left last time: a hidden label makes a block narrower, so measuring the
      // trimmed one would find it narrower still and never give the label back.
      for (const block of blocks) block.classList.remove("narrow", "bare");
      for (const block of blocks) {
        const room = block.getBoundingClientRect().width;
        block.classList.toggle("narrow", room < 46);
        // What the number itself needs — shot 7 fits where shot 47 does not,
        // and dropping a digit that would have fitted reads as a blank block
        // rather than as a tight one.
        const digits = block.querySelector(".mmc-tl-tick-n")?.textContent.length ?? 2;
        block.classList.toggle("bare", room < 16 + 9 * digits);
      }
      return;
    }

    // Edge code: a numeral every few shots, at the widest cadence that still
    // keeps two numbers well clear of each other. Sparse on purpose — its job
    // is to make the band countable, not to name every block on it.
    const step = [1, 2, 5, 10, 20, 25, 50].find((n) => per * n >= 56) ?? 100;
    const origin = lane.getBoundingClientRect().left;
    this.edge.replaceChildren(...blocks.flatMap((block, index) => (index % step ? [] : [
      el("span", {
        class: "mmc-tl-edge-n",
        style: { left: `${Math.round(block.getBoundingClientRect().left - origin)}px` },
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
   * A finished pre-stage still, pushed into the timeline by the neighbour's
   * result chips. The roles land where one pass would put them — a start frame
   * opens shot 1, an end frame closes the last shot, a reference joins shot 1 —
   * under each shot's own capacity and exclusivity rules. Returns a refusal
   * message, or null on success.
   */
  attachFromPreStage({ role, filename }) {
    const shots = this.timeline.segments;
    const index = role === "last_frame" ? shots.length - 1 : 0;
    const segment = shots[index];
    const where = t("segment {n}", { n: index + 1 });
    if (role === "reference") {
      const blocked = S.blockedReason(segment, "reference");
      if (blocked) return t("{where}: {blocked}", { where, blocked });
      const { used, max, filesLeft } = S.capacity(segment, "image");
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
   * The sampler row, shared with the Creator node — see `sampling.js`. Both
   * nodes own their sampler and declare the same widgets, so neither draws its
   * own version of this.
   */
  renderSampling() {
    return samplingBar({
      widgets: this.widgets,
      value: (name, fallback) => this.value(name, fallback),
      set: (name, value) => this.set(name, value),
      // Several generations mean the seed and the step count are asked of each
      // of them; one generation means they are asked once. The passes are the
      // generations, whatever the cards look like.
      perSegment: S.passes(this.timeline).length > 1,
      // The turbo switch, on the timeline's global stack: a speed-up belongs to
      // the run, which is the whole reason the global stack exists.
      turbo: Turbo.turboPills({
        container: this.timeline,
        ...this.widgetIO(),
        onCommit: () => this.commit(),
      }),
      // A chained timeline legitimately runs some shots on one checkpoint and
      // some on the other, so the pill is asked about the set rather than
      // about one — a Ref2VA it never reaches for is not missing.
      trailing: [
        facesPill({ target: this.timeline, commit: () => this.commit() }),
        weightsPill({
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
