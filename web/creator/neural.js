// The refiner's saved setups: six numbers somebody found by eye, kept.
//
// The DLSS block rides on a piece, a timeline and a pre-stage (`state.js`), so
// every one of them starts at the defaults and every one of them is tuned
// separately. That is right for the *piece* — how hard to refine this shot is a
// question about this shot — and wrong for the person: the answer to "what do
// these dials want to be for faces" is found once, at some cost, on one
// picture, and then wanted on everything.
//
// So a profile is per machine and not per workflow, and it goes where this
// pack's other per-machine answers go — the settings file, through the same
// cache the sampler row reads its pills out of. Nothing queued reads any of
// this: a `.json` handed to somebody else still renders what its blocks say,
// and their own shelf of profiles is theirs.
//
// The starting block is the same store's other half. A profile is applied by
// hand; the starting block is what a piece's refiner *begins* at the first time
// it is switched on, so a machine that has settled on an answer stops re-typing
// it. Stored as numbers rather than as a name, so deleting the profile it came
// from leaves the answer standing.

import { uiSetting, patchSettings } from "./api.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";
import { NEURAL_DEFAULTS, NEURAL_PRECISIONS, NEURAL_PROFILES, NEURAL_RANGES,
         neuralDefaultsFor, parseNeural } from "./state.js";

/** Mirrors `settings.MAX_PROFILE_NAME` / `MAX_NEURAL_PROFILES`. */
export const MAX_NAME = 40;
export const MAX_PROFILES = 24;

/** The fields a profile is: everything but `on`, which is the piece's own
 *  answer and never a saved one. A profile that could arrive switched off would
 *  be a setup that turns the refiner off when applied, which is not a setup. */
export const PROFILE_KEYS = ["profile", ...Object.keys(NEURAL_RANGES), "precision"];

/** Just the saved fields of a block, in one order, so two of them compare. */
export function profileOf(block) {
  const kept = {};
  for (const key of PROFILE_KEYS) kept[key] = (block ?? NEURAL_DEFAULTS)[key];
  return kept;
}

/** Whether two blocks say the same thing about the refiner. Numbers through
 *  `Number`, because a block that has been through the settings file holds
 *  floats and one straight off a stepper may hold an integer. */
export function sameProfile(one, other) {
  return PROFILE_KEYS.every((key) => (
    typeof NEURAL_DEFAULTS[key] === "number"
      ? Number(one?.[key]) === Number(other?.[key])
      : one?.[key] === other?.[key]));
}

/** What this machine has saved: `[{name, block}]`, each block clamped onto this
 *  build's ranges on the way out. */
export function savedProfiles() {
  const raw = uiSetting("neural_profiles", []);
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((entry) => entry && typeof entry.name === "string")
    .map((entry) => ({ name: entry.name, block: profileOf(parseNeural(entry.block)) }));
}

/** Save these dials under this name, replacing a profile of the same name.
 *  Optimistic, like every other write through `patchSettings`: the shelf is
 *  redrawn from the cache the call updates, and the server's reply corrects it. */
export function saveProfile(name, block) {
  const clean = String(name ?? "").trim().slice(0, MAX_NAME);
  if (!clean) return Promise.resolve();
  const kept = profileOf(block);
  const rest = savedProfiles().filter((entry) => entry.name !== clean);
  const next = [...rest, { name: clean, block: kept }].slice(-MAX_PROFILES);
  return patchSettings({ neural_profiles: next });
}

export function forgetProfile(name) {
  return patchSettings({
    neural_profiles: savedProfiles().filter((entry) => entry.name !== name),
  });
}

/** The dials a piece's refiner starts at the first time it is switched on. */
export function startingBlock() {
  const raw = uiSetting("neural_start", null);
  return raw ? profileOf(parseNeural(raw)) : profileOf(NEURAL_DEFAULTS);
}

/** Whether this machine has said anything about that — which is what decides
 *  whether the popover offers to forget it. */
export function hasStartingBlock() {
  return Boolean(uiSetting("neural_start", null));
}

/** Make these dials the ones new work starts from, or `null` to go back to the
 *  pack's own defaults. */
export function setStartingBlock(block) {
  return patchSettings({ neural_start: block ? profileOf(block) : null });
}

/** Copy the saved fields of `block` onto `target` in place, leaving `on` alone.
 *  In place because the block is the piece's, held by whoever drew the popover,
 *  and replacing the object would leave that holder pointing at the old one. */
export function applyProfile(target, block) {
  for (const key of PROFILE_KEYS) target[key] = block[key];
  return target;
}

/** Move `block` to preset `next`, carrying the preset's opening strengths with
 *  it — but only over dials still sitting where the outgoing preset put them.
 *  A dial someone has moved is an answer, and switching style is not a reason
 *  to throw it away; a dial nobody has touched is just the old preset showing
 *  through, and leaving it there would make the presets differ in name only. */
export function adoptProfileDefaults(block, next) {
  const was = neuralDefaultsFor(block.profile);
  const now = neuralDefaultsFor(next);
  for (const key of ["detail", "colour", "intensity"]) {
    if (Number(block[key]) === was[key]) block[key] = now[key];
  }
  block.profile = next;
  return block;
}

// ---- the dials ---------------------------------------------------------------
//
// One rail, drawn wherever the refiner is set: the pill's popover, and the
// loupe's compare rail. It used to be drawn only in the popover, as a column of
// steppers — `detail` runs 0 to 8 in steps of a quarter, which is thirty-two
// presses end to end, and the picture it changes was not on the screen. The
// bench, meanwhile, drew the same six values as sliders with their stops under
// them, because the bench has the picture.
//
// So: sliders everywhere, and the picture wherever it can be had. A slider says
// where 1 sits in the range, which is the one thing about these numbers that
// has to be legible — every one of them is "how much of the model's answer",
// and 1 is all of it. Double-clicking a dial puts it back there.

/** What each dial is called on the rail, and what it does. The keys are the
 *  block's; the words are the ones `neural.py` puts on the same dials in the
 *  bench's catalogue, so the two surfaces do not name one thing twice. */
export const DIAL_NOTES = {
  detail: "How much of the model's high-frequency change is kept. 1 is its own "
        + "answer; 0 keeps only its colour.",
  colour: "How much of the model's low-frequency change — tone and colour — is "
        + "kept. 0 keeps only its detail.",
  intensity: "The refined picture over the source. 1 is all of it.",
  scale: "Run the network on the picture resampled by this factor and bring the "
       + "result back. Finer material at 2, and about four times the memory.",
};

export const PROFILE_NOTES = {
  standard: "What the driver runs.",
  natural: "The model's style index one step up.",
  cinematic: "The model's style index two steps up.",
  neutral: "Local tone and structure off.",
};

export const PRECISION_NOTES = {
  reference: "float32 with the driver's own rounding — matches it to 0.005.",
  fast: "float16 on the GPU — half the memory.",
};

/** The dials the two surfaces show, in order. `scale` is a still's: a clip runs
 *  at the frame's own size because the temporal history has to. */
export const DIAL_ORDER = ["detail", "colour", "intensity"];

const shown = (key, value) => (key === "scale" ? `×${value}` : Number(value).toFixed(2));

/**
 * One dial: a label, its number, a track with its stops under it.
 *
 * @param {object} spec
 * @param {string} spec.label      the word on the rail
 * @param {number} spec.value
 * @param {{min:number, max:number, step:number, default:number}} spec.range
 * @param {(next:number) => void} spec.onChange  while it is being dragged
 * @param {string} [spec.note]     the tooltip, already in English
 * @param {string} [spec.key]      which dial, for how the number reads
 */
export function neuralDial({ label, value, range, onChange, note = "", key = "" }) {
  const readout = el("span", { class: "mmc-nr-value", text: shown(key, value) });
  const slider = el("input", {
    type: "range", class: "mmc-nr-range",
    min: String(range.min), max: String(range.max), step: String(range.step),
    value: String(value),
    "aria-label": label,
    oninput: (event) => {
      readout.textContent = shown(key, event.target.value);
      onChange(Number(event.target.value));
    },
    // Back to what it was written to be. A dial whose whole meaning is "1 is
    // the model's own answer" needs a way home that is not thirty-two presses
    // or a memory of which number it started at.
    ondblclick: (event) => {
      event.preventDefault();
      event.target.value = String(range.default);
      readout.textContent = shown(key, range.default);
      onChange(range.default);
    },
  });
  return el("div", { class: "mmc-nr-dial", title: note ? t(note) : null }, [
    el("div", { class: "mmc-nr-diallabel" }, [el("span", { text: label }), readout]),
    slider,
  ]);
}

/**
 * A row of words, one of which is on. The pack's segmented control, in the
 * refiner's own class so neither bench nor popover owns it.
 *
 * Two or three short words sit on the label's own line, where they read as the
 * answer to it. Four do not: `standard natural cinematic neutral` is wider than
 * any rail this is drawn on, and pushed to the right of a label it wrapped with
 * one word stranded under the other three and the label floating beside the
 * gap. So a longer set takes the line under its label and fills it from the
 * left — a group of choices rather than a ragged right edge.
 */
export function neuralChoice({ label, value, options, onChange, notes = {} }) {
  const stacked = options.length > 3;
  const chips = el("div", { class: "mmc-nr-opts" }, options.map((option) => el("button", {
    class: `mmc-nr-opt${value === option ? " on" : ""}`,
    "aria-pressed": value === option,
    title: notes[option] ? t(notes[option]) : null,
    text: t(option),
    onclick: () => onChange(option),
  })));
  return el("div", { class: `mmc-nr-row${stacked ? " stacked" : ""}` }, [
    el("span", { class: "mmc-nr-label", text: label }),
    chips,
  ]);
}

/**
 * On or off, as a switch.
 *
 * It was two radio rows with a sentence under each — a quarter of the popover
 * spent saying that a boolean is a boolean, above the dials that are the only
 * reason anybody opened it. A switch is the control for this, and the sentence
 * that was worth keeping (what "on" does to a render) belongs under the title
 * once rather than under each of two options.
 */
export function neuralSwitch({ on, onChange, label }) {
  return el("button", {
    class: `mmc-nr-switch${on ? " on" : ""}`,
    role: "switch", "aria-checked": on, "aria-label": label,
    onclick: () => onChange(!on),
  }, [el("span", { class: "mmc-nr-knob" })]);
}

/**
 * The whole rail for one block: profile, the three strengths, the still's
 * scale, precision.
 *
 * `onChange` is called after every movement with nothing: the block is mutated
 * in place, and what the caller does about it — commit the piece, mark a tile
 * stale — is the caller's. `redraw` is for the changes that alter which rows
 * exist, so a caller that rebuilds on every change can pass the same function
 * to both.
 *
 * @param {object} spec
 * @param {object} spec.block   the neural block, mutated in place
 * @param {() => void} spec.onChange
 * @param {() => void} [spec.redraw]  after a choice, which is drawn as pressed
 * @param {boolean} [spec.still]  offer the processing scale
 * @param {object} spec.ranges  `NEURAL_RANGES`, passed rather than imported so
 *   this module holds no opinion about the bounds — `state.js` mirrors them.
 */
export function neuralRail({ block, onChange, redraw = null, still = false, ranges }) {
  const rows = [
    neuralChoice({
      label: t("profile"), value: block.profile, options: NEURAL_PROFILES,
      notes: PROFILE_NOTES,
      onChange: (next) => {
        adoptProfileDefaults(block, next);
        onChange();
        (redraw ?? onChange)();
      },
    }),
  ];
  const labels = { detail: t("detail"), colour: t("colour"), intensity: t("blend"),
                   scale: t("scale") };
  for (const key of [...DIAL_ORDER, ...(still ? ["scale"] : [])]) {
    rows.push(neuralDial({
      key, label: labels[key], value: Number(block[key]), range: ranges[key],
      note: DIAL_NOTES[key],
      onChange: (next) => { block[key] = next; onChange(); },
    }));
  }
  rows.push(neuralChoice({
    label: t("precision"), value: block.precision, options: NEURAL_PRECISIONS,
    notes: PRECISION_NOTES,
    onChange: (next) => { block.precision = next; onChange(); (redraw ?? onChange)(); },
  }));
  return rows;
}
