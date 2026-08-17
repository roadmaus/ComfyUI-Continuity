// The sampler row, drawn the same way on both nodes.
//
// Both the Creator and the Timeline own their sampler and declare the same
// widgets under the same names, so there is one row and both mount it. It lives
// outside the panel on either node because the panel says what the piece *is*
// and this says how it is run.
//
// The widgets are the real ComfyUI ones, hidden by the entry point and re-drawn
// here: `graphToPrompt` reads values off `node.widgets`, so these pills write
// through to them rather than holding state of their own.

import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import { openChoicePopover, stepperPill } from "./pills.js";
import { uiSetting } from "./api.js";
import { lastSeed } from "./seedmemory.js";

export const SEED_CONTROL = ["fixed", "increment", "decrement", "randomize"];

// Every widget this row draws. The entry point hides exactly these, so a name
// added here without being added there would render twice — once as a pill and
// once as the stock widget underneath.
export const SAMPLING_WIDGETS = [
  "seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler",
  "shift_video", "shift_audio",
  "block_cache", "spectrum", "spectrum_blend", "sage",
];

const BLOCK_CACHE_TITLE = {
  off: "Step caching is off.",
  safe: "FirstBlockCache, safest preset — fewest skipped steps.",
  fast: "FirstBlockCache, the pack's recommended preset.",
  aggressive: "FirstBlockCache, most skipping — fastest, furthest from a native render.",
  easy: "EasyCache — core's own step reuse, nothing to install. Cannot be combined with Spectrum.",
  tea: "TeaCache — skips transformer forwards on timestep similarity. Needs ComfyUI-MiniMaxH3-TeaCache.",
};

/**
 * Read and write the real widgets, by name.
 *
 * The `{value, set}` pair every body hands this row and `turbo.js` — the one
 * thing all three node bodies had a character-for-character copy of, differing
 * only in what they called the map they were holding. Here rather than on a
 * shared base class, because that is all they had in common: their `commit`,
 * `destroy` and `adoptWeights` are three different jobs that happen to share
 * three names, and a base class holding one function would have bought that
 * function at the price of a hierarchy.
 *
 * No re-render on write. Everything that uses this commits — and renders — once
 * at the end rather than three times along the way; a body that wants the
 * redraw does it in its own `set`.
 *
 * @param {() => object} widgets  name -> real ComfyUI widget. A thunk because a
 *   body may be handed its widgets after it is built.
 * @param {() => void} [onChange] the node needs redrawing on the canvas
 */
export function widgetIO(widgets, onChange) {
  return {
    value: (name, fallback) => widgets()?.[name]?.value ?? fallback,
    set: (name, value) => {
      const widget = widgets()?.[name];
      if (!widget) return;
      widget.value = value;
      // Some of them — the seed's after-generate control — hang behaviour off
      // the callback rather than off the value, so it is not optional.
      widget.callback?.(value);
      onChange?.();
    },
  };
}

/**
 * @param {object} options
 * @param {object} options.widgets           name -> real ComfyUI widget
 * @param {(name, fallback) => any} options.value
 * @param {(name, value) => void} options.set write-through to the widget
 * @param {boolean} options.perSegment       true when there is more than one
 *                                           generation, which changes what the
 *                                           seed and step counts mean
 * @param {HTMLElement[]} [options.turbo]     the turbo switch's pills (see
 *   turbo.js), drawn with the accelerators because that is what it is — built
 *   by the caller because it needs the state, which this row otherwise doesn't
 * @param {HTMLElement[]} [options.trailing] appended after the accelerators —
 *   the weights pill, which belongs on this row because it is the other half of
 *   "how is this run" and nowhere else because it is not a sampler setting
 * @returns {HTMLElement}
 */
export function samplingBar({ widgets, value, set, perSegment = false, turbo = [], trailing = [] }) {
  const pills = [];

  if (widgets.seed) {
    const control = value("control_after_generate", "fixed");
    // What the last queue actually ran on, offered back. Always drawn, beside
    // the dice it undoes — a control that appears only once it would do
    // something is a control nobody knows is there, which is the whole of what
    // was wrong with hiding it. Dimmed and inert until there is a seed to go
    // back to, and again once the seed already is that one.
    const last = lastSeed(widgets.seed);
    const reusable = last !== null && last !== Number(value("seed", 0));
    const seedText = String(value("seed", 0));
    pills.push(el("div", { class: "mmc-pill mmc-pill-group" }, [
      el("button", {
        class: "mmc-step mmc-seed-dice",
        title: t("Roll a new seed now"),
        onclick: () => set("seed", Math.floor(Math.random() * 0xffffffff)),
      }, [icon("dice", 15)]),
      el("button", {
        class: "mmc-step mmc-seed-last",
        // `.mmc-step:disabled` already dims it and refuses the cursor.
        disabled: !reusable,
        title: last === null
          ? t("Nothing queued yet — after a render this comes back to the seed it ran on")
          : t("Back to {seed}, the seed the last queue ran on", { seed: last }),
        onclick: () => { if (reusable) set("seed", last); },
      }, [icon("rewind", 15)]),
      el("input", {
        class: "mmc-seed-input",
        type: "text",
        value: seedText,
        // Sized to the digits it is holding. The field was 92px, which is a
        // guess that fits about eight digits — and seeds are ten, so the number
        // that identifies the render was the one thing on the row you could not
        // read. `ch` is exactly one digit in the mono face the stylesheet gives
        // this, so the pill breathes with its content instead: tight around a
        // hand-typed 7, wide enough for anything the dice can roll.
        style: { width: `${Math.min(21, Math.max(5, seedText.length + 1))}ch` },
        title: perSegment
          ? t("One seed for the whole piece: every segment runs on this number.")
          : t("The seed of the one generation."),
        onchange: (event) => {
          const parsed = Number(String(event.target.value).replace(/[^\d]/g, "")) || 0;
          set("seed", parsed);
        },
        onpointerdown: (event) => event.stopPropagation(),
      }),
      // Quiet on "fixed", which is now the default and the state where nothing
      // happens; awake on the three that move the seed between queues. The same
      // rule the accelerator pills follow — what is doing something to your
      // render is what is lit — and it hands the digits back the emphasis they
      // were competing with.
      ...(widgets.control_after_generate ? [el("button", {
        class: `mmc-ghost mmc-seed-mode${control === "fixed" ? "" : " on"}`,
        title: t("What happens to the seed after each queue"),
        text: control,
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("After generate"),
          options: SEED_CONTROL,
          value: control,
          onPick: (picked) => set("control_after_generate", picked),
        }),
      })] : []),
    ]));
  }

  if (widgets.steps) {
    pills.push(stepperPill({
      value: Number(value("steps", 20)), min: 1, max: 200, step: 1,
      iconName: "steps", width: "42px",
      title: perSegment ? t("Denoising steps, per segment") : t("Denoising steps"),
      format: (n) => t("{n} steps", { n }),
      onChange: (next) => set("steps", next),
    }));
  }

  if (widgets.cfg) {
    pills.push(stepperPill({
      value: Number(value("cfg", 1)), min: 0, max: 30, step: 0.5, width: "52px",
      title: t("Classifier-free guidance. The distilled H3 checkpoints want 1.0, "
           + "and at 1.0 the negative is skipped entirely."),
      format: (n) => t("cfg {n}", { n: n.toFixed(1) }),
      onChange: (next) => set("cfg", next),
    }));
  }

  for (const [name, label] of [["sampler_name", "Sampler"], ["scheduler", "Scheduler"]]) {
    const widget = widgets[name];
    if (!widget) continue;
    const options = widget.options?.values || [];
    pills.push(el("button", {
      class: "mmc-pill",
      title: t(label),
      onclick: (event) => openChoicePopover(event.currentTarget, {
        title: t(label),
        options: typeof options === "function" ? options(widget) : options,
        value: widget.value,
        onPick: (picked) => set(name, picked),
      }),
    }, [el("span", { text: String(widget.value) })]));
  }

  // The flow shifts, H3's two clocks. Drawn as one compact stepper pair after
  // the scheduler because they are schedule too: the checkpoints' own values
  // by default, reset by the turbo switch to what the picked LoRA's card
  // names, and honest about which track a wrong value ruins first.
  //
  // Hidden unless Settings → Nodes asks for them: most rows never leave the
  // checkpoints' own schedule, and the widgets keep working underneath — the
  // turbo switch still writes them, loaded workflows still carry them. A value
  // *off* that schedule shows its pill whatever the setting says, the custom-CRF
  // rule: what is in force has to be visible, and hiding it is how a stale
  // turbo preset would quietly ruin every later render.
  const showShifts = uiSetting("show_shift_pills", false);
  if (widgets.shift_video && (showShifts || Number(value("shift_video", 12)) !== 12)) {
    pills.push(stepperPill({
      value: Number(value("shift_video", 12)), min: 0.01, max: 100, step: 0.5, width: "48px",
      title: t("The video flow shift. 12 is the checkpoints' own schedule; a turbo LoRA's card may name another."),
      format: (n) => t("shift {n}", { n: +n.toFixed(2) }),
      onChange: (next) => set("shift_video", next),
    }));
  }
  if (widgets.shift_audio && (showShifts || Number(value("shift_audio", 3)) !== 3)) {
    pills.push(stepperPill({
      value: Number(value("shift_audio", 3)), min: 0.01, max: 100, step: 0.5, width: "48px",
      title: t("The audio flow shift. 3 is the checkpoints' own schedule. A wrong one distorts the soundtrack before it touches the picture."),
      format: (n) => t("audio {n}", { n: +n.toFixed(2) }),
      onChange: (next) => set("shift_audio", next),
    }));
  }

  // The accelerators. Off is the default and reads as off — an unlit pill —
  // because they are other people's nodes and a render with one on is not a
  // native render, which is worth being able to see at a glance. The turbo
  // switch leads them: it is the one that changes the most about the run.
  pills.push(...turbo);

  if (widgets.block_cache) {
    const options = widgets.block_cache.options?.values || [];
    const current = String(value("block_cache", "off"));
    pills.push(el("button", {
      class: `mmc-pill${current === "off" ? "" : " accel-on"}`,
      title: BLOCK_CACHE_TITLE[current] ? t(BLOCK_CACHE_TITLE[current]) : t("FirstBlockCache"),
      onclick: (event) => openChoicePopover(event.currentTarget, {
        title: t("Block cache"),
        options: typeof options === "function" ? options(widgets.block_cache) : options,
        value: current,
        onPick: (picked) => set("block_cache", picked),
      }),
    }, [el("span", { text: current === "off" ? t("cache off") : t("cache {preset}", { preset: current }) })]));
  }

  if (widgets.spectrum) {
    const on = Boolean(value("spectrum", false));
    pills.push(el("button", {
      class: `mmc-pill${on ? " accel-on" : ""}`,
      title: on
        ? t("Spectrum on — forecasting features across steps.")
        : t("Spectrum off. Needs ComfyUI-Spectrum-MiniMax-H3 when switched on."),
      onclick: () => set("spectrum", !on),
    }, [el("span", { text: on ? t("spectrum") : t("spectrum off") })]));

    // Only worth a control when it is doing something; the blend is ignored
    // outright while Spectrum is off.
    if (on && widgets.spectrum_blend) {
      pills.push(stepperPill({
        value: Number(value("spectrum_blend", 0.5)), min: 0, max: 1, step: 0.05, width: "52px",
        title: t("Spectrum's video spectral share — higher is faster and further from a native render"),
        format: (n) => t("blend {n}", { n: n.toFixed(2) }),
        onChange: (next) => set("spectrum_blend", next),
      }));
    }
  }

  // Last of the accelerators, and the only one that does not change which steps
  // run — it changes what one attention call costs, so it sits with them but
  // rules nothing else out.
  if (widgets.sage) {
    const on = Boolean(value("sage", false));
    pills.push(el("button", {
      class: `mmc-pill${on ? " accel-on" : ""}`,
      title: on
        ? t("Sage attention on — H3's attention runs quantized. Faster, and lower peak VRAM.")
        : t("Sage attention off. Needs ComfyUI-KJNodes and sageattention on an NVIDIA card when switched on."),
      onclick: () => set("sage", !on),
    }, [el("span", { text: on ? t("sage") : t("sage off") })]));
  }

  return el("div", { class: "mmc-pills" }, [...pills, ...trailing]);
}
