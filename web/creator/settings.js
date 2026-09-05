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
// Tabs, because the page answers several questions that are not the same
// question: how good the file is, where it goes, how much of a node face is
// drawn, and how large it is drawn. Every one of them is this machine's rather
// than the workflow's, which is the only reason they share a page.

import { el, mountOverlay } from "./dom.js";
import { loadSettings, saveSettings, resetSettings, noteSettings, loadLatentCache,
         clearLatentCache, clearPickerPrefs, pickerPrefsHeld, clearLoraPrefs,
         loraPrefsHeld } from "./api.js";
import * as P from "./presets.js";
import { resetSettings as resetRefiner, settingsStored as refinerStored,
         remoteStatus, saveRemote } from "./refine.js";
import { forgetLayout } from "./fullscreen.js";
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
// four, so a hand-edited file can go further than this offers); these are the
// three answers worth clicking.
const LEAD_IN = [
  { steps: 0, label: "Off",
    note: "The whole schedule runs on the distillation, which is what a turbo "
        + "render has always been." },
  { steps: 1, label: "One step",
    note: "The cheapest version of the idea. Enough on a 4-step render, where one "
        + "step is a quarter of the schedule." },
  { steps: 2, label: "Two steps",
    note: "The one to start with at 6 and 8 steps. Costs about a quarter of what "
        + "the distillation saved." },
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
  { value: 1, label: "1d" },
  { value: 7, label: "1w" },
  { value: 30, label: "1m" },
  { value: 90, label: "3m" },
  { value: 365, label: "1y" },
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

/** Where `value` sits along a stop list, as 0..1 — the position a mark on the
 *  rail has to take. Interpolated between the stops it falls between, because
 *  the rail is a list of indices and the value is not linear along it. */
function alongStops(stops, value) {
  const last = stops.length - 1;
  if (value <= stops[0].value) return 0;
  for (let i = 0; i < last; i += 1) {
    const low = stops[i].value;
    const high = stops[i + 1].value;
    if (value <= high) return (i + (value - low) / (high - low)) / last;
  }
  return 1;
}

const TABS = [
  { key: "quality", label: "Quality" },
  { key: "folders", label: "Folders" },
  // The key stays "nodes" — it is what `show()` and the tests address the tab
  // by, and it was never on screen. The label is "General" because the tab
  // stopped being about node faces when the rendering sections landed on it:
  // it now holds two groups, and "Nodes" is the name of one of them.
  { key: "nodes", label: "General" },
  { key: "appearance", label: "Appearance" },
  // Last, and named for what it holds rather than for how it feels about it.
  // "Danger" as a tab label is a warning with nothing behind it yet — the
  // gravity belongs on the press, where the thing actually happens.
  { key: "data", label: "Stored data" },
];

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
           note: "A look on its own, without the piece it came off." },
};

/** What each group is and who else it belongs to. The heading has to answer
 *  "where does this live" before a press can be an informed one. */
const GROUP_TITLE = {
  "The library": {
    title: "Presets and cast",
    note: "Everything you starred into the preset library. It is stored against "
        + "your ComfyUI user rather than in a workflow, so it follows you across "
        + "browsers — and nothing else carries it, which is why it is the half of "
        + "this page worth reading twice.",
  },
  "This browser": {
    title: "How you left things",
    note: "What the pack remembers about the way you work, rather than about "
        + "what you made. Losing any of it costs a few clicks, never a file.",
  },
  "This machine": {
    title: "Files and settings on this disk",
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
    name: "Stars and where you left off",
    note: "Starred files, the folder each picker tab opens on, and how large the "
        + "fullscreen editor draws a take. No file is touched.",
    held: (kept) => kept.picker ?? 0,
    remove: async () => { await clearPickerPrefs(); forgetLayout(); },
  },
  {
    id: "loras",
    group: "This browser",
    name: "The LoRA manager's notes",
    note: "Stars, pinned versions, and the strength and trigger words each file "
        + "was last used at. The LoRAs themselves stay on the disk.",
    held: (kept) => kept.loras ?? 0,
    remove: () => clearLoraPrefs(),
  },
  {
    id: "refiner",
    group: "This browser",
    name: "Refiner choices",
    note: "Which model rewrites a prompt, at what temperature, and any template "
        + "or skill pinned to a family.",
    held: (kept) => (kept.refiner ? "set" : 0),
    remove: async () => resetRefiner(),
  },
  {
    id: "cache",
    group: "This machine",
    name: "The reference cache",
    note: "Encoded references kept between renders. Deleting them costs the next "
        + "render one encode each and changes nothing about what it produces.",
    held: (kept) => (kept.cacheBytes ? said(kept.cacheBytes) : 0),
    remove: () => clearLatentCache(),
  },
  {
    id: "remote",
    group: "This machine",
    name: "The refiner's server",
    note: "The endpoint the remote refiner calls and the key it calls with. The "
        + "key never leaves this machine, and this is how it goes.",
    held: (kept) => (kept.remote ? "set" : 0),
    remove: () => saveRemote("", ""),
  },
  {
    id: "settings",
    group: "This machine",
    name: "Every setting on this page",
    note: "Quality, output folders, previews and appearance, back to what the "
        + "pack ships with.",
    // Always offered: there is no count of "how default" a settings file is,
    // and a page cannot honestly report one.
    held: () => "in force",
    remove: () => resetSettings(),
  },
];


class SettingsPage {
  constructor(resolve) {
    this.resolve = resolve;
    this.settings = null;   // until the server answers
    this.cache = null;      // what the reference cache is holding, once asked
    // What is stored, by row id, once the Stored data tab has asked. Null until
    // then: the tab counts presets by reading every index on disk, and a page
    // opened to change the video quality has no business doing that.
    this.kept = null;
    this.sweeping = false;  // the "remove everything" pass, while it runs
    this.problem = null;
    this.tab = TABS[0].key;
  }

  mount() {
    this.body = el("div", { class: "mmc-set-body" });
    this.tabs = TABS.map((tab) => el("button", {
      class: "mmc-tab",
      "aria-selected": tab.key === this.tab,
      text: t(tab.label),
      onclick: () => this.show(tab.key),
    }));
    this.modal = el("div", { class: "mmc-modal mmc-settings" }, [
      el("div", { class: "mmc-modal-head" }, [
        ...this.tabs,
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => this.close() }),
      ]),
      this.body,
      el("div", { class: "mmc-modal-foot" }, [
        el("button", { class: "mmc-add", text: t("Done"), onclick: () => this.close() }),
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
   * Painted first so the radio moves under the pointer, then corrected if the
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

  show(tab) {
    if (tab === this.tab) return;
    this.tab = tab;
    // The problem line belongs to the control that produced it, so it does not
    // follow you to a tab where it means nothing.
    this.problem = null;
    this.render();
    if (tab === "data") this.takeStock();
  }

  /**
   * Count everything the Stored data tab is about to offer to remove.
   *
   * Every reader is allowed to fail on its own: an install with no preset index
   * yet, a frontend with no userdata API, a server too old to answer for the
   * remote refiner. A row whose count could not be read says so and stays
   * pressable — the remove call is the one that decides, and it is idempotent.
   */
  async takeStock() {
    const [presets, picker, loras, remote] = await Promise.all([
      P.presetCounts().catch(() => ({})),
      pickerPrefsHeld().catch(() => 0),
      loraPrefsHeld().catch(() => 0),
      remoteStatus({ force: true }).catch(() => ({ url: "", key_set: false })),
    ]);
    this.kept = {
      presets,
      picker,
      loras,
      refiner: refinerStored(),
      cacheBytes: Number(this.cache?.bytes ?? 0),
      remote: !!(remote.url || remote.key_set),
    };
    if (this.tab === "data") this.render();
  }

  close() {
    this.unmount();
    this.resolve();
  }

  // ---- render ---------------------------------------------------------------

  render() {
    if (!this.settings) {
      this.body.replaceChildren(el("div", { class: "mmc-set-wait", text: this.problem ?? t("Reading settings…") }));
      return;
    }
    for (const [index, tab] of TABS.entries()) {
      this.tabs[index].setAttribute("aria-selected", String(tab.key === this.tab));
    }
    this.body.replaceChildren(
      ...(this.problem ? [el("div", { class: "mmc-set-problem", text: this.problem })] : []),
      ...(this.tab === "quality" ? [this.renderQuality()]
        : this.tab === "nodes" ? this.renderNodes()
        : this.tab === "appearance" ? this.renderAppearance()
        : this.tab === "data" ? this.renderStored()
        : this.renderFolders()),
    );
  }

  renderQuality() {
    const current = this.settings.video_crf;
    // A file edited by hand can hold any point on the scale. Shown as its own
    // row rather than silently rounded to the nearest tier — it is in force,
    // so it has to be visible, and picking a tier is how you leave it.
    const rows = QUALITY.some((tier) => tier.crf === current)
      ? QUALITY
      : [{ crf: current, label: "Custom",
           note: "Set by hand in the settings file. Pick one of the four below to leave it." },
         ...QUALITY];

    return this.section("Output", "Video quality",
      "How much the encoder may throw away when it writes an .mp4. Applies to "
      + "every render this ComfyUI makes, whatever workflow made it.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((tier) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": tier.crf === current,
          onclick: () => tier.crf !== current && this.set({ video_crf: tier.crf }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(tier.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(tier.note) }),
          ]),
          // The real encoder value, on every row. The rest of this pack shows
          // the exact filename and the exact pixel size under the friendly
          // word; a quality control that said only "Fine" would be the one
          // place in it that asks you to take an adjective on trust.
          el("span", { class: "mmc-set-value", text: t("crf {crf}", { crf: tier.crf }) }),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("MP4, H.264, 8-bit 4:2:0 — the file this pack has always written. "
                + "CRF is libx264's quality target: lower is better and larger, and six "
                + "points is roughly double the size. Needs ComfyUI 0.29 or newer; older "
                + "builds can only write the default."),
          }),
        ]),
      ]);
  }

  // ---- nodes ----------------------------------------------------------------

  /**
   * How big the picture the sampler broadcasts is, and how hard it is squeezed.
   *
   * The only thing on this tab that is not purely cosmetic — not because it
   * changes a render (it cannot; this is the picture you watch while one
   * happens) but because the frame has to *arrive*. It is a full-clip animated
   * WebP, re-encoded and sent on every sampling step, and a websocket behind a
   * reverse proxy has a frame cap: aiohttp's is 4 MiB and nothing raises it by
   * default. A frame over that does not arrive late — it takes the socket down
   * mid-render.
   *
   * So the default is the size a preview is actually looked at rather than the
   * override node's 1024, and the rails are here for the two directions that
   * leaves: a long 720p clip that still crosses a cap, and a machine on
   * localhost with room to spare that would rather see the detail.
   */
  renderPreviewSize() {
    const px = Number(this.settings.preview_max_px ?? 640);
    const quality = Number(this.settings.preview_quality ?? 80);

    const size = this.stopSlider({
      stops: PREVIEW_PX_STOPS,
      value: px,
      name: "Draw the step preview at",
      read: (value) => ({ value: String(value), unit: "px" }),
      note: (value) => value > 768
        ? t("Larger than any box that shows it. Costs an encode and the bytes every step.")
        : value < 384
          ? t("Small and cheap. For a wire that drops long renders at anything larger.")
          : t("The long edge. The box that shows it is a node face, or the fullscreen dock."),
      warn: (value) => value > 768,
      apply: (value) => this.set({ preview_max_px: value }),
    });

    const squeeze = this.stopSlider({
      stops: PREVIEW_Q_STOPS,
      value: quality,
      name: "At quality",
      read: (value) => ({ value: String(value) }),
      note: (value) => value >= 90
        ? t("Near-lossless, and several times the bytes of 80 for a decode of a "
            + "half-finished latent.")
        : t("The encoder's own scale. 80 is what the override node picks unasked."),
      warn: (value) => value >= 90,
      apply: (value) => this.set({ preview_quality: value }),
    });

    return this.section("Nodes", "Step preview",
      "How large the picture the sampler broadcasts each step is. It is a whole clip, "
      + "re-encoded and sent every step, and a websocket behind a proxy has a frame "
      + "limit — a frame past it takes the connection down mid-render rather than "
      + "arriving late. Nothing about the render changes: this is the picture you "
      + "watch while it happens.",
      [
        el("div", { class: "mmc-set-field mmc-set-bounds" }, [size, squeeze]),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Read when a render is queued, so the next one uses it. "
                + "Only KJNodes' preview override draws these frames at all."),
          }),
        ]),
      ]);
  }

  /**
   * What the node faces offer, as opposed to what a render writes. First (and
   * so far only) resident: the sampler row's two flow-shift pills, hidden by
   * default because most rows never leave the checkpoints' own schedule.
   *
   * Hiding the pills does not hide the values: the widgets stay on the node,
   * the turbo switch and loaded workflows still write them, and the graph
   * still honours them — which is why a value off the checkpoints' own 12/3
   * keeps its pill on screen whatever this says. In force means visible, the
   * same rule the Custom quality row lives by.
   */
  /**
   * What a blended seam hands the next shot (issues #41, #46). The latent is
   * the better join — the run is sliced off what the sampler made, so nothing
   * is decoded and re-encoded on the way — and the frames are the road every
   * render took before it existed, kept so the two can be compared on one
   * strip. Per machine, like the lead-in: it is a statement about how a seam is
   * conditioned, not about the piece, and the family decides whether it can
   * take a latent at all (`base.Family.hands_latents`).
   */
  renderLatentSeams() {
    const latent = this.settings.latent_seams !== false;
    const rows = [
      { value: true, label: "The latent",
        note: "The run is sliced off what the sampler made. Nothing is decoded and "
            + "encoded again on the way, so the next shot starts from the picture "
            + "the model actually drew." },
      { value: false, label: "The frames",
        note: "The road every render took before: the tail is read off the decode "
            + "and encoded again. Kept for a side-by-side on the same strip." },
    ];
    return this.section("Rendering", "Seam handoff",
      "What a blended seam hands the next shot: the source pass's own latent, or "
      + "its frames decoded and encoded again. The round trip darkens the run a "
      + "little and hardens its contrast, in the same direction at every seam, "
      + "and that walks down a strip.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.value === latent,
          onclick: () => row.value !== latent && this.set({ latent_seams: row.value }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Only blended seams between two generated shots. A seam off a clip, "
                + "a face-passed shot or a shot finished at another canvas reads the "
                + "frames either way. Read when a render is queued."),
          }),
        ]),
      ]);
  }

  /**
   * Whether the stage plays what it shows, or waits to be asked. On by
   * default — it is what the stage has always done — and off for the people
   * whose complaint is real: a canvas with a dozen finished renders on it is
   * a dozen looping decoders, all playing for nobody.
   *
   * UI-only, like everything else on this tab: the file written is the same
   * file, and the sound rules do not move — a clip started by hand still
   * follows the pointer, because no browser autoplays sound either way.
   */
  renderPreviews() {
    const playing = this.settings.autoplay_previews !== false;
    const rows = [
      { value: true, label: "Plays itself",
        note: "What the stage has always done: the clip loops silently as soon as it "
            + "lands, and the sound follows the pointer. Step previews animate as the "
            + "sampler works." },
      { value: false, label: "Waits for play",
        note: "The stage holds the first frame, still, with the browser's controls to "
            + "start it. For crowded canvases, where every looping clip is a decoder "
            + "running for nobody." },
    ];
    return this.section("Nodes", "Preview playback",
      "Whether the stage plays a clip the moment it has one — the finished render, "
      + "and the animated step previews while it samples. The file is the same "
      + "either way; this only decides whether it moves before being asked.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.value === playing,
          onclick: () => row.value !== playing && this.set({ autoplay_previews: row.value }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Open nodes pick the change up the next time they redraw — "
                + "closing this page is enough."),
          }),
        ]),
      ]);
  }

  /**
   * How many of a turbo render's opening steps run without the distillation.
   *
   * The other setting on this page that reaches the render, and the one people
   * arrive at this page looking for: a distillation LoRA is very good at
   * finishing a shot and it is not what decided the shot, so a piece rendered
   * entirely through one stops following the prompt as closely as the model on
   * its own would. This hands the opening steps back to the base weights and
   * lets the distillation finish, on the same schedule and the same seed.
   *
   * Per machine rather than per node because it is a statement about how you
   * use a distillation — the LoRA, the steps and the schedule are all still the
   * workflow's. A `.json` shared with someone who leaves this off renders the
   * distillation's own opening.
   */
  renderLeadIn() {
    const current = Number(this.settings.turbo_lead_in) || 0;
    // A file edited by hand can ask for more than the three rows offer. Shown
    // as its own row rather than silently rounded — it is in force, so it has
    // to be visible, and picking a row below is how you leave it.
    const rows = LEAD_IN.some((row) => row.steps === current)
      ? LEAD_IN
      : [{ steps: current, label: "Custom",
           note: "Set by hand in the settings file. Pick one of the rows below to leave it." },
         ...LEAD_IN];

    return [this.section("Rendering", "Turbo lead-in",
      "Turbo LoRAs buy their speed by collapsing the schedule, and the opening "
      + "steps are where a shot's composition and motion are actually decided — "
      + "which is why a distilled render stops listening to the prompt as closely. "
      + "This runs the opening on the checkpoint with the LoRA held off it, then "
      + "hands the rest of the same schedule to the distilled model.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.steps === current,
          onclick: () => row.steps !== current && this.set({ turbo_lead_in: row.steps }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Not extra steps: they come out of the count on the node, so a "
                + "6-step turbo render with a two-step lead-in is still six. Only "
                + "where the turbo switch has engaged a LoRA — a checkpoint with the "
                + "distillation merged into its weights has none to hold off. The "
                + "refine and face passes are untouched: they resume partway down "
                + "the schedule, so the steps this splits are not in them."),
          }),
        ]),
      ])];
  }

  /**
   * Whether the node faces offer the controls most rows never touch.
   *
   * The sampler row has grown: a cache, Spectrum, an attention backend, a
   * turbo switch with a lead-in inside it, and two accelerators that trade
   * something too subtle to be set by accident. Every one of them is worth
   * having and none of them is worth *reading past* on the way to the seed.
   *
   * So this is a length control, not a permission: nothing is disabled and
   * nothing is locked. And it never hides something that is on — a lead-in
   * that is set, a card already running low VRAM, keeps its pill whatever this
   * says. In force means visible, which is the same rule the custom quality
   * row and the shift pills live by, and it is what makes turning this off a
   * safe thing to do without checking what you had switched on.
   *
   * First on the tab because it decides how much of the rest of the tab there
   * is: the turbo lead-in section below only appears when this is on.
   */
  renderAdvanced() {
    const on = this.settings.advanced === true;
    const rows = [
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
    return this.section("Nodes", "Advanced controls",
      "How much of the sampler row a node draws. Everything here is available "
      + "either way — this decides what is on screen while you work, not what a "
      + "render is allowed to do.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.value === on,
          onclick: () => row.value !== on && this.set({ advanced: row.value }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Open nodes pick the change up the next time they redraw — "
                + "closing this page is enough."),
          }),
        ]),
      ]);
  }

  renderNodes() {
    const shown = this.settings.show_shift_pills === true;
    const rows = [
      { value: false, label: "Hidden",
        note: "The row before the shifts arrived. A value away from the checkpoints' "
            + "own schedule — a turbo preset, a loaded workflow — still shows its "
            + "pill: it is in force, so it stays visible." },
      { value: true, label: "Shown",
        note: "Two stepper pills after the scheduler, for dialling the two schedules "
            + "by hand. A turbo LoRA's card may name the values it was distilled against." },
    ];
    // The lead-in is an advanced control, so its section comes and goes with
    // the switch above — except while it is set, which is the rule the pill
    // follows too: a setting in force must be reachable from the page that
    // holds it, or it is a number changing renders with nowhere to change it
    // back.
    const leadIn = this.settings.advanced === true || Number(this.settings.turbo_lead_in) > 0
      ? this.renderLeadIn() : [];
    return [this.renderAdvanced(), this.renderPreviews(), this.renderPreviewSize(),
      ...leadIn, this.renderLatentSeams(), this.renderRefCache(),
      this.section("Nodes", "Flow shift pills",
      "Whether the sampler row offers H3's two flow shifts — the video and audio "
      + "schedule clocks. The values apply either way; this only decides who has "
      + "to look at them.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.value === shown,
          onclick: () => row.value !== shown && this.set({ show_shift_pills: row.value }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Open nodes pick the change up the next time they redraw — "
                + "closing this page is enough."),
          }),
        ]),
      ])];
  }


  /**
   * Whether a reference's latents are kept between renders.
   *
   * A generation caches on its whole request, so editing one word of the prompt
   * re-decodes and re-encodes every reference the shot cites — and a reference
   * does not know the prompt exists. Kept, they are encoded once per (file,
   * canvas, VAE) and the prompt is free to move.
   *
   * It cannot change what a render produces, only how long it takes: the
   * encoder rounds a reference's presentation to 8 bits whether this is on or
   * off, so a cached reference and a freshly encoded one are the same tensors.
   * That is what makes this a safe switch rather than a quality decision.
   */
  renderRefCache() {
    const on = this.settings.latent_cache !== false;
    const rows = [
      { value: true, label: "Kept",
        note: "A reference is encoded once and reused until its file, the canvas it "
            + "was encoded at, or the VAE changes. Editing the prompt, the seed, the "
            + "sampler or the other references reuses it." },
      { value: false, label: "Encoded every time",
        note: "What every render did before this existed. For a box with no room "
            + "to spare." },
    ];
    return this.section("Rendering", "Reference cache",
      "Attaching a video or a cast member means decoding it and pushing it "
      + "through the VAE, and on a high-resolution source that is most of the "
      + "wait before sampling starts. None of it depends on the prompt.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.value === on,
          onclick: () => row.value !== on && this.set({ latent_cache: row.value }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        ...(on ? [this.cacheBounds()] : []),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Kept beside your settings, so restarting ComfyUI does not lose "
                + "them. Only this page and the two limits above ever remove one."),
          }),
          ...(this.cache && this.cache.entries
            ? [el("button", { class: "mmc-opt mmc-set-clear", text: t("Clear"),
                              onclick: () => this.clearCache() })]
            : []),
        ]),
      ]);
  }

  /**
   * The two limits, in the card the typed settings use.
   *
   * They are one setting asked twice — how long, and how much — so they share a
   * card split by a hairline, the way the two output folders do.
   *
   * The size rail carries a mark at what the store is *actually* holding, which
   * is the one thing on this page that is a reading rather than a choice: a
   * ceiling is a decision about a real number, and asking for it without
   * showing that number is asking somebody to guess. It is the pack's accent
   * rather than the rail's blue so it cannot be mistaken for a second thumb.
   * The retention rail has no such mark, because there is nothing true to put
   * on it.
   */
  cacheBounds() {
    const gb = Number(this.settings.latent_cache_gb ?? 8);
    const days = Number(this.settings.latent_cache_days ?? 30);
    const held = Number(this.cache?.bytes ?? 0);

    const keep = this.stopSlider({
      stops: KEEP_STOPS,
      value: days,
      name: "Keep unread references for",
      // Off, there is nothing on disk to age, and a live retention rail beside
      // a store that holds nothing would be a control with no effect.
      disabled: gb <= 0,
      read: (value) => ({ value: keepFor(value) }),
      note: (value) => gb <= 0
        ? t("Nothing is written to disk to keep.")
        : value <= 0
          ? t("Only the size limit below ever drops one.")
          : t("Dropped once nothing has read it for that long."),
      apply: (value) => this.set({ latent_cache_days: value }),
    });

    const size = this.stopSlider({
      stops: SIZE_STOPS,
      value: gb,
      name: "Never grow past",
      read: (value) => value <= 0
        ? { value: t("Off") }
        : { value: String(value), unit: "GB" },
      note: (value) => {
        if (value <= 0) return t("Nothing is written to disk — this session only.");
        const over = held - value * 1024 * 1024 * 1024;
        if (over > 0) return t("Over by {size}; the next render drops that much.",
                               { size: said(over) });
        return held
          ? t("Holding {size} across {entries} references.",
              { size: said(held), entries: this.cache.entries })
          : t("Nothing stored yet.");
      },
      warn: (value) => value > 0 && held > value * 1024 * 1024 * 1024,
      mark: held > 0 ? { at: held / (1024 * 1024 * 1024), label: said(held) } : null,
      apply: (value) => this.set({ latent_cache_gb: value }),
    });

    return el("div", { class: "mmc-set-field mmc-set-bounds" }, [keep, size]);
  }

  /**
   * One rail over a list of stops. -> the element.
   *
   * `input` repaints the readout by hand and `change` writes the setting: a
   * drag that re-rendered the page would pull the rail out from under the
   * thumb, which is the deal every other slider in this pack has.
   */
  stopSlider({ stops, value, name, read, note, warn, mark, apply, disabled }) {
    // A value set by hand in the settings file takes its own place on the rail
    // rather than being rounded onto a neighbour: it is in force, so it has to
    // be reachable, and moving off it is how you leave it. Sorted by size, with
    // the "no limit" stop held at the end whatever number stands for it.
    const offered = stops.some((stop) => stop.value === value)
      ? stops
      : [...stops, { value }].sort((a, b) => (a.value || Infinity) - (b.value || Infinity));
    const index = offered.findIndex((stop) => stop.value === value);
    const last = offered.length - 1;

    const shown = el("span", { class: "mmc-edge" });
    const unit = el("span", { class: "mmc-edge-unit" });
    const said = el("span");
    // A gauge rather than a tick: "how full" is what a ceiling is set to
    // answer, and a bar answers it where a point only says where. Drawn in the
    // rail's own stop space so it lines up with the thumb it is being compared
    // against — past the thumb is over the limit, and reads as over without
    // anything having to say so. Built before `paint`, which reaches for it on
    // its first call.
    const fill = mark ? el("span") : null;
    const reading = mark
      ? el("div", { class: "mmc-set-usage", title: mark.label }, [fill])
      : null;
    fill?.style.setProperty("--p", String(alongStops(offered, mark.at)));

    const paint = (at) => {
      const now = offered[at].value;
      const showing = read(now);
      shown.textContent = showing.value;
      unit.textContent = showing.unit ?? "";
      said.textContent = note(now);
      const over = Boolean(warn?.(now));
      said.classList.toggle("over", over);
      reading?.classList.toggle("over", over);
      for (const [position, tick] of ticks.entries()) {
        tick.classList.toggle("on", position === at);
      }
    };

    const rail = el("input", {
      type: "range", min: 0, max: last, step: 1, value: index,
      disabled: Boolean(disabled),
      "aria-label": t(name),
      oninput: (event) => paint(Number(event.target.value)),
      onchange: (event) => apply(offered[Number(event.target.value)].value),
    });

    const ticks = offered.map((stop, position) => {
      const tick = el("button", {
        class: "mmc-slider-mark",
        disabled: Boolean(disabled),
        title: read(stop.value).value,
        onclick: () => { rail.value = String(position); paint(position); apply(stop.value); },
      }, stop.label ? [el("span", { text: t(stop.label) })] : []);
      // A custom property has to go through setProperty; Object.assign drops it.
      tick.style.setProperty("--p", String(position / last));
      return tick;
    });

    paint(index);
    return el("div", { class: disabled ? "mmc-set-slider off" : "mmc-set-slider" }, [
      el("div", { class: "mmc-note-key", text: t(name) }),
      el("div", { class: "mmc-slider-read" }, [el("span", {}, [shown, unit]), said]),
      el("div", { class: "mmc-slider-row" }, [
        el("div", { class: "mmc-slider-track" }, [rail, ...ticks, ...(reading ? [reading] : [])]),
      ]),
    ]);
  }

  // ---- appearance -------------------------------------------------------------

  /**
   * How large this pack draws its own text.
   *
   * One multiplier over every size in styles/ — see `--mmc-type` in
   * styles/base.js for why it is a multiplier and not a set of named sizes. It
   * is written onto the document out of `noteSettings`, so the page you are
   * setting it on resizes under the pointer: the best preview a control like
   * this can have is the thing itself, and it costs nothing to have.
   *
   * What moves with it is the text and what holds text — the pills, the rail's
   * tiles, the fixed-height segments that carry a label. What does not is the
   * room around them and the picture: the insets, the gaps between cards, the
   * plate. That is the line between a text size and a magnifier, and the browser
   * already has a magnifier on Cmd +.
   */
  renderAppearance() {
    const current = Number(this.settings.text_scale) || 1;
    // A file edited by hand can hold any point between settings.py's 0.8 and
    // 1.6. Shown as its own row rather than rounded to the nearest offer — it is
    // in force, so it has to be visible, and picking a row is how you leave it.
    const rows = TEXT_SCALE.some((row) => row.scale === current)
      ? TEXT_SCALE
      : [{ scale: current, label: "Custom",
           note: "Set by hand in the settings file. Pick one of the rows below to leave it." },
         ...TEXT_SCALE];

    return [this.section("Interface", "Text size",
      "How large this pack draws its own text, everywhere it draws any: the node "
      + "faces, the fullscreen editor, the timeline, the picker, and this page — "
      + "which is why the words you are reading move as you choose. Nothing of "
      + "ComfyUI's own moves with it.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.scale === current,
          onclick: () => row.scale !== current && this.set({ text_scale: row.scale }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
          // The number in force, on every row — the same promise the quality
          // tab's crf column makes. A percentage rather than the stored 1.12,
          // because "112%" is the one reading of a multiplier nobody has to be
          // told how to read.
          el("span", { class: "mmc-set-value", text: `${Math.round(row.scale * 100)}%` }),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Text and the controls that carry it — the pills, the tool "
                + "tiles, the segments. The room around them and the picture stay "
                + "where they are, so this makes the words larger rather than the "
                + "window smaller. Open nodes pick the change up immediately. For "
                + "everything at once, including ComfyUI's own chrome, the "
                + "browser's own zoom is still the better tool."),
          }),
        ]),
      ]),
      this.themeSection(),
      this.liftSection()];
  }

  /**
   * Which palette the pack wears.
   *
   * The whole of this pack's colour derives from two of ComfyUI's own variables
   * — see `--mmc-ground` and `--mmc-ink` in styles/base.js — so following the
   * desk costs nothing and happens by itself. This setting only exists for the
   * case following gets wrong: a light desk under a pack whose job is showing
   * you a picture.
   */
  themeSection() {
    const current = this.settings.theme === "dark" ? "dark" : "follow";
    return this.section("Interface", "Colour",
      "Whether this pack takes its colours from ComfyUI's palette or keeps a "
      + "dark ground for the fullscreen editor. Following is the default and "
      + "covers every palette there is, including ones you built yourself.",
      [
        el("div", { class: "mmc-set-choices" }, THEMES.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.value === current,
          onclick: () => row.value !== current && this.set({ theme: row.value }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("This pack only. ComfyUI's own chrome is set in its own "
                + "Appearance settings and does not move with this. The dark "
                + "ground reaches the fullscreen editor and not the node faces, "
                + "which stay part of the node ComfyUI draws around them. The "
                + "accent amber is the pack's either way — on a pale palette it "
                + "is drawn a shade deeper, because amber on white is not a "
                + "colour a word can be written in."),
          }),
        ]),
      ]);
  }

  /**
   * How far the surfaces step off the ground beneath them.
   *
   * One multiplier over all four rungs of the ramp — see `--mmc-lift` in
   * styles/base.js. It is here rather than left as a constant because the ramp
   * is proportional to a palette's own contrast and some palettes have very
   * little: there is no one set of percentages right for a ground of #ffffff
   * and one of #073642.
   */
  liftSection() {
    const current = Number(this.settings.surface_lift) || 1;
    // A hand-edited file can hold any point between settings.py's 0.4 and 2.
    // Shown as its own row rather than rounded to the nearest offer, the same
    // promise the text scale above makes.
    const rows = SURFACE_LIFT.some((row) => row.lift === current)
      ? SURFACE_LIFT
      : [{ lift: current, label: "Custom",
           note: "Set by hand in the settings file. Pick one of the rows below to leave it." },
         ...SURFACE_LIFT];

    return this.section("Interface", "Surface separation",
      "How far this pack's cards and panels step off the ground behind them. "
      + "Every surface is a mix of the palette's own background and its text "
      + "colour; this says how far along that mix each one sits.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.lift === current,
          onclick: () => row.lift !== current && this.set({ surface_lift: row.lift }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
          el("span", { class: "mmc-set-value", text: `${Math.round(row.lift * 100)}%` }),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("Applies to whatever palette is in force, so it is worth a "
                + "second look after changing the row above. The page you are "
                + "reading moves with it, which is the best preview a control "
                + "like this can have."),
          }),
        ]),
      ]);
  }

  // ---- folders ---------------------------------------------------------------

  /**
   * Where each family files what it makes: one section, two cards, a row per
   * family in each.
   *
   * It was one row per *kind* until families arrived, and that was the bug: an
   * LTX 2.5 piece wrote `minimax/renders/H3_00021_.mp4` — the wrong shelf and
   * somebody else's name on the file. A render lands somewhere because of what
   * rendered it, so the question is asked once per family, and the families
   * come off the catalog rather than a list here: a new one gets its row by
   * existing, and gets it filled with the default the save node will use,
   * because that default is served in its manifest.
   *
   * The two cards keep their own heading and the renders/stills split the
   * gallery sorts on, but they still share one section: the footnote below them
   * is about every field on the tab, and saying it twice taught nothing.
   *
   * This used to be a pill on every node, which meant every node was a place
   * the answer could differ and a shared workflow arrived carrying somebody
   * else's folder names. It is one answer per family per machine now.
   */
  renderFolders() {
    const renders = FAMILIES.filter((family) => family.produces.includes("video"));
    const stills = FAMILIES.filter((family) => family.produces.includes("still"));
    return [
      this.section("Output", "Folders",
        "Where this ComfyUI files what it makes. Every family gets a folder of "
        + "its own, and renders and stills get their own shelf — which is how "
        + "the gallery tells any of them apart.",
        [
          this.folderCard("Renders", "video_prefix", renders, "video", "mp4"),
          this.folderCard("Stills", "image_prefix", stills, "still", "png"),
          el("div", { class: "mmc-set-foot" }, [
            el("span", { text: t("Relative to ComfyUI's output folder (") }),
            el("code", { text: "--output-directory" }),
            el("span", { text: t(" moves that). The last part names the files, not a folder — "
                             + "core's counter numbers them apart.") }),
          ]),
        ]),
    ];
  }

  /**
   * One shelf's card: a heading and a destination per family that files there.
   *
   * `kind` is which half of the family's `output` block holds its default —
   * H3 is in both cards and its two defaults are different folders, so the
   * fallback has to be read per card and not per family.
   */
  folderCard(title, key, families, kind, extension) {
    return el("div", { class: "mmc-set-group" }, [
      el("div", { class: "mmc-set-group-name", text: t(title) }),
      el("div", { class: "mmc-set-field" },
        families.map((family) => this.folderRow(
          key, family.id, family.label, family.output?.[kind] ?? "", extension))),
    ]);
  }

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
    const example = el("div", { class: "mmc-out-example" });
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
      example.replaceChildren(...(error ? [] : [
        // One line: the folder half dim, the file half bright. The colour break
        // is the split nobody expects — "minimax/renders/H3" is a file called
        // H3 in a folder called renders, not a folder called H3 — and a break
        // in the path itself says that better than labels beside it did.
        el("span", { class: "mmc-out-dim", text: "→ " }),
        el("span", {
          class: "mmc-out-dim",
          text: folderOf(prefix) ? `output/${folderOf(prefix)}/` : "output/",
        }),
        el("span", { text: examplePath(stemOf(prefix), { extension }) }),
      ]));
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
      field,
      problem,
      example,
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
   * An inventory rather than a row of red buttons. Everything on this tab is
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
  renderStored() {
    const groups = [];
    for (const row of STORED) {
      const last = groups[groups.length - 1];
      if (last && last.name === row.group) last.rows.push(row);
      else groups.push({ name: row.group, rows: [row] });
    }
    return [
      ...groups.map(({ name, rows }) => this.section(name, GROUP_TITLE[name].title,
        GROUP_TITLE[name].note,
        [el("div", { class: "mmc-set-field mmc-zone" }, rows.map((row) => this.storedRow(row)))])),
      this.section("Everything", "Start over",
        "Every row above, in one press: the library, this browser's memory of "
        + "how you work, and every setting back to default. Nothing here touches "
        + "a render, a reference or a workflow — those are files, and this page "
        + "does not delete files.",
        [el("div", { class: "mmc-set-field" }, [this.sweepButton()])]),
    ];
  }

  /** One row: what it is, what is behind it, and the press. */
  storedRow(row) {
    const kept = this.kept ? row.held(this.kept) : null;
    const empty = kept === 0;
    const held = this.kept === null ? t("Counting…")
      : empty ? t("none")
      : typeof kept === "number" ? String(kept) : t(kept);
    const press = el("button", {
      class: "mmc-zone-go",
      disabled: this.kept === null || empty || this.sweeping ? true : undefined,
      text: t("Remove"),
      onclick: () => this.armRow(row, press),
    });
    return el("div", { class: "mmc-zone-row", "data-empty": String(empty) }, [
      el("div", { class: "mmc-zone-what" }, [
        el("span", { class: "mmc-zone-name", text: t(row.name) }),
        el("span", { class: "mmc-zone-note", text: t(row.note) }),
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
    for (const press of this.body.querySelectorAll(".armed")) {
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
      disabled: this.kept === null || !standing || this.sweeping ? true : undefined,
      text: this.sweeping ? t("Removing…")
        : this.kept === null ? t("Counting…")
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

  /** One setting, under a section heading. The heading repeats down the page as
   *  more of them arrive; grouping is what keeps this readable at ten. */
  section(group, title, description, controls) {
    return el("div", { class: "mmc-set-section" }, [
      el("div", { class: "mmc-note-key", text: t(group) }),
      el("div", { class: "mmc-set-title", text: t(title) }),
      el("div", { class: "mmc-set-desc", text: t(description) }),
      ...controls,
    ]);
  }
}
