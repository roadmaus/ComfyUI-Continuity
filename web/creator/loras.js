// The LoRA manager: the full-screen modal behind the rail's third tool.
//
// Unlike the asset picker this edits in place rather than returning a selection.
// Adding a LoRA is only the first of three decisions — strength and which
// checkpoint it belongs to are the other two — and a pick-then-configure flow
// would have meant closing the modal to find out what you picked. So every
// control writes straight through to creator_data and the only exit is Done.
//
// Cards come from models/loras. Everything above the filename — showcase image,
// title, base model, trigger words — comes from whatever sidecars are beside the
// file, which is `lorameta.py`'s problem rather than this file's: half a dozen
// tools write half a dozen layouts and they all arrive here as one row shape. A
// LoRA nothing has ever described still gets a working card from its filename.
//
// A real collection is hundreds or thousands of files, so the grid never holds
// all of them: a folder picker narrows what the server even walks, and what
// comes back is appended a screenful at a time as you scroll.

import { el, ICONS, svg, drawFrame, mountOverlay } from "./dom.js";
import { listLoras, loraPreviewUrl } from "./api.js";
import { openLoraDetail } from "./loradetail.js";
import { t } from "./i18n.js";
import * as S from "./state.js";

// Cards added per pass, and how far below the fold to keep filling. One card is
// a handful of elements and, once active, four controls — a thousand of them at
// once is a locked-up tab, which is the whole reason for chunking.
const CHUNK = 48;
const LOOKAHEAD = 500;

// The last folder browsed, so reopening the manager lands where you left off.
const FOLDER_KEY = "mmc.loraFolder";

const MAX_STRENGTH = 2;

/** A LoRA's filename as the chips, the swap header and the strip face's pill
 *  say it: no folder, no extension. What a card shows is the sidecar's title
 *  where there is one. */
export const loraBase = (entry) => baseName(entry.name);
const baseName = (name) => name.split("/").pop().replace(/\.[^.]+$/, "");

/** What the per-LoRA checkpoint control offers, for a family that routes.
 *  Built per family rather than once, because the choices *are* the family's
 *  routed slots — and a family with one transformer has none, which is why the
 *  control is dropped rather than drawn with a single option. */
const modeChoices = (family) => [
  ...S.checkpointsOf(family).map(
    (id) => [id, S.checkpointLabels(family)[id], S.checkpointWhen(family)[id]]),
  ["both", "Both", "Patch whichever checkpoint is routed."],
];

/**
 * The stack, as every face that has one draws it.
 *
 * Three faces hold LoRAs — the Creator's, the PreStage's and the timeline's —
 * and they drew (or, in the timeline's case, did not draw) their own chips.
 * That is fine for a row of one label and a ✕ and stops being fine the moment
 * the chip carries decisions: a mute that means one thing on the Creator and
 * another on the PreStage is not a mute, and a stack the timeline shows only as
 * "2 LoRAs" is a stack you cannot mute, swap or read the strength of at all.
 *
 * So the chip lives here, beside the manager it opens, and the faces pass what
 * differs: which checkpoints are in play (none, for the PreStage's single-DiT
 * models) and the four callbacks that commit.
 *
 * @param {object} state              anything with a `loras` array
 * @param {string[]|null} spec.targets the checkpoints this graph routes to, for
 *                                     the idle mark; null where a LoRA cannot
 *                                     claim the wrong one
 * @param {boolean} [spec.triggers]   draw the trigger-word prefix note. Off for
 *                                     the timeline, where the prefix is
 *                                     composed per segment and one line under
 *                                     the strip would be a guess at which.
 */
export function loraBlock(state, spec) {
  const parts = [el("div", { class: "mmc-assets" },
                    (state.loras ?? []).map((entry) => loraChip(entry, spec)))];
  // Trigger words go in front of the prompt at compile time. Showing the
  // prefix is the difference between that and the prompt quietly not being
  // what the box says it is.
  const triggers = spec.triggers === false ? [] : S.promptTriggers(state);
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

/** One entry: the mute, the weight, the swap and the ✕. */
function loraChip(entry, { targets = null, family = S.DEFAULT_VIDEO_FAMILY,
                           onToggle, onManage, onSwap, onRemove }) {
  const modes = S.loraModes(entry);
  const label = S.checkpointLabels(family);
  // Set to a checkpoint this graph does not route to. Still in the stack —
  // dropping it on a route change would throw the setting away — but out of
  // the run, and said so on the chip rather than only in the manager.
  const idle = targets ? !modes.some((mode) => targets.includes(mode)) : false;
  return el("div", {
    class: `mmc-asset${idle ? " idle" : ""}${entry.enabled === false ? " off" : ""}`,
    title: idle
      ? t("{name} — set to {modes}, but this graph routes to {target}.", {
          name: entry.name,
          modes: modes.map((mode) => label[mode]).join(" + "),
          target: targets.map((mode) => label[mode]).join(" + "),
        })
      : entry.name,
  }, [
    el("span", { class: "mmc-asset-thumb" }, [svg(ICONS.effect, 15)]),
    // The name is the mute. Whether a LoRA is the reason the last render looked
    // like that is a question you ask a dozen times an hour, and the only
    // control that used to answer it was the ✕ — which takes the strength, the
    // checkpoint and the trigger words with it.
    loraName(entry, () => onToggle(entry)),
    el("button", {
      class: "mmc-ghost",
      style: { fontSize: "11px" },
      title: targets
        ? t("Strength, and which checkpoint this LoRA belongs to")
        : t("Strength — edit on the LoRA card"),
      text: targets
        ? `${Number(entry.strength ?? 1).toFixed(2)} · ${S.claimsBoth(entry) ? t("both") : label[modes[0]]}`
        : Number(entry.strength ?? 1).toFixed(2),
      onclick: () => onManage(entry),
    }),
    swapLoraButton(entry, () => onSwap(entry)),
    el("button", {
      class: "mmc-asset-x", text: "✕", title: t("Remove {name}", { name: entry.name }),
      onclick: () => onRemove(entry),
    }),
  ]);
}

/** The name, which is the mute switch: click to take this LoRA out of the run
 *  and click again to bring it back, with everything you set up still on it. */
function loraName(entry, onToggle) {
  const off = entry.enabled === false;
  return el("button", {
    class: "mmc-asset-handle mmc-asset-name",
    "aria-pressed": off,
    title: off
      ? t("{name} is muted — out of the run, and kept exactly as you set it up. Click to bring it back.",
          { name: baseName(entry.name) })
      : t("{name} — click to mute it: out of the run, but its strength, checkpoint and triggers stay.",
          { name: baseName(entry.name) }),
    text: baseName(entry.name),
    onclick: onToggle,
  });
}

/** Try a different file in this slot. */
function swapLoraButton(entry, onclick) {
  return el("button", {
    class: "mmc-asset-x mmc-asset-shuffle",
    title: t("Swap {name} for another LoRA, in the same slot.", { name: baseName(entry.name) }),
    onclick,
  }, [svg(ICONS.shuffle, 13)]);
}

/**
 * @param {object} options
 * @param {object} options.state       anything with a `loras` array, mutated in
 *                                     place — a creator_data state or a timeline
 * @param {string[]} [options.targets] the checkpoints in play, for the idle
 *                                     marks. Defaults to the one this state
 *                                     routes to; a timeline passes the set its
 *                                     segments route to, which can be both.
 * @param {() => void} options.onChange called after every edit; reserialises
 * @param {string} [options.swapping]  the name of an entry to replace: the grid
 *                                     becomes a one-shot picker, and the card
 *                                     you click takes that entry's slot.
 */
export function openLoras(options) {
  return new Promise((resolve) => {
    new LoraManager(options, resolve).mount();
  });
}

class LoraManager {
  /** `checkpointModes: false` drops the FL2VA/Ref2VA segment and the idle
   *  marks — the PreStage's image models have one DiT each, so "which
   *  checkpoint does this LoRA claim" is not a question there. */
  constructor({ state, onChange, targets, family = S.DEFAULT_VIDEO_FAMILY,
                checkpointModes = true, swapping = null }, resolve) {
    this.state = state;
    this.family = family;
    // ...and dropped for a family that ships one transformer, for the same
    // reason the PreStage drops it: "which checkpoint does this LoRA claim" is
    // not a question where there is one. `S.routing` is the whole test.
    this.checkpointModes = checkpointModes && S.routing(family);
    // Swapping is the same grid asked a different question — "which one
    // instead" rather than "which ones" — so it is a flag on the manager
    // rather than a second browser that would need its own folder memory,
    // chunking, previews and sidecar reading.
    this.swapping = swapping;
    this.targets = targets ?? (this.checkpointModes
      ? [S.checkpoint(state)] : [...S.checkpointsOf(family)]);
    this.onChange = onChange;
    this.resolve = resolve;
    this.query = "";
    this.rows = [];
    this.folders = [];
    this.cards = new Map();   // name -> the card element currently in the grid
    this.shown = 0;
    this.loaded = false;
    try {
      this.folder = localStorage.getItem(FOLDER_KEY) || "";
    } catch {
      this.folder = "";   // storage can be denied outright; the picker still works
    }
  }

  mount() {
    this.stillWatch = this.watchStills();
    this.grid = el("div", {
      class: "mmc-grid mmc-lora-grid",
      onscroll: () => this.fill(),
    });
    this.picker = el("select", {
      class: "mmc-folder",
      title: t("Which folder under models/loras to browse."),
      onchange: (event) => this.setFolder(event.target.value),
    });
    this.search = el("input", {
      class: "mmc-search",
      type: "search",
      placeholder: t("Search LoRAs..."),
      oninput: (event) => { this.query = event.target.value.toLowerCase(); this.renderGrid(); },
    });
    this.foot = el("div", { class: "mmc-modal-foot" }, [
      this.slots = el("span", { class: "mmc-slots" }),
      el("button", {
        class: "mmc-add",
        // Nothing has changed yet in a swap, so the way out of one is Cancel.
        text: this.swapping ? t("Cancel") : t("Done"),
        onclick: () => this.close(),
      }),
    ]);

    this.modal = el("div", { class: "mmc-modal" }, [
      el("div", { class: "mmc-modal-head" }, [
        el("button", {
          class: "mmc-tab", "aria-selected": true,
          text: this.swapping
            ? t("Replace {name}", { name: baseName(this.swapping) })
            : t("LoRAs"),
        }),
        el("button", { class: "mmc-close", text: "✕", onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-modal-bar" }, [
        this.picker,
        this.search,
        el("button", { class: "mmc-ghost", text: t("Rescan"), onclick: () => this.load({ force: true }) }),
      ]),
      this.grid,
      this.foot,
    ]);
    this.modal.style.position = "relative";

    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(); },
    }, [this.modal]);

    this.unmount = mountOverlay(this.overlay, () => this.close());

    this.renderFoot();
    this.load();
    setTimeout(() => this.search.focus(), 30);
  }

  async load({ force = false } = {}) {
    const folder = this.folder;
    this.loaded = false;
    this.renderGrid();
    let body;
    try {
      body = await listLoras({ folder, force });
      this.loadError = null;
    } catch (error) {
      body = { loras: [], folders: this.folders };
      this.loadError = error.message;
    }
    // A slow folder answering after you have already moved on would otherwise
    // repaint the grid with the wrong folder's cards.
    if (folder !== this.folder) return;
    this.rows = body.loras ?? [];
    this.folders = body.folders ?? [];
    this.matched = body.matched ?? this.rows.length;
    this.truncated = !!body.truncated;
    this.loaded = true;
    this.renderPicker();
    this.renderGrid();
  }

  setFolder(folder) {
    this.folder = folder;
    try {
      localStorage.setItem(FOLDER_KEY, folder);
    } catch { /* denied storage is not worth failing a click over */ }
    this.load();
  }

  renderPicker() {
    // The remembered folder may have been renamed or emptied since; it stays in
    // the list so the picker still shows what it is actually browsing.
    const known = this.folders.some((entry) => entry.path === this.folder);
    const entries = known ? this.folders : [...this.folders, { path: this.folder, count: 0 }];
    this.picker.replaceChildren(...entries.map((entry) => el("option", {
      value: entry.path,
      text: `${entry.path || t("All folders")} (${entry.count})`,
    })));
    this.picker.value = this.folder;
  }

  /** Anything the user could reasonably type: filename, Civitai title, base
   *  model, tag or trigger word. */
  visible() {
    if (!this.query) return this.rows;
    return this.rows.filter((row) =>
      [row.name, row.title, row.version, row.base_model, ...(row.tags || []), ...(row.trained_words || [])]
        .filter(Boolean).join(" ").toLowerCase().includes(this.query));
  }

  // ---- edits ---------------------------------------------------------------

  changed() {
    this.onChange?.();
    this.renderFoot();
  }

  toggle(row) {
    if (this.swapping) return this.swapTo(row);
    if (S.findLora(this.state, row.name)) S.removeLora(this.state, row.name);
    // Both of these are the sidecar's opinion and both stay editable: the
    // triggers become chips that can be switched off, the strength a slider
    // that can be dragged. Starting from what the file's author chose is only
    // a better guess than 1.00, not a decision.
    else S.addLora(this.state, row.name, row.trained_words || [], row.strength);
    this.refreshCard(row);
    this.changed();
  }

  /** Take the slot of the entry this manager was opened to replace, and leave:
   *  one pick is the whole errand, and staying open would ask a question — which
   *  of these two is the swap — that the grid can no longer answer. */
  swapTo(row) {
    S.replaceLora(this.state, this.swapping, row.name, row.trained_words || [], row.strength);
    this.changed();
    this.close();
  }

  /** Neither of these re-renders the grid: the trigger row owns a text input,
   *  and rebuilding the card under it would take the caret away between words. */
  toggleTrigger(entry, word) {
    const at = entry.triggers.findIndex((w) => w.toLowerCase() === word.toLowerCase());
    if (at >= 0) entry.triggers.splice(at, 1);
    else entry.triggers.push(word);
    this.changed();
  }

  addTrigger(entry, raw) {
    const word = raw.trim();
    if (!word || entry.triggers.some((w) => w.toLowerCase() === word.toLowerCase())) return false;
    entry.triggers.push(word);
    this.changed();
    return true;
  }

  setModes(entry, row, choice) {
    entry.modes = choice === "both"
      ? [...S.checkpointsOf(this.family)] : [choice];
    this.refreshCard(row);
    this.changed();
  }

  // ---- render --------------------------------------------------------------

  /** Rebuild one card where it stands.
   *
   *  Adding a LoRA or switching its checkpoint changes only that card, and
   *  redrawing the whole grid for it would throw away the scroll position and
   *  every chunk appended to reach it.
   */
  refreshCard(row) {
    const current = this.cards.get(row.name);
    if (!current) return;
    const next = this.card(row);
    current.replaceWith(next);
    this.cards.set(row.name, next);
    // A card that just lost its controls is shorter, which can uncover room the
    // next chunk should fill.
    this.fill();
  }

  message(text) {
    this.grid.replaceChildren(el("div", { class: "mmc-empty", text }));
    this.cards.clear();
    this.pending = null;
    this.shown = 0;
  }

  renderGrid() {
    if (!this.loaded) return this.message(t("Loading…"));
    if (this.loadError) return this.message(t("Could not read models/loras: {error}", { error: this.loadError }));

    const rows = this.visible();
    if (!rows.length) {
      const where = this.folder ? `“${this.folder}”` : "models/loras";
      const capped = this.truncated
        ? " " + t("Only the {shown} most recent of {matched} here were listed — try a narrower folder.",
                  { shown: this.rows.length, matched: this.matched })
        : "";
      return this.message((this.query
        ? t("No LoRA matching “{query}” in {where}.", { query: this.query, where })
        : t("No LoRAs in {where} yet.", { where })) + capped);
    }

    this.pending = rows;
    this.shown = 0;
    this.cards.clear();
    this.note = el("div", { class: "mmc-grid-note" });
    this.grid.replaceChildren(this.note);
    this.grid.scrollTop = 0;
    this.fill();
  }

  /** Append chunks until the note sits far enough below the fold. */
  fill() {
    if (!this.pending || this.shown >= this.pending.length) return;
    const bottom = this.grid.getBoundingClientRect().bottom + LOOKAHEAD;
    while (this.shown < this.pending.length
           && this.note.getBoundingClientRect().top < bottom) {
      this.appendChunk();
    }
  }

  appendChunk() {
    const batch = this.pending.slice(this.shown, this.shown + CHUNK);
    const frag = document.createDocumentFragment();
    for (const row of batch) {
      const card = this.card(row);
      this.cards.set(row.name, card);
      frag.appendChild(card);
    }
    this.grid.insertBefore(frag, this.note);
    this.shown += batch.length;
    this.renderNote();
  }

  renderNote() {
    const left = this.pending.length - this.shown;
    if (left > 0) {
      this.note.textContent = t("{left} more below…", { left });
    } else if (this.truncated) {
      // The server described only the newest of what it found, and the search
      // box only filters what it sent — so say so rather than let a LoRA that
      // was never listed read as one that is not on disk.
      this.note.textContent = t(
        "Only the {shown} most recent of {matched} LoRAs in this scope were "
        + "listed. Choose a narrower folder to reach the older ones.",
        { shown: this.rows.length, matched: this.matched });
    } else {
      this.note.textContent = "";
    }
  }

  /**
   * A still of the showcase clip, so a video card shows something before
   * anyone hovers it: an in-page <video> whose src carries a media fragment.
   * `#t=0.12` makes the browser itself display the frame at 0.12s — a beat
   * past the black or mid-fade these clips routinely open on — with no canvas
   * capture at all. Every capture route tried here (frame counting, seek +
   * drawImage) worked on one browser and not another; the fragment is the one
   * the CiviMeta browser in roadmaus-utils has already proven on every
   * machine this runs on.
   *
   * Lazy through an IntersectionObserver, for the reason hoverClip tears its
   * decoder down: a folder of hundreds of cards each opening a connection at
   * once is the media-element cap and the six-per-host budget both blown in
   * one scroll. Only cards that reach the viewport ever get a src, and the
   * grid already appends in viewport-sized chunks. The observer is the
   * manager's own and is disconnected with it — a shared one would keep every
   * dead card of every closed modal alive.
   */
  still(source) {
    const video = el("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.dataset.src = `${source}#t=0.12`;
    this.stillWatch.observe(video);
    return video;
  }

  watchStills() {
    return new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const video = entry.target;
        this.stillWatch.unobserve(video);
        if (video.dataset.src) {
          video.src = video.dataset.src;
          delete video.dataset.src;
        }
      }
    }, { rootMargin: "300px" });
  }

  /**
   * Run a showcase clip inside `art` for as long as the pointer is over it,
   * drawn onto a canvas inserted ahead of `before`.
   *
   * Decoder and canvas are both built on hover and torn down on leave, so the
   * grid never holds more than the one clip under the pointer: browsers cap how
   * many media elements a page may have, and in a folder of hundreds every card
   * past the cap silently stays blank.
   */
  hoverClip(art, before, source) {
    let video = null;
    let stage = null;
    let timer = null;

    const follow = () => {
      timer = null;
      if (!video || video.paused) return;
      // 480 rather than the default cap: the card is 230 px wide and the canvas
      // is a hover preview nobody inspects closely.
      drawFrame(stage, video, 480);
      timer = requestAnimationFrame(follow);
    };

    art.addEventListener("pointerenter", () => {
      if (!video) {
        stage = el("canvas");
        art.insertBefore(stage, before);
        video = document.createElement("video");
        video.muted = true;
        video.loop = true;
        video.playsInline = true;
        // The clip is going to be decoded the moment it arrives, so there is
        // nothing for `metadata` to save here.
        video.preload = "auto";
        video.src = source;
      }
      video.play().then(follow, () => {});
    });

    art.addEventListener("pointerleave", () => {
      if (timer) cancelAnimationFrame(timer);
      timer = null;
      if (video) {
        video.pause();
        // Stop the download too: leaving the src on a dropped element keeps a
        // connection out of the browser's six-per-host budget until it finishes.
        video.removeAttribute("src");
        video.load();
        video = null;
      }
      stage?.remove();
      stage = null;
    });
  }

  card(row) {
    const entry = S.findLora(this.state, row.name);
    const card = el("div", { class: "mmc-lora", "aria-selected": !!entry });

    const art = el("div", {
      class: "mmc-lora-art",
      role: "button",
      tabindex: "0",
      title: this.swapping
        ? t("Use {name} instead", { name: row.name })
        : t("{name} — double-click for details", { name: row.name }),
      // Double-clicks are detected by hand, same as the picker's cells: the
      // first click's toggle rebuilds the card, so the second click lands on a
      // replacement element and no browser synthesises a dblclick across two
      // nodes. The second click re-toggles first, so viewing the details
      // leaves the selection exactly where it stood.
      onclick: () => {
        // One click is the whole gesture while swapping, and it closes the
        // grid — there is no second one for a details view to arrive on.
        if (this.swapping) return this.toggle(row);
        const now = Date.now();
        const double = this.lastClick
          && this.lastClick.name === row.name && now - this.lastClick.at < 400;
        this.lastClick = double ? null : { name: row.name, at: now };
        this.toggle(row);
        if (double) openLoraDetail(row);
      },
      onkeydown: (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this.toggle(row); }
      },
    });
    // The preview kind is decided server-side from what was actually found: an
    // H3 LoRA usually showcases clips, CiviMeta only generates still thumbnails
    // for still media, and `{name}.preview.mp4` is a video by definition — so a
    // video card shows a still of its clip (see `still`) and plays it on hover.
    if (row.preview === "image") {
      art.appendChild(el("img", { src: loraPreviewUrl(row.name), loading: "lazy", alt: "" }));
    } else {
      // Underneath the still and the clip, and on its own when there is no
      // preview at all.
      art.appendChild(el("div", { class: "mmc-cell-fallback" }, [svg(ICONS.effect, 26)]));
    }
    // The still sits over the fallback and under the hover clip, all three
    // stacked by the art box's absolute positioning.
    if (row.preview === "video") {
      art.appendChild(this.still(loraPreviewUrl(row.name)));
    }
    const check = el("div", { class: "mmc-check" });
    art.appendChild(check);
    if (row.preview === "video") this.hoverClip(art, check, loraPreviewUrl(row.name));
    card.appendChild(art);

    const meta = [row.base_model, row.version].filter(Boolean).join(" · ");
    const body = el("div", { class: "mmc-lora-body" }, [
      el("div", { class: "mmc-lora-name", text: row.title || row.base, title: row.name }),
      el("div", { class: "mmc-lora-sub", text: meta || row.name }),
    ]);
    // Until the LoRA is active its trigger words are just information; once it
    // is, they become the editable list in the controls below.
    if (!entry && row.trained_words?.length) {
      body.appendChild(el("div", {
        class: "mmc-lora-words",
        title: t("Trigger words from the sidecar. Adding this LoRA takes them on, and you can then drop or extend them."),
        text: row.trained_words.join(", "),
      }));
    }
    // A LoRA nothing has described says so, rather than looking like one whose
    // sidecar is merely empty. The manager is also where someone would go to
    // find out why a card is bare.
    if (!entry && !row.sources?.length) {
      body.appendChild(el("div", {
        class: "mmc-lora-words",
        title: t("No sidecar and nothing in the file's own header. Double-click for what the safetensors header does say."),
        text: t("no metadata"),
      }));
    }
    // Not while swapping: the controls edit an entry, and every card in that
    // grid is a candidate rather than something in the stack.
    if (entry && !this.swapping) body.appendChild(this.controls(entry, row));
    card.appendChild(body);
    return card;
  }

  /**
   * The trigger words this LoRA contributes to the front of the prompt.
   *
   * The sidecar's words and your own are the same list once the LoRA is added —
   * a sidecar word is a chip you can switch off, a word you type is a chip you
   * can delete, and creator_data stores whichever survived. So a LoRA whose
   * sidecar is wrong, or has none at all, is no harder to trigger than one whose
   * sidecar is right.
   */
  triggerBox(entry, row) {
    if (!Array.isArray(entry.triggers)) entry.triggers = [];
    const suggested = row.trained_words || [];
    const isSuggested = (word) => suggested.some((s) => s.toLowerCase() === word.toLowerCase());
    const chosen = (word) => entry.triggers.some((w) => w.toLowerCase() === word.toLowerCase());

    const chips = el("div", { class: "mmc-trigs" });
    const renderChips = () => {
      const own = entry.triggers.filter((word) => !isSuggested(word));
      chips.replaceChildren(...[
        ...suggested.map((word) => el("button", {
          class: "mmc-trig", "aria-pressed": chosen(word),
          title: chosen(word) ? t("In the prompt — click to drop") : t("From the sidecar — click to use"),
          text: word,
          onclick: () => { this.toggleTrigger(entry, word); renderChips(); },
        })),
        ...own.map((word) => el("button", {
          class: "mmc-trig own", "aria-pressed": true,
          title: t("Yours — click to remove"),
          text: word,
          onclick: () => { this.toggleTrigger(entry, word); renderChips(); },
        })),
      ]);
    };
    renderChips();

    const input = el("input", {
      class: "mmc-trig-add",
      type: "text",
      placeholder: suggested.length ? t("add a word") : t("no sidecar words — add your own"),
      onkeydown: (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        if (this.addTrigger(entry, event.target.value)) renderChips();
        event.target.value = "";
      },
      // The manager sits over the graph canvas, which reads keys of its own.
      onkeyup: (event) => event.stopPropagation(),
    });

    return el("div", { class: "mmc-trig-box" }, [
      el("div", { class: "mmc-lora-row" }, [el("span", { class: "mmc-lora-label", text: t("Triggers") })]),
      chips,
      input,
    ]);
  }

  controls(entry, row) {
    // A hand-edited creator_data can carry anything; the slider needs a number.
    if (!Number.isFinite(entry.strength)) entry.strength = S.DEFAULT_STRENGTH;
    const readout = el("span", { class: "mmc-lora-strength", text: entry.strength.toFixed(2) });
    // The same mute the chip on the node face carries, so a stack switched off
    // there does not read as fully in here. See `state.toggleLora`.
    const mute = el("button", {
      class: "mmc-lora-mute",
      "aria-pressed": entry.enabled === false,
      title: entry.enabled === false
        ? t("Muted — kept with its strength, its checkpoint and its triggers, and out of the run. Click to bring it back.")
        : t("Mute: out of the run, but kept exactly as you set it up."),
      text: entry.enabled === false ? t("muted") : t("mute"),
      onclick: () => { S.toggleLora(this.state, entry.name); this.refreshCard(row); this.changed(); },
    });
    const slider = el("input", {
      type: "range", min: -1, max: MAX_STRENGTH, step: 0.05, value: entry.strength,
      // Dragging must not re-render the card out from under the pointer, so the
      // readout is updated by hand and only the release reserialises.
      oninput: (event) => {
        entry.strength = Number(event.target.value);
        readout.textContent = entry.strength.toFixed(2);
      },
      onchange: () => this.changed(),
      onpointerdown: (event) => event.stopPropagation(),
    });

    const current = S.claimsBoth(entry) ? "both" : S.loraModes(entry)[0];
    const modes = el("div", { class: "mmc-seg" }, modeChoices(this.family).map(([value, label, hint]) =>
      el("button", {
        class: "mmc-seg-btn",
        "aria-pressed": value === current,
        title: t(hint),
        text: t(label),
        onclick: () => this.setModes(entry, row, value),
      })));

    const rows = [
      el("div", { class: "mmc-lora-row" }, [
        el("span", { class: "mmc-lora-label", text: t("Strength") }), mute, readout]),
      slider,
      ...(this.checkpointModes ? [modes] : []),
      this.triggerBox(entry, row),
    ];
    // Active, but on none of the checkpoints this graph routes to.
    if (this.checkpointModes && !this.applies(entry)) {
      rows.push(el("div", {
        class: "mmc-lora-idle",
        text: this.targets.length > 1
          ? t("Idle — {targets} are routed here.", { targets: this.routesTo() })
          : t("Idle — {targets} is routed here.", { targets: this.routesTo() }),
      }));
    }
    return el("div", { class: "mmc-lora-ctl" }, rows);
  }

  /** Whether this entry lands on anything the caller said is in play.
   *
   *  Always, for a family that does not route: there is one transformer, every
   *  LoRA is patched onto it, and "idle" would be reporting a distinction the
   *  family does not have. */
  applies(entry) {
    if (!this.checkpointModes && !this.targets.length) return true;
    return S.loraModes(entry).some((mode) => this.targets.includes(mode));
  }

  routesTo() {
    const label = S.checkpointLabels(this.family);
    return this.targets.map((name) => label[name]).join(" + ")
      || t(S.FAMILY_LABEL[this.family]);
  }

  renderFoot() {
    if (this.swapping) {
      this.slots.textContent = t("Pick what takes {name}'s place — its strength, checkpoint and "
                               + "triggers come from the file you pick.", { name: baseName(this.swapping) });
      return;
    }
    const entries = this.state.loras;
    // Muted counts with idle rather than with active: both mean the same thing
    // to the next queue, which is that this file is not in it.
    const active = entries.filter((entry) => entry.enabled !== false && this.applies(entry)).length;
    const extra = entries.length > active
      ? " " + t("({count} idle)", { count: entries.length - active })
      : "";
    this.slots.textContent = t("{active} on {targets}", { active, targets: this.routesTo() }) + extra;
    this.slots.classList.toggle("full", false);
  }

  close() {
    // The observer holds strong references to every card it still watches.
    this.stillWatch.disconnect();
    this.unmount();
    this.resolve();
  }
}
