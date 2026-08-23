// The refine button, its settings, and the panel the rewrite lands in.
//
// H3-Base reads an expanded, sectioned description rather than a sentence, and
// `contextir.py` can only put the *skeleton* of one back — the field names, the
// instruction line, the shot markers. The prose is what a local vision model is
// for, and `refine.py` is the half of this that talks to it.
//
// The rewrite is fetched here, on a click, and stored in the blob. It is not
// done at queue time on purpose: what the model will actually read has to be
// visible and editable *before* five minutes of sampling rather than after, and
// a rewrite generated inside `execute` would differ between two runs of the same
// queue and miss ComfyUI's cache every time.
//
// So the panel below is deliberately an editor and not a readout. The rewrite is
// a draft: it can be corrected, switched off without being thrown away, and
// reverted to the sentence it came from.

import { el, icon, dismissable, keepScroll, placeNear } from "./dom.js";
import { stepperPill } from "./pills.js";
import { t } from "./i18n.js";
import { api } from "../../../scripts/api.js";

// Machine-level, not workflow-level. Which text encoder is on this disk is a
// fact about this computer; putting it in `creator_data` would ship it to
// whoever opens the workflow next and would invalidate the node's cache every
// time the temperature moved.
const STORE = "minimax_creator.refiner";

const DEFAULTS = {
  // A text encoder in ComfyUI's own process, managed and evicted like any other
  // model — which on a machine already offloading H3's own encoder is the
  // difference between a rewrite and a coffee break.
  model: "",
  // Cold by default: refining is a fidelity task, and at 0.7 a small model
  // paraphrases the very words it was told to keep. Raise it for variety.
  temperature: 0.3,
  seed: -1,
  language: "English",
  // Which skill package writes the rewrite instead of the built-in prompts.
  // Empty is the built-in harness; a name is a `.skill` under the node's
  // skills/ folder, handed to the model whole as its only instruction.
  skill: "",
  // Which of the built-in per-mode templates writes the rewrite. "auto"
  // follows the request's derived mode — frames pick I2VA/L2VA/FL2VA,
  // @ references pick REF2VA, nothing picks T2VA — exactly as the weights
  // pill's route does. A pinned name overrides everywhere, REF2VA included;
  // a pin across the reference boundary comes back with a quality hint in
  // the reply's problems rather than a refusal.
  template: "auto",
  // How long the reply may run, in tokens — not a context size. There is no
  // context setting on this backend: ComfyUI's Qwen3-VL tokenizer never
  // truncates, so the prompt is embedded whole however long it gets, and the
  // only budget that exists is the one on the answer. A whole-timeline rewrite
  // of a dozen cards is the case that needs it raised.
  maxTokens: 6144,
};

// What the reply-length pill may be moved between. Mirrors `refine.MIN_PREDICT`
// and `refine.MAX_PREDICT`, which clamp it again server-side.
const TOKENS = { min: 1024, max: 32768, step: 1024 };

// The eleven the guide's `<d>[Language]` tag is documented against.
export const LANGUAGES = [
  "English", "Chinese", "Spanish", "French", "German", "Portuguese",
  "Russian", "Japanese", "Korean", "Italian", "Arabic",
];

export function settings() {
  let stored;
  try {
    stored = JSON.parse(localStorage.getItem(STORE) || "{}");
  } catch {
    return { ...DEFAULTS };
  }
  // Settings written while there were two backends hold two model names under
  // two keys. The text encoder is the one that still means something; the
  // Ollama tag under `model` names nothing that can be loaded.
  if (stored.localModel !== undefined) {
    const { localModel, backend, url, ...rest } = stored;
    stored = { ...rest, model: localModel };
  }
  // `saveSettings` writes the whole object, so every install that ever saved
  // anything has the old 0.7 default baked in as if it were a choice. It was
  // not one — 0.7 was the default — so it moves with the default.
  if (stored.temperature === 0.7) {
    const { temperature, ...rest } = stored;
    stored = rest;
  }
  return { ...DEFAULTS, ...stored };
}

export function saveSettings(patch) {
  const next = { ...settings(), ...patch };
  try { localStorage.setItem(STORE, JSON.stringify(next)); } catch { /* private mode */ }
  return next;
}

/** The text encoder the refiner is set to. Empty means nothing is chosen. */
export function chosenModel(current = settings()) {
  return current.model || "";
}

// ---- the server -------------------------------------------------------------

let modelCache = { at: 0, names: [] };

/** The text encoders on disk. Empty means the folder is bare — which the
 *  settings popover says, rather than showing a blank list. */
export async function listModels({ force = false } = {}) {
  if (!force && Date.now() - modelCache.at < 20000) return modelCache.names;
  try {
    const response = await api.fetchApi("/minimax_creator/refine/models");
    const body = await response.json();
    modelCache = { at: Date.now(), names: body.models ?? [] };
  } catch {
    modelCache = { at: Date.now(), names: [] };
  }
  return modelCache.names;
}

let skillCache = { at: 0, names: [] };

/** The skill packages under the node's skills/ folder. */
export async function listSkills({ force = false } = {}) {
  if (!force && Date.now() - skillCache.at < 20000) return skillCache.names;
  try {
    const response = await api.fetchApi("/minimax_creator/refine/skills");
    const body = await response.json();
    skillCache = { at: Date.now(), names: body.skills ?? [] };
  } catch {
    skillCache = { at: Date.now(), names: [] };
  }
  return skillCache.names;
}

/**
 * Ask for a rewrite.
 *
 * `payload` is `{kind, data, index}` — the blob the caller is already holding,
 * because the server has to compile it to find out what the request is: the
 * mode, the reference slots, and which ordinal each handle will be given.
 *
 * @returns {Promise<{mode, shots: {index, body, sections?}[], soundscape, music,
 *                    sections: object|null, piece: string|null,
 *                    scope: string|null, seen: string, problems: string[],
 *                    skill?: string}>}
 *   `piece` is the rewritten global prompt (whole-timeline refines only);
 *   `scope: "shot"` marks bodies that compile joins the global prompt onto,
 *   like typed text; chained reference cards carry their own `sections`.
 */
export async function refine(payload) {
  const { model, temperature, seed, language, maxTokens, skill, template } = settings();
  const response = await api.fetchApi("/minimax_creator/refine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, model, temperature, seed, language,
                           max_tokens: maxTokens, skill, template }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || t("the refiner failed ({status})", { status: response.status }));
  return await collect(body.job);
}

/**
 * Wait for a started job and hand back its result.
 *
 * A rewrite runs for many minutes with nothing on the wire, and no browser
 * holds a silent HTTP request open that long — Chromium drops one flat at five
 * minutes, a proxy in between usually sooner. So the POST above only starts
 * the job; the server announces the end on the websocket, and the result is
 * collected here with a GET. The event is just the nudge — a slow poll backs
 * it up, so a dropped websocket costs seconds, not the rewrite.
 */
function collect(job) {
  return new Promise((resolve, reject) => {
    let timer = null;
    let inFlight = false;
    const settle = (fn, value) => {
      clearInterval(timer);
      api.removeEventListener("minimax_creator.refine.done", nudge);
      fn(value);
    };
    const check = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await api.fetchApi(`/minimax_creator/refine/job/${job}`);
        const body = await response.json().catch(() => ({}));
        if (response.status === 404) {
          settle(reject, new Error(body.error || t("the refine was lost — the server may have restarted")));
        } else if (body.done && body.error) {
          settle(reject, new Error(body.error));
        } else if (body.done) {
          settle(resolve, body.result);
        }
        // Anything else is "still writing", or a blip the next poll retries.
      } catch { /* a network blip; the next poll retries */ }
      inFlight = false;
    };
    const nudge = ({ detail }) => { if (detail?.job === job) check(); };
    api.addEventListener("minimax_creator.refine.done", nudge);
    timer = setInterval(check, 5000);
    check(); // it may have finished before the listener existed
  });
}

// ---- settings popover -------------------------------------------------------

/**
 * Where the model and the sampling live.
 *
 * The model is the only thing anyone changes twice, so it is the whole of the
 * popover; the rest is folded away behind one line. Built out of the same
 * option rows and pills as the aspect and resolution popovers rather than as a
 * form — a `<select>` and two number inputs would be the only browser chrome in
 * the entire node.
 */
export function openSettings(anchor, onChange) {
  const pop = el("div", { class: "mmc-pop mmc-refine-pop" });
  const modelHost = el("div", { class: "mmc-refine-models" });
  const skillHost = el("div", { class: "mmc-refine-models" });
  const templateHost = el("div", { class: "mmc-refine-models" });
  const moreHost = el("div", { class: "mmc-refine-more-body" });

  const changed = () => { onChange?.(); drawTemplate(); drawMore(); };

  // What each template is for, in the words the pill and the panel share.
  const TEMPLATES = [
    ["auto", "follows what is attached: frames pick I2VA / L2VA / FL2VA, "
             + "@ references pick REF2VA, a bare prompt picks T2VA."],
    ["T2VA", "text only — the video is described from nothing."],
    ["I2VA", "first frame — the rewrite opens on the attached image and develops forward."],
    ["L2VA", "last frame — the rewrite converges on the attached image at the end."],
    ["FL2VA", "first and last frame — the rewrite is the motion path between the two."],
    ["REF2VA", "@ references — the six-section form that defines and tracks them. "
               + "Pinnable on any request, but without references it may degrade quality."],
  ];

  /** Which per-mode template writes the rewrite. Hidden while a skill is
   *  chosen — a skill replaces the built-in prompting whole, templates
   *  included, and a dial that does nothing should not be shown doing it. */
  function drawTemplate() {
    if (settings().skill) {
      templateHost.replaceChildren();
      return;
    }
    const chosen = settings().template || "auto";
    templateHost.replaceChildren(
      el("span", { class: "mmc-note-key", text: t("template") }),
      el("div", { class: "mmc-chips" }, TEMPLATES.map(([name, why]) => el("button", {
        class: "mmc-chip",
        "aria-checked": name === chosen,
        text: name === "auto" ? "auto" : name.toLowerCase(),
        title: t(why),
        onclick: () => { saveSettings({ template: name }); changed(); },
      }))),
      el("div", { class: "mmc-refine-hint",
                  text: t("Which of the built-in prompt templates writes the rewrite. "
                      + "auto follows the request, like the weights route; the result "
                      + "panel says which one was used.") }),
    );
  }

  /** Built-in prompts, or one of the skill packages. Only drawn when a skill
   *  exists on disk: with a bare skills/ folder there is no choice to show,
   *  and a one-option radio group would only raise the question it answers. */
  async function drawSkills(force = false) {
    const names = await listSkills({ force });
    let chosen = settings().skill;
    // A setting pointing at a package since deleted would silently refine with
    // it and 400 on every press; forget it instead.
    if (chosen && !names.includes(chosen)) {
      saveSettings({ skill: "" });
      chosen = "";
    }
    if (!names.length) {
      skillHost.replaceChildren();
      return;
    }
    // Each row says what kind of thing it is, because the two kinds behave
    // nothing alike: a prompt is the node's harness with the format assembled
    // around the model, a skill is a package the model follows on its own.
    const row = (label, value, kind, title) => el("button", {
      class: "mmc-opt",
      "aria-checked": value === chosen,
      title,
      onclick: () => { saveSettings({ skill: value }); changed(); drawSkills(); },
    }, [
      el("span", { class: "mmc-opt-label mmc-refine-name", text: label }),
      el("span", { class: "mmc-opt-kind", text: t(kind) }),
      el("span", { class: "mmc-radio" }),
    ]);
    skillHost.replaceChildren(
      el("span", { class: "mmc-note-key", text: t("prompting") }),
      row(t("built-in"), "", "prompt",
          t("The node's own instructions and guides, with the format assembled around the model's prose.")),
      ...names.map((name) => row(name, name, "skill",
          t("The '{name}' skill package, handed to the model as its only instruction. "
        + "The model writes the whole prompt document itself — instruction line, shot "
        + "markers and timestamps included — and the rewrite lands as one block.", { name }))),
      el("div", { class: "mmc-refine-hint",
                  text: t("A skill replaces the built-in prompting entirely, and rewrites one "
                      + "generation at a time.") }),
    );
  }

  async function drawModels(force = false) {
    modelHost.replaceChildren(el("div", { class: "mmc-refine-hint", text: t("Looking for models…") }));
    const names = await listModels({ force });
    if (!names.length) {
      // An empty list is a state with an action in it, not a blank panel: where
      // to put a model is the whole of the answer.
      modelHost.replaceChildren(el("div", { class: "mmc-refine-empty" }, [
        el("div", { text: t("No text encoders found.") }),
        el("code", { text: "models/text_encoders/qwen3vl_4b.safetensors" }),
        el("button", { class: "mmc-ghost", text: t("Look again"), onclick: () => drawModels(true) }),
      ]));
      return;
    }
    const chosen = chosenModel();
    modelHost.replaceChildren(...names.map((name) => el("button", {
      class: "mmc-opt",
      "aria-checked": name === chosen,
      // The full name, because the row ellipsises it — a folder-qualified
      // `qwen3vl/qwen3vl_4b_instruct_fp8.safetensors` is not a width any
      // popover should be.
      title: name,
      onclick: () => { saveSettings({ model: name }); changed(); drawModels(); },
    }, [
      el("span", { class: "mmc-opt-label mmc-refine-name", text: name }),
      el("span", { class: "mmc-radio" }),
    ])));
  }

  /** The language chips and the two sampling pills. Redrawn whole on every
   *  change — it is a dozen elements and none of them holds a caret. */
  function drawMore() {
    const current = settings();
    const chip = (name) => el("button", {
      class: "mmc-chip",
      "aria-checked": name === current.language,
      text: t(name),
      onclick: () => { saveSettings({ language: name }); changed(); },
    });

    const random = current.seed < 0;
    moreHost.replaceChildren(
      el("div", { class: "mmc-refine-group" }, [
        el("span", { class: "mmc-note-key", text: t("language") }),
        el("div", { class: "mmc-chips" }, LANGUAGES.map(chip)),
        el("div", { class: "mmc-refine-hint",
                    text: t("The prose and the dialogue. Field names, labels and camera terms stay English.") }),
      ]),
      el("div", { class: "mmc-refine-group" }, [
        el("span", { class: "mmc-note-key", text: t("reply length") }),
        el("div", { class: "mmc-refine-row" }, [
          stepperPill({
            value: Number(current.maxTokens), ...TOKENS, width: "62px",
            title: t("How many tokens the rewrite may run to. Raise it if a whole-timeline "
                 + "refine comes back cut off; there is no cost to a model that stops early."),
            format: (n) => t("{n}k tokens", { n: Math.round(n / 1024) }),
            onChange: (next) => { saveSettings({ maxTokens: next }); changed(); },
          }),
        ]),
        el("div", { class: "mmc-refine-hint",
                    text: t("The answer's budget, not a context size — the prompt is never "
                        + "truncated to fit, however long it gets.") }),
      ]),
      el("div", { class: "mmc-refine-group" }, [
        el("span", { class: "mmc-note-key", text: t("sampling") }),
        el("div", { class: "mmc-refine-row" }, [
          stepperPill({
            value: Number(current.temperature), min: 0, max: 2, step: 0.05, width: "58px",
            title: t("Lower keeps closer to your wording; higher invents more around it."),
            format: (n) => t("temp {n}", { n: n.toFixed(2) }),
            onChange: (next) => { saveSettings({ temperature: next }); changed(); },
          }),
          el("div", { class: "mmc-pill mmc-pill-group" }, [
            el("button", {
              class: "mmc-step mmc-seed-dice",
              title: random ? t("Fix the seed at a number") : t("Roll a new seed now"),
              onclick: () => {
                saveSettings({ seed: Math.floor(Math.random() * 0x7fffffff) });
                changed();
              },
            }, [icon("dice", 15)]),
            el("button", {
              class: "mmc-ghost mmc-refine-seed",
              text: random ? t("new every time") : String(current.seed),
              title: random
                ? t("Every refine comes out differently. Click to fix it.")
                : t("Refining the same prompt gives the same rewrite. Click to vary it again."),
              onclick: () => {
                saveSettings({ seed: random ? Math.floor(Math.random() * 0x7fffffff) : -1 });
                changed();
              },
            }),
          ]),
        ]),
      ]),
    );
  }

  pop.append(
    el("div", { class: "mmc-pop-title", text: t("Refiner") }),
    modelHost,
    el("div", { class: "mmc-refine-hint mmc-refine-note",
                text: t("A Qwen3-VL text encoder, loaded and evicted like any other model. "
                    + "It also reads your attached images.") }),
    skillHost,
    templateHost,
    el("details", { class: "mmc-refine-fold" }, [
      el("summary", { text: t("Language and sampling") }),
      moreHost,
    ]),
  );

  document.body.appendChild(pop);
  placeNear(pop, anchor);
  dismissable(pop);
  drawModels();
  drawSkills();
  drawTemplate();
  drawMore();
}

// ---- the panel --------------------------------------------------------------

const REF_SECTIONS = ["subject_definitions", "summary", "retention_analysis"];

/**
 * The rewrite, where it can be read and edited.
 *
 * Owns nothing: it is handed the state that holds `refined` and a commit
 * callback, exactly like the rest of the editor. Built once and refreshed in
 * place, because the textareas in it are being typed into — rebuilding them on
 * every commit would drop the caret mid-word.
 */
export class RefinePanel {
  /**
   * @param {object} options
   * @param {() => object} options.getState  the state whose `refined` this shows
   * @param {() => void} options.onCommit
   * @param {boolean} [options.audioFields]  show overall_soundscape / non_diegetic_music.
   *   True in the Creator node, which has nowhere else to put them; false in a
   *   timeline segment, where they belong to the timeline and are edited there.
   * @param {() => void} [options.onRevert]  the rewrite was thrown away. For an
   *   owner holding state this panel cannot reach — the timeline's own audio
   *   fields and reference sections, which no longer belong to anything once
   *   the last card's rewrite is gone.
   */
  constructor({ getState, onCommit, audioFields = true, onRevert = null }) {
    this.getState = getState;
    this.onCommit = onCommit;
    this.audioFields = audioFields;
    this.onRevert = onRevert;
    this.problems = [];
    // What the model said it could see in the attached images, from the last
    // call. Deliberately not in the state: it describes one run of one model,
    // it is never queued, and a saved workflow carrying it would present a
    // year-old readout as current.
    this.seen = "";
    this.root = el("div", { class: "mmc-refined" });
    this.bodyBox = null;
    // The editable boxes, by key, and the arrangement they were last drawn in.
    // Together they are what "refreshed in place" is made of — see `box` and
    // the shape gate at the top of `render`.
    this.boxes = new Map();
    this.shape = null;
    this.render();
  }

  get refined() {
    return this.getState().refined || null;
  }

  /** Take a server reply for one shot. `soundscape`/`music` are written onto the
   *  state only where this panel is the thing that shows them. */
  apply(result, shot) {
    const state = this.getState();
    // What the rewrite is about to overwrite, so `clear` can put the state back
    // exactly as it was rather than leaving generated prose behind in two fields
    // the user never typed in. Carried across a second refine rather than
    // re-taken, or refining twice would record the first rewrite's output as
    // "what was there before".
    const replaced = this.refined?.replaced
      ?? { soundscape: state.soundscape ?? "", music: state.music ?? "" };

    state.refined = {
      body: shot.body,
      // Present on a timeline segment's rewrite: the body is the shot alone,
      // and compile joins the global prompt in front of it as it does for
      // typed text. The Creator node has no global prompt and gets none.
      ...(result.scope ? { scope: result.scope } : {}),
      ...(result.sections ? { sections: result.sections } : {}),
      // Which skill package wrote this, when one did — the answer to "why does
      // this rewrite look nothing like yesterday's" once the setting has moved.
      ...(result.skill ? { skill: result.skill } : {}),
      // Which template wrote this, and whether that was the request's own mode
      // or a pin. Stored, not re-derived: the setting and the attachments can
      // both move after the fact, and the answer is about this rewrite.
      ...(result.template ? { template: result.template, forced: !!result.forced } : {}),
      // What it was written from, so the panel can say when the prompt has moved
      // on underneath it. Advisory: a rewrite of an older sentence is a stale
      // draft, not a broken one, and only the user can say which.
      source: state.prompt ?? "",
      model: chosenModel(),
      enabled: true,
      ...(this.audioFields ? { replaced } : {}),
    };
    // Only what the reply actually carries. An empty field means the model had
    // nothing to add, which is not the same as "make this empty" — and these
    // two are typed in by hand as often as they are written by a rewrite, so
    // blanking them on a reply that skipped them deleted a line the user wrote
    // in a box they were looking at. The timeline has always taken them this
    // way (see `Timeline.takePiece`); this is the face agreeing with it.
    if (this.audioFields) {
      if (result.soundscape) state.soundscape = result.soundscape;
      if (result.music) state.music = result.music;
    }
    this.seen = result.seen ?? "";
    this.problems = result.problems ?? [];
    this.render();
  }

  fail(message) {
    this.problems = [message];
    this.render();
  }

  /**
   * Throw the rewrite away and put the state back where it was.
   *
   * Everything the rewrite wrote goes, not just the body: the reference sections,
   * and the two audio fields it overwrote, restored to whatever they held before
   * — empty, if the user had never typed in them. Reverting is the user saying
   * "queue what I wrote", and a `overall_soundscape` still full of the model's
   * prose would queue a line they did not write and could not see the origin of.
   */
  clear() {
    const state = this.getState();
    const replaced = state.refined?.replaced;
    delete state.refined;
    if (this.audioFields && replaced) {
      state.soundscape = replaced.soundscape ?? "";
      state.music = replaced.music ?? "";
    }
    this.seen = "";
    this.problems = [];
    this.onCommit?.();
    this.onRevert?.();
    this.render();
  }

  /** Whether the prompt has been edited since the rewrite was made. */
  get stale() {
    const refined = this.refined;
    return !!refined && (refined.source ?? "") !== (this.getState().prompt ?? "");
  }

  /**
   * One of the panel's editable boxes: built on first sight, then kept.
   *
   * These are typed into, and typing in one runs `onCommit` — which on the node
   * face ends in a full `render` of this panel. Rebuilding the element under
   * the caret is what that used to mean: a textarea removed from the document
   * takes the focus with it and its replacement starts scrolled to the top, so
   * the box accepted one character per click and jumped back to the top after
   * each one. The element is now made once and only its value is refreshed
   * afterwards — and `render` leaves the DOM alone entirely unless the panel's
   * shape has actually moved.
   *
   * `set` is captured at creation and outlives every later render, so it must
   * resolve the state it writes to when it is *called* rather than closing over
   * whichever object was current when the box was built. See the call sites.
   */
  box(key, value, set, { rows = 3, placeholder = "", className = "mmc-refined-box" } = {}) {
    if (!this.boxes.has(key)) {
      const made = el("textarea", {
        class: className, rows: String(rows), placeholder,
        oninput: (event) => { set(event.target.value); this.onCommit?.(); },
      });
      made.addEventListener("pointerdown", (event) => event.stopPropagation());
      // A rewrite is longer than the rows it is given, and this box lives in a
      // node body where the wheel is the canvas's zoom — see `keepScroll`.
      keepScroll(made);
      this.boxes.set(key, made);
    }
    return this.fill(key, value);
  }

  /** A value into a box that is already drawn, and only where it differs:
   *  writing a box's own text back into it would put the caret at the end. */
  fill(key, value) {
    const box = this.boxes.get(key);
    const next = value ?? "";
    if (box && box.value !== next) box.value = next;
    return box;
  }

  /** The state into the boxes, rebuilding nothing. What a render does when the
   *  shape has not moved — a second rewrite landing on top of an identical one
   *  still has to show its new prose. */
  syncBoxes() {
    const state = this.getState();
    const refined = this.refined;
    this.fill("body", refined?.body);
    if (refined?.sections) {
      for (const name of REF_SECTIONS) this.fill(`section:${name}`, refined.sections[name]);
    }
    if (this.audioFields) {
      this.fill("soundscape", state.soundscape);
      this.fill("music", state.music);
    }
  }

  render() {
    const state = this.getState();
    const refined = this.refined;
    // The audio fields keep the panel open on their own once they hold
    // something: they are queued whether or not a rewrite exists, so a pair the
    // user typed themselves must not lose the only place they can be edited.
    const audio = !!(this.audioFields && (state.soundscape?.trim() || state.music?.trim()));
    const empty = !refined && !audio && !this.problems.length;

    // What the panel is made of, as against what is written in it. Typing moves
    // the second and never the first, so a shape that has not moved is a panel
    // that must not be rebuilt — the boxes in it are being written in. Every
    // part of the arrangement is in here: what the head says, whether the two
    // folds exist, and the warnings under them.
    const shape = JSON.stringify([
      empty, !!refined, refined?.enabled !== false, refined?.model ?? null,
      refined?.template ?? null, !!refined?.forced, refined?.skill ?? null,
      this.stale, this.seen, !!refined?.sections, audio, this.problems,
    ]);
    if (shape === this.shape) {
      this.syncBoxes();
      return;
    }
    this.shape = shape;

    if (empty) {
      this.root.replaceChildren();
      this.boxes.clear();
      return;
    }

    const parts = [];
    if (refined) {
      const on = refined.enabled !== false;
      parts.push(el("div", { class: "mmc-refined-head" }, [
        el("button", {
          class: `mmc-refined-toggle${on ? " on" : ""}`,
          title: on
            ? t("This rewrite is what the model will read. Click to queue your own prompt instead — "
              + "the rewrite is kept.")
            : t("Your own prompt is what the model will read. Click to use the rewrite again."),
          onclick: () => {
            refined.enabled = !on;
            this.onCommit?.();
            this.render();
          },
        }, [el("span", { class: "mmc-dot" }), el("span", { text: on ? t("refined") : t("refined (off)") })]),
        ...(refined.model ? [el("span", { class: "mmc-refined-model", text: refined.model })] : []),
        // Which template this prose is in — the same answer the weights pill
        // gives about the checkpoint. A pin is marked, because a rewrite in a
        // style the attachments do not imply should say it was asked for.
        ...(refined.template ? [el("span", {
          class: "mmc-refined-model",
          text: refined.forced ? t("{template} (pinned)", { template: refined.template.toLowerCase() })
                               : refined.template.toLowerCase(),
          title: refined.forced
            ? t("Written with the {template} template you pinned in the refiner's "
              + "settings, not the one the attachments imply.", { template: refined.template })
            : t("Written with the {template} template, picked automatically from "
              + "what is attached.", { template: refined.template }),
        })] : []),
        ...(refined.skill ? [el("span", { class: "mmc-refined-model",
                                          text: t("skill: {skill}", { skill: refined.skill }),
                                          title: t("Written by this skill package rather than the "
                                               + "built-in prompts — the whole document, format included.") })] : []),
        ...(this.stale ? [el("span", {
          class: "mmc-refined-stale",
          text: t("prompt edited since"),
          title: t("Your prompt has changed since this was written. It still queues as it stands — "
               + "refine again to fold the change in."),
        })] : []),
        el("span", { style: { flex: "1" } }),
        el("button", {
          class: "mmc-ghost", text: t("Revert"),
          title: t("Throw the rewrite away and go back to your own prompt. The soundscape "
               + "and score it wrote go with it."),
          onclick: () => this.clear(),
        }),
      ]));

      // The one thing the panel never said, and the thing that decides what is
      // generated: the rewrite stands in for the prompt rather than joining it.
      parts.push(el("div", {
        class: "mmc-refined-lede",
        text: on
          ? t("Queued instead of the prompt above, not alongside it.")
          : t("Off — the prompt above is queued as you wrote it."),
      }));

      // What the model said was in the pictures, written before the rewrite so
      // that writing it had to happen first. Folded away, because when it is
      // right it says nothing new — and read the moment the rewrite describes a
      // scene that is not the one in your frames, which is the only way to tell
      // "it did not look" from "it looked and wrote badly".
      if (this.seen) {
        parts.push(el("details", { class: "mmc-refined-fold" }, [
          el("summary", { text: t("what the model saw in your images") }),
          el("div", { class: "mmc-refine-hint mmc-refined-seen", text: this.seen }),
        ]));
      }

      this.bodyBox = this.box(
        "body", refined.body,
        (value) => { const current = this.refined; if (current) current.body = value; },
        { rows: 8, placeholder: t("The rewritten description.") });
      parts.push(this.bodyBox);

      // Only the reference form has these, and only a refiner ever writes them —
      // they are the three sections nothing can derive from a sentence. Folded,
      // like the prompt the rewrite stands in for: three more textareas held
      // open under a rewrite this long is what doubled the node, and the summary
      // is what stops folding them reading as the references having been
      // dropped — it says where a @handle becomes the <Subject N> the shot
      // bodies speak in, so the answer is one click away rather than absent.
      if (refined.sections) {
        const sections = el("div", { class: "mmc-refined-sections" });
        for (const name of REF_SECTIONS) {
          sections.append(el("label", { class: "mmc-refined-section" }, [
            el("span", { class: "mmc-tl-field-name", text: name }),
            this.box(
              `section:${name}`, refined.sections[name],
              (value) => { const sections = this.refined?.sections; if (sections) sections[name] = value; },
              { rows: 3, className: "mmc-refined-box mmc-tl-small" }),
          ]));
        }
        parts.push(el("details", { class: "mmc-refined-fold" }, [
          el("summary", { text: t("reference analysis — where your @references are defined") }),
          sections,
        ]));
      }

    }

    if (this.audioFields && (refined || audio)) {
      parts.push(el("div", { class: "mmc-tl-audio" }, [
        el("label", { class: "mmc-tl-field" }, [
          el("span", { class: "mmc-tl-field-name", text: "overall_soundscape" }),
          this.box(
            "soundscape", state.soundscape,
            (value) => { this.getState().soundscape = value; },
            { rows: 3, className: "mmc-refined-box mmc-tl-small",
              placeholder: t("Everything heard in the room. Empty leaves it to the model; N/A is silence.") }),
        ]),
        el("label", { class: "mmc-tl-field" }, [
          el("span", { class: "mmc-tl-field-name", text: "non_diegetic_music" }),
          this.box(
            "music", state.music,
            (value) => { this.getState().music = value; },
            { rows: 3, className: "mmc-refined-box mmc-tl-small",
              placeholder: t("The score only the audience hears. Empty leaves it to the model.") }),
        ]),
      ]));
    }

    for (const problem of this.problems) {
      parts.push(el("div", { class: "mmc-warn", text: problem }));
    }
    this.root.replaceChildren(...parts);
  }
}

/**
 * The Refine control: one press does the thing, a corner opens its settings.
 *
 * The settings used to hang off the button as a floating badge, which put a
 * circle over the neighbouring rail tool and read as a notification rather than
 * as a way in. It is now inside the tile's own rounded box — the same split-
 * button idea, contained, so the rail keeps its alignment and nothing overlaps.
 *
 * `run` does the work and reports back; this only handles the two states the
 * button itself has — idle, and waiting on a model that may take a minute.
 */
export function refineButton({ run, label = "Refine", title, className = "mmc-tool" }) {
  let busy = false;
  const text = el("span", { text: t(label) });
  // The generation ticks ComfyUI's own progress channel once per token, under
  // the refiner's id — `refine_local.PROGRESS_ID` — so the button can count
  // tokens instead of promising vaguely. Best effort: with no event the label
  // just stays "Refining…".
  const onProgress = ({ detail }) => {
    if (detail?.prompt_id !== "minimax-creator-refine") return;
    text.textContent = `${t("Refining…")} ${detail.value}/${detail.max}`;
  };
  const button = el("button", {
    class: className,
    title: title || t("Rewrite this prompt into the expanded description H3 was trained to read, "
                  + "keeping everything you wrote and expanding it."),
    onclick: async () => {
      if (busy) return;
      busy = true;
      button.classList.add("busy");
      text.textContent = t("Refining…");
      api.addEventListener("progress", onProgress);
      try {
        await run();
      } finally {
        busy = false;
        button.classList.remove("busy");
        api.removeEventListener("progress", onProgress);
        text.textContent = t(label);
      }
    },
  }, [el("span", { class: "mmc-tool-icon" }, [icon("brain")]), text]);

  const more = el("button", {
    class: "mmc-refine-more",
    // The chosen model is what this opens onto, so it is what the tooltip
    // leads with — "Settings" would say less than the answer itself.
    title: chosenModel()
      ? t("{model} — click to change the model, template, language or sampling", { model: chosenModel() })
      : t("Choose a model"),
    onclick: (event) => {
      event.stopPropagation();
      openSettings(event.currentTarget, () => {
        more.title = chosenModel()
          ? t("{model} — click to change the model, template, language or sampling", { model: chosenModel() })
          : t("Choose a model");
      });
    },
  }, [icon("chevron", 12)]);

  // The rail draws a tile with the chevron in its corner; the timeline bar draws
  // a pill with the chevron on its end. Same two controls, told apart by which
  // shape the caller asked for.
  const pill = className.includes("mmc-pill");
  return el("div", { class: `mmc-refine-split${pill ? " pill" : ""}` }, [button, more]);
}
