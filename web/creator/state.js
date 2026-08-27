// The UI's model of creator_data, and the rules the backend will enforce anyway.
// Mirrors compile.py: it validates here so the user sees the problem while
// editing rather than at queue time, but compile.py stays authoritative.

import { VIDEO_RULES, featherGrid, framesForSeconds, secondsForFrames,
         matchSeconds, resolveCanvas, rulesFor } from "./canvas.js";
import { DEFAULT_STILL_ARCH, DEFAULT_VIDEO_FAMILY, STILL_ARCHES,
         UPSCALERS, VIDEO_FAMILIES, stillFamily, upscaler, videoFamily } from "./manifest.js";
import { t } from "./i18n.js";
// Where files land is not in the blob any more — it is a preference of this
// machine, in `settings.js`, so a shared workflow does not carry one person's
// folder names onto another person's disk.

// What a fresh card is worth. Mirrors `compile._duration_seconds`' default, and
// is what `addSegmentRefusal` weighs against the frame budget.
export const DEFAULT_DURATION_S = 6;

// ---- which family renders the piece -----------------------------------------
//
// A piece names its family the way it names its canvas: one field, at piece
// level, because the segments are concatenated at the end and cannot come out
// of two architectures any more than they can come out two sizes. Mirrors
// `compile.piece_family` — including its forgiveness, which is `videoFamily`'s.
//
// Every block a control reads off a family — the reference grammar, the weight
// slots, the routing table, the turbo declarations, the pre-stage's still —
// has an accessor here taking a family id, and a constant beside it bound to
// the default family under the name the readers already spell. The constants
// are what the H3-shaped UI still reads; the accessors are what a control
// becomes when it is taught to ask the piece which family it is drawing.

export { VIDEO_FAMILIES, DEFAULT_VIDEO_FAMILY };

/** The id a piece renders with, validated. An absent or unknown one is the
 *  default — see `compile.piece_family` for why an unrecognised id is a piece
 *  to draw rather than a blob to refuse.
 *
 *  **A missing *piece* is not an absent family, and does not get the default.**
 *  The two used to give the same answer, and that made a whole class of caller
 *  bug invisible: a host that reached through `mmcBody` for the wrong property
 *  — `.state` on a piece node, where the blob is `.timeline` — got `undefined`,
 *  and got a confident "MiniMax H3" back. The fullscreen bar shipped that way
 *  and drew H3 over every LTX 2.5 shot without ever looking broken. Refusing is
 *  `manifest.family`'s own rule one level up: an unknown id is a bug rather
 *  than a state, and so is a piece that is not there. */
export const pieceFamily = (piece) => {
  if (!piece) {
    throw new Error("pieceFamily: no piece. A piece node keeps its blob on "
                  + "`mmcBody.timeline`; only a pre-stage keeps one on `.state`.");
  }
  return VIDEO_FAMILIES.includes(piece.family) ? piece.family : DEFAULT_VIDEO_FAMILY;
};

/** That family's whole manifest. Refuses a missing piece for `pieceFamily`'s
 *  reason, which is the whole point of routing through it rather than reaching
 *  past it to `videoFamily(piece?.family)` as this used to. */
export const familyOf = (piece) => videoFamily(pieceFamily(piece));

/** What the family pill calls each choice, and what it says about it — the
 *  families' own strings, translation keys like any written in source. */
export const FAMILY_LABEL = Object.fromEntries(
  VIDEO_FAMILIES.map((id) => [id, videoFamily(id).label]));
export const FAMILY_DESCRIPTION = Object.fromEntries(
  VIDEO_FAMILIES.map((id) => [id, videoFamily(id).description]));

// The blocks, by family id. One line each, so that "what does a control need
// from a family" stays a list rather than a habit of reaching into `.manifest`
// from wherever the question came up.
export const referenceOf = (id) => videoFamily(id).reference;
export const weightsOf = (id) => videoFamily(id).weights;

/** What a family with one checkpoint routes between: nothing. A `routes` block
 *  describes a standing choice among a family's *routed* slots, and LTX 2.5
 *  ships one transformer, so its manifest declares none rather than a control
 *  offering a single option. "auto" is what every reader already spells for
 *  "follow the mode", and with nothing to follow it to it stays there — which
 *  is why `serializeModels` writes no `route` key for such a family at all. */
const NO_ROUTING = { options: ["auto"], default: "auto" };
export const routesOf = (id) => videoFamily(id).routes ?? NO_ROUTING;
export const modesOf = (id) => videoFamily(id).modes;
export const turboOf = (id) => videoFamily(id).capabilities.turbo;
export const stillOf = (id) => videoFamily(id).still;

/** How a family runs a second pass, or a falsy value where it has none.
 *
 *  Declared as *what kind* rather than as a flag because the two families do
 *  genuinely different things: H3 re-encodes the request at the target canvas
 *  and samples again, so its target is the resolution slider's; LTX runs a
 *  trained latent upscaler, so its target is the first pass times a factor the
 *  model fixed. A control that said "refined up to this size" for both would
 *  be right about one of them. */
export const refineOf = (id) => videoFamily(id).capabilities?.refine;

/** What the prompt refiner's template pill offers for a family, as
 *  `{name, help}` in the order the chips are drawn, "auto" first.
 *
 *  The pill used to carry one hardcoded list, which was the default family's
 *  five modes — so a piece on any other family was offered templates its
 *  refiner does not have and, worse, was rewritten into that family's prompt
 *  form. What a rewrite looks like is a statement about what a checkpoint was
 *  trained to read, so the names and the copy travel in the manifest and the
 *  server resolves a pin against the same list. */
export const templatesOf = (id) => videoFamily(id).prompt?.templates ?? [];
export const widgetsOf = (id) => videoFamily(id).widgets;

/** Whether a family declares a capability at all. Bidirectional by design: a
 *  new family may *have* things H3 lacks (LTX's duration predictor), and H3
 *  lacks things a later one has, so a capability-gated control asks rather
 *  than branching on an id. */
export const canDo = (piece, capability) =>
  Boolean(familyOf(piece).capabilities?.[capability]);

/** The whole of a capability's declaration, or null. `canDo` answers whether
 *  there is one; this is for a control that needs what it says. */
export const capabilityOf = (piece, capability) =>
  familyOf(piece).capabilities?.[capability] ?? null;

/** The chips a cutout would destroy the meaning of — there the background *is*
 *  the reference. Mirrors `cutout.KEEPS_BACKGROUND`. */
export const KEEPS_BACKGROUND = ["scene", "style"];

/** Whether cutting this picture out would leave the reference intact. -> bool.
 *
 *  Asked per picture and answered by its chip: a `scene` reference cites where
 *  something was photographed and a `style` one cites how it looks, and both
 *  live in exactly the pixels a matte throws away. Everything else — `full`
 *  included, which means "this whole picture is a reference to something" — is a
 *  subject the render wants and a background it does not. Mirrors
 *  `cutout.wanted`, which is the backend's copy of the same list. */
export const canCut = (takes) => !KEEPS_BACKGROUND.includes(takes ?? "full");

/** Whether this asset is a plate — a picture the picker made out of pictures.
 *  A plate carries its panels; an ordinary attachment is one photograph and
 *  carries none. See `creator/plate.py`. */
export const isPlate = (asset) => Boolean(asset?.panels?.length);

/** Every handle a piece has spoken for, plates' panels included.
 *
 *  Panels are citable and the cast claims them, so they are handles in exactly
 *  the sense `nextHandle` has to avoid — a plate holding `@img-2` and a loose
 *  attachment called `@img-2` is a prompt with two answers, and `compile.py`
 *  refuses the blob rather than picking one. */
export function takenHandles(state) {
  const taken = new Set();
  for (const asset of state?.assets ?? []) {
    taken.add(asset.handle);
    for (const panel of asset.panels ?? []) taken.add(panel.handle);
  }
  return taken;
}

/**
 * What the picker needs to build a plate for this piece, or null where it
 * cannot build one at all.
 *
 * The three things it cannot work out for itself: which grey the family lays
 * its panels on, whether a fresh pick starts out cut (`declare.CUTOUT_DEFAULT`
 * — on for LTX 2.5, whose panels are ingredients rather than photographs; off
 * for H3, where every piece ever saved was rendered against whole pictures),
 * and which background-removal model the weights control names. The last of
 * those comes off the capability's own `slot`, so the matte the picker takes is
 * the file the node says it uses rather than a field name guessed here.
 *
 * The canvas is the caller's, because the sheet is built at the size the shot
 * generates at.
 *
 * The model may be empty, and that is not a reason to refuse the plate: laying
 * two pictures out side by side needs no matte at all, and the missing weight
 * is only reported when the scissors are actually pressed.
 */
/** The next free `<prefix>-N`, marking it taken. Shared by the two numbering
 *  schemes a plate can land in — `img-N` on a card, `ref-N` in a pool. */
function nextIn(taken, prefix) {
  for (let n = 1; ; n += 1) {
    const handle = `${prefix}-${n}`;
    if (!taken.has(handle)) { taken.add(handle); return handle; }
  }
}

/**
 * A plate answer from the picker -> the entry a card or a pool carries.
 *
 * One asset, holding the composite's own filename and the panels it was laid
 * out from. The panels keep handles because they are what the prompt cites and
 * what the cast claims — `panel 2` on LTX 2.5, `panel 2 of <Picture 1>` on H3 —
 * and the plate keeps one of its own so there is something to hang the chip and
 * the ✕ off. See `compile._parse_panels`.
 *
 * `taken` is every handle already spoken for (`takenHandles`), and it is
 * *mutated*: the plate and its panels are numbered against one another as they
 * are issued, so no two of them can be handed the same name. The prefixes are
 * the caller's because the two hosts number differently — a card's references
 * are `img-N`, a pool's are all `ref-N`.
 *
 * `kept` is `filename -> panel` from a plate being re-picked. A picture that
 * comes back keeps its handle and its chip, so a prompt citing `@img-2` still
 * means the picture it meant and a panel does not lose what it reads as for
 * having been dragged one cell to the left.
 */
export function plateEntry(picked, taken, {
  plate = "plate", panel = "img", handle = null, kept = new Map(),
} = {}) {
  if (handle) taken.delete(handle);        // a re-pick keeps the name it had
  const entry = {
    handle: handle ?? nextIn(taken, plate),
    kind: "image",
    role: "reference",
    filename: picked.path,
    ref_size: "max",
    panels: [],
  };
  taken.add(entry.handle);
  for (const source of picked.panels ?? []) {
    const before = kept.get(source.path);
    const made = {
      handle: before && !taken.has(before.handle) ? before.handle : nextIn(taken, panel),
      filename: source.path,
      ...(source.cut ? { cut: true } : {}),
    };
    // The arrangement and the clicks ride with the panel for the same reason
    // `cut` does: they are what the composite already looks like, and what
    // re-opening the editor has to start from.
    if (source.rect) made.rect = source.rect;
    if (source.points?.length) made.points = source.points;
    if (before?.takes) made.takes = before.takes;
    taken.add(made.handle);
    entry.panels.push(made);
  }
  return entry;
}

export function plateSpec(piece, { width, height } = {}) {
  const capability = capabilityOf(piece, "cutout");
  if (!capability) return null;
  return {
    backdrop: capability.backdrop ?? 0.5,
    cut: Boolean(capability.default),
    model: piece?.models?.[capability.slot || "cutout"] ?? "",
    // The click-to-cut segmenter (SAM3), where the family names one. Empty is
    // fine: the scissors still work whole-subject, and only a click asks.
    segment: piece?.models?.[capability.segment || ""] ?? "",
    width: width || 1280,
    height: height || 704,
    // Whether the family's image references *are* one sheet (LTX 2.5). The
    // picker treats the whole image selection as the sheet where this is set;
    // elsewhere a sheet is something Connect builds out of part of it.
    sheet: sheetRefs(piece),
  };
}

/** Whether this family's image references are the panels of ONE composite
 *  sheet — LTX 2.5's `reference.sheet` declaration. Decides how image slots
 *  are counted (panels there, attachments elsewhere: the two grammars'
 *  `refuse` methods count the same ways) and how the picker behaves. */
export const sheetRefs = (piece) => Boolean(referenceOf(pieceFamily(piece)).sheet);

// The reference grammar — what may be attached, how much of it, and what a
// chip may narrow it to.
//
// **The vocabulary is shared; the counts are the piece's family's.**
//
// This used to be read wholesale off the default family, with a note saying it
// would become `referenceOf(pieceFamily(piece))` the day one family's
// declaration differed from another's. That day is here: LTX 2.5 takes no
// references at all, because a citation reaches its encoder as a bare
// `<Picture 1>` with no picture behind it, and drawing an enabled "Add image"
// on a piece the compiler will refuse is the UI lying about what the model can
// be sent.
//
// What stays global is the *vocabulary* — the takes, the tracks, the default
// sizes — because those are `compile.py`'s own constants and shared by
// construction. What moves is the counts, which are now asked of the piece.
// `test_family_select` holds the vocabulary identical across the families and
// no longer holds the counts, which is the difference this split makes real.
const REFERENCE = referenceOf(DEFAULT_VIDEO_FAMILY);

/** How many of each kind this piece's family takes, and how many files in all.
 *  Zero on a family with no reference grammar, which is what every capacity
 *  check and every attach control below reads. */
export const refCaps = (piece) => referenceOf(pieceFamily(piece)).max;

/** Whether this piece's family reads attached files at all. What the rail asks
 *  before it draws a tool that would only ever refuse. */
export const takesReferences = (piece) => refCaps(piece).files > 0;

/** Whether this piece's family reads attached files *of this kind*.
 *
 *  A second question from `takesReferences`, and it became one the day a family
 *  read some kinds and not others: LTX 2.5's reference grammar is a composite
 *  sheet of stills, so it takes nine images and no video and no sound. The rail
 *  asks per tool, so a family that cannot use a clip does not offer to attach
 *  one — the same reasoning that hides all three on a family that reads none. */
export const takesKind = (piece, kind) => (refCaps(piece)[kind] ?? 0) > 0;

const PREFIX = { image: "img", video: "vid", audio: "aud" };

/** Which of a reference video's streams are referenced. Mirrors compile.TRACKS.
 *  "sound" drops the picture, so the clip counts as an audio reference and
 *  nothing else. */
export const TRACKS = REFERENCE.tracks;
export const DEFAULT_TRACK = REFERENCE.default_track;

/** What a reference is encoded at when nobody said. Mirrors compile.DEFAULT_REF_SIZE.
 *
 *  Per kind, because "max" is a different ceiling for each: an image's is the
 *  reference pipeline's 2048 short edge, a video's is core's 768 reference
 *  canvas, which is already all a video ever gets. Audio has no size and is not
 *  in the table. */
export const DEFAULT_REF_SIZE = REFERENCE.sizes;

/** The setting in force for an asset — the stored one, or its kind's default.
 *  Read this rather than `asset.ref_size`, which an older blob simply omits. */
export const refSize = (asset) => asset.ref_size || DEFAULT_REF_SIZE[asset.kind] || "match";

/** Whether an asset has a size to choose at all. */
export const sizeable = (asset) =>
  asset.role === "reference" && DEFAULT_REF_SIZE[asset.kind] !== undefined;

/** What of a reference is actually the reference. "full" — the default — is
 *  the whole file; the others narrow it so "them from @img-1" stops dragging the
 *  picture's background, palette and pose into the video. The DiT gets the same
 *  tensor either way, so this is prose or it is nothing: the refiner's glossary
 *  reads it, and so does the prompt the compiler writes — every reference is
 *  defined and scoped in it, always. Mirrors compile.TAKES.
 *
 *  A clip takes the same four and four more, which are the roles H3's reference
 *  guide gives a video: the content takes and "motion" mine it for a
 *  `<Subject N>`, while "camera", "edit" and "continue" are the whole-video
 *  relationships `<Video N>` is reserved for. Audio takes the guide's own audio
 *  roles, whose split is copy against reference — the difference between an
 *  "audio reuse" task-type prefix and an "audio reference" one. */
export const IMAGE_TAKES = REFERENCE.takes.image;
export const VIDEO_TAKES = REFERENCE.takes.video;
export const AUDIO_TAKES = REFERENCE.takes.audio;
export const TAKES = REFERENCE.takes;

/** Which vocabulary an asset scopes with. A clip taken for its soundtrack alone
 *  is an audio reference and scopes as one: it arrives among the audio, takes an
 *  `<Audio N>` and never has its picture encoded, so the picture words would be
 *  narrowing a file that is not there. Mirrors `compile._parse_assets`. */
export const scopeKind = (asset) =>
  (asset.kind === "audio" || asset.track === "sound") ? "audio" : asset.kind;

/** The list an asset may choose from — empty for anything with nothing to
 *  narrow, which is what `takeable` reads. */
export const takeOptions = (asset) =>
  (asset.role === "reference" && TAKES[scopeKind(asset)]) || [];

/** The narrowing in force for an asset — the stored one, or the whole file. */
export const takes = (asset) =>
  (takeOptions(asset).includes(asset.takes) ? asset.takes : "full");

/** Whether an asset has a narrowing to choose at all: references only — a
 *  keyframe is bound whole by the alignment line. */
export const takeable = (asset) => takeOptions(asset).length > 0;

// ---- what a file lending itself to somebody is narrowed to -------------------
//
// A picture hung on @anna as their looks *is* a person reference, and leaving it at
// "full" says the opposite in the one place the model reads: "what the target
// video takes from it is what the picture actually shows" — its background, its
// pose, the lot. The two settings were never independent; the second one was
// just being typed twice, and the second typing was easy to forget.
//
// So hanging a file on somebody narrows the file, and the four slots map onto
// the vocabulary the file already has:
//
//   their looks    -> what they are: person, object, scene or style
//   they move    -> motion, the guide's own word for mining a clip for movement
//   their voice    -> voice, likewise for timbre
//   their place    -> edit, which is "the target video is an edited version of
//                   this one, and everything the description does not change
//                   stays" — the whole of swapping them in for its occupant
//
// **Only over the default.** A narrowing somebody chose is theirs: this fills a
// blank rather than overruling an answer, and the one moment it moves an answer
// is when *they* changes, where the old answer was this rule's own doing.

/** What the slot a file sits in says the file should be narrowed to, or null
 *  where the file has no such word to take. */
export function slotTake(subject, slot, asset) {
  const wanted = slot === "from" ? (subject.takes ?? "person")
    : slot === "motion" ? "motion"
    : slot === "voice" ? "voice"
    : slot === "replaces" ? "edit"
    : null;
  return wanted && takeOptions(asset).includes(wanted) ? wanted : null;
}

/** Narrow a file to what its slot says, unless somebody has already narrowed it
 *  themselves. `over` is the value that counts as unanswered beside "full" —
 *  the take they used to carry, when what they *is* has just been changed.
 *  Answers whether anything moved. */
export function inheritTake(subject, slot, asset, { over = null } = {}) {
  if (!asset || !takeable(asset)) return false;
  const wanted = slotTake(subject, slot, asset);
  if (!wanted) return false;
  const standing = takes(asset);
  if (standing === wanted) return false;
  if (standing !== "full" && standing !== over) return false;
  asset.takes = wanted;
  return true;
}

/** Every file behind a subject, narrowed to what its slot says. Handed the files
 *  that exist here — a handle attached somewhere else is not this surface's to
 *  change — and `over` where they have just stopped being one thing and started
 *  being another. */
export function inheritTakes(subject, assets, { over = null } = {}) {
  let moved = false;
  const find = (handle) => (assets ?? []).find((asset) => asset.handle === handle);
  for (const handle of subject.from ?? []) {
    moved = inheritTake(subject, "from", find(handle), { over }) || moved;
  }
  for (const slot of ["motion", "voice"]) {
    if (subject[slot]) moved = inheritTake(subject, slot, find(subject[slot])) || moved;
  }
  for (const handle of replacesOf(subject)) {
    moved = inheritTake(subject, "replaces", find(handle)) || moved;
  }
  return moved;
}

// The sentences that used to live here — one per scope, mirroring
// `contextir._DEFINE` — are gone. They existed to feed the band above the
// prompt, and the box shows the compiler's own finished prompt now
// (`api.compiledPrompt`), so there is nothing left for a copy of them to say
// that the real thing does not say better. The copy drifted from the compiler
// twice while it existed, which is the argument against ever keeping one.

// ---- weights ----------------------------------------------------------------
//
// Which files the node loads. These used to be sockets; they are named in the
// blob now and `models.py` builds the loaders inside the subgraph. The slots
// are the family's — served in its manifest, in the order the weights popover
// lists them — and the backend reads exactly these keys, because the manifest
// is built from the same `models.SLOTS` the loaders are.
//
// Every reading of the table is a function of the family, because the slot ids
// *are* the family's — a filename in `dit` means nothing to a family whose
// checkpoint slot is called `fl2va`. The constants under them are the default
// family's, which is what the popover and the LoRA manager still read.

const slotTable = (id, key) =>
  Object.fromEntries(weightsOf(id).filter((slot) => key in slot)
                                  .map((slot) => [slot.id, slot[key]]));

export const modelFields = (id) => weightsOf(id).map((slot) => slot.id);
export const modelLabels = (id) => slotTable(id, "title");
export const modelHints = (id) => slotTable(id, "help");

export const MODEL_FIELDS = modelFields(DEFAULT_VIDEO_FAMILY);

/** What the popover calls each slot, and what each is for — the family's own
 *  strings, translation keys like any written in source. */
export const MODEL_LABEL = modelLabels(DEFAULT_VIDEO_FAMILY);
export const MODEL_HINT = modelHints(DEFAULT_VIDEO_FAMILY);

/** UNETLoader's own list. Core's vocabulary, not a family's — applies to any
 *  checkpoint slot on any machine. */
export const MODEL_DTYPES = ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"];

/**
 * What `models.route` may hold — the family's standing instruction to run
 * everything on one checkpoint whatever the mode works out to. Worth having
 * because H3's two are one architecture trained twice; see `models.ROUTES`.
 *
 * The per-request `checkpoint` pin could already say that for one generation,
 * but it is not sticky: attaching a reference makes the pin illegal,
 * `normalizeCheckpoint` drops it, and removing the reference leaves you back on
 * auto. A route survives that, and applies to every segment of a timeline.
 */
export const routeOptions = (id) => routesOf(id).options;
const DEFAULT_ROUTE = routesOf(DEFAULT_VIDEO_FAMILY).default;

/** The next route in the cycle — the *family's* cycle, since what a route may
 *  name is its routed slots. Here rather than in the badge that cycles it, so
 *  the popover that lists them and the badge that steps through them cannot
 *  disagree about the order. */
export function nextRoute(route, family = DEFAULT_VIDEO_FAMILY) {
  const options = routeOptions(family);
  return options[(options.indexOf(route) + 1) % options.length];
}

/** Which fields a device can be pinned for: the slots that become a loader.
 *  `preview` is not one — it is a filename handed to KJNodes' node, which puts
 *  its decoder wherever the sampler is — and neither is `sam3`, which the face
 *  pass loads and releases inside its own node. Mirrors `models.DEVICE_FIELDS`. */
export const deviceFields = (id) => weightsOf(id).filter((slot) => slot.device)
                                                 .map((slot) => slot.id);
export const DEVICE_FIELDS = deviceFields(DEFAULT_VIDEO_FAMILY);

/** The slots a render can never go without whatever the mode derives: loaders
 *  that are not routed and not opt-in. Of the routed checkpoints, only the one
 *  the mode routes to is needed — `requiredModels` answers that for a given
 *  state.
 *
 *  `required` absent means required, which is the reading every family written
 *  before the key existed needs. A slot that says otherwise is a file the
 *  family can render without at all — LTX's duration head and latent upscaler
 *  are each an opt-in pass — and an empty one of those is an offer rather than
 *  the missing weights that refuse a queue. */
export const alwaysRequired = (id) => weightsOf(id)
  .filter((slot) => slot.loads && !slot.routed && slot.required !== false)
  .map((slot) => slot.id);
export const ALWAYS_REQUIRED = alwaysRequired(DEFAULT_VIDEO_FAMILY);

/** A blank weights block for one family. Family-shaped by construction: the
 *  keys are that family's slot ids, which is why switching families builds a
 *  new block rather than carrying the old one across. */
export function emptyModels(family = DEFAULT_VIDEO_FAMILY) {
  const empty = {
    dtype: "default",
    // Which checkpoint everything runs on whatever the mode derives.
    route: routesOf(family).default,
    // `{field: "cuda:1"}` for anything pinned to a card of its own, through
    // ComfyUI-MultiGPU. Empty is the normal state and means wherever ComfyUI
    // would have put it.
    devices: {},
  };
  for (const field of modelFields(family)) empty[field] = "";
  return empty;
}

/** Coerce whatever was in the blob into a full weights block. Every field may
 *  legitimately be empty: that is what a node nobody has set up yet looks like,
 *  and it is also what a workflow saved when these were sockets loads as.
 *
 *  A block stored under another family's slot ids parses to an empty one, which
 *  is the honest reading: those filenames named that family's loaders. */
export function parseModels(raw, family = DEFAULT_VIDEO_FAMILY) {
  const out = emptyModels(family);
  if (!raw || typeof raw !== "object") return out;
  for (const field of modelFields(family)) {
    if (typeof raw[field] === "string") out[field] = raw[field].trim();
  }
  if (MODEL_DTYPES.includes(raw.dtype)) out.dtype = raw.dtype;
  if (routeOptions(family).includes(raw.route)) out.route = raw.route;
  // Not validated against the machine's device list: the blob may have been
  // saved on a two-card box and opened on a one-card one, and silently dropping
  // the pin would lose the setting rather than report it. `models.loader_for`
  // refuses at queue time, naming the pack.
  if (raw.devices && typeof raw.devices === "object") {
    for (const field of deviceFields(family)) {
      if (typeof raw.devices[field] === "string" && raw.devices[field].trim()) {
        out.devices[field] = raw.devices[field].trim();
      }
    }
  }
  return out;
}

/**
 * The weights this piece picked for the families it is not on — `{family:
 * block}`, each block in that family's own slot ids.
 *
 * Set aside by `setFamily` and read back by it, so a piece that has been tried
 * on two architectures remembers both sets of files. Kept per family and not
 * merged into one block, for the reason `parseModels` gives: `vae` means a
 * different file to each of them.
 *
 * Only known video families are kept. A block for a family this install has
 * not got is dropped rather than carried, because there is no slot table to
 * read it against and nothing that could ever hand it back.
 */
export function parseSpareModels(raw) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;
  for (const family of VIDEO_FAMILIES) {
    const block = serializeModels(parseModels(raw[family], family), family).models;
    if (Object.keys(block).length) out[family] = block;
  }
  return out;
}

/** Absent when nothing is set aside, so every piece that has never switched
 *  families round-trips to the bytes it always did. */
function serializeSpareModels(raw) {
  const spare = parseSpareModels(raw);
  return Object.keys(spare).length ? { models_spare: spare } : {};
}

// ---- the upscale backend's own weights ---------------------------------------
//
// Its own block beside `models`, mirroring `redetail.Weights`. Four of its five
// slot ids are LTX 2.5's own — they are the same files from the same folders —
// which is exactly why they cannot share a block with the piece's: `vae` on an
// H3 piece is H3's video VAE, and two files cannot live under one key.

/** Which of a backend's slots a piece rendering on `family` has to fill. The
 *  backend declares the family whose weights are already these, and there the
 *  render's own loaders answer — see `redetail.needed`. */
export function upscalerFields(backend, family = DEFAULT_VIDEO_FAMILY) {
  if (!backend) return [];
  return backend.weights
    .filter((slot) => backend.shares_with !== family || !slot.loads)
    .map((slot) => slot.id);
}

export function emptyUpscalerModels() {
  return {};
}

/** Whatever was in the blob, as a block of filenames. Every backend's slots at
 *  once rather than the active one's: a piece that has been switched between
 *  backends should not lose the files it picked for the other. */
export function parseUpscalerModels(raw) {
  const out = emptyUpscalerModels();
  if (!raw || typeof raw !== "object") return out;
  for (const backend of UPSCALERS) {
    for (const slot of backend.weights) {
      if (typeof raw[slot.id] === "string" && raw[slot.id].trim()) {
        out[slot.id] = raw[slot.id].trim();
      }
    }
  }
  return out;
}

/** Absent when nothing was picked, so every piece that never touched a backend
 *  round-trips to the bytes it always did. */
function serializeUpscalerModels(models) {
  const picked = parseUpscalerModels(models);
  return Object.keys(picked).length ? { upscale_models: picked } : {};
}

/** Only what was actually picked, so a blob says nothing about fields nobody
 *  has touched — and a `dtype` left alone adds nothing at all. */
function serializeModels(models, family = DEFAULT_VIDEO_FAMILY) {
  const picked = parseModels(models, family);
  const out = {};
  for (const field of modelFields(family)) {
    if (picked[field]) out[field] = picked[field];
  }
  if (picked.dtype !== "default") out.dtype = picked.dtype;
  // Absent means "follow the mode", so the common case adds nothing.
  if (picked.route !== routesOf(family).default) out.route = picked.route;
  // Absent means "wherever ComfyUI would", so a single-GPU blob adds nothing.
  if (Object.keys(picked.devices).length) out.devices = { ...picked.devices };
  return { models: out };
}

/** One weights block as a blob writes it: only what was picked. The machine's
 *  own memory of a family's files stores exactly this shape — see
 *  `models.rememberWeights` — so the two cannot drift apart. */
export const serializedModels = (models, family = DEFAULT_VIDEO_FAMILY) =>
  serializeModels(models, family).models;

/**
 * Fill empty fields from what this machine last picked for the family, in
 * place. -> whether it changed anything.
 *
 * The same rescue `guessModels` performs and a better-informed one, so it runs
 * first: a filename guess is this pack reading a folder listing, and this is
 * the answer the user gave the last time they were asked. Only ever fills an
 * empty field — a piece that says which transformer it rendered on is not
 * corrected by a memory of a later pick — and only fields the family has.
 */
export function adoptRemembered(models, remembered, family = DEFAULT_VIDEO_FAMILY) {
  const block = remembered?.[family];
  if (!block || typeof block !== "object") return false;
  const stored = parseModels(block, family);
  let changed = false;
  for (const field of modelFields(family)) {
    if (models[field] || !stored[field]) continue;
    models[field] = stored[field];
    changed = true;
  }
  return changed;
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
export function guessModels(models, files, family = DEFAULT_VIDEO_FAMILY) {
  let changed = false;
  for (const slot of weightsOf(family)) {
    if (models[slot.id] || !slot.hints.length) continue;
    // A candidate matches on any of the slot's needles and none of its
    // exclusions — the manifest's exclusions are how a slot sharing a folder
    // with another (the two VAEs, the T=1 image decoder) rules out the files
    // that answer to the shared name but are not it.
    const matched = (files?.[slot.id] ?? []).filter((name) =>
      slot.hints.some((needle) => name.toLowerCase().includes(needle))
      && !slot.avoid.some((pattern) => new RegExp(pattern, "i").test(name)));
    if (matched.length !== 1) continue;
    models[slot.id] = matched[0];
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
export function requiredModels(checkpoints, face = false,
                               family = DEFAULT_VIDEO_FAMILY) {
  // The detector only when a pass in this render actually asks for one — a file
  // nothing loads is not a file anybody has to own. Mirrors `models.check`. And
  // only where the family has one at all: `sam3` is H3's SAM3 crop detector,
  // and a family with no face pass has no slot of that name to require.
  const detector = face && modelFields(family).includes("sam3") ? ["sam3"] : [];
  return [...alwaysRequired(family), ...detector, ...checkpoints];
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

/** Which required fields are still empty, in listing order — the family's own
 *  slot order, which is the order the popover draws the rows in. */
export function missingModels(models, required, family = DEFAULT_VIDEO_FAMILY) {
  const order = modelFields(family);
  return required.filter((field) => !models[field])
    .sort((a, b) => order.indexOf(a) - order.indexOf(b));
}

// ---- turbo ------------------------------------------------------------------
//
// The turbo block is the switch's memory, not the LoRA itself. Engaged, the
// distillation LoRA is an ordinary entry in `loras` — same stack, same manager,
// same one-click disable — and this records which file the switch reaches for,
// which quality it was left at, and what the sampler row said before it was
// thrown, so switching off puts the row back rather than guessing at defaults.
// compile.py never reads it.

// The family's declarations — step counts, the row the switch sets and where
// it resets to, how far the lead-in stepper reaches (the server refuses
// anything past it either way), and what a distill file engages at.
const TURBO = turboOf(DEFAULT_VIDEO_FAMILY);

export const TURBO_QUALITIES = Object.keys(TURBO.steps);
export const TURBO_STEPS = TURBO.steps;
export const TURBO_LEAD_MAX = TURBO.lead_max;
export const TURBO_SAMPLER = TURBO.row.sampler_name;
export const TURBO_SCHEDULER = TURBO.row.scheduler;
export const TURBO_RESET = TURBO.reset;

/** What the switch engages a file at — strength and the flow shifts its card
 *  was distilled against, guessed off the filename by the family's preset
 *  table; the manager's slider and the shift pills override it like any
 *  other value. */
export function turboPreset(name, family = DEFAULT_VIDEO_FAMILY) {
  const TURBO = turboOf(family) ?? turboOf(DEFAULT_VIDEO_FAMILY);
  const hit = TURBO.presets.find((p) => new RegExp(p.match, "i").test(name || ""));
  if (hit) return { strength: hit.strength, shift_video: hit.shift_video, shift_audio: hit.shift_audio };
  return { strength: TURBO.default_strength,
           shift_video: TURBO_RESET.shift_video, shift_audio: TURBO_RESET.shift_audio };
}

export const turboStrength = (name, family = DEFAULT_VIDEO_FAMILY) =>
  turboPreset(name, family).strength;

/** The switch's block, off. `family` decides only the quality it starts on —
 *  a family with no turbo switch never draws the pill, and the block rides its
 *  blob inert. Written per family rather than off the default's because
 *  `setFamily` resets the switch on a switch, and the default family's "medium"
 *  in another family's blob is a number from a step table it does not have. */
export function emptyTurbo(family = DEFAULT_VIDEO_FAMILY) {
  const TURBO = turboOf(family);
  return {
    // The file the switch engages, relative to models/loras. Picked in the
    // weights popover, because it is machine configuration like the files above
    // it: set once when the LoRA is downloaded, then thrown from the pill.
    lora: "",
    // The user said their checkpoint is a merged distill — turbo with no LoRA
    // at all, the switch owning only the sampler row. Remembered so the pill
    // engages directly on the next press instead of asking again.
    merged: false,
    quality: TURBO?.default_quality ?? "",
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

/** What a declared control carries in the blob, by widget type. The manifest's
 *  vocabulary is about how a value is *drawn*; this is the JSON type behind it,
 *  and it is the only thing the store needs to know. */
const FIELD_KIND = { stepper: "number", slider: "number",
                     toggle: "boolean", combo: "string", text: "string" };

const SAMPLING_FIELD_CACHE = new Map();

/** Every field this family's sampler row keeps in the blob, and what each has
 *  to be.
 *
 *  Derived from the family's own widget declarations, because a list written
 *  down here is one family's: this was H3's, and an LTX 2.5 piece lost every
 *  field of its row but `steps` on the way through — `video_cfg` and the sigma
 *  pair dropped on load and on save both, so the pills wrote a store that
 *  forgot them and the render ran the distilled defaults whatever the row said.
 *  `tests/test_sampling_mirror.py` holds each family's list against the
 *  `DEFAULTS` its own backend module resolves against. The seed is in neither:
 *  it stays a widget, for the reason `sampling.WIDGET_ONLY` gives.
 *
 *  All three groups, because the accelerators and the taste guidance are row
 *  too — they are declared apart because they are *drawn* apart, lit rather
 *  than dialled. A family that has not tried them declares none, and then it
 *  has none. `weights` and `reference` are not here: those groups describe
 *  files and attachments, which live in their own blocks of the blob.
 *
 *  The *values* are deliberately not mirrored. A default here would be a second
 *  place the row's numbers live, and the whole point of the move is that the
 *  backend resolves an absent field against its own defaults — so this says
 *  what a field is, and says nothing about what it should be. */
export function samplingFields(family = DEFAULT_VIDEO_FAMILY) {
  return rowFields(videoFamily(family));
}

/** The same, for a pre-stage's architecture. Its row is a family's row too —
 *  Krea 2 declares four controls and Ideogram 4 declares three *different*
 *  ones — and the only thing that differs is which manifest answers. */
export const stillRowFields = (arch) => rowFields(stillFamily(arch));

/** The list itself, off one manifest. Keyed on the manifest object rather than
 *  on an id, because the two callers above address a family by two different
 *  vocabularies and there is one answer per manifest either way. */
function rowFields(manifest) {
  let fields = SAMPLING_FIELD_CACHE.get(manifest);
  if (!fields) {
    fields = Object.fromEntries(manifest.widgets
      .filter((w) => w.group === "sampler" || w.group === "accel"
                     || w.group === "guidance")
      .map((w) => [w.id, FIELD_KIND[w.type]]));
    SAMPLING_FIELD_CACHE.set(manifest, fields);
  }
  return fields;
}

/** The row as stored, for the family whose row it is. Unknown keys and wrong
 *  types dropped, the rest kept as written — this is not the place that decides
 *  what a legal step count is, because a blob queued without ever being opened
 *  here never passes through it and the backend has to decide that anyway. */
export function parseSampling(raw, family = DEFAULT_VIDEO_FAMILY) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;
  for (const [name, kind] of Object.entries(samplingFields(family))) {
    const value = raw[name];
    if (value === undefined || value === null) continue;
    if (typeof value === kind) out[name] = value;
  }
  return out;
}

/** Absent until something is in it, like the turbo block above: a piece nobody
 *  has tuned says nothing about how it is sampled, and queues off the family's
 *  own defaults exactly as every piece did before the row moved. */
export function serializeSampling(sampling, family = DEFAULT_VIDEO_FAMILY) {
  const picked = parseSampling(sampling, family);
  return Object.keys(picked).length ? { sampling: picked } : {};
}

/**
 * The rows this piece dialled for the families it is not on — `{family: row}`.
 *
 * The weights' stash, for the sampler row, and for the same reason: the row is
 * the family's. Two of its fields are spelled the same on both — `steps` and
 * `sampler_name` — and mean different things, so a row carried across a switch
 * puts H3's 20 res_multistep steps on a transformer distilled to want 8 euler
 * ones, quietly, on a piece nobody touched the row of. `setFamily` sets it
 * aside instead, and hands it back on the way home.
 */
export function parseSamplingSpare(raw) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;
  for (const family of VIDEO_FAMILIES) {
    // Each stashed row read as its own family's — that is the whole point of
    // the stash, and reading LTX's aside through H3's list would empty it.
    const row = parseSampling(raw[family], family);
    if (Object.keys(row).length) out[family] = row;
  }
  return out;
}

/** Absent when nothing is set aside — every piece that never switched. */
function serializeSamplingSpare(raw) {
  const spare = parseSamplingSpare(raw);
  return Object.keys(spare).length ? { sampling_spare: spare } : {};
}

/** The family's routed slots, which is also the granularity a LoRA belongs
 *  to: every mode a checkpoint answers for runs the same weights. */
export const checkpointsOf = (id) => weightsOf(id).filter((slot) => slot.routed)
                                                  .map((slot) => slot.id);
export const CHECKPOINTS = checkpointsOf(DEFAULT_VIDEO_FAMILY);

/** What each of a family's routed checkpoints is called, and when it is used.
 *  Empty for a family that ships one transformer — which is what every reader
 *  of these should branch on rather than assuming two. */
export const checkpointLabels = (id) => slotTable(id, "name");
export const checkpointWhen = (id) => slotTable(id, "when");

/** Whether a family routes at all: two or more checkpoints to choose between.
 *  A family with one has no route pill, no per-LoRA checkpoint mode and no
 *  idle marks, because there is nothing for any of the three to say. */
export const routing = (id) => checkpointsOf(id).length > 1;
export const CHECKPOINT_LABEL = slotTable(DEFAULT_VIDEO_FAMILY, "name");
export const CHECKPOINT_WHEN = slotTable(DEFAULT_VIDEO_FAMILY, "when");

// Which checkpoint the mode implies, and what each payload shape's mode is
// called — the family's declarations, mirrored from compile.py through the
// manifest. See `derivedCheckpoint` and `mode`.
const ROUTED = routesOf(DEFAULT_VIDEO_FAMILY);
/** What `state.checkpoint` may hold: follow the mode, or pin one.
 *
 *  The default family's names, and deliberately: this is reached on parse,
 *  where a segment does not yet know whose strip it is on. Nothing downstream
 *  reads a pin the family cannot honour — `checkpoint()` answers null on a
 *  family that routes between nothing, `setFamily` deletes every pin on a
 *  switch, and `compile._resolve_checkpoint` ignores one for the same stated
 *  reason. So the worst this does is keep a string nobody asks for. */
export const CHECKPOINT_CHOICES = ["auto", ...CHECKPOINTS];
export const DEFAULT_STRENGTH = 1.0;

/** How far a LoRA's weight may go in either direction. Well past where a style
 *  LoRA is useful, because slider LoRAs are not style LoRAs — see the manager's
 *  SCALES, whose widest span this is. */
export const MAX_STRENGTH = 25;

/** Mirrors compile.UPSCALE_MODES, first_pass_edge and the refine-denoise
 *  clamp. How a piece reaches the size it is finished at, asked once: sample
 *  at the first-pass edge and refine up ("two_pass", the default), one pass at
 *  the slider's size ("direct" — past native, off-distribution), or hand the
 *  finished pass to a backend that is not the family's own ("redetail" — one
 *  pass at the native edge, then a generative x2 re-render). The first-pass
 *  edge is native unless lowered, so past native two passes happen on their
 *  own, and under it only when the user lowers the edge — a blob without the
 *  key keeps meaning what it meant.
 *
 *  "redetail" is the one whose finished size is not the slider's: it is twice
 *  what was sampled, which is also the only way any of the three reaches past
 *  the family's own edge. `redetailTarget` is what says so on the pill. */
export const UPSCALE_MODES = ["two_pass", "direct", "redetail"];
export const DEFAULT_REFINE_DENOISE = 0.5;
export const MIN_REFINE_DENOISE = 0.1;
export const MAX_REFINE_DENOISE = 0.9;

/** `rules` rather than the default family's constants: "native" is where a
 *  family's weights were trained, and the two this pack ships were trained at
 *  different sizes. Every caller has the piece, so every caller can say which. */
const clampSampleEdge = (value, rules) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return rules.nativeShortEdge;
  const snapped = Math.round(n / rules.multiple) * rules.multiple;
  return Math.min(rules.nativeShortEdge, Math.max(rules.minShortEdge, snapped));
};

/** The short edge the first of two passes samples at: the stored edge, capped
 *  by the slider — at the cap the two passes collapse into one render.
 *  Mirrors `compile.first_pass_edge`, which takes the family for this reason. */
export const sampleEdge = (target) =>
  Math.min(clampSampleEdge(target.sample_edge, rulesFor(pieceFamily(target))),
           target.short_edge);

/** Whether this canvas owner renders in two passes. `target` is anything with
 *  `short_edge`, `sample_edge` and `upscale` — a state or a timeline.
 *
 *  A backend mode is not two passes: "redetail" samples once and then re-renders
 *  what came out, which is a different thing from refining a latent up. */
export const twoPass = (target) =>
  sampleEdge(target) < target.short_edge
  && target.upscale !== "direct" && !upscalerOf(target);

/** The backend this piece finishes through, or undefined where the mode is a
 *  pass the family makes on its own. Mirrors what `compile_request` does with
 *  the same field: `two_pass` and `direct` name no backend. */
export const upscalerOf = (target) => upscaler(target?.upscale);

/** What a piece finishing through a backend is finished at: the canvas as
 *  sampled, times the backend's own factor. `null` where no backend is in play.
 *
 *  The slider is the *sampled* size under a backend and the finished size under
 *  the other two, which is the one thing the pill has to say out loud — see
 *  `pills.js`. Mirrors `redetail.target`: doubling a canvas already on the /32
 *  grid is what puts it on the /64 grid the guide's dilation needs, which is why
 *  the factor is the model's and not a number anyone gets to set.
 *
 *  `backend` is passed explicitly by the one caller that has to ask about a
 *  finish the piece has *not* chosen: the option row offering it, which has to
 *  print the size you would get before you get it. Default is the piece's own
 *  choice, which is what every readout wants. */
export function redetailTarget(target, ratio, backend = upscalerOf(target)) {
  if (!backend) return null;
  const rules = rulesFor(pieceFamily(target));
  const [width, height] = resolveCanvas(ratio, sampleEdge(target), rules);
  return { sampled: { width, height }, scale: backend.scale,
           width: width * backend.scale, height: height * backend.scale };
}

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
// The face pass belongs to the default family — it is written against that
// family's detector, frame grid and re-encode, and every other family declares
// `face: false` — so these are that family's edges, spelled as such. A family
// that grows a face pass brings its own bounds and these become a declaration.
export const MIN_FACE_CANVAS = VIDEO_RULES.minShortEdge;
export const MAX_FACE_CANVAS = VIDEO_RULES.nativeShortEdge;
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
        Math.round(canvas / VIDEO_RULES.multiple) * VIDEO_RULES.multiple))
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
    // Whether the model picks the length instead. Only a family with a
    // duration head can — see `canDo(piece, "duration")` — and `duration_s`
    // stays what it is while auto is on, because it is the estimate the strip
    // counts with and what the card falls back to when auto goes off again.
    auto_duration: false,
    aspect: "16:9",
    short_edge: VIDEO_RULES.nativeShortEdge,
    // The two-pass choice and its two knobs. Owned wherever the canvas is
    // owned; all inert while the first-pass edge is not under the slider.
    upscale: UPSCALE_MODES[0],
    sample_edge: VIDEO_RULES.nativeShortEdge,
    refine_denoise: DEFAULT_REFINE_DENOISE,
    // The face pass, off until asked for. Owned wherever the canvas is owned.
    face: emptyFace(),
    // "auto" follows the mode. Pinning it runs the same payload on the other
    // weights; compile.py decides which pins it will accept.
    checkpoint: "auto",
    // Which files to load. Owned by the node, not by a segment — a timeline
    // segment inherits the timeline's and never carries its own.
    models: emptyModels(),
    // And the upscale backend's own, on the same terms. Empty until a piece
    // asks to finish through one.
    upscale_models: emptyUpscalerModels(),
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
      // A hand-edited blob can hold anything, and a card carrying the flag
      // from a piece that has since been switched to a family with no duration
      // head means "the number beside it" — the same reading `compile_request`
      // gives it, so the pill and the queue agree.
      state.auto_duration = state.auto_duration === true;
      if (!UPSCALE_MODES.includes(state.upscale)) state.upscale = UPSCALE_MODES[0];
      state.sample_edge = clampSampleEdge(state.sample_edge,
                                          rulesFor(pieceFamily(state)));
      state.refine_denoise = clampRefineDenoise(state.refine_denoise);
      state.face = parseFace(state.face);
      state.models = parseModels(state.models);
      state.upscale_models = parseUpscalerModels(state.upscale_models);
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
 *  merged into one stack by `compile.merge_loras`.
 *
 *  Exported for the LoRA manager's saved stacks, which are preset bodies: a
 *  stack kept from that window and one captured by the preset library have to be
 *  the same bytes, and the way to be sure of that is one serializer. */
export function serializeLoras(entries, family = DEFAULT_VIDEO_FAMILY) {
  return entries.map((entry) => {
    const out = { name: entry.name, strength: round2(entry.strength) };
    if (entry.enabled === false) out.enabled = false;
    // The literal words, not a pointer at the sidecar: creator_data has to
    // still say what it means on a machine where that LoRA is missing.
    if (entry.triggers?.length) out.triggers = [...entry.triggers];
    // Absent means both checkpoints, so the common case adds nothing — and on
    // a family that routes between none, `modes` means nothing at all and is
    // never written.
    if (!claimsBoth(entry, family)) out.modes = [...entry.modes];
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
    // Absent means live, so nothing that was never muted grows a key.
    if (asset.enabled === false) out.enabled = false;
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

/** The parts of a state every generation has, timeline segment or not.
 *  `family` is the *piece's* — a segment carries none of its own — and only
 *  decides what a LoRA's checkpoint claim is worth. */
function serializeCommon(state, family = DEFAULT_VIDEO_FAMILY) {
  return {
    prompt: state.prompt ?? "",
    ...serializeRefined(state.refined),
    // An empty field is emitted as nothing, which is not the same as "N/A" —
    // see contextir.compose. A segment leaving them blank inherits the
    // timeline's rather than clearing them.
    ...(state.soundscape?.trim() ? { soundscape: state.soundscape } : {}),
    ...(state.music?.trim() ? { music: state.music } : {}),
    assets: serializeAssets(state.assets),
    loras: serializeLoras(state.loras, family),
    duration_s: state.duration_s,
    // Only the deliberate state is written: absent is "the length is the
    // number beside it", which is what every blob written before the head
    // existed says and means.
    ...(state.auto_duration ? { auto_duration: true } : {}),
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
    // Native is the *piece's* family's — `first_pass_edge` reads an absent one
    // as that family's own edge, so comparing against another family's would
    // write out the number that was already going to be assumed.
    ...(state.upscale !== UPSCALE_MODES[0] ? { upscale: state.upscale } : {}),
    ...(state.sample_edge !== rulesFor(pieceFamily(state)).nativeShortEdge
      ? { sample_edge: state.sample_edge } : {}),
    ...(state.refine_denoise !== DEFAULT_REFINE_DENOISE
      ? { refine_denoise: state.refine_denoise } : {}),
    ...serializeFace(state.face),
    // Not in serializeCommon: the weights belong to the node, and a timeline
    // segment goes through that function too. The turbo switch likewise.
    ...serializeModels(state.models),
    ...serializeUpscalerModels(state.upscale_models),
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

// Mirrors compile.MAX_SEGMENTS / compile.MAX_TIMELINE_MINUTES — two bounds on two
// quantities, and only the second is about work. Cards are bounded so a corrupt
// blob is refused before it is walked; how long the queue runs is a question
// about frames, because a pass is anything from 5 to 1445 of them and a run of
// cards is one generation. `canAddSegment` is what the strip actually asks.
export const MAX_SEGMENTS = 240;
export const MAX_TIMELINE_MINUTES = 30;

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

/** Which pass, by position — what indexes anything held one-per-pass, such as
 *  `passWindows`. Separate from `passOf` because a caller with a window list in
 *  hand wants the subscript and not the pass. */
export function passIndexOf(timeline, index) {
  return passes(timeline).findIndex((pass) => index >= pass.start && index < pass.end);
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

// ---- takes and holds --------------------------------------------------------
//
// A piece built a pass at a time. Mirrors the same section of compile.py, which
// is where the argument for the shape lives; what is here is what the strip
// needs to draw it.
//
// Two keys and four readings. `hold` takes a card out of the next render;
// `take` is the render it already has. Held with a take is a card playing the
// film it already has, held without one is a card that has not been shot yet,
// and no hold at all is a card that is sampled — whether or not an old take is
// sitting on it, because retaking is the absence of a hold rather than a mode
// of its own.
//
// Neither belongs to a clip card: it is played rather than generated, so "not
// in the next render" could only mean "not in the piece", which is what
// removing it is for.

/** Whether this card is out of the next render. Mirrors `compile.is_held`. */
export const isHeld = (segment) => !isClip(segment) && segment?.hold === true;

/** The render this card has, kept or not. A card being retaken still has last
 *  time's until this one lands. */
export const takeOn = (segment) =>
  (segment?.take && String(segment.take.filename || "").trim() ? segment.take : null);

/** Whether this card plays a take instead of being sampled. Mirrors
 *  `compile.take_of`: a take only counts while the card is held, because a take
 *  on a card that is in the render is a take about to be replaced. */
export const isKept = (segment) => isHeld(segment) && takeOn(segment) !== null;

/** Whether a pass is sampled by the next render. A pass is one generation and
 *  there is no half of one to hold, so the run's first card answers for it —
 *  the same place the seam flags and the mode are read from. */
export const passShot = (pass) => !isClip(pass.segments[0]) && !isHeld(pass.segments[0]);

/**
 * A card's own seed, or null for the piece's.
 *
 * Absent is the default and means the number on the node: a piece is one look
 * and the seed is the handle on it. A card carries one when it has been retaken
 * until it came out right — the number that made that take is a fact about the
 * take. Mirrors `compile.segment_seed`.
 */
export function segmentSeed(segment) {
  const raw = segment?.seed;
  if (raw === null || raw === undefined || raw === "") return null;
  const seed = Number(raw);
  return Number.isInteger(seed) && seed >= 0 ? seed : null;
}

/**
 * The takes a finished render reported, onto the cards that made them.
 *
 * -> whether any landed. By card number rather than by position, because a
 * render is not always the whole strip: the save node is told which card each
 * pass is, and that number is the number on the card. One that has moved or
 * been deleted since the queue went out is left alone rather than guessed at.
 *
 * Nothing is held here. A take that came back is a take to look at, and holding
 * the card is the gesture that says it is good — doing it here would decide for
 * the user, and would quietly stop the next queue from re-rendering the card
 * they were about to re-render.
 *
 * `stamp` is what the card looked like when its take was attached, so an edit
 * afterwards can be marked rather than silently shipped — see `editedSince`. It
 * is taken now rather than at queue time, which leaves a window: a card edited
 * while its own render was still running is stamped as if the edit had been in
 * it. The cost of closing that is a queue-time hook, for a mark that only ever
 * says "look at this again".
 */
export function attachTakes(timeline, reports) {
  // One serialization for the whole report rather than one per take: the strip
  // is the thing being hashed, and it is the same strip for all of them.
  const stamps = stampsOf(timeline);
  let landed = false;
  for (const report of reports ?? []) {
    const index = Number(report.segment) - 1;
    const segment = timeline.segments[index];
    if (!segment || isClip(segment)) continue;
    segment.take = takeFrom(report, stamps[index]);
    landed = true;
  }
  return landed;
}

function takeFrom(report, stamp) {
  return {
    // Annotated the way the picker annotates a file from the gallery, because
    // that is what this is: a video under output/, named so that
    // `folder_paths.get_annotated_filepath` finds it. Without the tag it would
    // be looked for in the input folder and the take would simply not exist.
    filename: `${[report.subfolder, report.filename].filter(Boolean).join("/")} [output]`,
    duration_s: Number(report.duration_s) || 0,
    ...(report.width && report.height
      ? { width: Number(report.width), height: Number(report.height) } : {}),
    has_audio: report.has_audio !== false,
    ...(Number.isInteger(report.seed) ? { seed: report.seed } : {}),
    stamp,
  };
}

/**
 * Which cards' kept takes no longer describe the card.
 *
 * -> a Set of segment indices. Editing a kept card is allowed — the take is
 * still the film that exists — but the card has stopped being a description of
 * it, and marking that is the difference between a strip you can trust and one
 * that quietly ships last week's shot. The piece's own fields are in the stamp
 * too: changing the global prompt or the canvas changes what every card would
 * render to, so every take goes stale together, which is the truth.
 */
export function editedSince(timeline) {
  const stamps = stampsOf(timeline);
  const edited = new Set();
  timeline.segments.forEach((segment, index) => {
    const take = takeOn(segment);
    if (take && take.stamp && take.stamp !== stamps[index]) edited.add(index);
  });
  return edited;
}

/** One stamp per card, off a single serialization of the piece. Per card rather
 *  than per call because a strip of twenty would otherwise serialize the piece
 *  twenty times to answer one question about it. */
function stampsOf(timeline) {
  const blob = JSON.parse(serializeTimeline(timeline));
  const { segments, ...piece } = blob;
  const head = JSON.stringify(piece);
  return (segments ?? []).map((card) => {
    const { hold, take, ...rest } = card;
    return hash(head + JSON.stringify(rest));
  });
}

/** FNV-1a, base 36. Not a checksum of anything anyone else reads — it only has
 *  to change when the card does. */
function hash(text) {
  let value = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 0x01000193) >>> 0;
  }
  return value.toString(36);
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
export function continuingSegment(piece) {
  const state = emptySegment();
  state.continue = true;
  state.continue_audio = true;
  // Medium — the third of the family's four widths, which is ~0.9 s of
  // inherited motion on H3 and ~0.7 s on LTX 2.5. The position in the grid
  // rather than the number, because the number is the family's.
  state.feather = featherGridOf(piece)[2];
  return state;
}

export function emptyTimeline() {
  return {
    version: 2,
    // Which architecture renders it. One for the whole piece, like the canvas
    // and for the same reason; the default is the family this pack shipped
    // alone, so a fresh node is the node it always was.
    family: DEFAULT_VIDEO_FAMILY,
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
    short_edge: VIDEO_RULES.nativeShortEdge,
    // The two-pass choice rides with the canvas, which is the timeline's.
    upscale: UPSCALE_MODES[0],
    sample_edge: VIDEO_RULES.nativeShortEdge,
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
    // The cast: who the piece is about. Written alongside the prompt that cites
    // them and cleared with it — a subject nobody names is a shelf of files the
    // next scene never asked for.
    subjects: [],
    // How much of the previous segment's sound a continuing seam inherits.
    // Mirrors compile.DEFAULT_AUDIO_TAIL_S.
    audio_tail_s: DEFAULT_AUDIO_TAIL_S,
    // The sound lane: files placed on the finished piece's own clock, which the
    // picture is generated against. Empty until one is laid down. See sound.py.
    sound: [],
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
    models: { ...emptyModels(), route: ROUTED.timeline },
    // The weights this piece picked for the families it is not on. Empty until
    // it has been switched at least once — see `setFamily`.
    models_spare: {},
    // The upscale backend's own files, when the piece finishes through one.
    upscale_models: emptyUpscalerModels(),
    // The turbo switch. Global like the LoRA it engages: a speed-up belongs to
    // the run, not to shot 3.
    turbo: emptyTurbo(),
    // The rows dialled for the families this piece is not on. See `setFamily`.
    sampling_spare: {},
    // How the piece is sampled. Empty on a fresh node and empty in every blob
    // saved before the row moved off the widgets: an absent field falls back to
    // the widget it always used, so a piece that says nothing here samples the
    // way it always did. See `sampling.py`.
    sampling: {},
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
 * the reference pool, the cast, the sound lane, and the strip — which goes back
 * to one blank shot, the same thing a piece is when you drop the node.
 *
 * The lane goes because a laid track is the piece's own sound: the shots under
 * it are generated against it, and leaving it behind hands the next scene a
 * soundtrack somebody wrote for the one before it. The files are untouched —
 * what is cleared is where they were laid, which is writing like the rest.
 *
 * The cast goes with the prose that cites it. Left behind, it is a set of
 * subjects no `@handle` in the piece names any more: they draw a shelf, they
 * ride down onto every card as `segment.cast`, and they make the next scene's
 * first prompt answer to somebody it never cast.
 *
 * Everything not named here survives, and that is the whole point of the
 * control. Where the weights are, which LoRAs are patched onto them, the turbo
 * switch, the canvas, the face pass and the render mode are all set once for a
 * machine or for a project; retyping them is not part of starting the next
 * scene. The sampler row is not in the blob at all and so is untouched by
 * construction.
 */
export const CLEARED_KEYS = ["prompt", "soundscape", "music", "refined", "assets", "subjects",
                             "sound", "segments"];

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
    || segment.auto_duration
    || (segment.checkpoint && segment.checkpoint !== "auto")
    || faceOverride(segment));

/** Whether `clearPiece` would change anything. A piece still as it was dropped
 *  has nothing to clear, and the tool says so by being unavailable rather than
 *  by arming, confirming and then doing nothing. */
export function pieceWritten(timeline) {
  if (CLEARED_KEYS.some((key) => typeof timeline[key] === "string" && timeline[key].trim())) return true;
  if (timeline.refined) return true;
  if (timeline.assets?.length) return true;
  if (timeline.subjects?.length) return true;
  if (timeline.sound?.length) return true;
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
 * Render this piece with another family, in place.
 *
 * What the writing is stays: the prompt, the cast, the reference pool, the
 * strip and its seams are a piece, not a checkpoint's idea of one. What goes is
 * everything keyed by the old family's own vocabulary, because carrying it
 * across would not be carrying a setting — it would be naming slots and
 * checkpoints the new family does not have:
 *
 * - the weights block, whose keys *are* the old family's slot ids;
 * - the turbo switch, whose LoRA was distilled against the old weights — and
 *   the LoRA with it: the switch owns that entry, and a distill left in the
 *   stack after its switch is gone is a file patched onto weights it was never
 *   trained against, with no control left that admits to owning it;
 * - every card's checkpoint pin, which names a routed slot by id;
 * - each LoRA's `modes`, for the same reason — the file is left in the stack,
 *   because a LoRA is the user's and dropping it silently would be losing work,
 *   and it is retargeted at whatever the new family routes to.
 *
 * **The weights are set aside rather than thrown away.** They are not writing,
 * they are which files this machine has, and re-picking six of them for every
 * trip between two families is the kind of chore that makes a switch not worth
 * making. The outgoing block is stashed on the piece under its family's id and
 * the incoming one comes back from that stash — and failing that from
 * `remembered`, the last block this machine picked for the family it is going
 * to (`settings.weights`, which the pill supplies because this module holds no
 * machine settings of its own).
 *
 * The canvas survives but is re-clamped: the edges are the new family's, and a
 * 1024 short edge on a family that stops at 768 is not a canvas.
 */
export function setFamily(timeline, id, remembered = null) {
  const family = VIDEO_FAMILIES.includes(id) ? id : DEFAULT_VIDEO_FAMILY;
  const was = pieceFamily(timeline);
  if (family === was) return false;
  timeline.family = family;

  // Set aside under the family it belongs to, so coming back is free. Only
  // what was picked — an untouched block stashes nothing, and the stash a
  // piece never fills is never written to its blob.
  const spare = parseSpareModels(timeline.models_spare);
  const incoming = spare[family] ?? remembered?.[family];
  const outgoing = serializeModels(timeline.models, was).models;
  if (Object.keys(outgoing).length) spare[was] = outgoing;
  else delete spare[was];
  // The family being switched *to* keeps nothing in the stash: its block is
  // about to be the live one, and two copies of it would be one to go stale.
  delete spare[family];
  timeline.models_spare = spare;

  timeline.models = parseModels(incoming, family);
  // The sampler row, on the same terms and for a sharper reason: `steps` and
  // `sampler_name` are spelled the same on both families and mean different
  // things, so a row left in place is H3's 20 res_multistep steps quietly in
  // force on a transformer distilled to want 8 euler ones.
  //
  // The turbo switch is released into it first. Switching off *is* putting the
  // row back — that is the whole bargain the switch strikes — and a switch
  // reset without it would set aside a row that is a distillation's step count
  // rather than the one the user dialled.
  if (timeline.turbo?.on && timeline.turbo.saved) {
    timeline.sampling = { ...(timeline.sampling ?? {}), ...timeline.turbo.saved };
  }
  const rows = parseSamplingSpare(timeline.sampling_spare);
  const row = rows[family];
  const dialled = parseSampling(timeline.sampling, was);
  if (Object.keys(dialled).length) rows[was] = dialled;
  else delete rows[was];
  delete rows[family];
  timeline.sampling_spare = rows;
  timeline.sampling = row ?? {};

  // The switch's own entry goes with the switch. Every other LoRA stays: it is
  // the user's file and theirs to keep or remove, and the chip is where that is
  // said. See the note above.
  if (timeline.turbo?.lora) removeLora(timeline, timeline.turbo.lora);
  timeline.turbo = emptyTurbo(family);

  const routed = checkpointsOf(family);
  // A seam's width is retargeted rather than dropped, for the same reason a
  // LoRA is: the user asked for a blend of about that length and the new
  // family can make one, just not out of the same number of frames. The
  // nearest width its video VAE can encode standalone is what they meant —
  // H3's medium 22 becomes LTX's 25. `syncCanvas` drops anything that is
  // still off the grid or that the card can no longer afford.
  const grid = featherGrid(rulesFor(family));
  const nearest = (width) => grid.reduce(
    (best, f) => (Math.abs(f - width) < Math.abs(best - width) ? f : best), grid[0]);
  for (const entry of timeline.loras ?? []) entry.modes = [...routed];
  const predicts = Boolean(videoFamily(family).capabilities?.duration);
  for (const segment of timeline.segments ?? []) {
    delete segment.checkpoint;
    if (segment.feather > 1) segment.feather = nearest(segment.feather);
    // Unlike the blend, this is dropped rather than retargeted: there is no
    // nearest answer to "let the model choose" on a family whose weights
    // cannot. The card falls back to the length beside the pill, which is what
    // `duration_s` has been holding all along.
    if (!predicts) segment.auto_duration = false;
    for (const entry of segment.loras ?? []) entry.modes = [...routed];
  }

  // The same two clamps `clampSampleEdge` and the resolution slider apply, on
  // the new family's numbers: the canvas snaps to its grid and stops at its
  // ceiling, and the first-pass edge stops at its native size — past which
  // there is no second pass to be the first half of.
  const rules = rulesFor(family);
  const edge = (value, ceiling) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return rules.nativeShortEdge;
    const snapped = Math.round(n / rules.multiple) * rules.multiple;
    return Math.min(ceiling, Math.max(rules.minShortEdge, snapped));
  };
  timeline.short_edge = edge(timeline.short_edge, rules.maxShortEdge);
  timeline.sample_edge = edge(timeline.sample_edge, rules.nativeShortEdge);
  // An aspect the new family does not list is its nearest listed shape, which
  // is `describeRatio`'s question asked of the ratio the label stood for.
  if (!rules.aspects.some(([label]) => label === timeline.aspect)) {
    // Looked up in the family being *left*, which is what the label meant: read
    // off the default family's list it was the right ratio only while the piece
    // happened to be on that family, and every other switch resolved the label
    // against a list it was never written in.
    const ratio = rulesFor(was).aspects
      .find(([label]) => label === timeline.aspect)?.[1] ?? 16 / 9;
    timeline.aspect = rules.aspects.reduce(
      (best, entry) => Math.abs(entry[1] - ratio) < Math.abs(best[1] - ratio) ? entry : best,
      rules.aspects[0])[0];
  }
  return true;
}

/**
 * The files a subject's handles can name in a piece: the pool, and a lone
 * shot's own row.
 *
 * A piece of one shot keeps its cast's pictures on that shot — see
 * `promoteCastFiles` for why — so the two lists are one scope wherever the
 * question is "what is this piece's cast built out of". The same pair
 * `parseTimeline` narrows against on the way in.
 */
export function castAssets(timeline) {
  const segments = timeline.segments ?? [];
  const lone = segments.length === 1 ? (segments[0].assets ?? []) : [];
  return [...(timeline.assets ?? []), ...lone];
}

/** `text` with `@old` rewritten to `@new` for each entry of `renamed`. The
 *  word boundary is what keeps `@img-1` off the front of `@img-10`. */
function renameCitations(text, renamed) {
  let out = String(text ?? "");
  for (const [from, to] of renamed) {
    out = out.replace(new RegExp(`@${from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g"), `@${to}`);
  }
  return out;
}

/**
 * The copies a duplicated card left behind, sent after the files they copy.
 *
 * `Timeline.duplicate` copies a card whole, so duplicating the only shot of a
 * piece hands the new card its own deep copy of every one of the cast's files —
 * and it is the *original* the promotion above then moves into the pool. What
 * is left on the clone is the same picture again, under the handle the original
 * wore, claimed by no subject: invisible in the cast shelf, uncited by anything
 * the shelf can see, and a second reference the model is billed for at queue
 * time. It is the copy of a file that has moved, so it follows it.
 *
 * Handle *and* filename, which is exactly the clone's signature. A handle is
 * one card's own vocabulary — `img-1` on card 5 is not the file `img-1` on card
 * 1 was — and the same picture attached to another card by hand under a handle
 * of its own is a second reference somebody meant, which `poolDoubles` reports
 * rather than repairs.
 *
 * The card's own prose follows too, for the reason card 1's does: the old name
 * meant something there and now names nothing.
 */
function followPromoted(timeline, moved, renamed) {
  timeline.segments.forEach((segment, index) => {
    if (!index || isClip(segment)) return;
    const dropped = new Map();
    for (const asset of [...(segment.assets ?? [])]) {
      if (asset.role !== "reference" || moved.get(asset.handle) !== asset.filename) continue;
      dropped.set(asset.handle, renamed.get(asset.handle));
      segment.assets = segment.assets.filter((entry) => entry !== asset);
    }
    if (!dropped.size) return;
    for (const key of ["prompt", "soundscape", "music"]) {
      if (segment[key]) segment[key] = renameCitations(segment[key], dropped);
    }
    const refined = segment.refined;
    if (refined?.body) refined.body = renameCitations(refined.body, dropped);
    for (const [name, text] of Object.entries(refined?.sections ?? {})) {
      refined.sections[name] = renameCitations(text, dropped);
    }
    // The piece's aspect source, where it named this card's copy. Card 0 is the
    // pool, which is where the picture is now — the same move card 1's source
    // makes at the foot of `promoteCastFiles`.
    const source = timeline.aspect_source;
    if (source && typeof source === "object" && Number(source.card) === index + 1
        && dropped.has(source.handle)) {
      timeline.aspect_source = { handle: dropped.get(source.handle) };
    }
  });
}

/**
 * A piece of more than one shot keeps its cast's files in the pool.
 *
 * A piece of one shot keeps them on that shot's own row instead — both
 * `presets.addSubjectToPiece` and the face's own "attach a file…" put them
 * there — because a piece with a pool is not a lone shot any more and the node
 * would answer casting somebody by folding its face into the strip summary.
 *
 * The cast itself is the piece's either way, and that is where the two part
 * company the moment a second card exists: the files are somewhere only card 1
 * can see. The shelf in the Timeline window draws a member with no pictures
 * behind them, and citing them on card 2 is refused at queue time over files
 * that are sitting right there on card 1.
 *
 * So growing the strip moves them, once, here — which is also what repairs a
 * piece that was grown before this existed, since every load syncs. Handles are
 * reallocated: `ref-N` is what a pool entry is called, and `img-1` on card 1 is
 * not the same file as `img-1` on card 5. Card 1's own prose is rewritten to
 * follow, because that is where the old name meant something — and so is the
 * prose of a card holding a copy of what moved, which `followPromoted` sends
 * after it.
 */
function promoteCastFiles(timeline) {
  const cast = timeline.subjects ?? [];
  const segment = timeline.segments?.[0];
  if (!cast.length || (timeline.segments?.length ?? 0) < 2 || isClip(segment)) return;
  const claimed = new Set();
  for (const subject of cast) {
    for (const handle of subjectFiles(subject)) claimed.add(handle);
    for (const handle of replacesOf(subject)) claimed.add(handle);
  }
  if (!Array.isArray(timeline.assets)) timeline.assets = [];
  const renamed = new Map();
  // What each promoted handle was a picture of, for the copies below.
  const moved = new Map();
  for (const asset of [...(segment.assets ?? [])]) {
    // References only. A keyframe a subject claims is refused by
    // `subjectProblem` and by `subjects.check`, and moving it would turn a
    // refusal the user can still act on into a picture that quietly changed
    // card.
    if (!claimed.has(asset.handle) || asset.role !== "reference") continue;
    const was = asset.handle;
    asset.handle = nextPoolHandle(timeline);
    renamed.set(was, asset.handle);
    moved.set(was, asset.filename);
    timeline.assets.push(asset);
    segment.assets = segment.assets.filter((entry) => entry !== asset);
  }
  if (!renamed.size) return;
  for (const subject of cast) {
    if (Array.isArray(subject.from)) {
      subject.from = subject.from.map((handle) => renamed.get(handle) ?? handle);
    }
    for (const slot of ["motion", "voice"]) {
      if (renamed.has(subject[slot])) subject[slot] = renamed.get(subject[slot]);
    }
    const stood = replacesOf(subject);
    if (stood.length) subject.replaces = stood.map((h) => renamed.get(h) ?? h);
  }
  for (const key of ["prompt", "soundscape", "music"]) {
    if (segment[key]) segment[key] = renameCitations(segment[key], renamed);
  }
  const refined = segment.refined;
  if (refined?.body) refined.body = renameCitations(refined.body, renamed);
  for (const [name, text] of Object.entries(refined?.sections ?? {})) {
    refined.sections[name] = renameCitations(text, renamed);
  }
  // The piece's aspect source, where it named one of these on card 1. Card 0 is
  // the pool, which is where the file is now.
  const source = timeline.aspect_source;
  if (source && typeof source === "object" && renamed.has(source.handle)) {
    timeline.aspect_source = { handle: renamed.get(source.handle) };
  }
  followPromoted(timeline, moved, renamed);
}

/**
 * A piece back down to one shot keeps its references on that shot.
 *
 * The exact inverse of `promoteCastFiles`, and it exists for the same sentence
 * read the other way. Growing a strip moves the cast's files into the pool
 * because they are somewhere only card 1 can see; a strip that shrinks back to
 * one card has no second card left to see them from, and the reason for the
 * pool is gone with it.
 *
 * Without this the pool was a one-way door, and an expensive one: the piece
 * goes on carrying a field a shot's face has no slot for, so `loneShot` stays
 * false, the node stays folded into the strip summary, and the toggle back is
 * drawn dead over "the reference pool" — a field nothing on that face can
 * empty. Add a second card once and the Creator never wears its own face again.
 *
 * The cast's files and nothing else, which is the promotion's own filter read
 * backwards. A pool entry no subject claims was attached to the *piece* on
 * purpose — from the strip's own bar, where that is the only thing attaching
 * means — and it holds the strip open by design: the shot's face has no row for
 * a reference every card shares. Emptying that is the user's to do, and the
 * dead toggle already names it.
 *
 * At one shot the pool and the shot's own row are a single scope already —
 * `castAssets` reads them as one, and `syncCanvas` mirrors the pool onto the
 * segment for compile — so what moves changes address, not meaning.
 */
function collapsePool(timeline) {
  const segments = timeline.segments ?? [];
  const segment = segments[0];
  const cast = timeline.subjects ?? [];
  if (segments.length !== 1 || isClip(segment) || !cast.length) return;
  if (!(timeline.assets ?? []).length) return;
  const claimed = new Set();
  for (const subject of cast) {
    for (const handle of subjectFiles(subject)) claimed.add(handle);
    for (const handle of replacesOf(subject)) claimed.add(handle);
  }
  if (!Array.isArray(segment.assets)) segment.assets = [];
  const renamed = new Map();
  for (const asset of [...timeline.assets]) {
    if (!claimed.has(asset.handle) || asset.role !== "reference") continue;
    const was = asset.handle;
    // The shot's vocabulary: img-1, vid-2, aud-1. `ref-N` says "the piece's",
    // and there is no piece left to say it about.
    asset.handle = nextHandle(segment, asset.kind);
    if (was !== asset.handle) renamed.set(was, asset.handle);
    segment.assets.push(asset);
    timeline.assets = timeline.assets.filter((entry) => entry !== asset);
  }
  if (!renamed.size) return;
  for (const subject of timeline.subjects ?? []) {
    if (Array.isArray(subject.from)) {
      subject.from = subject.from.map((handle) => renamed.get(handle) ?? handle);
    }
    for (const slot of ["motion", "voice"]) {
      if (renamed.has(subject[slot])) subject[slot] = renamed.get(subject[slot]);
    }
    const stood = replacesOf(subject);
    if (stood.length) subject.replaces = stood.map((h) => renamed.get(h) ?? h);
  }
  // Both scopes' prose. The piece's own text can cite a pool handle, and it
  // still holds the strip open on its own — but a citation left pointing at a
  // handle nothing answers to would survive being emptied, which is worse than
  // the rewrite being redundant here.
  for (const key of ["prompt", "soundscape", "music"]) {
    if (timeline[key]) timeline[key] = renameCitations(timeline[key], renamed);
    if (segment[key]) segment[key] = renameCitations(segment[key], renamed);
  }
  for (const holder of [timeline.refined, segment.refined]) {
    if (holder?.body) holder.body = renameCitations(holder.body, renamed);
    for (const [name, text] of Object.entries(holder?.sections ?? {})) {
      holder.sections[name] = renameCitations(text, renamed);
    }
  }
  // The piece's aspect source, in the shape a card's file takes: the pool is
  // card 0, and the file is on card 1 now.
  const src = timeline.aspect_source;
  if (src && typeof src === "object" && renamed.has(src.handle)) {
    timeline.aspect_source = { handle: renamed.get(src.handle), card: 1 };
  }
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
    // A clip is played rather than generated, so it has no hold to be out of
    // the render by and no take to play instead of one.
    if (isClip(segment)) { delete segment.hold; delete segment.take; }
  });
  // Holds belong to the pass. A pass is one generation and its take is one
  // file, so a run of merged cards is shot or held together and the run's first
  // card is where both are read from — the same rule the mode badge and the
  // off-distribution mark already follow. Cleared here rather than guarded at
  // every read, so merging a kept card into a live pass cannot leave half a
  // pass holding a take of the other half.
  for (const pass of passes(timeline)) {
    if (pass.segments.length < 2) continue;
    const held = isHeld(pass.segments[0]);
    pass.segments.forEach((segment, offset) => {
      if (held) segment.hold = true; else delete segment.hold;
      if (offset) delete segment.take;
    });
  }
  // Before the aspect source is pruned, because a promoted or demoted file is
  // one of the things it can name and it must be renamed rather than dropped.
  // The two are exclusive by segment count and neither is a toggle: each is
  // asked on every load and answers about the strip as it stands.
  promoteCastFiles(timeline);
  collapsePool(timeline);
  // The piece's aspect source, pruned before it is mirrored: a card that was
  // deleted or an asset that was detached leaves a name pointing at nothing,
  // and compile would refuse the strip over it. Cleared here once, like every
  // other stale flag, rather than guarded at every read.
  const source = timeline.aspect_source;
  if (source !== undefined && source !== "pill" && !validAspectSource(timeline, source)) {
    delete timeline.aspect_source;
  }
  timeline.segments.forEach((segment, index) => {
    if (isClip(segment)) return;   // no canvas, no pool, no prompt to mirror
    segment.aspect = timeline.aspect;
    // Mirrored in the segment's own vocabulary — a handle, "pill", or nothing
    // — so `aspectSourceAsset` answers per segment. A source naming another
    // card's asset mirrors as nothing here; only the timeline bar can show it.
    delete segment.aspect_source;
    const src = timeline.aspect_source;
    if (src === "pill") segment.aspect_source = "pill";
    else if (src && typeof src === "object" && src.handle
             && (!src.card || Number(src.card) === index + 1)) {
      segment.aspect_source = src.handle;
    }
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
    // The cast rides down with the pool and for the same reason: a segment
    // citing @anna is a reference generation, and every accessor that reads the
    // prompt — `citedPool`, the chips, `mode()` — has to be able to tell.
    segment.cast = timeline.subjects ?? [];
    segment.globalTexts = {
      prompt: timeline.prompt ?? "",
      soundscape: timeline.soundscape ?? "",
      music: timeline.music ?? "",
    };
  });
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
  const rules = rulesFor(pieceFamily(timeline));
  const grid = featherGrid(rules);
  // "Let the model choose" is meaningless on a family with no weights that
  // can. Cleared here, like every other stale flag, so a hand-edited blob and
  // a piece switched away from LTX arrive in the same shape — and so the flag
  // is never written where `compile_request` would read it as a no anyway.
  const predicts = canDo(timeline, "duration");
  const pins = canDo(timeline, "seam_pin");
  timeline.segments.forEach((segment, index) => {
    if (!predicts) segment.auto_duration = false;
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
    // A width off this family's own grid goes with it: the run a seam inherits
    // has to be one its video VAE can encode standalone, and a strip switched
    // between families carries the old family's numbers until something drops
    // them. `compile_request` refuses them, so this is what keeps the pill and
    // the queue saying the same thing.
    if (segment.feather) {
      const paying = isClip(segment) ? timeline.segments[index - 1] : segment;
      if (!paying || isClip(paying)
          || !grid.includes(segment.feather)
          || 2 * segment.feather > framesForSeconds(paying.duration_s, rules)) {
        delete segment.feather;
      }
    }
    // The pin goes with the blend it modifies — on an unblended seam the
    // boundary frame is the seam and is named whatever this says, and on a
    // family with one conditioning channel there is nothing to pin twice.
    if (segment.feather_pin && (!segment.feather || !pins)) delete segment.feather_pin;
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
  syncSound(timeline);
  return timeline;
}

/**
 * Keep the sound lane inside the piece it is laid on.
 *
 * The lane is placed in piece time and the piece can get shorter underneath it —
 * shorten a shot, delete a card, switch to a family whose grid rounds the other
 * way, and a cue that ended on the last frame now runs off the end. `sound.parse`
 * refuses that, which is right for a hand-edited blob and wrong as the thing a
 * user meets for trimming a shot: the render would stop with an error about a
 * file they were not touching.
 *
 * So the same rule the feathers above follow — what the piece can no longer
 * afford is cut here rather than left to fail at queue time. Cut and not
 * dropped: a cue is minutes of somebody's music and losing all of it because the
 * piece lost a second is not a trade anybody would make. Only a block left with
 * nothing at all goes.
 */
function syncSound(timeline) {
  if (!timeline.sound?.length) return timeline;
  const rules = rulesFor(pieceFamily(timeline));
  const total = timelineFrames(timeline);
  const kept = [];
  for (const entry of timeline.sound) {
    const at = Math.max(0, Math.round((Number(entry.at_s) || 0) * rules.fps));
    const room = (total - at) / rules.fps;
    if (room < MIN_SOUND_SECONDS) continue;
    const length = (Number(entry.out_s) || 0) - (Number(entry.in_s) || 0);
    kept.push(length <= room ? entry
      : { ...entry, out_s: Number((entry.in_s + room).toFixed(3)) });
  }
  timeline.sound = kept;
  return timeline;
}

/**
 * The lane, read off a blob that may have been hand-written.
 *
 * `sound.parse` refuses what this drops — that is the right answer on the
 * Python side, where a bad block is a render that must not start, and the wrong
 * one here, where it is a node that will not open. Same rule the rest of this
 * reader follows: keep what can be read, drop what cannot, and let the surface
 * show what survived.
 */
function parseSound(raw) {
  if (!Array.isArray(raw)) return [];
  // Dropped on exactly what `sound.parse` raises on, so the lane never draws a
  // block the compiler will refuse: a lane that showed one would send the user
  // to a queue-time error about a file they cannot see anything wrong with.
  const number = (value) => {
    const parsed = Number(value ?? 0);
    return Number.isFinite(parsed) ? round3(parsed) : null;
  };
  return raw
    .filter((entry) => entry && typeof entry.filename === "string" && entry.filename)
    .map((entry) => ({
      filename: entry.filename,
      at_s: number(entry.at_s),
      in_s: number(entry.in_s),
      out_s: number(entry.out_s),
    }))
    .filter((entry) => entry.at_s !== null && entry.in_s !== null && entry.out_s !== null
                    && entry.at_s >= 0 && entry.out_s - entry.in_s >= MIN_SOUND_SECONDS);
}

/** The lane, as the blob stores it. Same three decimals `soundlane.store`
 *  writes: the lane is placed on a clock, and rounding it to the two the rest
 *  of this file uses would move a cue by up to half a frame every save. */
const serializeSound = (blocks) => blocks.map((block) => ({
  filename: block.filename,
  at_s: round3(block.at_s),
  in_s: round3(block.in_s),
  out_s: round3(block.out_s),
}));

const round3 = (value) => Number((Number(value) || 0).toFixed(3));

/** Mirrors `sound.MIN_SECONDS`. Spelled here rather than imported: `sound.js`
 *  imports this module, and a cycle for one constant is a worse trade than one
 *  number said twice with the mirror suite holding them equal. */
const MIN_SOUND_SECONDS = 0.25;

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
export const PIECE_FIELDS = ["family", "aspect", "aspect_source", "short_edge",
                             "upscale", "sample_edge", "refine_denoise", "face",
                             "models", "models_spare", "upscale_models", "turbo",
                             "output_prefix", "subjects", "sampling",
                             "sampling_spare"];

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
      // Absent in every blob saved before the sampler row moved, and anything
      // at all in a hand-edited one.
      timeline.sampling = parseSampling(timeline.sampling, pieceFamily(timeline));
      // The cast. Absent in every workflow saved before it existed, and a
      // hand-edited blob can hold anything; kept as written otherwise, because
      // whether a subject's files are still attached is the band's readout
      // rather than a reason to drop somebody the user cast.
      if (!Array.isArray(timeline.subjects)) timeline.subjects = [];
      timeline.subjects = timeline.subjects
        .filter((s) => s && typeof s.handle === "string")
        .map((s) => ({
          handle: s.handle,
          from: Array.isArray(s.from) ? s.from.filter((h) => typeof h === "string") : [],
          takes: SUBJECT_TAKES.includes(s.takes) ? s.takes : "person",
          ...(s.description ? { description: String(s.description) } : {}),
          ...(subjectFeatures(s).length ? { features: subjectFeatures(s) } : {}),
          ...(s.motion ? { motion: String(s.motion) } : {}),
          ...(s.voice ? { voice: String(s.voice) } : {}),
          ...(replacesOf(s).length ? { replaces: replacesOf(s) } : {}),
          ...(s.replaces_what ? { replaces_what: String(s.replaces_what) } : {}),
          ...(SUBJECT_MARKERS.includes(s.relationship) ? { relationship: s.relationship } : {}),
        }));
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
      // Absent in every workflow saved before a second video family existed,
      // and anything at all in a hand-edited one. Both read as the default,
      // which is what `compile.piece_family` will do with them anyway.
      timeline.family = pieceFamily(timeline);
      if (!RENDER_MODES.includes(timeline.render)) timeline.render = "chained";
      // The piece form is "pill" or {card?, handle?}. A bare handle is a
      // hand-written blob's shorthand for the first card's asset (a lone
      // generation, usually), read as such; anything else is dropped and
      // `syncCanvas` prunes what no longer names a picture.
      const src = timeline.aspect_source;
      if (typeof src === "string" && src && src !== "pill" && src !== "auto") {
        timeline.aspect_source = { card: 1, handle: src };
      } else if (src !== "pill" && (!src || typeof src !== "object")) {
        delete timeline.aspect_source;
      }
      timeline.audio_tail_s = clampTail(timeline.audio_tail_s);
      timeline.sound = parseSound(timeline.sound);
      for (const key of ["soundscape", "music"]) {
        if (typeof timeline[key] !== "string") timeline[key] = "";
      }
      if (!timeline.refined || typeof timeline.refined !== "object") timeline.refined = null;
      if (!UPSCALE_MODES.includes(timeline.upscale)) timeline.upscale = UPSCALE_MODES[0];
      timeline.sample_edge = clampSampleEdge(timeline.sample_edge,
                                             rulesFor(pieceFamily(timeline)));
      timeline.refine_denoise = clampRefineDenoise(timeline.refine_denoise);
      timeline.face = parseFace(timeline.face);
      timeline.models = parseModels(timeline.models, timeline.family);
      timeline.models_spare = parseSpareModels(timeline.models_spare);
      timeline.sampling_spare = parseSamplingSpare(timeline.sampling_spare);
      timeline.upscale_models = parseUpscalerModels(timeline.upscale_models);
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
          if (featherGridOf(timeline).includes(width) && width > 1) segment.feather = width;
          if (raw.feather_pin === true) segment.feather_pin = true;
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
        delete segment.feather_pin;
        const width = Number(raw?.feather);
        if (featherGridOf(timeline).includes(width) && width > 1) segment.feather = width;
        if (raw?.feather_pin === true) segment.feather_pin = true;
        // Whether this card is in the next render, and the render it already
        // has. Both survive a reload for the same reason the prompt does: a
        // piece shot a pass at a time is shot over days, and a strip that
        // forgot which cards were done would ask for them all again.
        delete segment.hold;
        if (raw?.hold === true) segment.hold = true;
        delete segment.take;
        const take = raw?.take;
        if (take && typeof take === "object" && String(take.filename || "").trim()) {
          segment.take = {
            filename: String(take.filename),
            duration_s: Number(take.duration_s) || 0,
            ...(Number(take.width) > 0 && Number(take.height) > 0
              ? { width: Number(take.width), height: Number(take.height) } : {}),
            has_audio: take.has_audio !== false,
            ...(Number.isInteger(take.seed) ? { seed: take.seed } : {}),
            ...(take.stamp ? { stamp: String(take.stamp) } : {}),
          };
        }
        // The card's own seed. Absent — which is every card until somebody
        // rolls one here — means the number on the node.
        delete segment.seed;
        const seed = Number(raw?.seed);
        if (Number.isInteger(seed) && seed >= 0) segment.seed = seed;
        return segment;
      });
      // Every cast file narrowed to what its slot says — once, on the way in.
      //
      // A piece written before hanging a file on somebody narrowed it carries
      // their pictures at "full", which tells the model the opposite of what they
      // are: "what the target video takes from it is what the picture actually
      // shows", background and pose and all. That is not a preference anybody
      // set, it is a line nobody knew was there, so it is repaired here rather
      // than left for the user to find four shots later.
      //
      // Read against the lists a subject's handle can actually name — the pool,
      // and a lone shot's own row, which is where a piece of one shot keeps their
      // pictures. Never across cards: `img-1` on card 2 is a different file
      // from `img-1` on card 5, and narrowing somebody else's picture because
      // it shares a handle is worse than the line this is fixing.
      //
      // After the promotion rather than before it, so a piece grown into a
      // strip before that repair existed is narrowed on the load that moves its
      // cast's files rather than on the one after. `syncCanvas` runs it again
      // below and has nothing left to do.
      promoteCastFiles(timeline);
      collapsePool(timeline);
      for (const subject of timeline.subjects) {
        inheritTakes(subject, castAssets(timeline));
      }
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
    // Absent means the default, so every piece rendered before a second family
    // existed round-trips to the bytes it always did — the same rule `upscale`
    // and `aspect_source` follow, and the one `compile.piece_family` reads.
    ...(pieceFamily(timeline) !== DEFAULT_VIDEO_FAMILY ? { family: timeline.family } : {}),
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
    // Absent means auto — the rule that always held — so a piece that never
    // chose a source round-trips exactly as it always did.
    ...(timeline.aspect_source ? { aspect_source: timeline.aspect_source } : {}),
    short_edge: timeline.short_edge,
    ...(timeline.upscale !== UPSCALE_MODES[0] ? { upscale: timeline.upscale } : {}),
    ...(timeline.sample_edge !== rulesFor(pieceFamily(timeline)).nativeShortEdge
      ? { sample_edge: timeline.sample_edge } : {}),
    ...(timeline.refine_denoise !== DEFAULT_REFINE_DENOISE
      ? { refine_denoise: timeline.refine_denoise } : {}),
    ...serializeFace(timeline.face),
    loras: serializeLoras(timeline.loras ?? [], pieceFamily(timeline)),
    // The reference pool. Absent when empty, so a timeline that never used one
    // round-trips exactly as it always did.
    ...(timeline.assets?.length ? { assets: serializeAssets(timeline.assets) } : {}),
    // The cast, on the same terms: absent when nobody was cast, so a piece
    // without one round-trips to the bytes it always did.
    ...(timeline.subjects?.length ? { subjects: timeline.subjects } : {}),
    audio_tail_s: clampTail(timeline.audio_tail_s),
    // The sound lane. Absent when nothing is on it, so a piece that never laid
    // a track down round-trips to the bytes it always did — and present the
    // moment one is, which is the whole of what a lane is for: it is the piece
    // being cut to something, and a piece that forgot it on reload was not.
    ...(timeline.sound?.length ? { sound: serializeSound(timeline.sound) } : {}),
    // Where this node's renders land, when the blob overrides the setting. No
    // control writes it — it is the hand-edit the README documents as the only
    // way to have two nodes write to different places — so it is carried
    // through rather than understood. Dropping it here is what made editing
    // anything on the node quietly move its output back to the default folder.
    ...(timeline.output_prefix ? { output_prefix: timeline.output_prefix } : {}),
    ...serializeModels(timeline.models, pieceFamily(timeline)),
    ...serializeSpareModels(timeline.models_spare),
    ...serializeUpscalerModels(timeline.upscale_models),
    ...serializeTurbo(timeline.turbo),
    ...serializeSampling(timeline.sampling, pieceFamily(timeline)),
    ...serializeSamplingSpare(timeline.sampling_spare),
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
          ...(index > 0 && segment.continue && feather(segment, timeline) > 1
            ? { feather: feather(segment, timeline) } : {}),
          ...(index > 0 && segment.continue && featherPin(segment, timeline)
            ? { feather_pin: true } : {}),
        };
      }
      const out = serializeCommon(segment, pieceFamily(timeline));
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
      if (out.continue && feather(segment, timeline) > 1) {
        out.feather = feather(segment, timeline);
        // Only alongside the blend, and only the deliberate state — absent is
        // "the blend speaks for itself", which is the default and what every
        // blob written before the switch existed says.
        if (featherPin(segment, timeline)) out.feather_pin = true;
      }
      // Out of the next render, and the render it already has. Only the
      // deliberate states are written: a card nobody has held and nothing has
      // rendered writes exactly what it always did.
      if (segment.hold === true) out.hold = true;
      if (takeOn(segment)) out.take = { ...segment.take };
      if (segmentSeed(segment) !== null) out.seed = segmentSeed(segment);
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
/**
 * Where every pass lands in the finished piece — one window per pass.
 *
 * Two frame counts per pass, and the difference between them is why this is not
 * a running sum of durations. `at`/`frames` are what the pass *delivers*, which
 * is its place in the file and so the axis a soundtrack is laid against.
 * `sampledAt`/`sampled` are what it *generates*, which is wider at both ends by
 * the seams it re-makes and the reel then trims off.
 *
 * A feathered seam re-generates its inherited run at the head of the pass, and
 * those frames cover the same instants as the tail of the pass in front — so
 * `sampledAt` is `at` less the head blend, on one clock rather than two. That is
 * what lets supplied sound cross a seam: both passes are handed the same stretch
 * of the same track for the frames they share.
 *
 * Mirrors `compile.timeline_windows`.
 */
export function passWindows(timeline) {
  const all = passes(timeline);
  // The piece's own family's: the grid a pass snaps to and the rate a clip's
  // seconds become frames at are both the weights', and this readout is the
  // number on the strip's bar. Mirrors `compile.timeline_windows`, which asks
  // `rules_of(data)` for exactly the same two things.
  const rules = rulesFor(pieceFamily(timeline));
  const windows = [];
  let at = 0;
  all.forEach((pass, index) => {
    const head = pass.segments[0];
    const seconds = cutTimes(pass.segments).total;
    // A clip is played, not sampled, so its length is its own — there is no
    // frame grid to snap it to. Mirrors `compile.timeline_windows`.
    if (isClip(head)) {
      const frames = Math.round(seconds * rules.fps);
      windows.push({ at, frames, sampledAt: at, sampled: frames, clip: true });
      at += frames;
      return;
    }
    // A blended seam re-generates its inherited run at the pass's head and
    // trims it off after decode, so those frames are sampled but never
    // delivered. Only between passes: a seam inside one does not exist.
    //
    // Never on a clip: its seam flags describe the blend running *backwards*
    // into it, which is paid for by the pass in front and is subtracted there.
    // Read here as well, they would take it off the strip twice.
    const lead = index > 0 && continues(head) && feather(head, timeline) > 1
      ? feather(head, timeline) : 0;
    // ...and the same at the far end, where a clip in front of the next pass
    // owns the blend: those frames are re-generated at *this* pass's tail.
    const after = all[index + 1]?.segments[0];
    const tail = after && isClip(after) && continues(after) && feather(after, timeline) > 1
      ? feather(after, timeline) : 0;
    const sampled = framesForSeconds(seconds, rules);
    windows.push({ at, frames: sampled - lead - tail,
                   sampledAt: at - lead, sampled, clip: false });
    at += sampled - lead - tail;
  });
  return windows;
}

export function timelineFrames(timeline) {
  return passWindows(timeline).reduce((total, window) => total + window.frames, 0);
}

/** How many shots this piece's family advises putting in one generation, or
 *  null where its guidance gives no number. Advice rather than a limit: a
 *  longer pass is marked, never refused. */
export const advisedShots = (piece) =>
  familyOf(piece).capabilities?.multishot?.advised_max ?? null;

/** Whether a pass holds more cuts than its family advises. What LTX 2.5's own
 *  prompting guide says is "prefer 2-4 shots in one generation; more cuts
 *  usually need clearer, shorter beats per shot" — so this is the same kind of
 *  statement `isTrainedLength` makes about a duration, and wears the same mark. */
export function overAdvisedShots(timeline, pass) {
  const advised = advisedShots(timeline);
  return advised !== null && pass.segments.length > advised;
}

/** Whether any card on this strip has its length picked by the model, which
 *  makes every total above an estimate rather than a count. The readouts say so
 *  with a "~"; see `_predicted_frames` for why no better number exists before
 *  the render. */
export const hasAutoDuration = (timeline) =>
  canDo(timeline, "duration")
  && (timeline.segments ?? []).some((segment) => segment.auto_duration === true);

/** What the finished clip will run to. */
export function timelineSeconds(timeline) {
  return secondsForFrames(timelineFrames(timeline),
                          rulesFor(pieceFamily(timeline)));
}

/**
 * How much of the piece the next queue will actually make.
 *
 * The same arithmetic as `timelineFrames` over the passes that are sampled: a
 * held card is not one, and neither is a card playing a take or a supplied
 * clip. Equal to the whole piece on a strip that has never held anything, which
 * is why the bar only shows it when the two differ — a number that always
 * matched its neighbour would be noise on every render anyone has run so far.
 */
export function sampledFrames(timeline) {
  const all = passes(timeline);
  const rules = rulesFor(pieceFamily(timeline));
  return all.reduce((total, pass, index) => {
    if (!passShot(pass)) return total;
    const head = pass.segments[0];
    const overlap = index > 0 && continues(head) && feather(head, timeline) > 1
      ? feather(head, timeline) : 0;
    const after = all[index + 1]?.segments[0];
    const runs = after && isClip(after) && continues(after) && feather(after, timeline) > 1
      ? feather(after, timeline) : 0;
    return total + framesForSeconds(cutTimes(pass.segments).total, rules) - overlap - runs;
  }, 0);
}

/** ...in seconds of finished video. */
export function sampledSeconds(timeline) {
  return secondsForFrames(sampledFrames(timeline),
                          rulesFor(pieceFamily(timeline)));
}

/**
 * Shoot this pass and nothing else: lock every other card, unlock this one.
 *
 * -> whether anything changed. The gesture the whole feature is for. A piece is
 * built one expensive generation at a time — shoot a card, look at it, keep it,
 * move on — and doing that by hand means locking five cards to shoot the sixth,
 * then unlocking one and locking another for every step after. Said once, it is
 * one click per card: soloing the next card locks the one before it, and a card
 * locked with a take is a card playing its take, so the strip walks itself
 * forward.
 *
 * Whole passes, because a pass is one generation and there is no half of one to
 * shoot. Clips are left alone: a supplied clip is played rather than generated,
 * so it is not something to hold back from a render.
 */
export function soloPass(timeline, index) {
  let changed = false;
  for (const pass of passes(timeline)) {
    const head = pass.segments[0];
    if (isClip(head)) continue;
    const wanted = !(pass.start <= index && index < pass.start + pass.segments.length);
    for (const segment of pass.segments) {
      if (wanted === (segment.hold === true)) continue;
      if (wanted) segment.hold = true; else delete segment.hold;
      changed = true;
    }
  }
  return changed;
}

/**
 * Lock or unlock the whole strip.
 *
 * -> whether anything changed. The two ends of shooting a piece in parts: lock
 * everything to stop generating and let the render assemble the piece out of
 * the takes it already has, unlock everything to put the whole strip back in
 * the pot. Neither is reachable by soloing, which always leaves one card out.
 */
export function holdAll(timeline, held) {
  let changed = false;
  for (const segment of timeline.segments) {
    if (isClip(segment)) continue;
    if (held === (segment.hold === true)) continue;
    if (held) segment.hold = true; else delete segment.hold;
    changed = true;
  }
  return changed;
}

/**
 * Forget the take on this card. -> whether there was one.
 *
 * The card goes back to what it was before it rendered: locked with nothing to
 * play, or simply in the next render. Only the strip's memory of the file is
 * dropped — the take itself stays under output/ with the rest of them, because
 * it is a render somebody may still want and this is a card saying it is not
 * the one.
 *
 * The pass's, like everything else about a take: a pass is one generation and
 * its take is one file, so the run's first card answers for it.
 */
export function dropTake(timeline, index) {
  const segment = passes(timeline).find(
    (pass) => pass.start <= index && index < pass.start + pass.segments.length,
  )?.segments[0];
  if (!segment || !takeOn(segment)) return false;
  delete segment.take;
  return true;
}

/** Whether the strip is holding anything back — which is what decides whether
 *  any of this is drawn at all. */
export const shotInParts = (timeline) =>
  timeline.segments.some((segment) => isHeld(segment) || takeOn(segment));

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
  const rules = rulesFor(pieceFamily(timeline));
  const cap = MAX_TIMELINE_MINUTES * 60 * rules.fps;
  if (timelineFrames(timeline) + framesForSeconds(seconds, rules) > cap) {
    return t("A timeline holds at most {minutes} minutes of finished video. "
           + "Shorten it, or split the piece across two Timeline nodes.",
             { minutes: MAX_TIMELINE_MINUTES });
  }
  return null;
}

// ---- pre-stage --------------------------------------------------------------
//
// The PreStage node's blob. Mirrors compile_image.py the way this file mirrors
// compile.py and canvas.js mirrors canvas.py: the UI shows the resolved canvas
// and refuses the illegal combinations early, and compile_image.py stays
// authoritative at queue time.

/** The arch pill's vocabulary and order — the catalog's still_arches, named
 *  by each family's own label. */
export const PRESTAGE_ARCHES = Object.keys(STILL_ARCHES);
export const PRESTAGE_ARCH_LABEL = Object.fromEntries(
  PRESTAGE_ARCHES.map((arch) => [arch, stillFamily(arch).label]));

// The video family's arch is not an image model, and almost nothing below
// applies to it. Its still is a *video generation* whose first latent frame is
// decoded as a picture, so its request is an ordinary creator state — same
// assets, same LoRAs, same weights block, same routing — and every rule for it
// is the one already written for the video nodes. It lives in its own
// sub-block (`state[PRESTAGE_STILL_ARCH].request`) and is driven by
// CreatorEditor.

export const PRESTAGE_STILL_ARCH = stillOf(DEFAULT_VIDEO_FAMILY).arch;
export const isStill = (state) => state?.arch === PRESTAGE_STILL_ARCH;

/** The canvas rules a still on this branch is counted on. A still made by the
 *  video model is a video generation one latent frame of which is decoded, so
 *  its frame counts land on that family's own grid and nowhere else. */
const STILL_RULES = rulesFor(STILL_ARCHES[PRESTAGE_STILL_ARCH]);

/** What the length pill offers, and what a fresh still samples: the family's
 *  declaration, from the cheapest legal clip up to the bottom of its trained
 *  range. */
export const PRESTAGE_STILL_LENGTHS = stillOf(DEFAULT_VIDEO_FAMILY).lengths;
export const PRESTAGE_STILL_FRAMES = stillOf(DEFAULT_VIDEO_FAMILY).default_frames;
export const PRESTAGE_STILL_INDEX = stillOf(DEFAULT_VIDEO_FAMILY).default_index;
export const PRESTAGE_PROMPT_MODES = stillOf(DEFAULT_VIDEO_FAMILY).prompt_modes;

/** Frames -> latent frames, on the manifest's grid. Mirrors the family
 *  still.py's latent_frames, which mirrors core's causal VAE packing. */
export const stillLatentFrames = (frames, grid = stillOf(DEFAULT_VIDEO_FAMILY).latent) =>
  (frames <= grid.base_frames ? grid.base_latent
    : Math.floor((frames - grid.base_frames) / grid.frame_step)
      * grid.latent_step + grid.base_latent);

/** What the still branch writes into the sampler row: the Creator node's own
 *  defaults — the family's sampler widgets — because it is the Creator's
 *  sampler. */
export const PRESTAGE_STILL_ROW = Object.fromEntries(
  widgetsOf(DEFAULT_VIDEO_FAMILY).filter((w) => ["steps", "cfg", "sampler_name", "scheduler"].includes(w.id))
               .map((w) => [w.id, w.default]));

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
  if (Number.isFinite(frames)) {
    out.frames = framesForSeconds(Math.max(1, frames) / STILL_RULES.fps, STILL_RULES);
  }
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

/** The two image architectures. The video family's branch keeps its weights
 *  inside its own request, in `models.Weights`' shape, so it is not one of
 *  these. */
export const PRESTAGE_IMAGE_ARCHES =
  Object.keys(STILL_ARCHES).filter((arch) => arch !== PRESTAGE_STILL_ARCH);

// The image families' shared canvas — every image family serves the same
// block, built from compile_image.py, and compile_image stays authoritative
// at queue time. Wider than the video envelope on purpose: a style sheet is a
// legitimate still. The aspects are [label, ratio] pairs in the popover's
// order, the declaration's own.
const IMAGE_CANVAS = stillFamily(DEFAULT_STILL_ARCH).canvas;
export const PRESTAGE_CANVAS_MULTIPLE = IMAGE_CANVAS.multiple;
export const PRESTAGE_MIN_EDGE = IMAGE_CANVAS.min_short_edge;
export const PRESTAGE_MAX_EDGE = IMAGE_CANVAS.max_short_edge;
export const PRESTAGE_DEFAULT_EDGE = IMAGE_CANVAS.default_short_edge;
export const PRESTAGE_MAX_PIXELS = IMAGE_CANVAS.max_pixels;
export const PRESTAGE_MIN_RATIO = IMAGE_CANVAS.min_ratio;
export const PRESTAGE_MAX_RATIO = IMAGE_CANVAS.max_ratio;
export const PRESTAGE_ASPECTS = Object.entries(IMAGE_CANVAS.aspects);
const PRESTAGE_DEFAULT_ASPECT = IMAGE_CANVAS.default_aspect;

const IMAGE_FAMILY = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES.map((arch) => [arch, stillFamily(arch)]));
const KREA = IMAGE_FAMILY.krea2;
const IDEOGRAM = IMAGE_FAMILY.ideogram4;
const widgetDefaults = (family, ids) => Object.fromEntries(
  family.widgets.filter((w) => ids.includes(w.id)).map((w) => [w.id, w.default]));

/** How many style references the arch takes — its encoder's own slot count. */
export const PRESTAGE_MAX_REFS = KREA.prompt.max_refs;

/** The sampler row each image arch runs with nothing distilled on it — the
 *  family's own widget defaults, which is what the arch pill writes into the
 *  widgets on arrival and what the turbo switch returns to on release.
 *
 *  Per arch rather than Krea's row for everyone: this node has one static
 *  schema wearing Krea's numbers, and an arch that samples 20 steps at cfg 4
 *  arriving on 52 at 3.5 is a slow render nobody asked for. Ideogram is the one
 *  exception and says so itself — its steps are the quality preset's, not a
 *  widget default. */
export const PRESTAGE_BASE_ROW = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES.map((arch) => [arch,
    widgetDefaults(IMAGE_FAMILY[arch], ["steps", "cfg", "sampler_name", "scheduler"])]));

/** Krea 2's turbo row and step table — its turbo capability's own. */
export const PRESTAGE_KREA_TURBO = KREA.capabilities.turbo.row;
export const PRESTAGE_TURBO_QUALITIES = Object.keys(KREA.capabilities.turbo.steps);
export const PRESTAGE_TURBO_STEPS = KREA.capabilities.turbo.steps;

/** Every image arch's turbo declaration, by arch. The pill is one pill and it
 *  does not mean one thing: Krea's throws a distilled checkpoint *or* the SVD
 *  extraction of it as a LoRA, Ideogram's has no distilled checkpoint to throw
 *  and is a LoRA or nothing. `checkpoint` and `lora` are which of the two a
 *  family offers, so the pill can draw the choice rather than assume it. */
export const PRESTAGE_TURBO = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES
    .filter((arch) => IMAGE_FAMILY[arch].capabilities.turbo)
    .map((arch) => [arch, IMAGE_FAMILY[arch].capabilities.turbo]));
export const turboOfArch = (arch) => PRESTAGE_TURBO[arch] ?? null;

/** How Krea 2 lays reference tokens into the sequence — the adapter's choice,
 *  because the published reference LoRAs disagree and neither layout errors.
 *  The blob's `ref_method` is that one family's field and stays Krea's. */
export const PRESTAGE_REF_METHODS = KREA.capabilities.refs.methods;
export const PRESTAGE_DEFAULT_REF_METHOD = KREA.capabilities.refs.default_method;

/** What an attached picture *means* on each image arch. Four different answers
 *  across three families, none of them guessable from the file: Ideogram reads
 *  none at all, Krea 2 reads them only through an adapter and wants to be told
 *  which layout that adapter learned, and Qwen Image Edit reads them on the base
 *  weights — where the first one is not a reference at all but the picture being
 *  changed, which is why it also decides the canvas. A family that declares no
 *  `refs` capability reads none. */
export const PRESTAGE_REFS = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES.map((arch) => {
    const refs = IMAGE_FAMILY[arch].capabilities.refs;
    return [arch, {
      reads: Boolean(refs),
      methods: refs?.methods ?? [],
      needsLora: refs?.needs_lora === true,
      editsFirst: refs?.edits_first === true,
      // What this family calls an attached picture, [singular, plural]. Not one
      // word for every family: Krea 2 carries a look across and "style
      // reference" is what those images contribute, while on an edit family the
      // same slot holds the subject and calling it a style reference names the
      // one thing the model is not reading it for.
      noun: refs?.noun ?? ["style reference", "style references"],
      // The blob field that releases the first picture from being the one
      // edited, on the family where it otherwise always is.
      startBlank: refs?.start_blank ?? null,
      // The tracings this family's weights follow when one arrives as a
      // picture, and the editions that learned to. Empty where a guide is not
      // a picture at all — on those families it is the init image, which is
      // what every guide was before these weights had a built-in ControlNet.
      nativeControl: refs?.native_control ?? [],
      controlEditions: refs?.control_editions ?? [],
      // Which blob field names the adapter that reads them, on the family where
      // one has to, and the filename needles the picker pre-selects from.
      adapter: refs?.adapter ?? null,
      adapterHints: refs?.adapter_hints ?? [],
      // How many pictures each release of these weights was post-trained on,
      // where that is not one number for every file the family loads.
      editions: refs?.editions ?? null,
      defaultEdition: refs?.default_edition ?? null,
      editionHints: refs?.edition_hints ?? [],
    }];
  }));

/** Qwen Image Edit's releases and the reference count each reads. */
const QWEN_REFS = PRESTAGE_REFS.qwenedit ?? {};
export const PRESTAGE_EDITIONS = QWEN_REFS.editions ?? {};
export const PRESTAGE_DEFAULT_EDITION = QWEN_REFS.defaultEdition ?? null;

/** Which edition a checkpoint filename looks like, or null when it says
 *  nothing — a guess offered to the pill, never a decision taken behind it.
 *  Mirrors `families/qwenedit/still.EDITION_HINTS`. */
export function preStageEditionGuess(filename) {
  const name = (filename ?? "").toLowerCase();
  if (!name) return null;
  for (const [needle, edition] of QWEN_REFS.editionHints ?? []) {
    if (name.includes(needle)) return edition;
  }
  return null;
}

/** How far a reference's shape may sit from the canvas before it is worth
 *  saying so.
 *
 *  A reference whose aspect does not match the output's is out of distribution
 *  for the edit adapters — they were trained on pairs that agreed — and it
 *  shows up as preservation quietly getting worse rather than as anything
 *  failing. 6% lets 16:9 against 1.85:1 pass and catches 3:2 against 16:9,
 *  which is the gap that actually happens when a still is dropped onto a
 *  canvas somebody set for something else. A warning and not a refusal: it is a
 *  worse render, not an impossible one.
 *
 *  The families whose first reference *is* the canvas cannot disagree with it,
 *  so this is Krea 2's alone. */
export const PRESTAGE_REF_RATIO_TOLERANCE = 0.06;

/** Is this reference's shape far enough from the canvas to warn about? */
export function preStageRefOffShape(state, size, canvasRatio) {
  const refs = PRESTAGE_REFS[state?.arch];
  if (!refs?.reads || refs.editsFirst) return false;
  if (!size?.width || !size?.height || !canvasRatio) return false;
  const ratio = size.width / size.height;
  return Math.abs(ratio - canvasRatio) / canvasRatio > PRESTAGE_REF_RATIO_TOLERANCE;
}

/** Fill in the reference adapter and the Qwen edition where the blob can say
 *  what they are — the one guess each, run after anything that could have
 *  changed the answer. Returns whether it wrote anything.
 *
 *  Neither is a decision taken behind the user: the adapter is only ever filled
 *  from a filename that names itself a reference LoRA (a stack holding one
 *  unrelated LoRA is left alone, which is the whole point of the field), and
 *  the edition only from a checkpoint filename that names a release. */
export function syncPreStageGuesses(state) {
  let changed = false;
  const refs = PRESTAGE_REFS[state.arch];
  if (refs?.adapter && !state.ref_lora && state.refs?.length) {
    const named = (state.loras ?? [])
      .filter((entry) => entry?.name && entry.enabled !== false)
      .map((entry) => entry.name)
      .find((name) => refs.adapterHints.some((hint) => name.toLowerCase().includes(hint)));
    if (named) {
      state.ref_lora = named;
      changed = true;
    }
  }
  if (refs?.editions) {
    const guess = preStageEditionGuess(state.models?.[state.arch]?.model);
    if (guess && guess !== state.edition) {
      state.edition = guess;
      changed = true;
    }
  }
  return changed;
}

/** How many references this render may carry, and why that is the number.
 *
 *  Not a constant: the encoder's three slots are one cap and what a checkpoint
 *  was post-trained to read is another, and on Qwen Image Edit the second
 *  changed between releases. Mirrors `compile_image.ref_limit`. */
export function preStageMaxRefs(state) {
  const refs = PRESTAGE_REFS[state?.arch];
  if (!refs?.editions) return PRESTAGE_MAX_REFS;
  return refs.editions[state.edition] ?? refs.editions[refs.defaultEdition] ?? PRESTAGE_MAX_REFS;
}

/** Ideogram's official preset table. The presets own steps *and* the schedule
 *  shape; the widget cfg feeds the dual-model guider. */
export const PRESTAGE_IDEOGRAM_QUALITIES = Object.keys(IDEOGRAM.capabilities.qualities);
export const PRESTAGE_IDEOGRAM_STEPS = Object.fromEntries(
  Object.entries(IDEOGRAM.capabilities.qualities).map(([name, preset]) => [name, preset.steps]));
export const PRESTAGE_IDEOGRAM_ROW = widgetDefaults(IDEOGRAM, ["cfg", "sampler_name"]);
const PRESTAGE_DEFAULT_QUALITY = widgetDefaults(IDEOGRAM, ["quality"]).quality;

export const PRESTAGE_DEFAULT_DENOISE = KREA.capabilities.init_image.default_denoise;
export const PRESTAGE_MIN_DENOISE = KREA.capabilities.init_image.min_denoise;

/** Which weight fields each architecture has — its manifest's slots, in
 *  popover order — and what the popover calls each one. */
export const PRESTAGE_FIELDS = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES.map((arch) => [arch, IMAGE_FAMILY[arch].weights.map((w) => w.id)]));
export const PRESTAGE_FIELD_LABEL = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES.flatMap((arch) =>
    IMAGE_FAMILY[arch].weights.map((w) => [w.id, w.title])));
export const PRESTAGE_FIELD_HINT = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES.map((arch) => [arch,
    Object.fromEntries(IMAGE_FAMILY[arch].weights.map((w) => [w.id, w.help]))]));

/** Filename hints for `guessPreStageModels`, per arch per field. */
const PRESTAGE_HINTS = Object.fromEntries(
  PRESTAGE_IMAGE_ARCHES.map((arch) => [arch,
    Object.fromEntries(IMAGE_FAMILY[arch].weights.map((w) => [w.id, w.hints]))]));

export function emptyPreStage() {
  return {
    version: 1,
    arch: DEFAULT_STILL_ARCH,
    prompt: "",
    aspect: PRESTAGE_DEFAULT_ASPECT,
    short_edge: PRESTAGE_DEFAULT_EDGE,
    // {"filename", "denoise"} for img2img, or null.
    init: null,
    // [{handle, filename}] — style references, Krea 2 only.
    refs: [],
    loras: [],
    // The turbo pill, per arch the way `models` is: it does not mean the same
    // thing on both sides, so one shared block would carry Krea's distilled
    // file onto Ideogram the moment the arch pill moved. Either way it keeps
    // the H3 contract — the sampler row is saved once per throw and put back
    // exactly on release — and `lora` is the entry in the ordinary stack the
    // switch owns, which is H3's arrangement too.
    turbo: emptyPreStageTurbo(),
    // Which reference layout Krea 2's adapter was trained on. See
    // `PRESTAGE_REF_METHODS`.
    ref_method: PRESTAGE_DEFAULT_REF_METHOD,
    // Which entry in the stack is that adapter. Named rather than counted: the
    // compile checks this field, because "the stack is not empty" would pass a
    // render whose only LoRA is a style and whose pictures go nowhere. Krea 2's
    // field; null until a reference is attached and one is picked.
    ref_lora: null,
    // Draw onto an empty canvas even with pictures attached, instead of editing
    // the first one. Only an edit family has anything to release; see
    // `preStageStartsBlank`.
    start_blank: false,
    // Which Qwen-Image-Edit release the checkpoint is, which decides how many
    // pictures it reads — nothing in the file says, so it is declared here and
    // guessed from the filename. See `PRESTAGE_EDITIONS`.
    edition: PRESTAGE_DEFAULT_EDITION,
    // Ideogram's speed axis: which official preset shapes the schedule.
    quality: PRESTAGE_DEFAULT_QUALITY,
    // The video family's branch: its own settings, and its generation in the
    // Creator's shape. Nothing above it applies to that branch — see
    // `emptyStill`. The key is the arch's frozen blob name.
    [PRESTAGE_STILL_ARCH]: emptyStill(),
    // See the piece's: empty until a pill writes one, and an absent field falls
    // back to the widget it always used.
    sampling: {},
    models: emptyPreStageModels(),
    // A hint for peer discovery, never authoritative — ids renumber on paste,
    // so the pre-stage pill re-derives the pairing by scan.
    peer: null,
  };
}

export function emptyPreStageTurbo() {
  const empty = {};
  for (const [arch, turbo] of Object.entries(PRESTAGE_TURBO)) {
    empty[arch] = { on: false, quality: turbo.default_quality, saved: null, lora: null };
  }
  return empty;
}

/** The pre-stage turbo block, validated per arch.
 *
 *  A blob written before the pill went per-arch has the flat shape, and is read
 *  as Krea 2's: it was the only arch with a turbo pill at all. The same reading
 *  the compiler does — see `compile_image.turbo_block`. */
export function parsePreStageTurbo(raw) {
  const out = emptyPreStageTurbo();
  const stored = raw && typeof raw === "object" ? raw : {};
  const blocks = typeof stored.on === "boolean" ? { krea2: stored } : stored;
  for (const [arch, empty] of Object.entries(out)) {
    const side = blocks[arch];
    if (!side || typeof side !== "object") continue;
    empty.on = side.on === true;
    if (Object.keys(PRESTAGE_TURBO[arch].steps).includes(side.quality)) empty.quality = side.quality;
    if (side.saved && typeof side.saved === "object") empty.saved = { ...side.saved };
    if (typeof side.lora === "string" && side.lora.trim()) empty.lora = side.lora.trim();
    // A LoRA-only arch cannot be on without one: Ideogram ships no distilled
    // checkpoint, so an `on` with no file is a compile refusal waiting to
    // happen. Read as off, which is what it will render as either way.
    if (empty.on && !empty.lora && !PRESTAGE_TURBO[arch].checkpoint) empty.on = false;
  }
  return out;
}

export function emptyPreStageModels() {
  const empty = { dtype: "default" };
  for (const arch of PRESTAGE_IMAGE_ARCHES) empty[arch] = {};
  return empty;
}

export function parsePreStage(raw) {
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      const state = { ...emptyPreStage(), ...parsed };
      if (!PRESTAGE_ARCHES.includes(state.arch)) state.arch = DEFAULT_STILL_ARCH;
      if (typeof state.prompt !== "string") state.prompt = "";
      if (!Array.isArray(state.refs)) state.refs = [];
      // Not truncated to the cap. The compile refuses a render carrying more
      // references than its weights read, and a blob quietly losing the fourth
      // one on the way in would put those two on different terms — and would
      // silently drop two pictures the moment the Qwen edition pill moved to
      // the release that reads one. The chips past the cap are drawn as
      // refused instead; see `renderRefChip`.
      state.refs = state.refs
        .filter((ref) => ref && typeof ref.filename === "string")
        // `guide` is the only role a picture can have beyond being one: it says
        // this slot holds a tracing the weights follow rather than a picture
        // they read. Nothing in the graph changes — the guide is Picture N like
        // any other — so this is carried for the chip and for the one refusal
        // that depends on it.
        .map((ref) => (ref.role === "guide"
          ? { handle: ref.handle, filename: ref.filename, role: "guide",
              guide: typeof ref.guide === "string" ? ref.guide : null }
          : { handle: ref.handle, filename: ref.filename }));
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
      if (!PRESTAGE_IDEOGRAM_QUALITIES.includes(state.quality)) state.quality = PRESTAGE_DEFAULT_QUALITY;
      state[PRESTAGE_STILL_ARCH] = parseStill(state[PRESTAGE_STILL_ARCH]);
      // The sampler row, on the same terms as the piece's — absent in every
      // blob saved before it moved off the widgets. See `sampling.py`.
      //
      // Read through the default family's list, which is deliberate: this node
      // samples stills, and every one of its five widgets is named in that
      // list. A still architecture that wants a row of its own would ask for it
      // here, the way `parseTimeline` asks for the piece's family's.
      state.sampling = parseSampling(state.sampling);
      if (!PRESTAGE_REF_METHODS.includes(state.ref_method)) {
        state.ref_method = PRESTAGE_DEFAULT_REF_METHOD;
      }
      state.ref_lora = typeof state.ref_lora === "string" && state.ref_lora.trim()
        ? state.ref_lora.trim() : null;
      state.start_blank = state.start_blank === true;
      if (!Object.keys(PRESTAGE_EDITIONS).includes(state.edition)) {
        state.edition = PRESTAGE_DEFAULT_EDITION;
      }
      state.turbo = parsePreStageTurbo(state.turbo);
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
      // Last, because both guesses read fields filled above — the LoRA stack
      // and the checkpoint this arch loads. A blob written before either field
      // existed comes in with the answer already worked out, rather than
      // wearing "no adapter" over a stack that plainly has one.
      syncPreStageGuesses(state);
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
    ...(state.refs.length ? { refs: state.refs.map((r) => ({
      handle: r.handle, filename: r.filename,
      ...(r.role ? { role: r.role } : {}),
      ...(r.guide ? { guide: r.guide } : {}),
    })) } : {}),
    loras: serializeLoras(state.loras),
    ...serializePreStageTurbo(state.turbo),
    ...(state.quality !== "default" ? { quality: state.quality } : {}),
    ...(state.ref_method !== PRESTAGE_DEFAULT_REF_METHOD ? { ref_method: state.ref_method } : {}),
    ...(state.ref_lora ? { ref_lora: state.ref_lora } : {}),
    ...(state.start_blank ? { start_blank: true } : {}),
    ...(state.edition !== PRESTAGE_DEFAULT_EDITION ? { edition: state.edition } : {}),
    [PRESTAGE_STILL_ARCH]: serializeStill(state[PRESTAGE_STILL_ARCH]),
    ...serializeSampling(state.sampling),
    ...(Object.keys(models).length ? { models } : {}),
    ...(state.peer != null ? { peer: state.peer } : {}),
  }, null, 2);
}

/** The turbo block, arches that have nothing to say left out — a pill never
 *  thrown writes nothing, exactly as the flat block did. */
function serializePreStageTurbo(turbo) {
  const out = {};
  for (const [arch, side] of Object.entries(turbo ?? {})) {
    if (!side?.on && !side?.saved) continue;
    out[arch] = {
      on: side.on, quality: side.quality,
      ...(side.lora ? { lora: side.lora } : {}),
      ...(side.saved ? { saved: { ...side.saved } } : {}),
    };
  }
  return Object.keys(out).length ? { turbo: out } : {};
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

/** Which picture this render's canvas follows, or null.
 *
 *  The init image, and on an edit family the first reference when there is no
 *  init: `Picture 1` is the thing being changed, so the compile promotes it to
 *  the init at denoise 1 and the aspect comes off it. Mirrored here so the
 *  aspect pill says "from image" for the same renders the compile resolves that
 *  way — see `compile_image.compile_prestage`. */
export function preStageSource(state) {
  if (state.init) return state.init.filename;
  if (PRESTAGE_REFS[state.arch]?.editsFirst && state.refs?.length
      && !state.start_blank) {
    return state.refs[0].filename;
  }
  return null;
}

/** Does this render read a ControlNet guide as one of its pictures?
 *
 *  True only where the weights were post-trained to follow one — which is a
 *  property of the edition, not of the family. Everywhere else a guide belongs
 *  in the init slot, at a denoise, the way every guide did before the built-in
 *  ControlNet existed. See `families/qwenedit/still.NATIVE_CONTROL`. */
export function preStageReadsGuides(state) {
  const refs = PRESTAGE_REFS[state?.arch];
  if (!refs?.nativeControl?.length) return false;
  return !refs.controlEditions.length
    || refs.controlEditions.includes(state.edition);
}

/** Is this render drawing onto an empty canvas with its pictures only cited?
 *
 *  Only ever true on a family whose first picture would otherwise be promoted
 *  to the thing being edited — everywhere else the empty canvas is simply what
 *  a render with no init image already does, and a flag saying so would be a
 *  second name for the same state. */
export function preStageStartsBlank(state) {
  const refs = PRESTAGE_REFS[state?.arch];
  return Boolean(refs?.editsFirst && state?.refs?.length && state.start_blank
                 && !state.init);
}

/** The resolved image canvas, mirroring compile_image.resolve_canvas: /16 grid,
 *  2048² area cap, and the aspect taken from the source picture when the caller
 *  measured one — `preStageSource` is which picture that is. */
export function resolvedPreStage(state, initSize = null) {
  let ratio = PRESTAGE_ASPECTS.find(([label]) => label === state.aspect)?.[1] ?? 16 / 9;
  let fromImage = false;
  if (initSize?.width && initSize?.height) {
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
  const dit = IMAGE_FAMILY[state.arch]?.capabilities.turbo && state.turbo.on ? "turbo_model" : "model";
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
  if (match) return (Number(match[2]) - 1 + (TAG_OFFSET[match[1]] ?? 0)) % 8;
  // A name rather than a file's handle, which is what a cast member wears:
  // `anna` counts nothing, so every one of them used to fall to hue 0 — the
  // shelf's "a cast of five reads as five colours" was one colour five times,
  // and a member's chip mid-prompt matched their card only by accident. Spread
  // over the same eight by the letters themselves: no counter to keep, and a
  // member keeps their colour across a reload and a rename back.
  return hue(String(handle ?? ""));
}

/** A string onto one of the eight hues. FNV-1a, for its spread on short inputs
 *  — `anna` and `anna_2` have to land apart, and a sum of char codes does not
 *  do that. `>>> 0` after each step keeps it in 32 unsigned bits, which is
 *  what makes the answer the same in every browser. */
function hue(text) {
  let value = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    value = (value ^ text.charCodeAt(i)) >>> 0;
    value = Math.imul(value, 0x01000193) >>> 0;
  }
  return value % 8;
}

/** Next free @handle for a kind: img-1, img-2, ... Stable across deletions.
 *
 *  `kind` may also be "plate", which is not a kind of file but the one thing a
 *  card can hold that is not one: a composite the picker made. It gets a prefix
 *  of its own so it cannot take a number a panel inside it wants — the panels
 *  are the `img-N`s, and the plate is what holds them. */
export function nextHandle(state, kind) {
  const prefix = kind === "plate" ? "plate" : PREFIX[kind];
  const taken = takenHandles(state);
  for (let n = 1; ; n += 1) {
    const handle = `${prefix}-${n}`;
    if (!taken.has(handle)) return handle;
  }
}

// ---- loras ------------------------------------------------------------------

const round2 = (value) => Math.round((Number(value) || 0) * 100) / 100;

/**
 * The checkpoints an entry claims. Missing or nonsense means every one of them.
 *
 * Empty on a family that routes between none: a LoRA there claims nothing
 * because there is nothing to claim between, and every reader below treats an
 * empty claim on such a family as "applies to the one set of weights". Which is
 * why the family has to be passed — the old reading, "unrecognised means both",
 * is H3's answer to a question LTX 2.5 does not ask, and it is what put an H3
 * distill on an LTX transformer.
 */
export function loraModes(entry, family = DEFAULT_VIDEO_FAMILY) {
  const all = checkpointsOf(family);
  if (!all.length) return [];
  const claimed = (entry.modes || []).filter((m) => all.includes(m));
  return claimed.length ? claimed : [...all];
}

/** Whether an entry claims everything there is to claim — which is vacuously
 *  true on a family with nothing, and is what keeps `modes` out of its blobs. */
export const claimsBoth = (entry, family = DEFAULT_VIDEO_FAMILY) =>
  loraModes(entry, family).length === checkpointsOf(family).length;

/** The checkpoint the mode implies, before any pin. Null on a family that
 *  routes between none: "which of them" has no answer where there is one. */
export const derivedCheckpoint = (state, family = DEFAULT_VIDEO_FAMILY) => {
  if (!routing(family)) return null;
  const routed = routesOf(family);
  return hasReferences(state) ? routed.reference : routed.plain;
};

/** Which checkpoint this state routes to, and so which LoRAs will apply.
 *  Mirrors `compile._resolve_checkpoint`, null included. */
export function checkpoint(state, family = DEFAULT_VIDEO_FAMILY) {
  if (!routing(family)) return null;
  const pin = state.checkpoint;
  return !pin || pin === "auto" ? derivedCheckpoint(state, family) : pin;
}

/** The same answer as a list, which is the shape `requiredModels` and the LoRA
 *  chips' `targets` want: one checkpoint, or none at all. */
export const checkpointsFor = (state, family = DEFAULT_VIDEO_FAMILY) => {
  const routed = checkpoint(state, family);
  return routed ? [routed] : [];
};

/** Whether the routing is the user's choice rather than the mode's. */
export const checkpointPinned = (state, family = DEFAULT_VIDEO_FAMILY) =>
  canPinCheckpoint(state, family) && state.checkpoint !== "auto";

/** A pin only means anything where there is a choice to make. References are
 *  encoded *for* Ref2VA — no other weights can read the blocks — so the
 *  reference modes have none, and neither has a family with one transformer. */
export const canPinCheckpoint = (state, family = DEFAULT_VIDEO_FAMILY) =>
  routing(family) && derivedCheckpoint(state, family) === routesOf(family).plain;

/** Drop a pin the mode has moved out from under. Attaching a reference turns a
 *  frame generation into a reference one, and compile.py rejects an fl2va pin on
 *  that outright; clearing it here keeps the blob queueable. */
export function normalizeCheckpoint(state, family = DEFAULT_VIDEO_FAMILY) {
  if (!canPinCheckpoint(state, family)) state.checkpoint = "auto";
}

/** The refiner's prose for a state, or "" when there is none in play. Mirrors
 *  `compile.refined_body` — same field, same meaning for `enabled`. */
export function refinedBody(state) {
  const refined = state?.refined;
  if (!refined || refined.enabled === false) return "";
  return (refined.body || "").trim();
}

export const findLora = (state, name) => state.loras.find((l) => l.name === name) || null;

/** Applied to the routed checkpoint on the next queue, in patch order. With
 *  nothing to route between, every enabled entry is applied — there is one set
 *  of weights and they are what a LoRA on this piece patches. Mirrors
 *  `compile.active_loras`. */
export function activeLoras(state, family = DEFAULT_VIDEO_FAMILY) {
  const target = checkpoint(state, family);
  return state.loras.filter((entry) =>
    entry.enabled !== false && round2(entry.strength) !== 0
    && (!target || loraModes(entry, family).includes(target)));
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
export function addLora(state, name, triggers = [], strength = null,
                        family = DEFAULT_VIDEO_FAMILY) {
  if (findLora(state, name)) return null;
  const entry = newLora(name, triggers, strength, family);
  state.loras.push(entry);
  return entry;
}

/** One entry, as the file and its sidecar describe it. */
function newLora(name, triggers, strength, family = DEFAULT_VIDEO_FAMILY) {
  // A file with no sidecar arrives as `strength: null`, and `Number(null)` is 0
  // — a weight, and a legal one, so it has to be ruled out before the cast.
  const preferred = typeof strength === "number" ? strength : NaN;
  return {
    name,
    // The window is a sanity check on what a sidecar claims, not a cap on what
    // a LoRA may be run at: slider LoRAs are trained as a signed axis and are
    // meant to be driven to ten or more, and clipping their author's own
    // suggested weight to 2 was the manager quietly disagreeing with the file.
    strength: Number.isFinite(preferred) && preferred >= -MAX_STRENGTH && preferred <= MAX_STRENGTH
      ? preferred : turboStrength(name),
    enabled: true,
    // The family's routed slots — none, on a family that ships one
    // transformer, where a claim would name a checkpoint nothing routes to.
    modes: [...checkpointsOf(family)], triggers: [...triggers],
  };
}

/**
 * The words compile.py will put in front of the prompt. Mirrors
 * `compile.collect_triggers` — same walk, same case-insensitive dedup — for the
 * same reason canvas.js mirrors canvas.py: the node has to show the composed
 * prompt before anything is queued. compile.py stays authoritative.
 */
export function promptTriggers(state, family = DEFAULT_VIDEO_FAMILY) {
  const out = [];
  const seen = new Set();
  for (const entry of activeLoras(state, family)) {
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
 *
 * Empty on a family that routes between none — and that empty list is the
 * answer every caller wants: no checkpoint is required of the weights popover,
 * no LoRA is idle for claiming the wrong one, and nothing is asked of a
 * `models` block that has no such slot in it.
 */
export function timelineCheckpoints(timeline) {
  const family = pieceFamily(timeline);
  const routed = new Set(passes(timeline)
    .map((pass) => passCheckpoint(pass.segments, family)));
  return checkpointsOf(family).filter((name) => routed.has(name));
}

/** The one checkpoint a pass runs on. Its shots are merged into a single
 *  request, so a reference in any of them makes the whole pass Ref2VA. */
export function passCheckpoint(segments, family = DEFAULT_VIDEO_FAMILY) {
  // Supplied footage is played rather than sampled, so it routes to no
  // checkpoint at all — and a clip is never merged, so a pass holding one
  // holds nothing else. Answered before `checkpoint()`, which would ask a clip
  // card for the references it has no place to keep.
  if (segments.some(isClip)) return null;
  if (!routing(family)) return null;
  if (segments.length === 1) return checkpoint(segments[0], family);
  const routed = routesOf(family);
  if (segments.some(hasReferences)) return routed.reference;
  const pin = segments.map((s) => s.checkpoint).find((c) => c && c !== "auto");
  return pin || routed.plain;
}

/** What a family calls a payload shape, back to the shape itself — the modes
 *  table read the other way. */
export const modeShape = (piece, named) =>
  Object.entries(modesOf(pieceFamily(piece))).find(([, label]) => label === named)?.[0] ?? null;

/**
 * A payload shape in plain words, for a readout that has no checkpoint to name.
 *
 * The families' own mode labels are their trainings' vocabulary — H3's
 * `FL2VA`, Lightricks' `FL2V` — and on H3 they earn their place, because the
 * badge that shows one is naming which of two checkpoint files the generation
 * routes to and the file is called that. On a family with one transformer
 * there is no second set of weights and nothing to route: the badge is a
 * readout of what this generation *is*, and "FL2V" is a codename for
 * "start → end" that a person has to already know to read.
 *
 * Keyed by the shape rather than by the label, so it is the same six words for
 * every family that ever declares one — the shapes are `grammar.py`'s
 * vocabulary and the labels are each family's.
 */
export const MODE_SHAPE_LABEL = {
  opens_closes: "start → end",
  opens: "from start frame",
  closes: "to end frame",
  text: "from text",
  reference: "from references",
};

/**
 * The mode a pass's merged request will compile to.
 *
 * `mode()` answers it for one segment, and a pass of one is exactly that. Past
 * one the shots are a single generation, so the question is asked of all of
 * them at once — a reference anywhere makes it REF2VA, and the keyframes are
 * the first shot's start and the last shot's end.
 */
export function passMode(segments, piece) {
  if (segments.length === 1) return mode(segments[0], piece);
  const modes = modesOf(pieceFamily(piece));
  if (modes.reference && segments.some(hasReferences)) return modes.reference;
  const head = segments[0] ?? { assets: [] };
  const first = frameAsset(head, "first_frame");
  const last = frameAsset(segments[segments.length - 1] ?? { assets: [] }, "last_frame");
  // The pass's own start frame is the seam's, when it has one — the same rule a
  // lone continuing segment follows, asked of the shot the seam lands on.
  if (continues(head)) return last ? modes.opens_closes : modes.opens;
  if (first && last) return modes.opens_closes;
  if (first) return modes.opens;
  if (last) return modes.closes;
  return modes.text;
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
/**
 * What is wrong with the strip as a whole, or null — the refusals a queue would
 * meet, said while the cards are still in front of you.
 *
 * Only one so far, and it is the one a piece shot a pass at a time can walk
 * into by clicking: holding the last card that was still in the render leaves
 * nothing for the queue to generate. Said rather than prevented, the way this
 * pack says the others — the strip is still saveable, and putting one card back
 * makes it right again.
 */
export function stripProblem(timeline) {
  if (!timeline.segments.length) return null;
  // A strip where every card plays a take is not a problem — it is the last
  // step of shooting a piece a pass at a time, and what it queues is the piece
  // written out of the film it already has, at no sampling cost at all. What
  // there is nothing to do about is a strip with no film and no generation.
  if (!passes(timeline).some((pass) => passShot(pass) || isKept(pass.segments[0])
                                       || isClip(pass.segments[0]))) {
    return t("Every card is held with nothing to play, so the next render has "
           + "nothing to make. Put one back in the render to shoot it.");
  }
  return seamProblem(timeline);
}

/**
 * A card that continues from film this render will not have. Mirrors
 * `compile._rebase_seam`.
 *
 * A held card with no take is not in the render at all, so the card behind it
 * moves up and inherits from whoever now sits in front of it. That is the one
 * way shooting out of order goes wrong, and it goes wrong quietly: the shot
 * comes back looking fine and is wrong only once the piece is assembled. The
 * queue refuses it, and this is that refusal said while the cards are still in
 * front of you.
 *
 * Which is also the rule for shooting out of order, stated: a card behind a cut
 * shoots whenever you like, and a card behind a seam waits for the one it
 * continues from. Nothing here objects to shooting card 6 before card 4 — only
 * to card 6 claiming to continue from a card that has not been shot.
 */
export function seamProblem(timeline) {
  const runs = passes(timeline);
  // Every card whose frames this render actually has: generated now, spliced
  // from a take, or supplied footage. A whole pass at a time, because a seam
  // reaching into a merged run lands on the pass that produces its frames.
  const here = new Set();
  for (const pass of runs) {
    const head = pass.segments[0];
    if (isHeld(head) && !isKept(head)) continue;
    pass.segments.forEach((_, index) => here.add(pass.start + index));
  }
  for (const pass of runs) {
    const head = pass.segments[0];
    // Nothing in front of the first card, nothing conditioned on a clip, and
    // nothing to say about a card that is not being generated.
    if (!pass.start || isClip(head) || isHeld(head)) continue;
    if (!head.continue && !head.continue_audio) continue;
    const source = continueSource(head, pass.start);
    if (here.has(source - 1)) continue;
    return t("Segment {card} continues from segment {source}, which is not in "
           + "this render — it is locked with nothing to play. Shoot segment "
           + "{source} first, or turn off the seam in front of segment {card} "
           + "to start it on nothing.",
             { card: pass.start + 1, source });
  }
  return null;
}

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

/** The global LoRAs that will be patched onto at least one segment. On a
 *  family that routes between nothing, every enabled entry is one — the same
 *  reading `activeLoras` gives. */
export function activeGlobalLoras(timeline) {
  const family = pieceFamily(timeline);
  const targets = timelineCheckpoints(timeline);
  return (timeline.loras ?? []).filter((entry) =>
    entry.enabled !== false && round2(entry.strength) !== 0
    && (!routing(family)
        || loraModes(entry, family).some((mode) => targets.includes(mode))));
}

export function removeLora(state, name) {
  state.loras = state.loras.filter((entry) => entry.name !== name);
}

/**
 * Out of the run without leaving the stack: the chip's mute.
 *
 * `enabled: false` is read everywhere a LoRA is counted — `activeLoras`,
 * `activeGlobalLoras`, the trigger prefix, `compile.merge_loras` — and it is
 * the answer to the only question the ✕ used to be asked: is this file the
 * reason the last render looked like that. Removing it to find out costs the
 * strength you dialled in, the checkpoint you pinned it to and the trigger
 * words you edited; muting it costs nothing and is the same click again to
 * undo. Turbo counts it as switching off, which is what it is — see `turbo.js`.
 */
export function toggleLora(state, name) {
  const entry = findLora(state, name);
  if (entry) entry.enabled = entry.enabled === false;
  return entry;
}

/**
 * Swap the file under one entry, keeping its slot.
 *
 * The slot is what you set up — where it sits in the patch order, which
 * checkpoint it claims, whether it is muted — and the file is what you are
 * trying out, so a swap changes the file and what travels with the file: the
 * new sidecar's trigger words and the weight its author settled on, exactly
 * what adding it fresh would have given you. Strengths do not carry across
 * files: 0.6 on a character LoRA and 0.6 on a distill are not the same number.
 *
 * Swapping to a file already in the stack is not a swap but a removal — the
 * same LoRA cannot be patched twice — so the old slot goes and the entry that
 * was already there is left exactly as it stands.
 */
export function replaceLora(state, name, next, triggers = [], strength = null,
                            family = DEFAULT_VIDEO_FAMILY) {
  const at = state.loras.findIndex((entry) => entry.name === name);
  if (at < 0 || next === name) return null;
  const was = state.loras[at];
  const already = findLora(state, next);
  if (already) {
    state.loras.splice(at, 1);
    return already;
  }
  state.loras[at] = {
    ...newLora(next, triggers, strength, family),
    modes: [...loraModes(was, family)],
    ...(was.enabled === false ? { enabled: false } : {}),
  };
  return state.loras[at];
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

// ---- the cast ---------------------------------------------------------------
//
// Subjects are the piece's, like the pool, and cited the same way. What differs
// is how a citation is recognised: a file's handle is known by its shape, a
// subject's only by having been declared, so `@anna` means nothing in a piece
// where nobody cast Anna and no prose is reinterpreted by the feature existing.
// Mirrors `subjects.py`.

/** What of the files behind a subject is the reference. Mirrors
 *  `subjects.TAKES` — the four an image takes, without the whole-video
 *  relationships, which have no subject in them. */
export const SUBJECT_TAKES = ["person", "object", "scene", "style"];

/** The reference guide's fixed relationship markers. Mirrors
 *  `subjects.MARKERS`; they are English output values in every language. */
export const SUBJECT_MARKERS = ["fully_preserved", "partially_preserved",
                                "attribute_transfer", "weak_reference"];

/** A subject's name: letters, digits and underscores, starting with a letter.
 *  No hyphen, which is exactly what tells it from a file's handle. Mirrors
 *  `subjects.HANDLE_RE`. */
export const SUBJECT_HANDLE_RE = /^[A-Za-z][A-Za-z0-9_]{0,31}$/;

/** Every file handle a subject claims, in citation order. Mirrors
 *  `subjects.Subject.files` — the clip somebody is replaced *in* is not among
 *  them, because its own content is kept and it keeps its own definition. */
/** The clips a subject stands in for somebody in, always as a list.
 *
 *  One person can occupy the same role in several clips — a medium shot and a
 *  close-up of one scene is the ordinary case — and while this held a single
 *  handle the second clip could only be attached and left undefined. Blobs
 *  written before that carry a bare string, which is read as the one-element
 *  list it always meant; `subjects.parse` does the same on the other side. */
export function replacesOf(subject) {
  const raw = subject?.replaces;
  if (!raw) return [];
  return (Array.isArray(raw) ? raw : [raw]).map(String).filter(Boolean);
}

/**
 * What the reference shows about a subject, one phrase per feature.
 *
 * The unit both of the guide's subject sections are made of: section 6's worked
 * example defines "<Subject 3> ... with long blonde hair and a light-pink
 * button-down shirt" and then names those same features again in
 * `retention_analysis`. `instead` is what the target video gives them in place
 * of one, which is section 4.1's `partially_preserved` exactly — "some defined
 * characteristics are changed".
 *
 * A bare string is read as a feature with nothing to say about it, and a row
 * with no text at all is dropped: the editor writes an empty row the moment
 * somebody presses "add a feature". Mirrors `subjects._parse_features`.
 */
export function subjectFeatures(subject) {
  return (subject?.features ?? [])
    .map((item) => (typeof item === "string"
      ? { is: item.trim(), instead: "" }
      : { is: String(item?.is ?? "").trim(), instead: String(item?.instead ?? "").trim() }))
    .filter((feature) => feature.is);
}

/**
 * The relationship marker a subject carries, derived. Mirrors
 * `subjects.Subject.relationship`.
 *
 * Derived from facts the user stated rather than picked off a list they could
 * contradict — which is what the picker was, and it wrote `partially_preserved`
 * over a sentence that said everything was retained. Standing in for somebody
 * leads, because the transfer is the relationship whatever else changes; a
 * feature the target video gives them instead is `partially_preserved`; the
 * rest is preserved whole.
 *
 * `relationship` on the blob still wins. It is the only way to reach
 * `weak_reference`, which nothing here can infer: "only broad similarity in
 * style, category, composition, or atmosphere" is a judgement about the render.
 */
export function subjectMarker(subject) {
  if (SUBJECT_MARKERS.includes(subject?.relationship)) return subject.relationship;
  if (replacesOf(subject).length) return "attribute_transfer";
  if (subjectFeatures(subject).some((feature) => feature.instead)) return "partially_preserved";
  return "fully_preserved";
}

export function subjectFiles(subject) {
  const out = [...(subject.from ?? [])];
  for (const extra of [subject.motion, subject.voice]) {
    if (extra && !out.includes(extra)) out.push(extra);
  }
  return out;
}

/**
 * The handles `subject` claims that nobody else in `cast` claims too.
 *
 * What a member takes with them when they leave. Casting somebody attaches
 * their pictures as it goes — `presets.addSubjectToPiece` and the shelf's own
 * `+` both do it — so removing them and leaving the files behind makes the node
 * accumulate pictures nothing points at, and the only way back is to find each
 * one on the asset row and press its own ✕.
 *
 * Claims only, deliberately. Whether a *prompt* still writes `@img-2` is a
 * question about the host's own texts, and the host is the one that can answer
 * it — see `handleWritten`. A shelf knows the cast and nothing else.
 */
export function soleClaims(subject, cast) {
  const held = new Set();
  for (const other of cast ?? []) {
    if (other === subject) continue;
    for (const handle of subjectFiles(other)) held.add(handle);
    for (const handle of replacesOf(other)) held.add(handle);
  }
  const mine = new Set(subjectFiles(subject));
  for (const handle of replacesOf(subject)) mine.add(handle);
  return [...mine].filter((handle) => !held.has(handle));
}

/**
 * Whether any of `texts` writes `@handle`.
 *
 * Texts only — no subject expansion. A host asking "may I drop this file now?"
 * has *just* taken somebody out of the cast, and the segment mirrors that
 * `syncTimeline` maintains have not caught up yet; a check that expanded the
 * cast would read the stale copy, find the departing member still citing the
 * file, and keep every one of them.
 */
export function handleWritten(texts, handle) {
  return citedHandles(texts).has(handle);
}

/** Every text in a piece a citation could be written into: the timeline's own
 *  three, and each segment's. */
export function allTexts(timeline) {
  const texts = [timeline.prompt, timeline.soundscape, timeline.music];
  for (const segment of timeline.segments ?? []) {
    texts.push(segment.prompt, segment.soundscape, segment.music);
  }
  return texts;
}

/** A pattern matching `@name` for exactly the subjects in `cast`, or null for
 *  an empty cast. Mirrors `subjects.citation_re`. */
export function subjectCitationRe(cast) {
  const names = (cast ?? []).map((s) => s.handle).filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return names.length ? new RegExp(`@(${names.join("|")})\\b`, "g") : null;
}

/** The subjects the given texts cite, as a Set of names. */
function citedSubjects(texts, cast) {
  const pattern = subjectCitationRe(cast);
  const found = new Set();
  if (!pattern) return found;
  for (const text of texts) {
    for (const match of String(text ?? "").matchAll(pattern)) found.add(match[1]);
  }
  return found;
}

/** The subjects a segment's text casts into it, in cast order. */
export function citedCast(state) {
  const cast = state.cast ?? [];
  if (!cast.length) return [];
  const found = citedSubjects(poolTexts(state), cast);
  return cast.filter((subject) => found.has(subject.handle));
}

/** Whether the timeline's own texts cite a subject — "in every segment". */
export function subjectCitedGlobally(timeline, subject) {
  return citedSubjects([timeline.prompt, timeline.soundscape, timeline.music],
                       timeline.subjects ?? []).has(subject.handle);
}

/** Which segments cast a subject, as 1-based card numbers. */
export function subjectCitations(timeline, subject) {
  return timeline.segments
    .map((segment, index) => (citedCast(segment).includes(subject) ? index + 1 : null))
    .filter((n) => n !== null);
}

/** What is wrong with a subject, as one sentence, or "" if nothing is. Mirrors
 *  the refusals in `subjects.parse` and `subjects.check`, so the band can say
 *  it where it is fixable instead of at queue time.
 *
 *  `scope` is anything with `subjects` and `assets` — the piece for the shelf in
 *  the Timeline window, and the shot plus whatever pool rides on it for the one
 *  on the node face. Which files count is a fact about *where* the subject is
 *  being checked: somebody built out of a card's own attachment is fine on that
 *  card and dangling on the next one, and the surface asking is the one that
 *  knows which it is. */
export function subjectProblem(scope, subject) {
  if (!subject.handle) return "this subject has no name yet";
  if (!SUBJECT_HANDLE_RE.test(subject.handle)) {
    return "a name is letters, digits and underscores, starting with a letter — no hyphen";
  }
  const twins = (scope.subjects ?? []).filter((s) => s.handle === subject.handle);
  if (twins.length > 1) return `two subjects are both called @${subject.handle}`;
  const assets = scope.assets ?? [];
  const byHandle = new Map(assets.map((a) => [a.handle, a]));
  if (byHandle.has(subject.handle)) {
    return `@${subject.handle} is also a file's handle — one @ means one thing`;
  }
  const files = subjectFiles(subject);
  // Described in words alone is a subject: in a generation with no references
  // there is no picture to point at, and the description is the whole of what
  // the name can mean. Mirrors the same relaxation in `subjects.parse`.
  if (!files.length && !replacesOf(subject).length
      && !String(subject.description ?? "").trim()
      && !subjectFeatures(subject).length) {
    return "nothing behind them yet — hang a file on them, or describe them in words";
  }
  const wanted = [...files, ...replacesOf(subject)].filter(Boolean);
  const missing = wanted.filter((h) => !byHandle.has(h));
  if (missing.length) {
    return `built out of ${missing.map((h) => "@" + h).join(", ")}, which is not attached here`;
  }
  // A keyframe is a fact about one moment of the target video, not a reference
  // somebody is made of — `subjects.check` refuses it, so the shelf says so
  // where it can still be undone. Named separately from "not attached": the
  // file is right there, and "missing" would send the user looking for it.
  const keyframe = wanted.map((h) => byHandle.get(h)).find((a) => a.role !== "reference");
  if (keyframe) {
    return `@${keyframe.handle} is this shot's ${keyframe.role === "first_frame" ? "start" : "end"} `
         + "frame — a moment of the video being made, not a reference they are made of";
  }
  return "";
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
  // Casting a subject cites every file behind them, plus the clip they stand in
  // the place of — writing `@anna` is the whole gesture, and it would be a
  // strange one that made you name their photographs beside them. Mirrors the
  // same expansion in `compile.cited_pool`.
  for (const subject of citedCast(state)) {
    for (const handle of subjectFiles(subject)) found.add(handle);
    for (const handle of replacesOf(subject)) found.add(handle);
  }
  const own = new Set(state.assets.map((a) => a.handle));
  return pool.filter((asset) => found.has(asset.handle) && !own.has(asset.handle));
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

/**
 * The cast members a pool file belongs to — nobody, for an ordinary reference.
 *
 * A pool entry is not always something somebody attached to the piece. Growing
 * the strip past one card moves the cast's own pictures into the pool
 * (`promoteCastFiles`), because that is the only scope card 2 can see them
 * from, so a piece with two cards and two members has two pool entries nobody
 * put there — and drawn as ordinary references they read as copies of the
 * shelf right above them, which is what they were reported as.
 *
 * Claims, the same pair the promotion filters on: what a member is built out of
 * and the clips they stand in for.
 */
export function assetOwners(timeline, asset) {
  return (timeline.subjects ?? []).filter((subject) =>
    subjectFiles(subject).includes(asset.handle)
    || replacesOf(subject).includes(asset.handle));
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

/** Muted: switched off by hand or by the deletion of its last mention, kept
 *  exactly as it was attached, and out of the run. The same word a LoRA uses,
 *  and the same key compile.py reads. */
export const muted = (asset) => asset.enabled === false;

/** The references this generation actually sends. Muted ones are attached and
 *  drawn — they are the row you put one back from — but they are not references
 *  of this render in any way that counts, so the mode, the limits, the
 *  checkpoint pin and the slot counters all read through here. */
export const references = (state) =>
  state.assets.filter((a) => a.role === "reference" && !muted(a));
export const refImages = (state) => references(state).filter((a) => a.kind === "image");
// The same bucketing compile.py does: a video kept for its soundtrack alone is
// an audio reference, and never a video one.
export const soundOnly = (asset) => asset.kind === "video" && asset.track === "sound";
export const refVideos = (state) => references(state).filter((a) => a.kind === "video" && !soundOnly(a));
export const refAudios = (state) => references(state).filter((a) => a.kind === "audio" || soundOnly(a));
export const frameAsset = (state, role) => state.assets.find((a) => a.role === role) || null;

// ---- how long a reference is, against how long the card is ------------------
//
// Two lengths that never used to meet. A card's is `duration_s`, set on the
// pill; a reference's is its trim, or the file's own as the probe read it. The
// generation has to answer for the difference: `media.load_all` cuts every
// reference video down to the card's frame count, so a 12-second clip on a
// 6-second card loses half of itself, and a standalone audio reference is sent
// whole against a card that is not as long as it is.
//
// Every clip has a length and every clip is cut by it, so the offer is made for
// all of them — how a reference is narrowed does not change what the card does
// with the time it occupies, and a rule that withheld the offer from some takes
// only meant the one file somebody wanted to match could not be matched. A
// cast member's voice is narrowed to "voice" and the clip they stand in for to
// "edit"; both are ordinary references with a length, and both are exactly the
// case this exists for.
//
// The takes below still decide *which* reference the pill volunteers when a
// card carries several: these are the ones the length leads — a signal in time,
// or a whole-clip relationship — against a clip mined for a look, which is a
// moving still and the last one worth matching to.
export const LENGTH_LED = {
  audio: ["full", "copy", "music", "voice", "ambience"],
  video: ["full", "motion", "camera", "edit", "continue"],
};

/** Whether this reference has a length at all — every clip does, no picture
 *  does. Kept as a name because "has a length" is the question three callers
 *  are asking, and `kind !== "image"` is not what any of them mean. */
export const timed = (asset) => asset?.kind === "video" || asset?.kind === "audio";

/** Whether the length is what this reference is mainly about — the tiebreak
 *  when a card carries several. */
export const lengthLed = (asset) =>
  (LENGTH_LED[scopeKind(asset)] ?? []).includes(takes(asset));

/**
 * A reference's own length in seconds, or null while it is not known.
 *
 * The trim decides it where there is one — that range *is* the reference. The
 * whole file's length is not in the blob and never has been: it is a fact about
 * the file, so it comes from the probe route, and `lengthOf` is the caller's
 * cache of those answers.
 */
export function refSeconds(asset, lengthOf) {
  const trim = asset?.trim;
  if (trim && Number.isFinite(trim.start) && Number.isFinite(trim.end) && trim.end > trim.start) {
    return trim.end - trim.start;
  }
  const whole = lengthOf?.(asset?.filename);
  return Number.isFinite(whole) && whole > 0 ? whole : null;
}

/** A card length as the UI says it. Whole seconds plain, as they have always
 *  been read; a matched one to the two decimals `matchSeconds` wrote, because
 *  the whole point of that number is that it is not a whole second. */
export const showSeconds = (seconds) => {
  const value = Number(seconds) || 0;
  return Number.isInteger(value) ? String(value) : round2(value).toFixed(2);
};

/** Every reference this card is generated against whose length means something,
 *  with the length — the card's own and the pool ones its text cites, because
 *  both ride into this one generation. */
export function timedRefs(state, lengthOf) {
  const found = [];
  for (const asset of [...references(state), ...citedPool(state)]) {
    if (!timed(asset)) continue;
    const seconds = refSeconds(asset, lengthOf);
    if (seconds !== null) found.push({ asset, seconds });
  }
  return found;
}

/**
 * The offer the duration pill makes, or null when there is nothing to say.
 *
 * The longest reference, because that is the one the card is otherwise cutting
 * — but a clip the length leads beats one mined for a look at any length, so a
 * shot carrying a line of dialogue and a forty-second style plate offers the
 * line. `duration` is what the pill would write — `matchSeconds`, not a rounded
 * second — and `matched` is whether the card already lands on the same frame
 * count, which is the only sense in which two lengths can agree here.
 */
export function lengthMatch(state, lengthOf, piece) {
  // The grid the offer lands on is the piece's family's: `matchSeconds` answers
  // in the model's own units precisely because whole seconds do not cover the
  // frame grid evenly, and which grid that is differs by family.
  const rules = rulesFor(pieceFamily(piece));
  let longest = null;
  for (const entry of timedRefs(state, lengthOf)) {
    const better = !longest
      || (lengthLed(entry.asset) && !lengthLed(longest.asset))
      || (lengthLed(entry.asset) === lengthLed(longest.asset)
          && entry.seconds > longest.seconds);
    if (better) longest = entry;
  }
  if (!longest) return null;
  const duration = matchSeconds(longest.seconds, rules);
  return {
    asset: longest.asset,
    seconds: longest.seconds,
    duration,
    matched: framesForSeconds(Number(state.duration_s) || 0, rules)
             === framesForSeconds(duration, rules),
  };
}

export function hasReferences(state) {
  // A cited pool reference is a reference of this generation in every way that
  // matters — the mode, the checkpoint, the pin — even though the asset lives
  // on the timeline. Mirrors what compile's injection makes true.
  return references(state).length > 0 || citedPool(state).length > 0;
}

/** A timeline segment that starts from the previous segment's last frame. */
export const continues = (state) => state.continue === true;

/** `width` retargeted onto a piece's own feather grid — the nearest run its
 *  video VAE can encode standalone. What `setFamily` does to every seam on a
 *  family switch, and what applying a preset written on another family has to
 *  do to the one it carries: H3's medium 22 reaches LTX 2.5 as 25, where left
 *  alone it would fall off the grid and be silently the classic single frame.
 *  1 stays 1 — the classic seam is on every family's grid. */
export function nearestFeather(width, piece) {
  const n = Number(width);
  if (!Number.isFinite(n) || n <= 1) return 1;
  const grid = featherGridOf(piece);
  return grid.reduce((best, f) => (Math.abs(f - n) < Math.abs(best - n) ? f : best), grid[0]);
}

/** The widths the seams of *this* piece may be. A family's own grid, because
 *  the run a seam inherits has to be one its video VAE can encode standalone —
 *  H3 takes 5 frames where LTX 2.5 would crop the same run to 1 and go on
 *  claiming a feathered seam. See `canvas.feather_grid`. */
export const featherGridOf = (piece) => featherGrid(rulesFor(pieceFamily(piece)));

/** The same grid for a seam that belongs to no piece yet — the shipped starters,
 *  which are family-neutral by design and are retargeted by `nearestFeather`
 *  when one is applied to a card.
 *
 *  A named export rather than `featherGridOf()` with nothing in the brackets,
 *  which is what this was. Omitting the piece and meaning "the default family"
 *  reads identically to omitting it by mistake, and `pieceFamily` cannot tell
 *  them apart — so the one caller that means it says so, and everybody else
 *  gets an error. */
export const DEFAULT_FEATHER_GRID = featherGrid(rulesFor(DEFAULT_VIDEO_FAMILY));

/** Whether this seam also names its boundary frame to the text encoder, on
 *  top of the run it pins for the DiT. Only meaningful on a blended seam and
 *  on a family that presents pictures at all — an unblended seam's boundary
 *  frame *is* the seam and is always named, and a family with one conditioning
 *  channel has nothing to say twice. Mirrors `Compiled.feather_pin`. */
export function featherPin(segment, piece) {
  return segment.feather_pin === true
    && feather(segment, piece) > 1
    && canDo(piece, "seam_pin");
}

/** The seam's width in frames — a valid grid value, or the classic 1. */
export function feather(segment, piece) {
  const grid = featherGridOf(piece);
  return grid.includes(segment.feather) && segment.feather > 1 ? segment.feather : 1;
}

/** The widest feather this segment's duration allows. Mirrors compile: the
 *  overlap is trimmed off after decode, so it must stay under half the clip. */
export function maxFeather(segment, piece) {
  const rules = rulesFor(pieceFamily(piece));
  const frames = framesForSeconds(segment.duration_s, rules);
  return featherGrid(rules).filter((f) => 2 * f <= frames).pop() ?? 1;
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

/** What this generation is, in the piece's family's own names.
 *
 *  The vocabulary is the family's — H3 names the payload forms its training
 *  distinguishes (`T2VA`, `REF2VA`), LTX 2.5 names the guides its segment node
 *  builds — so a card read the default family's list said `T2VA` over an LTX
 *  piece, which is the name of something that family has never heard of.
 *
 *  **A family may declare no reference mode**, and LTX 2.5 does not: attaching
 *  a file changes nothing its segment node builds, so a card carrying one still
 *  says what its frames make it. Absent, this falls through to them. Mirrors
 *  `compile._derive_mode`, whose reference arm is H3's checkpoint split. */
export function mode(state, piece) {
  const modes = modesOf(pieceFamily(piece));
  if (modes.reference && hasReferences(state)) return modes.reference;
  const first = frameAsset(state, "first_frame");
  const last = frameAsset(state, "last_frame");
  if (continues(state)) return last ? modes.opens_closes : modes.opens;
  if (first && last) return modes.opens_closes;
  if (first) return modes.opens;
  if (last) return modes.closes;
  return modes.text;
}

/** What each bucket currently holds. A video with its sound on occupies both a
 *  video slot and an audio one, which is the rule compile.py enforces.
 *
 *  `except` leaves one asset out of the count — the sheet the picker was opened
 *  on, whose panels are the selection being edited and would otherwise be
 *  counted twice.
 */
function counts(state, piece = null, except = null) {
  // How an image reference is counted is the family's grammar. On a sheet
  // family the references are the panels of one composite, so the panels are
  // what the cap is about (mirrors `LTX25Grammar.refuse` — a plate counted as
  // one would let a twelve-panel sheet through a nine-panel limit). Everywhere
  // else a sheet is one encoded picture among the others, and counting its
  // panels would charge one H3 reference slot per storyboard cell (mirrors
  // `Grammar.refuse`, which counts attachments).
  const panels = sheetRefs(piece ?? state);
  const images = refImages(state).filter((a) => a !== except)
    .reduce((n, a) => n + (panels ? Math.max(1, a.panels?.length ?? 0) : 1), 0);
  const videos = refVideos(state).length;
  const audios = refAudios(state).length
    + refVideos(state).filter((v) => v.track === "picture+sound").length;
  return { image: images, video: videos, audio: audios, files: images + videos + audios };
}

/** How many slots a kind has left, for the picker's "n / 9 slots filled".
 *
 *  `piece` is optional and trailing, the way `lengthMatch` takes it: a caller
 *  with the piece in hand gets that family's caps, and one without gets the
 *  default family's. Optional rather than required because half the call sites
 *  are inside a lone Creator node, where the piece *is* the state. */
export function capacity(state, kind, piece = null, except = null) {
  const used = counts(state, piece, except);
  const max = refCaps(piece ?? state)[kind];
  return { used: used[kind], max, filesLeft: refCaps(piece ?? state).files - used.files };
}

/**
 * Why the references as they now stand would not compile, or null. The same
 * limits as `_derive_mode`, checked after a change has been applied, so a switch
 * that would fail at queue time can be handed back while it is still reversible.
 *
 * The zero case gets its own sentence. "At most 0 reference images" is true and
 * useless; what a user switching a piece to a family with no reference grammar
 * needs to hear is that the files have to come off, and why.
 */
export function overflow(state, piece = null) {
  const used = counts(state, piece);
  const caps = refCaps(piece ?? state);
  if (!caps.files) {
    return used.files
      ? t("{family} reads no attached references — an attached file would reach it "
        + "as an ordinal in the prompt with nothing behind it. Detach them, or put "
        + "the piece back on a model that reads them.",
          { family: familyOf(piece ?? state).label })
      : null;
  }
  // A kind this family reads none of gets the zero sentence too, for the reason
  // the whole-family case above does: "at most 0 reference videos" is true and
  // useless. It happens on LTX 2.5, whose grammar is a sheet of stills — nine
  // pictures, no clips, no sound.
  for (const kind of ["video", "audio", "image"]) {
    if (caps[kind] === 0 && used[kind] > 0) {
      return t("{family} reads references as stills only — detach the {kind} "
             + "references, or put the piece on a model that reads them.",
               { family: familyOf(piece ?? state).label, kind: t(kind) });
    }
  }
  // A sheet family carries its image references as ONE composite file, and the
  // compiler refuses loose seconds rather than laying out a sheet nobody saw.
  if (sheetRefs(piece ?? state) && refImages(state).length > 1) {
    return t("{family} reads one reference image — the sheet the picker lays out "
           + "as you choose the files. Combine these into one sheet.",
             { family: familyOf(piece ?? state).label });
  }
  if (used.image > caps.image) return t("At most {max} reference images.", { max: caps.image });
  if (used.video > caps.video) return t("At most {max} reference videos.", { max: caps.video });
  if (used.audio > caps.audio) {
    return t("At most {max} reference audio clips, counting video soundtracks.", { max: caps.audio });
  }
  if (used.files > caps.files) return t("At most {max} reference files in total.", { max: caps.files });
  return null;
}

/** Attached pictures an aspect ratio can be taken from — everything but sound:
 *  frames, reference images, and reference videos not cited for their
 *  soundtrack alone. Mirrors the assets `compile_request` accepts as an
 *  `aspect_source`. */
export const aspectDonors = (state) =>
  state.assets.filter((a) => a.kind === "image"
                             || (a.kind === "video" && a.track !== "sound"));

/**
 * The asset whose own pixels decide the ratio under the current aspect source,
 * or null when the pill's preset rules. Mirrors `compile_request`'s resolution
 * order: an explicit handle names any attached picture (a mirrored pool
 * reference included), "pill" forces the preset, and auto is the rule that
 * always held — the anchor frame, then the pill.
 */
export function aspectSourceAsset(state) {
  const source = state.aspect_source ?? "auto";
  if (source === "pill") return null;
  if (source !== "auto") {
    return aspectDonors(state).find((a) => a.handle === source)
      ?? (state.pool ?? []).find((a) => a.handle === source && a.kind !== "audio"
                                        && !soundOnly(a))
      ?? null;
  }
  return frameAsset(state, "first_frame") || frameAsset(state, "last_frame");
}

/** The resolved geometry and duration shown on the pills. `sourceSize` is the
 *  pixel size of `aspectSourceAsset`'s answer, when the caller has probed it —
 *  the keyframe under the auto rule, any chosen picture otherwise.
 *
 *  `piece` is where the family lives: the frame grid, the rate and the area cap
 *  are the weights' and a card carries none of them. Absent means the default
 *  family, which is what every caller meant before there were two. */
export function resolved(state, sourceSize = null, piece = null) {
  const rules = rulesFor(pieceFamily(piece));
  const frames = framesForSeconds(state.duration_s, rules);
  let ratio = rules.aspects.find(([label]) => label === state.aspect)?.[1] ?? 16 / 9;
  let fromImage = false;
  if (sourceSize && sourceSize.width && sourceSize.height) {
    ratio = sourceSize.width / sourceSize.height;
    fromImage = true;
  }
  const [width, height] = resolveCanvas(ratio, state.short_edge, rules);
  return { frames, seconds: secondsForFrames(frames, rules),
           width, height, ratio, fromImage };
}

/**
 * Why the UI blocks an action, or null. Frames and references share a
 * generation now — the frames ride as pinned guides Ref2VA reads alongside its
 * references, exactly as a seam's inherited frame always has — so what is left
 * here is the one true redundancy: a continuation *is* a start frame, so a
 * segment cannot also name a file for the slot.
 */
export function blockedReason(state, action) {
  if (action === "first_frame" && continues(state)) {
    return t("This segment's start frame is an earlier segment's last frame. Turn continuation off to choose one.");
  }
  if (action === "continue" && frameAsset(state, "first_frame")) {
    return t("Remove this segment's start frame first — continuing would replace it with the source "
           + "segment's last frame.");
  }
  return null;
}

// ---- what an attached picture is *for*, after the fact -----------------------
//
// A file used to be told what it was at the moment it arrived: picked on the
// Start frame pill it was the start frame, picked with Add image it was a
// reference, and that was the end of it. Changing your mind meant taking it
// off and finding it again on the other pill — which spends a handle, so a
// prompt that cited @img-1 comes back citing nothing.
//
// The role is a property of the attachment, not of the picking, so it moves.
// `rerole` is the whole of it; `reroleBlocked` is why it sometimes cannot.

/** The role an asset carries. Written on every attachment this pack makes; the
 *  default is what an older blob's untyped attachment always meant. */
export const roleOf = (asset) => asset?.role ?? "reference";

export const ATTACH_ROLES = ["first_frame", "last_frame", "reference"];

/** What this picture is doing on the card, in the word the chip wears. */
export const roleLabel = (role) =>
  (role === "first_frame" ? t("start") : role === "last_frame" ? t("end") : t("reference"));

/** The assets as they would stand with `asset` attached as `role` — clones, for
 *  asking the caps a question without answering it. See `rerole` for why an
 *  occupied slot is a swap. */
function reroled(state, asset, role) {
  const from = roleOf(asset);
  return state.assets.map((a) => {
    if (a === asset) return { ...a, role };
    return role !== "reference" && roleOf(a) === role ? { ...a, role: from } : a;
  });
}

/**
 * Why @handle cannot be attached as `role` instead, or null.
 *
 * Four answers, in the order they are worth hearing: a file that could never be
 * a frame, a picture narrowed or cut and so not a whole frame, a slot the
 * segment's continuation already fills, and a family with no room for another
 * reference. The middle two are fixable in the rows right above the one this
 * refuses in, which is why they are refusals and not silent repairs — a frame
 * is bound whole (`compile._parse_assets` refuses the alternative), and a
 * picture quietly un-cut on promotion is a file changed behind somebody's back.
 */
export function reroleBlocked(state, asset, role, piece = null) {
  if (roleOf(asset) === role) return null;
  if (role !== "reference") {
    if (asset.kind !== "image") {
      return t("A shot opens and closes on a still. @{handle} is a {kind}, so it can only "
             + "be a reference.", { handle: asset.handle, kind: t(asset.kind) });
    }
    if (isPlate(asset) && asset.panels.length > 1) {
      return t("A sheet is several pictures in one file — there is no single frame in it "
             + "for the shot to open or close on.");
    }
    // A lone panel is how a cut-out picture is carried: the file named on the
    // asset is the cut version, and the panel under it is the photograph it was
    // lifted out of. Said as the cut, because that is what somebody set.
    if (isPlate(asset)) {
      return t("This picture is cut out of its background. A frame is used whole — keep the "
             + "background, and it can be one.");
    }
    if (takes(asset) !== "full") {
      return t("A frame is used whole: the shot opens or closes on the picture itself, so "
             + "there is nothing for it to be read as a part of. Set it back to full first.");
    }
    const why = blockedReason(state, role);
    if (why) return why;
  }
  // Applied and then read back, rather than counted by hand: a promotion into
  // an occupied slot hands that picture the role this one is leaving, and what
  // the caps have to answer is the whole trade. Only a refusal this change
  // *causes* is one — a card already over its family's cap is over it either
  // way, and saying so here would block every move out of the state that fixes
  // it.
  const after = overflow({ ...state, assets: reroled(state, asset, role) }, piece);
  return after && after !== overflow(state, piece) ? after : null;
}

/**
 * Attach @handle as `role` instead, in place — so the handle, the file and
 * everything set on it survive, and a prompt citing it still fits.
 *
 * A slot that was taken is swapped, never emptied: the picture standing there
 * takes the role this one is leaving, because "make this the end frame" is not
 * a request to lose the end frame you had, and the two-frame case is the one
 * this gesture exists for — you attached them the wrong way round.
 *
 * Muting comes off on the way to a frame. A mute is "attached, and out of this
 * run", which a keyframe cannot be — `compile._parse_assets` refuses one — and
 * making a picture the opening of the shot is not an ambiguous way to say you
 * want it in.
 */
export function rerole(state, asset, role) {
  const from = roleOf(asset);
  if (from === role) return;
  if (role !== "reference") {
    const held = state.assets.find((a) => a !== asset && roleOf(a) === role);
    if (held) held.role = from;
    delete asset.enabled;
  }
  asset.role = role;
}

/**
 * Why the seam in front of a clip cannot be made live, or null.
 *
 * A different question from `blockedReason`, and asked of a different card: a
 * clip is not conditioned on anything, so what this seam does is pin the *end*
 * of the shot behind it. A shot carrying references takes the pin like any
 * other — the frame rides as a pinned guide on Ref2VA — so the only conflict
 * left is a shot that already names its own end frame.
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
  return null;
}

/** Whether a piece-level aspect source still names a picture the piece holds.
 *  `syncCanvas` prunes what fails this, so a deleted card or a detached asset
 *  cannot leave a source compile would refuse the strip over. */
export function validAspectSource(timeline, source) {
  // Piece level knows two shapes: "pill" (checked by the caller) and the
  // object form — `parseTimeline` normalizes a hand-written bare handle into
  // it before anything gets here.
  if (!source || typeof source !== "object") return false;
  const card = Number(source.card) || 0;
  if (!card) {
    return (timeline.assets ?? []).some((a) => a.handle === source.handle
      && a.kind !== "audio" && !soundOnly(a));
  }
  const segment = timeline.segments[card - 1];
  if (!segment) return false;
  if (isClip(segment)) return !source.handle;
  return aspectDonors(segment).some((a) => a.handle === source.handle);
}

/**
 * Every picture the piece could take its aspect from, for the popover:
 * `{value, card, asset}` per donor — a clip card's footage (`{card}` alone),
 * and every card's frames and visual references — plus the pool's.
 */
export function timelineAspectSources(timeline) {
  const sources = [];
  timeline.segments.forEach((segment, index) => {
    if (isClip(segment)) {
      sources.push({ value: { card: index + 1 }, card: index + 1, asset: segment });
      return;
    }
    for (const asset of aspectDonors(segment)) {
      sources.push({ value: { card: index + 1, handle: asset.handle },
                     card: index + 1, asset });
    }
  });
  for (const asset of timeline.assets ?? []) {
    if (asset.kind === "audio" || soundOnly(asset)) continue;
    sources.push({ value: { handle: asset.handle }, card: null, asset });
  }
  return sources;
}

/**
 * The size whose ratio the timeline's canvas follows, or null when the pill
 * rules. Mirrors `compile._timeline_canvas`: the chosen source when one is
 * named, else segment 1's own anchor, else the first clip. `sizeOf(filename)`
 * is the caller's probe cache and may return undefined while a probe is still
 * out — the pill then shows the preset until the answer lands.
 */
export function timelineAspectSize(timeline, sizeOf, { ignoreChoice = false } = {}) {
  const source = ignoreChoice ? undefined : timeline.aspect_source;
  if (source === "pill") return null;
  if (source && typeof source === "object") {
    const card = Number(source.card) || 0;
    if (card && isClip(timeline.segments[card - 1])) {
      const clip = timeline.segments[card - 1];
      return clip.width && clip.height ? { width: clip.width, height: clip.height } : null;
    }
    const donor = card
      ? aspectDonors(timeline.segments[card - 1] ?? { assets: [] })
          .find((a) => a.handle === source.handle)
      : (timeline.assets ?? []).find((a) => a.handle === source.handle);
    return (donor && sizeOf(donor.filename)) || null;
  }
  const head = timeline.segments[0];
  if (head && !isClip(head)) {
    const anchor = frameAsset(head, "first_frame") || frameAsset(head, "last_frame");
    if (anchor) return sizeOf(anchor.filename) || null;
  }
  const clip = timeline.segments.find((s) => isClip(s) && s.width && s.height);
  return clip ? { width: clip.width, height: clip.height } : null;
}

/** The widest blend the segment behind a clip can afford. The overlap is
 *  re-generated at that segment's tail and trimmed off it, so it comes out of
 *  that card's length and not the clip's. */
export function maxClipFeather(timeline, index) {
  const before = index > 0 ? timeline.segments[index - 1] : null;
  if (!before || isClip(before)) return 1;
  return maxFeather(before, timeline);
}
