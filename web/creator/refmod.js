// The Save as RefMod body: pick pictures and clips, say what it is of, save.
//
// The node has no sockets. What it saves is chosen here, from the same picker
// every other attachment uses — images, clips and finished Renders — and the
// two questions a picture cannot answer for itself — what it is *of*, and
// whether to keep the whole picture or only the movement — are pills on the
// face. Everything else (resolution, the causal trim, the file format) is the
// node's business, not the user's.
//
// Several files stack into one mod, the way the sibling extractor stacks a set
// of stills: a handful of photographs of one person, or a face from a still and
// a walk from a clip, become one reference the tokenizer is shown as one
// picture.
//
// Follows `PreStageEditor`'s shape: a `state` object, a `root` element the node
// hosts, a `commit()` that writes the blob back through `onCommit`, and a
// `render()` that redraws from state. The blob lives in the hidden `refmod_data`
// widget.

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

// How many files one mod may stack. A ceiling rather than a policy — a mod is a
// reference, and a hundred frames of one is a clip, not a moodboard.
export const REFMOD_MAX_FILES = 64;

const TYPE_LABEL = {
  generic: "generic",
  identity: "a person",
  pose_motion: "movement",
  clothing: "clothing",
  background: "a place",
  style: "a look",
};

/** One picked row -> the `{path, kind}` the blob stores. Renders are their own
 *  kind in the picker but a file is an image or a clip wherever it lives. */
const asFile = (picked) => ({
  path: picked.path,
  kind: picked.kind === "video" ? "video" : "image",
});

/** A blob -> the body's state, with every field clamped to a legal value. */
export function parseRefMod(raw) {
  let blob = {};
  try {
    blob = JSON.parse(raw || "{}") || {};
  } catch {
    blob = {};
  }
  if (typeof blob !== "object") blob = {};
  let files = [];
  if (Array.isArray(blob.files)) {
    files = blob.files
      .filter((file) => file && typeof file.path === "string" && file.path)
      .map((file) => ({ path: file.path, kind: file.kind === "video" ? "video" : "image" }));
  } else if (typeof blob.filename === "string" && blob.filename) {
    // A save from before this node stacked files: one `filename`/`kind` pair.
    files = [{ path: blob.filename, kind: blob.kind === "video" ? "video" : "image" }];
  }
  return {
    files,
    name: typeof blob.name === "string" ? blob.name : "",
    type: REFMOD_TYPES.includes(blob.type) ? blob.type : "generic",
    capture: blob.capture === "motion" ? "motion" : "full",
    vae: typeof blob.vae === "string" ? blob.vae : "",
  };
}

/** The body's state -> the blob the node reads. */
export function serializeRefMod(state) {
  return JSON.stringify({
    files: (state.files ?? []).filter((file) => file?.path).map(asFile),
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

  /** The media well: the picker, on images, clips and finished Renders. */
  async choose() {
    const first = this.state.files[0];
    const chosen = await openPicker({
      kinds: ["image", "video", "renders"],
      kind: first?.kind === "video" ? "video" : "image",
      // No reference cap here: this builds a file rather than taking a slot.
      capacity: () => ({ used: 0, max: REFMOD_MAX_FILES, filesLeft: REFMOD_MAX_FILES }),
    });
    if (!chosen?.length) return;
    this.state.files = chosen.slice(0, REFMOD_MAX_FILES).map(asFile);
    // A name only if the user has not written one: the first filename's stem is
    // a better default than "my_reference", and rewriting a chosen name is
    // worse than leaving the default alone.
    if (!this.state.name) {
      const pick = chosen[0];
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
    const first = state.files[0] ?? null;
    const ready = Boolean(state.files.length && state.name.trim());
    // A real still, not an icon: the well's whole job is to show what was
    // picked, and `stillUrl` is the one place that knows which route draws it
    // (a picture or a render is `/view`, a clip is the server-decoded still, a
    // RefMod is its own route).
    const still = first ? stillUrl({ path: first.path, kind: first.kind }) : null;
    const label = !first
      ? t("Choose pictures or clips")
      : state.files.length === 1
        ? first.path
        : t("{count} files", { count: state.files.length });
    const well = el("button", {
      class: "mmc-well",
      type: "button",
      title: t("Choose pictures and clips to save as one reference"),
      onclick: () => this.choose(),
    }, [
      still
        ? el("img", { class: "mmc-asset-thumb", src: still, alt: first.path,
                      loading: "lazy", style: { width: "100%", height: "auto",
                                                display: "block", borderRadius: "6px" },
                      onerror: (event) => event.target.replaceWith(icon("gallery", 18)) })
        : icon("gallery", 18),
      el("span", { class: "mmc-model-name", text: label }),
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
