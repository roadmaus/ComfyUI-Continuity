// The settings page: the preferences that belong to this ComfyUI rather than to
// a workflow. Opened from the rail's Settings tool, beside the Gallery.
//
// The line it draws is `settings.py`'s: a workflow says what the piece is, and
// this says how this machine writes it. Nothing here is saved into creator_data,
// so a `.json` shared with someone else renders the same shot at whatever
// quality their own copy of ComfyUI is set to.
//
// Every control writes through the moment it is touched — the same deal the LoRA
// manager has, and for the same reason: a page with a Save button has a state
// where what you see and what is stored disagree, and Done is then two different
// promises. Done here only closes.
//
// The server is the only copy. Nothing is cached between openings: the file can
// be edited by hand, and a page that showed a remembered value would be showing
// something the next render will not use.
//
// One page, read down like a ledger. It was tabs while it held three settings;
// at sixteen, a tab called General was holding ten of them and each was a card
// of every option's explanation, so nothing could be found without scrolling
// and nothing read at a glance. Now every setting is one line — its name on the
// left, the choice on the right, and under it the note for the option that is
// in force — and an index down the side names the five groups: what a render
// writes, how it is sampled, what a node face draws, how the pack is drawn, and
// what the pack is holding. What you see is what is set; the other options'
// notes wait on the pointer.

import { el, mountOverlay } from "./dom.js";
import { loadSettings, saveSettings, resetSettings, noteSettings, loadLatentCache,
         clearLatentCache, clearPickerPrefs, pickerPrefsHeld, clearLoraPrefs,
         loraPrefsHeld, neuralStatus, neuralCheck, neuralExtract } from "./api.js";
import * as P from "./presets.js";
import { resetSettings as resetRefiner, settingsStored as refinerStored,
         remoteStatus, saveRemote } from "./refine.js";
import { forgetLayout, layoutPrefsHeld } from "./fullscreen.js";
import { t } from "./i18n.js";
import { CLOCK_TOKENS, FRAME_TOKENS, cleanPrefix, folderOf, stemOf, examplePath,
         splitTokens, tokenLabel, tokenValues } from "./outputs.js";
import { FAMILIES } from "./manifest.js";

// libx264's own quality scale: lower is better and bigger, and six points is
// roughly double the file size. Four points on it, because the encoder's full
// 0–51 makes forty useless values as reachable as the four good ones — the size
// claims below all come off that one rule, so the rows cannot drift apart.
//
// `settings.py` decides what is *allowed* (the whole scale, so a hand-edited
// file is honoured); this decides what is *offered*.
const QUALITY = [
  { crf: 28, label: "Draft",
    note: "Smallest files, about half of Standard. Fine for checking timing; "
        + "banding shows up in dark gradients." },
  { crf: 23, label: "Standard",
    note: "What libx264 picks on its own, and what this pack wrote before the "
        + "setting existed." },
  { crf: 18, label: "Fine",
    note: "About twice the size of Standard. Hard to tell from the frames the "
        + "sampler handed over." },
  { crf: 14, label: "Archival",
    note: "About three times the size of Standard. Keeps the grain and fine "
        + "texture H.264 usually eats first." },
];

// The turbo lead-in, in steps: how much of a distilled render's opening is
// sampled on the base weights. `settings.py` decides what is allowed (up to
// four); these are the three answers worth clicking. Four is the default and
// the measured best: on an 8-hop strip the step at each cut fell from +2.86
// with it off to +0.98, and the texture ratchet fell with it.
// The motion fix's gate, as the line a shot has to clear rather than as a
// number: the two rows either side of the default sit against the two clips
// it was measured on (`derope.GATE` says which). Peak frame-to-frame change at
// thumbnail scale, 0-255.
const MOTION_GATE = [
  { value: 0, label: "Every shot",
    note: "No line. A calm shot is re-drawn too, and comes back sharper but "
        + "moving wrongly — measured on a fern stirring in a draught. For "
        + "trying the pass out, not for a strip." },
  { value: 1.5, label: "Gentle motion",
    note: "Under the fern. A walk, a turn of the head and a slow pan all go "
        + "through the pass; none of them has been measured there." },
  { value: 2.5, label: "Fast motion",
    note: "The default, between the two measured clips: a spinning kick reads "
        + "4.4, the fern 1.9." },
  { value: 4, label: "Fastest only",
    note: "Just under the kick. A brisk gesture is left alone, and a burst "
        + "slower than that kick may be too." },
];

const LEAD_IN = [
  { steps: 0, label: "Off",
    note: "The whole schedule runs on the distillation, which is what a turbo "
        + "render was before the lead-in existed. Fastest, and drifts the most "
        + "down a strip." },
  { steps: 2, label: "Two steps",
    note: "A quarter of the way there at 8 steps, for about a quarter of what "
        + "the distillation saved." },
  { steps: 4, label: "Four steps",
    note: "The default. Half of an 8-step schedule on the base weights, which is "
        + "where the seam step was measured smallest and the texture cleanest. "
        + "Costs those four steps at full speed." },
];

// How large the pack draws its own text, as the multiplier `--mmc-type` carries
// (styles/base.js). Four points, because a slider over a continuum of type sizes
// is a control you tune rather than choose — and there are only about four
// answers here: a step down, the sizes as drawn, and two steps up for a screen
// you are sitting further from than the person who drew them was.
//
// `settings.py` decides what is *allowed* (0.8 to 1.6, so a hand-edited file can
// go further); this decides what is *offered*.
const TEXT_SCALE = [
  { scale: 0.92, label: "Small",
    note: "A step down: more of a node face, a longer strip of takes, and a "
        + "little more of the picker's grid before it scrolls." },
  { scale: 1, label: "Default",
    note: "Every size in the pack as it was drawn." },
  { scale: 1.12, label: "Large",
    note: "The one to try first on a 4K screen at native resolution, where this "
        + "pack is drawn a step smaller than the rest of the desk." },
  { scale: 1.25, label: "Largest",
    note: "A quarter again. Reads across a room; a node face on the canvas holds "
        + "less before it scrolls, because the face is the size the graph gives "
        + "it and only what is inside it grows." },
];

// What the pack may wear. Two answers, not three: "follow" is right for almost
// everybody and is what the stylesheet does unaided, and the case for pinning is
// specific enough to name on its own row. There is no "light" — a light editor
// over a dark graph is the one combination nobody asks for, and offering it
// would only be symmetry for its own sake.
//
// The pin reaches the fullscreen editor and nothing else, which is not a
// limitation so much as the whole of where it makes sense: a node body sits
// inside a node ComfyUI draws in its own palette, so a dark body on a light desk
// is a dark island in a white card rather than a dark editor. The shell covers
// the viewport and has no such argument to lose.
//
// `settings.py` decides what is allowed; this decides what is offered, and here
// they happen to be the same two.
const THEMES = [
  { value: "follow", label: "Follow ComfyUI",
    note: "Every colour this pack draws comes from the palette in ComfyUI's own "
        + "Appearance settings, so the pack changes when the desk does — "
        + "including palettes you made yourself." },
  { value: "dark", label: "Dark in fullscreen",
    note: "Node faces still follow the palette, but the fullscreen editor keeps "
        + "a dark ground. For judging pictures: a frame read against white is "
        + "read against the wrong thing, which is why the tools that cut and "
        + "grade are dark." },
];

// How far the surfaces step off the ground. A tuned control rather than a chosen
// one, like the text scale, and for the same reason it is offered as a handful
// of points: the useful range is narrow and the difference between neighbouring
// points is visible on screen the moment you pick one.
const SURFACE_LIFT = [
  { lift: 0.6, label: "Flat",
    note: "The cards barely leave the ground. Quietest on a palette that already "
        + "has plenty of contrast of its own." },
  { lift: 1, label: "Default",
    note: "The ladder as drawn." },
  { lift: 1.4, label: "Raised",
    note: "The one to try on Github, Nord or Solarized, where the palette's own "
        + "contrast is low enough that the four surfaces read as two." },
  { lift: 1.8, label: "Highest",
    note: "Cards clearly apart from what they sit on. The most separation this "
        + "offers before they stop looking like they belong to it." },
];

export function openSettings() {
  return new Promise((resolve) => new SettingsPage(resolve).mount());
}

/** A byte count in the unit that makes it legible: "640 KB", "820 MB", "4.2 GB".
 *  Down to kilobytes for the same reason the terminal lines go there — a store
 *  holding only sound references is not holding "0 MB". */
function said(bytes) {
  const kb = Number(bytes) / 1024;
  if (kb >= 1024 * 1024) return `${(kb / (1024 * 1024)).toFixed(1)} GB`;
  if (kb >= 1024) return `${Math.round(kb / 1024)} MB`;
  return `${Math.round(kb)} KB`;
}

// The two numbers the reference cache is bounded by. Both are magnitudes, and
// both are magnitudes nobody wants to the unit: the difference between keeping
// a reference 30 days and 31 is not a decision, and neither is 8 GB against 9.
// So the rails travel a list of stops rather than a range — a week, a month, a
// year; 8 GB, 16, 32 — and a value typed into the settings file by hand is
// sorted into the list rather than rounded away, which is the rule the quality
// tiers and the text scale already live by.
//
// Labels on some stops only. A rail carrying nine of them is a rail nobody
// reads; the unlabelled ones keep their tick, so the grid is still visible and
// still clickable.
const KEEP_STOPS = [
  { value: 1, label: "1 day" },
  { value: 7, label: "1 week" },
  { value: 30, label: "1 month" },
  { value: 90, label: "3 months" },
  { value: 365, label: "1 year" },
  // Last, not first: it is the largest answer to "how long", whatever the
  // number storing it happens to be.
  { value: 0, label: "Forever" },
];

const SIZE_STOPS = [
  { value: 0, label: "Off" },
  { value: 1 }, { value: 2, label: "2" }, { value: 4 },
  { value: 8, label: "8" }, { value: 16 }, { value: 32, label: "32" },
  { value: 64 }, { value: 128, label: "128" },
];

// What the step preview may be sized and squeezed to. The long edge in pixels,
// and the encoder's own quality scale. Both are the override node's numbers, so
// the ends of these rails are the ends of what it accepts.
const PREVIEW_PX_STOPS = [
  { value: 128, label: "128" }, { value: 256 }, { value: 384, label: "384" },
  { value: 512 }, { value: 640, label: "640" }, { value: 768 },
  { value: 1024, label: "1024" },
];
const PREVIEW_Q_STOPS = [
  { value: 40, label: "40" }, { value: 50 }, { value: 60, label: "60" },
  { value: 70 }, { value: 80, label: "80" }, { value: 90 }, { value: 100, label: "100" },
];

/** How long a retention reads. The offered stops have names; a hand-typed
 *  number is simply a number of days. */
function keepFor(days) {
  const named = { 0: "Forever", 1: "1 day", 7: "1 week", 30: "1 month",
                  90: "3 months", 365: "1 year" };
  return named[days] ? t(named[days]) : t("{days} days", { days: Number(days) });
}


/** What each preset scope is, in the words somebody deciding whether to keep it
 *  needs. Beside `SCOPE_LABEL` rather than in it: that one names a tab, and a
 *  tab is not a warning. */
const PRESET_ROW = {
  piece: { name: "Pieces",
           note: "Whole timelines you saved: the strip, the cast, the weights and "
               + "the settings that rendered them." },
  shot: { name: "Shots",
          note: "One card's worth — its prompt, its duration and its seam." },
  prestage: { name: "Pre-stages",
              note: "A still and the arch that made it." },
  cast: { name: "Cast",
          note: "People you kept, with the files they are built out of and every "
              + "feature written down about them." },
  style: { name: "Styles",
           note: "A look on its own, without the piece it came off — and the stars "
               + "on the shipped atlas." },
};

/** What each group is and who else it belongs to. The heading has to answer
 *  "where does this live" before a press can be an informed one. */
const GROUP_TITLE = {
  "The library": {
    title: "Preset library",
    note: "Everything you starred into the preset library. It is stored against "
        + "your ComfyUI user rather than in a workflow, so it follows you across "
        + "browsers — and nothing else carries it, which is why it is the half of "
        + "this page worth reading twice.",
  },
  "This browser": {
    title: "This browser",
    note: "What the pack remembers about the way you work, rather than about "
        + "what you made. Losing any of it costs a few clicks, never a file.",
  },
  "This machine": {
    title: "This machine",
    note: "Files on this disk and settings this install renders by. Shared by "
        + "every workflow that opens here, and by nobody else.",
  },
};

/**
 * Everything this pack has written down, one row each.
 *
 * The list is the whole design. A settings page can only be honest about what
 * it is holding if it says so item by item — so each row reports what is
 * actually there before it offers to remove it, and a row with nothing behind
 * it is visibly inert rather than a button that would silently do nothing.
 *
 * `held` reads the inventory the page loaded; `remove` is the one that acts.
 * "Remove everything" below is nothing but this list run in order, which is why
 * there is no second description of what everything means.
 *
 * `group` is where it lives, because where a thing lives is what you need to
 * know before throwing it away: the library follows the ComfyUI user across
 * browsers, the browser rows are this machine's browser alone, and the machine
 * rows are files on this disk that a render reads.
 */
const STORED = [
  ...P.SCOPES.map((scope) => ({
    id: `preset:${scope}`,
    group: "The library",
    name: PRESET_ROW[scope].name,
    note: PRESET_ROW[scope].note,
    held: (kept) => kept.presets?.[scope] ?? 0,
    remove: () => P.deletePresets(scope),
  })),
  {
    id: "picker",
    group: "This browser",
    name: "Picker stars and folders",
    note: "Starred files, the folder each picker tab opens on, and how large the "
        + "fullscreen editor draws a take. No file is touched.",
    held: (kept) => kept.picker ?? 0,
    remove: async () => { await clearPickerPrefs(); forgetLayout(); },
  },
  {
    id: "loras",
    group: "This browser",
    name: "LoRA notes",
    note: "Stars, pinned versions, and the strength and trigger words each file "
        + "was last used at. The LoRAs themselves stay on the disk.",
    held: (kept) => kept.loras ?? 0,
    remove: () => clearLoraPrefs(),
  },
  {
    id: "refiner",
    group: "This machine",
    name: "Refiner choices",
    note: "Which model rewrites a prompt and answers the chat room, at what "
        + "temperature, and any template or skill pinned to a family. The "
        + "server's address and key are their own row.",
    held: (kept) => (kept.refiner ? "set" : 0),
    remove: async () => resetRefiner(),
  },
  {
    id: "cache",
    group: "This machine",
    name: "Reference cache",
    note: "Encoded references kept between renders. Deleting them costs the next "
        + "render one encode each and changes nothing about what it produces.",
    held: (kept) => (kept.cacheBytes ? said(kept.cacheBytes) : 0),
    remove: () => clearLatentCache(),
  },
  {
    id: "remote",
    group: "This machine",
    name: "Remote refiner",
    note: "The endpoint the remote refiner calls and the key it calls with. The "
        + "key never leaves this machine, and this is how it goes.",
    held: (kept) => (kept.remote ? "set" : 0),
    remove: () => saveRemote("", ""),
  },
  {
    id: "settings",
    group: "This machine",
    name: "Settings",
    press: "Reset",
    note: "Quality, output folders, previews and appearance, back to what the "
        + "pack ships with.",
    // Always offered: there is no count of "how default" a settings file is,
    // and a page cannot honestly report one.
    held: () => true,
    remove: () => resetSettings(),
  },
];

// The two-answer settings, as the same shape the tables above have: a value,
// the word on the button, and the note the row shows while that answer is the
// one in force. The notes are the long form — a segment button carries a word,
// and the word alone ("Kept") never said what it was keeping or why.
const LORA_LOADERS = [
  { value: "vendored", label: "This pack",
    note: "Keeps the quantized checkpoint exactly as baked and runs each file as an "
        + "exact branch beside it. Ports adaLN between dense and curve checkpoints, "
        + "fuses a stack into one branch, and carries the per-file audio dial." },
  { value: "core", label: "ComfyUI",
    note: "What every published workflow runs on: each layer a file touches is "
        + "dequantized, patched and requantized with fresh rounding, so the base "
        + "under a LoRA is not quite the one you loaded and the same seed can land "
        + "on a different shot. Pick this to match a result made outside this pack." },
];

const LORA_CARD_METADATA = [
  { value: false, label: "Off",
    note: "Use model metadata for card titles and subtitles." },
  { value: true, label: "On",
    note: "Use same-stem .cm-info.json labels when available; otherwise show the file name and path." },
];

const SEAM_HANDOFFS = [
  { value: "frames", label: "Frames",
    note: "The road every render took before: the tail is read off the decode "
        + "and encoded again. Kept for a side-by-side on the same strip." },
  { value: "latent", label: "Latent",
    note: "The run is sliced off what the sampler made. Nothing is decoded and "
        + "encoded again on the way, so the next shot starts from the picture "
        + "the model actually drew." },
  { value: "levelled", label: "Levelled latent",
    note: "The same slice, pulled back to the first shot's tone and contrast "
        + "before the model reads it. Each shot still drifts a little within "
        + "itself, but the next one starts where the first did, so it stops "
        + "stacking down the strip. The finished frames are not touched." },
  { value: "masked", label: "Masked latent",
    note: "The same slice, written into the next shot's own latent and held "
        + "there while the rest is sampled: the model continues the frames it "
        + "made rather than generating new ones under guidance. Measured to take "
        + "the step out of the seam, and cheaper to sample; not yet measured with "
        + "a turbo lead-in. Picture only; the sound crosses the seam as before." },
];

const PLAYBACK = [
  { value: true, label: "Plays itself",
    note: "What the stage has always done: the clip loops silently as soon as it "
        + "lands, and the sound follows the pointer." },
  { value: false, label: "Waits for play",
    note: "The finished clip holds its first frame, still, with the browser's "
        + "controls to start it. For crowded canvases, where every looping clip is "
        + "a decoder running for nobody. The step preview keeps moving either way." },
];

const ADVANCED = [
  { value: false, label: "Standard",
    note: "The sampler row as most renders use it: the seed, the recipe, the step "
        + "count and the strengths. A control you have already set still shows its "
        + "pill — it is in force, so it stays visible." },
  { value: true, label: "Everything",
    note: "Adds each family's own last few controls — H3's low VRAM, fast math and "
        + "turbo lead-in, LTX's sampler pick and its noise curve — and the turbo "
        + "lead-in to this page. For the rows where the last few percent of speed, "
        + "of VRAM or of curve is worth a decision." },
];

const SHIFT_PILLS = [
  { value: false, label: "Hidden",
    note: "The row before the shifts arrived. A value away from the checkpoints' "
        + "own schedule — a turbo preset, a loaded workflow — still shows its "
        + "pill: it is in force, so it stays visible." },
  { value: true, label: "Shown",
    note: "Two stepper pills after the scheduler, for dialling the two schedules "
        + "by hand. A turbo LoRA's card may name the values it was distilled against." },
];

const REF_CACHE = [
  { value: true, label: "Keep",
    note: "A reference is encoded once and reused until its file, the canvas it "
        + "was encoded at, or the VAE changes. Editing the prompt, the seed, the "
        + "sampler or the other references reuses it." },
  { value: false, label: "Re-encode",
    note: "What every render did before this existed. For a box with no room "
        + "to spare." },
];

// A value the settings file holds that no button offers. It takes its own
// button rather than being rounded onto a neighbour: it is in force, so it has
// to be visible, and pressing another is how you leave it.
const CUSTOM_NOTE = "Set by hand in the settings file. Pick one of the others to leave it.";

// The index down the side, in page order. The keys are what `show()` and the
// tests address a group by.
const GROUPS = [
  { key: "output", label: "Output" },
  { key: "rendering", label: "Rendering" },
  { key: "nodes", label: "Nodes" },
  { key: "interface", label: "Interface" },
  // Last, and named for what it holds rather than for how it feels about it.
  // "Danger" would be a warning with nothing behind it yet — the gravity
  // belongs on the press, where the thing actually happens.
  { key: "data", label: "Stored data" },
];



class SettingsPage {
  constructor(resolve) {
    this.resolve = resolve;
    this.settings = null;   // until the server answers
    this.cache = null;      // what the reference cache is holding, once asked
    // What is stored, by row id, once the page has been read down to the
    // inventory. Null until then: the count reads every preset index on disk,
    // and a page opened to change the video quality has no business doing that.
    this.kept = null;
    this.sweeping = false;  // the "remove everything" pass, while it runs
    // The DLSS 5 refiner's standing on this machine. Null until asked — the
    // answer hashes nothing, but it is a route, so it is asked once the page
    // has its settings and not before. `neuralBusy` names the press in flight
    // — "check" or "extract" — and `neuralNote` is what the last press said.
    this.neural = null;
    this.neuralBusy = null;
    this.neuralNote = null;
    this.problem = null;
    this.group = GROUPS[0].key;
  }

  mount() {
    this.page = el("div", { class: "mmc-set-page", onscroll: () => this.spy() });
    this.links = GROUPS.map((group) => el("button", {
      class: "mmc-set-ix",
      "aria-current": group.key === this.group,
      text: t(group.label),
      onclick: () => this.show(group.key),
    }));
    // The problem line lives in the head: a page this long can have the
    // control that failed scrolled out of view, and a refusal that lands off
    // screen is a refusal nobody reads. The head is always there.
    this.said = el("div", { class: "mmc-set-problem" });
    // No Done: every control has already written through by the time it is
    // released, so there is nothing for a press to finish — the ✕ closes.
    this.modal = el("div", { class: "mmc-modal mmc-settings" }, [
      el("div", { class: "mmc-modal-head" }, [
        el("span", { class: "mmc-set-title", text: t("Settings") }),
        this.said,
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      el("div", { class: "mmc-set-body" }, [
        el("nav", { class: "mmc-set-index", "aria-label": t("Sections") }, this.links),
        this.page,
      ]),
    ]);
    this.modal.style.position = "relative";

    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(); },
    }, [this.modal]);

    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.render();
    this.load();
  }

  async load() {
    try {
      this.settings = await loadSettings();
      noteSettings(this.settings);
    } catch (error) {
      this.problem = t("Could not read the settings — {error}", { error: error.message });
    }
    this.render();
    // Separately, and never fatally: how much disk the reference cache is
    // holding is a thing the page reports, not a thing it needs to draw. An
    // older build with no such route leaves the line off rather than the page.
    try {
      this.cache = await loadLatentCache();
      this.render();
    } catch { /* the line stays absent */ }
  }

  /** Empty the reference cache, and say what that freed. */
  async clearCache() {
    this.problem = null;
    try {
      this.cache = await clearLatentCache();
    } catch (error) {
      this.problem = t("Not cleared — {error}", { error: error.message });
    }
    this.render();
  }

  /**
   * Write one setting through, and take the server's answer over the click.
   *
   * Painted first so the button moves under the pointer, then corrected if the
   * reply disagrees. The correction is the point: a value the server refused
   * must not be left on screen looking chosen.
   */
  async set(patch) {
    const previous = this.settings;
    this.settings = { ...this.settings, ...patch };
    this.problem = null;
    // Through the cache on the way out as well as on the way back, which is the
    // deal patchSettings already has: one of these settings is drawn by the
    // stylesheet rather than by this page (the text scale, applied out of
    // noteSettings), and a control whose effect waits for a round trip is a
    // control that feels broken on a slow one. The reply below overwrites this
    // with what was actually stored, and a refusal puts `previous` back.
    noteSettings(this.settings);
    this.render();
    try {
      this.settings = await saveSettings(patch);
      // The bodies read some of these (the shift pills' visibility) off the
      // cache in api.js, so what the server actually stored goes there too.
      noteSettings(this.settings);
    } catch (error) {
      this.settings = previous;
      noteSettings(previous);
      this.problem = t("Not saved — {error}", { error: error.message });
    }
    this.render();
  }

  /** The index's press: scroll the group to the top of the page. */
  show(key) {
    this.arrive(key);
    this.page.querySelector(`.mmc-set-group[data-group="${key}"]`)
      ?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  /**
   * Which group the page is scrolled to, off the scroll position. The last
   * heading at or above the top edge is the one being read; the index follows
   * it, and reaching the inventory is what triggers the count.
   */
  spy() {
    const top = this.page.scrollTop + this.page.clientHeight * 0.3;
    let current = GROUPS[0].key;
    for (const group of this.page.querySelectorAll(".mmc-set-group")) {
      if (group.offsetTop <= top) current = group.dataset.group;
    }
    // The bottom of the page is the last group whether or not its heading has
    // reached the line: a short inventory under a long page would otherwise
    // never be "current".
    if (this.page.scrollTop + this.page.clientHeight >= this.page.scrollHeight - 2) {
      current = GROUPS[GROUPS.length - 1].key;
    }
    this.arrive(current);
  }

  arrive(key) {
    if (key === "data" && this.kept === null) this.takeStock();
    if (key === this.group) return;
    this.group = key;
    for (const [index, group] of GROUPS.entries()) {
      this.links[index].setAttribute("aria-current", String(group.key === key));
    }
  }

  /**
   * Count everything the inventory is about to offer to remove.
   *
   * Every reader is allowed to fail on its own: an install with no preset index
   * yet, a frontend with no userdata API, a server too old to answer for the
   * remote refiner. A row whose count could not be read says so and stays
   * pressable — the remove call is the one that decides, and it is idempotent.
   */
  async takeStock() {
    // Marked before the await so a second arrival does not count twice.
    this.kept = this.kept ?? false;
    const [presets, picker, loras, remote] = await Promise.all([
      P.presetCounts().catch(() => ({})),
      pickerPrefsHeld().catch(() => 0),
      loraPrefsHeld().catch(() => 0),
      remoteStatus({ force: true }).catch(() => ({ url: "", key_set: false })),
    ]);
    this.kept = {
      presets,
      picker: picker + layoutPrefsHeld(),
      loras,
      refiner: refinerStored(),
      cacheBytes: Number(this.cache?.bytes ?? 0),
      remote: !!(remote.url || remote.key_set),
    };
    this.render();
  }

  close() {
    this.unmount();
    this.resolve();
  }

  // ---- render ---------------------------------------------------------------

  render() {
    // The inventory can be counted off an unmounted page (the tests do), and
    // there is nothing to draw it on then.
    if (!this.page) return;
    this.said.textContent = this.problem ?? "";
    if (!this.settings) {
      this.page.replaceChildren(el("div", { class: "mmc-set-wait", text: this.problem ?? t("Reading settings…") }));
      return;
    }
    if (this.neural === null && !this.neuralBusy) this.loadNeural();
    this.page.replaceChildren(
      this.groupBlock("output", [this.qualityCard(), ...this.folderCards()]),
      this.groupBlock("rendering", [this.seamsCard(), this.passesCard(), this.cacheCard()]),
      this.groupBlock("nodes", [this.nodesCard()]),
      this.groupBlock("interface", [this.interfaceCard()]),
      this.groupBlock("data", this.storedCards()),
    );
  }

  // ---- output ---------------------------------------------------------------

  qualityCard() {
    const crf = this.settings.video_crf;
    return this.card("Video", [this.row({
      key: "video_crf",
      name: "Video quality",
            ...this.segment({
        options: QUALITY.map((tier) => ({ value: tier.crf, label: tier.label, note: tier.note })),
        value: crf,
        // The real encoder value, on every button. The rest of this pack shows
        // the exact filename and the exact pixel size under the friendly word;
        // a quality control that said only "Fine" would be the one place in it
        // that asks you to take an adjective on trust.
        shown: (value) => t("crf {crf}", { crf: value }),
        also: "MP4, H.264, 8-bit 4:2:0, whatever workflow made it. Six crf points is "
            + "roughly double the size. Needs ComfyUI 0.29 or newer.",
        apply: (value) => this.set({ video_crf: value }),
      }),
    })]);
  }

  /**
   * Where each family files what it makes: a card per shelf, a row per family.
   *
   * It was one row per *kind* until families arrived, and that was the bug: an
   * LTX 2.5 piece wrote `minimax/renders/H3_00021_.mp4` — the wrong shelf and
   * somebody else's name on the file. A render lands somewhere because of what
   * rendered it, so the question is asked once per family, and the families
   * come off the catalog rather than a list here: a new one gets its row by
   * existing, and gets it filled with the default the save node will use,
   * because that default is served in its manifest.
   *
   * This used to be a pill on every node, which meant every node was a place
   * the answer could differ and a shared workflow arrived carrying somebody
   * else's folder names. It is one answer per family per machine now.
   *
   * `kind` is which half of the family's `output` block holds its default —
   * H3 is in both cards and its two defaults are different folders, so the
   * fallback has to be read per card and not per family.
   */
  folderCards() {
    const shelf = (title, key, kind, extension) => {
      const families = FAMILIES.filter((family) => family.produces.includes(kind));
      return this.card(title, families.map((family) => this.folderRow(
        key, family.id, family.label, family.output?.[kind] ?? "", extension)));
    };
    return [
      shelf("Renders", "video_prefix", "video", "mp4"),
      shelf("Stills", "image_prefix", "still", "png"),
    ];
  }

  // ---- rendering ------------------------------------------------------------

  /**
   * What a blended seam hands the next shot (issues #41, #46), and how many of
   * a turbo render's opening steps run without the distillation. Both are per
   * machine rather than per node because they are statements about how a seam
   * is conditioned and how you use a distillation — the LoRA, the steps and
   * the schedule are all still the workflow's. A `.json` shared with someone
   * who leaves these at their defaults renders the defaults.
   *
   * The lead-in is an advanced control, so its row comes and goes with the
   * switch in the Nodes group — except while it is set, which is the rule the
   * pill follows too: a setting in force must be reachable from the page that
   * holds it, or it is a number changing renders with nowhere to change it
   * back.
   */
  seamsCard() {
    const handoff = this.settings.seam_handoff || "latent";
    const leadIn = Number(this.settings.turbo_lead_in) || 0;
    const rows = [this.row({
      key: "seam_handoff",
      name: "Seam handoff",
      hint: "What a blended seam hands the next shot.",
      ...this.segment({
        options: SEAM_HANDOFFS,
        value: handoff,
        also: "Every continued shot comes out a little brighter and harder than the "
            + "one it continues, and the next seam is pinned on that, so it walks "
            + "down a strip. Only blended seams between two generated shots; a seam "
            + "off a clip or a face-passed shot reads the frames either way. Read "
            + "when a render is queued.",
        apply: (value) => this.set({ seam_handoff: value }),
      }),
    })];
    if (this.settings.advanced === true || leadIn > 0) {
      rows.push(this.row({
        key: "turbo_lead_in",
        name: "Turbo lead-in",
        hint: "Opening steps with the turbo LoRA held off.",
        ...this.segment({
          options: LEAD_IN.map((row) => ({ value: row.steps, label: row.label, note: row.note })),
          value: leadIn,
          also: "Not extra steps: they come out of the count on the node. Only where "
              + "the turbo switch has engaged a LoRA — a checkpoint with the "
              + "distillation merged into its weights has none to hold off.",
          apply: (value) => this.set({ turbo_lead_in: value }),
        }),
      }));
    }
    return this.card("Seams", rows);
  }

  /**
   * The passes a render may take on the way out: the motion fix's gate, which
   * loader puts an H3 piece's LoRAs on, and the DLSS 5 refiner's standing.
   *
   * The gate is a calibration — the two clips it was measured on are named in
   * the notes — and never hidden behind the advanced switch, since a card can
   * be asking for the pass while the number that decides whether it runs has
   * nowhere to be changed. The loader was measured 2026-09-13 on int8 ConvRot:
   * ComfyUI's requantizes every layer a file touches, so the same seed lands
   * on a different shot; the vendored stack keeps the bake.
   */
  passesCard() {
    const gate = Number(this.settings.motion_fix_abstain ?? 2.5);
    const loader = this.settings.lora_loader || "vendored";
    return this.card("Passes", [
      this.row({
        key: "motion_fix_abstain",
        name: "Motion fix",
        hint: "The motion a shot needs before the pass runs.",
        ...this.segment({
          options: MOTION_GATE,
          value: gate,
          shown: (value) => t("gate {value}", { value }),
          also: "Peak frame-to-frame change at thumbnail scale. Either way the pass "
              + "writes what it saw into the render history, so a card whose fix did "
              + "nothing says why.",
          apply: (value) => this.set({ motion_fix_abstain: value }),
        }),
      }),
      this.row({
        key: "lora_loader",
        name: "LoRA loader",
        ...this.segment({
          options: LORA_LOADERS,
          value: loader,
          also: "Read when a render is queued. The guide LoRA pass always uses "
              + "ComfyUI's loader, the one its files were published against.",
          apply: (value) => this.set({ lora_loader: value }),
        }),
      }),
      this.neuralRow(),
    ]);
  }

  /**
   * The DLSS 5 neural refiner: where it stands on this machine, and the two
   * presses that set it up.
   *
   * This row exists because of the support tail the refiner brings with it.
   * The weights live inside NVIDIA's own DLL and this pack ships none of it —
   * not the DLL, not the weights, not the extraction tool — so every install
   * goes: install the package, find the DLL, check it is the right build,
   * extract. Each of those can go wrong in a way nobody here can fix over an
   * issue, which is why every state of it is written on this page: what is
   * installed, what is not, whether the file at that path is the build the
   * decoder was verified against, and where the weights landed.
   */
  neuralRow() {
    const state = this.neural;
    const dll = this.settings.neural_dll ?? "";
    const busy = Boolean(this.neuralBusy);
    const checked = state?.dll ?? null;

    // The standing in two words beside the field, the whole of it on hover.
    const standing = state === null
      ? el("span", { class: "mmc-neural-line", text: t("Asking…") })
      : el("span", { class: `mmc-neural-line${state.weights ? " ok" : ""}`,
                     text: state.weights
            ? t("Weights extracted, in {folder}/{file}.", { folder: state.folder, file: state.weights_file })
            : t("Not extracted yet. They come out of your own {dll} (file version {version}) below.",
                { dll: state.dll_name, version: state.dll_version }) });

    // The box is not re-rendered while it is typed in — that would drop the
    // caret — so the Check button's readiness is flipped by hand on input
    // rather than read off the render. The first version computed `disabled`
    // once from the empty box and nothing pasted in afterwards could enable it.
    let checkButton = null;
    const field = el("input", {
      type: "text", class: "mmc-neural-path", value: dll, spellcheck: "false",
      placeholder: t("…/Streamline/bin/x64/nvngx_dlssnr.dll"),
      "aria-label": t("Path to your nvngx_dlssnr.dll"),
      disabled: busy || null,
      oninput: (event) => {
        this.settings = { ...this.settings, neural_dll: event.target.value };
        if (checkButton) checkButton.disabled = busy || !event.target.value.trim();
      },
      onkeydown: (event) => {
        event.stopPropagation();
        if (event.key === "Enter") { event.preventDefault(); this.checkNeural(); }
      },
      onpaste: (event) => event.stopPropagation(),
    });

    const verdict = checked
      ? el("div", { class: `mmc-neural-verdict${checked.supported ? " ok" : " bad"}` }, [
          el("span", { text: checked.verified
            ? t("This is the build upstream verified ({version}).", { version: state.dll_version })
            : checked.supported
              ? t("Usable: {reason}", { reason: checked.reason })
              : t(checked.reason ?? "Not the supported build.") }),
        ])
      : null;

    const note = this.neuralNote
      ? el("div", { class: `mmc-neural-verdict${this.neuralNote.ok ? " ok" : " bad"}`,
                    text: this.neuralNote.text })
      : null;

    // One press: Check until the file at the path is known to be the right
    // build, then Extract. Two buttons of which one is always disabled is a
    // row with a dead control on it.
    const extractable = Boolean(checked?.supported) && !busy;
    const action = extractable
      ? el("button", {
          class: "mmc-set-reset mmc-neural-extract",
          text: this.neuralBusy === "extract" ? t("Extracting…") : t("Extract weights"),
          title: t("Run the port's extraction over the DLL, locally, into {folder}.",
                   { folder: state?.folder ?? "models/dlss" }),
          onclick: () => this.extractNeural(),
        })
      : (checkButton = el("button", {
          class: "mmc-set-reset", text: this.neuralBusy === "check" ? t("Checking…") : t("Check"),
          disabled: busy || !dll.trim() || null,
          title: t("Hash the file and say whether it is the build the weights come out of."),
          onclick: () => this.checkNeural(),
        }));
    return this.row({
      key: "neural_dll",
      name: "Neural refiner (DLSS 5)",
      control: el("div", { class: "mmc-neural-field" }, [
          // The standing rides in the box after the path, the way the folder
          // fields carry their suffix: one box to the column's edge.
          el("div", { class: "mmc-neural-row" }, [field, action]),
          standing,
          verdict,
          note,
        ]),
      aside: t("Nothing of NVIDIA's ships with this pack: the weights are extracted "
            + "here from the DLL, which is never read again, and nothing is "
            + "downloaded. The code is the open-source port {upstream} "
            + "(Apache-2.0), carried in this pack at commit {commit}. Its figures — "
            + "within 0.005 of the driver on game renders — are its own, not this "
            + "pack's. Trained on game frames: expect strong results on figures and "
            + "faces, and odd ones on flat or abstract work.",
            { upstream: state?.upstream ?? "iamwavecut/MLX-DLSS",
              commit: (state?.commit ?? "").slice(0, 7) }),
    });
  }

  async loadNeural() {
    this.neuralBusy = "load";
    try {
      this.neural = await neuralStatus();
      if (this.neural.dll_path && !("neural_dll" in (this.settings ?? {}))) {
        this.settings = { ...this.settings, neural_dll: this.neural.dll_path };
      }
    } catch (error) {
      this.neural = { installed: false, weights: null, needs: String(error?.message ?? error) };
    } finally {
      this.neuralBusy = null;
      this.render();
    }
  }

  async checkNeural() {
    const path = (this.settings.neural_dll ?? "").trim();
    if (!path || this.neuralBusy) return;
    this.neuralBusy = "check";
    this.neuralNote = null;
    this.render();
    try {
      const checked = await neuralCheck(path);
      this.neural = { ...(this.neural ?? {}), dll: checked };
    } catch (error) {
      this.neuralNote = { ok: false, text: String(error?.message ?? error) };
    } finally {
      this.neuralBusy = null;
      this.render();
    }
  }

  async extractNeural() {
    const path = (this.settings.neural_dll ?? "").trim();
    if (!path || this.neuralBusy) return;
    this.neuralBusy = "extract";
    this.neuralNote = null;
    this.render();
    try {
      this.neural = await neuralExtract(path);
      this.neuralNote = { ok: true, text: t("Extracted. The refiner is ready; pills and the upscale bench "
                                           + "pick it up on their next open.") };
    } catch (error) {
      this.neuralNote = { ok: false, text: String(error?.message ?? error) };
    } finally {
      this.neuralBusy = null;
      this.render();
    }
  }

  /**
   * Whether a reference's latents are kept between renders, and the two
   * limits on the store.
   *
   * A generation caches on its whole request, so editing one word of the prompt
   * re-decodes and re-encodes every reference the shot cites — and a reference
   * does not know the prompt exists. Kept, they are encoded once per (file,
   * canvas, VAE) and the prompt is free to move. It cannot change what a render
   * produces, only how long it takes: the encoder rounds a reference's
   * presentation to 8 bits whether this is on or off, so a cached reference
   * and a freshly encoded one are the same tensors.
   *
   * The size row carries a gauge of what the store is *actually* holding,
   * which is the one thing on this page that is a reading rather than a
   * choice: a ceiling is a decision about a real number, and asking for it
   * without showing that number is asking somebody to guess.
   */
  cacheCard() {
    const on = this.settings.latent_cache !== false;
    const gb = Number(this.settings.latent_cache_gb ?? 8);
    const days = Number(this.settings.latent_cache_days ?? 30);
    const held = Number(this.cache?.bytes ?? 0);
    const rows = [this.row({
      key: "latent_cache",
      name: "Encoded references",
      hint: "Kept between renders.",
      ...this.segment({
        options: REF_CACHE,
        value: on,
        also: "Attaching a video or a cast member means pushing it through the VAE, "
            + "and on a large source that is most of the wait before sampling. Kept "
            + "beside your settings across restarts; only this page and the two "
            + "limits below ever remove one.",
        apply: (value) => this.set({ latent_cache: value }),
      }),
    })];
    if (on) {
      // Off, there is nothing on disk to age, and a live retention row beside
      // a store that holds nothing would be a control with no effect. It stays
      // on the page — it is still what would happen once there is — and goes
      // quiet.
      rows.push(this.row({
        key: "latent_cache_days",
        name: "Expire unread after",
        ...this.segment({
          options: KEEP_STOPS,
          value: days,
          disabled: gb <= 0,
          report: true,
          custom: (value) => keepFor(value),
          said: () => gb <= 0
            ? t("Nothing is written to disk to keep.")
            : days <= 0
              ? t("Only the size limit below ever drops one.")
              : null,
          apply: (value) => this.set({ latent_cache_days: value }),
        }),
      }));
      const over = gb > 0 ? held - gb * 1024 * 1024 * 1024 : 0;
      const bound = this.stepper({
          options: SIZE_STOPS.map((stop) => ({ ...stop, label: stop.label ?? String(stop.value) })),
          value: gb,
          shown: (value) => (value ? t("{n} GB", { n: value }) : t("Off")),
          custom: (value) => String(value),
          warn: over > 0,
          said: () => gb <= 0
            ? t("Nothing is written to disk — this session only.")
            : over > 0
              ? t("Over by {size}; the next render drops that much.", { size: said(over) })
              : t("Nothing stored yet."),
          apply: (value) => this.set({ latent_cache_gb: value }),
      });
      // What the store is holding under that ceiling, beside the stepper.
      // Emptying it is the inventory's press, not a second one here.
      if (held > 0 && gb > 0) bound.reading = t("{held} held", { held: said(held) });
      rows.push(this.row({
        key: "latent_cache_gb",
        name: "Cache limit",
        ...bound,
      }));
    }
    return this.card("Reference cache", rows);
  }

  // ---- nodes ----------------------------------------------------------------

  /**
   * What the node faces offer, as opposed to what a render writes.
   *
   * The advanced switch is a length control, not a permission: nothing is
   * disabled and nothing is locked. And it never hides something that is on —
   * a lead-in that is set, a card already running low VRAM, keeps its pill
   * whatever this says. In force means visible, which is the same rule the
   * custom quality button and the shift pills live by, and it is what makes
   * turning this off a safe thing to do without checking what you had
   * switched on.
   *
   * The step preview is the only thing here that is not purely cosmetic — not
   * because it changes a render (it cannot; this is the picture you watch
   * while one happens) but because the frame has to *arrive*. It is a full-clip
   * animated WebP, re-encoded and sent on every sampling step, and a websocket
   * behind a reverse proxy has a frame cap: aiohttp's is 4 MiB and nothing
   * raises it by default. A frame over that does not arrive late — it takes
   * the socket down mid-render. So the default is the size a preview is
   * actually looked at rather than the override node's 1024.
   */
  nodesCard() {
    const px = Number(this.settings.preview_max_px ?? 640);
    const quality = Number(this.settings.preview_quality ?? 80);
    return this.card("Nodes", [
      this.row({
        key: "advanced",
        name: "Advanced controls",
        ...this.segment({
          options: ADVANCED,
          value: this.settings.advanced === true,
          also: "Nothing is locked either way. Open nodes pick the change up the next "
              + "time they redraw — closing this page is enough.",
          apply: (value) => this.set({ advanced: value }),
        }),
      }),
      this.row({
        key: "show_shift_pills",
        name: "Flow shift pills",
        hint: "H3's schedule clocks on the sampler row.",
        ...this.segment({
          options: SHIFT_PILLS,
          value: this.settings.show_shift_pills === true,
          also: "The values apply either way; this only decides who has to look at them.",
          apply: (value) => this.set({ show_shift_pills: value }),
        }),
      }),
      this.row({
        key: "autoplay_previews",
        name: "Preview playback",
        ...this.segment({
          options: PLAYBACK,
          value: this.settings.autoplay_previews !== false,
          apply: (value) => this.set({ autoplay_previews: value }),
        }),
      }),
      this.row({
        key: "preview_max_px",
        name: "Step preview size",
        hint: "Long edge of the frame sent each step.",
        ...this.stepper({
          options: PREVIEW_PX_STOPS.map((stop) => ({ value: stop.value, label: String(stop.value) })),
          value: px,
          shown: (value) => t("{n} px", { n: value }),
          custom: (value) => String(value),
          warn: px > 768,
          also: "It is a whole clip, re-encoded and sent every step, and a websocket "
              + "behind a proxy has a frame limit: a frame past it takes the "
              + "connection down mid-render rather than arriving late. Read when a "
              + "render is queued; only KJNodes' preview override draws it.",
          said: () => px > 768
            ? t("Larger than any box that shows it. Costs an encode and the bytes every step.")
            : px < 384
              ? t("Small and cheap. For a wire that drops long renders at anything larger.")
              : t("The long edge. The box that shows it is a node face, or the fullscreen dock."),
          apply: (value) => this.set({ preview_max_px: value }),
        }),
      }),
      this.row({
        key: "preview_quality",
        name: "Step preview quality",
        ...this.stepper({
          options: PREVIEW_Q_STOPS.map((stop) => ({ value: stop.value, label: String(stop.value) })),
          value: quality,
          custom: (value) => String(value),
          warn: quality >= 90,
          said: () => quality >= 90
            ? t("Near-lossless, and several times the bytes of 80 for a decode of a "
                + "half-finished latent.")
            : t("The encoder's own scale. 80 is what the override node picks unasked."),
          apply: (value) => this.set({ preview_quality: value }),
        }),
      }),
    ]);
  }

  // ---- interface ------------------------------------------------------------

  /**
   * How the pack is drawn: how large its text is, which palette it wears, and
   * how far its surfaces step off the ground.
   *
   * The text size is one multiplier over every size in styles/ — see
   * `--mmc-type` in styles/base.js for why it is a multiplier and not a set of
   * named sizes. It is written onto the document out of `noteSettings`, so the
   * page you are setting it on resizes under the pointer. What moves with it is
   * the text and what holds text; what does not is the room around them and
   * the picture. That is the line between a text size and a magnifier, and the
   * browser already has a magnifier on Cmd +.
   *
   * The whole of this pack's colour derives from two of ComfyUI's own
   * variables — `--mmc-ground` and `--mmc-ink` — so following the desk costs
   * nothing and happens by itself. The colour row only exists for the case
   * following gets wrong: a light desk under a pack whose job is showing you a
   * picture. There is no "light" — a light editor over a dark graph is the one
   * combination nobody asks for.
   *
   * The separation is one multiplier over all four rungs of the surface ramp
   * (`--mmc-lift`). It is a setting rather than a constant because the ramp is
   * proportional to a palette's own contrast and some palettes have very
   * little: there is no one set of percentages right for a ground of #ffffff
   * and one of #073642.
   */
  interfaceCard() {
    const scale = Number(this.settings.text_scale) || 1;
    const theme = this.settings.theme === "dark" ? "dark" : "follow";
    const lift = Number(this.settings.surface_lift) || 1;
    const percent = (value) => `${Math.round(value * 100)}%`;
    return this.card("Interface", [
      this.row({
        key: "lora_skip_metadata",
        name: "Skip model metadata in LoRA cards",
        ...this.segment({
          options: LORA_CARD_METADATA,
          value: this.settings.lora_skip_metadata === true,
          also: "Card labels only. LoRA loading, trigger words, detail metadata and local "
              + "thumbnails stay unchanged. Reopen the LoRA manager to apply changes.",
          apply: (value) => this.set({ lora_skip_metadata: value }),
        }),
      }),
      this.row({
        key: "text_scale",
        name: "Text size",
        ...this.segment({
          options: TEXT_SCALE.map((row) => ({ value: row.scale, label: row.label, note: row.note })),
          value: scale,
          // The number in force, on every button — the same promise the quality
          // row's crf makes. A percentage rather than the stored 1.12, because
          // "112%" is the one reading of a multiplier nobody has to be told how
          // to read.
          shown: percent,
          also: "Nothing of ComfyUI's moves with it, and this page moves as you "
              + "choose. For everything at once, including ComfyUI's chrome, use the "
              + "browser's zoom.",
          apply: (value) => this.set({ text_scale: value }),
        }),
      }),
      this.row({
        key: "theme",
        name: "Colour",
        hint: "This pack only.",
        ...this.segment({
          options: THEMES,
          value: theme,
          apply: (value) => this.set({ theme: value }),
        }),
      }),
      this.row({
        key: "surface_lift",
        name: "Surface separation",
        ...this.segment({
          options: SURFACE_LIFT.map((row) => ({ value: row.lift, label: row.label, note: row.note })),
          value: lift,
          shown: percent,
          apply: (value) => this.set({ surface_lift: value }),
        }),
      }),
    ]);
  }

  // ---- folders --------------------------------------------------------------

  /**
   * One family's destination: its name, the field, and the line it resolves to.
   *
   * Written through on Enter or on leaving the field rather than on every
   * keystroke — the rest of the page writes on a click, and a click is finished
   * where a half-typed path is not. What is live is the *reading*: the line
   * under the field moves as you type, folder half dim and filename bright,
   * because a prefix is two things at once and "renders/H3" being a file called
   * H3 rather than a folder called H3 is the one surprise this page holds.
   *
   * The field is a token field, not a text box. `%year%` is core's spelling of
   * a token and it is a fine thing to *store*; it was a terrible thing to edit,
   * because eight loose characters in a text box can be typed into, split, and
   * half-deleted — which is how a field ends up reading `minima%sssyear%%month%x`
   * with no way to tell the typo from the token. Here each one is a single tile
   * wearing its plain word: the caret can sit either side of it and there is no
   * position inside it, so one Backspace takes the whole thing. What is stored
   * is unchanged, so `outputs.py` never learns about any of this.
   *
   * The token chips only exist while the field has focus — CSS, off
   * :focus-within — so the page at rest is a field per family and not eight
   * buttons per family.
   */
  folderRow(key, family, title, fallback, extension) {
    // The server fills a row for every family it knows, so the fallback is for
    // the one case it cannot: a settings file that predates this family. It is
    // the manifest's own default, which is what the save node would use.
    const stored = this.settings[key]?.[family] ?? fallback;
    const field = el("div", {
      class: "mmc-out-field",
      contenteditable: "true",
      role: "textbox",
      "aria-multiline": "false",
      spellcheck: "false",
      "aria-label": t("{title} — folder and filename prefix", { title }),
      onkeydown: (event) => {
        event.stopPropagation();
        // The box is one line. Enter finishes it rather than growing it a
        // second one the path could never hold.
        if (event.key === "Enter") { event.preventDefault(); field.blur(); }
        if (event.key === "Escape") { write(stored); field.blur(); }
      },
      onpaste: (event) => {
        // Plain text, and not the graph's. ComfyUI's own paste listener decides
        // an event is "on the canvas" by asking whether the target is an input
        // or a textarea — a contenteditable is neither — and it never looks at
        // defaultPrevented, so a Ctrl+V in here would also deal out the last
        // copied nodes. The prompt box carries the long version of this note.
        event.preventDefault();
        event.stopPropagation();
        // A path is one line: whatever shape the clipboard's newlines were in,
        // they arrive here as the spaces `cleanPrefix` will then refuse out loud.
        const text = (event.clipboardData?.getData("text/plain") ?? "").replace(/\s+/g, " ");
        insert(text);
      },
      // A contenteditable has no `change`; leaving it is the whole commit.
      onblur: () => commit(),
    });
    const problem = el("div", { class: "mmc-out-problem" });
    const example = el("span", { class: "mmc-out-ghost" });
    const root = el("span", { class: "mmc-out-ghost mmc-out-root", text: "output/" });
    /**
     * Back to the folder this family ships with.
     *
     * On the row rather than on the tab, because the default is per family and
     * per shelf — H3 files into two of them and they are two different folders,
     * so there is no one path a single button could mean. It says which one it
     * means anyway: the path is in the title, since "default" names nothing on
     * its own and this is the last chance to read it before it lands.
     *
     * Only up while the row is off its default. A control that does nothing is
     * worse than no control, and five rows sitting at their defaults would
     * otherwise carry five buttons that all decline to do anything.
     */
    const reset = el("button", {
      class: "mmc-set-reset",
      text: t("Reset"),
      title: t("Back to {path}", { path: fallback }),
      onclick: () => { write(fallback); commit(); },
    });

    /** The stored string the field currently spells. Walks rather than reading
     *  textContent: a tile's text is the plain word, and the token is what has
     *  to come out. Anything the browser wrapped the content in on the way past
     *  is walked through — a wrapper's text belongs to the path too. */
    const read = (parent = field) => {
      let text = "";
      for (const node of parent.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) text += node.nodeValue;
        else if (node.dataset?.token) text += node.dataset.token;
        else if (node.tagName !== "BR") text += read(node);
      }
      return text;
    };

    /** Draw a stored string: literal text as text, every token as one tile. */
    const write = (text) => {
      field.replaceChildren(...splitTokens(text).map((part) => (part.token
        ? el("span", {
            class: "mmc-out-tile",
            contenteditable: "false",
            "data-token": part.token,
            text: tokenLabel(part.token),
          })
        : document.createTextNode(part.text))));
    };

    /**
     * Where the caret is as an offset into `read()`, or null if it is not in
     * here. An offset survives the rebuild a node does not — which is the only
     * reason the field can be redrawn from its string under someone's fingers.
     *
     * The walk mirrors `read`'s, because it is the same string being counted,
     * and it has to be a walk for the same reason: the browser is free to wrap
     * what is in here, and a caret inside a wrapper is still a caret in the
     * path. The container is the *parent* when the caret sits between two
     * nodes rather than inside one — then the offset is a child index.
     */
    const caret = () => {
      const selection = window.getSelection?.();
      const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
      if (!range || !field.contains(range.endContainer)) return null;
      let at = 0;
      let found = null;
      const walk = (parent) => {
        const kids = [...parent.childNodes];
        for (let index = 0; index < kids.length; index += 1) {
          if (found !== null) return;
          if (range.endContainer === parent && range.endOffset === index) { found = at; return; }
          const node = kids[index];
          if (node === range.endContainer) { found = at + range.endOffset; return; }
          if (node.nodeType === Node.TEXT_NODE) at += node.nodeValue.length;
          else if (node.dataset?.token) at += node.dataset.token.length;
          else if (node.tagName !== "BR") walk(node);
        }
        if (found === null && range.endContainer === parent) found = at;
      };
      walk(field);
      return found ?? at;
    };

    /** The caret at an offset into the stored string. A tile is passed over
     *  whole — there is no offset inside one to land on. */
    const place = (index) => {
      let at = 0;
      for (const node of field.childNodes) {
        const length = node.nodeType === Node.TEXT_NODE
          ? node.nodeValue.length : (node.dataset?.token?.length ?? 0);
        if (node.nodeType === Node.TEXT_NODE && index <= at + length) {
          const range = document.createRange();
          range.setStart(node, Math.max(0, index - at));
          range.collapse(true);
          const selection = window.getSelection();
          selection?.removeAllRanges();
          selection?.addRange(range);
          field.focus();
          return;
        }
        at += length;
      }
      // Past everything, or the last thing in here is a tile: the caret goes
      // after the lot, which is where the next keystroke belongs anyway.
      field.focus();
      const range = document.createRange();
      range.selectNodeContents(field);
      range.collapse(false);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    };

    /** Text into the path where the caret is, then redrawn — which is what
     *  turns a pasted or chip-written `%year%` into its tile. Typing, not
     *  finishing: the write is still Enter's or blur's. */
    const insert = (text) => {
      const before = read();
      const at = caret() ?? before.length;
      write(before.slice(0, at) + text + before.slice(at));
      place(at + text.length);
      paint();
    };

    const paint = () => {
      const { prefix, error } = cleanPrefix(read(), stored);
      field.classList.toggle("bad", Boolean(error));
      // A path that does not parse is off its default too, and that is exactly
      // when the way back matters most.
      reset.style.display = !error && prefix === fallback ? "none" : "";
      problem.textContent = error ?? "";
      problem.style.display = error ? "" : "none";
      // The counter and the extension, ghosted straight after what is typed:
      // "renders/H3" followed by "_00001_.mp4" says, in the field itself, that
      // the last part names the files and core numbers them apart.
      example.textContent = error ? "" : examplePath("", { extension });
      return { prefix, error };
    };

    const commit = () => {
      const { prefix, error } = paint();
      // A path that does not parse is left on screen to be fixed rather than
      // stored or silently reverted — nothing has changed on disk yet, and the
      // line under it says what is wrong.
      if (error || prefix === this.settings[key]?.[family]) return;
      // The whole block, not the one family: `set` patches the settings object
      // shallowly, so sending `{h3: …}` alone would drop every other family's
      // folder on the way through.
      this.set({ [key]: { ...this.settings[key], [family]: prefix } });
    };

    /**
     * Whether the DOM has stopped spelling the string the way `write` would.
     *
     * Two ways it can: a token typed or pasted as bare text — someone who knows
     * core's syntax should see the tile appear under their fingers rather than
     * be told they have typed it wrong — and a wrapper the browser put around
     * the content on its way past, which is the engine's own doing and would
     * otherwise accumulate. Both are answered the same way, by redrawing from
     * the string, so neither has to be detected precisely.
     */
    const strayed = (parent = field) => [...parent.childNodes].some((node) => (
      node.nodeType === Node.TEXT_NODE
        ? splitTokens(node.nodeValue).some((part) => part.token)
        : !node.dataset?.token || strayed(node)));

    field.addEventListener("input", () => {
      if (strayed()) {
        const at = caret();
        write(read());
        if (at !== null) place(at);
      }
      paint();
    });
    write(stored);
    paint();

    const values = tokenValues();
    /** One inserter. Says the word it writes and what that word is worth right
     *  now, because "month" alone never said whether it meant 08 or August —
     *  and the answer is the folder name. */
    const chip = (token) => el("button", {
      class: "mmc-out-token",
      title: t("Inserts {name}, filled in when the file is written", { name: tokenLabel(token) }),
      // pointerdown is swallowed so the click does not blur the field first —
      // and inserting is typing, not finishing: it repaints the reading and
      // leaves the write to Enter or blur, the same deal the keyboard has. A
      // commit here would re-render the page and yank the field, row and caret
      // both, out from under the second click.
      onpointerdown: (event) => event.preventDefault(),
      onclick: () => insert(token),
    }, [
      el("span", { class: "mmc-out-token-name", text: tokenLabel(token) }),
      el("span", { class: "mmc-out-token-now", text: values[token] }),
    ]);

    return el("div", { class: "mmc-set-dest" }, [
      // The family's own name, untranslated: "MiniMax H3" and "LTX 2.5" are
      // what the checkpoints are called, and the card above already says in
      // this reader's language whether these are renders or stills.
      el("div", { class: "mmc-set-dest-head" }, [
        el("span", { class: "mmc-set-dest-name", text: title }),
        reset,
      ]),
      // One line: ComfyUI's output folder ghosted before the path, the counter
      // and extension ghosted after it. Clicking the ghosts puts the caret in
      // the field, since they read as part of it.
      el("div", { class: "mmc-set-path", onclick: (event) => { if (event.target !== field) field.focus(); } },
         [root, field, example]),
      problem,
      // Clock first, then frame — the order they are useful in, since a folder
      // per shoot is what this field is mostly for. Nothing marks the boundary:
      // the row wraps at this width, and a rule between the groups spends most
      // of its life stranded at the end of a line saying nothing.
      el("div", { class: "mmc-out-tokens" }, [
        el("span", { class: "mmc-out-tokens-key", text: t("insert") }),
        ...CLOCK_TOKENS.map(chip),
        ...FRAME_TOKENS.map(chip),
      ]),
    ]);
  }

  // ---- stored data ----------------------------------------------------------

  /**
   * What this pack is holding, and how to take any of it back.
   *
   * An inventory rather than a row of red buttons. Everything here is
   * irreversible and most of it is invisible from anywhere else — a preset
   * library lives in ComfyUI's user directory, the LoRA notes and the refiner's
   * choices in this browser — so the question the page has to answer first is
   * not "are you sure" but "what is there". Each row says what it holds before
   * it offers to remove it, and a row holding nothing is plainly inert.
   *
   * Grouped by where the thing lives, because that is what decides who else
   * loses it: the library follows the ComfyUI user, the browser rows are this
   * browser's alone, and the machine rows are files on this disk.
   */
  storedCards() {
    const groups = [];
    for (const row of STORED) {
      const last = groups[groups.length - 1];
      if (last && last.name === row.group) last.rows.push(row);
      else groups.push({ name: row.group, rows: [row] });
    }
    return [
      ...groups.map(({ name, rows }) => this.card(GROUP_TITLE[name].title,
        rows.map((row) => this.storedRow(row)), null, GROUP_TITLE[name].note)),
      this.card("Start over", [this.sweepButton()], null,
        "Every row above, in one press: the library, this browser's memory of "
        + "how you work, and every setting back to default. Nothing here touches "
        + "a render, a reference or a workflow — those are files, and this page "
        + "does not delete files."),
    ];
  }

  /** One row: what it is, what is behind it, and the press. */
  storedRow(row) {
    const kept = this.kept ? row.held(this.kept) : null;
    const empty = kept === 0;
    const held = !this.kept ? t("Counting…")
      : empty ? t("none")
      : typeof kept === "number" ? String(kept) : kept === true ? "" : t(kept);
    const press = el("button", {
      class: "mmc-zone-go",
      disabled: !this.kept || empty || this.sweeping ? true : undefined,
      text: t(row.press ?? "Remove"),
      onclick: () => this.armRow(row, press),
    });
    return el("div", { class: "mmc-zone-row", "data-empty": String(empty) }, [
      el("div", { class: "mmc-zone-what", title: t(row.note) }, [
        el("span", { class: "mmc-zone-name", text: t(row.name) }),
      ]),
      el("span", { class: "mmc-zone-held", text: held }),
      press,
    ]);
  }

  /** The press asks once. Same bargain the picker's Delete and the rail's Clear
   *  strike, and for the same reason: there is no undo, and a row of them is a
   *  row you can slip on. Anything but a second press puts it back. */
  armRow(row, press) {
    if (press.classList.contains("armed")) { this.runStored([row]); return; }
    // Only ever one armed at a time, so a stray press cannot fire the row above
    // the one being read.
    this.disarm();
    press.classList.add("armed");
    press.textContent = t("Really remove?");
    this.armTimer = setTimeout(() => this.render(), 5000);
  }

  disarm() {
    clearTimeout(this.armTimer);
    for (const press of this.page.querySelectorAll(".armed")) {
      press.classList.remove("armed");
    }
  }

  /** The whole list, armed the same way. Says how many rows it is about to
   *  empty rather than "everything", which is a word and not a number. */
  sweepButton() {
    const standing = this.kept
      ? STORED.filter((row) => row.held(this.kept) !== 0).length
      : 0;
    const press = el("button", {
      class: "mmc-zone-go mmc-zone-all",
      disabled: !this.kept || !standing || this.sweeping ? true : undefined,
      text: this.sweeping ? t("Removing…")
        : !this.kept ? t("Counting…")
        : standing ? t("Remove everything")
        : t("Nothing stored"),
      onclick: () => {
        if (press.classList.contains("armed")) {
          this.runStored(STORED.filter((row) => row.held(this.kept) !== 0));
          return;
        }
        this.disarm();
        press.classList.add("armed");
        press.textContent = t("Really remove all {count}?", { count: standing });
        this.armTimer = setTimeout(() => this.render(), 5000);
      },
    });
    return press;
  }

  /**
   * Do it, then re-count.
   *
   * Row by row, and a row that fails does not stop the ones after it: these are
   * separate stores in separate places, and stopping at the first refusal would
   * leave a "remove everything" that removed some of it and said nothing about
   * which. What went wrong comes back named, so the row that survived is the
   * row you can see.
   */
  async runStored(rows) {
    this.disarm();
    this.problem = null;
    this.sweeping = true;
    this.render();
    const failures = [];
    for (const row of rows) {
      try {
        await row.remove();
      } catch (error) {
        failures.push(t("{name}: {error}", { name: t(row.name), error: error.message }));
      }
    }
    this.sweeping = false;
    // The settings row rewrites the page's own subject, so what is now in force
    // is read back rather than assumed — and the stylesheet is told, since the
    // text scale and the palette are drawn from it.
    try {
      this.settings = await loadSettings();
      noteSettings(this.settings);
    } catch { /* the page keeps what it had; the row's own failure says why */ }
    try {
      this.cache = await loadLatentCache();
    } catch { /* the line stays absent */ }
    if (failures.length) {
      this.problem = failures.length === 1 ? failures[0]
        : t("{count} did not go — {first}", { count: failures.length, first: failures[0] });
    }
    await this.takeStock();
  }

  // ---- the shapes -----------------------------------------------------------

  /** One group of the index: its heading, then its cards. */
  groupBlock(key, cards) {
    // No heading of its own: the index already says the word, and every card
    // carries a head — a group of one card takes the group's name for it.
    const group = GROUPS.find((entry) => entry.key === key);
    return el("section", { class: "mmc-set-group", "data-group": key, "aria-label": t(group.label) }, cards);
  }

  /**
   * One card: rows that belong together, under a name when the group holds
   * more than one card. `foot` is the line under the rows that is about all of
   * them — read when a render is queued, relative to the output folder — and
   * `desc` the line above them, which only the inventory uses: where a store
   * lives is what you need to know before throwing it away, and it is one fact
   * per card rather than one per row.
   */
  card(title, rows, foot = null, desc = null, under = null) {
    // `under` is the folder every path in the card sits below — said once in
    // the head rather than once per field.
    // Where a store lives waits on the pointer, over the head: at rest the
    // inventory is a table, and a paragraph over every third of it is not.
    return el("div", { class: "mmc-set-card" }, [
      ...(title ? [el("div", { class: "mmc-set-card-name", title: desc ? t(desc) : null }, [
        el("span", { text: t(title) }),
        ...(under ? [el("span", { class: "mmc-set-card-under", text: under })] : []),
      ])] : []),
      ...rows,
      ...(foot ? [el("div", { class: "mmc-set-card-foot", text: foot })] : []),
    ]);
  }

  /**
   * One setting: its name and what it is for on the left, the control on the
   * right, and under both the note for the answer in force. `lead` sits in
   * front of the control — the cache's gauge — and `more` is whatever a row
   * needs the full width for, which is the refiner's path field and nothing
   * else. `key` is the setting's own name in the file, which is how the tests
   * find a row and how a reader of the DOM can tell which one it is.
   */
  row({ key, name, hint = null, control, note = null, aside = null, reading = null, lead = null, more = [] }) {
    // Under the name: the number in force where there is one — crf 23, 112%
    // — and otherwise nothing. What a setting is for waits on the pointer.
    if (reading) { aside = [hint, aside].filter(Boolean).map((text) => t(text)).join(" "); hint = reading; }
    else if (hint) { aside = [hint, aside].filter(Boolean).map((text) => t(text)).join(" "); hint = null; }
    const hintBox = typeof hint === "string" ? el("span", { class: "mmc-set-hint", text: hint }) : hint;
    // At rest a row is its name, one line on what it is for, and the answer.
    // The reasoning waits on the pointer: every button carries its option's
    // note as a title, and the hint carries what is true of the row whichever
    // is pressed. `note` is drawn only where it is a reading — the cache's
    // "holding 2.3 GB" — not an explanation.
    const noteBox = note
      ? (typeof note === "string"
        ? el("div", { class: "mmc-set-note", text: note })
        : el("div", { class: "mmc-set-note" }, [note]))
      : null;
    return el("div", { class: "mmc-set-row", "data-key": key }, [
      el("div", { class: "mmc-set-what", title: aside || null }, [
        el("span", { class: "mmc-set-name", text: t(name) }),
      ]),
      el("div", { class: "mmc-set-ctl" }, [lead, control, hintBox]),
      noteBox,
      ...more.map((extra) => el("div", { class: "mmc-set-more" }, [extra])),
    ]);
  }

  /**
   * A row of buttons, one pressed. -> `{ control, note }` for `row`.
   *
   * `options` are `{ value, label, note? }`; `shown` puts the real number
   * beside the word on every button, and `unit` after the row of them. The
   * note under the row is the pressed option's own, or `said()` where the
   * consequence depends on more than the choice — the cache's rows read the
   * store as well as the setting. The other options' notes wait on the
   * pointer, as titles.
   *
   * A value the settings file holds that no button offers takes its own button
   * rather than being rounded onto a neighbour: it is in force, so it has to be
   * visible, and pressing another is how you leave it. `custom` names it —
   * "Custom" for a tier, the number itself for a stop — and a stop list keeps
   * its order, with the hand-typed value sorted in among the numbers.
   */
  /**
   * A number walked along a scale: the value in force between a step down and
   * a step up. -> `{ control, note }` for `row`, the same shape `segment` hands
   * over. `options` are the stops, in order; a value the file holds that is
   * not one of them is shown as it is, and a step moves to the nearest stop
   * past it. `shown` spells the value with its unit — "8 GB", "640 px".
   */
  stepper({ options, value, apply, shown = (v) => String(v), said = null, also = null,
            warn = false, report = false }) {
    const stops = options.map((option) => option.value);
    const at = stops.indexOf(value);
    const down = at >= 0 ? stops[at - 1] : [...stops].reverse().find((stop) => stop < value);
    const up = at >= 0 ? stops[at + 1] : stops.find((stop) => stop > value);
    const step = (to, glyph, title) => el("button", {
      class: "mmc-set-step", text: glyph, title,
      disabled: to === undefined ? true : null,
      onclick: () => to !== undefined && apply(to),
    });
    const control = el("div", { class: "mmc-set-stepper", "data-stops": String(stops.length) }, [
      step(down, "−", down === undefined ? null : shown(down)),
      el("span", { class: "mmc-set-step-val", text: shown(value) }),
      step(up, "+", up === undefined ? null : shown(up)),
    ]);
    const note = said && (warn || report) ? el("span", { class: warn ? "over" : null, text: said() }) : null;
    const said_ = said && !(warn || report) ? said() : null;
    return { control, note, aside: [also, said_].filter(Boolean).join(" "), reading: null };
  }

  segment({ options, value, apply, shown = null, unit = null, custom = () => t("Custom"),
            said = null, also = null, warn = false, disabled = false, report = false }) {
    let offered = options;
    if (!options.some((option) => option.value === value)) {
      const own = { value, label: custom(value), note: CUSTOM_NOTE, custom: true };
      // Sorted in where the stops are numbers in order; ahead of everything
      // where they are words. A zero stop is "Off" or "Forever" and stays put.
      const numeric = options.length > 2 && options.every((option) => typeof option.value === "number");
      if (numeric) {
        const stops = options.filter((option) => option.value > 0).map((option) => option.value);
        const ascending = stops[stops.length - 1] >= stops[0];
        const at = options.findIndex((option) => option.value > 0
          && (ascending ? option.value > value : option.value < value));
        offered = at < 0 ? [...options, own] : [...options.slice(0, at), own, ...options.slice(at)];
      } else {
        offered = [own, ...options];
      }
    }
    const chosen = offered.find((option) => option.value === value);
    const buttons = offered.map((option) => {
      const on = option.value === value;
      const title = [shown ? shown(option.value) : null, option.note ? t(option.note) : null]
        .filter(Boolean).join(" — ");
      return el("button", {
        class: "mmc-set-seg-opt",
        "aria-pressed": on,
        disabled: disabled || null,
        title: title || null,
        onclick: () => !on && apply(option.value),
      }, [el("span", { class: "mmc-set-seg-in", text: option.custom ? option.label : t(option.label) })]);
    });
    const control = el("div", { class: `mmc-set-seg${disabled ? " off" : ""}` }, [
      el("div", { class: "mmc-set-seg-row", role: "group" }, buttons),
      ...(unit ? [el("span", { class: "mmc-set-unit", text: unit })] : []),
    ]);
    // A reading — what the store holds, what a preview this size costs — is
    // drawn under the row; an explanation is not.
    const note = said && (warn || report) ? el("span", { class: warn ? "over" : null, text: said() }) : null;
    const said_ = said && !(warn || report) ? said() : null;
    return { control, note, aside: [also, said_].filter(Boolean).join(" "), reading: shown ? shown(value) : null };
  }
}
