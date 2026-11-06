// The room's *Thinks with* popover: the model that turns what you say into a
// prompt, and how it writes.
//
// One popover for everything about the writing, kept apart from everything
// about the drawing (the *Makes with* sheet in `chat.js`). The word "model"
// meant four things in this room — the thinker, the image family, the video
// family, the edit family — and "sampling" meant two: how a text model picks
// its next token and how a diffusion model picks its next step. Here the
// thinker is the only model, and the dial is called what it does.
//
// **The choice is the refiner's** (`refine.settings`), on purpose: the same
// backend, the same model, the same server card. A machine set up once for
// the node's Refine button is set up for its chats, and the other way round.
// What the refiner popover also carries — the per-mode templates, the
// prompting modes, the rewrite's language — is the rewrite's business and
// does not reach a chat turn (`chat.requestBlock` sends none of it), so none
// of it is drawn here. The verbosity dial and the skill are the room's own
// (`settings.chat`) and are drawn here because they are about the writing.
//
// **Only models that can chat are listed.** The refiner's list is every
// file under models/text_encoders, and half of those are the encoders the
// renders load — H3's 32B Qwen, LTX's Gemma, a CLIP-L, a T5 — which cannot
// hold a conversation or, worse, can, at a size nobody would choose. A file
// picked as some family's encoder in `settings.weights` is still offered,
// because it is a real choice on a small disk, but it says which family
// loads it; a file that is not a language model at all is left out.
import { el, icon, placeNear, dismissable } from "./dom.js";
import { openChoicePopover, stepperPill } from "./pills.js";
import { settings as refinerSettings, saveSettings as saveRefiner, chosenModel,
         listModels, listDevices, drawRemoteCard, remoteStatus, seedControl, takesSeed } from "./refine.js";
import { rememberedWeights } from "./models.js";
import { neuralSwitch } from "./neural.js";
import { FAMILIES } from "./manifest.js";
import { t } from "./i18n.js";

/** How many blocks of prompting the verbosity dial is cut into — `chat.TIERS`,
 *  held together by `tests/test_chat_mirror.py`. The dial itself is a number
 *  from 0 to 1, which is what is saved and sent; the server reads one block
 *  or none off it, and this is only so the readout can name the block. */
const VERBOSITY_TIERS = 3;

/** What the reply-length pill may be moved between. Mirrors
 *  `chat.MIN_REPLY_TOKENS` and `chat.MAX_REPLY_TOKENS`, which clamp it
 *  again server-side. */
const REPLY_TOKENS = { min: 256, max: 8192, step: 256 };

/** What each block is called beside the slider, bottom first. */
const TIER_NAMES = ["as written", "a little", "more", "rich"];

/** `chat.verbosity_tier`: the dial -> which block, 0 to `VERBOSITY_TIERS`. */
export function verbosityTier(dial) {
  if (!(dial > 0)) return 0;
  return Math.min(VERBOSITY_TIERS, Math.ceil(Math.round(dial * VERBOSITY_TIERS * 1e9) / 1e9));
}

/** Files under text_encoders that are not language models: an encoder alone,
 *  a projection, CLIP. Nothing here could answer a message. */
const NOT_A_THINKER = /(^|\/)(clip_[lg]|clip_vision|t5|umt5|flan-t5|.*projection|.*_vision)/i;

/** A model that can look at a picture, by the names the families use. A
 *  chat cites pictures, so this is the tag worth wearing. */
const READS_PICTURES = /vl|vision|llava/i;

/** The model's name as the pill says it: the file without its folder and
 *  its extension. The whole name is on the pill's title. */
export function thinkerName(current = refinerSettings()) {
  const model = chosenModel(current);
  if (!model) return "";
  return model.split("/").pop().replace(/\.(safetensors|gguf|bin|pt)$/i, "");
}

/** Which family's encoder a file is, by `settings.weights`, or "". */
function encoderOf(name) {
  const weights = rememberedWeights();
  for (const family of FAMILIES) {
    const block = weights[family.id];
    if (block && Object.values(block).includes(name)) return t(family.label);
  }
  return "";
}

/**
 * Open the popover under `anchor`.
 *
 * @param {object} doors
 *   `rail()` / `setRail(patch)` the room's rail (verbosity, skill);
 *   `skills` the names under the node's skills folder;
 *   `onChange()` the room repaints its header.
 */
export function openThinker(anchor, { rail, setRail, skills, onChange }) {
  const pop = el("div", { class: "mmc-pop mmc-ch-thinker" });
  const backendHost = el("div", { class: "mmc-refine-seg" });
  const modelHost = el("div", { class: "mmc-refine-models" });
  const deviceHost = el("div", { class: "mmc-ch-device-host" });
  const noteHost = el("div", { class: "mmc-refine-hint mmc-refine-note" });
  const writesHost = el("div", { class: "mmc-ch-writes" });

  const changed = () => { onChange?.(); drawWrites(); };

  /** In-process, or a server the user already runs. The popover's first
   *  decision; everything under it is that word's consequence. */
  function drawBackend() {
    const chosen = refinerSettings().backend === "remote" ? "remote" : "local";
    const half = (label, value, help) => el("button", {
      class: "mmc-refine-seg-btn",
      "aria-checked": value === chosen,
      text: t(label),
      title: t(help),
      onclick: () => {
        if (value === chosen) return;
        saveRefiner({ backend: value });
        changed(); drawBackend(); drawNote(); drawModels();
      },
    });
    backendHost.replaceChildren(
      half("this ComfyUI", "local",
           "A text encoder in ComfyUI's own process, loaded and evicted like any other model."),
      half("a server", "remote",
           "An OpenAI-compatible endpoint you already run — LM Studio, Ollama, "
           + "llama.cpp, vLLM — or a hosted API."),
    );
  }

  function drawNote() {
    noteHost.textContent = refinerSettings().backend === "remote"
      ? ""
      : t("It shares the card with your renders, so a reply waits behind whatever "
          + "is sampling. A server is the better setting on one GPU.");
  }

  /** The list, filtered to what can think, each with what it is beside it. */
  async function drawModels(force = false) {
    if (refinerSettings().backend === "remote") {
      deviceHost.replaceChildren();
      return drawRemoteCard(modelHost, changed, force);
    }
    modelHost.replaceChildren(el("div", { class: "mmc-refine-hint", text: t("Looking for models…") }));
    const available = await listModels({ force });
    const choices = await listDevices();
    const devices = choices.includes("default") ? choices : ["default", ...choices];
    const names = available.filter((name) => !NOT_A_THINKER.test(name));
    if (devices.length > 1) {
      const savedDevice = refinerSettings().chatDevice || "default";
      const selected = devices.includes(savedDevice) ? savedDevice : "default";
      deviceHost.replaceChildren(el("div", { class: "mmc-ch-device-line" }, [
        el("span", { class: "mmc-ch-k", text: t("LLM device") }),
        el("button", {
          class: "mmc-pill mmc-ch-value",
          text: selected === "default" ? t("ComfyUI default") : selected,
          title: t("Choose the device used to load the local chat model."),
          onclick: (event) => openChoicePopover(event.currentTarget, {
            title: t("Local LLM device"),
            options: devices,
            value: selected,
            label: (device) => device === "default" ? t("ComfyUI default") : device,
            onPick: (device) => {
              saveRefiner({ chatDevice: device === "default" ? "" : device });
              changed(); drawModels();
            },
          }),
        }),
      ]));
    } else deviceHost.replaceChildren();
    if (!names.length) {
      modelHost.replaceChildren(el("div", { class: "mmc-refine-empty" }, [
        el("div", { text: t("No model here can chat yet.") }),
        el("code", { text: "models/text_encoders/qwen3vl_4b.safetensors" }),
        el("button", { class: "mmc-ghost", text: t("Look again"), onclick: () => drawModels(true) }),
      ]));
      return;
    }
    const chosen = refinerSettings().model;
    modelHost.replaceChildren(el("div", { class: "mmc-refine-list" }, names.map((name) => {
      const tags = [];
      const encoder = encoderOf(name);
      if (encoder) tags.push(t("{family}'s encoder", { family: encoder }));
      if (READS_PICTURES.test(name)) tags.push(t("reads pictures"));
      return el("button", {
        class: "mmc-opt",
        "aria-checked": name === chosen,
        title: name,
        onclick: () => { saveRefiner({ model: name }); changed(); drawModels(); },
      }, [
        el("span", { class: "mmc-opt-label mmc-refine-name", text: name.split("/").pop() }),
        ...(tags.length ? [el("span", { class: "mmc-opt-kind", text: tags.join(" · ") })] : []),
        el("span", { class: "mmc-radio" }),
      ]);
    })));
  }

  /** One line: what it is, and the control. */
  const line = (label, control, title) => el("div", { class: "mmc-ch-line", title }, [
    el("span", { class: "mmc-ch-k", text: label }),
    el("span", { class: "mmc-ch-v" }, [control]),
  ]);

  /** The verbosity dial: how much the model may add to a prompt beyond what
   *  was said, 0 to 1, as a range with the name of the block it lands in
   *  beside it. The number is what is saved, so the blocks can be recut on
   *  the server without moving anybody's dial; the name is what the number
   *  means. Painted on every move, saved on release. */
  function verbosityRow() {
    const bar = rail();
    const name = el("span", { class: "mmc-ch-tier" });
    const slider = el("input", {
      type: "range", min: 0, max: 1, step: 0.05, value: Number(bar.verbosity) || 0,
      "aria-label": t("Verbosity"),
      // The graph canvas reads a pointerdown as the start of a drag.
      onpointerdown: (event) => event.stopPropagation(),
    });
    const paint = () => { name.textContent = t(TIER_NAMES[verbosityTier(Number(slider.value))]); };
    slider.addEventListener("input", paint);
    slider.addEventListener("change", () => { setRail({ verbosity: Number(slider.value) }); });
    paint();
    return line(t("Verbosity"), el("div", { class: "mmc-ch-verbosity" }, [slider, name]),
                t("How much the model may add to a prompt beyond what you said — the "
                  + "light, the lens, the textures, the sound — without changing what "
                  + "you meant. At the left it writes as it always has; each step up "
                  + "is a fuller block of prompting. A skill you append still wins."));
  }

  /** The room's own two, and the two dials of the thinker's that a chat
   *  turn reads. Redrawn whole on every change — nothing here holds a
   *  caret except the slider, which is rebuilt at its saved value. */
  function drawWrites() {
    const bar = rail();
    const current = refinerSettings();
    writesHost.replaceChildren(
      verbosityRow(),
      line(t("Skill"), el("button", {
        class: "mmc-pill mmc-ch-value", text: bar.skill || t("none"),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("Append to the room's prompting"),
          options: ["", ...skills().map((entry) => entry.name)],
          value: bar.skill || "",
          label: (name) => name || t("none"),
          onPick: (name) => { setRail({ skill: name }); drawWrites(); },
        }),
      }), t("A file from the node's skills folder, added to this room's own "
            + "prompting. It is only ever added: the room's reply contract is "
            + "what turns an answer into a render.")),
      line(t("Creativity"), stepperPill({
        value: Number(current.temperature), min: 0, max: 2, step: 0.05, width: "58px",
        format: (n) => n.toFixed(2),
        onChange: (next) => { saveRefiner({ temperature: next }); changed(); },
      }), t("The model's temperature. Lower keeps closer to your wording; higher "
            + "invents more around it. Cold keeps a small model on task.")),
      takesSeed(current)
        ? line(t("Seed"), seedControl(changed, {
          random: t("Every reply comes out differently. Click to fix it."),
          fixed: t("The same message gets the same reply. Click to vary it again."),
        }), t("Fixed, asking again gives the same answer and the same magic caption; "
              + "new every time, each ask is a fresh roll. Shared with the Refiner. "
              + "What a render samples on is another number, the room's own die."))
        : line(t("Seed"), el("span", { class: "mmc-refine-hint", text: t("this server takes none") }),
               t("Claude's API has no seed, so every reply is a fresh roll whatever is set here.")),
      line(t("Reply length"), (() => {
        const value = Number(bar.reply_tokens) || 1024;
        const readout = el("span", { class: "mmc-ch-token-count", text: t("{n} tokens", { n: value }) });
        const slider = el("input", {
          class: "mmc-ch-token-slider", type: "range",
          min: REPLY_TOKENS.min, max: REPLY_TOKENS.max, step: REPLY_TOKENS.step,
          value,
          "aria-label": t("Reply length"),
          onpointerdown: (event) => event.stopPropagation(),
          oninput: (event) => {
            const next = Number(event.currentTarget.value);
            readout.textContent = t("{n} tokens", { n: next });
          },
          onchange: (event) => setRail({ reply_tokens: Number(event.currentTarget.value) }),
        });
        return el("div", { class: "mmc-ch-token-control" }, [slider, readout]);
      })(), t("How many tokens a reply may run to. Lower this to reduce the local model's reserved generation memory; raise it if replies are being cut off.")),
      ...magicRows(bar),
    );
  }

  /** The magic prompt: a second reply that rewrites a still's prompt as the
   *  structured caption its family was trained on, in that family's own
   *  published instruction. Only Ideogram 4.0 has one, and the switch says
   *  so rather than hiding when the room is on another family — it is a
   *  standing choice, read whenever a still lands on one. The boxes only
   *  mean something with it on. */
  function magicRows(bar) {
    const rows = [line(t("Magic prompt"), neuralSwitch({
      on: bar.magic === true, label: t("Magic prompt"),
      onChange: (on) => { setRail({ magic: on }); drawWrites(); },
    }), t("For a picture on Ideogram 4.0, which reads a structured caption rather "
          + "than a sentence: Ideogram's own magic prompt turns the model's words "
          + "into that caption. A second reply, and a long one — it runs to the "
          + "refiner's reply length, not this one."))];
    if (bar.magic === true) {
      rows.push(line(t("Keep boxes"), neuralSwitch({
        on: bar.magic_bboxes === true, label: t("Keep boxes"),
        onChange: (on) => { setRail({ magic_bboxes: on }); drawWrites(); },
      }), t("Keep where the magic prompt places each element in the frame. Ideogram "
            + "drops them by default; kept, they pin the layout, and a box drawn "
            + "badly is where doubled or missing subjects come from.")));
    }
    return rows;
  }

  pop.append(
    el("div", { class: "mmc-refine-head" }, [
      el("span", { class: "mmc-pop-title", text: t("Thinks with") }),
      backendHost,
    ]),
    el("div", { class: "mmc-refine-hint mmc-ch-thinker-lead",
                text: t("Turns what you say into a prompt. The same choice as the node's "
                        + "Refine button, so it is set once.") }),
    modelHost,
    deviceHost,
    noteHost,
    el("div", { class: "mmc-ch-rule" }),
    writesHost,
  );

  document.body.appendChild(pop);
  placeNear(pop, anchor);
  dismissable(pop);
  drawBackend();
  drawNote();
  drawModels();
  drawWrites();
  // Whether the server takes a seed is its URL's to say, and that is a fetch
  // the first time round; drawn again once it is known.
  if (refinerSettings().backend === "remote") remoteStatus().then(() => drawWrites());
  return pop;
}
