// A preset is a setup you can put back: what was captured, where it is kept, and
// what happens when it is applied.
//
// **The sampler row is not in the blob.** `steps`, `cfg`, `sampler_name`,
// `scheduler`, the two flow shifts and the accelerators are stock ComfyUI widgets
// that `sampling.js` hides and re-draws as pills, and `graphToPrompt` reads their
// values off `node.widgets`. A preset that stored only `creator_data` would drop
// the turbo schedule, the step count and the block cache — which is most of what
// anyone tunes. So a preset is a blob *and* a widget row, which is the pair
// `stashPreStage` in `js/minimax_creator.js` already writes for its own reasons.
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
];

export const SECTION = Object.fromEntries(SECTIONS.map((s) => [s.key, s]));

/** Which sections a scope can hold at all. A shot has no canvas and no weights —
 *  the piece owns both — and only a piece has a strip. */
export const SCOPE_SECTIONS = {
  piece: ["look", "weights", "speed", "prompt", "loras", "refs", "strip"],
  shot: ["prompt", "refs", "loras", "shot", "speed"],
  prestage: ["look", "weights", "speed", "prompt", "loras", "refs"],
};

export const SCOPES = ["piece", "shot", "prestage"];
export const SCOPE_LABEL = { piece: "Piece", shot: "Shot", prestage: "Pre-stage" };

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
    const h3 = (from === "prestage" ? arch : targetArch) === S.PRESTAGE_STILL_ARCH;
    if (!h3) {
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
                              "block_cache", "spectrum", "spectrum_blend"];

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
      ...(blob.minimax ? {
        minimax: {
          ...pick(blob.minimax, ["frames", "latent_index"]),
          models: blob.minimax.request?.models ?? {},
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
  MiniMaxH3Creator: { scope: "piece", input: "creator_data" },
  MiniMaxH3Timeline: { scope: "piece", input: "timeline_data" },
  MiniMaxH3PreStage: { scope: "prestage", input: "prestage_data" },
};

/** A read-only `widgetIO` over an API prompt's `inputs`. A wired input arrives
 *  as a `[nodeId, slot]` pair rather than a value, and is no more a sampler
 *  setting than an empty socket is. */
function promptIO(inputs) {
  return {
    value: (name, fallback) => {
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
    data = capturePreStage(S.parsePreStage(source.blob), promptIO(source.inputs));
  } else {
    // Through the same normalise-then-serialise path a live node's capture goes
    // through, rather than treating the stored blob as already canonical: the
    // file may have been written by an older build, and `parseTimeline` ->
    // `syncTimeline` is what decides what this one means by it.
    const timeline = S.parseTimeline(source.blob);
    S.syncTimeline(timeline);
    data = capturePiece(timeline, promptIO(source.inputs));
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
      ? (body.weights?.minimax?.models ?? {})
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
      const still = body.weights?.minimax;
      if (still) {
        if (still.frames !== undefined) state.minimax.frames = still.frames;
        if (still.latent_index !== undefined) state.minimax.latent_index = still.latent_index;
        // The H3 branch's checkpoints, which are not in the block above — see
        // `capturePreStage`. Restored through `parseModels` like any other.
        state.minimax.request.models = S.parseModels(still.models ?? {});
      }
    } else {
      // A piece's weights only reach the H3 branch, whose request is a creator
      // request — `crossable` has already refused every other case.
      state.arch = S.PRESTAGE_STILL_ARCH;
      state.minimax.request.models = S.parseModels(body.weights ?? {});
    }
  }
  if (chosen.has("speed")) {
    state.turbo = S.parseTurbo(body.speed?.turbo ?? null);
    applyRow(body.speed?.row, io);
  }
  if (chosen.has("prompt")) {
    state.prompt = body.prompt?.prompt ?? "";
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
    if (!entry?.data || !SCOPES.includes(entry.scope)) continue;
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
