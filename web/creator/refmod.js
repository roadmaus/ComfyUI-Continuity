// Saving somebody as a saved reference: the ledger, and the job behind it.
//
// A RefMod is the DiT half of a reference already encoded — one H3 VAE latent
// in a safetensors file, the format `ComfyUI-MiniMaxH3Mod` reads and writes
// (`creator/refmod.py` says the rest). What it is *for* here is a cast member:
// their looks come from a few pictures, and each picture is a few hundred
// reference tokens riding through every sampling step. Saved as compressed mods
// they are sixty-four each, and a shot that could carry two of them can carry
// six. Saved as full mods they are the same encode cached on disk, shareable as
// one file per picture.
//
// So the door is the *ledger*, a line under the member's tiles that says what
// their looks cost a render and offers to save them: encode every picture they
// are built out of, attach the mods where the pictures were, and point their
// looks at the mods. The pictures leave the piece unless somebody else still
// needs them — another member, or a sentence that writes the handle by hand —
// which is the same bargain removing a member makes with their files. The
// first version of this was a cube icon in the card's header, which said none
// of that; the number is the argument, so the number is what is drawn.
//
// The host does the attaching, for the reason the shelf's `keep` and `library`
// are the host's: a shelf does not know whether a member's pictures live on a
// card's row or in the piece's pool, and there are two hosts.

import { isRefMod, listAssets, makeRefMod, refmodFileUrl, viewUrl } from "./api.js";
import { el, icon } from "./dom.js";
import { t } from "./i18n.js";
import * as S from "./state.js";

// ---- what it costs ------------------------------------------------------------
//
// The reason a mod exists is a number, so the number is drawn wherever a member's
// pictures are: the *ledger* under their tiles says what they cost a render and
// offers the one thing that changes it. A mod's count is read off its header
// (the listing carries it) and is exact. A picture's is an estimate from the
// arithmetic the encoder does — 16 px a latent cell, 2x2 cells a token, so a
// token is 32x32 source pixels: `match` is the generation's own area over
// that, `max` is a 2048 short edge over that, which is 4096 tokens for a square
// picture and more for a wide one. Close enough to choose by; marked ≈.

/** Tokens a compressed mod of a square picture costs: the 48-grid the maker
 *  pools a still to (`routes/refmod.DEFAULT_GRID`), 24x24 tokens. Measured:
 *  the sibling pack's 16-grid stains a face; 48 renders like the full mod. */
export const COMPRESSED_TOKENS = 576;
/** Tokens one frame of a stack costs: the sibling pack's square 16-grid. */
export const STACK_FRAME_TOKENS = 64;
/** Tokens a full mod of a square picture costs, at the maker's 1024 edge. */
export const FULL_TOKENS = 1024;
/** Where a member's mods are written, under models/refmods/. */
export const SUBFOLDER = "cast";
// The canvas assumed for a `match` estimate where no host can say — the
// library sheet, whose member is not on any node yet.
const NOMINAL_CANVAS = { width: 992, height: 576 };

// What a stack costs, by the maker's defaults: every still is one frame of the
// grid, a clip is 22 source frames read as six latent ones. See
// `routes/refmod.STACK_FRAMES`.
const STACK_CLIP_FRAMES = 6;

/** The three ways to save somebody's looks, in the words the menu uses.
 *
 *  `stack` leads where it applies: it is what the sibling pack means by a
 *  character — every still and clip in one file, cited as one `<Video n>`,
 *  motion included — and it is the shape their downloads come in. The two
 *  per-picture modes follow; `compressed` before `full` because it is the one
 *  with a reason to exist, the token budget. */
export const MODES = [
  {
    key: "stack", label: "One file — everything stacked",
    note: "Every still and clip in their looks, each pooled to a 16×16 grid and laid "
        + "end to end as one video RefMod. One portable file that includes their "
        + "motion; not a budget move — a clip is six frames of tokens.",
  },
  {
    key: "compressed", label: "Compressed",
    note: "Pooled to a 48-grid and refined against the full encode. Renders "
        + "like the full mod at under half its tokens; pooled further, a face "
        + "comes back stained.",
  },
  {
    key: "full", label: "Full",
    note: "The encode at a 1024 short edge, saved so it is never redone. Renders "
        + "the same as the picture at that size.",
  },
];

// A picture's aspect (long over short), measured off its thumbnail the first
// time the ledger asks. The measure is asynchronous; the caller is told when it
// lands and draws again.
const aspects = new Map();
function aspectOf(filename, onKnown) {
  const hit = aspects.get(filename);
  if (hit !== undefined) return hit;
  aspects.set(filename, null);
  if (typeof Image === "undefined") return null;
  const measure = new Image();
  measure.onload = () => {
    const { naturalWidth: w, naturalHeight: h } = measure;
    if (w && h) { aspects.set(filename, Math.max(w, h) / Math.min(w, h)); onKnown?.(); }
  };
  measure.src = viewUrl(filename, { preview: true });
  return null;
}

/** What one picture costs a render, ≈. `canvas` is the generation's
 *  `{width, height}` where the host knows it. */
export function pictureTokens(entry, canvas, onKnown) {
  if (S.refSize(entry) === "match") {
    const { width, height } = canvas ?? NOMINAL_CANVAS;
    return Math.round((width * height) / 1024);
  }
  return Math.round(4 * FULL_TOKENS * (aspectOf(entry.filename, onKnown) ?? 1));
}

/** What one picture would cost as a mod of `mode`. */
export function modTokens(entry, mode, onKnown) {
  // Full is sized on the short edge, so a wide picture costs more; the
  // compressed grid sits on the long edge, so a wide picture costs less.
  const aspect = aspectOf(entry.filename, onKnown) ?? 1;
  if (mode === "compressed") return Math.round(COMPRESSED_TOKENS / aspect);
  return Math.round(FULL_TOKENS * aspect);
}

// The listing of every mod on the machine, by path. `listAssets` caches it and
// `makeRefMod` and friends invalidate that cache, so asking again is cheap and
// always current; what is kept here is the synchronous view a redraw reads.
let known = new Map();
export async function modRows() {
  const rows = await listAssets({ root: "refmods" });
  known = new Map(rows.map((row) => [row.path, row]));
  return known;
}
/** The listing row of one mod, or undefined while the listing is on its way
 *  (`onKnown` fires when it lands) — or null for a mod the listing lacks. */
export function modRow(path, onKnown) {
  if (known.has(path)) return known.get(path);
  modRows().then(() => onKnown?.(), () => {});
  return known.size ? null : undefined;
}

/** What a listing row is, in the ledger's words: a stack, or compressed / full. */
export function modeWord(row) {
  if (row.source === "stack") return t("stack");
  return t(row.mode === "training" ? "compressed" : "full");
}

/** A count for a shut line: 558 stays 558, 4,096 becomes 4.1k. */
export function shortTokens(n) {
  return n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k` : String(n);
}
const long = (n) => n.toLocaleString();

/**
 * The sum over a member's looks: `entries` are their `from` stills — assets on
 * a card, or a stored member's files — each `{filename, kind, ref_size}`.
 * -> `{pictures, mods, picTokens, modTokens, modes, exact, rows}`.
 */
export function cost(entries, canvas, onKnown) {
  const out = { pictures: 0, clips: 0, mods: 0, picTokens: 0, modTokens: 0, modes: new Set(),
                exact: true, rows: [] };
  for (const entry of entries) {
    if (isRefMod(entry.filename)) {
      out.mods += 1;
      const row = modRow(entry.filename, onKnown);
      if (row) { out.modTokens += row.tokens ?? 0; out.modes.add(row.mode); out.rows.push(row); }
      else out.exact = false;
    } else if (entry.kind === "video") {
      // A clip's tokens are its latent frames times a 768-edge grid — a number
      // that needs the clip's length, which nothing here has. Counted, not
      // priced; the line says so.
      out.clips += 1;
      out.exact = false;
    } else {
      out.pictures += 1;
      out.picTokens += pictureTokens(entry, canvas, onKnown);
      out.exact = false;
    }
  }
  return out;
}

/** What a member costs, for their shut line: "≈4.1k tok", or "128 tok" when
 *  every one of their looks is a mod. Empty where they have no looks. */
export function costMark(entries, canvas, onKnown) {
  const c = cost(entries, canvas, onKnown);
  if (!c.pictures && !c.mods && !c.clips) return null;
  const total = c.picTokens + c.modTokens;
  const plus = c.clips ? "+" : "";
  return { text: `${c.exact ? "" : "≈"}${shortTokens(total)}${plus} tok`, saved: c.exact };
}

/** The mode menu's rows, each naming what it would cost. */
export function modeRows(entries, onPick, onKnown) {
  const fresh = entries.filter((entry) => !isRefMod(entry.filename));
  const stills = fresh.filter((entry) => entry.kind !== "video");
  const clips = fresh.length - stills.length;
  // A stack of one still is a compressed mod wearing the wrong kind; offered
  // only where there is something to stack.
  const offered = MODES.filter((mode) => mode.key !== "stack" || fresh.length > 1 || clips);
  return offered.map((mode) => {
    const tokens = mode.key === "stack"
      ? (stills.length + clips * STACK_CLIP_FRAMES) * STACK_FRAME_TOKENS
      : stills.reduce((sum, entry) => sum + modTokens(entry, mode.key, onKnown), 0);
    const approx = mode.key !== "stack" || clips;
    return {
      label: t("{mode} — {tokens} tokens", {
        mode: t(mode.label), tokens: (approx ? "≈" : "") + long(tokens) }),
      note: mode.key !== "stack" && clips
        ? `${t(mode.note)} ${t("Stills only — a clip is stacked, not saved on its own.")}`
        : t(mode.note),
      onPick: () => onPick(mode.key),
    };
  });
}

/**
 * The ledger: one line under a member's looks that says what they cost and
 * what to do about it. Drawn by both hosts of the shelf and by the library
 * sheet, so the sentence is the same in all three places.
 *
 *   entries   their `from` stills, `{filename, kind, ref_size}`
 *   canvas    the generation's `{width, height}`, or null
 *   busy      `{count, mode, progress}` while their pictures are on the queue
 *   note      what went wrong the last time, or null
 *   onSave    called with the button as anchor; the host opens the mode menu
 *   onLibrary open the library on the saved file, or null
 *   onKnown   redraw — a measure or the listing landed
 *
 * -> an element, or null where they have no looks to account for.
 */
export function ledger({ entries, canvas = null, busy = null, note = null,
                         onSave = null, onLibrary = null, onKnown = null }) {
  const c = cost(entries, canvas, onKnown);
  if (!c.pictures && !c.mods && !busy) return null;
  const root = el("div", { class: "mmc-cast-ledger" });
  const what = el("span", { class: "mmc-cast-ledger-what" });
  root.appendChild(what);
  const say = (lead, ...rest) => {
    what.replaceChildren(el("b", { text: lead }), ...rest.filter(Boolean).flatMap((part) => [
      el("span", { class: "mmc-cast-ledger-dot", text: " · " }),
      typeof part === "string" ? el("span", { text: part }) : part,
    ]));
  };
  const n = (text) => el("span", { class: "mmc-cast-ledger-n", text });
  const sizes = () => {
    const kinds = new Set(entries.filter((e) => !isRefMod(e.filename)).map((e) => S.refSize(e)));
    return [...kinds].map((k) => t(k)).join("/");
  };
  const fresh = c.pictures + c.clips;
  const pictureWords = (count) => t(count === 1 ? "{count} picture" : "{count} pictures", { count });
  const clipWords = (count) => t(count === 1 ? "{count} clip" : "{count} clips", { count });
  const modWords = (count) => t(count === 1 ? "{count} RefMod" : "{count} RefMods", { count });
  // "1 picture", "2 pictures + 1 clip" — what is encoded fresh; and the same
  // with the size it is encoded at.
  const freshParts = () => [c.pictures ? pictureWords(c.pictures) : null,
                            c.clips ? clipWords(c.clips) : null].filter(Boolean).join(" + ");
  const freshWords = () => t("{what} at {size}", { what: freshParts(), size: sizes() });
  const freshTokens = () => `≈${long(c.picTokens)}${c.clips ? "+" : ""} ${t("tokens")}`;

  if (busy) {
    root.classList.add("busy");
    const stills = entries.filter((e) => !isRefMod(e.filename) && e.kind !== "video");
    const after = busy.mode === "stack"
      ? (stills.length + c.clips * STACK_CLIP_FRAMES) * STACK_FRAME_TOKENS
      : stills.reduce((sum, e) => sum + modTokens(e, busy.mode, onKnown), 0);
    say(t(busy.mode === "stack" ? "Stacking {count} files into one…"
          : busy.count === 1 ? "Encoding {count} picture…" : "Encoding {count} pictures…", { count: busy.count }),
        t(busy.mode === "compressed" ? "compressed" : busy.mode === "stack" ? "stack" : "full"),
        n(`${freshTokens().replace(` ${t("tokens")}`, "")} → ≈${long(after)} ${t("tokens")}`));
    root.appendChild(el("span", { class: "mmc-cast-ledger-queued", text: t("on the queue") }));
    const bar = el("span", { class: "mmc-cast-ledger-bar" },
                   [el("i", { style: { width: `${Math.round((busy.progress ?? 0) * 100)}%` } })]);
    root.appendChild(bar);
  } else if (fresh && !c.mods) {
    say(t("Encoded on every render"), freshWords(), n(freshTokens()));
    if (onSave) {
      root.appendChild(el("button", {
        class: "mmc-cast-ledger-act on",
        title: t("Encode their looks once and save the result as a file the render "
               + "reads instead — one stacked file, or one per picture."),
        onclick: (event) => onSave(event.currentTarget),
      }, [icon("cube", 12), el("span", { text: t(fresh === 1 ? "Save as RefMod ▾" : "Save as RefMods ▾") })]));
    }
  } else if (fresh && c.mods) {
    say(`${modWords(c.mods)} + ${freshParts()}`, n(`${long(c.modTokens)} + ${freshTokens()}`));
    if (onSave) {
      root.appendChild(el("button", {
        class: "mmc-cast-ledger-act on",
        onclick: (event) => onSave(event.currentTarget),
      }, [icon("cube", 12), el("span", { text: t(fresh === 1 ? "Save the picture too ▾" : "Save the pictures too ▾") })]));
    }
  } else {
    root.classList.add("saved");
    const modes = [...new Set(c.rows.map(modeWord))].join("/");
    const folder = c.rows.length === 1
      ? el("span", { class: "mmc-cast-ledger-path", text: c.rows[0].path.replace(/^refmod:/, "refmods/") })
      : null;
    say(t(c.mods === 1 ? "Saved as a RefMod" : "Saved as {count} RefMods", { count: c.mods }),
        modes || null,
        c.exact ? n(`${long(c.modTokens)} ${t("tokens")}`) : null,
        folder);
    if (c.rows.length === 1) {
      root.appendChild(el("a", {
        class: "mmc-cast-ledger-act", href: refmodFileUrl(c.rows[0].path), download: "",
        title: t("The .safetensors itself — drop it in another machine's models/refmods, "
               + "or in the sibling pack's loader."),
      }, [icon("download", 12), el("span", { text: t("Download") })]));
    }
    if (onLibrary) {
      root.appendChild(el("button", {
        class: "mmc-cast-ledger-act",
        onclick: () => onLibrary(c.rows[0]?.path ?? null),
      }, [el("span", { text: t("Show in library") })]));
    }
  }
  if (note) root.appendChild(el("span", { class: "mmc-cast-ledger-note", text: note }));
  return root;
}

// A member's `takes` word, as the mod format's `concept_type`. Metadata for
// their loaders' filters; nothing here reads it back.
const CONCEPT = { person: "identity", object: "generic", scene: "background", style: "style" };

/** Their looks as the ledger counts them: everything their looks come from,
 *  attached here — stills, clips, and mods of either kind. */
export function looks(subject, assets) {
  return (subject.from ?? [])
    .map((handle) => (assets ?? []).find((a) => a.handle === handle))
    .filter((a) => a && (a.kind === "image" || a.kind === "video") && a.role === "reference"
                   && a.track !== "sound");
}

/** What a member can be saved out of, per mode. Never a mod already, never a
 *  cut-out sheet — that is a layout the encoder builds at render time. The
 *  per-picture modes take stills alone; a stack takes clips too, which is the
 *  point of it. */
export function keepable(subject, assets, mode = "compressed") {
  return looks(subject, assets).filter((a) => !isRefMod(a.filename) && !S.isPlate(a)
                                             && (mode === "stack" || a.kind === "image"));
}

/**
 * Keep `subject`'s pictures as mods and rebuild their looks out of them.
 *
 * `host` is what the two shelf hosts know and the shelf does not:
 *   vae         the H3 video VAE the piece is set to, by filename
 *   list()      the asset array a new reference lands in
 *   nextHandle(kind)  a fresh handle for that array
 *   texts()     every text a handle could be written into by hand
 *   cast()      the whole cast, to see who else claims a picture
 *   drop(handles)     take pictures nobody needs any more off the piece
 *   onProgress  the queue's progress, if the host shows one
 *
 * -> the picker rows of the mods written, in the order of the pictures.
 */
export async function keepAsMod(subject, assets, mode, host) {
  const stack = mode === "stack";
  const sources = keepable(subject, assets, mode);
  if (!sources.length) {
    throw new Error(t("Nothing to save — hang a picture on them first."));
  }
  // The words on each file go into the stack's own description: one file
  // cannot carry a note per picture, and "her face, front-lit; the coat" is
  // worth keeping in its header.
  const notes = S.subjectNotes(subject);
  const noted = sources.map((a) => notes[a.handle]).filter(Boolean);
  const answer = await makeRefMod({
    name: subject.handle,
    subfolder: SUBFOLDER,
    sources: sources.map((a) => a.filename),
    mode: stack ? "stack" : mode === "full" ? "full" : "compressed",
    description: [subject.description ?? "", ...(stack ? noted : [])].filter(Boolean).join("; "),
    concept: CONCEPT[subject.takes ?? "person"] ?? "generic",
    vae: host.vae ?? "",
  }, { onProgress: host.onProgress });
  const rows = answer?.mods ?? [];
  if (!rows.length) throw new Error(t("the server saved nothing"));

  // One mod per picture, in the picture's place: same narrowing, same words —
  // or one stack in the place of all of them, wearing the first's narrowing.
  // The words are read before the looks move: `subjectNotes` keeps only the
  // notes on files the member still claims.
  const list = host.list();
  const swapped = new Map();
  rows.forEach((row, index) => {
    const source = stack ? sources[0] : sources[index];
    const kind = row.kind === "video" ? "video" : "image";
    const entry = {
      handle: host.nextHandle(kind),
      kind,
      role: "reference",
      filename: row.path,
      ...(kind === "video" ? { track: "picture" } : {}),
      ...(source?.takes ? { takes: source.takes } : {}),
    };
    list.push(entry);
    if (stack) for (const a of sources) swapped.set(a.handle, entry.handle);
    else if (source) swapped.set(source.handle, entry.handle);
  });
  // A stack stands for several handles at once; the member's looks list it once.
  const from = (subject.from ?? []).map((handle) => swapped.get(handle) ?? handle);
  subject.from = from.filter((handle, index) => from.indexOf(handle) === index);
  const moved = { ...notes };
  for (const [old, fresh] of swapped) {
    if (!notes[old]) continue;
    if (!stack) moved[fresh] = notes[old];
    delete moved[old];
  }
  if (Object.keys(moved).length) subject.notes = moved;
  else delete subject.notes;

  // The pictures, unless somebody still needs them. Another member's claim or
  // a handle written by hand keeps a file; a mod standing in for it does not.
  const held = new Set();
  for (const other of host.cast()) {
    if (other === subject) continue;
    for (const handle of S.subjectFiles(other)) held.add(handle);
  }
  const texts = host.texts();
  const gone = [...swapped.keys()].filter(
    (handle) => !held.has(handle) && !S.handleWritten(texts, handle));
  if (gone.length) host.drop(gone);
  return rows;
}
