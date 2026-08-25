// The sampler row, drawn the same way on both nodes.
//
// Both the Creator and the Timeline own their sampler and declare the same
// widgets under the same names, so there is one row and both mount it. It lives
// outside the panel on either node because the panel says what the piece *is*
// and this says how it is run.
//
// **The values are in the blob, not on the widgets.** They were widgets until a
// second model family made that untenable — a node's widget list is static per
// class, and LTX-AV wants a different row rather than a longer one — so the row
// moved into `creator_data` where the rest of the piece already lives. The
// thirteen widgets stay declared and stay hidden, as the fallback that carries
// every workflow saved before the move; see `sampling.py` and `blobIO` below.
//
// The seed is the exception and is still a widget, because
// `control_after_generate` is the frontend's own linked control and there is
// nothing for a JSON field to be.

import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import { openChoicePopover, stepperPill, pillSet, pillClass, accelClass } from "./pills.js";
import { DEFAULT_VIDEO_FAMILY, widgetsOf as S_widgetsOf } from "./state.js";
import { uiSetting } from "./api.js";
import { lastSeed } from "./seedmemory.js";

export const SEED_CONTROL = ["fixed", "increment", "decrement", "randomize"];

// Every widget this row draws. The entry point hides exactly these, so a name
// added here without being added there would render twice — once as a pill and
// once as the stock widget underneath.
export const SAMPLING_WIDGETS = [
  "seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler",
  "shift_video", "shift_audio",
  "block_cache", "spectrum", "spectrum_blend", "sage", "attention", "chunk_ffn",
  "fp16_accumulation",
];

// `sage` is in that list and is never drawn: it is the switch `attention`
// replaced, kept so a workflow saved with it on still runs sage, and hidden so
// nobody sets it from two places. See `adoptSage`.

const ATTENTION_TITLE = {
  default: "The checkpoint's own attention.",
  sage: "Sage attention — H3's attention runs quantized. Faster, and lower peak VRAM. Needs ComfyUI-KJNodes and sageattention on an NVIDIA card.",
  kitchen: "Comfy Kitchen attention — core's own int8 kernel, nothing to install. Needs a ComfyUI whose build ships it.",
};

// Noun first, the way the cache pill reads ("cache off", "cache fast"): the
// pill has to say what it is a choice *about*, and a pill reading "kitchen"
// on its own says nothing at all to somebody who has not read the release
// notes. The backends keep their own names — they are what the packs and core
// call them, and searching for either finds the right page.
const ATTENTION_LABEL = {
  default: "attention default",
  sage: "attention sage",
  kitchen: "attention kitchen",
};

const BLOCK_CACHE_TITLE = {
  off: "Step caching is off.",
  safe: "FirstBlockCache, safest preset — fewest skipped steps.",
  fast: "FirstBlockCache, the pack's recommended preset.",
  aggressive: "FirstBlockCache, most skipping — fastest, furthest from a native render.",
  easy: "EasyCache — core's own step reuse, nothing to install. Cannot be combined with Spectrum.",
  tea: "TeaCache — skips transformer forwards on timestep similarity. Needs ComfyUI-MiniMaxH3-TeaCache.",
};

/**
 * Carry a workflow saved with the old `sage` switch onto the `attention` list.
 *
 * The switch became one option of a list, and the two cannot both be authority
 * or a node would say sage in one place and default in the other. So the switch
 * is read exactly once — the first time a node carrying it is drawn — moved onto
 * the list and cleared, and after that the list is the only thing that decides.
 * A node that never had it on passes straight through and nothing is written.
 *
 * Only while the list is still at its default: a workflow saved *after* the
 * rename has already answered this, including by answering "default".
 */
function adoptSage(widgets, set) {
  if (!widgets.sage?.value) return;
  if (String(widgets.attention?.value ?? "default") === "default") set("attention", "sage");
  set("sage", false);
}

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

/** The fields that stay on the node's widgets whatever else moves into the blob.
 *
 *  `control_after_generate` is not a declared input at all — the frontend
 *  attaches it to the seed and names it itself — so there is nothing for a JSON
 *  field to be. And the seed rides with it: they are one control, the number and
 *  what happens to it after a queue, and splitting them across two stores would
 *  mean a saved piece whose seed and its after-generate disagreed about which
 *  run they described.
 *
 *  `sage` is here for the opposite reason: it is the retired switch, and the one
 *  thing `adoptSage` does with it is *clear* it. A clear that landed in the blob
 *  would leave the widget still on, so the switch would be adopted again on
 *  every mount and could never be put down. It predates the list, no pill writes
 *  one, and `sampling.py` reads it off the widgets for the same reason. */
export const WIDGET_ONLY = ["seed", "control_after_generate", "sage"];

/**
 * The row, over the blob — with the seed still over the widgets.
 *
 * Everything that draws this row (`samplingBar`, the turbo switch, the preset
 * capture and apply) already talks to a `{value, set}` pair and has never known
 * where the values were kept. That is what makes moving them a change to one
 * function rather than to the row: the pair still answers to the same names, and
 * `sampling.py` reads the same block on the other side.
 *
 * Why they moved is in `sampling.py`'s docstring — briefly, a node's widget list
 * is static per class and a second model family does not want this one.
 *
 * @param {object} widgets   name -> real ComfyUI widget, for the seed
 * @param {() => object} read   the blob's `sampling` block, possibly undefined
 * @param {(block: object) => void} write   store an updated block
 * @param {() => void} [onChange]  the node needs redrawing
 */
export function blobIO(widgets, read, write, onChange) {
  const widgets_ = widgetIO(widgets, onChange);
  return {
    value: (name, fallback) => {
      if (WIDGET_ONLY.includes(name)) return widgets_.value(name, fallback);
      const stored = read()?.[name];
      return stored === undefined || stored === null ? fallback : stored;
    },
    set: (name, value) => {
      if (WIDGET_ONLY.includes(name)) { widgets_.set(name, value); return; }
      write({ ...(read() || {}), [name]: value });
      onChange?.();
    },
  };
}

/**
 * Move a pre-blob sampler row into the blob, once. -> new blob text, or null.
 *
 * The migration, and the only place either half of the row is copied. A
 * workflow saved before the move has no `sampling` block and its widgets hold
 * the real values, so the first time a body mounts one it writes them across;
 * from then on the blob is what is read, saved and queued.
 *
 * **Called once the graph has finished configuring, never at construction.** A
 * saved workflow assigns its widget values *after* `nodeCreated`, so a body that
 * migrated early would copy the schema's defaults over the user's row — which is
 * the one way this could do real damage.
 *
 * Read off the raw text rather than off parsed state, because `parseSampling`
 * cannot tell an absent block from an empty one and that difference is the whole
 * question: `{}` is what a body writes for a piece nobody has tuned, and reading
 * it as "unmigrated" would put the widgets back on top of a row somebody had
 * deliberately cleared.
 *
 * Nothing is lost by declining: `sampling.py` falls back per field, so a blob
 * this never runs on queues off its widgets exactly as it always did.
 *
 * @param {string} raw        the blob as stored
 * @param {object} widgets    name -> real ComfyUI widget
 * @param {(raw: string) => object} parse
 * @param {(state: object) => string} serialize
 */
export function adopted(raw, widgets, parse, serialize) {
  let stored;
  try {
    stored = JSON.parse(raw)?.sampling;
  } catch {
    return null;   // an unparseable blob is the state module's problem, not this one
  }
  if (stored && typeof stored === "object") return null;

  const block = {};
  for (const name of SAMPLING_WIDGETS) {
    if (WIDGET_ONLY.includes(name)) continue;
    const widget = widgets?.[name];
    if (widget && widget.value !== undefined) block[name] = widget.value;
  }
  if (!Object.keys(block).length) return null;

  const state = parse(raw);
  state.sampling = block;
  return serialize(state);
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
/**
 * One card's own seed, on the card's own editor.
 *
 * Not the sampler row: steps, cfg, the sampler and the accelerators describe
 * how the piece is run and there is one answer to that for the whole node. The
 * seed is the one number a card has business overriding, and the reason is
 * shooting a piece a pass at a time — retaking segment 2 under a single number
 * for the whole piece means rolling the number that made the take already kept
 * on segment 1, so the handle stops describing the piece. A take's seed is a
 * fact about the take.
 *
 * Unlit while the card inherits, which is every card until somebody rolls one
 * here — the row's rule everywhere else, and the honest reading: an inherited
 * seed is doing nothing to this card that it is not doing to all of them.
 *
 * @param {number|null} options.own    this card's seed, or null to inherit
 * @param {number} options.piece       the number on the node, which is what an
 *                                     inheriting card runs on
 * @param {(seed: number|null) => void} options.onChange  null clears the override
 * @param {number|null} [options.taken] the seed the card's take was made on,
 *   named in the tooltip because "which seed made this" is the whole reason
 *   the number is on screen at all
 */
export function segmentSeedPill({ own, piece, onChange, taken = null }) {
  const inherited = own === null || own === undefined;
  const shown = String(inherited ? piece : own);
  return el("div", { class: `mmc-pill mmc-pill-group${inherited ? "" : " on"}` }, [
    el("button", {
      class: "mmc-step mmc-seed-dice",
      title: t("Roll a seed for this card alone. The rest of the piece keeps the "
             + "number on the node."),
      onclick: () => onChange(Math.floor(Math.random() * 0xffffffff)),
    }, [icon("dice", 15)]),
    el("button", {
      class: "mmc-step mmc-seed-last",
      disabled: inherited,
      title: inherited
        ? t("This card runs on the piece's seed, which is what every card does "
          + "until you roll one here.")
        : t("Back to the piece's seed, {seed}.", { seed: piece }),
      onclick: () => { if (!inherited) onChange(null); },
    }, [icon("rewind", 15)]),
    el("input", {
      class: "mmc-seed-input",
      type: "text",
      value: shown,
      style: { width: `${Math.min(21, Math.max(5, shown.length + 1))}ch` },
      title: [
        inherited
          ? t("The piece's seed. Type a number to give this card one of its own.")
          : t("This card's own seed. The rest of the piece runs on {seed}.", { seed: piece }),
        taken === null ? null : t("Its take was made on {seed}.", { seed: taken }),
      ].filter(Boolean).join(" "),
      onchange: (event) => {
        const text = String(event.target.value).replace(/[^\d]/g, "");
        onChange(text === "" ? null : Number(text) || 0);
      },
      onpointerdown: (event) => event.stopPropagation(),
    }),
    // Which of the two numbers is in force. A readout, not a control — the
    // rewind beside it is how you go back — so it is a span and wears the
    // "fixed" seed mode's own quiet.
    el("span", {
      class: `mmc-seed-mode${inherited ? "" : " on"}`,
      text: inherited ? t("piece") : t("card"),
    }),
  ]);
}


/**
 * The seed, and what happens to it after a queue.
 *
 * Shared by every family's row, because the seed is not a family's control: it
 * is the node's, it is the one field on this row that is still a real widget,
 * and `control_after_generate` is the frontend's own linked control with
 * nothing for a JSON field to be. Lifted out of `samplingBar` when a second
 * family arrived wanting a different row and the same seed.
 *
 * -> an array, so a caller can spread it, and an empty one where there is no
 * seed widget to draw (a timeline segment's own editor).
 */
function seedPills({ widgets, value, set, perSegment }) {
  if (!widgets.seed) return [];
  const pills = [];
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
        ? t("The piece's seed: every card runs on this number unless it was given "
          + "one of its own, which is set on the card.")
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
  return pills;
}


/**
 * One family's sampler row, drawn from what its manifest declares.
 *
 * The widget vocabulary is `families/manifest.py`'s — `{id, type, label, group,
 * default, min, max, step, options, help}`, with `type` one of slider, stepper,
 * toggle, combo — and this is the renderer for it. A family the frontend has
 * never heard of gets a working row out of its declarations alone, which is the
 * whole claim the manifest makes: LTX-AV wanted two CFG scales, a stretched
 * schedule and a terminal, and none of that is a superset of H3's row.
 *
 * Only the `sampler` group. `accel`, `guidance` and `weights` are drawn
 * elsewhere — `guidance` by `guidanceRow` just below, right after this — and a
 * family that declares none of them simply has none on the row. LTX declares no
 * accelerators, because every accelerator this pack knows about is an H3 patch.
 *
 * A combo with no `options` reads them off the node's own widget of that name,
 * the same rule the H3 row follows: core's sampler list is the node schema's to
 * declare and a copy of it in a manifest would go stale the first time core
 * added one. LTX's `sampler_name` is exactly that case.
 *
 * Values go through `value`/`set`, which for these families is the blob — none
 * of these ids is one of the node's thirteen frozen widget slots, and there is
 * nowhere else they could live.
 */
function declaredRow(family, widgets, value, set) {
  return S_widgetsOf(family)
    .filter((w) => w.group === "sampler")
    .map((w) => declaredPill(w, widgets, value, set))
    .filter(Boolean);
}


/**
 * The taste-guidance pills, as one set — a family's `guidance` group.
 *
 * Apart from the sampler row and apart from the accelerators, because it is
 * neither. An accelerator buys time and spends quality; these spend time and
 * buy quality, and each of them costs an extra forward pass per step. So they
 * are lit exactly when they are costing something — the accelerator rule, read
 * off the manifest's `off` value rather than guessed from a range, because
 * "does nothing" is 0 for one of LTX's two and 1.0 for the other.
 *
 * A control that only modifies another (`requires`) is drawn only while that
 * one is on, which is the rule Spectrum's blend already follows one row up.
 * One pill for the group, divided: they are one question — how much extra
 * sampling is this piece willing to pay for.
 */
function guidanceRow(family, widgets, value, set) {
  const declared = S_widgetsOf(family).filter((w) => w.group === "guidance");
  if (!declared.length) return [];
  const active = (w) => w.off !== undefined && value(w.id, w.default) !== w.off;
  const pill = pillSet(declared.map((w) => {
    if (w.requires) {
      const on = declared.find((other) => other.id === w.requires);
      if (!on || !active(on)) return null;
    }
    return (seg) => declaredPill(w, widgets, value, set, seg, active(w));
  }));
  return pill ? [pill] : [];
}


function declaredPill(w, widgets, value, set, seg = false, lit = false) {
  const help = w.help ? t(w.help) : t(w.label);
  const current = value(w.id, w.default);

  if (w.type === "text") {
    // A typed field in a pill. The one control whose value is prose — LTX's
    // STG takes a list of block numbers — so there is nothing to step and
    // nothing to choose from, and core parses whatever is typed with a digit
    // grep rather than a grammar.
    const text = String(current ?? "");
    return el("div", { class: `${pillClass(seg, lit ? " accel-on" : "")} mmc-pill-group`, title: help }, [
      el("span", { text: `${t(w.label)} ` }),
      el("input", {
        class: "mmc-pill-text",
        type: "text",
        value: text,
        style: { width: `${Math.min(18, Math.max(3, text.length + 1))}ch` },
        onchange: (event) => set(w.id, String(event.target.value)),
        onpointerdown: (event) => event.stopPropagation(),
      }),
    ]);
  }

  if (w.type === "toggle") {
    const on = Boolean(current);
    // Lit when on, quiet when off — the rule every switch on this row follows,
    // so what is doing something to your render is what you can see.
    return el("button", {
      class: accelClass(seg, on),
      title: help,
      onclick: () => set(w.id, !on),
    }, [el("span", { text: on ? t(w.label) : t("{label} off", { label: t(w.label) }) })]);
  }

  if (w.type === "combo") {
    // The node's own widget of the same name, where the manifest declared no
    // list — core's sampler names are the schema's and a manifest carrying a
    // copy would go stale the first time core added one. Nothing to offer at
    // all means no pill, rather than a popover that opens empty.
    const declared = w.options ?? [];
    const fromWidget = widgets[w.id]?.options?.values;
    const options = declared.length
      ? declared
      : (typeof fromWidget === "function" ? fromWidget(widgets[w.id]) : fromWidget) || [];
    if (!options.length) return null;
    return el("button", {
      class: accelClass(seg, lit),
      title: help,
      onclick: (event) => openChoicePopover(event.currentTarget, {
        title: t(w.label),
        options,
        value: String(current),
        onPick: (picked) => set(w.id, picked),
      }),
    }, [el("span", { text: String(current) })]);
  }

  // slider and stepper are one control here. The manifest's distinction is
  // about how much of a range a value sweeps, and the pill this row is built
  // out of is a stepper with a typed field in it — which serves both, and is
  // the control every number on H3's row already uses.
  const step = w.step ?? 1;
  const decimals = String(step).includes(".") ? String(step).split(".")[1].length : 0;
  return stepperPill({
    seg,
    className: lit ? "accel-on" : "",
    value: Number(current),
    min: w.min ?? 0,
    max: w.max ?? 100,
    step,
    width: decimals ? "58px" : "46px",
    title: help,
    format: (n) => `${t(w.label)} ${decimals ? n.toFixed(decimals) : n}`,
    onChange: (next) => set(w.id, next),
  });
}


export function samplingBar({ widgets, value, set, perSegment = false,
                              turbo = [], trailing = [], family = DEFAULT_VIDEO_FAMILY }) {
  const pills = [];

  // A family the frontend has never seen draws its row from its own manifest —
  // see `declaredRow`. H3's row stays handwritten below: it predates the
  // manifest vocabulary and every one of its controls carries copy about the
  // checkpoints it belongs to ("the distilled H3 checkpoints want 1.0", "a
  // wrong audio shift distorts the soundtrack before it touches the picture"),
  // which is worth more than the uniformity of deriving it. The seed is shared,
  // because the seed is the node's and not the family's.
  if (family !== DEFAULT_VIDEO_FAMILY) {
    return el("div", { class: "mmc-pills" }, [
      ...seedPills({ widgets, value, set, perSegment }),
      ...declaredRow(family, widgets, value, set),
      ...guidanceRow(family, widgets, value, set),
      ...turbo, ...trailing,
    ]);
  }

  pills.push(...seedPills({ widgets, value, set, perSegment }));

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

  // One pill, divided: a sampler and its scheduler are two halves of one
  // schedule, and as two loose pills they read as two unrelated lists of names.
  const schedule = pillSet([["sampler_name", "Sampler"], ["scheduler", "Scheduler"]]
    .filter(([name]) => widgets[name])
    .map(([name, label]) => (seg) => {
      const widget = widgets[name];
      // The *options* come off the widget — that list is the node's schema and
      // is the one thing the blob has no business copying. The **value** does
      // not: it moved into the blob with the rest of the row, and reading
      // `widget.value` here was the one place in this file that still reached
      // around `value()`. It drew the stale widget while `set` wrote the blob,
      // so picking a sampler on any face changed the render and left the pill
      // showing the old name — which reads as a control that does nothing.
      const options = widget.options?.values || [];
      const current = String(value(name, widget.value));
      return el("button", {
        class: pillClass(seg),
        title: t(label),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t(label),
          options: typeof options === "function" ? options(widget) : options,
          value: current,
          onPick: (picked) => set(name, picked),
        }),
      }, [el("span", { text: current })]);
    }));
  if (schedule) pills.push(schedule);

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
  // Whether this machine wants the controls most rows never touch. It hides,
  // it does not disable: a control that is *on* keeps its pill whatever this
  // says, so nothing can be switched on and out of sight at the same time.
  const advanced = uiSetting("advanced", false) === true;
  // The two clocks share a pill — and only sometimes both: either can be on
  // screen alone, off its schedule while the other is at its default, which is
  // why they are drawn rather than listed.
  const shifts = pillSet([
    widgets.shift_video && (showShifts || Number(value("shift_video", 12)) !== 12)
      ? (seg) => stepperPill({
          seg,
          value: Number(value("shift_video", 12)), min: 0.01, max: 100, step: 0.5, width: "48px",
          title: t("The video flow shift. 12 is the checkpoints' own schedule; a turbo LoRA's card may name another."),
          format: (n) => t("shift {n}", { n: +n.toFixed(2) }),
          onChange: (next) => set("shift_video", next),
        })
      : null,
    widgets.shift_audio && (showShifts || Number(value("shift_audio", 3)) !== 3)
      ? (seg) => stepperPill({
          seg,
          value: Number(value("shift_audio", 3)), min: 0.01, max: 100, step: 0.5, width: "48px",
          title: t("The audio flow shift. 3 is the checkpoints' own schedule. A wrong one distorts the soundtrack before it touches the picture."),
          format: (n) => t("audio {n}", { n: +n.toFixed(2) }),
          onChange: (next) => set("shift_audio", next),
        })
      : null,
  ]);
  if (shifts) pills.push(shifts);

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
    // The switch and its blend in one pill. The blend is still only drawn while
    // Spectrum is on — it is ignored outright otherwise — but switching Spectrum
    // on now *extends the control you just pressed* rather than making a second
    // pill appear beside it, which is the same event said much more plainly.
    pills.push(pillSet([
      (seg) => el("button", {
        class: accelClass(seg, on),
        title: on
          ? t("Spectrum on — forecasting features across steps.")
          : t("Spectrum off. Needs ComfyUI-Spectrum-MiniMax-H3 when switched on."),
        onclick: () => set("spectrum", !on),
      }, [el("span", { text: on ? t("spectrum") : t("spectrum off") })]),
      on && widgets.spectrum_blend
        ? (seg) => stepperPill({
            seg,
            value: Number(value("spectrum_blend", 0.5)), min: 0, max: 1, step: 0.05, width: "52px",
            title: t("Spectrum's video spectral share — higher is faster and further from a native render"),
            format: (n) => t("blend {n}", { n: n.toFixed(2) }),
            onChange: (next) => set("spectrum_blend", next),
          })
        : null,
    ]));
  }

  // Last of the accelerators, and the three that do not change which steps run —
  // they change what an attention call costs, what the MLP peaks at and how a
  // matmul accumulates, so they sit with them but rule nothing else out.
  if (widgets.attention) adoptSage(widgets, set);
  const attention = widgets.attention ? String(value("attention", "default")) : null;
  const lowVram = Boolean(value("chunk_ffn", false));
  const fastMath = Boolean(value("fp16_accumulation", false));

  // The last two segments are named for what you get rather than for how they
  // are built. "Chunk FFN" and "fp16 accumulation" are what the packs call them
  // and are in the tooltips, where somebody looking for them will find them; on
  // the row they are the only controls that would have asked you to know what a
  // feed-forward is before you could tell whether you wanted one.
  //
  // One pill for the three: none of them changes which steps run, and all three
  // are statements about the machine rather than about the piece. Each is drawn
  // only when it is on or when the advanced controls are asked for, so the pill
  // is as long as this install has reason for it to be.
  const machine = pillSet([
    widgets.attention
      ? (seg) => {
          const options = widgets.attention.options?.values || [];
          return el("button", {
            class: accelClass(seg, attention !== "default"),
            title: t(ATTENTION_TITLE[attention] || ATTENTION_TITLE.default),
            onclick: (event) => openChoicePopover(event.currentTarget, {
              title: t("Attention"),
              options: typeof options === "function" ? options(widgets.attention) : options,
              value: attention,
              onPick: (picked) => set("attention", picked),
            }),
          }, [el("span", { text: t(ATTENTION_LABEL[attention] || ATTENTION_LABEL.default) })]);
        }
      : null,
    widgets.chunk_ffn && (advanced || lowVram)
      ? (seg) => el("button", {
          class: accelClass(seg, lowVram),
          title: lowVram
            ? t("Low VRAM on — H3's feed-forward runs in chunks, so the peak is lower. The frames are the same ones: chunking is a rearrangement, not a trade. Needs ComfyUI-KJNodes.")
            : t("Low VRAM — run H3's feed-forward in chunks (KJNodes' Chunk FFN). Lowers the peak a render has to fit in, and changes nothing about the frames. Needs ComfyUI-KJNodes."),
          onclick: () => set("chunk_ffn", !lowVram),
        }, [el("span", { text: lowVram ? t("low vram") : t("low vram off") })])
      : null,
    widgets.fp16_accumulation && (advanced || fastMath)
      ? (seg) => el("button", {
          class: accelClass(seg, fastMath),
          title: fastMath
            ? t("Fast math on — cuBLAS accumulates fp16 matmuls in fp16 while this model runs (KJNodes' fp16 accumulation). Only fp16 matmuls: a bf16 or quantized H3 has none, and nothing changes there.")
            : t("Fast math — let cuBLAS accumulate fp16 matmuls in fp16 while this model runs (KJNodes' fp16 accumulation). Faster where the card supports it, at some precision. Only reaches a genuinely fp16 model: the released H3 checkpoints run bf16, and their quantized layers go through comfy-kitchen's own kernels rather than cuBLAS, so on those this does nothing at all. Needs ComfyUI-KJNodes and torch 2.7 or newer."),
          onclick: () => set("fp16_accumulation", !fastMath),
        }, [el("span", { text: fastMath ? t("fast math") : t("fast math off") })])
      : null,
  ]);
  if (machine) pills.push(machine);

  return el("div", { class: "mmc-pills" }, [...pills, ...trailing]);
}
