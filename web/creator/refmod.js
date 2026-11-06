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
// are built out of and hang the mod on the picture. The picture stays — it is
// the reference every family can read, and what a still family is handed —
// and it carries its renditions by latent space (`asset.mods`): the family
// rendering it takes the one in its own space and encodes the picture
// otherwise. A stack is the exception: one video file standing for every
// still and clip, the sibling pack's own shape for a character, and it takes
// the pictures' place the way it always did. The first version of this was a
// cube icon in the card's header, which said none of that; the number is the
// argument, so the number is what is drawn.
//
// A latent belongs to one VAE, so "a mod" is a mod *for a family*: H3's, or
// Flux 2 Klein's, made from the same picture through that family's VAE. The
// ledger is drawn for the piece's own family and the menu offers the others
// this machine could encode for (`modFamilies`), so a member on an H3 piece
// can carry a Klein rendition for the chat's stills.
//
// The host does the attaching, for the reason the shelf's `keep` and `library`
// are the host's: a shelf does not know whether a member's pictures live on a
// card's row or in the piece's pool, and there are two hosts.

import { isRefMod, listAssets, makeRefMod, remakeRefMod, viewUrl } from "./api.js";
import { t } from "./i18n.js";
import { FAMILIES, VIDEO_FAMILIES, family as familyManifest } from "./manifest.js";
import * as S from "./state.js";

// ---- which families keep mods ---------------------------------------------------

/** H3's latent space — every mod made before the spaces arrived is in it,
 *  and it is what a host that names no family gets. */
export const DEFAULT_SPACE = "h3_video";

/** A family's mod table (`capabilities.refmod`), or null where it keeps none. */
export const refmodOf = (id) => familyManifest(id)?.capabilities?.refmod ?? null;

/**
 * Every family a cast member can be sent to, the piece's own first — one
 * entry per family in the catalog, whether or not it keeps mods. What the
 * wears panel draws a tab for, and what `keepAsMod` is handed as `family`.
 *
 *   id, label     the family's
 *   video         renders video (a piece's family) rather than a still
 *   here          this is the piece's family
 *   reads         `{pictures, clips, voice}` — which of a member's files the
 *                 family reads at all: a video family's reference caps, a
 *                 still family's `max_refs`. Mirrors `chat.ref_limit`.
 *   adapter       reads pictures only through a LoRA in its stack (Krea 2 —
 *                 `capabilities.refs.needs_lora`). Mirrors `chat.needs_adapter`.
 *   refmod        keeps saved references; then `space`, `vae`, `clips`, `grid`
 *                 as the family's mod table says — `vae` the file that
 *                 family's encoder would use here, by the piece's own weights
 *                 for its family and the machine's remembered picks for the
 *                 rest (`models.rememberedWeights`), or "" where none is picked.
 */
export function castFamilies(pieceId, pieceVae, remembered = {}) {
  const out = [];
  for (const manifest of FAMILIES) {
    const own = manifest.id === pieceId;
    const video = VIDEO_FAMILIES.includes(manifest.id);
    const max = manifest.reference?.max ?? {};
    const stills = Number(manifest.prompt?.max_refs ?? 0);
    const table = manifest.capabilities?.refmod ?? null;
    out.push({
      id: manifest.id, label: manifest.label, video, here: own,
      reads: {
        pictures: video ? (max.image ?? 0) > 0 : stills > 0,
        clips: video && (max.video ?? 0) > 0,
        voice: video && (max.audio ?? 0) > 0,
      },
      adapter: Boolean(manifest.capabilities?.refs?.needs_lora),
      adapterHints: [...(manifest.capabilities?.refs?.adapter_hints ?? [])],
      refmod: Boolean(table),
      ...(table ? {
        space: table.space, clips: Boolean(table.clips), grid: table.grid,
        vae: own ? (pieceVae ?? "") : (remembered?.[manifest.id]?.vae ?? ""),
      } : {}),
    });
  }
  out.sort((a, b) => (a.here ? -1 : b.here ? 1 : 0));
  return out;
}

/** The families a member's pictures can be saved for, the piece's first:
 *  the `castFamilies` entries that keep mods. */
export const modFamilies = (pieceId, pieceVae, remembered = {}) =>
  castFamilies(pieceId, pieceVae, remembered).filter((family) => family.refmod);

/** The mod an entry is read from in `space`: itself, or the rendition it
 *  carries — or null where the family would encode it. */
export const modIn = (entry, space = DEFAULT_SPACE) =>
  isRefMod(entry?.filename) ? entry.filename : (entry?.mods?.[space] ?? null);

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
/** The same two for Flux 2 Klein: a 1 MP picture is a 64x64 grid and every
 *  cell is a token there (the VAE packs the 2x2 into its channels), so full
 *  is 4,096 and compressed — the family's 32-grid — a quarter of it. */
export const KLEIN_FULL_TOKENS = 4096;
export const KLEIN_COMPRESSED_TOKENS = 1024;
/** Tokens a clip kept on its own costs per latent frame, at the 768 reference
 *  canvas: a 48x27 grid is 24x14 tokens for a 16:9 clip. Compressed to the
 *  family's grid it is what a stack frame is. */
export const CLIP_FRAME_TOKENS = 336;
/** Latent frames a clip mod holds at the maker's defaults: 22 source frames
 *  read as six. */
export const CLIP_FRAMES = 6;
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
  {
    key: "clip", label: "Each clip — its own file",
    note: "A clip encoded whole at the 768 reference canvas, up to a minute of "
        + "it, and kept as one video RefMod: long motion for a few hundred "
        + "tokens a frame, read off the file instead of decoded every render.",
  },
];
// The notes above are H3's; Klein's numbers differ and the menu says so.
const KLEIN_NOTES = {
  compressed: "Pooled to a 32-grid on the long edge and refined against the full "
            + "encode — a quarter of the tokens. Unmeasured against the picture yet.",
  full: "The encode at 1 MP, as Klein reads a reference, saved so it is never redone.",
};

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

/** What one picture would cost as a mod of `mode`, in `space`. */
export function modTokens(entry, mode, onKnown, space = DEFAULT_SPACE) {
  if (entry.kind === "video") {
    return CLIP_FRAMES * (mode === "compressed" ? STACK_FRAME_TOKENS : CLIP_FRAME_TOKENS);
  }
  const aspect = aspectOf(entry.filename, onKnown) ?? 1;
  if (space === "flux2") {
    // Sized to an area, so the aspect changes nothing but the grid's shape.
    return mode === "compressed" ? KLEIN_COMPRESSED_TOKENS : KLEIN_FULL_TOKENS;
  }
  // Full is sized on the short edge, so a wide picture costs more; the
  // compressed grid sits on the long edge, so a wide picture costs less.
  if (mode === "compressed") return Math.round(COMPRESSED_TOKENS / aspect);
  return Math.round(FULL_TOKENS * aspect);
}

// The listing of every mod on the machine, by path. `listAssets` caches it and
// `makeRefMod` and friends invalidate that cache, so asking again is cheap and
// always current; what is kept here is the synchronous view a redraw reads.
let known = new Map();
// When the listing last landed (0: never), and the one on its way, so a
// redraw asking about twenty tiles asks the server once.
let listedAt = 0;
let pending = null;
// How old a listing may be before a redraw asks again: files deleted on disk
// behind the page's back are noticed, without a request per redraw.
const STALE_MS = 30000;
export async function modRows() {
  const rows = await listAssets({ root: "refmods" });
  known = new Map(rows.map((row) => [row.path, row]));
  listedAt = Date.now();
  return known;
}
function refresh() {
  if (!pending) pending = modRows().finally(() => { pending = null; });
  return pending;
}
// What a redraw would draw differently about one mod: there or not, and what
// it costs. A fresh listing that changes none of it redraws nothing.
const rowKey = (row) => (row ? `${row.mode}|${row.tokens}|${row.size}|${row.source_present}` : String(row));
/** The listing row of one mod, or undefined while the listing is on its way
 *  — or null for a mod the listing lacks: its file is gone.
 *
 *  `onKnown` fires only when what the answer would be has changed. It used to
 *  fire after every listing a missing mod asked for, so a member whose file
 *  had been deleted asked again on the redraw that drew it, forever: the
 *  listing endpoint hammered and the card redrawn under the cursor too fast
 *  to open, edit or delete (issue #121). */
export function modRow(path, onKnown) {
  const now = known.has(path) ? known.get(path) : listedAt ? null : undefined;
  if (!listedAt || Date.now() - listedAt > STALE_MS) {
    refresh().then(() => {
      if (rowKey(known.get(path) ?? null) !== rowKey(now)) onKnown?.();
    }, () => {});
  }
  return now;
}

/** The renditions `entries` carry in `space` whose files are gone from
 *  models/refmods, by path. Empty while the listing is on its way. */
export function missingMods(entries, space = DEFAULT_SPACE, onKnown = null) {
  return entries
    .map((entry) => entry?.mods?.[space])
    .filter((path) => path && modRow(path, onKnown) === null);
}

/**
 * Take `space`'s renditions off `files` — every one, or only those in `paths`
 * — so the pictures are pictures again for that family and can be saved
 * afresh. -> how many were taken off.
 *
 * Only the reference is forgotten; the file stays in models/refmods, where
 * another piece or a workflow may still cite it, and the library's Saved
 * references column is where it is deleted. A rendition whose file has gone
 * is the case this exists for: the render refuses it by name (`encode._mod_of`)
 * and nothing else in the card could take it off.
 */
export function forgetMods(files, space = DEFAULT_SPACE, paths = null) {
  const only = paths ? new Set(paths) : null;
  let count = 0;
  for (const file of files ?? []) {
    const path = file?.mods?.[space];
    if (!path || (only && !only.has(path))) continue;
    const rest = { ...file.mods };
    delete rest[space];
    if (Object.keys(rest).length) file.mods = rest;
    else delete file.mods;
    count += 1;
  }
  return count;
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
 * a card, or a stored member's files — each `{filename, kind, ref_size, mods}`.
 * -> `{pictures, mods, picTokens, modTokens, modes, exact, rows}`. Counted for
 * one family: an entry is a mod where it is one, or carries a rendition in
 * `space`; a picture whose only mod is another family's is a picture here.
 */
export function cost(entries, canvas, onKnown, space = DEFAULT_SPACE) {
  const out = { pictures: 0, clips: 0, mods: 0, picTokens: 0, modTokens: 0, modes: new Set(),
                exact: true, rows: [], missing: [] };
  for (const entry of entries) {
    const path = modIn(entry, space);
    if (path) {
      out.mods += 1;
      const row = modRow(path, onKnown);
      if (row) { out.modTokens += row.tokens ?? 0; out.modes.add(row.mode); out.rows.push(row); }
      else {
        out.exact = false;
        if (row === null) out.missing.push(path);
      }
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
export function costMark(entries, canvas, onKnown, space = DEFAULT_SPACE) {
  const c = cost(entries, canvas, onKnown, space);
  if (!c.pictures && !c.mods && !c.clips) return null;
  const total = c.picTokens + c.modTokens;
  const plus = c.clips ? "+" : "";
  return { text: `${c.exact ? "" : "≈"}${shortTokens(total)}${plus} tok`, saved: c.exact };
}

/** The mode menu's rows for one family, each naming what it would cost.
 *  `family` is a `modFamilies` entry, or absent for H3's. Only what is not
 *  saved for that family yet is offered: a picture carrying its rendition
 *  already is not encoded twice. */
export function modeRows(entries, onPick, onKnown, family = null) {
  const space = family?.space ?? DEFAULT_SPACE;
  const clipsTaken = family ? family.clips : true;
  const fresh = entries.filter((entry) => !modIn(entry, space));
  const stills = fresh.filter((entry) => entry.kind !== "video");
  const clips = fresh.length - stills.length;
  // A stack of one still is a compressed mod wearing the wrong kind; offered
  // only where there is something to stack. Clips only where the family
  // keeps them.
  const offered = MODES.filter((mode) =>
    (mode.key !== "stack" || (clipsTaken && (fresh.length > 1 || clips)))
    && (mode.key !== "clip" || (clipsTaken && clips)));
  return offered.map((mode) => {
    const tokens = mode.key === "stack"
      ? (stills.length + clips * STACK_CLIP_FRAMES) * STACK_FRAME_TOKENS
      : mode.key === "clip"
        ? clips * modTokens({ kind: "video" }, "full", onKnown, space)
        : stills.reduce((sum, entry) => sum + modTokens(entry, mode.key, onKnown, space), 0);
    const approx = mode.key !== "stack" || clips;
    const note = space === "flux2" && KLEIN_NOTES[mode.key] ? KLEIN_NOTES[mode.key] : mode.note;
    return {
      label: t("{mode} — {tokens} tokens", {
        mode: t(mode.label), tokens: (approx ? "≈" : "") + long(tokens) }),
      note: mode.key !== "stack" && mode.key !== "clip" && clips && clipsTaken
        ? `${t(note)} ${t("Stills only — a clip is kept on its own, or stacked.")}`
        : t(note),
      onPick: () => onPick(mode.key, family),
      key: mode.key,
    };
  });
}

/** One row for all of them, where more than one family could be encoded
 *  for right now: the same picture through each family's VAE, one job after
 *  the other, per-picture modes only — a stack and a clip are H3's shapes.
 *  `onPick(mode, families)`. Empty where fewer than two are ready. */
export function everyFamilyRows(entries, families, onPick, onKnown) {
  const ready = (families ?? []).filter((family) => family?.refmod && family.vae);
  if (ready.length < 2) return [];
  return ["compressed", "full"].map((key) => {
    const mode = MODES.find((m) => m.key === key);
    const perFamily = ready.map((family) => {
      const fresh = entries.filter((entry) => !modIn(entry, family.space) && entry.kind !== "video");
      return fresh.reduce((sum, entry) => sum + modTokens(entry, key, onKnown, family.space), 0);
    });
    if (!perFamily.some(Boolean)) return null;
    return {
      label: t("{mode} — {tokens} tokens", {
        mode: t(mode.label), tokens: `≈${perFamily.map(long).join(" + ")}` }),
      note: t("For every family this machine can encode for: {families}. One job per family, in that order.",
              { families: ready.map((family) => t(family.label)).join(", ") }),
      onPick: () => onPick(key, ready),
      key,
    };
  }).filter(Boolean);
}

/** The mode rows for one family, refused where that family has no VAE picked
 *  on this machine: drawn and disabled here rather than queued to be refused
 *  by the route. */
export function familyModeRows(entries, family, onPick, onKnown) {
  const rows = modeRows(entries, onPick, onKnown, family);
  if (family?.refmod && !family.vae && rows.length) {
    const why = t("Pick the {family} VAE in its weights control first.", { family: t(family.label) });
    for (const row of rows) { row.disabled = true; row.note = `${row.note} ${why}`; }
  }
  return rows;
}

/** A listing row's aspect, long over short, off its own grid — exact, where a
 *  picture's has to be measured. */
function rowAspect(row) {
  const [, h, w] = row.grid ?? [1, 1, 1];
  return Math.max(h, w) / Math.max(1, Math.min(h, w));
}

/**
 * The re-encode menu's rows: one per per-picture mode, each naming what their
 * mods would cost in it and where the picture to read comes from. A stack and
 * a clip have no rows — they were several files, or a run of frames, and
 * saving the member again is how one is remade.
 *
 * A mode the mods are in already is offered too, as an encode *again* from the
 * picture: the way to redo one that came out wrong, or that was made before
 * the picture was fixed (issue #121 — the menu used to offer only the mode a
 * mod was not in, so a bad one could never be redone).
 *
 * A mod whose picture has gone can still be *compressed*: the full file is the
 * encode, and the grid is pooled and refined against it. Nothing else can be
 * made of it. Those are left out of a row rather than sinking it, the row says
 * how many, and a row with nothing it can do is drawn disabled.
 */
export function remakeRows(rows, onPick) {
  const stills = rows.filter((row) => row && row.source !== "stack" && row.kind !== "video");
  if (!stills.length) return [];
  return MODES.filter((mode) => mode.key === "compressed" || mode.key === "full").map((mode) => {
    const current = mode.key === "compressed" ? "training" : "encode";
    // From the picture where it is there; from the file's own full encode
    // where only that is left and the mode asked for is compressed.
    const doable = (row) => row.source_present || (mode.key === "compressed" && row.mode === "encode");
    const targets = stills.filter(doable);
    const stuck = stills.length - targets.length;
    const again = targets.length > 0 && targets.every((row) => row.mode === current);
    const tokens = targets.reduce((sum, row) => sum + (mode.key === "compressed"
      ? Math.round(COMPRESSED_TOKENS / rowAspect(row))
      : Math.round(FULL_TOKENS * rowAspect(row))), 0);
    const from = !targets.length
      ? t("The picture it was made of is not in the input folder any more — attach it "
        + "again and save the member instead.")
      : targets.every((row) => row.source_present)
        ? t("From {file}", { file: targets.map((row) => row.source_file).join(", ") })
        : t("Pooled from the full encode already in the file — the picture it was "
          + "made of is not in the input folder any more.");
    const skipped = stuck && targets.length
      ? ` ${t(stuck === 1 ? "{count} is left as it is — its picture is not in the input folder any more."
                          : "{count} are left as they are — their pictures are not in the input folder any more.",
              { count: stuck })}`
      : "";
    return {
      label: t(again ? "{mode} again — {tokens} tokens" : "{mode} — {tokens} tokens",
               { mode: t(mode.label), tokens: `≈${long(tokens)}` }),
      note: `${t(mode.note)} ${from}${skipped}`,
      disabled: !targets.length,
      onPick: () => onPick(mode.key, targets.map((row) => row.path)),
    };
  });
}

/**
 * Write `mods` again as `mode`, in place. -> the listing rows of what was
 * written. Nothing to attach and nothing to move: the file keeps its name and
 * the member's looks keep pointing at it — the listing is what changed, and it
 * is fetched again so the ledger's next redraw says the new cost.
 */
export async function remakeMods(mods, mode, { vae = "", onProgress = null } = {}) {
  const answer = await remakeRefMod({ mods, mode, vae }, { onProgress });
  const rows = answer?.mods ?? [];
  if (!rows.length) throw new Error(t("the server wrote nothing"));
  await modRows();
  return rows;
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

/** What a member can be saved out of, per mode and family. Never a mod
 *  already, never a picture carrying its rendition for that family already,
 *  never a cut-out sheet — that is a layout the encoder builds at render
 *  time. The per-picture modes take stills alone; `clip` takes clips alone; a
 *  stack takes both, which is the point of it. */
export function keepable(subject, assets, mode = "compressed", space = DEFAULT_SPACE) {
  return looks(subject, assets).filter((a) => !modIn(a, space) && !S.isPlate(a)
                                             && (mode === "stack" || a.kind === (mode === "clip" ? "video" : "image")));
}

/**
 * Keep `subject`'s pictures as mods for one family, and hang each on its
 * picture — or, `stack`, rebuild their looks out of the one file.
 *
 * `host` is what the two shelf hosts know and the shelf does not:
 *   family      a `modFamilies` entry — `{id, label, space, vae}`; absent is
 *               H3's with `host.vae`, which is what every caller was before
 *               the spaces arrived
 *   vae         the H3 video VAE the piece is set to, by filename (see above)
 *   list()      the asset array a new reference lands in (a stack's)
 *   nextHandle(kind)  a fresh handle for that array
 *   texts()     every text a handle could be written into by hand
 *   cast()      the whole cast, to see who else claims a picture
 *   drop(handles)     take pictures nobody needs any more off the piece
 *   onProgress  the queue's progress, if the host shows one
 *
 * -> the picker rows of the mods written, in the order of the pictures.
 */
export async function keepAsMod(subject, assets, mode, host) {
  const family = host.family ?? { id: null, space: DEFAULT_SPACE, vae: host.vae ?? "" };
  const stack = mode === "stack";
  const sources = keepable(subject, assets, mode, family.space);
  if (!sources.length) {
    throw new Error(t(mode === "clip" ? "Nothing to save — hang a clip on them first."
                                      : "Nothing to save — hang a picture on them first."));
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
    // The framing on each chip, by position: a mod is the latent of what the
    // model would have read, and that is the window, not the file.
    crops: sources.map((a) => a.crop ?? null),
    mode: stack ? "stack" : mode === "clip" ? "clip" : mode === "full" ? "full" : "compressed",
    description: [subject.description ?? "", ...(stack ? noted : [])].filter(Boolean).join("; "),
    concept: CONCEPT[subject.takes ?? "person"] ?? "generic",
    vae: family.vae ?? "",
    ...(family.id ? { family: family.id } : {}),
  }, { onProgress: host.onProgress });
  const rows = answer?.mods ?? [];
  if (!rows.length) throw new Error(t("the server saved nothing"));

  if (!stack) {
    // One mod per file, hung on the file it was made of. Nothing moves: the
    // picture is still their looks, still cited by its handle, still what
    // every other family reads; the family this was made for reads the mod.
    rows.forEach((row, index) => {
      const source = sources[index];
      if (!source) return;
      source.mods = { ...(source.mods ?? {}), [row.space ?? family.space]: row.path };
    });
    return rows;
  }

  // A stack: one file in the place of all of them, wearing the first's
  // narrowing. The words are read before the looks move: `subjectNotes`
  // keeps only the notes on files the member still claims.
  const list = host.list();
  const swapped = new Map();
  rows.forEach((row) => {
    const source = sources[0];
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
    for (const a of sources) swapped.set(a.handle, entry.handle);
  });
  // A stack stands for several handles at once; the member's looks list it once.
  const from = (subject.from ?? []).map((handle) => swapped.get(handle) ?? handle);
  subject.from = from.filter((handle, index) => from.indexOf(handle) === index);
  // The per-file words went into the header above; the stack is one latent
  // and cannot carry a note, or wake, per picture — a stack of plates that
  // conflict is exactly what waking them one at a time replaces.
  const moved = { ...notes };
  for (const old of swapped.keys()) delete moved[old];
  if (Object.keys(moved).length) subject.notes = moved;
  else delete subject.notes;
  const woken = { ...S.subjectTriggers(subject) };
  for (const old of swapped.keys()) delete woken[old];
  if (Object.keys(woken).length) subject.triggers = woken;
  else delete subject.triggers;

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
