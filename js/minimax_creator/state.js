// The UI's model of creator_data, and the rules the backend will enforce anyway.
// Mirrors compile.py: it validates here so the user sees the problem while
// editing rather than at queue time, but compile.py stays authoritative.

import { ASPECT_PRESETS, FPS, MIN_SHORT_EDGE, NATIVE_SHORT_EDGE, CANVAS_MULTIPLE,
         framesForSeconds, secondsForFrames, resolveCanvas } from "./canvas.js";
import { t } from "./i18n.js";
// Where files land is not in the blob any more — it is a preference of this
// machine, in `settings.js`, so a shared workflow does not carry one person's
// folder names onto another person's disk.

// What a fresh card is worth. Mirrors `compile._duration_seconds`' default, and
// is what `addSegmentRefusal` weighs against the frame budget.
export const DEFAULT_DURATION_S = 6;

export const MAX_REF_IMAGES = 9;
export const MAX_REF_VIDEOS = 3;
export const MAX_REF_AUDIOS = 3;
export const MAX_REF_FILES = 12;

const PREFIX = { image: "img", video: "vid", audio: "aud" };

/** Which of a reference video's streams are referenced. Mirrors compile.TRACKS.
 *  "sound" drops the picture, so the clip counts as an audio reference and
 *  nothing else. */
export const TRACKS = ["picture", "picture+sound", "sound"];
export const DEFAULT_TRACK = "picture";

/** What a reference is encoded at when nobody said. Mirrors compile.DEFAULT_REF_SIZE.
 *
 *  Per kind, because "max" is a different ceiling for each: an image's is the
 *  reference pipeline's 2048 short edge, a video's is core's 768 reference
 *  canvas, which is already all a video ever gets. Audio has no size and is not
 *  in the table. */
export const DEFAULT_REF_SIZE = { image: "match", video: "max" };

/** The setting in force for an asset — the stored one, or its kind's default.
 *  Read this rather than `asset.ref_size`, which an older blob simply omits. */
export const refSize = (asset) => asset.ref_size || DEFAULT_REF_SIZE[asset.kind] || "match";

/** Whether an asset has a size to choose at all. */
export const sizeable = (asset) =>
  asset.role === "reference" && DEFAULT_REF_SIZE[asset.kind] !== undefined;

/** What of a reference image is actually the reference. "full" — the default —
 *  is the whole picture; the others narrow it so "her from @img-1" stops
 *  dragging the picture's background, palette and pose into the video. Read by
 *  the refiner's glossary; the DiT gets the same tensor either way. */
export const TAKES = ["full", "person", "object", "scene", "style"];

/** The narrowing in force for an asset — the stored one, or the whole picture. */
export const takes = (asset) => (TAKES.includes(asset.takes) ? asset.takes : "full");

/** Whether an asset has a narrowing to choose at all: reference images only —
 *  a keyframe is bound whole by the alignment line, and a video's narrowing is
 *  its track. */
export const takeable = (asset) => asset.kind === "image" && asset.role === "reference";

// ---- weights ----------------------------------------------------------------
//
// Which files the node loads. These used to be sockets; they are named in the
// blob now and `models.py` builds the loaders inside the subgraph. Mirrors
// `models.Weights` field for field — the backend reads exactly these keys.

/** In the order the weights popover lists them, which is the order you set them
 *  in: the two checkpoints, then the three things every mode needs, then the
 *  preview decoder, which changes nothing about the render. */
export const MODEL_FIELDS = ["fl2va", "ref2va", "clip", "vae", "audio_vae",
                             "preview", "sam3"];

export const MODEL_LABEL = {
  fl2va: "FL2VA checkpoint",
  ref2va: "Ref2VA checkpoint",
  clip: "Text encoder",
  vae: "Video VAE",
  audio_vae: "Audio VAE",
  preview: "Preview decoder",
  sam3: "Face detector",
};

/** What each field is for, said once, in the popover. */
export const MODEL_HINT = {
  fl2va: "Text-only, start/end frame and continuing shots run on these weights.",
  ref2va: "Anything with an @ reference runs on these weights.",
  clip: "H3's text encoder. Loaded as CLIPLoader type 'minimax'.",
  vae: "Decodes the picture.",
  audio_vae: "Decodes the sound. H3 always generates some, so this is never optional.",
  preview: "taeh3, from models/vae_approx — what the live preview decodes through. "
         + "Without it the preview is latent2rgb, which is colour without detail.",
  sam3: "A SAM3 checkpoint, from models/checkpoints — what the face pass asks "
      + "where the face is. Needed only when the face pass is switched on.",
};

/** UNETLoader's own list. Applies to both checkpoints — they are the same
 *  architecture at the same precision on any machine that has both. */
export const MODEL_DTYPES = ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"];

/**
 * What `models.route` may hold. Mirrors `models.ROUTES`.
 *
 * "auto" follows the mode, which is what the node has always done. The other two
 * are a standing instruction to run everything on one checkpoint whatever the
 * mode works out to — worth having because the two are one architecture trained
 * twice, and Ref2VA handles the keyframe and text-only payloads FL2VA was
 * trained for perfectly well.
 *
 * The per-request `checkpoint` pin could already say that for one generation,
 * but it is not sticky: attaching a reference makes the pin illegal,
 * `normalizeCheckpoint` drops it, and removing the reference leaves you back on
 * auto. A route survives that, and applies to every segment of a timeline.
 */
export const ROUTES = ["auto", "fl2va", "ref2va"];

/** The next route in the cycle. Here rather than in the badge that cycles it,
 *  so the popover that lists them and the badge that steps through them cannot
 *  disagree about the order. */
export const nextRoute = (route) => ROUTES[(ROUTES.indexOf(route) + 1) % ROUTES.length];

/** Which fields a device can be pinned for: the five that become a loader.
 *  `preview` is not one — it is a filename handed to KJNodes' node, which puts
 *  its decoder wherever the sampler is — and neither is `sam3`, which the face
 *  pass loads and releases inside its own node. Mirrors `models.DEVICE_FIELDS`. */
export const DEVICE_FIELDS = MODEL_FIELDS.filter(
  (field) => field !== "preview" && field !== "sam3");

/** Everything but `preview` is needed to render at all — and of the two
 *  checkpoints, only the one the mode routes to. `requiredModels` answers that
 *  for a given state; this is the part that never depends on the mode. */
export const ALWAYS_REQUIRED = ["clip", "vae", "audio_vae"];

export function emptyModels() {
  return {
    fl2va: "", ref2va: "", clip: "", vae: "", audio_vae: "", preview: "",
    sam3: "",
    dtype: "default",
    // Which checkpoint everything runs on whatever the mode derives.
    route: "auto",
    // `{field: "cuda:1"}` for anything pinned to a card of its own, through
    // ComfyUI-MultiGPU. Empty is the normal state and means wherever ComfyUI
    // would have put it.
    devices: {},
  };
}

/** Coerce whatever was in the blob into a full weights block. Every field may
 *  legitimately be empty: that is what a node nobody has set up yet looks like,
 *  and it is also what a workflow saved when these were sockets loads as. */
export function parseModels(raw) {
  const out = emptyModels();
  if (!raw || typeof raw !== "object") return out;
  for (const field of MODEL_FIELDS) {
    if (typeof raw[field] === "string") out[field] = raw[field].trim();
  }
  if (MODEL_DTYPES.includes(raw.dtype)) out.dtype = raw.dtype;
  if (ROUTES.includes(raw.route)) out.route = raw.route;
  // Not validated against the machine's device list: the blob may have been
  // saved on a two-card box and opened on a one-card one, and silently dropping
  // the pin would lose the setting rather than report it. `models.loader_for`
  // refuses at queue time, naming the pack.
  if (raw.devices && typeof raw.devices === "object") {
    for (const field of DEVICE_FIELDS) {
      if (typeof raw.devices[field] === "string" && raw.devices[field].trim()) {
        out.devices[field] = raw.devices[field].trim();
      }
    }
  }
  return out;
}

/** Only what was actually picked, so a blob says nothing about fields nobody
 *  has touched — and a `dtype` left alone adds nothing at all. */
function serializeModels(models) {
  const picked = parseModels(models);
  const out = {};
  for (const field of MODEL_FIELDS) {
    if (picked[field]) out[field] = picked[field];
  }
  if (picked.dtype !== "default") out.dtype = picked.dtype;
  // Absent means "follow the mode", so the common case adds nothing.
  if (picked.route !== "auto") out.route = picked.route;
  // Absent means "wherever ComfyUI would", so a single-GPU blob adds nothing.
  if (Object.keys(picked.devices).length) out.devices = { ...picked.devices };
  return { models: out };
}

/**
 * Fill empty fields from unambiguous filename matches, in place.
 *
 * For the case that matters: a workflow saved when these were sockets loads with
 * nothing chosen, and the files are almost always already on disk under
 * recognisable names. Only ever fills a field that is empty, and only when
 * exactly one candidate matches — guessing between two is wrong half the time,
 * and the node asks instead. Returns whether it changed anything.
 */
/** The experimental T=1 image decoder, by name. It is a merged H3 VAE and loads
 *  through the same node as the real one, so nothing downstream can tell them
 *  apart — which is why the guess below has to. In a video workflow it costs
 *  multi-frame reconstruction; on the pre-stage's H3 branch it is the point. */
export const IMAGE_VAE_RE = /t1[_-]?image|image[_-]vae/i;

const MODEL_HINTS = {
  fl2va: ["fl2va", "first_last"],
  ref2va: ["ref2va"],
  clip: ["minimax"],
  vae: ["minimax", "h3"],
  audio_vae: ["audio"],
  preview: ["taeh3"],
};

export function guessModels(models, files) {
  let changed = false;
  for (const field of MODEL_FIELDS) {
    if (models[field]) continue;
    const needles = MODEL_HINTS[field];
    let matched = (files?.[field] ?? []).filter((name) =>
      needles.some((needle) => name.toLowerCase().includes(needle)));
    // The two VAEs share a folder and both answer to "minimax": whichever says
    // "audio" is the audio one, and the video VAE is whatever is left.
    if (field === "vae") {
      matched = matched.filter((name) => !IMAGE_VAE_RE.test(name) && !name.toLowerCase().includes("audio"));
    }
    if (matched.length !== 1) continue;
    models[field] = matched[0];
    changed = true;
  }
  return changed;
}

/**
 * Which fields a render cannot go without: the three constants plus whichever
 * checkpoints it routes to. Mirrors `models.check`, which refuses at queue time
 * on exactly this list — a Creator passes `[checkpoint(state)]` and a Timeline
 * passes `timelineCheckpoints(timeline)`, because a chained clip legitimately
 * runs some shots on one checkpoint and some on the other.
 */
export function requiredModels(checkpoints, face = false) {
  // The detector only when a pass in this render actually asks for one — a file
  // nothing loads is not a file anybody has to own. Mirrors `models.check`.
  return [...ALWAYS_REQUIRED, ...(face ? ["sam3"] : []), ...checkpoints];
}

/**
 * The checkpoints a render will actually load, after the route has had its say.
 *
 * A forced route collapses the set to one whatever the modes derived, which is
 * the point of it: "always Ref2VA" on a timeline means one loader for the whole
 * clip rather than one per checkpoint its shots happened to want.
 */
export function routedCheckpoints(models, derived) {
  const route = models?.route ?? "auto";
  return route === "auto" ? derived : [route];
}

/** Which required fields are still empty, in listing order. */
export function missingModels(models, required) {
  return required.filter((field) => !models[field])
    .sort((a, b) => MODEL_FIELDS.indexOf(a) - MODEL_FIELDS.indexOf(b));
}

// ---- turbo ------------------------------------------------------------------
//
// The turbo block is the switch's memory, not the LoRA itself. Engaged, the
// distillation LoRA is an ordinary entry in `loras` — same stack, same manager,
// same one-click disable — and this records which file the switch reaches for,
// which quality it was left at, and what the sampler row said before it was
// thrown, so switching off puts the row back rather than guessing at defaults.
// compile.py never reads it.

/** In effort order. The step counts are the H3 turbo community's numbers: 4 is
 *  the distillation target and the floor, 6 the comfort zone, 8 about as close
 *  to a native 20-step render as the LoRAs get — past 8 they over-sharpen. */
export const TURBO_QUALITIES = ["draft", "medium", "good"];
export const TURBO_STEPS = { draft: 4, medium: 6, good: 8 };

/** What the switch sets the row to. H3 samples picture and sound as one latent
 *  on two flow clocks, and at turbo step counts res_multistep leaves the audio
 *  warbling — euler + beta is the combination the turbo LoRAs were tuned
 *  against and the one that keeps the soundtrack intact. */
export const TURBO_SAMPLER = "euler";
export const TURBO_SCHEDULER = "beta";

/** Where the row returns to when the switch is thrown off and nothing was
 *  saved — the node's own declared defaults, mirrored from creator_node.py.
 *  The shifts are the checkpoints' own flow schedules; at exactly these
 *  values the backend emits no shift node at all. */
export const TURBO_RESET = {
  steps: 20, sampler_name: "res_multistep", scheduler: "simple",
  shift_video: 12, shift_audio: 3,
};

/** What the switch engages a file at — strength and the flow shifts its card
 *  was distilled against. The two families were distilled at different scales
 *  and their cards name different schedules: lightx2v's distill runs at ~0.6
 *  with the video clock at 6, larryvrh's at 1.0 on the checkpoints' own
 *  schedule. A guess off the filename; the manager's slider and the shift
 *  pills override it like any other value. */
export function turboPreset(name) {
  if (/lightx2v/i.test(name || "")) {
    return { strength: 0.6, shift_video: 6, shift_audio: 3 };
  }
  return { strength: 1.0, shift_video: TURBO_RESET.shift_video, shift_audio: TURBO_RESET.shift_audio };
}

export const turboStrength = (name) => turboPreset(name).strength;

export function emptyTurbo() {
  return {
    // The file the switch engages, relative to models/loras. Picked in the
    // weights popover, because it is machine configuration like the files above
    // it: set once when the LoRA is downloaded, then thrown from the pill.
    lora: "",
    // The user said their checkpoint is a merged distill — turbo with no LoRA
    // at all, the switch owning only the sampler row. Remembered so the pill
    // engages directly on the next press instead of asking again.
    merged: false,
    quality: "medium",
    // Whether the switch is thrown. The LoRA entry itself can be removed from
    // two other places — the chip and the manager — which is why this is
    // reconciled against the stack on every commit rather than trusted.
    on: false,
    // The sampler row as it stood when the switch was thrown: {steps,
    // sampler_name, scheduler}. Null when off.
    saved: null,
  };
}

export function parseTurbo(raw) {
  const out = emptyTurbo();
  if (!raw || typeof raw !== "object") return out;
  if (typeof raw.lora === "string") out.lora = raw.lora.trim();
  out.merged = raw.merged === true;
  if (TURBO_QUALITIES.includes(raw.quality)) out.quality = raw.quality;
  out.on = raw.on === true;
  if (raw.saved && typeof raw.saved === "object") {
    out.saved = {
      steps: Number(raw.saved.steps) || TURBO_RESET.steps,
      sampler_name: typeof raw.saved.sampler_name === "string"
        ? raw.saved.sampler_name : TURBO_RESET.sampler_name,
      scheduler: typeof raw.saved.scheduler === "string"
        ? raw.saved.scheduler : TURBO_RESET.scheduler,
      // Rows saved before the shifts existed restore the defaults, which is
      // exactly what those rows were running at.
      shift_video: Number(raw.saved.shift_video) || TURBO_RESET.shift_video,
      shift_audio: Number(raw.saved.shift_audio) || TURBO_RESET.shift_audio,
    };
  }
  return out;
}

/** Nothing at all until a file is picked, so every blob from before the switch
 *  existed — and every node nobody turbos — says nothing about it. */
export function serializeTurbo(turbo) {
  const picked = parseTurbo(turbo);
  if (!picked.lora && !picked.merged && !picked.on) return {};
  const out = { lora: picked.lora };
  if (picked.merged) out.merged = true;
  if (picked.quality !== "medium") out.quality = picked.quality;
  if (picked.on) out.on = true;
  if (picked.saved) out.saved = { ...picked.saved };
  return { turbo: out };
}

/** The two H3 checkpoints, which is also the granularity a LoRA belongs to:
 *  T2VA, I2VA, L2VA and FL2VA are all the same weights. */
export const CHECKPOINTS = ["fl2va", "ref2va"];
export const CHECKPOINT_LABEL = { fl2va: "FL2VA", ref2va: "Ref2VA" };
/** What `state.checkpoint` may hold: follow the mode, or pin one. */
export const CHECKPOINT_CHOICES = ["auto", ...CHECKPOINTS];
export const DEFAULT_STRENGTH = 1.0;

/** Mirrors compile.UPSCALE_MODES, first_pass_edge and the refine-denoise
 *  clamp. A render whose first pass sits under the slider goes one of two
 *  ways: sample at the first-pass edge and refine up ("two_pass", the
 *  default), or one pass at the slider's size ("direct" — past native,
 *  off-distribution). The first-pass edge is native unless lowered, so past
 *  native two passes happen on their own, and under it only when the user
 *  lowers the edge — a blob without the key keeps meaning what it meant. */
export const UPSCALE_MODES = ["two_pass", "direct"];
export const DEFAULT_REFINE_DENOISE = 0.5;
export const MIN_REFINE_DENOISE = 0.1;
export const MAX_REFINE_DENOISE = 0.9;

const clampSampleEdge = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return NATIVE_SHORT_EDGE;
  const snapped = Math.round(n / CANVAS_MULTIPLE) * CANVAS_MULTIPLE;
  return Math.min(NATIVE_SHORT_EDGE, Math.max(MIN_SHORT_EDGE, snapped));
};

/** The short edge the first of two passes samples at: the stored edge, capped
 *  by the slider — at the cap the two passes collapse into one render. */
export const sampleEdge = (target) =>
  Math.min(clampSampleEdge(target.sample_edge), target.short_edge);

/** Whether this canvas owner renders in two passes. `target` is anything with
 *  `short_edge`, `sample_edge` and `upscale` — a state or a timeline. */
export const twoPass = (target) =>
  sampleEdge(target) < target.short_edge && target.upscale !== "direct";

/**
 * The face pass. Mirrors `compile.face_piece` / `compile.face_for`.
 *
 * H3 draws a face badly in proportion to how small the head is in frame, which
 * is not something a bigger canvas reaches. So after a pass is decoded, the
 * face is cropped out frame by frame, re-drawn at a canvas where it fills the
 * picture, and composited back.
 *
 * The piece owns the two knobs and a card owns only the switch: "on", "off", or
 * nothing at all, which inherits. How the pass works is one answer per render;
 * what a card gets to say is whether this shot is one that needs it.
 */
export const DEFAULT_FACE_CANVAS = 512;
export const MIN_FACE_CANVAS = MIN_SHORT_EDGE;
export const MAX_FACE_CANVAS = NATIVE_SHORT_EDGE;
export const DEFAULT_FACE_DENOISE = 0.45;
export const MIN_FACE_DENOISE = 0.1;
export const MAX_FACE_DENOISE = 0.9;
export const FACE_OVERRIDES = ["on", "off"];

export const emptyFace = () => ({
  on: false, canvas: DEFAULT_FACE_CANVAS, denoise: DEFAULT_FACE_DENOISE,
});

export function parseFace(raw) {
  const face = { ...emptyFace(), ...(raw && typeof raw === "object" ? raw : {}) };
  const canvas = Number(face.canvas);
  const denoise = Number(face.denoise);
  face.on = Boolean(face.on);
  face.canvas = Number.isFinite(canvas)
    ? Math.min(MAX_FACE_CANVAS, Math.max(MIN_FACE_CANVAS,
        Math.round(canvas / CANVAS_MULTIPLE) * CANVAS_MULTIPLE))
    : DEFAULT_FACE_CANVAS;
  face.denoise = Number.isFinite(denoise)
    ? Math.min(MAX_FACE_DENOISE, Math.max(MIN_FACE_DENOISE, denoise))
    : DEFAULT_FACE_DENOISE;
  return face;
}

/** Absent while it is off, so every blob that never asked for one is unchanged. */
export const serializeFace = (face) =>
  (face?.on ? { face: { on: true, canvas: face.canvas, denoise: face.denoise } } : {});

/** What one card's switch says: "on", "off", or "" for inherit. */
export const faceOverride = (segment) =>
  (FACE_OVERRIDES.includes(segment?.face) ? segment.face : "");

/** Whether this shot runs the face pass, piece and card taken together. */
export const faceOn = (piece, segment) => {
  const override = faceOverride(segment);
  if (override) return override === "on" && Boolean(piece?.face?.on);
  return Boolean(piece?.face?.on);
};

/** Whether any shot on this strip runs one — what decides if a detector is
 *  needed at all. Mirrors the `face` flag `render.emit` hands `models.check`. */
export const faceAnywhere = (timeline) =>
  Boolean(timeline?.face?.on)
  && (timeline.segments ?? []).some((segment) => !isClip(segment) && faceOn(timeline, segment));

const clampRefineDenoise = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULT_REFINE_DENOISE;
  return Math.min(MAX_REFINE_DENOISE, Math.max(MIN_REFINE_DENOISE, n));
};

/** A fresh generation. `prefix` is where its renders land when the blob does
 *  not say — the video default, or the stills folder for the pre-stage's H3
 *  branch, whose request is one of these too. */
export function emptyState() {
  return {
    version: 1,
    prompt: "",
    // The refiner's rewrite of `prompt`, when there is one: `{body, sections?,
    // source, model, enabled}`. Stored with its `@handles` intact rather than
    // with H3's ordinals in it, so compile.py substitutes it exactly as it
    // substitutes typed text and attaching an asset re-labels it correctly.
    refined: null,
    // The two Context-IR audio fields. The timeline owns its own pair and hands
    // them down; a lone generation has nowhere else to keep them.
    soundscape: "",
    music: "",
    assets: [],
    loras: [],
    duration_s: DEFAULT_DURATION_S,
    aspect: "16:9",
    short_edge: NATIVE_SHORT_EDGE,
    // The two-pass choice and its two knobs. Owned wherever the canvas is
    // owned; all inert while the first-pass edge is not under the slider.
    upscale: UPSCALE_MODES[0],
    sample_edge: NATIVE_SHORT_EDGE,
    refine_denoise: DEFAULT_REFINE_DENOISE,
    // The face pass, off until asked for. Owned wherever the canvas is owned.
    face: emptyFace(),
    // "auto" follows the mode. Pinning it runs the same payload on the other
    // weights; compile.py decides which pins it will accept.
    checkpoint: "auto",
    // Which files to load. Owned by the node, not by a segment — a timeline
    // segment inherits the timeline's and never carries its own.
    models: emptyModels(),
    // The turbo switch. Owned by the node for the same reason the weights are.
    turbo: emptyTurbo(),
  };
}

export function parseState(raw) {
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      const state = { ...emptyState(), ...parsed };
      // Workflows saved before LoRAs existed have no key at all, and a
      // hand-edited blob can have the wrong type in it.
      if (!Array.isArray(state.loras)) state.loras = [];
      if (!Array.isArray(state.assets)) state.assets = [];
      if (!state.refined || typeof state.refined !== "object") state.refined = null;
      for (const key of ["soundscape", "music"]) {
        if (typeof state[key] !== "string") state[key] = "";
      }
      if (!CHECKPOINT_CHOICES.includes(state.checkpoint)) state.checkpoint = "auto";
      if (!UPSCALE_MODES.includes(state.upscale)) state.upscale = UPSCALE_MODES[0];
      state.sample_edge = clampSampleEdge(state.sample_edge);
      state.refine_denoise = clampRefineDenoise(state.refine_denoise);
      state.face = parseFace(state.face);
      state.models = parseModels(state.models);
      state.turbo = parseTurbo(state.turbo);
      normalizeCheckpoint(state);
      for (const asset of state.assets) {
        if (asset?.kind !== "video") continue;
        // Workflows saved before the picture/sound split carry the two-state
        // `with_audio` boolean. compile.py still reads it; the editor works in
        // tracks from here on, so it is converted on the way in.
        if (!TRACKS.includes(asset.track)) asset.track = asset.with_audio ? "picture+sound" : DEFAULT_TRACK;
        delete asset.with_audio;
      }
      return state;
    }
  } catch {
    // A malformed blob is recoverable: fall back to empty rather than leaving
    // the node unusable. The user's text is gone either way.
  }
  return emptyState();
}

/** LoRA entries, stripped to what compile.py reads. Shared by a segment's own
 *  list and the timeline's global one — they are the same kind of entry and are
 *  merged into one stack by `compile.merge_loras`. */
function serializeLoras(entries) {
  return entries.map((entry) => {
    const out = { name: entry.name, strength: round2(entry.strength) };
    if (entry.enabled === false) out.enabled = false;
    // The literal words, not a pointer at the sidecar: creator_data has to
    // still say what it means on a machine where that LoRA is missing.
    if (entry.triggers?.length) out.triggers = [...entry.triggers];
    // Absent means both checkpoints, so the common case adds nothing.
    if (!claimsBoth(entry)) out.modes = [...entry.modes];
    return out;
  });
}

/** The refiner's rewrite, stripped to what compile.py reads, or nothing.
 *
 *  An empty body is nothing at all rather than an empty rewrite: reverting
 *  should leave a blob that looks like one the refiner was never run on. */
function serializeRefined(refined) {
  const body = (refined?.body ?? "").trim();
  const sections = refined?.sections;
  // A timeline's own `refined` may hold nothing but `replaced` — a chained
  // refine-all writes the rewritten global prompt and audio into the visible
  // fields and keeps only the originals here — and dropping it would leave
  // Revert nothing to restore after a reload.
  if (!body && !sections && !refined?.replaced) return {};
  return {
    refined: {
      ...(body ? { body } : {}),
      // The rewrite is the shot alone, and compile joins the global prompt in
      // front of it as it does for typed text. Absent means it absorbed the
      // join when it was written, and compile leaves it whole.
      ...(refined.scope === "shot" ? { scope: "shot" } : {}),
      ...(sections ? { sections: { ...sections } } : {}),
      // Kept so the panel can say the prompt has moved on since; compile.py
      // never reads either, and both are small enough not to be worth splitting
      // out of the one object that says "this was refined".
      source: refined.source ?? "",
      ...(refined.model ? { model: refined.model } : {}),
      // Which template wrote this prose, and whether it was pinned — kept for
      // the same reason as `model`: after a reload it is the only record of
      // which form the stored rewrite is in.
      ...(refined.template ? { template: refined.template } : {}),
      ...(refined.forced ? { forced: true } : {}),
      // What the rewrite overwrote in `soundscape` and `music`, so Revert puts
      // them back rather than leaving generated prose in fields the user never
      // typed in — including after a reload, which is exactly when nobody
      // remembers what was in them.
      // Two empty strings when that is what was there: "the user had typed
      // nothing" is the fact Revert needs most, and dropping it as falsy would
      // leave the rewrite's own prose behind on exactly that case.
      ...(refined.replaced ? { replaced: { ...refined.replaced } } : {}),
      // Absent means on, so the common case adds nothing.
      ...(refined.enabled === false ? { enabled: false } : {}),
    },
  };
}

/** Asset entries, stripped to what compile.py reads. Shared by a state's own
 *  list and the timeline's reference pool — same shape, same defaults. */
function serializeAssets(assets) {
  return assets.map((asset) => {
    const out = { handle: asset.handle, kind: asset.kind, role: asset.role, filename: asset.filename };
    if (asset.kind === "video") out.track = asset.track || DEFAULT_TRACK;
    // Only what departs from the backend's own default for the kind, so the
    // common setting adds nothing and an old blob round-trips unchanged.
    if (sizeable(asset) && refSize(asset) !== DEFAULT_REF_SIZE[asset.kind]) {
      out.ref_size = refSize(asset);
    }
    // Absent means the whole file, so a clip nobody trimmed adds nothing.
    if (asset.trim && asset.kind !== "image") {
      out.trim = { start: asset.trim.start, end: asset.trim.end };
    }
    // Absent means the whole picture, so an unnarrowed reference adds nothing
    // and compile.py refuses the field anywhere it means nothing.
    if (takeable(asset) && takes(asset) !== "full") {
      out.takes = takes(asset);
    }
    return out;
  });
}

/** The parts of a state every generation has, timeline segment or not. */
function serializeCommon(state) {
  return {
    prompt: state.prompt ?? "",
    ...serializeRefined(state.refined),
    // An empty field is emitted as nothing, which is not the same as "N/A" —
    // see contextir.compose. A segment leaving them blank inherits the
    // timeline's rather than clearing them.
    ...(state.soundscape?.trim() ? { soundscape: state.soundscape } : {}),
    ...(state.music?.trim() ? { music: state.music } : {}),
    assets: serializeAssets(state.assets),
    loras: serializeLoras(state.loras),
    duration_s: state.duration_s,
    // Absent means "follow the mode", so the common case adds nothing.
    ...(state.checkpoint && state.checkpoint !== "auto" ? { checkpoint: state.checkpoint } : {}),
  };
}

export function serializeState(state) {
  return JSON.stringify({
    version: 1,
    ...serializeCommon(state),
    aspect: state.aspect,
    short_edge: state.short_edge,
    // Absent means the default, so a blob that never left native adds nothing.
    ...(state.upscale !== UPSCALE_MODES[0] ? { upscale: state.upscale } : {}),
    ...(state.sample_edge !== NATIVE_SHORT_EDGE ? { sample_edge: state.sample_edge } : {}),
    ...(state.refine_denoise !== DEFAULT_REFINE_DENOISE
      ? { refine_denoise: state.refine_denoise } : {}),
    ...serializeFace(state.face),
    // Not in serializeCommon: the weights belong to the node, and a timeline
    // segment goes through that function too. The turbo switch likewise.
    ...serializeModels(state.models),
    ...serializeTurbo(state.turbo),
  }, null, 2);
}

// ---- timeline ---------------------------------------------------------------
//
// A timeline is a global prompt, one canvas, and a list of segments. A segment
// is an ordinary state — same assets, same LoRAs, same checkpoint routing, so
// the same editor drives it — minus the canvas, which belongs to the timeline
// because the segments are concatenated at the end and have to match, plus one
// flag saying whether it starts from the previous segment's last frame.

// Mirrors compile.MAX_SEGMENTS / compile.MAX_TIMELINE_FRAMES — two bounds on two
// quantities, and only the second is about work. Cards are bounded so a corrupt
// blob is refused before it is walked; how long the queue runs is a question
// about frames, because a pass is anything from 5 to 1445 of them and a run of
// cards is one generation. `canAddSegment` is what the strip actually asks.
export const MAX_SEGMENTS = 240;
export const MAX_TIMELINE_FRAMES = 30 * 60 * FPS;

/** Mirrors compile.RENDER_MODES. "chained" is a generation per segment,
 *  concatenated; "single" is one generation whose description holds every
 *  segment as a `[Shot n]` with its own cut time.
 *
 *  Both are now readings of the same thing — see `passes` — and `render` is
 *  derived from the merge flags rather than set. It is still written, and still
 *  what every "is the whole strip one generation" question asks. */
export const RENDER_MODES = ["chained", "single"];
export const isSingle = (timeline) => timeline.render === "single";

/** Whether a segment is generated in the same pass as the one before it.
 *  Meaningless on the first — there is nothing in front of it to merge into —
 *  which `syncTimeline` keeps true by clearing it there. */
export const merged = (segment) => segment.merge === true;

/**
 * The strip as passes: `[{ start, end, segments }]`, in play order.
 *
 * Mirrors `compile.timeline_runs`. A pass is one generation, so a pass is what
 * a seam sits between, what a checkpoint and a LoRA stack belong to, and what
 * the cost line counts. Most passes are one segment long, which is what chained
 * always was; a strip merged end to end is one pass, which is what one pass
 * always was. The middle — a run of shots the model cuts between, chained to
 * the rest — is what neither could say.
 */
export function passes(timeline) {
  const runs = [];
  timeline.segments.forEach((segment, index) => {
    if (index && merged(segment)) runs[runs.length - 1].end = index + 1;
    else runs.push({ start: index, end: index + 1 });
  });
  return runs.map((run) => ({ ...run, segments: timeline.segments.slice(run.start, run.end) }));
}

/** The pass a segment is generated in. */
export function passOf(timeline, index) {
  return passes(timeline).find((pass) => index >= pass.start && index < pass.end);
}

/** Mirrors compile.DEFAULT_AUDIO_TAIL_S / MAX_AUDIO_TAIL_S. Short on purpose:
 *  the reference rows ride through every sampling step, and a long tail pushes
 *  the target's time origin away from the inherited start frame. */
export const DEFAULT_AUDIO_TAIL_S = 1.0;
export const MAX_AUDIO_TAIL_S = 4.0;

const clampTail = (value) => {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return DEFAULT_AUDIO_TAIL_S;
  return Math.min(seconds, MAX_AUDIO_TAIL_S);
};

// ---- clip cards -------------------------------------------------------------
//
// A card that is not a generation: footage the user already has, cut into the
// piece and played as it is. Mirrors compile.SEGMENT_KINDS.
//
// It is a card rather than a reference because it occupies time on the strip —
// it has a length, a place in the order and seams on both sides of it, which
// is exactly what a shot has. A reference clip is something a generation looks
// at; this one is part of the finished video.

export const SEGMENT_KINDS = ["shot", "clip"];

/** Whether a card is supplied footage. Absent means a shot, which is every
 *  card written before clips existed. */
export const isClip = (segment) => segment?.kind === "clip";

/** A clip card's length: its trim's, or the whole file's as the probe read it.
 *  Not a setting — how much of the file plays is what decides it. */
export function clipSeconds(segment) {
  const trim = segment?.trim;
  if (trim && Number.isFinite(trim.start) && Number.isFinite(trim.end) && trim.end > trim.start) {
    return trim.end - trim.start;
  }
  return Number(segment?.duration_s) || 0;
}

/** Whether a clip card plays with its own sound. On unless the card says not:
 *  a clip chosen for a moment of action is usually wanted for the sound of it. */
export const clipSound = (segment) => segment?.sound !== false;

/**
 * A clip card, from what the picker and the probe route between them know.
 *
 * `width`/`height` are the file's own, and are what lets the timeline take its
 * aspect from the footage without the backend opening the file. `has_audio` is
 * the probe's too — a clip with no soundtrack cannot carry one across a seam,
 * and the switch has to be able to say so rather than fail at queue time.
 */
export function clipSegment({ filename, duration, width, height, hasAudio }) {
  return {
    kind: "clip",
    filename,
    duration_s: Number(duration) || 0,
    ...(width && height ? { width, height } : {}),
    // Not serialized — a fact about the file, re-read when it is re-attached,
    // and only ever used to grey out a control the file cannot honour.
    has_audio: hasAudio !== false,
    // The seam in front of a clip runs backwards: the shot before it ends on
    // this clip's opening frame. Off on a new card, unlike a new shot's seam,
    // because turning it on changes how the card *before* it is generated —
    // it pins that generation's last frame, which a shot carrying references
    // cannot do. A hard cut is the one default that is always available.
    continue: false,
    continue_audio: false,
  };
}

export function emptySegment() {
  const state = emptyState();
  delete state.version;
  state.continue = false;
  // The sound seam, independent of the picture one: a hard cut whose music keeps
  // playing and a match cut that resets the sound are both ordinary.
  state.continue_audio = false;
  return state;
}

/** A segment added behind another. A strip is usually one continuous piece, so
 *  the seam opens live on both tracks with a medium blend of motion across the
 *  cut — the settings a hard cut would make the user click on every card. The
 *  first segment has no seam and stays `emptySegment`, and a loaded timeline
 *  keeps exactly what it stored. */
export function continuingSegment() {
  const state = emptySegment();
  state.continue = true;
  state.continue_audio = true;
  state.feather = FEATHER_GRID[2]; // Medium — 0.9 s of motion at 24 fps
  return state;
}

export function emptyTimeline() {
  return {
    version: 2,
    // How the segments become video. Chained by default: it is the mode with no
    // length limit, and it is what every timeline saved before this existed was.
    render: "chained",
    prompt: "",
    // The two Context-IR audio fields, global because a soundscape and a score
    // belong to the piece rather than to one shot. See contextir.py.
    soundscape: "",
    music: "",
    // The reference form's three analysis sections, in one pass only: there the
    // shots are a single generation over one merged reference pool, so the
    // analysis describes the whole clip. Chained, each segment keeps its own.
    refined: null,
    aspect: "16:9",
    short_edge: NATIVE_SHORT_EDGE,
    // The two-pass choice rides with the canvas, which is the timeline's.
    upscale: UPSCALE_MODES[0],
    sample_edge: NATIVE_SHORT_EDGE,
    refine_denoise: DEFAULT_REFINE_DENOISE,
    // The face pass, off until asked for. One answer for the whole piece; a
    // card may still opt out of it.
    face: emptyFace(),
    // Patched onto every segment, in front of whatever that segment adds. What
    // a turbo LoRA is for: you want it on the whole clip, not shot by shot.
    loras: [],
    // The piece's own reference pool — a character sheet, a location plate —
    // cited by @handle from any segment's text and injected into exactly the
    // segments that cite it. Mirrors compile.timeline_pool.
    assets: [],
    // How much of the previous segment's sound a continuing seam inherits.
    // Mirrors compile.DEFAULT_AUDIO_TAIL_S.
    audio_tail_s: DEFAULT_AUDIO_TAIL_S,
    // One set of weights for the whole clip. Chained or not, the segments are
    // concatenated at the end and cannot come from different checkpoints of the
    // same name any more than they can come out different sizes.
    //
    // Routed to Ref2VA rather than auto: it is the stronger checkpoint — a
    // superset of what FL2VA was trained for, handling text-only and keyframe
    // segments alongside references — and one route means a strip mixing
    // reference and plain cards runs on one set of weights. The pill still
    // overrides it, and a saved timeline keeps whatever it stored (a blob with
    // a models block and no route reads back as auto, exactly as it ran).
    models: { ...emptyModels(), route: "ref2va" },
    // The turbo switch. Global like the LoRA it engages: a speed-up belongs to
    // the run, not to shot 3.
    turbo: emptyTurbo(),
    // One blank shot, because that is what this node is when you drop it. It
    // was empty while the strip was a node of its own: a new timeline was a
    // reel with nothing on it and two equally good ways to begin, and an
    // opening card would have had to be a shot when a clip was just as likely.
    //
    // The merge answers that question for it. A piece of one shot *is* the
    // Creator — you drop this node to write a video — so the shot is the
    // default and the clip is the other thing you can do to a strip that
    // exists. Which also retires the state the old reasoning was protecting
    // against: the card is not undeletable, it is only unemptyable, and
    // clearing the last one leaves a blank shot rather than a piece with
    // nothing in it and a face that can only say so. See `syncCanvas`.
    segments: [emptySegment()],
  };
}

/**
 * What "Clear" empties: the piece as it was written.
 *
 * The standing prompt, the two Context-IR audio fields, the rewrite over them,
 * the reference pool, and the strip — which goes back to one blank shot, the
 * same thing a piece is when you drop the node.
 *
 * Everything not named here survives, and that is the whole point of the
 * control. Where the weights are, which LoRAs are patched onto them, the turbo
 * switch, the canvas, the face pass and the render mode are all set once for a
 * machine or for a project; retyping them is not part of starting the next
 * scene. The sampler row is not in the blob at all and so is untouched by
 * construction.
 */
export const CLEARED_KEYS = ["prompt", "soundscape", "music", "refined", "assets", "segments"];

/** The shot's own writing — everything on a card that is not mirrored down onto
 *  it by `syncCanvas`, which is where the canvas and the pool arrive from. */
const segmentWritten = (segment) =>
  Boolean((segment.prompt || "").trim()
    || (segment.soundscape || "").trim()
    || (segment.music || "").trim()
    || segment.refined
    || segment.assets?.length
    || segment.loras?.length
    || isClip(segment)
    || segment.duration_s !== DEFAULT_DURATION_S
    || (segment.checkpoint && segment.checkpoint !== "auto")
    || faceOverride(segment));

/** Whether `clearPiece` would change anything. A piece still as it was dropped
 *  has nothing to clear, and the tool says so by being unavailable rather than
 *  by arming, confirming and then doing nothing. */
export function pieceWritten(timeline) {
  if (CLEARED_KEYS.some((key) => typeof timeline[key] === "string" && timeline[key].trim())) return true;
  if (timeline.refined) return true;
  if (timeline.assets?.length) return true;
  const segments = timeline.segments ?? [];
  return segments.length !== 1 || segmentWritten(segments[0]);
}

/** Empty the piece, in place — the body holds this object and everything else
 *  in the node mutates it rather than replacing it. */
export function clearPiece(timeline) {
  const blank = emptyTimeline();
  for (const key of CLEARED_KEYS) timeline[key] = blank[key];
}

/**
 * Mirror the timeline's canvas onto each segment, so a segment state answers
 * `resolved()` and `mode()` on its own and the editor needs no special case.
 * Stripped again by `serializeTimeline` — the segments do not own it.
 */
function syncCanvas(timeline) {
  // A piece is at least one shot, so deleting the last card clears it rather
  // than emptying the piece. What that removes is a face nobody wanted: a
  // summary reporting "empty · 0 segments" with a button offering to open a
  // strip that has nothing on it, reached by doing the ordinary thing of
  // deleting cards. The node is the Creator, and the Creator with nothing in it
  // is a blank prompt.
  //
  // Here rather than in the delete handler, so a hand-edited blob and a saved
  // workflow arrive in the same shape as one the strip just emptied. The two
  // ways to begin a piece are still both offered — they are the add tile beside
  // the card, which is where they are the rest of the time.
  if (!timeline.segments.length) timeline.segments.push(emptySegment());
  // A clip is not generated, so it cannot share a generation — neither by
  // being merged into the pass in front of it nor by having a card merged into
  // it. Cleared here rather than guarded at every read, the same way the seam
  // flags on segment 1 are, so reordering cannot leave a merge behind that
  // `compile.timeline_runs` would refuse the whole strip over.
  timeline.segments.forEach((segment, index) => {
    if (isClip(segment)) delete segment.merge;
    if (index && isClip(timeline.segments[index - 1])) delete segment.merge;
  });
  for (const segment of timeline.segments) {
    if (isClip(segment)) continue;   // no canvas, no pool, no prompt to mirror
    segment.aspect = timeline.aspect;
    segment.short_edge = timeline.short_edge;
    segment.upscale = timeline.upscale;
    segment.sample_edge = timeline.sample_edge;
    segment.refine_denoise = timeline.refine_denoise;
    // The face pass is *not* mirrored down: a segment's `face` key is its own
    // switch, not a copy of the piece's settings. What is cleaned up here is a
    // card left saying "on" after the piece was switched off — compile refuses
    // that pairing by name, and a switch nobody can see is not worth being
    // refused over. Same repair `merge` gets on a clip, two blocks up.
    if (!timeline.face?.on && faceOverride(segment) === "on") delete segment.face;
    // The piece's reference pool, mirrored like the canvas so a segment state
    // answers `mode()`, `checkpoint()` and the prompt box's chips on its own:
    // a segment citing @ref-1 is a reference generation and every accessor has
    // to say so. The global texts ride along because a citation in them is a
    // citation here too — the join and the audio inheritance are compile's,
    // and `citedPool` mirrors both. Never serialized — all of it is the
    // timeline's.
    segment.pool = timeline.assets ?? [];
    segment.globalTexts = {
      prompt: timeline.prompt ?? "",
      soundscape: timeline.soundscape ?? "",
      music: timeline.music ?? "",
    };
  }
  // Segment 1 has nothing in front of it. Kept in step here rather than guarded
  // at every read, so reordering cannot leave a stale flag behind. `merge` goes
  // with the seam flags because it is one of them — the statement that there is
  // no seam here at all — and a segment moved to the front has nothing left to
  // be merged into.
  if (timeline.segments.length) {
    timeline.segments[0].continue = false;
    timeline.segments[0].continue_audio = false;
    delete timeline.segments[0].merge;
  }
  // `render` is derived, not set: it is the name for a strip that turned out to
  // be one pass end to end, which is a fact about the merge flags. Everything
  // that asks `isSingle` is asking exactly that. A lone segment keeps whatever
  // it was told — with no seam in the strip there is nothing to derive from,
  // and the answer only decides whether the card is called a shot.
  if (timeline.segments.length > 1) {
    timeline.render = timeline.segments.every((segment, index) => !index || merged(segment))
      ? "single" : "chained";
  }
  // A strip holding footage is never one pass, whatever the flags say: a clip
  // is played rather than generated, so there is no single generation for the
  // strip to collapse into. A timeline saved as one pass before a clip was cut
  // into it opens as the chain it now is.
  if (timeline.segments.some(isClip)) timeline.render = "chained";
  // A seam may name any earlier segment as its source; anything else — the
  // previous one included, which is what absence already means — is dropped.
  // Same policy as the flags: pruned here once rather than guarded at every
  // read, so reordering and deleting cannot leave a stale source behind.
  timeline.segments.forEach((segment, index) => {
    const from = segment.continue_from;
    if (!Number.isInteger(from) || from < 1 || from >= index) delete segment.continue_from;
    // A feather the duration can no longer afford — the overlap is trimmed
    // off after decode, so it must stay under half the clip — is dropped the
    // same way, rather than left to fail at queue time.
    // A blend the segment it is generated in can no longer afford — the
    // overlap is trimmed off after decode, so it must stay under half the
    // clip — is dropped the same way, rather than left to fail at queue time.
    // For a clip card the blend is spent by the card *before* it, since that
    // is the generation re-making those frames.
    if (segment.feather) {
      const paying = isClip(segment) ? timeline.segments[index - 1] : segment;
      if (!paying || isClip(paying)
          || 2 * segment.feather > framesForSeconds(paying.duration_s)) {
        delete segment.feather;
      }
    }
    // Nothing runs into a clip that has no generation in front of it — two
    // clips end to end have no sampler between them to condition.
    if (isClip(segment) && (!index || isClip(timeline.segments[index - 1]))) {
      segment.continue = false;
      segment.continue_audio = false;
      delete segment.feather;
    }
    // A clip with no soundtrack has none to carry backwards across the seam.
    if (isClip(segment) && segment.has_audio === false) segment.continue_audio = false;
  });
  return timeline;
}

export { syncCanvas as syncTimeline };

/**
 * The fields a piece owns and a shot does not — the whole of the old
 * creator/timeline split, written down as a list. A lone generation kept all of
 * these inline because it had nowhere else to keep them; a piece holds them once
 * and every shot on the strip is held to them. `syncCanvas` mirrors the first
 * five back down, so a segment state still answers `resolved()` on its own.
 *
 * Mirrors `compile.PIECE_FIELDS`.
 */
export const PIECE_FIELDS = ["aspect", "short_edge", "upscale", "sample_edge",
                             "refine_denoise", "face", "models", "turbo",
                             "output_prefix"];

/** What only a lone generation ever carried at the top level. Tells a version-1
 *  `creator_data` blob from a fresh node's "{}" — which is an empty piece and
 *  must not become a shot nobody wrote. Mirrors `compile._LONE_SHOT_KEYS`. */
const LONE_SHOT_KEYS = ["prompt", "assets", "loras", "duration_s", "checkpoint",
                        "refined", "soundscape", "music"];

/**
 * A version-1 `creator_data` blob, read as the one-shot piece it always was.
 *
 * The mirror of `compile.as_piece`, and everything argued there holds here: it
 * runs on every load of every workflow saved while these were two nodes, it is
 * the exact inverse of the split `PIECE_FIELDS` names, and the three placements
 * it gets right are `prompt` and `assets` going *down* to the shot while the
 * seven piece fields go up.
 *
 * Idempotent — a blob that already has a strip is returned untouched.
 */
export function asPiece(parsed) {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed.segments)) return parsed;
  if (parsed.version !== 1 && !LONE_SHOT_KEYS.some((key) => key in parsed)) return parsed;

  const shot = { ...parsed };
  delete shot.version;
  // `models` even when the blob carried none: the empty piece routes to Ref2VA
  // by preference, and a lone generation that rendered on `auto` must not
  // quietly change weights by being opened. An empty block parses to auto.
  const piece = { version: 2, prompt: "", models: {} };
  for (const field of PIECE_FIELDS) {
    if (field in shot) {
      piece[field] = shot[field];
      delete shot[field];
    }
  }
  piece.segments = [shot];
  return piece;
}

export function parseTimeline(raw) {
  try {
    const parsed = asPiece(JSON.parse(raw));
    if (parsed && typeof parsed === "object") {
      const timeline = { ...emptyTimeline(), ...parsed };
      // Workflows saved before either existed have no key at all, and a
      // hand-edited blob can have the wrong type in it.
      if (!Array.isArray(timeline.loras)) timeline.loras = [];
      if (!Array.isArray(timeline.assets)) timeline.assets = [];
      timeline.assets = timeline.assets.filter(
        (asset) => asset && typeof asset.handle === "string" && typeof asset.filename === "string");
      for (const asset of timeline.assets) {
        // A pool entry is a reference by definition — compile.timeline_pool
        // refuses anything else, so nothing else is kept here either.
        asset.role = "reference";
        if (asset.kind === "video" && !TRACKS.includes(asset.track)) {
          asset.track = asset.with_audio ? "picture+sound" : DEFAULT_TRACK;
        }
        delete asset.with_audio;
      }
      if (!RENDER_MODES.includes(timeline.render)) timeline.render = "chained";
      timeline.audio_tail_s = clampTail(timeline.audio_tail_s);
      for (const key of ["soundscape", "music"]) {
        if (typeof timeline[key] !== "string") timeline[key] = "";
      }
      if (!timeline.refined || typeof timeline.refined !== "object") timeline.refined = null;
      if (!UPSCALE_MODES.includes(timeline.upscale)) timeline.upscale = UPSCALE_MODES[0];
      timeline.sample_edge = clampSampleEdge(timeline.sample_edge);
      timeline.refine_denoise = clampRefineDenoise(timeline.refine_denoise);
      timeline.face = parseFace(timeline.face);
      timeline.models = parseModels(timeline.models);
      timeline.turbo = parseTurbo(timeline.turbo);
      // No card is invented for a blob that has none: a fresh node's widget is
      // "{}" and the strip it opens is empty on purpose — see `emptyTimeline`.
      const segments = Array.isArray(parsed.segments) ? parsed.segments : [];
      timeline.segments = segments.map((raw) => {
        // A clip card holds none of a generation's machinery — no prompt, no
        // assets, no LoRAs — so it is read on its own terms rather than through
        // `parseState`, which would fill it with fields that mean nothing here.
        // The seam keys are still read below, because the seam in front of a
        // clip is a seam like any other; only which way it runs is different.
        if (raw?.kind === "clip") {
          const segment = clipSegment({
            filename: String(raw.filename ?? ""),
            duration: Number(raw.duration_s) || 0,
            width: Number(raw.width) || 0,
            height: Number(raw.height) || 0,
            // Unknown until the file is probed again. Assumed present so a
            // stored sound seam is not silently dropped on load; the card
            // re-probes and corrects it.
            hasAudio: true,
          });
          if (raw.sound === false) segment.sound = false;
          const start = Number(raw.trim?.start);
          const end = Number(raw.trim?.end);
          if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
            segment.trim = { start, end };
          }
          segment.continue = raw.continue === true;
          segment.continue_audio = raw.continue_audio === true;
          const width = Number(raw.feather);
          if (FEATHER_GRID.includes(width) && width > 1) segment.feather = width;
          return segment;
        }
        const segment = parseState(JSON.stringify(raw ?? {}));
        delete segment.version;
        // The weights are the timeline's. A segment carrying its own would be a
        // second answer to a question that has one. The turbo switch likewise.
        delete segment.models;
        delete segment.turbo;
        segment.continue = raw?.continue === true;
        segment.continue_audio = raw?.continue_audio === true;
        // Which pass this segment is generated in. A timeline saved as one pass
        // before the flags existed is every segment merged into the first,
        // which is the same timeline said the new way — and is what stops
        // `passes` from having to know about `render` at all.
        delete segment.merge;
        if (raw?.merge === true || timeline.render === "single") segment.merge = true;
        // The seam's source, as the 1-based number on the card it names.
        // `syncCanvas` prunes anything that does not point at an earlier
        // segment, so only the type is checked here.
        delete segment.continue_from;
        const from = Number(raw?.continue_from);
        if (Number.isInteger(from)) segment.continue_from = from;
        // The seam's width. Off the grid means the classic single frame,
        // which is also what absence means.
        delete segment.feather;
        const width = Number(raw?.feather);
        if (FEATHER_GRID.includes(width) && width > 1) segment.feather = width;
        return segment;
      });
      return syncCanvas(timeline);
    }
  } catch {
    // Same reasoning as parseState: an unreadable blob leaves the node usable.
  }
  return emptyTimeline();
}

export function serializeTimeline(timeline) {
  return JSON.stringify({
    version: 2,
    render: timeline.render === "single" ? "single" : "chained",
    prompt: timeline.prompt ?? "",
    // Absent means the field is not emitted at all, which is not the same as
    // "N/A" — see contextir.compose — so an empty box writes nothing.
    ...(timeline.soundscape?.trim() ? { soundscape: timeline.soundscape } : {}),
    ...(timeline.music?.trim() ? { music: timeline.music } : {}),
    // Sections only: the timeline has no body of its own, and `single_payload`
    // assembles the shots into one. `serializeRefined` drops the key when there
    // is nothing in it, which is every timeline that is not a refined one-pass.
    ...serializeRefined(timeline.refined),
    aspect: timeline.aspect,
    short_edge: timeline.short_edge,
    ...(timeline.upscale !== UPSCALE_MODES[0] ? { upscale: timeline.upscale } : {}),
    ...(timeline.sample_edge !== NATIVE_SHORT_EDGE ? { sample_edge: timeline.sample_edge } : {}),
    ...(timeline.refine_denoise !== DEFAULT_REFINE_DENOISE
      ? { refine_denoise: timeline.refine_denoise } : {}),
    ...serializeFace(timeline.face),
    loras: serializeLoras(timeline.loras ?? []),
    // The reference pool. Absent when empty, so a timeline that never used one
    // round-trips exactly as it always did.
    ...(timeline.assets?.length ? { assets: serializeAssets(timeline.assets) } : {}),
    audio_tail_s: clampTail(timeline.audio_tail_s),
    // Where this node's renders land, when the blob overrides the setting. No
    // control writes it — it is the hand-edit the README documents as the only
    // way to have two nodes write to different places — so it is carried
    // through rather than understood. Dropping it here is what made editing
    // anything on the node quietly move its output back to the default folder.
    ...(timeline.output_prefix ? { output_prefix: timeline.output_prefix } : {}),
    ...serializeModels(timeline.models),
    ...serializeTurbo(timeline.turbo),
    segments: timeline.segments.map((segment, index) => {
      if (isClip(segment)) {
        return {
          kind: "clip",
          filename: segment.filename,
          duration_s: round2(segment.duration_s),
          ...(segment.width && segment.height
            ? { width: segment.width, height: segment.height } : {}),
          ...(segment.trim ? { trim: { start: round2(segment.trim.start),
                                       end: round2(segment.trim.end) } } : {}),
          // Only the deliberate choice is written: sound on is what a clip
          // comes with, so an absent key reads as it always would.
          ...(clipSound(segment) ? {} : { sound: false }),
          // The seam in front of it, which acts on the card behind it. Same
          // keys as any other seam, and never on the first card — there is
          // nothing in front of it to run into this one.
          ...(index > 0 && segment.continue ? { continue: true } : {}),
          ...(index > 0 && segment.continue_audio ? { continue_audio: true } : {}),
          ...(index > 0 && segment.continue && feather(segment) > 1
            ? { feather: feather(segment) } : {}),
        };
      }
      const out = serializeCommon(segment);
      // Which pass this segment belongs to, said as "the same one as the
      // segment before me" — so a pass survives inserting, moving and deleting
      // with no numbers to keep in step. Never on the first segment, which is
      // always a pass of its own.
      if (index > 0 && merged(segment)) out.merge = true;
      // The card's own answer about the face pass, and only when it has one:
      // absent is the third state and the default, which is to inherit.
      if (faceOverride(segment)) out.face = faceOverride(segment);
      // Absent means a hard cut, which is the default, so only continuations
      // add anything. Never on the first segment: there is nothing to continue.
      if (index > 0 && segment.continue) out.continue = true;
      if (index > 0 && segment.continue_audio) out.continue_audio = true;
      // Only on a live seam, and only when it names something other than the
      // previous segment — which is what an absent key already says.
      if ((out.continue || out.continue_audio)
          && Number.isInteger(segment.continue_from)
          && segment.continue_from >= 1 && segment.continue_from < index) {
        out.continue_from = segment.continue_from;
      }
      // The seam's width — only on a live picture seam, and only past the
      // classic single frame, which absence already says.
      if (out.continue && feather(segment) > 1) out.feather = feather(segment);
      return out;
    }),
  }, null, 2);
}

/** A copy that shares nothing with the original — for "duplicate segment". */
export function cloneSegment(segment) {
  return JSON.parse(JSON.stringify(segment));
}

/**
 * Where each shot of one pass cuts in, and what its shots add up to before
 * snapping.
 *
 * Takes the pass's own segments, because a cut time is written against the
 * generation it happens inside: shot 1 of every pass opens at 00:00, whatever
 * has played before it. Off the raw durations rather than the snapped ones,
 * mirroring `compile.group_payload` — a pass has one frame count and it is the
 * total, so there is no per-shot grid for a cut time to land on.
 */
export function cutTimes(segments) {
  const at = [];
  let total = 0;
  for (const segment of segments) {
    at.push(total);
    total += segmentSeconds(segment);
  }
  return { at, total };
}

/** A card's length. A clip's is its window's — see `clipSeconds`. Mirrors
 *  `compile._duration_seconds`. */
export const segmentSeconds = (segment) =>
  (isClip(segment) ? clipSeconds(segment) : Number(segment.duration_s) || 0);

/** `5` -> `"00:05.000"`. Mirrors `contextir.shot_time`, which writes the real one. */
export function shotTime(seconds) {
  const ms = Math.round(Number(seconds) * 1000);
  const pad = (n, width) => String(n).padStart(width, "0");
  return `${pad(Math.floor(ms / 60000), 2)}:${pad(Math.floor(ms / 1000) % 60, 2)}.${pad(ms % 1000, 3)}`;
}

/**
 * The frames the finished clip holds.
 *
 * One pass is one generation, so its shots are summed and snapped to the 17n+5
 * grid once — which is not the same number as snapping each of them. The passes
 * are then concatenated, which is what a strip of unmerged segments always was:
 * every one its own pass, every one snapped alone.
 */
export function timelineFrames(timeline) {
  const all = passes(timeline);
  return all.reduce((total, pass, index) => {
    const head = pass.segments[0];
    // A blended seam re-generates its inherited run at the pass's head and
    // trims it off after decode, so those frames are sampled but never
    // delivered. Only between passes: a seam inside one does not exist.
    //
    // Never on a clip: its seam flags describe the blend running *backwards*
    // into it, which is paid for by the pass in front and is subtracted there.
    // Read here as well, they would take it off the strip twice.
    const overlap = index > 0 && !isClip(head) && continues(head) && feather(head) > 1
      ? feather(head) : 0;
    // ...and the same at the far end, where a clip in front of the next pass
    // owns the blend: those frames are re-generated at *this* pass's tail.
    const after = all[index + 1]?.segments[0];
    const runs = after && isClip(after) && continues(after) && feather(after) > 1
      ? feather(after) : 0;
    // A clip is played, not sampled, so its length is its own — there is no
    // 17n+5 grid to snap it to. Mirrors `compile.timeline_frames`.
    const seconds = cutTimes(pass.segments).total;
    const own = isClip(head) ? Math.round(seconds * FPS) : framesForSeconds(seconds);
    return total + own - overlap - runs;
  }, 0);
}

/** What the finished clip will run to. */
export function timelineSeconds(timeline) {
  return secondsForFrames(timelineFrames(timeline));
}

/**
 * Why another card cannot be added, or null when it can — the string goes
 * straight into the button's tooltip.
 *
 * Asked with the card that *would* be added rather than after the fact, so a
 * control goes dead on the click that queueing would have refused instead of
 * letting the strip reach a state `timeline_payloads` throws on. The frame bound
 * is the one that will actually be met: at six seconds a card, half an hour is
 * three hundred cards against a card cap of 240, so `MAX_SEGMENTS` only ever
 * catches a blob nobody built by clicking.
 */
export function addSegmentRefusal(timeline, seconds = DEFAULT_DURATION_S) {
  if (timeline.segments.length >= MAX_SEGMENTS) {
    return t("A timeline holds at most {max} segments.", { max: MAX_SEGMENTS });
  }
  if (timelineFrames(timeline) + framesForSeconds(seconds) > MAX_TIMELINE_FRAMES) {
    return t("A timeline holds at most {minutes} minutes of finished video. "
           + "Shorten it, or split the piece across two Timeline nodes.",
             { minutes: Math.round(MAX_TIMELINE_FRAMES / (60 * FPS)) });
  }
  return null;
}

// ---- pre-stage --------------------------------------------------------------
//
// The PreStage node's blob. Mirrors compile_image.py the way this file mirrors
// compile.py and canvas.js mirrors canvas.py: the UI shows the resolved canvas
// and refuses the illegal combinations early, and compile_image.py stays
// authoritative at queue time.

export const PRESTAGE_ARCHES = ["krea2", "ideogram4", "minimax"];
export const PRESTAGE_ARCH_LABEL = {
  krea2: "Krea 2", ideogram4: "Ideogram 4", minimax: "MiniMax H3",
};

// The third architecture is not an image model, and almost nothing below
// applies to it. A still from H3 is a *video generation* whose first latent
// frame is decoded as a picture, so its request is an ordinary creator state —
// same assets, same LoRAs, same weights block, same routing — and every rule
// for it is the one already written for the video nodes. It lives in its own
// sub-block (`state.minimax.request`) and is driven by CreatorEditor.

export const PRESTAGE_STILL_ARCH = "minimax";
export const isStill = (state) => state?.arch === PRESTAGE_STILL_ARCH;

/** What the length pill offers, and what a fresh still samples. Every entry is
 *  a legal 17n+5 count; 5 is the cheapest clip H3 can be asked for and 124 is
 *  the bottom of its trained range. Mirrors compile_still.STILL_LENGTHS. */
export const PRESTAGE_STILL_LENGTHS = [5, 22, 39, 56, 90, 124];
export const PRESTAGE_STILL_FRAMES = 5;
export const PRESTAGE_STILL_INDEX = 0;
export const PRESTAGE_PROMPT_MODES = ["context-ir", "plain"];

/** Frames -> latent frames. Mirrors compile_still.latent_frames, which mirrors
 *  core: the VAE is causal on the 17k+5 <-> 5k+2 grid. */
export const stillLatentFrames = (frames) =>
  (frames <= 5 ? 2 : Math.floor((frames - 5) / 17) * 5 + 2);

/** What the H3 branch writes into the sampler row: the Creator node's own
 *  defaults, because it is the Creator's sampler. */
export const PRESTAGE_STILL_ROW = {
  steps: 20, cfg: 1.0, sampler_name: "res_multistep", scheduler: "simple",
};

export function emptyStill() {
  return {
    frames: PRESTAGE_STILL_FRAMES,
    latent_index: PRESTAGE_STILL_INDEX,
    prompt_mode: "context-ir",
    // The generation, in the Creator's own shape — because it is one.
    request: emptyState(),
  };
}

export function parseStill(raw) {
  const out = emptyStill();
  if (!raw || typeof raw !== "object") return out;
  const frames = Number(raw.frames);
  if (Number.isFinite(frames)) out.frames = framesForSeconds(Math.max(1, frames) / FPS);
  const index = Number(raw.latent_index);
  if (Number.isFinite(index)) out.latent_index = Math.round(index);
  if (PRESTAGE_PROMPT_MODES.includes(raw.prompt_mode)) out.prompt_mode = raw.prompt_mode;
  out.request = parseState(JSON.stringify(raw.request ?? {}));
  return out;
}

function serializeStill(still) {
  const out = {
    frames: still.frames,
    latent_index: still.latent_index,
    request: JSON.parse(serializeState(still.request)),
  };
  if (still.prompt_mode !== "context-ir") out.prompt_mode = still.prompt_mode;
  return out;
}

export const PRESTAGE_CANVAS_MULTIPLE = 16;
export const PRESTAGE_MIN_EDGE = 512;
export const PRESTAGE_MAX_EDGE = 2048;
export const PRESTAGE_DEFAULT_EDGE = 1024;
export const PRESTAGE_MAX_PIXELS = 2048 * 2048;
export const PRESTAGE_MIN_RATIO = 1 / 3;
export const PRESTAGE_MAX_RATIO = 3;

// Order matters: this is the order the ratio popover lists them in. Wider than
// the video envelope on purpose — a style sheet is a legitimate still.
export const PRESTAGE_ASPECTS = [
  ["16:9", 16 / 9],
  ["3:2", 3 / 2],
  ["4:3", 4 / 3],
  ["1:1", 1],
  ["3:4", 3 / 4],
  ["2:3", 2 / 3],
  ["9:16", 9 / 16],
  ["21:9", 21 / 9],
];

/** Core's Qwen-edit encoder has exactly three image slots. */
export const PRESTAGE_MAX_REFS = 3;

/** What each Krea 2 checkpoint wants from the sampler row — what the arch and
 *  turbo pills write into the widgets, mirrored from compile_image.py. */
export const PRESTAGE_KREA_RAW = { steps: 52, cfg: 3.5, sampler_name: "euler", scheduler: "simple" };
export const PRESTAGE_KREA_TURBO = { cfg: 1.0, sampler_name: "euler", scheduler: "simple" };
export const PRESTAGE_TURBO_QUALITIES = ["draft", "medium", "good"];
export const PRESTAGE_TURBO_STEPS = { draft: 4, medium: 6, good: 8 };

/** Ideogram's official preset table (V4_QUALITY_48 / V4_DEFAULT_20 /
 *  V4_TURBO_12). The presets own steps *and* the schedule shape; the widget cfg
 *  feeds the dual-model guider, 7 being the template's number. */
export const PRESTAGE_IDEOGRAM_QUALITIES = ["quality", "default", "turbo"];
export const PRESTAGE_IDEOGRAM_STEPS = { quality: 48, default: 20, turbo: 12 };
export const PRESTAGE_IDEOGRAM_ROW = { cfg: 7.0, sampler_name: "euler" };

export const PRESTAGE_DEFAULT_DENOISE = 0.65;
export const PRESTAGE_MIN_DENOISE = 0.05;

/** Which weight fields each architecture has, in popover order. Mirrors
 *  render_image.ARCH_FIELDS. */
export const PRESTAGE_FIELDS = {
  krea2: ["model", "turbo_model", "clip", "vae"],
  ideogram4: ["model", "uncond_model", "clip", "vae"],
};
export const PRESTAGE_FIELD_LABEL = {
  model: "Checkpoint",
  turbo_model: "Turbo checkpoint",
  uncond_model: "Unconditional checkpoint",
  clip: "Text encoder",
  vae: "VAE",
};
export const PRESTAGE_FIELD_HINT = {
  krea2: {
    model: "Krea 2 RAW — the undistilled base. ~52 steps at cfg 3.5, and the one to train LoRAs against.",
    turbo_model: "Krea 2 Turbo — the 8-step distillation the turbo pill swaps in. LoRAs trained on RAW apply here too.",
    clip: "Qwen3-VL 4B, loaded as CLIPLoader type 'krea2'.",
    vae: "The Qwen image VAE.",
  },
  ideogram4: {
    model: "Ideogram 4.0's conditional branch.",
    uncond_model: "The unconditional branch — Ideogram ships CFG as a second model. "
                + "Optional: without it the render runs ordinary CFG on the one checkpoint.",
    clip: "Qwen3-VL 8B, loaded as CLIPLoader type 'ideogram4'.",
    vae: "The Flux 2 VAE.",
  },
};

/** Filename hints for `guessPreStageModels`, per arch per field. */
const PRESTAGE_HINTS = {
  krea2: { model: ["krea2_raw"], turbo_model: ["krea2_turbo"], clip: ["qwen3vl_4b"], vae: ["qwen_image_vae"] },
  ideogram4: {
    model: ["ideogram4"], uncond_model: ["ideogram4_unconditional"],
    clip: ["qwen3vl_8b"], vae: ["flux2"],
  },
};

export function emptyPreStage() {
  return {
    version: 1,
    arch: "krea2",
    prompt: "",
    aspect: "16:9",
    short_edge: PRESTAGE_DEFAULT_EDGE,
    // {"filename", "denoise"} for img2img, or null.
    init: null,
    // [{handle, filename}] — style references, Krea 2 only.
    refs: [],
    loras: [],
    // The image turbo is a checkpoint swap, not a LoRA — Krea Turbo *is* a
    // distilled checkpoint — but the pill keeps the H3 contract: it saves the
    // sampler row once per throw and puts it back exactly on release.
    turbo: { on: false, quality: "good", saved: null },
    // Ideogram's speed axis: which official preset shapes the schedule.
    quality: "default",
    // The H3 branch: its own settings, and its generation in the Creator's
    // shape. Nothing above it applies to that branch — see `emptyStill`.
    minimax: emptyStill(),
    models: emptyPreStageModels(),
    // A hint for peer discovery, never authoritative — ids renumber on paste,
    // so the pre-stage pill re-derives the pairing by scan.
    peer: null,
  };
}

export function emptyPreStageModels() {
  return { krea2: {}, ideogram4: {}, dtype: "default" };
}

/** The two image architectures. The H3 branch keeps its weights inside its own
 *  request, in `models.Weights`' shape, so it is not one of these. */
export const PRESTAGE_IMAGE_ARCHES = PRESTAGE_ARCHES.filter((arch) => arch !== PRESTAGE_STILL_ARCH);

export function parsePreStage(raw) {
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      const state = { ...emptyPreStage(), ...parsed };
      if (!PRESTAGE_ARCHES.includes(state.arch)) state.arch = "krea2";
      if (typeof state.prompt !== "string") state.prompt = "";
      if (!Array.isArray(state.refs)) state.refs = [];
      state.refs = state.refs
        .filter((ref) => ref && typeof ref.filename === "string")
        .slice(0, PRESTAGE_MAX_REFS);
      if (!Array.isArray(state.loras)) state.loras = [];
      // UI-only, never serialized: the LoRA manager and `promptTriggers` walk
      // the video-state accessors (`checkpoint`, `references`), which want
      // these two fields to exist even though an image render has neither.
      state.assets = [];
      state.checkpoint = "auto";
      if (!state.init || typeof state.init !== "object" || !state.init.filename) state.init = null;
      if (state.init) {
        const denoise = Number(state.init.denoise);
        state.init.denoise = Number.isFinite(denoise)
          ? Math.min(1, Math.max(PRESTAGE_MIN_DENOISE, denoise)) : PRESTAGE_DEFAULT_DENOISE;
      }
      if (!PRESTAGE_IDEOGRAM_QUALITIES.includes(state.quality)) state.quality = "default";
      state.minimax = parseStill(state.minimax);
      const turbo = state.turbo && typeof state.turbo === "object" ? state.turbo : {};
      state.turbo = {
        on: turbo.on === true,
        quality: PRESTAGE_TURBO_QUALITIES.includes(turbo.quality) ? turbo.quality : "good",
        saved: turbo.saved && typeof turbo.saved === "object" ? { ...turbo.saved } : null,
      };
      const models = state.models && typeof state.models === "object" ? state.models : {};
      state.models = emptyPreStageModels();
      for (const arch of PRESTAGE_IMAGE_ARCHES) {
        const side = models[arch];
        if (!side || typeof side !== "object") continue;
        for (const field of PRESTAGE_FIELDS[arch]) {
          if (typeof side[field] === "string" && side[field].trim()) {
            state.models[arch][field] = side[field].trim();
          }
        }
      }
      if (MODEL_DTYPES.includes(models.dtype)) state.models.dtype = models.dtype;
      return state;
    }
  } catch {
    // Same reasoning as parseState: an unreadable blob leaves the node usable.
  }
  return emptyPreStage();
}

export function serializePreStage(state) {
  const models = {};
  for (const arch of PRESTAGE_IMAGE_ARCHES) {
    const side = {};
    for (const field of PRESTAGE_FIELDS[arch]) {
      if (state.models?.[arch]?.[field]) side[field] = state.models[arch][field];
    }
    if (Object.keys(side).length) models[arch] = side;
  }
  if (state.models?.dtype && state.models.dtype !== "default") models.dtype = state.models.dtype;
  return JSON.stringify({
    version: 1,
    arch: state.arch,
    prompt: state.prompt ?? "",
    aspect: state.aspect,
    short_edge: state.short_edge,
    ...(state.init ? { init: { filename: state.init.filename, denoise: round2(state.init.denoise) } } : {}),
    ...(state.refs.length ? { refs: state.refs.map((r) => ({ handle: r.handle, filename: r.filename })) } : {}),
    loras: serializeLoras(state.loras),
    ...(state.turbo.on || state.turbo.saved
      ? { turbo: { on: state.turbo.on, quality: state.turbo.quality,
                   ...(state.turbo.saved ? { saved: { ...state.turbo.saved } } : {}) } }
      : {}),
    ...(state.quality !== "default" ? { quality: state.quality } : {}),
    minimax: serializeStill(state.minimax),
    ...(Object.keys(models).length ? { models } : {}),
    ...(state.peer != null ? { peer: state.peer } : {}),
  }, null, 2);
}

/** Fill empty weight fields from unambiguous filename matches — the same
 *  service `guessModels` does for the video nodes, for the same first-run. */
export function guessPreStageModels(models, byFolder) {
  const lists = {
    model: byFolder?.diffusion_models ?? [], turbo_model: byFolder?.diffusion_models ?? [],
    uncond_model: byFolder?.diffusion_models ?? [],
    clip: byFolder?.text_encoders ?? [], vae: byFolder?.vae ?? [],
  };
  let changed = false;
  for (const arch of PRESTAGE_IMAGE_ARCHES) {
    for (const field of PRESTAGE_FIELDS[arch]) {
      if (models[arch][field]) continue;
      const needles = PRESTAGE_HINTS[arch][field];
      let matched = lists[field].filter((name) =>
        needles.some((needle) => name.toLowerCase().includes(needle)));
      // RAW vs Turbo vs unconditional share stems; whichever says the more
      // specific word belongs to the more specific field.
      if (field === "model" && arch === "ideogram4") {
        matched = matched.filter((name) => !name.toLowerCase().includes("unconditional"));
      }
      if (matched.length !== 1) continue;
      models[arch][field] = matched[0];
      changed = true;
    }
  }
  return changed;
}

/** The resolved image canvas, mirroring compile_image.resolve_canvas: /16 grid,
 *  2048² area cap, and the aspect taken from the init image when there is one. */
export function resolvedPreStage(state, initSize = null) {
  let ratio = PRESTAGE_ASPECTS.find(([label]) => label === state.aspect)?.[1] ?? 16 / 9;
  let fromImage = false;
  if (state.init && initSize?.width && initSize?.height) {
    ratio = initSize.width / initSize.height;
    fromImage = true;
  }
  ratio = Math.min(PRESTAGE_MAX_RATIO, Math.max(PRESTAGE_MIN_RATIO, ratio));
  const edge = Math.max(PRESTAGE_MIN_EDGE, Math.min(PRESTAGE_MAX_EDGE, Math.round(state.short_edge)));

  let width, height;
  if (ratio >= 1) { width = edge * ratio; height = edge; }
  else { width = edge; height = edge / ratio; }
  if (width * height > PRESTAGE_MAX_PIXELS) {
    const scale = Math.sqrt(PRESTAGE_MAX_PIXELS / (width * height));
    width *= scale;
    height *= scale;
  }
  // The long side is capped too — 2048 is the models' per-axis ceiling, and a
  // 3:1 sheet at a big short edge would sail past it inside the area cap.
  if (Math.max(width, height) > PRESTAGE_MAX_EDGE) {
    const scale = PRESTAGE_MAX_EDGE / Math.max(width, height);
    width *= scale;
    height *= scale;
  }
  const snap16 = (v) => Math.max(PRESTAGE_CANVAS_MULTIPLE,
    Math.floor(v / PRESTAGE_CANVAS_MULTIPLE + 0.5) * PRESTAGE_CANVAS_MULTIPLE);
  width = snap16(width);
  height = snap16(height);
  while (width * height > PRESTAGE_MAX_PIXELS && Math.max(width, height) > PRESTAGE_CANVAS_MULTIPLE) {
    if (width >= height) width -= PRESTAGE_CANVAS_MULTIPLE;
    else height -= PRESTAGE_CANVAS_MULTIPLE;
  }
  return { width, height, ratio, fromImage };
}

/** Next free ref handle: img-1, img-2, ... — the same identity scheme the video
 *  assets use, so the tag hues carry over. */
export function nextPreStageHandle(state) {
  const taken = new Set(state.refs.map((r) => r.handle));
  for (let n = 1; ; n += 1) {
    const handle = `img-${n}`;
    if (!taken.has(handle)) return handle;
  }
}

/** Which of a fresh pre-stage's weight fields are still empty, for the pill's
 *  warning — clip, vae and whichever DiT the turbo pill selects. */
export function missingPreStageModels(state) {
  const side = state.models[state.arch] ?? {};
  const dit = state.arch === "krea2" && state.turbo.on ? "turbo_model" : "model";
  return [dit, "clip", "vae"].filter((field) => !side[field]);
}

/** Which of the eight identity hues (--mmc-tag-0..7) a handle wears, everywhere
 *  it appears — asset bar, prompt chip, mention menu. Derived from the handle
 *  alone so it needs no stored state and survives reloads; handles are stable
 *  across deletions, so img-2 keeps its hue after img-1 is removed. The kind
 *  offset staggers img-1 / vid-1 / aud-1 onto different hues. */
const TAG_OFFSET = { img: 0, vid: 1, aud: 2 };
export function tagIndex(handle) {
  const match = /^([A-Za-z]+)-(\d+)$/.exec(handle || "");
  if (!match) return 0;
  return (Number(match[2]) - 1 + (TAG_OFFSET[match[1]] ?? 0)) % 8;
}

/** Next free @handle for a kind: img-1, img-2, ... Stable across deletions. */
export function nextHandle(state, kind) {
  const prefix = PREFIX[kind];
  const taken = new Set(state.assets.map((a) => a.handle));
  for (let n = 1; ; n += 1) {
    const handle = `${prefix}-${n}`;
    if (!taken.has(handle)) return handle;
  }
}

// ---- loras ------------------------------------------------------------------

const round2 = (value) => Math.round((Number(value) || 0) * 100) / 100;

/** The checkpoints an entry claims. Missing or nonsense means both. */
export function loraModes(entry) {
  const claimed = (entry.modes || []).filter((m) => CHECKPOINTS.includes(m));
  return claimed.length ? claimed : [...CHECKPOINTS];
}

export const claimsBoth = (entry) => loraModes(entry).length === CHECKPOINTS.length;

/** The checkpoint the mode implies, before any pin. */
export const derivedCheckpoint = (state) => (hasReferences(state) ? "ref2va" : "fl2va");

/** Which checkpoint this state routes to, and so which LoRAs will apply.
 *  Mirrors `compile._resolve_checkpoint`. */
export function checkpoint(state) {
  const pin = state.checkpoint;
  return !pin || pin === "auto" ? derivedCheckpoint(state) : pin;
}

/** Whether the routing is the user's choice rather than the mode's. */
export const checkpointPinned = (state) => canPinCheckpoint(state) && state.checkpoint !== "auto";

/** A pin only means anything where there is a choice to make. References are
 *  encoded *for* Ref2VA — no other weights can read the blocks — so the
 *  reference modes have none. */
export const canPinCheckpoint = (state) => derivedCheckpoint(state) === "fl2va";

/** Drop a pin the mode has moved out from under. Attaching a reference turns a
 *  frame generation into a reference one, and compile.py rejects an fl2va pin on
 *  that outright; clearing it here keeps the blob queueable. */
export function normalizeCheckpoint(state) {
  if (!canPinCheckpoint(state)) state.checkpoint = "auto";
}

/** The refiner's prose for a state, or "" when there is none in play. Mirrors
 *  `compile.refined_body` — same field, same meaning for `enabled`. */
export function refinedBody(state) {
  const refined = state?.refined;
  if (!refined || refined.enabled === false) return "";
  return (refined.body || "").trim();
}

export const findLora = (state, name) => state.loras.find((l) => l.name === name) || null;

/** Applied to the routed checkpoint on the next queue, in patch order. */
export function activeLoras(state) {
  const target = checkpoint(state);
  return state.loras.filter((entry) =>
    entry.enabled !== false && loraModes(entry).includes(target) && round2(entry.strength) !== 0);
}

/** `triggers` seeds from the sidecar's trained words, which is the only moment
 *  the sidecar is consulted — from here on the entry owns its own list, so
 *  dropping a word or adding one of your own are the same edit. */
/** `strength` is the weight a sidecar recorded — A1111's "preferred weight",
 *  Lora Manager's usage tip — which is the number whoever wrote it settled on
 *  after using the file. Absent, out of range or not a number all mean nobody
 *  recorded one, and the slider starts at `turboStrength` — 1.00 for anything
 *  that is not a distill, and the number that distill's author published for the
 *  ones that are, so engaging one from the manager lands where the switch would
 *  have put it. */
export function addLora(state, name, triggers = [], strength = null) {
  if (findLora(state, name)) return null;
  // A file with no sidecar arrives as `strength: null`, and `Number(null)` is 0
  // — a weight, and a legal one, so it has to be ruled out before the cast.
  const preferred = typeof strength === "number" ? strength : NaN;
  const entry = {
    name,
    strength: Number.isFinite(preferred) && preferred >= -1 && preferred <= 2
      ? preferred : turboStrength(name),
    enabled: true,
    modes: [...CHECKPOINTS], triggers: [...triggers],
  };
  state.loras.push(entry);
  return entry;
}

/**
 * The words compile.py will put in front of the prompt. Mirrors
 * `compile.collect_triggers` — same walk, same case-insensitive dedup — for the
 * same reason canvas.js mirrors canvas.py: the node has to show the composed
 * prompt before anything is queued. compile.py stays authoritative.
 */
export function promptTriggers(state) {
  const out = [];
  const seen = new Set();
  for (const entry of activeLoras(state)) {
    for (const raw of entry.triggers || []) {
      const word = String(raw).trim();
      if (!word || seen.has(word.toLowerCase())) continue;
      seen.add(word.toLowerCase());
      out.push(word);
    }
  }
  return out;
}

/**
 * The checkpoints a timeline's segments actually route to, in a fixed order.
 *
 * A global LoRA is patched onto every segment, and the segments need not agree:
 * a reference shot runs on Ref2VA and a text one on FL2VA in the same piece. So
 * "will this LoRA do anything" is a question about a set rather than about one
 * checkpoint, which is what the manager is handed instead of `checkpoint()`.
 */
export function timelineCheckpoints(timeline) {
  const routed = new Set(passes(timeline).map((pass) => passCheckpoint(pass.segments)));
  return CHECKPOINTS.filter((name) => routed.has(name));
}

/** The one checkpoint a pass runs on. Its shots are merged into a single
 *  request, so a reference in any of them makes the whole pass Ref2VA. */
export function passCheckpoint(segments) {
  // Supplied footage is played rather than sampled, so it routes to no
  // checkpoint at all — and a clip is never merged, so a pass holding one
  // holds nothing else. Answered before `checkpoint()`, which would ask a clip
  // card for the references it has no place to keep.
  if (segments.some(isClip)) return null;
  if (segments.length === 1) return checkpoint(segments[0]);
  if (segments.some(hasReferences)) return "ref2va";
  const pin = segments.map((s) => s.checkpoint).find((c) => c && c !== "auto");
  return pin || "fl2va";
}

/**
 * The mode a pass's merged request will compile to.
 *
 * `mode()` answers it for one segment, and a pass of one is exactly that. Past
 * one the shots are a single generation, so the question is asked of all of
 * them at once — a reference anywhere makes it REF2VA, and the keyframes are
 * the first shot's start and the last shot's end.
 */
export function passMode(segments) {
  if (segments.length === 1) return mode(segments[0]);
  if (segments.some(hasReferences)) return "REF2VA";
  const head = segments[0] ?? { assets: [] };
  const first = frameAsset(head, "first_frame");
  const last = frameAsset(segments[segments.length - 1] ?? { assets: [] }, "last_frame");
  // The pass's own start frame is the seam's, when it has one — the same rule a
  // lone continuing segment follows, asked of the shot the seam lands on.
  if (continues(head)) return last ? "FL2VA" : "I2VA";
  if (first && last) return "FL2VA";
  if (first) return "I2VA";
  if (last) return "L2VA";
  return "T2VA";
}

/**
 * Why this pass could not be generated as one, or null.
 *
 * Mirrors `compile.group_payload`'s refusals so a run merged into one pass says
 * what is wrong with it while the shots are still in front of you, rather than
 * at queue time. compile.py stays authoritative — this only has to catch the
 * structural ones, which are the ones a strip of separate segments routinely
 * has, because separate segments are allowed all of them.
 *
 * Nothing to say about a pass of one: everything below is about shots sharing a
 * generation, and a lone segment shares its with nobody.
 */
export function passProblem(timeline, pass) {
  const shots = pass.segments;
  if (shots.length < 2) return null;
  const globalPrompt = (timeline.prompt || "").trim();
  const number = (index) => pass.start + index + 1;

  for (const [index, shot] of shots.entries()) {
    // A refined shot has prose whatever its prompt box holds — the rewrite
    // replaces it at compile time — so an empty box is only empty if nothing
    // was written for it at all.
    const text = (refinedBody(shot) || shot.prompt || "").trim();
    // The global prompt opens the first shot of every pass, so it is that
    // shot's text when the box under it is empty.
    if (!text && !(index === 0 && globalPrompt)) {
      return t("Shot {shot} has no prompt. The shots of a pass are one description "
             + "with cuts in it, so an empty one leaves a cut with nothing on the far side.",
             { shot: number(index) });
    }
    if (frameAsset(shot, "first_frame") && index !== 0) {
      return t("Shot {shot} has a start frame, but this pass opens on shot {first}.",
               { shot: number(index), first: number(0) });
    }
    if (frameAsset(shot, "last_frame") && index !== shots.length - 1) {
      return t("Shot {shot} has an end frame, but this pass ends on shot {last}.",
               { shot: number(index), last: number(shots.length - 1) });
    }
  }

  const withRefs = shots.findIndex(hasReferences);
  const withFrames = shots.findIndex((s) => frameAsset(s, "first_frame") || frameAsset(s, "last_frame"));
  if (withRefs >= 0 && withFrames >= 0) {
    return t("Shot {frames} has a start/end frame and shot {refs} has references. "
           + "Those are different checkpoints and one generation runs on one of them.",
           { frames: number(withFrames), refs: number(withRefs) });
  }

  for (const [key, what] of [["checkpoint", "the checkpoint"], ["soundscape", "the soundscape"],
                             ["music", "the music"]]) {
    const seen = new Set(shots
      .map((shot) => (key === "checkpoint" ? shot.checkpoint : (shot[key] || "").trim()))
      .filter((value) => value && value !== "auto"));
    if (key !== "checkpoint" && (timeline[key] || "").trim()) seen.add((timeline[key] || "").trim());
    if (seen.size > 1) return t("The shots disagree about {what}. One pass has only one.", { what: t(what) });
  }
  return null;
}

/** The global LoRAs that will be patched onto at least one segment. */
export function activeGlobalLoras(timeline) {
  const targets = timelineCheckpoints(timeline);
  return (timeline.loras ?? []).filter((entry) =>
    entry.enabled !== false && round2(entry.strength) !== 0
    && loraModes(entry).some((mode) => targets.includes(mode)));
}

export function removeLora(state, name) {
  state.loras = state.loras.filter((entry) => entry.name !== name);
}

// ---- assets -----------------------------------------------------------------

/** Every @handle in a text, in order of first appearance. Mirrors
 *  compile.HANDLE_RE — the one shape a handle may take. */
export const HANDLE_RE = /@([A-Za-z]+-\d+)/g;

/** The handles the given texts cite, as a Set. */
function citedHandles(texts) {
  const found = new Set();
  for (const text of texts) {
    for (const match of String(text ?? "").matchAll(HANDLE_RE)) found.add(match[1]);
  }
  return found;
}

/** The texts of `state` that compile will substitute, global joins included:
 *  the global prompt rides in front of every segment, and the global audio
 *  fields are inherited by a segment that writes none of its own. `own: true`
 *  drops the global parts — for telling a segment's own citation from one the
 *  global prompt put there. */
function poolTexts(state, { own = false } = {}) {
  const global_ = (own ? null : state.globalTexts) ?? {};
  const texts = [state.prompt ?? "", global_.prompt ?? "",
                 state.soundscape || global_.soundscape || "",
                 state.music || global_.music || ""];
  if (state.refined && state.refined.enabled !== false) {
    texts.push(state.refined.body ?? "");
    for (const text of Object.values(state.refined.sections ?? {})) texts.push(text ?? "");
  }
  return texts;
}

/** The pool assets a segment's text cites, in pool order. Mirrors
 *  `compile.cited_pool`: the prompt with the global one joined in front (a
 *  citation there is a citation everywhere), the rewrite standing in for it
 *  with its sections, and the two audio fields with their inheritance — a
 *  citation anywhere in them is what injects the asset into this segment's
 *  generation at queue time. The pool rides on the segment as `state.pool`,
 *  mirrored by `syncTimeline` the way the canvas is; a lone Creator state has
 *  none. */
export function citedPool(state) {
  const pool = state.pool ?? [];
  if (!pool.length) return [];
  const found = citedHandles(poolTexts(state));
  const own = new Set(state.assets.map((a) => a.handle));
  return pool.filter((asset) => found.has(asset.handle) && !own.has(asset.handle));
}

/** The subset of `citedPool` this segment cites in its own text — what remains
 *  when the global prompt's citations are set aside. For messages that tell
 *  the user *where* to edit a mention out. */
export function citedPoolOwn(state) {
  const found = citedHandles(poolTexts(state, { own: true }));
  return citedPool(state).filter((asset) => found.has(asset.handle));
}

/** Whether the timeline's own texts cite a pool asset — the "applies to every
 *  segment" state the shelf reports as such. */
export function poolCitedGlobally(timeline, asset) {
  return citedHandles([timeline.prompt, timeline.soundscape, timeline.music])
    .has(asset.handle);
}

/** Which segments cite a pool asset, as 1-based card numbers — the shelf's
 *  "used in segments 2, 4" readout. */
export function poolCitations(timeline, asset) {
  return timeline.segments
    .map((segment, index) => (citedPool(segment).includes(asset) ? index + 1 : null))
    .filter((n) => n !== null);
}

/**
 * Where a pool asset's *file* is attached to a card in its own right — the same
 * picture, under a second handle, doing the same job one level down.
 *
 * The one way the shelf's readout is true and still reads as broken. A piece
 * reference is used by citing `@ref-2` in a card; attaching the file to the
 * card instead gives it a handle of the card's own (`@img-3`) and works
 * perfectly, so the piece copy is left uncited and the shelf says so — and from
 * the outside that is a reference plainly in use being reported as unused.
 *
 * Reported rather than repaired: both are legal, and which one was meant is the
 * user's to say. Matched on filename, which is what "the same reference" means
 * here — the handle is exactly the thing that differs.
 *
 * @returns {{segment: number, handle: string}[]} 1-based card numbers with the
 *   handle the file wears there.
 */
export function poolDoubles(timeline, asset) {
  const out = [];
  timeline.segments.forEach((segment, index) => {
    const own = (segment.assets ?? []).find((entry) => entry.filename === asset.filename);
    if (own) out.push({ segment: index + 1, handle: own.handle });
  });
  return out;
}

/** Next free pool handle: ref-1, ref-2, ... One counter across kinds — the
 *  prefix says "the piece's", not what the file is; the glossary says that. */
export function nextPoolHandle(timeline) {
  const taken = new Set((timeline.assets ?? []).map((a) => a.handle));
  for (let n = 1; ; n += 1) {
    const handle = `ref-${n}`;
    if (!taken.has(handle)) return handle;
  }
}

export const references = (state) => state.assets.filter((a) => a.role === "reference");
export const refImages = (state) => references(state).filter((a) => a.kind === "image");
// The same bucketing compile.py does: a video kept for its soundtrack alone is
// an audio reference, and never a video one.
export const soundOnly = (asset) => asset.kind === "video" && asset.track === "sound";
export const refVideos = (state) => references(state).filter((a) => a.kind === "video" && !soundOnly(a));
export const refAudios = (state) => references(state).filter((a) => a.kind === "audio" || soundOnly(a));
export const frameAsset = (state, role) => state.assets.find((a) => a.role === role) || null;

export function hasReferences(state) {
  // A cited pool reference is a reference of this generation in every way that
  // matters — the mode, the checkpoint, the pin — even though the asset lives
  // on the timeline. Mirrors what compile's injection makes true.
  return references(state).length > 0 || citedPool(state).length > 0;
}

/** A timeline segment that starts from the previous segment's last frame. */
export const continues = (state) => state.continue === true;

/** Mirrors compile.FEATHER_GRID: the seam widths the video VAE's temporal
 *  grid can encode standalone. 1 is the classic single-frame seam; more pins
 *  the source's last run as motion context, re-generated at this segment's
 *  head and trimmed off after decode. */
export const FEATHER_GRID = [1, 5, 22, 39];

/** The seam's width in frames — a valid grid value, or the classic 1. */
export function feather(segment) {
  return FEATHER_GRID.includes(segment.feather) && segment.feather > 1 ? segment.feather : 1;
}

/** The widest feather this segment's duration allows. Mirrors compile: the
 *  overlap is trimmed off after decode, so it must stay under half the clip. */
export function maxFeather(segment) {
  const frames = framesForSeconds(segment.duration_s);
  return FEATHER_GRID.filter((f) => 2 * f <= frames).pop() ?? 1;
}

/** The 1-based number of the segment the seam in front of `index` inherits
 *  from — the previous one unless a valid `continue_from` names an earlier
 *  segment. Meaningless for index 0, which has no seam. */
export function continueSource(segment, index) {
  const from = segment.continue_from;
  return Number.isInteger(from) && from >= 1 && from < index ? from : index;
}

/** Rewrite every seam source through `map` (1-based number in the old order ->
 *  the same segment's new number, or null for one that is gone), after a move,
 *  duplicate or remove changed what the numbers point at. `syncTimeline` then
 *  prunes whatever no longer points at an earlier segment. */
export function remapContinueFrom(timeline, map) {
  for (const segment of timeline.segments) {
    if (!Number.isInteger(segment.continue_from)) continue;
    const next = map(segment.continue_from);
    if (Number.isInteger(next) && next >= 1) segment.continue_from = next;
    else delete segment.continue_from;
  }
}

/** ...and one whose sound carries on from it. Not implied by the above. */
export const continuesAudio = (state) => state.continue_audio === true;

/** A frame the segment names itself — a file in a slot, not an inherited one.
 *  This is what still locks references out: an inherited frame rides as a
 *  pinned guide references can coexist with, a named file cannot. */
export function frameFile(state) {
  return !!(frameAsset(state, "first_frame") || frameAsset(state, "last_frame"));
}

export function mode(state) {
  if (hasReferences(state)) return "REF2VA";
  const first = frameAsset(state, "first_frame");
  const last = frameAsset(state, "last_frame");
  if (continues(state)) return last ? "FL2VA" : "I2VA";
  if (first && last) return "FL2VA";
  if (first) return "I2VA";
  if (last) return "L2VA";
  return "T2VA";
}

/** What each bucket currently holds. A video with its sound on occupies both a
 *  video slot and an audio one, which is the rule compile.py enforces. */
function counts(state) {
  const images = refImages(state).length;
  const videos = refVideos(state).length;
  const audios = refAudios(state).length
    + refVideos(state).filter((v) => v.track === "picture+sound").length;
  return { image: images, video: videos, audio: audios, files: images + videos + audios };
}

/** How many slots a kind has left, for the picker's "n / 9 slots filled". */
export function capacity(state, kind) {
  const used = counts(state);
  const max = { image: MAX_REF_IMAGES, video: MAX_REF_VIDEOS, audio: MAX_REF_AUDIOS }[kind];
  return { used: used[kind], max, filesLeft: MAX_REF_FILES - used.files };
}

/**
 * Why the references as they now stand would not compile, or null. The same
 * limits as `_derive_mode`, checked after a change has been applied, so a switch
 * that would fail at queue time can be handed back while it is still reversible.
 */
export function overflow(state) {
  const used = counts(state);
  if (used.image > MAX_REF_IMAGES) return t("At most {max} reference images.", { max: MAX_REF_IMAGES });
  if (used.video > MAX_REF_VIDEOS) return t("At most {max} reference videos.", { max: MAX_REF_VIDEOS });
  if (used.audio > MAX_REF_AUDIOS) {
    return t("At most {max} reference audio clips, counting video soundtracks.", { max: MAX_REF_AUDIOS });
  }
  if (used.files > MAX_REF_FILES) return t("At most {max} reference files in total.", { max: MAX_REF_FILES });
  return null;
}

/** The resolved geometry and duration shown on the pills. */
export function resolved(state, keyframeSize = null) {
  const frames = framesForSeconds(state.duration_s);
  let ratio = ASPECT_PRESETS.find(([label]) => label === state.aspect)?.[1] ?? 16 / 9;
  let fromImage = false;
  if (keyframeSize && keyframeSize.width && keyframeSize.height) {
    ratio = keyframeSize.width / keyframeSize.height;
    fromImage = true;
  }
  const [width, height] = resolveCanvas(ratio, state.short_edge);
  return { frames, seconds: secondsForFrames(frames), width, height, ratio, fromImage };
}

/**
 * Why the UI blocks an action, or null. Frames and references need different
 * checkpoints and cannot be combined in one pass, so each side locks the other
 * out rather than letting the backend reject the graph at queue time.
 */
export function blockedReason(state, action) {
  // A continuing segment no longer locks references out (or the other way
  // round): the inherited frames ride as pinned guides that payload.py places
  // on the segment's own timeline, which Ref2VA reads alongside its
  // references. Only a segment's *own* frame files still conflict with them.
  if (action === "reference" && frameFile(state)) {
    return t("Remove the start/end frame first — references use the Ref2VA checkpoint, frames use FL2VA.");
  }
  if (action === "first_frame" && continues(state)) {
    return t("This segment's start frame is an earlier segment's last frame. Turn continuation off to choose one.");
  }
  if ((action === "first_frame" || action === "last_frame") && hasReferences(state)) {
    // The reference may be a cited pool asset rather than an attached file, in
    // which case "remove" means editing the mention out — of this segment's
    // text, or of the global prompt whose join put the citation everywhere.
    if (references(state).length) {
      return t("Remove the references first — start/end frames use the FL2VA checkpoint, references use Ref2VA.");
    }
    const own = citedPoolOwn(state);
    if (own.length) {
      return t("This segment cites a piece reference ({handles}) — edit the mention out first: "
        + "start/end frames use the FL2VA checkpoint, references use Ref2VA.",
          { handles: own.map((a) => `@${a.handle}`).join(", ") });
    }
    return t("The global prompt cites {handles}, which rides into every segment — edit the "
      + "mention out of the global prompt to use start/end frames here.",
        { handles: citedPool(state).map((a) => `@${a.handle}`).join(", ") });
  }
  if (action === "continue" && frameAsset(state, "first_frame")) {
    return t("Remove this segment's start frame first — continuing would replace it with the source "
           + "segment's last frame.");
  }
  return null;
}

/**
 * Why the seam in front of a clip cannot be made live, or null.
 *
 * A different question from `blockedReason`, and asked of a different card: a
 * clip is not conditioned on anything, so what this seam does is pin the *end*
 * of the shot behind it. That makes it a keyframe generation — which a shot
 * already carrying references or its own end frame cannot be.
 */
export function clipSeamBlocked(timeline, index, action) {
  const clip = timeline.segments[index];
  const before = index > 0 ? timeline.segments[index - 1] : null;
  const n = index;   // the card behind it, 1-based, which is this card's index

  if (!before || isClip(before)) {
    return t("Two clips play one after the other, with nothing generated between them to run in.");
  }
  if (action === "continue_audio") {
    if (clip.has_audio === false) return t("This clip has no soundtrack to carry back across the cut.");
    if (!clipSound(clip)) {
      return t("This clip is playing silent. Turn its sound on to carry it back across the cut.");
    }
    return null;
  }
  if (frameAsset(before, "last_frame")) {
    return t("Segment {n} has its own end frame. Remove it to end on this clip instead.", { n });
  }
  if (hasReferences(before)) {
    return t("Segment {n} carries references, and ending on this clip pins its last frame — "
           + "those are different checkpoints (Ref2VA vs FL2VA). Remove the references, "
           + "or keep this a hard cut.", { n });
  }
  return null;
}

/** The widest blend the segment behind a clip can afford. The overlap is
 *  re-generated at that segment's tail and trimmed off it, so it comes out of
 *  that card's length and not the clip's. */
export function maxClipFeather(timeline, index) {
  const before = index > 0 ? timeline.segments[index - 1] : null;
  if (!before || isClip(before)) return 1;
  return maxFeather(before);
}
