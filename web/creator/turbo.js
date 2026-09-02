// The turbo switch: one pill that throws an H3 distillation LoRA onto the run.
//
// Thrown on, it does three things at once — adds the chosen LoRA to the
// ordinary stack, saves the sampler row and re-sets it to what the turbo LoRAs
// were tuned against (euler + beta; H3's joint audio warbles on res_multistep
// at these step counts), and drops the steps to the picked quality. Thrown off,
// it removes the entry and puts the row back exactly as it stood.
//
// The LoRA itself is a normal entry the whole way: the manager's card, the
// chip's ✕ and the strength slider all work on it, which is the point — the
// switch is a shortcut into the stack, not a second stack. `sync` is the other
// half of that bargain: when the entry is removed or disabled anywhere else,
// the switch notices on the next commit and gives the sampler row back.

import { el, icon } from "./dom.js";
import { openChoicePopover, openNotePopover, stepperPill } from "./pills.js";
import { listLoraNames, uiSetting, patchSettings } from "./api.js";
import * as S from "./state.js";
import { t } from "./i18n.js";

// The LoRA names, for the two pickers here. The manager's listing carries
// cards and sidecars; a choice popover only needs the names.
//
// Cached for the life of the page once a fetch *succeeds* — a failure leaves it
// unloaded so the next draw or press simply asks again. Caching the failure was
// the old behaviour, and a request racing the extension's routes at load time
// pinned every picker on this page to an empty list until reload.
//
// Names only, off their own route: the folder listing stats every file and
// reads a sidecar per row, which on a fresh start of a large folder is minutes
// during which a press opened nothing (issue #41) — and it is capped at the
// newest files, so a distillation older than the cap was never offered.
let names = null;
let inflight = null;

export function loadLoraNames(onReady) {
  if (names) { onReady?.(); return; }
  inflight ??= listLoraNames()
    .then((listed) => { names = listed; })
    .catch(() => {})
    .finally(() => { inflight = null; });
  if (onReady) inflight.then(onReady);
}

/** The manager's Rescan reaches this cache too: a button that says "look
 *  again" has to reach every copy of the list, not just the manager's own. */
export function forgetLoraNames() { names = null; }

export const loraNames = () => names ?? [];

/** Whether a filename says it is a distillation LoRA. Every released H3 family
 *  does — "turbo" in larryvrh's, lightx2v's and Kijai's names alike — so the
 *  picker leads with these and keeps the character LoRAs out of the way. */
const looksTurbo = (name) => /turbo|distill/i.test(name);

const SHOW_ALL = "— show all —";

/** The lora-less choice: some turbo checkpoints ship with the distillation
 *  merged into the weights, and those want the step drop with no LoRA at all. */
export const NO_LORA = "— no LoRA · merged checkpoint —";

/**
 * The turbo file list, filtered to names that say turbo, with the full folder
 * one press away. A wrongly-named distill is reachable, not hidden — and when
 * nothing matches the filter at all, the full list is what opens.
 */
function openTurboChoice(anchor, { value, onPick, includeNone = false, all = false, retried = false }) {
  // Not loaded yet — the first fetch is started lazily and can have failed
  // once. One retry per press: fetch, then open with whatever arrived. The
  // press is answered at once with a note, because on a cold start core is
  // still walking the model folders and a press that shows nothing for the
  // length of that walk reads as a pill that does not work. The note is
  // replaced by the list when it lands, and is left standing, reworded, when
  // it does not.
  if (names === null && !retried) {
    const closeNote = openNotePopover(anchor, t("Scanning models/loras…"));
    loadLoraNames(() => {
      closeNote();
      if (!anchor.isConnected) return;
      if (names === null) {
        openNotePopover(anchor, t("Could not list models/loras — press again to retry."));
        return;
      }
      openTurboChoice(anchor, { value, onPick, includeNone, all, retried: true });
    });
    return;
  }
  const matched = loraNames().filter(looksTurbo);
  const showAll = all || !matched.length;
  const listed = showAll ? loraNames() : matched;
  openChoicePopover(anchor, {
    title: showAll ? t("Turbo LoRA — all files") : t("Turbo LoRA"),
    options: [
      ...(includeNone ? [typeof includeNone === "string" ? t(includeNone) : t("— none —")] : []),
      ...listed,
      // Only when it would add something: a filter that matched everything has
      // nothing more to show.
      ...(showAll || matched.length === loraNames().length ? [] : [t(SHOW_ALL)]),
    ],
    value,
    onPick: (picked) => {
      if (picked === t(SHOW_ALL)) {
        openTurboChoice(anchor, { value, onPick, includeNone, all: true });
        return;
      }
      onPick(picked);
    },
  });
}

/** The entry the switch owns, if it is in the stack at all. */
const entryOf = (container) => (container.turbo?.lora ? S.findLora(container, container.turbo.lora) : null);

/** Engaged means present *and* enabled: the manager's quick-disable counts as
 *  switching off, because that is what it is for.
 *
 *  With no file chosen there is nothing to reconcile against — that is the
 *  merged-checkpoint mode, where the distillation is baked into the weights
 *  the user picked and the switch only owns the sampler row. */
const engaged = (container) => {
  if (!container.turbo?.lora) return true;
  const entry = entryOf(container);
  return !!entry && entry.enabled !== false && Math.round((Number(entry.strength) || 0) * 100) !== 0;
};

/** Widget IO, as the editor and the timeline body both provide it:
 *  `value(name, fallback)` and `set(name, value)` over the real ComfyUI widgets. */

function throwOn(container, { value, set }) {
  // The switch's numbers are the piece's family's — the step table, the row it
  // writes and the strengths its presets guess are all declarations of the
  // family that has a turbo switch at all.
  const family = S.pieceFamily(container);
  const turbo = container.turbo;
  // No file is the merged-checkpoint mode: the distillation is already in the
  // weights, so the switch touches nothing but the sampler row.
  if (turbo.lora) {
    const entry = entryOf(container);
    if (entry) {
      entry.enabled = true;
      if (Math.round((Number(entry.strength) || 0) * 100) === 0) {
        entry.strength = S.turboStrength(turbo.lora, family);
      }
    } else {
      const added = S.addLora(container, turbo.lora, []);
      if (added) added.strength = S.turboStrength(turbo.lora, family);
    }
  }
  // Saved once per throw, not per quality change: the row being remembered is
  // the pre-turbo one, and draft → good in between should not overwrite it.
  if (!turbo.on) {
    turbo.saved = {
      steps: Number(value("steps", S.TURBO_RESET.steps)),
      sampler_name: String(value("sampler_name", S.TURBO_RESET.sampler_name)),
      scheduler: String(value("scheduler", S.TURBO_RESET.scheduler)),
      shift_video: Number(value("shift_video", S.TURBO_RESET.shift_video)),
      shift_audio: Number(value("shift_audio", S.TURBO_RESET.shift_audio)),
    };
  }
  turbo.on = true;
  // The row and the step table are the family's unless the picked file's preset
  // owns them — see `state.turboPreset`. With no file at all they are the
  // family's by definition: a merged checkpoint has no card to read.
  const steps = S.turboSteps(turbo.lora, family);
  const row = S.turboRow(turbo.lora, family);
  set("steps", steps[turbo.quality] ?? steps.medium ?? S.TURBO_STEPS.medium);
  set("sampler_name", row.sampler_name);
  set("scheduler", row.scheduler);
  // The flow shifts the picked family's card was distilled against — part of
  // the same contract as the step count, so they are thrown and released with
  // the row. Merged-checkpoint mode keeps the row's own values: the schedule
  // is the checkpoint's business and the user picked it.
  if (turbo.lora) {
    const preset = S.turboPreset(turbo.lora, family);
    set("shift_video", preset.shift_video);
    set("shift_audio", preset.shift_audio);
  }
}

function throwOff(container, { set }, { removeEntry = true } = {}) {
  const turbo = container.turbo;
  if (removeEntry && turbo.lora) S.removeLora(container, turbo.lora);
  const saved = turbo.saved ?? S.TURBO_RESET;
  set("steps", saved.steps);
  set("sampler_name", saved.sampler_name);
  set("scheduler", saved.scheduler);
  set("shift_video", saved.shift_video ?? S.TURBO_RESET.shift_video);
  set("shift_audio", saved.shift_audio ?? S.TURBO_RESET.shift_audio);
  turbo.on = false;
  turbo.saved = null;
}

/**
 * Reconcile the switch with the stack, on every commit.
 *
 * The entry can leave the stack without the pill being touched — the chip's ✕,
 * the manager's card, a strength dragged to zero — and each of those means
 * "turbo off", so the sampler row has to come back too. The one asymmetry: an
 * entry re-enabled by hand does not throw the switch, because nothing was saved
 * and silently rewriting the steps under someone editing a card is worse than
 * leaving the pill for them to press.
 */
export function sync(container, widgetIO) {
  if (container.turbo?.on && !engaged(container)) {
    throwOff(container, widgetIO, { removeEntry: false });
    return true;
  }
  return false;
}

/** Swap which file the switch reaches for — from the weights popover. Engaged,
 *  the entries swap with it so the run never carries both distills at once.
 *  Swapping to *none* keeps the switch thrown: that is the statement "my
 *  checkpoint is already distilled", not "slow back down". */
export function setTurboLora(container, name, widgetIO) {
  const turbo = container.turbo;
  const was = turbo.lora;
  if (name === was) return;
  turbo.lora = name;
  if (!turbo.on) return;
  if (was) S.removeLora(container, was);
  if (name) throwOn(container, widgetIO);
}

const QUALITY_TITLE = {
  draft: "4 steps — the fast look. Softer detail; heavy motion can smear.",
  medium: "6 steps — the comfort zone the turbo LoRAs were tuned for.",
  good: "8 steps — about as close to a native 20-step render as a distill gets. "
      + "Past 8 they over-sharpen rather than improve.",
};

/**
 * The switch and, while it is on, the quality stops. Drawn on the sampler row
 * with the other accelerators, because that is what it is — and lit the same
 * way, because a render with it on is not a native render.
 *
 * @param {object} spec
 * @param {object} spec.container   a state or a timeline: `.loras`, `.turbo`
 * @param {(name, fallback) => any} spec.value
 * @param {(name, value) => void} spec.set
 * @param {() => void} spec.onCommit  serialize the container after a change
 */
export function turboPills({ container, value, set, onCommit }) {
  const turbo = container.turbo;
  const on = turbo.on && engaged(container);
  // The lead-in is this machine's setting, not this node's, and it is in force
  // on every turbo render made here — so the row carries it rather than leaving
  // a render that samples its opening on the base weights looking identical to
  // one that does not. Only where there is a LoRA to hold off: a merged
  // checkpoint has none. See `settings.js` and `render.LeadIn`.
  const lead = turbo.lora ? Number(uiSetting("turbo_lead_in", 0)) || 0 : 0;
  const short = (name) => name.split("/").pop().replace(/\.[^.]+$/, "");
  const pills = [];

  // So the first press has a list to offer rather than a spinner: cached after
  // the first fetch, and only started at all while no file is picked yet.
  if (!turbo.lora) loadLoraNames();

  // The row the switch is setting, named rather than assumed: it is the
  // family's for every ordinary distill and the file's own for one that was
  // trained against a particular schedule.
  const rowOf = S.turboRow(turbo.lora, S.pieceFamily(container));
  const rowName = `${rowOf.sampler_name} + ${rowOf.scheduler}`;

  pills.push(el("div", { class: `mmc-pill mmc-pill-group${on ? " accel-on" : ""}` }, [
    el("button", {
      class: "mmc-turbo-main",
      title: on
        ? turbo.lora
          ? t("Turbo — running on {lora} at {steps} steps, {row}. "
            + "Switching off removes the LoRA and puts the sampler row back.",
            { lora: turbo.lora, steps: value("steps", "?"), row: rowName })
          : t("Turbo — {steps} steps, {row}, no LoRA: the checkpoint is "
            + "taken to be a merged distill. Switching off puts the sampler row back.",
            { steps: value("steps", "?"), row: rowName })
        : turbo.lora
          ? t("Turbo off. On, it adds {lora}, drops the steps to the picked quality and "
            + "switches the sampler to {row} — H3's soundtrack warbles on "
            + "res_multistep at turbo step counts.", { lora: turbo.lora, row: rowName })
          : t("Turbo off. The first press picks which distillation LoRA it engages — or none, "
            + "for a checkpoint with the distillation already merged in."),
      onclick: (event) => {
        if (turbo.on) {
          throwOff(container, { value, set });
          onCommit();
        } else if (turbo.lora || turbo.merged) {
          throwOn(container, { value, set });
          onCommit();
        } else {
          // No file picked yet: the first press is the picking. Engaging on the
          // spot rather than sending anyone to the weights popover — the pill
          // was pressed to go faster, not to configure something. "No LoRA" is
          // a real answer: merged turbo checkpoints carry their distillation
          // in the weights, and the user picking it is trusted to know that.
          openTurboChoice(event.currentTarget, {
            includeNone: NO_LORA,
            value: "",
            onPick: (picked) => {
              if (picked === t(NO_LORA)) turbo.merged = true;
              else turbo.lora = picked;
              throwOn(container, { value, set });
              onCommit();
            },
          });
        }
      },
    // Just the state. The filename used to ride here and was the widest thing
    // on the row by a factor of four — forty characters of
    // `minimax_h3_turbo_v4_step600_ema_pruned_comfyui` for a decision made once,
    // the day the file was downloaded, crowding out the numbers that are
    // actually dialled. It is named in the tooltip, in the picker beside this,
    // and in the weights popover. "merged" stays: that is not which file, it is
    // that there is no file, which changes what the switch does.
    }, [icon("bolt", 16), el("span", {
      text: !on ? t("turbo off")
        : turbo.lora ? t("turbo")
        : t("turbo · merged"),
    })]),
    // Which file, as its own control — the seed pill's shape: the big half
    // throws the switch, the small half changes what it throws. Only once
    // there is something to change; before that the big half is the picker.
    // Merged mode counts as something to change: without this the choice
    // "no LoRA" was final for the node's whole life, because the big half
    // remembers it and never asks again.
    ...(turbo.lora || turbo.merged ? [el("button", {
      class: "mmc-step mmc-turbo-pick",
      title: (turbo.lora
          ? t("Pick a different turbo LoRA — now {lora}.", { lora: turbo.lora })
          : t("Pick a turbo LoRA — now none: the checkpoint is taken to be a merged distill."))
           + (on ? " " + t("Swapped in place: the run never carries both distills at once.") : ""),
      onclick: (event) => openTurboChoice(event.currentTarget, {
        includeNone: NO_LORA,
        value: turbo.lora || t(NO_LORA),
        onPick: (picked) => {
          turbo.merged = picked === t(NO_LORA);
          setTurboLora(container, picked === t(NO_LORA) ? "" : picked, { value, set });
          onCommit();
        },
      }),
    }, [icon("chevron", 14)])] : []),
  ]));

  // Only while it is doing something, like the spectrum blend: off, the
  // qualities are a setting for a feature not in use.
  if (on) {
    const steps = Number(value("steps", 0));
    // The picked file's table, which is the family's for everything that does
    // not name its own. A file with its own counts describes them itself rather
    // than through the three stock sentences, which would be about numbers it
    // is not running.
    const table = S.turboSteps(turbo.lora, S.pieceFamily(container));
    const own = S.turboPreset(turbo.lora, S.pieceFamily(container)).note;
    pills.push(el("div", { class: "mmc-pill mmc-turbo-seg" }, S.TURBO_QUALITIES.map((quality) => el("button", {
      class: "mmc-turbo-opt",
      // Pressed is derived from the real steps widget, so a hand-edited step
      // count un-presses all three rather than one of them lying about it.
      "aria-pressed": steps === table[quality],
      title: own
        ? t("{steps} steps.", { steps: table[quality] }) + " " + t(own)
        : t(QUALITY_TITLE[quality]),
      onclick: () => {
        turbo.quality = quality;
        set("steps", table[quality]);
        onCommit();
      },
    }, [
      el("span", { text: t(quality === "medium" ? "med" : quality) }),
      el("span", { class: "mmc-pill-sub", text: String(table[quality]) }),
    ]))));
  }

  // The lead-in, beside the quality stops because it is a slice of exactly the
  // number they set: `lead 2/6` next to the `med 6` that made it six. A stepper
  // rather than stops of its own — it is a plain count with a natural zero, and
  // the row already spells counts this way (steps, cfg, the two shifts).
  //
  // Shown as a fraction because the numerator alone means nothing: two of four
  // is half the render on the base weights, two of eight is a quarter. Lit only
  // when it is doing something, like every other accelerator on this row.
  //
  // Writing here writes the settings file — this is a shortcut into the one
  // answer that page holds, not a second copy of it, the same bargain the
  // switch strikes with the LoRA stack. Other open nodes pick it up when they
  // next redraw.
  // Advanced, like the two accelerators it sits beside: a lead-in is a claim
  // about how a distillation should be used, and a row that never makes that
  // claim should not have to carry the control for it. In force is still
  // visible — a lead-in that is set shows its pill whatever the setting says,
  // because a number that is changing the render must never be off screen.
  if (on && turbo.lora && (uiSetting("advanced", false) === true || lead > 0)) {
    const steps = Number(value("steps", 0)) || 0;
    pills.push(stepperPill({
      value: lead, min: 0, max: Math.min(S.TURBO_LEAD_MAX, Math.max(0, steps - 1)),
      step: 1, width: "44px",
      className: lead ? "accel-on" : "",
      // Parenthesised: `+` binds tighter than `:`, and without them the last
      // sentence would only ever appear on the off branch.
      title: (lead
        ? t("Turbo lead-in: the first {n} of these {steps} steps sample with the "
          + "distillation held off the checkpoint, and the rest finish on it. "
          + "One seed, one schedule — this only moves where the LoRA takes over.",
          { n: lead, steps })
        : t("Turbo lead-in — off. A distillation decides a shot in far fewer steps "
          + "than the model would, which is what makes a turbo render stop "
          + "following the prompt. Hand the opening steps back and the rest of "
          + "the same schedule still finishes on the LoRA."))
        + " " + t("This machine's setting, not this workflow's — the same one on "
                + "the settings page."),
      format: (n) => (n ? t("lead {n}/{steps}", { n, steps }) : t("lead off")),
      onChange: (next) => { patchSettings({ turbo_lead_in: next }).then(onCommit); onCommit(); },
    }));
  }

  return pills;
}

/**
 * The weights-popover row: which file the switch reaches for. Listed with the
 * files because it is the same kind of decision — made once when the LoRA is
 * downloaded — and `openChoicePopover`d like every other row there.
 */
export function turboRow({ container, widgetIO, onChange }) {
  const NONE = "— none —";
  const turbo = container.turbo;
  return el("div", { class: "mmc-weight-row" }, [
    el("span", { class: "mmc-weight-name", text: t("Turbo LoRA") }),
    el("button", {
      class: `mmc-weight-file${turbo.lora ? "" : " empty"}`,
      title: t("The distillation LoRA the turbo pill engages, from models/loras.\n\n"
           + "larryvrh's v4 EMA runs at strength 1.0 on the checkpoints' own schedule; "
           + "the lightx2v distill at about 0.6 with the video shift at 6 — the switch "
           + "sets both from the filename, the LoRA manager's slider and the shift pills "
           + "override them. Steps and sampler are the pill's business, not this row's.\n\n"
           + "'none' also fits a checkpoint with the distillation merged into the weights: "
           + "the pill then only drops the steps and swaps the sampler, and the schedule "
           + "stays whatever the row says."),
      text: turbo.lora || (turbo.merged ? t("no LoRA · merged checkpoint") : t("not set")),
      onclick: (event) => openTurboChoice(event.currentTarget, {
        includeNone: true,
        value: turbo.lora || t(NONE),
        onPick: (picked) => {
          if (picked === t(NONE)) turbo.merged = false;
          setTurboLora(container, picked === t(NONE) ? "" : picked, widgetIO);
          onChange();
        },
      }),
    }),
  ]);
}
