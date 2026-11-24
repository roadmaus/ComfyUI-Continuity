// The back of a finished render: what made it, and the way back to a node.
//
// A card in the chat has always had a back — the prompt and the numbers a
// render was made from. A take on the fullscreen lip and a file in the gallery
// are the same object, a finished render you are deciding about, and what
// their back adds is the way home: it can put what made the file back on the
// node, or hand the words to the clipboard.
//
// Read out of the file rather than out of anything a window remembers — both
// save nodes embed the graph that made a render (`renderMeta`), and
// `captureFromRender` already turns that into the sections a preset holds. So
// a render's back and "Preset from a render" are one reading of one file, and
// what lands on the node is exactly what a preset of it would land.

import { app } from "../../../scripts/app.js";
import { renderMeta } from "./api.js";
import { el, icon, copyDoor } from "./dom.js";
import { elapsed } from "./stage.js";
import { t } from "./i18n.js";
import { openPlace } from "./placerender.js";
import * as P from "./presets.js";
import * as S from "./state.js";

const PRESTAGE = "MiniMaxH3PreStage";

const reduced = () =>
  globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/**
 * Where a render's settings land, as the `home` a slate asks.
 *
 * A still is the pre-stage's to take back and a clip the piece's. The node
 * the window was opened from answers for its own kind — with its own target,
 * so a card of a strip takes a clip's settings as that card rather than as
 * the whole piece — and the node paired with it answers for the other, found
 * by the blob's `peer` field the way the fullscreen pair is.
 *
 * @param {object} own
 * @param {"video"|"still"} own.kind   what the opening node makes
 * @param {() => string|number|null} own.nodeId
 * @param {() => object|null} own.target  its preset target
 * @param {() => object|null} own.io      its `widgetIO`, for the seed
 * @returns {(scope: string) => {target: object, io: object|null}|null}
 */
export function settingsHome(own) {
  return (scope) => {
    const kind = scope === "prestage" ? "still" : "video";
    if (kind === own.kind) {
      const target = own.target?.() ?? null;
      return target ? { target, io: own.io?.() ?? null } : null;
    }
    const id = own.nodeId?.();
    if (id === null || id === undefined) return null;
    const nodes = app.graph?._nodes ?? [];
    const peer = own.kind === "video"
      ? nodes.find((n) => n.comfyClass === PRESTAGE && n.mmcBody
          && String(n.mmcBody.state?.peer) === String(id))
      : nodes.find((n) => n.mmcBody && n.comfyClass !== PRESTAGE && String(n.id)
          === String(nodes.find((m) => String(m.id) === String(id))?.mmcBody?.state?.peer));
    const target = peer?.mmcBody?.presetTarget?.() ?? null;
    return target ? { target, io: peer.mmcBody.widgetIO?.() ?? null } : null;
  };
}

/**
 * Make a card turn over.
 *
 * Half a turn out, the faces swapped while the card is edge-on, half a turn
 * in. The back is built on the first turn rather than with the card: it costs
 * a request, and most renders are looked at and never turned.
 *
 * @param {HTMLElement} card   positioned; the back is laid over all of it
 * @param {HTMLElement} media  the picture or clip on its front
 * @param {() => HTMLElement} build  the back, asked for once
 * @returns {{button: HTMLElement, turn: () => void}}  the button is the
 *   caller's to place — on the card, top right, is where its CSS puts it
 */
export function turner(card, media, build) {
  let turned = false, turning = false, back = null;
  const button = el("button", {
    class: "mmc-fs-flip", "aria-pressed": "false", title: t("What made this"),
    onclick: (event) => { event.stopPropagation(); turn(); },
  }, [icon("flip", 15)]);
  const swap = () => {
    card.classList.toggle("mmc-turned", turned);
    button.setAttribute("aria-pressed", String(turned));
    button.title = turned ? t("Back to the picture") : t("What made this");
    button.replaceChildren(icon(turned ? "image" : "flip", 15));
    // A clip does not go on talking behind its own back.
    if (turned) media.pause?.();
    else media.play?.()?.catch?.(() => {});
  };
  const turn = () => {
    if (turning || !card.isConnected) return;
    turned = !turned;
    if (turned && !back) {
      back = build();
      card.appendChild(back);
    }
    if (reduced() || !card.animate) { swap(); return; }
    const edge = "perspective(1400px) rotateY(90deg)";
    const flat = "perspective(1400px) rotateY(0deg)";
    turning = true;
    const settle = () => { turning = false; };
    card.animate([{ transform: flat }, { transform: edge }],
                 { duration: 170, easing: "ease-in" }).finished.then(() => {
      if (!card.isConnected) { settle(); return; }
      swap();
      card.animate([{ transform: "perspective(1400px) rotateY(-90deg)" }, { transform: flat }],
                   { duration: 240, easing: "cubic-bezier(.2,.7,.15,1)" })
        .finished.then(settle, settle);
    }, settle);
  };
  return { button, turn };
}

/**
 * The back of one render: the words, the numbers, and the doors.
 *
 * @param {object} spec
 * @param {{path: string, kind: string}|null} spec.source  the file, as the
 *   gallery names it — null for a render that was never saved
 * @param {string} [spec.name]
 * @param {HTMLElement} spec.media  read for the file's own size
 * @param {number|null} [spec.tookMs]
 * @param {(scope: string) => object|null} [spec.home]  see `settingsHome`
 */
export function takeSlate({ source, name = "", media, tookMs = null, home = null }) {
  const root = el("div", { class: "mmc-fs-slate mmc-ch-slate" }, [
    el("div", { class: "mmc-ch-prompt" }, [el("p", { text: t("Reading…") })]),
  ]);
  (async () => {
    if (!source) throw new Error(t("This render was not saved, so nothing says what made it."));
    const captured = P.captureFromRender(await renderMeta(source.path), { ...source, name });
    root.replaceChildren(...slateParts({ captured, media, tookMs, home, source, name }));
  })().catch((error) => {
    root.replaceChildren(el("div", { class: "mmc-ch-prompt" }, [
      el("p", { text: error.message ?? String(error) })]), ...placeDoors(source, name));
  });
  return root;
}

/** The doors onto a timeline, for a saved video: its shots, or its footage. */
function placeDoors(source, name) {
  if (source?.kind !== "video") return [];
  const said = el("span", { class: "mmc-fs-slate-note" });
  const door = (label, title, clip) => el("button", { class: "mmc-fs-slate-door", text: label, title,
    onclick: () => openPlace({ path: source.path, name, clip, done: (sentence) => { said.textContent = sentence; } })
      .catch((error) => { said.textContent = error.message ?? String(error); }) });
  return [el("div", { class: "mmc-fs-slate-doors" }, [
    door(t("Place into timeline"), t("Put its shots on a timeline, with their settings and their takes kept."), false),
    door(t("Place as clip"), t("Put the footage alone on a timeline. It is never generated again."), true),
    said])];
}

function slateParts({ captured, media, tookMs, home, source, name }) {
  const data = captured.data;
  const still = captured.scope === "prestage";
  // The words. A still has one prompt; a piece has a standing one and one
  // per card, and a lone shot's is the whole of it.
  const cards = still ? [] : (data.strip?.segments ?? []);
  const texts = still
    ? [data.prompt]
    : [data.prompt, ...cards].filter((text) => (text?.prompt ?? "").trim() || text?.refined?.body);
  const words = texts.map((text, index) => {
    const numbered = !still && cards.length > 1 && cards.includes(text);
    const typed = (text?.prompt ?? "").trim();
    const rewrite = text?.refined?.enabled !== false ? (text?.refined?.body ?? "").trim() : "";
    return [
      el("p", { text: `${numbered ? `${cards.indexOf(text) + 1}. ` : ""}${typed || rewrite}` }),
      // The rewrite is what the sampler read; folded under the words it was
      // written from, the way the chat folds a caption.
      ...(typed && rewrite ? [el("details", { class: "mmc-ch-caption" }, [
        el("summary", { text: t("Refined") }),
        el("pre", { text: rewrite }),
      ])] : []),
      // Each text on its own button, named for which one it is: the typed
      // prompt goes back in a prompt box, the rewrite goes anywhere else.
      el("div", { class: "mmc-copy-row" }, [
        ...(typed ? [copyDoor(t("Copy prompt"), typed)] : []),
        ...(rewrite ? [copyDoor(t("Copy refined"), rewrite)] : []),
      ]),
    ];
  }).flat();
  const prompt = el("div", { class: "mmc-ch-prompt" },
                    words.length ? words : [el("p", { text: t("No prompt.") })]);

  const facts = [];
  const fact = (key, value) => {
    if (value === null || value === undefined || value === "") return null;
    const dd = el("dd", { text: String(value), title: String(value) });
    facts.push(el("dt", { text: key }), dd);
    return dd;
  };
  const arch = data.weights?.arch;
  fact(t("made with"), still
    ? t(S.PRESTAGE_ARCH_LABEL[arch] ?? arch ?? "")
    : t(S.FAMILY_LABEL[data.speed?.family] ?? data.speed?.family ?? ""));
  const size = fact(t("size"), "—");
  const canvas = [data.look?.aspect,
                  data.look?.short_edge ? t("{n} short edge", { n: data.look.short_edge }) : null]
    .filter(Boolean).join(" · ");
  const measure = () => {
    const w = media.naturalWidth || media.videoWidth, h = media.naturalHeight || media.videoHeight;
    size.textContent = [w && h ? `${w} × ${h}` : null, canvas].filter(Boolean).join(" · ") || "—";
  };
  measure();
  media.addEventListener(media.tagName === "VIDEO" ? "loadedmetadata" : "load", measure, { once: true });
  if (!still) {
    const seconds = cards.reduce((sum, card) => sum + (Number(card.duration_s) || 0), 0);
    if (seconds) fact(t("length"), t("{n} s", { n: Math.round(seconds * 100) / 100 }));
  }
  const row = data.speed?.row ?? {};
  const turbo = still ? data.speed?.turbo?.[arch]?.on : data.speed?.turbo?.on;
  fact(t("sampler"), [row.quality ? t(row.quality) : null,
                      row.steps ? t("{n} steps", { n: row.steps }) : null,
                      row.cfg != null ? `cfg ${row.cfg}` : null,
                      row.sampler_name, row.scheduler,
                      turbo ? t("turbo") : null].filter(Boolean).join(" · "));
  if (captured.seed != null) fact(t("seed"), captured.seed);
  const loras = [...(data.loras ?? []), ...cards.flatMap((card) => card.loras ?? [])]
    .filter((entry) => entry?.name && entry.enabled !== false)
    .map((entry) => entry.name.split("/").pop().replace(/\.[^.]+$/, ""));
  fact(t("LoRAs"), [...new Set(loras)].join(", "));
  const files = still
    ? (data.refs?.refs?.length ?? 0) + (data.refs?.init ? 1 : 0)
    : (data.refs?.length ?? 0) + cards.reduce((sum, card) => sum + (card.assets?.length ?? 0), 0);
  if (files) fact(t("from"), t(files === 1 ? "{count} file" : "{count} files", { count: files }));
  if (tookMs) fact(t("took"), elapsed(tookMs));

  // The way home. Which node, by what the file is: a still is the
  // pre-stage's to take back and a clip the piece's — `home` knows where each is.
  const landing = home?.(captured.scope) ?? null;
  const target = landing?.target ?? null;
  const off = P.sectionsOff();
  const keys = !target ? [] : Object.keys(data).filter((key) => !off.has(key)
    && P.crossable(key, captured.scope, target.scope, {
      arch: arch ?? null, targetArch: target.arch?.() ?? null,
      family: data.speed?.family ?? null, targetFamily: target.family?.() ?? null,
    }).ok);
  const said = el("span", { class: "mmc-fs-slate-note" });
  const keepSeed = () => {
    if (captured.seed === null || !landing.io) return;
    const io = landing.io;
    io.set("seed", captured.seed);
    io.set("control_after_generate", "fixed");
  };
  const door = (label, title, run, done) => el("button", {
    class: "mmc-fs-slate-door", text: label, title,
    onclick: () => {
      try { run(); said.textContent = done; }
      catch (error) { said.textContent = t("Could not apply it — {error}", { error: error.message }); }
    },
  });
  const taken = keys.map((key) => t(P.SECTION[key]?.label ?? key)).join(" · ");
  const doors = el("div", { class: "mmc-fs-slate-doors" }, !target
    ? [el("span", { class: "mmc-fs-slate-note",
                    text: t("No node here to put these settings back on.") })]
    : [
        door(t("Use these settings"),
             t("Put what made this take back on {label}: {sections} — and its seed, kept. "
             + "The sections are the ones ticked in Presets.",
               { label: target.label, sections: taken || t("nothing") }),
             () => { keepSeed(); target.apply(data, keys, captured.scope); },
             t("Back on {label}.", { label: target.label })),
        ...(captured.seed !== null ? [door(t("Seed only"),
             t("Keep seed {seed} on {label} and leave everything else as it is.",
               { seed: captured.seed, label: target.label }),
             keepSeed, t("Seed {seed} kept.", { seed: captured.seed }))] : []),
        said,
      ]);
  if (target && !said.textContent) said.textContent = taken;
  return [prompt, el("dl", { class: "mmc-ch-facts" }, facts), doors, ...placeDoors(source, name)];
}
