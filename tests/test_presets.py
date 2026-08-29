"""A preset put back is the setup it was taken from.

Two questions, and neither has a Python half to mirror — presets live entirely on
the near side of the queue, which is the one nice thing about the feature.

**Round trip.** Capture a piece, apply every section to a node that has nothing
in common with it, serialise: the blob has to come back identical to the one that
was captured. That is the whole promise, and it is the one a hand-written
per-section apply gets wrong quietly — a field nobody thought to carry reads as
"the preset did not set that", which is indistinguishable from "the preset set it
to the default" right up until somebody's two-pass render comes out at 720.

The sampler row is checked with it, because it is not in the blob and a preset
that dropped it would still pass a blob comparison.

**Cross-scope.** A preset of one kind applied to a node of another lands exactly
the sections that can cross and refuses the rest *with a reason*. The refusals
are the interesting half: a section that cannot cross must be visible and
explained rather than missing.

    python3 tests/test_presets.py

Skips itself if node is not installed. Shares the stub tree with
`test_js_bodies.py`, minus the DOM — nothing here renders anything.
"""

import json
import os
import shutil
import subprocess
import sys

import layout
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if shutil.which("node") is None:
    print("skipped: node is not installed")
    sys.exit(0)

# `presets.js` reaches ComfyUI's api for the userdata calls and `i18n.js` reaches
# the setting store for the locale. Neither is exercised here — capture and apply
# are pure — so the stubs only have to exist.
STUBS = {
    "app.js": "export const app = { registerExtension() {}, extensionManager: null };",
    "api.js": """
const store = new Map();
globalThis.__userdata = store;
export const api = {
  apiURL: (u) => u,
  async fetchApi(url) {
    // The family catalog, written beside this stub — manifest.js loads it at
    // import, the same way the real route serves it.
    if (String(url).startsWith("/continuity/families")) {
      const body = (await import("node:fs")).readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  },
  async getUserData(file) {
    return store.has(file)
      ? { status: 200, json: async () => JSON.parse(store.get(file)) }
      : { status: 404, json: async () => null };
  },
  async storeUserData(file, value) { store.set(file, JSON.stringify(value)); return { status: 200 }; },
  async deleteUserData(file) { store.delete(file); return { status: 204 }; },
};
""",
    "widgets.js": "export const ComfyWidgets = {};",
}

CHECK = r"""
const S = await import("./web/creator/state.js");
const P = await import("./web/creator/presets.js");

const out = { errors: [] };

/** A stand-in for the node's sampler widgets: the same {value, set} pair
 *  `sampling.widgetIO` hands the row, over a plain object. */
function fakeIO(initial = {}) {
  const values = { ...initial };
  return {
    values,
    value: (name, fallback) => (name in values ? values[name] : fallback),
    set: (name, value) => { values[name] = value; },
  };
}

// Every field H3 declares, because the list a preset carries is derived from
// exactly that. It was written down instead, and the three at the end are what
// that cost: `attention`, `chunk_ffn` and `fp16_accumulation` arrived after the
// list was written and no preset ever kept them.
const ROW = {
  steps: 7, cfg: 2.5, sampler_name: "euler", scheduler: "beta",
  shift_video: 6, shift_audio: 4, block_cache: "fast",
  spectrum: true, spectrum_blend: 0.75,
  attention: "sage", chunk_ffn: true, fp16_accumulation: true,
  // Not a preset's business, and the check below proves it is not carried.
  seed: 4471,
};
const ROW_FIELDS = Object.keys(ROW).filter((name) => name !== "seed");

// A piece with something in every section, so nothing can pass by being empty.
const SOURCE = JSON.stringify({
  version: 2,
  render: "chained",
  prompt: "the standing description",
  soundscape: "wind over stone",
  music: "low strings",
  aspect: "9:16",
  short_edge: 480,
  upscale: "direct",
  sample_edge: 640,
  refine_denoise: 0.7,
  audio_tail_s: 2.5,
  loras: [{ name: "turbo/lightx2v.safetensors", strength: 0.6 }],
  assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "plate.png" }],
  models: { fl2va: "fl2va.safetensors", clip: "clip.safetensors", vae: "vae.safetensors",
            audio_vae: "audio.safetensors", route: "ref2va", dtype: "fp8_e4m3fn" },
  turbo: { lora: "turbo/lightx2v.safetensors", quality: "draft", on: true,
           saved: { steps: 20, sampler_name: "res_multistep", scheduler: "simple",
                    shift_video: 12, shift_audio: 3 } },
  segments: [
    { prompt: "shot one @ref-1", assets: [], loras: [], duration_s: 5, checkpoint: "ref2va" },
    { prompt: "shot two", assets: [], loras: [], duration_s: 7, merge: true },
    { prompt: "shot three", assets: [
        { handle: "img-1", kind: "image", role: "first_frame", filename: "open.png" }],
      loras: [], duration_s: 9, continue: true, continue_audio: true, feather: 22 },
  ],
});

// ---- round trip -------------------------------------------------------------

try {
  const source = S.parseTimeline(SOURCE);
  S.syncTimeline(source);
  const io = fakeIO(ROW);
  const body = P.capturePiece(source, io);
  const captured = S.serializeTimeline(source);

  // A node with nothing in common: different canvas, different weights,
  // different strip. Every field the preset carries has to overwrite one.
  const target = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "something else entirely", aspect: "1:1", short_edge: 720,
    models: { fl2va: "other.safetensors" },
    segments: [{ prompt: "a card that should not survive", assets: [], loras: [], duration_s: 6 }],
  }));
  const targetIO = fakeIO({ steps: 20, cfg: 1, sampler_name: "res_multistep",
                            scheduler: "simple", seed: 99 });
  P.applyToPiece(body, Object.keys(body), target, targetIO);
  S.syncTimeline(target);

  out.roundTrip = {
    blob: S.serializeTimeline(target) === captured,
    // Every field the family declares, at the value it was captured at.
    row: ROW_FIELDS.every((name) => targetIO.values[name] === ROW[name]),
    // …and the seed left exactly as the target had it.
    seedUntouched: targetIO.values.seed === 99,
  };
  if (!out.roundTrip.blob) {
    out.roundTrip.got = JSON.parse(S.serializeTimeline(target));
    out.roundTrip.want = JSON.parse(captured);
  }
} catch (error) {
  out.errors.push(`round trip: ${error.stack}`);
}

// A section left out is a section left alone: applying only the look must not
// touch the prompt, the strip or anything else.
try {
  const source = S.parseTimeline(SOURCE);
  S.syncTimeline(source);
  const body = P.capturePiece(source, fakeIO(ROW));

  const target = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "keep me", aspect: "1:1", short_edge: 720, models: {},
    segments: [{ prompt: "keep me too", assets: [], loras: [], duration_s: 6 }],
  }));
  const io = fakeIO({ steps: 20 });
  P.applyToPiece(body, ["look"], target, io);
  S.syncTimeline(target);
  out.partial = {
    lookLanded: target.aspect === "9:16" && target.short_edge === 480
             && target.upscale === "direct" && target.refine_denoise === 0.7,
    promptKept: target.prompt === "keep me",
    stripKept: target.segments.length === 1 && target.segments[0].prompt === "keep me too",
    rowKept: io.values.steps === 20,
  };
} catch (error) {
  out.errors.push(`partial: ${error.stack}`);
}

// A look that never left the defaults still puts a node that did back. The blob
// omits a field at its default, so a naive merge would leave the target's.
try {
  const plain = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", models: {},
    segments: [{ prompt: "", assets: [], loras: [], duration_s: 6 }],
  }));
  S.syncTimeline(plain);
  const body = P.capturePiece(plain, fakeIO({}));
  const target = S.parseTimeline(SOURCE);
  S.syncTimeline(target);
  P.applyToPiece(body, ["look"], target, fakeIO({}));
  const fresh = S.emptyTimeline();
  out.defaults = {
    aspect: target.aspect === fresh.aspect,
    upscale: target.upscale === fresh.upscale,
    denoise: target.refine_denoise === fresh.refine_denoise,
  };
} catch (error) {
  out.errors.push(`defaults: ${error.stack}`);
}

// ---- shots ------------------------------------------------------------------

try {
  const source = S.parseTimeline(SOURCE);
  S.syncTimeline(source);
  const io = fakeIO(ROW);
  const body = P.captureShot(source, 2, io);

  const target = S.parseTimeline(SOURCE);
  S.syncTimeline(target);
  // `piece` on every call, because every call in the pack has one: the seam
  // width a preset carries is retargeted onto the target family's grid, and
  // that is a question only the piece can answer.
  P.applyToShot(body, Object.keys(body), target.segments[0], fakeIO({}), { piece: target });
  S.syncTimeline(target);
  const landed = target.segments[0];
  // Read off the serialized blob, not off the live object: what a card *is* is
  // what `serializeTimeline` writes for it, and a leftover field the serializer
  // refuses to emit is not a seam.
  const written = JSON.parse(S.serializeTimeline(target)).segments[0];
  out.shot = {
    prompt: landed.prompt === "shot three",
    duration: landed.duration_s === 9,
    // Segment 1 has nothing in front of it, so `syncTimeline` clears the seam
    // the preset carried — the normaliser doing exactly its job rather than a
    // preset writing a state the editor could not produce.
    seamPruned: written.continue === undefined && written.continue_audio === undefined
             && written.feather === undefined,
    frameCarried: (landed.assets ?? []).some((a) => a.role === "first_frame"
                                              && a.filename === "open.png"),
  };
  // …and onto a card that *does* have something in front of it, where the seam
  // is legal and has to survive.
  const second = S.parseTimeline(SOURCE);
  S.syncTimeline(second);
  P.applyToShot(body, Object.keys(body), second.segments[1], fakeIO({}), { piece: second });
  S.syncTimeline(second);
  out.shot.seamKept = second.segments[1].continue === true
                   && second.segments[1].feather === 22;
} catch (error) {
  out.errors.push(`shot: ${error.stack}`);
}

// ---- cross-scope ------------------------------------------------------------

try {
  const reasons = {};
  for (const [key, from, to, opts] of [
    ["strip", "piece", "prestage", {}],
    ["strip", "piece", "shot", {}],
    ["look", "piece", "shot", {}],
    ["weights", "piece", "shot", {}],
    ["shot", "shot", "piece", {}],
    ["weights", "piece", "prestage", { targetArch: "krea2" }],
  ]) {
    const verdict = P.crossable(key, from, to, opts);
    reasons[`${key}:${from}->${to}`] = verdict.ok ? true : verdict.why;
  }
  out.refusals = reasons;
  out.crossings = {
    // The one weights crossing that is legal: a pre-stage on the H3 branch runs
    // a creator request, under the same keys.
    weightsToH3: P.crossable("weights", "piece", "prestage", { targetArch: "minimax" }).ok,
    weightsFromH3: P.crossable("weights", "prestage", "piece", { arch: "minimax" }).ok,
    promptEverywhere: ["piece", "shot", "prestage"].every((to) =>
      P.crossable("prompt", "piece", to).ok),
    lorasEverywhere: ["piece", "shot", "prestage"].every((to) =>
      P.crossable("loras", "piece", to).ok),
  };
  // Every refusal says something. An empty reason is a disabled row with no
  // explanation on it, which is the failure mode this design set out to avoid.
  out.everyRefusalExplained = Object.values(reasons)
    .every((why) => why === true || (typeof why === "string" && why.length > 12));

  // The crossing that is not about scope at all: two pieces, two families. The
  // row and the weights are the family's — both spell `steps` and
  // `sampler_name` and mean different things by them, and no slot id is shared
  // — so those two sections refuse and everything else crosses freely.
  const across = (key) => P.crossable(key, "piece", "piece",
                                      { family: "h3", targetFamily: "ltx25" });
  out.families = {
    speed: across("speed").ok === false && !!across("speed").why,
    weights: across("weights").ok === false,
    // The reason names both of them rather than saying "different families".
    named: ["h3", "ltx25"].every((id) =>
      Object.values(across("speed").params ?? {}).includes(S.FAMILY_LABEL[id])),
    // Same family, same everything: nothing here narrows an ordinary crossing.
    same: P.crossable("speed", "piece", "piece",
                      { family: "ltx25", targetFamily: "ltx25" }).ok,
    // A card's row is the piece's, so it crosses on the same terms.
    shot: P.crossable("speed", "shot", "piece",
                      { family: "h3", targetFamily: "ltx25" }).ok === false,
    // Sections that are not the family's are untouched by any of it.
    others: ["prompt", "loras", "refs", "look"].every((key) =>
      P.crossable(key, "piece", "piece", { family: "h3", targetFamily: "ltx25" }).ok),
    // A pre-stage on the H3 branch *is* a creator request, so its weights are
    // H3's and land on an H3 piece and on no other.
    stillBranchToH3: P.crossable("weights", "prestage", "piece",
                                 { arch: "minimax", targetFamily: "h3" }).ok,
    stillBranchToLtx: P.crossable("weights", "prestage", "piece",
                                  { arch: "minimax", targetFamily: "ltx25" }).ok === false,
  };
} catch (error) {
  out.errors.push(`cross: ${error.stack}`);
}

// ---- a family's own row, kept whole -----------------------------------------
//
// The list a preset carries used to be H3's, written down. On LTX 2.5 that kept
// `steps` and `sampler_name` — the two names both rows happen to spell — and
// dropped the cfg pair, the sigma curve, the stretch and the guidance.
try {
  const source = S.parseTimeline(JSON.stringify({
    version: 2, family: "ltx25", prompt: "a red room", aspect: "16:9",
    segments: [{ prompt: "a", assets: [], loras: [], duration_s: 5 }],
  }));
  S.syncTimeline(source);
  const LTX_ROW = { steps: 8, video_cfg: 3, audio_cfg: 7, sampler_name: "euler",
                    max_shift: 2.4, base_shift: 0.9, stretch: false, terminal: 0.2,
                    stg_scale: 1, stg_blocks: "29,30", modality_scale: 3 };
  const body = P.capturePiece(source, fakeIO({ ...LTX_ROW, seed: 12 }));
  const target = S.parseTimeline(JSON.stringify({
    version: 2, family: "ltx25", prompt: "b",
    segments: [{ prompt: "c", assets: [], loras: [], duration_s: 5 }],
  }));
  const targetIO = fakeIO({});
  P.applyToPiece(body, ["speed"], target, targetIO);
  out.ltxRow = {
    family: body.speed?.family,
    whole: Object.entries(LTX_ROW).every(([name, value]) => targetIO.values[name] === value),
    // None of H3's, which this family does not have.
    noH3: !("cfg" in body.speed.row) && !("shift_video" in body.speed.row),
  };
} catch (error) {
  out.errors.push(`ltx row: ${error.stack}`);
}

// A pre-stage's init becomes a card's start frame — the direction the whole
// pre-stage/creator pairing exists for.
try {
  const pre = S.parsePreStage(JSON.stringify({
    version: 1, arch: "krea2", prompt: "a lighthouse",
    aspect: "3:2", short_edge: 1024,
    init: { filename: "plate.png", denoise: 0.55 },
    refs: [{ filename: "style.png" }],
    loras: [{ name: "krea/style.safetensors", strength: 0.8 }],
    models: { krea2: {}, ideogram4: {}, minimax: {} },
  }));
  const body = P.capturePreStage(pre, fakeIO({ steps: 52, cfg: 3.5 }));

  const target = S.parseTimeline(SOURCE);
  S.syncTimeline(target);
  const card = target.segments[0];
  P.applyToShot(body, ["prompt", "refs", "loras"], card, fakeIO({}),
                { from: "prestage", piece: target });
  S.syncTimeline(target);
  out.preToShot = {
    prompt: card.prompt === "a lighthouse",
    init: (card.assets ?? []).some((a) => a.role === "first_frame" && a.filename === "plate.png"),
    ref: (card.assets ?? []).some((a) => a.role === "reference" && a.filename === "style.png"),
    handlesUnique: new Set((card.assets ?? []).map((a) => a.handle)).size
                 === (card.assets ?? []).length,
    lora: (card.loras ?? []).length === 1,
  };
} catch (error) {
  out.errors.push(`prestage -> shot: ${error.stack}`);
}

// The H3 branch keeps its checkpoints in `minimax.request.models`, not in the
// top-level `models` block — that one is filled for the two image architectures
// only. A capture that read the wrong one looked fine and quietly carried no
// weights at all, which on apply *blanked* the target's.
try {
  const h3 = S.parsePreStage(JSON.stringify({
    version: 1, arch: "minimax", prompt: "a still",
    aspect: "16:9", short_edge: 720,
    models: { krea2: {}, ideogram4: {}, minimax: {} },
    minimax: {
      frames: 5, latent_index: 0,
      request: { prompt: "a still", assets: [], loras: [], aspect: "16:9", short_edge: 720,
                 models: { fl2va: "fl2va.safetensors", ref2va: "ref2va.safetensors",
                           clip: "clip.safetensors", vae: "vae.safetensors",
                           audio_vae: "audio.safetensors", route: "ref2va" } },
    },
  }));
  const body = P.capturePreStage(h3, fakeIO({}));

  // Onto a piece: the crossing `crossable` exists to allow.
  const piece = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", models: { fl2va: "wrong.safetensors" },
    segments: [{ prompt: "", assets: [], loras: [], duration_s: 6 }],
  }));
  P.applyToPiece(body, ["weights"], piece, fakeIO({}), { from: "prestage" });

  // …and back onto a pre-stage of its own kind.
  const back = S.parsePreStage(JSON.stringify({ version: 1, arch: "krea2" }));
  P.applyToPreStage(body, ["weights"], back, fakeIO({}), { from: "prestage" });

  out.h3Weights = {
    captured: (body.weights?.minimax?.models ?? {}).fl2va === "fl2va.safetensors",
    toPiece: piece.models.fl2va === "fl2va.safetensors"
          && piece.models.clip === "clip.safetensors"
          && piece.models.route === "ref2va",
    toPreStage: back.minimax.request.models.fl2va === "fl2va.safetensors"
             && back.minimax.request.models.audio_vae === "audio.safetensors",
    framesKept: back.minimax.frames === 5,
  };
} catch (error) {
  out.errors.push(`h3 weights: ${error.stack}`);
}

// References crossing *into* a pre-stage have to be re-handled. A ref with no
// handle draws as "@undefined" — and worse, the chip's remove button filters on
// `r.handle !== ref.handle`, so one undefined handle deletes every ref sharing
// it, which is all of them. The three-slot cap is the editor's, and a preset
// must not be able to exceed it.
try {
  const wide = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", models: {},
    segments: [{ prompt: "", loras: [], duration_s: 6, assets: [
      { handle: "img-1", kind: "image", role: "first_frame", filename: "open.png" },
      { handle: "img-2", kind: "image", role: "reference", filename: "r1.png" },
      { handle: "img-3", kind: "image", role: "reference", filename: "r2.png" },
      { handle: "img-4", kind: "image", role: "reference", filename: "r3.png" },
      { handle: "img-5", kind: "image", role: "reference", filename: "r4.png" },
      { handle: "vid-1", kind: "video", role: "reference", filename: "clip.mp4" },
    ] }],
  }));
  S.syncTimeline(wide);
  const shotBody = P.captureShot(wide, 0, fakeIO({}));
  const pre = S.parsePreStage(JSON.stringify({ version: 1, arch: "krea2" }));
  P.applyToPreStage(shotBody, ["refs"], pre, fakeIO({}), { from: "shot" });
  out.refsIntoPreStage = {
    init: pre.init?.filename === "open.png",
    capped: pre.refs.length === S.PRESTAGE_MAX_REFS,
    everyHandled: pre.refs.every((r) => typeof r.handle === "string" && r.handle.length > 0),
    handlesUnique: new Set(pre.refs.map((r) => r.handle)).size === pre.refs.length,
    // A video reference has nowhere to go on an image model.
    noVideo: pre.refs.every((r) => !r.filename.endsWith(".mp4")),
  };
} catch (error) {
  out.errors.push(`refs into prestage: ${error.stack}`);
}

// A pre-stage round trip of its own.
try {
  const pre = S.parsePreStage(JSON.stringify({
    version: 1, arch: "ideogram4", quality: "quality", prompt: "a poster",
    aspect: "3:2", short_edge: 1024, refs: [], loras: [],
    models: { krea2: {}, ideogram4: {}, minimax: {} },
  }));
  const io = fakeIO({ steps: 48, cfg: 7, sampler_name: "euler", scheduler: "simple" });
  const body = P.capturePreStage(pre, io);
  const captured = S.serializePreStage(pre);

  const target = S.parsePreStage(JSON.stringify({ version: 1, arch: "krea2", prompt: "other" }));
  const targetIO = fakeIO({ steps: 52, cfg: 3.5 });
  P.applyToPreStage(body, Object.keys(body), target, targetIO);
  out.preRoundTrip = {
    blob: S.serializePreStage(target) === captured,
    arch: target.arch === "ideogram4",
    // Ideogram 4's row is a quality, a cfg and a sampler — no steps and no
    // scheduler at all. So the cfg crosses and the step count does not: the
    // target keeps its own 52, because a preset off this architecture has no
    // opinion about a control this architecture does not have.
    row: targetIO.values.cfg === 7 && targetIO.values.steps === 52,
  };
  if (!out.preRoundTrip.blob) {
    out.preRoundTrip.got = JSON.parse(S.serializePreStage(target));
    out.preRoundTrip.want = JSON.parse(captured);
  }
} catch (error) {
  out.errors.push(`prestage round trip: ${error.stack}`);
}

// ---- the card ---------------------------------------------------------------

try {
  const source = S.parseTimeline(SOURCE);
  S.syncTimeline(source);
  const body = P.capturePiece(source, fakeIO(ROW));
  const card = P.describe(body, "piece");
  out.card = {
    // Shots two and three of the source share a pass (`merge: true` on the
    // second), so three cards draw as two casings.
    passes: card.lane.runs.length,
    blocks: card.lane.runs.reduce((n, run) => n + run.blocks.length, 0),
    // Real durations, not equal shares: the whole point of the lane.
    seconds: card.lane.runs.flatMap((run) => run.blocks.map((b) => b.seconds)),
    shots: card.facts.shots,
    total: card.facts.seconds,
    // Card 1 cites @ref-1 from the pool, card 3 has its own start frame, card 2
    // has neither and draws flat.
    frames: card.frames.map((f) => [f.at, f.path]),
  };
  // With a cover the lane is a ruler and draws no pictures, so the frames are
  // not collected at all.
  out.card.framesWithCover = P.describe(body, "piece", {
    cover: { path: "out.mp4 [output]", v: 1 } }).frames.length;
} catch (error) {
  out.errors.push(`card: ${error.stack}`);
}

// The cover has to record *which kind* of render it is, not just where it is:
// a still is served by core's /view as a webp, a clip only by this pack's thumb
// route. Point an <img> at an .mp4 and it renders nothing at all — which against
// the hero's near-black reads as a cover that is simply black.
try {
  out.cover = P.coverFromResult({
    isImage: false,
    saved: { filename: "H3_00021_.mp4", subfolder: "minimax/renders", type: "output" },
  });
  out.coverStill = P.coverFromResult({
    isImage: true,
    saved: { filename: "prestage_00003_.png", subfolder: "minimax/stills", type: "output" },
  });
  out.coverEmpty = P.coverFromResult(null);
  out.coverNoResult = P.coverFromResult({ isImage: false, saved: null });
} catch (error) {
  out.errors.push(`cover: ${error.stack}`);
}

// ---- a preset taken from a render -------------------------------------------
//
// The fixture is a real render's `prompt` tag, off an H3_000NN_.mp4 queued
// through the API, with only the prompt text shortened. Two things about it are
// the point rather than incidental detail:
//
//   * its blob is a **version 1** lone-shot `creator_data` — the shape a Creator
//     wrote before pieces had strips — so `asPiece` has to promote it;
//   * its inputs carry **no `shift_video`/`shift_audio`**, because the render
//     predates those two widgets. That is exactly the case that makes reading
//     the `workflow` tag's positional `widgets_values` wrong: nine values where
//     the node now declares eleven, and everything after the gap lands one slot
//     out. Read by name, an absent widget is simply absent.

const RENDER_BLOB = JSON.stringify({
  version: 1,
  prompt: "subject_definitions:\n<Subject 1> is the chapel interior in @img-1.\n",
  assets: [
    { handle: "img-1", kind: "image", role: "reference", filename: "IMG_3006.jpeg",
      ref_size: "max", takes: "scene" },
    { handle: "img-2", kind: "image", role: "reference", filename: "IMG_3059.jpeg",
      ref_size: "max", takes: "person" },
  ],
  loras: [],
  duration_s: 15,
  aspect: "3:4",
  short_edge: 512,
  models: {
    ref2va: "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    clip: "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    vae: "minimax_h3_video_vae_fp16.safetensors",
    audio_vae: "minimax_h3_audio_vae_fp32.safetensors",
    preview: "taeh3.safetensors",
  },
});

const RENDER_META = {
  workflow: { nodes: [] },
  prompt: {
    "2": {
      class_type: "MiniMaxH3Creator",
      _meta: { title: "MiniMax H3 Creator" },
      inputs: {
        creator_data: RENDER_BLOB,
        seed: 459812802937181,
        steps: 20, cfg: 1.0, sampler_name: "res_multistep", scheduler: "simple",
        block_cache: "off", spectrum: false, spectrum_blend: 0.5,
      },
    },
  },
};

const RENDER_ASSET = {
  path: "minimax/renders/H3_00028_.mp4 [output]",
  name: "H3_00028_.mp4", kind: "video", mtime: 1755100000,
};

try {
  const taken = P.captureFromRender(RENDER_META, RENDER_ASSET);
  const row = taken.data.speed?.row ?? {};
  out.fromRender = {
    scope: taken.scope,
    // The name is the render's, because that is what you recognise it by.
    name: taken.defaultName,
    // The cover comes free and comes right: the render it was taken from is by
    // definition the picture of what this setup produces.
    cover: taken.cover,
    aspect: taken.data.look?.aspect,
    shortEdge: taken.data.look?.short_edge,
    route: taken.data.weights?.ref2va,
    // The v1 blob promoted: one card, at the length the lone shot ran — and its
    // writing and its references are the *card's*, not the piece's, because on a
    // lone generation that is whose they were. `asPiece` decides this, and the
    // preset takes its word for it rather than having a second opinion.
    shots: taken.data.strip?.segments?.length,
    seconds: taken.data.strip?.segments?.[0]?.duration_s,
    pool: (taken.data.refs ?? []).map((ref) => ref.handle),
    cardRefs: (taken.data.strip?.segments?.[0]?.assets ?? []).map((ref) => ref.handle),
    pieceText: (taken.data.prompt?.prompt ?? "").length,
    cardCites: (taken.data.strip?.segments?.[0]?.prompt ?? "").includes("@img-1"),
    steps: row.steps,
    sampler: row.sampler_name,
    // Absent in the file and therefore absent here — not the next value along.
    shiftVideo: "shift_video" in row,
    // The one field a preset never carries, and it was right there in the tag.
    seed: "seed" in row,
  };

  // And the whole point: what came out of the file goes onto a node and is the
  // piece the file was rendered from.
  const target = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "nothing in common", aspect: "1:1", models: {},
    segments: [{ prompt: "not this either", assets: [], loras: [], duration_s: 6 }],
  }));
  const targetIO = fakeIO({ steps: 4, cfg: 9, seed: 99 });
  P.applyToPiece(taken.data, Object.keys(taken.data), target, targetIO);
  S.syncTimeline(target);
  const want = S.parseTimeline(RENDER_BLOB);
  S.syncTimeline(want);
  out.fromRender.blob = S.serializeTimeline(target) === S.serializeTimeline(want);
  if (!out.fromRender.blob) {
    out.fromRender.got = JSON.parse(S.serializeTimeline(target));
    out.fromRender.want = JSON.parse(S.serializeTimeline(want));
  }
  out.fromRender.rowLanded = targetIO.values.steps === 20
                          && targetIO.values.sampler_name === "res_multistep";
  out.fromRender.seedUntouched = targetIO.values.seed === 99;
} catch (error) {
  out.errors.push(`fromRender: ${error.stack}`);
}

// Which node, when a workflow holds more than one that could have made it.
try {
  const creator = RENDER_META.prompt["2"];
  const prestage = {
    class_type: "MiniMaxH3PreStage",
    inputs: {
      prestage_data: JSON.stringify({ version: 1, arch: "krea2", prompt: "a plate",
                                      aspect: "3:4", short_edge: 512, refs: [] }),
      seed: 7, steps: 28, cfg: 3.5, sampler_name: "euler", scheduler: "simple",
    },
  };
  // The ordinary pairing: a PreStage feeding a Creator. The render's own kind
  // settles it — a clip cannot have come from the still node — so this is not
  // ambiguous at all.
  const paired = { prompt: { "2": creator, "5": prestage } };
  const clip = P.captureFromRender(paired, RENDER_ASSET);
  const still = P.captureFromRender(paired, {
    path: "minimax/stills/prestage_00003_.png [output]",
    name: "prestage_00003_.png", kind: "image", mtime: 1755100001,
  });

  // Two of the same node is the case nothing in the file can settle.
  const twins = { prompt: { "9": creator, "4": creator } };
  const picked = P.captureFromRender(twins, RENDER_ASSET);

  out.whichNode = {
    clipScope: clip.scope, clipAmbiguous: clip.ambiguous,
    stillScope: still.scope, stillArch: still.data.weights?.arch,
    stillCover: still.cover?.kind,
    twinsAmbiguous: picked.ambiguous,
    // Lowest id, so the same file always gives the same preset.
    twinsNode: picked.node,
  };
} catch (error) {
  out.errors.push(`whichNode: ${error.stack}`);
}

// A render this cannot be taken from says which of the two reasons it is.
try {
  const reasons = {};
  const attempt = (key, meta, asset) => {
    try { P.captureFromRender(meta, asset ?? RENDER_ASSET); reasons[key] = null; }
    catch (error) { reasons[key] = error.message; }
  };
  attempt("bare", { prompt: null, workflow: null });
  attempt("foreign", { prompt: { "1": { class_type: "KSampler", inputs: { seed: 1 } } } });
  // A still whose workflow holds only a piece node: the file cannot have come
  // from it, and saying "no node" would be a lie about a workflow that has one.
  attempt("wrongKind", RENDER_META, { path: "x.png [output]", name: "x.png", kind: "image" });
  out.renderRefusals = reasons;
  out.everyRenderRefusalExplained = Object.values(reasons)
    .every((why) => typeof why === "string" && why.length > 24);
} catch (error) {
  out.errors.push(`renderRefusals: ${error.stack}`);
}

// ---- the cast ---------------------------------------------------------------
//
// A member is the one preset whose files are named rather than handled, and the
// one that adds to a node instead of replacing part of it. Both are checked
// here, against a piece that has never seen her pictures.

const CAST_SOURCE = JSON.stringify({
  version: 2, prompt: "@anna waits", models: {},
  assets: [
    { handle: "ref-1", kind: "image", role: "reference", filename: "anna/face.png" },
    { handle: "ref-2", kind: "audio", role: "reference", filename: "anna/voice.wav" },
    { handle: "ref-3", kind: "image", role: "reference", filename: "loft.png" },
  ],
  subjects: [{ handle: "anna", takes: "person", from: ["ref-1", "ref-9"], voice: "ref-2",
               description: "mid-thirties, dark coat", relationship: "fully_preserved" }],
  segments: [{ prompt: "@anna waits", assets: [], loras: [], duration_s: 6 }],
});

try {
  const source = S.parseTimeline(CAST_SOURCE);
  S.syncTimeline(source);
  // The scope a subject's handles can name — the pool, and a lone shot's own
  // row, which is where a piece of one shot keeps its cast's pictures. The
  // shelf that calls this in earnest resolves to exactly that pair, and a
  // one-shot source is normalized into the second half of it on load.
  const captured = P.captureSubject(source.subjects[0], S.castAssets(source));
  const member = captured.data.cast;

  // A strip that has never seen her, so every file she needs is attached by the
  // apply rather than found. Several cards can cite her, so her files go to the
  // one list all of them can reach.
  const target = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", models: {},
    assets: [{ handle: "ref-1", kind: "image", role: "reference", filename: "other.png" }],
    segments: [{ prompt: "", assets: [], loras: [], duration_s: 6 },
               { prompt: "", assets: [], loras: [], duration_s: 6 }],
  }));
  P.applyToPiece(captured.data, ["cast"], target, fakeIO({}));
  const landed = target.subjects[0];

  // …and again, into the same piece. She is somebody else now, and her files are
  // the ones already attached.
  P.applyToPiece(captured.data, ["cast"], target, fakeIO({}));
  const poolAfter = target.assets.length;

  // A piece of one shot has no pool worth the name: her pictures attach to the
  // shot, under the handles the reference row shows, like anything else picked.
  const lone = S.parseTimeline(JSON.stringify({
    version: 2, prompt: "", models: {},
    segments: [{ prompt: "", assets: [], loras: [], duration_s: 6 }],
  }));
  S.syncTimeline(lone);
  P.applyToPiece(captured.data, ["cast"], lone, fakeIO({}));

  out.cast = {
    // Named, not handled: nothing in the body may be a handle from the node she
    // was kept off.
    namesFiles: member.files.every((file) => !!file.filename && !("handle" in file)),
    // The dangling `ref-9` is dropped rather than carried into the library.
    droppedDangling: member.files.filter((file) => file.slot === "from").length === 1,
    slots: member.files.map((file) => file.slot).join(","),
    keptWords: member.description === "mid-thirties, dark coat"
            && member.relationship === "fully_preserved",
    // Her two files attached beside the one that was already there.
    attached: target.assets.length === 3,
    // On a piece of one shot they are that shot's own references instead, named
    // the way the row names them.
    onTheShot: lone.segments[0].assets.map((asset) => asset.handle).join(","),
    poolLeftAlone: (lone.assets ?? []).length === 0,
    loneSound: S.subjectProblem(
      { subjects: lone.subjects, assets: lone.segments[0].assets }, lone.subjects[0]) === "",
    handlesFresh: landed.from[0] !== "ref-1" && landed.voice !== "ref-1",
    // Everything the pack refuses a subject for: a name, files that exist, no
    // collision with a file's handle.
    sound: S.subjectProblem({ subjects: target.subjects, assets: target.assets }, landed) === "",
    // The second arrival is a second person, on the same files.
    twice: target.subjects.length === 2 && target.subjects[1].handle === "anna_2",
    reused: poolAfter === 3,
    // Adding, not replacing: somebody already cast is still cast.
    added: target.subjects[0] === landed,
    // A member is refused by a card, with a reason rather than a silence.
    refusedByShot: P.crossable("cast", "cast", "shot").ok === false
                && !!P.crossable("cast", "cast", "shot").why,
    refusedByPreStage: P.crossable("cast", "cast", "prestage").ok === false,
    takenByPiece: P.crossable("cast", "cast", "piece").ok === true,
  };
} catch (error) {
  out.errors.push(`cast: ${error.stack}`);
}

// ---- storage ----------------------------------------------------------------

try {
  const source = S.parseTimeline(SOURCE);
  S.syncTimeline(source);
  const body = P.capturePiece(source, fakeIO(ROW));
  const row = await P.savePreset({ name: "  Portal walk  ", scope: "piece", data: body });
  const listed = await P.listPresets({ force: true });
  const readBack = await P.loadBody(row);
  out.storage = {
    named: row.name === "Portal walk",
    listed: listed.length === 1 && listed[0].id === row.id,
    // The index carries the whole card, so the grid never fetches a body to draw.
    cardInIndex: !!row.lane && !!row.facts && Array.isArray(row.frames),
    bodyRoundTrips: JSON.stringify(readBack) === JSON.stringify(body),
    starred: (await P.updatePreset(row.id, { starred: true })).starred === true,
  };
  await P.deletePreset(row.id);
  out.storage.deleted = (await P.listPresets({ force: true })).length === 0;
} catch (error) {
  out.errors.push(`storage: ${error.stack}`);
}

// Kept over her, not beside her: pressing the star twice leaves one @anna.
try {
  const source = S.parseTimeline(CAST_SOURCE);
  S.syncTimeline(source);
  const first = await P.keepSubject(source.subjects[0], S.castAssets(source));
  source.subjects[0].description = "and the cardigan is hers";
  await P.keepSubject(source.subjects[0], S.castAssets(source));
  const rows = (await P.listPresets({ force: true })).filter((row) => row.scope === "cast");
  const body = await P.loadBody(rows[0]);
  out.keep = {
    one: rows.length === 1,
    named: rows[0].name === "anna",
    // The card draws her off the index alone, portrait included.
    described: rows[0].facts?.takes === "person" && rows[0].portrait === "anna/face.png",
    rewritten: body?.cast?.description === "and the cardigan is hers",
    sameRow: rows[0].id === first.id,
  };
  await P.deletePreset(rows[0].id);
} catch (error) {
  out.errors.push(`keep: ${error.stack}`);
}

// A library written when the pack was called MiniMax Creator still opens. This
// is the migration the rename owed: a preset is work somebody did by
// hand, and it lives in userdata rather than in the workflow, so a rename is the
// one thing that could quietly lose it.
try {
  const store = globalThis.__userdata;
  store.clear();
  const body = { look: { aspect: "21:9" } };
  store.set("minimax_creator.presets.json", JSON.stringify({
    version: P.PRESET_VERSION,
    presets: [{ id: "pold", name: "Portal walk", scope: "piece", updated: 1,
                sections: ["look"], facts: {}, lane: [], frames: [] }],
  }));
  store.set("minimax_creator.preset.pold.json", JSON.stringify({ data: body }));

  const rows = await P.listPresets({ force: true });
  out.legacy = {
    listed: rows.length === 1 && rows[0].id === "pold",
    bodyRead: JSON.stringify(await P.loadBody(rows[0])) === JSON.stringify(body),
  };

  // ...and the new name wins outright once it exists, rather than the two being
  // merged: a preset deleted under the new name must stay deleted.
  store.set("continuity.presets.json", JSON.stringify({
    version: P.PRESET_VERSION, presets: [],
  }));
  out.legacy.newNameWins = (await P.listPresets({ force: true })).length === 0;
  store.clear();
} catch (error) {
  out.errors.push(`legacy: ${error.stack}`);
}

// The shipped starters load, describe themselves, and name no files.
try {
  const { BUILTIN } = await import("./web/creator/presets/builtin.js");
  out.builtin = {
    count: BUILTIN.length,
    allDescribed: BUILTIN.every((row) => !!row.facts && Array.isArray(row.sections)
                                      && row.sections.length > 0),
    scopesKnown: BUILTIN.every((row) => P.SCOPES.includes(row.scope)),
    // The rule that keeps a shipped library from being red on every machine but
    // the one it was written on.
    namesNoFiles: BUILTIN.every((row) => {
      const json = JSON.stringify(row.data);
      return !/safetensors|\.png|\.mp4|\.gguf/i.test(json);
    }),
    sectionsAllowed: BUILTIN.every((row) =>
      row.sections.every((key) => P.SCOPE_SECTIONS[row.scope].includes(key))),
  };
} catch (error) {
  out.errors.push(`builtin: ${error.stack}`);
}

console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-presets-")
try:
    pack = os.path.join(work, "pack")
    shutil.copytree(os.path.join(ROOT, "web"), os.path.join(pack, "web"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, source in STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(source)
    with open(os.path.join(work, "scripts", "families.json"), "w", encoding="utf-8") as handle:
        handle.write(layout.catalog_json())
    with open(os.path.join(pack, "check.mjs"), "w", encoding="utf-8") as handle:
        handle.write(CHECK)
    result = subprocess.run(["node", os.path.join(pack, "check.mjs")],
                            capture_output=True, text=True, cwd=pack)
finally:
    shutil.rmtree(work, ignore_errors=True)

if result.returncode != 0:
    print("the preset module did not load:\n"
          + (result.stderr.strip() or result.stdout.strip()))
    sys.exit(1)

report = json.loads(result.stdout.strip().splitlines()[-1])
from harness import FAILURES, check, passed

FAILURES.extend(report["errors"])

# ---- round trip -------------------------------------------------------------

trip = report.get("roundTrip", {})
if not trip.get("blob"):
    FAILURES.append("a captured piece does not come back identical:\n"
                    f"    want {json.dumps(trip.get('want'), sort_keys=True)[:400]}\n"
                    f"    got  {json.dumps(trip.get('got'), sort_keys=True)[:400]}")
legacy = report.get("legacy") or {}
check("a library saved under the pack's old name still lists", legacy.get("listed"), True)
check("...and its bodies still open", legacy.get("bodyRead"), True)
check("...and the new name wins once it exists", legacy.get("newNameWins"), True)

check("the sampler row comes back too — it is not in the blob", trip.get("row"), True)
check("...and the seed is left where the target had it", trip.get("seedUntouched"), True)

partial = report.get("partial", {})
check("applying one section lands it", partial.get("lookLanded"), True)
check("...and leaves the prompt alone", partial.get("promptKept"), True)
check("...and the strip", partial.get("stripKept"), True)
check("...and the sampler row", partial.get("rowKept"), True)

# The trap a naive merge falls into: a blob omits a field at its default, so a
# preset of defaults has to *reset* rather than say nothing.
defaults = report.get("defaults", {})
check("a default look resets an aspect that had moved", defaults.get("aspect"), True)
check("...the upscale mode", defaults.get("upscale"), True)
check("...and the refine denoise", defaults.get("denoise"), True)

# ---- shots ------------------------------------------------------------------

shot = report.get("shot", {})
check("a shot preset carries its prompt", shot.get("prompt"), True)
check("...its duration", shot.get("duration"), True)
check("...and its start frame", shot.get("frameCarried"), True)
check("a seam that cannot exist on card 1 is pruned rather than written",
      shot.get("seamPruned"), True)
check("...and kept where there is something in front of it", shot.get("seamKept"), True)

# ---- cross-scope ------------------------------------------------------------

crossings = report.get("crossings", {})
check("a piece's weights reach a pre-stage on the H3 branch", crossings.get("weightsToH3"), True)
check("...and come back from one", crossings.get("weightsFromH3"), True)
check("a prompt crosses to everything", crossings.get("promptEverywhere"), True)
check("so do LoRAs", crossings.get("lorasEverywhere"), True)

refusals = report.get("refusals", {})
for key in ("strip:piece->prestage", "strip:piece->shot", "look:piece->shot",
            "weights:piece->shot", "shot:shot->piece", "weights:piece->prestage"):
    if refusals.get(key) is True:
        FAILURES.append(f"{key} should not be allowed to cross")
check("every refusal carries a reason the row can show",
      report.get("everyRefusalExplained"), True)

pre_to_shot = report.get("preToShot", {})
check("a pre-stage's prompt reaches a card", pre_to_shot.get("prompt"), True)
check("...its init becomes that card's start frame", pre_to_shot.get("init"), True)
check("...its style refs become references", pre_to_shot.get("ref"), True)
check("...with handles that cannot collide", pre_to_shot.get("handlesUnique"), True)
check("...and its LoRAs come along", pre_to_shot.get("lora"), True)

h3 = report.get("h3Weights", {})
check("an H3 pre-stage's checkpoints are captured from the still's own request",
      h3.get("captured"), True)
check("...and reach a piece rather than blanking its weights", h3.get("toPiece"), True)
check("...and come back onto a pre-stage", h3.get("toPreStage"), True)
check("...without losing the still's frame settings", h3.get("framesKept"), True)

into = report.get("refsIntoPreStage", {})
check("a card's start frame becomes the pre-stage's init", into.get("init"), True)
check("references crossing in are capped at the encoder's three slots",
      into.get("capped"), True)
check("...and every one of them is handled", into.get("everyHandled"), True)
check("...uniquely, so removing one chip removes one", into.get("handlesUnique"), True)
check("a video reference has nowhere to go on an image model", into.get("noVideo"), True)

pre_trip = report.get("preRoundTrip", {})
if not pre_trip.get("blob"):
    FAILURES.append("a captured pre-stage does not come back identical:\n"
                    f"    want {json.dumps(pre_trip.get('want'), sort_keys=True)[:400]}\n"
                    f"    got  {json.dumps(pre_trip.get('got'), sort_keys=True)[:400]}")
check("the architecture comes with it", pre_trip.get("arch"), True)
check("and so does its shorter row", pre_trip.get("row"), True)

families = report.get("families", {})
check("a row does not cross between model families", families.get("speed"), True)
check("...nor do the weights", families.get("weights"), True)
check("...and the reason names both families", families.get("named"), True)
check("...while the same family crosses as it always did", families.get("same"), True)
check("...a card's row is the piece's, and refuses the same way", families.get("shot"), True)
check("...and nothing else on the preset is narrowed", families.get("others"), True)
check("an H3 pre-stage's weights reach an H3 piece",
      families.get("stillBranchToH3"), True)
check("...and not one on another family", families.get("stillBranchToLtx"), True)

ltx_row = report.get("ltxRow", {})
check("a preset off an LTX 2.5 piece says whose row it holds",
      ltx_row.get("family"), "ltx25")
check("...carries the whole of it", ltx_row.get("whole"), True)
check("...and none of H3's", ltx_row.get("noH3"), True)

# ---- the card ---------------------------------------------------------------

card = report.get("card", {})
check("merged cards draw under one casing", card.get("passes"), 2)
check("...without losing a block", card.get("blocks"), 3)
check("the lane is drawn at real durations", card.get("seconds"), [5, 7, 9])
check("the facts line counts the shots", card.get("shots"), 3)
check("...and their length", card.get("total"), 21)
check("a cited pool reference pictures its card, and a start frame pictures its own",
      card.get("frames"), [[0, "plate.png"], [2, "open.png"]])
check("a card with a cover collects no block pictures", card.get("framesWithCover"), 0)

check("a finished render becomes a cover path the thumb route takes",
      (report.get("cover") or {}).get("path"), "minimax/renders/H3_00021_.mp4 [output]")
# The field the first cut of this left out, and the whole of why covers were black.
check("...marked as a clip, so it is served by the thumb route and not by /view",
      (report.get("cover") or {}).get("kind"), "video")
check("...in the picker's own row shape, so api.stillUrl needs no adapter",
      sorted((report.get("cover") or {}).keys()), ["kind", "mtime", "path"])
check("a pre-stage still is marked an image, which /view can serve",
      (report.get("coverStill") or {}).get("kind"), "image")
check("...and nothing becomes no cover", report.get("coverEmpty"), None)
check("...as does a stage that has run but saved nothing", report.get("coverNoResult"), None)

# ---- a preset taken from a render -------------------------------------------

taken = report.get("fromRender", {})
check("a render's embedded workflow is a piece preset", taken.get("scope"), "piece")
check("...named after the render, which is what you recognise it by",
      taken.get("name"), "H3_00028")
check("...carrying the render itself as its cover", taken.get("cover"), {
    "path": "minimax/renders/H3_00028_.mp4 [output]", "kind": "video", "mtime": 1755100000})
check("...its canvas", taken.get("aspect"), "3:4")
check("...at its short edge", taken.get("shortEdge"), 512)
check("...the checkpoint it was routed through",
      taken.get("route"), "minimax_h3_ref2va_pruned_int8_convrot.safetensors")
# The blob in this file is a version-1 lone shot, from before pieces had strips.
check("a v1 blob is promoted to a piece of one card", taken.get("shots"), 1)
check("...at the length that shot ran", taken.get("seconds"), 15)
check("...whose references are the card's, as they were on a lone generation",
      taken.get("cardRefs"), ["img-1", "img-2"])
check("...so the piece's pool is empty rather than holding a copy",
      taken.get("pool"), [])
check("...and the writing is the card's too", taken.get("pieceText"), 0)
check("...still citing the handles it cited", taken.get("cardCites"), True)
check("the sampler row comes off the tag by name", taken.get("steps"), 20)
check("...all of it", taken.get("sampler"), "res_multistep")
# The trap that decides which tag is read: this render predates the two flow
# shifts, so its row is two entries short of what the node declares now.
check("a widget the render predates is absent, not the next value along",
      taken.get("shiftVideo"), False)
check("and the seed is not carried, though the tag has one", taken.get("seed"), False)

if not taken.get("blob"):
    FAILURES.append("a preset taken from a render does not put its piece back:\n"
                    f"    want {json.dumps(taken.get('want'), sort_keys=True)[:400]}\n"
                    f"    got  {json.dumps(taken.get('got'), sort_keys=True)[:400]}")
check("...and the row lands with it", taken.get("rowLanded"), True)
check("...leaving the target's seed alone", taken.get("seedUntouched"), True)

which = report.get("whichNode", {})
check("a clip in a PreStage→Creator graph comes off the piece node",
      which.get("clipScope"), "piece")
check("...with nothing to disambiguate", which.get("clipAmbiguous"), 0)
check("and a still off the pre-stage node", which.get("stillScope"), "prestage")
check("...with its architecture", which.get("stillArch"), "krea2")
check("...covered by the still, served by /view", which.get("stillCover"), "image")
check("two nodes of one kind cannot be told apart, and the caller is told so",
      which.get("twinsAmbiguous"), 2)
check("...settled by the lowest id, so one file always gives one preset",
      which.get("twinsNode"), "4")

render_refusals = report.get("renderRefusals", {})
for key in ("bare", "foreign", "wrongKind"):
    if render_refusals.get(key) is None:
        FAILURES.append(f"a render that is {key} should not yield a preset")
check("every refusal says which of the reasons it is",
      report.get("everyRenderRefusalExplained"), True)

# ---- storage ----------------------------------------------------------------

storage = report.get("storage", {})
check("a saved preset keeps its trimmed name", storage.get("named"), True)
check("...and is listed back", storage.get("listed"), True)
check("the index carries the whole card, so the grid draws without a body",
      storage.get("cardInIndex"), True)
check("the body round-trips through storage", storage.get("bodyRoundTrips"), True)
check("starring writes through", storage.get("starred"), True)
check("deleting removes it", storage.get("deleted"), True)

cast = report.get("cast", {})
check("a kept cast member names her files rather than handling them",
      cast.get("namesFiles"), True)
check("...and a handle she claims that is not attached is dropped",
      cast.get("droppedDangling"), True)
check("...her slots ride with her files", cast.get("slots"), "from,voice")
check("...as do her words and her retention marker", cast.get("keptWords"), True)
check("casting her attaches her files to a piece that never had them",
      cast.get("attached"), True)
check("...under handles that are free there", cast.get("handlesFresh"), True)
check("...and she is a subject the pack will queue", cast.get("sound"), True)
check("on a piece of one shot her files are that shot's own references",
      cast.get("onTheShot"), "img-1,aud-1")
check("...and nothing is put in a pool the face does not draw",
      cast.get("poolLeftAlone"), True)
check("...she is queueable there too", cast.get("loneSound"), True)
check("casting her twice is two people, not one overwritten",
      cast.get("twice"), True)
check("...on the files already attached, not a second copy of them",
      cast.get("reused"), True)
check("...and whoever was already cast is still cast", cast.get("added"), True)
check("a card refuses her, and says why", cast.get("refusedByShot"), True)
check("...so does a pre-stage", cast.get("refusedByPreStage"), True)
check("...and a piece takes her", cast.get("takenByPiece"), True)

keep = report.get("keep", {})
check("keeping her twice leaves one of her", keep.get("one"), True)
check("...filed under the name she is written as", keep.get("named"), True)
check("...with the card's whole picture in the index", keep.get("described"), True)
check("...and the second keep is the row the first made", keep.get("sameRow"), True)
check("...rewritten rather than added to", keep.get("rewritten"), True)

builtin = report.get("builtin", {})
check("the shipped starters describe themselves", builtin.get("allDescribed"), True)
check("...under scopes the library knows", builtin.get("scopesKnown"), True)
check("...holding only sections that scope can take", builtin.get("sectionsAllowed"), True)
check("...and naming no file that is only on one machine", builtin.get("namesNoFiles"), True)

passed(f"presets round-trip, cross scopes and draw — {builtin.get('count', 0)} starters ship")
