// What the room takes from the canvas, and whose each setting is.
//
// A chat renders from its own piece. Its family, its shape, its seed, its
// cast, the files it made and attached, and the family's pinned LoRAs are all
// the conversation's, assembled by `chat.js` at render time; nothing on the
// canvas is read into a chat render and nothing a chat renders is written
// onto the canvas. The one exception is how a render *samples* — the sampler
// row and the turbo switch — and that only while the room follows the node:
// a chat is usually opened over a piece somebody has already tuned, and the
// steps, the guidance and the schedule they settled on are the ones a draft
// beside it should sample on too. So a machine set up once, on the node, is
// set up for its chats.
//
// **Every row says whose it is.** `source(kind)` answers one of three words,
// and the *Makes with* sheet wears the answer as a badge beside the row:
//
//   - `node` — the node under the room is on this family, and its row is
//     what the room samples on. Change the node and the room changes.
//   - `chat` — the room keeps a row of its own for this side, kept on the
//     machine (`settings.chat`) so it is there on the next page and for every
//     chat. The node is free to be set differently.
//   - `defaults` — there is nothing to follow: no node under the room, or a
//     node on another family (H3's steps are not LTX's, and H3's turbo LoRA
//     is not a file LTX can wear). The family's own defaults, all the way down.
//
// **A row of the chat's own is the steps and the guidance, never the
// speed-ups.** The accelerators — block cache, spectrum, attention, VDN, the
// low-VRAM and fast-math switches — are statements about this machine rather
// than about a piece, so they are never copied into the chat's row and never
// drawn on it; the render takes the node's where the node can be followed
// and the family's defaults where it cannot (`row`).
//
// The chat's own row is drawn with the same functions the faces mount —
// `samplingBar`, `turboPills`, `PreStageRow` — over a blank blob of the
// room's family through `blobIO`. A followed row is read, never drawn: the
// node is the one place it is edited, which is the whole point of following.
import { samplingBar, blobIO, SAMPLING_WIDGETS, WIDGET_ONLY } from "./sampling.js";
import { turboPills, sync as syncTurbo } from "./turbo.js";
import { PreStageRow } from "./prestage.js";
import * as S from "./state.js";
import { DEFAULT_STILL_ARCH, STILL_ARCHES, DEFAULT_VIDEO_FAMILY, stillFamily } from "./manifest.js";
import { t } from "./i18n.js";

/** The image arches the room can draw a picture with — every pre-stage arch,
 *  MiniMax's included now that it is MiniMax H3 Image (`routes/chat._rail`). */
export const PICTURE_ARCHES = S.PRESTAGE_IMAGE_ARCHES;

/** The image arches a cited picture can be *changed* on: the families whose
 *  manifest says the first picture cited is the one being edited. Read off
 *  the manifest, never off a family id — `chat.edits_pictures` reads the
 *  same flag. What the room's *Edits* pill offers. */
export const EDIT_ARCHES = PICTURE_ARCHES.filter(
  (arch) => Boolean(stillFamily(arch).capabilities?.refs?.edits_first));

/** The rail field a side's own row is kept in. */
const OWN = { still: "pinned_still", video: "pinned_video" };

/** The pre-stage's sampler row, by widget name. One node draws every image
 *  arch, so its row is one set of widgets whatever the arch. */
const STILL_ROW = ["steps", "cfg", "sampler_name", "scheduler"];

/** The keys of a video family's row that are about the machine — the
 *  accelerators — plus the blob-only VDN stage, which rides with them. */
function accelKeys(family) {
  return new Set([
    ...S.widgetsOf(family).filter((w) => w.group === "accel").map((w) => w.id),
    "vdn",
  ]);
}

/** `block` without the keys in `drop`. */
function without(block, drop) {
  return Object.fromEntries(Object.entries(block ?? {}).filter(([name]) => !drop.has(name)));
}

/** Only the keys of `block` in `keep`. */
function only(block, keep) {
  return Object.fromEntries(Object.entries(block ?? {}).filter(([name]) => keep.has(name)));
}

/** The widgets a chat's own row is drawn over: the node's, minus the seed's
 *  (the room's seed is its own) and minus the accelerators; or, with no
 *  node on the canvas to borrow them from, a stand-in per name — the bar
 *  only asks whether a widget exists, and reads its value through the io. */
function ownWidgets(kind, family, real) {
  const drop = new Set([...WIDGET_ONLY, ...(kind === "video" ? accelKeys(family) : [])]);
  if (real && Object.keys(real).length) return without(real, drop);
  const names = kind === "video"
    ? S.widgetsOf(family).filter((w) => w.group === "sampler").map((w) => w.id)
    : STILL_ROW;
  return Object.fromEntries(names.map((name) => [name, { name }]));
}

/**
 * The sampler row a chat render samples on, and whose it is.
 *
 * @param {object} doors
 *   `node()` the piece's node under the room, or null;
 *   `preStage()` the pre-stage beside it, or null;
 *   `rail()` / `setRail(patch)` the room's rail, where the families and a
 *   row of the room's own live.
 */
export class Sync {
  constructor({ node, preStage, rail, setRail }) {
    this.node = node ?? (() => null);
    this.preStage = preStage ?? (() => null);
    this.rail = rail;
    this.setRail = setRail;
    this.copies = { still: null, video: null };
    this.followers = new Set();
  }

  // ---- the room's own families -----------------------------------------------

  videoFamily() {
    return this.rail().video_family || DEFAULT_VIDEO_FAMILY;
  }

  stillArch() {
    const arch = this.rail().still_arch;
    return PICTURE_ARCHES.includes(arch) ? arch : DEFAULT_STILL_ARCH;
  }

  /** The still family the server is told, by name — the arch as the registry
   *  names its family. */
  stillFamily() {
    return STILL_ARCHES[this.stillArch()] ?? null;
  }

  /** The arch a cited picture is changed on when the image model cannot read
   *  one — the room's *Edits* choice — or "" for whichever is ready, which
   *  the server decides (`routes/chat.machine`). */
  editArch() {
    const arch = this.rail().edit_arch;
    return EDIT_ARCHES.includes(arch) ? arch : "";
  }

  /** What the turn's settings block says about the sides: which families,
   *  and whether the still's turbo switch loads the Turbo checkpoint. */
  families() {
    const turbo = this.row("still").turbo;
    return {
      still_family: this.stillFamily() ?? "",
      video_family: this.videoFamily(),
      edit_family: STILL_ARCHES[this.editArch()] ?? "",
      still_turbo_checkpoint: Boolean(turbo?.on && !turbo?.lora),
    };
  }

  // ---- the nodes, where they can be followed ------------------------------------

  clipNode() {
    const node = this.node();
    const body = node?.mmcBody;
    const piece = body?.timeline;
    return body && piece ? { node, body, piece } : null;
  }

  pictureNode() {
    const node = this.preStage();
    const body = node?.mmcBody;
    const state = body?.state;
    return body && state ? { node, body, state } : null;
  }

  /** Whether a side's node is one the room can follow: there, and on the
   *  room's own family. A row is a family's. `arch` is the image arch a
   *  still is being drawn on where it is not the room's own — an edit of a
   *  cited picture on the *Edits* family — and the pre-stage has to be on
   *  that one to be followed for it. */
  followable(kind, arch = this.stillArch()) {
    if (kind === "video") {
      const live = this.clipNode();
      return Boolean(live && S.pieceFamily(live.piece) === this.videoFamily());
    }
    const live = this.pictureNode();
    return Boolean(live && live.state.arch === arch);
  }

  // ---- whose row it is -------------------------------------------------------------

  /** Whose row a side samples on: `chat`, `node` or `defaults`. */
  source(kind, arch = this.stillArch()) {
    if (this.own(kind)) return "chat";
    return this.followable(kind, arch) ? "node" : "defaults";
  }

  /** How many sides keep a row of the room's own — what the header pill says. */
  ownCount() {
    return ["still", "video"].filter((kind) => this.own(kind)).length;
  }

  /** Why a side samples on its defaults: what was there to follow, if
   *  anything. Empty for a side that is the node's or the chat's. */
  reason(kind) {
    if (this.source(kind) !== "defaults") return "";
    const family = kind === "still"
      ? t(S.PRESTAGE_ARCH_LABEL[this.stillArch()])
      : t(S.FAMILY_LABEL[this.videoFamily()]);
    const live = kind === "still" ? this.pictureNode() : this.clipNode();
    if (!live) {
      return kind === "still"
        ? t("No pre-stage under this chat to follow, so {family} samples on its defaults.", { family })
        : t("No piece under this chat to follow, so {family} samples on its defaults.", { family });
    }
    const theirs = kind === "still"
      ? t(S.PRESTAGE_ARCH_LABEL[live.state.arch] ?? live.state.arch)
      : t(S.FAMILY_LABEL[S.pieceFamily(live.piece)] ?? S.pieceFamily(live.piece));
    return t("The node is on {theirs}, and a row is a family's, so {family} samples on its defaults.",
             { theirs, family });
  }

  // ---- a row of the room's own ---------------------------------------------------

  own(kind) {
    return Boolean(this.rail()[OWN[kind]]);
  }

  /** The room's own row for a side, parsed, or null while the side follows.
   *  A row saved before the accelerators were kept out of it loses them on
   *  the way in, so a copy is never the machine's speed-ups frozen. */
  copy(kind) {
    const raw = this.rail()[OWN[kind]];
    if (!raw) { this.copies[kind] = null; return null; }
    if (!this.copies[kind]) {
      if (kind === "still") {
        this.copies.still = S.parsePreStage(raw);
      } else {
        const copy = S.parseTimeline(raw);
        copy.sampling = without(copy.sampling, accelKeys(S.pieceFamily(copy)));
        this.copies.video = copy;
      }
    }
    return this.copies[kind];
  }

  /** Write a side's own row back to the rail, after a change on it. */
  save(kind) {
    const copy = this.copies[kind];
    if (!copy) return;
    this.setRail({ [OWN[kind]]: kind === "still" ? S.serializePreStage(copy) : S.serializeTimeline(copy) });
  }

  /**
   * Give a side a row of the room's own, started from what it samples on
   * now: the node's row where the node can be followed, the family's
   * defaults where it cannot.
   *
   * The copy is a blank blob of the room's family with only the row and the
   * turbo switch written onto it — nothing else of the node's comes across,
   * because nothing else of the node's is the room's, and the accelerators
   * stay out (`rowOf`). It is a whole blob rather than the two fields because
   * the pills that draw and edit a row (`turboPills`, `PreStageRow`) read and
   * write one.
   */
  takeOwn(kind) {
    let copy;
    if (kind === "still") {
      const arch = this.stillArch();
      const live = this.followable("still") ? this.pictureNode() : null;
      const blank = { ...S.emptyPreStage(), arch, sampling: this.rowOf(kind, live?.body.widgetIO()) };
      if (live?.state.turbo?.[arch]) blank.turbo = { ...blank.turbo, [arch]: { ...live.state.turbo[arch] } };
      copy = S.parsePreStage(S.serializePreStage(blank));
    } else {
      const family = this.videoFamily();
      const live = this.followable("video") ? this.clipNode() : null;
      const blank = { ...S.emptyTimeline(), family, sampling: this.rowOf(kind, live?.body.widgetIO()) };
      if (live?.piece.turbo) blank.turbo = { ...live.piece.turbo };
      // The turbo file rides in the stack as well as on the switch; the
      // switch alone is a switch on nothing. Only that entry comes across.
      const worn = live?.piece.loras?.find((entry) => entry.name && entry.name === live.piece.turbo?.lora);
      if (worn) blank.loras = [{ ...worn }];
      copy = S.parseTimeline(S.serializeTimeline(blank));
    }
    this.copies[kind] = copy;
    this.save(kind);
  }

  /**
   * Move the room onto another family, the pinned copy with it. A row is a
   * family's: the copy goes through the same switch the node's blob does —
   * `PreStageRow.setArch` for a still, `state.setFamily` for a clip — so the
   * leaving family's numbers are set aside under its name and the arriving
   * one's come back, or its defaults where it was never dialled. Writing the
   * rail alone left Ideogram's guidance in force on Krea.
   */
  moveStill(arch) {
    const copy = this.copy("still");
    if (copy && copy.arch !== arch) {
      const io = blobIO(() => ({}), () => copy.sampling, (block) => { copy.sampling = block; });
      new PreStageRow({ state: copy, widgetIO: () => io, commit: () => {} }).setArch(arch);
      this.save("still");
    }
    this.setRail({ still_arch: arch });
  }

  moveVideo(family) {
    const copy = this.copy("video");
    if (copy && S.setFamily(copy, family)) this.save("video");
    this.setRail({ video_family: family });
  }

  /** Drop the room's own row; the side follows the node again. */
  follow(kind) {
    this.copies[kind] = null;
    this.setRail({ [OWN[kind]]: "" });
  }

  /** The row's values off an io, by name — what `takeOwn` copies. The seed
   *  and the accelerators stay behind. */
  rowOf(kind, io) {
    const row = {};
    if (!io) return row;
    const drop = new Set([...WIDGET_ONLY, ...(kind === "video" ? accelKeys(this.videoFamily()) : [])]);
    for (const name of SAMPLING_WIDGETS) {
      if (drop.has(name)) continue;
      const value = io.value(name, undefined);
      if (value !== undefined) row[name] = value;
    }
    return row;
  }

  // ---- what a render samples on ---------------------------------------------------

  /**
   * The row for a render of `kind` -> `{sampling, turbo, loras, widgets}`.
   *
   * The chat's own: the copy's row, its switch and the turbo file in its
   * stack — and, on the clip side, the node's accelerators laid under it
   * where the node can be followed, since those are the machine's and not
   * the chat's. Following: the node's blob-level row, its switch, that file,
   * and the node's widget values as the queue would read them (the blob wins
   * for the row, the widgets are the fallback — `sampling.resolve`).
   * Neither: empty, which is the family's defaults all the way down.
   *
   * `arch` is the image arch a still is drawn on where it is not the room's
   * own — a cited picture changed on the *Edits* family. A row is a
   * family's, so the copy's steps and guidance are read only where the copy
   * is on that arch, and the node's only where the node is; the turbo block
   * is per arch on both and is read for the one asked. Otherwise the
   * family's own defaults, which is what a node on another family gets too.
   */
  row(kind, arch = this.stillArch()) {
    const copy = this.copy(kind);
    const live = this.followable(kind, arch) ? this.liveRow(kind, arch) : null;
    if (!copy) return live ?? { sampling: {}, turbo: null, loras: [], widgets: {} };
    const own = this.rowFrom(kind, copy, {}, arch);
    if (kind === "video" && live) {
      const keys = accelKeys(this.videoFamily());
      own.sampling = { ...only(live.sampling, keys), ...own.sampling };
      own.widgets = only(live.widgets, keys);
    }
    return own;
  }

  /** The node's row, as the queue would read it. Only where `followable`. */
  liveRow(kind, arch = this.stillArch()) {
    if (kind === "still") {
      const { body, state } = this.pictureNode();
      return this.rowFrom(kind, state, without(this.values(body.widgetIO(), body.samplingWidgets), new Set(WIDGET_ONLY)), arch);
    }
    const { body, piece } = this.clipNode();
    return this.rowFrom(kind, piece, without(this.values(body.widgetIO(), body.widgets), new Set(WIDGET_ONLY)));
  }

  rowFrom(kind, blob, widgets, arch = this.stillArch()) {
    if (kind === "still") {
      // The room's own arch reads the row whatever the blob says it was
      // written for — a copy taken before the pill moved keeps working;
      // any other arch reads it only when the blob is on that arch.
      const own = arch === this.stillArch() || blob.arch === arch;
      return { sampling: own ? { ...(blob.sampling ?? {}) } : {}, turbo: blob.turbo?.[arch] ?? null,
               loras: [], widgets: own ? widgets : {} };
    }
    const turbo = blob.turbo ?? null;
    const worn = (blob.loras ?? []).filter((entry) => entry.name && entry.name === turbo?.lora);
    return { sampling: { ...(blob.sampling ?? {}) }, turbo, loras: worn.map((entry) => ({ ...entry })), widgets };
  }

  /** The widget values an io holds, by name. */
  values(io, widgets) {
    const out = {};
    for (const name of Object.keys(widgets ?? {})) {
      const value = io.value(name, undefined);
      if (["string", "number", "boolean"].includes(typeof value)) out[name] = value;
    }
    return out;
  }

  // ---- the row, said in a line ---------------------------------------------------

  /**
   * A side's row as one line for the sheet: "8 steps · cfg 1 · euler · beta
   * · shift 6 · turbo good". The family's own controls in the family's own
   * order, at the values the render would sample on — the blob's over the
   * widgets' over the family's defaults — so a followed row reads the node
   * and a defaults row reads the manifest.
   */
  summary(kind, arch = this.stillArch()) {
    const row = this.row(kind, arch);
    const values = { ...row.widgets, ...row.sampling };
    const parts = [];
    if (kind === "video") {
      const family = this.videoFamily();
      for (const w of S.widgetsOf(family)) {
        if (w.group !== "sampler") continue;
        const value = values[w.id] ?? w.default;
        if (value === undefined || value === null || value === "") continue;
        if (typeof value === "boolean") { if (value) parts.push(t(w.label)); continue; }
        parts.push(w.id === "steps" ? t("{n} steps", { n: value }) : `${t(w.label)} ${value}`);
      }
    } else {
      const base = arch === "ideogram4"
        ? { steps: S.PRESTAGE_IDEOGRAM_STEPS[S.emptyPreStage().quality], ...S.PRESTAGE_IDEOGRAM_ROW }
        : S.PRESTAGE_BASE_ROW[arch];
      const merged = { ...base, ...values };
      if (merged.steps !== undefined) parts.push(t("{n} steps", { n: merged.steps }));
      if (merged.cfg !== undefined) parts.push(`cfg ${merged.cfg}`);
      if (merged.sampler_name) parts.push(String(merged.sampler_name));
      if (merged.scheduler) parts.push(String(merged.scheduler));
    }
    if (row.turbo?.on) parts.push(t("turbo {quality}", { quality: t(row.turbo.quality ?? "good") }));
    return parts.join(" · ");
  }

  // ---- following ------------------------------------------------------------------

  /**
   * Be told when either node redraws. The bodies and their editors each have
   * one `onRender` slot, and the shell holds the body's — so this chains
   * behind whatever is there rather than taking the slot. Re-laid on every
   * fire, because editors are rebuilt (an arch switch mounts a new one) and
   * the shell re-assigns the body's slot on every remount; a link is marked
   * so it is never laid twice over itself.
   */
  watch(fn) {
    this.followers.add(fn);
    this.chainAll();
    return () => this.followers.delete(fn);
  }

  chainAll() {
    for (const body of [this.clipNode()?.body, this.pictureNode()?.body]) if (body) this.chain(body);
  }

  chain(body) {
    for (const host of [body, body.editor, body.faceEditor]) {
      if (!host || host.onRender?.mmcChat) continue;
      const was = host.onRender;
      host.onRender = () => {
        was?.();
        for (const fn of this.followers) fn();
        this.chainAll();
      };
      host.onRender.mmcChat = true;
    }
  }

  // ---- the chat's own row, drawn -------------------------------------------------

  /**
   * The clip side's own row: steps, cfg, the schedule, the turbo switch —
   * over the copy, through `blobIO`. Nothing while the side follows: a
   * followed row is edited on the node. `redraw` is the sheet's repaint
   * after a pill writes.
   */
  clipRow(redraw) {
    const copy = this.copy("video");
    if (!copy) return null;
    const family = S.pieceFamily(copy);
    const widgets = ownWidgets("video", family, this.clipNode()?.body.widgets);
    const io = blobIO(() => ({}), () => copy.sampling, (block) => { copy.sampling = block; });
    const set = (name, value) => { io.set(name, value); this.save("video"); redraw(); };
    const commit = () => { syncTurbo(copy, io); this.save("video"); redraw(); };
    return samplingBar({
      family, widgets, value: io.value, set, perSegment: false, container: copy, accel: false,
      turbo: S.turboOf(family) ? turboPills({ container: copy, value: io.value, set, onCommit: commit }) : [],
    });
  }

  /** The picture side's own row, the pre-stage's own turbo pill included. */
  pictureRow(redraw) {
    const copy = this.copy("still");
    if (!copy) return null;
    const io = blobIO(() => ({}), () => copy.sampling, (block) => { copy.sampling = block; });
    const host = { state: copy, widgetIO: () => io, commit: () => { this.save("still"); redraw(); } };
    const widgets = ownWidgets("still", null, this.pictureNode()?.body.samplingWidgets);
    const set = (name, value) => { io.set(name, value); this.save("still"); redraw(); };
    const row = new PreStageRow(host);
    return samplingBar({
      widgets, value: io.value, set, perSegment: false,
      turbo: row.renderTurbo(),
    });
  }
}
