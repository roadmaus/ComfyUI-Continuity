// A preset is a setup you can put back: what was captured, where it is kept, and
// what happens when it is applied.
//
// **A preset is a blob and a row.** `steps`, `cfg`, `sampler_name`, `scheduler`,
// the two flow shifts and the accelerators were stock ComfyUI widgets when this
// was written, so a preset that stored only `creator_data` would have dropped
// the turbo schedule, the step count and the block cache — most of what anyone
// tunes. The row lives in the blob now (see `sampling.py`), which makes the pair
// redundant on paper and load-bearing in practice: presets already in the
// library were captured off widgets, so both halves are still read and applied.
//
// The seed is the one field still genuinely on a widget, and the one this never
// captures anyway — a preset is a setup, not a take.
//
// **Cut into sections, because "everything" is the right default and the wrong
// only option.** A preset that always replaces the whole node stops being used
// the moment you have a prompt worth keeping — you want *that look* on *this
// shot*. So a preset stores whatever was captured and applies per section, and
// the sections are not arbitrary: each is a set of fields the node already treats
// as one thing.
//
// **Nothing here is read at execute time.** `settings.py` opens by explaining
// when a server route is required — the save node reads settings while a queued
// prompt runs, and an execution has no request behind it and so no ComfyUI user.
// A preset's whole life is over before the queue button is pressed, so that
// condition does not hold and this goes through the userdata API, exactly as the
// picker's favorites do. There is no Python half of this feature.

import { api } from "../../../scripts/api.js";
import { t } from "./i18n.js";
import * as S from "./state.js";
import { NATIVE_SHORT_EDGE } from "./canvas.js";

// ---- storage ----------------------------------------------------------------
//
// Two levels, because a library has to draw before it has read everything. The
// index holds one row per preset — everything a card draws, a few hundred bytes
// — and the body holds the sections, fetched when a card is opened or applied.
//
// One file for both would mean rewriting a 24-shot timeline's worth of JSON every
// time somebody stars something, and re-downloading every preset in the library
// to draw one row of cards. The split is the picker's own lazy-grid reasoning at
// a smaller scale.
//
// Flat filenames rather than a `presets/` subfolder: the userdata API takes a
// path, but a flat prefix needs nothing from it that the picker's single file has
// not already proven works.

const INDEX_FILE = "minimax_creator.presets.json";
const BODY_FILE = (id) => `minimax_creator.preset.${id}.json`;
// The mirror, for a frontend whose userdata API is unavailable. Same deal the
// picker's prefs have: losing a write is recoverable in a way a blocked click is
// not.
const INDEX_KEY = "mmc-presets";
const BODY_KEY = (id) => `mmc-preset-${id}`;

export const PRESET_VERSION = 1;

let indexCache = null;

/** An id that cannot collide with a builtin's and does not need a counter kept
 *  anywhere. Time-ordered so a directory listing reads chronologically. */
function newId() {
  return `p${Date.now().toString(36)}${Math.floor(Math.random() * 0x10000).toString(16).padStart(4, "0")}`;
}

async function readUserData(file, key) {
  try {
    const response = await api.getUserData(file);
    if (response.status === 200) return await response.json();
    // 404 is a library nobody has written to yet, which is not an error.
    if (response.status === 404) return null;
  } catch {
    // No userdata API on this frontend, or it is offline.
  }
  try { return JSON.parse(localStorage.getItem(key) ?? "null"); } catch { return null; }
}

async function writeUserData(file, key, value) {
  const body = JSON.stringify(value);
  try { localStorage.setItem(key, body); } catch { /* quota; userdata still tries */ }
  try {
    const response = await api.storeUserData(file, value, { stringify: true });
    if (response && response.status >= 400) {
      throw new Error(t("the server refused it ({status})", { status: response.status }));
    }
  } catch (error) {
    // Reported rather than swallowed: a preset that looked saved and was not is
    // work the user believes they still have. The localStorage copy above is why
    // this is a warning and not a loss.
    throw new Error(t("Could not store the preset — {error}", { error: error.message ?? error }));
  }
}

async function deleteUserData(file, key) {
  try { localStorage.removeItem(key); } catch { /* nothing to remove */ }
  try { await api.deleteUserData?.(file); } catch { /* already gone, or no API */ }
}

/** Every stored row, newest first. Cached — the library re-reads on open through
 *  `listPresets({force: true})`, and everything that writes updates the cache. */
export async function listPresets({ force = false } = {}) {
  if (indexCache && !force) return indexCache;
  const raw = await readUserData(INDEX_FILE, INDEX_KEY);
  const rows = Array.isArray(raw?.presets) ? raw.presets : [];
  indexCache = rows.filter((row) => row && typeof row.id === "string")
    .sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0));
  return indexCache;
}

async function writeIndex(rows) {
  indexCache = rows.sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0));
  await writeUserData(INDEX_FILE, INDEX_KEY, { version: PRESET_VERSION, presets: indexCache });
}

/** The sections of one preset. Builtins carry theirs inline and never hit
 *  storage. Returns null when the body is gone — a row whose body cannot be read
 *  can still be renamed and deleted, which is the only useful thing left to do
 *  with it. */
export async function loadBody(row) {
  if (row.builtin) return row.data ?? null;
  const stored = await readUserData(BODY_FILE(row.id), BODY_KEY(row.id));
  return stored?.data ?? null;
}

/** Store a captured preset and hand back its index row.
 *
 *  The card fields are derived here rather than passed in, so every call site
 *  files the same row and there is one description of what a card needs. */
export async function savePreset({ name, scope, note = "", folder = "", data, cover = null }) {
  const now = Date.now();
  const row = {
    id: newId(),
    name: name.trim() || t("Untitled preset"),
    scope,
    note,
    folder,
    starred: false,
    created: now,
    updated: now,
    version: PRESET_VERSION,
    sections: Object.keys(data),
    cover,
    ...describe(data, scope, { cover }),
  };
  await writeUserData(BODY_FILE(row.id), BODY_KEY(row.id), { version: PRESET_VERSION, id: row.id, data });
  await writeIndex([row, ...(await listPresets())]);
  return row;
}

/** Rename, star, re-shelve, re-cover. Index-only — none of it touches a body. */
export async function updatePreset(id, patch) {
  const rows = await listPresets();
  const next = rows.map((row) => (row.id === id
    ? { ...row, ...patch, updated: patch.updated ?? Date.now() }
    : row));
  await writeIndex(next);
  return next.find((row) => row.id === id);
}

export async function deletePreset(id) {
  const rows = await listPresets();
  await writeIndex(rows.filter((row) => row.id !== id));
  await deleteUserData(BODY_FILE(id), BODY_KEY(id));
}

/** Re-store a body under an existing row — "Save over this preset". */
export async function replaceBody(id, { data, scope, cover }) {
  await writeUserData(BODY_FILE(id), BODY_KEY(id), { version: PRESET_VERSION, id, data });
  return updatePreset(id, {
    sections: Object.keys(data),
    ...(cover !== undefined ? { cover } : {}),
    ...describe(data, scope, { cover }),
  });
}

// ---- the sections -----------------------------------------------------------
//
// Each key is a set of fields that always move together and that the node
// already treats as one thing. `hue` indexes the reference-identity colours in
// styles/base.js — the eye is already trained on them in the prompt box, so a
// chip row becomes scannable for nothing.

export const SECTIONS = [
  {
    key: "look", label: "Look", hue: 0,
    hint: "Aspect, short edge, and the two-pass refine.",
  },
  {
    key: "weights", label: "Weights", hue: 4,
    hint: "Which files load, at what precision, routed to which checkpoint.",
  },
  {
    key: "speed", label: "Speed", hue: 5,
    hint: "The turbo switch and the whole sampler row.",
  },
  {
    key: "prompt", label: "Prompt", hue: 2,
    hint: "The text, the soundscape and the score.",
  },
  {
    key: "loras", label: "LoRAs", hue: 3,
    hint: "The LoRA stack, at its strengths.",
  },
  {
    key: "refs", label: "References", hue: 6,
    hint: "The attached media, by filename.",
  },
  {
    key: "strip", label: "Strip", hue: 1,
    hint: "Every card, its seams, and how they are generated.",
  },
  {
    key: "shot", label: "Timing & seam", hue: 1,
    hint: "How long this card runs, and what happens in front of it.",
  },
  // Somebody, rather than a setting. The one section whose files are named
  // rather than handled: a cast member is kept so they can walk into a piece they
  // were never attached to, and a handle means nothing over there. See
  // `captureSubject`.
  {
    key: "cast", label: "Cast", hue: 6,
    hint: "One cast member, their references, and what they take from them.",
  },
  // The one section no capture produces. A style comes from the shipped atlas
  // rather than off a node, and it is the only section that *edits* the field it
  // lands on instead of replacing it — see `leadWithStyle`. Hue 7 is the one
  // reference-identity colour the other seven sections left free.
  {
    key: "style", label: "Style", hue: 7,
    hint: "Goes in front of the prompt; a style already there is swapped out.",
  },
];

export const SECTION = Object.fromEntries(SECTIONS.map((s) => [s.key, s]));

/** Which sections a scope can hold at all. A shot has no canvas and no weights —
 *  the piece owns both — and only a piece has a strip. */
export const SCOPE_SECTIONS = {
  piece: ["look", "weights", "speed", "prompt", "loras", "refs", "strip", "style", "cast"],
  shot: ["prompt", "refs", "loras", "shot", "speed", "style"],
  prestage: ["look", "weights", "speed", "prompt", "loras", "refs", "style"],
  // A style is a source and never a target: you apply one to a node, and there
  // is no node a style could be captured off. It is the one scope whose tab is a
  // catalogue rather than a shelf of your own work.
  style: ["style"],
  // A cast member is a source and a target both — kept from a node's own shelf,
  // applied to any piece. What they cannot be is a *setup*: their tab holds one
  // person per row rather than one node per row, which is why they are a scope of
  // their own and not an eighth section of a piece.
  cast: ["cast"],
};

export const SCOPES = ["piece", "shot", "prestage", "cast", "style"];
export const SCOPE_LABEL = { piece: "Piece", shot: "Shot", prestage: "Pre-stage",
                             cast: "Cast", style: "Style" };

/**
 * Whether one section of a preset can land on a target of another scope, and why
 * not when it cannot.
 *
 * A section that cannot cross is shown and disabled with the reason on it, never
 * hidden: "this pre-stage runs Krea 2, and these are H3 checkpoints" is
 * information, where a missing row is a bug the user reports.
 */
export function crossable(key, from, to, { arch = null, targetArch = null } = {}) {
  if (!SCOPE_SECTIONS[to]?.includes(key)) {
    if (key === "strip") return { ok: false, why: "Only a piece has a strip." };
    if (key === "shot") return { ok: false, why: "Only a card has a duration and a seam." };
    if (key === "cast") {
      return { ok: false, why: to === "shot"
        ? "A cast belongs to the piece, not to one shot — apply them from the piece's own Presets."
        : "Only a piece has a cast." };
    }
    if (key === "look" && to === "shot") return { ok: false, why: "The piece owns the canvas, not the shot." };
    if (key === "weights" && to === "shot") return { ok: false, why: "The piece owns the weights, not the shot." };
    return { ok: false, why: "Not something this node holds." };
  }
  if (from === to) return { ok: true };
  // The one genuinely awkward crossing. The two node families name different
  // files: a piece loads FL2VA/Ref2VA/CLIP/two VAEs, a pre-stage loads Krea 2 or
  // Ideogram 4 — except on its H3 branch, whose `request` *is* a creator request
  // and whose models block is the same block under the same keys.
  if (key === "weights") {
    const stillBranch = (from === "prestage" ? arch : targetArch) === S.PRESTAGE_STILL_ARCH;
    if (!stillBranch) {
      return { ok: false, why: "These are different model families — only a pre-stage on the H3 branch loads the same files a piece does." };
    }
  }
  return { ok: true };
}

// ---- capture ----------------------------------------------------------------
//
// Always off the *serialized* blob rather than off the live state object. The
// serializers are what decide the canonical shape — which fields are omitted for
// being at their default, which are rounded, which are dropped as meaningless —
// and a capture that read the state directly would be a second opinion about all
// of it.

/** The sampler widgets a preset carries, by node family. The seed is not one of
 *  them and never will be: it is the one number that has to be different next
 *  time, and `control_after_generate` exists to make sure of it — a preset that
 *  restored one would turn "run it again" into "run the same frame again". */
export const SPEED_WIDGETS = ["steps", "cfg", "sampler_name", "scheduler",
                              "shift_video", "shift_audio",
                              "block_cache", "spectrum", "spectrum_blend", "sage"];

/** What a pre-stage's row actually has. Its node declares five widgets; the
 *  shifts and the accelerators belong to the video sampler alone. */
export const PRESTAGE_SPEED_WIDGETS = ["steps", "cfg", "sampler_name", "scheduler"];

function readRow(io, names) {
  const row = {};
  for (const name of names) {
    const value = io.value(name, undefined);
    if (value !== undefined && value !== null) row[name] = value;
  }
  return row;
}

const pick = (source, keys) => Object.fromEntries(
  keys.filter((key) => source[key] !== undefined).map((key) => [key, source[key]]));

/**
 * A piece — a Creator or a Timeline — as a preset body.
 *
 * `io` is the `widgetIO` pair the body already hands the sampler row, so the row
 * is read through exactly the accessor everything else writes it through.
 */
export function capturePiece(timeline, io) {
  const blob = JSON.parse(S.serializeTimeline(timeline));
  return {
    look: pick(blob, ["aspect", "short_edge", "upscale", "sample_edge", "refine_denoise",
                      "face"]),
    weights: blob.models ?? {},
    speed: { turbo: blob.turbo ?? null, row: readRow(io, SPEED_WIDGETS) },
    prompt: pick(blob, ["prompt", "soundscape", "music", "refined"]),
    loras: blob.loras ?? [],
    refs: blob.assets ?? [],
    strip: {
      render: blob.render,
      audio_tail_s: blob.audio_tail_s,
      segments: blob.segments ?? [],
    },
  };
}

/**
 * One card of a strip as a preset body.
 *
 * Through the timeline's own serializer and then indexed, rather than through a
 * serializer of its own: a segment's canonical shape is whatever
 * `serializeTimeline` writes for it, seam flags and all, and there is no second
 * implementation of that to get wrong.
 */
export function captureShot(timeline, index, io) {
  const blob = JSON.parse(S.serializeTimeline(timeline));
  const segment = blob.segments?.[index] ?? {};
  return {
    prompt: pick(segment, ["prompt", "soundscape", "music", "refined"]),
    refs: segment.assets ?? [],
    loras: segment.loras ?? [],
    shot: pick(segment, ["duration_s", "checkpoint", "continue", "continue_audio",
                         "continue_from", "feather", "merge", "kind", "filename",
                         "sound", "width", "height", "trim"]),
    speed: { row: readRow(io, SPEED_WIDGETS) },
  };
}

/**
 * A PreStage node as a preset body. `arch` and `quality` ride with the weights
 * because they are what chooses the model, which is what that section is.
 *
 * The H3 branch keeps its files somewhere else, and missing that is a silent way
 * to lose them: `serializePreStage` fills the top-level `models` block for the
 * two *image* architectures only (`PRESTAGE_IMAGE_ARCHES`), while the H3 branch's
 * checkpoints live in `minimax.request.models` — because that request *is* an
 * ordinary creator request. So the still's block is carried alongside its frame
 * settings, and `crossable`'s promise that an H3 pre-stage "loads the same files
 * a piece does" is one this can actually keep.
 */
export function capturePreStage(state, io) {
  const blob = JSON.parse(S.serializePreStage(state));
  return {
    look: pick(blob, ["aspect", "short_edge"]),
    weights: {
      arch: blob.arch,
      quality: blob.quality,
      models: blob.models ?? {},
      ...(blob[S.PRESTAGE_STILL_ARCH] ? {
        [S.PRESTAGE_STILL_ARCH]: {
          ...pick(blob[S.PRESTAGE_STILL_ARCH], ["frames", "latent_index"]),
          models: blob[S.PRESTAGE_STILL_ARCH].request?.models ?? {},
        },
      } : {}),
    },
    speed: { turbo: blob.turbo ?? null, row: readRow(io, PRESTAGE_SPEED_WIDGETS) },
    prompt: pick(blob, ["prompt"]),
    loras: blob.loras ?? [],
    refs: {
      ...(blob.init ? { init: blob.init } : {}),
      refs: blob.refs ?? [],
    },
  };
}

// ---- capture one cast member ------------------------------------------------
//
// The other kind of thing worth keeping. Everything above this line is a *node*
// set up a certain way; a cast member is a person, and the reason to keep them is
// that they have to be the same person in a piece you have not written yet.
//
// **Their files are named, not handled.** Everywhere else in this pack a subject
// cites `@img-2`, and that handle is a fact about one node's attachment list —
// carried into another piece it points at nothing, or worse, at somebody else's
// picture. So what is stored is the filename, and applying them is what attaches
// the file and hands out the handle. That is the whole difference between this
// section and `refs`, and it is why they are a scope of their own.
//
// The slot rides with each file because it is the half a filename cannot say: the
// same clip is their movement on one card and the place they take on the next.

/** The four slots a file can sit in behind a subject, in citation order.
 *  Mirrors `ROLES` in `cast.js` and `subjects.Subject`. */
export const SUBJECT_SLOTS = ["from", "motion", "voice", "replaces"];

/** What of an asset row travels with a cast member. The handle is deliberately
 *  not in it — see above — and neither is `role`, which is `reference` for
 *  everything a subject can be built out of. */
function storedFile(asset, slot) {
  return {
    slot,
    filename: asset.filename,
    kind: asset.kind ?? "image",
    ...(asset.track ? { track: asset.track } : {}),
    ...(asset.ref_size ? { ref_size: asset.ref_size } : {}),
    ...(asset.trim ? { trim: asset.trim } : {}),
  };
}

/**
 * One subject as a preset body, against the files they are built out of *here*.
 *
 * A handle they claim that is not attached any more is dropped rather than
 * carried: the library is where they are correct by definition, and a member who
 * arrived with a reference to a file nobody has is a card that cannot queue on
 * every machine they land on.
 */
export function captureSubject(subject, assets) {
  const byHandle = new Map((assets ?? []).map((asset) => [asset.handle, asset]));
  const files = [];
  for (const handle of subject.from ?? []) {
    const asset = byHandle.get(handle);
    if (asset?.filename) files.push(storedFile(asset, "from"));
  }
  for (const slot of ["motion", "voice"]) {
    const asset = byHandle.get(subject[slot]);
    if (asset?.filename) files.push(storedFile(asset, slot));
  }
  // Several, where somebody stands in for the same person in more than one clip.
  for (const handle of S.replacesOf(subject)) {
    const asset = byHandle.get(handle);
    if (asset?.filename) files.push(storedFile(asset, "replaces"));
  }
  return {
    data: {
      cast: {
        handle: subject.handle || "subject",
        takes: subject.takes ?? "person",
        ...(subject.description ? { description: subject.description } : {}),
        // What they are, feature by feature. Kept with them, because a member
        // who comes back out of the library without the features that made them
        // that person comes back as a name and a photograph.
        ...(S.subjectFeatures(subject).length
          ? { features: S.subjectFeatures(subject) } : {}),
        ...(subject.replaces_what ? { replaces_what: subject.replaces_what } : {}),
        ...(subject.relationship ? { relationship: subject.relationship } : {}),
        files,
      },
    },
    cover: null,
    defaultName: subject.handle || "",
  };
}

/**
 * What a kept member is made of, in one line: what they are, then what is behind
 * them. Off the index row's `facts`, so it costs nothing to draw.
 *
 * Here rather than in the library because two surfaces read it — the roster card
 * and the `@` menu's own row, which offers them mid-sentence — and a second
 * implementation of "person · 2 pictures · voice" would drift from this one.
 */
export function castFactsLine(facts = {}) {
  const pictures = facts.pictures ?? 0;
  const clips = facts.clips ?? 0;
  const features = facts.features ?? 0;
  const nothing = !pictures && !clips && !facts.motion && !facts.voice && !facts.replaces;
  return [
    t(facts.takes ?? "person"),
    pictures
      ? t(pictures === 1 ? "{count} picture" : "{count} pictures", { count: pictures })
      : null,
    clips ? t(clips === 1 ? "{count} clip" : "{count} clips", { count: clips }) : null,
    facts.motion ? t("moves") : null,
    facts.voice ? t("voice") : null,
    facts.replaces ? t("their place") : null,
    // How much of them is written down, feature by feature. Worth a card's
    // width: a member with six features is somebody who will come back the same
    // person, and one with none is a name over a photograph.
    features
      ? t(features === 1 ? "{count} feature" : "{count} features", { count: features })
      : null,
    nothing && !features && facts.described ? t("described") : null,
  ].filter(Boolean).join(" · ");
}

/**
 * Keep one subject in the roster, as they stand on this node.
 *
 * Kept *over* a member of the same name rather than beside them. The star on their
 * card is pressed twice for one reason — they have changed since the last time,
 * another picture, a voice — and a library that answered that with a second
 * @anna would make the roster useless at exactly the point it started being
 * used. A name is who somebody is here; there is one of them.
 */
export async function keepSubject(subject, assets) {
  const captured = captureSubject(subject, assets);
  const name = captured.defaultName || t("Untitled preset");
  const standing = (await listPresets()).find(
    (row) => row.scope === "cast" && !row.builtin && row.name === name);
  if (standing) return replaceBody(standing.id, { data: captured.data, scope: "cast" });
  return savePreset({ name, scope: "cast", data: captured.data });
}

// ---- capture from a render --------------------------------------------------
//
// The other way a preset is made: not off a node that is set up, but off a file
// that came out well. Both save nodes embed the workflow that produced the
// render — the MP4 in its container tags, the PNG in its text chunks — for the
// reason core's savers do, and that embedded workflow already holds the whole of
// what a preset is. Nothing had to be stored for this; it was in the files all
// along, and the only thing missing was a reader.
//
// **Off the `prompt` tag, never the `workflow` tag.** Both are there. The
// workflow is the canvas graph, whose `widgets_values` is a positional array —
// and this pack has already changed the length of that row once, when the two
// flow shifts were added. A render made before that has nine entries where the
// current node declares eleven, so reading it positionally silently assigns
// `steps` to `shift_video` and everything after it. The `prompt` tag is the API
// form: `{"2": {"class_type": …, "inputs": {"steps": 20, "cfg": 1.0, …}}}`, keyed
// by name, which is the same thing `widgetIO` is keyed by. It also survives a
// render queued over the API, where the workflow tag is a one-node stub.

/** The node ids a render can have come from, and what each calls its blob. */
export const RENDER_SOURCES = {
  "MiniMaxH3Creator": { scope: "piece", input: "creator_data" },
  "MiniMaxH3Timeline": { scope: "piece", input: "timeline_data" },
  "MiniMaxH3PreStage": { scope: "prestage", input: "prestage_data" },
};

/** A read-only `widgetIO` over an API prompt's `inputs`. A wired input arrives
 *  as a `[nodeId, slot]` pair rather than a value, and is no more a sampler
 *  setting than an empty socket is. */
function promptIO(inputs, sampling) {
  return {
    value: (name, fallback) => {
      // The blob first, exactly as `sampling.resolve` reads it on the other
      // side. The widgets are still in `inputs` and still carry *a* value — the
      // node declares them and always will — but on any render made since the
      // row moved they carry whatever was on the node before it moved, which is
      // not what sampled. Reading them first would take a preset off a render
      // and quietly capture somebody else's step count.
      const stored = sampling?.[name];
      if (stored !== undefined && stored !== null) return stored;
      const value = inputs?.[name];
      return value === undefined || Array.isArray(value) ? fallback : value;
    },
    set: () => { /* a file is not a node; nothing here is applied back */ },
  };
}

/**
 * Every node in an embedded prompt that a preset could be taken from, in node-id
 * order, each as `{id, scope, blob, inputs}`.
 */
export function renderSources(prompt) {
  const entries = Object.entries(prompt ?? {});
  const found = [];
  for (const [id, node] of entries) {
    // `hasOwn` and not a bare lookup: a class_type of "constructor" is a string
    // like any other and would otherwise find something on Object's prototype.
    const type = node?.class_type;
    if (typeof type !== "string" || !Object.hasOwn(RENDER_SOURCES, type)) continue;
    const source = RENDER_SOURCES[type];
    const blob = node?.inputs?.[source.input];
    if (typeof blob !== "string") continue;
    found.push({ id, scope: source.scope, blob, inputs: node.inputs });
  }
  return found.sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0));
}

/**
 * One render, as a preset ready to be saved: `{scope, data, cover, defaultName}`
 * in the shape `savePreset` takes and a `presetTarget`'s `capture()` returns, so
 * the two ways of making a preset end in exactly the same call.
 *
 * `asset` is the picker's own row for the file — `{path, kind, mtime, name}` —
 * which is already the shape a cover is stored in. The cover comes free and it
 * comes right: the render this was taken from *is* the picture of what this
 * setup produces, which is the one thing a cover is for.
 *
 * **Which node, when a workflow holds several.** The render's kind decides
 * first, and it decides most of it: an MP4 came from a piece and a PNG from a
 * pre-stage, so a graph pairing a PreStage with a Creator — the ordinary way
 * these two nodes are used — is never ambiguous at all. Two Creators in one
 * graph is, and there the lowest node id wins and the caller is told, because
 * the tags carry nothing that says which of them wrote this file. Guessing
 * quietly would be the worse half of that.
 */
export function captureFromRender(meta, asset) {
  const sources = renderSources(meta?.prompt);
  if (!sources.length) {
    throw new Error(meta?.prompt || meta?.workflow
      ? t("That render was not made by these nodes.")
      : t("That render carries no workflow — it was saved with metadata disabled, or written by something else."));
  }
  const wanted = asset?.kind === "image" ? "prestage" : "piece";
  const matching = sources.filter((source) => source.scope === wanted);
  if (!matching.length) {
    throw new Error(t("That render's workflow holds no node that could have made a {kind}.",
                      { kind: t(asset?.kind === "image" ? "image" : "video") }));
  }
  const source = matching[0];

  let data;
  if (source.scope === "prestage") {
    const state = S.parsePreStage(source.blob);
    data = capturePreStage(state, promptIO(source.inputs, state.sampling));
  } else {
    // Through the same normalise-then-serialise path a live node's capture goes
    // through, rather than treating the stored blob as already canonical: the
    // file may have been written by an older build, and `parseTimeline` ->
    // `syncTimeline` is what decides what this one means by it.
    const timeline = S.parseTimeline(source.blob);
    S.syncTimeline(timeline);
    data = capturePiece(timeline, promptIO(source.inputs, timeline.sampling));
  }

  const stem = String(asset?.name ?? asset?.path ?? "").split("/").pop()
    .replace(/\.[^.]+$/, "").replace(/_+$/, "");
  return {
    scope: source.scope,
    data,
    cover: asset?.path ? { path: asset.path, kind: asset.kind, mtime: asset.mtime } : null,
    defaultName: stem || t("Untitled preset"),
    // What the caller warns about. Not an error: the preset it made is a real
    // preset off a real node, it may simply be off the other one.
    ambiguous: matching.length > 1 ? matching.length : 0,
    node: source.id,
  };
}

// ---- what the card draws ----------------------------------------------------

/** The picture behind one block of the lane, first hit wins:
 *  a clip's own still, then the card's start frame, then its end frame, then the
 *  first reference image it cites — and nothing, which is the ordinary text-only
 *  shot and draws flat. */
function blockPicture(segment, pool) {
  if (segment.kind === "clip") {
    return segment.filename ? { path: segment.filename, kind: "video" } : null;
  }
  const own = segment.assets ?? [];
  const frame = own.find((a) => a.role === "first_frame")
             ?? own.find((a) => a.role === "last_frame");
  if (frame?.filename) return { path: frame.filename, kind: frame.kind };
  const reference = own.find((a) => a.role === "reference" && a.kind === "image");
  if (reference?.filename) return { path: reference.filename, kind: "image" };
  // The piece's pool, but only the handles this card's text actually cites — a
  // pool asset rides into exactly the segments that name it, and a card that
  // never mentions one is not a card that shows it.
  const text = `${segment.prompt ?? ""} ${segment.refined?.body ?? ""}`;
  const cited = (pool ?? []).find((a) => a.kind === "image" && a.handle
                                      && text.includes(`@${a.handle}`));
  return cited?.filename ? { path: cited.filename, kind: "image" } : null;
}

/** At most this many blocks get a picture. Past it they are too narrow to read
 *  and it is thirty requests to say so. */
export const MAX_FRAMES = 6;

/** The lane, as the card draws it: one entry per pass, each holding its blocks at
 *  their real relative durations, plus the pictures for the first few. */
export function laneOf(body, scope) {
  if (scope !== "piece") return null;
  const segments = body.strip?.segments ?? [];
  if (!segments.length) return null;
  const pool = body.refs ?? [];
  const runs = [];
  segments.forEach((segment, index) => {
    const seconds = segment.kind === "clip"
      ? Math.max(0.1, Number(segment.duration_s) || 0.1)
      : Math.max(0.1, Number(segment.duration_s) || S.DEFAULT_DURATION_S);
    const block = { at: index, seconds, clip: segment.kind === "clip" };
    // A card merged into the one before it shares its generation, so it shares
    // its casing — the same reading `compile.timeline_runs` gives the strip.
    if (index && segment.merge === true && runs.length) runs[runs.length - 1].blocks.push(block);
    else runs.push({ blocks: [block] });
  });
  const frames = [];
  segments.forEach((segment, index) => {
    if (frames.length >= MAX_FRAMES) return;
    const picture = blockPicture(segment, pool);
    if (picture) frames.push({ at: index, ...picture });
  });
  return { runs, frames };
}

/** A pre-stage has no strip, so its card draws the canvas at its true aspect —
 *  filled with the init if there is one, else its first reference. */
export function canvasOf(body) {
  const refs = body.refs ?? {};
  const filename = refs.init?.filename
    ?? (refs.refs ?? []).find((ref) => ref.filename)?.filename;
  return {
    aspect: body.look?.aspect ?? "16:9",
    picture: filename ? { path: filename, kind: "image" } : null,
  };
}

/** The facts line, which is instrument reading rather than prose — the library
 *  sets it in a monospace face for exactly that reason. */
export function factsOf(body, scope) {
  if (scope === "cast") {
    const member = body.cast ?? {};
    const files = member.files ?? [];
    const built = files.filter((file) => file.slot === "from");
    return {
      takes: member.takes ?? "person",
      // Counted apart, because they read apart. A clip standing in the `from`
      // slot lends its frames the way a still does, but calling it a picture put
      // "2 pictures" under a card whose second file was an mp4 — and the card's
      // own face, which only ever draws an image, then had one to draw for one
      // of those two and not the other.
      pictures: built.filter((file) => (file.kind ?? "image") === "image").length,
      clips: built.filter((file) => (file.kind ?? "image") !== "image").length,
      motion: files.some((file) => file.slot === "motion"),
      voice: files.some((file) => file.slot === "voice"),
      replaces: files.some((file) => file.slot === "replaces"),
      described: Boolean(String(member.description ?? "").trim()),
      features: S.subjectFeatures(member).length,
    };
  }
  if (scope === "style") {
    const style = body.style ?? {};
    return { category: style.category ?? "", clips: (style.clips ?? []).length };
  }
  if (scope === "prestage") {
    const arch = body.weights?.arch ?? S.PRESTAGE_ARCHES[0];
    return {
      arch,
      aspect: body.look?.aspect ?? "16:9",
      quality: body.weights?.quality ?? null,
    };
  }
  if (scope === "shot") {
    const shot = body.shot ?? {};
    return {
      seconds: Number(shot.duration_s) || S.DEFAULT_DURATION_S,
      clip: shot.kind === "clip",
      feather: shot.feather ?? null,
      checkpoint: shot.checkpoint ?? "auto",
    };
  }
  const segments = body.strip?.segments ?? [];
  const seconds = segments.reduce((total, segment) =>
    total + (Number(segment.duration_s) || S.DEFAULT_DURATION_S), 0);
  const passes = segments.reduce((count, segment, index) =>
    count + (index && segment.merge === true ? 0 : 1), 0);
  return {
    shots: segments.length,
    passes,
    seconds,
    aspect: body.look?.aspect ?? "16:9",
    short_edge: body.look?.short_edge ?? NATIVE_SHORT_EDGE,
    route: body.weights?.route ?? "auto",
  };
}

/**
 * Everything the card draws, off the body — the index row's whole picture half.
 *
 * Derived at save time and stored, because the grid draws from the index alone:
 * a library of a hundred presets must not fetch a hundred bodies to paint one
 * screen of cards.
 *
 * `frames` is skipped entirely when there is a cover. The hero is the cover then,
 * and the lane is redrawn as a thin ruler across its foot — a ruler draws no
 * pictures, so collecting them would be six requests nothing reads.
 */
export function describe(data, scope, { cover = null } = {}) {
  const facts = factsOf(data, scope);
  // A style's pictures are files this pack ships, not renders on this machine,
  // so they are plain URLs rather than the `{path, kind}` rows `stillUrl`
  // resolves through a route. `stylelib.js` puts them on the row itself.
  // Their face is one of their own pictures, addressed as an input file — there is
  // no render behind a cast member and no output folder to look in. Where they are
  // words alone there is nothing to show, and the card draws their glyph instead.
  if (scope === "cast") {
    const still = (data.cast?.files ?? []).find(
      (file) => file.slot === "from" && (file.kind ?? "image") === "image");
    // Their own prose, on the index so the card can set it without fetching a
    // body. Capped rather than clamped in CSS alone: the index is read whole on
    // every library open, and a member described in nine hundred words would be
    // nine hundred words in every one of them.
    const words = String(data.cast?.description ?? "").trim().replace(/\s+/g, " ");
    return {
      facts,
      portrait: still?.filename ?? null,
      ...(words ? { blurb: words.slice(0, 160) } : {}),
      frames: [],
    };
  }
  if (scope === "style") return { facts, frames: [] };
  if (scope === "prestage") return { facts, canvas: canvasOf(data), frames: [] };
  if (scope === "shot") {
    const shot = data.shot ?? {};
    const picture = cover ? null : blockPicture({ ...shot, assets: data.refs ?? [] }, []);
    return { facts, frames: picture ? [{ at: 0, ...picture }] : [] };
  }
  const lane = laneOf(data, scope);
  return {
    facts,
    lane: lane ? { runs: lane.runs } : null,
    frames: cover ? [] : (lane?.frames ?? []),
  };
}

/**
 * A finished render, as a cover.
 *
 * Takes the whole of `stage.result` rather than its `saved` half, because the
 * kind is the half that is not in there: `saved` is the `{filename, subfolder,
 * type}` shape the gallery listing produces, and whether the render was a clip or
 * a still is `isImage`, which `stage.js` derives from *which* output key came
 * back — `mmc_video` or `mmc_image`.
 *
 * Stored as `{path, kind, mtime}`: an asset row exactly as the listing route
 * produces one, so `api.stillUrl` shows it with no adapter and no second opinion
 * about which route serves what. Everything in this pack that points at a media
 * file keeps it in that shape, and a cover is not special.
 */
export function coverFromResult(result) {
  const saved = result?.saved;
  if (!saved?.filename) return null;
  const relative = saved.subfolder ? `${saved.subfolder}/${saved.filename}` : saved.filename;
  return {
    path: `${relative} [output]`,
    kind: result.isImage ? "image" : "video",
    mtime: Math.floor(Date.now() / 1000),
  };
}

// ---- the style clause -------------------------------------------------------
//
// A style is the one section that *edits* the field it lands on instead of
// replacing it. Every other section owns its fields outright — applying `look`
// puts a whole canvas back — but a style is a clause at the front of a sentence
// somebody wrote, and a style that wiped the prompt would be a style used once.
//
// So applying one **swaps the lead**: the descriptor goes in front, and where the
// prompt already opens with a descriptor from the atlas, that one comes out. Try
// six looks on the same shot and you get six prompts, not six stacked paragraphs.
//
// Knowing which openings are swappable means knowing the atlas, and the atlas is
// a sixth of a megabyte the library imports only when its tab is opened. So the
// vocabulary is *registered* here rather than imported: `stylelib.js` calls this
// as it loads, and loading it is the only way a style can reach an apply at all.

let VOCABULARY = [];

/** Teach the swap which openings belong to a style rather than to a sentence.
 *  Longest first, so "Claymation with visible fingerprint texture" is matched
 *  ahead of the bare "Claymation" that is also in the atlas. */
export function setStyleVocabulary(phrases) {
  VOCABULARY = [...new Set(phrases ?? [])]
    .map((phrase) => String(phrase).trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((phrase) => phrase.toLowerCase());
}

/** How much of `text` is a descriptor from the atlas — 0 for none. The match has
 *  to land on a clause boundary, or the bare "Claymation" would also match
 *  "Claymationist puppets" and eat a word that was never a style. */
function leadLength(text) {
  const lower = text.toLowerCase();
  for (const phrase of VOCABULARY) {
    if (!lower.startsWith(phrase)) continue;
    const after = text[phrase.length];
    if (after === undefined || /[\s,.;:—-]/.test(after)) return phrase.length;
  }
  return 0;
}

// The openings it is safe to lower-case once they are mid-sentence behind a
// descriptor: a closed list of articles and prepositions. Lower-casing whatever
// the prompt happens to start with would turn "Marcus waits at the gate" into
// "marcus waits at the gate", and mangling somebody's character is worse than a
// capital letter after a comma.
const SAFE_LEAD = /^(A|An|The|In|Inside|On|At|Across|Under|Over|Through|Along|Beside|Behind|Beneath|Outside|From|Two|Three|Four|Five|Six)\b/;

/**
 * `text`, opening with `phrase`.
 *
 * The descriptor leads and the prompt follows it after a comma, which is the
 * shape H3's own captions have — the atlas *is* the opening clause of one, and
 * the scene is what came after it.
 */
export function leadWithStyle(text, phrase) {
  const descriptor = String(phrase ?? "").trim().replace(/[,.;:\s]+$/, "");
  const body = String(text ?? "").trim();
  const rest = body.slice(leadLength(body)).replace(/^[\s,.;:—-]+/, "");
  if (!descriptor) return rest;
  if (!rest) return descriptor;
  const tail = SAFE_LEAD.test(rest) ? rest[0].toLowerCase() + rest.slice(1) : rest;
  return `${descriptor}, ${tail}`;
}

/**
 * Cast somebody into a piece, and where they are a look, take the standing one
 * off first.
 *
 * One look at a time. Applying a style used to swap the descriptor that was
 * leading the sentence for the new one — try six looks on a shot and you get six
 * prompts, not six stacked paragraphs — and a look that is a subject has to keep
 * that promise, or the same six attempts leave six subjects on the piece and six
 * names in the sentence.
 *
 * Everything that casts a look goes through here: the library's Apply and the
 * `/` menu's own rows.
 */
export function castIntoPiece(stored, timeline) {
  const cast = addSubjectToPiece(stored, timeline);
  if (cast?.takes !== "style") return cast;
  for (const other of [...(timeline.subjects ?? [])]) {
    if (other !== cast && other.takes === "style") dropStyle(other, timeline);
  }
  return cast;
}

/**
 * Take a look off the piece: the subject, its citations, and the picture it
 * alone was built out of.
 *
 * The same three things deleting its chip does (`editor.dropCited`), done from
 * the other end — there is no chip to delete when the swap happens inside an
 * Apply. Written here rather than reused from there because that path starts
 * from a keystroke in a box and this one starts from a preset.
 */
function dropStyle(subject, timeline) {
  const cast = timeline.subjects ?? [];
  const orphans = new Set(S.soleClaims(subject, cast));
  const pattern = S.subjectCitationRe([subject]);
  // The name, and the comma it was leading with — "@claymation, a woman waits"
  // must not become ", a woman waits".
  const scrub = (text) => String(text ?? "")
    .replace(pattern, "")
    .replace(/^[\s,;:—-]+/, "")
    .replace(/\s+,/g, ",")
    .replace(/\s{2,}/g, " ")
    .trim();
  for (const host of [timeline, ...(timeline.segments ?? [])]) {
    for (const field of ["prompt", "soundscape", "music"]) {
      if (host[field]) host[field] = scrub(host[field]);
    }
  }
  // Its picture, unless something still writes the handle by hand.
  const texts = S.allTexts(timeline);
  const keep = (asset) => !orphans.has(asset.handle) || S.handleWritten(texts, asset.handle);
  timeline.assets = (timeline.assets ?? []).filter(keep);
  for (const segment of timeline.segments ?? []) {
    if (segment.assets) segment.assets = segment.assets.filter(keep);
  }
  timeline.subjects = cast.filter((s) => s !== subject);
}

/**
 * `text`, opening with `@handle`.
 *
 * The same shape `leadWithStyle` writes — a clause, a comma, then the scene —
 * with a citation in place of the words. Which is the whole difference between
 * the two ways a look can arrive: as a descriptor typed into the sentence, or as
 * a subject the sentence names. A name can be clicked open and deleted; a
 * descriptor is prose, and the only way out of it is to select it and retype.
 *
 * Already there, already leading: nothing happens. Applying the same look twice
 * should not write it twice.
 */
export function leadWithName(text, handle) {
  const name = `@${handle}`;
  const body = String(text ?? "").trim();
  if (!handle) return body;
  if (body === name || body.startsWith(`${name},`) || body.startsWith(`${name} `)) return body;
  if (!body) return name;
  const tail = SAFE_LEAD.test(body) ? body[0].toLowerCase() + body.slice(1) : body;
  return `${name}, ${tail}`;
}

// ---- apply ------------------------------------------------------------------
//
// Never straight into the widget. Everything goes `parse* -> mutate -> sync* ->
// serialize*`, because the normalisers do real work: `syncTimeline` prunes seams
// the restored durations can no longer afford, `normalizeCheckpoint` drops a pin
// the restored references make illegal, and `parseModels` is what turns a stored
// block into a full one. A preset must not be able to put a node into a state the
// editor could not have produced.

/** What a section reverts to when the preset omits a field for it being at the
 *  default. Applying a section *replaces* it — a preset whose look never left
 *  native has to put a node that did back, not leave it where it was. */
function lookDefaults() {
  const empty = S.emptyTimeline();
  return pick(empty, ["aspect", "short_edge", "upscale", "sample_edge", "refine_denoise",
                      "face"]);
}

/** Re-handle a list of assets against what the target already has, so applying
 *  references into a card that has some of its own cannot collide. */
function rehandle(assets, target) {
  const out = [];
  const scratch = { assets: [...(target.assets ?? [])] };
  for (const asset of assets) {
    const entry = { ...asset };
    const taken = new Set(scratch.assets.map((a) => a.handle));
    if (!entry.handle || taken.has(entry.handle)) {
      entry.handle = S.nextHandle(scratch, entry.kind ?? "image");
    }
    scratch.assets.push(entry);
    out.push(entry);
  }
  return out;
}

/**
 * A free name for somebody arriving from the library.
 *
 * Two things can be in the way. Another subject of that name is the ordinary
 * one — cast @anna twice and the second is @anna_2, because two subjects called
 * the same thing is a piece where `@anna` means neither. A *file* of that name
 * is the rarer one and matters just as much: one @ means one thing, and
 * `subjectProblem` refuses a subject that shadows a handle.
 */
function freeSubjectHandle(wanted, timeline) {
  const taken = new Set([
    ...(timeline.subjects ?? []).map((subject) => subject.handle),
    ...(timeline.assets ?? []).map((asset) => asset.handle),
    // The shots' own attachments as well as the pool: on a piece of one shot
    // that is where their pictures just landed.
    ...(timeline.segments ?? []).flatMap((segment) => (segment.assets ?? [])
      .map((asset) => asset.handle)),
  ]);
  // Normalised rather than discarded. This used to answer an unusable handle
  // with the bare word "subject", which is how every atlas look whose name opens
  // on a number — "2D cutout-paper", "1970s educational film" — arrived as
  // `@subject` while the button that cast it promised its own name. Losing the
  // identity is worse than bending it: the handle is what the sentence writes.
  const cleaned = String(wanted ?? "").replace(/[^A-Za-z0-9_]/g, "_")
    .replace(/_+$/, "").slice(0, 32);
  // The format wants a letter in front; a name that opens on a digit gets one
  // rather than losing the digit. "2d_cutout_paper" and "d_cutout_paper" are
  // not the same name, and neither of them is "subject".
  const base = S.SUBJECT_HANDLE_RE.test(cleaned) ? cleaned
    : S.SUBJECT_HANDLE_RE.test(`s_${cleaned}`) ? `s_${cleaned}`
    : "subject";
  let handle = base;
  for (let n = 2; taken.has(handle); n += 1) handle = `${base}_${n}`;
  return handle;
}

/**
 * Walk one stored cast member into a piece, files and all.
 *
 * The one section that *adds* rather than replaces. Every other section owns its
 * fields outright — applying `look` puts a whole canvas back — but a cast is a
 * list of people and casting somebody has never meant dismissing everybody else.
 *
 * **Their files attach where a file attaches.** A picture of Anna arriving with
 * them is an ordinary image reference and shows up in the reference row as one,
 * under `img-2`, beside anything else attached — because that is what it is, and
 * because a file the node holds and never shows is a file nobody can size, trim
 * or take off again.
 *
 * Which list is *the* list depends on the piece, and on nothing else:
 *
 * - **One shot.** The shot's own attachments. A piece of one shot has no pool
 *   worth the name — its face draws that shot's references and nothing else — so
 *   a file put in the pool would be attached, paid for, and invisible.
 * - **A strip.** The piece's reference pool, which is the one list several cards
 *   can cite. A subject lives on the piece; their files cannot live on one card of
 *   it and be there for the rest.
 *
 * A file already attached is *used* rather than attached twice — the same
 * picture under two handles is two references to the model and half a wasted
 * budget.
 */
export function addSubjectToPiece(stored, timeline) {
  if (!stored) return null;
  if (!Array.isArray(timeline.assets)) timeline.assets = [];
  if (!Array.isArray(timeline.subjects)) timeline.subjects = [];
  const single = (timeline.segments ?? []).length === 1;
  const host = single ? timeline.segments[0] : timeline;
  if (!Array.isArray(host.assets)) host.assets = [];
  const slots = { from: [], replaces: [] };
  for (const file of stored.files ?? []) {
    if (!file?.filename) continue;
    const kind = file.kind ?? "image";
    // Anywhere the piece already holds it — the shot's row or the pool, since a
    // subject may cite either and neither is worth a second copy.
    let asset = [...host.assets, ...(single ? timeline.assets : [])].find(
      (entry) => entry.filename === file.filename && entry.kind === kind);
    if (!asset) {
      asset = {
        handle: single ? S.nextHandle(host, kind) : S.nextPoolHandle(timeline),
        kind,
        role: "reference",
        filename: file.filename,
        ref_size: file.ref_size ?? "max",
        ...(file.track ? { track: file.track } : {}),
        ...(file.trim ? { trim: file.trim } : {}),
      };
      host.assets.push(asset);
    }
    // Their looks and the place they take hold several files each; the other
    // two hold one. See `cast.LIST_ROLES`.
    if (file.slot === "from" || file.slot === "replaces") slots[file.slot].push(asset.handle);
    else if (SUBJECT_SLOTS.includes(file.slot)) slots[file.slot] = asset.handle;
    // Narrowed to what the slot says, exactly as hanging it on them by hand
    // would — a picture that arrives as their looks is a person reference and has
    // to say so. Over the default only; a file the piece already held under a
    // narrowing somebody chose keeps it. See `state.inheritTake`.
    S.inheritTake({ ...stored, takes: stored.takes ?? "person" }, file.slot, asset);
  }
  const subject = {
    handle: freeSubjectHandle(stored.handle || "subject", timeline),
    takes: S.SUBJECT_TAKES.includes(stored.takes) ? stored.takes : "person",
    from: slots.from,
    ...(slots.motion ? { motion: slots.motion } : {}),
    ...(slots.voice ? { voice: slots.voice } : {}),
    ...(slots.replaces.length ? { replaces: slots.replaces } : {}),
    ...(stored.description ? { description: String(stored.description) } : {}),
    ...(S.subjectFeatures(stored).length ? { features: S.subjectFeatures(stored) } : {}),
    ...(stored.replaces_what ? { replaces_what: String(stored.replaces_what) } : {}),
    ...(S.SUBJECT_MARKERS.includes(stored.relationship)
      ? { relationship: stored.relationship } : {}),
  };
  timeline.subjects.push(subject);
  return subject;
}

/** Write the speed row through the widget accessor. Names the target does not
 *  declare are skipped by `widgetIO.set` itself, which is what makes one stored
 *  row applicable to a pre-stage's shorter one. */
function applyRow(row, io) {
  for (const [name, value] of Object.entries(row ?? {})) io.set(name, value);
}

/**
 * Apply the chosen sections of a preset body to a parsed timeline, in place.
 *
 * The caller commits — which is what runs `syncTimeline` and writes the blob.
 */
export function applyToPiece(body, keys, timeline, io, { from = "piece" } = {}) {
  const chosen = new Set(keys);

  if (chosen.has("look")) {
    Object.assign(timeline, lookDefaults(), body.look ?? {});
  }
  if (chosen.has("weights")) {
    // Through `parseModels` rather than assigned: a stored block omits every
    // field at its default, and the state wants a full one.
    //
    // From a pre-stage this reads the H3 branch's own block — the one inside its
    // still request, which is where a creator-shaped set of weights lives on that
    // node. `crossable` has already refused every other architecture.
    timeline.models = S.parseModels(from === "prestage"
      ? (body.weights?.[S.PRESTAGE_STILL_ARCH]?.models ?? {})
      : (body.weights ?? {}));
  }
  if (chosen.has("speed")) {
    timeline.turbo = S.parseTurbo(body.speed?.turbo ?? null);
    applyRow(body.speed?.row, io);
  }
  if (chosen.has("prompt")) {
    const text = body.prompt ?? {};
    timeline.prompt = text.prompt ?? "";
    timeline.soundscape = text.soundscape ?? "";
    timeline.music = text.music ?? "";
    timeline.refined = text.refined ?? null;
  }
  if (chosen.has("style")) {
    timeline.prompt = leadWithStyle(timeline.prompt, body.style?.text);
  }
  if (chosen.has("loras")) {
    timeline.loras = JSON.parse(JSON.stringify(body.loras ?? []));
  }
  if (chosen.has("refs")) {
    // A piece's pool is references only — it has no single generation for a
    // keyframe to open, which is what a pre-stage's `init` is. Crossing from one
    // drops it rather than inventing a card to hang it on.
    const incoming = from === "prestage"
      ? (body.refs?.refs ?? []).map((ref) => ({ ...ref, role: "reference" }))
      : (body.refs ?? []);
    timeline.assets = incoming.map((asset, index) => ({
      ...asset,
      role: "reference",
      handle: asset.handle ?? `ref-${index + 1}`,
    }));
  }
  if (chosen.has("cast")) {
    // Added, never assigned — see `addSubjectToPiece`. Applied after `refs`, so
    // a preset carrying both finds the pool it is meant to look in.
    const cast = castIntoPiece(body.cast, timeline);
    // A look casts itself into the sentence. Somebody cast from the roster is
    // written in by the `@` menu at the caret, because that is where you asked
    // for them; a style applied from the library comes from a window with no
    // caret in it, and the instruction "now go and type @lego_brickfilm" was the
    // whole of what used to happen. It leads, which is where a style has always
    // gone — and it is a chip, so it opens on a click and leaves when deleted.
    // The `/` menu casts the same member and writes the name where you typed it.
    if (cast?.takes === "style") {
      // Onto the prompt that is actually on screen. `addSubjectToPiece` already
      // draws this line for the look's picture — a piece of one shot keeps its
      // files on that shot rather than in a pool — and the sentence follows it:
      // a lone shot's prompt is the node's face, while the standing prompt of a
      // strip is the one every segment inherits.
      const host = (timeline.segments ?? []).length === 1 ? timeline.segments[0] : timeline;
      host.prompt = leadWithName(host.prompt, cast.handle);
    }
  }
  if (chosen.has("strip")) {
    const strip = body.strip ?? {};
    timeline.render = strip.render === "single" ? "single" : "chained";
    if (strip.audio_tail_s !== undefined) timeline.audio_tail_s = strip.audio_tail_s;
    // Parsed back through the timeline reader, so every segment arrives in the
    // shape the editor builds rather than the shape the blob stores.
    const parsed = S.parseTimeline(JSON.stringify({
      ...JSON.parse(S.serializeTimeline(timeline)),
      segments: strip.segments ?? [],
    }));
    timeline.segments = parsed.segments;
  }
  return timeline;
}

/** Apply to one card of a strip, in place. The caller commits. */
export function applyToShot(body, keys, segment, io, { from = "shot" } = {}) {
  const chosen = new Set(keys);

  if (chosen.has("prompt")) {
    const text = body.prompt ?? {};
    segment.prompt = text.prompt ?? "";
    segment.soundscape = text.soundscape ?? "";
    segment.music = text.music ?? "";
    segment.refined = text.refined ?? null;
  }
  if (chosen.has("style")) {
    segment.prompt = leadWithStyle(segment.prompt, body.style?.text);
  }
  if (chosen.has("loras")) {
    segment.loras = JSON.parse(JSON.stringify(body.loras ?? []));
  }
  if (chosen.has("refs")) {
    // The useful direction: a pre-stage's init becomes this card's start frame,
    // which is the whole reason the pre-stage sits to the left of the Creator.
    const incoming = from === "prestage"
      ? [
          ...(body.refs?.init ? [{ ...body.refs.init, role: "first_frame", kind: "image" }] : []),
          ...(body.refs?.refs ?? []).map((ref) => ({ ...ref, role: "reference", kind: "image" })),
        ]
      : (from === "piece" ? (body.refs ?? []) : (body.refs ?? []));
    segment.assets = rehandle(
      incoming.map((asset) => ({ ...asset })), { assets: [] });
  }
  if (chosen.has("shot")) {
    const shot = body.shot ?? {};
    if (shot.duration_s !== undefined) segment.duration_s = shot.duration_s;
    segment.checkpoint = shot.checkpoint ?? "auto";
    for (const flag of ["continue", "continue_audio"]) {
      segment[flag] = shot[flag] === true;
    }
    for (const key of ["continue_from", "feather", "merge"]) {
      if (shot[key] === undefined) delete segment[key];
      else segment[key] = shot[key];
    }
  }
  if (chosen.has("speed")) {
    applyRow(body.speed?.row, io);
  }
  return segment;
}

/** Apply to a PreStage state, in place. The caller commits. */
export function applyToPreStage(body, keys, state, io, { from = "prestage" } = {}) {
  const chosen = new Set(keys);

  if (chosen.has("look")) {
    if (body.look?.aspect) state.aspect = body.look.aspect;
    if (body.look?.short_edge) state.short_edge = body.look.short_edge;
  }
  if (chosen.has("weights")) {
    if (from === "prestage") {
      if (body.weights?.arch) state.arch = body.weights.arch;
      if (body.weights?.quality) state.quality = body.weights.quality;
      state.models = { ...state.models, ...(body.weights?.models ?? {}) };
      const still = body.weights?.[S.PRESTAGE_STILL_ARCH];
      if (still) {
        if (still.frames !== undefined) state[S.PRESTAGE_STILL_ARCH].frames = still.frames;
        if (still.latent_index !== undefined) state[S.PRESTAGE_STILL_ARCH].latent_index = still.latent_index;
        // The H3 branch's checkpoints, which are not in the block above — see
        // `capturePreStage`. Restored through `parseModels` like any other.
        state[S.PRESTAGE_STILL_ARCH].request.models = S.parseModels(still.models ?? {});
      }
    } else {
      // A piece's weights only reach the H3 branch, whose request is a creator
      // request — `crossable` has already refused every other case.
      state.arch = S.PRESTAGE_STILL_ARCH;
      state[S.PRESTAGE_STILL_ARCH].request.models = S.parseModels(body.weights ?? {});
    }
  }
  if (chosen.has("speed")) {
    state.turbo = S.parseTurbo(body.speed?.turbo ?? null);
    applyRow(body.speed?.row, io);
  }
  if (chosen.has("prompt")) {
    state.prompt = body.prompt?.prompt ?? "";
  }
  if (chosen.has("style")) {
    state.prompt = leadWithStyle(state.prompt, body.style?.text);
  }
  if (chosen.has("loras")) {
    state.loras = JSON.parse(JSON.stringify(body.loras ?? []));
  }
  if (chosen.has("refs")) {
    if (from === "prestage") {
      state.init = body.refs?.init ? { ...body.refs.init } : null;
      state.refs = [];
      for (const ref of (body.refs?.refs ?? []).slice(0, S.PRESTAGE_MAX_REFS)) {
        // Re-issued rather than trusted even here: a body written by an older
        // build may have none, and a handle-less chip cannot be removed alone.
        state.refs.push({ handle: ref.handle || S.nextPreStageHandle(state),
                          filename: ref.filename });
      }
    } else {
      // From a piece or a card: its start frame becomes the init, its reference
      // images become the style references. Videos and audio have nowhere to go
      // on an image model and are dropped rather than half-applied.
      //
      // Handles are re-issued rather than carried: a pre-stage's are `img-N` from
      // `nextPreStageHandle`, and a piece's are its own scheme. A ref arriving
      // without one is not a cosmetic problem — the chip's remove button filters
      // on `r.handle !== ref.handle`, so one undefined handle deletes every ref
      // that shares it, which is all of them.
      const assets = Array.isArray(body.refs) ? body.refs : [];
      const frame = assets.find((a) => a.role === "first_frame");
      state.init = frame ? { filename: frame.filename, denoise: state.init?.denoise ?? 0.6 } : null;
      //
      // Capped at the encoder's three slots, because a preset must not be able
      // to put a node into a state the editor could not have produced — a piece
      // may hold nine reference images and Krea 2's edit path has room for three.
      state.refs = [];
      for (const asset of assets) {
        if (asset.role !== "reference" || asset.kind !== "image") continue;
        if (state.refs.length >= S.PRESTAGE_MAX_REFS) break;
        state.refs.push({ handle: S.nextPreStageHandle(state), filename: asset.filename });
      }
    }
  }
  return state;
}

// ---- export / import --------------------------------------------------------
//
// The answer to the one real weakness of userdata storage: presets do not follow
// a workflow to another machine. Browser-side both ways — a Blob download and a
// file input — because nothing here needs the server.

export function exportPresets(rows, bodies) {
  const payload = {
    kind: "minimax_creator.presets",
    version: PRESET_VERSION,
    presets: rows.map((row, index) => ({
      ...row, builtin: undefined, data: bodies[index] ?? {},
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = rows.length === 1
    ? `${rows[0].name.replace(/[^\w -]+/g, "_")}.mmcpreset.json`
    : "minimax_creator.presets.json";
  link.click();
  URL.revokeObjectURL(url);
}

/** Read an exported file back in. Every preset lands as a new one — importing is
 *  not merging, and a preset that arrived twice is two presets rather than a
 *  silent overwrite of whichever one happened to share an id. */
export async function importPresets(file) {
  const payload = JSON.parse(await file.text());
  const incoming = Array.isArray(payload?.presets) ? payload.presets : [];
  if (!incoming.length) throw new Error(t("That file holds no presets."));
  const saved = [];
  for (const entry of incoming) {
    // A style is shipped, never stored: the Style tab draws the vendored atlas
    // and would not show a row that landed in the user's library beside it. A
    // file claiming one is skipped rather than imported into somewhere invisible.
    if (!entry?.data || !SCOPES.includes(entry.scope) || entry.scope === "style") continue;
    saved.push(await savePreset({
      name: entry.name ?? t("Untitled preset"),
      scope: entry.scope,
      note: entry.note ?? "",
      folder: entry.folder ?? "",
      data: entry.data,
      // The card half is re-derived from the body rather than trusted from the
      // file — an export written by an older build may describe a card this one
      // draws differently, and the body is the part that has to survive.
      cover: entry.cover ?? null,
    }));
  }
  if (!saved.length) throw new Error(t("That file holds no presets this build understands."));
  return saved;
}
