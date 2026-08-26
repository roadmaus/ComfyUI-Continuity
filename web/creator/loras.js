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
//
// Three things outlive the window, in `api.loadLoraPrefs`. The scope it was last
// left in, so it opens where you were. Which files are starred, which is the
// only way back to a LoRA in a folder too large to list. And what you last had
// each LoRA set to — the strength you settled on and the trigger words you kept
// — because that is the part that took the trying, and it used to be thrown away
// the moment the LoRA left the stack.
//
// A saved *stack* is a preset and lives in the preset store, under the Stacks
// tab here. `presets.js` already knows how to name, file, cross-apply and export
// a set of sections, and a LoRA stack is one of its sections; a second store for
// the same data would be a second set of those answers to keep in step.

import { el, ICONS, svg, drawFrame, mountOverlay } from "./dom.js";
import { listLoras, listLorasNamed, loraPreviewUrl, loadLoraPrefs, saveLoraPrefs } from "./api.js";
import { openLoraDetail } from "./loradetail.js";
import { listPresets, loadBody, savePreset, deletePreset } from "./presets.js";
import { t } from "./i18n.js";
import * as S from "./state.js";

// Cards added per pass, and how far below the fold to keep filling. One card is
// a handful of elements and, once active, four controls — a thousand of them at
// once is a locked-up tab, which is the whole reason for chunking.
const CHUNK = 48;
const LOOKAHEAD = 500;

// The two scopes that are not places. A folder path cannot collide with these:
// they come from splitting a relative filename on "/", and a leading colon is
// not something any of them starts with.
const FAVORITES = ":favorites";
const RECENT = ":recent";
const isShelf = (scope) => scope === FAVORITES || scope === RECENT;

// How many of the recently-used to put on that shelf. Long enough to cover what
// you are actually working with this month, short enough to still be a shelf
// rather than a second All.
const RECENT_SHOWN = 60;

const MAX_STRENGTH = 2;

const same = (a, b) => a.toLowerCase() === b.toLowerCase();
const has = (list, word) => list.some((entry) => same(entry, word));

/** A LoRA's filename as the chips, the swap header and the strip face's pill
 *  say it: no folder, no extension. What a card shows is the sidecar's title
 *  where there is one. */
export const loraBase = (entry) => baseName(entry.name);
const baseName = (name) => name.split("/").pop().replace(/\.[^.]+$/, "");

/** The folder a name sits in, "" at the root — the scope that certainly holds
 *  it, which is what `reveal` opens on. */
const folderOf = (name) => name.split("/").slice(0, -1).join("/");

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
  const triggers = spec.triggers === false
    ? [] : S.promptTriggers(state, spec.family ?? S.DEFAULT_VIDEO_FAMILY);
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
  const modes = S.loraModes(entry, family);
  const label = S.checkpointLabels(family);
  // Whether this chip has a checkpoint to say anything about at all. A family
  // that ships one transformer has none — every LoRA is patched onto it — so
  // the chip wears its strength alone, which is also what the PreStage's
  // single-DiT stacks have always done (`targets: null`).
  const routes = Boolean(targets?.length) && S.routing(family);
  // Set to a checkpoint this graph does not route to. Still in the stack —
  // dropping it on a route change would throw the setting away — but out of
  // the run, and said so on the chip rather than only in the manager.
  const idle = routes ? !modes.some((mode) => targets.includes(mode)) : false;
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
      title: routes
        ? t("Strength, and which checkpoint this LoRA belongs to")
        : t("Strength — edit on the LoRA card"),
      text: routes
        ? `${Number(entry.strength ?? 1).toFixed(2)} · ${S.claimsBoth(entry, family) ? t("both") : label[modes[0]]}`
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
 * @param {string} [options.reveal]    the name of a LoRA to scroll to and mark.
 *                                     Opening the manager from a chip means
 *                                     "this one" — see `revealNow`.
 * @param {string} [options.scope]     which kind of node this stack belongs to,
 *                                     for a stack saved from here: "piece",
 *                                     "shot" or "prestage".
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
                checkpointModes = true, swapping = null, reveal = null,
                scope = "piece" }, resolve) {
    this.state = state;
    this.family = family;
    this.presetScope = scope;
    // ...and dropped for a family that ships one transformer, for the same
    // reason the PreStage drops it: "which checkpoint does this LoRA claim" is
    // not a question where there is one. `S.routing` is the whole test.
    this.checkpointModes = checkpointModes && S.routing(family);
    // Swapping is the same grid asked a different question — "which one
    // instead" rather than "which ones" — so it is a flag on the manager
    // rather than a second browser that would need its own folder memory,
    // chunking, previews and sidecar reading.
    this.swapping = swapping;
    // Which card to scroll to once the grid has one. Cleared the moment it is
    // spent, so that typing in the search box does not keep jumping back.
    this.reveal = swapping ? null : reveal;
    this.revealTried = false;
    this.targets = targets ?? (this.checkpointModes
      ? S.checkpointsFor(state, family) : [...S.checkpointsOf(family)]);
    this.onChange = onChange;
    this.resolve = resolve;
    this.query = "";
    this.rows = [];
    this.folders = [];
    this.missing = [];
    this.cards = new Map();   // name -> the card element currently in the grid
    this.shown = 0;
    this.loaded = false;
    // Which LoRAs on screen were set up from memory rather than from their
    // sidecar, so the card can say so — a slider sitting somewhere the file's
    // author did not put it is otherwise unexplained.
    this.restored = new Set();
    this.tab = "loras";
    // Until the prefs land: no favorites, nothing remembered, browsing
    // everything. The grid says "Loading…" over all of it anyway.
    this.prefs = { folder: "", favorites: [], used: {} };
    this.scope = "";
  }

  mount() {
    this.stillWatch = this.watchStills();
    this.grid = el("div", {
      class: "mmc-grid mmc-lora-grid",
      onscroll: () => this.fill(),
    });
    this.picker = el("select", {
      class: "mmc-folder",
      title: t("What the grid shows: a shelf of your own, or a folder under models/loras."),
      onchange: (event) => this.setScope(event.target.value),
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

    this.bar = el("div", { class: "mmc-modal-bar" }, [
      this.picker,
      this.search,
      el("button", { class: "mmc-ghost", text: t("Rescan"), onclick: () => this.load({ force: true }) }),
    ]);
    this.stacksPane = el("div", { class: "mmc-stacks", style: { display: "none" } });
    this.stacks = [];

    // A swap is one question with one answer in it — "which file instead" — so
    // it gets the title it always had and none of the tabs. Applying a whole
    // stack is not an answer to it.
    this.tabs = this.swapping
      ? [el("button", {
          class: "mmc-tab", "aria-selected": true,
          text: t("Replace {name}", { name: baseName(this.swapping) }),
        })]
      : [
          this.loraTab = el("button", {
            class: "mmc-tab", "aria-selected": true, text: t("LoRAs"),
            onclick: () => this.setTab("loras"),
          }),
          this.stackTab = el("button", {
            class: "mmc-tab", "aria-selected": false, text: t("Stacks"),
            title: t("Whole stacks you have saved, kept with your presets."),
            onclick: () => this.setTab("stacks"),
          }),
        ];

    this.modal = el("div", { class: "mmc-modal" }, [
      el("div", { class: "mmc-modal-head" }, [
        ...this.tabs,
        el("button", { class: "mmc-close", text: "✕", onclick: () => this.close() }),
      ]),
      this.bar,
      this.grid,
      this.stacksPane,
      this.foot,
    ]);
    this.modal.style.position = "relative";

    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(); },
    }, [this.modal]);

    this.unmount = mountOverlay(this.overlay, () => this.close());

    this.renderFoot();
    this.start();
    setTimeout(() => this.search.focus(), 30);
  }

  /** Read what was remembered, then open on it. The prefs are one small file
   *  and the grid is showing "Loading…" for the listing regardless, so there is
   *  nothing to be gained by drawing a scope the user did not leave it in. */
  async start() {
    this.prefs = { ...(await loadLoraPrefs()) };
    // A LoRA asked for by name is the whole reason the window is open, and it
    // will not be on a shelf that does not hold it. Its own folder is where it
    // certainly is.
    this.scope = this.reveal ? folderOf(this.reveal) : this.prefs.folder;
    this.load();
  }

  writePrefs() {
    this.prefs = { ...saveLoraPrefs(this.prefs) };
  }

  async load({ force = false } = {}) {
    const scope = this.scope;
    this.loaded = false;
    this.renderGrid();
    let body;
    try {
      body = isShelf(scope)
        ? await listLorasNamed(this.shelved(scope))
        : await listLoras({ folder: scope, force });
      this.loadError = null;
    } catch (error) {
      body = { loras: [], folders: this.folders };
      this.loadError = error.message;
    }
    // A slow folder answering after you have already moved on would otherwise
    // repaint the grid with the wrong folder's cards.
    if (scope !== this.scope) return;
    this.rows = body.loras ?? [];
    this.folders = body.folders ?? this.folders;
    this.missing = body.missing ?? [];
    this.matched = body.matched ?? this.rows.length;
    // A shelf is the files it names, all of them: there is no cap to be under.
    this.truncated = !!body.truncated;
    this.loaded = true;
    // Asked for a LoRA that is not here after all — renamed, deleted, or in a
    // folder the name does not describe. One retry across everything, then the
    // grid is left as it is and the search box is the way to look.
    if (this.reveal && !this.rows.some((row) => row.name === this.reveal)
        && !this.revealTried && this.scope !== "") {
      this.revealTried = true;
      this.scope = "";
      return this.load();
    }
    this.renderPicker();
    this.renderGrid();
  }

  /** The names on a shelf, in the order it shows them. Favorites keep the order
   *  they were starred in; recents are newest first, which is the only order a
   *  list of recents can be in. */
  shelved(scope) {
    if (scope === FAVORITES) return [...this.prefs.favorites];
    return Object.entries(this.prefs.used)
      .sort((a, b) => (b[1].at ?? 0) - (a[1].at ?? 0))
      .slice(0, RECENT_SHOWN)
      .map(([name]) => name);
  }

  setScope(scope) {
    this.scope = scope;
    // Only a folder is a place to open on next time. A shelf is a way of
    // looking at the collection rather than part of it, and landing on an empty
    // Favorites every morning is not where anyone means to start.
    if (!isShelf(scope)) {
      this.prefs.folder = scope;
      this.writePrefs();
    }
    this.load();
  }

  renderPicker() {
    // The remembered folder may have been renamed or emptied since; it stays in
    // the list so the picker still shows what it is actually browsing.
    const known = isShelf(this.scope) || this.folders.some((entry) => entry.path === this.scope);
    const folders = known ? this.folders : [...this.folders, { path: this.scope, count: 0 }];
    const option = (value, text) => el("option", { value, text });
    // Shelves and folders in one control, because they answer one question —
    // what is the grid showing — and two controls would let them disagree. The
    // groups are what keep "Favorites" from reading as a directory.
    const shelves = el("optgroup", { label: t("Shelves") }, [
      option(FAVORITES, `★ ${t("Favorites")} (${this.prefs.favorites.length})`),
      option(RECENT, `${t("Recently used")} (${Object.keys(this.prefs.used).length})`),
    ]);
    const places = el("optgroup", { label: t("Folders") }, folders.map(
      (entry) => option(entry.path, `${entry.path || t("All folders")} (${entry.count})`)));
    this.picker.replaceChildren(shelves, places);
    this.picker.value = this.scope;
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
    this.rememberAll();
    this.onChange?.();
    this.renderFoot();
  }

  // ---- memory --------------------------------------------------------------
  //
  // What each LoRA was last set to, so that adding one back — to this piece next
  // week, or to a piece that has never seen it — starts where you left off
  // rather than where its sidecar guessed. The sidecar is still the fallback,
  // and still the only thing a LoRA nobody has used yet has.

  memoryOf(name) {
    return this.prefs.used[name] ?? null;
  }

  /**
   * Write every live entry down. All of them rather than the one that changed,
   * because `changed` is called from six places and threading the entry through
   * all of them would be six chances to forget one — and the stack is a handful
   * of entries, not a list to walk carefully.
   *
   * `custom` is only recomputed where the row is on screen: the sidecar's words
   * are what "custom" is defined against, and a stack can hold entries from
   * folders this scope is not showing. Their vocabulary is left as it was rather
   * than guessed at from a sidecar we cannot read.
   */
  rememberAll() {
    const now = Date.now();
    for (const entry of this.state.loras ?? []) {
      const previous = this.memoryOf(entry.name);
      const row = this.rows.find((candidate) => candidate.name === entry.name);
      const custom = [...(previous?.custom ?? [])];
      if (row) {
        const sidecar = row.trained_words || [];
        for (const word of entry.triggers ?? []) {
          if (has(sidecar, word) || has(custom, word)) continue;
          custom.push(word);
        }
      }
      this.prefs.used[entry.name] = {
        strength: Number.isFinite(entry.strength) ? entry.strength : null,
        on: [...(entry.triggers ?? [])],
        custom,
        modes: {
          ...(previous?.modes ?? {}),
          // Only where the family has checkpoints to claim between. A pre-stage
          // session must not write an empty claim over the one a piece made:
          // the ids belong to the family, and it has none to overwrite it with.
          ...(this.checkpointModes ? { [this.family]: S.loraModes(entry, this.family) } : {}),
        },
        at: now,
      };
    }
    this.writePrefs();
  }

  toggle(row) {
    if (this.swapping) return this.swapTo(row);
    if (S.findLora(this.state, row.name)) {
      // Remembered on the way out, which is the whole point: the setup survives
      // the removal, and putting the LoRA back brings it with it.
      this.rememberAll();
      S.removeLora(this.state, row.name);
      this.restored.delete(row.name);
    } else {
      this.add(row);
    }
    this.refreshCard(row);
    this.changed();
  }

  /**
   * Add one, from memory where there is any and from the sidecar otherwise.
   *
   * Both are opinions and both stay editable: the triggers become chips that can
   * be switched off, the strength a slider that can be dragged. What memory
   * changes is whose opinion it starts from — yours, from the last time you used
   * this file, rather than the author's guess at how anyone would.
   */
  add(row) {
    const memory = this.memoryOf(row.name);
    const strength = Number.isFinite(memory?.strength) ? memory.strength : row.strength;
    const entry = S.addLora(this.state, row.name, memory ? memory.on : (row.trained_words || []),
                            strength, this.family);
    if (!entry) return;
    const claim = memory?.modes?.[this.family];
    if (this.checkpointModes && claim?.length) entry.modes = [...claim];
    if (memory) this.restored.add(row.name);
  }

  /** Take the slot of the entry this manager was opened to replace, and leave:
   *  one pick is the whole errand, and staying open would ask a question — which
   *  of these two is the swap — that the grid can no longer answer. */
  swapTo(row) {
    S.replaceLora(this.state, this.swapping, row.name, row.trained_words || [],
                  row.strength, this.family);
    this.changed();
    this.close();
  }

  // ---- favorites -----------------------------------------------------------

  isFavorite(name) {
    return this.prefs.favorites.includes(name);
  }

  toggleFavorite(row) {
    this.prefs.favorites = this.isFavorite(row.name)
      ? this.prefs.favorites.filter((name) => name !== row.name)
      : [...this.prefs.favorites, row.name];
    this.writePrefs();
    // On the favorites shelf a star changes what is on screen, so the shelf is
    // re-read; anywhere else it only changes the card it is on.
    if (this.scope === FAVORITES) this.load();
    else {
      this.refreshCard(row);
      this.renderPicker();   // the count in the scope picker moved
    }
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

  /**
   * Drop a word of your own for good — out of the prompt and out of the
   * vocabulary this LoRA remembers.
   *
   * The other half of letting a custom word survive being switched off. Once an
   * off word is still a chip, "click again to remove it" is no longer available
   * as the way to be rid of one, and without this there would be no way at all:
   * a typo typed once would sit under that LoRA forever.
   *
   * Out of the entry first, so that the write `changed` triggers does not read
   * it back off the live list and put it straight back.
   */
  forgetTrigger(entry, word) {
    const at = entry.triggers.findIndex((w) => same(w, word));
    if (at >= 0) entry.triggers.splice(at, 1);
    const memory = this.memoryOf(entry.name);
    if (memory) memory.custom = memory.custom.filter((known) => !same(known, word));
    this.changed();
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
      if (!this.query && this.scope === FAVORITES) {
        return this.message(t("No favorites yet — hover a card and hit the star. "
                            + "This is how you get back to a LoRA in a folder too big to scroll."));
      }
      if (!this.query && this.scope === RECENT) {
        return this.message(t("Nothing used yet. Every LoRA you set up turns up here, "
                            + "with the strength and the trigger words you left on it."));
      }
      const where = this.scopeLabel();
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
    this.revealNow();
  }

  /** What to call the scope in a sentence. */
  scopeLabel() {
    if (this.scope === FAVORITES) return t("your favorites");
    if (this.scope === RECENT) return t("what you have used");
    return this.scope ? `“${this.scope}”` : "models/loras";
  }

  /**
   * Scroll to the LoRA the window was opened for and mark it.
   *
   * Opening the manager from a chip on the node face means "this one" — and the
   * grid it opened onto was a folder of hundreds, scrolled to the top, with no
   * hint of which card the chip you clicked belongs to. Finding it by hand was
   * the whole of what used to happen.
   *
   * Chunks are appended past it rather than waiting for a scroll to ask for
   * them: `fill` stops a screenful below the fold, and the card is only
   * scrollable-to once it exists. One-shot — the reveal is spent here, so that
   * typing in the search box afterwards does not keep dragging the grid back.
   */
  revealNow() {
    const name = this.reveal;
    if (!name) return;
    this.reveal = null;
    const at = this.pending.findIndex((row) => row.name === name);
    if (at < 0) return;
    while (this.shown <= at && this.shown < this.pending.length) this.appendChunk();
    const card = this.cards.get(name);
    if (!card) return;
    card.scrollIntoView({ block: "center" });
    // A grid of near-identical cards does not say which one moved under you.
    card.classList.add("mmc-lora-found");
    setTimeout(() => card.classList.remove("mmc-lora-found"), 1600);
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
    } else if (this.missing.length) {
      // A shelf names its files, so it is the one listing that can tell the
      // difference between "not here" and "gone" — and it should, rather than
      // quietly showing nine of the ten you starred.
      this.note.textContent = t(
        this.missing.length === 1
          ? "{count} file on this shelf is no longer in models/loras: {names}"
          : "{count} files on this shelf are no longer in models/loras: {names}",
        { count: this.missing.length, names: this.missing.map(baseName).join(", ") });
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
    // Not while swapping: every card there is a candidate for one slot, and
    // filing one away is not what the click you came to make is about.
    if (!this.swapping) {
      const starred = this.isFavorite(row.name);
      art.appendChild(el("button", {
        class: `mmc-lora-star${starred ? " on" : ""}`,
        title: starred ? t("Remove from favorites") : t("Add to favorites"),
        // The art is itself a button that adds the LoRA, and a star is a
        // different errand entirely.
        onclick: (event) => { event.stopPropagation(); this.toggleFavorite(row); },
      }, [svg(ICONS.star, 13)]));
    }
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
   *
   * Which chips exist and which are lit are two questions, and they used to have
   * one answer. `entry.triggers` is the words going into the prompt, so a chip
   * drawn only from it could not show a word that is off — the sidecar's words
   * survived being switched off because they are redrawn from the sidecar, and a
   * word you typed simply vanished, with no way back but typing it again. So the
   * chips are the sidecar's words plus the vocabulary this LoRA remembers, and
   * `entry.triggers` decides which of them are pressed.
   */
  triggerBox(entry, row) {
    if (!Array.isArray(entry.triggers)) entry.triggers = [];
    const suggested = row.trained_words || [];
    const chosen = (word) => has(entry.triggers, word);
    // Yours: what memory has for this file, plus anything live that neither list
    // accounts for — a stack applied from a preset arrives with words this
    // machine has never seen typed.
    const remembered = (this.memoryOf(entry.name)?.custom ?? []).filter((word) => !has(suggested, word));
    const own = [...remembered];
    for (const word of entry.triggers) {
      if (!has(suggested, word) && !has(own, word)) own.push(word);
    }

    const chips = el("div", { class: "mmc-trigs" });
    const renderChips = () => {
      chips.replaceChildren(...[
        ...suggested.map((word) => el("button", {
          class: "mmc-trig", "aria-pressed": chosen(word),
          title: chosen(word) ? t("In the prompt — click to drop") : t("From the sidecar — click to use"),
          text: word,
          onclick: () => { this.toggleTrigger(entry, word); renderChips(); },
        })),
        ...own.map((word) => el("span", {
          class: `mmc-trig own${chosen(word) ? " on" : ""}`,
          "aria-pressed": chosen(word),
        }, [
          el("button", {
            class: "mmc-trig-word",
            title: chosen(word)
              ? t("Yours, in the prompt — click to drop")
              : t("Yours — click to use"),
            text: word,
            onclick: () => { this.toggleTrigger(entry, word); renderChips(); },
          }),
          el("button", {
            class: "mmc-trig-forget", text: "✕",
            title: t("Forget “{word}” for this LoRA", { word }),
            onclick: () => {
              this.forgetTrigger(entry, word);
              own.splice(own.findIndex((candidate) => same(candidate, word)), 1);
              renderChips();
            },
          }),
        ])),
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
        const word = event.target.value.trim();
        if (this.addTrigger(entry, word)) {
          if (!has(suggested, word) && !has(own, word)) own.push(word);
          renderChips();
        }
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

    const current = S.claimsBoth(entry, this.family)
      ? "both" : S.loraModes(entry, this.family)[0];
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
    // Where the settings came from, when it was not this file's author. A
    // slider that opens somewhere other than the sidecar's preferred weight is
    // otherwise a small unexplained thing, and "did I set that or did it?" is
    // exactly the doubt this whole feature exists to remove.
    if (this.restored.has(entry.name)) {
      rows.push(el("div", {
        class: "mmc-lora-memo",
        title: t("Everything here is how you last left this LoRA. Change it and the new setup is what comes back next time."),
        text: t("your last setup"),
      }));
    }
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
    return S.loraModes(entry, this.family).some((mode) => this.targets.includes(mode));
  }

  routesTo() {
    const label = S.checkpointLabels(this.family);
    return this.targets.map((name) => label[name]).join(" + ")
      || t(S.FAMILY_LABEL[this.family]);
  }

  // ---- stacks --------------------------------------------------------------
  //
  // A stack you have saved, which is a preset holding nothing but its `loras`
  // section. The preset store already answers naming, filing, deletion, export
  // and — through `crossable` — whether a stack kept off a piece may land on a
  // pre-stage, which for LoRAs it always may. Keeping them here as well as in
  // the library is only a question of where you are standing when you want one:
  // you build a stack in this window, and this is where you reach for one.

  setTab(tab) {
    this.tab = tab;
    this.loraTab?.setAttribute("aria-selected", String(tab === "loras"));
    this.stackTab?.setAttribute("aria-selected", String(tab === "stacks"));
    const stacks = tab === "stacks";
    this.bar.style.display = stacks ? "none" : "";
    this.grid.style.display = stacks ? "none" : "";
    this.stacksPane.style.display = stacks ? "" : "none";
    this.renderFoot();
    if (stacks) this.loadStacks();
  }

  /** Only the ones that are a stack and nothing else. A piece preset carrying
   *  LoRAs alongside its prompt and its weights is a whole node, and applying it
   *  from here would change six things the window cannot show you. */
  async loadStacks() {
    this.stacksPane.replaceChildren(el("div", { class: "mmc-empty", text: t("Loading…") }));
    let rows;
    try {
      rows = await listPresets({ force: true });
    } catch (error) {
      this.stacksPane.replaceChildren(el("div", {
        class: "mmc-empty",
        text: t("Could not read your presets: {error}", { error: error.message }),
      }));
      return;
    }
    const stacks = rows.filter((row) => !row.builtin
      && Array.isArray(row.sections) && row.sections.length === 1 && row.sections[0] === "loras");
    // The bodies hold the filenames, which is what a stack is worth showing: a
    // count tells you nothing about which stack this is. Few enough to read at
    // once, and only on this tab.
    const bodies = await Promise.all(stacks.map((row) => loadBody(row).catch(() => null)));
    this.stacks = stacks.map((row, at) => ({ row, entries: bodies[at]?.loras ?? [] }));
    this.renderStacks();
  }

  renderStacks() {
    const parts = [this.saveStackRow()];
    if (!this.stacks.length) {
      parts.push(el("div", {
        class: "mmc-empty",
        text: t("No saved stacks yet. Set a stack up on the LoRAs tab, then keep it here — "
              + "it lands with your presets, and applies to a piece, a card or a pre-stage alike."),
      }));
    }
    parts.push(...this.stacks.map((stack) => this.stackRow(stack)));
    this.stacksPane.replaceChildren(...parts);
  }

  /** Keep what is in the stack right now. The name is asked for inline rather
   *  than through a prompt(): the window is already a window, and a second one
   *  over it to type six characters is a jolt. */
  saveStackRow() {
    const live = this.state.loras ?? [];
    const name = el("input", {
      class: "mmc-stack-name", type: "text",
      placeholder: t("name this stack"),
      onkeydown: (event) => { if (event.key === "Enter") save(); },
      onkeyup: (event) => event.stopPropagation(),   // the graph canvas reads keys
    });
    const save = () => this.saveStack(name.value);
    return el("div", { class: "mmc-stack-save" }, [
      el("div", { class: "mmc-stack-save-what" }, [
        el("span", { class: "mmc-lora-label", text: t("Keep this stack") }),
        el("span", {
          class: "mmc-stack-sub",
          text: live.length
            ? live.map((entry) => baseName(entry.name)).join(", ")
            : t("nothing in the stack to keep"),
        }),
      ]),
      name,
      el("button", {
        class: "mmc-add", text: t("Save"),
        disabled: !live.length,
        onclick: save,
      }),
    ]);
  }

  async saveStack(typed) {
    const entries = this.state.loras ?? [];
    if (!entries.length) return;
    await savePreset({
      name: typed.trim() || t("LoRA stack"),
      scope: this.presetScope,
      // Through the same serializer every other capture goes through, so a
      // stack kept here and a stack kept by the preset library are the same
      // bytes — see the note over `presets.capturePiece`.
      data: { loras: S.serializeLoras(entries, this.family) },
    });
    this.loadStacks();
  }

  stackRow({ row, entries }) {
    const names = entries.map((entry) => baseName(entry.name));
    return el("div", { class: "mmc-stack" }, [
      el("div", { class: "mmc-stack-what" }, [
        el("div", { class: "mmc-stack-title", text: row.name }),
        el("div", {
          class: "mmc-stack-sub",
          title: entries.map((entry) => `${entry.name} @ ${Number(entry.strength ?? 1).toFixed(2)}`).join("\n"),
          text: names.length ? names.join(", ") : t("empty"),
        }),
      ]),
      el("button", {
        class: "mmc-ghost",
        title: t("Add these to the stack that is already here, leaving it in place."),
        text: t("Add"),
        onclick: () => this.applyStack(entries, { replace: false }),
      }),
      el("button", {
        class: "mmc-add",
        title: t("Throw away the current stack and use this one instead."),
        text: t("Replace"),
        onclick: () => this.applyStack(entries, { replace: true }),
      }),
      el("button", {
        class: "mmc-del", text: t("Delete"),
        title: t("Delete the “{name}” stack", { name: row.name }),
        onclick: (event) => this.armDelete(event.currentTarget, row),
      }),
    ]);
  }

  /** Two clicks, because a stack is somebody's work and there is no undo behind
   *  this window. The same arming, and the same classes, as the picker's. */
  armDelete(button, row) {
    if (button.classList.contains("armed")) {
      deletePreset(row.id).then(() => this.loadStacks());
      return;
    }
    button.textContent = t("Delete for good");
    button.classList.add("armed");
    setTimeout(() => {
      if (!button.isConnected) return;
      button.textContent = t("Delete");
      button.classList.remove("armed");
    }, 3000);
  }

  /**
   * Put a saved stack on this node.
   *
   * Replace is what a preset does everywhere else — `presets.applyToPiece` and
   * its two siblings assign the section over whatever was there — and Add is the
   * thing this window can offer that the library cannot: you are looking at the
   * stack, so merging into it is a decision you can actually see the result of.
   * A file already in the stack keeps the settings it has; the one on screen is
   * the one you were just working on.
   */
  applyStack(entries, { replace }) {
    if (replace) this.state.loras = [];
    for (const entry of entries) {
      if (S.findLora(this.state, entry.name)) continue;
      this.state.loras.push(JSON.parse(JSON.stringify(entry)));
    }
    // The applied entries carry their own strengths and words, so nothing here
    // was "restored" from memory — the note would be pointing at the wrong
    // source. Their settings are written *into* memory by `changed`, which is
    // right: a stack you applied is a setup you used.
    for (const entry of entries) this.restored.delete(entry.name);
    this.changed();
    this.setTab("loras");
    this.renderGrid();
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
