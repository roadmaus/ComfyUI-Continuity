// The LoRA detail sheet: double-click on a manager card.
//
// Two deliberately different shapes, because the two kinds of file know
// different things about themselves. A LoRA some tool has described opens
// showcase-first — big media, a filmstrip, and under the selected image the
// generation recipe that was recorded for it, which is the closest thing to an
// answer to "how do I prompt this". A LoRA nothing has described opens as a
// spec sheet read from the safetensors header itself: trainer, rank, precision,
// training run, and (for kohya-trained files) the dataset's tag frequency,
// which is the closest thing such a file has to trigger words.
//
// Which tool wrote what is not this file's business. `lorameta.py` merges every
// sidecar it found into one record under this pack's own field names, and names
// its sources at the bottom of the sheet — which is the one place it matters,
// because "where did this title come from" is a question only asked when the
// title looks wrong.

import { el, ICONS, svg, mountOverlay } from "./dom.js";
import { loraDetail, loraShowcaseUrl } from "./api.js";
import { t } from "./i18n.js";

/** Open the sheet for one listing row. Resolves when it closes. */
export function openLoraDetail(row) {
  return new Promise((resolve) => {
    new LoraDetailSheet(row, resolve).mount();
  });
}

// What each of `lorameta.PROVIDERS` is called on the sheet. Named after the file
// on disk rather than after the tool wherever the file is the recognisable part:
// somebody looking at why a title is wrong is going to go looking in the folder.
const SOURCE_LABEL = {
  civimeta: "CiviMeta sidecar",
  loramanager: ".metadata.json",
  civitai_info: ".civitai.info",
  a1111: ".json / .txt",
  header: "safetensors header",
  loose: "preview file",
};

// ---- formatting -------------------------------------------------------------

function fmtBytes(size) {
  if (!Number.isFinite(size) || size <= 0) return null;
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(2)} GB`;
  return `${Math.round(size / 1024 ** 2)} MB`;
}

function fmtCount(value) {
  if (!Number.isFinite(value)) return null;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  return String(value);
}

function fmtDate(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString();
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// ---- description HTML -------------------------------------------------------

// A description is HTML straight from Civitai, or plain text somebody typed
// into a `.txt` beside the file. Only this structural subset survives; anything
// else is unwrapped to its text, which is also what makes plain text safe to
// send through here. No images and no iframes: a detail sheet must not phone
// remote hosts on open.
const SAFE_TAGS = new Set([
  "P", "BR", "UL", "OL", "LI", "STRONG", "B", "EM", "I", "U", "S",
  "CODE", "PRE", "BLOCKQUOTE",
]);

function sanitize(html) {
  const doc = new DOMParser().parseFromString(String(html), "text/html");
  const frag = document.createDocumentFragment();
  const walk = (source, out) => {
    for (const node of source.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        out.appendChild(document.createTextNode(node.nodeValue));
        continue;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) continue;
      const tag = node.tagName;
      if (tag === "SCRIPT" || tag === "STYLE" || tag === "IFRAME") continue;
      if (/^H[1-6]$/.test(tag)) {
        // Civitai authors headline freely; in a 340px column they all become
        // one bold paragraph size or the type scale belongs to the description.
        const heading = el("p", { class: "mmc-sheet-h" });
        walk(node, heading);
        out.appendChild(heading);
        continue;
      }
      if (tag === "A") {
        const href = node.getAttribute("href") || "";
        if (/^https?:\/\//i.test(href)) {
          const anchor = el("a", { href, target: "_blank", rel: "noopener noreferrer" });
          walk(node, anchor);
          out.appendChild(anchor);
          continue;
        }
        walk(node, out);
        continue;
      }
      if (!SAFE_TAGS.has(tag)) {
        walk(node, out);   // unknown structure keeps its words
        continue;
      }
      const copy = document.createElement(tag.toLowerCase());
      walk(node, copy);
      out.appendChild(copy);
    }
  };
  walk(doc.body, frag);
  return frag;
}

// ---- the safetensors header, interpreted ------------------------------------

/**
 * The spec rows the header supports, as [label, value] pairs. Two trainer
 * dialects are understood: ai-toolkit writes JSON-in-string values (`software`,
 * `training_info`), kohya's sd-scripts writes flat `ss_*` keys.
 */
function headerFacts(header, size) {
  const md = header?.metadata || {};
  const software = parseJson(md.software);
  const training = parseJson(md.training_info);
  const rows = [];
  const push = (label, value) => { if (value) rows.push([label, String(value)]); };

  if (software?.name) push("Trainer", `${software.name} ${software.version || ""}`.trim());
  else if (Object.keys(md).some((key) => key.startsWith("ss_"))) push("Trainer", "kohya sd-scripts");
  push("Base model", md.ss_base_model_version || md.ss_sd_model_name);
  // Labels stay English here; they are translated where they are rendered
  // (and filtered against in fileFacts by their English spelling).
  const rank = header?.ranks?.length ? header.ranks.join(" / ") : md.ss_network_dim;
  const alpha = md.ss_network_alpha;
  push("Rank", rank && (alpha ? `${rank} · α ${alpha}` : String(rank)));
  const dtypes = Object.keys(header?.dtypes || {});
  push("Precision", dtypes.join(" + "));
  push("Tensors", header?.tensors);
  const steps = training?.step ?? md.ss_steps ?? md.ss_max_train_steps;
  const epoch = training?.epoch ?? md.ss_epoch ?? md.ss_num_epochs;
  push("Trained", [
    steps && t("{steps} steps", { steps: fmtCount(Number(steps)) ?? steps }),
    epoch && t("epoch {epoch}", { epoch }),
  ].filter(Boolean).join(" · "));
  push("Resolution", md.ss_resolution);
  push("Dataset", md.ss_num_train_images && t("{count} images", { count: md.ss_num_train_images }));
  push("Learning rate", md.ss_learning_rate);
  const hash = md.sshs_model_hash || md.ss_new_sd_model_hash;
  push("Hash", hash && String(hash).slice(0, 12));
  push("File size", fmtBytes(size));
  return rows;
}

/**
 * kohya's ss_tag_frequency: {dataset: {tag: count}} — the words the training
 * captions actually used, which for a sidecar-less LoRA is the best available
 * stand-in for trigger words. Aggregated across datasets, most frequent first.
 */
function tagFrequency(metadata) {
  const sets = parseJson(metadata?.ss_tag_frequency);
  if (!sets || typeof sets !== "object") return [];
  const totals = new Map();
  for (const tags of Object.values(sets)) {
    if (!tags || typeof tags !== "object") continue;
    for (const [tag, count] of Object.entries(tags)) {
      if (Number.isFinite(count)) totals.set(tag, (totals.get(tag) || 0) + count);
    }
  }
  return [...totals.entries()].sort((a, b) => b[1] - a[1]);
}

// ---- the sheet --------------------------------------------------------------

class LoraDetailSheet {
  constructor(row, resolve) {
    this.row = row;
    this.resolve = resolve;
    this.current = 0;   // which showcase item the stage shows
  }

  mount() {
    this.sheet = el("div", { class: "mmc-sheet" }, [
      el("div", { class: "mmc-sheet-info" }, [el("div", { class: "mmc-empty", text: t("Loading…") })]),
    ]);
    this.overlay = el("div", {
      class: "mmc-overlay",
      onpointerdown: (event) => { if (event.target === this.overlay) this.close(); },
    }, [this.sheet]);
    this.unmount = mountOverlay(this.overlay, () => this.close());
    this.load();
  }

  async load() {
    try {
      this.detail = await loraDetail(this.row.name);
    } catch (error) {
      this.detail = { error: error.message };
    }
    if (!this.overlay.isConnected) return;
    this.render();
  }

  close() {
    this.unmount();
    this.resolve();
  }

  render() {
    const detail = this.detail;
    if (detail.error) {
      this.sheet.replaceChildren(el("div", { class: "mmc-sheet-info" }, [
        this.closeButton(),
        el("div", { class: "mmc-empty", text: t("Could not read this LoRA: {error}", { error: detail.error }) }),
      ]));
      return;
    }
    const showcase = detail.showcase || [];
    this.sheet.classList.toggle("bare", !showcase.length);
    this.sheet.replaceChildren(
      ...(showcase.length ? [this.stage(showcase)] : []),
      detail.meta ? this.metaInfo() : this.headerInfo(),
    );
  }

  closeButton() {
    return el("button", { class: "mmc-close mmc-sheet-close", text: "✕", onclick: () => this.close() });
  }

  // ---- left pane: showcase -------------------------------------------------

  stage(showcase) {
    this.stageMedia = el("div", { class: "mmc-sheet-media" });
    this.recipeBox = el("div", { class: "mmc-sheet-recipe" });
    const strip = showcase.length > 1
      ? el("div", { class: "mmc-sheet-strip" }, showcase.map((item, index) => this.stripCell(item, index)))
      : null;
    this.stripCells = strip ? [...strip.children] : [];
    this.showItem(this.current);
    return el("div", { class: "mmc-sheet-stage" }, [this.stageMedia, strip, this.recipeBox]);
  }

  stripCell(item, index) {
    const cell = el("button", {
      class: "mmc-sheet-thumb",
      "aria-selected": index === this.current,
      onclick: () => this.showItem(index),
    });
    if (item.kind === "video" && !item.thumb) {
      // A video showcase has no generated thumbnail; the media-fragment trick
      // the manager's cards use paints its first usable frame instead.
      const video = el("video", { muted: true, playsInline: true, preload: "metadata" });
      video.src = `${loraShowcaseUrl(this.row.name, item.index)}#t=0.12`;
      cell.appendChild(video);
    } else {
      cell.appendChild(el("img", {
        src: loraShowcaseUrl(this.row.name, item.index, { thumb: true }),
        loading: "lazy", alt: "",
      }));
    }
    return cell;
  }

  showItem(index) {
    const item = (this.detail.showcase || [])[index];
    if (!item) return;
    this.current = index;
    this.stripCells.forEach((cell, at) => cell.setAttribute("aria-selected", String(at === index)));
    const source = loraShowcaseUrl(this.row.name, item.index);
    this.stageMedia.replaceChildren(item.kind === "video"
      ? el("video", { src: source, controls: true, loop: true, muted: true, autoplay: true, playsInline: true })
      : el("img", { src: source, alt: "" }));
    this.renderRecipe(item.meta);
  }

  /** The generation settings recorded for the shown image — the sheet's whole
   *  reason to exist. Absent metadata leaves the strip empty rather than
   *  padding it with dashes. */
  renderRecipe(meta) {
    if (!meta) {
      this.recipeBox.replaceChildren();
      this.recipeBox.classList.remove("on");
      return;
    }
    this.recipeBox.classList.add("on");
    const facts = [
      meta.seed != null && ["seed", String(meta.seed)],
      meta.steps != null && ["steps", String(meta.steps)],
      meta.cfg != null && ["cfg", String(meta.cfg)],
      meta.sampler && ["sampler", String(meta.sampler)],
      meta.scheduler && ["sched", String(meta.scheduler)],
    ].filter(Boolean);
    const children = [];
    if (facts.length) {
      children.push(el("div", { class: "mmc-sheet-recipe-facts" }, facts.map(([label, value]) =>
        el("span", {}, [
          el("span", { class: "mmc-sheet-recipe-k", text: t(label) }),
          " ",
          el("span", { class: "mmc-sheet-recipe-v", text: value }),
        ]))));
    }
    if (meta.prompt) {
      children.push(el("div", { class: "mmc-sheet-prompt" }, [
        el("div", { class: "mmc-sheet-prompt-text", text: meta.prompt, title: meta.prompt }),
        this.copyButton(meta.prompt),
      ]));
    }
    if (meta.negative_prompt) {
      children.push(el("div", {
        class: "mmc-sheet-negative",
        text: t("negative: {prompt}", { prompt: meta.negative_prompt }),
        title: meta.negative_prompt,
      }));
    }
    this.recipeBox.replaceChildren(...children);
  }

  copyButton(text) {
    const button = el("button", {
      class: "mmc-sheet-copy",
      text: t("Copy prompt"),
      onclick: async () => {
        try {
          await navigator.clipboard.writeText(text);
          button.textContent = t("Copied");
        } catch {
          button.textContent = t("Copy failed");
        }
        setTimeout(() => { button.textContent = t("Copy prompt"); }, 1500);
      },
    });
    return button;
  }

  // ---- right pane: the sidecar's story -------------------------------------

  section(label, children) {
    const body = [].concat(children).filter(Boolean);
    if (!body.length) return null;
    return el("div", { class: "mmc-sheet-section" }, [
      el("div", { class: "mmc-sheet-label", text: label }),
      ...body,
    ]);
  }

  chips(words, className = "mmc-sheet-chip") {
    if (!words?.length) return null;
    return el("div", { class: "mmc-sheet-chips" },
      words.map((word) => el("span", { class: className, text: word })));
  }

  metaInfo() {
    const meta = this.detail.meta;
    const stats = meta.stats || {};
    const eyebrow = [meta.type, meta.base_model].filter(Boolean).join(" · ");

    const statRow = el("div", { class: "mmc-sheet-stats" }, [
      Number.isFinite(stats.downloads) && this.stat(fmtCount(stats.downloads), t("downloads")),
      stats.rating > 0 && this.stat(`★ ${stats.rating.toFixed(1)}`, t("rating")),
      stats.favorites > 0 && this.stat(fmtCount(stats.favorites), t("favorites")),
      stats.comments > 0 && this.stat(fmtCount(stats.comments), t("comments")),
    ].filter(Boolean));

    const description = [meta.description, meta.version_description]
      .filter((html) => html && String(html).trim());
    const about = description.length
      ? el("div", { class: "mmc-sheet-desc" }, description.map((html) => {
        const block = el("div");
        block.appendChild(sanitize(html));
        return block;
      }))
      : null;

    // Built server-side, because only the server knows whether the record that
    // produced this sheet came from Civitai at all — a LoRA described entirely
    // by a `.txt` and a preview image has nowhere to link to.
    const link = meta.url ? el("a", {
      class: "mmc-sheet-link",
      href: meta.url,
      target: "_blank", rel: "noopener noreferrer",
      text: t("Open on Civitai ↗"),
    }) : null;

    return el("div", { class: "mmc-sheet-info" }, [
      this.closeButton(),
      el("div", { class: "mmc-sheet-eyebrow" }, [
        eyebrow,
        meta.nsfw ? el("span", { class: "mmc-sheet-nsfw", text: t("NSFW") }) : null,
      ]),
      el("div", { class: "mmc-sheet-title", text: meta.title || this.row.base }),
      el("div", {
        class: "mmc-sheet-byline",
        text: [
          meta.version,
          meta.creator && t("by {creator}", { creator: meta.creator }),
          meta.fetched_at && t("fetched {date}", { date: fmtDate(meta.fetched_at) }),
        ].filter(Boolean).join(" · "),
      }),
      statRow.childElementCount ? statRow : null,
      this.section(t("Trigger words"), this.chips(meta.trained_words, "mmc-sheet-chip accent")),
      // Whoever wrote the sidecar had settled on a weight. The manager's slider
      // now starts there, so the sheet says where "there" came from.
      this.section(t("Suggested strength"), Number.isFinite(meta.strength)
        ? el("div", { class: "mmc-sheet-license", text: meta.strength.toFixed(2) })
        : null),
      this.section(t("Notes"), meta.notes
        ? el("div", { class: "mmc-sheet-desc" }, [el("div", { text: meta.notes })])
        : null),
      this.section(t("About"), about),
      this.section(t("Versions"), this.versions(meta)),
      this.section(t("License"), this.license(meta.license)),
      this.section(t("Tags"), meta.tags?.length
        ? el("div", { class: "mmc-sheet-tags", text: meta.tags.join(" · ") })
        : null),
      this.section(t("File"), this.fileFacts(meta)),
      link,
    ]);
  }

  stat(value, label) {
    return el("span", { class: "mmc-sheet-stat" }, [
      el("span", { class: "mmc-sheet-stat-v", text: value }),
      el("span", { class: "mmc-sheet-stat-k", text: label }),
    ]);
  }

  /** Sibling versions from the sidecar, the installed one marked. */
  versions(meta) {
    if (!meta.versions?.length) return null;
    return el("div", { class: "mmc-sheet-versions" }, meta.versions.map((version) =>
      el("div", { class: "mmc-sheet-version", "aria-current": version.id === meta.version_id }, [
        el("span", { class: "mmc-sheet-version-name", text: version.name || String(version.id) }),
        el("span", {
          class: "mmc-sheet-version-sub",
          text: [version.base_model, fmtDate(version.created_at)].filter(Boolean).join(" · "),
        }),
        version.id === meta.version_id ? el("span", { class: "mmc-sheet-installed", text: t("installed") }) : null,
      ])));
  }

  /** Already normalised server-side: Civitai returns an array of permissions
   *  and CiviMeta stores the same thing as the set literal "{Image,Rent,Sell}",
   *  and neither spelling reaches this far any more. */
  license(license) {
    if (!license) return null;
    const lines = [
      license.commercial?.length
        ? t("Commercial use: {kinds}", { kinds: license.commercial.join(", ") }) : t("No commercial use"),
      license.credit ? t("Credit required") : t("Credit not required"),
      license.derivatives ? t("Derivatives allowed") : t("No derivatives"),
    ];
    return el("div", { class: "mmc-sheet-license", text: lines.join(" · ") });
  }

  fileFacts(meta) {
    const header = this.detail.header || {};
    const facts = headerFacts(header, this.detail.size)
      .filter(([label]) => ["Rank", "Precision", "Tensors", "File size"].includes(label));
    const sources = (meta.sources || []).map((key) => (SOURCE_LABEL[key] ? t(SOURCE_LABEL[key]) : key));
    return el("div", { class: "mmc-sheet-file" }, [
      el("div", { class: "mmc-sheet-path", text: this.row.name, title: this.row.name }),
      facts.length ? el("div", {
        class: "mmc-sheet-file-facts",
        text: facts.map(([label, value]) => `${t(label).toLowerCase()} ${value}`).join(" · "),
      }) : null,
      meta.hash ? el("div", { class: "mmc-sheet-hash", text: t("sha256 {hash}…", { hash: String(meta.hash).slice(0, 12) }), title: meta.hash }) : null,
      // Only worth reading when something above looks wrong, which is exactly
      // when knowing which file on disk said it is the whole answer.
      sources.length ? el("div", {
        class: "mmc-sheet-file-facts",
        title: t("Where the fields above were read from. Later entries only fill in what earlier ones left blank."),
        text: t("read from {sources}", { sources: sources.join(", ") }),
      }) : null,
    ]);
  }

  // ---- the bare sheet: what the file says about itself ---------------------

  headerInfo() {
    const header = this.detail.header || {};
    const metadata = header.metadata || {};
    const facts = headerFacts(header, this.detail.size);
    const tags = tagFrequency(metadata);

    const spec = facts.length ? el("div", { class: "mmc-sheet-spec" }, facts.map(([label, value]) =>
      el("div", { class: "mmc-sheet-spec-row" }, [
        el("span", { class: "mmc-sheet-spec-k", text: t(label) }),
        el("span", { class: "mmc-sheet-spec-v", text: value }),
      ]))) : null;

    const tagChips = tags.length ? el("div", { class: "mmc-sheet-chips" },
      tags.slice(0, 24).map(([tag, count]) => el("span", { class: "mmc-sheet-chip" }, [
        tag,
        el("span", { class: "mmc-sheet-chip-n", text: String(count) }),
      ]))) : null;

    const keys = Object.keys(metadata);
    const raw = keys.length ? el("details", { class: "mmc-sheet-raw" }, [
      el("summary", { text: t("All header fields ({count})", { count: keys.length }) }),
      el("div", { class: "mmc-sheet-raw-rows" }, keys.sort().map((key) => {
        const value = String(metadata[key]);
        return el("div", { class: "mmc-sheet-raw-row" }, [
          el("span", { class: "mmc-sheet-raw-k", text: key }),
          el("span", {
            class: "mmc-sheet-raw-v",
            text: value.length > 200 ? `${value.slice(0, 200)}…` : value,
            title: value.length > 200 ? value : null,
          }),
        ]);
      })),
    ]) : null;

    return el("div", { class: "mmc-sheet-info" }, [
      this.closeButton(),
      el("div", { class: "mmc-sheet-eyebrow" }, [
        el("span", { class: "mmc-sheet-mono-mark" }, [svg(ICONS.effect, 13)]),
        header.error ? "safetensors" : t("safetensors header"),
      ]),
      el("div", { class: "mmc-sheet-title", text: metadata.name || metadata.ss_output_name || this.row.base }),
      el("div", {
        class: "mmc-sheet-byline",
        text: t("No sidecar anywhere beside this file — everything below was read from the file itself."),
      }),
      header.error
        ? el("div", { class: "mmc-sheet-license", text: t("The header could not be read: {error}", { error: header.error }) })
        : null,
      this.section(t("Specification"), spec),
      this.section(t("Dataset tags"), tagChips && [
        el("div", {
          class: "mmc-sheet-hint",
          text: t("The most frequent words in the training captions — the closest thing this file has to trigger words."),
        }),
        tagChips,
      ]),
      raw,
      this.section(t("File"), el("div", { class: "mmc-sheet-file" }, [
        el("div", { class: "mmc-sheet-path", text: this.row.name, title: this.row.name }),
      ])),
    ]);
  }
}
