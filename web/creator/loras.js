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
import { forgetLoraNames } from "./turbo.js";
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

/**
 * The slider's span, and what one notch of it is worth.
 *
 * A style LoRA lives inside ±2 and wants a fine notch there. A slider LoRA —
 * age, weight, detail, the ones trained as a signed axis — is meant to be
 * driven to ±10 and sometimes past it, and one track stretched to cover both is
 * a track where the whole useful range of every ordinary LoRA is four pixels
 * wide. So the span is a setting on the card rather than a constant here, and
 * every span keeps roughly eighty notches across the same width: the drag feels
 * identical at every scale and only the units under it change.
 */
const SCALES = [
  { span: 2, step: 0.05 },
  { span: 5, step: 0.1 },
  { span: 10, step: 0.25 },
  { span: 25, step: 0.5 },
];
const MAX_STRENGTH = SCALES[SCALES.length - 1].span;

/** The smallest span that holds a value — what a card opens on when memory or a
 *  sidecar hands it a weight the default span cannot show. */
function scaleFor(value) {
  const at = SCALES.findIndex((scale) => Math.abs(value) <= scale.span + 1e-9);
  return at < 0 ? SCALES.length - 1 : at;
}

/** A LoRA trained as a signed axis rather than a style, which is the one kind
 *  the default span is wrong for. Nothing records this in a field, but the
 *  people who train them say so in the name or the tags, every time. */
const SLIDER_HINT = /(?:^|[^a-z0-9])sliders?(?:[^a-z0-9]|$)/i;
const looksLikeSlider = (row) =>
  SLIDER_HINT.test([row.name, row.title, ...(row.tags || [])].filter(Boolean).join(" "));

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

// ---- versions ---------------------------------------------------------------
//
// One model's files, as one card.
//
// A LoRA that has been retrained four times is four files on disk, and it was
// four cards in the grid — four all-but-identical thumbnails under four
// identical titles, with nothing on any of them saying which was which or that
// the other three existed. Picking the right one meant reading four filenames
// off four cards and knowing the trainer's naming habits.
//
// Civitai's model id settles it wherever a sidecar carries one: every version
// of a model shares it and no two models do. Everything else — a folder of
// hand-trained files nothing has ever described — falls back to the filename,
// which is where the version is written anyway. `dreamscape_v1`,
// `dreamscape-v2` and `dreamscape_v2_000012` all reduce to `dreamscape` once
// the tail is taken off.
//
// That fallback is deliberately kept inside one folder. Two people's `style_v1`
// in two folders are two different LoRAs, and a card that merged them would be
// a card that lies about what you are choosing between.

/** Tails that name a *version* of one model rather than a different model.
 *  Deliberately narrow: a group that is too eager hides a file, and a file
 *  hidden inside the wrong card is worse than a file with its own card. */
const VERSION_TAIL =
  /[-_. ]+(?:v(?:er)?[.\-_]?\d+(?:[._]\d+)*|e(?:p|poch)?[-_]?\d+|step[-_]?\d+|\d{2,6}|rank\d+|dim\d+|final|last|fp16|fp8|bf16|pruned)$/i;

/**
 * The half of a split model this file is, or "".
 *
 * Wan's two-transformer LoRAs ship as a high-noise file and a low-noise one,
 * and a text-to-video LoRA and its image-to-video sibling are routinely
 * published under one model id. Those are not versions of each other: the pair
 * goes in the stack *together*, and grouping them would put a card in the grid
 * offering a choice between two files you need both of.
 */
function roleOf(name) {
  const stem = baseName(name).toLowerCase();
  const marks = [];
  if (/(^|[^a-z])high([^a-z]|$)|highnoise/.test(stem)) marks.push("high");
  else if (/(^|[^a-z])low([^a-z]|$)|lownoise/.test(stem)) marks.push("low");
  if (/(^|[^a-z])t2v([^a-z]|$)/.test(stem)) marks.push("t2v");
  else if (/(^|[^a-z])i2v([^a-z]|$)/.test(stem)) marks.push("i2v");
  return marks.join("+");
}

function groupKey(row) {
  const role = roleOf(row.name);
  if (row.model_id) return `model:${row.model_id}|${role}`;
  let stem = baseName(row.name).toLowerCase();
  // Repeatedly: `dreamscape_v2_000012_fp16` wears three of these tails at once.
  for (let pass = 0; pass < 4; pass += 1) {
    const next = stem.replace(VERSION_TAIL, "");
    if (next === stem || next.length < 3) break;
    stem = next;
  }
  return `stem:${folderOf(row.name)}/${stem}|${role}`;
}

/** Natural order, so v2 sorts before v10 rather than after it. */
function naturally(a, b) {
  const chunks = (text) => text.toLowerCase().match(/\d+|\D+/g) ?? [];
  const left = chunks(a);
  const right = chunks(b);
  for (let at = 0; at < Math.max(left.length, right.length); at += 1) {
    const one = left[at] ?? "";
    const two = right[at] ?? "";
    if (one === two) continue;
    const numeric = /^\d/.test(one) && /^\d/.test(two);
    return numeric ? Number(one) - Number(two) : (one < two ? -1 : 1);
  }
  return 0;
}

/**
 * What to call each file on the pills: the part that is not shared with its
 * siblings.
 *
 * The card already carries the model's name in its title, and a pill repeating
 * it is a pill you cannot read at 230px. What you are actually choosing between
 * is the tail — `v1` against `v2` against `v2_lite` — so the common head comes
 * off and the difference is what is left. Trimmed back to a word boundary, so a
 * pair that diverges mid-word (`...v1` / `...v15`) does not read as `` / `5`.
 */
function commonHead(stems) {
  // One file shares its whole name with itself: there is nothing to take off,
  // and trimming back to a separator anyway would leave a card titled "dream"
  // over a file called dream_scape.
  if (stems.length < 2) return stems[0] ?? "";
  let head = stems[0];
  for (const stem of stems.slice(1)) {
    let at = 0;
    while (at < head.length && at < stem.length
           && head[at].toLowerCase() === stem[at].toLowerCase()) at += 1;
    head = head.slice(0, at);
  }
  return head.replace(/[^-_. ]*$/, "").replace(/[-_. ]+$/, "");
}

function versionLabels(stems) {
  if (stems.length < 2) return stems;
  const head = commonHead(stems);
  const labels = stems.map((stem) => stem.slice(head.length).replace(/^[-_. ]+/, ""));
  // One of the files is named exactly the shared head — `thing` beside
  // `thing_final` — so its pill would be blank. Everything falls back to the
  // whole stem rather than one pill with nothing on it.
  return labels.every(Boolean) ? labels : stems;
}

/**
 * Rows in, cards out. Every group carries its members in version order and the
 * short label each of them wears.
 *
 * Built off whatever the grid is currently showing, filter included: a search
 * for "v2" narrows the pills to the v2s, which is the same promise the grid has
 * always made about the cards.
 */
function groupRows(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = groupKey(row);
    if (!groups.has(key)) groups.set(key, { key, members: [] });
    groups.get(key).members.push(row);
  }
  for (const group of groups.values()) {
    group.members.sort((a, b) => naturally(a.version || baseName(a.name),
                                           b.version || baseName(b.name)));
    const stems = group.members.map((row) => row.base || baseName(row.name));
    group.labels = new Map(
      versionLabels(stems).map((label, at) => [group.members[at].name, label]));
    // The newest is the one a card opens on when nothing else decides it, and
    // the sort above put it last.
    group.newest = group.members[group.members.length - 1].name;
    // A model's title is the model's and not the version's. A sidecar knows the
    // difference; a folder of bare filenames does not, so the shared head of
    // the names stands in for it — which is the same string the pills were cut
    // away from, so card and pills together spell each filename back out.
    const titled = group.members.find((row) => row.title);
    group.title = titled?.title || commonHead(stems)
      || stems.reduce((shortest, stem) => (stem.length < shortest.length ? stem : shortest));
  }
  return [...groups.values()];
}

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

/** One entry: the mute, the weight, the swap and the ✕.
 *
 *  `turbo` is the file the turbo switch owns, when this stack is the one it
 *  throws its LoRA into. That entry is an ordinary entry and stays in the rail
 *  — the rail is the account of what is patched onto the run, and one that drew
 *  only some of it is one you cannot read as an answer — but it is not a LoRA
 *  anybody picked, and drawn like the rest it read as one somebody had. So it
 *  wears the switch's own bolt and the switch's own word, and the file is in
 *  the tooltip: the same trade the pill made when the filename came off it,
 *  where forty characters of `..._turbo_v4_step600_ema_pruned` crowded out
 *  everything the row was for. */
function loraChip(entry, { targets = null, family = S.DEFAULT_VIDEO_FAMILY, turbo = null,
                           onToggle, onManage, onSwap, onRemove }) {
  const isTurbo = Boolean(turbo) && entry.name === turbo;
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
      : isTurbo
        ? t("{name} — the distillation the turbo switch threw on. Muting or "
            + "removing it here switches turbo off and puts the sampler row back.",
            { name: entry.name })
        : entry.name,
  }, [
    el("span", { class: "mmc-asset-thumb" }, [svg(isTurbo ? ICONS.bolt : ICONS.effect, 15)]),
    // The name is the mute. Whether a LoRA is the reason the last render looked
    // like that is a question you ask a dozen times an hour, and the only
    // control that used to answer it was the ✕ — which takes the strength, the
    // checkpoint and the trigger words with it.
    loraName(entry, () => onToggle(entry), isTurbo ? t("turbo") : null),
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
function loraName(entry, onToggle, label = null) {
  const off = entry.enabled === false;
  return el("button", {
    class: "mmc-asset-handle mmc-asset-name",
    "aria-pressed": off,
    // The file either way, muted or not: the chip is what a stack is read off,
    // and a name shortened to a word still has to say which file it is when
    // asked. Only the face is the switch's word.
    title: off
      ? t("{name} is muted — out of the run, and kept exactly as you set it up. Click to bring it back.",
          { name: baseName(entry.name) })
      : t("{name} — click to mute it: out of the run, but its strength, checkpoint and triggers stay.",
          { name: baseName(entry.name) }),
    text: label ?? baseName(entry.name),
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
    this.cards = new Map();   // group key -> the card element currently in the grid
    this.groups = [];
    this.groupAt = new Map(); // file name -> the group it is a version of
    // Which version each card is showing, for this sitting. The one that
    // outlives the window is `prefs.pinned`; this is what a click on a pill
    // does, which is a way of looking rather than a decision to keep.
    this.picked = new Map();  // group key -> file name
    // The slider span each card is on, likewise for this sitting only until it
    // is written to memory with everything else the LoRA was set to.
    this.scales = new Map();  // file name -> index into SCALES
    this.shown = 0;
    this.loaded = false;
    // Which LoRAs on screen were set up from memory rather than from their
    // sidecar, so the card can say so — a slider sitting somewhere the file's
    // author did not put it is otherwise unexplained.
    this.restored = new Set();
    this.tab = "loras";
    // Until the prefs land: no favorites, nothing remembered, browsing
    // everything. The grid says "Loading…" over all of it anyway.
    this.prefs = { folder: "", favorites: [], used: {}, pinned: {} };
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
    // Rescan reaches every copy of the list: the turbo pickers hold the names
    // for the life of the page, and "look again" includes them.
    if (force) forgetLoraNames();
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
        // The span the card was left on, not just the one you clicked to: a
        // slider LoRA recognised by its name should still open wide next week,
        // when nothing has been clicked at all.
        scale: Number.isFinite(entry.strength) ? this.scaleOf(entry, row) : (previous?.scale ?? null),
        on: [...(entry.triggers ?? [])],
        // Remembered beside the strength and for the same reason: which files
        // drag the sound is a property of the collection, learned once.
        audio: Number.isFinite(entry.audio) ? entry.audio : null,
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
    if (Number.isFinite(memory?.audio)) entry.audio = memory.audio;
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

  // ---- versions ------------------------------------------------------------

  /**
   * Which of a model's files the card is showing.
   *
   * What is in the stack outranks what is pinned, because the controls under
   * the pills edit that entry — a card showing v1 while v2 is the file being
   * patched onto the run would put the strength slider under the wrong name.
   * A click on a pill outranks both: that is you asking to look at one.
   */
  shownIn(group) {
    const held = (name) => name && group.members.some((row) => row.name === name);
    const picked = this.picked.get(group.key);
    if (held(picked)) return picked;
    const active = group.members.find((row) => S.findLora(this.state, row.name));
    if (active) return active.name;
    const pinned = this.prefs.pinned?.[group.key];
    return held(pinned) ? pinned : group.newest;
  }

  /**
   * Turn a card to one of its versions.
   *
   * With none of this model in the stack that is only a way of looking. With
   * one of its versions in the stack it is a swap in place — the same slot, the
   * strength you dialled in, the checkpoint you pinned it to, a different file
   * — because that is the whole of what changing a version means, and doing it
   * by hand used to be: find the old card, remove it, find the new one, add it,
   * and set the strength again from memory.
   *
   * The one case where a model is legitimately in a stack twice is the split
   * families — a high-noise file beside its low-noise half — and `roleOf` has
   * already given those two cards of their own. So inside one card there is
   * nothing else a version click could mean.
   */
  pick(group, name) {
    this.picked.set(group.key, name);
    const active = group.members.find((row) => S.findLora(this.state, row.name));
    if (active && active.name !== name) this.switchTo(active.name, name);
    this.refreshCard(group.members[0]);
  }

  /**
   * Run a different file in an entry's slot.
   *
   * Not the same deal as `swapTo`, which is "this is a different LoRA" and lets
   * the new file bring its own everything. A version switch is the same LoRA,
   * later: the weight you settled on is the weight you still want, so it
   * survives. The trigger words do not — a retrain routinely renames them, and
   * carrying the old ones across would put words in the prompt that the file
   * now loaded has never been trained on.
   */
  switchTo(from, to) {
    const was = S.findLora(this.state, from);
    const already = S.findLora(this.state, to);
    const row = this.rows.find((candidate) => candidate.name === to);
    const strength = was?.strength;
    const entry = S.replaceLora(this.state, from, to, row?.trained_words ?? [],
                                row?.strength ?? null, this.family);
    // `replaceLora` hands back the existing entry when the target was already
    // in the stack; that one is somebody's setup and is left alone.
    if (entry && !already) {
      if (Number.isFinite(strength)) entry.strength = strength;
      const memory = this.memoryOf(to);
      if (memory?.on?.length) entry.triggers = [...memory.on];
    }
    this.restored.delete(from);
    this.changed();
  }

  /**
   * Keep one version as the one this model opens on.
   *
   * A pin is about the collection rather than about this piece: "of the four
   * files I have of this, that is the one I use". So it outlives the window and
   * every piece in it, and the only thing that overrides it is a version
   * actually being in the stack you are looking at.
   */
  togglePin(group, name) {
    const pinned = { ...(this.prefs.pinned ?? {}) };
    if (pinned[group.key] === name) delete pinned[group.key];
    else pinned[group.key] = name;
    this.prefs.pinned = pinned;
    this.writePrefs();
    this.refreshCard(group.members[0]);
    return pinned[group.key] ?? null;
  }

  /**
   * The pills: one per file this model has on disk, each wearing only the part
   * of its name the others do not share.
   *
   * This row is the whole of what the grouping costs. Four retrains used to be
   * four cards saying the same title four times over; they are now four words
   * you can read at a glance and click between, with the one you are running
   * lit and the one you keep marked.
   */
  versionRow(group, shown) {
    const pinned = this.prefs.pinned?.[group.key];
    const label = (row) => group.labels.get(row.name) || baseName(row.name);
    // Whether clicking a pill is a swap or only a look, which is the one thing
    // the tooltips have to be straight about.
    const running = group.members.some((row) => S.findLora(this.state, row.name));
    const pills = group.members.map((row) => {
      const active = Boolean(S.findLora(this.state, row.name));
      const here = row.name === shown.name;
      return el("button", {
        class: `mmc-ver${active ? " on" : ""}`,
        "aria-pressed": here,
        title: here ? row.name
          : active ? t("{name} — in the stack.", { name: row.name })
          : running ? t("Run {name} instead. The strength and the checkpoint come with it.",
                        { name: row.name })
          : t("Show {name}", { name: row.name }),
        text: label(row),
        onclick: (event) => { event.stopPropagation(); this.pick(group, row.name); },
      });
    });
    if (!this.swapping) {
      const kept = pinned === shown.name;
      pills.push(el("button", {
        class: `mmc-ver-pin${kept ? " on" : ""}`,
        title: kept
          ? t("{label} is the version this card opens on. Click to stop keeping it.",
              { label: label(shown) })
          : t("Open this card on {label} from now on.", { label: label(shown) }),
        onclick: (event) => { event.stopPropagation(); this.togglePin(group, shown.name); },
      }, [svg(ICONS.pin, 12)]));
    }
    return el("div", { class: "mmc-vers" }, pills);
  }

  /** The sheet, told what else this model has on disk so its Versions list can
   *  be the thing you switch with rather than a list of what exists. */
  openDetail(group, row) {
    return openLoraDetail(row, {
      versions: group.members.map((member) => ({
        row: member,
        label: group.labels.get(member.name) || baseName(member.name),
      })),
      pinned: this.prefs.pinned?.[group.key] ?? null,
      isActive: (name) => Boolean(S.findLora(this.state, name)),
      onPick: (name) => this.pick(group, name),
      onPin: (name) => this.togglePin(group, name),
    });
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
    const group = this.groupAt.get(row.name);
    if (!group) return;
    const current = this.cards.get(group.key);
    if (!current) return;
    const next = this.card(group);
    current.replaceWith(next);
    this.cards.set(group.key, next);
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

    this.groups = groupRows(rows);
    this.groupAt.clear();
    for (const group of this.groups) {
      for (const row of group.members) this.groupAt.set(row.name, group);
    }
    this.pending = this.groups;
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
    const at = this.pending.findIndex(
      (group) => group.members.some((row) => row.name === name));
    if (at < 0) return;
    // The card is a model now, so revealing a file also means turning the card
    // to it — otherwise the grid scrolls to a thumbnail of the wrong version.
    this.picked.set(this.pending[at].key, name);
    while (this.shown <= at && this.shown < this.pending.length) this.appendChunk();
    const card = this.cards.get(this.pending[at].key);
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
    for (const group of batch) {
      const card = this.card(group);
      this.cards.set(group.key, card);
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

  card(group) {
    const name = this.shownIn(group);
    const row = group.members.find((candidate) => candidate.name === name) ?? group.members[0];
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
        if (double) this.openDetail(group, row);
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

    // The title is the model's and the sub line is this file's: with four
    // versions on one card the name has to stop moving when you click between
    // them, or the pills read as four different LoRAs rather than one.
    const meta = [row.base_model, row.version].filter(Boolean).join(" · ");
    const body = el("div", { class: "mmc-lora-body" }, [
      el("div", { class: "mmc-lora-name", text: group.title || row.base, title: row.name }),
      el("div", { class: "mmc-lora-sub", text: meta || row.name, title: row.name }),
    ]);
    if (group.members.length > 1) body.appendChild(this.versionRow(group, row));
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

  // ---- strength ------------------------------------------------------------

  /**
   * The span this LoRA's slider covers, decided once and then yours.
   *
   * Picked for you the first time: a file whose own name says "slider" opens at
   * ±10, a file your last setup or its sidecar put at 6.5 opens wide enough to
   * show 6.5, and everything else opens at ±2 — where an ordinary LoRA's whole
   * useful range finally gets the full width of the track instead of the middle
   * fifth of it.
   *
   * Never narrower than the weight it has to display, whatever was remembered:
   * a track that cannot reach the number beside it is a broken control.
   */
  scaleOf(entry, row) {
    const needed = scaleFor(entry.strength);
    const held = this.scales.get(entry.name);
    if (held !== undefined) return Math.max(held, needed);
    const memory = this.memoryOf(entry.name);
    const start = Number.isFinite(memory?.scale)
      ? memory.scale
      : (row && looksLikeSlider(row) ? scaleFor(10) : 0);
    return Math.max(start, needed);
  }

  setScale(entry, row, at) {
    this.scales.set(entry.name, at);
    this.refreshCard(row);
    this.changed();
  }

  /** From the typed box rather than the track, so it may name a weight the
   *  current span cannot reach — the span follows rather than clipping it. */
  setStrength(entry, row, value) {
    const held = Math.max(-MAX_STRENGTH, Math.min(MAX_STRENGTH, value));
    entry.strength = Math.round(held * 100) / 100;
    this.scales.set(entry.name, this.scaleOf(entry, row));
    this.refreshCard(row);
    this.changed();
  }

  /**
   * The weight: a track, the number it is on, and the span the track covers.
   *
   * The number is typed rather than read, because no track is the right one for
   * every LoRA and there has to be one control that always reaches the value
   * you mean. The span is a button rather than a hidden constant for the same
   * reason the pills exist — the thing that differs between two files should be
   * the thing on screen.
   */
  strengthBox(entry, row) {
    const at = this.scaleOf(entry, row);
    const scale = SCALES[at];
    const readout = el("input", {
      class: "mmc-lora-num",
      type: "text", inputmode: "decimal", spellcheck: "false",
      value: entry.strength.toFixed(2),
      title: t("The weight this LoRA is patched on at. Type any value from -{max} to {max}.",
               { max: MAX_STRENGTH }),
      onchange: (event) => {
        const typed = Number(String(event.target.value).replace(",", ".").trim());
        if (Number.isFinite(typed)) this.setStrength(entry, row, typed);
        else event.target.value = entry.strength.toFixed(2);
      },
      onkeydown: (event) => { if (event.key === "Enter") event.target.blur(); },
      onkeyup: (event) => event.stopPropagation(),   // the graph canvas reads keys
    });
    const span = el("button", {
      class: "mmc-lora-span",
      text: `±${scale.span}`,
      title: t("The track runs -{span} to {span} in steps of {step}. Click to widen it: "
             + "slider LoRAs are trained to be driven well past where a style LoRA stops.",
             { span: scale.span, step: scale.step }),
      onclick: () => this.setScale(entry, row,
        at + 1 >= SCALES.length ? scaleFor(entry.strength) : at + 1),
    });
    const slider = el("input", {
      type: "range", min: -scale.span, max: scale.span, step: scale.step,
      value: entry.strength,
      // Dragging must not re-render the card out from under the pointer, so the
      // readout is updated by hand and only the release reserialises.
      oninput: (event) => {
        entry.strength = Number(event.target.value);
        readout.value = entry.strength.toFixed(2);
      },
      onchange: () => this.changed(),
      onpointerdown: (event) => event.stopPropagation(),
    });
    return { readout, span, slider };
  }

  /**
   * How much of this LoRA reaches the soundtrack.
   *
   * H3 runs video and audio through one tower, so an adapter conditions the
   * sound whether it was trained to or not — and it was trained to: video and
   * audio latents are denoised jointly, so a file built from clips with silent
   * or scraped audio has learned that as surely as it learned the face. The
   * symptom is mumbling under a shot in which nobody was meant to speak.
   *
   * Not a mute, and the label does not promise one: attention is joint over the
   * packed sequence, so turning this down damps where the LoRA is applied
   * rather than everything it eventually reaches. See `lora.modality`.
   */
  audioBox(entry, row) {
    // Read rather than written: full is the default, and a card that has only
    // been *looked at* should not leave a setting behind in the saved piece.
    const audio = Number.isFinite(entry.audio) ? entry.audio : 1;
    const readout = el("output", { class: "mmc-lora-read", value: audio.toFixed(2) });
    const slider = el("input", {
      type: "range", min: 0, max: 1, step: 0.05, value: audio,
      // Same reason as the strength slider: a re-render mid-drag takes the
      // pointer's target out from under it.
      oninput: (event) => {
        entry.audio = Number(event.target.value);
        readout.value = entry.audio.toFixed(2);
      },
      onchange: () => this.changed(),
      onpointerdown: (event) => event.stopPropagation(),
    });
    return el("div", { class: "mmc-lora-sound" }, [
      el("div", { class: "mmc-lora-row" }, [
        el("span", {
          class: "mmc-lora-label",
          title: t("How much of this LoRA reaches the soundtrack. Turn it down "
                   + "for a file whose training clips had poor sound: H3 generates "
                   + "picture and sound together, so an adapter carries what it "
                   + "heard as well as what it saw. It damps rather than mutes."),
          text: t("Soundtrack"),
        }),
        readout,
      ]),
      slider,
    ]);
  }

  controls(entry, row) {
    // A hand-edited creator_data can carry anything; the slider needs a number.
    if (!Number.isFinite(entry.strength)) entry.strength = S.DEFAULT_STRENGTH;
    const { readout, span, slider } = this.strengthBox(entry, row);
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
        el("span", { class: "mmc-lora-label", text: t("Strength") }), mute, span, readout]),
      slider,
      ...(this.checkpointModes ? [modes] : []),
      ...(S.loraAudioOf(this.family) ? [this.audioBox(entry, row)] : []),
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
