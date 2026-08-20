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
// Two tabs, because the page now answers two questions that are not the same
// question: how good the file is, and where it goes. Both are this machine's
// rather than the workflow's, which is the only reason they share a page.

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

export function openSettings() {
  return new Promise((resolve) => new SettingsPage(resolve).mount());
}

const TABS = [
  { key: "quality", label: "Quality" },
  { key: "folders", label: "Folders" },
  { key: "nodes", label: "Nodes" },
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
    this.render();
    try {
      this.settings = await saveSettings(patch);
      // The bodies read some of these (the shift pills' visibility) off the
      // cache in api.js, so what the server actually stored goes there too.
      noteSettings(this.settings);
    } catch (error) {
      this.settings = previous;
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
    return [this.renderPreviews(), ...this.renderScopes(), this.section("Nodes", "Flow shift pills",
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
   * Whether a reference's scope is written into the prompt for the model.
   *
   * The one setting on this page that reaches the render, which is worth being
   * plain about: the same `.json` queues different prose on a machine that has
   * this on. It sits here anyway because it is a statement about how you prompt
   * rather than about this piece — some people write the scope into their own
   * sentence and want no second copy of it — and a per-node copy would turn one
   * answer into a dozen.
   */
  renderScopes() {
    const on = this.settings.define_refs === true;
    const rows = [
      { value: false, label: "Only the refiner",
        note: "What every render did before this existed. The scope reaches Refine's "
            + "glossary and stops there, so a piece queued without a rewrite has the "
            + "chip set to something the model is never told." },
      { value: true, label: "Also the prompt",
        note: "One sentence per reference, written in front of the description: what "
            + "that file lends and what it does not. Shown in the box above your own "
            + "text, so you can read what is being sent. A refined reference form "
            + "says it better and replaces these." },
    ];
    return [this.section("Nodes", "Reference scopes in the prompt",
      "H3 has no reference-conditioning switch — the DiT is handed the same tensor "
      + "whatever a chip says, so 'camera only' or 'her face, not her background' is "
      + "prose or it is nothing. This decides whether the compiler writes that prose "
      + "itself, or leaves it to Refine.",
      [
        el("div", { class: "mmc-set-choices" }, rows.map((row) => el("button", {
          class: "mmc-opt mmc-set-opt",
          "aria-checked": row.value === on,
          onclick: () => row.value !== on && this.set({ define_refs: row.value }),
        }, [
          el("span", { class: "mmc-radio" }),
          el("span", { class: "mmc-set-opt-text" }, [
            el("span", { class: "mmc-set-opt-label", text: t(row.label) }),
            el("span", { class: "mmc-set-opt-note", text: t(row.note) }),
          ]),
        ]))),
        el("div", { class: "mmc-set-foot" }, [
          el("span", {
            text: t("This one changes what is queued, not just what is drawn: a "
                + "workflow shared with someone whose copy is set the other way "
                + "renders the other prose."),
          }),
        ]),
      ])];
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
