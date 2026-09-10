// The Save as RefMod body: pick a picture or clip, say what it is of, save.
//
// The node has no sockets. What it saves is chosen here, from the same picker
// every other attachment uses, and the two questions a picture cannot answer
// for itself — what it is *of*, and whether to keep the whole picture or only
// the movement — are pills on the face. Everything else (resolution, the causal
// trim, the file format) is the node's business, not the user's.
//
// Follows `PreStageEditor`'s shape: a `state` object, a `root` element the node
// hosts, a `commit()` that writes the blob back through `onCommit`, and a
// `render()` that redraws from state. The blob lives in the hidden `refmod_data`
// widget.

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

import { el, icon } from "./dom.js";
import { stillUrl } from "./api.js";
import { VIDEO } from "./manifest.js";
import { openPicker } from "./picker.js";
import { t } from "./i18n.js";

// The sibling RefMod pack's own vocabulary for what a reference is of, and the
// same list the backend maps to `takes`. Kept in step by hand; an unknown type
// still seeds `full` server-side.
export const REFMOD_TYPES = ["generic", "identity", "pose_motion", "clothing",
                             "background", "style"];
export const REFMOD_CAPTURES = ["full", "motion"];

const TYPE_LABEL = {
  generic: "generic",
  identity: "a person",
  pose_motion: "movement",
  clothing: "clothing",
  background: "a place",
  style: "a look",
};

/** A blob -> the body's state, with every field clamped to a legal value. */
export function parseRefMod(raw) {
  let blob = {};
  try {
    blob = JSON.parse(raw || "{}") || {};
  } catch {
    blob = {};
  }
  if (typeof blob !== "object") blob = {};
  return {
    filename: typeof blob.filename === "string" ? blob.filename : "",
    kind: blob.kind === "video" ? "video" : "image",
    name: typeof blob.name === "string" ? blob.name : "",
    type: REFMOD_TYPES.includes(blob.type) ? blob.type : "generic",
    capture: blob.capture === "motion" ? "motion" : "full",
    vae: typeof blob.vae === "string" ? blob.vae : "",
  };
}

/** The body's state -> the blob the node reads. */
export function serializeRefMod(state) {
  return JSON.stringify({
    filename: state.filename || "",
    kind: state.kind === "video" ? "video" : "image",
    name: state.name || "",
    type: REFMOD_TYPES.includes(state.type) ? state.type : "generic",
    capture: state.capture === "motion" ? "motion" : "full",
    vae: state.vae || "",
  }, null, 2);
}

export class RefModBody {
  constructor({ state, onCommit, onSave }) {
    this.state = state;
    this.onCommit = onCommit;
    this.onSave = onSave;
    // `mmc-root` + `mmc-panel` are the editor's shared card/panel, so the node
    // wears the same surface as every other Continuity body.
    this.root = el("div", { class: "mmc-root" });
    // The VAE list is the server's, read once: the same files the Creator's
    // settings popover offers, so a node made here picks up a re-encoded VAE the
    // moment the piece does.
    this.vaeFiles = [];
    this.loadVaeFiles();
    this.render();
  }

  commit() {
    this.onCommit?.();
    this.render();
  }

  /** A blob that arrived after the body was built — a loaded workflow. */
  setState(state) {
    // Mutated, not replaced: the node's `onCommit`/`onSave` read `body.state`,
    // but keeping one object is the stronger guarantee — anything else holding
    // a reference to the state goes on seeing the truth.
    Object.assign(this.state, state);
    this.render();
  }

  /** The VAE files, and a default when the blob has not named one. */
  async loadVaeFiles() {
    let files = [];
    try {
      const response = await api.fetchApi("/continuity/models");
      const data = await response.json();
      files = data?.files?.vae ?? [];
    } catch {
      files = [];
    }
    this.vaeFiles = files;
    // A first guess only, and only when nothing is chosen: the default video
    // family's own filename needles, read off the served manifest the way
    // `state.js` reads them — so this file names no family and a renamed
    // checkpoint still lands. What the user picks afterwards is never
    // overwritten.
    if (!this.state.vae && files.length) {
      const hints = VIDEO.weights?.find((w) => w.id === "vae")?.hints ?? [];
      this.state.vae = files.find((name) =>
        hints.some((needle) => name.toLowerCase().includes(needle))) ?? files[0];
      this.onCommit?.();
    }
    this.render();
  }

  /** The media well: the picker, on the kind the chosen file already is. */
  async choose() {
    const chosen = await openPicker({
      kinds: ["image", "video"],
      kind: this.state.kind === "video" ? "video" : "image",
      single: true,
      capacity: () => ({ used: 0, max: 1, filesLeft: 1 }),
    });
    const pick = chosen?.[0];
    if (!pick || pick.path === this.state.filename) return;
    this.state.filename = pick.path;
    this.state.kind = pick.kind === "video" ? "video" : "image";
    // A name only if the user has not written one: the filename stem is a
    // better default than "my_reference", and rewriting a chosen name is worse
    // than leaving the default alone.
    if (!this.state.name) {
      this.state.name = String(pick.name || pick.path).replace(/\.[^./\\]+$/, "");
    }
    this.commit();
  }

  /** A labelled `<select>` over `options`, one row of the pill group. */
  select(label, value, options, onPick, render = (v) => v) {
    const control = el("select", {
      class: "mmc-ref-select",
      onchange: (event) => { onPick(event.target.value); this.commit(); },
    }, options.map((option) =>
      el("option", { value: option, selected: option === value, text: render(option) })));
    return el("div", { class: "mmc-pills" }, [
      el("span", { class: "mmc-pill", text: label }),
      control,
    ]);
  }

  render() {
    const state = this.state;
    const ready = Boolean(state.filename && state.name.trim());
    // A real still, not an icon: the well's whole job is to show what was
    // picked, and `stillUrl` is the one place that knows which route draws it
    // (a picture is `/view`, a clip is the server-decoded still). `image`/
    // `video` icons are only the empty state — a framed picture with a mountain
    // on it reads as a broken-image placeholder wherever it is used for real.
    const still = state.filename
      ? stillUrl({ path: state.filename, kind: state.kind })
      : null;
    const well = el("button", {
      class: "mmc-well",
      type: "button",
      title: t("Choose a picture or a clip to save as a reference"),
      onclick: () => this.choose(),
    }, [
      still
        ? el("img", { class: "mmc-asset-thumb", src: still, alt: state.filename,
                      loading: "lazy", style: { width: "100%", height: "auto",
                                                display: "block", borderRadius: "6px" } })
        : icon("gallery", 18),
      el("span", { class: "mmc-model-name", text: state.filename || t("Choose a picture or clip") }),
    ]);

    const name = el("input", {
      class: "mmc-ref-name",
      type: "text",
      value: state.name,
      placeholder: t("reference name"),
      spellcheck: "false",
      oninput: (event) => { state.name = event.target.value; this.onCommit?.(); },
    });

    this.root.replaceChildren(
      el("div", { class: "mmc-panel" }, [
        well,
        name,
        this.select(t("type"), state.type, REFMOD_TYPES,
                    (value) => { state.type = value; }, (v) => t(TYPE_LABEL[v] ?? v)),
        this.select(t("capture"), state.capture, REFMOD_CAPTURES,
                    (value) => { state.capture = value; }),
        // The settings row: the VAE, from the same list the Creator's popover
        // reads. A plain select rather than a popover — there is one control,
        // and a popover for one control is a second click for nothing.
        this.vaeFiles.length
          ? this.select(t("video VAE"), state.vae, this.vaeFiles,
                        (value) => { state.vae = value; })
          : el("div", { class: "mmc-warn",
              text: this.state.vae
                ? t("VAE: {name}", { name: this.state.vae })
                : t("No VAE files found — set one up in ComfyUI's models/vae folder.") }),
        el("button", {
          class: "mmc-btn mmc-btn-primary",
          type: "button",
          disabled: ready ? undefined : true,
          title: ready ? t("Save this reference and queue the node")
                       : t("Pick a file and give it a name first"),
          onclick: () => this.onSave?.(),
        }, [icon("weights", 14), el("span", { text: t("Save RefMod") })]),
      ]),
    );
  }
}
