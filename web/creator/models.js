// The weights control: one pill, one popover, six files.
//
// These were five sockets until the node stopped having any. They are
// configuration rather than composition — you set them once when you install the
// checkpoints and then never again — so they get one pill at the end of the
// sampler row rather than a row of their own, and the popover is where the six
// choices live.
//
// The pill is the only thing that changes shape: with everything picked it says
// what precision it is running at, and with a required file missing it says so
// in the same warm orange the resolution slider uses past 768. That is not a
// decoration — `models.check` refuses the render on exactly this list, and the
// difference between finding out here and finding out at queue time is a minute
// of your life.

import { el, icon, dismissable, placeNear } from "./dom.js";
import { t } from "./i18n.js";
import { openChoicePopover } from "./pills.js";
import { listModels, uiSetting, patchSettings } from "./api.js";
import * as S from "./state.js";
import { turboRow, loadLoraNames } from "./turbo.js";

// The two "not a filename" entries in the choice lists. Spelled out rather than
// left as an empty row, because a list whose first entry is blank reads as a
// rendering bug.
const NONE = "— none —";
const AUTO = "— auto —";

/** Said as an instruction rather than as a name: a route *is* a checkpoint
 *  field, and "always Ref2VA" is what choosing it does. The names are the
 *  manifest's; only "auto" has its own sentence. */
export const routeLabel = (route, family = S.DEFAULT_VIDEO_FAMILY) =>
  route === "auto" ? t("auto — follow the mode")
    : t("always {name}", { name: S.checkpointLabels(family)[route] ?? route });

// The listing, shared by every node body on the canvas. Fetched once and handed
// out synchronously afterwards, because the pill is re-rendered on every commit
// and an await in that path would make the row flicker.
let catalog = null;

/** Load the catalog if it is not already here. `onReady` runs only if this call
 *  is the one that fetched it, so a caller can re-render without every node on
 *  the canvas re-rendering for the same reason. */
export function loadCatalog(onReady) {
  if (catalog) return catalog;
  listModels().then((body) => {
    catalog = body;
    onReady?.(body);
  }).catch(() => {
    // A failed listing is an empty one: the pill says the folders are empty
    // rather than the node breaking over a route that did not answer.
    catalog = { files: {}, dtypes: S.MODEL_DTYPES, preview_override: false };
    onReady?.(catalog);
  });
  return catalog;
}

/** Ask again, and re-render when the answer differs from what is on screen.
 *
 * `loadCatalog` answers once and holds it for the life of the page, which is
 * right for a pill that redraws on every commit and wrong the moment a file is
 * copied into a model folder while the tab is open — the listing that never
 * expires is a file that can never be picked. Opening the popover is the one
 * moment the listing is being read rather than displayed, so that is where the
 * question is asked again. `listModels` has its own 60s window, so a run of
 * opens is one request. */
export function refreshCatalog(onChanged) {
  listModels().then((body) => {
    const same = JSON.stringify(body) === JSON.stringify(catalog);
    catalog = body;
    if (!same) onChanged?.(body);
  }).catch(() => {});           // a failed re-ask leaves what is already here
}

export const catalogFiles = () => catalog?.files ?? {};

/** The raw per-folder listings (`diffusion_models`, `text_encoders`, `vae`) —
 *  what the PreStage's weights control browses, since its fields do not map
 *  onto the video node's. */
export const catalogByFolder = () => catalog?.by_folder ?? {};

/** Every device ComfyUI-MultiGPU offers, or `[]` when it is not installed —
 *  which is what the device control keys off. No pack, no control, rather than
 *  a control offering one choice that does nothing. */
export const catalogDevices = () => catalog?.devices ?? [];

/** Whether KJNodes' preview override is installed. The preview decoder is the
 *  one field that needs somebody else's pack, and a control that cannot do
 *  anything should say why rather than look broken. */
export const hasPreviewOverride = () => catalog?.preview_override !== false;

/**
 * The pill. Reports first and configures second, which is the right way round
 * for something you look at far more often than you change.
 *
 * @param {object} spec
 * @param {object} spec.piece       the piece whose weights these are. Read for
 *   one thing and it decides every other: which family the piece renders with,
 *   and so which slots exist, what they are called, whether there is a route to
 *   force and whether a checkpoint can be idle. Every constant this control used
 *   to read was the default family's, which was right for exactly as long as
 *   there was one family.
 * @param {object} spec.models       the state's weights block, mutated in place
 * @param {string[]} spec.checkpoints the checkpoints the *modes* derive; a
 *   forced route collapses this to one, so it is passed raw and resolved here
 * @param {boolean} [spec.face]     whether a pass in this render runs the face
 *   pass, which is what decides whether the detector counts as missing
 * @param {() => void} spec.onChange after a pick
 * @param {object} [spec.turbo]      `{container, widgetIO}` — the state or
 *   timeline that owns the turbo switch, and the widget IO the switch writes
 *   through when its file is swapped while engaged. Absent, no turbo row.
 */
export function weightsPill({ piece, models, checkpoints, onChange, turbo, face = false }) {
  const family = S.pieceFamily(piece);
  const label_ = S.modelLabels(family);
  const routed = S.routedCheckpoints(models, checkpoints);
  // Both sets at once, as labels rather than slot ids: a piece finishing
  // through an upscale backend loads that backend's files too, and a pill that
  // counted only the family's would read "weights" over a render the queue is
  // about to refuse. The ids cannot be merged — four of the backend's are the
  // family's own spelled the same way — but the labels are what is shown.
  const missing = [
    ...S.missingModels(models, S.requiredModels(routed, face, family), family)
      .map((field) => t(label_[field])),
    ...missingUpscalerLabels(piece),
  ];
  // What the pill reports when everything is picked, in order of how much it
  // changes about the run: which cards it is spread over first, then precision,
  // then nothing worth saying.
  const spread = new Set(S.deviceFields(family).map((f) => models.devices[f]).filter(Boolean));
  const settled = models.route !== "auto"
    ? t("weights · always {checkpoint}", { checkpoint: S.checkpointLabels(family)[models.route] })
    : spread.size
      ? (spread.size > 1
          ? t("weights · {count} devices", { count: spread.size })
          : t("weights · {device}", { device: [...spread][0] }))
      : models.dtype === "default" ? t("weights") : t("weights · {dtype}", { dtype: models.dtype.replace("fp8_", "fp8 ") });
  const label = missing.length
    ? (missing.length === 1
        ? t("no {model}", { model: missing[0].toLowerCase() })
        : t("{count} weights missing", { count: missing.length }))
    : settled;

  return el("button", {
    class: `mmc-pill mmc-weights${missing.length ? " missing" : ""}`,
    title: missing.length
      ? t("Not picked yet: {models}. The render is refused without them.", {
          models: missing.join(", "),
        })
      : t("Which checkpoints, text encoder and VAEs this node loads."),
    onclick: (event) => openWeightsPopover(event.currentTarget,
      { piece, models, checkpoints, onChange, turbo, face }),
  }, [icon("weights", 16), el("span", { text: label })]);
}

/**
 * The upscale backend's slots this piece has not filled, as labels.
 *
 * Empty unless the piece is actually finishing through a backend: these files
 * are a second family's, they are only loaded by that pass, and a pill
 * reporting them missing on a render that never reaches them would be asking
 * for a 21.5 GB download nothing was going to open.
 */
function missingUpscalerLabels(piece) {
  const backend = S.upscalerOf(piece);
  if (!backend) return [];
  const picked = piece.upscale_models ?? {};
  return S.upscalerFields(backend, S.pieceFamily(piece))
    .filter((id) => !picked[id])
    // Qualified, because the popover's group heading is not here to do it: the
    // backend's rows are called "Transformer" and "Text encoder" under a
    // heading that says ReDetail, and both names also belong to the family's
    // own slots. In a flat list they have to carry it themselves.
    .map((id) => t("{backend} {model}", {
      backend: t(backend.label),
      model: t(backend.weights.find((slot) => slot.id === id).title).toLowerCase(),
    }));
}

/**
 * Which architecture renders the piece — the pill that leads the piece's row.
 *
 * It used to sit in the sampler row, in front of the weights, because the
 * weights are an answer to it: the slots in that popover are the family's, and
 * so are the checkpoints the routing pill cycles. But the sampler row is behind
 * a disclosure, and the family is not a sampler setting — it decides what every
 * pill above the row *means*: the routes, the frame step, the lengths a
 * duration head can be asked for. A choice nothing else in the body reads
 * without cannot be the one thing you have to open a panel to find, so it leads
 * the row that answers "what is this render", on every surface that has one —
 * the shot's, the strip's bar, the pre-stage's, which spells it as its own
 * architecture pill. The weights stay on the sampler row: they are file paths,
 * set once when a checkpoint is installed.
 *
 * A property of the piece and not of a card, like the canvas: the segments are
 * concatenated at the end and cannot come out of two architectures. Static
 * while there is only one family installed — a choice of one is a readout, and
 * a popover that can only confirm what the pill already says is a click that
 * does nothing.
 *
 * @param {object} spec
 * @param {object} spec.piece     the timeline or lone-shot piece; `setFamily`
 *   rewrites its family-shaped fields in place
 * @param {() => void} spec.onChange after a switch that changed something
 */
export function familyPill({ piece, onChange }) {
  const id = S.pieceFamily(piece);
  const label = (which) => t(S.FAMILY_LABEL[which]);
  // The description is the family's own, off its manifest — a translation key
  // like any string written in source.
  const says = t(S.FAMILY_DESCRIPTION[id]);
  const body = [icon("model", 16),
                el("span", { class: "mmc-model-name", text: label(id) })];

  // A choice of one is a readout, so it is drawn as one — the static pill the
  // strip face uses, not a disabled button. `:disabled` is the unavailable
  // look, and a control greyed out for having nothing to offer reads as broken.
  if (S.VIDEO_FAMILIES.length < 2) {
    return el("span", { class: "mmc-pill mmc-pill-static mmc-pill-model", title: says }, body);
  }
  return el("button", {
    class: "mmc-pill mmc-pill-model",
    title: says + "\n" + t("Click to render this piece with another architecture. The "
      + "prompt, the cast and the strip stay; the turbo switch and every "
      + "checkpoint pin are the family's and are reset. The weights are not "
      + "lost — each family's files are remembered and come back with it."),
    onclick: (event) => openChoicePopover(event.currentTarget, {
      title: t("Video model"),
      options: S.VIDEO_FAMILIES.map(label),
      value: label(id),
      onPick: (picked) => {
        const next = S.VIDEO_FAMILIES.find((which) => label(which) === picked);
        // The machine's memory is the fallback the piece's own stash does not
        // cover: the first time this piece is switched to a family there is
        // nothing set aside for it, and the files are still the same six on
        // this disk as the last node that picked them.
        if (!next || !S.setFamily(piece, next, rememberedWeights())) return;
        // Nothing set aside and nothing remembered for the family being
        // switched to: the folder listing is the last thing left that knows
        // anything about its files.
        adoptWeights(piece);
        onChange?.();
      },
    }),
  }, body);
}

/**
 * The weights this machine last picked, by family — `settings.weights`.
 *
 * Which files are on this disk is a property of the machine, not of a piece:
 * one person's `models/` is the same six answers whatever workflow is open, and
 * re-picking them for every new node (and every trip between two families) is
 * the chore this remembers away. The piece's own block still wins — it is what
 * the blob says the render used — and this only fills what nothing has said.
 *
 * Stored beside the lead-in for the same reason it is: per-machine, one file,
 * written straight through rather than by a settings page nobody would think to
 * open for this.
 */
const rememberedWeights = () => uiSetting("weights", {}) ?? {};

/**
 * Fill a piece's empty weight rows from what is already known. -> changed.
 *
 * Two answers, best first: what this machine last picked for the family, then
 * an unambiguous filename match in the folder listing. Both only ever fill an
 * empty row, so neither can talk over a piece that says what it rendered on.
 *
 * The rescue every node body runs once its catalog and settings have landed,
 * and what a family switch falls back to when neither the piece's stash nor the
 * machine's memory has heard of the family being switched to.
 */
export function adoptWeights(piece) {
  const family = S.pieceFamily(piece);
  const remembered = S.adoptRemembered(piece.models, rememberedWeights(), family);
  const guessed = S.guessModels(piece.models, catalogFiles(), family);
  return remembered || guessed;
}

/** Record this family's block as the machine's, after a pick. Fire and forget:
 *  the piece already has the answer, and a memory that failed to write is next
 *  time's problem rather than this click's. */
function rememberWeights(family, models) {
  const block = S.serializedModels(models, family);
  patchSettings({ weights: { ...rememberedWeights(), [family]: block } });
}

/**
 * A row per file, each opening the list for its folder.
 *
 * Rebuilt in place after every pick rather than closed: setting up a machine
 * means setting all six, and closing the popover between each one would make
 * that six round trips through a pill.
 */
export function openWeightsPopover(anchor, { piece, models, checkpoints, onChange, turbo, face = false }) {
  const pop = el("div", { class: "mmc-pop mmc-weights-pop" });
  const body = el("div");

  // Every list, label and hint below is this family's. Read once, at the top:
  // the popover is rebuilt in place after each pick, and the family cannot
  // change under it — the family pill is outside this popover, and switching
  // families closes it.
  const family = S.pieceFamily(piece);
  // Every pick of the family's own files is also this machine's answer about
  // them, so it is remembered as one: the next node, and the next switch back
  // to this family, start from what was chosen here rather than from six empty
  // rows. The backend's slots and the turbo file below are not the family's and
  // go through `onChange` alone.
  const commit = () => { rememberWeights(family, models); onChange(); };
  const fields = S.modelFields(family);
  const label_ = S.modelLabels(family);
  const hint_ = S.modelHints(family);
  const deviceFields = S.deviceFields(family);
  const routes = S.routeOptions(family);
  const routedSlots = S.checkpointsOf(family);

  // Recomputed inside `render` rather than captured: forcing a route changes
  // which of the two checkpoints is required, and that has to show on the row
  // the moment the route above it is picked.
  const required = () => new Set(S.requiredModels(
    S.routedCheckpoints(models, checkpoints), face, family));

  const render = () => {
    const files = catalogFiles();
    const devices = catalogDevices();

    // Leads the popover, because it decides which of the two checkpoints below
    // it are used at all. Forced, the other one is never loaded and never
    // required — which is also why `required` is recomputed on every pick.
    // Absent for a family that ships one transformer. A route is a standing
    // choice *among* a family's checkpoints, and a control offering one option
    // lies about what it does.
    const routeRow = !S.routing(family) ? null : el("div", { class: "mmc-weight-row" }, [
      el("span", { class: "mmc-weight-name", text: t("Route") }),
      el("button", {
        class: `mmc-weight-file${models.route === "auto" ? "" : " forced"}`,
        title: t("Which checkpoint every generation runs on.\n\n"
             + "auto follows the mode: references go to Ref2VA, everything else to FL2VA.\n"
             + "Forced, that is ignored and one checkpoint takes the lot — the two are one "
             + "architecture trained twice, and Ref2VA handles text-only and keyframe "
             + "payloads perfectly well.\n\n"
             + "FL2VA cannot take references at all, so forcing it is refused on a "
             + "generation that has any."),
        text: routeLabel(models.route, family),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("Route"),
          options: routes.map((route) => routeLabel(route, family)),
          value: routeLabel(models.route, family),
          onPick: (picked) => {
            models.route = routes.find(
              (route) => routeLabel(route, family) === picked) ?? "auto";
            commit();
            render();
          },
        }),
      }),
    ]);

    /**
     * Where one field's weights are loaded. Only drawn when ComfyUI-MultiGPU is
     * installed: with one card there is nothing to choose, and a control whose
     * only option is the default is a control that lies about what it does.
     *
     * A button of its own rather than part of the row, because the row is
     * already a button and nesting two is invalid — and because these are two
     * different questions about the same file.
     */
    const devicePill = (field) => {
      if (!devices.length || !deviceFields.includes(field)) return null;
      const pinned = models.devices[field] || "";
      return el("button", {
        class: `mmc-weight-device${pinned ? " pinned" : ""}`,
        title: pinned
          ? t("Loaded on {device}, through ComfyUI-MultiGPU.", { device: pinned })
          : t("Loaded wherever ComfyUI would put it. Pick a device to pin it — "
            + "putting the text encoder on a second card frees the first one for the DiT."),
        text: pinned || t("auto"),
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("{model} — device", { model: t(label_[field]) }),
          options: [t(AUTO), ...devices],
          value: pinned || t(AUTO),
          onPick: (picked) => {
            if (picked === t(AUTO)) delete models.devices[field];
            else models.devices[field] = picked;
            commit();
            render();
          },
        }),
      });
    };

    const needed = required();
    const rows = fields.map((field) => {
      const chosen = models[field];
      const options = files[field] ?? [];
      // The preview is the one field that also needs a pack. Say which half is
      // absent — "no files" and "no node to read them with" have different fixes.
      const unavailable = field === "preview" && !hasPreviewOverride();

      return el("div", {
        class: `mmc-weight-row${needed.has(field) && !chosen ? " missing" : ""}`
             // A checkpoint the route has taken out of play: still listed, so
             // the setting is not thrown away, but visibly out of the run — the
             // same treatment an idle LoRA gets.
             + (routedSlots.includes(field) && !needed.has(field) ? " idle" : ""),
      }, [
        el("span", { class: "mmc-weight-name", text: t(label_[field]) }),
        el("button", {
          class: `mmc-weight-file${chosen ? "" : " empty"}`,
          title: unavailable
            ? t("Needs KJNodes' Model Preview Override — the node that draws the live "
              + "preview at all. Without the pack there is none; the render is "
              + "unaffected either way.")
            : t(hint_[field]),
          // The tail of a folder-qualified name is the part that identifies it;
          // the button ellipsises from the left so that is what survives.
          text: chosen || (unavailable ? t("unavailable") : t("not set")),
          onclick: (event) => openChoicePopover(event.currentTarget, {
            title: t(label_[field]),
            // "none" is a real answer for the optional fields and for a
            // checkpoint this graph does not route to, so it is offered rather
            // than only reachable by clearing the blob by hand.
            options: [t(NONE), ...options],
            value: chosen || t(NONE),
            onPick: (picked) => {
              models[field] = picked === t(NONE) ? "" : picked;
              commit();
              render();
            },
          }),
        }),
        devicePill(field),
      ]);
    });

    // One precision for both checkpoints — they are the same architecture, and
    // two controls would imply a choice nobody has.
    rows.push(el("div", { class: "mmc-weight-row" }, [
      el("span", { class: "mmc-weight-name", text: t("Precision") }),
      el("button", {
        class: "mmc-weight-file",
        title: t("How the checkpoints are loaded. fp8 halves the weights in VRAM at "
             + "some cost in fidelity; 'default' loads them as they were saved. "
             + "GGUF files ignore this — their precision was baked in when they "
             + "were quantized."),
        text: models.dtype,
        onclick: (event) => openChoicePopover(event.currentTarget, {
          title: t("Precision"),
          options: catalog?.dtypes ?? S.MODEL_DTYPES,
          value: models.dtype,
          onPick: (picked) => { models.dtype = picked; commit(); render(); },
        }),
      }),
    ]));

    // The upscale backend's own files, in a group of their own under the
    // family's. A group and not a mixed-in row, because that is what they are:
    // a second architecture's weights, loaded for one pass at the end of the
    // render, and a user picking an LTX transformer on an H3 piece should be
    // able to see that is what they are doing. Only where the piece is actually
    // finishing through one — otherwise the pass never runs and the rows would
    // be asking for files nothing opens.
    const backend = S.upscalerOf(piece);
    if (backend) {
      const picked = piece.upscale_models ?? (piece.upscale_models = {});
      const backendFields = S.upscalerFields(backend, family);
      const shared = backend.shares_with === family;
      rows.push(
        el("div", { class: "mmc-weight-group" }, [
          el("span", { class: "mmc-weight-group-name", text: t(backend.label) }),
          el("span", { class: "mmc-weight-group-note",
                       text: shared
                         ? t("runs on this piece's own weights")
                         : t("a second architecture, for the finishing pass") }),
        ]),
        ...backendFields.map((id) => {
          const slot = backend.weights.find((entry) => entry.id === id);
          const chosen = picked[id] ?? "";
          return el("div", {
            class: `mmc-weight-row${chosen ? "" : " missing"}`,
          }, [
            el("span", { class: "mmc-weight-name", text: t(slot.title) }),
            el("button", {
              class: `mmc-weight-file${chosen ? "" : " empty"}`,
              title: t(slot.help),
              text: chosen || t("not set"),
              onclick: (event) => openChoicePopover(event.currentTarget, {
                title: t(slot.title),
                options: [t(NONE), ...(files[id] ?? [])],
                value: chosen || t(NONE),
                onPick: (choice) => {
                  if (choice === t(NONE)) delete picked[id];
                  else picked[id] = choice;
                  onChange();
                  render();
                },
              }),
            }),
          ]);
        }));
    }

    // The turbo switch's file, under the files it runs beside. Configuration
    // like everything above it — the throwing happens on the sampler row. Only
    // where the family declares one: a distillation LoRA is a thing a
    // particular set of weights has, and asking a family that has none to pick
    // a file for it would be offering a row nothing reads.
    if (turbo && S.turboOf(family)) {
      rows.push(turboRow({
        container: turbo.container,
        widgetIO: turbo.widgetIO,
        onChange: () => { onChange(); render(); },
      }));
    }

    body.replaceChildren(...(routeRow ? [routeRow] : []), ...rows);
  };

  pop.append(el("div", { class: "mmc-pop-title", text: t("Weights") }), body);
  render();
  document.body.appendChild(pop);
  placeNear(pop, anchor);
  dismissable(pop);

  // The catalog may not have arrived yet on a freshly loaded page. Re-render
  // rather than block: the rows are meaningful without it — they say what is
  // picked — and the file lists fill in behind them. The LoRA names likewise,
  // fetched here rather than at load because only this popover wants them.
  if (catalog) refreshCatalog(() => pop.isConnected && render());
  else loadCatalog(() => pop.isConnected && render());
  if (turbo && S.turboOf(family)) loadLoraNames(() => pop.isConnected && render());
}
