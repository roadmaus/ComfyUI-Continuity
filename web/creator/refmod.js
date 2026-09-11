// Keeping somebody as a saved reference.
//
// A RefMod is the DiT half of a reference already encoded — one H3 VAE latent
// in a safetensors file, the format `ComfyUI-MiniMaxH3Mod` reads and writes
// (`creator/refmod.py` says the rest). What it is *for* here is a cast member:
// their looks come from a few pictures, and each picture is a few hundred
// reference tokens riding through every sampling step. Kept as compressed mods
// they are sixty-four each, and a shot that could carry two of them can carry
// six. Kept as full mods they are the same encode cached on disk, shareable as
// one file per picture.
//
// So this is a press on the member's own card, beside the star: encode every
// picture they are built out of, attach the mods where the pictures were, and
// point their looks at the mods. The pictures leave the piece unless somebody
// else still needs them — another member, or a sentence that writes the handle
// by hand — which is the same bargain removing a member makes with their files.
//
// The host does the attaching, for the reason the shelf's `keep` and `library`
// are the host's: a shelf does not know whether a member's pictures live on a
// card's row or in the piece's pool, and there are two hosts.

import { isRefMod, makeRefMod } from "./api.js";
import { t } from "./i18n.js";
import * as S from "./state.js";

/** The two ways to keep a picture, in the words the menu uses. `compressed`
 *  leads because it is the one with a reason to exist: the token budget. */
export const MODES = [
  {
    key: "compressed", label: "Compressed",
    note: "Pooled to a 16-cell grid and refined against the full encode — 64 "
        + "tokens a picture, so more of them fit a shot. Keeps colour, build and "
        + "large structure; fine detail goes.",
  },
  {
    key: "full", label: "Full",
    note: "The encode as it is, at a 1024 short edge — the reference's whole "
        + "detail, cached on disk and kept as one file.",
  },
];

// A member's `takes` word, as the mod format's `concept_type`. Metadata for
// their loaders' filters; nothing here reads it back.
const CONCEPT = { person: "identity", object: "generic", scene: "background", style: "style" };

// Where kept members' mods are written, under models/refmods/.
export const SUBFOLDER = "cast";

/** The pictures a member can be kept out of: the stills their looks come from,
 *  attached here, and not already mods. A clip is not kept — a motion mod is a
 *  different thing and nothing here makes one yet. */
export function keepable(subject, assets) {
  return (subject.from ?? [])
    .map((handle) => (assets ?? []).find((a) => a.handle === handle))
    .filter((a) => a && a.kind === "image" && a.role === "reference"
                   && !isRefMod(a.filename) && !S.isPlate(a));
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
  const sources = keepable(subject, assets);
  if (!sources.length) {
    throw new Error(t("Nothing to keep — hang a picture on them first."));
  }
  const answer = await makeRefMod({
    name: subject.handle,
    subfolder: SUBFOLDER,
    sources: sources.map((a) => a.filename),
    mode: mode === "full" ? "full" : "compressed",
    description: subject.description ?? "",
    concept: CONCEPT[subject.takes ?? "person"] ?? "generic",
    vae: host.vae ?? "",
  }, { onProgress: host.onProgress });
  const rows = answer?.mods ?? [];
  if (!rows.length) throw new Error(t("the server kept nothing"));

  // One mod per picture, in the picture's place: same narrowing, same words.
  // The words are read before the looks move: `subjectNotes` keeps only the
  // notes on files the member still claims.
  const notes = S.subjectNotes(subject);
  const list = host.list();
  const swapped = new Map();
  rows.forEach((row, index) => {
    const source = sources[index];
    const entry = {
      handle: host.nextHandle("image"),
      kind: "image",
      role: "reference",
      filename: row.path,
      ...(source?.takes ? { takes: source.takes } : {}),
    };
    list.push(entry);
    if (source) swapped.set(source.handle, entry.handle);
  });
  subject.from = (subject.from ?? []).map((handle) => swapped.get(handle) ?? handle);
  const moved = { ...notes };
  for (const [old, fresh] of swapped) {
    if (!notes[old]) continue;
    moved[fresh] = notes[old];
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
