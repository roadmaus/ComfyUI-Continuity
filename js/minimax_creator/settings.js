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
import { loadSettings, saveSettings, noteSettings } from "./api.js";
import { t } from "./i18n.js";
import { TOKENS, cleanPrefix, folderOf, stemOf, examplePath } from "./outputs.js";

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

const TABS = [
  { key: "quality", label: "Quality" },
  { key: "folders", label: "Folders" },
  { key: "nodes", label: "Nodes" },
  { key: "appearance", label: "Appearance" },
];

class SettingsPage {
  constructor(resolve) {
    this.resolve = resolve;
    this.settings = null;   // until the server answers
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
        note: "The sampler row as most renders use it: the seed, the schedule, the "
            + "caches and the attention backend. A control you have already switched "
            + "on still shows its pill — it is in force, so it stays visible." },
      { value: true, label: "Everything",
        note: "Adds the turbo lead-in, low VRAM and fast math to the sampler row, and "
            + "the turbo lead-in to this page. For the rows where the last few percent "
            + "of speed or of VRAM is worth a decision." },
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
    return [this.renderAdvanced(), this.renderPreviews(), ...leadIn,
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
   * Where the two kinds of file land: one section, one card, two rows.
   *
   * The two prefixes are one setting asked twice, so they read as two rows of
   * one card the way the quality tiers do — two full sections was the same
   * heading, description and token row said twice, and the second telling
   * taught nothing the first had not.
   *
   * This used to be a pill on every node, which meant every node was a place
   * the answer could differ and a shared workflow arrived carrying somebody
   * else's folder names. It is one answer per machine now.
   */
  renderFolders() {
    return [
      this.section("Output", "Folders",
        "Where this ComfyUI files what it makes. Renders and stills get their "
        + "own, which is how the gallery tells them apart.",
        [
          el("div", { class: "mmc-set-field" }, [
            this.folderRow("video_prefix", "Renders",
              "finished videos — the Creator and the Timeline", "mp4"),
            this.folderRow("image_prefix", "Stills",
              "pre-stage stills", "png"),
          ]),
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
   * One destination: a name, the field, and the single line it resolves to.
   *
   * Written through on Enter or on leaving the field rather than on every
   * keystroke — the rest of the page writes on a click, and a click is finished
   * where a half-typed path is not. What is live is the *reading*: the line
   * under the field moves as you type, folder half dim and filename bright,
   * because a prefix is two things at once and "renders/H3" being a file called
   * H3 rather than a folder called H3 is the one surprise this page holds.
   *
   * The token chips only exist while the field has focus — CSS, off
   * :focus-within — so the page at rest is two fields, not sixteen buttons.
   */
  folderRow(key, title, description, extension) {
    const stored = this.settings[key];
    const field = el("input", {
      class: "mmc-out-field",
      type: "text",
      value: stored,
      spellcheck: false,
      "aria-label": t("{title} — folder and filename prefix", { title: t(title) }),
      onkeydown: (event) => {
        event.stopPropagation();
        if (event.key === "Enter") field.blur();
        if (event.key === "Escape") { field.value = this.settings[key]; field.blur(); }
      },
      onchange: () => commit(),
      onblur: () => commit(),
    });
    const problem = el("div", { class: "mmc-out-problem" });
    const example = el("div", { class: "mmc-out-example" });

    const paint = () => {
      const { prefix, error } = cleanPrefix(field.value, stored);
      field.classList.toggle("bad", Boolean(error));
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
      if (error || prefix === this.settings[key]) return;
      this.set({ [key]: prefix });
    };

    field.addEventListener("input", paint);
    paint();

    return el("div", { class: "mmc-set-dest" }, [
      el("div", { class: "mmc-set-dest-head" }, [
        el("span", { class: "mmc-set-dest-name", text: t(title) }),
        el("span", { class: "mmc-set-dest-sub", text: t(description) }),
      ]),
      field,
      problem,
      example,
      // Core expands these when the file is written. Buttons because nobody
      // guesses the spelling of `%year%`, and a folder per shoot date is the
      // most useful thing this field does. The chips say the word and the
      // field receives the token: `%year%` is core's syntax and the stored
      // value, not something anyone should have to read on a button — the
      // reading underneath shows what it turns into the moment it lands.
      // Inserting is typing, not finishing: it repaints the reading and leaves
      // the write to Enter or blur, the same deal the keyboard has — a commit
      // here would re-render the page and yank the field (row and caret both)
      // out from under the second click. pointerdown is swallowed so the click
      // does not blur the field first.
      el("div", { class: "mmc-out-tokens" }, [
        el("span", { class: "mmc-out-tokens-key", text: t("insert") }),
        ...TOKENS.map((token) => el("button", {
        class: "mmc-out-token",
        text: token.replaceAll("%", ""),
        title: t("Inserts {token} — filled in when the file is written", { token }),
        onpointerdown: (event) => event.preventDefault(),
        onclick: () => {
          const at = field.selectionStart ?? field.value.length;
          field.value = field.value.slice(0, at) + token + field.value.slice(field.selectionEnd ?? at);
          field.focus();
          field.setSelectionRange?.(at + token.length, at + token.length);
          paint();
        },
      }))]),
    ]);
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
