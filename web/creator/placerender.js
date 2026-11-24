// A finished render, put on a timeline.
//
// The render's file carries the piece that made it and the gallery knows which
// takes it was cut from, so a shot can come back whole: its words, its cast, its
// seed, and the film it already has, kept. It plays as it is until it is edited
// or reshot, like any other kept take. A file with none of that is footage, and
// comes in as a clip.

import { app } from "../../../scripts/app.js";
import { listAssets, probe, renderMeta } from "./api.js";
import { el, mountOverlay } from "./dom.js";
import { t } from "./i18n.js";
import * as P from "./presets.js";
import * as S from "./state.js";

const PIECES = ["MiniMaxH3Creator", "MiniMaxH3Timeline"];
const copy = (value) => JSON.parse(JSON.stringify(value));

/** What a render can put on a strip: `{ piece, seed, shots: [{ pass, film }] }`.
 *  A shot's own file carries no settings, so the render it belongs to is asked.
 *  -> null where nothing says which shot is which file. */
async function shotsOf(path) {
  const rows = await listAssets({ root: "output" });
  const row = rows.find((candidate) => candidate.shots?.includes(path))
    ?? rows.find((candidate) => candidate.path === path);
  const source = P.renderSources((await renderMeta(row?.path ?? path)).prompt)
    .find((candidate) => candidate.scope === "piece");
  if (!source) return null;
  const piece = S.parseTimeline(source.blob);
  S.syncTimeline(piece);
  const passes = S.passes(piece);
  const films = row?.shots ?? (passes.length === 1 ? [path] : []);
  const made = passes.filter((pass) => !S.isClip(pass.segments[0]));
  const named = films.length === passes.length ? passes : films.length === made.length ? made : null;
  if (!named) return null;
  const shots = named.map((pass, k) => ({ pass, film: films[k], number: passes.indexOf(pass) }))
    .filter(({ pass }) => !S.isClip(pass.segments[0]));
  return { piece, seed: Number.isFinite(source.inputs?.seed) ? source.inputs.seed : null, shots,
           only: shots.findIndex((shot) => shot.film === path && films.length > 1) };
}

/** A strip nobody has written on. */
const blank = (timeline) => timeline.segments.every((card) => !S.isClip(card)
  && !(card.prompt ?? "").trim() && !card.assets?.length && !card.take)
  && !(timeline.prompt ?? "").trim() && !timeline.assets?.length && !timeline.subjects?.length;

const report = async (film, segment) => {
  const read = await probe(film).catch(() => ({}));
  const bare = film.replace(/ \[output\]$/, "");
  const cut = bare.lastIndexOf("/");
  return { segment, filename: bare.slice(cut + 1), subfolder: bare.slice(0, Math.max(0, cut)),
           duration_s: read.duration ?? 0, width: read.width, height: read.height,
           has_audio: read.hasAudio !== false };
};

/** The cards of one pass as they go on another strip: ids and seams of their
 *  own, the seed they were shot on, and the film out of the way. */
function cardsOf(source, { pass, number }, first) {
  return pass.segments.map((segment, k) => {
    const card = copy(segment);
    for (const key of ["card_id", "take", "hold", "continue_from", "storyboard"]) delete card[key];
    if (first && k === 0) { card.continue = false; card.continue_audio = false; }
    if (!Number.isInteger(card.seed) && source.seed !== null) {
      card.seed = source.seed + (source.piece.seeds === "each" ? number : 0);
    }
    return card;
  });
}

/** Bring what `card` needs from its old piece: the scene it stood in, the cast
 *  and references it names, its set, and the LoRAs over the whole piece. */
function carry(source, card, timeline, sets) {
  const from = source.piece;
  const scene = (from.prompt ?? "").trim();
  if (scene && scene !== (timeline.prompt ?? "").trim()) {
    card.prompt = [scene, card.prompt].filter(Boolean).join("\n");
    if (card.refined?.body) card.refined.body = `${scene}\n${card.refined.body}`;
  }
  const texts = [card.prompt, card.refined?.body, card.soundscape, card.music].filter(Boolean);
  const pool = S.castAssets(from);
  const filesOf = (subject, assets) => S.subjectFiles(subject)
    .map((handle) => assets.find((asset) => asset.handle === handle)?.filename).filter(Boolean).sort().join("|");
  const renames = [];
  for (const subject of from.subjects ?? []) {
    if (!texts.some((text) => S.subjectCitationRe([subject]).test(text))) continue;
    const files = filesOf(subject, pool);
    let here = (timeline.subjects ?? []).find((other) =>
      other.handle === subject.handle && filesOf(other, S.castAssets(timeline)) === files);
    here ??= P.castIntoPiece(P.captureSubject(subject, pool).data.cast, timeline, { pool: true });
    // A piece of one shot keeps its cast's pictures on the shot.
    const claimed = new Set(S.subjectFiles(subject));
    card.assets = (card.assets ?? []).filter((asset) => !claimed.has(asset.handle));
    if (here.handle !== subject.handle) renames.push([subject.handle, here.handle]);
  }
  for (const asset of from.assets ?? []) {
    if (!S.handleWritten(texts, asset.handle)) continue;
    const entry = { ...copy(asset), handle: S.nextPoolHandle(timeline) };
    const held = (timeline.assets ?? []).find((other) => other.filename === asset.filename && other.kind === asset.kind);
    if (!held) timeline.assets = [...(timeline.assets ?? []), entry];
    const handle = (held ?? entry).handle;
    if (handle !== asset.handle) renames.push([asset.handle, handle]);
  }
  // By way of names nothing else has, so two that swap do not become one.
  renames.forEach(([was], k) => S.renameSubjectCitations([card], was, `mmcplaced${k}`));
  renames.forEach(([, now], k) => S.renameSubjectCitations([card], `mmcplaced${k}`, now));
  const set = S.setOf(from, card);
  if (set) {
    const same = (timeline.sets ?? []).find((other) => other.id === set.id
      && JSON.stringify(other.objects) === JSON.stringify(set.objects));
    if (same) sets.set(set.id, same.id);
    else if (!sets.has(set.id)) {
      const taken = new Set((timeline.sets ?? []).map((other) => other.id));
      let id = set.id;
      for (let n = 1; taken.has(id); n += 1) id = `s${n}`;
      timeline.sets = [...(timeline.sets ?? []), { ...copy(set), id }];
      sets.set(set.id, id);
    }
    card.set = sets.get(set.id);
  }
  const worn = new Set([...(timeline.loras ?? []), ...(card.loras ?? [])].map((entry) => entry.name));
  card.loras = [...(card.loras ?? []), ...copy((from.loras ?? []).filter((entry) => !worn.has(entry.name)))];
}

/** Put cards on a strip at `at`, each of `films` kept on the card it names. */
async function land(body, cards, films, at) {
  const timeline = body.timeline;
  const reports = [];
  for (const { index, film } of films) reports.push(await report(film, index));
  if (blank(timeline)) { timeline.segments = []; at = 0; }
  timeline.segments.splice(at, 0, ...cards);
  S.remapContinueFrom(timeline, (n) => (n > at ? n + cards.length : n));
  S.syncTimeline(timeline);
  S.ensureCardIds(timeline);
  S.attachTakes(timeline, reports.map((entry) => ({ ...entry, segment: at + entry.segment + 1 })));
  (body.reel ?? body).commit();
}

/** A whole piece put on a node: the render's own settings, and these shots. */
async function replace(body, source, picked) {
  const timeline = body.timeline;
  const fresh = copy(JSON.parse(S.serializeTimeline(source.piece)));
  fresh.segments = [];
  const made = S.parseTimeline(JSON.stringify(fresh));
  made.segments = [];
  for (const key of Object.keys(timeline)) delete timeline[key];
  Object.assign(timeline, made);
  if (source.seed !== null) {
    body.widgetIO().set("seed", source.seed);
    body.widgetIO().set("control_after_generate", "fixed");
  }
  const { cards, films } = gather(source, picked);
  await land(body, cards, films, 0);
}

function gather(source, picked) {
  const cards = [], films = [];
  let last = null;
  for (const shot of picked) {
    films.push({ index: cards.length, film: shot.film });
    // A seam holds only where the shot it continues from came along.
    cards.push(...cardsOf(source, shot, last === null || shot.number !== last + 1));
    last = shot.number;
  }
  return { cards, films };
}

function newNode() {
  const node = globalThis.LiteGraph.createNode(PIECES[0]);
  const below = (app.graph._nodes ?? []).reduce((low, other) => Math.max(low, other.pos[1] + other.size[1]), 0);
  node.pos = [80, below + 80];
  app.graph.add(node);
  return node;
}

/**
 * Ask where a render goes, and put it there. `clip` places the footage alone.
 * `done(sentence)` is told how it went.
 */
export async function openPlace({ path, name = "", clip = false, done = () => {} }) {
  const source = clip ? null : await shotsOf(path);
  if (!clip && !source?.shots.length) throw new Error(t("Nothing says which shots this file is made of. Place it as a clip."));
  const pieces = (app.graph?._nodes ?? []).filter((node) => PIECES.includes(node.comfyClass) && node.mmcBody?.timeline);
  // Asked every time: nothing is chosen until it is pressed.
  let target = null, at = null;
  let picked = new Set(source ? (source.only >= 0 ? [source.only] : source.shots.keys()) : []);
  const said = el("p", { class: "mmc-reel-why" });
  const rows = el("div", { class: "mmc-place-body" });
  const go = el("button", { class: "mmc-reel-btn primary", text: t("Place it") });
  const choice = (label, on, press) => el("button", { class: "mmc-reel-value", "aria-pressed": Boolean(on), text: label, onclick: press });
  const row = (label, children) => el("div", { class: "mmc-place-row" }, [el("b", { text: label }), el("div", { class: "mmc-reel-inline" }, children)]);
  const other = () => target && target !== "new" && !blank(target.mmcBody.timeline)
    && source && S.pieceFamily(target.mmcBody.timeline) !== S.pieceFamily(source.piece);
  const draw = () => {
    const timeline = target && target !== "new" ? target.mmcBody.timeline : null;
    const filled = timeline && !blank(timeline);
    rows.replaceChildren(...[
      row(t("Where"), [
        ...pieces.map((node) => choice(pieces.length === 1 ? t("This piece") : `${node.title} #${node.id}`, target === node,
          () => { target = node; at = null; draw(); })),
        choice(t("A new piece"), target === "new", () => { target = "new"; at = null; draw(); })]),
      source && source.shots.length > 1 ? row(t("Shots"), source.shots.map((shot, k) =>
        choice(t("Shot {n}", { n: k + 1 }), picked.has(k), () => { picked.has(k) ? picked.delete(k) : picked.add(k); draw(); }))) : null,
      filled ? row(t("At"), [choice(t("The start"), at === 0, () => { at = 0; draw(); }),
        ...timeline.segments.map((_, k) => choice(k === timeline.segments.length - 1 ? t("The end") : t("After shot {n}", { n: k + 1 }),
          at === k + 1, () => { at = k + 1; draw(); }))]) : null,
    ].filter(Boolean));
    said.textContent = other()
      ? t("That piece renders with another model, so these shots can only go in as a clip.")
      : !target ? t("Pick a piece.")
        : clip ? t("The footage alone. It is never generated again.")
          : filled ? t("Its shots come with their words, cast and seeds, and their takes kept. The piece's own model and size stay.")
            : t("The render's whole piece comes with it, its takes kept.");
    go.disabled = !target || (filled && at === null) || (source && !picked.size) || other();
  };
  const overlay = el("div", { class: "mmc-overlay", onpointerdown: (event) => { if (event.target === overlay) close(); } }, [
    el("div", { class: "mmc-modal mmc-place" }, [
      el("div", { class: "mmc-reel-head" }, [
        el("span", { class: "mmc-reel-title", text: clip ? t("Place as clip") : t("Place into timeline") }),
        el("span", { class: "mmc-reel-meta", text: name }),
        el("button", { class: "mmc-close", text: "✕", title: t("Close"), onclick: () => close() })]),
      rows, said, el("div", { class: "mmc-place-foot" }, [go])])]);
  const unmount = mountOverlay(overlay, () => close());
  const close = () => unmount();
  go.onclick = async () => {
    go.disabled = true;
    try {
      const node = target === "new" ? newNode() : target;
      const body = node.mmcBody;
      const shots = source ? source.shots.filter((_, k) => picked.has(k)) : [];
      const fits = clip ? null : S.addSegmentRefusal(body.timeline);
      if (fits) throw new Error(fits);
      if (clip) {
        const read = await probe(path).catch(() => ({}));
        await land(body, [S.clipSegment({ filename: path, duration: read.duration, width: read.width,
          height: read.height, hasAudio: read.hasAudio })], [], at ?? 0);
      } else if (blank(body.timeline)) {
        await replace(body, source, shots);
      } else {
        const { cards, films } = gather(source, shots);
        const sets = new Map();
        for (const card of cards) carry(source, card, body.timeline, sets);
        await land(body, cards, films, at);
      }
      close();
      done(target === "new" ? t("On a new piece.") : t("On {name}.", { name: node.title }));
    } catch (error) {
      said.textContent = error.message ?? String(error);
      go.disabled = false;
    }
  };
  draw();
}
